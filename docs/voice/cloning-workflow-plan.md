# Synthetic cloning workflow implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure synthetic metadata workflow that reports descriptor incompleteness and evaluator failure while delegating candidate eligibility to `represent_candidate`.

**Architecture:** `runtime/voice_cloning.py` owns immutable workflow request and result values. It accepts an evaluator outcome as data and delegates only a matching quality decision to `runtime.voice_candidates.represent_candidate`; it never invokes an evaluator or performs effects.

**Tech Stack:** Python standard library (`dataclasses`, `enum`, `unittest`).

**Spec:** `docs/voice/cloning-workflow-design.md`

## Global constraints

- Work from base `5a37dca4fb060da692903f03b21a9293e7ef8706` only after Buford attests this design and plan.
- Reuse `CandidateBinding`, `CandidateRequest`, `Provenance`, `QualityEvidence`, and `represent_candidate`; do not alter eligibility semantics.
- Accept evaluator-result data. Do not add a callback, provider, storage, audio, transcript, recording, upload, download, inference, playback, retention, deletion, consent, or activation capability.
- Do not invent quality thresholds or real authority policies. Synthetic labels are not consent, evaluator authority, or activation authority.
- Parse malformed or mismatched input loudly. Never convert evaluator failure into accepted or rejected quality, and never use a fallback result.
- Keep every workflow value immutable and bind descriptor and evaluator outcome to the exact request.

## Review focus

- An evaluator result for a different candidate version or provenance digest raises rather than affects the requested candidate.
- An incomplete descriptor with accepted quality returns `DescriptorIncomplete`, not a candidate or `CandidateRejection`.
- `EvaluatorFailure` and `QualityState.REJECTED` remain distinct observable outcomes.
- Missing, unknown, denied, rejected, and incomplete evidence retain the existing `CandidateRejection` reason after delegation.
- Mutation of a returned binding, provenance, descriptor, or failure result raises and cannot change a later evaluation.

## File structure

- Create `runtime/voice_cloning.py`: immutable workflow types and the pure `evaluate_cloning_request` boundary.
- Create `tests/test_voice_cloning.py`: behavior tests for workflow outcomes and malformed/cross-bound inputs.
- Modify `docs/voice/cloning-workflow-design.md` only if implementation exposes a mismatch between approved design and actual contract.

### Task 1: Define parsed workflow values

**Files:**

- Create: `runtime/voice_cloning.py`
- Test: `tests/test_voice_cloning.py`

**Interfaces:**

- Consumes: `CandidateBinding`, `CandidateRequest`, and `QualityEvidence` from `runtime.voice_candidates`.
- Produces: `DescriptorCompleteness`, `SyntheticDescriptor`, `CloningEvaluationRequest`, `QualityDecision`, `EvaluatorFailureReason`, and `EvaluatorFailure`.

- [ ] **Step 1: Write the failing construction test**

```python
def test_request_requires_one_matching_descriptor_binding(self):
    binding = CandidateBinding(CandidateVersion("fixture", 1), Provenance("ref", "digest"))
    other = CandidateBinding(CandidateVersion("fixture", 2, CandidateVersion("fixture", 1)), Provenance("ref-2", "digest-2"))

    with self.assertRaisesRegex(ValueError, "binding"):
        CloningEvaluationRequest(
            CandidateRequest(binding),
            SyntheticDescriptor(other, DescriptorCompleteness.COMPLETE),
        )
```

- [ ] **Step 2: Run it to verify RED**

Run: `python -m unittest tests.test_voice_cloning.VoiceCloningTests.test_request_requires_one_matching_descriptor_binding`

Expected: FAIL because `runtime.voice_cloning` does not exist.

- [ ] **Step 3: Add minimal immutable values**

```python
@dataclass(frozen=True)
class CloningEvaluationRequest:
    request: CandidateRequest
    descriptor: SyntheticDescriptor

    def __post_init__(self):
        if type(self.request) is not CandidateRequest or type(self.descriptor) is not SyntheticDescriptor:
            raise ValueError("cloning evaluation requires parsed request and descriptor")
        if self.request.binding != self.descriptor.binding:
            raise ValueError("descriptor binding contradicts request")
```

Use exact-type checks consistent with `runtime.voice_candidates`. Apply the same binding rule to `QualityDecision` and constrain `EvaluatorFailureReason` to a closed enum.

- [ ] **Step 4: Run focused construction tests**

Run: `python -m unittest tests.test_voice_cloning -v`

