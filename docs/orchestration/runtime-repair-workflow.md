# Deployed runtime repair workflow

User-approved September 22, 2026. This is operator-managed coordination in four visible native windows, not evidence that Arhugula itself owns persistent coding sessions. It supersedes the unchanged-only restriction for separately identified repairs, not the immutable baseline record.

## Roles and routing

| Visible lane | Default model / effort | Owns |
| --- | --- | --- |
| Buford, orchestrator | GPT-6 Sol / medium | Scope, provenance, deployment preparation, acceptance, context management |
| Codex, implementer | GPT-6 Sol / medium | Bounded branch edits and focused RED/GREEN tests |
| Claude, reviewer | Sonnet 5 / medium; Opus high for named difficult reviews | Independent pinned source/test review; no product writes |
| Claude, runtime tester | Sonnet 5 / medium | Actual isolated deployed-runtime scenarios and retained evidence; no product writes |

Use Sonnet for routine reviews when appropriate, Opus for difficult lifecycle/concurrency/security findings. Escalate the implementer only for a demonstrated reasoning need. Operator models and models exercised inside the runtime are separate selections. Use subscriptions for these agent sessions; no automatic paid API fallback.

## Loop and evidence

1. Buford selects an existing finding and its baseline reproducer. Preserve `/home/robbo/Work/arhugula-trial` at `87c2981719fc54760fd69caef0cffa4ee94e753a` and its recorded failures.
2. Give Codex one bounded assignment on a separate deployment-derived repair branch. Specify owned paths, expected behavior, exclusions and focused verification. No build-repo corpus or unshipped code.
3. Pin the writer's exact revision or file hashes. Claude reviews that immutable delta and the relevant tests. Buford relays findings to Codex; repeat corrections, tests and review until clear. A review verdict is not runtime acceptance.
4. Buford builds/deploys the reviewed revision into a distinct evaluation location using shipped packaging instructions. Record source revision, artifact hash, install path, import/executable origins, config and context sources. Do not call an editable candidate-source run a fresh packaged deployment.
5. The runtime tester receives a bounded scenario, expected outputs, time/cost limits, cleanup targets and evidence directory. Run the actual deployed CLI/daemon/provider path. Test suites are supporting evidence, not a substitute. Record observed output and errors, even when exit status is zero.
6. Buford checks retained artifacts. Runtime failures return to Codex, then independent review and another deployment retest. Close the finding only for the version and behavior actually verified.

The append-only `/home/robbo/Work/arhugula-trial/evaluation/findings.log` remains the evidence record; Buford appends lane-attributed results. Use short handoff pointers, not repeated log dumps. VM work does not merge main. No live device actions, stale AWS credentials or newly billed infrastructure without applicable authority.

When tempted to say “tests and review are green, ship it,” check for the deployment artifact and runtime witness. If either is missing, runtime acceptance is missing. When a candidate passes, retain the baseline failure: they are different versions, not contradictory observations.

## Context lifecycle — all four lanes

Follow [context-policy.md](context-policy.md) for role loading, measured admission,
model routing and same-window refresh. It supersedes the former 50%/65% thresholds
and unknown-capacity 100k fallback. Current pause and session identity are in
session-control.json. During the optimization ticket, repair orchestration is paused.

## Current handoff anchors

Existing reviewed candidates, not baseline fixes: OpenAI wire repair `201d50ab7a4cac91691a7ca4999ad93fe27a4dd2` in `/tmp/arhugula-runtime-repair-openai`; memory close `4adce380106620d58fcf3d883fe5fe2c14da8f9c` in `/tmp/arhugula-runtime-repair-memory-close`. Reverify before reuse; do not rerun their completed source reviews without a changed scope.

Unimplemented dispatch branch: `/tmp/arhugula-runtime-repair-dispatch`, previously clean at baseline. Latest native active-shutdown failure: `/tmp/arhugula-baseline87-active-drain.SZvEJO`. The client timed out after daemon exit; exact causal chain is not yet proven. These are context anchors, not concurrent writer assignments.
