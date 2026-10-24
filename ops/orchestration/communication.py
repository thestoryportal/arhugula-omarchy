"""Exact LIT comment publication and pointer-only native queue delivery.

LIT holds the work record; the native queue carries only a pointer to one
verified comment. Every operation has a caller-chosen stable ID, so a retry
reconciles to the one actual comment or enqueue instead of a second assignment.
"""
from dataclasses import dataclass, field, replace
import enum
import hashlib
import json
from pathlib import Path
import re

from .continuation import Lease, Stop
from .records import atomic_json, read_json


LOCK = "communication.lock"
OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,79}")
POINTER_FIELD = re.compile(r"[^|\r\n]{1,160}")


class Reason(enum.Enum):
    """Stable WS-18 guard reason codes; callers branch on these, never on prose."""

    INVALID_INPUT = "invalid_input"
    POLICY_MISMATCH = "policy_mismatch"
    AUTHORITY_CHANGED = "authority_changed"
    AUTHORITY_UNAVAILABLE = "authority_unavailable"
    OWNERSHIP_CONFLICT = "ownership_conflict"
    IDENTITY_MISMATCH = "identity_mismatch"
    HEADROOM_UNKNOWN = "headroom_unknown"
    REFRESH_REQUIRED = "refresh_required"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    PUBLICATION_UNCERTAIN = "publication_uncertain"


class Hold(Stop):
    """The dependent transition must not proceed and must not be replayed blindly."""

    def __init__(self, reason, detail):
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason


class QueueFailed(Exception):
    """The native queue reported it did not enqueue; only delivery may be retried."""


@dataclass(frozen=True)
class VerifiedComment:
    issue: str
    comment_id: str
    body_sha256: str
    operation_id: str
    # Reconciled write faults stay visible without changing which comment this is.
    write_failures: tuple = field(default=(), compare=False)


@dataclass(frozen=True)
class Party:
    name: str
    role: str


@dataclass(frozen=True)
class Recipient(Party):
    session_id: str


@dataclass(frozen=True)
class DeliveryReceipt:
    comment: VerifiedComment
    thread: str
    message_id: str
    text: str
    # "enqueued" until observe_receipt sees the recipient consume the pointer.
    state: str


def _operation(operation_id):
    if not OPERATION_ID.fullmatch(operation_id):
        raise Hold(Reason.INVALID_INPUT, f"operation id {operation_id!r}")
    return operation_id


def _marked(body, operation_id):
    # LIT trims surrounding whitespace, so only a trimmed body round-trips exactly;
    # a body's own operation line would make the marker ambiguous.
    if (
        not body
        or body != body.strip()
        or any(line.startswith("operation:") for line in body.splitlines())
    ):
        raise Hold(Reason.INVALID_INPUT, "comment body must be trimmed, nonempty and free of operation lines")
    return f"{body}\n\noperation: {_operation(operation_id)}"


def _carrying(adapter, issue, marker):
    try:
        comments = adapter.export()["comments"]
        return [c for c in comments if c["issue_id"] == issue and marker in c["body"].splitlines()]
    except Exception as error:
        # [LAW:no-silent-failure] An unreadable or partial export is never "no comment".
        raise Hold(Reason.AUTHORITY_UNAVAILABLE, f"lit export: {error!r}") from error


def _write(adapter, issue, text):
    try:
        adapter.comment(issue, text)
    except Exception as error:
        # The outcome is unknown until the store is read again.
        return f"{type(error).__name__}: {error}"
    return None


def ensure_comment(adapter, issue, operation_id, body, *, ledger):
    """Publish ``body`` on ``issue`` at most once and return the one stored comment."""
    text = _marked(body, operation_id)
    marker = text.rsplit("\n", 1)[1]
    failures = []
    # [LAW:single-enforcer] The shared lease serializes this team's comment writes.
    with Lease(Path(ledger) / LOCK):
        found = _carrying(adapter, issue, marker)
        if not found:
            failure = _write(adapter, issue, text)
            found = _carrying(adapter, issue, marker)
            failures += [failure] if failure else []
            if failure and not found:
                # The failed command has exited and a fresh read shows no comment:
                # non-delivery is proved, which permits exactly one retry. A write
                # that reported success yet is absent is not retried.
                retry = _write(adapter, issue, text)
                found = _carrying(adapter, issue, marker)
                failures += [retry] if retry else []
    if len(found) != 1:
        ids = [c["id"] for c in found]
        raise Hold(Reason.PUBLICATION_UNCERTAIN, f"{issue} operation {operation_id}: comments {ids}; write failures {failures}")
    (comment,) = found
    if comment["body"] != text:
        raise Hold(Reason.INVALID_INPUT, f"operation {operation_id} already names {comment['id']} with a different body")
    return VerifiedComment(issue, comment["id"], hashlib.sha256(text.encode()).hexdigest(), operation_id, tuple(failures))


def _field(value):
    if not POINTER_FIELD.fullmatch(value):
        raise Hold(Reason.INVALID_INPUT, f"pointer field must be one short line without '|': {value[:40]!r}")
    return value


