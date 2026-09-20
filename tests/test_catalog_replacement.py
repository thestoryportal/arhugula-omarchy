import threading
import unittest

from runtime.contracts import Capability
from runtime.core import ConfirmationError, ControlPlane, Outcome
from runtime.journal import MemoryJournal
from test_control_plane import fixture


class CatalogReplacementTests(unittest.TestCase):
    def make(self, *, risk='safe', catalog=None, execute=None, clock=None):
        self.calls = []
        self.journal = MemoryJournal()
        return ControlPlane(
            [fixture('capability', risk=risk)] if catalog is None else catalog,
            fixture('policy'), execute or (lambda command: self.calls.append(command) or Outcome('success')),
            self.journal, profile=fixture('profile'), clock=clock or (lambda: 1000))

    def test_atomic_replacement_rejects_old_commands_and_accepts_new_version(self):
        plane = self.make()
        self.assertEqual(plane.catalog_version, 1)
        self.assertEqual(plane.replace_catalog([fixture('capability', catalog_version=2)],
                                              expected_version=1, new_version=2), 2)
        old = plane.dispatch(fixture('command'))
        self.assertEqual(old.error.code, 'catalog.stale')
        self.assertEqual(self.calls, [])
        result = plane.dispatch(fixture('command', command_id='new', catalog_version=2))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(self.calls), 1)

    def test_mixed_constructor_versions_are_rejected_and_empty_starts_at_one(self):
        with self.assertRaises(ValueError):
            self.make(catalog=[fixture('capability'), fixture('capability', capability_id='other', catalog_version=2)])
        self.assertEqual(self.make(catalog=[]).catalog_version, 1)

    def test_invalid_replacements_leave_catalog_and_preview_unchanged(self):
        v2 = fixture('capability', catalog_version=2, risk='confirm')
        cases = [
            ([v2], True, 2), ([v2], 1.0, 2), ([v2], 0, 2), ([v2], 2, 2),
            ([v2], 1, True), ([v2], 1, 2.0), ([v2], 1, 1), ([v2], 1, -1),
            ([v2, v2], 1, 2), ([fixture('capability'), v2], 1, 2),
            ([fixture('capability')], 1, 2), ([None], 1, 2),
            (None, 1, 2), ([v2] * 257, 1, 2),
        ]
        for catalog, expected, new in cases:
            with self.subTest(expected=expected, new=new, count=len(catalog) if catalog else 0):
                plane = self.make(risk='confirm')
                preview = plane.request_confirmation(fixture('command'), 'focus')
                with self.assertRaises(ValueError):
                    plane.replace_catalog(catalog, expected_version=expected, new_version=new)
                self.assertEqual(plane.catalog_version, 1)
                self.assertEqual(plane.confirm(preview.token, 'panel', 'focus').status, 'success')

    def test_successful_replacement_invalidates_all_old_previews(self):
        plane = self.make(risk='confirm')
        previews = [plane.request_confirmation(fixture('command', command_id=f'old-{i}'), 'focus')
                    for i in range(2)]
        plane.replace_catalog([fixture('capability', catalog_version=2, risk='confirm')],
                              expected_version=1, new_version=2)
        for preview in previews:
            with self.assertRaises(ConfirmationError):
                plane.confirm(preview.token, 'keyboard', 'focus')
        self.assertEqual(self.calls, [])
        fresh = plane.request_confirmation(fixture('command', command_id='fresh', catalog_version=2), 'focus')
        self.assertEqual(plane.confirm(fresh.token, 'panel', 'focus').status, 'success')

    def test_empty_replacement_removes_execution_without_resetting_revision(self):
        plane = self.make()
        plane.replace_catalog([], expected_version=1, new_version=2)
        self.assertEqual(plane.catalog_version, 2)
        result = plane.dispatch(fixture('command', catalog_version=2))
        self.assertEqual(result.error.code, 'capability.unavailable')
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            plane.replace_catalog([fixture('capability')], expected_version=2, new_version=1)

    def test_duplicate_history_and_policy_are_preserved(self):
        plane = self.make()
        self.assertEqual(plane.dispatch(fixture('command')).status, 'success')
        plane.replace_catalog([fixture('capability', catalog_version=2),
                               fixture('capability', capability_id='not.allowed', catalog_version=2)],
                              expected_version=1, new_version=2)
        self.assertEqual(plane.dispatch(fixture('command', catalog_version=2)).error.code, 'command.duplicate')
        denied = plane.dispatch(fixture('command', command_id='unauthorized', capability_id='not.allowed', catalog_version=2))
        self.assertEqual(denied.error.code, 'policy.denied')
        self.assertEqual(len(self.calls), 1)

    def test_direct_mutable_capability_is_snapshotted_before_install(self):
        plane = self.make()
        arguments = {'name': 'string'}
        capability = Capability(1, 'menu.open', 2, True, 'safe', arguments, 'trusted-test')
        catalog = [capability]
        plane.replace_catalog(catalog, expected_version=1, new_version=2)
        arguments['name'] = 'integer'
        catalog.clear()
        self.assertEqual(plane.dispatch(fixture('command', catalog_version=2)).status, 'success')

    def test_concurrent_same_base_replacements_have_one_winner(self):
        plane = self.make()
        barrier, outcomes = threading.Barrier(3), []
        def publish():
            barrier.wait(timeout=2)
            try:
                plane.replace_catalog([fixture('capability', catalog_version=2)], expected_version=1, new_version=2)
                outcomes.append('published')
            except ValueError:
                outcomes.append('rejected')
        threads = [threading.Thread(target=publish) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=2)
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ['published', 'rejected'])
        self.assertEqual(plane.catalog_version, 2)

    def test_reentrant_guard_refresh_is_rejected_and_admission_fails_closed(self):
        plane = self.make()
        attempts = []
        def guard():
            attempts.append('attempted')
            plane.replace_catalog([], expected_version=1, new_version=2)
            return True
        result = plane.dispatch(fixture('command'), guard=guard)
        self.assertEqual(attempts, ['attempted'])
        self.assertEqual(result.error.code, 'context.stale')
        self.assertEqual(plane.catalog_version, 1)
        self.assertEqual(self.calls, [])
        plane.replace_catalog([], expected_version=1, new_version=2)
        self.assertEqual(plane.catalog_version, 2)

    def test_reentrant_preview_clock_cannot_replace_catalog(self):
        armed = [False]
        def clock():
            if armed[0]:
                plane.replace_catalog([], expected_version=1, new_version=2)
            return 1000
        plane = self.make(risk='confirm', clock=clock)
        armed[0] = True
        with self.assertRaises(ValueError):
            plane.request_confirmation(fixture('command'), 'focus')
        armed[0] = False
        self.assertEqual(plane.catalog_version, 1)
        plane.replace_catalog([], expected_version=1, new_version=2)
        self.assertEqual(plane.catalog_version, 2)

    def test_reentrant_confirmation_refresh_cannot_change_authorization(self):
        plane = self.make(risk='confirm')
        preview = plane.request_confirmation(fixture('command'), 'focus')
        def guard():
            plane.replace_catalog([], expected_version=1, new_version=2)
            return True
        result = plane.confirm(preview.token, 'panel', 'focus', guard=guard)
        self.assertEqual(result.error.code, 'context.stale')
        self.assertEqual(plane.catalog_version, 1)
        self.assertEqual(self.calls, [])

    def test_other_thread_refresh_waits_until_executor_finishes(self):
        entered, release, attempted, refreshed = (threading.Event() for _ in range(4))
        outcomes = []
        def execute(command):
            entered.set()
            if not release.wait(timeout=3):
                raise RuntimeError('test coordination timeout')
            return Outcome('success')
        plane = self.make(execute=execute)
        worker = threading.Thread(target=lambda: outcomes.append(plane.dispatch(fixture('command')).status))
        def refresh():
            attempted.set()
            plane.replace_catalog([], expected_version=1, new_version=2)
            refreshed.set()
        publisher = threading.Thread(target=refresh)
        worker.start()
        try:
            self.assertTrue(entered.wait(timeout=2))
            publisher.start()
            self.assertTrue(attempted.wait(timeout=2))
            self.assertFalse(refreshed.wait(timeout=0.03))
        finally:
            release.set()
            worker.join(timeout=3)
            if publisher.ident is not None:
                publisher.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(publisher.is_alive())
        self.assertEqual(outcomes, ['success'])
        self.assertTrue(refreshed.is_set())
        self.assertEqual(plane.catalog_version, 2)


if __name__ == '__main__':
    unittest.main()
