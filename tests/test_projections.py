import json
from pathlib import Path
import unittest

from runtime.contracts import Interaction, decode
from runtime.journal import MemoryJournal


def record(kind, **patch):
    data = json.loads(Path("tests/fixtures/contracts-v1.json").read_text())
    payload = next(item for item in data if item["kind"] == kind)
    return decode({**payload, **patch})


class ProjectionTests(unittest.TestCase):
    def test_rebuild_tracks_latest_action_and_interaction_in_sequence_order(self):
        """Would fail if replay ignores ordering or does not replace stale current state."""
        from runtime.projections import rebuild

        journal = MemoryJournal()
        journal.append(record("event", event_id="event-1", event_type="command.started", status="pending"))
        journal.append(Interaction(1, "interaction-1", "command-1", "corr-1", 1,
                                   dict(record("event").context), "voice.preview", {}))
        journal.append(record("event", event_id="event-2", event_type="command.finished", status="success"))

        projection = rebuild(journal)

        self.assertEqual(projection.cursor, 3)
        self.assertEqual(projection.action, {"status": "success", "event_type": "command.finished"})
        self.assertEqual(projection.interaction, {"phase": "voice.preview"})

    def test_rebuild_projects_latest_lane_and_provider_health(self):
        """Would fail if a later journal event cannot replace stale lane/provider state."""
        from runtime.projections import rebuild

        context = dict(record("event").context)
        context.update({"lane_id": "lane-2", "provider_id": "local", "model_version": "v2"})
        journal = MemoryJournal()
        journal.append(record("event", event_id="health-1", event_type="command.finished",
                              status="success", context=context))

        projection = rebuild(journal)

        self.assertEqual(projection.lane, "lane-2")
        self.assertEqual(projection.provider, {"id": "local", "model_version": "v2", "status": "success"})

    def test_projection_detects_staleness_and_full_rebuild_recovers(self):
        """Would fail if a view stays trusted after journal data advances."""
        from runtime.projections import is_stale, rebuild

        journal = MemoryJournal()
        journal.append(record("event", event_id="action-1", event_type="command.started", status="pending"))
        stale = rebuild(journal)
        journal.append(record("event", event_id="action-2", event_type="command.finished", status="success"))

        self.assertTrue(is_stale(stale, journal))
        current = rebuild(journal)
        self.assertFalse(is_stale(current, journal))
        self.assertEqual(current.action, {"status": "success", "event_type": "command.finished"})


if __name__ == "__main__":
    unittest.main()
