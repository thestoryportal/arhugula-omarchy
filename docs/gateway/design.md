# Offline host gateway contract

This slice supplies authenticated, bounded request/response seams for LLM,
evaluator and TTS work. It opens no socket, runs no model, and plays no audio.
Buford assigned `.298.ejy` at `75183698e1aa477973b1c6cd7ceffad48c6182c4`.
Existing VM policy remains the sole action authority; model output is data.

## Boundaries and decisions

The v1 wire envelope identifies request, service, provider/model and catalog
revision. Closed service variants are parsed into frozen records; duplicate keys,
unknown fields, non-finite values and boolean integer substitutes fail closed.
`Provider` is snapshotted through the existing public codec, not redefined.
// [LAW:parse-dont-validate] retain the checked shape at the boundary.
// [LAW:one-source-of-truth] provider facts retain their existing owner.

Requests allow 64 KiB UTF-8 wire bytes, 32 KiB total payload text, 32 unique
candidates, nesting depth 8, IDs of 1–128 ASCII identifier characters, and a
1–30000 ms budget. LLM input carries text/context/candidate IDs; its result carries
text and an optional candidate ID from that set. Evaluator input carries context
and candidate ID/text pairs; output scores every candidate exactly once with finite
scores in [0,1] and selects an optional member. TTS takes text and a voice ID;
output is canonical base64 mono 24 kHz, 16-bit PCM, 1–240000 frames (10 seconds).
Text responses allow 64 KiB wire bytes; TTS responses allow 1 MiB. No remote
audio URL, path, executable or playback instruction is accepted. Schema extension
`x-limits` is canonical for these bounds; codecs derive their limits from it.

The HTTPS endpoint and lowercase SHA-256 peer identity are trusted configuration.
The injected transport exposes its already-verified TLS peer identity *before*
receiving the bearer credential, and replies carry the same identity. Insecure
schemes, credentials embedded in URLs, query/fragment, redirects and mismatched
peers fail closed. This checks an injected TLS attestation; it does not perform
TLS verification itself. A future real adapter must obtain that attestation from
TLS, never from HTTP/body data. Synthetic bearer secrets contain 32–256 URL-safe
ASCII characters and are excluded from representations and error messages.
// [LAW:effects-at-boundaries] actual TLS/HTTP and inference remain injected edges.

`Admission` owns server-side credential, provider/service/catalog and replay
admission. Credentials are compared in constant time before parsing. Authenticated
valid IDs are retained for the owner's lifetime, up to 4096; no eviction/TTL
silently permits replay. Exhaustion rejects further work. Restart and multi-process
replay protection are explicitly outside this memory-only slice. The client has a
separate outgoing replay owner. These are distinct admission boundaries, not a
second provider registry. Provider lifecycle/activation belongs to C.4.
// [LAW:single-enforcer] each admission invariant has one named owner.

One client owns one active call, one original monotonic deadline, and one terminal
delivery. Polling, timeout, cancellation, callback re-entry and late replies cannot
start a second attempt or resurrect a result. Injected `begin`, `poll`, `cancel`
and clock callbacks must be bounded; the client does not preempt arbitrary Python
code. Cleanup returns an exact boolean proof. Missing/failed cleanup latches the
client closed. Backward/non-integer clock readings also latch closed. Caller polling
drives timeout observation; there is no background thread or scheduler.
// [LAW:no-ambient-temporal-coupling] lifecycle ordering belongs to the client.

No automatic retries. A configured VM-local provider may be tried once, within the
original deadline, only after `unavailable`, `provider_failed`, or an early transport
`timeout`. Authentication, peer identity, malformed/mismatched responses,
cancellation, clock failure, replay, exhausted history and cleanup failure never
fall back. A degraded success retains primary failure and actual provider/model;
a failed fallback retains both failures. Full-budget timeout cannot start fallback.
HTTP 502/503 map to unavailable, 504 to timeout, 401/403 to authentication;
other non-200 statuses (including redirects) are invalid responses. Their bodies
are not diagnostic messages. A begin callback returns an owned job or an atomic
`RemoteError` proving no resource was acquired; an exception lacks that proof and
latches cleanup failure. Future adapters must honor this distinction.
// [LAW:no-silent-failure] fallback is an explicit result, not disguised success.

## Verification and exclusions

Tests exercise all service results; authentication before provider admission;
schema/codec agreement; oversized/malformed/duplicate/deep data; provider, request,
service and catalog mismatch; bounded PCM; peer/redirect denial; timeout, clock
regression, cancel/late/reentrant/threaded behavior; replay/exhaustion; failed
fallback and cleanup; and redaction. Negative mutations must be caught by behavioral
tests. Full ResourceWarning-error suite, Ruff, source/fresh zipapp health and diff
checks precede the immutable review handoff to Buford. Local Ruff is unavailable;
Buford will require actual Ruff CI success on the final PR head before merging.
// [LAW:behavior-not-structure] check observable outcomes and denied effects.

No live host/network/listener/credentials/model/audio activation, concrete transport,
provider management, global persistence or VM execution authority. No edits to
existing contracts, catalog, voice, policy, journal or CI. Buford alone publishes,
reviews integration evidence, merges, verifies main and closes LIT.
