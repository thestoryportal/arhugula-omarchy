from dataclasses import FrozenInstanceError, replace
import unittest

from runtime.contracts import Profile
from runtime.voice.conversation_records import (
    Clarification, Code, Context, ContextItem, ContextState, ConversationPolicy,
    Display, Entry, Exchange, Limits, Notice, Request, Response, SetupEvidence,
    Snapshot, TurnToken,
)


def fixture():
    limits = Limits(8, 256, 2048, 8, 4)
    policy = ConversationPolicy('personal', 'local', 1, frozenset(Entry),
                                'end conversation', 'F9', limits)
    setup = SetupEvidence(1, frozenset({'Home', 'End'}), frozenset({'KP_EQUAL'}))
    return Snapshot(Profile(1, 'personal', 'local', True, True), 1, policy,
                    setup, Context(1, ContextState.EMPTY, ()))


def token():
    return TurnToken('owner:1', 1, 1, 'personal', 1, 1, 1)


class RecordTests(unittest.TestCase):
    def test_policy_is_immutable_and_rejects_ambient_or_unbounded_inputs(self):
        policy = fixture().policy
        with self.assertRaises(FrozenInstanceError):
            policy.exit_key = 'End'
        for changes in ({'entries': {'panel'}}, {'entries': frozenset({'panel'})},
                        {'entries': frozenset()}, {'revision': True},
                        {'exit_phrase': ''}, {'exit_key': 'x' * 129},
                        {'profile_id': None}, {'limits': {}},
                        {'exit_phrase': 'x' * 257}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(policy, **changes)
        for field in ('turns', 'text_chars', 'context_chars', 'context_items', 'polls'):
            for value in (True, 0, -1, 1.0, 10**9):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(policy.limits, **{field: value})

    def test_setup_requires_bounded_immutable_collision_evidence(self):
        setup = fixture().setup
        for changes in ({'revision': False}, {'occupied': set()},
                        {'reserved': frozenset({1})}, {'occupied': frozenset({''})},
                        {'occupied': frozenset(str(n) for n in range(257))}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(setup, **changes)

    def test_context_distinguishes_empty_unavailable_and_conflicting(self):
        one = ContextItem('archive:one', 'private memory')
        two = ContextItem('archive:two', 'different memory')
        valid = (Context(1, ContextState.EMPTY, ()),
                 Context(1, ContextState.UNAVAILABLE, ()),
                 Context(1, ContextState.AVAILABLE, (one,)),
                 Context(1, ContextState.CONFLICTING, (one, two), 'conflict-1'))
        self.assertEqual(len(set(valid)), 4)
        for args in ((1, 'empty', ()), (True, ContextState.EMPTY, ()),
                     (1, ContextState.EMPTY, (one,)),
                     (1, ContextState.UNAVAILABLE, (one,)),
                     (1, ContextState.AVAILABLE, ()),
                     (1, ContextState.AVAILABLE, (one,), 'conflict'),
                     (1, ContextState.CONFLICTING, (one,), 'conflict'),
                     (1, ContextState.CONFLICTING, (one, two)),
                     (1, ContextState.AVAILABLE, [one]),
                     (1, ContextState.AVAILABLE, (one,) * 65)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Context(*args)
        for args in (('', 'memory'), ('origin', ''), ('origin', 'x' * 16385),
                     ('origin', 'hidden\x00value')):
            with self.assertRaises(ValueError):
                ContextItem(*args)

    def test_snapshot_parses_profile_and_keeps_absence_explicit(self):
        snapshot = fixture()
        self.assertIsNone(replace(snapshot, policy=None).policy)
        for changes in ({'profile': {}}, {'revision': True}, {'setup': None},
                        {'context': None}, {'policy': {}},
                        {'profile': replace(snapshot.profile, enabled=1)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(snapshot, **changes)

    def test_tokens_and_results_reject_lookalikes_and_hide_content(self):
        current = token()
        for changes in ({'session_id': ''}, {'turn': True}, {'generation': 0},
                        {'profile_revision': -1}, {'policy_revision': 0},
                        {'context_revision': False}):
            with self.assertRaises(ValueError):
                replace(current, **changes)
        response = Response(current, 'private response')
        exchange = Exchange(current, 'private prompt', response.text, None)
        request = Request(current, 'private prompt', fixture().context, (exchange,), None)
        for record in (response, exchange, request):
            self.assertNotIn('private', repr(record))
        for args in ((None, 'answer'), (current, ''), (current, 'x' * 16385)):
            with self.assertRaises(ValueError):
                Response(*args)
        with self.assertRaises(ValueError):
            replace(request, history=[exchange])
        with self.assertRaises(ValueError):
            replace(request, history=(None,))
        with self.assertRaises(ValueError):
            replace(request, resolved_conflict='nonexistent')

    def test_clarification_and_notice_are_closed_content_free_records(self):
        current = token()
        self.assertTrue(Clarification(current, 'conflict', True).use_current)
        for args in ((current, '', True), (current, 'conflict', 1),
                     (None, 'conflict', True)):
            with self.assertRaises(ValueError):
                Clarification(*args)
        notice = Notice(1, 'owner:1', current, Display.READY, Code.READY)
        for changes in ({'version': 2}, {'version': True}, {'state': 'ready'},
                        {'code': 'ready'}, {'turn': {}}, {'session_id': []}):
            with self.assertRaises(ValueError):
                replace(notice, **changes)
        self.assertNotIn('text', notice.__dataclass_fields__)
