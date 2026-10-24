"""Measure every session-control row with the existing admit command (read-only).

This is an observation for the readiness register, not an admission decision.
"""

import json
import subprocess
import sys
from pathlib import Path

O_ROOT = Path("/home/robbo/Work/arhugula-omarchy")
control = json.loads((O_ROOT / "docs/orchestration/session-control.json").read_text())
print(json.dumps({"repair_paused": control["repair_paused"],
                  "notification_thread": control["notification_thread"]}))
for row in control["sessions"]:
    argv = [sys.executable, "-m", "ops.orchestration.session_context", "admit",
            "--kind", row["kind"], "--transcript", row["transcript"],
            "--task-budget", str(row["task_budget"]), "--reserve", str(row["reserve"]),
            "--ceiling", str(row["ceiling"])]
    result = subprocess.run(argv, capture_output=True, text=True, cwd=O_ROOT)
    # admit exits 1 on a hold; the decision JSON on stdout is the observation.
    print(json.dumps({"role": row["role"], "session_id": row["session_id"],
                      "exit": result.returncode, "stdout": result.stdout.strip(),
                      "stderr": result.stderr.strip()}))
