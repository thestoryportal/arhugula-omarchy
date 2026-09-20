import io
import unittest
import wave

from runtime.voice.process import ProcessResult
from runtime.voice.transcription import TranscriptionJob


class TranscriptionTests(unittest.TestCase):
    def job(self):
        class Worker:
            result = None
            input = None
            def start(self, data): self.input = data
            def poll(self): return self.result
            def cancel(self): return ProcessResult('canceled', b'', 'process.canceled')
        worker = Worker()
        return TranscriptionJob(worker_factory=lambda: worker), worker

    def test_wav_encoding_and_transient_generation_preserving_result(self):
        job, worker = self.job()
        pcm = b'\x01\x00' * 320
        job.start(pcm, 7)
        with wave.open(io.BytesIO(worker.input), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth()), (1, 16000, 2))
            self.assertEqual(wav.readframes(320), pcm)
        self.assertIsNone(job.poll())
        worker.result = ProcessResult('success', b'open omarchy menu\n', 'process.ok')
        result = job.poll()
        self.assertEqual((result.generation, result.status, result.text), (7, 'success', 'open omarchy menu'))
        self.assertNotIn('open omarchy', repr(result))
        self.assertIsNone(job.poll())

    def test_cancel_discards_late_result(self):
        job, worker = self.job()
        job.start(bytes(640), 1)
        job.cancel()
        worker.result = ProcessResult('success', b'open omarchy menu', 'process.ok')
        self.assertIsNone(job.poll())
        with self.assertRaises(RuntimeError):
            job.start(bytes(640), 2)
        self.assertTrue(job.cleanup_proven)

    def test_cancel_cannot_hide_unproven_cleanup(self):
        job, worker = self.job()
        job.start(bytes(640), 1)
        worker.cancel = lambda: ProcessResult('uncertain', b'', 'process.cleanup-unproven')
        job.cancel()
        self.assertFalse(job.cleanup_proven)
        self.assertIsNone(job.poll())

    def test_invalid_pcm_or_generation_never_starts_worker(self):
        job, worker = self.job()
        for pcm in (b'', bytes(1), bytes(639), bytes(480001), bytearray(640), None):
            with self.assertRaises(ValueError): job.start(pcm, 1)
        for generation in (True, 0, -1, '1', None):
            with self.assertRaises(ValueError): job.start(bytes(640), generation)
        self.assertIsNone(worker.input)

    def test_missing_backend_does_not_discover_or_launch_voxtype(self):
        with self.assertRaises(ValueError): TranscriptionJob()

    def test_empty_invalid_utf8_oversize_and_nonzero_outputs_fail_privately(self):
        for status, data in (('success', b''), ('success', b'  \n'), ('success', b'\xff'),
                             ('success', b'x' * 16385), ('failed', b'private')):
            job, worker = self.job()
            job.start(bytes(640), 5)
            worker.result = ProcessResult(status, data, 'private diagnostic')
            result = job.poll()
            self.assertEqual(result.status, 'failed')
            self.assertIsNone(result.text)
            self.assertNotIn('private', repr(result))


if __name__ == '__main__':
    unittest.main()