def _stored(adapter, comment):
    """Only the one LIT comment matching every claimed field may be pointed at."""
    # [LAW:parse-dont-validate] A VerifiedComment is a claim any caller can build;
    # the store, reread under the lease, is the proof.
    found = _carrying(adapter, comment.issue, f"operation: {_operation(comment.operation_id)}")
    stored = [(c["id"], hashlib.sha256(c["body"].encode()).hexdigest()) for c in found]
    if stored != [(comment.comment_id, comment.body_sha256)]:
        raise Hold(Reason.INVALID_INPUT, f"{comment.issue} {comment.comment_id} is not the stored comment of operation {comment.operation_id}")


def routed(routing, recipient):
    """The one current routing row for ``recipient``, read at the moment of use."""
    try:
        control = json.loads(Path(routing).read_text())
        paused = control["repair_paused"]
        rows = [s for s in control["sessions"] if s["role"] == recipient.name]
        if type(paused) is not bool:
            raise ValueError("repair_paused must be a boolean")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Hold(Reason.AUTHORITY_UNAVAILABLE, f"routing {routing}: {error!r}") from error
    if paused:
        raise Hold(Reason.AUTHORITY_CHANGED, "repair_paused is set; a pending pointer or assignment cannot resume work")
    if [row["session_id"] for row in rows] != [recipient.session_id]:
        raise Hold(Reason.IDENTITY_MISMATCH, f"{recipient.name} is not routed to {recipient.session_id}")
    return rows[0]


def _admit(routing, recipient):
    """Current routing, read at the moment of delivery, governs a pending pointer."""
    if routed(routing, recipient)["kind"] != "codex":
        raise Hold(Reason.INVALID_INPUT, f"{recipient.name} has no native codex queue")


def _intent(path):
    try:
        return read_json(path)
    except FileNotFoundError:
        return None
    except ValueError as error:
        raise Hold(Reason.PUBLICATION_UNCERTAIN, f"delivery intent {path}: {error}") from error


def deliver_pointer(adapter, queue, recipient, comment, operation_id, *, sender, action, routing, ledger):
    """Enqueue one pointer to ``comment`` through the injected existing native queue.

    ``comment`` is reread from LIT through ``adapter`` and must match exactly one
    stored comment by issue, ID, body hash and operation, or nothing is recorded
    or enqueued.

    ``queue(thread, text)`` returns the native message ID, raises QueueFailed when
    the queue refused, and anything else leaves delivery uncertain. The durable
    intent is written before enqueue, so an interrupted process holds instead of
    replaying a pointer that may already be queued.
    """
    # [LAW:one-source-of-truth] The pointer is derived from the stored comment,
    # never from the task body, so a duplicate task conversation cannot be sent.
    text = " | ".join([
        f"TO {_field(recipient.name)}, {_field(recipient.role)}",
        f"FROM {_field(sender.name)}, {_field(sender.role)}",
        _field(comment.issue),
        _field(comment.comment_id),
        _field(action),
    ])
    path = Path(ledger) / f"{_operation(operation_id)}.json"
    intent = dict(operation_id=operation_id, issue=comment.issue, comment_id=comment.comment_id,
                  body_sha256=comment.body_sha256, thread=recipient.session_id, text=text)
    with Lease(Path(ledger) / LOCK):
        _stored(adapter, comment)
        _admit(routing, recipient)
        prior = _intent(path) or dict(intent, state="comment_verified", queue_failures=[])
        if {key: prior[key] for key in intent} != intent:
            raise Hold(Reason.INVALID_INPUT, f"operation {operation_id} already delivers {prior['comment_id']} to {prior['thread']}")
        if prior["state"] == "enqueued":
            return DeliveryReceipt(comment, prior["thread"], prior["message_id"], text, "enqueued")
        if prior["state"] != "comment_verified":
            raise Hold(Reason.PUBLICATION_UNCERTAIN, f"{path} is {prior['state']}; reconcile from the recipient rollout before any replay")
        atomic_json(path, dict(prior, state="queue_intended"))
        try:
            message_id = queue(recipient.session_id, text)
        except QueueFailed as error:
            atomic_json(path, dict(prior, queue_failures=[*prior["queue_failures"], str(error)]))
            raise
        except Exception as error:
            atomic_json(path, dict(prior, state="delivery_uncertain", queue_failures=[*prior["queue_failures"], repr(error)]))
            raise Hold(Reason.PUBLICATION_UNCERTAIN, f"enqueue outcome unknown for {operation_id}: {error!r}") from error
        atomic_json(path, dict(prior, state="enqueued", message_id=message_id))
    return DeliveryReceipt(comment, recipient.session_id, message_id, text, "enqueued")


def _consumed(line, text):
    payload = json.loads(line).get("payload")
    return (
        isinstance(payload, dict)
        and payload.get("type") == "message"
        and payload.get("role") == "user"
        and [part.get("text") for part in payload.get("content", [])] == [text]
    )


def observe_receipt(receipt, rollout_lines):
    """Enqueue is not receipt: only the recipient consuming the exact pointer is."""
    if any(_consumed(line, receipt.text) for line in rollout_lines):
        return replace(receipt, state="receipt_observed")
    return receipt
