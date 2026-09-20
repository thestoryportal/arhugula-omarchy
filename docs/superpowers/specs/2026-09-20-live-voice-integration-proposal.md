# Live voice integration proposal

Status: PROPOSED, NOT APPROVED FOR IMPLEMENTATION OR DEPLOYMENT.
Planning ticket: `arhugula-voice-core-b4k.ceb.hq3`.
Integration ticket: `arhugula-voice-core-b4k.ceb.z5x` remains HIL-required.

## Intent and authority

The user approved preparing a repository-only plan and permission checklist.
The intended destination remains independent Home/End dictation plus one-shot
KP_EQUAL command capture, local transcription, clarification and confirmation,
and VM-authorized actions. Success means an observed live speech path with no
command text reaching a focused application, not merely passing mocked tests.

This proposal refines the approved [workspace design](2026-09-19-omarchy-agent-workspace-design.md)
and [adapter contracts](2026-09-20-voice-adapter-contracts-design.md). It does not
relax their authority boundary or the user's prohibitions. The earlier approval
for one menu opening was consumed; it is not permission for another test.

## Read-only observations, 2026-09-20

Baseline repository commit: `e8f5b8ba56dbc2e28a4803020a7a0cee2e7e1601`.
No recording, transcription, playback, service operation or menu launch was
performed during this planning inventory. Service configuration presence is NOT
evidence that a daemon is running or healthy. Model presence is NOT inference
or accuracy evidence. The following are local observations, not portable defaults.

| Observed source | Relevant finding |
| --- | --- |
| `/home/robbo/.config/hypr/bindings.lua:22` | HOME invokes `voxtype record start`; END invokes `voxtype record stop` |
| Same file, line 28 | KP_EQUAL invokes `/home/robbo/.local/bin/omarchy-voice-command-trigger` |
| That trigger script | Starts the command-profile daemon recording, sleeps seven seconds, then stops it |
| `/home/robbo/.config/systemd/user/voxtype.service` | Separate default dictation daemon |
| `/home/robbo/.config/systemd/user/voxtype-commands.service` | Command daemon reads `/home/robbo/.config/voxtype/commands.toml` |
| Command profile | Local Whisper `base.en`, 16 kHz, eight-second maximum, clipboard output mode, post-process hook |
| `/home/robbo/.local/bin/omarchy-voice-commands` | Hard-coded phrase matching launches `omarchy-menu summon` directly; all branches emit no transcript |
| Default dictation profile | Local Whisper, typing with clipboard fallback, media pause enabled; leave these settings unchanged |
| Installed CLI help | Voxtype 1.0.1 exposes `transcribe FILE` for 16 kHz mono WAV; help does not establish output isolation |
| Existing model file | `/home/robbo/.local/share/voxtype/models/ggml-base.en.bin`, 147,964,211 bytes |
| Executable discovery | `/usr/bin/pw-record`, `/usr/bin/pw-cat`, `/usr/bin/voxtype` present; `whisper-cli`, `whisper`, `espeak-ng`, `piper` not found on inspected PATH |

The repository has no installed live binding, but the machine already has a
legacy live-command configuration. Do not confuse these statements. The legacy
hook does not use this repository's validator, approval tokens or journal.
Its empty stdout does not prove that the surrounding clipboard-configured
pipeline has no clipboard effect. Do not execute it as a characterization test.
No claim is made that the legacy path is broken or that it has leaked text.

## Options and recommendation

1. **Foreground coordinator, then opt-in cutover — recommended.** Keep existing
   files unchanged while building and testing isolated adapters. Use approved
   recordings before an explicitly isolated microphone session. Request exact
   binding/service changes only after acceptance. Lowest initial deployment scope.
2. **Patch the existing Voxtype post-process hook.** Fewer files, but its daemon
   output pipeline, seven-second trigger and direct action path do not provide
   the required adaptive capture, shared ownership and correlated authorization.
   Reject as the default integration approach.
3. **Replace dictation and command services together.** Simplifies eventual
   ownership, but immediately risks the working typing/clipboard path. Defer;
   it is not necessary to validate command control.

## Proposed architecture and invariants

Foreground VM coordinator owns an activation generation, cancellation, mode,
mute state and capture process. Each activation creates a fresh ID and a bounded
capture; there is no always-listening mode. Existing `CommandCapture` receives
20 ms frames (640 bytes, signed little-endian PCM, mono 16 kHz), with its current
15,000 ms maximum, 3,000 ms initial silence and 700/400 ms adaptive trailing silence.
All queues and subprocess outputs have explicit limits and monotonic deadlines.

