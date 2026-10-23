"""Per-decision Memento context ceiling for one measured Codex lane.

The pinned upstream grammar sets the soft threshold; the measured lane sets the bound.
A decision is recomputed from the latest completed request every time and is never
remembered across a changed identity, model or reported window.
"""

from dataclasses import dataclass
import math
from pathlib import Path

from .artifacts import file_binding
from .vendor.memento import ceiling_config as memento


class CeilingHold(ValueError):
    """The ceiling cannot be decided; admission and effects hold."""


@dataclass(frozen=True)
class LaneIdentity:
    session_id: str
    model: str
    window: int


@dataclass(frozen=True)
class Measurement:
    identity: LaneIdentity
    request_input: int
    response_output: int
    status: str
    turns: int

    @property
    def usage(self):
        return self.request_input + self.response_output

    @classmethod
    def parse(cls, summary, expected=None):
        """Bind a session_context Codex summary; any unknown fact holds."""
        # [LAW:parse-dont-validate] Downstream code receives only a complete measurement.
        counts = (
            summary.get("latest_request_input_tokens"),
            summary.get("latest_response_output_tokens"),
            summary.get("reported_context_window_tokens"),
            summary.get("completion_count"),
        )
        if (
            summary.get("kind") != "codex"
            or not isinstance(summary.get("session_id"), str)
            or not isinstance(summary.get("model"), str)
            or summary.get("identity_conflict") is not False
            or summary.get("metric_error") is not None
            or any(type(n) is not int or n < 0 for n in counts)
            or counts[2] == 0
        ):
            raise CeilingHold("lane identity, model, window or usage is unknown")
        identity = LaneIdentity(summary["session_id"], summary["model"], counts[2])
        if expected is not None and identity != expected:
            raise CeilingHold("measured lane identity, model or window changed")
        return cls(identity, counts[0], counts[1], summary["status"], counts[3])


@dataclass(frozen=True)
class Bound:
    identity: LaneIdentity
    ceiling: int
    reserve: int
    close: int
    soft: int
    grace: int

    @property
    def limit(self):
        return self.soft + self.grace

    @classmethod
    def resolve(cls, row, layers, measurement, handoff_reserve=0):
        # C is the lower of the operator ceiling and the lane's own reported window;
        # the reserve only lowers the hard close, never raises capacity.
        ceiling = min(row["ceiling"], measurement.identity.window)
        reserve = max(row["reserve"], handoff_reserve)
        close = ceiling - reserve
        soft = soft_threshold(layers)
        if close <= 0 or not 0 < soft <= close:
            raise CeilingHold(
                f"soft threshold {soft} must be positive and at most hard close {close}"
            )
        # Upstream GRACE is the furthest a session may run past its ceiling; here
        # it is a maximum, capped so the finish band never crosses the hard close.
        grace = min(memento.GRACE, close - soft)
        return cls(measurement.identity, ceiling, reserve, close, soft, grace)


@dataclass(frozen=True)
class Authority:
    """The one ceiling authority: sealed layer bytes plus the handoff reserve.

    The supervisor seals it from its attested config into the reset package, and
    workflow admission reads it back from the journal, so both decide on one bound.
    """

    record: dict

    @classmethod
    def seal(cls, memento_config):
        reserve = memento_config["handoff_reserve"]
        if type(reserve) is not int or reserve < 0:
            raise CeilingHold("handoff reserve must be a non-negative integer")
        layers = [file_binding(p) for p in memento_config["ceiling_layers"]]
        return cls({"layers": layers, "handoff_reserve": reserve})

    @classmethod
    def sealed(cls, record):
        """The journal's sealed authority, refused if absent or its layers changed."""
        # [LAW:parse-dont-validate] Only an unchanged sealed record reaches a decision.
        if record is None:
            raise CeilingHold("no sealed ceiling authority; admission holds")
        try:
            changed = any(file_binding(b["path"]) != b for b in record["layers"])
        except OSError as error:
            raise CeilingHold(f"sealed ceiling layer unreadable: {error}") from None
        if changed:
            raise CeilingHold("sealed ceiling layer changed; admission holds")
        return cls(record)

    def bound(self, row, measurement):
        return Bound.resolve(
            row, [b["path"] for b in self.record["layers"]], measurement,
            self.record["handoff_reserve"],
        )


def soft_threshold(layers):
    """Fold the explicit layer files with the pinned grammar; refusals hold."""
    try:
        written = [w for w in (memento.ceiling_in(Path(p)) for p in layers) if w]
        if not written:
            raise CeilingHold("no Memento ceiling layer is configured")
        soft = memento.folded(written)
    except SystemExit as refusal:
        # [LAW:no-silent-failure] Upstream refuses by exiting; a supervisor turns it
        # into a held decision that names the file instead of a dead process.
        raise CeilingHold(str(refusal.code)) from None
    if soft == math.inf:
        raise CeilingHold("a disabled ceiling is not an admissible bound")
    return soft


def band(tokens, bound):
    if tokens < bound.soft:
        return "under"
    return "finish" if tokens < bound.limit else "close"


INSTRUCTIONS = {
    "under": None,
    "finish": (
        "MEMENTO CEILING: {tokens} tokens reached the {soft} soft threshold of this "
        "lane's {ceiling} bound. Finish the current unit, admit no new work, then "
        "release owned work and write the sealed bottle at that released boundary."
    ),
    "close": (
        "MEMENTO CEILING: {tokens} tokens reached hard close {limit} of this lane's "
        "{ceiling} bound. Admit no new work; close out at the next released boundary "
        "and write the sealed bottle. The external supervisor alone clears."
    ),
}


@dataclass(frozen=True)
class Decision:
    turn: tuple
    band: str
    admit: bool
    reasons: tuple
    instruction: object


def decide(measurement, bound, task_budget, expected=None):
    """One admission and instruction decision for one completed turn."""
    if expected is not None and measurement.identity != expected:
        raise CeilingHold("measured lane identity, model or window changed")
    if measurement.identity != bound.identity:
        raise CeilingHold("bound belongs to another lane measurement")
    position = band(measurement.usage, bound)
    reasons = []
    if position != "under":
        reasons.append("ceiling-" + position)
    if measurement.request_input + task_budget + bound.reserve > bound.ceiling:
        reasons.append("insufficient-headroom")
    text = INSTRUCTIONS[position]
    return Decision(
        turn=(measurement.identity.session_id, measurement.turns),
        band=position,
        admit=not reasons,
        reasons=tuple(reasons),
        instruction=None
        if text is None
        else text.format(
            tokens=measurement.usage,
            soft=bound.soft,
            limit=bound.limit,
            ceiling=bound.ceiling,
        ),
    )
