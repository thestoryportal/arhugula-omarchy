"""Real VM routing with synthetic frames and in-memory worker doubles only."""
import json
from pathlib import Path
import unittest
import threading

from runtime.contracts import Event, VoiceObservation, decode, encode
from runtime.core import ControlPlane, Outcome
from runtime.journal import MemoryJournal
from runtime.voice.capture import CommandCapture, Frame
from runtime.voice.coordinator import Coordinator
from runtime.voice.process import ProcessResult
from runtime.voice.router import Action, VoiceRouter, VoiceState
from runtime.voice.session import BusyError, FaultedError, SessionOwner
from runtime.voice.transcription import TranscriptResult, TranscriptionJob


def record(kind, **patch):
    values = json.loads(Path('tests/fixtures/contracts-v1.json').read_text())
    return decode({**next(item for item in values if item['kind'] == kind), **patch})


class Worker:
    def __init__(self):
        self.result = None
        self.input = None
        self.cleaned = True

    def start(self, data):
        self.input = data

    def poll(self):
        return self.result

    def cancel(self):
        return ProcessResult('canceled' if self.cleaned else 'uncertain', b'', 'process.canceled')


class Device:
    def __init__(self):
        self.chunks = []
        self.started = False
        self.stopped = False
        self.cleaned = True

    def start(self, source):
        self.started = True

    def poll(self):
        result, self.chunks = self.chunks, []
        return result

    def cancel(self):
        self.stopped = True
        return self.cleaned


