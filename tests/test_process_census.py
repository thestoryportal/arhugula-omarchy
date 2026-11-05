"""A process disappearing during observation cannot invalidate a released command."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from ops.orchestration.artifacts import capture, group_active
from ops.orchestration.native_window import WindowCapability, processes


class ProcessCensusTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.gone = self.root / '101' / 'stat'
        self.live = self.root / '100' / 'stat'
        self.live.parent.mkdir()
        self.live.write_text(
            '100 (worker with space) S 42 900 900 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 12345 0 0\n'
        )

    def observation(self, error):
        glob, read = Path.glob, Path.read_text

        def paths(path, pattern):
            if path == Path('/proc') and pattern == '[0-9]*/stat':
                return iter((self.gone, self.live))
            return glob(path, pattern)

        def contents(path, *args, **kwargs):
            if path == self.gone:
                raise error
            return read(path, *args, **kwargs)

        return patch.object(Path, 'glob', paths), patch.object(Path, 'read_text', contents)

    def test_exited_process_does_not_hide_surviving_native_identity(self):
        for error in (FileNotFoundError(2, 'gone'), ProcessLookupError(3, 'gone')):
            with self.subTest(error=type(error).__name__):
                paths, reads = self.observation(error)
                with paths, reads:
                    self.assertEqual(processes(), {100: ('12345', 42)})

    def test_exited_process_does_not_hide_live_owned_descendant(self):
        paths, reads = self.observation(ProcessLookupError(3, 'gone'))
        with paths, reads:
            self.assertTrue(group_active(900))
            self.assertFalse(group_active(901))

    def test_exited_unrelated_process_preserves_successful_command_receipt(self):
        paths, reads = self.observation(ProcessLookupError(3, 'gone'))
        with paths, reads:
            result = capture(
                [sys.executable, '-c', "print('complete')"], Path.cwd(), root=self.root
            )
        self.assertEqual((result['exit'], result['terminal']), (0, 'exited'))
        self.assertEqual(Path(result['stdout']['path']).read_text(), 'complete\n')
        self.assertEqual(Path(result['stderr']['path']).read_text(), '')
        self.assertEqual(json.loads(Path(result['receipt']).read_text()), result)

    def test_permission_error_does_not_become_an_empty_census(self):
        for consumer in (processes, lambda: group_active(900)):
            paths, reads = self.observation(PermissionError(13, 'denied'))
            with paths, reads, self.assertRaises(PermissionError):
                consumer()

    def test_zombie_does_not_count_as_a_live_descendant(self):
        self.live.write_text(self.live.read_text().replace(') S ', ') Z '))
        paths, reads = self.observation(FileNotFoundError(2, 'gone'))
        with paths, reads:
            self.assertFalse(group_active(900))
            self.assertEqual(processes(), {100: ('12345', 42)})

    def test_malformed_record_remains_a_failure(self):
        for text in ('missing delimiter', '100 (worker) S 42 invalid'):
            for consumer in (processes, lambda: group_active(900)):
                with self.subTest(text=text, consumer=consumer):
                    self.live.write_text(text)
                    paths, reads = self.observation(FileNotFoundError(2, 'gone'))
                    with paths, reads, self.assertRaises((IndexError, ValueError)):
                        consumer()

    def test_disappeared_required_native_process_refuses_capability(self):
        capability = WindowCapability('0xabc', 'window', 100, '12345', 101, '12346')
        clients = [dict(address='0xabc', stableId='window', pid=100,
                        mapped=True, acceptsInput=True)]
        for error in (FileNotFoundError(2, 'gone'), ProcessLookupError(3, 'gone')):
            with self.subTest(error=type(error).__name__):
                paths, reads = self.observation(error)
                with paths, reads, self.assertRaises(ValueError):
                    capability.parse(clients, processes())
