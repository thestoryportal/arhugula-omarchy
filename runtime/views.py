"""Sensitivity-safe read-only views over runtime projections."""


def compact(projection):
    """Return current operational state without diagnostic payloads."""
    return {
        "cursor": projection.cursor,
        "lane": projection.lane,
        "action_status": None if projection.action is None else projection.action["status"],
        "interaction_phase": None if projection.interaction is None else projection.interaction["phase"],
        "provider_status": None if projection.provider is None else projection.provider["status"],
    }