class CoordinatorTests(unittest.TestCase):
    def make(self, risk='safe', observer=None, device=None):
        self.owner = SessionOwner()
        self.journal = MemoryJournal()
        self.calls, self.spoken, self.workers = [], [], []
        self.now = 0.0
        self.state = VoiceState(record('command').context, 'focus-epoch-1', 'external-turn')
        self.plane = ControlPlane([record('capability', risk=risk)], record('policy'),
                                  lambda command: self.calls.append(command) or Outcome('success'),
                                  self.journal, profile=record('profile', voice_enabled=True))
        self.router = VoiceRouter(self.plane,
            [Action('menu.open', 1, {'name': 'main'}, ('show menu',), 'Open menu')],
            lambda: self.state, self.spoken.append)
        def factory():
            worker = Worker()
            self.workers.append(worker)
            return TranscriptionJob(worker_factory=lambda: worker)
        return Coordinator(self.owner, CommandCapture(), self.router, factory,
                           observer or self.journal.append,
                           device_factory=(lambda: device) if device else None,
                           source='approved-test-source' if device else None,
                           clock=lambda: self.now)

    def finish_capture(self, coordinator, generation):
        coordinator.feed(generation, Frame(b'\x00\x10' * 320, True), sequence=0)
        for sequence in range(1, 36):
            coordinator.feed(generation, Frame(bytes(640), False), sequence=sequence)

    def answer(self, coordinator, text=b'show menu'):
        self.workers[-1].result = ProcessResult('success', text, 'process.ok')
        return coordinator.poll()

    def test_one_activation_dispatches_once_with_correlated_private_observations(self):
        coordinator = self.make()
        generation = coordinator.activate()
        with self.assertRaises(BusyError):
            coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.assertEqual(coordinator.phase, 'processing')
        self.assertEqual(self.answer(coordinator).status, 'success')
        self.assertIsNone(coordinator.poll())
        self.assertIsNone(coordinator.transcribed(TranscriptResult(generation, 'success', 'show menu', 'ok')))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(coordinator.phase, 'idle')
        events = [event for _, event in self.journal.read()]
        self.assertEqual([e.phase for e in events if isinstance(e, VoiceObservation)],
                         ['capture.started', 'capture.stopped', 'transcription.started', 'transcription.finished'])
        self.assertEqual(len({e.correlation_id for e in events}), 1)
        self.assertEqual(events[0].session_id, self.owner.session_id)
        self.assertEqual(events[0].activation_id, coordinator.activation_id)
        self.assertEqual(len([e for e in events if isinstance(e, Event)]), 2)
        self.assertNotIn('show menu', json.dumps([encode(e) for e in events]))
        self.assertEqual(self.spoken, [])

    def test_repeated_turns_use_fresh_single_use_jobs_and_ids(self):
        coordinator = self.make()
        ids = []
        for _ in range(2):
            generation = coordinator.activate()
            ids.append((generation, coordinator.activation_id, coordinator.correlation_id))
            self.finish_capture(coordinator, generation)
            self.assertEqual(self.answer(coordinator).status, 'success')
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(len(self.workers), 2)
        self.assertEqual(len(self.calls), 2)

    def test_cancel_during_processing_discards_late_result_and_allows_dictation(self):
        coordinator = self.make()
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        coordinator.cancel()
        self.assertIsNone(coordinator.transcribed(TranscriptResult(generation, 'success', 'show menu', 'ok')))
        self.assertEqual(self.calls, [])
        self.assertGreater(self.owner.begin('dictation'), generation)

    def test_failed_cleanup_latches_owner_and_prevents_dispatch_or_new_capture(self):
        coordinator = self.make()
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.workers[-1].cleaned = False
        coordinator.cancel()
        self.assertEqual(coordinator.phase, 'faulted')
        with self.assertRaises(FaultedError):
            self.owner.begin('dictation')
        with self.assertRaises(BusyError):
            coordinator.activate()
        self.assertEqual(self.journal.read()[-1][1].phase, 'owner.faulted')
        self.assertEqual(self.calls, [])

    def test_journal_failures_at_each_transition_fail_closed_and_clean_resources(self):
        for phase in ('capture.started', 'capture.stopped', 'transcription.started', 'transcription.finished'):
            with self.subTest(phase=phase):
                def observe(event):
                    if event.phase == phase:
                        raise OSError('private failure text')
                    self.journal.append(event)
                coordinator = self.make(observer=observe)
                generation = coordinator.activate()
                self.finish_capture(coordinator, generation)
                if self.workers:
                    self.answer(coordinator)
                self.assertEqual(coordinator.phase, 'idle')
                self.assertEqual(coordinator.code, 'journal.unavailable')
                self.assertEqual(self.calls, [])
                self.assertEqual(self.spoken, [])
                self.owner.begin('dictation')

    def test_mute_after_each_persistence_transition_prevents_transcription_or_dispatch(self):
        for phase in ('capture.started', 'capture.stopped', 'transcription.started', 'transcription.finished'):
            with self.subTest(phase=phase):
                def observe(event):
                    self.journal.append(event)
                    if event.phase == phase:
                        self.state = VoiceState(self.state.context, self.state.key, self.state.activation_id, muted=True)
                coordinator = self.make(observer=observe)
                generation = coordinator.activate()
                self.finish_capture(coordinator, generation)
                if self.workers:
                    self.answer(coordinator)
                self.assertEqual(coordinator.phase, 'idle')
                self.assertEqual(self.calls, [])
                self.assertEqual(self.spoken, [])
                self.assertEqual(coordinator.code, 'context.stale')

    def test_context_epoch_away_and_back_is_not_the_original_context(self):
        coordinator = self.make()
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.state = VoiceState(self.state.context, 'focus-epoch-3', 'external-turn')
        self.assertIsNone(self.answer(coordinator))
        self.assertEqual(self.calls, [])
        self.assertEqual(coordinator.code, 'context.stale')

    def test_generation_change_during_execution_intent_blocks_vm_executor(self):
        coordinator = self.make()
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        append = self.journal.append
        def change(event):
            result = append(event)
            if isinstance(event, Event) and event.event_type == 'command.started':
                self.owner.cancel()
            return result
        self.journal.append = change
        self.assertEqual(self.answer(coordinator).status, 'blocked')
        self.assertEqual(self.calls, [])

    def test_duplicate_sequence_not_counted_and_gap_or_malformed_frame_discards(self):
        coordinator = self.make()
        generation = coordinator.activate()
        coordinator.feed(generation, Frame(bytes(640), True), sequence=0)
        for _ in range(1000):
            coordinator.feed(generation, Frame(bytes(640), False), sequence=0)
        self.assertEqual(coordinator.phase, 'capturing')
        coordinator.feed(generation, Frame(bytes(640), True), sequence=2)
        self.assertEqual(coordinator.phase, 'idle')
        self.assertEqual(self.workers, [])
        for frame in (None, Frame(bytes(32), True)):
            generation = coordinator.activate()
            coordinator.feed(generation, frame)
            self.assertEqual(coordinator.phase, 'idle')
        self.assertEqual(self.calls, [])

    def test_initial_silence_never_starts_transcription(self):
        coordinator = self.make()
        generation = coordinator.activate()
        for _ in range(150):
            coordinator.feed(generation, Frame(bytes(640), False))
        self.assertEqual(coordinator.phase, 'idle')
        self.assertEqual(self.workers, [])
        self.assertEqual(self.calls, [])

    def test_injected_device_is_stopped_before_transcription_and_fragmentation_is_framed(self):
        device = Device()
        coordinator = self.make(device=device)
        coordinator.activate()
        self.assertTrue(device.started)
        device.chunks = [b'\x00\x10' * 319]
        coordinator.poll()
        device.chunks = [b'\x00\x10']
        coordinator.poll()
        for _ in range(35):
            device.chunks = [bytes(640)]
            coordinator.poll()
        self.assertTrue(device.stopped)
        self.assertEqual(coordinator.phase, 'processing')
        self.assertEqual(self.answer(coordinator).status, 'success')

    def test_device_cleanup_failure_or_deadline_never_starts_transcription(self):
        device = Device()
        coordinator = self.make(device=device)
        generation = coordinator.activate()
        device.cleaned = False
        self.finish_capture(coordinator, generation)
        self.assertEqual(coordinator.phase, 'faulted')
        self.assertEqual(self.workers, [])
        device = Device()
        coordinator = self.make(device=device)
        coordinator.activate()
        self.now = 15.0
        coordinator.poll()
        self.assertTrue(device.stopped)
        self.assertEqual(coordinator.phase, 'idle')
        self.assertEqual(self.workers, [])

    def test_unknown_and_negative_input_never_executes(self):
        for phrase in (b'purple garden', b'do not show menu', b'cancel'):
            with self.subTest(phrase=phrase):
                coordinator = self.make()
                generation = coordinator.activate()
                self.finish_capture(coordinator, generation)
                self.answer(coordinator, phrase)
                self.assertEqual(self.calls, [])

    def test_panel_confirmation_is_single_use_and_cancel_revokes_it(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                coordinator = self.make(risk='confirm')
                generation = coordinator.activate()
                self.finish_capture(coordinator, generation)
                reply = self.answer(coordinator)
                self.assertEqual(reply.status, 'preview')
                self.assertEqual(self.calls, [])
                if cancel:
                    coordinator.cancel()
                confirmed = coordinator.confirm(reply.token, 'panel', True)
                self.assertEqual(confirmed.status, 'blocked' if cancel else 'success')
                self.assertEqual(len(self.calls), 0 if cancel else 1)
                self.assertEqual(coordinator.confirm(reply.token, 'panel', True).status, 'blocked')

    def test_voice_confirmation_requires_new_activation_and_preserves_command_correlation(self):
        coordinator = self.make(risk='confirm')
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        preview = self.answer(coordinator)
        original = coordinator.correlation_id
        self.assertEqual(coordinator.confirm(preview.token, 'voice', 'yes').status, 'blocked')
        generation = coordinator.activate(confirmation_token=preview.token)
        self.finish_capture(coordinator, generation)
        self.assertEqual(self.answer(coordinator, b'yes').status, 'success')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].correlation_id, original)

    def test_direct_feed_and_result_cannot_bypass_wall_deadlines(self):
        coordinator = self.make()
        generation = coordinator.activate()
        self.now = 15.0
        self.finish_capture(coordinator, generation)
        self.assertEqual(coordinator.phase, 'idle')
        self.assertEqual(self.workers, [])
        coordinator = self.make()
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.workers[-1].result = ProcessResult('success', b'show menu', 'process.ok')
        result = coordinator._job.poll()
        self.now = 30.0
        self.assertIsNone(coordinator.transcribed(result))
        self.assertEqual(self.calls, [])

    def test_cancel_observer_cannot_reenter_cleanup_recursively(self):
        observed = []
        def observe(event):
            observed.append(event.phase)
            self.journal.append(event)
            if event.phase == 'capture.canceled':
                coordinator.cancel()
        coordinator = self.make(observer=observe)
        coordinator.activate()
        coordinator.cancel()
        self.assertEqual(observed, ['capture.started', 'capture.canceled'])
        self.assertEqual(coordinator.phase, 'idle')

    def test_disabled_voice_profile_remains_blocked(self):
        coordinator = self.make()
        self.plane._profile = record('profile', voice_enabled=False)
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.assertEqual(self.answer(coordinator).code, 'voice.disabled')
        self.assertEqual(self.calls, [])

    def test_job_start_exception_is_sanitized_and_uncertain_cleanup_faults(self):
        class BrokenJob:
            cleanup_proven = False
            def start(self, pcm, generation):
                raise OSError('private provider details')
            def cancel(self):
                pass
        coordinator = self.make()
        coordinator._factory = BrokenJob
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.assertEqual(coordinator.phase, 'faulted')
        self.assertEqual(self.calls, [])
        self.assertNotIn('private provider', json.dumps([encode(e) for _, e in self.journal.read()]))

    def test_cancel_invalidates_while_persistence_waits_then_releases_after_cleanup(self):
        entered, release = threading.Event(), threading.Event()
        def observe(event):
            self.journal.append(event)
            if event.phase == 'transcription.finished':
                entered.set()
                if not release.wait(2):
                    raise TimeoutError()
        coordinator = self.make(observer=observe)
        generation = coordinator.activate()
        self.finish_capture(coordinator, generation)
        self.workers[-1].result = ProcessResult('success', b'show menu', 'process.ok')
        polling = threading.Thread(target=coordinator.poll)
        polling.start()
        self.assertTrue(entered.wait(2))
        canceling = threading.Thread(target=coordinator.cancel)
        canceling.start()
        self.assertTrue(coordinator._cancel_requested.wait(2))
        self.assertFalse(self.owner.accepts(generation))
        try:
            with self.assertRaises(BusyError):
                self.owner.begin('dictation')
        finally:
            release.set()
            polling.join(2)
            canceling.join(2)
        self.assertFalse(polling.is_alive())
        self.assertFalse(canceling.is_alive())
        self.assertEqual(self.calls, [])
        self.owner.begin('dictation')
