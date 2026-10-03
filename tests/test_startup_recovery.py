"""Interrupted clears recover under current authority without freshness credit."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from pathlib import Path

import test_auto_reset
from ops.orchestration.artifacts import file_binding
from ops.orchestration.loop import identity


class StartupRecoveryTests(unittest.TestCase):
    setUp = test_auto_reset.AutoResetTests.setUp
    controller = test_auto_reset.AutoResetTests.controller
    hold = test_auto_reset.AutoResetTests.hold
    fresh = test_auto_reset.AutoResetTests.fresh
    recovery_fixture = test_auto_reset.AutoResetTests.recovery_fixture

    def current_authority(self):
        controller, authority, fresh = self.recovery_fixture()
        grant = json.loads(authority.read_text())
        old = Path(controller.status()['old_transcript'])
        with old.open('a') as stream:
            stream.write(json.dumps({'type': 'response_item', 'payload': {'role': 'user', 'content': [{'text': 'automatic continuation after clear'}]}}) + '\n')
        grant['kind'] = 'expired-waiting-title-current-authority'
        snapshot = self.root / 'current-parent.jsonl'
        snapshot.write_bytes(old.read_bytes())
        grant['parent_transcript'] = file_binding(snapshot)
        grant['parent_frontier'] = {'count': 1, 'hash': identity(old)['last_user_hash']}
        control = json.loads(self.loop.control.read_text())
        control['repair_paused'] = False
        self.loop.control.write_text(json.dumps(control))
        frozen = Path(grant['routing']['path'])
        frozen.write_bytes(self.loop.control.read_bytes())
        grant['routing'] = file_binding(frozen)
        human = Path(grant['human_authority']['path'])
        human.write_text(json.dumps({'session_id': 'new', 'user_frontier': grant['user_frontier'], 'actual_user_message': identity(fresh)['first_user']}))
        grant['human_authority'] = file_binding(human)
        authority.write_text(json.dumps(grant))
        return controller, authority, fresh

    def test_changed_parent_recovers_current_identity_with_unpaused_routing(self):
        controller, authority, fresh = self.current_authority()
        before = self.loop.status()
        result = controller.recover_maintenance(authority)
        after = self.loop.status()
        self.assertEqual(result['phase'], 'maintenance_recovered')
        self.assertEqual(after['session_id'], 'new')
        self.assertTrue(after['maintenance_only'])
        self.assertFalse(json.loads(self.loop.control.read_text())['repair_paused'])
        for key in ('epoch', 'completed', 'reviews', 'quarantine', 'unit_quarantine'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.window.queued, [])
        self.assertEqual(len(self.window.lines), 1)
        with self.assertRaisesRegex(ValueError, 'genuine native reset'):
            self.loop.begin('u1')

    def test_recovery_retains_different_current_goal_without_replacing_production_contract(self):
        controller, authority, fresh = self.current_authority()
        grant = json.loads(authority.read_text())
        with sqlite3.connect(self.database) as db:
            db.execute('INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)', ('new', 'recovery', 'Fix the interrupted reset', 'active', None, 9, 2, 2000, 2000))
        from ops.orchestration.native_goal import read_goal
        goal = Path(grant['current_goal']['path'])
        goal.write_text(json.dumps(read_goal(self.database, 'new')))
        grant['current_goal'] = file_binding(goal)
        authority.write_text(json.dumps(grant))
        controller.recover_maintenance(authority)
        ledger = json.loads(Path(self.config['goal_ledger']).read_text())
        self.assertEqual(ledger['objective'], 'full scope')
        self.assertEqual(ledger['deadline'], 'original')
        self.assertEqual(ledger['tokens_used'], 100)
        self.assertEqual(ledger['recovery_goals'][0]['session_id'], 'new')
        self.assertEqual(ledger['recovery_goals'][0]['receipt'], file_binding(goal))
        controller.retain_goal(goal, 'new')
        self.assertEqual(json.loads(Path(self.config['goal_ledger']).read_text())['objective'], 'full scope')

    def test_fresh_native_clear_requires_startup_receipt_before_workflow(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        package = Path(controller.status()['reset']['directory'])
        prompt = (package / 'resume-prompt.txt').read_text()
        self.assertIn('ops.orchestration.startup packet', prompt)
        self.assertIn('--state ' + str(self.loop.path), prompt)
        self.assertIn('--control ' + str(self.loop.control), prompt)
        self.assertNotIn('--unit reset-startup-recovery', prompt)
        controller.step(self.fresh())
        self.assertEqual(self.loop.status()['epoch'], 1)
        with self.assertRaisesRegex(ValueError, 'startup context receipt'):
            self.loop.begin('u1')

    def test_live_pause_after_current_authority_refuses_without_goal_write(self):
        controller, authority, fresh = self.current_authority()
        control = json.loads(self.loop.control.read_text())
        control['repair_paused'] = True
        self.loop.control.write_text(json.dumps(control))
        ledger = Path(self.config['goal_ledger']).read_bytes()
        with self.assertRaises(ValueError):
            controller.recover_maintenance(authority)
        self.assertEqual(Path(self.config['goal_ledger']).read_bytes(), ledger)

    def test_recovery_goal_evidence_remains_bound_on_later_reads(self):
        controller, authority, fresh = self.current_authority()
        from ops.orchestration.goal_lineage import GoalLineage
        path = self.root / 'repair-goal.json'
        path.write_text(json.dumps({'goal': {'threadId': 'new', 'objective': 'repair', 'tokensUsed': 9, 'timeUsedSeconds': 2}, 'remainingTokens': None}))
        ledger = GoalLineage(self.config['goal_ledger'])
        ledger.record_recovery(path, 'original')
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'recovery.*receipt'):
            ledger._existing('original')

    def test_recovery_goal_cannot_regress_usage(self):
        self.current_authority()
        from ops.orchestration.goal_lineage import GoalLineage
        ledger = GoalLineage(self.config['goal_ledger'])
        for number, tokens in enumerate((9, 8)):
            path = self.root / f'repair-goal-{number}.json'
            path.write_text(json.dumps({'goal': {'threadId': 'new', 'objective': 'repair', 'tokensUsed': tokens, 'timeUsedSeconds': 2}, 'remainingTokens': None}))
            if number == 0:
                ledger.record_recovery(path, 'original')
            else:
                with self.assertRaisesRegex(ValueError, 'regressed'):
                    ledger.record_recovery(path, 'original')

    def test_current_authority_retries_after_routing_write_without_epoch_credit(self):
        controller, authority, fresh = self.current_authority()
        from ops.orchestration.records import atomic_json
        def interrupted(path, value, **kwargs):
            atomic_json(path, value, **kwargs)
            if Path(path) == self.loop.control:
                raise OSError('after routing write')
        before = self.loop.status()
        with patch('ops.orchestration.loop.atomic_json', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'routing'):
                controller.recover_maintenance(authority)
        result = controller.recover_maintenance(authority)
        self.assertEqual(result['phase'], 'maintenance_recovered')
        self.assertEqual(self.loop.status()['epoch'], before['epoch'])
        self.assertEqual(self.window.queued, [])

    def test_current_parent_authority_refuses_another_unbound_outgoing_message(self):
        controller, authority, fresh = self.current_authority()
        old = Path(controller.status()['old_transcript'])
        with old.open('a') as stream:
            stream.write(json.dumps({'type': 'response_item', 'payload': {'role': 'user', 'content': [{'text': 'later direct pause'}]}}) + '\n')
        before = self.loop.status()
        with self.assertRaisesRegex(ValueError, 'parent'):
            controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status(), before)


if __name__ == '__main__':
    unittest.main()
