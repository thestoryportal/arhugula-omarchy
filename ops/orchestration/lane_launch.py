"""Fresh role-scoped launch plans; run in the existing terminal after release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

API_OVERRIDES = frozenset({
    'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
    'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CLAUDE_CODE_USE_BEDROCK',
    'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
})
# A parent's native session identity; each fresh child CLI mints its own.
SESSION_AFFINITY = frozenset({'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CLAUDE_CODE_SESSION_ID'})
INHERITED_OVERRIDES = API_OVERRIDES | SESSION_AFFINITY
# [LAW:one-source-of-truth] Guidance and control live only in the canonical root; a lane
# checkout's tracked copies are stale or absent.
CANONICAL_GUIDANCE = {'agents': 'AGENTS.md', 'policy': 'docs/orchestration/context-policy.md',
                      'communication': 'docs/orchestration/communication.md',
                      'control': 'docs/orchestration/session-control.json'}
CODER_ROLES = ('claude-coder', 'profile-coder', 'facade-coder')
ROLE_TITLES = {
    'buford': 'Buford, lead orchestrator',
    'implementer': 'Codex, implementer',
    'profile-reviewer': 'Codex, independent profile reviewer',
    'facade-reviewer': 'Codex, independent facade reviewer',
    'claude-coder': 'Claude, coding implementer',
    'profile-coder': 'Claude, Omarchy profile coding implementer',
    'facade-coder': 'Claude, production facade coder',
    'reviewer': 'Claude, independent source reviewer',
    'runtime': 'Claude, runtime tester',
    'senior-reviewer': 'Claude, senior independent reviewer',
}


def execution_environment(env):
    """Keep subscription authentication in its CLI; remove API routes and parent identity."""
    return {key: value for key, value in env.items() if key not in INHERITED_OVERRIDES}


def lane_checkout(root, workdir):
    """A lane is a registered linked worktree of the root: one shared LIT store, its own claim lane."""
    workdir = Path(workdir).resolve()
    marker = workdir / '.git'
    pointer = marker.read_text().removeprefix('gitdir:').strip() if marker.is_file() else ''
    admin = (workdir / pointer).resolve()
    registration = admin / 'gitdir'
    registered = (admin / registration.read_text().strip()).resolve() if registration.is_file() else None
    # [LAW:parse-dont-validate] LIT claims are per checkout; only a distinct linked worktree
    # of this root keeps the store canonical and the lane identity separate. Git records the
    # link both ways, so a copied pointer names an admin entry registered to another checkout.
    if admin.parent != root / '.git' / 'worktrees' or registered != marker:
        raise ValueError(f'lane workdir must be a linked worktree of {root}')
    return workdir


def launch_plan(root, role, *, reason='', codex='codex', claude='claude',
                assignment_message=None, workdir=None):
    root = Path(root).resolve()
    if workdir is not None and role not in CODER_ROLES:
        raise ValueError('workdir override belongs to the isolated Claude coder lane')
    launch_cwd = lane_checkout(root, workdir) if workdir is not None else root
    profiles = json.loads((root / 'docs/orchestration/launch-profiles.json').read_text())
    if profiles.get('version') != 1 or role not in profiles.get('roles', {}):
        raise ValueError('unknown role or profile version')
    if role not in ROLE_TITLES:
        raise ValueError('role has no actual recipient name')
    if role.startswith('senior-') and not reason.strip():
        raise ValueError('senior role requires a bounded escalation reason')
    profile = profiles['roles'][role]
    role_file = (root / profile['role_file']).resolve()
    if not role_file.is_relative_to(root) or not role_file.is_file():
        raise ValueError('role file must exist inside the root checkout')
    startup_action = (assignment_message if assignment_message is not None else
                      'Follow canonical Startup, verify current release, ownership and measured admission, '
                      'then begin eligible work in this turn. Hold unreleased scope. ')
    guidance = {name: root / path for name, path in CANONICAL_GUIDANCE.items()}
    prompt = (
        f'TO: {ROLE_TITLES[role]}. FROM: Buford, lead orchestrator. '
        f'The human user authorized this named-team workflow in the user-provided {guidance["agents"]}; '
        'verify that source before accepting delegated work. '
        f'Read {role_file} and {guidance["policy"]}. '
        f'{startup_action}'
        # [LAW:one-source-of-truth] The pause lives in the registry, not launch text.
        f'Check {guidance["control"]} for the current repair pause. '
        'Continue only a verified current released claim. '
        'Read applicable full guidance once when doing that medium; do not load history. '
        'This is a new session, not resume or fork.'
    )
    if reason:
        prompt += f' Escalation decision: {reason}'
    # [LAW:effects-at-boundaries] A launch is inspectable argv until --run is explicit.
    if profile['client'] == 'codex':
        argv = [codex, '--model', profile['model'], '-c',
                f'model_reasoning_effort="{profile["effort"]}"',
                # [LAW:single-enforcer] Native approval review owns its workspace-write sandbox;
                # redundant sandbox/approval flags are rejected by this installed CLI.
                '--approve-for-me', '--cd', str(root)]
    elif profile['client'] == 'claude':
        runtime = role == 'runtime'
        coder = role in CODER_ROLES
        native_role_context = (
            f'Arhugula role: {ROLE_TITLES[role]}. The validated role guidance is:\n'
            f'{role_file.read_text(encoding="utf-8").strip()}\n'
            f'Canonical installed root: {root}. Launch checkout: {launch_cwd}. Read guidance '
            'and control only at these canonical paths, never a checkout copy; before '
            f'delegated work, read and verify {", ".join(map(str, guidance.values()))}. '
            'Authors select eligible released work; Buford coordinates integration; '
            'the role prompt does not authenticate a sender or authorize a task. '
            'Honor the current repair pause and keep independent source review and '
            'runtime testing separate. Direct user instructions and normal tool '
            'permissions still apply; do not bypass a denial.'
        )
        argv = [claude, '--safe-mode', '--model', profile['model'], '--effort', profile['effort'],
                '--autocompact', 'auto', '--name', f'Arhugula {role}',
                '--append-system-prompt', native_role_context,
                '--tools', ('Read,Glob,Grep,Bash,Edit,Write' if coder else
                            'Read,Glob,Grep,Bash' if runtime else 'Read,Glob,Grep'),
                '--allowedTools', ('Read,Glob,Grep,Bash,Edit,Write' if coder else
                                   'Read,Glob,Grep'),
                '--permission-mode', 'auto' if runtime or coder else 'dontAsk']
    else:
        raise ValueError('unsupported client')
    return {'role': role, 'model': profile['model'], 'effort': profile['effort'],
            'cwd': str(launch_cwd), 'argv': [*argv, prompt], 'shell': False,
            'removed_environment_keys': sorted(INHERITED_OVERRIDES)}


def fresh_bootstrap(root, role, *, ticket, comment, artifact):
    """One verified authority and assignment prompt for a native same-window clear."""
    root = Path(root).resolve()
    artifact = Path(artifact).resolve()
    if not ticket or not comment or not artifact.is_relative_to(root) or not artifact.is_file():
        raise ValueError('bootstrap requires a ticket, comment and local assignment file')
    action = ('read-only source review' if role in ('reviewer', 'senior-reviewer')
              else 'bounded assignment')
    assignment = (
        'The human user explicitly directed Buford to clear and prompt fresh windows '
        'once durable context is in place. '
        f'Current bounded assignment: {ticket} | {comment}; exact canonical comment '
        f'snapshot: {artifact}. Verify AGENTS.md and the snapshot, then execute the '
        f'{action} within its bounds. '
    )
    return launch_plan(root, role, assignment_message=assignment)['argv'][-1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--reason', default='')
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--run', action='store_true', help='launch here; default only prints argv')
    parser.add_argument('--released', action='store_true', help='attest prior worker/process ownership released')
    parser.add_argument('--keep-open', action='store_true', help='offer new/exit after child exits in this terminal')
    parser.add_argument('--bootstrap-only', action='store_true', help='print one post-clear authority and assignment prompt')
    parser.add_argument('--ticket', default='')
    parser.add_argument('--comment', default='')
    parser.add_argument('--artifact', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.bootstrap_only:
            if args.run:
                raise ValueError('--bootstrap-only cannot launch a session')
            print(fresh_bootstrap(args.root, args.role, ticket=args.ticket,
                                  comment=args.comment, artifact=args.artifact))
            return 0
        plan = launch_plan(args.root, args.role, reason=args.reason,
                           codex=args.codex, claude=args.claude, workdir=args.workdir)
        if not args.run:
            print(json.dumps(plan, indent=2))
            return 0
        if not args.released or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError('--run requires a visible terminal and --released ownership attestation')
        # [LAW:no-ambient-temporal-coupling] Only child exit permits the next fresh session.
        while True:
            result = subprocess.run(plan['argv'], cwd=plan['cwd'], env=execution_environment(os.environ), check=False)
            if result.returncode or not args.keep_open:
                return result.returncode
            print('Session exited. Preserve its ticket evidence; verify ownership release before typing new.')
            if input('new / exit: ').strip() != 'new':
                return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'launch refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
