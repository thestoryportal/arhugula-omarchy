import concurrent.futures
import threading
import unittest
from uuid import UUID

from runtime.voice.session import BusyError, FaultedError, SessionOwner, StaleOwnerError


class OwnerTests(unittest.TestCase):
    def test_conversation_contends_with_all_participating_modes(self):
        for first in ('command', 'dictation', 'conversation'):
            for second in ('command', 'dictation', 'conversation'):
                with self.subTest(first=first, second=second):
                    owner = SessionOwner()
                    lease = owner.begin(first)
                    with self.assertRaises(BusyError):
                        owner.begin(second)
                    owner.release(lease, cleaned=True)
                    successor = owner.begin(second)
                    owner.cancel(generation=lease)
                    self.assertTrue(owner.accepts(successor))

    def test_conversation_cleanup_fault_blocks_every_participating_mode(self):
        owner = SessionOwner()
        lease = owner.begin('conversation')
        owner.cancel(generation=lease)
        owner.release(lease, cleaned=False)
        for mode in ('command', 'dictation', 'conversation'):
            with self.assertRaises(FaultedError):
                owner.begin(mode)

    def test_scoped_cancel_never_invalidates_a_successor_owner(self):
        owner = SessionOwner()
        old = owner.begin('command')
        owner.release(old, cleaned=True)
        current = owner.begin('dictation')
        owner.cancel(generation=old)
        self.assertTrue(owner.accepts(current))
        owner.cancel(generation=current)
        self.assertFalse(owner.accepts(current))
        with self.assertRaises(BusyError):
            owner.begin('command')
        owner.release(current, cleaned=True)
        self.assertTrue(owner.accepts(owner.begin('command')))

    def test_invalid_scoped_cancellation_does_not_change_owner(self):
        owner = SessionOwner()
        current = owner.begin('command')
        for invalid in (True, False, 0, -1, '1', 1.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                owner.cancel(generation=invalid)
            self.assertTrue(owner.accepts(current))

    def test_cancellation_does_not_release_physical_owner(self):
        owner = SessionOwner()
        generation = owner.begin("command")
        canceled = owner.cancel()
        self.assertGreater(canceled, generation)
        self.assertFalse(owner.accepts(generation))
        with self.assertRaises(BusyError):
            owner.begin("dictation")
        owner.release(generation, cleaned=True)
        self.assertGreater(owner.begin("dictation"), canceled)

    def test_completion_releases_ownership_and_invalidates_old_work(self):
        owner = SessionOwner()
        generation = owner.begin("dictation")
        self.assertTrue(owner.accepts(generation))
        owner.release(generation, cleaned=True)
        self.assertFalse(owner.accepts(generation))
        later = owner.begin("command")
        self.assertGreater(later, generation)
        self.assertFalse(owner.accepts(generation))
        self.assertTrue(owner.accepts(later))

    def test_repeated_cancel_retains_original_cleanup_token(self):
        owner = SessionOwner()
        generation = owner.begin("command")
        first = owner.cancel()
        second = owner.cancel()
        self.assertGreater(second, first)
        for wrong in (first, second, generation + 20):
            with self.assertRaises(StaleOwnerError):
                owner.release(wrong, cleaned=True)
        owner.release(generation, cleaned=True)
        self.assertTrue(owner.accepts(owner.begin("dictation")))

    def test_cancel_before_start_does_not_claim_resources(self):
        owner = SessionOwner()
        canceled = owner.cancel()
        self.assertFalse(owner.accepts(canceled))
        self.assertGreater(owner.begin("command"), canceled)

    def test_failed_cleanup_latches_fault_even_after_later_success_report(self):
        owner = SessionOwner()
        generation = owner.begin("command")
        owner.release(generation, cleaned=False)
        self.assertFalse(owner.accepts(generation))
        owner.cancel()
        with self.assertRaises(FaultedError):
            owner.release(generation, cleaned=True)
        with self.assertRaises(FaultedError):
            owner.begin("dictation")

    def test_late_duplicate_cleanup_cannot_release_new_capture(self):
        owner = SessionOwner()
        old = owner.begin("command")
        owner.release(old, cleaned=True)
        new = owner.begin("command")
        for success in (True, False):
            with self.assertRaises(StaleOwnerError):
                owner.release(old, cleaned=success)
        self.assertTrue(owner.accepts(new))
        with self.assertRaises(BusyError):
            owner.begin("dictation")

    def test_invalid_mode_does_not_claim(self):
        owner = SessionOwner()
        for mode in (None, True, 1, "", "COMMAND", "shell", []):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                owner.begin(mode)
        self.assertTrue(owner.accepts(owner.begin("command")))

    def test_invalid_cleanup_and_generation_do_not_change_owner(self):
        owner = SessionOwner()
        generation = owner.begin("command")
        for value in (True, False, None, 0, -1, "1", 1.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                owner.release(value, cleaned=True)
            self.assertFalse(owner.accepts(value))
        for value in (0, 1, None, "yes"):
            with self.subTest(cleaned=value), self.assertRaises(ValueError):
                owner.release(generation, cleaned=value)
        self.assertTrue(owner.accepts(generation))

    def test_release_without_owner_rejects(self):
        with self.assertRaises(StaleOwnerError):
            SessionOwner().release(1, cleaned=True)

    def test_begin_contention_admits_only_one_owner(self):
        owner = SessionOwner()
        barrier = threading.Barrier(8)
        def begin(_):
            barrier.wait(timeout=3)
            try:
                return owner.begin("command")
            except BusyError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(begin, range(8)))
        winners = [value for value in outcomes if value is not None]
        self.assertEqual(len(winners), 1)
        self.assertTrue(owner.accepts(winners[0]))

    def test_new_instances_require_separate_session_identity(self):
        first, second = SessionOwner(), SessionOwner()
        self.assertEqual(UUID(first.session_id).version, 4)
        self.assertNotEqual(first.session_id, second.session_id)
        with self.assertRaises(AttributeError):
            first.session_id = second.session_id


if __name__ == "__main__":
    unittest.main()
