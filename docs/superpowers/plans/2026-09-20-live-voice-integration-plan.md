# Live Voice Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> for the lead implementer, or superpowers:subagent-driven-development when
> independent task delegation is explicitly selected. Steps use checkboxes.
> P1 repository steps are now approved in the isolated worktree. P2-P8 remain
> gated; foreign main diagnostics stay untouched and merge/push are deferred.

**Goal:** Connect the verified voice substrate to one safe local command without
disturbing working dictation or leaking command speech into applications.

**Architecture:** A VM-owned foreground coordinator serializes activation,
capture, transcription and trusted confirmation. Adapters remain injectable;
the existing control plane owns authorization and execution receipts. Install
bindings and a user service only after separate permission and acceptance gates.

**Tech Stack:** Python 3.11+ standard library, existing typed contracts/SQLite,
PipeWire CLI adapter, candidate installed Voxtype 1.0.1 file transcriber; candidate
Tkinter panel. Provider behavior and GUI availability require characterization.
No dependency or model downloads are implied.

**Spec:** [Live integration proposal](../specs/2026-09-20-live-voice-integration-proposal.md),
refining [approved workspace design](../specs/2026-09-19-omarchy-agent-workspace-design.md).
Read both. Subsequent user approval covers P1 only, not live deployment.

## Global Constraints

- Command capture has no typing, paste or clipboard dependency.
- Live PCM and transcript are transient.
- The earlier approval for one menu opening was consumed; it is not permission for another test.
- Runtime networking is deny-by-default with narrow approved update access.
- Python 3.11+, existing dependencies only; no package, host, VM, firewall or `/usr/share/omarchy/` changes.
- P0/P1 are currently authorized. The proposal defines P2-P8 and exact exclusions.
- No implementation starts until proposal/plan review and P1 approval. Live gates remain separate.
- Each claimed atomic ticket has one writer, fresh verification, LIT evidence, commit, close and handoff.
- Astra/high: ownership, contracts, policy, integration and final risk review. Terra/medium: bounded fixtures, inventory and independent validation.
- Parent `.ceb`, integration `.z5x` and circle-back `.csj.o19` stay open until their actual acceptance gates pass.

## Review Focus

1. Home pressed during command capture: cancellation and child teardown finish before default dictation starts (Tasks 1, 4, 7).
2. Late transcription after cancel/restart: generation mismatch prevents speech, preview and execution (Tasks 3, 4).
3. Legacy config or hooks accidentally inherited by file transcription: no typing/clipboard/daemon/hook or network effects (Task 3).
4. Missing/stale compositor, mute or device state: fail closed even after waiting for journal ownership; do not equate polling with atomic actuation (Tasks 4, 6).
5. Partial installation, duplicate trigger or failed child cleanup: no second owner, no automatic action retry, recover only owned changes (Tasks 1, 5, 7).

## Current evidence and execution order

The baseline has 137 tests, reviewed routing/confirmation and a successful typed
menu smoke, not live speech acceptance. A separate legacy command daemon, trigger
and direct menu hook already exist on the machine; see the proposal's inventory.
The default Voxtype dictation config and both legacy scripts remain unchanged.
`tkinter` module discovery succeeded; no window was created and Tk usability was
not tested. TTS selection remains a permission/implementation decision.

This is one live-command subproject, not a replacement for all voice/TTS/agent
epics. Task 6 deliberately gates concrete speech output on provider selection.
Native sequential implementation with a final Astra/high independent review is
recommended because capture ownership and cancellation share state. Terra may
own isolated replay fixtures/review; never give two agents overlapping files.

After P1 approval, create/rank atomic children under `.z5x` using LIT. Keep the
parent HIL marker until its release gate is resolved; do not remove an inherited
stop merely to run the autonomous loop. Explicitly authorized repository tasks
can be claimed manually with their scoped approval recorded in LIT, as was hq3.

## Planned file map

These files do not exist yet unless identified as existing; this plan creates
no runtime code. Public signatures below are proposed contracts for review.

