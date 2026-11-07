"""Synthetic regression witnesses retained from the frozen R6 observer."""

import errno
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import process_observer as runner


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.argv = ["/installed/python", "-I", "-B", "/installed/parent.py"]
        self.timeout_argv = ["timeout", "-k", "5", "30", *self.argv]
        self.root = {
            "pid": 100,
            "starttime": 11,
            "ppid": 1,
            "pgid": 100,
            "state": "S",
            "comm": "timeout",
            "cmdline": self.timeout_argv,
        }
        self.parent = {
            "pid": 101,
            "starttime": 12,
            "ppid": 100,
            "pgid": 100,
            "parent_key": (100, 11),
            "state": "S",
            "comm": "python",
            "cmdline": self.argv,
        }

    def classify(self, samples):
        return runner.classify(samples, (100, 11), self.argv, "/candidate", ["runner"])

    def test_nominal_lifetime_roles(self):
        git = {
            "pid": 102,
            "starttime": 13,
            "ppid": 101,
            "pgid": 100,
            "parent_key": (101, 12),
            "state": "S",
            "comm": "git",
            "cmdline": ["git", "-C", "/candidate", "status", "--porcelain"],
        }
        result = self.classify([self.root, self.parent, git])
        self.assertEqual(result["unknown"], [])
        self.assertEqual(result["blocking_read_errors"], [])
        self.assertEqual(
            [m["role"] for m in result["members"].values()],
            ["timeout", "witness-parent", "git:status"],
        )

    def test_same_tick_parent_graph_ignores_arrival_order(self):
        parent = {**self.parent, "starttime": 11}
        git = {
            "pid": 102,
            "starttime": 11,
            "ppid": 101,
            "pgid": 100,
            "parent_key": (101, 11),
            "state": "S",
            "comm": "git",
            "cmdline": ["git", "-C", "/candidate", "status", "--porcelain"],
        }
        for samples in ([self.root, parent, git], [self.root, git, parent]):
            result = self.classify(samples)
            self.assertEqual(result["unknown"], [])
            self.assertEqual(result["members"]["102:11"]["role"], "git:status")

    def test_reused_timeout_pid_is_unknown(self):
        reused = {**self.root, "starttime": 99}
        result = self.classify([self.root, reused])
        self.assertIn("100:99", result["unknown"])

    def test_child_parent_lifetime_must_match(self):
        wrong_parent = {**self.parent, "parent_key": (100, 99)}
        result = self.classify([self.root, wrong_parent])
        self.assertIn("101:12", result["unknown"])

    def test_later_unattributable_error_blocks(self):
        result = self.classify(
            [self.root, self.parent, {"pid": 100, "stat_error": "gone"}]
        )
        self.assertEqual(len(result["blocking_read_errors"]), 1)

    def test_observed_r6_missing_stat_without_lifetime_proof_blocks(self):
        missing = {
            "pid": 101,
            "stat_error": repr(FileNotFoundError(errno.ENOENT, "No such file")),
            "stat_errno": errno.ENOENT,
        }
        result = self.classify([self.root, self.parent, missing])
        self.assertEqual(result["terminal_disappearances"], [])
        self.assertEqual(result["blocking_read_errors"], [missing])

    def test_bound_terminal_lifetime_retains_disappearance(self):
        missing = {
            "pid": 101,
            "stat_error": "FileNotFoundError(2, 'No such file or directory')",
            "stat_errno": errno.ENOENT,
            "terminal_key": [101, 12],
            "terminal_proof": "pidfd-signaled",
        }
        result = self.classify([self.root, self.parent, missing])
        self.assertEqual(result["terminal_disappearances"], [missing])
        self.assertEqual(result["read_errors"], [missing])
        self.assertEqual(result["blocking_read_errors"], [])
        self.assertEqual(result["unknown"], [])

    def test_pid_reuse_keeps_missing_stat_blocking(self):
        missing = {
            "pid": 101,
            "stat_error": "gone",
            "stat_errno": errno.ENOENT,
            "terminal_key": [101, 12],
            "terminal_proof": "pidfd-signaled",
        }
        reused = {**self.parent, "starttime": 99}
        result = self.classify([self.root, self.parent, reused, missing])
        self.assertEqual(result["terminal_disappearances"], [])
        self.assertEqual(result["blocking_read_errors"], [missing])

    def test_permission_error_keeps_terminal_annotation_blocking(self):
        denied = {
            "pid": 101,
            "stat_error": "PermissionError(1, 'Operation not permitted')",
            "stat_errno": errno.EPERM,
            "terminal_key": [101, 12],
            "terminal_proof": "pidfd-signaled",
        }
        result = self.classify([self.root, self.parent, denied])
        self.assertEqual(result["blocking_read_errors"], [denied])

    def test_pidfd_bind_error_remains_blocking(self):
        denied = {
            "pid": 101,
            "pidfd_bind_error": "PermissionError(1, 'Operation not permitted')",
        }
        result = self.classify([self.root, self.parent, denied])
        self.assertEqual(result["blocking_read_errors"], [denied])

    def test_pidfd_binding_requires_same_live_lifetime(self):
        with (
            patch.object(runner.os, "pidfd_open", return_value=77),
            patch.object(
                runner, "read_proc", return_value={**self.parent, "starttime": 99}
            ),
            patch.object(runner.os, "close") as close,
        ):
            with self.assertRaisesRegex(RuntimeError, "lifetime changed"):
                runner.bind_pidfd(self.parent)
        close.assert_called_once_with(77)
        with (
            patch.object(runner.os, "pidfd_open", return_value=78),
            patch.object(runner, "read_proc", return_value=self.parent),
            patch.object(runner.select, "select", return_value=([78], [], [])),
            patch.object(runner.os, "close") as close,
        ):
            with self.assertRaisesRegex(RuntimeError, "exited before binding"):
                runner.bind_pidfd(self.parent)
        close.assert_called_once_with(78)

    def test_observer_marks_only_signaled_bound_lifetime(self):
        zombie = {**self.root, "state": "Z", "cmdline": []}
        missing = {
            "pid": 101,
            "stat_error": "FileNotFoundError(2, 'No such file or directory')",
            "stat_errno": errno.ENOENT,
        }

        class CompletedAfterFirstScan:
            pid = 100
            calls = 0

            def poll(self):
                self.calls += 1
                return None if self.calls == 1 else 1

        for signaled in (False, True):
            with (
                self.subTest(signaled=signaled),
                patch.object(
                    runner.os, "listdir", side_effect=[["100", "101"], ["100", "101"]]
                ),
                patch.object(
                    runner,
                    "read_proc",
                    side_effect=[
                        self.root.copy(),
                        self.parent.copy(),
                        zombie.copy(),
                        missing.copy(),
                    ],
                ),
                patch.object(
                    runner, "bind_pidfd", side_effect=lambda rec: rec["pid"] + 10
                ),
                patch.object(
                    runner.select,
                    "select",
                    return_value=([111], [], []) if signaled else ([], [], []),
                ),
                patch.object(runner.os, "close") as close,
            ):
                samples, overran = runner.observe(
                    CompletedAfterFirstScan(), time.monotonic() + 10, self.root.copy()
                )
            result = self.classify(samples)
            self.assertFalse(overran)
            self.assertEqual(bool(result["terminal_disappearances"]), signaled)
            self.assertEqual(bool(result["blocking_read_errors"]), not signaled)
            self.assertEqual(close.call_count, 2)

    def test_bracketed_stat_rejects_identity_change(self):
        def stat(start):
            fields = ["S", "1", "100"] + ["0"] * 16 + [str(start)] + ["0"] * 3
            return "100 (timeout) " + " ".join(fields)

        with (
            patch.object(Path, "read_text", side_effect=[stat(11), stat(99)]),
            patch.object(Path, "read_bytes", return_value=b"timeout\0"),
        ):
            result = runner.read_proc("100")
        self.assertIn("identity_error", result)
        self.assertIsNone(runner.process_key(result))

    def test_completed_observation_after_deadline_is_overrun(self):
        class Completed:
            pid = 100

            def poll(self):
                return 0

        with (
            patch.object(runner.time, "monotonic", return_value=1000),
            patch.object(runner.os, "listdir") as listing,
        ):
            samples, overran = runner.observe(Completed(), 10, self.root)
        self.assertTrue(overran)
        self.assertEqual(samples, [self.root])
        listing.assert_not_called()

    def test_observation_expires_mid_scan(self):
        class Completed:
            pid = 100

            def poll(self):
                return 0

        with (
            patch.object(runner.time, "monotonic", side_effect=[0, 1, 11]),
            patch.object(runner.os, "listdir", return_value=["101", "102"]),
            patch.object(runner, "read_proc", return_value=self.parent),
            patch.object(runner, "bind_pidfd", return_value=110),
            patch.object(runner.os, "close"),
        ):
            samples, overran = runner.observe(Completed(), 10, self.root)
        self.assertTrue(overran)
        self.assertEqual(samples, [self.root])


if __name__ == "__main__":
    unittest.main()
