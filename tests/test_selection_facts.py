import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ops.orchestration import selection_facts
from ops.orchestration.selection_facts import admission, main, observe

SCRIPT = Path(selection_facts.__file__)
UNIT = "trial.u24"
GATE = "trial.release"
AUTHOR = {"kind": "claude", "role": "claude-coder", "session_id": "author-1",
          "transcript": "author.jsonl", "task_budget": 1, "reserve": 1, "ceiling": 9}
LEAD = {"kind": "codex", "role": "buford", "session_id": "lead-1",
        "transcript": "lead.jsonl", "task_budget": 1, "reserve": 1, "ceiling": 9}
REVIEWER = {"kind": "codex", "role": "implementer", "session_id": "reviewer-1",
            "transcript": "reviewer.jsonl", "task_budget": 1, "reserve": 1, "ceiling": 9}


def snapshot(*, status="in_progress", assignee="claude_author-1", gate="closed"):
    unit = {"id": UNIT, "status": status, "labels": []}
    if assignee:
        unit["assignee"] = assignee
    return {
        "issues": [unit, {"id": GATE, "status": gate, "labels": ["role:human"]}],
        "relations": [{"src_id": UNIT, "dst_id": GATE, "type": "blocks"}],
    }


def control(*sessions, paused=True):
    return {"repair_paused": paused, "sessions": list(sessions or (AUTHOR, REVIEWER, LEAD))}


class Measure:
    """The one effect seam: records which routed session was measured."""

    def __init__(self, *reasons):
        self.reasons = list(reasons)
        self.rows = []

    def __call__(self, row):
        self.rows.append(row)
        return {"decision": "hold" if self.reasons else "allow", "reasons": self.reasons}


class AdmissionTests(unittest.TestCase):
    def judge(self, data, routing=None, operation="implementation", measure=None):
        return admission(data, routing or control(), UNIT, operation, measure or Measure())

    def test_claimed_released_unit_admits_its_author_for_implementation(self):
        measure = Measure()
        self.assertEqual(
            self.judge(snapshot(), measure=measure),
            {"admission": "confirmed", "reasons": [], "session_id": "author-1"},
        )
        self.assertEqual(measure.rows, [AUTHOR])

    def test_integration_is_measured_on_the_one_buford_session(self):
        measure = Measure()
        observed = self.judge(snapshot(), operation="integration", measure=measure)
        self.assertEqual((observed["admission"], observed["session_id"]), ("confirmed", "lead-1"))
        self.assertEqual(measure.rows, [LEAD])

    def test_integration_without_exactly_one_buford_row_is_unknown(self):
        for routing in (control(AUTHOR), control(AUTHOR, LEAD, dict(LEAD, session_id="lead-2"))):
            with self.subTest(sessions=len(routing["sessions"])):
                measure = Measure()
                observed = self.judge(snapshot(), routing, "integration", measure)
                self.assertEqual(observed["admission"], "unknown")
                self.assertEqual(measure.rows, [])

    def test_absent_unit_is_unknown(self):
        data = snapshot()
        data["issues"] = data["issues"][1:]
        self.assertEqual(self.judge(data)["admission"], "unknown")

    def test_unclaimed_unit_is_contradicted_without_measurement(self):
        for data in (snapshot(status="open"), snapshot(status="closed")):
            with self.subTest(status=data["issues"][0]["status"]):
                measure = Measure()
                observed = self.judge(data, measure=measure)
                self.assertEqual(observed["reasons"], ["unit-not-claimed"])
                self.assertEqual(observed["admission"], "contradicted")
                self.assertEqual(measure.rows, [])

    def test_holder_must_be_a_routed_author(self):
        holders = {
            "no assignee": "",
            "unrouted session": "claude_author-2",
            "routed reviewer": "codex_reviewer-1",
            "routed lead": "codex_lead-1",
            "kind mismatch": "codex_author-1",
        }
        for name, holder in holders.items():
            with self.subTest(name):
                observed = self.judge(snapshot(assignee=holder))
                self.assertEqual(observed["admission"], "contradicted")
                self.assertEqual(observed["reasons"], ["claim-holder-not-a-routed-author"])

    def test_pause_requires_a_closed_inherited_human_gate(self):
        open_gate = self.judge(snapshot(gate="open"))
        self.assertEqual(
            (open_gate["admission"], open_gate["reasons"]), ("contradicted", ["production-paused"])
        )
        ungated = snapshot()
        ungated["relations"] = []
        self.assertEqual(self.judge(ungated)["reasons"], ["production-paused"])
        self.assertEqual(self.judge(snapshot(gate="open"), control(paused=False))["admission"],
                         "confirmed")

    def test_one_closed_gate_does_not_mask_another_open_inherited_gate(self):
        # pass-2 F2: every inherited human gate must be closed, as Preparation.admit requires
        for direct, inherited in (("closed", "open"), ("open", "closed")):
            with self.subTest(direct=direct, inherited=inherited):
                data = snapshot(gate=direct)
                data["issues"] += [
                    {"id": "trial.epic", "status": "open", "labels": []},
                    {"id": "trial.second", "status": inherited, "labels": ["role:human"]},
                ]
                data["relations"] += [
                    {"src_id": UNIT, "dst_id": "trial.epic", "type": "parent-child"},
                    {"src_id": "trial.epic", "dst_id": "trial.second", "type": "blocks"},
                ]
                observed = self.judge(data)
                self.assertEqual((observed["admission"], observed["reasons"]),
                                 ("contradicted", ["production-paused"]))
        both = snapshot()
        both["issues"].append({"id": "trial.second", "status": "closed", "labels": ["role:human"]})
        both["relations"].append({"src_id": UNIT, "dst_id": "trial.second", "type": "blocks"})
        self.assertEqual(self.judge(both)["admission"], "confirmed")

    def test_gate_is_inherited_through_the_parent_epic(self):
        data = snapshot()
        data["issues"].append({"id": "trial.epic", "status": "open", "labels": []})
        data["relations"] = [
            {"src_id": UNIT, "dst_id": "trial.epic", "type": "parent-child"},
            {"src_id": "trial.epic", "dst_id": GATE, "type": "blocks"},
        ]
        self.assertEqual(self.judge(data)["admission"], "confirmed")

    def test_closed_gate_without_the_human_label_does_not_release(self):
        data = snapshot()
        data["issues"][1]["labels"] = []
        self.assertEqual(self.judge(data)["reasons"], ["production-paused"])

    def test_in_turn_completion_alone_is_not_a_refusal(self):
        observed = self.judge(snapshot(), measure=Measure(selection_facts.IN_TURN))
        self.assertEqual((observed["admission"], observed["reasons"]), ("confirmed", []))

    def test_unmeasured_session_is_unknown(self):
        observed = self.judge(
            snapshot(), measure=Measure(selection_facts.IN_TURN, "missing-request-metric",
                                        "insufficient-headroom"))
        self.assertEqual(observed["admission"], "unknown")
        self.assertEqual(observed["reasons"], ["missing-request-metric", "insufficient-headroom"])

    def test_any_other_hold_reason_contradicts(self):
        for reason in ("insufficient-headroom", "session-id-mismatch", "invalid-ceiling"):
            with self.subTest(reason):
                observed = self.judge(snapshot(), measure=Measure(reason))
                self.assertEqual((observed["admission"], observed["reasons"]),
                                 ("contradicted", [reason]))

    def test_operation_outside_the_contract_is_a_caller_error(self):
        with self.assertRaises(ValueError):
            self.judge(snapshot(), operation="review")


