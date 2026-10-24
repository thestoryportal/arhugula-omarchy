# Operator-surface recovery decision (WO-U17)

**Decision:** every operator surface resumes a paused workflow through one path:
`api.resume(workflow, resume_handle=<workflow_id>)`. That call reads one exact
pause-journal record and hands it to the in-process `run_workflow` worker. There,
`DurableRootResume` claims the record in `ResumeClaimStore` and durably marks it
`started` before the workflow body runs. CLI, MCP and HTTP are thin adapters over
that path. None of them owns an operation ID, a claim, a pause store or an approval.
HTTP is not a separate surface: in the accepted contracts, HTTP is only the
transport the daemon's MCP server uses over a Unix socket.

Today only the Python API can resume. No CLI subcommand, MCP tool or HTTP endpoint
exposes resume. Those are gaps, listed below with owners. This record decides how
they must fit together. It implements nothing, and it does not clear or amend any
product contract.

Status: proposed by claude-coder for independent review under LIT
`arhugula-harness-trial-193.u9f.ytk`. A source review of this record is not
installed acceptance.

H revision: `46a3b74e5e5579aae4dadd081c84e3157ddd8b63`

## Authority used

The product's accepted heads are Runtime spec v1.134 (E38) and CP spec v1.124
(E39). Runtime v1.134 and v1.133 are deltas over the full v1.132 body, so the
Runtime citations below point into v1.132. Runtime v1.136 (E32) and the A4 fork
(E33) are Proposed. They are cited only to name the owner of a gap, never as
accepted behavior. All paths are in the product repo
`/home/robbo/Work/arhugula-build-eval`. Each citation is checked by
`tests/test_operator_surface_recovery_decision.py`.

## Behaviors

| Behavior | Decision | Evidence | Gaps |
| --- | --- | --- | --- |
| Operation identity | A resume is addressed by `workflow_id`, passed as `resume_handle`. The claim is keyed by the exact journal record that read returned, and a resumed run keeps the snapshot's `run_id`. Surfaces pass `workflow_id` through and create no IDs of their own. | E1, E30, E11, E31 | none |
| Admission owner | `DurableRootResume`, running inside the `run_workflow` worker, is the only admission owner. It claims through `ResumeClaimStore`. `api.run` already reaches that worker through the in-process MCP client, so a surface that calls `api.resume` reuses the same owner. Any other claim, lease or idempotency store is prohibited. | E5, E12, E13, E17 | none |
| Durable paused state | Paused state lives only in `JournalWorkflowPauseStore`, under the verified state placement. Surfaces read it through the existing accessor and `harness-inspect` enumeration, never through their own copy. The latest record is not a liveness claim, because the journal has no pause-resolved marker. | E18, E41, E42, E35, E36 | G5 |
| At-most-once resume | Only the `resume_handle` path is at-most-once: it claims and fsyncs `started` before the body runs, and it refuses a record that was already claimed. A caller-supplied `pause_snapshot` takes no claim, so no operator surface may expose it. Recovery of a claimed record goes through the audited admin route. | E2, E3, E4, E16 | G5, G6 |
| Typed refusal | Three refusal classes stay distinct. (1) `api.resume` argument and read errors, raised before bootstrap: `ResumeArgsError`, `ResumeHandleUnknownError` and `ResumeDirectChildHandleError`. (2) The root claim refusal `ResumeClaimRefusedError`, whose `reason` is a `RootResumeRefusal` (`placement`, `claim-refused`, `claim-busy`, `start-refused`). The worker records it on the request because typed errors do not survive the MCP text boundary, and `api.resume` raises it. (3) Child refusals after the body begins, typed `ChildResumeRefusal`. Surfaces present each class under its own fail class, never map one onto another, and never parse message text. No surface may present a refusal as success or as PAUSED. | E47, E48, E49, E50, E14, E15, E44 | G4, G9 |
| Inherited authorization | A child is admitted only through its parent's live started claim (`ClaimedChildAdmission`), and a grandchild only through its child. Operator approval enters a resume once, as `resume_context`. Surfaces pass that context through and never store approvals. | E46, E19, E20, E45 | G7 |
| Transport presentation | The per-surface part is presentation only. The CLI maps status to an exit code, including 5 for PAUSED. The daemon returns the `RunResult` JSON from `run_workflow`. HTTP is the daemon's MCP streamable-HTTP transport. | E21, E23, E8, E9, E24, E28 | G1, G2, G3, G8 |

## Gaps and owners

