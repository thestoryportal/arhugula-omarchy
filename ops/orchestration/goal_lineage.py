"""Retain actual thread-local goal receipts and derive lifetime accounting."""

import argparse
import hashlib
import json
from pathlib import Path

from .artifacts import file_binding
from .continuation import Lease
from .records import atomic_json


def goal_observation(raw):
    observation = raw.get("tool_result", raw)
    goal = observation["goal"]
    session = (
        goal["threadId"]
        if goal is not None
        else raw.get("session_id", raw.get("native_store", {}).get("thread_id"))
    )
    if not isinstance(session, str) or not session:
        raise ValueError("session-bound actual goal observation required")
    if goal is None and (
        set(("goal", "remainingTokens", "completionBudgetReport")) - observation.keys()
        or observation["remainingTokens"] is not None
        or observation["completionBudgetReport"] is not None
    ):
        raise ValueError("actual absent goal observation required")
    return session, observation


class GoalLineage:
    def __init__(self, path):
        self.path = Path(path)

    def _existing(self, deadline):
        if not self.path.exists():
            raise ValueError("original goal ledger required for absent native goal")
        state = json.loads(self.path.read_text())
        if state["deadline"] != deadline or state["token_budget"] is not None:
            raise ValueError("goal contract changed")
        for evidence in state["receipts"]:
            if file_binding(evidence["path"]) != evidence:
                raise ValueError("goal receipt changed")
        return state

    def record_absence(self, receipt, deadline):
        session, observation = goal_observation(json.loads(Path(receipt).read_text()))
        if observation["goal"] is not None:
            raise ValueError("actual absent goal observation required")
        bound = file_binding(receipt)
        with Lease(self.path.with_suffix(".lock")):
            state = self._existing(deadline)
            # [LAW:one-source-of-truth] Keep the original contract and actual usage;
            # absent thread-local goals contribute evidence, never invented counters.
            item = {"session_id": session, "receipt": bound}
            absent = state.setdefault("absent_goals", [])
            if item not in absent:
                absent.append(item)
            if bound not in state["receipts"]:
                state["receipts"].append(bound)
            atomic_json(self.path, state)
            return state

    def record(self, receipt, deadline):
        raw = json.loads(Path(receipt).read_text())
        goal = raw["goal"]
        if (
            not goal
            or raw.get("remainingTokens") is not None
            or goal.get("tokenBudget") is not None
        ):
            raise ValueError("original unbounded goal contract required")
        contract = {
            "objective": goal["objective"],
            "deadline": deadline,
            "token_budget": None,
        }
        usage = {k: goal[k] for k in ("tokensUsed", "timeUsedSeconds")}
        if any(type(v) is not int or v < 0 for v in usage.values()):
            raise ValueError("invalid actual goal usage")
        bound = file_binding(receipt)
        with Lease(self.path.with_suffix(".lock")):
            state = (
                self._existing(deadline)
                if self.path.exists()
                else {"version": 1, **contract, "threads": {}, "receipts": []}
            )
            if any(state[k] != v for k, v in contract.items()):
                raise ValueError("goal contract changed")
            old = state["threads"].get(
                goal["threadId"], dict(tokensUsed=0, timeUsedSeconds=0)
            )
            if any(usage[k] < old[k] for k in usage):
                raise ValueError("actual goal usage regressed")
            state["threads"][goal["threadId"]] = usage
            if bound not in state["receipts"]:
                state["receipts"].append(bound)
            state["tokens_used"] = sum(
                v["tokensUsed"] for v in state["threads"].values()
            )
            state["seconds_used"] = sum(
                v["timeUsedSeconds"] for v in state["threads"].values()
            )
            state["objective_sha256"] = hashlib.sha256(
                contract["objective"].encode()
            ).hexdigest()
            atomic_json(self.path, state)
            return state

    def record_recovery(self, receipt, deadline):
        """Retain a different native repair objective without relabeling its usage."""
        session, observation = goal_observation(json.loads(Path(receipt).read_text()))
        goal = observation['goal']
        if goal is None or observation.get('remainingTokens') is not None or goal.get('tokenBudget') is not None:
            raise ValueError('actual unbounded recovery goal required')
        with Lease(self.path.with_suffix('.lock')):
            state = self._existing(deadline)
            # [LAW:one-source-of-truth] Separate objectives retain separate actual receipts and counters.
            item = {'session_id': session, 'receipt': file_binding(receipt)}
            records = state.setdefault('recovery_goals', [])
            if item not in records:
                records.append(item)
            atomic_json(self.path, state)
            return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--deadline", required=True)
    args = parser.parse_args()
    result = GoalLineage(args.ledger).record(args.receipt, args.deadline)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("tokens_used", "seconds_used", "deadline", "objective_sha256")
            }
        )
    )
