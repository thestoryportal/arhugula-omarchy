"""Stream raw subprocess output to private disk files; emit bounded receipts."""
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

DEFAULT_ROOT = Path('/mnt/mac/arhugula-artifacts')


def require_mac_share(mountinfo):
    for line in mountinfo.splitlines():
        left, right = line.split(' - ', 1)
        fields, filesystem = left.split(), right.split()
        if fields[4] == '/mnt/mac' and 'rw' in fields[5].split(',') and filesystem[:2] == ['9p', 'mac']:
            return
    raise ValueError('writable Mac share is unavailable; no guest-disk fallback')


def file_binding(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': str(Path(path).absolute()), 'bytes': Path(path).stat().st_size,
            'sha256': digest.hexdigest()}


def summary(paths, limit=4096):
    # [LAW:carrying-cost] Cap even a single compiler line; retain full bytes on disk.
    matches, tail = [], b''
    for path in paths:
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda: stream.readline(1024), b''):
                if re.search(rb'error|fail|traceback|passed|ran \d+|^OK$', chunk, re.I) and sum(map(len, matches)) < limit // 2:
                    matches.append(chunk[:512])
                tail = (tail + chunk)[-limit // 2:]
    return (b''.join(matches)[:limit // 2] + b'\n[bounded tail]\n' + tail).decode('utf-8', 'replace')[:limit]


def capture(argv, cwd, *, root=DEFAULT_ROOT, timeout=300, input=None):
    if not argv or any(not isinstance(x, str) or not x or '\x00' in x for x in argv) or timeout <= 0:
        raise ValueError('literal argv and positive timeout required')
    root = Path(root).absolute()
    if root == DEFAULT_ROOT or DEFAULT_ROOT in root.parents:
        require_mac_share(Path('/proc/self/mountinfo').read_text())
    root = private_directory(root)
    directory = Path(tempfile.mkdtemp(prefix='run-', dir=root))
    paths = [directory / 'stdout.log', directory / 'stderr.log']
    began = time.monotonic()
    launch_error = None
    terminal, code = 'exited', None
    # [LAW:effects-at-boundaries] No pipe buffers or raw logs enter model context.
    with paths[0].open('xb') as stdout, paths[1].open('xb') as stderr:
        os.chmod(paths[0], 0o600); os.chmod(paths[1], 0o600)
        try:
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.communicate(input=input.encode() if isinstance(input, str) else input, timeout=timeout)
                code = process.returncode
            except BaseException as error:
                # This capture owns this process group, never an inherited worker.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                terminal = 'timeout' if isinstance(error, subprocess.TimeoutExpired) else 'interrupted'
                code = 124 if terminal == 'timeout' else 130
                if terminal == 'interrupted':
                    launch_error = error
        except OSError as error:
            terminal, launch_error = 'launch_failed', error
            stderr.write(str(error).encode())
        for stream in (stdout, stderr):
            stream.flush(); os.fsync(stream.fileno())
    sync_directory(directory)
    receipt = dict(version=1, argv=argv, cwd=str(Path(cwd).absolute()), exit=code,
                   terminal=terminal, elapsed_seconds=round(time.monotonic()-began, 3),
                   stdout=file_binding(paths[0]), stderr=file_binding(paths[1]),
                   summary=summary(paths), receipt=str(directory / 'receipt.json'))
    atomic_json(directory / 'receipt.json', receipt)
    if launch_error is not None:
        raise launch_error
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT,
                        help='explicit alternative store; default requires mounted Mac share')
    parser.add_argument('--cwd', type=Path, default=Path.cwd())
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
        result = capture(argv, args.cwd, root=args.root, timeout=args.timeout)
        print(json.dumps(result))
        return result['exit'] if 0 <= result['exit'] <= 255 else 1
    except (OSError, ValueError) as error:
        print(json.dumps({'error': str(error), 'durable_success': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
