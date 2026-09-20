# Visible team sessions

These are the user-selected Codex session windows, verified against the local
session index on 2026-09-20. Read current session identity before dispatch.

| Role | Session UUID | Model |
| --- | --- | --- |
| Buford, lead orchestrator | `01a0bf2f-2b1e-7840-8ecb-dfc72f9a3af0` | GPT-6 Astra |
| Henrietta, senior engineer | `01a0bcff-2e1f-7443-9b41-6273e8f09609` | GPT-6 Astra, high |
| Munson, coding/test engineer | `01a0bec6-46e5-7313-b527-cc799f600956` | GPT-5.6 Terra, high |
| Hannibal, independent reviewer | `01a0bea6-e73c-7460-bee3-fc7b543f14d8` | GPT-5.6 Terra, medium |

Route with `codex queue --thread <exact UUID> --message <text>` using safely
quoted arguments. Start each message `TO: <actual recipient name and role>.
FROM: <actual sender name and role>`. Buford signs Buford's messages; each worker
signs their own name and role, including replies to Buford.
Replies go only to Buford's UUID. A queue receipt proves enqueueing, not execution;
require the recipient's acknowledgment or work evidence before claiming progress.

The earlier child agents named Henrietta, Munson, and Hannibal were different
sessions. Their bounded audits are reusable evidence, but they are not this roster.
Their assignments ended; the child cleanup writer was interrupted before ownership
passed to the visible Munson session. Do not resume those child writers or create
same-named substitutes for these windows. Additional helpers require explicit
bounded delegation and cannot share a writer's files.

Buford retains GitHub push, PR, CI, merge, and post-main verification. Naming the
sender in a handoff does not transfer that role to its recipient. Independent agent
review and all required CI remain; separate GitHub-user approval is not a gate.
