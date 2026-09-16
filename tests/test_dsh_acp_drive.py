# -*- coding: utf-8 -*-
"""`scripts/dsh_acp_drive.py` 与 ACP 覆盖层/会话规格的针对性测试（#74；#76 返工 D1–D3）。

覆盖本片承诺的行为：

- **传输**：ACP v1 的 newline-delimited JSON-RPC 请求/响应/通知，服务端反向请求
  （`session/request_permission`）必须被应答，超时与进程中途退出必须报失败；
- **下游参数（D1）**：`--server-arg` 必须能传 `-X utf8`、`--profile` 这类前导连字符值，
  等号写法与分离写法都可用；与驱动选项同名时按用法错误退出，不静默吞掉；
- **会话控制（D3）**：`session/new` → **活动期在 `session/list` 中隐藏** → `session/close`
  → **可见（持久化）** → `session/resume` **同 ID** → 再次隐藏；工作区不符、未知 ID、
  已活动会话的重复 resume 都必须被拒绝（`call_expect_error` 保证“被静默接受”也算失败）；
- **不退化**：整个生命周期里 `session/new` 只出现一次，恢复只走 `session/resume`；
- **凭证**：会话规格只写密钥文件**路径**；驱动输出与会话引用里不出现凭据正文；
  隔离服务上验证“ACP 声明的 env 才会到达 MCP 子进程”，父进程环境里的密钥会被清洗掉；
- **配置层（D2）**：覆盖层仍是 13 条原生工具禁用 + 只读沙箱，且**不再覆盖 approval**
  （`read-only + policy: never` 不匹配 ACP preset，真实 `session/new` 报 -32603），
  `dump --profile acp` 会把 profile 传给 DSH。

全部测试使用**模拟 ACP 进程**与**隔离 TALK 服务**，不启动真实模型、不读生产凭证、
不写生产数据。模拟进程按 `@deepseek-ai/dsh-acp` 0.1.5-rc.2 的**真机可观察行为**实现方法名、
能力声明与错误语义（`session/new` 即进入活动状态、`session/list` 过滤活动会话、
`session/resume` 的 `invalidParams` 分支与“返回里没有 sessionId”），并按
`@deepseek-ai/dsh-mcp-client` 的 `buildChildEnv` 复现“清洗父环境 + 合并声明 env”。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import server.main as server_main
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_ROOT / "scripts"
LAUNCHER = PROJECT_ROOT / "scripts" / "dsh_talk_mcp_launch.py"
SESSION_TEMPLATE_PATH = PROJECT_ROOT / "deploy" / "dsh" / "acp-session.template.json"
OVERLAY_TEMPLATE_PATH = PROJECT_ROOT / "deploy" / "dsh" / "acp-overlay.template.yml"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import dsh_acp_drive  # noqa: E402  （驱动自身也这样导入同目录模块）
import dsh_talk_precheck  # noqa: E402

EXPECTED_TOOLS = list(dsh_talk_precheck.EXPECTED_TOOLS)
PLACEHOLDER_KEY = "isolated-member-key-0123456789"


# --------------------------------------------------------------------------------------
# 模拟 ACP 服务进程
# --------------------------------------------------------------------------------------

MOCK_ACP_SOURCE = '''# -*- coding: utf-8 -*-
"""最小 ACP v1 服务进程：复现 dsh-acp 的方法、能力与错误语义（测试用）。"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CREDENTIAL_NAME = re.compile(r"KEY|PASSWORD|SECRET|TOKEN", re.I)


def parse_args():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--report", required=True)
    parser.add_argument("--state", default=None)
    parser.add_argument("--fail-method", default=None)
    parser.add_argument("--hang-method", default=None)
    parser.add_argument("--exit-after", default=None)
    parser.add_argument("--emit-permission", action="store_true")
    parser.add_argument("--probe-mcp", action="store_true")
    parser.add_argument("--call-mcp-tool", default=None)
    parser.add_argument("--drop-env", default="")
    parser.add_argument("--no-resume-capability", action="store_true")
    return parser.parse_args()


