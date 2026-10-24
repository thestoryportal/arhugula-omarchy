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

    def admitted(self, *preparation, reservations=()):
        """A runner config whose loop journal holds a real Buford grant for this checkout.

        LIT is a seam the test edits; procfs shows this process holding Buford's
        transcript, so preparation can be issued. Returns (config, lit, control).
        """
        from ops.orchestration.loop import IMPLEMENTATION, Loop, Preparation

        base = Path(self.directory.name)
        transcript = base / "buford.jsonl"
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": "buford"}}))
        control = base / "control.json"
        control.write_text(json.dumps({"repair_paused": False, "notification_thread": "buford",
            "sessions": [{"role": "buford", "session_id": "buford",
                          "transcript": str(transcript)}]}))
        proc = base / "proc"
        for pid, parent, held in ((os.getpid(), 1, transcript),):
            (proc / str(pid) / "fd").mkdir(parents=True)
            (proc / str(pid) / "stat").write_text(f"{pid} (test) S {parent} 0 0\n")
            (proc / str(pid) / "fd" / "3").symlink_to(held)
        lit = mock.Mock()
        lit.data = {
            "issues": [{"id": "unit-1", "status": "in_progress", "labels": []},
                       {"id": "goal", "status": "open", "labels": []},
                       {"id": "gate", "status": "closed", "labels": ["role:human"],
                        "closed_at": "2026-10-23T22:07:38Z"}],
            "relations": [{"type": "blocks", "src_id": "unit-1", "dst_id": "gate"}],
            "comments": [{"id": "cmt-release", "issue_id": "gate", "body": "released",
                          "created_at": "2026-10-23T22:05:35Z"}],
        }
        lit.read.side_effect = lambda ticket: (json.loads(json.dumps(lit.data)), {})
        (base / "handoff.md").write_text("goal")
        journal = base / "state.json"
        loop = Loop(journal, control, lit, proc=proc)
        loop.initialize("buford", "gpt-6.1-sol", "high", base / "handoff.md", "goal")
        for record in ({"kind": "writer", "key": "unit-1", "owner": "coder",
                        "reviewer": "reviewer", "worktree": str(self.tree),
                        "paths": ["own.txt"], "resources": []}, *reservations):
            loop.reserve(record)
        clearance = Preparation.parse(preparation, "cmt-release") if preparation else IMPLEMENTATION
        grant = loop.begin("unit-1", clearance=clearance)["admission"]
        # The runner reads LIT through its native boundary; here that is the seam.
        self.enterContext(mock.patch("ops.orchestration.runner.NativeLit", return_value=lit))
        config = {"verify_argv": ["true"], "loop_state": str(journal),
                  "loop_control": str(control), "admission": grant,
                  "artifact_root": str(base / "artifacts")}
        return config, lit, control

    def test_runner_effects_clear_their_operation_against_the_journal_grant(self):
        from ops.orchestration.runner import adapter_for

        config, lit, _ = self.admitted("artifact-inspection", "test-preparation")
        for missing in ("admission", "loop_control"):
            partial = {k: v for k, v in config.items() if k != missing}
            with self.assertRaisesRegex(ValueError, "requires the admission and loop_control"):
                adapter_for(partial, self.tree, 60)
        prepared = adapter_for(config, self.tree, 60)
        prepared.lit_argv = ["false"]
        head = git(self.tree, "rev-parse", "HEAD")
        (self.tree / "own.txt").write_text("owned\n")
        # Preparation inspects and verifies; it never claims, commits, comments or closes.
        self.assertEqual(prepared.inspect(allowed=["own.txt"])["branch"], "isolated")
        self.assertTrue(prepared.verify()[0])
        for effect in (lambda: prepared.commit("unit-1", ["own.txt"]),
                       lambda: prepared.start("unit-1"),
                       lambda: prepared.comment("unit-1", "evidence"),
                       lambda: prepared.done("unit-1")):
            with self.assertRaisesRegex(ValueError, "operation-not-admitted: implementation"):
                effect()
        self.assertEqual(git(self.tree, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.tree, "diff", "--cached", "--name-only"), "")
        # A prerequisite opened after the grant stales even its admitted operations.
        lit.data["issues"].append({"id": "late", "status": "open", "labels": []})
        lit.data["relations"].append({"type": "blocks", "src_id": "unit-1", "dst_id": "late"})
        for effect in (lambda: prepared.inspect(allowed=["own.txt"]), prepared.verify):
            with self.assertRaisesRegex(ValueError, "LIT changed"):
                effect()

    def test_runner_commit_holds_on_stale_scope_or_control(self):
        from ops.orchestration.runner import adapter_for

        config, lit, control = self.admitted()
        head = git(self.tree, "rev-parse", "HEAD")
        (self.tree / "own.txt").write_text("owned\n")
        original = (json.loads(json.dumps(lit.data)), control.read_text())

        def blocker():
            lit.data["issues"].append({"id": "late", "status": "open", "labels": []})
            lit.data["relations"].append({"type": "blocks", "src_id": "unit-1", "dst_id": "late"})

        def pause():
            control.write_text(control.read_text().replace('"repair_paused": false',
                                                            '"repair_paused": true'))

        for change in (blocker, pause):
            lit.data, _ = json.loads(json.dumps(original[0])), control.write_text(original[1])
            change()
            with self.subTest(change=change.__name__):
                with self.assertRaisesRegex(ValueError, "LIT changed or pause/routing changed"):
                    adapter_for(config, self.tree, 60).commit("unit-1", ["own.txt"])
                self.assertEqual(git(self.tree, "rev-parse", "HEAD"), head)
        lit.data, _ = original[0], control.write_text(original[1])
        self.assertTrue(adapter_for(config, self.tree, 60).commit("unit-1", ["own.txt"]))

    def test_runner_inspects_under_the_loop_journal_ownership(self):
        from ops.orchestration.runner import adapter_for

        config, _, _ = self.admitted(reservations=[
            {"kind": "preserved", "key": "cmt-protected",
             "worktree": str(self.root), "paths": ["foreign.txt"]}])
        journal = Path(config["loop_state"])
        (self.root / "foreign.txt").write_text("preserved residue")
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            adapter_for({"verify_argv": ["true"]}, self.tree, 60).inspect()
        owned = adapter_for(config, self.tree, 60)
        self.assertEqual(owned.inspect()["branch"], "isolated")
        # Releasing the declaration after construction stops it covering the checkout.
        state = json.loads(journal.read_text())
        state["reservations"] = state["reservations"][:1]
        journal.write_text(json.dumps(state))
        with self.assertRaisesRegex(Stop, "dirty-tree-conflict"):
            owned.inspect()

    def test_ownership_cannot_be_released_while_an_inspection_relies_on_it(self):
        from ops.orchestration.loop import Loop
        from ops.orchestration.runner import adapter_for

        config, _, _ = self.admitted(reservations=[
            {"kind": "preserved", "key": "cmt-protected",
             "worktree": str(self.root), "paths": ["foreign.txt"]}])
        journal = Path(config["loop_state"])
        (self.root / "foreign.txt").write_text("preserved residue")
        owned = adapter_for(config, self.tree, 60)
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
        self.assertEqual(len(json.loads(journal.read_text())["reservations"]), 2)

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

    def granted(self):
        """A runner config holding a real Buford grant whose Loop reads this LIT store."""
        from ops.orchestration.loop import Loop, NativeLit
        from ops.orchestration.runner import adapter_for

        base, tree = self.root.parent, self.trees["lane"]
        control = base / "control.json"
        control.write_text(json.dumps({"repair_paused": False, "notification_thread": "buford",
            "sessions": [{"role": "buford", "session_id": "buford", "transcript": "unused"}]}))
        (base / "handoff.md").write_text("goal")
        journal, artifacts = base / "loop" / "state.json", str(base / "artifacts")
        loop = Loop(journal, control, NativeLit(tree, artifacts))
        loop.initialize("buford", "gpt-6.1-sol", "high", base / "handoff.md", "goal")
        loop.reserve({"kind": "writer", "key": self.ticket, "owner": "coder",
                      "reviewer": "reviewer", "worktree": str(tree),
                      "paths": ["own.txt"], "resources": []})
        config = {"verify_argv": ["true"], "loop_state": str(journal),
                  "loop_control": str(control), "artifact_root": artifacts,
                  "admission": loop.begin(self.ticket)["admission"]}
        with self.native(CODEX_THREAD_ID="thread-1"):
            return adapter_for(config, tree, 60)

    def test_one_grant_carries_the_run_through_its_own_ticket_transitions(self):
        # Every effect continue_work performs, in its order, under one grant.
        run, tree = self.granted(), self.trees["lane"]
        head = run.inspect()["head"]
        run.start(self.ticket)
        run.inspect(expected_head=head)
        (tree / "own.txt").write_text("owned\n")
        run.inspect(expected_head=head, allowed=["own.txt"])
        self.assertTrue(run.verify()[0])
        run.comment(self.ticket, "Verified")
        commit = run.commit(self.ticket, ["own.txt"])
        run.inspect(expected_head=commit)
        run.done(self.ticket)
        run.comment(self.ticket, "Committed")
        self.assertEqual(self.issue()["status"], "closed")

    def test_a_prerequisite_opened_after_the_claim_still_stales_the_grant(self):
        run, tree = self.granted(), self.trees["lane"]
        head = run.inspect()["head"]
        run.start(self.ticket)
        subprocess.run(["lit", "new", "--title", "Late prerequisite", "--topic", "claims"],
                       cwd=tree, check=True, capture_output=True)
        exported = json.loads(subprocess.run(["lit", "export"], cwd=tree, check=True,
                                             capture_output=True, text=True).stdout)
        (late,) = [i["id"] for i in exported["issues"] if i["id"] != self.ticket]
        subprocess.run(["lit", "dep", "add", "--from", late, "--to", self.ticket],
                       cwd=tree, check=True, capture_output=True)
        (tree / "own.txt").write_text("owned\n")
        with self.assertRaisesRegex(ValueError, "LIT changed"):
            run.commit(self.ticket, ["own.txt"])
        self.assertEqual(git(tree, "rev-parse", "HEAD"), head)

    def test_a_foreign_comment_after_the_claim_still_stales_the_grant(self):
        run, tree = self.granted(), self.trees["lane"]
        head = run.inspect()["head"]
        run.start(self.ticket)
        subprocess.run(["lit", "comment", "add", self.ticket, "--body", "hold"],
                       cwd=tree, check=True, capture_output=True)
        (tree / "own.txt").write_text("owned\n")
        with self.assertRaisesRegex(ValueError, "LIT changed"):
            run.commit(self.ticket, ["own.txt"])
        self.assertEqual(git(tree, "rev-parse", "HEAD"), head)
