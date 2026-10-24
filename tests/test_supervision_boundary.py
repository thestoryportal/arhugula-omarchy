"""WO-U22 fixtures: the retained process-group capture against WS-14 cases.

Each case records what ops.orchestration.artifacts proves and which gap stays a
retained obligation in docs/orchestration/workflow-readiness.md (Supervision
boundary decision, O1-O3). A future boundary flips a gap assertion only with evidence.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from ops.orchestration.processes import process_stats

ROOT = Path(__file__).resolve().parents[1]

# Announces "pid start" atomically, then idles as a stand-in for a live resource.
SLEEPER = """
import os, sys, time
from pathlib import Path
start = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
path = Path(sys.argv[1])
path.with_suffix('.tmp').write_text(f'{os.getpid()} {start}')
path.with_suffix('.tmp').rename(path)
time.sleep(60)
"""

# Product that leaves one child behind, inside or outside its own session.
SPAWN = f"""
import subprocess, sys, time
from pathlib import Path
escape, path = sys.argv[1] == 'escape', Path(sys.argv[2])
subprocess.Popen([sys.executable, '-c', {SLEEPER!r}, str(path)], start_new_session=escape)
while not path.exists():
    time.sleep(0.01)
"""


def alive(handle):
    return any((s.pid, s.start) == handle and s.state != "Z" for s in process_stats())


class SupervisionBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def announced(self, name):
        path = self.root / name
        deadline = time.monotonic() + 10
        while not path.exists():
            self.assertLess(time.monotonic(), deadline, f"{name} was never announced")
            time.sleep(0.01)
        pid, start = path.read_text().split()
        handle = (int(pid), start)

        def reclaim():
            # [LAW:single-enforcer] Fixture cleanup signals only the exact
            # pid+start identity it recorded, never a reused pid or a name.
            if alive(handle):
                os.kill(handle[0], signal.SIGKILL)

        self.addCleanup(reclaim)
        return handle

    def capture(self, *argv):
        from ops.orchestration.artifacts import capture

        store = self.root / "store"
        return capture([sys.executable, "-c", *argv], ROOT, root=store, timeout=10)

    def test_product_survivor_fails_before_supervisor_cleanup(self):
        result = self.capture(SPAWN, "stay", str(self.root / "survivor"))
        survivor = self.announced("survivor")

        # The survivor existed at the product checkpoint; the failure is sealed
        # in the receipt even though owned group cleanup then removed it.
        self.assertEqual((result["terminal"], result["exit"]), ("descendants_active", 125))
        self.assertFalse(alive(survivor))

    def test_driver_death_has_no_product_cleanup_go(self):
        store = self.root / "store"
        driver = subprocess.Popen(
            [sys.executable, "-m", "ops.orchestration.artifacts", "--root", str(store),
             "--timeout", "30", "--", sys.executable, "-c", SLEEPER, str(self.root / "product")],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.addCleanup(driver.wait)
        product = self.announced("product")
        driver.kill()
        driver.wait()

        # No receipt means no product GO; raw evidence survives unsealed.
        self.assertEqual(list(store.glob("*/receipt.json")), [])
        self.assertEqual(len(list(store.glob("*/stdout.log"))), 1)
        # O2: nothing outside the dead driver owns the product group, so it
        # outlives the driver until an external owner reclaims it.
        self.assertTrue(alive(product))

    def test_external_handle_owner_mismatch_preserves_sentinel(self):
        sentinel_process = subprocess.Popen(
            [sys.executable, "-c", SLEEPER, str(self.root / "sentinel")],
            start_new_session=True,
        )
        self.addCleanup(sentinel_process.wait)
        sentinel = self.announced("sentinel")

        result = self.capture(SPAWN, "escape", str(self.root / "escaped"))
        escaped = self.announced("escaped")

        # Cleanup never touches a handle outside its own process group.
        self.assertTrue(alive(sentinel))
        self.assertTrue(alive(escaped))
        # O1: the escaped session is unattributed, so the receipt reports a clean
        # exit instead of retaining a failure for an unowned survivor.
        self.assertEqual((result["terminal"], result["exit"]), ("exited", 0))


if __name__ == "__main__":
    unittest.main()
