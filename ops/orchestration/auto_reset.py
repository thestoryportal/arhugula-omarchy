"""Autonomous same-window native reset; never replay an uncertain input effect."""

import argparse
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import select
import socket
import sqlite3
import sys
import time
import uuid
from datetime import datetime

from .artifacts import DEFAULT_ROOT, file_binding
from .continuation import Lease
from .goal_lineage import GoalLineage, goal_observation
from .loop import Loop, NativeLit, RecoveryTransfer, identity
from .native_window import NativeWindow, WindowCapability
from .native_goal import read_goal
from .records import atomic_json, private_directory


def user_frontier(actual):
    return {"count": actual["user_count"], "hash": actual["last_user_hash"]}


@dataclass(frozen=True)
class ExpiredTitleRecovery:
    """The original waiting-title case requires its actual human first user."""

    @classmethod
    def parse(cls, transfer, failed, config):
        if failed["phase"] != "waiting_title":
            raise ValueError("expired waiting_title recovery authority required")
        return cls()

    def bind_user(self, transfer, failed, actual, proof):
        grant = transfer.grant
        human = json.loads(Path(grant["human_authority"]["path"]).read_text())
        if (
            human["session_id"] != actual["session_id"]
            or human["user_frontier"] != grant["user_frontier"]
            or human["actual_user_message"] != actual["first_user"]
        ):
            raise ValueError(
                "actual same-window human frontier recovery evidence required"
            )


@dataclass(frozen=True)
class ExpiredPromptRecovery:
    """An expired delivered prompt transfers maintenance identity, never freshness."""

    prompt: dict

    @classmethod
    def parse(cls, transfer, failed, config):
        grant = transfer.grant
        if (
            failed["phase"] != "waiting_fresh"
            or transfer.failed.get("maintenance_recovery") is None
            or transfer.failed.get("maintenance_only") is not True
        ):
            raise ValueError("expired waiting_fresh sealed-prompt recovery required")
        frozen = json.loads(Path(grant["config"]["path"]).read_text())
        effective = {k: v for k, v in config.items() if k != "config_path"}
        if {k: v for k, v in frozen.items() if k != "config_path"} != effective:
            raise ValueError("failed recovery config changed")
        if "config_path" in config and any(
            file_binding(config["config_path"])[k] != grant["config"][k]
            for k in ("bytes", "sha256")
        ):
            raise ValueError("actual supervisor config changed")
        package = Path(failed["reset"]["directory"])
        attempt = {
            "manifest": failed["reset"]["manifest"],
            "frontier": file_binding(package / "frontier.json"),
            "nonce": failed["nonce"],
            "started": failed["started"],
            "fresh_context": failed["fresh_context"],
        }
        if grant["attempt"] != attempt or failed["fresh_context"]["user_input"]:
            raise ValueError("failed prompt attempt/creation binding mismatch")
        frontier = json.loads((package / "frontier.json").read_text())
        if (
            frontier["nonce"] != failed["nonce"]
            or failed["title"] != "Buford-auto-" + frontier["nonce"]
            or failed["routing"] != frontier["routing"]
        ):
            raise ValueError("failed prompt nonce/title/frontier mismatch")
        text = (package / "resume-prompt.txt").read_text()
        # [LAW:one-source-of-truth] historical keyboard attempts removed
        # the file's final newline; their sealed failed supervisor carries no queue intent.
        if "queue_ack" not in failed:
            text = text.removesuffix("\n")
        elif (
            failed["prompt"] != file_binding(package / "resume-prompt.txt")
            or failed["queue_ack"]["session_id"]
            != failed["fresh_context"]["session_id"]
        ):
            raise ValueError("failed queued prompt/target intent mismatch")
        expected = {
            "file": file_binding(package / "resume-prompt.txt"),
            "bytes": len(text.encode()),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "count": 1,
        }
        if grant["prompt"] != expected:
            raise ValueError("sealed prompt bytes/hash/count mismatch")
        frozen_goal = json.loads(Path(grant["goal_ledger"]["path"]).read_text())
        current_goal = json.loads(Path(config["goal_ledger"]).read_text())
        # [LAW:one-source-of-truth] Recovery may append its two actual observations;
        # it cannot rewrite the inherited objective, deadline, counters or history.
        keys = set(frozen_goal) | set(current_goal)
        if any(
            frozen_goal.get(k) != current_goal.get(k)
            for k in keys - {"receipts", "absent_goals"}
        ):
            raise ValueError("protected goal contract/accounting changed")
        allowed = [grant["terminal_goal"], grant["current_goal"]]
        if any(
            r not in current_goal["receipts"] for r in frozen_goal["receipts"]
        ) or any(
            r not in frozen_goal["receipts"] + allowed for r in current_goal["receipts"]
        ):
            raise ValueError("protected goal receipt history changed")
        allowed_absent = [
            {"session_id": session, "receipt": grant[key]}
            for session, key in (
                (failed["reset"]["previous_session"], "terminal_goal"),
                (grant["session_id"], "current_goal"),
            )
        ]
        before_absent = frozen_goal.get("absent_goals", [])
        after_absent = current_goal.get("absent_goals", [])
        if any(r not in after_absent for r in before_absent) or any(
            r not in before_absent + allowed_absent for r in after_absent
        ):
            raise ValueError("protected goal absence history changed")
        return cls(expected)

    def bind_user(self, transfer, failed, actual, proof):
        initial = failed["fresh_context"]
        if (
            any(
                proof[k] != initial[k]
                for k in ("session_id", "created_at", "creation_log_id", "process_uuid")
            )
            or proof["user_input"] is not True
            or datetime.fromisoformat(actual["created_at"].replace("Z", "+00:00"))
            != datetime.fromisoformat(initial["created_at"].replace("Z", "+00:00"))
            or actual["user_count"] != 1
            or len(actual["first_user"].encode()) != self.prompt["bytes"]
            or hashlib.sha256(actual["first_user"].encode()).hexdigest()
            != self.prompt["sha256"]
        ):
            raise ValueError("actual sole sealed prompt/native creation mismatch")


