"""R6 process observation and classification; contains no scenario executor."""

import errno
import os
from pathlib import Path
import select
import subprocess
import time
from datetime import datetime, timezone

POLL_SECONDS = 0.003


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_stat(raw: str) -> dict:
    comm = raw[raw.index("(") + 1 : raw.rindex(")")]
    f = raw[raw.rindex(")") + 2 :].split()
    return {
        "comm": comm,
        "state": f[0],
        "ppid": int(f[1]),
        "pgid": int(f[2]),
        "starttime": int(f[19]),
    }


def read_proc(pid: str) -> dict:
    rec: dict = {"ts": now(), "pid": int(pid)}
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        first = parse_stat(stat_path.read_text())
        rec.update(first)
    except OSError as e:
        rec["stat_error"] = repr(e)
        rec["stat_errno"] = e.errno
        return rec
    try:
        rec["cmdline"] = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1]
        rec["cmdline"] = [c.decode("utf-8", "surrogateescape") for c in rec["cmdline"]]
    except OSError as e:
        rec["cmdline_error"] = repr(e)
    # [LAW:no-ambient-temporal-coupling] A cmdline belongs to this process only when
    # the lifetime and parent/group identity survive the bracketed stat read.
    try:
        second = parse_stat(stat_path.read_text())
        if any(first[k] != second[k] for k in ("starttime", "ppid", "pgid")):
            rec["identity_error"] = {"after": second}
    except OSError as e:
        rec["stat_after_error"] = repr(e)
    return rec


def process_key(rec: dict) -> tuple[int, int] | None:
    return (
        (rec["pid"], rec["starttime"])
        if "starttime" in rec and "identity_error" not in rec
        else None
    )


