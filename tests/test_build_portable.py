"""Portable package and detached launcher regression tests."""
import contextlib
import io
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import build_portable as build
from scripts import talk_runtime


class PortableBuildTests(unittest.TestCase):
    def test_allowlist_exclusions_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            root.mkdir()
            for name in build.ALLOW:
                path = root / name
                if '.' in name:
                    path.write_text('fixture', encoding='utf-8')
                else:
                    path.mkdir()
                    (path / 'keep.txt').write_text('fixture', encoding='utf-8')
            (root / 'server' / 'tests').mkdir()
            (root / 'server' / 'tests' / 'secret.txt').write_text('fixture', encoding='utf-8')
            (root / 'server' / 'operator.key').write_text('fixture', encoding='utf-8')
            (root / 'server' / 'talk.db').write_text('fixture', encoding='utf-8')
            with mock.patch.object(build, 'ROOT', root):
                stage = build.build(Path(directory) / 'output', make_zip=True, skip_python=True)
            self.assertTrue((stage / 'server' / 'keep.txt').is_file())
            self.assertFalse((stage / 'server' / 'tests').exists())
            self.assertFalse((stage / 'server' / 'operator.key').exists())
            self.assertFalse((stage / 'server' / 'talk.db').exists())
            self.assertEqual(list((stage / 'config').iterdir()), [])
            self.assertEqual(list((stage / 'data').iterdir()), [])
            with zipfile.ZipFile(stage.parent / 'TALK-portable-0.1.0.zip') as archive:
                self.assertIn('TALK/server/keep.txt', archive.namelist())
                self.assertIn('TALK/config/', archive.namelist())

    def test_secret_scanner_rejects_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad.txt').write_text('-----BEGIN PRIVATE KEY-----', encoding='utf-8')
            with self.assertRaises(ValueError):
                build.scan(root)

    def test_dependency_metadata_is_allowed_but_source_metadata_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'runtime' / 'python' / 'Lib' / 'site-packages' / 'fastapi' / '.agents'
            metadata.mkdir(parents=True)
            (metadata / 'readme.md').write_text('metadata', encoding='utf-8')
            self.assertEqual(build.scan(root), 1)
            source_metadata = root / 'TALK' / '.agents'
            source_metadata.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'excluded path'):
                build.scan(root)

    def test_dependency_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'runtime' / 'python' / 'Lib' / 'site-packages' / 'pkg'
            package.mkdir(parents=True)
            (package / 'payload').write_bytes(b'SQLite format 3\x00data')
            with self.assertRaisesRegex(ValueError, 'database'):
                build.scan(root)

    def test_ssl_retries_and_reports_exhaustion(self):
        failure = subprocess.CompletedProcess(['python'], 1, '', 'failure')
        success = subprocess.CompletedProcess(['python'], 0, '', '')
        with mock.patch.object(build.subprocess, 'run', side_effect=[failure, success]) as run, \
             mock.patch.object(build.time, 'sleep') as sleep, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            build.verify_ssl(Path('python'), Path('.'))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(sleep.call_args_list, [mock.call(3), mock.call(3)])
        errors = io.StringIO()
        with mock.patch.object(build.subprocess, 'run', return_value=failure) as run, \
             mock.patch.object(build.time, 'sleep') as sleep, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                build.verify_ssl(Path('python'), Path('.'))
        self.assertEqual(run.call_count, 10)
        self.assertEqual(sleep.call_args_list, [mock.call(3)] * 10)
        self.assertEqual(errors.getvalue(), 'failure' * 10)
        self.assertEqual(caught.exception.stderr, 'failure')

    @unittest.skipUnless(os.name == 'nt', 'Windows creation flags')
    def test_detach_retries_without_breakaway(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'project_root': str(root), 'state_dir': str(root), 'project_id': 'test', 'hosts': []}
            process = mock.Mock(pid=123)
            with mock.patch.object(talk_runtime, 'load_config', return_value=config), \
                 mock.patch.object(talk_runtime.rsh, 'ensure_private_dir', side_effect=lambda p: p.mkdir(parents=True)), \
                 mock.patch.object(talk_runtime.subprocess, 'Popen', side_effect=[PermissionError('denied'), process]) as popen, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(talk_runtime.main(['serve', '--config', str(root / 'runtime.json'), '--apply', '--detach']), 0)
            first, second = [call.kwargs['creationflags'] for call in popen.call_args_list]
            self.assertTrue(first & talk_runtime.subprocess.CREATE_BREAKAWAY_FROM_JOB)
            self.assertEqual(second, first & ~talk_runtime.subprocess.CREATE_BREAKAWAY_FROM_JOB)
            self.assertIn('breakaway denied', (root / 'runtime' / 'launcher.err').read_text(encoding='utf-8'))


    @unittest.skipUnless(os.name == 'nt', 'Windows creation flags')
    def test_detach_retry_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'project_root': str(root), 'state_dir': str(root), 'project_id': 'test', 'hosts': []}
            with mock.patch.object(talk_runtime, 'load_config', return_value=config), \
                 mock.patch.object(talk_runtime.rsh, 'ensure_private_dir', side_effect=lambda p: p.mkdir(parents=True)), \
                 mock.patch.object(talk_runtime.subprocess, 'Popen', side_effect=[PermissionError('denied'), OSError('failure')]):
                with self.assertRaises(talk_runtime.RuntimeErrorCode) as error:
                    talk_runtime.main(['serve', '--config', str(root / 'runtime.json'), '--apply', '--detach'])
            self.assertEqual(error.exception.code, 'runtime_detach_retry_failed')
            self.assertIn('retry without breakaway failed', (root / 'runtime' / 'launcher.err').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
