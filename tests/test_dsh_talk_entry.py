# -*- coding: utf-8 -*-
"""`scripts/dsh_talk_precheck.py` 与 `scripts/dsh_talk_mcp_launch.py` 的针对性回归测试。

覆盖本片（#72 返工）的必要行为：

- `dump` 的 `--patch` 相对路径必须按**调用者目录**解析成绝对路径后再交给 DSH；
  显式绝对路径与含中文/空格的目录必须原样可用（旧实现把相对路径原样传给 DSH，
  DSH 按 `dsh_home.parent` 解析，读不到覆盖层——本文件的假 DSH 复现该路径语义）；
- 覆盖层渲染/写盘边界：只有真实绝对路径、不含密钥正文、默认拒绝写进仓库、拒绝覆盖；
- 启动器密钥解析：无密钥/仓库内密钥/BOM/空文件/非法字符，错误是中文且不回显密钥；
- 身份与项目核对：本人凭证通过，他人凭证与不符的期望项目被拒；
- 隔离 HTTP 服务上的 `check` 预检（随机端口 + 测试成员，不读生产凭证）；
- stdio 探针的工具目录、覆盖层错误传播与超时清理。

除隔离服务与 stdio 探针外全部离线；不启动模型、不读生产凭证、不写生产数据。
"""

from __future__ import annotations

import contextlib
import importlib.util
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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

import server.main as server_main
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRECHECK_PATH = PROJECT_ROOT / "scripts" / "dsh_talk_precheck.py"
LAUNCHER_PATH = PROJECT_ROOT / "scripts" / "dsh_talk_mcp_launch.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dsh_talk_precheck = _load_module("dsh_talk_precheck", PRECHECK_PATH)
dsh_talk_mcp_launch = _load_module("dsh_talk_mcp_launch_under_test", LAUNCHER_PATH)


@contextlib.contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# 假 DSH：只复现“用自己的 cwd 读 `--patch`”这条路径语义，不加载任何真实模块、不调用模型。
FAKE_DSH_SOURCE = '''# -*- coding: utf-8 -*-
"""最小伪 DSH：复现 DSH 读 --patch 的路径语义，供 dump 回归使用。"""
import json
import os
import sys
from pathlib import Path

argv = list(sys.argv[1:])


def flag_value(flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


raw_patch = flag_value("--patch") or ""
# DSH 是把自己的 cwd 与“原样的 --patch”拼起来读覆盖层的。
resolved = Path(raw_patch) if os.path.isabs(raw_patch) else Path.cwd() / raw_patch
Path(os.environ["FAKE_DSH_REPORT"]).write_text(
    json.dumps(
        {
            "argv": argv,
            "cwd": str(Path.cwd()),
            "patch_raw": raw_patch,
            "patch_resolved": str(resolved),
            "patch_is_absolute": os.path.isabs(raw_patch),
            "dsh_home": os.environ.get("DSH_HOME"),
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
if not resolved.is_file():
    print(f"dsh: failed to read overlay {resolved}: ENOENT", file=sys.stderr)
    raise SystemExit(1)
print("# 伪 DSH 组合树（仅复现 --patch 读取路径语义）")
for marker in ("@deepseek-ai/dsh-mcp-client", "mcp-talk", "read-only", "talk"):
    print(f"- id: {marker}")
raise SystemExit(0)
'''

# 睡到超时为止的子进程：只有被 kill 才不会有收尾标记文件。
SLEEPER_SOURCE = '''# -*- coding: utf-8 -*-
import atexit
import sys
import time
from pathlib import Path

marker = Path(sys.argv[1])
atexit.register(lambda: marker.write_text("finished", encoding="utf-8"))
time.sleep(30)
'''


