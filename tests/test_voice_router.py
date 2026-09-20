import json
from pathlib import Path
import threading
import unittest

from runtime.contracts import Event, Interaction, decode
from runtime.core import ControlPlane, Outcome
from runtime.journal import MemoryJournal
from runtime.voice.router import Action, VoiceRouter, VoiceState


def record(kind, **patch):
    payload = next(item for item in json.loads(Path("tests/fixtures/contracts-v1.json").read_text()) if item["kind"] == kind)
    return decode({**payload, **patch})


class VoiceRouterTests(unittest.TestCase):
    def test_injected_correlation_keeps_distinct_command_ids_and_default_still_works(self):
        router = self.make()
        router.correlation_ids = lambda: 'activation-correlation'
        first = router.handle('show menu')
        self.turn()
        second = router.handle('show menu')
        self.assertEqual(first.result.correlation_id, 'activation-correlation')
        self.assertEqual(second.result.correlation_id, 'activation-correlation')
        self.assertNotEqual(first.result.command_id, second.result.command_id)
        router = self.make()
        first = router.handle('show menu')
        self.turn()
        second = router.handle('show menu')
        self.assertNotEqual(first.result.correlation_id, second.result.correlation_id)

    def make(self, risk="safe", proposal=None, actions=None, capability_patch=None, voice_enabled=True):
        self.calls, self.spoken = [], []
        self.journal = MemoryJournal()
        self.state = VoiceState(dict(record("command").context), "focus-1", "turn-1")
        self.plane = ControlPlane([record("capability", risk=risk, **(capability_patch or {}))], record("policy"),
                                  lambda command: self.calls.append(command) or Outcome("success"),
                                  self.journal, profile=record("profile", voice_enabled=voice_enabled))
        action = Action("menu.open", 1, {"name": "main"}, ("open omarchy menu", "show menu"), "Open Omarchy menu")
        return VoiceRouter(self.plane, actions or [action], lambda: self.state, self.spoken.append, proposal=proposal)

    def turn(self, name="turn-2", **patch):
        self.state = VoiceState(self.state.context, patch.get("key", self.state.key), name,
                                patch.get("muted", False), patch.get("mode", "command"))

    def test_normalized_alias_dispatches_once_without_typing_or_routine_speech(self):
        router = self.make()
        self.assertEqual(router.handle("  OPEN, Omarchy MENU! ").status, "success")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].arguments["name"], "main")
        self.assertEqual(self.spoken, [])
        self.assertEqual(router.handle("show menu").code, "activation.reused")
        self.assertEqual(len(self.calls), 1)

    def test_ambiguous_or_unknown_requires_a_new_activation_to_clarify(self):
        actions = [Action("menu.open", 1, {"name": "main"}, ("open menu",), "Menu"),
                   Action("other.menu", 1, {}, ("open menu",), "Other menu")]
        router = self.make(actions=actions)
        self.assertEqual(router.handle("open menu").status, "clarify")
        self.assertTrue(self.spoken)
        self.assertEqual(self.calls, [])
        self.assertEqual(router.handle("open menu").code, "activation.reused")
        router = self.make()
        self.assertEqual(router.handle("do something unrecognized").status, "clarify")
        self.turn()
        self.assertEqual(router.handle("show menu").status, "success")

    def test_risk_and_correction_preview_then_panel_keyboard_voice_confirmation(self):
        for channel in ("panel", "keyboard", "voice"):
            router = self.make(risk="confirm")
            reply = router.handle("show menu")
            self.assertEqual(reply.status, "preview")
            self.assertEqual(self.calls, [])
            if channel == "voice":
                self.assertEqual(router.confirm(reply.token, channel, "yes").code, "activation.reused")
                self.turn()
            result = router.confirm(reply.token, channel, "yes" if channel == "voice" else True)
            self.assertEqual(result.status, "success")
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(router.confirm(reply.token, "panel", True).status, "blocked")
        router = self.make()
        self.assertEqual(router.handle("show menu", corrected=True).status, "preview")
        self.assertEqual(self.calls, [])

    def test_muted_wrong_mode_stale_context_and_stale_catalog_are_blocked(self):
        for patch in ({"muted": True}, {"mode": "dictation"}):
            router = self.make()
            self.turn("turn-1", **patch)
            self.assertEqual(router.handle("show menu").status, "blocked")
            self.assertEqual(self.calls, [])
            self.assertEqual(self.spoken, [])
        router = self.make(risk="confirm")
        reply = router.handle("show menu")
        self.turn(key="focus-2")
        self.assertEqual(router.confirm(reply.token, "keyboard", True).status, "blocked")
        self.assertEqual(self.calls, [])
        router = self.make(capability_patch={"catalog_version": 2})
        self.assertEqual(router.handle("show menu").result.error.code, "catalog.stale")
        self.assertEqual(self.calls, [])

    def test_risk_blocked_never_executes(self):
        router = self.make(risk="blocked")
        self.assertEqual(router.handle("show menu").status, "blocked")
        self.assertEqual(self.calls, [])

    def test_provider_proposals_are_closed_data_and_never_grant_confirmation(self):
        good = [{"capability_id": "menu.open", "catalog_version": 1, "confidence": 0.95}]
        router = self.make(risk="confirm", proposal=lambda text, actions: good)
        self.assertEqual(router.handle("bring up the controls").status, "preview")
        self.assertEqual(self.calls, [])
        for proposal in ([{**good[0], "confirmed": True}], [{**good[0], "confidence": True}],
                         [{**good[0], "confidence": float("nan")}], [{**good[0], "capability_id": "shell.run"}], "junk"):
            router = self.make(proposal=lambda text, actions: proposal)
            self.assertEqual(router.handle("bring up the controls").status, "clarify")
            self.assertEqual(self.calls, [])

    def test_state_change_during_proposal_blocks_execution_and_speech(self):
        def proposal(text, actions):
            self.turn("turn-1", muted=True)
            return [{"capability_id": "menu.open", "catalog_version": 1, "confidence": 0.95}]
        router = self.make(proposal=proposal)
        self.assertEqual(router.handle("bring up controls").status, "blocked")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.spoken, [])

    def test_journal_failure_prevents_clarification_and_execution(self):
        router = self.make()
        self.journal.close()
        self.assertEqual(router.handle("unknown phrase").status, "blocked")
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.calls, [])

    def test_approximate_or_model_candidate_is_previewed_not_silently_executed(self):
        router = self.make()
        self.assertEqual(router.handle("open omarchy menus").status, "preview")
        self.assertEqual(self.calls, [])
        router = self.make(proposal=lambda *_: [{"capability_id": "menu.open", "catalog_version": 1, "confidence": 0.99}])
        self.assertEqual(router.handle("do not open the menu").status, "preview")
        self.assertEqual(self.calls, [])

    def test_confirmation_is_bound_to_session_context_not_only_focus_key(self):
        router = self.make(risk="confirm")
        reply = router.handle("show menu")
        self.state = VoiceState({**self.state.context, "session_id": "other-session"}, "focus-1", "turn-2")
        self.assertEqual(router.confirm(reply.token, "panel", True).status, "blocked")
        self.assertEqual(self.calls, [])

    def test_state_service_failure_is_explicit_and_never_executes(self):
        router = self.make()
        router.state = lambda: (_ for _ in ()).throw(OSError("private state"))
        self.assertEqual(router.handle("show menu").status, "blocked")
        self.assertEqual(self.calls, [])

    def test_journal_contention_rechecks_state_for_dispatch_and_confirmation(self):
        for confirming in (False, True):
            with self.subTest(confirming=confirming):
                router = self.make(risk="confirm" if confirming else "safe")
                preview = router.handle("show menu") if confirming else None
                self.spoken.clear()
                sampled = threading.Event()
                reads, replies = [], []
                def state():
                    snapshot = self.state
                    reads.append(snapshot)
                    if len(reads) == (1 if confirming else 2):
                        sampled.set()
                    return snapshot
                router.state = state
                operation = (lambda: router.confirm(preview.token, "panel", True)) if confirming else (lambda: router.handle("show menu"))
                worker = threading.Thread(target=lambda: replies.append(operation()))
                with self.journal.dispatch_lock:
                    worker.start()
                    self.assertTrue(sampled.wait(2), "worker did not sample state")
                    self.turn(key="focus-2", muted=True)
                worker.join(2)
                self.assertFalse(worker.is_alive())
                self.assertEqual(replies[0].status, "blocked")
                self.assertEqual(self.calls, [])
                self.assertEqual(self.spoken, [])

    def test_intent_persistence_state_change_prevents_execution(self):
        for confirming in (False, True):
            with self.subTest(confirming=confirming):
                router = self.make(risk="confirm" if confirming else "safe")
                preview = router.handle("show menu") if confirming else None
                append = self.journal.append
                def append_and_change(event):
                    sequence = append(event)
                    if isinstance(event, Event) and event.event_type == "command.started":
                        self.turn(key="focus-2", muted=True)
                    return sequence
                self.journal.append = append_and_change
                reply = router.confirm(preview.token, "panel", True) if confirming else router.handle("show menu")
                self.assertEqual(reply.code, "context.stale")
                self.assertEqual(self.calls, [])

    def test_speech_rechecks_state_after_preview_or_clarification_persistence(self):
        for phase in ("voice.preview", "voice.clarification", "confirmation-answer"):
            with self.subTest(phase=phase):
                router = self.make(risk="confirm" if phase != "voice.clarification" else "safe")
                preview = router.handle("show menu") if phase == "confirmation-answer" else None
                if preview:
                    self.turn()
                self.spoken.clear()
                append = self.journal.append
                def append_and_change(event):
                    sequence = append(event)
                    if isinstance(event, Interaction):
                        self.turn(key="focus-2", muted=True)
                    return sequence
                self.journal.append = append_and_change
                reply = (router.confirm(preview.token, "voice", "maybe") if preview else
                         router.handle("unrecognized phrase" if phase == "voice.clarification" else "show menu"))
                self.assertEqual(reply.code, "context.stale")
                self.assertEqual(self.spoken, [])
                self.assertEqual(self.calls, [])

    def test_stale_preview_cannot_speak_ambiguous_confirmation_prompt(self):
        router = self.make(risk="confirm")
        preview = router.handle("show menu")
        self.spoken.clear()
        self.turn(key="focus-2")
        reply = router.confirm(preview.token, "voice", "maybe")
        self.assertEqual(reply.code, "context.stale")
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.calls, [])

    def test_voice_boundary_overrides_generic_source_and_enforces_profile(self):
        router = self.make(voice_enabled=False)
        self.state = VoiceState({**self.state.context, "source": "terminal"}, "focus-1", "turn-1")
        self.assertEqual(router.handle("show menu").code, "voice.disabled")
        self.assertEqual(self.calls, [])
        self.assertTrue(all(event.context["source"] == "voice" for _, event in self.journal.read()))

    def test_voice_execution_and_preview_journal_have_voice_provenance(self):
        for risk in ("safe", "confirm"):
            with self.subTest(risk=risk):
                router = self.make(risk=risk)
                self.state = VoiceState({**self.state.context, "source": "terminal"}, "focus-1", "turn-1")
                router.handle("show menu")
                self.assertTrue(self.journal.read())
                self.assertTrue(all(event.context["source"] == "voice" for _, event in self.journal.read()))
                if self.calls:
                    self.assertEqual(self.calls[0].context["source"], "voice")

    def test_capture_to_fake_transcription_to_vm_dispatch(self):
        from runtime.voice.capture import CommandCapture, Frame
        capture = CommandCapture()
        started = capture.key_equal()
        capture.feed(Frame(b'\x00' * 16000, True))
        finished = capture.feed(Frame(b'\x00' * 22400, False))
        self.assertEqual(finished.status, "processing")
        self.assertEqual(finished.token, started.token)
        router = self.make()
        self.turn(finished.token)
        def transcribe(audio):
            self.assertEqual(len(audio), 38400)
            return "show menu"
        self.assertEqual(router.handle(transcribe(finished.audio)).status, "success")
        self.assertEqual(capture.complete(finished.token).status, "idle")
        self.assertEqual(len(self.calls), 1)
