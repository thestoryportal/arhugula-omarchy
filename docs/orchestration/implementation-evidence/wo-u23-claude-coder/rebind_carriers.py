"""Re-derive the WO-U23 carrier bindings: H blobs at the U01 read, the U23 base and the
candidate head; O blobs at its base, plus the current SHA-256 and Git state of the bytes
in the canonical O root, with each row's owner and rollback disposition. Read-only: it
stages, rewrites and restores nothing. Prints JSON; exits nonzero if a path is missing at
the H candidate or an O row has no recorded owner."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

H_PATHS = """CLAUDE.md CONTEXT.md AGENTS.md docs/governance/roadmap-protocol.md
tools/hooks/safe-merge.sh tools/merge_door.py tools/roadmap_status_refresh.py
.claude/skills/ship-pr/SKILL.md .agents/skills/ship-pr/SKILL.md .claude/skills/roadmap-continue/SKILL.md
.codex/notes/discipline-digest.md .codex/notes/deterministic-context-workflow.md
tools/codex_context_guard.py tools/codex_loop.py justfile .agents/skills/codex-autonomous-loop/SKILL.md
.claude/settings.json .codex/hooks.json tools/hooks/postedit-lint.sh tools/hooks/stop-gate.sh
tools/hooks/stop-loop.sh tools/hooks/permission-guard.sh .githooks/pre-commit
tools/hooks/precmd-clear-cache.sh uv.lock tools/review_loop_gate.py tools/merge_gate_log.py
tools/review_schemas .claude/skills/merge-gate/SKILL.md .agents/skills/merge-gate/SKILL.md
.github/workflows/ci.yml tools/ci_bookkeeping_diff.py tools/roadmap-audit/post-merge-refresh.sh
tools/roadmap-audit/session-start.sh tools/hooks/prompt-context.sh tools/hooks/lib.sh
.claude/skills/two-lane/SKILL.md .agents/skills/two-lane/SKILL.md .codex/notes/leg-brief-template.md
.codex/notes/claude-codex-parity.md tools/arc_exit_report.py tools/arc_metrics.py tools/lanes_pilot.py
tools/prime_report.py tools/branch_hygiene_batch.py .harness/roadmap_status.md Project_Roadmap_v1.md
tools/test_roadmap_status_refresh.py tools/test_roadmap_status_consumers.py tools/test_roadmap_ritual_smoke.py
tools/test_codex_context_guard.py tools/test_merge_door.py tools/test_codex_workflow_parity.py
tools/test_arc_exit_report.py tools/test_branch_hygiene_batch.py tools/test_ci_bookkeeping_filter.py
tools/hooks/test_lib.sh tools/hooks/test_prompt_context.sh tools/hooks/test_skill_exit_report.sh
tools/hooks/test_skill_two_lane.sh tools/roadmap-audit/test_post_merge_refresh.sh
tools/roadmap-audit/test_session_start.sh tools/codex-parity-check.sh tools/loop_cost_baseline.py
.harness/workflow-policy.json tools/workflow_policy.py tools/workflow_boundaries.py tools/workflow_commit.py
tools/workflow_evidence.py tools/workflow_adoption.py tools/test_workflow_adoption.py
tools/test_merge_gate_log.py tools/test_review_loop_gate.py""".split()
O_PATHS = """AGENTS.md CLAUDE.md docs/orchestration/paired-lanes-framework.md docs/orchestration/context-policy.md
docs/orchestration/communication.md docs/orchestration/authorization.md docs/orchestration/memento-current.md
docs/orchestration/session-control.json docs/orchestration/launch-profiles.json ops/orchestration/loop.py
ops/orchestration/local.py ops/orchestration/artifacts.py ops/orchestration/records.py
ops/orchestration/review_budget.py ops/orchestration/auto_reset.py ops/orchestration/goal_lineage.py
ops/orchestration/native_window.py ops/orchestration/native_goal.py ops/orchestration/startup.py
ops/orchestration/session_context.py .github/workflows/ci.yml .promptctl/memento.conf
docs/orchestration/roles/buford.md docs/orchestration/roles/claude-coder.md
docs/orchestration/roles/codex-reviewer.md docs/orchestration/roles/facade-coder.md
docs/orchestration/roles/implementer.md docs/orchestration/roles/reviewer.md
docs/orchestration/roles/runtime.md""".split()
_GUIDANCE = (
    "protected root guidance; user-directed edits via Buford",
    "retained in place: rollback restores no root bytes, and these hashes are the version a "
    "restored set binds",
)
_CONTROL = (
    "Buford/operator (routing, profiles, Memento ceilings)",
    "retained in place: current routing and limits govern after any rollback",
)
_TOOLING = (
    "root orchestration tooling (O main)",
    "retained: a Git-tracked revision; protected dirty bytes are preserved, never reset",
)
# [LAW:one-source-of-truth] owner/rollback disposition per O row, by path prefix
O_OWNERS = {
    "AGENTS.md": _GUIDANCE,
    "CLAUDE.md": _GUIDANCE,
    "docs/orchestration/roles/": _GUIDANCE,
    "docs/orchestration/paired-lanes-framework.md": _GUIDANCE,
    "docs/orchestration/context-policy.md": _GUIDANCE,
    "docs/orchestration/communication.md": _GUIDANCE,
    "docs/orchestration/authorization.md": _GUIDANCE,
    "docs/orchestration/memento-current.md": _GUIDANCE,
    "docs/orchestration/session-control.json": _CONTROL,
    "docs/orchestration/launch-profiles.json": _CONTROL,
    ".promptctl/memento.conf": _CONTROL,
    "ops/orchestration/": _TOOLING,
    ".github/workflows/ci.yml": _TOOLING,
}


def blob(repo: str, rev: str, path: str) -> str | None:
    out = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "-q", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()[:12] if out.returncode == 0 else None


def root_bytes(root: str, path: str) -> dict[str, str | None]:
    """The current bytes at the canonical root: their SHA-256 and Git porcelain state."""
    file = Path(root) / path
    status = subprocess.run(
        ["git", "-C", root, "status", "--porcelain", "--", path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout[:2]
    state = {"": "clean", "??": "untracked"}.get(status, f"tracked-{status.strip() or 'changed'}")
    return {
        "root_sha256": hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None,
        "root_state": state if file.is_file() else "absent",
    }


def owner(path: str) -> tuple[str, str] | None:
    return next((v for k, v in O_OWNERS.items() if path == k or path.startswith(k)), None)


def main(h: str, h_u01: str, h_base: str, h_cand: str, o: str, o_base: str, o_root: str) -> int:
    root_head = subprocess.run(
        ["git", "-C", o_root, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # root_state is relative to the canonical root checkout's own HEAD, recorded here
    rows = {"H": {}, "O": {}, "O_root": {"path": o_root, "head": root_head}}
    for p in H_PATHS:
        rows["H"][p] = {
            r: blob(h, rev, p)
            for r, rev in (("u01", h_u01), ("base", h_base), ("candidate", h_cand))
        }
    for p in O_PATHS:
        disposition = owner(p) or (None, None)
        rows["O"][p] = {
            "base": blob(o, o_base, p),
            **root_bytes(o_root, p),
            "owner": disposition[0],
            "rollback": disposition[1],
        }
    print(json.dumps(rows, indent=1))
    missing = [p for p, b in rows["H"].items() if b["candidate"] is None]
    unowned = [p for p, b in rows["O"].items() if b["owner"] is None]
    for label, paths in (("absent at H candidate", missing), ("O row without owner", unowned)):
        if paths:
            print(f"ERROR: {label}: {paths}", file=sys.stderr)
    return 1 if missing or unowned else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
