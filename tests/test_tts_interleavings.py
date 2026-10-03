"""Cancellation and resource proof at controlled synchronous callback boundaries."""
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from runtime.voice.session import FaultedError
from runtime.voice.tts import PlaybackState
from runtime.voice.tts_records import Code, Completion, Duck, Phase
from tests.tts_fakes import Rig


def fail():
    raise RuntimeError('private backend detail')


class ObservedLock:
    """Test scheduler: observe a canceler reaching a held real transition lock."""
    def __init__(self, lock, waiting):
        self.lock, self.waiting = lock, waiting

    def __enter__(self):
        if threading.current_thread().name == 'tts-test-canceler':
            self.waiting.set()
        self.lock.acquire()
        return self

    def __exit__(self, *_):
        self.lock.release()


class TtsInterleavingTests(unittest.TestCase):
    def test_reentrant_cancel_at_each_boundary_never_publishes_success(self):
        for boundary in ('snapshot', 'host.begin', 'host.poll', 'host.cancel',
                         'mix.factory', 'mix.apply', 'player.factory', 'player.start',
                         'player.poll', 'player.cancel', 'mix.restore'):
            with self.subTest(boundary=boundary):
                rig = Rig(mix=Duck(500))
                rig.hooks[boundary] = rig.output.cancel
                rig.output.start(rig.utterance())
                result = rig.output.poll()
                if result is None:
                    rig.player.state = PlaybackState.COMPLETE
                    result = rig.output.poll()
                self.assertIsNotNone(result)
                self.assertEqual(result.code, Code.CANCELED)
                self.assertTrue(rig.output.cleanup_proven)
                self.assertTrue(rig.owner.accepts(rig.generation))
                self.assertEqual(rig.media['gain'], 900)
                self.assertLessEqual(rig.player.cancels, 1)
                self.assertLessEqual(rig.mix.restores, 1)
                self.assertIsNone(rig.output.poll())

    def test_late_allocation_after_reentrant_cancel_is_still_cleaned(self):
        for boundary, cleanup in (('mix.factory', 'mix.restore'),
                                  ('mix.apply', 'mix.restore'),
                                  ('player.factory', 'player.cancel'),
                                  ('player.start', 'player.cancel'),
                                  ('player.poll', 'player.cancel')):
            with self.subTest(boundary=boundary):
                rig, live = Rig(), []
                def allocate_late():
                    rig.output.cancel()
                    live.append('allocated-after-cancel')
                rig.hooks[boundary] = allocate_late
                rig.hooks[cleanup] = live.clear
                rig.output.start(rig.utterance())
                result = rig.output.poll()
                if result is None:
                    result = rig.output.poll()
                self.assertEqual(result.code, Code.CANCELED)
                self.assertEqual(live, [])
                self.assertTrue(rig.output.cleanup_proven)

    def test_unknown_factory_outcome_faults_shared_admission(self):
        for boundary in ('mix.factory', 'player.factory'):
            with self.subTest(boundary=boundary):
                rig = Rig()
                rig.hooks[boundary] = fail
                rig.output.start(rig.utterance())
                self.assertEqual(rig.output.poll().code, Code.CLEANUP)
                self.assertEqual(rig.output.notice.phase, Phase.FAULTED)
                with self.assertRaises(FaultedError):
                    rig.owner.begin('command')
                self.assertFalse(rig.output.start(rig.utterance('again')))
                if boundary == 'player.factory':
                    self.assertEqual(rig.mix.restores, 1)

    def test_malformed_returned_handle_faults_without_skipping_other_cleanup(self):
        rig = Rig()
        rig.hooks['player.factory'] = lambda: setattr(rig, 'player', object())
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.CLEANUP)
        self.assertEqual(rig.mix.restores, 1)
        self.assertFalse(rig.output.cleanup_proven)

    def test_partial_effect_exceptions_are_cleaned_and_content_free(self):
        for boundary in ('mix.apply', 'player.start', 'player.poll'):
            with self.subTest(boundary=boundary):
                rig = Rig(mix=Duck(500))
                rig.hooks[boundary] = fail
                rig.output.start(rig.utterance('private utterance'))
                result = rig.output.poll()
                if result is None:
                    result = rig.output.poll()
                self.assertEqual(result.code, Code.UNAVAILABLE)
                self.assertEqual(rig.media['gain'], 900)
                self.assertTrue(rig.output.cleanup_proven)
                self.assertNotIn('private', repr((result, rig.output.notice)))

    def test_all_three_cleanup_proofs_require_literal_true(self):
        for resource in ('host', 'player', 'mix'):
            for proof in (False, 1, None, 'raises'):
                with self.subTest(resource=resource, proof=proof):
                    rig = Rig(fallback=True)
                    handle = {'host': rig.host_job, 'player': rig.player, 'mix': rig.mix}[resource]
                    method = 'restore' if resource == 'mix' else 'cancel'
                    if proof == 'raises':
                        rig.hooks[resource + '.' + method] = fail
                    else:
                        setattr(handle, 'restore_result' if resource == 'mix' else 'clean', proof)
                    rig.output.start(rig.utterance())
                    result = rig.output.poll()
                    if result is None:
                        rig.player.state = PlaybackState.COMPLETE
                        result = rig.output.poll()
                    self.assertEqual(result.code, Code.CLEANUP)
                    self.assertFalse(rig.output.cleanup_proven)
                    with self.assertRaises(FaultedError):
                        rig.owner.begin('dictation')
                    self.assertEqual(rig.local_requests, [])
                    counts = (rig.host_job.cancels, rig.player.cancels, rig.mix.restores)
                    rig.output.cancel()
                    rig.output.cancel()
                    self.assertEqual(counts, (rig.host_job.cancels, rig.player.cancels, rig.mix.restores))
                    if resource == 'host':
                        self.assertNotIn('mix.factory', rig.events)
                    else:
                        self.assertEqual(rig.mix.restores, 1)

    def test_nested_start_poll_refused_but_notice_reads_are_inert(self):
        rig = Rig()
        def nested():
            count = len(rig.events)
            self.assertFalse(rig.output.start(rig.utterance('nested')))
            self.assertIsNone(rig.output.poll())
            self.assertIsNotNone(rig.output.notice)
            self.assertFalse(rig.output.cleanup_proven)
            self.assertEqual(len(rig.events), count)
        for event in ('snapshot', 'host.begin', 'mix.apply', 'player.start',
                      'player.poll', 'player.cancel', 'mix.restore'):
            rig.hooks[event] = nested
        rig.output.start(rig.utterance())
        rig.output.poll()
        rig.player.state = PlaybackState.COMPLETE
        self.assertEqual(rig.output.poll().code, Code.PLAYED)
        self.assertEqual(len(rig.host_requests), 1)

    def test_configuration_drift_after_gateway_returns_prevents_mix(self):
        rig = Rig()
        changed = []
        def disable_after_cleanup():
            if rig.host_job.cancels and not changed:
                changed.append(True)
                rig.configuration.disable()
        rig.hooks['snapshot'] = disable_after_cleanup
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.STALE)
        self.assertNotIn('mix.factory', rig.events)
        self.assertTrue(rig.output.cleanup_proven)

    def test_gateway_internal_fallback_can_precede_policy_resample_but_not_playback(self):
        rig = Rig(fallback=True)
        rig.host_error('unavailable')
        rig.hooks['host.cancel'] = lambda: setattr(rig, 'snapshot', replace(rig.snapshot, muted=True))
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.STALE)
        self.assertEqual(len(rig.local_requests), 1)  # Accepted offline sampling limit.
        self.assertEqual(rig.local_job.cancels, 1)
        self.assertNotIn('mix.factory', rig.events)
        self.assertTrue(rig.output.cleanup_proven)

    def test_policy_drift_after_mix_apply_restores_before_any_player(self):
        rig = Rig(mix=Duck(500))
        rig.hooks['mix.apply'] = lambda: rig.next_turn()
        rig.output.start(rig.utterance())
        self.assertEqual(rig.output.poll().code, Code.STALE)
        self.assertNotIn('player.factory', rig.events)
        self.assertEqual(rig.media['gain'], 900)

    def test_late_fault_and_cancel_never_alter_successor_generation(self):
        rig = Rig()
        rig.output.start(rig.utterance())
        rig.output.poll()
        rig.owner.release(rig.generation, cleaned=True)  # Unsupported early caller release.
        successor = rig.owner.begin('dictation')
        rig.mix.restore_result = False
        rig.output.cancel()
        self.assertEqual(rig.output.poll().code, Code.CLEANUP)
        self.assertTrue(rig.owner.accepts(successor))
        rig.output.cancel()
        self.assertTrue(rig.owner.accepts(successor))

    def test_completion_construction_cancel_wins_before_publication(self):
        rig = Rig()
        rig.output.start(rig.utterance())
        rig.output.poll()
        rig.player.state = PlaybackState.COMPLETE
        def interrupted(*args):
            value = Completion(*args)
            rig.output.cancel()
            return value
        with patch('runtime.voice.tts.Completion', side_effect=interrupted):
            self.assertEqual(rig.output.poll().code, Code.CANCELED)
        self.assertTrue(rig.output.cleanup_proven)

    def test_cross_thread_cancel_is_visible_before_callback_unwinds(self):
        rig = Rig()
        entered, finish, waiting = threading.Event(), threading.Event(), threading.Event()
        rig.output._lock = ObservedLock(rig.output._lock, waiting)
        results = []
        def block():
            entered.set()
            if not finish.wait(3):
                raise RuntimeError('test callback deadline')
        rig.hooks['host.poll'] = block
        rig.output.start(rig.utterance())
        worker = threading.Thread(target=lambda: results.append(rig.output.poll()))
        canceler = threading.Thread(target=rig.output.cancel, name='tts-test-canceler')
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            canceler.start()
            self.assertTrue(waiting.wait(3))
            self.assertEqual(rig.host_job.cancels, 0)
        finally:
            finish.set()
            worker.join(3)
            if canceler.ident is not None:
                canceler.join(3)
        self.assertFalse(worker.is_alive() or canceler.is_alive())
        self.assertEqual([r.code for r in results], [Code.CANCELED])
        self.assertNotIn('player.start', rig.events)
        self.assertTrue(rig.owner.accepts(rig.generation))
