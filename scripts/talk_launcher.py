"""Desktop wrapper for a portable TALK runtime."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
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


def browser_candidates(env, platform=None):
    platform = platform or sys.platform
    if platform == 'darwin':
        user = Path(env.get('HOME') or str(Path.home()))
        return ([Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                 user / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
                [Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')])
    if platform == 'win32':
        chrome = [Path(env[name]) / 'Google/Chrome/Application/chrome.exe'
                  for name in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA') if env.get(name)]
        edge = [Path(env[name]) / 'Microsoft/Edge/Application/msedge.exe'
                for name in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA') if env.get(name)]
        return chrome, edge
    return [], []


def find_browser(env, platform=None):
    chrome, edge = browser_candidates(env, platform)
    return next((path for path in (*chrome, *edge) if path.is_file()), None)


_CHROME_WINDOW_CLASS = 'Chrome_WidgetWin_1'
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WM_CLOSE = 0x0010
_TASKKILL_TIMEOUT_SEC = 5
_USER32 = None


def _get_user32():
    """Return a private WinDLL handle for user32 with explicit 64-bit safe signatures."""
    global _USER32
    if os.name != 'nt':
        return None
    if _USER32 is not None:
        return _USER32
    from ctypes import wintypes
    dll = ctypes.WinDLL('user32', use_last_error=True)
    lpdword = ctypes.POINTER(wintypes.DWORD)
    lprect = ctypes.POINTER(wintypes.RECT)
    dll.EnumWindows.argtypes = (ctypes.c_void_p, wintypes.LPARAM)
    dll.EnumWindows.restype = wintypes.BOOL
    dll.GetWindowThreadProcessId.argtypes = (wintypes.HWND, lpdword)
    dll.GetWindowThreadProcessId.restype = wintypes.DWORD
    dll.IsWindowVisible.argtypes = (wintypes.HWND,)
    dll.IsWindowVisible.restype = wintypes.BOOL
    dll.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    dll.GetClassNameW.restype = ctypes.c_int
    dll.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    dll.GetWindowLongW.restype = wintypes.LONG
    dll.IsIconic.argtypes = (wintypes.HWND,)
    dll.IsIconic.restype = wintypes.BOOL
    dll.GetWindowRect.argtypes = (wintypes.HWND, lprect)
    dll.GetWindowRect.restype = wintypes.BOOL
    dll.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    dll.PostMessageW.restype = wintypes.BOOL
    _USER32 = dll
    return _USER32


def _patch_json_file(path, mutator):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        data = {}
    mutator(data)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def prepare_browser_profile(profile):
    def disable_background(data):
        if not isinstance(data.get('background_mode'), dict):
            data['background_mode'] = {}
        data['background_mode']['enabled'] = False

    def disable_local_state_background(data):
        disable_background(data)
        if not isinstance(data.get('glic'), dict):
            data['glic'] = {}
        data['glic']['launcher_enabled'] = False

    _patch_json_file(profile / 'Default' / 'Preferences', disable_background)
    _patch_json_file(profile / 'Local State', disable_local_state_background)


def _normalize_profile_path(profile):
    return os.path.normcase(os.path.abspath(str(profile))).rstrip('\\/')


def _split_windows_cmdline(cmdline):
    """Split a Windows command line into argv tokens honoring double-quote grouping."""
    tokens = []
    current = []
    in_quotes = False
    i = 0
    length = len(cmdline)
    while i < length:
        ch = cmdline[i]
        if ch.isspace() and not in_quotes:
            if current:
                tokens.append(''.join(current))
                current = []
            i += 1
            continue
        if ch == '\\':
            slashes = 0
            while i < length and cmdline[i] == '\\':
                slashes += 1
                i += 1
            if i < length and cmdline[i] == '"':
                current.append('\\' * (slashes // 2))
                if slashes % 2 == 1:
                    current.append('"')
                else:
                    in_quotes = not in_quotes
                i += 1
            else:
                current.append('\\' * slashes)
            continue
        if ch == '"':
            if in_quotes and i + 1 < length and cmdline[i + 1] == '"':
                current.append('"')
                i += 2
            else:
                in_quotes = not in_quotes
                i += 1
            continue
        current.append(ch)
        i += 1
    if current:
        tokens.append(''.join(current))
    return tokens


def _cmdline_matches_profile(cmdline, profile):
    if not isinstance(cmdline, str) or not cmdline.strip():
        return False
    tokens = _split_windows_cmdline(cmdline)
    if len(tokens) < 2:
        return False
    last_profile = None
    i = 1
    while i < len(tokens):
        arg = tokens[i]
        low = arg.lower()
        if low.startswith('--user-data-dir='):
            last_profile = arg[len('--user-data-dir='):]
        elif low == '--user-data-dir' and i + 1 < len(tokens):
            last_profile = tokens[i + 1]
            i += 1
        i += 1
    if not last_profile:
        return False
    return _normalize_profile_path(last_profile) == _normalize_profile_path(profile)


def _get_process_tree_pids(root_pid):
    if type(root_pid) is not int or root_pid <= 0:
        return set()
    pids = {root_pid}
    try:
        parents = talk_runtime.process_parents()
    except Exception:
        return pids
    changed = True
    while changed:
        changed = False
        for pid, parent_pid in parents.items():
            if parent_pid in pids and pid not in pids:
                pids.add(pid)
                changed = True
    return pids


def _find_profile_browser_pids(browser_name, profile):
    """Return PIDs of same-executable browser processes using the exact TALK profile."""
    if os.name != 'nt' or not browser_name or profile is None:
        return set()
    exe_name = Path(str(browser_name)).name
    if not exe_name or not re.fullmatch(r'[A-Za-z0-9._-]+', exe_name):
        return set()
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
        "$ErrorActionPreference='SilentlyContinue';"
        f"$items=Get-CimInstance Win32_Process -Filter \"Name='{exe_name}'\" "
        "| Select-Object ProcessId,CommandLine;"
        "if ($items) { $items | ConvertTo-Json -Compress }"
    )
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=5, check=False, creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    raw = (result.stdout or '').lstrip('\ufeff').strip()
    if result.returncode != 0 or not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except ValueError:
        return set()
    records = [parsed] if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
    matched = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        pid = record.get('ProcessId')
        cmdline = record.get('CommandLine')
        if type(pid) is int and pid > 0 and _cmdline_matches_profile(cmdline, profile):
            matched.add(pid)
    return matched


def _list_visible_browser_windows(target_pids):
    """Return HWNDs of visible/minimized Chromium app windows, or None if enumeration fails."""
    if os.name != 'nt' or not target_pids:
        return []
    try:
        from ctypes import wintypes
        user32 = _get_user32()
        if user32 is None:
            return None
    except Exception:
        return None
    hwnds = []
    callback_failed = False
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        nonlocal callback_failed
        try:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in target_pids:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            class_buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, class_buf, 64)
            if class_buf.value != _CHROME_WINDOW_CLASS:
                return True
            ex_style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            if ex_style & _WS_EX_TOOLWINDOW:
                return True
            if user32.IsIconic(hwnd):
                hwnds.append(int(hwnd))
                return True
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                if (rect.right - rect.left) > 0 and (rect.bottom - rect.top) > 0:
                    hwnds.append(int(hwnd))
            return True
        except Exception:
            callback_failed = True
            return False

    try:
        cb = enum_proc(callback)
        ok = user32.EnumWindows(ctypes.cast(cb, ctypes.c_void_p), 0)
        if not ok or callback_failed:
            return None
    except Exception:
        return None
    return hwnds


def _post_close_windows(hwnds):
    if os.name != 'nt' or not hwnds:
        return
    try:
        user32 = _get_user32()
        if user32 is None:
            return
    except Exception:
        return
    for hwnd in hwnds:
        try:
            user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
        except Exception:
            pass


def _wait_process_exit(process, timeout):
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.1)
    return process.poll() is not None


def _run_taskkill(pid, *, force=False, tree=True):
    cmd = ['taskkill', '/PID', str(pid)]
    if tree:
        cmd.append('/T')
    if force:
        cmd.append('/F')
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.run(
        cmd, capture_output=True, check=False,
        timeout=_TASKKILL_TIMEOUT_SEC, creationflags=creationflags,
    )


def terminate_browser_process(process, *, profile=None, browser_name=None, grace_timeout=3.0):
    """Gracefully close TALK's browser (so Chrome removes its tray icon), then force-kill if stuck."""
    if os.name != 'nt':
        process.terminate()
        return True
    pid = getattr(process, 'pid', None)
    succeeded = False
    if process.poll() is None and type(pid) is int and pid > 0:
        tree_pids = _get_process_tree_pids(pid)
        windows = _list_visible_browser_windows(tree_pids)
        if windows:
            _post_close_windows(windows)
        try:
            _run_taskkill(pid, force=False, tree=True)
        except (OSError, subprocess.SubprocessError):
            pass
        if _wait_process_exit(process, grace_timeout):
            succeeded = True
        else:
            try:
                forced = _run_taskkill(pid, force=True, tree=True)
            except (OSError, subprocess.SubprocessError):
                forced = None
            if _wait_process_exit(process, 1.0) or (forced is not None and forced.returncode == 0):
                succeeded = True
    elif process.poll() is not None:
        succeeded = True

    if profile is not None and browser_name:
        orphan_pids = _find_profile_browser_pids(browser_name, profile)
        if orphan_pids:
            orphan_windows = _list_visible_browser_windows(orphan_pids)
            if orphan_windows:
                _post_close_windows(orphan_windows)
            for opid in sorted(orphan_pids):
                try:
                    _run_taskkill(opid, force=False, tree=True)
                except (OSError, subprocess.SubprocessError):
                    pass
            deadline = time.monotonic() + min(2.0, grace_timeout)
            while time.monotonic() < deadline:
                remaining = _find_profile_browser_pids(browser_name, profile)
                if not remaining:
                    break
                time.sleep(0.2)
            else:
                remaining = _find_profile_browser_pids(browser_name, profile)
                for opid in sorted(remaining):
                    try:
                        _run_taskkill(opid, force=True, tree=True)
                    except (OSError, subprocess.SubprocessError):
                        pass
    return succeeded or process.poll() is not None


