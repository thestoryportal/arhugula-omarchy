from dataclasses import replace
import json
from pathlib import Path
import threading
from types import MappingProxyType
import unittest

from runtime.catalog import CatalogError, CatalogRegistry
from runtime.inventory import Inventory, InventoryItem, discover


def fixture():
    return json.loads(Path('tests/fixtures/inventory-v1.json').read_text())


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.registry = CatalogRegistry()

    def seed(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        return self.registry.publish(candidate, reviewed_ids=candidate.diff.added)

    def test_first_discovery_requires_complete_explicit_review_before_publication(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        self.assertEqual(candidate.diff.added, ('app.terminal', 'bind.launcher', 'custom.capture',
                                             'menu.root', 'omarchy.menu.root'))
        self.assertEqual(candidate.diff.changed, ())
        self.assertEqual(candidate.diff.removed, ())
        self.assertTrue(all(not entry.reviewed for entry in candidate.snapshot.entries))
        self.assertEqual(self.registry.snapshot(1).entries, ())
        with self.assertRaises(CatalogError):
            self.registry.publish(candidate, reviewed_ids=())
        published = self.registry.publish(candidate, reviewed_ids=candidate.diff.added)
        self.assertEqual(published.version, 2)
        self.assertTrue(all(entry.reviewed for entry in published.entries))
        with self.assertRaises(CatalogError):
            self.registry.snapshot(1)

    def test_custom_binding_add_change_remove_have_exact_diffs_and_new_revisions(self):
        self.seed()
        data = fixture()
        data['custom_bindings'].append({'id': 'custom.new', 'keys': 'SUPER, N', 'action': 'new.action'})
        candidate = self.registry.propose(discover(data), expected_version=2)
        self.assertEqual(candidate.diff.added, ('custom.new',))
        self.assertEqual(candidate.diff.changed, ())
        self.assertEqual(candidate.diff.removed, ())
        self.registry.publish(candidate, reviewed_ids=('custom.new',))
        data['custom_bindings'][0]['action'] = 'different.action'
        candidate = self.registry.propose(discover(data), expected_version=3)
        self.assertEqual(candidate.diff.changed, ('custom.capture',))
        self.assertFalse(next(e for e in candidate.snapshot.entries if e.identifier == 'custom.capture').reviewed)
        self.registry.publish(candidate, reviewed_ids=('custom.capture',))
        data['custom_bindings'].pop(0)
        candidate = self.registry.propose(discover(data), expected_version=4)
        self.assertEqual(candidate.diff.removed, ('custom.capture',))
        published = self.registry.publish(candidate, reviewed_ids=())
        self.assertEqual(published.version, 5)
        self.assertNotIn('custom.capture', {e.identifier for e in published.entries})
        with self.assertRaises(CatalogError):
            self.registry.snapshot(4)

    def test_identical_inventory_and_transient_state_do_not_advance_version(self):
        original = self.seed()
        data = fixture()
        data['state'] = {'focused_app': 'other', 'workspace': '9'}
        candidate = self.registry.propose(discover(data), expected_version=2)
        self.assertEqual(candidate.snapshot, original)
        self.assertEqual(candidate.diff.added + candidate.diff.changed + candidate.diff.removed, ())
        self.assertEqual(candidate.diff.unchanged, tuple(e.identifier for e in original.entries))
        self.assertEqual(self.registry.publish(candidate, reviewed_ids=()), original)

    def test_ordering_does_not_change_fingerprints_or_diffs(self):
        inventory = discover(fixture())
        first = self.registry.propose(inventory, expected_version=1)
        reordered = replace(inventory, capabilities=tuple(
            replace(item, data=dict(reversed(list(item.data.items()))))
            for item in reversed(inventory.capabilities)))
        second = self.registry.propose(reordered, expected_version=1)
        self.assertEqual(first.snapshot, second.snapshot)
        self.assertEqual(first.diff, second.diff)

    def test_source_and_provenance_changes_invalidate_prior_review(self):
        self.seed()
        inventory = discover(fixture())
        for changed_item in (
            replace(inventory.capabilities[1], source='custom_bindings'),
            replace(inventory.capabilities[1], provenance='new:provenance'),
        ):
            with self.subTest(changed_item=changed_item.identifier):
                items = list(inventory.capabilities)
                items[1] = changed_item
                candidate = self.registry.propose(replace(inventory, capabilities=tuple(items)), expected_version=2)
                self.assertEqual(candidate.diff.changed, ('bind.launcher',))
                with self.assertRaises(CatalogError):
                    self.registry.publish(candidate, reviewed_ids=())

    def test_approval_like_discovery_fields_do_not_authorize_publication(self):
        data = fixture()
        data['custom_bindings'][0].update(approved=True, enabled=True, reviewed=True)
        candidate = self.registry.propose(discover(data), expected_version=1)
        self.assertFalse(next(e for e in candidate.snapshot.entries if e.identifier == 'custom.capture').reviewed)
        with self.assertRaises(CatalogError):
            self.registry.publish(candidate, reviewed_ids=())
        self.assertEqual(self.registry.snapshot(1).entries, ())

    def test_direct_mutable_inventory_cannot_mutate_candidate_or_published_state(self):
        data = {'id': 'custom.one', 'keys': 'SUPER, X', 'action': 'one', 'nested': {'values': ['keep']}}
        item = InventoryItem('custom.one', 'custom_bindings', 'trusted:test', data)
        candidate = self.registry.propose(Inventory((item,), {}, 'state'), expected_version=1)
        data['action'] = 'changed'
        data['nested']['values'].append('changed')
        entry = candidate.snapshot.entries[0]
        self.assertEqual(entry.data['action'], 'one')
        self.assertEqual(entry.data['nested']['values'], ('keep',))
        with self.assertRaises(TypeError):
            entry.data['action'] = 'changed'
        with self.assertRaises((AttributeError, TypeError)):
            entry.data['nested']['values'].append('changed')
        published = self.registry.publish(candidate, reviewed_ids=('custom.one',))
        self.assertEqual(published.entries[0].fingerprint, entry.fingerprint)
        self.assertEqual(published.entries[0].data['action'], 'one')

    def test_superseded_foreign_forged_and_replayed_candidates_cannot_publish(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        replacement = self.registry.propose(discover(fixture()), expected_version=1)
        for bad in (candidate, replace(replacement), None):
            with self.subTest(candidate=type(bad)), self.assertRaises(CatalogError):
                self.registry.publish(bad, reviewed_ids=replacement.diff.added)
        with self.assertRaises(CatalogError):
            CatalogRegistry().publish(replacement, reviewed_ids=replacement.diff.added)
        self.registry.publish(replacement, reviewed_ids=replacement.diff.added)
        with self.assertRaises(CatalogError):
            self.registry.publish(replacement, reviewed_ids=replacement.diff.added)

    def test_invalid_approval_sets_cannot_publish_or_consume_candidate(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        for bad in (True, 'preapproved', list(candidate.diff.added), ('custom.capture',),
                    candidate.diff.added + ('unknown',), candidate.diff.added * 2,
                    (True,), (None,)):
            with self.subTest(approvals=bad), self.assertRaises(CatalogError):
                self.registry.publish(candidate, reviewed_ids=bad)
            self.assertEqual(self.registry.snapshot(1).entries, ())
        self.assertEqual(self.registry.publish(candidate, reviewed_ids=candidate.diff.added).version, 2)

    def test_stale_boolean_float_and_missing_revisions_reject(self):
        self.seed()
        for version in (None, True, False, 1, 2.0, '2', -1, 3):
            with self.subTest(version=version), self.assertRaises(CatalogError):
                self.registry.snapshot(version)
            with self.subTest(propose=version), self.assertRaises(CatalogError):
                self.registry.propose(discover(fixture()), expected_version=version)

    def test_duplicate_empty_inconsistent_and_invalid_source_inventory_rejects(self):
        inventory = discover(fixture())
        item = inventory.capabilities[0]
        bad_items = (
            (item, item),
            (replace(item, identifier=''),),
            (replace(item, identifier='different.id'),),
            (replace(item, source='untrusted-shell'),),
            (replace(item, provenance=''),),
            (replace(item, data={'id': item.identifier}),),
            (replace(item, data=[]),),
        )
        for items in bad_items:
            with self.subTest(items=items), self.assertRaises(CatalogError):
                self.registry.propose(replace(inventory, capabilities=items), expected_version=1)
        with self.assertRaises(CatalogError):
            self.registry.propose({}, expected_version=1)
        self.assertEqual(self.registry.snapshot(1).entries, ())

    def test_nonfinite_non_json_deep_oversize_and_overfull_inputs_reject(self):
        inventory = discover(fixture())
        item = inventory.capabilities[0]
        deep = value = {}
        for _ in range(18):
            value['nested'] = {}
            value = value['nested']
        cyclic = {}
        cyclic['self'] = cyclic
        for bad in (float('nan'), float('inf'), object(), {1: 'bad-key'}, deep, cyclic,
                    'x' * 17000, list(range(5000))):
            data = dict(item.data)
            data['extra'] = bad
            with self.subTest(value=type(bad)), self.assertRaises(CatalogError):
                self.registry.propose(replace(inventory, capabilities=(replace(item, data=data),)), expected_version=1)
        with self.assertRaises(CatalogError):
            self.registry.propose(replace(inventory, capabilities=(item,) * 257), expected_version=1)

    def test_invalid_proposal_does_not_destroy_previous_pending_review(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        with self.assertRaises(CatalogError):
            self.registry.propose(None, expected_version=1)
        self.assertEqual(self.registry.publish(candidate, reviewed_ids=candidate.diff.added).version, 2)

    def test_concurrent_publish_consumes_candidate_once(self):
        candidate = self.registry.propose(discover(fixture()), expected_version=1)
        barrier = threading.Barrier(3)
        outcomes = []
        def publish():
            barrier.wait()
            try:
                self.registry.publish(candidate, reviewed_ids=candidate.diff.added)
                outcomes.append('published')
            except CatalogError:
                outcomes.append('rejected')
        threads = [threading.Thread(target=publish) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ['published', 'rejected'])
        self.assertEqual(self.registry.snapshot(2).version, 2)

    def test_removal_to_empty_catalog_advances_revision_and_invalidates_old_view(self):
        old = self.seed()
        empty = Inventory((), MappingProxyType({}), 'fixture:state')
        candidate = self.registry.propose(empty, expected_version=2)
        self.assertEqual(candidate.diff.removed, tuple(e.identifier for e in old.entries))
        self.assertEqual(self.registry.publish(candidate, reviewed_ids=()).entries, ())
        with self.assertRaises(CatalogError):
            self.registry.snapshot(2)

    def test_repr_and_validation_errors_do_not_reveal_action_payload(self):
        data = fixture()
        secret = 'SENSITIVE_COMMAND_DO_NOT_LOG'
        data['custom_bindings'][0]['action'] = secret
        candidate = self.registry.propose(discover(data), expected_version=1)
        self.assertNotIn(secret, repr(candidate))
        self.assertNotIn(secret, repr(candidate.snapshot))
        self.assertNotIn(secret, repr(candidate.snapshot.entries))
        data['custom_bindings'][0]['id'] = secret + '\n'
        with self.assertRaises(CatalogError) as error:
            self.registry.propose(discover(data), expected_version=1)
        self.assertNotIn(secret, str(error.exception))


if __name__ == '__main__':
    unittest.main()
