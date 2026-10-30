# Workflow optimization adoption inventory

This is the WO-U01 baseline (plan WP-01; specification WS-01, WS-17, WS-18; WT-27
inputs). For each rule the `arhugula-trial-v1` profile would change, it records the
current carrier, the enforcer, how it is disposed of, how that is verified and where
rollback restores it from. It also byte-binds the protected root work that `main`
does not contain.

**Adoption state: `inactive`.** No gate is disabled and no activation receipt exists
(`O/.local/buford-loop/workflow-activation.json` is absent). WO-U23 re-bound every
row to the current bases and gave it a disposition (see WO-U23 reconciliation). That
section names the activation holds that remain. Until WP-17 activation, the existing
gates govern everything listed here.

Facts were read at 2026-10-23T22:46:14Z by claude-coder (session
`1c4c420e-3207-45b6-830b-c741708760cd`) against:

| Repository | Remote | Revision read |
| --- | --- | --- |
| `O` = `/home/robbo/Work/arhugula-omarchy` | `thestoryportal/arhugula-omarchy` | `origin/main` `4e9fc3b6a42b61516fb44121ce46e1afea5fd2f5`; the root checkout itself is on local `main` `fd03988` plus the protected changes below |
| `H` = `/home/robbo/Work/arhugula-build-eval` | `thestoryportal/arhugula-harness` | `origin/main` `91e76a4e22ffc0b013fa14a5d680d1c991f5a1e5`, the same revision the plan audited; the checkout is clean on `main` |

Governing artifacts, matched to the SHA-256 values recorded in LIT c12:
plan `09e264b4…96025e`, specification `e16b61e8…df5`, PRD `c0fbeab3…eac39`.
None of the three is in `O` `main` yet (see Protected root work).

## Required CI contexts and branch rules

Neither repository has a GitHub ruleset; the `rulesets` and `rules/branches/main`
endpoints both return an empty list. `main` is guarded by classic branch protection
in both repositories, with `strict: true` (the branch must be up to date) and no
required approving review count. Each required context below was matched to the job
`name:` that produces it at the revision read.

**O** (`.github/workflows/ci.yml`, Python 3.11, admins not enforced): `Ruff lint`
(job `lint`), `Python test suite` (job `test`), `Runtime and package smoke` (job
`runtime-smoke`). The jobs have no `needs:` edges and already run in parallel.

**H** (`.github/workflows/ci.yml` blob `98c5fde744f1`, Python 3.12, admins
enforced): 14 required contexts.

| Required context | Job | Waits on `changes` |
| --- | --- | --- |
| `pytest (all axis packages) — blocking` | `test` | yes |
| `ruff (lint + format) — blocking` | `lint` | no |
| `pyright (strict) — blocking` | `typecheck` | yes |
| `substitution ledger (tally gate) — blocking` | `substitution-ledger` | no |
| `CLAUDE.md citations (I-1 resolution gate) — blocking` | `claude-md-citations` | no |
| `arc ledger (tally gate) — blocking` | `arc-ledger` | no |
| `semantic overlay (drift gate) — blocking` | `semantic-overlay` | no |
| `tools/ test coverage guard + codex-loop tests — blocking` | `tools-test-coverage-and-codex-loop` | yes |
| `Q1 review gate (structured artifact) — blocking` | `q1-review-gate` | no |
| `Q3 evidence + closure gate — blocking` | `q3-evidence-and-closure-gate` | no |
| `merge-gate log consistency (C-HE-23 §2 reducer) — blocking` | `gate-log-consistency` | no |
| `Codex context guard (anti-rot gate) — blocking` | `codex-context-guard` | no |
| `split-brain ledger backstop — blocking` | `split-brain` | no |
| `clearance corpus (frontmatter gate) — blocking` | `clearance-corpus` | no |

Three H jobs are not required contexts: `classify diff (bookkeeping fast path)`
(`changes`), the `axis isolation — harness-<axis>` matrix and `coverage
(informational) — advisory at v1`. A second workflow, `x-al-3-guard.yml` (blob
`c6d68fac6237`), produces no required context. WS-10 work (WO-U09, WO-U10) must
keep every one of the 14 contexts produced, with the same failure semantics, before
it changes the graph.

## Carrier inventory

Columns follow the WP-01 interface. *Revision* is the Git blob prefix at the
revision read above for H, and either `main` or a protected working-file hash for O.
*Disposition* uses: **retain** (unchanged by the trial), **scope** (applies outside
the trial; the trial gets a narrower rule only under validated membership),
**retire-after-activation** (removed for trial units only once WS-17 activation
succeeds), **reuse** (an existing mechanism already meets the requirement) and
**conditional** (adopt only with the stated proof; otherwise retain). The rollback
source of every H row is its blob at `91e76a4`; for O it is the protected bytes or
`main` blob named.

### Root repository (O)

