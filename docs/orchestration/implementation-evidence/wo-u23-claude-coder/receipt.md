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

`carrier-bindings.json` is the output of `rebind_carriers.py <H> 91e76a4e… 741e379c… HEAD <O> 766d5a31…`.
The source09 reducer replay used the real `.harness/merge-gate-log.jsonl` rows at
the H candidate. Passes 1, 2 and 3 each replay as complete, and pass 3 closes the
cycle.
