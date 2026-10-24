"""Assignment packets: the current LIT pointer plus a compact immutable artifact index.

A packet carries pointers, hashes and obligations, never artifact bodies. Bodies
stay complete on disk and are read in hash-verified slices, so a large result
never enters model context whole and a partial read cannot pass for the whole.
Hash lineage identifies bytes; it never certifies meaning, so an independent
reviewer still reads the effective document itself.
"""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
from pathlib import Path
import re

from .communication import Hold, Reason, Recipient, VerifiedComment, routed, stored
from .session_context import admit, inspect_transcript
from .startup import EXCEEDED, UNAVAILABLE, StartupBudgetRejected, receipt


SLICE_LIMIT = 16 * 1024
PROJECTION_LIMIT = 16 * 1024
REVISION = re.compile(r"[0-9a-f]{40}")
OPTIONAL = frozenset({"findings", "dependencies"})
ADOPTION = re.compile(r"adoption: session (\S+) compactions (\d+)")
ADOPTED = re.compile(r"adopted-source: ([0-9a-f]{64}) (\S.*)")

# The existing admit() reasons, mapped to the WS-18 code callers branch on.
CAPACITY = {
    "paused": Reason.AUTHORITY_CHANGED,
    "missing-session-id": Reason.IDENTITY_MISMATCH,
    "session-id-conflict": Reason.IDENTITY_MISMATCH,
    "session-id-mismatch": Reason.IDENTITY_MISMATCH,
    # An unfinished or interrupted turn may still be writing; release is unproved.
    "session-not-complete": Reason.OWNERSHIP_CONFLICT,
    "invalid-ceiling": Reason.INVALID_INPUT,
    "invalid-budget": Reason.INVALID_INPUT,
    "missing-request-metric": Reason.HEADROOM_UNKNOWN,
    "insufficient-headroom": Reason.REFRESH_REQUIRED,
}
STARTUP = {UNAVAILABLE: Reason.HEADROOM_UNKNOWN, EXCEEDED: Reason.REFRESH_REQUIRED}


@dataclass(frozen=True)
class Artifact:
    uri: str
    byte_length: int
    sha256: str
    producer: str
    purpose: str
    policy_version: str
    # Immutable parent edges: the artifacts this one amends or consolidates.
    supersedes: tuple = ()


