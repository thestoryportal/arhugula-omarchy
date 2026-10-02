import unittest
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone


class NativeWindowTests(unittest.TestCase):
    def test_native_cd_override_does_not_require_process_chdir(self):
        from ops.orchestration.native_window import launch_cwd

        for arguments in (
            ["codex", "resume", "uuid", "-C", "/tmp/project"],
            ["codex", "--cd", "/tmp/project"],
            ["codex", "--cd=/tmp/project"],
        ):
            self.assertEqual(launch_cwd(arguments, "/home/robbo"), Path("/tmp/project"))
        self.assertEqual(launch_cwd(["codex"], "/tmp/project"), Path("/tmp/project"))
        for arguments in (["codex", "-C"], ["codex", "-C", "/a", "--cd", "/b"]):
            with self.assertRaises(ValueError):
                launch_cwd(arguments, "/tmp")

    def native_context_fixture(self):
        from ops.orchestration.native_window import NativeWindow, WindowCapability

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        (home / "thread-writer-locks").mkdir()
        window = NativeWindow(
            WindowCapability("0xabc", "stable", os.getppid(), "1", os.getpid(), "2"),
            Path.cwd(),
            codex_home=home,
        )
        window.check = lambda: None  # Compositor is the only substituted boundary.
        db = sqlite3.connect(home / "logs_2.sqlite")
        self.addCleanup(db.close)
        db.execute(
            "CREATE TABLE logs(id INTEGER PRIMARY KEY,ts INTEGER,ts_nanos INTEGER,thread_id TEXT,process_uuid TEXT,feedback_log_body TEXT,target TEXT)"
        )
        prepared = time.time() - 2
        frontier = {
            "prepared_at": datetime.fromtimestamp(prepared, timezone.utc).isoformat(),
            "native_lane": {
                "cwd": str(Path.cwd()),
                "source": "cli",
                "originator": "codex-tui",
            },
        }

        def create(offset=0, body=None, locked=True, pid=None):
            created = time.time() + offset
            identifier = str(
                uuid.UUID(int=(int(created * 1000) << 80) | (7 << 76) | (2 << 62))
            )
            stream = (home / "thread-writer-locks" / (identifier + ".lock")).open("w")
            self.addCleanup(stream.close)
            if locked:
                fcntl.flock(stream, fcntl.LOCK_EX)
            text = (
                (
                    f'rpc.method="thread/start" rpc.transport="in-process" app_server.client_name="codex-tui" '
                    f"app_server.thread_start.create_thread shell_snapshot{{thread_id={identifier}}} "
                    "Shell snapshot successfully created:"
                )
                if body is None
                else body
            )
            db.execute(
                "INSERT INTO logs(ts,ts_nanos,thread_id,process_uuid,feedback_log_body,target) VALUES(?,?,?,?,?,?)",
                (
                    int(created),
                    int((created % 1) * 1e9),
                    identifier,
                    f"pid:{pid or os.getpid()}:process",
                    text,
                    "codex_core::shell_snapshot",
                ),
            )
            db.commit()
            return identifier

        return window, home, db, frontier, create

    def retained_context_fixture(self):
        from dataclasses import asdict
        from ops.orchestration.artifacts import file_binding

        window, home, db, frontier, create = self.native_context_fixture()
        identifier = create()
        path = home / ("rollout-2026-10-02T01-00-00-" + identifier + ".jsonl")
        stream = path.open("w+")
        self.addCleanup(stream.close)
        rows = [
            {
                "type": "session_meta",
                "payload": {"id": identifier, **frontier["native_lane"]},
            },
            {
                "type": "response_item",
                "payload": {"role": "user", "content": [{"text": "human report"}]},
            },
        ]
        stream.write("".join(json.dumps(row) + "\n" for row in rows))
        stream.flush()
        db.execute(
            "INSERT INTO logs(ts,ts_nanos,thread_id,process_uuid,feedback_log_body,target) VALUES(?,?,?,?,?,?)",
            (
                int(time.time()),
                0,
                identifier,
                f"pid:{os.getpid()}:process",
                "op: TurnInput { request: ... }",
                "handlers",
            ),
        )
        db.commit()
        proof = window.context(frontier, "old")
        config = home / "config.json"
        config.write_text(json.dumps({"window": asdict(window.cap)}))
        boundary = home / "frontier.json"
        boundary.write_text(json.dumps(frontier))
        out = home / "stdout.log"
        out.write_text(json.dumps(proof) + "\n")
        receipt = home / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "argv": ["python", "-m", "read_only_native_context_witness"],
                    "cwd": str(window.cwd),
                    "exit": 0,
                    "terminal": "exited",
                    "stdout": file_binding(out),
                }
            )
        )
        grant = {
            "receipt": file_binding(receipt),
            "config": file_binding(config),
            "frontier": file_binding(boundary),
        }
        # Native log retention removes creation evidence while preserving recent activity.
        db.execute("DELETE FROM logs WHERE target='codex_core::shell_snapshot'")
        for _ in range(999):
            db.execute(
                "INSERT INTO logs(ts,ts_nanos,thread_id,process_uuid,feedback_log_body,target) VALUES(?,?,?,?,?,?)",
                (
                    int(time.time()),
                    0,
                    identifier,
                    f"pid:{os.getpid()}:process",
                    "current activity",
                    "handlers",
                ),
            )
        db.commit()
        return window, home, db, frontier, proof, grant, stream

    def test_pruned_creation_requires_explicit_retained_maintenance_witness(self):
        window, home, db, frontier, proof, grant, stream = (
            self.retained_context_fixture()
        )
        self.assertEqual(db.execute("SELECT count(*) FROM logs").fetchone()[0], 1000)
        self.assertIsNone(window.context(frontier, "old"))
        self.assertIsNone(window.recovery_context(frontier, "old", None))
        self.assertEqual(
            window.recovery_context(frontier, "old", grant)["session_id"],
            proof["session_id"],
        )
        self.assertTrue(window.recovery_context(frontier, "old", grant)["user_input"])
        self.assertIsNone(window.context(frontier, "old"))

    def test_retained_proof_contract_does_not_depend_on_diagnostic_program(self):
        from ops.orchestration.artifacts import file_binding

        window, home, db, frontier, proof, grant, stream = (
            self.retained_context_fixture()
        )
        path = Path(grant["receipt"]["path"])
        receipt = json.loads(path.read_text())
        receipt["argv"] = ["python", "-c", "print(existing_observation)"]
        path.write_text(json.dumps(receipt))
        grant["receipt"] = file_binding(path)
        self.assertEqual(
            window.recovery_context(frontier, "old", grant)["session_id"],
            proof["session_id"],
        )

    def test_retained_witness_refuses_changed_proof_and_current_ownership(self):
        from dataclasses import replace
        from ops.orchestration.artifacts import file_binding

        for kind in (
            "unbound",
            "stdout",
            "session",
            "process",
            "window",
            "frontier",
            "failed",
            "cwd",
            "foreign-rollout",
            "empty-rollout",
            "closed-rollout",
            "unlocked",
            "current-process",
            "missing",
            "contradiction",
        ):
            with self.subTest(kind=kind):
                window, home, db, frontier, proof, grant, stream = (
                    self.retained_context_fixture()
                )
                receipt_path = Path(grant["receipt"]["path"])
                receipt = json.loads(receipt_path.read_text())
                if kind == "missing":
                    grant.pop("receipt")
                elif kind == "contradiction":
                    window.context = lambda *args: {**proof, "creation_log_id": 9999}
                elif kind == "unbound":
                    receipt_path.write_text("{}")
                elif kind == "window":
                    window.cap = replace(window.cap, native_start="changed")
                elif kind == "frontier":
                    frontier = {
                        **frontier,
                        "prepared_at": datetime.now(timezone.utc).isoformat(),
                    }
                elif kind == "foreign-rollout":
                    stream.seek(0)
                    stream.truncate()
                    stream.write(
                        json.dumps(
                            {"type": "session_meta", "payload": {"id": "foreign"}}
                        )
                        + "\n"
                    )
                    stream.flush()
                elif kind == "empty-rollout":
                    stream.seek(0)
                    stream.truncate()
                    stream.flush()
                elif kind == "closed-rollout":
                    stream.close()
                elif kind == "unlocked":
                    for fd in (window.proc / "fd").iterdir():
                        try:
                            target = fd.resolve(strict=True)
                        except FileNotFoundError:
                            continue
                        if target.name == proof["session_id"] + ".lock":
                            fcntl.flock(int(fd.name), fcntl.LOCK_UN)
                elif kind == "current-process":
                    db.execute("UPDATE logs SET process_uuid='pid:999:foreign'")
                    db.commit()
                else:
                    if kind in ("stdout", "session", "process"):
                        if kind == "session":
                            proof["session_id"] = str(uuid.uuid4())
                        elif kind == "process":
                            proof["process_uuid"] = "pid:999:foreign"
                        else:
                            proof["user_input"] = False
                        Path(receipt["stdout"]["path"]).write_text(
                            json.dumps(proof) + "\n"
                        )
                        if kind != "stdout":
                            receipt["stdout"] = file_binding(receipt["stdout"]["path"])
                    elif kind == "failed":
                        receipt["exit"] = 1
                    elif kind == "cwd":
                        receipt["cwd"] = "/foreign"
                    receipt_path.write_text(json.dumps(receipt))
                    grant["receipt"] = file_binding(receipt_path)
                with self.assertRaises(ValueError):
                    window.recovery_context(frontier, "old", grant)

    def test_real_writer_fd_proves_deferred_context_with_no_rollout(self):
        window, home, db, frontier, create = self.native_context_fixture()
        identifier = create()
        proof = window.context(frontier, "old")
        self.assertEqual(proof["session_id"], identifier)
        self.assertIsNone(proof["transcript"])
        self.assertFalse(proof["user_input"])
        self.assertEqual(window.transcripts(), [])

    def test_real_owned_empty_rollout_and_persisted_header_discovery(self):
        window, home, db, frontier, create = self.native_context_fixture()
        identifier = create()
        path = home / ("rollout-2026-10-02T01-00-00-" + identifier + ".jsonl")
        with path.open("w+") as stream:
            self.assertEqual(window.context(frontier, "old")["transcript"], str(path))
            row = {
                "type": "session_meta",
                "payload": {"id": identifier, **frontier["native_lane"]},
            }
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            self.assertEqual(window.transcripts(), [path])
            self.assertEqual(window.context(frontier, "old")["session_id"], identifier)
            stream.seek(0)
            stream.truncate()
            stream.write("broken")
            stream.flush()
            with self.assertRaises(ValueError):
                window.context(frontier, "old")

    def test_parent_creation_refuses_helper_foreign_old_and_ambiguous_evidence(self):
        for kind in ("helper", "foreign", "old", "ambiguous", "unlocked"):
            with self.subTest(kind=kind):
                window, home, db, frontier, create = self.native_context_fixture()
                if kind == "helper":
                    create(body="guardian thread creation")
                elif kind == "foreign":
                    create(pid=999999)
                elif kind == "old":
                    create(offset=-10)
                elif kind == "unlocked":
                    create(locked=False)
                else:
                    create()
                    create(offset=0.01)
                if kind in ("ambiguous", "unlocked"):
                    with self.assertRaises(ValueError):
                        window.context(frontier, "old")
                else:
                    self.assertIsNone(window.context(frontier, "old"))

    def test_native_input_log_refuses_even_before_rollout_flush(self):
        window, home, db, frontier, create = self.native_context_fixture()
        identifier = create()
        db.execute(
            "INSERT INTO logs(ts,ts_nanos,thread_id,process_uuid,feedback_log_body,target) VALUES(?,?,?,?,?,?)",
            (
                int(time.time()),
                0,
                identifier,
                f"pid:{os.getpid()}:process",
                "op: TurnInput { request: ... }",
                "handlers",
            ),
        )
        db.commit()
        self.assertTrue(window.context(frontier, "old")["user_input"])

    def test_hyprland_eval_ack_is_ok_not_lua_print_output(self):
        from ops.orchestration.native_window import NativeWindow, WindowCapability

        window = NativeWindow(
            WindowCapability("0xabc", "stable", 10, "100", 11, "101"), "."
        )
        window.check = lambda: None
        window.command = lambda argv: "ok\n"
        window.type("literal")
        window.submit()

    def test_native_tab_submits_literal_composer_without_return_newlines(self):
        from ops.orchestration.native_window import NativeWindow, WindowCapability

        window = NativeWindow(
            WindowCapability("0xabc", "stable", 10, "100", 11, "101"), "."
        )
        window.check = lambda: None
        commands = []

        def command(argv):
            commands.append(argv)
            return "ok\n"

        window.command = command
        window.type("complete exact prompt")
        window.submit()
        self.assertIn('"Tab"', commands[-1][-1])
        self.assertNotIn('"Return"', commands[-1][-1])

    def test_literal_prompt_keys_are_window_bound_without_clipboard_or_focus(self):
        from ops.orchestration.native_window import key_events, input_program

        self.assertEqual(
            key_events("A1_/: "),
            [
                ("SHIFT", "a"),
                ("", "1"),
                ("SHIFT", "minus"),
                ("", "slash"),
                ("SHIFT", "semicolon"),
                ("", "space"),
            ],
        )
        program = input_program("0xabc", "A1_/: ")
        self.assertIn("address:0xabc", program)
        self.assertNotIn("focus(", program)
        self.assertNotIn("clipboard", program)

    def test_unsupported_text_is_refused_before_any_dispatch(self):
        from ops.orchestration.native_window import input_program

        for text in ("line\nbreak", "snowman \u2603", "\x00"):
            with self.assertRaises(ValueError):
                input_program("0xabc", text)
        with self.assertRaises(ValueError):
            input_program("0xabc');os.execute('bad')", "safe")

    def test_window_and_pid_reuse_refuse_target_capability(self):
        from ops.orchestration.native_window import WindowCapability

        cap = WindowCapability("0xabc", "stable", 10, "100", 11, "101")
        client = {
            "address": "0xabc",
            "stableId": "stable",
            "pid": 10,
            "mapped": True,
            "acceptsInput": True,
        }
        processes = {10: ("100", 1), 11: ("101", 10)}
        self.assertEqual(cap.parse([client], processes).address, "0xabc")
        for changed in ({**client, "stableId": "reused"}, {**client, "pid": 12}):
            with self.assertRaises(ValueError):
                cap.parse([changed], processes)
        with self.assertRaises(ValueError):
            cap.parse([client], {10: ("999", 1), 11: ("101", 10)})
        with self.assertRaises(ValueError):
            cap.parse([client], {10: ("100", 1), 11: ("101", 99)})

    def test_keyboard_layout_and_caps_must_match_literal_delivery(self):
        from ops.orchestration.native_window import require_us_keyboard

        good = {"main": True, "active_keymap": "English (US)", "capsLock": False}
        require_us_keyboard([good])
        for rows in (
            [],
            [{**good, "capsLock": True}],
            [{**good, "active_keymap": "German"}],
        ):
            with self.assertRaises(ValueError):
                require_us_keyboard(rows)
