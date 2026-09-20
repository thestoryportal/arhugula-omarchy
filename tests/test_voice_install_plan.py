"""Offline proposal tests: no host inspection or installation is permitted."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops.voice_install_plan import plan_install


ROOT = '/home/robbo/'
BASELINE = (
    '.config/hypr/bindings.lua',
    '.config/systemd/user/voxtype.service',
    '.config/systemd/user/voxtype-commands.service',
    '.config/voxtype/config.toml',
    '.config/voxtype/commands.toml',
    '.local/bin/omarchy-voice-command-trigger',
    '.local/bin/omarchy-voice-commands',
)
TARGETS = (
    '.config/systemd/user/arhugula-voice.service',
    '.config/arhugula/voice.json',
    '.local/share/arhugula/voice-v1.pyz',
    '.local/bin/arhugula-voice-home',
    '.local/bin/arhugula-voice-end',
    '.local/bin/arhugula-voice-command',
)


def fixture():
    approved = {ROOT + path: 'a' * 64 for path in BASELINE}
    current = {**approved, **{ROOT + path: None for path in TARGETS}}
    return current, approved


class InstallPlanTests(unittest.TestCase):
    def test_plan_is_detached_deterministic_json_and_never_performs_io(self):
        # Catches a planner that probes/writes the host or mutates caller state.
        current, approved = fixture()
        original = copy.deepcopy((current, approved))
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'sentinel'
            sentinel.write_bytes(b'keep')
            with patch('builtins.open', side_effect=AssertionError('unexpected IO')), \
                 patch.object(Path, 'open', side_effect=AssertionError('unexpected IO')), \
                 patch.object(subprocess, 'Popen', side_effect=AssertionError('unexpected process')):
                plan = plan_install(current, approved, 'v1')
                self.assertEqual(plan, plan_install(dict(reversed(list(current.items()))), approved, 'v1'))
            self.assertEqual(sentinel.read_bytes(), b'keep')
            self.assertEqual(list(Path(directory).iterdir()), [sentinel])
        self.assertEqual((current, approved), original)
        self.assertEqual(json.loads(json.dumps(plan)), plan)
        self.assertFalse(plan['ready_to_apply'])
        self.assertFalse(plan['external_execution'])
        plan['baseline'][ROOT + BASELINE[0]] = 'b' * 64
        self.assertEqual(approved[ROOT + BASELINE[0]], 'a' * 64)

    def test_missing_unknown_and_malformed_snapshot_fields_reject(self):
        current, approved = fixture()
        for path in current:
            changed = dict(current)
            del changed[path]
            with self.subTest(missing=path), self.assertRaises(ValueError):
                plan_install(changed, approved, 'v1')
        for path in approved:
            changed = dict(approved)
            del changed[path]
            with self.subTest(missing_approval=path), self.assertRaises(ValueError):
                plan_install(current, changed, 'v1')
        for bad in (None, True, [], {}, 'a' * 63, 'g' * 64, 'A' * 64):
            changed = dict(current)
            changed[ROOT + BASELINE[0]] = bad
            with self.subTest(hash=bad), self.assertRaises(ValueError):
                plan_install(changed, approved, 'v1')
        for snapshot in ('current', 'approved'):
            c, a = fixture()
            (c if snapshot == 'current' else a)['/usr/share/omarchy/anything'] = 'a' * 64
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                plan_install(c, a, 'v1')
        for invalid in (None, [], True):
            with self.assertRaises(ValueError):
                plan_install(invalid, approved, 'v1')
            with self.assertRaises(ValueError):
                plan_install(current, invalid, 'v1')

    def test_drift_and_existing_new_paths_block_even_with_same_approved_hash(self):
        for path in BASELINE:
            current, approved = fixture()
            current[ROOT + path] = 'b' * 64
            with self.subTest(drift=path), self.assertRaises(ValueError):
                plan_install(current, approved, 'v1')
        for path in TARGETS:
            for occupied in ('a' * 64, 'symlink', '', False):
                current, approved = fixture()
                current[ROOT + path] = occupied
                with self.subTest(occupied=path, value=occupied), self.assertRaises(ValueError):
                    plan_install(current, approved, 'v1')

    def test_version_cannot_escape_fixed_artifact_destination(self):
        current, approved = fixture()
        for version in ('', '.', '..', '../v1', 'v1/other', '/tmp/x', 'v1\n', 'x' * 65, True, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                plan_install(current, approved, version)

    def test_only_bindings_modified_all_other_legacy_paths_preserved(self):
        current, approved = fixture()
        plan = plan_install(current, approved, 'v1')
        changes = plan['operations']
        modified = [op for op in changes if op['operation'] == 'modify']
        self.assertEqual([op['path'] for op in modified], [ROOT + BASELINE[0]])
        self.assertEqual(modified[0]['precondition'], {'sha256': 'a' * 64})
        additions = [op for op in changes if op['operation'] == 'add']
        self.assertEqual({op['path'] for op in additions}, {ROOT + path for path in TARGETS})
        self.assertTrue(all(op['precondition'] == {'absent': True} for op in additions))
        self.assertEqual(set(plan['preserve']), {ROOT + path for path in BASELINE[1:]})
        self.assertTrue(all(op['path'].startswith(ROOT) for op in changes))

    def test_each_binding_unbound_before_single_replacement_and_semantics_preserved(self):
        current, approved = fixture()
        plan = plan_install(current, approved, 'v1')
        changes = next(op for op in plan['operations'] if op['operation'] == 'modify')['bindings']
        active = {'HOME': 'legacy-home', 'END': 'legacy-end', 'KP_EQUAL': 'legacy-command',
                  'SUPER + X': 'unrelated'}
        for change in changes:
            if change['operation'] == 'unbind':
                active.pop(change['key'])
            else:
                self.assertNotIn(change['key'], active, 'replacement would stack handlers')
                active[change['key']] = change['destination']
        self.assertEqual(active, {
            'HOME': ROOT + '.local/bin/arhugula-voice-home',
            'END': ROOT + '.local/bin/arhugula-voice-end',
            'KP_EQUAL': ROOT + '.local/bin/arhugula-voice-command',
            'SUPER + X': 'unrelated',
        })
        contracts = plan['wrapper_contracts']
        self.assertEqual(contracts['HOME']['steps'], ['cancel-command', 'prove-cleanup', 'dictation-start'])
        self.assertEqual(contracts['HOME']['forward_argv'], ['voxtype', 'record', 'start'])
        self.assertEqual(contracts['END']['steps'], ['require-dictation-owner', 'dictation-stop'])
        self.assertEqual(contracts['END']['forward_argv'], ['voxtype', 'record', 'stop'])
        self.assertEqual(contracts['KP_EQUAL']['steps'], ['owned-command-activation'])

    def test_second_plan_after_partial_install_or_cutover_cannot_stack(self):
        current, approved = fixture()
        plan = plan_install(current, approved, 'v1')
        for operation in plan['operations']:
            after_partial = dict(current)
            after_partial[operation['path']] = 'b' * 64
            with self.subTest(path=operation['path']), self.assertRaises(ValueError):
                plan_install(after_partial, approved, 'v1')

    def test_rollback_requires_owned_receipt_hashes_and_cleanup_not_blanket_restore(self):
        current, approved = fixture()
        plan = plan_install(current, approved, 'v1')
        rollback = plan['rollback']
        self.assertFalse(rollback['ready'])
        self.assertEqual(rollback['first'], ['disable-command-admission', 'prove-owned-child-cleanup'])
        self.assertEqual({item['path'] for item in rollback['operations']},
                         {item['path'] for item in plan['operations']})
        for item in rollback['operations']:
            self.assertEqual(item['precondition'], 'current-sha256-equals-owned-install-receipt')
            self.assertIsNone(item['installed_sha256'])
            if item['path'] == ROOT + BASELINE[0]:
                self.assertEqual(item['operation'], 'restore-owned-binding-diff')
                self.assertEqual(item['original_sha256'], 'a' * 64)
            else:
                self.assertEqual(item['operation'], 'remove-owned-addition')
        self.assertFalse(plan['service_policy']['start'])
        self.assertFalse(plan['service_policy']['enable'])
        self.assertEqual(plan['service_policy']['restart'], 'no')


if __name__ == '__main__':
    unittest.main()
