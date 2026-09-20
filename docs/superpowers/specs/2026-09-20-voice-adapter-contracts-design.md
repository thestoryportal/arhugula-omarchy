# Repository-only voice adapter contracts

This refines approved B.1/B.2, not the live Voxtype deployment. User delegated
routine implementation decisions and requested autonomous continuation. Existing
Home/End, local VM Whisper, focused typing, clipboard fallback and independent
KP_EQUAL capture remain the product requirements. No keybinding or service edits.

Choose a small injected state machine over launching Voxtype commands or copying
its configuration: it makes the safety boundary testable without coupling to a
live service. Captured PCM and transcription remain transient; diagnostic notices
contain interaction ID, phase, status and safe code, never text or audio. These
notices are adapter observations, not execution authority or replacements for the
runtime journal. A future live binding must persist correlated runtime events and
route output through VM-authorized executors before enabling real side effects.

Dictation binds a versioned Provider record: VM placement, enabled, available,
and transcription capability. The injected transcriber represents local Whisper;
no provider download or inference process is launched. `home()` saves a trusted
focus token and starts capture once; `end()` stops capture, transcribes, rechecks
focus, and requests text delivery with the original token. The output adapter
must also validate that token at actuation, closing the last focus race.

Typing returns delivered/not-delivered/uncertain. Clipboard copy (no automatic
paste) is allowed only after definite non-delivery and a fresh focus check.
Exceptions or uncertain delivery never trigger fallback. Focus changes discard
the output attempt. Provider/capture/transcription errors produce explicit safe
failures. Cancel discards capture and never transcribes or outputs. Failed capture
cleanup latches a fault; a new binding is required after external reconciliation.

KP_EQUAL is a separate one-shot state machine with injected PCM frames and trusted
speech-activity observations, maximum duration, silence termination, explicit
processing/cancel states, and no typing/clipboard dependency at all. Recorded
replay is a fixture, not microphone access. Live capture, VAD calibration, semantic
routing, trusted confirmation and one approved live action smoke remain later
work. The live smoke is outside current repository-only authority.
