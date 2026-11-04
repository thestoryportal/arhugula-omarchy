# Buford — approved gate-removal implementation in progress

Actual root session01a1a807-02cb-7c90-b83c-c4d09102b56d hands off at real capacity HOLD, not task completion. Last admit: latest-request-input328848, ceiling350000, remaining21152 <35000 required (budget20000/reserve15000); also active/session-not-complete. Native cwd/home/robbo, gpt-6.1-sol/high/on-request/workspace-write/auto_review. Goal NULL; preserve predecessor PAUSED full-goal provenance, do not create/resume/narrow/complete a goal through tools.

## Immediate objective and authority

The user directly complained that the workflow takes many hours and then asked which gates can be removed. At native2026-11-04T19:49:36.111Z they said: **“Recommendations approved. Durably implement these changes”**. Exact event: O/.local/release-campaign-20261103/buford-continuation-01a1a807/gate-removal-user-approval.json. Implement all seven approved recommendations, not just prose:

1. Remove repeated Buford ratification for witness/prose corrections preserving ratified behavior.
2. Permit isolated inactive code/test preparation while storage is established; storage still gates implementation acceptance and resume exposure (Runtimev1.137 B7 item4).
3. Default to ONE independent review; add a specialty reviewer only for a named risk, rather than primary + artifact + three mandatory lenses.
4. Verify corrections and affected regressions on the delta; full rereview only for actual changed scope/behavior.
5. Remove the separate mandatory roadmap refresh PR / its PR CI / its own-main CI cycle. Generate status from Git/LIT, or refresh at a milestone.
6. Focused local checks, with qualifying unchanged CI reused; no mandatory duplicate full local suite followed by equivalent remote CI.
7. CI gates landing/release while independent work proceeds in isolated worktrees, rather than stopping everyone.

Retain independent review, required CI on the actual candidate, installed acceptance, recovery proof, actual denials and full original scope. User approval authorizes changing the enforced workflow; do not invent private activation proof or restart the closed WO batch. No new general orchestrator, dashboard, ticket hierarchy or evidence-form project.

O=/home/robbo/Work/arhugula-omarchy is canonical authority/LIT cwd. H=/home/robbo/Work/arhugula-build-eval is linked product repo. New W=O/.worktrees/delivery-throughput-20261104, branch ops/delivery-throughput-20261104, basebe163134df2acdd94e0e0d83574ef6eb529cffa3. **WIP preservation commit02b8ec6322ae0ffb1fc0dc8e8306229fdfcfa74f**, clean, not pushed, no PR/frozen review/CI/merge. Resume this worktree; do not create another arc.

Claim LIT cmt-02250fa2-1660-4dc7-8c1e-50f15c86112e. Reservation delivery-throughput-20261104 is pending/gen1, lane arhugula-delivery-throughput-20261104-buford01a1a807 (persisted W/.harness/.lane-id), arc_type applying, reserved19:56:10Z; no head/base/attested tree/PR yet. Root owns workflow implementation paths; profile-coder's separate Runtime claim below stays protected.

## What is already durable

Canonical O AGENTS and campaignv3 implement items1/2 and batching/reuse guidance, local commit9d6edf2 (only those2 files). AGENTS sha256da4c029966aa46ead63651c7b4322aa5e459c8272d56a8333e3cb7321d1fc507; campaign0b0e59ebf848ee72e67ba7d589aa44f7aed2d7b2c4931c8b95806ae733b6f62f. Broader approval arrived AFTER that commit and supersedes the recommendations-only statement in LIT cmt-261bb5c5. Canonical sources still need all-seven consolidation/coherent adoption.

WIP changes9 files /173 additions,28 deletions:

- `.harness/workflow-policy.json`: review_rules.delivery = `single-independent-milestone-status-v1`.
- `tools/workflow_policy.py`: strictly parses that closed value; `streamlined_delivery` is distinct from trial activation. `refresh_rule` returns the existing unpinned/no-refresh rule for this tracked approved delivery setting without claiming a trial unit was activated. Existing empty-rule fixtures/legacy semantics remain.
- `tools/review_schemas/finding_record.schema.json`: new explicit `initial`/`correction` pass tags, retaining old1/2/esc/3 unchanged.
- `tools/review_loop_gate.py`: one primary (codex role, including Gemini wrapper) completes an initial/correction; accepted/open P1/P2 require correction, delta binds to last reviewed head; deliberate full correction may bind full diff; recorded initial history stays distinct from legacy cycles. Existing authoring preflight, real findings/dispositions, bounds and legacy records remain. `_cycle_request` selects new policy from tracked JSON.
- `tools/merge_door.py`: injected refresh_rule seam; new policy releases only after exact own-main success and publishes the existing identified landing receipt. Legacy refresh intents refuse instead of being silently abandoned. CLI profile `--with-refresh` returns `<kind> refresh|no-refresh`; explicit old/milestone continuations keep the legacy driver. Child refresh failure now exposes bounded stderr rather than an opaque CalledProcessError.
- `tools/hooks/safe-merge.sh`: consumes profile+refresh posture; holds policy-query failure exit via a separate assignment before `read`; same holder-bound wrapper remains the only merge path.
- Focused tests in test_review_loop_gate.py, test_workflow_policy.py and test_merge_door.py prove one reviewer, correction delta, no-refresh successful own-main, red own-main still blocked, malformed policy refusal and legacy selection retained.

