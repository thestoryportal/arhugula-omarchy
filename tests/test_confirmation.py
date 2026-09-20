import json
from pathlib import Path
import tempfile
import unittest

from runtime.contracts import Interaction, decode, encode
from runtime.core import ConfirmationError, ControlPlane, Outcome
from runtime.journal import MemoryJournal, SQLiteJournal


def record(kind, **patch):
    payload = next(item for item in json.loads(Path("tests/fixtures/contracts-v1.json").read_text()) if item["kind"] == kind)
    return decode({**payload, **patch})


class ConfirmationTests(unittest.TestCase):
    def make(self, journal=None):
        self.calls, self.now = [], [1000]
        self.journal = journal or MemoryJournal()
        return ControlPlane([record("capability", risk="confirm")], record("policy"),
                            lambda command: self.calls.append(command) or Outcome("success"),
                            self.journal, profile=record("profile"), clock=lambda: self.now[0])

    def test_vm_preview_is_immutable_and_all_confirmation_channels_work(self):
        for channel in ("panel", "keyboard", "voice"):
            plane = self.make()
            preview = plane.request_confirmation(record("command"), "focus-1")
            self.assertEqual(self.calls, [])
            self.assertIsInstance(self.journal.read()[0][1], Interaction)
            with self.assertRaises(TypeError):
                preview.command.arguments["name"] = "unsafe"
            result = plane.confirm(preview.token, channel, "focus-1")
            self.assertEqual(result.status, "success")
            self.assertEqual(len(self.calls), 1)
            with self.assertRaises(ConfirmationError):
                plane.confirm(preview.token, channel, "focus-1")

    def test_command_cannot_assert_confirmation_and_direct_dispatch_remains_blocked(self):
        plane = self.make()
        command = record("command")
        with self.assertRaises(ValueError):
            decode({**encode(command), "confirmed": True})
        self.assertEqual(plane.dispatch(command).status, "blocked")
        self.assertEqual(self.calls, [])

    def test_expiry_context_change_denial_and_invalid_channel_never_execute(self):
        for reason in ("expiry", "context", "denial", "channel"):
            plane = self.make()
            preview = plane.request_confirmation(record("command"), "focus-1")
            if reason == "expiry":
                self.now[0] = preview.expires_at_ms
            result = plane.confirm(preview.token, "model" if reason == "channel" else "panel",
                                   "focus-2" if reason == "context" else "focus-1",
                                   approved=reason != "denial")
            self.assertEqual(result.status, "canceled" if reason == "denial" else "blocked")
            self.assertEqual(self.calls, [])

    def test_pending_safe_correction_cannot_be_bypassed_by_direct_dispatch(self):
        plane = ControlPlane([record("capability")], record("policy"),
                             lambda _: self.fail("must not execute"), MemoryJournal(),
                             profile=record("profile"))
        plane.request_confirmation(record("command"), "focus-1")
        self.assertEqual(plane.dispatch(record("command")).status, "blocked")

    def test_journal_failure_prevents_preview_and_confirmation(self):
        plane = self.make()
        self.journal.close()
        with self.assertRaises(ConfirmationError):
            plane.request_confirmation(record("command"), "focus-1")
        self.assertEqual(self.calls, [])
        plane = self.make()
        preview = plane.request_confirmation(record("command"), "focus-1")
        self.journal.close()
        self.assertEqual(plane.confirm(preview.token, "panel", "focus-1").status, "blocked")
        self.assertEqual(self.calls, [])

    def test_safe_preview_requires_approval_across_shared_planes(self):
        calls, journal = [], MemoryJournal()
        def plane():
            return ControlPlane([record("capability")], record("policy"),
                                lambda command: calls.append(command) or Outcome("success"),
                                journal, profile=record("profile"))
        preview = plane().request_confirmation(record("command"), "focus-1")
        result = plane().dispatch(preview.command)
        self.assertEqual(result.error.code if result.error else None, "confirmation.required")
        self.assertEqual(calls, [])

    def test_safe_preview_requires_approval_after_sqlite_reopen(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            def plane(journal):
                return ControlPlane([record("capability")], record("policy"),
                                    lambda command: calls.append(command) or Outcome("success"),
                                    journal, profile=record("profile"))
            with SQLiteJournal(path) as journal:
                preview = plane(journal).request_confirmation(record("command"), "focus-1")
            with SQLiteJournal(path) as journal:
                reopened = plane(journal)
                with self.assertRaises(ConfirmationError):
                    reopened.confirm(preview.token, "panel", "focus-1")
                result = reopened.dispatch(preview.command)
                self.assertEqual(result.error.code if result.error else None, "confirmation.required")
                self.assertEqual(calls, [])

    def test_clarification_observation_does_not_reserve_execution(self):
        calls = []
        plane = ControlPlane([record("capability")], record("policy"),
                             lambda command: calls.append(command) or Outcome("success"),
                             MemoryJournal(), profile=record("profile"))
        command = record("command")
        plane.observe_interaction(command, "voice.clarification", {"reason": "unknown"})
        self.assertEqual(plane.dispatch(command).status, "success")
        self.assertEqual(len(calls), 1)

    def test_mixed_interaction_and_execution_records_reopen_without_poisoning_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite"
            with SQLiteJournal(path) as journal:
                plane = self.make(journal)
                preview = plane.request_confirmation(record("command"), "focus-1")
                self.assertEqual(encode(decode(encode(journal.read()[0][1]))), encode(journal.read()[0][1]))
                self.assertEqual(plane.confirm(preview.token, "keyboard", "focus-1").status, "success")
            with SQLiteJournal(path) as journal:
                plane = self.make(journal)
                self.assertEqual(plane.dispatch(record("command")).error.code, "command.duplicate")
                with self.assertRaises(ConfirmationError):
                    plane.confirm(preview.token, "keyboard", "focus-1")
                self.assertEqual(self.calls, [])
