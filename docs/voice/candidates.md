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
