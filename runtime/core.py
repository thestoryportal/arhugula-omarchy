"""VM-owned synchronous dispatch; no concrete action or transport is installed."""
from dataclasses import dataclass, field
import time
from collections.abc import Mapping
from uuid import uuid4

from .contracts import (Capability, Command, ContractError, Error, Event, Policy,
                        Profile, Result, decode, encode)


@dataclass(frozen=True)
class Outcome:
    status: str
    output: Mapping = field(default_factory=dict)
    error: Error | None = None


def _snapshot(value, expected):
    result = decode(encode(value))
    if not isinstance(result, expected):
        raise ContractError(f"expected {expected.__name__}")
    return result


class ControlPlane:
    """A trusted VM owner binds policy/profile/catalog and an injected executor.

    Journal adapters provide a shared dispatch_lock and exclusive persistent
    ownership. Commands are never retried automatically, including after restart.
    Use a new command ID only after explicitly reconciling the previous outcome.
    Cancellation here is pre-dispatch; mid-action cancellation is an executor's
    responsibility and cannot undo already completed effects.
    """

    def __init__(self, catalog, policy, executor, journal, *, profile,
                 clock=None, identifiers=None):
        entries = [_snapshot(item, Capability) for item in catalog]
        self._catalog = {item.capability_id: item for item in entries}
        if len(entries) != len(self._catalog):
            raise ValueError("duplicate capability IDs")
        self._policy = _snapshot(policy, Policy)
        self._profile = _snapshot(profile, Profile)
        self._executor = executor
        self._journal = journal
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._identifiers = identifiers or (lambda: str(uuid4()))
        self._seen = set()

    def _error(self, code, message):
        return Error(1, code, message, False)

    def _result(self, command, status, output=None, error=None):
        return _snapshot(Result(1, self._identifiers(), command.command_id,
                                command.correlation_id, status, {} if output is None else output, error), Result)

    def _event(self, command, result, start):
        now = self._clock()
        return _snapshot(Event(
            1, self._identifiers(), command.command_id, command.correlation_id,
            "command.finished" if result else "command.started", now,
            result.status if result else "pending", command.capability_id,
            command.catalog_version, self._policy.revision, max(0, now - start),
            command.context,
            {"result_id": result.result_id, "error_code": result.error.code if result.error else None}
            if result else {}), Event)

    def _denial(self, command):
        profile, policy = self._profile, self._policy
        if not profile.enabled or profile.policy_id != policy.policy_id or command.context["profile_id"] != profile.profile_id:
            return "profile.denied"
        if command.context["source"] == "voice" and not profile.voice_enabled:
            return "voice.disabled"
        if not policy.enabled or command.capability_id not in policy.allowed_capabilities:
            return "policy.denied"
        capability = self._catalog.get(command.capability_id)
        if capability is None or not capability.enabled:
            return "capability.unavailable"
        if capability.catalog_version != command.catalog_version:
            return "catalog.stale"
        if capability.risk == "blocked":
            return "risk.blocked"
        if capability.risk == "confirm" or command.capability_id in policy.confirmation_required:
            return "confirmation.required"
        if command.arguments.keys() != capability.arguments.keys():
            return "arguments.invalid"
        primitive_types = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}
        for name, kind in capability.arguments.items():
            if type(command.arguments[name]) not in primitive_types[kind]:
                return "arguments.invalid"
        return None

    def dispatch(self, command, *, canceled=False):
        command = _snapshot(command, Command)
        if type(canceled) is not bool:
            raise ContractError("canceled must be boolean")
        with self._journal.dispatch_lock:
            return self._dispatch(command, canceled)

    def _dispatch(self, command, canceled):
        # Read failures fail closed, before any executor invocation. Re-read while
        # holding the journal's shared lock to cover multiple dispatcher objects.
        try:
            self._seen.update(event.command_id for _, event in self._journal.read())
        except Exception:
            return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot read execution history"))
        start = self._clock()
        duplicate = command.command_id in self._seen
        self._seen.add(command.command_id)
        denial = "command.duplicate" if duplicate else self._denial(command)
        if canceled and not duplicate:
            result = self._result(command, "canceled")
        elif denial:
            result = self._result(command, "blocked", error=self._error(denial, "VM policy did not authorize execution"))
        else:
            try:
                self._journal.append(self._event(command, None, start))
            except Exception:
                return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot persist execution intent"))
            try:
                outcome = self._executor(command)
                if not isinstance(outcome, Outcome) or outcome.status not in ("success", "failed", "canceled", "uncertain"):
                    raise ContractError("invalid executor outcome")
                result = self._result(command, outcome.status, outcome.output, outcome.error)
            except Exception:
                result = self._result(command, "uncertain", error=self._error("executor.uncertain", "Executor did not produce a valid outcome; reconcile before retry"))
        try:
            self._journal.append(self._event(command, result, start))
        except Exception:
            # Do not claim success if completion evidence could not be persisted.
            status = "uncertain" if not denial and not canceled else result.status
            return self._result(command, status, error=self._error("journal.unavailable", "Cannot persist completion; reconcile before retry"))
        return result
