# Dictation Contract Implementation Plan

> Execute inline with superpowers:executing-plans, then one read-only Astra/high
> review of the voice branch. Routine choices are delegated by the user.

Goal: prove Home/End semantics and safe output fallback without touching live IO.
Architecture: injected capture/transcription/focus/output adapters; immutable
results and observation notices. Existing Provider codecs validate placement.
Tech stack: Python >=3.11 standard library and unittest.
Spec: docs/superpowers/specs/2026-09-20-voice-adapter-contracts-design.md and the
approved workspace design's Dictation section.

## Global constraints

Repository only. No services, keybindings, microphone, clipboard, focused-app
typing, network or model downloads. Test doubles are the only action adapters.
Capture cleanup must succeed before a failed session can return to idle.

## Review focus

Focus changes during transcription/fallback must not redirect output.
Uncertain typing must never duplicate via clipboard fallback.
Repeated Home/End must not restart capture or retype an old transcript.
Host/unavailable providers must be refused before capture.
Capture-stop/cancel failure must not leave a silently reusable live capture.

## Task 1: v1t dictation contracts and deterministic adapter

Files: runtime/voice/__init__.py, runtime/voice/dictation.py,
tests/test_dictation.py, docs/voice/contracts.md, docs/voice/handoff.json.
Interfaces: immutable FocusToken(window_id, generation), Delivery(status),
DictationResult(status, code, delivery), Notice(interaction_id, phase, status,
code); Dictation(capture, transcribe, output, focus, provider, observe).
Capture: start(), stop()->bytes, cancel(); transcribe(bytes)->str; focus()->token;
output.type_text(text, token)->Delivery; output.copy_text(text)->Delivery.
Methods home()/end()/cancel() return DictationResult; state is idle/recording/
processing/faulted. Observation failure blocks before side effects, or reports
uncertain after an output attempt. No transcript in a result or notice.

- [ ] Write tests including this core assertion and the five review cases:

```python
session.home()
result = session.end()
assert result.status == "success"
assert output.typed == [("hello", FocusToken("editor", 1))]
assert output.copied == []
```

- [ ] Run `python3 -m unittest discover -s tests -p test_dictation.py -q`;
  expect missing runtime.voice module before implementation.
- [ ] Implement strict provider validation, state transitions and this output
  ordering (all exceptions are classified; no raw exception strings emitted):

```python
if focus() != original_focus:
    return DictationResult("blocked", "focus.changed", None)
delivery = output.type_text(text, original_focus)
if delivery.status == "not-delivered" and focus() == original_focus:
    delivery = output.copy_text(text)
```

- [ ] Run full `python3 -W error::ResourceWarning -m unittest discover -s tests -q`
  and `git diff --check`; commit only named files, record evidence and close v1t.
- [ ] Write durable handoff pointing at f5v; continue in LIT order. Implement
  f5v from its own bounded brief with Terra/medium ownership, no shared writers.