def index_artifact(path, *, producer, purpose, policy_version, supersedes=()):
    """Bind ``path``'s current bytes; every later read is checked against this hash."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise Hold(Reason.ARTIFACT_UNAVAILABLE, f"{path}: {error!r}") from error
    return Artifact(str(Path(path).resolve()), len(data), hashlib.sha256(data).hexdigest(),
                    producer, purpose, policy_version, tuple(supersedes))


@dataclass(frozen=True)
class EffectiveView:
    document: str
    # The document's ancestors and the document itself, in index precedence order.
    lineage: tuple


@dataclass(frozen=True)
class ArtifactIndex:
    artifacts: tuple

    def __post_init__(self):
        seen = set()
        for artifact in self.artifacts:
            # [LAW:types-are-the-program] Parents precede children, so the lineage is
            # append-only and acyclic by construction.
            unknown = [parent for parent in artifact.supersedes if parent not in seen]
            if artifact.sha256 in seen or unknown:
                raise Hold(Reason.INVALID_INPUT, f"{artifact.uri} is a duplicate or supersedes {unknown} not indexed before it")
            seen.add(artifact.sha256)


def _descendants(index, root):
    reach = {root}
    for artifact in index.artifacts:
        if reach.intersection(artifact.supersedes):
            reach.add(artifact.sha256)
    return reach


def _lineage(index, head):
    reach = {head}
    for artifact in reversed(index.artifacts):
        if artifact.sha256 in reach:
            reach.update(artifact.supersedes)
    return tuple(a.sha256 for a in index.artifacts if a.sha256 in reach)


def effective_views(index):
    """One view per current head; amendments leaving two heads of one original conflict."""
    superseded = {parent for artifact in index.artifacts for parent in artifact.supersedes}
    heads = [a.sha256 for a in index.artifacts if a.sha256 not in superseded]
    for root in (a.sha256 for a in index.artifacts if not a.supersedes):
        current = [head for head in heads if head in _descendants(index, root)]
        if len(current) != 1:
            raise Hold(Reason.OWNERSHIP_CONFLICT, f"amendments of {root} leave current heads {current}; consolidate them before publishing a view")
    return tuple(EffectiveView(head, _lineage(index, head)) for head in heads)


@dataclass(frozen=True)
class Slice:
    sha256: str
    offset: int
    data: bytes


def read_slice(artifact, offset, limit=SLICE_LIMIT):
    if not (0 <= offset <= artifact.byte_length and 0 < limit <= SLICE_LIMIT):
        raise Hold(Reason.INVALID_INPUT, f"slice {offset}+{limit} outside {artifact.byte_length} bytes or over {SLICE_LIMIT}")
    try:
        with open(artifact.uri, "rb") as stream:
            stream.seek(offset)
            return Slice(artifact.sha256, offset, stream.read(limit))
    except OSError as error:
        raise Hold(Reason.ARTIFACT_UNAVAILABLE, f"{artifact.uri}: {error!r}") from error


def assemble(artifact, slices):
    """Return the whole result only from contiguous slices whose bytes match its hash."""
    data = b""
    for piece in slices:
        if piece.sha256 != artifact.sha256 or piece.offset != len(data):
            raise Hold(Reason.INVALID_INPUT, f"slice at {piece.offset} does not continue {len(data)} bytes of {artifact.sha256}")
        data += piece.data
    # [LAW:no-silent-failure] A truncated read can never stand in for a full verdict.
    if len(data) != artifact.byte_length:
        raise Hold(Reason.INVALID_INPUT, f"slices cover {len(data)} of {artifact.byte_length} bytes of {artifact.sha256}")
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise Hold(Reason.ARTIFACT_UNAVAILABLE, f"{artifact.uri} changed since it was indexed")
    return data


@dataclass(frozen=True)
class Finding:
    issue: str
    comment_id: str
    # The artifact version the finding was raised against, superseded or not.
    against: str
    # The verified resolution comment, or None while the finding is open.
    resolved_by: str | None


@dataclass(frozen=True)
class Guidance:
    path: str
    # The first action at which this source must be fully in context.
    medium: str


@dataclass(frozen=True)
class Source:
    """A guidance source bound to the bytes it holds when the packet is built."""

    path: str
    sha256: str
    medium: str


def _bind(guidance):
    try:
        data = Path(guidance.path).read_bytes()
    except OSError as error:
        raise Hold(Reason.ARTIFACT_UNAVAILABLE, f"guidance {guidance.path}: {error!r}") from error
    return Source(guidance.path, hashlib.sha256(data).hexdigest(), guidance.medium)


def adoption_body(session_id, compactions, sources):
    """The LIT record a session publishes after reading ``sources`` ((path, sha256) pairs)."""
    return "\n".join([f"adoption: session {session_id} compactions {compactions}",
                      *(f"adopted-source: {sha} {path}" for path, sha in sorted(sources))])


def _loaded(lit, record, session_id, compactions):
    """Sources the session's own stored adoption record shows still in its context."""
    if record is None:
        return frozenset()
    lines = stored(lit, record)["body"].splitlines()
    headers = [match for match in map(ADOPTION.fullmatch, lines) if match]
    if [match[1] for match in headers] != [session_id]:
        raise Hold(Reason.IDENTITY_MISMATCH, f"adoption {record.comment_id} is not one record of {session_id}")
    if int(headers[0][2]) != compactions:
        # A compaction since adoption may have dropped any source from context.
        return frozenset()
    return frozenset((match[2], match[1]) for match in map(ADOPTED.fullmatch, lines) if match)


@dataclass(frozen=True)
class Admitted:
    recipient: Recipient
    model: str
    effort: str
    capacity: dict
    startup: dict
    # The session's stored adoption record, or None before it has read any guidance.
    adoption: VerifiedComment | None
    # (path, sha256) sources still present in this session's context.
    loaded: frozenset


