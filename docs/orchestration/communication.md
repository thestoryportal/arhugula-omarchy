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

Keep routine comments short: the result or blocker, exact revision/evidence
pointer and next action. Link detailed review findings and raw test logs from
their retained artifact; do not repeat them in every correction/status comment.
For example, report "correction frozen at SHA; findings F1/F2 addressed; receipts
at PATH; paired reviewer please verify" rather than replaying the assignment,
governance and test transcript. Preserve substantive findings and attribution in
the linked review record. Native notifications carry only the ticket/comment
pointer and requested action; there is no parallel chat or acknowledgment loop.

Workers write their own grounding, progress, findings, evidence and release
comments directly to LIT. Buford does not transcribe routine worker reports.
Within user-released campaign scope, authors select eligible bounded slices,
coordinate claims/worktrees and reserve available independent reviewers. They
exchange review requests, clarifications, corrections and evidence directly. Buford nudges idle lanes; GREEN-cycle delivery
starts its integration attestation and closure responsibilities. No routine Buford
assignment, permission or relay is required. A peer request cannot assign a new unit,
expand owned paths, waive a gate or release a pause. An author asking their reserved independent
reviewer to inspect a frozen correction is within scope; a reviewer claiming the
next blocked implementation ticket is not.

Every coordination comment identifies actual sender name/role, intended recipient
name/role, task and session UUID. Git author identity alone does not identify the sending agent. Include the
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

`lit show` renders comment bodies without their own IDs. For an exact cited comment,
capture `lit export` JSON inside a local command, select by both `comment.id` and
`issue_id`, and print only bounded verification output:

```sh
python3 - arhugula-orchestration-7ji cmt-f1919c37-1689-4bde-9b2a-6bc119f33476 <<'PY'
import json
import subprocess
import sys

issue_id, comment_id = sys.argv[1:3]
result = subprocess.run(["lit", "export"], check=True, capture_output=True, text=True)
comments = json.loads(result.stdout)["comments"]
matches = [comment for comment in comments
           if comment.get("id") == comment_id and comment.get("issue_id") == issue_id]
if len(matches) != 1:
    raise SystemExit(f"expected one matching comment, found {len(matches)}")
comment = matches[0]
if len(sys.argv) == 4:
    from pathlib import Path
    Path(sys.argv[3]).write_text(
        f"LIT comment snapshot: {issue_id} {comment_id}\n\n{comment['body']}\n")
print(json.dumps({"id": comment["id"], "issue_id": comment["issue_id"],
                  "body_prefix": comment["body"][:500], "body_chars": len(comment["body"])}))
PY
```

Replace the two arguments for another comment. Pass an absolute workspace path as
a third argument to save the selected full body for a Read-only reviewer. `lit
export` writes to stdout; a positional filename does not redirect it. Do not paste
the full export into model context. The labeled **LIT comment snapshot** is
agent-authored ticket context, not independent proof of human consent. Verify a
claimed human instruction against the actual user turn through an authorized read,
or hold for direct human resolution. Read enough newer ticket context to detect
supersession.

## Delivery is separate from the record

Installed LIT 0.14.0 exposes comments and workflow events. The observed project
`comment_added` dry-run fires zero definitions. Automatic tagged-comment delivery
to Codex sessions is NOT verified or configured. A tag is not a delivery receipt.

After a successful comment write, capture its actual ID and send one short native
pointer to the roster-verified recipient. Use `codex queue` for Codex; use the
verified existing Foot window for Claude as described below:

```text
TO <name, role> | FROM <name, role> | <ticket> | <comment-id> | <requested action>
```

No duplicated comment body, logs or history. A failed comment write sends no action
notification; report the failure. If queue delivery fails after the comment lands,
retain that comment ID and retry delivery, not the comment write. A successful
enqueue is not proof of execution. The paired actors verify delivery/work directly.
No routine acknowledgment loop; blockers and completion go into the ticket.

Send Buford completion pointers to the verified `notification_thread` in current
`session-control.json`. A delivery target alone does not establish native freshness or work admission. Preserve the actual queue receipt or delivery failure with the result
pointer before release. A terminal-only completion is not a delivered handoff.
Buford checks current native/LIT status and nudges idle lanes under the standing
never-idle direction; pairs retain direct review exchanges. GREEN-cycle results
go to Buford for integration. A verified Buford continuation updates its notification destination with its
actual native routing; no external-supervisor receipt is required for the
user-directed Memento continuation.

An author may send the recorded review pointer directly to the reserved Codex
reviewer with `codex queue --thread <verified-uuid> --message <pointer>`. Use the
installed command help and retain the actual delivery result. The recipient must
match the current reserved review role and admitted native session. A queued message is
not a new assignment or evidence that the reviewer has started. Codex-to-Codex
communication uses native `codex queue`; do not type prompts into Codex chat boxes.
If a fresh thread has no persisted rollout, retain that native delivery error in
LIT and resolve it within the pair rather than repeating failed queues or UI input.

**NEVER IDLE: the sender owns the handoff through verified recipient uptake.** A
finding posted after the author stopped waiting must trigger that author. A frozen
candidate must trigger its reviewer. Before ending the sending turn, deliver the
pointer and check for the recipient's native user/queue-consumption event followed
by activity on that task. Preserve the receipt with the comment ID. A comment,
typed composer text or successful enqueue alone does not complete this obligation.
If uptake is delayed, retain the pointer and report the exact delivery boundary
once in the ticket; Buford can nudge the idle lane without rewriting the finding.
Do not spend a review pass or reset a session merely to check delivery.

