"""Stream raw subprocess output to private disk files; emit bounded receipts.

A receipt is what a model reads, so as printed it never exceeds
MODEL_RECEIPT_LIMIT bytes. Everything it summarizes stays complete on disk, bound
by size and digest: the argv, both streams and every finding line. Consumers read
those through assignment_packet's hash-verified slices; `summary_truncated` says
when the summary alone is not the whole finding set.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from .records import atomic_json, private_directory, sync_directory
from .processes import process_stats

DEFAULT_ROOT = Path("/mnt/mac/arhugula-artifacts")
MOUNTINFO = Path("/proc/self/mountinfo")
MODEL_RECEIPT_LIMIT = 16 * 1024
# The limit caps a receipt; a summary normally needs far less of it.
SUMMARY_BUDGET = 4096
# Published numbers are wider than the zeros measured before launch; this covers them.
NUMERIC_SLACK = 256
FINDING = re.compile(rb"error|fail|traceback|passed|ran \d+|^OK$", re.I)
TAIL_HEADER = "\n[bounded tail]\n"


def require_mac_share(mountinfo):
    for line in mountinfo.splitlines():
        left, right = line.split(" - ", 1)
        fields, filesystem = left.split(), right.split()
        if (
            fields[4] == "/mnt/mac"
            and "rw" in fields[5].split(",")
            and filesystem[:2] == ["9p", "mac"]
        ):
            return
    raise ValueError("writable Mac share is unavailable; no guest-disk fallback")


def store_kind(root):
    """Where a receipt's evidence lives; only the proved Mac share is durable."""
    if root == DEFAULT_ROOT or DEFAULT_ROOT in root.parents:
        require_mac_share(MOUNTINFO.read_text())
        return "mac_share"
    # [LAW:one-source-of-truth] An explicit root is a test store and its receipt says
    # so; it can never stand in for production evidence.
    return "test_only"


def private_file(path):
    stream = path.open("xb")
    os.chmod(path, 0o600)
    return stream


def file_binding(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(Path(path).absolute()),
        "bytes": Path(path).stat().st_size,
        "sha256": digest.hexdigest(),
    }


def write_findings(paths, findings):
    """Copy every finding line of `paths` into `findings`; return (count, output tail)."""
    count, tail = 0, b""
    with private_file(findings) as stream:
        for path in paths:
            with path.open("rb") as source:
                # [LAW:carrying-cost] Even one compiler line is read in bounded chunks.
                for chunk in iter(lambda: source.readline(1024), b""):
                    if FINDING.search(chunk):
                        stream.write(chunk if chunk.endswith(b"\n") else chunk + b"\n")
                        count += 1
                    tail = (tail + chunk)[-MODEL_RECEIPT_LIMIT:]
        stream.flush()
        os.fsync(stream.fileno())
    return count, tail


def encoded(text):
    """Bytes `text` adds to a printed receipt: its JSON string form, quotes excluded."""
    return len(json.dumps(text)) - 2


def fit(text, budget, *, keep_head):
    """The longest head (or tail) of `text` whose encoding fits in `budget` bytes."""

    def part(length):
        return text[:length] if keep_head else text[len(text) - length :]

    # Escapes widen a character to as many as 12 bytes, so search on the encoding.
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if encoded(part(middle)) <= budget else (low, middle - 1)
    return part(low)


