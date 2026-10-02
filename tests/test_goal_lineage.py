import json
from pathlib import Path
import tempfile
import unittest


class GoalLineageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def receipt(self, session, tokens, seconds, objective="original scope"):
        path = self.root / (session + str(tokens) + ".json")
        path.write_text(
            json.dumps(
                {
                    "goal": {
                        "threadId": session,
                        "objective": objective,
                        "tokensUsed": tokens,
                        "timeUsedSeconds": seconds,
                        "status": "paused",
                    },
                    "remainingTokens": None,
                }
            )
        )
        return path

    def test_fresh_native_zero_cannot_erase_lifetime_usage_or_deadline(self):
        from ops.orchestration.goal_lineage import GoalLineage

        ledger = GoalLineage(self.root / "ledger.json")
        ledger.record(self.receipt("old", 870069, 2834), "2026-10-02T05:06:38Z")
        result = ledger.record(self.receipt("fresh", 0, 0), "2026-10-02T05:06:38Z")
        self.assertEqual(
            (result["tokens_used"], result["seconds_used"]), (870069, 2834)
        )
        self.assertEqual(result["deadline"], "2026-10-02T05:06:38Z")
        self.assertEqual(len(result["receipts"]), 2)

    def test_same_thread_receipts_update_max_without_double_count(self):
        from ops.orchestration.goal_lineage import GoalLineage

        ledger = GoalLineage(self.root / "ledger.json")
        ledger.record(self.receipt("old", 10, 1), "original")
        result = ledger.record(self.receipt("old", 12, 2), "original")
        self.assertEqual(result["tokens_used"], 12)
        self.assertEqual(len(result["receipts"]), 2)
        with self.assertRaisesRegex(ValueError, "regressed"):
            ledger.record(self.receipt("old", 11, 2), "original")

    def test_scope_deadline_and_unbounded_contract_cannot_change(self):
        from ops.orchestration.goal_lineage import GoalLineage

        ledger = GoalLineage(self.root / "ledger.json")
        ledger.record(self.receipt("old", 10, 1), "original")
        with self.assertRaisesRegex(ValueError, "contract"):
            ledger.record(self.receipt("new", 0, 0), "extended")
        with self.assertRaisesRegex(ValueError, "contract"):
            ledger.record(self.receipt("other", 0, 0, "smaller scope"), "original")

    def test_actual_absent_goal_retains_objective_and_totals_without_zero_thread(self):
        from ops.orchestration.goal_lineage import GoalLineage

        ledger = GoalLineage(self.root / "ledger.json")
        before = ledger.record(self.receipt("old", 870069, 2834), "original")
        path = self.root / "absent.json"
        path.write_text(
            json.dumps(
                {
                    "session_id": "new",
                    "tool_result": {
                        "goal": None,
                        "remainingTokens": None,
                        "completionBudgetReport": None,
                    },
                }
            )
        )
        result = ledger.record_absence(path, "original")
        for key in (
            "objective",
            "deadline",
            "objective_sha256",
            "threads",
            "tokens_used",
            "seconds_used",
        ):
            self.assertEqual(result[key], before[key])
        self.assertNotIn("new", result["threads"])
        self.assertEqual(result["absent_goals"][0]["session_id"], "new")
        self.assertEqual(ledger.record_absence(path, "original"), result)
        with self.assertRaisesRegex(ValueError, "contract"):
            ledger.record_absence(path, "extended")

    def test_absence_cannot_initialize_or_disguise_a_present_goal(self):
        from ops.orchestration.goal_lineage import GoalLineage

        ledger = GoalLineage(self.root / "ledger.json")
        path = self.root / "absent.json"
        path.write_text(
            json.dumps(
                {
                    "session_id": "new",
                    "tool_result": {
                        "goal": None,
                        "remainingTokens": None,
                        "completionBudgetReport": None,
                    },
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "original goal ledger"):
            ledger.record_absence(path, "original")
        ledger.record(self.receipt("old", 10, 1), "original")
        with self.assertRaises(ValueError):
            ledger.record_absence(self.receipt("new", 0, 0), "original")
