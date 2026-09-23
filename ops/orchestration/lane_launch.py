"""Fresh role-scoped launch plans; run in the existing terminal after release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

API_OVERRIDES = frozenset({
    'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL',
    'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CLAUDE_CODE_USE_BEDROCK',
    'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY',
})


def execution_environment(env):
    """Keep subscription authentication in its CLI; remove API route overrides."""
    return {key: value for key, value in env.items() if key not in API_OVERRIDES}


def launch_plan(root, role, *, reason='', mcp_names=(), codex='codex', claude='claude'):
    root = Path(root).resolve()
    profiles = json.loads((root / 'docs/orchestration/launch-profiles.json').read_text())
    if profiles.get('version') != 1 or role not in profiles.get('roles', {}):
        raise ValueError('unknown role or profile version')
    if role.startswith('senior-') and not reason.strip():
        raise ValueError('senior role requires a bounded escalation reason')
    profile = profiles['roles'][role]
    role_file = (root / profile['role_file']).resolve()
    if not role_file.is_relative_to(root) or not role_file.is_file():
        raise ValueError('role file must exist inside the root checkout')
    prompt = (
        f'TO: {role}. FROM: Buford, lead orchestrator. '
        'The human user authorized this named-team workflow in the user-provided AGENTS.md '
        f'at {root}; verify that source before accepting delegated work. '
        f'Read {role_file} and docs/orchestration/context-policy.md. '
        'Startup only: report role and wait for a canonical assignment pointer. '
        'Repair orchestration remains paused. Do not resume older assignments. '
        'Read applicable full guidance once when doing that medium; do not load history. '
        'This is a new session, not resume or fork.'
    )
    if reason:
        prompt += f' Escalation decision: {reason}'
    # [LAW:effects-at-boundaries] A launch is inspectable argv until --run is explicit.
    if profile['client'] == 'codex':
        argv = [codex, '--model', profile['model'], '-c',
                f'model_reasoning_effort="{profile["effort"]}"',
                '--sandbox', 'workspace-write', '--ask-for-approval', 'on-request',
                '--disable', 'apps', '--disable', 'plugins', '--disable', 'remote_plugin',
                '--cd', str(root)]
        for name in sorted(mcp_names):
            argv.extend(['-c', f'mcp_servers.{json.dumps(name)}.enabled=false'])
    elif profile['client'] == 'claude':
        runtime = role == 'runtime'
        argv = [claude, '--safe-mode', '--model', profile['model'], '--effort', profile['effort'],
                '--autocompact', 'auto', '--name', f'Arhugula {role}',
                '--tools', 'Read,Glob,Grep,Bash' if runtime else 'Read,Glob,Grep',
                '--allowedTools', 'Read,Glob,Grep', '--permission-mode', 'auto' if runtime else 'dontAsk',
                '--strict-mcp-config']
    else:
        raise ValueError('unsupported client')
    return {'role': role, 'model': profile['model'], 'effort': profile['effort'],
            'cwd': str(root), 'argv': [*argv, prompt], 'shell': False,
            'removed_environment_keys': sorted(API_OVERRIDES)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--reason', default='')
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--run', action='store_true', help='launch here; default only prints argv')
    parser.add_argument('--released', action='store_true', help='attest prior worker/process ownership released')
    parser.add_argument('--keep-open', action='store_true', help='offer new/exit after child exits in this terminal')
    args = parser.parse_args(argv)
    try:
        config_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
        config_path = config_home / 'config.toml'
        config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
        plan = launch_plan(args.root, args.role, reason=args.reason,
                           mcp_names=config.get('mcp_servers', {}), codex=args.codex, claude=args.claude)
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
