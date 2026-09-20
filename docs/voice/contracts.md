# Dictation adapter contract

`runtime.voice.dictation.Dictation` preserves Home-start/End-stop behavior with
injected capture, local transcriber, focus, output and observation seams. It is a
repository simulator/contract, not an installed Voxtype replacement. Tests never
read microphone audio, type into applications, or modify the real clipboard.

Bind a validated VM Provider with transcription capability and available health.
`home()` starts once; another Home is blocked while busy. `end()` stops once,
transcribes bytes, validates nonempty text and rechecks the original FocusToken.
Tokens include a generation, so leaving and returning to the same window can
invalidate a stale target. The trusted output adapter must enforce the token
again at actuation. An unavailable or changed focus blocks both output routes.

Output Delivery is delivered, not-delivered (definitely no effect), or uncertain.
Only definite non-delivery permits clipboard fallback after another focus check.
Fallback copies text; it never automatically pastes. Exceptions and invalid
delivery responses are uncertain, never reasons to duplicate output. Results
report the route and safe code, not the transcript. Ordinary service failure is
failed; cancellation is canceled; failed capture cleanup latches faulted until
the owning adapter is reconciled and a new binding is made.

Calls serialize and reject reentrant state transitions from injected callbacks.
Cancel operates on recording, not a running synchronous transcriber. Mid-process
interruption belongs to the future asynchronous adapter. Observation failure
prevents capture/output where possible, and reports uncertainty after attempted
output. Notices carry correlation and safe state only; they are diagnostic
observations, not durable runtime execution truth. Live binding must add runtime
journal correlation and VM authorization; no concrete live Output is shipped.

The existing live Home/End path is unchanged. No keybindings or service units are
generated. The next KP_EQUAL capture component has no output/clipboard seam, so
command speech cannot accidentally enter this dictation path.
