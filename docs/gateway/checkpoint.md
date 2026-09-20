# Gateway implementation checkpoint

## Assignment and immutable source

- Ticket: `arhugula-catalog-gateway-yll.298.ejy`; parent epic:
  `arhugula-catalog-gateway-yll`.
- Henrietta: session `01a0bcff-2e1f-7443-9b41-6273e8f09609`, Astra/high,
  repository-only implementation. Communicate only with Buford
  `01a0bf2f-2b1e-7840-8ecb-dfc72f9a3af0` through native Codex queue.
- Worktree: `/home/robbo/Work/arhugula-omarchy/.worktrees/host-gateway-protocol`.
- Branch: `feat/host-gateway-protocol`.
- Assigned baseline: `75183698e1aa477973b1c6cd7ceffad48c6182c4`.
- Design/plan: `1ac06be`; wire/admission: `0ee1c09`;
  implementation: `780ed887cfa2c91b6fa95493a89fc92e4f9fb03c`;
  cleanup-failure latch: `25e51c3afdcaff5379f60fc46e0ebea638a0d8c4`.
- Goal: authenticated bounded request/response seams, explicit failures/fallback,
  cancellation and replay behavior, without gaining VM action authority.

## Delivered for review

New `runtime/gateway/{__init__,wire,admission,client}.py`,
`schemas/gateway-v1.json`, `tests/test_gateway_{wire,client}.py`,
`tests/gateway_mutations.py`, and `docs/gateway/` only. No existing catalog,
voice, core, journal, provider registry, orchestration or CI files changed.

Wire envelopes use closed LLM/evaluator/TTS variants and immutable parsed values.
Admission owns constant-time bearer checking, provider/service/catalog checks and
4096-ID lifetime replay memory. Client owns one active call, one deadline, one
terminal delivery and cleanup proof. Peer attestation precedes credential release.
Typed success, degraded success and failure preserve actual provider provenance.
All transport/provider/clock effects are injected; no real adapter is activated.

## Verification evidence

Commands were run in this worktree. Full-suite runs used escalation because existing
tests need private temporary Unix sockets. Gateway edges were injected; no live
host, model or audio was used.

- Baseline: `python -W error::ResourceWarning -m unittest discover -s tests -q`
  passed 167 tests in 7.066s.
- Task 1: wire tests first failed on the missing gateway module; 17 focused tests
  then passed. Full suite passed 184 tests in 7.769s; ledger rerun 7.789s.
- Task 2: client tests first failed on the missing client module; initial 25
  lifecycle tests passed. Additional endpoint/peer/status cases failed against
  the first implementation and passed after their fixes. Final focused suite:
  `python -W error::ResourceWarning -m unittest tests.test_gateway_wire
  tests.test_gateway_client -q` — 44 tests, 1.099s.
- Full suite after final production refactor: 211 tests, 8.387s; after adding
  durable mutation probes: 211 tests, 8.295s.
- Final negative test first failed because transport cleanup could override a
  provider's explicit cleanup failure. The fix preserves the fail-closed latch.
  Fresh full verification at `25e51c3`: 212 tests, 8.180s, ResourceWarning errors
  enabled; all seven mutation probes were detected again.
- `python -m tests.gateway_mutations`: 7/7 in-memory mutations detected, each
  against a passing original test. Mutations remove authentication, envelope
  identity matching, peer-before-secret enforcement, restricted fallback,
  replay refusal, exact cleanup proof, or deadline enforcement. No file writes.
- `git diff --check`: clean.
- `python -m runtime health`: state ok, simulation, external_execution false.
- `python -m ops.build /tmp/arhugula-gateway-review.UyzajM/control-plane.pyz`
  and that artifact's `health`: successful, simulation/external execution false.
- An isolated `python -I` import from that archive parsed a literal TTS request,
  loaded the gateway schema and constructed an Endpoint. No transport invoked.
- Ruff: unavailable locally. Buford confirmed no verified installed executable
  and directed continuation without installation; actual final-head Ruff CI is
  still mandatory before integration. No local lint success is claimed.

## Review request and unresolved evidence

Request independent material/security review of baseline through the immutable
implementation, including these docs, through Buford only. No new reviewer has
been dispatched by Henrietta. This is not a review-clearance or release claim.
Review focus: credential disclosure, correlated provider/catalog responses,
callback re-entry/cancel, cleanup-failure reuse, and Unicode/base64/type limits.

Only local tests are attested here. Buford owns publication, required three-job CI,
protected merge, post-main CI and final LIT closure. No separate GitHub-user
approval gate exists. Ticket remains in progress pending review/integration.

## Rulings and limits

- Numeric limits, 4096-ID non-evicting lifetime history and transient-only fallback
  are delegated contract decisions; `design.md` and the schema record the exact
  bounds. Cost if unsuitable: a reviewed protocol revision, not silent widening.
- `begin` exceptions cannot prove cleanup. They latch closed; adapters must return
  atomic `RemoteError` when no resource was acquired. Cost: an overly strict fault
  until an adapter supplies a trustworthy cleanup/no-resource capability.
- HTTP 502/503/504 classify host loss/timeout; 401/403 classify authentication;
  redirects and other non-200 responses fail closed. No remote diagnostic text
  enters a failure result.
- TLS identity is a trusted injected attestation, not cryptography implemented by
  this slice. A real adapter must bind it to the channel carrying the credential.
- No actual Mac/network/listener/secret acquisition/model/audio/desktop operation.
  No provider installation, activation, rotation or live acceptance; C.4 remains
  separate. No transport reimplementation or broad child-audit duplication.
- Callbacks must be bounded; client polling drives deadlines, and arbitrary Python
  callbacks cannot be preempted. The synchronous lock cannot promise live latency.
- Replay and cleanup ownership are process-local. Restart, multi-process dedup,
  cross-owner catalog revocation and credential rotation are not implemented.
  The VM still validates current catalog/policy before any actual action.
- Worker stop: completed the assigned local implementation/checkpoint; await
  Buford's immutable review disposition. No publication or ticket closure by me.
- Next work: review fixes if assigned; provider-management C.4 is the next planned
  catalog/gateway responsibility, not an implementation assignment or claimed leaf.

## Personal learnings

The main checkout moved during Buford's integration work; the assigned immutable
baseline and new worktree kept this work independent. Existing implementations
were read rather than rebuilt. Avoid claiming an injected TLS identity proves a
real channel: test the credential boundary and document the adapter's obligation.
Likewise, a provider result does not prove cleanup; returning an owned job or an
atomic no-resource failure makes that distinction reviewable. Error provenance
belongs in degraded results, not in raw diagnostic strings or invisible retries.
Transport teardown is also weaker than provider cleanup: an explicit provider
cleanup failure must remain latched even when transport cancellation succeeds.
