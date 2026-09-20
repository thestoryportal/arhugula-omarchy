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

Task 2 .z5x.hjr CLOSED in 5e6d60e: bounded immutable PCM framing and uncalibrated
RMS-energy candidate. Eleven focused tests and 159 full-suite tests pass; replay
proves synthetic silence/adaptive/max/cancel paths only. Ruling: invalid or partial
PCM terminates its parser instead of permitting resynchronization — prevents
ambiguous dropped samples; cost is a new parser/activation after stream failure.
Next .z5x.7om covers only Task 3 repository seams. P2 backend characterization and
consented recordings remain a separate human gate before live integration.

Task 3 P1 .z5x.7om implementation committed in 10b922c: bounded trusted-worker
process supervision, explicitly injected capture/transcription seams and a
synthetic-only replay CLI. Pre-review verification: 78 focused voice tests and
192 full-suite tests pass with ResourceWarning as error; five replay cases pass.
Independent Astra/high review is pending; this is not ticket completion or live
backend proof. LIT doctor reports integrity ok; LIT sync remains local/pending.
Ruling: split Task 3 at its explicit P2 STOP — costs an additional handoff, keeps
unconsented recordings and installed-backend activation outside P1.
Ruling: require explicit factories; WAV-stdin is an injected protocol, not a
Voxtype FILE compatibility claim — costs backend bridge/characterization work.
Ruling: preserve cancel()'s planned None return and expose cleanup_proven — costs
one extra coordinator check before ownership can be released.

P1 boundary review completed: Astra/high independently reviewed 3dcceed..10b922c
and passed 78 voice tests. Two Important findings concerned startup/initialization
exceptions bypassing owned child cleanup. Four regression subcases failed first;
one fix pass 7604a08 passed 17 process tests and 194 full-suite tests. Fresh
post-commit full suite passed 194/194 in 8.538s; replay 5/5, explicitly synthetic.
No Critical findings or deferred Minors. See p1-review.md for exact findings,
verification and six explicit rulings on capabilities outside this P1 scope.
.z5x.7om CLOSED; Task 3 as a whole remains partial because P2 is unresolved.

STOP: .z5x.pab is hil-required. Obtain exact consented recording paths and scope
for isolated local transcription characterization before any real inference.
P3-P8 remain separate; no new menu approval or live configuration permission.
lit next suggests .csj circle-back, but the open HIL integration/acceptance gate
prevents claiming voice release. Parent .ceb/.z5x and release remain open.
Main still has foreign untracked diagnostics. Keep branch/worktree/scratch;
do not merge or push. LIT local records are intact but remote sync is failing.
docs/voice/handoff.json contains the stopped Memento-compatible continuation.

Subsequent user response "Permissions granted" authorizes the requested P2
isolated local transcription scope, not P3-P8. Exact consented WAV paths are
still missing and have been requested; do not search personal audio directories.
Read-only inventory confirms installed bwrap and the existing Voxtype/model
paths. A five-second bounded bwrap /usr/bin/true probe with private namespaces,
cleared environment, no host home/run mounts and no capabilities failed before
the payload: "loopback: Failed to create NETLINK_ROUTE socket: Operation not
permitted". This is evidence about this tool sandbox, not proof that isolation
is impossible on the machine. No provider was invoked and no recording read.
Keep .z5x.pab OPEN/hil-required until fixtures and a usable isolation mechanism
are established. No privileged escalation, system change or download attempted.

Subsequent attended-capture approval: up to three 10-second clips, explicit
prompt/ready timing, private temporary local storage and deletion of only those
clips after testing. Zero clips consumed. No general live P3-P8 approval.
The approved execution-tool escalation (not root) allowed bwrap /usr/bin/true
and isolated Voxtype --help to succeed; prior failure was tool-sandbox-specific.
Neither help nor the probe establishes complete backend compatibility/isolation
acceptance. No microphone was opened and no inference was run.
Read-only live inventory found voxtype-commands.service active/running and
voxtype.service activating/auto-restart; default input is
omarchy_host_input_672e782964f78070. Service interruption remains unapproved.
STOP before capture: ask to quiesce both legacy services and restore prior start
intent afterward, and confirm this input. Do not repair the retrying service or
alter bindings/configuration. Home/End would be unavailable during quiescence.

