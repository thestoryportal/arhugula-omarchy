"""Memento on a Codex lane: the real Stop gate, ceiling command, launcher and Foot helper."""

import difflib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from ops.orchestration.memento_codex.build import build, HELPER

REPO = Path(__file__).resolve().parents[1]
# The exact pinned bytes of the files these gates execute; the pin below verifies every byte.
PINNED = REPO / "tests/fixtures/memento-4f95f159/memento"
THREAD = "01a1692e-9731-7251-8e34-d363eb25263a"
LAUNCHER = "skills/message-in-a-bottle/bin/finalize-session"
SKILL = "skills/message-in-a-bottle/SKILL.md"
MARKER = "handoff scheduled → foot codex pid 70 in 10s (log: /tmp/finalize-log.x)"
# A code-mode cell returning the exec_command result itself, so the command's own exit is reported.
RAN = json.dumps({"output": MARKER + "\n", "exit_code": 0}, ensure_ascii=False)


def build_plugin(out):
    """Build from the vendored subset under a pin derived from the merged PIN.json."""
    pin = json.loads((REPO / "ops/orchestration/memento_foot/PIN.json").read_text())
    named = {str(p.relative_to(PINNED)) for p in PINNED.rglob("*") if p.is_file()}
    return build(PINNED, out, {"commit": pin["commit"], "replaced": pin["replaced"],
                               "files": {n: pin["files"][n] for n in named - set(pin["replaced"])}})


def meta():
    return {"type": "session_meta", "payload": {"id": THREAD, "cwd": "/w", "cli_version": "0.159.2"}}


def user(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": text}]}}


def usage(last, total=None):
    """A Codex token_count event; the last_token_usage is the newest request's own counter."""
    info = last and {"total_token_usage": total or last, "last_token_usage": last, "model_context_window": 475000}
    return {"type": "event_msg", "payload": {"type": "token_count", "info": info}}


# The exact counter of the post-trust scratch request that the pinned hook logged as tokens=0.
POST_TRUST = {"input_tokens": 151564, "cached_input_tokens": 151424, "cache_write_input_tokens": 0,
              "output_tokens": 6, "reasoning_output_tokens": 0, "total_tokens": 151570}


def call(command, call_id="call_1"):
    return {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": call_id, "name": "exec",
                                                 "status": "completed", "input": command}}


def output(text, call_id="call_1", header="Script completed\nOutput:\n"):
    return {"type": "response_item", "payload": {
        "type": "custom_tool_call_output", "call_id": call_id,
        "output": [{"type": "input_text", "text": header}, {"type": "input_text", "text": text}]}}


