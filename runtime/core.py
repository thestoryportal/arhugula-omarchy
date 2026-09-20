"""VM-owned synchronous dispatch; no concrete action or transport is installed."""
from dataclasses import dataclass, field
from contextlib import contextmanager
from itertools import islice
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


def _guard_denial(guard):
    """Trusted adapter callback only; missing/nontrue state fails closed."""
    if guard is None:
        return None
    try:
        if guard() is True:
            return None
    except Exception:
        pass
    return "context.stale"


def _catalog_snapshot(catalog):
    try:
        entries = [_snapshot(item, Capability) for item in islice(catalog, 257)]
    except TypeError as error:
        raise ValueError("catalog.invalid") from error
    if len(entries) > 256:
        raise ValueError("catalog.oversize")
    result = {item.capability_id: item for item in entries}
    if len(result) != len(entries):
        raise ValueError("duplicate capability IDs")
    versions = {item.catalog_version for item in entries}
    if len(versions) > 1:
        raise ValueError("catalog.mixed-revisions")
    return result, next(iter(versions), None)


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
        self._catalog, revision = _catalog_snapshot(catalog)
        self._catalog_version = revision if revision is not None else 1
        self._catalog_users = 0
        self._policy = _snapshot(policy, Policy)
        self._profile = _snapshot(profile, Profile)
        self._executor = executor
        self._journal = journal
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._identifiers = identifiers or (lambda: str(uuid4()))
        self._seen = set()
        self._confirmations = {}

    @property
    def catalog_version(self):
        with self._journal.dispatch_lock:
            return self._catalog_version

    @contextmanager
    def _catalog_use(self):
        # RLock also admits same-thread callbacks. Track active authorization
        # lifetimes so reentrant refresh cannot change the checked catalog.
        with self._journal.dispatch_lock:
            self._catalog_users += 1
            try:
                yield
            finally:
                self._catalog_users -= 1

    def replace_catalog(self, catalog, *, expected_version, new_version):
        """Trusted VM-only CAS; never expose as a model/remote mutation tool.

        Replaces this owner's complete typed catalog and invalidates its previews.
        Does not change policy, clear command history, cancel started actions or
        synchronize other ControlPlane instances. Callers own cross-owner cutover.
        """
        if (type(expected_version) is not int or expected_version < 1
                or type(new_version) is not int or new_version < 1):
            raise ValueError("catalog.version")
        replacement, revision = _catalog_snapshot(catalog)
        if revision is not None and revision != new_version:
            raise ValueError("catalog.version")
        with self._journal.dispatch_lock:
            if self._catalog_users:
                raise ValueError("catalog.in-use")
            if expected_version != self._catalog_version or new_version <= self._catalog_version:
                raise ValueError("catalog.stale")
            self._catalog = replacement
            self._catalog_version = new_version
            self._confirmations.clear()
            return new_version

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
        with self._catalog_use():
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

    def confirm(self, token, channel, context_key, *, approved=True, guard=None):
        with self._catalog_use():
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
            if denial := _guard_denial(guard):
                return self._confirmation_blocked(command, denial)
            try:
                self.observe_interaction(command, "voice.confirmation", {"channel": channel, "approved": approved})
            except Exception:
                return self._confirmation_blocked(command, "journal.unavailable")
            return self._dispatch(command, canceled=not approved, confirmed=approved, guard=guard)

    def dispatch(self, command, *, canceled=False, guard=None):
        """Guard is trusted state validation, rechecked after intent persistence.

        The adapter must own state transitions through final actuation; this
        callback cannot make an external platform operation atomic by itself.
        """
        command = _snapshot(command, Command)
        if type(canceled) is not bool:
            raise ContractError("canceled must be boolean")
        with self._catalog_use():
            return self._dispatch(command, canceled, guard=guard)

    def _dispatch(self, command, canceled, confirmed=False, guard=None):
        # Read failures fail closed, before any executor invocation. Re-read while
        # holding the journal's shared lock to cover multiple dispatcher objects.
        try:
            history = self._journal.read()
            self._seen.update(event.command_id for _, event in history if isinstance(event, Event))
            # Preview observations impose a durable restriction, never approval
            # or an execution receipt. A lost token cannot lift this restriction.
            pending = any(isinstance(event, Interaction) and event.phase == "voice.preview"
                          and event.interaction_id == command.command_id for _, event in history)
        except Exception:
            return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot read execution history"))
        start = self._clock()
        duplicate = command.command_id in self._seen
        self._seen.add(command.command_id)
        denial = ("command.duplicate" if duplicate else
                  "confirmation.required" if pending and not confirmed else
                  _guard_denial(guard) or self._denial(command, confirmed))
        if canceled and not duplicate:
            result = self._result(command, "canceled")
        elif denial:
            result = self._result(command, "blocked", error=self._error(denial, "VM policy did not authorize execution"))
        else:
            try:
                self._journal.append(self._event(command, None, start))
            except Exception:
                return self._result(command, "blocked", error=self._error("journal.unavailable", "Cannot persist execution intent"))
            denial = _guard_denial(guard)
            if denial:
                result = self._result(command, "blocked", error=self._error(denial, "Current state no longer authorizes execution"))
            else:
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
