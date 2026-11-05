# C.4 offline verification checkpoint

TO: Buford, lead orchestrator. FROM: Henrietta, senior engineer.
Task `.298.isr`; baseline `fd03988e780b9039636f46fdfb4cfdce24e1b2b3`.
Branch `feat/provider-configuration`, worktree `.worktrees/provider-configuration`.
Session `01a0c02c-000b-7303-8737-74523c1cf28b`.

## Evidence

- Baseline: 392 tests passed in 10.532s. In the restricted sandbox seven existing
  Unix-socket tests fail with `control.socket-unavailable`; approved execution
  outside that sandbox passes them. No voice/control source workaround was made.
- Public gateway boundary: missing-API RED, then gateway tests and full suite
  GREEN (402 tests). Exclusive owner claim also tested RED→GREEN.
- Provider records: five missing-boundary RED tests → GREEN; full suite 407.
- Configuration owner: twelve missing-owner RED tests → GREEN. Further failing
  tests exposed disable-before-bootstrap, active-handle rejection, polling into
  fallback during a transaction, and adding/removing fallback roles; fixes passed.
- Final implementation tree: `python -W error::ResourceWarning -m unittest
  discover -s tests -q` — 439 tests passed in 11.493s, including temporary local
  Unix sockets. The 47 new tests use real owners over fake effects.
- `python -m tests.provider_mutations` — 12/12 detected; exact candidate binding,
  expected revision, epoch ownership, bootstrap, health, evaluation, bundle,
  budgets, effect permit, replay retention, disable and cleanup-fault retention.
- `python -m tests.gateway_mutations` — existing 7/7 detected.
- `python -m runtime health` — simulation, state ok, external_execution false.
- `python -m ops.build /tmp/arhugula-provider-smoke.I6vD3f/arhugula.pyz`, zipapp
  health and provider imports/schema access from the zipapp all passed.
- `git diff --check` passed. `python -m ruff --version` reports no installed
  module; local lint is unverified. No package download was attempted.

The handoff message carries the immutable final SHA and its exact-head retest.
This file records implementation evidence, not independent review or CI.

## Supplemental permit concurrency proof

Buford's reiterated requirement prompted three additional tests after `a237b2a`;
no production change was needed. Cancel/disable invoked inside either primary or
fallback permit prevents that effect even when the permit returns True. Cutover
from either permit returns busy and cancellation completes. A disable on another
thread serializes behind the admitted attempt, retires its job, then denies new
effects after returning. Event-controlled threads join within bounded time.

Two added mutations remove the post-permit cancellation checkpoint or permit
reentrant cutover; both are detected. Provider mutations now total 14/14.
These tests demonstrate serialized disable semantics: calling disable concurrently
does not retroactively undo an effect admitted before disable acquired ownership.

## Decisions for review

### C4-RECORDS-CODE-REVIEW-1 fix

Hannibal's `forged-unaccounted` finding reproduced against `dcd0a6d`: a
lookalike manifest with placement `other` and RAM `10**30` passed accounting.
`check_budgets` now requires exact Manifest records before grouping; their
constructors already own Resources and Provider placement validation. Subclasses
can bypass those constructors, so `isinstance` is insufficient. No repeated
schema checks or gateway/configuration changes were added. The input iterable is
snapshotted once: previously a one-shot iterable also silently skipped VM totals.

RED: the two budget regressions produced 13 assertion failures (accepted invalid
items, wrong denial type for missing fields, and accepted excessive VM RAM from an
iterator). The constructor-contract characterization passed before the fix.
GREEN: all eight records tests passed; full ResourceWarning-error suite passed
445 tests in 11.793s with approved temporary Unix-socket access. Provider mutations
are 17/17, including removed exact-type guard, weakened `isinstance` guard and
removed iterable snapshot; existing gateway mutations remain 7/7. Tuple/list/
iterator inputs preserve valid host shared-RAM and VM exact-ceiling totals and
reject one-byte VM excess. `git diff --check` passed.

This is implementation evidence for bounded Hannibal re-review through Buford,
not resolution attestation. Full-arc independent review and required CI remain
pending. The trusted in-process contract does not defend against malicious Python
using `object.__new__`/`object.__setattr__` to bypass frozen record invariants.

The public gateway claim is exclusive and starts disabled atomically; the token
protects configuration changes while preserving existing unconfigured callers.
No private gateway state is copied. Callback reentry rejects configuration edits;
poll cannot advance effects inside a configuration transaction.

Bootstrap applies to previously absent roles. A newly added fallback needs its own
bound bootstrap evaluation; retained host roles still use active comparison.
Removing fallback compares the retained host and removes fallback effects.
The risk to review is accidentally interpreting bootstrap as blanket comparison
authority; a mismatched retained-host bundle test denies that path.

Trusted local API invocation is the authority boundary. Receipts are not proof
of a human-authenticated UI or that an evaluator actually ran. The host's Admission
is unchanged; cutover here governs the VM client. Memory limits can deny further
changes/rollback, and disable remains available. Clock and callback contracts
remain explicit; no arbitrary Python callback is preempted.

## Handoff boundary

Independent security review must inspect the complete baseline-to-head range,
especially public gateway reentry, opaque receipts, bootstrap versus comparison,
health at fallback and resource pool accounting. Buford owns review routing,
required PR/main CI, integration and closure. Keep this branch/worktree for review.
No catalog/core/evaluation/voice/CI files changed. No network/provider/model,
download/update, persistence, UI, audio, device or desktop activation occurred.
`.0hj` remains actual provider release/persistence reconciliation. Do not clear
this session before Buford accepts the durable checkpoint.
