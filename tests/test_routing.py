import json
import subprocess
import sys
import unittest

from ops.orchestration.routing import route, route_backlog


def ticket(title="Unknown work", labels=()):
    return {"id": "unit", "title": title, "labels": list(labels), "issue_type": "task"}


class RoutingTests(unittest.TestCase):
    def test_capabilities_choose_model_effort_and_role(self):
        for capability, model, effort in [
            ("architecture", "gpt-6-astra", "high"),
            ("contracts", "gpt-6-astra", "high"),
            ("security", "gpt-6-astra", "high"),
            ("cross-cutting", "gpt-6-astra", "high"),
            ("session-lifecycle", "gpt-6-astra", "high"),
            ("model-routing", "gpt-6-astra", "high"),
            ("orchestration", "gpt-6-astra", "high"),
            ("debugging", "gpt-6-astra", "high"),
            ("high-risk-review", "gpt-6-astra", "high"),
            ("exploration", "gpt-5.6-terra", "medium"),
            ("inventory", "gpt-5.6-terra", "medium"),
            ("tests", "gpt-5.6-terra", "medium"),
            ("fixtures", "gpt-5.6-terra", "medium"),
            ("documentation", "gpt-5.6-terra", "medium"),
            ("bounded-implementation", "gpt-5.6-terra", "medium"),
            ("validation", "gpt-5.6-terra", "medium"),
            ("independent-review", "gpt-5.6-terra", "medium"),
        ]:
            with self.subTest(capability=capability):
                result = route(ticket(labels=[f"capability:{capability}", "autonomous-safe"]))
                self.assertEqual((result["model"], result["effort"]), (model, effort))
                self.assertEqual(result["decision"], "ready")

    def test_explicit_metadata_overrides_title_inference(self):
        result = route(ticket("Test model routing", ["capability:tests", "model:terra", "role:review", "effort:medium", "autonomous-safe"]))
        self.assertEqual((result["model"], result["role"]), ("gpt-5.6-terra", "review"))

    def test_high_risk_work_cannot_be_demoted_by_model_label(self):
        result = route(ticket(labels=["capability:security", "model:terra", "autonomous-safe"]))
        self.assertEqual(result["stop_reason"], "routing-conflict")

    def test_hil_in_parent_dominates_safe_leaf(self):
        result = route(ticket(labels=["capability:tests", "autonomous-safe"]), [ticket(labels=["hil-required"])])
        self.assertEqual(result["stop_reason"], "hil-required")

    def test_autonomy_is_never_inherited(self):
        result = route(ticket(labels=["capability:tests"]), [ticket(labels=["autonomous-safe"])])
        self.assertEqual(result["stop_reason"], "autonomy-unclassified")

    def test_ambiguity_unknown_and_conflicting_metadata_stop(self):
        for labels in [[], ["model:wat"], ["effort:low"], ["role:unknown"],
                       ["capability:magic"], ["model:astra", "model:terra"],
                       ["capability:tests", "effort:high"]]:
            with self.subTest(labels=labels):
                self.assertEqual(route(ticket(labels=labels + ["autonomous-safe"]))["decision"], "stop")

    def test_security_label_beats_bounded_capability(self):
        result = route(ticket(labels=["security", "capability:tests", "autonomous-safe"]))
        self.assertEqual(result["model"], "gpt-6-astra")

    def test_backlog_uses_actual_relations_and_stable_rank_order(self):
        data = {"version": 2, "issues": [
            {**ticket(labels=["hil-required"]), "id": "parent", "issue_type": "epic"},
            {**ticket(labels=["capability:tests", "autonomous-safe"]), "rank": "b"},
            {**ticket("Write documentation", ["autonomous-safe"]), "id": "first", "rank": "a"},
        ], "relations": [{"src_id": "unit", "dst_id": "parent", "type": "parent-child"}]}
        results = route_backlog(data)
        self.assertEqual([r["ticket"] for r in results], ["first", "unit"])
        self.assertEqual(results[1]["stop_reason"], "hil-required")
        self.assertEqual(results[0]["model"], "gpt-5.6-terra")

    def test_cycles_are_rejected(self):
        data = {"version": 2, "issues": [ticket()], "relations": [
            {"src_id": "unit", "dst_id": "unit", "type": "parent-child"}]}
        with self.assertRaises(ValueError):
            route_backlog(data)

    def test_cli_reads_export_without_writing(self):
        result = subprocess.run([sys.executable, "-m", "ops.orchestration.routing"],
            input=json.dumps({"version": 2, "issues": [ticket("Write documentation", ["autonomous-safe"])], "relations": []}),
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["routes"][0]["model"], "gpt-5.6-terra")


if __name__ == "__main__":
    unittest.main()
