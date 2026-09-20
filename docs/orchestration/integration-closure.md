# Integration closure evidence v1

This document defines how repository work is described between its local
verification and durable main landing. It is an evidence vocabulary for LIT,
handoffs, reviews, and fixtures; it neither changes the continuation runner nor
authorizes a merge, a GitHub action, a live action, or a ticket close.

## Delivery states

| State | Meaning | Closable? |
| --- | --- | --- |
| `locally-verified` | Focused and full repository checks passed for a local immutable commit. | No |
| `review-cleared` | An independent range review reported no blocking finding. | No |
| `stacked-merged` | The commit is merged into an integration or stacked branch, not `main`. | No |
| `awaiting-integration` | Required review, protected-branch, baseline, or publication evidence is incomplete. | No |
| `main-verified` | The exact evidence commit is integrated on `main` and all required post-main checks succeeded. | Yes |

`locally-verified`, `review-cleared`, and `stacked-merged` may all be true at
once. They still describe an awaiting-integration unit until the `main-verified`
conditions are independently evidenced.

## Required final evidence

A final closure record names:

- the immutable `evidence_sha` that was reviewed and verified;
- the `integrated_main_sha`, which must identify that same delivered content on
  the actual `main` history;
- successful required checks run after that main integration: `Python test suite`,
  `Ruff lint`, and `Runtime and package smoke`.

Missing evidence is not evidence. A stale or mismatched SHA is not a main
landing. A failed, cancelled, or pending post-main check is not success. An
agent review remains useful range evidence; it neither substitutes for the
required CI evidence nor grants merge authority.

A full lowercase 40-character SHA-1 value is required when a repository uses
SHA-1 object IDs, but this syntactic check is not proof that the object exists,
is reachable from `main`, or represents a successful landing. Those facts still
require the separately recorded integration and post-main evidence.

The companion fixture at `tests/fixtures/integration-closure-v1.json` contains
the normal states and negative examples. It deliberately marks only a matching
main SHA with successful post-main checks as closable. It is test data and
documentation, not CI, runner, or GitHub enforcement.
