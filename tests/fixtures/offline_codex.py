"""Stand-in executable for the installed Codex exec argv/output-file protocol."""
import json
from pathlib import Path
import sys

args = sys.argv[1:]
context = json.load(sys.stdin)
model = args[args.index("--model") + 1]
effort = args[args.index("--config") + 1]
output = Path(args[args.index("--output-last-message") + 1])
assert args[-1] == "-"
assert "supervisor" in context
assert context["model"] == model
Path("capture.json").write_text(json.dumps({"argv": args, "context": context}))
output.write_text(json.dumps({"files": ["capture.json"], "summary": model + " " + effort,
                              "risks": [], "stop_reason": None}))
print("Codex stream logging is not a receipt")
