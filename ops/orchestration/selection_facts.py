"""WO-U24 native admission fact for the trial workflow's `SelectionFacts.admission`.

Under the paired workflow a unit's live assignment is its native LIT claim, not a Buford
loop grant. `admission` judges one export snapshot plus the canonical routing: the unit
is claimed (`in_progress`) by a routed pair author, a paused production scope is released
by a closed human gate the unit inherits, and the session acting for the operation is
admitted by its own measured context. The author acts for `implementation`; Buford, the
sole integrator, acts for `integration`. Every fact the snapshot cannot establish is
`unknown`; every fact it refutes is `contradicted`. Both refuse trial selection.

The product repository's selection adapter runs this file with `python3 -I`, so it imports
the orchestration package from its own checkout root rather than from the caller.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):  # run as a script by the product selection adapter
    sys.path.insert(0, str(ROOT))

from ops.orchestration.loop import HUMAN_GATE, prerequisites  # noqa: E402
from ops.orchestration.session_context import admit, inspect_transcript  # noqa: E402

CONTROL = ROOT / "docs" / "orchestration" / "session-control.json"
AUTHOR_ROLES = frozenset({"claude-coder", "profile-coder", "facade-coder"})
OPERATIONS = ("implementation", "integration")
# The acting session's own check runs inside its turn, so its latest response is never
# complete yet; that alone is not a refusal. Every other admit reason is.
IN_TURN = "session-not-complete"
UNREAD = "missing-request-metric"


def _observed(admission, *reasons, session=None):
    return {"admission": admission, "reasons": list(reasons), "session_id": session}


def released(data, unit):
    """The unit inherits at least one human gate and every one is closed. [LAW:single-enforcer]
    the rule `loop.Preparation.admit` applies: an open inherited gate still holds."""
    issues = {i["id"]: i for i in data["issues"]}
    gates = [
        issues[gate] for gate in prerequisites(data, unit)
        if HUMAN_GATE in issues[gate].get("labels", ())
    ]  # fmt: skip
    return bool(gates) and all(gate["status"] == "closed" for gate in gates)


def admission(data, control, unit, operation, measure):
    """[LAW:effects-at-boundaries] pure over the snapshot; `measure` is the one effect, the
    acting session's `session_context.admit` decision."""
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {OPERATIONS}: {operation!r}")
    issues = [i for i in data["issues"] if i["id"] == unit]
    if len(issues) != 1:
        return _observed("unknown", "unit-not-in-lit")
    if issues[0]["status"] != "in_progress":
        return _observed("contradicted", "unit-not-claimed")
    # The export omits an empty assignee; an unassigned unit has no routed holder.
    holder = issues[0].get("assignee", "")
    sessions = control["sessions"]
    author = next((s for s in sessions if holder == f"{s['kind']}_{s['session_id']}"), None)
    if author is None or author["role"] not in AUTHOR_ROLES:
        return _observed("contradicted", "claim-holder-not-a-routed-author")
    if control["repair_paused"] is not False and not released(data, unit):
        return _observed("contradicted", "production-paused", session=author["session_id"])
    leads = [s for s in sessions if s["role"] == "buford"]
    if operation == "integration" and len(leads) != 1:
        return _observed("unknown", "one-buford-routing-record-required")
    actor = author if operation == "implementation" else leads[0]
    reasons = [r for r in measure(actor)["reasons"] if r != IN_TURN]
    verdict = "unknown" if UNREAD in reasons else "contradicted" if reasons else "confirmed"
    return _observed(verdict, *reasons, session=actor["session_id"])


def measure(row):
    """[LAW:single-enforcer] the existing measured admission, with the row's own limits."""
    return admit(
        inspect_transcript(row["kind"], row["transcript"]),
        task_budget=row["task_budget"],
        reserve=row["reserve"],
        ceiling=row["ceiling"],
        expected_session_id=row["session_id"],
    )


def observe(unit, operation):
    """One native export and the canonical routing, judged once. A failed read is unknown."""
    try:
        export = subprocess.run(
            ["lit", "export"], cwd=ROOT, capture_output=True, check=True, timeout=30
        ).stdout
        return admission(
            json.loads(export), json.loads(CONTROL.read_text()), unit, operation, measure
        )
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        return _observed("unknown", f"unreadable: {type(error).__name__}: {error}")


def main(argv=None):
    """`selection_facts.py admission <unit> <implementation|integration>`: one JSON line.
    Exit 0 for every observation, 2 for a usage error."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] != "admission" or args[2] not in OPERATIONS:
        print(f"usage: selection_facts.py admission <unit> <{'|'.join(OPERATIONS)}>",
              file=sys.stderr)
        return 2
    print(json.dumps(observe(args[1], args[2]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
