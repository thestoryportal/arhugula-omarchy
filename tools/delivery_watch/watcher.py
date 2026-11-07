#!/usr/bin/env python3
"""Local delivery observations -> durable, at-most-once native notifications."""

import argparse
from contextlib import closing
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time


class ObservationDeferred(Exception):
    """This cycle's effect budget is spent; the next cycle retains the work."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def epoch(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def run(argv, cwd, timeout=12):
    # [LAW:effects-at-boundaries] All external observation and notification is here.
    return subprocess.run(
        argv,
        cwd=cwd,
        env={**os.environ, "LIT_DISABLE_AUTO_SYNC": "1"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def text_parts(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_parts(x) for x in value)
    if isinstance(value, dict):
        return "\n".join(
            text_parts(value[k])
            for k in ("text", "content", "output", "message")
            if k in value
        )
    return ""


def native_result_texts(item, calls):
    """Return final prose and outputs belonging to native Memento invocations."""
    payload = item.get("payload", item.get("message", {}))
    record, kind = item.get("type"), payload.get("type")
    content = payload.get("content", [])
    blocks = content if isinstance(content, list) else []
    # [LAW:parse-dont-validate] Call identity establishes output provenance;
    # document text and request-cache copies cannot become launcher receipts.
    launcher = r"(?:[^\s'\"]*/)?finalize-session(?=\s|['\"]|$)"
    if record == "assistant":
        for block in blocks:
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                command = block.get("input", {}).get("command", "")
                if re.match(r"\s*['\"]?" + launcher, command):
                    calls[block["id"]] = True
    if record == "response_item" and kind in {"function_call", "custom_tool_call"}:
        arguments = payload.get("arguments", payload.get("input", ""))
        if re.search(r"['\"]?cmd['\"]?\s*:\s*['\"]\s*" + launcher, arguments):
            calls[payload["call_id"]] = True
    outputs = []
    if record == "user":
        for block in blocks:
            if block.get("type") == "tool_result" and calls.pop(
                block.get("tool_use_id"), False
            ):
                outputs.append(text_parts(block.get("content", "")))
    if record == "response_item" and kind in {
        "function_call_output",
        "custom_tool_call_output",
    }:
        if calls.pop(payload.get("call_id"), False):
            outputs.append(text_parts(payload.get("output", "")))
    final = (record == "assistant" and payload.get("stop_reason") == "end_turn") or (
        record == "response_item"
        and payload.get("role") == "assistant"
        and payload.get("phase") in {"final", "final_answer"}
    )
    prose = (
        "\n".join(
            b.get("text", "")
            for b in blocks
            if b.get("type") in {"text", "output_text"}
        )
        if final
        else ""
    )
    return prose, "\n".join(outputs)


def native_activity(item):
    """Parse native lifecycle records; cached requests and tool results are not input."""
    record = item.get("type")
    payload = item.get("payload", item.get("message", {}))
    kind = payload.get("type")
    content = payload.get("content", [])
    if record == "event_msg":
        if kind in {"task_complete", "turn_aborted"}:
            return "idle", None
        if kind == "task_started":
            return "busy", None
        native_item = payload.get("item", {})
        if kind in {"item_started", "item_completed"}:
            if native_item.get("type") == "UserMessage":
                return "busy", text_parts(native_item.get("content", []))
            if native_item.get("type") in {"Reasoning", "AgentMessage", "ToolCall"}:
                return "busy", None
    if record == "response_item":
        if kind == "message" and payload.get("role") == "user":
            # [LAW:parse-dont-validate] Codex also injects context as user-role
            # messages. Only native typed-input provenance can acknowledge a wake.
            metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
            actual_input = metadata.get("content_item_kinds") == ["user.text"]
            return "busy", text_parts(content) if actual_input else None
        if (
            kind in {"function_call", "custom_tool_call", "reasoning"}
            or payload.get("role") == "assistant"
        ):
            return "busy", None
    if record == "user":
        if isinstance(content, str) or any(
            c.get("type") == "text" for c in content if isinstance(c, dict)
        ):
            return "busy", text_parts(content)
        if any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
            return "busy", None
    if record == "assistant":
        return ("idle" if payload.get("stop_reason") == "end_turn" else "busy"), None
    return None, None


def pending_native_inputs(database, target):
    """Read the actual queue, failing closed on missing or incompatible storage."""
    # [LAW:effects-at-boundaries] Never create, delete or consume native queue rows.
    with closing(
        sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        columns = {r[1] for r in connection.execute("PRAGMA table_info(queued_items)")}
        if not {"id", "thread_id", "payload_json"} <= columns:
            raise ValueError("native queue queued_items schema is incompatible")
        rows = connection.execute(
            "SELECT payload_json FROM queued_items WHERE thread_id=?", (target,)
        ).fetchall()
    for (raw,) in rows:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"UserInput"}:
            raise ValueError("native queue contains unsupported payload type")
        user = payload["UserInput"]
        if not isinstance(user, dict) or not isinstance(user.get("content"), list):
            raise ValueError("native queue contains malformed UserInput")
    return len(rows)


class Watcher:
    def __init__(self, config, db, command=run, now=time.time):
        self.config, self.db, self.command, self.now = config, db, command, now
        self.deadline = None
        db.executescript("""
          CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, pointer TEXT NOT NULL,
            action TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            batch TEXT, detail TEXT);
          CREATE TABLE IF NOT EXISTS outbox (
            id TEXT PRIMARY KEY, target TEXT NOT NULL, message TEXT NOT NULL,
            created REAL NOT NULL, status TEXT NOT NULL, receipt TEXT);
        """)
        self.state = {
            k: json.loads(v) for k, v in db.execute("SELECT key,value FROM state")
        }
        if "activation" not in self.state:
            self.state["activation"] = config.get("activation_epoch", now())
        # [LAW:no-ambient-temporal-coupling] A crash after dispatch is uncertainty,
        # never evidence that another send is safe.
        with db:
            db.execute("UPDATE events SET status='uncertain' WHERE status='sending'")
            db.execute("UPDATE outbox SET status='uncertain' WHERE status='sending'")

    def save(self):
        # Persist the complete owned snapshot, including removed deadlines and
        # recovered errors; upserts alone would resurrect them after restart.
        self.db.execute("DELETE FROM state")
        self.db.executemany(
            "INSERT OR REPLACE INTO state VALUES (?,?)",
            [(k, json.dumps(v)) for k, v in self.state.items()],
        )

    def event(self, key, source, pointer, action, detail=""):
        self.db.execute(
            "INSERT OR IGNORE INTO events(id,source,pointer,action,created,detail) VALUES (?,?,?,?,?,?)",
            (digest(key), source, pointer, action, self.now(), detail[:2000]),
        )

    def observe(self, key, fn):
        try:
            fn()
            self.state.pop("error:" + key, None)
            self.state.pop("deferred:" + key, None)
        except ObservationDeferred:
            self.state["deferred:" + key] = True
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
            sqlite3.Error,
            subprocess.SubprocessError,
        ) as error:
            message = f"{key}: {type(error).__name__}: {error}"
            print(message, file=sys.stderr, flush=True)
            signature = digest(message)
            if self.state.get("error:" + key) != signature:
                self.event(
                    ["error", key, signature],
                    key,
                    key,
                    "Observation failed; inspect watcher journal",
                    message,
                )
                self.state["error:" + key] = signature

    def call(self, argv):
        timeout = 12 if self.deadline is None else min(12, self.deadline - self.now())
        if timeout <= 0:
            raise ObservationDeferred()
        return self.command(argv, self.config["cwd"], timeout=timeout)

    def checked(self, argv):
        result = self.call(argv)
        if result.returncode:
            raise RuntimeError(
                f"command exited {result.returncode}: {result.stderr[:1000]}"
            )
        return json.loads(result.stdout)

    def lit(self, roles):
        data = self.checked(["lit", "export"])
        seen = set(self.state.get("lit_seen", []))
        explicit = set(self.config.get("tickets", []))
        adopted = set(self.state.get("lit_explicit_baselined", []))
        new_tickets = explicit - adopted
        authors = {
            s["session_id"]: role
            for role, s in roles.items()
            if s.get("kind") == "claude" and role != "runtime"
        }
        issues = {i["id"]: i for i in data.get("issues", [])}
        retained = self.state.get("owned_claims", {})
        claims = {}
        for c in sorted(data["comments"], key=lambda c: c["created_at"]):
            ticket = c["issue_id"]
            prefix = self.config.get("ticket_family", "arhugula-harness-trial-193")
            relevant = (
                ticket == prefix
                or ticket.startswith(prefix + ".")
                or ticket in self.config.get("tickets", [])
            )
            body = c["body"]
            branch = re.search(
                r"\bbranch\s*:?\s+[`\"']?([A-Za-z0-9][\w./-]+)", body, re.I
            )
            previous_claim = retained.get(ticket, {})
            author_role = next(
                (role for author, role in authors.items() if author in body), None
            )
            if (
                c["id"] == previous_claim.get("claim_id")
                and previous_claim.get("author_role") in roles
            ):
                author_role = previous_claim["author_role"]
            if (
                relevant
                and branch
                and re.search(r"\bCLAIM\s*[:(]", body)
                and epoch(c["created_at"]) >= self.state["activation"]
                and issues.get(ticket, {}).get("status") not in {"closed", "done"}
                and author_role is not None
            ):
                claims[ticket] = {
                    "repo": self.config.get(
                        "source_repo", "thestoryportal/arhugula-harness"
                    ),
                    "head": branch[1],
                    "claim_id": c["id"],
                    "author_role": author_role,
                }
            if relevant and re.search(r"\bWRITER RELEASE\b", body):
                claims.pop(ticket, None)
            if (
                not relevant
                or epoch(c["created_at"]) < self.state["activation"]
                or c["id"] in seen
            ):
                continue
            seen.add(c["id"])
            # Newly covered records are adopted without replaying their history.
            if ticket in new_tickets:
                continue
            # Buford already owns its own published result; notifying it again
            # creates feedback without advancing a peer's delivery.
            sender = re.search(r"(?:^|[|;\n])\s*FROM\s*:?\s+([^|;\n]+)", body, re.I)
            if sender and re.match(r"Buford(?:\b|[0-9a-f]{8}\b)", sender[1], re.I):
                continue
            if not re.search(
                r"GREEN|NEEDS\s*CORRECTION|frozen|ratif|verdict|result|handoff|memento|merged|CI.*(?:success|fail)",
                body,
                re.I,
            ):
                continue
            self.event(
                ["lit", c["id"]],
                "lit",
                f"{ticket} {c['id']}",
                "Read new delivery result and advance its next transition",
            )
            for role in roles:
                if re.search(r"\bTO\s+" + re.escape(role) + r"\b", body, re.I):
                    self.state["pending:" + role] = {
                        "pointer": c["id"],
                        "at": self.now(),
                    }
        self.state["lit_seen"] = sorted(seen)
        self.state["lit_explicit_baselined"] = sorted(explicit | adopted)
        self.state["owned_claims"] = claims
        self.state["claimed_branches"] = [
            {"repo": c["repo"], "head": c["head"]} for c in claims.values()
        ]

    def transcript(self, role, session, emit=True):
        path = Path(session["transcript"])
        if not path.exists():
            raise FileNotFoundError(str(path))
        key = "transcript:" + role
        stat = path.stat()
        previous = self.state.get(key)
        identity = [str(path), stat.st_ino]
        changed = previous is not None and (
            previous["identity"] != identity
            or stat.st_size < previous["offset"]
            or previous.get("session_id", session["session_id"])
            != session["session_id"]
        )
        bootstrap = previous is None or changed or "activity" not in previous
        offset = 0 if bootstrap else previous["offset"]
        calls = {} if bootstrap else dict(previous.get("memento_calls", {}))
        activity = (
            {"phase": "unknown", "idle_since": None}
            if bootstrap
            else dict(previous["activity"])
        )
        if changed:
            self.state.pop("pending:" + role, None)
            self.state.pop("memento:" + role, None)
        emit = emit and not bootstrap
        with path.open("rb") as stream:
            stream.seek(offset)
            # [LAW:single-enforcer] Only complete JSONL records advance the cursor.
            while line := stream.readline():
                if not line.endswith(b"\n"):
                    break
                item = json.loads(line)
                position = stream.tell()
                payload = item.get("payload", item.get("message", {}))
                text = text_parts(payload)
                kind = payload.get("type", "") if isinstance(payload, dict) else ""
                stamp = item.get("timestamp")
                fresh = not stamp or epoch(stamp) >= self.state["activation"]
                phase, input_text = native_activity(item)
                user = input_text is not None
                if phase:
                    activity["phase"] = phase
                    activity["idle_since"] = (
                        (self.now() if bootstrap or not stamp else epoch(stamp))
                        if phase == "idle"
                        else None
                    )
                    self.state["busy:" + role] = phase == "busy"
                if input_text is not None:
                    self.state.pop("pending:" + role, None)
                    wake = self.state.get("assessment:" + session["session_id"], {})
                    outstanding = wake.get("outstanding")
                    if outstanding and f"<workflow-wake:{outstanding}>" in input_text:
                        wake["consumed"] = {
                            "event": outstanding,
                            "position": position,
                            "at": stamp,
                        }
                        wake["outstanding"] = None
                    if "Read and follow the handoff" in input_text:
                        self.state.pop("memento:" + role, None)
                if not fresh:
                    offset = position
                    continue
                event_key = ["transcript", role, identity, position]
                pointer = f"{role} {path}:{position}"
                final_text, launcher_text = native_result_texts(item, calls)
                if user and "Read and follow the handoff" in text:
                    self.state.pop("memento:" + role, None)
                    if emit:
                        self.event(
                            event_key + ["successor"],
                            role,
                            pointer,
                            "Successor bottle received; verify continuity and continue claim",
                        )
                if (
                    user
                    or kind in {"task_started", "agent_message"}
                    or payload.get("type") == "function_call"
                ):
                    self.state.pop("pending:" + role, None)
                    self.state["busy:" + role] = True
                if (
                    kind in {"task_complete", "turn_aborted"}
                    or payload.get("stop_reason") == "end_turn"
                ):
                    self.state["busy:" + role] = False
                    if emit:
                        self.event(
                            event_key + ["complete"],
                            role,
                            pointer,
                            "Native turn ended; inspect result and next owned transition",
                        )
                if re.search(r"handoff scheduled\s*[→>-]", launcher_text, re.I):
                    self.state["memento:" + role] = {
                        "at": self.now(),
                        "pointer": pointer,
                        "session": session["session_id"],
                    }
                    if emit:
                        self.event(
                            event_key + ["scheduled"],
                            role,
                            pointer,
                            "Memento scheduled; verify successor receipt",
                        )
                if re.search(
                    r"uncertain (?:deliver|handoff)|cannot write the handoff|handoff.*(?:failed|failure)|codex-foot-helper:.*(?:refused|stopped)|[\"']step[\"']\s*:\s*[\"']stopped",
                    launcher_text + "\n" + final_text,
                    re.I,
                ):
                    if emit:
                        self.event(
                            event_key + ["failed"],
                            role,
                            pointer,
                            "Memento failed or uncertain; inspect and apply authorized bounded recovery",
                        )
                if re.search(
                    r"\bGREEN\b|NEEDS\s*CORRECTION|\bAPPROVE\b|\bfrozen\b",
                    final_text,
                    re.I,
                ):
                    if emit:
                        self.event(
                            event_key + ["result"],
                            role,
                            pointer,
                            "Native review/freeze result ready; read original and advance delivery",
                        )
                offset = position
        self.state[key] = {
            "identity": identity,
            "session_id": session["session_id"],
            "offset": offset,
            "memento_calls": calls,
            "activity": activity,
        }

    def assessment_root(self, control):
        roots = [
            s
            for s in control["sessions"]
            if s["role"] == "buford"
            and s["session_id"] == control["notification_thread"]
        ]
        if len(roots) != 1:
            raise ValueError(
                "current Buford notification route has no unique native transcript"
            )
        return roots[0]

    def assessment_ready(self, control):
        policy = self.config.get("workflow_assessment", {})
        if not policy.get("enabled", False) or policy.get("paused", False):
            return False
        root = self.assessment_root(control)
        if self.state.get("memento:buford") or self.state.get(
            "error:transcript:buford"
        ):
            return False
        activity = self.state.get("transcript:buford", {})
        if (
            activity.get("session_id") != root["session_id"]
            or activity.get("activity", {}).get("phase") != "idle"
        ):
            return False
        if self.now() - activity["activity"]["idle_since"] < policy.get(
            "idle_seconds", 45
        ):
            return False
        return (
            pending_native_inputs(
                self.config["native_queue_database"], root["session_id"]
            )
            == 0
        )

    def assessment(self, control):
        policy = self.config.get("workflow_assessment", {})
        target = control["notification_thread"]
        old = self.state.get("assessment_route")
        if old != target:
            # [LAW:no-ambient-temporal-coupling] A successor gets a new idle
            # interval, never the predecessor's pending wake or a replayed send.
            self.db.execute(
                "UPDATE events SET status='superseded' WHERE source=? AND status='pending'",
                ("workflow-assessment:" + str(old),),
            )
            self.state["assessment_route"] = target
        if not policy.get("enabled", False) or policy.get("paused", False):
            state = self.state.get("assessment:" + target, {})
            outstanding = state.get("outstanding")
            if outstanding:
                changed = self.db.execute(
                    "UPDATE events SET status='disabled' WHERE id=? AND status='pending'",
                    (outstanding,),
                ).rowcount
                if changed:
                    state["outstanding"] = None
            return
        interval = policy.get("idle_seconds", 45)
        if not 30 <= interval <= 60:
            raise ValueError(
                "workflow assessment idle_seconds must be between 30 and 60"
            )
        if not self.assessment_ready(control):
            return
        wake = self.state.setdefault(
            "assessment:" + target, {"sequence": 0, "outstanding": None}
        )
        if wake["outstanding"]:
            return
        if self.db.execute(
            "SELECT 1 FROM events WHERE status IN ('pending','sending') LIMIT 1"
        ).fetchone():
            return
        wake["sequence"] += 1
        event_id = digest(["workflow-assessment", target, wake["sequence"]])
        self.event(
            ["workflow-assessment", target, wake["sequence"]],
            "workflow-assessment:" + target,
            f"<workflow-wake:{event_id}> target={target}",
            "Assess the current workspace/workflow and advance the next authorized transition; preserve holds, repair pause, review budgets and native ownership. This wake grants no source/live effect or PASS.",
        )
        wake["outstanding"] = event_id

    def deadlines(self, roles):
        for role in roles:
            memento = self.state.get("memento:" + role)
            if memento and self.now() - memento["at"] >= self.config.get(
                "handoff_timeout_seconds", 120
            ):
                self.event(
                    ["missing-successor", role, memento],
                    role,
                    memento["pointer"],
                    "No successor bottle within timeout; inspect blocked Memento",
                )
            pending = self.state.get("pending:" + role)
            if (
                pending
                and not self.state.get("busy:" + role, False)
                and self.now() - pending["at"]
                >= self.config.get("idle_timeout_seconds", 120)
            ):
                self.event(
                    ["idle-pending", role, pending],
                    role,
                    pending["pointer"],
                    "Idle role has pending handoff; verify and trigger its next authorized action",
                )

    def github(self):
        if self.now() < self.state.get("github_next", 0):
            return
        self.state["github_next"] = self.now() + self.config.get(
            "github_poll_seconds", 60
        )
        watched = {(p["repo"], p["number"]): p for p in self.config.get("prs", [])}
        branches = {
            (b["repo"], b["head"]): b
            for b in self.config.get("pr_branches", [])
            + self.state.get("claimed_branches", [])
        }
        for branch in branches.values():
            key = f"branch-pr:{branch['repo']}:{branch['head']}"
            pulls = self.checked(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    branch["repo"],
                    "--head",
                    branch["head"],
                    "--state",
                    "all",
                    "--limit",
                    "10",
                    "--json",
                    "number,url",
                ]
            )
            seen = set(self.state.get(key, []))
            for pull in pulls:
                watched[(branch["repo"], pull["number"])] = {
                    "repo": branch["repo"],
                    "number": pull["number"],
                }
                if key in self.state and pull["number"] not in seen:
                    self.event(
                        [key, pull["number"]],
                        key,
                        pull["url"],
                        "New owned PR discovered; verify frozen review and exact candidate checks",
                    )
                seen.add(pull["number"])
            self.state[key] = sorted(seen)
        for pr in watched.values():
            key = f"pr:{pr['repo']}#{pr['number']}"
            data = self.checked(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr["number"]),
                    "--repo",
                    pr["repo"],
                    "--json",
                    "state,headRefOid,statusCheckRollup,url",
                ]
            )
            checks = data.get("statusCheckRollup") or []
            terminal = all(
                c.get("status") == "COMPLETED"
                or c.get("state") in {"SUCCESS", "FAILURE", "ERROR"}
                for c in checks
            )
            value = [
                data["state"],
                data["headRefOid"],
                terminal,
                sorted(
                    [
                        (
                            c.get("name", c.get("context", "")),
                            c.get("conclusion", c.get("state", "")),
                        )
                        for c in checks
                    ]
                ),
            ]
            if (
                key in self.state
                and value != self.state[key]
                and (terminal or data["state"] != self.state[key][0])
            ):
                self.event(
                    [key, value],
                    key,
                    data["url"],
                    "PR state/checks transitioned; verify exact candidate and merge gate",
                )
            self.state[key] = value
        for ref in self.config.get("refs", []):
            key = f"ref:{ref['repo']}:{ref['ref']}"
            data = self.checked(
                ["gh", "api", f"repos/{ref['repo']}/git/ref/{ref['ref']}"]
            )
            value = data["object"]["sha"]
            if key in self.state and self.state[key] != value:
                self.event(
                    [key, value],
                    key,
                    key + "@" + value,
                    "Remote reference changed; verify landing and own-main checks",
                )
            self.state[key] = value
        self.state["github_success_at"] = self.now()

    def fingerprints(self):
        for name in self.config.get("merge_files", []):
            path = Path(name)
            if path.is_dir():
                # Reservation generations are immutable files; new names are
                # the store's transition signal, without replaying their history.
                value = digest(
                    sorted(
                        (
                            str(p.relative_to(path)),
                            p.stat().st_size,
                            p.stat().st_mtime_ns,
                        )
                        for p in path.glob("*/*.json")
                    )
                )
            else:
                value = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.exists()
                    else "ABSENT"
                )
            key = "file:" + str(path)
            if key in self.state and self.state[key] != value:
                self.event(
                    [key, value],
                    key,
                    str(path),
                    "Merge door/reservation changed; inspect current holder and gate",
                )
            self.state[key] = value

    def poll(self):
        with self.db:
            control = json.loads(Path(self.config["session_control"]).read_text())
            selected = self.config.get("roles", [])
            roles = {
                s["role"]: s
                for s in control["sessions"]
                if selected == "registered" or s["role"] in selected
            }
            self.observe("lit", lambda: self.lit(roles))
            for role, session in roles.items():
                self.observe(
                    "transcript:" + role,
                    lambda r=role, s=session: self.transcript(r, s, emit=r != "buford"),
                )
            if (
                self.config.get("workflow_assessment", {}).get("enabled")
                and "buford" not in roles
            ):
                self.observe(
                    "transcript:buford",
                    lambda: self.transcript(
                        "buford", self.assessment_root(control), emit=False
                    ),
                )
            self.deadlines({r: s for r, s in roles.items() if r != "buford"})
            if self.now() >= self.state.get("github_next", 0):
                self.observe("github", self.github)
            self.observe("merge-files", self.fingerprints)
            self.observe("workflow-assessment", lambda: self.assessment(control))
            self.save()

    def dispatch(self):
        rows = self.db.execute(
            "SELECT id,pointer,action,source FROM events WHERE status='pending' ORDER BY created,id LIMIT 12"
        ).fetchall()
        if (
            not rows
            or self.now() < self.state.get("queue_retry_at", 0)
            or (self.deadline is not None and self.now() >= self.deadline)
        ):
            return
        # [LAW:one-source-of-truth] Resolve the current root at the send boundary.
        control = json.loads(Path(self.config["session_control"]).read_text())
        target = control["notification_thread"]
        if any(r[3].startswith("workflow-assessment:") for r in rows):
            try:
                self.transcript("buford", self.assessment_root(control), emit=False)
                ready = self.assessment_ready(control)
            except (OSError, ValueError, KeyError, sqlite3.Error) as error:
                print(
                    f"workflow assessment send suppressed: {error}",
                    file=sys.stderr,
                    flush=True,
                )
                ready = False
            rows = [
                r
                for r in rows
                if not r[3].startswith("workflow-assessment:")
                or (r[3] == "workflow-assessment:" + target and ready)
            ]
            with self.db:
                self.save()
        if not rows:
            return
        batch = digest([r[0] for r in rows])
        message = (
            "TO Buford integration lead FROM local delivery watcher | "
            + str(len(rows))
            + " new events\n"
            + "\n".join(f"{p} | {a}" for _, p, a, _ in rows)
        )
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO outbox VALUES (?,?,?,?,?,?)",
                (batch, target, message, self.now(), "sending", None),
            )
            self.db.executemany(
                "UPDATE events SET status='sending',batch=? WHERE id=?",
                [(batch, r[0]) for r in rows],
            )
        try:
            result = self.call(
                ["codex", "queue", "--thread", target, "--message", message]
            )
            success = result.returncode == 0 and re.search(
                r"Queued message [0-9a-f-]+ for thread " + re.escape(target) + r"\.",
                result.stdout,
            )
            known_zero = (
                result.returncode != 0
                and "failed to initialize state database:" in result.stderr
                and "attempt to write a readonly database" in result.stderr
            )
            status = "sent" if success else "pending" if known_zero else "uncertain"
            receipt = json.dumps(
                {
                    "exit": result.returncode,
                    "stdout": result.stdout[:1500],
                    "stderr": result.stderr[:1500],
                }
            )
        except ObservationDeferred:
            status, receipt = (
                "pending",
                "Cycle budget spent before queue command; no send attempted",
            )
        except (OSError, subprocess.SubprocessError) as error:
            status, receipt = "uncertain", repr(error)
        with self.db:
            self.db.execute("UPDATE events SET status=? WHERE batch=?", (status, batch))
            self.db.execute(
                "UPDATE outbox SET status=?,receipt=? WHERE id=?",
                (status, receipt, batch),
            )
            if status == "pending":
                self.state["queue_retry_at"] = self.now() + 60
                self.save()
        print(
            json.dumps(
                {"batch": batch, "status": status, "target": target, "receipt": receipt}
            ),
            flush=True,
        )

    def cycle(self, deliver=True):
        # [LAW:single-enforcer] The existing process owns the timer and all
        # effect timeouts. Slow Git/LIT observations cannot starve idle wakeups.
        self.deadline = self.now() + min(15, self.config.get("poll_seconds", 15))
        try:
            if self.config.get("workflow_assessment", {}).get("enabled"):
                with self.db:
                    control = json.loads(
                        Path(self.config["session_control"]).read_text()
                    )
                    self.observe(
                        "transcript:buford",
                        lambda: self.transcript(
                            "buford", self.assessment_root(control), emit=False
                        ),
                    )
                    self.observe(
                        "workflow-assessment", lambda: self.assessment(control)
                    )
                    self.save()
                if deliver:
                    self.dispatch()
            self.poll()
            if deliver:
                self.dispatch()
        finally:
            self.deadline = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Clone existing DB into memory; observe and print pending events, never send or mutate disk baseline",
    )
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    database = Path(config["database"])
    lock = None
    if args.dry_run:
        db = sqlite3.connect(":memory:")
        if database.exists():
            source = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            source.backup(db)
            source.close()
    else:
        database.parent.mkdir(parents=True, exist_ok=True)
        lock = database.with_suffix(".lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(database)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
    watcher = Watcher(config, db)
    while True:
        started = time.time()
        try:
            refreshed = json.loads(Path(args.config).read_text())
            if refreshed["database"] != config["database"]:
                raise ValueError(
                    "database path changed while existing watcher lock is held"
                )
            watcher.config = config = refreshed
            watcher.cycle(deliver=not args.dry_run)
            if args.dry_run:
                print(
                    json.dumps(
                        db.execute(
                            "SELECT id,source,pointer,action,status FROM events WHERE status!='sent'"
                        ).fetchall()
                    )
                )
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            print(f"watcher fatal poll error: {error}", file=sys.stderr, flush=True)
            if args.once or args.dry_run:
                return 1
        if args.once or args.dry_run:
            return 0
        time.sleep(
            max(0, min(15, config.get("poll_seconds", 15)) - (time.time() - started))
        )


if __name__ == "__main__":
    raise SystemExit(main())
