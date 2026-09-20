"""Versioned, content-safe snapshots for offline observability consumers."""
from dataclasses import dataclass
from collections.abc import Mapping

from .evaluation import promotion
from .projections import is_stale
from .views import compact as compact_view
from .views import detailed as detailed_view


@dataclass(frozen=True)
class Available:
    """A source whose evidence can be read without side effects."""

    value: object


@dataclass(frozen=True)
class Unreadable:
    """A source that could not supply trustworthy evidence."""


@dataclass(frozen=True)
class Contradictory:
    """Sources whose disagreement prevents a trustworthy presentation."""


@dataclass(frozen=True)
class ProjectionEvidence:
    """The replay result and journal used to establish its freshness."""

    projection: object
    journal: object


@dataclass(frozen=True)
class DetailEvidence:
    """Public-safe diagnostic input tied to one projection and journal."""

    projection: object
    journal: object
    diagnostics: object


@dataclass(frozen=True)
class ReviewEvidence:
    """Comparison evidence only; this record carries no executable capability."""

    active: object
    candidate: object
    labels: object
    rollback_ready: object


def snapshot(*, compact, detail, review):
    """Return detached offline observation without reading, retaining, or acting on sources."""
    # [LAW:effects-at-boundaries] Inputs contain all observations; this boundary performs no I/O.
    return {
        "version": "observability-adapter/v1",
        "compact": _projection_section(compact, compact_view),
        "detail": _detail_section(detail),
        "review": _review_section(review),
    }


def _projection_section(source, render):
    # [LAW:parse-dont-validate] Closed source states make availability explicit at this seam.
    failure = _failure_section(source)
    if failure is not None:
        return failure
    if not isinstance(source.value, ProjectionEvidence):
        return _unreadable()
    try:
        freshness = "stale" if is_stale(source.value.projection, source.value.journal) else "current"
        return {"source_state": "available", "freshness": freshness,
                "data": _detach(render(source.value.projection))}
    except Exception:
        # [LAW:no-silent-failure] A failed source remains visible rather than becoming healthy data.
        return _unreadable()


def _detail_section(source):
    failure = _failure_section(source)
    if failure is not None:
        return failure
    if not isinstance(source.value, DetailEvidence):
        return _unreadable()
    try:
        freshness = "stale" if is_stale(source.value.projection, source.value.journal) else "current"
        return {"source_state": "available", "freshness": freshness,
                "data": _detach(detailed_view(source.value.projection, source.value.diagnostics))}
    except Exception:
        return _unreadable()


def _review_section(source):
    failure = _failure_section(source)
    if failure is not None:
        return failure
    if not isinstance(source.value, ReviewEvidence):
        return _unreadable()
    try:
        decision = promotion(source.value.active, source.value.candidate,
                             labels=source.value.labels, rollback_ready=source.value.rollback_ready)
        # [LAW:single-enforcer] Evaluation owns the comparison; this adapter only renders its evidence.
        return {
            "source_state": "available",
            "freshness": "not-applicable",
            "evidence": {
                "comparison": "qualified" if decision["decision"] == "promote" else "incomplete",
                "regressions": list(decision["regressions"]),
                "reasons": list(decision["reasons"]),
            },
        }
    except Exception:
        return _unreadable()


def _failure_section(source):
    if isinstance(source, Unreadable):
        return _unreadable()
    if isinstance(source, Contradictory):
        return {"source_state": "contradictory", "freshness": "unknown"}
    if isinstance(source, Available):
        return None
    return _unreadable()


def _unreadable():
    return {"source_state": "unreadable", "freshness": "unknown"}


def _detach(value):
    # [LAW:one-source-of-truth] The returned snapshot owns its copy; it never aliases source evidence.
    if isinstance(value, Mapping):
        return {key: _detach(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_detach(item) for item in value]
    return value
