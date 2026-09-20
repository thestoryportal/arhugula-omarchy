# Repository-only voice coordinator

`runtime.voice.coordinator.Coordinator` composes the reviewed owner, capture,
transcription and VM router. It installs nothing and discovers no live backend.
One foreground caller drives `activate`, `feed`, `poll` and `confirm`.
`cancel` invalidates ownership before waiting for any in-flight transition;
dictation cannot acquire the owner until physical cleanup has been proved.
Cancellation is atomically scoped to the command generation; a late or duplicate
command cancel cannot invalidate a successor dictation owner. Trusted callback
cancellation during activation/confirmation preflight is retained, not cleared
when starting the new turn, and cannot resurrect a canceled preview.

The fourth constructor argument is a **factory** creating a fresh single-use
`TranscriptionJob` on each turn. Optional `device_factory` and `source` must be
provided together. No default source/provider or typing/clipboard collaborator
exists. Bind a router exclusively: the coordinator wraps its trusted state
supplier and correlation generator for its lifetime.

Optional `speech=` supplies the repository speech seam. Before command admission,
the coordinator calls cancel and requires proven cleanup; failure prevents device
startup. No provider is inferred. See `panel-speech.md` for trusted backend limits.

`activate()` returns a generation. `feed(generation, frame, sequence=N)` accepts
one 640-byte frame, rejects sequence gaps and ignores already consumed sequence
numbers. Unnumbered feed is for a trusted local caller; repeated PCM content is
not a duplicate (silence frames are normally identical). Stale generation input
is ignored. Direct feeds, provider results and polling obey wall-clock bounds.

`poll()` handles at most 16 chunks/10,240 bytes, framing fragmented PCM before
the candidate energy VAD. Capture ends by existing silence/sample limits or the
15-second deadline; transcription has a 30-second deadline. Capture cleanup
must finish before transcription starts. Only the matching completed job with
proven cleanup may route a result. Journal failure or stale state discards the
turn. Unproven cleanup faults admission until external reconciliation.

Trusted state includes full VM context, mute/mode and a **monotonic context
epoch in `VoiceState.key`**. A focus away-and-back must advance that epoch even
if its application/context becomes identical again. Polling cannot detect
unreported excursions or make platform actuation atomic. The trusted executor
retains the final compare-and-act responsibility. Callbacks must be bounded;
immediate generation invalidation does not promise bounded cleanup while a
trusted callback is hung. No live timing acceptance is claimed.

Panel/keyboard confirmation uses `confirm(token, channel, bool)`. A voice answer
requires `activate(confirmation_token=token)` and fresh capture/transcription;
ordinary activation or cancellation discards coordinator access to the old
preview. Original command correlation continues across the confirmation turn.
Canceled/expired/changed-context previews never gain authority from telemetry.
No panel, socket, microphone or speech output is implemented by this module.

`VoiceObservation` v1 carries lifecycle IDs, trusted metadata, phase/status and
finite diagnostic codes. It has no transcript/audio/token/details fields and
is not an execution receipt. Older readers reject the new record kind; avoid
downgrading a reader once such records exist. Existing execution receipts and
confirmation restrictions retain their original meaning.

Offline verification:

```sh
python3 -m unittest discover -s tests -p test_voice_coordinator.py -v
python3 -m ops.voice_replay --coordinator
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Replay uses synthetic PCM, injected text and an in-memory fake executor. Its
successful exact/unknown/negative/canceled/silence/denied-confirmation cases do
not establish real ASR/VAD quality. P2 corpus and FILE/output bridge, actual
controls/panel/TTS, physical Home/End arbitration and live release remain open.