| Gap | What is missing | Owner | Held until | Evidence |
| --- | --- | --- | --- | --- |
| G1 | The CLI has no `resume` subcommand, and the admin CLI has no resume command. | Product Runtime spec, CLI contract C-RT-29 (§14.18), through a product design back-flow arc | A released product unit specifies CLI resume over `api.resume(resume_handle=...)` and satisfies the constraints below | E22, E29, E37 |
| G2 | The daemon registers one MCP tool, `run_workflow(workflow_id)`. Resume state is bound in process, not over the MCP wire, so a daemon client cannot resume. | Product Runtime spec, C-RT-35 resume and the daemon MCP server, through a product design back-flow arc | A released product unit defines daemon resume that admits through `DurableRootResume` | E8, E9, E10 |
| G3 | No HTTP operator surface exists in the accepted contracts beyond the daemon's MCP transport. Whether one should exist is undecided. | Product PRD and architecture owner; the user decides whether to open it | A user-released product decision says an HTTP operator surface exists; until then, none is built | E24, E28 |
| G4 | No accepted or proposed contract carries the root refusal classes (1) and (2) across the MCP wire, and the CLI exit-code table has no row for them. No carrier exists to reuse; this record does not choose one. | Product Runtime spec, C-RT-35 resume and the CLI exit-code table (§14.18.2), through a product design back-flow arc | A released product contract defines how each root refusal class crosses each surface | E15, E47, E48, E49, E50 |
| G9 | Child refusals (class 3) do not yet propagate to the root result. A4 proposes `RunResult.resume_refusal` for propagated child refusals only, not for the root classes in G4. | A4 typed resume refusal (U-RT-159 / U-CP-106) | A4 clears in the A3 then A5 then A4 order; until then no surface relies on `resume_refusal` | E32, E33, E34, E51, E52 |
| G5 | The journal cannot tell an outstanding pause from a resolved one (B-104, Reading D). Only the claim keeps resume at-most-once. | B-104 register row and its demand test | B-104 is resolved; until then, surfaces rely on the claim and never on the read | E35, E36, E2 |
| G6 | Engine-native durable-state pauses have no safe resume path. | Product Runtime spec, exit code 5 row (b) | A released product contract defines engine-native resume; until then, surfaces offer no resume for those pauses | E29, E40 |
| G7 | HITL approval through operator surfaces is not established. `api.run` declines elicitation, the CLI daemon client binds no elicitation callback, and production approval routes through Claude Code as the registered MCP client. An inherited gate change is refused only under the Proposed A4 work. | Product Runtime spec, HITL composer C-RT-18, and A4 for the inherited-gate refusal | A released product contract defines approval collection per surface without a surface-owned approval store | E6, E7, E25, E43 |
| G8 | The operator guide's exit-code table stops at 4 and omits 5 (PAUSED), which the CLI already returns. | Product docs (docs-only change) | Not a hold; any product docs change may fix it | E23, E26, E27 |

## Constraints on later product work

These constraints apply to every unit that adds or changes resume behavior on a
CLI, MCP or HTTP surface.

1. Resume through `api.resume(resume_handle=...)`, or a successor contract that
   still admits through `DurableRootResume`. Add no claim, lease, journal or
   idempotency store per surface.
2. Accept `workflow_id` and keep the snapshot's `run_id`. Create no operation IDs.
3. Do not expose the caller-supplied `pause_snapshot` path from an operator surface.
4. Keep the three refusal classes distinct and present each unchanged under its own
   fail class; never map an argument, handle or depth error onto a claim refusal.
   Do not assume a transport form for root refusals before G4 is resolved, or that
   A4's `resume_refusal` carries them.
5. Pass `resume_context` through once. Store no approvals.
6. Keep HTTP as the daemon's MCP transport unless the user opens G3.

Conflict check (WT-09): the product source at the pinned revision has one claim
store, `ResumeClaimStore` (E17), and one registered MCP tool (E8). No competing
claim or recovery store exists to reconcile.

## Evidence

