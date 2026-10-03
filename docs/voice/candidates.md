# Synthetic voice candidates

`runtime.voice_candidates` is a deterministic, metadata-only decision boundary for
offline fixtures. A request identifies one synthetic candidate version, optional
same-identity prior version, and an immutable provenance reference. Authority-state
and quality-decision evidence are supplied separately and must bind to precisely the
same request.

The boundary creates a `VoiceCandidate` only when provenance is valid and the two
supplied fixture states are respectively `SYNTHETIC_AUTHORIZED` and
`SYNTHETIC_ACCEPTED`. Missing, unknown, denied, rejected, or incomplete evidence
returns `CandidateRejection`, which deliberately has no candidate value. Malformed
identities, versions, provenance, and contradictory bindings or lineage raise
`ValueError` rather than being converted to an approval-shaped result.

Candidate outputs require an exact valid `CandidateBinding`. Rejections require a
nonempty immutable tuple drawn from the boundary's closed reason vocabulary; mutable
or forged output constructor values are rejected.

All values are frozen and hold metadata references only. The synthetic labels are not
authenticated consent, evaluator evidence, trusted approval receipts, real samples,
or activation authority. This module does not collect, retain, delete, persist,
upload, download, synthesize, play, infer from, or activate any voice data. Real
consent/revocation, retention/deletion, quality-issuer authority, thresholds, and
activation remain later user-policy work.

## Post-implementation gate remediation — 2026-09-20

The preimplementation design/plan artifact gate was skipped. This section is
post-implementation remediation, not prior approval or a rewritten chronology.

The retrospective design is a pure synthetic decision boundary: request, provenance,
and supplied authority/quality states enter; an immutable candidate or explicit
rejection leaves. `CandidateBinding` owns candidate identity, version lineage, and
provenance in one place. Requests and evidence carry that exact binding, preventing a
later source or lineage substitution. Candidate output construction requires an exact
`CandidateBinding`; rejection construction requires a nonempty immutable tuple from
the closed reason vocabulary. Neither output is consent, authenticated approval, or
activation authority.

Executed sequence: `60aa91807485e0f6f0f92f9ec340f6b7cd2f9491` introduced the
metadata boundary. At `d9b7241b30557b68dede50c0fdd81d5bb2f9de31`, direct forged
candidate binding and mutable/invalid rejection-reason RED regressions exposed the
public-constructor gap; exact output validation made the five focused tests GREEN.
Against that immutable head, six in-memory mutants were detected: denied authority,
rejected quality, request-binding, non-monotonic lineage, candidate-output binding,
and rejection mutability guards. The unmodified focused baseline passed.

For final verification and review, provide the immutable head and confirm focused and
full tests, package smoke, and all six mutation probes; then request an independent
review of the same immutable diff. Do not extend this metadata contract into real
authorization, retention, or activation policy.
