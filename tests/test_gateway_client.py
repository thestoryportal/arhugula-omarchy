from dataclasses import replace
import threading
import unittest

from runtime.gateway.admission import Admission, Bearer
from runtime.gateway.client import (
    Endpoint, Host, Local, HttpReply, GatewayClient, Success, Degraded, Failed,
)
from runtime.gateway.wire import GatewayError, RemoteError, parse_request
from tests.test_gateway_wire import host_provider, request_doc, response_doc, wire


PEER = 'a' * 64


class Clock:
    now = 1000

    def __call__(self):
        return self.now


class Job:
    def __init__(self, reply=None, cleanup=True, on_poll=None, on_cancel=None):
        self.reply, self.cleanup = reply, cleanup
        self.on_poll, self.on_cancel = on_poll, on_cancel
        self.cancels = self.polls = 0

    def poll(self):
        self.polls += 1
        if self.on_poll:
            self.on_poll()
        return self.reply

    def cancel(self):
        self.cancels += 1
        if self.on_cancel:
            self.on_cancel()
        return self.cleanup


class Transport:
    peer_identity = PEER

    def __init__(self, admission):
        self.admission, self.sent = admission, []
        self.job = Job()
        self.on_begin = None

    def begin(self, outgoing):
        self.sent.append(outgoing)
        admitted = self.admission.admit(outgoing.authorization, outgoing.body)
        if self.on_begin:
            self.on_begin()
        self.last = admitted.request
        return self.job


class GatewayClientTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.bearer = Bearer('s' * 32)
        self.provider = host_provider()
        self.transport = Transport(Admission(self.provider, 7, self.bearer))
        self.host = Host(self.provider, Endpoint('https://host.test/v1/gateway', PEER),
                         self.bearer, self.transport)
        self.local_calls = []
        self.local_job = Job()
        self.local_provider = host_provider(provider_id='vm', placement='vm')
        self.local = Local(self.local_provider, self.local_begin)
        self.client = GatewayClient(self.host, 7, self.clock, self.local)
        self.request = parse_request(wire(request_doc()))

    def local_begin(self, request, budget_ms):
        self.local_calls.append((request, budget_ms))
        return self.local_job

    def host_reply(self, request=None, **changes):
        request = self.request if request is None else request
        self.transport.job.reply = HttpReply(200, wire(response_doc(request, **changes)), PEER)

    def host_error(self, code):
        doc = response_doc(self.request)
        del doc['result']
        doc.update(status='error', code=code)
        self.transport.job.reply = HttpReply(200, wire(doc), PEER)

    def test_all_services_cross_real_admission_and_return_data_once(self):
        for service in ('llm', 'evaluator', 'tts'):
            request = parse_request(wire(request_doc(service, request_id=service)))
            self.host_reply(request)
            self.client.start(request)
            result = self.client.poll()
            self.assertIsInstance(result, Success)
            self.assertEqual((result.provider_id, result.model_version), ('host', 'm1'))
            self.assertEqual(self.transport.last, request)
            self.assertIsNone(self.client.poll())
            self.assertTrue(self.client.cleanup_proven)
        self.assertEqual(self.local_calls, [])

    def test_peer_identity_is_checked_before_disclosing_credential_or_request(self):
        self.transport.peer_identity = 'b' * 64
        self.client.start(self.request)
        result = self.client.poll()
        self.assertEqual(result.failures[0].code, 'identity')
        self.assertEqual(self.transport.sent, [])
        self.assertEqual(self.local_calls, [])

    def test_insecure_ambiguous_or_credential_bearing_endpoints_rejected(self):
        for url in ('http://host.test/v1/gateway', 'https://user:secret@host.test/v1/gateway',
                    'https://host.test/v1/gateway?token=secret', 'https://host.test/v1/gateway#x',
                    'https://host.test:bad/v1/gateway', 'https://host.test/other',
                    'https://host.test\n/v1/gateway', 'https://host.test:0/v1/gateway',
                    'https://host.test/v1/gateway?', 'https://host.test/v1/gateway#',
                    'https://host%2etest/v1/gateway', 'https://host\\evil/v1/gateway'):
            with self.subTest(url=url), self.assertRaises(GatewayError):
                Endpoint(url, PEER)
        for peer in ('A' * 64, 'a' * 64 + '\n', '', None):
            with self.assertRaises(GatewayError):
                Endpoint('https://host.test/v1/gateway', peer)

    def test_redirect_or_wrong_response_peer_is_not_followed_or_fallen_back(self):
        for status, peer, code in ((302, PEER, 'invalid_response'),
                                   (200, 'b' * 64, 'identity')):
            self.setUp()
            self.transport.job.reply = HttpReply(status, wire(response_doc(self.request)), peer)
            self.client.start(self.request)
            self.assertEqual(self.client.poll().failures[0].code, code)
            self.assertEqual(len(self.transport.sent), 1)
            self.assertEqual(self.local_calls, [])
            self.assertEqual(self.transport.job.cancels, 1)

    def test_peer_attestation_must_be_a_string_not_an_equality_impersonator(self):
        class Impersonator:
            def __eq__(self, other):
                return True
        self.transport.peer_identity = Impersonator()
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'identity')
        self.assertEqual(self.transport.sent, [])
        self.setUp()
        self.transport.job.reply = HttpReply(200, wire(response_doc(self.request)), Impersonator())
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'identity')

    def test_http_host_loss_and_atomic_begin_failure_can_use_explicit_fallback(self):
        for status in (502, 503, 504):
            self.setUp()
            self.transport.job.reply = HttpReply(status, b'private backend diagnostic', PEER)
            self.client.start(self.request)
            self.assertIsNone(self.client.poll())
            self.local_job.reply = wire(response_doc(self.local_calls[0][0]))
            result = self.client.poll()
            self.assertIsInstance(result, Degraded)
            self.assertEqual(result.primary.code, 'timeout' if status == 504 else 'unavailable')
        self.setUp()
        self.transport.job = RemoteError('unavailable')
        self.client.start(self.request)
        self.local_job.reply = wire(response_doc(self.local_calls[0][0]))
        self.assertIsInstance(self.client.poll(), Degraded)

    def test_auth_protocol_and_catalog_failures_never_trigger_local_fallback(self):
        for code in ('authentication', 'identity', 'invalid_response', 'stale_catalog',
                     'replay', 'exhausted', 'canceled', 'clock', 'cleanup'):
            self.setUp()
            self.host_error(code)
            self.client.start(self.request)
            self.assertEqual(self.client.poll().failures[0].code, code)
            self.assertEqual(self.local_calls, [])

    def test_mismatched_and_malformed_responses_are_explicit_failures(self):
        for body in (b'private transcript not JSON',
                     wire(response_doc(self.request, provider_id='other')),
                     wire(response_doc(self.request, catalog_version=8)),
                     wire(response_doc(self.request, result={'text': 'go', 'candidate_id': 'shell'}))):
            self.setUp()
            self.transport.job.reply = HttpReply(200, body, PEER)
            self.client.start(self.request)
            result = self.client.poll()
            self.assertEqual(result.failures[0].code, 'invalid_response')
            self.assertNotIn('private', repr(result))
            self.assertEqual(self.local_calls, [])

    def test_one_explicit_local_attempt_preserves_primary_failure_and_remaining_budget(self):
        self.host_error('unavailable')
        self.client.start(self.request)
        self.clock.now = 2000
        self.assertIsNone(self.client.poll())
        request, budget = self.local_calls[0]
        self.assertEqual((request.request_id, request.provider_id, request.catalog_version), ('r1', 'vm', 7))
        self.assertEqual((budget, request.budget_ms), (29000, 29000))
        self.local_job.reply = wire(response_doc(request))
        result = self.client.poll()
        self.assertIsInstance(result, Degraded)
        self.assertEqual((result.primary.code, result.primary.provider_id), ('unavailable', 'host'))
        self.assertEqual(result.result.provider_id, 'vm')
        self.assertEqual(result.result.output.candidate_id, 'menu')
        self.assertEqual(self.transport.job.cancels, 1)
        self.assertEqual(self.local_job.cancels, 1)
        self.assertIsNone(self.client.poll())

    def test_failed_fallback_retains_both_failures_and_never_retries(self):
        self.host_error('provider_failed')
        self.client.start(self.request)
        self.client.poll()
        self.local_job.reply = b'private malformed output'
        result = self.client.poll()
        self.assertEqual([(f.provider_id, f.code) for f in result.failures],
                         [('host', 'provider_failed'), ('vm', 'invalid_response')])
        self.assertEqual(len(self.local_calls), 1)
        self.assertIsNone(self.client.poll())

    def test_missing_fallback_is_failure_not_empty_success(self):
        client = GatewayClient(self.host, 7, self.clock)
        self.host_error('unavailable')
        client.start(self.request)
        self.assertIsInstance(client.poll(), Failed)

    def test_total_deadline_stops_polling_and_forbids_late_success_or_fallback(self):
        self.host_reply()
        self.client.start(self.request)
        self.clock.now = 31000
        self.assertEqual(self.client.poll().failures[0].code, 'timeout')
        self.assertEqual(self.transport.job.polls, 0)
        self.assertEqual(self.transport.job.cancels, 1)
        self.assertEqual(self.local_calls, [])
        self.clock.now = 32000
        self.assertIsNone(self.client.poll())

    def test_early_timeout_can_degrade_but_does_not_extend_deadline(self):
        self.host_error('timeout')
        self.client.start(self.request)
        self.clock.now = 30000
        self.client.poll()
        self.assertEqual(self.local_calls[0][1], 1000)
        self.local_job.reply = wire(response_doc(self.local_calls[0][0]))
        self.clock.now = 31000
        result = self.client.poll()
        self.assertEqual([p.code for p in result.failures], ['timeout', 'timeout'])

    def test_clock_regression_and_invalid_clock_latch_closed_after_cleanup(self):
        for bad in (1500, True, 1.5, None):
            self.setUp()
            self.client.start(self.request)
            self.clock.now = 2000
            self.assertIsNone(self.client.poll())
            self.clock.now = bad
            self.assertEqual(self.client.poll().failures[0].code, 'clock')
            self.assertTrue(self.client.cleanup_proven)
            with self.assertRaises(GatewayError):
                self.client.start(replace(self.request, request_id='second'))

    def test_cancel_is_single_terminal_and_suppresses_a_late_result(self):
        self.client.start(self.request)
        self.client.cancel()
        self.host_reply()
        self.client.cancel()
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.assertIsNone(self.client.poll())
        self.assertEqual(self.transport.job.cancels, 1)
        self.assertTrue(self.client.cleanup_proven)

    def test_reentrant_cancel_during_begin_waits_for_the_owned_job_cleanup(self):
        self.transport.on_begin = self.client.cancel
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.assertEqual(self.transport.job.cancels, 1)
        self.assertEqual(self.local_calls, [])

    def test_reentrant_cancel_during_poll_or_cleanup_suppresses_success(self):
        for callback in ('on_poll', 'on_cancel'):
            self.setUp()
            setattr(self.transport.job, callback, self.client.cancel)
            self.host_reply()
            self.client.start(self.request)
            self.assertEqual(self.client.poll().failures[0].code, 'canceled')
            self.assertIsNone(self.client.poll())

    def test_reentrant_poll_and_start_cannot_consume_or_replace_the_active_call(self):
        def reenter():
            self.assertIsNone(self.client.poll())
            with self.assertRaises(GatewayError) as caught:
                self.client.start(replace(self.request, request_id='second'))
            self.assertEqual(caught.exception.code, 'busy')
        self.transport.job.on_poll = reenter
        self.host_reply()
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)
        self.assertEqual(len(self.transport.sent), 1)

    def test_callback_overrun_suppresses_success_and_proves_cleanup(self):
        def overrun():
            self.clock.now = 31001
        self.transport.job.on_poll = overrun
        self.host_reply()
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'timeout')
        self.assertTrue(self.client.cleanup_proven)

    def test_unproven_cleanup_latches_closed_and_never_starts_fallback(self):
        for proof in (False, 1, None):
            self.setUp()
            self.transport.job.cleanup = proof
            self.host_error('unavailable')
            self.client.start(self.request)
            self.assertEqual(self.client.poll().failures[-1].code, 'cleanup')
            self.assertFalse(self.client.cleanup_proven)
            self.assertEqual(self.local_calls, [])
            with self.assertRaises(GatewayError):
                self.client.start(replace(self.request, request_id='second'))

    def test_remote_cleanup_failure_cannot_be_overridden_by_transport_cleanup(self):
        self.host_error('cleanup')
        self.client.start(self.request)
        result = self.client.poll()
        self.assertEqual(result.failures[-1].code, 'cleanup')
        self.assertFalse(self.client.cleanup_proven)
        with self.assertRaises(GatewayError):
            self.client.start(replace(self.request, request_id='second'))
        self.assertEqual(self.local_calls, [])

    def test_begin_exception_cannot_claim_cleanup_or_leak_diagnostics(self):
        def fail():
            raise RuntimeError('private token ' + self.bearer.value)
        self.transport.on_begin = fail
        self.client.start(self.request)
        result = self.client.poll()
        self.assertEqual(result.failures[-1].code, 'cleanup')
        self.assertNotIn('private', repr(result))
        self.assertNotIn(self.bearer.value, repr(result))
        self.assertEqual(self.local_calls, [])

    def test_provider_unavailable_can_fall_back_without_sending_credentials(self):
        host = replace(self.host, provider=host_provider(health='unavailable'))
        client = GatewayClient(host, 7, self.clock, self.local)
        client.start(self.request)
        self.assertEqual(self.transport.sent, [])
        self.assertEqual(len(self.local_calls), 1)
        self.local_job.reply = wire(response_doc(self.local_calls[0][0]))
        self.assertIsInstance(client.poll(), Degraded)

    def test_disabled_local_provider_cannot_be_invoked(self):
        local = replace(self.local, provider=replace(self.local_provider, enabled=False))
        client = GatewayClient(self.host, 7, self.clock, local)
        self.host_error('unavailable')
        client.start(self.request)
        self.assertEqual([f.code for f in client.poll().failures], ['unavailable', 'unavailable'])
        self.assertEqual(self.local_calls, [])

    def test_direct_request_revalidation_busy_and_replay_precede_transport(self):
        with self.assertRaises(GatewayError):
            self.client.start(replace(self.request, budget_ms=True))
        self.client.start(self.request)
        with self.assertRaises(GatewayError):
            self.client.start(replace(self.request, request_id='second'))
        self.client.cancel()
        with self.assertRaises(GatewayError):
            self.client.start(replace(self.request, request_id='second'))
        self.client.poll()
        with self.assertRaises(GatewayError) as caught:
            self.client.start(self.request)
        self.assertEqual(caught.exception.code, 'replay')
        self.assertEqual(len(self.transport.sent), 1)

    def test_client_lifetime_history_exhausts_without_eviction(self):
        for i in range(4096):
            request = replace(self.request, request_id=f'r{i}')
            self.host_reply(request)
            self.client.start(request)
            self.assertIsInstance(self.client.poll(), Success)
        for request_id, code in (('r0', 'replay'), ('overflow', 'exhausted')):
            with self.assertRaises(GatewayError) as caught:
                self.client.start(replace(self.request, request_id=request_id))
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(len(self.transport.sent), 4096)

    def test_representations_do_not_expose_wire_or_credential(self):
        self.client.start(self.request)
        shown = repr(self.transport.sent[0]) + repr(self.host) + repr(self.client)
        self.assertNotIn('open menu', shown)
        self.assertNotIn(self.bearer.value, shown)

    def test_two_threads_cannot_start_two_jobs(self):
        barrier = threading.Barrier(3)
        results = []
        def start(index):
            barrier.wait()
            try:
                self.client.start(replace(self.request, request_id=f'r{index}'))
                results.append('started')
            except GatewayError as error:
                results.append(error.code)
        threads = [threading.Thread(target=start, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(results, ['started', 'busy'])
        self.assertEqual(len(self.transport.sent), 1)
        self.client.cancel()


if __name__ == '__main__':
    unittest.main()
