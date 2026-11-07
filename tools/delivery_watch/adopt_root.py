"""Adopt the calling Codex successor without changing peers or admission policy."""

import argparse
import fcntl
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


def update_control(control_path, transform):
    """Serialize control writers on a stable lock, including atomic replacements."""
    control_path = Path(control_path).resolve()
    # [LAW:single-enforcer] Every writer uses this lock, never the replaced inode.
    with control_path.with_suffix(control_path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        control = json.loads(control_path.read_bytes())
        updated = transform(control)
        with tempfile.NamedTemporaryFile(
            dir=control_path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                os.fchmod(stream.fileno(), control_path.stat().st_mode & 0o777)
                stream.write((json.dumps(updated, indent=2) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, control_path)
                # [LAW:no-silent-failure] Success includes durable directory metadata.
                directory = os.open(control_path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
    return control, updated


def adopt(control_path, transcript_path, session_id):
    transcript_path = Path(transcript_path).resolve(strict=True)
    with transcript_path.open() as stream:
        metadata = json.loads(stream.readline())
    control, _ = update_control(
        control_path,
        lambda current: successor_control(
            current, session_id, transcript_path, metadata
        ),
    )
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
