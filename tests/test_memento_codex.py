"""Behavioral tests for the Memento same-window Buford reset core."""

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "ops" / "orchestration" / "vendor" / "memento"
ROW = {"role": "buford", "ceiling": 200000, "reserve": 15000, "task_budget": 20000}


def summary(**changes):
    value = {
        "kind": "codex",
        "session_id": "01a165ea-9859-7551-9ec4-82ace6fd4419",
        "identity_conflict": False,
        "model": "gpt-6.1-sol",
        "status": "complete",
        "latest_request_input_tokens": 100000,
        "latest_response_output_tokens": 1000,
        "reported_context_window_tokens": 475000,
        "metric_error": None,
        "completion_count": 3,
    }
    value.update(changes)
    return value


class Layers:
    def __init__(self, test):
        self.directory = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.directory))

    def write(self, text, name="codex.conf"):
        path = self.directory / name
        path.write_text(text)
        return [path]


class VendorPin(unittest.TestCase):
    def test_vendored_upstream_bytes_equal_the_pin(self):
        pin = json.loads((VENDOR / "PIN.json").read_text())
        self.assertEqual(pin["commit"], "4f95f15954318b2bebe8996d52ec8191aba85c42")
        for name, record in pin["files"].items():
            digest = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
            self.assertEqual(digest, record["sha256"], name)
        self.assertEqual(
            pin["files"]["ceiling_config.py"]["sha256"],
            "cdcc1d8fdc98424b2ca7bab0d2e628145c1eea462bcb110fd2237805dab7382c",
        )

    def test_adapter_uses_only_the_three_pinned_upstream_names(self):
        tree = ast.parse((ROOT / "ops" / "orchestration" / "ceiling.py").read_text())
        used = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "memento"
        }
        self.assertEqual(used, {"ceiling_in", "folded", "GRACE"})


