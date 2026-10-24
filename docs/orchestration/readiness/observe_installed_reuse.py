"""Judge whether the accepted 19-step build/install may be reused at a product revision.

Read-only: it hashes the retained native acceptance, the existing install and Git objects,
and never runs the installed interpreter, a build or a scenario. Run it with the pinned
product interpreter so `tools.workflow_evidence` (WO-U19) is the code that decides:

    /home/robbo/Work/arhugula-build-eval/.venv/bin/python \
        docs/orchestration/readiness/observe_installed_reuse.py \
        --product /home/robbo/Work/arhugula-build-eval --current origin/main --out DIR

It prints one JSON summary and writes the equivalence record it derived into DIR.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/home/robbo/Work/arhugula-omarchy")
ACCEPTANCE = (
    ROOT
    / ".local/production-source09-01a10968/installed-build-execution-01a10c4c"
    / "build-evidence-acceptance.json"
)
ACCEPTED_HEAD = "91e76a4e22ffc0b013fa14a5d680d1c991f5a1e5"
EXEC_ROOT = ROOT / ".local/production-source09-01a10968/installed-a3-exec-01a10bd5"
UNIT = "arhugula-harness-trial-193.c4s.g4k"
REPOSITORY = "thestoryportal/arhugula-harness"
PACKAGES = ("core", "is", "as", "cp", "od", "cxa", "runtime")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--current", required=True, help="product revision to judge")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product))
    from tools import workflow_evidence as evidence
    from tools.workflow_policy import parse_policy

    policy = parse_policy(
        (args.product / ".harness" / "workflow-policy.json").read_bytes()
    )

    def installed_inputs(rev: str) -> evidence.InputManifest:
        # Installed inputs only: each member's source and project file plus the root
        # project and lock. Gates, docs and tools are not built into any wheel.
        return evidence.build_manifest(
            args.product,
            evidence.CheckRequest(
                unit=UNIT,
                repository=REPOSITORY,
                scope=evidence.GitTree(rev),
                policy=policy,
                checker=evidence.Checker(
                    "uv-build", "0.12.21", ("uv", "build", "--all-packages")
                ),
                domains=tuple(f"harness-{name}/src" for name in PACKAGES),
                explicit=("pyproject.toml", "uv.lock")
                + tuple(f"harness-{name}/pyproject.toml" for name in PACKAGES),
                environment={},
                material_base=None,
                closure="declared",
            ),
        )

    acceptance = ACCEPTANCE.read_bytes()
    pinned = Path(json.loads(acceptance)["result"]["path"])
    accepted = evidence.accepted_build_install(
        acceptance, pinned.read_bytes(), installed_inputs(ACCEPTED_HEAD)
    )
    artifact, environment = evidence.observe_install(
        EXEC_ROOT, tuple(f"harness_{name}" for name in PACKAGES), origins=None
    )
    current = evidence.InstalledCandidate(
        installed_inputs(args.current), artifact, environment
    )
    without = evidence.install_reuse(accepted, current)
    summary: dict[str, object] = {
        "accepted_record": accepted.record_id,
        "accepted_head": accepted.candidate.source.head,
        "accepted_key": accepted.candidate.key,
        "current_head": current.source.head,
        "current_key": current.key,
        "installed_inputs_identical": accepted.candidate.source.key
        == current.source.key,
        "without_equivalence": {
            "disposition": without.disposition,
            "reasons": without.reasons,
        },
    }
    if summary["installed_inputs_identical"]:
        record = evidence.install_equivalence_record(
            accepted,
            current,
            record_id=f"wo-u19-install-equivalence-{current.source.head[:12]}",
            producer={"tool": "observe_installed_reuse.py", "unit": UNIT},
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / "install-equivalence.json"
        path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        carried = evidence.install_reuse(
            accepted, current, evidence.parse_equivalence(path.read_bytes())
        )
        summary["with_equivalence"] = {
            "record": str(path),
            "disposition": carried.disposition,
            "reasons": carried.reasons,
        }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
