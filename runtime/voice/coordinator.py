"""Foreground command lifecycle; all IO is explicitly injected, never discovered.

One owner drives activate/feed/poll/confirm. Cross-thread cancel invalidates the
generation immediately, then waits for the current transition to finish cleanup.
Trusted observers/state suppliers must be bounded. Polling is not atomic with
external compositor changes: state.key must include a monotonic context epoch,
and the executor must enforce its own final actuation guard.
"""
import math
import threading
import time
from types import MappingProxyType
from uuid import uuid4

from ..contracts import VoiceObservation, decode, encode
from .capture import Frame
from .pcm import EnergyVad, PcmFramer
from .router import VoiceReply, VoiceState
from .session import BusyError
from .transcription import TranscriptResult


class _Stop(Exception):
    pass


class Coordinator:
    """Own a router exclusively and create fresh single-use jobs each activation.

    transcriber is a zero-argument job factory, not a reusable TranscriptionJob.
    Optional device_factory/source bind an explicit capture adapter. No typing,
    clipboard, installed provider, socket, or live permission default exists.
    feed accepts optional contiguous sequence numbers for transport deduplication;
    identical unnumbered PCM frames are legitimate audio, not duplicates.
    """

    def __init__(self, owner, capture, router, transcriber, observe, *,
                 device_factory=None, source=None, vad=None, clock=None, speech=None):
        if not callable(transcriber) or not callable(observe):
            raise ValueError('explicit job factory and observer required')
        if (device_factory is None) != (source is None) or (
                device_factory is not None and not callable(device_factory)):
            raise ValueError('capture requires an explicit factory and source')
        self.owner, self.capture, self.router = owner, capture, router
        self._factory, self._observe = transcriber, observe
        self._device_factory, self._source = device_factory, source
        self._speech = speech
        self._vad = vad or EnergyVad(0.02)  # Synthetic candidate, not calibrated.
        self._clock = clock or time.monotonic
        self._state_source = router.state
        self._lock = threading.RLock()
        self._cancel_requested = threading.Event()
        self._busy = self._valid = False
        self._generation = self._snapshot = self._job = self._device = None
        self._device_cleaned = None
        self._phase, self._code = 'idle', 'capture.canceled'
        self._activation_id = self._correlation_id = None
        self._pending_token = self._confirming = None
        self._sequence = 0
        self._framer = None
        router.state = self._router_state
        router.correlation_ids = lambda: self._correlation_id

    @property
    def phase(self):
        return self._phase

    @property
    def code(self):
        return self._code

    @property
    def activation_id(self):
        return self._activation_id

    @property
    def correlation_id(self):
        return self._correlation_id

    def _sample(self):
        value = self._state_source()
        if (not isinstance(value, VoiceState) or type(value.key) is not str or not value.key
                or type(value.activation_id) is not str or not value.activation_id
                or type(value.muted) is not bool):
            raise ValueError('trusted voice state unavailable')
        return VoiceState(MappingProxyType(dict(value.context)), value.key,
                          value.activation_id, value.muted, value.mode)

    def _current(self):
        try:
            # State suppliers may reenter cancel; check authority AFTER them.
            current = self._sample() if self._valid else None
            good = (self._valid and not self._cancel_requested.is_set()
                    and current == self._snapshot
                    and not self._snapshot.muted and self._snapshot.mode == 'command'
                    and (self._generation is None or self.owner.accepts(self._generation)))
        except Exception:
            good = False
        if not good:
            self._valid = False
        return good

    def _check(self):
        if not self._current():
            raise _Stop('capture.canceled' if self._cancel_requested.is_set() else 'context.stale')
        now = self._clock()
        if self._phase in {'capturing', 'processing'} and (
                not math.isfinite(now) or now >= self._deadline):
            raise _Stop('capture.device-error' if self._phase == 'capturing' else 'transcription.failed')

    def _router_state(self):
        current = self._current()
        snapshot = self._snapshot
        if snapshot is None:
            raise ValueError('no voice activation')
        return VoiceState(snapshot.context, snapshot.key + ':' + self.owner.session_id,
                          self._activation_id, muted=not current, mode='command')

    def _emit(self, phase, status, code):
        try:
            event = decode(encode(VoiceObservation(
                1, str(uuid4()), self.owner.session_id, self._activation_id,
                self._correlation_id, int(time.time() * 1000),
                {**self._snapshot.context, 'source': 'voice'}, phase, status, code)))
            self._observe(event)
        except Exception:
            raise _Stop('journal.unavailable') from None

    def _stop_device(self):
        if self._device is None:
            return True
        if self._device_cleaned is None:
            try:
                self._device_cleaned = self._device.cancel() is True
            except Exception:
                self._device_cleaned = False
        return self._device_cleaned

    def _cleanup(self):
        clean = self._stop_device()
        if not self._valid or self._cancel_requested.is_set():
            clean = self._stop_speech() and clean
        if self._job is not None:
            try:
                self._job.cancel()
                clean = (self._job.cleanup_proven is True) and clean
            except Exception:
                clean = False
        try:
            if self.capture.state != 'idle':
                self.capture.cancel()
            clean = (self.capture.state == 'idle') and clean
        except Exception:
            clean = False
        return clean

    def _stop_speech(self):
        if self._speech is None:
            return True
        try:
            self._speech.cancel()
            return self._speech.cleanup_proven is True
        except Exception:
            return False

    def _release(self, clean):
        if self._generation is not None:
            self.owner.release(self._generation, cleaned=clean)
            self._generation = None
        self._job = self._device = self._framer = None
        self._phase = 'idle' if clean else 'faulted'
        if not clean:
            self._valid = False
            self._code = 'owner.cleanup-unproven'
            try:
                self._emit('owner.faulted', 'uncertain', self._code)
            except _Stop:
                pass  # Never conceal the local fault because the journal failed.

    def _fail(self, code):
        phase = self._phase
        self._valid = False
        self._pending_token = self._confirming = None
        if self._generation is not None:
            self.owner.cancel(generation=self._generation)
        clean = self._cleanup()
        self._code = code
        if code != 'journal.unavailable':
            try:
                if phase == 'capturing':
                    self._emit('capture.canceled', 'canceled', code)
                elif phase == 'processing':
                    self._emit('transcription.finished', 'canceled', code)
            except _Stop:
                self._code = 'journal.unavailable'
        self._release(clean)

    def activate(self, *, confirmation_token=None):
        with self._lock:
            if self._busy or self._phase != 'idle':
                raise BusyError('voice owner is busy or faulted')
            self._busy = True
            try:
                return self._activate(confirmation_token)
            finally:
                self._busy = False

    def _activate(self, confirmation_token):
        # Clear a previous turn's cancellation before invoking collaborators,
        # never erase cancellation delivered by this preflight's callbacks.
        if confirmation_token is None:
            self._cancel_requested.clear()
        if not self._stop_speech():
            raise BusyError('speech cleanup unproven')
        if confirmation_token is not None and (
                confirmation_token != self._pending_token or not self._current()):
            raise ValueError('no current confirmation')
        try:
            snapshot = self._sample()
            if (snapshot.muted or snapshot.mode != 'command'
                    or self._cancel_requested.is_set()
                    or (confirmation_token is not None and (
                        confirmation_token != self._pending_token or not self._valid
                        or snapshot != self._snapshot))):
                raise ValueError()
        except Exception:
            raise ValueError('trusted voice state unavailable') from None
        generation = self.owner.begin('command')
        self._generation, self._snapshot = generation, snapshot
        self._activation_id = self.owner.session_id + ':' + str(generation)
        if confirmation_token is None:
            self._correlation_id = str(uuid4())
            self._pending_token = None
        self._confirming = confirmation_token
        self._sequence = 0
        self._job = self._device = self._device_cleaned = None
        self._framer = PcmFramer()
        self._valid = True
        self._phase, self._code = 'capturing', 'capture.started'
        try:
            self._deadline = self._clock() + 15.0
            self._emit('capture.started', 'recording', self._code)
            self._check()
            if self.capture.key_equal().status != 'recording':
                raise _Stop('capture.device-error')
            self._check()
            if self._device_factory is not None:
                self._device = self._device_factory()
                self._check()
                self._device.start(self._source)
                self._check()
        except _Stop as exc:
            self._fail(str(exc))
        except Exception:
            self._fail('capture.device-error')
        return generation

    def feed(self, generation, frame, *, sequence=None):
        with self._lock:
            if self._busy:
                return
            self._busy = True
            try:
                self._feed(generation, frame, sequence)
            finally:
                self._busy = False

    def _feed(self, generation, frame, sequence=None):
        if type(generation) is not int or generation != self._generation or self._phase != 'capturing':
            return
        try:
            self._check()
            if sequence is not None:
                if type(sequence) is not int or sequence < 0 or sequence > self._sequence:
                    raise _Stop('capture.invalid-frame')
                if sequence < self._sequence:
                    return
            if type(frame) is not Frame or len(frame.pcm) != 640:
                raise _Stop('capture.invalid-frame')
            self._sequence += 1
            result = self.capture.feed(frame)
            self._check()
            if result.status == 'recording':
                return
            if result.status not in {'idle', 'processing'}:
                raise _Stop('capture.invalid-frame')
            if not self._stop_device():
                raise _Stop('owner.cleanup-unproven')
            self._emit('capture.stopped', result.status, 'capture.' + result.reason)
            self._check()
            if result.status == 'idle':
                self._code = 'capture.initial-silence'
                self._release(self._cleanup())
                return
            self._phase, self._code = 'processing', 'transcription.started'
            self._emit('transcription.started', 'processing', self._code)
            self._check()
            self._job = self._factory()
            self._check()
            self._deadline = self._clock() + 30.0
            self._job.start(result.audio, generation)
            self._check()
        except _Stop as exc:
            self._fail(str(exc))
        except Exception:
            self._fail('transcription.failed' if self._phase == 'processing' else 'capture.invalid-frame')

    def transcribed(self, result):
        with self._lock:
            if self._busy:
                return None
            self._busy = True
            try:
                return self._transcribed(result)
            finally:
                self._busy = False

    def _transcribed(self, result):
        if (type(result) is not TranscriptResult or type(result.generation) is not int
                or result.generation != self._generation or self._phase != 'processing'):
            return None
        try:
            self._check()
            if self._job is None or self._job.cleanup_proven is not True:
                raise _Stop('transcription.cleanup-unproven')
            valid_text = (type(result.text) is str and bool(result.text.strip())
                          and len(result.text.encode('utf-8')) <= 16384)
            successful = result.status == 'success' and valid_text
            self._emit('transcription.finished', 'success' if successful else 'failed',
                       'transcription.ok' if successful else 'transcription.failed')
            self._check()
            self._phase = 'routing'
            if not successful:
                self._fail('transcription.failed')
                return None
            reply = (self.router.confirm(self._confirming, 'voice', result.text)
                     if self._confirming is not None else self.router.handle(result.text))
            self._pending_token = reply.token if reply.status in {'preview', 'clarify'} else None
            self._confirming = None
            self._code = reply.code
            self._release(self._cleanup())
            return reply
        except _Stop as exc:
            self._fail(str(exc))
        except Exception:
            self._fail('transcription.failed')
        return None

    def poll(self):
        """One bounded foreground tick; no thread, background loop or live default."""
        with self._lock:
            if self._busy or self._phase not in {'capturing', 'processing'}:
                return None
            self._busy = True
            try:
                self._check()
                now = self._clock()
                if not math.isfinite(now) or now >= self._deadline:
                    raise _Stop('capture.device-error' if self._phase == 'capturing' else 'transcription.failed')
                if self._phase == 'capturing' and self._device is not None:
                    chunks = self._device.poll()
                    if (type(chunks) is not list or len(chunks) > 16
                            or any(type(c) is not bytes for c in chunks)
                            or sum(map(len, chunks)) > 10240):
                        raise _Stop('capture.invalid-frame')
                    for chunk in chunks:
                        if self._phase != 'capturing':
                            break
                        for pcm in self._framer.feed(chunk):
                            self._feed(self._generation, Frame(pcm, self._vad.is_speech(pcm)))
                            if self._phase != 'capturing':
                                break
                if self._phase == 'processing':
                    result = self._job.poll()
                    if result is not None:
                        return self._transcribed(result)
            except _Stop as exc:
                self._fail(str(exc))
            except Exception:
                self._fail('capture.device-error' if self._phase == 'capturing' else 'transcription.failed')
            finally:
                self._busy = False
        return None

    def cancel(self):
        generation = self._generation
        self._cancel_requested.set()
        if generation is not None:
            self.owner.cancel(generation=generation)  # Before any journal wait.
        with self._lock:
            self._valid = False
            self._pending_token = self._confirming = None
            if self._busy:  # Reentrant trusted callback: outer transition cleans.
                return
            self._busy = True
            try:
                if self._generation is not None:
                    # _fail also invalidates; repeated cancellation is conservative.
                    self._fail('capture.canceled')
                elif not self._stop_speech():
                    self._phase, self._code = 'faulted', 'owner.cleanup-unproven'
            finally:
                self._busy = False

    def confirm(self, token, channel, answer):
        with self._lock:
            if self._busy:
                return VoiceReply('blocked', 'confirmation.unavailable')
            self._busy = True
            try:
                return self._confirm(token, channel, answer)
            finally:
                self._busy = False

    def _confirm(self, token, channel, answer):
        if (self._phase != 'idle' or token is None
                or token != self._pending_token or channel not in {'panel', 'keyboard'}
                or type(answer) is not bool or not self._current()):
            return VoiceReply('blocked', 'confirmation.unavailable')
        self._generation = self.owner.begin('command')
        self._pending_token = None
        try:
            reply = self.router.confirm(token, channel, answer)
            self._code = reply.code
            self._release(self._cleanup())
            return reply
        except Exception:
            self._fail('context.stale')
            return VoiceReply('blocked', 'confirmation.unavailable')
