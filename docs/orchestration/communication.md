# Compact team communication protocol

Approved by the user on 2026-09-20. This changes message transport and retrieval,
not Laws, permissions, review gates, or the fresh-session workflow.

## Current state, not repeated history

Buford owns one current checkpoint per named agent in this directory's
`checkpoints/` folder. Paths are rooted in the main checkout
`/home/robbo/Work/arhugula-omarchy`, even when a worker is in a worktree.
Only Buford edits these checkpoints. Workers retain evidence in their owned
artifacts and report a pointer; they do not race to update Root's state.

Each checkpoint has YAML frontmatter: schema, agent, session, task, revision,
state, writer, and head. Revision increases for every change to that agent's
checkpoint, including a new task or session. A checkpoint is routing state, not
an independent grant of authority. It cannot override the user or repository Laws.
`paused` means no work; `writer: released` means no edits. Missing or conflicting
identity, scope or revision means stop and report once, not guess.

The short body separates Action, Boundaries, Evidence and Grounding. Active scope,
stop conditions and permissions belong in Action/Boundaries, not behind an optional
history link. Evidence points to immutable full Git SHAs and specific verification
artifacts; reported evidence stays distinguishable from independently verified facts.
Past receipts belong in LIT, Git, or the history log, not the current action.

## Notifications and stale messages

Send one short notification after updating and reading back the checkpoint:

```text
TO: <actual recipient>. FROM: <actual sender>.
TASK: <id>; REV: <checkpoint revision>.
ACTION: <one requested transition>.
CHECKPOINT: <absolute path>#<section>
```

Aim for 60-120 words, not a hard truncation rule. Include a full immutable head
when assigning review/integration; obtain it from Git, never reconstruct it.
Do not paste the checkpoint, test logs, full receipt and historical conversation
into the notification. A pointer saves nothing if the next step dumps every file.

On receipt, compare task/revision/session against the current checkpoint and your
last accepted revision. An older notification is historical: do not execute or
acknowledge it. An identical accepted revision is a duplicate. If the file is newer
than the notification, do not execute either action blindly: read its current
Action/Boundaries; obey a pause immediately, otherwise report the mismatch once
and await a matching notification. A new file alone does not start a task.

Before writes or publication, recheck the current revision and writer authority.
"The old message says fix it" is not authority after writer release. Stop rather
than adding another corrective commit to a head already under review.

## Read only what the decision needs

First adoption/fresh context: read this protocol, the current checkpoint fully,
and every required AGENTS/Laws/skill instruction and required reference fully.
This protocol does not summarize or replace any mandatory guidance. Then retrieve
the assigned design, code, or evidence needed to perform the task correctly.

Mid-session: read checkpoint metadata, Action and Boundaries; load Evidence or
Grounding when the changed task requires it. Do not repeat already read, unchanged
material merely to acknowledge a status update. Actual code reviewers still inspect
the exact code/tests; a hash identifies evidence but is not evidence of correctness.

For targeted reads without extra dependencies:

```bash
# Frontmatter, excluding opening delimiter; no whole-document dump.
sed -n '2,/^---$/p' /absolute/checkpoint.md
# One named section, stopping before the next section.
awk '/^## Action$/{p=1;next} /^## /&&p{exit} p' /absolute/checkpoint.md
```

Use the same selection for Boundaries/Evidence/Grounding. If a task needs a full
file, read it fully. Do not hide tool output and claim the model learned it; only
text actually returned enters its context. This is retrieval discipline, not lossy
compression or a reason to omit instructions that matter late in an arc.

## Reports and receipts

Respond for assignment acceptance, a blocker requiring action, material findings,
writer release, or completion. Acknowledgment-of-acknowledgment and unchanged
status echoes need no reply. Keep routine status in the artifact; send a delta
when scope/head changes or Buford must decide. Urgent findings include enough
reproduction information to act safely, regardless of the suggested word target.

Reports cite task/revision, exact head, artifact path, changed scope, result and
next required action. Keep implementer, reviewer and CI evidence separate. Record
full commands/results once in an owned verification artifact or LIT comment, not
in every queue receipt. Never edit released review artifacts to add status; use
a new report or explicitly authorized documentation delta.

## Transitions, monitoring and rollback

Buford attests completion/grounding, preserves memory, prepares the next checkpoint,
then controls the same-window clear/model/effort/handoff sequence. A fresh session
reports its actual UUID once; Buford updates roster/checkpoint before new dispatch.
Old session/task notifications cannot reactivate work after that transition.

Watchers only alert Buford. A deliberate pause is not a reason to assign work;
do not arm or resume alerting while the user has paused the team. Alerts do not
constitute task authorization. Integration remains Buford-owned, with explicitly
delegated helper execution and all required review/PR/main CI gates intact.

During rollout the team stays paused until Buford sends a matching resume notice.
Rollback is an explicit protocol update and revised checkpoints, never deletion
of evidence or silent resurrection of old queued assignments.
