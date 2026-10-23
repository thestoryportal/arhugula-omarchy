"""Workflow timing reduced from existing stage receipts, never from ticket or comment counts.

Overlapping intervals count once, a missing timestamp stays unknown, and CI queue and
classification stay outside the package/parity execution comparison. The reducer is
pure: it reads immutable receipt rows and gates nothing, so it can run asynchronously.
"""

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping, Sequence


class Stage(Enum):
    QUEUE = "queue"
    STARTUP = "startup"
    IMPLEMENTATION = "implementation"
    LOCAL_VERIFICATION = "local_verification"
    REVIEW = "review"
    CORRECTION = "correction"
    CI_QUEUE = "ci_queue"
    CI_EXECUTION = "ci_execution"
    INTEGRATION = "integration"
    INSTALLED_ACCEPTANCE = "installed_acceptance"
    CLEANUP = "cleanup"


CHECK_STAGES = frozenset(
    {Stage.LOCAL_VERIFICATION, Stage.REVIEW, Stage.CI_EXECUTION, Stage.INSTALLED_ACCEPTANCE}
)


class Activity(Enum):
    ACTIVE = "active"
    RESOURCE_CONTENTION = "resource_contention"
    CAPABILITY_WAIT = "capability_wait"
    REFRESH_HOLD = "refresh_hold"


class Outcome(Enum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Unknown:
    """A duration no receipt established. It is never zero and never estimated."""

    reason: str


@dataclass(frozen=True)
class Interval:
    """A stage's place on the shared UTC timeline.

    The length comes from the producer's monotonic clock and the UTC start only places
    it, so wall-clock adjustments cannot change how long a stage took.
    """

    utc_start: datetime
    seconds: float

    @property
    def utc_end(self):
        return self.utc_start + timedelta(seconds=self.seconds)


@dataclass(frozen=True)
class StageEvent:
    unit: str
    # None: workflow bookkeeping that delivered no product behavior.
    behavior: "str | None"
    policy_version: str
    candidate: str
    stage: Stage
    activity: Activity
    producer: str
    session: str
    run: str
    outcome: Outcome
    timing: "Interval | Unknown"
    inputs: frozenset
    evidence: tuple


_TIMESTAMPS = ("monotonic_start", "monotonic_end", "utc_start")


def parse_event(row: Mapping) -> StageEvent:
    """Bind one receipt row. A missing timestamp becomes Unknown; a malformed row raises."""
    # [LAW:parse-dont-validate] Reducers accept only StageEvent, so nothing inland re-checks.
    if "behavior" not in row:
        raise ValueError("receipt lacks behavior; use null for bookkeeping")
    behavior = row["behavior"]
    return StageEvent(
        unit=_text(row, "unit"),
        behavior=None if behavior is None else _text(row, "behavior"),
        policy_version=_text(row, "policy_version"),
        candidate=_text(row, "candidate"),
        stage=Stage(row.get("stage")),
        activity=Activity(row.get("activity")),
        producer=_text(row, "producer"),
        session=_text(row, "session"),
        run=_text(row, "run"),
        outcome=Outcome(row.get("outcome")),
        timing=_timing(row),
        inputs=frozenset(_texts(row, "inputs")),
        evidence=tuple(_texts(row, "evidence")),
    )


def _text(row, key):
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"receipt {key} must be non-empty text")
    return value


def _texts(row, key):
    values = row.get(key)
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise ValueError(f"receipt {key} must be a list of non-empty text")
    return values


def _number(row, key):
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"receipt {key} must be a number")
    return value


def _timing(row):
    missing = [key for key in _TIMESTAMPS if row.get(key) is None]
    if missing:
        return Unknown("receipt lacks " + ", ".join(missing))
    seconds = _number(row, "monotonic_end") - _number(row, "monotonic_start")
    if seconds < 0:
        raise ValueError("receipt monotonic_end precedes monotonic_start")
    start = datetime.fromisoformat(_text(row, "utc_start"))
    if start.utcoffset() is None:
        raise ValueError("receipt utc_start lacks a UTC offset")
    return Interval(start, seconds)


@dataclass(frozen=True)
class UnitReport:
    unit: str
    behavior: "str | None"
    policy_versions: tuple
    completed: bool
    # First receipt start to last receipt end on the shared timeline.
    elapsed_seconds: "float | Unknown"
    # Elapsed time no receipt covers; overlapping stages are counted once.
    unrecorded_seconds: "float | Unknown"
    stage_seconds: Mapping
    activity_seconds: Mapping
    repeated_checks: int
    rework: int
    # Distinct producer runs with at least one failed stage.
    failed_runs: int


