"""Bind native clear and exact-thread queue delivery to one existing TUI lane."""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import re
import select
import sqlite3
import uuid
from datetime import datetime, timezone

from .artifacts import capture, DEFAULT_ROOT, file_binding
from .processes import process_stats


class QueueRefused(ValueError):
    """The effect boundary refused before invoking the queue transport."""


def clear_program(address, title):
    if not re.fullmatch(r"0x[0-9a-f]+", address):
        raise ValueError("invalid window address")
    if (
        not re.fullmatch(r"Buford-auto-[0-9a-f-]{36}", title)
        or uuid.UUID(title[12:]).version != 4
    ):
        raise ValueError("native clear requires the generated nonce title")
    text = "/clear " + title
    keys = [{" ": "space", "/": "slash", "-": "minus"}.get(c, c.lower()) for c in text]
    modifiers = ["SHIFT" if c.isupper() else "" for c in text]
    # [LAW:polishing-by-subtraction] The keyboard seam handles only native clear;
    # continuation text belongs to the exact-thread queue, never a key encoder.
    events = (
        "{"
        + ",".join(
            "{" + json.dumps(m) + "," + json.dumps(k) + "}"
            for m, k in zip(modifiers, keys)
        )
        + "}"
    )
    return (
        f"for _,k in ipairs({events}) do hl.dispatch(hl.dsp.send_shortcut("
        f'{{mods=k[1],key=k[2],window="address:{address}"}})) end '
        f'print("BUFORD_NATIVE_CLEAR {len(keys)}")'
    )


def require_us_keyboard(rows):
    main = [r for r in rows if r.get("main")]
    if (
        len(main) != 1
        or main[0].get("active_keymap") != "English (US)"
        or main[0].get("capsLock") is not False
    ):
        raise ValueError(
            "literal native delivery requires the verified US keyboard without caps lock"
        )


def processes():
    return {proc.pid: (proc.start, proc.parent) for proc in process_stats()}


def boot_facts(proc=Path("/proc")):
    stat = (Path(proc) / "stat").read_text().splitlines()
    return {
        "boot_id": (Path(proc) / "sys/kernel/random/boot_id").read_text().strip(),
        "btime": next(int(line.split()[1]) for line in stat if line.startswith("btime ")),
    }


@dataclass(frozen=True)
class LockHolder:
    pid: int
    fd: str
    name: str
    device: int
    inode: int


def _scan(proc):
    """Map every held FLOCK to a named fd of its holder, reading only holder fd tables."""
    entries = set()
    for line in (Path(proc) / "locks").read_text().splitlines():
        fields = line.split()
        # Blocked waiters print "->" and hold nothing.
        if len(fields) < 6 or fields[1] != "FLOCK":
            continue
        major, minor, inode = fields[5].split(":")
        entries.add((int(fields[4]), os.makedev(int(major, 16), int(minor, 16)), int(inode)))
    holders = []
    for pid in sorted({entry[0] for entry in entries}):
        directory = Path(proc) / str(pid) / "fd"
        try:
            names = os.listdir(directory)
        except PermissionError as error:
            raise ValueError("lock holder fd table is not readable") from error
        except FileNotFoundError:
            names = []
        for fd in names:
            link = directory / fd
            try:
                name, info = os.readlink(link), os.stat(link)
            except PermissionError as error:
                raise ValueError("lock holder fd is not readable") from error
            except FileNotFoundError:
                # An fd that closed during the scan holds nothing; coverage still decides.
                continue
            holders.append(LockHolder(pid, fd, name, info.st_dev, info.st_ino))
    mapped = set()
    for pid, device, inode in entries:
        match = {h for h in holders if (h.pid, h.device, h.inode) == (pid, device, inode)}
        if not match:
            raise ValueError("held lock does not map to a holder fd")
        mapped |= match
    return sorted(mapped, key=lambda h: (h.pid, int(h.fd))), holders


