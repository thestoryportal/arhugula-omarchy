"""Closed, bounded local conversation values; no command or wire authority."""
from dataclasses import dataclass, field
from enum import Enum

from runtime.contracts import Profile, decode, encode


class Entry(Enum):
    VOICE = 'voice'
    PANEL = 'panel'
    KEYBOARD = 'keyboard'


class ContextState(Enum):
    AVAILABLE = 'available'
    EMPTY = 'empty'
    CONFLICTING = 'conflicting'
    UNAVAILABLE = 'unavailable'


class Display(Enum):
    INACTIVE = 'inactive'
    READY = 'ready'
    PROCESSING = 'processing'
    CLARIFYING = 'clarifying'
    STOPPING = 'stopping'
    FAULTED = 'faulted'


class Code(Enum):
    INACTIVE = 'conversation.inactive'
    READY = 'conversation.ready'
    PROCESSING = 'conversation.processing'
    CONFLICT = 'conversation.conflict'
    CANCELED = 'conversation.canceled'
    ENDED = 'conversation.ended'
    HANDOFF = 'conversation.handoff'
    STALE = 'conversation.stale'
    LIMIT = 'conversation.limit'
    DENIED = 'conversation.denied'
    UNAVAILABLE = 'conversation.unavailable'
    INVALID_RESULT = 'conversation.invalid-result'
    CLEANUP = 'conversation.cleanup-unproven'
    BUSY = 'conversation.busy'


def _require(condition):
    if not condition:
        raise ValueError('conversation.invalid-record')


def _number(value, ceiling=2**63 - 1):
    _require(type(value) is int and 0 < value <= ceiling)


def text(value, ceiling=16384):
    """Parse one bounded text value without changing whole-utterance identity."""
    _require(type(value) is str and 0 < len(value) <= ceiling)
    _require(bool(value.strip()) and all(ord(c) >= 32 or c in '\n\t' for c in value))
    _require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value))
    return value


def _id(value):
    text(value, 128)
    _require(all(c.isascii() and (c.isalnum() or c in '-_.:') for c in value))


def _optional_id(value):
    if value is not None:
        _id(value)


def _tuple(value, kind, ceiling):
    _require(type(value) is tuple and len(value) <= ceiling)
    _require(all(type(item) is kind for item in value))


@dataclass(frozen=True)
class Limits:
    turns: int
    text_chars: int
    context_chars: int
    context_items: int
    polls: int

    def __post_init__(self):
        for value, ceiling in ((self.turns, 64), (self.text_chars, 16384),
                               (self.context_chars, 65536), (self.context_items, 64),
                               (self.polls, 1024)):
            _number(value, ceiling)


@dataclass(frozen=True)
class SetupEvidence:
    revision: int
    occupied: frozenset[str]
    reserved: frozenset[str]

    def __post_init__(self):
        _number(self.revision)
        for keys in (self.occupied, self.reserved):
            _require(type(keys) is frozenset and len(keys) <= 256)
            for key in keys:
                text(key, 128)


@dataclass(frozen=True)
class ConversationPolicy:
    profile_id: str
    policy_id: str
    revision: int
    entries: frozenset[Entry]
    exit_phrase: str = field(repr=False)
    exit_key: str
    limits: Limits

    def __post_init__(self):
        _id(self.profile_id)
        _id(self.policy_id)
        _number(self.revision)
        _require(type(self.entries) is frozenset and bool(self.entries)
                 and all(type(entry) is Entry for entry in self.entries))
        _require(type(self.limits) is Limits)
        text(self.exit_phrase, self.limits.text_chars)
        text(self.exit_key, 128)


@dataclass(frozen=True)
class ContextItem:
    source: str
    text: str = field(repr=False)

    def __post_init__(self):
        _id(self.source)
        text(self.text)


@dataclass(frozen=True)
class Context:
    revision: int
    state: ContextState
    items: tuple[ContextItem, ...] = field(repr=False)
    conflict_id: str | None = None

    def __post_init__(self):
        _number(self.revision)
        _require(type(self.state) is ContextState)
        _tuple(self.items, ContextItem, 64)
        _require(sum(len(item.text) for item in self.items) <= 65536)
        _optional_id(self.conflict_id)
        # [LAW:types-are-the-program] Empty, unavailable and conflict stay distinct.
        if self.state is ContextState.CONFLICTING:
            _require(len(self.items) >= 2 and self.conflict_id is not None)
        else:
            _require(self.conflict_id is None)
            _require(bool(self.items) == (self.state is ContextState.AVAILABLE))


@dataclass(frozen=True)
class Snapshot:
    profile: Profile
    revision: int
    policy: ConversationPolicy | None
    setup: SetupEvidence
    context: Context

    def __post_init__(self):
        _require(type(self.profile) is Profile)
        # [LAW:single-enforcer] The shared codec owns Profile validity.
        object.__setattr__(self, 'profile', decode(encode(self.profile)))
        _id(self.profile.profile_id)
        _id(self.profile.policy_id)
        _number(self.revision)
        _require(self.policy is None or type(self.policy) is ConversationPolicy)
        _require(type(self.setup) is SetupEvidence and type(self.context) is Context)


@dataclass(frozen=True)
class TurnToken:
    session_id: str
    turn: int
    generation: int
    profile_id: str
    profile_revision: int
    policy_revision: int
    context_revision: int

    def __post_init__(self):
        _id(self.session_id)
        _id(self.profile_id)
        for value in (self.turn, self.generation, self.profile_revision,
                      self.policy_revision, self.context_revision):
            _number(value)


@dataclass(frozen=True)
class Response:
    token: TurnToken
    text: str = field(repr=False)

    def __post_init__(self):
        _require(type(self.token) is TurnToken)
        text(self.text)


@dataclass(frozen=True)
class Exchange:
    token: TurnToken
    text: str = field(repr=False)
    response: str = field(repr=False)
    resolved_conflict: str | None

    def __post_init__(self):
        _require(type(self.token) is TurnToken)
        text(self.text)
        text(self.response)
        _optional_id(self.resolved_conflict)


@dataclass(frozen=True)
class Request:
    token: TurnToken
    text: str = field(repr=False)
    context: Context = field(repr=False)
    history: tuple[Exchange, ...] = field(repr=False)
    resolved_conflict: str | None

    def __post_init__(self):
        _require(type(self.token) is TurnToken and type(self.context) is Context)
        text(self.text)
        _tuple(self.history, Exchange, 64)
        _optional_id(self.resolved_conflict)
        _require(self.resolved_conflict is None or
                 self.resolved_conflict == self.context.conflict_id)
        _require(self.token.context_revision == self.context.revision)


@dataclass(frozen=True)
class Clarification:
    token: TurnToken
    conflict_id: str
    use_current: bool

    def __post_init__(self):
        _require(type(self.token) is TurnToken and type(self.use_current) is bool)
        _id(self.conflict_id)


@dataclass(frozen=True)
class Notice:
    version: int
    session_id: str | None
    turn: TurnToken | None
    state: Display
    code: Code

    def __post_init__(self):
        _require(type(self.version) is int and self.version == 1)
        _optional_id(self.session_id)
        _require(self.turn is None or type(self.turn) is TurnToken)
        _require(type(self.state) is Display and type(self.code) is Code)
        _require(self.turn is None or self.turn.session_id == self.session_id)