@dataclass(frozen=True)
class MeasurementReport:
    units: tuple
    # Closed product units in verified closure order, at most the first two.
    first_substantive: tuple

    @property
    def before_after_ready(self):
        return len(self.first_substantive) == 2

    @property
    def sample_limit(self):
        return (
            f"{len(self.first_substantive)} of the first 2 completed substantive deliveries; "
            "further samples are required before generalizing savings"
        )


@dataclass(frozen=True)
class Closure:
    """A verified ticket closure: review, CI, main landing, post-main CI and applicable
    installed acceptance all passed. Stage receipts alone never establish completion."""

    unit: str
    evidence: str


def reduce_metrics(events: Sequence[StageEvent], closures: Sequence[Closure] = ()) -> MeasurementReport:
    """Report every unit; closures are given in verified closure order."""
    by_unit = {}
    for event in events:
        by_unit.setdefault(event.unit, []).append(event)
    closed = [closure.unit for closure in closures]
    unreported = sorted(set(closed) - set(by_unit))
    if unreported:
        raise ValueError("closed units have no stage receipts: " + ", ".join(unreported))
    # [LAW:one-source-of-truth] Completion comes from closure records, not stage outcomes.
    units = tuple(_unit_report(unit, group, unit in closed) for unit, group in by_unit.items())
    behaviors = {report.unit: report.behavior for report in units}
    substantive = [unit for unit in dict.fromkeys(closed) if behaviors[unit] is not None]
    return MeasurementReport(units=units, first_substantive=tuple(substantive[:2]))


def _unit_report(unit, events, completed):
    behaviors = {event.behavior for event in events}
    if len(behaviors) != 1:
        raise ValueError(f"unit {unit} receipts disagree on delivered behavior")
    elapsed = _elapsed(events)
    covered = _covered(events)
    return UnitReport(
        unit=unit,
        behavior=behaviors.pop(),
        policy_versions=tuple(sorted({event.policy_version for event in events})),
        completed=completed,
        elapsed_seconds=elapsed,
        unrecorded_seconds=_difference(elapsed, covered),
        stage_seconds=_grouped(events, lambda event: event.stage),
        activity_seconds=_grouped(events, lambda event: event.activity),
        repeated_checks=_repeated_checks(events),
        rework=sum(event.stage is Stage.CORRECTION for event in events),
        failed_runs=len({event.run for event in events if event.outcome is Outcome.FAILED}),
    )


def _intervals(events):
    """Every interval, or the Unknown that makes any span over these events unknown."""
    unknown = [event.timing.reason for event in events if isinstance(event.timing, Unknown)]
    if unknown:
        return Unknown("; ".join(sorted(set(unknown))))
    return sorted((event.timing for event in events), key=lambda interval: interval.utc_start)


def _covered(events):
    intervals = _intervals(events)
    if isinstance(intervals, Unknown):
        return intervals
    # [LAW:one-source-of-truth] Union length, so concurrent review/CI/parity count once.
    total = 0.0
    reached = datetime.min.replace(tzinfo=timezone.utc)
    for interval in intervals:
        if interval.utc_end > reached:
            total += (interval.utc_end - max(interval.utc_start, reached)).total_seconds()
            reached = interval.utc_end
    return total


def _elapsed(events):
    intervals = _intervals(events)
    if isinstance(intervals, Unknown):
        return intervals
    end = max(interval.utc_end for interval in intervals)
    return (end - intervals[0].utc_start).total_seconds()


def _difference(total, part):
    if isinstance(total, Unknown):
        return total
    return part if isinstance(part, Unknown) else total - part


def _grouped(events, key):
    groups = {}
    for event in events:
        groups.setdefault(key(event), []).append(event)
    return {name: _covered(group) for name, group in groups.items()}


def _repeated_checks(events):
    """Checks re-run on an already-checked candidate with the same declared inputs."""
    keys = [(event.stage, event.candidate, event.inputs) for event in events if event.stage in CHECK_STAGES]
    return len(keys) - len(set(keys))


TARGET_SECONDS = 450.0
WARM = "warm"


