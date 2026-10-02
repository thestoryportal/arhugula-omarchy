"""Private, atomic JSON records; callers own semantic parsing and leases."""
import json
import os
from pathlib import Path
import tempfile


def private_directory(path):
    path = Path(path).absolute()
    # [LAW:parse-dont-validate] Refuse redirection at the filesystem boundary.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('record path contains a symlink')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('record directory must be private and owned')
    return path


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path = Path(path).absolute()
    directory = private_directory(path.parent)
    if path.is_symlink():
        raise ValueError('record path contains a symlink')
    fd, temporary = tempfile.mkstemp(prefix='.record-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
