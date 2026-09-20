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
    evaluator_consensus: bool = False

    def __post_init__(self):
        if self.source not in {"synthetic", "recorded", "live"}:
            raise ValueError("unsupported replay source")
        if not all(type(value) is bool for value in (self.pinned, self.deterministic,
                                                       self.independently_evaluated,
                                                       self.evaluator_consensus)):
            raise ValueError("replay evidence flags must be booleans")
        if type(self.version) is not str or not self.version:
            raise ValueError("version must be nonempty text")
        if type(self.bundle_id) is not str or not self.bundle_id:
            raise ValueError("bundle ID must be nonempty text")
        if not isinstance(self.outcomes, dict) or not self.outcomes or not all(type(key) is str and key and value in {"pass", "fail"}
                                                          for key, value in self.outcomes.items()):
            raise ValueError("outcomes must map case IDs to pass or fail")
        object.__setattr__(self, "outcomes", MappingProxyType(dict(self.outcomes)))


def promotion(active, candidate, *, labels=(), rollback_ready=False):
    """Return a non-authoritative promotion decision from immutable evidence."""
    if not isinstance(labels, (tuple, frozenset)) or not all(label in {"approved", "rejected"}
                                                              for label in labels):
        raise ValueError("labels must be an exact approved/rejected collection")
    if type(rollback_ready) is not bool:
        raise ValueError("rollback readiness must be boolean")
    regressions = tuple(case for case, result in active.outcomes.items()
                        if result == "pass" and candidate.outcomes.get(case) != "pass")
    reasons = []
    if not active.pinned:
        reasons.append("baseline-pinned-replay-required")
    if not active.deterministic:
        reasons.append("baseline-deterministic-replay-required")
    if not active.independently_evaluated:
        reasons.append("baseline-independent-evaluation-required")
    if not active.evaluator_consensus:
        reasons.append("baseline-independent-evaluator-disagreement")
    if not candidate.pinned:
        reasons.append("pinned-replay-required")
    if not candidate.deterministic:
        reasons.append("deterministic-replay-required")
    if not candidate.independently_evaluated:
        reasons.append("independent-evaluation-required")
    if not candidate.evaluator_consensus:
        reasons.append("independent-evaluator-disagreement")
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
