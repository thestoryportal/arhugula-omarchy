# Synthetic cloning workflow implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure synthetic metadata workflow that reports the exact required sample IDs still missing and evaluator failure while delegating candidate eligibility to `represent_candidate`.

**Architecture:** `runtime/voice_cloning.py` owns immutable workflow request and result values. It accepts an evaluator outcome as data and delegates only a matching quality decision to `runtime.voice_candidates.represent_candidate`; it never invokes an evaluator or performs effects.

**Tech Stack:** Python standard library (`dataclasses`, `enum`, `unittest`).

**Spec:** `docs/voice/cloning-workflow-design.md`

## Global constraints

- Work from base `5a37dca4fb060da692903f03b21a9293e7ef8706` only after Buford attests this design and plan.
- Reuse `CandidateBinding`, `CandidateRequest`, `Provenance`, `QualityEvidence`, and `represent_candidate`; do not alter eligibility semantics.
- Accept evaluator-result data. Do not add a callback, provider, storage, audio, transcript, recording, upload, download, inference, playback, retention, deletion, consent, or activation capability.
- Do not invent quality thresholds or real authority policies. Synthetic labels are not consent, evaluator authority, or activation authority.
- Parse malformed or mismatched input loudly. Never convert evaluator failure into accepted or rejected quality, and never use a fallback result.
- Derive missing samples from one immutable required/supplied metadata representation; do not add a completeness flag.
- Keep every workflow value immutable and bind descriptor and evaluator outcome to the exact request. Validate supplied authority binding before every result branch.

## Review focus

- An evaluator result for a different candidate version or provenance digest raises rather than affects the requested candidate.
- Required-but-unsupplied sample IDs return a deterministic `MissingSampleRequirements`, not a candidate or `CandidateRejection`.
- `EvaluatorFailure` and `QualityState.REJECTED` remain distinct observable outcomes.
- A missing evaluator result passes `None` through as canonical `quality-missing`; unknown, denied, rejected, and incomplete evidence retain existing reasons after delegation.
- Mutation of a returned binding, provenance, descriptor, or failure result raises and cannot change a later evaluation.

## File structure

- Create `runtime/voice_cloning.py`: immutable workflow types and the pure `evaluate_cloning_request` boundary.
- Create `tests/test_voice_cloning.py`: behavior tests for workflow outcomes and malformed/cross-bound inputs.
- Create `tests/probe_voice_cloning_mutations.py`: offline, in-memory mutation probes with passing controls.
- Create `tests/voice_cloning_package_smoke.py`: fresh-pyz API smoke outside checkout runtime paths.
- Modify `docs/voice/cloning-workflow-design.md` only if implementation exposes a mismatch between approved design and actual contract.
- Create `docs/voice/cloning-workflow-evidence.md`: exact-head local verification, scope audit, and limitations.

### Task 1: Define parsed workflow values

**Files:**

- Create: `runtime/voice_cloning.py`
- Test: `tests/test_voice_cloning.py`

**Interfaces:**

- Consumes: `CandidateBinding`, `CandidateRequest`, and `QualityEvidence` from `runtime.voice_candidates`.
- Produces: `SyntheticDescriptor`, `CloningEvaluationRequest`, `QualityDecision`, `EvaluatorFailureReason`, and `EvaluatorFailure`.

- [ ] **Step 1: Write failing public-constructor tests**

