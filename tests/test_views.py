import unittest

from runtime.projections import Projection


class ViewTests(unittest.TestCase):
    def test_compact_view_exposes_current_state_without_sensitive_details(self):
        """Would fail if compact status leaks diagnostic detail or omits active state."""
        from runtime.views import compact

        projection = Projection(4, {"status": "success", "event_type": "command.finished"},
                                {"phase": "voice.preview"}, "lane-1",
                                {"id": "local", "model_version": "v1", "status": "success"})

        self.assertEqual(compact(projection), {
            "cursor": 4, "lane": "lane-1", "action_status": "success",
            "interaction_phase": "voice.preview", "provider_status": "success",
        })


if __name__ == "__main__":
    unittest.main()
