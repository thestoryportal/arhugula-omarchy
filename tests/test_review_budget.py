import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


class RecordedGate:
    """Replay bound provider observations, without implementing reducer rules."""

    def __init__(self, observation):
        self.observation = observation

    def reply(self, method, rows, *args, **kwargs):
        call = self.observation["calls"][method]
        if rows != self.observation["rows"] or call["query"] != {
            "args": list(args),
            "kwargs": kwargs,
        }:
            raise AssertionError(
                "gate request differs from recorded canonical evidence"
            )
        return call["result"]

    def pass_runs(self, rows, arc):
        return [SimpleNamespace(**run) for run in self.reply("pass_runs", rows, arc)]

    def _last_dispositions(self, rows):
        return self.reply("_last_dispositions", rows)

    def next_pass(self, rows, arc, **kwargs):
        return self.reply("next_pass", rows, arc, **kwargs)

    def unfixed_after_pass_3(self, rows, arc):
        return self.reply("unfixed_after_pass_3", rows, arc)


def rows_for(cycle_pass, head="head", severity=None, unavailable=False):
    roles = {
        "1": [
            "codex_review_wrapper",
            "merge-gate-concurrency",
            "merge-gate-spec-conformance",
            "merge-gate-witness-adequacy",
        ],
        "2": ["codex_review_wrapper", "merge-gate-witness-adequacy"],
        "3": ["merge-gate-concurrency"],
    }[cycle_pass]
    rows = [
        dict(
            arc_id="arc",
            cycle_pass=cycle_pass,
            head_sha=head,
            diff_digest="digest",
            producer=role,
            record_kind="reviewer_unavailable" if unavailable else "no_finding",
        )
        for role in roles
    ]
    if severity:
        rows[0].update(
            record_kind="finding", finding_id=f"{cycle_pass}-{head}", severity=severity
        )
        rows.append(
            dict(
                record_kind="finding_adjudication",
                finding_id=f"{cycle_pass}-{head}",
                disposition="accepted",
            )
        )
    return rows


class ReviewBudgetTests(unittest.TestCase):
    def evaluate(self, rows, observed=(), impacts=()):
        from ops.orchestration.review_budget import evaluate

        # [LAW:single-enforcer] The product owns reducer rules; this suite tests
        # the adapter against recorded provider replies, never a copied reducer.
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/review-budget-gate.json").read_text()
        )
        return evaluate(
            RecordedGate(fixture["cases"][self._testMethodName]),
            rows,
            "arc",
            "head",
            "digest",
            list(observed),
            list(impacts),
        )

    def test_missing_canonical_reducer_fails_loudly(self):
        from ops.orchestration.review_budget import load_gate

        # [LAW:no-silent-failure] Portable adapter tests cannot become a runtime
        # fallback when the real product-owned reducer is unavailable.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError) as refusal:
                load_gate(directory)
            self.assertEqual(
                Path(refusal.exception.filename),
                Path(directory).resolve() / "tools/review_loop_gate.py",
            )

    def test_fifth_p1_quarantines_and_sixth_is_not_admitted(self):
        observed = [["old", "3", f"h{n}", "d"] for n in range(4)]
        result = self.evaluate(rows_for("3", severity="P1"), observed)
        self.assertEqual(result["completed_passes"], 5)
        self.assertEqual(result["decision"], "quarantine")
        self.assertFalse(result["admit_review"])

    def test_two_consecutive_pass3_p1_stop_before_five(self):
        result = self.evaluate(
            rows_for("3", "old", "P1") + rows_for("3", severity="P1")
        )
        self.assertEqual(result["completed_passes"], 2)
        self.assertEqual(result["decision"], "quarantine")

    def test_unavailable_and_partial_reviews_do_not_complete(self):
        result = self.evaluate(rows_for("1", unavailable=True) + rows_for("1")[:2])
        self.assertEqual(result["completed_passes"], 0)
        self.assertNotEqual(result["decision"], "code_verified")

    def test_clear_does_not_reset_prior_bindings_and_duplicates_do_not_count(self):
        result = self.evaluate(rows_for("3"), [["arc", "3", "head", "digest"]])
        self.assertEqual(result["completed_passes"], 1)
        self.assertEqual(result["decision"], "code_verified")

    def test_p2_is_not_nonblocking_from_severity_alone(self):
        result = self.evaluate(rows_for("1", severity="P2"))
        self.assertEqual(result["decision"], "fix_required")
        self.assertIn("1-head", result["blocking_findings"])

    def test_independently_adjudicated_prose_is_followup_but_cycle_still_required(self):
        rows = rows_for("1", severity="P2")
        result = self.evaluate(
            rows,
            impacts=[
                {
                    "finding_id": "1-head",
                    "impact": "prose_no_behavior",
                    "actor": "independent_absorber",
                    "producer": "codex_review_wrapper",
                    "evidence": "receipt-sha256",
                }
            ],
        )
        self.assertEqual(result["blocking_findings"], [])
        self.assertEqual(result["followups"], ["1-head"])
        self.assertNotEqual(result["decision"], "code_verified")

    def test_self_disposition_cannot_excuse_prose(self):
        with self.assertRaisesRegex(ValueError, "independent"):
            self.evaluate(
                rows_for("1", severity="P2"),
                impacts=[
                    {
                        "finding_id": "1-head",
                        "impact": "prose_no_behavior",
                        "actor": "codex_review_wrapper",
                        "producer": "codex_review_wrapper",
                        "evidence": "x",
                    }
                ],
            )

    def test_undisposed_finding_never_becomes_code_verified(self):
        result = self.evaluate(rows_for("3", severity="P3")[:-1])
        self.assertEqual(result["decision"], "adjudication_required")

    def test_fifth_clean_mandatory_terminal_can_verify(self):
        result = self.evaluate(
            rows_for("3", severity="P3"), [["old", "3", f"h{n}", "d"] for n in range(4)]
        )
        self.assertEqual(result["completed_passes"], 5)
        self.assertEqual(result["decision"], "code_verified")
        self.assertFalse(result["admit_review"])

    def test_pass2_p1_on_fix_delta_blocks_same_head_full_diff_admission(self):
        rows = rows_for("1", "old") + rows_for("2", severity="P1")
        for row in rows:
            if row.get("cycle_pass") == "2":
                row["diff_digest"] = "fix-delta-digest"
        result = self.evaluate(rows)
        self.assertEqual(result["decision"], "fix_required")
        self.assertIn("2-head", result["blocking_findings"])
        self.assertFalse(result["admit_review"])
