"""Antigravity CLI (``agy``) 原生能力探测、目录解析与无头 ``stream-json`` 执行接口。

不读取或复制任何原生认证文件；按能力探测放行新版本（``MIN_SUPPORTED=1.5.0``，
``MAX_TESTED=1.5.16``，高于 ``MAX_TESTED`` 放行并附带 ``antigravity_version_untested``
告警），不锁死单一版本号。

跨任务会话续用证明以 append-only NDJSON 写入受管 ``proof_dir``（默认位于角色私有
``home/.talk-antigravity-sessions/<conversation_id>.jsonl``），与原生认证目录隔离，
确保跨进程/跨任务新建 ``AntigravityNative`` 实例时可完整核验历史切面与防篡改哈希。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bridges.antigravity_effort import (
    cli_model_id,
    parse_agy_models_output,
    parse_model_id,
)

MIN_SUPPORTED = (1, 5, 0)
MAX_TESTED = (1, 5, 16)
CURRENT_VERSION = "1.5.16"
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_PROOF_BYTES = 16 * 1024 * 1024
MAX_SAFE_INTEGER = 9_007_199_254_740_991

_VERSION_RE = re.compile(r"(?<![\w.])(\d+)\.(\d+)\.(\d+)(?![\w.+-])")
SESSION_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_PROBE_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_PROBE_TTL = 60.0

# 仅放行已审计且全部纳入配置指纹的受管参数；拒绝可静默改写权限/工作区的
# --settings / --agent / --project 等未受控入口。
_ALLOWED_VALUE_FLAGS = frozenset(
    {
        "--model",
        "--effort",
        "--output-format",
        "--mode",
        "--print-timeout",
        "--add-dir",
        "--log-file",
    }
)
_ALLOWED_BOOL_FLAGS = frozenset(
    {
        "--disable-slash-commands",
        "--sandbox",
        "--dangerously-skip-permissions",
    }
)
_ALLOWED_MODES = frozenset({"auto", "accept-edits", "plan"})


class AntigravityNativeError(RuntimeError):
    """稳定的 Antigravity 原生适配错误，仅向调用方暴露固定原因码。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.reason_code = code


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_path(path: Path | str) -> str:
    resolved = str(Path(path).resolve())
    return resolved.casefold() if os.name == "nt" else resolved


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return not path.is_symlink()
    except (ValueError, OSError):
        return False


def parse_antigravity_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.search(text) if isinstance(text, str) else None
    if not match:
        raise AntigravityNativeError("antigravity_version_unparseable")
    return tuple(map(int, match.groups()))


def supported_version(value: str) -> bool:
    try:
        return parse_antigravity_version(value) >= MIN_SUPPORTED
    except AntigravityNativeError:
        return False


def detect_capabilities(help_text: str) -> dict[str, bool]:
    """从 ``agy --help`` 文本探测所需命令行能力，按选项声明行匹配而非正文误伤。"""
    def has_option(flag: str) -> bool:
        return bool(
            re.search(
                r"(?m)^\s*(?:-\w,?\s+)?" + re.escape(flag) + r"(?=[\s,=\[]|$)",
                help_text,
            )
        )

    capabilities = {
        flag: has_option(flag)
        for flag in (
            "--print",
            "--model",
            "--effort",
            "--output-format",
            "--conversation",
            "--mode",
            "--disable-slash-commands",
            "--print-timeout",
        )
    }
    capabilities["models"] = bool(re.search(r"(?m)^\s*models(?:\s|$)", help_text))
    return capabilities


def clear_antigravity_probe_cache() -> None:
    _PROBE_CACHE.clear()


