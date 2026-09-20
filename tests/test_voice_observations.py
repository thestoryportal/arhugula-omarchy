"""Lifecycle telemetry must round-trip without acquiring action authority."""
import json
from pathlib import Path
import tempfile
import unittest

from runtime.contracts import ContractError, decode, encode, loads
from runtime.core import ControlPlane, Outcome
from runtime.journal import JournalError, MemoryJournal, SQLiteJournal


def fixture(kind, **patch):
    records = json.loads(Path('tests/fixtures/contracts-v1.json').read_text())
    return decode({**next(item for item in records if item['kind'] == kind), **patch})


def payload(**patch):
    return {
        'kind': 'voice-observation', 'version': 1, 'event_id': 'obs-1',
        'session_id': 'voice-session-1', 'activation_id': 'activation-1',
        'correlation_id': 'corr-1', 'timestamp_ms': 100,
        'context': {**fixture('command').context, 'source': 'voice'},
        'phase': 'capture.started', 'status': 'recording',
        'code': 'capture.started', **patch,
    }


class VoiceObservationTests(unittest.TestCase):
    def test_versioned_roundtrip_snapshots_context_without_content_fields(self):
        wire = payload()
        record = decode(wire)
        self.assertEqual(type(record).__name__, 'VoiceObservation')
        self.assertEqual(encode(loads(json.dumps(wire))), wire)
        wire['context']['source'] = 'terminal'
        self.assertEqual(record.context['source'], 'voice')
        with self.assertRaises(TypeError):
            record.context['source'] = 'terminal'
        with self.assertRaises(AttributeError):
            record.status = 'success'

    def test_rejects_private_content_versions_and_authority_shaped_fields(self):
        for patch in (
            {'transcript': 'private speech'}, {'audio': 'pcm'}, {'token': 'secret'},
            {'details': {'text': 'private'}}, {'command_id': 'cmd-1'},
            {'version': 2}, {'version': True}, {'timestamp_ms': True},
            {'phase': 'voice.preview'}, {'phase': 'command.started'},
            {'status': 'approved'}, {'code': 'private speech'},
            {'activation_id': ''}, {'session_id': ''},
            {'phase': 'owner.faulted', 'status': 'success'},
        ):
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                decode(payload(**patch))

    def test_all_lifecycle_phases_are_nonexecution_records(self):
        for phase, status, code in (
            ('capture.started', 'recording', 'capture.started'),
            ('capture.stopped', 'processing', 'capture.silence'),
            ('capture.canceled', 'canceled', 'capture.canceled'),
            ('transcription.started', 'processing', 'transcription.started'),
            ('transcription.finished', 'success', 'transcription.ok'),
            ('owner.faulted', 'uncertain', 'owner.cleanup-unproven'),
        ):
            with self.subTest(phase=phase):
                record = decode(payload(phase=phase, status=status, code=code))
                self.assertEqual(encode(record)['phase'], phase)
                self.assertFalse(hasattr(record, 'command_id'))
                self.assertFalse(hasattr(record, 'interaction_id'))

    def test_both_journals_deduplicate_replay_and_preserve_receipt_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.sqlite'
            for journal in (MemoryJournal(), SQLiteJournal(path)):
                with journal, self.subTest(adapter=type(journal).__name__):
                    observation = decode(payload())
                    self.assertEqual(journal.append(observation), 1)
                    self.assertEqual(journal.append(observation), 1)
                    with self.assertRaises(JournalError):
                        journal.append(decode(payload(timestamp_ms=101)))
                    calls = []
                    plane = ControlPlane([fixture('capability')], fixture('policy'),
                                         lambda command: calls.append(command) or Outcome('success'),
                                         journal, profile=fixture('profile'))
                    replayed = []
                    journal.replay(lambda seq, event: replayed.append((seq, event.kind)))
                    self.assertEqual(replayed, [(1, 'voice-observation')])
                    self.assertEqual(calls, [])
                    self.assertEqual(plane.dispatch(fixture('command')).status, 'success')
                    self.assertEqual(len(calls), 1)
                    self.assertEqual([event.kind for _, event in journal.read()],
                                     ['voice-observation', 'event', 'event'])
            with SQLiteJournal(path) as journal:
                self.assertEqual(encode(journal.read()[0][1]), payload())
                self.assertEqual([seq for seq, _ in journal.read()], [1, 2, 3])
                self.assertEqual(journal.read()[0][1].correlation_id, 'corr-1')

    def test_observations_cannot_approve_confirmation_required_action(self):
        journal = MemoryJournal()
        journal.append(decode(payload(phase='transcription.finished', status='success',
                                      code='transcription.ok')))
        calls = []
        plane = ControlPlane([fixture('capability', risk='confirm')], fixture('policy'),
                             calls.append, journal, profile=fixture('profile'))
        result = plane.dispatch(fixture('command'))
        self.assertEqual(result.error.code, 'confirmation.required')
        self.assertEqual(calls, [])
