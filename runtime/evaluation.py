"""Deterministic, read-only replay comparison and promotion gates."""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ReplayRun:
    """A bounded evaluation result; it never invokes a replay source."""
    version: str
    source: str
    bundle_id: str
    pinned: bool
    deterministic: bool
    independently_evaluated: bool
    outcomes: dict

    def __post_init__(self):
        if self.source not in {"synthetic", "recorded", "live"}:
            raise ValueError("unsupported replay source")
        if not all(type(value) is bool for value in (self.pinned, self.deterministic,
                                                       self.independently_evaluated)):
            raise ValueError("replay evidence flags must be booleans")
        if not isinstance(self.outcomes, dict) or not all(type(key) is str and value in {"pass", "fail"}
                                                          for key, value in self.outcomes.items()):
            raise ValueError("outcomes must map case IDs to pass or fail")
        object.__setattr__(self, "outcomes", MappingProxyType(dict(self.outcomes)))


def promotion(active, candidate, *, labels=(), rollback_ready=False):
    """Return a non-authoritative promotion decision from immutable evidence."""
    regressions = tuple(case for case, result in active.outcomes.items()
                        if result == "pass" and candidate.outcomes.get(case) != "pass")
    reasons = []
    if not active.pinned:
        reasons.append("baseline-pinned-replay-required")
    if not active.deterministic:
        reasons.append("baseline-deterministic-replay-required")
    if not active.independently_evaluated:
        reasons.append("baseline-independent-evaluation-required")
    if not candidate.pinned:
        reasons.append("pinned-replay-required")
    if not candidate.deterministic:
        reasons.append("deterministic-replay-required")
    if not candidate.independently_evaluated:
        reasons.append("independent-evaluation-required")
    if candidate.bundle_id != active.bundle_id:
        reasons.append("replay-bundle-mismatch")
    if candidate.source != active.source:
        reasons.append("replay-source-mismatch")
    if candidate.outcomes.keys() != active.outcomes.keys():
        reasons.append("replay-coverage-incomplete")
    if regressions:
        reasons.append("replay-regression")
    if "fail" in candidate.outcomes.values():
        reasons.append("candidate-failure")
    if "approved" not in labels:
        reasons.append("manual-approval-required")
    if not rollback_ready:
        reasons.append("rollback-readiness-required")
    if "rejected" in labels:
        reasons.append("manual-rejection")
    return {"decision": "promote" if not reasons else "hold", "regressions": regressions,
            "reasons": tuple(reasons)}
