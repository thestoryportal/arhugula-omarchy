"""Bounded supervisor. Models implement one unit; LIT and Git remain authorities."""
import fcntl
import json
import os
from pathlib import Path
import time

from .handoff import validate, write_handoff
from .routing import index_backlog, is_complete, route


class Stop(RuntimeError):
    pass


class Lease:
    """Repository-wide exclusive kernel lease; no stale TTL takeover of a writer."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise Stop("lease-conflict") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def select_ticket(data, next_output):
    issues, parents, ancestors = index_backlog(data)
    identifiers = [line.split()[0] for line in next_output.splitlines() if line.split() and line.split()[0] in issues]
    if not identifiers:
        if next_output.strip():
            raise Stop("no-workable-ticket")
        return None, []
    if len(set(identifiers)) != 1:
        raise Stop("ambiguous-lit-next")
    current = issues[identifiers[0]]
    while True:
        children = [issues[child] for child, parent in parents.items() if parent == current["id"]]
        unfinished = [i for i in children if i.get("status") != "closed"
                      and not i.get("archived_at") and not i.get("deleted_at")]
        if children and not unfinished:
            raise Stop("container-needs-reconciliation")
        if not unfinished:
            break
        current = min(unfinished, key=lambda i: (i.get("rank", ""), i["id"]))
    if current.get("status") == "closed" or current.get("archived_at") or current.get("deleted_at"):
        raise Stop("stale-lit-next")
    chain = ancestors[current["id"]]
    scope = {current["id"], *(i["id"] for i in chain)}
    # LIT export v2 stores blocked issue as src and prerequisite as dst.
    for relation in data.get("relations", []):
        if relation["type"] == "blocks" and relation["src_id"] in scope:
            dependency = issues.get(relation["dst_id"])
            if dependency is None or not is_complete(relation["dst_id"], issues, parents):
                raise Stop("blocked")
    return current, chain


def receipt_files(receipt):
    if not isinstance(receipt, dict):
        raise Stop("invalid-worker-receipt")
    if receipt.get("stop_reason"):
        if not isinstance(receipt["stop_reason"], str):
            raise Stop("invalid-worker-receipt")
        raise Stop(receipt["stop_reason"])
    files = receipt.get("files")
    if (not isinstance(files, list) or not files or not isinstance(receipt.get("summary"), str)
            or not receipt["summary"].strip() or not isinstance(receipt.get("risks"), list)
            or any(not isinstance(r, str) or not r.strip() for r in receipt["risks"])):
        raise Stop("invalid-worker-receipt")
    for name in files:
        if (not isinstance(name, str) or not name or "\x00" in name or "\n" in name
                or Path(name).is_absolute() or any(part in {"..", ".git", ".worktrees"} for part in Path(name).parts)
                or name.startswith("-") or str(Path(name)) in {".", ""}):
            raise Stop("invalid-worker-receipt")
    return files


def revalidate(adapter, original, ancestors, assignment):
    current, current_ancestors = select_ticket(adapter.export(), original["id"] + " active")
    if current is None or current.get("status") != "in_progress":
        raise Stop("ticket-state-changed")
    rerouted = route(current, current_ancestors)
    if rerouted["decision"] != "ready":
        raise Stop(rerouted["stop_reason"])
    if any(rerouted[k] != assignment[k] for k in ("model", "effort", "role", "capability")):
        raise Stop("assignment-changed")
    if ([i["id"] for i in current_ancestors] != [i["id"] for i in ancestors]
            or any(current.get(k) != original.get(k) for k in ("title", "description", "issue_type"))):
        raise Stop("ticket-scope-changed")
    adapter.assert_claim(original["id"])


def bounded_context(context, handoff_path, ceiling):
    if len(json.dumps(context).encode("utf-8")) <= ceiling:
        return context
    # Full history remains in the durable record; a fresh worker receives an
    # explicit reference rather than an ever-growing prompt argument.
    compact = {**context, "completed_work": context["completed_work"][-3:],
               "verification": context["verification"][-2:],
               "history_reference": str(handoff_path),
               "history_counts": {k: len(context[k]) for k in ("completed_work", "verification", "risks")}}
    if len(json.dumps(compact).encode("utf-8")) <= ceiling:
        return compact
    compact.update(completed_work=[], verification=[], risks=[])
    if len(json.dumps(compact).encode("utf-8")) > ceiling:
        raise Stop("context-limit")
    return compact


def continue_work(adapter, worker, handoff_path, *, goal, limit=1, seconds=1800, prior=None, context_bytes=65536):
    """Caller must hold Lease through this loop and every child process lifetime."""
    if type(limit) is not int or not 1 <= limit <= 100 or seconds <= 0 or type(context_bytes) is not int or context_bytes < 1024:
        raise ValueError("finite positive bounds required (1..100 tickets)")
    began = time.monotonic()
    record = dict(version=1, active_ticket="none", parent_epic="none", branch="uninspected",
                  worktree=str(getattr(adapter, "cwd", Path.cwd())), model="gpt-6-astra",
                  effort="high", role="implement", goal=goal, completed_work=[],
                  verification=[], risks=[], next_ticket=None, stop_reason=None,
                  worker_stop=False, recovery_required=False)
    if prior is not None:
        validate(prior)
        for field in ("completed_work", "verification", "risks"):
            record[field] = list(prior[field])
        for field in ("active_ticket", "parent_epic", "branch", "worktree", "model", "effort", "role", "next_ticket"):
            record[field] = prior[field]
        if "resolutions" in prior:
            record["resolutions"] = list(prior["resolutions"])
    try:
        if prior is not None and prior.get("recovery_required"):
            record["recovery_required"] = True
            raise Stop("recovery-required")
        if prior is not None and prior.get("worker_stop"):
            record.update(active_ticket=prior["active_ticket"], parent_epic=prior["parent_epic"],
                          branch=prior["branch"], worktree=prior["worktree"],
                          next_ticket=prior["next_ticket"], worker_stop=True,
                          model=prior["model"], effort=prior["effort"], role=prior["role"])
            raise Stop(prior["stop_reason"] or "worker-resolution-required")
        if prior is not None and prior["stop_reason"] == "interrupted":
            record["recovery_required"] = True
            raise Stop("recovery-required")
        pending = adapter.next()
        for iteration in range(limit):
            if time.monotonic() - began >= seconds:
                raise Stop("time-limit")
            issue, ancestors = select_ticket(adapter.export(), pending)
            if issue is None:
                raise Stop("queue-empty")
            identifier = issue["id"]
            record.update(active_ticket=identifier, next_ticket=identifier,
                          parent_epic=next((i["id"] for i in ancestors if i.get("issue_type") == "epic"), identifier))
            assignment = route(issue, ancestors)
            if assignment["decision"] != "ready":
                raise Stop(assignment["stop_reason"])
            record.update(model=assignment["model"], effort=assignment["effort"], role=assignment["role"])
            state = adapter.inspect()
            if prior is not None and prior["branch"] != "uninspected" and (state["worktree"] != prior["worktree"] or state["branch"] != prior["branch"]):
                raise Stop("handoff-worktree-mismatch")
            record.update(branch=state["branch"], worktree=state["worktree"])
            # Persist intent before claim: interruption never looks like a closed unit.
            record["stop_reason"] = "interrupted"
            write_handoff(handoff_path, record)
            adapter.start(identifier)
            epic_body = adapter.show(record["parent_epic"])
            ticket_body = adapter.show(identifier)
            adapter.inspect(expected_head=state["head"])
            revalidate(adapter, issue, ancestors, assignment)
            context = {**record, "stop_reason": None, "ticket_body": ticket_body, "epic_body": epic_body,
                       "supervisor": "Implement only this unit. Return JSON files/summary/risks/stop_reason. "
                       "Do not claim, close, commit, push, launch other agents or change live configuration. "
                       "Supervisor owns LIT/Git transitions and fresh verification."}
            context = bounded_context(context, handoff_path, context_bytes)
            record["recovery_required"] = True
            receipt = worker(context)
            if isinstance(receipt, dict) and receipt.get("stop_reason"):
                record["recovery_required"] = False
                record["worker_stop"] = True
                summary = receipt.get("summary")
                if isinstance(summary, str) and summary.strip():
                    record["risks"].append("Worker stop: " + summary)
                risks = receipt.get("risks")
                if isinstance(risks, list):
                    record["risks"].extend(r for r in risks if isinstance(r, str) and r.strip())
            files = receipt_files(receipt)
            record["recovery_required"] = False
            record["risks"].extend(receipt["risks"])
            adapter.inspect(expected_head=state["head"], allowed=files)
            revalidate(adapter, issue, ancestors, assignment)
            for attempt in range(2):
                passed, evidence = adapter.verify()
                record["verification"].append(f"{identifier}: {evidence}")
                if passed:
                    break
            else:
                raise Stop("verification-failed-twice")
            adapter.inspect(expected_head=state["head"], allowed=files)
            revalidate(adapter, issue, ancestors, assignment)
            adapter.comment(identifier, "Verified: " + record["verification"][-1] + "\nDecision/handoff: " + receipt["summary"])
            record["recovery_required"] = True
            write_handoff(handoff_path, record)
            commit = adapter.commit(identifier, files)
            record["completed_work"].append(f"{identifier}: {commit}: {receipt['summary']}")
            # Crash between commit and done leaves enough evidence for recovery.
            write_handoff(handoff_path, record)
            adapter.inspect(expected_head=commit)
            revalidate(adapter, issue, ancestors, assignment)
            adapter.done(identifier)
            record.update(stop_reason=None, next_ticket=None, recovery_required=False)
            write_handoff(handoff_path, record)
            adapter.comment(identifier, f"Committed {commit}; durable handoff {handoff_path}")
            pending = adapter.next()
            upcoming, _ = select_ticket(adapter.export(), pending)
            record["next_ticket"] = upcoming["id"] if upcoming else None
            write_handoff(handoff_path, record)
        raise Stop("ticket-limit")
    except Stop as error:
        record["stop_reason"] = str(error)
    except Exception as error:
        record["stop_reason"] = "adapter-error"
        record["risks"].append(f"{type(error).__name__}: {error}")
    write_handoff(handoff_path, record)
    if record["active_ticket"] != "none":
        try:
            adapter.comment(record["active_ticket"], "Stopped: " + record["stop_reason"] + f"; handoff {handoff_path}")
        except Exception:
            # The durable record remains the recovery path if LIT is unavailable.
            pass
    return record
