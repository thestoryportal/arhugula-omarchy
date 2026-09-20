"""Strict gateway v1 boundary. Parsed model data carries no execution authority."""
import base64
from dataclasses import asdict, dataclass, field
from importlib.resources import files
import json
import math
import re
from types import MappingProxyType


def _freeze_schema(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_schema(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_schema(item) for item in value)
    return value


_SCHEMA = _freeze_schema(json.loads(files('schemas').joinpath('gateway-v1.json').read_text()))
# [LAW:one-source-of-truth] Wire shape and bounds derive from the packaged schema.
LIMITS = MappingProxyType(_SCHEMA['x-limits'])


class GatewayError(ValueError):
    """Fixed public code only; raw diagnostics never become a message."""

    def __init__(self, code):
        self.code = code if code in _SCHEMA['$defs']['code']['enum'] else 'invalid_response'
        super().__init__(self.code)


@dataclass(frozen=True)
class LlmInput:
    text: str = field(repr=False)
    context: str = field(repr=False)
    candidates: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    text: str = field(repr=False)


@dataclass(frozen=True)
class EvaluationInput:
    context: str = field(repr=False)
    candidates: tuple[Candidate, ...] = field(repr=False)


@dataclass(frozen=True)
class SpeechInput:
    text: str = field(repr=False)
    voice: str


@dataclass(frozen=True)
class Request:
    request_id: str
    provider_id: str
    model_version: str
    catalog_version: int
    budget_ms: int
    payload: LlmInput | EvaluationInput | SpeechInput = field(repr=False)

    @property
    def service(self):
        return {LlmInput: 'llm', EvaluationInput: 'evaluator', SpeechInput: 'tts'}[type(self.payload)]


@dataclass(frozen=True)
class LlmOutput:
    text: str = field(repr=False)
    candidate_id: str | None


@dataclass(frozen=True)
class Score:
    candidate_id: str
    score: float


@dataclass(frozen=True)
class EvaluationOutput:
    scores: tuple[Score, ...]
    selected_id: str | None


@dataclass(frozen=True)
class SpeechOutput:
    pcm: bytes = field(repr=False)


@dataclass(frozen=True)
class RemoteError:
    code: str


Output = LlmOutput | EvaluationOutput | SpeechOutput
Reply = Output | RemoteError


def _check(value, schema):
    """Only the keywords in this bundled schema; not a general schema engine."""
    if '$ref' in schema:
        return _check(value, _SCHEMA['$defs'][schema['$ref'].split('/')[-1]])
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'null': type(None)}
    if kind == 'number':
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError
    elif kind is not None and type(value) is not types[kind]:
        raise ValueError
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise ValueError
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError
    if isinstance(value, dict):
        if not set(schema.get('required', ())) <= value.keys():
            raise ValueError
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and value.keys() - properties.keys():
            raise ValueError
        for key in value.keys() & properties.keys():
            _check(value[key], properties[key])
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            raise ValueError
        for item in value:
            _check(item, schema.get('items', {}))
        if schema.get('uniqueItems') and len(set(value)) != len(value):
            raise ValueError
    if kind == 'string':
        value.encode('utf-8')
        if len(value) < schema.get('minLength', 0):
            raise ValueError
        if 'pattern' in schema and re.fullmatch(schema['pattern'], value) is None:
            raise ValueError
    if kind in ('number', 'integer') and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        raise ValueError
    for child in schema.get('allOf', ()):
        _check(value, child)
    if 'oneOf' in schema:
        matches = 0
        for child in schema['oneOf']:
            try:
                _check(value, child)
                matches += 1
            except ValueError:
                pass
        if matches != 1:
            raise ValueError
    if 'not' in schema:
        try:
            _check(value, schema['not'])
        except ValueError:
            pass
        else:
            raise ValueError
    if 'if' in schema:
        try:
            _check(value, schema['if'])
        except ValueError:
            pass
        else:
            _check(value, schema['then'])


def _load(raw, limit):
    if type(raw) is not bytes or len(raw) > limit:
        raise ValueError

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError

    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject_constant)
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > LIMITS['depth'] or nodes > LIMITS['nodes']:
            raise ValueError
        if type(item) is dict:
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth + 1) for v in item)
    return value


