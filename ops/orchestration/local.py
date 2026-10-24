"""Explicit subprocess adapters; never interpret ticket text as shell commands."""

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile

from .continuation import Stop
from .handoff import validate
from .artifacts import capture, DEFAULT_ROOT
from .ownership import undeclared


def command(argv, cwd, *, timeout=60, input=None, env=None):
    # Own process group so a timeout cannot leave an editing child behind.
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
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
    def __init__(
        self,
        cwd,
        verify_argv,
        *,
        timeout=60,
        lit_argv=("lit",),
        artifact_root=DEFAULT_ROOT,
        ownership=lambda: (),
    ):
        self.cwd = Path(cwd).resolve()
        # Source of the active reservations, read again at every inspection so a
        # released owner stops covering its checkout; with none, every other
        # dirty checkout is unowned.
        self.ownership = ownership
        self.verify_argv = verify_argv
        self.timeout = timeout
        self.lit_argv = list(lit_argv)
        self.artifact_root = artifact_root
        # LIT derives the claiming session from the environment; pinning it here
        # keeps every claim and renewal by this adapter under one identity.
        self.lit_env = dict(os.environ)
        # LIT records CLAUDE_CODE_SESSION_ID itself and prefers it over --assignee;
        # a Codex session names its native thread through that fallback. With
        # neither, LIT would leave the claim anonymous: there is no owner to claim as.
        thread = self.lit_env.get("CODEX_THREAD_ID")
        self.owner_args = (
            ["--assignee", f"codex_{thread}"] if thread
            else [] if self.lit_env.get("CLAUDE_CODE_SESSION_ID")
            else None
        )
        self.claims = {}

    def checked(self, argv, cwd=None, env=None):
        result = command(argv, cwd or self.cwd, timeout=self.timeout, env=env)
        if result.returncode:
            raise Stop(f"command-failed: {shlex.join(argv)}: {result.stderr.strip()}")
        return result.stdout

    def git(self, *args, cwd=None):
        return self.checked(["git", *args], cwd=cwd)

    def lit(self, *args):
        return self.checked([*self.lit_argv, *args], env=self.lit_env)

    def next(self):
        result = command([*self.lit_argv, "next"], self.cwd, timeout=self.timeout, env=self.lit_env)
        if result.returncode == 0:
            return result.stdout
        # LIT 0.14 uses exit 1, not an empty successful result, for exhaustion.
        if result.returncode == 1 and result.stderr.splitlines()[:1] == [
            "error (code=1): no ready work"
        ]:
            return ""
        raise Stop(f"lit-next-failed: {result.stderr.strip()}")

    def export(self):
        return json.loads(self.lit("export"))

    def assignee(self, ticket):
        (issue,) = [i for i in self.export()["issues"] if i["id"] == ticket]
        # LIT export omits the field for an issue nobody holds.
        return issue.get("assignee", "")

    def claim(self, ticket, holder):
        # [LAW:single-enforcer] Every native claim passes this ownership check.
        # Native start silently transfers a same-checkout claim to another session,
        # so a current holder other than this adapter's refuses before any mutation.
        if self.owner_args is None:
            raise Stop("claim-owner-unknown")
        if self.assignee(ticket) != holder:
            raise Stop("claim-conflict")
        try:
            self.lit("start", ticket, *self.owner_args)
        except Stop as error:
            raise Stop("claim-conflict") from error
        owner = self.assignee(ticket)
        if not owner or holder not in ("", owner):
            raise Stop("claim-conflict")
        self.claims[ticket] = owner

    def start(self, ticket):
        self.claim(ticket, self.claims.get(ticket, ""))

    def show(self, ticket):
        return self.lit("show", ticket)

    def comment(self, ticket, body):
        self.lit("comment", "add", ticket, "--body", body)

    def done(self, ticket):
        self.lit("done", ticket)

    def assert_claim(self, ticket):
        # LIT has no read-only exported claims API. Renew only the claim this
        # adapter made, through the native conflict check; never pass --take.
        self.claim(ticket, self.claims.get(ticket))

    def common_dir(self):
        return Path(
            self.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        )

    def dirty(self, worktree):
        # -z keeps names verbatim and terminates every record with NUL; a rename's
        # following record is its source path.
        records = iter(self.git(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", cwd=worktree
        ).split("\0")[:-1])
        paths = set()
        for record in records:
            paths.add(record[3:])
            if {"R", "C"} & set(record[:2]):
                paths.add(next(records))
        return paths

    def inspect(self, expected_head=None, allowed=()):
        branch = self.git("branch", "--show-current").strip()
        if not branch or branch in {"main", "master"}:
            raise Stop("isolated-branch-required")
        head = self.git("rev-parse", "HEAD").strip()
        if expected_head and head != expected_head:
            raise Stop("git-head-changed")
        ownership = tuple(self.ownership())
        # Inspect every linked checkout. Dirty work another active reservation
        # declares is not this assignment's conflict; anything undeclared is.
        # Uncooperative external writers remain a residual race; the shared lease
        # serializes this supervisor's sessions.
        for item in self.git("worktree", "list", "--porcelain", "-z").split("\0"):
            if item.startswith("worktree "):
                other = Path(item[9:]).resolve()
                if other != self.cwd and undeclared(
                    ownership, other, self.dirty(other)
                ):
                    raise Stop("dirty-tree-conflict")
        changed = set(
            filter(None, self.git("diff", "--name-only", "-z", "HEAD").split("\0"))
        )
        changed.update(
            filter(None, self.git("diff", "--cached", "--name-only", "-z").split("\0"))
        )
        changed.update(filter(None, self.git("diff", "--name-only", "-z").split("\0")))
        changed.update(
            filter(
                None,
                self.git("ls-files", "--others", "--exclude-standard", "-z").split(
                    "\0"
                ),
            )
        )
        if changed - set(allowed):
            raise Stop("dirty-tree-conflict")
        if (
            self.git("diff", "--name-only", "--diff-filter=D", "HEAD").strip()
            or self.git("diff", "--cached", "--name-only", "--diff-filter=D").strip()
        ):
            raise Stop("destructive")
        for name in changed:
            path = self.cwd / name
            if path.is_symlink() or any(
                p.is_symlink() for p in path.parents if p != self.cwd
            ):
                raise Stop("symlink-change")
        return dict(branch=branch, head=head, worktree=str(self.cwd))

    def verify(self):
        result = capture(
            self.verify_argv, self.cwd, root=self.artifact_root, timeout=self.timeout
        )
        evidence = f"{shlex.join(self.verify_argv)}; exit={result['exit']}; receipt={result['receipt']}\n{result['summary']}"
        return result["terminal"] == "exited" and result["exit"] == 0, evidence

    def commit(self, ticket, files):
        self.inspect(allowed=files)
        self.git("diff", "--check")
        # Literal pathspecs prevent a worker receipt from staging arbitrary globs.
        self.git("--literal-pathspecs", "add", "--", *files)
        self.git("diff", "--cached", "--check")
        staged = set(
            filter(None, self.git("diff", "--cached", "--name-only", "-z").split("\0"))
        )
        if staged - set(files):
            raise Stop("dirty-tree-conflict")
        if not self.git("diff", "--cached", "--name-only").strip():
            raise Stop("no-changes-to-commit")
        self.git("commit", "-m", f"feat(orchestration): complete {ticket}")
        return self.git("rev-parse", "HEAD").strip()


