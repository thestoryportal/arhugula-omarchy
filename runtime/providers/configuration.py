"""One trusted, memory-only provider configuration owner; no provider effects.

Only trusted local configuration code may stage observations or issue approvals.
Python object identity is an in-process capability, not a process security sandbox.
"""
from dataclasses import dataclass, replace
import re

from runtime.contracts import Provider
from runtime.evaluation import ReplayRun, promotion
from runtime.gateway.client import GatewayClient, Host, Local
from .records import ConfigurationError, Manifest, Policy, check_budgets


@dataclass(frozen=True)
class Evidence:
    manifest_digest: str
    bundle_digest: str
    run: ReplayRun
    evaluators: tuple[str, ...]

    def __post_init__(self):
        if any(type(d) is not str or re.fullmatch('[0-9a-f]{64}', d) is None
               for d in (self.manifest_digest, self.bundle_digest)):
            raise ConfigurationError('evidence-digest')
        if (type(self.run) is not ReplayRun or type(self.evaluators) is not tuple
                or not self.evaluators or any(type(e) is not str or not e for e in self.evaluators)
                or len(set(self.evaluators)) != len(self.evaluators)):
            raise ConfigurationError('evidence-evaluators')
        r = self.run
        object.__setattr__(self, 'run', ReplayRun(
            r.version, r.source, r.bundle_id, r.pinned, r.deterministic,
            r.independently_evaluated, dict(r.outcomes), r.evaluator_consensus))


@dataclass(frozen=True, eq=False)
class Candidate:
    baseline: int
    manifests: tuple[Manifest, ...]
    host: Host
    local: Local | None
    policy: Policy
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class Active:
    revision: int
    candidate: Candidate


@dataclass(frozen=True)
class Disabled:
    revision: int
    previous: Candidate | None


@dataclass(frozen=True)
class _Approval:
    candidate: Candidate
    bootstrap: bool


@dataclass(frozen=True)
class _Health:
    status: str
    observed_at_ms: int


