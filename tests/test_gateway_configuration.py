"""Configuration must not erase the gateway's existing lifecycle evidence."""
from dataclasses import replace
import threading
import unittest

from runtime.gateway.client import Failed, GatewayError, HttpReply, Success
from runtime.gateway.wire import LIMITS
from tests import test_gateway_client as fixtures
from tests.test_gateway_wire import response_doc, wire


class GatewayConfigurationTests(unittest.TestCase):
    setUp = fixtures.GatewayClientTests.setUp
    local_begin = fixtures.GatewayClientTests.local_begin
    host_reply = fixtures.GatewayClientTests.host_reply

    def test_rebind_preserves_replay_history(self):
        self.host_reply()
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)
        with self.client.configuration():
            self.client.reconfigure(self.host, self.local)
        with self.assertRaisesRegex(GatewayError, 'replay'):
            self.client.start(self.request)
        self.assertEqual(len(self.transport.sent), 1)

    def test_active_and_unconsumed_results_block_rebind(self):
        self.client.start(self.request)
        with self.assertRaisesRegex(GatewayError, 'busy'):
            self.client.reconfigure(self.host)
        self.client.cancel()
        with self.assertRaisesRegex(GatewayError, 'busy'):
            self.client.reconfigure(self.host)
        self.assertIsInstance(self.client.poll(), Failed)
        self.client.reconfigure(self.host)

    def test_cleanup_fault_survives_disable_and_rebind(self):
        self.transport.job.cleanup = False
        self.client.start(self.request)
        self.client.disable()
        self.assertEqual(self.client.poll().failures[-1].code, 'cleanup')
        with self.assertRaisesRegex(GatewayError, 'cleanup'):
            self.client.reconfigure(self.host)
        self.assertFalse(self.client.cleanup_proven)
        self.assertEqual(self.local_calls, [])

    def test_rebind_cannot_reset_replay_exhaustion(self):
        for index in range(LIMITS['history']):
            req = replace(self.request, request_id=f'call-{index}')
            self.host_reply(req)
            self.client.start(req)
            self.client.poll()
        self.client.reconfigure(self.host)
        with self.assertRaisesRegex(GatewayError, 'exhausted'):
            self.client.start(replace(self.request, request_id='new'))
        self.assertEqual(len(self.transport.sent), LIMITS['history'])

    def test_permit_runs_before_primary_and_fallback_effects(self):
        seen = []

        def permit(provider, service, now):
            seen.append((provider.provider_id, service, now))
            return provider.placement == 'host'

        self.client.reconfigure(self.host, self.local, permit=permit)
        self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
        self.client.start(self.request)
        self.clock.now += 1
        result = self.client.poll()
        self.assertEqual([x.code for x in result.failures], ['unavailable', 'canceled'])
        self.assertEqual(seen, [('host', 'llm', 1000), ('vm', 'llm', 1001)])
        self.assertEqual(self.local_calls, [])

    def test_false_throwing_or_truthy_permit_cannot_begin(self):
        def broken(*args):
            raise RuntimeError('private')

        for permit in (lambda *args: False, lambda *args: 1, broken):
            self.setUp()
            self.client.reconfigure(self.host, self.local, permit=permit)
            self.client.start(self.request)
            self.assertEqual(self.client.poll().failures[0].code, 'canceled')
            self.assertEqual(self.transport.sent, [])
            self.assertEqual(self.local_calls, [])

    def test_disable_from_permit_cannot_begin_even_with_true_return(self):
        def permit(*args):
            self.client.disable()
            return True

        self.client.reconfigure(self.host, self.local, permit=permit)
        self.client.start(self.request)
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.assertEqual(self.transport.sent, [])
        with self.assertRaisesRegex(GatewayError, 'canceled'):
            self.client.start(replace(self.request, request_id='other'))

    def test_configuration_excludes_calls_and_callback_reentry(self):
        with self.client.configuration():
            with self.assertRaisesRegex(GatewayError, 'busy'):
                self.client.start(self.request)
            with self.assertRaisesRegex(GatewayError, 'busy'):
                with self.client.configuration():
                    self.fail('reentered')
        rejected = []

        def reenter():
            try:
                with self.client.configuration():
                    self.fail('callback entered configuration')
            except GatewayError as error:
                rejected.append(error.code)

        self.transport.on_begin = reenter
        self.client.start(self.request)
        self.assertEqual(rejected, ['busy'])

    def test_configuration_serializes_other_thread_until_commit(self):
        begun, finished = threading.Event(), threading.Event()

        def caller():
            begun.set()
            self.client.start(self.request)
            finished.set()

        with self.client.configuration():
            worker = threading.Thread(target=caller)
            worker.start()
            self.assertTrue(begun.wait(1))
            self.assertFalse(finished.is_set())
            self.client.reconfigure(self.host, permit=lambda *args: False)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(finished.is_set())
        self.assertEqual(self.client.poll().failures[0].code, 'canceled')
        self.assertEqual(self.transport.sent, [])

    def test_existing_caller_without_permit_keeps_success(self):
        self.client.reconfigure(self.host, self.local)
        self.transport.job.reply = HttpReply(200, wire(response_doc(self.request)), fixtures.PEER)
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)

    def test_exclusive_configuration_claim_closes_admission_atomically(self):
        owner = self.client.claim_configuration()
        with self.assertRaisesRegex(GatewayError, 'busy'):
            self.client.claim_configuration()
        with self.assertRaisesRegex(GatewayError, 'canceled'):
            self.client.start(self.request)
        with self.assertRaisesRegex(GatewayError, 'identity'):
            self.client.reconfigure(self.host)
        with self.assertRaisesRegex(GatewayError, 'identity'):
            self.client.disable()
        with self.assertRaisesRegex(GatewayError, 'identity'):
            with self.client.configuration(object()):
                self.fail('foreign owner')
        with self.client.configuration(owner):
            self.client.reconfigure(self.host, owner=owner)
        self.host_reply()
        self.client.start(self.request)
        self.assertIsInstance(self.client.poll(), Success)

    def test_configuration_transaction_cannot_poll_into_fallback_effect(self):
        self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
        self.client.start(self.request)
        with self.client.configuration():
            self.assertIsNone(self.client.poll())
            self.assertEqual(self.local_calls, [])
            self.assertEqual(self.transport.job.polls, 0)
        self.assertIsNone(self.client.poll())
        self.assertEqual(len(self.local_calls), 1)

    def test_cancel_or_disable_inside_either_permit_prevents_that_effect(self):
        for placement in ('host', 'vm'):
            for action in ('cancel', 'disable'):
                with self.subTest(placement=placement, action=action):
                    self.setUp()

                    def permit(provider, service, now):
                        if provider.placement == placement:
                            getattr(self.client, action)()
                        return True

                    self.client.reconfigure(self.host, self.local, permit=permit)
                    self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
                    self.client.start(self.request)
                    result = self.client.poll()
                    self.assertEqual(len(self.transport.sent), int(placement == 'vm'))
                    self.assertEqual(self.local_calls, [])
                    self.assertEqual(result.failures[-1].code, 'canceled')
                    self.assertTrue(self.client.cleanup_proven)
                    self.assertIsNone(self.client.poll())

    def test_cutover_from_either_permit_is_busy_and_cancellation_still_completes(self):
        for placement in ('host', 'vm'):
            with self.subTest(placement=placement):
                self.setUp()
                denied = []

                def permit(provider, service, now):
                    if provider.placement == placement:
                        try:
                            self.client.reconfigure(self.host)
                        except GatewayError as error:
                            denied.append(error.code)
                        self.client.cancel()
                    return True

                self.client.reconfigure(self.host, self.local, permit=permit)
                self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
                self.client.start(self.request)
                result = self.client.poll()
                self.assertEqual(denied, ['busy'])
                self.assertEqual(self.local_calls, [])
                self.assertEqual(result.failures[-1].code, 'canceled')
                self.assertTrue(self.client.cleanup_proven)

    def test_threaded_disable_serializes_with_each_permit_and_retires_admitted_effect(self):
        for placement in ('host', 'vm'):
            with self.subTest(placement=placement):
                self.setUp()
                entered, release = threading.Event(), threading.Event()
                attempted, disabled = threading.Event(), threading.Event()
                failures = []

                def permit(provider, service, now):
                    if provider.placement == placement:
                        entered.set()
                        return release.wait(2)
                    return True

                def drive():
                    try:
                        if placement == 'host':
                            self.client.start(self.request)
                        else:
                            self.client.poll()
                    except Exception as error:
                        failures.append(error)

                def disable():
                    attempted.set()
                    try:
                        self.client.disable()
                        disabled.set()
                    except Exception as error:
                        failures.append(error)

                self.client.reconfigure(self.host, self.local, permit=permit)
                self.transport.job.reply = HttpReply(503, b'', fixtures.PEER)
                if placement == 'vm':
                    self.client.start(self.request)
                caller = threading.Thread(target=drive, daemon=True)
                disabler = threading.Thread(target=disable, daemon=True)
                try:
                    caller.start()
                    self.assertTrue(entered.wait(2))
                    disabler.start()
                    self.assertTrue(attempted.wait(2))
                    self.assertFalse(disabled.is_set())
                finally:
                    release.set()
                    caller.join(3)
                    if disabler.ident is not None:
                        disabler.join(3)
                self.assertFalse(caller.is_alive())
                self.assertFalse(disabler.is_alive())
                self.assertEqual(failures, [])
                self.assertTrue(disabled.is_set())
                self.assertEqual(self.client.poll().failures[-1].code, 'canceled')
                effects = (len(self.transport.sent), len(self.local_calls))
                self.assertEqual(effects, (1, int(placement == 'vm')))
                with self.assertRaisesRegex(GatewayError, 'canceled'):
                    self.client.start(replace(self.request, request_id='after-disable'))
                self.assertEqual((len(self.transport.sent), len(self.local_calls)), effects)
                self.assertTrue(self.client.cleanup_proven)
