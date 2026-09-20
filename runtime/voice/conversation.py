"""Offline conversation controller over one participating SessionOwner.

Snapshot/job callbacks are trusted, bounded and synchronous. Poll count bounds
pending work, not wall time. No listener, provider, action or output is discovered.
Call poll to observe external snapshot changes; there is no background monitor.
"""
from dataclasses import replace
import threading

from .conversation_records import (
    Clarification, Code, ContextState, Display, Entry, Exchange, Notice, Request,
    Response, Snapshot, TurnToken, text,
)
from .session import BusyError, SessionOwner


class _Stop(Exception):
    def __init__(self, code):
        self.code = code


class Conversation:
    def __init__(self, owner, snapshot, jobs):
        if not isinstance(owner, SessionOwner) or not callable(snapshot) or not callable(jobs):
            raise ValueError('conversation.invalid-binding')
        self.owner = owner
        self._snapshot_source, self._jobs = snapshot, jobs
        self._lock, self._gate = threading.RLock(), threading.Lock()
        self._busy = False
        self._lease = self._intent = self._snapshot = self._session_id = None
        self._request = self._job = None
        self._unknown_job = False
        self._history = ()
        self._turn = self._polls = 0
        self._phase, self._code = Display.INACTIVE, Code.INACTIVE

    @property
    def notice(self):
        with self._lock, self._gate:
            state = Display.STOPPING if self._intent is not None else self._phase
            return Notice(1, self._session_id, self.pending, state, self._code)

    @property
    def pending(self):
        return None if self._request is None else self._request.token

    @property
    def history(self):
        return self._history

    def _sample(self):
        try:
            snapshot = self._snapshot_source()
            if type(snapshot) is not Snapshot:
                raise ValueError()
            return snapshot
        except Exception:
            raise _Stop(Code.UNAVAILABLE) from None

    @staticmethod
    def _eligible(snapshot):
        policy, profile = snapshot.policy, snapshot.profile
        if (policy is None or not profile.enabled or not profile.voice_enabled
                or policy.profile_id != profile.profile_id or policy.policy_id != profile.policy_id
                or policy.exit_key in snapshot.setup.occupied | snapshot.setup.reserved):
            raise _Stop(Code.DENIED)
        if snapshot.context.state is ContextState.UNAVAILABLE:
            raise _Stop(Code.UNAVAILABLE)
        if (len(snapshot.context.items) > policy.limits.context_items
                or sum(len(i.text) for i in snapshot.context.items) > policy.limits.context_chars):
            raise _Stop(Code.LIMIT)

    def _check(self):
        current = self._sample()
        with self._gate:
            if self._intent is not None:
                raise _Stop(self._intent)
            if current != self._snapshot or not self.owner.accepts(self._lease):
                raise _Stop(Code.STALE)

    def _invalidate(self, code):
        with self._gate:
            if (self._intent is None or self._intent is Code.CANCELED
                    or code in (Code.ENDED, Code.HANDOFF)):
                self._intent = code
            if self._lease is not None:
                self.owner.cancel(generation=self._lease)

    def _run(self, operation):
        with self._lock:
            if self._busy:
                raise BusyError('conversation.transition-active')
            self._busy = True
            result = None
            try:
                result = operation()
            except _Stop as stop:
                self._invalidate(stop.code)
            finally:
                try:
                    if self._intent is not None:
                        self._stop()
                        result = None
                finally:
                    self._busy = False
            return result

    def _cleanup(self):
        clean = not self._unknown_job
        if self._job is not None:
            try:
                self._job.cancel()
                clean = (self._job.cleanup_proven is True) and clean
            except Exception:
                clean = False
        self._job = None
        self._unknown_job = not clean
        return clean

    def _stop(self):
        # [LAW:no-ambient-temporal-coupling] Cleanup runs after callbacks unwind.
        self._phase = Display.STOPPING
        clean = self._cleanup()
        if clean and self._intent is Code.CANCELED and self._snapshot is not None:
            try:
                if self._sample() != self._snapshot:
                    self._invalidate(Code.STALE)
            except _Stop as stop:
                self._invalidate(stop.code)
        self._request = None
        with self._gate:
            code = self._intent
            lease, self._lease = self._lease, None
            if lease is not None:
                self.owner.release(lease, cleaned=clean)
            self._phase, self._code = Display.INACTIVE, code
            if not clean:
                self._phase, self._code = Display.FAULTED, Code.CLEANUP
            elif code is Code.CANCELED and lease is not None:
                try:
                    # Participating clients can win this gap; never take over.
                    self._lease = self.owner.begin('conversation')
                    self._phase = Display.READY
                except BusyError:
                    self._code = Code.BUSY
            self._intent = None
        if self._phase is not Display.READY:
            self._history = ()
            self._snapshot = self._session_id = None

    def enter(self, channel):
        if type(channel) is not Entry:
            raise ValueError('conversation.invalid-entry')

        def enter():
            if self._phase is not Display.INACTIVE:
                raise BusyError('conversation.not-inactive')
            snapshot = self._sample()
            self._eligible(snapshot)
            if channel not in snapshot.policy.entries:
                raise _Stop(Code.DENIED)
            with self._gate:
                if self._intent is not None:
                    raise _Stop(self._intent)
                self._lease = self.owner.begin('conversation')
                self._session_id = self.owner.session_id + ':' + str(self._lease)
            self._snapshot, self._history, self._turn = snapshot, (), 0
            self._phase, self._code = Display.READY, Code.READY
            self._check()
            return True
        return self._run(enter)

    def _context_size(self):
        return (sum(len(i.text) for i in self._snapshot.context.items)
                + sum(len(i.text) + len(i.response) for i in self._history))

    def _start(self):
        self._phase, self._code = Display.PROCESSING, Code.PROCESSING
        self._polls = 0
        try:
            self._unknown_job = True
            self._job = self._jobs()
            if self._job is None:
                raise ValueError()
            self._unknown_job = False
            self._check()
            self._job.start(self._request)
            self._check()
        except _Stop:
            raise
        except Exception:
            raise _Stop(Code.UNAVAILABLE) from None

    def submit(self, value):
        text(value)

        def submit():
            if self._phase not in (Display.READY, Display.PROCESSING, Display.CLARIFYING):
                raise BusyError('conversation.not-active')
            self._check()
            policy = self._snapshot.policy
            text(value, policy.limits.text_chars)
            if value == policy.exit_phrase:
                raise _Stop(Code.ENDED)
            if self._phase is not Display.READY:
                raise BusyError('conversation.turn-active')
            if (self._turn >= policy.limits.turns
                    or self._context_size() + len(value) > policy.limits.context_chars):
                raise _Stop(Code.LIMIT)
            self._turn += 1
            token = TurnToken(self._session_id, self._turn, self._lease, policy.profile_id,
                              self._snapshot.revision, policy.revision,
                              self._snapshot.context.revision)
            self._request = Request(token, value, self._snapshot.context, self._history, None)
            if self._snapshot.context.state is ContextState.CONFLICTING:
                self._phase, self._code = Display.CLARIFYING, Code.CONFLICT
            else:
                self._start()
            return token
        return self._run(submit)

    def clarify(self, clarification):
        if type(clarification) is not Clarification:
            raise ValueError('conversation.invalid-clarification')

        def clarify():
            if self._phase is not Display.CLARIFYING:
                return False
            self._check()
            if (clarification.token != self.pending
                    or clarification.conflict_id != self._request.context.conflict_id):
                return False
            if clarification.use_current:
                self._request = replace(self._request, resolved_conflict=clarification.conflict_id)
                self._start()
            else:
                self._request = None
                self._phase, self._code = Display.READY, Code.CANCELED
            return True
        return self._run(clarify)

    def poll(self):
        def poll():
            if self._phase not in (Display.READY, Display.PROCESSING, Display.CLARIFYING):
                return None
            self._check()
            if self._phase is not Display.PROCESSING:
                return None
            self._polls += 1
            try:
                result = self._job.poll()
            except Exception:
                raise _Stop(Code.UNAVAILABLE) from None
            self._check()
            limits = self._snapshot.policy.limits
            if result is None:
                if self._polls >= limits.polls:
                    raise _Stop(Code.LIMIT)
                return None
            if type(result) is not Response or result.token != self.pending:
                raise _Stop(Code.INVALID_RESULT)
            if (len(result.text) > limits.text_chars or self._context_size()
                    + len(self._request.text) + len(result.text) > limits.context_chars):
                raise _Stop(Code.LIMIT)
            if not self._cleanup():
                raise _Stop(Code.CLEANUP)
            self._check()
            exchange = Exchange(result.token, self._request.text, result.text,
                                self._request.resolved_conflict)
            # [LAW:no-ambient-temporal-coupling] Publication and cancellation
            # have one ordering point, after all callbacks and value construction.
            with self._gate:
                if self._intent is not None:
                    raise _Stop(self._intent)
                if not self.owner.accepts(self._lease):
                    raise _Stop(Code.STALE)
                self._history += (exchange,)
                self._request = None
                self._phase, self._code = Display.READY, Code.READY
            return result
        return self._run(poll)

    def exit_key(self, key):
        text(key, 128)

        def exit_key():
            if self._phase not in (Display.READY, Display.PROCESSING, Display.CLARIFYING):
                return False
            self._check()
            if key != self._snapshot.policy.exit_key:
                return False
            self._invalidate(Code.ENDED)
            return True
        # A matching key reports recognition even though it invalidates work.
        matched = [False]

        def record_match():
            matched[0] = exit_key()
        self._run(record_match)
        return matched[0]

    def _cancel(self, code):
        # Logical cancellation must not wait behind a synchronous collaborator.
        with self._gate:
            active = self._lease is not None or self._busy
        if not active:
            return
        self._invalidate(code)
        with self._lock:
            if not self._busy:
                self._run(lambda: None)

    def cancel_turn(self):
        self._cancel(Code.CANCELED)

    def end(self):
        self._cancel(Code.ENDED)

    def handoff(self):
        self._cancel(Code.HANDOFF)
