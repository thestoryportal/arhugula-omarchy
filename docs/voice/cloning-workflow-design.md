# Synthetic cloning workflow design

## Purpose and scope

This proposed pure workflow turns supplied synthetic descriptor metadata, a candidate-version request, supplied authority evidence, and a supplied evaluator result into one explicit outcome. It makes descriptor incompleteness and evaluator failure visible without changing the eligibility rule already owned by `runtime.voice_candidates.represent_candidate`.

The design is limited to offline metadata. A synthetic label does not establish real consent, evaluator authority, data-retention authority, quality thresholds, storage, or activation. It does not collect, retain, delete, persist, upload, download, synthesize, play, or infer from voice data. This slice is not full guided cloning.

## Existing boundary retained

`runtime.voice_candidates` remains the source of truth for candidate eligibility. `CandidateBinding` already couples `CandidateVersion` and `Provenance`; therefore it already supplies candidate identity/version lineage and immutable descriptor reference/digest. `represent_candidate` remains the only operation that translates supplied `AuthorityEvidence` and accepted `QualityEvidence` into `VoiceCandidate` or `CandidateRejection`.

The workflow must not reimplement its missing, unknown, denied, rejected, or incomplete authority/quality checks. It delegates that decision unchanged after the workflow establishes descriptor completeness and a matching evaluator result.

## Proposed module and data flow

Create `runtime/voice_cloning.py` as the pure orchestration boundary. It imports the existing candidate types and exports these immutable value types:

```python
class DescriptorCompleteness(Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"

@dataclass(frozen=True)
class SyntheticDescriptor:
    binding: CandidateBinding
    completeness: DescriptorCompleteness

@dataclass(frozen=True)
class CloningEvaluationRequest:
    request: CandidateRequest
    descriptor: SyntheticDescriptor

@dataclass(frozen=True)
class QualityDecision:
    request: CloningEvaluationRequest
    evidence: QualityEvidence

@dataclass(frozen=True)
class EvaluatorFailure:
    request: CloningEvaluationRequest
    reason: EvaluatorFailureReason

@dataclass(frozen=True)
class DescriptorIncomplete:
    request: CloningEvaluationRequest
```

`SyntheticDescriptor` contains the immutable `CandidateBinding` rather than copying reference and digest fields. Its binding therefore identifies the exact provenance reference/digest it describes. Its constructor accepts only an exact `CandidateBinding` and `DescriptorCompleteness`. `CloningEvaluationRequest` accepts only exact request and descriptor values whose bindings match. This gives each request one candidate version, lineage, provenance reference/digest, and completeness state without two editable copies of provenance.

`QualityDecision` accepts only a request and `QualityEvidence` whose binding equals that request's binding. `EvaluatorFailure` instead holds a closed `EvaluatorFailureReason` such as `UNAVAILABLE` or `INVALID_RESPONSE`; it has no `QualityEvidence`. Both variants contain the whole `CloningEvaluationRequest`, preventing an evaluator result for one version, descriptor digest, or completeness state from being used for another.

The public function is:

```python
def evaluate_cloning_request(
    request: CloningEvaluationRequest,
    authority: AuthorityEvidence | None,
    evaluator_result: QualityDecision | EvaluatorFailure,
) -> VoiceCandidate | CandidateRejection | DescriptorIncomplete | EvaluatorFailure:
    ...
```

It accepts evaluator results as supplied data. It does not call an evaluator and does not use a callback, which keeps this boundary pure and avoids implying evaluator execution is pure. The exact `EvaluatorFailureReason` vocabulary is closed for this metadata-only slice; it classifies a supplied result failure, not candidate quality.

## Evaluation behavior

The function parses its inputs at this boundary and rejects malformed types or cross-request bindings with `ValueError`. Once parsed, it has this fixed result flow:

1. An incomplete descriptor returns `DescriptorIncomplete(request)`. No candidate is created and no quality conclusion is inferred.
2. An `EvaluatorFailure` returns that same typed failure. It is distinct from `QualityState.REJECTED`, so a failed evaluator is never silently treated as a negative quality decision.
3. A `QualityDecision` passes its supplied `QualityEvidence` with supplied authority evidence to `represent_candidate(request.request, authority, evidence)`. The returned `VoiceCandidate` or `CandidateRejection` is returned unchanged.

This order makes descriptor completeness and evaluator-result integrity workflow concerns. Eligibility remains in its existing single enforcer. The function has no effects, storage adapter, or fallback result.

## Failure semantics

Malformed construction and contradictory bindings fail loudly with `ValueError`. They are not candidate denials because the boundary cannot truthfully evaluate the metadata. `DescriptorIncomplete` and `EvaluatorFailure` are typed, non-candidate outcomes. Existing candidate denials remain `CandidateRejection` with the existing closed reason vocabulary.

No result authorizes any action outside the metadata decision. `VoiceCandidate` remains a representable synthetic candidate, not an approval, consent record, storage authorization, evaluator attestation, or activation grant.

## Required behavior tests

`tests/test_voice_cloning.py` should construct every input in memory; no callback or effect adapter is needed.

- A complete descriptor, matching accepted evaluator decision, and qualifying supplied authority yields the existing immutable `VoiceCandidate`.
- An incomplete descriptor yields `DescriptorIncomplete` even when quality is accepted, and produces no candidate.
- An evaluator failure yields `EvaluatorFailure` unchanged even when descriptor and authority are qualifying; `REJECTED` remains a separate `CandidateRejection` path through `represent_candidate`.
- Every authority/quality denial (missing, unknown, denied, rejected, and incomplete) passes through `represent_candidate` and preserves its exact rejection reason.
- Mismatched descriptor/request/evaluator bindings, contradictory lineage, malformed enum values, and forged values fail loudly at construction or evaluation.
- Returned workflow values, nested bindings, provenance, and evaluator failure data are frozen; mutation attempts raise rather than altering later decisions.

## Implementation gate

This document is a design proposal only. Buford must attest this design and the companion implementation plan before product code or tests begin.