class BoundRule(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import ceiling

        self.ceiling = ceiling
        self.layers = Layers(self)

    def bound(self, layer="ceiling = 150_000\n", row=ROW, **changes):
        measurement = self.ceiling.Measurement.parse(summary(**changes))
        return self.ceiling.Bound.resolve(row, self.layers.write(layer), measurement)

    def test_worked_example(self):
        bound = self.bound()
        self.assertEqual(
            (bound.ceiling, bound.reserve, bound.close, bound.soft, bound.grace),
            (200000, 15000, 185000, 150000, 35000),
        )
        self.assertEqual(bound.limit, 185000)

    def test_window_below_operating_ceiling_lowers_the_bound(self):
        bound = self.bound(reported_context_window_tokens=180000)
        self.assertEqual((bound.ceiling, bound.close), (180000, 165000))

    def test_larger_measured_handoff_reserve_lowers_hard_close(self):
        measurement = self.ceiling.Measurement.parse(summary())
        bound = self.ceiling.Bound.resolve(
            ROW, self.layers.write("ceiling = 150_000\n"), measurement, handoff_reserve=40000
        )
        self.assertEqual((bound.reserve, bound.close, bound.grace), (40000, 160000, 10000))

    def test_grace_is_a_maximum_not_added_capacity(self):
        bound = self.bound("ceiling = 50_000\n")
        self.assertEqual((bound.grace, bound.limit), (100000, 150000))

    def test_off_nonpositive_signed_and_above_close_refuse(self):
        for text in ("ceiling = off\n", "ceiling = 0\n", "ceiling = 190_000\n", "ceiling = -400_000\n"):
            with self.subTest(text=text), self.assertRaises(self.ceiling.CeilingHold):
                self.bound(text)

    def test_missing_or_malformed_layer_holds_instead_of_exiting(self):
        with self.assertRaises(self.ceiling.CeilingHold):
            self.ceiling.Bound.resolve(
                ROW, [self.layers.directory / "absent.conf"], self.ceiling.Measurement.parse(summary())
            )
        with self.assertRaises(self.ceiling.CeilingHold):
            self.bound("limit = 150_000\n")

    def test_bands_at_boundaries(self):
        bound = self.bound()
        band = self.ceiling.band
        self.assertEqual(band(149999, bound), "under")
        self.assertEqual(band(150000, bound), "finish")
        self.assertEqual(band(184999, bound), "finish")
        self.assertEqual(band(185000, bound), "close")


class MeasuredAdmission(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import ceiling

        self.ceiling = ceiling
        self.layers = Layers(self).write("ceiling = 150_000\n")

    def decide(self, expected=None, **changes):
        measurement = self.ceiling.Measurement.parse(summary(**changes))
        bound = self.ceiling.Bound.resolve(ROW, self.layers, measurement)
        return self.ceiling.decide(measurement, bound, ROW["task_budget"], expected=expected)

    def test_unknown_identity_model_window_or_metric_holds(self):
        for change in (
            {"session_id": None},
            {"model": None},
            {"reported_context_window_tokens": None},
            {"latest_request_input_tokens": None},
            {"identity_conflict": True},
            {"metric_error": "partial"},
        ):
            with self.subTest(change=change), self.assertRaises(self.ceiling.CeilingHold):
                self.decide(**change)

    def test_changed_identity_model_or_window_holds(self):
        expected = self.ceiling.Measurement.parse(summary()).identity
        for change in (
            {"session_id": "01a10e35-d6c4-7282-9ef8-2c7c8629ae4a"},
            {"model": "gpt-6-sol"},
            {"reported_context_window_tokens": 258400},
        ):
            with self.subTest(change=change), self.assertRaises(self.ceiling.CeilingHold):
                self.decide(expected=expected, **change)

    def test_each_lane_window_gets_its_own_bound(self):
        worker = self.ceiling.Measurement.parse(summary(reported_context_window_tokens=180000))
        bound = self.ceiling.Bound.resolve(ROW, self.layers, worker)
        self.assertEqual((bound.ceiling, bound.close, bound.identity.window), (180000, 165000, 180000))
        small = self.ceiling.Measurement.parse(summary(reported_context_window_tokens=150000))
        with self.assertRaises(self.ceiling.CeilingHold):
            self.ceiling.Bound.resolve(ROW, self.layers, small)

    def test_budget_and_reserve_must_fit_even_below_soft_threshold(self):
        decision = self.decide(latest_request_input_tokens=170000, latest_response_output_tokens=0)
        self.assertEqual(decision.band, "finish")
        decision = self.decide(latest_request_input_tokens=140000, latest_response_output_tokens=0)
        self.assertEqual((decision.band, decision.admit), ("under", True))
        tight = dict(ROW, task_budget=60000)
        measurement = self.ceiling.Measurement.parse(summary(latest_request_input_tokens=140000, latest_response_output_tokens=0))
        decision = self.ceiling.decide(measurement, self.ceiling.Bound.resolve(tight, self.layers, measurement), 60000)
        self.assertEqual((decision.band, decision.admit), ("under", False))
        self.assertIn("insufficient-headroom", decision.reasons)

    def test_over_operating_ceiling_lane_must_close_out(self):
        decision = self.decide(latest_request_input_tokens=244059, latest_response_output_tokens=1650)
        self.assertEqual((decision.band, decision.admit), ("close", False))
        self.assertIn("released boundary", decision.instruction)

    def test_one_decision_key_per_completed_turn(self):
        one, two = self.decide(), self.decide()
        self.assertEqual(one.turn, two.turn)
        self.assertNotEqual(one.turn, self.decide(completion_count=4).turn)


OUT = "01a165ea-9859-7551-9ec4-82ace6fd4419"
CHILD = "01a165ea-98ea-7983-93d2-b28384fe495e"
DEAD = "01a10e35-d6c4-7282-9ef8-2c7c8629ae4a"
FRESH = "01a170aa-0000-7000-8000-000000000001"


def lock_line(number, pid, path):
    info = os.stat(path)
    return (
        f"{number}: FLOCK  ADVISORY  WRITE {pid} "
        f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino} 0 EOF"
    )


class FakeHost:
    """A fake /proc and Codex home backed by real files, so devices/inodes are real."""

    def __init__(self, test, native_pid=4484):
        self.root = Path(tempfile.mkdtemp())
        test.addCleanup(self.cleanup)
        self.proc = self.root / "proc"
        self.home = self.root / "codex"
        (self.home / "thread-writer-locks").mkdir(parents=True)
        (self.home / "sessions").mkdir()
        self.proc.mkdir()
        (self.proc / "sys/kernel/random").mkdir(parents=True)
        (self.proc / "sys/kernel/random/boot_id").write_text("boot-b\n")
        self.btime = 2_000_000_000
        (self.proc / "stat").write_text(f"cpu 1 2 3\nbtime {self.btime}\n")
        (self.proc / "locks").write_text("")
        self.native = native_pid
        self.locks = []
        self.fds = {}

    def cleanup(self):
        for path in self.root.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o700)
        __import__("shutil").rmtree(self.root)

    def lock_file(self, session, suffix=""):
        path = self.home / "thread-writer-locks" / f"{session}.lock{suffix}"
        path.write_text("")
        return path

    def rollout(self, session, *, source="cli", parent=None, when=None):
        path = self.home / "sessions" / f"rollout-2026-10-23T00-00-00-{session}.jsonl"
        meta = {"id": session, "cwd": str(self.root), "source": source, "originator": "codex-tui"}
        if parent is not None:
            meta["parent_thread_id"] = parent
        path.write_text(json.dumps({"type": "session_meta", "timestamp": "2026-10-23T00:00:00Z", "payload": meta}) + "\n")
        if when is not None:
            os.utime(path, (when, when))
        return path

    def hold(self, pid, path, *, lock=True, fd=None):
        fds = self.proc / str(pid) / "fd"
        info = self.proc / str(pid) / "fdinfo"
        fds.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        number = str(fd if fd is not None else 3 + len(self.fds.setdefault(pid, [])))
        (fds / number).symlink_to(path)
        self.fds[pid].append(number)
        text = "pos:\t0\nflags:\t02\n"
        if lock:
            self.locks.append(lock_line(len(self.locks) + 1, pid, path))
            text += f"lock:\t1: FLOCK  ADVISORY  WRITE {pid} 00:00:0 0 EOF\n"
        (info / number).write_text(text)
        (self.proc / "locks").write_text("\n".join(self.locks) + "\n")
        return number


