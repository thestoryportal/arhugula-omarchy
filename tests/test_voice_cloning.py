import unittest
from unittest.mock import ANY

from runtime.voice_candidates import (
    AuthorityEvidence,
    AuthorityState,
    CandidateBinding,
    CandidateRejection,
    CandidateRequest,
    CandidateVersion,
    Provenance,
    QualityEvidence,
    QualityState,
    VoiceCandidate,
)

try:
    from runtime.voice_cloning import (
        CloningEvaluationRequest,
        EvaluatorFailure,
        EvaluatorFailureReason,
        MissingSampleRequirements,
        QualityDecision,
        SyntheticDescriptor,
        evaluate_cloning_request,
    )
except ImportError as error:
    WORKFLOW_IMPORT_ERROR = error
else:
    WORKFLOW_IMPORT_ERROR = None


class VoiceCloningTests(unittest.TestCase):
    def setUp(self):
        self.binding = CandidateBinding(
            CandidateVersion("fixture", 2, CandidateVersion("fixture", 1)),
            Provenance("fixture-v2", "sha256:fixture-v2"),
        )
        self.request = CandidateRequest(self.binding)
        self.authorized = AuthorityEvidence(self.binding, AuthorityState.SYNTHETIC_AUTHORIZED)
        complete_descriptor = SyntheticDescriptor(
            self.binding, frozenset({"sample-a", "sample-b"}), frozenset({"sample-a", "sample-b"})
        )
        self.complete_request = CloningEvaluationRequest(self.request, complete_descriptor)
        self.accepted_decision = QualityDecision(
            self.complete_request,
            QualityEvidence(self.binding, QualityState.SYNTHETIC_ACCEPTED),
        )
        self.request_missing_sample_a = CloningEvaluationRequest(
            self.request,
            SyntheticDescriptor(self.binding, frozenset({"sample-a", "sample-b"}), frozenset({"sample-b"})),
        )

    def require_workflow(self):
        self.assertIsNone(WORKFLOW_IMPORT_ERROR, "runtime.voice_cloning must exist")

    def test_descriptor_derives_sorted_missing_sample_ids(self):
        self.require_workflow()

        descriptor = SyntheticDescriptor(
            self.binding,
            frozenset({"sample-c", "sample-a", "sample-b"}),
            frozenset({"sample-b"}),
        )

        self.assertEqual(descriptor.missing_sample_ids, ("sample-a", "sample-c"))

    def test_request_requires_one_matching_descriptor_binding(self):
        self.require_workflow()
        other = CandidateBinding(
            CandidateVersion("fixture", 3, CandidateVersion("fixture", 2)),
            Provenance("fixture-v3", "sha256:fixture-v3"),
        )

        with self.assertRaisesRegex(ValueError, "binding"):
            CloningEvaluationRequest(
                self.request,
                SyntheticDescriptor(other, frozenset({"sample-a"}), frozenset({"sample-a"})),
            )

    def test_public_result_constructors_reject_malformed_or_inconsistent_values(self):
        self.require_workflow()
        descriptor = SyntheticDescriptor(self.binding, frozenset({"sample-a"}), frozenset())
        request = CloningEvaluationRequest(self.request, descriptor)

        with self.assertRaisesRegex(ValueError, "sample"):
            SyntheticDescriptor(self.binding, {"sample-a"}, frozenset())
        with self.assertRaisesRegex(ValueError, "sample"):
            SyntheticDescriptor(self.binding, frozenset({""}), frozenset())
        with self.assertRaisesRegex(ValueError, "missing"):
            MissingSampleRequirements(request, ())
        with self.assertRaisesRegex(ValueError, "missing"):
            MissingSampleRequirements(request, ["sample-a"])
        with self.assertRaisesRegex(ValueError, "missing"):
            MissingSampleRequirements(request, ("other",))
        with self.assertRaisesRegex(ValueError, "missing"):
            MissingSampleRequirements(request, (ANY,))
        with self.assertRaisesRegex(ValueError, "reason"):
            EvaluatorFailure(request, "unavailable")

        other = CandidateBinding(CandidateVersion("other", 1), Provenance("other", "sha256:other"))
        with self.assertRaisesRegex(ValueError, "binding"):
            QualityDecision(request, QualityEvidence(other, QualityState.SYNTHETIC_ACCEPTED))

    def test_missing_required_sample_is_not_a_candidate(self):
        self.require_workflow()
        accepted_decision = QualityDecision(
            self.request_missing_sample_a,
            QualityEvidence(self.binding, QualityState.SYNTHETIC_ACCEPTED),
        )

        result = evaluate_cloning_request(
            self.request_missing_sample_a, self.authorized, accepted_decision
        )

        self.assertEqual(result, MissingSampleRequirements(self.request_missing_sample_a, ("sample-a",)))
        self.assertNotIsInstance(result, VoiceCandidate)

    def test_evaluator_failure_is_not_rejected_quality(self):
        self.require_workflow()
        failure = EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE)

        result = evaluate_cloning_request(self.complete_request, self.authorized, failure)

        self.assertIs(result, failure)

    def test_contradictory_authority_binding_rejected_before_missing_sample_outcome(self):
        self.require_workflow()
        other = CandidateBinding(CandidateVersion("other", 1), Provenance("other", "sha256:other"))
        matching_decision = QualityDecision(
            self.request_missing_sample_a,
            QualityEvidence(self.binding, QualityState.SYNTHETIC_ACCEPTED),
        )

        with self.assertRaisesRegex(ValueError, "authority binding"):
            evaluate_cloning_request(
                self.request_missing_sample_a,
                AuthorityEvidence(other, AuthorityState.SYNTHETIC_AUTHORIZED),
                matching_decision,
            )

    def test_missing_evaluator_result_preserves_quality_missing(self):
        self.require_workflow()

        result = evaluate_cloning_request(self.complete_request, self.authorized, None)

        self.assertEqual(result, CandidateRejection(("quality-missing",)))

    def test_workflow_delegates_each_candidate_eligibility_denial(self):
        self.require_workflow()
        cases = (
            (None, self.accepted_decision, "authority-missing"),
            (AuthorityEvidence(self.binding, AuthorityState.UNKNOWN), self.accepted_decision, "authority-unknown"),
            (AuthorityEvidence(self.binding, AuthorityState.DENIED), self.accepted_decision, "authority-denied"),
            (self.authorized, QualityDecision(self.complete_request, QualityEvidence(self.binding, QualityState.UNKNOWN)), "quality-unknown"),
            (self.authorized, QualityDecision(self.complete_request, QualityEvidence(self.binding, QualityState.REJECTED)), "quality-rejected"),
            (self.authorized, QualityDecision(self.complete_request, QualityEvidence(self.binding, QualityState.INCOMPLETE)), "quality-incomplete"),
        )

        for authority, evaluator_result, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(
                    evaluate_cloning_request(self.complete_request, authority, evaluator_result),
                    CandidateRejection((reason,)),
                )

    def test_evaluator_result_for_a_different_request_fails_before_outcome(self):
        self.require_workflow()
        other_request = CloningEvaluationRequest(
            self.request,
            SyntheticDescriptor(self.binding, frozenset({"sample-a"}), frozenset({"sample-a"})),
        )
        foreign_result = QualityDecision(
            other_request,
            QualityEvidence(self.binding, QualityState.SYNTHETIC_ACCEPTED),
        )

        with self.assertRaisesRegex(ValueError, "evaluator result"):
            evaluate_cloning_request(self.complete_request, self.authorized, foreign_result)

    def test_result_binding_and_failure_are_immutable(self):
        self.require_workflow()
        result = evaluate_cloning_request(self.complete_request, self.authorized, self.accepted_decision)

        with self.assertRaises(AttributeError):
            result.binding.version.version = 9
        with self.assertRaises(AttributeError):
            self.complete_request.descriptor.required_sample_ids = frozenset()
        with self.assertRaises(AttributeError):
            EvaluatorFailure(self.complete_request, EvaluatorFailureReason.UNAVAILABLE).reason = "rejected"


if __name__ == "__main__":
    unittest.main()