Native `codex queue` defers delivery while the recipient's turn is active. Keep
coordination turns bounded: after dispatch and verified uptake, end the turn when
the next action belongs to a peer. Do not keep a turn open with repeated sleep or
status checks while notifications accumulate. Ending a waiting turn does not
finish the work unit and does not call for Memento. A queued notification starts
the next turn; process its exact comment once and continue the authorized work.
If a comment was already handled through LIT, acknowledge its native uptake without
repeating the task or its historical status.

Before Memento, check the existing native queue for the current thread and let
pending notifications arrive through bounded turns first. Do not use a reset to
drain a backlog. Do not delete pending items, replay already consumed pointers or
send a second copy to manufacture uptake. An active-turn queue is not a real-time
steering channel; report that boundary honestly rather than promising immediate
delivery. Immediate human stop/cancel still takes precedence over queued work.

For a Claude recipient, verify its current roster session/transcript and existing
Foot client (`arhugula-claude-coder`, `arhugula-profile-coder` or
`arhugula-facade-coder`), including live address, stable ID, terminal/process
ownership and input availability. Deliver only the short pointer into that window
using the existing Hyprland native input, then submit it with Return. Target the
verified window explicitly; preserve focus and other composers. Recheck the bound
client before submission. The tested manual route uses
`hyprctl eval` with `hl.dispatch(hl.dsp.send_shortcut({mods=...,key=...,
window="address:..."}))` for literal keys and then Return, with verified English
(US) keyboard and caps lock off. Retain type and submit results separately, then
verify the exact pointer in that session's transcript and subsequent task activity.
The first verified author wake-up is U01 cmt-0f32f6aa-c199-4c7f-a824-41fddbafdf1c;
bounded evidence is
`.local/opus-preparation-20261022/coordination/buford-continuation-20261023-224925/u01-native-nudge.json`.

Claude authors also read their ticket at review boundaries; this supplements native
delivery. No automatic tagged-LIT wake-up or monitoring service is established.
Do not resume another CLI against an active transcript or type into a Codex
composer. If submission or uptake is uncertain, inspect the exact existing pointer
and native receipt before another attempt; never resend the whole work record or
blindly press Return. An actual denial remains binding. Pair actors deliver their
own handoffs directly; routine Buford relay and acknowledgment loops are unnecessary.

For same-claim continuations, use context-policy's verified-continuation admission
rule rather than repeating requests for central ALLOW. Record Startup and the
completed-turn admission result once; deliver to independently verified current
native peers. Buford reconciles canonical metadata without blocking unchanged
authorized work merely for an old UUID. Missing native proof, failed admission and
actual holds still block the affected action. Report progress through landings,
accepted assertions and the next owned blocker under release-campaign.md; a startup
or delivery acknowledgment is not an acceptance result.

Direct LIT access permits append-only comments and each worker's existing assigned
claim/progress operations. It does not grant deletion or rewriting of another
agent's record, forced claim takeover, HIL release, review-budget edits, routing
changes or unverified ticket closure. Keep normal tool/sandbox approval controls.
Native LIT serialization remains the store's responsibility; report a failed write
and retry that write after verifying its result rather than launching concurrent
mutations or inventing a private replacement backlog.

Immediate user pause/cancel goes directly to sessions; it does not wait for LIT.
The roster and small role-checkpoint metadata retain ONLY session routing and
pause/writer safety state. They are not a second task/evidence conversation.
A pause defeats older ticket comments and queued messages. A paused scope needs
a matching release by its controlling authority; after release, routine pair
exchanges within that scope do not require a fresh Buford assignment. Stale
session IDs do not regain authority.

## Workflow transitions

The canonical paired-lanes-framework.md owns pair delivery, integration, closure,
cleanup and session continuity. Load its applicable complete section before that
transition. context-policy.md owns startup, changed-guidance adoption and measured
admission. This communication reference owns record/delivery mechanics only; a
native pointer does not waive any workflow gate or release a pause.

## User summaries

Report briefly: what landed and by whom; what each agent picks up next; remaining
implementation-unit and review/release-arc counts, plus the actual remaining list
from live `lit ls`. Exclude parent/epic double counting and distinguish blocked
leaves, unfiled known gaps and release decisions. A ticket count is not automatically
the original plan's atomic-unit count. Interrupt otherwise only for a decision or
blocker requiring the user.

## Transition state

The 2026-11-03 accepted release campaign governs bounded preparation, reviewer
pooling, author feature publishing, phase milestones and context-boundary
handoffs. Disk edits alone do not prove native adoption. Previously, the user
released the now-closed 25-unit batch and repair pause at c12
cmt-0c59889e-442c-4b5c-a01c-15847302ac02; unrelated paused scopes remain held. Unmerged custom-form
amendments are abandoned, preserved as history and must not be published. Existing
checkpoint task bodies and old queued assignments are superseded by this protocol;
retain their evidence rather than deleting unrelated work. No automatic LIT
notification service or measured billed-token reduction is claimed.

## Operational events

The local session monitor may issue metadata-only alerts carrying this ticket and
a durable event-file pointer. Those alerts are not assignments or work records.
No notifications while repair_paused is true. Receipt is still not acknowledgment.
Use context-policy.md for admission and refresh; no model-driven empty polling.
