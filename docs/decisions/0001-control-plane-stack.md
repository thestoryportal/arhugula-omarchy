# 0001: Local control-plane stack

Status: accepted under the user's delegated implementation authority.
LIT: arhugula-control-plane-jat.0db.t78. Date: 2026-09-20.

The foundation uses Python 3.11 or newer, standard-library dataclasses and
strict versioned JSON wire records, unittest, SQLite, and zipapp packaging.
Developer bootstrap runs locally with no downloads. This is a control-plane
choice, separate from accelerated speech/model computation.

Python keeps adapters and deterministic tests accessible and includes SQLite,
JSON, Unix sockets, subprocess control and packaging. Rust offers stronger
compile-time guarantees but introduces a toolchain/dependency acquisition
step. TypeScript would align with a future web UI but needs a separate runtime
and SQLite dependency. Neither advantage justifies a second foundation stack
for this local-first slice. Revisit only with measured limitations.

The VM runtime owns validation, policy, catalog lookup, dispatch and journal
interfaces. Executors and provider clients sit behind typed injected seams;
models never receive a raw shell executor. Heavy capture/speech/inference
processes remain external adapters, with the Mac limited to bounded model
requests. UI, terminal, voice and MCP are clients of the same contracts.

Local service transport is UTF-8 JSON request/response over a Unix-domain
socket with local filesystem access control. Host gateway transport is
authenticated HTTPS JSON on the explicitly approved host-only link.
Neither listener nor network connection is enabled by this foundation.
Framing, credentials, timeouts and cancellation belong to the transport units
and must be tested before activation. No unauthenticated TCP fallback.

Wire schema format is versioned JSON Schema documents, with closed object
shapes, accompanied by strict Python codecs. The project does not implement
a general JSON Schema engine: validation is explicit for its own record types,
and fixtures check codec/schema agreement. Unknown versions and fields fail
closed; booleans are not accepted as integer versions. Extensions require a
new contract version or an explicit compatible optional field.

SQLite is the local event-journal backend, with explicit transactions,
idempotent event IDs, append ordering and schema version checks. An in-memory
implementation shares the same interface for deterministic tests. The journal
is diagnostic/recovery evidence, not action authorization. Profiles use TOML
when configuration becomes necessary; memory archives remain a later unit.

Package only runtime/ and schemas/ into a stdlib zipapp. External executors
are disabled in the foundation. No pip install, systemd unit, Hyprland reload,
audio changes, model download or network access is part of bootstrap.
Disable by not running the application; rollback is a previous Git revision.

Layout: runtime/ owns contracts and dispatch; schemas/ owns wire documents;
adapters/ owns IO implementations once introduced; ops/ owns local build and
bootstrap; tests/ owns all fixtures. services/, ui/ and memory/ are reserved
responsibilities in the approved plan and will be created when they have code.
