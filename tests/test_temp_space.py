"""Generated-cache reclamation must preserve live and unrelated work."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class TempSpaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

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
                       target_free=sys.maxsize, **kwargs)

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
        from ops.orchestration.temp_space import execute
        scratch = self.root / "scratch"
        output = self.root / "observed.json"
        script = ("import json,os,tempfile,sys; "
                  "p=tempfile.mkdtemp(); "
                  "open(sys.argv[1],'w').write(json.dumps({'tmp':os.environ.get('TMPDIR'),'created':p})); "
                  "sys.exit(7)")
        result = execute([sys.executable, "-c", script, str(output)], scratch,
                         tmp_root=self.root / "separate-tmp")
        observed = json.loads(output.read_text())
        self.assertEqual(result, 7)
        self.assertEqual(observed["tmp"], str(scratch))
        self.assertEqual(Path(observed["created"]).parent, scratch)

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
                    "from ops.orchestration.temp_space import main; "
                    "sys.exit(main(Path(sys.argv.pop(1))))")
        prefix = [sys.executable, "-c", launcher, str(install), "exec", "--"]
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
