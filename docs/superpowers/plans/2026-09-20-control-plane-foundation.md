# Control-plane foundation implementation plan

> Execute inline using superpowers:executing-plans, with one Astra/high final review.

Goal: versioned contracts, deterministic VM dispatch and a persistent correlated
event journal, bootstrappable without network or live configuration changes.
Spec: docs/superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md.
Stack: Python >=3.11, dataclasses, JSON Schema wire documents, SQLite, unittest,
zipapp. Architecture and authority boundaries remain those of the approved spec.

Global constraints: models propose; VM policy authorizes; injected executors
alone perform actions. No live executor, service, audio or network changes.
LIT orders and claims units; Git commits code; each unit closes with evidence.

Review focus: reject bool-as-int versions and unknown fields; freeze mutable
input across policy checks; deny stale/unknown/disabled capabilities; represent
executor exceptions as uncertain; reject duplicate-event conflicts and unknown
database versions without modifying existing data.

1. t78 stack/scaffold: tests/test_contract_bootstrap.py exercises
   `python3 -m runtime health`, rejects unknown commands, and builds/runs a zipapp
   outside the checkout. Implement runtime/cli.py, ops/build.py, ops/bootstrap.py
   and stack ADR. Expect missing modules first, then all tests passing. Commit,
   run bootstrap in a clean temporary clone, and record output before closing.
2. c90 contracts: runtime/contracts.py provides `decode(payload: dict) -> Record`,
   `encode(record: Record) -> dict`, and `loads(text: str) -> Record`.
   Record kinds: command, result, event, capability, policy, profile, provider,
   error. Add tests/test_contracts.py for valid roundtrips, strict types, closed
   shapes, invalid states, correlation and version rejection; add schema data
   under schemas/. Expect import failure before codecs, then a green full suite.
3. gsk runtime: `ControlPlane(catalog, policy, executor, journal).dispatch(command)`
   validates catalog version, enablement, arguments and confirmations before
   calling a VM executor. Fake executors produce success/failed/canceled/
   uncertain; denied work produces blocked. Inject IDs/time for repeatability.
   Test no executor call on denial, exception uncertainty and journal evidence.
4. A.4 journal (new LIT unit): `append(event) -> int`, `read(after=0) -> list`
   shared by memory and SQLite adapters; same-ID/same-event is idempotent,
   same-ID/different-event conflicts. Test persistence/reopen, ordering, replay,
   version refusal and correlation using temporary files, then full suite.
5. m7m circle-back: independent Astra/high review, test-first fixes, full suite
   and clean-checkout bootstrap, update spec/README/handoff, reconcile LIT,
   commit and publish only with clean worktrees and unchanged main ownership.

Every unit starts with failing behavior tests, implements only its stated seam,
runs `python3 -W error::ResourceWarning -m unittest discover -s tests -v`,
records decisions/evidence in LIT, commits, closes, and writes the handoff.