| Path | Responsibility |
| --- | --- |
| `runtime/voice/session.py` | Generation/ownership transitions and bounded admission |
| `runtime/voice/pcm.py` | Frame assembly and candidate streaming VAD |
| `runtime/voice/process.py` | Bounded subprocess lifetime, cancellation and output limits |
| `runtime/voice/device.py` | Explicit PipeWire source, streaming frame queue and owned capture teardown |
| `runtime/voice/transcription.py` | Isolated local file-transcription adapter |
| `runtime/voice/coordinator.py` | Capture/router composition and stale-work rejection |
| `runtime/voice/control.py` | Closed local control protocol and peer/size validation |
| `runtime/voice/speech.py` | Finite prompt policy and interruptible playback seam |
| `ui/voice_panel.py` | Minimal trusted status/confirmation panel |
| `ops/voice_session.py` | Dry-run-first foreground entrypoint, never implicit deployment |
| `ops/voice_replay.py` | Consented corpus replay and sanitized report |
| `ops/voice_install_plan.py` | Read-only proposed diff, exact targets and rollback manifest |
| `ops/templates/arhugula-voice.service` | Inert user-unit template, not installed |
| `ops/templates/voice-bindings.lua` | Inert scoped binding template |
| `schemas/voice-session-v1.json` | Closed control-message schema, not model tools |
| Existing `runtime/contracts.py`, `runtime/journal.py`, `schemas/contracts-v1.json` | Versioned non-execution voice observations |
| `tests/test_voice_session.py`, `test_voice_pcm.py`, `test_voice_process.py`, `test_voice_device.py`, `test_voice_transcription.py`, `test_voice_coordinator.py`, `test_voice_control.py`, `test_voice_speech.py`, `test_voice_panel.py`, `test_voice_install_plan.py` | Named test targets for the corresponding modules |
| `tests/fixtures/voice-replay/manifest.json` | Synthetic/publicly authorized fixture metadata only; no private speech |
| `docs/voice/live-integration.md` | Evidence, operations, supported boundary and recovery instructions |

## Task 1 — Exclusive session ownership and admission (Astra/high, P1)

**Files:** Create `runtime/voice/session.py`, `tests/test_voice_session.py`.
**Interfaces:** `SessionOwner()` exposes `begin(mode: str) -> int`,
`cancel() -> int`, `accepts(generation: int) -> bool`,
`release(generation: int, cleaned: bool) -> None`. Modes are only `command` and
`dictation`; concurrent begin raises `BusyError`; failed cleanup latches faulted.
Generation is never reused in one owner; restart adds a fresh session UUID.

- [ ] Add this failing contract test and tests for repeated begin, invalid mode,
  fault latch, cancel-before-start and Home waiting for cleanup:

```python
import unittest
from runtime.voice.session import SessionOwner, BusyError

class OwnerTests(unittest.TestCase):
    def test_cancellation_does_not_release_physical_owner(self):
        owner = SessionOwner()
        generation = owner.begin("command")
        owner.cancel()
        self.assertFalse(owner.accepts(generation))
        with self.assertRaises(BusyError):
            owner.begin("dictation")
        owner.release(generation, cleaned=True)
        self.assertGreater(owner.begin("dictation"), generation)
```

- [ ] Run `python3 -m unittest discover -s tests -p test_voice_session.py -v`;
  expect missing module before implementation, then assertions while refining.
- [ ] Implement locked transitions: idle -> owned -> canceling -> idle/faulted.
  Cancellation increments logical generation but retains physical cleanup token.
  Never hold this lock across a blocking capture/provider call.
- [ ] Rerun focused tests and full suite. Commit only `session.py` and its tests;
  record observed RED/GREEN, ownership ruling and next task in LIT/handoff.

## Task 2 — Bounded PCM and replayable VAD candidate (Terra/medium, P1)

**Files:** Create `runtime/voice/pcm.py`, `tests/test_voice_pcm.py`, synthetic
`tests/fixtures/voice-replay/manifest.json`.
**Interfaces:** `PcmFramer.feed(chunk: bytes) -> list[bytes]`,
`PcmFramer.finish() -> None` (reject incomplete final frame),
`EnergyVad(threshold_rms: float).is_speech(pcm: bytes) -> bool`.
640-byte frames; bound each input chunk to 64 KiB and buffered remainder to 639
bytes. Threshold is finite and strictly between zero and one. Frame PCM is s16le;
normalize RMS by 32768. Device/stdout chunk boundaries are not audio-frame boundaries.