class CodexGateTests(unittest.TestCase):
    """[LAW:behavior-not-structure] Each test executes the built hook, command or launcher."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.dir.name)
        cls.plugin = cls.root / "plugin"
        build_plugin(cls.plugin)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.project = self.case / "project"
        (self.project / ".promptctl").mkdir(parents=True)
        (self.project / ".promptctl/memento.conf").write_text("ceiling = 80000\n")
        self.log = self.case / "ceiling.log"
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX", "TMUX_PANE",
                                 "HYPRLAND_INSTANCE_SIGNATURE", "CLAUDE_PID")}
        self.env.update(MEMENTO_CONFIG_HOME=str(self.case / "config"), XDG_CONFIG_HOME=str(self.case / "xdg"),
                        MEMENTO_CEILING_LOG=str(self.log), HOME=str(self.case))

    def stop(self, *records):
        rollout = self.case / f"rollout-x-{THREAD}.jsonl"
        rollout.write_text("".join(json.dumps(r) + "\n" for r in (meta(), *records)))
        payload = {"hook_event_name": "Stop", "session_id": THREAD, "cwd": str(self.project),
                   "transcript_path": str(rollout), "stop_hook_active": False}
        result = subprocess.run([str(self.plugin / "hooks/scripts/context-ceiling.py")], input=json.dumps(payload),
                                env=self.env, cwd=self.project, capture_output=True, text=True)
        return result, self.log.read_text() if self.log.exists() else ""

    def test_latest_codex_request_usage_gates_past_the_ceiling(self):
        # Cumulative totals and an older, larger request are not the live context; a null-info
        # rate-limit update after the request carries no count at all.
        older = dict(POST_TRUST, input_tokens=400000)
        result, log = self.stop(user("go"), usage(older), user("Reply DONE."),
                                usage(POST_TRUST, total=dict(POST_TRUST, input_tokens=848677)), usage(None))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertIn("tokens=151570 ceiling=80000", log)

    def test_codex_rollout_without_usage_is_loud_not_zero(self):
        result, log = self.stop(user("go"), usage(None))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stopped: ValueError: no Codex last_token_usage", log)
        self.assertNotIn("tokens=0", log)

    def test_codex_closeout_is_credited_only_for_a_real_launcher_call_in_this_turn(self):
        ran = call(f"text((await tools.exec_command({{cmd:\"{self.plugin / LAUNCHER} 'bottle'\"}})).output)")
        credited, _ = self.stop(user("close out"), ran, output(RAN), usage(POST_TRUST))
        self.assertIn("close-out ran", json.loads(credited.stdout)["systemMessage"])
        forged = call(f"text((await tools.exec_command({{cmd:\"echo '{MARKER}' finalize-session\"}})).output)")
        echoed, _ = self.stop(user("close out"), forged, output(RAN), usage(POST_TRUST))
        self.assertEqual(json.loads(echoed.stdout)["decision"], "block")
        earlier, _ = self.stop(user("close out"), ran, output(RAN), user("next"), usage(POST_TRUST))
        self.assertEqual(json.loads(earlier.stdout)["decision"], "block")

    def test_failed_or_unreported_codex_command_is_not_a_closeout(self):
        ran = call(f"text((await tools.exec_command({{cmd:\"{self.plugin / LAUNCHER} 'bottle'\"}})).output)")
        # A nonzero exit in either form, a failed cell, or a completed cell whose command reported
        # no exit at all: none of them proves the launcher succeeded.
        for failed in (output(MARKER + "\nProcess exited with code 2"),
                       output(json.dumps({"output": MARKER + "\n", "exit_code": 2}, ensure_ascii=False)),
                       output(MARKER + "\nexit_code: 2"), output(RAN, header="Script failed\n"), output(MARKER)):
            result, _ = self.stop(user("close out"), ran, failed, usage(POST_TRUST))
            self.assertEqual(json.loads(result.stdout)["decision"], "block")
        reported, _ = self.stop(user("close out"), ran, output(MARKER + "\nProcess exited with code 0", header=""),
                                usage(POST_TRUST))
        self.assertIn("close-out ran", json.loads(reported.stdout)["systemMessage"])

    def test_clear_receipt_names_the_codex_process_it_ran_under(self):
        hook = str(self.plugin / "hooks/scripts/clear-session-ceiling.py")
        codex = self.case / "codex"
        codex.write_text('#!/bin/bash\necho "$$"\n"$@"\nexit $?\n')
        codex.chmod(0o755)
        payload = json.dumps({"hook_event_name": "SessionStart", "source": "clear", "session_id": "01a16999",
                              "cwd": str(self.project), "transcript_path": "/dev/null"})
        under = subprocess.run([str(codex), hook], input=payload, env=self.env, capture_output=True, text=True, check=True)
        subprocess.run([hook], input=payload, env=self.env, capture_output=True, text=True, check=True)
        start = re.search(rf" codex={under.stdout.strip()}:(\d+) -> no-override", self.log.read_text())
        self.assertIsNotNone(start, self.log.read_text())
        # With no codex ancestor the receipt names no owner: `none` where the walk runs out, or
        # `unreadable` where a shallow tree (CI) reaches pid 0 first. The helper refuses both.
        self.assertRegex(self.log.read_text(), r" codex=(none|unreadable) -> no-override\n$")

    def test_codex_guidance_is_added_to_the_unchanged_bottle_skill(self):
        pinned = (PINNED / SKILL).read_text().splitlines()
        built = (self.plugin / SKILL).read_text()
        edits = difflib.SequenceMatcher(None, pinned, built.splitlines()).get_opcodes()
        self.assertEqual({op for op, *_ in edits}, {"equal", "insert"})
        self.assertIn('`sandbox_permissions: "require_escalated"`', built)

    def test_claude_transcript_count_is_unchanged(self):
        rollout = self.case / "claude.jsonl"
        rollout.write_text(json.dumps({"type": "assistant", "message": {"usage": {
            "input_tokens": 10, "cache_read_input_tokens": 70000, "cache_creation_input_tokens": 20000,
            "output_tokens": 5}}}) + "\n")
        payload = {"hook_event_name": "Stop", "session_id": "s1", "cwd": str(self.project), "transcript_path": str(rollout)}
        subprocess.run([str(self.plugin / "hooks/scripts/context-ceiling.py")], input=json.dumps(payload),
                       env=self.env, cwd=self.project, capture_output=True, text=True, check=True)
        self.assertIn("tokens=90015 ceiling=80000", self.log.read_text())

    def test_ceiling_command_moves_the_codex_threads_own_layer(self):
        ceiling = [str(self.plugin / "skills/ceiling/bin/ceiling"), "set", "session", "200000"]
        moved = subprocess.run(ceiling, env=dict(self.env, CODEX_THREAD_ID=THREAD), cwd=self.project,
                               capture_output=True, text=True)
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertIn("200000", (self.case / "config/sessions" / THREAD / "memento.conf").read_text())
        result, log = self.stop(user("go"), usage(POST_TRUST))
        self.assertIn("tokens=151570 ceiling=200000 -> allow-under", log)
        both = subprocess.run(ceiling, env=dict(self.env, CODEX_THREAD_ID=THREAD, CLAUDE_CODE_SESSION_ID="other"),
                              cwd=self.project, capture_output=True, text=True)
        self.assertNotEqual(both.returncode, 0)
        self.assertFalse((self.case / "config/sessions/other").exists())

    def launch(self, *args, chain=("foot",), **env):
        """Run the built launcher under an offline process table: this shell, codex 70, then the
        `chain` of its ancestors as pids 50, 40, ... under init."""
        tools = self.case / "tools"
        tools.mkdir(exist_ok=True)
        pids = [50 - 10 * i for i in range(len(chain))]
        cases = "".join(f"{pid}:comm) echo {comm};; {pid}:ppid) echo {parent};; "
                        for pid, comm, parent in zip(pids, chain, pids[1:] + [1]))
        (tools / "ps").write_text(f"""#!/bin/sh
