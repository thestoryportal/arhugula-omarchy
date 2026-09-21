"""Closed offline audio policy; no provider activation or output authority."""
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import re

from runtime.gateway.client import Failure
from runtime.gateway.wire import GatewayError, Request, SpeechInput, parse_request, request_bytes
from runtime.providers.configuration import Active, Disabled
from .conversation_records import ContextState, Snapshot, TurnToken, text


class Event(Enum):
    RESPONSE = 'response'
    STATUS = 'status'


class Phase(Enum):
    IDLE = 'idle'
    SYNTHESIZING = 'synthesizing'
    PLAYING = 'playing'
    STOPPING = 'stopping'
    FAULTED = 'faulted'


class Code(Enum):
    IDLE = 'tts.idle'
    STARTED = 'tts.started'
    PLAYING = 'tts.playing'
    PLAYED = 'tts.played'
    DEGRADED = 'tts.degraded'
    MUTED = 'tts.muted'
    SILENT = 'tts.silent'
    DENIED = 'tts.denied'
    STALE = 'tts.stale'
    UNAVAILABLE = 'tts.unavailable'
    INVALID_AUDIO = 'tts.invalid-audio'
    LIMIT = 'tts.limit'
    CANCELED = 'tts.canceled'
    BUSY = 'tts.busy'
    REPLAY = 'tts.replay'
    CLEANUP = 'tts.cleanup-unproven'


def _require(condition):
    if not condition:
        raise ValueError('tts.invalid-record')


def _id(value):
    _require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value) is not None)


def _number(value, ceiling=2**53 - 1):
    _require(type(value) is int and 0 < value <= ceiling)


@dataclass(frozen=True)
class Unchanged:
    pass


@dataclass(frozen=True)
class Pause:
    pass


@dataclass(frozen=True)
class Duck:
    gain_milli: int

    def __post_init__(self):
        _require(type(self.gain_milli) is int and 0 <= self.gain_milli < 1000)


MixIntent = Unchanged | Duck | Pause


@dataclass(frozen=True)
class RouteVoice:
    provider_id: str
    model_version: str
    voice: str

    def __post_init__(self):
        for value in (self.provider_id, self.model_version, self.voice):
            _id(value)


@dataclass(frozen=True)
class Spoken:
    event: Event
    voice: str
    mix: MixIntent

    def __post_init__(self):
        _require(type(self.event) is Event and type(self.mix) in (Unchanged, Duck, Pause))
        _id(self.voice)


@dataclass(frozen=True)
class Silent:
    event: Event

    def __post_init__(self):
        _require(type(self.event) is Event)


@dataclass(frozen=True)
class Limits:
    text_chars: int
    synthesis_ms: int
    synthesis_polls: int
    playback_polls: int

    def __post_init__(self):
        for value, ceiling in ((self.text_chars, 16384), (self.synthesis_ms, 30000),
                               (self.synthesis_polls, 1024), (self.playback_polls, 1024)):
            _number(value, ceiling)


@dataclass(frozen=True)
class AudioPolicy:
    profile_id: str
    policy_id: str
    revision: int
    configuration_revision: int
    rules: tuple[Spoken | Silent, ...]
    voices: tuple[RouteVoice, ...]
    limits: Limits

    def __post_init__(self):
        _id(self.profile_id)
        _id(self.policy_id)
        _number(self.revision)
        _number(self.configuration_revision)
        _require(type(self.limits) is Limits)
        _require(type(self.rules) is tuple and len(self.rules) <= 2
                 and all(type(r) in (Spoken, Silent) for r in self.rules))
        _require(len({r.event for r in self.rules}) == len(self.rules))
        _require(type(self.voices) is tuple and len(self.voices) <= 4
                 and all(type(v) is RouteVoice for v in self.voices))
        _require(len(set(self.voices)) == len(self.voices))


@dataclass(frozen=True)
class AudioSnapshot:
    conversation: Snapshot = field(repr=False)
    current_turn: TurnToken | None
    policy: AudioPolicy | None
    muted: bool

    def __post_init__(self):
        _require(type(self.conversation) is Snapshot)
        _require(self.current_turn is None or type(self.current_turn) is TurnToken)
        _require(self.policy is None or type(self.policy) is AudioPolicy)
        _require(type(self.muted) is bool)


