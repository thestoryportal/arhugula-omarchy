# Synthetic cloning workflow design

## Purpose and scope

This proposed pure workflow turns supplied synthetic descriptor metadata, a candidate-version request, supplied authority evidence, and a supplied evaluator result into one explicit outcome. It identifies the specific required synthetic samples still missing and makes evaluator failure visible without changing the eligibility rule already owned by `runtime.voice_candidates.represent_candidate`.

The design is limited to offline metadata. A synthetic label does not establish real consent, evaluator authority, data-retention authority, quality thresholds, storage, or activation. It does not collect, retain, delete, persist, upload, download, synthesize, play, or infer from voice data. This slice is not full guided cloning.

## Existing boundary retained

`runtime.voice_candidates` remains the source of truth for candidate eligibility. `CandidateBinding` already couples `CandidateVersion` and `Provenance`; therefore it already supplies candidate identity/version lineage and immutable descriptor reference/digest. `represent_candidate` remains the only operation that translates supplied `AuthorityEvidence` and accepted `QualityEvidence` into `VoiceCandidate` or `CandidateRejection`.

The workflow must not reimplement missing, unknown, denied, rejected, or incomplete authority/quality checks. It delegates those decisions unchanged after it establishes request identity, required samples, and evaluator-result integrity.

## Proposed module and data flow

Create `runtime/voice_cloning.py` as the pure orchestration boundary. It imports the existing candidate types and exports these immutable value types:

```python
@dataclass(frozen=True)
class SyntheticDescriptor:
    binding: CandidateBinding
    required_sample_ids: frozenset[str]
    supplied_sample_ids: frozenset[str]

    @property
    def missing_sample_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.required_sample_ids - self.supplied_sample_ids))

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
class MissingSampleRequirements:
    request: CloningEvaluationRequest
    sample_ids: tuple[str, ...]
```

`SyntheticDescriptor` contains `CandidateBinding` rather than copying reference and digest fields. Its binding identifies the exact provenance reference/digest. Its supplied metadata is two exact `frozenset[str]` values: required synthetic sample identifiers and supplied synthetic sample identifiers. Each identifier is nonempty text; the supplied set need not be a subset, because extra supplied metadata is not an eligibility decision. `missing_sample_ids` is the sorted set difference of those immutable inputs. It is the sole completeness representation: there is no independently editable completeness flag.

`CloningEvaluationRequest` accepts only exact request and descriptor values whose bindings match. This gives each request one candidate version, lineage, provenance reference/digest, and a deterministic list of required samples still absent without independently editable completeness or provenance copies.

`QualityDecision` accepts only a request and `QualityEvidence` whose binding equals that request's binding. `EvaluatorFailure` instead holds a closed `EvaluatorFailureReason` such as `UNAVAILABLE` or `INVALID_RESPONSE`; it has no `QualityEvidence`. Both variants contain the whole `CloningEvaluationRequest`, preventing an evaluator result for one version, descriptor digest, or required/supplied sample set from being used for another.

Every public workflow result constructor parses its own values. `QualityDecision` rejects a malformed or mismatched evidence binding; `EvaluatorFailure` rejects a malformed request or reason; and `MissingSampleRequirements` accepts only an exact request plus a nonempty exact tuple equal to that request's derived `missing_sample_ids`. It therefore cannot claim no missing samples, mutable sample IDs, or IDs that differ from the descriptor. Frozen dataclasses protect the resulting values after this construction boundary.

The public function is:

```python
def evaluate_cloning_request(
    request: CloningEvaluationRequest,
    authority: AuthorityEvidence | None,
    evaluator_result: QualityDecision | EvaluatorFailure | None,
) -> VoiceCandidate | CandidateRejection | MissingSampleRequirements | EvaluatorFailure:
    ...
```

It accepts evaluator results as supplied data. It does not call an evaluator and does not use a callback, which keeps this boundary pure and avoids implying evaluator execution is pure. The exact `EvaluatorFailureReason` vocabulary is closed for this metadata-only slice; it classifies a supplied result failure, not candidate quality.

## Evaluation behavior

