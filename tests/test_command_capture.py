"""Behavior contracts for synthetic command-capture PCM replay."""
import json
from pathlib import Path
import unittest

from runtime.voice.capture import CaptureConfig, CommandCapture, Frame


def pcm(duration_ms):
    return b"\x00" * (duration_ms * 32)


class CommandCaptureTests(unittest.TestCase):
    def test_synthetic_replay_is_deterministic_and_bounded(self):
        """Fixture is synthetic replay, not microphone or VAD-accuracy evidence."""
        events = json.loads(Path("tests/fixtures/command-capture.json").read_text())

        def replay():
            capture = CommandCapture()
            capture.key_equal()
            result = None
            for event in events:
                result = capture.feed(Frame(pcm(event["duration_ms"]), event["speech"]))
            return result

        first, second = replay(), replay()
        self.assertEqual((first.reason, len(first.audio)), (second.reason, len(second.audio)))
        self.assertEqual((first.status, first.reason, len(first.audio)), ("processing", "silence", 38400))

    def test_speech_then_silence_returns_immutable_command_audio(self):
        capture = CommandCapture()
        token = capture.key_equal().token
        self.assertEqual(capture.feed(Frame(pcm(500), True)).status, "recording")
        result = capture.feed(Frame(pcm(700), False))
        self.assertEqual((result.status, result.reason, result.token, len(result.audio)),
                         ("processing", "silence", token, 38400))
        self.assertIsInstance(result.audio, bytes)
        self.assertEqual(capture.state, "processing")

    def test_initial_silence_discards_empty_audio(self):
        capture = CommandCapture(CaptureConfig(initial_silence_ms=100))
        token = capture.key_equal().token
        result = capture.feed(Frame(pcm(100), False))
        self.assertEqual((result.status, result.reason, result.token, result.audio),
                         ("idle", "initial-silence", token, b""))
        self.assertEqual(capture.buffered_bytes, 0)

    def test_observer_failures_retain_the_terminal_session_token(self):
        def fail_on(call_number):
            calls = []
            def observe(notice):
                calls.append(notice)
                if len(calls) == call_number:
                    raise OSError("sink")
            return observe

        start_notices = []
        def fail_start(notice):
            start_notices.append(notice)
            raise OSError("sink")
        start = CommandCapture(observe=fail_start)
        start_result = start.key_equal()
        self.assertEqual((start_result.status, start_result.reason, start_result.token),
                         ("failed", "observation-failed", start_notices[0].token))

        feed = CommandCapture(observe=fail_on(2))
        feed_token = feed.key_equal().token
        feed_result = feed.feed(Frame(pcm(1), True))
        self.assertEqual((feed_result.status, feed_result.reason, feed_result.token),
                         ("failed", "observation-failed", feed_token))

        finish = CommandCapture(observe=fail_on(3))
        finish_token = finish.key_equal().token
        finish.feed(Frame(pcm(1), True))
        finish_result = finish.feed(Frame(pcm(700), False))
        self.assertEqual((finish_result.status, finish_result.reason, finish_result.token),
                         ("failed", "observation-failed", finish_token))

    def test_long_utterance_uses_the_shorter_long_silence_bound(self):
        capture = CommandCapture(CaptureConfig(max_ms=1000, initial_silence_ms=500,
                                               short_silence_ms=100, long_silence_ms=40,
                                               long_utterance_ms=100))
        capture.key_equal()
        capture.feed(Frame(pcm(100), True))
        result = capture.feed(Frame(pcm(40), False))
        self.assertEqual((result.status, result.reason), ("processing", "silence"))

    def test_max_duration_trims_last_frame_without_overfill(self):
        capture = CommandCapture(CaptureConfig(max_ms=100, initial_silence_ms=100,
                                               short_silence_ms=100, long_silence_ms=100,
                                               long_utterance_ms=100))
        capture.key_equal()
        result = capture.feed(Frame(pcm(200), True))
        self.assertEqual((result.status, result.reason, len(result.audio)), ("processing", "max-duration", 3200))
        self.assertEqual(capture.buffered_bytes, 3200)

    def test_duplicate_hotkey_and_stale_completion_cannot_reuse_session(self):
        capture = CommandCapture()
        first = capture.key_equal().token
        self.assertEqual(capture.key_equal().status, "blocked")
        capture.feed(Frame(pcm(1), True))
        capture.cancel()
        second = capture.key_equal().token
        self.assertNotEqual(first, second)
        self.assertEqual(capture.complete(first).status, "blocked")
        self.assertEqual(capture.state, "recording")

    def test_cancel_in_processing_invalidates_completion_token(self):
        capture = CommandCapture()
        token = capture.key_equal().token
        capture.feed(Frame(pcm(1), True))
        capture.feed(Frame(pcm(700), False))
        self.assertEqual(capture.cancel().status, "canceled")
        self.assertEqual(capture.complete(token).status, "blocked")
        self.assertEqual(capture.state, "idle")

    def test_invalid_frames_are_rejected_and_observer_failure_discards_audio(self):
        for args in ((b"", False), (b"\x00", False), ("pcm", False), (pcm(1), 1)):
            with self.assertRaises(ValueError):
                Frame(*args)

        calls = []
        def failing_after_start(notice):
            calls.append(notice)
            if len(calls) > 1:
                raise OSError("sink")
        capture = CommandCapture(observe=failing_after_start)
        capture.key_equal()
        result = capture.feed(Frame(pcm(1), True))
        self.assertEqual((result.status, result.reason, result.audio), ("failed", "observation-failed", b""))
        self.assertEqual(capture.state, "idle")

    def test_invalid_feed_discards_previously_buffered_speech(self):
        capture = CommandCapture()
        capture.key_equal()
        capture.feed(Frame(pcm(1), True))
        result = capture.feed("not-a-frame")
        self.assertEqual((result.status, result.reason, result.audio), ("failed", "invalid-frame", b""))
        self.assertEqual((capture.state, capture.buffered_bytes), ("idle", 0))

    def test_config_rejects_nonpositive_bool_and_unbounded_silence_values(self):
        for patch in ({"max_ms": True}, {"max_ms": 0}, {"initial_silence_ms": 15001},
                      {"short_silence_ms": 15001}, {"long_silence_ms": 15001},
                      {"long_utterance_ms": 15001}):
            with self.assertRaises(ValueError):
                CaptureConfig(**patch)

    def test_observer_reentry_cannot_mutate_in_flight_transition(self):
        capture = CommandCapture()
        nested = []
        def observe(notice):
            nested.append(capture.cancel())
        capture.observe = observe
        result = capture.key_equal()
        self.assertEqual(result.status, "recording")
        self.assertEqual(nested[0].status, "blocked")
        self.assertEqual(capture.state, "recording")
