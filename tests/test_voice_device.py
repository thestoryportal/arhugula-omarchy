import unittest

from runtime.voice.device import CaptureIOError, PipeWireCapture
from runtime.voice.process import ProcessResult


class FakeWorker:
    def __init__(self):
        self.result = None
        self.cancel_result = ProcessResult('canceled', b'', 'process.canceled')
        self.started = False

    def start(self, data):
        if data is not None:
            raise AssertionError('capture must not receive stdin data')
        self.started = True

    def poll(self):
        return self.result

    def cancel(self):
        return self.cancel_result


class CaptureTests(unittest.TestCase):
    def capture(self):
        worker, calls = FakeWorker(), []
        def factory(argv, **kwargs):
            calls.append((argv, kwargs))
            return worker
        capture = PipeWireCapture(worker_factory=factory)
        capture.start('approved.node')
        return capture, worker, calls

    def test_explicit_factory_and_source_are_required(self):
        with self.assertRaises(ValueError):
            PipeWireCapture()
        for source in ('', 'default', '0', '--remote=other', 'node;sh', None):
            with self.subTest(source=source):
                capture = PipeWireCapture(worker_factory=lambda *a, **k: self.fail('invalid source launched'))
                with self.assertRaises(ValueError):
                    capture.start(source)

    def test_fixed_argv_limits_and_fragmented_stream(self):
        capture, worker, calls = self.capture()
        argv, options = calls[0]
        self.assertEqual(argv, ('/usr/bin/pw-record', '--rate', '16000', '--channels', '1',
                                '--format', 's16', '--raw', '--target', 'approved.node',
                                '--sample-count', '240000', '-'))
        self.assertEqual((options['max_stdout'], options['timeout_s'], options['idle_timeout_s']), (480000, 15, 1))
        receive = options['stdout_consumer']
        receive(bytes(639))
        self.assertEqual(capture.poll(), [])
        receive(b'\x00')
        self.assertEqual(capture.poll(), [bytes(640)])
        worker.result = ProcessResult('success', b'', 'process.ok')
        self.assertEqual(capture.poll(), [])
        self.assertTrue(capture.cancel())

    def test_queue_overflow_discards_whole_turn(self):
        capture, worker, calls = self.capture()
        receive = calls[0][1]['stdout_consumer']
        receive(bytes(640 * 16))
        with self.assertRaises(CaptureIOError):
            receive(bytes(640))
        with self.assertRaises(CaptureIOError):
            capture.poll()
        self.assertTrue(capture.cancel())

    def test_partial_eof_and_empty_capture_fail(self):
        for data in (b'', b'\x00'):
            capture, worker, calls = self.capture()
            if data:
                calls[0][1]['stdout_consumer'](data)
            worker.result = ProcessResult('success', b'', 'process.ok')
            with self.assertRaises(CaptureIOError):
                capture.poll()

    def test_total_duration_is_independently_bounded(self):
        capture, _, calls = self.capture()
        receive = calls[0][1]['stdout_consumer']
        for _ in range(750):
            receive(bytes(640))
            self.assertEqual(capture.poll(), [bytes(640)])
        with self.assertRaises(CaptureIOError):
            receive(bytes(640))

    def test_cancel_drops_pending_frames_and_rejects_late_audio(self):
        capture, _, calls = self.capture()
        receive = calls[0][1]['stdout_consumer']
        receive(bytes(640))
        self.assertTrue(capture.cancel())
        self.assertEqual(capture.poll(), [])
        with self.assertRaises(CaptureIOError):
            receive(bytes(640))
        with self.assertRaises(CaptureIOError):
            capture.start('approved.node')

    def test_cleanup_failure_is_not_reported_as_success(self):
        capture, worker, _ = self.capture()
        worker.cancel_result = ProcessResult('uncertain', b'', 'process.cleanup-unproven')
        self.assertFalse(capture.cancel())
        self.assertFalse(capture.cancel())

    def test_source_failure_does_not_release_pending_audio(self):
        capture, worker, calls = self.capture()
        calls[0][1]['stdout_consumer'](bytes(640))
        worker.result = ProcessResult('failed', b'', 'process.exit')
        with self.assertRaises(CaptureIOError):
            capture.poll()


if __name__ == '__main__':
    unittest.main()
