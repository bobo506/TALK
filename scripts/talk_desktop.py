"""仓库内 TALK 的桌面启动入口（Windows）。

服务已在运行时直接开窗口接入；未运行就按根目录 ``config.toml`` 启动一个
API 子进程，窗口关闭后只停止这个子进程，不碰其他人启动的实例。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scripts import mcp_onboarding
from scripts.talk_launcher import (  # noqa: E402  (依赖上面的 sys.path 插入)
    LauncherError,
    SingleInstance,
    find_browser,
    healthy,
    notify,
    open_default_browser,
    run_browser,
)

DESKTOP_QUERY = '/loading?desktop=1'
START_TIMEOUT_SEC = 45
STOP_TIMEOUT_SEC = 20


def read_server(home):
    """读取 ``config.toml`` 的 host/port；只依赖 [server] 小节。"""
    path = Path(home) / 'config.toml'
    try:
        with path.open('rb') as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LauncherError(f'无法读取配置：{path}；{exc}') from exc
    server = data.get('server') or {}
    port = server.get('port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise LauncherError(f'配置项 server.port 无效：{port!r}')
    return str(server.get('host') or '127.0.0.1'), port


def local_url(host, port):
    """把监听地址换算成本机可访问的 URL。"""
    target = '127.0.0.1' if host in ('', '0.0.0.0', '::', 'localhost') else host
    if ':' in target and not target.startswith('['):
        target = f'[{target}]'
    return f'http://{target}:{port}'


def plan_action(api_healthy, port_available):
    """决定本次启动动作：接入已有服务、自己启动，或因端口被占而报错。"""
    if api_healthy:
        return 'attach'
    if port_available:
        return 'start'
    return 'blocked'


def port_available(host, port):
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind(('' if host in ('0.0.0.0', '::') else host, port))
    except OSError:
        return False
    return True


class ApiService:
    """按根目录配置启动/停止一个 API 子进程；只对自己启动的进程负责。"""

    def __init__(self, home, host, port, env=None):
        self.home = Path(home)
        self.host = host
        self.port = port
        self.env = dict(env if env is not None else os.environ)
        self.env['TALK_CONFIG'] = str(self.home / 'config.toml')
        self.env['PYTHONPATH'] = os.pathsep.join(
            filter(None, (str(self.home), self.env.get('PYTHONPATH', ''))))
        self.log_dir = self.home / 'logs' / 'launcher'
        self.control_file = self.log_dir / f'api-{port}.stop'
        self.log_file = self.log_dir / f'api-{port}.log'
        self.process = None

    def start(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if self.control_file.exists():
            self.control_file.unlink()
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        with self.log_file.open('ab') as log:
            self.process = subprocess.Popen(
                [sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_api',
                 '--host', self.host, '--port', str(self.port),
                 '--control-file', str(self.control_file)],
                cwd=str(self.home), env=self.env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, creationflags=flags)

    def wait_healthy(self, url, timeout=START_TIMEOUT_SEC):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if healthy(url):
                return
            if self.process is not None and self.process.poll() is not None:
                raise LauncherError(
                    f'API 启动失败（退出码 {self.process.returncode}），详见 {self.log_file}')
            time.sleep(.25)
        raise LauncherError(f'API 启动超时，详见 {self.log_file}')

    def stop(self, timeout=STOP_TIMEOUT_SEC):
        """通过控制文件优雅停止；超时才终止自己的子进程。"""
        if self.process is None:
            return
        try:
            self.control_file.parent.mkdir(parents=True, exist_ok=True)
            self.control_file.write_text('stop', encoding='utf-8')
        except OSError:
            pass
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            self.process = None
            try:
                self.control_file.unlink()
            except OSError:
                pass


def launch_window(url, env):
    """Launch a browser window and report whether it is an app window."""
    browser = find_browser(env)
    if browser is None:
        open_default_browser(url + DESKTOP_QUERY)
        notify('已使用系统默认浏览器；关闭标签页不会自动停服务，可用 stop.bat 停止服务。')
        return False
    profile_root = Path(env.get('LOCALAPPDATA') or Path.home()) / 'TALK'
    run_browser(browser, profile_root, url + DESKTOP_QUERY, env)
    return True


def install_shortcut(home, env=None):
    """在桌面生成指向 ``start-gui.vbs`` 的 TALK 快捷方式。"""
    env = dict(env if env is not None else os.environ)
    home = Path(home).resolve()
    vbs = home / 'start-gui.vbs'
    if not vbs.is_file():
        raise LauncherError(f'缺少桌面入口：{vbs}')
    browser = find_browser(env) or Path(env.get('SystemRoot', r'C:\Windows')) / 'System32' / 'shell32.dll'
    script = (
        "$ErrorActionPreference='Stop';"
        "$desktop=[Environment]::GetFolderPath('Desktop');"
        "$link=Join-Path $desktop 'TALK.lnk';"
        "$shell=New-Object -ComObject WScript.Shell;"
        "$s=$shell.CreateShortcut($link);"
        f"$s.TargetPath=Join-Path $env:SystemRoot 'System32\\wscript.exe';"
        f"$s.Arguments='\"{vbs}\"';"
        f"$s.WorkingDirectory='{home}';"
        f"$s.IconLocation='{browser},0';"
        "$s.Description='TALK 桌面版';"
        "$s.Save();"
        "Write-Output $link"
    )
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise LauncherError('创建桌面快捷方式失败：' + (result.stdout + result.stderr).strip())
    return result.stdout.strip()


def write_boot_status(home, result=None):
    """Write a non-sensitive onboarding summary."""
    result = result or {}
    clients = ('codex', 'kimi', 'workbuddy', 'dsh')
    members = {f'agent:{name}-t' for name in clients}
    detected = result.get('detected', {})
    def client_names(items):
        return [item['client'] for item in items if isinstance(item, dict) and item.get('client') in clients]
    failed = bool(result.get('errors')) or result.get('member_status') == 'api_unavailable' or result.get('_failed', False)
    data = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'detected': [name for name in clients if isinstance(detected.get(name), dict) and detected[name].get('detected') is True],
        'members_ok': [name for name in result.get('members_ok', []) if name in members],
        'member_missing': [name for name in result.get('member_missing', []) if name in members],
        'configs_written': client_names(result.get('configs_written', [])),
        'skipped': client_names(result.get('skipped', [])),
        'download': {'needed': False, 'text': '无需下载'},
        'ready': not failed,
    }
    if failed:
        data['error'] = 'MCP 配置失败，请查看日志'
    path = Path(home) / 'logs' / 'launcher' / 'boot-status.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def run(home, env):
    host, port = read_server(home)
    url = local_url(host, port)
    action = plan_action(healthy(url), port_available(host, port))
    if action == 'blocked':
        raise LauncherError(f'端口 {port} 已被占用，但 TALK 健康检查失败；请检查占用进程后再试。')
    result = {'_failed': True}
    try:
        result = mcp_onboarding.run(Path(home), Path(env.get('USERPROFILE') or Path.home()), True)
        if (result['errors'] or result['member_status'] == 'api_unavailable') and sys.stderr is not None:
            print('Warning: MCP onboarding reported an error or member API unavailable.', file=sys.stderr)
    except Exception:
        result = {'_failed': True}
        # Do not include exception text, which may contain configuration secrets.
        if sys.stderr is not None:
            print('Warning: MCP onboarding failed.', file=sys.stderr)
    try:
        write_boot_status(home, result)
    except Exception:
        if sys.stderr is not None:
            print('Warning: could not write boot status.', file=sys.stderr)
    if action == 'attach':
        launch_window(url, env)
        return 0
    service = ApiService(home, host, port, env)
    owns_service = False
    try:
        service.start()
        owns_service = True
        service.wait_healthy(url)
        launch_window(url, env)
    except BaseException:
        if owns_service:
            service.stop()
        raise
    print('服务仍在运行，可在页面点“退出服务”或运行 stop.bat。', flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', default=str(SOURCE_ROOT), help='TALK 根目录')
    parser.add_argument('--install-shortcut', action='store_true', help='在桌面创建 TALK 快捷方式')
    args = parser.parse_args(argv)
    home = Path(args.home).resolve()
    try:
        if args.install_shortcut:
            print(install_shortcut(home))
            return 0
        with SingleInstance(home / 'config.toml'):
            return run(home, os.environ)
    except LauncherError as exc:
        if '已在运行' in str(exc):
            notify('TALK 桌面启动器已经在运行。')
            return 0
        notify(str(exc) + '\n排查：status.bat 查看状态，stop.bat 停止服务。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
