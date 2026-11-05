# Solo harness scope and execution plan

The user-approved feature scope was recorded on 2026-11-04 in
`arhugula-harness-trial-193` at `cmt-1af62682-3d73-49c1-a2e9-29390aa1ba29`.
The eleven-package queue below is derived from that scope under standing execution
authority; it does not claim separate user approval of the package ordering.
The direct instruction approves the repository-derived solo-developer local harness
features, including memory, dynamic orchestration, skills, validators and local tools.
Multiple agents are included; multiuser/team-tenancy certification, six-category
production certification and exhaustive production load/soak qualification are deferred.
Deferred findings remain recorded, never PASS. Preserve unrelated-file/secret protections,
actual permission denials, B7 storage acceptance/exposure binding and existing claims.

## Scope derived from actual source

Baseline repository: `https://github.com/thestoryportal/arhugula-harness.git`,
merged revision `81fbed7cbd6e8e2925c9303ff6b32f75d1280264`, tree
`87fdda33c8e7973fd75e1a5fd192baa4f1f0fe41`; the inspected `c53bf794` tree matched.
The following overlapping groups describe included functionality, not task counts,
extra signoffs or installed PASS claims. A listed configuration condition governs
activation; it is not permission to omit an approved feature or weaken its protection.
Current implementation, ownership and acceptance state belong in live LIT, with exact
candidate evidence. The versioned [feature inventory](solo-feature-inventory.json)
retains all 37 source observations, source paths, baseline conditions/limits and
proposed witnesses. Its observations describe the identified historical source
snapshot, not current acceptance or an instruction to repeat completed work.
The retained .local fragments are provenance, not the durable scope dependency.

### Core execution

- **Solo persona, configuration and workflow authoring.** Solo persona is runtime default; four workload classes; TOML/YAML versioned manifests; typed/unknown-field validation; environment/file/CLI configuration precedence; path bindings; workflow/default and per-step configuration; explicit optional-feature switches.
- **Public CLI, MCP and Python execution ingress.** CLI run with provider/model/config/output options; one-shot bootstrap-execute-shutdown; daemon client over Unix socket; MCP run_workflow by registry key or manifest path; Python run; text/JSON results and typed exit statuses.
- **Local process/session lifecycle and administration.** Persistent daemon socket/pidfile; bootstrap rollback; signal-driven drain; reject new work after drain; bounded shutdown and observability flush; per-process Python run concurrency guard; daemon request contexts.
- **Six solo-usable multi-agent workflow patterns.** Single-threaded-linear; parallelization; orchestrator-workers; decentralized-handoff; hierarchical-delegation; evaluator-optimizer; workload/topology admissibility; branch-index ordered aggregation; cascade pause/proceed/cancel; evaluator structured verdict and iteration cap.
- **Nested agents, briefs, roles and bounded concurrency.** Child workflow manifests/steps; canonical brief and summary hash; parent/child causality; inherited gate/placement constraints; role-specific model binding; recursive hierarchy; three-child hierarchical width cap; configurable sub-agent worker capacity; child failure/pause/refusal propagation.
- **Inter-step context and post-join synthesis.** Linear/handoff prior-output delivery; evaluator draft/feedback delivery; per-run context isolation; effect-free post-join LLM synthesis over ordered worker outputs; deterministic fold without synthesis.
- **Structured results, output replay and inspection.** Completed/failed/drained/partial/paused outcomes; terminal state and typed failure; pause reference; audit head and trace IDs; provider/model, dispatch-kind and provider-discriminator cost rollups; per-run persisted engine outputs; replay and fanout recovery markers; read-only human/JSON ledger inspection; pause/protected-result inspection.; Inspector trace-browser TUI and holdout sample/review/scaffold commands; audit verification and sidecar-migration administration where their explicit inputs are supplied.
- **Model/engine routing and resilience controls.** Workload/persona/deployment engine selection; five engine classes; layered routing; per-role/per-step provider/model/prompt binding; fallback chains; retry/backoff and circuit breakers; typed deadlines; post-effect no-retry fence; local/subscription routes.
- **Versioned prompts, role selection and cache controls.** Inline and stored prompt versions; role/workload selection; per-step prompt override; reject unauthored hashes; provider cache directives, long-TTL workload controls, boot prewarm, daemon keepalive and concurrent cache cohorts.
- **Skill registry and activation hooks.** Load *.skill.json manifests; validate frontmatter; reject duplicate IDs; content version hash/body-token estimate; workflow-init and dispatch selection hooks; explicit activate_skill; activation spans.
- **Tool contracts, MCP clients and deferred discovery.** Named ToolContract registration; duplicate/reserved-name rejection; MCP stdio/StreamableHTTP/SSE clients; tool discovery and calls; frozen schema superset; deferred search_tools; per-call trust and schema checks; idempotency, timeouts and result normalization.
- **Model-emitted tools and operator assessment.** Offered-membership/schema validation; bounded model/tool iterations; tool rewrite/assessment before dispatch; DENY/HOLD/refusal; operator disposition auditing; post-effect terminal fence; tool result returned to inference.
- **Solo approval, response palettes and notifications.** AUTO/ASK/DENY composition; placement inheritance; response approve/edit/reject/respond/hold where permitted; cross-trust/validator palette narrowing; MCP elicitation; timeout fail-closed; operator-policy override with append-only evidence; optional webhook delivery.
- **Pause-state access, durable resume and recovery.** Python read_paused_workflow_state and resume; durable pause handles and claim admission; run identity/context preservation; corruption/staleness/workflow/child-handle refusal; root/child authority; nested/fanout pause context; engine-specific recovery and effect-fence resolution; journal inspect/adopt/dispose administration.
- **Validation and escalation extension framework.** CP validator registry/evaluate API; driver validation hooks; transient retry/escalation; narrowed HITL palette; cost/audit integration; optional webhook composer.