def _cleanup_orphan_profile_tray(browser, profile):
    """Clean up windowless tray-only zombie processes bound to TALK's own launcher profile."""
    if os.name != 'nt':
        return
    try:
        browser_path = Path(browser)
        if not browser_path.is_file() or not Path(profile).exists():
            return
    except OSError:
        return
    pids = _find_profile_browser_pids(browser_path.name, profile)
    if not pids:
        return
    # Fail-closed: never kill if window enumeration failed (None) or any app window is visible.
    windows = _list_visible_browser_windows(pids)
    if windows is None or windows:
        return
    try:
        for pid in sorted(pids):
            _run_taskkill(pid, force=False, tree=True)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            remaining = _find_profile_browser_pids(browser_path.name, profile)
            if not remaining:
                return
            time.sleep(0.2)
        remaining = _find_profile_browser_pids(browser_path.name, profile)
        if not remaining:
            return
        remaining_windows = _list_visible_browser_windows(remaining)
        if remaining_windows is None or remaining_windows:
            return
        for pid in sorted(remaining):
            _run_taskkill(pid, force=True, tree=True)
    except (OSError, subprocess.SubprocessError):
        return


def _request_browser_close(process, stop, closed, *, profile=None, browser_name=None, close_lock=None):
    def _do_close():
        if stop.is_set() or closed.is_set() or process.poll() is not None:
            return
        closed.set()
        try:
            ok = terminate_browser_process(process, profile=profile, browser_name=browser_name)
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok and process.poll() is None:
            closed.clear()

    if close_lock is not None:
        with close_lock:
            _do_close()
    else:
        _do_close()