def _text_size(value):
    if isinstance(value, str):
        return len(value.encode('utf-8'))
    if isinstance(value, dict):
        return sum(_text_size(v) for v in value.values())
    if isinstance(value, list):
        return sum(_text_size(v) for v in value)
    return 0


def _unique(ids):
    if len(set(ids)) != len(ids):
        raise ValueError


def catalog_revision(value: int) -> int:
    try:
        _check(value, _SCHEMA['$defs']['revision'])
        return value
    except (ValueError, TypeError):
        raise GatewayError('stale_catalog') from None


def parse_request(raw: bytes) -> Request:
    # [LAW:parse-dont-validate] This is the only raw request -> domain crossing.
    try:
        doc = _load(raw, LIMITS['request_bytes'])
        _check(doc, _SCHEMA['$defs']['request'])
        payload = doc['payload']
        if _text_size(payload) > LIMITS['text_bytes']:
            raise ValueError
        if doc['service'] == 'llm':
            parsed = LlmInput(payload['text'], payload['context'], tuple(payload['candidates']))
        elif doc['service'] == 'evaluator':
            candidates = tuple(Candidate(**item) for item in payload['candidates'])
            _unique([item.candidate_id for item in candidates])
            parsed = EvaluationInput(payload['context'], candidates)
        else:
            parsed = SpeechInput(**payload)
        return Request(doc['request_id'], doc['provider_id'], doc['model_version'],
                       doc['catalog_version'], doc['budget_ms'], parsed)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise GatewayError('invalid_request') from None


def _envelope(request):
    return {'version': 1, 'request_id': request.request_id, 'service': request.service,
            'provider_id': request.provider_id, 'model_version': request.model_version,
            'catalog_version': request.catalog_version}


def request_bytes(request: Request) -> bytes:
    try:
        if type(request) is not Request:
            raise ValueError
        doc = {**_envelope(request), 'budget_ms': request.budget_ms, 'payload': asdict(request.payload)}
        raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        parse_request(raw)
        return raw
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise GatewayError('invalid_request') from None


def parse_response(raw: bytes, request: Request) -> Reply:
    try:
        limit = LIMITS['audio_response_bytes'] if request.service == 'tts' else LIMITS['text_response_bytes']
        doc = _load(raw, limit)
        _check(doc, _SCHEMA['$defs']['response'])
        if any(doc[key] != value for key, value in _envelope(request).items()):
            raise ValueError
        if doc['status'] == 'error':
            return RemoteError(doc['code'])
        result = doc['result']
        if request.service == 'llm':
            selected = result['candidate_id']
            if selected is not None and selected not in request.payload.candidates:
                raise ValueError
            return LlmOutput(result['text'], selected)
        if request.service == 'evaluator':
            scores = tuple(Score(**item) for item in result['scores'])
            ids = [item.candidate_id for item in scores]
            _unique(ids)
            if set(ids) != {item.candidate_id for item in request.payload.candidates}:
                raise ValueError
            if result['selected_id'] is not None and result['selected_id'] not in ids:
                raise ValueError
            return EvaluationOutput(scores, result['selected_id'])
        pcm = base64.b64decode(result['pcm_b64'], validate=True)
        if not 0 < len(pcm) <= LIMITS['pcm_bytes'] or len(pcm) % 2:
            raise ValueError
        if base64.b64encode(pcm).decode() != result['pcm_b64']:
            raise ValueError
        return SpeechOutput(pcm)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise GatewayError('invalid_response') from None


def response_bytes(request: Request, reply: Reply) -> bytes:
    try:
        doc = _envelope(request)
        if type(reply) is RemoteError:
            doc.update(status='error', code=reply.code)
        else:
            if type(reply) is SpeechOutput:
                result = {'pcm_b64': base64.b64encode(reply.pcm).decode(),
                          'sample_rate': 24000, 'channels': 1, 'sample_width': 2}
            elif type(reply) in (LlmOutput, EvaluationOutput):
                result = asdict(reply)
            else:
                raise ValueError
            doc.update(status='ok', result=result)
        raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        parse_response(raw, request)
        return raw
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise GatewayError('invalid_response') from None
