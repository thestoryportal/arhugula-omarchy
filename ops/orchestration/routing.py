"""Versioned, read-only model routing for LIT export v2 (Python standard library)."""
import json
import re
import sys

HIGH = frozenset({"architecture", "contracts", "security", "cross-cutting",
                  "session-lifecycle", "model-routing", "orchestration",
                  "debugging", "high-risk-review"})
BOUNDED = frozenset({"exploration", "inventory", "tests", "fixtures",
                     "documentation", "bounded-implementation", "validation",
                     "independent-review"})
MODELS = {"astra": ("gpt-6-astra", "high"), "terra": ("gpt-5.6-terra", "medium")}
STOPS = ("hil-required", "needs-design", "privileged", "destructive", "external-credentials", "external-network")


def route(issue, ancestors=()):
    """Metadata on the leaf is explicit; ancestor stop/security labels constrain it."""
    labels = set(issue.get("labels") or [])
    inherited = set().union(*(set(a.get("labels") or []) for a in ancestors))
    result = dict(version=1, ticket=issue["id"], model=None, effort=None,
                  role=None, capability=None, decision="stop", stop_reason=None,
                  source=None)

    def stop(reason):
        result["stop_reason"] = reason
        return result

    for marker in STOPS:
        if marker in labels | inherited:
            return stop(marker)
    fields = {}
    allowed = {"model": set(MODELS), "effort": {"high", "medium"},
               "role": {"implement", "review", "validate", "explore"},
               "capability": HIGH | BOUNDED}
    for key, values in allowed.items():
        found = {label.split(":", 1)[1] for label in labels if label.startswith(key + ":")}
        if len(found) > 1 or not found <= values:
            return stop("routing-conflict")
        fields[key] = next(iter(found), None)
    capability = fields["capability"]
    source = "explicit" if capability else "default"
    # Security is a floor even for an explicitly bounded task. Other inherited
    # capability/model labels do not silently reclassify a whole epic.
    if "security" in labels | inherited or "high-risk" in labels | inherited:
        capability, source = "security", "risk-floor"
    if not capability:
        high_labels = labels & HIGH
        if len(high_labels) > 1:
            return stop("routing-conflict")
        if high_labels:
            capability = sorted(high_labels)[0]
        elif "validation" in labels:
            capability = "validation"
        elif "session-continuity" in labels:
            capability = "session-lifecycle"
        elif "workflow" in labels or "circle-back" in labels:
            capability = "orchestration"
        else:
            title = issue.get("title", "").lower()
            for pattern, candidate in [
                (r"contract|schema|protocol", "contracts"),
                (r"security|permission|authenticat|policy|redact|sandbox", "security"),
                (r"architecture|stack|boundar", "architecture"),
                (r"lifecycle|session|handoff", "session-lifecycle"),
                (r"model.routing", "model-routing"),
                (r"orchestrat|continuation|circle.back|reconcile", "orchestration"),
                (r"inventory|discover", "inventory"),
                (r"\btest|fixture|replay", "tests"),
                (r"documentation|\bdocs\b", "documentation"),
                (r"explor|inspect", "exploration"),
                (r"validat|dry.run", "validation"),
                (r"review", "independent-review"),
            ]:
                if re.search(pattern, title):
                    capability = candidate
                    break
    if capability is None:
        return stop("routing-ambiguous")
    model_class = "astra" if capability in HIGH else "terra"
    # Explicit Astra may promote bounded work; Terra cannot demote high risk.
    if fields["model"]:
        if model_class == "astra" and fields["model"] == "terra":
            return stop("routing-conflict")
        model_class = fields["model"]
    model, effort = MODELS[model_class]
    if fields["effort"] and fields["effort"] != effort:
        return stop("routing-conflict")
    role = fields["role"] or ({"independent-review": "review", "high-risk-review": "review",
                               "validation": "validate", "exploration": "explore"}.get(capability, "implement"))
    result.update(model=model, effort=effort, role=role, capability=capability, source=source)
    if "autonomous-safe" not in labels:
        return stop("autonomy-unclassified")
    result["decision"] = "ready"
    return result


def index_backlog(data):
    if data.get("version") != 2:
        raise ValueError("unsupported LIT export version")
    issues = {i["id"]: i for i in data["issues"]}
    if len(issues) != len(data["issues"]):
        raise ValueError("duplicate issue id")
    parents = {}
    for relation in data.get("relations", []):
        if relation["type"] != "parent-child":
            continue
        child, parent = relation["src_id"], relation["dst_id"]
        if child not in issues or parent not in issues or child in parents:
            raise ValueError("invalid parent relationship")
        parents[child] = parent
    ancestors = {}
    for identifier in issues:
        chain, seen, current = [], {identifier}, identifier
        while current in parents:
            current = parents[current]
            if current in seen:
                raise ValueError("parent cycle")
            seen.add(current)
            chain.append(issues[current])
        ancestors[identifier] = chain
    return issues, parents, ancestors


def route_backlog(data):
    issues, parents, ancestors = index_backlog(data)
    containers = set(parents.values())
    leaves = [i for i in issues.values() if i["id"] not in containers
              and i.get("issue_type") != "epic" and i.get("status") != "closed"
              and not i.get("archived_at") and not i.get("deleted_at")]
    results = []
    for i in sorted(leaves, key=lambda i: (i.get("rank", ""), i["id"])):
        result = route(i, ancestors[i["id"]])
        scope = {i["id"], *(a["id"] for a in ancestors[i["id"]])}
        blocked = set()
        for relation in data.get("relations", []):
            if relation["type"] == "blocks":
                if relation["src_id"] not in issues or relation["dst_id"] not in issues:
                    raise ValueError("invalid dependency relationship")
                if relation["src_id"] in scope and not is_complete(relation["dst_id"], issues, parents):
                    blocked.add(relation["dst_id"])
        result["blocked_by"] = sorted(blocked)
        if blocked and result["decision"] == "ready":
            result.update(decision="stop", stop_reason="blocked")
        results.append(result)
    return results


def is_complete(identifier, issues, parents):
    """LIT exports epic completion through children, not an epic status field."""
    issue = issues[identifier]
    if issue.get("status") == "closed":
        return True
    if issue.get("issue_type") != "epic":
        return False
    children = [child for child, parent in parents.items() if parent == identifier
                and not issues[child].get("archived_at") and not issues[child].get("deleted_at")]
    return bool(children) and all(is_complete(child, issues, parents) for child in children)


def main():
    try:
        routes = route_backlog(json.load(sys.stdin))
        json.dump({"version": 1, "routes": routes}, sys.stdout, indent=2, sort_keys=True)
        print()
        return 0
    except (ValueError, KeyError, TypeError) as error:
        print(f"routing input rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
