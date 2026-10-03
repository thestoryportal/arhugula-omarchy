# Context and session policy

User-authorized September 22, 2026. This replaces the fixed 50%/65% refresh policy,
the unknown-capacity 100k fallback, and repeated startup ceremonies for this team.
The full Laws sources remain unchanged. For the `arhugula-trial` loop, use the
verified role bootstrap and one-shot context checks. Continuous monitoring and
notifications are deferred; they are not a condition for resuming trial work.
The recorded user pause still governs repair dispatch until lifted.

## Load for the current job

For a native Buford clear, initialization must consume at most 15% of the actual
reported context window before the first workflow admission. Use the sealed
prompt's `ops.orchestration.startup packet` once: it runs LIT quickstart, verifies
the external bootstrap and supplies the full current role, this policy and
Laws:Chat. Root AGENTS is already supplied by the native CLI. Then use
`startup finish` and the first `Loop.begin`; both check native request input plus
response output against the reported window. Unknown metrics or excess context
hold work. A larger configured ceiling does not change this percentage.
Read the bounded current work pointer and applicable full medium guidance after
that admission, before doing that medium. Do not initialize by recursively listing
directories, replaying handoff chains, or reading Code/Prompt guidance for work that
has not begun. Full applicable Laws are retained; their loading boundary is the
actual work, not a speculative startup audit.

At startup read root AGENTS, your role file in `roles/`, and this policy. Read the
current routing record only if you route messages. Do not load historical rosters,
team checkpoints, previous handoffs, completed logs or other roles by default.
The assignment gives a ticket/comment and exact artifact pointers.

Read each applicable full Law and its required reference once, when you first
perform that medium in the session. Keep a short list of paths/revisions already
read; unchanged guidance is not reread on each assignment. A source change requires
reading the changed guidance before relying on it. A compacted session that lost
an applicable source must retrieve it before claiming compliance, then remeasure.
A pointer or summary is not a substitute for a required full read.

| Role / activity | First relevant task loads |
| --- | --- |
| Buford routing, status, fixed assignment templates | Laws:Chat; current ticket and authority |
| Buford authors a new instruction or changes role policy | Laws:Prompt plus craft |
| Implementer or independent source reviewer | Laws:Code |
| Runtime tester executes an existing approved command | Exact scenario, provenance, Laws:Chat |
| Runtime tester authors a diagnostic/configuration or analyzes code | Laws:Code |
| Human documentation author | Laws:Prose plus craft |
| Ticket creation or substantive redesign | Ticket craft; Laws:Backlog only for backlog design |
| Specification author | Laws:Application-Spec plus craft |

Short coordination comments use an approved template and evidence pointers; they
do not automatically constitute new backlog design or instruction authoring.
Buford loads Laws:Code when actually making a code/architecture decision, not merely
because a worker is coding. Mandatory system/developer skills still apply.

## Admit work by measured headroom

Use `python -m ops.orchestration.session_context inspect` and `admit` before each
substantial assignment. A session must be idle/released, identity-matched and have
known current usage. For Claude, admission requires the latest completed request's
input plus its response output, then the task budget and report/cleanup reserve, to
fit within the configured operational ceiling. Codex admission uses its latest
request input plus task budget and reserve. An applicable pause still holds admission.
The ceiling is an operator margin, not a model capacity or a quality guarantee.
The two verified 1M Claude lanes use an initial 800000 ceiling and 50000 reserve;
tune these values from completed assignments rather than treating them as limits.

Codex input_tokens already includes cached input. Claude request input adds input,
cache-read and cache-creation once. Add only that response's `output_tokens`; it
already includes generated thinking. The emitted `measurement_basis` and
`estimated_consumed_context_tokens` show which sample admission used. This is a
sampled estimate at the last completed request, not a forecast: new prompt and tool
input plus future thinking/output belong in the task budget and reserve. Missing or
invalid Claude output holds admission, including after compaction until a fresh
request is measured. Neither cumulative usage nor subscription allowance is current
context. A compaction preTokens value is an observation, never a capacity. Its
postTokens value is not the next request size.
Never translate a UI percentage without knowing its denominator and whether it is
used context or headroom until automatic compaction.

