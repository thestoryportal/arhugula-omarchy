"""WO-U16: the seven prepared A5/A4/A7 units carry actionable reuse dispositions.

The record is the one map a later pull reads before reusing or reconstructing a
prepared unit, so the parser below is the contract it must satisfy: full commit
IDs, a disposition from the four specified kinds with that kind's own required
fields, and a stack whose parents follow the A3 -> A5 -> A4 clearance order.
"""

from dataclasses import dataclass
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/orchestration/assignment-snapshots/wo-u16-prepared-dispositions.json"
PRODUCT = Path("/home/robbo/Work/arhugula-build-eval")
WORKTREES = Path("/home/robbo/Work/arhugula-omarchy")

FULL_ID = re.compile(r"[0-9a-f]{40}")
COMMENT_ID = re.compile(r"cmt-[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
# [LAW:types-are-the-program] Each kind names exactly the fields its consumer acts on.
KIND_FIELDS = {
    "reuse_unchanged": ("reverification",),
    "reuse_with_delta": ("delta", "reverification"),
    "held": ("blocker", "release_condition"),
    "superseded_with_reason": ("reason", "replacement"),
}
UNIT_FIELDS = ("unit", "stream", "worktree", "branch", "head", "parent", "merge_base",
               "base_delta", "contract_impact", "dependency_changes", "clearance_gate",
               "retained_findings", "disposition")


@dataclass(frozen=True)
class Unit:
    unit: str
    stream: str
    worktree: str
    branch: str
    head: str
    parent: str
    merge_base: str
    kind: str
    delta: str
    reverification: tuple


@dataclass(frozen=True)
class Record:
    baseline: str
    clearance_order: tuple
    stack_root: str
    contract_commits: tuple
    units: tuple


def _full_id(value, where):
    if not isinstance(value, str) or not FULL_ID.fullmatch(value):
        raise ValueError(f"{where}: not a full commit ID: {value!r}")
    return value


def _text(entry, field, where):
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: missing {field}")
    return value


def _comments(values, where):
    if not values or any(not isinstance(v, str) or not COMMENT_ID.fullmatch(v) for v in values):
        raise ValueError(f"{where}: evidence needs full LIT comment IDs: {values!r}")


def _unit(entry, index):
    where = f"units[{index}]"
    missing = [field for field in UNIT_FIELDS if field not in entry]
    if missing:
        raise ValueError(f"{where}: missing {missing}")
    for finding in entry["retained_findings"]:
        _text(finding, "summary", where)
        _comments(finding.get("evidence"), where)
    disposition = entry["disposition"]
    kind = disposition.get("kind")
    if kind not in KIND_FIELDS:
        raise ValueError(f"{where}: unknown disposition {kind!r}")
    for field in KIND_FIELDS[kind]:
        value = disposition.get(field)
        if not value or (isinstance(value, list) and not all(isinstance(v, str) and v.strip() for v in value)):
            raise ValueError(f"{where}: {kind} needs {field}")
    _comments(disposition.get("evidence"), where)
    return Unit(
        unit=_text(entry, "unit", where), stream=_text(entry, "stream", where),
        worktree=_text(entry, "worktree", where), branch=_text(entry, "branch", where),
        head=_full_id(entry["head"], f"{where}.head"),
        parent=_full_id(entry["parent"], f"{where}.parent"),
        merge_base=_full_id(entry["merge_base"], f"{where}.merge_base"), kind=kind,
        delta=disposition.get("delta", ""),
        reverification=tuple(disposition.get("reverification", ())))


def _stack_parents(record):
    """Each unit sits on its stream predecessor; a stream's first unit sits on the
    previous clearance stream's last head, or on its merge base when unordered."""
    expected, last_head = {}, {}
    previous = record.stack_root
    for stream in record.clearance_order[1:]:
        heads = [u for u in record.units if u.stream == stream]
        if not heads:
            raise ValueError(f"clearance stream {stream} has no units")
        expected[heads[0].unit] = previous
        previous = heads[-1].head
    for unit in record.units:
        expected.setdefault(unit.unit, last_head.get(unit.stream, unit.merge_base))
        if unit.parent != expected[unit.unit]:
            raise ValueError(f"{unit.unit}: parent {unit.parent} breaks the stack order")
        last_head[unit.stream] = unit.head


def parse_record(raw):
    units = tuple(_unit(entry, index) for index, entry in enumerate(raw["units"]))
    for field in ("unit", "head", "worktree"):
        values = [getattr(u, field) for u in units]
        if len(set(values)) != len(values):
            raise ValueError(f"duplicate unit {field}")
    record = Record(
        baseline=_full_id(raw["baseline"]["commit"], "baseline"),
        clearance_order=tuple(raw["clearance_order"]),
        stack_root=_full_id(raw["stack_root"]["head"], "stack_root"),
        contract_commits=tuple(_full_id(c["commit"], "contract_commits") for c in raw["contract_commits"]),
        units=units)
    _stack_parents(record)
    return record


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


class PreparedDispositionRecordTest(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(RECORD.read_text())

    def test_record_dispositions_cover_the_seven_prepared_units_in_clearance_order(self):
        record = parse_record(self.raw)

        self.assertEqual(
            [(u.unit, u.kind) for u in record.units],
            [("A5 U1", "reuse_with_delta"), ("A5 U2", "reuse_with_delta"),
             ("A5 U3", "reuse_with_delta"), ("A4 U1", "reuse_with_delta"),
             ("A4 U2", "reuse_with_delta"), ("A7 U1", "reuse_with_delta"),
             ("A7 U2", "reuse_with_delta")])
        self.assertEqual(record.clearance_order, ("A3", "A5", "A4"))

    def test_a4_disposition_carries_the_source_work_rt_plan_v2_67_still_owes(self):
        # Rebasing cf1c916f alone cannot clear A4: the plan's Delivery portions say no
        # preparation head carries the returned-arm result-preserving carrier.
        a4 = {u.unit: u for u in parse_record(self.raw).units if u.stream == "A4"}
        owed = " ".join((a4["A4 U2"].delta, *a4["A4 U2"].reverification)).lower()

        for obligation in ("RefusedChildResultAuditSigningError", "result_ref", "criterion 2",
                           "criterion 5", "criterion 4", "real-leaf", "criterion 8"):
            with self.subTest(obligation):
                self.assertIn(obligation.lower(), owed)
        self.assertNotIn("No file content change is expected", a4["A4 U2"].delta)
        gate = self.raw["units"][4]["clearance_gate"]
        self.assertIn("A5", gate)
        self.assertIn("A3", gate)

    def test_parser_refuses_records_a_later_pull_could_not_act_on(self):
        def mutated(change):
            raw = copy.deepcopy(self.raw)
            change(raw)
            return raw

        cases = {
            "short head": lambda r: r["units"][0].update(head=r["units"][0]["head"][:8]),
            "unknown kind": lambda r: r["units"][1]["disposition"].update(kind="reuse"),
            "delta without reverification": lambda r: r["units"][2]["disposition"].update(reverification=[]),
            "held without release": lambda r: r["units"][3].update(
                disposition={"kind": "held", "blocker": "A3 witness", "evidence": r["units"][3]["disposition"]["evidence"]}),
            "missing contract impact": lambda r: r["units"][4].pop("contract_impact"),
            "missing clearance gate": lambda r: r["units"][5].pop("clearance_gate"),
            "duplicate head": lambda r: r["units"][6].update(head=r["units"][5]["head"]),
            "short comment pointer": lambda r: r["units"][5]["disposition"].update(evidence=["cmt-8ac926b9"]),
            "A4 off the A5 stack": lambda r: r["units"][3].update(parent=r["stack_root"]["head"]),
            "short baseline": lambda r: r["baseline"].update(commit="3e913ccc"),
        }
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                parse_record(mutated(change))


@unittest.skipUnless((PRODUCT / ".git").exists(), "product checkout H is not present on this host")
class PreparedDispositionResolutionTest(unittest.TestCase):
    """[LAW:behavior-not-structure] The record's IDs are checked against the actual repositories."""

    def test_every_recorded_commit_resolves_and_matches_its_retained_worktree(self):
        raw = json.loads(RECORD.read_text())
        record = parse_record(raw)

        for commit in (record.baseline, record.stack_root, *record.contract_commits):
            self.assertEqual(_git(PRODUCT, "rev-parse", "--verify", f"{commit}^{{commit}}"), commit)
        for commit in record.contract_commits:
            _git(PRODUCT, "merge-base", "--is-ancestor", commit, record.baseline)
        for unit in record.units:
            with self.subTest(unit.unit):
                self.assertEqual(_git(PRODUCT, "rev-parse", "--verify", f"{unit.head}^"), unit.parent)
                self.assertEqual(_git(PRODUCT, "merge-base", unit.head, record.baseline), unit.merge_base)
                self.assertNotEqual(unit.merge_base, unit.head, "a landed unit needs superseded_with_reason")
                worktree = WORKTREES / unit.worktree.removeprefix("O/")
                self.assertEqual(_git(worktree, "rev-parse", "HEAD"), unit.head)
                self.assertEqual(_git(worktree, "branch", "--show-current"), unit.branch)


if __name__ == "__main__":
    unittest.main()
