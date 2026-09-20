"""Repository-only health surface. No network listener or external executor."""
import argparse
import json
import sys


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer required")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["health"])
    parser.parse_args()
    print(json.dumps({"version": 1, "service": "control-plane", "state": "ok",
                      "mode": "simulation", "external_execution": False}, sort_keys=True))
    return 0
