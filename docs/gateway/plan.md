# Offline gateway implementation plan

> **For agentic workers:** Use superpowers:executing-plans in the assigned Henrietta session. Independent review goes to Buford only.

**Goal:** bounded authenticated model-service exchanges with explicit failures and no VM action authority.
**Architecture:** strict pure wire codecs, server admission, injected client lifecycle.
**Tech Stack:** Python 3.11+, stdlib, unittest, existing zipapp packaging.
**Spec:** `docs/gateway/design.md`, grounded in the approved workspace spec and gateway handoff.

## Global constraints

- New `runtime/gateway/`, `schemas/gateway-v1.json`, gateway tests/docs only.
- No network, secrets acquisition, listeners, model/audio or GitHub operations.
- Numeric and failure-class decisions are frozen in the design and schema.
- One local writer; no changes to existing integration worktrees.

## Review focus

- Credentials must not reach a transport with the wrong peer attestation.
- A response that is valid JSON but mismatches identity/catalog cannot succeed.
- Re-entry or cancellation during an injected callback cannot restart an attempt.
- Failure to prove cleanup cannot be followed by fallback or another request.
- Boundary Unicode, base64 and bool/int cases cannot defeat byte/type limits.

### Task 1: wire contract and authenticated admission

Files: new `runtime/gateway/{__init__,wire,admission}.py`,
`schemas/gateway-v1.json`, `tests/test_gateway_wire.py`.
Interfaces: `parse_request(bytes) -> Request`, `parse_response(bytes, Request) -> Reply`;
`Admission(provider, catalog_version, bearer).admit(header, bytes) -> Admitted`.

- [x] Write tests using hand-authored v1 envelopes and synthetic credentials.
  ```python
  admitted = admission.admit('Bearer ' + 's' * 32, request_bytes)
  self.assertEqual(admitted.request.request_id, 'r1')
  with self.assertRaises(GatewayError):
      admission.admit('Bearer ' + 's' * 32, request_bytes)
  ```
- [x] Run `python -m unittest tests.test_gateway_wire -q`.
  Expected RED: missing gateway module before implementation.
- [x] Implement immutable service variants and strict bounded parsers; dedicated
  admission owns auth/provider/version/history checks. Never invoke a provider here.
- [x] Run focused tests and full ResourceWarning-error suite. Expected GREEN.
- [x] Commit wire/admission/schema/tests with fresh evidence.

### Task 2: injected request lifecycle and explicit fallback

Files: new `runtime/gateway/client.py`, `tests/test_gateway_client.py`.
Consumes Task 1 records/codecs. Produces `GatewayClient.start(Request)`,
`poll() -> Success | Degraded | Failed | None`, `cancel()` and cleanup status.

- [x] Write tests with literal remote replies and bounded in-memory exchanges.
  ```python
  client.start(request)
  client.cancel()
  self.assertEqual(client.poll().failures[0].code, 'canceled')
  self.assertIsNone(client.poll())
  ```
- [x] Run `python -m unittest tests.test_gateway_client -q`.
  Expected RED: missing client before implementation.
- [x] Implement peer-before-secret admission, single-owner lifecycle and typed
  terminal outcomes; preserve one deadline and primary/fallback provenance.
- [x] Test all five review-focus conditions plus timeout/replay/exhaustion/redaction;
  run focused/full suites and meaningful negative mutations. Expected GREEN.
- [x] Commit implementation and record evidence, limitations and personal
  learnings in `docs/gateway/checkpoint.md`.
- [ ] Buford's independent review disposition and any assigned fix pass. The
  worker's immutable request is recorded in LIT/native queue after checkpoint
  commit; publication, integration and closure remain Buford-owned.

No deployment, main landing or ticket closure is implied by local green tests.
