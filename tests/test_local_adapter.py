from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.orchestration.local import LocalAdapter, ProcessWorker
from ops.orchestration.continuation import Stop


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


class LocalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "base.txt").write_text("base\n")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-m", "baseline")
        self.tree = Path(self.directory.name) / "worktree"
        git(self.root, "worktree", "add", "-b", "isolated", str(self.tree))
        self.adapter = LocalAdapter(self.tree, ["git", "diff", "--check"])

    def test_clean_inspection_and_commit_only_declared_files(self):
        baseline = self.adapter.inspect()
        self.assertEqual(baseline["branch"], "isolated")
        (self.tree / "new file.txt").write_text("content\n")
        self.adapter.inspect(expected_head=baseline["head"], allowed=["new file.txt"])
        commit = self.adapter.commit("unit-1", ["new file.txt"])
        self.assertEqual(git(self.tree, "rev-parse", "HEAD"), commit)
        self.assertEqual(git(self.tree, "status", "--porcelain"), "")
        self.assertEqual(git(self.tree, "show", "HEAD:new file.txt"), "content")

    def test_other_worktree_dirty_stops_even_when_own_tree_is_clean(self):
        (self.root / "foreign.txt").write_text("another agent")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            self.adapter.inspect()

    def test_unexpected_file_or_head_stops(self):
        (self.tree / "foreign.txt").write_text("another agent")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            self.adapter.inspect(allowed=["expected.txt"])
        with self.assertRaisesRegex(Stop, "git-head-changed"):
            self.adapter.inspect(expected_head="wrong", allowed=["foreign.txt"])

    def test_deletion_and_symlink_changes_stop(self):
        (self.tree / "base.txt").unlink()
        with self.assertRaisesRegex(Stop, "destructive"):
            self.adapter.inspect(allowed=["base.txt"])
        git(self.tree, "restore", "base.txt")
        (self.tree / "link").symlink_to(self.root / "base.txt")
        with self.assertRaisesRegex(Stop, "symlink-change"):
            self.adapter.inspect(allowed=["link"])

    def test_real_verification_failure_carries_exit_status(self):
        adapter = LocalAdapter(self.tree, ["git", "rev-parse", "--verify", "refs/heads/missing"])
        passed, evidence = adapter.verify()
        self.assertFalse(passed)
        self.assertIn("exit=128", evidence)

    def test_process_worker_receives_json_context_without_shell(self):
        worker = ProcessWorker(["python3", "-c", "import json,sys; c=json.load(sys.stdin); print(json.dumps({'files':['new.txt'],'summary':c['goal'],'risks':[],'stop_reason':None}))"], self.tree, 5)
        self.assertEqual(worker({"goal": "text; $NOT_SHELL"})["summary"], "text; $NOT_SHELL")

    def test_worker_timeout_stops(self):
        worker = ProcessWorker(["python3", "-c", "import time; time.sleep(2)"], self.tree, 0.01)
        with self.assertRaisesRegex(Stop, "worker-timeout"):
            worker({})
