# AGENTS

## Integration authority

Use the user's existing visible Codex sessions for the named team. Session IDs,
roles, and routing are in [the session roster](docs/orchestration/session-roster.md).
Do not create same-named child agents as substitutes for those windows. Address
handoffs explicitly `TO: <actual recipient name and role>. FROM: <actual sender
name and role>` to preserve provenance and prevent role confusion.

Use [LIT-centered communication](docs/orchestration/communication.md): ticket
comments are the work record; native queue messages carry only ticket/comment
pointers and an action. Role checkpoints retain routing/pause metadata only, not
duplicate task conversations. Read canonical guidance from the root checkout,
not an older worktree copy. No verified automatic tagged-comment notification is
configured; never assume a LIT tag wakes a session. Direct pause defeats older
comments/messages. Applicable Laws remain full-read once per relevant medium; follow the role-loading policy below.

The user authorizes Buford to own feature push, PR creation, CI, merge to main,
and post-main CI. Buford may explicitly delegate bounded integration execution to
helpers while retaining attestation and closure. Independent agent review remains
part of the implementation arc. There is no separate GitHub-user approval requirement. Do not stop for one
or revive that superseded gate from old tickets, handoffs, or review notes.
Keep all required CI checks; close work only with verified main landing and
successful post-main CI. This authority does not expand live-device consent.

<!-- BEGIN LIT INTEGRATION -->
## lit Agent-Native Workflow

This repository uses `lit` for agent-native issue tracking.

Start by running `lit quickstart` to load the workflow instructions. It prints how tickets are found, created, updated, and closed here, so running it first means the rest of your work follows the conventions this repo expects. It's a quick, read-only command — no need to check in before running it.

<!-- END LIT INTEGRATION -->

## Laws governance

The full Laws philosophy governs this team's individual work, coordination,
planning, implementation, review, and delivery. Engage it before decisions, not
just at the final gate. Speed does not turn these principles into optional advice.

After `lit quickstart`, read [the role-loading and context policy](docs/orchestration/context-policy.md) and your assigned role file. The user approved this narrower loading policy on 2026-09-22. Load full guidance when first performing its medium, not all guidance at startup:

- Code, tests, schemas, configuration, review, and architecture: read
  [Laws:Code](docs/governance/laws/code/SKILL.md).
- Agent instructions, delegation messages, skills, and handoffs: read
  [Laws:Prompt](docs/governance/laws/prompt/SKILL.md) and its required
  [craft reference](docs/governance/laws/prompt/references/craft.md).
- Backlog design: [Laws:Backlog](docs/governance/laws/backlog/SKILL.md).
- Existing-application behavioral specifications:
  [Laws:Application-Spec](docs/governance/laws/application-spec/SKILL.md).
- Human-facing documents: [Laws:Prose](docs/governance/laws/prose/SKILL.md).
- Conversational replies: [Laws:Chat](docs/governance/laws/chat/SKILL.md).

Read each selected skill's required references once per unchanged source in the session. Routine fixed-template coordination comments do not trigger prompt/backlog/ticket authoring reloads. Single-ticket craft is retained
at [the upstream ticket reference](docs/governance/laws/ticket/references/craft.md);
upstream names its entrypoint `DISABLED_SKILL.md`, so it is not an installed active
skill. Apply the user's full-Laws direction to ticket work using that reference
alongside LIT's workflow when creating or substantively redesigning tickets.

These are user-required governance, not optional reading. Apply each to its own
medium; do not use code-subtraction rules to compress prompt guidance. Keep
delegation contexts focused on the craft and task they must perform. Read the
actual sources before claiming compliance. For example, "all green" without
the required verification and independent review evidence is not an attestation.

Pinned upstream provenance and update rules are in
[the Laws source record](docs/governance/laws/README.md). Team roles, integration
ownership and current pause state are in
[the session roster](docs/orchestration/session-roster.md). Historical checkpoints
are evidence pointers, not required startup reading.
