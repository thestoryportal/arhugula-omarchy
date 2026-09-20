import json
from pathlib import Path
import struct
import unittest

from runtime.voice.capture import CommandCapture, Frame
from runtime.voice.pcm import EnergyVad, PcmFramer


class PcmTests(unittest.TestCase):
    def test_pipe_fragmentation_preserves_exact_frame_bytes(self):
        frame = bytes(range(256)) * 2 + bytes(range(128))
        framer = PcmFramer()
        self.assertEqual(framer.feed(frame[:639]), [])
        self.assertEqual(framer.feed(frame[639:]), [frame])
        framer.finish()

    def test_max_chunk_keeps_only_a_subframe_remainder(self):
        framer = PcmFramer()
        self.assertEqual(framer.feed(bytes(65536)), [bytes(640)] * 102)
        self.assertEqual(framer.feed(bytes(384)), [bytes(640)])
        framer.finish()

    def test_byte_at_a_time_keeps_order_without_padding(self):
        framer = PcmFramer()
        output = []
        for value in b'\x34\x12' * 640:
            output.extend(framer.feed(bytes([value])))
        self.assertEqual(output, [b'\x34\x12' * 320] * 2)
        framer.finish()

    def test_invalid_input_faults_parser_and_discards_partial_data(self):
        for chunk in (None, "audio", bytearray(640), memoryview(bytes(640)), bytes(65537)):
            with self.subTest(kind=type(chunk)):
                framer = PcmFramer()
                framer.feed(b'\x01')
                with self.assertRaises(ValueError):
                    framer.feed(chunk)
                with self.assertRaises(ValueError):
                    framer.feed(bytes(639))

    def test_partial_finish_rejects_and_cannot_be_reused(self):
        framer = PcmFramer()
        framer.feed(bytes(639))
        with self.assertRaises(ValueError):
            framer.finish()
        with self.assertRaises(ValueError):
            framer.feed(b'\x00')

    def test_empty_chunk_and_clean_finish_never_fabricate_audio(self):
        framer = PcmFramer()
        self.assertEqual(framer.feed(b''), [])
        framer.finish()
        framer.finish()
        with self.assertRaises(ValueError):
            framer.feed(bytes(640))

    def test_vad_uses_signed_little_endian_rms_and_inclusive_threshold(self):
        self.assertFalse(EnergyVad(0.02).is_speech(bytes(640)))
        self.assertFalse(EnergyVad(0.01).is_speech(b'\x00\x01' * 320))
        self.assertTrue(EnergyVad(1 / 128).is_speech(b'\x00\xff' * 320))
        self.assertTrue(EnergyVad(0.99).is_speech(b'\x00\x80' * 320))
        self.assertTrue(EnergyVad(0.99).is_speech(b'\xff\x7f' * 320))
        self.assertFalse(EnergyVad(0.03).is_speech(struct.pack('<hh', 1000, 0) * 160))

    def test_vad_rejects_nonfinite_boolean_out_of_range_thresholds(self):
        for threshold in (True, False, None, "0.02", 0, 1, -0.1, 1.1, float('inf'), float('nan')):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                EnergyVad(threshold)

    def test_vad_rejects_invalid_frame_geometry_and_mutable_input(self):
        detector = EnergyVad(0.02)
        for pcm in (b'', bytes(639), bytes(641), bytes(1280), bytearray(640), None):
            with self.subTest(kind=type(pcm)), self.assertRaises(ValueError):
                detector.is_speech(pcm)

    def test_synthetic_replay_bounds_silence_and_adaptive_end(self):
        path = Path(__file__).parent / 'fixtures/voice-replay/manifest.json'
        manifest = json.loads(path.read_text())
        for case in manifest['cases']:
            with self.subTest(case=case['name']):
                capture = CommandCapture()
                capture.key_equal()
                detector = EnergyVad(manifest['threshold_rms'])
                for run in case['runs']:
                    pcm = struct.pack('<h', run['sample']) * 320
                    for _ in range(run['frames']):
                        result = capture.feed(Frame(pcm, detector.is_speech(pcm)))
                self.assertEqual(result.status, case['status'])
                self.assertEqual(result.reason, case['reason'])
                self.assertEqual(len(result.audio), case['audio_bytes'])
                self.assertLessEqual(capture.buffered_bytes, 480000)

    def test_cancel_discards_framed_capture_and_rejects_late_audio(self):
        framer, capture = PcmFramer(), CommandCapture()
        capture.key_equal()
        for pcm in framer.feed(struct.pack('<h', 1000) * 320):
            capture.feed(Frame(pcm, EnergyVad(0.02).is_speech(pcm)))
        self.assertEqual(capture.cancel().status, 'canceled')
        self.assertEqual(capture.buffered_bytes, 0)
        self.assertEqual(capture.feed(Frame(bytes(640), False)).status, 'blocked')


if __name__ == '__main__':
    unittest.main()
