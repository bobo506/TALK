"""351-E：DSH 角色的思考强度受管写入（只改 patch 里的 reasoningEffort 行）。

DSH 的强度不是命令行参数，而是角色私有 patch（``model-*.patch.yml``）里的
``reasoningEffort``。用户实测 DSH 界面提供 ``off / low / high / max``，但按用户决定
TALK 当前只开放 ``max``；本模块只负责把目标值写进那一行，不新建配置段。
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

# 用户界面观察到的 DSH 档位；TALK 当前只开放 max（其余记录在案、不开放）。
OBSERVED_EFFORTS = ("off", "low", "high", "max")
# 用户确认四档全部开放；写入时仍只接受这四个字面量。
OPEN_EFFORTS = ("off", "low", "high", "max")

_LINE = re.compile(r"^(?P<indent>[ \t]*)reasoningEffort[ \t]*:[ \t]*(?P<value>[A-Za-z]+)[ \t]*$", re.MULTILINE)


def normalize_effort(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip().lower()
    return item if item in OBSERVED_EFFORTS else None


def resolve_open_effort(binding: Any) -> str | None:
    """按公开绑定取本次要写入的强度；只接受 TALK 已开放的档位（当前仅 max）。"""
    if not isinstance(binding, dict):
        return None
    effort = normalize_effort(binding.get("effective_effort"))
    if effort is None or effort not in OPEN_EFFORTS:
        return None
    options = binding.get("effort_options")
    if isinstance(options, list) and options:
        allowed = {normalize_effort(value) for value in options} - {None}
        if effort not in allowed:
            return None
    return effort


def set_patch_effort(text: str, effort: str) -> tuple[str, str]:
    """把 patch 文本里的 ``reasoningEffort`` 行改成目标值。

    有该行 → ``replace``；没有该行 → 抛 ``ValueError('dsh_effort_line_missing')``，
    不新建键（YAML 嵌套位置未知，插入可能改错层级）。
    """
    value = normalize_effort(effort)
    if value is None or value not in OPEN_EFFORTS:
        raise ValueError("dsh_effort_not_open")
    updated, count = _LINE.subn(lambda match: "%sreasoningEffort: %s" % (match.group("indent"), value), text)
    if not count:
        raise ValueError("dsh_effort_line_missing")
    return updated, "replace"


def apply_patch_effort(path: Path, effort: str) -> str:
    """原子替换；内容没变化返回 ``unchanged``，失败不改原文件。"""
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    updated, mode = set_patch_effort(text, effort)
    if updated == text:
        return "unchanged"
    handle, temp_name = tempfile.mkstemp(prefix=".effort-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return mode


def find_patch(directory: Path) -> Path | None:
    """角色原生目录里的 ``model-*.patch.yml``；多份时取排序第一份（与启动回填口径一致）。"""
    for path in sorted(Path(directory).glob("model-*.patch.yml")):
        return path
    return None
