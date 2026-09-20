"""Home/End dictation semantics with injected, VM-owned IO contracts."""
from dataclasses import dataclass
import threading
from typing import Protocol
from uuid import uuid4

from ..contracts import ContractError, Provider, decode, encode


@dataclass(frozen=True)
class FocusToken:
    window_id: str
    generation: int

    def __post_init__(self):
        if type(self.window_id) is not str or not self.window_id or type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid focus token")


@dataclass(frozen=True)
class Delivery:
    status: str

    def __post_init__(self):
        if self.status not in ("delivered", "not-delivered", "uncertain"):
            raise ValueError("invalid delivery state")


@dataclass(frozen=True)
class DictationResult:
    status: str
    code: str
    delivery: str | None = None


@dataclass(frozen=True)
class Notice:
    interaction_id: str
    phase: str
    status: str
    code: str


class Capture(Protocol):
    def start(self) -> None: ...
    def stop(self) -> bytes: ...
    def cancel(self) -> None: ...


class Output(Protocol):
    """Trusted VM output, not raw model callbacks.

    type_text MUST atomically enforce the supplied focus token as far as the
    platform permits, and report uncertain after any possibly partial effect.
    copy_text copies only; it must never send a paste key to the focused app.
    """
    def type_text(self, text: str, target: FocusToken) -> Delivery: ...
    def copy_text(self, text: str) -> Delivery: ...


class Dictation:
    def __init__(self, capture: Capture, transcribe, output: Output, focus,
                 provider: Provider, observe):
        self.provider = decode(encode(provider))
        if not isinstance(self.provider, Provider):
            raise ContractError("dictation requires a Provider")
        self.capture, self.transcribe, self.output = capture, transcribe, output
        self.focus, self.observe = focus, observe
        self._state = "idle"
        self._target = None
        self._interaction = None
        self._lock = threading.RLock()

    @property
    def state(self):
        return self._state

    def _emit(self, phase, result):
        try:
            self.observe(Notice(self._interaction, phase, result.status, result.code))
            return True
        except Exception:
            return False

    def _cleanup(self):
        try:
            self.capture.cancel()
            self._state = "idle"
            return True
        except Exception:
            self._state = "faulted"
            return False

    def _complete(self, result, attempted=False):
        faulted = self._state == "faulted"
        self._state = "faulted" if faulted else "processing"
        observed = self._emit("dictation.finished", result)
        self._target = None
        self._state = "faulted" if faulted else "idle"
        if not observed:
            return DictationResult("uncertain" if attempted or faulted else "blocked", "observation.unavailable")
        return result

    def home(self):
        with self._lock:
            if self._state != "idle":
                return DictationResult("blocked", "capture.faulted" if self._state == "faulted" else "capture.busy")
            self._state = "processing"
            self._interaction = str(uuid4())
            provider = self.provider
            if provider.placement != "vm" or not provider.enabled or provider.health == "unavailable" or "transcription" not in provider.capabilities:
                return self._complete(DictationResult("blocked", "provider.unavailable"))
            try:
                self._target = self.focus()
                if not isinstance(self._target, FocusToken):
                    raise ValueError("invalid focus")
            except Exception:
                return self._complete(DictationResult("blocked", "focus.unavailable"))
            result = DictationResult("recording", "capture.started")
            if not self._emit("dictation.starting", result):
                self._target = None
                self._state = "idle"
                return DictationResult("blocked", "observation.unavailable")
            # Busy before calling a reentrant injected adapter.
            self._state = "processing"
            try:
                self.capture.start()
            except Exception:
                clean = self._cleanup()
                return self._complete(DictationResult("failed" if clean else "uncertain", "capture.failed"))
            self._state = "recording"
            return result

    def end(self):
        with self._lock:
            if self._state != "recording":
                return DictationResult("blocked", "capture.idle" if self._state == "idle" else "capture." + self._state)
            self._state = "processing"
            try:
                audio = self.capture.stop()
            except Exception:
                clean = self._cleanup()
                return self._complete(DictationResult("failed" if clean else "uncertain", "capture.failed"))
            if not self._emit("dictation.processing", DictationResult("processing", "capture.stopped")):
                return self._complete(DictationResult("blocked", "observation.unavailable"))
            try:
                if type(audio) is not bytes or not audio:
                    raise ValueError("invalid audio")
                text = self.transcribe(audio)
                if type(text) is not str or not text.strip():
                    raise ValueError("empty or invalid transcript")
            except Exception:
                return self._complete(DictationResult("failed", "transcription.failed"))
            try:
                if self.focus() != self._target:
                    return self._complete(DictationResult("blocked", "focus.changed"))
            except Exception:
                return self._complete(DictationResult("blocked", "focus.unavailable"))
            try:
                delivery = self.output.type_text(text, self._target)
                if not isinstance(delivery, Delivery):
                    raise ValueError("invalid delivery")
            except Exception:
                return self._complete(DictationResult("uncertain", "output.uncertain"), attempted=True)
            route = "typing"
            if delivery.status == "not-delivered":
                try:
                    if self.focus() != self._target:
                        return self._complete(DictationResult("blocked", "focus.changed"))
                except Exception:
                    return self._complete(DictationResult("blocked", "focus.unavailable"))
                route = "clipboard"
                try:
                    delivery = self.output.copy_text(text)
                    if not isinstance(delivery, Delivery):
                        raise ValueError("invalid delivery")
                except Exception:
                    return self._complete(DictationResult("uncertain", "output.uncertain"), attempted=True)
            status = {"delivered": "success", "not-delivered": "failed", "uncertain": "uncertain"}[delivery.status]
            return self._complete(DictationResult(status, "output." + delivery.status, route), attempted=True)

    def cancel(self):
        with self._lock:
            if self._state != "recording":
                return DictationResult("blocked", "capture." + self._state)
            self._state = "processing"
            clean = self._cleanup()
            return self._complete(DictationResult("canceled" if clean else "uncertain", "capture.canceled" if clean else "capture.faulted"))
