# Visible team sessions

## Fresh runtime repair team — 2026-09-22 20:23 local

Current workflow: [runtime repair and context lifecycle](runtime-repair-workflow.md).
These fresh sessions supersede the deployment-evaluation UUIDs below. All four
startup acknowledgments observed; no product task was assigned during startup.

| Role | Session UUID | Window class | Model / effort |
| --- | --- | --- | --- |
| Buford successor, orchestrator | `01a0cc21-9334-7450-be94-47bd20db84c8` | `arhugula-next-buford` | GPT-6 Astra / medium |
| Codex, implementer | `01a0cc0e-8c3c-76d0-816e-8bc6e62157eb` | `arhugula-fresh-codex` | GPT-6 Sol / medium |
| Claude, independent source reviewer | `b8550e64-0656-4acb-b914-92c400ae33e2` | `arhugula-fresh-review` | Opus 5.5 / high |
| Claude, runtime tester | `9d04caf9-cc39-46d2-8a80-96303983f5af` | `arhugula-fresh-runtime` | Sonnet 5 / medium |

Codex model/effort verified in new turn_context records. Claude model IDs verified
in assistant response metadata; effort verified from explicit live launch argv
(not claimed as separately server-reported reasoning effort). Claude Max OAuth
verified before launch; API override variables removed. Reviewer has Read/Glob/Grep;
runtime tester adds Bash with auto permission classification, not blanket approval.

Reviewer session `b8550e64-0656-4acb-b914-92c400ae33e2` auto-compacted on
2026-09-23 at 02:48 UTC, at 63,828 pre-compaction tokens. Its bounded review
finished afterward. Preserve the session and evidence; refresh before another
substantial reviewer assignment. It is no longer an uncompacted fresh session.
The 100k fallback did not prevent this compaction; no verified context-window
denominator or configured PreCompact hook was established by the inspection.

Buford successor handoff: [installed-runtime handoff](buford-installed-runtime-handoff.md).
This second fresh orchestrator completed startup acknowledgment; Astra/medium
verified in its actual turn_context on 2026-09-22 20:39 local. Explicit AUTHORITY
TRANSFER from `01a0cc11-a6d9-7db0-8fac-6c102b314a83` was received; the successor
now holds orchestration authority (LIT `cmt-19396cb2-9534-41de-b64a-efa213fd7e5f`).
That outgoing root completed the installed memory gate and preserves the active
Codex writer; refresh is for context, not a restart of the work. It is retained as
history in workspace5 after transfer. The earlier root
`01a0c21f-4c12-75e2-a7a2-4b6da742ac74` is also historical and no longer dispatches;
its blocked old goal does not restrict the user-approved repair loop.

Previous three worker processes were stopped only after completed turns were
verified; transcripts and worktrees remain intact. The first fresh runtime launch
exited during startup before creating a session; relaunch created the UUID above
and completed startup. No duplicate runtime worker is intended.

## Historical deployment evaluation lanes — before fresh-session transfer

These were the deployment-evaluation windows before the fresh team above.
Their UUIDs are historical; do not route new assignments to them.

| Role | Session UUID | Window class | Routing |
| --- | --- | --- | --- |
| Codex, coding/test engineer | `01a0cbac-c814-7c00-ab72-93ec463169c3` | `arhugula-e2e-codex` | Native Codex queue; require task acknowledgment/completion |
| Claude, independent reviewer | `102a35a6-4a73-4544-9873-3db5322eb1b4` | `arhugula-e2e-claude` | Existing visible Sonnet session; read-only source reviews |
| Opus, independent senior reviewer | `da6174e9-dbf3-4e92-a714-de8421114249` | `arhugula-e2e-opus` | Opus 5.5/high; response metadata verified `claude-opus-5-5` at 2026-09-23 00:16:25 UTC |

