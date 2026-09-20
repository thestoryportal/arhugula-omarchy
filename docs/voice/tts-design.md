# Offline TTS routing and audio policy design

HENRIETTA-TTS-1, revision 3; existing ticket `arhugula-voice-profiles-c8o.4us.dn6`.
Author: Henrietta, session `01a0c097-f8c8-7c41-8bbb-b2f4ce462e85`.
Base: `5a37dca4fb060da692903f03b21a9293e7ef8706`.
Status: proposed written design, awaiting Buford attestation before product code.

## Outcome and authority

One explicitly polled TTS controller accepts supplied conversation text, selects an
explicit event/voice policy, obtains bounded PCM through the existing gateway,
and exercises interruptible playback and scoped mix restoration through fakes.
Planned tests establish host success, eligible VM degradation, silence, cancellation,
freshness, and cleanup behavior. They do not establish speech quality or live use.

- No actual synthesis/audio/mix/window/network effects, recording, downloads,
  retention or activation authority. All collaborators are fake/offline.
- Reuse GatewayClient and ProviderConfiguration; no copied gateway lifecycle or
  second SessionOwner. Here ProviderConfiguration means the existing
  `runtime.providers.configuration.Configuration` class.
- Existing SpeechQueue/control/Profile/candidate contracts stay unchanged.
- New TTS records/controller/tests/docs only. Report any required shared
  gateway/provider/session change to Buford before making it.
- Buford owns review routing, integration, CI, closure and fresh-session routing.
  Do not self-clear or infer implementation permission from this document.

## Source grounding and alternatives

These sources were inspected at the exact base above:

| Source | Constraint carried into this design |
| --- | --- |
| `runtime/gateway/client.py` | One call; host plus optional local route; deadline, replay, transient fallback and cleanup already owned here |
| `runtime/gateway/wire.py`, `schemas/gateway-v1.json` | SpeechInput carries one logical voice; returned PCM is mono 24 kHz, 16-bit, nonempty/even, at most 480,000 bytes |
| `runtime/providers/configuration.py` | Active revision binds routes; existing permits check health, service and resource budgets before each attempt |
| `runtime/voice/conversation.py`, `conversation_records.py` | Response carries TurnToken; completed turns retain the conversation lease but pending becomes None |
| `runtime/voice/session.py` | Existing generation admission and permanent cleanup fault; no TTS mode or new owner needed |
| `runtime/voice/speech.py` | Three fixed command prompts; start/cancel interface has no playback completion pump |

The selected approach is a separate output controller over those existing seams.
Extending SpeechQueue would change its finite command contract. Reimplementing
gateway jobs would duplicate fallback, authentication and cleanup rules. Both
alternatives expand authority or create competing owners. A separate module keeps
output policy local while gateway/provider rules retain their current enforcers.
[LAW:decomposition] [LAW:single-enforcer] [LAW:one-source-of-truth]

## Closed values and policy

`runtime/voice/tts_records.py` will own frozen local values, not a shared wire
schema. Constructors reject wrong types, booleans as counts, mutable containers,
invalid enums, duplicates and out-of-range values. Invalid input raises a fixed
`tts.invalid-record` ValueError without embedding input. Text/PCM are absent from
repr, notices and exceptions. Reuse the Profile codec and ConversationSnapshot;
do not copy their validation. [LAW:parse-dont-validate]

The public values are:

- `Event`: RESPONSE or STATUS. STATUS is silent unless explicitly enabled; this
  does not expand command prompts or install a status announcer.
- `Unchanged`, `Duck(gain_milli)`, `Pause`: a closed mix-intent union. Duck accepts
  integer gain 0..999; Unchanged expresses no change. This is intent for a fake
  lease, not permission to change host/VM media.
- `RouteVoice(provider_id, model_version, voice)`: exact route identity and
  approved logical voice. IDs follow the gateway identifier grammar.
- `Spoken(event, voice, mix)` or `Silent(event)`: per-event rules; no optional
  voice on a silent rule. An omitted event is also silent.
- `AudioPolicy(profile_id, policy_id, revision, configuration_revision,
  rules, voices, limits)`: unique tuple rules, at most two; unique tuple route
  voices, at most four (two events times two routes). IDs bind the existing Profile. Revisions are positive
  integers at most 2**53-1. Each spoken voice must be supported by every route
  in the active provider configuration, including optional fallback.
- `Limits(text_chars, synthesis_ms, synthesis_polls, playback_polls)`: explicit
  positive integers, ceilings 16,384 / 30,000 / 1,024 / 1,024 respectively.
  Wire byte limits remain enforced by the gateway codec, including UTF-8 voice
  plus text size; no truncation or duplicate wire parser.
- `AudioSnapshot(conversation, current_turn, policy, muted)`: immutable existing
  ConversationSnapshot, current TurnToken or None, AudioPolicy or None, and a
  literal boolean mute. The trusted supplier names the latest output-eligible
  turn even after Conversation.pending becomes None.
