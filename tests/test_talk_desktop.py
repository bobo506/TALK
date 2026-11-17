"""TALK 仓库桌面入口的决策与生命周期测试；不启动真实服务、不弹窗。"""
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import talk_desktop as desktop


class DesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='talk-desktop-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.real_onboarding = desktop.mcp_onboarding.run
        self.onboarding = patch.object(desktop.mcp_onboarding, 'run', return_value={'errors': [], 'member_status': 'checked'}).start()
        self.addCleanup(patch.stopall)

    def write_config(self, text):
        (self.home / 'config.toml').write_text(text, encoding='utf-8')

    def test_read_server_defaults_and_explicit_values(self):
        self.write_config('[server]\nport = 8000\n')
        self.assertEqual(desktop.read_server(self.home), ('127.0.0.1', 8000))
        self.write_config('[server]\nhost = "0.0.0.0"\nport = 8123\n')
        self.assertEqual(desktop.read_server(self.home), ('0.0.0.0', 8123))

    def test_read_server_rejects_invalid_port_and_missing_file(self):
        for text in ('[server]\nport = "8000"\n', '[server]\nport = 70000\n', '[server]\n'):
            with self.subTest(text=text):
                self.write_config(text)
                with self.assertRaisesRegex(desktop.LauncherError, 'server.port'):
                    desktop.read_server(self.home)
        (self.home / 'config.toml').unlink()
        with self.assertRaisesRegex(desktop.LauncherError, '无法读取配置'):
            desktop.read_server(self.home)

    def test_local_url_maps_wildcard_hosts(self):
        self.assertEqual(desktop.local_url('127.0.0.1', 8000), 'http://127.0.0.1:8000')
        self.assertEqual(desktop.local_url('0.0.0.0', 8000), 'http://127.0.0.1:8000')
        self.assertEqual(desktop.local_url('', 8000), 'http://127.0.0.1:8000')
        self.assertEqual(desktop.local_url('192.168.1.5', 8000), 'http://192.168.1.5:8000')
        self.assertEqual(desktop.local_url('::1', 8000), 'http://[::1]:8000')

    def test_plan_action(self):
        self.assertEqual(desktop.plan_action(True, False), 'attach')
        self.assertEqual(desktop.plan_action(False, True), 'start')
        self.assertEqual(desktop.plan_action(False, False), 'blocked')

    def test_port_available_reflects_listener(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            self.assertFalse(desktop.port_available('127.0.0.1', port))
        self.assertTrue(desktop.port_available('127.0.0.1', port))

    def test_service_start_arguments_and_environment(self):
        process = SimpleNamespace(poll=lambda: None, wait=lambda timeout=None: 0)
        with patch.object(desktop.subprocess, 'Popen', return_value=process) as popen:
            desktop.ApiService(self.home, '127.0.0.1', 8000, {}).start()
        args = popen.call_args.args[0]
        self.assertEqual(args[1:8], ['-B', '-X', 'utf8', '-m', 'scripts.talk_api', '--host', '127.0.0.1'])
        self.assertEqual(args[8:10], ['--port', '8000'])
        self.assertEqual(args[10], '--control-file')
        self.assertEqual(args[11], str(self.home / 'logs' / 'launcher' / 'api-8000.stop'))
        env = popen.call_args.kwargs['env']
        self.assertEqual(env['TALK_CONFIG'], str(self.home / 'config.toml'))
        self.assertEqual(popen.call_args.kwargs['cwd'], str(self.home))

    def test_runtime_config_priority_and_invalid_env_fallback(self):
        home = self.home / 'TALK'
        home.mkdir()
        portable = home / 'config' / 'runtime.json'
        portable.parent.mkdir()
        private = self.home / 'TALK-private' / 'talk-runtime.json'
        private.parent.mkdir()
        explicit = self.home / 'explicit.json'
        for path in (portable, private, explicit):
            path.write_text('{}', encoding='utf-8')
        self.assertEqual(desktop.find_runtime_config(home, {'TALK_RUNTIME_CONFIG': str(explicit)}), explicit)
        self.assertEqual(desktop.find_runtime_config(home, {'TALK_RUNTIME_CONFIG': 'relative.json'}), portable)
        self.assertEqual(desktop.find_runtime_config(home, {'TALK_RUNTIME_CONFIG': str(self.home / 'missing')}), portable)
        portable.unlink()
        self.assertEqual(desktop.find_runtime_config(home, {}), private)
        private.unlink()
        self.assertIsNone(desktop.find_runtime_config(home, {}))

    def test_run_passes_runtime_to_api_and_spawns_after_health(self):
        config = self.home / 'config' / 'runtime.json'
        config.parent.mkdir()
        config.write_text('{}', encoding='utf-8')
        order = []
        service = Mock()
        service.start.side_effect = lambda: order.append('start')
        service.wait_healthy.side_effect = lambda url: order.append('healthy')
        process = Mock()
        process.poll.return_value = None
        def spawn(*args, **kwargs):
            order.append('runtime')
            return process
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service) as api, \
             patch.object(desktop.subprocess, 'Popen', side_effect=spawn) as popen, \
             patch.object(desktop, 'launch_window', side_effect=lambda *args: order.append('window')):
            self.assertEqual(desktop.run(self.home, {}), 0)
        self.assertEqual(order, ['start', 'healthy', 'runtime', 'window'])
        self.assertEqual(api.call_args.args[3]['TALK_RUNTIME_CONFIG'], str(config))
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], [desktop.sys.executable, '-B', '-X', 'utf8', '-m',
                         'scripts.talk_runtime', 'serve', '--config', str(config), '--apply', '--attach-api'])
        self.assertEqual(popen.call_args.kwargs['cwd'], str(self.home))
        self.assertEqual(popen.call_args.kwargs['stdin'], desktop.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stdout'], desktop.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stderr'], desktop.subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['creationflags'],
                         getattr(desktop.subprocess, 'DETACHED_PROCESS', 0) | getattr(desktop.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))

    def test_no_runtime_config_keeps_window_and_does_not_spawn(self):
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=True), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'find_runtime_config', return_value=None), \
             patch.object(desktop.subprocess, 'Popen') as popen, \
             patch.object(desktop, 'launch_window') as window:
            self.assertEqual(desktop.run(self.home, {}), 0)
        popen.assert_not_called()
        window.assert_called_once()
        self.assertIn('未找到 runtime 配置，角色不会自动启动。',
                      (self.home / 'logs/launcher/runtime-launcher.log').read_text(encoding='utf-8'))

    def test_runtime_failure_does_not_block_attached_window(self):
        config = self.home / 'runtime.json'
        config.write_text('{}', encoding='utf-8')
        for failure in (OSError('failure'), Mock(poll=Mock(return_value=1))):
            with self.subTest(failure=failure), \
                 patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
                 patch.object(desktop, 'healthy', return_value=True), \
                 patch.object(desktop, 'port_available', return_value=True), \
                 patch.object(desktop.subprocess, 'Popen', side_effect=[failure]) as popen, \
                 patch.object(desktop, 'launch_window') as window:
                self.assertEqual(desktop.run(self.home, {'TALK_RUNTIME_CONFIG': str(config)}), 0)
                popen.assert_called_once()
                window.assert_called_once()
        log = (self.home / 'logs/launcher/runtime-launcher.log').read_text(encoding='utf-8')
        self.assertIn('runtime 启动异常；角色不会自动启动。', log)
        self.assertIn('runtime 启动异常；角色不会自动启动。', log)

    def test_service_stop_uses_control_file_then_clears_it(self):
        service = desktop.ApiService(self.home, '127.0.0.1', 8000, {})
        captured = {}

        def wait(timeout=None):
            captured['text'] = service.control_file.read_text(encoding='utf-8')
            return 0

        service.process = SimpleNamespace(wait=wait)
        service.stop()
        self.assertEqual(captured['text'], 'stop')
        self.assertIsNone(service.process)
        self.assertFalse(service.control_file.exists())

    def test_service_stop_falls_back_to_terminate(self):
        calls = []

        def wait(timeout=None):
            calls.append(timeout)
            if len(calls) == 1:
                raise desktop.subprocess.TimeoutExpired('api', timeout)
            return 0

        process = SimpleNamespace(wait=wait, terminate=Mock(), kill=Mock())
        service = desktop.ApiService(self.home, '127.0.0.1', 8000, {})
        service.process = process
        service.stop()
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()

    def test_wait_healthy_retries_until_ok(self):
        service = desktop.ApiService(self.home, '127.0.0.1', 8000, {})
        service.process = SimpleNamespace(poll=lambda: None)
        with patch.object(desktop, 'healthy', side_effect=[False, True]), \
             patch.object(desktop.time, 'sleep'):
            service.wait_healthy('http://127.0.0.1:8000')

    def test_wait_healthy_stops_on_child_exit(self):
        service = desktop.ApiService(self.home, '127.0.0.1', 8000, {})
        service.process = SimpleNamespace(poll=lambda: 3, returncode=3)
        with patch.object(desktop, 'healthy', return_value=False):
            with self.assertRaisesRegex(desktop.LauncherError, 'API 启动失败'):
                service.wait_healthy('http://127.0.0.1:8000')

    def test_run_attach_never_starts_or_stops(self):
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=True), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService') as service, \
             patch.object(desktop, 'launch_window', return_value=True):
            self.assertEqual(desktop.run(self.home, {}), 0)
        service.assert_not_called()

    def test_run_started_service_remains_after_window_close(self):
        service = Mock()
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service), \
             patch.object(desktop, 'launch_window', return_value=True):
            self.assertEqual(desktop.run(self.home, {}), 0)
        service.start.assert_called_once_with()
        service.wait_healthy.assert_called_once()
        service.stop.assert_not_called()

    def test_start_onboards_after_health_and_before_window(self):
        order = []
        service = Mock()
        service.start.side_effect = lambda: order.append('start')
        service.wait_healthy.side_effect = lambda url: order.append('healthy')
        self.onboarding.side_effect = lambda *args: (order.append('onboarding') or {'errors': [], 'member_status': 'checked'})
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service), \
             patch.object(desktop, 'write_boot_status', side_effect=lambda *args: order.append('status')), \
             patch.object(desktop, 'launch_window', side_effect=lambda *args: order.append('window')):
            desktop.run(self.home, {})
        self.assertEqual(order, ['start', 'healthy', 'onboarding', 'status', 'window'])

    def test_run_default_browser_keeps_started_service(self):
        service = Mock()
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service), \
             patch.object(desktop, 'launch_window', return_value=False):
            self.assertEqual(desktop.run(self.home, {}), 0)
        service.start.assert_called_once_with()
        service.stop.assert_not_called()

    def test_run_blocked_port_does_not_touch_service(self):
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=False), \
             patch.object(desktop, 'ApiService') as service:
            with self.assertRaisesRegex(desktop.LauncherError, '已被占用'):
                desktop.run(self.home, {})
        service.assert_not_called()

    def test_run_stops_service_when_health_check_fails(self):
        service = Mock()
        service.wait_healthy.side_effect = desktop.LauncherError('health failed')
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service), \
             patch.object(desktop, 'launch_window') as window:
            with self.assertRaises(desktop.LauncherError):
                desktop.run(self.home, {})
        service.stop.assert_called_once_with()
        window.assert_not_called()

    def test_run_stops_service_when_window_fails(self):
        service = Mock()
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=False), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'ApiService', return_value=service), \
             patch.object(desktop, 'launch_window', side_effect=desktop.LauncherError('浏览器失败')):
            with self.assertRaisesRegex(desktop.LauncherError, '浏览器失败'):
                desktop.run(self.home, {})
        service.stop.assert_called_once_with()

    def test_onboarding_called_once_and_failure_does_not_block(self):
        with patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=True), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'launch_window') as window:
            self.assertEqual(desktop.run(self.home, {'USERPROFILE': str(self.home)}), 0)
            self.onboarding.assert_called_once_with(self.home, self.home, True)
            self.onboarding.reset_mock()
            self.onboarding.side_effect = RuntimeError('secret-key')
            with patch.object(desktop.sys, 'stderr') as stderr:
                self.assertEqual(desktop.run(self.home, {'USERPROFILE': str(self.home)}), 0)
                self.assertNotIn('secret-key', str(stderr.write.call_args_list))
            self.assertEqual(window.call_count, 2)

    def test_onboarding_repeat_is_idempotent(self):
        # Exercise the real onboarding through the desktop entry on isolated paths.
        real_run = self.real_onboarding
        config = self.home / '.codex' / 'config.toml'
        config.parent.mkdir()
        config.write_text('', encoding='utf-8')
        key = self.home / '.talk' / 'keys' / 'agent_codex_t.key'
        key.parent.mkdir(parents=True)
        key.write_text('test-key', encoding='utf-8')
        self.onboarding.side_effect = lambda repo, home, apply: real_run(repo, home, apply, skip_members=True)
        with patch.object(desktop.mcp_onboarding.shutil, 'which', return_value=None), \
             patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), \
             patch.object(desktop, 'healthy', return_value=True), \
             patch.object(desktop, 'port_available', return_value=True), \
             patch.object(desktop, 'launch_window'):
            self.assertEqual(desktop.run(self.home, {'USERPROFILE': str(self.home)}), 0)
            original, timestamp = config.read_bytes(), config.stat().st_mtime_ns
            self.assertEqual(desktop.run(self.home, {'USERPROFILE': str(self.home)}), 0)
        self.assertEqual((config.read_bytes(), config.stat().st_mtime_ns), (original, timestamp))
        self.assertEqual(self.onboarding.call_count, 2)

    def test_main_already_running_is_quiet(self):
        with patch.object(desktop, 'SingleInstance',
                          side_effect=desktop.LauncherError('TALK 桌面启动器已在运行。')), \
             patch.object(desktop, 'notify') as notify:
            self.assertEqual(desktop.main([]), 0)
        notify.assert_called_once_with('TALK 桌面启动器已经在运行。')

    def test_install_shortcut_requires_vbs_and_reports_path(self):
        with self.assertRaisesRegex(desktop.LauncherError, '缺少桌面入口'):
            desktop.install_shortcut(self.home)
        (self.home / 'start-gui.vbs').write_text('', encoding='utf-8')
        ok = SimpleNamespace(returncode=0, stdout='C:\\Desktop\\TALK.lnk\n', stderr='')
        with patch.object(desktop.subprocess, 'run', return_value=ok) as run:
            self.assertEqual(desktop.install_shortcut(self.home, {}), 'C:\\Desktop\\TALK.lnk')
        self.assertIn('TALK.lnk', run.call_args.args[0][-1])
        icon = self.home.resolve() / 'web' / 'icons' / 'favicon.ico'
        self.assertIn(f"$s.IconLocation='{icon},0';", run.call_args.args[0][-1])
        failed = SimpleNamespace(returncode=1, stdout='', stderr='boom')
        with patch.object(desktop.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(desktop.LauncherError, '创建桌面快捷方式失败'):
                desktop.install_shortcut(self.home, {})


if __name__ == '__main__':
    unittest.main()

class BootStatusDesktopTests(unittest.TestCase):
    def test_window_uses_loading_page(self):
        with patch.object(desktop, 'find_browser', return_value=None), patch.object(desktop, 'open_default_browser') as browser, patch.object(desktop, 'notify'):
            desktop.launch_window('http://127.0.0.1:8123', {})
        browser.assert_called_once_with('http://127.0.0.1:8123/loading?desktop=1')

    def test_window_passes_health_url_to_browser(self):
        with tempfile.TemporaryDirectory() as home, \
             patch.object(desktop, 'find_browser', return_value='browser.exe'), \
             patch.object(desktop, 'run_browser') as browser:
            self.assertTrue(desktop.launch_window('http://127.0.0.1:8123', {'LOCALAPPDATA': home}))
        browser.assert_called_once_with('browser.exe', Path(home) / 'TALK',
                                        'http://127.0.0.1:8123/loading?desktop=1',
                                        {'LOCALAPPDATA': home}, health_url='http://127.0.0.1:8123')

    def test_summary_overwrites_and_removes_sensitive_paths(self):
        import json
        with tempfile.TemporaryDirectory() as home:
            result = {'detected': {'codex': {'detected': True}}, 'members_ok': ['agent:codex-t'], 'member_missing': [], 'configs_written': [{'client':'codex', 'path':'secret-path'}], 'skipped': [], 'errors': [], 'member_status':'checked'}
            desktop.write_boot_status(home, result)
            path = Path(home) / 'logs/launcher/boot-status.json'
            first = json.loads(path.read_text(encoding='utf-8'))
            desktop.write_boot_status(home, result)
            second = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(first['configs_written'], ['codex'])
            self.assertEqual(first['detected'], ['codex'])
            self.assertTrue(second['ready'])
            self.assertNotIn('secret-path', str(second))
            desktop.write_boot_status(home, {'_failed': True})
            self.assertFalse(json.loads(path.read_text(encoding='utf-8'))['ready'])

    def test_unavailable_members_do_not_mark_configuration_failed(self):
        import json
        with tempfile.TemporaryDirectory() as home:
            desktop.write_boot_status(home, {'errors': [], 'member_status': 'api_unavailable'})
            data = json.loads((Path(home) / 'logs/launcher/boot-status.json').read_text(encoding='utf-8'))
            self.assertTrue(data['ready'])
            self.assertEqual(data['member_status'], 'api_unavailable')
            self.assertNotIn('error', data)

    def test_onboarding_exception_records_failure_and_opens_window(self):
        import json
        with tempfile.TemporaryDirectory() as home, patch.object(desktop, 'read_server', return_value=('127.0.0.1', 8000)), patch.object(desktop, 'healthy', return_value=True), patch.object(desktop, 'port_available', return_value=False), patch.object(desktop.mcp_onboarding, 'run', side_effect=RuntimeError('secret-key')), patch.object(desktop, 'launch_window') as window:
            self.assertEqual(desktop.run(home, {}), 0)
            data = json.loads((Path(home) / 'logs/launcher/boot-status.json').read_text(encoding='utf-8'))
            self.assertFalse(data['ready'])
            self.assertNotIn('secret-key', str(data))
            window.assert_called_once()
