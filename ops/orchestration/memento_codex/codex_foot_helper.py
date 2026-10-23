"""Session-owned delayed Foot handoff for a Codex lane: the Foot helper reading Codex's own records.

Codex keeps no per-process session file. Its thread is the CODEX_THREAD_ID this helper inherits
from the launcher, its turn state is the newest task event in that thread's rollout, and its clear
is proven only by this plugin's SessionStart(clear) receipt for a new thread, written by a hook
running under this same codex process. Its window may sit one launch shell above codex, and its
composer needs its own line clearing and a separate submit; the keyboard check, the handoff
sequence and the intent before every effect are the Foot helper's own.
"""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

# Installed beside the Foot helper, which has no .py suffix, so it is loaded by path.
_loader = importlib.machinery.SourceFileLoader("foot_helper", str(Path(__file__).with_name("foot-helper")))
foot = importlib.util.module_from_spec(importlib.util.spec_from_loader("foot_helper", _loader))
_loader.exec_module(foot)

TURN_STATE = {"task_started": "busy", "task_complete": "idle", "turn_aborted": "idle"}
# Foot may run codex through the login shell it started for it (`foot bash -ic codex`).
LAUNCH_SHELL = "bash"
# Codex reads a fast keystroke burst as a paste, so a Return inside it becomes a newline; a Return
# sent after this pause submits. [LAW:no-ambient-temporal-coupling] exception: the burst window
# belongs to Codex's composer and is observable only as this behavior.
SUBMIT_GAP_SECONDS = 1.0


def composer_input(address, text):
    """Two compositor scripts for Codex's composer: replace the line with `text`, then submit.
    Ctrl-U leaves slash-command residue there; Ctrl-A then Ctrl-K empties the line."""
    foot.keystrokes(address, text)  # [LAW:single-enforcer] the Foot helper's address/text refusal
    typed = [("CTRL", "a"), ("CTRL", "k")] + [foot.KEYS.get(c, ("SHIFT" if c.isupper() else "", c.lower()))
                                              for c in text]
    return [script(address, typed), script(address, [("", "Return")])]


def script(address, keys):
    events = ",".join("{" + json.dumps(m) + "," + json.dumps(k) + "}" for m, k in keys)
    return (f"for _,k in ipairs({{{events}}}) do hl.dispatch(hl.dsp.send_shortcut("
            f'{{mods=k[1],key=k[2],window="address:{address}"}})) end')


def user_text(line):
    """The text of a user message rollout line, or None for any other or torn line."""
    try:
        payload = json.loads(line).get("payload")
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "message" or payload.get("role") != "user":
        return None
    return "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "input_text")


