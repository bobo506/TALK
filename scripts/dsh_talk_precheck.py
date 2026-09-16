#!/usr/bin/env python3
"""DSH 原生主控入口的配置生成、身份预检与 stdio 工具探针（无密钥落盘）。

三个子命令各自独立、都可在**零模型**下运行：

- ``config``：把 ``deploy/dsh/talk-mcp.patch.template.yml`` 渲染成实际路径的
  ``--patch`` 覆盖层；默认只打印，``--write`` 才落盘，且默认拒绝写进仓库。
- ``check``：用本人 ``TALK_API_KEY``（环境变量或仓库外密钥文件）做只读身份检查，
  显式核对期望 member 与期望 project，输出一行 JSON。
- ``probe``：按覆盖层里真实的 ``command``/``args``/``env`` 拉起 stdio MCP，
  只发 ``initialize`` + ``tools/list``，核对工具目录；用占位密钥、不访问服务端。
- ``dump``：让 DSH 自己组合 ``--patch`` 覆盖层并导出配置树，用于证明“白名单与 MCP 行
  是组合层事实”，同样不发起任何模型请求。``--patch``/``--dsh-home``/``--out`` 都先按
  调用者当前目录解析成绝对路径再传下游：DSH 会把相对 ``--patch`` 拼在它自己的 cwd
  （这里为 ``dsh_home.parent``）上，直接传相对路径会读错位置。

密钥只从环境变量或仓库外文件读取；本脚本绝不打印、绝不写入密钥正文。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATE_PATH = REPO_ROOT / "deploy" / "dsh" / "talk-mcp.patch.template.yml"
SERVER_NAME = "talk"
MCP_PLUGIN = "@deepseek-ai/dsh-mcp-client"
PLACEHOLDER_KEY = "precheck-local-placeholder"
STDIO_FALLBACK_MARKER = "STDIO_FALLBACK_FILE_STDIO"
EXPECTED_TOOLS = (
    "talk_list_agents",
    "talk_delegate_task",
    "talk_get_task",
    "talk_list_tasks",
    "talk_wait_tasks",
    "talk_reply_task",
    "talk_cancel_task",
    "talk_collect_result",
    "talk_get_delivery",
)


class DshPrecheckError(RuntimeError):
    """预检可预期的中文错误；调用方只打印 message。"""


class _TolerantLoader(yaml.SafeLoader):
    """容忍 cordis 覆盖层里的 `!!js` 表达式：只做结构核对，不求值。"""


def _ignore_js(loader: yaml.Loader, node: yaml.Node) -> str:
    return f"<js:{node.value if isinstance(node, yaml.ScalarNode) else 'expr'}>"


_TolerantLoader.add_constructor("tag:yaml.org,2002:js", _ignore_js)
_TolerantLoader.add_constructor("!js", _ignore_js)


def load_rows(path: Path) -> list:
    try:
        return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_TolerantLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DshPrecheckError(f"覆盖层不是合法 UTF-8 YAML：{path}（{exc}）") from exc


def default_python() -> Path:
    """优先仓库内 venv，其次当前解释器；两者都会写进生成的覆盖层。"""
    venv = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return venv
    return Path(sys.executable)


def resolve_caller_path(path: Path) -> Path:
    """把命令行传入的路径按**调用者当前工作目录**解析成绝对路径。

    必须在下游子进程之前解析：``dump`` 会把 DSH 的 cwd 设成 ``dsh_home.parent``，
    而 DSH 是把 ``--patch`` 原样拼在自己的 cwd 上的，于是相对路径会被读成
    ``<dsh_home.parent>/<相对路径>`` 而不是调用者所在目录下的文件（#71 定位的缺陷）。
    绝对路径（含空格/中文目录）经此函数原样保留。
    """
    return Path(path).expanduser().resolve()


def render_patch(*, server: str, project: str) -> str:
    if not TEMPLATE_PATH.is_file():
        raise DshPrecheckError(f"找不到覆盖层模板 {TEMPLATE_PATH}")
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "__PYTHON__": str(default_python()).replace("\\", "/"),
        "__REPO__": str(REPO_ROOT).replace("\\", "/"),
        "__SERVER__": server,
        "__PROJECT__": project,
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    leftover = [token for token in replacements if token in text]
    if leftover:
        raise DshPrecheckError(f"模板仍有未替换占位符：{leftover}")
    return text


def write_patch(target: Path, *, allow_in_repo: bool) -> Path:
    resolved = target.expanduser().resolve()
    if not resolved.is_absolute():
        raise DshPrecheckError(f"写入目标必须是绝对路径：{target}")
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        if not allow_in_repo:
            raise DshPrecheckError(
                f"写入目标位于仓库内（{resolved}）；隔离验证请显式加 --allow-in-repo，"
                "并确认它是不入库的临时目录"
            )
    if resolved.exists():
        raise DshPrecheckError(f"目标已存在，不覆盖：{resolved}（先删除或换目录）")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(render_patch(server="http://127.0.0.1:8000", project="prj_e8fe7066bbec"), encoding="utf-8")
    return resolved


def load_patch_entry(patch_path: Path) -> dict:
    path = Path(patch_path).expanduser().resolve()
    if not path.is_file():
        raise DshPrecheckError(f"找不到覆盖层文件 {path}")
    rows = load_rows(path)
    if not isinstance(rows, list):
        raise DshPrecheckError(f"覆盖层顶层必须是数组：{path}")
    for row in rows:
        if not isinstance(row, dict):
            continue
        for entry in row.get("insert") or []:
            if isinstance(entry, dict) and entry.get("name") == MCP_PLUGIN:
                config = entry.get("config") or {}
                for field in ("command", "args", "transport", "serverName"):
                    if field not in config:
                        raise DshPrecheckError(f"MCP 条目缺少字段 {field}：{path}")
                return config
    raise DshPrecheckError(f"覆盖层里没有 {MCP_PLUGIN} 条目：{path}")


def disabled_row_ids(patch_path: Path) -> list[str]:
    rows = load_rows(patch_path)
    found = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("disabled") is True and isinstance(row.get("id"), str):
            found.append(row["id"])
    return found


def run_stdio_requests(command: list[str], *, env: dict, cwd: Path, requests: list[dict], timeout: float = 60) -> dict:
    """拉起 stdio MCP 子进程并取回输出；沙箱禁止匿名管道时退化为文件型 stdio。"""
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
        return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "transport": "pipe"}
    except PermissionError:
        pass

    with tempfile.TemporaryDirectory(prefix="dsh-talk-probe-") as tmp_name:
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
                cwd=str(workdir if not cwd else cwd),
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
    return {"returncode": returncode, "stdout": stdout, "stderr": stderr, "transport": "file"}


def probe_tools(config: dict, *, cwd: Path | None = None) -> dict:
    command = [str(config["command"]), *[str(item) for item in config.get("args") or []]]
    env = dict(os.environ)
    for key, value in (config.get("env") or {}).items():
        if isinstance(value, str):
            env[str(key)] = value
    # 占位密钥：只为让既有入口通过“密钥已提供”的分支，不访问服务端。
    env["TALK_API_KEY"] = PLACEHOLDER_KEY
    env.pop("TALK_MEMBER_ID", None)
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dsh-talk-precheck", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    outcome = run_stdio_requests(command, env=env, cwd=cwd or REPO_ROOT, requests=requests)
    tools: list[str] = []
    server_info = None
    for line in outcome["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("id") == 1 and isinstance(payload.get("result"), dict):
            server_info = payload["result"].get("serverInfo")
        if payload.get("id") == 2 and isinstance(payload.get("result"), dict):
            tools = [str(item.get("name")) for item in payload["result"].get("tools") or []]
    return {
        "transport": outcome["transport"],
        "returncode": outcome["returncode"],
        "serverInfo": server_info,
        "tools": tools,
        "stderr_tail": outcome["stderr"][-800:],
    }


def run_check(*, server: str, project: str, expect_member: str, key_source: dict, expect_project: str | None = None) -> dict:
    sys.path.insert(0, str(SCRIPT_DIR))
    from dsh_talk_mcp_launch import DshEntryError, resolve_api_key

    try:
        api_key, source = resolve_api_key()
    except DshEntryError as exc:
        return {"ok": False, "stage": "credential", "error": str(exc)}
    env = dict(os.environ)
    env["TALK_API_KEY"] = api_key
    env.pop("TALK_MEMBER_ID", None)
    entry = SCRIPT_DIR.parent / "bridges" / "talk_terminal_mcp.py"
    # 受限沙箱禁止匿名管道，统一用文件型 stdio 收集输出。
    with tempfile.TemporaryDirectory(prefix="dsh-talk-check-") as tmp_name:
        workdir = Path(tmp_name)
        stdout_path = workdir / "stdout.txt"
        stderr_path = workdir / "stderr.txt"
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_handle:
            returncode = subprocess.call(
                [sys.executable, "-X", "utf8", str(entry), "--server", server, "--project", project, "--check"],
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=env,
                timeout=60,
            )
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
    if returncode != 0:
        return {"ok": False, "stage": "connect", "error": (stderr or stdout).strip()}
    try:
        report = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        return {"ok": False, "stage": "parse", "error": f"{exc}"}
    member = str(report.get("member") or report.get("member_id") or "")
    project_seen = str(report.get("project") or report.get("project_id") or "")
    # `--expect-project` 省略时才退回“实际请求的项目”：显式给了期望项目就必须核对它，
    # 否则这个参数只是摆设，会让操作者误以为已经核对过项目。
    expected_project = expect_project or project
    problems = []
    if member != expect_member:
        problems.append(f"身份不是 {expect_member}（实际 {member or '未知'}）")
    if project_seen != expected_project:
        problems.append(f"项目不是 {expected_project}（实际 {project_seen or '未知'}）")
    return {
        "ok": not problems,
        "stage": "identity",
        "key_source": source,
        "report": report,
        "problems": problems,
        **key_source,
    }


def resolve_dsh_command() -> list[str]:
    """解析可直接 spawn 的 dsh 命令。

    Windows 上 `dsh` 只是 npm shim（`.cmd`/`.ps1`），不能直接 CreateProcess；
    与 `bridges/cli_bridge.py` 相同，绕过 shim 用 Node 启动官方 `bin.js`，
    这样多行/中文参数也不会被 shim 的 `%*` 边界截断。
    """
    import shutil

    node = shutil.which("node") or shutil.which("node.exe")
    entry = REPO_ROOT / ".venv" / "Scripts" / "dsh.cmd"
    candidates = []
    shim = shutil.which("dsh.cmd") or shutil.which("dsh")
    if shim:
        candidates.append(Path(shim).resolve().parent / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js")
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(
            Path(appdata) / "npm" / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        )
    for candidate in candidates:
        if candidate.is_file() and node:
            return [node, str(candidate)]
    if shim is None:
        raise DshPrecheckError("PATH 上找不到 dsh；请先安装 @deepseek-ai/dsh")
    _ = entry
    raise DshPrecheckError(f"找到 dsh shim（{shim}）但解析不到官方 bin.js；请检查 npm 全局安装")


def run_dump(*, patch_path: Path, dsh_home: Path, out_path: Path, profile: str = "headless") -> dict:
    """让 DSH 组合 ``--patch`` 覆盖层并导出配置树；三个路径先解析成绝对路径。

    DSH 会把 ``--patch`` 原样拼在自己的 cwd 上，而这里为了隔离把子进程 cwd 设成
    ``dsh_home.parent``；因此相对路径必须在传下游之前按调用者 cwd 定死，否则 DSH
    会去 ``<dsh_home.parent>/<相对路径>`` 找覆盖层并报 ``failed to read overlay``。
    ``profile`` 默认为 ``headless``（#72 行为不变）；#74 的 ACP 覆盖层用 ``acp``。
    """
    patch_path = resolve_caller_path(patch_path)
    if not patch_path.is_file():
        raise DshPrecheckError(f"找不到覆盖层文件 {patch_path}（相对路径按本次调用目录解析）")
    dsh_home = resolve_caller_path(dsh_home)
    out_path = resolve_caller_path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DSH_HOME"] = str(dsh_home)
    env["PYTHONUTF8"] = "1"
    stderr_path = out_path.with_suffix(".stderr.log")
    command = [*resolve_dsh_command(), "--profile", str(profile), "--patch", str(patch_path), "--dump-config"]
    with out_path.open("w", encoding="utf-8") as handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as err_handle:
        returncode = subprocess.call(
            command,
            stdout=handle,
            stderr=err_handle,
            env=env,
            cwd=str(dsh_home.parent),
            timeout=300,
        )
    text = out_path.read_text(encoding="utf-8")
    stderr_text = stderr_path.read_text(encoding="utf-8")
    return {
        "returncode": returncode,
        "bytes": len(text.encode("utf-8")),
        "has_mcp_plugin": MCP_PLUGIN in text,
        "has_mcp_row_id": "mcp-talk" in text,
        "has_readonly_mode": "read-only" in text,
        "has_server_talk": "talk" in text,
        "stderr_tail": stderr_text[-600:],
        "out_path": str(out_path),
        "patch_path": str(patch_path),
        "dsh_home": str(dsh_home),
        "profile": str(profile),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DSH 原生主控入口预检（零模型）")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="渲染 --patch 覆盖层")
    config.add_argument("--write", type=Path, default=None, help="写入该路径；省略时只打印")
    config.add_argument("--allow-in-repo", action="store_true", help="允许写入仓库内的隔离临时目录")

    check = sub.add_parser("check", help="只读身份检查（需要本人密钥）")
    check.add_argument("--server", default="http://127.0.0.1:8000")
    check.add_argument("--project", default="prj_e8fe7066bbec")
    check.add_argument("--expect-member", default="agent:deepseek")
    check.add_argument("--expect-project", default="prj_e8fe7066bbec")

    probe = sub.add_parser("probe", help="按覆盖层拉起 stdio MCP 并核对工具目录")
    probe.add_argument("--patch", type=Path, required=True)
    probe.add_argument("--cwd", type=Path, default=None)

    dump = sub.add_parser("dump", help="让 DSH 组合覆盖层并导出配置树")
    dump.add_argument("--patch", type=Path, required=True)
    dump.add_argument("--dsh-home", type=Path, required=True)
    dump.add_argument("--out", type=Path, required=True)
    dump.add_argument(
        "--profile",
        default="headless",
        help="要组合的 DSH profile；默认 headless，#74 的 ACP 覆盖层用 acp",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "config":
            if args.write is None:
                print(render_patch(server="http://127.0.0.1:8000", project="prj_e8fe7066bbec"))
                return 0
            path = write_patch(args.write, allow_in_repo=args.allow_in_repo)
            print(json.dumps({"ok": True, "written": str(path)}, ensure_ascii=False))
            return 0
        if args.command == "check":
            result = run_check(
                server=args.server,
                project=args.project,
                expect_member=args.expect_member,
                expect_project=args.expect_project,
                key_source={},
            )
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("ok") else 1
        if args.command == "probe":
            config = load_patch_entry(args.patch)
            result = probe_tools(config, cwd=args.cwd)
            result["expected_tools"] = list(EXPECTED_TOOLS)
            result["tools_match"] = sorted(result["tools"]) == sorted(EXPECTED_TOOLS)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["tools_match"] else 1
        if args.command == "dump":
            result = run_dump(
                patch_path=args.patch,
                dsh_home=args.dsh_home,
                out_path=args.out,
                profile=getattr(args, "profile", "headless"),
            )
            # 用解析后的绝对路径读取覆盖层，避免与下游 DSH 的 cwd 语义分叉。
            result["disabled_rows"] = disabled_row_ids(Path(result["patch_path"]))
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["returncode"] == 0 and result["has_mcp_plugin"] else 1
    except DshPrecheckError as exc:
        print(f"DSH 预检失败：{exc}", file=sys.stderr)
        return 1
    except (subprocess.TimeoutExpired, OSError) as exc:
        # 路径解析后传下游，启动失败/超时都应在这一层收口成中文短错误，而不是 traceback。
        print(
            f"DSH 预检失败：子进程无法启动或未在时限内结束（{type(exc).__name__}）",
            file=sys.stderr,
        )
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
