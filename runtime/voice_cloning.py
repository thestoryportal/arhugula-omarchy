"""Pure synthetic cloning-workflow metadata; never samples, effects, or authority."""
from dataclasses import dataclass
from enum import Enum

from runtime.voice_candidates import (
    AuthorityEvidence,
    CandidateBinding,
    CandidateRejection,
    CandidateRequest,
    QualityEvidence,
    QualityState,
    VoiceCandidate,
    represent_candidate,
)


def _sample_ids(value: object, name: str) -> frozenset[str]:
    # [LAW:parse-dont-validate] Descriptor construction is the metadata boundary.
    if type(value) is not frozenset or any(type(item) is not str or not item for item in value):
        raise ValueError(f"{name} requires a frozen set of nonempty sample IDs")
    return value


@dataclass(frozen=True)
class SyntheticDescriptor:
    """Immutable required/supplied synthetic sample metadata for one binding."""

    binding: CandidateBinding
    required_sample_ids: frozenset[str]
    supplied_sample_ids: frozenset[str]

    def __post_init__(self):
        # [LAW:types-are-the-program] Parsed fields admit no editable completeness flag.
        if type(self.binding) is not CandidateBinding:
            raise ValueError("descriptor requires a candidate binding")
        _sample_ids(self.required_sample_ids, "required samples")
        _sample_ids(self.supplied_sample_ids, "supplied samples")

    @property
    def missing_sample_ids(self) -> tuple[str, ...]:
        # [LAW:one-source-of-truth] Completeness derives from the two supplied sets.
        return tuple(sorted(self.required_sample_ids - self.supplied_sample_ids))


@dataclass(frozen=True)
class CloningEvaluationRequest:
    """One candidate request and its descriptor, bound to the same provenance."""

    request: CandidateRequest
    descriptor: SyntheticDescriptor

    def __post_init__(self):
        if type(self.request) is not CandidateRequest or type(self.descriptor) is not SyntheticDescriptor:
            raise ValueError("cloning evaluation requires parsed request and descriptor")
        if self.request.binding != self.descriptor.binding:
            raise ValueError("descriptor binding contradicts request")


@dataclass(frozen=True)
class QualityDecision:
    """A supplied quality decision bound to its exact workflow request."""

    request: CloningEvaluationRequest
    evidence: QualityEvidence

    def __post_init__(self):
        if type(self.request) is not CloningEvaluationRequest or type(self.evidence) is not QualityEvidence:
            raise ValueError("quality decision requires parsed request and evidence")
        if self.request.request.binding != self.evidence.binding:
            raise ValueError("quality decision binding contradicts request")


class EvaluatorFailureReason(Enum):
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid-response"


@dataclass(frozen=True)
class EvaluatorFailure:
    """A supplied evaluator failure, distinct from a quality decision."""

    request: CloningEvaluationRequest
    reason: EvaluatorFailureReason

    def __post_init__(self):
        if type(self.request) is not CloningEvaluationRequest:
            raise ValueError("evaluator failure requires a parsed request")
        if type(self.reason) is not EvaluatorFailureReason:
            raise ValueError("evaluator failure requires a closed reason")


@dataclass(frozen=True)
class MissingSampleRequirements:
    """The exact required synthetic sample IDs absent from a request descriptor."""

    request: CloningEvaluationRequest
    sample_ids: tuple[str, ...]

    def __post_init__(self):
        if type(self.request) is not CloningEvaluationRequest:
            raise ValueError("missing samples require a parsed request")
        if type(self.sample_ids) is not tuple or not self.sample_ids:
            raise ValueError("missing samples require a nonempty immutable tuple")
        if self.sample_ids != self.request.descriptor.missing_sample_ids:
            raise ValueError("missing samples must equal request-derived missing IDs")


def _parse_workflow_inputs(
    request: object,
    authority: object,
    evaluator_result: object,
) -> None:
    # [LAW:single-enforcer] One workflow boundary checks cross-request metadata.
    if type(request) is not CloningEvaluationRequest:
        raise ValueError("cloning evaluation requires a parsed request")
    if authority is not None:
        if type(authority) is not AuthorityEvidence:
            raise ValueError("authority evidence is malformed")
        if authority.binding != request.request.binding:
            raise ValueError("authority binding contradicts request")
    if evaluator_result is None:
        return
    if type(evaluator_result) not in (QualityDecision, EvaluatorFailure):
        raise ValueError("evaluator result is malformed")
    if evaluator_result.request != request:
        raise ValueError("evaluator result contradicts request")


def evaluate_cloning_request(
    request: CloningEvaluationRequest,
    authority: AuthorityEvidence | None,
    evaluator_result: QualityDecision | EvaluatorFailure | None,
) -> VoiceCandidate | CandidateRejection | MissingSampleRequirements | EvaluatorFailure:
    """Return a pure synthetic workflow outcome from supplied metadata."""
    # [LAW:effects-at-boundaries] Evaluator execution is supplied data, never invoked here.
    _parse_workflow_inputs(request, authority, evaluator_result)
    missing = request.descriptor.missing_sample_ids
    if missing:
        return MissingSampleRequirements(request, missing)
    if type(evaluator_result) is EvaluatorFailure:
        return evaluator_result
    quality = None if evaluator_result is None else evaluator_result.evidence
    # [LAW:single-enforcer] Candidate eligibility remains owned by represent_candidate.
    return represent_candidate(request.request, authority, quality)
