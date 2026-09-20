# Trusted execution-catalog replacement

`ControlPlane.replace_catalog(capabilities, expected_version=old,
new_version=new)` replaces **one existing owner's** typed execution catalog.
It is trusted VM configuration, not a model/MCP/remote tool and not a conversion
from inventory argv/action strings. Existing policy/profile checks still decide
whether a listed capability may execute.

The constructor now rejects mixed catalog revisions and duplicate capability IDs;
empty initialization uses revision1. `catalog_version` reads the current revision
under the dispatch lock. Replacements accept up to256 validated Capability records,
snapshot nested data through the existing codec and reject mixed revisions,
duplicate IDs, bool/float/nonpositive versions, an incorrect expected revision or
a non-increasing new revision. Every entry must carry the new revision. An empty
replacement explicitly advances the revision and removes all capabilities.

The complete map/revision swap and clearing of old confirmation tokens happen
under the journal's shared dispatch lock. Invalid input/CAS failures leave both
catalog and previews unchanged. The policy, profile, executor, journal and duplicate
command history remain intact. A catalog update never permits retry of a previously
seen command ID. Old previews cannot execute after successful replacement.

## Concurrency and caller duties

Dispatch, confirmation and preview issuance mark an active catalog-use lifetime.
Another thread's replacement waits for that lifetime to finish. A same-thread
replacement from an injected clock, guard, journal or executor callback rejects
with `catalog.in-use`; the RLock alone would not prevent reentrant mutation.
Failed guard refresh causes the existing guard path to fail closed. Catalog-use
state unwinds in `finally`, including exceptions.

Replacement does not cancel or undo an action already admitted to the executor;
it waits for that synchronous dispatch to finish. Trusted callbacks must remain
bounded; this method adds no callback-preemption or external-operation timeout.
It does not broadcast to separately constructed planes, establish cross-process
exclusion or persist the revision across restart. A live operator must quiesce all
old owners and establish one authority before cutover. Keep stale instances away
from execution; sharing a journal alone does not share catalog configuration.

The inventory `CatalogRegistry` remains a separate proposal/review store. A future
trusted binding must map reviewed inventory to a fixed typed capability/executor
catalog and reconcile both owners explicitly. Never blindly treat the inventory
`reviewed` flag, its revision or raw action data as this method's authorization.
There is no new generic catalog-change event schema or persistence migration;
caller-level durable configuration/observability remains integration work.

Tests cover real dispatch and confirmation with fake executors, immutable input,
invalid update preservation, stale request rejection, replay-history retention,
unchanged policy, competing publications and reentrant/threaded cutover. All tests
are offline; no live service, voice provider, action or deployment is implied.