User subsequently confirmed that exact temporary service stop/restart and the
current default host-input source. P2 pab manually claimed for attended work;
HIL label stays to prevent unattended continuation. No additional authority.
Services have NOT been paused and zero real clips have been captured. Wait for
per-clip Ready; recheck idle/source and unchanged config hashes at that point.
Bound capture to 10 seconds, prove owned child cleanup, then restore service
start intent before waiting for the next clip. Do not repair pre-existing faults.

Isolation preflight passed outside the tool sandbox: private runtime/home/PID/
network view, no host Voxtype config or audio/input/GPU devices, no external IP
route and cleared environment. An explicitly supplied temporary config and the
existing pinned local model transcribed 0.5 seconds of synthetic silence in
2.143s; process.ok, 115 stdout bytes, cleanup success. This is CLI execution proof,
not real ASR accuracy, silence rejection or full backend-adapter compatibility.
Private session directory /tmp/arhugula-voice-p2.SMIIotwE contains only dedicated
config and generated silence. No raw user audio/transcript enters Git or LIT.
First neutral prompt: The blue notebook is beside the window.

Clip 1 after explicit Ready: original configuration hashes and command-daemon
idle state checked; approved source present; only the two approved services
stopped. Capture emitted 311296 PCM bytes (9.728s), ending at the 10s wall
deadline (process.timeout). Cleanup was proven. Both services were restarted
and sampled active/running; config hashes unchanged. This does not repair or
establish sustained health of the pre-existing retrying dictation service.
Private WAV geometry 16 kHz mono s16 verified; peak 0.6269, RMS 0.0427.
Isolated transcription succeeded in 2.0s (132 stdout bytes, five lines), but
the expected neutral phrase was absent. This is NOT an ASR acceptance pass.
Only sanitized comparison/geometry evidence retained, not raw audio/transcript.

The originally approved automatic cleanup deleted clip-1.wav after this test.
User subsequently requested playback; by the time the request could be acted
on, deletion was confirmed and neither audio nor transcript was recoverable
from project artifacts. No playback occurred. Proposed next attended slot is
clip 2 with the same neutral sentence; retain it through playback/review before
deletion. Wait for Ready; do not start another microphone recording implicitly.
One of three capture slots consumed; ticket remains in progress, not complete.

Clip 2 on explicit retry request: same source/idle/hash checks and two-service
quiescence. Captured 315392 bytes (9.856s), ending at the 10s deadline; cleanup
proven, both services restarted, hashes unchanged. Played exactly once on the
then-current default sink omarchy_host_output_fe8f9fe212905612 at unchanged
volume (1.00); playback and cleanup process.ok. User heard only the beginning
and reported cutoff at "the blue not". This is failed speech acceptance.
Isolated ASR process.ok in 2.02s but expected phrase absent (3/6 unique expected
words found; raw transcript not retained). Energy >=0.02 RMS appears only from
8.88s to9.84s, supporting late speech/chat-cue timing rather than a full sentence
being lost by transcription. Energy is not a speech classifier.
After playback/review and timing analysis, deleted only clip-2.wav under prior
cleanup consent; no retained real clips. Two of three capture slots consumed.
Clear safe timing correction for final slot: user sends Ready then immediately
repeats the neutral sentence until Stop, instead of waiting for the delayed
Recording chat cue. Keep the <=10s recording bound, no automatic retry or extra
slot. Await Ready. P2 remains in progress; no successful speech/corpus release.

Next Ready attempt aborted in preflight before any service stop or microphone
Popen: command state file absent. No clip-3.wav was created; two actual clips
remain consumed, and the conservatively reserved third slot is released after
that proof. No automatic retry: told user Stop and await fresh readiness.
Read-only diagnosis found default dictation active/idle but command service in
zero-MainPID auto-restart, exit1. Both units' recent logs contain already-running
markers, consistent with legacy singleton contention. Before the first trial,
the command service ran and default dictation retried; after restarting both,
the winning service changed. Restored start intent is NOT both-daemon health.
No config/repair attempted; record this integration issue separately from ASR.
The operational preflight incorrectly required a missing idle file even from a
zero-PID restarting daemon. Revised read-only check passes: live PID requires
explicit idle; zero PID is allowed only inactive/failed or activating/auto-restart.
Recheck just before approved two-service quiescence and require both stopped
before capture. This permits isolated testing without repairing the legacy
configuration. Fresh Ready still required; final capture stays <=10 seconds.
