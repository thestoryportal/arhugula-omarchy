"""Workflow admission refuses unknown or over-budget native startup context."""
import json
import unittest
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


if __name__ == '__main__':
    unittest.main()
