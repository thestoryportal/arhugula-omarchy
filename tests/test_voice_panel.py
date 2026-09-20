"""Headless panel model through the real closed control dispatcher."""
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest

from runtime.voice.control import ControlDispatcher, ControlState
from runtime.voice.router import VoiceState
from runtime.contracts import decode
from runtime.core import ControlPlane, Outcome
from runtime.journal import MemoryJournal
from runtime.voice.router import Action, VoiceRouter
from ui.voice_panel import VoicePanelModel


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.state = VoiceState({'profile_id': 'p'}, 'epoch-1', 'turn-1')
        self.now = 1000
        self.confirmations = []
        handlers = {op: lambda request: False for op in
                    ('activate', 'cancel', 'mute', 'dictation-start', 'dictation-stop', 'confirm')}
        handlers['confirm'] = lambda request: self.confirmations.append(request) or True
        self.dispatcher = ControlDispatcher('session-1', handlers,
            lambda: ControlState(self.state.key, 'idle', self.state.muted))
        self.panel = VoicePanelModel(lambda: self.state,
            lambda payload: self.dispatcher.handle(payload, peer_uid=os.geteuid()),
            clock=lambda: self.now)
        self.panel.connect('session-1')

    def preview(self, token='private-token'):
        return self.panel.present_preview(token, 'Open Omarchy menu', 2000, state=self.state)

    def test_private_preview_displays_countdown_and_sends_one_bound_confirmation(self):
        self.assertTrue(self.preview())
        view = self.panel.view()
        self.assertEqual(view['capability_label'], 'Open Omarchy menu')
        self.assertEqual(view['expires_in_ms'], 1000)
        self.assertTrue(view['can_confirm'])
        self.assertNotIn('private-token', json.dumps(view))
        self.assertTrue(self.panel.confirm(True))
        self.assertFalse(self.panel.confirm(True))
        self.assertEqual(len(self.confirmations), 1)
        sent = self.confirmations[0]
        self.assertEqual((sent['token'], sent['channel'], sent['approved'], sent['session_id'], sent['context_epoch']),
                         ('private-token', 'panel', True, 'session-1', 'epoch-1'))

    def test_full_context_staleness_removes_preview_and_prevents_dispatch(self):
        for patch in ({'context': {'profile_id': 'q'}}, {'key': 'epoch-2'},
                      {'activation_id': 'turn-2'}, {'muted': True}, {'mode': 'dictation'}):
            with self.subTest(patch=patch):
                self.setUp()
                self.preview()
                self.state = replace(self.state, **patch)
                self.assertFalse(self.panel.confirm(True))
                self.assertFalse(self.panel.view()['can_confirm'])
                self.assertEqual(self.confirmations, [])

    def test_expiry_and_clock_rollback_fail_closed(self):
        for now in (2000, 999):
            with self.subTest(now=now):
                self.setUp()
                self.preview()
                self.now = now
                self.assertFalse(self.panel.confirm(True))
                self.now = 1000
                self.assertFalse(self.panel.view()['can_confirm'])
                self.assertEqual(self.confirmations, [])

    def test_reconnect_discards_old_preview_and_replayed_token(self):
        self.preview()
        self.panel.disconnect()
        self.panel.connect('session-1')
        self.assertFalse(self.panel.confirm(True))
        self.assertFalse(self.preview())
        self.assertTrue(self.preview('fresh-token'))

    def test_keyboard_shortcuts_are_focused_only_and_preserve_channel(self):
        self.preview()
        self.assertFalse(self.panel.key('Return', focused=False))
        self.assertEqual(self.confirmations, [])
        self.assertTrue(self.panel.key('Escape', focused=True))
        self.assertEqual(self.confirmations[0]['channel'], 'keyboard')
        self.assertFalse(self.confirmations[0]['approved'])

    def test_disconnected_and_stale_issuance_cannot_create_preview(self):
        self.panel.disconnect()
        self.assertFalse(self.preview())
        self.panel.connect('session-1')
        self.assertFalse(self.panel.present_preview('token', 'Menu', 2000,
                         state=replace(self.state, key='old-epoch')))

    def test_reentrant_disconnect_during_confirm_prevents_delivery(self):
        self.preview()
        def state():
            self.panel.disconnect()
            self.panel.connect('session-1')
            return self.state
        self.panel.state = state
        self.assertFalse(self.panel.confirm(True))
        self.assertEqual(self.confirmations, [])

    def test_exception_after_delivery_never_retries_or_leaks_details(self):
        def send(payload):
            self.confirmations.append(payload)
            raise RuntimeError('private-token private speech')
        self.panel.send_control = send
        self.preview()
        self.assertFalse(self.panel.confirm(True))
        self.assertEqual(self.panel.code, 'panel.uncertain')
        self.assertFalse(self.panel.confirm(True))
        self.assertFalse(self.preview())
        self.assertEqual(len(self.confirmations), 1)
        self.assertNotIn('private-token', json.dumps(self.panel.view()))

    def test_phase_and_degraded_state_survive_without_speech_or_preview(self):
        self.panel.update_status('processing', degraded=True)
        view = self.panel.view()
        self.assertEqual(view['phase'], 'processing')
        self.assertTrue(view['degraded'])
        self.assertFalse(view['can_confirm'])

    def test_invalid_private_preview_fields_fail_closed(self):
        for token, label, expiry in [('bad token', 'Menu', 2000),
                                      ('token', 'Menu\nInjected', 2000),
                                      ('token', 'Menu', float('nan')),
                                      ('token', 'Menu', 31001)]:
            with self.subTest(token=token, label=label, expiry=expiry):
                self.assertFalse(self.panel.present_preview(token, label, expiry, state=self.state))
        self.assertEqual(self.confirmations, [])

    def test_nested_context_mutation_cannot_refresh_preview_authority(self):
        self.preview()
        self.state.context['profile_id'] = 'other'
        self.assertFalse(self.panel.confirm(True))
        self.assertEqual(self.confirmations, [])

    def test_disconnect_during_countdown_cannot_leave_enabled_view(self):
        self.preview()
        calls = 0
        def clock():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.panel.disconnect()
            return self.now
        self.panel._clock = clock
        view = self.panel.view()
        self.assertFalse(view['can_confirm'])
        self.assertIsNone(view['preview'])

    def test_panel_controls_reach_real_vm_policy_and_execute_exactly_once(self):
        fixtures = json.loads(Path('tests/fixtures/contracts-v1.json').read_text())
        def record(kind, **patch):
            return decode({**next(item for item in fixtures if item['kind'] == kind), **patch})
        executed = []
        self.state = VoiceState(record('command').context, 'epoch-1', 'turn-1')
        plane = ControlPlane([record('capability', risk='confirm')], record('policy'),
            lambda command: executed.append(command) or Outcome('success'), MemoryJournal(),
            profile=record('profile', voice_enabled=True), clock=lambda: self.now)
        router = VoiceRouter(plane,
            [Action('menu.open', 1, {'name': 'main'}, ('show menu',), 'Open menu')],
            lambda: self.state, lambda prompt: None)
        reply = router.handle('show menu')
        self.assertEqual(reply.status, 'preview')
        self.assertEqual(executed, [])
        self.dispatcher.handlers['confirm'] = lambda request: router.confirm(
            request['token'], request['channel'], request['approved']).status == 'success'
        self.assertTrue(self.panel.present_preview(reply.token, 'Open menu', self.now + 30000, state=self.state))
        self.assertTrue(self.panel.confirm(True))
        self.assertFalse(self.panel.confirm(True))
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0].capability_id, 'menu.open')

    def test_preview_replay_memory_is_bounded_without_evicting_consumed_tokens(self):
        for number in range(4096):
            self.assertTrue(self.preview('token-' + str(number)))
        self.assertFalse(self.preview('one-more'))
        self.assertFalse(self.preview('token-0'))
        self.assertFalse(self.panel.view()['can_confirm'])
