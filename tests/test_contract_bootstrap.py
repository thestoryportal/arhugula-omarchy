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
            # Exercise packaged schema resources and the whole foundation outside
            # the checkout, not merely a health handler that imports no codecs.
            probe = """
import json, sys
sys.path.insert(0, sys.argv[1])
from runtime.contracts import decode
from runtime.core import ControlPlane, Outcome
from runtime.journal import SQLiteJournal
records = {item['kind']: decode(item) for item in json.load(sys.stdin)}
with SQLiteJournal('probe.sqlite') as journal:
    plane = ControlPlane([records['capability']], records['policy'],
                         lambda command: Outcome('success'), journal,
                         profile=records['profile'])
    assert plane.dispatch(records['command']).status == 'success'
    assert len(journal.read()) == 2
print('packaged-dispatch-ok')
"""
            result = subprocess.run([sys.executable, "-I", "-c", probe, str(artifact)],
                                    input=Path("tests/fixtures/contracts-v1.json").read_text(),
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "packaged-dispatch-ok")

    def test_unknown_command_does_not_fall_through_to_execution(self):
        result = subprocess.run([sys.executable, "-m", "runtime", "exec", "touch", "/tmp/unrequested"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