### Harness memory

- **Canonical local persistence, five-tier typed envelopes, derived index and operation ledger.** runtime.memory.enabled; verified permitted state root; working tier is live context, not a claim that every tier is a persistent database.
- **Automatic episodic capture and explicit event capture.** capture_run_events/capture_turns and capture policy; scope/provenance derived from actual dispatch.
- **Policy-filtered query/retrieve/read, lexical ranking and bounded context packet.** active eligible record kind; requested scope and policy; token_budget; semantic/procedural data already admitted.
- **Prompt injection, native/provider access selection and subscription CLI delivery.** standard tools when supported/enabled, otherwise permitted prompt packet, then opt-in native provider, else no-access; subscription CLI has text transport.
- **Standard memory tools and optional native/backing stores.** tool-capable SDK route and standard_tool_access; native provider disabled by default; configured backend capability/auth remains required.
- **Reviewed semantic/procedural promotion, preferences, edits, deny and supersession.** retain actual review policy, source refs, target kind and explicit injection policy; proposed remains nonactive until permitted approval; do not impersonate human approver.
- **Scope, provenance, write/review policies and immutable audit identity.** solo workspace/workflow/provider-family/profile boundaries still apply; multiagent sharing only when permitted; multiuser certification outside current finish line.
- **Content redaction, tombstone and retention expiry.** explicit redaction/retention operation; preserve ledger sidecars and exclusion from recall/tool reads.
- **Migration, CLI source-import policy, compaction disposition and durability carriers.** explicit callback migration apply; CLI import policy; admitted compaction dispositions; selected engine durability evidence.
- **Local L2 embeddings and cross-axis procedural context composition.** routing activation configured with admitted corpus, optional embedding extra, pinned local model/cache; procedural resolver from actual prompt/skill/routing state.

### Local stack and protections

