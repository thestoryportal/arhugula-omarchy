"""Explicit subprocess adapters; never interpret ticket text as shell commands."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess

from .continuation import Stop


def command(argv, cwd, *, timeout=60, input=None):
    # Own process group so a timeout cannot leave an editing child behind.
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


class LocalAdapter:
    def __init__(self, cwd, verify_argv, *, timeout=60, lit_argv=("lit",)):
        self.cwd = Path(cwd).resolve()
        self.verify_argv = verify_argv
        self.timeout = timeout
        self.lit_argv = list(lit_argv)

    def checked(self, argv, cwd=None):
        result = command(argv, cwd or self.cwd, timeout=self.timeout)
        if result.returncode:
            raise Stop(f"command-failed: {shlex.join(argv)}: {result.stderr.strip()}")
        return result.stdout

    def git(self, *args, cwd=None):
        return self.checked(["git", *args], cwd=cwd)

    def lit(self, *args):
        return self.checked([*self.lit_argv, *args])

    def next(self):
        result = command([*self.lit_argv, "next"], self.cwd, timeout=self.timeout)
        if result.returncode == 0:
            return result.stdout
        # LIT 0.14 uses exit 1, not an empty successful result, for exhaustion.
        if result.returncode == 1 and result.stderr.splitlines()[:1] == ["error (code=1): no ready work"]:
            return ""
        raise Stop(f"lit-next-failed: {result.stderr.strip()}")

    def export(self):
        return json.loads(self.lit("export"))

    def start(self, ticket):
        try:
            self.lit("start", ticket)
        except Stop as error:
            raise Stop("claim-conflict") from error

    def show(self, ticket):
        return self.lit("show", ticket)

    def comment(self, ticket, body):
        self.lit("comment", "add", ticket, "--body", body)

    def done(self, ticket):
        self.lit("done", ticket)

    def common_dir(self):
        return Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())

    def inspect(self, expected_head=None, allowed=()):
        branch = self.git("branch", "--show-current").strip()
        if not branch or branch in {"main", "master"}:
            raise Stop("isolated-branch-required")
        head = self.git("rev-parse", "HEAD").strip()
        if expected_head and head != expected_head:
            raise Stop("git-head-changed")
        # Inspect every linked checkout. Uncooperative external writers remain a
        # residual race; the shared lease serializes this supervisor's sessions.
        for item in self.git("worktree", "list", "--porcelain", "-z").split("\0"):
            if item.startswith("worktree "):
                other = Path(item[9:]).resolve()
                if other != self.cwd and self.git("status", "--porcelain=v1", "--untracked-files=all", cwd=other).strip():
                    raise Stop("dirty-tree-conflict")
        changed = set(filter(None, self.git("diff", "--name-only", "-z", "HEAD").split("\0")))
        changed.update(filter(None, self.git("ls-files", "--others", "--exclude-standard", "-z").split("\0")))
        if changed - set(allowed):
            raise Stop("dirty-tree-conflict")
        if self.git("diff", "--name-only", "--diff-filter=D", "HEAD").strip():
            raise Stop("destructive")
        for name in changed:
            path = self.cwd / name
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != self.cwd):
                raise Stop("symlink-change")
        return dict(branch=branch, head=head, worktree=str(self.cwd))

    def verify(self):
        result = command(self.verify_argv, self.cwd, timeout=self.timeout)
        evidence = f"{shlex.join(self.verify_argv)}; exit={result.returncode}\n{result.stdout[-6000:]}{result.stderr[-6000:]}"
        return result.returncode == 0, evidence

    def commit(self, ticket, files):
        self.inspect(allowed=files)
        self.git("diff", "--check")
        # Literal pathspecs prevent a worker receipt from staging arbitrary globs.
        self.git("--literal-pathspecs", "add", "--", *files)
        self.git("diff", "--cached", "--check")
        if not self.git("diff", "--cached", "--name-only").strip():
            raise Stop("no-changes-to-commit")
        self.git("commit", "-m", f"feat(orchestration): complete {ticket}")
        return self.git("rev-parse", "HEAD").strip()


class ProcessWorker:
    """Trusted local argv in; one JSON receipt out. No executable comes from LIT."""
    def __init__(self, argv, cwd, timeout):
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
            raise ValueError("worker argv required")
        self.argv, self.cwd, self.timeout = argv, cwd, timeout

    def __call__(self, context):
        try:
            result = command(self.argv, self.cwd, timeout=self.timeout, input=json.dumps(context))
        except subprocess.TimeoutExpired:
            raise Stop("worker-timeout") from None
        if result.returncode:
            raise Stop("worker-failed")
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise Stop("invalid-worker-receipt") from None
