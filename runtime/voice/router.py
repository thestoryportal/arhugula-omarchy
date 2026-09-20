"""Data-only speech candidates; the VM control plane retains all authority."""
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import math
import re
import threading
import time
from types import MappingProxyType
import unicodedata
from uuid import uuid4

from ..contracts import Result, decode
from ..core import ConfirmationError


def normalize(text):
    if type(text) is not str:
        raise ValueError("transcript must be text")
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


@dataclass(frozen=True)
class Action:
    capability_id: str
    catalog_version: int
    arguments: Mapping
    aliases: tuple[str, ...]
    label: str

    def __post_init__(self):
        if not self.aliases or any(type(alias) is not str or not normalize(alias) for alias in self.aliases):
            raise ValueError("action aliases must be nonempty text")
        if type(self.label) is not str or not self.label:
            raise ValueError("action label must be nonempty text")
        if not isinstance(self.arguments, Mapping) or any(type(key) is not str or type(value) not in (str, int, float, bool) or (type(value) is float and not math.isfinite(value)) for key, value in self.arguments.items()):
            raise ValueError("action arguments must be finite primitives")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True)
class VoiceState:
    context: Mapping
    key: str
    activation_id: str
    muted: bool = False
    mode: str = "command"


@dataclass(frozen=True)
class VoiceReply:
    status: str
    code: str
    token: str | None = None
    prompt: str | None = None
    result: Result | None = None