Capture, VAD and transcription are separate adapters. A standard-library RMS
energy detector is a candidate, NOT an approved speech detector; pin its threshold
in the replay manifest and reject it if silence/noise/quiet-speech gates fail.
No threshold is promoted solely because synthetic frames pass. A learned VAD
would need separate dependency/model approval if the candidate is inadequate.

Prefer characterizing the installed Voxtype file-transcription interface with
a dedicated repository config and the existing model. Do not use either live
daemon config: those contain typing, clipboard or post-processing behavior.
The isolated file CLI must prove transcript-only output and no desktop/network
effects before becoming the backend. Missing proof is a stop, not a reason to
try a live daemon or download another provider. The concrete safe config and
stdout parsing contract are deliverables of that characterization, not assumed
from `--help`.

Transcription feeds `VoiceRouter.handle(text)`, with current trusted `VoiceState`;
models cannot choose a shell command, executable, output destination or approval.
Only `menu.open` with `name=main` is enabled initially. Exact aliases may execute
after VM checks; inferred/corrected phrases preview; ambiguity asks for a new
activation. Confirmation remains expiring, single-use and context-bound. Do not
reuse the old smoke ID or database for a new authorized session, and do not invent
new IDs to repeat an uncertain action within that session.

Command capture has no typing, paste or clipboard dependency. Dictation remains
on the existing Voxtype daemon; a future approved Home/End wrapper only arbitrates
ownership then forwards those existing start/stop commands. It must not add a
second transcription or output path. If the coordinator fails, command mode
fails closed; dictation fallback is allowed only after proving that no command
capture/transcriber remains alive. Never silently start both owners.

Polling `voxtype` state alone is not a mutual-exclusion mechanism. An isolated
foreground microphone trial requires permission to quiesce conflicting legacy
capture owners, or an independently verified exclusive arrangement. For normal
use, approved Home/End and KP_EQUAL wrappers serialize entry through the owner;
unexpected direct legacy recording invalidates command mode. External callers
that bypass the owner remain an explicit support boundary, not a solved race.

A private Unix socket may expose a closed set of trusted local control messages
(activate, cancel, status, mute, dictation-start/stop, confirm). Owner-only
directory/socket modes, peer credentials and bounded messages exclude other
UIDs, not hostile processes running as the same user. Neither models nor MCP get
this endpoint. No network listener or arbitrary command payload is allowed.

Fresh focus/mode/mute/activation state must be checked after queue/persistence
waits and at actuation. A journal lock does not lock the compositor. If platform
atomic compare-and-act cannot be provided, record the limitation and block
focus-sensitive output; never claim polling eliminates that race. The first
menu action is global, but stale context still invalidates its authorization.

Foreground visual status is required even when speech is disabled. Spoken
clarification requires a separately approved local TTS backend, finite trusted
prompt vocabulary and interruptible playback. No suitable standalone executable
was discovered; text-only mode is useful interim behavior, NOT completion of
spoken clarification. A real panel confirmation adapter is also a release gate;
a simulated `channel="panel"` call is not evidence of a working panel.

## Permission checklist

Every row is independently scoped. Only P0 is authorized by the latest user
message. Approval of this proposal or a later row does not imply all other rows.

| Gate | Requested future authority | Explicit exclusions |
| --- | --- | --- |
| P0 — authorized now | Read-only discovery; repository documentation, LIT evidence, verified commits and existing-remote publication | No runtime implementation or live effects |
| P1 — pending | Implement repository adapters, fake-process tests, config/service templates and replay harness | No installing templates, live audio, real provider inference, service control or downloads |
| P2 — pending | Read specifically user-approved local recordings; run isolated local file transcription using the existing pinned model | No microphone, speech playback, clipboard, typing, hook/daemon execution, uploads or provider downloads |
| P3 — pending | User-attended foreground microphone trial: approved source only, at most 12 activations of at most 15 seconds; at most 30 seconds transcription per activation; fake executor | No menu/action effects, playback, automatic retrials, device/default/volume changes or continuous capture |
| P3 ownership subgate — pending | If necessary for isolation, temporarily stop ONLY `voxtype.service` and `voxtype-commands.service` after idle checks; restore only units previously active | No stop while recording/transcribing; no enable/disable, config edits, unrelated service control or automatic retry; warn Home/End will be temporarily unavailable |
| P4 — pending decision | Select a local TTS provider; approve bounded playback on an explicit sink at unchanged volume, at most six prompts | No inferred package/model installation authority, network, host transport, media duck/pause or device-default changes |
| P5 — pending | One new, attended live speech-to-menu opening after replay/mic tests; explicit session ID and one-action budget | Prior menu approval is consumed; no general desktop commands or retry on uncertainty |
| P6 — pending | Back up and edit only the HOME, END and KP_EQUAL entries in `/home/robbo/.config/hypr/bindings.lua`; install new project-owned wrappers; reload/validate Hyprland | Preserve Home-start/End-stop semantics and default Voxtype config; no global Escape binding or unrelated key changes |
| P7 — optional, pending | Install one project-owned user unit and config under paths below; daemon-reload; bounded start/stop and, separately if requested, enable it | No root services, edits to existing Voxtype units, package changes, firewall, host or VM changes |
| P8 — pending | Human acceptance of physical keyboard, actual panel, fresh-voice confirmation and recovery; explicitly approve a scratch target for Home/End typing and possible clipboard fallback | No automatic expansion of the one-menu budget; other cases use fake execution unless separately authorized; no typing into existing user documents |

