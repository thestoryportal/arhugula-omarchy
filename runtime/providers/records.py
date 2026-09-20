"""Closed offline configuration records, with explicit units and no authority."""
from dataclasses import asdict, dataclass, fields
import hashlib
from importlib.resources import files
import json
import re

from runtime.contracts import Provider, decode, encode


class ConfigurationError(ValueError):
    """A fixed configuration denial, never raw input or secrets."""


_SCHEMA = json.loads(files('schemas').joinpath('provider-configuration-v1.json').read_text())


def _check(value, schema):
    """Only the schema vocabulary shipped in this package; not a general validator."""
    if '$ref' in schema:
        if schema['$ref'] == 'contracts-v1.json#/$defs/provider':
            if type(decode(value)) is not Provider:
                raise ConfigurationError('provider')
            return
        return _check(value, _SCHEMA['$defs'][schema['$ref'].split('/')[-1]])
    kind = schema['type']
    expected = {'object': dict, 'array': list, 'integer': int, 'boolean': bool, 'string': str}
    if type(value) is not expected[kind]:
        raise ConfigurationError('shape')
    if 'const' in schema and value != schema['const']:
        raise ConfigurationError('version')
    if 'enum' in schema and value not in schema['enum']:
        raise ConfigurationError('enum')
    if kind == 'object':
        properties = schema['properties']
        if set(value) != set(schema['required']):
            raise ConfigurationError('fields')
        for key, item in value.items():
            _check(item, properties[key])
    if kind == 'array':
        for item in value:
            _check(item, schema['items'])
        if schema.get('uniqueItems') and len(set(value)) != len(value):
            raise ConfigurationError('duplicate')
    if kind == 'integer' and value < schema.get('minimum', 0):
        raise ConfigurationError('number')
    if kind == 'string' and 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
        raise ConfigurationError('digest')


def _parse(raw, name):
    try:
        # [LAW:parse-dont-validate] One bounded, closed input boundary feeds records.
        if len(json.dumps(raw, allow_nan=False)) > 65536:
            raise ConfigurationError('size')
        _check(raw, _SCHEMA['$defs'][name])
    except (TypeError, ValueError, RecursionError, OverflowError):
        raise ConfigurationError('invalid-' + name) from None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Resources:
    ram_bytes: int
    accelerator_bytes: int
    disk_bytes: int
    cpu_millicores: int
    slots: int

    def __post_init__(self):
        _parse(asdict(self), 'resources')


@dataclass(frozen=True)
class Manifest:
    provider: Provider
    artifact_sha256: str
    resources: Resources

    def __post_init__(self):
        if type(self.provider) is not Provider or type(self.resources) is not Resources:
            raise ConfigurationError('manifest')
        object.__setattr__(self, 'provider', decode(encode(self.provider)))
        _parse(self.document(), 'manifest')
        if self.provider.enabled or self.provider.health != 'unavailable':
            raise ConfigurationError('manifest-authority')
        if not self.provider.capabilities or self.resources.slots < 1:
            raise ConfigurationError('manifest-empty')

    def document(self):
        return {'version': 1, 'provider': encode(self.provider),
                'artifact_sha256': self.artifact_sha256, 'resources': asdict(self.resources)}

    @property
    def digest(self):
        return digest(self.document())


@dataclass(frozen=True)
class Policy:
    health_ttl_ms: int
    allow_degraded: bool
    allow_fallback: bool
    updates: str
    shared_memory: tuple[str, ...]
    host_budget: Resources
    vm_budget: Resources

    def __post_init__(self):
        if (type(self.shared_memory) is not tuple or type(self.host_budget) is not Resources
                or type(self.vm_budget) is not Resources):
            raise ConfigurationError('policy')
        _parse(self.document(), 'policy')

    def document(self):
        doc = asdict(self)
        doc['shared_memory'] = list(self.shared_memory)
        return {'version': 1, **doc}

    @property
    def digest(self):
        return digest(self.document())


def parse_manifest(raw):
    _parse(raw, 'manifest')
    return Manifest(decode(raw['provider']), raw['artifact_sha256'], Resources(**raw['resources']))


def parse_policy(raw):
    _parse(raw, 'policy')
    return Policy(raw['health_ttl_ms'], raw['allow_degraded'], raw['allow_fallback'],
                  raw['updates'], tuple(raw['shared_memory']),
                  Resources(**raw['host_budget']), Resources(**raw['vm_budget']))


def check_budgets(manifests, policy):
    """Account resident allocations conservatively; no hardware measurement."""
    if type(policy) is not Policy:
        raise ConfigurationError('policy-required')
    for placement, ceiling in (('host', policy.host_budget), ('vm', policy.vm_budget)):
        group = [m.resources for m in manifests if m.provider.placement == placement]
        totals = {f.name: sum(getattr(r, f.name) for r in group) for f in fields(Resources)}
        # [LAW:one-source-of-truth] Shared allocations debit the named RAM pool.
        if placement in policy.shared_memory:
            totals['ram_bytes'] += totals['accelerator_bytes']
        if any(value > getattr(ceiling, key) for key, value in totals.items()):
            raise ConfigurationError('budget-exceeded')