- `Utterance(token, event, text)`: supplied nonblank text, at most 16,384
  characters, without surrogates or controls other than newline/tab; the controller accepts
  the exact current token. A RESPONSE can be constructed from the existing
  Response token/text. It confers no command authority.
- `Phase`: IDLE, SYNTHESIZING, PLAYING, STOPPING, FAULTED. `Code` is closed:
  IDLE, STARTED, PLAYING, PLAYED, DEGRADED, MUTED, SILENT, DENIED, STALE,
  UNAVAILABLE, INVALID_AUDIO, LIMIT, CANCELED, BUSY, REPLAY, CLEANUP.
- `Notice(phase, code)` and `Completion(code, provider_id, model_version,
  failures)`: content-free results. Route IDs are optional only when no route
  completed; failures are at most three existing gateway Failure values.
  Completion never contains SpeechOutput, text, credentials or backend errors.

Mute dominates policy, and missing policy, disabled profile/voice, missing
conversation policy or mismatched profile/policy identity denies output before
any effect. Missing event/Silent rule emits SILENT; absent policy emits DENIED;
supplier failure emits UNAVAILABLE. A voice incompatibility denies the whole
configured route set before synthesis, rather than silently selecting a voice.
The gateway preserves SpeechInput.voice across fallback. Concrete voice mapping
belongs to a separately authorized adapter; no catalog candidate becomes active.

## Interfaces and responsibility

`TtsOutput(owner, gateway, configuration, catalog_version, snapshot, players,
mixes)` consumes one existing SessionOwner, a dedicated GatewayClient and its
existing Configuration, an explicit catalog revision, a bounded snapshot supplier,
and bounded inert factories for playback jobs/mix leases. Trusted composition
must pair configuration with its gateway and reserve that gateway for this output
controller. The controller never stages, approves, activates, disables or
reconfigures providers. Offline tests set up fake configurations explicitly.

`start(utterance) -> bool` reports admission. `poll() -> Completion | None`
advances one bounded step and returns a terminal result once. `cancel() -> None`
invalidates immediately and retires resources. `notice` and `cleanup_proven` are
side-effect-free properties. One active job and at most one unconsumed completion
are allowed; no queue, automatic retry, or implicit replacement. Busy admission
does not cancel somebody else's work. A cleanup fault permanently closes this
controller's admission. No reset API is provided.

The fake collaborator contracts are:

```python
class PlaybackJob(Protocol):
    def start(self, audio: SpeechOutput) -> None: ...
    def poll(self) -> PlaybackState: ...  # PENDING, COMPLETE, FAILED
    def cancel(self) -> bool: ...        # literal True proves quiescence

class MixLease(Protocol):
    def apply(self, intent: Unchanged | Duck | Pause) -> None: ...
    def restore(self) -> bool: ...       # literal True proves restoration
```

Factories return inert handles before start/apply can allocate effects; a factory
exception or malformed handle leaves cleanup unknown and faults admission.
Every acquired handle is retired even after partial start/apply failure. The mix
lease owns its captured prior state and restores only what it changed; no broad
resume, volume reset or guessed original state. Unchanged performs no mix mutation.
Restoration is idempotent, including an acquired lease never applied. Playback
cancel is idempotent, including a job never started. Callbacks are trusted and
bounded; arbitrary Python cannot be forcibly preempted.

## Freshness and replay

Admission compares the utterance token with AudioSnapshot.current_turn and binds
its profile, profile revision, conversation policy revision and context revision
to the existing ConversationSnapshot. The token's session identity must use this
owner's existing conversation identity (`owner.session_id:entry_generation`),
with a positive entry generation no greater than token.generation. The existing
owner must still accept token.generation. Disabled/missing context or policy
cannot make an old response current. AudioPolicy and active Configuration
revision are pinned too. Compare the complete immutable snapshot, not just IDs.

Recheck freshness and local cancellation after every injected callback, before
each subsequent effect and before publishing completion. Configuration changes
between completed synthesis and playback invalidate buffered PCM. Poll also
detects drift while playback is pending. Trusted revisions must be monotonic;
sampling cannot detect an unseen change-and-revert or atomically guard a real
device. Gateway-internal callbacks are governed by GatewayClient, not the outer
TTS callback barrier: a snapshot change during a gateway poll can precede an
internal fallback before that poll returns. The controller then discards its
result and proves cleanup before any playback/mix. This slice does not promise
atomic per-attempt audio-policy admission inside GatewayClient. Real synthesis
needs a trusted per-attempt binding as well as a real output adapter; adding such
a shared seam requires a separate report and authorization.

Derive request_id as SHA-256 of canonical JSON `[version=1, full TurnToken,
Event.value]`, with a fixed `tts-` prefix. Text, audio-policy revision and voice do not
change this identity: an audible attempt for the same turn/event cannot be
retried by changing content or configuration. Gateway ReplayHistory remains
the single replay owner; its 4,096-entry lifetime cap has no eviction. A suppressed
event consumes no gateway attempt. At most one RESPONSE and one explicitly
enabled STATUS can be attempted per turn. No cross-process replay guarantee.

