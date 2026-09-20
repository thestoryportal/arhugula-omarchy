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
Bootstrap explicitly approves a candidate with qualifying independent, pinned,
deterministic, unanimous passing evaluation, without inventing an active replay.
Normal activation uses `promotion()` only for comparison. Rollback stages prior
approved content with a new comparison and review; it never rewinds revision.
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

Update policy is explicit metadata: disabled or manual. This slice performs no
check/download/update; configuration approval grants none of those effects.

## Gateway seam and atomicity

The gateway owns its existing lock, active call, terminal result, replay history,
clock and cleanup faults. Add a public configuration transaction that excludes
concurrent calls and refuses callback reentry. The provider owner performs state
changes inside it. Idle-only public rebind validates routes and a bounded permit
callback, retains replay/fault state, and refuses an unconsumed result. Disable
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

## Verification

Use real configuration and gateway owners with fake transports/jobs and clocks.
Prove activation 1→2, rollback→3, exact receipt/evidence binding, rejection without
mutation, disabled admission, fallback freshness, aggregate budgets, reentrant and
threaded cutover, replay exhaustion/fault survival and fresh-owner denial. Run
negative mutations, full ResourceWarning-error suite, existing gateway mutations,
source/zipapp health and packaged imports. Independent review and required PR/main
CI remain Buford's delivery gates.
