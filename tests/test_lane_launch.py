"""Launch plans preserve subscription auth, bounded roles and fresh sessions."""
import json
from pathlib import Path
import tempfile
import unittest

from ops.orchestration.lane_launch import launch_plan, execution_environment, fresh_bootstrap

ROOT = Path(__file__).resolve().parents[1]


class LaneLaunchTests(unittest.TestCase):
    def test_routine_coordinator_uses_light_profile_without_resume_or_apps(self):
        plan = launch_plan(ROOT, 'buford', mcp_names=['server.with.dot'])
        self.assertEqual(plan['model'], 'gpt-6-sol')
        self.assertIn('apps', plan['argv'])
        self.assertIn('plugins', plan['argv'])
        self.assertIn('mcp_servers."server.with.dot".enabled=false', plan['argv'])
        self.assertNotIn('resume', plan['argv'])
        self.assertNotIn('fork', plan['argv'])
        self.assertIn('user-provided AGENTS.md', plan['argv'][-1])
        self.assertIn('verify', plan['argv'][-1])
        self.assertLess(len(plan['argv'][-1]), 900)

    def test_review_cannot_execute_commands_or_bypass_permissions(self):
        plan = launch_plan(ROOT, 'reviewer')
        argv = plan['argv']
        self.assertEqual(plan['model'], 'claude-sonnet-5')
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'dontAsk')
        self.assertEqual(argv[argv.index('--autocompact') + 1], 'auto')
        self.assertIn('--safe-mode', argv)
        self.assertNotIn('--bare', argv)
        self.assertNotIn('--dangerously-skip-permissions', argv)

    def test_runtime_bash_still_requires_permission_classification(self):
        argv = launch_plan(ROOT, 'runtime')['argv']
        self.assertIn('Read,Glob,Grep,Bash', argv)
        self.assertEqual(argv[argv.index('--allowedTools') + 1], 'Read,Glob,Grep')
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'auto')

    def test_escalation_requires_a_named_decision(self):
        with self.assertRaisesRegex(ValueError, 'reason'):
            launch_plan(ROOT, 'senior-reviewer')
        self.assertEqual(launch_plan(ROOT, 'senior-reviewer', reason='review cancellation race')['model'], 'claude-opus-5-5')

    def test_environment_removes_api_routes_preserves_subscription_home(self):
        env = execution_environment({'HOME': '/home/operator', 'PATH': '/bin', 'ANTHROPIC_API_KEY': 'secret', 'ANTHROPIC_BASE_URL': 'bad', 'OPENAI_API_KEY': 'secret', 'CLAUDE_CODE_USE_VERTEX': '1'})
        self.assertEqual(env['HOME'], '/home/operator')
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertNotIn('ANTHROPIC_BASE_URL', env)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('CLAUDE_CODE_USE_VERTEX', env)

    def test_unknown_role_and_escaping_role_path_fail(self):
        with self.assertRaises(ValueError):
            launch_plan(ROOT, 'not-a-role')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'docs/orchestration'
            target.mkdir(parents=True)
            (target / 'launch-profiles.json').write_text(json.dumps({'version': 1, 'roles': {'buford': {'client': 'codex', 'model': 'gpt-6-sol', 'effort': 'medium', 'role_file': '../../../outside'}}}))
            with self.assertRaises(ValueError):
                launch_plan(root, 'buford')

    def test_clear_bootstrap_carries_authority_and_exact_assignment(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / 'assignment.txt'
            artifact.write_text('bounded reviewer task\n')
            prompt = fresh_bootstrap(ROOT, 'reviewer', ticket='arhugula-orchestration-7ji',
                                     comment='cmt-example', artifact=artifact)
            self.assertTrue(prompt.startswith('TO: Claude, independent source reviewer.'))
            self.assertIn('user-provided AGENTS.md', prompt)
            self.assertIn('repair orchestration remains paused', prompt.lower())
            self.assertIn('cmt-example', prompt)
            self.assertIn(str(artifact), prompt)
            self.assertIn('verify', prompt)
            self.assertLess(len(prompt), 1250)
            with self.assertRaises(ValueError):
                fresh_bootstrap(ROOT, 'reviewer', ticket='arhugula-orchestration-7ji',
                                comment='cmt-example', artifact=ROOT.parent / 'other.txt')


if __name__ == '__main__':
    unittest.main()