## Lifecycle and cleanup

1. IDLE admission obtains a current snapshot and active configuration, selects
   an event rule, verifies route/voice compatibility, and constructs a validated
   gateway Request. Rejected/silent/muted starts return False with a notice and
   no synthesis, player or mix calls.
2. An admitted start invokes GatewayClient.start once. The gateway owns host
   primary, optional VM fallback, one shared deadline, permits, wire parsing and
   synthesis cleanup. Synthesis polls are additionally bounded by Limits.
3. A gateway terminal success/degradation must contain SpeechOutput and proven
   gateway cleanup. Audio stays private in memory. Preserve successful route and
   primary failure provenance, then recheck freshness before acquiring output
   handles. A gateway failure produces no playback or mix change.
4. Acquire the inert mix lease, apply its intent, acquire the inert player, and
   start with the already parsed SpeechOutput. Recheck after each call. Poll the
   player up to playback_polls; COMPLETE is not cleanup proof. FAILED, invalid
   result, exhaustion, cancellation or drift begins cleanup with no retry.
5. STOPPING first retires any owned synthesis, then cancels the player, then
   restores the mix lease. Attempt remaining cleanup even after one failure.
   Gateway cleanup, playback cancellation and mix restoration must all be
   proven. Drain only this controller's gateway terminal; do not consume or
   cancel another user's call after a BUSY rejection.
6. Publish PLAYED or DEGRADED only after cleanup and the final freshness/cancel
   gate. Otherwise publish the applicable fixed failure code once. Drop private
   text, audio, snapshot and handle references at retirement. This is bounded
   transient storage, not secure erasure or an archive/retention implementation.

Gateway fallback remains limited to its existing transient failure classes and
remaining synthesis budget. Authentication, identity, invalid response, canceled
or unproven cleanup results inside GatewayClient cannot trigger fallback. After synthesis returns, the TTS
controller never starts another synthesis attempt: playback/mix failure has no
fallback, even if nothing became audible. [LAW:no-silent-failure]

Public transitions serialize; nested start/poll is rejected as busy. A separate
cancellation gate records intent before waiting for the transition lock. A
reentrant cancel records intent and defers physical cleanup until the callback
returns, so resources allocated after cancel remain owned. Completion publication
and cancellation share a final ordering point after value construction. Status
reads never invoke callbacks. Poll budgets bound steps, not wall time.
[LAW:no-ambient-temporal-coupling]

Completion precedence is CLEANUP for any unproven resource, then observed local
cancellation or staleness, then the operation result. Gateway replay maps to
REPLAY, busy to BUSY, exhausted/timeout or poll exhaustion to LIMIT, malformed
audio to INVALID_AUDIO, and other gateway failures to UNAVAILABLE. Preserve the
original gateway Failure tuple independently of that public code. A clean
playback failure maps to UNAVAILABLE; successful fallback maps to DEGRADED only
after playback and restoration succeed. Suppressed admission creates no terminal
completion; an admitted operation has one terminal slot that must be polled
before starting another operation, including after cancel.

TTS borrows the current conversation generation: it never calls owner.begin,
never releases a clean conversation lease, and normal TTS cancel does not cancel
the conversation. Unproven output cleanup faults the matching shared lease with
the existing `owner.release(generation, cleaned=False)` operation, in addition
to latching TTS FAULTED. A stale-generation report must never alter a successor;
retain the local fault and report CLEANUP. Never repair this by replacing owner.

This does not install a conversation/TTS coordinator. A future trusted coordinator
must publish the current turn, serialize new-turn/capture/handoff operations with
TTS cancel plus cleanup proof, and retain shared admission until every borrower
quiesces. Calling Conversation.end independently can release its lease without
knowing about this output job. That combination is explicitly unsupported here;
no automatic conversation playback or platform-wide arbitration is claimed.

## Verification and remaining gates

The [implementation plan](tts-plan.md) assigns behavioral tests to records,
lifecycle, fault/reentry cases and packaged use. Use real GatewayClient,
Configuration and SessionOwner with fake effects and deterministic interleavings.
Require RED/GREEN, assertion-detecting mutations, full regression and package
smoke before immutable actual-code review through Buford.
[LAW:behavior-not-structure] [LAW:verifiable-goals]

External `.ceb.z5x.8l3` still owns provider/model and real-playback decisions.
The live-voice proposal's P4 permits only a separately selected VM provider and
explicit sink, unchanged volume and at most six prompts once authorized; it
excludes host transport and real duck/pause. P8 human intelligibility/interruption
and actual interface acceptance remain external. The epic's voice-core dependency,
cloning, archive and profile activation gates are untouched. This document does
not establish full voice-stack release or satisfy those gates.
