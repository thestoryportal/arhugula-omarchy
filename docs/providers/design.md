# Offline provider configuration

C.4 implements one trusted local configuration owner above the existing gateway.
Buford attested this scope for `.298.isr` at `fd03988` on 2026-09-20.
This document serves implementers and reviewers; it does not authorize live use.

## Ownership and trust

`runtime/providers/records.py` parses closed immutable manifests and explicit
offline policy. Provider identity, placement, version and capabilities reuse the
existing Provider codec. Enabled and health are derived snapshots. A manifest
binds a provider to an artifact digest and resource estimates; a candidate binds
host and optional VM fallback manifests, route identities, policy and evaluation.
No endpoint, credential or executable is accepted from a manifest.
// [LAW:one-source-of-truth] existing contracts own provider identity.

`runtime/providers/configuration.py` owns candidates, trusted review receipts,
active revision and health observations. Its public local review API is trusted
configuration authority, never a model/tool wire API. Receipts are opaque,
owner-bound, single-use object identities held by the owner. Candidate snapshots
include baseline revision, exact routes, manifest digests, policy, immutable
ReplayRun evidence and pinned bundle digest. No wire flag becomes a receipt.
Bootstrap explicitly approves newly configured roles with qualifying independent,
pinned, deterministic, unanimous passing evaluation, without inventing an active
replay. Adding fallback requires bootstrap for that new role and still compares
the existing host. Removing fallback compares the retained host. Normal activation
uses `promotion()` only for comparison. Rollback stages prior approved content
with a new comparison and review; it never rewinds revision.
// [LAW:parse-dont-validate] receipt identity retains locally granted authority.

Health observations are trusted local data, bound to candidate artifact and owner
epoch. Caller-supplied monotonic milliseconds and explicit TTL determine freshness
at commit and each gateway attempt. Missing policy/health, future or stale time,
unsupported degraded use and resource excess deny. Resource vectors use RAM,
accelerator memory and disk bytes, CPU millicores and concurrency slots; policy
supplies separate VM/host ceilings. Explicit shared-memory accounting combines
RAM and accelerator allocations into the RAM ceiling. Estimates account for all
configured resident providers; this single-call gateway reserves one execution
slot. No hardware measurements or production defaults are supplied.
The public budget boundary snapshots its iterable and accepts exact Manifest
records only; their constructors own resource and placement validity. Lookalikes
and subclasses cannot silently escape accounting through an unknown placement.

Update policy is explicit metadata: disabled or manual. This slice performs no
check/download/update; configuration approval grants none of those effects.

## Gateway seam and atomicity

The gateway owns its existing lock, active call, terminal result, replay history,
clock and cleanup faults. `claim_configuration()` exclusively attaches one owner
and atomically closes admission. Public configuration transactions require that
owner's opaque token, exclude concurrent calls and refuse callback reentry.
Polling inside a transaction cannot advance a call. The provider owner performs
state changes inside this boundary. Idle-only public rebind validates routes and
a bounded permit callback, retains replay/fault state, and refuses an unconsumed result. Disable
closes new admission and cancels through the existing lifecycle, including during
callback reentry. Failed cleanup stays latched. No gateway private fields are read
or copied by the provider package. A permit is checked immediately before every
primary/fallback begin; refusal produces canceled, without fallback or effects.
Existing callers without a permit retain existing behavior.
// [LAW:no-ambient-temporal-coupling] gateway alone serializes effect lifetimes.

Candidates and review receipts never change active state. Commit checks baseline,
receipt, evaluation, health, budgets and gateway quiescence before publishing a new
revision. Denials leave active state and receipt consumption unchanged. Disable
advances revision and preserves content for inspection, closing fallback as well.
Calls already admitted retain their route; ordinary changes return busy.

New owners start disabled with a fresh in-memory identity. Prior receipts and
health observations do not transfer. Restores are input candidates only. No
persistence, process supervision, UI, network, models, downloads, audio, devices,
catalog/core/evaluation/voice changes or GitHub work belongs to this slice.
`.0hj` retains durable epochs, cross-process replay and actual provider release.
The host-side `Admission` remains a separate unchanged owner; VM cutover does not
claim atomic host reconfiguration or fresh server replay protection.

## Local API and limits

`parse_manifest(document)` requires a version-1 Provider with `enabled=false`
and `health="unavailable"`; input flags cannot pre-enable a route. It returns an
immutable Manifest whose digest binds all provider and resource fields.
`parse_policy(document)` requires every field in the packaged schema; neither
parser invents default TTLs or budgets. Each JSON-shaped input is at most 64 KiB.
The schema defines shape; record constructors additionally enforce canonical
disabled input state, nonempty capabilities and at least one resource slot.

`Configuration(gateway)` claims that existing client once and starts at
`Disabled(0, None)`. `stage(manifest, host, policy=..., evidence=...,
local_manifest=..., local=...)` captures the exact immutable candidate. Host/Local
contain already trusted injected effects; their mutable implementation is not
made trustworthy by staging. Evidence contains the exact manifest digest, pinned
bundle content digest, ReplayRun and independent evaluator identity tuple, ordered
host then optional VM. No evidence/approval data is loaded from a model response.

`observe(candidate, provider_id, status=..., observed_at_ms=...)` records a trusted
local observation in this epoch. `approve_bootstrap(candidate)` authorizes new
roles, while `approve(candidate)` authorizes ordinary changes. Both return opaque
single-use receipts; `activate(candidate, receipt, now_ms=...)` consumes one only
on success. `reject(candidate)` revokes a staged change, not the active state.
`restore(revision, evidence=...)` stages earlier content for fresh comparison and
approval. `disable()` increments revision and closes admission through gateway
cancellation. `state` returns an immutable Active or Disabled record.

Configuration times and gateway clock readings must share one monotonic epoch
and millisecond units. Health age is inclusive of the configured TTL. Regressing
health observations deny; invalid or regressing current time latches this owner
closed. Health/permit refusal is exposed by the gateway as `canceled`, retaining
any preceding host failure. It cannot silently invoke a fallback.

There are at most 256 retained candidates, outstanding receipts and retained
activation revisions per owner; reaching a limit denies without eviction or
reset. Exhaustion can deny a restore or rollback as well as a forward change;
disable remains available and does not require free history capacity. These are memory bounds,
not production provider resource defaults. The existing gateway admits one call
at a time. Resource accounting conservatively includes all configured providers
and adds accelerator bytes to the RAM pool for explicitly shared placements.
It does not measure real usage or supervise processes. Review receipts prove
trusted local API invocation, not human authentication or evaluator execution;
those sources must be supplied by a later authorized integration.

## Verification

Use real configuration and gateway owners with fake transports/jobs and clocks.
Prove activation 1→2, rollback→3, exact receipt/evidence binding, rejection without
mutation, disabled admission, fallback freshness, aggregate budgets, reentrant and
threaded cutover, replay exhaustion/fault survival and fresh-owner denial. Run
negative mutations, full ResourceWarning-error suite, existing gateway mutations,
source/zipapp health and packaged imports. Independent review and required PR/main
CI remain Buford's delivery gates.
