"""Headless model for a future focused Tk panel, not a deployed GUI.

Private preview delivery is an explicit trusted in-process binding, never public
status or a model tool. The injected sender carries closed controls to the VM;
an accepted control is not an execution receipt. No window/key hook is created.
"""
from dataclasses import dataclass, field
import json
import re
import threading
import time
from uuid import uuid4

from runtime.voice.control import decode_control
from runtime.voice.speech import snapshot_state


_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
_PHASES = {'idle', 'capturing', 'processing', 'routing', 'faulted', 'dictation'}


@dataclass(frozen=True)
class _Preview:
    token: str = field(repr=False)
    label: str
    issued: int
    expires: int
    state: object = field(repr=False)


class VoicePanelModel:
    def __init__(self, state, send_control, *, clock=None, identifiers=None):
        if not callable(state) or not callable(send_control):
            raise ValueError('panel.invalid-binding')
        self.state, self.send_control = state, send_control
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._identifiers = identifiers or (lambda: str(uuid4()))
        self._lock = threading.RLock()
        self._session = self._preview = None
        self._epoch = 0
        self._last_now = None
        self._seen = set()
        self._busy = False
        self._phase, self._degraded = 'idle', False
        self.code = 'panel.disconnected'

    def connect(self, session_id):
        if type(session_id) is not str or not _ID.fullmatch(session_id):
            raise ValueError('panel.invalid-session')
        with self._lock:
            self._epoch += 1
            self._session, self._preview = session_id, None
            self._phase, self._degraded = 'idle', False
            self.code = 'panel.connected'

    def disconnect(self):
        with self._lock:
            self._epoch += 1
            self._session = self._preview = None
            self.code = 'panel.disconnected'

    def update_status(self, phase, *, degraded=False):
        if type(phase) is not str or phase not in _PHASES or type(degraded) is not bool:
            raise ValueError('panel.invalid-status')
        with self._lock:
            self._phase, self._degraded = phase, degraded

    def _now(self):
        value = self._clock()
        if type(value) is not int or value < 0:
            raise ValueError('panel.invalid-clock')
        if self._last_now is not None and value < self._last_now:
            raise ValueError('panel.clock-regressed')
        self._last_now = value
        return value

    def _current(self, preview, epoch):
        current, now = snapshot_state(self.state()), self._now()
        return (self._session is not None and self._epoch == epoch
                and current == preview.state and not current.muted and current.mode == 'command'
                and preview.issued <= now < preview.expires)

    def present_preview(self, token, capability_label, expires_at_ms, *, state):
        with self._lock:
            if self._busy or self._session is None:
                return False
            self._busy = True
            self._preview = None
            epoch = self._epoch
            try:
                now = self._now()
                if (type(token) is not str or not _ID.fullmatch(token)
                        or token in self._seen or len(self._seen) >= 4096
                        or type(capability_label) is not str or not 0 < len(capability_label) <= 160
                        or not capability_label.isprintable()
                        or type(expires_at_ms) is not int or not 0 < expires_at_ms - now <= 30000):
                    return False
                preview = _Preview(token, capability_label, now, expires_at_ms, snapshot_state(state))
                if not self._current(preview, epoch):
                    return False
                self._seen.add(token)
                self._preview = preview
                self.code = 'panel.preview'
                return True
            except Exception:
                self.code = 'panel.unavailable'
                return False
            finally:
                self._busy = False

    def view(self):
        with self._lock:
            preview = self._preview
            if self._busy:
                preview = None
            else:
                self._busy = True
                try:
                    remaining = 0 if preview is None else max(0, preview.expires - self._now())
                    if preview is not None and not self._current(preview, self._epoch):
                        self._preview = preview = None
                    if remaining == 0 or preview is not self._preview:
                        self._preview = preview = None
                except Exception:
                    self._preview = preview = None
                finally:
                    self._busy = False
            return {'connected': self._session is not None, 'phase': self._phase,
                    'degraded': self._degraded, 'capability_label': preview.label if preview else None,
                    'preview': 'Confirm: ' + preview.label + '?' if preview else None,
                    'expires_in_ms': remaining if preview else 0, 'can_confirm': preview is not None}

    def confirm(self, approved, *, channel='panel'):
        with self._lock:
            if (self._busy or self._preview is None or type(approved) is not bool
                    or channel not in ('panel', 'keyboard')):
                return False
            self._busy = True
            preview, self._preview = self._preview, None  # Consume BEFORE callbacks.
            epoch, session = self._epoch, self._session
            try:
                if not self._current(preview, epoch):
                    self.code = 'panel.stale'
                    return False
                payload = json.dumps({'version': 1, 'op': 'confirm', 'request_id': self._identifiers(),
                    'session_id': session, 'context_epoch': preview.state.key, 'token': preview.token,
                    'channel': channel, 'approved': approved}).encode('utf-8')
                decode_control(payload)
                if not self._current(preview, epoch):
                    self.code = 'panel.stale'
                    return False
                response = self.send_control(payload)
                accepted = type(response) is dict and response.get('status') == 'ok' and response.get('code') == 'control.ok'
                self.code = 'panel.sent' if accepted else 'panel.denied'
                return accepted
            except Exception:
                self.code = 'panel.uncertain'
                return False
            finally:
                self._busy = False

    def key(self, key, *, focused):
        if focused is not True or key not in ('Return', 'Escape'):
            return False
        return self.confirm(key == 'Return', channel='keyboard')
