"""运行器版本只读探测，不改变运行器或配置。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

# codex 来自 bridges/codex_execution_native.SUPPORTED_VERSIONS；其余为当前验证基线。
ADAPTED_VERSIONS = {
    "codex": ("0.164.0", "bridges/codex_execution_native.SUPPORTED_VERSIONS"),
    "kimi-code": ("2.0.2", "2026-11-04 当前验证基线"),
    "dsh": ("0.2.1-rc.5", "2026-11-04 当前验证基线"),
    "workbuddy": ("2.165.0", "2026-11-05 本机验证基线"),
}
WORKBUDDY_ACP_ADAPTED_DESKTOP = ("5.8.3", "2026-11-05 ACP 验证基线；5.9.3 已知不兼容")
COMMANDS = {"codex": ("codex.cmd", "codex"), "kimi-code": ("kimi",), "dsh": ("dsh.cmd", "dsh")}
_VERSION = re.compile(r"(?<![\w.])(\d+(?:\.\d+)+(?:-rc\.\d+)?)(?![\w.+-])")
_cache = {}
_lock = threading.Lock()


def parse_version(runtime: str, output: str) -> str | None:
    if runtime == "codex":
        match = re.search(r"\bcodex-cli\s+(\d+(?:\.\d+)+(?:-rc\.\d+)?)(?![\w.+-])", output)
    else:
        match = _VERSION.search(output)
    return match.group(1) if match else None


def _parts(version):
    if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)+(?:-rc\.\d+)?", version):
        return None
    base, _, rc = version.partition("-rc.")
    return tuple(map(int, base.split("."))), int(rc) if rc else None


def compare_versions(detected, adapted):
    a, b = _parts(detected), _parts(adapted)
    if a is None or b is None:
        return "unknown"
    width = max(len(a[0]), len(b[0]))
    av = a[0] + (0,) * (width - len(a[0]))
    bv = b[0] + (0,) * (width - len(b[0]))
    if av == bv:
        av = (a[1] is None, a[1] or 0)
        bv = (b[1] is None, b[1] or 0)
    return "match" if av == bv else "newer" if av > bv else "older"


def _probe_workbuddy_desktop():
    """读取 Windows 可执行文件的固定版本资源，不启动桌面程序。"""
    try:
        import ctypes
        from ctypes import wintypes

        localappdata = os.environ.get("LOCALAPPDATA")
        if not localappdata:
            return None, "未设置 LOCALAPPDATA，无法检测 WorkBuddy 桌面版本"
        exe = Path(localappdata) / "Programs/WorkBuddy/WorkBuddy.exe"
        if not exe.is_file():
            return None, "未找到 WorkBuddy 桌面程序"
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        version.VerQueryValueW.restype = wintypes.BOOL
        size = version.GetFileVersionInfoSizeW(str(exe), None)
        if not size:
            return None, "无法读取 WorkBuddy 桌面版本资源"
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(exe), 0, size, buf):
            return None, "无法读取 WorkBuddy 桌面版本资源"
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or length.value < 52:
            return None, "无法解析 WorkBuddy 桌面版本资源"
        words = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD))
        if words[0] != 0xFEEF04BD:
            return None, "无法解析 WorkBuddy 桌面版本资源"
        ms, ls = words[2], words[3]
        parts = [ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff]
        if parts[-1] == 0:
            parts.pop()
        return ".".join(map(str, parts)), ""
    except Exception:
        return None, "WorkBuddy 桌面版本探测失败"


def _probe_workbuddy():
    try:
        localappdata = os.environ.get("LOCALAPPDATA")
        if not localappdata:
            return None, "未设置 LOCALAPPDATA，无法检测 WorkBuddy", "error"
        exe = Path(localappdata) / "Programs/WorkBuddy/WorkBuddy.exe"
        asar = exe.parent / "resources/app.asar"
        entry = asar / "cli/bin/codebuddy"
        if not exe.is_file():
            return None, "未找到 WorkBuddy", "missing"
        if not asar.is_file():
            return None, "未找到 WorkBuddy", "error"
        with tempfile.TemporaryDirectory(prefix="talk-wb-version-") as config_dir:
            env = os.environ.copy()
            env.update({
                "CODEBUDDY_CONFIG_DIR": config_dir,
                "WORKBUDDY_CONFIG_DIR": config_dir,
                "ELECTRON_RUN_AS_NODE": "1",
                "CODEBUDDY_FORCE_LITE_WB_BUNDLE": "1",
                "DISABLE_AUTOUPDATER": "1",
                "CODEBUDDY_REMOTE_CONFIG_DISABLED": "1",
                "CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS": "1",
            })
            result = subprocess.run(
                [str(exe), str(entry), "--version"], timeout=5,
                stdin=subprocess.DEVNULL, capture_output=True, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                return None, "版本命令执行失败", "error"
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            version = parse_version("workbuddy", output)
            return (version, "", "ok") if version else (None, "无法解析版本", "error")
    except subprocess.TimeoutExpired:
        return None, "探测超时", "error"
    except Exception:
        return None, "版本探测失败", "error"


def _probe(runtime):
    if runtime == "workbuddy":
        return _probe_workbuddy()
    commands = COMMANDS.get(runtime)
    if not commands:
        return None, "无可靠 CLI 探针", "error"
    try:
        exe = next((path for name in commands if (path := shutil.which(name))), None)
        if not exe:
            return None, "未找到命令", "missing"
        result = subprocess.run([exe, "--version"], timeout=3, stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode != 0:
            return None, "版本命令执行失败", "error"
        output = result.stdout.decode("utf-8", errors="replace")
        version = parse_version(runtime, output)
        return (version, "", "ok") if version else (None, "无法解析版本", "error")
    except subprocess.TimeoutExpired:
        return None, "探测超时", "error"
    except Exception:
        return None, "版本探测失败", "error"


def clear_cache():
    with _lock:
        _cache.clear()


def get_version(runtime):
    # 防止并发请求重复启动探针。
    with _lock:
        now = time.monotonic()
        cached = _cache.get(runtime)
        if cached and now - cached[0] < 600:
            return dict(cached[1])
        adapted, source = ADAPTED_VERSIONS.get(runtime, (None, "无已验证基线"))
        detected, detail, probe_status = _probe(runtime)
        result = {"adapted_version": adapted, "adapted_source": source, "detected_version": detected,
                  "status": compare_versions(detected, adapted), "probe_status": probe_status,
                  "detail": detail or ("无已验证基线" if not adapted else "")}
        if runtime == "workbuddy":
            desktop, desktop_detail = _probe_workbuddy_desktop()
            desktop_adapted, _ = WORKBUDDY_ACP_ADAPTED_DESKTOP
            desktop_status = compare_versions(desktop, desktop_adapted)
            warning = None if desktop_status == "match" else (
                f"WorkBuddy 桌面版本 {desktop or '未知'}，TALK ACP 已验证版本 {desktop_adapted}；适配关系需确认"
            )
            result.update(desktop_version=desktop, desktop_adapted_version=desktop_adapted,
                          desktop_status=desktop_status, adapter_warning=warning)
            if desktop_detail:
                result["detail"] = "；".join(filter(None, (result["detail"], desktop_detail)))
        _cache[runtime] = (time.monotonic(), result)
        return dict(result)
