import json
from pathlib import Path
import unittest
import sqlite3
from datetime import datetime, timezone
import test_loop


class WindowSeam:
    def __init__(self, root):
        self.root = root
        self.name = "old"
        self.lines = []
        self.queued = []
        self.created = None
        self.pending = None
        self.rollouts = []
        self.next_id = "new"

    def check(self):
        return {"title": self.name}

    def title(self):
        return self.name

    def clear(self, title):
        self.pending = "/clear " + title
        self.lines.append(self.pending)
        if self.pending.startswith("/clear "):
            self.name = self.pending[7:]
            self.created = datetime.now(timezone.utc).isoformat()
            path = self.root / (self.next_id + ".jsonl")
            path.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": self.next_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
                + "\n"
            )
            self.rollouts = [path]

    def transcripts(self):
        return self.rollouts

    def context(self, frontier, previous):
        from ops.orchestration.loop import identity

        if self.rollouts:
            actual = identity(self.rollouts[0])
            return {
                "session_id": actual["session_id"],
                "user_input": bool(actual["user_count"]),
                "transcript": str(self.rollouts[0]),
                "created_at": self.created,
                "process_uuid": "pid:123:fixture",
                "creation_log_id": 1,
            }
        return {
            "session_id": self.next_id,
            "user_input": False,
            "transcript": None,
            "created_at": self.created,
            "process_uuid": "pid:123:fixture",
            "creation_log_id": 1,
        }

    def queue(self, context, frontier, previous, text):
        self.queued.append((context["session_id"], text))
        return {"message_id": "message-id", "session_id": context["session_id"]}

    def delivered_context(self, frontier, previous, initial):
        from ops.orchestration.native_window import NativeWindow

        return NativeWindow.delivered_context(self, frontier, previous, initial)

    def recovery_context(self, frontier, previous, grant):
        return self.context(frontier, previous)