- [ ] Add fragmented-chunk, invalid bytes/size, incomplete-frame, max-buffer and
  RMS tests, including:

```python
import unittest
from runtime.voice.pcm import PcmFramer, EnergyVad

class PcmTests(unittest.TestCase):
    def test_pipe_fragmentation_and_silence(self):
        framer = PcmFramer()
        self.assertEqual(framer.feed(bytes(639)), [])
        self.assertEqual(framer.feed(bytes(1)), [bytes(640)])
        framer.finish()
        self.assertFalse(EnergyVad(0.02).is_speech(bytes(640)))
```

- [ ] Run `python3 -m unittest discover -s tests -p test_voice_pcm.py -v` RED.
- [ ] Implement framing, bounded parsing and RMS classifier; feed existing
  `Frame(pcm, speech)` into `CommandCapture`, without changing its timeout defaults.
  The test threshold 0.02 is illustrative, not calibrated production policy.
- [ ] Test exact 15-second bound, clipping/noise, no-speech finish and recording
  cancellation using generated PCM. Real quiet/noise accuracy belongs to P2.
- [ ] Run focused/full suites; commit files, label synthetic evidence accurately.

## Task 3 — Cancellable process adapter and local transcription (Astra/high)

**Files:** Create `process.py`, `device.py`, `transcription.py`, their named tests, and
`ops/voice_replay.py`; produce dedicated repository-only transcriber config after
characterization. Do not copy either live Voxtype config.
**Interfaces:** `OwnedProcess(argv: tuple[str, ...], *, max_output: int,
timeout_s: float)` exposes `start(input_bytes: bytes | None)`,
`poll() -> ProcessResult | None`, `cancel() -> ProcessResult`.
`ProcessResult` is frozen with `status`, `stdout: bytes`, `code: str`; raw stderr
is not public. `TranscriptionJob.start(pcm: bytes, generation: int)` and
`poll() -> TranscriptResult | None`, `cancel() -> None`; frozen `TranscriptResult`
has `generation: int`, `status: str`, `text: str | None`, `code: str`.
Text is private transient data, never an observation or diagnostic payload.
`PipeWireCapture.start(source: str)`, `poll() -> list[bytes]` and `cancel() -> bool`
own a separate streaming process: `poll` returns bounded chunks for `PcmFramer`;
`cancel` returns true only after confirmed child teardown. Source comes from the
trusted operator selection, not transcript/model data.

- [ ] Under P1, write subprocess-fake tests first. Pin `shell=False`, fixed trusted
  executable, bounded stdout/stderr (64 KiB each), 30-second monotonic timeout,
  SIGTERM then bounded SIGKILL/reap of owned process group only, and no orphan after
  cancellation. Use a controlled Python child for tests, never Voxtype.

```python
import sys, unittest
from runtime.voice.process import OwnedProcess

class ProcessTests(unittest.TestCase):
    def test_cancel_owns_and_reaps_child(self):
        worker = OwnedProcess(
            (sys.executable, "-c", "import time; time.sleep(60)"),
            max_output=65536, timeout_s=30)
        worker.start(None)
        self.assertEqual(worker.cancel().status, "canceled")
        self.assertEqual(worker.poll().status, "canceled")
```

- [ ] Run `python3 -m unittest discover -s tests -p test_voice_process.py -v`
  and the equivalent transcription target RED; implement the process seam and
  generation-preserving fake transcriber. Strictly reject invalid WAV/sample
  geometry, empty/oversize transcript, invalid UTF-8, nonzero exit and late output.
- [ ] Add `test_voice_device.py` RED with a fake Popen and fragmented pipe reads;
  implement the streaming adapter using the locally documented fixed argv shape:

```python
argv = ["/usr/bin/pw-record", "--rate", "16000", "--channels", "1",
        "--format", "s16", "--raw", "--target", approved_source,
        "--sample-count", "240000", "-"]
```

  The live argv is NOT executed under P1. Bound total PCM to 480,000 bytes,
  queue to 16 frames (320 ms), stderr to 64 KiB and wall time to 15 seconds.
  Queue overflow, malformed output, source loss or silent stall cancels capture;
  do not silently drop frames or switch to another source. Unlike transcription,
  consume PCM incrementally, not through an accumulating `communicate()` call.
  Test teardown when silence ends capture before the process sample limit.
