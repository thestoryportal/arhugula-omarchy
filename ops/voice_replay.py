"""Replay the repository's synthetic constant-PCM fixtures; never open a device."""
import argparse
import json
from pathlib import Path
import re
import struct

from runtime.voice.capture import CommandCapture, Frame
from runtime.voice.pcm import EnergyVad, PcmFramer
from runtime.contracts import Capability, Policy, Profile, VoiceObservation
from runtime.core import ControlPlane, Outcome
from runtime.journal import MemoryJournal
from runtime.voice.coordinator import Coordinator
from runtime.voice.process import ProcessResult
from runtime.voice.router import Action, VoiceRouter, VoiceState
from runtime.voice.session import SessionOwner
from runtime.voice.transcription import TranscriptionJob


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('invalid synthetic fixture shape')


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('invalid synthetic fixture bound')


def run_synthetic(manifest: dict) -> dict:
    _shape(manifest, 'version source sample_rate channels frame_samples threshold_rms production_calibrated cases')
    for key, expected in (('version', 1), ('sample_rate', 16000), ('channels', 1), ('frame_samples', 320)):
        _integer(manifest[key], expected, expected)
    if manifest['production_calibrated'] is not False or type(manifest['source']) is not str:
        raise ValueError('synthetic fixture cannot establish production accuracy')
    cases = manifest['cases']
    if type(cases) is not list or not 1 <= len(cases) <= 32:
        raise ValueError('invalid synthetic case count')
    detector = EnergyVad(manifest['threshold_rms'])
    names = set()
    for case in cases:
        _shape(case, 'name runs status reason audio_bytes')
        name = case['name']
        if type(name) is not str or not re.fullmatch('[a-z0-9-]{1,80}', name) or name in names:
            raise ValueError('invalid synthetic case name')
        names.add(name)
        if case['status'] not in ('idle', 'processing') or case['reason'] not in ('initial-silence', 'silence', 'max-duration'):
            raise ValueError('invalid synthetic expected result')
        _integer(case['audio_bytes'], 0, 480000)
        if type(case['runs']) is not list or not 1 <= len(case['runs']) <= 16:
            raise ValueError('invalid synthetic run count')
        total = 0
        for run in case['runs']:
            _shape(run, 'sample frames')
            _integer(run['sample'], -32768, 32767)
            _integer(run['frames'], 1, 750)
            total += run['frames']
        _integer(total, 1, 750)
    reports = []
    for case in cases:
        framer, capture = PcmFramer(), CommandCapture()
        result = capture.key_equal()
        for run in case['runs']:
            pcm = struct.pack('<h', run['sample']) * 320
            for _ in range(run['frames']):
                for frame in framer.feed(pcm):
                    result = capture.feed(Frame(frame, detector.is_speech(frame)))
        framer.finish()
        actual = {'status': result.status, 'reason': result.reason, 'audio_bytes': len(result.audio)}
        reports.append({'name': case['name'], **actual,
                        'passed': all(actual[key] == case[key] for key in actual)})
    return {'version': 1, 'mode': 'synthetic', 'real_speech_validated': False,
            'passed': all(case['passed'] for case in reports), 'cases': reports}


def run_coordinator_synthetic() -> dict:
    """Fixed in-memory corpus exercises real composition, not ASR accuracy."""
    cases = (
        ('exact', b'show menu', 1), ('unknown', b'purple garden', 0),
        ('negative', b'do not show menu', 0), ('canceled', b'show menu', 0),
        ('silence', b'show menu', 0), ('confirmation-denied', b'show menu', 0),
    )
    reports = []
    for name, text, expected in cases:
        journal, calls = MemoryJournal(), []
        context = {'session_id': 'synthetic-session', 'profile_id': 'synthetic',
                   'lane_id': None, 'agent_id': None, 'source': 'voice',
                   'provider_id': None, 'model_version': None,
                   'provenance': 'synthetic-replay', 'sensitivity': 'private'}
        plane = ControlPlane(
            [Capability(1, 'menu.open', 1, True, 'confirm' if name == 'confirmation-denied' else 'safe',
                        {'name': 'string'}, 'synthetic-replay')],
            Policy(1, 'synthetic', 1, True, ('menu.open',), ()),
            lambda command: calls.append(command) or Outcome('success'), journal,
            profile=Profile(1, 'synthetic', 'synthetic', True, True))
        router = VoiceRouter(plane, [Action('menu.open', 1, {'name': 'main'}, ('show menu',), 'Menu')],
                             lambda: VoiceState(context, 'synthetic-epoch-1', 'synthetic-turn'),
                             lambda prompt: None)

        class ReplayWorker:
            def start(self, data):
                pass

            def poll(self):
                return ProcessResult('success', text, 'process.ok')

            def cancel(self):
                return ProcessResult('canceled', b'', 'process.canceled')

        coordinator = Coordinator(SessionOwner(), CommandCapture(), router,
                                  lambda: TranscriptionJob(worker_factory=ReplayWorker),
                                  journal.append)
        generation = coordinator.activate()
        if name == 'silence':
            for _ in range(150):
                coordinator.feed(generation, Frame(bytes(640), False))
        else:
            coordinator.feed(generation, Frame(b'\x00\x10' * 320, True))
            for _ in range(35):
                coordinator.feed(generation, Frame(bytes(640), False))
        if name == 'canceled':
            coordinator.cancel()
        reply = coordinator.poll()
        if name == 'confirmation-denied' and reply and reply.status == 'preview':
            coordinator.confirm(reply.token, 'panel', False)
        events = [event for _, event in journal.read()]
        correlated = len({event.correlation_id for event in events}) == 1
        reports.append({'name': name, 'executions': len(calls),
                        'observations': sum(isinstance(e, VoiceObservation) for e in events),
                        'passed': len(calls) == expected and coordinator.phase == 'idle' and correlated})
        journal.close()
    return {'version': 1, 'mode': 'synthetic-coordinator', 'real_speech_validated': False,
            'passed': all(case['passed'] for case in reports), 'cases': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coordinator', action='store_true', help='run fixed synthetic coordinator cases')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / 'tests/fixtures/voice-replay/manifest.json'
    try:
        report = (run_coordinator_synthetic() if args.coordinator else
                  run_synthetic(json.loads(path.read_text())))
    except (ValueError, OSError):
        print(json.dumps({'mode': 'synthetic', 'passed': False, 'error': 'fixture.invalid'}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