class LockTable(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import native_window

        self.nw = native_window
        self.host = FakeHost(self)

    def test_each_flock_maps_to_its_holder_fd_by_device_and_inode(self):
        path = self.host.lock_file(OUT)
        self.host.hold(4484, path)
        table = self.nw.lock_table(self.host.proc)
        self.assertEqual([(h.pid, h.name) for h in table], [(4484, str(path))])

    def test_unmapped_lock_entry_holds(self):
        path = self.host.lock_file(OUT)
        self.host.hold(4484, path)
        (self.host.proc / "locks").write_text(lock_line(1, 9999, path) + "\n")
        with self.assertRaises(ValueError):
            self.nw.lock_table(self.host.proc)

    def test_permission_denied_holder_fd_table_holds(self):
        path = self.host.lock_file(OUT)
        self.host.hold(4484, path)
        (self.host.proc / "4484" / "fd").chmod(0)
        with self.assertRaises(ValueError):
            self.nw.lock_table(self.host.proc)

    def test_fd_closing_mid_scan_is_ignored_but_coverage_still_required(self):
        held = self.host.lock_file(OUT)
        self.host.hold(4484, held)
        gone = self.host.root / "gone"
        (self.host.proc / "4484" / "fd" / "9").symlink_to(gone)
        self.assertEqual(len(self.nw.lock_table(self.host.proc)), 1)


class PredecessorRule(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import native_window

        self.nw = native_window
        self.host = FakeHost(self)
        self.rollout = self.host.rollout(DEAD, when=self.host.btime - 3600)
        self.seal = self.nw.seal_predecessor(DEAD, self.rollout, self.host.home, self.host.proc)

    def absent(self):
        return self.nw.predecessor_absent(self.seal, self.host.home, self.host.proc)

    def test_previous_boot_predecessor_with_no_current_owner_passes(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        self.assertTrue(self.absent())
        self.assertEqual(self.seal["boot_id"], "boot-b")

    def test_missing_lock_path_alone_does_not_pass_when_rollout_is_held(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        self.host.hold(5555, self.rollout)
        with self.assertRaises(ValueError):
            self.absent()

    def test_renamed_or_deleted_held_lock_still_holds(self):
        self.host.hold(5555, self.host.lock_file(DEAD, " (deleted)"))
        with self.assertRaises(ValueError):
            self.absent()

    def test_activity_at_or_after_boot_holds(self):
        late = self.host.rollout(DEAD, when=self.host.btime + 1)
        with self.assertRaises(ValueError):
            self.nw.seal_predecessor(DEAD, late, self.host.home, self.host.proc)

    def test_rollout_change_between_prepare_and_clear_holds(self):
        with self.rollout.open("a") as stream:
            stream.write("{}\n")
        os.utime(self.rollout, (self.host.btime - 10, self.host.btime - 10))
        with self.assertRaises(ValueError):
            self.absent()

    def test_changed_boot_holds(self):
        (self.host.proc / "sys/kernel/random/boot_id").write_text("boot-c\n")
        with self.assertRaises(ValueError):
            self.absent()


class OutgoingLane(unittest.TestCase):
    def setUp(self):
        from ops.orchestration import native_window

        self.host = FakeHost(self)
        self.cap = native_window.WindowCapability("0xa", "1", 2827, "1", 4484, "2")
        cwd = str(self.host.root)
        self.window = native_window.NativeWindow(self.cap, cwd, codex_home=self.host.home)
        self.window.proc = self.host.proc / "4484"
        self.window.proc.mkdir()
        (self.window.proc / "cmdline").write_bytes(b"codex\0--no-daemon\0")
        (self.window.proc / "cwd").symlink_to(cwd)
        self.window.check = lambda: {}
        self.frontier = {"native_lane": {"cwd": cwd, "source": "cli", "originator": "codex-tui"}}

    def lane(self):
        return self.window.outgoing(self.frontier)

    def test_writer_lock_joined_to_its_sole_cli_rollout_with_subagent_child(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        out = self.host.rollout(OUT)
        self.host.hold(4484, out, lock=False)
        self.host.hold(4484, self.host.lock_file(CHILD))
        self.host.hold(4484, self.host.rollout(CHILD, source={"subagent": {"other": "guardian"}}, parent=OUT), lock=False)
        lane = self.lane()
        self.assertEqual((lane["thread"], lane["rollout"]), (OUT, str(out)))
        self.assertEqual(lane["inode"], os.stat(out).st_ino)

    def test_unproven_extra_lock_refuses(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        self.host.hold(4484, self.host.rollout(OUT), lock=False)
        self.host.hold(4484, self.host.lock_file(CHILD))
        with self.assertRaises(ValueError):
            self.lane()

    def test_child_of_another_session_refuses(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        self.host.hold(4484, self.host.rollout(OUT), lock=False)
        self.host.hold(4484, self.host.lock_file(CHILD))
        self.host.hold(4484, self.host.rollout(CHILD, source={"subagent": {}}, parent=DEAD), lock=False)
        with self.assertRaises(ValueError):
            self.lane()

    def test_second_cli_rollout_refuses(self):
        self.host.hold(4484, self.host.lock_file(OUT))
        self.host.hold(4484, self.host.rollout(OUT), lock=False)
        self.host.hold(4484, self.host.lock_file(CHILD))
        self.host.hold(4484, self.host.rollout(CHILD), lock=False)
        with self.assertRaises(ValueError):
            self.lane()

    def test_lock_not_write_held_by_native_pid_refuses(self):
        number = self.host.hold(4484, self.host.lock_file(OUT))
        self.host.hold(4484, self.host.rollout(OUT), lock=False)
        (self.window.proc / "fdinfo" / number).write_text("pos:\t0\n")
        with self.assertRaises(ValueError):
            self.lane()


class FreshContextMark(unittest.TestCase):
    BODY = (
        'rpc.method="thread/start" rpc.transport="in-process" app_server.client_name="codex-tui" '
        "app_server.thread_start.create_thread shell_snapshot{thread_id=%s} Shell snapshot successfully created:"
    )

    def setUp(self):
        import sqlite3
        from ops.orchestration import native_window

        self.host = FakeHost(self)
        self.db = sqlite3.connect(self.host.home / "logs_2.sqlite")
        self.addCleanup(self.db.close)
        self.db.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER, ts_nanos INTEGER, thread_id TEXT, "
            "process_uuid TEXT, target TEXT, feedback_log_body TEXT)"
        )
        cap = native_window.WindowCapability("0xa", "1", 2827, "1", 4484, "2")
        self.window = native_window.NativeWindow(cap, "/w", codex_home=self.host.home)
        self.window.check = lambda: {}
        self.window.rollouts = lambda: []
        self.owned = {FRESH}
        self.window.owned_threads = lambda frontier: self.owned
        self.row(OUT, "pid:4484:old")
        self.frontier = {
            "native_lane": {"cwd": "/w", "source": "cli", "originator": "codex-tui"},
            "prepared_at": "2026-10-23T00:00:00+00:00",
            "log_mark": self.window.log_mark(),
            "excluded_sessions": [OUT, DEAD],
        }

    def row(self, session, process, ts=1792900000):
        self.db.execute(
            "INSERT INTO logs (ts, ts_nanos, thread_id, process_uuid, target, feedback_log_body) VALUES (?,?,?,?,?,?)",
            (ts, 0, session, process, "codex_core::shell_snapshot", self.BODY % session),
        )
        self.db.commit()

    def context(self):
        return self.window.context(self.frontier, OUT)

    def test_rows_at_or_below_mark_never_suffice(self):
        self.assertIsNone(self.context())

    def test_post_mark_creation_row_by_the_native_process_proves_fresh_context(self):
        self.row(FRESH, "pid:4484:new")
        proof = self.context()
        self.assertEqual((proof["session_id"], proof["process_uuid"]), (FRESH, "pid:4484:new"))

    def test_mixed_process_uuids_after_mark_refuse(self):
        self.row(FRESH, "pid:4484:new")
        self.row(FRESH, "pid:4484:other")
        with self.assertRaises(ValueError):
            self.context()

    def test_reused_excluded_uuid_refuses(self):
        self.frontier["excluded_sessions"].append(FRESH)
        self.row(FRESH, "pid:4484:new")
        with self.assertRaises(ValueError):
            self.context()

    def test_new_thread_lock_not_held_by_native_pid_refuses(self):
        self.owned = set()
        self.row(FRESH, "pid:4484:new")
        with self.assertRaises(ValueError):
            self.context()


import test_loop  # noqa: E402  (the shared journal fixture, as test_startup_budget uses it)


def bottle_data(**changes):
    value = {
        "role": "buford",
        "outgoing": {"session_id": "live", "model": "gpt-6.1-sol", "effort": "high", "window": 475000, "process": "pid:4484:2"},
        "lit": {"ticket": "arhugula-harness-trial-193.c12", "comments": ["cmt-1"]},
        "release_receipt": "/r/owner.json",
        "pause": ["docs/orchestration/session-control.json#repair_paused", "AGENTS.md:109-116"],
        "goal_receipt": "/r/goal.json",
        "next_step": "startup packet, finish, then Loop.begin",
    }
    value.update(changes)
    return value


class MementoPackage(unittest.TestCase):
    setUp = test_loop.LoopTests.setUp
    fresh_transcript = test_loop.LoopTests.fresh_transcript

    def outgoing_rollout(self, status="task_complete"):
        path = self.root / "live.jsonl"
        rows = [
            {"type": "session_meta", "payload": {"id": "live", "cwd": "/w", "source": "cli", "originator": "codex-tui"}},
            {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "high"}},
            {"type": "event_msg", "payload": {"type": status}},
        ]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path

    def prepare(self, bottle=None):
        from ops.orchestration.ceiling import Authority
        from ops.orchestration.loop import Bottle

        layer = Layers(self).write("ceiling = 150_000\n")[0]
        self.authority = Authority.seal({"ceiling_layers": [str(layer)], "handoff_reserve": 40000}).record
        self.bottle = self.root / "bottle.json"
        self.bottle.write_text(json.dumps(bottle or bottle_data()))
        continuation, goal = self.root / "continuation.txt", self.root / "goal.json"
        continuation.write_text("next")
        goal.write_text("{}")
        rollout = self.outgoing_rollout()
        memento = {
            "outgoing": {"thread": "live", "rollout": str(rollout), "device": 1, "inode": 2},
            "predecessor": {"session": "old"},
            "log_mark": 41,
            "bottle": Bottle.parse(self.bottle).binding,
            "ceiling": self.authority,
        }
        automatic = {"config": "/c.json", "continuation": str(continuation), "goal_receipt": str(goal), "memento": memento}
        return self.loop.prepare_clear(self.root / "package", [], automatic=automatic), rollout

    def test_outgoing_lane_is_previous_and_routed_journal_identity_is_inherited(self):
        reset, _ = self.prepare()
        self.assertEqual((reset["previous_session"], reset["inherited_session"]), ("live", "old"))
        frontier = json.loads((self.root / "package/frontier.json").read_text())
        self.assertEqual(frontier["log_mark"], 41)
        self.assertEqual(set(frontier["excluded_sessions"]), {"live", "old", "protected"})
        prompt = (self.root / "package/resume-prompt.txt").read_text()
        self.assertIn(f"sealed bottle {self.bottle}", prompt)
        self.assertIn("FROM: Outgoing Buford live, lead orchestrator (inherited routed predecessor old)", prompt)
        # Admission takes the sealed authority from the journal, never from prompt arguments.
        self.assertNotIn("--ceiling-layer", prompt)
        self.assertEqual((frontier["ceiling"], self.loop._read()["ceiling"]), (self.authority, self.authority))

    def test_bottle_is_sealed_before_clear_and_a_changed_bottle_refuses(self):
        reset, _ = self.prepare()
        manifest = json.loads(Path(reset["manifest"]["path"]).read_text())
        self.assertIn(str(self.bottle), [f["path"] for f in manifest["files"]])
        self.bottle.write_text(json.dumps(bottle_data(next_step="changed")))
        with self.assertRaises(ValueError):
            self.loop.clear_package(reset)

    def test_bottle_carries_pointers_only(self):
        from ops.orchestration.loop import Bottle

        for bad in (bottle_data(objective="ship it"), bottle_data(deadline="x"), bottle_data(lit={"ticket": "t", "comments": []})):
            path = self.root / "bad.json"
            path.write_text(json.dumps(bad))
            with self.subTest(bad=sorted(bad)), self.assertRaises(ValueError):
                Bottle.parse(path)

    def test_ready_clear_binds_the_outgoing_lane_not_the_routed_predecessor(self):
        _, rollout = self.prepare()
        self.assertTrue(self.loop.ready_clear(rollout)["clear_allowed"])
        with self.assertRaises(ValueError):
            self.loop.ready_clear(self.old_transcript)

    def test_fresh_identity_equal_to_the_inherited_predecessor_refuses(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.loop.bootstrap(self.fresh_transcript("old"))

    def test_ceiling_reset_request_is_idempotent_and_holds_admission(self):
        evidence = {"turn": "live:3", "band": "close", "usage": 190000}
        self.loop.request_reset(evidence)
        self.assertEqual(self.loop.request_reset(evidence), [evidence])
        with self.assertRaisesRegex(ValueError, "context-reset-required"):
            self.loop.begin("u1")

    def test_startup_holds_despite_an_older_epoch_receipt(self):
        state = self.loop._read()
        state.update(startup_required=True, startup_receipt={"epoch": state["epoch"] - 1})
        self.loop._save(state)
        with self.assertRaisesRegex(ValueError, "startup context receipt"):
            self.loop.begin("u1")


class StubLoop:
    def __init__(self):
        self.requests = []

    def _control(self):
        return {"sessions": [dict(ROW, session_id=OUT, transcript="/dead.jsonl")]}

    def status(self):
        return {}

    def request_reset(self, evidence):
        self.requests.append(evidence)


class StubWindow:
    def __init__(self):
        self.instructions = []
        self.fail = None

    def outgoing(self, frontier):
        return {"thread": OUT, "rollout": "/live.jsonl", "device": 1, "inode": 2}

    def instruct(self, frontier, thread, text):
        if self.fail:
            raise self.fail
        self.instructions.append((thread, text))
        return {"message_id": "m", "session_id": thread}


class CeilingFold(unittest.TestCase):
    def setUp(self):
        from ops.orchestration.auto_reset import AutoReset

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root))
        layers = Layers(self).write("ceiling = 150_000\n")
        self.loop, self.window = StubLoop(), StubWindow()
        config = {"cwd": "/w", "memento": {"ceiling_layers": [str(p) for p in layers], "handoff_reserve": 0}}
        self.controller = AutoReset(self.loop, self.root / "supervisor.json", config, self.window)

    def fold(self, **changes):
        with mock.patch("ops.orchestration.auto_reset.inspect_transcript", return_value=summary(**changes)):
            return self.controller.fold(self.controller.status())

    def test_repeated_turn_end_gives_one_decision_and_one_instruction(self):
        for _ in range(3):
            self.fold(latest_request_input_tokens=160000)
        self.assertEqual(len(self.window.instructions), 1)
        self.assertEqual(self.window.instructions[0][0], OUT)
        self.assertEqual(self.controller.status()["ceiling_decisions"][f"{OUT}:3"]["phase"], "instructed")

    def test_close_band_requests_one_reset_and_under_band_instructs_nothing(self):
        self.fold(latest_request_input_tokens=100000)
        self.assertEqual((self.window.instructions, self.loop.requests), ([], []))
        self.fold(latest_request_input_tokens=190000, completion_count=4)
        self.fold(latest_request_input_tokens=190000, completion_count=4)
        self.assertEqual(len(self.loop.requests), 1)
        self.assertIn("released boundary", self.window.instructions[-1][1])

    def test_crash_after_instruction_intent_never_replays(self):
        self.window.fail = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.fold(latest_request_input_tokens=160000)
        self.window.fail = None
        with self.assertRaisesRegex(ValueError, "uncertain ceiling instruction"):
            self.fold(latest_request_input_tokens=160000)
        self.assertEqual(self.window.instructions, [])

    def test_active_turn_is_not_measured_until_its_end(self):
        self.fold(status="active", latest_request_input_tokens=190000)
        self.assertNotIn("ceiling_decisions", self.controller.status())


class SupervisorService(unittest.TestCase):
    def test_absent_compositor_is_a_read_only_wait_until_the_socket_returns(self):
        from ops.orchestration import auto_reset

        runtime = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(runtime))
        socket_path = runtime / "hypr" / "sig" / ".socket2.sock"
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            socket_path.parent.mkdir(parents=True, exist_ok=True)
            socket_path.write_text("")

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "HYPRLAND_INSTANCE_SIGNATURE": "sig"}):
            with self.assertRaises(auto_reset.CompositorAbsent):
                auto_reset.Wakeups([]).close()
            auto_reset.compositor_wait(sleep)
        self.assertEqual(sleeps, [5])

    def test_unit_is_installed_persistent_and_not_session_bound(self):
        text = (ROOT / "ops/orchestration/units/buford-memento-reset.service").read_text()
        directives = [line for line in text.splitlines() if line and not line.startswith("#")]
        for line in ("Type=exec", "Restart=on-failure", "WantedBy=default.target"):
            self.assertIn(line, directives)
        self.assertFalse([line for line in directives if line.startswith(("PartOf=", "BindsTo="))])
        start = next(line for line in directives if line.startswith("ExecStart=")).split("=", 1)[1].split()
        self.assertEqual(start[1:4], ["-m", "ops.orchestration.auto_reset", "run"])
        self.assertTrue(start[0].startswith("/") and start[-1].startswith("/"))

    def test_executing_source_closure_covers_every_imported_module_and_startup(self):
        from ops.orchestration import auto_reset, loop, native_window
        from ops.orchestration.artifacts import file_binding

        closure = {path.name for path in auto_reset.source_closure()}
        # The fresh context runs startup; the supervisor runs auto_reset and what both import.
        for name in ("startup.py", "auto_reset.py", "loop.py", "native_window.py", "ceiling.py",
                     "ceiling_config.py", "artifacts.py", "records.py", "session_context.py"):
            self.assertIn(name, closure)
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        authority, continuation, layer = root / "a", root / "c", root / "codex.conf"
        for path in (authority, continuation, layer):
            path.write_text("ceiling = 150_000\n")
        full = [file_binding(p) for p in (*auto_reset.source_closure(), *auto_reset.CLOSURE_FILES, layer)]
        startup = next(b for b in full if b["path"].endswith("orchestration/startup.py"))
        base = [file_binding(m.__file__) for m in (auto_reset, loop, native_window)]
        for name, acceptance in (
            ("selected modules only", base),
            ("startup omitted", [b for b in full if b is not startup]),
            ("startup mutated", [b if b is not startup else {**b, "sha256": "0" * 64} for b in full]),
        ):
            config = {"authority": file_binding(authority), "continuation": file_binding(continuation),
                      "source_acceptance": acceptance, "memento": {"ceiling_layers": [str(layer)]}}
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, "not attested|binding changed"):
                auto_reset.AutoReset(None, root / "s.json", config, None).bindings()
        config["source_acceptance"] = full
        auto_reset.AutoReset(None, root / "s.json", config, None).bindings()


