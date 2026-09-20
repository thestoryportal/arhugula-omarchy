# Offline Catalog Refresh Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for native execution
> with test-driven-development and one shared immutable-range review.

**Goal:** Version fixture-discovered inventory and require content-bound first-use
review before publishing catalog snapshots.
**Architecture:** One process-local registry, immutable data snapshots, deterministic
fingerprints/diffs, trusted publication and strict stale-version rejection.
**Tech Stack:** Python3.11+ standard library; existing runtime.inventory.
**Spec:** ../specs/2026-09-20-catalog-refresh-design.md

## Global Constraints

- Models propose; VM policy/executors authorize and act. No action strings execute.
- No live discovery, network, audio, configuration/service/package changes.
- One Astra-owned worktree; no CI, projections, voice or contract/schema edits.
- Review/verification evidence is local until protected main and post-main CI.

## Review Focus

1. Mutable/forged Inventory construction must not mutate retained entries.
2. Input approval-like fields cannot bypass explicit candidate review.
3. Source/provenance/action changes invalidate review even with the same ID.
4. Concurrent/replayed/superseded publications cannot advance twice.
5. Revision checks reject bool/float and snapshots cannot imply live revocation.

## Task 1: Versioned candidate registry

**Files:** create runtime/catalog.py, tests/test_catalog.py, docs/catalog/refresh.md.
**Consumes:** existing Inventory/InventoryItem from runtime.inventory.discover.
**Produces:** CatalogRegistry.propose(inventory, *, expected_version),
publish(candidate, *, reviewed_ids), snapshot(version); CatalogError and frozen
CatalogEntry, CatalogSnapshot, CatalogDiff, CatalogCandidate records.

- [ ] Add a failing test using the real inventory fixture:
  ```python
  registry = CatalogRegistry()
  candidate = registry.propose(discover(fixture), expected_version=1)
  assert candidate.diff.added == ('app.terminal', 'bind.launcher', 'custom.capture',
                                  'menu.root', 'omarchy.menu.root')
  with self.assertRaises(CatalogError):
      registry.publish(candidate, reviewed_ids=())
  snapshot = registry.publish(candidate, reviewed_ids=candidate.diff.added)
  assert snapshot.version == 2
  with self.assertRaises(CatalogError):
      registry.snapshot(1)
  ```
- [ ] Add named tests for each acceptance case in the spec, with literal expected
  custom-binding diffs, deep mutation attempts and two competing publishers.
- [ ] Run `python3 -m unittest discover -s tests -p test_catalog.py -v`.
  Expected: missing catalog module, then failing assertions until implemented.
- [ ] Implement bounded canonical snapshots, stable SHA-256 fingerprints, sorted
  diffs and a locked registry. Keep publication guards before any mutation:
  ```python
  if candidate is not self._pending or candidate.base_version != self._current.version:
      raise CatalogError('catalog.candidate')
  required = candidate.diff.added + candidate.diff.changed
  if set(reviewed_ids) != set(required):
      raise CatalogError('catalog.review')
  ```
  Validate exact tuple/string/unique approval types before set comparison.
  Freeze nested values, bound entries256/depth16/entry JSON16384 bytes, and use
  finite JSON. No-op publication retains the revision; consume pending candidate.
- [ ] Rerun focused tests (expected all pass), then full ResourceWarning-error suite,
  `git diff --check`, runtime health and a fresh ops.build zipapp health.
- [ ] Document the non-authoritative boundary and record LIT evidence, then commit
  only the named files and request the shared review desk's immutable range.
- [ ] Address Important findings test-first; persist docs/catalog/handoff.json and
  review disposition. Keep ticket awaiting-integration until main/post-main gates.

Self-review: C.2 inventory refresh covered; live C.1 collectors and hot ControlPlane
catalog binding are explicitly excluded and must be tracked as follow-up work.
No wire-contract migration, live deployment or external acquisition is implied.