@dataclass(frozen=True)
class Utterance:
    token: TurnToken
    event: Event
    text: str = field(repr=False)

    def __post_init__(self):
        _require(type(self.token) is TurnToken and type(self.event) is Event)
        try:
            text(self.text)
        except ValueError:
            raise ValueError('tts.invalid-record') from None


@dataclass(frozen=True)
class Notice:
    phase: Phase
    code: Code

    def __post_init__(self):
        _require(type(self.phase) is Phase and type(self.code) is Code)


@dataclass(frozen=True)
class Completion:
    code: Code
    provider_id: str | None
    model_version: str | None
    failures: tuple[Failure, ...]

    def __post_init__(self):
        _require(type(self.code) is Code)
        _require((self.provider_id is None) == (self.model_version is None))
        if self.provider_id is not None:
            _id(self.provider_id)
            _id(self.model_version)
        _require(type(self.failures) is tuple and len(self.failures) <= 3
                 and all(type(f) is Failure for f in self.failures))
        for failure in self.failures:
            _id(failure.provider_id)
            _id(failure.model_version)
            _require(type(failure.code) is str and GatewayError(failure.code).code == failure.code)


@dataclass(frozen=True)
class Denied:
    code: Code

    def __post_init__(self):
        _require(type(self.code) is Code)


@dataclass(frozen=True)
class Ready:
    request: Request = field(repr=False)
    mix: MixIntent

    def __post_init__(self):
        _require(type(self.mix) in (Unchanged, Duck, Pause))
        try:
            # [LAW:parse-dont-validate] Direct construction retains the same wire proof.
            parsed = parse_request(request_bytes(self.request))
        except GatewayError:
            raise ValueError('tts.invalid-record') from None
        _require(type(parsed.payload) is SpeechInput)
        object.__setattr__(self, 'request', parsed)


Admission = Denied | Ready


def request_id(token: TurnToken, event: Event) -> str:
    _require(type(token) is TurnToken and type(event) is Event)
    # [LAW:single-enforcer] Gateway replay owns attempts; content cannot change identity.
    raw = json.dumps([1, asdict(token), event.value], sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return 'tts-' + hashlib.sha256(raw).hexdigest()


def admit(utterance: Utterance, snapshot: AudioSnapshot,
          active: Active | Disabled, catalog_version: int) -> Admission:
    """Pure crossing to a wire-proven request; owner freshness belongs to TtsOutput."""
    _require(type(utterance) is Utterance and type(snapshot) is AudioSnapshot)
    _require(type(active) in (Active, Disabled))
    if snapshot.muted:
        return Denied(Code.MUTED)
    p, c, t = snapshot.policy, snapshot.conversation, utterance.token
    if (p is None or c.policy is None or not c.profile.enabled or not c.profile.voice_enabled
            or p.profile_id != c.profile.profile_id or p.policy_id != c.profile.policy_id
            or c.policy.profile_id != c.profile.profile_id or c.policy.policy_id != c.profile.policy_id):
        return Denied(Code.DENIED)
    if c.context.state is ContextState.UNAVAILABLE:
        return Denied(Code.UNAVAILABLE)
    if (t != snapshot.current_turn or t.profile_id != c.profile.profile_id
            or t.profile_revision != c.revision or t.policy_revision != c.policy.revision
            or t.context_revision != c.context.revision):
        return Denied(Code.STALE)
    rule = next((r for r in p.rules if r.event is utterance.event), Silent(utterance.event))
    if type(rule) is Silent:
        return Denied(Code.SILENT)
    if type(active) is Disabled:
        return Denied(Code.UNAVAILABLE)
    if p.configuration_revision != active.revision:
        return Denied(Code.DENIED)
    candidate = active.candidate
    routes = (candidate.host,) if candidate.local is None else (candidate.host, candidate.local)
    for spoken in (r for r in p.rules if type(r) is Spoken):
        if any(RouteVoice(route.provider.provider_id, route.provider.model_version,
                          spoken.voice) not in p.voices for route in routes):
            return Denied(Code.DENIED)
    if len(utterance.text) > p.limits.text_chars:
        return Denied(Code.LIMIT)
    request = Request(request_id(t, utterance.event), candidate.host.provider.provider_id,
                      candidate.host.provider.model_version, catalog_version,
                      p.limits.synthesis_ms, SpeechInput(utterance.text, rule.voice))
    try:
        return Ready(request, rule.mix)
    except ValueError:
        return Denied(Code.LIMIT)
