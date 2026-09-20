# Command capture contract

`runtime.voice.capture.CommandCapture` is a repository-only, one-shot KP_EQUAL
capture state machine. It accepts synthetic 16 kHz mono signed-16-bit PCM
frames and trusted speech observations; it does not access a microphone,
perform VAD, type text, or use the clipboard.

Capture duration is bounded to configured whole milliseconds. A speech-bearing
result enters `processing` with immutable PCM for a future command router;
initial silence, cancellation, invalid input, and observation failures discard
audio. The JSON test fixture is deterministic synthetic replay only, not a
recording or evidence of microphone/VAD accuracy.
