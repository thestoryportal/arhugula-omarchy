import json
from pathlib import Path
import sys
import tempfile
import unittest

from ops.orchestration.local import CodexWorker
from test_handoff import record


class CodexWorkerTests(unittest.TestCase):
    def test_each_invocation_uses_current_assignment_and_receipt_file(self):
        executable = str(Path(__file__).with_name("fixtures") / "offline_codex.py")
        with tempfile.TemporaryDirectory() as directory:
            worker = CodexWorker(directory, 10, [sys.executable, executable])
            for model, effort in [("gpt-6-astra", "high"), ("gpt-5.6-terra", "medium")]:
                context = {**record(directory), "model": model, "effort": effort,
                           "supervisor": "Implement only; supervisor owns LIT/Git transitions."}
                result = worker(context)
                self.assertIn(model, result["summary"])
                capture = json.loads((Path(directory) / "capture.json").read_text())
                self.assertEqual(capture["context"], context)
                self.assertIn(f'model_reasoning_effort="{effort}"', capture["argv"])
                self.assertIn("--output-schema", capture["argv"])
                self.assertEqual(capture["argv"][-1], "-")

    def test_large_context_travels_over_stdin_not_one_argv_argument(self):
        executable = str(Path(__file__).with_name("fixtures") / "offline_codex.py")
        with tempfile.TemporaryDirectory() as directory:
            context = {**record(directory), "supervisor": "worker only", "goal": "x" * 150000}
            result = CodexWorker(directory, 10, [sys.executable, executable])(context)
            self.assertEqual(result["files"], ["capture.json"])
