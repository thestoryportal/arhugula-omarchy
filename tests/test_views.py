import unittest
from types import MappingProxyType

from runtime.projections import Projection


class ViewTests(unittest.TestCase):
    def test_compact_view_exposes_current_state_without_sensitive_details(self):
        """Would fail if compact status leaks diagnostic detail or omits active state."""
        from runtime.views import compact

        projection = Projection(4, {"status": "success", "event_type": "command.finished"},
                                {"phase": "voice.preview"}, "lane-1",
                                {"id": "local", "model_version": "v1", "status": "success"},
                                "command", False, "healthy", ("tts",), False)

        self.assertEqual(compact(projection), {
            "cursor": 4, "lane": "lane-1", "action_status": "success",
            "interaction_phase": "voice.preview", "provider_status": "success",
            "active_mode": "command", "muted": False, "health": "healthy",
            "degraded_capabilities": ["tts"], "pending": False, "voice_lifecycle": {},
        })

    def test_compact_view_detaches_content_free_voice_lifecycle_only(self):
        """Would fail if compact voice state leaks content or returns a mutable projection reference."""
        from runtime.views import compact

        projection = Projection(5, None, None, None, None,
                                voice_lifecycle={"session-a": {
                                    "phase": "transcription.finished", "status": "success",
                                    "code": "transcription.ok",
                                }})
        view = compact(projection)

        self.assertEqual(view["voice_lifecycle"], {"session-a": {
            "phase": "transcription.finished", "status": "success", "code": "transcription.ok",
        }})
        view["voice_lifecycle"]["session-a"]["phase"] = "altered"
        self.assertEqual(projection.voice_lifecycle["session-a"]["phase"], "transcription.finished")

    def test_detailed_view_filters_sensitive_diagnostics_by_default(self):
        """Private transcript data must not appear in the normal detail view."""
        from runtime.views import compact, detailed

        projection = Projection(9, {"status": "success", "event_type": "command.finished"},
                                {"phase": "voice.preview"}, "lane-1",
                                {"id": "local", "model_version": "v1", "status": "success"})
        diagnostics = [
            {"category": "timing", "value": {"duration_ms": 18}, "sensitivity": "public"},
            {"category": "transcript", "value": "private words", "sensitivity": "private"},
        ]

        self.assertEqual(detailed(projection, diagnostics), {
            "state": compact(projection),
            "diagnostics": [{"category": "timing", "value": {"duration_ms": 18}}],
        })

    def test_detailed_view_expands_sensitive_diagnostics_only_when_requested(self):
        """An explicit request can expand the diagnostic payload for review."""
        from runtime.views import compact, detailed

        projection = Projection(0, None, None, None, None)
        diagnostics = [
            {"category": "risk", "value": "confirm", "sensitivity": "public"},
            {"category": "transcript", "value": "private words", "sensitivity": "private"},
        ]

        self.assertEqual(detailed(projection, diagnostics, include_sensitive=True), {
            "state": compact(projection),
            "diagnostics": [
                {"category": "risk", "value": "confirm"},
                {"category": "transcript", "value": "private words"},
            ],
        })

    def test_detailed_view_defaults_unknown_sensitivity_to_hidden_and_detaches_values(self):
        """Views need a safe default and must never expose mutable source state."""
        from runtime.views import detailed

        diagnostics = [
            {"category": "verification", "value": {"checks": ["passed"]}, "sensitivity": "public"},
            {"category": "execution", "value": "host state", "sensitivity": "internal"},
        ]
        view = detailed(Projection(0, None, None, None, None), diagnostics)
        view["diagnostics"][0]["value"]["checks"].append("altered")

        self.assertEqual(view["diagnostics"], [
            {"category": "verification", "value": {"checks": ["passed", "altered"]}},
        ])
        self.assertEqual(diagnostics[0]["value"], {"checks": ["passed"]})

    def test_detailed_view_accepts_immutable_event_detail_values(self):
        """Journal-derived frozen details can be rendered without being returned by reference."""
        from runtime.views import detailed

        value = MappingProxyType({"duration_ms": 18})
        view = detailed(Projection(0, None, None, None, None), [
            {"category": "timing", "value": value, "sensitivity": "public"},
        ])

        self.assertEqual(view["diagnostics"], [
            {"category": "timing", "value": {"duration_ms": 18}},
        ])
        self.assertIsNot(view["diagnostics"][0]["value"], value)

    def test_detailed_view_never_expands_unknown_sensitivity(self):
        """Only the closed private classification permits explicit expansion."""
        from runtime.views import detailed

        view = detailed(Projection(0, None, None, None, None), [
            {"category": "risk", "value": "safe", "sensitivity": "public"},
            {"category": "execution", "value": "internal", "sensitivity": "internal"},
        ], include_sensitive=True)

        self.assertEqual(view["diagnostics"], [
            {"category": "risk", "value": "safe"},
        ])

    def test_detailed_view_preserves_review_categories_in_order(self):
        """The review surface carries each execution-decision category without reshaping it."""
        from runtime.views import detailed

        diagnostics = [
            {"category": category, "value": category + " value", "sensitivity": "public"}
            for category in ("transcript", "candidate", "risk", "validation", "execution",
                             "verification", "timing")
        ]

        self.assertEqual(detailed(Projection(0, None, None, None, None), diagnostics)["diagnostics"], [
            {"category": category, "value": category + " value"}
            for category in ("transcript", "candidate", "risk", "validation", "execution",
                             "verification", "timing")
        ])


if __name__ == "__main__":
    unittest.main()
