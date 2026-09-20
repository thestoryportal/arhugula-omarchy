"""Owned in-memory audio boundary; never synthesizes or plays real speech."""
from dataclasses import replace
import threading
import unittest

from runtime.voice.process import ProcessResult
from runtime.voice.router import VoiceState
from runtime.voice.speech import SpeechQueue


class AudioBackend:
    def __init__(self):
        self.pending = None
        self.played = []
        self.calls = []
        self.on_start = lambda: None
        self.on_cancel = lambda: None
        self.clean = True

    def start(self, prompt):
        self.calls.append('start')
        self.pending = prompt
        self.on_start()

    def cancel(self):
        self.calls.append('cancel')
        self.on_cancel()
        if self.clean:
            self.pending = None
        return ProcessResult('canceled' if self.clean else 'uncertain', b'',
                             'process.canceled' if self.clean else 'process.cleanup-unproven')

    def finish_synthesis(self):
        if self.pending is not None:
            self.played.append(self.pending)
            self.pending = None


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.state = VoiceState({'profile_id': 'p'}, 'epoch-1', 'turn-1')
        self.backend = AudioBackend()
        self.queue = SpeechQueue(self.backend, lambda: self.state)

    def test_muted_wrong_mode_stale_and_arbitrary_prompts_never_start(self):
        for patch, prompt, activation in [
            ({'muted': True}, 'Please repeat the command.', 'turn-1'),
            ({'mode': 'dictation'}, 'Please repeat the command.', 'turn-1'),
            ({}, 'Please repeat the command.', 'old-turn'),
            ({}, 'private arbitrary model text', 'turn-1'),
        ]:
            with self.subTest(patch=patch, activation=activation):
                self.state = VoiceState({'profile_id': 'p'}, 'epoch-1', 'turn-1', **patch)
                self.assertFalse(self.queue.say(prompt, activation))
                self.assertIsNone(self.backend.pending)

    def test_current_prompt_is_canceled_before_delayed_synthesis_can_play(self):
        self.assertTrue(self.queue.say('Please repeat the command.', 'turn-1'))
        self.assertFalse(self.queue.cleanup_proven)
        self.queue.cancel()
        self.backend.finish_synthesis()
        self.assertEqual(self.backend.played, [])
        self.assertTrue(self.queue.cleanup_proven)

    def test_replacement_cancels_previous_work_before_start(self):
        self.queue.say('Please repeat the command.', 'turn-1')
        self.assertTrue(self.queue.say('Please confirm in the voice panel.', 'turn-1'))
        self.assertEqual(self.backend.calls, ['start', 'cancel', 'start'])

    def test_every_state_dimension_invalidates_owned_speech(self):
        for patch in ({'context': {'profile_id': 'q'}}, {'key': 'epoch-2'},
                      {'activation_id': 'turn-2'}, {'muted': True}, {'mode': 'dictation'}):
            with self.subTest(patch=patch):
                self.setUp()
                self.queue.say('Please repeat the command.', 'turn-1')
                self.state = replace(self.state, **patch)
                self.queue.poll()
                self.backend.finish_synthesis()
                self.assertEqual(self.backend.played, [])
                self.assertTrue(self.queue.cleanup_proven)

    def test_mutating_the_original_context_does_not_mutate_snapshot(self):
        self.queue.say('Please repeat the command.', 'turn-1')
        self.state.context['profile_id'] = 'changed'
        self.queue.poll()
        self.assertIsNone(self.backend.pending)

    def test_cancel_reentered_from_state_preflight_is_not_erased(self):
        def state():
            self.queue.cancel()
            return self.state
        self.queue = SpeechQueue(self.backend, state)
        self.assertFalse(self.queue.say('Please repeat the command.', 'turn-1'))
        self.assertEqual(self.backend.calls, [])

    def test_cancel_during_start_cleans_even_late_backend_creation(self):
        def starting():
            self.queue.cancel()
            self.backend.pending = 'late result'
        self.backend.on_start = starting
        self.assertFalse(self.queue.say('Please repeat the command.', 'turn-1'))
        self.backend.finish_synthesis()
        self.assertEqual(self.backend.played, [])

    def test_failed_cleanup_latches_and_never_admits_another_prompt(self):
        self.queue.say('Please repeat the command.', 'turn-1')
        self.backend.clean = False
        self.queue.cancel()
        self.backend.clean = True
        self.assertFalse(self.queue.say('Please repeat the command.', 'turn-1'))
        self.assertFalse(self.queue.cleanup_proven)
        self.assertEqual(self.queue.code, 'speech.cleanup-unproven')

    def test_backend_and_state_exception_details_are_not_exposed(self):
        def fail(*args):
            raise RuntimeError('private prompt or provider diagnostic')
        self.backend.on_start = fail
        self.assertFalse(self.queue.say('Please repeat the command.', 'turn-1'))
        self.assertEqual(self.queue.code, 'speech.unavailable')
        self.assertTrue(self.queue.cleanup_proven)
        self.queue = SpeechQueue(self.backend, fail)
        self.assertFalse(self.queue.say('Please repeat the command.', 'turn-1'))
        self.assertEqual(self.queue.code, 'speech.state-unavailable')

    def test_concurrent_cancel_invalidates_waiting_start_before_return(self):
        entered, resume = threading.Event(), threading.Event()
        self.backend.on_start = lambda: (entered.set(), resume.wait(2))
        answers = []
        worker = threading.Thread(target=lambda: answers.append(self.queue.say('Please repeat the command.', 'turn-1')))
        worker.start()
        self.assertTrue(entered.wait(2))
        canceler = threading.Thread(target=self.queue.cancel)
        canceler.start()
        resume.set()
        worker.join(2)
        canceler.join(2)
        self.assertFalse(worker.is_alive() or canceler.is_alive())
        self.assertTrue(self.queue.cleanup_proven)
        self.assertIsNone(self.backend.pending)

    def test_reentrant_cancel_backend_does_not_recurse(self):
        self.queue.say('Please repeat the command.', 'turn-1')
        self.backend.on_cancel = self.queue.cancel
        self.queue.cancel()
        self.assertTrue(self.queue.cleanup_proven)
        self.assertEqual(self.backend.calls, ['start', 'cancel'])