def lock_table(proc=Path("/proc")):
    return _scan(proc)[0]


def _last_record_time(rollout):
    stamps = [
        json.loads(line).get("timestamp")
        for line in Path(rollout).read_text().splitlines()
        if line.strip()
    ]
    stamps = [s for s in stamps if s]
    if not stamps:
        raise ValueError("predecessor rollout has no timestamped record")
    return datetime.fromisoformat(stamps[-1].replace("Z", "+00:00")).timestamp()


def seal_predecessor(session, rollout, codex_home, proc=Path("/proc")):
    """Seal an inherited predecessor at prepare; it must already pass the rule."""
    info = os.stat(rollout)
    seal = {
        "session": str(uuid.UUID(session)),
        "rollout": str(rollout),
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "last_record": _last_record_time(rollout),
        **boot_facts(proc),
    }
    predecessor_absent(seal, codex_home, proc)
    return seal


def predecessor_absent(seal, codex_home, proc=Path("/proc")):
    """Prove a routed predecessor that differs from the outgoing lane has no owner.

    No process survives a reboot, so a predecessor whose last activity precedes this
    boot cannot be alive; its old pid is never looked up. Path absence is never
    evidence: the lock table and the sealed rollout inode decide.
    """
    if boot_facts(proc) != {"boot_id": seal["boot_id"], "btime": seal["btime"]}:
        raise ValueError("boot changed since the predecessor was sealed")
    try:
        info = os.stat(seal["rollout"])
    except FileNotFoundError as error:
        raise ValueError("sealed predecessor rollout is gone") from error
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
        seal["device"], seal["inode"], seal["size"], seal["mtime_ns"]
    ):
        raise ValueError("predecessor rollout changed since it was sealed")
    if info.st_mtime_ns / 1e9 >= seal["btime"] or seal["last_record"] >= seal["btime"]:
        raise ValueError("predecessor was active in the current boot")
    lock = str(Path(codex_home) / "thread-writer-locks" / (seal["session"] + ".lock"))
    _, holders = _scan(proc)
    for holder in holders:
        if holder.name in (lock, lock + " (deleted)") or (holder.device, holder.inode) == (
            seal["device"], seal["inode"]
        ):
            raise ValueError("predecessor lock or rollout is still held")
    return True


def launch_cwd(argv, process_cwd):
    directories = []
    for index, arg in enumerate(argv):
        if arg in ("-C", "--cd"):
            if index + 1 == len(argv):
                raise ValueError("native launch directory is missing")
            directories.append(argv[index + 1])
        elif arg.startswith("--cd="):
            directories.append(arg[5:])
    if len(directories) > 1:
        raise ValueError("ambiguous native launch directory")
    return (Path(process_cwd) / (directories[0] if directories else ".")).resolve()


@dataclass(frozen=True)
class WindowCapability:
    address: str
    stable_id: str
    terminal_pid: int
    terminal_start: str
    native_pid: int
    native_start: str

    def parse(self, clients, proc):
        # [LAW:parse-dont-validate] Return a bound capability; refuse reused handles.
        matching = [c for c in clients if c["address"] == self.address]
        if (
            len(matching) != 1
            or matching[0]["stableId"] != self.stable_id
            or matching[0]["pid"] != self.terminal_pid
            or not matching[0].get("mapped")
            or not matching[0].get("acceptsInput")
            or proc.get(self.terminal_pid, (None,))[0] != self.terminal_start
            or proc.get(self.native_pid, (None,))[0] != self.native_start
        ):
            raise ValueError("native window/process capability changed")
        parent = self.native_pid
        seen = set()
        while parent != self.terminal_pid and parent not in seen and parent in proc:
            seen.add(parent)
            parent = proc[parent][1]
        if parent != self.terminal_pid:
            raise ValueError("native client left its bound terminal")
        return self


