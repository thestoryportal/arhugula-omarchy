"""Generated-cache reclamation must preserve live and unrelated work."""
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


class TempSpaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        (self.proc / str(os.getpid())).symlink_to(Path("/proc") / str(os.getpid()), target_is_directory=True)

    def cache(self, number=1, *, age=10800):
        path = self.root / f"dolt-gitblobstore-materialized-{number}"
        path.mkdir()
        blob = path / ("a" * 40 + "-1")
        blob.write_bytes(b"x" * 8192)
        stamp = time.time() - age
        os.utime(blob, (stamp, stamp))
        os.utime(path, (stamp, stamp))
        return path

    def clean(self, **kwargs):
        from ops.orchestration.temp_space import reclaim
        return reclaim(self.root, minimum_free=sys.maxsize,
                       target_free=sys.maxsize, proc_root=self.proc, **kwargs)

    def test_pressure_removes_old_generated_cache_and_preserves_other_files(self):
        old = self.cache()
        log = self.root / "review.log"
        log.write_text("protected evidence")
        result = self.clean()
        self.assertFalse(old.exists())
        self.assertEqual(log.read_text(), "protected evidence")
        self.assertEqual(result["removed"], [str(old)])

    def test_recent_cache_is_preserved(self):
        recent = self.cache(age=60)
        self.clean()
        self.assertTrue(recent.exists())

    def test_live_open_blob_is_preserved(self):
        live = self.cache()
        with next(live.iterdir()).open("rb"):
            result = self.clean()
        self.assertTrue(live.exists())
        self.assertEqual(result["removed"], [])

    def test_live_working_directory_is_preserved(self):
        live = self.cache()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=live)
        (self.proc / str(child.pid)).symlink_to(Path("/proc") / str(child.pid), target_is_directory=True)
        try:
            self.clean()
            self.assertTrue(live.exists())
        finally:
            child.terminate()
            child.wait()

    def test_symlink_cache_and_symlink_blob_are_preserved(self):
        external = self.root / "protected"
        external.mkdir()
        (external / "evidence").write_text("retain")
        link = self.root / "dolt-gitblobstore-materialized-1"
        link.symlink_to(external, target_is_directory=True)
        cache = self.cache(2)
        next(cache.iterdir()).unlink()
        (cache / ("a" * 40 + "-1")).symlink_to(external / "evidence")
        self.clean()
        self.assertTrue(link.is_symlink())
        self.assertTrue(cache.exists())
        self.assertEqual((external / "evidence").read_text(), "retain")

    def test_unknown_cache_content_is_preserved(self):
        cache = self.cache()
        (cache / "worktree-not-a-blob").write_text("protected")
        self.clean()
        self.assertTrue(cache.exists())

    def test_enough_free_space_does_not_remove_cache(self):
        from ops.orchestration.temp_space import reclaim
        cache = self.cache()
        result = reclaim(self.root, minimum_free=1, target_free=2)
        self.assertTrue(cache.exists())
        self.assertEqual(result["removed"], [])

    def test_invalid_thresholds_fail_before_cleanup(self):
        from ops.orchestration.temp_space import reclaim
        cache = self.cache()
        with self.assertRaises(ValueError):
            reclaim(self.root, minimum_free=2, target_free=1)
        self.assertTrue(cache.exists())

    def test_exec_routes_child_scratch_to_disk_and_preserves_exit(self):
        scratch = self.root / "scratch"
        output = self.root / "observed.json"
        script = ("import json,os,tempfile,sys; "
                  "p=tempfile.mkdtemp(); "
                  "open(sys.argv[1],'w').write(json.dumps({'tmp':os.environ.get('TMPDIR'),'created':p})); "
                  "sys.exit(7)")
        launcher = ("from pathlib import Path; import sys; "
                    "from ops.orchestration.temp_space import execute; "
                    "sys.exit(execute(sys.argv[2:], Path(sys.argv[1]), tmp_root=Path(sys.argv[1]).parent))")
        result = subprocess.run([sys.executable, "-c", launcher, str(scratch),
                                 sys.executable, "-c", script, str(output)]).returncode
        observed = json.loads(output.read_text())
        self.assertEqual(result, 7)
        self.assertEqual(observed["tmp"], str(scratch))
        self.assertEqual(Path(observed["created"]).parent, scratch)

    def test_exec_preserves_pid_and_graceful_sigint(self):
        ready = self.root / "signal-ready"
        launcher = ("from pathlib import Path; import sys; "
                    "from ops.orchestration.temp_space import execute; "
                    "sys.exit(execute(sys.argv[2:], Path(sys.argv[1]), tmp_root=Path(sys.argv[1]).parent))")
        script = ("import os,signal,sys,time; from pathlib import Path; "
                  "signal.signal(signal.SIGINT,lambda *_:(time.sleep(0.5),sys.exit(42))); "
                  "p=Path(sys.argv[1]); t=p.with_suffix('.tmp'); t.write_text(str(os.getpid())); t.rename(p); time.sleep(30)")
        child = subprocess.Popen([sys.executable, "-c", launcher, str(self.root / "scratch"),
                                  sys.executable, "-c", script, str(ready)], start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline and child.poll() is None:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            os.killpg(child.pid, signal.SIGINT)
            self.assertEqual(child.wait(timeout=5), 42)
            self.assertEqual(int(ready.read_text()), child.pid)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()

    def test_vanished_generated_cache_is_skipped(self):
        from ops.orchestration.temp_space import Cache
        self.assertIsNone(Cache.parse(self.root / "dolt-gitblobstore-materialized-99", time.time()))

    def test_exec_records_tmp_cleanup_failure_and_still_runs_command(self):
        scratch = self.root / "scratch"
        link = self.root / "tmp-link"
        link.symlink_to(self.root, target_is_directory=True)
        output = self.root / "ran"
        launcher = ("from pathlib import Path; import sys; "
                    "from ops.orchestration.temp_space import execute; "
                    "execute(sys.argv[3:], Path(sys.argv[1]), tmp_root=Path(sys.argv[2]))")
        result = subprocess.run([sys.executable, "-c", launcher, str(scratch), str(link),
                                 sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).touch()", str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())
        receipt = json.loads((scratch.parent / "space-receipt.json").read_text())
        self.assertIn("error", receipt["roots"][0])
        self.assertIn("temporary_space_error", result.stderr)

    def test_unreadable_process_defers_cleanup(self):
        cache = self.cache()
        proc = self.proc / "100"
        proc.mkdir()
        (proc / "comm").write_text("python")
        (proc / "cmdline").write_bytes(b"python\x00")
        (proc / "cwd").symlink_to(self.root)
        (proc / "fd").mkdir(mode=0)
        try:
            result = self.clean()
            self.assertTrue(cache.exists())
            self.assertIn(100, result["deferred_producers"])
        finally:
            (proc / "fd").chmod(0o700)

    def test_live_producer_defers_without_making_cache_recent(self):
        cache = self.cache()
        proc = self.proc / "100"
        proc.mkdir()
        (proc / "comm").write_text("dolt")
        (proc / "cmdline").write_bytes(b"dolt\x00")
        (proc / "cwd").symlink_to(self.root)
        (proc / "fd").mkdir()
        (proc / "maps").write_text("")
        result = self.clean()
        self.assertEqual(result["deferred_producers"], [100])
        (proc / "comm").write_text("python")
        self.clean()
        self.assertFalse(cache.exists())

    def test_failed_delete_quarantines_cache_for_next_maintenance(self):
        cache = self.cache()
        with patch("shutil.rmtree", side_effect=OSError("delete failed")):
            with self.assertRaises(OSError):
                self.clean()
        self.assertFalse(cache.exists())
        tombstones = list(self.root.glob(".arhugula-dolt-reclaim-*"))
        self.assertEqual(len(tombstones), 1)
        self.clean()
        self.assertFalse(tombstones[0].exists())

    def test_timer_detects_changed_installed_files(self):
        from ops.orchestration.temp_space import main
        install = self.root / "install"
        install.mkdir(mode=0o700)
        wrapper = install / "wrapper"
        original = b"reviewed wrapper"
        wrapper.write_bytes(original)
        (install / "installation.json").write_text(json.dumps({str(wrapper): hashlib.sha256(original).hexdigest()}))
        wrapper.write_text("unreviewed update")
        with patch.object(sys, "argv", ["temp-space", "maintain"]):
            self.assertEqual(main(install), 78)
        receipt = json.loads((install / "space-receipt.json").read_text())
        self.assertIn("integrity_error", receipt)

    def test_exec_preserves_signal_exit(self):
        launcher = ("from pathlib import Path; import sys; "
                    "from ops.orchestration.temp_space import execute; "
                    "execute(sys.argv[2:], Path(sys.argv[1]), tmp_root=Path(sys.argv[1]).parent)")
        result = subprocess.run([sys.executable, "-c", launcher, str(self.root / "scratch"),
                                 sys.executable, "-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"])
        self.assertEqual(result.returncode, -signal.SIGTERM)

    def test_tmpfs_scratch_is_rejected(self):
        from ops.orchestration.temp_space import scratch_directory
        if not Path("/dev/shm").is_dir():
            self.skipTest("tmpfs is unavailable")
        with tempfile.TemporaryDirectory(dir="/dev/shm") as path:
            with self.assertRaises(ValueError):
                scratch_directory(path)

    def test_timer_publishes_both_storage_reports(self):
        from ops.orchestration.temp_space import main
        install = self.root / "install"
        install.mkdir(mode=0o700)
        wrapper = install / "wrapper"
        original = b"reviewed wrapper"
        wrapper.write_bytes(original)
        (install / "installation.json").write_text(json.dumps({str(wrapper): hashlib.sha256(original).hexdigest()}))
        with patch.object(sys, "argv", ["temp-space", "maintain"]):
            self.assertEqual(main(install), 0)
        receipt = json.loads((install / "space-receipt.json").read_text())
        self.assertEqual([r["root"] for r in receipt["roots"]], ["/tmp", str(install / "tmp")])

    def test_closed_fd_does_not_drop_other_references(self):
        from ops.orchestration.temp_space import references
        proc = self.proc / "100"
        proc.mkdir()
        (proc / "comm").write_text("python")
        (proc / "cmdline").write_bytes(b"python\x00")
        (proc / "cwd").symlink_to(self.root)
        (proc / "fd").mkdir()
        missing = proc / "fd" / "1"
        missing.symlink_to(self.root)
        (proc / "maps").write_text("1 2 3 4 5 /protected-mapped-file\n")
        readlink = os.readlink
        def raced_readlink(path, *args, **kwargs):
            if Path(path) == missing:
                raise FileNotFoundError("descriptor closed")
            return readlink(path, *args, **kwargs)
        with patch("os.readlink", side_effect=raced_readlink):
            refs, _, _ = references(self.proc)
        self.assertIn("/protected-mapped-file", refs)

    def test_exec_rejects_symlink_scratch(self):
        from ops.orchestration.temp_space import execute
        target = self.root / "target"
        target.mkdir()
        scratch = self.root / "scratch"
        scratch.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            execute([sys.executable, "-c", "pass"], scratch)

    def test_long_lived_command_does_not_serialize_other_commands(self):
        install = self.root / "installed"
        ready = self.root / "ready"
        launcher = ("from pathlib import Path; import sys; "
                    "from ops.orchestration.temp_space import execute; "
                    "execute(sys.argv[2:], Path(sys.argv[1]))")
        prefix = [sys.executable, "-c", launcher, str(install)]
        child = subprocess.Popen(prefix + [sys.executable, "-c",
            "from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30)", str(ready)],
            start_new_session=True)
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline and child.poll() is None:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "long-lived child did not start")
            try:
                result = subprocess.run(prefix + [sys.executable, "-c", "pass"], timeout=3)
            except subprocess.TimeoutExpired:
                self.fail("long-lived command blocked an independent invocation")
            self.assertEqual(result.returncode, 0)
        finally:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            child.wait()


if __name__ == "__main__":
    unittest.main()
