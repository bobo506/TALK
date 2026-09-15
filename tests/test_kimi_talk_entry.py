# -*- coding: utf-8 -*-
"""`scripts/kimi_talk_mcp_launch.py` 与 `scripts/kimi_talk_precheck.py` 的针对性测试。

覆盖 L1-1 的验收点：

- 模板/生成配置只有真实绝对路径，不含密钥正文，密钥文件位置必须在仓库外；
- 写盘默认拒绝覆盖、拒绝未确认的 git 工作区；
- 启动器按环境变量 > 密钥文件的顺序取密钥，错误文案是中文且不回显密钥；
- 身份核对能挡住“用别的成员（如 human:bobo）凭证冒充 agent:kimi”；
- 按配置真实拉起 stdio MCP 时能看到九个工具，且包含 `talk_get_delivery`。

除最后一个隔离服务用例以外，全部离线；不启动模型、不写生产数据、不做长等待。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import server.main as server_main
from cli.talk import scaffold_project
from tests.test_support import RouteTestCase
from tests.test_talk_client import LiveTalkServer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_PATH = PROJECT_ROOT / "scripts" / "kimi_talk_mcp_launch.py"
PRECHECK_PATH = PROJECT_ROOT / "scripts" / "kimi_talk_precheck.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kimi_talk_mcp_launch = _load_module("kimi_talk_mcp_launch", LAUNCHER_PATH)
kimi_talk_precheck = _load_module("kimi_talk_precheck", PRECHECK_PATH)


class ConfigGenerationTests(unittest.TestCase):
    def test_generated_config_uses_real_paths_and_no_secret(self):
        config = kimi_talk_precheck.build_mcp_config(project_root=PROJECT_ROOT)
        entry = config["mcpServers"]["talk"]
        self.assertEqual(Path(entry["command"]), kimi_talk_precheck.default_python(PROJECT_ROOT))
        self.assertTrue(Path(entry["command"]).is_file())
        self.assertEqual(Path(entry["args"][0]), (PROJECT_ROOT / "scripts" / "kimi_talk_mcp_launch.py"))
        self.assertEqual(entry["args"][1:], ["--project-root", str(PROJECT_ROOT)])
        self.assertEqual(Path(entry["cwd"]), PROJECT_ROOT)
        self.assertGreaterEqual(entry["toolTimeoutMs"], 660000)
        self.assertEqual(entry["startupTimeoutMs"], 30000)
        # 密钥只能以“仓库外文件路径”的形式出现。
        key_file = Path(entry["env"]["TALK_KIMI_KEY_FILE"])
        with self.assertRaises(ValueError):
            key_file.relative_to(PROJECT_ROOT)
        text = kimi_talk_precheck.config_text(config)
        self.assertNotIn("TALK_API_KEY", text)
        for marker in ("sk-", "Bearer ", "ghp_"):
            self.assertNotIn(marker, text)

    def test_template_file_is_not_a_live_config(self):
        template_path = PROJECT_ROOT / "deploy" / "kimi-code" / "mcp.talk.template.json"
        data = json.loads(template_path.read_text(encoding="utf-8"))
        entry = data["mcpServers"]["talk"]
        self.assertTrue(entry["command"].startswith("<"))
        self.assertNotIn("TALK_API_KEY", entry.get("env", {}))

    def test_write_config_refuses_overwrite_and_unconfirmed_git_workspace(self):
        config = kimi_talk_precheck.build_mcp_config(project_root=PROJECT_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "会话工作区 with spaces"
            workspace.mkdir()
            target = kimi_talk_precheck.write_mcp_config(config, workspace=workspace)
            self.assertEqual(target, workspace.resolve() / ".kimi-code" / "mcp.json")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), config)
            with self.assertRaises(kimi_talk_precheck.PrecheckError) as ctx:
                kimi_talk_precheck.write_mcp_config(config, workspace=workspace)
            self.assertIn("--force", str(ctx.exception))

            git_workspace = Path(directory) / "git-工作区"
            (git_workspace / ".git").mkdir(parents=True)
            with self.assertRaises(kimi_talk_precheck.PrecheckError) as ctx:
                kimi_talk_precheck.write_mcp_config(config, workspace=git_workspace)
            self.assertIn("git", str(ctx.exception))
            self.assertTrue(
                kimi_talk_precheck.write_mcp_config(
                    config, workspace=git_workspace, allow_git_workspace=True
                ).is_file()
            )


class ApiKeyResolutionTests(unittest.TestCase):
    def test_environment_wins_over_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / "agent-kimi.key"
            key_file.write_text("file-key\n", encoding="utf-8")
            env = {"TALK_API_KEY": "env-key", "TALK_KIMI_KEY_FILE": str(key_file)}
            key, source = kimi_talk_mcp_launch.resolve_api_key(
                repo_root=PROJECT_ROOT, environ=env
            )
            self.assertEqual(key, "env-key")
            self.assertEqual(source, "环境变量 TALK_API_KEY")
            self.assertNotIn("env-key", source)

    def test_key_file_is_used_and_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / "agent-kimi.key"
            key_file.write_text("\n  \nfile-key\nsecond-line\n", encoding="utf-8")
            key, source = kimi_talk_mcp_launch.resolve_api_key(
                repo_root=PROJECT_ROOT, environ={"TALK_KIMI_KEY_FILE": str(key_file)}
            )
            self.assertEqual(key, "file-key")
            self.assertIn(str(key_file.resolve()), source)
            self.assertNotIn("file-key", source)

    def test_bom_prefixed_key_file_is_tolerated_and_invalid_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            # Windows PowerShell 5.1 的 `Set-Content -Encoding utf8` 会写 BOM：
            # 必须剥掉，否则 HTTP 头按 latin-1 编码时报出难懂的编码错误。
            bom_file = Path(directory) / "bom.key"
            bom_file.write_bytes(b"\xef\xbb\xbffile-key\n")
            key, _source = kimi_talk_mcp_launch.resolve_api_key(
                repo_root=PROJECT_ROOT, environ={"TALK_KIMI_KEY_FILE": str(bom_file)}
            )
            self.assertEqual(key, "file-key")

            bad_file = Path(directory) / "bad.key"
            bad_file.write_text("key with spaces\n", encoding="utf-8")
            with self.assertRaises(kimi_talk_mcp_launch.KimiEntryError) as ctx:
                kimi_talk_mcp_launch.resolve_api_key(
                    repo_root=PROJECT_ROOT, environ={"TALK_KIMI_KEY_FILE": str(bad_file)}
                )
            self.assertIn("可打印 ASCII", str(ctx.exception))
            self.assertNotIn("key with spaces", str(ctx.exception))

    def test_missing_empty_and_in_repo_key_files_give_chinese_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.key"
            with self.assertRaises(kimi_talk_mcp_launch.KimiEntryError) as ctx:
                kimi_talk_mcp_launch.resolve_api_key(
                    repo_root=PROJECT_ROOT, environ={"TALK_KIMI_KEY_FILE": str(missing)}
                )
            self.assertIn("未找到密钥文件", str(ctx.exception))

            empty = Path(directory) / "empty.key"
            empty.write_text("\n\n", encoding="utf-8")
            with self.assertRaises(kimi_talk_mcp_launch.KimiEntryError) as ctx:
                kimi_talk_mcp_launch.resolve_api_key(
                    repo_root=PROJECT_ROOT, environ={"TALK_KIMI_KEY_FILE": str(empty)}
                )
            self.assertIn("密钥文件为空", str(ctx.exception))

            fake_repo = Path(directory) / "repo"
            fake_repo.mkdir()
            inside = fake_repo / "leaked.key"
            inside.write_text("in-repo-key\n", encoding="utf-8")
            with self.assertRaises(kimi_talk_mcp_launch.KimiEntryError) as ctx:
                kimi_talk_mcp_launch.resolve_api_key(
                    repo_root=fake_repo, environ={"TALK_KIMI_KEY_FILE": str(inside)}
                )
            self.assertIn("仓库内", str(ctx.exception))
            self.assertNotIn("in-repo-key", str(ctx.exception))


class IdentityGuardTests(unittest.TestCase):
    def test_foreign_member_and_project_are_rejected(self):
        report = {"ok": True, "member_id": "human:bobo", "project_id": "prj_other"}
        problems = kimi_talk_precheck.assert_identity(
            report, expect_member="agent:kimi", expect_project="prj_e8fe7066bbec"
        )
        self.assertEqual(len(problems), 2)
        self.assertIn("human:bobo", problems[0])
        self.assertIn("agent:kimi", problems[0])
        self.assertIn("prj_other", problems[1])

    def test_matching_identity_passes(self):
        report = {"ok": True, "member_id": "agent:kimi", "project_id": "prj_e8fe7066bbec"}
        self.assertEqual(
            kimi_talk_precheck.assert_identity(
                report, expect_member="agent:kimi", expect_project="prj_e8fe7066bbec"
            ),
            [],
        )
        self.assertEqual(
            kimi_talk_precheck.assert_identity(
                {"ok": False, "member_id": "agent:kimi", "project_id": "prj_x"},
                expect_member="agent:kimi",
                expect_project=None,
            ),
            ["连接检查未返回 ok=true"],
        )

    def test_check_mode_fails_without_credential_and_prints_no_traceback(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"TALK_PROJECT_ID": "prj_e8fe7066bbec"}, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = kimi_talk_precheck.main(["check", "--project-root", str(PROJECT_ROOT)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("TALK_API_KEY 未设置", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class StdioProbeTests(unittest.TestCase):
    def test_probe_lists_nine_tools_including_delivery_over_stdio(self):
        report = kimi_talk_precheck.run_probe(
            config_path=None,
            project_root=PROJECT_ROOT,
            python_executable=None,
            key_file=None,
            timeout=90,
        )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["returncode"], 0, report["stderr"])
        self.assertEqual(report["server_info"]["name"], "talk_tools_mcp")
        self.assertEqual(report["tool_count"], 9)
        self.assertIn("talk_get_delivery", report["tools"])
        self.assertIn("talk_collect_result", report["tools"])
        self.assertIn("talk_wait_tasks", report["tools"])
        # 工具发现不等于身份验证，也不代表真实主控闭环。
        self.assertFalse(report["identity_verified"])
        self.assertNotIn(kimi_talk_precheck.PLACEHOLDER_KEY, json.dumps(report, ensure_ascii=False))

    def test_probe_uses_the_written_config_entry(self):
        config = kimi_talk_precheck.build_mcp_config(project_root=PROJECT_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "mcp.json"
            target.write_text(kimi_talk_precheck.config_text(config), encoding="utf-8")
            report = kimi_talk_precheck.run_probe(
                config_path=target,
                project_root=Path(directory),
                python_executable=None,
                key_file=None,
                timeout=90,
            )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["tool_count"], 9)


class LiveCheckTests(RouteTestCase):
    """用隔离服务验证真实身份核对，不触碰生产数据。"""

    def setUp(self):
        super().setUp()
        self.add_member("human:bobo", api_key="bobo-key", display_name="项目管理者")
        self.add_member("agent:kimi", api_key="kimi-key", display_name="Kimi Reviewer")
        self.project_root = self._tmpdir / "kimi 工作区 with spaces"
        self.project_root.mkdir()

    def _prepare_project(self, base_url: str) -> None:
        with self.make_client() as client:
            client.post("/api/projects", headers={"X-API-Key": "bobo-key"}, json={
                "project_id": "prj_kimi_entry", "display_name": "Kimi 入口验证",
            }).raise_for_status()
            client.post("/api/projects/prj_kimi_entry/sync", headers={"X-API-Key": "bobo-key"}, json={
                "agents": [{"member_id": "agent:kimi", "business_role": "reviewer"}],
            }).raise_for_status()
        scaffold_project(
            self.project_root,
            display_name="Kimi 入口验证",
            project_id="prj_kimi_entry",
            server_url=base_url,
        )

    def test_check_accepts_own_identity_and_blocks_foreign_credential(self):
        with LiveTalkServer(server_main.app) as base_url:
            self._prepare_project(base_url)
            env = {
                "TALK_API_KEY": "kimi-key",
                "TALK_MEMBER_ID": "agent:codex",
                "TALK_DEFERRED_FILE": str(self._tmpdir / "unexpected.jsonl"),
            }
            with patch.dict(os.environ, env, clear=True):
                report = kimi_talk_precheck.run_check(
                    project_root=self.project_root,
                    server=None,
                    project=None,
                    expect_member="agent:kimi",
                    expect_project=None,
                )
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["member_id"], "agent:kimi")
            self.assertEqual(report["project_id"], "prj_kimi_entry")
            self.assertEqual(report["agents"][0]["member_id"], "agent:kimi")

            # 拿 human:bobo 的凭证不能冒充 agent:kimi 通过。
            with patch.dict(os.environ, {**env, "TALK_API_KEY": "bobo-key"}, clear=True):
                foreign = kimi_talk_precheck.run_check(
                    project_root=self.project_root,
                    server=None,
                    project=None,
                    expect_member="agent:kimi",
                    expect_project=None,
                )
            self.assertFalse(foreign["ok"])
            self.assertEqual(foreign["member_id"], "human:bobo")
            self.assertIn("不得用其它成员", foreign["problems"][0])

    def test_check_can_take_credential_from_external_key_file(self):
        with LiveTalkServer(server_main.app) as base_url:
            self._prepare_project(base_url)
            with tempfile.TemporaryDirectory() as outside_repo:
                key_file = Path(outside_repo) / "agent-kimi.key"
                key_file.write_text("kimi-key\n", encoding="utf-8")
                with patch.dict(os.environ, {"TALK_KIMI_KEY_FILE": str(key_file)}, clear=True):
                    report = kimi_talk_precheck.run_check(
                        project_root=self.project_root,
                        server=None,
                        project=None,
                        expect_member="agent:kimi",
                        expect_project="prj_kimi_entry",
                    )
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["member_id"], "agent:kimi")
            self.assertEqual(report["project_id"], "prj_kimi_entry")


if __name__ == "__main__":
    unittest.main()
