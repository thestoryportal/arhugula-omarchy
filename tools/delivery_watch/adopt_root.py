"""Adopt the calling Codex successor without changing peers or admission policy."""

import argparse
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID


def successor_control(control, session_id, transcript, metadata):
    # [LAW:parse-dont-validate] Only a native session identity can replace a route.
    UUID(session_id)
    if (
        metadata.get("type") != "session_meta"
        or metadata["payload"]["id"] != session_id
    ):
        raise ValueError("transcript does not belong to the calling native session")
    roots = [s for s in control["sessions"] if s["role"] == "buford"]
    if len(roots) != 1 or roots[0]["kind"] != "codex":
        raise ValueError("control must have one Codex Buford role")
    if control["notification_thread"] != roots[0]["session_id"]:
        raise ValueError("notification route and Buford identity disagree")
    if any(
        s["session_id"] == session_id
        for s in control["sessions"]
        if s["role"] != "buford"
    ):
        raise ValueError("calling session already belongs to another role")
    # [LAW:one-source-of-truth] Policy and peer identities come from current control.
    return {
        **control,
        "notification_thread": session_id,
        "sessions": [
            {**s, "session_id": session_id, "transcript": str(transcript)}
            if s["role"] == "buford"
            else s
            for s in control["sessions"]
        ],
    }


def adopt(control_path, transcript_path, session_id):
    control_path = Path(control_path).resolve()
    transcript_path = Path(transcript_path).resolve(strict=True)
    original = control_path.read_bytes()
    control = json.loads(original)
    with transcript_path.open() as stream:
        metadata = json.loads(stream.readline())
    updated = successor_control(control, session_id, transcript_path, metadata)
    # [LAW:effects-at-boundaries] Readers see either complete control revision.
    with tempfile.NamedTemporaryFile(dir=control_path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(updated, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.chmod(control_path.stat().st_mode & 0o777)
        if control_path.read_bytes() != original:
            raise ValueError("control changed during adoption; no route was replaced")
        os.replace(temporary, control_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "previous": control["notification_thread"],
        "current": session_id,
        "transcript": str(transcript_path),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("transcript", type=Path)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                adopt(args.control, args.transcript, os.environ["CODEX_THREAD_ID"])
            )
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"root adoption refused: {error}\n")


if __name__ == "__main__":
    main()
