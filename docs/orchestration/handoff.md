# Codex Memento-compatible handoff v1

Compatibility means durable goal, progress, evidence, next action and explicit
stop state carried into a fresh session. No Claude launcher, environment
variable, context counter, or undocumented Memento wire protocol is assumed.
`docs/orchestration/handoff.json` is the checked-in boundary record for this
implementation. A runner uses private session files under its Git common
directory, shared across linked worktrees, without modifying LIT storage.

Required fields: version, active_ticket, parent_epic, branch, absolute worktree,
model, effort, role, goal, completed_work, verification, risks, next_ticket,
stop_reason. Empty risks are allowed; an empty next ticket is JSON null.
Stop reason is null only while continuation is permitted. Preserve ticket
and commit IDs in completed_work and commands/results in verification.

```sh
python3 -m ops.orchestration.handoff write /absolute/private/session.json < docs/orchestration/handoff.json
python3 -m ops.orchestration.handoff plan /absolute/private/session.json
python3 -m ops.orchestration.handoff plan /absolute/private/session.json --transport tmux --name lane_1
```

`write` validates before atomically replacing a record, fsyncs the file and
directory, and writes mode 0600 (new parent directory 0700). It rejects
symlink paths. A failed validation preserves the prior record. Retain prior
boundary records or commit references for recovery. Unknown schema versions
are rejected; migrate explicitly before resuming.

`plan` is the queue adapter: it prints exact argv and context, and never
starts a second writer. Fresh transport uses `codex exec`; tmux transport
uses `tmux new-session` with separate command arguments. Both carry the
model, reasoning effort, workspace-write sandbox and selected worktree.
Flags were checked against installed `codex exec --help` on 2026-09-20.
No `--last` session selection is used: durable files avoid resuming an
unrelated session. Actual launch requires a supervisor holding the shared
lease and fresh Git/LIT checks (the continuation unit); use subprocess argv,
never `eval`. Detached tmux must not outlive its exclusive lease owner.

On restart, LIT/Git must be reread. A file can be stale, refer to a relocated
worktree, or name an already-closed ticket. It is context, never authority.
Re-route the next ticket before launching; the previous model is historical.
A non-null stop reason rejects planning. Resolving a stop requires fresh
evidence and a new record, never merely deleting the stop field.

Fresh plans expose `stdin` and use `-` as the Codex prompt argument, avoiding
per-argument OS size limits. tmux plans cap the prompt at 32768 bytes and use
a durable handoff reference when history is large; oversized required context
is rejected. These plans describe standalone sessions. For automated work,
use the continuation runner's `"worker": "codex"` adapter, which re-routes each
ticket and supplies worker-only context instead of standalone session duties.

Optional boolean `worker_stop` and `recovery_required` fields latch reported
safety stops and uncertain completion. `handoff resolve --evidence ...` records
an explicit resolution under the shared lease. Resolution history survives
subsequent sessions. Do not edit away these fields to make a run proceed.

Disable by not consuming the queued record. Nothing starts at login, installs
services, accesses credentials or changes live Omarchy. Model process/network
access must already be authorized; local dry-runs never contact a provider.
