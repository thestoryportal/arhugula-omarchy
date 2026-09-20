import copy
from pathlib import Path
import tempfile
import unittest

from ops.orchestration.continuation import Lease, Stop, select_ticket, continue_work
from ops.orchestration.handoff import read_handoff


def backlog():
    return {"version": 2, "issues": [
        {"id": "epic", "issue_type": "epic", "title": "Bootstrap", "labels": []},
        {"id": "arc", "issue_type": "feature", "title": "Implement", "labels": [], "status": "open"},
        *[{"id": f"unit-{n}", "title": "Write fixtures", "issue_type": "task", "rank": str(n),
           "status": "open", "labels": ["autonomous-safe", "capability:fixtures"]} for n in (1, 2)]
    ], "relations": [
        {"src_id": "arc", "dst_id": "epic", "type": "parent-child"},
        *[{"src_id": f"unit-{n}", "dst_id": "arc", "type": "parent-child"} for n in (1, 2)]]}


class FakeAdapter:
    """LIT/Git boundary double; real routing, state machine, and persistence."""
    def __init__(self):
        self.data = backlog()
        self.events = []
        self.foreign = False
        self.fail_verify = False
        self.fail_commit = False
        self.claim_conflict = False
        self.head = "base"
        self.files = []
        self.claimed = None

    def next(self):
        self.events.append("next")
        return "arc  open feature Implement" if any(i.get("status") == "open" and i["id"].startswith("unit") for i in self.data["issues"]) else ""

    def export(self):
        return copy.deepcopy(self.data)

    def inspect(self, expected_head=None, allowed=()):
        if self.foreign or set(self.files) - set(allowed):
            raise Stop("dirty-tree-conflict")
        if expected_head and expected_head != self.head:
            raise Stop("git-head-changed")
        return {"branch": "feature/one", "worktree": "/tmp/isolated", "head": self.head}

    def start(self, ticket):
        if self.claim_conflict:
            raise Stop("claim-conflict")
        self.events.append("start:" + ticket)
        self.claimed = ticket
        next(i for i in self.data["issues"] if i["id"] == ticket)["status"] = "in_progress"

    def show(self, ticket):
        self.events.append("show:" + ticket)
        return ticket

    def verify(self):
        self.events.append("verify")
        return not self.fail_verify, "fixture verification"

    def comment(self, ticket, body):
        self.events.append("comment:" + ticket)

    def commit(self, ticket, files):
        self.events.append("commit:" + ticket)
        if self.fail_commit:
            raise Stop("commit-failed")
        self.head = "commit-" + ticket
        self.files = []
        return self.head

    def done(self, ticket):
        self.events.append("done:" + ticket)
        next(i for i in self.data["issues"] if i["id"] == ticket)["status"] = "closed"

    def assert_claim(self, ticket):
        if self.claimed != ticket:
            raise Stop("claim-conflict")


def worker(adapter, **changes):
    def implement(context):
        adapter.events.append("work:" + context["active_ticket"])
        adapter.files = ["fixture.txt"]
        return {"files": ["fixture.txt"], "summary": "Added fixture", "risks": [], "stop_reason": None, **changes}
    return implement


