import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class BootstrapTests(unittest.TestCase):
    def test_health_is_versioned_and_cannot_execute_external_actions(self):
        result = subprocess.run([sys.executable, "-m", "runtime", "health"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"version": 1, "service": "control-plane",
                         "state": "ok", "mode": "simulation", "external_execution": False})

    def test_zipapp_runs_outside_checkout_without_installed_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "control-plane.pyz"
            built = subprocess.run([sys.executable, "-m", "ops.build", str(artifact)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([sys.executable, "-I", str(artifact), "health"], cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["mode"], "simulation")

    def test_unknown_command_does_not_fall_through_to_execution(self):
        result = subprocess.run([sys.executable, "-m", "runtime", "exec", "touch", "/tmp/unrequested"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
