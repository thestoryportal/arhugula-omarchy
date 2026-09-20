"""Trusted local controls; same-UID code is NOT isolated by Unix permissions.

No model tool or remote transport may receive this endpoint. Handlers and state
come from the operator-owned startup path, never a wire approval flag. A control
acknowledgement is not an execution receipt or permission to retry an action.
"""
from dataclasses import dataclass
import fcntl
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import threading
import time


_SCHEMA = json.loads(files('schemas').joinpath('voice-session-v1.json').read_text())
_SHAPES = {shape['properties']['op']['const']: shape for shape in _SCHEMA['oneOf']}
_MUTATIONS = frozenset(_SHAPES) - {'status'}
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')


def decode_control(payload: bytes) -> dict:
    """Decode a single bounded UTF-8 object against the bundled closed schema."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('control.invalid')
            result[key] = value
        return result

    try:
        if type(payload) is not bytes or not 0 < len(payload) <= 4096:
            raise ValueError()
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs)
        if type(value) is not dict or type(value.get('op')) is not str:
            raise ValueError()
        shape = _SHAPES.get(value['op'])
        if shape is None or set(value) != set(shape['required']):
            raise ValueError()
        for key, rule in shape['properties'].items():
            item = value[key]
            if type(item) is not {'string': str, 'integer': int, 'boolean': bool}[rule['type']]:
                raise ValueError()
            if 'const' in rule and item != rule['const']:
                raise ValueError()
            if 'enum' in rule and item not in rule['enum']:
                raise ValueError()
            if 'pattern' in rule and re.fullmatch(rule['pattern'], item) is None:
                raise ValueError()
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError('control.invalid') from None


@dataclass(frozen=True)
class ControlState:
    context_epoch: str
    phase: str
    muted: bool

    def __post_init__(self):
        if (type(self.context_epoch) is not str or not _ID.fullmatch(self.context_epoch)
                or self.phase not in {'idle', 'capturing', 'processing', 'routing', 'faulted', 'dictation'}
                or type(self.muted) is not bool):
            raise ValueError('control.invalid-state')


def _reply(status, code, state=None):
    result = {'version': 1, 'status': status, 'code': code}
    if state is not None:
        result['state'] = state
    return result


class ControlDispatcher:
    """Bounded session-local replay guard, not a replacement for VM policy.

    handlers consume validated data and return a literal bool: accepted/denied.
    They must validate state at actuation and honor cancellation/owner cleanup.
    Exceptions are uncertain, and the request ID stays consumed. Tokens are
    accepted only on the trusted confirmation path, never returned in status.
    """

    def __init__(self, session_id, handlers, state):
        if (type(session_id) is not str or not _ID.fullmatch(session_id)
                or type(handlers) is not dict or set(handlers) != _MUTATIONS
                or not all(callable(handler) for handler in handlers.values()) or not callable(state)):
            raise ValueError('control.invalid-binding')
        self.session_id, self.handlers, self.state = session_id, dict(handlers), state
        self._seen = set()
        self._lock = threading.Lock()
        self._uid, self._pid = os.geteuid(), os.getpid()

    def handle(self, payload, *, peer_uid):
        if type(peer_uid) is not int or peer_uid != self._uid or os.getpid() != self._pid:
            return _reply('blocked', 'control.peer')
        if not self._lock.acquire(blocking=False):
            return _reply('blocked', 'control.busy')
        try:
            try:
                request = decode_control(payload)
            except ValueError:
                return _reply('blocked', 'control.invalid')
            try:
                state = self.state()
                if type(state) is not ControlState:
                    raise ValueError()
            except Exception:
                return _reply('blocked', 'control.state-unavailable')
            public = {'session_id': self.session_id, 'context_epoch': state.context_epoch,
                      'phase': state.phase, 'muted': state.muted}
            if request['op'] == 'status':
                return _reply('ok', 'control.ok', public)
            if request['session_id'] != self.session_id or request['context_epoch'] != state.context_epoch:
                return _reply('blocked', 'control.stale')
            identifier = request['request_id']
            if identifier in self._seen:
                return _reply('blocked', 'control.replayed')
            if len(self._seen) >= 4096:
                return _reply('blocked', 'control.exhausted')
            self._seen.add(identifier)
            try:
                # Recheck after state callback and replay bookkeeping; the
                # handler still owns final compare-and-act, not this sample.
                if self.state() != state:
                    return _reply('blocked', 'control.stale')
                accepted = self.handlers[request['op']](request)
                if type(accepted) is not bool:
                    raise ValueError()
            except Exception:
                return _reply('uncertain', 'control.uncertain')
            return _reply('ok' if accepted else 'blocked', 'control.ok' if accepted else 'control.denied')
        finally:
            self._lock.release()


class LocalControlServer:
    """Explicit single-request AF_UNIX server in an existing private directory.

    Request framing: 4-byte network-order length, then <=4096 UTF-8 JSON bytes.
    Response: one bounded JSON object followed by EOF. No pipelining/retry loop.
    start never unlinks a stale endpoint; close only removes its own inode.
    """

    def __init__(self, directory, dispatcher, *, timeout_s=0.25):
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 2 or not isinstance(dispatcher, ControlDispatcher)):
            raise ValueError('control.invalid-server')
        self.directory = Path(directory).absolute()
        self.path = self.directory / 'control.sock'
        self.dispatcher, self.timeout_s = dispatcher, timeout_s
        self._directory_fd = self._socket = self._identity = None
        self._pid = os.getpid()

    def start(self):
        if self._socket is not None or self._directory_fd is not None or os.getpid() != self._pid:
            raise ValueError('control.already-owned')
        try:
            for path in (self.directory, *self.directory.parents):
                if path.is_symlink():
                    raise ValueError()
            self._directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            info = os.fstat(self._directory_fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError()
            fcntl.flock(self._directory_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                os.stat('control.sock', dir_fd=self._directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError()
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            # Anchor creation and cleanup to the opened directory, not a later
            # replacement of its pathname. Never bind a TCP/network listener.
            self._socket.bind(f'/proc/self/fd/{self._directory_fd}/control.sock')
            owned = os.stat('control.sock', dir_fd=self._directory_fd, follow_symlinks=False)
            if not stat.S_ISSOCK(owned.st_mode) or owned.st_uid != os.geteuid():
                raise ValueError()
            self._identity = (owned.st_dev, owned.st_ino)
            # The fresh socket is inside an anchored 0700 directory; other
            # UIDs cannot substitute it. Avoid newer fchmodat2-only flags.
            os.chmod('control.sock', 0o600, dir_fd=self._directory_fd)
            self._socket.listen(1)
            self._socket.settimeout(self.timeout_s)
        except Exception:
            self.close()
            raise ValueError('control.socket-unavailable') from None

    @staticmethod
    def _read(connection, size, deadline):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            connection.settimeout(remaining)
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise ValueError()
            data.extend(chunk)
        return bytes(data)

    def serve_once(self):
        if self._socket is None or os.getpid() != self._pid:
            raise ValueError('control.not-owned')
        try:
            connection, _ = self._socket.accept()
        except socket.timeout:
            return False
        with connection:
            deadline = time.monotonic() + self.timeout_s
            try:
                _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.geteuid():
                    reply = _reply('blocked', 'control.peer')
                else:
                    length = struct.unpack('!I', self._read(connection, 4, deadline))[0]
                    if not 0 < length <= 4096:
                        raise ValueError()
                    reply = self.dispatcher.handle(self._read(connection, length, deadline), peer_uid=uid)
            except (OSError, ValueError, struct.error):
                reply = _reply('blocked', 'control.invalid-frame')
            try:
                connection.settimeout(self.timeout_s)
                connection.sendall(json.dumps(reply, separators=(',', ':')).encode())
            except OSError:
                pass  # No retry of an uncertain request or its action.
        return True

    def close(self):
        if os.getpid() != self._pid:
            raise ValueError('control.not-owned')
        try:
            if self._socket is not None:
                self._socket.close()
            if self._directory_fd is not None and self._identity is not None:
                try:
                    info = os.stat('control.sock', dir_fd=self._directory_fd, follow_symlinks=False)
                    if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self._identity:
                        os.unlink('control.sock', dir_fd=self._directory_fd)
                except FileNotFoundError:
                    pass
        finally:
            if self._directory_fd is not None:
                os.close(self._directory_fd)
            self._socket = self._directory_fd = self._identity = None
