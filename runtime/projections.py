"""Read-only rebuildable current-state views of the event journal."""
from dataclasses import dataclass, field
from types import MappingProxyType

from .contracts import Event, Interaction, VoiceObservation


@dataclass(frozen=True)
class Projection:
    cursor: int
    action: MappingProxyType | None
    interaction: MappingProxyType | None
    lane: str | None
    provider: MappingProxyType | None
    active_mode: str | None = None
    muted: bool | None = None
    health: str | None = None
    degraded_capabilities: tuple[str, ...] = ()
    pending: bool = False
    voice_lifecycle: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))


def rebuild(journal):
    """Replay a journal into latest action and interaction state without IO."""
    cursor, action, interaction, lane, provider = 0, None, None, None, None
    active_mode, muted, health, degraded_capabilities, pending = None, None, None, (), False
    voice_lifecycle = {}
    for cursor, item in journal.read():
        if isinstance(item, Event):
            action = MappingProxyType({"status": item.status, "event_type": item.event_type})
            pending = item.status == "pending"
            lane = item.context["lane_id"]
            if item.context["provider_id"] is not None:
                provider = MappingProxyType({"id": item.context["provider_id"],
                                              "model_version": item.context["model_version"],
                                              "status": item.status})
            if isinstance(item.details.get("health"), str):
                health = item.details["health"]
            if isinstance(item.details.get("degraded_capabilities"), (list, tuple)):
                degraded_capabilities = tuple(item.details["degraded_capabilities"])
        elif isinstance(item, Interaction):
            interaction = MappingProxyType({"phase": item.phase})
            if isinstance(item.details.get("mode"), str):
                active_mode = item.details["mode"]
            if isinstance(item.details.get("muted"), bool):
                muted = item.details["muted"]
        elif isinstance(item, VoiceObservation):
            voice_lifecycle[item.session_id] = MappingProxyType({
                "phase": item.phase, "status": item.status, "code": item.code,
            })
    return Projection(cursor, action, interaction, lane, provider, active_mode, muted,
                      health, degraded_capabilities, pending, MappingProxyType(voice_lifecycle))


def is_stale(projection, journal):
    """Return whether journal entries exist beyond a projection's replay cursor."""
    return bool(journal.read(after=projection.cursor))
