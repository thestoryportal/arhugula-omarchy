import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from runtime.contracts import decode, encode
from runtime.core import ControlPlane, Outcome
from runtime.journal import JournalError, MemoryJournal, SQLiteJournal


def record(kind, **patch):
    payload = next(item for item in json.loads(Path("tests/fixtures/contracts-v1.json").read_text()) if item["kind"] == kind)
    return decode({**payload, **patch})


class JournalTests(unittest.TestCase):
    def test_both_adapters_order_deduplicate_conflict_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            for journal in (MemoryJournal(), SQLiteJournal(Path(directory) / "events.sqlite")):
                with journal, self.subTest(adapter=type(journal).__name__):
                    event = record("event")
                    self.assertEqual(journal.append(event), 1)
                    self.assertEqual(journal.append(event), 1)
                    self.assertEqual(journal.append(record("event", event_id="event-2")), 2)
                    with self.assertRaises(JournalError):
                        journal.append(record("event", status="failed"))
                    self.assertEqual([seq for seq, _ in journal.read()], [1, 2])
                    self.assertEqual([seq for seq, _ in journal.read(after=1)], [2])
                    projection = []
                    journal.replay(lambda seq, item: projection.append((seq, item.command_id)))
                    self.assertEqual(projection, [(1, "cmd-1"), (2, "cmd-1")])
                    self.assertEqual(encode(journal.read()[0][1]), encode(event))
                    for bad in (-1, True, "0"):
                        with self.assertRaises(ValueError):
                            journal.read(after=bad)
                    with self.assertRaises(ValueError):
                        journal.append(record("command"))

    def test_reopen_preserves_sequence_correlation_and_dispatch_suppression(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            calls = []
            with SQLiteJournal(path) as journal:
                plane = ControlPlane([record("capability")], record("policy"),
                                     lambda command: calls.append(command) or Outcome("success"),
                                     journal, profile=record("profile"))
                self.assertEqual(plane.dispatch(record("command")).status, "success")
            with SQLiteJournal(path) as journal:
                self.assertEqual([event.status for _, event in journal.read()], ["pending", "success"])
                self.assertEqual(journal.read()[0][1].correlation_id, "corr-1")
                plane = ControlPlane([record("capability")], record("policy"),
                                     lambda command: calls.append(command) or Outcome("success"),
                                     journal, profile=record("profile"))
                self.assertEqual(plane.dispatch(record("command")).status, "blocked")
                self.assertEqual(len(calls), 1)
                self.assertEqual([seq for seq, _ in journal.read()], [1, 2, 3])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_second_owner_is_rejected_and_close_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path):
                with self.assertRaises(JournalError):
                    SQLiteJournal(path)
            with SQLiteJournal(path) as journal:
                self.assertEqual(journal.read(), [])

    def test_interrupted_execution_remains_nonretryable_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path) as journal:
                journal.append(record("event", event_type="command.started", status="pending"))
            with SQLiteJournal(path) as journal:
                calls = []
                plane = ControlPlane([record("capability")], record("policy"), calls.append,
                                     journal, profile=record("profile"))
                result = plane.dispatch(record("command"))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(calls, [])

    def test_unknown_database_version_refused_without_mutating_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path):
                pass
            connection = sqlite3.connect(path)
            with connection:
                connection.execute("PRAGMA user_version=2")
            connection.close()
            original = path.read_bytes()
            with self.assertRaises(JournalError):
                SQLiteJournal(path)
            self.assertEqual(path.read_bytes(), original)

    def test_symlinks_and_nonprivate_existing_database_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path):
                pass
            link = Path(directory) / "linked.sqlite"
            link.symlink_to(path)
            with self.assertRaises(JournalError):
                SQLiteJournal(link)
            os.chmod(path, 0o644)
            with self.assertRaises(JournalError):
                SQLiteJournal(path)

    def test_corrupt_event_is_not_silently_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path) as journal:
                journal.append(record("event"))
            connection = sqlite3.connect(path)
            with connection:
                connection.execute("UPDATE events SET payload = '{}' WHERE sequence = 1")
            connection.close()
            with SQLiteJournal(path) as journal:
                with self.assertRaises(JournalError):
                    journal.read()