Expected: PASS for matching construction; mismatched/forged values raise `ValueError`.

- [ ] **Step 5: Commit**

```bash
git add runtime/voice_cloning.py tests/test_voice_cloning.py
git commit -m "feat: define synthetic cloning workflow values"
```

### Task 2: Route pure workflow outcomes

**Files:**

- Modify: `runtime/voice_cloning.py`
- Modify: `tests/test_voice_cloning.py`

**Interfaces:**

- Consumes: `CloningEvaluationRequest`, `AuthorityEvidence | None`, and supplied `QualityDecision | EvaluatorFailure`.
- Produces: `VoiceCandidate | CandidateRejection | DescriptorIncomplete | EvaluatorFailure`.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_incomplete_descriptor_is_not_a_candidate(self):
    result = evaluate_cloning_request(self.incomplete_request, self.authorized, self.accepted_decision)
    self.assertEqual(result, DescriptorIncomplete(self.incomplete_request))
    self.assertNotIsInstance(result, VoiceCandidate)

def test_evaluator_failure_is_not_rejected_quality(self):
    failure = EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE)
    self.assertIs(evaluate_cloning_request(self.complete_request, self.authorized, failure), failure)
```

- [ ] **Step 2: Run them to verify RED**

Run: `python -m unittest tests.test_voice_cloning.VoiceCloningTests.test_incomplete_descriptor_is_not_a_candidate tests.test_voice_cloning.VoiceCloningTests.test_evaluator_failure_is_not_rejected_quality`

Expected: FAIL because `evaluate_cloning_request` does not exist.

- [ ] **Step 3: Add fixed outcome routing**

```python
def evaluate_cloning_request(request, authority, evaluator_result):
    _parse_workflow_inputs(request, authority, evaluator_result)
    if request.descriptor.completeness is DescriptorCompleteness.INCOMPLETE:
        return DescriptorIncomplete(request)
    if type(evaluator_result) is EvaluatorFailure:
        return evaluator_result
    return represent_candidate(request.request, authority, evaluator_result.evidence)
```

`_parse_workflow_inputs` is the sole workflow input boundary. It rejects a result bound to another request and does not duplicate `represent_candidate` evidence-state rules.

- [ ] **Step 4: Run behavior tests including delegated denials**

Run: `python -m unittest tests.test_voice_cloning -v`

Expected: PASS for complete success, incomplete descriptor, evaluator failure, rejected quality, and every existing authority/quality denial with its exact reason.

- [ ] **Step 5: Commit**

```bash
git add runtime/voice_cloning.py tests/test_voice_cloning.py
git commit -m "feat: route synthetic cloning workflow outcomes"
```

### Task 3: Verify immutability and preserve the design contract

**Files:**

- Modify: `tests/test_voice_cloning.py`
- Modify: `docs/voice/cloning-workflow-design.md`

**Interfaces:**

- Consumes: all Task 1 and Task 2 workflow values.
- Produces: executable evidence that frozen values preserve a fixed request and result.

- [ ] **Step 1: Write failing immutability and cross-request tests**

```python
def test_result_binding_and_failure_are_immutable(self):
    result = evaluate_cloning_request(self.complete_request, self.authorized, self.accepted_decision)
    with self.assertRaises(AttributeError):
        result.binding.version.version = 9
    with self.assertRaises(AttributeError):
        EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE).reason = "rejected"
```

Add a separate assertion that a `QualityDecision` built for another request raises before any candidate outcome can be returned.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `python -m unittest tests.test_voice_cloning -v`

Expected: FAIL until frozen values and exact request binding are implemented.

- [ ] **Step 3: Complete minimal contract correction**

Keep workflow values frozen and ensure the design document names final exported types and the closed evaluator-failure vocabulary. Do not add effects or policy.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m unittest tests.test_voice_cloning tests.test_voice_candidates -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -q`

Expected: PASS with no modifications outside the workflow module, its tests, and the approved design document.

- [ ] **Step 5: Commit**

```bash
git add tests/test_voice_cloning.py docs/voice/cloning-workflow-design.md
git commit -m "test: cover immutable synthetic cloning outcomes"
```

## Plan self-review

The plan maps descriptor completeness to `DescriptorIncomplete`, evaluator execution failure to `EvaluatorFailure`, and all evidence eligibility to the existing `represent_candidate` single enforcer. It includes behavior tests for every required outcome, exact request binding, malformed values, lineage, and immutability. It contains no evaluator callback, effect adapter, real-world policy, or product work.

This plan requires Buford's attestation before Task 1 begins.