| Carrier | Revision | Old rule | Disposition | Scope | Enforcer | Verification | Rollback source | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `AGENTS.md`, `CLAUDE.md`, `docs/orchestration/{paired-lanes-framework,context-policy,communication,authorization,memento-current}.md`, `roles/*.md` | protected, differs from or absent in `main` (table below) | Startup route, measured admission, pointer delivery, review independence, no-HIL through normal controls | retain; the released c12 workflow already runs on these bytes | all lanes | read by each session; no code enforcer | WT-02, WT-03, WT-05 | protected bytes below; older `main` copies of AGENTS/CLAUDE/context-policy/communication/buford role | inactive |
| `docs/orchestration/session-control.json`, `launch-profiles.json` | protected, absent in `main` | Native identity, transcripts, ceilings, pause, notification target, model/effort | retain | all lanes | `ops/orchestration/session_context.py admit` reads the caller-supplied ceiling | WT-05, WT-07 | protected bytes below | inactive |
| `.promptctl/memento.conf` (untracked) | protected (table below) | Effective 225 000-token project ceiling | retain; Buford/operator owned | all Claude/Codex lanes | installed Memento `ceiling` reader | WT-07 | protected bytes | inactive |
| `ops/orchestration/loop.py` | protected, differs from `main` | `fingerprint(data, ticket, goal)` and `Loop.check(admission)` re-read the comment-sensitive authority token before a consequential step | reuse | all scheduling | `Loop.check` | WT-02 | protected bytes; `main` blob | inactive |
| `ops/orchestration/local.py` | identical to `main` | `start` raises `claim-conflict` and never passes `--take`; `dirty-tree-conflict` stops a dirty adapter checkout | reuse | all claims | `LocalAdapter.start` | WT-02 | `main` | inactive |
| `ops/orchestration/artifacts.py`, `records.py` | identical to `main` | `capture` fsyncs logs to the Mac share (refusing a guest-disk fallback) and publishes its receipt through `records.atomic_json`: temporary file, `fsync`, `os.replace`, and an unacknowledged replacement is marked uncertain | reuse | artifact receipts | `records.atomic_json`, `artifacts.require_mac_share` | WT-22, WT-23 | `main` | inactive |
| `ops/orchestration/review_budget.py` | protected, differs from `main` | Loads H `tools/review_loop_gate.py` and consumes its canonical admission rather than duplicating budget rules | reuse | review admission | H `review_loop_gate.py` via `canonical_admission` | WT-12, WT-28 | protected bytes; `main` blob | inactive |
| `ops/orchestration/auto_reset.py`, `goal_lineage.py`, `native_window.py`, `native_goal.py` | `auto_reset.py`, `native_window.py` differ from `main`; `goal_lineage.py`, `native_goal.py` identical | External reset receipts and goal lineage (`goal_observation`) | reuse; verify against an actual runtime receipt before relying on it (WS-17 §19.2) | session refresh | these modules | WT-05, WT-07 | protected bytes; `main` blobs | inactive |
| `ops/orchestration/startup.py`, `session_context.py` | identical to `main` | Startup budget and session admission measurement | reuse | all lanes | `session_context admit` | WT-05, WT-25 | `main` | inactive |
| `.git/hooks/pre-push` (installed, not tracked) | local install | Runs `lit sync push` on every `git push` | retain; public LIT sync is user-authorized and must stay on its normal control path | root pushes | installed Git hook | WT-30 | the installed hook file | inactive |
| `.github/workflows/ci.yml` | `main` | Three required contexts above | retain | all root PRs | GitHub branch protection | WT-13 | `main` | inactive |

### Product repository (H)

