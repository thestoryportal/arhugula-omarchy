"""Explicitly polled offline TTS; injected callbacks are trusted and bounded.

The caller retains the shared conversation lease until every output borrower is
clean. This module does not install that coordinator or any live effect adapter.
"""
from dataclasses import dataclass, field, replace
from enum import Enum
import threading
from typing import Protocol

from runtime.gateway.client import GatewayClient, Success, Degraded, Failed
from runtime.gateway.wire import GatewayError, SpeechOutput, catalog_revision
from runtime.providers.configuration import Active, Configuration
from .session import SessionOwner, StaleOwnerError, FaultedError
from .tts_records import (
    AudioSnapshot, Code, Completion, Denied, MixIntent, Notice, Phase, Ready,
    Utterance, admit,
)


class PlaybackState(Enum):
    PENDING = 'pending'
    COMPLETE = 'complete'
    FAILED = 'failed'


class PlaybackJob(Protocol):
    def start(self, audio: SpeechOutput) -> None: ...
    def poll(self) -> PlaybackState: ...
    def cancel(self) -> bool: ...


class MixLease(Protocol):
    def apply(self, intent: MixIntent) -> None: ...
    def restore(self) -> bool: ...


class _Stop(Exception):
    def __init__(self, code):
        self.code = code


def _gateway_code(code):
    return {'replay': Code.REPLAY, 'busy': Code.BUSY, 'cleanup': Code.CLEANUP,
            'exhausted': Code.LIMIT, 'timeout': Code.LIMIT,
            'invalid_response': Code.INVALID_AUDIO}.get(code, Code.UNAVAILABLE)


@dataclass
class _Call:
    snapshot: AudioSnapshot = field(repr=False)
    ready: Ready = field(repr=False)
    epoch: int
    gateway_owned: bool = False
    synthesis_clean: bool = True
    unknown: bool = False
    player: PlaybackJob | None = field(default=None, repr=False)
    mix: MixLease | None = field(default=None, repr=False)
    polls: int = 0
    provider_id: str | None = None
    model_version: str | None = None
    failures: tuple = ()
    success: Code = Code.PLAYED


