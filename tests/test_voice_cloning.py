import unittest

from runtime.voice_candidates import (
    CandidateBinding,
    CandidateRequest,
    CandidateVersion,
    Provenance,
    QualityEvidence,
    QualityState,
)

try:
    from runtime.voice_cloning import (
        CloningEvaluationRequest,
        EvaluatorFailure,
        EvaluatorFailureReason,
        MissingSampleRequirements,
        QualityDecision,
        SyntheticDescriptor,
    )
except ModuleNotFoundError as error:
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
        with self.assertRaisesRegex(ValueError, "reason"):
            EvaluatorFailure(request, "unavailable")

        other = CandidateBinding(CandidateVersion("other", 1), Provenance("other", "sha256:other"))
        with self.assertRaisesRegex(ValueError, "binding"):
            QualityDecision(request, QualityEvidence(other, QualityState.SYNTHETIC_ACCEPTED))


if __name__ == "__main__":
    unittest.main()
