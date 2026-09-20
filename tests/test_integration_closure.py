import json
from pathlib import Path
import re
import unittest


FIXTURE = Path(__file__).with_name("fixtures") / "integration-closure-v1.json"
SHA1 = re.compile(r"^[0-9a-f]{40}$")


class IntegrationClosureEvidenceTests(unittest.TestCase):
    def load_contract(self):
        self.assertTrue(FIXTURE.exists(), "the integration-closure fixture must exist")
        return json.loads(FIXTURE.read_text())

    def test_only_matching_main_evidence_with_successful_post_main_checks_is_closable(self):
        """A stacked merge, review clearance, or incomplete CI must not close a unit."""
        contract = self.load_contract()
        self.assertEqual(contract["version"], 1)

        closable = {case["id"] for case in contract["cases"] if case["closable"]}
        self.assertEqual(closable, {"main-verified"})

        main = next(case for case in contract["cases"] if case["id"] == "main-verified")
        self.assertEqual(main["integrated_main_sha"], main["evidence_sha"])
        self.assertEqual(main["post_main_checks"], "success")
        self.assertTrue(main["github_user_approval"])

    def test_incomplete_or_untrustworthy_evidence_never_makes_a_unit_closable(self):
        """Breaks if a missing, stale, mismatched, stacked-only, failed, or pending case closes."""
        contract = self.load_contract()
        expected_not_closable = {
            "locally-verified",
            "review-cleared",
            "stacked-merged",
            "awaiting-integration",
            "missing-evidence",
            "stale-evidence",
            "mismatched-evidence",
            "failed-post-main-ci",
            "pending-post-main-ci",
            "agent-review-only",
        }
        cases = {case["id"]: case for case in contract["cases"]}
        self.assertEqual(set(cases) - {"main-verified"}, expected_not_closable)
        self.assertTrue(all(not cases[case_id]["closable"] for case_id in expected_not_closable))
        self.assertFalse(cases["stacked-merged"]["integrated_main_sha"])
        self.assertFalse(cases["agent-review-only"]["github_user_approval"])
        self.assertNotEqual(cases["mismatched-evidence"]["integrated_main_sha"],
                            cases["mismatched-evidence"]["evidence_sha"])
        self.assertIn(cases["failed-post-main-ci"]["post_main_checks"], {"failure", "cancelled"})
        self.assertEqual(cases["pending-post-main-ci"]["post_main_checks"], "pending")

    def test_recorded_commit_evidence_uses_full_sha1_syntax_when_present(self):
        """Breaks if fixture evidence degrades into a label or abbreviated object ID."""
        contract = self.load_contract()
        for case in contract["cases"]:
            for field in ("evidence_sha", "integrated_main_sha"):
                value = case[field]
                if value is not None:
                    self.assertIsInstance(value, str, f"{case['id']} {field}")
                    self.assertIsNotNone(SHA1.fullmatch(value), f"{case['id']} {field}")


if __name__ == "__main__":
    unittest.main()
