# Offline catalog refresh design

Scope: approved workspace design and implementation plan C.1/C.2, LIT
`arhugula-catalog-gateway-yll.298.din`. Native Astra/high implementation in
`feat/catalog-refresh`; Terra retains observability/CI, shared desk reviews.
Robbo explicitly authorized continuous repository work and autonomous bounded
design decisions. No live discovery, host access, provider or system changes.

## Intent and boundary

Consume the existing `runtime.inventory.Inventory` rather than invent another
discovery format. Build deterministic versioned snapshots and reviewable
add/change/remove diffs, including custom bindings. Inventory action strings,
argv, provenance and review markers remain data: nothing executes or authorizes
an action. Existing ControlPlane typed capabilities/policy remain unchanged.

Use an in-memory VM-owned `CatalogRegistry`, initially empty at revision1.
Immutable snapshots contain sorted entries with stable SHA-256 fingerprints,
source/provenance and frozen data. Fingerprints cover the complete entry, not
transient focused-app/workspace state. Reject malformed/duplicate records,
unsupported source, nonfinite JSON, excessive depth/size and invalid versions.
Snapshot caller-owned values before retaining them.

`propose(inventory, expected_version=...)` computes the candidate and exact
added/changed/removed/unchanged IDs. Changes produce revision+1; a no-op keeps
the revision. New or changed entries are unreviewed, even if an input field
claims approval. Only unchanged entries retain prior review. Proposal order and
JSON object-key order do not affect fingerprints or diffs.

`publish(candidate, reviewed_ids=...)` is a trusted operator/VM API, never a
model tool. Require the exact pending candidate object, its current base revision,
and explicit IDs for every added/changed entry; reject missing, duplicate or
extra approvals. A replacement proposal supersedes the previous one. Publication
is atomic under a process-local lock and consumes the candidate. A forged/copied,
stale, replayed or foreign-registry candidate cannot publish. `snapshot(version)`
rejects stale/malformed revisions before returning data.

## Non-goals and costs

Review is candidate-content-bound process-local configuration, not authenticated
human identity, execution authorization or persistent approval. A restart starts
an empty registry; persistence/receipt recovery is a separate unit. No production
hot-reload connection to ControlPlane is added: old ControlPlane instances retain
their own constructor snapshots. A future trusted binding must quiesce dispatch
and replace its typed catalog/confirmations atomically; this unit does not claim
to revoke execution authority in an already-running ControlPlane.

Raw discovery data may contain sensitive command strings; exclude entry data from
repr/errors and do not log or journal snapshots by default. No fixture content is
executed. Live Omarchy discovery and capabilities-to-executor mapping remain
separate characterized adapters.

## Acceptance

Test initial discovery/review, same-data no-op, deterministic ordering, custom
binding addition/change/removal, source/provenance change, duplicate/malformed
input, immutable snapshots, superseded/foreign/forged/replayed candidates,
strict revision/approval types and competing publication. Prove stale version
requests reject. Existing full suite and runtime/fresh zipapp health must pass.
Independent range review and protected main/post-main CI precede LIT closure.
