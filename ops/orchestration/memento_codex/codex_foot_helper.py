"""Session-owned delayed Foot handoff for a Codex lane: the Foot helper reading Codex's own records.

Codex keeps no per-process session file. Its thread is the CODEX_THREAD_ID this helper inherits
from the launcher, its turn state is the newest task event in that thread's rollout, and its clear
is proven only by this plugin's SessionStart(clear) receipt for a new thread, written by a hook
running under this same codex process. Everything else - the window binding, keyboard check,
intent markers and keystrokes - is the Foot helper's own.
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


class CodexFootHelper(foot.FootHelper):
    def __init__(self, pid, msgfile, goalfile, delay, thread=None, codex_home=None, **host):
        super().__init__(pid, msgfile, goalfile, delay, **host)
        self.thread = thread or os.environ["CODEX_THREAD_ID"]
        home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        rollouts = list((home / "sessions").glob(f"*/*/*/rollout-*-{self.thread}.jsonl"))
        if len(rollouts) != 1:
            raise ValueError(f"refused: {len(rollouts)} rollouts name codex thread {self.thread}")
        self.rollout = rollouts[0]
        if (self.proc / str(self.pid) / "comm").read_text().strip() != "codex":
            raise ValueError("refused: the bound process is not codex")
        self.start = self.stat(self.pid)[1]
        self.receipts_at_bind = self.clear_receipts()

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