class CodexFootHelper(foot.FootHelper):
    def __init__(self, pid, msgfile, goalfile, delay, thread=None, codex_home=None, **host):
        super().__init__(pid, msgfile, goalfile, delay, **host)
        self.thread = thread or os.environ["CODEX_THREAD_ID"]
        self.home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        rollouts = self.rollouts(self.thread)
        if len(rollouts) != 1:
            raise ValueError(f"refused: {len(rollouts)} rollouts name codex thread {self.thread}")
        self.rollout = rollouts[0]
        if self.comm(self.pid) != "codex":
            raise ValueError("refused: the bound process is not codex")
        self.start = self.stat(self.pid)[1]
        self.receipts_at_bind = self.clear_receipts()
        # The capability every input is checked against. A Foot address alone is not ownership:
        # a replacement Foot can reuse it, so the whole process/start/window tuple is compared.
        self.bound = self.window()

    def comm(self, pid):
        return (self.proc / str(pid) / "comm").read_text().strip()

    def rollouts(self, thread):
        return list((self.home / "sessions").glob(f"*/*/*/rollout-*-{thread}*.jsonl"))

    def window(self):
        """The one mapped Foot window running this codex, directly or through its launch shell.
        Codex's and the shell's pid and start ticks join the binding, so a restarted codex or a
        replaced shell is a changed window."""
        parent, start = self.stat(self.pid)
        parent = int(parent)
        shell = [(parent, self.stat(parent)[1])] if self.comm(parent) == LAUNCH_SHELL else []
        terminal = int(self.stat(parent)[0]) if shell else parent
        if self.comm(terminal) != "foot":
            raise ValueError("refused: codex is no longer under its foot terminal")
        clients = [c for c in json.loads(self.run(["hyprctl", "-j", "clients"])) if c.get("pid") == terminal]
        if len(clients) != 1 or not clients[0].get("mapped") or not clients[0].get("acceptsInput"):
            raise ValueError("refused: foot window is missing, ambiguous or not accepting input")
        return (clients[0]["address"], clients[0]["stableId"], terminal, self.stat(terminal)[1],
                (self.pid, start), *shell)

    def effect(self, phase, address, text):
        """The Foot helper's durable intent, then Codex's composer input. [LAW:verifiable-goals] a
        compositor ack is not delivery: the handoff counts only once the new thread records it."""
        scripts = composer_input(address, text)
        with self.intent.open("w") as handle:
            handle.write(json.dumps({"phase": phase, "address": address}))
            handle.flush()
            os.fsync(handle.fileno())
        for each in scripts:
            # [LAW:no-ambient-temporal-coupling] the submit gap is time in which ownership can change,
            # so each script, not just each phase, is sent only to the still-bound window.
            if self.window() != self.bound:
                raise ValueError(f"uncertain {phase}: the bound foot window changed mid-input; never replayed")
            self.keyboard()
            if self.run(["hyprctl", "eval", each]).strip() != "ok":
                raise ValueError(f"uncertain {phase}: compositor did not acknowledge; never replayed")
            self.sleep(SUBMIT_GAP_SECONDS)
        if phase == "deliver_intent":
            self.await_message(text)

    def await_message(self, text):
        session, waited = self.session()["sessionId"], 0.0
        while True:
            rollouts = self.rollouts(session)
            if len(rollouts) > 1:
                raise ValueError("uncertain delivery: several rollouts name the new thread; never replayed")
            if any(user_text(line) == text for r in rollouts for line in r.read_text().splitlines()):
                return
            if waited >= self.timeout:
                raise ValueError("uncertain delivery: the new thread never recorded the handoff; never replayed")
            self.sleep(1.0)
            waited += 1.0

    def started_sessions(self):
        """Sessions other than this thread that this plugin's SessionStart(clear) hook logged from
        under this same codex process since the helper bound. [LAW:single-enforcer] the receipt's
        owner field binds a clear to its process; another lane's receipt in the shared log names
        another owner and is not this window's boundary."""
        receipts = self.clear_receipts()
        added = receipts[len(self.receipts_at_bind):] if receipts.startswith(self.receipts_at_bind) else receipts
        owner = f" codex={self.pid}:{self.start} "
        return [line.split("session=", 1)[1].split()[0] for line in added.splitlines()
                if " event=SessionStart " in line and owner in line and " -> stopped:" not in line
                and f"session={self.thread[:8]} " not in line]

    def turn_state(self):
        """The state the newest task event left, or idle for a thread that never started a turn."""
        state = "idle"
        for line in self.rollout.read_text().splitlines():
            try:
                payload = json.loads(line).get("payload")
            except ValueError:
                continue  # a torn final line is ordinary in a rollout still being appended to
            state = TURN_STATE.get(payload.get("type"), state) if isinstance(payload, dict) else state
        return state

    def session(self):
        """The Foot helper's session record, derived from Codex's records. [LAW:one-source-of-truth]
        the identity is the newest started session, so one new receipt is the native clear
        boundary the Foot helper waits for; two make the boundary unknowable, which is refused."""
        if self.stat(self.pid)[1] != self.start:
            raise ValueError("refused: the codex process changed since the handoff was scheduled")
        started = self.started_sessions()
        if len(started) > 1:
            raise ValueError("uncertain clear: several new sessions started; nothing delivered")
        return {"pid": self.pid, "pidDomain": "codex", "sessionId": (started or [self.thread[:8]])[0],
                "status": "idle" if started else self.turn_state()}


def main(argv=None):
    try:
        CodexFootHelper(*(argv or sys.argv[1:])).handoff()
    except (ValueError, OSError, KeyError, foot.subprocess.CalledProcessError) as error:
        print(f"codex-foot-helper: {error}", file=sys.stderr)  # the upstream log captures it
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