```python
def test_request_requires_one_matching_descriptor_binding(self):
    binding = CandidateBinding(CandidateVersion("fixture", 1), Provenance("ref", "digest"))
    other = CandidateBinding(CandidateVersion("fixture", 2, CandidateVersion("fixture", 1)), Provenance("ref-2", "digest-2"))

    with self.assertRaisesRegex(ValueError, "binding"):
        CloningEvaluationRequest(
            CandidateRequest(binding),
            SyntheticDescriptor(other, frozenset({"sample-a"}), frozenset({"sample-a"})),
        )

    descriptor = SyntheticDescriptor(binding, frozenset({"sample-a"}), frozenset())
    request = CloningEvaluationRequest(CandidateRequest(binding), descriptor)
    with self.assertRaisesRegex(ValueError, "missing"):
        MissingSampleRequirements(request, ())
    with self.assertRaisesRegex(ValueError, "missing"):
        MissingSampleRequirements(request, ["sample-a"])
    with self.assertRaisesRegex(ValueError, "missing"):
        MissingSampleRequirements(request, ("other",))
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

Use exact-type checks consistent with `runtime.voice_candidates`. `SyntheticDescriptor` accepts only frozen sets of nonempty IDs and derives sorted missing IDs from their difference. Apply the same exact-request rule to `QualityDecision`, constrain `EvaluatorFailureReason` to a closed enum, and require `MissingSampleRequirements(request, sample_ids)` to accept only a nonempty exact tuple equal to `request.descriptor.missing_sample_ids`.

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

- Consumes: `CloningEvaluationRequest`, `AuthorityEvidence | None`, and supplied `QualityDecision | EvaluatorFailure | None`.
- Produces: `VoiceCandidate | CandidateRejection | MissingSampleRequirements | EvaluatorFailure`.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_missing_required_sample_is_not_a_candidate(self):
    result = evaluate_cloning_request(self.request_missing_sample_a, self.authorized, self.accepted_decision)
    self.assertEqual(result, MissingSampleRequirements(self.request_missing_sample_a, ("sample-a",)))
    self.assertNotIsInstance(result, VoiceCandidate)

def test_evaluator_failure_is_not_rejected_quality(self):
    failure = EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE)
    self.assertIs(evaluate_cloning_request(self.complete_request, self.authorized, failure), failure)
```

- [ ] **Step 2: Run them to verify RED**

Run: `python -m unittest tests.test_voice_cloning.VoiceCloningTests.test_missing_required_sample_is_not_a_candidate tests.test_voice_cloning.VoiceCloningTests.test_evaluator_failure_is_not_rejected_quality`

Expected: FAIL because `evaluate_cloning_request` does not exist.

- [ ] **Step 3: Add fixed outcome routing**

```python
def evaluate_cloning_request(request, authority, evaluator_result):
    _parse_workflow_inputs(request, authority, evaluator_result)
    missing = request.descriptor.missing_sample_ids
    if missing:
        return MissingSampleRequirements(request, missing)
    if type(evaluator_result) is EvaluatorFailure:
        return evaluator_result
    quality = None if evaluator_result is None else evaluator_result.evidence
    return represent_candidate(request.request, authority, quality)
```

`_parse_workflow_inputs` is the sole workflow input boundary. It rejects a supplied authority binding that differs from the request before the missing-sample or evaluator-failure branch, rejects a result bound to another exact request, and does not duplicate `represent_candidate` evidence-state rules.

- [ ] **Step 4: Run behavior tests including delegated denials**

Run: `python -m unittest tests.test_voice_cloning -v`

Expected: PASS for complete success, targeted missing samples, evaluator failure, missing quality (`None`), rejected quality, and every existing authority/quality denial with its exact reason.

- [ ] **Step 5: Commit**

```bash
git add runtime/voice_cloning.py tests/test_voice_cloning.py
git commit -m "feat: route synthetic cloning workflow outcomes"
```

### Task 3: Extend coverage for immutability and exact request binding

**Files:**

- Modify: `tests/test_voice_cloning.py`
- Modify: `docs/voice/cloning-workflow-design.md`

**Interfaces:**

- Consumes: all Task 1 and Task 2 workflow values.
- Produces: executable evidence that frozen values preserve a fixed request and result.

- [ ] **Step 1: Write cross-request coverage and immutable-value coverage**

```python
def test_result_binding_and_failure_are_immutable(self):
    result = evaluate_cloning_request(self.complete_request, self.authorized, self.accepted_decision)
    with self.assertRaises(AttributeError):
        result.binding.version.version = 9
    with self.assertRaises(AttributeError):
        EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE).reason = "rejected"
```

Add a separate assertion that a `QualityDecision` built for another request raises before any candidate outcome can be returned.

- [ ] **Step 2: Run focused tests and record the honest baseline**

Run: `python -m unittest tests.test_voice_cloning -v`

Expected: The new cross-request assertion is RED before its binding rule exists. Immutability constructor assertions start GREEN after Task 1 because frozen values are already delivered; record that passing control rather than manufacturing a RED.

- [ ] **Step 3: Complete minimal contract correction**

Keep workflow values frozen and ensure the design document names final exported types and the closed evaluator-failure vocabulary. Do not add effects or policy.

- [ ] **Step 4: Run focused and full suites**

Run: `python -m unittest tests.test_voice_cloning tests.test_voice_candidates -v`

