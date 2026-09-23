"""Inspect local Codex/Claude session metadata and admit bounded work.

Transcript content is parsed locally but never included in returned data. The
operational ceiling is always supplied by the caller, not inferred from usage or
compaction metadata.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from typing import Any
from uuid import UUID


def _fresh(kind: str) -> dict[str, Any]:
    if kind not in {"codex", "claude"}:
        raise ValueError("kind must be codex or claude")
    return {
        "kind": kind,
        "session_id": None,
        "identity_conflict": False,
        "model": None,
        "last_activity": None,
        "status": "unknown",
        "latest_request_input_tokens": None,
        "cached_input_tokens": None,
        "reported_context_window_tokens": None,
        "metric_error": None,
        "compactions": [],
        "completion_times": [],
        "completion_count": 0,
        "observed_responses": 0,
        "partial_tail": False,
        "_seen_response_hashes": [],
        "_completed_response_hashes": [],
        "_last_response_hash": None,
        "_active_turn_id": None,
        "_last_codex_compaction": False,
    }


def _nonnegative(value: Any) -> bool:
    return type(value) is int and value >= 0


def _identity(state: dict[str, Any], value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    if state["session_id"] is None:
        state["session_id"] = value
    elif state["session_id"] != value:
        state["identity_conflict"] = True


def _activity(state: dict[str, Any], value: Any) -> None:
    if (
        isinstance(value, str)
        and value
        and (state["last_activity"] is None or value > state["last_activity"])
    ):
        state["last_activity"] = value


def _window(state: dict[str, Any], value: Any) -> None:
    if value is None:
        return
    if not _nonnegative(value) or value == 0:
        state["metric_error"] = "invalid-context-window"
        state["reported_context_window_tokens"] = None
        return
    previous = state["reported_context_window_tokens"]
    if previous is not None and previous != value:
        state["metric_error"] = "conflicting-context-window"
        state["reported_context_window_tokens"] = None
    elif state["metric_error"] not in {
        "invalid-context-window",
        "conflicting-context-window",
    }:
        state["reported_context_window_tokens"] = value


def _codex_usage(state: dict[str, Any], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    input_tokens = usage.get("input_tokens")
    cached = usage.get("cached_input_tokens", 0)
    if (
        not _nonnegative(input_tokens)
        or not _nonnegative(cached)
        or cached > input_tokens
    ):
        state["metric_error"] = "invalid-request-metric"
        state["latest_request_input_tokens"] = None
        return
    # [LAW:one-source-of-truth] Codex input_tokens already includes cached input.
    state["latest_request_input_tokens"] = input_tokens
    state["cached_input_tokens"] = cached


def _claude_usage(state: dict[str, Any], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    fields = (
        usage.get("input_tokens"),
        usage.get("cache_read_input_tokens", 0),
        usage.get("cache_creation_input_tokens", 0),
    )
    if not all(_nonnegative(value) for value in fields):
        state["metric_error"] = "invalid-request-metric"
        state["latest_request_input_tokens"] = None
        return
    state["latest_request_input_tokens"] = sum(fields)
    state["cached_input_tokens"] = fields[1] + fields[2]


def _compaction(
    state: dict[str, Any], time: Any, pre: Any, post: Any, trigger: Any
) -> None:
    state["compactions"].append(
        {
            "time": time if isinstance(time, str) else None,
            "pre_tokens": pre if _nonnegative(pre) else None,
            "post_tokens": post if _nonnegative(post) else None,
            "trigger": trigger if isinstance(trigger, str) else None,
        }
    )


def _feed_codex(state: dict[str, Any], record: dict[str, Any]) -> None:
    kind = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return
    _identity(
        state,
        payload.get("session_id") or payload.get("id")
        if kind == "session_meta"
        else payload.get("session_id"),
    )
    if kind == "session_meta":
        # session_meta.context_window is an opaque window ID in Codex JSONL.
        _window(state, payload.get("model_context_window"))
    elif kind == "turn_context":
        if isinstance(payload.get("model"), str):
            state["model"] = payload["model"]
    elif kind == "token_usage_record":
        _codex_usage(state, payload.get("usage") or payload.get("turn_token_usage"))
    elif kind == "compacted":
        prior = payload.get("latest_token_usage_record") or {}
        usage = prior.get("usage") or prior.get("turn_token_usage") or {}
        _compaction(
            state, record.get("timestamp"), usage.get("input_tokens"), None, None
        )
        state["_last_codex_compaction"] = True
    elif kind == "event_msg":
        event = payload.get("type")
        if event == "task_started":
            state["status"] = "active"
            state["_active_turn_id"] = payload.get("turn_id")
            _window(state, payload.get("model_context_window"))
        elif event == "task_complete":
            if state["_active_turn_id"] in {None, payload.get("turn_id")}:
                state["status"] = "complete"
                state["_active_turn_id"] = None
                state["completion_times"].append(record.get("timestamp"))
                state["completion_count"] += 1
        elif event in {"turn_aborted", "task_aborted", "task_failed"}:
            state["status"] = "unknown"
            state["_active_turn_id"] = None
        elif event == "token_count":
            info = payload.get("info") or {}
            if isinstance(info, dict):
                _codex_usage(state, info.get("last_token_usage"))
                _window(state, info.get("model_context_window"))
        elif event == "context_compacted":
            if not state["_last_codex_compaction"]:
                _compaction(state, record.get("timestamp"), None, None, None)
            state["_last_codex_compaction"] = False


def _feed_claude(state: dict[str, Any], record: dict[str, Any]) -> None:
    _identity(state, record.get("sessionId") or record.get("session_id"))
    kind = record.get("type")
    if kind == "user":
        state["status"] = "active"
    elif kind == "assistant":
        message = record.get("message")
        if not isinstance(message, dict):
            return
        identifier = message.get("id")
        if not isinstance(identifier, str) or not identifier:
            state["metric_error"] = "missing-response-id"
            return
        digest = hashlib.sha256(identifier.encode()).hexdigest()
        if (
            digest in state["_seen_response_hashes"]
            and digest != state["_last_response_hash"]
        ):
            return
        if digest not in state["_seen_response_hashes"]:
            state["_seen_response_hashes"].append(digest)
            state["observed_responses"] += 1
            state["_last_response_hash"] = digest
            state["latest_request_input_tokens"] = None
            state["cached_input_tokens"] = None
        if isinstance(message.get("model"), str):
            state["model"] = message["model"]
        _claude_usage(state, message.get("usage"))
        stop = message.get("stop_reason")
        state["status"] = (
            "complete"
            if stop == "end_turn"
            else "active"
            if stop == "tool_use"
            else "unknown"
        )
        if stop == "end_turn" and digest not in state["_completed_response_hashes"]:
            state["_completed_response_hashes"].append(digest)
            state["completion_times"].append(record.get("timestamp"))
            state["completion_count"] += 1
    elif kind == "system":
        subtype = record.get("subtype")
        if subtype == "compact_boundary":
            metadata = record.get("compactMetadata") or {}
            _compaction(
                state,
                record.get("timestamp"),
                metadata.get("preTokens"),
                metadata.get("postTokens"),
                metadata.get("trigger"),
            )
        elif subtype in {"interrupted", "turn_aborted", "task_failed"}:
            state["status"] = "unknown"


def _feed(state: dict[str, Any], record: Any) -> None:
    if not isinstance(record, dict):
        raise ValueError("invalid JSONL record type")
    _activity(state, record.get("timestamp"))
    if state["kind"] == "codex":
        _feed_codex(state, record)
    else:
        _feed_claude(state, record)


def _scan(
    kind: str, transcript: Path, prior: dict[str, Any] | None = None, offset: int = 0
) -> tuple[dict[str, Any], int]:
    state = _fresh(kind) if prior is None else prior
    state["partial_tail"] = False
    with transcript.open("rb") as stream:
        stream.seek(offset)
        while True:
            start = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                if state["status"] != "active":
                    raise ValueError(
                        f"truncated completed JSONL record at byte {start}"
                    )
                state["partial_tail"] = True
                break
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid JSON at byte {start}") from error
            _feed(state, record)
            offset = stream.tell()
    state["compaction_count"] = len(state["compactions"])
    return state, offset


def _public(state: dict[str, Any]) -> dict[str, Any]:
    summary = {
        key: value
        for key, value in state.items()
        if not key.startswith("_") and key != "completion_times"
    }
    summary["compactions"] = state["compactions"][-3:]
    return summary


def inspect_transcript(kind: str, transcript: str | Path) -> dict[str, Any]:
    """Return bounded metadata only, never message content or reasoning."""
    state, _ = _scan(kind, Path(transcript))
    return _public(state)


def admit(
    summary: dict[str, Any],
    *,
    task_budget: int,
    reserve: int,
    ceiling: int,
    paused: bool = False,
    expected_session_id: str | None = None,
) -> dict[str, Any]:
    """Decide from explicit operational headroom and completed session state."""
    reasons = []
    if paused:
        reasons.append("paused")
    if not isinstance(summary.get("session_id"), str) or not summary["session_id"]:
        reasons.append("missing-session-id")
    if summary.get("identity_conflict"):
        reasons.append("session-id-conflict")
    if expected_session_id is not None and (
        summary.get("session_id") != expected_session_id
        or summary.get("identity_conflict")
    ):
        reasons.append("session-id-mismatch")
    if summary.get("status") != "complete":
        reasons.append("session-not-complete")
    if not _nonnegative(ceiling) or ceiling == 0:
        reasons.append("invalid-ceiling")
    if not _nonnegative(task_budget) or not _nonnegative(reserve):
        reasons.append("invalid-budget")
    request = summary.get("latest_request_input_tokens")
    if not _nonnegative(request) or summary.get("metric_error"):
        reasons.append("missing-request-metric")
    remaining = (
        ceiling - request if _nonnegative(ceiling) and _nonnegative(request) else None
    )
    required = (
        task_budget + reserve
        if _nonnegative(task_budget) and _nonnegative(reserve)
        else None
    )
    if remaining is not None and required is not None and remaining < required:
        reasons.append("insufficient-headroom")
    # [LAW:verifiable-goals] Compaction preTokens never substitutes for a ceiling.
    return {
        "decision": "allow" if not reasons else "hold",
        "reasons": reasons,
        "remaining_tokens": remaining,
        "required_tokens": required,
        "operational_ceiling_tokens": ceiling,
    }


class NotificationError(RuntimeError):
    """A queue delivery failed after the event was durably recorded."""


def _load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("unsupported watch config version")
    if type(config.get("repair_paused")) is not bool:
        raise ValueError("repair_paused must be boolean")
    if not isinstance(config.get("ticket"), str) or not config["ticket"]:
        raise ValueError("ticket must be nonempty")
    thread = config.get("notification_thread")
    if thread is not None:
        try:
            valid_thread = str(UUID(thread)) == thread
        except (ValueError, TypeError, AttributeError):
            valid_thread = False
        if not valid_thread:
            raise ValueError("notification_thread must be an exact UUID")
    sessions = config.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("sessions must be a nonempty list")
    roles = set()
    for session in sessions:
        if not isinstance(session, dict):
            raise ValueError("invalid session config")
        for field in ("role", "kind", "session_id", "transcript"):
            if not isinstance(session.get(field), str) or not session[field]:
                raise ValueError(f"session {field} must be nonempty")
        if session["kind"] not in {"codex", "claude"} or session["role"] in roles:
            raise ValueError("invalid or duplicate session role/kind")
        roles.add(session["role"])
        for field in ("ceiling", "task_budget", "reserve"):
            if not _nonnegative(session.get(field)):
                raise ValueError(f"session {field} must be a nonnegative integer")
    return config


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "sessions": {},
            "pending_notifications": [],
            "sent_notifications": [],
        }
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("unsupported watch state version")
    if not isinstance(state.get("sessions"), dict) or not isinstance(
        state.get("pending_notifications"), list
    ):
        raise ValueError("invalid watch state")
    state.setdefault("sent_notifications", [])
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    # [LAW:no-ambient-temporal-coupling] A complete checkpoint replaces the
    # previous one only after all event records have reached durable storage.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _existing_event_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    identifiers = set()
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid event JSONL line {number}") from error
            if not isinstance(event, dict) or not isinstance(
                event.get("event_id"), str
            ):
                raise ValueError(f"invalid event JSONL line {number}")
            identifiers.add(event["event_id"])
    return identifiers


def _event_id(session: dict[str, Any], event_type: str, marker: Any) -> str:
    data = [session["role"], session["kind"], session["session_id"], event_type, marker]
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]


def _append_event(path: Path, event: dict[str, Any]) -> None:
    encoded = (json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n").encode()
    descriptor = os.open(
        path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _scan_watch_session(
    session: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    path = Path(session["transcript"])
    if previous is None or any(
        previous.get(key) != session[key]
        for key in ("kind", "session_id", "transcript")
    ):
        previous = {
            "kind": session["kind"],
            "session_id": session["session_id"],
            "transcript": session["transcript"],
            "offset": 0,
            "summary": _fresh(session["kind"]),
            "completion_emitted": 0,
            "compaction_emitted": 0,
            "last_admission_key": None,
            "admission_revision": 0,
            "file_identity": None,
        }
    if not path.exists():
        if previous["offset"]:
            raise ValueError(f"transcript disappeared for role {session['role']}")
        return previous
    stat = path.stat()
    identity = [stat.st_dev, stat.st_ino]
    if previous["file_identity"] is not None and previous["file_identity"] != identity:
        raise ValueError(f"transcript replaced for role {session['role']}")
    if stat.st_size < previous["offset"]:
        raise ValueError(f"transcript truncated for role {session['role']}")
    summary, offset = _scan(
        session["kind"], path, previous["summary"], previous["offset"]
    )
    previous.update(offset=offset, summary=summary, file_identity=identity)
    return previous


def _candidate_events(
    session: dict[str, Any], saved: dict[str, Any], decision: dict[str, Any]
) -> list[dict[str, Any]]:
    summary = saved["summary"]
    base = {
        "role": session["role"],
        "kind": session["kind"],
        "session_id": session["session_id"],
        "source": session["transcript"],
    }
    events = []
    identity_ok = (
        summary["session_id"] == session["session_id"]
        and not summary["identity_conflict"]
    )
    if identity_ok:
        for index in range(saved["completion_emitted"], summary["completion_count"]):
            event = {
                **base,
                "type": "completion",
                "ordinal": index + 1,
                "time": summary["completion_times"][index],
                "action": "operator-review",
            }
            event["event_id"] = _event_id(session, "completion", index + 1)
            events.append(event)
        for index in range(saved["compaction_emitted"], summary["compaction_count"]):
            event = {
                **base,
                "type": "compaction",
                "ordinal": index + 1,
                **summary["compactions"][index],
                "action": "operator-review",
            }
            event["event_id"] = _event_id(session, "compaction", index + 1)
            events.append(event)
    saved["completion_emitted"] = summary["completion_count"]
    saved["compaction_emitted"] = summary["compaction_count"]
    admission = {
        "decision": decision["decision"],
        "reasons": decision["reasons"],
        "latest_request_input_tokens": summary["latest_request_input_tokens"],
        "remaining_tokens": decision["remaining_tokens"],
        "required_tokens": decision["required_tokens"],
        "operational_ceiling_tokens": decision["operational_ceiling_tokens"],
    }
    marker = json.dumps(admission, sort_keys=True, separators=(",", ":"))
    if marker != saved["last_admission_key"]:
        saved["admission_revision"] += 1
        event = {
            **base,
            "type": "admission",
            **admission,
            "action": "operator-decision",
        }
        event["event_id"] = _event_id(session, "admission", saved["admission_revision"])
        events.append(event)
        saved["last_admission_key"] = marker
    return events


def _deliver_pending(
    config: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
    events_path: Path,
    queue_runner: Any,
) -> None:
    if config["repair_paused"]:
        return
    thread = config.get("notification_thread")
    if thread is None:
        raise ValueError("--notify requires notification_thread")
    while state["pending_notifications"]:
        event_id = state["pending_notifications"][0]
        pointer = f"{events_path}#{event_id}"
        message = (
            f"TO: Codex thread {thread}. FROM: session_context watch. "
            f"{config['ticket']} | {pointer} | inspect local event and decide action"
        )
        argv = ["codex", "queue", "--thread", thread, "--message", message]
        try:
            result = queue_runner(argv, capture_output=True, text=True, check=False)
        except OSError as error:
            raise NotificationError(f"queue failed: {error}") from error
        if result.returncode != 0:
            raise NotificationError(
                f"queue failed: {result.returncode}: {result.stderr.strip()[:200]}"
            )
        state["pending_notifications"].pop(0)
        state["sent_notifications"].append(event_id)
        _save_state(state_path, state)


def watch_once(
    config_path: str | Path,
    state_path: str | Path,
    events_path: str | Path,
    *,
    notify: bool = False,
    queue_runner: Any = subprocess.run,
) -> list[dict[str, Any]]:
    """Poll only unread JSONL bytes and durably emit changed local events."""
    config = _load_config(Path(config_path))
    state_path, events_path = Path(state_path), Path(events_path)
    state = _load_state(state_path)
    known_ids = _existing_event_ids(events_path)
    emitted = []
    if notify and config.get("notification_thread") is None:
        raise ValueError("--notify requires notification_thread")
    for session in config["sessions"]:
        role = session["role"]
        saved = _scan_watch_session(session, state["sessions"].get(role))
        decision = admit(
            _public(saved["summary"]),
            task_budget=session["task_budget"],
            reserve=session["reserve"],
            ceiling=session["ceiling"],
            paused=config["repair_paused"],
            expected_session_id=session["session_id"],
        )
        candidates = _candidate_events(session, saved, decision)
        for event in candidates:
            if event["event_id"] not in known_ids:
                _append_event(events_path, event)
                known_ids.add(event["event_id"])
                emitted.append(event)
            if (
                notify
                and event["event_id"] not in state["sent_notifications"]
                and event["event_id"] not in state["pending_notifications"]
            ):
                state["pending_notifications"].append(event["event_id"])
        state["sessions"][role] = saved
        _save_state(state_path, state)
    if notify:
        _deliver_pending(config, state, state_path, events_path, queue_runner)
    return emitted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "admit"):
        command = commands.add_parser(name)
        command.add_argument("--kind", required=True, choices=("codex", "claude"))
        command.add_argument("--transcript", required=True, type=Path)
        if name == "admit":
            command.add_argument("--task-budget", required=True, type=int)
            command.add_argument("--reserve", required=True, type=int)
            command.add_argument("--ceiling", required=True, type=int)
            command.add_argument("--paused", action="store_true")
    watch = commands.add_parser("watch")
    watch.add_argument("--config", required=True, type=Path)
    watch.add_argument("--state", required=True, type=Path)
    watch.add_argument("--events", required=True, type=Path)
    watch.add_argument("--once", action="store_true")
    watch.add_argument("--interval", type=float, default=5.0)
    watch.add_argument("--notify", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in {"inspect", "admit"}:
            summary = inspect_transcript(args.kind, args.transcript)
            if args.command == "inspect":
                print(json.dumps(summary, sort_keys=True))
                return 0
            decision = admit(
                summary,
                task_budget=args.task_budget,
                reserve=args.reserve,
                ceiling=args.ceiling,
                paused=args.paused,
            )
            print(
                json.dumps(
                    {
                        **decision,
                        "session_id": summary["session_id"],
                        "status": summary["status"],
                        "model": summary["model"],
                    },
                    sort_keys=True,
                )
            )
            return 0 if decision["decision"] == "allow" else 1
        if args.interval <= 0:
            raise ValueError("--interval must be positive")
        stopped = threading.Event()

        def stop(_signal: int, _frame: Any) -> None:
            stopped.set()

        if not args.once:
            signal.signal(signal.SIGINT, stop)
            signal.signal(signal.SIGTERM, stop)
        while not stopped.is_set():
            events = watch_once(
                args.config, args.state, args.events, notify=args.notify
            )
            print(
                json.dumps({"emitted": len(events), "events": str(args.events)}),
                flush=True,
            )
            if args.once:
                break
            stopped.wait(args.interval)
        return 0
    except (ValueError, OSError, NotificationError) as error:
        print(f"session_context stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