class MockAcpServer:
    def __init__(self, args):
        self.args = args
        self.report = Path(args.report)
        self.sessions = {}
        self.active = set()
        self.counter = 0
        self.server_request_id = 900
        self.drop = {name for name in (args.drop_env or "").split(",") if name}
        # 子进程事实（#76 D1）：`sys.orig_argv` 含解释器选项，能证明 `-X utf8`
        # 这类前导连字符参数真的到达了下游进程，而不是只被驱动解析掉。
        self.record(
            "startup",
            argv=list(sys.argv),
            orig_argv=list(getattr(sys, "orig_argv", [])),
            utf8_mode=bool(sys.flags.utf8_mode),
            python_utf8_env=os.environ.get("PYTHONUTF8"),
        )
        self.load_state()

    # -- 持久化（模拟 dsh 的 session 持久化：新进程仍能 resume） -----------
    def load_state(self):
        if not self.args.state:
            return
        path = Path(self.args.state)
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.sessions = {str(k): v for k, v in (data.get("sessions") or {}).items()}
        self.counter = int(data.get("counter") or 0)

    def save_state(self):
        if not self.args.state:
            return
        Path(self.args.state).write_text(
            json.dumps({"sessions": self.sessions, "counter": self.counter}, ensure_ascii=False),
            encoding="utf-8",
        )

    # -- 协议 ---------------------------------------------------------------
    def send(self, payload):
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\\n")
        sys.stdout.flush()

    def record(self, event, **fields):
        entry = {"event": event}
        entry.update(fields)
        with self.report.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")

    def respond(self, request_id, result):
        self.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def error(self, request_id, code, message):
        self.send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def notify(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def read_response(self, request_id):
        """同步等待某个 id 的响应；EOF 返回 None。"""
        while True:
            line = sys.stdin.readline()
            if not line:
                return None
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == request_id:
                return payload
            self.record("client_extra", payload=payload)

    # -- MCP 子进程探测 ------------------------------------------------------
    def build_child_env(self, entries):
        """复现 dsh-mcp-client 的 buildChildEnv：清洗父环境 + 合并声明 env。"""
        env = {
            name: value
            for name, value in os.environ.items()
            if not CREDENTIAL_NAME.search(name) and not name.startswith("DSH_")
        }
        for entry in entries:
            if entry.get("name") in self.drop:
                continue
            env[entry["name"]] = entry["value"]
        return env

    def probe_mcp(self, server, cwd):
        command = [server["command"], *[str(item) for item in server.get("args") or []]]
        env = self.build_child_env(server.get("env") or [])
        self.record(
            "mcp_child_env",
            names=sorted(env),
            has_parent_key="TALK_API_KEY" in env,
            command=command,
        )
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(cwd),
        )
        tools = []
        call_payload = None
        try:
            try:
                proc.stdin.write(json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "mock-acp", "version": "1"}},
                }, ensure_ascii=False) + "\\n")
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\\n")
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\\n")
                if self.args.call_mcp_tool:
                    proc.stdin.write(json.dumps({
                        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": self.args.call_mcp_tool, "arguments": {}},
                    }, ensure_ascii=False) + "\\n")
                proc.stdin.flush()
            except (OSError, ValueError):
                pass
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == 2 and isinstance(payload.get("result"), dict):
                    tools = [str(item.get("name")) for item in payload["result"].get("tools") or []]
                if payload.get("id") == 3:
                    call_payload = payload
                    break
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            stderr_text = proc.stderr.read() if proc.stderr else ""
        self.record("mcp_probe", tools=tools, call=call_payload, stderr_tail=stderr_text[-600:])
        return tools, stderr_text

    # -- 方法 ---------------------------------------------------------------
    def handle(self, payload):
        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params") or {}
        if method is None:
            self.record("client_response", payload=payload)
            return
        self.record("request", method=method, params=params)

        if self.args.exit_after and method == self.args.exit_after:
            sys.stdout.flush()
            raise SystemExit(0)
        if method == self.args.fail_method:
            self.error(request_id, -32603, "mock failure for " + method)
            return
        if method == self.args.hang_method:
            while True:
                time.sleep(30)

        if method == "initialize":
            capabilities = {"close": {}, "list": {}}
            if not self.args.no_resume_capability:
                capabilities["resume"] = {}
            self.respond(request_id, {
                "protocolVersion": 1,
                "agentInfo": {"name": "mock-dsh-acp", "version": "0.0.0-test"},
                "agentCapabilities": {
                    "mcpCapabilities": {"http": True},
                    "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
                    "sessionCapabilities": capabilities,
                },
                "authMethods": [],
            })
        elif method == "session/new":
            cwd = str(params.get("cwd") or "")
            servers = params.get("mcpServers") or []
            if self.args.probe_mcp and servers:
                tools, stderr_text = self.probe_mcp(servers[0], cwd)
                if not tools:
                    self.error(
                        request_id, -32602,
                        "mcpServers[0] failed to start: " + stderr_text.strip()[-200:],
                    )
                    return
            self.counter += 1
            session_id = "mock-session-%d" % self.counter
            self.sessions[session_id] = cwd
            # 真实 dsh-acp：新建后会话处于**活动**状态，session/list 会过滤它
            # （#75 真机实证）。模拟进程必须照此登记，不能按驱动预期伪造协议。
            self.active.add(session_id)
            self.save_state()
            self.respond(request_id, {
                "sessionId": session_id,
                "configOptions": [{
                    "id": "model", "name": "Model", "type": "select",
                    "currentValue": "mock/model", "options": [{"value": "mock/model", "name": "mock"}],
                }],
            })
        elif method == "session/list":
            wanted = params.get("cwd")
            entries = [
                {"sessionId": key, "cwd": value}
                for key, value in self.sessions.items()
                if key not in self.active and (wanted is None or wanted == value)
            ]
            self.respond(request_id, {"sessions": entries})
        elif method == "session/resume":
            session_id = str(params.get("sessionId") or "")
            cwd = str(params.get("cwd") or "")
            if session_id not in self.sessions:
                self.error(request_id, -32602, "session is not resumable: " + session_id)
            elif session_id in self.active:
                self.error(request_id, -32602, "session is already active: " + session_id)
            elif cwd != self.sessions[session_id]:
                self.error(request_id, -32602, "session cwd does not match: " + cwd)
            else:
                self.active.add(session_id)
                self.respond(request_id, {"configOptions": []})
        elif method == "session/close":
            session_id = str(params.get("sessionId") or "")
            self.active.discard(session_id)
            self.respond(request_id, {})
        elif method == "session/prompt":
            session_id = str(params.get("sessionId") or "")
            self.notify("session/update", {
                "sessionId": session_id,
                "update": {"sessionUpdate": "agent_message_chunk",
                           "messageId": "m1", "content": {"type": "text", "text": "MOCK-REPLY"}},
            })
            if self.args.emit_permission:
                self.server_request_id += 1
                self.send({
                    "jsonrpc": "2.0", "id": self.server_request_id,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": session_id,
                        "toolCall": {"toolCallId": "call-1"},
                        "options": [
                            {"optionId": "allow-once", "name": "Allow once", "kind": "allow_once"},
                            {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                        ],
                    },
                })
                response = self.read_response(self.server_request_id)
                self.record("permission_response", response=response)
            self.respond(request_id, {"stopReason": "end_turn"})
        else:
            self.error(request_id, -32601, "mock does not implement " + str(method))

    def serve(self):
        while True:
            line = sys.stdin.readline()
            if not line:
                return
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                self.record("unparsed", text=text[:200])
                continue
            self.handle(payload)


if __name__ == "__main__":
    MockAcpServer(parse_args()).serve()
'''

ARGV_PROBE_SOURCE = '''# -*- coding: utf-8 -*-
"""子进程事实探针：把自己的 argv 与 UTF-8 模式写进 JSON（不用 stdio 管道）。"""

import json
import os
import sys
from pathlib import Path