| Carrier | Revision | Old rule | Disposition | Scope | Enforcer | Verification | Rollback source | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CLAUDE.md` §12.2 / §12.2.1 | `42cd1892fe1e` | Every merge triggers a post-merge roadmap refresh PR, stopped by the "terminating refresh PR" clause | retire-after-activation for trial units only | validated trial membership | `tools/merge_door.py` and `CLAUDE.md citations` CI | WT-16, WT-27 | blob | inactive |
| `tools/hooks/safe-merge.sh`, `tools/merge_door.py`, `tools/roadmap_status_refresh.py` | `fed768c3e34c`, `d86ad0f7093d`, `453f99f3c4f3` | `safe-merge.sh` aborts before taking the lease unless the refresh producer supports `--emit-refresh-pr-json`; `merge_door.land()` runs the refresh after the merge | scope: retire only the trial refresh coupling; keep serialization, CAS/recovery, exact final binding and own-main CI | trial units | `merge_door.py` lease | WT-16, WT-27 | blobs | inactive |
| `.claude/skills/ship-pr/SKILL.md`, `.agents/skills/ship-pr/SKILL.md`, `.claude/skills/roadmap-continue/SKILL.md` | `1947ae34f517`, `b5f0a4e46e50`, `63b7bb32b44f` | `roadmap-refresh-post-<pr>` continuation and its branch close-out | retire-after-activation for trial units | trial units | skill procedure | WT-27, WT-29 | blobs | inactive |
| `.codex/notes/discipline-digest.md` line 39, `CONTEXT.md` (routes to `docs/governance/roadmap-protocol.md` §12.2), `AGENTS.md` lines 25–30 | `a52b847ea8e5`, `804b20860125` (protocol `952e39bb2aaf`), `ac8fc32e0374` | "Refresh must be the immediate next commit after a substantive merge"; AGENTS requires re-running `just codex-preflight` after long work and names historical orchestrator model shapes | scope: remove trial immediate refresh and obsolete timing/model assertions; keep product contracts and governance | trial units | session procedure; `Codex context guard` CI | WT-01, WT-10, WT-27 | blobs | inactive |
| `.codex/notes/deterministic-context-workflow.md`, `tools/codex_context_guard.py`, `tools/codex_loop.py` | `df0b94543db7`, `3a08cc02797c`, `1a4538cd0784` | Phase records and the anti-rot guard; WP-02/WP-03 add `workflow status`/`workflow check` beside them | scope: four trial boundaries replace duplicated phases; source identity, guidance, scoped verification and publication truth retained | trial units | `codex_context_guard.py`; `Codex context guard` CI | WT-01, WT-10, WT-11 | blobs | inactive |
| `justfile` (`codex-check`), `.agents/skills/codex-autonomous-loop/SKILL.md` step 7 | `cf5b85ca3da1`, `94a955ea0d8e` | `local_gate` runs `just codex-check`: sync, lint, format check, Pyright and six other checks, then non-e2e pytest | scope: expose narrow and full choices; named full-check exceptions retained | trial units | `just` recipe; skill procedure | WT-10, WT-11 | blobs | inactive |
| `.claude/settings.json`, `.codex/hooks.json`, `tools/hooks/{postedit-lint,stop-gate,stop-loop,permission-guard}.sh` | `5b542c90e0be`, `d49faa3bdf57`, `d7af3e179f9d`, `1be2c180a449`, `561e7f392178`, `16ac5c60135b` | Agent hook map: changed-file lint/format on edit, Stop gates, permission guard (17 hook scripts wired in `settings.json`) | retain lint/format, permission and native context guards; remove only a duplicate unchanged-subject check | trial units | the agent clients' hook runners | WT-10, WT-11 | blobs | inactive |
| `.githooks/pre-commit` | `55ac45602996` | Shipped advisory pre-commit | retain; **not installed** (`core.hooksPath` unset, `.git/hooks` holds only `*.sample`), so disabling it saves nothing | none in effect | none | WT-10 | blob | inactive |
| `tools/hooks/precmd-clear-cache.sh` | `23dd88e7edfa` | Deletes `__pycache__`/`*.pyc` before any pytest, pyright, `uv run` or `just test` command | retain: WO-U21 rejected narrower invalidation (see Cache and sync reuse disposition) | all commands | the agent hook | WT-24; `tools/hooks/test_precmd_clear_cache.sh` cases 4–7 | blob | retained |
| `justfile` (`codex-sync`), `uv.lock`, `uv run` | `cf5b85ca3da1`, `b165a567c5cb` | `codex-sync` runs `uv sync --all-packages`; every `uv run` checks the lock and environment before it runs | retain: WO-U21 added no separate reuse layer; the unlocked route's WS-15 gaps are retained (see Cache and sync reuse disposition) | all commands | uv | WT-15, WT-24 | blobs | retained |
| `tools/review_loop_gate.py`, `tools/merge_gate_log.py`, `tools/review_schemas/*.schema.json`, `.claude/skills/merge-gate/SKILL.md`, `.agents/skills/merge-gate/SKILL.md` | `d450e118bab2`, `ff8b76fba68f`, schema directory, `a17e15437468`, `84af30fc0c97` | Canonical review budget reducer, five-pass ceiling, merge-gate log consistency | reuse the reducer; adopt explicit concern coverage and correction progression without resetting accounting (source09 keeps its three spent passes) | all reviews | `review_loop_gate.py`; `Q1 review gate` and `merge-gate log consistency` CI | WT-12, WT-28 | blobs | inactive |
| `.github/workflows/ci.yml`, `tools/ci_bookkeeping_diff.py` | `98c5fde744f1`, `418238132d9c` | Required graph and bookkeeping fast path above | scope: parallel graph and one coverage execution, every required context preserved | all H PRs | GitHub branch protection | WT-13, WT-14, WT-15 | blobs | inactive |
| `tools/roadmap-audit/post-merge-refresh.sh`, `tools/roadmap-audit/session-start.sh`, `tools/hooks/prompt-context.sh`, `tools/hooks/lib.sh` | `1bb491d37d27`, `e13542889c6b`, `e660fa567798`, `52714acfcff5` | Agent hooks enforce the fixed point: `post-merge-refresh.sh` (wired at `.claude/settings.json:226` and `.codex/hooks.json:124`) emits "terminating refresh owed" after a substantive merge; `session-start.sh` (`settings.json:200`) and `prompt-context.sh` (`hooks.json:147`) apply the §12.2.1 one-ahead-HEAD exception; `lib.sh` holds their shared JSON shape | retire-after-activation for trial units, together with the CLAUDE.md §12.2 row; otherwise retain | trial units | the agent clients' hook runners | WT-16, WT-27 | blobs | inactive |
| `.claude/skills/two-lane/SKILL.md`, `.agents/skills/two-lane/SKILL.md`, `.codex/notes/leg-brief-template.md`, `.codex/notes/claude-codex-parity.md` | `94237dbf1501`, `8cc55ad7988e`, `a211489808a7`, `c875a687ecdc` | Instructions that require the terminating refresh as the immediate next commit (`leg-brief-template.md:56`) or as part of green CI parity (`claude-codex-parity.md:22`) | retire-after-activation for trial units; a stale copy left behind means migration is incomplete (WS-17 §19.1) | trial units | skill/brief procedure | WT-27 | blobs | inactive |
| `tools/arc_exit_report.py`, `tools/arc_metrics.py`, `tools/lanes_pilot.py`, `tools/prime_report.py`, `tools/branch_hygiene_batch.py` | `d9b90161bbb2`, `e3559464a957`, `b12e30a3a98a`, `7b9081ec2ba2`, `5db95a6d05dd` | Reporting and hygiene tools that assume a terminating refresh commit or `roadmap-refresh-post-<N>` branch exists after each merge | scope: accept a trial landing with no refresh; legacy behavior retained | trial units | the tools themselves | WT-26, WT-27 | blobs | inactive |
| `.harness/roadmap_status.md`, `Project_Roadmap_v1.md` | `b6be9b66ddc7`, `d2cf3dee5465` | Manual roadmap status and next action, rewritten by each terminating refresh | retire-after-activation for trial status (WS-01 §3.2: derive volatile trial status); static roadmap content maintained | trial units | the refresh producer and `session-start.sh` hash check | WT-01, WT-29 | blobs | inactive |
| Refresh fixtures: `tools/test_roadmap_status_refresh.py`, `tools/test_roadmap_status_consumers.py`, `tools/test_roadmap_ritual_smoke.py`, `tools/test_codex_context_guard.py`, `tools/test_merge_door.py`, `tools/test_codex_workflow_parity.py`, `tools/test_arc_exit_report.py`, `tools/test_branch_hygiene_batch.py`, `tools/test_ci_bookkeeping_filter.py`, `tools/hooks/test_lib.sh`, `tools/hooks/test_prompt_context.sh`, `tools/hooks/test_skill_exit_report.sh`, `tools/hooks/test_skill_two_lane.sh`, `tools/roadmap-audit/test_post_merge_refresh.sh`, `tools/roadmap-audit/test_session_start.sh` | `2222c80902da`, `ecf727906e2a`, `0c4835ac378b`, `cde4706f4bc5`, `48262e20c64d`, `e3fb0a98c214`, `b0c6c349a130`, `9197d10943a7`, `3b026f1f6334`, `48891e3ed908`, `e5bf29a9a66b`, `526d6bc2309e`, `5d08e324e8e2`, `92f32784fdec`, `9c8e73dc2514` | Assert refresh behavior. All run in required CI: the first three are named at `ci.yml:464-466`, `test_codex_context_guard.py` at `ci.yml:662`, the other Python files through `tools/codex-parity-check.sh` (`6699bd572926`), and every shell fixture through that script's glob at line 86 | scope: each retired rule is removed or trial-scoped in its fixture in the same change; legacy assertions retained for non-trial work | all H PRs | required CI contexts above | WT-27 | blobs | inactive |
| `tools/loop_cost_baseline.py` | `5779f7686c31` | Existing cost receipts | reuse as WO-U02/WS-16 input | measurement | none | WT-26 | blob | inactive |

Every other H file that names the refresh fixed point at `91e76a4` is a historical
design or evidence record under `.harness/`, `design-substrate/`, `docs/research/` or
`docs/diagrams/code-loop/`. These are retained unchanged and enforce nothing. The
`docs/diagrams/code-loop/` diagrams are static architecture, so they are updated
once activation changes the merge flow. The verifier re-runs this search and fails
on any match not cited above.

## Existing mechanisms marked for reuse

These already satisfy a requirement, so the units that touch them extend them
rather than replace them: comment-sensitive `fingerprint` and `Loop.check` (WS-02),
`LocalAdapter.start` claim-conflict and dirty-tree checks without `--take` (WS-02),
atomic receipt publication through `records.atomic_json` (WS-15), the H `review_loop_gate.py`
reducer reached through `review_budget.canonical_admission` (WS-09), and external
reset and goal lineage in `auto_reset.py`/`goal_lineage.py` (WS-04). LIT itself
remains the task record; no unit adds a second store.

## Protected root work

`origin/main` lacks most of the guidance the team runs on today. These working
files in the root checkout are protected: no unit may sweep them into its commit,
and no unit may assume `main` contains them. Hashes are SHA-256 of the bytes at the
read time; *state* compares them with the same path at `origin/main` `4e9fc3b`.

The active guidance is still being edited while the team runs on it (the framework
moved from v5 to v6 during this read). So these bindings name a retained snapshot,
not whatever is on disk later: an exact copy of every listed file is kept under
`O/docs/orchestration/implementation-evidence/wo-u01-claude-coder-1/snapshot/`. That
copy is also the rollback source for these bytes. A later on-disk change is new
protected work and needs its own binding.

The table below is the U01 record. WO-U23 binds the bytes of its inventory rows, as
observed at the file's `observed_at` time, in
`implementation-evidence/wo-u23-claude-coder/carrier-bindings.json`; where the two
differ, that file is the later binding.

| Path | State | Bytes | SHA-256 |
| --- | --- | --- | --- |
| `.codex/config.toml` | absent | 219 | `e72038d955b37cc34dbd58a9ae357a430e24cceb183fb01e1905298aa60378c6` |
| `.ignore` | absent | 227 | `b81e710759023fc9dea5cfc0e320c6e1224c267d9646745088e87739a2d103b0` |
| `.promptctl/memento.conf` | absent | 17 | `2a4f8ed2bcab4e0d56c34377ff7c009bf9d73ab3e9924572afa583e5f9eabbcf` |
| `:memory:.ses` | absent | 51 | `64c22436660805a3b3a369d8667b2e685a8193e5581f15c90bc3eb38197e5eeb` |
| `docs/diagnostics/01a0bdf2-bec8-71e1-946d-4ac8c3d0ce6c/case.md` | absent | 1976 | `3295f45f6b52f9741993c2ee90259bbac8d4993ec95dec8aac10e8bb8e950ac6` |
| `docs/diagnostics/01a0bdf2-bec8-71e1-946d-4ac8c3d0ce6c/report.md` | absent | 2702 | `7684fa8cd5357be23cac0a8bec43b06420c17dc535a9b4c793df07bacea24a82` |
| `docs/diagnostics/rtk-evaluation-2026-09-21.tar.gz` | absent | 8117 | `e8a58a6a344e879c84b952e81d6f6db67cd5f0664adfdd8f7dc83dc9a03ed528` |
| `docs/orchestration/authorization.md` | absent | 3806 | `45eb5e65102ec7457903e8189123f8dad73bec83ba60273cb08bf1b228a3fba4` |
| `docs/orchestration/launch-profiles.json` | absent | 1745 | `5e6033b2d9edc6db2924f2f825e823d7ba3f63961943c236587786cb73c94be1` |
| `docs/orchestration/memento-current.md` | absent | 4297 | `546aead8fe73c12d771387a961f73b3efb61bde538291497f318b2ce4f7dd886` |
| `docs/orchestration/paired-lanes-framework.md` | absent | 13085 | `2422eecc7b57aa8262cef188eb0fc860be46ad14320cfbfc3910a1acae3baf72` |
| `docs/orchestration/roles/claude-coder.md` | absent | 2124 | `f7837ea35b61d23cdcf99a3316b7b3291cfdcc4fc2fac624cee5dacb7c72db6b` |
| `docs/orchestration/roles/codex-reviewer.md` | absent | 2156 | `5cc823a3e0f02a216d91ba82d09d6e87384939cbfe0e6afa430f13f23526dc50` |
| `docs/orchestration/roles/facade-coder.md` | absent | 741 | `0d1371a66e716ca36fb26f647c2e35d668a25f510e3746b119f1bb186aeea339` |
| `docs/orchestration/roles/implementer.md` | absent | 440 | `7475a2df158973656e99adceeb4e26cba320638f486e4769d32403d028d95779` |
| `docs/orchestration/roles/reviewer.md` | absent | 1066 | `bb282eb193c986c25f51d1ba87666fc6499b36c534d2220cc9cd0ff343040adc` |
| `docs/orchestration/roles/runtime.md` | absent | 2079 | `fdb8e17352405baadd1218bf3a36bffa391ef7dd2ebf344b0869445b832eae8d` |
| `docs/orchestration/session-control.json` | absent | 2836 | `e2699f0991d522e5de993e5104f945d0d98f9f9d492cbd93554d5c87a5f03cb3` |
| `docs/orchestration/workflow-optimization-lit-index.md` | absent | 15227 | `774e619f6170c824e9ad2cfb3ab25c29f2553f1388aee2c95a37d8790856047c` |
| `docs/orchestration/workflow-optimization-prd.md` | absent | 53709 | `c0fbeab3f0a849b415d2ddeda5eeaf337d2d2bc715baa5569d167a98b66eac39` |
| `docs/orchestration/workflow-optimization-specification.md` | absent | 104455 | `e16b61e85a2d7afebe46b8e3fbf2b216945536705cb3b63cad023b819fc99df5` |
| `docs/orchestration/workflow-optimization-wall-clock-estimate.md` | absent | 13441 | `cb16d2cc65b8942efce076b288fb98044fc3269a403a4d9c3e5e077834d12206` |
| `docs/superpowers/plans/2026-10-22-workflow-optimization.md` | absent | 67016 | `09e264b4e7bf356664cd56541622633a5caf7fda29496d12bec387937d96025e` |
| `nvim.log` | absent | 132 | `bfb805d72e0dbb7c885e2ff7c971a569ae0fa5e4a6c22db6a468a354c716919f` |
| `ops/orchestration/arhugula-session-context.service` | absent | 536 | `fff81b478c00b1067cd8357ee1a631311c359e6f3b2321c0622a0a80daffd9f6` |
| `ops/orchestration/lane_launch.py` | absent | 11304 | `04856831f07c23f37ff6ea19e600af5e1b247994a648b4bbd5b226a4b6a629a8` |
| `tests/test_lane_launch.py` | absent | 15763 | `b046532ab1acf81da168b00e182e378efa5d8c5d5719be620b9161e34f57d51c` |
| `AGENTS.md` | differs | 5828 | `e800fc0f54f0ca9797c234acba14795458027d55a027435ab2a4f99a7605ac52` |
| `CLAUDE.md` | differs | 856 | `cc1aa4ed8b6c31c91bd8bd57914032a6b53d60debf7727d42711f192805cf28e` |
| `README.md` | differs | 2471 | `8e8e84912d3927aca94951beabe0a1820d8fb02a0eb06b1880dd3a7402358cc7` |
| `docs/orchestration/communication.md` | differs | 10105 | `5ae3379ce843351d514cb4a0383c17fc3711caa9613c444aafbec6e0b3819a52` |
| `docs/orchestration/context-policy.md` | differs | 10501 | `0dc12fde6adc6553700805ab29c739c9ba2acaddddc9f5daf8fe99360f4251f4` |
| `docs/orchestration/roles/buford.md` | differs | 1768 | `fa60cf17227100be6f1c20f7118e9466ed32b1a56a338c7e87bb6755ea0ed7ee` |
| `docs/orchestration/session-roster.md` | differs | 1068 | `f7b00d334aaa782eef0d06fdb4d872dd1394e0cc0261f40fb5333b9cbd6c0117` |
| `ops/orchestration/auto_reset.py` | differs | 51986 | `06d9713c2dff9e3bb1a9de64674b5aae3b7ec6fcd1f91e8dddde26d90888ee34` |
| `ops/orchestration/loop.py` | differs | 52665 | `f5fdfef081b518cb6eb9d018b60fb72e0251bbe946cab032f35e86766a78594d` |
| `ops/orchestration/native_window.py` | differs | 19001 | `24b149685abdb44f5b8b53669b8d53714a0314051399ab31faf98a3728e94108` |
| `ops/orchestration/review_budget.py` | differs | 5774 | `041ddb8bf5feaa2ca4924d084eac57d1d8cae20693893a77735799bbd3bd2ca4` |
| `tests/test_auto_reset.py` | differs | 78392 | `21f8636ae98316798c15ba20a68fbf454e6f021656552f1bdcb10e1be03e201c` |
| `tests/test_loop.py` | differs | 15329 | `2e81e8d34bd5db6fb9c383574e0a102011fce923aeb18041c254949b8091659e` |
| `tests/test_review_budget.py` | differs | 12645 | `834b5a55165415b4d93866ae585945753b2f66791ea0bc254fbc631580c4247d` |

The `.local/`, `.harness/` and `docs/orchestration/{implementation,review}-evidence/`
trees are retained evidence. They are excluded from this table and from any commit.

These modified or untracked files are byte-identical to `origin/main`, so they need
no landing: `ops/orchestration/artifacts.py`, `ops/orchestration/goal_lineage.py`, `ops/orchestration/local.py`, `ops/orchestration/native_goal.py`, `ops/orchestration/processes.py`, `ops/orchestration/records.py`, `ops/orchestration/runner.py`, `ops/orchestration/session_context.py`, `ops/orchestration/startup.py`, `tests/test_artifacts.py`, `tests/test_codex_worker.py`, `tests/test_goal_lineage.py`, `tests/test_isolated_lit.py`, `tests/test_local_adapter.py`, `tests/test_native_window.py`, `tests/test_process_census.py`, `tests/test_reset_corrections.py`, `tests/test_session_context.py`, `tests/test_startup_budget.py`, `tests/test_startup_recovery.py`.

The working tree also deletes 25 tracked historical handoff, plan and spec files
that are still in `origin/main` (`git status --porcelain | grep '^ D '`). The
originals are archived outside the checkout under the c12 manifest. Removing them
from `main` is a separate reviewed change.

**Dispositions.** Buford/operator owns these bytes; no per-file author record
exists beyond that.

- *Active guidance* (`AGENTS.md`, `CLAUDE.md`, `README.md`, the framework,
  context-policy, communication, authorization, memento-current, session-roster,
  session-control, launch-profiles, `roles/*.md`): retain in place. They must land
  through one reviewed root docs change before WP-17 activation relies on them. They
  are not a prerequisite for inactive WO-U02..WO-U16 work.
- *Governing artifacts* (the plan, specification, PRD, LIT index and wall-clock
  estimate): retain at the c12 hashes. They must land, or have their retained
  location recorded, before activation cites them from `main`.
- *Operational source* (`loop.py`, `auto_reset.py`, `native_window.py`,
  `review_budget.py` and their tests, plus the absent `lane_launch.py`,
  `test_lane_launch.py` and `arhugula-session-context.service`): the running
  orchestration differs from `main`. A unit that modifies one of these files bases on
  `main` and brings forward only the bytes it explicitly owns, with provenance and
  review. Landing those bytes is a real dependency of that unit.
- *Local client configuration* (`.promptctl/memento.conf`, the effective Memento
  ceiling; `.codex/config.toml`): Buford/operator policy. Retain, never commit; no
  worker edits them.
- *Unrelated local residue* (`docs/diagnostics/`, `.ignore`, `nvim.log`,
  `:memory:.ses`): retain and never commit. No adoption dependency.

## Prerequisites, holds and unknowns

- **Native identity.** `session-control.json` is the only current source of lane
  UUIDs; it changed during this read (Buford is now `01a16aee`, and every Codex lane
  now names a transcript, so `session_context admit` can measure it). LIT comments
  on WO-U01 and WO-U02 cite earlier UUIDs (claude-coder `eece00ad`, profile-coder
  `be2808b1`, Buford `01a16ac3` and `01a16ad8`); those are historical and grant
  nothing.
- **Queue delivery to a blank thread.** Buford's c12 comment `cmt-ed8dd3ef` defers
  the native blank-thread messaging repair. A Codex thread without a persisted
  rollout cannot be shown to have received a queue message.
- **Delivery.** No automatic LIT-comment-to-session delivery is configured
  (communication.md). A queued message is not evidence that the reviewer started.
- **Activation inputs (WT-27).** The activation receipt, accepted policy file
  (`H/.harness/workflow-policy.json`) and trial membership IDs do not exist yet.
  Activation stays held until each consumer accepts the same version, the trial
  refresh coupling is removed from fixtures and parity assertions, and post-main
  CI passes.
- **Not observed.** Mac shared-artifact-store availability, installed-runtime
  state and the Runtime lane's process handles were not inspected for this unit;
  their status is `unknown` here. WO-U18 (environment prerequisites) and WO-U19
  (installed evidence) own those facts.

## Cache and sync reuse disposition (WO-U21)

WO-U21 rejected both narrower alternatives. `precmd-clear-cache.sh` keeps deleting
every project `__pycache__` and `.pyc` before a test-shaped command, and no separate
sync-reuse record was added, so every `uv sync` and `uv run` still checks the
environment itself. Rejecting the reuse layer does not show that the sync commands H
actually runs meet WS-15; the gaps measured on that route are retained below. Scripts
and bounded receipts are in
`O/docs/orchestration/implementation-evidence/wo-u21-profile-coder/`; the raw logs
they point to are on the Mac artifact share.

**Bytecode invalidation.** A narrower method must never import a stale `.pyc`, and
every candidate tested did:

- CPython's default pyc records only the source's size and modification second, so
  it cannot see an edit that keeps both. Deleting only the pycs whose header
  disagrees with their source keeps serving the old code, and `python -B` reads the
  stale pyc as well.
- A renamed or deleted module still imports from a legacy `.pyc` left at its old
  path. A `__pycache__` entry never loads without its source.
- A session whose project directory is the parent can run tests inside
  `.worktrees/` or `.codex-worktrees/`. Pruning those directories, as
  `.claude/worktrees` already is, leaves edits there stale.
- Checked-hash pycs do catch the same-size edit, but CPython writes an ordinary
  timestamp pyc for any module first compiled later. They stay correct only if every
  command recompiles the whole tree first.
- Changing interpreter needs nothing: each interpreter reads only pycs carrying its
  own tag (checked for `cpython-311`, `cpython-312` and `cpython-314`).
- Workspace members import from source through editable `.pth` files in the
  worktree's own `.venv`. The hook clears that source's pycs, so an edit behind an
  editable install is seen. An installed copy in `site-packages` is a separate
  origin: the hook keeps its pycs, and a copy that shadows the source keeps loading.
  Which origin loads is decided by synchronization, not by the cache.
- No shared editable was found. At 18:05Z on 2026-10-24, 210 worktrees were
  registered with H; 41 had a `.venv`, and every path line in their `.pth` files
  (231, all uv workspace editables) pointed inside the worktree's own tree. The
  other 169, including both lanes nested under H `main`, had no `.venv`. H
  `main`'s own `.venv`, last written by uv 0.12.17, holds no workspace members.
  Worktrees created or synced later are not covered by that inventory. The hook
  would not clear an editable pointing outside the session's project directory;
  the contract does not cover that case, and its absence rests on WS-15's ban on
  environments shared between worktrees.

`tools/hooks/test_precmd_clear_cache.sh` now holds these cases as a 19-check
contract. It passes against the current hook on Python 3.11, 3.12 and 3.14 and fails
against the timestamp-selective, `-B`-only and worktree-pruning candidates. Keeping
caches would also save little. The hook itself took 128–205 ms. The 55-test
`harness-core` command took 3.2–4.9 s after clearing and 3.6–3.9 s with caches
kept, which is no measurable difference. Compiling all 1,223 project modules from
nothing, the worst case, took 7.9–9.8 s.

**Environment sync.** Two routes were measured in the owned worktree. On the locked
route, a warm `uv sync --all-packages --locked` checked all 110 packages in
73–150 ms and `uv run --locked` started in 86–195 ms. It refused a dependency the
lock did not contain, reinstalled a package whose metadata had been deleted from
`.venv`, and refused Python 3.11 under `requires-python >=3.12`.

H does not use that route. `just codex-sync` runs `uv sync --all-packages`,
`just codex-test` runs `uv run pytest`, and the CI setup steps run the same unlocked
sync; none passes `--locked`. Across two runs of this route a warm sync took
22–365 ms and `uv run` started in 32–378 ms. Given a changed dependency, both commands rewrote
`uv.lock` and succeeded instead of refusing. The added requirement was already a
locked transitive package, so no new install was exercised. `uv run` reinstalled a
deleted distribution before running. After `uv sync --package harness-core` removed
the other six members, `uv run` failed with `ModuleNotFoundError` until
`uv sync --all-packages` restored them. Both commands refused Python 3.11. uv
ignored the uv version recorded in `.venv/pyvenv.cfg`. With `pyvenv.cfg` deleted,
both commands still exited 0. `uv run` then started `.venv/bin/python` with the base
interpreter's prefix, outside the environment, and importing `harness_core` or
`yaml` failed with `ModuleNotFoundError`.

A separate reuse record would be a second copy of the environment's identity for no
measurable saving: warm checks already cost well under a second. None was added,
and no environment is shared between worktrees.

**What stays required.** The hook and its contract remain in force. A later
narrower proposal must pass the same contract and show a measured saving. WS-15
conformance of H's actual sync route is not established, and two gaps stay open
outside this unit's paths. First, the local and CI setup commands permit lock
mutation where WS-10 §12.4 requires `uv sync --locked`. Second, uv accepts an
environment without `pyvenv.cfg` as intact. Behavior under a different uv version
is untested; every probe ran uv 0.13.5. The gaps are filed as two tickets, both
routed by Buford and not yet released for implementation:
`arhugula-harness-trial-193.9kh.2rn.8a2` covers the local `just codex-sync` and
`codex-test` route and the missing `pyvenv.cfg` case, and
`arhugula-harness-trial-193.9kh.2rn.lh9` covers the setup steps in `ci.yml` and
`pr-metadata.yml`. The rejected cache and reuse alternatives produced no
implementation scope.

## WO-U23 reconciliation

WO-U23 (plan WP-17; WS-01, WS-17, WS-18; WT-27, WT-28) re-binds the rows above to
the bases it was released on and states the compatible inactive set. It does not
publish the activation receipt or activate any consumer.

| Repository | Base | Candidate |
| --- | --- | --- |
| `H` | `741e379cbf94bd9ddb6c158dd66028b6bb6ef8f9` | `47cac2854c794ac36fed267bf1af82d0510f8e6f` (branch `work/wo-u23-01a18c6b`) |
| `O` | `766d5a31472cf4d80a8be47890b3b00c0764104c` | the commit that carries this section (same branch name) |

`H` `main` moved to `b29c52df` after the base was taken. Integration reconciles that
at the Git gate.

Every carrier's blob at the U01 read, the H base and the H candidate is in
`implementation-evidence/wo-u23-claude-coder/carrier-bindings.json`. Each O row has
its O base blob and the SHA-256 of the bytes in the canonical root when the file was
generated (`observed_at` 2026-10-30T13:24:52Z), with their Git state against the root
checkout's own HEAD (`fd03988e`), the row's owner and its rollback disposition. The
Buford-owned control rows change with routing, so a later root can differ; rerun the
script before relying on a control hash. `rebind_carriers.py` in the same
directory re-derives the file and only reads. Dispositions:

- **retained**: legacy behavior stays in force.
- **replaced**: a landed or WO-U23 change now carries the rule.
- **retired**: the rule is removed. No row is retired before activation.
- **unaffected**: the trial does not touch the row.

| Inventory row | WO-U23 disposition | Consumer/fixture version at candidate |
| --- | --- | --- |
| O guidance (`AGENTS.md`, `CLAUDE.md`, framework/context/communication/authorization/memento-current, roles) | retained; still protected root work, owned through user-directed Buford edits. Rollback restores no root bytes; a restored set binds these hashes | root SHA-256 per path at `observed_at` in the bindings file, for example framework `76cfbaf8ce7e…`, `AGENTS.md` `7452f8dcab32…`. Framework, authorization, memento-current and most role files are absent from O base |
| O `session-control.json`, `launch-profiles.json`, `.promptctl/memento.conf` | retained; Buford/operator owned. Current routing and limits govern after any rollback | root SHA-256 at `observed_at` `f752c41f021e…`, `5e6033b2d9ed…`, `2a4f8ed2bcab…` (all absent from O base). `session-control.json` was `7c35f04badec…` in the pass-2 binding and `a84002bab7a5…` in the pass-3 binding; each change followed a Buford routing update |
| O `loop.py`, `local.py`, `artifacts.py`/`records.py`, `review_budget.py`, `startup.py`/`session_context.py` | retained (reuse) | O base blobs; current root SHA-256 and state in the bindings file |
| O `auto_reset.py`, `goal_lineage.py`, `native_window.py`, `native_goal.py` | retained; native refresh is an activation hold (below) | O base blobs; current root SHA-256 and state in the bindings file |
| O `.git/hooks/pre-push`, O `ci.yml` | retained | installed hook; O base blob |
| H `CLAUDE.md` §12.1/§12.2/§12.2.1 | replaced by WO-U23 `1fc5b5cb`, `f1664ac0` and `47cac285`: a trial-scope paragraph says the refresh audit governs legacy landings, that under a published activation the merge door rules on each landing, and that CI judges tracked membership instead of the receipt | `583b9b53fd96` |
| H `safe-merge.sh`, `merge_door.py`, `roadmap_status_refresh.py` | replaced by WO-U08: `merge_door.landing_profile` keeps the legacy refresh and gives a `trial` landing none, only under a matching activation | `2460a16d0a76`, `cfe756e94831`, refresh unchanged |
| H `.agents/skills/ship-pr` steps 4–7, `.claude/skills/ship-pr` refresh section, `.codex/notes/leg-brief-template.md` step 4 | replaced by WO-U23 `1fc5b5cb`: steps 4–6 and the Claude refresh section govern a legacy landing; the leg-brief gives the legacy and trial merge sequences separately | `79b118c095ac`, `04c956a9da77`, `b1b77602fac4` |
| H `.claude/skills/roadmap-continue` | retained; no immediate-next-commit sentence to scope | unchanged since U01 |
| H `.codex/notes/discipline-digest.md` | replaced by WO-U23 `96e28798`: immediate refresh scoped to legacy landings; "CI is ~75s, poll at ~80s" replaced by waiting on actual CI status | `a8368a7c59d3` |
| H `AGENTS.md`, `CONTEXT.md` | retained; AGENTS line 26 already allows "post-merge refresh or explicit non-applicability" | unchanged since U01 |
| H `codex_context_guard.py` | replaced by WO-U23 `a675d7d6`, `f1664ac0` and `47cac285`: under `workflow_policy.refresh_rule` = `trial` the drift check warns `ROADMAP_STATUS_TRIAL_UNPINNED` instead of the hard `ROADMAP_STATUS_DRIFT`; `refresh-rule` gives the hooks the same reading. CI cannot read the receipt, so its `--allow-roadmap-drift` owed lag walks back through tracked trial landings (`workflow_policy.tracked_trial_landing`: appended merge-gate-log rows that are all canonical finding records under that revision's schema, include a `finding` or `no_finding` verdict and bind one arc the policy at that revision enrolls) to the last verified refresh; consecutive trial landings pass, and a legacy landing in the chain still drifts. Without enrolled arcs or an activation it is unchanged | `570ce63759bd` |
| H deterministic-context note, `codex_loop.py` | retained | unchanged since U01 |
| H `justfile`, `codex-autonomous-loop` skill | retained; `justfile` changed only by `39e2878f` (setup lock-drift refusal), and the narrow/full trial choice is not exposed yet | `a7eb7026e9e5`; skill unchanged |
| H hook map and edit/Stop/permission hooks | retained (`stop-gate.sh` gained WO-U06's staged-content binding, `3081a9a1`) | `stop-gate.sh` `ce6dee5a33d0`; others unchanged |
| H `.githooks/pre-commit` | unaffected; still not installed | `e1694209e242` |
| H `precmd-clear-cache.sh`, `uv`/`codex-sync` | retained (WO-U21) | unchanged since U01 |
| H `review_loop_gate.py`, `merge_gate_log.py`, schemas, merge-gate skills | replaced by WO-U07 and WO-U23 O1/O2 (below); populating the policy and amending skill/schema legality are activation holds | `c47114468d72`, `ba9c1837388f`, schemas `3c1fcbe40210`; skills unchanged |
| H `ci.yml`, `ci_bookkeeping_diff.py` | replaced by WO-U09/WO-U10 | `ec356aea8e5f`, `ef06035f5189` |
| H refresh hooks (`post-merge-refresh.sh`, `session-start.sh`, `prompt-context.sh`, `lib.sh`) and their shell fixtures | replaced by WO-U23 `a675d7d6`: `hook_refresh_rule` reads the guard; under `trial` no refresh is owed, and an unreadable rule keeps the legacy message and names the failure | `cbfaca88221b`, `08db5f8a7441`, `fc9934411fdf`, `d0a9559c0cc1` |
| H two-lane skills, `claude-codex-parity.md` | retained; recipes for operator-invoked legacy lanes | unchanged since U01 |
| H `arc_exit_report.py`, `arc_metrics.py`, `lanes_pilot.py`, `prime_report.py`, `branch_hygiene_batch.py` | retained; they report and refuse nothing. A landing with no refresh reports `refresh_commit: null` and anchors on the merge | unchanged since U01 |
| H `.harness/roadmap_status.md`, `Project_Roadmap_v1.md` | retained until activation | `b812a9be3445`; roadmap unchanged |
| H refresh fixtures | retained legacy cases unchanged; WO-U23 adds the trial, unreadable-rule and consecutive-trial-landing cases to the guard and hook fixtures | per-file blobs in the bindings file |
| H `loop_cost_baseline.py` | unaffected | unchanged since U01 |
| H `.harness/workflow-policy.json`, `workflow_policy.py`, `workflow_boundaries.py`, `workflow_commit.py`, `workflow_evidence.py` (WO-U03 to WO-U06) | retained; `eligible_units` and `review_rules` are still empty. WO-U23 `a675d7d6` adds `activation_binds` (now shared with `select_profile`) and `refresh_rule`; `f1664ac0` adds `tracked_trial_landing` and `sha256_digest` | policy `edeeab80c8be`, `workflow_policy.py` `1c0afa8664f7` |
| **New:** H `tools/workflow_adoption.py`, `test_workflow_adoption.py`, registered in `codex-parity-check.sh` | added by WO-U23 `0a11453e`, corrected in `fda1aec5` and `f1664ac0`. `evaluate_adoption` returns only `inactive`, `prepared` or `validated`, never `active`. An `Inventory` cannot exist without a SHA-256 digest. The gate judges the inventory's required consumers against the parsed policy and that digest, so an omitted carrier, an unrelated consumer, a policy defect or another inventory version holds `policy_mismatch`; review, CI, own-main, active writers and release hold with their WS-18 codes. `plan_rollback` stays `rollback_required` and binds the prior `PolicyBinding` (policy and versioned activation binding), the prior carrier versions and a by-value ledger snapshot. Only `verify_rollback` returns `rolled_back`, after it observes those controls and carrier versions restored, reconciled intents and retained records, counters and authority. No input can replay an intent or restore a hold the user superseded | `4f1d17e2a55c`, `228f321572a5`, `97c59115d544` |
| **New:** H O1 (`0087cdbb`) | `merge_gate_log.trial_review_decision` takes no caller `doc_only`. It derives doc-only from Git with the reducer's one predicate, and permitted gate-row appends do not count toward it | `ba9c1837388f` |
| **New:** H O2 (`f28c9e92`) | under the trial reducer, a legacy one-lens closing pass 3 completes a cycle whose passes 1 and 2 were concern-complete; an incomplete pass 1 keeps its concerns missing | `test_review_loop_gate.py` |

**O3 disposition.** The trial policy needs a stable LIT unit ID bound to
review arc `trial-a3-source-09` (WS-01 §3.1). No original record supplies one. The
merge-gate log and `.harness/review-evidence/a3-contract-authority/` name the arc
only as "unit trial-a3-source-09". LIT `193.5i4` is a follow-up that carries notes,
not the arc's unit. Populating the policy is therefore an activation hold on that
missing binding; no ID was invented. The arc's three spent passes are already
canonical log rows, which the landed reducer counts once the arc is a member:

- pass 1: `06cf6778`/`007a5787`, complete
- pass 2: `af75b888`/`777cc833`, complete
- pass 3: `af75b888`/`224c30d7`, complete (one lens)

A legacy `rounds` entry repeating them would double-count. The only P1, from
gemini in pass 1, was rejected. The trial streak counts only passes after pass 1,
so the original streak is 0. The log has no stop row. The five-pass ceiling and
those three passes are unchanged.

**Activation holds.** WO-U23 implements none of these, and WO-U24 cannot activate
while any of them is open:

1. The O3 unit-ID binding above. Once it exists: populate `eligible_units` and
   `review_rules` from the originals, and amend the merge-gate skills,
   `review_schemas` and the launcher/emit/decision consumers together so the
   trial progression is legal.
2. The WO-U14 native refresh receipt, plus WO-U19 installed evidence for the final
   candidate.
3. Wiring `workflow_adoption.evaluate_adoption` and `verify_rollback` to real
   consumer, review, CI, own-main, writer and carrier-version facts, and publishing
   the receipt last (WO-U24). Its
   fixtures prove refusal; they are not live acceptance.

## Re-verifying this inventory

A reviewer can reproduce every fact above with read-only commands. Revisions:
`git rev-parse origin/main` in each repository. Protected-work states: for each
path, compare `sha256sum <path>` with `git show origin/main:<path> | sha256sum`.
Branch rules: `gh api repos/<owner>/<repo>/branches/main/protection` and
`gh api repos/<owner>/<repo>/rulesets`. H blobs: `git rev-parse
origin/main:<path>`. Required-context names: `grep -n 'name:'
.github/workflows/ci.yml`. A hash that no longer matches means that carrier changed
after the read time; re-read it before relying on its row.

The author's check script re-derives all of these at once and exits nonzero on any
mismatch: `python3 docs/orchestration/implementation-evidence/wo-u01-claude-coder-1/verify_inventory.py
<this file>` (retained in the root checkout's evidence tree, not in this commit).