User authorized the additional Opus reviewer and delegated review-model routing.
The coding lane was refreshed in-place on 2026-09-23 00:31 UTC after its old
thread `01a0cacb-efc3-73f3-904a-d268e031e1a1` repeatedly reported insufficient
turn budget. Old transcript and unfinished work are preserved. Current compact
assignment is `/tmp/arhugula-memory-close-fresh-handoff.txt`; target worktree is
`/tmp/arhugula-runtime-repair-memory-close`. Explicit CLI resume via
`/tmp/arhugula-resume-coding-lane.sh` restored Terra/medium and the correct cwd;
both were verified in the new turn metadata. A fresh chat initially inherited
Astra. Queue model flags did not establish a changed running model; do not rely
on queue receipts as model-selection evidence. The terminal remains top-right.
Prefer Sonnet for routine bounded checks and Opus for concurrency, recovery,
memory permissions and architectural reviews. Both reviewer windows retain
Read/Glob/Grep-only tools; coding authority is not implied by review assignment.
The dependency terminal is preserved in workspace 1. Opus occupies its previous
bottom-left workspace-4 slot; Codex is top-right and Sonnet bottom-right.
Opus launches with explicit Claude Code `2.1.280`, installed alongside `2.1.278`;
the initial older-CLI attempt was rejected by the model service. Subscription
authentication was verified as `claude.ai` / Max. The launch excludes API-key
environment variables and uses safe mode to exclude unrelated local customizations.

These windows are operator-managed evaluation lanes, not evidence that the
deployed Harness owns native persistent coding-session lifecycle. The evaluation
findings log remains `/home/robbo/Work/arhugula-trial/evaluation/findings.log`.
VM work does not merge main; the user's newer deployment brief supersedes the
historical feature-team landing instructions below for this evaluation.

## Historical feature team

These are the user-selected Codex session windows, verified against the local
session index on 2026-09-20. Read current session identity before dispatch.

| Role | Session UUID | Model |
| --- | --- | --- |
| Buford, lead orchestrator | `01a0c21f-4c12-75e2-a7a2-4b6da742ac74` | GPT-6 Astra, medium |
| Henrietta, senior engineer | `01a0c097-f8c8-7c41-8bbb-b2f4ce462e85` | GPT-6 Astra, high |
| Munson, coding/test engineer | `01a0c0a7-2333-7f90-8d4d-45b43cb89067` | GPT-5.6 Terra, medium |
| Hannibal, independent reviewer | `01a0bea6-e73c-7460-bee3-fc7b543f14d8` | GPT-5.6 Terra, medium |

Route with `codex queue --thread <exact UUID> --message <text>` using safely
quoted arguments. Start each message `TO: <actual recipient name and role>.
FROM: <actual sender name and role>`. Buford signs Buford's messages; each worker
signs their own name and role, including replies to Buford.
Replies go only to Buford's UUID. A queue receipt proves enqueueing, not execution;
require the recipient's acknowledgment or work evidence before claiming progress.

Current task state: [Henrietta](checkpoints/henrietta.md),
[Munson](checkpoints/munson.md), [Hannibal](checkpoints/hannibal.md).
Use [compact communication](communication.md); send revisioned action/pointer
notifications, not repeated full handoffs. Read canonical files from the root
checkout. Rollout pause is lifted only per matching checkpoint/task notification;
never infer work authorization from another agent's resume.

Munson's prior thread `01a0c03e-0556-7971-af22-4b2b6174003e` was cleared in
the same visible Foot window on 2026-09-20. The new UUID/model/effort were
verified in local session metadata after submitting the durable handoff.
Do not route new work to the prior thread or replay its queued reset messages.

Henrietta's prior thread `01a0c02c-000b-7303-8737-74523c1cf28b` was likewise
cleared in its existing Foot window after grounding attestation and writer
release. New UUID and Astra/high were verified after submitting the root handoff.

The earlier child agents named Henrietta, Munson, and Hannibal were different
sessions. Their bounded audits are reusable evidence, but they are not this roster.
Their assignments ended; the child cleanup writer was interrupted before ownership
passed to the visible Munson session. Do not resume those child writers or create
same-named substitutes for these windows. Additional helpers require explicit
bounded delegation and cannot share a writer's files.

Buford retains GitHub integration ownership, attestation and closure, and may
explicitly delegate bounded push/PR/CI/merge/post-main execution to helpers.
Naming the sender alone does not transfer that role to its recipient. Independent agent
review and all required CI remain; separate GitHub-user approval is not a gate.
