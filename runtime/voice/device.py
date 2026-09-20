"""Opt-in fixed PipeWire argv; tests inject workers and never open a microphone."""
import re
import threading

from .pcm import PcmFramer
from .process import ProcessResult


class CaptureIOError(ValueError):
    """Capture failed; discard the complete activation, not just this chunk."""


class PipeWireCapture:
    def __init__(self, *, worker_factory=None):
        if not callable(worker_factory):
            raise ValueError('explicit approved worker binding required')
        self._factory = worker_factory
        self._lock = threading.Lock()
        self._framer, self._queue = PcmFramer(), []
        self._started = self._closed = False
        self._cleaned = None
        self._worker = self._error = None
        self._total = 0

    def start(self, source: str):
        if (type(source) is not str or source in {'default', '0'} or
                not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}', source)):
            raise ValueError('explicit approved PipeWire node required')
        with self._lock:
            if self._started or self._closed:
                raise CaptureIOError('capture.single-use')
            self._started = True
        argv = ('/usr/bin/pw-record', '--rate', '16000', '--channels', '1',
                '--format', 's16', '--raw', '--target', source, '--sample-count', '240000', '-')
        try:
            worker = self._factory(argv, max_output=65536, timeout_s=15,
                                   stdout_consumer=self._receive, max_stdout=480000, idle_timeout_s=1)
            with self._lock:
                self._worker = worker
                closed = self._closed
            if closed:
                self.cancel()
                raise CaptureIOError('capture.canceled')
            worker.start(None)
        except Exception:
            with self._lock:
                self._error = 'capture.start-failed'
            self.cancel()
            raise CaptureIOError('capture.start-failed') from None

    def _receive(self, chunk):
        with self._lock:
            if self._closed or self._error:
                raise CaptureIOError('capture.closed')
            try:
                if type(chunk) is not bytes or not chunk or self._total + len(chunk) > 480000:
                    raise ValueError('invalid PCM')
                frames = self._framer.feed(chunk)
                if len(self._queue) + len(frames) > 16:
                    raise ValueError('queue overflow')
                self._queue.extend(frames)
                self._total += len(chunk)
            except ValueError:
                self._queue.clear()
                self._error = 'capture.invalid-stream'
                raise CaptureIOError(self._error) from None

    def poll(self) -> list[bytes]:
        with self._lock:
            worker = self._worker
            if self._closed and not self._error:
                return []
        try:
            result = worker.poll() if worker is not None else None
        except Exception:
            result = ProcessResult('uncertain', b'', 'process.unknown')
        with self._lock:
            if result is not None and not self._error:
                if not isinstance(result, ProcessResult) or result.status != 'success':
                    self._error = 'capture.worker-failed'
                else:
                    try:
                        self._framer.finish()
                        if self._total == 0:
                            raise ValueError('empty capture')
                        self._closed, self._cleaned = True, True
                    except ValueError:
                        self._error = 'capture.incomplete-stream'
            error = self._error
            frames, self._queue = self._queue, []
        if error:
            self.cancel()
            raise CaptureIOError(error)
        return frames

    def cancel(self) -> bool:
        with self._lock:
            self._closed = True
            self._queue.clear()
            if self._cleaned is not None:
                return self._cleaned
            worker, started = self._worker, self._started
        if worker is None:
            return not started
        try:
            result = worker.cancel()
            clean = isinstance(result, ProcessResult) and result.status in {'success', 'failed', 'canceled'}
        except Exception:
            clean = False
        with self._lock:
            self._cleaned = clean
        return clean