@dataclass(frozen=True)
class RetainedContext:
    """Explicit proof for one expired maintenance boundary, never prompt delivery."""

    session_id: str
    created_at: str
    process_uuid: str
    creation_log_id: int
    transcript: str
    user_input: bool

    @classmethod
    def parse(cls, grant, cap, cwd, frontier, previous):
        try:
            return cls._parse(grant, cap, cwd, frontier, previous)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("malformed retained native context evidence") from error

    @classmethod
    def _parse(cls, grant, cap, cwd, frontier, previous):
        # [LAW:parse-dont-validate] Bind the retained observation once; current
        # ownership is a separate capability, not a substitute creation event.
        evidence = {}
        for key in ("receipt", "config", "frontier"):
            bound = grant[key]
            if file_binding(bound["path"]) != bound:
                raise ValueError("retained native context evidence changed")
            evidence[key] = json.loads(Path(bound["path"]).read_text())
        receipt = evidence["receipt"]
        if (
            receipt["exit"] != 0
            or receipt["terminal"] != "exited"
            or receipt["cwd"] != str(cwd)
            or evidence["config"]["window"] != asdict(cap)
            or evidence["frontier"] != frontier
            or file_binding(receipt["stdout"]["path"]) != receipt["stdout"]
        ):
            raise ValueError("retained native context witness binding mismatch")
        proof = json.loads(Path(receipt["stdout"]["path"]).read_text())
        identifier = uuid.UUID(proof["session_id"])
        created = (identifier.int >> 80) / 1000
        if (
            identifier.version != 7
            or proof["session_id"] == previous
            or proof["user_input"] is not True
            or created < datetime.fromisoformat(frontier["prepared_at"]).timestamp()
            or proof["created_at"]
            != datetime.fromtimestamp(created, timezone.utc).isoformat()
            or not re.fullmatch(
                f"pid:{cap.native_pid}:[a-zA-Z0-9-]+", proof["process_uuid"]
            )
            or type(proof["creation_log_id"]) is not int
            or proof["creation_log_id"] <= 0
            or not Path(proof["transcript"]).is_absolute()
        ):
            raise ValueError("retained native creation proof mismatch")
        # [LAW:carrying-cost] The explicit grant attests the independently checked
        # observation; incidental diagnostic source is not a durable protocol.
        return cls(**proof)


