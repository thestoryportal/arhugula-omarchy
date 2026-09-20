"""Closed v1 wire contracts. Models supply data, never authorization.

The validator implements only the schema keywords used by our bundled schema;
it is not a general JSON Schema implementation. Codecs are the trust boundary.
"""
from collections.abc import Mapping
from dataclasses import dataclass, fields
from importlib.resources import files
import json
import math
import re
from types import MappingProxyType
from typing import ClassVar


class ContractError(ValueError):
    """Untrusted data did not satisfy the versioned wire contract."""


@dataclass(frozen=True)
class Record:
    version: int
    kind: ClassVar[str]


@dataclass(frozen=True)
class Command(Record):
    kind = "command"
    command_id: str
    correlation_id: str
    capability_id: str
    catalog_version: int
    requested_at_ms: int
    arguments: Mapping
    context: Mapping


@dataclass(frozen=True)
class Error(Record):
    kind = "error"
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class Result(Record):
    kind = "result"
    result_id: str
    command_id: str
    correlation_id: str
    status: str
    output: Mapping
    error: Error | None


@dataclass(frozen=True)
class Event(Record):
    kind = "event"
    event_id: str
    command_id: str
    correlation_id: str
    event_type: str
    timestamp_ms: int
    status: str
    capability_id: str
    catalog_version: int
    policy_revision: int
    duration_ms: float
    context: Mapping
    details: Mapping


@dataclass(frozen=True)
class Capability(Record):
    kind = "capability"
    capability_id: str
    catalog_version: int
    enabled: bool
    risk: str
    arguments: Mapping
    provenance: str


@dataclass(frozen=True)
class Policy(Record):
    kind = "policy"
    policy_id: str
    revision: int
    enabled: bool
    allowed_capabilities: tuple[str, ...]
    confirmation_required: tuple[str, ...]


@dataclass(frozen=True)
class Profile(Record):
    kind = "profile"
    profile_id: str
    policy_id: str
    enabled: bool
    voice_enabled: bool


@dataclass(frozen=True)
class Provider(Record):
    kind = "provider"
    provider_id: str
    placement: str
    model_version: str
    enabled: bool
    health: str
    capabilities: tuple[str, ...]


_TYPES = {cls.kind: cls for cls in (Command, Error, Result, Event, Capability, Policy, Profile, Provider)}
_DEFS = json.loads(files("schemas").joinpath("contracts-v1.json").read_text())["$defs"]


def _json(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json(item)
        return
    raise ContractError("expected finite JSON values and string object keys")


def _validate(value, schema, path="$"):
    if "$ref" in schema:
        return _validate(value, _DEFS[schema["$ref"].split("/")[-1]], path)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                _validate(value, alternative, path)
                return
            except ContractError:
                pass
        raise ContractError(f"{path}: no allowed shape matched")
    kind = schema.get("type")
    valid = {"object": type(value) is dict, "array": type(value) is list,
             "string": type(value) is str, "integer": type(value) is int,
             "number": type(value) in (int, float), "boolean": type(value) is bool,
             "null": value is None}
    if kind and not valid[kind]:
        raise ContractError(f"{path}: expected {kind}")
    if "const" in schema and value != schema["const"]:
        raise ContractError(f"{path}: unsupported constant or version")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"{path}: unsupported value")
    if kind == "object":
        properties = schema.get("properties", {})
        if not set(schema.get("required", ())) <= value.keys():
            raise ContractError(f"{path}: missing required field")
        for key, item in value.items():
            if "propertyNames" in schema:
                _validate(key, schema["propertyNames"], path)
            rule = properties.get(key, schema.get("additionalProperties", True))
            if rule is False:
                raise ContractError(f"{path}: unknown field {key}")
            if isinstance(rule, dict):
                _validate(item, rule, f"{path}.{key}")
    if kind == "array":
        for item in value:
            _validate(item, schema.get("items", {}), path + "[]")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise ContractError(f"{path}: duplicate items")
    if kind == "string":
        if len(value) < schema.get("minLength", 0) or ("pattern" in schema and not re.fullmatch(schema["pattern"], value)):
            raise ContractError(f"{path}: invalid string")
    if kind in ("integer", "number") and value < schema.get("minimum", float("-inf")):
        raise ContractError(f"{path}: below minimum")


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, Record):
        return {"kind": value.kind, **{field.name: _thaw(getattr(value, field.name)) for field in fields(value)}}
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def decode(payload: dict) -> Record:
    """Validate and snapshot a wire object into immutable typed records."""
    try:
        _json(payload)
        if type(payload) is not dict or type(payload.get("kind")) is not str or payload["kind"] not in _TYPES:
            raise ContractError("unknown record kind")
        kind = payload["kind"]
        _validate(payload, _DEFS[kind])
        if kind == "result":
            if payload["status"] in ("blocked", "failed", "uncertain") and payload["error"] is None:
                raise ContractError("unsuccessful result requires an error")
            if payload["status"] == "success" and payload["error"] is not None:
                raise ContractError("successful result cannot carry an error")
        if kind == "event" and ((payload["event_type"] == "command.started") != (payload["status"] == "pending")):
            raise ContractError("event type and status disagree")
        values = {key: _freeze(value) for key, value in payload.items() if key != "kind"}
        if kind == "result" and payload["error"] is not None:
            values["error"] = decode(payload["error"])
        return _TYPES[kind](**values)
    except RecursionError as exc:
        raise ContractError("cyclic or excessively nested data") from exc


def encode(record: Record) -> dict:
    """Return a detached validated JSON object, including for direct constructors."""
    if type(record) not in _TYPES.values():
        raise ContractError("expected a known record")
    try:
        payload = _thaw(record)
        decode(payload)
        return payload
    except RecursionError as exc:
        raise ContractError("cyclic or excessively nested data") from exc


def loads(text: str) -> Record:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ContractError(f"non-finite JSON constant: {value}")

    try:
        return decode(json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant))
    except ContractError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("invalid JSON document") from exc
