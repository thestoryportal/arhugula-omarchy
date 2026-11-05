"""Independent ae7761a findings exercised at public controller boundaries."""

import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ops.orchestration.artifacts import file_binding
from ops.orchestration.native_window import NativeWindow
from ops.orchestration.records import atomic_json
import test_auto_reset


class ResetCorrectionTests(unittest.TestCase):
    setUp = test_auto_reset.AutoResetTests.setUp
    controller = test_auto_reset.AutoResetTests.controller
    hold = test_auto_reset.AutoResetTests.hold
    fresh = test_auto_reset.AutoResetTests.fresh
    recovery_fixture = test_auto_reset.AutoResetTests.recovery_fixture
    prompt_recovery_fixture = test_auto_reset.AutoResetTests.prompt_recovery_fixture

    def pending(self):
        self.hold()
        controller = self.controller()
        for _ in range(3):
            controller.step()
        return controller, self.fresh()

    def execution(self, controller, authority):
        grant = json.loads(authority.read_text())
        config = self.root / "execution-config.json"
        config.write_text(json.dumps(self.config))
        self.config["config_path"] = str(config)
        grant["execution_config"] = file_binding(config)
        authority.write_text(json.dumps(grant))
        return grant

    def no_credit(self, before):
        after = self.loop.status()
        for key in (
            "epoch",
            "epoch_start",
            "epoch_completed",
            "completed",
            "reviews",
            "quarantine",
            "unit_quarantine",
            "reset_requested",
        ):
            self.assertEqual(after.get(key), before.get(key), key)
        self.assertEqual(after["reset"], before["reset"])
        self.assertNotIn("native_receipt", after)

    def delayed_input_log(self):
        original = self.window.context
        self.window.context = lambda *args: {**original(*args), "user_input": False}

    def without_prompt(self, fresh):
        rows = [json.loads(row) for row in fresh.read_text().splitlines()]
        fresh.write_text(
            "".join(
                json.dumps(row) + "\n"
                for row in rows
                if not (
                    row["type"] == "response_item"
                    and row["payload"].get("role") == "user"
                )
            )
        )

    def provisional(self):
        controller, fresh = self.pending()
        with patch.object(controller, "publish", side_effect=OSError("publication")):
            with self.assertRaises(OSError):
                controller.step(fresh)
        return controller, fresh

    def test_rollout_before_input_log_bootstraps_and_publishes_within_gate(self):
        controller, fresh = self.pending()
        self.delayed_input_log()
        self.clock = controller.status()["started"] + 119
        result = controller.step(fresh)
        self.assertEqual(result["phase"], "verified")
        self.assertEqual(self.loop.status()["epoch"], 1)
        self.assertFalse(
            json.loads(Path(result["receipt"]["path"]).read_text())["native_context"][
                "user_input"
            ]
        )
        self.assertEqual(len(self.window.queued), 1)

    def test_pending_prompt_waits_without_effects_then_readies_on_original_clock(self):
        controller, fresh = self.pending()
        complete = fresh.read_bytes()
        self.without_prompt(fresh)
        self.delayed_input_log()
        before, supervisor = self.loop.status(), controller.status()
        routing = self.loop.control.read_bytes()
        self.clock = supervisor["started"] + 119
        for _ in range(2):
            self.assertEqual(controller.step(fresh), supervisor)
            self.assertEqual(self.loop.status(), before)
            self.assertEqual(self.loop.control.read_bytes(), routing)
            self.assertFalse(Path(self.config["receipt_directory"]).exists())
            self.assertEqual(len(self.window.queued), 1)
        fresh.write_bytes(complete)
        self.assertEqual(controller.step(fresh)["phase"], "verified")
        self.assertEqual(controller.status()["started"], supervisor["started"])

    def test_publication_waits_for_prompt_without_acceptance_or_replay(self):
        controller, fresh = self.provisional()
        complete = fresh.read_bytes()
        self.without_prompt(fresh)
        self.delayed_input_log()
        before, supervisor = self.loop.status(), controller.status()
        self.clock = supervisor["started"] + 119
        self.assertEqual(controller.step(fresh), supervisor)
        self.assertEqual(self.loop.status(), before)
        self.assertFalse(Path(self.config["receipt_directory"]).exists())
        self.assertEqual(len(self.window.queued), 1)
        fresh.write_bytes(complete)
        self.assertEqual(controller.step(fresh)["phase"], "verified")
        self.assertEqual(controller.status()["started"], supervisor["started"])

    def test_pending_delivery_and_publication_refuse_original_deadline(self):
        for publication in (False, True):
            with self.subTest(publication=publication):
                self.setUp()
                controller, fresh = (
                    self.provisional() if publication else self.pending()
                )
                self.without_prompt(fresh)
                self.delayed_input_log()
                before = self.loop.status()
                self.clock = controller.status()["started"] + 121
                with self.assertRaisesRegex(ValueError, "deadline"):
                    controller.step(fresh)
                self.assertEqual(self.loop.status(), before)
                self.assertEqual(len(self.window.queued), 1)

    def test_missing_rollout_or_model_waits_in_both_delivery_phases(self):
        for publication in (False, True):
            for kind in ("no-rollout", "empty-rollout", "no-model"):
                with self.subTest(publication=publication, kind=kind):
                    self.setUp()
                    controller, fresh = (
                        self.provisional() if publication else self.pending()
                    )
                    if kind == "no-rollout":
                        observed = self.window.context({}, "old")
                        self.window.rollouts = []
                        self.window.context = lambda *args: {
                            **observed,
                            "transcript": None,
                        }
                    elif kind == "empty-rollout":
                        observed = self.window.context({}, "old")
                        self.window.context = lambda *args: observed
                        fresh.write_text("")
                    else:
                        rows = [
                            json.loads(row) for row in fresh.read_text().splitlines()
                        ]
                        fresh.write_text(
                            "".join(
                                json.dumps(row) + "\n"
                                for row in rows
                                if row["type"] != "turn_context"
                            )
                        )
                    self.delayed_input_log()
                    before, supervisor = self.loop.status(), controller.status()
                    if publication and kind == "empty-rollout":
                        # A once-published routing identity cannot be erased as pending.
                        with self.assertRaises(ValueError):
                            controller.step()
                    else:
                        self.assertEqual(controller.step(), supervisor)
                    self.assertEqual(self.loop.status(), before)
                    self.assertEqual(len(self.window.queued), 1)

    def test_delivery_and_publication_refuse_identity_or_prompt_contradiction(self):
        for publication in (False, True):
            for kind in (
                "session_id",
                "created_at",
                "process_uuid",
                "creation_log_id",
                "missing",
                "prompt",
                "extra-input",
            ):
                with self.subTest(publication=publication, kind=kind):
                    self.setUp()
                    controller, fresh = (
                        self.provisional() if publication else self.pending()
                    )
                    original = self.window.context
                    if kind == "missing":
                        self.window.context = lambda *args: None
                    elif kind in ("prompt", "extra-input"):
                        with fresh.open("a") as stream:
                            stream.write(
                                json.dumps(
                                    {
                                        "type": "response_item",
                                        "payload": {
                                            "role": "user",
                                            "content": [{"text": "changed"}],
                                        },
                                    }
                                )
                                + "\n"
                            )
                        if kind == "prompt":
                            self.without_prompt(fresh)
                            with fresh.open("a") as stream:
                                stream.write(
                                    json.dumps(
                                        {
                                            "type": "response_item",
                                            "payload": {
                                                "role": "user",
                                                "content": [{"text": "changed"}],
                                            },
                                        }
                                    )
                                    + "\n"
                                )
                    else:
                        self.window.context = lambda *args: {
                            **original(*args),
                            kind: "changed",
                        }
                    before = self.loop.status()
                    with self.assertRaises(ValueError):
                        controller.step(fresh)
                    self.assertEqual(self.loop.status(), before)
                    self.assertEqual(len(self.window.queued), 1)

    def test_late_supervisor_recovery_uses_durable_acceptance_after_native_evidence_loss(
        self,
    ):
        controller, fresh = self.pending()
        with patch.object(controller, "save", side_effect=OSError("supervisor")):
            with self.assertRaises(OSError):
                controller.step(fresh)
        accepted = self.loop.status()
        self.clock = controller.status()["started"] + 121
        self.window.context = lambda *args: None
        self.window.name = "later activity"
        result = controller.step(fresh)
        self.assertEqual(result["phase"], "verified")
        self.assertEqual(self.loop.status(), accepted)
        self.assertEqual(len(self.window.queued), 1)

    def test_bootstrap_is_provisional_and_late_publication_has_no_credit(self):
        controller, fresh = self.pending()
        before = self.loop.status()
        with patch.object(controller, "publish", side_effect=OSError("publication")):
            with self.assertRaises(OSError):
                controller.step(fresh)
        self.no_credit(before)
        self.clock += 121
        with self.assertRaisesRegex(ValueError, "deadline"):
            controller.step(fresh)
        self.no_credit(before)

    def test_receipt_fsync_crossing_deadline_leaves_only_provisional_evidence(self):
        controller, fresh = self.pending()
        before = self.loop.status()

        def late(path, data, **kwargs):
            atomic_json(path, data, **kwargs)
            if "bootstrap" in data:
                self.clock += 121

        with patch("ops.orchestration.auto_reset.atomic_json", side_effect=late):
            with self.assertRaisesRegex(ValueError, "deadline"):
                controller.step(fresh)
        candidate = json.loads(
            (
                Path(self.config["receipt_directory"])
                / (controller.status()["nonce"] + ".json")
            ).read_text()
        )
        self.assertFalse(candidate["verified"])
        self.no_credit(before)

    def test_distinct_uuid_and_metadata_creation_times_recover(self):
        controller, authority, fresh, _ = self.prompt_recovery_fixture()
        rows = fresh.read_text().splitlines()
        meta = json.loads(rows[0])
        meta["payload"]["timestamp"] = (
            datetime.fromisoformat(self.window.created) + timedelta(milliseconds=5)
        ).isoformat()
        rows[0] = json.dumps(meta)
        fresh.write_text("\n".join(rows) + "\n")
        self.execution(controller, authority)
        controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["epoch"], 0)
        self.assertEqual(self.loop.status()["session_id"], "third")

    def test_reviewed_execution_config_can_change_without_rewriting_failed_config(self):
        controller, authority, fresh, _ = self.prompt_recovery_fixture()
        grant = json.loads(authority.read_text())
        historical = Path(grant["config"]["path"]).read_bytes()
        source = self.root / "installed-reviewed-source.py"
        source.write_text("reviewed candidate")
        self.config["source_acceptance"].append(file_binding(source))
        self.execution(controller, authority)
        controller.recover_maintenance(authority)
        self.assertEqual(Path(grant["config"]["path"]).read_bytes(), historical)
        self.assertEqual(self.loop.status()["epoch"], 0)

    def test_running_candidate_cannot_attest_different_installed_blobs(self):
        controller = self.controller()
        old = self.root / "auto_reset.py"
        old.write_text("retained old installed candidate")
        self.config["source_acceptance"] = [file_binding(old)]
        with self.assertRaisesRegex(ValueError, "executing"):
            controller.bindings()

    def test_proven_pre_dispatch_refusal_can_resample_without_retargeting(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        original = self.window.context
        observed = original({}, "old")
        self.window.queue = lambda context, frontier, previous, text: (
            NativeWindow.queue(self.window, context, frontier, previous, text)
        )
        calls = []
        self.window.command = lambda argv: calls.append(argv)
        count = 0

        def changes(*args):
            nonlocal count
            count += 1
            return original(*args) if count == 1 else {**observed, "user_input": True}

        self.window.context = changes
        with self.assertRaises(ValueError):
            controller.step()
        self.assertEqual(calls, [])
        self.assertEqual(controller.status()["phase"], "prompt_refused")
        self.window.context = original
        self.window.queue = lambda context, frontier, previous, text: (
            self.window.queued.append((context["session_id"], text))
            or {"session_id": context["session_id"], "message_id": "test"}
        )
        controller.step()
        self.assertEqual(len(self.window.queued), 1)
        self.assertEqual(len(controller.status()["queue_refusals"]), 1)

    def test_uncertain_dispatch_never_replays(self):
        self.hold()
        controller = self.controller()
        controller.step()
        controller.step()
        calls = []

        def uncertain(*args):
            calls.append(args)
            raise OSError("queue transport nonzero")

        self.window.queue = uncertain
        with self.assertRaises(OSError):
            controller.step()
        with self.assertRaisesRegex(ValueError, "uncertain"):
            controller.step()
        self.assertEqual(len(calls), 1)

    def rebound(self, authority, **paths):
        grant = json.loads(authority.read_text())
        for key, path in paths.items():
            snapshot = Path(grant[key]["path"])
            snapshot.write_bytes(Path(path).read_bytes())
            grant[key] = file_binding(snapshot)
        authority.write_text(json.dumps(grant))
        return grant

    def test_expired_provisional_transfer_recovers_via_normal_apis_without_credit(self):
        for boundary in (
            "intent",
            "route",
            "publication",
            "receipt",
            "acknowledgement",
        ):
            with self.subTest(boundary=boundary):
                self.setUp()
                controller, authority, fresh, _ = self.prompt_recovery_fixture()
                self.clock -= 121
                before = self.loop.status()
                save = self.loop._save

                def interrupt(state):
                    save(state)
                    if boundary == "intent" and state.get("pending_bootstrap"):
                        raise OSError("after intent")
                    if boundary == "route" and state.get("awaiting_native_receipt"):
                        raise OSError("after route")
                    if boundary == "acknowledgement" and state.get(
                        "pending_native_receipt"
                    ):
                        self.clock += 121

                def late_receipt(path, data, **kwargs):
                    atomic_json(path, data, **kwargs)
                    if "bootstrap" in data:
                        self.clock += 121

                if boundary == "publication":
                    target = patch.object(
                        controller, "publish", side_effect=OSError(boundary)
                    )
                elif boundary == "receipt":
                    target = patch(
                        "ops.orchestration.auto_reset.atomic_json",
                        side_effect=late_receipt,
                    )
                else:
                    target = patch.object(self.loop, "_save", side_effect=interrupt)
                with target:
                    with self.assertRaises((OSError, ValueError)):
                        controller.step(fresh)
                self.no_credit(before)
                self.rebound(
                    authority,
                    journal=self.loop.path,
                    routing=self.loop.control,
                    supervisor=controller.path,
                    goal_ledger=self.config["goal_ledger"],
                )
                self.execution(controller, authority)
                self.clock = controller.status()["started"] + 121
                recovered = controller.recover_maintenance(authority)
                self.assertFalse(recovered["automatic_acceptance"])
                for key in (
                    "epoch",
                    "epoch_start",
                    "completed",
                    "reviews",
                    "quarantine",
                ):
                    self.assertEqual(self.loop.status()[key], before[key])
                self.assertEqual(self.loop.status()["session_id"], "third")
                self.assertTrue(self.loop.status()["maintenance_only"])
                self.assertFalse(self.loop.status()["awaiting_native_receipt"])
                self.assertEqual(controller.recover_maintenance(authority), recovered)

    def test_deadline_crossing_lit_or_acknowledgement_cannot_earn_credit(self):
        for boundary in ("lit", "acknowledgement"):
            with self.subTest(boundary=boundary):
                self.setUp()
                controller, fresh = self.pending()
                before = self.loop.status()
                if boundary == "lit":
                    original = self.loop.lit.read

                    def slow(*args):
                        result = original(*args)
                        self.clock += 121
                        return result

                    target = patch.object(self.loop.lit, "read", side_effect=slow)
                else:
                    original = self.loop._save

                    def slow(state):
                        original(state)
                        if state.get("pending_native_receipt"):
                            self.clock += 121

                    target = patch.object(self.loop, "_save", side_effect=slow)
                with target:
                    with self.assertRaisesRegex(ValueError, "deadline"):
                        controller.step(fresh)
                self.no_credit(before)

    def test_provisional_crashes_retry_once_without_history_loss(self):
        for boundary in (
            "intent",
            "route",
            "journal",
            "ack_intent",
            "accepted",
            "supervisor",
        ):
            with self.subTest(boundary=boundary):
                self.setUp()
                controller, fresh = self.pending()
                before = self.loop.status()
                original = self.loop._save
                fired = False

                def crash(state):
                    nonlocal fired
                    match = (
                        boundary == "intent"
                        and state.get("pending_bootstrap")
                        and not state.get("awaiting_native_receipt")
                        or boundary == "route"
                        and state.get("last_bootstrap")
                        and not state.get("pending_native_receipt")
                        or boundary == "journal"
                        and state.get("last_bootstrap")
                        and not state.get("pending_native_receipt")
                        or boundary == "ack_intent"
                        and state.get("pending_native_receipt")
                        or boundary == "accepted"
                        and state.get("native_receipt")
                    )
                    if match and not fired:
                        fired = True
                        if boundary != "route":
                            original(state)
                        raise OSError(boundary)
                    original(state)

                if boundary == "supervisor":
                    target = patch.object(
                        controller, "save", side_effect=OSError(boundary)
                    )
                else:
                    target = patch.object(self.loop, "_save", side_effect=crash)
                with target:
                    with self.assertRaises(OSError):
                        controller.step(fresh)
                if boundary not in ("accepted", "supervisor"):
                    self.no_credit(before)
                else:
                    # Durable in-deadline acceptance survives a later supervisor crash.
                    self.clock += 121
                result = controller.step(fresh)
                self.assertEqual(result["phase"], "verified")
                self.assertEqual(self.loop.status()["epoch"], 1)
                for key in ("completed", "reviews", "quarantine", "unit_quarantine"):
                    self.assertEqual(self.loop.status()[key], before[key])
                self.assertEqual(len(self.window.queued), 1)
                self.assertEqual(len(self.window.lines), 1)

    def test_config_recovery_denies_every_other_key_and_wrong_attestation(self):
        controller, authority, fresh, _ = self.prompt_recovery_fixture()
        self.execution(controller, authority)
        original = copy.deepcopy(self.config)
        # [LAW:behavior-not-structure] Every protected value is changed and bound
        # as the execution config; the immutable history must still refuse it.
        for key in set(original) - {"source_acceptance", "config_path"}:
            with self.subTest(key=key):
                self.config.clear()
                self.config.update(copy.deepcopy(original))
                self.config[key] = (
                    {**original[key], "changed": True}
                    if isinstance(original[key], dict)
                    else "changed"
                )
                self.execution(controller, authority)
                with self.assertRaises((ValueError, OSError)):
                    controller.recover_maintenance(authority)
                self.assertEqual(self.loop.status()["session_id"], "new")
        self.config.clear()
        self.config.update(original)
        self.execution(controller, authority)
        for mutation in (
            "wrong-file",
            "changed-file",
            "wrong-effective",
            "changed-source",
        ):
            with self.subTest(mutation=mutation):
                self.config.clear()
                self.config.update(copy.deepcopy(original))
                grant = self.execution(controller, authority)
                if mutation == "wrong-file":
                    grant["execution_config"]["sha256"] = "0" * 64
                    authority.write_text(json.dumps(grant))
                elif mutation == "changed-file":
                    Path(self.config["config_path"]).write_text("{}")
                elif mutation == "wrong-effective":
                    self.config["source_acceptance"] = []
                else:
                    Path(self.config["source_acceptance"][0]["path"]).write_text(
                        "unreviewed"
                    )
                with self.assertRaises(ValueError):
                    controller.recover_maintenance(authority)

    def refresh_chain(self, controller, authority):
        grant = json.loads(authority.read_text())
        before = controller.status()["control_snapshot"]
        steps = []
        left = self.root / "chain-start.json"
        left.write_text(json.dumps(before))
        initial = file_binding(left)
        previous = next(s for s in before["sessions"] if s["role"] == "implementer")[
            "session_id"
        ]
        starting_session = previous
        for n in range(2):
            after = copy.deepcopy(before)
            row = next(s for s in after["sessions"] if s["role"] == "implementer")
            session = "impl-step-" + str(n)
            row.update(
                session_id=session, transcript=str(self.root / (session + ".jsonl"))
            )
            right = self.root / ("chain-after-" + str(n) + ".json")
            right.write_text(json.dumps(after))
            creation = self.root / ("chain-creation-" + str(n) + ".json")
            created = {
                "session_id": session,
                "created_at": "creation",
                "creation_log_id": n,
                "process_uuid": "same-process",
                "transcript": None,
                "user_input": False,
            }
            creation.write_text(json.dumps(created))
            proof = self.root / ("chain-proof-" + str(n) + ".json")
            proof.write_text(
                json.dumps(
                    {**created, "user_input": True, "transcript": row["transcript"]}
                )
            )
            delivery = self.root / ("chain-delivery-" + str(n) + ".json")
            delivery.write_text(
                json.dumps(
                    {"session_id": session, "model": "gpt-6.1-sol", "effort": "high"}
                )
            )
            step = self.root / ("chain-step-" + str(n) + ".json")
            step.write_text(
                json.dumps(
                    {
                        "kind": "authorized-idle-implementer-native-refresh",
                        "production_paused": True,
                        "native_acceptance": False,
                        "previous_session": previous,
                        "session_id": session,
                        "control_before": file_binding(left),
                        "control_after": file_binding(right),
                        "native_creation": file_binding(creation),
                        "current_native_proof": file_binding(proof),
                        "delivery": file_binding(delivery),
                    }
                )
            )
            steps.append(file_binding(step))
            before, previous, left = after, session, right
        self.f.control.write_bytes(left.read_bytes())
        routing = Path(grant["routing"]["path"])
        routing.write_bytes(left.read_bytes())
        grant["routing"] = file_binding(routing)
        refresh = self.root / "chain.json"
        refresh.write_text(
            json.dumps(
                {
                    "kind": "authorized-idle-implementer-native-refresh",
                    "production_paused": True,
                    "native_acceptance": False,
                    "previous_session": starting_session,
                    "immediate_previous_session": "impl-step-0",
                    "session_id": "impl-step-1",
                    "control_before": initial,
                    "control_after": file_binding(left),
                    "delivery": file_binding(delivery),
                    "refresh_chain": steps,
                }
            )
        )
        grant["implementer_refresh"] = file_binding(refresh)
        authority.write_text(json.dumps(grant))
        return grant, refresh

    def test_truthful_two_step_refresh_chain_is_consumed(self):
        controller, authority, fresh = self.recovery_fixture(routing_refresh=True)
        self.refresh_chain(controller, authority)
        controller.recover_maintenance(authority)
        self.assertEqual(self.loop.status()["epoch"], 0)
        self.assertEqual(
            self.loop._control()["sessions"][-1]["session_id"], "impl-step-1"
        )

    def test_altered_chain_cannot_hide_missing_steps_or_foreign_routing(self):
        for mutation in (
            "missing",
            "missing-chain",
            "reorder",
            "adjacency",
            "hash",
            "foreign",
            "creation",
            "predecessor",
        ):
            with self.subTest(mutation=mutation):
                self.setUp()
                controller, authority, fresh = self.recovery_fixture(
                    routing_refresh=True
                )
                grant, path = self.refresh_chain(controller, authority)
                aggregate = json.loads(path.read_text())
                steps = aggregate["refresh_chain"]
                if mutation == "missing":
                    steps.pop(0)
                elif mutation == "missing-chain":
                    aggregate.pop("refresh_chain")
                elif mutation == "reorder":
                    steps.reverse()
                elif mutation == "hash":
                    steps[0]["sha256"] = "0" * 64
                elif mutation == "predecessor":
                    aggregate["immediate_previous_session"] = "invented"
                else:
                    step_path = Path(steps[0]["path"])
                    step = json.loads(step_path.read_text())
                    if mutation == "adjacency":
                        step["previous_session"] = "foreign"
                    elif mutation == "creation":
                        proof_path = Path(step["current_native_proof"]["path"])
                        proof = json.loads(proof_path.read_text())
                        proof["creation_log_id"] = 999
                        proof_path.write_text(json.dumps(proof))
                        step["current_native_proof"] = file_binding(proof_path)
                    else:
                        routing_path = Path(step["control_after"]["path"])
                        routing = json.loads(routing_path.read_text())
                        routing["sessions"][1]["session_id"] = "foreign"
                        routing_path.write_text(json.dumps(routing))
                        step["control_after"] = file_binding(routing_path)
                    step_path.write_text(json.dumps(step))
                    steps[0] = file_binding(step_path)
                path.write_text(json.dumps(aggregate))
                grant["implementer_refresh"] = file_binding(path)
                authority.write_text(json.dumps(grant))
                with self.assertRaises(ValueError):
                    controller.recover_maintenance(authority)
                self.assertEqual(self.loop.status()["session_id"], "old")


if __name__ == "__main__":
    unittest.main()
