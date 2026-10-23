from datetime import datetime, timedelta, timezone
import unittest

from ops.orchestration import workflow_metrics as wm


T0 = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def row(unit, stage, start, seconds, **changes):
    """One receipt row as a producer would emit it, offset from a shared UTC origin."""
    base = dict(
        unit=unit,
        behavior=f"{unit} delivered behavior",
        policy_version="arhugula-trial-v1@1",
        candidate="cand-1",
        stage=stage,
        activity="active",
        producer="producer",
        session="session",
        run="run",
        outcome="passed",
        monotonic_start=5000 + start,
        monotonic_end=5000 + start + seconds,
        utc_start=(T0 + timedelta(seconds=start)).isoformat(),
        inputs=[],
        evidence=["receipt"],
    )
    base.update(changes)
    return base


def reduce(*rows):
    return wm.reduce_metrics([wm.parse_event(r) for r in rows])


def conditions(**changes):
    base = dict(
        runner_image="ubuntu-24.04-arm@20261020",
        runner_resources="4cpu-16g",
        suites="package+parity@v1",
        lock="uv.lock:abc",
        checkers="pytest8/pyright1",
        cache="warm",
    )
    base.update(changes)
    return wm.CiConditions(**base)


def ci_run(execution, cond=None, classification=15.0, queue=40.0):
    return wm.CiRun(
        run="run-new",
        execution=execution,
        classification=classification,
        runner_queue=queue,
        conditions=cond or conditions(),
    )


