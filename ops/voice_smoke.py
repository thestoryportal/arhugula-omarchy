"""Dry-run by default; an explicitly approved one-shot menu smoke via VM policy."""
import argparse
import json

from runtime.contracts import decode, encode
from runtime.core import ControlPlane, Outcome
from runtime.journal import MemoryJournal, SQLiteJournal
from runtime.voice.menu import OmarchyMenuExecutor


def build_plane(executor, journal=None):
    journal = journal if journal is not None else MemoryJournal()
    capability = decode({"kind": "capability", "version": 1, "capability_id": "menu.open",
                         "catalog_version": 1, "enabled": True, "risk": "safe",
                         "arguments": {"name": "string"}, "provenance": "approved-menu-smoke"})
    policy = decode({"kind": "policy", "version": 1, "policy_id": "smoke", "revision": 1,
                     "enabled": True, "allowed_capabilities": ["menu.open"], "confirmation_required": []})
    profile = decode({"kind": "profile", "version": 1, "profile_id": "smoke", "policy_id": "smoke",
                      "enabled": True, "voice_enabled": False})
    command = decode({"kind": "command", "version": 1, "command_id": "approved-menu-smoke-v1",
                      "correlation_id": "approved-menu-smoke-v1", "capability_id": "menu.open",
                      "catalog_version": 1, "requested_at_ms": 0, "arguments": {"name": "main"},
                      "context": {"session_id": "approved-menu-smoke", "profile_id": "smoke",
                                  "lane_id": None, "agent_id": None, "source": "terminal",
                                  "provider_id": None, "model_version": None,
                                  "provenance": "explicit-human-smoke-approval", "sensitivity": "private"}})
    return ControlPlane([capability], policy, executor, journal, profile=profile), command, journal


def smoke(*, live=False, journal_path=None):
    """Return (result, owned journal); caller closes the journal after inspection."""
    if type(live) is not bool or (live and journal_path is None):
        raise ValueError("live smoke requires explicit mode and a durable journal path")
    journal = SQLiteJournal(journal_path) if live else MemoryJournal()
    try:
        executor = OmarchyMenuExecutor() if live else (lambda _: Outcome("success", {"mode": "simulation"}))
        plane, command, _ = build_plane(executor, journal)
        return plane.dispatch(command), journal
    except Exception:
        journal.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="requires separate human approval; opens the root menu once")
    parser.add_argument("--journal", help="required persistent database path for the approved live smoke")
    args = parser.parse_args()
    try:
        result, journal = smoke(live=args.live, journal_path=args.journal)
        try:
            print(json.dumps(encode(result), sort_keys=True))
            return 0 if result.status == "success" else 2
        finally:
            journal.close()
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
