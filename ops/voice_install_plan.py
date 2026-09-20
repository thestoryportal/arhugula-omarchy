"""Pure, host-specific P1 cutover proposal; NOT an installer or authorization.

Inputs are trusted, externally collected snapshots. None means a path was
explicitly observed absent (including no dangling symlink), never uninspected.
This module performs no IO and cannot prove that an input reflects the host.
"""
import re


_ROOT = '/home/robbo/'
_BINDINGS = _ROOT + '.config/hypr/bindings.lua'
_BASELINE = (
    _BINDINGS,
    _ROOT + '.config/systemd/user/voxtype.service',
    _ROOT + '.config/systemd/user/voxtype-commands.service',
    _ROOT + '.config/voxtype/config.toml',
    _ROOT + '.config/voxtype/commands.toml',
    _ROOT + '.local/bin/omarchy-voice-command-trigger',
    _ROOT + '.local/bin/omarchy-voice-commands',
)
_WRAPPERS = (
    ('HOME', _ROOT + '.local/bin/arhugula-voice-home'),
    ('END', _ROOT + '.local/bin/arhugula-voice-end'),
    ('KP_EQUAL', _ROOT + '.local/bin/arhugula-voice-command'),
)


def plan_install(current_hashes: dict[str, str | None],
                 approved_hashes: dict[str, str], target_version: str) -> dict:
    """Return a detached, deterministic review proposal or reject with ValueError.

    The seven approved baseline paths must match exactly. Current paths include
    those seven plus all six proposed additions, explicitly absent. A different
    baseline/target set requires a new reviewed planner, not caller-chosen paths.
    The result deliberately lacks deployable content hashes: reviewed wrappers,
    runtime bindings, artifact, live acceptance and scoped operator authority
    remain prerequisites. Rollback is also inert until an owned install receipt
    records exact installed hashes and the original scoped binding diff.
    """
    if (type(target_version) is not str or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', target_version) is None):
        raise ValueError('install.version')
    additions = (
        (_ROOT + '.config/systemd/user/arhugula-voice.service', 'service-template', '0600'),
        (_ROOT + '.config/arhugula/voice.json', 'reviewed-runtime-config', '0600'),
        (_ROOT + f'.local/share/arhugula/voice-{target_version}.pyz', 'reviewed-voice-artifact', '0700'),
        *((path, 'reviewed-owner-wrapper', '0700') for _, path in _WRAPPERS),
    )
    if type(current_hashes) is not dict or type(approved_hashes) is not dict:
        raise ValueError('install.snapshot')
    expected = set(_BASELINE) | {path for path, _, _ in additions}
    if set(approved_hashes) != set(_BASELINE) or set(current_hashes) != expected:
        raise ValueError('install.paths')
    for path in _BASELINE:
        before, approved = current_hashes[path], approved_hashes[path]
        if any(type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None
               for value in (before, approved)):
            raise ValueError('install.hash')
        if before != approved:
            raise ValueError('install.drift')
    if any(current_hashes[path] is not None for path, _, _ in additions):
        raise ValueError('install.target-exists')

    operations = [
        {'operation': 'add', 'path': path, 'precondition': {'absent': True},
         'content_requirement': content, 'mode': mode}
        for path, content, mode in additions
    ]
    binding_changes = []
    for key, destination in _WRAPPERS:
        binding_changes.extend([
            {'operation': 'unbind', 'key': key},
            {'operation': 'bind', 'key': key, 'destination': destination},
        ])
    operations.append({
        'operation': 'modify', 'path': _BINDINGS,
        'precondition': {'sha256': current_hashes[_BINDINGS]},
        'scope': 'HOME, END, KP_EQUAL entries only; retain every other byte',
        'bindings': binding_changes,
    })
    rollback = []
    for operation in reversed(operations):
        path = operation['path']
        rollback.append({
            'operation': ('restore-owned-binding-diff' if path == _BINDINGS
                          else 'remove-owned-addition'),
            'path': path,
            'precondition': 'current-sha256-equals-owned-install-receipt',
            'installed_sha256': None,
            'original_sha256': current_hashes[path],
        })
    return {
        'version': 1, 'target_version': target_version,
        'mode': 'proposal-only', 'ready_to_apply': False, 'external_execution': False,
        'baseline': {path: approved_hashes[path] for path in _BASELINE},
        'preserve': list(_BASELINE[1:]),
        'operations': operations,
        'wrapper_contracts': {
            'HOME': {'steps': ['cancel-command', 'prove-cleanup', 'dictation-start'],
                     'forward_argv': ['voxtype', 'record', 'start']},
            'END': {'steps': ['require-dictation-owner', 'dictation-stop'],
                    'forward_argv': ['voxtype', 'record', 'stop']},
            'KP_EQUAL': {'steps': ['owned-command-activation']},
        },
        'service_policy': {'start': False, 'enable': False, 'restart': 'no',
                           'restore_legacy': 'only-recorded-prior-active-after-cleanup'},
        'requires': [
            'trusted-fresh-regular-file-and-no-symlink-inventory',
            'reviewed-exact-content-hashes-and-scoped-binding-diff',
            'owned-original-backups-and-service-state-record',
            'complete-foreground-provider-and-owner-wrapper-bindings',
            'recorded-and-live-acceptance',
            'explicit-cutover-and-separate-service-start-authority',
        ],
        'rollback': {
            'ready': False,
            'first': ['disable-command-admission', 'prove-owned-child-cleanup'],
            'operations': rollback,
            'requires': ['owned-install-receipt-and-original-backups',
                         'current-installed-hash-match-or-stop-without-overwrite'],
            'validate_after_binding_restore': [['hyprctl', 'reload'], ['hyprctl', 'configerrors']],
            'retain_recovery_files': True,
        },
    }
