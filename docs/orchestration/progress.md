# Execution ledger — plan: docs/superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md

LIT is the work authority. This ledger records evidence and implementation
decisions, and never substitutes for LIT status.

Pre-flight interfaces: routing -> handoff -> continuation -> isolated tests.
Routing produces versioned model/effort/role/stop data. Handoff must retain it;
continuation must enforce it before claim and launch. No authority conflict.

Ruling: the approved plan has epic bullets rather than executable Task N
briefs; use LIT unit descriptions as briefs and this durable ledger instead
of the skill's numbered-task extraction scripts. Cost if wrong: bookkeeping
adaptation only. Retain all workspaces to honor the user's no-destructive-work
boundary.

Ruling: bootstrap tools use dependency-free Python under ops/orchestration;
foundation remains free to select its own stack. Cost if wrong: a small
adapter migration rather than an early control-plane commitment.

Task cqh: verified. Baseline 7313ed5. Tests first: routing module absent,
expected import failure. Implement capability routing, explicit metadata,
inherited safety floor, fail-closed conflicts and backlog dry-run.
Verification: `python3 -m unittest discover -s tests -v` passes 10 tests;
live `lit export` report covers 38 leaves (5 eligible, 21 missing autonomy,
12 ambiguous). `git diff --check` passes. Ambiguities are the planned mgt unit.

Task 6x0: baseline 0aab894. Handoff/launch-plan tests first fail because the
module is absent. Required fields, model/effort pairing, stop refusal,
corruption, symlink refusal, private atomic persistence and argv boundaries.
Memento compatibility is semantic durable context, not an undocumented API.
Installed Codex exec/resume help inspected; no external documentation or model
network access used under this session's restriction.
Task 6x0: complete; fresh full suite 18/18 pass, tmux plan CLI smoke passed,
diff check clean. Ticket closed after implementation commit.

Task jl9: baseline ae419d1. State-machine and real Git adapter tests first
failed on absent modules. Added exclusive shared lease, selection/ancestor
dependency validation, fresh verification, scoped commits, LIT close and
durable crash/stop handoff. Real temporary Git worktrees exercise foreign
dirt, changed HEAD, deletion, symlinks, scoped commits and worker timeout.
Ruling: unfiltered lit next plus explicit hierarchy/dependency validation is
required by observed 0.14.0 behavior; --type task can bypass an ancestor block.
Cost if wrong: conservative stops rather than out-of-order implementation.
Timeout test exposed unclosed process pipes; draining communicate after
process-group termination fixes the resource leak without changing policy.
Task jl9: complete. Fresh full suite 34/34 with resource warnings treated as
errors; live runner plan selected jl9 Astra/high; diff check passes. Real
LIT and worker/resume integration remains the separate yvy unit.

Task mgt: baseline 47d2054. Sanitized real LIT export fixture pins 35 open
leaves (three implementation units already closed). Reviewed metadata covers
all 38 original leaves, including closed units. Live CLI materialization
updated 37 tickets, preserved safety/unrelated labels, and a second preview
produced zero patches. All 35 open leaves have model assignments: 27 Astra,
8 Terra; zero routing ambiguity/conflict. Safety eligibility remains separate.
Fresh suite: 39/39 tests pass; diff check passes.

Terra/medium read-only routing review: dependency-blocked reporting and mixed
bare capability role loss reproduced RED and fixed GREEN. Report now includes
blocked_by and refuses ambiguous bare high capability labels.
Ruling: ready in a report must not imply a blocked issue is executable;
dependency stops now apply as well as supervisor enforcement. Cost if wrong:
more conservative dry-run output, no expansion of authority.
Minor (deferred): legacy bare labels recognize high capabilities and validation
but not all bounded capabilities. Use canonical capability: labels; broadening
legacy aliases is not needed for the materialized backlog.

Task yvy: baseline 7b47fab. Real LIT temporary stores, linked Git worktrees,
subprocess fixture workers, and a fresh Python supervisor process exercised
claim -> verification -> commit -> close -> durable handoff -> next claim.
First route Astra/high, second Terra/medium; prior completed work and evidence
survived the process boundary. Both tickets closed, two scoped commits, clean
Git state. HIL/foreign-tree cases left work unclaimed and unchanged.
Regression discovery: resume initially lacked a prior-record input (RED);
implemented validated history carryover with branch/worktree check (GREEN).
Real LIT queue exhaustion returns exit 1; exact diagnostic is now normalized.
Fresh suite 41/41 pass with resource warnings as errors; diff check passes.
No provider credentials/network or live configuration used.

Task 8i8: baseline ddbfc9d. Astra/high whole-branch read-only review found
seven Important issues; no Critical issues. All seven entered one fix pass:

1. Foreign index content hidden by restored worktree: regression RED, now
   inspect index/worktree separately and gate exact staged paths before commit.
2. Restart bypass of worker safety stops and lost explanation: regression RED,
   now latch worker_stop, preserve summary/risks, require recorded resolution.
   Post-commit uncertainty and repeated interrupted resumes also stay latched.
3. Preflight uninspected branch poisoned resumes: regression RED, now retain
   established identity and allow fresh inspection of an unknown identity.
4. Completed epic exports lack status: regression RED, shared completion
   resolver now uses child rollups while preserving normal container checks.
5. Missing synchronous Codex integration: tests RED, CodexWorker now invokes
   current model/effort with stdin and schema-checked receipt-file transport.
6. Unbounded context/oversized argv: tests RED, fresh prompts now use stdin;
   active context has a configurable byte ceiling and durable-history references;
   tmux prompts are bounded. Required oversized context stops explicitly.
7. LIT state changed during worker: regression RED, fresh ticket/ancestor,
   dependency, scope, route and claim checks guard launch/commit/close.

Fresh verification after fixes: 54/54 tests pass with ResourceWarning as error;
git diff --check passes. Real LIT/Git integration now also runs the synchronous
Codex adapter against an offline executable for successive Astra/high and
Terra/medium tickets, producing two verified commits and closed tickets.

Final: Ruling: reviewer set aside paid-provider behavior, detached tmux
lifecycle, live Omarchy integration, and hostile trusted executables. Keep
these outside this offline bootstrap release: provider/live access exceeds
session scope, detached sessions require an external lease owner, and trusted
workers still need process sandboxing. Cost if wrong: additional integration
validation before enabling those deployment modes. No paid/live success claimed.

Task 8i8: complete in commit 7c89844. All orchestration arcs and the epic are
closed in LIT. Final suite 54/54, diff check clean, LIT integrity clean.
Next: arhugula-control-plane-jat.0db.t78, Astra/high architecture. Fresh
runner plan stops autonomy-unclassified; all 32 remaining leaves lack reviewed
autonomous-safe scope. Preserve this boundary rather than silently granting
backlog-wide eligibility. Git remote/LIT sync are checked separately at publish.
