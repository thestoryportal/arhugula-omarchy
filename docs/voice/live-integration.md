# P1 repository integration substrate

Scope: P1 only. No microphone, Voxtype inference, TTS, live bindings, service
changes or new menu actions have been performed. Main has foreign diagnostic
work; user permits isolated implementation but defers integration and push.

## Ownership and framing

`SessionOwner` is process-local admission. Pair every integer generation with its
session UUID across restart boundaries. Cancellation invalidates logical work;
only cleanup with the original owning generation releases admission. Failed
cleanup latches faulted. A new instance is safe only after external reconciliation;
it is not a way to bypass ownership of a live device.

`PcmFramer` converts bounded immutable chunks to 640-byte s16le frames and rejects
partial EOF or malformed input without resynchronization. `EnergyVad` computes
RMS amplitude against an explicit threshold. It is uncalibrated and cannot tell
speech from sufficiently loud noise. No real speech accuracy is established.

## Process and capture seams

`OwnedProcess` accepts fixed trusted absolute argv, never a shell. It bounds stdin
to 480,044 bytes, ordinary stdout/stderr to <=64 KiB each, and runtime to <=30s.
A supervisor thread enforces timeouts even if the caller stops polling. Streaming
stdout can instead go to an explicitly trusted callback with a <=480,000-byte
total; stderr remains bounded and undisclosed. Callbacks must be nonblocking.
Stream idle timeout is optional; capture selects one second.

`poll()` returns a sanitized `ProcessResult` once terminal; `cancel()` is idempotent
and synchronously requests owned process-group cleanup. It never signals by name.
The leader stays unreaped until group termination signals have been issued so
its numeric group cannot be reused for unrelated work during cleanup. An
unproven group cleanup returns uncertain, never success. This is a Linux trusted
worker lifecycle, not a security sandbox: same-user malicious workers or children
that escape the group require stronger isolation before any provider promotion.

`PipeWireCapture` requires an explicit worker factory; it has no implicit live
default. The factory follows the OwnedProcess constructor/start/poll/cancel
contract. Its fixed argv names only `/usr/bin/pw-record`, explicit source, mono
16 kHz s16 raw output, 240,000 samples. It applies 15s wall timeout, 1s stream
stall timeout, 480,000-byte total and a 16-frame queue. Malformed data, overflow,
empty/partial EOF and worker failure invalidate the whole activation. Callers
must discard previously drained audio after failure. `cancel()` reports whether
cleanup was proven; false must latch the coordinator unavailable. Do not invoke
this adapter with a real factory until the live capture gate is approved.

## Transcription seam, not an installed backend

`TranscriptionJob` also requires a trusted explicit worker factory. It encodes
bounded whole-frame PCM as an in-memory 16 kHz mono WAV and passes it on stdin;
the worker returns bounded UTF-8 text on stdout. This is an injected protocol,
NOT a claim that installed `voxtype transcribe FILE` accepts stdin or suppresses
desktop hooks. P2 must prove an isolated backend and bridge its actual file CLI.
No live config is loaded and no provider is discovered or downloaded.

Results preserve generation, deliver once and omit text from repr. Canceled
jobs ignore late output. Invalid UTF-8, empty/oversize output and failures produce
safe codes with no transcript. `cancel()` retains its planned None return;
`cleanup_proven` separately tells the coordinator whether release is safe. A false
value never permits another owner to start. Text remains transient private data,
not an execution receipt or journal observation.

## Synthetic replay

Run `python3 -m ops.voice_replay` for the committed constant-PCM fixture report.
It uses no subprocess/device/provider. It verifies framing, initial silence,
adaptive trailing silence and the 15s bound. Reports carry safe counts and
statuses; `real_speech_validated` is always false. Tests exercise subprocess
lifecycle only with controlled Python children, and capture/transcriber boundaries
with fake workers. Real audio/provider characterization is a separate HIL ticket.
