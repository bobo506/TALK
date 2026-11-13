"""Desktop launcher ownership and shutdown tests; no GUI or production state."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import talk_launcher as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='launcher-unit-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = {'base_url': 'http://localhost:8124', 'state_dir': str(self.home), 'project_id': 'fixture'}
        self.path = self.home / 'config' / 'runtime.json'
        self.app = launcher.Launcher(self.home, self.path, self.config, 'http://127.0.0.1:8124', {})

    def test_config_default_override_and_invalid(self):
        with patch.object(launcher.talk_runtime, 'load_config', return_value=self.config) as load:
            home, path, _, url = launcher.resolve_config({'TALK_HOME': str(self.home)})
            self.assertEqual(path, self.path)
            self.assertEqual(home, self.home)
            self.assertEqual(url, 'http://127.0.0.1:8124')
            override = self.home / 'custom.json'
            launcher.resolve_config({'TALK_HOME': str(self.home), 'TALK_RUNTIME_CONFIG': str(override)})
            load.assert_called_with(override)
        with patch.object(launcher.talk_runtime, 'load_config', return_value={'base_url': 'http://localhost'}):
            with self.assertRaisesRegex(launcher.LauncherError, '配置无效'):
                launcher.resolve_config({'TALK_HOME': str(self.home)})
        with patch.object(launcher.talk_runtime, 'load_config', side_effect=FileNotFoundError('missing')):
            with self.assertRaisesRegex(launcher.LauncherError, '配置无效'):
                launcher.resolve_config({'TALK_HOME': str(self.home)})

    def test_attach_never_starts_or_stops(self):
        with patch.object(launcher, 'healthy', return_value=True), patch.object(self.app, 'run_runtime') as run:
            self.app.start()
            self.assertFalse(self.app.owned)
            self.assertTrue(self.app.stop()[0])
            run.assert_not_called()

    def test_owned_start_and_close(self):
        result = SimpleNamespace(returncode=0, stdout='{"started_launcher_pid": 123}', stderr='')
        with patch.object(launcher, 'healthy', side_effect=[False, True]), \
             patch.object(self.app, 'run_runtime', return_value=result) as run, \
             patch.object(self.app, 'read_owned_identity', return_value=(123, 'start')):
            self.app.start()
            self.assertTrue(self.app.owned)
            self.assertTrue(self.app.stop()[0])
            self.assertEqual(run.call_args_list[0].args, ('serve', '--detach'))
            self.assertEqual(run.call_args_list[1].args, ('stop', '--wait'))

    def test_failed_stop_does_not_kill(self):
        self.app.owned, self.app.identity = True, (123, 'start')
        result = SimpleNamespace(returncode=1, stdout='stop_blocked', stderr='')
        with patch.object(self.app, 'read_owned_identity', return_value=self.app.identity), \
             patch.object(self.app, 'run_runtime', return_value=result) as run:
            ok, detail = self.app.stop()
            self.assertFalse(ok)
            self.assertTrue(self.app.owned)
            self.assertIn('stop_blocked', detail)
            run.assert_called_once_with('stop', '--wait')

    def test_start_failure_cleanup_owned(self):
        started = SimpleNamespace(returncode=0, stdout='{"started_launcher_pid": 123}', stderr='')
        stopped = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(launcher, 'healthy', return_value=False), \
             patch.object(launcher.time, 'monotonic', side_effect=[0, 1, 100]), \
             patch.object(launcher.time, 'sleep'), \
             patch.object(self.app, 'read_owned_identity', return_value=(123, 'start')), \
             patch.object(self.app, 'run_runtime', side_effect=[started, stopped]) as run:
            with self.assertRaisesRegex(launcher.LauncherError, '已停止'):
                self.app.start()
            self.assertEqual(run.call_args_list[1].args, ('stop', '--wait'))
            self.assertFalse(self.app.owned)

    def test_start_timeout_unknown_identity_does_not_stop(self):
        started = SimpleNamespace(returncode=0, stdout='{"started_launcher_pid": 123}', stderr='')
        with patch.object(launcher, 'healthy', return_value=False), \
             patch.object(launcher.time, 'monotonic', side_effect=[0, 1, 100]), \
             patch.object(launcher.time, 'sleep'), \
             patch.object(self.app, 'read_owned_identity', return_value=None), \
             patch.object(self.app, 'run_runtime', return_value=started) as run:
            with self.assertRaisesRegex(launcher.LauncherError, '可能残留.*status.bat / stop.bat'):
                self.app.start()
            run.assert_called_once_with('serve', '--detach')

    def test_cannot_stop_changed_identity(self):
        self.app.owned, self.app.identity = True, (123, 'start')
        with patch.object(self.app, 'read_owned_identity', return_value=(456, 'other')), \
             patch.object(self.app, 'run_runtime') as run, patch.object(launcher, 'notify'):
            self.assertFalse(self.app.stop()[0])
            run.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows mutex')
    def test_single_instance(self):
        with launcher.SingleInstance(self.path):
            with self.assertRaisesRegex(launcher.LauncherError, '已在运行'):
                with launcher.SingleInstance(self.path):
                    pass
        with launcher.SingleInstance(self.path):
            pass

    def test_find_edge_in_order_and_missing(self):
        roots = [self.home / 'x86', self.home / 'program', self.home / 'local']
        env = dict(zip(('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'), map(str, roots)))
        paths = [root / 'Microsoft/Edge/Application/msedge.exe' for root in roots]
        for path in reversed(paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            self.assertEqual(launcher.find_edge(env), path)
        for path in paths:
            path.unlink()
        with self.assertRaisesRegex(launcher.LauncherError, '未找到 Microsoft Edge'):
            launcher.find_edge(env)

    def test_edge_arguments_and_autoclose(self):
        process = unittest.mock.Mock()
        process.poll.return_value = None
        timer = unittest.mock.Mock()
        with patch.object(launcher.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(launcher.threading, 'Timer', return_value=timer) as make_timer:
            launcher.run_edge('edge.exe', self.home, self.app.url, {'TALK_LAUNCHER_AUTOCLOSE_MS': '3000'})
            args = popen.call_args.args[0]
            self.assertEqual(args, ['edge.exe', '--app=' + self.app.url,
                '--user-data-dir=' + str(self.home / 'data/launcher-profile'), '--no-first-run',
                '--no-default-browser-check', '--disable-background-mode'])
            self.assertEqual(make_timer.call_args.args[0], 3)
            make_timer.call_args.args[1]()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with()
            timer.cancel.assert_called_once_with()

    def test_main_owned_and_attach_close_and_stop_failure(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        for owned, stop_result in ((True, (True, '')), (False, (True, '')),
                                   (True, (False, 'stop_blocked'))):
            with self.subTest(owned=owned, result=stop_result), \
                 patch.object(launcher, 'resolve_config', return_value=(self.home, self.path, self.config, self.app.url)), \
                 patch.object(launcher, 'SingleInstance', return_value=Lock()), \
                 patch.object(launcher, 'find_edge', return_value='edge.exe'), \
                 patch.object(launcher, 'run_edge') as edge, \
                 patch.object(self.app, 'start'), patch.object(self.app, 'read_owned_identity', return_value=(123, 'start')), \
                 patch.object(self.app, 'run_runtime', return_value=SimpleNamespace(returncode=0 if stop_result[0] else 1,
                                                                                   stdout=stop_result[1], stderr='')) as runtime, \
                 patch.object(launcher, 'Launcher', return_value=self.app), patch.object(launcher, 'notify') as notify:
                self.app.owned, self.app.identity = owned, (123, 'start')
                self.assertEqual(launcher.main(), 0 if stop_result[0] else 1)
                edge.assert_called_once()
                if owned:
                    runtime.assert_called_once_with('stop', '--wait')
                else:
                    runtime.assert_not_called()
                if not stop_result[0]:
                    self.assertIn('服务未停止，请处理忙任务后使用 stop.bat/status.bat', notify.call_args.args[0])

    def test_missing_edge_never_starts_runtime(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(launcher, 'resolve_config', return_value=(self.home, self.path, self.config, self.app.url)), \
             patch.object(launcher, 'SingleInstance', return_value=Lock()), \
             patch.object(launcher, 'find_edge', side_effect=launcher.LauncherError('未找到 Microsoft Edge')), \
             patch.object(launcher, 'Launcher') as constructor, patch.object(launcher, 'notify') as notify:
            self.assertEqual(launcher.main(), 1)
            self.assertIn('未找到 Microsoft Edge', notify.call_args.args[0])
            constructor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
