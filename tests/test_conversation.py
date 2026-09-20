from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

from runtime.voice.conversation import Conversation
from runtime.voice.conversation_records import (
    Clarification, Code, Context, ContextItem, ContextState, Display, Entry, Response,
)
from runtime.voice.session import BusyError, FaultedError, SessionOwner
from tests.test_conversation_records import fixture


class Job:
    def __init__(self):
        self.request = self.result = None
        self.cleanup_proven = False
        self.on_start = self.on_poll = self.on_cancel = lambda: None
        self.clean = True
        self.cancels = 0

    def start(self, request):
        self.request = request
        self.on_start()

    def poll(self):
        self.on_poll()
        return self.result

    def cancel(self):
        self.cancels += 1
        self.on_cancel()
        self.cleanup_proven = self.clean


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = fixture()
        self.owner = SessionOwner()
        self.jobs = []
        self.make_job = Job
        self.conversation = Conversation(self.owner, lambda: self.snapshot, self.factory)

    def factory(self):
        job = self.make_job()
        self.jobs.append(job)
        return job

    def enter(self):
        self.assertTrue(self.conversation.enter(Entry.PANEL))

    def answer(self, prompt='hello', answer='answer'):
        current = self.conversation.submit(prompt)
        self.assertIsNotNone(current)
        self.jobs[-1].result = Response(current, answer)
        return self.conversation.poll()

    def conflict(self):
        self.snapshot = replace(self.snapshot, context=Context(
            2, ContextState.CONFLICTING,
            (ContextItem('archive:one', 'tea'), ContextItem('archive:two', 'coffee')),
            'conflict-1'))

    def test_continuity_retains_history_and_one_shared_lease(self):
        self.enter()
        first = self.answer()
        self.assertEqual(first.text, 'answer')
        self.assertEqual(self.conversation.notice.state, Display.READY)
        second = self.conversation.submit('continue')
        self.assertEqual(first.token.session_id, second.session_id)
        self.assertEqual(first.token.generation, second.generation)
        self.assertEqual(second.turn, 2)
        self.assertEqual(self.jobs[-1].request.history[0].response, 'answer')
        for mode in ('command', 'dictation'):
            with self.assertRaises(BusyError):
                self.owner.begin(mode)

    def test_entry_channels_are_explicit_and_default_free(self):
        for channel in Entry:
            with self.subTest(channel=channel):
                self.assertTrue(self.conversation.enter(channel))
                self.conversation.end()
        self.snapshot = replace(self.snapshot, policy=replace(
            self.snapshot.policy, entries=frozenset({Entry.VOICE})))
        self.assertFalse(self.conversation.enter(Entry.KEYBOARD))
        self.assertEqual(self.conversation.notice.code, Code.DENIED)
        with self.assertRaises(ValueError):
            self.conversation.enter('voice')

    def test_disabled_missing_mismatched_policy_and_collision_deny_entry(self):
        original = self.snapshot
        for snapshot in (
                replace(original, policy=None),
                replace(original, profile=replace(original.profile, enabled=False)),
                replace(original, profile=replace(original.profile, voice_enabled=False)),
                replace(original, policy=replace(original.policy, profile_id='foreign')),
                replace(original, policy=replace(original.policy, policy_id='foreign')),
                replace(original, setup=replace(original.setup, occupied=frozenset({'F9'}))),
                replace(original, setup=replace(original.setup, reserved=frozenset({'F9'})))):
            with self.subTest(snapshot=snapshot):
                self.setUp()
                self.snapshot = snapshot
                self.assertFalse(self.conversation.enter(Entry.PANEL))
                lease = self.owner.begin('command')
                self.owner.release(lease, True)
        self.assertEqual(self.jobs, [])

    def test_unavailable_context_refuses_without_fabricating_empty_memory(self):
        self.snapshot = replace(self.snapshot, context=Context(2, ContextState.UNAVAILABLE, ()))
        self.assertFalse(self.conversation.enter(Entry.PANEL))
        self.assertEqual(self.conversation.notice.code, Code.UNAVAILABLE)
        self.assertEqual(self.jobs, [])

    def test_exact_spoken_exit_and_configured_key(self):
        self.enter()
        self.answer('please end conversation now')
        self.assertFalse(self.conversation.exit_key('End'))
        self.assertEqual(self.conversation.notice.state, Display.READY)
        self.assertIsNone(self.conversation.submit('end conversation'))
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.conversation.history, ())
        self.enter()
        self.assertTrue(self.conversation.exit_key('F9'))
        self.assertEqual(self.conversation.notice.code, Code.ENDED)

    def test_exit_interrupts_processing_and_clarification(self):
        self.enter()
        self.conversation.submit('pending')
        self.conversation.submit('end conversation')
        self.assertTrue(self.jobs[-1].cleanup_proven)
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
        self.conflict()
        self.enter()
        self.conversation.submit('prefer tea')
        self.conversation.exit_key('F9')
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)

    def test_turn_cancel_preserves_history_with_new_generation(self):
        self.enter()
        first = self.answer()
        old = self.conversation.submit('interrupt me')
        self.conversation.cancel_turn()
        self.assertFalse(self.owner.accepts(old.generation))
        self.assertEqual(self.conversation.notice.state, Display.READY)
        current = self.conversation.submit('continue')
        self.assertEqual(current.session_id, first.token.session_id)
        self.assertGreater(current.generation, old.generation)
        self.assertEqual(self.jobs[-1].request.history[0].text, 'hello')

    def test_end_handoff_and_reentry_change_session_identity(self):
        self.enter()
        first = self.answer()
        self.conversation.handoff()
        self.assertEqual(self.conversation.notice.code, Code.HANDOFF)
        self.assertEqual(self.conversation.history, ())
        successor = self.owner.begin('dictation')
        self.conversation.end()
        self.conversation.cancel_turn()
        self.assertTrue(self.owner.accepts(successor))
        self.owner.release(successor, True)
        self.enter()
        self.assertNotEqual(self.conversation.submit('new').session_id, first.token.session_id)

    def test_shared_owner_denies_conversation_entry_while_occupied(self):
        for mode in ('command', 'dictation'):
            lease = self.owner.begin(mode)
            with self.assertRaises(BusyError):
                self.conversation.enter(Entry.PANEL)
            self.assertTrue(self.owner.accepts(lease))
            self.owner.release(lease, True)
        self.enter()

    def test_conflict_requires_exact_current_clarification_and_keeps_provenance(self):
        self.conflict()
        original = self.snapshot.context
        self.enter()
        current = self.conversation.submit('I prefer tea')
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.conversation.notice.state, Display.CLARIFYING)
        for clarification in (Clarification(current, 'foreign-conflict', True),
                              Clarification(replace(current, turn=99), 'conflict-1', True),
                              Clarification(replace(current, session_id='foreign'), 'conflict-1', True)):
            self.assertFalse(self.conversation.clarify(clarification))
        self.assertEqual(self.jobs, [])
        confirmation = Clarification(current, 'conflict-1', True)
        self.assertTrue(self.conversation.clarify(confirmation))
        self.assertFalse(self.conversation.clarify(confirmation))
        self.jobs[-1].result = Response(current, 'tea acknowledged')
        self.assertEqual(self.conversation.poll().text, 'tea acknowledged')
        self.assertEqual(self.conversation.history[0].resolved_conflict, 'conflict-1')
        self.assertEqual(self.snapshot.context, original)
        self.assertEqual(self.jobs[-1].request.context, original)
        self.assertEqual(self.jobs[-1].request.resolved_conflict, 'conflict-1')

    def test_rejected_or_canceled_conflict_cannot_replay(self):
        self.conflict()
        self.enter()
        current = self.conversation.submit('tea')
        self.assertTrue(self.conversation.clarify(Clarification(current, 'conflict-1', False)))
        self.assertEqual(self.conversation.notice.state, Display.READY)
        self.conversation.submit('coffee')
        self.assertFalse(self.conversation.clarify(Clarification(current, 'conflict-1', True)))
        self.conversation.cancel_turn()
        self.assertFalse(self.conversation.clarify(Clarification(current, 'conflict-1', True)))
        self.assertEqual(self.jobs, [])

    def test_foreign_conflict_rejection_cannot_resolve_current_turn(self):
        self.conflict()
        self.enter()
        current = self.conversation.submit('tea')
        self.assertFalse(self.conversation.clarify(Clarification(current, 'foreign', False)))
        self.assertEqual(self.conversation.notice.state, Display.CLARIFYING)
        self.assertEqual(self.conversation.pending, current)

    def test_stale_foreign_replayed_response_never_enters_history(self):
        for field, value in (('session_id', 'foreign'), ('turn', 99), ('generation', 99),
                             ('profile_id', 'foreign'), ('profile_revision', 99),
                             ('policy_revision', 99), ('context_revision', 99)):
            with self.subTest(field=field):
                self.setUp()
                self.enter()
                current = self.conversation.submit('hello')
                self.jobs[-1].result = Response(replace(current, **{field: value}), 'wrong')
                self.assertIsNone(self.conversation.poll())
                self.assertEqual(self.conversation.history, ())
                self.assertEqual(self.conversation.notice.code, Code.INVALID_RESULT)
        self.setUp()
        self.enter()
        first = self.answer()
        self.conversation.submit('continue')
        self.jobs[-1].result = first
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.code, Code.INVALID_RESULT)

    def test_profile_context_setup_or_policy_drift_ends_without_response(self):
        for transform in (
                lambda s: replace(s, revision=2),
                lambda s: replace(s, profile=replace(s.profile, enabled=False)),
                lambda s: replace(s, policy=None),
                lambda s: replace(s, policy=replace(s.policy, revision=2)),
                lambda s: replace(s, context=replace(s.context, revision=2)),
                lambda s: replace(s, setup=replace(s.setup, revision=2))):
            with self.subTest(transform=transform):
                self.setUp()
                self.enter()
                current = self.conversation.submit('hello')
                self.jobs[-1].result = Response(current, 'stale')
                self.snapshot = transform(self.snapshot)
                self.assertIsNone(self.conversation.poll())
                self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
                self.assertEqual(self.conversation.notice.code, Code.STALE)

    def test_conflict_drift_prevents_job_start(self):
        self.conflict()
        self.enter()
        current = self.conversation.submit('tea')
        self.snapshot = replace(self.snapshot, context=replace(self.snapshot.context, revision=3))
        self.assertFalse(self.conversation.clarify(Clarification(current, 'conflict-1', True)))
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.conversation.notice.code, Code.STALE)

    def test_turn_text_context_and_poll_limits_fail_explicitly(self):
        self.snapshot = replace(self.snapshot, policy=replace(
            self.snapshot.policy, limits=replace(self.snapshot.policy.limits, turns=1)))
        self.enter()
        self.answer()
        self.assertIsNone(self.conversation.submit('second'))
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)
        self.setUp()
        self.enter()
        with self.assertRaises(ValueError):
            self.conversation.submit('x' * 257)
        self.assertEqual(self.jobs, [])
        current = self.conversation.submit('hello')
        for _ in range(4):
            self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)
        self.assertFalse(self.owner.accepts(current.generation))
        self.setUp()
        self.snapshot = replace(self.snapshot, context=Context(
            1, ContextState.AVAILABLE, (ContextItem('archive:one', 'x' * 2049),)))
        self.assertFalse(self.conversation.enter(Entry.PANEL))
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)

    def test_history_and_response_share_explicit_context_budget(self):
        self.snapshot = replace(self.snapshot, policy=replace(self.snapshot.policy,
            limits=replace(self.snapshot.policy.limits, context_chars=24)))
        self.enter()
        self.answer('1234567890', '1234567890')
        self.assertIsNone(self.conversation.submit('12345'))
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)
        self.setUp()
        self.enter()
        current = self.conversation.submit('hi')
        self.jobs[-1].result = Response(current, 'x' * 257)
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)

    def test_pending_turn_rejects_reentry_and_notice_contains_no_content(self):
        self.enter()
        current = self.conversation.submit('private input')
        with self.assertRaises(BusyError):
            self.conversation.submit('another')
        with self.assertRaises(BusyError):
            self.conversation.enter(Entry.PANEL)
        self.assertEqual(self.conversation.pending, current)
        self.assertNotIn('private', repr(self.conversation.notice))
        self.assertEqual(self.conversation.notice.version, 1)

    def test_failed_or_unknown_cleanup_faults_all_admission(self):
        for clean in (False, None, 1):
            with self.subTest(clean=clean):
                self.setUp()
                self.enter()
                self.conversation.submit('hello')
                self.jobs[-1].clean = clean
                self.conversation.cancel_turn()
                self.assertEqual(self.conversation.notice.state, Display.FAULTED)
                for mode in ('command', 'dictation', 'conversation'):
                    with self.assertRaises(FaultedError):
                        self.owner.begin(mode)
                self.jobs[-1].clean = True
                self.conversation.end()
                self.assertEqual(self.conversation.notice.state, Display.FAULTED)

    def test_callback_cancellation_waits_for_construction_and_start_return(self):
        for boundary in ('factory', 'start', 'poll', 'cleanup'):
            with self.subTest(boundary=boundary):
                self.setUp()
                job = Job()
                def cancel_and_allocate():
                    self.conversation.cancel_turn()
                    self.assertEqual(job.cancels, 0)
                    job.cleanup_proven = False
                if boundary == 'factory':
                    def construct():
                        cancel_and_allocate()
                        return job
                    self.make_job = construct
                else:
                    self.make_job = lambda: job
                    if boundary == 'start':
                        job.on_start = cancel_and_allocate
                self.enter()
                current = self.conversation.submit('hello')
                if boundary in ('poll', 'cleanup'):
                    setattr(job, 'on_' + ('cancel' if boundary == 'cleanup' else 'poll'),
                            self.conversation.cancel_turn)
                    job.result = Response(current, 'must not publish')
                    self.assertIsNone(self.conversation.poll())
                else:
                    self.assertIsNone(current)
                self.assertEqual(self.conversation.notice.state, Display.READY)
                self.assertEqual(self.conversation.history, ())
                self.assertTrue(job.cleanup_proven)
                self.assertEqual(job.cancels, 1)
                self.assertIsNone(self.conversation.pending)

    def test_end_during_cancel_cleanup_overrides_turn_resume(self):
        self.enter()
        self.conversation.submit('pending')
        self.jobs[-1].on_cancel = self.conversation.end
        self.conversation.cancel_turn()
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
        self.assertEqual(self.conversation.notice.code, Code.ENDED)
        self.assertTrue(self.owner.accepts(self.owner.begin('command')))

    def test_supplier_cancellation_cannot_be_erased_by_entry_or_freshness(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                self.setUp()
                if existing:
                    self.enter()
                    current = self.conversation.submit('hello')
                    self.jobs[-1].result = Response(current, 'no')
                def sample():
                    self.conversation.end()
                    return self.snapshot
                self.conversation._snapshot_source = sample
                self.assertFalse(self.conversation.poll() if existing else
                                 self.conversation.enter(Entry.PANEL))
                self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
                self.assertEqual(self.conversation.history, ())
                self.assertTrue(self.owner.accepts(self.owner.begin('command')))

    def test_drift_during_job_start_poll_and_cleanup_suppresses_results(self):
        for boundary in ('start', 'poll', 'cancel'):
            with self.subTest(boundary=boundary):
                self.setUp()
                job = Job()
                def drift():
                    self.snapshot = replace(self.snapshot, revision=2)
                setattr(job, 'on_' + boundary, drift)
                self.make_job = lambda: job
                self.enter()
                current = self.conversation.submit('hello')
                if boundary != 'start':
                    job.result = Response(current, 'stale')
                    self.assertIsNone(self.conversation.poll())
                else:
                    self.assertIsNone(current)
                self.assertEqual(self.conversation.history, ())
                self.assertEqual(self.conversation.notice.code, Code.STALE)
                self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
                self.assertTrue(job.cleanup_proven)

    def test_callback_nested_mutations_are_busy_but_notice_and_cancel_work(self):
        self.enter()
        job = Job()
        self.make_job = lambda: job
        def reenter():
            self.assertEqual(self.conversation.notice.state, Display.PROCESSING)
            for operation in (lambda: self.conversation.enter(Entry.PANEL),
                              lambda: self.conversation.submit('nested'),
                              self.conversation.poll,
                              lambda: self.conversation.clarify(Clarification(
                                  self.conversation.pending, 'conflict', True))):
                with self.assertRaises(BusyError):
                    operation()
        job.on_start = job.on_poll = job.on_cancel = reenter
        current = self.conversation.submit('hello')
        job.result = Response(current, 'answer')
        self.assertEqual(self.conversation.poll().text, 'answer')

    def test_cross_thread_cancel_invalidates_before_waiting_for_callback(self):
        self.enter()
        entered, finish = threading.Event(), threading.Event()
        job = Job()
        self.make_job = lambda: job
        def blocked_start():
            entered.set()
            if not finish.wait(3):
                raise RuntimeError('test callback timed out')
        job.on_start = blocked_start
        results = []
        worker = threading.Thread(target=lambda: results.append(self.conversation.submit('hello')))
        worker.start()
        self.assertTrue(entered.wait(3))
        current = self.conversation.pending
        invalidated = threading.Event()
        original_cancel = self.owner.cancel
        def cancel(**kwargs):
            result = original_cancel(**kwargs)
            invalidated.set()
            return result
        self.owner.cancel = cancel
        canceler = threading.Thread(target=self.conversation.cancel_turn)
        canceler.start()
        try:
            self.assertTrue(invalidated.wait(3))
            self.assertFalse(self.owner.accepts(current.generation))
            self.assertEqual(job.cancels, 0)
            with self.assertRaises(BusyError):
                self.owner.begin('dictation')
        finally:
            finish.set()
            worker.join(3)
            canceler.join(3)
        self.assertFalse(worker.is_alive() or canceler.is_alive())
        self.assertEqual(results, [None])
        self.assertTrue(job.cleanup_proven)
        self.assertEqual(self.conversation.notice.state, Display.READY)

    def test_lease_gap_loser_never_cancels_or_releases_successor(self):
        self.enter()
        self.conversation.submit('hello')
        release = self.owner.release
        successor = []
        def compete(generation, cleaned):
            release(generation, cleaned)
            successor.append(self.owner.begin('dictation'))
        self.owner.release = compete
        self.conversation.cancel_turn()
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
        self.assertEqual(self.conversation.notice.code, Code.BUSY)
        self.conversation.cancel_turn()
        self.conversation.end()
        self.assertTrue(self.owner.accepts(successor[0]))
        self.assertEqual(len(successor), 1)

    def test_external_owner_cancel_ends_conversation_without_reacquisition(self):
        self.enter()
        current = self.conversation.submit('hello')
        self.jobs[-1].result = Response(current, 'stale')
        self.owner.cancel(generation=current.generation)
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)
        successor = self.owner.begin('command')
        self.conversation.end()
        self.assertTrue(self.owner.accepts(successor))

    def test_partial_start_poll_and_cleanup_exceptions_are_explicit(self):
        def fail():
            raise RuntimeError('private error')
        for boundary in ('start', 'poll', 'cancel'):
            with self.subTest(boundary=boundary):
                self.setUp()
                job = Job()
                setattr(job, 'on_' + boundary, fail)
                self.make_job = lambda: job
                self.enter()
                current = self.conversation.submit('hello')
                if boundary == 'poll':
                    self.assertIsNone(self.conversation.poll())
                elif boundary == 'cancel':
                    job.result = Response(current, 'answer')
                    self.assertIsNone(self.conversation.poll())
                else:
                    self.assertIsNone(current)
                self.assertEqual(self.conversation.history, ())
                self.assertEqual(self.conversation.notice.state,
                                 Display.FAULTED if boundary == 'cancel' else Display.INACTIVE)
                self.assertNotIn('private', repr(self.conversation.notice))

    def test_unknown_factory_outcome_faults_admission(self):
        def fail():
            raise RuntimeError('factory outcome unknown')
        self.make_job = fail
        self.enter()
        self.assertIsNone(self.conversation.submit('hello'))
        self.assertEqual(self.conversation.notice.state, Display.FAULTED)
        with self.assertRaises(FaultedError):
            self.owner.begin('command')

    def test_cancel_between_final_freshness_and_publication_keeps_history_empty(self):
        from runtime.voice.conversation_records import Exchange
        self.enter()
        current = self.conversation.submit('hello')
        self.jobs[-1].result = Response(current, 'canceled answer')
        constructed, proceed, canceled = threading.Event(), threading.Event(), threading.Event()
        results = []
        def construct(*args):
            value = Exchange(*args)
            constructed.set()
            if not proceed.wait(3):
                raise RuntimeError('test scheduling timeout')
            return value
        original_cancel = self.owner.cancel
        def invalidate(**kwargs):
            value = original_cancel(**kwargs)
            canceled.set()
            return value
        self.owner.cancel = invalidate
        with patch('runtime.voice.conversation.Exchange', construct):
            worker = threading.Thread(target=lambda: results.append(self.conversation.poll()))
            worker.start()
            self.assertTrue(constructed.wait(3))
            canceler = threading.Thread(target=self.conversation.cancel_turn)
            canceler.start()
            try:
                self.assertTrue(canceled.wait(3))
            finally:
                proceed.set()
                worker.join(3)
                canceler.join(3)
        self.assertFalse(worker.is_alive() or canceler.is_alive())
        self.assertEqual(results, [None])
        self.assertEqual(self.conversation.history, ())

    def test_ready_poll_observes_drift_without_an_active_response_job(self):
        self.enter()
        self.snapshot = replace(self.snapshot, revision=2)
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.code, Code.STALE)
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)

    def test_cleanup_notice_is_stopping_and_fault_is_content_free(self):
        self.enter()
        self.conversation.submit('private input')
        notices = []
        self.jobs[-1].on_cancel = lambda: notices.append(self.conversation.notice)
        self.jobs[-1].clean = False
        self.conversation.end()
        self.assertEqual(notices[0].state, Display.STOPPING)
        self.assertEqual(self.conversation.notice.code, Code.CLEANUP)
        self.assertNotIn('private input', repr(notices))

    def test_context_items_and_last_allowed_poll_boundaries(self):
        self.snapshot = replace(self.snapshot, policy=replace(self.snapshot.policy,
            limits=replace(self.snapshot.policy.limits, context_items=1)))
        self.snapshot = replace(self.snapshot, context=Context(1, ContextState.AVAILABLE,
            (ContextItem('one', 'a'), ContextItem('two', 'b'))))
        self.assertFalse(self.conversation.enter(Entry.PANEL))
        self.assertEqual(self.conversation.notice.code, Code.LIMIT)
        self.setUp()
        self.enter()
        current = self.conversation.submit('hello')
        for _ in range(3):
            self.assertIsNone(self.conversation.poll())
        self.jobs[-1].result = Response(current, 'last chance')
        self.assertEqual(self.conversation.poll().text, 'last chance')
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(len(self.conversation.history), 1)

    def test_wrong_response_shape_and_unavailable_supplier_fail_closed(self):
        for value in ({'text': 'answer'}, 'answer', 1):
            with self.subTest(value=value):
                self.setUp()
                self.enter()
                self.conversation.submit('hello')
                self.jobs[-1].result = value
                self.assertIsNone(self.conversation.poll())
                self.assertEqual(self.conversation.notice.code, Code.INVALID_RESULT)
        self.setUp()
        self.enter()
        self.conversation.submit('hello')
        self.snapshot = None
        self.assertIsNone(self.conversation.poll())
        self.assertEqual(self.conversation.notice.code, Code.UNAVAILABLE)
        self.assertTrue(self.jobs[-1].cleanup_proven)

    def test_exit_phrase_is_not_normalized_or_substring_matched(self):
        self.enter()
        for value in ('End conversation', 'end conversation ', ' end conversation',
                      'end conversation now', 'do not end conversation'):
            self.assertEqual(self.answer(value).text, 'answer')
            self.assertEqual(self.conversation.notice.state, Display.READY)
        self.conversation.submit('end conversation')
        self.assertEqual(self.conversation.notice.state, Display.INACTIVE)

    def test_available_context_is_passed_with_provenance_and_no_output_effects(self):
        self.snapshot = replace(self.snapshot, context=Context(
            1, ContextState.AVAILABLE, (ContextItem('archive:source', 'remember tea'),)))
        with (patch('subprocess.Popen', side_effect=AssertionError('unexpected process')),
              patch('socket.socket', side_effect=AssertionError('unexpected socket')),
              patch('builtins.open', side_effect=AssertionError('unexpected file'))):
            self.enter()
            result = self.answer('hello')
            self.conversation.end()
        self.assertEqual(result.text, 'answer')
        self.assertEqual(self.jobs[-1].request.context.items,
                         (ContextItem('archive:source', 'remember tea'),))
        self.assertEqual(self.conversation.history, ())


if __name__ == '__main__':
    unittest.main()
