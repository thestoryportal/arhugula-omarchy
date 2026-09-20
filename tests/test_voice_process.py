import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from runtime.voice.process import OwnedProcess


class ProcessTests(unittest.TestCase):
    def worker(self, script, **kwargs):
        worker = OwnedProcess((sys.executable, '-c', script),
                              max_output=kwargs.get('max_output', 65536),
                              timeout_s=kwargs.get('timeout_s', 3))
        self.addCleanup(worker.cancel)
        return worker

    def wait(self, worker):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            result = worker.poll()
            if result is not None:
                return result
            time.sleep(0.01)
        self.fail('owned process did not settle within test bound')

    def test_success_uses_exact_argv_no_shell_and_private_output(self):
        calls = []
        real = subprocess.Popen
        def launch(*args, **kwargs):
            calls.append((args, kwargs))
            return real(*args, **kwargs)
        script = 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'
        worker = self.worker(script)
        with patch('runtime.voice.process.subprocess.Popen', side_effect=launch):
            worker.start(b'private transcript')
        result = self.wait(worker)
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.stdout, b'private transcript')
        self.assertNotIn('private transcript', repr(result))
        self.assertEqual(calls[0][0][0], (sys.executable, '-c', script))
        self.assertIs(calls[0][1]['shell'], False)
        self.assertIs(calls[0][1]['start_new_session'], True)

    def test_cancel_reaps_owned_child_and_cannot_restart(self):
        worker = self.worker('import time; time.sleep(60)')
        children = []
        real = subprocess.Popen
        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child
        with patch('runtime.voice.process.subprocess.Popen', side_effect=launch):
            worker.start(None)
        start = time.monotonic()
        self.assertEqual(worker.cancel().status, 'canceled')
        self.assertLess(time.monotonic() - start, 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertEqual(worker.poll().status, 'canceled')
        with self.assertRaises(RuntimeError):
            worker.start(None)

    def test_timeout_is_enforced_without_caller_polling(self):
        worker = self.worker('import time; time.sleep(60)', timeout_s=0.05)
        worker.start(None)
        time.sleep(0.4)
        result = worker.poll()
        self.assertIsNotNone(result)
        self.assertEqual((result.status, result.code, result.stdout), ('failed', 'process.timeout', b''))

    def test_stdout_and_stderr_overflow_fail_without_leaking(self):
        for fd in (1, 2):
            with self.subTest(fd=fd):
                worker = self.worker(f'import os; os.write({fd}, b"private" * 10000)', max_output=32)
                worker.start(None)
                result = self.wait(worker)
                self.assertEqual((result.status, result.code), ('failed', 'process.output-limit'))
                self.assertEqual(result.stdout, b'')
                self.assertNotIn('private', repr(result))

    def test_nonzero_and_missing_executable_are_safe_failures(self):
        worker = self.worker('import sys; print("private"); sys.exit(7)')
        worker.start(None)
        result = self.wait(worker)
        self.assertEqual((result.status, result.code, result.stdout), ('failed', 'process.exit', b''))
        missing = OwnedProcess(('/nonexistent/arhugula-test',), max_output=10, timeout_s=1)
        missing.start(None)
        self.assertEqual(missing.poll().code, 'process.start-failed')

    def test_cancel_before_start_never_launches(self):
        worker = self.worker('raise AssertionError("must not run")')
        self.assertEqual(worker.cancel().status, 'canceled')
        with self.assertRaises(RuntimeError):
            worker.start(None)

    def test_invalid_configuration_and_input_are_rejected_before_launch(self):
        for argv in ([], ('relative',), ('/bin/true', 1), ('/bin/true', '\x00'), ('',)):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                OwnedProcess(argv, max_output=10, timeout_s=1)
        for bound in (True, 0, -1, 65537):
            with self.assertRaises(ValueError):
                OwnedProcess((sys.executable,), max_output=bound, timeout_s=1)
        for timeout in (True, 0, -1, 31, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                OwnedProcess((sys.executable,), max_output=10, timeout_s=timeout)
        worker = self.worker('pass')
        for data in ('text', bytearray(1), bytes(480045)):
            with self.assertRaises(ValueError):
                worker.start(data)
        worker.start(None)
        self.assertEqual(self.wait(worker).status, 'success')

    def test_foreign_process_cannot_cancel_or_poll_owner(self):
        worker = self.worker('pass')
        creator = os.getpid()
        with patch('runtime.voice.process.os.getpid', return_value=creator + 1):
            for action in (worker.poll, worker.cancel, lambda: worker.start(None)):
                with self.assertRaises(RuntimeError):
                    action()

    def test_large_input_is_pumped_without_pipe_deadlock(self):
        worker = self.worker('import sys; print(len(sys.stdin.buffer.read()))')
        worker.start(bytes(480044))
        self.assertEqual(self.wait(worker).stdout, b'480044\n')

    def test_streaming_output_is_delivered_but_not_retained_in_receipt(self):
        chunks = []
        worker = OwnedProcess((sys.executable, '-c', 'import os; os.write(1, b"x" * 70000)'),
                              max_output=65536, timeout_s=3,
                              stdout_consumer=chunks.append, max_stdout=80000, idle_timeout_s=1)
        self.addCleanup(worker.cancel)
        worker.start(None)
        result = self.wait(worker)
        self.assertEqual((result.status, result.stdout), ('success', b''))
        self.assertEqual(b''.join(chunks), b'x' * 70000)

    def test_stream_consumer_failure_closes_process_and_sanitizes_error(self):
        def reject(chunk):
            raise ValueError('private audio')
        worker = OwnedProcess((sys.executable, '-c', 'print("pcm")'), max_output=100,
                              timeout_s=3, stdout_consumer=reject, max_stdout=100)
        self.addCleanup(worker.cancel)
        worker.start(None)
        result = self.wait(worker)
        self.assertEqual((result.status, result.code), ('failed', 'process.io-failed'))
        self.assertNotIn('private', repr(result))

    def test_silent_stream_stalls_independently_of_general_deadline(self):
        worker = OwnedProcess((sys.executable, '-c', 'import time; time.sleep(60)'),
                              max_output=100, timeout_s=3, stdout_consumer=lambda _: None,
                              max_stdout=100, idle_timeout_s=0.05)
        self.addCleanup(worker.cancel)
        worker.start(None)
        self.assertEqual(self.wait(worker).code, 'process.stalled')

    def test_invalid_stream_policy_rejects_before_launch(self):
        for kwargs in ({'stdout_consumer': 1}, {'max_stdout': 480001},
                       {'idle_timeout_s': True}, {'idle_timeout_s': 0},
                       {'stdout_consumer': lambda _: None, 'max_stdout': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                OwnedProcess((sys.executable,), max_output=100, timeout_s=1, **kwargs)

    def test_cancel_terminates_same_group_descendant_and_reaps_leader(self):
        script = '''import subprocess,sys,signal,time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
def stop(*args):
    child.wait(timeout=0.3)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
print("READY", flush=True)
time.sleep(60)
'''
        ready = threading.Event()
        worker = OwnedProcess((sys.executable, '-c', script), max_output=100,
                              timeout_s=3, stdout_consumer=lambda _: ready.set(), max_stdout=100)
        self.addCleanup(worker.cancel)
        worker.start(None)
        self.assertTrue(ready.wait(2), 'child handshake absent')
        self.assertEqual(worker.cancel().status, 'canceled')

    def test_unproven_group_cleanup_never_reports_success(self):
        worker = self.worker('pass')
        killpg = os.killpg
        def probe(group, sig):
            if sig == 0:
                raise PermissionError('private system detail')
            return killpg(group, sig)
        with patch('runtime.voice.process.os.killpg', side_effect=probe):
            worker.start(None)
            result = self.wait(worker)
        self.assertEqual((result.status, result.stdout), ('uncertain', b''))
        self.assertNotIn('private', repr(result))


if __name__ == '__main__':
    unittest.main()