class Configuration:
    """Trusted local API; all state shares the gateway's public transaction.

    An instance is its own epoch. No object from a former instance is accepted.
    One instance retains at most 256 candidates, receipts and active revisions each;
    exhaustion fails closed. No network, disk, model or audio API exists here.
    """

    def __init__(self, gateway: GatewayClient):
        if type(gateway) is not GatewayClient:
            raise ConfigurationError('gateway')
        self._gateway = gateway
        self._state = Disabled(0, None)
        self._staged = set()
        self._approvals = {}
        self._history = {}
        self._health = {}
        self._last_time = 0
        self._clock_fault = False
        self._token = gateway.claim_configuration()

    @property
    def state(self):
        with self._gateway.configuration(self._token):
            return self._state

    def stage(self, manifest, host, *, policy, evidence, local_manifest=None, local=None):
        with self._gateway.configuration(self._token):
            return self._stage(manifest, host, policy, evidence, local_manifest, local)

    def _stage(self, manifest, host, policy, evidence, local_manifest, local):
        if type(policy) is not Policy:
            raise ConfigurationError('policy-required')
        manifests = (manifest,) if local_manifest is None else (manifest, local_manifest)
        routes = (host,) if local is None else (host, local)
        if (type(host) is not Host or (local is not None and type(local) is not Local)
                or len(manifests) != len(routes)
                or any(type(m) is not Manifest for m in manifests)):
            raise ConfigurationError('routes')
        if local is not None and not policy.allow_fallback:
            raise ConfigurationError('fallback-policy')
        for m, route, placement in zip(manifests, routes, ('host', 'vm')):
            if (m.provider.placement != placement
                    or replace(route.provider, enabled=False, health='unavailable') != m.provider):
                raise ConfigurationError('route-binding')
        if len({m.provider.provider_id for m in manifests}) != len(manifests):
            raise ConfigurationError('duplicate-provider')
        if (type(evidence) is not tuple or len(evidence) != len(manifests)
                or any(type(e) is not Evidence for e in evidence)):
            raise ConfigurationError('evidence')
        for manifest, item in zip(manifests, evidence):
            if item.manifest_digest != manifest.digest or item.run.version != manifest.provider.model_version:
                raise ConfigurationError('evidence-binding')
        if len(self._staged) >= 256:
            raise ConfigurationError('candidate-capacity')
        candidate = Candidate(self._state.revision, manifests, host, local, policy, evidence)
        self._staged.add(candidate)
        return candidate

    def _owned(self, candidate):
        if type(candidate) is not Candidate or candidate not in self._staged:
            raise ConfigurationError('candidate-owner')

    def observe(self, candidate, provider_id, *, status, observed_at_ms):
        with self._gateway.configuration(self._token):
            self._owned(candidate)
            matches = [m for m in candidate.manifests if m.provider.provider_id == provider_id]
            if (type(provider_id) is not str or not matches
                    or type(status) is not str or status not in ('healthy', 'degraded', 'unavailable')
                    or type(observed_at_ms) is not int or observed_at_ms < 0):
                raise ConfigurationError('health-observation')
            key = matches[0].digest
            preceding = self._health.get(key)
            if preceding is not None and observed_at_ms < preceding.observed_at_ms:
                raise ConfigurationError('health-regression')
            self._health[key] = _Health(status, observed_at_ms)

    def _approve(self, candidate, bootstrap):
        with self._gateway.configuration(self._token):
            self._owned(candidate)
            if bootstrap != (len(candidate.evidence) > len(self._baseline())):
                raise ConfigurationError('bootstrap-approval-required')
            if candidate.baseline != self._state.revision:
                raise ConfigurationError('stale-revision')
            if len(self._approvals) >= 256:
                raise ConfigurationError('approval-capacity')
            receipt = object()
            self._approvals[receipt] = _Approval(candidate, bootstrap)
            return receipt

    def approve_bootstrap(self, candidate):
        """Approve exact evaluation for new roles, comparing retained roles too."""
        return self._approve(candidate, True)

    def approve(self, candidate):
        """Explicit local approval of a change; comparison alone is not authority."""
        return self._approve(candidate, False)

    def reject(self, candidate):
        with self._gateway.configuration(self._token):
            self._owned(candidate)
            if candidate.baseline != self._state.revision:
                raise ConfigurationError('stale-revision')
            self._staged.remove(candidate)
            self._approvals = {r: a for r, a in self._approvals.items() if a.candidate is not candidate}

    def _time(self, now_ms):
        if type(now_ms) is not int or now_ms < self._last_time:
            self._clock_fault = True
        if self._clock_fault:
            raise ConfigurationError('clock')
        self._last_time = now_ms

    def _healthy(self, manifest, policy, now_ms):
        observation = self._health.get(manifest.digest)
        if (observation is None or not 0 <= now_ms - observation.observed_at_ms <= policy.health_ttl_ms
                or observation.status == 'unavailable'
                or (observation.status == 'degraded' and not policy.allow_degraded)):
            raise ConfigurationError('health-ineligible')
        return observation.status

    def _baseline(self):
        previous = (self._state.candidate if type(self._state) is Active else self._state.previous)
        return () if previous is None else previous.evidence

    def _evaluation(self, candidate, bootstrap):
        baselines = self._baseline()
        for index, proposed in enumerate(candidate.evidence):
            if index >= len(baselines):
                r = proposed.run
                if not (r.pinned and r.deterministic and r.independently_evaluated
                        and r.evaluator_consensus and all(v == 'pass' for v in r.outcomes.values())
                        and bootstrap):
                    raise ConfigurationError('bootstrap-evaluation')
                continue
            baseline = baselines[index]
            if baseline.bundle_digest != proposed.bundle_digest:
                raise ConfigurationError('evaluation-bundle-mismatch')
            # [LAW:single-enforcer] This helper compares; the receipt authorizes.
            result = promotion(baseline.run, proposed.run, labels=('approved',), rollback_ready=True)
            if result['decision'] != 'promote':
                raise ConfigurationError('evaluation-hold')

    def activate(self, candidate, receipt, *, now_ms):
        with self._gateway.configuration(self._token):
            self._owned(candidate)
            if candidate.baseline != self._state.revision:
                raise ConfigurationError('stale-revision')
            approval = self._approvals.get(receipt) if type(receipt) is object else None
            if approval is None or approval.candidate is not candidate:
                raise ConfigurationError('approval-required')
            self._evaluation(candidate, approval.bootstrap)
            self._time(now_ms)
            health = tuple(self._healthy(m, candidate.policy, now_ms) for m in candidate.manifests)
            check_budgets(candidate.manifests, candidate.policy)
            if len(self._history) >= 256:
                raise ConfigurationError('revision-capacity')
            routes = (candidate.host,) if candidate.local is None else (candidate.host, candidate.local)
            rebound = tuple(replace(route, provider=replace(m.provider, enabled=True, health=status))
                            for route, m, status in zip(routes, candidate.manifests, health))
            next_state = Active(self._state.revision + 1, candidate)
            # [LAW:no-ambient-temporal-coupling] No callback can interleave rebind
            # and publication inside the gateway-owned configuration transaction.
            self._gateway.reconfigure(rebound[0], rebound[1] if len(rebound) == 2 else None,
                                      permit=self._permit, owner=self._token)
            self._state = next_state
            self._history[next_state.revision] = candidate
            del self._approvals[receipt]
            return next_state

    def _permit(self, provider: Provider, service, now_ms):
        """Runs under the gateway lock/callback barrier, with no second lifecycle."""
        try:
            self._time(now_ms)
            if type(self._state) is not Active:
                return False
            candidate = self._state.candidate
            matches = [m for m in candidate.manifests if
                       (m.provider.provider_id, m.provider.model_version) ==
                       (provider.provider_id, provider.model_version)]
            if not matches or service not in matches[0].provider.capabilities:
                return False
            self._healthy(matches[0], candidate.policy, now_ms)
            check_budgets(candidate.manifests, candidate.policy)
            return True
        except ConfigurationError:
            return False

    def disable(self):
        with self._gateway.configuration(self._token):
            previous = self._state.candidate if type(self._state) is Active else self._state.previous
            self._state = Disabled(self._state.revision + 1, previous)
            self._gateway.disable(owner=self._token)
            return self._state

    def restore(self, revision, *, evidence):
        """Previously approved content becomes a fresh candidate, never active."""
        with self._gateway.configuration(self._token):
            if type(revision) is not int or revision not in self._history:
                raise ConfigurationError('restore-revision')
            previous = self._history[revision]
            return self._stage(previous.manifests[0], previous.host, previous.policy, evidence,
                               previous.manifests[1] if len(previous.manifests) == 2 else None,
                               previous.local)
