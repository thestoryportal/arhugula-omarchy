"""The session-owned Foot helper: one same-window clear, then only the bottle pointer."""

import json
from pathlib import Path
import hashlib
import os
import re
import subprocess
import tempfile
import unittest

from ops.orchestration.memento_foot.foot_helper import FootHelper, keystrokes
from ops.orchestration.memento_foot.build import build, LAUNCHER


class Host:
    """Offline /proc, Claude session file and compositor for one Claude-under-foot lane."""

    def __init__(self, root):
        self.root = Path(root)
        self.proc, self.sessions = self.root / "proc", self.root / "sessions"
        for pid, parent, start, comm in ((50, 1, "7", "foot"), (60, 50, "9", "claude")):
            d = self.proc / str(pid)
            d.mkdir(parents=True)
            (d / "stat").write_text(f"{pid} ({comm}) S {parent} " + " ".join(["0"] * 16) + f" 0 {start} 0\n")
            (d / "comm").write_text(comm + "\n")
        self.sessions.mkdir()
        self.record = {"pid": 60, "procStart": "9", "pidDomain": "linux:m:pid:[1]",
                       "sessionId": "s1", "status": "busy", "updatedAt": 1}
        self.write()
        self.clients = [{"pid": 50, "address": "0xabc", "mapped": True, "acceptsInput": True}]
        self.clients[0]["stableId"] = "window1"
        self.keyboard = {"main": True, "active_keymap": "English (US)", "capsLock": False}
        self.clear_changes_session = True
        self.draft, self.submitted = "", []
        self.after_clear_draft = ""
        self.typed, self.ack = [], "ok"

    def write(self):
        (self.sessions / "60.json").write_text(json.dumps(self.record))

    def run(self, argv):
        if argv[:2] == ["hyprctl", "-j"]:
            if argv[2] == "devices":
                return json.dumps({"keyboards": [self.keyboard]})
            return json.dumps(self.clients)
        self.typed.append(argv[2])
        for mods, key in re.findall(r'\{("[^"}]*"),("[^"}]*")\}', argv[2]):
            mods, key = json.loads(mods), json.loads(key)
            if mods == "CTRL" and key == "u":
                self.draft = ""
            elif key == "Return":
                self.submitted.append(self.draft)
                self.draft = ""
            elif key != "Escape":
                char = {"slash": "/", "space": " ", "period": ".", "minus": "-"}.get(key, key)
                self.draft += "_" if mods == "SHIFT" and key == "minus" else char.upper() if mods == "SHIFT" else char
        if self.submitted and self.submitted[-1] == "/clear":
            self.record.update(updatedAt=self.record["updatedAt"] + 1, status="idle")
            if self.clear_changes_session:
                self.record["sessionId"] = "s2"
            self.write()
            self.draft = self.after_clear_draft
        return self.ack

    def sleep(self, _):
        self.record["status"] = "idle"  # the outgoing turn ends while the helper waits
        self.write()


class FootHelperTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.host = Host(self.dir.name)
        self.msg = Path(self.dir.name) / "handoff.md"
        self.msg.write_text("handoff text")
        self.goal = Path(self.dir.name) / "goal"
        self.goal.write_text("")

    def helper(self):
        h = self.host
        return FootHelper(60, self.msg, self.goal, 10, proc=h.proc, sessions=h.sessions,
                          run=h.run, sleep=h.sleep, timeout=3, clear_log=Path(self.dir.name) / "clear.log")

    def test_waits_for_idle_clears_same_window_then_types_only_the_pointer(self):
        self.helper().handoff()
        self.assertEqual(self.host.typed, [keystrokes("0xabc", "/clear"),
                                           keystrokes("0xabc", f"Read and follow the handoff at {self.msg}")])
        self.assertEqual(json.loads(self.msg.with_name("handoff.md.foot-intent").read_text())["phase"], "delivered")

    def test_actual_goal_only_is_carried(self):
        self.goal.write_text("ship the parser")
        self.helper().handoff()
        self.assertEqual(self.host.typed[-1], keystrokes("0xabc", "/goal ship the parser"))

    def test_existing_composer_draft_cannot_fuse_with_clear_or_bottle(self):
        self.host.draft = "unsent draft"
        self.host.after_clear_draft = "leftover after clear"
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_transient_goal_removed_only_after_success(self):
        self.goal.write_text("ship the parser")
        self.helper().handoff()
        self.assertFalse(self.goal.exists())
        self.assertTrue(self.msg.exists())

    def test_refuses_before_any_input(self):
        cases = {
            "session identity changed": lambda h: h.record.update(sessionId="other"),
            "process reused": lambda h: (h.proc / "60" / "stat").write_text("60 (claude) S 50 " + "0 " * 17 + "99 0\n"),
            "no longer under foot": lambda h: (h.proc / "50" / "comm").write_text("bash\n"),
            "ambiguous window": lambda h: h.clients.append(dict(h.clients[0], address="0xdef")),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.setUp()
                helper = self.helper()
                original = self.host.sleep

                def sleep(seconds, mutate=mutate, original=original):
                    original(seconds)
                    mutate(self.host)
                    self.host.write() if name == "session identity changed" else None
                self.host.sleep = sleep
                helper.sleep = sleep
                with self.assertRaisesRegex(ValueError, "refused"):
                    helper.handoff()
                self.assertEqual(self.host.typed, [])

    def test_busy_session_times_out_without_input(self):
        helper = self.helper()
        helper.sleep = lambda _: None  # the session never goes idle
        with self.assertRaisesRegex(ValueError, "never went idle"):
            helper.handoff()
        self.assertEqual(self.host.typed, [])

    def test_uncertain_effect_surfaces_and_is_never_replayed(self):
        self.host.ack = "error"
        with self.assertRaisesRegex(ValueError, "uncertain clear_intent"):
            self.helper().handoff()
        self.assertEqual(len(self.host.typed), 1)
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.helper().handoff()
        self.assertEqual(len(self.host.typed), 1)
        self.assertTrue(self.goal.exists())
        self.assertTrue(self.msg.exists())

    def test_keystrokes_refuse_text_outside_the_safe_set(self):
        with self.assertRaises(ValueError):
            keystrokes("0xabc", "first line\nsecond input")

    def test_unchanged_session_id_requires_the_clear_hook_receipt(self):
        self.host.clear_changes_session = False
        original = self.host.run
        def run(argv):
            result = original(argv)
            if argv[:2] == ["hyprctl", "eval"] and len(self.host.typed) == 1:
                (Path(self.dir.name) / "clear.log").write_text(
                    "2026-10-23T00:00:00 session=s1 event=SessionStart override=x -> no-override\n")
            return result
        self.host.run = run
        self.helper().handoff()
        self.assertEqual(len(self.host.typed), 2)

    def test_idle_timestamp_change_is_not_a_clear_receipt(self):
        self.host.clear_changes_session = False
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual(len(self.host.typed), 1)

    def test_reused_window_is_refused_before_input(self):
        helper = self.helper()
        original = helper.sleep
        def reuse(seconds):
            original(seconds)
            self.host.clients[0]["stableId"] = "replacement"
        helper.sleep = reuse
        with self.assertRaisesRegex(ValueError, "window"):
            helper.handoff()
        self.assertEqual(self.host.typed, [])

    def test_wrong_keyboard_is_refused_before_input(self):
        self.host.keyboard["capsLock"] = True
        with self.assertRaisesRegex(ValueError, "keyboard"):
            self.helper().handoff()
        self.assertEqual(self.host.typed, [])


class BuildTests(unittest.TestCase):
    def test_additive_patch_builds_and_selects_foot(self):
        # [LAW:behavior-not-structure] Execute the built launcher; no compositor or reset runs.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "upstream"
            launcher = upstream / LAUNCHER
            launcher.parent.mkdir(parents=True)
            launcher.write_text(r'''#!/usr/bin/env bash
set -euo pipefail
HOSTED=""
HANDOFF_DELAY_SECONDS=10
MSGFILE=/tmp/bottle
GOAL=""
_find_claude_session() { [[ "${MISSING_OWNER:-}" != 1 ]] || return 1; printf '60\nclaude'; }
_refuse() { echo "$*" >&2; exit 2; }
if false; then
      trap - EXIT
      echo "handoff scheduled → tmux $TARGET in ${HANDOFF_DELAY_SECONDS}s (log: $LOGFILE)"

    elif [[ -z "$HOSTED" && "${TERM_PROGRAM:-}" == "iTerm.app" && -n "${ITERM_SESSION_ID:-}" ]] \
         && osascript -e 'tell application "iTerm2" to get version' >/dev/null 2>&1; then
      echo iterm
else
      echo detached
fi
''')
            launcher.chmod(0o755)
            pin = {"commit": "fixture", "files": {}, "replaced": {LAUNCHER: hashlib.sha256(launcher.read_bytes()).hexdigest()}}
            built = root / "built"
            build(upstream, built, pin)
            tools = root / "tools"
            tools.mkdir()
            ps = tools / "ps"
            ps.write_text('#!/bin/sh\ncase "$*" in *comm*) if [ "${WRONG_PARENT:-}" = 1 ]; then echo bash; else echo foot; fi;; *) echo 50;; esac\n')
            ps.chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                       HYPRLAND_INSTANCE_SIGNATURE="offline", FINALIZE_DRY_RUN="1")
            for missing, wrong_parent, expected in [("", "", 0), ("1", "", 2), ("", "1", 2)]:
                result = subprocess.run(["bash", str(built / LAUNCHER)], env=dict(env, MISSING_OWNER=missing, WRONG_PARENT=wrong_parent), capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 0:
                    self.assertIn("transport=foot", result.stdout)
                else:
                    self.assertNotIn("detached", result.stdout)


if __name__ == "__main__":
    unittest.main()
