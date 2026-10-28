"""Codex 0.163.0/0.164.0 原生会话接口；不读取认证文件，不自动批准工具请求。

复用已配置任务命令的模型、开发者指令、沙箱、禁用功能及网络环境。
app-server 只走本次私有 stdio；不连接桌面 daemon、不开放监听端口。
原生 rollout 只读取当前 TALK 自建会话，正文仅用于确认本轮真实送达。
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

CURRENT_VERSION = "0.164.0"
LEGACY_VERSIONS = ("0.163.0",)
SUPPORTED_VERSIONS = (CURRENT_VERSION, *LEGACY_VERSIONS)
# 兼容旧调用方按单值比较；新代码必须按集合判定，不能把 0.164 当 0.163 放行。
SUPPORTED_VERSION = CURRENT_VERSION
MAX_ROLLOUT_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024 * 1024
SESSION_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class CodexNativeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.reason_code = code


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_path(path: Path | str) -> Path:
    raw = str(path)
    if os.name == "nt":
        if raw.startswith("\\\\?\\UNC\\"):
            raw = "\\\\" + raw[8:]
        elif raw.startswith("\\\\?\\"):
            raw = raw[4:]
    return Path(raw).resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        canonical_path(path).relative_to(canonical_path(root))
        return True
    except (ValueError, OSError):
        return False


def _normalized_settings(value: Any) -> Any:
    if isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\")):
        return str(canonical_path(value)).casefold()
    if isinstance(value, dict):
        return {k:_normalized_settings(v) for k,v in value.items()}
    if isinstance(value, list):
        return [_normalized_settings(v) for v in value]
    return value


@dataclass
class LaunchSpec:
    argv: list[str]
    env: dict[str, str]
    home: Path
    model: str
    provider: str
    effort: str
    sandbox: str
    approval: str
    fingerprint: str
    version: str = CURRENT_VERSION


def resolve_launch(command: Sequence[str], workdir: Path, binding: Mapping[str, Any]) -> LaunchSpec:
    """仅接受可解析的原生命令或已配置受管薄驱动；未知参数明确拒绝。

    薄驱动是宿主原本会执行的受信本地入口。只加载其定义、调用纯 argv/env
    构造函数，不运行 main；不另找账号、不复制登录、不降模型或权限。
    """
    argv = list(map(str, command))
    env = dict(os.environ)
    sources: dict[str, str] = {}
    if len(argv) >= 2 and Path(argv[1]).suffix == ".py":
        driver = Path(argv[1]).resolve()
        if not _inside(driver, workdir) or driver.name != "native_driver.py":
            raise CodexNativeError("codex_driver_unsupported")
        sources["driver"] = hashlib.sha256(driver.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location("_talk_codex_driver_" + uuid.uuid4().hex, driver)
        if spec is None or spec.loader is None:
            raise CodexNativeError("codex_driver_unreadable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if (Path(module.ROOT).resolve() != workdir.resolve()
                or module.MODEL != binding["model_id"]
                or Path(env.get("CODEX_HOME", "")).resolve() != (Path(module.NATIVE) / ".codex").resolve()):
            raise CodexNativeError("codex_driver_identity_mismatch")
        # The exact configured task command must select this model and mode.
        if argv[2:] != ["--mode", "task", "--model", binding["model_id"]]:
            raise CodexNativeError("codex_driver_command_mismatch")
        argv = list(module.build_argv("task", binding["model_id"]))
        env = module.native_environment(env)
    home_raw = env.get("CODEX_HOME")
    if not home_raw or not Path(home_raw).is_absolute():
        raise CodexNativeError("codex_home_required")
    home = Path(home_raw).resolve()
    if not home.is_dir():
        raise CodexNativeError("codex_home_missing")
    try:
        at = argv.index("exec")
    except ValueError as exc:
        raise CodexNativeError("codex_command_unsupported") from exc
    executable = Path(shutil.which(argv[0]) or argv[0]).resolve()
    if executable.name.lower() not in {"codex.exe", "codex"} or not executable.is_file():
        raise CodexNativeError("codex_native_executable_required")
    version = subprocess.run([str(executable), "--version"], capture_output=True,
                             encoding="utf-8", timeout=15, check=True,
                             **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    cli_version = version.stdout.strip()
    if not cli_version.startswith("codex-cli "):
        raise CodexNativeError("codex_version_unsupported")
    cli_version = cli_version[len("codex-cli "):]
    # 0.164 的 app-server 对本适配器使用的 thread/start、thread/read、
    # thread/resume、turn/start 与 model/list 为增量兼容；0.163 旧角色仍可启动。
    if cli_version not in SUPPORTED_VERSIONS:
        raise CodexNativeError("codex_version_unsupported")
    prefix = argv[1:at]
    approved_prefix: list[str] = []
    approval = None
    i = 0
    while i < len(prefix):
        flag = prefix[i]
        if flag in {"-a", "--ask-for-approval"} and i + 1 < len(prefix):
            approval = prefix[i + 1]
            approved_prefix += [flag, approval]
            i += 2
        elif flag == "--strict-config":
            approved_prefix.append(flag)
            i += 1
        else:
            raise CodexNativeError("codex_global_option_unsupported")
    if approval != "never":
        raise CodexNativeError("codex_approval_unverified")
    settings: dict[str, Any] = {}
    disabled: list[str] = []
    sandbox = None
    i = at + 1
    while i < len(argv):
        flag = argv[i]
        if flag == "-" and i == len(argv) - 1:
            i += 1
        elif flag in {"--model", "-m", "--sandbox", "-s", "--color", "--disable", "-c", "--config"} and i + 1 < len(argv):
            value = argv[i + 1]
            if flag in {"--model", "-m"}:
                settings["model"] = value
            elif flag in {"--sandbox", "-s"}:
                sandbox = value
            elif flag == "--disable":
                disabled.append(value)
            elif flag in {"-c", "--config"}:
                key, sep, raw = value.partition("=")
                if not sep or key not in {"model_reasoning_effort", "developer_instructions", "base_instructions"}:
                    raise CodexNativeError("codex_config_option_unsupported")
                try:
                    settings[key] = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CodexNativeError("codex_config_option_invalid") from exc
            i += 2
        elif flag in {"--skip-git-repo-check", "--ignore-rules"}:
            # These exec-only flags do not grant model capabilities.
            i += 1
        else:
            raise CodexNativeError("codex_exec_option_unsupported")
    if settings.get("model") != binding["model_id"] or sandbox not in {"read-only", "workspace-write"}:
        raise CodexNativeError("codex_model_or_sandbox_unverified")
    effort = settings.get("model_reasoning_effort")
    if effort not in {"minimal", "low", "medium", "high", "xhigh"}:
        raise CodexNativeError("codex_effort_unverified")
    settings["sandbox_mode"] = sandbox
    settings["model_provider"] = binding["provider_id"]
    # This opt-in channel has one turn per task, but a persistent native thread.
    # Keep the legacy one-shot path's developer prompt unchanged.
    instructions = settings.get("developer_instructions")
    if isinstance(instructions, str):
        settings["developer_instructions"] = instructions.replace("本会话只有一轮", "本次任务只执行一轮", 1)
    args = [str(executable), *approved_prefix]
    for name in disabled:
        args += ["--disable", name]
    for key, value in settings.items():
        args += ["-c", key + "=" + json.dumps(value, ensure_ascii=False)]
    args += ["app-server", "--stdio"]
    config = home / "config.toml"
    sources["config"] = hashlib.sha256(config.read_bytes()).hexdigest() if config.is_file() else "absent"
    sources["adapter"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    sources["executable"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    sources["channel"] = hashlib.sha256(Path(__file__).with_name("codex_execution_channel.py").read_bytes()).hexdigest()
    stable_binding = {k: binding[k] for k in ("runtime", "runner_id", "provider_id", "model_id", "binding_fingerprint")}
    fingerprint = digest({"argv": args, "sources": sources, "home": str(home).casefold(),
                          "binding": stable_binding, "version": cli_version})
    return LaunchSpec(args, env, home, str(binding["model_id"]), str(binding["provider_id"]),
                      effort, sandbox, approval, fingerprint, cli_version)


def read_rollout(path: Path, *, home: Path, session_id: str, workdir: Path,
                 model: str, provider: str,
                 version: str | None = None) -> tuple[dict, list[tuple[int, str]]]:
    """逐行读取指定会话，保留原生来源时间；不把累计计费用量当上下文。"""
    if not SESSION_RE.fullmatch(session_id) or not _inside(path, home / "sessions"):
        raise CodexNativeError("codex_rollout_path_invalid")
    if session_id not in path.name:
        raise CodexNativeError("codex_rollout_filename_mismatch")
    stat = path.stat()
    if stat.st_size > MAX_ROLLOUT_BYTES:
        raise CodexNativeError("codex_rollout_too_large")
    data = path.read_bytes()
    if len(data) != stat.st_size or (data and not data.endswith(b"\n")):
        raise CodexNativeError("codex_rollout_incomplete")
    try:
        rows = [json.loads(line) for line in data.splitlines() if line.strip()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CodexNativeError("codex_rollout_invalid") from exc
    if any(not isinstance(r, dict) or not isinstance(r.get("payload"), dict) for r in rows):
        raise CodexNativeError("codex_rollout_invalid")
    if not rows or rows[0].get("type") != "session_meta":
        raise CodexNativeError("codex_rollout_header_missing")
    meta = rows[0].get("payload", {})
    meta_version = meta.get("cli_version")
    if (meta.get("id") != session_id or meta_version not in SUPPORTED_VERSIONS
            or (version is not None and meta_version != version)
            or Path(meta.get("cwd", "")).resolve() != workdir.resolve()
            or meta.get("model_provider") != provider):
        raise CodexNativeError("codex_rollout_identity_mismatch")
    usage = None
    source_time = None
    users: list[tuple[int, str]] = []
    canonical_users: list[tuple[int, str]] = []
    current_model = None
    settings_sha = None
    usage_index = -1
    last_user_index = -1
    for index, row in enumerate(rows):
        payload = row.get("payload", {})
        if row.get("type") == "turn_context":
            current_model = payload.get("model")
        if row.get("type") == "compacted":
            usage, source_time = None, None
        if row.get("type") != "event_msg":
            continue
        if payload.get("type") == "thread_settings_applied":
            if payload.get("thread_id") != session_id or not isinstance(payload.get("thread_settings"), dict):
                raise CodexNativeError("codex_thread_settings_invalid")
            settings_sha = digest(_normalized_settings(payload["thread_settings"]))
        if payload.get("type") == "user_message" and isinstance(payload.get("message"), str):
            users.append((index, text_digest(payload["message"])))
            last_user_index = index
        item = payload.get("item")
        if payload.get("type") == "item_completed" and isinstance(item, dict) and item.get("type") == "UserMessage":
            if payload.get("thread_id") != session_id or not isinstance(payload.get("turn_id"), str):
                raise CodexNativeError("codex_user_item_identity_mismatch")
            content = item.get("content")
            if (not isinstance(content, list) or not content
                    or any(not isinstance(c, dict) or c.get("type") != "text" or not isinstance(c.get("text"), str) for c in content)):
                raise CodexNativeError("codex_user_item_invalid")
            canonical_users.append((index, text_digest("\n".join(c["text"] for c in content))))
            last_user_index = index
        if payload.get("type") == "token_count" and payload.get("info") is not None:
            usage = payload.get("info")
            source_time = row.get("timestamp")
            usage_index = index
    if current_model is not None and current_model != model:
        raise CodexNativeError("codex_rollout_model_mismatch")
    used = capacity = None
    invalid = False
    missing = usage is None or usage_index < last_user_index
    if usage is not None:
        if not isinstance(usage, dict):
            invalid, usage = True, {}
        last = usage.get("last_token_usage")
        if last is not None and not isinstance(last, dict):
            invalid, last = True, None
        used = last.get("total_tokens") if last is not None else None
        capacity = usage.get("model_context_window")
        missing = missing or used is None or capacity is None
        for name, value in (("used", used), ("capacity", capacity)):
            if value is not None and (type(value) is not int or value < (1 if name == "capacity" else 0)
                                      or value > 9_007_199_254_740_991):
                invalid = True
        if not isinstance(source_time, str):
            invalid = True
        try:
            if not isinstance(source_time, str):
                raise ValueError()
            dt = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
            if dt.tzinfo is None or dt > datetime.now(timezone.utc):
                raise ValueError()
        except ValueError:
            invalid = True
    if invalid:
        used, capacity = None, None
        if not isinstance(source_time, str):
            source_time = None
    return ({"schema": "talk-codex-context-snapshot-1", "native_session_id": session_id,
             "session_revision": len(rows), "native_sha256": hashlib.sha256(data).hexdigest(),
             "observed_at": now_iso(), "used_tokens": used, "context_window": capacity,
             "source_time": source_time, "metrics_missing": missing, "metrics_invalid": invalid,
             "settings_sha256": settings_sha}, canonical_users or users)


class CodexNative:
    """一个任务一个 app-server 进程；原生 thread 持久化并按明确 ID 续接。"""
    def __init__(self, spec: LaunchSpec, workdir: Path):
        self.spec, self.workdir = spec, workdir
        self.home, self.fingerprint = spec.home, spec.fingerprint
        self.process = None
        self._reader = self._stderr = None
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._next_id = 0
        self._paths: dict[str, Path] = {}
        self._created: set[str] = set()
        self._active_turn = None
        self.last_thread_metadata: dict = {}

    async def open(self) -> None:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        self.process = await asyncio.create_subprocess_exec(*self.spec.argv, cwd=self.workdir,
            env=self.spec.env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=MAX_LINE_BYTES, **kwargs)
        self._reader = asyncio.create_task(self._pump())
        self._stderr = asyncio.create_task(self._drain_stderr())
        await self.rpc("initialize", {"clientInfo": {"name": "talk_execution_adapter", "title": "TALK", "version": "1.0.0"},
                                      "capabilities": {"experimentalApi": True}})
        await self._send({"method": "initialized", "params": {}})

    async def _send(self, message: dict) -> None:
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.process.stdin.drain()

    async def _drain_stderr(self) -> None:
        # Do not retain provider errors or credentials in transcript/sidecar.
        while await self.process.stderr.read(65536):
            pass

    async def _pump(self) -> None:
        try:
            while line := await self.process.stdout.readline():
                value = json.loads(line)
                if "id" in value and "method" not in value:
                    future = self._pending.pop(value["id"], None)
                    if future is not None and not future.done():
                        if "error" in value:
                            future.set_exception(CodexNativeError("codex_rpc_error"))
                        else:
                            future.set_result(value.get("result"))
                elif "id" in value:
                    # Never upgrade the existing approval/sandbox boundary.
                    await self._send({"id": value["id"], "error": {"code": -32000, "message": "TALK cannot grant additional permissions"}})
                elif value.get("method") in {"item/completed", "turn/completed", "error", "model/rerouted"}:
                    # Keep final texts/status only, no streamed reasoning or command output.
                    method = value["method"]
                    if method == "item/completed" and value.get("params", {}).get("item", {}).get("type") != "agentMessage":
                        continue
                    self._events.put_nowait(value)
        except Exception:
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CodexNativeError("codex_connection_closed"))
            self._pending.clear()
            try:
                self._events.put_nowait({"method": "connection/closed", "params": {}})
            except asyncio.QueueFull:
                pass

    async def rpc(self, method: str, params: dict, timeout: float = 30) -> dict:
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"id": request_id, "method": method, "params": params})
            result = await asyncio.wait_for(future, timeout)
            if not isinstance(result, dict):
                raise CodexNativeError("codex_rpc_result_invalid")
            return result
        finally:
            self._pending.pop(request_id, None)

    def _verify_thread(self, result: dict, session_id: str | None = None, *, attached: bool = False) -> str:
        thread = result.get("thread", {})
        self.last_thread_metadata = {k:thread.get(k) for k in ("id","path","historyMode","cliVersion","cwd","modelProvider","model","reasoningEffort")}
        sid = thread.get("id")
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid) or (session_id is not None and sid != session_id):
            raise CodexNativeError("codex_thread_id_mismatch")
        thread_version = thread.get("cliVersion")
        if (Path(thread.get("cwd", "")).resolve() != self.workdir.resolve()
                or thread.get("modelProvider") != self.spec.provider or thread.get("ephemeral") is not False
                or (thread_version is not None and thread_version not in SUPPORTED_VERSIONS)):
            raise CodexNativeError("codex_thread_identity_mismatch")
        if attached and (result.get("model") != self.spec.model or result.get("reasoningEffort") != self.spec.effort
                         or result.get("approvalPolicy") != self.spec.approval
                         or result.get("sandbox", {}).get("type") != {"read-only": "readOnly", "workspace-write": "workspaceWrite"}[self.spec.sandbox]):
            raise CodexNativeError("codex_thread_permissions_mismatch")
        if attached and result.get("sandbox", {}).get("networkAccess", False) is not False:
            raise CodexNativeError("codex_network_permissions_unverified")
        path = thread.get("path")
        if path is None and sid in self._paths and session_id == sid:
            # In 0.163.0 resume(excludeTurns=true) may omit its unstable path.
            # Only reuse the path already verified by thread/read on this same
            # connection; the disk header/hash is checked again before input.
            path = str(self._paths[sid])
        if not isinstance(path, str) or not _inside(Path(path), self.home / "sessions"):
            raise CodexNativeError("codex_rollout_path_invalid")
        self._paths[sid] = canonical_path(path)
        return sid

    async def create(self) -> str:
        result = await self.rpc("thread/start", {"model": self.spec.model, "modelProvider": self.spec.provider,
            "cwd": str(self.workdir), "approvalPolicy": self.spec.approval, "sandbox": self.spec.sandbox,
            "ephemeral": False, "allowProviderModelFallback": False})
        sid = self._verify_thread(result, attached=True)
        self._created.add(sid)
        return sid

    async def query(self, session_id: str) -> tuple[dict, list[tuple[int, str]]]:
        if not SESSION_RE.fullmatch(session_id):
            raise CodexNativeError("codex_thread_id_invalid")
        result = await self.rpc("thread/read", {"threadId": session_id, "includeTurns": False})
        self._verify_thread(result, session_id)
        return self.snapshot(session_id)

    def snapshot(self, session_id: str) -> tuple[dict, list[tuple[int, str]]]:
        if session_id not in self._paths:
            raise CodexNativeError("codex_rollout_unverified")
        if session_id in self._created and not self._paths[session_id].exists():
            # Codex allocates a durable ID/path eagerly but creates the rollout
            # lazily on first input. This is an empty cut, never a delivery ACK.
            return ({"schema": "talk-codex-context-snapshot-1", "native_session_id": session_id,
                     "session_revision": 0, "native_sha256": hashlib.sha256(b"").hexdigest(),
                     "observed_at": now_iso(), "used_tokens": None, "context_window": None,
                     "source_time": None, "metrics_missing": True}, [])
        # 旧角色可能在 0.163 创建后由 0.164 CLI 续接；rollout 头只要求是受支持
        # 的协议版本，不能把当前可执行文件版本强加给历史文件。
        return read_rollout(self._paths[session_id], home=self.home, session_id=session_id,
                            workdir=self.workdir, model=self.spec.model, provider=self.spec.provider)

    async def deliver(self, session_id: str, text: str, timeout: int, *, expected_sha256: str) -> dict:
        before = self.snapshot(session_id)[0]
        if before["native_sha256"] != expected_sha256:
            raise CodexNativeError("codex_native_history_changed")
        if session_id not in self._created:
            result = await self.rpc("thread/resume", {"threadId": session_id, "excludeTurns": True,
                "model": self.spec.model, "modelProvider": self.spec.provider, "cwd": str(self.workdir),
                "approvalPolicy": self.spec.approval, "sandbox": self.spec.sandbox})
            self._verify_thread(result, session_id, attached=True)
        after = self.snapshot(session_id)[0]
        if after["native_sha256"] != expected_sha256:
            # Native resume persists a settings receipt in this version. Permit
            # only append-only identical settings; never user/model/tool events.
            raw = self._paths[session_id].read_bytes()
            lines = raw.splitlines(keepends=True)
            cut = before["session_revision"]
            delta = [json.loads(x) for x in lines[cut:]]
            if (not before.get("settings_sha256") or after.get("settings_sha256") != before["settings_sha256"]
                    or hashlib.sha256(b"".join(lines[:cut])).hexdigest() != expected_sha256
                    or not 0 < len(delta) <= 8
                    or any(r.get("type") != "event_msg" or r.get("payload",{}).get("type") != "thread_settings_applied"
                           or r["payload"].get("thread_id") != session_id for r in delta)):
                raise CodexNativeError("codex_native_history_changed")
        # Resume itself must not introduce another user turn; caller verifies the final delta.
        result = await self.rpc("turn/start", {"threadId": session_id, "model": self.spec.model,
            "effort": self.spec.effort, "input": [{"type": "text", "text": text}]})
        turn_id = result.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            raise CodexNativeError("codex_turn_id_missing")
        self._active_turn = (session_id, turn_id)
        replies: list[str] = []
        rerouted = False
        async with asyncio.timeout(timeout):
            while True:
                event = await self._events.get()
                method, params = event.get("method"), event.get("params", {})
                if method == "connection/closed":
                    raise CodexNativeError("codex_connection_closed")
                if params.get("threadId") != session_id or params.get("turnId", turn_id) != turn_id:
                    continue
                if method == "model/rerouted":
                    rerouted = True
                elif method == "item/completed":
                    item = params.get("item", {})
                    if item.get("phase") in {None, "final_answer"} and isinstance(item.get("text"), str):
                        replies.append(item["text"])
                elif method == "turn/completed":
                    turn = params.get("turn", {})
                    if turn.get("id") != turn_id:
                        continue
                    self._active_turn = None
                    return {"status": turn.get("status"), "reply": "\n".join(replies).strip(), "rerouted": rerouted}

    async def close(self) -> None:
        if self.process is None:
            return
        if self._active_turn is not None and self.process.returncode is None:
            sid, tid = self._active_turn
            try:
                await self.rpc("turn/interrupt", {"threadId": sid, "turnId": tid}, timeout=5)
            except Exception:
                pass
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), 10)
        except asyncio.TimeoutError:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(self.process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                await asyncio.wait_for(killer.wait(), 10)
            else:
                import signal
                os.killpg(self.process.pid, signal.SIGKILL)
            await asyncio.wait_for(self.process.wait(), 10)
        for task in (self._reader, self._stderr):
            if task is not None:
                task.cancel()
        await asyncio.gather(*(t for t in (self._reader, self._stderr) if t is not None), return_exceptions=True)
