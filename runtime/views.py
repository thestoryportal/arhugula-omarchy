"""Sensitivity-safe read-only views over runtime projections."""
from collections.abc import Mapping


def _detach(value):
    """Copy JSON-like journal values, including immutable mapping proxies."""
    if isinstance(value, Mapping):
        return {key: _detach(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_detach(item) for item in value]
    return value


def compact(projection):
    """Return current operational state without diagnostic payloads."""
    return {
        "cursor": projection.cursor,
        "lane": projection.lane,
        "action_status": None if projection.action is None else projection.action["status"],
        "interaction_phase": None if projection.interaction is None else projection.interaction["phase"],
        "provider_status": None if projection.provider is None else projection.provider["status"],
        "active_mode": projection.active_mode,
        "muted": projection.muted,
        "health": projection.health,
        "degraded_capabilities": list(projection.degraded_capabilities),
        "pending": projection.pending,
    }


def detailed(projection, diagnostics, *, include_sensitive=False):
    """Return expanded review diagnostics, hiding private entries by default.

    Each diagnostic is a mapping with ``category``, ``value``, and
    ``sensitivity``. Only ``public`` diagnostics are visible by default;
    sensitivity is an access control input, never returned in the payload.
    """
    visible = []
    for diagnostic in diagnostics:
        sensitivity = diagnostic.get("sensitivity")
        if sensitivity != "public" and not (sensitivity == "private" and include_sensitive):
            continue
        visible.append({"category": diagnostic["category"],
                        "value": _detach(diagnostic["value"])})
    return {"state": compact(projection), "diagnostics": visible}
