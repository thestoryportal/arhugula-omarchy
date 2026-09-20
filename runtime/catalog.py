"""Offline inventory catalog and trusted, content-bound review publication.

Discovery strings are data, never executor bindings. This registry is not the
ControlPlane's execution catalog and does not hot-reload or revoke its authority.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import re
import threading

from .inventory import Inventory, InventoryError, InventoryItem, discover


class CatalogError(ValueError):
    """Finite diagnostic code; no inventory payload is disclosed."""


@dataclass(frozen=True)
class CatalogEntry:
    identifier: str
    source: str
    provenance: str
    fingerprint: str
    data: Mapping = field(repr=False)
    reviewed: bool = False


@dataclass(frozen=True)
class CatalogSnapshot:
    version: int
    entries: tuple[CatalogEntry, ...] = field(repr=False)


@dataclass(frozen=True)
class CatalogDiff:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]


@dataclass(frozen=True)
class CatalogCandidate:
    base_version: int
    snapshot: CatalogSnapshot
    diff: CatalogDiff


_SOURCES = ('omarchy_commands', 'menus', 'hyprland_bindings', 'custom_bindings', 'installed_apps')


def _plain(value, budget, depth=0):
    """Snapshot bounded JSON, accepting frozen inventory mappings/sequences."""
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise CatalogError('catalog.size')
    if value is None or type(value) in (str, bool, int):
        if type(value) is str and len(value) > 16384:
            raise CatalogError('catalog.size')
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if len(value) > 4096 or any(type(key) is not str for key in value):
            raise CatalogError('catalog.data')
        return {key: _plain(item, budget, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        if len(value) > 4096:
            raise CatalogError('catalog.size')
        return [_plain(item, budget, depth + 1) for item in value]
    raise CatalogError('catalog.data')


def _entries(inventory):
    if (type(inventory) is not Inventory or type(inventory.capabilities) is not tuple
            or len(inventory.capabilities) > 256):
        raise CatalogError('catalog.inventory')
    fixture = {'version': 1, 'state': {}, **{source: [] for source in _SOURCES}}
    metadata = {}
    for item in inventory.capabilities:
        if (type(item) is not InventoryItem or type(item.identifier) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', item.identifier) is None
                or type(item.source) is not str or item.source not in _SOURCES
                or type(item.provenance) is not str or not item.provenance.strip()
                or len(item.provenance) > 512 or item.identifier in metadata):
            raise CatalogError('catalog.entry')
        data = _plain(item.data, [4096])
        if type(data) is not dict or data.get('id') != item.identifier:
            raise CatalogError('catalog.entry')
        try:
            encoded = json.dumps({'data': data, 'source': item.source, 'provenance': item.provenance},
                                 sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        except (ValueError, OverflowError, UnicodeError) as error:
            raise CatalogError('catalog.data') from error
        if len(encoded) > 16384:
            raise CatalogError('catalog.size')
        fixture[item.source].append(data)
        metadata[item.identifier] = (item.provenance, hashlib.sha256(encoded).hexdigest())
    try:
        frozen = discover(fixture)
    except InventoryError as error:
        raise CatalogError('catalog.inventory') from error
    return tuple(CatalogEntry(item.identifier, item.source, *metadata[item.identifier], item.data)
                 for item in frozen.capabilities)


class CatalogRegistry:
    """Trusted process-local owner. Never expose publish as a model/MCP tool.

    One pending candidate, replaced on successful propose. All added/changed IDs
    require explicit review together; no partial publication or silent promotion.
    Persistent recovery and live executor catalog replacement are separate work.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._current = CatalogSnapshot(1, ())
        self._pending = None

    def _require_version(self, version):
        if type(version) is not int or version != self._current.version:
            raise CatalogError('catalog.stale')

    def snapshot(self, version):
        with self._lock:
            self._require_version(version)
            return self._current

    def propose(self, inventory, *, expected_version):
        # Validate/copy before taking the lock; failed proposals do not consume
        # an existing review. Recheck the revision after potentially slow copying.
        entries = _entries(inventory)
        with self._lock:
            self._require_version(expected_version)
            previous = {entry.identifier: entry for entry in self._current.entries}
            incoming = {entry.identifier: entry for entry in entries}
            common = previous.keys() & incoming.keys()
            changed = tuple(sorted(key for key in common
                                   if previous[key].fingerprint != incoming[key].fingerprint))
            unchanged = tuple(sorted(common - set(changed)))
            diff = CatalogDiff(tuple(sorted(incoming.keys() - previous.keys())), changed,
                               tuple(sorted(previous.keys() - incoming.keys())), unchanged)
            revised = bool(diff.added or diff.changed or diff.removed)
            snapshot = CatalogSnapshot(self._current.version + int(revised), tuple(
                previous[entry.identifier] if entry.identifier in unchanged else entry
                for entry in entries))
            candidate = CatalogCandidate(self._current.version, snapshot, diff)
            self._pending = candidate
            return candidate

    def publish(self, candidate, *, reviewed_ids):
        if (type(reviewed_ids) is not tuple or any(type(key) is not str for key in reviewed_ids)
                or len(set(reviewed_ids)) != len(reviewed_ids)):
            raise CatalogError('catalog.review')
        with self._lock:
            if (type(candidate) is not CatalogCandidate or candidate is not self._pending
                    or candidate.base_version != self._current.version):
                raise CatalogError('catalog.candidate')
            required = set(candidate.diff.added + candidate.diff.changed)
            if set(reviewed_ids) != required:
                raise CatalogError('catalog.review')
            snapshot = CatalogSnapshot(candidate.snapshot.version, tuple(
                replace(entry, reviewed=True) if entry.identifier in required else entry
                for entry in candidate.snapshot.entries))
            self._current = snapshot
            self._pending = None
            return snapshot
