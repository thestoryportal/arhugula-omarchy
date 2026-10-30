# WO-U23 author evidence (claude-coder)

LIT: `arhugula-harness-trial-193.99c.mn6`. Author: claude-coder. Native
`40f8274e-57a1-4f38-8271-f0dd600f4c7f` worked to H `f28c9e92`, then handed off at
its ceiling to `1545f6e8-049b-4104-a364-a10f77964dbb`, which wrote `3cae3282` and
this evidence. Reviewer: implementer `01a18c54`. The state is inactive; no
activation receipt was published.

Raw logs are on the Mac share in `/mnt/mac/arhugula-artifacts/wo-u23-claude-coder-40f8274e/`.
All pytest runs used the H venv Python on the H candidate's `tools/`.

| Check | Raw log | Result |
| --- | --- | --- |
| O1 suites | `o1-pytest.log` | 306 passed |
| adoption gate | `adoption-pytest.log` | 15 passed |
| context guard after the digest edit | `context-guard-pytest.log` | 105 passed |
| affected set at `3cae3282`: `test_merge_gate_log`, `test_review_loop_gate`, `test_workflow_adoption`, `test_arc_exit_report`, `test_codex_workflow_parity`, `test_codex_context_guard`, `test_merge_door`, `test_workflow_policy` | `u23-affected-pytest.log` | 810 passed, 12 failed |
| skill/carrier shell fixtures (`tools/hooks/test_skill_*.sh`, `test_loop_lib.sh`) | `carrier-hooks.log` | all `rc=0` except `test_loop_lib.sh` (148 passed, 2 failed) |
| `test_loop_lib.sh` at H `main` `b29c52df` | `loop-lib-baseline-741e379c.log` | the same 2 failures |
| ruff check, ruff format, pyright on changed tools | `u23-lint.log` | ruff clean; `workflow_adoption.py` 0 pyright errors |

