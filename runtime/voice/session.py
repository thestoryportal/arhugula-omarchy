"""Process-local admission; logical cancellation never proves physical cleanup."""
import threading
from uuid import uuid4


class BusyError(RuntimeError):
    """An existing owner still holds resources."""


class FaultedError(BusyError):
    """Cleanup was not proven; external reconciliation is required."""


class StaleOwnerError(RuntimeError):
    """A cleanup report does not belong to the current resource owner."""


class SessionOwner:
    """Trusted coordinator seam, not an OS device lock or authorization token.

    Pair generations with session_id when carrying work across process/restart
    boundaries. The caller releases ONLY after all owned resources are cleaned;
    a false report latches a fault and cannot be reversed on this instance.
    Methods contain no callbacks or blocking device/provider operations.
    """

    def __init__(self):
        self._session_id = str(uuid4())
        self._lock = threading.Lock()
        self._generation = 0
        self._owner = None
        self._state = "idle"

    @property
    def session_id(self):
        return self._session_id

    def begin(self, mode: str) -> int:
        if type(mode) is not str or mode not in {"command", "dictation"}:
            raise ValueError("invalid session mode")
        with self._lock:
            if self._state == "faulted":
                raise FaultedError("cleanup requires external reconciliation")
            if self._state != "idle":
                raise BusyError("previous owner has not released resources")
            self._generation += 1
            self._owner = self._generation
            self._state = "owned"
            return self._owner

    def cancel(self) -> int:
        with self._lock:
            self._generation += 1
            if self._state == "owned":
                self._state = "canceling"
            return self._generation

    def accepts(self, generation: int) -> bool:
        if type(generation) is not int or generation <= 0:
            return False
        with self._lock:
            return self._state == "owned" and generation == self._owner

    def release(self, generation: int, cleaned: bool) -> None:
        if type(generation) is not int or generation <= 0 or type(cleaned) is not bool:
            raise ValueError("cleanup requires a generation and literal boolean")
        with self._lock:
            if self._state == "faulted":
                raise FaultedError("cleanup requires external reconciliation")
            if self._owner != generation:
                raise StaleOwnerError("cleanup does not match resource owner")
            if not cleaned:
                self._state = "faulted"
                return
            self._owner = None
            self._state = "idle"
