"""Offline model-transport fixture. Receives the real supervisor context."""
import json
from pathlib import Path
import sys

context = json.load(sys.stdin)
identifier = context["active_ticket"]
path = Path(identifier + ".json")
path.write_text(json.dumps({"ticket": identifier, "model": context["model"],
                            "effort": context["effort"], "goal": context["goal"],
                            "prior_completed": context["completed_work"]}, indent=2) + "\n")
print(json.dumps({"files": [str(path)], "summary": "Wrote harmless isolated fixture",
                  "risks": [], "stop_reason": None}))
