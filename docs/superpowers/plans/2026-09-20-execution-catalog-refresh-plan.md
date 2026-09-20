# Trusted Execution Catalog Replacement Plan

> **For agentic workers:** Use superpowers:executing-plans and TDD in the existing
> isolated catalog worktree. Shared review desk handles the immutable range.

**Goal:** Safely replace one VM ControlPlane's typed catalog without reviving old
commands or confirmations.
**Architecture:** Trusted in-process API under the existing journal dispatch lock;
strict expected-version compare-and-swap, monotonic revisions and preview clearing.
**Tech Stack:** Python3.11+ standard library, existing Capability codec.
**Spec:** ../specs/2026-09-19-omarchy-agent-workspace-design.md, Catalog/policy sections;
refines the explicit hot-replacement gap in ../specs/2026-09-20-catalog-refresh-design.md.

## Global Constraints

- VM policy remains execution authority; no raw inventory action/argv mapping.
- Repository-only .298.1td, Astra owns runtime/core.py and new focused tests/docs.
- No live/network/provider/config/service changes or automatic policy enablement.
- Keep duplicate command history; no replay or cancellation of already-started effects.
- One ControlPlane owner only; this API is not cross-process/global revocation.
- Existing protected main and post-main CI gates remain required for final closure.

## Design and Review Focus

Constructor catalog entries must share one revision; an empty initial catalog has
revision1. New read-only `catalog_version` reports the current revision under lock.
`replace_catalog(catalog, *, expected_version, new_version) -> int` validates and
freezes at most256 typed capabilities before acquiring the lock. Require exact
positive integer versions, expected==current, new>current and every candidate
entry's catalog_version==new. Reject duplicate IDs and malformed data. Empty
replacement is allowed with its explicit new revision. Return installed revision.

Under the journal lock, swap the complete map/revision and clear outstanding
confirmation tokens, retaining policy/profile/executor and duplicate history.
Concurrent replacements using the same expected version yield one winner.
Wrap dispatch/confirm/preview lifetime in a private catalog-use context: same-thread
reentrant refresh from trusted guard/journal/clock/executor callbacks must reject,
while another thread waits for the current call to finish. This prevents the RLock
from allowing catalog changes between authorization and actuation/preview storage.

Review focus/tests: invalid replacements leave existing previews intact; successful
replacement invalidates old previews; stale commands reject without executor calls;
reentrant replacement cannot slip through the shared RLock; blocked in-flight
execution completes under its original catalog before queued replacement proceeds.
No retroactive cancellation or synchronization of separately constructed planes.

## Task 1: Atomic trusted replacement

**Files:** runtime/core.py; tests/test_catalog_replacement.py;
docs/catalog/execution-refresh.md. No wire/schema or voice edits.

- [ ] RED tests for missing replacement API and mixed constructor revisions:
  ```python
  plane.replace_catalog([capability_v2], expected_version=1, new_version=2)
  assert plane.catalog_version == 2
  assert plane.dispatch(command_v1).error.code == 'catalog.stale'
  ```
  Add test tables for bool/float/stale/decreasing/mixed revisions, duplicate IDs,
  immutable caller data, empty catalog, retained history/policy and invalidated
  tokens. Use threading events/barriers for ordering and two competing refreshes.
- [ ] Run `python3 -m unittest discover -s tests -p test_catalog_replacement.py -v`;
  expect missing API/mixed-revision acceptance failures before implementation.
- [ ] Add shared catalog validation, revision state and trusted CAS method. Reuse
  codec snapshots. Add catalog-use context around preview/confirm/dispatch:
  ```python
  with self._journal.dispatch_lock:
      if self._catalog_users:
          raise ValueError('catalog.in-use')
      if expected_version != self._catalog_version or new_version <= self._catalog_version:
          raise ValueError('catalog.stale')
      self._catalog = replacement
      self._catalog_version = new_version
      self._confirmations.clear()
  ```
- [ ] Focused tests and full ResourceWarning-error suite must pass, then diff check,
  runtime/fresh zipapp smoke, meaningful local combined-branch verification.
- [ ] Record scope/rulings/evidence in LIT and docs, commit focused unit, request
  independent immutable-range review, fix Important findings test-first, hand off.
  Keep awaiting-integration until actual protected main and post-main CI.
