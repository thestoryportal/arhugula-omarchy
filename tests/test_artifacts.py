import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ArtifactTests(unittest.TestCase):
    def capture(self, script, timeout=5):
        from ops.orchestration.artifacts import capture
        return capture([sys.executable, '-c', script], Path.cwd(),
                       root=self.root, timeout=timeout)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_large_output_is_complete_on_disk_and_summary_is_bounded(self):
        result = self.capture("import sys; print('x'*2000000); print('ERROR useful failure',file=sys.stderr); sys.exit(7)")
        self.assertEqual(result['exit'], 7)
        self.assertEqual(Path(result['stdout']['path']).stat().st_size, 2000001)
        self.assertLess(len(json.dumps(result)), 10000)
        self.assertIn('ERROR useful failure', result['summary'])
        self.assertEqual(result['stdout']['sha256'], hashlib.sha256(b'x'*2000000+b'\n').hexdigest())
        self.assertEqual(json.loads(Path(result['receipt']).read_text()), result)

    def test_timeout_has_terminal_receipt_and_preserves_raw_output(self):
        result = self.capture("import time; print('started',flush=True); time.sleep(20)", 0.1)
        self.assertEqual(result['terminal'], 'timeout')
        self.assertEqual(result['exit'], 124)
        self.assertEqual(Path(result['stdout']['path']).read_text(), 'started\n')

    def test_missing_mac_mount_refuses_before_command_execution(self):
        from ops.orchestration.artifacts import require_mac_share
        with self.assertRaisesRegex(ValueError, 'Mac share'):
            require_mac_share('1 2 3 / / rw - ext4 /dev/vda rw\n')
        with self.assertRaisesRegex(ValueError, 'Mac share'):
            require_mac_share('1 2 3 / /mnt/mac ro - 9p mac rw\n')

    def test_symlink_store_cannot_redirect_logs(self):
        from ops.orchestration.artifacts import capture
        link = self.root / 'link'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            capture(['true'], Path.cwd(), root=link)

    def test_launch_failure_is_recorded_without_success_receipt(self):
        with self.assertRaises(FileNotFoundError):
            self.capture_command(['/nonexistent/buford-command'])
        receipts = list(self.root.glob('*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text())['terminal'], 'launch_failed')

    def capture_command(self, argv):
        from ops.orchestration.artifacts import capture
        return capture(argv, Path.cwd(), root=self.root)

    def test_unsupported_fsync_cannot_publish_a_receipt(self):
        from ops.orchestration.artifacts import capture
        from unittest.mock import patch
        with patch('os.fsync', side_effect=OSError('disk failed')):
            with self.assertRaisesRegex(OSError, 'disk failed'):
                capture(['true'], Path.cwd(), root=self.root)
        self.assertEqual(list(self.root.glob('*/receipt.json')), [])

    def test_final_directory_fsync_failure_leaves_no_success_receipt(self):
        from ops.orchestration.artifacts import capture
        from unittest.mock import patch
        import os
        original=os.fsync; calls=0
        def fail_final(fd):
            nonlocal calls
            calls+=1
            if calls==5:raise OSError('final publication sync failed')
            return original(fd)
        with patch('os.fsync',side_effect=fail_final):
            with self.assertRaisesRegex(OSError,'final publication sync failed'):
                capture(['true'],Path.cwd(),root=self.root)
        for path in self.root.glob('*/receipt.json'):
            result=json.loads(path.read_text())
            self.assertNotEqual((result['terminal'],result['exit']),('exited',0))

    def test_parent_exit_cannot_publish_success_with_owned_descendants_running(self):
        result=self.capture("import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print('parent done')")
        self.assertEqual(result['terminal'],'descendants_active')
        self.assertEqual(result['exit'],125)