- [ ] Run focused/full suites and commit the P1 deliverable; no real inference.
- [ ] STOP for P2 before characterizing `/usr/bin/voxtype transcribe FILE`.
  Inspect installed behavior/source or a genuinely isolated, no-network/no-desktop
  fixture environment. Test a dedicated local-only config with hooks/output drivers
  disabled, explicit existing model path and approved WAV. `--help` is insufficient
  proof that a config knob disables all output. If isolation/config semantics cannot
  be established, block the backend; do not run on the live desktop to find out.
- [ ] Commit only the proven dedicated config, fixture provenance/hash metadata
  and sanitized characterization evidence; pin executable/model identity for live
  preflight. Any provider update invalidates that proof. Missing model stops;
  setup/download commands are not a fallback.

## Task 4 — Coordinator, observations and no-leak replay (Astra/high, P1/P2)

**Files:** Create `coordinator.py`, `tests/test_voice_coordinator.py`; extend
`runtime/contracts.py`, `runtime/journal.py`, `schemas/contracts-v1.json` and
their existing contract/journal tests. Add replay driver behavior to `ops/voice_replay.py`.
**Interfaces:** `Coordinator(owner, capture, router, transcriber, observe)` exposes
`activate() -> int`, `feed(generation: int, frame: Frame) -> None`,
`transcribed(result: TranscriptResult) -> VoiceReply | None`, `cancel() -> None`.
Consumes the earlier contracts plus existing `CommandCapture` and `VoiceRouter`.
Router state supplier is bound to current owner generation and full VM context.

- [ ] Define independently versioned `VoiceObservation` (`kind=voice-observation`,
  `version=1`) with event_id, session_id, activation_id, correlation_id,
  timestamp_ms, context, phase, status, code; no transcript/audio/token fields.
  Closed phases: capture.started/stopped/canceled, transcription.started/finished,
  owner.faulted. Add round-trip/unknown-field/version/reopen/replay tests first.
- [ ] Add coordinator regressions using `unittest.mock.Mock` for collaborators:

```python
from unittest.mock import Mock
from runtime.voice.session import SessionOwner
from runtime.voice.capture import CommandCapture
from runtime.voice.coordinator import Coordinator
from runtime.voice.transcription import TranscriptResult

router = Mock()
coordinator = Coordinator(SessionOwner(), CommandCapture(), router, Mock(), Mock())
generation = coordinator.activate()
coordinator.cancel()
late = TranscriptResult(generation, "success", "open omarchy menu", "ok")
assert coordinator.transcribed(late) is None
router.handle.assert_not_called()
```

- [ ] Also test duplicate frames/results, journal failures at every transition,
  context away-and-back, mute during persistence, generation restart, Home during
  processing and failed cleanup. No injected command collaborator may expose
  typing or clipboard methods. Capture and inference events must not create
  execution receipts or restrictive preview records accidentally.
- [ ] Run `python3 -m unittest discover -s tests -p test_voice_coordinator.py -v`
  RED; implement a single owner/event loop with bounded work queues (one active
  job, reject concurrent activation rather than retaining audio backlog).
- [ ] Wire existing router `handle`, `confirm` and VM journal; use fake executor
  for every P1/P2 run. Keep correlation from activation through inference and
  execution: extend the existing router constructor with keyword-only
  `correlation_ids: Callable[[], str] | None = None`, defaulting to its current
  UUID behavior, and pin it to the coordinator's current activation correlation.
  Add backward-compatibility tests; do not rewrite existing receipts. Wire
  device.poll -> PcmFramer -> EnergyVad -> Frame -> coordinator.feed in the
  foreground event loop; cancellation closes both capture and transcription.
- [ ] Run synthetic replay, then P2 consented replay after Task 3 backend proof.
  Record per-case transcript/routing correctness privately and publish only
  safe metrics; zero execution for negative/unknown/noise cases. Commit with
  explicit “synthetic only” or “recorded replay passed” evidence, never both by assumption.

## Task 5 — Trusted local controls and foreground status (Astra/high, P1)