class ContinuationTests(unittest.TestCase):
    def run_loop(self, adapter, implementation=None, limit=2):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            result = continue_work(adapter, implementation or worker(adapter), path,
                                   goal="Finish bootstrap", limit=limit)
            self.assertEqual(read_handoff(path), result)
            return result

    def test_container_selection_descends_in_rank_order(self):
        self.assertEqual(select_ticket(backlog(), "arc open Implement")[0]["id"], "unit-1")

    def test_export_blocks_direction_and_ancestor_dependency_are_enforced(self):
        data = backlog()
        data["issues"].append({"id": "prerequisite", "status": "open", "issue_type": "feature"})
        data["relations"].append({"src_id": "epic", "dst_id": "prerequisite", "type": "blocks"})
        with self.assertRaisesRegex(Stop, "blocked"):
            select_ticket(data, "unit-1 open Write fixtures")

    def test_two_tickets_commit_before_done_and_preserve_evidence(self):
        adapter = FakeAdapter()
        result = self.run_loop(adapter)
        self.assertEqual(result["stop_reason"], "ticket-limit")
        self.assertEqual(len(result["completed_work"]), 2)
        self.assertEqual(len(result["verification"]), 2)
        for n in (1, 2):
            self.assertLess(adapter.events.index(f"commit:unit-{n}"), adapter.events.index(f"done:unit-{n}"))
        self.assertEqual(result["model"], "gpt-5.6-terra")
        self.assertEqual(result["next_ticket"], None)

    def test_hil_and_dirty_conflict_stop_before_claim(self):
        for kind in ("hil", "dirty", "claim"):
            adapter = FakeAdapter()
            if kind == "hil":
                adapter.data["issues"][2]["labels"].append("hil-required")
            elif kind == "dirty":
                adapter.foreign = True
            else:
                adapter.claim_conflict = True
            result = self.run_loop(adapter)
            self.assertEqual(result["stop_reason"], {"hil": "hil-required", "dirty": "dirty-tree-conflict", "claim": "claim-conflict"}[kind])
            self.assertFalse(any(e.startswith("work:") for e in adapter.events))

    def test_two_failed_verifications_never_commit_or_close(self):
        adapter = FakeAdapter()
        adapter.fail_verify = True
        result = self.run_loop(adapter)
        self.assertEqual(result["stop_reason"], "verification-failed-twice")
        self.assertEqual(adapter.events.count("verify"), 2)
        self.assertFalse(any(e.startswith(("commit:", "done:")) for e in adapter.events))

    def test_failed_commit_never_closes(self):
        adapter = FakeAdapter()
        adapter.fail_commit = True
        result = self.run_loop(adapter)
        self.assertEqual(result["stop_reason"], "commit-failed")
        self.assertNotIn("done:unit-1", adapter.events)

    def test_worker_stop_and_out_of_scope_files_cannot_close(self):
        for changes, reason in [({"stop_reason": "privileged"}, "privileged"),
                                ({"files": ["../escape"]}, "invalid-worker-receipt"),
                                ({"files": [".git/config"]}, "invalid-worker-receipt"),
                                ({"files": []}, "invalid-worker-receipt")]:
            adapter = FakeAdapter()
            result = self.run_loop(adapter, worker(adapter, **changes))
            self.assertEqual(result["stop_reason"], reason)
            self.assertNotIn("done:unit-1", adapter.events)

    def test_crash_leaves_active_ticket_and_stop_handoff(self):
        adapter = FakeAdapter()
        def crash(context):
            raise RuntimeError("lost worker")
        result = self.run_loop(adapter, crash)
        self.assertEqual(result["active_ticket"], "unit-1")
        self.assertEqual(result["stop_reason"], "adapter-error")
        self.assertIn("lost worker", result["risks"][-1])

    def test_lease_prevents_simultaneous_writers_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.lock"
            with Lease(path):
                with self.assertRaisesRegex(Stop, "lease-conflict"):
                    with Lease(path):
                        pass
            with Lease(path):
                pass

    def test_worker_safety_stop_survives_restart_with_its_risks(self):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            first = continue_work(adapter, worker(adapter, stop_reason="hil-required", risks=["Needs human design"]), path, goal="Safety")
            self.assertIn("Needs human design", first["risks"])
            self.assertTrue(first["worker_stop"])
            adapter.files = []
            adapter.events.clear()
            second = continue_work(adapter, worker(adapter), path, goal="Safety", prior=first)
            self.assertEqual(second["stop_reason"], "hil-required")
            self.assertFalse(any(e.startswith("work:") for e in adapter.events))

    def test_corrected_preflight_stop_can_revalidate_uninspected_branch(self):
        adapter = FakeAdapter()
        adapter.foreign = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            first = continue_work(adapter, worker(adapter), path, goal="Safety")
            adapter.foreign = False
            second = continue_work(adapter, worker(adapter), path, goal="Safety", prior=first)
            self.assertEqual(second["stop_reason"], "ticket-limit")
            self.assertEqual(len(second["completed_work"]), 1)

    def test_context_ceiling_hands_off_without_starting_another_worker(self):
        adapter = FakeAdapter()
        adapter.data["issues"][2]["description"] = "x" * 5000
        adapter.show = lambda ticket: "x" * 5000
        with tempfile.TemporaryDirectory() as directory:
            result = continue_work(adapter, worker(adapter), Path(directory) / "handoff.json", goal="Bound context", context_bytes=2000)
        self.assertEqual(result["stop_reason"], "context-limit")
        self.assertFalse(any(e.startswith("work:") for e in adapter.events))

    def test_lit_safety_change_during_worker_prevents_commit_and_close(self):
        adapter = FakeAdapter()
        def changed(context):
            result = worker(adapter)(context)
            adapter.data["issues"][2]["labels"].append("hil-required")
            return result
        result = self.run_loop(adapter, changed)
        self.assertEqual(result["stop_reason"], "hil-required")
        self.assertNotIn("commit:unit-1", adapter.events)
        self.assertNotIn("done:unit-1", adapter.events)

    def test_failed_close_cannot_replay_already_committed_work_on_restart(self):
        adapter = FakeAdapter()
        def failed_close(ticket):
            raise RuntimeError("LIT unavailable after commit")
        adapter.done = failed_close
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            first = continue_work(adapter, worker(adapter), path, goal="Safety")
            self.assertTrue(first["recovery_required"])
            adapter.events.clear()
            second = continue_work(adapter, worker(adapter), path, goal="Safety", prior=first)
            self.assertEqual(second["stop_reason"], "recovery-required")
            self.assertFalse(any(e.startswith("work:") for e in adapter.events))

    def test_interrupted_stop_remains_latched_after_multiple_restarts(self):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            first = continue_work(adapter, worker(adapter), path, goal="Safety")
            first["stop_reason"] = "interrupted"
            for _ in range(2):
                adapter.events.clear()
                first = continue_work(adapter, worker(adapter), path, goal="Safety", prior=first)
                self.assertEqual(first["stop_reason"], "recovery-required")
                self.assertTrue(first["recovery_required"])
                self.assertFalse(any(e.startswith("work:") for e in adapter.events))
