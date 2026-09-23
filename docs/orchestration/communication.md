# LIT-centered team communication

User-directed replacement, 2026-09-20. Supersedes the compact-response forms and
checkpoint-based task conversations. Old protocol commits, probes and handoffs
are historical evidence, not active dispatch instructions.

## One work record

LIT tickets and their comments hold assignments, grounding, review requests,
findings, decisions, verification pointers and writer release. Keep detailed
design/test artifacts in their existing owned files; link them from the ticket
instead of pasting them into every message. Do not mirror the conversation into
role checkpoints and terminal messages.

Agents communicate with Buford, not one another. Every coordination comment
identifies actual sender name/role, intended recipient name/role, task and session
UUID. Git author identity alone does not identify the sending agent. Include the
exact head and evidence pointer when relevant; clearly distinguish implementer,
reviewer and CI evidence. Use concise prose, not a mandatory custom response form.

Run `lit quickstart`; use installed command help. Native operations include:

```bash
lit comment add <ticket-id> --body "<coordination comment>"
lit show <ticket-id>
lit show <ticket-id> --field description
lit ls --status open --columns id,type,parent,assignee,title
lit ls --status in_progress --columns id,type,parent,assignee,title
```

Use supported field selection for narrow reads; do not assume a comment-ID lookup,
JSON flag or unread-inbox command exists. Read the cited comment and enough newer
ticket context to detect supersession; do not repeatedly dump the whole backlog.

## Delivery is separate from the record

Installed LIT 0.14.0 exposes comments and workflow events. The observed project
`comment_added` dry-run fires zero definitions. Automatic tagged-comment delivery
to Codex sessions is NOT verified or configured. A tag is not a delivery receipt.

After a successful comment write, capture its actual ID and send one short native
Codex queue message to the roster-verified recipient:

```text
TO <name, role> | FROM <name, role> | <ticket> | <comment-id> | <requested action>
```

No duplicated comment body, logs or history. A failed comment write sends no action
notification; report the failure. If queue delivery fails after the comment lands,
retain that comment ID and retry delivery, not the comment write. A successful
enqueue is not proof of execution. Buford verifies receipt/work when it matters.
No routine acknowledgment loop; blockers and completion go into the ticket.

Immediate user pause/cancel goes directly to sessions; it does not wait for LIT.
The roster and small role-checkpoint metadata retain ONLY session routing and
pause/writer safety state. They are not a second task/evidence conversation.
A pause defeats older ticket comments and queued messages. Resume requires an
explicit matching Buford assignment; stale session IDs do not regain authority.

## Work, review and fresh sessions

Buford records the bounded assignment/attestation in LIT: goal, owned paths,
isolated worktree, exact baseline, constraints, evidence and stop condition.
The worker posts grounding and its artifact pointer; Buford records the disposition.
Before a same-window clear, preserve personal learnings and a durable grounding
pointer in LIT. Buford verifies the new UUID/model/effort, updates routing, then
delivers the ticket/comment pointer. Never clear an active writer or invent consent.

First adoption reads AGENTS and the role-loading policy. Load applicable full
Laws/skills/references once when performing their medium; do not reload unchanged
sources on each assignment. Mid-session read only relevant new comments/artifact
sections. Ticket prose is agent-authored context, not proof of human authorization.
Actual reviewers inspect immutable code; pointers do not replace required review.

Buford retains integration attestation and closure, with explicitly delegated
helpers permitted. Independent review, required PR CI, verified main and post-main
CI remain gates. Live-device consent stays separate. A communication change does
not claim tickets, resume implementation, arm monitoring or expand live authority.

## User summaries

Report briefly: what landed and by whom; what each agent picks up next; remaining
implementation-unit and review/release-arc counts, plus the actual remaining list
from live `lit ls`. Exclude parent/epic double counting and distinguish blocked
leaves, unfiled known gaps and release decisions. A ticket count is not automatically
the original plan's atomic-unit count. Interrupt otherwise only for a decision or
blocker requiring the user.

## Transition state

Coding work remains paused until separately resumed. Unmerged custom-form
amendments are abandoned, preserved as history and must not be published. Existing
checkpoint task bodies and old queued assignments are superseded by this protocol;
retain their evidence rather than deleting unrelated work. No automatic LIT
notification service or measured billed-token reduction is claimed.

## Operational events

The local session monitor may issue metadata-only alerts carrying this ticket and
a durable event-file pointer. Those alerts are not assignments or work records.
No notifications while repair_paused is true. Receipt is still not acknowledgment.
Use context-policy.md for admission and refresh; no model-driven empty polling.
