# Offline inventory catalog refresh

`runtime.catalog.CatalogRegistry` consumes the existing fixture-backed
`runtime.inventory.discover` output. It performs no filesystem discovery,
subprocess execution, network request or runtime authorization. Inventoried
command strings stay data; review does not turn them into executable tools.

```python
from runtime.catalog import CatalogRegistry
from runtime.inventory import discover

registry = CatalogRegistry()                  # empty revision1
candidate = registry.propose(discover(fixture), expected_version=1)
# Trusted operator examines candidate.diff and candidate.snapshot privately.
# Never generate reviewed_ids from model output or blindly approve this list.
reviewed_ids = ('custom.capture',)             # example explicit decision
# Only valid if these are EXACTLY this candidate's added/changed IDs:
snapshot = registry.publish(candidate, reviewed_ids=reviewed_ids)
current = registry.snapshot(snapshot.version)
```

All additions and changes require explicit review together. Missing, duplicate,
unknown or non-tuple approvals reject without consuming the pending candidate.
`reviewed_ids` is a trusted in-process configuration decision, not authenticated
human approval. Neither this method nor private candidate data belongs in model
tools/MCP. Removals need an explicit publish call but no first-use IDs.

Entry fingerprints hash canonical JSON of source, provenance and complete data.
Order of inventory entries/object keys is irrelevant; order of lists/argv is
meaningful. A changed command, key, source, provenance or other data invalidates
prior review. Transient focus/workspace state is excluded from catalog versioning
and still needs independent fresh-context checks at execution.

Publication with any addition/change/removal advances the revision exactly once;
no-op publication preserves it. A new valid proposal supersedes the previous
pending object. A copied, foreign, replayed or superseded candidate rejects.
Validation failure does not destroy the existing pending review. A process-local
lock serializes publication, and version revalidation occurs after input copying.
Snapshot/proposal revision values must be exact integers, not bool/float/strings.

Every retained entry is a detached frozen snapshot, including nested containers.
Input bounds: at most256 entries; depth16; at most4096 nodes per entry; canonical
entry payload including provenance/source at most16384 bytes. JSON is finite;
IDs are bounded ASCII identifiers and sources are the five inventory categories.
Exceptions use finite codes. Entry data is excluded from repr, but IDs/provenance
are not a redaction system: do not log snapshots containing sensitive metadata.

## Deliberate limits

This is a **discovery catalog**, not an execution catalog replacement API. The
existing ControlPlane still owns separately validated typed Capability/policy
snapshots. Calling `registry.snapshot(old_revision)` rejects, but a previously
constructed ControlPlane or a previously returned immutable snapshot is not
magically revoked. Live binding must independently quiesce dispatch and invalidate
old confirmations when installing a new typed execution catalog. No such binding
is installed by this unit.

State and approvals are memory-only; a new registry starts empty at revision1.
Never resume stale in-flight commands across registry restarts. Persistence,
cross-process epochs, durable review receipts, live inventory collection, typed
capability/executor mapping and operational cutover are separately tracked work.
There is no hot-reload, rollback installer, host gateway or execution authority.

Validation uses fixture-backed inventory and fake data only. Tests exercise
add/change/remove/no-op diffs, review binding, malformed input, mutation attempts,
strict revisions and competing publication. Local passing tests and independent
review do not satisfy protected-main/post-main CI closure requirements.
