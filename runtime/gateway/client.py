"""Single-owner offline gateway lifecycle over bounded, injected effect seams.

Transports must attest an already-verified TLS peer before begin receives a
credential. No transport or provider implementation is installed by this module.
All callbacks must be bounded; no Python callback is preempted by this client.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from ipaddress import ip_address
import re
from threading import RLock
from typing import Callable, Protocol
from urllib.parse import urlsplit

from runtime.contracts import Provider
from .admission import Bearer, ReplayHistory, check_provider, provider_snapshot
from .wire import (
    GatewayError, RemoteError, Output, Request, catalog_revision,
    parse_request, parse_response, request_bytes,
)


@dataclass(frozen=True)
class Endpoint:
    url: str
    peer_identity: str

    def __post_init__(self):
        try:
            if (type(self.url) is not str or any(ord(c) <= 32 or ord(c) > 126 for c in self.url)
                    or any(c in self.url for c in ('?', '#', '%', '\\'))):
                raise ValueError
            parts = urlsplit(self.url)
            if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
                    or parts.password is not None or parts.query or parts.fragment
                    or parts.path != '/v1/gateway' or parts.port == 0):
                raise ValueError
            try:
                ip_address(parts.hostname)
            except ValueError:
                if len(parts.hostname) > 253 or any(
                    re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) is None
                    for label in parts.hostname.split('.')
                ):
                    raise ValueError
            if type(self.peer_identity) is not str or re.fullmatch('[0-9a-f]{64}', self.peer_identity) is None:
                raise ValueError
        except (ValueError, TypeError):
            raise GatewayError('identity') from None


@dataclass(frozen=True)
class Outgoing:
    endpoint: Endpoint
    authorization: str = field(repr=False)
    body: bytes = field(repr=False)
    budget_ms: int


@dataclass(frozen=True)
class HttpReply:
    status: int
    body: bytes = field(repr=False)
    peer_identity: str


class Job(Protocol):
    def poll(self) -> HttpReply | bytes | None: ...
    def cancel(self) -> bool: ...


class Transport(Protocol):
    peer_identity: str

    def begin(self, outgoing: Outgoing) -> Job | RemoteError: ...


@dataclass(frozen=True)
class Host:
    provider: Provider
    endpoint: Endpoint
    bearer: Bearer = field(repr=False)
    transport: Transport = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'provider', provider_snapshot(self.provider, 'host'))
        if type(self.endpoint) is not Endpoint or type(self.bearer) is not Bearer:
            raise GatewayError('identity')


@dataclass(frozen=True)
class Local:
    provider: Provider
    begin: Callable[[Request, int], Job | RemoteError] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'provider', provider_snapshot(self.provider, 'vm'))


@dataclass(frozen=True)
class Failure:
    code: str
    provider_id: str
    model_version: str


@dataclass(frozen=True)
class Success:
    output: Output = field(repr=False)
    provider_id: str
    model_version: str


@dataclass(frozen=True)
class Degraded:
    result: Success
    primary: Failure


@dataclass(frozen=True)
class Failed:
    failures: tuple[Failure, ...]


@dataclass
class _Call:
    request: Request
    route: Host | Local
    deadline: int | None = None
    last_time: int | None = None
    job: Job | None = None
    primary: Failure | None = None
    cancel_requested: bool = False


class GatewayClient:
    """One active operation and one unconsumed terminal result; memory-only replay.

    A begin callback returns a Job (owned resources) or RemoteError (an atomic
    failure with no owned resources). An exception cannot prove this, so begin
    exceptions latch cleanup failure. cancel must return exact True to prove
    synthesis/transport cleanup, including after a completed response.
    """

    def __init__(self, host: Host, catalog_version: int, clock: Callable[[], int], local: Local | None = None):
        if type(host) is not Host or (local is not None and type(local) is not Local):
            raise GatewayError('identity')
        self._host, self._local = host, local
        self._catalog_version, self._clock = catalog_revision(catalog_version), clock
        self._history = ReplayHistory()
        self._lock = RLock()
        self._active = None
        self._terminal = None
        self._fault = None
        self._inside_callback = False
        self._unclean = False

        self._configuring = False
        self._disabled = False
        self._permit = None
        self._configuration_owner = None

    def claim_configuration(self):
        """Attach one trusted configuration owner, atomically starting disabled."""
        with self._lock:
            if (self._configuration_owner is not None or self._active is not None
                    or self._terminal is not None or self._inside_callback or self._configuring):
                raise GatewayError('busy')
            if self._fault:
                raise GatewayError(self._fault)
            self._configuration_owner = object()
            self._disabled = True
            return self._configuration_owner

    def _require_configuration_owner(self, owner):
        if owner is not self._configuration_owner:
            raise GatewayError('identity')

    @contextmanager
    def configuration(self, owner=None):
        """Serialize trusted configuration state with calls; forbid callback reentry.

        The caller may publish its own state and rebind atomically here. This
        grants no authority to model data. Keep transaction bodies bounded and
        effect-free; lifecycle operations remain owned by this gateway.
        """
        with self._lock:
            self._require_configuration_owner(owner)
            if self._inside_callback or self._configuring:
                raise GatewayError('busy')
            self._configuring = True
            try:
                yield
            finally:
                self._configuring = False

    def reconfigure(self, host: Host, local: Local | None = None, *, permit=None, owner=None):
        """Rebind idle routes without discarding replay, exhaustion or faults.

        permit(provider, service, monotonic_ms) is a bounded trusted callback;
        exact True permits an attempt. Refusal/exception cancels without fallback.
        """
        with self._lock:
            self._require_configuration_owner(owner)
            if self._active is not None or self._terminal is not None or self._inside_callback:
                raise GatewayError('busy')
            if self._fault:
                raise GatewayError(self._fault)
            if type(host) is not Host or (local is not None and type(local) is not Local):
                raise GatewayError('identity')
            if permit is not None and not callable(permit):
                raise GatewayError('invalid_request')
            # [LAW:one-source-of-truth] Route changes retain the admission owner.
            self._host, self._local, self._permit = host, local, permit
            self._disabled = False

    def disable(self, *, owner=None):
        """Close admission immediately, retiring any job through normal cleanup."""
        with self._lock:
            self._require_configuration_owner(owner)
            self._disabled = True
            self.cancel()

    @property
    def cleanup_proven(self):
        with self._lock:
            return not self._unclean

    def _invoke(self, function, *args):
        self._inside_callback = True
        try:
            return function(*args)
        finally:
            self._inside_callback = False

    def _failure(self, call, code):
        return Failure(code, call.route.provider.provider_id, call.route.provider.model_version)

    def _interruption(self, call):
        try:
            now = self._invoke(self._clock)
            if type(now) is not int or now < 0 or (call.last_time is not None and now < call.last_time):
                raise ValueError
        except Exception:
            self._fault = 'clock'
            return 'clock'
        call.last_time = now
        if call.deadline is None:
            call.deadline = now + call.request.budget_ms
        if call.cancel_requested:
            return 'canceled'
        if now >= call.deadline:
            return 'timeout'
        return None

    def start(self, request: Request):
        with self._lock:
            if (self._active is not None or self._terminal is not None
                    or self._inside_callback or self._configuring):
                raise GatewayError('busy')
            if self._fault:
                raise GatewayError(self._fault)
            if self._disabled:
                raise GatewayError('canceled')
            request = parse_request(request_bytes(request))
            if request.catalog_version != self._catalog_version:
                raise GatewayError('stale_catalog')
            if (request.provider_id, request.model_version) != (self._host.provider.provider_id,
                                                              self._host.provider.model_version):
                raise GatewayError('identity')
            self._history.claim(request.request_id)
            self._active = _Call(request, self._host)
            self._begin()

    def _begin(self):
        call = self._active
        interrupted = self._interruption(call)
        if interrupted:
            self._finish(self._failure(call, interrupted))
            return
        request = replace(call.request, provider_id=call.route.provider.provider_id,
                          model_version=call.route.provider.model_version,
                          budget_ms=call.deadline - call.last_time)
        try:
            request_bytes(request)
            check_provider(request, call.route.provider, self._catalog_version)
            if type(call.route) is Host:
                peer = self._invoke(lambda: call.route.transport.peer_identity)
                if type(peer) is not str or peer != call.route.endpoint.peer_identity:
                    raise GatewayError('identity')
        except GatewayError as error:
            self._finish(self._failure(call, error.code))
            return
        except Exception:
            self._finish(self._failure(call, 'identity'))
            return
        # [LAW:effects-at-boundaries] No credential goes to an unattested transport.
        interrupted = self._interruption(call)
        if interrupted:
            self._finish(self._failure(call, interrupted))
            return
        request = replace(request, budget_ms=call.deadline - call.last_time)
        call.request = request
        # [LAW:single-enforcer] Configuration admission precedes every effect,
        # including fallback; the existing callback barrier protects reentry.
        try:
            permitted = (self._permit is None or self._invoke(
                self._permit, call.route.provider, request.service, call.last_time) is True)
        except Exception:
            permitted = False
        if not permitted or self._disabled or call.cancel_requested:
            self._finish(self._failure(call, 'canceled'))
            return
        self._unclean = True
        try:
            if type(call.route) is Host:
                outgoing = Outgoing(call.route.endpoint, call.route.bearer.header(),
                                    request_bytes(request), request.budget_ms)
                job = self._invoke(call.route.transport.begin, outgoing)
            else:
                job = self._invoke(call.route.begin, request, request.budget_ms)
        except Exception:
            # A throwing begin did not return an owned cleanup capability.
            self._finish(self._failure(call, 'provider_failed'))
            return
        if type(job) is RemoteError:
            self._unclean = False
            self._finish(self._failure(call, GatewayError(job.code).code))
            return
        call.job = job
        interrupted = self._interruption(call)
        if interrupted:
            self._finish(self._failure(call, interrupted))

    def _retire(self, call):
        job, call.job = call.job, None
        if job is None:
            return not self._unclean
        try:
            proven = self._invoke(job.cancel) is True
        except Exception:
            proven = False
        self._unclean = not proven
        return proven

    def _finish(self, value):
        call = self._active
        clean = self._retire(call)
        # Transport cleanup cannot overrule a provider's explicit cleanup failure.
        clean = clean and not (type(value) is Failure and value.code == 'cleanup')
        self._unclean = not clean
        interrupted = self._interruption(call)
        if interrupted:
            value = self._failure(call, interrupted)
        preceding = () if call.primary is None else (call.primary,)
        if not clean:
            self._fault = 'cleanup'
            failure = (value,) if type(value) is Failure else ()
            self._terminal = Failed(preceding + failure + (self._failure(call, 'cleanup'),))
        elif type(value) is Failure:
            # [LAW:no-silent-failure] Degradation retains the primary's actual failure.
            if (type(call.route) is Host and self._local is not None and not interrupted
                    and value.code in ('unavailable', 'provider_failed', 'timeout')):
                call.primary, call.route = value, self._local
                self._begin()
                return
            self._terminal = Failed(preceding + (value,))
        else:
            success = Success(value, call.route.provider.provider_id, call.route.provider.model_version)
            self._terminal = success if call.primary is None else Degraded(success, call.primary)
        self._active = None

    def poll(self) -> Success | Degraded | Failed | None:
        with self._lock:
            if self._inside_callback or self._configuring:
                return None
            if self._active is not None:
                call = self._active
                interrupted = self._interruption(call)
                if interrupted:
                    self._finish(self._failure(call, interrupted))
                else:
                    try:
                        incoming = self._invoke(call.job.poll)
                    except GatewayError as error:
                        self._finish(self._failure(call, error.code))
                    except Exception:
                        self._finish(self._failure(call, 'provider_failed'))
                    else:
                        interrupted = self._interruption(call)
                        if interrupted:
                            self._finish(self._failure(call, interrupted))
                        elif incoming is not None:
                            self._receive(call, incoming)
            result, self._terminal = self._terminal, None
            return result

    def _receive(self, call, incoming):
        try:
            if type(call.route) is Host:
                if type(incoming) is not HttpReply or type(incoming.status) is not int:
                    raise GatewayError('invalid_response')
                if type(incoming.peer_identity) is not str or incoming.peer_identity != call.route.endpoint.peer_identity:
                    raise GatewayError('identity')
                if incoming.status in (401, 403):
                    raise GatewayError('authentication')
                if incoming.status in (502, 503, 504):
                    raise GatewayError('timeout' if incoming.status == 504 else 'unavailable')
                if incoming.status != 200:
                    raise GatewayError('invalid_response')
                raw = incoming.body
            else:
                raw = incoming
            reply = parse_response(raw, call.request)
            value = self._failure(call, reply.code) if type(reply) is RemoteError else reply
        except GatewayError as error:
            value = self._failure(call, error.code)
        self._finish(value)

    def cancel(self):
        with self._lock:
            if self._active is None:
                return
            self._active.cancel_requested = True
            # [LAW:no-ambient-temporal-coupling] Re-entry cannot discard an unreturned job.
            if not self._inside_callback:
                self._finish(self._failure(self._active, 'canceled'))
