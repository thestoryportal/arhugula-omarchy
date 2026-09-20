"""Single-use, transient WAV transcription job with explicitly injected backend.

No Voxtype configuration is inferred or loaded. A trusted backend accepts WAV
bytes on stdin and produces plain UTF-8 on stdout; installed file-CLI compatibility
has NOT been established. P2 characterization must precede any concrete binding.
"""
from dataclasses import dataclass, field
import io
import threading
import wave

from .process import ProcessResult


@dataclass(frozen=True)
class TranscriptResult:
    generation: int
    status: str
    text: str | None = field(repr=False)
    code: str


class TranscriptionJob:
    def __init__(self, *, worker_factory=None):
        if not callable(worker_factory):
            raise ValueError('explicit approved transcription backend required')
        self._factory = worker_factory
        self._lock = threading.Lock()
        self._started = self._closed = False
        self._worker = self._pending = self._generation = None
        self._cleaned = None

    @property
    def cleanup_proven(self):
        with self._lock:
            return self._cleaned is True

    def start(self, pcm: bytes, generation: int):
        if type(pcm) is not bytes or not pcm or len(pcm) % 640 or len(pcm) > 480000:
            raise ValueError('requires bounded whole-frame PCM')
        if type(generation) is not int or generation <= 0:
            raise ValueError('requires positive integer generation')
        with self._lock:
            if self._started or self._closed:
                raise RuntimeError('transcription job is single-use')
            self._started, self._generation = True, generation
        try:
            stream = io.BytesIO()
            with wave.open(stream, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)
            worker = self._factory()
            with self._lock:
                self._worker = worker
                closed = self._closed
            if closed:
                self.cancel()
                return
            worker.start(stream.getvalue())
        except Exception:
            self.cancel()
            with self._lock:
                self._pending = TranscriptResult(generation, 'failed' if self._cleaned else 'uncertain', None, 'transcription.start-failed')

    def poll(self) -> TranscriptResult | None:
        with self._lock:
            if self._pending is not None:
                result, self._pending = self._pending, None
                return result
            if self._closed or self._worker is None:
                return None
            worker = self._worker
        try:
            raw = worker.poll()
        except Exception:
            self.cancel()
            return TranscriptResult(self._generation, 'uncertain', None, 'transcription.worker-failed')
        if raw is None:
            return None
        text = None
        status, code = 'failed', 'transcription.failed'
        clean = isinstance(raw, ProcessResult) and raw.status in {'success', 'failed', 'canceled'}
        if isinstance(raw, ProcessResult) and raw.status == 'success':
            try:
                if type(raw.stdout) is not bytes or not 0 < len(raw.stdout) <= 16384:
                    raise ValueError('invalid transcript size')
                text = raw.stdout.decode('utf-8').strip()
                if not text or any(ord(c) < 32 and c not in '\n\t' for c in text):
                    raise ValueError('invalid transcript')
                status, code = 'success', 'transcription.ok'
            except (ValueError, UnicodeError):
                text = None
        if not clean:
            status, code = 'uncertain', 'transcription.cleanup-unproven'
        with self._lock:
            if self._closed:
                return None
            self._closed, self._cleaned = True, clean
            return TranscriptResult(self._generation, status, text, code)

    def cancel(self) -> None:
        with self._lock:
            self._closed = True
            self._pending = None
            if self._cleaned is not None:
                return
            worker, started = self._worker, self._started
        clean = not started
        if worker is not None:
            try:
                result = worker.cancel()
                clean = isinstance(result, ProcessResult) and result.status in {'success', 'failed', 'canceled'}
            except Exception:
                clean = False
        with self._lock:
            # A worker still being constructed must receive cancellation too.
            if worker is not None or not started:
                self._cleaned = clean
