# Command Capture Implementation Plan

> Use superpowers:subagent-driven-development for this one Terra/medium task,
> then final Astra/high review of the combined voice-contract branch.

Goal: deterministic one-shot KP_EQUAL capture without live audio or output.
Spec: docs/superpowers/specs/2026-09-20-voice-adapter-contracts-design.md and
the approved workspace design's Command mode section.
Stack: Python >=3.11 standard library.

## Global Constraints

Repository only. No services, keybindings, microphone, clipboard, focused-app
typing, network or model downloads. Command speech never enters dictation output.
No changes to runtime contracts/core/journal or the existing dictation module.

## Review Focus

Frames exceeding the duration bound must not overfill the PCM buffer.
Silence-only capture must not send an empty command for processing.
Duplicate hotkeys and stale completion callbacks must not restart/reuse audio.
Invalid frames or observer failures must discard, not leak captured speech.
Cancellation in processing must invalidate the old completion token.

### Task 1: f5v bounded adaptive capture

LIT arhugula-voice-core-b4k.ceb.f5v is claimed by the coordinator. You exclusively
own runtime/voice/capture.py, tests/test_command_capture.py,
tests/fixtures/command-capture.json, docs/voice/capture.md. No other tracked files.
Do not change LIT or push; coordinator records evidence/closes after review.

Interfaces: `Frame(pcm: bytes, speech: bool)` is 16kHz mono signed 16-bit PCM.
Reject empty, odd-length, non-bytes PCM and nonboolean speech. Duration derives
from samples, never untrusted declared duration. PCM must contain a whole number
of milliseconds (32 bytes/ms). Trusted VAD supplies speech observations; this
task does not install a VAD. `CaptureConfig` defaults max_ms=15000,
initial_silence_ms=3000, short_silence_ms=700, long_silence_ms=400,
long_utterance_ms=2000. Positive integer bounds (bool forbidden); silence bounds
and long_utterance_ms cannot exceed max_ms. Threshold switches from short to
long after the configured accumulated speech duration.

`CommandCapture(config=..., observe=...)` provides `key_equal()`, `feed(Frame)`,
`cancel()`, `complete(token)`; read-only state idle/recording/processing and
bounded buffered-byte count. `key_equal()` starts once and returns a fresh
session token; repeat while recording/processing is blocked. `feed` accepts only
recording, emits an immutable capture result when stopping, otherwise reports
recording. Terminal result includes status, safe reason, token, immutable audio.
Only a speech-containing finish has status processing and audio bytes. Initial
silence ends idle with no audio. Silence/max stops are deterministic; trim a
frame at the remaining max duration so buffers never exceed max_ms*32 bytes.
No microphone timing or sleeps. The last frame's speech flag applies to its
included samples. Cancel clears buffers, returns canceled, and invalidates any
processing token. `complete(token)` clears processing only for the matching
token; a stale token never changes a newer session. Reentrant observer callbacks
must not mutate in-flight state. Notices exclude raw audio; observer failure
discards the session and returns an explicit failed result.

No typing/clipboard dependency exists. Returned command PCM is for the command
router only. Keep this separate from Dictation; no shared mutable capture or
automatic mode switching. The live coordinator will arbitrate physical devices.

- [ ] Write behavior tests first, including synthetic PCM and a deterministic
  recorded-event JSON fixture replayed twice with the same completion reason
  and byte count. Fixture frames specify duration_ms and speech; test generates
  PCM bytes at the fixed format. Clearly label fixture as synthetic replay,
  not real microphone audio or VAD accuracy evidence.

```python
capture = CommandCapture()
token = capture.key_equal().token
capture.feed(Frame(b'\x00' * 16000, True))
result = capture.feed(Frame(b'\x00' * 22400, False))
assert result.status == 'processing'
assert result.token == token
assert len(result.audio) == 38400
```

- [ ] Run `python3 -m unittest discover -s tests -p test_command_capture.py -q`;
  record missing module RED before implementation.
- [ ] Implement bounded accumulation and adaptive silence:

```python
remaining = config.max_ms * 32 - len(buffer)
included = frame.pcm[:remaining]
buffer.extend(included)
elapsed_ms += len(included) // 32
```

  Use explicit state/token transitions for silence/max/cancel/stale completion;
  cover all five review-focus conditions with focused behavior assertions.
- [ ] Run focused tests, then full suite once:
  `python3 -W error::ResourceWarning -m unittest discover -s tests -q`.
- [ ] Run `git diff --check`, self-review and commit only your four owned files.
  Write RED/GREEN/commands/output/commit/concerns in the assigned report file.
