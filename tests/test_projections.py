import json
from pathlib import Path
import unittest

from runtime.contracts import Interaction, decode
from runtime.journal import MemoryJournal


def record(kind, **patch):
    data = json.loads(Path("tests/fixtures/contracts-v1.json").read_text())
    payload = next(item for item in data if item["kind"] == kind)
    return decode({**payload, **patch})


def voice(session_id, event_id, phase, status, code):
    return decode({
        "kind": "voice-observation", "version": 1, "event_id": event_id,
        "session_id": session_id, "activation_id": "activation-" + session_id,
        "correlation_id": "correlation-" + session_id, "timestamp_ms": 100,
        "context": {**record("event").context, "source": "voice"},
        "phase": phase, "status": status, "code": code,
    })


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

    def test_rebuild_projects_operational_state_from_safe_event_details(self):
        """Views need replayed mode, mute, health, degradation, and pending state."""
        from runtime.projections import rebuild

        journal = MemoryJournal()
        journal.append(Interaction(1, "interaction-1", "command-1", "corr-1", 1,
                                   dict(record("event").context), "voice.preview",
                                   {"mode": "command", "muted": False}))
        journal.append(record("event", event_id="health-1", event_type="command.started",
                              status="pending", details={"health": "degraded",
                                                         "degraded_capabilities": ["tts"]}))

        projection = rebuild(journal)

        self.assertEqual(projection.active_mode, "command")
        self.assertFalse(projection.muted)
        self.assertEqual(projection.health, "degraded")
        self.assertEqual(projection.degraded_capabilities, ("tts",))
        self.assertTrue(projection.pending)

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

    def test_rebuild_keeps_latest_content_free_lifecycle_per_session_without_authority(self):
        """Would fail if voice replay leaks content, mixes sessions, or changes action state."""
        from runtime.projections import rebuild

        journal = MemoryJournal()
        journal.append(record("event", event_id="action-1", event_type="command.started", status="pending"))
        journal.append(voice("session-a", "voice-1", "capture.started", "recording", "capture.started"))
        journal.append(voice("session-b", "voice-2", "transcription.started", "processing", "transcription.started"))
        journal.append(voice("session-a", "voice-3", "capture.stopped", "processing", "capture.silence"))

        projection = rebuild(journal)

        self.assertEqual(projection.cursor, 4)
        self.assertEqual(projection.action, {"status": "pending", "event_type": "command.started"})
        self.assertTrue(projection.pending)
        self.assertEqual(projection.voice_lifecycle, {
            "session-a": {"phase": "capture.stopped", "status": "processing", "code": "capture.silence"},
            "session-b": {"phase": "transcription.started", "status": "processing", "code": "transcription.started"},
        })
        self.assertEqual({key for state in projection.voice_lifecycle.values() for key in state},
                         {"phase", "status", "code"})

    def test_voice_lifecycle_advances_cursor_and_marks_old_replay_stale(self):
        """Would fail if a voice observation is ignored by replay freshness tracking."""
        from runtime.projections import is_stale, rebuild

        journal = MemoryJournal()
        current = rebuild(journal)
        journal.append(voice("session-a", "voice-1", "capture.canceled", "canceled", "capture.canceled"))

        self.assertTrue(is_stale(current, journal))
        self.assertEqual(rebuild(journal).voice_lifecycle, {
            "session-a": {"phase": "capture.canceled", "status": "canceled", "code": "capture.canceled"},
        })


if __name__ == "__main__":
    unittest.main()
