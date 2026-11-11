import ast
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server import workspace_relink_files as files


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RelinkFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'config'
        self.roots = [self.root]

    def error(self, code, fn, *args):
        with self.assertRaises(files.WorkspaceFileError) as caught:
            fn(*args)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def prepare(self, target=None, old=None, new=b'new'):
        return files.prepare_write(target or self.target, new, None if old is None else digest(old), self.roots)

    def test_create_and_overwrite(self):
        receipt = self.prepare()
        self.assertFalse(self.target.exists())
        self.assertEqual(receipt.temp.parent, self.target.parent)
        self.assertEqual(digest(b'new'), receipt.new_digest)
        self.assertTrue(files.commit_write(receipt, self.roots).committed)
        self.assertEqual(b'new', self.target.read_bytes())
        self.assertFalse(receipt.temp.exists())
        receipt = self.prepare(old=b'new', new=b'updated')
        files.commit_write(receipt, self.roots)
        self.assertEqual(b'updated', self.target.read_bytes())

    def test_conflicts(self):
        self.target.write_bytes(b'old')
        for expected in (None, digest(b'wrong')):
            self.error('workspace_file_conflict', files.prepare_write, self.target, b'new', expected, self.roots)
            self.assertEqual(b'old', self.target.read_bytes())
        receipt = self.prepare(old=b'old')
        self.target.write_bytes(b'external')
        err = self.error('workspace_file_conflict', files.commit_write, receipt, self.roots)
        self.assertEqual(b'external', self.target.read_bytes())
        files.abort_write(receipt)
        self.target.unlink()
        self.error('workspace_file_conflict', files.prepare_write, self.target, b'new', digest(b'old'), self.roots)
        print('conflict:', err.code, 'external content preserved')

    def test_path_refusals(self):
        outside = self.root.parent / ('outside-' + self.root.name)
        cases = [Path('relative'), str(self.target) + '\0', str(self.root / ('x' * 4100)), outside, self.root]
        for path in cases:
            with self.subTest(path=str(path)[:80]):
                self.error('workspace_path_refused', files.prepare_write, path, b'new', None, self.roots)
        self.assertEqual([], list(self.root.iterdir()))
        print('path refusals: relative, NUL, long, outside, directory -> workspace_path_refused; zero writes')

    def test_existence_changes_conflict(self):
        receipt = self.prepare()
        self.target.write_bytes(b'external')
        self.error('workspace_file_conflict', files.commit_write, receipt, self.roots)
        self.assertEqual(b'external', self.target.read_bytes())
        files.abort_write(receipt)
        receipt = self.prepare(old=b'external')
        self.target.unlink()
        self.error('workspace_file_conflict', files.commit_write, receipt, self.roots)
        self.assertFalse(self.target.exists())
        files.abort_write(receipt)
        print('existence conflicts: appeared / disappeared -> workspace_file_conflict')

    def test_links_refused(self):
        real = self.root / 'real'
        real.mkdir()
        link = self.root / 'link'
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('directory symlink unavailable')
        self.error('workspace_path_refused', files.prepare_write, link / 'child', b'x', None, self.roots)
        filelink = self.root / 'filelink'
        filelink.symlink_to(real / 'missing')
        self.error('workspace_path_refused', files.prepare_write, filelink, b'x', None, self.roots)
        self.assertEqual([], list(real.iterdir()))
        print('path refusals: parent and target symlinks -> workspace_path_refused')

    def test_simulated_symlink_refused_when_creation_unavailable(self):
        parent = self.root / 'parent'
        parent.mkdir()
        original = Path.lstat
        for link, target in ((parent, parent / 'child'), (self.target, self.target)):
            def fake_lstat(path, *args, **kwargs):
                if path == link:
                    return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
                return original(path, *args, **kwargs)
            with mock.patch.object(Path, 'lstat', fake_lstat):
                self.error('workspace_path_refused', files.prepare_write, target, b'x', None, self.roots)
        self.assertEqual([], list(parent.iterdir()))
        self.assertFalse(self.target.exists())
        print('path refusals: simulated parent and target symlink -> workspace_path_refused')

    @unittest.skipUnless(os.name == 'nt', 'junction requires Windows')
    def test_junction_refused(self):
        # mklink is used only by the test, in the isolated temporary directory.
        import subprocess
        real = self.root / 'real'
        real.mkdir()
        junction = self.root / 'junction'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(real)], capture_output=True)
        if result.returncode:
            self.skipTest('junction creation unavailable')
        self.error('workspace_path_refused', files.prepare_write, junction / 'child', b'x', None, self.roots)
        self.error('workspace_path_refused', files.prepare_write, junction, b'x', None, self.roots)
        self.assertEqual([], list(real.iterdir()))
        junction.rmdir()
        print('path refusals: target and parent junction -> workspace_path_refused')

    def test_abort_and_failed_prepare_cleanup(self):
        self.target.write_bytes(b'old')
        receipt = self.prepare(old=b'old')
        self.assertEqual(b'old', self.target.read_bytes())
        files.abort_write(receipt)
        files.abort_write(receipt)
        self.assertFalse(receipt.temp.exists())
        with mock.patch.object(files.os, 'fsync', side_effect=OSError('private data')):
            err = self.error('workspace_write_failed', self.prepare, self.target, b'old')
        self.assertNotIn('private data', str(err))
        self.assertEqual([self.target], list(self.root.iterdir()))

    def test_rollback(self):
        self.target.write_bytes(b'old')
        receipt = self.prepare(old=b'old')
        files.commit_write(receipt, self.roots)
        files.rollback_write(receipt, self.roots)
        self.assertEqual(b'old', self.target.read_bytes())
        created = self.root / 'created'
        receipt = self.prepare(created)
        files.commit_write(receipt, self.roots)
        files.rollback_write(receipt, self.roots)
        self.assertFalse(created.exists())
        receipt = self.prepare(old=b'old')
        files.commit_write(receipt, self.roots)
        self.target.write_bytes(b'external')
        err = self.error('workspace_recovery_required', files.rollback_write, receipt, self.roots)
        self.assertEqual(b'external', self.target.read_bytes())
        print('rollback:', err.code, 'external content preserved; old restored and created removed')

    def test_uncommitted_rollback_aborts(self):
        receipt = self.prepare()
        files.rollback_write(receipt, self.roots)
        self.assertFalse(receipt.temp.exists())
        self.assertFalse(self.target.exists())

    def batch(self, rollback_fails):
        other = self.root / 'other'
        self.target.write_bytes(b'old1')
        other.write_bytes(b'old2')
        a, b = self.prepare(old=b'old1'), self.prepare(other, b'old2')
        real_replace = os.replace
        calls = []
        def replace(src, dst):
            calls.append((src, dst))
            if len(calls) == 2 or (rollback_fails and len(calls) == 3):
                raise OSError('private system error')
            return real_replace(src, dst)
        with mock.patch.object(files.os, 'replace', side_effect=replace):
            code = 'workspace_recovery_required' if rollback_fails else 'workspace_write_failed'
            err = self.error(code, files.commit_batch, [a, b], self.roots)
        self.assertEqual(b'old2', other.read_bytes())
        self.assertFalse(b.temp.exists())
        if rollback_fails:
            self.assertEqual((str(self.target),), err.not_rolled_back)
            self.assertEqual('workspace_write_failed', err.original_code)
            self.assertEqual(b'new', self.target.read_bytes())
            print('batch:', err.code, 'original=', err.original_code, 'not_rolled_back=', err.not_rolled_back)
        else:
            self.assertEqual(b'old1', self.target.read_bytes())
            print('batch:', err.code, 'first rolled back; both old values preserved')

    def test_batch_failure_compensated(self):
        self.batch(False)

    def test_batch_failure_and_rollback_failure(self):
        self.batch(True)

    def test_batch_success(self):
        other = self.root / 'other'
        a, b = self.prepare(), self.prepare(other)
        self.assertEqual([a, b], files.commit_batch([a, b], self.roots))
        self.assertEqual(b'new', other.read_bytes())

    def test_fsync_atomic_replace_and_staged_integrity(self):
        self.target.write_bytes(b'old')
        real_fsync, real_replace = os.fsync, os.replace
        observations = []
        def replace(src, dst):
            self.assertEqual(self.target.parent, Path(src).parent)
            self.assertEqual(self.target, Path(dst))
            observations.append((self.target.read_bytes(), Path(src).read_bytes()))
            return real_replace(src, dst)
        with mock.patch.object(files.os, 'fsync', wraps=real_fsync) as sync, mock.patch.object(files.os, 'replace', side_effect=replace):
            receipt = self.prepare(old=b'old')
            self.assertEqual(b'old', self.target.read_bytes())
            files.commit_write(receipt, self.roots)
            self.assertGreaterEqual(sync.call_count, 1)
            print('fsync calls:', sync.call_count, '; replace observations:', observations)
        self.assertEqual([(b'old', b'new')], observations)
        self.assertEqual(b'new', self.target.read_bytes())
        receipt = self.prepare(old=b'new')
        receipt.temp.write_bytes(b'tampered')
        self.error('workspace_write_failed', files.commit_write, receipt, self.roots)
        self.assertEqual(b'new', self.target.read_bytes())
        files.abort_write(receipt)

    def test_no_forbidden_imports_or_target_writes(self):
        source = Path(files.__file__).read_text(encoding='utf-8')
        tree = ast.parse(source)
        imports = [alias.name.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
        imports += [node.module.split('.')[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module]
        self.assertTrue(set(imports).isdisjoint({'sqlmodel', 'sqlalchemy', 'requests', 'subprocess', 'socket', 'httpx'}))
        self.assertNotIn('.write_bytes(', source)
        self.assertNotIn('.write_text(', source)
        self.assertEqual(2, source.count('os.replace('))


if __name__ == '__main__':
    unittest.main()
