"""Workflow admission refuses unknown or over-budget native startup context."""
import json
import unittest
import io
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
import test_loop


class StartupBudgetTests(unittest.TestCase):
    setUp = test_loop.LoopTests.setUp

    def require_startup(self):
        state = json.loads(self.loop.path.read_text())
        state['startup_required'] = True
        self.loop.path.write_text(json.dumps(state))

    def sample(self, input_tokens, output_tokens=0, window=1000):
        with self.old_transcript.open('a') as stream:
            stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': input_tokens, 'cached_input_tokens': 0, 'output_tokens': output_tokens}, 'model_context_window': window}}}) + '\n')

    def test_exact_fifteen_percent_admits_after_measured_startup(self):
        self.require_startup()
        self.sample(140, 10)
        report = self.loop.finish_startup()
        self.assertEqual(report['consumed_tokens'], 150)
        self.assertEqual(report['limit_tokens'], 150)
        self.assertEqual(report['context_window_tokens'], 1000)
        self.assertEqual(self.loop.begin('u1')['ticket'], 'u1')

    def test_above_fifteen_percent_holds_work_without_admission(self):
        self.require_startup()
        self.sample(150, 1)
        with self.assertRaisesRegex(ValueError, 'startup-context-budget'):
            self.loop.finish_startup()
        with self.assertRaisesRegex(ValueError, 'startup'):
            self.loop.begin('u1')
        self.assertIsNone(self.loop.status()['admission'])
        self.assertEqual(self.loop.status()['startup_rejection']['consumed_tokens'], 151)
        self.assertTrue(self.loop.status()['reset_requested'])

    def test_unknown_window_or_missing_output_never_claims_fifteen_percent(self):
        for window, output in ((None, 10), (1000, None), (True, 0)):
            with self.subTest(window=window, output=output):
                self.setUp()
                self.require_startup()
                self.sample(140, output, window)
                with self.assertRaisesRegex(ValueError, 'startup.*metric'):
                    self.loop.finish_startup()

    def test_startup_growth_after_receipt_is_checked_before_first_work(self):
        self.require_startup()
        self.sample(100, 0)
        self.loop.finish_startup()
        self.sample(151, 0)
        with self.assertRaisesRegex(ValueError, 'startup-context-budget'):
            self.loop.begin('u1')
        self.assertIsNone(self.loop.status()['admission'])
        self.assertEqual(self.loop.status()['startup_rejection']['reason'], 'startup-context-budget exceeded')

    def test_packet_loads_full_startup_guidance_and_retains_inbox_without_history(self):
        from ops.orchestration.startup import packet
        root = self.loop.path.parent
        names = ('docs/orchestration/context-policy.md', 'docs/orchestration/roles/buford.md', 'docs/governance/laws/chat/SKILL.md')
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('FULL ' + name)
        inbox = root / 'pending.json'
        inbox.write_text('[{"id":"new-message","text":"current direction"}]')
        receipt = root / 'inbox-receipt.json'
        receipt.write_text('{}')
        lit = Mock()
        lit.command.return_value = ('LIT quickstart', None)
        lit.read.return_value = ({'issues': [{'id': 'goal', 'status': 'in_progress', 'title': 'Work'}]}, None)
        controller = SimpleNamespace(config={'cwd': str(root), 'continuation': {'path': '/complete-handoff'}, 'deadline': 'original'}, loop=SimpleNamespace(lit=lit, status=lambda: {'goal_ticket': 'goal'}, _control=lambda: {'repair_paused': False}))
        output = io.StringIO()
        with patch('ops.orchestration.auto_reset.wait_bootstrap', return_value={'session_id': 'fresh', 'epoch': 1}), patch('ops.orchestration.artifacts.capture', return_value={'exit': 0, 'terminal': 'exited', 'receipt': str(receipt), 'stdout': {'path': str(inbox)}}), redirect_stdout(output):
            packet(controller, Path('manifest'))
        for name in names:
            self.assertIn('FULL ' + name, output.getvalue())
        self.assertIn('"inbox_pending": ["new-message"]', output.getvalue())
        self.assertNotIn('current direction', output.getvalue())
        lit.command.assert_called_once_with('quickstart')


if __name__ == '__main__':
    unittest.main()
