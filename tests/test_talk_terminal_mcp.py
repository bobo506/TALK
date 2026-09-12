import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from sqlmodel import select

import server.main as server_main
from bridges import talk_task_tools
from bridges import talk_terminal_mcp as terminal
from bridges.talk_task_tools import TOOL_SCHEMAS, TalkToolError
from cli.talk import scaffold_project
from server.models import AgentTask, Message
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

ENTRY = Path(__file__).resolve().parents[1] / "bridges" / "talk_terminal_mcp.py"
STDIO_FALLBACK_MARKER = "STDIO_FALLBACK_FILE_STDIO"


def run_stdio_process(command, *, input_text, env, cwd=None, timeout=15, check=False):
    """运行 stdio MCP 子进程并取回输出。

    首选匿名管道，与真实 MCP 客户端一致；当运行沙箱禁止 CreatePipe
    （Windows 报 PermissionError / WinError 5，例如 DSH 的受限文件沙箱）时，
    退化为临时文件型 stdio。两种通道喂入同一份 JSON-RPC 文本、断言完全相同，
    只有传输方式不同；退化会在 stderr 留下 STDIO_FALLBACK_MARKER 以便如实记录。
    """
    pipe_kwargs = {
        "input": input_text,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "env": env,
        "timeout": timeout,
        "check": check,
    }
    if cwd is not None:
        pipe_kwargs["cwd"] = cwd
    try:
        return subprocess.run(list(command), **pipe_kwargs)
    except PermissionError:
        return run_stdio_process_with_files(
            command, input_text=input_text, env=env, cwd=cwd, timeout=timeout, check=check
        )


