# Workflow optimization adoption inventory

This is the WO-U01 baseline (plan WP-01; specification WS-01, WS-17, WS-18; WT-27
inputs). For each rule the `arhugula-trial-v1` profile would change, it records the
current carrier, the enforcer, how it is disposed of, how that is verified and where
rollback restores it from. It also byte-binds the protected root work that `main`
does not contain.

**Adoption state: `inactive`.** No carrier has been changed, no gate disabled and no
activation receipt exists (`O/.local/buford-loop/workflow-activation.json` is
absent). Every row's status is `inactive` until its own unit lands. Until WP-17
activation, the existing gates govern everything listed here.

Facts were read at 2026-10-23T22:41Z by claude-coder (session
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
| `docs/orchestration/session-control.json`, `launch-profiles.json` | protected, absent in `main` | Native identity, ceilings, pause, model/effort | retain | all lanes | `ops/orchestration/session_context.py admit` reads the caller-supplied ceiling | WT-05, WT-07 | protected bytes below | inactive |
| `.promptctl/memento.conf` (`2a4f8ed2…`, 17 B, untracked) | protected | Effective 225 000-token project ceiling | retain; Buford/operator owned | all Claude/Codex lanes | installed Memento `ceiling` reader | WT-07 | protected bytes | inactive |
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
| `tools/hooks/precmd-clear-cache.sh` | `23dd88e7edfa` | Deletes `__pycache__`/`*.pyc` before any pytest, pyright, `uv run` or `just test` command | conditional: narrower invalidation only after WT-24 proof; otherwise retain | all commands | the agent hook | WT-24 | blob | inactive |
| `tools/review_loop_gate.py`, `tools/merge_gate_log.py`, `tools/review_schemas/*.schema.json`, `.claude/skills/merge-gate/SKILL.md`, `.agents/skills/merge-gate/SKILL.md` | `d450e118bab2`, `ff8b76fba68f`, schema directory, `a17e15437468`, `84af30fc0c97` | Canonical review budget reducer, five-pass ceiling, merge-gate log consistency | reuse the reducer; adopt explicit concern coverage and correction progression without resetting accounting (source09 keeps its three spent passes) | all reviews | `review_loop_gate.py`; `Q1 review gate` and `merge-gate log consistency` CI | WT-12, WT-28 | blobs | inactive |
| `.github/workflows/ci.yml`, `tools/ci_bookkeeping_diff.py` | `98c5fde744f1`, `418238132d9c` | Required graph and bookkeeping fast path above | scope: parallel graph and one coverage execution, every required context preserved | all H PRs | GitHub branch protection | WT-13, WT-14, WT-15 | blobs | inactive |
| `tools/loop_cost_baseline.py` | `5779f7686c31` | Existing cost receipts | reuse as WO-U02/WS-16 input | measurement | none | WT-26 | blob | inactive |

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
and no unit may assume `main` contains them. Hashes are SHA-256 of the working file
at the read time; *state* compares it with the same path at `origin/main`
`4e9fc3b`.

| Path | State | Bytes | SHA-256 |
| --- | --- | --- | --- |
| `.ignore` | absent | 227 | `b81e710759023fc9dea5cfc0e320c6e1224c267d9646745088e87739a2d103b0` |
| `:memory:.ses` | absent | 51 | `64c22436660805a3b3a369d8667b2e685a8193e5581f15c90bc3eb38197e5eeb` |
| `docs/diagnostics/01a0bdf2-bec8-71e1-946d-4ac8c3d0ce6c/case.md` | absent | 1976 | `3295f45f6b52f9741993c2ee90259bbac8d4993ec95dec8aac10e8bb8e950ac6` |
| `docs/diagnostics/01a0bdf2-bec8-71e1-946d-4ac8c3d0ce6c/report.md` | absent | 2702 | `7684fa8cd5357be23cac0a8bec43b06420c17dc535a9b4c793df07bacea24a82` |
| `docs/diagnostics/rtk-evaluation-2026-09-21.tar.gz` | absent | 8117 | `e8a58a6a344e879c84b952e81d6f6db67cd5f0664adfdd8f7dc83dc9a03ed528` |
| `docs/orchestration/authorization.md` | absent | 3806 | `45eb5e65102ec7457903e8189123f8dad73bec83ba60273cb08bf1b228a3fba4` |
| `docs/orchestration/launch-profiles.json` | absent | 1745 | `5e6033b2d9edc6db2924f2f825e823d7ba3f63961943c236587786cb73c94be1` |
| `docs/orchestration/memento-current.md` | absent | 4297 | `546aead8fe73c12d771387a961f73b3efb61bde538291497f318b2ce4f7dd886` |
| `docs/orchestration/paired-lanes-framework.md` | absent | 12426 | `ab71d82ac653e3c1e0b3037883f5fb7a071371b0c37168440f1e78b3d6be0aba` |
| `docs/orchestration/roles/claude-coder.md` | absent | 2124 | `f7837ea35b61d23cdcf99a3316b7b3291cfdcc4fc2fac624cee5dacb7c72db6b` |
| `docs/orchestration/roles/codex-reviewer.md` | absent | 2156 | `5cc823a3e0f02a216d91ba82d09d6e87384939cbfe0e6afa430f13f23526dc50` |
| `docs/orchestration/roles/facade-coder.md` | absent | 486 | `6df93c3c6c60c7e8696d3b68d958ed1e05a5346c3fd66eaf51de7f8060d94f35` |
| `docs/orchestration/roles/implementer.md` | absent | 440 | `7475a2df158973656e99adceeb4e26cba320638f486e4769d32403d028d95779` |
| `docs/orchestration/roles/reviewer.md` | absent | 1066 | `bb282eb193c986c25f51d1ba87666fc6499b36c534d2220cc9cd0ff343040adc` |
| `docs/orchestration/roles/runtime.md` | absent | 2079 | `fdb8e17352405baadd1218bf3a36bffa391ef7dd2ebf344b0869445b832eae8d` |
| `docs/orchestration/session-control.json` | absent | 2836 | `bf6135ec95f3b24039bcdbcbe991fe832317f9de0ccb5e90cebc6ce00a3b4e0e` |
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

Also protected and untracked: `.codex/config.toml` (219 B, `e72038d955b37cc34dbd58a9ae357a430e24cceb183fb01e1905298aa60378c6`)
and `.promptctl/memento.conf` (17 B, `2a4f8ed2bcab4e0d56c34377ff7c009bf9d73ab3e9924572afa583e5f9eabbcf`).
The `.local/`, `.harness/` and `docs/orchestration/{implementation,review}-evidence/`
trees are retained evidence. They are excluded from this table and from any commit.

These modified or untracked files are byte-identical to `origin/main`, so they need
no landing: `ops/orchestration/local.py`, `ops/orchestration/runner.py`, `tests/test_codex_worker.py`, `tests/test_isolated_lit.py`, `tests/test_local_adapter.py`, `ops/orchestration/artifacts.py`, `ops/orchestration/goal_lineage.py`, `ops/orchestration/native_goal.py`, `ops/orchestration/processes.py`, `ops/orchestration/records.py`, `ops/orchestration/session_context.py`, `ops/orchestration/startup.py`, `tests/test_artifacts.py`, `tests/test_goal_lineage.py`, `tests/test_native_window.py`, `tests/test_process_census.py`, `tests/test_reset_corrections.py`, `tests/test_session_context.py`, `tests/test_startup_budget.py`, `tests/test_startup_recovery.py`.

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
- *Unrelated local residue* (`docs/diagnostics/`, `.ignore`, `nvim.log`,
  `:memory:.ses`): retain and never commit. No adoption dependency.

## Prerequisites, holds and unknowns

- **Native identity.** `session-control.json` lists the current lanes. LIT
  comments on WO-U01 and WO-U02 cite earlier UUIDs (claude-coder `eece00ad`,
  profile-coder `be2808b1`, Buford `01a16ac3`); those are historical and grant
  nothing. WO-U02's assignee is still `be2808b1`, while the registered profile-coder
  is `a1c7950c`. Reconciling that belongs to profile-coder.
- **Codex admission metrics are unknown.** The `implementer`, `profile-reviewer`
  and `facade-reviewer` entries have `transcript: null`, so `session_context
  admit` cannot measure them. Buford's c12 comment `cmt-ed8dd3ef` defers the
  native blank-thread messaging repair; a Codex thread without a persisted rollout
  cannot be shown to have received a queue message.
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
