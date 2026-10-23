"""Behavioral tests for the Memento same-window Buford reset core."""

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "ops" / "orchestration" / "vendor" / "memento"
ROW = {"role": "buford", "ceiling": 200000, "reserve": 15000, "task_budget": 20000}


def summary(**changes):
    value = {
        "kind": "codex",
        "session_id": "01a165ea-9859-7551-9ec4-82ace6fd4419",
        "identity_conflict": False,
        "model": "gpt-6.1-sol",
        "status": "complete",
        "latest_request_input_tokens": 100000,
        "latest_response_output_tokens": 1000,
        "reported_context_window_tokens": 475000,
        "metric_error": None,
        "completion_count": 3,
    }
    value.update(changes)
    return value


class Layers:
    def __init__(self, test):
        self.directory = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.directory))

    def write(self, text, name="codex.conf"):
        path = self.directory / name
        path.write_text(text)
        return [path]


class VendorPin(unittest.TestCase):
    def test_vendored_upstream_bytes_equal_the_pin(self):
        pin = json.loads((VENDOR / "PIN.json").read_text())
        self.assertEqual(pin["commit"], "4f95f15954318b2bebe8996d52ec8191aba85c42")
        for name, record in pin["files"].items():
            digest = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
            self.assertEqual(digest, record["sha256"], name)
        self.assertEqual(
            pin["files"]["ceiling_config.py"]["sha256"],
            "cdcc1d8fdc98424b2ca7bab0d2e628145c1eea462bcb110fd2237805dab7382c",
        )

    def test_adapter_uses_only_the_three_pinned_upstream_names(self):
        tree = ast.parse((ROOT / "ops" / "orchestration" / "ceiling.py").read_text())
        used = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "memento"
        }
        self.assertEqual(used, {"ceiling_in", "folded", "GRACE"})


class BoundRule(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import ceiling

        self.ceiling = ceiling
        self.layers = Layers(self)

    def bound(self, layer="ceiling = 150_000\n", row=ROW, **changes):
        measurement = self.ceiling.Measurement.parse(summary(**changes))
        return self.ceiling.Bound.resolve(row, self.layers.write(layer), measurement)

    def test_worked_example(self):
        bound = self.bound()
        self.assertEqual(
            (bound.ceiling, bound.reserve, bound.close, bound.soft, bound.grace),
            (200000, 15000, 185000, 150000, 35000),
        )
        self.assertEqual(bound.limit, 185000)

    def test_window_below_operating_ceiling_lowers_the_bound(self):
        bound = self.bound(reported_context_window_tokens=180000)
        self.assertEqual((bound.ceiling, bound.close), (180000, 165000))

    def test_larger_measured_handoff_reserve_lowers_hard_close(self):
        measurement = self.ceiling.Measurement.parse(summary())
        bound = self.ceiling.Bound.resolve(
            ROW, self.layers.write("ceiling = 150_000\n"), measurement, handoff_reserve=40000
        )
        self.assertEqual((bound.reserve, bound.close, bound.grace), (40000, 160000, 10000))

    def test_grace_is_a_maximum_not_added_capacity(self):
        bound = self.bound("ceiling = 50_000\n")
        self.assertEqual((bound.grace, bound.limit), (100000, 150000))

    def test_off_nonpositive_signed_and_above_close_refuse(self):
        for text in ("ceiling = off\n", "ceiling = 0\n", "ceiling = 190_000\n", "ceiling = -400_000\n"):
            with self.subTest(text=text), self.assertRaises(self.ceiling.CeilingHold):
                self.bound(text)

    def test_missing_or_malformed_layer_holds_instead_of_exiting(self):
        with self.assertRaises(self.ceiling.CeilingHold):
            self.ceiling.Bound.resolve(
                ROW, [self.layers.directory / "absent.conf"], self.ceiling.Measurement.parse(summary())
            )
        with self.assertRaises(self.ceiling.CeilingHold):
            self.bound("limit = 150_000\n")

    def test_bands_at_boundaries(self):
        bound = self.bound()
        band = self.ceiling.band
        self.assertEqual(band(149999, bound), "under")
        self.assertEqual(band(150000, bound), "finish")
        self.assertEqual(band(184999, bound), "finish")
        self.assertEqual(band(185000, bound), "close")


class MeasuredAdmission(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import ceiling

        self.ceiling = ceiling
        self.layers = Layers(self).write("ceiling = 150_000\n")

    def decide(self, expected=None, **changes):
        measurement = self.ceiling.Measurement.parse(summary(**changes))
        bound = self.ceiling.Bound.resolve(ROW, self.layers, measurement)
        return self.ceiling.decide(measurement, bound, ROW["task_budget"], expected=expected)

    def test_unknown_identity_model_window_or_metric_holds(self):
        for change in (
            {"session_id": None},
            {"model": None},
            {"reported_context_window_tokens": None},
            {"latest_request_input_tokens": None},
            {"identity_conflict": True},
            {"metric_error": "partial"},
        ):
            with self.subTest(change=change), self.assertRaises(self.ceiling.CeilingHold):
                self.decide(**change)

    def test_changed_identity_model_or_window_holds(self):
        expected = self.ceiling.Measurement.parse(summary()).identity
        for change in (
            {"session_id": "01a10e35-d6c4-7282-9ef8-2c7c8629ae4a"},
            {"model": "gpt-6-sol"},
            {"reported_context_window_tokens": 258400},
        ):
            with self.subTest(change=change), self.assertRaises(self.ceiling.CeilingHold):
                self.decide(expected=expected, **change)

    def test_each_lane_window_gets_its_own_bound(self):
        worker = self.ceiling.Measurement.parse(summary(reported_context_window_tokens=180000))
        bound = self.ceiling.Bound.resolve(ROW, self.layers, worker)
        self.assertEqual((bound.ceiling, bound.close, bound.identity.window), (180000, 165000, 180000))
        small = self.ceiling.Measurement.parse(summary(reported_context_window_tokens=150000))
        with self.assertRaises(self.ceiling.CeilingHold):
            self.ceiling.Bound.resolve(ROW, self.layers, small)

    def test_budget_and_reserve_must_fit_even_below_soft_threshold(self):
        decision = self.decide(latest_request_input_tokens=170000, latest_response_output_tokens=0)
        self.assertEqual(decision.band, "finish")
        decision = self.decide(latest_request_input_tokens=140000, latest_response_output_tokens=0)
        self.assertEqual((decision.band, decision.admit), ("under", True))
        tight = dict(ROW, task_budget=60000)
        measurement = self.ceiling.Measurement.parse(summary(latest_request_input_tokens=140000, latest_response_output_tokens=0))
        decision = self.ceiling.decide(measurement, self.ceiling.Bound.resolve(tight, self.layers, measurement), 60000)
        self.assertEqual((decision.band, decision.admit), ("under", False))
        self.assertIn("insufficient-headroom", decision.reasons)

    def test_over_operating_ceiling_lane_must_close_out(self):
        decision = self.decide(latest_request_input_tokens=244059, latest_response_output_tokens=1650)
        self.assertEqual((decision.band, decision.admit), ("close", False))
        self.assertIn("released boundary", decision.instruction)

    def test_one_decision_key_per_completed_turn(self):
        one, two = self.decide(), self.decide()
        self.assertEqual(one.turn, two.turn)
        self.assertNotEqual(one.turn, self.decide(completion_count=4).turn)


if __name__ == "__main__":
    unittest.main()