import test_auto_reset  # noqa: E402  (the shared supervisor fixture)


class LiveWindow:
    """The proven live lane differs from the journal's routed identity."""

    def __init__(self, root, rollout):
        self.home, self.rollout = root, rollout

    def outgoing(self, frontier):
        return {"thread": "live", "rollout": str(self.rollout), "device": 1, "inode": 2}

    def log_mark(self):
        return 41


class OutgoingGoalRelease(unittest.TestCase):
    """F1: release and prepare bind the live outgoing goal; the journal UUID is inherited."""

    def setUp(self):
        import sqlite3

        fixture = test_auto_reset.AutoResetTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f, self.root = fixture, fixture.root
        rollout = self.root / "live.jsonl"
        rollout.write_text("".join(json.dumps(r) + "\n" for r in (
            {"type": "session_meta", "payload": {"id": "live", "cwd": str(self.root), "source": "cli", "originator": "codex-tui"}},
            {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "high"}},
            {"type": "event_msg", "payload": {"type": "task_complete"}})))
        self.goals = {}
        for thread, used in (("live", 50), ("old", 100)):
            path = self.root / f"goal-{thread}.json"
            path.write_text(json.dumps({"goal": {"threadId": thread, "objective": "full scope", "tokensUsed": used,
                                                 "timeUsedSeconds": 5, "status": "paused"}, "remainingTokens": None}))
            self.goals[thread] = path
        with sqlite3.connect(fixture.database) as connection:
            connection.execute("INSERT INTO thread_goals VALUES (?,?,?,?,?,?,?,?,?)",
                               ("live", "goal", "full scope", "paused", None, 50, 5, 1000, 1000))
        self.bottle = self.root / "bottle.json"
        self.bottle.write_text(json.dumps(bottle_data(outgoing={**bottle_data()["outgoing"], "session_id": "live"})))
        self.ownership = self.root / "ownership.json"
        self.ownership.write_text(json.dumps({"owned_processes": []}))
        layer = Layers(self).write("ceiling = 150_000\n")[0]
        fixture.config["memento"] = {"ceiling_layers": [str(layer)], "handoff_reserve": 0}
        fixture.window = LiveWindow(self.root, rollout)
        self.controller = fixture.controller()

    def release(self, thread):
        return self.controller.release(self.ownership, self.goals[thread], self.bottle)

    def test_release_then_prepare_binds_the_live_goal_and_inherits_the_journal_uuid(self):
        from ops.orchestration.artifacts import file_binding

        self.assertEqual(self.f.loop.status()["session_id"], "old")
        record = self.release("live")
        self.assertEqual((record["outgoing"], record["inherited_session"]), ("live", "old"))
        self.assertEqual(record["goal_receipt"], str(self.goals["live"].absolute()))
        ledger = json.loads(Path(self.f.config["goal_ledger"]).read_text())
        self.assertIn("live", ledger["threads"])
        self.assertNotIn("old", ledger["threads"])
        with mock.patch("ops.orchestration.auto_reset.seal_predecessor", return_value={"session": "old"}):
            prepared = self.controller.prepare()
        self.assertEqual(prepared["phase"], "waiting_idle")
        self.assertEqual(prepared["goal_receipt"], file_binding(self.goals["live"]))
        reset = self.f.loop.status()["reset"]
        self.assertEqual((reset["previous_session"], reset["inherited_session"]), ("live", "old"))
        prompt = (Path(reset["directory"]) / "resume-prompt.txt").read_text()
        self.assertIn("FROM: Outgoing Buford live", prompt)
        self.assertNotIn("FROM: Outgoing Buford old", prompt)

    def test_a_goal_observed_on_the_stale_journal_uuid_is_refused(self):
        with self.assertRaisesRegex(ValueError, "actual current goal observation required"):
            self.release("old")
        self.assertFalse(Path(self.f.config["release"]).read_text().count('"outgoing"'))


