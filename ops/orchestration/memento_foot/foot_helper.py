"""Session-owned delayed Foot handoff: clear this same window, then type the bottle pointer.

Upstream finalize-session has already written the handoff to disk and ended the turn.
This helper waits for its own session to go idle, proves the window still belongs to
that same Claude process, and performs each keystroke effect once, behind an intent.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

LINE = re.compile(r"[\x20-\x7e]{1,4096}")
KEYS = {" ": ("", "space"), "/": ("", "slash"), "-": ("", "minus"), "_": ("SHIFT", "minus"),
        ".": ("", "period"), ":": ("SHIFT", "semicolon"), "=": ("", "equal"), "+": ("SHIFT", "equal")}
KEYS.update({c: ("SHIFT", k) for c, k in zip('!@#$%^&*()', '1234567890')})
KEYS.update({";": ("", "semicolon"), "'": ("", "apostrophe"), '"': ("SHIFT", "apostrophe"),
             ",": ("", "comma"), "<": ("SHIFT", "comma"), ">": ("SHIFT", "period"),
             "?": ("SHIFT", "slash"), "`": ("", "grave"), "~": ("SHIFT", "grave"),
             "[": ("", "bracketleft"), "]": ("", "bracketright"), "{": ("SHIFT", "bracketleft"),
             "}": ("SHIFT", "bracketright"), "\\": ("", "backslash"), "|": ("SHIFT", "backslash")})


def keystrokes(address, text):
    if not re.fullmatch(r"0x[0-9a-f]+", address) or not LINE.fullmatch(text):
        raise ValueError("refused: keystroke text or window address outside the allowed set")
    # [LAW:single-enforcer] Every input starts with an empty composer, as upstream does.
    prefix = [("", "Escape")] if text == "/clear" else []
    keys = prefix + [("CTRL", "u")] + [KEYS.get(c, ("SHIFT" if c.isupper() else "", c.lower())) for c in text] + [("", "Return")]
    events = ",".join("{" + json.dumps(m) + "," + json.dumps(k) + "}" for m, k in keys)
    return (f"for _,k in ipairs({{{events}}}) do hl.dispatch(hl.dsp.send_shortcut("
            f'{{mods=k[1],key=k[2],window="address:{address}"}})) end')


class FootHelper:
    def __init__(self, pid, msgfile, goalfile, delay, proc=Path("/proc"),
                 sessions=Path.home() / ".claude/sessions", run=None, sleep=time.sleep,
                 timeout=300, clear_log=Path.home() / ".claude/memento/context-ceiling.log"):
        self.pid, self.msgfile, self.goalfile, self.delay = int(pid), Path(msgfile), Path(goalfile), float(delay)
        self.proc, self.sessions, self.sleep, self.timeout = Path(proc), Path(sessions), sleep, timeout
        self.run = run or (lambda argv: subprocess.run(argv, check=True, capture_output=True, text=True).stdout)
        self.intent = self.msgfile.with_name(self.msgfile.name + ".foot-intent")
        self.clear_log = Path(clear_log)

    def stat(self, pid):
        text = (self.proc / str(pid) / "stat").read_text()
        fields = text[text.rfind(")") + 2:].split()
        return fields[1], fields[19]  # parent pid, start ticks

    def session(self):
        record = json.loads((self.sessions / f"{self.pid}.json").read_text())
        if record.get("pid") != self.pid or record.get("procStart") != self.stat(self.pid)[1]:
            raise ValueError("refused: session file no longer describes this Claude process")
        return record

    def window(self):
        """The one mapped Foot window whose terminal is this Claude process's parent."""
        foot = int(self.stat(self.pid)[0])
        if (self.proc / str(foot) / "comm").read_text().strip() != "foot":
            raise ValueError("refused: Claude process is no longer under its foot terminal")
        clients = [c for c in json.loads(self.run(["hyprctl", "-j", "clients"])) if c.get("pid") == foot]
        if len(clients) != 1 or not clients[0].get("mapped") or not clients[0].get("acceptsInput"):
            raise ValueError("refused: foot window is missing, ambiguous or not accepting input")
        return (clients[0]["address"], clients[0]["stableId"], foot, self.stat(foot)[1])

    def keyboard(self):
        keyboards = json.loads(self.run(["hyprctl", "-j", "devices"]))["keyboards"]
        main = [k for k in keyboards if k.get("main")]
        if (len(main) != 1 or main[0].get("active_keymap") != "English (US)"
                or main[0].get("capsLock") is not False):
            raise ValueError("refused: literal input requires the US keyboard without caps lock")

    def clear_receipts(self):
        return self.clear_log.read_text() if self.clear_log.exists() else ""

    def wait_idle(self, bound):
        waited = 0.0
        while True:
            record = self.session()
            if record["sessionId"] != bound["sessionId"] or record["pidDomain"] != bound["pidDomain"]:
                raise ValueError("refused: session identity changed before the handoff")
            if record.get("status") == "idle":
                return record
            if waited >= self.timeout:
                raise ValueError("refused: session never went idle; nothing typed")
            self.sleep(1.0)
            waited += 1.0

    def effect(self, phase, address, text):
        # [LAW:effects-at-boundaries] Leave a durable no-replay marker before input.
        with self.intent.open("w") as handle:
            handle.write(json.dumps({"phase": phase, "address": address}))
            handle.flush()
            os.fsync(handle.fileno())
        if self.run(["hyprctl", "eval", keystrokes(address, text)]).strip() != "ok":
            raise ValueError(f"uncertain {phase}: compositor did not acknowledge; never replayed")

    def handoff(self):
        if self.intent.exists():
            raise ValueError("refused: an earlier Foot effect is recorded; inspect, never replay")
        bound = self.session()
        window = self.window()
        self.keyboard()
        goal = self.goalfile.read_text() if self.goalfile.exists() else ""
        if goal:
            keystrokes(window[0], f"/goal {goal}")
        clear_before = self.clear_receipts()
        self.sleep(self.delay)
        before = self.wait_idle(bound)
        if self.window() != window:
            raise ValueError("refused: foot window changed before the clear")
        self.keyboard()
        address = window[0]
        self.effect("clear_intent", address, "/clear")
        after, waited = self.session(), 0.0
        # [LAW:verifiable-goals] A timestamp update alone cannot prove /clear.
        # Accept native identity change or this plugin's SessionStart(clear) receipt.
        while True:
            receipts = self.clear_receipts()
            added = receipts[len(clear_before):] if receipts.startswith(clear_before) else receipts
            clear_seen = any(f"session={after['sessionId'][:8]} event=SessionStart " in line
                             and " -> stopped:" not in line for line in added.splitlines())
            if after.get("status") == "idle" and (after["sessionId"] != before["sessionId"] or clear_seen):
                break
            if waited >= self.timeout:
                raise ValueError("uncertain clear: no native boundary observed; nothing delivered")
            self.sleep(1.0)
            waited += 1.0
            after = self.session()
        if self.window() != window:
            raise ValueError("refused: foot window changed across the clear")
        self.keyboard()
        self.effect("deliver_intent", address, f"Read and follow the handoff at {self.msgfile}")
        if goal:
            self.effect("goal_intent", address, f"/goal {goal}")
        self.intent.write_text(json.dumps({"phase": "delivered", "address": address}))
        self.goalfile.unlink(missing_ok=True)


def main(argv=None):
    try:
        FootHelper(*(argv or sys.argv[1:])).handoff()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"foot-helper: {error}", file=sys.stderr)  # the upstream log captures it
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
