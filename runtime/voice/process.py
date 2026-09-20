"""Bounded Linux subprocess ownership for trusted, fixed local adapter argv.

Not a sandbox: callers must approve the executable/config separately. Descendants
that escape the process group are outside this trusted-worker contract.
"""
from dataclasses import dataclass, field
import os
import selectors
import signal
import subprocess
import threading
import time


@dataclass(frozen=True)
class ProcessResult:
    status: str
    stdout: bytes = field(repr=False)
    code: str


class OwnedProcess:
    def __init__(self, argv: tuple[str, ...], *, max_output: int, timeout_s: float,
                 stdout_consumer=None, max_stdout=None, idle_timeout_s=None):
        if (type(argv) is not tuple or not argv or
                any(type(x) is not str or not x or '\x00' in x for x in argv) or
                not os.path.isabs(argv[0]) or sum(len(x) for x in argv) > 8192):
            raise ValueError('requires bounded, fixed absolute executable argv')
        if type(max_output) is not int or not 0 < max_output <= 65536:
            raise ValueError('invalid process output bound')
        if type(timeout_s) not in (int, float) or not 0 < timeout_s <= 30:
            raise ValueError('invalid process deadline')
        if stdout_consumer is not None and not callable(stdout_consumer):
            raise ValueError('stream consumer must be trusted callable')
        if max_stdout is not None and (stdout_consumer is None or type(max_stdout) is not int or not 0 < max_stdout <= 480000):
            raise ValueError('invalid streaming output bound')
        if idle_timeout_s is not None and (stdout_consumer is None or type(idle_timeout_s) not in (int, float) or not 0 < idle_timeout_s <= timeout_s):
            raise ValueError('invalid streaming idle deadline')
        self._argv, self._max_output, self._timeout = argv, max_output, timeout_s
        self._consumer, self._max_stdout = stdout_consumer, max_stdout or max_output
        self._idle_timeout = idle_timeout_s
        self._creator = os.getpid()
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = self._process = self._result = None
        self._started = False

    def _check_owner(self):
        if os.getpid() != self._creator:
            raise RuntimeError('process adapter cannot be inherited across fork')

    def start(self, input_bytes: bytes | None):
        self._check_owner()
        if input_bytes is not None and (type(input_bytes) is not bytes or len(input_bytes) > 480044):
            raise ValueError('input must be bounded immutable bytes')
        with self._lock:
            if self._started or self._result is not None:
                raise RuntimeError('owned process is single-use')
            self._started = True
            try:
                self._process = subprocess.Popen(
                    self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, shell=False, start_new_session=True,
                    close_fds=True, bufsize=0)
            except OSError:
                self._result = ProcessResult('failed', b'', 'process.start-failed')
                return
            try:
                self._thread = threading.Thread(target=self._run, args=(input_bytes or b'',), daemon=True)
                self._thread.start()
            except Exception:
                # Ownership has not transferred to a running supervisor. Keep
                # admission locked until this synchronous cleanup is complete.
                clean = self._cleanup()
                self._result = ProcessResult('failed' if clean else 'uncertain', b'',
                                             'process.start-failed' if clean else 'process.cleanup-unproven')

    def poll(self) -> ProcessResult | None:
        self._check_owner()
        with self._lock:
            return self._result

    def cancel(self) -> ProcessResult:
        self._check_owner()
        with self._lock:
            if self._result is not None:
                return self._result
            if not self._started:
                self._result = ProcessResult('canceled', b'', 'process.canceled')
                return self._result
            self._cancel.set()
            thread = self._thread
        thread.join(timeout=0.9)
        with self._lock:
            if self._result is None:
                self._result = ProcessResult('uncertain', b'', 'process.cleanup-unproven')
            return self._result

    def _cleanup(self):
        # Do not reap the leader before signaling the group: retaining its PID
        # prevents that process-group number being reused for unrelated work.
        child = self._process
        clean = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass
            except OSError:
                clean = False
            if sig == signal.SIGTERM:
                time.sleep(0.05)
        try:
            child.wait(timeout=0.5)
        except (subprocess.TimeoutExpired, OSError):
            clean = False
        # Read-only probe after reaping; never signal this numeric group again.
        try:
            os.killpg(child.pid, 0)
            clean = False
        except ProcessLookupError:
            pass
        except OSError:
            clean = False
        for stream in (child.stdin, child.stdout, child.stderr):
            try:
                stream.close()
            except OSError:
                clean = False
        return clean

    def _run(self, data):
        child = self._process
        output = bytearray()
        counts = {'stdout': 0, 'stderr': 0}
        offset = 0
        status, code = 'failed', 'process.io-failed'
        selector = None
        try:
            selector = selectors.DefaultSelector()
            deadline = time.monotonic() + self._timeout
            last_stdout = time.monotonic()
            for name, stream in (('stdout', child.stdout), ('stderr', child.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            if data:
                os.set_blocking(child.stdin.fileno(), False)
                selector.register(child.stdin, selectors.EVENT_WRITE, 'stdin')
            else:
                child.stdin.close()
            while True:
                if self._cancel.is_set():
                    status, code = 'canceled', 'process.canceled'
                    break
                if time.monotonic() >= deadline:
                    status, code = 'failed', 'process.timeout'
                    break
                if self._idle_timeout is not None and time.monotonic() - last_stdout >= self._idle_timeout:
                    status, code = 'failed', 'process.stalled'
                    break
                overflow = False
                for key, _ in selector.select(timeout=0.01):
                    stream, name = key.fileobj, key.data
                    try:
                        if name == 'stdin':
                            offset += os.write(stream.fileno(), data[offset:offset + 4096])
                            if offset == len(data):
                                selector.unregister(stream)
                                stream.close()
                                data = b''
                            continue
                        chunk = os.read(stream.fileno(), 4096)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    counts[name] += len(chunk)
                    if counts[name] > (self._max_stdout if name == 'stdout' else self._max_output):
                        overflow = True
                        break
                    if name == 'stdout':
                        last_stdout = time.monotonic()
                        if self._consumer is None:
                            output.extend(chunk)
                        else:
                            self._consumer(chunk)
                if overflow:
                    status, code = 'failed', 'process.output-limit'
                    break
                exited = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if exited is not None and not selector.get_map():
                    if exited.si_code == os.CLD_EXITED and exited.si_status == 0:
                        status, code = 'success', 'process.ok'
                    else:
                        status, code = 'failed', 'process.exit'
                    break
        except Exception:
            status, code = 'failed', 'process.io-failed'
        finally:
            try:
                if selector is not None:
                    selector.close()
            except Exception:
                status, code = 'failed', 'process.io-failed'
            if not self._cleanup():
                status, code = 'uncertain', 'process.cleanup-unproven'
            result = ProcessResult(status, bytes(output) if status == 'success' else b'', code)
            output.clear()
            with self._lock:
                if self._result is None:
                    self._result = result