def bind_pidfd(rec: dict) -> int:
    """Pin a previously observed lifetime while it is still demonstrably live."""
    fd = os.pidfd_open(rec["pid"])
    try:
        after = read_proc(str(rec["pid"]))
        if process_key(after) != process_key(rec) or select.select([fd], [], [], 0)[0]:
            raise RuntimeError(
                f"pidfd lifetime changed or exited before binding: {rec['pid']}"
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def observe(proc: subprocess.Popen, deadline: float, root: dict) -> tuple[list, bool]:
    """Sample every /proc member of the case process group, or child of a member, until exit."""
    root_key = process_key(root)
    samples, members, member_pids = (
        [root],
        ({root_key} if root_key else set()),
        {proc.pid},
    )
    pidfds: dict[tuple[int, int], int] = {}
    attempted: set[tuple[int, int]] = set()

    def bind_member(rec: dict) -> None:
        key = process_key(rec)
        if key is None or key in attempted:
            return
        attempted.add(key)
        try:
            pidfds[key] = bind_pidfd(rec)
            rec["pidfd_bound"] = True
        except (OSError, RuntimeError) as error:
            samples.append(
                {"ts": now(), "pid": rec["pid"], "pidfd_bind_error": repr(error)}
            )

    if time.monotonic() >= deadline:
        return samples, True
    bind_member(root)
    try:
        while True:
            if time.monotonic() >= deadline:
                return samples, True
            exited = proc.poll() is not None
            snapshot = {}
            for pid in os.listdir("/proc"):
                if time.monotonic() >= deadline:
                    return samples, True
                if not pid.isdigit():
                    continue
                snapshot[int(pid)] = read_proc(pid)
            for rec in snapshot.values():
                if time.monotonic() >= deadline:
                    return samples, True
                parent = snapshot.get(rec.get("ppid"))
                if parent is not None:
                    rec["parent_key"] = process_key(parent)
                elif rec.get("ppid") in member_pids:
                    rec["parent_unresolved"] = True
                # [LAW:no-ambient-temporal-coupling] A pinned lifetime must signal exit before ENOENT is evidence.
                if rec.get("stat_errno") == errno.ENOENT and rec["pid"] in member_pids:
                    bound = [
                        (key, fd) for key, fd in pidfds.items() if key[0] == rec["pid"]
                    ]
                    if len(bound) == 1 and select.select([bound[0][1]], [], [], 0)[0]:
                        rec["terminal_key"] = list(bound[0][0])
                        rec["terminal_proof"] = "pidfd-signaled"
            pending = list(snapshot.values())
            while pending:
                if time.monotonic() >= deadline:
                    return samples, True
                before = len(pending)
                kept = []
                for rec in pending:
                    key = process_key(rec)
                    if (
                        key in members
                        or rec.get("pgid") == proc.pid
                        or rec.get("parent_key") in members
                        or rec["pid"] in member_pids
                    ):
                        samples.append(rec)
                        member_pids.add(rec["pid"])
                        if key is not None:
                            members.add(key)
                            bind_member(rec)
                    else:
                        kept.append(rec)
                if len(kept) == before:
                    break
                pending = kept
            if exited:
                return samples, time.monotonic() >= deadline
            time.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    finally:
        for fd in pidfds.values():
            os.close(fd)


def classify(
    samples: list,
    root_key: tuple[int, int] | None,
    argv: list,
    candidate_root: str,
    own_cmd: list,
) -> dict:
    """Identity per (pid, starttime) from its last non-empty cmdline; anything unproven is unknown."""
    allowed_git = [
        ["git", "-C", candidate_root, "rev-parse", "HEAD"],
        ["git", "-C", candidate_root, "status", "--porcelain"],
    ]
    timeout_argv = ["timeout", "-k", "5", "30", *argv]
    by_key: dict = {}
    for r in samples:
        if "starttime" in r:
            by_key.setdefault((r["pid"], r["starttime"]), []).append(r)
    members, unknown = {}, []
    # [LAW:no-ambient-temporal-coupling] Resolve the parent graph before presenting members.
    roles = {}

    def role_for(key, visiting=frozenset()):
        if key in roles:
            return roles[key]
        if key in visiting or key not in by_key:
            return None
        recs = by_key[key]
        cmds = [r["cmdline"] for r in recs if r.get("cmdline")]
        final = cmds[-1] if cmds else None
        parents = {tuple(r["parent_key"]) for r in recs if r.get("parent_key")}
        parent_role = (
            role_for(next(iter(parents)), visiting | {key})
            if len(parents) == 1
            else None
        )
        if key == root_key and final == timeout_argv:
            role = "timeout"
        elif parent_role == "timeout" and final == argv:
            role = "witness-parent"
        elif parent_role == "witness-parent" and final in allowed_git:
            role = "git:" + final[3]
        else:
            role = None
        roles[key] = role
        return role

    for (pid, st), recs in sorted(by_key.items(), key=lambda kv: kv[0][1]):
        cmds = [r["cmdline"] for r in recs if r.get("cmdline")]
        ppid = recs[0]["ppid"]
        final = cmds[-1] if cmds else None
        parent_keys = {tuple(r["parent_key"]) for r in recs if r.get("parent_key")}
        parent_role = (
            role_for(next(iter(parent_keys))) if len(parent_keys) == 1 else None
        )
        role = role_for((pid, st))
        # pre-exec clone samples carry the parent's argv; any other cmdline is unexplained
        parent_cmd = (
            own_cmd
            if (pid, st) == root_key
            else {"timeout": timeout_argv, "witness-parent": argv}.get(parent_role)
        )
        stray = [c for c in cmds if c != final and c != parent_cmd]
        entry = {
            "pid": pid,
            "starttime": st,
            "ppid": ppid,
            "role": role,
            "samples": len(recs),
            "states": sorted({r["state"] for r in recs}),
            "comms": sorted({r["comm"] for r in recs}),
            "empty_cmdline_samples": sum(1 for r in recs if not r.get("cmdline")),
            "cmdlines": [list(x) for x in dict.fromkeys(tuple(c) for c in cmds)],
        }
        members[f"{pid}:{st}"] = entry
        if (
            role is None
            or stray
            or len(parent_keys) > 1
            or any(r.get("parent_unresolved") for r in recs)
        ):
            unknown.append(f"{pid}:{st}")
    if root_key is None or f"{root_key[0]}:{root_key[1]}" not in members:
        unknown.append("timeout-unobserved")
    errors = [
        r
        for r in samples
        if any(
            k in r
            for k in (
                "stat_error",
                "cmdline_error",
                "stat_after_error",
                "identity_error",
                "pidfd_bind_error",
            )
        )
    ]
    # [LAW:no-silent-failure] Only a pinned, signaled lifetime discharges its own missing-stat race.
    terminal = [
        r
        for r in errors
        if "stat_error" in r
        and r.get("stat_errno") == errno.ENOENT
        and r.get("terminal_proof") == "pidfd-signaled"
        and tuple(r.get("terminal_key", ())) in by_key
        and r["terminal_key"][0] == r["pid"]
        and not any(
            k in r
            for k in (
                "cmdline_error",
                "stat_after_error",
                "identity_error",
                "pidfd_bind_error",
            )
        )
        and len([key for key in by_key if key[0] == r["pid"]]) == 1
    ]
    blocking = [r for r in errors if r not in terminal]
    return {
        "members": members,
        "unknown": unknown,
        "read_errors": errors,
        "blocking_read_errors": blocking,
        "terminal_disappearances": terminal,
        "limits": "polling observer; processes shorter than one poll may be unseen; no kernel trace",
    }