def monitor_browser_health(process, health_url, stop, closed, *, profile=None, browser_name=None, close_lock=None):
    failures = 0
    while not stop.wait(2):
        if process.poll() is not None:
            return
        failures = 0 if healthy(health_url) else failures + 1
        if failures >= 3:
            _request_browser_close(
                process, stop, closed,
                profile=profile, browser_name=browser_name, close_lock=close_lock,
            )
            return


def monitor_browser_window(process, profile, stop, closed, *, browser_name=None,
                           poll_interval=1.0, grace_polls=2, close_lock=None):
    """Exit TALK's browser cleanly once all of its visible app windows have closed."""
    if os.name != 'nt':
        return
    pid = getattr(process, 'pid', None)
    if type(pid) is not int or pid <= 0:
        return
    saw_window = False
    missing_polls = 0
    while not stop.wait(poll_interval):
        if process.poll() is not None:
            return
        tree_pids = _get_process_tree_pids(pid)
        windows = _list_visible_browser_windows(tree_pids)
        if windows is None:
            # Fail-closed on enumeration error: do not assume windows disappeared.
            continue
        if windows:
            saw_window = True
            missing_polls = 0
            continue
        if not saw_window:
            continue
        missing_polls += 1
        if missing_polls >= grace_polls:
            _request_browser_close(
                process, stop, closed,
                profile=profile, browser_name=browser_name, close_lock=close_lock,
            )
            return


