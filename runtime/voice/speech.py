"""Single-slot, finite-prompt speech seam; no provider or output is discovered.

The trusted backend owns synthesis AND playback. cancel must quiesce both,
including delayed results, before returning a non-uncertain ProcessResult.
start/cancel must be bounded; this wrapper cannot preempt a Python callback.
The foreground owner calls poll on state changes and cancel before capture.
"""
from collections.abc import Mapping
import json
import threading
from types import MappingProxyType
from typing import Protocol

from .process import ProcessResult
from .router import VoiceState


PROMPTS = frozenset({
    'Please repeat the command.',
    'Please confirm in the voice panel.',
    'Start a new command turn and say yes or no.',
})


class SpeechBackend(Protocol):
    def start(self, prompt: str) -> None: ...

    def cancel(self) -> ProcessResult: ...


def snapshot_state(value: VoiceState) -> VoiceState:
    """Detach the complete trusted context, including nested mutable values."""
    if (not isinstance(value, VoiceState) or not isinstance(value.context, Mapping)
            or type(value.key) is not str or not value.key
            or type(value.activation_id) is not str or not value.activation_id
            or type(value.muted) is not bool or value.mode not in ('command', 'dictation')):
        raise ValueError('voice.invalid-state')
    context = json.loads(json.dumps(dict(value.context), allow_nan=False))
    return VoiceState(MappingProxyType(context), value.key, value.activation_id,
                      value.muted, value.mode)


class SpeechQueue:
    """No backlog or automatic retry; say returns admission, not playback proof."""

    def __init__(self, backend: SpeechBackend, state):
        if not callable(state) or not all(callable(getattr(backend, name, None))
                                         for name in ('start', 'cancel')):
            raise ValueError('speech.invalid-binding')
        self._backend, self._state = backend, state
        self._lock, self._epoch_lock = threading.RLock(), threading.Lock()
        self._epoch = 0
        self._active = self._busy = self._stopping = self._faulted = False
        self._snapshot = None
        self._code = 'speech.idle'

    @property
    def cleanup_proven(self):
        with self._lock:
            return not self._active and not self._faulted and not self._stopping

    @property
    def code(self):
        return self._code

    def _generation(self):
        with self._epoch_lock:
            return self._epoch

    def _current(self, snapshot, epoch):
        current = snapshot_state(self._state())
        return (current == snapshot and not current.muted and current.mode == 'command'
                and epoch == self._generation())

    def _stop(self):
        if self._stopping:
            return
        if self._active:
            self._stopping = True
            try:
                result = self._backend.cancel()
                clean = (isinstance(result, ProcessResult)
                         and result.status in {'success', 'canceled', 'failed'}
                         and result.code != 'process.cleanup-unproven')
            except Exception:
                clean = False
            finally:
                self._stopping = False
            self._active = not clean
            self._faulted = self._faulted or not clean
        self._snapshot = None
        if self._faulted:
            self._code = 'speech.cleanup-unproven'

    def say(self, prompt: str, activation_id: str) -> bool:
        with self._lock:
            if self._faulted or self._busy or self._stopping:
                return False
            if type(prompt) is not str or prompt not in PROMPTS:
                self._code = 'speech.invalid-prompt'
                return False
            self._busy = True
            epoch = self._generation()
            try:
                try:
                    snapshot = snapshot_state(self._state())
                    eligible = (type(activation_id) is str and snapshot.activation_id == activation_id
                                and self._current(snapshot, epoch))
                except Exception:
                    self._code = 'speech.state-unavailable'
                    self._stop()
                    return False
                if not eligible:
                    self._code = 'speech.stale'
                    self._stop()
                    return False
                self._stop()
                if self._faulted:
                    return False
                try:
                    current = self._current(snapshot, epoch)
                except Exception:
                    current = False
                if not current:
                    self._code = 'speech.stale'
                    return False
                self._active = True  # Own cleanup even if start partially fails.
                self._snapshot = snapshot
                try:
                    self._backend.start(prompt)
                    # A reentrant cancel may finish before start returns and
                    # before a badly timed backend allocates its last resource.
                    self._active = True
                    if not self._current(snapshot, epoch):
                        self._code = 'speech.stale'
                        self._stop()
                        return False
                except Exception:
                    self._active = True
                    self._code = 'speech.unavailable'
                    self._stop()
                    return False
                self._code = 'speech.started'
                return True
            finally:
                self._busy = False

    def cancel(self) -> None:
        # Invalidate immediately, before waiting for a bounded start callback.
        with self._epoch_lock:
            self._epoch += 1
        with self._lock:
            self._code = 'speech.canceled'
            self._stop()

    def poll(self) -> None:
        with self._lock:
            if not self._active or self._busy or self._stopping:
                return
            self._busy = True
            try:
                try:
                    current = self._current(self._snapshot, self._generation())
                except Exception:
                    current = False
                if not current:
                    self._code = 'speech.stale'
                    self._stop()
            finally:
                self._busy = False
