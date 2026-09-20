import json
from pathlib import Path
import unittest
import threading

from runtime.contracts import decode, encode
from runtime.core import ControlPlane, Outcome


def fixture(kind, **patch):
    payload = next(item for item in json.loads(Path("tests/fixtures/contracts-v1.json").read_text()) if item["kind"] == kind)
    return decode({**payload, **patch})


class RecordingJournal:
    def __init__(self, fail_at=None):
        self.events = []
        self.fail_at = fail_at
        self.dispatch_lock = threading.RLock()

    def append(self, event):
        if len(self.events) == self.fail_at:
            raise OSError("private path must not leak")
        self.events.append(event)
        return len(self.events)

    def read(self, after=0):
        return [(index, event) for index, event in enumerate(self.events, 1) if index > after]


class ControlPlaneTests(unittest.TestCase):
    def make(self, outcome=None, **options):
        self.calls = []
        self.journal = options.pop("journal", RecordingJournal())
        def execute(command):
            self.assertEqual(self.journal.events[-1].event_type, "command.started")
            self.calls.append(command)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome or Outcome("success", {"opened": True})
        return ControlPlane(
            options.pop("catalog", [fixture("capability")]),
            options.pop("policy", fixture("policy")), execute, self.journal,
            profile=options.pop("profile", fixture("profile")), clock=lambda: 2000,
            **options)

    def test_success_is_correlated_and_journaled_before_executor(self):
        result = self.make().dispatch(fixture("command"))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.command_id, "cmd-1")
        self.assertEqual(result.correlation_id, "corr-1")
        self.assertEqual([event.status for event in self.journal.events], ["pending", "success"])
        self.assertEqual(self.journal.events[-1].policy_revision, 1)
        self.assertEqual(self.journal.events[-1].context["session_id"], "session-1")
        self.assertEqual(len(self.calls), 1)

    def test_every_executor_terminal_state_and_exception_uncertainty(self):
        for status in ("success", "failed", "canceled", "uncertain"):
            with self.subTest(status=status):
                error = fixture("error") if status in ("failed", "uncertain") else None
                result = self.make(Outcome(status, {}, error)).dispatch(fixture("command"))
                self.assertEqual(result.status, status)
                self.assertEqual(self.journal.events[-1].status, status)
        result = self.make(RuntimeError("sensitive exception")).dispatch(fixture("command"))
        self.assertEqual(result.status, "uncertain")
        self.assertNotIn("sensitive", json.dumps(encode(result)))

    def test_policy_catalog_profile_arguments_and_confirmation_deny_before_execution(self):
        cases = [
            ({"catalog": []}, {}),
            ({"catalog": [fixture("capability", enabled=False)]}, {}),
            ({"catalog": [fixture("capability", risk="blocked")]}, {}),
            ({"catalog": [fixture("capability", risk="confirm")]}, {}),
            ({"policy": fixture("policy", enabled=False)}, {}),
            ({"policy": fixture("policy", allowed_capabilities=[])}, {}),
            ({"policy": fixture("policy", confirmation_required=["menu.open"])}, {}),
            ({"profile": fixture("profile", enabled=False)}, {}),
            ({"profile": fixture("profile", policy_id="other")}, {}),
            ({}, {"catalog_version": 2}),
            ({}, {"arguments": {"name": 1}}),
            ({}, {"arguments": {"name": "main", "shell": "echo"}}),
            ({}, {"context": {**encode(fixture("command"))["context"], "profile_id": "other"}}),
            ({}, {"context": {**encode(fixture("command"))["context"], "source": "voice"}}),
        ]
        for options, patch in cases:
            with self.subTest(options=options, patch=patch):
                result = self.make(**options).dispatch(fixture("command", **patch))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(self.calls, [])
                self.assertEqual(self.journal.events[-1].status, "blocked")

    def test_cancellation_duplicate_and_restart_never_reexecute(self):
        plane = self.make()
        self.assertEqual(plane.dispatch(fixture("command"), canceled=True).status, "canceled")
        self.assertEqual(self.calls, [])
        self.assertEqual(plane.dispatch(fixture("command")).status, "blocked")
        journal = self.journal
        restarted = self.make(journal=journal)
        self.assertEqual(restarted.dispatch(fixture("command")).status, "blocked")
        self.assertEqual(self.calls, [])

    def test_journal_failure_blocks_before_execution_and_is_uncertain_after(self):
        for fail_at, status, count in [(0, "blocked", 0), (1, "uncertain", 1)]:
            with self.subTest(fail_at=fail_at):
                plane = self.make(journal=RecordingJournal(fail_at))
                result = plane.dispatch(fixture("command"))
                self.assertEqual(result.status, status)
                self.assertEqual(result.error.code, "journal.unavailable")
                self.assertEqual(len(self.calls), count)
                plane.dispatch(fixture("command"))
                self.assertEqual(len(self.calls), count)

    def test_invalid_executor_outcome_is_uncertain(self):
        for outcome in (Outcome("pending", {}), Outcome("success", {"bad": object()}), Outcome("success", []), "not an outcome"):
            result = self.make(outcome).dispatch(fixture("command"))
            self.assertEqual(result.status, "uncertain")

    def test_duplicate_catalog_ids_fail_at_configuration_boundary(self):
        with self.assertRaises(ValueError):
            self.make(catalog=[fixture("capability"), fixture("capability")])

    def test_multiple_dispatchers_share_journal_execution_history(self):
        first = self.make()
        second = self.make(journal=self.journal)
        self.assertEqual(first.dispatch(fixture("command")).status, "success")
        self.assertEqual(second.dispatch(fixture("command")).status, "blocked")
        self.assertEqual(len(self.calls), 1)

    def test_boolean_does_not_satisfy_integer_argument(self):
        plane = self.make(catalog=[fixture("capability", arguments={"count": "integer"})])
        self.assertEqual(plane.dispatch(fixture("command", arguments={"count": True})).status, "blocked")
        self.assertEqual(self.calls, [])
