"""Replay the repository's synthetic constant-PCM fixtures; never open a device."""
import argparse
import json
from pathlib import Path
import re
import struct

from runtime.voice.capture import CommandCapture, Frame
from runtime.voice.pcm import EnergyVad, PcmFramer


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


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    path = Path(__file__).resolve().parents[1] / 'tests/fixtures/voice-replay/manifest.json'
    try:
        report = run_synthetic(json.loads(path.read_text()))
    except (ValueError, OSError):
        print(json.dumps({'mode': 'synthetic', 'passed': False, 'error': 'fixture.invalid'}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
