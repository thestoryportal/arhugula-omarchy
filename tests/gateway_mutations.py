"""Offline in-memory negative probes: python -m tests.gateway_mutations.

No source file, schema or Git state is changed. Each probe first runs its real
behavioral test against the original module, then recompiles one changed boundary.
"""
import importlib
import io
from pathlib import Path
import sys
import unittest


MUTATIONS = (
    ('runtime.gateway.admission',
     'hmac.compare_digest(supplied, self._bearer.header().encode())', 'True',
     'tests.test_gateway_wire.GatewayAdmissionTests.test_auth_precedes_parsing_and_rejected_auth_does_not_consume_id'),
    ('runtime.gateway.wire',
     'if any(doc[key] != value for key, value in _envelope(request).items()):', 'if False:',
     'tests.test_gateway_wire.GatewayWireTests.test_response_identity_fields_must_match_exactly'),
    ('runtime.gateway.client',
     'if type(peer) is not str or peer != call.route.endpoint.peer_identity:', 'if False:',
     'tests.test_gateway_client.GatewayClientTests.test_peer_identity_is_checked_before_disclosing_credential_or_request'),
    ('runtime.gateway.client',
     "and value.code in ('unavailable', 'provider_failed', 'timeout')", 'and True',
     'tests.test_gateway_client.GatewayClientTests.test_auth_protocol_and_catalog_failures_never_trigger_local_fallback'),
    ('runtime.gateway.admission', 'if request_id in self._ids:', 'if False:',
     'tests.test_gateway_wire.GatewayAdmissionTests.test_auth_precedes_parsing_and_rejected_auth_does_not_consume_id'),
    ('runtime.gateway.client', 'self._invoke(job.cancel) is True', 'bool(self._invoke(job.cancel))',
     'tests.test_gateway_client.GatewayClientTests.test_unproven_cleanup_latches_closed_and_never_starts_fallback'),
    ('runtime.gateway.client', 'if now >= call.deadline:', 'if False:',
     'tests.test_gateway_client.GatewayClientTests.test_total_deadline_stops_polling_and_forbids_late_success_or_fallback'),
)


def fresh_module(name):
    for key in tuple(sys.modules):
        if key.startswith('runtime.gateway') or key.startswith('tests.test_gateway'):
            del sys.modules[key]
    return importlib.import_module(name)


def run_test(name):
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if result.testsRun != 1:
        raise RuntimeError(output.getvalue())
    for test, _ in result.errors:
        if type(test).__name__ == '_FailedTest':
            raise RuntimeError(output.getvalue())
    return result, output.getvalue()


def main():
    for module_name, before, after, test_name in MUTATIONS:
        fresh_module(module_name)
        baseline, output = run_test(test_name)
        if not baseline.wasSuccessful():
            raise RuntimeError('Baseline failure: ' + output)
        module = fresh_module(module_name)
        source = Path(module.__file__).read_text()
        if source.count(before) != 1:
            raise RuntimeError('Mutation anchor changed: ' + before)
        exec(compile(source.replace(before, after, 1), module.__file__, 'exec'), module.__dict__)
        mutated, output = run_test(test_name)
        if mutated.wasSuccessful():
            raise RuntimeError('SURVIVED: ' + before)
        print('DETECTED:', module_name, before, '->', after)
    print(f'{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected; no files changed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