class AutoResetTests(unittest.TestCase):
    def setUp(self):
        fixture = test_loop.LoopTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f = fixture
        self.root = fixture.root
        self.loop = fixture.loop
        from ops.orchestration.artifacts import file_binding

        authority = self.root / "authority"
        authority.write_text("user requires automatic clear and continuation")
        instructions = self.root / "continuation"
        instructions.write_text(
            "Continue acceptance then authorized production without HIL."
        )
        goal = self.root / "goal.json"
        goal.write_text(
            json.dumps(
                {
                    "goal": {
                        "threadId": "old",
                        "objective": "full scope",
                        "tokensUsed": 100,
                        "timeUsedSeconds": 10,
                        "status": "paused",
                    },
                    "remainingTokens": None,
                }
            )
        )
        self.release = self.root / "release.json"
        self.release.write_text(
            json.dumps(
                {
                    "session_id": "old",
                    "epoch": 0,
                    "owned_processes": [],
                    "goal_receipt": str(goal),
                    "completed": [],
                    "user_frontier": {"count": 0, "hash": None},
                }
            )
        )
        self.database = self.root / "goals.sqlite"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY,goal_id TEXT,objective TEXT,status TEXT,token_budget INTEGER,tokens_used INTEGER,time_used_seconds INTEGER,created_at_ms INTEGER,updated_at_ms INTEGER)"
            )
            connection.execute(
                "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
                ("old", "goal", "full scope", "active", None, 100, 10, 1000, 1000),
            )
        self.config = {
            "authority": file_binding(authority),
            "continuation": file_binding(instructions),
            "release": str(self.release),
            "packages": str(self.root / "packages"),
            "goal_ledger": str(self.root / "lineage.json"),
            "deadline": "original",
            "goal_database": str(self.database),
            "receipt_directory": str(self.root / "receipts"),
            "sessions": str(self.root),
            "source_acceptance": [file_binding(authority)],
            "control": str(fixture.control),
            "state": str(self.loop.path),
            "supervisor": str(self.root / "supervisor.json"),
            "cwd": str(self.root),
            "artifact_root": str(self.root / "artifacts"),
            "runtime_unit": "test-only",
            "version": 1,
        }
        self.window = WindowSeam(self.root)
        self.clock = 100
        from ops.orchestration import auto_reset, loop, native_window

        self.config["source_acceptance"].extend(
            file_binding(module.__file__)
            for module in (auto_reset, loop, native_window)
        )

    def controller(self):
        from ops.orchestration.auto_reset import AutoReset

        return AutoReset(
            self.loop,
            self.root / "supervisor.json",
            self.config,
            self.window,
            lambda: self.clock,
        )

    def hold(self):
        self.loop.prepare_clear(self.root / "old-package", [])

    def recovery_fixture(self, *, routing_refresh=False):
        from ops.orchestration.artifacts import file_binding
        from ops.orchestration.auto_reset import user_frontier
        from ops.orchestration.loop import identity

        control = json.loads(self.f.control.read_text())
        control["repair_paused"] = True
        if routing_refresh:
            control["sessions"].append(
                {
                    "role": "implementer",
                    "session_id": "impl-old",
                    "transcript": "old-impl",
                }
            )
        self.f.control.write_text(json.dumps(control))
        self.config["window"] = {"native_pid": 123}
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.clock += 121
        fresh = self.fresh()
        rows = fresh.read_text().splitlines()
        user = json.loads(rows[-1])
        user["payload"]["content"][0]["text"] = "human report of failed blank session"
        fresh.write_text("\n".join(rows[:-1] + [json.dumps(user)]) + "\n")
        self.window.rollouts = [fresh]
        grant = {
            "maintenance_only": True,
            "window": self.config["window"],
            "deadline": self.config["deadline"],
            "session_id": "new",
            "transcript": str(fresh),
            "user_frontier": user_frontier(identity(fresh)),
        }
        for key, path in (
            ("supervisor", controller.path),
            ("journal", self.loop.path),
            ("routing", self.loop.control),
        ):
            snapshot = self.root / ("failed-" + key + ".json")
            snapshot.write_bytes(path.read_bytes())
            grant[key] = file_binding(snapshot)
        from ops.orchestration.native_goal import read_goal

        for key, data in (
            (
                "human_authority",
                {
                    "session_id": "new",
                    "user_frontier": grant["user_frontier"],
                    "actual_user_message": identity(fresh)["first_user"],
                },
            ),
            ("terminal_goal", read_goal(self.database, "old")),
            (
                "current_goal",
                {
                    "session_id": "new",
                    "tool_result": {
                        "goal": None,
                        "remainingTokens": None,
                        "completionBudgetReport": None,
                    },
                },
            ),
        ):
            snapshot = self.root / (key + ".json")
            snapshot.write_text(json.dumps(data))
            grant[key] = file_binding(snapshot)
        if routing_refresh:
            current = json.loads(self.f.control.read_text())
            next(s for s in current["sessions"] if s["role"] == "implementer").update(
                session_id="impl-new", transcript="new-impl"
            )
            self.f.control.write_text(json.dumps(current))
            snapshot = Path(grant["routing"]["path"])
            snapshot.write_bytes(self.f.control.read_bytes())
            grant["routing"] = file_binding(snapshot)
            delivery = self.root / "delivery.json"
            delivery.write_text(
                json.dumps(
                    {"session_id": "impl-new", "model": "gpt-6.1-sol", "effort": "high"}
                )
            )
            refresh = self.root / "implementer-refresh.json"
            refresh.write_text(
                json.dumps(
                    {
                        "kind": "authorized-idle-implementer-native-refresh",
                        "production_paused": True,
                        "previous_session": "impl-old",
                        "session_id": "impl-new",
                        "control_after": file_binding(self.f.control),
                        "delivery": file_binding(delivery),
                    }
                )
            )
            grant["implementer_refresh"] = file_binding(refresh)
        authority = self.root / "recovery-authority.json"
        authority.write_text(json.dumps(grant))
        return controller, authority, fresh

    def test_complete_prompt_uses_one_queue_to_created_uuid(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        prompt = (
            Path(controller.status()["reset"]["directory"]) / "resume-prompt.txt"
        ).read_text()
        self.assertEqual(self.window.queued, [("new", prompt)])
        self.assertEqual(len(self.window.lines), 1)
        controller.step(self.fresh())
        self.assertEqual(controller.status()["phase"], "verified")
        self.assertEqual(len(self.window.queued), 1)

    def prompt_recovery_fixture(self, *, legacy=False, routing_refresh=False):
        from ops.orchestration.artifacts import file_binding
        from ops.orchestration.auto_reset import user_frontier
        from ops.orchestration.loop import identity

        controller, predecessor, outgoing = self.recovery_fixture(
            routing_refresh=routing_refresh
        )
        controller.recover_maintenance(predecessor)
        prior_proof = self.loop.status()["maintenance_recovery"]
        with outgoing.open("a") as stream:
            stream.write(
                json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}})
                + "\n"
            )
        prior = json.loads(predecessor.read_text())
        self.release.write_text(
            json.dumps(
                {
                    "session_id": "new",
                    "epoch": 0,
                    "owned_processes": [],
                    "goal_receipt": prior["current_goal"]["path"],
                    "completed": [],
                    "user_frontier": user_frontier(identity(outgoing)),
                }
            )
        )
        controller.save({"phase": "monitoring"})
        self.window.next_id = "third"
        for _ in range(3):
            controller.step()
        failed = controller.status()
        if legacy:
            failed.pop("queue_ack")
            failed.pop("prompt")
            controller.save(failed)
        package = Path(failed["reset"]["directory"])
        (self.root / "package/resume-prompt.txt").write_text(
            (package / "resume-prompt.txt").read_text()
        )
        fresh = self.f.fresh_transcript("third")
        rows = fresh.read_text().splitlines()
        meta = json.loads(rows[0])
        meta["payload"]["timestamp"] = self.window.created
        rows[0] = json.dumps(meta)
        if legacy:
            user = json.loads(rows[-1])
            user["payload"]["content"][0]["text"] = user["payload"]["content"][0][
                "text"
            ].removesuffix("\n")
            rows[-1] = json.dumps(user)
        fresh.write_text("\n".join(rows) + "\n")
        self.window.rollouts = [fresh]
        self.clock += 121
        grant = {
            "kind": "expired-waiting-fresh-sealed-prompt",
            "maintenance_only": True,
            "window": self.config["window"],
            "deadline": self.config["deadline"],
            "session_id": "third",
            "transcript": str(fresh),
            "user_frontier": user_frontier(identity(fresh)),
            "human_authority": prior["human_authority"],
            "predecessor": prior_proof,
            "attempt": {
                "manifest": failed["reset"]["manifest"],
                "frontier": file_binding(package / "frontier.json"),
                "nonce": failed["nonce"],
                "started": failed["started"],
                "fresh_context": failed["fresh_context"],
            },
            "prompt": {
                "file": file_binding(package / "resume-prompt.txt"),
                "bytes": len(identity(fresh)["first_user"].encode()),
                "sha256": identity(fresh)["last_user_hash"],
                "count": 1,
            },
        }
        from ops.orchestration.native_goal import read_goal

        data = {
            "supervisor": failed,
            "journal": self.loop._read(),
            "routing": self.loop._control(),
            "config": self.config,
            "goal_ledger": json.loads(Path(self.config["goal_ledger"]).read_text()),
            "terminal_goal": read_goal(self.database, "new"),
            "current_goal": read_goal(self.database, "third"),
        }
        for key, value in data.items():
            path = self.root / ("second-" + key + ".json")
            path.write_bytes(
                self.loop.path.read_bytes()
            ) if key == "journal" else path.write_text(json.dumps(value))
            grant[key] = file_binding(path)
        authority = self.root / "second-recovery-authority.json"
        execution = self.root / "second-execution-config.json"
        execution.write_text(json.dumps(self.config))
        self.config["config_path"] = str(execution)
        grant["execution_config"] = file_binding(execution)
        authority.write_text(json.dumps(grant))
        return controller, authority, fresh, predecessor

    def test_queued_prompt_cannot_bootstrap_after_nonce_title_changes(self):
        self.hold()
        controller = self.controller()
        for _ in range(3):
            controller.step()
        fresh = self.fresh()
        self.window.name += " extra"
        with self.assertRaisesRegex(ValueError, "nonce title"):
            controller.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 0)
        self.assertEqual(len(self.window.queued), 1)

    def test_receipt_crash_does_not_thaw_protected_routing(self):
        from unittest.mock import patch

        self.hold()
        controller = self.controller()
        for _ in range(3):
            controller.step()
        fresh = self.fresh()
        with patch.object(
            controller, "publish", side_effect=OSError("before publication")
        ):
            with self.assertRaises(OSError):
                controller.step(fresh)
        control = self.loop._control()
        control["sessions"][1]["session_id"] = "changed-protected"
        self.f.control.write_text(json.dumps(control))
        with self.assertRaisesRegex(ValueError, "routing/pause"):
            controller.step(fresh)
        self.assertNotIn("native_receipt", self.loop.status())
        self.assertTrue(self.loop.status()["awaiting_native_receipt"])

    def test_receipt_write_crossing_deadline_keeps_acceptance_held(self):
        from unittest.mock import patch
        from ops.orchestration.records import atomic_json

        self.hold()
        controller = self.controller()
        for _ in range(3):
            controller.step()
        fresh = self.fresh()

        def late_receipt(path, data, **kwargs):
            atomic_json(path, data, **kwargs)
            if "bootstrap" in data:
                self.clock += 121

        with patch(
            "ops.orchestration.auto_reset.atomic_json", side_effect=late_receipt
        ):
            with self.assertRaisesRegex(ValueError, "deadline"):
                controller.step(fresh)
        self.assertNotIn("native_receipt", self.loop.status())
        self.assertTrue(self.loop.status()["awaiting_native_receipt"])
        self.assertEqual(controller.status()["phase"], "waiting_fresh")

    def test_prompt_recovery_accepts_only_the_bound_second_implementer_refresh(self):
        from ops.orchestration.artifacts import file_binding

        controller, authority, fresh, predecessor = self.prompt_recovery_fixture(
            routing_refresh=True
        )
        control = self.loop._control()
        impl = next(s for s in control["sessions"] if s["role"] == "implementer")
        impl.update(session_id="impl-final", transcript="final-impl")
        self.f.control.write_text(json.dumps(control))
        grant = json.loads(authority.read_text())
        snapshot = Path(grant["routing"]["path"])
        snapshot.write_bytes(self.f.control.read_bytes())
        grant["routing"] = file_binding(snapshot)
        delivery = self.root / "final-impl-delivery.json"
        delivery.write_text(
            json.dumps(
                {"session_id": "impl-final", "model": "gpt-6.1-sol", "effort": "high"}
            )
        )
        refresh = self.root / "final-impl-refresh.json"
        refresh.write_text(
            json.dumps(
                {
                    "kind": "authorized-idle-implementer-native-refresh",
                    "production_paused": True,
                    "previous_session": "impl-new",
                    "session_id": "impl-final",
                    "control_after": file_binding(self.f.control),
                    "delivery": file_binding(delivery),
                }
            )
        )
        grant["implementer_refresh"] = file_binding(refresh)
        authority.write_text(json.dumps(grant))
        controller.recover_maintenance(authority)
        actual = self.loop._control()
        self.assertEqual(actual["sessions"][1:], control["sessions"][1:])
        self.assertEqual(actual["sessions"][0]["session_id"], "third")
        self.assertTrue(actual["repair_paused"])

    def test_native_creation_change_holds_before_bootstrap_and_before_receipt(self):
        from unittest.mock import patch

        for boundary in ("bootstrap", "publication"):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.hold()
                controller = self.controller()
                for _ in range(3):
                    controller.step()
                fresh = self.fresh()
                if boundary == "publication":
                    with patch.object(
                        controller,
                        "publish",
                        side_effect=OSError("crash before receipt"),
                    ):
                        with self.assertRaises(OSError):
                            controller.step(fresh)
                original = self.window.context
                self.window.context = lambda *args: {
                    **original(*args),
                    "creation_log_id": 999,
                }
                with self.assertRaisesRegex(ValueError, "native context changed"):
                    controller.step(fresh)
                self.assertNotIn("native_receipt", self.loop.status())
                self.assertEqual(self.loop.status()["epoch"], 0)

    def test_legacy_expired_prompt_recovers_without_retrospective_acceptance(self):
        controller, authority, fresh, predecessor = self.prompt_recovery_fixture(
            legacy=True
        )
        before = self.loop.status()
        controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["epoch"], before["epoch"])
        self.assertTrue(self.loop.status()["maintenance_only"])
        self.assertTrue(self.loop.status()["reset_requested"])
        self.assertFalse(controller.status()["automatic_acceptance"])
        self.assertNotIn("native_receipt", self.loop.status())
        ledger = json.loads(Path(self.config["goal_ledger"]).read_text())
        self.assertNotIn("new", ledger["threads"])
        self.assertNotIn("third", ledger["threads"])
        self.assertEqual((ledger["tokens_used"], ledger["seconds_used"]), (100, 10))

    def test_successive_failed_attempt_has_distinct_recovery_without_credit(self):
        controller, authority, fresh, predecessor = self.prompt_recovery_fixture()
        before = self.loop.status()
        result = controller.recover_maintenance(authority)
        after = self.loop.status()
        self.assertEqual(result["phase"], "maintenance_recovered")
        self.assertFalse(result["automatic_acceptance"])
        self.assertEqual(after["session_id"], "third")
        self.assertEqual(
            after["maintenance_recovery_history"][-1], before["maintenance_recovery"]
        )
        for key in (
            "epoch",
            "epoch_start",
            "completed",
            "reviews",
            "quarantine",
            "unit_quarantine",
            "admissions",
            "iteration",
            "handoff",
        ):
            self.assertEqual(after[key], before[key])
        self.assertTrue(after["maintenance_only"])
        self.assertTrue(after["reset_requested"])
        self.assertNotIn("native_receipt", after)
        self.assertEqual(controller.recover_maintenance(authority), result)

    def test_prompt_queue_crashes_never_replay_uncertain_effect(self):
        from unittest.mock import patch

        for boundary in ("intent", "enqueue", "ack"):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.hold()
                controller = self.controller()
                controller.step()
                controller.step()
                save, queue = controller.save, self.window.queue

                def crash_save(state):
                    save(state) if state["phase"] == "prompt_intent" else None
                    if state["phase"] == (
                        "prompt_intent" if boundary == "intent" else "waiting_fresh"
                    ):
                        raise OSError("crashed publication")
                    save(state)

                def crash_queue(*args):
                    queue(*args)
                    raise OSError("uncertain enqueue")

                with (
                    patch.object(controller, "save", side_effect=crash_save),
                    patch.object(
                        self.window,
                        "queue",
                        side_effect=crash_queue if boundary == "enqueue" else queue,
                    ),
                ):
                    with self.assertRaises(OSError):
                        controller.step()
                self.assertEqual(controller.status()["phase"], "prompt_intent")
                count = len(self.window.queued)
                with self.assertRaisesRegex(ValueError, "uncertain"):
                    self.controller().step()
                self.assertEqual(len(self.window.queued), count)
                self.assertEqual(count, 0 if boundary == "intent" else 1)
                self.assertEqual(self.loop.status()["epoch"], 0)

    def test_deadline_expiring_in_queue_or_lit_read_does_not_bootstrap(self):
        for boundary in ("queue", "bootstrap-read"):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.hold()
                controller = self.controller()
                controller.step()
                controller.step()
                if boundary == "queue":
                    queue = self.window.queue

                    def delayed_queue(*args):
                        result = queue(*args)
                        self.clock += 121
                        return result

                    self.window.queue = delayed_queue
                    controller.step()
                else:
                    controller.step()
                    read = self.f.lit.read

                    def delayed_read(*args):
                        result = read(*args)
                        self.clock += 121
                        return result

                    self.f.lit.read = delayed_read
                with self.assertRaisesRegex(ValueError, "deadline"):
                    controller.step(self.fresh())
                self.assertEqual(self.loop.status()["epoch"], 0)
                self.assertEqual(
                    self.loop._control()["sessions"][0]["session_id"], "old"
                )

    def test_successor_recovery_crashes_at_each_publication_boundary(self):
        from unittest.mock import patch

        for boundary in ("intent", "routing", "journal", "supervisor"):
            with self.subTest(boundary=boundary):
                self.setUp()
                controller, authority, fresh, predecessor = (
                    self.prompt_recovery_fixture()
                )
                save, write = self.loop._save, controller.save
                previous = self.loop.status()

                def crash(state):
                    if boundary == "intent" and state.get("pending_maintenance"):
                        save(state)
                        raise OSError("intent crash")
                    if boundary == "routing" and state["session_id"] == "third":
                        raise OSError("routing crash")
                    if boundary == "journal" and state["session_id"] == "third":
                        save(state)
                        raise OSError("journal crash")
                    save(state)

                def crash_supervisor(state):
                    write(state)
                    raise OSError("supervisor crash")

                with (
                    patch.object(self.loop, "_save", side_effect=crash),
                    patch.object(
                        controller,
                        "save",
                        side_effect=crash_supervisor
                        if boundary == "supervisor"
                        else write,
                    ),
                ):
                    with self.assertRaises(OSError):
                        controller.recover_maintenance(authority)
                recovered = self.controller().recover_maintenance(authority)
                self.assertFalse(recovered["automatic_acceptance"])
                state = self.loop.status()
                self.assertEqual(state["epoch"], previous["epoch"])
                self.assertEqual(
                    state["maintenance_recovery_history"],
                    [previous["maintenance_recovery"]],
                )
                self.assertEqual(state["session_id"], "third")
                self.assertEqual(len(self.window.queued), 1)

    def test_successor_recovery_refuses_changed_bound_evidence_and_contract(self):
        import copy

        for mutation in (
            "predecessor",
            "config",
            "journal",
            "nonce",
            "started",
            "creation",
            "prompt",
            "UUID",
            "frontier",
            "title",
            "native",
            "goal",
            "old-grant",
        ):
            with self.subTest(mutation=mutation):
                self.setUp()
                controller, authority, fresh, predecessor = (
                    self.prompt_recovery_fixture()
                )
                grant = json.loads(authority.read_text())
                state = self.loop.status()
                before = self.loop._control()
                if mutation == "predecessor":
                    grant["predecessor"]["failed_reset"]["previous_session"] = "changed"
                elif mutation in ("config", "journal"):
                    path = Path(grant[mutation]["path"])
                    path.write_text(path.read_text() + " ")
                elif mutation in ("nonce", "started"):
                    grant["attempt"][mutation] = "changed"
                elif mutation == "creation":
                    grant["attempt"]["fresh_context"]["creation_log_id"] += 1
                elif mutation == "prompt":
                    grant["prompt"]["sha256"] = "changed"
                elif mutation == "UUID":
                    grant["session_id"] = "foreign"
                elif mutation == "frontier":
                    grant["user_frontier"]["count"] += 1
                elif mutation == "title":
                    self.window.name += " extra"
                elif mutation == "native":
                    actual_context = copy.deepcopy(self.window.context({}, "new"))
                    actual_context["process_uuid"] = "pid:999:foreign"
                    self.window.recovery_context = lambda *_: actual_context
                elif mutation == "goal":
                    path = Path(self.config["goal_ledger"])
                    data = json.loads(path.read_text())
                    data["tokens_used"] += 1
                    path.write_text(json.dumps(data))
                else:
                    predecessor.write_text(predecessor.read_text() + " ")
                authority.write_text(json.dumps(grant))
                with self.assertRaises(ValueError):
                    controller.recover_maintenance(authority)
                self.assertEqual(self.loop.status(), state)
                self.assertEqual(self.loop._control(), before)

    def test_successor_recovery_cannot_relabel_exact_prompt_as_title_recovery(self):
        controller, authority, fresh, predecessor = self.prompt_recovery_fixture()
        grant = json.loads(authority.read_text())
        grant.pop("kind")
        authority.write_text(json.dumps(grant))
        with self.assertRaises(ValueError):
            controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["session_id"], "new")

    def test_successor_recovery_requires_sole_exact_first_prompt(self):
        for mutation in ("changed", "extra", "newline"):
            with self.subTest(mutation=mutation):
                self.setUp()
                controller, authority, fresh, predecessor = (
                    self.prompt_recovery_fixture()
                )
                rows = fresh.read_text().splitlines()
                row = json.loads(rows[-1])
                if mutation == "extra":
                    rows.append(json.dumps(row))
                else:
                    row["payload"]["content"][0]["text"] += (
                        "changed" if mutation == "changed" else "\n"
                    )
                    rows[-1] = json.dumps(row)
                fresh.write_text("\n".join(rows) + "\n")
                # Even binding the current frontier must not bless wrong/extra text.
                from ops.orchestration.loop import identity
                from ops.orchestration.auto_reset import user_frontier

                grant = json.loads(authority.read_text())
                grant["user_frontier"] = user_frontier(identity(fresh))
                authority.write_text(json.dumps(grant))
                with self.assertRaises(ValueError):
                    controller.recover_maintenance(authority)
                self.assertEqual(self.loop.status()["session_id"], "new")

    def test_pruned_context_recovery_passes_only_explicit_grant_to_native_boundary(
        self,
    ):
        controller, authority, fresh = self.recovery_fixture()
        proof = self.window.context({}, "old")
        self.window.context = lambda *args: None
        before = self.loop.status()
        lines = list(self.window.lines)
        observed = []

        def recovery(frontier, previous, retained):
            observed.append(retained)
            return proof if retained == {"explicit": "bound witness"} else None

        self.window.recovery_context = recovery
        with self.assertRaisesRegex(ValueError, "human frontier"):
            controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status(), before)
        grant = json.loads(authority.read_text())
        grant["retained_context"] = {"explicit": "bound witness"}
        authority.write_text(json.dumps(grant))
        recovered = controller.recover_maintenance(authority)
        self.assertEqual(observed, [None, grant["retained_context"]])
        self.assertEqual(recovered["phase"], "maintenance_recovered")
        self.assertFalse(recovered["automatic_acceptance"])
        self.assertEqual(self.window.lines, lines)
        self.assertEqual(self.loop.status()["epoch"], before["epoch"])
        self.assertTrue(self.loop.status()["production_paused"])

    def test_recovery_preserves_failed_evidence_counters_pause_and_deadline(self):
        controller, authority, fresh = self.recovery_fixture()
        before = self.loop.status()
        failed = controller.path.read_bytes()
        routing = json.loads(self.f.control.read_text())
        grant = json.loads(authority.read_text())
        result = controller.recover_maintenance(authority)
        after = self.loop.status()
        current = json.loads(self.f.control.read_text())
        for key in (
            "epoch",
            "epoch_start",
            "completed",
            "reviews",
            "quarantine",
            "unit_quarantine",
            "iteration",
            "admissions",
            "handoff",
        ):
            self.assertEqual(after[key], before[key])
        self.assertEqual(current["sessions"][1:], routing["sessions"][1:])
        self.assertEqual(current["sessions"][0]["session_id"], "new")
        self.assertEqual(Path(grant["supervisor"]["path"]).read_bytes(), failed)
        self.assertEqual(result["reset"], before["reset"])
        self.assertFalse(result["automatic_acceptance"])
        self.assertNotIn("native_receipt", after)
        self.assertTrue(after["production_paused"])
        self.assertTrue(after["reset_requested"])
        with self.assertRaisesRegex(ValueError, "genuine native reset"):
            self.loop.begin("u1")
        self.assertEqual(controller.recover_maintenance(authority), result)
        self.loop.begin("u1", maintenance=True)
        state = self.loop.status()
        controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status(), state)
        with self.assertRaisesRegex(ValueError, "context-reset-required"):
            self.loop.begin("u2", maintenance=True, headroom=False)
        self.assertEqual(len(self.window.lines), 1)

    def test_recovery_crashes_after_routing_and_after_journal_are_retry_safe(self):
        from unittest.mock import patch

        for boundary in ("routing", "supervisor"):
            with self.subTest(boundary=boundary):
                # Each crash is exercised from the same durable failed intent.
                if boundary == "routing":
                    controller, authority, fresh = self.recovery_fixture()
                    save = self.loop._save

                    def crash(state):
                        if state["session_id"] == "new":
                            raise OSError("routing crash")
                        save(state)

                    with patch.object(self.loop, "_save", side_effect=crash):
                        with self.assertRaises(OSError):
                            controller.recover_maintenance(authority)
                    with patch.object(
                        controller, "save", side_effect=OSError("supervisor crash")
                    ):
                        with self.assertRaises(OSError):
                            controller.recover_maintenance(authority)
                else:
                    controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["epoch"], 0)
        self.assertEqual(controller.status()["phase"], "maintenance_recovered")
        self.assertEqual(len(self.window.lines), 1)

    def test_recovery_refuses_unbound_frontier_deadline_pause_and_window(self):
        controller, authority, fresh = self.recovery_fixture()
        grant = json.loads(authority.read_text())
        import copy

        for key, value in (
            ("user_frontier", {"count": 999, "hash": "wrong"}),
            ("deadline", "extended"),
            ("window", {"native_pid": 999}),
            ("maintenance_only", False),
            ("session_id", "foreign"),
        ):
            with self.subTest(key=key):
                broken = copy.deepcopy(grant)
                broken[key] = value
                authority.write_text(json.dumps(broken))
                with self.assertRaises(ValueError):
                    controller.recover_maintenance(authority)
                self.assertEqual(self.loop.status()["session_id"], "old")
        authority.write_text(json.dumps(grant))
        control = json.loads(self.f.control.read_text())
        control["repair_paused"] = False
        self.f.control.write_text(json.dumps(control))
        with self.assertRaises(ValueError):
            controller.recover_maintenance(authority)

    def test_maintenance_recovery_cli_requires_and_uses_explicit_authority(self):
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        from unittest.mock import patch
        from ops.orchestration.auto_reset import main

        controller, authority, fresh = self.recovery_fixture()
        args = ["auto_reset", "recover-maintenance", "--config", "fixture"]
        with patch("sys.argv", args), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main()
        output = StringIO()
        with (
            patch("sys.argv", args + ["--recovery-authority", str(authority)]),
            patch("ops.orchestration.auto_reset.configured", return_value=controller),
            redirect_stdout(output),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(
            json.loads(output.getvalue())["phase"], "maintenance_recovered"
        )
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_manual_recovery_requires_later_full_native_reset_for_credit(self):
        controller, authority, fresh = self.recovery_fixture()
        controller.recover_maintenance(authority)
        with self.assertRaisesRegex(ValueError, "maintenance recovery only"):
            controller.step()
        self.assertTrue(self.loop.status()["maintenance_only"])
        # Release the recovered human turn, then exercise a later complete reset.
        with fresh.open("a") as stream:
            stream.write(
                json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}})
                + "\n"
            )
        goal = Path(json.loads(authority.read_text())["current_goal"]["path"])
        from ops.orchestration.auto_reset import user_frontier
        from ops.orchestration.loop import identity

        self.release.write_text(
            json.dumps(
                {
                    "session_id": "new",
                    "epoch": 0,
                    "owned_processes": [],
                    "goal_receipt": str(goal),
                    "completed": [],
                    "user_frontier": user_frontier(identity(fresh)),
                }
            )
        )
        controller.save(
            {
                "phase": "monitoring",
                "recovery_authority": controller.status()["recovery_authority"],
            }
        )
        self.window.next_id = "third"
        controller.step()
        controller.step()
        self.window.rollouts[0].write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "third",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            )
            + "\n"
        )
        controller.step()
        controller.step()
        # The helper's package pointer must follow the new sealed prompt.
        package = Path(self.loop.status()["reset"]["directory"])
        (self.root / "package/resume-prompt.txt").write_text(
            (package / "resume-prompt.txt").read_text()
        )
        later = self.f.fresh_transcript("third")
        self.window.rollouts = [later]
        controller.step(later)
        self.assertEqual(controller.status()["phase"], "verified")
        self.assertEqual(self.loop.status()["epoch"], 1)
        self.assertFalse(self.loop.status()["maintenance_only"])
        self.assertTrue(self.loop.status()["production_paused"])
        ledger = json.loads(Path(self.config["goal_ledger"]).read_text())
        self.assertEqual((ledger["tokens_used"], ledger["seconds_used"]), (100, 10))
        self.assertNotIn("new", ledger["threads"])

    def test_recovered_maintenance_cannot_evade_inherited_fifth_completion(self):
        for n in range(1, 6):
            self.loop.begin(f"u{n}")
            self.f.close(f"u{n}")
        release = json.loads(self.release.read_text())
        release["completed"] = sorted(self.loop.status()["completed"])
        self.release.write_text(json.dumps(release))
        controller, authority, fresh = self.recovery_fixture()
        controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["epoch_completed"], 5)
        with self.assertRaisesRegex(ValueError, "context-reset-required"):
            self.loop.begin("u6", maintenance=True)

    def test_recovery_refuses_stale_absence_when_a_native_goal_now_exists(self):
        controller, authority, fresh = self.recovery_fixture()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
                ("new", "goal2", "full scope", "paused", None, 50, 5, 2000, 2000),
            )
        with self.assertRaisesRegex(ValueError, "native recovery goal changed"):
            controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["session_id"], "old")

    def test_recovery_rejects_other_protected_routing_changes_even_when_snapshotted(
        self,
    ):
        controller, authority, fresh = self.recovery_fixture()
        from ops.orchestration.artifacts import file_binding

        grant = json.loads(authority.read_text())
        routing = Path(grant["routing"]["path"])
        data = json.loads(routing.read_text())
        data["sessions"][1]["session_id"] = "foreign"
        routing.write_text(json.dumps(data))
        self.f.control.write_text(routing.read_text())
        grant["routing"] = file_binding(routing)
        authority.write_text(json.dumps(grant))
        with self.assertRaisesRegex(ValueError, "implementer-only"):
            controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["session_id"], "old")

    def test_recovery_accepts_only_the_bound_implementer_refresh_delta(self):
        controller, authority, fresh = self.recovery_fixture(routing_refresh=True)
        controller.recover_maintenance(authority)
        current = json.loads(self.f.control.read_text())
        self.assertEqual(
            next(s for s in current["sessions"] if s["role"] == "implementer")[
                "session_id"
            ],
            "impl-new",
        )
        self.assertEqual(
            next(s for s in current["sessions"] if s["role"] == "runtime")[
                "session_id"
            ],
            "protected",
        )

    def fresh(self):
        state = self.loop.status()
        package = Path(state["reset"]["directory"])
        self.f.root.joinpath("package").mkdir(exist_ok=True)
        self.f.root.joinpath("package/resume-prompt.txt").write_text(
            (package / "resume-prompt.txt").read_text()
        )
        path = self.f.fresh_transcript()
        rows = path.read_text().splitlines()
        meta = json.loads(rows[0])
        meta["payload"]["timestamp"] = self.window.created
        rows[0] = json.dumps(meta)
        path.write_text("\n".join(rows) + "\n")
        self.window.rollouts = [path]
        return path

    def test_fifth_close_automatically_prepares_clears_and_submits_full_prompt(self):
        for n in range(1, 6):
            self.loop.begin(f"u{n}")
            self.f.close(f"u{n}")
        release = json.loads(self.release.read_text())
        release["completed"] = sorted(self.loop.status()["completed"])
        self.release.write_text(json.dumps(release))
        controller = self.controller()
        for _ in range(4):
            controller.step()
        self.assertEqual(len(self.window.lines), 1)
        self.assertEqual(len(self.window.queued), 1)
        self.assertTrue(self.window.lines[0].startswith("/clear Buford-auto-"))
        self.assertIn("BUFORD_CONTEXT_HANDOFF", self.window.queued[0][1])
        self.assertIn("without HIL", self.window.queued[0][1])
        controller.step(self.fresh())
        self.assertEqual(self.loop.status()["epoch"], 1)
        self.assertEqual(len(self.loop.status()["completed"]), 5)
        self.assertEqual(controller.status()["phase"], "verified")

    def test_active_parent_is_held_without_window_input(self):
        self.hold()
        with self.f.old_transcript.open("a") as stream:
            stream.write(
                json.dumps({"type": "event_msg", "payload": {"type": "task_started"}})
                + "\n"
            )
        controller = self.controller()
        controller.step()
        self.assertEqual(self.window.lines, [])
        self.assertEqual(controller.status()["phase"], "waiting_idle")

    def test_clear_with_no_rollout_submits_once_then_verifies_actual_context(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.window.rollouts[0].unlink()
        self.window.rollouts = []
        controller.step()
        self.assertEqual(len(self.window.lines), 1)
        self.assertEqual(len(self.window.queued), 1)
        controller.step(self.fresh())
        self.assertEqual(controller.status()["phase"], "verified")
        self.assertEqual(self.loop.status()["epoch"], 1)

    def test_empty_owned_rollout_does_not_delay_first_prompt(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.window.rollouts[0].write_text("")
        context = self.window.context
        self.window.context = lambda *_: {
            "session_id": "new",
            "user_input": False,
            "transcript": str(self.window.rollouts[0]),
            "created_at": self.window.created,
            "process_uuid": "pid:123:fixture",
            "creation_log_id": 1,
        }
        controller.step()
        self.window.context = context
        self.assertEqual(len(self.window.lines), 1)
        self.assertEqual(len(self.window.queued), 1)
        controller.step(self.fresh())
        self.assertEqual(controller.status()["phase"], "verified")

    def test_nonce_title_must_match_exactly(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.window.name += " extra"
        controller.step()
        self.assertEqual(len(self.window.lines), 1)

    def test_exact_nonce_title_permits_only_native_activity_prefix(self):
        controller, authority, fresh = self.recovery_fixture()
        state = controller.status()
        self.config["cwd"] = str(self.root)
        self.window.name = "⠇ " + state["title"] + " | " + self.root.name
        self.assertEqual(
            controller.recover_maintenance(authority)["phase"], "maintenance_recovered"
        )

    def test_pre_prompt_spinner_title_holds_even_before_input_evidence_arrives(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        state = controller.status()
        self.config["cwd"] = str(self.root)
        self.window.name = "⠇ " + state["title"] + " | " + self.root.name
        controller.step()
        self.assertEqual(controller.status()["phase"], "waiting_title")
        self.assertEqual(len(self.window.lines), 1)

    def test_recovery_refuses_arbitrary_prefix_and_suffix_titles(self):
        controller, authority, fresh = self.recovery_fixture()
        state = controller.status()
        self.config["cwd"] = str(self.root)
        for title in (
            "foreign " + state["title"] + " | " + self.root.name,
            "⠇ " + state["title"] + " extra | " + self.root.name,
            "⠇ ⠇ " + state["title"] + " | " + self.root.name,
        ):
            self.window.name = title
            with self.assertRaisesRegex(ValueError, "nonce title mismatch"):
                controller.recover_maintenance(authority)

    def test_deferred_preexisting_input_refuses_prompt(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.window.rollouts = []
        self.window.context = lambda *_: {
            "session_id": "new",
            "user_input": True,
            "transcript": None,
        }
        with self.assertRaisesRegex(ValueError, "fresh user input"):
            controller.step()
        self.assertEqual(len(self.window.lines), 1)

    def test_deferred_uuid_is_bound_before_prompt(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.window.rollouts = []
        controller.step()
        fresh = self.fresh()
        fresh.write_text(fresh.read_text().replace('"new"', '"foreign"'))
        with self.assertRaisesRegex(ValueError, "context changed"):
            controller.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_late_user_message_invalidates_prepared_reset(self):
        self.hold()
        controller = self.controller()
        controller.step()
        with self.f.old_transcript.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"role": "user", "content": [{"text": "pause now"}]},
                    }
                )
                + "\n"
            )
        with self.assertRaisesRegex(ValueError, "user input changed"):
            controller.step()
        self.assertEqual(self.window.lines, [])

    def test_changed_authority_or_control_refuses_delivery(self):
        self.hold()
        controller = self.controller()
        controller.step()
        self.f.control.write_text(self.f.control.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "routing"):
            controller.step()
        self.assertEqual(self.window.lines, [])

    def test_uncertain_native_delivery_is_never_blindly_replayed(self):
        self.hold()
        controller = self.controller()
        controller.step()

        def crash(text):
            raise OSError("transport uncertain")

        self.window.clear = crash
        with self.assertRaisesRegex(OSError, "uncertain"):
            controller.step()
        recovered = self.controller()
        with self.assertRaisesRegex(ValueError, "uncertain"):
            recovered.step()
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_wrong_fresh_model_keeps_production_held(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        fresh = self.fresh()
        fresh.write_text(fresh.read_text().replace("gpt-6.1-sol", "gpt-6-astra"))
        with self.assertRaisesRegex(ValueError, "model"):
            controller.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_reset_deadline_is_clear_to_bootstrap_not_active_turn_wait(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        self.clock += 121
        with self.assertRaisesRegex(ValueError, "deadline"):
            controller.step()

    def test_receipt_publication_crash_recovers_without_second_epoch_or_prompt(self):
        from unittest.mock import patch

        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        fresh = self.fresh()
        with patch.object(
            controller, "publish", side_effect=OSError("receipt disk failure")
        ):
            with self.assertRaisesRegex(OSError, "disk failure"):
                controller.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 0)
        recovered = self.controller()
        recovered.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 1)
        self.assertEqual(len(self.window.lines), 1)
        self.assertEqual(len(self.window.queued), 1)
        self.assertEqual(recovered.status()["phase"], "verified")

    def test_stale_release_waits_for_current_fifth_boundary_instead_of_exiting(self):
        for n in range(1, 6):
            self.loop.begin(f"u{n}")
            self.f.close(f"u{n}")
        controller = self.controller()
        controller.step()
        self.assertEqual(controller.status()["phase"], "waiting_release")
        self.assertEqual(self.window.lines, [])
        release = json.loads(self.release.read_text())
        release["completed"] = sorted(self.loop.status()["completed"])
        self.release.write_text(json.dumps(release))
        controller.step()
        self.assertEqual(controller.status()["phase"], "waiting_idle")

    def test_headroom_hold_is_persisted_and_prepared_without_five_closes(self):
        with self.assertRaisesRegex(ValueError, "context-reset-required"):
            self.loop.begin("u1", headroom=False)
        controller = self.controller()
        controller.step()
        self.assertEqual(controller.status()["phase"], "waiting_idle")

    def test_unpublished_native_receipt_holds_new_epoch_admission(self):
        from unittest.mock import patch

        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        with patch.object(controller, "publish", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                controller.step(self.fresh())
        with self.assertRaisesRegex(ValueError, "native reset receipt"):
            self.loop.begin("u1")

    def test_ar1_complete_prompt_required_not_just_nonce_prefix(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        fresh = self.fresh()
        original = fresh.read_text().splitlines()
        row = json.loads(original[-1])
        prompt = row["payload"]["content"][0]["text"]
        marker = prompt[prompt.index("BUFORD_CONTEXT_HANDOFF ") :].split(". ", 1)[0]
        for broken in (marker, prompt[:-20], "prefix " + prompt, prompt + " suffix"):
            row["payload"]["content"][0]["text"] = broken
            fresh.write_text("\n".join(original[:-1] + [json.dumps(row)]) + "\n")
            with self.assertRaises(ValueError):
                controller.step(fresh)
            self.assertEqual(self.loop.status()["epoch"], 0)

    def test_ar2_new_user_before_prepare_cannot_become_authority(self):
        self.hold()
        controller = self.controller()
        with self.f.old_transcript.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"role": "user", "content": [{"text": "pause now"}]},
                    }
                )
                + "\n"
            )
        with self.assertRaisesRegex(ValueError, "user input changed"):
            controller.step()
        self.assertEqual(self.window.lines, [])

    def test_ar2_second_fresh_user_invalidates_bootstrap(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        fresh = self.fresh()
        with fresh.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"role": "user", "content": [{"text": "pause now"}]},
                    }
                )
                + "\n"
            )
        with self.assertRaises(ValueError):
            controller.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_ar3_routing_publication_crash_recovers_through_supervisor(self):
        from unittest.mock import patch

        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        fresh = self.fresh()
        save = self.loop._save

        def crash_final(state):
            if state["epoch"] == 1:
                raise OSError("crash after routing")
            save(state)

        with patch.object(self.loop, "_save", side_effect=crash_final):
            with self.assertRaises(OSError):
                controller.step(fresh)
        recovered = self.controller()
        recovered.step(fresh)
        self.assertEqual(self.loop.status()["epoch"], 1)
        self.assertEqual(len(self.window.lines), 1)
        self.assertEqual(len(self.window.queued), 1)

    def test_ar5_active_goal_tail_is_read_from_terminal_native_database(self):
        self.hold()
        controller = self.controller()
        controller.step()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE thread_goals SET tokens_used=120,time_used_seconds=12,updated_at_ms=2000"
            )
        for _ in range(3):
            controller.step()
        controller.step(self.fresh())
        ledger = json.loads(Path(self.config["goal_ledger"]).read_text())
        self.assertEqual((ledger["tokens_used"], ledger["seconds_used"]), (120, 12))

    def test_ar4_native_owned_rollout_discovery_ignores_date_partition(self):
        self.hold()
        controller = self.controller()
        for _ in range(4):
            controller.step()
        state = controller.status()
        frontier = json.loads(
            (Path(state["reset"]["directory"]) / "frontier.json").read_text()
        )
        self.root.joinpath(*frontier["prepared_at"][:10].split("-")).mkdir(parents=True)
        future = self.root / "2099/01/01"
        future.mkdir(parents=True)
        path = self.fresh()
        moved = future / path.name
        path.rename(moved)
        self.window.rollouts = [moved]
        self.assertEqual(controller.fresh(state), moved)

    def test_ar2_cleared_chat_input_holds_before_prompt_delivery(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        with self.window.rollouts[0].open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"role": "user", "content": [{"text": "pause now"}]},
                    }
                )
                + "\n"
            )
        with self.assertRaisesRegex(ValueError, "fresh user input"):
            controller.step()
        self.assertEqual(len(self.window.lines), 1)

    def test_ar2_repeated_identical_user_event_after_release_is_stale(self):
        row = (
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {"role": "user", "content": [{"text": "same"}]},
                }
            )
            + "\n"
        )
        with self.f.old_transcript.open("a") as stream:
            stream.write(row)
        from ops.orchestration.loop import identity

        release = json.loads(self.release.read_text())
        actual = identity(self.f.old_transcript)
        release["user_frontier"] = {
            "count": actual.get("user_count", 1),
            "hash": actual["last_user_hash"],
        }
        self.release.write_text(json.dumps(release))
        self.hold()
        with self.f.old_transcript.open("a") as stream:
            stream.write(row)
        with self.assertRaisesRegex(ValueError, "user input changed"):
            self.controller().step()
