"""Windows desktop wrapper for a portable TALK runtime."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
from scripts import talk_runtime


class LauncherError(Exception):
    pass


def resolve_config(env):
    home = Path(env.get('TALK_HOME') or SOURCE_ROOT).resolve()
    path = Path(env.get('TALK_RUNTIME_CONFIG') or home / 'config' / 'runtime.json').resolve()
    try:
        config = talk_runtime.load_config(path)
        parsed = urlsplit(config['base_url'])
        port = parsed.port
        if port is None or not 1 <= port <= 65535:
            raise ValueError('base_url 必须包含有效端口')
    except (OSError, ValueError, KeyError, TypeError, talk_runtime.RuntimeErrorCode) as exc:
        raise LauncherError(f'运行配置无效：{path}；{exc}') from exc
    return home, path, config, f'http://127.0.0.1:{port}'


def notify(message):
    print(message, file=sys.stderr, flush=True)
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, str(message), 'TALK', 0x10)


def find_edge(env):
    for name in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        root = env.get(name)
        if root:
            candidate = Path(root) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'
            if candidate.is_file():
                return candidate
    raise LauncherError('未找到 Microsoft Edge，请安装 Edge 后重试。')


def run_edge(edge, home, url, env):
    profile = home / 'data' / 'launcher-profile'
    profile.mkdir(parents=True, exist_ok=True)
    delay = env.get('TALK_LAUNCHER_AUTOCLOSE_MS')
    seconds = max(0, int(delay)) / 1000 if delay else None
    process = subprocess.Popen([str(edge), f'--app={url}', f'--user-data-dir={profile}',
                                '--no-first-run', '--no-default-browser-check',
                                '--disable-background-mode'], env=env)
    timer = None
    if seconds is not None:
        def close_edge():
            try:
                if process.poll() is None:
                    process.terminate()
            except OSError:
                pass  # The Edge process may already have exited.
        timer = threading.Timer(seconds, close_edge)
        timer.daemon = True
        timer.start()
    try:
        process.wait()
    finally:
        if timer:
            timer.cancel()
            timer.join()


class SingleInstance:
    def __init__(self, path):
        self.name = 'Local\\TALK-launcher-' + hashlib.sha256(str(path).casefold().encode('utf-8')).hexdigest()
        self.handle = None

    def __enter__(self):
        if os.name != 'nt':
            raise LauncherError('桌面启动器仅支持 Windows。')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        self.kernel = kernel
        self.handle = kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise LauncherError('无法创建单实例锁。')
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise LauncherError('TALK 桌面启动器已在运行。')
        return self

    def __exit__(self, *args):
        if self.handle:
            self.kernel.CloseHandle(self.handle)


def healthy(url):
    try:
        with urllib.request.urlopen(url + '/healthz', timeout=2) as response:
            return response.status == 200 and json.load(response).get('status') == 'ok'
    except (OSError, ValueError, TypeError):
        return False


class Launcher:
    def __init__(self, home, path, config, url, env):
        self.home, self.path, self.config, self.url = home, path, config, url
        self.env = dict(env, TALK_HOME=str(home))
        if (home / 'config' / 'config.toml').is_file():
            self.env['TALK_CONFIG'] = str(home / 'config' / 'config.toml')
        self.env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(SOURCE_ROOT), self.env.get('PYTHONPATH', ''))))
        self.owned = False
        self.pid = None
        self.identity = None

    def run_runtime(self, action, *options):
        return subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'scripts.talk_runtime', action,
                               '--config', str(self.path), '--apply', *options], cwd=self.home, env=self.env,
                              text=True, encoding='utf-8', errors='replace', capture_output=True)

    def read_owned_identity(self):
        try:
            health = json.loads((Path(self.config['state_dir']) / 'runtime' / 'health.json').read_text(encoding='utf-8'))
            if (health.get('project_id') == self.config['project_id'] and health.get('api_mode') == 'owned'
                and talk_runtime.is_owned_descendant(self.pid, health.get('pid'), talk_runtime.process_parents())):
                return health['pid'], health['started_at']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def stop(self):
        if not self.owned:
            return True, ''
        if self.read_owned_identity() != self.identity:
            return False, '无法确认运行时归属，已阻止停止；请检查状态。'
        try:
            result = self.run_runtime('stop', '--wait')
        except OSError as exc:
            return False, str(exc)
        if result.returncode:
            return False, (result.stdout + result.stderr).strip()
        self.owned = False
        return True, ''

    def start(self):
        if healthy(self.url):
            return
        port = urlsplit(self.url).port
        try:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', port))
        except OSError as exc:
            raise LauncherError(f'端口 {port} 已占用且 TALK 健康检查失败。') from exc
        result = self.run_runtime('serve', '--detach')
        if result.returncode:
            raise LauncherError('启动运行时失败：' + (result.stdout + result.stderr).strip())
        try:
            self.pid = int(json.loads(result.stdout)['started_launcher_pid'])
            if self.pid <= 0:
                raise ValueError('invalid pid')
        except (ValueError, KeyError, TypeError) as exc:
            raise LauncherError('启动结果缺少进程身份，服务可能残留；请检查 status.bat，必要时使用 stop.bat。') from exc
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            identity = self.read_owned_identity()
            if identity:
                self.identity, self.owned = identity, True
                if healthy(self.url):
                    return
            time.sleep(.25)
        if self.owned:
            ok, detail = self.stop()
            if not ok:
                raise LauncherError('启动超时，停止被阻止：' + detail + '；请检查 status.bat / stop.bat。')
        else:
            raise LauncherError('启动超时，无法确认进程归属，服务可能残留；请检查 status.bat / stop.bat。')
        raise LauncherError('启动超时，已停止本启动器的服务。')

def main():
    try:
        home, path, config, url = resolve_config(os.environ)
        with SingleInstance(path):
            edge = find_edge(os.environ)
            launcher = Launcher(home, path, config, url, os.environ)
            try:
                launcher.start()
                run_edge(edge, home, url + '/?desktop=1', launcher.env)
            except Exception:
                if launcher.owned:
                    ok, detail = launcher.stop()
                    if not ok:
                        notify('服务未停止，请处理忙任务后使用 stop.bat/status.bat。\n' + detail)
                raise
            ok, detail = launcher.stop()
            if not ok:
                notify('服务未停止，请处理忙任务后使用 stop.bat/status.bat。\n' + detail)
                return 1
    except Exception as exc:
        notify(str(exc) + '\n异常退出或强制结束后服务可能残留，可使用 stop.bat 停止。')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