- **Local package/config/run/daemon/operator UX.** solo-developer with local-development or self-hosted-server; choose actual config surface separately.
- **Local Ollama and configurable routing/reliability.** No team-persona requirement; local Ollama models explicitly enabled; paid Anthropic/OpenAI SDK routes outside selected release profile.
- **Subscription CLI providers and instruction/memory profiles.** Claude Code and Codex selected for first release. Antigravity/Gemini and generic-command adapters exist but are not implicit release additions; docs explicitly exclude Gemini/Antigravity overlays.
- **Offline embedding and workload classifier.** Optional embedding extra, routing_activation=true, verified local BAAI/bge-small-en-v1.5 assets/cache; no cloud classifier required.
- **One operator's agent teams and six workflow topologies.** Included for SOLO; agent multiplicity does not imply TEAM_BINDING; workload/engine admissibility still applies.
- **MCP server/client integrations and tool discovery.** Solo can host run_workflow and consume configured external tools; stdio/streamable_http/SSE subject to trust/transport floors. HTTP MCP transport retained; separate HTTP operator recovery API excluded.
- **Local process, Docker and gVisor sandbox enforcement.** Solo still obeys delivered tier >= resolved floor. T1 host/T2 Docker/T3 runsc local; T4 current factory uses E2B managed full VM outside no-paid-local profile.
- **Solo HITL policy and real safety decisions.** SOLO persona floor auto defaults true; local-mutation auto defaults false; other safety floors still compose. Per-step persona is a separate binding from deployment OD persona.
- **Self-hosted telemetry, traces and cost visibility.** SOLO local-development/self-hosted-server supported; team sampling/multi-tenant qualification deferred.
- **Secret handling, local audit signatures and protected results.** Self-hosted-keyring/local optional keyring-env fallback; solo can select local Ed25519 and fail-closed signing; MTC forbids local signer and requires stronger tenant/delegated controls. Cloud KMS/GCP Secret Manager outside local profile.
- **Local memory storage and persistence choices.** Automatic local memory default; filesystem/encrypted filesystem/operator-defined configurable, SQLite DATABASE for self-hosted-server; S3/managed DB/provider-native memory are explicit optional remote routes, not required local dependencies.
- **Retained state, pause/resume/recovery and backup boundary.** Solo safety/recovery remains in scope; durable opt-ins and actual retained root required. No multiuser/production soak prerequisite added.

Memory includes episodic run/turn/tool/compaction records; semantic facts,
preferences, decisions, conventions, failure lessons and research; procedural snapshots;
scoped capture, persistent storage, policy-filtered query/read and bounded prompt packets;
reviewed promotion, edits/supersession and auditable redaction/retention/migration.
Honor `never`, `retrieval_only`, `prompt_packet_allowed`, `tool_allowed` and
`native_allowed` at their corresponding output boundaries. Do not equate automatic
summary capture with a full transcript archive, or L2 model-routing embeddings with
vector-memory recall. General import/export, scheduled pruning and arbitrary interactive
CLI turn ownership are not established by the baseline APIs; deliver the supported
interactive integration and expose remaining source gaps explicitly, without inventing
permissions or silently removing approved outcomes. Existing jpp/2rk/oxw records remain
the memory work records; source already contains the external-CLI packet routing fix.

## Eleven work packages

Use existing records/claims. These packages organize delivery; they do not authorize
11 new tickets, reopen closed work, take over a writer or grant additional review passes.

| Package | Owned outcome and done condition |
| --- | --- |
| 1. Land prepared changes | Baseline priority was 1699 then 1701, with 1702 independent. Check current Git/LIT before acting; retain prior findings, reviews and Source09 provenance. Done: Actual main landing and required candidate/own-main CI; 1700 already complete and never repeated. |
| 2. Complete memory | Existing jpp/2rk/oxw: selective injection, supported CLI delivery, target-aware promotion and capture/review/recall integration. Done: Separate supported Codex/Claude runs reuse permitted persistent knowledge; restrictions, promotion and redaction work. |
| 3. Complete public workflow control | CLI/MCP pause, answer, inspect/resume and usable elicitation; preserve typed root/child refusals. Done: Real public pause/answer/resume works once; invalid or duplicate resume causes no effects. |
| 4. Complete dynamic orchestration | Lead-directed worker selection/spawning and information flow, preserving roles, bounds and inheritance. Done: Changing the lead plan changes workers/briefs and yields the correct joined result. |
| 5. Complete usable skills | Selected versioned skill content and supported tool bindings reach actual execution. Done: A workflow uses the selected skill; unavailable/invalid content fails explicitly. |
| 6. Complete validators | Wire configured validators into runtime evaluation and escalation. Done: A real configured validator accepts/rejects/escalates; no false success from an empty registry. |
| 7. Complete local tool carrier | Resolve required local high-isolation code/computer tool execution without E2B dependence or safety downgrade. Done: Permitted tool actually runs locally with required isolation and cleanup; denied calls have no effect. |
| 8. Bind retained state and backup | Choose/bind actual state and backup boundary; preserve existing B7/permission holds. Done: Supported restart/reset, backup/restore and rollback preserve memory, state, claims and keys. |
| 9. Finish solo setup and local stack | Selected providers, Ollama, offline assets, topology examples, sandbox, secrets/audit/redaction, local telemetry and accurate instructions. Done: Documented local setup runs selected routes and actual integrations without excluded fallback. |
| 10. Qualify one installed candidate | Shared feature/negative/cancellation/restart/restore scenarios; repair observed blockers and rerun affected cases. Done: Approved solo feature inventory is demonstrated on the identified installed build. |
| 11. Close solo deployment | Final operating/recovery instructions, required source09/provenance/shipping records and finding disposition. Done: No unresolved solo blocker; deployment acceptance recorded and existing relevant tasks closed truthfully. |

