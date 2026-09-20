"""Read-only rebuildable current-state views of the event journal."""
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import Event, Interaction


@dataclass(frozen=True)
class Projection:
    cursor: int
    action: MappingProxyType | None
    interaction: MappingProxyType | None
    lane: str | None
    provider: MappingProxyType | None


def rebuild(journal):
    """Replay a journal into latest action and interaction state without IO."""
    cursor, action, interaction, lane, provider = 0, None, None, None, None
    for cursor, item in journal.read():
        if isinstance(item, Event):
            action = MappingProxyType({"status": item.status, "event_type": item.event_type})
            lane = item.context["lane_id"]
            if item.context["provider_id"] is not None:
                provider = MappingProxyType({"id": item.context["provider_id"],
                                              "model_version": item.context["model_version"],
                                              "status": item.status})
        elif isinstance(item, Interaction):
            interaction = MappingProxyType({"phase": item.phase})
    return Projection(cursor, action, interaction, lane, provider)


def is_stale(projection, journal):
    """Return whether journal entries exist beyond a projection's replay cursor."""
    return bool(journal.read(after=projection.cursor))