class ObserveTests(unittest.TestCase):
    def test_failed_export_is_unknown(self):
        with mock.patch.object(selection_facts.subprocess, "run",
                               side_effect=subprocess.CalledProcessError(1, ["lit", "export"])):
            observed = observe(UNIT, "implementation")
        self.assertEqual(observed["admission"], "unknown")
        self.assertTrue(observed["reasons"][0].startswith("unreadable: CalledProcessError"))

    def test_malformed_export_or_unreadable_routing_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            routing = Path(directory) / "session-control.json"
            routing.write_text(json.dumps(control()))
            cases = {
                "export not JSON": (b"{", routing),
                "export missing relations": (json.dumps({"issues": snapshot()["issues"]}).encode(),
                                             routing),
                "routing absent": (json.dumps(snapshot()).encode(), Path(directory) / "absent"),
            }
            for name, (export, path) in cases.items():
                with self.subTest(name), \
                        mock.patch.object(selection_facts, "CONTROL", path), \
                        mock.patch.object(selection_facts.subprocess, "run",
                                          return_value=mock.Mock(stdout=export)):
                    observed = observe(UNIT, "implementation")
                self.assertEqual(observed["admission"], "unknown")
                self.assertTrue(observed["reasons"][0].startswith("unreadable: "))

    def test_missing_transcript_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            row = dict(AUTHOR, transcript=str(Path(directory) / "absent.jsonl"))
            routing = Path(directory) / "session-control.json"
            routing.write_text(json.dumps(control(row, LEAD)))
            with mock.patch.object(selection_facts, "CONTROL", routing), \
                    mock.patch.object(selection_facts.subprocess, "run",
                                      return_value=mock.Mock(stdout=json.dumps(snapshot()))):
                observed = observe(UNIT, "implementation")
        self.assertEqual(observed["admission"], "unknown")
        self.assertTrue(observed["reasons"][0].startswith("unreadable: FileNotFoundError"))


class CommandTests(unittest.TestCase):
    def test_usage_errors_exit_two(self):
        for argv in ([], ["admission", UNIT], ["admit", UNIT, "integration"],
                     ["admission", UNIT, "review"]):
            with self.subTest(argv=argv), mock.patch("sys.stderr"):
                self.assertEqual(main(argv), 2)

    def test_isolated_script_prints_one_observation_line(self):
        with tempfile.TemporaryDirectory() as directory:
            # A `lit` that fails stands in for an unreadable store; the script still
            # answers with exit 0 and one parseable JSON line.
            lit = Path(directory) / "lit"
            lit.write_text("#!/bin/sh\nexit 3\n")
            lit.chmod(0o755)
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "admission", UNIT, "integration"],
                capture_output=True, text=True, check=False, cwd=directory,
                env={"PATH": directory},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        [line] = result.stdout.splitlines()
        self.assertEqual(json.loads(line)["admission"], "unknown")


if __name__ == "__main__":
    unittest.main()