class DeliveryTimingTest(unittest.TestCase):
    def test_overlapping_review_ci_is_not_summed(self):
        report = reduce(
            row("u1", "implementation", 0, 100),
            row("u1", "review", 100, 300),
            row("u1", "ci_queue", 120, 30),
            row("u1", "ci_execution", 150, 250, run="package"),
            row("u1", "ci_execution", 150, 300, run="parity"),
            row("u1", "integration", 450, 50),
        )
        (unit,) = report.units
        # Serial addition would give 100 + 300 + 30 + 250 + 300 + 50 = 1030.
        self.assertEqual(unit.elapsed_seconds, 500)
        self.assertEqual(unit.unrecorded_seconds, 0)
        self.assertEqual(unit.stage_seconds[wm.Stage.REVIEW], 300)
        # Parallel package/parity jobs occupy one 300-second window, not 550 seconds.
        self.assertEqual(unit.stage_seconds[wm.Stage.CI_EXECUTION], 300)

    def test_gaps_without_receipts_stay_visible(self):
        report = reduce(
            row("u1", "implementation", 0, 100),
            row("u1", "review", 160, 40),
        )
        (unit,) = report.units
        self.assertEqual(unit.elapsed_seconds, 200)
        self.assertEqual(unit.unrecorded_seconds, 60)

    def test_missing_time_is_unknown(self):
        report = reduce(
            row("u1", "implementation", 0, 100),
            row("u1", "review", 100, 50, monotonic_end=None),
            row("u1", "integration", 150, 10),
        )
        (unit,) = report.units
        review = unit.stage_seconds[wm.Stage.REVIEW]
        self.assertIsInstance(review, wm.Unknown)
        self.assertIn("monotonic_end", review.reason)
        self.assertIsInstance(unit.elapsed_seconds, wm.Unknown)
        self.assertIsInstance(unit.unrecorded_seconds, wm.Unknown)
        # A missing receipt elsewhere does not erase what other receipts established.
        self.assertEqual(unit.stage_seconds[wm.Stage.IMPLEMENTATION], 100)
        self.assertNotIn(wm.Stage.QUEUE, unit.stage_seconds)

    def test_queue_and_waits_are_separate_from_active_work(self):
        report = reduce(
            row("u1", "queue", 0, 30),
            row("u1", "implementation", 30, 100),
            row("u1", "review", 130, 20, activity="capability_wait"),
            row("u1", "review", 150, 40),
            row("u1", "ci_queue", 190, 25, activity="resource_contention"),
            row("u1", "startup", 215, 5, activity="refresh_hold"),
        )
        (unit,) = report.units
        self.assertEqual(unit.stage_seconds[wm.Stage.QUEUE], 30)
        self.assertEqual(unit.stage_seconds[wm.Stage.CI_QUEUE], 25)
        self.assertEqual(unit.activity_seconds[wm.Activity.ACTIVE], 170)
        self.assertEqual(unit.activity_seconds[wm.Activity.CAPABILITY_WAIT], 20)
        self.assertEqual(unit.activity_seconds[wm.Activity.RESOURCE_CONTENTION], 25)
        self.assertEqual(unit.activity_seconds[wm.Activity.REFRESH_HOLD], 5)

    def test_rework_failures_and_repeated_checks_are_counted(self):
        report = reduce(
            row("u1", "local_verification", 0, 10, inputs=["head:a", "lock:x"]),
            row("u1", "local_verification", 10, 10, inputs=["lock:x", "head:a"]),
            row("u1", "local_verification", 20, 10, inputs=["head:b", "lock:x"]),
            row("u1", "ci_execution", 30, 100, outcome="failed"),
            row("u1", "correction", 130, 40),
            row("u1", "correction", 170, 20),
            row("u1", "ci_execution", 190, 100, candidate="cand-2"),
        )
        (unit,) = report.units
        self.assertEqual(unit.repeated_checks, 1)
        self.assertEqual(unit.rework, 2)
        self.assertEqual(unit.stage_seconds[wm.Stage.CORRECTION], 60)
        self.assertEqual(unit.failed_runs, 1)

    def test_two_reports_require_substantive_deliveries(self):
        events = [
            row("product-1", "implementation", 0, 100),
            row("product-1", "integration", 100, 10),
            row("bookkeeping", "implementation", 0, 5, behavior=None),
            row("bookkeeping", "integration", 5, 5, behavior=None),
            row("product-2", "implementation", 0, 100),
            row("product-2", "integration", 100, 10, outcome="failed"),
        ]
        report = reduce(*events)
        self.assertEqual(report.first_substantive, ("product-1",))
        self.assertFalse(report.before_after_ready)
        self.assertIn("further samples", report.sample_limit)

        events += [
            row("product-3", "implementation", 0, 100),
            row("product-3", "integration", 100, 10),
            row("product-2", "integration", 200, 10),
        ]
        report = reduce(*events)
        # Completion follows receipt append order, not unit naming or first appearance.
        self.assertEqual(report.first_substantive, ("product-1", "product-3"))
        self.assertTrue(report.before_after_ready)
        self.assertIn("further samples", report.sample_limit)

    def test_units_with_conflicting_behavior_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "behavior"):
            reduce(
                row("u1", "implementation", 0, 10),
                row("u1", "integration", 10, 10, behavior="something else"),
            )


class ReceiptParseTest(unittest.TestCase):
    def test_malformed_receipts_fail_loudly(self):
        bad = [
            row("u1", "implementation", 0, 10, monotonic_end=4000),
            row("u1", "implementation", 0, 10, utc_start="2026-10-23T12:00:00"),
            row("u1", "deployment", 0, 10),
            row("u1", "implementation", 0, 10, outcome="maybe"),
            row("", "implementation", 0, 10),
            row("u1", "implementation", 0, 10, monotonic_start=True),
        ]
        missing_behavior = row("u1", "implementation", 0, 10)
        del missing_behavior["behavior"]
        for receipt in bad + [missing_behavior]:
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                wm.parse_event(receipt)

    def test_absent_timestamp_is_unknown_not_zero(self):
        receipt = row("u1", "implementation", 0, 10)
        del receipt["utc_start"]
        timing = wm.parse_event(receipt).timing
        self.assertIsInstance(timing, wm.Unknown)
        self.assertIn("utc_start", timing.reason)