def run_browser(browser, home, url, env, health_url=None):
    profile = home / 'data' / 'launcher-profile'
    browser_name = Path(str(browser)).name
    _cleanup_orphan_profile_tray(browser, profile)
    prepare_browser_profile(profile)
    delay = env.get('TALK_LAUNCHER_AUTOCLOSE_MS')
    seconds = max(0, int(delay)) / 1000 if delay else None
    process = subprocess.Popen([str(browser), f'--app={url}', f'--user-data-dir={profile}',
                                '--no-first-run', '--no-default-browser-check',
                                '--disable-background-mode', '--disable-features=Glic'], env=env)
    timer = None
    auto_closed = False
    stop_monitor = threading.Event()
    health_closed = threading.Event()
    close_lock = threading.Lock()
    monitors = []
    if health_url:
        monitor = threading.Thread(
            target=monitor_browser_health,
            args=(process, health_url, stop_monitor, health_closed),
            kwargs={'profile': profile, 'browser_name': browser_name, 'close_lock': close_lock},
            daemon=True,
        )
        monitor.start()
        monitors.append(monitor)
    if os.name == 'nt' and type(getattr(process, 'pid', None)) is int and process.pid > 0:
        win_monitor = threading.Thread(
            target=monitor_browser_window,
            args=(process, profile, stop_monitor, health_closed),
            kwargs={'browser_name': browser_name, 'close_lock': close_lock},
            daemon=True,
        )
        win_monitor.start()
        monitors.append(win_monitor)
    if seconds is not None:
        def close_browser():
            nonlocal auto_closed
            try:
                if process.poll() is None:
                    auto_closed = True
                    process.terminate()
            except OSError:
                pass  # The browser process may already have exited.
        timer = threading.Timer(seconds, close_browser)
        timer.daemon = True
        timer.start()
    try:
        exit_code = process.wait()
    finally:
        stop_monitor.set()
        for monitor in monitors:
            monitor.join()
        if timer:
            timer.cancel()
            timer.join()
    if exit_code and not auto_closed and not health_closed.is_set():
        raise LauncherError(f"浏览器启动或运行失败（退出码 {exit_code}）。")


def open_default_browser(url):
    try:
        if not webbrowser.open(url):
            raise LauncherError('无法打开系统默认浏览器，请检查浏览器设置。')
    except (OSError, webbrowser.Error) as exc:
        raise LauncherError(f'无法打开系统默认浏览器：{exc}') from exc


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
            browser = find_browser(os.environ)
            launcher = Launcher(home, path, config, url, os.environ)
            try:
                launcher.start()
                if browser is None:
                    open_default_browser(url + '/?desktop=1')
                    notify('已使用系统默认浏览器；关闭浏览器窗口不会自动停服务，请用 stop.bat 停止服务。')
                    return 0
                run_browser(browser, home, url + '/?desktop=1', launcher.env, health_url=url)
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
