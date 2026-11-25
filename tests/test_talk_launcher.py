"""Desktop launcher ownership and shutdown tests; no GUI or production state."""
import os
import json
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

    def test_browser_priority_and_missing(self):
        roots = [self.home / 'program', self.home / 'x86', self.home / 'local']
        env = dict(zip(('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'), map(str, roots)))
        chrome = [root / 'Google/Chrome/Application/chrome.exe' for root in roots]
        edge = [root / 'Microsoft/Edge/Application/msedge.exe' for root in roots]
        for path in (edge[1], chrome[2], chrome[0]):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.assertEqual(launcher.find_browser(env, 'win32'), chrome[0])
        chrome[0].unlink()
        self.assertEqual(launcher.find_browser(env, 'win32'), chrome[2])
        chrome[2].unlink()
        self.assertEqual(launcher.find_browser(env, 'win32'), edge[1])
        edge[1].unlink()
        self.assertIsNone(launcher.find_browser(env, 'win32'))

    def test_macos_candidates_and_precedence(self):
        env = {'HOME': str(self.home)}
        chrome, edge = launcher.browser_candidates(env, 'darwin')
        self.assertEqual(str(chrome[0]), str(Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')))
        self.assertEqual(chrome[1], self.home / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        self.assertEqual(str(edge[0]), str(Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')))
        with patch.object(Path, 'is_file', autospec=True, side_effect=lambda path: path in (chrome[1], edge[0])):
            self.assertEqual(launcher.find_browser(env, 'darwin'), chrome[1])
        with patch.object(Path, 'is_file', autospec=True, side_effect=lambda path: path == edge[0]):
            self.assertEqual(launcher.find_browser(env, 'darwin'), edge[0])

    def test_preferences_create_merge_and_recover_corrupt_json(self):
        profile = self.home / 'profile'
        preferences = profile / 'Default' / 'Preferences'
        local_state = profile / 'Local State'
        launcher.prepare_browser_profile(profile)
        self.assertEqual(json.loads(preferences.read_text(encoding='utf-8')), {'background_mode': {'enabled': False}})
        self.assertEqual(
            json.loads(local_state.read_text(encoding='utf-8')),
            {'background_mode': {'enabled': False}, 'glic': {'launcher_enabled': False}},
        )
        preferences.write_text(json.dumps({'other': {'value': 1}, 'background_mode': {'enabled': True, 'extra': 2}}), encoding='utf-8')
        local_state.write_text(json.dumps({'keep': 7, 'background_mode': {'enabled': True}, 'glic': {'launcher_enabled': True, 'x': 1}}), encoding='utf-8')
        launcher.prepare_browser_profile(profile)
        self.assertEqual(json.loads(preferences.read_text(encoding='utf-8')), {'other': {'value': 1}, 'background_mode': {'enabled': False, 'extra': 2}})
        self.assertEqual(
            json.loads(local_state.read_text(encoding='utf-8')),
            {'keep': 7, 'background_mode': {'enabled': False}, 'glic': {'launcher_enabled': False, 'x': 1}},
        )
        preferences.write_text('{broken', encoding='utf-8')
        local_state.write_text('{broken', encoding='utf-8')
        launcher.prepare_browser_profile(profile)
        self.assertEqual(json.loads(preferences.read_text(encoding='utf-8')), {'background_mode': {'enabled': False}})
        self.assertEqual(
            json.loads(local_state.read_text(encoding='utf-8')),
            {'background_mode': {'enabled': False}, 'glic': {'launcher_enabled': False}},
        )

    def test_cmdline_matches_exact_profile_only(self):
        target = self.home / 'data' / 'launcher-profile'
        spaced = self.home / 'My User' / 'TALK' / 'data' / 'launcher-profile'
        cjk = self.home / '测试用户' / 'TALK' / 'data' / 'launcher-profile'
        self.assertTrue(launcher._cmdline_matches_profile(
            f'chrome.exe --app=http://127.0.0.1:8000 --user-data-dir={target} --no-first-run', target))
        self.assertTrue(launcher._cmdline_matches_profile(
            f'chrome.exe "--user-data-dir={spaced}" --no-first-run', spaced))
        self.assertTrue(launcher._cmdline_matches_profile(
            f'chrome.exe --user-data-dir="{spaced}" --no-first-run', spaced))
        self.assertTrue(launcher._cmdline_matches_profile(
            f'chrome.exe "--user-data-dir={cjk}" --no-first-run', cjk))
        self.assertFalse(launcher._cmdline_matches_profile(
            f'chrome.exe --user-data-dir={target}-other --no-first-run', target))
        self.assertFalse(launcher._cmdline_matches_profile(
            'chrome.exe --profile-directory=Default', target))
        # Quoted flag containing fake --user-data-dir text must not match.
        self.assertFalse(launcher._cmdline_matches_profile(
            f'chrome.exe --app="http://127.0.0.1/?q= --user-data-dir={target}"', target))
        # Multiple --user-data-dir flags: Chromium honors the last one.
        self.assertFalse(launcher._cmdline_matches_profile(
            f'chrome.exe --user-data-dir={target} --user-data-dir={target}-other', target))

    def test_find_profile_browser_pids_handles_utf8_cjk_single_array_and_rejects_bad_name(self):
        cjk_profile = self.home / '测试用户' / 'launcher-profile'
        single_json = json.dumps({
            'ProcessId': 4242,
            'CommandLine': f'chrome.exe "--user-data-dir={cjk_profile}" --no-first-run',
        }, ensure_ascii=False)
        array_json = json.dumps([
            {'ProcessId': 1111, 'CommandLine': 'chrome.exe --profile-directory=Default'},
            {'ProcessId': 4243, 'CommandLine': f'chrome.exe --user-data-dir="{cjk_profile}"'},
            {'ProcessId': True, 'CommandLine': f'chrome.exe --user-data-dir="{cjk_profile}"'},
        ], ensure_ascii=False)
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher.subprocess, 'run', side_effect=[
                 SimpleNamespace(returncode=0, stdout='\ufeff' + single_json),
                 SimpleNamespace(returncode=0, stdout=array_json),
             ]) as run:
            self.assertEqual(launcher._find_profile_browser_pids('chrome.exe', cjk_profile), {4242})
            self.assertIn('[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)', run.call_args_list[0].args[0][-1])
            self.assertEqual(launcher._find_profile_browser_pids('chrome.exe', cjk_profile), {4243})
            # Reject invalid executable name without invoking PowerShell.
            self.assertEqual(launcher._find_profile_browser_pids("chrome';calc;.exe", cjk_profile), set())
            self.assertEqual(run.call_count, 2)

    def test_health_monitor_three_consecutive_failures_graceful_then_force(self):
        process = unittest.mock.Mock(pid=1234)
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher, 'healthy', side_effect=[False, True, False, False, False]) as health, \
             patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={1234}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[999]), \
             patch.object(launcher, '_post_close_windows') as post_close, \
             patch.object(launcher, '_wait_process_exit', return_value=False), \
             patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as kill:
            launcher.monitor_browser_health(process, 'http://127.0.0.1:8124', stop, closed)
        self.assertEqual(health.call_count, 5)
        post_close.assert_called_once_with([999])
        self.assertEqual(kill.call_args_list[0].args[0], ['taskkill', '/PID', '1234', '/T'])
        self.assertEqual(kill.call_args_list[1].args[0], ['taskkill', '/PID', '1234', '/T', '/F'])
        closed.set.assert_called_once_with()
        process.terminate.assert_not_called()

    def test_health_monitor_graceful_exit_skips_force_kill(self):
        process = unittest.mock.Mock(pid=1234)
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher, 'healthy', return_value=False), \
             patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={1234}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[999]), \
             patch.object(launcher, '_post_close_windows') as post_close, \
             patch.object(launcher, '_wait_process_exit', return_value=True), \
             patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as kill:
            launcher.monitor_browser_health(process, 'http://127.0.0.1:8124', stop, closed)
        post_close.assert_called_once_with([999])
        self.assertEqual(len(kill.call_args_list), 1)
        self.assertEqual(kill.call_args_list[0].args[0], ['taskkill', '/PID', '1234', '/T'])
        closed.set.assert_called_once_with()

    def test_window_monitor_closes_tray_after_window_disappears(self):
        process = unittest.mock.Mock(pid=2468)
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        profile = self.home / 'data' / 'launcher-profile'
        # Startup (no window yet) -> visible -> enum error (ignored) -> closed (poll 1) -> closed (poll 2 -> terminate).
        windows_seq = [[], [101], None, [], []]
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={2468}), \
             patch.object(launcher, '_list_visible_browser_windows', side_effect=windows_seq), \
             patch.object(launcher, 'terminate_browser_process', return_value=True) as term:
            launcher.monitor_browser_window(
                process, profile, stop, closed, browser_name='chrome.exe', poll_interval=0.01, grace_polls=2,
            )
        closed.set.assert_called_once_with()
        term.assert_called_once_with(process, profile=profile, browser_name='chrome.exe')

    def test_window_monitor_fail_closed_on_enum_error(self):
        process = unittest.mock.Mock(pid=2468)
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.side_effect = [False, False, False, False, True]
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={2468}), \
             patch.object(launcher, '_list_visible_browser_windows', side_effect=[[101], None, None, None]), \
             patch.object(launcher, 'terminate_browser_process') as term:
            launcher.monitor_browser_window(
                process, self.home / 'profile', stop, closed, poll_interval=0.01, grace_polls=2,
            )
        term.assert_not_called()
        closed.set.assert_not_called()

    def test_window_monitor_ignores_startup_before_first_window(self):
        process = unittest.mock.Mock(pid=2468)
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.side_effect = [False, False, False, True]
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={2468}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[]), \
             patch.object(launcher, 'terminate_browser_process') as term:
            launcher.monitor_browser_window(
                process, self.home / 'profile', stop, closed, poll_interval=0.01, grace_polls=2,
            )
        term.assert_not_called()
        closed.set.assert_not_called()

    def test_cleanup_orphan_profile_tray_only_kills_windowless_profile(self):
        fake_chrome = self.home / 'chrome.exe'
        fake_chrome.write_text('', encoding='utf-8')
        profile = self.home / 'data' / 'launcher-profile'
        profile.mkdir(parents=True)
        # Active window present -> do not touch.
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_find_profile_browser_pids', return_value={5555}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[777]), \
             patch.object(launcher, '_run_taskkill') as kill:
            launcher._cleanup_orphan_profile_tray(fake_chrome, profile)
        kill.assert_not_called()
        # Window enumeration failed (None) -> fail-closed, do not touch.
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_find_profile_browser_pids', return_value={5555}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=None), \
             patch.object(launcher, '_run_taskkill') as kill:
            launcher._cleanup_orphan_profile_tray(fake_chrome, profile)
        kill.assert_not_called()
        # Windowless tray zombie -> gracefully kill, then stop once gone.
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_find_profile_browser_pids', side_effect=[{5555}, set()]), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[]), \
             patch.object(launcher, '_run_taskkill') as kill:
            launcher._cleanup_orphan_profile_tray(fake_chrome, profile)
        kill.assert_called_once_with(5555, force=False, tree=True)
        # taskkill OSError must not crash startup.
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_find_profile_browser_pids', return_value={5555}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[]), \
             patch.object(launcher, '_run_taskkill', side_effect=OSError('missing taskkill')):
            launcher._cleanup_orphan_profile_tray(fake_chrome, profile)

    def test_terminate_browser_cleans_orphan_profile_pids_without_touching_others(self):
        process = unittest.mock.Mock(pid=1000)
        process.poll.return_value = 0
        profile = self.home / 'data' / 'launcher-profile'
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_find_profile_browser_pids', side_effect=[{2001}, {2001}, {2001}]), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[]), \
             patch.object(launcher, '_run_taskkill', return_value=SimpleNamespace(returncode=0)) as kill, \
             patch.object(launcher.time, 'sleep'):
            ok = launcher.terminate_browser_process(
                process, profile=profile, browser_name='chrome.exe', grace_timeout=0.0,
            )
        self.assertTrue(ok)
        self.assertEqual(kill.call_args_list[0].args, (2001,))
        self.assertEqual(kill.call_args_list[0].kwargs, {'force': False, 'tree': True})
        self.assertEqual(kill.call_args_list[1].args, (2001,))
        self.assertEqual(kill.call_args_list[1].kwargs, {'force': True, 'tree': True})

    def test_terminate_browser_returns_false_when_main_and_orphan_kill_fail(self):
        process = unittest.mock.Mock(pid=1000)
        process.poll.return_value = None
        profile = self.home / 'data' / 'launcher-profile'
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_process_tree_pids', return_value={1000}), \
             patch.object(launcher, '_list_visible_browser_windows', return_value=[]), \
             patch.object(launcher, '_wait_process_exit', return_value=False), \
             patch.object(launcher, '_find_profile_browser_pids', return_value={1000}), \
             patch.object(launcher, '_run_taskkill', return_value=SimpleNamespace(returncode=1)):
            ok = launcher.terminate_browser_process(
                process, profile=profile, browser_name='chrome.exe', grace_timeout=0.0,
            )
        self.assertFalse(ok)

    def test_request_browser_close_deduplicates_across_monitors(self):
        import threading as _threading
        process = unittest.mock.Mock(pid=1234)
        process.poll.return_value = None
        stop = _threading.Event()
        closed = _threading.Event()
        lock = _threading.Lock()
        with patch.object(launcher, 'terminate_browser_process', return_value=True) as term:
            launcher._request_browser_close(process, stop, closed, close_lock=lock)
            launcher._request_browser_close(process, stop, closed, close_lock=lock)
        term.assert_called_once()
        self.assertTrue(closed.is_set())

    def test_health_monitor_success_does_not_terminate(self):
        process = unittest.mock.Mock()
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.side_effect = [False, False, True]
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher, 'healthy', return_value=True), patch.object(launcher.subprocess, 'run') as kill:
            launcher.monitor_browser_health(process, 'http://127.0.0.1:8124', stop, closed)
        kill.assert_not_called()
        process.terminate.assert_not_called()
        closed.set.assert_not_called()

    def test_list_visible_browser_windows_returns_none_on_enum_failure(self):
        fake_user32 = unittest.mock.Mock()
        fake_user32.EnumWindows.return_value = 0
        with patch.object(launcher.os, 'name', 'nt'), \
             patch.object(launcher, '_get_user32', return_value=fake_user32):
            self.assertIsNone(launcher._list_visible_browser_windows({1234}))

    def test_health_monitor_non_windows_terminates_handle(self):
        process = unittest.mock.Mock()
        process.poll.return_value = None
        stop = unittest.mock.Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        closed = unittest.mock.Mock()
        closed.is_set.return_value = False
        with patch.object(launcher, 'healthy', return_value=False), patch.object(launcher.os, 'name', 'posix'):
            launcher.monitor_browser_health(process, 'http://127.0.0.1:8124', stop, closed)
        process.terminate.assert_called_once_with()

    def test_edge_arguments_and_autoclose(self):
        process = unittest.mock.Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        timer = unittest.mock.Mock()
        with patch.object(launcher.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(launcher.threading, 'Timer', return_value=timer) as make_timer:
            launcher.run_browser('edge.exe', self.home, self.app.url, {'TALK_LAUNCHER_AUTOCLOSE_MS': '3000'})
            args = popen.call_args.args[0]
            self.assertEqual(args, ['edge.exe', '--app=' + self.app.url,
                '--user-data-dir=' + str(self.home / 'data/launcher-profile'), '--no-first-run',
                '--no-default-browser-check', '--disable-background-mode', '--disable-features=Glic'])
            self.assertEqual(make_timer.call_args.args[0], 3)
            make_timer.call_args.args[1]()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with()
            timer.cancel.assert_called_once_with()

    def test_browser_failed_exit_is_reported(self):
        process = unittest.mock.Mock()
        process.wait.return_value = 3
        with patch.object(launcher.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(launcher.LauncherError, '浏览器启动或运行失败'):
                launcher.run_browser('browser.exe', self.home, self.app.url, {})

    def test_main_owned_and_attach_close_and_stop_failure(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        for owned, stop_result in ((True, (True, '')), (False, (True, '')),
                                   (True, (False, 'stop_blocked'))):
            with self.subTest(owned=owned, result=stop_result), \
                 patch.object(launcher, 'resolve_config', return_value=(self.home, self.path, self.config, self.app.url)), \
                 patch.object(launcher, 'SingleInstance', return_value=Lock()), \
                 patch.object(launcher, 'find_browser', return_value='edge.exe'), \
                 patch.object(launcher, 'run_browser') as edge, \
                 patch.object(self.app, 'start'), patch.object(self.app, 'read_owned_identity', return_value=(123, 'start')), \
                 patch.object(self.app, 'run_runtime', return_value=SimpleNamespace(returncode=0 if stop_result[0] else 1,
                                                                                   stdout=stop_result[1], stderr='')) as runtime, \
                 patch.object(launcher, 'Launcher', return_value=self.app), patch.object(launcher, 'notify') as notify:
                self.app.owned, self.app.identity = owned, (123, 'start')
                self.assertEqual(launcher.main(), 0 if stop_result[0] else 1)
                edge.assert_called_once()
                self.assertEqual(edge.call_args.kwargs.get('health_url'), self.app.url)
                if owned:
                    runtime.assert_called_once_with('stop', '--wait')
                else:
                    runtime.assert_not_called()
                if not stop_result[0]:
                    self.assertIn('服务未停止，请处理忙任务后使用 stop.bat/status.bat', notify.call_args.args[0])

    def test_default_browser_does_not_wait_or_stop(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(launcher, 'resolve_config', return_value=(self.home, self.path, self.config, self.app.url)), \
             patch.object(launcher, 'SingleInstance', return_value=Lock()), \
             patch.object(launcher, 'find_browser', return_value=None), \
             patch.object(launcher, 'Launcher', return_value=self.app), \
             patch.object(self.app, 'start'), patch.object(self.app, 'stop') as stop, \
             patch.object(launcher, 'open_default_browser') as opened, patch.object(launcher, 'notify') as notify:
            self.app.owned = True
            self.assertEqual(launcher.main(), 0)
            opened.assert_called_once_with(self.app.url + '/?desktop=1')
            self.assertIn('不会自动停服务', notify.call_args.args[0])
            self.assertIn('stop.bat', notify.call_args.args[0])
            stop.assert_not_called()

    def test_default_browser_failure_is_clear(self):
        with patch.object(launcher.webbrowser, 'open', return_value=False):
            with self.assertRaisesRegex(launcher.LauncherError, '无法打开系统默认浏览器'):
                launcher.open_default_browser(self.app.url)



if __name__ == '__main__':
    unittest.main()
