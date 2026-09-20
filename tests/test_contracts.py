import json
from pathlib import Path
import unittest

from runtime.contracts import ContractError, decode, encode, loads


def fixtures():
    return json.loads(Path("tests/fixtures/contracts-v1.json").read_text())


class ContractTests(unittest.TestCase):
    def test_all_wire_kinds_roundtrip_to_named_immutable_records(self):
        for payload in fixtures():
            with self.subTest(kind=payload["kind"]):
                record = decode(payload)
                self.assertEqual(type(record).__name__.lower(), payload["kind"])
                self.assertEqual(encode(record), payload)
                self.assertEqual(encode(loads(json.dumps(payload))), payload)
                with self.assertRaises(AttributeError):
                    record.version = 99

    def test_unknown_versions_fields_and_wrong_primitive_types_rejected(self):
        for payload in fixtures():
            for patch in ({"version": 2}, {"version": True}, {"version": "1"},
                          {"unexpected": "field"}, {"kind": "unknown"}):
                with self.subTest(kind=payload["kind"], patch=patch), self.assertRaises(ContractError):
                    decode({**payload, **patch})
            incomplete = dict(payload)
            del incomplete["version"]
            with self.assertRaises(ContractError):
                decode(incomplete)

    def test_invalid_ids_states_and_nested_fields_fail_closed(self):
        command, _, result, event, capability, policy, profile, provider = fixtures()
        for payload in [
            {**command, "command_id": ""},
            {**command, "catalog_version": -1},
            {**command, "arguments": {"number": float("nan")}},
            {**command, "context": {**command["context"], "authority": "model"}},
            {**result, "status": "pending"},
            {**result, "error": None},
            {**event, "duration_ms": True},
            {**capability, "enabled": 1},
            {**capability, "risk": "unknown"},
            {**capability, "arguments": {"name": "shell"}},
            {**policy, "allowed_capabilities": [""]},
            {**profile, "voice_enabled": "true"},
            {**provider, "placement": "internet"},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                decode(payload)

    def test_decode_snapshots_nested_mutable_input(self):
        payload = fixtures()[0]
        record = decode(payload)
        payload["arguments"]["name"] = "changed"
        payload["context"]["source"] = "voice"
        self.assertEqual(record.arguments["name"], "main")
        self.assertEqual(record.context["source"], "test")
        with self.assertRaises(TypeError):
            record.arguments["name"] = "changed"
        wire = encode(record)
        wire["arguments"]["name"] = "changed again"
        self.assertEqual(record.arguments["name"], "main")

    def test_non_json_values_and_duplicate_keys_rejected(self):
        for text in ['{"kind":"command","kind":"error"}', '{"kind":"error","version":NaN}']:
            with self.assertRaises(ContractError):
                loads(text)
        with self.assertRaises(ContractError):
            decode({**fixtures()[0], "arguments": {"object": object()}})

    def test_schema_and_golden_fixture_fields_match(self):
        schema = json.loads(Path("schemas/contracts-v1.json").read_text())
        for payload in fixtures():
            definition = schema["$defs"][payload["kind"]]
            self.assertEqual(set(payload), set(definition["required"]))
            self.assertFalse(definition["additionalProperties"])