def recovery_case(transfer, failed, config):
    # [LAW:parse-dont-validate] Two distinct failed-attempt capabilities own their
    # different evidence contracts; common publication consumes the proven case.
    cases = {
        "expired-waiting-title-human-frontier": ExpiredTitleRecovery,
        "expired-waiting-fresh-sealed-prompt": ExpiredPromptRecovery,
    }
    kind = transfer.grant.get("kind", "expired-waiting-title-human-frontier")
    if kind not in cases:
        raise ValueError("unknown maintenance recovery capability")
    try:
        return cases[kind].parse(transfer, failed, config)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("malformed failed-attempt recovery evidence") from error


class AutoReset:
    def __init__(self, loop, path, config, window, clock=time.monotonic):
        self.loop = loop
        self.path = Path(path)
        self.config = config
        self.window = window
        self.clock = clock

    def status(self):
        return (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"phase": "monitoring"}
        )

    def save(self, state):
        atomic_json(self.path, state)

    def bindings(self):
        for bound in [
            self.config["authority"],
            self.config["continuation"],
            *self.config["source_acceptance"],
        ]:
            if file_binding(bound["path"]) != bound:
                raise ValueError("autoreset authority/source binding changed")

    def retain_goal(self, receipt, session):
        actual, observation = goal_observation(json.loads(Path(receipt).read_text()))
        if actual != session:
            raise ValueError("actual current goal observation required")
        ledger = GoalLineage(self.config["goal_ledger"])
        if observation["goal"] is None:
            if read_goal(self.config["goal_database"], session)["goal"] is not None:
                raise ValueError("native goal appeared after absence observation")
            return ledger.record_absence(receipt, self.config["deadline"])
        return ledger.record(receipt, self.config["deadline"])

    def prepare(self):
        state = self.loop.status()
        routing = next(
            s for s in self.loop._control()["sessions"] if s["role"] == "buford"
        )
        release = json.loads(Path(self.config["release"]).read_text())
        if (release["session_id"], release["epoch"]) != (
            state["session_id"],
            state["epoch"],
        ) or release.get("completed") != sorted(state["completed"]):
            waiting = {"phase": "waiting_release"}
            self.save(waiting)
            return waiting
        actual = identity(routing["transcript"])
        if release["user_frontier"] != user_frontier(actual):
            raise ValueError("user input changed since release")
        self.retain_goal(release["goal_receipt"], state["session_id"])
        directory = Path(self.config["packages"]) / str(uuid.uuid4())
        reset = self.loop.prepare_clear(
            directory,
            release["owned_processes"],
            automatic={
                "config": self.config.get("config_path", "fixture-config.json"),
                "continuation": self.config["continuation"]["path"],
                "goal_receipt": release["goal_receipt"],
                "goal_ledger": self.config["goal_ledger"],
                "deadline": self.config["deadline"],
            },
        )
        frontier = json.loads((directory / "frontier.json").read_text())
        prepared = {
            "phase": "waiting_idle",
            "old_transcript": routing["transcript"],
            "old_user_frontier": release["user_frontier"],
            "routing": file_binding(self.loop.control),
            "control_snapshot": self.loop._control(),
            "reset": reset,
            "nonce": frontier["nonce"],
            "title": "Buford-auto-" + frontier["nonce"],
            "started": None,
            "goal_receipt": file_binding(release["goal_receipt"]),
        }
        self.save(prepared)
        return prepared

    def unchanged_parent(self, state, recovery_transcript=None):
        if file_binding(self.loop.control) != state["routing"]:
            journal = self.loop.status()
            pending = journal.get("pending_bootstrap")
            publication = journal.get("last_bootstrap", {})
            if (
                publication.get("manifest") == state["reset"]["manifest"]
                and recovery_transcript is not None
                and publication.get("transcript")
                == str(Path(recovery_transcript).absolute())
            ):
                pending = journal["session_id"]
            expected = json.loads(json.dumps(state["control_snapshot"]))
            buford = next(s for s in expected["sessions"] if s["role"] == "buford")
            if (
                recovery_transcript is None
                or pending != identity(recovery_transcript)["session_id"]
            ):
                raise ValueError("routing/pause changed after preparation")
            previous = buford["session_id"]
            buford.update(
                session_id=pending, transcript=str(Path(recovery_transcript).absolute())
            )
            if expected.get("notification_thread") == previous:
                expected["notification_thread"] = pending
            if self.loop._control() != expected:
                raise ValueError("routing/pause changed outside pending bootstrap")
        actual = identity(state["old_transcript"])
        if user_frontier(actual) != state["old_user_frontier"]:
            raise ValueError("user input changed after preparation")
        return actual

    def cleared(self, state):
        frontier = json.loads(
            (Path(state["reset"]["directory"]) / "frontier.json").read_text()
        )
        matching = []
        # The actual native client owns these rollouts; filename day is irrelevant.
        for path in self.window.transcripts():
            candidate = identity(path)
            if (
                candidate["session_id"] != state["reset"]["previous_session"]
                and candidate["created_at"]
                and datetime.fromisoformat(
                    candidate["created_at"].replace("Z", "+00:00")
                )
                >= datetime.fromisoformat(frontier["prepared_at"])
                and {k: candidate[k] for k in ("cwd", "source", "originator")}
                == frontier["native_lane"]
            ):
                matching.append(path)
        if len(matching) > 1:
            raise ValueError("ambiguous fresh native CLI context")
        return matching[0] if matching else None

    def fresh(self, state):
        path = self.cleared(state)
        if path is not None and identity(path)["model"] is not None:
            return path
        return None

    def publish(self, state, result):
        proof = result["last_bootstrap"]
        if (
            proof.get("manifest") != state["reset"]["manifest"]
            or proof.get("nonce") != state["nonce"]
        ):
            raise ValueError("bootstrap receipt does not bind this native reset")
        self.unchanged_parent(state, recovery_transcript=proof["transcript"])
        self.require_nonce_title(state)
        frontier = self.loop.clear_package(state["reset"])
        current = self.window.delivered_context(
            frontier, state["reset"]["previous_session"], state["fresh_context"]
        )
        if current["transcript"] != proof["transcript"]:
            raise ValueError("native context changed before receipt publication")
        fresh = identity(proof["transcript"])
        expected = (Path(state["reset"]["directory"]) / "resume-prompt.txt").read_text()
        if fresh["user_count"] != 1 or fresh["first_user"] != expected:
            raise ValueError(
                "fresh user input changed before native receipt publication"
            )
        elapsed = self.clock() - state["started"]
        if elapsed > 120:
            raise ValueError("native reset deadline exceeded")
        directory = private_directory(self.config["receipt_directory"])
        old = identity(state["old_transcript"])
        if (
            old["status"] != "complete"
            or user_frontier(old) != state["old_user_frontier"]
        ):
            raise ValueError(
                "terminal outgoing goal accounting requires the unchanged completed turn"
            )
        terminal = read_goal(
            self.config["goal_database"], state["reset"]["previous_session"]
        )
        digest = hashlib.sha256(
            json.dumps(terminal, sort_keys=True).encode()
        ).hexdigest()
        terminal_path = directory / (
            state["nonce"] + ".terminal-goal." + digest + ".json"
        )
        if not terminal_path.exists():
            atomic_json(terminal_path, terminal)
        self.retain_goal(terminal_path, state["reset"]["previous_session"])
        snapshot = directory / (state["nonce"] + ".goal-ledger.json")
        if not snapshot.exists():
            atomic_json(
                snapshot, json.loads(Path(self.config["goal_ledger"]).read_text())
            )
        elapsed = self.clock() - state["started"]
        if elapsed > 120:
            raise ValueError(
                "native reset deadline exceeded before receipt publication"
            )
        receipt = {
            "version": 1,
            "verified": True,
            "manifest": state["reset"]["manifest"],
            "nonce": state["nonce"],
            "previous_session": proof["previous_session"],
            "session_id": result["session_id"],
            "epoch": result["epoch"],
            "transcript": proof["transcript"],
            "seconds": round(elapsed, 3),
            "goal_receipt": state["goal_receipt"],
            "terminal_goal_receipt": file_binding(terminal_path),
            "goal_ledger": file_binding(snapshot),
            "bootstrap": proof,
            "transport": "verified-window-native-clear-and-exact-thread-queue",
            "queue_ack": state["queue_ack"],
            "prompt": state["prompt"],
            "native_context": current,
        }
        path = directory / (state["nonce"] + ".json")
        if path.exists():
            previous = json.loads(path.read_text())
            if any(previous[k] != receipt[k] for k in receipt if k != "seconds"):
                raise ValueError("existing native receipt differs; do not overwrite")
        else:
            atomic_json(path, receipt)
        self.loop.acknowledge_native_reset(
            path, deadline=state["started"] + 120, clock=self.clock
        )
        state.update(phase="verified", receipt=file_binding(path))
        self.save(state)
        return state

    def step(self, fresh_transcript=None):
        self.bindings()
        state = self.status()
        journal = self.loop.status()
        phase = state["phase"]
        if phase == "maintenance_recovered":
            raise ValueError(
                "maintenance recovery only; release a later genuine native reset"
            )
        if phase in ("monitoring", "verified", "waiting_release"):
            if (
                journal["epoch_completed"] < 5
                and journal["reset"] is None
                and not journal.get("reset_requested")
            ):
                return state
            return self.prepare()
        if phase in ("clear_intent", "prompt_intent"):
            raise ValueError(
                "uncertain native input effect; inspect actual title/transcript before recovery"
            )
        if state["started"] is not None and self.clock() - state["started"] > 120:
            raise ValueError("native reset deadline exceeded; production remains held")
        if phase == "waiting_idle":
            actual = self.unchanged_parent(state)
            if actual["status"] != "complete":
                return state
            self.loop.ready_clear(state["old_transcript"])
            self.window.check()
            state.update(phase="clear_intent", started=self.clock())
            self.save(state)
            # [LAW:effects-at-boundaries] Durable intent precedes every native input.
            self.window.clear(state["title"])
            state["phase"] = "waiting_title"
            self.save(state)
            return state
        if phase == "waiting_title":
            self.unchanged_parent(state)
            if not self.title_matches(state, self.window.title()):
                return state
            frontier = json.loads(
                (Path(state["reset"]["directory"]) / "frontier.json").read_text()
            )
            proof = self.window.context(frontier, state["reset"]["previous_session"])
            if proof is None:
                return state
            path = proof["transcript"]
            actual = identity(path) if path is not None else None
            if (
                proof["user_input"]
                or actual is not None
                and (actual["user_count"] or actual["status"] == "active")
            ):
                raise ValueError("fresh user input before generated prompt delivery")
            self.loop.ready_clear(state["old_transcript"])
            text = (Path(state["reset"]["directory"]) / "resume-prompt.txt").read_text()
            if self.clock() - state["started"] > 120:
                raise ValueError("native reset deadline exceeded before queue effect")
            state.update(
                fresh_context=proof,
                phase="prompt_intent",
                prompt=file_binding(
                    Path(state["reset"]["directory"]) / "resume-prompt.txt"
                ),
            )
            self.save(state)
            state["queue_ack"] = self.window.queue(
                proof, frontier, state["reset"]["previous_session"], text
            )
            state["phase"] = "waiting_fresh"
            self.save(state)
            return state
        if phase == "waiting_fresh":
            if (
                journal.get("last_bootstrap", {}).get("manifest")
                == state["reset"]["manifest"]
            ):
                return self.publish(state, journal)
            path = fresh_transcript or self.fresh(state)
            self.unchanged_parent(state, recovery_transcript=path)
            if path is None:
                return state
            frontier = json.loads(
                (Path(state["reset"]["directory"]) / "frontier.json").read_text()
            )
            self.require_nonce_title(state)
            current = self.window.delivered_context(
                frontier, state["reset"]["previous_session"], state["fresh_context"]
            )
            if (
                current["transcript"] != str(Path(path).absolute())
                or identity(path)["session_id"] != current["session_id"]
            ):
                raise ValueError("fresh native context changed after prompt delivery")
            result = self.loop.bootstrap(
                path, deadline=state["started"] + 120, clock=self.clock
            )
            return self.publish(state, result)
        raise ValueError("unknown autoreset phase")

    def title_matches(self, state, title):
        return title in (
            state["title"],
            state["title"] + " | " + Path(self.config.get("cwd", ".")).name,
        )

    def require_nonce_title(self, state):
        # [LAW:single-enforcer] Activity decoration is recognized only after
        # delivery/recovery. The waiting-title empty-context gate stays literal.
        title = re.sub(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏✓] ", "", self.window.title())
        if not self.title_matches(state, title):
            raise ValueError("same-window recovery nonce title mismatch")

    def recover_maintenance(self, authority):
        self.bindings()
        transfer = RecoveryTransfer.parse(authority)
        bound, grant = transfer.binding, transfer.grant
        state = self.status()
        failed = json.loads(Path(grant["supervisor"]["path"]).read_text())
        applied = state.get("phase") == "maintenance_recovered"
        if applied:
            if state["recovery_authority"] != bound:
                raise ValueError("maintenance recovery authority changed")
            original = {
                k: v
                for k, v in state.items()
                if k
                not in (
                    "recovery_authority",
                    "recovery_context",
                    "automatic_acceptance",
                )
            }
            original["phase"] = failed["phase"]
            if original != failed:
                raise ValueError("recovered supervisor changed")
        elif state != failed:
            raise ValueError("failed supervisor changed before recovery")
        case = recovery_case(transfer, failed, self.config)
        if (
            failed["started"] is None
            or self.clock() - failed["started"] <= 120
            or grant["window"] != self.config["window"]
            or grant["deadline"] != self.config["deadline"]
            or grant["maintenance_only"] is not True
            or not self.loop._control()["repair_paused"]
        ):
            raise ValueError(
                "expired same-window maintenance recovery authority required"
            )
        frontier = self.loop.clear_package(failed["reset"])
        failed_journal = json.loads(Path(grant["journal"]["path"]).read_text())
        if failed_journal["reset"] != failed["reset"]:
            raise ValueError("failed reset/journal mismatch")
        routing = json.loads(Path(grant["routing"]["path"]).read_text())
        if routing != failed["control_snapshot"]:
            refresh = grant.get("implementer_refresh")
            if refresh is None or file_binding(refresh["path"]) != refresh:
                raise ValueError("bound implementer-only routing refresh required")
            refresh = json.loads(Path(refresh["path"]).read_text())
            expected = json.loads(json.dumps(failed["control_snapshot"]))
            implementer = next(
                s for s in expected["sessions"] if s["role"] == "implementer"
            )
            current = next(s for s in routing["sessions"] if s["role"] == "implementer")
            if (
                refresh["kind"] != "authorized-idle-implementer-native-refresh"
                or refresh["production_paused"] is not True
                or refresh["previous_session"] != implementer["session_id"]
                or refresh["session_id"] != current["session_id"]
                or any(
                    refresh["control_after"][k] != grant["routing"][k]
                    for k in ("sha256", "bytes")
                )
                or file_binding(refresh["delivery"]["path"]) != refresh["delivery"]
            ):
                raise ValueError("implementer routing refresh evidence mismatch")
            delivery = json.loads(Path(refresh["delivery"]["path"]).read_text())
            if (delivery["session_id"], delivery["model"], delivery["effort"]) != (
                current["session_id"],
                "gpt-6.1-sol",
                "high",
            ):
                raise ValueError("actual refreshed implementer identity mismatch")
            implementer.update(
                session_id=current["session_id"], transcript=current["transcript"]
            )
            if routing != expected:
                raise ValueError(
                    "protected routing changed outside implementer refresh"
                )
        if (
            user_frontier(identity(failed["old_transcript"]))
            != failed["old_user_frontier"]
        ):
            raise ValueError("old user input changed before maintenance recovery")
        journal = self.loop.status()
        proof = journal.get("maintenance_recovery")
        transferred = proof is not None and proof["authority"] == bound
        if not transferred:
            self.loop.ready_clear(failed["old_transcript"])
        self.require_nonce_title(failed)
        proof = self.window.recovery_context(
            frontier, failed["reset"]["previous_session"], grant.get("retained_context")
        )
        actual = identity(grant["transcript"])
        if (
            proof is None
            or proof["session_id"] != grant["session_id"]
            or actual["session_id"] != proof["session_id"]
            or proof["transcript"] != str(Path(grant["transcript"]).absolute())
            or actual["user_count"] < 1
            or user_frontier(actual) != grant["user_frontier"]
            or (actual["model"], actual["effort"]) != ("gpt-6.1-sol", "high")
            or {k: actual[k] for k in ("cwd", "source", "originator")}
            != frontier["native_lane"]
            or not actual["created_at"]
            or datetime.fromisoformat(actual["created_at"].replace("Z", "+00:00"))
            < datetime.fromisoformat(frontier["prepared_at"])
        ):
            raise ValueError(
                "actual same-window human frontier recovery evidence required"
            )
        case.bind_user(transfer, failed, actual, proof)
        for key, session in (
            ("terminal_goal", failed["reset"]["previous_session"]),
            ("current_goal", actual["session_id"]),
        ):
            observed_session, observed = goal_observation(
                json.loads(Path(grant[key]["path"]).read_text())
            )
            if (
                observed_session != session
                or observed["goal"]
                != read_goal(self.config["goal_database"], session)["goal"]
            ):
                raise ValueError("actual native recovery goal changed")
        self.retain_goal(
            grant["terminal_goal"]["path"], failed["reset"]["previous_session"]
        )
        self.retain_goal(grant["current_goal"]["path"], actual["session_id"])
        self.loop.recover_maintenance(transfer)
        state.update(
            phase="maintenance_recovered",
            recovery_authority=bound,
            recovery_context=proof,
            automatic_acceptance=False,
        )
        self.save(state)
        return state