class CiComparisonTest(unittest.TestCase):
    def test_queue_and_classification_are_separate(self):
        run = ci_run(wm.SplitJobs(package=200.0, parity=300.0, aggregate=20.0))
        baseline = ci_run(wm.SequentialJob(636.0))
        result = wm.compare_ci(run, baseline)
        # max(package, parity) + aggregate; queue (40) and classification (15) excluded.
        self.assertEqual(result.execution_seconds, 320)
        self.assertEqual(result.classification_seconds, 15)
        self.assertEqual(result.runner_queue_seconds, 40)
        self.assertEqual(result.target, wm.Target.MET)
        self.assertEqual(result.speedup_seconds, 316)

    def test_inseparable_components_make_target_unknown(self):
        run = ci_run(wm.SplitJobs(package=200.0, parity=wm.Unknown("no job end"), aggregate=20.0))
        result = wm.compare_ci(run, ci_run(wm.SequentialJob(636.0)))
        self.assertIsInstance(result.execution_seconds, wm.Unknown)
        self.assertEqual(result.target, wm.Target.UNKNOWN)
        self.assertIsInstance(result.speedup_seconds, wm.Unknown)

    def test_runner_change_prevents_speedup_claim(self):
        baseline = ci_run(wm.SequentialJob(636.0))
        for changed, field in (
            (conditions(runner_image="ubuntu-24.04-arm@20261101"), "runner_image"),
            (conditions(suites="package+parity@v2"), "suites"),
            (conditions(cache="cold"), "cache"),
        ):
            with self.subTest(field=field):
                result = wm.compare_ci(
                    ci_run(wm.SplitJobs(package=200.0, parity=300.0, aggregate=20.0), changed),
                    baseline,
                )
                self.assertEqual(result.incomparable, (field,))
                self.assertEqual(result.execution_seconds, 320)
                self.assertEqual(result.target, wm.Target.UNKNOWN)
                self.assertIsInstance(result.speedup_seconds, wm.Unknown)
                self.assertFalse(result.disposition_required)

    def test_both_cold_is_still_not_comparable(self):
        cold = conditions(cache="cold")
        result = wm.compare_ci(
            ci_run(wm.SplitJobs(package=200.0, parity=300.0, aggregate=20.0), cold),
            ci_run(wm.SequentialJob(636.0), cold),
        )
        self.assertEqual(result.incomparable, ("cache",))
        self.assertEqual(result.target, wm.Target.UNKNOWN)

    def test_missed_target_requires_disposition(self):
        result = wm.compare_ci(
            ci_run(wm.SplitJobs(package=200.0, parity=480.0, aggregate=20.0)),
            ci_run(wm.SequentialJob(636.0)),
        )
        self.assertEqual(result.target, wm.Target.MISSED)
        self.assertTrue(result.disposition_required)
        self.assertEqual(result.speedup_seconds, 136)

    def test_historical_sample_keeps_its_limits(self):
        baseline = wm.HISTORICAL_BASELINE
        self.assertEqual(baseline.run, "37288061295")
        self.assertEqual(baseline.execution.critical(), 636)
        result = wm.compare_ci(ci_run(wm.SplitJobs(package=200.0, parity=300.0, aggregate=20.0)))
        self.assertEqual(result.baseline_run, "37288061295")
        self.assertEqual(result.baseline_execution_seconds, 636)
        # Its runner, suite and cache conditions were never recorded, so no numeric claim.
        self.assertEqual(set(result.incomparable), set(vars(conditions())))
        self.assertEqual(result.target, wm.Target.UNKNOWN)
        self.assertIsInstance(result.speedup_seconds, wm.Unknown)
        self.assertIn("single sample", result.baseline_limit)
        self.assertIn("37288061295", result.baseline_limit)


if __name__ == "__main__":
    unittest.main()
