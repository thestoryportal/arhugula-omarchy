import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from ops.orchestration.continuation import Lease, continue_work
from ops.orchestration.handoff import read_handoff
from ops.orchestration.local import CodexWorker, LocalAdapter, ProcessWorker


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("lit"), "real LIT integration requires lit")
class IsolatedLitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="arhugula-lit-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "repo"
        self.root.mkdir()
        self.run_command(self.root, "git", "init", "-b", "main")
        self.run_command(self.root, "git", "config", "user.name", "Integration Fixture")
        self.run_command(self.root, "git", "config", "user.email", "fixture@example.invalid")
        (self.root / "README.md").write_text("Isolated fixture repository\n")
        self.run_command(self.root, "git", "add", "README.md")
        self.run_command(self.root, "git", "commit", "-m", "baseline")
        self.run_command(self.root, "lit", "init", "--skip-agents", "--skip-hooks")
        self.tree = Path(self.directory.name) / "lane"
        self.run_command(self.root, "git", "worktree", "add", "-b", "fixture-lane", str(self.tree))
        for capability in ("contracts", "fixtures"):
            self.run_command(self.tree, "lit", "new", "--title", "Write harmless " + capability,
                             "--topic", "validation", "--labels", "autonomous-safe,capability:" + capability)
        self.adapter = LocalAdapter(self.tree, ["git", "diff", "--check"])
        self.worker = ProcessWorker([sys.executable, str(ROOT / "tests/fixtures/offline_worker.py")], self.tree, 10)
        self.state = self.adapter.common_dir() / "orchestration"

    def run_command(self, cwd, *args):
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_real_claim_commit_close_handoff_and_fresh_supervisor_resume(self):
        path = self.state / "handoff.json"
        with Lease(self.state / "runner.lock"):
            first = continue_work(self.adapter, self.worker, path, goal="Prove isolated continuity", limit=1)
        self.assertEqual(first["stop_reason"], "ticket-limit", first)
        self.assertEqual(first["model"], "gpt-6-astra")
        self.assertEqual(first["effort"], "high")
        self.assertIsNotNone(first["next_ticket"])
        prior = read_handoff(path)
        # A fresh Python process reads durable context, not conversation memory.
        fresh = LocalAdapter(self.tree, ["git", "diff", "--check"])
        config = Path(self.directory.name) / "trusted-config.json"
        config.write_text(json.dumps({"goal": prior["goal"], "worker_argv": self.worker.argv,
                                      "verify_argv": ["git", "diff", "--check"]}))
        output = self.run_command(ROOT, sys.executable, "-m", "ops.orchestration.runner", "run",
                                  "--cwd", str(self.tree), "--config", str(config), "--tickets", "1")
        second = json.loads(output)
        self.assertEqual(second["stop_reason"], "ticket-limit", second)
        self.assertEqual(second["model"], "gpt-5.6-terra")
        self.assertEqual(second["effort"], "medium")
        self.assertEqual(len(second["completed_work"]), 2)
        states = {i["status"] for i in fresh.export()["issues"]}
        self.assertEqual(states, {"closed"})
        fixture = json.loads((self.tree / (second["active_ticket"] + ".json")).read_text())
        self.assertEqual(fixture["prior_completed"], prior["completed_work"])
        self.assertEqual(self.run_command(self.tree, "git", "status", "--porcelain").strip(), "")
        self.assertEqual(len(self.run_command(self.tree, "git", "log", "--oneline").splitlines()), 3)

    def test_real_foreign_worktree_changes_and_hil_never_start_worker(self):
        (self.root / "foreign.txt").write_text("foreign session")
        with Lease(self.state / "runner.lock"):
            stopped = continue_work(self.adapter, self.worker, self.state / "handoff.json", goal="Safety", limit=1)
        self.assertEqual(stopped["stop_reason"], "dirty-tree-conflict")
        self.assertFalse(list(self.tree.glob("*.json")))
        self.assertEqual({i["status"] for i in self.adapter.export()["issues"]}, {"open"})
        selected = next(i for i in self.adapter.export()["issues"] if i["title"].endswith("contracts"))
        self.run_command(self.tree, "lit", "label", "add", selected["id"], "hil-required")
        with Lease(self.state / "runner.lock"):
            stopped = continue_work(self.adapter, self.worker, self.state / "handoff.json", goal="Safety", limit=1)
        self.assertEqual(stopped["stop_reason"], "hil-required")
        self.assertEqual((self.root / "foreign.txt").read_text(), "foreign session")

    def test_routed_codex_invocations_complete_two_real_tickets_offline(self):
        worker = CodexWorker(self.tree, 10, [sys.executable, str(ROOT / "tests/fixtures/offline_codex.py")])
        with Lease(self.state / "runner.lock"):
            result = continue_work(self.adapter, worker, self.state / "handoff.json", goal="Codex transport", limit=2)
        self.assertEqual(result["stop_reason"], "ticket-limit", result)
        self.assertIn("gpt-6-astra", result["completed_work"][0])
        self.assertIn('model_reasoning_effort="high"', result["completed_work"][0])
        self.assertIn("gpt-5.6-terra", result["completed_work"][1])
        self.assertIn('model_reasoning_effort="medium"', result["completed_work"][1])
        self.assertEqual({i["status"] for i in self.adapter.export()["issues"]}, {"closed"})
        self.assertEqual(self.run_command(self.tree, "git", "status", "--porcelain").strip(), "")