The 12 pytest failures are all `test_codex_workflow_parity` setup-recipe cases.
Each one fails because the local mise shim has no `just` version ("No version is
set for shim: just"). WO-U23 does not touch `justfile`, `uv.lock` or that test.

The 2 `test_loop_lib.sh` failures are lane-precedence cases. They reproduce on H
`main` without WO-U23's changes, so WO-U23 did not cause them.

On pyright: the CI pyright include does not cover `tools/`. The O1 hunk adds one
`rw._git` reportPrivateUsage, the same pattern the module already uses on lines
825, 839 and 846.

`carrier-bindings.json` is the output of `rebind_carriers.py <H> 91e76a4e… 741e379c… <H candidate> <O> 766d5a31… /home/robbo/Work/arhugula-omarchy`
(regenerated for passes 2 and 3; see below).
The source09 reducer replay used the real `.harness/merge-gate-log.jsonl` rows at
the H candidate. Passes 1, 2 and 3 each replay as complete, and pass 3 closes the
cycle.

## Pass-2 correction (findings F1–F4 of pass 1)

Native `629aacdb-a86b-41bb-94f4-856e43ccbf16` took over from `1545f6e8` at its
ceiling and wrote the correction. H candidate `fda1aec5f08b650e30b02b106f3db770a83070b9`
(commits `a675d7d6`, `1fc5b5cb`, `fda1aec5` on `3cae3282`). Raw logs are in
`/mnt/mac/arhugula-artifacts/wo-u23-claude-coder-40f8274e/pass2/`.

| Finding | Correction |
| --- | --- |
| F1 | `workflow_policy.refresh_rule` (built on `activation_binds`, which `select_profile` now shares) reads `trial` only under an activation of the tracked policy. The guard's drift check, its new `refresh-rule` command and the three refresh hooks consume it. `CLAUDE.md` §12.1/§12.2, both ship-pr carriers and the leg-brief sequence are scoped to legacy landings. Without an activation every enforcer behaves as before. The guard's CI step cannot see the private receipt; that is activation hold 2 |
| F2 | `evaluate_adoption` judges the inventory's required consumers against the parsed policy and inventory digest. New fixtures: omitted required carrier, unrelated-only consumer, policy defect, another inventory version |
| F3 | `plan_rollback` stays `rollback_required`; only `verify_rollback` returns `rolled_back`, after observed restoration, reconciled intents and retained records, counters and authority. The snapshot is by value; a fixture mutates the adopted ledger after planning |
| F4 | each O row now has its current root SHA-256, Git state against the root HEAD `fd03988e`, owner and rollback disposition |

| Check | Raw log | Result |
| --- | --- | --- |
| affected pytest at `fda1aec5` (20 modules: review/gate log, adoption, arc exit, parity, guard, door, policy, finding record, boundaries, commit, governance router, citation resolver, axis pins, artifact heads, refresh classes, roadmap status refresh/consumers/ritual, branch hygiene) | `u23-pass2-affected-pytest.log` | 1367 passed, 1 skipped, 20 failed |
| the same failing modules at the pass-1 head `3cae3282` (scratch clone) | `baseline-3cae3282.log` | same failures |
| all `tools/hooks/test_*.sh` and `tools/roadmap-audit/test_*.sh` | `shell-fixtures.log`, `sh-*.log` | rc=0 except `test_lane_init.sh` (2), `test_loop_lib.sh` (2), `test_permission_guard.sh` (1), all identical at `3cae3282` |
| ruff check/format, pyright, `bash -n`, `git diff --check` | `u23-pass2-lint.log` | clean; shellcheck is not installed on this host, so the hook edits are not shellchecked |

The 20 pytest failures are 12 `test_codex_workflow_parity` setup recipes (no
`just` version for the mise shim), 6 `test_workflow_commit` cases ("the uv
interpreter identity is unavailable") and 2 `test_branch_hygiene_batch` recipe
cases. None of these modules' subjects changed in this correction.

## Pass-3 correction (findings F1–F4 of pass 2)

Native `d19ad720-b5c8-429d-94a7-f269c814eeba` took over from `629aacdb` at its
ceiling and wrote this correction. H candidate `f1664ac032d6787dfb873bce6fb7e4f0205329f2`
(one commit on `fda1aec5`). Raw logs are in
`/mnt/mac/arhugula-artifacts/wo-u23-claude-coder-40f8274e/pass3/`.

| Finding | Correction |
| --- | --- |
| F1 | Pass 2's activation hold 2 is resolved without a new activation binding. WS-01 §3.1 already says CI "verifies tracked membership, the unit/arc bindings in the canonical review records and the policy at its checked-out revision". `workflow_policy.tracked_trial_landing` is that test: a squash landing whose appended `.harness/merge-gate-log.jsonl` rows bind exactly one arc the policy at the same revision enrolls. The guard's caller-gated owed lag (`--allow-roadmap-drift`, CI only) now walks back through such landings to the last verified refresh. Consecutive trial landings pass; a legacy landing in the chain, a two-arc or unenrolled landing, a rewritten log or an unparseable policy still drift. Session-start and preflight keep the receipt-bound rule. `CLAUDE.md` §12.2 says so |
| F2 | `Inventory` requires a SHA-256 digest (`workflow_policy.sha256_digest`), so the blank-digest probe now raises `PolicyError` naming `inventory.digest` |
| F3 | `plan_rollback` binds a `PolicyBinding` (policy plus versioned activation binding; blank identities refuse). `verify_rollback` takes the observed binding and stays `rollback_required`, with `controls not restored`, when it is absent or different |
| F4 | `carrier-bindings.json` regenerated against the protected root at `observed_at` 2026-10-30T12:48:13Z. `session-control.json` is now `a84002bab7a5…`. It was `7c35f04badec…` in the pass-2 binding, which stays in O `04bd41cb`. The inventory now calls these observed hashes, not current ones, because Buford's control rows change with routing |

| Check | Raw log | Result |
| --- | --- | --- |
| new guard fixtures against the pass-2 owed-lag code (red proof), then the guard, policy and adoption suites on the candidate | `u23-pass3-red-proof.log` | the consecutive-trial and trial-then-legacy cases fail on the old code; 204 passed on the candidate |
| whole `tools/` pytest at `f1664ac0` (`--continue-on-collection-errors`) | `u23-pass3-tools-pytest.log` | 4380 passed, 4 skipped, 36 failed, 7 collection errors |
| the 16 failures outside pass 2's set, at `fda1aec5` (scratch worktree, since removed) | `baseline-fda1aec5-extra-modules.log` | the same 16 failures |
| ruff check/format on the changed tools, pyright on `workflow_adoption.py`/`workflow_policy.py`, `git diff --check fda1aec5..f1664ac0` | `u23-pass3-lint.log` | clean |

The 36 failures are pass 2's 20 plus 16 in modules that pass 2 did not run
(`test_arc_close_recipe`, `test_b104_installed_public_witness`, `test_codex_loop`,
`test_loop_status_isolation`, `test_merge_gate_emit_all`, `test_r500_multitenant_selfhosted`,
`test_tools_test_coverage_guard`). All 16 fail the same way at `fda1aec5`. The 7
collection errors import workspace packages (`harness_as`, `harness_runtime`) that the
eval venv does not install. No shell hook changed in this correction, so pass 2's
shell receipts still cover the same inputs.

## Pass-4 correction (finding F1 of pass 3)

Native `94d7c2a3-9e99-4b98-9ce3-9abed6bcd3af` took over from `d19ad720` at its
ceiling and wrote this correction. H candidate `47cac2854c794ac36fed267bf1af82d0510f8e6f`
(one commit on `f1664ac0`). The reviewer accepted F2–F4 at pass 3, so no O or H change
touches them. Raw logs are in
`/mnt/mac/arhugula-artifacts/wo-u23-claude-coder-40f8274e/pass4/`.

| Finding | Correction |
| --- | --- |
| F1 | The CI owed-lag walk now counts a landing as a trial landing only when every row it appends to `.harness/merge-gate-log.jsonl` is a canonical finding record under `tools/review_schemas/finding_record.schema.json` at the landing's own revision, and at least one row is a `finding` or `no_finding` verdict. The pass-3 probe row `{"arc_id":"wo-fx","record_kind":"bogus"}` no longer qualifies, and neither does a valid row with no verdict (for example `reviewer_unavailable`), an extra key, a malformed `ts`, a boolean `round_n` or a revision without the schema. `workflow_policy.tracked_trial_landing` still decides enrollment from the resulting arc set. `CLAUDE.md` §12.2 states the narrower test |

CI runs the guard on `/usr/bin/python3`, which has no `jsonschema`, so the guard cannot
call `finding_record.validate`. It instead evaluates the tracked schema for exactly the
keywords that schema uses (`type`, `enum`, `required`, `properties`,
`additionalProperties: false`, `minLength`, `pattern`, `minimum`) and rejects a schema
containing any other keyword. The code marks this as a `[LAW:single-enforcer]` exception.
`finding_record.validate` still owns write-time validity; its extra semantic checks are
not repeated in the guard.

`carrier-bindings.json` is regenerated for H `47cac285` at `observed_at`
2026-10-30T13:24:52Z. Only the `CLAUDE.md`, `codex_context_guard.py` and
`test_codex_context_guard.py` candidate blobs changed, plus the root `session-control.json`
hash (`f752c41f021e…`), which Buford's routing of the reviewer successor changed after
12:48Z. The adoption inventory carries the new H candidate, blobs and observation.

| Check | Raw log | Result |
| --- | --- | --- |
| the pass-4 guard tests against the pass-3 guard `f1664ac0`, with only the schema-path constant the fixture reads added | `u23-pass4-red-proof.log` | the 8 new F1 tests fail; the other 14 selected tests pass |
| guard schema evaluation against `jsonschema.validate`, and a stdlib-only run under `/usr/bin/python3 -I` | `u23-pass4-parser-probes.log` | no disagreements across 4,195 live log rows and 213 mutations. Under the system interpreter a live `no_finding` row yields its arc, the probe row yields none, and `jsonschema` is never imported |
| whole `tools/` pytest at `47cac285` (`--continue-on-collection-errors`) | `u23-pass4-tools-pytest.log` | 4388 passed, 4 skipped, 36 failed, 7 collection errors. The 36 failures are the same tests by name as at pass 3 |
| ruff check/format, pyright on the guard with the same `f1664ac0` config, `git diff --check` | `u23-pass4-lint.log` | ruff clean. Pyright reports 156 errors against 162 at `f1664ac0`, none in the changed range. Diff check clean |

## Pass-5 correction (finding F1 of pass 4)

Native `94d7c2a3-9e99-4b98-9ce3-9abed6bcd3af` wrote this correction. H candidate
`1177ec15fe995ab098aae7ec1bfa65bd734d5d73` (one commit on `47cac285`). This is the last
of the five original review passes. Raw logs are in
`/mnt/mac/arhugula-artifacts/wo-u23-claude-coder-40f8274e/pass5/`.

| Finding | Correction |
| --- | --- |
| F1 | Pass 4's schema-subset parser accepted rows the canonical writer refuses, such as a `no_finding` row timestamped `9999-99-99T99:99:99Z`. The subset evaluator is deleted. `finding_record.admit_appended` now exposes the writers' own append contract (`validate` plus the prior-row invariants, in log order), and the guard's trial walk admits appended rows only through it. Rows a writer would refuse no longer qualify: an impossible timestamp, a `finding_id` that disagrees with its producer, or a reused `finding_id` that changes an earlier row's arc |

The contract needs `jsonschema`, which `/usr/bin/python3` lacks. Only
`--allow-roadmap-drift` callers now walk trial landings (`derive(trial_membership=…)`),
and the walk loads the contract only once the policy at that revision enrolls an arc.
CI's guard step and `just codex-context-check-ci` run under `uv run python`. Every caller
without the flag keeps the one-step legacy owed-lag reading on stdlib Python. `CLAUDE.md`
§12.2 and the Codex deterministic-context note say so. The one remaining
system-interpreter caller with the flag, the Codex stop gate's GitHub Actions
push-to-main branch, is added to activation hold 1.

| Check | Raw log | Result |
| --- | --- | --- |
| the reviewer's pass-4 probe (impossible-timestamp row, then a normal landing) against the pass-4 guard and this candidate | `u23-pass5-red-proof.log` | pass-4 guard: `owed_lag` True. This candidate: False. A canonical row is True under both |
| the guard run on an enrolled two-trial-landing fixture under `/usr/bin/python3` and the venv, with and without the flag | `u23-pass5-interpreter-probes.log` | system Python without the flag: exit 0, `owed_lag` False. System Python with the flag: loud `ModuleNotFoundError: jsonschema`. The venv with the flag: `owed_lag` True, `ROADMAP_STATUS_LAG_EXPECTED` |
| ruff, pyright against `47cac285` on the same config, `git diff --check`, and seven affected modules | `u23-pass5-lint.log` | clean. Pyright reports 156 errors in the guard and 125 in `finding_record`, the same as at `47cac285`. The affected modules ran 572 passed |
| whole `tools/` pytest at `1177ec15` (`--continue-on-collection-errors`) | `u23-pass5-tools-pytest.log` | 4391 passed, 4 skipped, 36 failed, 7 collection errors. The 36 failures are the same tests by name as at pass 3 |

`carrier-bindings.json` is regenerated for H `1177ec15` at `observed_at`
2026-10-30T13:40:06Z. `rebind_carriers.py` now also binds `tools/finding_record.py`. The
adoption inventory carries the new candidate blobs for `CLAUDE.md`, the guard,
`finding_record.py`, the deterministic-context note, `justfile` and `ci.yml`.
