"""Active assignment ownership: who writes which checkout, paths and scarce resources.

A reservation is recorded before work uses what it names. Conflicts are decided
here once; the loop journal stores the records and the local adapter reads them.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Writer:
    """One authoring assignment in its isolated checkout, with its reserved reviewer."""

    key: str  # LIT ticket
    owner: str
    reviewer: str
    worktree: Path
    paths: frozenset
    resources: frozenset

    @property
    def worktrees(self):
        return frozenset({self.worktree})

    @property
    def writes(self):
        return self.paths

    @property
    def declared_dirty(self):
        return self.paths


@dataclass(frozen=True)
class Hold:
    """A non-writing reservation of resources, e.g. a Runtime quiet window."""

    key: str
    owner: str
    resources: frozenset

    worktrees = writes = declared_dirty = frozenset()


@dataclass(frozen=True)
class Preserved:
    """Protected dirty work kept in place; it occupies its checkout but writes nothing."""

    key: str  # evidence pointer recording the preservation
    worktree: Path
    paths: frozenset

    resources = writes = frozenset()

    @property
    def worktrees(self):
        return frozenset({self.worktree})

    @property
    def declared_dirty(self):
        return self.paths


def _text(record, name):
    value = record.get(name)
    if type(value) is not str or not value:
        raise ValueError(f"invalid reservation: {name}")
    return value


def _names(record, name):
    value = record.get(name)
    if type(value) is not list or any(type(x) is not str or not x for x in value):
        raise ValueError(f"invalid reservation: {name}")
    return frozenset(value)


def _paths(record):
    paths = _names(record, "paths")
    for path in paths:
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ValueError(f"invalid reservation: path {path!r}")
    return paths


def _worktree(record):
    path = Path(_text(record, "worktree"))
    if not path.is_absolute():
        raise ValueError("invalid reservation: worktree must be absolute")
    return path.resolve()


_KINDS = {
    "writer": lambda r: Writer(
        _text(r, "key"), _text(r, "owner"), _text(r, "reviewer"),
        _worktree(r), _paths(r), _names(r, "resources")),
    "hold": lambda r: Hold(_text(r, "key"), _text(r, "owner"), _names(r, "resources")),
    "preserved": lambda r: Preserved(_text(r, "key"), _worktree(r), _paths(r)),
}


def parse(record):
    # [LAW:parse-dont-validate] Journal and caller records become typed reservations here.
    kind = record.get("kind") if isinstance(record, dict) else None
    if kind not in _KINDS:
        raise ValueError(f"invalid reservation: kind {kind!r}")
    return _KINDS[kind](record)


def covers(declared, path):
    """A declared path names one file; a trailing slash names a directory tree."""
    return any(path == d or d.endswith("/") and path.startswith(d) for d in declared)


def _overlap(left, right):
    return any(covers(left, p) for p in right) or any(covers(right, p) for p in left)


def conflicts(active, candidate):
    """Every reason `candidate` may not join `active`; empty means it may."""
    # [LAW:single-enforcer] The one decision on overlapping ownership and reservations.
    reasons = []
    for other in active:
        reasons += [
            reason
            for reason, clash in (
                ("duplicate-reservation", other.key == candidate.key),
                ("worktree-conflict", bool(other.worktrees & candidate.worktrees)),
                ("path-conflict", _overlap(other.writes, candidate.writes)),
                ("resource-conflict", bool(other.resources & candidate.resources)),
            )
            if clash
        ]
    if isinstance(candidate, Writer):
        authors = {w.owner for w in active if isinstance(w, Writer)}
        reviewers = {w.reviewer for w in active if isinstance(w, Writer)}
        reasons += [
            reason
            for reason, clash in (
                ("reviewer-not-independent", candidate.reviewer == candidate.owner),
                ("reviewer-is-active-author", candidate.reviewer in authors),
                ("author-reserved-as-reviewer", candidate.owner in reviewers),
            )
            if clash
        ]
    return sorted(set(reasons))


def undeclared(active, worktree, dirty):
    """Dirty paths in `worktree` that no active reservation declares as its own."""
    declared = frozenset().union(
        *(r.declared_dirty for r in active if Path(worktree).resolve() in r.worktrees)
    )
    return {path for path in dirty if not covers(declared, path)}