**Files:** Create `runtime/voice/control.py`, `schemas/voice-session-v1.json`,
`ops/voice_session.py`, `tests/test_voice_control.py`.
**Interfaces:** `decode_control(payload: bytes) -> dict` rejects unknown fields,
oversize (>4096 bytes), duplicate keys and invalid versions/types. Socket server
is explicit opt-in and exposes no network address. Status omits transcripts and
confirmation tokens; approved panel client receives pending token privately.

- [ ] Add failing parser/peer/socket-ownership tests including:

```python
import unittest
from runtime.voice.control import decode_control

class ControlTests(unittest.TestCase):
    def test_rejects_generated_shell_and_duplicate_keys(self):
        for data in (b'{"version":1,"op":"shell","command":"true"}',
                     b'{"version":1,"op":"cancel","op":"activate"}'):
            with self.assertRaises(ValueError):
                decode_control(data)
```

- [ ] Specify/implement closed operations activate, cancel, status, mute,
  dictation-start, dictation-stop, confirm. Require request ID and current session
  identity for mutating messages; confirm also carries a trusted token/channel and
  boolean decision. Reject replayed request IDs and expired session context.
- [ ] Use 0700 owner directory, 0600 socket, peer UID check, short per-request
  deadline and one bounded frame. Test symlinks, stale socket, second owner,
  wrong UID, hung client and exhausted activation history. Do not auto-unlink an
  unverified socket or auto-restart on ownership uncertainty.
- [ ] Implement dry-run CLI default and explicit live-permission preflight. A flag
  or JSON “approved” field supplied by a model is not authorization. Bind any
  external approval record only through the trusted operator startup path.
- [ ] Run `python3 -m unittest discover -s tests -p test_voice_control.py -v`
  and full suite; commit. Document that same-UID malicious code is not isolated
  by Unix filesystem permissions; no model tools get the control endpoint.

## Task 6 — Panel and interruptible clarification (Astra/high then Terra review)

**Files:** Create `runtime/voice/speech.py`, `ui/voice_panel.py`, corresponding tests.
**Interfaces:** `SpeechQueue(backend, state).say(prompt: str, activation_id: str)`
and `cancel() -> None`; state returns the existing `VoiceState`.
`SpeechBackend.start(prompt: str) -> None` and `cancel() -> ProcessResult` follow
owned-process cancellation; future concrete backend uses a fixed approved argv.
Compare complete VoiceState snapshots, not only activation IDs. Fixed reviewed
prompt catalog only, no arbitrary model text. Panel displays phase, degraded
state, capability label, preview/expiry and confirm/cancel; callbacks invoke
trusted `VoiceRouter.confirm(token, "panel", bool)` through local controls.

- [ ] P1: write fake-backend tests that stale/muted prompts do not start, activation
  interrupts playback before capture, canceled synthesis cannot later play, and
  prompt text never appears in diagnostic errors. Test panel token binding,
  expiry, reconnection and double-click without creating a desktop window.

```python
from unittest.mock import Mock
from runtime.voice.router import VoiceState
from runtime.voice.speech import SpeechQueue

state = lambda: VoiceState({}, "epoch-1", "turn-1", muted=True)
backend = Mock()
queue = SpeechQueue(backend, state)
queue.say("Please repeat the command.", "turn-1")
backend.start.assert_not_called()
```

- [ ] Implement injected speech queue and Tkinter view model first. The minimal
  panel uses buttons, explicit countdown and keyboard shortcuts only while that
  panel is focused; no global Escape interception. Tkinter module is present,
  but do not claim the display works until authorized window acceptance.
- [ ] Run `python3 -m unittest discover -s tests -p test_voice_speech.py -v`,
  panel target and full suite; commit repository-only behavior.
- [ ] STOP before concrete TTS selection/real playback: obtain P4 provider decision.
  Installed `piper`/`espeak-ng` were not found; no package/model fetch is authorized.
  Select an already available approved provider or request a distinct installation
  decision. Bind only local VM output with an explicit sink and unchanged volume.
- [ ] P4/P8: human checks intelligibility, interruption and actual panel/keyboard
  confirmation. Text-only status or fake panel callbacks cannot satisfy those gates.

## Task 7 — Read-only install plan, isolated trial and opt-in cutover (Astra/high)

