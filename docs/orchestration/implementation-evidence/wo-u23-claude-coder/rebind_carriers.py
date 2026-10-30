"""Re-derive the WO-U23 carrier blob bindings: H at the U01 read, the U23 base and the
candidate head; O at its base. Prints JSON; exits nonzero if a path is missing at the
candidate or a Git call fails."""

import json
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
ops/orchestration/session_context.py .github/workflows/ci.yml""".split()


def blob(repo: str, rev: str, path: str) -> str | None:
    out = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "-q", f"{rev}:{path}"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()[:12] if out.returncode == 0 else None


def main(h: str, h_u01: str, h_base: str, h_cand: str, o: str, o_base: str) -> int:
    rows = {"H": {}, "O": {}}
    for p in H_PATHS:
        rows["H"][p] = {
            r: blob(h, rev, p)
            for r, rev in (("u01", h_u01), ("base", h_base), ("candidate", h_cand))
        }
    for p in O_PATHS:
        rows["O"][p] = {"base": blob(o, o_base, p)}
    print(json.dumps(rows, indent=1))
    missing = [p for p, b in rows["H"].items() if b["candidate"] is None]
    if missing:
        print(f"ERROR: absent at H candidate: {missing}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
