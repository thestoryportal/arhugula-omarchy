"""Session-owned delayed Foot handoff: clear this same window, then type the bottle pointer.

Upstream finalize-session has already written the handoff to disk and ended the turn.
This helper waits for its own session to go idle, proves the window still belongs to
that same Claude process before every script it sends, performs each input once behind
an intent, and counts the handoff only once the cleared session records the pointer.
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
# Claude's and Codex's composers both read a long keystroke burst as a paste, so a Return inside
# it becomes a newline; a Return sent after this pause submits (cmt-80f558da). [LAW:no-ambient-temporal-coupling]
# exception: the burst window belongs to each composer and is observable only as this behavior.
SUBMIT_GAP_SECONDS = 1.0
# The shared receipt log names each session only by its 8-character prefix, which another lane's
# session can share; the full identity is the session directory of the receipt's override.
RECEIPT = re.compile(r" session=(\S+) event=SessionStart override=\S*/sessions/"
                     r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/memento\.conf ")


def typing(text):
    if not LINE.fullmatch(text):
        raise ValueError("refused: keystroke text outside the allowed set")
    return [KEYS.get(c, ("SHIFT" if c.isupper() else "", c.lower())) for c in text]


def script(address, keys):
    """One compositor script sending `keys` to the window at `address`."""
    if not re.fullmatch(r"0x[0-9a-f]+", address):
        raise ValueError("refused: window address outside the allowed set")
    events = ",".join("{" + json.dumps(m) + "," + json.dumps(k) + "}" for m, k in keys)
    return (f"for _,k in ipairs({{{events}}}) do hl.dispatch(hl.dsp.send_shortcut("
            f'{{mods=k[1],key=k[2],window="address:{address}"}})) end')


def prompt_text(line):
    """What a person submitted, from a Claude transcript line; None for any other or torn line,
    including the commands and meta records Claude writes around a clear."""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("type") != "user" or (record.get("origin") or {}).get("kind") != "human":
        return None
    content = record["message"]["content"]
    return content if isinstance(content, str) else "".join(p.get("text", "") for p in content if p.get("type") == "text")


class FootHelper:
    def __init__(self, pid, msgfile, goalfile, delay, proc=Path("/proc"),
                 sessions=Path.home() / ".claude/sessions", run=None, sleep=time.sleep,
                 timeout=300, clear_log=Path.home() / ".claude/memento/context-ceiling.log"):
        self.pid, self.msgfile, self.goalfile, self.delay = int(pid), Path(msgfile), Path(goalfile), float(delay)
        self.proc, self.sessions, self.sleep, self.timeout = Path(proc), Path(sessions), sleep, timeout
        self.projects = self.sessions.parent / "projects"  # Claude keeps transcripts beside its session files
        self.run = run or (lambda argv: subprocess.run(argv, check=True, capture_output=True, text=True).stdout)
        self.intent = self.msgfile.with_name(self.msgfile.name + ".foot-intent")
        self.clear_log = Path(clear_log)
        self.receipts_at_bind = self.clear_receipts()
        # The capability every input is checked against. A Foot address alone is not ownership:
        # a replacement Foot can reuse it, so the whole process/start/window tuple is compared.
        self.bound = self.window()

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
        """The one mapped Foot window whose terminal is this Claude process's parent. Claude's and
        Foot's start ticks join the binding, so a restarted process at a reused pid is a changed window."""
        parent, start = self.stat(self.pid)
        foot = int(parent)
        if (self.proc / str(foot) / "comm").read_text().strip() != "foot":
            raise ValueError("refused: Claude process is no longer under its foot terminal")
        clients = [c for c in json.loads(self.run(["hyprctl", "-j", "clients"])) if c.get("pid") == foot]
        if len(clients) != 1 or not clients[0].get("mapped") or not clients[0].get("acceptsInput"):
            raise ValueError("refused: foot window is missing, ambiguous or not accepting input")
        return (clients[0]["address"], clients[0]["stableId"], foot, self.stat(foot)[1], (self.pid, start))

    def keyboard(self):
        keyboards = json.loads(self.run(["hyprctl", "-j", "devices"]))["keyboards"]
        main = [k for k in keyboards if k.get("main")]
        if (len(main) != 1 or main[0].get("active_keymap") != "English (US)"
                or main[0].get("capsLock") is not False):
            raise ValueError("refused: literal input requires the US keyboard without caps lock")

    def clear_receipts(self):
        return self.clear_log.read_text() if self.clear_log.exists() else ""

    def added_receipts(self):
        """Receipt lines logged since the helper bound."""
        receipts = self.clear_receipts()
        return (receipts[len(self.receipts_at_bind):] if receipts.startswith(self.receipts_at_bind) else receipts).splitlines()

    def session_starts(self, lines):
        """Full identities of the SessionStart receipts among `lines`. [LAW:parse-dont-validate] a
        receipt whose full identity is missing or disagrees with its prefix cannot be attributed to
        any session, which is refused."""
        found = [RECEIPT.search(line) for line in lines if " event=SessionStart " in line and " -> stopped:" not in line]
        if not all(match and match[2].startswith(match[1]) for match in found):
            raise ValueError("uncertain session: a receipt names no consistent full session identity; never replayed")
        return [match[2] for match in found]

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

    def empty_line(self, text):
        """Claude's keys that empty its composer: Escape first leaves any open menu before /clear,
        and only then, because Escape while a turn runs would interrupt it."""
        return ([("", "Escape")] if text == "/clear" else []) + [("CTRL", "u")]

    def composer_input(self, address, text):
        """Two scripts: replace the composer line with `text`, then submit it on its own."""
        return [script(address, self.empty_line(text) + typing(text)), script(address, [("", "Return")])]

    def effect(self, phase, text):
        scripts = self.composer_input(self.bound[0], text)
        # [LAW:effects-at-boundaries] Leave a durable no-replay marker before input.
        with self.intent.open("w") as handle:
            handle.write(json.dumps({"phase": phase, "address": self.bound[0]}))
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

    def carried_goal(self):
        goal = self.goalfile.read_text() if self.goalfile.exists() else ""
        if goal:
            typing(f"/goal {goal}")
        return goal

    def await_clear(self, before, seen):
        """Claude's native clear boundary: a new session identity, or this plugin's SessionStart(clear)
        receipt for exactly the kept identity, never another session sharing its prefix. Returns the cleared session and how many of its prompts the
        outgoing session had already recorded. [LAW:verifiable-goals] A timestamp update alone cannot
        prove /clear."""
        waited = 0.0
        while True:
            after = self.session()
            clear_seen = after["sessionId"] in self.session_starts(
                line for line in self.added_receipts() if f" session={after['sessionId'][:8]} " in line)
            if after.get("status") == "idle" and (after["sessionId"] != before["sessionId"] or clear_seen):
                return after["sessionId"], seen.get(after["sessionId"], 0)
            if waited >= self.timeout:
                raise ValueError("uncertain clear: no native boundary observed; nothing delivered")
            self.sleep(1.0)
            waited += 1.0

    def prompts(self, session):
        """What a person submitted to `session`, in order, from the one transcript of that identity."""
        found = list(self.projects.glob(f"*/{session}.jsonl"))
        if len(found) > 1:
            raise ValueError(f"uncertain session: several transcripts name session {session}; never replayed")
        return [t for path in found for t in map(prompt_text, path.read_text().splitlines()) if t is not None]

    def first_input(self, boundary):
        """The cleared session's first prompt after those the outgoing session recorded under a kept identity."""
        session, earlier = boundary
        return next(iter(self.prompts(session)[earlier:]), None)

    def await_first_input(self, boundary, text):
        """[LAW:verifiable-goals] A compositor ack is not delivery: the handoff counts only once the
        cleared session records `text` as its FIRST input. Re-read each second, never sampled once."""
        waited = 0.0
        while True:
            first = self.first_input(boundary)
            if first == text:
                return
            if first is not None:
                raise ValueError("uncertain delivery: the cleared session's first input is not the handoff; never replayed")
            if waited >= self.timeout:
                raise ValueError("uncertain delivery: the cleared session never recorded the handoff; never replayed")
            self.sleep(1.0)
            waited += 1.0

    def handoff(self):
        if self.intent.exists():
            raise ValueError("refused: an earlier Foot effect is recorded; inspect, never replay")
        bound = self.session()
        self.keyboard()
        goal = self.carried_goal()
        self.sleep(self.delay)
        before = self.wait_idle(bound)
        if self.window() != self.bound:
            raise ValueError("refused: foot window changed before the clear")
        self.keyboard()
        pointer = f"Read and follow the handoff at {self.msgfile}"
        seen = {before["sessionId"]: len(self.prompts(before["sessionId"]))}
        self.effect("clear_intent", "/clear")
        boundary = self.await_clear(before, seen)
        self.effect("deliver_intent", pointer)
        self.await_first_input(boundary, pointer)
        if goal:
            self.effect("goal_intent", f"/goal {goal}")
        self.intent.write_text(json.dumps({"phase": "delivered", "address": self.bound[0]}))
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
