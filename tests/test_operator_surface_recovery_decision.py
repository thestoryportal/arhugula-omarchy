"""WO-U17: the operator-surface recovery decision is a map whose citations hold.

The decision record is the one place later CLI/MCP/HTTP work reads before it
builds resume behavior, so the parser below is the contract it must satisfy:
one decision row per required behavior, every row grounded in cited product
evidence, every gap owned, and every citation true at the pinned product
revision. A citation is either a literal on an exact line or a literal that is
absent from a file, because several gaps are claims that something does not
exist yet.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/orchestration/operator-surface-recovery-decision.md"
PRODUCT = Path("/home/robbo/Work/arhugula-build-eval")

# [LAW:one-source-of-truth] The required behaviors come from U17's Done-when and
# spec WS-05; the record must carry exactly these rows, no more and no fewer.
BEHAVIORS = (
    "Operation identity",
    "Admission owner",
    "Durable paused state",
    "At-most-once resume",
    "Typed refusal",
    "Inherited authorization",
    "Transport presentation",
)
REVISION = re.compile(r"^H revision: `([0-9a-f]{40})`$", re.MULTILINE)
LOCATION = re.compile(r"^(?P<path>[^\s:]+)(?::(?P<line>[1-9][0-9]*)| \(absent\))$")
LITERAL = re.compile(r"^`([^`|]+)`$")
EVIDENCE_ID = re.compile(r"E[1-9][0-9]*")
GAP_ID = re.compile(r"G[1-9][0-9]*")


@dataclass(frozen=True)
class Citation:
    id: str
    path: str
    line: int | None  # None means the literal must be absent from the file.
    literal: str


@dataclass(frozen=True)
class Row:
    name: str
    evidence: tuple
    gaps: tuple


@dataclass(frozen=True)
class Gap:
    id: str
    owner: str
    held_until: str
    evidence: tuple


@dataclass(frozen=True)
class Decision:
    revision: str
    behaviors: tuple
    gaps: tuple
    citations: tuple


def _table(text, heading):
    """Body rows of the first pipe table under `## heading`, split into cells."""
    section = text.split(f"\n## {heading}\n", 1)
    if len(section) != 2:
        raise ValueError(f"missing section: {heading}")
    lines = [line for line in section[1].split("\n## ", 1)[0].splitlines()
             if line.startswith("|")]
    if len(lines) < 3:
        raise ValueError(f"section {heading} has no table rows")
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[2:]]


def _ids(cell, pattern, empty_ok):
    if empty_ok and cell == "none":
        return ()
    ids = tuple(part.strip() for part in cell.split(","))
    if not ids or not all(pattern.fullmatch(part) for part in ids):
        raise ValueError(f"bad id list: {cell!r}")
    return ids


def _citation(cells):
    ident, location, literal = cells
    where = LOCATION.fullmatch(location)
    text = LITERAL.fullmatch(literal)
    if not EVIDENCE_ID.fullmatch(ident) or where is None or text is None:
        raise ValueError(f"bad evidence row: {cells!r}")
    line = where.group("line")
    return Citation(ident, where.group("path"), int(line) if line else None, text.group(1))


def parse(text):
    revision = REVISION.search(text)
    if revision is None:
        raise ValueError("missing pinned H revision")
    # [LAW:parse-dont-validate] Each table becomes typed rows once; checks read only these.
    behaviors = tuple(Row(name, _ids(evidence, EVIDENCE_ID, False), _ids(gaps, GAP_ID, True))
                      for name, _decision, evidence, gaps in _table(text, "Behaviors"))
    gaps = tuple(Gap(ident, owner, held, _ids(evidence, EVIDENCE_ID, False))
                 for ident, _missing, owner, held, evidence in _table(text, "Gaps and owners"))
    citations = tuple(_citation(cells) for cells in _table(text, "Evidence"))
    return Decision(revision.group(1), behaviors, gaps, citations)


def product_file(revision, path):
    return subprocess.run(["git", "-C", str(PRODUCT), "show", f"{revision}:{path}"],
                          check=True, capture_output=True, text=True).stdout


def holds(citation, revision):
    content = product_file(revision, citation.path)
    if citation.line is None:
        return citation.literal not in content
    lines = content.splitlines()
    return citation.line <= len(lines) and citation.literal in lines[citation.line - 1]


class OperatorSurfaceRecoveryDecisionTest(unittest.TestCase):
    def setUp(self):
        self.text = RECORD.read_text()
        self.decision = parse(self.text)

    def test_every_required_behavior_has_exactly_one_decision_row(self):
        self.assertEqual(tuple(row.name for row in self.decision.behaviors), BEHAVIORS)

    def test_every_citation_holds_at_the_pinned_product_revision(self):
        failed = [c.id for c in self.decision.citations if not holds(c, self.decision.revision)]
        self.assertEqual(failed, [])

    def test_every_cited_id_is_defined_and_every_defined_id_is_cited(self):
        defined = [c.id for c in self.decision.citations]
        self.assertEqual(len(defined), len(set(defined)))
        # Prose citations count too, so the authority paragraph cannot cite an undefined ID.
        body = self.text.split("\n## Evidence\n", 1)[0]
        cited = set(re.findall(rf"\b{EVIDENCE_ID.pattern}\b", body))
        self.assertEqual(cited, set(defined))
        gap_ids = [gap.id for gap in self.decision.gaps]
        self.assertEqual(len(gap_ids), len(set(gap_ids)))
        self.assertEqual({g for row in self.decision.behaviors for g in row.gaps}, set(gap_ids))

    def test_every_gap_names_an_owner_and_a_held_until_condition(self):
        self.assertTrue(self.decision.gaps)
        for gap in self.decision.gaps:
            with self.subTest(gap=gap.id):
                self.assertTrue(gap.owner and gap.held_until)

    def test_a_moved_or_reworded_citation_fails(self):
        line = next(c for c in self.decision.citations if c.line is not None)
        absent = next(c for c in self.decision.citations if c.line is None)
        moved = Citation(line.id, line.path, line.line + 1, line.literal)
        opening = product_file(self.decision.revision, absent.path)[:20]
        present = Citation(absent.id, absent.path, None, opening)
        self.assertFalse(holds(moved, self.decision.revision))
        self.assertFalse(holds(present, self.decision.revision))

    def test_a_row_without_evidence_does_not_parse(self):
        broken = re.sub(r"(\| Typed refusal \|[^|]*\|)[^|]*\|", r"\1  |", self.text, count=1)
        self.assertNotEqual(broken, self.text)
        with self.assertRaises(ValueError):
            parse(broken)


if __name__ == "__main__":
    unittest.main()
