# Operate the context-efficient team

Repair orchestration is paused while `session-control.json` has `repair_paused: true`.
Keep that pause until this optimization task is verified and the user resumes repairs.
The current record is in LIT `arhugula-orchestration-7ji`.

## Inspect before assigning

Run from the installed root checkout:

```sh
python -m ops.orchestration.session_context inspect --kind codex --transcript /absolute/session.jsonl
python -m ops.orchestration.session_context admit --kind codex --transcript /absolute/session.jsonl --ceiling 200000 --task-budget 20000 --reserve 15000
```

Use `--paused` whenever the requested work is paused. The integrated watcher reads
that state from the registry. An optimization assignment during the repair pause
must be explicitly identified as optimization work; do not turn off the repair pause
to run it. Admission is a prerequisite, not work authorization. Use the registered
identity, pinned assignment and observed completion state as well.

The initial 200k Codex and 60k Claude ceilings are operator budgets. They are not
model limits. The former 100k Claude auto-compact launch setting produced observed
compactions at 63.8k/67.2k; this does not establish why the client chose that moment.
New launches use the native auto setting. Keep a budget for full first-use Laws
reads, task output, reporting and cleanup. Adjust budgets from measured assignments.

## Fresh session in the same window

Preview a role launch without starting a model:

```sh
python -m ops.orchestration.lane_launch buford
python -m ops.orchestration.lane_launch reviewer
python -m ops.orchestration.lane_launch senior-reviewer --reason 'Review a disputed cancellation race'
```

After the existing worker has released work and reported any owned process handles,
use the native client new-session command in its existing visible window. Verify the
new UUID and actual model/effort metadata; do not call resume/fork a fresh context.
When starting the terminal lane from its shell, use:

```sh
python -m ops.orchestration.lane_launch reviewer --run --released --keep-open
```

This keeps the terminal after the child exits and offers `new / exit`; it never
kills a running child to refresh it. Supply `--codex` or `--claude` with the verified
installed executable if it is absent from PATH. Claude subscription auth is preserved:
no --bare, API fallback, auto-login, credential copying or permission bypass.

For an already running client, launch flags cannot be retroactively installed.
Use its native model/new-session commands only at a released boundary, or the launcher
after exiting the client. Record settings actually applied, not intended argv.
Old one-off /tmp launch scripts are historical; they are not the default launch path.

Update the matching row in session-control.json atomically after verifying the new
transcript identity. Keep old transcript files. The roster links to that registry;
do not maintain another current-UUID table. Buford replacement requires exactly one
explicit authority transfer. Worker refresh requires one bounded assignment pointer.
No additional window, repeated acknowledgment exchange or historical log dump is needed.

## Monitor without conversational polling

Keep generated state/events outside tracked source, e.g. `$XDG_STATE_HOME/arhugula`
or `~/.local/state/arhugula`. Preview one cycle with no notifications:

```sh
python -m ops.orchestration.session_context watch --config docs/orchestration/session-control.json --state /absolute/private-state.json --events /absolute/events.jsonl --once
```

For continuous local polling, omit --once. Add --notify only when queue delivery is
intended and the repair pause is lifted. A paused monitor still retains local events
but must not send model-waking notifications. The monitor cannot assign work, lift a
pause, kill a process or clear a session. A supervisor must preserve its PID and log;
stop only that PID when retiring it. There are no automatic paid model calls.

Verify restart deduplication before enabling notifications. A failed delivery must
remain visible and retryable. Alerts carry only metadata and an event-file pointer;
Buford records actual assignments/findings in LIT. Queue receipt is not execution.

## Acceptance and rollback

Run focused launcher/context tests, repository lint and required offline CI commands.
Independent review examines the pinned change. Verify live transcript accounting,
paused admission and a monitor cycle without delivery. Measure fresh startup input
and the next completed optimization review; retain actual results and limitations.
Do not claim subscription-dollar savings from raw token counts.

To roll back operational activation: stop the owned monitor PID, retain its state/logs,
use the previous verified lane launch at a released boundary, and restore policy files
from the pre-install backup. Leave repair_paused true. Do not reset worker worktrees,
remove evidence, change global CLI configuration or alter the immutable baseline.
