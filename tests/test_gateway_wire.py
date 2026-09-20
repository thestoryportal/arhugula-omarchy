import base64
from dataclasses import FrozenInstanceError, replace
import json
import unittest

from runtime.contracts import Provider
from runtime.gateway.admission import Admission, Bearer
from runtime.gateway.wire import (
    GatewayError, LlmInput, LlmOutput, EvaluationInput, EvaluationOutput,
    SpeechInput, SpeechOutput, RemoteError, parse_request, parse_response,
    request_bytes, response_bytes,
)


def wire(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()


def request_doc(service='llm', request_id='r1', **changes):
    payloads = {
        'llm': {'text': 'open menu', 'context': 'desktop', 'candidates': ['menu']},
        'evaluator': {'context': 'compare', 'candidates': [
            {'candidate_id': 'a', 'text': 'first'}, {'candidate_id': 'b', 'text': 'second'}]},
        'tts': {'text': 'Ready', 'voice': 'natural'},
    }
    return {'version': 1, 'request_id': request_id, 'service': service,
            'provider_id': 'host', 'model_version': 'm1', 'catalog_version': 7,
            'budget_ms': 30000, 'payload': payloads[service], **changes}


def response_doc(request, result=None, **changes):
    results = {
        'llm': {'text': 'choose menu', 'candidate_id': 'menu'},
        'evaluator': {'scores': [{'candidate_id': 'a', 'score': 0.8},
                                 {'candidate_id': 'b', 'score': 0.2}], 'selected_id': 'a'},
        'tts': {'pcm_b64': 'AAA=', 'sample_rate': 24000, 'channels': 1, 'sample_width': 2},
    }
    return {'version': 1, 'request_id': request.request_id, 'service': request.service,
            'provider_id': request.provider_id, 'model_version': request.model_version,
            'catalog_version': request.catalog_version, 'status': 'ok',
            'result': results[request.service] if result is None else result, **changes}


def host_provider(**changes):
    return Provider(**{'version': 1, 'provider_id': 'host', 'placement': 'host',
                      'model_version': 'm1', 'enabled': True, 'health': 'healthy',
                      'capabilities': ('llm', 'evaluator', 'tts'), **changes})


class GatewayWireTests(unittest.TestCase):
    def test_all_service_roundtrips_produce_immutable_domain_results(self):
        for service, input_type, output_type in (
            ('llm', LlmInput, LlmOutput), ('evaluator', EvaluationInput, EvaluationOutput),
            ('tts', SpeechInput, SpeechOutput),
        ):
            with self.subTest(service=service):
                request = parse_request(wire(request_doc(service)))
                self.assertIsInstance(request.payload, input_type)
                self.assertEqual(parse_request(request_bytes(request)), request)
                reply = parse_response(wire(response_doc(request)), request)
                self.assertIsInstance(reply, output_type)
                self.assertEqual(parse_response(response_bytes(request, reply), request), reply)
                with self.assertRaises(FrozenInstanceError):
                    request.catalog_version = 8
        self.assertEqual(parse_response(wire(response_doc(request)), request).pcm, b'\0\0')

    def test_bad_envelopes_cannot_be_parsed_as_requests(self):
        for changes in ({'version': True}, {'version': 2}, {'catalog_version': True},
                        {'catalog_version': 0}, {'budget_ms': 0}, {'budget_ms': 30001},
                        {'budget_ms': 1.0}, {'service': 'shell'}, {'request_id': 'x\n'},
                        {'request_id': 'x' * 129}, {'extra': 'private-secret'}):
            with self.subTest(changes=changes), self.assertRaises(GatewayError) as caught:
                parse_request(wire({**request_doc(), **changes}))
            self.assertEqual(str(caught.exception), 'invalid_request')

    def test_duplicate_keys_nonfinite_invalid_utf8_and_deep_json_rejected(self):
        valid = wire(request_doc())
        for raw in (b'[]', b'\xff', valid.replace(b'"version":1', b'"version":1,"version":1'),
                    valid.replace(b'30000', b'NaN'), b'[' * 9 + b'0' + b']' * 9,
                    valid.replace(b'open menu', b'\\ud800'), bytearray(valid)):
            with self.subTest(raw=repr(raw[:60])), self.assertRaises(GatewayError):
                parse_request(raw)

    def test_payload_byte_and_request_wire_limits(self):
        doc = request_doc(payload={'text': 'x' * 32768, 'context': '', 'candidates': []})
        self.assertEqual(len(parse_request(wire(doc)).payload.text), 32768)
        doc['payload']['text'] += 'x'
        with self.assertRaises(GatewayError):
            parse_request(wire(doc))
        doc['payload']['text'] = '\u00e9' * 16385
        with self.assertRaises(GatewayError):
            parse_request(wire(doc))
        with self.assertRaises(GatewayError):
            parse_request(b' ' * 65536 + wire(request_doc()))

    def test_candidates_are_unique_bounded_and_service_specific(self):
        for candidates in (['menu', 'menu'], ['c' + str(i) for i in range(33)], [True]):
            doc = request_doc(payload={'text': 'go', 'context': '', 'candidates': candidates})
            with self.assertRaises(GatewayError):
                parse_request(wire(doc))
        doc = request_doc('evaluator')
        doc['payload']['candidates'][1]['candidate_id'] = 'a'
        with self.assertRaises(GatewayError):
            parse_request(wire(doc))
        doc = request_doc('tts', payload={'text': 'go', 'voice': 'v', 'url': 'file:///secret'})
        with self.assertRaises(GatewayError):
            parse_request(wire(doc))

    def test_response_identity_fields_must_match_exactly(self):
        request = parse_request(wire(request_doc()))
        for changes in ({'request_id': 'other'}, {'provider_id': 'vm'}, {'model_version': 'm2'},
                        {'catalog_version': 8}, {'catalog_version': True}, {'service': 'tts'},
                        {'version': 2}, {'extra': 1}):
            with self.subTest(changes=changes), self.assertRaises(GatewayError):
                parse_response(wire(response_doc(request, **changes)), request)

    def test_llm_response_cannot_select_unknown_capability_or_grant_authority(self):
        request = parse_request(wire(request_doc()))
        for result in ({'text': 'go', 'candidate_id': 'shell'},
                       {'text': 'go', 'candidate_id': 'menu', 'approved': True},
                       {'text': 'go', 'candidate_id': 'menu', 'arguments': {'command': 'true'}}):
            with self.assertRaises(GatewayError):
                parse_response(wire(response_doc(request, result)), request)
        self.assertEqual(parse_response(wire(response_doc(request, {'text': 'clarify',
                                                                  'candidate_id': None})), request).text,
                         'clarify')

    def test_evaluator_scores_require_exact_ids_finite_scores_and_member_selection(self):
        request = parse_request(wire(request_doc('evaluator')))
        for result in (
            {'scores': [], 'selected_id': None},
            {'scores': [{'candidate_id': 'a', 'score': .5}] * 2, 'selected_id': 'a'},
            {'scores': [{'candidate_id': 'a', 'score': True},
                        {'candidate_id': 'b', 'score': .2}], 'selected_id': 'a'},
            {'scores': [{'candidate_id': 'a', 'score': 1.1},
                        {'candidate_id': 'b', 'score': .2}], 'selected_id': 'a'},
            {'scores': [{'candidate_id': 'a', 'score': .8},
                        {'candidate_id': 'b', 'score': .2}], 'selected_id': 'unknown'},
        ):
            with self.subTest(result=result), self.assertRaises(GatewayError):
                parse_response(wire(response_doc(request, result)), request)

    def test_pcm_is_bounded_canonical_and_has_no_url_or_playback(self):
        request = parse_request(wire(request_doc('tts')))
        result = response_doc(request)['result']
        maximum = {**result, 'pcm_b64': base64.b64encode(bytes(480000)).decode()}
        self.assertEqual(len(parse_response(wire(response_doc(request, maximum)), request).pcm), 480000)
        for changes in ({'pcm_b64': ''}, {'pcm_b64': 'AB=='}, {'pcm_b64': 'AAA=\n'},
                        {'pcm_b64': 'AAAA'}, {'pcm_b64': base64.b64encode(bytes(480002)).decode()},
                        {'channels': True}, {'sample_rate': 48000}, {'url': 'https://host/audio'},
                        {'play': True}):
            with self.subTest(changes=changes), self.assertRaises(GatewayError):
                parse_response(wire(response_doc(request, {**result, **changes})), request)

    def test_response_wire_limit_and_error_shape_are_enforced(self):
        request = parse_request(wire(request_doc()))
        with self.assertRaises(GatewayError):
            parse_response(b' ' * 65536 + wire(response_doc(request)), request)
        error = {k: v for k, v in response_doc(request).items() if k != 'result'}
        error.update(status='error', code='unavailable')
        self.assertEqual(parse_response(wire(error), request), RemoteError('unavailable'))
        for changes in ({'code': 'secret diagnostic'}, {'result': {}}, {'status': 'degraded'}):
            with self.assertRaises(GatewayError):
                parse_response(wire({**error, **changes}), request)

    def test_request_and_result_representations_exclude_content(self):
        request = parse_request(wire(request_doc(payload={'text': 'private-input',
                                                        'context': 'private-context', 'candidates': []})))
        result = parse_response(wire(response_doc(request, {'text': 'private-output',
                                                            'candidate_id': None})), request)
        self.assertNotIn('private', repr(request))
        self.assertNotIn('private', repr(request.payload))
        self.assertNotIn('private', repr(result))
        self.assertNotIn('AAA=', repr(SpeechOutput(b'\0\0')))

    def test_direct_request_constructors_are_revalidated_at_encoding(self):
        request = parse_request(wire(request_doc()))
        with self.assertRaises(GatewayError):
            request_bytes(replace(request, budget_ms=True))


class GatewayAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.bearer = Bearer('s' * 32)
        self.admission = Admission(host_provider(), 7, self.bearer)

    def test_auth_precedes_parsing_and_rejected_auth_does_not_consume_id(self):
        for header in ('Bearer wrong', 'Basic ' + 's' * 32, None, 'Bearer \u00e9', 'x' * 4097):
            with self.assertRaises(GatewayError) as caught:
                self.admission.admit(header, b'invalid JSON')
            self.assertEqual(caught.exception.code, 'authentication')
        admitted = self.admission.admit(self.bearer.header(), wire(request_doc()))
        self.assertEqual(admitted.request.request_id, 'r1')
        with self.assertRaises(GatewayError) as caught:
            self.admission.admit(self.bearer.header(), wire(request_doc()))
        self.assertEqual(caught.exception.code, 'replay')

    def test_provider_catalog_and_service_mismatch_cannot_be_admitted(self):
        for changes, code in (({'provider_id': 'other'}, 'identity'),
                              ({'model_version': 'm2'}, 'identity'),
                              ({'catalog_version': 8}, 'stale_catalog')):
            with self.assertRaises(GatewayError) as caught:
                self.admission.admit(self.bearer.header(), wire(request_doc(**changes)))
            self.assertEqual(caught.exception.code, code)
        unavailable = Admission(host_provider(health='unavailable'), 7, self.bearer)
        with self.assertRaises(GatewayError) as caught:
            unavailable.admit(self.bearer.header(), wire(request_doc()))
        self.assertEqual(caught.exception.code, 'unavailable')
        speech_only = Admission(host_provider(capabilities=('tts',)), 7, self.bearer)
        with self.assertRaises(GatewayError):
            speech_only.admit(self.bearer.header(), wire(request_doc()))

    def test_provider_configuration_is_snapshotted_not_mutably_shared(self):
        capabilities = ['llm']
        admission = Admission(host_provider(capabilities=capabilities), 7, self.bearer)
        capabilities.clear()
        self.assertEqual(admission.admit(self.bearer.header(), wire(request_doc())).request.service, 'llm')

    def test_replay_retention_never_evicts_old_ids_and_exhaustion_is_explicit(self):
        for i in range(4096):
            self.admission.admit(self.bearer.header(), wire(request_doc(request_id=f'r{i}')))
        for request_id, code in (('r0', 'replay'), ('overflow', 'exhausted')):
            with self.assertRaises(GatewayError) as caught:
                self.admission.admit(self.bearer.header(), wire(request_doc(request_id=request_id)))
            self.assertEqual(caught.exception.code, code)

    def test_secret_repr_and_invalid_secret_errors_are_redacted(self):
        self.assertNotIn('s' * 32, repr(self.bearer))
        for value in ('', 'private secret\r\n', 'x' * 257, b's' * 32):
            with self.assertRaises(GatewayError) as caught:
                Bearer(value)
            self.assertEqual(str(caught.exception), 'authentication')


if __name__ == '__main__':
    unittest.main()