These are **WIP, not reviewed/accepted/complete**. The shared skills, rootH guidance, report/status wording and all remaining consumers still need coherence work. No code should be called ready merely because a pure reducer passed.

## Exact verification and next concrete work

`MISE_UV_VERSION=0.13.5 uv run python -m pytest tools/test_review_loop_gate.py tools/test_workflow_policy.py tools/test_merge_door.py -q --tb=short` latest full run: **465 passed,2 failed** in11.32s. Logs `/tmp/buford-delivery-focused-tests.txt`.

One failure was a new test inserted before original happy-path assertions; fixed by moving those assertions back to their original test. Targeted rerun (`-k 'e2e_refresh_continuation or milestone_policy'`) now **2 passed,1 failed**,177 deselected, in6.55s. `/tmp/buford-delivery-refresh-tests.txt` identifies the remaining failure exactly:

```
test_e2e_refresh_continuation_through_real_producer_cli
BLOCKED: refresh producer failed: emit-refresh-pr: git fetch -q origin
+refs/heads/main:refs/remotes/origin/main failed: fatal: unable to access
'https://github.com/thestoryportal/arhugula-harness.git/': Could not resolve host: github.com
```

This is a provider-free legacy-recovery test whose Git shim is being escaped by the nested producer. **Fix hermeticity; do not enable network to make this fake test pass.** Its fixture at tools/test_merge_door.py around1900..2050 sets PATH/PYTHONPATH/shim state. The improved stderr now exposes the real cause. No production refresh action was retried.

Next:

1. Adopt current canonical Startup, verify actual bottle/native identity/model/effort/permissions/effective ceiling and completed admission, reconcile ONLY Buford routing. Read THIS bounded STATE, not the old1697 handoff. Preserve null goal.
2. Fix the one remaining test and rerun appropriate focused tests; run Ruff/format/Pyright on the actual edits. WIP has not been formatted yet. No full local suite was run or is claimed.
3. Complete user-approved source/policy adoption: single independent default review/correction CLI; risk-specific extra review only on named need; shared ship-pr/merge-gate guidance must stop instructing the old mandatory review stack; focused local checks + qualifying remote CI; permit independent work during CI. Update rootH CLAUDE targeted governance and Codex/Claude entrypoints coherently rather than leaving contradictory instructions.
4. Status/closeout: current guard warning `ROADMAP_STATUS_TRIAL_UNPINNED` incorrectly describes new milestone delivery as an activated trial. Correct source wording/consumers and tests. `arc_exit_report.py` still assumes missing refresh_commit may be owed; express intentional milestone/no-refresh delivery without claiming a missing obligation. Preserve actual current status from Git/LIT; merely tolerating a stale file is not generated current status. Avoid another tracked-status PR cycle.
5. Check in-flight legacy review behavior: `replay` currently seeds history from COMPLETED runs; with new policy and a partially delivered legacy pass it could demand initial instead of preserving that pass. Preserve existing in-flight history and spent budget. Check schema/row consumers, shadow/scoring/closure and wrapper integration with new tags, not only the pure tests.
6. Obtain ONE qualifying independent review on the frozen exact candidate (root authored code; existing Antigravity subscription wrapper is available/authorized for out-of-family review, no paid API fallback). Reviewer7d9 is primarily reserved for the author's Runtime claim and capacity-handing-off; do not silently take it over. No new review/pass was spent on this workflow WIP. Add specialty only for a named risk. Then required exact-head/base CI and own-main through safe wrapper; no raw gh merge/--admin and no protected-local-main sync.

W preflight passed before edits; required WIP codex-closeout exit0 before commit (output `/tmp/buford-delivery-wip-closeout.txt`), with OPEN_PRS_UNAVAILABLE (sandbox network), unpinned-status and overlay warnings. `git diff --check` passed. This is preservation, not acceptance. Graft absent as before; no blast-radius execution. Source work continues only after actual measured admission.

## PR1697 is DONE — do not rerun its delivery/metrics

PR1697 final1f927148 landed e8c798fb7e5ba97c3326fb98872de1e8c452b51e through safe wrapper, own-main41897900184 success. Immediate roadmap-only refresh1698 head61ed5e0e landed be163134df2acdd94e0e0d83574ef6eb529cffa3, own-main41899401965 success. Wrapper session23243 exit0 `released`, door null. Independent exact six pass3 bindings and merge tree65ec910d verified; approvals transfer gate-log-only from5d65d390. First claim10:43 to merge19:32 almost9h; PR open17:13 to19:32=2h19; no inferred speedup.