P3 is a proposed maximum budget, not permission to collect ambient audio or other
people's speech. The user chooses the source and start time and can end the trial
early. Device IDs and service states must be inspected again at execution time.
Stopping a process/service is a live action even if its configuration is unchanged.

Future P7 paths: `/home/robbo/.config/systemd/user/arhugula-voice.service`,
`/home/robbo/.config/arhugula/voice.json`, a versioned application artifact under
`/home/robbo/.local/share/arhugula/`, and new wrappers under
`/home/robbo/.local/bin/arhugula-voice*`. Validate exact target names before approval;
never use a wildcard as an install/delete target. These paths are not written now.
The existing command service can remain installed and inactive during trials;
disabling it at login is an additional explicit cutover choice, not implicit P7.

## Privacy, observations and retention

Live PCM and transcript are transient. Prefer bounded memory or anonymous runtime
files; if the backend requires a named WAV, use a private 0700 session directory,
0600 regular files, no symlink following and an explicit cleanup manifest. Retaining
recordings for replay needs separate per-fixture consent, provenance and duration.
Do not commit real user speech, transcripts, local configs or model files. Publish
only sanitized counts, hashes for consented fixture identification, timings and
safe error codes. Hashes are not anonymization of sensitive content.

Journal capture/transcription/cancellation observations with correlated IDs in a
new versioned non-execution record; do not label capture as `command.started` or
reuse `voice.preview` for generic telemetry. Existing command receipts retain their
meaning. Raw subprocess stderr and transcript must not enter LIT, Git or notices.

Cleanup authority must be included in live-session approval for exactly the
manifested temporary audio files created by that session. It never authorizes
deleting source recordings, old journals, backups, models or another session's
data. If cleanup is not authorized, do not create retained audio files. Zero-copy
or securely erased audio is not promised by Python buffers/filesystem deletion.

## Acceptance and rollback

All existing tests remain mandatory. Add deterministic fault/cancellation,
malformed frame, noisy/quiet replay, process-tree teardown, stale-context and
concurrency tests. Recorded corpus: three exact-menu utterances, two unknown
phrases, two negations, two clarification/confirmation pairs, silence and noise;
user supplies/approves recordings. Every non-affirmative/unknown/noise case must
cause zero real action and zero clipboard/typing calls. Exact-menu cases must
route correctly with fake execution before P5. Report per-case results rather
than claiming general ASR accuracy from this small corpus.

Target budgets for review: capture <=15 seconds, transcription deadline 30 seconds,
cancel returns control within one second and child cleanup within two seconds.
If hardware cannot meet a budget, report the evidence and obtain a revised bound;
do not remove timeouts. Kill/reap only owned children; never use process-name-wide
kill commands. Failed cleanup latches unavailable and prevents another activation.

Before any approved cutover: preserve exact originals, hashes, unit active/enabled
states and binding destinations. Treat drift as a stop. Disable command admission
first on rollback, stop/reap project-owned children, restore only the owned binding
diff if its post-install hash matches, then run `hyprctl reload` followed by
`hyprctl configerrors`. Restore previously active legacy services only after proving
no command worker remains. Conflicting edits, failed cleanup or config errors
require a human decision; do not overwrite unrelated changes. Keep recovery files.

The voice arc, z5x and circle-back o19 cannot close until actual recorded/live
acceptance, spoken clarification, confirmation surfaces, no-leak arbitration and
rollback are demonstrated. Shipping repository adapters is a smaller milestone.

## Decisions requested

First review this proposal and its [staged plan](../plans/2026-09-20-live-voice-integration-plan.md).
Recommended next authorization is P1 only. P2 needs approved fixture paths;
P3 needs source, attendance and ownership arrangement; P4 needs a provider;
P5-P8 need their specific later approvals. No ordinary “continue” should be
interpreted as permission for all these live effects.
