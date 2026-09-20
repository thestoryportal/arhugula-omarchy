"""VM-owned synchronous dispatch; no concrete action or transport is installed."""
from dataclasses import dataclass, field
import time
from collections.abc import Mapping
from uuid import uuid4

from .contracts import (Capability, Command, ContractError, Error, Event, Interaction, Policy,
                        Profile, Result, decode, encode)


@dataclass(frozen=True)
class Outcome:
    status: str
    output: Mapping = field(default_factory=dict)
    error: Error | None = None


class ConfirmationError(ValueError):
    """Unknown token or unavailable preview; no authorization was granted."""


@dataclass(frozen=True)
class Confirmation:
    token: str
    command: Command
    expires_at_ms: int


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
        self._confirmations = {}

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

    def _denial(self, command, confirmed=False):
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
        if not confirmed and (capability.risk == "confirm" or command.capability_id in policy.confirmation_required):
            return "confirmation.required"
        if command.arguments.keys() != capability.arguments.keys():
            return "arguments.invalid"
        primitive_types = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}
        for name, kind in capability.arguments.items():
            if type(command.arguments[name]) not in primitive_types[kind]:
                return "arguments.invalid"
        return None

    def observe_interaction(self, command, phase, details):
        """Append a non-authoritative observation; never an execution receipt."""
        command = _snapshot(command, Command)
        with self._journal.dispatch_lock:
            event = _snapshot(Interaction(1, self._identifiers(), command.command_id,
                                         command.correlation_id, self._clock(),
                                         command.context, phase, details), Interaction)
            self._journal.append(event)

    def assess(self, command):
        """Advisory only: dispatch always rechecks this policy under ownership."""
        command = _snapshot(command, Command)
        with self._journal.dispatch_lock:
            return self._denial(command)

    def request_confirmation(self, command, context_key):
        """Trusted VM adapter only. Model tools must not expose this/confirm."""
        command = _snapshot(command, Command)
        if type(context_key) is not str or not context_key:
            raise ConfirmationError("invalid context key")
        with self._journal.dispatch_lock:
            if self._denial(command, confirmed=True):
                raise ConfirmationError("command is not eligible for confirmation")
            now = self._clock()
            self._confirmations = {key: value for key, value in self._confirmations.items() if value[0].expires_at_ms > now}
            if len(self._confirmations) >= 128:
                raise ConfirmationError("too many pending confirmations")
            preview = Confirmation(str(uuid4()), command, now + 30000)
            try:
                self.observe_interaction(command, "voice.preview", {"capability_id": command.capability_id})
            except Exception as exc:
                raise ConfirmationError("journal unavailable") from exc
            self._confirmations[preview.token] = (preview, context_key)
            return preview

    def _confirmation_blocked(self, command, code):
        self._seen.add(command.command_id)
        result = self._result(command, "blocked", error=self._error(code, "Confirmation was not valid"))
        try:
            self._journal.append(self._event(command, result, self._clock()))
        except Exception:
            return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot record confirmation rejection"))
        return result

    def confirm(self, token, channel, context_key, *, approved=True):
        with self._journal.dispatch_lock:
            if type(token) is not str or token not in self._confirmations:
                raise ConfirmationError("unknown or already consumed confirmation")
            preview, original_key = self._confirmations.pop(token)
            command = preview.command
            if channel not in ("panel", "keyboard", "voice") or type(approved) is not bool:
                return self._confirmation_blocked(command, "confirmation.invalid")
            if context_key != original_key:
                return self._confirmation_blocked(command, "context.stale")
            if self._clock() >= preview.expires_at_ms:
                return self._confirmation_blocked(command, "confirmation.expired")
            try:
                self.observe_interaction(command, "voice.confirmation", {"channel": channel, "approved": approved})
            except Exception:
                return self._confirmation_blocked(command, "journal.unavailable")
            return self._dispatch(command, canceled=not approved, confirmed=approved)

    def dispatch(self, command, *, canceled=False):
        command = _snapshot(command, Command)
        if type(canceled) is not bool:
            raise ContractError("canceled must be boolean")
        with self._journal.dispatch_lock:
            return self._dispatch(command, canceled)

    def _dispatch(self, command, canceled, confirmed=False):
        # Read failures fail closed, before any executor invocation. Re-read while
        # holding the journal's shared lock to cover multiple dispatcher objects.
        try:
            self._seen.update(event.command_id for _, event in self._journal.read() if isinstance(event, Event))
        except Exception:
            return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot read execution history"))
        start = self._clock()
        duplicate = command.command_id in self._seen
        self._seen.add(command.command_id)
        pending = any(item[0].command.command_id == command.command_id for item in self._confirmations.values())
        denial = ("command.duplicate" if duplicate else
                  "confirmation.required" if pending and not confirmed else self._denial(command, confirmed))
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
