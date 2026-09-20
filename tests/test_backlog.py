import json
from pathlib import Path
import unittest

from ops.orchestration.audit import materialize
from ops.orchestration.routing import route_backlog


class BacklogTests(unittest.TestCase):
    def test_current_backlog_has_explicit_assignment_for_every_leaf(self):
        data = json.loads(Path("tests/fixtures/lit-backlog.json").read_text())
        metadata = json.loads(Path("ops/orchestration/backlog-metadata.json").read_text())
        before = json.loads(json.dumps(data))
        updated = materialize(data, metadata)
        routes = route_backlog(updated)
        self.assertEqual(data, before, "dry-run must not mutate source data")
        self.assertEqual(len(routes), 35)
        self.assertFalse(any(r["stop_reason"] in {"routing-ambiguous", "routing-conflict"} for r in routes))
        models = {r["ticket"]: r["model"] for r in routes}
        self.assertEqual(models["arhugula-control-plane-jat.0db.gsk"], "gpt-6-astra")
        self.assertEqual(models["arhugula-catalog-gateway-yll.298.1qs"], "gpt-5.6-terra")
        self.assertEqual(models["arhugula-observability-xb8.xug.yoc"], "gpt-5.6-terra")
        self.assertEqual(models["arhugula-orchestration-3hx.8i8"], "gpt-6-astra")
        # Routing does not invent authority for the foundation or live config.
        self.assertEqual(next(r for r in routes if r["ticket"].endswith(".t78"))["stop_reason"], "autonomy-unclassified")

    def test_materialization_preserves_safety_and_unrelated_labels(self):
        data = {"version": 2, "issues": [{"id": "one", "labels": ["hil-required", "custom", "model:astra"]}], "relations": []}
        updated = materialize(data, {"version": 1, "capabilities": {"one": "fixtures"}})
        self.assertEqual(set(updated["issues"][0]["labels"]), {"hil-required", "custom", "model:terra", "effort:medium", "role:implement", "capability:fixtures"})

    def test_unknown_ids_and_capabilities_rejected_before_apply(self):
        for capabilities in [{"missing": "tests"}, {"one": "unknown"}]:
            with self.assertRaises(ValueError):
                materialize({"version": 2, "issues": [{"id": "one"}], "relations": []}, {"version": 1, "capabilities": capabilities})
