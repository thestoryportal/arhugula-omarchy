# Offline observability acceptance preparation

This is an acceptance-preparation artifact for
`arhugula-observability-xb8.656.yv0`. It separates settled evidence from proposed
tests for the five workspace views named in the
[workspace design](../superpowers/specs/2026-09-19-omarchy-agent-workspace-design.md#agent-workspace).
It authorizes neither a workspace adapter nor retention, deletion, live I/O, or
execution. Projections remain rebuildable observations, never execution authority.

## Settled evidence and proposed cases

| View | Synthetic input and observable expected output | Privacy and authority denial | Supported API / missing capability |
| --- | --- | --- | --- |
| Compact status | **Settled:** a `Projection(0, None, None, None, None)` produces cursor `0`, null current-state fields, an empty degraded-capabilities list, and an empty voice-lifecycle map. A populated projection exposes only status fields. **Proposed acceptance:** replay a pending and then a failed event; the displayed state changes with the replay cursor, with no inferred success. | Compact output contains no diagnostics or transcript. Replaying it must not dispatch, promote, or mutate the journal. | [`compact`](../../runtime/views.py) and its [tests](../../tests/test_views.py) exist. No workspace/panel adapter exists. |
| Lane overview | **Proposed acceptance:** replay two synthetic lane IDs with distinct latest states; the overview has one current row per lane, keyed by stable ID, and an empty journal renders no rows. A source disagreement or unreadable source is visible as a safe error state, never as a healthy lane. | Rows exclude transcript, raw stderr, and private diagnostics; selecting a row is read-only and cannot claim work or control an agent. | The projection retains only the latest `lane`; no lane registry, aggregation, LIT/Git projection, or renderer exists. The planned surface is [G.2–G.3](../superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md). |
| Detailed lane | **Settled:** [`detailed`](../../runtime/views.py) returns public diagnostics by default and hides private or unknown sensitivity; its copy is detached from input. **Proposed acceptance:** a public timing record is visible, while a private synthetic transcript is absent unless a future, separately authorized review boundary requests it. Empty diagnostics render an empty list. | A sensitivity request is not execution permission. Raw transcript, recording, and subprocess stderr remain out of normal output, Git, and LIT under the [voice proposal](../superpowers/specs/2026-09-20-live-voice-integration-proposal.md#privacy-observations-and-retention). | The pure detailed read model exists. The D.3 workspace fields—candidates, intent, prompts, outputs, validation, and verification—are missing. |
| Topology | **Proposed acceptance:** provide synthetic agent, model, lane, issue, workspace, dependency, and blocked-path records; render their nodes and edges, preserve an empty graph for no records, and mark a snapshot stale when `is_stale` finds later journal entries. A failed source must display a safe error/degraded state and retain no invented topology. | Topology is observational: it cannot alter agent lifecycle, issue assignment, window placement, or execution. It excludes content-bearing diagnostics. | [`is_stale`](../../runtime/projections.py) exists, but no topology projection or graph renderer exists. [G.5](../superpowers/plans/2026-09-19-omarchy-agent-workspace-implementation-plan.md) remains the planned capability. |
| Review | **Settled:** two immutable synthetic [`ReplayRun`](../../runtime/evaluation.py) records can yield `promote` only with matching qualified evidence, manual approval, and rollback readiness; disagreement, regression, incomplete coverage, rejection, or missing readiness yields `hold`. **Proposed acceptance:** a review view reports those reasons exactly as read evidence, including an empty candidate set as “no comparison,” never a promotion. | Review output cannot promote, roll back, replay, or execute. Live provenance alone remains insufficient; fixture recordings require separate consent, provenance, and duration. | [`promotion`](../../runtime/evaluation.py) is a deterministic, non-authoritative decision helper. D.4’s comparison/correction/review surface and D.5’s replay harness are still missing. |

## Boundaries, stale and error behavior

The settled model declares a snapshot stale only when later journal entries exist;
`compact` does not currently expose a stale flag. A future adapter should show the
last snapshot with that condition and never refresh by side effect. Existing pure
view functions have no UI error contract. The proposed views therefore require a
content-safe error/degraded state for unreadable or contradictory sources, without a
fallback source that changes the meaning of the data.

Retention policy is unresolved: record classes, durations and triggers,
derivative/backup coverage, and purge authority have no settled contract. Retained
replay audio needs per-fixture consent, provenance, and duration; raw voice content
does not belong in fixtures, Git, LIT, or this artifact.

## Proposed implementation boundary and deterministic checks

A later slice may add a read-only adapter that consumes projections and evaluation
evidence, plus explicit source-error and freshness values. It must not add execution,
retention, purge, live transport, or UI installation. Keep authority at its existing
owners; a displayed state never becomes an authorization token.

Run these offline checks when that boundary is implemented:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_projections tests.test_views tests.test_evaluation
git diff --check
```