**Files:** Create `ops/voice_install_plan.py`, inert templates, its named test,
`docs/voice/live-integration.md`; modify voice handoff/progress with actual evidence.
**Interfaces:** `plan_install(current_hashes: dict[str, str],
approved_hashes: dict[str, str], target_version: str)
-> dict` returns exact add/modify operations and rollback preconditions; it performs
no filesystem/config/service mutation. Require the complete named baseline file
set from the proposal inventory and equality with the reviewed approval snapshot;
reject missing keys or drift. New files use absent-path preconditions.

- [ ] P1: write temporary-fixture tests proving plan generation never writes,
  unexpected drift rejects, Home/End semantics are unchanged, each old key is
  explicitly unbound before replacement, and no packaged/legacy files are overwritten.
  Test two successive install plans cannot silently stack trigger handlers.

```python
from pathlib import Path
from unittest.mock import patch
from ops.voice_install_plan import plan_install

with patch.object(Path, "write_text", side_effect=AssertionError("unexpected write")):
    try:
        plan_install({}, {}, "test-version")
    except ValueError:
        pass  # Missing baseline must reject before proposing mutations.
    else:
        raise AssertionError("incomplete baseline accepted")
```
- [ ] Implement inert diffs/templates with fixed new wrapper destinations; no
  installer runs during bootstrap/tests. Preserve existing Voxtype config and
  service definitions. Unit must have no automatic replay/restart of an action.
- [ ] Run `python3 -m unittest discover -s tests -p test_voice_install_plan.py -v`
  and full suite. Commit templates, plan and rollback instructions only.
- [ ] Before P3, recheck exact service active/enabled/recording states and conflicts;
  request ownership subgate if quiescence requires stopping existing daemons.
  Never stop recording/transcription or user work. Warn of temporary dictation
  unavailability; record exact restoration state. If safe ownership cannot be
  achieved with granted permissions, do not open the microphone.
- [ ] P3: attended foreground trial, bounded microphone source, fake executor,
  no typing/clipboard/playback. Report every activation, timing, cancellation,
  noise case and child cleanup. Do not consume P5 to debug capture.
- [ ] P5: after all applicable offline and ownership gates pass, new explicit
  one-action budget, one approved utterance, fresh voice activation, VM policy,
  journal intent, executor acknowledgement and independent menu visibility.
  Record actual result; uncertainty consumes the attempt and prohibits retry.
- [ ] P6: show exact binding diff and prior destinations; obtain approval then
  change only named entries and install exact new wrappers. HOME first cancels
  command capture and awaits cleanup, then forwards existing dictation start;
  END forwards existing stop for the dictation owner, not command transcription.
  Validate with `hyprctl reload` and `hyprctl configerrors`. Failed validation
  stops cutover and uses the preapproved scoped restore, not a full config reset.
- [ ] P7 separately: install/start project user unit only with exact paths and
  permissions approved; enable-at-login is another explicit choice. Never
  leave old and new KP_EQUAL handlers active. Old command service disablement
  needs explicit approval; retain old files for recovery.
- [ ] P8: verify real Home/End output only with an explicitly approved scratch
  target and typing/clipboard permission. Otherwise record preservation by diff
  only and leave live dictation acceptance incomplete. Exercise actual panel,
  keyboard and fresh-voice confirmation; extra menu effects need new budgets.
- [ ] Reconcile recorded/live evidence, limitations and rollback with o19. Close
  z5x/parent/release only when all required gates pass; commit handoff at each
  completed atomic unit and push only a clean, uncontended verified main.

## Verification commands and report

During approved repository implementation, every focused test target above uses
standard-library unittest. Tests must never discover/run live trials by default.
After each focused unit run:

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -q
git diff --check
lit doctor
```

Record ticket, commit, model/effort, exact verification command/exit status/count,
synthetic versus recorded versus live mode, review findings, permission gate,
remaining budget, changed files, unresolved risks, next ticket and stop reason.
Keep raw audio/transcript out of this public report. Existing-remote Git/LIT sync
does not authorize transmitting private recordings or local config snapshots.

## Planning handoff

P0 completion means these documents are checked and committed, not that any
proposed API exists. Review the proposal and plan, then authorize P1 if the
approach is acceptable. P2-P8 remain blocked by their individual decisions.
No runtime changes, new model process, microphone session, GUI, playback, service
change, binding edit or additional menu launch is part of preparing this plan.