Package order is integration priority where dependent, not whole-task serialization.
Independent source/acceptance preparation continues in owned worktrees while exact CI,
storage setup or shared-resource windows hold their own consuming transitions.

## Repeat for each deliverable

1. Confirm current release, native owner, isolated worktree and consuming prerequisite.
2. Implement runnable behavior with focused checks; retain qualifying unchanged proof.
3. Freeze for one independent reviewer; consolidate fixes and review affected deltas,
   preserving findings and spent passes. No author/correction-author self-approval.
4. Pass required exact candidate/base CI, use the holder-bound safe merge door and
   verify successful own-main CI. No duplicate full local suite, review panel or status PR.
5. Record one concise result and existing reflection/checkpoint/arc-close/metrics once
   per shipped source arc. Source done and installed done remain distinct; cleanup is separate.

PR1700 is source-complete once; do not replay its closeout. Preserve Source09 child
`arhugula-harness-trial-193.5i4` review notes, register/provenance, prior-only archive and
contract metrics obligations in substantive shipping work. Installed acceptance does not
turn a missing provenance witness into PASS or justify a separate closure/status PR.

## Installed completion

One identified local build must demonstrate every included solo feature, correct
negative/refusal behavior and local data protections through shared bounded functional,
failure-cleanup, restart and restore scenarios, with usable operating/recovery instructions
and no unresolved solo blocker. B7 still requires actual retained storage binding before
acceptance/resume exposure. Required local high-isolation computer/code tools need a local
T4 carrier; a correct refusal alone does not prove feature availability. Resolve those
concrete boundaries within current scope, without a general proposal/approval cycle,
paid fallback, safety downgrade or retry of a denied effect.

## Precedence and records

Later direct user instructions and actual holds govern. This plan plus current
release-campaign.md define scope and procedure; live LIT owns claims, findings, budgets,
releases and observed results. Role files add responsibilities and references add their
specific mechanics. A copied worktree AGENTS, roadmap, checkpoint, old audit, bottle or
historical ticket comment cannot restore superseded production scope, Gemini routing,
review panels, per-transition adoption receipts or status PRs. Preserve historical evidence
and actual denials. Apply an explicit supersession directly; hold only genuinely unresolved
conflicts at the affected action. Native continuity/current authority and measured
headroom remain required; fresh/changed substantial assignments retain admission.
A verified same-claim continuation begins useful work in the same turn under
context-policy, preserving honest inspect/admit results rather than ending solely
for a startup receipt. No routine central acknowledgment gate is created.

## Active delivery entrypoints

In the harness repository, `.harness/workflow-policy.json` and
`docs/delivery-policy.md` own selected-policy delivery. Legacy bodies in
`.agents/skills/context-save-lean/SKILL.md`,
`.agents/skills/codex-autonomous-loop/SKILL.md`,
`.agents/skills/roadmap-continue/SKILL.md`,
`.claude/skills/roadmap-continue/SKILL.md` and
`docs/governance/orchestration.md` cannot restore mandatory Gemini, second artifact
review, default review panels, duplicate full local suites, status PR cycles or
cleanup on the delivery path. Preserve recorded in-flight legacy obligations,
independent review, exact-candidate and own-main CI, findings/passes and denials.
The prior bounded entrypoint audit found inactive `tools/codex_loop.py` enforcement
for old main-sync/worktree-disposition gates. Keep inactive legacy state inactive;
do not initialize, repair, fabricate or delete loop state to make delivery pass.
These are cross-repository routing constraints, not a claim those external files
were changed or independently re-audited here. Apply any separate harness
entrypoint correction through its owned source/review path.
