# Attended local transcription trial, 2026-09-20

Partial P2 evidence, not live voice release. Three user-authorized microphone
clips, each bounded to ten seconds; no further microphone budget remains.
The user approved the current host-input source, temporary stop/restart of only
voxtype.service and voxtype-commands.service, private temporary recordings and
deletion after testing. Later playback consent covered review of the retained
second and third clips. No bindings, unit/config files or volumes were changed.

## Observed results

| Clip | Captured PCM duration | Isolated ASR time | Expected neutral phrase | Playback review |
| --- | --- | --- | --- | --- |
| 1 | 9.728s | 2.00s | Not found | Already deleted under original cleanup consent when playback requested |
| 2 | 9.856s | 2.02s | Not found | User confirmed cutoff near the beginning |
| 3 | 9.856s | 2.04s | Complete phrase found twice | User: "Verified as recorded" |

The known prompt was "The blue notebook is beside the window." Only comparison
metrics are retained, not recognized text. Normalization lowercased and extracted
ASCII word tokens. Clip 3 contained the full expected token sequence twice; this
does not mean the entire raw CLI output equaled the prompt. CLI stdout had five
lines (205 bytes), so no plain-transcript-only protocol is claimed.

For clip 2, RMS energy first exceeded 0.02 at8.88s in a9.856s clip, consistent
with late speech following the chat cue. This is timing evidence, not a speech
classifier. For clip 3 the user repeated the prompt immediately after Ready,
without waiting for the Recording message. Capture duration was not increased.

Each capture ended at the hard ten-second process deadline (process.timeout),
with bounded even-length PCM and proven child cleanup. The resulting WAVs were
16kHz, mono, signed16-bit, shorter than ten seconds. This validates deadline-cut
fixture collection, not natural sample-count completion or the live coordinator.
All real clips were deleted after their applicable testing/review; none is
recoverable from repository artifacts. No transcript, WAV or model is committed.

## Exact tested transcriber boundary

The inert fixture [voxtype-isolated.toml](../../tests/fixtures/voice-replay/voxtype-isolated.toml)
is ONLY for the tested isolated environment. Never install it as a live daemon
config. It was created independently, not copied from either user config.

The trial used bwrap with --unshare-all, --die-with-parent, --new-session,
--cap-drop ALL and --clearenv; read-only /usr and individual config/WAV/model
mounts, private /proc and minimal /dev, private /tmp, empty /run and /home.
Only PATH=/usr/bin and HOME=/home were supplied to inference. Host home/config,
runtime desktop sockets, sound/input/GPU devices and external IP routes were
absent in preflight assertions. No host network listener, upload, playback,
clipboard, typing or hook was enabled in the transcription environment.
This is operational evidence for these runs, not a general adversarial sandbox
audit. Command was the pinned native executable with -q -c /transcriber.toml
transcribe /input.wav; the existing local model was mounted as /model.bin.
The owned process deadline was30s, stdout/stderr bounds64KiB, with sanitized
results. Synthetic silence also completed in2.143s; no silence-rejection claim.

SHA-256 identities (updates invalidate this characterization):

- Native executable: b5e31a85aaa952d1a78c12b8a16ba5cbdcd92eb31adc7d1a908f3c9d06edd4f1
- Existing model: a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002
- Dedicated config: e1cdf754437c6ed0f2557a8fdcc6df5f1b61a431f4f8ebdaf27cdee97dd7b664
- Clip 3 WAV, now deleted: e4535ebaee0025127cf696dae2675baadcf22452883c10b8d8bd63d1dbd2d906

Hashes identify consented inputs, not anonymized speech. No repeatable real
corpus remains after deletion. Additional recordings require renewed consent.

## Remaining work and service state

The repository's WAV-stdin injection contract is still not a Voxtype FILE
adapter. A reviewed file/CLI-output bridge, broader exact/unknown/negation/
confirmation/noise corpus, VAD calibration and live coordinator acceptance
remain incomplete. Keep .z5x.pab and the voice integration/release parents open.

A preflight attempt between clips2 and3 aborted before service stop or capture:
the command idle file was missing for a zero-PID auto-restarting daemon. It did
not consume an actual recording slot. The corrected operational check requires
idle from a live daemon, but accepts no-PID inactive/failed or auto-restart state;
both units must still stop before capture. It is not atomic device arbitration.

Restart behavior needs separate investigation: initially default dictation
retried while commands ran; later those roles reversed and both journals had
already-running errors. No repair was attempted. The final read-only check
showed both active/running, PIDs708163/708164, Result=success. This is a snapshot,
not a sustained-health proof. Original hashes of both unit files and both live
Voxtype configs were unchanged throughout. No further service operation is
implied by the completed trial.
