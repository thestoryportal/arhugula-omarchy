"""Launch plans preserve subscription auth, bounded roles and fresh sessions."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from ops.orchestration.lane_launch import launch_plan, execution_environment, fresh_bootstrap

ROOT = Path(__file__).resolve().parents[1]
GUIDANCE_PATH = re.compile(r'[\w./-]*(?:AGENTS\.md|docs/orchestration/[\w./-]+\.(?:md|json))')


def git(cwd, *args):
    subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


def canonical_root_with_lane(test, lane='claude-coder'):
    """A main checkout holding the launch profiles, plus one linked lane worktree inside it."""
    directory = tempfile.TemporaryDirectory(prefix='arhugula-lane-launch-')
    test.addCleanup(directory.cleanup)
    root = Path(directory.name) / 'root'
    shutil.copytree(ROOT / 'docs/orchestration/roles', root / 'docs/orchestration/roles')
    shutil.copy(ROOT / 'docs/orchestration/launch-profiles.json', root / 'docs/orchestration')
    git(root.parent, 'init', '-q', '-b', 'main', str(root))
    git(root, 'commit', '-q', '--allow-empty', '-m', 'baseline')
    checkout = root / '.worktrees/lanes' / lane
    git(root, 'worktree', 'add', '-q', '-b', f'lane/{lane}', str(checkout))
    return root, checkout


class LaneLaunchTests(unittest.TestCase):
    def test_codex_native_launch_uses_one_normal_automatic_approval_mode(self):
        argv = launch_plan(ROOT, 'implementer')['argv']
        self.assertIn('--approve-for-me', argv)
        self.assertNotIn('--sandbox', argv)
        self.assertNotIn('--ask-for-approval', argv)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', argv)

    def test_each_additional_claude_author_has_a_named_codex_reviewer(self):
        profiles = json.loads((ROOT / 'docs/orchestration/launch-profiles.json').read_text())['roles']
        for role, name in (('profile-reviewer', 'profile'), ('facade-reviewer', 'facade')):
            with self.subTest(role=role):
                self.assertIn(role, profiles)
                plan = launch_plan(ROOT, role)
                self.assertEqual((plan['model'], plan['effort']),
                                 (profiles[role]['model'], profiles[role]['effort']))
                self.assertIn(f'TO: Codex, independent {name} reviewer.', plan['argv'][-1])
                self.assertIn('--approve-for-me', plan['argv'])

    def test_coordinator_preserves_native_plugins_and_mcp_configuration(self):
        plan = launch_plan(ROOT, 'buford')
        self.assertEqual(plan['model'], 'gpt-6.1-sol')
        self.assertNotIn('--disable', plan['argv'])
        self.assertFalse(any(arg.startswith('mcp_servers.') for arg in plan['argv']))
        self.assertNotIn('resume', plan['argv'])
        self.assertNotIn('fork', plan['argv'])
        self.assertIn(f'user-provided {ROOT / "AGENTS.md"};', plan['argv'][-1])
        self.assertIn('verify', plan['argv'][-1])

    def test_default_startup_advances_only_current_released_work(self):
        for role in ('buford', 'implementer', 'profile-reviewer', 'claude-coder', 'runtime'):
            with self.subTest(role=role):
                prompt = launch_plan(ROOT, role)['argv'][-1]
                self.assertIn('begin eligible work in this turn', prompt)
                self.assertIn('measured admission', prompt)
                self.assertIn('Hold unreleased scope', prompt)
                self.assertNotIn('Startup only', prompt)
                self.assertNotIn('wait for a canonical assignment', prompt)

    def test_claude_preserves_configured_mcp_servers(self):
        self.assertNotIn('--strict-mcp-config', launch_plan(ROOT, 'claude-coder')['argv'])

    def test_review_cannot_execute_commands_or_bypass_permissions(self):
        plan = launch_plan(ROOT, 'reviewer')
        argv = plan['argv']
        self.assertEqual(plan['model'], 'claude-opus-5-5')
        self.assertEqual(plan['effort'], 'high')
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-opus-5-5')
        self.assertEqual(argv[argv.index('--effort') + 1], 'high')
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

    def test_persistent_claude_coder_has_owned_write_tools_and_safe_mode(self):
        root, checkout = canonical_root_with_lane(self)
        plan = launch_plan(root, 'claude-coder', workdir=checkout)
        argv = plan['argv']
        self.assertEqual((plan['model'], plan['effort']), ('claude-opus-5-5', 'high'))
        self.assertEqual(plan['cwd'], str(checkout))
        self.assertIn('--safe-mode', argv)
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep,Bash,Edit,Write')
        self.assertEqual(argv[argv.index('--allowedTools') + 1], 'Read,Glob,Grep,Bash,Edit,Write')
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'auto')
        self.assertNotIn('--bare', argv)
        self.assertNotIn('--dangerously-skip-permissions', argv)
        context = argv[argv.index('--append-system-prompt') + 1]
        role_text = (root / 'docs/orchestration/roles/claude-coder.md').read_text().strip()
        self.assertIn(role_text, context)
        with self.assertRaisesRegex(ValueError, 'isolated Claude coder'):
            launch_plan(root, 'reviewer', workdir=checkout)

    def test_visible_profile_coder_is_distinct_opus_high_lane(self):
        root, checkout = canonical_root_with_lane(self, 'profile-coder')
        plan = launch_plan(root, 'profile-coder', workdir=checkout)
        argv = plan['argv']
        self.assertEqual((plan['model'], plan['effort']), ('claude-opus-5-5', 'high'))
        self.assertEqual(plan['cwd'], str(checkout))
        self.assertIn('Arhugula profile-coder', argv)
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep,Bash,Edit,Write')
        self.assertIn('Claude, Omarchy profile coding implementer', argv[-1])

    def test_facade_writer_can_launch_with_owned_worktree_and_write_tools(self):
        root, checkout = canonical_root_with_lane(self, 'facade-coder')
        plan = launch_plan(root, 'facade-coder', workdir=checkout)
        argv = plan['argv']
        self.assertEqual(plan['cwd'], str(checkout))
        self.assertEqual(argv[argv.index('--tools') + 1], 'Read,Glob,Grep,Bash,Edit,Write')
        self.assertEqual(argv[argv.index('--allowedTools') + 1], 'Read,Glob,Grep,Bash,Edit,Write')
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'auto')
        self.assertIn('TO: Claude, production facade coder.', argv[-1])

    def test_all_claude_launches_select_user_requested_opus_high(self):
        for role in ('claude-coder', 'profile-coder', 'facade-coder', 'reviewer', 'runtime', 'senior-reviewer'):
            with self.subTest(role=role):
                argv = launch_plan(ROOT, role, reason='bounded difficult review' if role=='senior-reviewer' else '')['argv']
                self.assertEqual(argv[argv.index('--model') + 1], 'claude-opus-5-5')
                self.assertEqual(argv[argv.index('--effort') + 1], 'high')

    def test_claude_roles_get_distinct_native_context_from_validated_role_files(self):
        reviewer = launch_plan(ROOT, 'reviewer')['argv']
        runtime = launch_plan(ROOT, 'runtime')['argv']
        self.assertIn('--append-system-prompt', reviewer)
        self.assertIn('--append-system-prompt', runtime)
        review_context = reviewer[reviewer.index('--append-system-prompt') + 1]
        runtime_context = runtime[runtime.index('--append-system-prompt') + 1]
        self.assertIn('Claude, independent source reviewer', review_context)
        self.assertNotIn('Claude, runtime tester', review_context)
        self.assertIn('Claude, runtime tester', runtime_context)
        self.assertNotIn('Claude, independent source reviewer', runtime_context)
        for argv, context in ((reviewer, review_context), (runtime, runtime_context)):
            self.assertIn('--safe-mode', argv)
            self.assertNotIn('--system-prompt', argv)
            self.assertNotIn('--bare', argv)
            self.assertIn('AGENTS.md', context)
            self.assertIn('context-policy.md', context)
            self.assertIn('session-control.json', context)
            self.assertIn('permission', context.lower())

    def test_native_context_reads_the_validated_role_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'docs/orchestration'
            (target / 'roles').mkdir(parents=True)
            (target / 'launch-profiles.json').write_text(json.dumps({
                'version': 1,
                'roles': {'reviewer': {
                    'client': 'claude', 'model': 'claude-sonnet-5',
                    'effort': 'medium', 'role_file': 'docs/orchestration/roles/reviewer.md',
                }},
            }))
            role_file = target / 'roles/reviewer.md'
            role_file.write_text('Reviewer source marker alpha')
            first = launch_plan(root, 'reviewer')['argv']
            role_file.write_text('Reviewer source marker beta')
            second = launch_plan(root, 'reviewer')['argv']
            self.assertIn('marker alpha', first[first.index('--append-system-prompt') + 1])
            self.assertIn('marker beta', second[second.index('--append-system-prompt') + 1])
            self.assertNotIn('marker alpha', second[second.index('--append-system-prompt') + 1])

    def test_assignment_stays_in_user_message_outside_native_role_context(self):
        plan = launch_plan(ROOT, 'reviewer', assignment_message='Ticket 7ji cmt-example only')
        argv = plan['argv']
        native_context = argv[argv.index('--append-system-prompt') + 1]
        self.assertNotIn('cmt-example', native_context)
        self.assertIn('cmt-example', argv[-1])

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

    def test_child_environment_drops_parent_session_identity_and_keeps_native_auth(self):
        parent = {'HOME': '/home/operator', 'CODEX_HOME': '/home/operator/.codex',
                  'CLAUDE_CONFIG_DIR': '/home/operator/.claude', 'PATH': '/bin',
                  'CODEX_THREAD_ID': 'buford-thread', 'CODEX_SESSION_ID': 'buford-thread',
                  'CLAUDE_CODE_SESSION_ID': 'parent-claude'}
        env = execution_environment(parent)
        self.assertEqual(env, {key: parent[key] for key in ('HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'PATH')})
        for role in ('implementer', 'claude-coder'):
            with self.subTest(role=role):
                removed = launch_plan(ROOT, role)['removed_environment_keys']
                self.assertLessEqual({'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CLAUDE_CODE_SESSION_ID'}, set(removed))

    def test_lane_author_reads_only_canonical_root_guidance(self):
        root, checkout = canonical_root_with_lane(self)
        argv = launch_plan(root, 'claude-coder', workdir=checkout)['argv']
        context, prompt = argv[argv.index('--append-system-prompt') + 1], argv[-1]
        # The quoted role file is validated guidance, not a launcher-authored path.
        launcher_context = context.replace((root / 'docs/orchestration/roles/claude-coder.md').read_text().strip(), '')
        for name, text in (('native context', launcher_context), ('prompt', prompt)):
            with self.subTest(text=name):
                paths = GUIDANCE_PATH.findall(text)
                self.assertTrue(paths)
                for path in paths:
                    self.assertTrue(path.startswith(f'{root}/'), path)
                    self.assertFalse(path.startswith(f'{checkout}/'), path)
        for relative in ('AGENTS.md', 'docs/orchestration/context-policy.md',
                         'docs/orchestration/communication.md', 'docs/orchestration/session-control.json'):
            self.assertIn(str(root / relative), context)
        self.assertIn(str(checkout), context)

    def test_lane_workdir_must_be_a_distinct_linked_worktree_of_the_canonical_root(self):
        root, checkout = canonical_root_with_lane(self)
        other, foreign = canonical_root_with_lane(self)
        plain = Path(tempfile.mkdtemp(dir=root.parent))
        # A copied pointer names a real admin directory that Git registered to another checkout.
        forged = root / '.worktrees/lanes/forged'
        forged.mkdir()
        shutil.copy(checkout / '.git', forged / '.git')
        for name, launch_root, workdir in (('root itself', root, root),
                                           ('plain directory', root, plain),
                                           ('another repository lane', root, foreign),
                                           ('lane passed as root', checkout, checkout),
                                           ('forged pointer to a registered lane', root, forged)):
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'linked worktree'):
                launch_plan(launch_root, 'claude-coder', workdir=workdir)
        self.assertEqual(launch_plan(other, 'claude-coder', workdir=foreign)['cwd'], str(foreign))

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
            self.assertIn(f'user-provided {ROOT / "AGENTS.md"};', prompt)
            self.assertIn('session-control.json', prompt)
            self.assertNotIn('repair orchestration remains paused', prompt.lower())
            self.assertIn('cmt-example', prompt)
            self.assertIn(str(artifact), prompt)
            self.assertIn('verify', prompt)
            self.assertLess(len(prompt), 1250)
            with self.assertRaises(ValueError):
                fresh_bootstrap(ROOT, 'reviewer', ticket='arhugula-orchestration-7ji',
                                comment='cmt-example', artifact=ROOT.parent / 'other.txt')


if __name__ == '__main__':
    unittest.main()