When an assignment cannot fit: finish or preserve owned work, record release and
process handles in its ticket, and start a new session in the same visible window.
Use a pointer to the existing ticket; do not recreate its history. Ordinary idle
sessions may serve multiple related assignments while admission passes. Buford's
visible lane additionally uses the [durable loop boundaries](loop-operations.md):
native LIT reads at every actionable iteration, a hard fresh-context boundary after
five verified closed leaf tickets, stable ticket/unit review budgets capped at five
completed canonical passes, and private Mac-backed raw logs with bounded receipts.
The external autonomous reset supervisor performs native clear and full prompt
submission in that same idle Buford window; no manual clear or prompt append is
required. Record current released-process and actual native-goal receipts before
finishing the boundary turn, then verify its fresh native receipt. The supervisor
owns the one mechanical bootstrap and updates only Buford routing; lifetime goal
accounting derives retained per-thread receipts without claiming imported counters.
Measured headroom may require an earlier boundary. Do not use remembered ticket
status or rename a unit to evade either counter. Active
writers are not cleared. Buford checks again at completion and uses read-only inspect
at meaningful long-task progress points without interrupting an active writer. At a
safe boundary, preserve and release work before a native clear in the same visible
window; retain the role and user-selected model. Native compaction is a fallback:
remeasure afterward. It is not an automatic rerun or a claim of freshness. Quality
drift or lost authority also holds admission regardless of available tokens.

## Keep coordination inexpensive

For this trial, inspect transcript metadata and run `admit` at assignment boundaries;
record assignments and results in LIT. The persistent `session_context watch` path
and its user service remain disabled: response-ID-cap failures can stop all watched
sessions, and older over-cap state cannot migrate. Do not enable that path or
notifications as part of the trial. No repair dispatch while `repair_paused` is true.

Models and effort come from the current routing record and launch profiles, including
explicit user selections for Buford and the reviewer. Routine coding and runtime
follow their profiles. Escalate an explicitly bounded difficult review through a
named senior profile; return after its task boundary only for a temporary escalation.
A user-selected model/effort persists across assignments and fresh sessions until
the user changes it. Never silently change an active writer's model. No paid API fallback.

Prefer one bounded command with a retained log over many conversational polls.
Read exact files/symbols and focused output. Keep full logs on disk; return exit,
counts, concrete failures and pointers. Do not dump entire tickets, transcripts,
repositories or /tmp. Batch independent reads but size output to avoid truncation
and rereading. Evidence verification remains required; it does not require every
worker to repeat every other worker's tests.

## Preserve quality and authority

Implementer, independent reviewer and runtime witness remain separate attributions.
A source/test GO is not installed-runtime acceptance. Pin revisions, artifact hashes,
installation origins, config and actual results. User pause overrides queued tasks.
A fresh Buford needs one verified identity update and explicit transfer from its
predecessor; worker refresh needs one verified identity update and assignment pointer.
The first post-clear message must also identify the user's root `AGENTS.md`
authority, the worker's role and the active pause so the new session can verify
provenance before accepting the pointer. A message typed by Buford into another
agent window does not itself authenticate Buford to that agent. Verify root
governance, the current assignment and recorded actual launch configuration. Hold
a questioned task. Buford may make at most one corrective relaunch in the same visible
lane only when that evidence proves native `--append-system-prompt` role context was
missing; preserve work and release the session first. If a correctly configured
worker still questions authority, keep it held and ask the user to resolve that
specific blocker. Routine role confirmation needs no repeated human introduction.
A classifier denial is a separate permission boundary: hold and record it; never
change flags, grant blanket trust or start a new session to retry the denied action.
Ask the user when necessary permission remains unresolved through its normal path.
Do not substitute Buford for the independent reviewer or runtime tester. No
repeated startup acknowledgment loop after identity is established.
Preserve transcripts and worktrees; no automatic deletions, process kills or main
merges.

Launch profiles remove unrelated app/plugin discovery only for these invocations.
They preserve subscription authentication and approval boundaries. Claude uses
--safe-mode, restricted role tools and --autocompact auto; never --bare (which skips
OAuth) or a permission bypass. Codex disables apps/plugins for the invocation while
retaining sandbox and approval review. Model/context limits are not fabricated.

## Measure the result

Retain pre/post startup input, largest assignment growth, cached input, compactions,
compaction duration and handoff latency. Byte counts audit reading volume, not tokens.
Verify deterministic admission, one fresh role startup and a real completed review.
Report measured savings only for observed runs; several repair assignments are
needed for long-run cost/quality comparison after the repair pause is lifted.