The function parses its inputs at this boundary and rejects malformed types or cross-request bindings with `ValueError`. It validates a supplied authority binding before every outcome branch, including missing-sample and evaluator-failure branches. A quality decision or evaluator failure must bind to the exact `CloningEvaluationRequest`, not merely an equal candidate binding. Once parsed, it has this fixed result flow:

1. One or more missing required sample identifiers returns `MissingSampleRequirements(request, sample_ids)`, where `sample_ids` is the deterministic sorted set difference. No candidate is created and no quality conclusion is inferred.
2. An `EvaluatorFailure` returns that same typed failure. It is distinct from `QualityState.REJECTED`, so a failed evaluator is never silently treated as a negative quality decision.
3. A `QualityDecision` passes its `QualityEvidence` and supplied authority evidence to `represent_candidate(request.request, authority, evidence)`. `None` is also supported: it passes `quality=None` to that same function, preserving its canonical `quality-missing` rejection. The returned `VoiceCandidate` or `CandidateRejection` is returned unchanged.

This makes required-sample completeness and evaluator-result integrity workflow concerns. Eligibility remains in its existing single enforcer. The function has no effects, storage adapter, or fallback result.

## Failure semantics

Malformed construction and contradictory bindings fail loudly with `ValueError`. They are not candidate denials because the boundary cannot truthfully evaluate the metadata. `MissingSampleRequirements` and `EvaluatorFailure` are typed non-candidate outcomes. Existing candidate denials, including missing quality, remain `CandidateRejection` with the existing closed reason vocabulary.

No result authorizes any action outside the metadata decision. `VoiceCandidate` remains a representable synthetic candidate, not an approval, consent record, storage authorization, evaluator attestation, or activation grant.

## Required behavior tests

`tests/test_voice_cloning.py` constructs all inputs in memory. `tests/probe_voice_cloning_mutations.py` recompiles the workflow module only in memory; each probe first runs its named behavioral test unchanged, then must make that test fail. Neither needs a callback or effect adapter.

- A complete descriptor, matching accepted evaluator decision, and qualifying supplied authority yields the existing immutable `VoiceCandidate`.
- Required sample IDs `{"sample-a", "sample-b"}` and supplied IDs `{"sample-b"}` yield `MissingSampleRequirements(..., ("sample-a",))` even when quality is accepted.
- An evaluator failure yields `EvaluatorFailure` unchanged even when descriptor and authority are qualifying; `REJECTED` remains a separate `CandidateRejection` path through `represent_candidate`.
- A missing evaluator result (`None`) passes through `represent_candidate` as missing quality and preserves `quality-missing`; unknown, denied, rejected, and incomplete evidence preserve their exact existing reason.
- Mismatched descriptor/request/evaluator bindings, contradictory authority bindings even on missing-sample and evaluator-failure paths, contradictory lineage, malformed enum values, and forged values fail loudly.
- Every public result constructor rejects malformed, mutable, and semantically inconsistent values. In particular, `MissingSampleRequirements` rejects empty, mutable, or non-derived sample IDs.
- Returned workflow values, nested bindings, provenance, descriptor sets, and evaluator failure data are frozen. The constructor tests for that contract start green once Task 1 establishes frozen types; later coverage records that fact rather than manufacturing a false RED.
- The mutation runner detects removal of authority-binding validation, replacement of derived missing IDs with an empty tuple, conversion of evaluator failure into missing quality, and a `None`-quality mutation that returns accepted quality. Its four passing controls and detected mutations are recorded in `docs/voice/cloning-workflow-evidence.md`; only named assertion failures count as detection.

## Verification and limitation record

The future evidence document records the exact final pin, changed-path scope audit, focused tests, full `ResourceWarning`-as-error regression, four mutation controls/probes, runtime health, and a fresh zipapp package smoke. That smoke runs outside checkout paths, proves `runtime.__file__` originates inside the fresh pyz, and exercises success, targeted missing samples, and evaluator failure through the packaged API. It retains its temporary artifact path unless an exact validated path is deliberately deleted. The record is local evidence only, not review, CI, integration, or live-release claims.

## Implementation gate

This document is a design proposal only. Buford must attest this design and the companion implementation plan before product code or tests begin.
