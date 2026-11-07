import copy
import json
from pathlib import Path
import tempfile
import unittest

from adopt_root import adopt


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.control = self.root / "control.json"
        self.transcript = self.root / "native.jsonl"
        self.sid = "01a1b81c-a7c3-73c2-95ce-c5278a3aa043"
        self.data = {
            "notification_thread": "old",
            "repair_paused": True,
            "sessions": [
                {
                    "role": "buford",
                    "kind": "codex",
                    "session_id": "old",
                    "transcript": "old.jsonl",
                    "ceiling": 225000,
                    "reserve": 15000,
                    "task_budget": 20000,
                },
                {"role": "reviewer", "session_id": "peer", "ceiling": 225000},
            ],
        }
        self.control.write_text(json.dumps(self.data))
        self.transcript.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": self.sid}}) + "\n"
        )

    def test_adoption_preserves_policy_and_peer_and_is_repeatable(self):
        adopt(self.control, self.transcript, self.sid)
        expected = copy.deepcopy(self.data)
        expected["notification_thread"] = self.sid
        expected["sessions"][0].update(
            session_id=self.sid, transcript=str(self.transcript)
        )
        self.assertEqual(json.loads(self.control.read_text()), expected)
        adopt(self.control, self.transcript, self.sid)
        self.assertEqual(json.loads(self.control.read_text()), expected)

    def test_refused_identity_or_control_never_writes(self):
        variants = [
            (self.data, "not-a-uuid"),
            (self.data, "01a1b80c-9b3d-7610-8bd7-b279952eb5ed"),
            ({**self.data, "notification_thread": "different"}, self.sid),
            ({**self.data, "sessions": [self.data["sessions"][0]] * 2}, self.sid),
            (
                {
                    **self.data,
                    "sessions": [
                        *self.data["sessions"],
                        {"role": "other", "session_id": self.sid},
                    ],
                },
                self.sid,
            ),
        ]
        for data, sid in variants:
            with self.subTest(data=data, sid=sid):
                self.control.write_text(json.dumps(data))
                original = self.control.read_bytes()
                with self.assertRaises(ValueError):
                    adopt(self.control, self.transcript, sid)
                self.assertEqual(self.control.read_bytes(), original)

    def test_missing_transcript_never_writes(self):
        original = self.control.read_bytes()
        with self.assertRaises(FileNotFoundError):
            adopt(self.control, self.root / "missing", self.sid)
        self.assertEqual(self.control.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