def _selected(profiles, name):
    try:
        profile = json.loads(Path(profiles).read_text())["roles"][name]
        return profile["client"], profile["model"], profile["effort"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Hold(Reason.AUTHORITY_UNAVAILABLE, f"launch profile {name} in {profiles}: {error!r}") from error


def admit_recipient(recipient, *, routing, profiles, ceiling, startup, adoption, lit):
    """Admit the routed session only from its own measured native facts.

    ``ceiling`` is the effective Memento setting. ``startup`` is the report
    recorded once when this session finished startup.budget(). ``adoption`` is
    the session's published adoption_body() comment, or None if it has none.
    """
    row = routed(routing, recipient)
    selected = _selected(profiles, recipient.name)
    if ceiling != row["ceiling"]:
        raise Hold(Reason.POLICY_MISMATCH, f"effective ceiling {ceiling} differs from routed {row['ceiling']}")
    try:
        summary = inspect_transcript(row["kind"], row["transcript"])
    except (OSError, ValueError) as error:
        raise Hold(Reason.HEADROOM_UNKNOWN, f"{row['transcript']}: {error!r}") from error
    # [LAW:single-enforcer] The existing measured admit stays the one capacity
    # decision; routed() has already enforced the pause.
    capacity = admit(summary, task_budget=row["task_budget"], reserve=row["reserve"],
                     ceiling=ceiling, expected_session_id=recipient.session_id)
    if capacity["reasons"]:
        raise Hold(CAPACITY[capacity["reasons"][0]], f"{recipient.session_id}: {capacity}")
    actual = (row["kind"], summary["model"], summary["effort"])
    if actual != selected:
        raise Hold(Reason.IDENTITY_MISMATCH, f"{recipient.session_id} runs {actual}, not the selected {selected}")
    if startup.get("session_id") != recipient.session_id:
        raise Hold(Reason.IDENTITY_MISMATCH, f"startup receipt is not of {recipient.session_id}")
    try:
        # [LAW:single-enforcer] startup.py owns the 15-percent rule for recorded reports too.
        receipt(startup, recipient.session_id)
    except StartupBudgetRejected as error:
        raise Hold(STARTUP[error.report["reason"]], f"startup receipt: {error.report}") from error
    if startup["context_window_tokens"] != summary["reported_context_window_tokens"]:
        raise Hold(Reason.HEADROOM_UNKNOWN, f"startup window {startup['context_window_tokens']} is not the native window")
    loaded = _loaded(lit, adoption, recipient.session_id, summary["compaction_count"])
    return Admitted(recipient, summary["model"], summary["effort"], capacity, startup, adoption, loaded)


@dataclass(frozen=True)
class Assignment:
    goal: str
    unit: str
    pointer: VerifiedComment
    recipient: Admitted
    baseline: str
    # Paths and resources this unit may change.
    owned: tuple
    deliverables: tuple
    acceptance: tuple
    constraints: tuple
    guidance: tuple
    # Every material finding, open or resolved, whatever version it was raised against.
    findings: tuple
    verification: tuple
    evidence: str
    dependencies: tuple
    stop: str

    def __post_init__(self):
        # [LAW:parse-dont-validate] Constructing an Assignment is the dispatch check;
        # an instance cannot lack required context.
        missing = [f.name for f in fields(self) if f.name not in OPTIONAL and not getattr(self, f.name)]
        if missing:
            raise Hold(Reason.INVALID_INPUT, f"assignment lacks required {missing}")
        if not REVISION.fullmatch(self.baseline):
            raise Hold(Reason.INVALID_INPUT, f"baseline {self.baseline!r} is not an exact revision")
        if self.pointer.issue != self.unit:
            raise Hold(Reason.INVALID_INPUT, f"pointer {self.pointer.comment_id} is on {self.pointer.issue}, not {self.unit}")


@dataclass(frozen=True)
class AssignmentPacket:
    assignment: Assignment
    artifacts: ArtifactIndex
    views: tuple
    # Sources this session has not loaded at their current bytes.
    reads: tuple
    # The bounded model projection: pointers and obligations only.
    text: str


def build_packet(assignment, artifacts, *, lit):
    """Publish only a packet whose pointer is the stored LIT comment it claims."""
    stored(lit, assignment.pointer)
    known = {artifact.sha256 for artifact in artifacts.artifacts}
    stray = [finding.comment_id for finding in assignment.findings if finding.against not in known]
    if stray:
        raise Hold(Reason.INVALID_INPUT, f"findings {stray} name no indexed artifact")
    views = effective_views(artifacts)
    recipient = assignment.recipient
    # [LAW:one-source-of-truth] The file's current bytes, not a recorded hash, decide
    # whether the session already holds this source.
    sources = tuple(_bind(g) for g in assignment.guidance)
    reads = tuple(s for s in sources if (s.path, s.sha256) not in recipient.loaded)
    text = json.dumps(dict(
        unit=assignment.unit,
        goal=assignment.goal,
        pointer=dict(issue=assignment.pointer.issue, comment_id=assignment.pointer.comment_id,
                     body_sha256=assignment.pointer.body_sha256),
        recipient=dict(asdict(recipient.recipient), model=recipient.model, effort=recipient.effort,
                       remaining_tokens=recipient.capacity["remaining_tokens"],
                       adoption=recipient.adoption and recipient.adoption.comment_id),
        **{name: getattr(assignment, name) for name in (
            "baseline", "owned", "deliverables", "acceptance", "constraints",
            "verification", "evidence", "dependencies", "stop")},
        guidance=[dict(asdict(s), loaded=s not in reads) for s in sources],
        artifacts=[asdict(artifact) for artifact in artifacts.artifacts],
        views=[asdict(view) for view in views],
        findings=[asdict(finding) for finding in assignment.findings],
    ))
    size = len(text.encode())
    if size > PROJECTION_LIMIT:
        # [LAW:no-silent-failure] Refuse rather than truncate: move bulk into an indexed artifact.
        raise Hold(Reason.INVALID_INPUT, f"projection is {size} bytes, over {PROJECTION_LIMIT}")
    return AssignmentPacket(assignment, artifacts, views, reads, text)