class Wakeups:
    """Kernel filesystem and compositor events; no model polling turns."""

    def __init__(self, paths):
        library = ctypes.CDLL(None, use_errno=True)
        self.fd = library.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        self.socket = None
        try:
            for path in set(map(Path, paths)):
                if path.exists():
                    if (
                        library.inotify_add_watch(
                            self.fd, os.fsencode(path), 0x00000FFF
                        )
                        < 0
                    ):
                        raise OSError(ctypes.get_errno(), "inotify_add_watch")
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(
                str(
                    Path(os.environ["XDG_RUNTIME_DIR"])
                    / "hypr"
                    / os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
                    / ".socket2.sock"
                )
            )
            self.socket.setblocking(False)
        except BaseException:
            self.close()
            raise

    def wait(self):
        for handle in select.select([self.fd, self.socket], [], [], 5)[0]:
            if handle == self.fd:
                os.read(self.fd, 65536)
            elif not self.socket.recv(65536):
                raise OSError("compositor event socket closed")

    def close(self):
        os.close(self.fd)
        if self.socket:
            self.socket.close()


def configured(path):
    config = json.loads(Path(path).read_text())
    config["config_path"] = str(Path(path).absolute())
    loop = Loop(
        config["state"],
        config["control"],
        NativeLit(config["cwd"], config.get("artifact_root", DEFAULT_ROOT)),
    )
    window = NativeWindow(
        WindowCapability(**config["window"]),
        config["cwd"],
        config.get("artifact_root", DEFAULT_ROOT),
    )
    return AutoReset(loop, config["supervisor"], config, window)


