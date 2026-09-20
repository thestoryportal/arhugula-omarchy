import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from ops.voice_replay import run_synthetic


class ReplayTests(unittest.TestCase):
    def manifest(self):
        return json.loads((Path(__file__).parent / 'fixtures/voice-replay/manifest.json').read_text())

    def test_synthetic_report_is_offline_and_has_no_audio_or_transcript(self):
        with patch('subprocess.Popen', side_effect=AssertionError('unexpected external process')):
            report = run_synthetic(self.manifest())
        self.assertTrue(report['passed'])
        self.assertFalse(report['real_speech_validated'])
        self.assertEqual(report['mode'], 'synthetic')
        self.assertEqual(len(report['cases']), 5)
        self.assertEqual(report['cases'][-1]['audio_bytes'], 480000)
        self.assertNotIn('transcript', json.dumps(report))

    def test_fixture_mismatch_is_reported_without_false_pass(self):
        manifest = self.manifest()
        manifest['cases'][0]['audio_bytes'] = 640
        self.assertFalse(run_synthetic(manifest)['passed'])

    def test_malformed_or_excessive_fixture_is_rejected(self):
        for value in (True, 0, 751, '750'):
            manifest = self.manifest()
            manifest['cases'][0]['runs'][0]['frames'] = value
            with self.assertRaises(ValueError):
                run_synthetic(manifest)
        manifest = self.manifest()
        manifest['production_calibrated'] = True
        with self.assertRaises(ValueError):
            run_synthetic(manifest)

    def test_cli_is_synthetic_by_default(self):
        result = subprocess.run([sys.executable, '-m', 'ops.voice_replay'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])


if __name__ == '__main__':
    unittest.main()
