import copy
import hashlib
import json
from pathlib import Path
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
            self.loop.check(first["admission"])
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

    def closeout(self, ticket, obligations, disposition="retained"):
        """Write one closeout record to its own content-addressed file, so records built
        together (a table of refusals) never overwrite each other before use."""
        body = json.dumps(
            {
                "record_type": "closeout",
                "schema_version": 1,
                "ticket": ticket,
                "worktrees": [
                    {
                        "disposition": disposition,
                        "owner": "facade-coder",
                        "path": "/w/u1",
                        "branch": "feat/u1",
                        "head": "a" * 40,
                        "protected": ["evidence/u1"],
                        "reason": "retained for reviewer readback",
                    }
                ],
                "obligations": [
                    {
                        "name": name,
                        "state": state,
                        "owner": "buford",
                        "next_action": "cmt-next",
                    }
                    for name, state in obligations
                ],
            }
        )
        path = self.root / f"closeout-{hashlib.sha256(body.encode()).hexdigest()}.json"
        path.write_text(body)
        return path

    def closure(self, **states):
        """Every WS-11 required obligation met unless overridden, then any extras."""
        from ops.orchestration.loop import TRIAL_CLOSURE

        return [(name, states.pop(name, "met")) for name in TRIAL_CLOSURE] + list(
            states.items()
        )

    def trial_loop(self):
        from ops.orchestration.loop import Loop

        return Loop(
            self.root / "state.json",
            self.control,
            self.lit,
            membership=lambda journal, ticket: "trial",
        )

    def closed(self, ticket):
        self.loop.begin(ticket)
        next(x for x in self.lit.data["issues"] if x["id"] == ticket)["status"] = "closed"

    def test_retained_worktree_can_close_trial(self):
        """WT-29: a retained worktree and pending asynchronous metrics/archive do not hold
        trial bookkeeping; the pending items stay visible with their owner."""
        self.closed("u1")
        closeout = self.closeout(
            "u1",
            self.closure(metrics="open", archive="open"),
        )
        result = self.trial_loop().complete("u1", self.evidence, closeout=closeout)
        self.assertEqual(result["epoch_completed"], 1)
        state = json.loads((self.root / "state.json").read_text())
        record = state["completed"]["u1"]
        self.assertEqual(record["pending"], ["metrics", "archive"])
        self.assertEqual(record["worktrees"], {"/w/u1": "retained"})
        self.assertEqual(self.loop.begin("u2")["epoch_completed"], 1)  # unrelated work moves

    def test_async_housekeeping_cannot_close_required_obligation(self):
        self.closed("u1")
        trial = self.trial_loop()
        open_final = self.closeout("u1", self.closure(installed_acceptance="open", metrics="met"))
        with self.assertRaisesRegex(ValueError, "required obligation open: installed_acceptance"):
            trial.complete("u1", self.evidence, closeout=open_final)
        # pass-1 F2 repro: an open asynchronous item alone is not a closeout
        only_async = self.closeout("u1", [("metrics", "open")])
        with self.assertRaisesRegex(ValueError, "omits required obligation: deliverables"):
            trial.complete("u1", self.evidence, closeout=only_async)
        with self.assertRaisesRegex(ValueError, "trial completion requires its closeout"):
            trial.complete("u1", self.evidence)
        for bad in (
            self.closeout("u2", self.closure()),  # another ticket's record
            self.closeout("u1", self.closure(own_main="deferred")),
            self.closeout("u1", self.closure(own_main="not_applicable")),
            self.closeout("u1", self.closure(metrics="not_applicable")),
            # pass-2 F5 repro: a closeout alone cannot waive installed acceptance
            self.closeout("u1", self.closure(installed_acceptance="not_applicable")),
            self.closeout("u1", self.closure() + [("review", "met")]),  # duplicate name
            self.closeout("u1", self.closure(), disposition="pending"),
            self.closeout("u1", []),
        ):
            with self.assertRaises(ValueError):
                trial.complete("u1", self.evidence, closeout=bad)
        self.assertEqual(self.loop.status()["epoch_completed"], 0)
        self.assertEqual(
            trial.complete("u1", self.evidence, closeout=self.closeout("u1", self.closure()))[
                "epoch_completed"
            ],
            1,
        )

    def test_non_trial_closeout_keeps_its_evidence_only_contract(self):
        """Legacy work completes on evidence alone; a trial closeout cannot attach to it."""
        self.closed("u1")
        with self.assertRaisesRegex(ValueError, "ticket is legacy"):
            self.loop.complete("u1", self.evidence, closeout=self.closeout("u1", self.closure()))
        self.assertEqual(self.loop.status()["epoch_completed"], 0)
        self.assertEqual(self.loop.complete("u1", self.evidence)["epoch_completed"], 1)

    def test_trial_membership_is_held_once_the_profile_is_activated(self):
        """The default adapter reads the activation receipt beside the journal: absent means
        every ticket is legacy; present, membership needs adapters this loop lacks, so
        completion holds instead of counting under either profile."""
        self.closed("u1")
        (self.root / "workflow-activation.json").write_text("{}")
        for closeout in (None, self.closeout("u1", self.closure())):
            with self.assertRaisesRegex(ValueError, "authority_unavailable"):
                self.loop.complete("u1", self.evidence, closeout=closeout)
        self.assertEqual(self.loop.status()["epoch_completed"], 0)

    def test_only_trial_or_legacy_membership_counts(self):
        """pass-2 F4 repro: a held or unknown membership from the adapter seam holds
        completion with or without a closeout; it is never counted as legacy."""
        from ops.orchestration.loop import Loop

        self.closed("u1")
        for profile in ("held", "unknown", None):
            loop = Loop(
                self.root / "state.json",
                self.control,
                self.lit,
                membership=lambda journal, ticket, profile=profile: profile,
            )
            for closeout in (None, self.closeout("u1", self.closure())):
                with self.assertRaisesRegex(ValueError, "holds completion"):
                    loop.complete("u1", self.evidence, closeout=closeout)
        self.assertEqual(self.loop.status()["epoch_completed"], 0)

    def test_workflow_closeout_cannot_close_a_production_parent(self):
        self.lit.data["relations"].append(
            {"type": "parent-child", "src_id": "u7", "dst_id": "u1"}
        )
        self.closed("u1")
        closeout = self.closeout("u1", self.closure())
        with self.assertRaisesRegex(ValueError, "completed parent/epic"):
            self.trial_loop().complete("u1", self.evidence, closeout=closeout)

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
                    self.loop.check(admission)
