from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime.voice.menu import OmarchyMenuExecutor
from ops.voice_smoke import build_plane, smoke


class MenuSmokeTests(unittest.TestCase):
    def test_dry_run_is_default_and_does_not_launch_processes(self):
        with patch("runtime.voice.menu.subprocess.run", side_effect=AssertionError("live launch")):
            result, journal = smoke()
            self.assertEqual(result.status, "success")
            self.assertEqual(result.output["mode"], "simulation")
            self.assertEqual(len(journal.read()), 2)
            journal.close()

    def test_exact_menu_argv_only_and_second_smoke_id_cannot_execute(self):
        with tempfile.TemporaryDirectory() as directory, patch("runtime.voice.menu.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            path = Path(directory) / "smoke.sqlite"
            result, journal = smoke(live=True, journal_path=path)
            self.assertEqual(result.status, "success")
            journal.close()
            result, journal = smoke(live=True, journal_path=path)
            self.assertEqual(result.status, "blocked")
            journal.close()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], ["/usr/share/omarchy/bin/omarchy", "menu", "summon", "root"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_timeout_and_nonzero_exit_are_uncertain_not_retried(self):
        for effect in (subprocess.TimeoutExpired("menu", 5), subprocess.CompletedProcess([], 1, "", "private stderr")):
            with patch("runtime.voice.menu.subprocess.run") as run:
                if isinstance(effect, Exception):
                    run.side_effect = effect
                else:
                    run.return_value = effect
                plane, command, journal = build_plane(OmarchyMenuExecutor())
                result = plane.dispatch(command)
                self.assertEqual(result.status, "uncertain")
                self.assertNotIn("private", result.error.message)
                self.assertEqual(plane.dispatch(command).status, "blocked")
                self.assertEqual(run.call_count, 1)
                journal.close()

    def test_executor_rejects_foreign_capabilities_arguments_and_live_without_journal(self):
        from dataclasses import replace
        plane, command, journal = build_plane(OmarchyMenuExecutor())
        with patch("runtime.voice.menu.subprocess.run") as run:
            for changed in (replace(command, capability_id="shell.run"), replace(command, arguments={"name": "system.shutdown"})):
                self.assertEqual(OmarchyMenuExecutor()(changed).status, "failed")
            run.assert_not_called()
        journal.close()
        with self.assertRaises(ValueError):
            smoke(live=True)

    def test_cli_default_is_simulation(self):
        result = subprocess.run([sys.executable, "-m", "ops.voice_smoke"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"mode": "simulation"', result.stdout)
