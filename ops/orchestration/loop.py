"""Durable admission boundaries for the existing visible Buford lane.

This controller records and holds work. It never clears a TUI, starts a replacement
orchestrator, unpauses a goal, steals a claim or merges product work.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from .artifacts import capture, DEFAULT_ROOT, file_binding
from .continuation import Lease, Stop, select_ticket
from .ownership import conflicts, parse as parse_reservation
from .records import atomic_json, private_directory
from .review_budget import evaluate, load_gate


def fingerprint(data, ticket, goal):
    # [LAW:one-source-of-truth] Comment bodies/IDs participate even without updated_at.
    scope = {ticket, goal}
    relations = data["relations"]
    while True:
        expanded = scope | {
            r["dst_id"]
            for r in relations
            if r["src_id"] in scope and r["type"] in ("parent-child", "blocks")
        }
        if expanded == scope:
            break
        scope = expanded
    value = {
        "issues": sorted(
            (i for i in data["issues"] if i["id"] in scope), key=lambda i: i["id"]
        ),
        "comments": sorted(
            (c for c in data["comments"] if c["issue_id"] in scope),
            key=lambda c: c["id"],
        ),
        "relations": sorted(
            (r for r in relations if r["src_id"] in scope or r["dst_id"] in scope),
            key=lambda r: json.dumps(r, sort_keys=True),
        ),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def excluded_scope(data, quarantined):
    excluded = set(quarantined)
    while True:
        expanded = excluded | {
            r["src_id"]
            for r in data.get("relations", [])
            if r["dst_id"] in excluded and r["type"] in ("blocks", "parent-child")
        }
        if expanded == excluded:
            return excluded
        excluded = expanded


def identity(transcript):
    result = dict(
        session_id=None,
        model=None,
        effort=None,
        status="unknown",
        input_tokens=None,
        created_at=None,
        cwd=None,
        source=None,
        originator=None,
        first_user=None,
        last_user=None,
        last_user_hash=None,
        user_count=0,
    )
    with Path(transcript).open() as stream:
        for row in map(json.loads, stream):
            payload = row.get("payload", {})
            if row.get("type") == "session_meta":
                identifier = payload["id"]
                if result["session_id"] not in (None, identifier):
                    raise ValueError("transcript identity conflict")
                result["session_id"] = identifier
                result.update(
                    created_at=payload.get("timestamp", row.get("timestamp")),
                    cwd=payload.get("cwd"),
                    source=payload.get("source"),
                    originator=payload.get("originator"),
                )
            # [LAW:single-enforcer] Native provenance separates automatic goal
            # context from user input, including identical user-authored text.
            elif (
                row.get("type") == "response_item"
                and payload.get("role") == "user"
                and payload.get("internal_chat_message_metadata_passthrough", {}).get(
                    "content_item_kinds"
                ) != ["goal.internal_context"]
            ):
                text = "\n".join(c.get("text", "") for c in payload.get("content", []))
                # Native CLI records injected AGENTS/environment before the user input.
                if not text.startswith(
                    ("# AGENTS.md instructions for ", "<environment_context>")
                ):
                    if result["first_user"] is None:
                        result["first_user"] = text
                    result["last_user_hash"] = hashlib.sha256(text.encode()).hexdigest()
                    result["last_user"] = text
                    result["user_count"] += 1
            elif row.get("type") == "turn_context":
                result.update(
                    model=payload.get("model"),
                    effort=payload.get("effort", payload.get("reasoning_effort")),
                )
            elif row.get("type") == "event_msg":
                event = payload.get("type")
                if event == "task_started":
                    result["status"] = "active"
                elif event == "task_complete":
                    result["status"] = "complete"
                elif event in ("turn_aborted", "task_aborted", "task_failed"):
                    result["status"] = "unknown"
                elif event == "token_count":
                    result["input_tokens"] = (
                        (payload.get("info") or {})
                        .get("last_token_usage", {})
                        .get("input_tokens")
                    )
    return result


BOTTLE_SHAPE = {
    "role": str,
    "outgoing": dict,
    "lit": dict,
    "release_receipt": str,
    "pause": list,
    "goal_receipt": str,
    "next_step": str,
}


@dataclass(frozen=True)
class Bottle:
    """The outgoing lane's sealed message: pointers only, never the conversation.

    The goal ledger stays the only home of objective and deadline, so a bottle that
    carries any key beyond pointers is refused rather than becoming a second source.
    """

    binding: dict

    @classmethod
    def parse(cls, path):
        binding = file_binding(path)
        data = json.loads(Path(path).read_text())
        if (
            set(data) != set(BOTTLE_SHAPE)
            or any(type(data[k]) is not t for k, t in BOTTLE_SHAPE.items())
            or set(data["outgoing"]) != {"session_id", "model", "effort", "window", "process"}
            or set(data["lit"]) != {"ticket", "comments"}
            or not data["lit"]["comments"]
            or not all(isinstance(p, str) and p for p in data["pause"])
        ):
            raise ValueError("bottle must hold only the sealed pointer schema")
        return cls(binding)

    def sealed(self):
        if file_binding(self.binding["path"]) != self.binding:
            raise ValueError("sealed bottle changed; refuse delivery")
        return self.binding


@dataclass(frozen=True)
class RecoveryTransfer:
    """Bound failed attempt and immutable predecessor chain, without epoch credit."""

    binding: dict
    grant: dict
    failed: dict

    @classmethod
    def parse(cls, authority, *, expected=None):
        try:
            return cls._parse(authority, expected)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("malformed maintenance recovery capability") from error

    @classmethod
    def _parse(cls, authority, expected):
        binding = file_binding(authority)
        if expected is not None and binding != expected:
            raise ValueError("predecessor maintenance authority changed")
        grant = json.loads(Path(authority).read_text())
        evidence_keys = [
            "supervisor",
            "journal",
            "routing",
            "human_authority",
            "current_goal",
            "terminal_goal",
        ]
        if grant.get("kind") == "expired-waiting-fresh-sealed-prompt":
            evidence_keys.extend(("config", "execution_config", "goal_ledger"))
        for key in evidence_keys:
            if file_binding(grant[key]["path"]) != grant[key]:
                raise ValueError("failed recovery evidence changed")
        failed = json.loads(Path(grant["journal"]["path"]).read_text())
        predecessor = failed.get("maintenance_recovery")
        # [LAW:types-are-the-program] A successor must carry the particular prior
        # authority; a phase whitelist cannot express this relationship.
        if predecessor is not None:
            if (
                grant.get("predecessor") != predecessor
                or predecessor["failed_reset"] == failed["reset"]
            ):
                raise ValueError("attempt-specific predecessor recovery proof required")
            old = predecessor["authority"]
            prior = cls.parse(old["path"], expected=old)
            history = [*prior.failed.get("maintenance_recovery_history", [])]
            if prior.failed.get("maintenance_recovery") is not None:
                history.append(prior.failed["maintenance_recovery"])
            if (
                prior.failed["reset"] != predecessor["failed_reset"]
                or failed.get("maintenance_recovery_history", []) != history
            ):
                raise ValueError("predecessor maintenance history mismatch")
            if prior.grant["session_id"] == failed["session_id"]:
                if (
                    grant.get("kind") != "expired-waiting-fresh-sealed-prompt"
                    or grant["human_authority"] != prior.grant["human_authority"]
                ):
                    raise ValueError("predecessor maintenance identity/authority mismatch")
            else:
                # [LAW:one-source-of-truth] A later accepted native reset makes
                # the earlier recovery historical; retain its entire proof chain.
                bound = failed["native_receipt"]
                if file_binding(bound["path"]) != bound:
                    raise ValueError("intervening native reset receipt changed")
                receipt = json.loads(Path(bound["path"]).read_text())
                acceptance = failed["native_acceptance"]
                if (
                    failed["maintenance_only"] is not False
                    or failed["awaiting_native_receipt"] is not False
                    or receipt["session_id"] != failed["session_id"]
                    or receipt["epoch"] != failed["epoch"]
                    or receipt["bootstrap"] != failed["last_bootstrap"]
                    or acceptance["deadline"] is None
                    or acceptance["accepted_at"] > acceptance["deadline"]
                ):
                    raise ValueError("intervening verified native reset required")
        elif grant.get("predecessor") is not None:
            raise ValueError("unexpected predecessor maintenance proof")
        return cls(binding, grant, failed)


def open_dependencies(data, ticket):
    # A child inherits its epic's native blockers, as LIT readiness does.
    relations = data["relations"]
    scope = {ticket}
    while True:
        expanded = scope | {
            r["dst_id"]
            for r in relations
            if r["src_id"] in scope and r["type"] == "parent-child"
        }
        if expanded == scope:
            break
        scope = expanded
    closed = {i["id"] for i in data["issues"] if i.get("status") == "closed"}
    return sorted(
        {r["dst_id"] for r in relations if r["src_id"] in scope and r["type"] == "blocks"}
        - closed
    )


def read_journal(path):
    state = json.loads(Path(path).read_text())
    if (
        state["version"] != 2
        or not isinstance(state["completed"], dict)
        or not isinstance(state["reviews"], dict)
    ):
        raise ValueError("invalid loop journal")
    # Journals written before reservations existed recorded none.
    state.setdefault("reservations", [])
    return state


@contextmanager
def journal_ownership(path):
    """Active reservations, held unchanged under the journal lease while in use."""
    # [LAW:no-ambient-temporal-coupling] The lease spans the whole decision, so no
    # reservation can be released between reading it and relying on it.
    with Lease(Path(path).with_suffix(".lock")):
        yield [parse_reservation(r) for r in read_journal(path)["reservations"]]


class NativeLit:
    def __init__(self, cwd, artifact_root=DEFAULT_ROOT, argv=("lit",)):
        self.cwd, self.root, self.argv = Path(cwd), artifact_root, list(argv)

    def command(self, *args):
        receipt = capture([*self.argv, *args], self.cwd, root=self.root, timeout=30)
        if receipt["exit"] or receipt["terminal"] != "exited":
            raise ValueError(f"LIT read/write failed: {receipt['receipt']}")
        return Path(receipt["stdout"]["path"]).read_text(), receipt["receipt"]

    def read(self, ticket):
        text, export = self.command("export")
        data = json.loads(text)
        # [LAW:no-silent-failure] A partial export cannot stand in for zero comments.
        if (
            data.get("version") != 2
            or any(type(data.get(k)) is not list for k in ("issues", "comments", "relations"))
            or sum(i["id"] == ticket for i in data["issues"]) != 1
        ):
            raise ValueError("invalid LIT ticket/export")
        _, show = self.command("show", ticket)
        return data, {"export": export, "show": show}

    def next(self, data, excluded):
        text, receipt = self.command("next")
        identifiers = [
            x for x in text.split() if x in {i["id"] for i in data["issues"]}
        ]
        if len(set(identifiers)) != 1:
            raise ValueError("ambiguous native LIT next")
        candidate = identifiers[0]
        if candidate not in excluded:
            return candidate, receipt
        # Explicit quarantine path, not a silent fallback to a different queue.
        text, receipt = self.command("backlog", "--columns", "id,state,blocked")
        for block in re.split(r"(?m)^\s*\d+\.\s+", text)[1:]:
            fields = block.splitlines()[0].split()
            if len(fields) < 3 or fields[0] in excluded or fields[2] != "-":
                continue
            claim_lines = [
                line.strip()
                for line in block.splitlines()[1:]
                if line.strip().startswith("claimed ")
            ]
            if any(
                "claimed here" not in line and "stale" not in line
                for line in claim_lines
            ):
                continue
            issue, _ = select_ticket(data, fields[0] + " native-backlog")
            if issue and issue["id"] not in excluded:
                return issue["id"], receipt
        return None, receipt


class Loop:
    def __init__(self, state, control, lit):
        self.path, self.control, self.lit = (
            Path(state).absolute(),
            Path(control).absolute(),
            lit,
        )

    def _read(self):
        return read_journal(self.path)

    def _save(self, state):
        atomic_json(self.path, state)

    def _control(self):
        data = json.loads(self.control.read_text())
        if type(data.get("repair_paused")) is not bool:
            raise ValueError("invalid pause control")
        if sum(s["role"] == "buford" for s in data["sessions"]) != 1:
            raise ValueError("one Buford routing record required")
        return data

    def initialize(self, session, model, effort, handoff, goal):
        private_directory(self.path.parent)
        with Lease(self.path.with_suffix(".lock")):
            if (
                self.path.exists()
                or self.path.with_name(
                    self.path.name + ".publication-uncertain"
                ).exists()
            ):
                raise ValueError("journal already initialized; never reset progress")
            control = self._control()
            buford = next(s for s in control["sessions"] if s["role"] == "buford")
            if buford["session_id"] != session:
                raise ValueError("Buford routing identity mismatch")
            self._save(
                dict(
                    version=2,
                    session_id=session,
                    model=model,
                    effort=effort,
                    epoch=0,
                    epoch_start=0,
                    completed={},
                    reviews={},
                    quarantine=[],
                    unit_quarantine=[],
                    admissions={},
                    arc_units={},
                    admission=None,
                    reservations=[],
                    iteration=0,
                    goal_ticket=goal,
                    handoff=file_binding(handoff),
                    reset=None,
                    pending_bootstrap=None,
                )
            )

    def status(self):
        state = self._read()
        return {
            **state,
            "epoch_completed": len(state["completed"]) - state["epoch_start"],
            "production_paused": self._control()["repair_paused"],
        }

    def begin(self, ticket, *, maintenance=False, headroom=True, unit=None):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            control = self._control()
            data, receipts = self.lit.read(ticket)
            if state.get("awaiting_native_receipt"):
                raise ValueError(
                    "verified native reset receipt required before fresh-epoch admission"
                )
            if state.get('startup_required'):
                receipt = state.get('startup_receipt')
                # An older epoch's receipt never stands in for this context's startup.
                if receipt is None or receipt.get('epoch') != state['epoch']:
                    raise ValueError('verified startup context receipt required before workflow')
                row = next(s for s in control['sessions'] if s['role'] == 'buford')
                state['startup_workflow_admission'] = self._startup_budget(state, row['transcript'])
            if state.get("maintenance_only") and not maintenance:
                raise ValueError(
                    "maintenance recovery requires a genuine native reset before production"
                )
            closed = {i["id"] for i in data["issues"] if i.get("status") == "closed"}
            unreconciled = (set(state["admissions"]) & closed) - set(state["completed"])
            if unreconciled:
                raise ValueError(
                    "completion-reconciliation-required: "
                    + ",".join(sorted(unreconciled))
                )
            if control["repair_paused"] and not maintenance:
                raise ValueError("production-paused")
            buford = next(s for s in control["sessions"] if s["role"] == "buford")
            if buford["session_id"] != state["session_id"]:
                raise ValueError("Buford identity changed; bootstrap required")
            recovered_maintenance = maintenance and state.get("maintenance_only", False)
            if (
                len(state["completed"]) - state["epoch_start"] >= 5
                or state["reset"]
                or state.get("reset_requested")
                and not recovered_maintenance
                or not headroom
            ):
                if not headroom:
                    state["reset_requested"] = True
                    self._save(state)
                raise ValueError("context-reset-required")
            denied = excluded_scope(data, set(state["quarantine"]))
            if ticket in denied:
                raise ValueError("ticket quarantined or dependent on quarantine")
            key = ticket if unit is None else ticket + "::" + unit
            if key in state["unit_quarantine"] or (
                unit is None
                and any(x.startswith(ticket + "::") for x in state["unit_quarantine"])
            ):
                raise ValueError("review unit quarantined; choose an independent unit")
            # Admission is implementation and landing clearance. Preparation beside
            # an open blocker is not admitted here: no verified grant source exists.
            blocked = open_dependencies(data, ticket)
            if blocked:
                raise ValueError("dependency-open: " + ",".join(blocked))
            reservation = self._writer(state, ticket)
            issue = next(i for i in data["issues"] if i["id"] == ticket)
            if (
                issue["status"] == "closed"
                or issue.get("deleted_at")
                or issue.get("archived_at")
            ):
                raise ValueError("ticket is not active")
            state["iteration"] += 1
            state["admission"] = dict(
                id=str(uuid.uuid4()),
                ticket=ticket,
                fingerprint=fingerprint(data, ticket, state["goal_ticket"]),
                control=file_binding(self.control)["sha256"],
                maintenance=maintenance,
                reads=receipts,
                iteration=state["iteration"],
                unit=unit,
                reservation=reservation,
            )
            state["admissions"][ticket] = state["admission"]
            state['startup_required'] = False
            self._save(state)
            return {
                "admission": state["admission"]["id"],
                "ticket": ticket,
                "iteration": state["iteration"],
                "reads": receipts,
                "epoch_completed": len(state["completed"]) - state["epoch_start"],
            }

    def _startup_budget(self, state, transcript):
        from .startup import budget, StartupBudgetRejected
        try:
            return budget(transcript, state['session_id'])
        except StartupBudgetRejected as error:
            state['startup_rejection'] = error.report
            state['reset_requested'] = True
            self._save(state)
            raise

    def request_reset(self, evidence):
        """Record a ceiling close decision; admission holds until a genuine reset."""
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            requests = state.setdefault("reset_requests", [])
            if evidence not in requests:
                requests.append(evidence)
            state["reset_requested"] = True
            self._save(state)
            return requests

    def finish_startup(self):
        """Bind native context measurement before the first workflow admission."""
        with Lease(self.path.with_suffix('.lock')):
            state = self._read()
            row = next(s for s in self._control()['sessions'] if s['role'] == 'buford')
            if row['session_id'] != state['session_id'] or state.get('awaiting_native_receipt'):
                raise ValueError('native bootstrap required before startup measurement')
            report = self._startup_budget(state, row['transcript'])
            report.update(epoch=state['epoch'], routing=file_binding(self.control))
            state['startup_receipt'] = report
            self._save(state)
            return report

    def check(self, admission):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            grant = state["admission"]
            if grant is None or grant["id"] != admission:
                raise ValueError("fresh LIT admission required")
            data, receipts = self.lit.read(grant["ticket"])
            if (
                fingerprint(data, grant["ticket"], state["goal_ticket"])
                != grant["fingerprint"]
                or file_binding(self.control)["sha256"] != grant["control"]
            ):
                raise ValueError("LIT changed or pause/routing changed; begin again")
            if self._writer(state, grant["ticket"]) != grant["reservation"]:
                raise ValueError("reservation changed; begin again")
            return {
                "ticket": grant["ticket"],
                "reads": receipts,
                "admission": admission,
            }

    def complete(self, ticket, evidence):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            data, receipts = self.lit.read(ticket)
            issue = next(i for i in data["issues"] if i["id"] == ticket)
            if (
                issue["status"] != "closed"
                or issue.get("deleted_at")
                or issue.get("archived_at")
            ):
                raise ValueError("LIT ticket must actually be closed")
            if any(
                r["type"] == "parent-child" and r["dst_id"] == ticket
                for r in data.get("relations", [])
            ):
                raise ValueError("completed parent/epic is not a completed leaf")
            if ticket not in state["completed"]:
                grant = state["admissions"].get(ticket)
                if grant is None or grant["ticket"] != ticket:
                    raise ValueError("completion requires this ticket admission")
                if ticket in excluded_scope(data, set(state["quarantine"])):
                    raise ValueError("quarantined work cannot complete")
                state["completed"][ticket] = {
                    "evidence": file_binding(evidence),
                    "reads": receipts,
                    "epoch": state["epoch"],
                }
                if state["admission"] and state["admission"]["ticket"] == ticket:
                    state["admission"] = None
                # A completed writer no longer owns its checkout, paths or resources.
                state["reservations"] = [
                    r for r in state["reservations"] if r["key"] != ticket
                ]
                self._save(state)
            return {
                "completed": ticket,
                "epoch_completed": len(state["completed"]) - state["epoch_start"],
            }

    def review(self, ticket, product, arc, *, impacts=(), unit=None):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            data, receipts = self.lit.read(ticket)
            gate = load_gate(product)
            binding = gate.rw.code_binding(Path(product), gate.FULL_DIFF_REF)
            log = Path(product) / ".harness/merge-gate-log.jsonl"
            if not log.is_file():
                raise ValueError("canonical review history missing")
            rows = gate.fr.read_rows(log)
            key = ticket if unit is None else ticket + "::" + unit
            if state["arc_units"].get(arc, key) != key:
                raise ValueError(
                    "stable review unit cannot be renamed to reset its budget"
                )
            state["arc_units"][arc] = key
            old = state["reviews"].get(key, {})
            reviewed = dict(binding)
            terminal = gate.completing_run(rows, arc)
            transfer = None
            if terminal is not None and terminal.head_sha != binding["head_sha"]:
                landing = importlib.import_module("merge_gate_log")
                delta = landing.landing_delta(
                    terminal.head_sha, binding["head_sha"], Path(product)
                )
                if not delta:
                    reviewed.update(
                        head_sha=terminal.head_sha, diff_digest=terminal.diff_digest
                    )
                    transfer = {
                        "reviewed_head": terminal.head_sha,
                        "final_head": binding["head_sha"],
                        "producer": file_binding(
                            Path(product) / "tools/merge_gate_log.py"
                        ),
                    }
            result = evaluate(
                gate,
                rows,
                arc,
                reviewed["head_sha"],
                reviewed["diff_digest"],
                old.get("observed", []),
                impacts,
            )
            result.update(
                binding=binding,
                arc=arc,
                product=str(Path(product).absolute()),
                gate=file_binding(Path(product) / "tools/review_loop_gate.py"),
                log=file_binding(log),
                reads=receipts,
                landing_transfer=transfer,
                unit=unit,
            )
            state["reviews"][key] = result
            if result["decision"] == "quarantine":
                target = (
                    state["quarantine"] if unit is None else state["unit_quarantine"]
                )
                identifier = ticket if unit is None else key
                if identifier not in target:
                    target.append(identifier)
            self._save(state)
            if result["decision"] == "quarantine":
                self.lit.command(
                    "label",
                    "add",
                    ticket,
                    "review-quarantined" if unit is None else "review-unit-quarantined",
                )
            self.lit.command(
                "comment",
                "add",
                ticket,
                "--body",
                f"TO: Buford (lead orchestrator). FROM: Buford (lead orchestrator), UUID {state['session_id']}. "
                f"Review budget {key}, {arc}: {result['decision']}, {result['completed_passes']}/5 completed passes; "
                f"head {binding['head_sha']}; receipt {self.path}. "
                f"Blocking findings {result['blocking_findings']}; follow-ups {result['followups']}. "
                "Canonical review/CI/landing/installed gates remain required.",
            )
            return {
                k: result[k]
                for k in (
                    "decision",
                    "completed_passes",
                    "admit_review",
                    "next_pass",
                    "blocking_findings",
                    "followups",
                    "binding",
                )
            }

    def reserve(self, record):
        candidate = parse_reservation(record)
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            reasons = conflicts(self._reservations(state), candidate)
            if reasons:
                raise ValueError("reservation-held: " + ",".join(reasons))
            state["reservations"].append(record)
            self._save(state)
            return {"reserved": candidate.key}

    def release(self, key):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            kept = [r for r in state["reservations"] if r["key"] != key]
            if len(kept) == len(state["reservations"]):
                raise ValueError(f"no reservation {key!r} to release")
            state["reservations"] = kept
            self._save(state)
            return {"released": key}

    @staticmethod
    def _writer(state, ticket):
        # [LAW:single-enforcer] Work is admitted only under its recorded writer
        # reservation, so its checkout, paths, resources and reviewer precede use.
        records = [
            r for r in state["reservations"]
            if r["key"] == ticket and r["kind"] == "writer"
        ]
        if not records:
            raise ValueError("reservation-required: reserve the writer before admission")
        return records[0]

    @staticmethod
    def _reservations(state):
        return [parse_reservation(r) for r in state["reservations"]]

    def ownership(self):
        with journal_ownership(self.path) as current:
            return current

    def next(self):
        state = self._read()
        data, receipts = self.lit.read(state["goal_ticket"])
        excluded = excluded_scope(data, set(state["quarantine"]))
        ticket, selection = self.lit.next(data, excluded)
        return {
            "ticket": ticket,
            "excluded": sorted(excluded),
            "reads": receipts,
            "selection_receipt": selection,
        }

    def prepare_clear(self, directory, owned_processes, *, automatic=None):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            for handle in owned_processes:
                if Path(f"/proc/{int(handle['pid'])}").exists():
                    raise ValueError(
                        "owned writer is still active; release before clear"
                    )
            if file_binding(state["handoff"]["path"]) != state["handoff"]:
                raise ValueError("sealed production handoff changed")
            data, reads = self.lit.read(state["goal_ticket"])
            directory = private_directory(directory)
            if (directory / "manifest.json").exists():
                raise ValueError("clear package already sealed")
            nonce = str(uuid.uuid4())
            prepared_at = datetime.now(timezone.utc).isoformat()
            control = self._control()
            memento = (automatic or {}).get("memento")
            outgoing = memento["outgoing"] if memento else None
            # The outgoing lane is the thread the native process actually holds; a
            # routed journal identity that differs is only an inherited predecessor.
            previous = outgoing["thread"] if outgoing else state["session_id"]
            inherited = state["session_id"] if previous != state["session_id"] else None
            provenance = identity(
                outgoing["rollout"]
                if outgoing
                else next(s["transcript"] for s in control["sessions"] if s["role"] == "buford")
            )
            bottle = Bottle(memento["bottle"]).sealed() if memento else None
            atomic_json(
                directory / "frontier.json",
                dict(
                    goal=state["goal_ticket"],
                    production_handoff=state["handoff"],
                    reads=reads,
                    epoch=state["epoch"],
                    completed=list(state["completed"]),
                    quarantine=state["quarantine"],
                    unit_quarantine=state["unit_quarantine"],
                    owned_processes=owned_processes,
                    routing=file_binding(self.control),
                    nonce=nonce,
                    prepared_at=prepared_at,
                    automatic=automatic is not None,
                    startup_limit_percent=15 if automatic is not None else None,
                    native_lane={
                        k: provenance[k] for k in ("cwd", "source", "originator")
                    },
                    **(
                        dict(
                            outgoing=outgoing,
                            inherited_session=inherited,
                            predecessor=memento["predecessor"],
                            log_mark=memento["log_mark"],
                            ceiling=memento["ceiling"],
                            excluded_sessions=sorted(
                                {previous, *([inherited] if inherited else [])}
                                | {s["session_id"] for s in control["sessions"]}
                            ),
                            bottle=bottle,
                        )
                        if memento
                        else {}
                    ),
                ),
            )
            prompt = (
                f"You are Buford, the user-selected {state['model']}/{state['effort']} lead orchestrator. "
                f"BUFORD_CONTEXT_HANDOFF {nonce} {file_binding(directory / 'frontier.json')['sha256']}. "
                "First run lit quickstart, then read root AGENTS.md, context-policy.md and the Buford role. "
                f"Verify {directory}/manifest.json and its frontier bindings. "
                f"Bootstrap with {sys.executable} -m ops.orchestration.loop --state {self.path} "
                f"--control {self.control} bootstrap --transcript <your actual fresh transcript path>. "
                "Verify your actual UUID/model/effort; update only Buford routing through bootstrap. "
                f"Read the bound production handoff {state['handoff']['path']} SHA256 "
                f"{state['handoff']['sha256']}, its checkpoint and immutable evidence manifest. "
                "Preserve the full six-category/nine-arc scope, original deadline and goal accounting. "
                "The existing explicit HIL pause remains until the user explicitly resumes production work. "
                "Use fresh LIT reads at every actionable loop boundary and the durable review/epoch controller. "
                "Do not restart completed gates or clear protected workers. Source GO and review clearance "
                "do not establish installed acceptance. Preserve worktrees, drafts and classifier denials.\n"
            )
            extra = []
            if automatic is not None:
                extra = [
                    file_binding(automatic["continuation"]),
                    file_binding(automatic["goal_receipt"]),
                ]
            path = directory / "resume-prompt.txt"
            if automatic is not None:
                # [DEVICE:negative-examples] Startup is a bounded phase, not a handoff/history audit.
                prompt = (
                    f"TO: Fresh Buford, lead orchestrator. FROM: Outgoing Buford {previous}, lead orchestrator"
                    + (f" (inherited routed predecessor {inherited})" if inherited else "")
                    + ". "
                    f"BUFORD_CONTEXT_HANDOFF {nonce} {file_binding(directory / 'frontier.json')['sha256']}. "
                    f"Retain {state['model']}/{state['effort']} in this same visible lane. Root user-provided AGENTS.md governs. "
                    f"Startup only: run {sys.executable} -m ops.orchestration.startup packet "
                    f"--config {automatic['config']} --manifest {directory}/manifest.json. "
                    "Packet and finish write retained receipts outside the sandbox; request normal sandbox/service approval on the first call when needed. "
                    "A sandbox write refusal does not prove the Mac share is absent. If preflight fails, retain one concise hold; do not read implementation or replay guidance to diagnose startup. "
                    "Read the packet's full current role, context policy and Chat Law. The external supervisor alone bootstraps. "
                    "Do not read history, full handoffs, Code or Prompt Laws, or search directories during startup. "
                    f"Then run {sys.executable} -m ops.orchestration.startup finish --config {automatic['config']}. "
                    "This verifies native usage <=15% of the reported window. Missing metrics or excess context holds work. "
                    "Report role, UUID and pause in at most three lines. "
                    f"Actual workflow begins by running {sys.executable} -m ops.orchestration.loop --state {self.path} --control {self.control} begin {state['goal_ticket']}"
                    + (f" --unit {automatic['workflow_unit']}" if automatic.get('workflow_unit') is not None else '')
                    + (
                        f". Then read and follow the sealed bottle {bottle['path']} sha256 {bottle['sha256']}; "
                        "a changed bottle holds"
                        if bottle
                        else ""
                    )
                    + f". After successful admission, read the bound continuation {automatic['continuation']} "
                    "and full applicable Laws once for its medium. Preserve original scope/deadline, actual goal accounting, "
                    "all review budgets, protected work and independent review/CI/installed gates. "
                    "Standing user permission applies without HIL; a newer direct pause wins. Never replay an uncertain clear or prompt.\n"
                )
            path.write_text(prompt)
            os.chmod(path, 0o600)
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            atomic_json(
                directory / "manifest.json",
                dict(
                    version=1,
                    files=[
                        file_binding(directory / "frontier.json"),
                        file_binding(path),
                        *extra,
                        *([bottle] if bottle else []),
                    ],
                ),
            )
            state["reset"] = {
                "directory": str(directory),
                "manifest": file_binding(directory / "manifest.json"),
                "previous_session": previous,
                **({"inherited_session": inherited} if memento else {}),
            }
            if memento:
                # [LAW:single-enforcer] Workflow admission reads this same sealed bound.
                state["ceiling"] = memento["ceiling"]
            state["admission"] = None
            self._save(state)
            return state["reset"]

    def clear_package(self, reset):
        if (
            reset is None
            or file_binding(reset["manifest"]["path"]) != reset["manifest"]
        ):
            raise ValueError("sealed clear package changed")
        manifest = json.loads(Path(reset["manifest"]["path"]).read_text())
        for bound in manifest["files"]:
            if file_binding(bound["path"]) != bound:
                raise ValueError("sealed clear package evidence changed")
        directory = Path(reset["directory"])
        if any(
            file_binding(directory / name) not in manifest["files"]
            for name in ("frontier.json", "resume-prompt.txt")
        ):
            raise ValueError("sealed package lacks frontier or full prompt")
        frontier = json.loads((directory / "frontier.json").read_text())
        # [LAW:single-enforcer] Released ownership belongs to the sealed package,
        # including delivery after the old goal thread automatically reenters.
        for handle in frontier["owned_processes"]:
            if Path(f"/proc/{int(handle['pid'])}").exists():
                raise ValueError("owned writer remains active")
        return frontier

    def ready_clear(self, transcript):
        state = self.status()
        actual = identity(transcript)
        if (
            state["reset"] is None
            or actual["status"] != "complete"
            or actual["session_id"] != state["reset"]["previous_session"]
            or (actual["model"], actual["effort"]) != (state["model"], state["effort"])
        ):
            raise ValueError(
                "native clear requires an idle matching lane and sealed package"
            )
        reset = state["reset"]
        self.clear_package(reset)
        return {"clear_allowed": True, "reset": reset}

    def bootstrap(self, transcript, *, deadline=None, clock=time.monotonic):
        began = time.monotonic()
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            reset = state["reset"]
            frontier = self.clear_package(reset)
            actual = identity(transcript)
            if (actual["model"], actual["effort"]) != (state["model"], state["effort"]):
                raise ValueError("fresh model/effort mismatch")
            if not actual["session_id"] or actual["session_id"] in (
                reset["previous_session"],
                reset.get("inherited_session"),
            ):
                raise ValueError("native context must have a fresh identity")
            token = f"BUFORD_CONTEXT_HANDOFF {frontier['nonce']} {file_binding(Path(reset['directory']) / 'frontier.json')['sha256']}"
            expected = (Path(reset["directory"]) / "resume-prompt.txt").read_text()
            created = actual["created_at"]
            if (
                not created
                or datetime.fromisoformat(created.replace("Z", "+00:00"))
                < datetime.fromisoformat(frontier["prepared_at"])
                or token not in (actual["first_user"] or "")
                or actual["first_user"] != expected
                or actual["user_count"] != 1
                or {k: actual[k] for k in ("cwd", "source", "originator")}
                != frontier["native_lane"]
                or actual["session_id"]
                in {
                    s["session_id"]
                    for s in self._control()["sessions"]
                    if s["role"] != "buford"
                }
            ):
                raise ValueError(
                    "actual fresh handoff-bound native lane evidence required"
                )
            if state["pending_bootstrap"] not in (None, actual["session_id"]):
                raise ValueError(
                    "bootstrap recovery identity differs from durable intent"
                )
            # [LAW:no-ambient-temporal-coupling] Automatic clear consumed the
            # old idle capability; manual bootstrap still requires that proof.
            if not frontier.get("automatic", False) and state["pending_bootstrap"] is None:
                old_routing = next(
                    s for s in self._control()["sessions"] if s["role"] == "buford"
                )
                self.ready_clear(old_routing["transcript"])
            _, reads = self.lit.read(state["goal_ticket"])
            if (
                time.monotonic() - began > 120
                or deadline is not None
                and clock() > deadline
            ):
                raise ValueError("bootstrap deadline exceeded; remains held")
            control = self._control()
            buford = next(s for s in control["sessions"] if s["role"] == "buford")
            if buford["session_id"] not in (state["session_id"], actual["session_id"]):
                raise ValueError("Buford routing changed by another owner")
            accepted = state.get("native_receipt")
            if accepted is not None:
                history = state.setdefault("native_receipt_history", [])
                history.append(
                    {"receipt": accepted, "acceptance": state["native_acceptance"]}
                )
                state.pop("native_receipt")
                state.pop("native_acceptance")
            state["pending_bootstrap"] = actual["session_id"]
            self._save(state)
            previous = buford["session_id"]
            buford.update(
                session_id=actual["session_id"],
                transcript=str(Path(transcript).absolute()),
            )
            if control.get("notification_thread") == previous:
                control["notification_thread"] = actual["session_id"]
            atomic_json(self.control, control, private=False)
            automatic = frontier.get("automatic", False)
            if automatic:
                state.update(startup_required=True, startup_receipt=None)
            # [LAW:no-ambient-temporal-coupling] Automatic routing is provisional;
            # acknowledgement alone earns the epoch and clears the original reset.
            state.update(admission=None, awaiting_native_receipt=automatic)
            if not automatic:
                state.update(
                    session_id=actual["session_id"],
                    epoch=state["epoch"] + 1,
                    epoch_start=len(state["completed"]),
                    reset=None,
                    pending_bootstrap=None,
                    reset_requested=False,
                )
            state["last_bootstrap"] = {
                "seconds": round(time.monotonic() - began, 3),
                "reads": reads,
                "previous_session": reset["previous_session"],
                "manifest": reset["manifest"],
                "nonce": frontier["nonce"],
                "transcript": str(Path(transcript).absolute()),
                "received_prompt_sha256": hashlib.sha256(expected.encode()).hexdigest(),
            }
            self._save(state)
            return self.status()

    def acknowledge_native_reset(self, receipt, *, deadline=None, clock=time.monotonic):
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            proof = json.loads(Path(receipt).read_text())
            if (
                proof.get("verified") is not False
                or proof.get("status") != "provisional"
                or proof["session_id"] != state["pending_bootstrap"]
                or proof["manifest"] != state["last_bootstrap"]["manifest"]
                or proof["nonce"] != state["last_bootstrap"]["nonce"]
                or proof["seconds"] > 120
                or proof["epoch"] != state["epoch"] + 1
                or state["reset"]["manifest"] != proof["manifest"]
            ):
                raise ValueError("native reset acceptance receipt mismatch")
            if deadline is not None and clock() > deadline:
                raise ValueError("native reset deadline exceeded before acceptance")
            # All evidence is durable before this acceptance decision. A crash
            # before the decision leaves the pending transfer recoverable.
            bound = file_binding(receipt)
            state["pending_native_receipt"] = bound
            self._save(state)
            accepted_at = clock()
            if deadline is not None and accepted_at > deadline:
                raise ValueError("native reset deadline exceeded before acceptance")
            state.update(
                session_id=state["pending_bootstrap"],
                epoch=proof["epoch"],
                epoch_start=len(state["completed"]),
                reset=None,
                reset_requested=False,
                pending_bootstrap=None,
                native_receipt=bound,
                pending_native_receipt=None,
                native_acceptance={"accepted_at": accepted_at, "deadline": deadline},
                awaiting_native_receipt=False,
                maintenance_only=False,
            )
            self._save(state)

    def recover_maintenance(self, authority):
        """Transfer Buford routing without freshness credit or production admission."""
        binding, grant, failed = authority.binding, authority.grant, authority.failed
        with Lease(self.path.with_suffix(".lock")):
            state = self._read()
            control = self._control()
            proof = state.get("maintenance_recovery")
            applied = proof is not None and proof["authority"] == binding
            pending = state.get("pending_maintenance")
            if pending is not None and pending != binding:
                raise ValueError("maintenance recovery intent changed")
            if applied:
                if state["session_id"] != grant["session_id"]:
                    raise ValueError("maintenance recovery identity changed")
            elif pending is None:
                if state != failed or any(
                    file_binding(self.path)[k] != grant["journal"][k]
                    for k in ("sha256", "bytes")
                ):
                    raise ValueError("failed journal changed before recovery")
            elif state != {**failed, "pending_maintenance": binding}:
                raise ValueError("failed journal changed after recovery intent")
            history = [*failed.get("maintenance_recovery_history", [])]
            if failed.get("maintenance_recovery") is not None:
                history.append(failed["maintenance_recovery"])
            recovered = {
                **failed,
                "session_id": grant["session_id"],
                "reset": None,
                "reset_requested": True,
                "admission": None,
                "maintenance_only": True,
                "pending_maintenance": None,
                "pending_bootstrap": None,
                "pending_native_receipt": None,
                "awaiting_native_receipt": False,
                "maintenance_recovery_history": history,
                "maintenance_recovery": {
                    "authority": binding,
                    "failed_reset": failed["reset"],
                },
            }
            frozen_control = json.loads(Path(grant["routing"]["path"]).read_text())
            expected = json.loads(json.dumps(frozen_control))
            buford = next(s for s in expected["sessions"] if s["role"] == "buford")
            if buford["session_id"] not in (
                failed["session_id"],
                failed.get("pending_bootstrap"),
            ):
                raise ValueError("failed Buford routing mismatch")
            previous = buford["session_id"]
            buford.update(
                session_id=grant["session_id"], transcript=grant["transcript"]
            )
            if expected.get("notification_thread") == previous:
                expected["notification_thread"] = grant["session_id"]
            current_authority = grant.get('kind') == 'expired-waiting-title-current-authority'
            if (not control["repair_paused"] and not current_authority) or control not in (
                frozen_control,
                expected,
            ):
                raise ValueError(
                    "maintenance recovery requires unchanged paused protected routing"
                )
            actual = identity(grant["transcript"])
            if (
                grant["maintenance_only"] is not True
                or actual["session_id"] != grant["session_id"]
                or (actual["model"], actual["effort"]) != ("gpt-6.1-sol", "high")
                or grant["session_id"]
                in {
                    s["session_id"]
                    for s in control["sessions"]
                    if s["role"] != "buford"
                }
                or {"count": actual["user_count"], "hash": actual["last_user_hash"]}
                != grant["user_frontier"]
            ):
                raise ValueError(
                    "actual human frontier/Sol/high recovery identity mismatch"
                )
            if applied:
                if control != expected:
                    raise ValueError("recovered Buford routing changed")
                return self.status()
            self.lit.read(state["goal_ticket"])
            if pending is None:
                state["pending_maintenance"] = binding
                self._save(state)
            # [LAW:no-ambient-temporal-coupling] Recovery intent survives a crash
            # between routing and journal publication; counters never change.
            atomic_json(self.control, expected, private=False)
            self._save(recovered)
            return self.status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state", type=Path, default=Path(".local/buford-loop/state.json")
    )
    parser.add_argument(
        "--control", type=Path, default=Path("docs/orchestration/session-control.json")
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--transcript", type=Path, required=True)
    init.add_argument("--handoff", type=Path, required=True)
    init.add_argument("--goal", required=True)
    begin = sub.add_parser("begin")
    begin.add_argument("ticket")
    begin.add_argument("--maintenance", action="store_true")
    begin.add_argument("--headroom-hold", action="store_true")
    begin.add_argument(
        "--unit", help="stable shipping-unit ID under a multi-unit LIT ticket"
    )
    reserve = sub.add_parser("reserve")
    reserve.add_argument(
        "--record", type=Path, required=True,
        help="writer, hold or preserved reservation JSON",
    )
    release = sub.add_parser("release")
    release.add_argument("key")
    check = sub.add_parser("check")
    check.add_argument("admission")
    complete = sub.add_parser("complete")
    complete.add_argument("ticket")
    complete.add_argument("--evidence", type=Path, required=True)
    review = sub.add_parser("review")
    review.add_argument("ticket")
    review.add_argument("--product", type=Path, required=True)
    review.add_argument("--arc", required=True)
    review.add_argument("--impacts", type=Path)
    review.add_argument(
        "--unit", help="stable unit ID when one LIT ticket contains multiple units"
    )
    prepare = sub.add_parser("prepare-clear")
    prepare.add_argument("directory", type=Path)
    prepare.add_argument(
        "--ownership",
        type=Path,
        required=True,
        help="released owner receipt with owned_processes list",
    )
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--transcript", type=Path, required=True)
    ready = sub.add_parser("ready-clear")
    ready.add_argument("--transcript", type=Path, required=True)
    sub.add_parser("status")
    sub.add_parser('finish-startup')
    sub.add_parser("next")
    args = parser.parse_args()
    loop = Loop(args.state, args.control, NativeLit(Path.cwd(), args.artifact_root))
    try:
        if args.command == "init":
            actual = identity(args.transcript)
            if (actual["model"], actual["effort"]) != ("gpt-6.1-sol", "high"):
                raise ValueError("Buford must retain actual user-selected model/effort")
            loop.initialize(
                actual["session_id"],
                actual["model"],
                actual["effort"],
                args.handoff,
                args.goal,
            )
            result = {"initialized": str(args.state)}
        elif args.command == "begin":
            buford = next(
                s for s in loop._control()["sessions"] if s["role"] == "buford"
            )
            actual = identity(buford["transcript"])
            state = loop.status()
            if (actual["session_id"], actual["model"], actual["effort"]) != (
                state["session_id"],
                state["model"],
                state["effort"],
            ):
                raise ValueError("actual Buford identity/model/effort mismatch")
            from .ceiling import Authority, CeilingHold, Measurement, decide
            from .session_context import inspect_transcript

            # [LAW:single-enforcer] Admission headroom is the per-decision Memento bound
            # of this measured lane under the journal's sealed authority, the same one
            # the supervisor enforces; no caller input can move it, and any gap holds.
            try:
                measurement = Measurement.parse(
                    inspect_transcript("codex", buford["transcript"])
                )
                if (measurement.identity.session_id, measurement.identity.model) != (
                    state["session_id"],
                    state["model"],
                ):
                    raise CeilingHold("measured lane is not the journal's Buford")
                decision = decide(
                    measurement,
                    Authority.sealed(state.get("ceiling")).bound(buford, measurement),
                    buford["task_budget"],
                )
            except CeilingHold as error:
                # Undecidable is a hold, not a measured overrun: no reset is requested.
                raise ValueError(f"ceiling-hold: {error}") from error
            fits = decision.admit
            result = loop.begin(
                args.ticket,
                maintenance=args.maintenance,
                headroom=fits and not args.headroom_hold,
                unit=args.unit,
            )
        elif args.command == "reserve":
            result = loop.reserve(json.loads(args.record.read_text()))
        elif args.command == "release":
            result = loop.release(args.key)
        elif args.command == "check":
            result = loop.check(args.admission)
        elif args.command == 'finish-startup':
            result = loop.finish_startup()
        elif args.command == "complete":
            result = loop.complete(args.ticket, args.evidence)
        elif args.command == "review":
            result = loop.review(
                args.ticket,
                args.product,
                args.arc,
                impacts=json.loads(args.impacts.read_text()) if args.impacts else [],
                unit=args.unit,
            )
        elif args.command == "prepare-clear":
            result = loop.prepare_clear(
                args.directory,
                json.loads(args.ownership.read_text())["owned_processes"],
            )
        elif args.command == "bootstrap":
            result = loop.bootstrap(args.transcript)
            result = {
                k: result[k]
                for k in (
                    "session_id",
                    "epoch",
                    "epoch_completed",
                    "production_paused",
                    "last_bootstrap",
                )
            }
        elif args.command == "ready-clear":
            result = loop.ready_clear(args.transcript)
        elif args.command == "next":
            result = loop.next()
        else:
            state = loop.status()
            result = {
                k: state[k]
                for k in (
                    "session_id",
                    "epoch",
                    "epoch_completed",
                    "production_paused",
                    "quarantine",
                    "unit_quarantine",
                    "iteration",
                    "reset",
                )
            }
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, Stop) as error:
        print(json.dumps({"held": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
