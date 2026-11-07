import copy
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from adopt_root import adopt, update_control


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

    def test_peer_writer_racing_replacement_preserves_both_updates(self):
        attempted = threading.Event()
        failures = []
        real_replace, real_flock = os.replace, fcntl.flock

        def peer_update():
            try:

                def transform(control):
                    control["sessions"][1]["session_id"] = "peer-new"
                    control["repair_paused"] = False
                    control["sessions"][1]["ceiling"] = 190000
                    return control

                update_control(self.control, transform)
            except Exception as error:
                failures.append(error)

        peer = threading.Thread(target=peer_update, name="peer-writer")

        def flock(descriptor, operation):
            if threading.current_thread() is peer:
                attempted.set()
            return real_flock(descriptor, operation)

        def replace(source, destination):
            if threading.current_thread() is not peer:
                peer.start()
                self.assertTrue(attempted.wait(5), "peer never attempted update")
            return real_replace(source, destination)

        with (
            patch("adopt_root.fcntl.flock", side_effect=flock),
            patch("adopt_root.os.replace", side_effect=replace),
        ):
            try:
                adopt(self.control, self.transcript, self.sid)
            finally:
                if peer.ident is not None:
                    peer.join(5)
        self.assertFalse(peer.is_alive())
        self.assertEqual(failures, [])
        result = json.loads(self.control.read_text())
        self.assertEqual(result["notification_thread"], self.sid)
        self.assertEqual(result["sessions"][1]["session_id"], "peer-new")
        self.assertEqual(result["sessions"][1]["ceiling"], 190000)
        self.assertFalse(result["repair_paused"])

    def test_syncs_replacement_then_directory_and_surfaces_sync_failure(self):
        real_sync = os.fsync
        for fail_directory in (False, True):
            with self.subTest(fail_directory=fail_directory):
                kinds = []

                def sync(descriptor):
                    directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
                    kinds.append("directory" if directory else "file")
                    if directory:
                        self.assertEqual(
                            json.loads(self.control.read_text())["notification_thread"],
                            self.sid,
                        )
                        if fail_directory:
                            raise OSError("directory sync failed")
                    real_sync(descriptor)

                with patch("adopt_root.os.fsync", side_effect=sync):
                    if fail_directory:
                        with self.assertRaisesRegex(OSError, "directory sync failed"):
                            adopt(self.control, self.transcript, self.sid)
                    else:
                        adopt(self.control, self.transcript, self.sid)
                self.assertEqual(kinds, ["file", "directory"])
                self.assertEqual(
                    {p.name for p in self.root.iterdir()},
                    {"control.json", "control.json.lock", "native.jsonl"},
                )


if __name__ == "__main__":
    unittest.main()
