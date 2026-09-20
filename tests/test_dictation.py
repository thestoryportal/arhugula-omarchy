import json
from pathlib import Path
import unittest

from runtime.contracts import decode
from runtime.voice.dictation import Delivery, Dictation, FocusToken


class Capture:
    def __init__(self):
        self.starts = self.stops = self.cancels = 0
        self.fail_start = self.fail_stop = self.fail_cancel = False

    def start(self):
        self.starts += 1
        if self.fail_start:
            raise OSError("private device")

    def stop(self):
        self.stops += 1
        if self.fail_stop:
            raise OSError("private device")
        return b"pcm-fixture"

    def cancel(self):
        self.cancels += 1
        if self.fail_cancel:
            raise OSError("private device")


class Output:
    def __init__(self):
        self.typed, self.copied = [], []
        self.typing = Delivery("delivered")
        self.clipboard = Delivery("delivered")

    def type_text(self, text, target):
        self.typed.append((text, target))
        if isinstance(self.typing, Exception):
            raise self.typing
        return self.typing

    def copy_text(self, text):
        self.copied.append(text)
        return self.clipboard


class DictationTests(unittest.TestCase):
    def make(self, **provider_patch):
        payload = next(item for item in json.loads(Path("tests/fixtures/contracts-v1.json").read_text()) if item["kind"] == "provider")
        provider = decode({**payload, "enabled": True, "health": "healthy", "capabilities": ["transcription"], **provider_patch})
        self.capture, self.output = Capture(), Output()
        self.target = FocusToken("editor", 1)
        self.notices, self.transcriptions = [], []
        self.transcription = "hello"
        def transcribe(audio):
            self.transcriptions.append(audio)
            if isinstance(self.transcription, Exception):
                raise self.transcription
            return self.transcription
        return Dictation(self.capture, transcribe, self.output, lambda: self.target,
                         provider, self.notices.append)

    def test_home_end_direct_typing_and_repeat_keys(self):
        session = self.make()
        self.assertEqual(session.home().status, "recording")
        self.assertEqual(session.home().code, "capture.busy")
        self.assertEqual(session.end().status, "success")
        self.assertEqual(session.end().code, "capture.idle")
        self.assertEqual(self.capture.starts, 1)
        self.assertEqual(self.capture.stops, 1)
        self.assertEqual(self.output.typed, [("hello", FocusToken("editor", 1))])
        self.assertEqual(self.output.copied, [])
        self.assertEqual(session.state, "idle")
        self.assertNotIn("hello", repr(self.notices))
        self.assertEqual(len({notice.interaction_id for notice in self.notices}), 1)

    def test_definite_nondelivery_uses_clipboard_without_pasting(self):
        session = self.make()
        self.output.typing = Delivery("not-delivered")
        session.home()
        result = session.end()
        self.assertEqual((result.status, result.delivery), ("success", "clipboard"))
        self.assertEqual(self.output.copied, ["hello"])

    def test_uncertain_exception_and_invalid_delivery_never_fall_back(self):
        for delivery in (Delivery("uncertain"), OSError("partial secret"), "invalid"):
            session = self.make()
            self.output.typing = delivery
            session.home()
            result = session.end()
            self.assertEqual(result.status, "uncertain")
            self.assertEqual(self.output.copied, [])
            self.assertNotIn("secret", repr(result))

    def test_focus_change_blocks_typing_and_clipboard(self):
        session = self.make()
        session.home()
        self.target = FocusToken("browser", 2)
        self.assertEqual(session.end().code, "focus.changed")
        self.assertEqual(self.output.typed, [])
        self.assertEqual(self.output.copied, [])

    def test_focus_change_after_typing_refusal_blocks_fallback(self):
        session = self.make()
        def refuse(text, focus):
            self.target = FocusToken("browser", 2)
            return Delivery("not-delivered")
        self.output.type_text = refuse
        session.home()
        self.assertEqual(session.end().code, "focus.changed")
        self.assertEqual(self.output.copied, [])

    def test_nonlocal_unavailable_and_wrong_capability_provider_block_capture(self):
        for patch in ({"placement": "host"}, {"enabled": False}, {"health": "unavailable"}, {"capabilities": ["intent"]}):
            session = self.make(**patch)
            self.assertEqual(session.home().status, "blocked")
            self.assertEqual(self.capture.starts, 0)

    def test_transcription_failure_and_empty_text_never_output(self):
        for transcript in (OSError("private transcript"), " ", b"wrong", None):
            session = self.make()
            self.transcription = transcript
            session.home()
            self.assertEqual(session.end().status, "failed")
            self.assertEqual(self.output.typed, [])
            self.assertEqual(session.state, "idle")

    def test_cancel_discards_and_capture_cleanup_failure_latches_fault(self):
        session = self.make()
        session.home()
        self.assertEqual(session.cancel().status, "canceled")
        self.assertEqual(self.transcriptions, [])
        self.assertEqual(self.output.typed, [])
        session.home()
        self.capture.fail_cancel = True
        self.assertEqual(session.cancel().status, "uncertain")
        self.assertEqual(session.state, "faulted")
        self.assertEqual(session.home().code, "capture.faulted")

    def test_capture_start_and_stop_errors_attempt_cleanup(self):
        for operation in ("start", "stop"):
            session = self.make()
            setattr(self.capture, "fail_" + operation, True)
            result = session.home()
            if operation == "stop":
                result = session.end()
            self.assertEqual(result.status, "failed")
            self.assertEqual(self.capture.cancels, 1)
            self.assertEqual(self.output.typed, [])

    def test_observation_failure_prevents_capture(self):
        session = self.make()
        session.observe = lambda notice: (_ for _ in ()).throw(OSError("sink"))
        self.assertEqual(session.home().status, "blocked")
        self.assertEqual(self.capture.starts, 0)

    def test_reentrant_observer_cannot_start_a_second_capture(self):
        session = self.make()
        nested = []
        def observe(notice):
            if not nested:
                nested.append(None)
                nested[0] = session.home()
        session.observe = observe
        self.assertEqual(session.home().status, "recording")
        self.assertEqual(nested[0].code, "capture.busy")
        self.assertEqual(self.capture.starts, 1)

    def test_completion_observer_cannot_restart_before_teardown(self):
        session = self.make()
        nested = []
        def observe(notice):
            if notice.phase == "dictation.finished":
                nested.append(session.home())
        session.observe = observe
        session.home()
        self.assertEqual(session.end().status, "success")
        self.assertEqual(nested[0].code, "capture.busy")
        self.assertEqual(self.capture.starts, 1)