class OneCeilingAuthority(unittest.TestCase):
    """F2: workflow admission and the supervisor consume one sealed ceiling authority."""

    setUp = test_loop.LoopTests.setUp

    def seal(self, reserve=40000, text="ceiling = 150_000\n"):
        from ops.orchestration.ceiling import Authority

        self.layer = Layers(self).write(text)[0]
        record = Authority.seal({"ceiling_layers": [str(self.layer)], "handoff_reserve": reserve}).record
        state = self.loop._read()
        state["ceiling"] = record
        self.loop._save(state)
        return record

    def begin(self, *extra, task_budget=30000, **changes):
        from ops.orchestration import loop

        row = dict(ROW, task_budget=task_budget)
        control = json.loads(self.control.read_text())
        control["sessions"][0].update(row, session_id="old")
        self.control.write_text(json.dumps(control))
        actual = {"session_id": "old", "model": "gpt-6.1-sol", "effort": "high"}
        measured = summary(**{"session_id": "old", "latest_request_input_tokens": 140000, **changes})
        argv = ["loop", "--state", str(self.loop.path), "--control", str(self.control), "begin", "u1", *extra]
        with mock.patch.object(loop, "identity", return_value=actual), \
                mock.patch.object(loop, "NativeLit", return_value=self.lit), \
                mock.patch("ops.orchestration.session_context.inspect_transcript", return_value=measured), \
                mock.patch("sys.argv", argv), mock.patch("sys.stdout", new_callable=__import__("io").StringIO), \
                mock.patch("sys.stderr", new_callable=__import__("io").StringIO) as stderr:
            code = loop.main()
        return code, stderr.getvalue()

    def test_cli_admission_applies_the_sealed_handoff_reserve(self):
        # 140000 + 30000 + max(15000 row, 40000 sealed) = 210000 > 200000.
        self.seal(reserve=40000)
        code, stderr = self.begin()
        self.assertEqual(code, 2)
        self.assertIn("context-reset-required", stderr)
        self.assertTrue(self.loop._read()["reset_requested"])

    def test_cli_admits_when_the_same_authority_fits(self):
        self.seal(reserve=15000)
        code, stderr = self.begin(latest_request_input_tokens=100000)
        self.assertEqual((code, stderr), (0, ""))

    def test_caller_supplied_ceiling_layer_is_refused(self):
        self.seal(reserve=15000)
        other = Layers(self).write("ceiling = 180_000\n", name="other.conf")[0]
        with self.assertRaises(SystemExit):
            self.begin("--ceiling-layer", str(other))

    def test_missing_changed_or_unknown_inputs_hold_without_requesting_reset(self):
        for name, prepare, changes in (
            ("no sealed authority", lambda: None, {}),
            ("layer changed after seal", lambda: (self.seal(), self.layer.write_text("ceiling = 190_000\n")), {}),
            ("unknown window", self.seal, {"reported_context_window_tokens": None}),
            ("changed model", self.seal, {"model": "gpt-6-sol"}),
        ):
            with self.subTest(case=name):
                state = self.loop._read()
                state.pop("ceiling", None)
                state["reset_requested"] = False
                self.loop._save(state)
                prepare()
                code, stderr = self.begin(**changes)
                self.assertEqual(code, 2)
                self.assertIn("ceiling-hold", stderr)
                self.assertFalse(self.loop._read()["reset_requested"])

    def test_cli_decides_on_the_verified_bytes_when_the_layer_changes_before_parsing(self):
        from ops.orchestration import ceiling

        self.seal(reserve=15000)
        real = ceiling.Authority.sealed.__func__

        def verified_then_changed(cls, record):
            authority = real(cls, record)
            self.layer.write_text("ceiling = 180_000\n")
            return authority

        # Reviewer probe: 160000 usage, 10000 task, 15000 reserve. The sealed 150000 is
        # finish/deny; the reopened 180000 would be under and fit (159000+10000+15000).
        with mock.patch.object(ceiling.Authority, "sealed", classmethod(verified_then_changed)):
            code, stderr = self.begin(task_budget=10000, latest_request_input_tokens=159000)
        self.assertEqual(code, 2)
        self.assertIn("context-reset-required", stderr)
        self.assertTrue(self.loop._read()["reset_requested"])

    def test_supervisor_decides_on_the_sealed_bytes_when_the_layer_changes_before_parsing(self):
        from ops.orchestration import ceiling
        from ops.orchestration.auto_reset import AutoReset

        layer = Layers(self).write("ceiling = 150_000\n")[0]
        real = ceiling.Authority.seal.__func__

        def sealed_then_changed(cls, memento_config):
            authority = real(cls, memento_config)
            layer.write_text("ceiling = 180_000\n")
            return authority

        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        window = StubWindow()
        config = {"cwd": "/w", "memento": {"ceiling_layers": [str(layer)], "handoff_reserve": 0}}
        controller = AutoReset(StubLoop(), root / "supervisor.json", config, window)
        with mock.patch.object(ceiling.Authority, "seal", classmethod(sealed_then_changed)), \
                mock.patch("ops.orchestration.auto_reset.inspect_transcript",
                           return_value=summary(latest_request_input_tokens=159000)):
            controller.fold(controller.status())
        decision = controller.status()["ceiling_decisions"][f"{OUT}:3"]
        self.assertEqual((decision["band"], decision["bound"]["soft"], decision["admit"]), ("finish", 150000, False))
        self.assertEqual(len(window.instructions), 1)

    def test_supervisor_refuses_a_config_bound_that_differs_from_the_sealed_one(self):
        from ops.orchestration.auto_reset import AutoReset
        from ops.orchestration.ceiling import Authority, CeilingHold

        layer = Layers(self).write("ceiling = 150_000\n")[0]
        sealed = Authority.seal({"ceiling_layers": [str(layer)], "handoff_reserve": 40000}).record
        stub = StubLoop()
        stub.status = lambda: {"ceiling": sealed}
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        config = {"cwd": "/w", "memento": {"ceiling_layers": [str(layer)], "handoff_reserve": 15000}}
        controller = AutoReset(stub, root / "supervisor.json", config, StubWindow())
        with mock.patch("ops.orchestration.auto_reset.inspect_transcript", return_value=summary()), \
                self.assertRaisesRegex(CeilingHold, "sealed ceiling authority"):
            controller.fold(controller.status())


if __name__ == "__main__":
    unittest.main()
