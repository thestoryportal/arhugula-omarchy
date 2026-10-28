"""Plan or run a bounded local continuation under one repository-wide lease."""
import argparse
import json
from pathlib import Path
import sys

from .continuation import Lease, Stop, continue_work, select_ticket
from .handoff import read_handoff
from .local import CodexWorker, LocalAdapter, ProcessWorker
from .routing import route
from .artifacts import DEFAULT_ROOT
from .loop import Loop, NativeLit, journal_ownership


def adapter_for(config, cwd, seconds):
    # The loop journal owns active reservations, held under its lease per inspection,
    # and the admission every effect of this run must clear through Loop, which
    # rereads LIT and control each time; the run's own LIT writes go through
    # Loop.transition, so only they move the grant's LIT basis. The grant also names
    # the run's work, so the run selects only its granted ticket and every effect
    # names the ticket it acts on. Without a journal nothing is declared, so every
    # other dirty checkout holds this run.
    journal = config.get("loop_state")
    if journal and not all(
        type(config.get(key)) is str for key in ("admission", "loop_control")
    ):
        raise ValueError("loop_state requires the admission and loop_control it clears against")
    store = config.get("artifact_root", DEFAULT_ROOT)

    def loop():
        return Loop(journal, config["loop_control"], NativeLit(cwd, store))

    scoped = dict(
        ownership=lambda: journal_ownership(journal),
        selection=lambda adapter: "\n".join(loop().selection(config["admission"])),
        clearance=lambda operation, *tickets: loop().check(
            config["admission"], operation, *tickets
        ),
        transition=lambda operation, ticket, write: loop().transition(
            config["admission"], operation, ticket, write
        ),
    ) if journal else {}
    return LocalAdapter(
        cwd,
        config.get("verify_argv", ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]),
        timeout=min(seconds, 300),
        artifact_root=store,
        **scoped,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "run"])
    parser.add_argument("--config", type=Path, help="trusted local JSON: worker_argv, verify_argv, goal, loop_state, loop_control, admission")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--tickets", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--context-bytes", type=int, default=65536, help="maximum worker input size; hand off before exceeding")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text()) if args.config else {}
        adapter = adapter_for(config, args.cwd, args.seconds)
        if args.mode == "plan":
            issue, ancestors = select_ticket(adapter.export(), adapter.next())
            print(json.dumps(route(issue, ancestors) if issue else {"stop_reason": "queue-empty"}, indent=2))
            return 0
        if not args.config or not isinstance(config.get("goal"), str) or not config["goal"].strip():
            raise ValueError("run requires a trusted worker config and goal")
        store=config.get('artifact_root',DEFAULT_ROOT)
        worker = (CodexWorker(adapter.cwd, min(args.seconds, 900), artifact_root=store) if config.get("worker") == "codex"
                  else ProcessWorker(config["worker_argv"], adapter.cwd, min(args.seconds, 900), artifact_root=store))
        state = adapter.common_dir() / "orchestration"
        with Lease(state / "runner.lock"):
            handoff = state / "handoff.json"
            prior = read_handoff(handoff) if handoff.exists() else None
            if prior and prior["stop_reason"] == "interrupted":
                raise Stop("recovery-required: inspect previous handoff and LIT/Git before retry")
            result = continue_work(adapter, worker, handoff, goal=config["goal"], limit=args.tickets, seconds=args.seconds, prior=prior, context_bytes=args.context_bytes)
            print(json.dumps(result, indent=2))
        return 0 if result["stop_reason"] in {"ticket-limit", "queue-empty"} else 2
    except (Stop, ValueError, KeyError, OSError) as error:
        print(f"continuation stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