| ID | Location | Literal |
| --- | --- | --- |
| E1 | harness-runtime/src/harness_runtime/api.py:1241 | `async def resume(` |
| E2 | harness-runtime/src/harness_runtime/api.py:1292 | `at-most-once admission (the` |
| E3 | harness-runtime/src/harness_runtime/api.py:1298 | `takes no claim and keeps the limit above.` |
| E4 | harness-runtime/src/harness_runtime/api.py:1297 | `manual recovery is the audited route` |
| E5 | harness-runtime/src/harness_runtime/api.py:569 | `async def _invoke_run_workflow_via_in_process_mcp(` |
| E6 | harness-runtime/src/harness_runtime/api.py:539 | `async def _refuse_elicitation_in_api_run(` |
| E7 | harness-runtime/src/harness_runtime/api.py:546 | `per Reading α` |
| E8 | harness-runtime/src/harness_runtime/lifecycle/mcp_server.py:295 | `@fastmcp.tool()` |
| E9 | harness-runtime/src/harness_runtime/lifecycle/mcp_server.py:297 | `workflow_id: str, ctx: Context[Any, Any]` |
| E10 | harness-runtime/src/harness_runtime/lifecycle/mcp_server.py:368 | `NOT over the MCP` |
| E11 | harness-runtime/src/harness_runtime/lifecycle/mcp_server.py:376 | `run_id = _resume_snapshot.run_id if _resume_snapshot is not None else uuid.uuid4().hex` |
| E12 | harness-runtime/src/harness_runtime/lifecycle/mcp_server.py:381 | `_admission: ResumeAdmission = state.get("_resume_admission", UNCLAIMED)` |
| E13 | harness-runtime/src/harness_runtime/lifecycle/root_resume_admission.py:126 | `class DurableRootResume` |
| E14 | harness-runtime/src/harness_runtime/lifecycle/root_resume_admission.py:67 | `class RootResumeRefusal(StrEnum):` |
| E15 | harness-runtime/src/harness_runtime/lifecycle/root_resume_admission.py:18 | `typed errors do not` |
| E16 | harness-runtime/src/harness_runtime/lifecycle/resume_claim_store.py:1 | `Crash-durable, at-most-once admission for one exact pause-journal record.` |
| E17 | harness-runtime/src/harness_runtime/lifecycle/resume_claim_store.py:534 | `class ResumeClaimStore:` |
| E18 | harness-runtime/src/harness_runtime/lifecycle/journal_workflow_pause_store.py:565 | `class JournalWorkflowPauseStore:` |
| E19 | harness-runtime/src/harness_runtime/lifecycle/claimed_child_admission.py:19 | `a grandchild is admitted through` |
| E20 | harness-cp/src/harness_cp/workflow_driver_types.py:244 | `class ChildResumeAuthority(Protocol):` |
| E21 | harness-runtime/src/harness_runtime/cli/app.py:353 | `@app.command("run")` |
| E22 | harness-runtime/src/harness_runtime/cli/app.py (absent) | `@app.command("resume")` |
| E23 | harness-runtime/src/harness_runtime/cli/app.py:58 | `EXIT_PAUSED = 5` |
| E24 | harness-runtime/src/harness_runtime/cli/app.py:152 | `_DAEMON_CLIENT_STREAMABLE_HTTP_URL = "http://127.0.0.1/mcp"` |
| E25 | harness-runtime/src/harness_runtime/cli/app.py:226 | `ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=30))` |
| E26 | docs/how-to-operate-runtime.md:84 | `Bootstrap, daemon connection/startup, or daemon MCP result error.` |
| E27 | docs/how-to-operate-runtime.md (absent) | `PAUSED` |
| E28 | design-substrate/Spec_Harness_Runtime_v1_132.md:1405 | `Daemon-client workflow invocation` |
| E29 | design-substrate/Spec_Harness_Runtime_v1_132.md:1431 | `subcommand exists yet` |
| E30 | design-substrate/Spec_Harness_Runtime_v1_132.md:3669 | `## §30 C-RT-35` |
| E31 | design-substrate/Spec_Harness_Runtime_v1_132.md:6496 | `Claim-store ownership and admission (AMENDED at v1.130).` |
| E32 | design-substrate/Spec_Harness_Runtime_v1_136.md:10 | `Status: PROPOSED — not cleared.` |
| E33 | .harness/class_1_fork_a4_typed_resume_refusal.md:3 | `Status: PROPOSED.` |
| E34 | .harness/class_1_fork_a4_typed_resume_refusal.md:21 | `RunResult.resume_refusal` |
| E35 | .harness/forward-register.yaml:4654 | `id: B-104` |
| E36 | .harness/forward-register.yaml:4671 | `status: registered_finding` |
| E37 | .harness/forward-register.yaml:4799 | `recourse has NO resume ADMIN-CLI command` |
| E38 | CLAUDE.md:58 | `(cleared 2026-10-04)` |
| E39 | CLAUDE.md:56 | `(cleared 2026-09-25)` |
| E40 | design-substrate/Spec_Harness_Runtime_v1_132.md:1431 | `engine-native durable-state pauses` |
| E41 | design-substrate/Spec_Harness_Runtime_v1_132.md:3761 | `durable-pause-state read accessor` |
| E42 | design-substrate/Spec_Harness_Runtime_v1_132.md:1602 | `durable-pause-journal ENUMERATION` |
| E43 | .harness/class_1_fork_a4_typed_resume_refusal.md:12 | `hitl-gate-config-changed` |
| E44 | harness-runtime/src/harness_runtime/lifecycle/claimed_child_admission.py:28 | `import ChildResumeRefusal, ChildResumeRefusedError` |
| E45 | harness-runtime/src/harness_runtime/api.py:1326 | `delivered one-shot to the resumed-step gate.` |
| E46 | design-substrate/Spec_Harness_Runtime_v1_132.md:27 | `permits a positional child only through a live` |
| E47 | harness-runtime/src/harness_runtime/api.py:197 | `class ResumeArgsError(Exception):` |
| E48 | harness-runtime/src/harness_runtime/api.py:210 | `class ResumeHandleUnknownError(Exception):` |
| E49 | harness-runtime/src/harness_runtime/api.py:244 | `class ResumeDirectChildHandleError(Exception):` |
| E50 | harness-runtime/src/harness_runtime/api.py:1342 | `RT-FAIL-RESUME-CLAIM-REFUSED` |
| E51 | design-substrate/Spec_Harness_Runtime_v1_136.md:40 | `(the returned arm).` |
| E52 | design-substrate/Spec_Harness_Runtime_v1_136.md:74 | `An existing Runtime refusal (for example` |
