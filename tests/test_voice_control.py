import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from runtime.voice.control import ControlDispatcher, ControlState, LocalControlServer, decode_control


def request(op='activate', **patch):
    return json.dumps({'version': 1, 'op': op, 'request_id': 'request-1',
                       'session_id': 'session-1', 'context_epoch': 'epoch-1', **patch}).encode()


class ControlTests(unittest.TestCase):
    def dispatcher(self):
        self.calls = []
        self.state = ControlState('epoch-1', 'idle', False)
        handlers = {op: lambda data, op=op: self.calls.append(op) or True
                    for op in ('activate', 'cancel', 'mute', 'dictation-start', 'dictation-stop', 'confirm')}
        return ControlDispatcher('session-1', handlers, lambda: self.state)

    def test_closed_parser_accepts_only_typed_operations(self):
        self.assertEqual(decode_control(b'{"version":1,"op":"status"}'), {'version': 1, 'op': 'status'})
        for op, fields in (('activate', {}), ('cancel', {}), ('dictation-start', {}),
                          ('dictation-stop', {}), ('mute', {'muted': True}),
                          ('confirm', {'token': 'private-token', 'channel': 'panel', 'approved': True})):
            self.assertEqual(decode_control(request(op, **fields))['op'], op)

    def test_unknown_duplicate_oversize_malformed_and_forged_approval_rejected(self):
        for data in (
            b'{"version":1,"op":"shell","command":"true"}',
            b'{"version":1,"op":"cancel","op":"activate"}',
            b'{"version":true,"op":"status"}', b'{"version":2,"op":"status"}',
            b'{"version":1,"op":"status","approved":true}', b'[]', b'\xff',
            b' ' * 4097, bytearray(b'{}'), request(request_id=''), request(context_epoch=''),
            request(approved=True), request('mute', muted=1),
            request('confirm', token='secret', channel='voice', approved=True),
            request('confirm', token='secret', channel='panel', approved='yes'),
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_control(data)

    def test_peer_session_epoch_and_replay_checks_precede_mutation(self):
        dispatcher = self.dispatcher()
        for data, uid in ((request(), os.geteuid() + 1),
                          (request(session_id='old-session'), os.geteuid()),
                          (request(context_epoch='old-epoch'), os.geteuid())):
            self.assertEqual(dispatcher.handle(data, peer_uid=uid)['status'], 'blocked')
        self.assertEqual(self.calls, [])
        self.assertEqual(dispatcher.handle(request(), peer_uid=os.geteuid())['status'], 'ok')
        self.assertEqual(dispatcher.handle(request(), peer_uid=os.geteuid())['code'], 'control.replayed')
        self.assertEqual(self.calls, ['activate'])

    def test_failed_mutation_is_not_retried_and_exception_text_is_private(self):
        dispatcher = self.dispatcher()
        def fail(data):
            raise RuntimeError('private transcript or token')
        dispatcher.handlers['activate'] = fail
        reply = dispatcher.handle(request(), peer_uid=os.geteuid())
        self.assertEqual(reply['status'], 'uncertain')
        self.assertNotIn('private', json.dumps(reply))
        self.assertEqual(dispatcher.handle(request(), peer_uid=os.geteuid())['code'], 'control.replayed')

    def test_request_history_is_bounded_and_status_remains_available(self):
        dispatcher = self.dispatcher()
        for index in range(4096):
            reply = dispatcher.handle(request(request_id=f'request-{index}'), peer_uid=os.geteuid())
            self.assertEqual(reply['status'], 'ok')
        self.assertEqual(dispatcher.handle(request(request_id='overflow'), peer_uid=os.geteuid())['code'],
                         'control.exhausted')
        reply = dispatcher.handle(b'{"version":1,"op":"status"}', peer_uid=os.geteuid())
        self.assertEqual(reply['state'], {'session_id': 'session-1', 'context_epoch': 'epoch-1',
                                          'phase': 'idle', 'muted': False})
        self.assertNotIn('token', json.dumps(reply))
        self.assertNotIn('transcript', json.dumps(reply))

    def test_reentrant_status_callback_cannot_start_another_mutation(self):
        dispatcher = self.dispatcher()
        nested = []
        def state():
            nested.append(dispatcher.handle(request(request_id='nested'), peer_uid=os.geteuid()))
            return self.state
        dispatcher.state = state
        reply = dispatcher.handle(request(), peer_uid=os.geteuid())
        self.assertEqual(reply['status'], 'ok')
        self.assertTrue(all(item['code'] == 'control.busy' for item in nested))
        self.assertEqual(self.calls, ['activate'])

    def test_state_drift_before_handler_consumes_id_without_mutating(self):
        dispatcher = self.dispatcher()
        samples = iter([ControlState('epoch-1', 'idle', False), ControlState('epoch-2', 'idle', False)])
        dispatcher.state = lambda: next(samples)
        self.assertEqual(dispatcher.handle(request(), peer_uid=os.geteuid())['code'], 'control.stale')
        self.assertEqual(self.calls, [])
        dispatcher.state = lambda: self.state
        self.assertEqual(dispatcher.handle(request(), peer_uid=os.geteuid())['code'], 'control.replayed')

    def test_schema_documents_all_and_only_allowed_operations(self):
        schema = json.loads(Path('schemas/voice-session-v1.json').read_text())
        self.assertEqual({item['properties']['op']['const'] for item in schema['oneOf']},
                         {'activate', 'cancel', 'status', 'mute', 'dictation-start', 'dictation-stop', 'confirm'})

    def test_default_cli_is_dry_run_and_live_flag_cannot_grant_authority(self):
        for args, code in (([], 0), (['--live'], 2)):
            result = subprocess.run([sys.executable, '-m', 'ops.voice_session', *args],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['external_execution'])
            self.assertFalse(report['listening'])


class SocketControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.calls = []
        handlers = {op: lambda data, op=op: self.calls.append(op) or True
                    for op in ('activate', 'cancel', 'mute', 'dictation-start', 'dictation-stop', 'confirm')}
        self.dispatcher = ControlDispatcher('session-1', handlers,
                                            lambda: ControlState('epoch-1', 'idle', False))

    def start(self):
        server = LocalControlServer(self.path, self.dispatcher, timeout_s=0.1)
        server.start()
        self.addCleanup(server.close)
        return server

    def client(self, server, data):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(client.close)
        client.settimeout(1)
        client.connect(str(server.path))
        client.sendall(data)
        return client

    def test_owned_socket_and_one_length_bounded_request(self):
        server = self.start()
        self.assertEqual(server.path.stat().st_mode & 0o777, 0o600)
        data = request()
        client = self.client(server, struct.pack('!I', len(data)) + data)
        self.assertTrue(server.serve_once())
        reply = json.loads(client.recv(4096))
        self.assertEqual(reply['status'], 'ok')
        self.assertEqual(self.calls, ['activate'])
        server.close()
        self.assertFalse(server.path.exists())
        self.assertTrue(self.path.exists())

    def test_socket_start_does_not_require_newer_nofollow_chmod_support(self):
        original = os.chmod
        def portable_chmod(path, mode, *, dir_fd=None, follow_symlinks=True):
            if dir_fd is not None and not follow_symlinks:
                raise ValueError('unsupported flags on older Python/Linux')
            return original(path, mode, dir_fd=dir_fd)
        with patch('runtime.voice.control.os.chmod', side_effect=portable_chmod):
            server = self.start()
        self.assertEqual(server.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_peer_is_rejected_before_dispatch(self):
        server = self.start()
        client = self.client(server, b'')
        with patch('socket.socket.getsockopt', return_value=struct.pack('3i', 123, os.geteuid()+1, 123)):
            server.serve_once()
        self.assertEqual(json.loads(client.recv(4096))['code'], 'control.peer')
        self.assertEqual(self.calls, [])

    def test_second_owner_and_preexisting_socket_are_not_unlinked(self):
        server = self.start()
        inode = server.path.stat().st_ino
        other = LocalControlServer(self.path, self.dispatcher)
        with self.assertRaises(ValueError):
            other.start()
        self.assertEqual(server.path.stat().st_ino, inode)
        server.close()
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(stale.close)
        stale.bind(str(server.path))
        with self.assertRaises(ValueError):
            other.start()
        self.assertTrue(server.path.exists())

    def test_symlink_or_nonprivate_directory_rejected_without_mutation(self):
        directory = self.path / 'real'
        directory.mkdir(mode=0o700)
        linked = self.path / 'link'
        linked.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            LocalControlServer(linked, self.dispatcher).start()
        directory.chmod(0o755)
        with self.assertRaises(ValueError):
            LocalControlServer(directory, self.dispatcher).start()
        self.assertEqual(list(directory.iterdir()), [])

    def test_oversize_and_hung_requests_do_not_mutate(self):
        server = self.start()
        for wire in (struct.pack('!I', 4097), b'\x00', struct.pack('!I', 100) + b'{'):
            client = self.client(server, wire)
            start = time.monotonic()
            self.assertTrue(server.serve_once())
            self.assertLess(time.monotonic() - start, 1)
            self.assertEqual(json.loads(client.recv(4096))['status'], 'blocked')
            client.close()
        self.assertEqual(self.calls, [])

    def test_cleanup_does_not_unlink_replacement_path(self):
        server = self.start()
        original = self.path / 'original.sock'
        server.path.rename(original)
        server.path.write_text('not our socket')
        server.close()
        self.assertEqual(server.path.read_text(), 'not our socket')

    def test_accept_without_client_is_bounded(self):
        server = self.start()
        start = time.monotonic()
        self.assertFalse(server.serve_once())
        self.assertLess(time.monotonic() - start, 1)
