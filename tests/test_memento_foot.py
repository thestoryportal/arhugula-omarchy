"""The session-owned Foot helper: one same-window clear, then only the bottle pointer."""

import json
from pathlib import Path
import hashlib
import os
import re
import subprocess
import tempfile
import unittest

from ops.orchestration.memento_foot.foot_helper import FootHelper
from ops.orchestration.memento_foot.build import build, LAUNCHER

# More typed characters than /clear in one burst read as a paste.
PASTE_AFTER = len("/clear")
OLD, NEW = "5a1b2c3d-0000-4000-8000-000000000001", "6e7f8091-0000-4000-8000-000000000002"


class Host:
    """Offline /proc, Claude session file, transcripts and compositor for one Claude-under-foot lane."""

    def __init__(self, root):
        self.root = Path(root)
        self.proc, self.sessions, self.projects = self.root / "proc", self.root / "sessions", self.root / "projects"
        for pid, parent, start, comm in ((50, 1, "7", "foot"), (60, 50, "9", "claude")):
            self.process(pid, parent, start, comm)
        self.sessions.mkdir()
        self.record = {"pid": 60, "procStart": "9", "pidDomain": "linux:m:pid:[1]",
                       "sessionId": OLD, "status": "busy", "updatedAt": 1}
        self.write()
        self.prompt(OLD, "earlier work")  # the outgoing session's own prompt
        self.clients = [{"pid": 50, "address": "0xabc", "mapped": True, "acceptsInput": True}]
        self.clients[0]["stableId"] = "window1"
        self.keyboard = {"main": True, "active_keymap": "English (US)", "capsLock": False}
        self.clear_changes_session, self.clear_receipt, self.foreign = True, False, []
        # The receipt's full identity is the session directory in its override path.
        self.override = lambda s: f"/p/sessions/{s}/memento.conf"
        self.draft, self.submitted, self.burst = "", [], 0
        self.after_clear_draft, self.first_inputs, self.records_input = "", [], True
        self.typed, self.ack, self.on_eval = [], "ok", None

    def process(self, pid, parent, start, comm):
        d = self.proc / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "stat").write_text(f"{pid} ({comm}) S {parent} " + " ".join(["0"] * 16) + f" 0 {start} 0\n")
        (d / "comm").write_text(comm + "\n")

    def write(self):
        (self.sessions / "60.json").write_text(json.dumps(self.record))

    def append(self, session, record):
        path = self.projects / "-w" / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def prompt(self, session, text):
        """A prompt as Claude records what a person submitted."""
        self.append(session, {"type": "user", "promptId": "p", "origin": {"kind": "human"},
                              "message": {"role": "user", "content": text}})

    def run(self, argv):
        if argv[:2] == ["hyprctl", "-j"]:
            if argv[2] == "devices":
                return json.dumps({"keyboards": [self.keyboard]})
            return json.dumps(self.clients)
        self.typed.append(argv[2])
        if self.on_eval:
            self.on_eval()  # ownership may change as soon as a script is sent
        # Claude's composer as observed on the Facade lane (cmt-80f558da): the short /clear burst
        # submitted, but a Return ending a long typing burst was pasted as a newline; a Return sent
        # after a pause submits.
        for mods, key in re.findall(r'\{("[^"}]*"),("[^"}]*")\}', argv[2]):
            mods, key = json.loads(mods), json.loads(key)
            if mods == "CTRL" and key == "u":
                self.draft = ""
            elif key == "Return" and self.burst > PASTE_AFTER:
                self.draft += "\n"
            elif key == "Return":
                self.submit()
            elif key != "Escape":
                char = {"slash": "/", "space": " ", "period": ".", "minus": "-"}.get(key, key)
                self.draft += "_" if mods == "SHIFT" and key == "minus" else char.upper() if mods == "SHIFT" else char
                self.burst += 1
        return self.ack

    def submit(self):
        text, self.draft = self.draft, ""
        self.submitted.append(text)
        if text != "/clear":
            if self.records_input:
                self.prompt(self.record["sessionId"], text)
            return
        self.record.update(updatedAt=self.record["updatedAt"] + 1, status="idle")
        if self.clear_changes_session:
            self.record["sessionId"] = NEW
        self.write()
        session = self.record["sessionId"]
        # Claude records the clear as a command, never as a person's prompt.
        self.append(session, {"type": "user", "message": {"role": "user", "content": "<command-name>/clear</command-name>"}})
        with (self.root / "clear.log").open("a") as handle:
            handle.writelines(f"t session={s[:8]} event=SessionStart override={self.override(s)} -> no-override\n"
                              for s in self.foreign + [session] * self.clear_receipt)
        for text in self.first_inputs:
            self.prompt(session, text)
        self.draft = self.after_clear_draft

    def sleep(self, _):
        self.burst = 0
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
        self.pointer = f"Read and follow the handoff at {self.msg}"

    def helper(self):
        h = self.host
        return FootHelper(60, self.msg, self.goal, 10, proc=h.proc, sessions=h.sessions,
                          run=h.run, sleep=h.sleep, timeout=3, clear_log=Path(self.dir.name) / "clear.log")

    def phase(self):
        return json.loads(self.msg.with_name("handoff.md.foot-intent").read_text())["phase"]

    def test_waits_for_idle_clears_same_window_then_submits_only_the_pointer(self):
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", self.pointer])
        self.assertEqual(self.phase(), "delivered")

    def test_actual_goal_only_is_carried_after_the_pointer_is_received(self):
        self.goal.write_text("ship the parser")
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", self.pointer, "/goal ship the parser"])

    def test_existing_composer_draft_cannot_fuse_with_clear_or_bottle(self):
        self.host.draft = "unsent draft"
        self.host.after_clear_draft = "leftover after clear"
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", self.pointer])

    def test_transient_goal_removed_only_after_success(self):
        self.goal.write_text("ship the parser")
        self.helper().handoff()
        self.assertFalse(self.goal.exists())
        self.assertTrue(self.msg.exists())

    def test_refuses_before_any_input(self):
        cases = {
            "session identity changed": lambda h: h.record.update(sessionId="other"),
            "process reused": lambda h: h.process(60, 50, "99", "claude"),
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

    def test_composer_input_refuses_text_or_address_outside_the_safe_set(self):
        for address, text in (("0xabc", "first line\nsecond input"), ("window", "text")):
            with self.subTest(address=address, text=text), self.assertRaises(ValueError):
                self.helper().composer_input(address, text)

    def test_unchanged_session_id_requires_the_clear_hook_receipt(self):
        self.host.clear_changes_session, self.host.clear_receipt = False, True
        self.helper().handoff()
        # The outgoing session's own earlier prompt is not the cleared session's first input.
        self.assertEqual((self.host.submitted, self.phase()), (["/clear", self.pointer], "delivered"))

    def test_another_sessions_same_prefix_receipt_is_not_this_sessions_clear(self):
        self.host.clear_changes_session, self.host.foreign = False, [OLD[:8] + "-1111-4000-8000-000000000009"]
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual((self.host.submitted, self.phase()), (["/clear"], "clear_intent"))

    def test_same_prefix_receipt_without_a_consistent_full_identity_delivers_nothing(self):
        for name, override in {"no session directory": lambda s: "x",
                               "another session's directory": lambda s: f"/p/sessions/{NEW}/memento.conf"}.items():
            with self.subTest(name):
                self.setUp()
                self.host.clear_changes_session, self.host.clear_receipt = False, True
                self.host.override = override
                with self.assertRaisesRegex(ValueError, "no consistent full session identity"):
                    self.helper().handoff()
                self.assertEqual((self.host.submitted, self.phase()), (["/clear"], "clear_intent"))

    def test_idle_timestamp_change_is_not_a_clear_receipt(self):
        self.host.clear_changes_session = False
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear"])

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

    def assert_not_delivered(self, reason):
        with self.assertRaisesRegex(ValueError, reason):
            self.helper().handoff()
        self.assertEqual((self.host.submitted, self.phase()), (["/clear", self.pointer], "deliver_intent"))
        self.assertTrue(self.goal.exists())
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", self.pointer])

    def test_compositor_ack_without_the_recorded_pointer_is_not_delivery(self):
        self.host.records_input = False
        self.assert_not_delivered("uncertain delivery: the cleared session never recorded the handoff")

    def test_unrelated_first_input_is_not_delivery(self):
        self.host.first_inputs = ["hello"]
        self.assert_not_delivered("uncertain delivery: the cleared session's first input is not the handoff")

    def test_ambiguous_transcripts_are_not_delivery(self):
        (self.host.projects / "-other").mkdir(parents=True)
        (self.host.projects / "-other" / f"{NEW}.jsonl").write_text("")
        self.assert_not_delivered(f"uncertain session: several transcripts name session {NEW}")

    def test_ownership_change_in_the_submit_gap_gets_no_return(self):
        for name, change in {"foot replaced at the same address": lambda h: h.process(50, 1, "12", "foot"),
                             "claude restarted under the same pid": lambda h: h.process(60, 50, "13", "claude")}.items():
            with self.subTest(name):
                self.setUp()
                self.host.on_eval = lambda change=change: change(self.host)
                with self.assertRaisesRegex(ValueError, "uncertain clear_intent: the bound foot window changed mid-input"):
                    self.helper().handoff()
                self.assertEqual((len(self.host.typed), self.host.submitted, self.phase()), (1, [], "clear_intent"))


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