Mandatory context-save-lean checkpoint `/home/robbo/.gstack/projects/arhugula-build-eval/checkpoints/20261104-124959-pr1697-contract-landing-fixed-point.md`. `arc-close` ran ONCE, exit0, report **H/.harness/.checkpoints/arc-exit-report-pr1697.md** (main checkout, not oldW), checkpoint.confirmed=true. Metrics queued **/home/robbo/.gstack/projects/arhugula-v2/arc-metrics-queue/runtime-resume-supersession-contract.json**. No transcript flag/cost fabrication. Typeinventing, declared2 grouped decisions, empty experimental treatment cohort with explicit notes. Do not recapture1697 metrics. Drain that queue normally in the NEXT content PR if still owed. Report's five shared stale todo_for_human rows are NOT new human gates and must not restart completed1691 or closed WO work.

Protected H LOCAL main **b29c52dff8fef83fdc080dc0df7a885feb37079e stays untouched**; only fetch origin/main. Old contract worktree clean/retained. No cleanup on delivery path. Earlier1691/1693,1692/1694,1695/1696 fixed points already done.

## Peers, delivery, holds

Current canonical routing is session-control.json; verify before any delivery. Authorc1ee631a-ce42-4a69-8d17-cca4851bb052, Opus5.5/high/auto, existing Foot13877/Claude13881/address0xaaab06677ae0/stable18000004,225000/60000/50000. Root verified metadata, typed one short LIT pointer and separately Return via targeted Hyprland native input, no focus/composer clearing. **Exact native uptake cmt-261bb5c5 at19:49:30.993Z plus activity verified**; receipts O/.local/release-campaign-20261103/buford-continuation-01a1a807/throughput-author-{type,submit,uptake}.json.

Author v3 adoption/new claim cmt-750a2114-0cd7-46d9-b824-ac84c1de12b6: U-RT-160b-prep inactive refusal value/parser/projection/tests, W=O/.worktrees/runtime-resume-refusal-value-20261104, branchfeat/runtime-resume-refusal-value, basebe163134. Owns new resume_refusal.py/test_resume_refusal.py, ONLY new ResumePauseRecordSupersededError declaration in api.py, one register follow-up and gate rows. No CLI/exposure/journal changes. Reviewer reserved implementer7d9 or admitted successor at freeze. Author recorded active admit HOLD[paused,session-not-complete]86238; earlier completed Startup ALLOW85829 remains historical. Verify actual admission for new work; do not synthesize completion or treat global repair_paused as a release of unrelated scope. Author's three1697 P3 carry goes in its first commit; four1691 P3 notes are owed to next A4 PR, not this Runtime prep.

Reviewer7d9 actual capacity HOLD186844/225000, remaining38156<65000, goalnull, same Foot13878/Codex13882/address0xaaab066a74f0/stable18000003. Root nudge cmt-02250fa2 native queue01a1a822-0570-7770-bc70-fe06ceffb79a consumed19:56:08 (task_started), reviewer recorded capacity handoff cmt-8c0fdcae-489c-4931-a00f-40dadacb0704 and delivery-boundary cmt-3d4efae1. Own Memento next per that comment; last predecessor task_complete19:58:11.720Z had null last_agent_message. **No successor identity/admission is yet verified by root**; no new window/child or assumed replacement. Check live native state rather than reconstructing a supervisor.

Root native queue had TWO pending pointers before preservation: author cmt-750a2114 queue01a1a81e-a681-7533-becb-adcd83a68637; reviewer cmt-8c0fdcae queue01a1a823-14e3-78c0-8f2f-8454016f4459. Their LIT bodies were read once here. Root yielded and consumed the AUTHOR pointer as the next native input; no duplicate claim/review action taken. Exactly ONE reviewer pointer remained on the read-only queue check. Yield the next bounded turn to receive it before Memento; do not delete/replay pointers or reset to drain queue. A parked erroneous old reviewer772 pointer stays parked.

**New actual denial:** auto-review rejected a combined terminal capture + commit invocation: “captures another author's terminal, potentially recording sensitive screen contents without explicit user authorization.” CreateProcess rejected BEFORE effects. No screenshot was created, retried or worked around. The independent commit command and native metadata + targeted pointer delivery were separately approved and succeeded. Preserve the capture denial; it is not an input-delivery denial and does not reopen other denied effects.

Keep D1/D2/D3, facadef766 Memento denials, A5 PR1688 exact-delivery hold, root manual full-public LIT sync denial and all uncertain effects. No actor/transport/interpreter retry. LIT only cwdO with LIT_DISABLE_AUTO_SYNC=1; exact IDs from export; exit0 local durable comments despite mirror warnings, no manual sync. repair_paused=true, storageUNSELECTED/UNBOUND, A5/A4 Proposed, B314 original engine-native recovery OPEN, Q01v5 all38/122 NOT_RUN/NOT_READY, W5 definition-only; venue/restore unestablished. O unrelated dirty/deleted/untracked work protected; only explicit owned files may be staged.

Full original objective persists: complete the user-accepted Trial193 campaign, all38 original acceptance rows/122 criteria across full supported scope, independent six-category decision on one exact integrated candidate with required review/CI/main/post-main/installed/operating/recovery evidence and runbooks. Current native goalNULL; no --goal in Memento. Own installed direct finalize-session `-- 'message'` via normal escalation ONCE. On failure/denial/uncertainty stop; no replay or alternate route without controlling direction.