class TtsOutput:
    """One job/terminal slot. No admission reset, device discovery or activation."""

    def __init__(self, owner, gateway, configuration, catalog_version, snapshot, players, mixes):
        if (not isinstance(owner, SessionOwner) or type(gateway) is not GatewayClient
                or type(configuration) is not Configuration
                or not all(callable(f) for f in (snapshot, players, mixes))):
            raise ValueError('tts.invalid-binding')
        self._owner, self._gateway, self._configuration = owner, gateway, configuration
        self._catalog_version = catalog_revision(catalog_version)
        self._snapshot, self._players, self._mixes = snapshot, players, mixes
        self._lock, self._gate = threading.RLock(), threading.Lock()
        self._epoch, self._busy, self._fault = 0, False, False
        self._call = self._terminal = None
        self._phase, self._code = Phase.IDLE, Code.IDLE

    @property
    def notice(self):
        with self._lock:
            return Notice(self._phase, self._code)

    @property
    def cleanup_proven(self):
        with self._lock:
            return self._call is None and not self._busy and not self._fault

    def _sample(self):
        snapshot = self._snapshot()
        if type(snapshot) is not AudioSnapshot:
            raise _Stop(Code.UNAVAILABLE)
        return snapshot

    def _belongs(self, token):
        prefix = self._owner.session_id + ':'
        entry = token.session_id.removeprefix(prefix)
        return (token.session_id.startswith(prefix) and entry.isascii() and entry.isdecimal()
                and 0 < int(entry) <= token.generation and self._owner.accepts(token.generation))

    def _check(self, call):
        current = self._sample()
        active = self._configuration.state
        with self._gate:
            if call.epoch != self._epoch:
                raise _Stop(Code.CANCELED)
            if (current != call.snapshot or not self._belongs(current.current_turn)
                    or type(active) is not Active
                    or active.revision != call.snapshot.policy.configuration_revision):
                raise _Stop(Code.STALE)

    def _run(self, operation, refused=None):
        if self._busy:
            return refused
        self._busy = True
        try:
            return operation()
        except _Stop as stop:
            self._stop_or_notice(stop.code)
            return refused
        except Exception:
            # [LAW:effects-at-boundaries] Collaborator details cannot enter status.
            self._stop_or_notice(Code.UNAVAILABLE)
            return refused
        finally:
            self._busy = False

    def _stop_or_notice(self, code):
        if self._call is not None:
            self._retire(code)
        else:
            self._code = code

    def start(self, utterance: Utterance) -> bool:
        if type(utterance) is not Utterance:
            raise ValueError('tts.invalid-utterance')
        with self._lock:
            if self._fault or self._call is not None or self._terminal is not None:
                return False

            def start():
                with self._gate:
                    epoch = self._epoch
                snapshot = self._sample()
                ready = admit(utterance, snapshot, self._configuration.state, self._catalog_version)
                if type(ready) is Denied:
                    self._code = ready.code
                    return False
                if not self._belongs(utterance.token):
                    raise _Stop(Code.STALE)
                call = _Call(snapshot, ready, epoch)
                self._call = call
                self._check(call)
                try:
                    self._gateway.start(ready.request)
                except GatewayError as error:
                    # A rejected start owns no gateway job/terminal to retire.
                    self._call = None
                    self._code = _gateway_code(error.code)
                    return False
                call.gateway_owned = True
                self._phase, self._code = Phase.SYNTHESIZING, Code.STARTED
                self._check(call)
                return True
            return self._run(start, False)

    @staticmethod
    def _contract(value, methods):
        if not all(callable(getattr(value, name, None)) for name in methods):
            raise _Stop(Code.CLEANUP)

    def _play(self, call, audio):
        call.unknown = True
        call.mix = self._mixes()
        self._contract(call.mix, ('apply', 'restore'))
        call.unknown = False
        self._check(call)
        call.mix.apply(call.ready.mix)
        self._check(call)
        call.unknown = True
        call.player = self._players()
        self._contract(call.player, ('start', 'poll', 'cancel'))
        call.unknown = False
        self._check(call)
        call.player.start(audio)
        self._check(call)
        call.polls = 0
        self._phase, self._code = Phase.PLAYING, Code.PLAYING

    def _advance(self):
        call = self._call
        if call is None:
            return
        self._check(call)
        call.polls += 1
        if self._phase is Phase.SYNTHESIZING:
            result = self._gateway.poll()
            if result is not None:
                call.gateway_owned = False
                call.synthesis_clean = self._gateway.cleanup_proven is True
                if type(result) is Failed:
                    call.failures = result.failures
                    raise _Stop(_gateway_code(result.failures[-1].code))
                if type(result) is Degraded:
                    call.failures, call.success = (result.primary,), Code.DEGRADED
                    result = result.result
                if type(result) is not Success or type(result.output) is not SpeechOutput:
                    raise _Stop(Code.INVALID_AUDIO)
                call.provider_id, call.model_version = result.provider_id, result.model_version
                if not call.synthesis_clean:
                    raise _Stop(Code.CLEANUP)
                self._check(call)
                self._play(call, result.output)
            else:
                self._check(call)
                if call.polls >= call.snapshot.policy.limits.synthesis_polls:
                    raise _Stop(Code.LIMIT)
        elif self._phase is Phase.PLAYING:
            result = call.player.poll()
            self._check(call)
            if result is PlaybackState.COMPLETE:
                self._retire(call.success)
            elif result is not PlaybackState.PENDING:
                raise _Stop(Code.UNAVAILABLE)
            elif call.polls >= call.snapshot.policy.limits.playback_polls:
                raise _Stop(Code.LIMIT)

    def _cleanup(self, call):
        clean = not call.unknown and call.synthesis_clean
        if call.gateway_owned:
            try:
                self._gateway.cancel()
                result = self._gateway.poll()
                proven = self._gateway.cleanup_proven is True
                if type(result) is Failed:
                    call.failures = result.failures
            except Exception:
                proven = False
            clean = proven and clean
            call.gateway_owned = False
        # [LAW:no-ambient-temporal-coupling] Restore even after cancellation fails.
        for handle, method in ((call.player, 'cancel'), (call.mix, 'restore')):
            if handle is not None:
                try:
                    proven = getattr(handle, method)() is True
                except Exception:
                    proven = False
                clean = proven and clean
        call.player = call.mix = None
        return clean

    def _retire(self, code):
        call = self._call
        self._phase = Phase.STOPPING
        clean = self._cleanup(call)
        try:
            self._check(call)
        except _Stop as stop:
            code = stop.code
        except Exception:
            code = Code.UNAVAILABLE
        if not clean:
            self._fault, code = True, Code.CLEANUP
            try:
                # [LAW:one-source-of-truth] Fault only the borrowed owning generation.
                self._owner.release(call.snapshot.current_turn.generation, cleaned=False)
            except (StaleOwnerError, FaultedError):
                pass  # Local fault remains; a successor is not ours to alter.
        completion = Completion(code, call.provider_id, call.model_version, call.failures)
        with self._gate:
            if clean and call.epoch != self._epoch:
                completion = replace(completion, code=Code.CANCELED)
            elif clean and not self._owner.accepts(call.snapshot.current_turn.generation):
                completion = replace(completion, code=Code.STALE)
            self._terminal, self._call = completion, None
            self._phase = Phase.FAULTED if self._fault else Phase.IDLE
            self._code = completion.code

    def poll(self) -> Completion | None:
        with self._lock:
            if self._busy:
                return None
            self._run(self._advance)
            result, self._terminal = self._terminal, None
            return result

    def cancel(self) -> None:
        with self._gate:
            self._epoch += 1
        with self._lock:
            # Reentry records intent; the active callback may still allocate.
            if self._call is not None and not self._busy:
                self._run(lambda: self._retire(Code.CANCELED))
