from contextlib import nullcontext
import json
import os
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

    def test_unrelated_dirty_tree_does_not_block_owned_work(self):
        from ops.orchestration.ownership import parse

        (self.root / "foreign.txt").write_text("preserved residue")
        (self.root / "notes").mkdir()
        (self.root / "notes" / "draft.md").write_text("preserved draft")
        preserved = parse({"kind": "preserved", "key": "cmt-protected",
                           "worktree": str(self.root), "paths": ["foreign.txt", "notes/"]})
        owned = LocalAdapter(self.tree, ["git", "diff", "--check"],
                             ownership=lambda: nullcontext([preserved]))
        (self.tree / "own.txt").write_text("owned\n")
        self.assertEqual(owned.inspect(allowed=["own.txt"])["branch"], "isolated")
        self.assertTrue(owned.commit("unit-1", ["own.txt"]))
        # The declaration covers exactly what it names; a new write there is unowned.
        (self.root / "late.txt").write_text("unknown writer")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            owned.inspect()
        # Ownership of one checkout says nothing about another dirty checkout.
        (self.root / "late.txt").unlink()
        other = Path(self.directory.name) / "other"
        git(self.root, "worktree", "add", "-b", "other", str(other))
        (other / "foreign.txt").write_text("undeclared")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            owned.inspect()

    def test_runner_inspects_under_the_loop_journal_ownership(self):
        from ops.orchestration.runner import adapter_for

        journal = Path(self.directory.name) / "state.json"
        journal.write_text(json.dumps({"version": 2, "completed": {}, "reviews": {},
            "reservations": [{"kind": "preserved", "key": "cmt-protected",
                              "worktree": str(self.root), "paths": ["foreign.txt"]}]}))
        (self.root / "foreign.txt").write_text("preserved residue")
        config = {"verify_argv": ["true"]}
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            adapter_for(config, self.tree, 60).inspect()
        owned = adapter_for({**config, "loop_state": str(journal)}, self.tree, 60)
        self.assertEqual(owned.inspect()["branch"], "isolated")
        # Releasing the declaration after construction stops it covering the checkout.
        state = json.loads(journal.read_text())
        state["reservations"] = []
        journal.write_text(json.dumps(state))
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            owned.inspect()

    def test_ownership_cannot_be_released_while_an_inspection_relies_on_it(self):
        from ops.orchestration.loop import Loop
        from ops.orchestration.runner import adapter_for

        journal = Path(self.directory.name) / "state.json"
        journal.write_text(json.dumps({"version": 2, "completed": {}, "reviews": {},
            "reservations": [{"kind": "preserved", "key": "cmt-protected",
                              "worktree": str(self.root), "paths": ["foreign.txt"]}]}))
        (self.root / "foreign.txt").write_text("preserved residue")
        owned = adapter_for({"loop_state": str(journal)}, self.tree, 60)
        attempts, scan = [], owned.dirty

        def release_mid_scan(worktree):
            try:
                Loop(journal, journal, None).release("cmt-protected")
            except Stop as error:
                attempts.append(str(error))
            return scan(worktree)

        owned.dirty = release_mid_scan
        self.assertEqual(owned.inspect()["branch"], "isolated")
        self.assertEqual(attempts, ["lease-conflict"])
        self.assertEqual(len(json.loads(journal.read_text())["reservations"]), 1)

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

    def issue(self):
        exported = subprocess.run(["lit", "export"], cwd=self.trees["lane"], check=True,
                                  capture_output=True, text=True).stdout
        (issue,) = json.loads(exported)["issues"]
        return issue

    def claim(self, session, method="start", lane="lane"):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": session}):
            adapter = LocalAdapter(self.trees[lane], ["true"])
        getattr(adapter, method)(self.ticket)
        return adapter

    def native(self, **identity):
        # Exactly the given native session variables, whatever runs the suite.
        environment = {k: v for k, v in os.environ.items()
                       if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
        return mock.patch.dict("os.environ", {**environment, **identity}, clear=True)

    def test_codex_session_claims_and_renews_as_its_native_thread(self):
        with self.native(CODEX_THREAD_ID="thread-1"):
            owner = LocalAdapter(self.trees["lane"], ["true"])
            owner.start(self.ticket)
            owner.assert_claim(self.ticket)
            self.assertEqual(self.issue()["assignee"], "codex_thread-1")
        with self.native(CODEX_THREAD_ID="thread-2"):
            successor = LocalAdapter(self.trees["lane"], ["true"])
        with self.assertRaisesRegex(Stop, "claim-conflict"):
            successor.start(self.ticket)
        self.assertEqual(self.issue()["assignee"], "codex_thread-1")

    def test_claim_without_a_native_session_refuses_before_any_mutation(self):
        with self.native():
            anonymous = LocalAdapter(self.trees["lane"], ["true"])
        for method in (anonymous.start, anonymous.assert_claim):
            with self.subTest(method=method.__name__):
                with self.assertRaisesRegex(Stop, "claim-owner-unknown"):
                    method(self.ticket)
                self.assertEqual(self.issue()["status"], "open")
                self.assertNotIn("assignee", self.issue())

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

    def test_changed_session_identity_never_transfers_a_held_claim(self):
        owner = self.claim("owner")
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "successor"}):
            owner.assert_claim(self.ticket)
            self.assertEqual(self.issue()["assignee"], "claude_owner")
            successor = LocalAdapter(self.trees["lane"], ["true"])
            for method in (successor.assert_claim, successor.start):
                with self.subTest(method=method.__name__):
                    with self.assertRaisesRegex(Stop, "claim-conflict"):
                        method(self.ticket)
                    self.assertEqual(self.issue()["assignee"], "claude_owner")
