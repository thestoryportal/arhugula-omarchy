import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

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

    def test_foreign_index_blob_cannot_hide_behind_clean_worktree_content(self):
        (self.tree / "base.txt").write_text("foreign staged content\n")
        git(self.tree, "add", "base.txt")
        (self.tree / "base.txt").write_text("base\n")
        self.assertEqual(git(self.tree, "diff", "HEAD", "--name-only"), "")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            self.adapter.inspect()
        (self.tree / "own.txt").write_text("owned\n")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            self.adapter.commit("unit-1", ["own.txt"])
        self.assertEqual(git(self.tree, "show", ":base.txt"), "foreign staged content")

    def test_deletion_and_symlink_changes_stop(self):
        (self.tree / "base.txt").unlink()
        with self.assertRaisesRegex(Stop, "destructive"):
            self.adapter.inspect(allowed=["base.txt"])
        git(self.tree, "restore", "base.txt")
        (self.tree / "link").symlink_to(self.root / "base.txt")
        with self.assertRaisesRegex(Stop, "symlink-change"):
            self.adapter.inspect(allowed=["link"])

    def test_real_verification_failure_carries_exit_status(self):
        adapter = LocalAdapter(self.tree, ["git", "rev-parse", "--verify", "refs/heads/missing"],
                               artifact_root=Path(self.directory.name) / 'artifacts')
        passed, evidence = adapter.verify()
        self.assertFalse(passed)
        self.assertIn("exit=128", evidence)

    def test_process_worker_receives_json_context_without_shell(self):
        worker = ProcessWorker(["python3", "-c", "import json,sys; c=json.load(sys.stdin); print(json.dumps({'files':['new.txt'],'summary':c['goal'],'risks':[],'stop_reason':None}))"], self.tree, 5, artifact_root=Path(self.directory.name)/'artifacts')
        self.assertEqual(worker({"goal": "text; $NOT_SHELL"})["summary"], "text; $NOT_SHELL")

    def test_worker_timeout_stops(self):
        worker = ProcessWorker(["python3", "-c", "import time; time.sleep(2)"], self.tree, 0.01, artifact_root=Path(self.directory.name)/'artifacts')
        with self.assertRaisesRegex(Stop, "worker-timeout"):
            worker({})

    def test_worker_raw_stderr_is_retained_without_entering_receipt(self):
        import json
        store=Path(self.directory.name)/'worker-artifacts'
        worker=ProcessWorker(['python3','-c',"import json,sys; print(json.dumps({'summary':'done'})); print('x'*2000000,file=sys.stderr)"],
                             self.tree,5,artifact_root=store)
        self.assertEqual(worker({}),{'summary':'done'})
        receipts=list(store.glob('*/receipt.json'))
        self.assertEqual(len(receipts),1)
        result=json.loads(receipts[0].read_text())
        self.assertEqual(result['stderr']['bytes'],2000001)
        self.assertLess(len(result['summary']),5000)


@unittest.skipUnless(shutil.which("lit"), "native claim behavior requires lit")
class NativeClaimTests(unittest.TestCase):
    """Claims through real LIT; each adapter runs under one native session identity."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "base.txt").write_text("base\n")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-m", "baseline")
        subprocess.run(["lit", "init", "--skip-agents", "--skip-hooks"], cwd=self.root,
                       check=True, capture_output=True)
        self.trees = {}
        for lane in ("lane", "other"):
            self.trees[lane] = Path(directory.name) / lane
            git(self.root, "worktree", "add", "-b", lane, str(self.trees[lane]))
        subprocess.run(["lit", "new", "--title", "Claimed unit", "--topic", "claims"],
                       cwd=self.trees["lane"], check=True, capture_output=True)
        self.ticket = self.issue()["id"]

    def adapter(self, session, lane="lane"):
        return LocalAdapter(self.trees[lane], ["true"]), {"CLAUDE_CODE_SESSION_ID": session}

    def issue(self):
        exported = subprocess.run(["lit", "export"], cwd=self.trees["lane"], check=True,
                                  capture_output=True, text=True).stdout
        (issue,) = json.loads(exported)["issues"]
        return issue

    def claim(self, session, method="start", lane="lane"):
        adapter, env = self.adapter(session, lane)
        with mock.patch.dict("os.environ", env):
            getattr(adapter, method)(self.ticket)
        return adapter

    def test_same_checkout_successor_cannot_take_over_native_claim(self):
        self.claim("owner")
        with self.assertRaisesRegex(Stop, "claim-conflict"):
            self.claim("successor")
        self.assertEqual(self.issue()["assignee"], "claude_owner")

    def test_other_checkout_claim_refuses_without_take(self):
        self.claim("owner")
        with self.assertRaisesRegex(Stop, "claim-conflict"):
            self.claim("other", lane="other")
        self.assertEqual(self.issue()["assignee"], "claude_owner")

    def test_owner_renews_its_claim_and_detects_a_later_reassignment(self):
        owner = self.claim("owner")
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "owner"}):
            owner.assert_claim(self.ticket)
            subprocess.run(["lit", "update", self.ticket, "--assignee", "claude_reassigned"],
                           cwd=self.trees["lane"], check=True, capture_output=True)
            with self.assertRaisesRegex(Stop, "claim-conflict"):
                owner.assert_claim(self.ticket)
        self.assertEqual(self.issue()["assignee"], "claude_reassigned")

    def test_asserting_an_unheld_claim_never_claims(self):
        with self.assertRaisesRegex(Stop, "claim-conflict"):
            self.claim("owner", "assert_claim")
        self.assertEqual(self.issue()["status"], "open")
        self.claim("owner")
        with self.assertRaisesRegex(Stop, "claim-conflict"):
            self.claim("owner", "assert_claim")

    def test_identity_change_inside_one_adapter_is_reported_not_recorded(self):
        adapter = self.claim("owner")
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "successor"}):
            with self.assertRaisesRegex(Stop, "claim-conflict"):
                adapter.assert_claim(self.ticket)
        self.assertEqual(adapter.claims[self.ticket], "claude_owner")