def run_stdio_process_with_files(command, *, input_text, env, cwd, timeout, check):
    """文件型 stdio 退化通道：stdin/stdout/stderr 都用普通文件，不创建任何管道。"""
    command = [str(part) for part in command]
    with tempfile.TemporaryDirectory(prefix="talk-stdio-") as tmp_name:
        workdir = Path(tmp_name)
        stdin_path = workdir / "stdin.jsonl"
        stdout_path = workdir / "stdout.jsonl"
        stderr_path = workdir / "stderr.log"
        stdin_path.write_text(input_text, encoding="utf-8")
        with stdin_path.open("r", encoding="utf-8") as stdin_handle, stdout_path.open(
            "w", encoding="utf-8"
        ) as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=stdin_handle,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=env,
                cwd=cwd,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                raise
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
    print(f"{STDIO_FALLBACK_MARKER} {command[1] if len(command) > 1 else command[0]}", file=sys.stderr)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class TerminalConfigTests(unittest.TestCase):
    def test_config_precedence_and_identity_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold_project(root, display_name="终端项目", project_id="prj_file", server_url="http://file.test")
            env = {"TALK_API_KEY": "test-secret", "TALK_MEMBER_ID": "agent:stale"}
            with patch.dict(os.environ, env, clear=True):
                args = terminal.build_parser().parse_args(["--project-root", directory])
                self.assertEqual(terminal.configure(args), ("http://file.test", "prj_file"))
                self.assertNotIn("TALK_MEMBER_ID", os.environ)
                os.environ.update(TALK_BASE_URL="http://env.test", TALK_PROJECT_ID="prj_env")
                self.assertEqual(terminal.configure(args), ("http://env.test", "prj_env"))
                args = terminal.build_parser().parse_args([
                    "--project-root", directory, "--server", "http://flag.test/", "--project", "prj_flag",
                ])
                self.assertEqual(terminal.configure(args), ("http://flag.test", "prj_flag"))

    def test_missing_config_fails_without_stdout_or_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = [
                ({}, ["--project", "prj_test"], "TALK_API_KEY"),
                ({"TALK_API_KEY": "test-secret"}, [], "project_id"),
                ({"TALK_API_KEY": "test-secret"}, ["--project-root", directory], ".talk/project.yaml"),
            ]
            for env, argv, expected in cases:
                with self.subTest(expected=expected), patch.dict(os.environ, env, clear=True):
                    output, errors = io.StringIO(), io.StringIO()
                    with patch.object(Path, "cwd", return_value=Path(directory)), patch("sys.stdout", output), patch("sys.stderr", errors):
                        self.assertEqual(terminal.main(argv), 1)
                    self.assertEqual(output.getvalue(), "")
                    self.assertIn(expected, errors.getvalue())
                    self.assertNotIn("test-secret", errors.getvalue())
                    self.assertNotIn("Traceback", errors.getvalue())

    def test_invalid_project_yaml_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".talk" / "project.yaml"
            path.parent.mkdir()
            for content in ("project_id: [", "- list", "project_id: 123"):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), patch.dict(os.environ, {"TALK_API_KEY": "secret"}, clear=True):
                    args = terminal.build_parser().parse_args(["--project-root", directory])
                    with self.assertRaises(TalkToolError):
                        terminal.configure(args)

    def test_unsafe_or_invalid_server_addresses_are_rejected(self):
        for url in ("file:///tmp/talk", "http://user:secret@host", "http://host/?key=secret", "http://host/#secret", "http://host:bad", "http://host:0"):
            with self.subTest(url=url), patch.dict(os.environ, {"TALK_API_KEY": "secret"}, clear=True):
                args = terminal.build_parser().parse_args(["--project", "prj_test", "--server", url])
                with self.assertRaises(TalkToolError):
                    terminal.configure(args)

    def test_connection_error_is_redacted_and_on_stderr(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"TALK_API_KEY": "private-key"}, clear=True), patch("sys.stdout", output), patch("sys.stderr", errors):
            with patch.object(terminal, "_api_request", side_effect=TalkToolError("无法连接 TALK API: private-key")):
                self.assertEqual(terminal.main(["--project", "prj_test", "--check"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("无法连接", errors.getvalue())
        self.assertNotIn("private-key", errors.getvalue())

    def test_wait_defaults_report_600_second_bound_and_client_timeout_hint(self):
        defaults = terminal.wait_defaults()
        self.assertEqual(defaults["default_timeout_seconds"], 600.0)
        self.assertEqual(defaults["max_timeout_seconds"], 600.0)
        self.assertGreaterEqual(defaults["recommended_client_tool_timeout_seconds"], 660.0)
        self.assertIn("660", defaults["note"])
        self.assertEqual(
            defaults["max_task_references_per_call"],
            talk_task_tools.WAIT_MAX_TASK_REFERENCES,
        )
        # 取消边界必须如实说明：同步等待不会被客户端取消立即终止，也不保证子进程随之退出。
        self.assertIn("不会立即终止程序侧等待", defaults["cancellation_note"])
        self.assertIn("不保证带走 MCP 子进程", defaults["cancellation_note"])
        self.assertIn("不改变任务状态", defaults["cancellation_note"])

    def test_wait_stats_file_sets_env_and_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stats").mkdir()
            target = root / "stats" / "wait.jsonl"
            with patch.dict(os.environ, {"TALK_API_KEY": "test-secret"}, clear=True):
                args = terminal.build_parser().parse_args([
                    "--project", "prj_test", "--wait-stats-file", str(target),
                ])
                self.assertEqual(terminal.configure(args), ("http://127.0.0.1:8000", "prj_test"))
                self.assertEqual(os.environ["TALK_WAIT_STATS_FILE"], str(target.resolve()))
            with patch.dict(os.environ, {"TALK_API_KEY": "test-secret"}, clear=True):
                args = terminal.build_parser().parse_args([
                    "--project", "prj_test",
                    "--wait-stats-file", str(root / "missing" / "wait.jsonl"),
                ])
                with self.assertRaises(TalkToolError):
                    terminal.configure(args)


class TerminalLiveTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.add_member("human:requester", api_key="requester-key", display_name="任务请求者")
        self.add_member("agent:worker", api_key="worker-key", display_name="开发角色")
        self.project_root = self._tmpdir / "普通项目 with spaces"
        self.project_root.mkdir()
        with self.make_client() as client:
            client.post("/api/projects", headers={"X-API-Key": "requester-key"}, json={
                "project_id": "prj_terminal", "display_name": "终端测试",
            }).raise_for_status()
            client.post("/api/projects/prj_terminal/sync", headers={"X-API-Key": "requester-key"}, json={
                "agents": [{"member_id": "agent:worker", "business_role": "dev"}],
            }).raise_for_status()

    def run_terminal(self, base_url, *, requests=(), extra_args=(), key="requester-key"):
        env = {name: value for name, value in os.environ.items() if not name.startswith("TALK_")}
        env.update(TALK_API_KEY=key, TALK_MEMBER_ID="agent:stale", PYTHONUTF8="1")
        # 即使继承了 bridge 环境，普通入口也不能登记无人处理的延迟消息。
        env["TALK_DEFERRED_FILE"] = str(self._tmpdir / "unexpected.jsonl")
        return run_stdio_process(
            [sys.executable, str(ENTRY), "--project-root", str(self.project_root), *extra_args],
            input_text="".join(json.dumps(request, ensure_ascii=False) + "\n" for request in requests),
            env=env,
            cwd=self.project_root,
            timeout=15,
        )

    def configure_project(self, base_url):
        scaffold_project(self.project_root, display_name="终端测试", project_id="prj_terminal", server_url=base_url)

    @staticmethod
    def call(name, arguments=None, id_=1):
        return {"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": {
            "name": name, "arguments": arguments or {},
        }}

    def results(self, process):
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        return [json.loads(line) for line in process.stdout.splitlines()]

    def payload(self, response):
        self.assertFalse(response["result"]["isError"], response)
        return json.loads(response["result"]["content"][0]["text"])

    def test_check_reads_identity_project_and_offline_roles_without_writes(self):
        with LiveTalkServer(server_main.app) as base_url:
            self.configure_project(base_url)
            process = self.run_terminal(base_url, extra_args=["--check"])
        report = self.results(process)[0]
        self.assertEqual(report["member_id"], "human:requester")
        self.assertEqual(report["project_id"], "prj_terminal")
        self.assertEqual(report["agents"], [{
            "member_id": "agent:worker", "display_name": "开发角色", "availability": "offline",
        }])
        self.assertNotIn("requester-key", process.stdout + process.stderr)
        with self.session() as session:
            self.assertEqual(session.exec(select(AgentTask)).all(), [])
            self.assertEqual(session.exec(select(Message)).all(), [])

    def test_check_reports_invalid_key_and_missing_project(self):
        with LiveTalkServer(server_main.app) as base_url:
            self.configure_project(base_url)
            for key, args, status in (
                ("invalid-private-key", ["--check"], "401"),
                ("requester-key", ["--check", "--project", "missing_project"], "404"),
            ):
                with self.subTest(status=status):
                    process = self.run_terminal(base_url, extra_args=args, key=key)
                    self.assertEqual(process.returncode, 1)
                    self.assertEqual(process.stdout, "")
                    self.assertIn(status, process.stderr)
                    self.assertNotIn(key, process.stderr)
                    self.assertNotIn("Traceback", process.stderr)

    def test_stdio_catalog_and_delegation_to_result_collection(self):
        with LiveTalkServer(server_main.app) as base_url:
            self.configure_project(base_url)
            responses = self.results(self.run_terminal(base_url, requests=[
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                self.call("talk_send", {"target": "agent:worker", "body": "不得发送"}, 3),
                self.call("talk_list_agents", id_=4),
                self.call("talk_delegate_task", {"target_member_id": "agent:worker", "content": "完成最小切片", "title": "终端委派"}, 5),
            ]))
            self.assertEqual(len(responses), 5)
            self.assertEqual({tool["name"] for tool in responses[1]["result"]["tools"]}, {tool["name"] for tool in TOOL_SCHEMAS})
            self.assertEqual(responses[2]["error"]["code"], -32601)
            self.assertFalse((self._tmpdir / "unexpected.jsonl").exists())
            self.assertEqual(self.payload(responses[3])["agents"][0]["member_id"], "agent:worker")
            task = self.payload(responses[4])
            self.assertEqual(task["project_id"], "prj_terminal")
            self.assertEqual(task["created_by"], "human:requester")
            self.assertEqual(task["workflow_status"], "assigned")

            with httpx.Client(base_url=base_url, headers={"X-API-Key": "worker-key"}, trust_env=False) as client:
                claimed = client.post(f"/api/tasks/{task['id']}/claim", json={}).json()
                result = client.post("/api/messages", json={
                    "type": "text", "content": "切片结果已完成", "group_id": task["hall_group_id"],
                })
                result.raise_for_status()
                client.post(f"/api/tasks/{task['id']}/complete", json={
                    "status": "succeeded", "result_message_id": result.json()["id"], "claim_token": claimed["claim_token"],
                }).raise_for_status()
            responses = self.results(self.run_terminal(base_url, requests=[
                self.call("talk_get_task", {"task_id": task["id"]}),
                self.call("talk_collect_result", {"task_id": task["id"]}, 2),
            ]))
            self.assertEqual(self.payload(responses[0])["task"]["workflow_status"], "submitted")
            collected = self.payload(responses[1])
            self.assertEqual(collected["task"]["workflow_status"], "completed")
            self.assertEqual(collected["result_message"]["content"], "切片结果已完成")
