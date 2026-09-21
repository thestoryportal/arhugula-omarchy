"""Exercise only packaged TTS with constant PCM and inert Python collaborators."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    archive = Path(sys.argv[1]).resolve(strict=True)
    checkout = Path(__file__).resolve().parents[1]
    sys.path[:] = [str(archive)] + [p for p in sys.path if p and
                                  not Path(p).resolve().is_relative_to(checkout)]
    import runtime
    import schemas
    assert str(archive) in runtime.__file__
    assert str(archive) in schemas.__file__
    from runtime.contracts import Profile, Provider
    from runtime.evaluation import ReplayRun
    from runtime.gateway.admission import Admission, Bearer
    from runtime.gateway.client import Endpoint, GatewayClient, Host, HttpReply, Local
    from runtime.gateway.wire import RemoteError, SpeechOutput, response_bytes
    from runtime.providers.configuration import Configuration, Evidence
    from runtime.providers.records import Manifest, Policy, Resources
    from runtime.voice.conversation_records import (
        Context, ContextState, ConversationPolicy, Entry, Limits as ConversationLimits,
        SetupEvidence, Snapshot, TurnToken,
    )
    from runtime.voice.session import SessionOwner
    from runtime.voice.tts import PlaybackState, TtsOutput
    from runtime.voice.tts_records import (
        AudioPolicy, AudioSnapshot, Code, Duck, Event, Limits, RouteVoice, Spoken, Utterance,
    )

    pcm, peer = b'\x00\x00' * 240, 'a' * 64

    class Job:
        def __init__(self, reply, host):
            self.reply, self.host, self.request, self.cancels = reply, host, None, 0

        def poll(self):
            raw = response_bytes(self.request, self.reply)
            return HttpReply(200, raw, peer) if self.host else raw

        def cancel(self):
            self.cancels += 1
            return True

    for scenario in ('primary', 'fallback', 'mute', 'cancel'):
        owner = SessionOwner()
        generation = owner.begin('conversation')
        token = TurnToken(owner.session_id + ':1', 1, generation, 'p', 1, 1, 1)
        host_provider = Provider(1, 'host', 'host', 'm1', True, 'healthy', ('tts',))
        local_provider = replace(host_provider, provider_id='vm', placement='vm')
        bearer = Bearer('s' * 32)
        admission = Admission(host_provider, 7, bearer)
        host_job = Job(RemoteError('unavailable') if scenario == 'fallback'
                       else SpeechOutput(pcm), True)
        local_job = Job(SpeechOutput(pcm), False)
        calls = []

        def host_begin(outgoing):
            calls.append('host')
            host_job.request = admission.admit(outgoing.authorization, outgoing.body).request
            return host_job

        def local_begin(request, budget):
            calls.append('local')
            local_job.request = request
            return local_job

        host = Host(host_provider, Endpoint('https://offline.test/v1/gateway', peer), bearer,
                    SimpleNamespace(peer_identity=peer, begin=host_begin))
        local = Local(local_provider, local_begin) if scenario == 'fallback' else None
        gateway = GatewayClient(host, 7, lambda: 1000, local)
        configuration = Configuration(gateway)
        manifests = tuple(Manifest(replace(p, enabled=False, health='unavailable'), 'a' * 64,
                                   Resources(100, 0, 100, 100, 1)) for p in
                          ((host_provider, local_provider) if local else (host_provider,)))
        resources = Resources(1000, 1000, 1000, 1000, 1)
        evidence = tuple(Evidence(m.digest, 'b' * 64,
            ReplayRun('m1', 'synthetic', 'smoke', True, True, True, {'safe': 'pass'}, True),
            ('offline',)) for m in manifests)
        candidate = configuration.stage(manifests[0], host,
            policy=Policy(100, False, True, 'disabled', (), resources, resources), evidence=evidence,
            local_manifest=manifests[-1] if local else None, local=local)
        for manifest in manifests:
            configuration.observe(candidate, manifest.provider.provider_id,
                                  status='healthy', observed_at_ms=1000)
        configuration.activate(candidate, configuration.approve_bootstrap(candidate), now_ms=1000)
        conversation = Snapshot(Profile(1, 'p', 'policy', True, True), 1,
            ConversationPolicy('p', 'policy', 1, frozenset({Entry.PANEL}), 'end', 'F9',
                               ConversationLimits(4, 100, 1000, 4, 8)),
            SetupEvidence(1, frozenset(), frozenset()), Context(1, ContextState.EMPTY, ()))
        policy = AudioPolicy('p', 'policy', 1, 1, (Spoken(Event.RESPONSE, 'natural', Duck(500)),),
            tuple(RouteVoice(m.provider.provider_id, 'm1', 'natural') for m in manifests),
            Limits(100, 30000, 8, 8))
        snapshot = AudioSnapshot(conversation, token, policy, scenario == 'mute')
        effects = {'gain': 800, 'audio': None, 'cancels': 0, 'restores': 0}

        def play(audio):
            effects['audio'] = audio.pcm

        def cancel_player():
            effects['cancels'] += 1
            return True

        def apply(intent):
            effects['gain'] = 800 * intent.gain_milli // 1000

        def restore():
            effects['gain'] = 800
            effects['restores'] += 1
            return True

        player = SimpleNamespace(start=play, cancel=cancel_player,
                                 poll=lambda: PlaybackState.COMPLETE)
        mix = SimpleNamespace(apply=apply, restore=restore)
        output = TtsOutput(owner, gateway, configuration, 7, lambda: snapshot,
                           lambda: player, lambda: mix)
        started = output.start(Utterance(token, Event.RESPONSE, 'synthetic text'))
        if scenario == 'mute':
            assert not started and calls == [] and effects['audio'] is None
        else:
            assert started
            assert output.poll() is None
            if scenario == 'fallback':
                assert output.poll() is None
            assert effects['audio'] == pcm and effects['gain'] == 400
            if scenario == 'cancel':
                output.cancel()
            result = output.poll()
            expected = {'primary': Code.PLAYED, 'fallback': Code.DEGRADED, 'cancel': Code.CANCELED}
            assert result.code is expected[scenario]
            assert effects['gain'] == 800 and effects['restores'] == 1 and effects['cancels'] == 1
            assert calls == (['host', 'local'] if scenario == 'fallback' else ['host'])
        assert output.cleanup_proven and owner.accepts(generation)
        assert output.poll() is None
        print('PASS packaged:', scenario)
    print('Packaged runtime:', runtime.__file__)


if __name__ == '__main__':
    main()