def wait_bootstrap(controller, manifest):
    bound = file_binding(manifest)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = controller.status()
        if (
            state.get("reset", {}).get("manifest") == bound
            and state["phase"] == "verified"
        ):
            if file_binding(state["receipt"]["path"]) != state["receipt"]:
                raise ValueError("native receipt changed")
            receipt = json.loads(Path(state["receipt"]["path"]).read_text())
            actual = identity(receipt["transcript"])
            journal = controller.loop.status()
            if (
                not receipt["verified"]
                or (actual["session_id"], actual["model"], actual["effort"])
                != (receipt["session_id"], "gpt-6.1-sol", "high")
                or journal["session_id"] != receipt["session_id"]
            ):
                raise ValueError("actual fresh native bootstrap mismatch")
            return receipt
        time.sleep(
            0.1
        )  # Mechanical receipt arrival only; never grants workflow authority.
    raise ValueError("external native bootstrap receipt not published by deadline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["run", "status", "wait-bootstrap", "release", "recover-maintenance"],
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ownership", type=Path)
    parser.add_argument("--goal-receipt", type=Path)
    parser.add_argument("--recovery-authority", type=Path)
    args = parser.parse_args()
    if args.command == "recover-maintenance" and args.recovery_authority is None:
        parser.error("recover-maintenance requires --recovery-authority")
    controller = configured(args.config)
    try:
        if args.command == "release":
            journal = controller.loop.status()
            owned = json.loads(args.ownership.read_text())["owned_processes"]
            if any(Path(f"/proc/{int(h['pid'])}").exists() for h in owned):
                raise ValueError("owned writer still active")
            controller.retain_goal(args.goal_receipt, journal["session_id"])
            result = dict(
                session_id=journal["session_id"],
                epoch=journal["epoch"],
                completed=sorted(journal["completed"]),
                owned_processes=owned,
                goal_receipt=str(args.goal_receipt.absolute()),
                user_frontier=user_frontier(
                    identity(
                        next(
                            s["transcript"]
                            for s in controller.loop._control()["sessions"]
                            if s["role"] == "buford"
                        )
                    )
                ),
            )
            atomic_json(controller.config["release"], result)
            if controller.status()["phase"] == "maintenance_recovered":
                controller.save(
                    {
                        "phase": "monitoring",
                        "recovery_authority": controller.status()["recovery_authority"],
                    }
                )
        elif args.command == "status":
            result = controller.status()
        elif args.command == "wait-bootstrap":
            result = wait_bootstrap(controller, args.manifest)
        elif args.command == "recover-maintenance":
            with Lease(controller.path.with_suffix(".runtime.lock")):
                result = controller.recover_maintenance(args.recovery_authority)
        else:
            with Lease(controller.path.with_suffix(".runtime.lock")):
                while True:
                    old = controller.status()
                    result = controller.step()
                    if result != old:
                        print(
                            json.dumps(
                                {
                                    "phase": result["phase"],
                                    "nonce": result.get("nonce"),
                                    "receipt": result.get("receipt"),
                                }
                            ),
                            flush=True,
                        )
                        continue
                    routing = next(
                        s
                        for s in controller.loop._control()["sessions"]
                        if s["role"] == "buford"
                    )
                    roots = Path(controller.config["sessions"])
                    today = time.strftime("%Y/%m/%d", time.gmtime())
                    wake = Wakeups(
                        [
                            controller.path.parent,
                            controller.loop.path.parent,
                            controller.loop.control,
                            routing["transcript"],
                            Path(routing["transcript"]).parent,
                            roots / today,
                            Path(controller.config["release"]).parent,
                        ]
                    )
                    try:
                        wake.wait()
                    finally:
                        wake.close()
            return 0
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(
            json.dumps({"held": str(error), "supervisor": str(controller.path)}),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