class ProcessWorker:
    """Trusted local argv in; one JSON receipt out. No executable comes from LIT."""

    def __init__(self, argv, cwd, timeout, *, artifact_root=DEFAULT_ROOT):
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(x, str) or not x for x in argv)
        ):
            raise ValueError("worker argv required")
        self.argv, self.cwd, self.timeout = argv, cwd, timeout
        self.artifact_root = artifact_root

    def __call__(self, context):
        result = capture(
            self.argv,
            self.cwd,
            root=self.artifact_root,
            timeout=self.timeout,
            input=json.dumps(context),
        )
        if result["terminal"] == "timeout":
            raise Stop("worker-timeout") from None
        if result["exit"] or result["terminal"] != "exited":
            raise Stop("worker-failed")
        try:
            if result["stdout"]["bytes"] > 1024 * 1024:
                raise ValueError("worker receipt exceeds bound")
            return json.loads(Path(result["stdout"]["path"]).read_text())
        except ValueError:
            raise Stop("invalid-worker-receipt") from None


class CodexWorker:
    """Synchronous Codex adapter using current routing, stdin, and a JSON receipt."""

    def __init__(self, cwd, timeout, executable=None, *, artifact_root=DEFAULT_ROOT):
        self.cwd, self.timeout = Path(cwd), timeout
        self.executable = executable or ["codex"]
        self.artifact_root = artifact_root

    def __call__(self, context):
        validate(context)
        if not context.get("supervisor"):
            raise Stop("worker-context-required")
        with tempfile.TemporaryDirectory(prefix="arhugula-codex-receipt-") as directory:
            output = Path(directory) / "receipt.json"
            schema = Path(__file__).with_name("worker-receipt.schema.json")
            argv = [
                *self.executable,
                "exec",
                "--model",
                context["model"],
                "--config",
                f'model_reasoning_effort="{context["effort"]}"',
                "--sandbox",
                "workspace-write",
                "--cd",
                str(self.cwd),
                "--output-schema",
                str(schema),
                "--output-last-message",
                str(output),
                "-",
            ]
            result = capture(
                argv,
                self.cwd,
                root=self.artifact_root,
                timeout=self.timeout,
                input=json.dumps(context),
            )
            if result["terminal"] == "timeout":
                raise Stop("worker-timeout") from None
            if result["exit"] or result["terminal"] != "exited":
                raise Stop("worker-failed")
            try:
                return json.loads(output.read_text())
            except (OSError, ValueError):
                raise Stop("invalid-worker-receipt") from None
