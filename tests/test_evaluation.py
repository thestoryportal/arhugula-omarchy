import unittest


class EvaluationTests(unittest.TestCase):
    def test_pinned_deterministic_independent_run_promotes_matching_candidate(self):
        """A candidate needs replay provenance, independent review, and rollback readiness."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-1", True, True, True,
                           {"case-1": "pass", "case-2": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-1", True, True, True,
                              {"case-1": "pass", "case-2": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "promote", "regressions": (), "reasons": (),
        })

    def test_disagreement_or_regression_blocks_promotion(self):
        """A candidate cannot promote over a failed replay or evaluator disagreement."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "recorded", "bundle-2", True, True, True,
                           {"case-1": "pass", "case-2": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "recorded", "bundle-2", True, True, False,
                              {"case-1": "pass", "case-2": "fail"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "hold", "regressions": ("case-2",),
            "reasons": ("independent-evaluation-required", "replay-regression", "candidate-failure"),
        })

    def test_live_run_is_evidence_only_until_manually_approved(self):
        """Live provenance does not grant promotion authority by itself."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "live", "bundle-3", True, True, True, {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "live", "bundle-3", True, True, True, {"case-1": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=(), rollback_ready=True)["decision"], "hold")

    def test_candidate_cannot_compare_against_a_different_pinned_bundle(self):
        """Promotion compares like-for-like replay evidence, never a substituted baseline."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", True, True, True, {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-b", True, True, True, {"case-1": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "hold", "regressions": (), "reasons": ("replay-bundle-mismatch",),
        })

    def test_candidate_failure_or_source_substitution_cannot_promote(self):
        """A new failed case and a changed replay source both invalidate comparison evidence."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", True, True, True, {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "recorded", "bundle-a", True, True, True,
                              {"case-1": "pass", "case-2": "fail"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "hold", "regressions": (),
            "reasons": ("replay-source-mismatch", "replay-coverage-incomplete", "candidate-failure"),
        })

    def test_replay_run_rejects_mutable_or_invalid_evidence(self):
        """Evaluation evidence remains a closed immutable data boundary."""
        from runtime.evaluation import ReplayRun

        with self.assertRaisesRegex(ValueError, "outcomes"):
            ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True, {"case-1": "unknown"}, True)
        outcomes = {"case-1": "pass"}
        run = ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True, outcomes, True)
        outcomes["case-1"] = "fail"
        self.assertEqual(run.outcomes, {"case-1": "pass"})

    def test_missing_baseline_case_blocks_promotion(self):
        """A candidate must cover every case in the trusted comparison bundle."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", True, True, True,
                           {"case-1": "pass", "case-2": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True,
                              {"case-1": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "hold", "regressions": ("case-2",),
            "reasons": ("replay-coverage-incomplete", "replay-regression"),
        })

    def test_unqualified_baseline_cannot_authorize_promotion(self):
        """Candidate evidence is only meaningful against a qualified active baseline."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", False, False, False,
                           {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True,
                              {"case-1": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True), {
            "decision": "hold", "regressions": (),
            "reasons": ("baseline-pinned-replay-required", "baseline-deterministic-replay-required",
                        "baseline-independent-evaluation-required"),
        })

    def test_rejection_and_missing_rollback_readiness_hold_a_candidate(self):
        """Manual rejection wins over approval and rollback readiness is mandatory."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", True, True, True, {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True,
                              {"case-1": "pass"}, True)

        self.assertEqual(promotion(active, candidate, labels=("approved", "rejected"), rollback_ready=False), {
            "decision": "hold", "regressions": (),
            "reasons": ("rollback-readiness-required", "manual-rejection"),
        })

    def test_promotion_requires_exact_labels_boolean_rollback_and_evaluator_consensus(self):
        """Substring labels, truthy rollback values, and evaluator disagreement cannot promote."""
        from runtime.evaluation import ReplayRun, promotion

        active = ReplayRun("active-v1", "synthetic", "bundle-a", True, True, True,
                           {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True,
                              {"case-1": "pass"}, False)
        with self.assertRaisesRegex(ValueError, "labels"):
            promotion(active, candidate, labels="preapproved", rollback_ready=True)
        with self.assertRaisesRegex(ValueError, "rollback"):
            promotion(active, candidate, labels=("approved",), rollback_ready=1)
        self.assertEqual(promotion(active, candidate, labels=("approved",), rollback_ready=True)["reasons"],
                         ("independent-evaluator-disagreement",))

    def test_replay_run_requires_nonempty_typed_provenance_and_cases(self):
        """An empty bundle or result set is not promotable evaluation evidence."""
        from runtime.evaluation import ReplayRun

        with self.assertRaisesRegex(ValueError, "bundle"):
            ReplayRun("candidate-v2", "synthetic", "", True, True, True, {"case-1": "pass"}, True)
        with self.assertRaisesRegex(ValueError, "outcomes"):
            ReplayRun("candidate-v2", "synthetic", "bundle-a", True, True, True, {}, True)


if __name__ == "__main__":
    unittest.main()
