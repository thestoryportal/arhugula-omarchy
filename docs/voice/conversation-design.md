# Offline conversation lifecycle design

HENRIETTA-CONVERSATION-1 implements `.4us.jsq` from integrated base
`91cfb7a5a193ddee21dcd95564fc5b5a3361e985`. The attested approach is a separate
controller over SessionOwner. This document fixes the implementation details for
Buford's review; offline acceptance does not satisfy the epic's live release gate.

## Purpose and boundaries

Trusted callers can enter a conversation, submit successive text turns, inspect
content-free status, clarify a memory conflict, interrupt a turn, or end the
session. Conversation never dispatches commands or outputs audio. Entry channels
are voice, panel, and keyboard, permitted explicitly by policy. Inputs are method
calls, not listeners. There are no default keys, providers, ambient context reads,
archive writes, retention rules, memory promotion, or execution authority.

Extending Coordinator would expose command dispatch. Reusing SpeechQueue would
confuse finite command prompts with conversation responses. A separate controller
keeps those authorities apart. Reusing SessionOwner avoids a competing admission
lock. [LAW:decomposition] [LAW:one-source-of-truth]

## Records and policy

`runtime/voice/conversation_records.py` owns frozen, closed local records. These
are Python API values, not additions to the shared control protocol or schemas.
Constructors reject unknown enum values, mutable collections, booleans as counts,
unbounded strings, and invalid combinations. Content fields do not appear in repr.

ConversationPolicy binds profile ID, policy ID, and a positive policy revision to
explicit entry channels, an exact whole-utterance exit phrase, a setup-selected
exit key, and Limits. Setup evidence supplies a positive revision plus occupied
and reserved key sets. The exit key must be absent from both sets; this proves
consistency of supplied evidence, not actual platform binding availability.
Limits bound turns, text characters, context characters/items, and polls per job.
Implementation ceilings reject excessive limits. No implicit truncation occurs.

Snapshot combines the existing Profile, a supplied positive profile revision,
policy (or explicit absence), setup evidence, and Context. Context has a positive
revision, provenance-bearing immutable items, and one of available, empty,
conflicting, unavailable. Conflicting input carries an exact conflict ID and at
least two items; empty/unavailable carry no items. Available carries items.
Unavailable context refuses admission instead of masquerading as empty memory.

Every turn token carries owner/session identity, turn number, generation,
profile/revision, policy revision, and context revision. A request carries its
token, text, immutable completed history, context, and optional exact conflict
resolution. Responses echo the full token. A clarification echoes both token and
conflict ID and explicitly chooses current speech or rejection. Only current
speech confirmation permits the pending conflicting turn to start; stored context
remains unchanged. Completed history preserves that resolution's provenance.

## Lifecycle and resource ownership

`runtime/voice/conversation.py` owns the conversation and one injected owner,
snapshot supplier, and response-job factory. Jobs expose bounded synchronous
`start(request)`, `poll()` (response or None), `cancel()`, and literal boolean
`cleanup_proven`. The controller owns a returned job even if start partially fails.
Factories must either return a cleanup-capable job or raise without allocating
resources; an unknown construction/cleanup outcome faults admission conservatively.

The controller holds a conversation lease while ready, processing, or clarifying.
Completed turns retain that lease and session identity. Cancel-turn invalidates
the generation, cleans the job, releases, and reacquires a fresh conversation
generation while retaining history/session identity. Another participating client
may win that release/reacquire interval; then conversation ends. End-session and
handoff release without reacquiring and discard in-memory history. A later entry
uses a new session identity. Failed/unknown cleanup permanently faults SessionOwner.

Public transitions serialize under a reentrant lock. A transition guard refuses
nested submit/enter/poll/clarify calls. Cancellation invalidates the generation
before waiting on the transition lock. Reentrant cancellation records its intent;
cleanup occurs after the active collaborator returns, so a callback cannot allocate
a resource after cleanup and escape ownership. End overrides turn cancellation.
External SessionOwner cancellation also invalidates the conversation. No callback
is invoked under SessionOwner's own lock. [LAW:no-ambient-temporal-coupling]

Sample the trusted snapshot and recheck generation/cancellation after each injected
callback and immediately before accepting a response. Any snapshot drift ends the
session, including disabled profile, missing policy, changed setup/context, or
changed revisions. Suppliers must report monotonic revisions; this API cannot
detect an unseen change-and-revert between samples. Foreground calls must be made
to observe changes; there is no background monitor. Jobs must be bounded; Python
callbacks cannot be forcibly preempted. Poll count bounds pending work, not wall time.

Display is a version-1 immutable notice derived from lifecycle state: inactive,
ready, processing, clarifying, stopping, faulted. It contains bounded identifiers,
state and a closed reason code; no text, memory, key, or phrase. Reading status has
no callbacks or side effects. Successful responses return to the trusted caller
only after cleanup and final freshness checks; no response observer is installed.

## Acceptance and external obligations

Tests cover all channels, exact exits, continuity and limits, conflict provenance,
stale/foreign/replayed results and clarification, state drift, callback reentry,
cross-thread cancellation, partial failures, and cleanup faults. Shared admission
tests cover command/dictation/conversation clients using the same SessionOwner;
they do not prove platform-wide Home/End arbitration. No shared Profile expansion,
router/coordinator/control, candidate contract, TTS, gateway, core, catalog, or CI
changes are included. Archive `.6br`, pruning `.pi1`, setup `.zcy`, and TTS
`.dn6`/`.8l3` remain external obligations. Buford owns independent review routing,
integration, CI and closure. Writer is released before integration.
