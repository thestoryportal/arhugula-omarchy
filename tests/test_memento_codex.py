"""Behavioral tests for the Memento same-window Buford reset core."""

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
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


if __name__ == "__main__":
    unittest.main()