class Target(Enum):
    MET = "met"
    MISSED = "missed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CiConditions:
    runner_image: "str | Unknown"
    runner_resources: "str | Unknown"
    suites: "str | Unknown"
    lock: "str | Unknown"
    checkers: "str | Unknown"
    cache: "str | Unknown"


@dataclass(frozen=True)
class SplitJobs:
    """Package and parity jobs run in parallel; the aggregate job follows both.

    Each job's seconds include its setup and required teardown.
    """

    package: "float | Unknown"
    parity: "float | Unknown"
    aggregate: "float | Unknown"

    def critical(self):
        jobs = (self.package, self.parity, self.aggregate)
        unknown = [job.reason for job in jobs if isinstance(job, Unknown)]
        if unknown:
            return Unknown("; ".join(unknown))
        return max(self.package, self.parity) + self.aggregate


@dataclass(frozen=True)
class SequentialJob:
    """One job ran package tests and then parity, as in the historical sample."""

    seconds: float

    def critical(self):
        return self.seconds


@dataclass(frozen=True)
class CiRun:
    run: str
    execution: "SplitJobs | SequentialJob"
    classification: "float | Unknown"
    runner_queue: "float | Unknown"
    conditions: CiConditions


_UNRECORDED = Unknown("not recorded with run 37288061295")

# Package pytest took 243 s and parity 365 s inside this one job. Only the job total
# is the comparison baseline; its runner, suite, lock, checker and cache conditions
# were not recorded, so it supports no numeric speedup claim by itself.
HISTORICAL_BASELINE = CiRun(
    run="37288061295",
    execution=SequentialJob(636.0),
    classification=Unknown("excluded from the historical package/parity job"),
    runner_queue=_UNRECORDED,
    conditions=CiConditions(*(_UNRECORDED for _ in fields(CiConditions))),
)

# The target is defined for warm runners whose conditions were recorded.
_REQUIRED = {"cache": WARM}


@dataclass(frozen=True)
class CiComparison:
    run: str
    baseline_run: str
    execution_seconds: "float | Unknown"
    baseline_execution_seconds: "float | Unknown"
    classification_seconds: "float | Unknown"
    runner_queue_seconds: "float | Unknown"
    # Observed condition fields that are unrecorded or not warm; they block the target.
    unqualified: tuple
    # Fields also differing from, or unrecorded in, the baseline; they block a speedup claim.
    incomparable: tuple
    target: Target
    speedup_seconds: "float | Unknown"

    @property
    def disposition_required(self):
        return self.target is Target.MISSED

    @property
    def baseline_limit(self):
        return f"single sample: run {self.baseline_run}; not a distribution or delivery forecast"


def compare_ci(observed: CiRun, baseline: CiRun = HISTORICAL_BASELINE) -> CiComparison:
    execution = observed.execution.critical()
    baseline_execution = baseline.execution.critical()
    pairs = [
        (field.name, getattr(observed.conditions, field.name), getattr(baseline.conditions, field.name))
        for field in fields(CiConditions)
    ]
    unqualified = tuple(name for name, value, _ in pairs if not _qualified(name, value))
    incomparable = tuple(
        name for name, value, prior in pairs if not (_qualified(name, value) and value == prior)
    )
    # [LAW:single-enforcer] The target judges this run alone; baseline comparability
    # gates only the numeric speedup, so a missed target stays visible without one.
    target_blockers = [execution.reason] if isinstance(execution, Unknown) else []
    target_blockers += [f"{name} unrecorded or not warm" for name in unqualified]
    speedup_blockers = target_blockers + [f"{name} not comparable" for name in incomparable]
    if isinstance(baseline_execution, Unknown):
        speedup_blockers.append(baseline_execution.reason)
    if target_blockers:
        target = Target.UNKNOWN
    else:
        target = Target.MET if execution <= TARGET_SECONDS else Target.MISSED
    if speedup_blockers:
        speedup = Unknown("; ".join(speedup_blockers))
    else:
        speedup = baseline_execution - execution
    return CiComparison(
        run=observed.run,
        baseline_run=baseline.run,
        execution_seconds=execution,
        baseline_execution_seconds=baseline_execution,
        classification_seconds=observed.classification,
        runner_queue_seconds=observed.runner_queue,
        unqualified=unqualified,
        incomparable=incomparable,
        target=target,
        speedup_seconds=speedup,
    )


def _qualified(name, value):
    return isinstance(value, str) and _REQUIRED.get(name, value) == value
