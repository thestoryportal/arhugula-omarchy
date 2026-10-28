import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest


class LitBoundary:
    """External LIT seam; all journal/recovery and scheduling code is real."""

    def __init__(self):
        self.data = {
            "version": 2,
            "issues": [
                {"id": f"u{n}", "status": "open", "issue_type": "task", "labels": []}
                for n in range(1, 8)
            ],
            "relations": [],
            "comments": [],
        }
        self.reads = 0
        self.fail = False

    def read(self, ticket):
        if self.fail:
            raise OSError("LIT read failed")
        self.reads += 1
        return copy.deepcopy(self.data), {
            "export": "retained-export",
            "show": "retained-show",
        }


def writer_record(root, key, owner, paths, *, tree=None, reviewer="reviewer", resources=()):
    return {"kind": "writer", "key": key, "owner": owner, "reviewer": reviewer,
            "worktree": str(Path(root) / (tree or key)), "paths": list(paths),
            "resources": list(resources)}


class LoopTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.old_transcript = self.root / "old.jsonl"
        self.old_transcript.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "old"}})
            + "\n"
            + json.dumps(
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-6.1-sol", "effort": "high"},
                }
            )
            + "\n"
            + json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}})
            + "\n"
        )
        self.control = self.root / "control.json"
        self.control.write_text(
            json.dumps(
                {
                    "repair_paused": False,
                    "notification_thread": "old",
                    "sessions": [
                        {
                            "role": "buford",
                            "session_id": "old",
                            "transcript": str(self.old_transcript),
                        },
                        {
                            "role": "runtime",
                            "session_id": "protected",
                            "transcript": "protected",
                        },
                    ],
                }
            )
        )
        self.handoff = self.root / "handoff.md"
        self.handoff.write_text("full sealed production goal")
        self.lit = LitBoundary()
        from ops.orchestration.loop import Loop

        self.loop = Loop(self.root / "state.json", self.control, self.lit)
        self.loop.initialize("old", "gpt-6.1-sol", "high", self.handoff, "u7")
        # Admission requires each ticket's writer reservation; one disjoint per ticket.
        for n in range(1, 8):
            self.loop.reserve(writer_record(self.root, f"u{n}", f"coder-u{n}", [f"u{n}.py"]))
        self.evidence = self.root / "proof.json"
        self.evidence.write_text('{"terminal":"success"}')

    def fresh_transcript(self, name="new"):
        from datetime import datetime, timezone

        transcript = self.root / (name + ".jsonl")
        prompt = (self.root / "package/resume-prompt.txt").read_text()
        transcript.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "id": name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-6.1-sol", "effort": "high"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    },
                }
            )
            + "\n"
        )
        return transcript

    def close(self, ticket):
        next(x for x in self.lit.data["issues"] if x["id"] == ticket)["status"] = (
            "closed"
        )
        return self.loop.complete(ticket, self.evidence)

    def test_five_closed_tickets_stop_sixth_and_survive_restart(self):
        for n in range(1, 6):
            self.loop.begin(f"u{n}")
            self.close(f"u{n}")
        from ops.orchestration.loop import Loop

        restarted = Loop(self.root / "state.json", self.control, self.lit)
        with self.assertRaisesRegex(ValueError, "context-reset-required"):
            restarted.begin("u6")
        self.assertEqual(restarted.status()["epoch_completed"], 5)

    def test_duplicate_close_does_not_advance_counter(self):
        self.loop.begin("u1")
        self.close("u1")
        self.close("u1")
        self.assertEqual(self.loop.status()["epoch_completed"], 1)

    def test_each_begin_reads_lit_and_comment_change_invalidates_transition(self):
        first = self.loop.begin("u1")
        self.lit.data["comments"].append(
            {"id": "new-comment", "issue_id": "u1", "body": "changed scope"}
        )
        with self.assertRaisesRegex(ValueError, "LIT changed"):
            self.loop.check(first["admission"], "implementation")
        self.loop.begin("u1")
        self.assertEqual(self.lit.reads, 3)

    def test_failed_read_never_uses_memory_or_mints_admission(self):
        self.lit.fail = True
        with self.assertRaisesRegex(OSError, "LIT read failed"):
            self.loop.begin("u1")
        self.assertIsNone(self.loop.status()["admission"])

    def test_pause_prevents_workflow_but_explicit_maintenance_can_read(self):
        control = json.loads(self.control.read_text())
        control["repair_paused"] = True
        self.control.write_text(json.dumps(control))
        with self.assertRaisesRegex(ValueError, "production-paused"):
            self.loop.begin("u1")
        self.loop.begin("u1", maintenance=True)
        self.assertTrue(self.loop.status()["production_paused"])

    def test_clear_refuses_owned_writer_and_changed_handoff(self):
        import os

        with self.assertRaisesRegex(ValueError, "owned writer"):
            self.loop.prepare_clear(self.root / "package", [{"pid": os.getpid()}])
        self.handoff.write_text("altered")
        with self.assertRaisesRegex(ValueError, "handoff"):
            self.loop.prepare_clear(self.root / "package", [])

    def test_wrong_model_or_same_identity_cannot_reset_five_ticket_epoch(self):
        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.root / "new.jsonl"
        transcript.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "new"}})
            + "\n"
            + json.dumps(
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-6-astra", "effort": "high"},
                }
            )
            + "\n"
        )
        with self.assertRaisesRegex(ValueError, "model"):
            self.loop.bootstrap(transcript)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_fresh_bootstrap_changes_only_buford_and_preserves_pause_and_counts(self):
        self.loop.begin("u1")
        self.close("u1")
        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.fresh_transcript()
        before = json.loads(self.control.read_text())
        result = self.loop.bootstrap(transcript)
        after = json.loads(self.control.read_text())
        self.assertEqual(after["sessions"][1], before["sessions"][1])
        self.assertEqual(after["repair_paused"], before["repair_paused"])
        self.assertEqual(result["epoch_completed"], 0)
        self.assertEqual(len(result["completed"]), 1)
        self.assertEqual(self.lit.reads, 4)

    def test_quarantined_parent_and_dependents_are_excluded(self):
        from ops.orchestration.loop import excluded_scope

        data = {
            "version": 2,
            "issues": [
                {"id": x} for x in ("parent", "bad", "child", "dependent", "okay")
            ],
            "relations": [
                {"type": "parent-child", "src_id": "bad", "dst_id": "parent"},
                {"type": "parent-child", "src_id": "child", "dst_id": "bad"},
                {"type": "blocks", "src_id": "dependent", "dst_id": "bad"},
            ],
        }
        self.assertEqual(excluded_scope(data, {"bad"}), {"bad", "child", "dependent"})

    def test_corrupt_journal_is_not_reset_to_empty(self):
        (self.root / "state.json").write_text("{partial")
        with self.assertRaises(ValueError):
            self.loop.begin("u1")

    def test_active_lane_never_becomes_clearable(self):
        self.loop.prepare_clear(self.root / "package", [])
        with self.old_transcript.open("a") as stream:
            stream.write(
                json.dumps({"type": "event_msg", "payload": {"type": "task_started"}})
                + "\n"
            )
        with self.assertRaisesRegex(ValueError, "idle"):
            self.loop.ready_clear(self.old_transcript)

    def test_crash_after_routing_update_recovers_without_double_epoch(self):
        from unittest.mock import patch

        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.fresh_transcript()
        original = self.loop._save

        def crash_final(state):
            if state["epoch"] == 1:
                raise OSError("crash after routing")
            original(state)

        with patch.object(self.loop, "_save", side_effect=crash_final):
            with self.assertRaisesRegex(OSError, "crash after routing"):
                self.loop.bootstrap(transcript)
        self.assertEqual(
            json.loads(self.control.read_text())["sessions"][0]["session_id"], "new"
        )
        self.assertEqual(self.loop.bootstrap(transcript)["epoch"], 1)

    def test_native_close_crash_holds_next_admission_until_completion_reconciled(self):
        self.loop.begin("u1")
        next(x for x in self.lit.data["issues"] if x["id"] == "u1")["status"] = "closed"
        from ops.orchestration.loop import Loop

        restarted = Loop(self.root / "state.json", self.control, self.lit)
        with self.assertRaisesRegex(ValueError, "completion-reconciliation"):
            restarted.begin("u2")
        restarted.complete("u1", self.evidence)
        self.assertEqual(restarted.begin("u2")["epoch_completed"], 1)

    def test_preexisting_unrelated_transcript_cannot_bootstrap(self):
        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.root / "unrelated.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "timestamp": "2020-01-01T00:00:00Z",
                    "payload": {"id": "unrelated", "timestamp": "2020-01-01T00:00:00Z"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-6.1-sol", "effort": "high"},
                }
            )
            + "\n"
        )
        with self.assertRaisesRegex(ValueError, "fresh handoff"):
            self.loop.bootstrap(transcript)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_native_injected_agents_prelude_does_not_mask_user_handoff(self):
        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.fresh_transcript()
        lines = transcript.read_text().splitlines()
        lines.insert(
            1,
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "# AGENTS.md instructions for /workspace\n<INSTRUCTIONS>rules</INSTRUCTIONS>",
                            }
                        ],
                    },
                }
            ),
        )
        transcript.write_text("\n".join(lines) + "\n")
        self.assertEqual(self.loop.bootstrap(transcript)["session_id"], "new")

    def test_new_transcript_without_handoff_token_is_held(self):
        self.loop.prepare_clear(self.root / "package", [])
        transcript = self.fresh_transcript()
        data = transcript.read_text().splitlines()
        row = json.loads(data[-1])
        row["payload"]["content"][0]["text"] = "unrelated task"
        data[-1] = json.dumps(row)
        transcript.write_text("\n".join(data) + "\n")
        with self.assertRaisesRegex(ValueError, "fresh handoff"):
            self.loop.bootstrap(transcript)

    def test_arc_ownership_survives_unit_advancing_to_another_arc(self):
        from unittest.mock import patch
        from types import SimpleNamespace

        product = self.root / "product"
        (product / "tools").mkdir(parents=True)
        (product / ".harness").mkdir()
        for path in ["tools/review_loop_gate.py", ".harness/merge-gate-log.jsonl"]:
            (product / path).write_text("")
        gate = SimpleNamespace(
            FULL_DIFF_REF="origin/main",
            rw=SimpleNamespace(
                code_binding=lambda *x: {
                    "head_sha": "head",
                    "base_sha": "base",
                    "diff_digest": "digest",
                }
            ),
            fr=SimpleNamespace(read_rows=lambda *x: []),
            completing_run=lambda *x: None,
        )
        result = {
            "decision": "review_required",
            "completed_passes": 4,
            "observed": [],
            "admit_review": True,
            "next_pass": "3",
            "blocking_findings": [],
            "followups": [],
        }
        with (
            patch("ops.orchestration.loop.load_gate", return_value=gate),
            patch("ops.orchestration.loop.evaluate", return_value=result.copy()),
            patch.object(
                self.lit, "command", return_value=("", "receipt"), create=True
            ),
        ):
            self.loop.review("u1", product, "arc-A", unit="stable")
            self.loop.review("u1", product, "arc-B", unit="stable")
            with self.assertRaisesRegex(ValueError, "renamed"):
                self.loop.review("u1", product, "arc-A", unit="renamed")

    def test_quarantine_native_backlog_skips_fresh_foreign_claim(self):
        from unittest.mock import patch
        from ops.orchestration.loop import NativeLit

        native = NativeLit(self.root, self.root / "artifacts")
        data = {
            "version": 2,
            "issues": [
                {"id": x, "status": "open"} for x in ("bad", "foreign", "ready")
            ],
            "relations": [],
        }
        outputs = [
            ("bad open task quarantined", "next-receipt"),
            (
                " 1. bad open -\n unclaimed\n 2. foreign open -\n claimed elsewhere (fresh): /other\n 3. ready open -\n unclaimed\n",
                "backlog-receipt",
            ),
        ]
        with patch.object(native, "command", side_effect=outputs):
            self.assertEqual(native.next(data, {"bad"}), ("ready", "backlog-receipt"))

    def writer(self, key, owner, paths, **options):
        return writer_record(self.root, key, owner, paths, **options)

    def test_overlapping_resources_hold_second_writer(self):
        self.loop.reserve(self.writer("w1", "coder-a", ["ops/orchestration/loop.py"]))
        for record, reason in (
            (self.writer("w2", "coder-b", ["ops/"]), "path-conflict"),
            (self.writer("w2", "coder-b", ["docs/x.md"], tree="w1"), "worktree-conflict"),
            (self.writer("w2", "coder-b", ["docs/x.md"], reviewer="coder-b"),
             "reviewer-not-independent"),
            (self.writer("w2", "coder-b", ["docs/x.md"], reviewer="coder-a"),
             "reviewer-is-active-author"),
            (self.writer("w2", "reviewer", ["docs/x.md"], reviewer="coder-b"),
             "author-reserved-as-reviewer"),
            (self.writer("w1", "coder-b", ["docs/x.md"]), "duplicate-reservation"),
        ):
            with self.assertRaisesRegex(ValueError, "reservation-held: .*" + reason):
                self.loop.reserve(record)
        # Disjoint independent work proceeds beside the first writer.
        self.loop.reserve(self.writer("w3", "coder-b", ["ops/orchestration/local.py"]))
        # Completion releases the writer's checkout and paths, nothing else.
        with self.assertRaisesRegex(ValueError, "path-conflict"):
            self.loop.reserve(self.writer("w4", "coder-c", ["u1.py"], reviewer="other"))
        self.loop.begin("u1")
        self.close("u1")
        self.loop.reserve(self.writer("w4", "coder-c", ["u1.py"], reviewer="other"))
        self.assertEqual(
            sorted(r.key for r in self.loop.ownership() if r.key.startswith("w")),
            ["w1", "w3", "w4"],
        )
        with self.assertRaisesRegex(ValueError, "no reservation"):
            self.loop.release("u1")

    def test_noncanonical_paths_cannot_alias_one_file(self):
        self.loop.reserve(self.writer("w1", "coder-a", ["ops/x.py", "docs/"]))
        for path in ("ops//x.py", "./ops/x.py", "ops/./x.py", "docs//", ".", "a/../b"):
            with self.assertRaisesRegex(ValueError, "invalid reservation: path"):
                self.loop.reserve(self.writer("w2", "coder-b", [path]))
        with self.assertRaisesRegex(ValueError, "path-conflict"):
            self.loop.reserve(self.writer("w2", "coder-b", ["docs/a/b.md"]))

    def test_admission_requires_current_writer_reservation(self):
        self.loop.release("u1")
        with self.assertRaisesRegex(ValueError, "reservation-required"):
            self.loop.begin("u1")
        quiet = {"kind": "hold", "key": "u1", "owner": "runtime", "resources": ["x"]}
        self.loop.reserve(quiet)
        with self.assertRaisesRegex(ValueError, "reservation-required"):
            self.loop.begin("u1")
        self.loop.release("u1")
        self.loop.reserve(self.writer("u1", "coder-u1", ["u1.py"]))
        grant = self.loop.begin("u1")
        self.assertEqual(self.loop.check(grant["admission"], "implementation")["ticket"], "u1")
        # A released or replaced reservation invalidates the admission it bound.
        self.loop.release("u1")
        with self.assertRaisesRegex(ValueError, "reservation-required"):
            self.loop.check(grant["admission"], "implementation")
        self.loop.reserve(self.writer("u1", "coder-u1", ["u1.py", "more.py"]))
        with self.assertRaisesRegex(ValueError, "reservation changed"):
            self.loop.check(grant["admission"], "implementation")

    def test_quiet_window_holds_heavy_conflict(self):
        quiet = {"kind": "hold", "key": "quiet:soak", "owner": "runtime",
                 "resources": ["host-load"]}
        self.loop.reserve(quiet)
        heavy = self.writer("w1", "coder-a", ["a.py"], resources=["host-load"])
        with self.assertRaisesRegex(ValueError, "reservation-held: resource-conflict"):
            self.loop.reserve(heavy)
        self.loop.reserve(self.writer("w2", "coder-b", ["b.py"]))
        self.assertEqual(self.loop.release("quiet:soak"), {"released": "quiet:soak"})
        self.loop.reserve(heavy)
        with self.assertRaisesRegex(ValueError, "resource-conflict"):
            self.loop.reserve(quiet)
        for malformed in (
            {**quiet, "kind": "lease"},
            {**quiet, "resources": "host-load"},
            self.writer("w4", "coder-d", ["../escape.py"]),
            self.writer("w4", "coder-d", ["/abs.py"]),
            {**self.writer("w4", "coder-d", ["d.py"]), "reviewer": ""},
        ):
            with self.assertRaisesRegex(ValueError, "invalid reservation"):
                self.loop.reserve(malformed)

    def test_quarantined_unit_preserves_true_dependencies(self):
        # dependent -> bad -> base; sibling is independent of all of them.
        self.lit.data["relations"] = [
            {"type": "blocks", "src_id": "u2", "dst_id": "u1"},
            {"type": "blocks", "src_id": "u3", "dst_id": "u2"},
            {"type": "parent-child", "src_id": "u5", "dst_id": "u4"},
            {"type": "blocks", "src_id": "u4", "dst_id": "u1"},
        ]
        state = json.loads((self.root / "state.json").read_text())
        state["quarantine"] = ["u2"]
        (self.root / "state.json").write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "quarantine"):
            self.loop.begin("u3")
        # The quarantined unit's own open dependency is real; it is not lost or hidden.
        with self.assertRaisesRegex(ValueError, "dependency-open: u1"):
            self.loop.begin("u4")
        with self.assertRaisesRegex(ValueError, "dependency-open: u1"):
            self.loop.begin("u5")
        self.loop.begin("u6")
        self.loop.begin("u1")
        self.close("u1")
        self.loop.begin("u5")
        self.close("u5")
        self.assertEqual(self.loop.status()["quarantine"], ["u2"])

    def procfs(self, *held):
        """procfs seam: this process descends from 4242, which keeps `held` open."""
        proc = self.root / "proc"
        shutil.rmtree(proc, ignore_errors=True)
        for pid, parent, files in ((os.getpid(), 4242, ()), (4242, 1, held)):
            (proc / str(pid) / "fd").mkdir(parents=True)
            (proc / str(pid) / "stat").write_text(f"{pid} (co) de) S {parent} 0 0\n")
            # An fd closed during the scan names a file that no longer exists.
            (proc / str(pid) / "fd" / "0").symlink_to(self.root / "closed")
            for fd, path in enumerate(files, 3):
                (proc / str(pid) / "fd" / str(fd)).symlink_to(path)
        return proc

    def issuing(self, *held):
        from ops.orchestration.loop import Loop

        return Loop(self.loop.path, self.control, self.lit, proc=self.procfs(*held))

    def gated(self):
        # u2 waits on open u1 and on the closed human gate whose closure released it.
        self.lit.data["issues"].append(
            {"id": "gate", "status": "closed", "labels": ["role:human"],
             "closed_at": "2026-10-23T22:07:38.569726325Z"})
        self.lit.data["relations"] = [
            {"type": "blocks", "src_id": "u2", "dst_id": "u1"},
            {"type": "blocks", "src_id": "u2", "dst_id": "gate"},
        ]
        self.lit.data["comments"] = [
            {"id": "cmt-request", "issue_id": "gate", "body": "please review",
             "created_at": "2026-10-23T02:00:00Z"},
            {"id": "cmt-release", "issue_id": "gate", "body": "released",
             "created_at": "2026-10-23T22:05:35.57391389Z"},
            {"id": "cmt-note", "issue_id": "gate", "body": "Ordinary agent note. No release.",
             "created_at": "2026-10-24T19:09:35Z"},
            {"id": "cmt-other", "issue_id": "u7", "body": "released",
             "created_at": "2026-10-23T22:06:00Z"},
        ]
        return self.issuing(self.old_transcript)

    def prepared(self, *operations, release="cmt-release"):
        from ops.orchestration.loop import Preparation

        return Preparation.parse(operations, release)

    def test_preparation_beside_open_prerequisite_clears_only_its_operations(self):
        loop = self.gated()
        with self.assertRaisesRegex(ValueError, "dependency-open: u1$"):
            loop.begin("u2")
        grant = loop.begin(
            "u2", clearance=self.prepared("artifact-inspection", "test-preparation")
        )["admission"]
        recorded = loop.status()["admission"]
        self.assertEqual(
            {k: recorded[k] for k in ("ticket", "blockers", "issuer", "release", "operations")},
            {"ticket": "u2", "blockers": ["u1"], "issuer": "old", "release": "cmt-release",
             "operations": ["artifact-inspection", "test-preparation"]},
        )
        self.assertEqual(recorded["reservation"]["paths"], ["u2.py"])
        self.assertEqual(loop.check(grant, "test-preparation")["ticket"], "u2")
        # Operations outside the recorded slice, implementation included, are refused at use.
        for operation in ("implementation", "environment-work"):
            with self.assertRaisesRegex(ValueError, "operation-not-admitted: " + operation):
                loop.check(grant, operation)
        # Preparation never completes the ticket.
        self.lit.data["issues"][1]["status"] = "closed"
        with self.assertRaisesRegex(ValueError, "completion requires this ticket admission"):
            loop.complete("u2", self.evidence)
        self.lit.data["issues"][1]["status"] = "open"
        # A changed prerequisite makes the grant stale; implementation then follows order.
        loop.begin("u1")
        grant = loop.begin("u2", clearance=self.prepared("artifact-inspection"))["admission"]
        self.close("u1")
        with self.assertRaisesRegex(ValueError, "LIT changed"):
            loop.check(grant, "artifact-inspection")
        implementation = loop.begin("u2")["admission"]
        self.assertEqual(loop.check(implementation, "implementation")["ticket"], "u2")

    def test_preparation_acts_only_under_the_record_its_gate_closed_on(self):
        loop = self.gated()
        for operations, release, error in (
            (("implementation",), "cmt-release", "preparation-operation-refused: implementation"),
            (("landing",), "cmt-release", "preparation-operation-refused: landing"),
            ((), "cmt-release", "preparation-operation-refused: none"),
            (("test-preparation",), None, "controlling release"),
        ):
            with self.subTest(operations=operations, release=release):
                with self.assertRaisesRegex(ValueError, error):
                    self.prepared(*operations, release=release)
        for ticket, release, error in (
            ("u2", "cmt-forged", "cmt-forged is not a gate of u2"),
            # An actual comment outside the ticket's gates releases nothing.
            ("u2", "cmt-other", "cmt-other is not a gate of u2"),
            # On the gate, only the record it closed on is the release.
            ("u2", "cmt-request", "cmt-request is not the record gate closed on"),
            ("u2", "cmt-note", "cmt-note is not the record gate closed on"),
            # A gate releases only what it natively blocks.
            ("u3", "cmt-release", "cmt-release is not a gate of u3"),
        ):
            with self.subTest(ticket=ticket, release=release):
                with self.assertRaisesRegex(ValueError, "release-unverified: " + error):
                    loop.begin(ticket, clearance=self.prepared("test-preparation", release=release))
        # A ticket that still inherits an open human gate stays held.
        self.lit.data["relations"].append({"type": "parent-child", "src_id": "u2", "dst_id": "u5"})
        self.lit.data["relations"].append({"type": "blocks", "src_id": "u5", "dst_id": "hil"})
        self.lit.data["issues"].append({"id": "hil", "status": "open", "labels": ["role:human"]})
        with self.assertRaisesRegex(ValueError, "hold-retained: hil"):
            loop.begin("u2", clearance=self.prepared("test-preparation"))
        self.lit.data["relations"] = self.lit.data["relations"][:2]
        # Preparation, like implementation, needs the ticket's recorded writer first.
        loop.release("u2")
        with self.assertRaisesRegex(ValueError, "reservation-required"):
            loop.begin("u2", clearance=self.prepared("test-preparation"))
        self.assertIsNone(loop.status()["admission"])

    def test_preparation_is_issued_only_from_the_native_buford_session(self):
        self.gated()
        other = self.root / "other.jsonl"
        other.write_text(self.old_transcript.read_text())
        # No caller ancestor holds the Buford transcript: the library begin refuses too.
        for loop in (self.issuing(), self.issuing(other)):
            with self.assertRaisesRegex(ValueError, "caller-not-issuer: no caller process"):
                loop.begin("u2", clearance=self.prepared("test-preparation"))
        self.assertIsNone(self.loop.status()["admission"])
        # The held transcript must still be the journal's Buford session.
        renamed = json.loads(self.control.read_text())
        renamed["sessions"][0]["transcript"] = str(self.meta_transcript("new"))
        self.control.write_text(json.dumps(renamed))
        with self.assertRaisesRegex(ValueError, "caller-not-issuer: Buford transcript"):
            self.issuing(Path(renamed["sessions"][0]["transcript"])).begin(
                "u2", clearance=self.prepared("test-preparation"))
        self.assertIsNone(self.loop.status()["admission"])

    def meta_transcript(self, session):
        transcript = self.root / (session + "-meta.jsonl")
        transcript.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": session}}) + "\n")
        return transcript

    def cli(self, *argv, actual=("old", "gpt-6.1-sol", "high"), held=None):
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        from ops.orchestration import ceiling, loop

        identity = dict(zip(("session_id", "model", "effort"), actual))
        measured = SimpleNamespace(identity=SimpleNamespace(session_id="old", model="gpt-6.1-sol"))
        row = json.loads(self.control.read_text())
        row["sessions"][0]["task_budget"] = 1
        self.control.write_text(json.dumps(row))
        bound = SimpleNamespace(bound=lambda *_: None)
        args = ["loop", "--state", str(self.loop.path), "--control", str(self.control), *argv]
        proc = self.procfs(*([self.old_transcript] if held is None else held))
        real = loop.Loop
        # The measured-headroom seam fits; identity and procfs are the boundaries under test.
        with patch.object(loop, "identity", return_value=identity), \
                patch.object(loop, "NativeLit", return_value=self.lit), \
                patch.object(loop, "Loop", lambda *a: real(*a, proc=proc)), \
                patch("ops.orchestration.session_context.inspect_transcript"), \
                patch.object(ceiling.Measurement, "parse", return_value=measured), \
                patch.object(ceiling.Authority, "sealed", return_value=bound), \
                patch.object(ceiling, "decide", return_value=SimpleNamespace(admit=True)), \
                patch("sys.argv", args), patch("sys.stdout", new_callable=io.StringIO) as out, \
                patch("sys.stderr", new_callable=io.StringIO) as err:
            code = loop.main()
        return code, out.getvalue(), err.getvalue()

    def test_cli_mints_preparation_only_under_actual_buford_identity(self):
        self.gated()
        prepare = ("begin", "u2", "--prepare", "test-preparation", "--release", "cmt-release")
        code, _, err = self.cli(*prepare, actual=("impostor", "gpt-6.1-sol", "high"))
        self.assertEqual(code, 2)
        self.assertIn("actual Buford identity/model/effort mismatch", err)
        # Matching stored identity alone is not the issuer: the caller must descend
        # from the Buford session, and the release must be the gate's closing record.
        for argv, held, error in (
            (prepare, (), "caller-not-issuer"),
            (prepare[:-1] + ("cmt-note",), None, "release-unverified: cmt-note"),
            (("begin", "u2", "--release", "cmt-release"), None, "preparation-operation-refused"),
            (("begin", "u2", "--prepare", "test-preparation"), None, "controlling release"),
        ):
            with self.subTest(argv=argv, held=held):
                code, _, err = self.cli(*argv, held=held)
                self.assertEqual(code, 2)
                self.assertIn(error, err)
        self.assertIsNone(self.loop.status()["admission"])
        code, out, err = self.cli(*prepare)
        self.assertEqual((code, err), (0, ""))
        grant = json.loads(out)["admission"]
        code, out, _ = self.cli("check", grant, "--operation", "test-preparation")
        self.assertEqual((code, json.loads(out)["ticket"]), (0, "u2"))
        code, _, err = self.cli("check", grant, "--operation", "implementation")
        self.assertEqual(code, 2)
        self.assertIn("operation-not-admitted: implementation", err)

    def test_export_without_comment_or_relation_records_holds_admission(self):
        from unittest.mock import patch
        from ops.orchestration.loop import Loop, NativeLit

        complete = {**copy.deepcopy(self.lit.data), "comments": [], "relations": []}
        for missing in ("comments", "relations"):
            export = {k: v for k, v in complete.items() if k != missing}
            native = NativeLit(self.root, self.root / "artifacts")
            outputs = [(json.dumps(export), "export-receipt"), ("u1", "show-receipt")]
            loop = Loop(self.root / "state.json", self.control, native)
            with self.subTest(missing=missing), patch.object(
                native, "command", side_effect=outputs
            ):
                with self.assertRaisesRegex(ValueError, "invalid LIT ticket/export"):
                    loop.begin("u1")
                self.assertIsNone(loop.status()["admission"])

    def test_pause_reassignment_or_failed_read_before_boundary_holds_check(self):
        def pause():
            control = json.loads(self.control.read_text())
            control["repair_paused"] = True
            self.control.write_text(json.dumps(control))

        def reassign():
            self.lit.data["issues"][0]["assignee"] = "claude_successor"

        def fail():
            self.lit.fail = True

        original = (self.control.read_text(), copy.deepcopy(self.lit.data))
        for change, error in (
            (pause, "pause/routing changed"),
            (reassign, "LIT changed"),
            (fail, "LIT read failed"),
        ):
            self.control.write_text(original[0])
            self.lit.data, self.lit.fail = copy.deepcopy(original[1]), False
            admission = self.loop.begin("u1")["admission"]
            change()
            with self.subTest(change=change.__name__):
                with self.assertRaisesRegex(Exception, error):
                    self.loop.check(admission, "implementation")

    def test_only_the_runs_own_transition_moves_its_grant(self):
        original = copy.deepcopy(self.lit.data)

        def claim():
            self.lit.data["issues"][0].update(status="in_progress", assignee="claude_coder")
            self.lit.data["comments"].append({"id": "own", "issue_id": "u1", "body": "claimed"})

        def comment():
            self.lit.data["comments"].append({"id": "foreign", "issue_id": "u1", "body": "hold"})

        def reassign():
            self.lit.data["issues"][0]["assignee"] = "claude_successor"

        def block():
            self.lit.data["relations"].append({"type": "blocks", "src_id": "u1", "dst_id": "u2"})

        for change in (comment, reassign, block):
            with self.subTest(change=change.__name__):
                self.lit.data = copy.deepcopy(original)
                admission = self.loop.begin("u1")["admission"]
                self.loop.transition(admission, "implementation", "u1", claim)
                self.loop.check(admission, "implementation")
                change()
                with self.assertRaisesRegex(ValueError, "LIT changed"):
                    self.loop.check(admission, "implementation")
        # A write that moves anything beside its own ticket's progress stands nothing.
        self.lit.data = copy.deepcopy(original)
        admission = self.loop.begin("u1")["admission"]
        with self.assertRaisesRegex(ValueError, "beside this run's transition"):
            self.loop.transition(admission, "implementation", "u1", lambda: (claim(), block()))
        with self.assertRaisesRegex(ValueError, "LIT changed"):
            self.loop.check(admission, "implementation")

    def test_a_grant_admits_effects_only_on_its_own_ticket(self):
        # A quarantined ticket and its dependent stay outside an independent grant.
        self.lit.data["relations"].append({"type": "blocks", "src_id": "u3", "dst_id": "u2"})
        state = json.loads((self.root / "state.json").read_text())
        state["quarantine"] = ["u2"]
        (self.root / "state.json").write_text(json.dumps(state))
        admission = self.loop.begin("u1")["admission"]
        writes = []
        for other in ("u2", "u3"):
            with self.subTest(other=other):
                with self.assertRaisesRegex(ValueError, f"grant-ticket-mismatch: u1 does not admit {other}"):
                    self.loop.check(admission, "implementation", other)
                with self.assertRaisesRegex(ValueError, "grant-ticket-mismatch"):
                    self.loop.check(admission, "implementation", "u1", other)
                with self.assertRaisesRegex(ValueError, "grant-ticket-mismatch"):
                    self.loop.transition(admission, "implementation", other,
                                         lambda: writes.append(other))
        self.assertEqual(writes, [])
        # The run's own ticket, and worktree effects naming no ticket, still clear.
        self.assertEqual(self.loop.check(admission, "implementation", "u1")["ticket"], "u1")
        self.assertEqual(self.loop.check(admission, "artifact-inspection")["ticket"], "u1")
        self.loop.transition(admission, "implementation", "u1", lambda: (
            self.lit.data["issues"][0].update(status="closed"), writes.append("u1")))
        self.assertEqual(writes, ["u1"])
        self.assertEqual(json.loads((self.root / "state.json").read_text())["quarantine"], ["u2"])

    def test_a_run_selects_only_its_granted_ticket_until_it_closes(self):
        stale = self.loop.begin("u2")["admission"]
        admission = self.loop.begin("u1")["admission"]
        self.assertEqual(self.loop.selection(admission), ["u1"])
        with self.assertRaisesRegex(ValueError, "fresh LIT admission required"):
            self.loop.selection(stale)
        self.lit.data["issues"][0]["status"] = "closed"
        self.assertEqual(self.loop.selection(admission), [])
