# Buford loop implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution.

**Goal:** Enforce durable five-ticket epochs, fresh LIT reads, bounded review and
Mac-backed raw artifacts before production workflow resumes.

**Architecture:** A visible-lane boundary controller uses an atomic event journal.
Product review history remains canonical; output capture lives at subprocess edges.

**Tech Stack:** Python standard library, LIT 0.14, existing Codex native TUI.

**Spec:** `docs/orchestration/loop-optimization-design.md`.

## Global Constraints

- Production goal and `repair_paused` remain paused throughout implementation.
- Retain scope, original deadline, worktrees, drafts, denials and review/CI gates.
- At most five completed leaf tickets and five completed review passes; earlier holds stand.
- Native clears occur only after an idle release; bootstrap deadline is 120 seconds.
- Raw logs default to `/mnt/mac/arhugula-artifacts`; no silent guest-disk fallback.

## Review Focus

- New comments without issue timestamp changes invalidate transition admission.
- Crash/restart cannot duplicate completed tickets or reset review history.
- A cancelled/unavailable review is never an approval or completed pass.
- Lost share, timeout and unsupported fsync cannot produce durable-success receipts.
- A new UUID with the wrong model, active writer or omitted ownership remains held.

### Task 1: File-backed subprocess artifacts

**Files:** `ops/orchestration/artifacts.py`, `tests/test_artifacts.py`,
`ops/orchestration/local.py`, `tests/test_local_adapter.py`.
**Interfaces:** `capture(argv, cwd, root, timeout, input=None)` returns a compact
receipt with complete output-file bindings. `verify()` uses that receipt.

- [x] Write behavioral tests for large output, nonzero exit, timeout and missing share.
- [x] Run tests; expected missing implementation failure.
- [x] Implement streaming files, fsync/hash manifests, bounded summaries; integrate verify.
- [x] Run artifact and adapter tests; expected all passing.
- [x] Commit the bounded deliverable.

### Task 2: Review circuit breaker

**Files:** `ops/orchestration/review_budget.py`, `tests/test_review_budget.py`.
**Interfaces:** `evaluate(gate, rows, arc, head, digest, observed)` derives completed
pass bindings from canonical reducer and returns budget/clearance/disposition.

- [x] Write tests for exact fifth/sixth boundary, earlier P1 stop, unavailable and P2/prose.
- [x] Run tests; expected missing implementation failure.
- [x] Implement reducer adapter and stable binding union, retaining canonical gate authority.
- [x] Run review tests against actual product module; expected all passing.
- [x] Commit the bounded deliverable.

### Task 3: LIT/epoch/restart boundary and operational adoption

**Files:** `ops/orchestration/loop.py`, `tests/test_loop.py`,
`docs/orchestration/loop-operations.md`; root role/context policy admission references.
**Interfaces:** `begin`, `complete`, `review`, `prepare-clear`, `bootstrap`, `status`
consume native reads and journal receipts; artifact `run` records raw execution.

- [x] Write tests for actual CLI reads, race/failed reads, idempotent completion,
  five-ticket hold, atomic recovery, wrong identity, paused/active clear and quarantine.
- [x] Run tests; expected missing implementation failure.
- [x] Implement lease-protected atomic journal, native LIT exclusion and sealed prompt.
- [x] Run full repository suite; expected all passing with normal host socket access.
- [x] Obtain one independent whole-branch review; fix meaningful findings with regressions.
- [x] Install only owned code/policy changes in root; seal/publish updated LIT handoff.

Advance approval is durable in root AGENTS; no additional design permission is
requested. Execute inline to retain the existing visible workers and protected lanes.

Implementation evidence and adoption receipts are retained under the root `.local/buford-loop/` and the sealed clear package. Native clear remains an idle external action; production closure is outside this maintenance change.
