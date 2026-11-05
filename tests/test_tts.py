"""Real gateway routing must never grant stale text playback authority."""
import base64
from dataclasses import replace
import importlib.util
import unittest

from runtime.voice.tts_records import Code, Duck, Event, Phase, Spoken, Pause, Silent, Unchanged
from tests.test_gateway_wire import response_doc, wire


class TtsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime.voice.tts'),
                             'offline TTS output controller must exist')
        from runtime.voice.tts import PlaybackState
        from tests.tts_fakes import Rig
        self.Rig, self.PlaybackState = Rig, PlaybackState

    def finish(self, rig):
        rig.player.state = self.PlaybackState.COMPLETE
        return rig.output.poll()

    def test_primary_plays_once_after_synthesis_cleanup_and_keeps_lease(self):
        rig = self.Rig()
        self.assertTrue(rig.output.start(rig.utterance()))
        self.assertIsNone(rig.output.poll())
        self.assertEqual(rig.output.notice.phase, Phase.PLAYING)
        self.assertEqual(rig.player.audio.pcm, b'\0\0' * 240)
        self.assertLess(rig.events.index('host.cancel'), rig.events.index('player.start'))
        result = self.finish(rig)
        self.assertEqual((result.code, result.provider_id, result.failures), (Code.PLAYED, 'host', ()))
        self.assertTrue(rig.output.cleanup_proven)
        self.assertTrue(rig.owner.accepts(rig.generation))
        self.assertEqual((rig.player.cancels, rig.mix.restores), (1, 1))
        self.assertIsNone(rig.output.poll())

    def test_fallback_keeps_voice_budget_and_failure_provenance(self):
        rig = self.Rig(fallback=True)
        rig.host_error('unavailable')
        rig.output.start(rig.utterance())
        rig.clock.now = 1050
        self.assertIsNone(rig.output.poll())
        self.assertEqual((rig.local_requests[0].payload.voice, rig.local_requests[0].budget_ms),
                          ('natural', 29950))
        self.assertIsNone(rig.output.poll())
        result = self.finish(rig)
        self.assertEqual((result.code, result.provider_id), (Code.DEGRADED, 'vm'))
        self.assertEqual([(f.code, f.provider_id) for f in result.failures], [('unavailable', 'host')])

    def test_no_fallback_for_authentication_or_invalid_audio(self):
        for code in ('authentication', 'invalid_response', 'identity', 'cleanup'):
            with self.subTest(code=code):
                rig = self.Rig(fallback=True)
                rig.host_error(code)
                rig.output.start(rig.utterance())
                result = rig.output.poll()
                self.assertNotIn(result.code, (Code.PLAYED, Code.DEGRADED))
                self.assertEqual(rig.local_requests, [])
                self.assertNotIn('mix.factory', rig.events)

    def test_mute_missing_policy_silent_status_and_unavailable_have_no_effects(self):
        for kind in ('mute', 'missing', 'status', 'disabled', 'voice', 'supplier'):
            with self.subTest(kind=kind):
                rig = self.Rig()
                utterance = rig.utterance(event=Event.STATUS if kind == 'status' else Event.RESPONSE)
                if kind == 'mute':
                    rig.snapshot = replace(rig.snapshot, muted=True)
                elif kind == 'missing':
                    rig.snapshot = replace(rig.snapshot, policy=None)
                elif kind == 'disabled':
                    rig.configuration.disable()
                elif kind == 'voice':
                    rig.snapshot = replace(rig.snapshot, policy=replace(rig.snapshot.policy, voices=()))
                elif kind == 'supplier':
                    rig.hooks['snapshot'] = lambda: (_ for _ in ()).throw(RuntimeError('private'))
                self.assertFalse(rig.output.start(utterance))
                self.assertEqual(rig.host_requests, [])
                self.assertNotIn('mix.factory', rig.events)
                self.assertNotIn('player.factory', rig.events)
                self.assertTrue(rig.output.cleanup_proven)

    def test_explicit_status_and_silent_response_select_event_rule(self):
        rig = self.Rig()
        rules = (Silent(Event.RESPONSE), Spoken(Event.STATUS, 'natural', Unchanged()))
        rig.snapshot = replace(rig.snapshot, policy=replace(rig.snapshot.policy, rules=rules))
        self.assertFalse(rig.output.start(rig.utterance()))
        self.assertTrue(rig.output.start(rig.utterance('ready', Event.STATUS)))
        rig.output.poll()
        self.assertEqual(self.finish(rig).code, Code.PLAYED)

    def test_scoped_mix_restores_only_changed_state(self):
        for intent, gain, paused in ((Duck(500), 450, False), (Pause(), 900, True),
                                     (Unchanged(), 900, False)):
            with self.subTest(intent=intent):
                rig = self.Rig(mix=intent)
                rig.output.start(rig.utterance())
                rig.output.poll()
                self.assertEqual((rig.media['gain'], rig.media['paused']), (gain, paused))
                rig.media['unrelated'] = 'newer'
                self.finish(rig)
                self.assertEqual(rig.media, {'gain': 900, 'paused': False, 'unrelated': 'newer'})

    def test_new_turn_and_full_snapshot_drift_suppress_old_synthesis(self):
        for kind in ('turn', 'profile', 'context', 'audio', 'mute', 'configuration', 'generation'):
            with self.subTest(kind=kind):
                rig = self.Rig()
                rig.output.start(rig.utterance())
                s = rig.snapshot
                if kind == 'turn':
                    rig.next_turn()
                elif kind == 'profile':
                    rig.snapshot = replace(s, conversation=replace(s.conversation, revision=2))
                elif kind == 'context':
                    rig.snapshot = replace(s, conversation=replace(s.conversation,
                                           context=replace(s.conversation.context, revision=2)))
                elif kind == 'audio':
                    rig.snapshot = replace(s, policy=replace(s.policy, revision=2))
                elif kind == 'mute':
                    rig.snapshot = replace(s, muted=True)
                elif kind == 'configuration':
                    rig.configuration.disable()
                else:
                    rig.owner.cancel(generation=rig.generation)
                self.assertEqual(rig.output.poll().code, Code.STALE)
                self.assertNotIn('player.start', rig.events)
                self.assertTrue(rig.output.cleanup_proven)

    def test_same_generation_foreign_owner_session_is_denied(self):
        rig = self.Rig()
        rig.token = replace(rig.token, session_id='foreign:1')
        rig.snapshot = replace(rig.snapshot, current_turn=rig.token)
        self.assertFalse(rig.output.start(rig.utterance()))
        self.assertEqual(rig.host_requests, [])

    def test_drift_in_synthesis_cleanup_never_reaches_mix(self):
        rig = self.Rig()
        rig.hooks['host.cancel'] = lambda: rig.configuration.disable()
        rig.output.start(rig.utterance())
        result = rig.output.poll()
        self.assertNotIn(result.code, (Code.PLAYED, Code.DEGRADED))
        self.assertNotIn('mix.factory', rig.events)

    def test_replayed_turn_with_changed_text_cannot_play_again(self):
        rig = self.Rig()
        rig.output.start(rig.utterance())
        rig.output.poll()
        self.finish(rig)
        self.assertFalse(rig.output.start(rig.utterance('changed text')))
        self.assertEqual(rig.output.notice.code, Code.REPLAY)
        self.assertEqual(len(rig.host_requests), 1)

    def test_busy_start_preserves_existing_job_and_terminal_requires_consumption(self):
        rig = self.Rig()
        rig.output.start(rig.utterance())
        self.assertFalse(rig.output.start(rig.utterance('second')))
        self.assertEqual(rig.host_job.cancels, 0)
        rig.output.cancel()
        self.assertFalse(rig.output.start(rig.utterance('third')))
        self.assertEqual(rig.output.poll().code, Code.CANCELED)
        self.assertTrue(rig.owner.accepts(rig.generation))

    def test_health_expiry_and_poll_limits_fail_without_output(self):
        rig = self.Rig()
        rig.clock.now = 1101
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.UNAVAILABLE)
        self.assertEqual(rig.host_requests, [])
        rig = self.Rig()
        rig.replies['host'] = None
        rig.output.start(rig.utterance())
        for _ in range(7):
            self.assertIsNone(rig.output.poll())
        self.assertEqual(rig.output.poll().code, Code.LIMIT)
        self.assertNotIn('mix.factory', rig.events)

    def test_playback_limit_and_failure_never_retry_synthesis(self):
        for state in (self.PlaybackState.PENDING, self.PlaybackState.FAILED, 'invalid'):
            rig = self.Rig(fallback=True)
            rig.output.start(rig.utterance())
            rig.output.poll()
            rig.player.state = state
            result = None
            for _ in range(8):
                result = rig.output.poll()
                if result:
                    break
            self.assertNotIn(result.code, (Code.PLAYED, Code.DEGRADED))
            self.assertEqual(len(rig.host_requests), 1)
            self.assertEqual(rig.local_requests, [])
            self.assertTrue(rig.output.cleanup_proven)

    def test_pcm_wire_bounds_and_sample_format_precede_output(self):
        for size in (0, 1, 2, 480000, 480002):
            with self.subTest(size=size):
                rig = self.Rig()
                rig.replies['host'] = lambda request: wire(response_doc(request, result={
                    'pcm_b64': base64.b64encode(b'\0' * size).decode(),
                    'sample_rate': 24000, 'channels': 1, 'sample_width': 2}))
                rig.output.start(rig.utterance())
                result = rig.output.poll()
                if size in (2, 480000):
                    self.assertIsNone(result)
                    self.assertEqual(len(rig.player.audio.pcm), size)
                    rig.output.cancel()
                else:
                    self.assertEqual(result.code, Code.INVALID_AUDIO)
                    self.assertNotIn('player.start', rig.events)
        rig = self.Rig()
        rig.replies['host'] = lambda request: wire(response_doc(request, result={
            'pcm_b64': 'AAA=', 'sample_rate': 16000, 'channels': 1, 'sample_width': 2}))
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.INVALID_AUDIO)

    def test_text_byte_budget_refuses_before_provider(self):
        rig = self.Rig()
        self.assertFalse(rig.output.start(rig.utterance('界' * 16384)))
        self.assertEqual(rig.output.notice.code, Code.LIMIT)
        self.assertEqual(rig.host_requests, [])
