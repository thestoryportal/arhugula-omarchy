# Repository-only panel and speech seam

Task6 P1 is deliberately headless and provider-free. Importing these modules
opens no window, starts no audio process and installs no key bindings.

`SpeechQueue(backend, state)` has one owned slot, not a backlog. `say(prompt,
activation_id)` accepts only the three reviewed literals in `PROMPTS`; its bool
means admitted, not spoken successfully. Dynamic router labels/model text are
not silently promoted into that catalog. A later trusted binding must select
the fixed prompt for the reply type and display capability-specific text in
the panel. No router-to-TTS binding or concrete provider is installed here.

The queue detaches and compares complete `VoiceState` snapshots (context,
monotonic context epoch, activation, mute, mode), including checks after backend
callbacks. `poll()` cancels stale work; `cancel()` invalidates in-flight startup
before waiting for cleanup. The trusted backend must cancel both synthesis and
playback, discard late synthesis results, use bounded start/cancel operations,
and return the owned-process cleanup result. Uncertain cleanup latches the
queue unavailable; callers cannot reset the latch by sending a new prompt.
No prompt/provider exception text is returned in diagnostic codes.

An optional `speech=` on `Coordinator` cancels speech and requires literal
`cleanup_proven is True` before admitting command capture. Cancellation arriving
during that preflight remains effective. Existing callers with no speech retain
their provider-free behavior. Future Home/End bindings must perform the same
cleanup gate before dictation; they are not implemented or validated here.
Polling does not replace a final platform actuation guard or provide a live
cancellation latency guarantee. A concrete backend must meet those gates.

`VoicePanelModel(state, send_control)` is a UI-independent model for a future
Tkinter view. Explicit `connect(session_id)` / `disconnect()` invalidate previews.
A trusted private binding calls `present_preview(token, capability_label,
expires_at_ms, state=issuance_state)` using the VM-issued expiry and state;
public control status cannot manufacture or recover a preview token. Labels
are bounded printable trusted catalog text, not speech transcripts.

`view()` returns phase, degraded state, capability label, preview text and
countdown, never the token. Expiry (maximum30 seconds), backward clock motion,
full-state drift and reconnect disable confirmation. Tokens are consumed before
any confirmation callback and retained in bounded replay memory (4096 entries,
no eviction). Exhaustion requires a new externally reconciled panel/session,
not automatic retry. Sender exceptions are uncertain and never retried.

`confirm(bool)` serializes the closed version1 control message; the injected
trusted sender reaches `ControlDispatcher` and its coordinator/VM handler.
The handler retains final authorization. The model does not call an executor.
`key('Return'|'Escape', focused=True)` uses the keyboard channel; unfocused keys
are ignored. This is not a keyboard listener or evidence of a working GUI.
Escape rejects the displayed preview only; global capture cancellation belongs
to a separately wired cancel control. Accepted control messages are not command
execution receipts. The GUI model is not yet included in the runtime-only zipapp.

Verification uses an in-memory audio backend, the real control parser/dispatcher,
the real VM confirmation path with a fake executor, and no `Tk()` instance.
Actual panel interaction, spoken intelligibility, output-device selection and
bounded interruption remain P4/P8 acceptance gates. Real TTS/provider selection
requires a human decision; no package/model installation or playback is inferred.
