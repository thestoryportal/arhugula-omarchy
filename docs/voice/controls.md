# Trusted local controls (repository-only)

`decode_control` consumes the bundled `schemas/voice-session-v1.json`: one UTF-8
object, at most4096 bytes, no duplicate/unknown fields, strict versions/types.
Operations are activate, cancel, status, mute, dictation-start, dictation-stop,
confirm. Every mutation requires request_id, session_id and context_epoch.
Mute adds a boolean muted; confirm adds a private token, panel/keyboard channel
and boolean approved. A voice answer must travel through a fresh coordinator
capture/transcription turn, not be forged as a socket confirmation channel.

`ControlDispatcher` takes explicit trusted handlers and a `ControlState` supplier.
Handlers enqueue/perform bounded operations on the owner and return literal
accepted/denied booleans. They retain final state validation, authorization and
physical cleanup obligations: a control acknowledgement is not an execution
receipt. Handler exceptions are uncertain; request IDs stay consumed, so lost
responses or failures never trigger automatic retries. Session history is
limited to4096 mutation IDs; exhaustion requires a new trusted session identity.
Reentrant/concurrent requests are refused rather than queued indefinitely.

Status contains only session ID, opaque context epoch, phase and mute state.
It never returns speech, audio or confirmation tokens. Future approved panel
binding must deliver previews privately; generic status is not that channel.
Session/epoch checks reject expired contexts, but same-UID malicious code is
not isolated by these controls. Models/MCP must not receive the endpoint.

`LocalControlServer` is explicitly constructed and started by trusted code,
never by importing the module or running the default CLI. It requires an
existing owned0700 directory with no symlink path components, claims its
directory lock and creates a0600 Unix socket named control.sock. Preexisting
files/sockets are refused, including stale ones. No TCP listener, auto-unlink
or auto-restart exists. Closing removes only the inode this instance created,
through its anchored directory descriptor; substituted paths are left alone.

Wire format: four-byte unsigned network-order byte length, then1–4096 bytes
of JSON. One request per connection. Response is one JSON object then EOF.
Peer credentials must match the process UID. Accept/read/write waits are
bounded; reads share a total deadline, so incomplete/slow requests cannot
extend it by supplying fragments. **Trusted callbacks are synchronous and must
be bounded by their startup binding**; the socket timeout cannot preempt a
Python callback or cancel an already-dispatched external effect. Later live
foreground wiring must preserve this bound and cancellation responsiveness.

```sh
python3 -m ops.voice_session
python3 -m ops.voice_session --live
```

The first command is dry-run status and starts nothing. The second checks the
unmet live prerequisites and exits2; a flag or JSON approved value grants no
authority. Concrete operator startup, approved microphone/provider binding and
fresh platform guards remain absent. This is a control seam, not an installed
voice service. No keybindings, existing daemons or user settings are changed.

Tests create only temporary sockets and injected handlers. The Codex command
sandbox blocks binding the anchored socket path; run the tests in an authorized
environment supporting local Unix sockets, not by skipping their assertions.
No live microphone/provider/desktop process is involved. Python3.11 CI and Ruff
remain separate integration checks; local execution used Python3.14.