target = Path(sys.argv[sys.argv.index("--report") + 1])
target.write_text(
    json.dumps(
        {
            "argv": list(sys.argv),
            "orig_argv": list(getattr(sys, "orig_argv", [])),
            "utf8_mode": bool(sys.flags.utf8_mode),
            "python_utf8_env": os.environ.get("PYTHONUTF8"),
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
'''


def _write_script(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _outside_repo_temp_candidates() -> list[Path]:
    """仓库外系统临时目录的候选，**不依赖**全局 ``tempfile.tempdir``。

    `tests/test_support.py` 把夹具目录建在仓库内的 ``.tmp-tests``，宿主或其它测试
    也可能改写 ``tempfile.tempdir``；因此这里按环境变量显式列出候选，逐个解析后再
    由调用方验证“确实在仓库外”，而不是假定默认 ``TemporaryDirectory()`` 就在仓库外。
    """
    candidates: list[Path] = []
    from_env = (os.environ.get(name) for name in ("TMPDIR", "TEMP", "TMP"))
    for raw in (*from_env, tempfile.gettempdir()):
        if not raw:
            continue
        try:
            resolved = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if resolved not in candidates:
            candidates.append(resolved)
    return candidates


def outside_repo_temp_dir(prefix: str = "dsh-acp-key-") -> tempfile.TemporaryDirectory:
    """创建**解析后确认位于仓库外**的临时目录；调用方负责 ``cleanup()``。

    启动器 `scripts/dsh_talk_mcp_launch.py` 按设计拒绝仓库内密钥文件，测试假密钥必须
    真的落在仓库外，否则 `session/new` 会以 -32602 失败。找不到可用目录时直接报错，
    绝不回落到仓库内位置或用户正式凭证位置。
    """
    repo = PROJECT_ROOT.resolve()
    problems: list[str] = []
    for candidate in _outside_repo_temp_candidates():
        try:
            handle = tempfile.TemporaryDirectory(prefix=prefix, dir=str(candidate))
        except (OSError, RuntimeError) as exc:
            problems.append(f"{candidate}：无法创建临时目录（{exc}）")
            continue
        resolved = Path(handle.name).resolve()
        if not resolved.is_relative_to(repo):
            return handle
        handle.cleanup()
        problems.append(f"{candidate}：解析后仍在仓库内（{resolved}）")
    raise RuntimeError(
        "找不到可用的仓库外系统临时目录，无法放置测试假密钥："
        + "；".join(problems or ["无候选目录"])
    )


@contextmanager
def outside_repo_key_file(content: str):
    """在仓库外临时目录里放一个**假**密钥文件，退出时必定清理。"""
    directory = outside_repo_temp_dir()
    try:
        key_file = Path(directory.name) / "agent-deepseek.key"
        key_file.write_text(content, encoding="utf-8")
        yield key_file.resolve()
    finally:
        directory.cleanup()


def mock_server_argv(
    mock: Path, report: Path, *extra: str, state: Path | None = None, equals_form: bool = False
) -> list[str]:
    """模拟 ACP 服务进程的驱动参数。

    `-X utf8` 与 `--report`/`--state` 都以 `-` 开头，正是 #75 缺陷 D1 的触发条件；
    默认用**分离写法**（原版本会 SystemExit 2），`equals_form=True` 时用推荐的等号写法。
    """
    pairs = [
        ("-X",),
        ("utf8",),
        (str(mock),),
        ("--report", str(report)),
    ]
    if state is not None:
        pairs.append(("--state", str(state)))
    pairs.extend((item,) for item in extra)

    argv: list[str] = []
    for pair in pairs:
        for index, value in enumerate(pair):
            if equals_form and index == 0:
                argv.append(f"--server-arg={value}")
            else:
                argv.append("--server-arg")
                argv.append(value)
    return ["--server-command", sys.executable, *argv]


def same_path(left, right) -> bool:
    """Windows 上临时目录可能带 8.3 短名，路径比较统一走 resolve()。"""
    return Path(left).resolve() == Path(right).resolve()


def precheck_module():
    """取驱动调用时真正会 import 到的 `dsh_talk_precheck` 模块对象。

    `tests/test_dsh_talk_entry.py` 会用 importlib 重新加载脚本并**替换**
    `sys.modules["dsh_talk_precheck"]`；驱动内部是调用时才 import，所以测试必须
    按 `sys.modules` 取当前对象，否则整套跑时 patch 会落在旧对象上而失效。
    """
    return sys.modules["dsh_talk_precheck"]


class AcpMockTestCase(unittest.TestCase):
    """共用：临时目录、模拟 ACP 进程、驱动调用入口。"""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-acp-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.workspace = self.root / "会话 工作区 with spaces"
        self.workspace.mkdir()
        self.mock = _write_script(self.root, "mock_acp.py", MOCK_ACP_SOURCE)
        self.report_path = self.root / "mock-report.jsonl"
        self.state_path = self.root / "mock-state.json"

    def driver(self, argv: list[str]) -> tuple[int, dict, str]:
        """在进程内运行薄驱动，返回 (退出码, stdout 解析出的 JSON, stderr 文本)。"""
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = dsh_acp_drive.main(argv)
        payload = {}
        for line in stdout.getvalue().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
        return code, payload, stderr.getvalue()

    def server_args(self, *extra: str) -> list[str]:
        return mock_server_argv(
            self.mock, self.report_path, *extra, state=self.state_path
        )

    def report(self) -> list[dict]:
        if not self.report_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def methods(self) -> list[str]:
        return [entry["method"] for entry in self.report() if entry.get("event") == "request"]


class HandshakeTests(AcpMockTestCase):
    def test_handshake_reports_capabilities_and_zero_model_calls(self):
        code, payload, stderr = self.driver(
            ["handshake", *self.server_args(), "--with-list", "--cwd", str(self.workspace)]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["model_calls"], 0)
        initialize = payload["initialize"]
        self.assertEqual(initialize["protocolVersion"], 1)
        self.assertEqual(initialize["agentInfo"]["name"], "mock-dsh-acp")
        self.assertEqual(initialize["sessionCapabilities"], ["close", "list", "resume"])
        self.assertIn("sessionCount", initialize)
        self.assertEqual(self.methods(), ["initialize", "session/list"])

    def test_downstream_hyphen_args_really_reach_the_child_process(self):
        """D1 的真实验证：分离写法 `--server-arg -X` 必须把 `-X utf8` 交给下游 Python。"""
        code, _payload, stderr = self.driver(
            ["handshake", *self.server_args(), "--cwd", str(self.workspace)]
        )
        self.assertEqual(code, 0, stderr)
        startup = [entry for entry in self.report() if entry.get("event") == "startup"]
        self.assertEqual(len(startup), 1)
        orig = startup[0]["orig_argv"]
        self.assertEqual(orig[1:4], ["-X", "utf8", str(self.mock)])
        self.assertIn(str(self.report_path), orig)
        self.assertTrue(startup[0]["utf8_mode"], startup[0])

    def test_equals_form_is_accepted_for_hyphen_values(self):
        """等号写法是推荐合同，必须与分离写法等价。"""
        code, _payload, stderr = self.driver(
            [
                "handshake",
                *mock_server_argv(self.mock, self.report_path, equals_form=True),
                "--cwd",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 0, stderr)
        startup = [entry for entry in self.report() if entry.get("event") == "startup"]
        self.assertEqual(startup[0]["orig_argv"][1:4], ["-X", "utf8", str(self.mock)])
        self.assertTrue(startup[0]["utf8_mode"], startup[0])
        self.assertEqual(self.methods(), ["initialize"])

    def test_missing_server_arg_value_is_a_usage_error_without_spawning(self):
        """负例：`--server-arg` 后没有值必须按用法错误退出，且不启动任何子进程。"""
        code, _payload, stderr = self.driver(
            ["handshake", "--server-command", sys.executable, "--server-arg", str(self.mock), "--server-arg"]
        )
        self.assertEqual(code, 2)
        self.assertIn("expected one argument", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(self.report(), [])

    def test_hyphen_value_colliding_with_a_drive_option_is_refused(self):
        """负例：与驱动选项同名的值不会被静默当下游参数吞掉。"""
        code, _payload, stderr = self.driver(
            ["handshake", "--server-arg", "--cwd", str(self.workspace)]
        )
        self.assertEqual(code, 2)
        self.assertIn("expected one argument", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(self.report(), [])

    def test_handshake_fails_when_resume_capability_is_missing(self):
        code, payload, stderr = self.driver(
            [
                "handshake",
                *self.server_args("--no-resume-capability"),
                "--cwd",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(payload.get("ok"), True)
        self.assertIn("阶段 initialize", stderr)
        self.assertIn("sessionCapabilities.resume", stderr)
        self.assertNotIn("Traceback", stderr)


class LifecycleTests(AcpMockTestCase):
    def _lifecycle(self, *extra: str):
        return self.driver(["lifecycle", *self.server_args(), "--cwd", str(self.workspace), *extra])

    def test_lifecycle_resumes_the_same_id_and_rejects_mismatch(self):
        code, payload, stderr = self._lifecycle()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["model_calls"], 0)
        session_id = payload["session_id"]
        self.assertTrue(session_id.startswith("mock-session-"), session_id)

        stages = {entry["stage"]: entry for entry in payload["stages"]}
        # D3：活动期隐藏 → close 后可见 → resume 后再次隐藏 → 再次 close 后可见。
        self.assertFalse(stages["session/list-active-hidden-after-new"]["containsSession"])
        self.assertTrue(stages["session/list-persisted-after-close"]["containsSession"])
        self.assertTrue(stages["session/resume-cwd-mismatch-rejected"]["ok"])
        self.assertTrue(stages["session/resume-unknown-rejected"]["ok"])
        self.assertTrue(stages["session/resume"]["ok"])
        self.assertEqual(stages["session/resume"]["sessionId"], session_id)
        self.assertTrue(stages["session/resume-duplicate-rejected"]["ok"])
        self.assertFalse(stages["session/list-active-hidden-after-resume"]["containsSession"])
        self.assertTrue(stages["session/list-persisted-after-resume-close"]["containsSession"])
        self.assertEqual(
            stages["session/list-active-hidden-after-resume"]["count"],
            stages["session/list-persisted-after-close"]["count"] - 1,
        )
        self.assertTrue(payload["listed_after_close_contains_session"])
        self.assertTrue(payload["listed_after_final_close_contains_session"])

        methods = self.methods()
        # 恢复只走 session/resume：整个生命周期里 session/new 只能出现一次。
        self.assertEqual(methods.count("session/new"), 1)
        self.assertEqual(methods.count("session/resume"), 4)
        self.assertEqual(payload["server_exit_code"], 0)

    def test_mock_does_not_hide_active_sessions_unless_the_driver_asks(self):
        """模拟进程自身的协议语义（不依赖驱动断言）：new 即活动、close/resume 切换状态。

        这条用例把 #75 记录的真机语义钉在 mock 一侧，避免“按驱动预期伪造协议”：
        若 mock 忘了在 session/new 登记 active，本用例会直接失败。
        """
        client = dsh_acp_drive.AcpClient(
            [sys.executable, "-X", "utf8", str(self.mock), "--report", str(self.report_path)],
            cwd=self.workspace,
            env={**os.environ, "PYTHONUTF8": "1"},
            stderr_path=self.root / "raw.stderr.log",
            timeout=60,
        )
        client.start()
        try:
            dsh_acp_drive.stage_initialize(client)
            created = client.call("session/new", {"cwd": str(self.workspace), "mcpServers": []})
            session_id = created["sessionId"]
            self.assertNotIn(session_id, dsh_acp_drive.list_session_ids(client, self.workspace))
            client.call("session/close", {"sessionId": session_id})
            self.assertIn(session_id, dsh_acp_drive.list_session_ids(client, self.workspace))
            resumed = client.call(
                "session/resume",
                {"sessionId": session_id, "cwd": str(self.workspace), "mcpServers": []},
            )
            self.assertNotIn("sessionId", resumed)  # 真机 resume 返回里没有 sessionId
            self.assertNotIn(session_id, dsh_acp_drive.list_session_ids(client, self.workspace))
            error = client.call_expect_error(
                "session/resume",
                {"sessionId": session_id, "cwd": str(self.workspace), "mcpServers": []},
            )
            self.assertIn("already active", str(error.get("message")))
        finally:
            self.assertEqual(client.stop(), 0)

    def test_lifecycle_events_show_which_requests_were_rejected(self):
        code, payload, _stderr = self._lifecycle()
        self.assertEqual(code, 0)
        requests = [
            entry
            for entry in payload["evidence"]["requests"]
            if entry["method"] == "session/resume"
        ]
        self.assertEqual(len(requests), 4)
        mismatch = json.loads(requests[0]["params"])
        self.assertFalse(same_path(mismatch["cwd"], self.workspace))
        unknown = json.loads(requests[1]["params"])
        self.assertNotEqual(unknown["sessionId"], payload["session_id"])
        resumed = json.loads(requests[2]["params"])
        self.assertEqual(resumed["sessionId"], payload["session_id"])
        self.assertTrue(same_path(resumed["cwd"], self.workspace))
        duplicate = json.loads(requests[3]["params"])
        self.assertEqual(duplicate["sessionId"], payload["session_id"])

    def test_session_ref_is_written_without_secrets_and_not_overwritten(self):
        ref_path = self.root / "refs" / "session.json"
        code, payload, stderr = self._lifecycle("--session-ref-out", str(ref_path))
        self.assertEqual(code, 0, stderr)
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        self.assertEqual(ref["session_id"], payload["session_id"])
        self.assertTrue(same_path(ref["cwd"], self.workspace))
        self.assertEqual(ref["model_calls"], 0)
        self.assertNotIn("TALK_API_KEY", json.dumps(ref, ensure_ascii=False))

        code, _payload, stderr = self._lifecycle("--session-ref-out", str(ref_path))
        self.assertEqual(code, 1)
        self.assertIn("不覆盖", stderr)

    def test_session_new_failure_is_not_reported_as_success(self):
        code, payload, stderr = self.driver(
            [
                "lifecycle",
                *self.server_args("--fail-method", "session/new"),
                "--cwd",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(payload.get("ok"), True)
        self.assertIn("阶段 session/new", stderr)
        self.assertIn("mock failure", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_server_exit_midflight_is_reported_as_failure(self):
        code, payload, stderr = self.driver(
            [
                "lifecycle",
                *self.server_args("--exit-after", "session/list"),
                "--cwd",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(payload.get("ok"), True)
        self.assertIn("阶段 session/list", stderr)
        self.assertIn("未完成", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_request_timeout_is_reported_and_the_child_is_stopped(self):
        started = time.monotonic()
        code, payload, stderr = self.driver(
            [
                "lifecycle",
                *self.server_args("--hang-method", "initialize"),
                "--cwd",
                str(self.workspace),
                "--timeout",
                "2",
            ]
        )
        elapsed = time.monotonic() - started
        self.assertEqual(code, 1)
        self.assertNotEqual(payload.get("ok"), True)
        self.assertIn("阶段 initialize", stderr)
        self.assertIn("没有响应", stderr)
        self.assertLess(elapsed, 60)

    def test_mismatch_that_is_silently_accepted_fails_the_driver(self):
        """模拟进程若把失配当成成功，驱动必须判失败，而不是记成通过。"""
        source = MOCK_ACP_SOURCE.replace(
            '            elif cwd != self.sessions[session_id]:\n'
            '                self.error(request_id, -32602, "session cwd does not match: " + cwd)\n',
            "",
        )
        self.assertNotEqual(source, MOCK_ACP_SOURCE)
        lax_mock = _write_script(self.root, "lax_acp.py", source)
        argv = [
            "lifecycle",
            *mock_server_argv(lax_mock, self.report_path),
            "--cwd",
            str(self.workspace),
        ]
        code, _payload, stderr = self.driver(argv)
        self.assertEqual(code, 1)
        self.assertIn("本应被拒绝", stderr)


class PromptTests(AcpMockTestCase):
    def test_prompt_requires_the_explicit_model_flag(self):
        code, _payload, stderr = self.driver(
            [
                "prompt",
                *self.server_args(),
                "--cwd",
                str(self.workspace),
                "--prompt-text",
                "只读核验三例",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("--allow-model", stderr)
        # 没有 --allow-model 时子进程根本不该被启动。
        self.assertEqual(self.report(), [])

    def test_prompt_records_updates_and_rejects_permission_by_default(self):
        code, payload, stderr = self.driver(
            [
                "prompt",
                *self.server_args("--emit-permission"),
                "--cwd",
                str(self.workspace),
                "--prompt-text",
                "只读核验三例",
                "--allow-model",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["model_calls"], 1)
        self.assertEqual(payload["prompt"]["stopReason"], "end_turn")
        self.assertEqual(payload["prompt"]["agentText"], "MOCK-REPLY")
        self.assertEqual(payload["prompt"]["permissions"][0]["optionId"], "reject-once")
        permission_responses = [
            entry for entry in self.report() if entry.get("event") == "permission_response"
        ]
        self.assertEqual(len(permission_responses), 1)
        outcome = permission_responses[0]["response"]["result"]["outcome"]
        self.assertEqual(outcome, {"outcome": "selected", "optionId": "reject-once"})
        self.assertEqual(self.methods().count("session/prompt"), 1)

    def test_prompt_can_resume_a_saved_session_ref(self):
        ref_path = self.root / "refs" / "session.json"
        code, payload, stderr = self.driver(
            [
                "lifecycle",
                *self.server_args(),
                "--cwd",
                str(self.workspace),
                "--session-ref-out",
                str(ref_path),
            ]
        )
        self.assertEqual(code, 0, stderr)
        session_id = payload["session_id"]

        self.report_path.unlink()
        code, payload, stderr = self.driver(
            [
                "prompt",
                *self.server_args(),
                "--cwd",
                str(self.workspace),
                "--allow-model",
                "--resume",
                str(ref_path),
                "--prompt-text",
                "继续同一会话",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["resumed"])
        self.assertEqual(payload["session_id"], session_id)
        methods = self.methods()
        self.assertEqual(methods.count("session/new"), 0)
        self.assertEqual(methods.count("session/resume"), 1)

    def test_prompt_refuses_a_resume_ref_with_a_different_workspace(self):
        ref_path = self.root / "refs" / "session.json"
        code, _payload, stderr = self.driver(
            [
                "lifecycle",
                *self.server_args(),
                "--cwd",
                str(self.workspace),
                "--session-ref-out",
                str(ref_path),
            ]
        )
        self.assertEqual(code, 0, stderr)
        other = self.root / "另一个 工作区"
        other.mkdir()
        self.report_path.unlink()
        code, _payload, stderr = self.driver(
            [
                "prompt",
                *self.server_args(),
                "--cwd",
                str(other),
                "--allow-model",
                "--resume",
                str(ref_path),
                "--prompt-text",
                "不该被启动",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("恢复工作区与会话引用不一致", stderr)
        # 不一致必须在启动子进程之前被拒绝。
        self.assertEqual(self.report(), [])

    def test_prompt_output_never_contains_a_declared_credential(self):
        spec_path = self.root / "spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "cwd": str(self.workspace),
                    "mcpServers": [
                        {
                            "name": "talk",
                            "command": sys.executable,
                            "args": [
                                "-X",
                                "utf8",
                                str(LAUNCHER),
                                "--project-root",
                                str(PROJECT_ROOT),
                            ],
                            "env": [
                                {"name": "PYTHONUTF8", "value": "1"},
                                {"name": "TALK_API_KEY", "value": PLACEHOLDER_KEY},
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        code, payload, stderr = self.driver(
            [
                "prompt",
                *self.server_args(),
                "--cwd",
                str(self.workspace),
                "--allow-model",
                "--session-spec",
                str(spec_path),
                "--prompt-text",
                "只读核验三例",
            ]
        )
        self.assertEqual(code, 0, stderr)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(PLACEHOLDER_KEY, serialized)
        self.assertNotIn(PLACEHOLDER_KEY, stderr)
        self.assertIn("<已隐藏>", serialized)
        # 驱动自己的取证里，凭据值必须已被遮蔽……
        new_request = [
            json.loads(entry["params"])
            for entry in payload["evidence"]["requests"]
            if entry["method"] == "session/new"
        ][0]
        self.assertEqual(new_request["mcpServers"][0]["name"], "talk")
        self.assertEqual(new_request["mcpServers"][0]["env"][1]["value"], "<已隐藏>")
        # ……但线上真实传过去的仍是操作者显式声明的条目（模拟进程记录了收到的原文）。
        recorded = [
            entry
            for entry in self.report()
            if entry.get("event") == "request" and entry.get("method") == "session/new"
        ]
        self.assertEqual(
            recorded[0]["params"]["mcpServers"][0]["env"],
            [
                {"name": "PYTHONUTF8", "value": "1"},
                {"name": "TALK_API_KEY", "value": PLACEHOLDER_KEY},
            ],
        )


class SpecAndOverlayTests(AcpMockTestCase):
    def test_session_template_keeps_placeholders_and_has_no_secret(self):
        text = SESSION_TEMPLATE_PATH.read_text(encoding="utf-8")
        for token in (
            "__CWD__",
            "__REPO__",
            "__PYTHON__",
            "__KEY_FILE__",
            "__SERVER__",
            "__PROJECT__",
        ):
            self.assertIn(token, text)
        self.assertNotIn("TALK_API_KEY", text)
        self.assertEqual(json.loads(text)["mcpServers"][0]["name"], "talk")

    def test_spec_renders_absolute_paths_and_only_the_key_file_path(self):
        key_file = self.root / "agent-deepseek.key"
        key_file.write_text(PLACEHOLDER_KEY + "\n", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = dsh_acp_drive.main(
                [
                    "spec",
                    "--cwd",
                    str(self.workspace),
                    "--key-file",
                    str(key_file),
                    "--server",
                    "http://127.0.0.1:8000",
                    "--project",
                    "prj_e8fe7066bbec",
                ]
            )
        self.assertEqual(code, 0, stderr.getvalue())
        spec = json.loads(stdout.getvalue())
        server = spec["mcpServers"][0]
        self.assertTrue(os.path.isabs(server["command"]))
        self.assertEqual(Path(server["args"][2]), LAUNCHER)
        env_names = [entry["name"] for entry in server["env"]]
        self.assertEqual(env_names, ["PYTHONUTF8", "TALK_DSH_KEY_FILE"])
        self.assertTrue(same_path(server["env"][1]["value"], key_file))
        self.assertNotIn(PLACEHOLDER_KEY, stdout.getvalue())

    def test_spec_refuses_in_repo_or_missing_key_file(self):
        in_repo = PROJECT_ROOT / ".tmp-tests" / f"dsh-acp-{uuid.uuid4().hex}" / "in-repo.key"
        self.addCleanup(shutil.rmtree, in_repo.parent, ignore_errors=True)
        in_repo.parent.mkdir(parents=True, exist_ok=True)
        in_repo.write_text(PLACEHOLDER_KEY + "\n", encoding="utf-8")
        _code, _payload, stderr = self.driver(
            ["spec", "--cwd", str(self.workspace), "--key-file", str(in_repo)]
        )
        self.assertIn("仓库内", stderr)

        _code, _payload, stderr = self.driver(
            ["spec", "--cwd", str(self.workspace), "--key-file", str(self.root / "missing.key")]
        )
        self.assertIn("找不到密钥文件", stderr)

    def test_spec_write_refuses_in_repo_target_without_flag(self):
        key_file = self.root / "agent-deepseek.key"
        key_file.write_text(PLACEHOLDER_KEY + "\n", encoding="utf-8")
        target = PROJECT_ROOT / ".tmp-tests" / f"dsh-acp-{uuid.uuid4().hex}" / "session.json"
        self.addCleanup(shutil.rmtree, target.parent, ignore_errors=True)
        _code, _payload, stderr = self.driver(
            [
                "spec",
                "--cwd",
                str(self.workspace),
                "--key-file",
                str(key_file),
                "--write",
                str(target),
            ]
        )
        self.assertIn("仓库内", stderr)
        self.assertFalse(target.exists())
        _code, payload, stderr = self.driver(
            [
                "spec",
                "--cwd",
                str(self.workspace),
                "--key-file",
                str(key_file),
                "--write",
                str(target),
                "--allow-in-repo",
            ]
        )
        self.assertEqual(_code, 0, stderr)
        self.assertTrue(target.is_file())
        self.assertTrue(same_path(payload["written"], target))

    def test_overlay_keeps_narrowing_rows_and_never_inserts_mcp(self):
        text = OVERLAY_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertEqual(text.count("disabled: true"), 13)
        for row in ("tool-subagent", "tool-pwsh", "tool-bash", "tool-ralph"):
            self.assertIn(row, text)
        self.assertIn("mode: read-only", text)
        # D2：read-only + approval: never 不匹配任何 ACP preset，真实 session/new 报
        # -32603 match no preset；覆盖层因此不再覆盖 approval，保留 DSH 默认的 ask。
        rows = [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("- id:")]
        self.assertNotIn("approval", rows)
        self.assertIn("sandbox-policy", rows)
        active_lines = [
            line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")
        ]
        self.assertNotIn("policy: never", "\n".join(active_lines))
        self.assertNotIn("danger-full-access", "\n".join(active_lines))
        # ACP 的 MCP 是按会话声明的：覆盖层不应再 insert 任何 MCP 条目。
        self.assertNotIn("insert:", text)
        self.assertNotIn("@deepseek-ai/dsh-mcp-client", text)
        self.assertNotIn("TALK_API_KEY", text)

    def test_dump_passes_the_requested_profile_and_defaults_to_headless(self):
        fake_dsh = _write_script(
            self.root,
            "fake_dsh.py",
            "# -*- coding: utf-8 -*-\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "argv = sys.argv[1:]\n"
            "Path(os.environ['FAKE_DSH_REPORT']).write_text(json.dumps(argv, ensure_ascii=False), encoding='utf-8')\n"
            "patch = argv[argv.index('--patch') + 1]\n"
            "Path(patch).read_text(encoding='utf-8')\n"
            "print('- id: @deepseek-ai/dsh-mcp-client')\n"
            "print('- id: read-only')\n",
        )
        patch_file = self.root / "overlay.yml"
        patch_file.write_text("- id: tool-pwsh\n  disabled: true\n", encoding="utf-8")
        report = self.root / "fake-dsh-argv.json"
        command = [sys.executable, "-X", "utf8", str(fake_dsh)]
        for profile, expected in (("acp", "acp"), (None, "headless")):
            with self.subTest(profile=profile):
                argv = [
                    "dump",
                    "--patch",
                    str(patch_file),
                    "--dsh-home",
                    str(self.root / "dsh-home"),
                    "--out",
                    str(self.root / f"dump-{expected}.yml"),
                ]
                if profile:
                    argv += ["--profile", profile]
                with patch.object(
                    dsh_talk_precheck, "resolve_dsh_command", return_value=command
                ), patch.dict(os.environ, {"FAKE_DSH_REPORT": str(report)}):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = dsh_talk_precheck.main(argv)
                self.assertEqual(code, 0, stderr.getvalue())
                recorded = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(recorded[recorded.index("--profile") + 1], expected)
                self.assertEqual(json.loads(stdout.getvalue())["profile"], expected)


class ServerArgContractTests(AcpMockTestCase):
    """D1 的合同层验证：解析结果、DSH 参数顺序、真实子进程收到的事实。

    这些用例只启动**不使用 stdio 管道**的子进程（探针把事实写进 JSON 文件），
    因此在宿主禁止管道的环境里也能真实执行。
    """

    def setUp(self) -> None:
        super().setUp()
        self.probe = _write_script(self.root, "argv_probe.py", ARGV_PROBE_SOURCE)
        self.probe_out = self.root / "argv-probe.json"

    def _resolve(self, argv: list[str]):
        parser = dsh_acp_drive.build_parser()
        parsed = parser.parse_args(dsh_acp_drive.normalize_dash_values(argv, parser))
        return dsh_acp_drive.resolve_server_argv(parsed)

    def _run_probe(self, argv: list[str]) -> dict:
        env = {key: value for key, value in os.environ.items() if key != "PYTHONUTF8"}
        subprocess.run(argv, check=True, env=env)  # 继承 stdio：不使用管道
        return json.loads(self.probe_out.read_text(encoding="utf-8"))

    def test_separated_and_equals_forms_both_deliver_python_utf8_flags(self):
        for equals_form in (False, True):
            with self.subTest(equals_form=equals_form):
                self.probe_out.unlink(missing_ok=True)
                argv = self._resolve(
                    [
                        "handshake",
                        *mock_server_argv(
                            self.probe, self.probe_out, equals_form=equals_form
                        ),
                    ]
                )
                self.assertEqual(
                    argv, [sys.executable, "-X", "utf8", str(self.probe), "--report", str(self.probe_out)]
                )
                recorded = self._run_probe(argv)
                self.assertEqual(recorded["orig_argv"][1:4], ["-X", "utf8", str(self.probe)])
                # 探针进程没有 PYTHONUTF8：utf8_mode 为真只可能来自真的收到了 -X utf8。
                self.assertIsNone(recorded["python_utf8_env"])
                self.assertTrue(recorded["utf8_mode"], recorded)

    def test_dsh_profile_and_patch_keep_hyphen_args_in_order(self):
        patch_file = self.root / "overlay.yml"
        patch_file.write_text("- id: tool-pwsh\n  disabled: true\n", encoding="utf-8")
        resolved_patch = str(patch_file.resolve())  # 驱动会把 --patch 绝对化后再传下游
        fake_dsh = [sys.executable, "-X", "utf8", str(self.probe)]
        with patch.object(precheck_module(), "resolve_dsh_command", return_value=fake_dsh):
            argv = self._resolve(
                [
                    "handshake",
                    "--patch",
                    str(patch_file),
                    "--profile",
                    "acp",
                    "--server-arg",
                    "-X",
                    "--server-arg",
                    "utf8",
                    "--server-arg",
                    "--report",
                    "--server-arg",
                    str(self.probe_out),
                ]
            )
        self.assertEqual(
            argv,
            [
                *fake_dsh,
                "--profile",
                "acp",
                "--patch",
                resolved_patch,
                "-X",
                "utf8",
                "--report",
                str(self.probe_out),
            ],
        )
        recorded = self._run_probe(argv)
        self.assertEqual(recorded["argv"][1:5], ["--profile", "acp", "--patch", resolved_patch])
        self.assertEqual(recorded["orig_argv"][1:4], ["-X", "utf8", str(self.probe)])
        self.assertTrue(recorded["utf8_mode"], recorded)

    def test_drive_option_names_are_not_swallowed_as_server_args(self):
        """与驱动选项同名（或本身是选项）的值必须报用法错误，而不是被当成下游参数。"""
        parser = dsh_acp_drive.build_parser()
        options = dsh_acp_drive.drive_option_strings(parser)
        for name in ("--server-arg", "--mcp-server-arg", "--cwd", "--patch", "--with-list"):
            self.assertIn(name, options)
        normalized = dsh_acp_drive.normalize_dash_values(
            ["handshake", "--server-arg", "--cwd", "--server-arg", "--report", "x", "--server-arg", "-X"],
            parser,
        )
        self.assertEqual(
            normalized,
            ["handshake", "--server-arg", "--cwd", "--server-arg=--report", "x", "--server-arg=-X"],
        )


class AcpDriveMcpCredentialTests(RouteTestCase):
    """隔离 TALK 服务上验证“ACP 声明的 env 才到达 MCP 子进程”。"""

    def setUp(self) -> None:
        super().setUp()
        self.add_member("human:requester", api_key="requester-key", display_name="任务请求者")
        self.add_member("agent:worker", api_key="worker-key", display_name="开发角色")
        self.workspace = self._tmpdir / "ACP 工作区 with spaces"
        self.workspace.mkdir()
        self.mock = _write_script(self._tmpdir, "mock_acp.py", MOCK_ACP_SOURCE)
        self.report_path = self._tmpdir / "mock-report.jsonl"
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "requester-key"},
                json={"project_id": "prj_acp", "display_name": "ACP 验证"},
            ).raise_for_status()
            client.post(
                "/api/projects/prj_acp/sync",
                headers={"X-API-Key": "requester-key"},
                json={"agents": [{"member_id": "agent:worker", "business_role": "dev"}]},
            ).raise_for_status()

    def _spec(self, base_url: str, *, key_file: Path | None, drop_key_env: bool = False) -> dict:
        env = [{"name": "PYTHONUTF8", "value": "1"}]
        if not drop_key_env:
            env.append({"name": "TALK_DSH_KEY_FILE", "value": str(key_file)})
        return {
            "cwd": str(self.workspace),
            "mcpServers": [
                {
                    "name": "talk",
                    "command": sys.executable,
                    "args": [
                        "-X",
                        "utf8",
                        str(LAUNCHER),
                        "--server",
                        base_url,
                        "--project",
                        "prj_acp",
                    ],
                    "env": env,
                }
            ],
        }

    def _server_args(self, *extra: str) -> list[str]:
        return mock_server_argv(self.mock, self.report_path, *extra)

    def _run(self, argv: list[str]) -> tuple[int, dict, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = dsh_acp_drive.main(argv)
        payload = {}
        for line in stdout.getvalue().splitlines():
            if line.strip():
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
        return code, payload, stderr.getvalue()

    def _report(self) -> list[dict]:
        if not self.report_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_declared_env_reaches_the_mcp_child_and_tools_are_reachable(self):
        # 夹具位置（#77 返工）：假密钥必须放在**仓库外**的系统临时目录里，并显式解析
        # 确认。旧夹具把密钥写在仓库内 `.tmp-tests`（tests/test_support.py 的临时根），
        # `scripts/dsh_talk_mcp_launch.py` 按设计拒绝仓库内密钥文件，导致 session/new
        # 报 -32602；用例退出时由 finally 清理该目录。
        with outside_repo_key_file("requester-key\n") as key_file:
            self.assertFalse(
                key_file.is_relative_to(PROJECT_ROOT.resolve()),
                f"测试假密钥必须位于仓库外：{key_file}",
            )
            with LiveTalkServer(server_main.app) as base_url:
                spec_path = self._tmpdir / "spec.json"
                spec_path.write_text(
                    json.dumps(self._spec(base_url, key_file=key_file), ensure_ascii=False),
                    encoding="utf-8",
                )
                # 父进程环境里放一个**假**密钥：清洗后不应该出现在 MCP 子进程环境里。
                with patch.dict(os.environ, {"TALK_API_KEY": "parent-env-should-be-scrubbed"}):
                    code, payload, stderr = self._run(
                        [
                            "prompt",
                            *self._server_args("--probe-mcp", "--call-mcp-tool", "talk_list_agents"),
                            "--cwd",
                            str(self.workspace),
                            "--allow-model",
                            "--session-spec",
                            str(spec_path),
                            "--prompt-text",
                            "只读核验三例",
                        ]
                    )
        self.assertEqual(code, 0, stderr)
        entries = self._report()
        child_env = [entry for entry in entries if entry.get("event") == "mcp_child_env"]
        self.assertEqual(len(child_env), 1)
        self.assertIn("TALK_DSH_KEY_FILE", child_env[0]["names"])
        self.assertFalse(child_env[0]["has_parent_key"], child_env[0])
        probe = [entry for entry in entries if entry.get("event") == "mcp_probe"]
        self.assertEqual(len(probe), 1)
        self.assertEqual(sorted(probe[0]["tools"]), sorted(EXPECTED_TOOLS))
        call = probe[0]["call"]
        self.assertIsNotNone(call, probe[0])
        self.assertFalse(call["result"]["isError"], call)
        agents = json.loads(call["result"]["content"][0]["text"])["agents"]
        self.assertEqual([item["member_id"] for item in agents], ["agent:worker"])
        # 密钥正文不出现在驱动输出与子进程 stderr 摘要里。
        self.assertNotIn("requester-key", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("requester-key", probe[0]["stderr_tail"])

    def test_missing_key_source_makes_session_new_fail_loudly(self):
        with LiveTalkServer(server_main.app) as base_url:
            spec_path = self._tmpdir / "spec-no-key.json"
            spec_path.write_text(
                json.dumps(
                    self._spec(base_url, key_file=None, drop_key_env=True), ensure_ascii=False
                ),
                encoding="utf-8",
            )
            # 本用例断言“没有声明任何密钥来源”。必须同时隔离宿主家目录：否则启动器
            # 会回落到 `~/.talk/agent-deepseek.key`，在真实机器上等于读取用户的正式
            # 凭证文件；指向仓库外的空临时目录后，该默认位置必定不存在。
            with outside_repo_temp_dir(prefix="dsh-acp-home-") as home:
                with patch.dict(
                    os.environ,
                    {
                        "TALK_API_KEY": "parent-env-should-be-scrubbed",
                        "USERPROFILE": str(home),
                        "HOME": str(home),
                    },
                ):
                    code, payload, stderr = self._run(
                        [
                            "lifecycle",
                            *self._server_args("--probe-mcp"),
                            "--cwd",
                            str(self.workspace),
                            "--session-spec",
                            str(spec_path),
                        ]
                    )
        self.assertEqual(code, 1)
        self.assertNotEqual(payload.get("ok"), True)
        self.assertIn("阶段 session/new", stderr)
        # 模拟进程复现 failOnStartupError：MCP 起不来时 session/new 必须报错。
        self.assertIn("mcpServers[0] failed to start", stderr)
        self.assertNotIn("Traceback", stderr)
        probe = [entry for entry in self._report() if entry.get("event") == "mcp_probe"]
        self.assertEqual(probe[0]["tools"], [])
        self.assertIn("密钥", probe[0]["stderr_tail"])


if __name__ == "__main__":
    unittest.main()
