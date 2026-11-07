from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "watcher", Path(__file__).with_name("watcher.py")
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.control = self.root / "control.json"
        self.transcript = self.root / "native.jsonl"
        self.transcript.write_text("")
        self.control.write_text(
            json.dumps(
                {
                    "notification_thread": "root-a",
                    "sessions": [
                        {
                            "role": "reviewer",
                            "session_id": "peer-a",
                            "transcript": str(self.transcript),
                        }
                    ],
                }
            )
        )
        self.config = {
            "cwd": str(self.root),
            "session_control": str(self.control),
            "database": str(self.root / "events.sqlite"),
            "roles": ["reviewer"],
            "activation_epoch": 1000,
        }
        self.clock = 1000
        self.calls = []
        self.comments = []
        self.pr = {
            "state": "OPEN",
            "headRefOid": "a",
            "statusCheckRollup": [{"name": "ci", "status": "IN_PROGRESS"}],
            "url": "https://example.test/pr/1",
        }
        self.queue_result = None
        self.pulls = []
        self.db = sqlite3.connect(self.config["database"])
        self.addCleanup(self.db.close)
        self.w = module.Watcher(self.config, self.db, self.command, lambda: self.clock)

    def command(self, argv, cwd, timeout=12):
        self.calls.append(argv)
        if argv[:2] == ["lit", "export"]:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"comments": self.comments}), ""
            )
        if argv[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.pr), "")
        if argv[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.pulls), "")
        if argv[:2] == ["codex", "queue"]:
            if isinstance(self.queue_result, BaseException):
                raise self.queue_result
            if self.queue_result is not None:
                return self.queue_result
            return subprocess.CompletedProcess(
                argv, 0, f"Queued message 01234567-abcd for thread {argv[3]}.\n", ""
            )
        raise AssertionError(argv)

    def status(self):
        return self.db.execute("SELECT status FROM events ORDER BY id").fetchall()

    def event(self, name="one"):
        with self.db:
            self.w.event(name, "test", "ticket comment", "advance")

    def append(self, record):
        with self.transcript.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def claude_launcher(self, call_id="launch"):
        self.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": call_id,
                            "name": "Bash",
                            "input": {
                                "command": "/plugin/bin/finalize-session -- 'same claim'"
                            },
                        }
                    ]
                },
            }
        )

    def test_success_dedup_and_bundle(self):
        self.event()
        self.event()
        self.event("two")
        self.w.dispatch()
        self.w.dispatch()
        self.assertEqual(self.status(), [("sent",), ("sent",)])
        self.assertEqual(sum(c[:2] == ["codex", "queue"] for c in self.calls), 1)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1
        )

    def test_route_resolved_at_send(self):
        self.event()
        control = json.loads(self.control.read_text())
        control["notification_thread"] = "root-new"
        self.control.write_text(json.dumps(control))
        self.w.dispatch()
        self.assertEqual(self.calls[-1][3], "root-new")

    def test_uncertain_not_replayed(self):
        self.event()
        self.queue_result = subprocess.TimeoutExpired("codex", 12)
        self.w.dispatch()
        self.w.dispatch()
        self.assertEqual(self.status(), [("uncertain",)])
        self.assertEqual(len(self.calls), 1)

    def test_crash_after_dispatch_boundary_not_replayed(self):
        self.event()
        with self.db:
            self.db.execute("UPDATE events SET status='sending'")
        recovered = module.Watcher(
            self.config, self.db, self.command, lambda: self.clock
        )
        recovered.dispatch()
        self.assertEqual(self.status(), [("uncertain",)])
        self.assertEqual(self.calls, [])

    def test_unknown_nonzero_and_unrecognized_success_are_uncertain(self):
        for result in [
            subprocess.CompletedProcess([], 1, "", "connection broke"),
            subprocess.CompletedProcess([], 0, "unknown acknowledgement", ""),
        ]:
            with self.db:
                self.db.execute("DELETE FROM events")
                self.db.execute("DELETE FROM outbox")
            self.event()
            self.queue_result = result
            self.w.dispatch()
            self.assertEqual(self.status(), [("uncertain",)])

    def test_known_predispatch_failure_retries_after_delay(self):
        self.event()
        self.queue_result = subprocess.CompletedProcess(
            [],
            1,
            "",
            "failed to initialize state database: attempt to write a readonly database",
        )
        self.w.dispatch()
        self.w.dispatch()
        self.assertEqual(len(self.calls), 1)
        self.clock += 61
        self.queue_result = None
        self.w.dispatch()
        self.assertEqual(self.status(), [("sent",)])
        self.assertEqual(len(self.calls), 2)

    def test_lit_cutoff_and_stable_id(self):
        self.comments = [
            {
                "id": "old",
                "issue_id": "arhugula-harness-trial-193.4h4",
                "created_at": "1970-01-01T00:16:39Z",
                "body": "GREEN",
            },
            {
                "id": "new",
                "issue_id": "arhugula-harness-trial-193.4h4",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "GREEN TO reviewer",
            },
            {
                "id": "other",
                "issue_id": "unrelated",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "GREEN",
            },
        ]
        self.w.poll()
        self.w.poll()
        self.assertEqual(
            self.db.execute("SELECT pointer FROM events").fetchall(),
            [("arhugula-harness-trial-193.4h4 new",)],
        )
        self.assertIn("pending:reviewer", self.w.state)

    def test_root_self_status_skipped_but_peer_result_kept(self):
        self.comments = [
            {
                "id": "root",
                "issue_id": "arhugula-harness-trial-193",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "FROM Buford integration lead root TO record. GREEN result",
            },
            {
                "id": "peer",
                "issue_id": "arhugula-harness-trial-193.4h4",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "FROM implementer reviewer TO Buford integration lead. GREEN",
            },
        ]
        self.w.poll()
        self.assertEqual(
            self.db.execute("SELECT pointer FROM events").fetchall(),
            [("arhugula-harness-trial-193.4h4 peer",)],
        )

    def test_scheduled_timeout_and_successor_receipt(self):
        self.w.poll()
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "launch",
                    "name": "exec",
                    "input": "text(await tools.exec_command({cmd:\"/plugin/bin/finalize-session -- 'same claim'\"}));",
                },
            }
        )
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "launch",
                    "output": "handoff scheduled → foot codex",
                },
            }
        )
        self.w.poll()
        self.clock += 120
        self.w.poll()
        self.w.poll()
        actions = [r[0] for r in self.db.execute("SELECT action FROM events")]
        self.assertEqual(sum("No successor" in a for a in actions), 1)
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "internal_chat_message_metadata_passthrough": {
                        "content_item_kinds": ["user.text"]
                    },
                    "content": [
                        {"text": "Read and follow the handoff at /tmp/bottle.md"}
                    ],
                },
            }
        )
        self.w.poll()
        self.assertNotIn("memento:reviewer", self.w.state)

    def test_partial_record_waits_and_claude_end_turn_emits(self):
        self.w.poll()
        record = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "GREEN"}],
                },
            }
        )
        self.transcript.write_text(record)
        self.w.poll()
        self.assertEqual(self.status(), [])
        with self.transcript.open("a") as f:
            f.write("\n")
        self.w.poll()
        self.w.poll()
        self.assertEqual(len(self.status()), 2)

    def test_claude_tool_result_is_not_user_uptake(self):
        self.w.poll()
        self.w.state["pending:reviewer"] = {"at": self.clock, "pointer": "comment-x"}
        self.claude_launcher()
        self.append(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "launch",
                            "content": "handoff scheduled → foot claude",
                        }
                    ]
                },
            }
        )
        self.w.poll()
        self.assertIn("pending:reviewer", self.w.state)
        self.assertIn("memento:reviewer", self.w.state)

    def test_green_in_tool_output_is_not_new_review_verdict(self):
        self.w.poll()
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "historical LIT GREEN",
                },
            }
        )
        self.w.poll()
        self.assertEqual(self.status(), [])

    def test_policy_source_and_cached_tool_results_are_not_memento_or_freeze_results(
        self,
    ):
        self.w.poll()
        policy = "A failed handoff holds its own lane; frozen candidates require GREEN. handoff scheduled → example"
        self.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "read",
                            "name": "Bash",
                            "input": {
                                "command": "cat docs/orchestration/context-policy.md"
                            },
                        }
                    ]
                },
            }
        )
        result = {
            "content": [
                {"type": "tool_result", "tool_use_id": "read", "content": policy}
            ]
        }
        self.append({"type": "user", "message": result})
        self.append({"type": "api-request-blob", "message": result})
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "read",
                    "output": policy,
                },
            }
        )
        self.w.poll()
        self.assertEqual(self.status(), [])
        self.assertNotIn("memento:reviewer", self.w.state)

    def test_claude_actual_launcher_failure_survives_poll_and_restart(self):
        self.w.poll()
        self.claude_launcher()
        self.w.poll()
        recovered = module.Watcher(
            self.config, self.db, self.command, lambda: self.clock
        )
        self.append(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "launch",
                            "content": "codex-foot-helper: refused; uncertain handoff",
                        }
                    ]
                },
            }
        )
        recovered.poll()
        recovered.poll()
        self.assertEqual(
            self.db.execute("SELECT action FROM events").fetchall(),
            [
                (
                    "Memento failed or uncertain; inspect and apply authorized bounded recovery",
                )
            ],
        )

    def test_cached_launcher_records_do_not_manufacture_a_native_receipt(self):
        self.w.poll()
        self.append(
            {
                "type": "api-request-blob",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "fake",
                            "name": "Bash",
                            "input": {
                                "command": "/plugin/bin/finalize-session -- 'old claim'"
                            },
                        }
                    ]
                },
            }
        )
        self.append(
            {
                "type": "api-request-blob",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "fake",
                            "content": "cannot write the handoff; handoff scheduled → stale",
                        }
                    ]
                },
            }
        )
        self.w.poll()
        self.assertEqual(self.status(), [])

    def test_codex_launcher_failure_and_final_verdict_are_retained(self):
        self.w.poll()
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "native",
                    "name": "exec_command",
                    "arguments": json.dumps(
                        {"cmd": "/plugin/bin/finalize-session -- 'same claim'"}
                    ),
                },
            }
        )
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "native",
                    "output": "cannot write the handoff",
                },
            }
        )
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [
                        {"type": "output_text", "text": "GREEN; frozen candidate abc"}
                    ],
                },
            }
        )
        self.w.poll()
        actions = [r[0] for r in self.db.execute("SELECT action FROM events")]
        self.assertEqual(sum("Memento failed" in a for a in actions), 1)
        self.assertEqual(sum("review/freeze" in a for a in actions), 1)

    def test_only_final_assistant_text_is_a_result(self):
        self.w.poll()
        self.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Reading source containing GREEN and handoff failure",
                        }
                    ],
                },
            }
        )
        self.append(
            {
                "type": "assistant",
                "message": {
                    "stop_reason": "tool_use",
                    "content": [
                        {
                            "type": "text",
                            "text": "The policy mentions frozen candidates and handoff failures.",
                        }
                    ],
                },
            }
        )
        self.w.poll()
        self.assertEqual(self.status(), [])
        self.append(
            {
                "type": "assistant",
                "message": {
                    "stop_reason": "end_turn",
                    "content": [
                        {
                            "type": "text",
                            "text": "Memento handoff failed; saved bottle retained.",
                        }
                    ],
                },
            }
        )
        self.w.poll()
        self.assertEqual(len(self.status()), 2)

    def test_idle_pending_and_observation_failure_dedupe(self):
        self.w.state["pending:reviewer"] = {"at": self.clock, "pointer": "comment-x"}
        self.clock += 120
        self.w.poll()
        self.w.poll()
        self.assertEqual(
            sum(
                "Idle role" in x[0]
                for x in self.db.execute("SELECT action FROM events")
            ),
            1,
        )
        self.transcript.unlink()
        self.w.poll()
        self.w.poll()
        self.assertEqual(
            sum(
                "Observation failed" in x[0]
                for x in self.db.execute("SELECT action FROM events")
            ),
            1,
        )

    def test_pr_initial_baseline_then_terminal_transition(self):
        self.config["prs"] = [{"repo": "owner/repo", "number": 1}]
        self.w.poll()
        self.assertEqual(self.status(), [])
        self.pr["statusCheckRollup"] = [
            {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}
        ]
        self.clock += 60
        self.w.poll()
        self.w.poll()
        self.assertEqual(len(self.status()), 1)

    def test_github_failure_stays_deduped_between_due_polls(self):
        self.config["prs"] = [{"repo": "owner/repo", "number": 1}]
        original = self.w.command

        def failed(argv, cwd, timeout=12):
            if argv[:2] == ["gh", "pr"]:
                raise subprocess.TimeoutExpired("gh", 12)
            return original(argv, cwd)

        self.w.command = failed
        self.w.poll()
        self.clock += 15
        self.w.poll()
        self.assertIn("error:github", self.w.state)
        self.clock += 46
        self.w.poll()
        self.assertEqual(len(self.status()), 1)
        self.w.command = original
        self.clock += 61
        self.w.poll()
        self.assertNotIn("error:github", self.w.state)
        self.assertEqual(self.w.state["github_success_at"], self.clock)

    def test_removed_deadline_and_recovered_error_do_not_return_after_restart(self):
        with self.db:
            self.w.state["memento:reviewer"] = {"pointer": "old", "at": 1000}
            self.w.state["error:github"] = "old-error"
            self.w.save()
            self.w.state.pop("memento:reviewer")
            self.w.state.pop("error:github")
            self.w.save()
        recovered = module.Watcher(
            self.config, self.db, self.command, lambda: self.clock
        )
        self.assertNotIn("memento:reviewer", recovered.state)
        self.assertNotIn("error:github", recovered.state)

    def test_owned_branch_discovers_new_pr_then_checks_transition(self):
        self.config["pr_branches"] = [{"repo": "owner/repo", "head": "feat/owned"}]
        self.w.poll()
        self.pulls = [{"number": 1, "url": self.pr["url"]}]
        self.clock += 60
        self.w.poll()
        self.w.poll()
        self.assertEqual(len(self.status()), 1)
        self.pr["statusCheckRollup"][0].update(status="COMPLETED", conclusion="SUCCESS")
        self.clock += 60
        self.w.poll()
        self.assertEqual(len(self.status()), 2)

    def test_reservation_directory_notifies_only_new_generation(self):
        store = self.root / "reservations"
        (store / "owned").mkdir(parents=True)
        (store / "owned" / "1.json").write_text("{}")
        self.config["merge_files"] = [str(store)]
        self.w.poll()
        self.assertEqual(self.status(), [])
        (store / "owned" / "2.json").write_text("{}")
        self.w.poll()
        self.w.poll()
        self.assertEqual(len(self.status()), 1)

    def test_memory_dry_run_clone_does_not_change_baseline(self):
        self.w.poll()
        self.event()
        self.db.commit()
        before = self.db.execute("SELECT * FROM state").fetchall()
        clone = sqlite3.connect(":memory:")
        self.addCleanup(clone.close)
        self.db.backup(clone)
        dry = module.Watcher(self.config, clone, self.command, lambda: self.clock)
        dry.state["activation"] = 123
        dry.poll()
        self.assertEqual(self.db.execute("SELECT * FROM state").fetchall(), before)
        self.assertFalse(any(c[:2] == ["codex", "queue"] for c in self.calls))

    def enable_watchdog(self, phase="idle"):
        self.root_transcript = self.root / "root.jsonl"
        self.root_transcript.write_text("")
        self.native_queue = self.root / "queue.sqlite"
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            db.execute(
                "CREATE TABLE queued_items(id TEXT PRIMARY KEY,thread_id TEXT,payload_json TEXT)"
            )
        control = json.loads(self.control.read_text())
        control["sessions"].append(
            {
                "role": "buford",
                "kind": "codex",
                "session_id": "root-a",
                "transcript": str(self.root_transcript),
            }
        )
        self.control.write_text(json.dumps(control))
        self.config.update(
            roles="registered",
            native_queue_database=str(self.native_queue),
            workflow_assessment={"enabled": True, "paused": False, "idle_seconds": 45},
        )
        if phase != "unknown":
            self.root_event(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "task_complete" if phase == "idle" else "task_started"
                    },
                }
            )

    def root_event(self, record):
        with self.root_transcript.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def root_complete(self):
        self.root_event({"type": "event_msg", "payload": {"type": "task_complete"}})

    def wakes(self):
        return self.db.execute(
            "SELECT id,status,source FROM events WHERE source LIKE 'workflow-assessment:%' ORDER BY created,id"
        ).fetchall()

    def wake_calls(self):
        return [
            c
            for c in self.calls
            if c[:2] == ["codex", "queue"] and "<workflow-wake:" in c[-1]
        ]

    def consume_wake(self):
        self.root_event(
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "item": {
                        "type": "UserMessage",
                        "content": [
                            {"type": "text", "text": self.wake_calls()[-1][-1]}
                        ],
                    },
                },
            }
        )

    def test_idle45_wakes_without_new_events_and_has_one_outstanding(self):
        self.enable_watchdog()
        self.w.poll()
        self.w.dispatch()
        self.clock += 44
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.clock += 1
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.assertIn("preserve holds", self.wake_calls()[0][-1])
        self.clock += 450
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.assertEqual(len(self.wakes()), 1)

    def test_actual_input_then_completed_idle_interval_allows_next_wake(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.consume_wake()
        self.w.poll()
        self.clock += 100
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(
            len(self.wake_calls()), 1
        )  # consumed, but actual turn remains busy
        self.root_complete()
        self.w.poll()
        self.clock += 44
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.clock += 1
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 2)

    def test_busy_custom_tool_calls_and_final_without_taskcomplete_suppress(self):
        self.enable_watchdog("busy")
        self.w.poll()
        self.clock += 100
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "x",
                    "name": "exec",
                    "input": "text(1)",
                },
            }
        )
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "GREEN"}],
                },
            }
        )
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wakes(), [])
        self.root_complete()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM events WHERE source='buford'"
            ).fetchone()[0],
            0,
        )

    def test_unknown_native_state_never_becomes_idle_by_elapsed_time(self):
        self.enable_watchdog("unknown")
        self.w.poll()
        self.clock += 1000
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wakes(), [])

    def test_real_claude_lifecycle_and_cached_records_are_distinct(self):
        activity = module.native_activity
        self.assertEqual(
            activity(
                {
                    "type": "assistant",
                    "message": {"stop_reason": "tool_use", "content": []},
                }
            ),
            ("busy", None),
        )
        self.assertEqual(
            activity(
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": "tool_result", "content": "GREEN"}]
                    },
                }
            ),
            ("busy", None),
        )
        self.assertEqual(
            activity(
                {
                    "type": "assistant",
                    "message": {
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "done"}],
                    },
                }
            ),
            ("idle", None),
        )
        self.assertEqual(
            activity(
                {"type": "api-request-blob", "message": {"stop_reason": "end_turn"}}
            ),
            (None, None),
        )

    def test_wake_token_in_tool_output_or_unrelated_input_is_not_consumption(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        text = self.wake_calls()[0][-1]
        self.root_event(
            {
                "type": "response_item",
                "payload": {"type": "custom_tool_call_output", "output": text},
            }
        )
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "another input"}],
                },
            }
        )
        self.root_complete()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)

    def test_native_pending_queue_suppresses_wake_and_remains_untouched(self):
        self.enable_watchdog()
        self.w.poll()
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            db.execute(
                "INSERT INTO queued_items VALUES(?,?,?)",
                (
                    "pending",
                    "root-a",
                    json.dumps(
                        {
                            "UserInput": {
                                "content": [
                                    {"type": "text", "text": "existing pointer"}
                                ],
                                "client_id": "x",
                            }
                        }
                    ),
                ),
            )
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wakes(), [])
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM queued_items").fetchone()[0], 1
            )
            db.execute(
                "DELETE FROM queued_items"
            )  # simulate actual native consumption, never watcher deletion
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)

    def test_queue_storage_missing_or_unknown_shape_fails_closed_loudly(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            db.execute("INSERT INTO queued_items VALUES('bad','root-a','{}')")
        self.w.poll()
        self.assertEqual(self.wakes(), [])
        self.assertIn("error:workflow-assessment", self.w.state)
        self.native_queue.unlink()
        self.w.poll()
        self.assertEqual(self.wakes(), [])
        self.assertFalse(self.native_queue.exists())

    def test_wake_send_rechecks_busy_and_queue_at_dispatch_boundary(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.root_event({"type": "event_msg", "payload": {"type": "task_started"}})
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.root_complete()
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.clock += 45
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            db.execute(
                "INSERT INTO queued_items VALUES('q','root-a',?)",
                (json.dumps({"UserInput": {"content": []}}),),
            )
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        with closing(sqlite3.connect(self.native_queue)) as db, db:
            db.execute("DELETE FROM queued_items")
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)

    def test_restart_and_uncertain_wake_do_not_resend(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.queue_result = subprocess.TimeoutExpired("codex", 12)
        self.w.dispatch()
        self.w = module.Watcher(self.config, self.db, self.command, lambda: self.clock)
        self.clock += 450
        self.queue_result = None
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.assertEqual(self.wakes()[0][1], "uncertain")

    def test_restart_consumption_and_second_completed_interval(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.w = module.Watcher(self.config, self.db, self.command, lambda: self.clock)
        self.consume_wake()
        self.root_complete()
        self.w.poll()
        self.w = module.Watcher(self.config, self.db, self.command, lambda: self.clock)
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 2)

    def replace_root(self, target="root-new"):
        path = self.root / (target + ".jsonl")
        path.write_text(
            json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}})
            + "\n"
        )
        control = json.loads(self.control.read_text())
        control["notification_thread"] = target
        for session in control["sessions"]:
            if session["role"] == "buford":
                session.update(session_id=target, transcript=str(path))
        self.control.write_text(json.dumps(control))
        self.root_transcript = path

    def test_memento_route_change_retires_unsent_wake_without_replay(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.replace_root()
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.assertEqual(self.wake_calls()[0][3], "root-new")
        self.assertIn("superseded", [r[1] for r in self.wakes()])

    def test_scheduled_root_memento_holds_timer_until_successor_route(self):
        self.enable_watchdog()
        self.w.poll()
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "memento",
                    "arguments": json.dumps(
                        {"cmd": "/plugin/finalize-session -- 'same claim'"}
                    ),
                },
            }
        )
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "memento",
                    "output": "handoff scheduled → foot codex",
                },
            }
        )
        self.root_complete()
        self.w.poll()
        self.clock += 120
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wakes(), [])
        self.replace_root()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)

    def test_paused_config_cancels_unsent_wake(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.config["workflow_assessment"]["paused"] = True
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.assertIn("disabled", [r[1] for r in self.wakes()])

    def test_disabled_config_cancels_unsent_wake(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.config["workflow_assessment"]["enabled"] = False
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.assertIn("disabled", [r[1] for r in self.wakes()])

    def test_root_unreadable_after_idle_state_cannot_create_wake(self):
        self.enable_watchdog()
        self.w.poll()
        self.root_transcript.unlink()
        self.clock += 45
        self.w.poll()
        self.assertEqual(self.wakes(), [])

    def test_new_role_and_ticket_coverage_baselines_history_then_follows_live_claims(
        self,
    ):
        self.config["roles"] = "registered"
        control = json.loads(self.control.read_text())
        control["sessions"].append(
            {
                "role": "profile-coder",
                "kind": "claude",
                "session_id": "author-live",
                "transcript": str(self.transcript),
            }
        )
        self.control.write_text(json.dumps(control))
        self.config["tickets"] = [
            "arhugula-memory-lifecycle-oxw",
            "arhugula-cli-usage-pq2",
        ]
        self.comments = [
            {
                "id": "historic",
                "issue_id": "arhugula-memory-lifecycle-oxw",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "GREEN FROM oldauthor",
            }
        ]
        self.append(
            {
                "type": "assistant",
                "message": {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "GREEN old"}],
                },
            }
        )
        self.w.poll()
        self.assertEqual(self.status(), [])
        self.comments += [
            {
                "id": "live",
                "issue_id": "arhugula-memory-lifecycle-oxw",
                "created_at": "1970-01-01T00:16:42Z",
                "body": "FROM profile-coder author-live CLAIM (bounded). branch fix/live frozen",
            },
            {
                "id": "unrelated",
                "issue_id": "arhugula-cli-usage-pq2",
                "created_at": "1970-01-01T00:16:42Z",
                "body": "FROM retired-author CLAIM (old). branch fix/stale frozen",
            },
        ]
        self.w.poll()
        self.assertEqual(
            self.w.state["claimed_branches"],
            [{"repo": "thestoryportal/arhugula-harness", "head": "fix/live"}],
        )
        self.assertEqual(len(self.status()), 2)

    def test_slow_observers_cannot_starve_due45_wake_past60(self):
        self.enable_watchdog()
        self.config["prs"] = [{"repo": "owner/repo", "number": 1}]
        original = self.w.command
        sends = []

        def slow(argv, cwd, timeout=12):
            if argv[:2] == ["codex", "queue"]:
                if "<workflow-wake:" in argv[-1]:
                    sends.append(self.clock)
                return original(argv, cwd, timeout)
            cost = 12
            self.clock += min(cost, timeout)
            if timeout < cost:
                raise subprocess.TimeoutExpired(argv, timeout)
            return original(argv, cwd, timeout)

        self.w.command = slow
        self.w.cycle()
        self.clock = 1044
        self.w.cycle()
        self.assertLessEqual(self.clock, 1059)
        self.w.cycle()
        self.assertTrue(sends)
        self.assertLessEqual(sends[0], 1060)

    def test_claimed_branch_survives_canonical_role_continuation_then_writer_release(
        self,
    ):
        self.config["roles"] = "registered"
        control = json.loads(self.control.read_text())
        control["sessions"].append(
            {
                "role": "profile-coder",
                "kind": "claude",
                "session_id": "author-old",
                "transcript": str(self.transcript),
            }
        )
        self.control.write_text(json.dumps(control))
        self.comments = [
            {
                "id": "claim",
                "issue_id": "arhugula-harness-trial-193.active",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "FROM profile-coder author-old CLAIM (bounded). branch: `fix/active` frozen",
            }
        ]
        self.w.poll()
        self.assertEqual(self.w.state["claimed_branches"][0]["head"], "fix/active")
        control["sessions"][-1]["session_id"] = "author-successor"
        self.control.write_text(json.dumps(control))
        self.w.poll()
        self.assertEqual(self.w.state["claimed_branches"][0]["head"], "fix/active")
        self.comments += [
            {
                "id": "release",
                "issue_id": "arhugula-harness-trial-193.active",
                "created_at": "1970-01-01T00:16:42Z",
                "body": "FROM author-successor WRITER RELEASE; source landed.",
            }
        ]
        self.w.poll()
        self.assertEqual(self.w.state["claimed_branches"], [])

    def test_deadline_expiring_during_send_boundary_is_known_unsent_not_uncertain(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        original = self.w.assessment_ready

        def budget_spent(control):
            ready = original(control)
            self.clock += 15
            return ready

        self.w.assessment_ready = budget_spent
        self.w.deadline = self.clock + 15
        self.w.dispatch()
        self.assertEqual(self.wake_calls(), [])
        self.assertEqual(self.wakes()[0][1], "pending")
        self.assertEqual(
            self.db.execute("SELECT status FROM outbox").fetchone()[0], "pending"
        )
        self.w.deadline = None
        self.w.assessment_ready = original
        self.clock += 60
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)

    def test_injected_codex_context_cannot_acknowledge_wake_but_typed_input_can(self):
        self.enable_watchdog()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        text = self.wake_calls()[0][-1]
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "internal_chat_message_metadata_passthrough": {
                        "content_item_kinds": ["context"]
                    },
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        self.root_complete()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 1)
        self.root_event(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "internal_chat_message_metadata_passthrough": {
                        "content_item_kinds": ["user.text"]
                    },
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        self.root_complete()
        self.w.poll()
        self.clock += 45
        self.w.poll()
        self.w.dispatch()
        self.assertEqual(len(self.wake_calls()), 2)

    def test_to_from_coordination_does_not_feed_root_its_own_status(self):
        self.comments = [
            {
                "id": "root-to-from",
                "issue_id": "arhugula-harness-trial-193",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "TO profile-coder | FROM Buford01a1abb3, integration lead | frozen result",
            },
            {
                "id": "root",
                "issue_id": "arhugula-harness-trial-193",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "TO profile-coder | FROM Buford integration lead | frozen result",
            },
            {
                "id": "peer-to-from",
                "issue_id": "arhugula-harness-trial-193",
                "created_at": "1970-01-01T00:16:41Z",
                "body": "TO Buford | FROM independent reviewer | GREEN",
            },
        ]
        self.w.poll()
        pointers = [r[0] for r in self.db.execute("SELECT pointer FROM events")]
        self.assertNotIn("arhugula-harness-trial-193 root", pointers)
        self.assertNotIn("arhugula-harness-trial-193 root-to-from", pointers)
        self.assertIn("arhugula-harness-trial-193 peer-to-from", pointers)


if __name__ == "__main__":
    unittest.main()