def find_antigravity_executable(env: Mapping[str, str] | None = None) -> str | None:
    """定位本机 ``agy`` 可执行文件：优先环境变量 PATH，再查 Windows 官方默认目录。"""
    source_env = os.environ if env is None else env
    search_path = source_env.get("PATH") if env is not None else None
    for name in ("agy.exe", "agy"):
        found = shutil.which(name, path=search_path) if env is not None else shutil.which(name)
        if found:
            return found
    local_app_data = source_env.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if candidate.is_file():
            return str(candidate)
    user_profile = source_env.get("USERPROFILE")
    if user_profile:
        candidate = Path(user_profile) / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def check_antigravity(
    executable: str,
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """探测 ``agy`` 版本与必需 CLI 能力，带 60 秒可失效缓存。"""
    cache_key = None
    path = Path(executable)
    try:
        if use_cache and path.is_absolute() and path.is_file():
            stat = path.stat()
            environment = dict(os.environ if env is None else env)
            env_hash = hashlib.sha256(
                json.dumps(sorted(environment.items()), ensure_ascii=True).encode("utf-8")
            ).digest()
            cache_key = (
                str(path.resolve()),
                stat.st_mtime_ns,
                stat.st_size,
                str(Path(cwd or os.getcwd()).resolve()),
                env_hash,
                subprocess.run,
            )
            cached = _PROBE_CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < _PROBE_TTL:
                return {**cached[1], "capabilities": cached[1]["capabilities"].copy()}
    except OSError:
        pass

    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": dict(env) if env is not None else None,
        "stdin": subprocess.DEVNULL,
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 15,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        ver_proc = subprocess.run([str(executable), "--version"], check=True, **kwargs)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AntigravityNativeError("antigravity_probe_failed", type(exc).__name__) from exc

    version_text = "\n".join(filter(None, (ver_proc.stdout, ver_proc.stderr)))
    version_tuple = parse_antigravity_version(version_text)
    version = ".".join(map(str, version_tuple))
    if version_tuple < MIN_SUPPORTED:
        raise AntigravityNativeError(
            "antigravity_version_unsupported",
            f"Detected {version}; minimum required is {'.'.join(map(str, MIN_SUPPORTED))}",
        )

    # agy --help writes usage to stderr and may return non-zero on Go flag builds.
    try:
        help_proc = subprocess.run([str(executable), "--help"], check=False, **kwargs)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AntigravityNativeError("antigravity_probe_failed", type(exc).__name__) from exc

    help_text = "\n".join(filter(None, (help_proc.stdout, help_proc.stderr)))
    if not help_text.strip():
        raise AntigravityNativeError("antigravity_probe_failed", "empty help output")

    capabilities = detect_capabilities(help_text)
    for flag, available in capabilities.items():
        if not available:
            raise AntigravityNativeError(
                f"antigravity_capability_missing:{flag}",
                f"Antigravity {version} is missing capability {flag}",
            )

    result = {
        "version": version,
        "capabilities": capabilities,
        "allowed": True,
        "warning": "antigravity_version_untested" if version_tuple > MAX_TESTED else None,
    }
    if cache_key is not None:
        if len(_PROBE_CACHE) >= 128:
            _PROBE_CACHE.clear()
        _PROBE_CACHE[cache_key] = (
            time.monotonic(),
            {**result, "capabilities": capabilities.copy()},
        )
    return result


def discover_antigravity_models(
    executable: str,
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """只读执行 ``agy models`` 并返回过滤后的 3 个目标模型及其实测强度列表。"""
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": dict(env) if env is not None else None,
        "stdin": subprocess.DEVNULL,
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run([str(executable), "models"], check=False, **kwargs)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AntigravityNativeError("antigravity_models_probe_failed", type(exc).__name__) from exc
    if proc.returncode != 0:
        raise AntigravityNativeError("antigravity_models_probe_failed", f"exit {proc.returncode}")
    return parse_agy_models_output(proc.stdout or "")


def _nonneg_int(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= MAX_SAFE_INTEGER else None


def _pos_int(value: Any) -> int | None:
    return value if type(value) is int and 0 < value <= MAX_SAFE_INTEGER else None


def parse_stream_json_events(output: str) -> dict[str, Any]:
    """解析 ``agy --output-format stream-json`` 输出的 NDJSON 事件流。

    严格核验所有事件中的 ``conversation_id`` 一致性；任何指标字段损坏时
    ``metrics_invalid=True`` 并同步清空 ``used_tokens`` / ``context_window``。
    """
    parsed_any = False
    event_count = 0
    seen_cids: set[str] = set()
    seen_models: set[str] = set()
    init_model: str | None = None
    init_cwd: str | None = None
    permission_mode: str | None = None
    result_status: str | None = None
    result_response: str | None = None
    result_usage: dict[str, Any] | None = None
    last_step_total_tokens: int | None = None
    num_turns: int | None = None
    context_window: int | None = None
    delta_parts: list[str] = []
    metrics_invalid = False

    def _record_cid(raw_cid: Any) -> None:
        if raw_cid is None:
            return
        if not isinstance(raw_cid, str) or not raw_cid.strip():
            raise AntigravityNativeError("antigravity_session_id_invalid")
        cid = raw_cid.strip()
        if not SESSION_RE.fullmatch(cid):
            raise AntigravityNativeError("antigravity_session_id_invalid")
        seen_cids.add(cid)

    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event = payload.get("event")
        if not isinstance(event, str):
            continue
        parsed_any = True
        event_count += 1

        if "conversation_id" in payload:
            _record_cid(payload.get("conversation_id"))

        if event == "init":
            init_body = payload.get("init")
            if isinstance(init_body, dict):
                if "conversation_id" in init_body:
                    _record_cid(init_body.get("conversation_id"))
                if isinstance(init_body.get("model"), str) and init_body["model"].strip():
                    init_model = init_body["model"].strip()
                    seen_models.add(init_model.lower())
                if isinstance(init_body.get("cwd"), str):
                    init_cwd = init_body["cwd"]
                if isinstance(init_body.get("permission_mode"), str):
                    permission_mode = init_body["permission_mode"]
                for cap_key in ("context_window", "max_context_tokens", "context_length"):
                    if cap_key in init_body:
                        cap = _pos_int(init_body[cap_key])
                        if cap is None:
                            metrics_invalid = True
                        else:
                            context_window = cap
        elif event == "step_update":
            step = payload.get("step_update")
            if isinstance(step, dict):
                if "conversation_id" in step:
                    _record_cid(step.get("conversation_id"))
                if step.get("step_type") == "agent_response":
                    delta = step.get("text_delta")
                    if isinstance(delta, str):
                        delta_parts.append(delta)
                    if step.get("state") == "DONE" and "usage" in step:
                        usage = step.get("usage")
                        if isinstance(usage, dict):
                            if "total_tokens" in usage:
                                parsed_total = _nonneg_int(usage.get("total_tokens"))
                                if parsed_total is None:
                                    metrics_invalid = True
                                else:
                                    last_step_total_tokens = parsed_total
                        else:
                            metrics_invalid = True
        elif event == "result":
            res = payload.get("result")
            if isinstance(res, dict):
                if "conversation_id" in res:
                    _record_cid(res.get("conversation_id"))
                if isinstance(res.get("status"), str):
                    result_status = res["status"].strip()
                if isinstance(res.get("response"), str):
                    result_response = res["response"]
                if type(res.get("num_turns")) is int:
                    num_turns = res["num_turns"]
                if "usage" in res:
                    usage = res.get("usage")
                    if isinstance(usage, dict):
                        if "total_tokens" in usage and _nonneg_int(usage.get("total_tokens")) is None:
                            metrics_invalid = True
                        else:
                            result_usage = usage
                    else:
                        metrics_invalid = True
                for cap_key in ("context_window", "max_context_tokens", "context_length"):
                    if cap_key in res:
                        cap = _pos_int(res[cap_key])
                        if cap is None:
                            metrics_invalid = True
                        else:
                            context_window = cap

    if len(seen_cids) > 1:
        raise AntigravityNativeError("antigravity_session_id_mismatch")
    if len(seen_models) > 1:
        raise AntigravityNativeError("antigravity_native_model_mismatch")

    conversation_id = next(iter(seen_cids)) if seen_cids else None

    if metrics_invalid:
        used_tokens: int | None = None
        context_window = None
    else:
        used_tokens = None
        if last_step_total_tokens is not None:
            used_tokens = last_step_total_tokens
        elif result_usage is not None and (num_turns is None or num_turns == 1):
            used_tokens = _nonneg_int(result_usage.get("total_tokens"))

    response_text = result_response if result_response is not None else (
        "".join(delta_parts) if delta_parts else ""
    )
    return {
        "parsed": parsed_any,
        "event_count": event_count,
        "conversation_id": conversation_id,
        "model": init_model,
        "cwd": init_cwd,
        "permission_mode": permission_mode,
        "status": result_status,
        "response": response_text,
        "num_turns": num_turns,
        "used_tokens": used_tokens,
        "context_window": context_window,
        "metrics_invalid": metrics_invalid,
        "events_sha256": text_digest(output or ""),
    }


def extract_antigravity_final_reply(output: str) -> str | None:
    """从 Antigravity ``stream-json`` stdout 提取最终文本；非 stream-json 或失败空体返回 ``None``。"""
    try:
        parsed = parse_stream_json_events(output)
    except AntigravityNativeError:
        return None
    if not parsed["parsed"]:
        return None
    reply = str(parsed["response"] or "").strip()
    status = parsed["status"]
    if not reply and status is not None and status.upper() != "SUCCESS":
        return None
    return reply


@dataclass
class LaunchSpec:
    argv: list[str]
    env: dict[str, str]
    home: Path
    base_model: str
    cli_model: str
    effort: str
    provider: str
    version: str
    mode: str | None
    fingerprint: str
    capacity: int | None = None


def resolve_launch(
    command: Sequence[str],
    workdir: Path,
    binding: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    check_cli: bool = True,
) -> LaunchSpec:
    """校验受管 ``agy`` 命令、模型绑定与 CLI 能力，返回不可变 :class:`LaunchSpec`。"""
    argv = list(map(str, command))
    if not argv:
        raise AntigravityNativeError("antigravity_command_unsupported")

    run_env = dict(os.environ if env is None else env)
    raw_exe = argv[0]
    if raw_exe.lower() in {"agy", "agy.exe"}:
        found = find_antigravity_executable(run_env)
        if not found:
            raise AntigravityNativeError("antigravity_native_executable_required")
        executable = Path(found).resolve()
    else:
        resolved_exe = shutil.which(raw_exe, path=run_env.get("PATH")) or raw_exe
        executable = Path(resolved_exe).resolve()
    if executable.name.lower() not in {"agy", "agy.exe"} or not executable.is_file():
        raise AntigravityNativeError("antigravity_native_executable_required")

    flags: dict[str, Any] = {}
    bool_flags: set[str] = set()
    add_dirs: list[str] = []
    i = 1
    saw_print_tail = False
    while i < len(argv):
        token = argv[i]
        if token in {"-p", "--print"} and i == len(argv) - 1:
            saw_print_tail = True
            i += 1
            continue
        if token in _ALLOWED_BOOL_FLAGS:
            bool_flags.add(token)
            i += 1
            continue
        if "=" in token and token.startswith("--"):
            flag, value = token.split("=", 1)
            if flag in _ALLOWED_VALUE_FLAGS:
                if flag == "--add-dir":
                    add_dirs.append(value)
                elif flag in flags:
                    raise AntigravityNativeError("antigravity_command_unsupported")
                else:
                    flags[flag] = value
                i += 1
                continue
            raise AntigravityNativeError("antigravity_command_unsupported")
        if token in _ALLOWED_VALUE_FLAGS and i + 1 < len(argv):
            value = argv[i + 1]
            if token == "--add-dir":
                add_dirs.append(value)
            elif token in flags:
                raise AntigravityNativeError("antigravity_command_unsupported")
            else:
                flags[token] = value
            i += 2
            continue
        raise AntigravityNativeError("antigravity_command_unsupported")

    if not saw_print_tail or flags.get("--output-format") != "stream-json" or "--model" not in flags:
        raise AntigravityNativeError("antigravity_command_unsupported")
    if "--sandbox" in bool_flags and "--dangerously-skip-permissions" in bool_flags:
        raise AntigravityNativeError("antigravity_command_unsupported")
    mode = flags.get("--mode")
    if mode is not None and mode not in _ALLOWED_MODES:
        raise AntigravityNativeError("antigravity_command_unsupported")

    parsed_cmd_model = parse_model_id(flags["--model"])
    if parsed_cmd_model is None:
        raise AntigravityNativeError("antigravity_model_unsupported")
    cmd_base, cmd_effort = parsed_cmd_model

    flag_effort = flags.get("--effort")
    if flag_effort is not None:
        if cmd_effort is not None and flag_effort.strip().lower() != cmd_effort:
            raise AntigravityNativeError("antigravity_effort_mismatch")
        effective_effort = flag_effort.strip().lower()
    else:
        effective_effort = cmd_effort

    try:
        expected_cli_model = cli_model_id(cmd_base, effective_effort)
    except ValueError as exc:
        raise AntigravityNativeError("antigravity_effort_unsupported") from exc
    if flags["--model"].strip().lower() != expected_cli_model:
        raise AntigravityNativeError("antigravity_model_binding_mismatch")
    resolved_effort = parse_model_id(expected_cli_model)[1]  # type: ignore[index]

    binding_model_raw = binding.get("model_id") or binding.get("model_alias")
    parsed_binding = parse_model_id(binding_model_raw)
    if parsed_binding is None or parsed_binding[0] != cmd_base:
        raise AntigravityNativeError("antigravity_model_binding_mismatch")
    if parsed_binding[1] is not None and parsed_binding[1] != resolved_effort:
        raise AntigravityNativeError("antigravity_model_binding_mismatch")

    provider = str(binding.get("provider_id") or "").strip()
    if not provider:
        raise AntigravityNativeError("antigravity_binding_unusable")

    probe_version = CURRENT_VERSION
    if check_cli:
        probe = check_antigravity(str(executable), cwd=workdir, env=run_env)
        probe_version = str(probe["version"])

    home_raw = (
        run_env.get("ANTIGRAVITY_HOME")
        or run_env.get("USERPROFILE")
        or run_env.get("HOME")
        or str(Path.home())
    )
    home = Path(home_raw).resolve()
    normalized_argv = [str(executable), *argv[1:]]
    fingerprint = digest(
        {
            "version": probe_version,
            "executable": str(executable),
            "base_model": cmd_base,
            "cli_model": expected_cli_model,
            "effort": resolved_effort,
            "mode": mode,
            "print_timeout": flags.get("--print-timeout"),
            "log_file": flags.get("--log-file"),
            "bool_flags": sorted(bool_flags),
            "add_dirs": add_dirs,
            "home": str(home),
        }
    )
    return LaunchSpec(
        argv=normalized_argv,
        env=run_env,
        home=home,
        base_model=cmd_base,
        cli_model=expected_cli_model,
        effort=str(resolved_effort),
        provider=provider,
        version=probe_version,
        mode=mode,
        fingerprint=fingerprint,
        capacity=None,
    )


class AntigravityNative:
    """受控 ``agy --output-format stream-json`` 无头执行器，支持磁盘证明续用与进程树清理。"""

    def __init__(self, spec: LaunchSpec, workdir: Path, *, proof_dir: Path | None = None) -> None:
        self.spec = spec
        self.home = spec.home
        self.fingerprint = spec.fingerprint
        self.workdir = workdir.resolve()
        self.proof_dir = (
            Path(proof_dir).resolve()
            if proof_dir is not None
            else (self.home / ".talk-antigravity-sessions").resolve()
        )
        self.process: asyncio.subprocess.Process | None = None
        self.last_session_id: str | None = None
        self._streams: list[asyncio.Task[None]] = []
        self._buffers: list[bytearray] = [bytearray(), bytearray()]

    def _proof_path(self, sid: str) -> Path:
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid):
            raise AntigravityNativeError("antigravity_session_id_invalid")
        target = self.proof_dir / f"{sid}.jsonl"
        if not _inside(target, self.proof_dir):
            raise AntigravityNativeError("antigravity_session_path_invalid")
        return target

    async def open(self) -> None:
        pass

    def snapshot(self, sid: str) -> tuple[dict[str, Any], list[tuple[int, str]]]:
        """从磁盘 append-only 证明文件读取并核验本会话全部已确认轮次。"""
        proof_file = self._proof_path(sid)
        if not proof_file.is_file():
            raise AntigravityNativeError("antigravity_session_unobserved")
        try:
            raw = proof_file.read_bytes()
        except OSError as exc:
            raise AntigravityNativeError("antigravity_session_unreadable") from exc
        if not raw or len(raw) > MAX_PROOF_BYTES or not raw.endswith(b"\n"):
            raise AntigravityNativeError("antigravity_proof_cut_invalid")
        try:
            rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AntigravityNativeError("antigravity_proof_corrupted") from exc
        if not rows:
            raise AntigravityNativeError("antigravity_proof_corrupted")

        users: list[tuple[int, str]] = []
        expected_workdir = _canonical_path(self.workdir)
        prev_revision = 0
        for row in rows:
            if not isinstance(row, dict):
                raise AntigravityNativeError("antigravity_proof_corrupted")
            if (
                row.get("native_session_id") != sid
                or row.get("fingerprint") != self.fingerprint
                or row.get("cli_model") != self.spec.cli_model
                or row.get("workdir") != expected_workdir
            ):
                raise AntigravityNativeError("antigravity_proof_identity_mismatch")
            row_index = _nonneg_int(row.get("index"))
            row_rev = _pos_int(row.get("session_revision"))
            body_sha = row.get("body_sha256")
            if (
                row_index is None
                or row_rev is None
                or row_index != prev_revision
                or row_rev <= prev_revision
                or not isinstance(body_sha, str)
                or len(body_sha) != 64
            ):
                raise AntigravityNativeError("antigravity_proof_corrupted")
            users.append((row_index, body_sha))
            prev_revision = row_rev

        last = rows[-1]
        metrics_invalid = bool(last.get("metrics_invalid"))
        used_tokens = None if metrics_invalid else _nonneg_int(last.get("used_tokens"))
        context_window = None if metrics_invalid else _pos_int(last.get("context_window"))
        if last.get("used_tokens") is not None and used_tokens is None:
            metrics_invalid = True
        if last.get("context_window") is not None and context_window is None:
            metrics_invalid = True
        if metrics_invalid:
            used_tokens = None
            context_window = None

        return (
            {
                "schema": "talk-antigravity-context-snapshot-1",
                "native_session_id": sid,
                "session_revision": prev_revision,
                "native_sha256": hashlib.sha256(raw).hexdigest(),
                "observed_at": str(last.get("observed_at") or now_iso()),
                "source_time": str(last.get("source_time") or last.get("observed_at") or now_iso()),
                "used_tokens": used_tokens,
                "context_window": context_window,
                "metrics_missing": used_tokens is None or context_window is None,
                "metrics_invalid": metrics_invalid,
                "terminal_reason": last.get("terminal_reason"),
            },
            users,
        )

    async def query(self, sid: str) -> tuple[dict[str, Any], list[tuple[int, str]]]:
        return self.snapshot(sid)

    def _append_proof(
        self,
        *,
        sid: str,
        prev_revision: int,
        text: str,
        parsed: dict[str, Any],
    ) -> None:
        target = self._proof_path(sid)
        self.proof_dir.mkdir(parents=True, exist_ok=True)
        if not _inside(target, self.proof_dir):
            raise AntigravityNativeError("antigravity_session_path_invalid")
        observed = now_iso()
        metrics_invalid = bool(parsed["metrics_invalid"])
        context_window = None if metrics_invalid else (parsed["context_window"] or self.spec.capacity)
        used_tokens = None if metrics_invalid else parsed["used_tokens"]
        row = {
            "schema": "talk-antigravity-turn-proof-1",
            "native_session_id": sid,
            "fingerprint": self.fingerprint,
            "cli_model": self.spec.cli_model,
            "workdir": _canonical_path(self.workdir),
            "index": prev_revision,
            "session_revision": prev_revision + max(1, int(parsed["event_count"])),
            "body_sha256": text_digest(text),
            "events_sha256": parsed["events_sha256"],
            "observed_at": observed,
            "source_time": observed,
            "used_tokens": used_tokens,
            "context_window": context_window,
            "metrics_missing": used_tokens is None or context_window is None,
            "metrics_invalid": metrics_invalid,
            "terminal_reason": parsed["status"],
        }
        payload = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        with target.open("ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    async def deliver(
        self,
        sid: str | None,
        text: str,
        timeout: int,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        prev_revision = 0
        if sid is not None:
            prev_snap, _ = self.snapshot(sid)
            if expected_sha256 is not None and prev_snap["native_sha256"] != expected_sha256:
                raise AntigravityNativeError("antigravity_native_history_changed")
            prev_revision = int(prev_snap["session_revision"])

        # spec.argv 以 -p / --print 结尾；续窗时在 -p 前插入 --conversation <sid>。
        argv = list(self.spec.argv[:-1])
        if sid is not None:
            argv.extend(("--conversation", sid))
        argv.extend((self.spec.argv[-1], text))

        if os.name == "nt" and len(subprocess.list2cmdline(argv)) >= 32760:
            raise AntigravityNativeError("antigravity_windows_command_line_limit")

        self.last_session_id = sid
        self._buffers = [bytearray(), bytearray()]
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=self.workdir,
            env=self.spec.env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **(
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            ),
        )

        async def _read(stream: asyncio.StreamReader | None, buf_index: int) -> None:
            if stream is None:
                return
            while chunk := await stream.read(65536):
                self._buffers[buf_index].extend(chunk)
                if len(self._buffers[buf_index]) > MAX_OUTPUT_BYTES:
                    raise AntigravityNativeError("antigravity_output_limit")

        self._streams = [
            asyncio.create_task(_read(self.process.stdout, 0)),
            asyncio.create_task(_read(self.process.stderr, 1)),
        ]
        returncode: int | None = None
        interrupted: BaseException | None = None
        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(*self._streams)
                returncode = await self.process.wait()
        except BaseException as exc:
            interrupted = exc
        finally:
            await asyncio.shield(self.close())

        text_output = bytes(self._buffers[0]).decode("utf-8", errors="replace")
        parsed: dict[str, Any] | None = None
        if text_output.strip():
            try:
                parsed = parse_stream_json_events(text_output)
                if parsed["conversation_id"] is not None:
                    if sid is None:
                        self.last_session_id = parsed["conversation_id"]
                    elif parsed["conversation_id"] == sid:
                        self.last_session_id = sid
            except AntigravityNativeError:
                if interrupted is None:
                    raise

        if interrupted is not None:
            # 若中断前已经收到合法 init（含 conversation_id 且模型/目录匹配），
            # 落盘本轮证明以便外层准确识别“送达后中断”并 taint 窗口。
            if (
                parsed is not None
                and parsed["parsed"]
                and parsed["conversation_id"] is not None
                and (sid is None or parsed["conversation_id"] == sid)
                and (parsed["model"] is None or parsed["model"].strip().lower() == self.spec.cli_model)
                and (parsed["cwd"] is None or _canonical_path(parsed["cwd"]) == _canonical_path(self.workdir))
            ):
                self._append_proof(
                    sid=parsed["conversation_id"],
                    prev_revision=prev_revision,
                    text=text,
                    parsed=parsed,
                )
            raise interrupted

        if parsed is None or not parsed["parsed"]:
            raise AntigravityNativeError("antigravity_stream_json_missing")

        returned_sid = parsed["conversation_id"]
        if returned_sid is None:
            raise AntigravityNativeError("antigravity_new_session_unconfirmed")
        if sid is not None and returned_sid != sid:
            raise AntigravityNativeError("antigravity_resume_session_mismatch")
        if parsed["model"] is not None and parsed["model"].strip().lower() != self.spec.cli_model:
            raise AntigravityNativeError("antigravity_native_model_mismatch")
        if parsed["cwd"] is not None and _canonical_path(parsed["cwd"]) != _canonical_path(self.workdir):
            raise AntigravityNativeError("antigravity_workspace_mismatch")
        if sid is None and self._proof_path(returned_sid).exists():
            raise AntigravityNativeError("antigravity_native_id_collision")

        self.last_session_id = returned_sid
        self._append_proof(
            sid=returned_sid,
            prev_revision=prev_revision,
            text=text,
            parsed=parsed,
        )

        ok = returncode == 0 and str(parsed["status"] or "").upper() == "SUCCESS"
        return {
            "status": "completed" if ok else "failed",
            "reply": str(parsed["response"] or "").strip(),
            "rerouted": False,
        }

    async def close(self) -> None:
        try:
            if self.process is not None and self.process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/PID",
                        str(self.process.pid),
                        "/T",
                        "/F",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    await asyncio.wait_for(killer.wait(), 10)
                else:
                    import signal
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                await asyncio.wait_for(self.process.wait(), 10)
                if self.process.returncode is None:
                    raise AntigravityNativeError("native_termination_unverified")
        finally:
            for task in self._streams:
                if not task.done():
                    task.cancel()
            if self._streams:
                await asyncio.gather(*self._streams, return_exceptions=True)
            self._streams = []
