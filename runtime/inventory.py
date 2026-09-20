"""Fixture-backed, read-only capability inventory discovery."""
from dataclasses import dataclass
from types import MappingProxyType


class InventoryError(ValueError):
    """Raised when an inventory fixture cannot form a complete trusted snapshot."""


@dataclass(frozen=True)
class InventoryItem:
    identifier: str
    source: str
    provenance: str
    data: MappingProxyType


@dataclass(frozen=True)
class Inventory:
    capabilities: tuple[InventoryItem, ...]
    state: MappingProxyType
    state_provenance: str


_SOURCES = {
    "omarchy_commands": ("id", "argv"),
    "menus": ("id", "title"),
    "hyprland_bindings": ("id", "keys", "action"),
    "custom_bindings": ("id", "keys", "action"),
    "installed_apps": ("id", "desktop_id"),
}


def _valid_record(source, record):
    required = _SOURCES[source]
    if type(record) is not dict or any(type(record.get(key)) is not str for key in required if key != "argv"):
        return False
    if source == "omarchy_commands":
        argv = record.get("argv")
        return type(argv) is list and bool(argv) and all(type(part) is str and part for part in argv)
    return True


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _json_compatible(value):
    if value is None or type(value) in (str, bool, int, float):
        return True
    if type(value) is list:
        return all(_json_compatible(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_compatible(item) for key, item in value.items())
    return False


def discover(fixture):
    """Return a complete inventory snapshot from a version-one fixture mapping."""
    if type(fixture) is not dict or fixture.get("version") != 1:
        raise InventoryError("unsupported inventory fixture")
    if not _json_compatible(fixture):
        raise InventoryError("inventory fixture must contain JSON-compatible values")
    if set(fixture) != {"version", *_SOURCES, "state"} or type(fixture["state"]) is not dict:
        raise InventoryError("inventory fixture is incomplete")

    items, seen = [], set()
    for source in _SOURCES:
        records = fixture[source]
        if type(records) is not list:
            raise InventoryError(f"{source} must be a list")
        for record in records:
            if not _valid_record(source, record):
                raise InventoryError(f"invalid {source} record")
            identifier = record["id"]
            if identifier in seen:
                raise InventoryError(f"duplicate capability id: {identifier}")
            seen.add(identifier)
            items.append(InventoryItem(identifier, source, f"fixture:{source}", _freeze(record)))

    return Inventory(tuple(sorted(items, key=lambda item: item.identifier)), _freeze(fixture["state"]), "fixture:state")
