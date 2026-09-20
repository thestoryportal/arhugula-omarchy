import unittest

from runtime.voice_candidates import (
    AuthorityEvidence,
    AuthorityState,
    CandidateBinding,
    CandidateRequest,
    CandidateRejection,
    CandidateVersion,
    Provenance,
    QualityEvidence,
    QualityState,
    VoiceCandidate,
    represent_candidate,
)


class VoiceCandidateTests(unittest.TestCase):
    def setUp(self):
        self.binding = CandidateBinding(
            CandidateVersion("synthetic-ava", 2, CandidateVersion("synthetic-ava", 1)),
            Provenance("fixture-ava-v2", "sha256:fixture-only"),
        )
        self.authorized = AuthorityEvidence(self.binding, AuthorityState.SYNTHETIC_AUTHORIZED)
        self.accepted = QualityEvidence(self.binding, QualityState.SYNTHETIC_ACCEPTED)

    def test_matching_authorized_accepted_synthetic_metadata_creates_frozen_candidate(self):
        result = represent_candidate(CandidateRequest(self.binding), self.authorized, self.accepted)

        self.assertIsInstance(result, VoiceCandidate)
        self.assertEqual(result.binding, self.binding)
        with self.assertRaises(AttributeError):
            result.binding.version.version = 3

    def test_missing_unknown_denied_rejected_or_incomplete_evidence_returns_no_candidate(self):
        cases = (
            (None, self.accepted, "authority-missing"),
            (AuthorityEvidence(self.binding, AuthorityState.UNKNOWN), self.accepted, "authority-unknown"),
            (AuthorityEvidence(self.binding, AuthorityState.DENIED), self.accepted, "authority-denied"),
            (self.authorized, None, "quality-missing"),
            (self.authorized, QualityEvidence(self.binding, QualityState.UNKNOWN), "quality-unknown"),
            (self.authorized, QualityEvidence(self.binding, QualityState.REJECTED), "quality-rejected"),
            (self.authorized, QualityEvidence(self.binding, QualityState.INCOMPLETE), "quality-incomplete"),
        )

        for authority, quality, reason in cases:
            with self.subTest(reason=reason):
                result = represent_candidate(CandidateRequest(self.binding), authority, quality)
                self.assertEqual(result, CandidateRejection((reason,)))
                self.assertNotIsInstance(result, VoiceCandidate)

    def test_contradictory_evidence_binding_fails_loudly(self):
        other = CandidateBinding(
            CandidateVersion("synthetic-ava", 3, CandidateVersion("synthetic-ava", 2)),
            Provenance("fixture-ava-v3", "sha256:fixture-only-v3"),
        )

        with self.assertRaisesRegex(ValueError, "binding"):
            represent_candidate(CandidateRequest(self.binding), AuthorityEvidence(other, AuthorityState.SYNTHETIC_AUTHORIZED), self.accepted)

    def test_malformed_states_and_contradictory_lineage_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "provenance"):
            Provenance("", "sha256:fixture-only")
        with self.assertRaisesRegex(ValueError, "state"):
            AuthorityEvidence(self.binding, "SYNTHETIC_AUTHORIZED")
        with self.assertRaisesRegex(ValueError, "lineage"):
            CandidateVersion("synthetic-ava", 2, CandidateVersion("another-candidate", 1))
        with self.assertRaisesRegex(ValueError, "lineage"):
            CandidateVersion("synthetic-ava", 2, CandidateVersion("synthetic-ava", 2))

    def test_output_constructors_reject_forged_bindings_and_mutable_or_invalid_reasons(self):
        with self.assertRaisesRegex(ValueError, "binding"):
            VoiceCandidate("forged")
        with self.assertRaisesRegex(ValueError, "reasons"):
            CandidateRejection(["authority-missing"])
        with self.assertRaisesRegex(ValueError, "reasons"):
            CandidateRejection(())
        with self.assertRaisesRegex(ValueError, "reasons"):
            CandidateRejection(("forged",))
        with self.assertRaisesRegex(ValueError, "reasons"):
            CandidateRejection((1,))


if __name__ == "__main__":
    unittest.main()
