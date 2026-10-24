import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ArtifactTests(unittest.TestCase):
    def capture(self, script, timeout=5):
        from ops.orchestration.artifacts import capture

        return capture(
            [sys.executable, "-c", script], Path.cwd(), root=self.root, timeout=timeout
        )

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_process_group_exiting_before_cleanup_preserves_success(self):
        from unittest.mock import patch

        # The census sees a descendant; it exits before the kill boundary.
        with patch("ops.orchestration.artifacts.group_active", side_effect=[True, False]), patch(
            "ops.orchestration.artifacts.os.killpg", side_effect=ProcessLookupError(3, "No such process")
        ):
            result = self.capture("print('complete')")
        self.assertEqual((result["exit"], result["terminal"]), (0, "exited"))
        self.assertEqual(Path(result["stdout"]["path"]).read_text(), "complete\n")
        self.assertEqual(json.loads(Path(result["receipt"]).read_text()), result)

    def test_cleanup_permission_error_remains_loud(self):
        from unittest.mock import patch

        with patch("ops.orchestration.artifacts.group_active", return_value=True), patch(
            "ops.orchestration.artifacts.os.killpg", side_effect=PermissionError(1, "Operation not permitted")
        ), self.assertRaises(PermissionError):
            self.capture("print('complete')")

    def test_large_output_is_complete_on_disk_and_summary_is_bounded(self):
        result = self.capture(
            "import sys; print('x'*2000000); print('ERROR useful failure',file=sys.stderr); sys.exit(7)"
        )
        self.assertEqual(result["exit"], 7)
        self.assertEqual(Path(result["stdout"]["path"]).stat().st_size, 2000001)
        self.assertLess(len(json.dumps(result)), 10000)
        self.assertIn("ERROR useful failure", result["summary"])
        self.assertEqual(
            result["stdout"]["sha256"],
            hashlib.sha256(b"x" * 2000000 + b"\n").hexdigest(),
        )
        self.assertEqual(json.loads(Path(result["receipt"]).read_text()), result)

    def test_timeout_has_terminal_receipt_and_preserves_raw_output(self):
        from unittest.mock import patch
        import time

        communicate = subprocess.Popen.communicate

        def after_output_ready(process, input=None, timeout=None):
            deadline = time.monotonic() + 5
            while not any(
                p.read_bytes() == b"started\n" for p in self.root.glob("*/stdout.log")
            ):
                if time.monotonic() >= deadline:
                    raise AssertionError("fixture did not publish startup output")
                time.sleep(0.01)
            return communicate(process, input=input, timeout=timeout)

        with patch.object(subprocess.Popen, "communicate", after_output_ready):
            result = self.capture(
                "import time; print('started',flush=True); time.sleep(20)", 0.1
            )
        self.assertEqual(result["terminal"], "timeout")
        self.assertEqual(result["exit"], 124)
        self.assertEqual(Path(result["stdout"]["path"]).read_text(), "started\n")

    def test_missing_mac_mount_refuses_before_command_execution(self):
        from ops.orchestration.artifacts import require_mac_share

        with self.assertRaisesRegex(ValueError, "Mac share"):
            require_mac_share("1 2 3 / / rw - ext4 /dev/vda rw\n")
        with self.assertRaisesRegex(ValueError, "Mac share"):
            require_mac_share("1 2 3 / /mnt/mac ro - 9p mac rw\n")

    def test_symlink_store_cannot_redirect_logs(self):
        from ops.orchestration.artifacts import capture

        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            capture(["true"], Path.cwd(), root=link)

    def test_launch_failure_is_recorded_without_success_receipt(self):
        with self.assertRaises(FileNotFoundError):
            self.capture_command(["/nonexistent/buford-command"])
        receipts = list(self.root.glob("*/receipt.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(
            json.loads(receipts[0].read_text())["terminal"], "launch_failed"
        )

    def capture_command(self, argv):
        from ops.orchestration.artifacts import capture

        return capture(argv, Path.cwd(), root=self.root)

    def test_unsupported_fsync_cannot_publish_a_receipt(self):
        from ops.orchestration.artifacts import capture
        from unittest.mock import patch

        with patch("os.fsync", side_effect=OSError("disk failed")):
            with self.assertRaisesRegex(OSError, "disk failed"):
                capture(["true"], Path.cwd(), root=self.root)
        self.assertEqual(list(self.root.glob("*/receipt.json")), [])

    def test_final_directory_fsync_failure_leaves_no_success_receipt(self):
        from ops.orchestration import records
        from ops.orchestration.artifacts import capture
        from unittest.mock import patch

        original = records.sync_directory

        def fail_final(path):
            # Only the sync acknowledging the replaced receipt fails.
            if (Path(path) / "receipt.json").exists():
                raise OSError("final publication sync failed")
            return original(path)

        with patch("ops.orchestration.records.sync_directory", side_effect=fail_final):
            with self.assertRaisesRegex(OSError, "final publication sync failed"):
                capture(["true"], Path.cwd(), root=self.root)
        self.assertEqual(list(self.root.glob("*/receipt.json")), [])
        self.assertEqual(len(list(self.root.glob("*/receipt.json.publication-uncertain"))), 1)

    def test_parent_exit_cannot_publish_success_with_owned_descendants_running(self):
        result = self.capture(
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print('parent done')"
        )
        self.assertEqual(result["terminal"], "descendants_active")
        self.assertEqual(result["exit"], 125)


class DurableStoreTests(unittest.TestCase):
    """WS-15 §17.2: the store is proved before execution and stays the evidence home."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.marker = self.root / "command-ran"

    def mountinfo(self, line):
        path = self.root / "mountinfo"
        path.write_text(line)
        return path

    def capture_default(self, mountinfo, argv):
        from unittest.mock import patch
        from ops.orchestration import artifacts

        store = self.root / "share" / "arhugula-artifacts"
        with patch.object(artifacts, "MOUNTINFO", mountinfo), patch.object(
            artifacts, "DEFAULT_ROOT", store
        ):
            return artifacts.capture(argv, Path.cwd(), root=store)

    def touch_marker(self):
        return [sys.executable, "-c", f"open({str(self.marker)!r}, 'w')"]

    def test_absent_or_read_only_share_refuses_before_the_command_runs(self):
        for line in (
            "1 2 3 / / rw - ext4 /dev/vda rw\n",
            "1 2 3 / /mnt/mac ro - 9p mac rw\n",
        ):
            with self.subTest(line=line):
                with self.assertRaisesRegex(ValueError, "Mac share"):
                    self.capture_default(self.mountinfo(line), self.touch_marker())
                self.assertFalse(self.marker.exists())
                # No fallback store was created on guest disk either.
                self.assertFalse((self.root / "share").exists())

    def test_default_store_receipt_names_the_share(self):
        result = self.capture_default(
            self.mountinfo("1 2 3 / /mnt/mac rw - 9p mac rw\n"), ["true"]
        )
        self.assertEqual(result["store"], "mac_share")

    def test_explicit_root_is_marked_test_only(self):
        from ops.orchestration.artifacts import capture

        result = capture(["true"], Path.cwd(), root=self.root / "explicit")
        self.assertEqual(result["store"], "test_only")

    def test_store_lost_mid_run_publishes_no_receipt_anywhere(self):
        from ops.orchestration.artifacts import capture

        store = self.root / "store"
        lose_store = (
            "import pathlib,shutil; print('partial',flush=True); "
            f"shutil.rmtree(next(pathlib.Path({str(store)!r}).glob('run-*')))"
        )
        with self.assertRaises(OSError):
            capture([sys.executable, "-c", lose_store], Path.cwd(), root=store)
        self.assertEqual(list(store.rglob("receipt.json*")), [])
        self.assertEqual(list(store.glob("run-*")), [])


class BoundedReceiptTests(unittest.TestCase):
    """WS-15 §17.2: at most 16 KiB returned; every material finding stays retrievable."""

    LIMIT = 16 * 1024

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def capture(self, argv):
        from ops.orchestration.artifacts import capture

        return capture(argv, Path.cwd(), root=self.root)

    def retrieve(self, binding):
        from ops.orchestration.assignment_packet import Artifact, assemble, read_slice

        artifact = Artifact(binding["path"], binding["bytes"], binding["sha256"], "capture", "findings", "1")
        offsets = range(0, artifact.byte_length, 16 * 1024)
        return assemble(artifact, [read_slice(artifact, offset) for offset in offsets])

    def test_receipt_stays_bounded_for_long_argv_and_escaped_output(self):
        argument = "\u00e9" * 40000
        noisy = "import sys\nfor n in range(20000): print('ERROR \\x01\\u00e9\\U0001f600', n, file=sys.stderr)"
        result = self.capture([sys.executable, "-c", noisy, argument])
        self.assertLessEqual(len(json.dumps(result).encode()), self.LIMIT)
        self.assertEqual(json.loads(Path(result["receipt"]).read_text()), result)
        argv = json.loads(self.retrieve(result["argv"]))
        self.assertEqual(argv[-1], argument)
        self.assertTrue(result["summary_truncated"])

    def test_findings_beyond_the_summary_are_flagged_and_complete_on_disk(self):
        result = self.capture(
            [sys.executable, "-c", "for n in range(3000): print(f'ERROR failure {n}')"]
        )
        self.assertTrue(result["summary_truncated"])
        self.assertEqual(result["findings_count"], 3000)
        self.assertIn("ERROR failure 0\n", result["summary"])
        lines = self.retrieve(result["findings"]).decode().splitlines()
        self.assertEqual(lines, [f"ERROR failure {n}" for n in range(3000)])

    def test_small_finding_set_is_shown_whole(self):
        result = self.capture(
            [sys.executable, "-c", "print('noise'); print('Ran 3 tests'); print('OK')"]
        )
        self.assertFalse(result["summary_truncated"])
        self.assertEqual(result["findings_count"], 2)
        self.assertTrue(result["summary"].startswith("Ran 3 tests\nOK\n"))
