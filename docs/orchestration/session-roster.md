# Visible team sessions

These are the user-selected Codex session windows, verified against the local
session index on 2026-09-20. Read current session identity before dispatch.

| Role | Session UUID | Model |
| --- | --- | --- |
| Buford, lead orchestrator | `01a0bf2f-2b1e-7840-8ecb-dfc72f9a3af0` | GPT-6 Astra |
| Henrietta, senior engineer | `01a0c097-f8c8-7c41-8bbb-b2f4ce462e85` | GPT-6 Astra, high |
| Munson, coding/test engineer | `01a0c068-d841-74a3-988c-5e05a3e7dd0a` | GPT-5.6 Terra, medium |
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