Expected: PASS.

Run: `python -W error::ResourceWarning -m unittest discover -s tests -q`

Expected: PASS with no modifications outside the workflow module, workflow tests/probes, and approved evidence/design documents.

- [ ] **Step 5: Commit**

```bash
git add tests/test_voice_cloning.py docs/voice/cloning-workflow-design.md
git commit -m "test: cover immutable synthetic cloning outcomes"
```

### Task 4: Run mutation probes and capture local evidence

**Files:**

- Create: `tests/probe_voice_cloning_mutations.py`
- Create: `tests/voice_cloning_package_smoke.py`
- Create: `docs/voice/cloning-workflow-evidence.md`

**Interfaces:**

- Consumes: the completed `runtime.voice_cloning` source and named behavioral tests.
- Produces: four passing controls, four assertion-detected in-memory mutations, an isolated fresh-pyz API smoke result, and one exact-head evidence record.

- [ ] **Step 1: Add the offline mutation runner**

Match `tests/probe_conversation_mutations.py`: reload only `runtime.voice_cloning`, run each named test unmodified, assert its single-test baseline passes, replace exactly one source anchor in memory, compile it into the reloaded module, then assert the same test fails. Never write source or change Git state.

```python
MUTATIONS = (
    ("if authority is not None:", "if False:", 1,
     "test_contradictory_authority_binding_rejected_before_missing_sample_outcome"),
    ("if missing:", "if False:", 1,
     "test_missing_required_sample_is_not_a_candidate"),
    ("return evaluator_result", "return represent_candidate(request.request, authority, None)", 1,
     "test_evaluator_failure_is_not_rejected_quality"),
    ("quality = None if evaluator_result is None else evaluator_result.evidence", "quality = QualityEvidence(request.request.binding, QualityState.SYNTHETIC_ACCEPTED) if evaluator_result is None else evaluator_result.evidence", 1,
     "test_missing_evaluator_result_preserves_quality_missing"),
)
```

The runner accepts a mutation only when the mutated named test has at least one assertion failure and zero errors. An import error, `AttributeError`, or another test-runner error aborts the probe as invalid evidence.

- [ ] **Step 2: Run passing controls and mutations**

Run: `python -m tests.probe_voice_cloning_mutations`

Expected: each named original control passes, each replacement causes a named behavioral assertion failure with zero errors, and the runner reports `4/4 mutations detected; no files changed`.

- [ ] **Step 3: Run source and fresh-package smoke**

Run: `python -m runtime health`

Expected: runtime health succeeds.

Implement `tests/voice_cloning_package_smoke.py` as a standalone smoke runner. It creates a unique temporary directory, builds `arhugula.pyz`, then invokes a clean Python subprocess with that directory as cwd and no checkout `PYTHONPATH`. The subprocess asserts `runtime.__file__` begins with the fresh pyz path and exercises packaged complete success, `MissingSampleRequirements(("sample-a",))`, and `EvaluatorFailure`. It prints the retained exact temporary directory path; do not delete it automatically.

Run: `python tests/voice_cloning_package_smoke.py`

Expected: source health, fresh zipapp health, the packaged API cases, and the imported-runtime path assertion succeed. The output names the retained artifact path.

- [ ] **Step 4: Write the evidence record and scope audit**

Record the final full commit SHA, exact base, changed paths, focused tests, full ResourceWarning-as-error result, mutation controls/results, source/package smoke result, `git diff --check`, and limitations in `docs/voice/cloning-workflow-evidence.md`. State that this is local implementation evidence only; it is not review, CI, integration, or live-cloning evidence.

- [ ] **Step 5: Commit verification evidence**

```bash
git add tests/probe_voice_cloning_mutations.py tests/voice_cloning_package_smoke.py docs/voice/cloning-workflow-evidence.md
git commit -m "test: verify synthetic cloning workflow"
```

## Plan self-review

The plan derives targeted missing samples from one immutable descriptor representation, maps evaluator execution failure to `EvaluatorFailure`, and sends missing quality and every other eligibility decision to the existing `represent_candidate` single enforcer. It includes behavior tests, passing mutation controls/probes, full ResourceWarning-as-error regression, source/package smoke, exact request binding, malformed values, lineage, and immutability. It contains no evaluator callback, effect adapter, real-world policy, or product work.

This plan requires Buford's attestation before Task 1 begins.
