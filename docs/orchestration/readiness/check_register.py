"""Check docs/orchestration/workflow-readiness.md against WS-13 15.1.

Usage: python3 docs/orchestration/readiness/check_register.py \
    docs/orchestration/workflow-readiness.md [--spec <spec.md>] [--root <O>]

Prints one line per problem and exits 1 if there are any; prints "ok" and exits 0
otherwise. Python 3.11 stdlib only, matching root tooling.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

O_ROOT = Path("/home/robbo/Work/arhugula-omarchy")
SPEC = O_ROOT / "docs/orchestration/workflow-optimization-specification.md"

STATES = frozenset({"ready", "missing", "denied", "unknown"})
# WS-13 15.1 entry fields. Permission is its own field so a standing approval can
# never be read as a capability, and vice versa.
FIELDS = (
    "State",
    "Permission",
    "Owner",
    "Environment",
    "Evidence",
    "Resolution",
    "Dependent scenarios",
    "Revalidate when",
)
HOST_RESTORE = "Host storage/restore"


@dataclass(frozen=True)
class Entry:
    name: str
    fields: dict[str, str]


@dataclass(frozen=True)
class Denial:
    ident: str
    path: str
    sha256: str


def section(text: str, heading: str) -> str:
    """Body of the first heading whose title starts with `heading`, up to the next
    heading of the same or higher level."""
    match = re.search(rf"^(#+) {re.escape(heading)}.*$", text, re.M)
    if match is None:
        raise ValueError(f"heading not found: {heading!r}")
    level = len(match.group(1))
    rest = text[match.end():]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    return rest[: end.start()] if end else rest


def spec_prerequisites(spec_text: str) -> list[str]:
    # [LAW:one-source-of-truth] The prerequisite list is the spec's own 15.1 table;
    # the checker never carries a second copy of it.
    table = section(spec_text, "15.1 Early prerequisite register")
    rows = re.findall(r"^\| ([^|]+?) \| [^|]+ \|$", table, re.M)
    names = [row for row in rows if row != "Prerequisite" and not set(row) <= set("- ")]
    if not names:
        raise ValueError("no prerequisite rows in spec 15.1")
    return names


def parse_entries(doc_text: str) -> list[Entry]:
    register = section(doc_text, "Register")
    chunks = re.split(r"^### (.+)$", register, flags=re.M)[1:]
    entries = []
    for name, body in zip(chunks[::2], chunks[1::2]):
        fields = dict(re.findall(r"^- \*\*([^*]+):\*\* (.+(?:\n  .+)*)$", body, re.M))
        entries.append(Entry(name.strip(), {k: " ".join(v.split()) for k, v in fields.items()}))
    return entries


def parse_denials(doc_text: str) -> list[Denial]:
    table = section(doc_text, "Retained denials")
    return [
        Denial(ident, path, digest)
        for ident, path, digest in re.findall(
            r"^\| (D\d+) \| `([^`]+)` \| `([0-9a-f]{64})` \|", table, re.M
        )
    ]


def problems(doc_text: str, spec_text: str, root: Path) -> list[str]:
    found: list[str] = []
    entries = parse_entries(doc_text)
    names = [entry.name for entry in entries]
    expected = spec_prerequisites(spec_text)

    found += [f"missing entry: {name}" for name in expected if name not in names]
    found += [f"entry not in spec 15.1: {name}" for name in names if name not in expected]
    found += [f"duplicate entry: {name}" for name in sorted(set(names)) if names.count(name) > 1]

    denials = parse_denials(doc_text)
    if not denials:
        found.append("retained denials table is empty")
    for denial in denials:
        target = root / denial.path
        if not target.is_file():
            found.append(f"{denial.ident}: retained denial file absent: {denial.path}")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != denial.sha256:
            found.append(f"{denial.ident}: retained denial hash changed: {denial.path}")

    cited: set[str] = set()
    for entry in entries:
        found += [f"{entry.name}: missing field {f}" for f in FIELDS if not entry.fields.get(f)]
        found += [f"{entry.name}: unexpected field {f}" for f in entry.fields if f not in FIELDS]
        match = re.match(r"`(\w+)`", entry.fields.get("State", ""))
        state = match.group(1) if match else ""
        if state not in STATES:
            found.append(f"{entry.name}: state must start with one of {sorted(STATES)}")
        refs = set(re.findall(r"\bD\d+\b", " ".join(entry.fields.values())))
        cited |= refs
        if state == "denied" and not refs:
            found.append(f"{entry.name}: denied without a retained denial reference")
        evidence = entry.fields.get("Evidence", "")
        if not re.search(r"\brun-[\w-]+|\bcmt-[0-9a-f]{8}|`[^`]*/[^`]*`", evidence):
            found.append(f"{entry.name}: evidence cites no receipt, LIT comment or path")
        # The Mac share holds logs; it is not retained block storage outside the
        # guest's reset domain, so it can never be the proof of host restore.
        if entry.name == HOST_RESTORE and state == "ready" and "/mnt/mac" in evidence:
            found.append(f"{HOST_RESTORE}: artifact mount presented as restore readiness")

    known = {denial.ident for denial in denials}
    found += [f"denial {ident} is linked from no entry" for ident in sorted(known - cited)]
    found += [f"reference to undefined denial {ident}" for ident in sorted(cited - known)]
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("doc", type=Path)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--root", type=Path, default=O_ROOT)
    args = parser.parse_args(argv)
    found = problems(args.doc.read_text(), args.spec.read_text(), args.root)
    print("\n".join(found) if found else "ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
