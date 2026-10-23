"""Session-owned delayed Foot handoff for a Codex lane: the Foot helper reading Codex's own records.

The handoff sequence, the per-script ownership and keyboard checks, the split typing and submit,
the intent before every effect and the first-input delivery rule are the Foot helper's own. Only
what Codex does natively differs: it keeps no per-process session file, so its thread is the
CODEX_THREAD_ID this helper inherits and its turn state is the newest task event in that thread's
rollout; its window may sit one launch shell above codex; its composer empties a line differently;
and its /clear starts no thread until the next input, so the new thread is known only from this
plugin's SessionStart(clear) receipt, written under this same codex once the pointer arrives.
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


def typed_text(line):
    """The text a person or composer typed, from a rollout line; None for any other or torn line,
    including the user-role context Codex injects (`content_item_kinds` other than user.text)."""
    try:
        payload = json.loads(line).get("payload")
    except ValueError:
        return None
    if (not isinstance(payload, dict) or payload.get("type") != "message" or payload.get("role") != "user"
            or (payload.get("internal_chat_message_metadata_passthrough") or {}).get("content_item_kinds") != ["user.text"]):
        return None
    return "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "input_text")


class CodexFootHelper(foot.FootHelper):
    def __init__(self, pid, msgfile, goalfile, delay, thread=None, codex_home=None, **host):
        self.thread = thread or os.environ["CODEX_THREAD_ID"]
        self.home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        super().__init__(pid, msgfile, goalfile, delay, **host)
        rollouts = self.rollouts(self.thread)
        if len(rollouts) != 1:
            raise ValueError(f"refused: {len(rollouts)} rollouts name codex thread {self.thread}")
        self.rollout = rollouts[0]
        if self.comm(self.pid) != "codex":
            raise ValueError("refused: the bound process is not codex")
        self.start = self.stat(self.pid)[1]

    def comm(self, pid):
        return (self.proc / str(pid) / "comm").read_text().strip()

    def rollouts(self, thread):
        return list((self.home / "sessions").glob(f"*/*/*/rollout-*-{thread}.jsonl"))

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

    def empty_line(self, text):
        """Ctrl-U leaves slash-command residue in Codex's composer; Ctrl-A then Ctrl-K empties the line."""
        return [("CTRL", "a"), ("CTRL", "k")]

    def carried_goal(self):
        if self.goalfile.exists() and self.goalfile.read_text():
            raise ValueError("refused: no verified Codex /goal carries a goal across the reset")
        return ""

    def await_clear(self, before, seen):
        """Codex's /clear has no boundary to observe before the pointer itself starts the new thread;
        the old thread is what that new one must differ from."""
        return self.thread

    def first_input(self, old):
        """The first typed input of the one new thread receipted under this codex."""
        started = self.started_sessions()
        if len(started) > 1:
            raise ValueError("uncertain delivery: several new sessions started; never replayed")
        if old in started:
            raise ValueError("uncertain delivery: the clear started no new thread; never replayed")
        return next((t for s in started for t in self.prompts(s)), None)

    def prompts(self, session):
        """What was typed into `session`, in order, from the one rollout of exactly that identity."""
        rollouts = self.rollouts(session)
        if len(rollouts) > 1:
            raise ValueError(f"uncertain session: several rollouts name session {session}; never replayed")
        return [t for r in rollouts for t in map(typed_text, r.read_text().splitlines()) if t is not None]

    def started_sessions(self):
        """Full identities of the sessions this plugin's SessionStart(clear) hook logged from under this
        same codex process since the helper bound. [LAW:single-enforcer] the receipt's owner field binds
        a clear to its process; another lane's receipt in the shared log names another owner and is not
        this window's boundary. The full identity, not the prefix a guardian thread can share, names it."""
        owner = f" codex={self.pid}:{self.start} "
        return self.session_starts(line for line in self.added_receipts() if owner in line)

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
        the identity is the newest started session, so a session started under this codex before the
        clear is a changed identity, which the idle wait refuses."""
        if self.stat(self.pid)[1] != self.start:
            raise ValueError("refused: the codex process changed since the handoff was scheduled")
        started = self.started_sessions()
        if len(started) > 1:
            raise ValueError("uncertain clear: several new sessions started; nothing delivered")
        return {"pid": self.pid, "pidDomain": "codex", "sessionId": (started or [self.thread])[0],
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
