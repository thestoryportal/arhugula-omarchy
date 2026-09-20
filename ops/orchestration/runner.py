"""Plan or run a bounded local continuation under one repository-wide lease."""
import argparse
import json
from pathlib import Path
import sys

from .continuation import Lease, Stop, continue_work, select_ticket
from .handoff import read_handoff
from .local import LocalAdapter, ProcessWorker
from .routing import route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "run"])
    parser.add_argument("--config", type=Path, help="trusted local JSON: worker_argv, verify_argv, goal")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--tickets", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text()) if args.config else {}
        adapter = LocalAdapter(args.cwd, config.get("verify_argv", ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]), timeout=min(args.seconds, 300))
        if args.mode == "plan":
            issue, ancestors = select_ticket(adapter.export(), adapter.next())
            print(json.dumps(route(issue, ancestors) if issue else {"stop_reason": "queue-empty"}, indent=2))
            return 0
        if not args.config or not isinstance(config.get("goal"), str) or not config["goal"].strip():
            raise ValueError("run requires a trusted worker config and goal")
        worker = ProcessWorker(config["worker_argv"], adapter.cwd, min(args.seconds, 900))
        state = adapter.common_dir() / "orchestration"
        with Lease(state / "runner.lock"):
            handoff = state / "handoff.json"
            prior = read_handoff(handoff) if handoff.exists() else None
            if prior and prior["stop_reason"] == "interrupted":
                raise Stop("recovery-required: inspect previous handoff and LIT/Git before retry")
            result = continue_work(adapter, worker, handoff, goal=config["goal"], limit=args.tickets, seconds=args.seconds, prior=prior)
            print(json.dumps(result, indent=2))
        return 0 if result["stop_reason"] in {"ticket-limit", "queue-empty"} else 2
    except (Stop, ValueError, KeyError, OSError) as error:
        print(f"continuation stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