def summary(findings, findings_bytes, tail, budget):
    """The first findings plus the output tail within `budget` encoded bytes, and
    whether the shown findings omit any of the complete set on disk."""
    with findings.open("rb") as stream:
        head = stream.read(budget).decode("utf-8", "replace")
    shown = fit(head, (budget - encoded(TAIL_HEADER)) // 2, keep_head=True)
    rest = budget - encoded(TAIL_HEADER) - encoded(shown)
    latest = fit(tail.decode("utf-8", "replace"), rest, keep_head=False)
    complete = findings_bytes <= budget and shown == head
    return shown + TAIL_HEADER + latest, not complete


def group_active(pgid):
    return any(proc.group == pgid and proc.state != 'Z' for proc in process_stats())


def capture(argv, cwd, *, root=DEFAULT_ROOT, timeout=300, input=None):
    if (
        not argv
        or any(not isinstance(x, str) or not x or "\x00" in x for x in argv)
        or timeout <= 0
    ):
        raise ValueError("literal argv and positive timeout required")
    root = Path(root).absolute()
    # The store is proved before anything runs; there is no guest-disk fallback.
    store = store_kind(root)
    root = private_directory(root)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    paths = [directory / "stdout.log", directory / "stderr.log"]
    argv_path, findings_path = directory / "argv.json", directory / "findings.log"
    # Each variable-size part of a run is a bound file, so the receipt stays fixed-size.
    bound = dict(argv=argv_path, stdout=paths[0], stderr=paths[1], findings=findings_path)

    def publishable(exit, terminal, group, elapsed, bindings, count, text, truncated):
        return dict(
            version=2,
            store=store,
            cwd=str(Path(cwd).absolute()),
            exit=exit,
            terminal=terminal,
            owned_process_group=group,
            elapsed_seconds=elapsed,
            **bindings,
            findings_count=count,
            summary=text,
            summary_truncated=truncated,
            receipt=str(directory / "receipt.json"),
        )

    unmeasured = {name: dict(path=str(path), bytes=0, sha256="0" * 64) for name, path in bound.items()}
    fixed = json.dumps(publishable(0, "descendants_active", 0, 0.0, unmeasured, 0, "", False))
    # [LAW:no-ambient-temporal-coupling] The bound is proved before launch, while a
    # refusal still has no effect.
    if len(fixed) + NUMERIC_SLACK + encoded(TAIL_HEADER) > MODEL_RECEIPT_LIMIT:
        raise ValueError("receipt paths leave no room within the model receipt bound")
    with private_file(argv_path) as stream:
        stream.write(json.dumps(argv).encode())
        stream.flush()
        os.fsync(stream.fileno())
    began = time.monotonic()
    launch_error = None
    terminal, code = "exited", None
    process_id = None
    # [LAW:effects-at-boundaries] No pipe buffers or raw logs enter model context.
    with private_file(paths[0]) as stdout, private_file(paths[1]) as stderr:
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            process_id = process.pid
            try:
                process.communicate(
                    input=input.encode() if isinstance(input, str) else input,
                    timeout=timeout,
                )
                code = process.returncode
            except BaseException as error:
                # This capture owns this process group, never an inherited worker.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                terminal = (
                    "timeout"
                    if isinstance(error, subprocess.TimeoutExpired)
                    else "interrupted"
                )
                code = 124 if terminal == "timeout" else 130
                if terminal == "interrupted":
                    launch_error = error
            if group_active(process.pid):
                # [LAW:no-ambient-temporal-coupling] A parent exit is not group release.
                # [LAW:no-ambient-temporal-coupling] A census cannot retain a
                # process group; ESRCH at the signal boundary means it released.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                else:
                    if terminal == "exited":
                        terminal, code = "descendants_active", 125
                deadline = time.monotonic() + 5
                while group_active(process.pid):
                    if time.monotonic() >= deadline:
                        raise OSError(
                            "owned subprocess group did not terminate; logs remain unsealed"
                        )
                    time.sleep(0.01)
        except OSError as error:
            terminal, launch_error = "launch_failed", error
            stderr.write(str(error).encode())
        for stream in (stdout, stderr):
            stream.flush()
            os.fsync(stream.fileno())
    count, tail = write_findings(paths, findings_path)
    sync_directory(directory)
    bindings = {name: file_binding(path) for name, path in bound.items()}
    elapsed = round(time.monotonic() - began, 3)
    measured = publishable(code, terminal, process_id, elapsed, bindings, count, "", False)
    text, truncated = summary(
        findings_path,
        bindings["findings"]["bytes"],
        tail,
        min(SUMMARY_BUDGET, MODEL_RECEIPT_LIMIT - len(json.dumps(measured))),
    )
    receipt = publishable(code, terminal, process_id, elapsed, bindings, count, text, truncated)
    atomic_json(directory / "receipt.json", receipt)
    if launch_error is not None:
        raise launch_error
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="explicit alternative store; default requires mounted Mac share",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        result = capture(argv, args.cwd, root=args.root, timeout=args.timeout)
        print(json.dumps(result))
        return result["exit"] if 0 <= result["exit"] <= 255 else 1
    except (OSError, ValueError) as error:
        print(
            json.dumps({"error": str(error), "durable_success": False}), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
