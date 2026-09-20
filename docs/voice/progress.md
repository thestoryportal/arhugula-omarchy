# Voice execution ledger

Baseline ec4e9a2; branch feat/voice-core-contracts; isolated .worktrees/voice-core.
Approved workspace spec/plan B.1+ and refined voice-adapter-contracts design.
No live services, configuration, audio or app output authorized.

v1t: RED missing runtime.voice; implemented injected dictation state machine.
Direct/fallback output, focus changes, provider gates, service failure, cancel,
failed cleanup, observer errors and callback reentrancy covered. Reentrancy
regressions first failed (nested capture started), then busy-state ordering fixed.
Raw transcription/audio and exception contents excluded from notices/results.
Clipboard fallback is copy-only; uncertainty never causes duplicate output.

f5v: Terra/medium sole writer 93c6f60; 104 tests initially passed. Independent
Terra review found terminal-token loss; test-first fix 9245803 and scoped review
clean. Coordinator full suite 105/105 passed. Capture bounds, silence adaptation,
cancel, stale tokens and synthetic replay verified; no actual VAD/audio claims.
Ruling: synthetic fixture replay is not real audio/VAD validation; no user audio
provided or captured. Cost if wrong: add approved recordings at integration.

User subsequently authorized one live Omarchy-menu smoke after offline checks,
without configuration/service changes. iz3 may use only `omarchy menu summon
root` once; no microphone, bindings, service changes or general desktop actions.

iz3 offline implementation: VM confirmation tokens and Interaction journal kind;
data-only candidate routing, clarification, correction preview and three trusted
confirmation channels; narrow fixed-argv menu executor and dry-run smoke CLI.
RED imports plus context-binding/state-service/inferred-execution regressions.
Ruling: inferred/fuzzy proposals always preview even at high confidence — lexical
similarity can misread negation — cost is one extra confirmation, not surprise IO.
Live smoke was held until independent review and its fix round passed.

Whole-branch Astra/high review of ec4e9a2..ad686a9 found R1 shared/reopened
preview bypass, R2 state freshness after blocking journal operations and before
speech, and R3 generic context source bypassing voice profile gating. A single
Astra/high fix wave 8abd0f1 reproduced 13 failing assertions and passed 27 focused
and 137 full-suite tests. Fixes persist restrictive preview observations, carry
trusted state guards through dispatch/confirmation, recheck before speech, and
stamp voice provenance. Final scoped re-review addressed R1-R3 with no new
Critical/Important findings; reviewer independently passed 27 focused tests.

The one authorized menu smoke succeeded on 2026-09-20 at implementation HEAD
d591b15. The fixed executor acknowledged the request; a separate read-only
Hyprland layers query observed one omarchy-menu surface (zero before). Durable
SQLite records contain exactly command.started/pending then command.finished/
success, with integrity_check=ok. See live-smoke.json. The authorization is now
consumed: do not launch again, switch journal paths, or interpret this as speech
acceptance. No config, service, audio, clipboard or typing changes were made.

Review deferrals are explicit: actual mic/VAD/Whisper/TTS, atomic platform output,
physical-device arbitration, synchronous-transcription interruption and complete
live speech release are not established by mock/synthetic tests. Network tools
are not exposed. All remain subject to the original authority boundary. A menu
smoke establishes the typed executor only; o19 must not claim a live voice release
without authorized bindings and recorded/live speech acceptance.

Ticket boundary: iz3 CLOSED after evidence commit 0a1a54c and a fresh 137/137
ResourceWarning-as-error suite (6.712s). LIT doctor reports integrity ok, zero
foreign-key issues/rank inversions/cycles. Original atomic units are closed, but
the end-to-end parent arc remains OPEN: the missing live binding is now explicit
as arhugula-voice-core-b4k.ceb.z5x (Astra/high, cross-cutting, hil-required).
Parent .ceb is also hil-required so a future loop cannot treat its closed original
children as release proof. Circle-back .csj.o19 and the voice epic remain OPEN.

Stop reason: authority boundary / HIL decision. Before resuming, obtain the
permitted live-binding scope, audio fixture/source consent and config/service
change limits; preserve the existing dictation path and require a disable plan.
Do not reuse the consumed menu approval. Read LIT and current Git state, then
resolve the durable stop explicitly; do not start a model session automatically.
Retain all worktrees and the private smoke journal for recovery. The complete
machine-readable continuation context is docs/voice/handoff.json. Publishing
these verified repository commits is not a claim of a usable live voice release.

hq3 planning authorization: user approved a repository-only integration plan and
permission checklist, not runtime implementation or deployment. Read-only local
inventory found an existing legacy KP_EQUAL -> seven-second shell trigger ->
Voxtype command daemon -> direct menu hook path outside this repository. Thus
"no installed repository binding" does not mean "no legacy voice configuration".
No legacy script was executed; no daemon health or clipboard-isolation claim is
made from configuration presence. Home/End use the separate default Voxtype path.

Proposed foreground-first integration and seven-task plan now distinguish P0
(authorized planning) from P1 (repository implementation), P2 (consented replay),
P3 (isolated microphone and explicit capture-owner quiescence), P4 (provider and
playback), P5 (new one-menu budget), P6 (scoped bindings), P7 (optional user service)
and P8 (actual confirmation/dictation/rollback acceptance). No TTS executable was
found on the inspected PATH; provider choice remains explicit. New design/plan
are PROPOSED, not approved. Keep z5x and parent HIL-required; do not resolve the
worker stop based on permission to write documents.

P1 continuation authorized subsequently: user released conflicting LIT work and
explicitly approved repository-only work in the clean voice-core worktree while
leaving foreign main diagnostics untouched; merge/push remain deferred.
Task 1 .z5x.kpp CLOSED, commit 3676cb3: cancellation invalidates logical work but
retains physical cleanup ownership; failed cleanup latches unavailable. Eleven
focused tests and 148 full-suite tests pass. No external resources are opened.
Ruling: SessionOwner is a process-local admission contract, not an OS device
lease — downstream coordinator must prove cleanup/exclusive IO ownership.
Task 2 inline routing explicitly promoted to Astra/high for the new device-byte
admission contract; cost is higher model usage, no change to P1 authority.
