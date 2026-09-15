#!/usr/bin/env python3
"""DSH 独立会话的 TALK MCP 启动器（仓库内不存放任何密钥）。

目的与 `scripts/kimi_talk_mcp_launch.py` 相同，只是换成给 DeepSeek Harness 的
`@deepseek-ai/dsh-mcp-client` stdio 条目使用。它只做两件事：

1. 解析 ``TALK_API_KEY``：优先外部环境变量，其次仓库外的密钥文件；密钥始终留在
   环境或仓库外文件里，绝不写入仓库、不打印、不落日志。
2. 把标准输入输出原样交给既有普通终端入口 ``bridges/talk_terminal_mcp.py``。

因此这里**不新增任何任务工具合同**：工具目录、只读边界与错误文案全部由既有入口决定。

为什么需要这一层：DSH 的子进程 seam 会按 ``/KEY|PASSWORD|SECRET|TOKEN/i`` 与
``DSH_*`` 清洗环境（`@deepseek-ai/dsh-subprocess` 的 `scrubbedParentEnv()`），
`dsh-mcp-client` 也以同一清洗结果作为子进程环境基座，只在配置显式给出 ``env`` 时
再合并回去。所以密钥必须由本启动器在**它自己的进程内**解析，而不是指望环境继承。

stdout 只承载 MCP JSON-RPC；所有诊断信息写 stderr，避免污染协议流。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY_FILE_NAME = "agent-deepseek.key"
DEFAULT_KEY_DIR_NAME = ".talk"


class DshEntryError(RuntimeError):
    """启动器可预期的中文错误；调用方只打印 message，不打印 traceback。"""


def default_key_file() -> Path:
    """仓库外的默认密钥文件位置：``~/.talk/agent-deepseek.key``。"""
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not home:
        try:
            home = str(Path.home())
        except RuntimeError as exc:
            raise DshEntryError(
                "无法确定用户主目录；请用 TALK_DSH_KEY_FILE 显式指定仓库外的密钥文件"
            ) from exc
    return (Path(home).expanduser() / DEFAULT_KEY_DIR_NAME / DEFAULT_KEY_FILE_NAME).resolve()


def _validate_key(key: str, *, source: str) -> str:
    """密钥必须是可打印 ASCII：HTTP 头按 latin-1 编码，含其它字符只会得到难懂的报错。"""
    if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in key):
        raise DshEntryError(
            f"{source} 的内容不是可用的 API Key：只应包含一行可打印 ASCII 字符；"
            "常见原因是文件带了 BOM、写入了多余内容或复制时带入了空格/换行"
        )
    return key


def _read_key_file(path: Path, *, repo_root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise DshEntryError(
            f"密钥文件位于仓库内（{resolved}）；请把它移到仓库外，例如 {default_key_file()}。"
        )
    if not resolved.is_file():
        raise DshEntryError(
            f"未找到密钥文件 {resolved}；请先在仓库外创建该文件，或在环境中设置 TALK_API_KEY。"
        )
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise DshEntryError(f"读取密钥文件失败（{resolved}）：{exc}") from exc
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return _validate_key(candidate, source=f"密钥文件 {resolved}")
    raise DshEntryError(f"密钥文件为空：{resolved}")


def resolve_api_key(
    *,
    repo_root: Path | None = None,
    environ: dict | None = None,
) -> tuple[str, str]:
    """返回 ``(api_key, 来源说明)``；来源说明不含密钥正文，可直接写日志。"""
    env = os.environ if environ is None else environ
    root = repo_root if repo_root is not None else REPO_ROOT

    from_env = (env.get("TALK_API_KEY") or "").strip()
    if from_env:
        return _validate_key(from_env, source="环境变量 TALK_API_KEY"), "环境变量 TALK_API_KEY"

    key_file = (env.get("TALK_DSH_KEY_FILE") or "").strip()
    path = Path(key_file) if key_file else default_key_file()
    key = _read_key_file(path, repo_root=root)
    return key, f"密钥文件 {path.expanduser().resolve()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DSH 独立会话的 TALK MCP 启动器（复用 bridges/talk_terminal_mcp.py）",
        # 关闭前缀匹配，否则 `--project prj_x` 会被当成 `--project-root prj_x`。
        allow_abbrev=False,
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=REPO_ROOT,
        help="包含 .talk/project.yaml 的工作区目录；默认为本仓库根目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):  # pragma: no cover - 管道被替换时忽略
                pass

    args, passthrough = build_parser().parse_known_args(argv)
    try:
        api_key, source = resolve_api_key()
    except DshEntryError as exc:
        print(f"DSH TALK 入口启动失败：{exc}", file=sys.stderr)
        return 1

    project_root = Path(args.project_root).expanduser().resolve()
    os.environ["TALK_API_KEY"] = api_key
    # 身份只由 API Key 对应的服务端成员决定，忽略任何继承的成员提示。
    os.environ.pop("TALK_MEMBER_ID", None)

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from bridges import talk_terminal_mcp
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给中文提示
        print(f"DSH TALK 入口启动失败：无法导入 TALK 终端入口（{exc}）", file=sys.stderr)
        return 1

    print(f"DSH TALK 入口：密钥来源 {source}；工作区 {project_root}", file=sys.stderr)
    explicit_project = any(
        item == "--project" or item.startswith("--project=") for item in passthrough
    )
    forwarded = list(passthrough) if explicit_project else ["--project-root", str(project_root), *passthrough]
    return talk_terminal_mcp.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
