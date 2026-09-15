#!/usr/bin/env python3
"""Kimi Code 独立会话入口的配置生成与无模型预检。

三个子命令，互相独立，全部不启动模型、不改任务数据：

``config``
    生成可直接放进工作区 ``.kimi-code/mcp.json`` 的配置；默认只打印，
    ``--write`` 才落盘。配置里只有真实绝对路径，**不含任何密钥正文**。
``check``
    用真实 TALK 身份做只读连接检查（等价于终端入口 ``--check``），并强制核对
    “凭证对应的成员 / 项目”是否就是本次授权身份；身份不符直接判失败。
``probe``
    按配置里的 ``command`` / ``args`` / ``cwd`` 真实拉起一次 stdio MCP 子进程，
    发 ``initialize`` + ``tools/list``，核对工具目录是否包含
    ``talk_get_delivery`` 与完整结果读取能力。该步骤不发起 HTTP 请求，
    因此**不能**证明身份，输出里如实标注 ``identity_verified=false``。

退出码：0 表示该子命令通过；1 表示检查失败或配置有误；2 表示用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SERVER_NAME = "talk"
PLACEHOLDER_KEY = "precheck-local-placeholder"
STDIO_FALLBACK_MARKER = "STDIO_FALLBACK_FILE_STDIO"
TOOL_TIMEOUT_FALLBACK_MS = 660000


class PrecheckError(RuntimeError):
    """可预期的中文错误；只打印 message，不打印 traceback。"""


# ---------------------------------------------------------------------------
# 基建
# ---------------------------------------------------------------------------


def load_launcher():
    """加载同目录启动器，复用它的默认密钥文件位置。"""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import kimi_talk_mcp_launch  # noqa: PLC0415 - 延迟导入，便于脚本与测试两种入口

    return kimi_talk_mcp_launch


def recommended_tool_timeout_ms() -> int:
    """把终端入口公布的客户端建议超时换算成 mcp.json 的 ``toolTimeoutMs``。"""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from bridges.talk_task_tools import WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS

        return int(WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS * 1000)
    except Exception:  # noqa: BLE001 - 依赖缺失时退回已知常量，不阻塞配置生成
        return TOOL_TIMEOUT_FALLBACK_MS


def default_python(repo_root: Path = REPO_ROOT) -> Path:
    """优先使用仓库自带虚拟环境解释器，其次当前解释器。"""
    candidate = repo_root / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file():
        return candidate
    return Path(sys.executable)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def build_mcp_config(
    *,
    project_root: Path,
    python_executable: Path | None = None,
    key_file: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """生成 stdio MCP 条目；密钥只以“外部文件路径”形式出现。"""
    project_root = Path(project_root).expanduser().resolve()
    launcher = (repo_root / "scripts" / "kimi_talk_mcp_launch.py").resolve()
    if not launcher.is_file():
        raise PrecheckError(f"缺少启动器 {launcher}，请确认仓库完整")
    interpreter = Path(python_executable).expanduser().resolve() if python_executable else default_python(repo_root)
    if not interpreter.is_file():
        raise PrecheckError(f"找不到 Python 解释器 {interpreter}；请用 --python 指定")
    resolved_key_file = (
        Path(key_file).expanduser().resolve() if key_file else load_launcher().default_key_file()
    )
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": str(interpreter),
                "args": [
                    str(launcher),
                    "--project-root",
                    str(project_root),
                ],
                "cwd": str(project_root),
                "env": {"TALK_KIMI_KEY_FILE": str(resolved_key_file)},
                "startupTimeoutMs": 30000,
                "toolTimeoutMs": recommended_tool_timeout_ms(),
                "enabled": True,
            }
        }
    }


def config_text(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def write_mcp_config(
    config: dict,
    *,
    workspace: Path,
    force: bool = False,
    allow_git_workspace: bool = False,
) -> Path:
    """写入 ``<workspace>/.kimi-code/mcp.json``；默认拒绝覆盖与仓库内误写。"""
    workspace = Path(workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise PrecheckError(f"工作区不存在：{workspace}")
    target = workspace / ".kimi-code" / "mcp.json"
    if target.exists() and not force:
        raise PrecheckError(f"{target} 已存在；确认要覆盖时再加 --force")
    if (workspace / ".git").exists() and not allow_git_workspace:
        raise PrecheckError(
            f"{workspace} 是 git 工作区：project 级 mcp.json 会影响该工作区所有“新”Kimi 会话；"
            "确认后请追加 --allow-git-workspace"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(config_text(config), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def assert_identity(report: dict, *, expect_member: str, expect_project: str | None) -> list[str]:
    """核对凭证对应的真实身份；返回中文问题列表，空列表表示通过。"""
    problems: list[str] = []
    actual_member = str(report.get("member_id") or "")
    actual_project = str(report.get("project_id") or "")
    if expect_member and actual_member != expect_member:
        problems.append(
            f"身份不匹配：期望 {expect_member}，实际 {actual_member or '未知'}；"
            "不得用其它成员（例如 human:bobo）的凭证代替本人身份"
        )
    if expect_project and actual_project != expect_project:
        problems.append(f"项目不匹配：期望 {expect_project}，实际 {actual_project or '未知'}")
    if not report.get("ok"):
        problems.append("连接检查未返回 ok=true")
    return problems


def run_check(
    *,
    project_root: Path,
    server: str | None,
    project: str | None,
    expect_member: str,
    expect_project: str | None,
) -> dict:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import talk_terminal_mcp  # noqa: PLC0415 - 延迟导入，保持纯离线子命令可用

    if not (os.environ.get("TALK_API_KEY") or "").strip():
        # 与启动器同一套取密钥规则：环境变量优先，其次仓库外密钥文件。
        try:
            key, _source = load_launcher().resolve_api_key()
        except Exception as exc:  # noqa: BLE001 - 统一转成中文短错误
            raise PrecheckError(
                f"TALK_API_KEY 未设置，且未取到仓库外密钥文件（{exc}）；"
                "请设置 TALK_API_KEY，或用 TALK_KIMI_KEY_FILE 指向仓库外的密钥文件"
            ) from exc
        os.environ["TALK_API_KEY"] = key

    argv = ["--project-root", str(Path(project_root).expanduser().resolve())]
    if server:
        argv += ["--server", server]
    if project:
        argv += ["--project", project]
    args = talk_terminal_mcp.build_parser().parse_args(argv)
    server_url, project_id = talk_terminal_mcp.configure(args)
    report = talk_terminal_mcp.check_connection(server_url, project_id)
    problems = assert_identity(report, expect_member=expect_member, expect_project=expect_project or project_id)
    return {
        "ok": not problems,
        "mode": "check",
        "server": server_url,
        "project_id": report.get("project_id"),
        "member_id": report.get("member_id"),
        "display_name": report.get("display_name"),
        "expect_member": expect_member,
        "agents": report.get("agents"),
        "problems": problems,
        "identity_verified": not problems,
        "network_calls": "只读 GET /api/members/me 与项目角色查询",
        "note": "本步骤只做只读连接检查：不创建任务、不发消息、不改任何数据。",
    }


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def run_stdio_requests(
    command: list[str],
    *,
    env: dict,
    cwd: Path,
    requests: list[dict],
    timeout: float = 60,
) -> dict:
    """拉起 stdio MCP 子进程并取回输出。

    首选匿名管道（与真实 MCP 客户端一致）；受限沙箱禁止 CreatePipe 时
    （Windows ``PermissionError`` / ``WinError 5``）退化为文件型 stdio，
    并在 stderr 留下 ``STDIO_FALLBACK_FILE_STDIO`` 标记，两种通道喂同一份
    JSON-RPC 文本、断言完全相同。
    """
    input_text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(cwd),
            timeout=timeout,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "transport": "pipe",
        }
    except PermissionError:
        pass

    with tempfile.TemporaryDirectory(prefix="kimi-talk-probe-") as tmp_name:
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
                cwd=str(cwd),
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                raise
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
    print(f"{STDIO_FALLBACK_MARKER} {command[0]}", file=sys.stderr)
    return {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "transport": "file",
    }


def load_config_entry(config_path: Path) -> dict:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise PrecheckError(f"找不到配置文件 {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrecheckError(f"配置文件不是合法 UTF-8 JSON：{path}（{exc}）") from exc
    entry = (data.get("mcpServers") or {}).get(SERVER_NAME)
    if not isinstance(entry, dict):
        raise PrecheckError(f"配置文件缺少 mcpServers.{SERVER_NAME} 条目：{path}")
    for field in ("command", "args"):
        if field not in entry:
            raise PrecheckError(f"配置条目缺少字段 {field}：{path}")
    return entry


def run_probe(
    *,
    config_path: Path | None,
    project_root: Path,
    python_executable: Path | None,
    key_file: Path | None,
    timeout: float,
) -> dict:
    if config_path is not None:
        entry = load_config_entry(config_path)
        config_env = entry.get("env") or {}
        command = [str(entry["command"]), *[str(item) for item in entry["args"]]]
        cwd = Path(entry.get("cwd") or project_root).expanduser().resolve()
    else:
        config = build_mcp_config(
            project_root=project_root,
            python_executable=python_executable,
            key_file=key_file,
        )
        entry = config["mcpServers"][SERVER_NAME]
        config_env = entry.get("env") or {}
        command = [str(entry["command"]), *[str(item) for item in entry["args"]]]
        cwd = Path(entry["cwd"])

    # 只排除继承的 TALK_* 环境，证明工具目录不依赖 bridge 上下文；
    # 占位密钥仅存在于子进程环境，用于满足入口的非空校验，不会发起 HTTP 请求。
    env = {name: value for name, value in os.environ.items() if not name.startswith("TALK_")}
    env.update({str(k): str(v) for k, v in config_env.items()})
    env["TALK_API_KEY"] = PLACEHOLDER_KEY
    env["PYTHONUTF8"] = "1"

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    result = run_stdio_requests(command, env=env, cwd=cwd, requests=requests, timeout=timeout)
    responses = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    init = next((item for item in responses if item.get("id") == 1), None)
    catalog = next((item for item in responses if item.get("id") == 2), None)
    tools = []
    if catalog and isinstance(catalog.get("result"), dict):
        tools = [tool.get("name") for tool in catalog["result"].get("tools", [])]
    return {
        "ok": result["returncode"] == 0 and bool(tools),
        "mode": "probe",
        "command": command,
        "cwd": str(cwd),
        "transport": result["transport"],
        "returncode": result["returncode"],
        "stderr": result["stderr"].strip(),
        "server_info": (init or {}).get("result", {}).get("serverInfo"),
        "tool_count": len(tools),
        "tools": tools,
        "has_talk_get_delivery": "talk_get_delivery" in tools,
        "identity_verified": False,
        "network_calls": 0,
        "note": (
            "tools/list 只证明配置可启动且工具目录正确；本步骤用占位密钥、未访问服务端，"
            "身份必须由 check 子命令用真实凭证验证。"
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kimi Code 独立会话入口的配置生成与无模型预检")
    sub = parser.add_subparsers(dest="mode", required=True)

    config_parser = sub.add_parser("config", help="生成 mcp.json 条目（默认只打印）")
    config_parser.add_argument("--project-root", type=Path, default=REPO_ROOT, help="工作区目录（TALK 项目根）")
    config_parser.add_argument("--python", type=Path, default=None, help="解释器绝对路径；默认优先仓库 .venv")
    config_parser.add_argument("--key-file", type=Path, default=None, help="仓库外的密钥文件路径")
    config_parser.add_argument("--write", type=Path, default=None, metavar="WORKSPACE", help="写入 <WORKSPACE>/.kimi-code/mcp.json")
    config_parser.add_argument("--force", action="store_true", help="允许覆盖已存在的 mcp.json")
    config_parser.add_argument(
        "--allow-git-workspace",
        action="store_true",
        help="确认允许写入 git 工作区（会影响该工作区所有新 Kimi 会话）",
    )

    check_parser = sub.add_parser("check", help="用真实凭证做只读连接与身份检查")
    check_parser.add_argument("--project-root", type=Path, default=REPO_ROOT, help="包含 .talk/project.yaml 的工作区")
    check_parser.add_argument("--server", default=None, help="覆盖 TALK 服务地址")
    check_parser.add_argument("--project", default=None, help="覆盖 project_id")
    check_parser.add_argument("--expect-member", default="agent:kimi", help="必须匹配的成员身份")
    check_parser.add_argument("--expect-project", default=None, help="必须匹配的 project_id；默认用解析结果")

    probe_parser = sub.add_parser("probe", help="按配置真实拉起 stdio MCP 并核对工具目录")
    probe_parser.add_argument("--config", type=Path, default=None, help="直接使用某个 mcp.json 的 talk 条目")
    probe_parser.add_argument("--project-root", type=Path, default=REPO_ROOT, help="未给 --config 时用于生成配置")
    probe_parser.add_argument("--python", type=Path, default=None, help="解释器绝对路径")
    probe_parser.add_argument("--key-file", type=Path, default=None, help="仓库外的密钥文件路径")
    probe_parser.add_argument("--timeout", type=float, default=60.0, help="子进程超时秒数")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover
                pass
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "config":
            config = build_mcp_config(
                project_root=args.project_root,
                python_executable=args.python,
                key_file=args.key_file,
            )
            if args.write is not None:
                target = write_mcp_config(
                    config,
                    workspace=args.write,
                    force=args.force,
                    allow_git_workspace=args.allow_git_workspace,
                )
                print(json.dumps({
                    "ok": True,
                    "mode": "config",
                    "written": str(target),
                    "contains_secret": False,
                    "note": "配置只含真实绝对路径与外部密钥文件位置；密钥正文请放在该文件里，不要写进 mcp.json。",
                }, ensure_ascii=False, indent=2))
            else:
                sys.stdout.write(config_text(config))
            return 0
        if args.mode == "check":
            report = run_check(
                project_root=args.project_root,
                server=args.server,
                project=args.project,
                expect_member=args.expect_member,
                expect_project=args.expect_project,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        report = run_probe(
            config_path=args.config,
            project_root=args.project_root,
            python_executable=args.python,
            key_file=args.key_file,
            timeout=args.timeout,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except PrecheckError as exc:
        print(f"Kimi 入口预检失败：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - 统一转成中文短错误，避免 traceback
        if not _is_expected_failure(exc):
            raise
        message = str(exc)
        api_key = os.environ.get("TALK_API_KEY", "").strip()
        if api_key:
            message = message.replace(api_key, "[已隐藏]")
        print(f"Kimi 入口预检失败：{message}", file=sys.stderr)
        return 1


def _is_expected_failure(exc: BaseException) -> bool:
    """终端入口的 TalkToolError 需要中文短错误；依赖缺失时退回通用判断。"""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from bridges.talk_task_tools import TalkToolError  # noqa: PLC0415

        if isinstance(exc, TalkToolError):
            return True
    except Exception:  # noqa: BLE001 - 依赖缺失不影响错误分类
        pass
    return isinstance(exc, (OSError, ValueError, subprocess.SubprocessError))


if __name__ == "__main__":
    raise SystemExit(main())