class VoiceRouter:
    def __init__(self, plane, actions, state, speak, *, proposal=None, identifiers=None,
                 correlation_ids=None):
        self.plane = plane
        self.actions = {action.capability_id: action for action in actions}
        if not self.actions or len(self.actions) != len(actions):
            raise ValueError("actions must have unique capability IDs")
        self.state, self.speak, self.proposal = state, speak, proposal
        self._identifiers = identifiers or (lambda: str(uuid4()))
        self.correlation_ids = correlation_ids or (lambda: str(uuid4()))
        self._activations, self._previews = set(), {}
        self._busy = False
        self._lock = threading.RLock()

    def _state(self):
        try:
            value = self.state()
        except Exception as exc:
            raise ValueError("trusted voice state is unavailable") from exc
        if not isinstance(value, VoiceState) or type(value.key) is not str or not value.key or type(value.activation_id) is not str or not value.activation_id or type(value.muted) is not bool:
            raise ValueError("invalid trusted voice state")
        return VoiceState(MappingProxyType(dict(value.context)), value.key, value.activation_id, value.muted, value.mode)

    def _binding(self, state):
        return json.dumps({"key": state.key, "context": dict(state.context)}, sort_keys=True, allow_nan=False)

    def _available(self, state):
        if state.muted:
            return "voice.muted"
        if state.mode != "command":
            return "voice.wrong-mode"
        return None

    def _current(self, state):
        try:
            current = self._state()
            return current == state and self._available(current) is None
        except (ValueError, TypeError):
            return False

    def _activate(self, state):
        if state.activation_id in self._activations:
            return "activation.reused"
        if len(self._activations) >= 4096:
            return "session.exhausted"
        self._activations.add(state.activation_id)
        return None

    def _command(self, action, state, version=None):
        return decode({"kind": "command", "version": 1,
                       "command_id": self._identifiers(), "correlation_id": self.correlation_ids(),
                       "capability_id": action.capability_id,
                       "catalog_version": action.catalog_version if version is None else version,
                       "requested_at_ms": int(time.time() * 1000),
                       "arguments": dict(action.arguments),
                       "context": {**state.context, "source": "voice"}})

    def _candidates(self, text):
        normalized = normalize(text)
        exact = [(action, 1.0, action.catalog_version) for action in self.actions.values()
                 if normalized in {normalize(alias) for alias in action.aliases}]
        if exact:
            return exact
        if self.proposal is not None:
            try:
                values = self.proposal(text, tuple(self.actions))
                if type(values) is not list or len(values) > 32:
                    raise ValueError("invalid candidate list")
                candidates, seen = [], set()
                for item in values:
                    if type(item) is not dict or set(item) != {"capability_id", "catalog_version", "confidence"}:
                        raise ValueError("invalid proposal shape")
                    identifier, version, score = item["capability_id"], item["catalog_version"], item["confidence"]
                    if type(identifier) is not str or identifier not in self.actions or identifier in seen or type(version) is not int or version < 1 or type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                        raise ValueError("invalid proposal data")
                    seen.add(identifier)
                    candidates.append((self.actions[identifier], score, version))
                return sorted(candidates, key=lambda value: (-value[1], value[0].capability_id))
            except Exception:
                return []
        candidates = [(action, max(SequenceMatcher(None, normalized, normalize(alias)).ratio() for alias in action.aliases), action.catalog_version)
                      for action in self.actions.values()]
        return sorted(candidates, key=lambda value: (-value[1], value[0].capability_id))

    def _speak(self, prompt, state):
        # Last check after any potentially blocking journal work. The trusted
        # owner must serialize state changes with the actual speech adapter.
        if not self._current(state):
            return VoiceReply("blocked", "context.stale")
        try:
            self.speak(prompt)
        except Exception:
            return VoiceReply("failed", "speech.unavailable")
        return None

    def _prompt(self, command, phase, prompt, details, state):
        try:
            self.plane.observe_interaction(command, phase, details)
        except Exception:
            return VoiceReply("blocked", "journal.unavailable")
        return self._speak(prompt, state)

    def handle(self, transcript, *, corrected=False):
        with self._lock:
            if self._busy:
                return VoiceReply("blocked", "voice.busy")
            self._busy = True
            try:
                return self._handle(transcript, corrected)
            except (ValueError, TypeError):
                return VoiceReply("blocked", "voice.invalid")
            finally:
                self._busy = False

    def _handle(self, transcript, corrected):
        state = self._state()
        denial = self._available(state) or self._activate(state)
        if denial:
            return VoiceReply("blocked", denial)
        if type(corrected) is not bool:
            return VoiceReply("blocked", "voice.invalid")
        candidates = self._candidates(transcript)
        current = self._state()
        if current != state or self._available(current):
            return VoiceReply("blocked", "context.stale")
        ambiguous = len(candidates) > 1 and candidates[0][1] - candidates[1][1] < 0.15
        action = candidates[0][0] if candidates else next(iter(self.actions.values()))
        command = self._command(action, state, candidates[0][2] if candidates else None)
        if not candidates or candidates[0][1] < 0.85 or ambiguous:
            prompt = "Please start a new command turn and name the action: " + ", ".join(item.label for item in list(self.actions.values())[:3])
            failure = self._prompt(command, "voice.clarification", prompt, {"reason": "ambiguous-or-unknown"}, state)
            return failure or VoiceReply("clarify", "clarification.required", prompt=prompt)
        denial = self.plane.assess(command)
        inferred = normalize(transcript) not in {normalize(alias) for alias in action.aliases}
        if denial == "confirmation.required" or ((corrected or inferred) and denial is None):
            if len(self._previews) >= 128:
                return VoiceReply("blocked", "confirmation.limit")
            try:
                preview = self.plane.request_confirmation(command, self._binding(state))
            except ConfirmationError:
                return VoiceReply("blocked", "confirmation.unavailable")
            prompt = ("Correction preview: " if corrected else "Candidate preview: " if inferred else "Confirm: ") + action.label + "?"
            failure = self._speak(prompt, state)
            if failure:
                self.plane.confirm(preview.token, "panel", self._binding(state), approved=False)
                return failure
            self._previews[preview.token] = (preview, self._binding(state))
            return VoiceReply("preview", "confirmation.required", token=preview.token, prompt=prompt)
        result = self.plane.dispatch(command, guard=lambda: self._current(state))
        return VoiceReply(result.status, result.error.code if result.error else "command.success", result=result)

    def confirm(self, token, channel, answer):
        with self._lock:
            if self._busy:
                return VoiceReply("blocked", "voice.busy")
            self._busy = True
            try:
                state = self._state()
                denial = self._available(state)
                if denial:
                    return VoiceReply("blocked", denial)
                if type(token) is not str or token not in self._previews:
                    return VoiceReply("blocked", "confirmation.unknown")
                preview, original_binding = self._previews[token]
                if self._binding(state) != original_binding:
                    self._previews.pop(token)
                    result = self.plane.confirm(token, channel, self._binding(state), approved=False)
                    return VoiceReply(result.status, result.error.code if result.error else "context.stale", result=result)
                if channel == "voice":
                    denial = self._activate(state)
                    if denial:
                        return VoiceReply("blocked", denial)
                    normalized = normalize(answer)
                    if normalized not in ("yes", "confirm", "no", "cancel"):
                        prompt = "Start a new command turn and say yes or no."
                        failure = self._prompt(preview.command, "voice.clarification", prompt, {"reason": "confirmation-answer"}, state)
                        return failure or VoiceReply("clarify", "confirmation.answer", token=token, prompt=prompt)
                    approved = normalized in ("yes", "confirm")
                elif channel in ("panel", "keyboard") and type(answer) is bool:
                    approved = answer
                else:
                    return VoiceReply("blocked", "confirmation.invalid")
                self._previews.pop(token)
                result = self.plane.confirm(token, channel, self._binding(state), approved=approved,
                                            guard=lambda: self._current(state))
                return VoiceReply(result.status, result.error.code if result.error else "command." + result.status, result=result)
            except (ValueError, TypeError):
                return VoiceReply("blocked", "confirmation.invalid")
            finally:
                self._busy = False
