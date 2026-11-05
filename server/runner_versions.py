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


def _probe_workbuddy():
    try:
        exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/WorkBuddy/WorkBuddy.exe"
        asar = exe.parent / "resources/app.asar"
        entry = asar / "cli/bin/codebuddy"
        if not exe.is_file() or not asar.is_file():
            return None, "未找到 WorkBuddy"
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
                return None, "版本命令执行失败"
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            version = parse_version("workbuddy", output)
            return (version, "") if version else (None, "无法解析版本")
    except subprocess.TimeoutExpired:
        return None, "探测超时"
    except Exception:
        return None, "版本探测失败"


def _probe(runtime):
    if runtime == "workbuddy":
        return _probe_workbuddy()
    commands = COMMANDS.get(runtime)
    if not commands:
        return None, "无可靠 CLI 探针"
    try:
        exe = next((path for name in commands if (path := shutil.which(name))), None)
        if not exe:
            return None, "未找到命令"
        result = subprocess.run([exe, "--version"], timeout=3, stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode != 0:
            return None, "版本命令执行失败"
        output = result.stdout.decode("utf-8", errors="replace")
        version = parse_version(runtime, output)
        return (version, "") if version else (None, "无法解析版本")
    except subprocess.TimeoutExpired:
        return None, "探测超时"
    except Exception:
        return None, "版本探测失败"


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
        detected, detail = _probe(runtime)
        result = {"adapted_version": adapted, "adapted_source": source, "detected_version": detected,
                  "status": compare_versions(detected, adapted), "detail": detail or ("无已验证基线" if not adapted else "")}
        _cache[runtime] = (time.monotonic(), result)
        return dict(result)
