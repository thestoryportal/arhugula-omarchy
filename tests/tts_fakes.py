"""In-memory TTS effects surrounding real gateway/configuration/owner objects."""
from dataclasses import replace

from runtime.contracts import encode
from runtime.evaluation import ReplayRun
from runtime.gateway.admission import Admission, Bearer
from runtime.gateway.client import Endpoint, Host, Local, HttpReply, GatewayClient
from runtime.gateway.wire import SpeechOutput, RemoteError, response_bytes
from runtime.providers.configuration import Configuration, Evidence
from runtime.providers.records import parse_manifest, parse_policy
from runtime.voice.conversation_records import TurnToken
from runtime.voice.session import SessionOwner
from runtime.voice.tts_records import (
    AudioPolicy, AudioSnapshot, Event, Limits, RouteVoice, Spoken, Unchanged, Utterance,
)
from tests.test_conversation_records import fixture
from tests.test_gateway_wire import host_provider
from tests.test_provider_records import manifest_doc, policy_doc


PCM = b'\x00\x00' * 240
PEER = 'a' * 64


class Clock:
    now = 1000

    def __call__(self):
        return self.now


class Job:
    def __init__(self, rig, kind):
        self.rig, self.kind = rig, kind
        self.request = None
        self.clean = True
        self.cancels = 0

    def poll(self):
        self.rig.effect(self.kind + '.poll')
        reply = self.rig.replies[self.kind]
        raw = reply(self.request) if callable(reply) else (
            None if reply is None else response_bytes(self.request, reply))
        if self.kind == 'host' and raw is not None:
            return HttpReply(self.rig.http_status, raw, PEER)
        return raw

    def cancel(self):
        self.cancels += 1
        self.rig.effect(self.kind + '.cancel')
        return self.clean


class Transport:
    peer_identity = PEER

    def __init__(self, rig, admission):
        self.rig, self.admission = rig, admission

    def begin(self, outgoing):
        request = self.admission.admit(outgoing.authorization, outgoing.body).request
        self.rig.host_requests.append(request)
        self.rig.host_job.request = request
        self.rig.effect('host.begin')
        return self.rig.host_job


class Player:
    def __init__(self, rig):
        from runtime.voice.tts import PlaybackState
        self.rig, self.state = rig, PlaybackState.PENDING
        self.clean, self.cancels, self.audio = True, 0, None

    def start(self, audio):
        self.audio = audio
        self.rig.effect('player.start')

    def poll(self):
        self.rig.effect('player.poll')
        return self.state

    def cancel(self):
        self.cancels += 1
        self.rig.effect('player.cancel')
        return self.clean


class Mix:
    def __init__(self, rig):
        self.rig, self.saved = rig, {}
        self.restore_result, self.restores = True, 0

    def apply(self, intent):
        from runtime.voice.tts_records import Duck, Pause
        if type(intent) is Duck:
            self.saved = {'gain': self.rig.media['gain']}
            self.rig.media['gain'] = self.rig.media['gain'] * intent.gain_milli // 1000
        elif type(intent) is Pause:
            self.saved = {'paused': self.rig.media['paused']}
            self.rig.media['paused'] = True
        self.rig.effect('mix.apply')

    def restore(self):
        self.restores += 1
        self.rig.effect('mix.restore')
        if self.restore_result is True:
            self.rig.media.update(self.saved)
            self.saved = {}
        return self.restore_result


class Rig:
    def __init__(self, *, fallback=False, mix=None):
        from runtime.voice.tts import TtsOutput
        self.events, self.hooks = [], {}
        self.host_requests, self.local_requests = [], []
        self.replies = {'host': SpeechOutput(PCM), 'local': SpeechOutput(PCM)}
        self.http_status, self.clock = 200, Clock()
        self.media = {'gain': 900, 'paused': False, 'unrelated': 'untouched'}
        self.player, self.mix = Player(self), Mix(self)
        self.host_job, self.local_job = Job(self, 'host'), Job(self, 'local')
        self.owner = SessionOwner()
        self.generation = self.owner.begin('conversation')
        self.token = TurnToken(self.owner.session_id + ':1', 1, self.generation,
                               'personal', 1, 1, 1)
        bearer = Bearer('s' * 32)
        provider = host_provider()
        transport = Transport(self, Admission(provider, 7, bearer))
        host = Host(provider, Endpoint('https://host.test/v1/gateway', PEER), bearer, transport)
        local_provider = host_provider(provider_id='vm', placement='vm')
        local = Local(local_provider, self.local_begin) if fallback else None
        self.gateway = GatewayClient(host, 7, self.clock, local)
        self.configuration = Configuration(self.gateway)
        manifests = tuple(parse_manifest(manifest_doc(provider=encode(replace(
            p, enabled=False, health='unavailable')))) for p in
            ((provider, local_provider) if fallback else (provider,)))
        evidence = tuple(Evidence(m.digest, 'b' * 64, ReplayRun(
            'm1', 'synthetic', 'tts-test', True, True, True, {'safe': 'pass'}, True),
            ('offline-reviewer',)) for m in manifests)
        self.candidate = self.configuration.stage(
            manifests[0], host, policy=parse_policy(policy_doc()), evidence=evidence,
            local_manifest=manifests[-1] if fallback else None, local=local)
        for manifest in manifests:
            self.configuration.observe(self.candidate, manifest.provider.provider_id,
                                       status='healthy', observed_at_ms=1000)
        self.configuration.activate(self.candidate,
                                    self.configuration.approve_bootstrap(self.candidate), now_ms=1000)
        voices = tuple(RouteVoice(m.provider.provider_id, 'm1', 'natural') for m in manifests)
        policy = AudioPolicy('personal', 'local', 1, 1,
                             (Spoken(Event.RESPONSE, 'natural', Unchanged() if mix is None else mix),),
                             voices, Limits(16384, 30000, 8, 8))
        self.snapshot = AudioSnapshot(fixture(), self.token, policy, False)
        self.output = TtsOutput(self.owner, self.gateway, self.configuration, 7,
                                self.sample, self.players, self.mixes)

    def effect(self, name):
        self.events.append(name)
        hook = self.hooks.get(name)
        if hook:
            hook()

    def sample(self):
        self.effect('snapshot')
        return self.snapshot

    def players(self):
        self.effect('player.factory')
        return self.player

    def mixes(self):
        self.effect('mix.factory')
        return self.mix

    def local_begin(self, request, budget):
        self.local_requests.append(request)
        self.local_job.request = request
        self.effect('local.begin')
        return self.local_job

    def utterance(self, text='answer', event=Event.RESPONSE):
        return Utterance(self.token, event, text)

    def next_turn(self):
        self.token = replace(self.token, turn=self.token.turn + 1)
        self.snapshot = replace(self.snapshot, current_turn=self.token)

    def host_audio(self, pcm):
        self.replies['host'] = SpeechOutput(pcm)

    def host_error(self, code):
        self.replies['host'] = RemoteError(code)

    def local_audio(self, pcm):
        self.replies['local'] = SpeechOutput(pcm)
