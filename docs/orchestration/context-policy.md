# Context and session policy

User-authorized September 22, 2026. This replaces the fixed 50%/65% refresh policy,
the unknown-capacity 100k fallback, and repeated startup ceremonies for this team.
The full Laws sources remain unchanged. Repair orchestration stays paused until
optimization implementation, independent review and operator verification finish.

## Load for the current job

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
known current input. Admission requires current input + task budget + report/cleanup
reserve <= the configured operational ceiling, and an applicable unpaused state.
The ceiling is a conservative operator policy, not a claim about model capacity.
The configured values are initial budgets; tune them from completed assignments.

Codex input_tokens already includes cached input. Claude request input adds input,
cache-read and cache-creation exactly once per response. Neither cumulative usage
nor subscription allowance is current context. A compaction preTokens value is an
observation, never a capacity. Its postTokens value is not the next request size.
Never translate a UI percentage without knowing its denominator and whether it is
used context or headroom until automatic compaction.

When an assignment cannot fit: finish or preserve owned work, record release and
process handles in its ticket, and start a new session in the same visible window.
Use a pointer to the existing ticket; do not recreate its history. Ordinary idle
sessions may serve multiple related assignments while admission passes. Active
writers are not cleared. Compaction is recorded and triggers reassessment, not an
automatic rerun or a claim of freshness. Quality drift or lost authority also holds
admission regardless of available tokens.

## Keep coordination inexpensive

Use `session_context watch` for local file-change polling and durable event output.
Polling does not call a model. It coalesces repeated state; optional native queue
notification wakes Buford for a changed completion, compaction or admission result.
Events contain metadata/pointers only. Monitor notifications are operational alerts,
not assignments or work evidence; canonical assignments/results remain in LIT.
No repair notification or dispatch while repair_paused is true. Optimization work
requires an explicit optimization assignment; a repair pause is not bypassed by
renaming an existing repair.

Models: routine Buford and coding use Sol/medium; routine independent review and
runtime use Sonnet/medium. Buford remains Sol/medium; Astra requires a new explicit user request. Escalate
an explicitly bounded difficult concurrency/security review to Opus/high. Reviewer
escalation must name the decision and return to the routine profile after its task boundary.
Never silently change an active writer's model. No paid API fallback.

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
provenance before accepting the pointer. No repeated startup acknowledgment loop
after identity is established. Preserve
transcripts and worktrees; no automatic deletions, process kills or main merges.

Launch profiles remove unrelated app/plugin discovery only for these invocations.
They preserve subscription authentication and approval boundaries. Claude uses
--safe-mode, restricted role tools and --autocompact auto; never --bare (which skips
OAuth) or a permission bypass. Codex disables apps/plugins for the invocation while
retaining sandbox and approval review. Model/context limits are not fabricated.

## Measure the result

Retain pre/post startup input, largest assignment growth, cached input, compactions,
compaction duration and handoff latency. Byte counts audit reading volume, not tokens.
Test deterministic admission and notification behavior offline, then verify one
fresh role startup and one real completed optimization assignment. Report measured
savings only for observed runs; several repair assignments are needed for long-run
cost/quality comparison, after repair pause is explicitly lifted.
