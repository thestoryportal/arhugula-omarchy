"""Append-only correlated events, with a private single-owner SQLite adapter."""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading

from .contracts import ContractError, Event, decode, encode, loads


class JournalError(ValueError):
    """Journal ownership, integrity, version or IO failure."""


def _event(value):
    if not isinstance(value, Event):
        raise JournalError("journal accepts only Event records")
    return decode(encode(value))


def _cursor(after):
    if type(after) is not int or after < 0:
        raise JournalError("cursor must be a nonnegative integer")


def _wire(event):
    return json.dumps(encode(event), sort_keys=True, separators=(",", ":"), allow_nan=False)


class MemoryJournal:
    def __init__(self):
        self.dispatch_lock = threading.RLock()
        self._events = []
        self._ids = {}
        self._closed = False

    def _open(self):
        if self._closed:
            raise JournalError("journal is closed")

    def append(self, event):
        event = _event(event)
        with self.dispatch_lock:
            self._open()
            if event.event_id in self._ids:
                sequence, existing = self._ids[event.event_id]
                if _wire(existing) != _wire(event):
                    raise JournalError("event ID conflicts with existing payload")
                return sequence
            sequence = len(self._events) + 1
            self._events.append((sequence, event))
            self._ids[event.event_id] = (sequence, event)
            return sequence

    def read(self, after=0):
        _cursor(after)
        with self.dispatch_lock:
            self._open()
            return list(self._events[after:])

    def replay(self, consume, after=0):
        """Rebuild a projection from a snapshot; never invokes an executor."""
        for sequence, event in self.read(after):
            consume(sequence, event)

    def close(self):
        with self.dispatch_lock:
            self._closed = True

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *_):
        self.close()


class SQLiteJournal(MemoryJournal):
    VERSION = 1
    APPLICATION_ID = 0x4152474A

    def __init__(self, path):
        super().__init__()
        self._connection = None
        self._descriptor = None
        try:
            path = Path(path).absolute()
            parent = path.parent.stat()
            if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
                raise JournalError("journal parent must be owned and not writable by others")
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            created = False
            try:
                self._descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                self._descriptor = os.open(path, flags)
            info = os.fstat(self._descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                raise JournalError("journal must be a private, owned, single-link regular file")
            fcntl.flock(self._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not created:
                reader = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                try:
                    version = reader.execute("PRAGMA user_version").fetchone()[0]
                    application = reader.execute("PRAGMA application_id").fetchone()[0]
                    if version != self.VERSION or application != self.APPLICATION_ID:
                        raise JournalError("unknown journal database version or application")
                    reader.execute("SELECT sequence, event_id, payload FROM events LIMIT 0")
                finally:
                    reader.close()
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise JournalError("journal path changed while opening")
            self._connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, check_same_thread=False)
            self._connection.execute("PRAGMA synchronous=FULL")
            if created:
                with self._connection:
                    self._connection.execute("CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
                    self._connection.execute(f"PRAGMA user_version={self.VERSION}")
                    self._connection.execute(f"PRAGMA application_id={self.APPLICATION_ID}")
        except Exception as exc:
            self.close()
            if isinstance(exc, JournalError):
                raise
            raise JournalError("cannot open or exclusively own journal") from exc

    def append(self, event):
        event = _event(event)
        payload = _wire(event)
        with self.dispatch_lock:
            self._open()
            try:
                with self._connection:
                    existing = self._connection.execute("SELECT sequence, payload FROM events WHERE event_id = ?", (event.event_id,)).fetchone()
                    if existing:
                        if existing[1] != payload:
                            raise JournalError("event ID conflicts with existing payload")
                        return existing[0]
                    cursor = self._connection.execute("INSERT INTO events(event_id, payload) VALUES (?, ?)", (event.event_id, payload))
                    return cursor.lastrowid
            except sqlite3.Error as exc:
                raise JournalError("cannot append event") from exc

    def read(self, after=0):
        _cursor(after)
        with self.dispatch_lock:
            self._open()
            try:
                result = []
                rows = self._connection.execute("SELECT sequence, event_id, payload FROM events WHERE sequence > ? ORDER BY sequence", (after,))
                for sequence, identifier, payload in rows:
                    event = loads(payload)
                    if not isinstance(event, Event) or event.event_id != identifier:
                        raise JournalError("stored event identity mismatch")
                    result.append((sequence, event))
                return result
            except (sqlite3.Error, ContractError) as exc:
                raise JournalError("cannot read valid journal events") from exc

    def close(self):
        with self.dispatch_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if self._descriptor is not None:
                os.close(self._descriptor)
                self._descriptor = None
            self._closed = True
