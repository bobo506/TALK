#!/usr/bin/env python3
"""DSH 原生 ACP 薄驱动（#74：主控验证入口，不是正式页面功能）。

它只做三件事，且**只做这三件事**：

1. **ACP 传输**：以 ACP v1（`@agentclientprotocol/sdk` 的 newline-delimited JSON-RPC）
   在 stdio 上与原生 `dsh --profile acp` 会话通信；
2. **会话控制**：`initialize` / `session/new` / `session/list` / `session/resume` /
   `session/close` / `session/prompt`，以及服务端反向请求（`session/request_permission`）
   的最小应答；
3. **输出取证**：把每一步的方法名、成功/失败、`session/update` 通知与真实 `sessionId`
   记录成一条 UTF-8 JSON，供主控与复核核对。

明确不做的事：

- 不实现、也不替代模型推理循环：`prompt` 每次只发送**一条**提示，等待该轮结算后停止；
  不回答工具调用、不追加后续轮次、不解析模型意图；
- 不由本脚本代替模型调用 TALK 任务工具：TALK 工具是通过 `session/new` 的 `mcpServers`
  挂进被测会话、由**会话内的模型**调用的；本脚本只负责把声明原样传给 ACP 服务端；
- 不新建 TALK 协议、不改数据库、不改授权模型、不改 bridge 工具合同；
- 不持有密钥：脚本自身不读取 TALK 密钥。密钥要么由被测会话的 MCP 启动器
  （`scripts/dsh_talk_mcp_launch.py`）在**它自己的进程内**从仓库外密钥文件解析，
  要么由操作者经授权在外部环境显式提供。本脚本打印/落盘的一切内容都经过凭据字段遮蔽。

`resume` 语义：只调用 `session/resume`，绝不退化成 `session/new`，也不伪造同 ID；
服务端拒绝（工作区不符、会话不可恢复、未知 ID、会话已在活动中）时脚本按失败退出，
并把该次拒绝作为证据记录，不写成功结论。

下游参数（`--server-arg` / `--mcp-server-arg`）的合同（#75 缺陷 D1）：Python 的
`-X utf8`、DSH 的 `--profile` 这类值天然以 `-` 开头。**等号写法总是可用**
（`--server-arg=-X`）；分离写法 `--server-arg -X` 也可用，但值不得与本驱动已注册的
选项同名（例如 `--cwd`），否则按用法错误退出，绝不把驱动自己的选项静默传给下游。

零模型命令（`handshake` / `lifecycle`）不发起任何模型请求；`prompt` 需要显式
`--allow-model` 才会执行，且受 `--prompt-timeout` 约束。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SESSION_TEMPLATE = REPO_ROOT / "deploy" / "dsh" / "acp-session.template.json"

#: ACP v1：对应 `@agentclientprotocol/sdk` 的 `PROTOCOL_VERSION`。
ACP_PROTOCOL_VERSION = 1
DEFAULT_TIMEOUT = 120.0
DEFAULT_PROMPT_TIMEOUT = 600.0
#: ACP 服务进程的 stderr 默认落在系统临时目录，避免污染仓库或会话工作区。
DEFAULT_STDERR_LOG = Path(tempfile.gettempdir()) / "talk-dsh-acp-server.stderr.log"

#: 与 DSH 子进程 seam 同源的凭据字段判别式：这些名字的值一律不打印、不落盘。
CREDENTIAL_NAME = re.compile(r"KEY|PASSWORD|SECRET|TOKEN", re.I)
REDACTED = "<已隐藏>"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class AcpDriveError(RuntimeError):
    """可预期的中文错误；`stage` 指明失败阶段，便于区分传输/协议/断言失败。"""

    def __init__(self, message: str, *, stage: str = "unknown") -> None:
        super().__init__(message)
        self.stage = stage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_caller_path(path: Path) -> Path:
    """按调用者当前目录解析成绝对路径。

    DSH 把 `--patch` / `DSH_HOME` 拼在**它自己的 cwd** 上，所以这两个值必须在
    传下游之前定死（#71 定位、#72 修复的同类缺陷），否则会读错位置。
    """
    return Path(path).expanduser().resolve()


def is_credential_name(name: str) -> bool:
    return bool(CREDENTIAL_NAME.search(name or ""))


def describe_env(env: dict) -> dict:
    """把环境变量描述成“名字 → 值或已隐藏”，凭据字段永不出值。"""
    described = {}
    for key, value in (env or {}).items():
        described[str(key)] = REDACTED if is_credential_name(str(key)) else str(value)
    return described


def collect_secrets(env: dict) -> list[str]:
    secrets = []
    for key, value in (env or {}).items():
        text = str(value or "")
        if text and is_credential_name(str(key)):
            secrets.append(text)
    return secrets


def sanitize(text: str, secrets: list[str]) -> str:
    result = text or ""
    for secret in secrets:
        if secret:
            result = result.replace(secret, REDACTED)
    return result


def tail(text: str, limit: int = 1200) -> str:
    text = text or ""
    return text[-limit:]


# --------------------------------------------------------------------------------------
# ACP stdio 客户端
# --------------------------------------------------------------------------------------


class AcpClient:
    """ACP v1 stdio 客户端：传输、请求/通知分派、权限应答与取证。

    这不是通用 ACP 库，只实现本片需要的传输与生命周期控制；任何协议错误都会以
    :class:`AcpDriveError` 抛出，绝不返回“看起来成功”的占位结果。
    """

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: dict,
        stderr_path: Path,
        timeout: float = DEFAULT_TIMEOUT,
        permission: str = "reject",
        extra_secrets: list[str] | None = None,
    ) -> None:
        self.argv = [str(item) for item in argv]
        self.cwd = Path(cwd)
        self.env = dict(env)
        self.stderr_path = Path(stderr_path)
        self.timeout = float(timeout)
        self.permission = permission
        # 会话规格里的凭据正文同样要遮蔽：它出现在 session/new 的 mcpServers 参数里。
        self._secrets = collect_secrets(self.env) + [
            str(item) for item in (extra_secrets or []) if item
        ]

        self._proc: subprocess.Popen | None = None
        self._stdin = None
        self._stderr_handle = None
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, dict] = {}
        self._next_id = 0
        self._exit_code: int | None = None
        self._closed_reason: str | None = None

        self.requests: list[dict] = []
        self.notifications: list[dict] = []
        self.updates: list[dict] = []
        self.permission_events: list[dict] = []
        self.unsupported_requests: list[dict] = []

    # -- 进程与传输 ---------------------------------------------------------------

    def start(self) -> None:
        self.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = self.stderr_path.open("w", encoding="utf-8")
        try:
            self._proc = subprocess.Popen(
                self.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(self.cwd),
                env=self.env,
            )
        except OSError as exc:
            self._close_stderr()
            raise AcpDriveError(
                f"无法启动 ACP 服务进程（{self.argv[0] if self.argv else '<空命令>'}）：{exc}",
                stage="spawn",
            ) from exc
        self._stdin = self._proc.stdin
        self._reader = threading.Thread(target=self._read_loop, name="acp-reader", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        stream = self._proc.stdout if self._proc is not None else None
        try:
            if stream is not None:
                for raw in stream:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        # 非协议输出（例如误写到 stdout 的日志）如实记录，但不当成消息。
                        self.notifications.append({"method": "<unparsed>", "text": line[:400]})
                        continue
                    if isinstance(payload, dict):
                        try:
                            self._dispatch(payload)
                        except AcpDriveError as exc:  # 应答失败不应带走读线程
                            self.notifications.append(
                                {"method": "<dispatch-error>", "text": str(exc), "at": _now()}
                            )
        except (OSError, ValueError):  # pragma: no cover - 进程被外部杀死时
            pass
        finally:
            self._on_eof()

    def _on_eof(self) -> None:
        with self._lock:
            if self._closed_reason is None:
                self._closed_reason = "ACP 服务进程已关闭标准输出（进程退出或崩溃）"
            pending = list(self._pending.values())
            self._pending.clear()
        for entry in pending:
            entry["error"] = self._closed_reason
            entry["event"].set()

    def _dispatch(self, payload: dict) -> None:
        method = payload.get("method")
        if isinstance(method, str) and "id" in payload:
            self._handle_server_request(payload)
            return
        if isinstance(method, str):
            self._handle_notification(payload)
            return
        if "id" in payload:
            with self._lock:
                entry = self._pending.pop(payload["id"], None)
            if entry is None:
                return
            entry["payload"] = payload
            entry["event"].set()

    def _handle_notification(self, payload: dict) -> None:
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        record = {
            "method": payload.get("method"),
            "sessionId": params.get("sessionId"),
            "at": _now(),
        }
        if payload.get("method") == "session/update":
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            record["sessionUpdate"] = update.get("sessionUpdate")
            self.updates.append(
                {
                    "sessionId": params.get("sessionId"),
                    "sessionUpdate": update.get("sessionUpdate"),
                    "update": update,
                    "at": record["at"],
                }
            )
        self.notifications.append(record)

    def _handle_server_request(self, payload: dict) -> None:
        """应答服务端反向请求；不支持的请求回 -32601，而不是静默丢弃。"""
        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        if method == "session/request_permission":
            options = params.get("options") if isinstance(params.get("options"), list) else []
            wanted_kinds = ("allow_once",) if self.permission == "allow" else ("reject_once",)
            chosen = None
            for option in options:
                if isinstance(option, dict) and option.get("kind") in wanted_kinds:
                    chosen = option.get("optionId")
                    break
            if chosen is None:
                outcome = {"outcome": "cancelled"}
            else:
                outcome = {"outcome": "selected", "optionId": chosen}
            tool_call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
            self.permission_events.append(
                {
                    "sessionId": params.get("sessionId"),
                    "toolCallId": tool_call.get("toolCallId"),
                    "policy": self.permission,
                    "optionId": chosen,
                    "outcome": outcome["outcome"],
                    "at": _now(),
                }
            )
            self._respond(request_id, {"outcome": outcome})
            return
        self.unsupported_requests.append(
            {
                "method": method,
                "params": sanitize(json.dumps(params, ensure_ascii=False), self._secrets),
                "at": _now(),
            }
        )
        self._respond_error(request_id, -32601, f"薄驱动不支持服务端请求 {method}")

    def _respond(self, request_id, result: dict) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _respond_error(self, request_id, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def _write(self, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._write_lock:
            if self._stdin is None or self._stdin.closed:
                raise AcpDriveError("ACP 服务进程的标准输入已关闭，无法继续写入", stage="transport")
            try:
                self._stdin.write(text)
                self._stdin.flush()
            except (OSError, ValueError) as exc:
                raise AcpDriveError(f"写入 ACP 服务进程失败：{exc}", stage="transport") from exc

    # -- 请求 ---------------------------------------------------------------------

    def _call(
        self,
        method: str,
        params: dict,
        *,
        timeout: float | None = None,
        stage: str | None = None,
    ) -> dict:
        """发送请求并取回结果；协议级错误不抛出，交给调用方决定是否可接受。"""
        stage = stage or method
        limit = self.timeout if timeout is None else float(timeout)
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            entry = {"event": threading.Event(), "payload": None, "error": None}
            self._pending[request_id] = entry
        self.requests.append(
            {
                "id": request_id,
                "method": method,
                "params": sanitize(json.dumps(params, ensure_ascii=False), self._secrets),
                "at": _now(),
            }
        )
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not entry["event"].wait(limit):
            with self._lock:
                self._pending.pop(request_id, None)
            raise AcpDriveError(
                f"{method} 在 {limit:.0f}s 内没有响应（阶段 {stage}）；"
                f"ACP 进程状态：{self._closed_reason or '仍在运行'}",
                stage=stage,
            )
        if entry["error"]:
            raise AcpDriveError(f"{method} 未完成：{entry['error']}", stage=stage)
        payload = entry["payload"] or {}
        error = payload.get("error")
        if isinstance(error, dict):
            message = sanitize(str(error.get("message") or ""), self._secrets)
            return {"ok": False, "error": {"code": error.get("code"), "message": message}}
        result = payload.get("result")
        if not isinstance(result, dict):
            return {"ok": False, "error": {"code": None, "message": f"{method} 返回了非对象结果"}}
        return {"ok": True, "result": result}

    def call(
        self,
        method: str,
        params: dict,
        *,
        timeout: float | None = None,
        stage: str | None = None,
    ) -> dict:
        """必须成功的请求；失败即抛 :class:`AcpDriveError`。"""
        outcome = self._call(method, params, timeout=timeout, stage=stage)
        if not outcome["ok"]:
            raise AcpDriveError(
                f"{method} 被拒绝：{outcome['error']['message']}（code={outcome['error']['code']}）",
                stage=stage or method,
            )
        return outcome["result"]

    def call_expect_error(
        self,
        method: str,
        params: dict,
        *,
        timeout: float | None = None,
        stage: str | None = None,
    ) -> dict:
        """必须被拒绝的请求；**成功返回反而算失败**，避免把“失配被静默接受”当成通过。"""
        outcome = self._call(method, params, timeout=timeout, stage=stage)
        if outcome["ok"]:
            raise AcpDriveError(
                f"{method} 本应被拒绝，却返回了成功结果；驱动不得把它记为通过",
                stage=stage or method,
            )
        return outcome["error"]

    # -- 收尾与取证 ---------------------------------------------------------------

    def stop(self, *, grace: float = 20.0) -> int | None:
        """关闭 stdin（ACP 以 EOF 触发有界退出），必要时 terminate/kill。"""
        if self._proc is None:
            return None
        try:
            if self._stdin is not None and not self._stdin.closed:
                self._stdin.close()
        except (OSError, ValueError):  # pragma: no cover
            pass
        code: int | None
        try:
            code = self._proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self._proc.terminate()
            try:
                code = self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                code = self._proc.wait(timeout=10)
        self._exit_code = code
        if self._reader is not None:
            self._reader.join(timeout=10)
        self._close_stderr()
        return code

    def _close_stderr(self) -> None:
        if self._stderr_handle is not None:
            try:
                self._stderr_handle.close()
            except OSError:  # pragma: no cover
                pass
            self._stderr_handle = None

    def secret_values(self) -> list[str]:
        """本次进程需要遮蔽的凭据值（服务进程环境 + 会话规格里的凭据字段）。"""
        return list(self._secrets)

    def stderr_tail(self, limit: int = 1200) -> str:
        try:
            text = self.stderr_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return sanitize(tail(text, limit), self._secrets)

    def agent_text(self) -> str:
        """把 `agent_message_chunk` 通知拼成可见回答（仅取证用，不参与控制流）。"""
        chunks = []
        for entry in self.updates:
            update = entry.get("update") or {}
            if update.get("sessionUpdate") != "agent_message_chunk":
                continue
            content = update.get("content") if isinstance(update.get("content"), dict) else {}
            text = content.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
        return sanitize("".join(chunks), self._secrets)

    def evidence(self) -> dict:
        return {
            "requests": self.requests,
            "notifications": len(self.notifications),
            "updates": [
                {
                    "sessionUpdate": item.get("sessionUpdate"),
                    "toolTitle": (item.get("update") or {}).get("title"),
                }
                for item in self.updates
            ],
            "permissions": self.permission_events,
            "unsupported_server_requests": self.unsupported_requests,
            "exit_code": self._exit_code,
            "closed_reason": self._closed_reason,
            "stderr_tail": self.stderr_tail(),
        }


# --------------------------------------------------------------------------------------
# 启动参数与会话规格
# --------------------------------------------------------------------------------------


def resolve_server_argv(args) -> list[str]:
    """解析可 spawn 的 ACP 服务命令；`--patch` 先解析成绝对路径。"""
    if args.server_command:
        return [str(args.server_command), *[str(item) for item in args.server_arg]]
    from dsh_talk_precheck import DshPrecheckError, resolve_dsh_command

    try:
        command = [*resolve_dsh_command(), "--profile", str(args.profile)]
    except DshPrecheckError as exc:
        raise AcpDriveError(f"无法解析本机 dsh 启动命令：{exc}", stage="spawn") from exc
    if args.patch:
        patch_path = resolve_caller_path(args.patch)
        if not patch_path.is_file():
            raise AcpDriveError(
                f"找不到覆盖层文件 {patch_path}（相对路径按本次调用目录解析）", stage="config"
            )
        command += ["--patch", str(patch_path)]
    return command + [str(item) for item in args.server_arg]


def build_server_env(args) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if args.dsh_home:
        env["DSH_HOME"] = str(resolve_caller_path(args.dsh_home))
    return env


def resolve_workspace(args) -> Path:
    workspace = resolve_caller_path(args.cwd or Path.cwd())
    if not workspace.is_dir():
        raise AcpDriveError(f"会话工作区不存在或不是目录：{workspace}", stage="config")
    return workspace


def validate_mcp_servers(servers) -> list[dict]:
    """发送前按 ACP/DSH 的规则做一次本地校验，错误信息比服务端更直白。"""
    if not servers:
        return []
    if not isinstance(servers, list):
        raise AcpDriveError("会话规格里的 mcpServers 必须是数组", stage="config")
    validated = []
    for index, server in enumerate(servers):
        if not isinstance(server, dict):
            raise AcpDriveError(f"mcpServers[{index}] 必须是对象", stage="config")
        if server.get("type"):
            raise AcpDriveError(
                f"mcpServers[{index}] 只支持 stdio 条目（本驱动的薄层边界）；"
                f"实际 type={server.get('type')}",
                stage="config",
            )
        name = str(server.get("name") or "").strip()
        if not name:
            raise AcpDriveError(f"mcpServers[{index}].name 不能为空", stage="config")
        command = str(server.get("command") or "")
        if not command or not os.path.isabs(command):
            raise AcpDriveError(
                f"mcpServers[{index}].command 必须是绝对路径（ACP 会拒绝相对命令）："
                f"{command or '<空>'}",
                stage="config",
            )
        args = server.get("args") or []
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            raise AcpDriveError(f"mcpServers[{index}].args 必须是字符串数组", stage="config")
        env_entries = server.get("env") or []
        if not isinstance(env_entries, list):
            raise AcpDriveError(
                f"mcpServers[{index}].env 必须是 ACP 的 name/value 数组，不是对象",
                stage="config",
            )
        normalized_env = []
        for entry in env_entries:
            if not isinstance(entry, dict) or "name" not in entry or "value" not in entry:
                raise AcpDriveError(
                    f"mcpServers[{index}].env 的每一项都必须是 {{name, value}}",
                    stage="config",
                )
            normalized_env.append({"name": str(entry["name"]), "value": str(entry["value"])})
        validated.append(
            {"name": name, "command": command, "args": list(args), "env": normalized_env}
        )
    return validated


def load_session_spec(path: Path) -> dict:
    spec_path = resolve_caller_path(path)
    if not spec_path.is_file():
        raise AcpDriveError(f"找不到会话规格文件 {spec_path}", stage="config")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcpDriveError(
            f"会话规格不是合法 UTF-8 JSON：{spec_path}（{exc}）", stage="config"
        ) from exc
    if not isinstance(spec, dict):
        raise AcpDriveError(f"会话规格顶层必须是对象：{spec_path}", stage="config")
    return spec


def describe_mcp_servers(servers: list[dict]) -> list[dict]:
    """只描述名字/命令/参数与“环境变量名 → 值或已隐藏”，绝不出凭据正文。"""
    described = []
    for server in servers:
        described.append(
            {
                "name": server["name"],
                "command": server["command"],
                "args": list(server["args"]),
                "env": describe_env({entry["name"]: entry["value"] for entry in server["env"]}),
            }
        )
    return described


def mcp_server_secrets(servers: list[dict]) -> list[str]:
    """会话规格里以凭据字段名给出的值；这些值不得出现在任何输出或落盘内容中。"""
    secrets: list[str] = []
    for server in servers:
        for entry in server.get("env") or []:
            value = str(entry.get("value") or "")
            if value and is_credential_name(str(entry.get("name") or "")):
                secrets.append(value)
    return secrets


def write_json(path: Path, payload: dict, *, allow_in_repo: bool = False) -> Path:
    target = resolve_caller_path(path)
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        if not allow_in_repo:
            raise AcpDriveError(
                f"输出目标位于仓库内（{target}）；隔离临时产物请显式加 --allow-in-repo",
                stage="output",
            )
    if target.exists():
        raise AcpDriveError(f"输出目标已存在，不覆盖：{target}", stage="output")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def assert_no_secrets(payload: dict, secrets: list[str]) -> None:
    """产物里不得出现凭据正文：序列化后逐个比对，比“字段名看起来安全”更强。"""
    serialized = json.dumps(payload, ensure_ascii=False)
    for secret in secrets:
        if secret and secret in serialized:
            raise AcpDriveError(
                "产物会包含凭据正文；请改为经仓库外密钥文件或外部授权环境传递",
                stage="output",
            )


# --------------------------------------------------------------------------------------
# 零模型阶段
# --------------------------------------------------------------------------------------


def stage_initialize(client: AcpClient, *, want_list: bool = False) -> dict:
    result = client.call(
        "initialize",
        {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "talk-dsh-acp-drive", "version": "1"},
        },
        stage="initialize",
    )
    capabilities = (
        result.get("agentCapabilities") if isinstance(result.get("agentCapabilities"), dict) else {}
    )
    session_capabilities = (
        capabilities.get("sessionCapabilities")
        if isinstance(capabilities.get("sessionCapabilities"), dict)
        else {}
    )
    evidence = {
        "protocolVersion": result.get("protocolVersion"),
        "agentInfo": result.get("agentInfo"),
        "sessionCapabilities": sorted(session_capabilities),
        "promptCapabilities": capabilities.get("promptCapabilities"),
        "mcpCapabilities": capabilities.get("mcpCapabilities"),
        "authMethods": result.get("authMethods"),
    }
    if evidence["protocolVersion"] != ACP_PROTOCOL_VERSION:
        raise AcpDriveError(
            f"ACP 协议版本不符：期望 {ACP_PROTOCOL_VERSION}，实际 {evidence['protocolVersion']}",
            stage="initialize",
        )
    for required in ("resume", "list", "close"):
        if required not in session_capabilities:
            raise AcpDriveError(
                f"ACP initialize 未声明 sessionCapabilities.{required}；本片要求的持久恢复不可用",
                stage="initialize",
            )
    if want_list:
        listed = client.call("session/list", {}, stage="session/list")
        evidence["sessionCount"] = len(listed.get("sessions") or [])
    return evidence


def list_session_ids(client: AcpClient, cwd: Path) -> list[str]:
    listed = client.call("session/list", {"cwd": str(cwd)}, stage="session/list")
    sessions = listed.get("sessions") if isinstance(listed.get("sessions"), list) else []
    return [str(item.get("sessionId")) for item in sessions if isinstance(item, dict)]


def mismatch_workspace(cwd: Path) -> Path:
    """构造一个**必然不同于**会话工作区的路径，用于 resume 失配负例。

    ACP 按物理目录身份比较工作区，路径不存在时退化为字面比较；因此这里既处理
    “父目录就是同一个盘根”的情况，也不要求该路径真实存在。
    """
    parent = cwd.parent
    if parent != cwd:
        return parent
    return cwd / "dsh-acp-cwd-mismatch-probe"


def stage_lifecycle(client: AcpClient, *, cwd: Path, mcp_servers: list[dict]) -> dict:
    """零模型 ACP 生命周期（#76 按真实 `dsh-acp` 语义修正 D3）：

    `initialize` → `session/new` → `session/list`（**活动期应隐藏**）→ `session/close`
    → `session/list`（**持久化后应可见**）→ 失配 / 未知 ID 拒绝 → `session/resume` 同 ID
    → 重复 resume 拒绝 → `session/list`（**恢复后又隐藏**）→ `session/close`
    → `session/list`（**再次可见**）。

    真实 `dsh-acp` 的 `session/list` 会过滤**活动**会话（#75 复核实证：新建后立刻
    断言它出现在 list 里必然失败）。因此本阶段不再用“新建后可见”当持久化证据，
    而用“关闭后可见”证明持久化、用“恢复后再次隐藏 + 持久化条目数不增加 + 重复
    resume 被拒”证明恢复的是**原会话**，而不是退化成新建。`session/resume` 的返回
    结果**不保证带 sessionId**（真机只返回 configOptions），所以返回值只作为附加
    证据：带了就必须等于请求的 ID，没带不构成失败。

    该序列不触发任何模型调用；它证明的是原生 ACP 的会话持久化与恢复接口本身，
    不代表模型侧主控闭环已经通过。
    """
    stages: list[dict] = []

    def record(name: str, ok: bool, **extra) -> None:
        entry = {"stage": name, "ok": bool(ok), "at": _now()}
        entry.update(extra)
        stages.append(entry)

    def listed_ids() -> list[str]:
        return list_session_ids(client, cwd)

    initialize_evidence = stage_initialize(client)
    record("initialize", True, protocolVersion=initialize_evidence["protocolVersion"])

    created = client.call(
        "session/new", {"cwd": str(cwd), "mcpServers": mcp_servers}, stage="session/new"
    )
    session_id = created.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise AcpDriveError(f"session/new 没有返回可用 sessionId：{created}", stage="session/new")
    record(
        "session/new",
        True,
        sessionId=session_id,
        configOptions=len(created.get("configOptions") or []),
    )

    # 活动期：真实服务端过滤活动会话；这里可见反而说明语义不符，不得当成持久化证据。
    listed_while_active = listed_ids()
    if session_id in listed_while_active:
        raise AcpDriveError(
            f"新建会话 {session_id} 仍是活动状态却出现在 session/list 中；"
            "真实 dsh-acp 会过滤活动会话，该结果不能作为持久化证据",
            stage="session/list",
        )
    record(
        "session/list-active-hidden-after-new",
        True,
        sessionId=session_id,
        containsSession=False,
        count=len(listed_while_active),
    )

    client.call("session/close", {"sessionId": session_id}, stage="session/close")
    record("session/close", True, sessionId=session_id)

    listed_after_close = listed_ids()
    if session_id not in listed_after_close:
        raise AcpDriveError(
            f"关闭后 {session_id} 仍不在 session/list 里，无法证明它被持久化",
            stage="session/list",
        )
    record(
        "session/list-persisted-after-close",
        True,
        sessionId=session_id,
        containsSession=True,
        count=len(listed_after_close),
    )

    # 负例 1：工作区不符必须被拒绝——resume 不得退化成“新建一个别的会话”。
    mismatch_error = client.call_expect_error(
        "session/resume",
        {"sessionId": session_id, "cwd": str(mismatch_workspace(cwd)), "mcpServers": mcp_servers},
        stage="session/resume-mismatch",
    )
    record(
        "session/resume-cwd-mismatch-rejected",
        True,
        code=mismatch_error.get("code"),
        message=mismatch_error.get("message"),
    )

    # 负例 2：未知 ID 必须被拒绝，避免“任何 ID 都能恢复”的假通过。
    unknown_error = client.call_expect_error(
        "session/resume",
        {
            "sessionId": "00000000-0000-4000-8000-000000000000",
            "cwd": str(cwd),
            "mcpServers": mcp_servers,
        },
        stage="session/resume-unknown",
    )
    record(
        "session/resume-unknown-rejected",
        True,
        code=unknown_error.get("code"),
        message=unknown_error.get("message"),
    )

    # 正例：同 ID、同工作区恢复；服务端接受该 ID 本身就是证据。
    resumed = client.call(
        "session/resume",
        {"sessionId": session_id, "cwd": str(cwd), "mcpServers": mcp_servers},
        stage="session/resume",
    )
    returned_id = resumed.get("sessionId")
    if returned_id is not None and str(returned_id) != session_id:
        raise AcpDriveError(
            f"session/resume 返回了另一个 sessionId（{returned_id} ≠ {session_id}）；"
            "恢复实际变成了新建或换会话",
            stage="session/resume",
        )
    record(
        "session/resume",
        True,
        sessionId=session_id,
        returnedSessionId=returned_id,
        resultKeys=sorted(resumed),
    )

    # 负例 3：会话已在活动中，重复 resume 必须被拒绝。
    duplicate_error = client.call_expect_error(
        "session/resume",
        {"sessionId": session_id, "cwd": str(cwd), "mcpServers": mcp_servers},
        stage="session/resume-duplicate",
    )
    record(
        "session/resume-duplicate-rejected",
        True,
        code=duplicate_error.get("code"),
        message=duplicate_error.get("message"),
    )

    # 同 ID 恢复的独立证据：恢复后该会话重新变成活动状态（list 里消失），
    # 且持久化条目数正好少一条——没有多出一个新建的会话。
    listed_after_resume = listed_ids()
    if session_id in listed_after_resume:
        raise AcpDriveError(
            f"恢复后 {session_id} 仍出现在 session/list 中；无法证明它已回到活动状态",
            stage="session/list",
        )
    if len(listed_after_resume) != len(listed_after_close) - 1:
        raise AcpDriveError(
            f"恢复后持久化会话数从 {len(listed_after_close)} 变成 {len(listed_after_resume)}；"
            "没有正好少掉被恢复的那一条，恢复可能新建了会话",
            stage="session/list",
        )
    record(
        "session/list-active-hidden-after-resume",
        True,
        sessionId=session_id,
        containsSession=False,
        count=len(listed_after_resume),
        persistedCountAfterClose=len(listed_after_close),
    )

    client.call("session/close", {"sessionId": session_id}, stage="session/close")
    record("session/close-after-resume", True, sessionId=session_id)
    listed_after_final_close = listed_ids()
    if session_id not in listed_after_final_close:
        raise AcpDriveError(
            f"再次关闭后 {session_id} 不在 session/list 里；恢复后的会话没有回到持久化状态",
            stage="session/list",
        )
    record(
        "session/list-persisted-after-resume-close",
        True,
        sessionId=session_id,
        containsSession=True,
        count=len(listed_after_final_close),
    )

    return {
        "session_id": session_id,
        "stages": stages,
        "initialize": initialize_evidence,
        "listed_after_close_contains_session": session_id in listed_after_close,
        "listed_after_final_close_contains_session": session_id in listed_after_final_close,
        "persisted_session_count_after_close": len(listed_after_close),
    }


def stage_prompt(client: AcpClient, *, session_id: str, text: str, timeout: float) -> dict:
    """单条提示的模型阶段：发送一次、等待结算、取证；不做第二轮。"""
    result = client.call(
        "session/prompt",
        {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        timeout=timeout,
        stage="session/prompt",
    )
    return {
        "stopReason": result.get("stopReason"),
        "agentText": client.agent_text(),
        "updateCount": len(client.updates),
        "toolTitles": [
            (item.get("update") or {}).get("title")
            for item in client.updates
            if (item.get("update") or {}).get("sessionUpdate") == "tool_call"
        ],
        "permissions": list(client.permission_events),
    }


# --------------------------------------------------------------------------------------
# 会话引用
# --------------------------------------------------------------------------------------


def build_session_ref(
    *,
    session_id: str,
    cwd: Path,
    argv: list[str],
    mcp_servers: list[dict],
    patch: Path | None,
    dsh_home: Path | None,
    model_calls: int,
    secrets: list[str] | None = None,
) -> dict:
    ref = {
        "protocol": "acp",
        "protocol_version": ACP_PROTOCOL_VERSION,
        "session_id": session_id,
        "cwd": str(cwd),
        "server_argv": list(argv),
        "patch": str(patch) if patch else None,
        "dsh_home": str(dsh_home) if dsh_home else None,
        "mcp_servers": describe_mcp_servers(mcp_servers),
        "model_calls": model_calls,
        "created_at": _now(),
        "note": "本文件不含凭据正文；恢复时用 session/resume 传同一个 session_id 与同一个 cwd。",
    }
    assert_no_secrets(ref, [*(secrets or []), *mcp_server_secrets(mcp_servers)])
    return ref


def load_resume_target(path: Path) -> dict:
    ref_path = resolve_caller_path(path)
    if not ref_path.is_file():
        raise AcpDriveError(f"找不到会话引用文件 {ref_path}", stage="config")
    try:
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcpDriveError(
            f"会话引用不是合法 UTF-8 JSON：{ref_path}（{exc}）", stage="config"
        ) from exc
    if not isinstance(ref, dict) or not isinstance(ref.get("session_id"), str):
        raise AcpDriveError(f"会话引用缺少 session_id：{ref_path}", stage="config")
    return ref


def default_python() -> Path:
    venv = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return venv
    return Path(sys.executable)


def render_session_spec(*, cwd: Path, key_file: Path, server: str, project: str) -> str:
    if not SESSION_TEMPLATE.is_file():
        raise AcpDriveError(f"找不到会话规格模板 {SESSION_TEMPLATE}", stage="config")
    text = SESSION_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__CWD__": str(cwd).replace("\\", "/"),
        "__REPO__": str(REPO_ROOT).replace("\\", "/"),
        "__PYTHON__": str(default_python()).replace("\\", "/"),
        "__KEY_FILE__": str(key_file).replace("\\", "/"),
        "__SERVER__": server,
        "__PROJECT__": project,
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    leftover = [token for token in replacements if token in text]
    if leftover:
        raise AcpDriveError(f"会话规格模板仍有未替换占位符：{leftover}", stage="config")
    return text


# --------------------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------------------


def _prepare(args, *, require_model: bool = False) -> tuple[AcpClient, Path, list[dict], dict]:
    if require_model and not args.allow_model:
        raise AcpDriveError(
            "prompt 会真实调用被测会话的模型：必须显式加 --allow-model 才会执行",
            stage="guard",
        )
    workspace = resolve_workspace(args)
    mcp_servers: list[dict] = []
    spec_info: dict = {}
    if getattr(args, "session_spec", None):
        spec = load_session_spec(args.session_spec)
        spec_cwd = spec.get("cwd")
        if isinstance(spec_cwd, str) and spec_cwd:
            workspace = resolve_caller_path(Path(spec_cwd))
            if not workspace.is_dir():
                raise AcpDriveError(f"会话规格里的 cwd 不存在：{workspace}", stage="config")
        mcp_servers = validate_mcp_servers(spec.get("mcpServers"))
        spec_info = {
            "spec": str(resolve_caller_path(args.session_spec)),
            "mcp_servers": describe_mcp_servers(mcp_servers),
        }
    elif getattr(args, "mcp_server_name", None):
        mcp_servers = validate_mcp_servers(
            [
                {
                    "name": args.mcp_server_name,
                    "command": args.mcp_server_command,
                    "args": list(args.mcp_server_arg),
                    "env": [{"name": "PYTHONUTF8", "value": "1"}],
                }
            ]
        )
        spec_info = {"mcp_servers": describe_mcp_servers(mcp_servers)}

    argv = resolve_server_argv(args)
    env = build_server_env(args)
    stderr_path = (
        resolve_caller_path(args.stderr_log) if args.stderr_log else Path(DEFAULT_STDERR_LOG)
    )
    client = AcpClient(
        argv,
        cwd=workspace,
        env=env,
        stderr_path=stderr_path,
        timeout=args.timeout,
        permission=args.permission,
        extra_secrets=mcp_server_secrets(mcp_servers),
    )
    context = {
        "workspace": str(workspace),
        "server_argv": argv,
        "server_env": describe_env(env),
        "stderr_log": str(stderr_path),
        "patch": str(resolve_caller_path(args.patch)) if args.patch else None,
        "dsh_home": str(resolve_caller_path(args.dsh_home)) if args.dsh_home else None,
        **spec_info,
    }
    return client, workspace, mcp_servers, context


def command_handshake(args) -> dict:
    client, workspace, _servers, context = _prepare(args)
    client.start()
    try:
        initialize = stage_initialize(client, want_list=args.with_list)
        payload = {
            "ok": True,
            "mode": "handshake",
            "model_calls": 0,
            "workspace": str(workspace),
            "initialize": initialize,
            "context": context,
            "evidence": client.evidence(),
        }
    finally:
        exit_code = client.stop()
    payload["server_exit_code"] = exit_code
    return payload


def command_lifecycle(args) -> dict:
    client, workspace, mcp_servers, context = _prepare(args)
    client.start()
    try:
        result = stage_lifecycle(client, cwd=workspace, mcp_servers=mcp_servers)
        payload = {
            "ok": True,
            "mode": "lifecycle",
            "model_calls": 0,
            "workspace": str(workspace),
            "context": context,
            **result,
            "evidence": client.evidence(),
        }
    finally:
        exit_code = client.stop()
    payload["server_exit_code"] = exit_code

    if args.session_ref_out:
        ref = build_session_ref(
            session_id=payload["session_id"],
            cwd=workspace,
            argv=context["server_argv"],
            mcp_servers=mcp_servers,
            patch=Path(context["patch"]) if context["patch"] else None,
            dsh_home=Path(context["dsh_home"]) if context["dsh_home"] else None,
            model_calls=0,
            secrets=client.secret_values(),
        )
        target = write_json(args.session_ref_out, ref, allow_in_repo=args.allow_in_repo)
        payload["session_ref"] = str(target)
    return payload


def command_prompt(args) -> dict:
    client, workspace, mcp_servers, context = _prepare(args, require_model=True)
    prompt_text = args.prompt_text
    if args.prompt_file:
        prompt_path = resolve_caller_path(args.prompt_file)
        if not prompt_path.is_file():
            raise AcpDriveError(f"找不到提示文件 {prompt_path}", stage="config")
        prompt_text = prompt_path.read_text(encoding="utf-8")
    if not prompt_text:
        raise AcpDriveError("必须用 --prompt-text 或 --prompt-file 给出一条提示正文", stage="config")

    resume_ref = load_resume_target(args.resume) if args.resume else None
    if resume_ref is not None:
        # 工作区一致性在**启动子进程之前**校验：不一致时直接拒绝，
        # 不去启动一个注定要被 ACP 拒绝的会话，也不做静默替换。
        ref_cwd = resolve_caller_path(Path(str(resume_ref.get("cwd") or workspace)))
        if ref_cwd != workspace:
            raise AcpDriveError(
                f"恢复工作区与会话引用不一致：引用 {ref_cwd}，本次 {workspace}"
                "（ACP 会拒绝不符的工作区，驱动不做静默替换）",
                stage="config",
            )
    client.start()
    stages: list[dict] = []
    session_id = ""
    try:
        stage_initialize(client)
        if resume_ref is not None:
            session_id = str(resume_ref["session_id"])
            client.call(
                "session/resume",
                {"sessionId": session_id, "cwd": str(workspace), "mcpServers": mcp_servers},
                stage="session/resume",
            )
            stages.append(
                {"stage": "session/resume", "ok": True, "sessionId": session_id, "at": _now()}
            )
        else:
            created = client.call(
                "session/new", {"cwd": str(workspace), "mcpServers": mcp_servers}, stage="session/new"
            )
            session_id = created.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise AcpDriveError(f"session/new 没有返回可用 sessionId：{created}", stage="session/new")
            stages.append({"stage": "session/new", "ok": True, "sessionId": session_id, "at": _now()})

        prompt_result = stage_prompt(
            client, session_id=session_id, text=prompt_text, timeout=args.prompt_timeout
        )
        stages.append(
            {
                "stage": "session/prompt",
                "ok": True,
                "stopReason": prompt_result["stopReason"],
                "at": _now(),
            }
        )
        payload = {
            "ok": True,
            "mode": "prompt",
            "model_calls": 1,
            "workspace": str(workspace),
            "session_id": session_id,
            "resumed": resume_ref is not None,
            "prompt": prompt_result,
            "stages": stages,
            "context": context,
            "evidence": client.evidence(),
        }
        client.call("session/close", {"sessionId": session_id}, stage="session/close")
    finally:
        exit_code = client.stop()
    payload["server_exit_code"] = exit_code

    if args.session_ref_out:
        ref = build_session_ref(
            session_id=payload["session_id"],
            cwd=workspace,
            argv=context["server_argv"],
            mcp_servers=mcp_servers,
            patch=Path(context["patch"]) if context["patch"] else None,
            dsh_home=Path(context["dsh_home"]) if context["dsh_home"] else None,
            model_calls=1,
            secrets=client.secret_values(),
        )
        target = write_json(args.session_ref_out, ref, allow_in_repo=args.allow_in_repo)
        payload["session_ref"] = str(target)
    return payload


def command_spec(args) -> dict:
    cwd = resolve_caller_path(args.cwd or Path.cwd())
    if not cwd.is_dir():
        raise AcpDriveError(f"会话工作区不存在或不是目录：{cwd}", stage="config")
    key_file = resolve_caller_path(args.key_file)
    try:
        key_file.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise AcpDriveError(
            f"密钥文件位于仓库内（{key_file}）；请放到仓库外，例如 ~/.talk/agent-deepseek.key",
            stage="config",
        )
    if not key_file.is_file():
        raise AcpDriveError(f"找不到密钥文件 {key_file}；请先创建它再渲染会话规格", stage="config")
    text = render_session_spec(cwd=cwd, key_file=key_file, server=args.server, project=args.project)
    if args.write is None:
        print(text)
        return {
            "ok": True,
            "mode": "spec",
            "written": None,
            "key_file": str(key_file),
            "already_printed": True,
        }
    target = resolve_caller_path(args.write)
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        if not args.allow_in_repo:
            raise AcpDriveError(
                f"写入目标位于仓库内（{target}）；隔离验证请显式加 --allow-in-repo",
                stage="output",
            )
    if target.exists():
        raise AcpDriveError(f"目标已存在，不覆盖：{target}（先删除或换目录）", stage="output")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"ok": True, "mode": "spec", "written": str(target), "key_file": str(key_file)}


#: 值合法地以 `-` 开头的驱动选项（下游命令参数与 MCP 参数，见模块说明的 D1 合同）。
DASH_VALUE_OPTIONS = ("--server-arg", "--mcp-server-arg")


def drive_option_strings(parser: argparse.ArgumentParser) -> set[str]:
    """收集本驱动（含全部子命令）已注册的选项名。

    只用于把“下游参数”和“驱动自己的选项”区分开：argparse 没有公开的遍历接口，
    这里刻意使用内部结构，且仅读取选项名，不改动解析行为。
    """
    options: set[str] = set()
    stack = [parser]
    while stack:
        current = stack.pop()
        for action in current._actions:
            options.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                stack.extend(action.choices.values())
    return options


def normalize_dash_values(argv: list[str], parser: argparse.ArgumentParser) -> list[str]:
    """把 `--server-arg -X` 这类分离写法规范化为等号写法（#75 缺陷 D1 的修复）。

    argparse 会把 `-X` 当成驱动选项，报 `expected one argument` 并以 2 退出，
    于是 Python 的 `-X utf8`、DSH 的 `--profile` 都传不下去。修复后的合同：

    - `--server-arg=值` / `--mcp-server-arg=值`：**任何值都可用**，是推荐写法；
    - `--server-arg 值`：值以 `-` 开头且**不是本驱动已注册的选项名**时自动识别；
    - 值恰好与驱动选项同名（例如 `--cwd`）时保持原样交给 argparse 报用法错误，
      绝不把“驱动自己的选项”当成下游参数静默吞掉。
    """
    options = drive_option_strings(parser)
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        following = argv[index + 1] if index + 1 < len(argv) else None
        if (
            token in DASH_VALUE_OPTIONS
            and following is not None
            and following.startswith("-")
            and following != "--"
            and following not in options
        ):
            normalized.append(f"{token}={following}")
            index += 2
            continue
        normalized.append(token)
        index += 1
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DSH 原生 ACP 薄驱动（传输 / 会话控制 / 输出取证，零模型优先）",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_server_options(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--server-command", default=None, help="替换默认 dsh 命令（模拟 ACP 进程/测试用）"
        )
        target.add_argument(
            "--server-arg",
            action="append",
            default=[],
            help=(
                "追加给服务命令的参数，可重复；值以 - 开头时推荐 --server-arg=值"
                "（例如 --server-arg=-X）；分离写法在值不与驱动选项同名时也接受"
            ),
        )
        target.add_argument("--profile", default="acp", help="DSH profile；默认 acp")
        target.add_argument("--patch", type=Path, default=None, help="ACP profile 的 --patch 覆盖层（绝对化后再传）")
        target.add_argument("--dsh-home", type=Path, default=None, help="隔离 DSH_HOME；省略时沿用环境")
        target.add_argument("--cwd", type=Path, default=None, help="会话工作区；默认当前目录")
        target.add_argument("--stderr-log", type=Path, default=None, help="ACP 子进程 stderr 落盘位置")
        target.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单条请求超时秒数")
        target.add_argument(
            "--permission",
            choices=("reject", "allow"),
            default="reject",
            help="对 session/request_permission 的默认应答；默认最保守的 reject",
        )
        target.add_argument("--out", type=Path, default=None, help="把取证 JSON 写到该文件")
        target.add_argument("--allow-in-repo", action="store_true", help="允许把产物写进仓库内（隔离临时目录）")

    def add_session_options(target: argparse.ArgumentParser) -> None:
        target.add_argument("--session-spec", type=Path, default=None, help="无密钥会话规格 JSON（含 mcpServers）")
        target.add_argument("--mcp-server-name", default=None, help="临时挂一个 stdio MCP 服务器（名字）")
        target.add_argument("--mcp-server-command", default=None, help="临时挂载的 MCP 服务器绝对命令")
        target.add_argument(
            "--mcp-server-arg",
            action="append",
            default=[],
            help="临时挂载的 MCP 服务器参数；值以 - 开头时推荐 --mcp-server-arg=值",
        )
        target.add_argument("--session-ref-out", type=Path, default=None, help="写出会话引用（无密钥）")

    handshake = sub.add_parser("handshake", help="零模型：真实 ACP initialize（可附带 session/list）")
    add_server_options(handshake)
    handshake.add_argument("--with-list", action="store_true", help="额外调用一次 session/list")
    handshake.set_defaults(func=command_handshake)

    lifecycle = sub.add_parser(
        "lifecycle",
        help=(
            "零模型：new → list（活动期隐藏）→ close → list（持久化可见）→ "
            "失配/未知/重复拒绝 → resume 同 ID → list（再次隐藏）→ close → list"
        ),
    )
    add_server_options(lifecycle)
    add_session_options(lifecycle)
    lifecycle.set_defaults(func=command_lifecycle)

    prompt = sub.add_parser("prompt", help="模型阶段：单条提示（需 --allow-model）")
    add_server_options(prompt)
    add_session_options(prompt)
    prompt.add_argument("--allow-model", action="store_true", help="确认本次会真实调用被测会话的模型")
    prompt.add_argument("--prompt-text", default=None, help="提示正文")
    prompt.add_argument("--prompt-file", type=Path, default=None, help="从文件读取提示正文")
    prompt.add_argument(
        "--prompt-timeout", type=float, default=DEFAULT_PROMPT_TIMEOUT, help="单条提示的等待上限（秒）"
    )
    prompt.add_argument("--resume", type=Path, default=None, help="先按会话引用 session/resume 再提示")
    prompt.set_defaults(func=command_prompt)

    spec = sub.add_parser("spec", help="渲染无密钥会话规格模板")
    spec.add_argument("--write", type=Path, default=None, help="写入该路径；省略时只打印")
    spec.add_argument("--cwd", type=Path, default=None, help="会话工作区")
    spec.add_argument("--key-file", type=Path, required=True, help="仓库外密钥文件路径（只写路径，不写密钥）")
    spec.add_argument("--server", default="http://127.0.0.1:8000")
    spec.add_argument("--project", default="prj_e8fe7066bbec")
    spec.add_argument("--allow-in-repo", action="store_true", help="允许写进仓库内的隔离临时目录")
    spec.set_defaults(func=command_spec)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover
                pass

    parser = build_parser()
    try:
        options = parser.parse_args(
            normalize_dash_values(list(sys.argv[1:] if argv is None else argv), parser)
        )
    except SystemExit as exc:
        # argparse 已把用法/错误写到 stderr；这里只把退出码交还调用方，
        # 使 in-process 调用（测试/嵌入）能断言退出码而不是收到 SystemExit。
        return int(exc.code or 0)
    try:
        payload = options.func(options)
    except AcpDriveError as exc:
        print(f"ACP 驱动失败（阶段 {exc.stage}）：{exc}", file=sys.stderr)
        return 1
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"ACP 驱动失败：子进程无法启动或未在时限内结束（{type(exc).__name__}）", file=sys.stderr)
        return 1

    if not payload.pop("already_printed", False):
        print(json.dumps(payload, ensure_ascii=False))
    if getattr(options, "out", None):
        try:
            target = write_json(
                options.out, payload, allow_in_repo=getattr(options, "allow_in_repo", False)
            )
        except AcpDriveError as exc:
            print(f"ACP 驱动失败（阶段 {exc.stage}）：{exc}", file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "evidence_written": str(target)}, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
