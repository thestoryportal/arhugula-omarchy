"""In-memory negative probes for provider authority and gateway cutover."""
import importlib
import io
from pathlib import Path
import sys
import unittest


MUTATIONS = (
    ('runtime.providers.configuration',
     'if approval is None or approval.candidate is not candidate:',
     'if approval is None:',
     'test_swapped_stale_foreign_and_rejected_receipts_deny'),
    ('runtime.providers.configuration',
     'if candidate.baseline != self._state.revision:',
     'if False:',
     'test_competing_commits_have_one_winner'),
    ('runtime.providers.configuration',
     'if type(candidate) is not Candidate or candidate not in self._staged:',
     'if type(candidate) is not Candidate:',
     'test_restart_rejects_old_candidates_receipts_and_observations'),
    ('runtime.providers.configuration',
     'if bootstrap != (len(candidate.evidence) > len(self._baseline())):', 'if False:',
     'test_disabled_configuration_does_not_reenable_with_bootstrap_approval'),
    ('runtime.providers.configuration',
     'or not 0 <= now_ms - observation.observed_at_ms <= policy.health_ttl_ms', '',
     'test_fallback_rechecks_freshness_before_effect'),
    ('runtime.providers.configuration',
     'if not (r.pinned and r.deterministic and r.independently_evaluated',
     'if not (True and r.deterministic and r.independently_evaluated',
     'test_unqualified_replay_flags_never_bootstrap'),
    ('runtime.providers.configuration',
     'if baseline.bundle_digest != proposed.bundle_digest:', 'if False:',
     'test_failed_unbound_or_mismatched_evaluation_cannot_activate'),
    ('runtime.providers.records',
     'if any(value > getattr(ceiling, key) for key, value in totals.items()):',
     'if False:', 'test_policy_and_budget_denials_preserve_active_state'),
    ('runtime.gateway.client',
     'if not permitted or self._disabled or call.cancel_requested:',
     'if self._disabled or call.cancel_requested:',
     'test_expired_primary_has_no_transport_or_fallback_effect'),
    ('runtime.gateway.client',
     'self._host, self._local, self._permit = host, local, permit',
     'self._host, self._local, self._permit = host, local, permit\n            self._history = ReplayHistory()',
     'test_disabled_owner_can_reactivate_with_new_review_without_resetting_replay'),
    ('runtime.providers.configuration',
     'self._gateway.disable(owner=self._token)', 'pass',
     'test_disable_blocks_admission_fallback_and_keeps_cleanup_fault'),
    ('runtime.gateway.client',
     "if self._fault:\n                raise GatewayError(self._fault)",
     "if False:\n                raise GatewayError(self._fault)",
     'test_disable_blocks_admission_fallback_and_keeps_cleanup_fault'),
)


def fresh_module(name):
    for key in tuple(sys.modules):
        if key.startswith(('runtime.providers', 'runtime.gateway',
                           'tests.test_provider', 'tests.test_gateway')):
            parent, _, child = key.rpartition('.')
            package = sys.modules.get(parent)
            if package is not None and hasattr(package, child):
                delattr(package, child)
            del sys.modules[key]
    return importlib.import_module(name)


def run_test(name):
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        'tests.test_provider_configuration.ProviderConfigurationTests.' + name)
    result = unittest.TextTestRunner(stream=output).run(suite)
    if result.testsRun != 1 or result.errors:
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
        expected = 3 if before in ('if candidate.baseline != self._state.revision:',
                                  "if self._fault:\n                raise GatewayError(self._fault)") else 1
        if source.count(before) != expected:
            raise RuntimeError('Mutation anchor changed: ' + before)
        exec(compile(source.replace(before, after), module.__file__, 'exec'), module.__dict__)
        mutated, output = run_test(test_name)
        if mutated.wasSuccessful():
            raise RuntimeError('SURVIVED: ' + before)
        print('DETECTED:', module_name, before, '->', after)
    print(f'{len(MUTATIONS)}/{len(MUTATIONS)} mutations detected; no files changed')


if __name__ == '__main__':
    main()
