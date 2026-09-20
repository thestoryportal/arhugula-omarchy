# Gateway next-session handoff

Henrietta → Buford, 2026-09-20. Buford accepted this repository-only approach.
This handoff is grounding, not implementation or release evidence. No ticket was
claimed. Preserve existing `docs/diagnostics/`.

## Target and starting evidence

`arhugula-catalog-gateway-yll.298.ejy`: authenticated Mac host model gateway.
Destination: bounded authenticated LLM/evaluator/TTS requests produce structured
responses or explicit failure/degraded outcomes while VM action authority stays local.

Exact inspected baseline: `feat/catalog-refresh` at
`3cb25ff20bbcd6732ea3b087d0093f43de40371a`, clean checkout
`/home/robbo/Work/arhugula-omarchy/.worktrees/catalog-refresh`.
Inspected main: `8f429f711bc0bdf2f4935050b976afd4956f6a45`.
Existing catalog implementation/reviews await PR10 integration; do not rebuild them.

Observed LIT: target OPEN/unassigned, Astra/high/security/implement; no direct
dependency displayed and no `autonomous-safe` label. Parent `.298` OPEN;
preceding `.1qs` CLOSED, `.din` and `.1td` IN_PROGRESS/awaiting-integration.
Catalog epic OPEN; its foundation dependency CLOSED; downstream integrations/MCP
and agent-workspace epics remain blocked by it.

Fresh session: read AGENTS, run `lit quickstart`, `lit next`, target/parent
`lit show`; recheck worktrees/claims. Buford assigns an immutable baseline and
isolated ownership before implementation. Unassigned is not proof of an unclaimed lane.

## Guiding sources

Full [Code](../governance/laws/code/SKILL.md),
[Prompt](../governance/laws/prompt/SKILL.md), its
[craft](../governance/laws/prompt/references/craft.md), and
[ticket craft](../governance/laws/ticket/references/craft.md) were read.
Pinned upstream: `4fb6c66df5d084a215c798c84e3cbc6090f695f9`.
Apply Laws throughout work, using AGENTS medium routing. Sources are currently
uncommitted: older worktrees need explicit access to
`/home/robbo/Work/arhugula-omarchy/docs/governance/laws/`.
Citations establish rationale, not compliance evidence.

[Accepted transport](../decisions/0001-control-plane-stack.md): authenticated
HTTPS JSON on an approved host-only link. Existing
[plan](../superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md)
separates gateway C.3 from provider-management C.4.

## Six proposed decisions

1. Closed service-specific payload/result variants share a versioned envelope.
   Parse bytes into immutable domain records once.
   // [LAW:types-are-the-program] exclude invalid combinations.
   // [LAW:parse-dont-validate] retain parsing proof.

2. Authentication owns request admission; VM policy owns action authorization.
   Reuse existing provider/catalog facts; grant no executor/catalog-mutation access.
   // [LAW:single-enforcer] name each invariant's owner.

3. Trusted endpoint/server identity and bearer credential cross injected HTTPS,
   verifier, and provider seams. Reject redirects/insecure schemes; tests use
   synthetic secrets. // [LAW:effects-at-boundaries] isolate external effects.

4. Proposed limits, to substantiate during design: 64 KiB request; 32 KiB
   text/context; 32 candidates; depth 8; 30-second total deadline; 64 KiB text
   response. TTS proposal: 10 seconds mono 24 kHz s16 PCM, 1 MiB encoded envelope,
   no remote URL/path or playback authority.
   // [LAW:one-source-of-truth] publish limits canonically.

5. One request-lifecycle owner handles cancellation and single terminal delivery;
   late replies cannot restart work. Define duplicate/replay retention; no automatic
   retries initially. // [LAW:no-ambient-temporal-coupling] encode ordering.

6. Explicit local fallback reports primary failure and provider provenance within
   the original deadline. Authentication/identity/malformed responses remain errors;
   absent/failed fallback remains an error.
   // [LAW:no-silent-failure] degradation cannot hide failure.

## Acceptance and stop

Behavioral tests cover all service successes; bad authentication/version/fields,
bounds, identity/catalog mismatches, malformed responses, timeout/host loss,
cancellation/late/duplicate replies, fallback failures, and diagnostic redaction.
Demonstrate no execution authority. Run focused/full ResourceWarning-error tests,
required Ruff, runtime/fresh-package smoke, diff check, and independent security
review; report immutable SHA, commands/results, dispositions and limitations.
[LAW:behavior-not-structure] [LAW:verifiable-goals]

No real Mac connection, credentials, listener, inference, downloads, deployment,
audio or desktop effects. Endpoint/trust/secrets/provider/live acceptance remain
unresolved. “I'll just contact the Mac to prove it” requires activation authority.

Stop after the verified offline implementation/review handoff to Buford. Buford owns
publication/merge and post-main CI; no separate GitHub-user approval is required.
Do not claim deployment or close from local tests.

Learnings: inspect existing branches before rebuilding absent-on-main features;
separate provider success from assembled-application and live-release evidence.
