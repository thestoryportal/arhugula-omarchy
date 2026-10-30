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
(regenerated for pass 2; see below).
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
