"""Reclaim inactive generated Dolt caches and admit disk-backed workflow scratch."""
import argparse
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time

GIB = 1024 ** 3
INSTALL = Path.home() / ".local/share/arhugula-workflow"


def stamp(path):
    s = path.lstat()
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns)


@dataclass(frozen=True)
class Cache:
    path: Path
    identity: tuple
    files: tuple

    @classmethod
    def parse(cls, path, cutoff):
        # [LAW:parse-dont-validate] Only this producer's immutable blob shape is disposable.
        if not re.fullmatch(r"(?:dolt-gitblobstore-materialized-[0-9]+|\.arhugula-dolt-reclaim-[0-9]+-[0-9]+)", path.name):
            return None
        try:
            return cls._parse(path, cutoff)
        except FileNotFoundError:
            return None  # A released cache is already reclaimed.

    @classmethod
    def _parse(cls, path, cutoff):
        s = path.lstat()
        if (not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid()
                or s.st_mtime > cutoff):
            return None
        files = tuple(sorted((p.name, stamp(p)) for p in path.iterdir()))
        for name, identity in files:
            if (not re.fullmatch(r"[0-9a-f]{40}-[0-9]+", name)
                    or not stat.S_ISREG(identity[2]) or identity[3] != os.getuid()
                    or identity[5] / 1e9 > cutoff):
                return None
        return cls(path, stamp(path), files)

    def unchanged(self):
        return (stamp(self.path) == self.identity
                and tuple(sorted((p.name, stamp(p)) for p in self.path.iterdir())) == self.files)


def references(proc_root=Path("/proc")):
    """Own-user file references and live producers; unreadable workers hold cleanup."""
    refs, producers, ignored = set(), [], []
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            command = (proc / "comm").read_text().strip()
            args = (proc / "cmdline").read_bytes()
            # User systemd and its PAM helper are nondumpable infrastructure, not cache producers.
            if args == b"/usr/lib/systemd/systemd\x00--user\x00" or command == "(sd-pam)":
                ignored.append(int(proc.name))
                continue
            if command in ("lit", "lit.real", "dolt"):
                producers.append(int(proc.name))
            refs.add(os.readlink(proc / "cwd"))
            for descriptor in (proc / "fd").iterdir():
                try:
                    refs.add(os.readlink(descriptor))
                except FileNotFoundError:
                    continue  # This descriptor closed; the process's other references remain relevant.
            for line in (proc / "maps").read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) == 6:
                    refs.add(fields[5].removesuffix(" (deleted)"))
        except FileNotFoundError:
            if proc.exists():
                producers.append(int(proc.name))  # A partially observed live process holds cleanup.
        except PermissionError:
            producers.append(int(proc.name))  # Unknown references are a visible deferral.
    return refs, producers, ignored


def reclaim(root, *, minimum_free, target_free, min_age=7200, proc_root=Path("/proc")):
    if minimum_free <= 0 or target_free < minimum_free or min_age <= 0:
        raise ValueError("positive reserve/age and target at least reserve required")
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("temporary root contains a symlink")
    before = shutil.disk_usage(root).free
    report = dict(root=str(root), before_free=before, after_free=before,
                  minimum_free=minimum_free, target_free=target_free, removed=[],
                  deferred_producers=[], ignored_infrastructure=[])
    if before >= minimum_free:
        return report
    cutoff = time.time() - min_age
    caches = [cache for path in root.iterdir()
              if (cache := Cache.parse(path, cutoff)) is not None]
    for cache in sorted(caches, key=lambda c: c.identity[5]):
        refs, producers, ignored = references(proc_root)
        report["ignored_infrastructure"] = ignored
        # [LAW:no-ambient-temporal-coupling] A live producer may reopen a cached blob later.
        if producers:
            report["deferred_producers"] = producers
            break
        if any(p == str(cache.path) or p.startswith(str(cache.path) + "/") for p in refs):
            continue
        try:
            if cache.unchanged():
                # [LAW:no-ambient-temporal-coupling] Detach the old namespace before interruptible deletion.
                tombstone = root / f".arhugula-dolt-reclaim-{cache.identity[1]}-{time.time_ns()}"
                cache.path.rename(tombstone)
                shutil.rmtree(tombstone)
                report["removed"].append(str(cache.path))
        except FileNotFoundError:
            continue  # A concurrent release already removed this cache.
        report["after_free"] = shutil.disk_usage(root).free
        if report["after_free"] >= target_free:
            break
    return report


def scratch_directory(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("scratch path contains a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = path.stat()
    if s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise ValueError("scratch must be private and owned")
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        mount = Path(left.split()[4].replace("\\040", " ").replace("\\134", "\\"))
        if path == mount or mount in path.parents:
            mounts.append((len(str(mount)), right.split()[0]))
    if not mounts or max(mounts)[1] in ("tmpfs", "ramfs", "devtmpfs"):
        raise ValueError("workflow scratch must be disk backed")
    return path


def execute(argv, scratch, *, tmp_root=Path("/tmp")):
    if not argv or any(not isinstance(a, str) or not a or "\x00" in a for a in argv):
        raise ValueError("literal command required")
    scratch = scratch_directory(scratch)
    results = maintain(scratch, tmp_root)
    if results[1].get("after_free", 0) < 4 * GIB:
        raise ValueError("disk scratch reserve unavailable: " + json.dumps(results[1]))
    # [LAW:effects-at-boundaries] Each child receives its own explicit temporary-storage environment.
    environment = dict(os.environ, TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch))
    # [LAW:no-ambient-temporal-coupling] Command ownership transfers with its PID and signals.
    os.execve(argv[0], argv, environment)


def maintain(scratch, tmp_root=Path("/tmp")):
    # [LAW:single-enforcer] Both callers retain failures and run both storage policies.
    with (scratch.parent / "maintenance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        results = []
        for root, minimum, target in ((tmp_root, 2 * GIB, 3 * GIB),
                                       (scratch, 4 * GIB, 8 * GIB)):
            try:
                report = reclaim(root, minimum_free=minimum, target_free=target)
            except (OSError, ValueError) as error:
                report = dict(root=str(root), minimum_free=minimum, error=str(error))
                print(json.dumps({"temporary_space_error": report}), file=sys.stderr)
            results.append(report)
        publish(scratch.parent / "space-receipt.json", {"time": time.time(), "roots": results})
        return results


def publish(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".space-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_install(installation):
    # [LAW:one-source-of-truth] The installer binds deployed bytes to the accepted revision.
    expected = json.loads((installation / "installation.json").read_text())
    if not isinstance(expected, dict) or not expected:
        raise ValueError("nonempty installation hash manifest required")
    for name, digest in expected.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid installed-file digest")
        with Path(name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise ValueError("installed file differs from reviewed bytes: " + name)


def main(installation=INSTALL):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["maintain", "exec"])
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        install = scratch_directory(installation)
        scratch = scratch_directory(install / "tmp")
        try:
            verify_install(install)
        except (OSError, ValueError) as error:
            publish(install / "space-receipt.json", {"time": time.time(), "integrity_error": str(error)})
            raise
        if args.command == "exec":
            argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            return execute(argv, scratch)
        results = maintain(scratch)
        print(json.dumps(results))
        return 0 if all(r.get("after_free", 0) >= r["minimum_free"] for r in results) else 78
    except (OSError, ValueError) as error:
        print(json.dumps({"temporary_space_error": str(error)}), file=sys.stderr)
        return 78


if __name__ == "__main__":
    sys.exit(main())
