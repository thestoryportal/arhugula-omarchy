"""Behavioral checks for local session metadata and admission."""

import json
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

from ops.orchestration.session_context import (
    NotificationError,
    admit,
    inspect_transcript,
    main,
    watch_once,
)


def _codex(kind, payload, at="2026-09-23T03:00:00Z"):
    return {"timestamp": at, "type": kind, "payload": payload}


def _claude(kind, *, message=None, subtype=None, at="2026-09-23T03:00:00Z", **extra):
    record = {"timestamp": at, "type": kind, "sessionId": "claude-1", **extra}
    if message is not None:
        record["message"] = message
    if subtype is not None:
        record["subtype"] = subtype
    return record


def _usage(inputs, cached=0):
    return {"input_tokens": inputs, "cached_input_tokens": cached}


def _claude_message(identifier, inputs, cache_read, cache_write, stop):
    return {
        "id": identifier,
        "model": "claude-opus-test",
        "stop_reason": stop,
        "usage": {
            "input_tokens": inputs,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
        },
        "content": [{"type": "text", "text": "secret transcript body"}],
    }


class SessionContextTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "session.jsonl"

    def write(self, *records, fragment=None):
        data = "".join(json.dumps(record) + "\n" for record in records)
        if fragment:
            data += fragment
        self.path.write_text(data)

    def test_codex_cached_input_is_already_in_request_total(self):
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("turn_context", {"model": "gpt-6-sol"}),
            _codex("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            _codex(
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": _usage(120, 100),
                        "model_context_window": 1000,
                    },
                },
            ),
            _codex("event_msg", {"type": "task_complete", "turn_id": "turn-1"}),
        )
        result = inspect_transcript("codex", self.path)
        self.assertEqual(result["session_id"], "codex-1")
        self.assertEqual(result["model"], "gpt-6-sol")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["latest_request_input_tokens"], 120)
        self.assertEqual(result["cached_input_tokens"], 100)
        self.assertEqual(result["reported_context_window_tokens"], 1000)
        self.assertNotIn("secret transcript body", json.dumps(result))

    def test_codex_session_meta_window_id_is_not_a_capacity(self):
        self.write(
            _codex(
                "session_meta",
                {"session_id": "codex-1", "context_window": {"window_id": "opaque"}},
            ),
            _codex(
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": _usage(80, 60),
                        "model_context_window": 1000,
                    },
                },
            ),
        )
        result = inspect_transcript("codex", self.path)
        self.assertEqual(result["reported_context_window_tokens"], 1000)
        self.assertIsNone(result["metric_error"])

    def test_claude_repeated_response_blocks_are_one_request(self):
        first = _claude_message("msg-1", 2, 40, 8, "tool_use")
        second = _claude_message("msg-2", 3, 50, 10, "end_turn")
        self.write(
            _claude("user", message={"content": "secret user body"}),
            _claude("assistant", message=first),
            _claude("assistant", message=first),
            _claude("assistant", message=second),
        )
        result = inspect_transcript("claude", self.path)
        self.assertEqual(result["latest_request_input_tokens"], 63)
        self.assertEqual(result["observed_responses"], 2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["model"], "claude-opus-test")
        self.assertNotIn("secret", json.dumps(result))

    def test_claude_later_block_of_same_response_can_finalize_usage(self):
        partial = {
            "id": "msg-1",
            "model": "claude-opus-test",
            "stop_reason": None,
            "content": [{"type": "text", "text": "private partial"}],
        }
        final = _claude_message("msg-1", 2, 40, 8, "end_turn")
        self.write(
            _claude("assistant", message=partial), _claude("assistant", message=final)
        )
        result = inspect_transcript("claude", self.path)
        self.assertEqual(result["observed_responses"], 1)
        self.assertEqual(result["latest_request_input_tokens"], 50)
        self.assertEqual(result["status"], "complete")

    def test_completion_active_and_interrupted_are_distinct(self):
        self.write(_codex("session_meta", {"session_id": "codex-1"}))
        self.assertEqual(inspect_transcript("codex", self.path)["status"], "unknown")
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        )
        self.assertEqual(inspect_transcript("codex", self.path)["status"], "active")
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            _codex("event_msg", {"type": "turn_aborted", "turn_id": "turn-1"}),
        )
        self.assertEqual(inspect_transcript("codex", self.path)["status"], "unknown")

    def test_compaction_metadata_is_separate_from_next_request(self):
        self.write(
            _claude(
                "assistant", message=_claude_message("msg-1", 2, 60, 8, "end_turn")
            ),
            _claude(
                "system",
                subtype="compact_boundary",
                compactMetadata={"trigger": "auto", "preTokens": 70, "postTokens": 20},
            ),
            _claude(
                "assistant", message=_claude_message("msg-2", 2, 24, 4, "end_turn")
            ),
        )
        result = inspect_transcript("claude", self.path)
        self.assertEqual(
            result["compactions"],
            [
                {
                    "time": "2026-09-23T03:00:00Z",
                    "pre_tokens": 70,
                    "post_tokens": 20,
                    "trigger": "auto",
                }
            ],
        )
        self.assertEqual(result["latest_request_input_tokens"], 30)
        self.assertIsNone(result["reported_context_window_tokens"])

    def test_codex_compaction_has_no_invented_post_tokens(self):
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex(
                "compacted", {"latest_token_usage_record": {"usage": _usage(220, 20)}}
            ),
            _codex("event_msg", {"type": "context_compacted"}),
            _codex(
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": _usage(90, 70),
                        "model_context_window": 1000,
                    },
                },
            ),
        )
        result = inspect_transcript("codex", self.path)
        self.assertEqual(len(result["compactions"]), 1)
        self.assertEqual(result["compactions"][0]["pre_tokens"], 220)
        self.assertIsNone(result["compactions"][0]["post_tokens"])
        self.assertEqual(result["latest_request_input_tokens"], 90)

    def test_inspect_bounds_compaction_details_while_retaining_total(self):
        self.write(
            *[
                _claude(
                    "system",
                    subtype="compact_boundary",
                    at=f"2026-09-23T03:00:0{number}Z",
                    compactMetadata={
                        "trigger": "auto",
                        "preTokens": 100 + number,
                        "postTokens": 20 + number,
                    },
                )
                for number in range(5)
            ]
        )
        result = inspect_transcript("claude", self.path)
        self.assertEqual(result["compaction_count"], 5)
        self.assertLessEqual(len(result["compactions"]), 3)
        self.assertEqual(result["compactions"][-1]["pre_tokens"], 104)
        self.assertNotIn("completion_times", result)

    def test_partial_active_line_is_tolerated_but_invalid_completed_line_fails(self):
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            fragment='{"type":"event_msg"',
        )
        result = inspect_transcript("codex", self.path)
        self.assertEqual(result["status"], "active")
        self.assertTrue(result["partial_tail"])
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("event_msg", {"type": "task_complete", "turn_id": "turn-1"}),
            fragment='{"type":"event_msg"',
        )
        with self.assertRaisesRegex(ValueError, "truncated"):
            inspect_transcript("codex", self.path)
        self.write(
            _codex("session_meta", {"session_id": "codex-1"}),
            _codex("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            fragment="not-json\n",
        )
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            inspect_transcript("codex", self.path)

    def test_admission_requires_explicit_ceiling_and_complete_matching_identity(self):
        summary = {
            "session_id": "codex-1",
            "status": "complete",
            "latest_request_input_tokens": 70,
        }
        self.assertEqual(
            admit(
                summary,
                task_budget=20,
                reserve=10,
                ceiling=100,
                expected_session_id="codex-1",
            )["decision"],
            "allow",
        )
        self.assertEqual(
            admit(summary, task_budget=21, reserve=10, ceiling=100)["decision"], "hold"
        )
        self.assertIn(
            "paused",
            admit(summary, task_budget=1, reserve=1, ceiling=100, paused=True)[
                "reasons"
            ],
        )
        self.assertIn(
            "session-id-mismatch",
            admit(
                summary,
                task_budget=1,
                reserve=1,
                ceiling=100,
                expected_session_id="stale",
            )["reasons"],
        )
        for status in ("active", "unknown"):
            self.assertIn(
                "session-not-complete",
                admit(
                    {**summary, "status": status}, task_budget=1, reserve=1, ceiling=100
                )["reasons"],
            )
        self.assertIn(
            "missing-request-metric",
            admit(
                {**summary, "latest_request_input_tokens": None},
                task_budget=1,
                reserve=1,
                ceiling=100,
            )["reasons"],
        )
        self.assertIn(
            "invalid-ceiling",
            admit(summary, task_budget=1, reserve=1, ceiling=0)["reasons"],
        )
        self.assertIn(
            "session-id-conflict",
            admit(
                {**summary, "identity_conflict": True},
                task_budget=1,
                reserve=1,
                ceiling=100,
            )["reasons"],
        )
        self.assertIn(
            "missing-session-id",
            admit(
                {**summary, "session_id": None}, task_budget=1, reserve=1, ceiling=100
            )["reasons"],
        )


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.transcript = root / "claude.jsonl"
        self.config = root / "config.json"
        self.state = root / "state.json"
        self.events = root / "events.jsonl"
        self.configure()

    def configure(self, *, paused=False, session_id="claude-1", thread=None):
        self.config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "repair_paused": paused,
                    "notification_thread": thread,
                    "ticket": "arhugula-orchestration-7ji",
                    "sessions": [
                        {
                            "role": "reviewer",
                            "kind": "claude",
                            "session_id": session_id,
                            "transcript": str(self.transcript),
                            "ceiling": 100,
                            "task_budget": 20,
                            "reserve": 10,
                        }
                    ],
                }
            )
        )

    def append(self, *records):
        with self.transcript.open("a") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")

    def test_events_are_incremental_and_deduplicated_across_restart(self):
        self.append(
            _claude("user", message={"content": "private instruction"}),
            _claude(
                "assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn")
            ),
            _claude(
                "system",
                subtype="compact_boundary",
                compactMetadata={"trigger": "auto", "preTokens": 60, "postTokens": 20},
            ),
        )
        first = watch_once(self.config, self.state, self.events)
        self.assertEqual(
            {event["type"] for event in first},
            {"completion", "compaction", "admission"},
        )
        self.assertEqual(watch_once(self.config, self.state, self.events), [])
        initial_lines = self.events.read_text().splitlines()
        self.assertEqual(len(initial_lines), 3)
        self.assertNotIn(
            "private instruction", self.state.read_text() + self.events.read_text()
        )

        self.append(
            _claude("user", message={"content": "another private instruction"}),
            _claude(
                "assistant", message=_claude_message("msg-2", 2, 70, 8, "end_turn")
            ),
        )
        changed = watch_once(self.config, self.state, self.events)
        self.assertEqual(
            {event["type"] for event in changed}, {"completion", "admission"}
        )
        self.assertEqual(
            next(event for event in changed if event["type"] == "admission")[
                "decision"
            ],
            "hold",
        )
        self.assertEqual(watch_once(self.config, self.state, self.events), [])
        self.assertEqual(len(self.events.read_text().splitlines()), 5)

    def test_notification_failure_retries_without_duplicate_event(self):
        self.configure(thread="12345678-1234-1234-1234-123456789abc")
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        calls = []

        def fail(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 1, "", "queue unavailable")

        with self.assertRaisesRegex(NotificationError, "queue unavailable"):
            watch_once(
                self.config, self.state, self.events, notify=True, queue_runner=fail
            )
        before = self.events.read_text().splitlines()
        self.assertTrue(before)
        self.assertEqual(calls[0][0][:2], ["codex", "queue"])
        self.assertNotIn("secret", json.dumps(calls))

        def succeed(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, "queued", "")

        self.assertEqual(
            watch_once(
                self.config, self.state, self.events, notify=True, queue_runner=succeed
            ),
            [],
        )
        self.assertEqual(self.events.read_text().splitlines(), before)
        self.assertEqual(
            watch_once(
                self.config, self.state, self.events, notify=True, queue_runner=succeed
            ),
            [],
        )
        self.assertEqual(len(calls), 1 + len(before))

    def test_repair_pause_blocks_admission_and_all_notifications(self):
        self.configure(paused=True, thread="12345678-1234-1234-1234-123456789abc")
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        calls = []

        def queue(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "queued", "")

        events = watch_once(
            self.config, self.state, self.events, notify=True, queue_runner=queue
        )
        admission = next(event for event in events if event["type"] == "admission")
        self.assertEqual(admission["decision"], "hold")
        self.assertIn("paused", admission["reasons"])
        self.assertEqual(calls, [])
        self.assertEqual(
            watch_once(
                self.config, self.state, self.events, notify=True, queue_runner=queue
            ),
            [],
        )
        self.assertEqual(calls, [])

    def test_stale_configured_identity_holds_without_completion_event(self):
        self.configure(session_id="another-session")
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        events = watch_once(self.config, self.state, self.events)
        self.assertEqual([event["type"] for event in events], ["admission"])
        self.assertIn("session-id-mismatch", events[0]["reasons"])

    def test_admission_transition_back_to_prior_decision_emits_again(self):
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        first = watch_once(self.config, self.state, self.events)
        first_admission = next(event for event in first if event["type"] == "admission")
        self.configure(paused=True)
        second = watch_once(self.config, self.state, self.events)
        self.assertEqual([event["type"] for event in second], ["admission"])
        self.configure(paused=False)
        third = watch_once(self.config, self.state, self.events)
        self.assertEqual([event["type"] for event in third], ["admission"])
        self.assertEqual(third[0]["decision"], "allow")
        self.assertNotEqual(third[0]["event_id"], first_admission["event_id"])

    def test_event_written_before_state_checkpoint_recovers_notification(self):
        thread = "12345678-1234-1234-1234-123456789abc"
        self.configure(thread=thread)
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        calls = []

        def queue(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "queued", "")

        watch_once(self.config, self.state, self.events)
        recorded = self.events.read_text().splitlines()
        self.state.unlink()  # Simulate a crash after event fsync but before state checkpoint.
        self.assertEqual(
            watch_once(
                self.config, self.state, self.events, notify=True, queue_runner=queue
            ),
            [],
        )
        self.assertEqual(self.events.read_text().splitlines(), recorded)
        self.assertEqual(len(calls), len(recorded))

    def test_cli_inspect_and_admit_emit_json_and_hold_exit_status(self):
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "inspect",
                        "--kind",
                        "claude",
                        "--transcript",
                        str(self.transcript),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(output.getvalue())["latest_request_input_tokens"], 50
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertNotEqual(
                main(
                    [
                        "admit",
                        "--kind",
                        "claude",
                        "--transcript",
                        str(self.transcript),
                        "--task-budget",
                        "60",
                        "--reserve",
                        "10",
                        "--ceiling",
                        "100",
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(output.getvalue())["decision"], "hold")

    def test_continuous_watch_terminates_on_sigterm_after_checkpoint(self):
        self.append(
            _claude("assistant", message=_claude_message("msg-1", 2, 40, 8, "end_turn"))
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "ops.orchestration.session_context",
                "watch",
                "--config",
                str(self.config),
                "--state",
                str(self.state),
                "--events",
                str(self.events),
                "--interval",
                "30",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            deadline = time.monotonic() + 3
            while (
                not self.state.exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertTrue(
                self.state.exists(), "watch never reached its first checkpoint"
            )
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=2)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('"emitted"', stdout)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)


if __name__ == "__main__":
    unittest.main()
