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

This retrospective design and prospective correction/verification plan was written
after implementation. It is not evidence of prior design approval. At this record's
creation, `d9b7241` already contains the output-constructor correction; that work is
preserved rather than reset or recast as earlier planning.

The boundary remains a pure synthetic metadata decision: a request, provenance, and
externally supplied authority and quality states flow in; an immutable candidate or
explicit rejection flows out. `CandidateBinding` is the single source of truth for
candidate identity, version lineage, and provenance. Request and evidence objects
must carry that exact binding, so neither source nor lineage can be substituted at a
later decision point. A valid result must require the exact parsed binding. A rejection
must require a nonempty tuple from the closed reason vocabulary, preventing mutable or
invented denial output. Neither result constitutes consent, authenticated approval, or
activation authority.

For this correction and any final immutable re-review, first run a RED regression for
forged candidate bindings and mutable, empty, unknown, or non-string rejection
reasons. Then make only the output-boundary validation GREEN, keeping decision inputs
and real-policy scope unchanged. Verify focused tests, output-guard mutations, and the
existing authority, quality, exact-binding, and lineage mutations; then run the full
suite and package smoke from the immutable commit supplied for independent review.
