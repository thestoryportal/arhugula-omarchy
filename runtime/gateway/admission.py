"""Owned memory-only authentication and replay admission; no model execution."""
from dataclasses import dataclass, field
import hmac
import re
from threading import RLock

from runtime.contracts import Provider, decode, encode
from .wire import GatewayError, LIMITS, Request, catalog_revision, parse_request


@dataclass(frozen=True)
class Bearer:
    value: str = field(repr=False)

    def __post_init__(self):
        if type(self.value) is not str or re.fullmatch(r'[A-Za-z0-9._~-]{32,256}', self.value) is None:
            raise GatewayError('authentication')

    def header(self):
        return 'Bearer ' + self.value


class ReplayHistory:
    """One admission owner's lifetime IDs, with no replay-enabling eviction."""

    def __init__(self):
        self._ids = set()
        self._lock = RLock()

    def claim(self, request_id):
        with self._lock:
            if request_id in self._ids:
                raise GatewayError('replay')
            if len(self._ids) >= LIMITS['history']:
                raise GatewayError('exhausted')
            self._ids.add(request_id)


def provider_snapshot(provider, placement):
    try:
        if type(provider) is not Provider:
            raise ValueError
        snapshot = decode(encode(provider))
        if snapshot.placement != placement:
            raise ValueError
        return snapshot
    except (ValueError, TypeError):
        raise GatewayError('identity') from None


def check_provider(request, provider, catalog_version):
    if request.catalog_version != catalog_version:
        raise GatewayError('stale_catalog')
    if (request.provider_id, request.model_version) != (provider.provider_id, provider.model_version):
        raise GatewayError('identity')
    if request.service not in provider.capabilities:
        raise GatewayError('invalid_request')
    if not provider.enabled or provider.health == 'unavailable':
        raise GatewayError('unavailable')


@dataclass(frozen=True)
class Admitted:
    request: Request = field(repr=False)


class Admission:
    def __init__(self, provider: Provider, catalog_version: int, bearer: Bearer):
        self._provider = provider_snapshot(provider, 'host')
        if type(bearer) is not Bearer:
            raise GatewayError('authentication')
        self._catalog_version = catalog_revision(catalog_version)
        self._bearer = bearer
        self._history = ReplayHistory()

    def admit(self, authorization: str, raw: bytes) -> Admitted:
        # [LAW:single-enforcer] Authentication precedes parse/provider/replay admission.
        try:
            supplied = (authorization.encode('ascii')
                        if type(authorization) is str and len(authorization) <= 263 else b'')
            accepted = hmac.compare_digest(supplied, self._bearer.header().encode())
        except UnicodeError:
            accepted = False
        if not accepted:
            raise GatewayError('authentication')
        request = parse_request(raw)
        check_provider(request, self._provider, self._catalog_version)
        self._history.claim(request.request_id)
        return Admitted(request)
