"""Policy mistakes must deny output before the gateway or audio boundaries."""
from dataclasses import FrozenInstanceError, replace
import importlib.util
import unittest

from runtime.gateway.admission import Bearer
from runtime.gateway.client import Endpoint, Host, Local, Failure
from runtime.providers.configuration import Active, Candidate, Disabled
from runtime.providers.records import parse_manifest, parse_policy
from tests.test_conversation_records import fixture, token
from tests.test_gateway_wire import host_provider
from tests.test_provider_records import manifest_doc, policy_doc


def values(r, fallback=False):
    host = Host(host_provider(), Endpoint('https://host.test/v1/gateway', 'a' * 64),
                Bearer('s' * 32), object())
    local = Local(host_provider(provider_id='vm', placement='vm'), lambda *_: None)
    active = Active(1, Candidate(0, (parse_manifest(manifest_doc()),), host,
                                 local if fallback else None, parse_policy(policy_doc()), ()))
    voices = (r.RouteVoice('host', 'm1', 'natural'),)
    if fallback:
        voices += (r.RouteVoice('vm', 'm1', 'natural'),)
    policy = r.AudioPolicy('personal', 'local', 1, 1,
                           (r.Spoken(r.Event.RESPONSE, 'natural', r.Unchanged()),),
                           voices, r.Limits(16384, 30000, 8, 8))
    return r.AudioSnapshot(fixture(), token(), policy, False), active


class TtsRecordsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime.voice.tts_records'),
                             'closed TTS policy records must exist')
        from runtime.voice import tts_records
        self.r = tts_records
        self.snapshot, self.active = values(self.r)
        self.u = self.r.Utterance(token(), self.r.Event.RESPONSE, 'private answer')

    def test_numeric_and_mix_bounds_reject_bool_mutation(self):
        r = self.r
        for field, ceiling in (('text_chars', 16384), ('synthesis_ms', 30000),
                               ('synthesis_polls', 1024), ('playback_polls', 1024)):
            for value in (True, 0, -1, 1.0, ceiling + 1):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(self.snapshot.policy.limits, **{field: value})
            replace(self.snapshot.policy.limits, **{field: ceiling})
        for gain in (True, -1, 1000, 0.5):
            with self.assertRaisesRegex(ValueError, 'tts.invalid-record'):
                r.Duck(gain)
        self.assertEqual((r.Duck(0).gain_milli, r.Duck(999).gain_milli), (0, 999))

    def test_policy_requires_closed_immutable_unique_rules_and_routes(self):
        r, p = self.r, self.snapshot.policy
        for changes in ({'revision': True}, {'configuration_revision': 0},
                        {'revision': 2**53}, {'profile_id': '-bad'},
                        {'rules': list(p.rules)}, {'rules': p.rules * 2},
                        {'rules': (object(),)}, {'voices': p.voices * 2},
                        {'voices': list(p.voices)}, {'limits': None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(p, **changes)
        with self.assertRaises(FrozenInstanceError):
            p.revision = 2
        for voice in ('', '-bad', 'a b', 'a' * 129, None):
            with self.assertRaises(ValueError):
                r.RouteVoice('host', 'm1', voice)
        for args in (('response', 'natural', r.Unchanged()),
                     (r.Event.RESPONSE, 'natural', 'duck')):
            with self.assertRaises(ValueError):
                r.Spoken(*args)
        with self.assertRaises(ValueError):
            r.Silent('status')

    def test_snapshot_utterance_and_notices_are_closed_and_private(self):
        r = self.r
        for changes in ({'muted': 1}, {'current_turn': {}}, {'policy': {}},
                        {'conversation': None}):
            with self.assertRaises(ValueError):
                replace(self.snapshot, **changes)
        for changes in ({'token': {}}, {'event': 'response'}, {'text': ''},
                        {'text': ' '}, {'text': '\ud800'}, {'text': 'a\x00b'},
                        {'text': 'x' * 16385}):
            with self.assertRaises(ValueError):
                replace(self.u, **changes)
        self.assertNotIn('private answer', repr(self.u))
        with self.assertRaises(ValueError):
            r.Notice('idle', r.Code.IDLE)
        with self.assertRaises(ValueError):
            r.Completion(r.Code.PLAYED, 'host', None, ())
        with self.assertRaises(ValueError):
            r.Completion(r.Code.PLAYED, 'host', 'm1', [Failure('timeout', 'host', 'm1')])

    def test_primary_request_preserves_text_voice_and_explicit_budget(self):
        r = self.r
        ready = r.admit(self.u, self.snapshot, self.active, 7)
        self.assertIsInstance(ready, r.Ready)
        self.assertEqual((ready.request.payload.text, ready.request.payload.voice,
                          ready.request.provider_id, ready.request.catalog_version,
                          ready.request.budget_ms), ('private answer', 'natural', 'host', 7, 30000))
        status = r.request_id(token(), r.Event.STATUS)
        self.assertNotEqual(ready.request.request_id, status)
        changed = r.admit(replace(self.u, text='different'), self.snapshot, self.active, 7)
        self.assertEqual(ready.request.request_id, changed.request.request_id)
        self.assertNotIn('private', ready.request.request_id)

    def test_muted_missing_silent_and_disabled_are_distinct_denials(self):
        r, s = self.r, self.snapshot
        cases = [(replace(s, muted=True), self.active, self.u, r.Code.MUTED),
                 (replace(s, policy=None), self.active, self.u, r.Code.DENIED),
                 (s, Disabled(2, None), self.u, r.Code.UNAVAILABLE),
                 (s, self.active, replace(self.u, event=r.Event.STATUS), r.Code.SILENT),
                 (replace(s, conversation=replace(s.conversation, policy=None)),
                  self.active, self.u, r.Code.DENIED)]
        for field in ('enabled', 'voice_enabled'):
            conv = replace(s.conversation, profile=replace(s.conversation.profile, **{field: False}))
            cases.append((replace(s, conversation=conv), self.active, self.u, r.Code.DENIED))
        for snapshot, active, utterance, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(r.admit(utterance, snapshot, active, 7), r.Denied(expected))

    def test_foreign_turn_and_revision_mismatch_deny(self):
        r, s = self.r, self.snapshot
        for field, value in (('turn', 2), ('profile_id', 'foreign'), ('profile_revision', 2),
                             ('policy_revision', 2), ('context_revision', 2)):
            with self.subTest(field=field):
                u = replace(self.u, token=replace(self.u.token, **{field: value}))
                self.assertEqual(r.admit(u, s, self.active, 7), r.Denied(r.Code.STALE))
        for field, value in (('profile_id', 'foreign'), ('policy_id', 'foreign'),
                             ('configuration_revision', 2)):
            altered = replace(s, policy=replace(s.policy, **{field: value}))
            self.assertEqual(r.admit(self.u, altered, self.active, 7), r.Denied(r.Code.DENIED))

    def test_fallback_requires_compatible_voice_on_every_route(self):
        r = self.r
        snapshot, active = values(r, True)
        self.assertIsInstance(r.admit(self.u, snapshot, active, 7), r.Ready)
        for voice in (r.RouteVoice('vm', 'm2', 'natural'), r.RouteVoice('vm', 'm1', 'other')):
            bad = replace(snapshot, policy=replace(snapshot.policy,
                          voices=(snapshot.policy.voices[0], voice)))
            self.assertEqual(r.admit(self.u, bad, active, 7), r.Denied(r.Code.DENIED))

    def test_character_and_wire_byte_limits_are_not_truncated(self):
        r = self.r
        ascii_input = replace(self.u, text='x' * 16384)
        self.assertEqual(len(r.admit(ascii_input, self.snapshot, self.active, 7).request.payload.text), 16384)
        multibyte = replace(self.u, text='界' * 16384)
        self.assertEqual(r.admit(multibyte, self.snapshot, self.active, 7), r.Denied(r.Code.LIMIT))
        small = replace(self.snapshot, policy=replace(self.snapshot.policy,
                        limits=replace(self.snapshot.policy.limits, text_chars=3)))
        self.assertEqual(r.admit(self.u, small, self.active, 7), r.Denied(r.Code.LIMIT))