pid=$(echo "$*" | sed 's/.*-p *//'); field=$(echo "$*" | sed 's/.*-o *\\([a-z]*\\).*/\\1/')
case "$pid:$field" in 70:comm) echo codex;; 70:ppid) echo 50;; {cases}
  *:ppid) echo 70;; *) echo bash;; esac
""")
        # A resolvable pane: tmux answers for %1 as a live pane, which a Claude lane would take.
        (tools / "tmux").write_text('#!/bin/sh\ncase "$1" in display-message) echo "%1 0 s:0.0";; esac\n')
        for tool in tools.iterdir():
            tool.chmod(0o755)
        env = dict(self.env, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}", FINALIZE_DRY_RUN="1",
                   MEMENTO_HANDOFF_DIR=str(self.case / "handoffs"), CODEX_THREAD_ID=THREAD, **env)
        return subprocess.run(["bash", str(self.plugin / LAUNCHER), *args], env=env, capture_output=True, text=True)

    def test_launcher_selects_same_foot_codex_transport_or_refuses(self):
        # Foot runs codex directly, or through the login shell it started (the retained Scratch lane).
        for chain in (("foot",), ("bash", "foot")):
            selected = self.launch("bottle", chain=chain, HYPRLAND_INSTANCE_SIGNATURE="offline", TMUX_PANE="%1")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertIn(f"transport=foot-codex codex_pid=70 thread={THREAD}", selected.stdout)
        refused = [self.launch("--goal", "ship it", "bottle", HYPRLAND_INSTANCE_SIGNATURE="offline"),
                   *(self.launch("bottle", chain=chain, HYPRLAND_INSTANCE_SIGNATURE="offline")
                     for chain in (("bash",), ("bash", "bash", "foot"), ("bash", "kitty"), ("tmux", "foot"))),
                   self.launch("bottle")]
        for result in refused:
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn("transport=", result.stdout)


class CodexHost:
    """Offline /proc, Codex rollout, plugin receipt log and compositor for one codex-under-foot lane."""

    def __init__(self, root, shell=False):
        self.root = Path(root)
        self.proc = self.root / "proc"
        # codex 60 runs directly in foot 50, or in the bash 55 that foot started for it.
        for pid, parent, start, comm in ((50, 1, "7", "foot"), (55, 50, "8", "bash"),
                                         (60, 55 if shell else 50, "9", "codex")):
            self.process(pid, parent, start, comm)
        self.home = self.root / "codex"
        self.rollout = self.home / "sessions/2026/10/23" / f"rollout-2026-10-23T00-00-00-{THREAD}.jsonl"
        self.rollout.parent.mkdir(parents=True)
        self.event("task_started")
        self.clear_log = self.root / "ceiling.log"
        self.clear_log.write_text(f"t session={THREAD[:8]} event=Stop tokens=1 ceiling=2 -> allow-under\n")
        self.clients = [{"pid": 50, "address": "0xabc", "mapped": True, "acceptsInput": True, "stableId": "w1"}]
        self.keyboard = {"main": True, "active_keymap": "English (US)", "capsLock": False}
        self.new_sessions, self.foreign, self.ends_turn = ["01a16999"], [], True
        self.draft, self.submitted, self.burst, self.records_input, self.on_sleep = "", [], False, True, None
        self.evals, self.on_eval = 0, None

    def process(self, pid, parent, start, comm):
        d = self.proc / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "stat").write_text(f"{pid} ({comm}) S {parent} " + " ".join(["0"] * 16) + f" 0 {start} 0\n")
        (d / "comm").write_text(comm + "\n")

    def event(self, kind):
        with self.rollout.open("a") as handle:
            handle.write(json.dumps({"type": "event_msg", "payload": {"type": kind}}) + "\n")

    def run(self, argv):
        if argv[:2] == ["hyprctl", "-j"]:
            return json.dumps({"keyboards": [self.keyboard]} if argv[2] == "devices" else self.clients)
        self.evals += 1
        if self.on_eval:
            self.on_eval()  # ownership may change as soon as a script is sent
        # Codex's composer as observed in the Scratch lane: Ctrl-U leaves the line, Ctrl-A then Ctrl-K
        # empties it, and a Return inside a typing burst is pasted as a newline instead of submitting.
        for mods, key in re.findall(r'\{("[^"}]*"),("[^"}]*")\}', argv[2]):
            mods, key = json.loads(mods), json.loads(key)
            if (mods, key) == ("CTRL", "k"):
                self.draft = ""
            elif key == "Return" and self.burst:
                self.draft += "\n"
            elif key == "Return":
                self.submit()
            elif mods != "CTRL" and key != "Escape":
                char = {"slash": "/", "space": " ", "period": ".", "minus": "-"}.get(key, key)
                self.draft += "_" if mods == "SHIFT" and key == "minus" else char.upper() if mods == "SHIFT" else char
                self.burst = True
        return "ok"

    def submit(self):
        text, self.draft = self.draft, ""
        self.submitted.append(text)
        if text == "/clear":
            with self.clear_log.open("a") as handle:
                handle.writelines(f"t session={s} event=SessionStart override=x codex={owner} -> no-override\n"
                                  for s, owner in self.foreign)
                handle.writelines(f"t session={s} event=SessionStart override=x codex=60:9 -> no-override\n"
                                  for s in self.new_sessions)
        elif self.records_input:
            rollout = self.rollout.with_name(f"rollout-2026-10-23T00-00-01-{self.new_sessions[0]}-7000.jsonl")
            with rollout.open("a") as handle:
                handle.write(json.dumps(user(text)) + "\n")

    def sleep(self, _):
        self.burst = False
        if self.on_sleep:
            self.on_sleep()
        if self.ends_turn:
            self.event("task_complete")  # the outgoing Codex turn ends while the helper waits
            self.ends_turn = False


class CodexFootHelperTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        # The installed layout: the Codex helper loads its sibling foot-helper by path.
        shutil.copy(REPO / "ops/orchestration/memento_foot/foot_helper.py", bin_dir / "foot-helper")
        shutil.copy(REPO / "ops/orchestration/memento_codex/codex_foot_helper.py", bin_dir / Path(HELPER).name)
        loader = importlib.machinery.SourceFileLoader("codex_foot_helper", str(bin_dir / Path(HELPER).name))
        self.module = importlib.util.module_from_spec(importlib.util.spec_from_loader("codex_foot_helper", loader))
        loader.exec_module(self.module)
        self.host = CodexHost(root)
        self.msg = root / "handoff.md"
        self.msg.write_text("bottle")
        self.goal = root / "goal"
        self.goal.write_text("")

    def helper(self):
        return self.module.CodexFootHelper(60, self.msg, self.goal, 0, thread=THREAD, codex_home=self.host.home,
                                           proc=self.host.proc, run=self.host.run, sleep=self.host.sleep,
                                           timeout=3, clear_log=self.host.clear_log)

    def test_waits_for_turn_end_clears_same_window_then_types_only_the_pointer(self):
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_clear_without_a_new_session_receipt_delivers_nothing(self):
        self.host.new_sessions = []
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear"])

    def test_another_lanes_clear_receipt_is_not_this_windows_clear(self):
        self.host.new_sessions, self.host.foreign = [], [("01a16bbb", "999:1")]
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear"])

    def test_unbound_clear_receipts_are_not_this_windows_clear(self):
        self.host.new_sessions, self.host.foreign = [], [("01a16bbb", "none"), ("01a16ccc", "unreadable")]
        with self.assertRaisesRegex(ValueError, "uncertain clear"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear"])

    def test_own_clear_receipt_beside_another_lanes_still_delivers(self):
        self.host.foreign = [("01a16bbb", "999:1")]
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_ambiguous_new_sessions_deliver_nothing(self):
        self.host.new_sessions = ["01a16999", "01a16aaa"]
        with self.assertRaisesRegex(ValueError, "several new sessions"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear"])

    def test_unparseable_rollout_line_is_not_a_turn_state(self):
        with self.host.rollout.open("a") as handle:
            handle.write('{"type": "event_msg", "payload": {"type": "task_sta\n')
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_slash_residue_is_emptied_and_each_input_submits_apart_from_its_typing(self):
        self.host.draft = "/sta"
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_handoff_the_new_thread_never_records_is_uncertain_and_not_replayed(self):
        self.host.records_input = False
        with self.assertRaisesRegex(ValueError, "uncertain delivery"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])
        self.assertIn("deliver_intent", self.msg.with_name(self.msg.name + ".foot-intent").read_text())
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.helper().handoff()

    def test_codex_in_its_foot_launch_shell_is_bound_and_delivered(self):
        self.host = CodexHost(Path(self.dir.name) / "shell", shell=True)
        self.helper().handoff()
        self.assertEqual(self.host.submitted, ["/clear", f"Read and follow the handoff at {self.msg}"])

    def test_replaced_launch_shell_is_a_changed_window(self):
        self.host = CodexHost(Path(self.dir.name) / "shell", shell=True)
        self.host.on_sleep = lambda: self.host.process(55, 50, "11", "bash")
        with self.assertRaisesRegex(ValueError, "window changed before the clear"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, [])

    def assert_gap_change_sends_no_return(self, change):
        """`change` replaces ownership right after the first script (the typed /clear) is sent."""
        self.host.on_eval = change
        with self.assertRaisesRegex(ValueError, "uncertain clear_intent: the bound foot window changed mid-input"):
            self.helper().handoff()
        self.assertEqual((self.host.evals, self.host.submitted), (1, []))
        self.assertIn("clear_intent", self.msg.with_name(self.msg.name + ".foot-intent").read_text())

    def test_launch_shell_replaced_in_the_submit_gap_gets_no_return(self):
        self.host = CodexHost(Path(self.dir.name) / "shell", shell=True)
        self.assert_gap_change_sends_no_return(lambda: self.host.process(55, 50, "11", "bash"))

    def test_foot_replaced_at_the_same_address_in_the_submit_gap_gets_no_return(self):
        self.assert_gap_change_sends_no_return(lambda: self.host.process(50, 1, "12", "foot"))

    def test_codex_restarted_under_the_same_pid_in_the_submit_gap_gets_no_return(self):
        self.assert_gap_change_sends_no_return(lambda: self.host.process(60, 50, "13", "codex"))

    def test_launch_shell_outside_foot_is_refused_before_input(self):
        self.host = CodexHost(Path(self.dir.name) / "shell", shell=True)
        self.host.process(50, 1, "7", "kitty")
        with self.assertRaisesRegex(ValueError, "no longer under its foot terminal"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, [])

    def test_turn_that_never_ends_times_out_without_input(self):
        self.host.ends_turn = False
        with self.assertRaisesRegex(ValueError, "never went idle"):
            self.helper().handoff()
        self.assertEqual(self.host.submitted, [])

    def test_binding_refuses_a_process_that_is_not_codex(self):
        (self.host.proc / "60/comm").write_text("claude\n")
        with self.assertRaisesRegex(ValueError, "not codex"):
            self.helper()


if __name__ == "__main__":
    unittest.main()
