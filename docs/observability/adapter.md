# Offline observability adapter

The adapter is a pure boundary for offline consumers. It accepts injected compact,
detail, and review evidence and returns one versioned snapshot. It does not read a
journal by itself, retain an input, or call a provider, gateway, replay, promotion,
or host-control API.

## Contract

Each input is one of three explicit source states: available, unreadable, or
contradictory. An unavailable state produces no substitute data. Every output section
reports its source state and freshness. Available projection-backed sections are
`current` or `stale`, based on the supplied journal; review evidence has `not-applicable`
freshness because it is a comparison, not a journal snapshot. A failed freshness check
is unreadable, never current by default.

Compact and detail data come from the existing read models. Detail uses their default
public-only filtering and is copied into the adapter result. Review exposes comparison
evidence and reasons, using `qualified` or `incomplete`; it deliberately has no action
or permission field. All returned mappings and lists are detached from supplied input.

## Implementation plan

1. Define closed source-state and evidence input records in
   `runtime/observability_adapter.py`.
2. Write behavioral tests for populated/current, empty/stale, unreadable,
   contradictory, private-detail, detached-result, and non-authoritative review
   evidence.
3. Implement the smallest pure adapter that composes `runtime.views`,
   `runtime.projections.is_stale`, and `runtime.evaluation.promotion`.
4. Run the adapter tests, the affected projection/view/evaluation suite, the full
   suite, and `git diff --check`.

The boundary does not settle retention, deletion, backup coverage, live transport,
GUI installation, lane aggregation, or topology. Those require separate authority.
