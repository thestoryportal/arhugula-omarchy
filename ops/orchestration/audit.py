"""Review/materialize explicit routing metadata via the LIT CLI only."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

from .routing import HIGH, BOUNDED, index_backlog, route_backlog


def materialize(data, metadata):
    issues, _, ancestors = index_backlog(data)
    if metadata.get("version") != 1 or not isinstance(metadata.get("capabilities"), dict):
        raise ValueError("unsupported metadata manifest")
    for identifier, capability in metadata["capabilities"].items():
        if identifier not in issues or capability not in HIGH | BOUNDED:
            raise ValueError(f"unknown issue/capability: {identifier}: {capability}")
    updated = copy.deepcopy(data)
    for issue in updated["issues"]:
        capability = metadata["capabilities"].get(issue["id"])
        if capability is None:
            continue
        labels = set(issue.get("labels") or [])
        inherited = set().union(*(set(i.get("labels") or []) for i in ancestors[issue["id"]]))
        high = capability in HIGH or bool((labels | inherited) & {"security", "high-risk"})
        model, effort = ("astra", "high") if high else ("terra", "medium")
        role = {"independent-review": "review", "high-risk-review": "review", "validation": "validate", "exploration": "explore"}.get(capability, "implement")
        labels = {x for x in labels if not x.startswith(("capability:", "model:", "effort:", "role:"))}
        labels.update({f"capability:{capability}", f"model:{model}", f"effort:{effort}", f"role:{role}"})
        issue["labels"] = sorted(labels)
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path(__file__).with_name("backlog-metadata.json"))
    parser.add_argument("--apply", action="store_true", help="explicitly materialize reviewed labels through lit update")
    args = parser.parse_args()
    try:
        original = json.loads(subprocess.run(["lit", "export"], check=True, capture_output=True, text=True).stdout)
        updated = materialize(original, json.loads(args.metadata.read_text()))
        before = {i["id"]: i for i in original["issues"]}
        patches = [{"id": i["id"], "labels": i["labels"]} for i in updated["issues"] if i.get("labels") != before[i["id"]].get("labels")]
        if args.apply:
            for patch in patches:
                subprocess.run(["lit", "update", patch["id"], "--labels", ",".join(patch["labels"])], check=True, capture_output=True, text=True)
        print(json.dumps({"version": 1, "applied": args.apply, "patches": patches, "routes": route_backlog(updated)}, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"audit stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
