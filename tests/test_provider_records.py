"""Closed provider inputs cannot smuggle authority or ambiguous resource units."""
import copy
import importlib.util
import unittest

from runtime.contracts import encode
from tests.test_gateway_wire import host_provider


def resources(**changes):
    return {'ram_bytes': 100, 'accelerator_bytes': 50, 'disk_bytes': 200,
            'cpu_millicores': 500, 'slots': 1, **changes}


def manifest_doc(**changes):
    return {'version': 1,
            'provider': encode(host_provider(enabled=False, health='unavailable')),
            'artifact_sha256': 'a' * 64, 'resources': resources(), **changes}


def policy_doc(**changes):
    budget = resources(ram_bytes=1024, accelerator_bytes=1024, disk_bytes=4096,
                       cpu_millicores=2000, slots=1)
    return {'version': 1, 'health_ttl_ms': 100, 'allow_degraded': False,
            'allow_fallback': True, 'updates': 'disabled', 'shared_memory': ['host'],
            'host_budget': dict(budget), 'vm_budget': dict(budget), **changes}


class ProviderRecordTests(unittest.TestCase):
    def records(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime.providers'),
                             'provider input boundary must exist')
        from runtime.providers import records
        return records

    def test_manifest_and_policy_snapshot_caller_data(self):
        r = self.records()
        raw = manifest_doc()
        parsed = r.parse_manifest(raw)
        policy = r.parse_policy(policy_doc())
        raw['provider']['capabilities'].clear()
        raw['resources']['ram_bytes'] = 0
        self.assertEqual(parsed.provider.capabilities, ('llm', 'evaluator', 'tts'))
        self.assertEqual(parsed.resources.ram_bytes, 100)
        self.assertEqual(policy.shared_memory, ('host',))
        self.assertFalse(parsed.provider.enabled)

    def test_closed_schema_rejects_invalid_or_authoritative_manifests(self):
        r = self.records()
        for changes in ({'version': 2}, {'artifact_sha256': 'latest'}, {'extra': 1},
                        {'resources': {'ram_mb': 1}},
                        {'resources': resources(ram_bytes=True)},
                        {'resources': resources(cpu_millicores=-1)},
                        {'provider': encode(host_provider())}):
            with self.subTest(changes=changes), self.assertRaises(r.ConfigurationError):
                r.parse_manifest(manifest_doc(**changes))

    def test_explicit_policy_rejects_missing_unknown_and_invalid_inputs(self):
        r = self.records()
        invalid = [None, {}, policy_doc(health_ttl_ms=True), policy_doc(health_ttl_ms=0),
                   policy_doc(allow_degraded=1), policy_doc(updates='automatic'),
                   policy_doc(shared_memory=['host', 'host']),
                   policy_doc(host_budget=resources(slots=-1))]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(r.ConfigurationError):
                r.parse_policy(raw)

    def test_digest_binds_every_manifest_and_policy_input(self):
        r = self.records()
        raw = manifest_doc()
        original = r.parse_manifest(raw).digest
        for altered in (manifest_doc(artifact_sha256='b' * 64),
                        manifest_doc(resources=resources(ram_bytes=101))):
            self.assertNotEqual(r.parse_manifest(altered).digest, original)
        reordered = dict(reversed(list(raw.items())))
        self.assertEqual(r.parse_manifest(reordered).digest, original)
        policy = r.parse_policy(policy_doc()).digest
        self.assertNotEqual(r.parse_policy(policy_doc(health_ttl_ms=101)).digest, policy)

    def test_budget_edges_and_shared_memory_are_explicit(self):
        r = self.records()
        manifest = r.parse_manifest(manifest_doc(resources=resources(ram_bytes=974)))
        r.check_budgets((manifest,), r.parse_policy(policy_doc()))
        too_large = r.parse_manifest(manifest_doc(resources=resources(ram_bytes=975)))
        with self.assertRaisesRegex(r.ConfigurationError, 'budget'):
            r.check_budgets((too_large,), r.parse_policy(policy_doc()))
        r.check_budgets((too_large,), r.parse_policy(policy_doc(shared_memory=[])))
        raw = copy.deepcopy(manifest_doc())
        raw['provider']['provider_id'] = 'other'
        with self.assertRaisesRegex(r.ConfigurationError, 'budget'):
            r.check_budgets((manifest, r.parse_manifest(raw)), r.parse_policy(policy_doc()))
