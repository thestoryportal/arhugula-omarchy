"""Bounded, synthetic-PCM command capture with no device or output seams."""
from dataclasses import dataclass
import threading
from uuid import uuid4


BYTES_PER_MS = 32


@dataclass(frozen=True)
class Frame:
    pcm: bytes
    speech: bool

    def __post_init__(self):
        if type(self.pcm) is not bytes or not self.pcm or len(self.pcm) % BYTES_PER_MS:
            raise ValueError("PCM must be nonempty whole milliseconds of bytes")
        if type(self.speech) is not bool:
            raise ValueError("speech must be boolean")


@dataclass(frozen=True)
class CaptureConfig:
    max_ms: int = 15000
    initial_silence_ms: int = 3000
    short_silence_ms: int = 700
    long_silence_ms: int = 400
    long_utterance_ms: int = 2000

    def __post_init__(self):
        values = (self.max_ms, self.initial_silence_ms, self.short_silence_ms,
                  self.long_silence_ms, self.long_utterance_ms)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("capture bounds must be positive integers")
        if any(value > self.max_ms for value in values[1:]):
            raise ValueError("capture bounds cannot exceed max_ms")


@dataclass(frozen=True)
class CaptureResult:
    status: str
    reason: str
    token: str | None = None
    audio: bytes = b""


@dataclass(frozen=True)
class CaptureNotice:
    token: str | None
    phase: str
    status: str
    reason: str


class CommandCapture:
    """A one-shot state machine fed by a trusted, external VAD observation."""
    def __init__(self, config=CaptureConfig(), observe=None):
        if not isinstance(config, CaptureConfig):
            raise ValueError("config must be CaptureConfig")
        if observe is not None and not callable(observe):
            raise ValueError("observe must be callable")
        self.config, self.observe = config, observe or (lambda notice: None)
        self._state = "idle"
        self._token = None
        self._buffer = bytearray()
        self._speech_ms = self._silence_ms = 0
        self._heard_speech = self._notifying = False
        self._lock = threading.RLock()

    @property
    def state(self):
        return self._state

    @property
    def buffered_bytes(self):
        return len(self._buffer)

    def _result(self, status, reason, audio=b""):
        return CaptureResult(status, reason, self._token, bytes(audio))

    def _discard(self):
        token = self._token
        self._state = "idle"
        self._token = None
        self._buffer.clear()
        self._speech_ms = self._silence_ms = 0
        self._heard_speech = False
        return token

    def _blocked(self, reason):
        return self._result("blocked", reason)

    def _notify(self, phase, result):
        self._notifying = True
        try:
            self.observe(CaptureNotice(result.token, phase, result.status, result.reason))
            return True
        except Exception:
            return False
        finally:
            self._notifying = False

    def _observed(self, phase, result):
        if self._notify(phase, result):
            return result
        self._discard()
        return CaptureResult("failed", "observation-failed", result.token)

    def key_equal(self):
        with self._lock:
            if self._notifying:
                return self._blocked("capture.busy")
            if self._state != "idle":
                return self._blocked("capture.busy")
            self._state = "recording"
            self._token = str(uuid4())
            return self._observed("capture.started", self._result("recording", "started"))

    def feed(self, frame):
        with self._lock:
            if self._notifying:
                return self._blocked("capture.busy")
            if not isinstance(frame, Frame):
                token = self._token
                if self._state in ("recording", "processing"):
                    self._discard()
                return CaptureResult("failed", "invalid-frame", token)
            if self._state != "recording":
                return self._blocked("capture." + self._state)
            remaining = self.config.max_ms * BYTES_PER_MS - len(self._buffer)
            included = frame.pcm[:remaining]
            self._buffer.extend(included)
            elapsed_ms = len(included) // BYTES_PER_MS
            if frame.speech:
                self._heard_speech = True
                self._speech_ms += elapsed_ms
                self._silence_ms = 0
            else:
                self._silence_ms += elapsed_ms
            if len(self._buffer) == self.config.max_ms * BYTES_PER_MS:
                return self._finish("max-duration")
            if not self._heard_speech and self._silence_ms >= self.config.initial_silence_ms:
                token = self._discard()
                return self._observed("capture.finished", CaptureResult("idle", "initial-silence", token))
            limit = (self.config.long_silence_ms if self._speech_ms >= self.config.long_utterance_ms
                     else self.config.short_silence_ms)
            if self._heard_speech and self._silence_ms >= limit:
                return self._finish("silence")
            return self._observed("capture.recording", self._result("recording", "recording"))

    def _finish(self, reason):
        if not self._heard_speech:
            token = self._discard()
            return self._observed("capture.finished", CaptureResult("idle", "initial-silence", token))
        self._state = "processing"
        return self._observed("capture.finished", self._result("processing", reason, self._buffer))

    def cancel(self):
        with self._lock:
            if self._notifying:
                return self._blocked("capture.busy")
            if self._state not in ("recording", "processing"):
                return self._blocked("capture." + self._state)
            token = self._token
            self._discard()
            return self._observed("capture.canceled", CaptureResult("canceled", "canceled", token))

    def complete(self, token):
        with self._lock:
            if self._notifying:
                return self._blocked("capture.busy")
            if self._state != "processing" or token != self._token:
                return self._blocked("stale-token")
            matched = self._token
            self._discard()
            return self._observed("capture.completed", CaptureResult("idle", "completed", matched))