class NativeWindow:
    def __init__(self, capability, cwd, artifact_root=DEFAULT_ROOT, *, codex_home=None):
        self.cap = capability
        self.cwd = Path(cwd)
        self.root = artifact_root
        self.home = (
            Path(codex_home).absolute()
            if codex_home is not None
            else Path.home() / ".codex"
        )
        self.proc = Path("/proc") / str(capability.native_pid)

    def command(self, argv):
        receipt = capture(argv, self.cwd, root=self.root, timeout=15)
        if receipt["terminal"] != "exited" or receipt["exit"]:
            raise OSError(f"native window command failed: {receipt['receipt']}")
        return Path(receipt["stdout"]["path"]).read_text()

    def check(self):
        clients = json.loads(self.command(["hyprctl", "-j", "clients"]))
        self.cap.parse(clients, processes())
        require_us_keyboard(
            json.loads(self.command(["hyprctl", "-j", "devices"]))["keyboards"]
        )
        return next(c for c in clients if c["address"] == self.cap.address)

    def title(self):
        return self.check()["title"]

    def transcripts(self):
        paths = []
        for path in self.rollouts():
            with path.open() as stream:
                try:
                    row = json.loads(next(stream))
                except StopIteration:
                    continue
            if (
                row.get("type") == "session_meta"
                and row["payload"].get("source") == "cli"
            ):
                paths.append(path)
        return paths

    def rollouts(self):
        self.check()
        paths = set()
        for fd in (self.proc / "fd").iterdir():
            try:
                path = fd.resolve(strict=True)
            except FileNotFoundError:
                continue
            if not path.name.startswith("rollout-") or path.suffix != ".jsonl":
                continue
            paths.add(path)
        return sorted(paths)

    def owned_threads(self, frontier):
        self.check()
        argv = (self.proc / "cmdline").read_bytes().decode().rstrip("\0").split("\0")
        if (
            frontier["native_lane"]
            != {"cwd": str(self.cwd), "source": "cli", "originator": "codex-tui"}
            or launch_cwd(argv, (self.proc / "cwd").resolve(strict=True))
            != self.cwd.resolve()
        ):
            raise ValueError("native CLI lane provenance changed")
        owned = set()
        for fd in (self.proc / "fd").iterdir():
            try:
                path = fd.resolve(strict=True)
            except FileNotFoundError:
                continue
            if (
                path.parent != self.home / "thread-writer-locks"
                or path.suffix != ".lock"
            ):
                continue
            info = (self.proc / "fdinfo" / fd.name).read_text()
            if not re.search(
                r"lock:\s+\d+: FLOCK\s+ADVISORY\s+WRITE "
                + str(self.cap.native_pid)
                + r" ",
                info,
            ):
                raise ValueError("native thread writer ownership is unproven")
            owned.add(str(uuid.UUID(path.stem)))
        return owned

    def outgoing(self, frontier):
        """The thread whose writer lock this native process holds, joined to its rollout."""
        owned = self.owned_threads(frontier)
        joined = {}
        for path in self.rollouts():
            with path.open() as stream:
                try:
                    row = json.loads(next(stream))
                except StopIteration:
                    continue
            if row.get("type") == "session_meta":
                joined.setdefault(row["payload"]["id"], []).append((path, row["payload"]))
        lanes, children = [], []
        for thread in owned:
            rows = joined.get(thread, [])
            if len(rows) != 1:
                raise ValueError("thread writer lock is not joined to one open rollout")
            path, meta = rows[0]
            (children if "parent_thread_id" in meta else lanes).append((thread, path, meta))
        if len(lanes) != 1 or any(
            m.get("source") == "cli" and t != lanes[0][0]
            for t, rows in joined.items()
            for _, m in rows
        ):
            raise ValueError("outgoing native CLI lane is not unique")
        thread, path, meta = lanes[0]
        if {k: meta.get(k) for k in ("cwd", "source", "originator")} != frontier["native_lane"]:
            raise ValueError("outgoing native rollout provenance changed")
        for _, _, child in children:
            if not (
                isinstance(child.get("source"), dict)
                and "subagent" in child["source"]
                and child["parent_thread_id"] == thread
            ):
                raise ValueError("extra writer lock is not a subagent of the outgoing lane")
        info = os.stat(path)
        return {"thread": thread, "rollout": str(path), "device": info.st_dev, "inode": info.st_ino}

    def log_mark(self):
        with sqlite3.connect(
            (self.home / "logs_2.sqlite").as_uri() + "?mode=ro", uri=True
        ) as db:
            return db.execute("SELECT COALESCE(MAX(id), 0) FROM logs").fetchone()[0]

    def recovery_context(self, frontier, previous, grant):
        if grant is None:
            return self.context(frontier, previous)
        retained = RetainedContext.parse(grant, self.cap, self.cwd, frontier, previous)
        proof = asdict(retained)
        current = self.context(frontier, previous)
        if current is not None and any(
            current[key] != proof[key]
            for key in (
                "session_id",
                "created_at",
                "process_uuid",
                "creation_log_id",
                "transcript",
            )
        ):
            raise ValueError("current native creation contradicts retained witness")
        owned = self.owned_threads(frontier)
        if proof["session_id"] not in owned:
            raise ValueError("retained native writer lock is no longer held")
        with sqlite3.connect(
            (self.home / "logs_2.sqlite").as_uri() + "?mode=ro", uri=True
        ) as db:
            processes = {
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT process_uuid FROM logs WHERE thread_id=? AND process_uuid LIKE ?",
                    (proof["session_id"], f"pid:{self.cap.native_pid}:%"),
                )
            }
            if processes != {proof["process_uuid"]}:
                raise ValueError(
                    "current native process provenance differs from retained witness"
                )
        paths = [
            str(p)
            for p in self.rollouts()
            if p.name.endswith("-" + proof["session_id"] + ".jsonl")
        ]
        if paths != [proof["transcript"]]:
            raise ValueError("retained native rollout is no longer exclusively owned")
        with Path(proof["transcript"]).open() as stream:
            try:
                row = json.loads(next(stream))
            except StopIteration as error:
                raise ValueError("retained native rollout is empty") from error
        if (
            row.get("type") != "session_meta"
            or row["payload"].get("id") != proof["session_id"]
            or {k: row["payload"].get(k) for k in ("cwd", "source", "originator")}
            != frontier["native_lane"]
        ):
            raise ValueError("retained native rollout provenance changed")
        self.check()
        return {**proof, "retained_context": grant}

    def context(self, frontier, previous):
        """Prove native TUI thread creation even before lazy rollout persistence."""
        owned = self.owned_threads(frontier)
        prepared = datetime.fromisoformat(frontier["prepared_at"]).timestamp()
        mark = frontier.get("log_mark")
        excluded = {previous, *frontier.get("excluded_sessions", ())}
        # [LAW:parse-dont-validate] A held native writer lock plus the native TUI
        # thread/start event proves creation; title alone never authorizes input.
        with sqlite3.connect(
            (self.home / "logs_2.sqlite").as_uri() + "?mode=ro", uri=True
        ) as db:
            # A sealed high-water mark binds the proof to rows written after prepare;
            # a wall-clock floor cannot separate a same-second pid reuse.
            rows = db.execute(
                "SELECT id,ts,ts_nanos,thread_id,process_uuid,feedback_log_body FROM logs "
                "WHERE target='codex_core::shell_snapshot' AND "
                + ("id>?" if mark is not None else "ts>=?")
                + " AND process_uuid LIKE ?",
                (mark if mark is not None else int(prepared), f"pid:{self.cap.native_pid}:%"),
            ).fetchall()
            if mark is not None and len({row[4] for row in rows}) > 1:
                raise ValueError("mixed native process identities after the sealed mark")
            candidates = []
            for log_id, ts, nanos, session, process, body in rows:
                if mark is None and (session not in owned or session == previous):
                    continue
                if not all(
                    token in body
                    for token in (
                        'rpc.method="thread/start"',
                        'rpc.transport="in-process"',
                        'app_server.client_name="codex-tui"',
                        "app_server.thread_start.create_thread",
                        f"shell_snapshot{{thread_id={session}}}",
                        "Shell snapshot successfully created:",
                    )
                ):
                    continue
                if session in excluded:
                    raise ValueError("fresh context reuses an outgoing, inherited or routed UUID")
                if session not in owned:
                    raise ValueError("fresh thread writer lock is not held by the native process")
                identifier = uuid.UUID(session)
                created = (identifier.int >> 80) / 1000
                if (
                    identifier.version != 7
                    or created < prepared
                    or ts + nanos / 1e9 < created
                ):
                    raise ValueError(
                        "old or malformed native context creation evidence"
                    )
                candidates.append(
                    dict(
                        session_id=session,
                        created_at=datetime.fromtimestamp(
                            created, timezone.utc
                        ).isoformat(),
                        process_uuid=process,
                        creation_log_id=log_id,
                        transcript=None,
                        user_input=False,
                    )
                )
            if len(candidates) > 1:
                raise ValueError("ambiguous fresh native CLI context")
            if not candidates:
                return None
            proof = candidates[0]
            proof["user_input"] = bool(
                db.execute(
                    "SELECT 1 FROM logs WHERE process_uuid=? AND thread_id=? "
                    "AND id>? AND (feedback_log_body LIKE '%op: TurnInput %' OR feedback_log_body LIKE '%codex.op=\"turn_input\"%') LIMIT 1",
                    (
                        proof["process_uuid"],
                        proof["session_id"],
                        proof["creation_log_id"],
                    ),
                ).fetchone()
            )
        # A real owned empty file is optional evidence, never a prerequisite.
        paths = [
            p
            for p in self.rollouts()
            if p.name.endswith("-" + proof["session_id"] + ".jsonl")
        ]
        if len(paths) > 1:
            raise ValueError("ambiguous fresh native rollout")
        if paths:
            with paths[0].open() as stream:
                try:
                    row = json.loads(next(stream))
                except StopIteration:
                    row = None
            if row is not None and (
                row.get("type") != "session_meta"
                or row["payload"].get("id") != proof["session_id"]
                or {k: row["payload"].get(k) for k in ("cwd", "source", "originator")}
                != frontier["native_lane"]
            ):
                raise ValueError("malformed or foreign native rollout")
            proof["transcript"] = str(paths[0])
        self.check()
        return proof

    def delivered_context(self, frontier, previous, initial):
        # [LAW:single-enforcer] Bootstrap and receipt publication resample the
        # same bound native creation; a queue acknowledgement is not this proof.
        current = self.context(frontier, previous)
        if current is None or any(
            current[k] != initial[k]
            for k in ("session_id", "created_at", "process_uuid", "creation_log_id")
        ):
            raise ValueError("fresh native context changed after prompt delivery")
        # [LAW:one-source-of-truth] TurnInput is asynchronous corroboration;
        # delivery readiness belongs to the owned rollout's sealed sole prompt.
        return current

    def queue(self, context, frontier, previous, text):
        # [LAW:single-enforcer] Reuse native ownership/provenance at the effect
        # boundary; an enqueue acknowledgement never proves actual user delivery.
        # [LAW:types-are-the-program] Only this pre-dispatch arm proves zero effect;
        # every failure after command invocation remains uncertain and unreplayable.
        try:
            current = self.context(frontier, previous)
            if current != context or current["user_input"]:
                raise ValueError(
                    "native queue target context changed or already has input"
                )
            session = str(uuid.UUID(context["session_id"]))
        except (ValueError, OSError) as error:
            raise QueueRefused(str(error)) from error
        return self._queued(session, text)

    def instruct(self, frontier, thread, text):
        """Queue one ceiling instruction to the proven outgoing lane thread only."""
        try:
            if self.outgoing(frontier)["thread"] != thread:
                raise ValueError("ceiling instruction target is not the outgoing lane")
        except (ValueError, OSError) as error:
            raise QueueRefused(str(error)) from error
        return self._queued(thread, text)

    def _queued(self, session, text):
        answer = self.command(
            ["codex", "queue", "--thread", session, "--message", text]
        )
        match = re.fullmatch(
            r"Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\n?", answer
        )
        if match is None or match[2] != session:
            raise ValueError(
                "native queue acknowledgement target mismatch; do not replay"
            )
        message = uuid.UUID(match[1])
        if message.version != 7:
            raise ValueError("invalid native queue message identity; do not replay")
        return {"message_id": str(message), "session_id": session}

    def clear(self, title):
        program = clear_program(self.cap.address, title)
        self.check()
        if self.command(["hyprctl", "eval", program]).strip() != "ok":
            raise OSError("native clear input was not acknowledged")
        # Only the slash command uses composer submission. Continuation delivery
        # is exclusively queued after the new UUID/empty native context is proven.
        select.select([], [], [], 0.8)
        self.check()
        program = (
            "hl.dispatch(hl.dsp.send_shortcut("
            f'{{mods="",key="Tab",window="address:{self.cap.address}"}}))'
        )
        if self.command(["hyprctl", "eval", program]).strip() != "ok":
            raise OSError("native clear submit was not acknowledged")
