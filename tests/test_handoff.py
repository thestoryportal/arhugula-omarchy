import json
import os
from pathlib import Path
import tempfile
import unittest

from ops.orchestration.handoff import validate, write_handoff, read_handoff, launch_plan


def record(worktree="/tmp/isolated repo"):
    return dict(version=1, active_ticket="unit-1", parent_epic="epic-1",
                branch="feature/one", worktree=worktree, model="gpt-6-astra", effort="high",
                role="implement", goal="Finish prerequisite", completed_work=["routing"],
                verification=["10 tests pass"], risks=[], next_ticket="unit-2", stop_reason=None)


class HandoffTests(unittest.TestCase):
    def test_roundtrip_private_atomic_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "handoff.json"
            write_handoff(path, record())
            self.assertEqual(read_handoff(path), record())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            changed = {**record(), "completed_work": ["routing", "handoff"]}
            write_handoff(path, changed)
            self.assertEqual(read_handoff(path), changed)

    def test_missing_fields_versions_types_and_model_pair_rejected(self):
        for changed in [dict(version=99), dict(effort="medium"), dict(model="unknown"),
                        dict(risks="none"), dict(goal=""), dict(worktree="relative"),
                        dict(stop_reason=""), dict(next_ticket=5), dict(role="bogus")]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate({**record(), **changed})
        for field in record():
            incomplete = record()
            del incomplete[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(incomplete)

    def test_failed_validation_preserves_last_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff.json"
            write_handoff(path, record())
            with self.assertRaises(ValueError):
                write_handoff(path, {**record(), "verification": None})
            self.assertEqual(read_handoff(path), record())

    def test_symlink_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("untouched")
            link = Path(directory) / "link"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                write_handoff(link, record())
            self.assertEqual(target.read_text(), "untouched")

    def test_fresh_process_argv_preserves_model_effort_and_context(self):
        plan = launch_plan(record())
        self.assertEqual(plan["argv"][:4], ["codex", "exec", "--model", "gpt-6-astra"])
        self.assertIn('model_reasoning_effort="high"', plan["argv"])
        self.assertIn("/tmp/isolated repo", plan["argv"])
        self.assertEqual(plan["cwd"], "/tmp/isolated repo")
        self.assertIn('"next_ticket": "unit-2"', plan["prompt"])
        self.assertIn("LIT", plan["prompt"])
        self.assertFalse(plan["shell"])

    def test_tmux_uses_separate_arguments_not_interpolated_shell(self):
        plan = launch_plan(record(), transport="tmux", name="lane_1")
        self.assertEqual(plan["argv"][:4], ["tmux", "new-session", "-d", "-s"])
        self.assertIn("codex", plan["argv"])
        self.assertIn('model_reasoning_effort="high"', plan["argv"])
        with self.assertRaises(ValueError):
            launch_plan(record(), transport="tmux", name="bad;name")

    def test_stop_record_and_empty_queue_do_not_launch(self):
        for changed in [dict(stop_reason="hil-required"), dict(next_ticket=None)]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                launch_plan({**record(), **changed})

    def test_corrupt_record_does_not_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text('{"version": 1')
            with self.assertRaises(ValueError):
                read_handoff(path)