def _write_script(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def _overlay_text(*, command: str, args: list[str] | None = None) -> str:
    payload = {
        "insert": [
            {
                "id": "mcp-talk",
                "name": dsh_talk_precheck.MCP_PLUGIN,
                "config": {
                    "serverName": "talk",
                    "transport": "stdio",
                    "command": command,
                    "args": list(args or []),
                    "env": {},
                },
            }
        ]
    }
    return yaml.safe_dump(payload, allow_unicode=True)


class ConfigGenerationTests(unittest.TestCase):
    def test_render_patch_uses_real_absolute_paths_and_keeps_isolation_rows(self):
        text = dsh_talk_precheck.render_patch(
            server="http://127.0.0.1:8000", project="prj_dsh_entry"
        )
        self.assertNotIn("__REPO__", text)
        self.assertNotIn("__PYTHON__", text)
        with tempfile.TemporaryDirectory(prefix="dsh-overlay-") as directory:
            path = _write_script(Path(directory), "patch.yml", text)
            rows = dsh_talk_precheck.load_rows(path)
            entry = dsh_talk_precheck.load_patch_entry(path)
            disabled = dsh_talk_precheck.disabled_row_ids(path)
        self.assertTrue(rows)
        self.assertEqual(Path(entry["command"]), dsh_talk_precheck.default_python())
        self.assertTrue(Path(entry["command"]).is_file())
        self.assertEqual(Path(entry["args"][2]), PRECHECK_PATH.parent / "dsh_talk_mcp_launch.py")
        self.assertEqual(
            entry["args"][3:],
            ["--server", "http://127.0.0.1:8000", "--project", "prj_dsh_entry"],
        )
        self.assertEqual(Path(entry["cwd"]), PROJECT_ROOT)
        self.assertNotIn("TALK_API_KEY", json.dumps(entry, ensure_ascii=False))
        # 覆盖层同时收窄原生工具与写权限，这些行是组合层事实而不是提示词约定。
        self.assertIn("tool-pwsh", disabled)
        self.assertIn("tool-subagent", disabled)
        self.assertEqual(len(disabled), 13)
        self.assertIn("read-only", text)

    def test_write_patch_boundaries(self):
        server = "http://127.0.0.1:8000"
        project = "prj_e8fe7066bbec"
        with tempfile.TemporaryDirectory(prefix="dsh-写盘 边界-") as directory:
            workspace = Path(directory) / "隔离 目录 with spaces"
            target = dsh_talk_precheck.write_patch(workspace / "talk-mcp.patch.yml", allow_in_repo=False)
            self.assertEqual(target, (workspace / "talk-mcp.patch.yml").resolve())
            text = target.read_text(encoding="utf-8")
            self.assertIn(server, text)
            self.assertIn(project, text)
            entry = dsh_talk_precheck.load_patch_entry(target)
            self.assertTrue(entry["command"])
            # 生成的覆盖层里只有环境变量名之外的东西：MCP 条目 env 不含任何密钥字段。
            self.assertEqual(sorted(entry.get("env") or {}), ["PYTHONUTF8"])
            self.assertFalse(
                [key for key in (entry.get("env") or {}) if "KEY" in key or "TOKEN" in key]
            )
            with self.assertRaises(dsh_talk_precheck.DshPrecheckError) as ctx:
                dsh_talk_precheck.write_patch(workspace / "talk-mcp.patch.yml", allow_in_repo=False)
            self.assertIn("不覆盖", str(ctx.exception))

            # 默认拒绝写进仓库；显式放行时才允许写进隔离临时目录。
            in_repo = PROJECT_ROOT / ".tmp-tests" / f"dsh-{uuid.uuid4().hex}" / "patch.yml"
            self.addCleanup(shutil.rmtree, in_repo.parent, ignore_errors=True)
            with self.assertRaises(dsh_talk_precheck.DshPrecheckError) as ctx:
                dsh_talk_precheck.write_patch(in_repo, allow_in_repo=False)
            self.assertIn("仓库内", str(ctx.exception))
            self.assertFalse(in_repo.exists())
            allowed = dsh_talk_precheck.write_patch(in_repo, allow_in_repo=True)
            self.assertTrue(allowed.is_file())

    def test_template_is_not_a_runnable_overlay(self):
        template = (PROJECT_ROOT / "deploy" / "dsh" / "talk-mcp.patch.template.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("__REPO__", template)
        self.assertIn("__PYTHON__", template)
        self.assertNotIn("D:/", template)
        self.assertNotIn("D:\\", template)
        self.assertNotIn("TALK_API_KEY:", template)


class DumpPathResolutionTests(unittest.TestCase):
    """`dump` 的相对路径回归：旧实现会把相对 --patch 原样交给按 dsh_home.parent 解析的 DSH。"""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-dump-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.fake_dsh = _write_script(self.root, "fake_dsh.py", FAKE_DSH_SOURCE)
        self.report_path = self.root / "fake-dsh-report.json"
        self.workdir = self.root / "会话 工作区 with spaces"
        self.patch_path = self.workdir / "review" / "talk-mcp.patch.yml"
        self.patch_path.parent.mkdir(parents=True)
        self.patch_path.write_text(
            dsh_talk_precheck.render_patch(
                server="http://127.0.0.1:8000", project="prj_e8fe7066bbec"
            ),
            encoding="utf-8",
        )
        self.dsh_home = self.workdir / "dsh-home"
        self.dsh_home.mkdir()
        # 预建 --out 的父目录：让“相对 --patch”用例只在路径解析上失败，
        # 而不是因为旧实现不会创建父目录而先失败（保持回归判据单一）。
        self.out_dir = self.workdir / "out"
        self.out_dir.mkdir()

    def _fake_command(self) -> list[str]:
        return [sys.executable, "-X", "utf8", str(self.fake_dsh)]

    def _report(self) -> dict:
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def test_relative_patch_is_resolved_against_the_calling_directory(self):
        relative_patch = Path("会话 工作区 with spaces/review/talk-mcp.patch.yml")
        with _chdir(self.root), patch.object(
            dsh_talk_precheck, "resolve_dsh_command", return_value=self._fake_command()
        ), patch.dict(os.environ, {"FAKE_DSH_REPORT": str(self.report_path)}):
            result = dsh_talk_precheck.run_dump(
                patch_path=relative_patch,
                dsh_home=Path("会话 工作区 with spaces/dsh-home"),
                out_path=Path("会话 工作区 with spaces/out/dump.yml"),
            )
        report = self._report()
        self.assertTrue(report["patch_is_absolute"], report)
        self.assertEqual(Path(report["patch_raw"]), self.patch_path.resolve())
        # 下游（伪 DSH 按自己的 cwd 解析）必须能真正读到同一个覆盖层文件。
        self.assertEqual(Path(report["patch_resolved"]), self.patch_path.resolve())
        self.assertTrue(Path(report["patch_resolved"]).is_file())
        # 隔离语义不变：子进程 cwd 仍是 dsh_home.parent。
        self.assertEqual(Path(report["cwd"]), self.dsh_home.resolve().parent)
        self.assertEqual(report["dsh_home"], str(self.dsh_home.resolve()))
        self.assertEqual(result["returncode"], 0, result["stderr_tail"])
        self.assertTrue(result["has_mcp_plugin"])
        self.assertTrue(result["has_readonly_mode"])
        self.assertEqual(Path(result["patch_path"]), self.patch_path.resolve())
        self.assertFalse((self.workdir / "out" / "dump.stderr.log").stat().st_size)

    def test_dump_cli_keeps_absolute_patch_and_reports_disabled_rows(self):
        out_path = self.workdir / "out" / "绝对 dump.yml"
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(
            dsh_talk_precheck, "resolve_dsh_command", return_value=self._fake_command()
        ), patch.dict(os.environ, {"FAKE_DSH_REPORT": str(self.report_path)}):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = dsh_talk_precheck.main(
                    [
                        "dump",
                        "--patch",
                        str(self.patch_path),
                        "--dsh-home",
                        str(self.dsh_home),
                        "--out",
                        str(out_path),
                    ]
                )
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        raw_patch = Path(self._report()["patch_raw"])
        self.assertTrue(raw_patch.is_absolute())
        # 绝对路径不做改写（只在文本形态上归一，例如 Windows 8.3 短名）。
        self.assertEqual(raw_patch.resolve(), self.patch_path.resolve())
        self.assertEqual(len(payload["disabled_rows"]), 13)
        self.assertIn("tool-pwsh", payload["disabled_rows"])
        self.assertEqual(Path(payload["out_path"]).resolve(), out_path.resolve())

    def test_dump_creates_the_missing_out_directory(self):
        out_path = self.workdir / "out" / "新目录" / "dump.yml"
        with patch.object(
            dsh_talk_precheck, "resolve_dsh_command", return_value=self._fake_command()
        ), patch.dict(os.environ, {"FAKE_DSH_REPORT": str(self.report_path)}):
            result = dsh_talk_precheck.run_dump(
                patch_path=self.patch_path, dsh_home=self.dsh_home, out_path=out_path
            )
        self.assertEqual(result["returncode"], 0, result["stderr_tail"])
        self.assertTrue(out_path.is_file())
        self.assertTrue(out_path.with_suffix(".stderr.log").is_file())

    def test_missing_patch_fails_with_chinese_error_instead_of_traceback(self):
        with _chdir(self.root):
            with self.assertRaises(dsh_talk_precheck.DshPrecheckError) as ctx:
                dsh_talk_precheck.run_dump(
                    patch_path=Path("会话 工作区 with spaces/review/missing.yml"),
                    dsh_home=Path("会话 工作区 with spaces/dsh-home"),
                    out_path=Path("会话 工作区 with spaces/out/dump.yml"),
                )
        message = str(ctx.exception)
        self.assertIn("找不到覆盖层文件", message)
        self.assertIn(str((self.workdir / "review" / "missing.yml").resolve()), message)

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = dsh_talk_precheck.main(
                [
                    "dump",
                    "--patch",
                    str(self.workdir / "review" / "missing.yml"),
                    "--dsh-home",
                    str(self.dsh_home),
                    "--out",
                    str(self.workdir / "out" / "dump.yml"),
                ]
            )
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("DSH 预检失败", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class ProbeAndOverlayTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-probe-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_overlay_errors_are_reported_in_chinese(self):
        cases = {
            "not-a-list.yml": (
                "id: tool-pwsh\ndisabled: true\n",
                "顶层必须是数组",
            ),
            "no-plugin.yml": (
                "- insert:\n    - id: other\n      name: '@other/plugin'\n      config: {}\n",
                "没有 @deepseek-ai/dsh-mcp-client 条目",
            ),
            "broken.yml": ("- insert: [\n", "不是合法 UTF-8 YAML"),
            "missing-field.yml": (
                "- insert:\n"
                "    - id: mcp-talk\n"
                "      name: '@deepseek-ai/dsh-mcp-client'\n"
                "      config:\n"
                "        serverName: talk\n"
                "        command: python\n"
                "        args: []\n",
                "缺少字段 transport",
            ),
        }
        for name, (text, expected) in cases.items():
            path = _write_script(self.root, name, text)
            with self.subTest(name=name):
                with self.assertRaises(dsh_talk_precheck.DshPrecheckError) as ctx:
                    dsh_talk_precheck.load_patch_entry(path)
                self.assertIn(expected, str(ctx.exception))

    def test_probe_lists_nine_tools_from_the_rendered_overlay(self):
        patch = dsh_talk_precheck.write_patch(
            self.root / "隔离 目录 with spaces" / "talk-mcp.patch.yml", allow_in_repo=False
        )
        config = dsh_talk_precheck.load_patch_entry(patch)
        result = dsh_talk_precheck.probe_tools(config)
        self.assertEqual(result["returncode"], 0, result["stderr_tail"])
        self.assertEqual(result["serverInfo"]["name"], "talk_tools_mcp")
        self.assertEqual(sorted(result["tools"]), sorted(dsh_talk_precheck.EXPECTED_TOOLS))
        self.assertIn("talk_get_delivery", result["tools"])
        # 探针只用占位密钥：结果里不得回显密钥正文（启动器只打印来源变量名，不打印值）。
        self.assertNotIn(dsh_talk_precheck.PLACEHOLDER_KEY, json.dumps(result, ensure_ascii=False))
        self.assertNotIn(dsh_talk_precheck.PLACEHOLDER_KEY, result["stderr_tail"])

    def test_probe_reports_missing_command_without_traceback(self):
        patch = _write_script(
            self.root,
            "missing-command.yml",
            _overlay_text(command=str(self.root / "不存在的解释器.exe")),
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = dsh_talk_precheck.main(["probe", "--patch", str(patch)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("DSH 预检失败", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_stdio_timeout_kills_the_child(self):
        marker = self.root / "sleeper-finished.txt"
        sleeper = _write_script(self.root, "sleeper.py", SLEEPER_SOURCE)
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            dsh_talk_precheck.run_stdio_requests(
                [sys.executable, "-X", "utf8", str(sleeper), str(marker)],
                env=dict(os.environ),
                cwd=self.root,
                requests=[{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}],
                timeout=1.5,
            )
        self.assertLess(time.monotonic() - started, 20)
        # 被 kill 的子进程不会执行收尾写入；否则标记文件会在 30 秒后才出现。
        time.sleep(2)
        self.assertFalse(marker.exists())


class DshLauncherCredentialTests(unittest.TestCase):
    def test_default_key_file_is_outside_the_repo_and_missing_file_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="dsh-home-") as home:
            with patch.dict(os.environ, {"USERPROFILE": home, "HOME": home}, clear=True):
                with self.assertRaises(dsh_talk_mcp_launch.DshEntryError) as ctx:
                    dsh_talk_mcp_launch.resolve_api_key(repo_root=PROJECT_ROOT)
            message = str(ctx.exception)
            self.assertIn("未找到密钥文件", message)
            self.assertIn(str(Path(home).resolve()), message)
            self.assertNotIn(str(PROJECT_ROOT), message)

    def test_repo_key_file_is_refused_and_message_hides_the_key(self):
        with tempfile.TemporaryDirectory(prefix="dsh-repo-") as directory:
            fake_repo = Path(directory) / "repo"
            fake_repo.mkdir()
            inside = fake_repo / "leaked.key"
            inside.write_text("in-repo-secret\n", encoding="utf-8")
            with self.assertRaises(dsh_talk_mcp_launch.DshEntryError) as ctx:
                dsh_talk_mcp_launch.resolve_api_key(
                    repo_root=fake_repo, environ={"TALK_DSH_KEY_FILE": str(inside)}
                )
            self.assertIn("仓库内", str(ctx.exception))
            self.assertNotIn("in-repo-secret", str(ctx.exception))

    def test_bom_blank_and_illegal_key_files(self):
        with tempfile.TemporaryDirectory(prefix="dsh-key-") as directory:
            bom = Path(directory) / "bom.key"
            bom.write_bytes(b"\xef\xbb\xbfAAAABBBBCCCC\n")
            key, source = dsh_talk_mcp_launch.resolve_api_key(
                repo_root=PROJECT_ROOT, environ={"TALK_DSH_KEY_FILE": str(bom)}
            )
            self.assertEqual(key, "AAAABBBBCCCC")
            self.assertIn("bom.key", source)
            self.assertNotIn("AAAABBBBCCCC", source)

            blank = Path(directory) / "blank.key"
            blank.write_text("\n  \n", encoding="utf-8")
            with self.assertRaises(dsh_talk_mcp_launch.DshEntryError) as ctx:
                dsh_talk_mcp_launch.resolve_api_key(
                    repo_root=PROJECT_ROOT, environ={"TALK_DSH_KEY_FILE": str(blank)}
                )
            self.assertIn("密钥文件为空", str(ctx.exception))

            illegal = Path(directory) / "illegal.key"
            illegal.write_text("key with spaces\n", encoding="utf-8")
            with self.assertRaises(dsh_talk_mcp_launch.DshEntryError) as ctx:
                dsh_talk_mcp_launch.resolve_api_key(
                    repo_root=PROJECT_ROOT, environ={"TALK_DSH_KEY_FILE": str(illegal)}
                )
            self.assertIn("可打印 ASCII", str(ctx.exception))
            self.assertNotIn("key with spaces", str(ctx.exception))

    def test_environment_key_wins_over_the_file(self):
        with tempfile.TemporaryDirectory(prefix="dsh-env-") as directory:
            key_file = Path(directory) / "agent-deepseek.key"
            key_file.write_text("file-key\n", encoding="utf-8")
            key, source = dsh_talk_mcp_launch.resolve_api_key(
                repo_root=PROJECT_ROOT,
                environ={"TALK_API_KEY": "env-key", "TALK_DSH_KEY_FILE": str(key_file)},
            )
            self.assertEqual(key, "env-key")
            self.assertEqual(source, "环境变量 TALK_API_KEY")
            self.assertNotIn("env-key", source)

    def test_launcher_main_without_credential_exits_one_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="dsh-nocred-") as home:
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"USERPROFILE": home, "HOME": home}, clear=True):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = dsh_talk_mcp_launch.main([])
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("DSH TALK 入口启动失败", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())


class LiveCheckTests(RouteTestCase):
    """用隔离服务验证身份/项目核对，不触碰生产数据与真实凭证。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="项目管理者")
        self.add_member("agent:deepseek", api_key="dsh-test-key", display_name="DeepSeek Dev")

    def _prepare_project(self) -> None:
        with self.make_client() as client:
            client.post(
                "/api/projects",
                headers={"X-API-Key": "bobo-key"},
                json={"project_id": "prj_dsh_entry", "display_name": "DSH 入口验证"},
            ).raise_for_status()
            client.post(
                "/api/projects/prj_dsh_entry/sync",
                headers={"X-API-Key": "bobo-key"},
                json={"agents": [{"member_id": "agent:deepseek", "business_role": "dev"}]},
            ).raise_for_status()

    def _test_env(self, api_key: str = "dsh-test-key") -> dict:
        """只覆盖 TALK_* 变量，不动系统环境。

        清空整个环境会让 Windows 上的子进程 Winsock 初始化失败（WinError 10106），
        那是测试写法问题而不是产品缺陷；这里改为显式覆盖：密钥用测试成员，
        密钥文件指向不存在的测试路径，即使变量缺失也读不到仓库外的真实密钥文件。
        """
        return {
            "TALK_API_KEY": api_key,
            "TALK_MEMBER_ID": "agent:codex",
            "TALK_DSH_KEY_FILE": str(self._tmpdir / "never-used.key"),
        }

    def test_check_accepts_own_credential_and_rejects_another_member(self):
        with LiveTalkServer(server_main.app) as base_url:
            self._prepare_project()
            with patch.dict(os.environ, self._test_env()):
                report = dsh_talk_precheck.run_check(
                    server=base_url,
                    project="prj_dsh_entry",
                    expect_member="agent:deepseek",
                    expect_project="prj_dsh_entry",
                    key_source={},
                )
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["report"]["member_id"], "agent:deepseek")
            self.assertEqual(report["report"]["project_id"], "prj_dsh_entry")
            # 密钥只从测试环境变量取，没有落到任何仓库外真实密钥文件。
            self.assertEqual(report["key_source"], "环境变量 TALK_API_KEY")
            # 环境里另有 TALK_MEMBER_ID 也不能改身份：身份只由密钥决定。
            self.assertEqual(report["report"]["agents"][0]["member_id"], "agent:deepseek")
            self.assertNotIn("dsh-test-key", json.dumps(report, ensure_ascii=False))

            with patch.dict(os.environ, self._test_env("bobo-key")):
                foreign = dsh_talk_precheck.run_check(
                    server=base_url,
                    project="prj_dsh_entry",
                    expect_member="agent:deepseek",
                    expect_project="prj_dsh_entry",
                    key_source={},
                )
            self.assertFalse(foreign["ok"], foreign)
            self.assertTrue(any("身份不是 agent:deepseek" in item for item in foreign["problems"]))
            self.assertNotIn("bobo-key", json.dumps(foreign, ensure_ascii=False))

    def test_check_rejects_unexpected_project_and_unknown_project(self):
        with LiveTalkServer(server_main.app) as base_url:
            self._prepare_project()
            with patch.dict(os.environ, self._test_env()):
                mismatch = dsh_talk_precheck.run_check(
                    server=base_url,
                    project="prj_dsh_entry",
                    expect_member="agent:deepseek",
                    expect_project="prj_other",
                    key_source={},
                )
                unknown = dsh_talk_precheck.run_check(
                    server=base_url,
                    project="prj_missing",
                    expect_member="agent:deepseek",
                    expect_project="prj_missing",
                    key_source={},
                )
        self.assertFalse(mismatch["ok"], mismatch)
        self.assertTrue(any("项目不是 prj_other" in item for item in mismatch["problems"]))
        self.assertFalse(unknown["ok"], unknown)
        self.assertEqual(unknown["stage"], "connect")
        self.assertNotIn("dsh-test-key", json.dumps([mismatch, unknown], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
