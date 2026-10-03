"""Trusted configuration drives real gateway behavior over offline fake effects."""
from dataclasses import replace
import importlib.util
import threading
import unittest

from runtime.contracts import encode
from runtime.evaluation import ReplayRun
from runtime.gateway.client import GatewayClient, GatewayError, HttpReply, Success, Degraded
from runtime.providers.records import ConfigurationError, parse_manifest, parse_policy
from tests import test_gateway_client as fixtures
from tests.test_gateway_wire import host_provider, response_doc, wire
from tests.test_provider_records import manifest_doc, policy_doc, resources


class ProviderConfigurationTests(unittest.TestCase):
    local_begin = fixtures.GatewayClientTests.local_begin
    host_reply = fixtures.GatewayClientTests.host_reply

    def setUp(self):
        fixtures.GatewayClientTests.setUp(self)
        self.assertIsNotNone(importlib.util.find_spec('runtime.providers.configuration'),
                             'trusted configuration owner must exist')
        from runtime.providers.configuration import Configuration, Evidence
        self.Configuration, self.Evidence = Configuration, Evidence
        self.owner = Configuration(self.client)
        self.policy = parse_policy(policy_doc())

    def candidate(self, version='m1', *, policy=None, fallback=False, outcomes=None,
                  bundle='b' * 64, run_version=None, artifact='a' * 64):
        manifest = parse_manifest(manifest_doc(
            provider=encode(host_provider(model_version=version, enabled=False, health='unavailable')),
            artifact_sha256=artifact))
        host = replace(self.host, provider=replace(self.provider, model_version=version))
        manifests, runs = [manifest], []
        local = None
        if fallback:
            manifests.append(parse_manifest(manifest_doc(
                provider=encode(host_provider(provider_id='vm', placement='vm',
                                               enabled=False, health='unavailable')))))
            local = self.local
        for m in manifests:
            run = ReplayRun(run_version or m.provider.model_version, 'synthetic', 'suite-1',
                            True, True, True, {'safe': 'pass'} if outcomes is None else outcomes, True)
            runs.append(self.Evidence(m.digest, bundle, run, ('independent-1',)))
        return self.owner.stage(manifests[0], host, policy=self.policy if policy is None else policy,
                                evidence=tuple(runs), local_manifest=manifests[-1] if fallback else None,
                                local=local)

    def observe(self, candidate, at=1000, status='healthy'):
        for manifest in candidate.manifests:
            self.owner.observe(candidate, manifest.provider.provider_id,
                               status=status, observed_at_ms=at)

    def bootstrap(self, **kwargs):
        candidate = self.candidate(**kwargs)
        self.observe(candidate)
        receipt = self.owner.approve_bootstrap(candidate)
        self.owner.activate(candidate, receipt, now_ms=1000)
        return candidate

    def test_bootstrap_needs_distinct_local_receipt_and_has_no_effects(self):
        candidate = self.candidate()
        self.observe(candidate)
        before = self.owner.state
        with self.assertRaisesRegex(ConfigurationError, 'approval'):
            self.owner.activate(candidate, object(), now_ms=1000)
        with self.assertRaisesRegex(ConfigurationError, 'bootstrap'):
            self.owner.approve(candidate)
        self.assertEqual(self.owner.state, before)
        self.assertEqual(self.transport.sent, [])
        receipt = self.owner.approve_bootstrap(candidate)
        state = self.owner.activate(candidate, receipt, now_ms=1000)
        self.assertEqual(state.revision, 1)
        self.host_reply()
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)

    def test_activation_and_rollback_advance_revision(self):
        first = self.bootstrap()
        second = self.candidate('m2')
        self.observe(second)
        self.owner.activate(second, self.owner.approve(second), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 2)
        restored = self.owner.restore(1, evidence=first.evidence)
        self.observe(restored)
        self.owner.activate(restored, self.owner.approve(restored), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 3)
        self.assertEqual(self.owner.state.candidate.manifests[0].provider.model_version, 'm1')
        self.assertEqual(self.transport.sent, [])

    def test_swapped_stale_foreign_and_rejected_receipts_deny(self):
        first, swapped = self.candidate(), self.candidate(artifact='c' * 64)
        self.observe(first)
        self.observe(swapped)
        receipt = self.owner.approve_bootstrap(first)
        with self.assertRaisesRegex(ConfigurationError, 'approval'):
            self.owner.activate(swapped, receipt, now_ms=1000)
        self.owner.activate(first, receipt, now_ms=1000)
        before = self.owner.state
        with self.assertRaises(ConfigurationError):
            self.owner.activate(first, receipt, now_ms=1000)
        with self.assertRaises(ConfigurationError):
            self.owner.activate(swapped, receipt, now_ms=1000)
        rejected = self.candidate('m2')
        rejected_receipt = self.owner.approve(rejected)
        self.owner.reject(rejected)
        with self.assertRaises(ConfigurationError):
            self.owner.activate(rejected, rejected_receipt, now_ms=1000)
        self.assertEqual(self.owner.state, before)

    def test_failed_unbound_or_mismatched_evaluation_cannot_activate(self):
        bad = self.candidate(outcomes={'safe': 'fail'})
        self.observe(bad)
        with self.assertRaisesRegex(ConfigurationError, 'evaluation'):
            self.owner.activate(bad, self.owner.approve_bootstrap(bad), now_ms=1000)
        with self.assertRaisesRegex(ConfigurationError, 'evidence'):
            self.candidate(run_version='not-this-model')
        self.bootstrap()
        mismatched = self.candidate('m2', bundle='c' * 64)
        self.observe(mismatched)
        with self.assertRaisesRegex(ConfigurationError, 'bundle'):
            self.owner.activate(mismatched, self.owner.approve(mismatched), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 1)

    def test_health_missing_future_expired_and_degraded_deny_without_consuming_receipt(self):
        candidate = self.candidate()
        receipt = self.owner.approve_bootstrap(candidate)
        for status, observed, now in ((None, None, 1000), ('healthy', 1001, 1000),
                                      ('healthy', 1001, 1102), ('degraded', 1102, 1102)):
            if status:
                self.observe(candidate, observed, status)
            with self.assertRaisesRegex(ConfigurationError, 'health'):
                self.owner.activate(candidate, receipt, now_ms=now)
            self.assertEqual(self.owner.state.revision, 0)
        self.observe(candidate, 1102)
        self.owner.activate(candidate, receipt, now_ms=1102)
        self.assertEqual(self.owner.state.revision, 1)

    def test_policy_and_budget_denials_preserve_active_state(self):
        self.bootstrap()
        raw = policy_doc(host_budget=resources(ram_bytes=149))
        candidate = self.candidate('m2', policy=parse_policy(raw))
        self.observe(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'budget'):
            self.owner.activate(candidate, self.owner.approve(candidate), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 1)
        with self.assertRaisesRegex(ConfigurationError, 'policy'):
            self.owner.stage(candidate.manifests[0], candidate.host, policy=None,
                             evidence=candidate.evidence)

    def test_fallback_rechecks_freshness_before_effect(self):
        candidate = self.bootstrap(fallback=True)
        self.owner.observe(candidate, 'host', status='healthy', observed_at_ms=1050)
        self.clock.now = 1050
        self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
        self.client.start(self.request)
        self.clock.now = 1101
        result = self.client.poll()
        self.assertEqual(self.local_calls, [])
        self.assertEqual([f.code for f in result.failures], ['unavailable', 'canceled'])

    def test_eligible_fallback_retains_primary_provenance(self):
        self.bootstrap(fallback=True)
        self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
        self.client.start(self.request)
        self.assertIsNone(self.client.poll())
        self.local_job.reply = wire(response_doc(self.local_calls[0][0]))
        result = self.client.poll()
        self.assertIsInstance(result, Degraded)
        self.assertEqual((result.primary.code, result.result.provider_id), ('unavailable', 'vm'))

    def test_disable_blocks_admission_fallback_and_keeps_cleanup_fault(self):
        self.bootstrap(fallback=True)
        self.transport.job.cleanup = False
        self.client.start(self.request)
        self.owner.disable()
        self.assertEqual(self.owner.state.revision, 2)
        self.assertEqual(self.transport.job.cancels, 1)
        self.assertEqual(self.client.poll().failures[-1].code, 'cleanup')
        self.assertEqual(self.local_calls, [])
        with self.assertRaises(GatewayError):
            self.client.start(replace(self.request, request_id='new'))
        candidate = self.candidate('m2', fallback=True)
        self.observe(candidate)
        with self.assertRaisesRegex(GatewayError, 'cleanup'):
            self.owner.activate(candidate, self.owner.approve(candidate), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 2)

    def test_busy_cutover_preserves_receipt_and_pinned_call(self):
        self.bootstrap()
        candidate = self.candidate('m2')
        self.observe(candidate)
        receipt = self.owner.approve(candidate)
        self.host_reply()
        self.client.start(self.request)
        with self.assertRaisesRegex(GatewayError, 'busy'):
            self.owner.activate(candidate, receipt, now_ms=1000)
        self.assertEqual(self.owner.state.revision, 1)
        self.assertEqual(self.client.poll().model_version, 'm1')
        self.owner.activate(candidate, receipt, now_ms=1000)
        self.assertEqual(self.owner.state.revision, 2)

    def test_competing_commits_have_one_winner(self):
        self.bootstrap()
        candidates = [self.candidate('m2'), self.candidate('m3')]
        for candidate in candidates:
            self.observe(candidate)
        receipts = [self.owner.approve(c) for c in candidates]
        results = []
        barrier = threading.Barrier(3)

        def publish(c, r):
            barrier.wait()
            try:
                results.append(self.owner.activate(c, r, now_ms=1000).revision)
            except ConfigurationError:
                results.append('stale')

        workers = [threading.Thread(target=publish, args=pair) for pair in zip(candidates, receipts)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertCountEqual(results, [2, 'stale'])

    def test_restart_rejects_old_candidates_receipts_and_observations(self):
        old = self.candidate()
        self.observe(old)
        receipt = self.owner.approve_bootstrap(old)
        fresh_client = GatewayClient(self.host, 7, self.clock, self.local)
        fresh = self.Configuration(fresh_client)
        with self.assertRaises(ConfigurationError):
            fresh.activate(old, receipt, now_ms=1000)
        with self.assertRaises(ConfigurationError):
            fresh.observe(old, 'host', status='healthy', observed_at_ms=1000)
        with self.assertRaisesRegex(GatewayError, 'canceled'):
            fresh_client.start(self.request)
        self.assertEqual(fresh.state.revision, 0)
        with self.assertRaisesRegex(GatewayError, 'busy'):
            self.Configuration(self.client)

    def test_disable_before_first_activation_still_requires_explicit_bootstrap(self):
        self.owner.disable()
        candidate = self.candidate()
        self.observe(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'bootstrap'):
            self.owner.approve(candidate)
        receipt = self.owner.approve_bootstrap(candidate)
        self.owner.activate(candidate, receipt, now_ms=1000)
        self.assertEqual(self.owner.state.revision, 2)

    def test_reject_is_for_staged_changes_and_cannot_revoke_active_observation_handle(self):
        active = self.bootstrap()
        with self.assertRaisesRegex(ConfigurationError, 'stale'):
            self.owner.reject(active)
        self.observe(active, at=1001)
        self.assertEqual(self.owner.state.revision, 1)

    def test_expired_primary_has_no_transport_or_fallback_effect(self):
        self.bootstrap(fallback=True)
        self.clock.now = 1101
        self.client.start(self.request)
        self.assertEqual(self.transport.sent, [])
        self.assertEqual(self.local_calls, [])
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')

    def test_regressing_observation_and_cross_call_clock_fail_closed(self):
        candidate = self.bootstrap()
        with self.assertRaisesRegex(ConfigurationError, 'health-regression'):
            self.observe(candidate, 999)
        self.clock.now = 999
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.clock.now = 1001
        self.client.start(replace(self.request, request_id='later'))
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.assertEqual(self.transport.sent, [])

    def test_capability_or_route_substitution_cannot_bind(self):
        candidate = self.candidate()
        for host in (replace(candidate.host, provider=replace(self.provider, provider_id='other')),
                     replace(candidate.host, endpoint=fixtures.Endpoint('https://other.test/v1/gateway', fixtures.PEER))):
            if host.provider.provider_id == 'other':
                with self.assertRaisesRegex(ConfigurationError, 'route-binding'):
                    self.owner.stage(candidate.manifests[0], host, policy=self.policy,
                                     evidence=candidate.evidence)
            else:
                changed = self.owner.stage(candidate.manifests[0], host, policy=self.policy,
                                           evidence=candidate.evidence)
                self.observe(candidate)
                with self.assertRaisesRegex(ConfigurationError, 'approval'):
                    self.owner.activate(changed, self.owner.approve_bootstrap(candidate), now_ms=1000)

    def test_fallback_requires_explicit_policy_and_its_own_evidence(self):
        with self.assertRaisesRegex(ConfigurationError, 'fallback-policy'):
            self.candidate(fallback=True, policy=parse_policy(policy_doc(allow_fallback=False)))
        candidate = self.candidate(fallback=True)
        with self.assertRaisesRegex(ConfigurationError, 'evidence'):
            self.owner.stage(candidate.manifests[0], candidate.host, policy=self.policy,
                             evidence=candidate.evidence[:1], local_manifest=candidate.manifests[1],
                             local=candidate.local)

    def test_unqualified_replay_flags_never_bootstrap(self):
        candidate = self.candidate()
        for flag in ('pinned', 'deterministic', 'independently_evaluated', 'evaluator_consensus'):
            evidence = replace(candidate.evidence[0], run=replace(
                candidate.evidence[0].run, outcomes={'safe': 'pass'}, **{flag: False}))
            bad = self.owner.stage(candidate.manifests[0], candidate.host, policy=self.policy,
                                   evidence=(evidence,))
            self.observe(bad)
            with self.assertRaisesRegex(ConfigurationError, 'evaluation'):
                self.owner.activate(bad, self.owner.approve_bootstrap(bad), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 0)

    def test_review_and_commit_cannot_reenter_from_transport_callback(self):
        self.bootstrap()
        candidate = self.candidate('m2')
        self.observe(candidate)
        receipt = self.owner.approve(candidate)
        denied = []

        def callback():
            try:
                self.owner.activate(candidate, receipt, now_ms=1000)
            except GatewayError as error:
                denied.append(error.code)

        self.transport.on_begin = callback
        self.host_reply()
        self.client.start(self.request)
        self.assertEqual(denied, ['busy'])
        self.assertEqual(self.client.poll().model_version, 'm1')
        self.assertEqual(self.owner.state.revision, 1)

    def test_disabled_owner_can_reactivate_with_new_review_without_resetting_replay(self):
        first = self.bootstrap()
        self.host_reply()
        self.client.start(self.request)
        self.client.poll()
        self.owner.disable()
        restored = self.owner.restore(1, evidence=first.evidence)
        self.observe(restored)
        self.owner.activate(restored, self.owner.approve(restored), now_ms=1000)
        with self.assertRaisesRegex(GatewayError, 'replay'):
            self.client.start(self.request)
        self.assertEqual(self.owner.state.revision, 3)

    def test_changed_route_serves_approved_version_without_changing_old_transport(self):
        self.bootstrap()
        candidate = self.candidate('m2')
        transport = fixtures.Transport(fixtures.Admission(candidate.host.provider, 7, self.bearer))
        changed = self.owner.stage(candidate.manifests[0], replace(candidate.host, transport=transport),
                                   policy=self.policy, evidence=candidate.evidence)
        self.observe(changed)
        self.owner.activate(changed, self.owner.approve(changed), now_ms=1000)
        req = replace(self.request, request_id='m2-call', model_version='m2')
        transport.job.reply = HttpReply(200, wire(response_doc(req)), fixtures.PEER)
        self.client.start(req)
        result = self.client.poll()
        self.assertEqual(result.model_version, 'm2')
        self.assertEqual(transport.last.model_version, 'm2')
        self.assertEqual(self.transport.sent, [])

    def test_record_copy_cannot_impersonate_owned_candidate(self):
        candidate = self.candidate()
        forged = replace(candidate)
        receipt = self.owner.approve_bootstrap(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'candidate-owner'):
            self.owner.activate(forged, receipt, now_ms=1000)
        with self.assertRaisesRegex(ConfigurationError, 'candidate-owner'):
            self.owner.approve_bootstrap(forged)

    def test_explicit_degraded_policy_permits_configured_health(self):
        candidate = self.candidate(policy=parse_policy(policy_doc(allow_degraded=True)))
        self.observe(candidate, status='degraded')
        self.owner.activate(candidate, self.owner.approve_bootstrap(candidate), now_ms=1100)
        self.clock.now = 1100
        self.host_reply()
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)

    def test_observation_and_activation_reject_invalid_time_types(self):
        candidate = self.candidate()
        for bad in (True, 1000.0, -1, '1000'):
            with self.assertRaises(ConfigurationError):
                self.owner.observe(candidate, 'host', status='healthy', observed_at_ms=bad)
        self.observe(candidate)
        receipt = self.owner.approve_bootstrap(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'clock'):
            self.owner.activate(candidate, receipt, now_ms=True)
        with self.assertRaisesRegex(ConfigurationError, 'clock'):
            self.owner.activate(candidate, receipt, now_ms=1000)
        self.assertEqual(self.owner.state.revision, 0)

    def test_candidate_capacity_fails_closed_without_replacing_active(self):
        self.bootstrap()
        for _ in range(255):
            self.candidate('m2')
        with self.assertRaisesRegex(ConfigurationError, 'capacity'):
            self.candidate('m3')
        self.assertEqual(self.owner.state.revision, 1)

    def test_disabled_configuration_does_not_reenable_with_bootstrap_approval(self):
        self.bootstrap()
        self.owner.disable()
        candidate = self.candidate('m2')
        with self.assertRaisesRegex(ConfigurationError, 'bootstrap'):
            self.owner.approve_bootstrap(candidate)
        self.assertEqual(self.owner.state.revision, 2)

    def test_adding_fallback_requires_bound_bootstrap_for_missing_baseline_role(self):
        self.bootstrap()
        candidate = self.candidate(fallback=True)
        self.observe(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'bootstrap'):
            self.owner.approve(candidate)
        self.owner.activate(candidate, self.owner.approve_bootstrap(candidate), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 2)

    def test_removing_fallback_compares_retained_host_and_disables_fallback_effect(self):
        self.bootstrap(fallback=True)
        candidate = self.candidate(policy=parse_policy(policy_doc(allow_fallback=False)))
        self.observe(candidate)
        self.owner.activate(candidate, self.owner.approve(candidate), now_ms=1000)
        self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
        self.client.start(self.request)
        result = self.client.poll()
        self.assertEqual([f.code for f in result.failures], ['unavailable'])
        self.assertEqual(self.local_calls, [])

    def test_fallback_bootstrap_does_not_skip_existing_host_comparison(self):
        self.bootstrap()
        candidate = self.candidate(fallback=True, bundle='c' * 64)
        self.observe(candidate)
        with self.assertRaisesRegex(ConfigurationError, 'bundle'):
            self.owner.activate(candidate, self.owner.approve_bootstrap(candidate), now_ms=1000)
        self.assertEqual(self.owner.state.revision, 1)
