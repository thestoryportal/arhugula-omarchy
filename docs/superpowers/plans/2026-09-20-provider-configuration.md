# Provider Configuration Implementation Plan

> For agentic workers: use superpowers:executing-plans inline. Buford explicitly
> authorized implementation after the durable design/plan; no further general
> design audit is required. Independent review is routed through Buford.

**Goal:** Complete the attested C.4 offline configuration boundary.

**Architecture:** One provider configuration owner uses the gateway's public
serialization and cutover seam. Existing Provider and evaluation responsibilities
remain intact; fake effects demonstrate the boundary.

**Tech Stack:** Python 3.11+ standard library, frozen records, closed JSON schema.

**Spec:** `docs/providers/design.md`.

## Global Constraints

- No real network/model/update/download/persistence/UI/device effects.
- Health TTLs/budgets/update policy are explicit caller-supplied offline inputs;
  missing policy denies. No production defaults or hardware calibration.
- Bootstrap is distinct trusted local approval with exact candidate/evaluation
  binding, never fabricated active baseline. Comparison grants no authority.
- No private gateway state copying, replay/fault reset or duplicate lifecycle owner.
- Own provider package/schema/tests/docs and necessary gateway seam/tests only.
- No catalog/core/evaluation/voice/CI changes without reporting. No GitHub/closure.

## Review Focus

- Callback reentry and competing commits cannot publish inconsistent revisions.
- Cleanup and replay exhaustion remain latched through rebind and disable.
- A fallback cannot use primary-only health evidence or expired health.
- Bootstrap/rollback cannot launder failed or mismatched evaluation into authority.
- Invalid numeric types, units and shared memory cannot evade budget accounting.

### Task 1: Public gateway configuration boundary

Files: modify `runtime/gateway/client.py`; create
`tests/test_gateway_configuration.py`.
Interfaces: `configuration()` transaction, `reconfigure(host, local=None,
permit=None)`, `disable()`; permit receives Provider, service and monotonic ms.

- [x] Write behavioral tests: rebind after completed call rejects replay;
  active/unconsumed/reentrant changes reject; fault/exhaustion survive; disable
  cancels and blocks primary/fallback; per-attempt permit rejects expired fallback.
  Example: `client.disable(); self.assertRaises(GatewayError, client.start, req)`.
- [x] RED: `python -m unittest tests.test_gateway_configuration -q` fails on missing seam.
- [x] Implement the public seam under the existing lifecycle lock; invoke permit
  before begin and recheck cancellation after the callback.
- [x] GREEN: run gateway configuration/client/wire suites, then full suite.
- [x] Commit the tested seam.

### Task 2: Immutable provider input boundary

Files: create `runtime/providers/{__init__,records}.py`,
`schemas/provider-configuration-v1.json`, `tests/test_provider_records.py`.
Interfaces: immutable Manifest, Resources, Policy, Health; strict manifest/policy
parsers consume JSON-shaped dictionaries; checked records feed Task 3.

- [x] Write tests: snapshots resist caller mutation; unknown fields/versions,
  booleans as numbers, missing policies, invalid digests/units and budgets deny.
  Example: `self.assertRaises(ConfigurationError, parse_policy, {})`.
- [x] RED: `python -m unittest tests.test_provider_records -q` fails on missing boundary.
- [x] Implement closed records and schema-derived parsing, resource accounting,
  canonical digest binding; retain existing Provider codec.
- [x] GREEN: records suite and full suite; commit.

### Task 3: Trusted configuration owner

Files: create `runtime/providers/configuration.py`,
`tests/test_provider_configuration.py`, `tests/provider_mutations.py`;
extend `docs/providers/design.md` with exact API/limits and evidence.
Interfaces: Configuration stages immutable candidates; trusted review grants
opaque receipts; activate/rollback/disable publish revision under the gateway
transaction. Observe supplies epoch-bound health. Public active snapshots are
immutable. Existing ReplayRun/promotion and Task 1/2 interfaces are consumed.

- [x] Write bootstrap/activation/rollback/restart tests with a real gateway and
  literal revisions; swapped receipts/evidence, failed evaluation and missing
  policy deny without effects or mutation.
- [x] RED: `python -m unittest tests.test_provider_configuration -q`.
- [x] Implement trusted receipts and pure eligibility checks; guard uses owned
  health and explicit policy immediately before primary/fallback begin.
- [x] Add RED/GREEN tests for health expiry/future/regression, exact budget edges,
  shared pools, competing/reentrant commits, disable/fallback and fault survival.
- [x] GREEN: full suite; run in-memory mutations for review, revision, health,
  budget, restart, disable and replay retention boundaries.
- [x] Run source and fresh zipapp smoke, gateway mutations, Ruff if available,
  diff check; record unavailable checks without claiming them passed.
- [x] Commit immutable review-ready head. Send evidence to Buford; retain branch
  and durable checkpoint, record personal learning. No publication or closure.
