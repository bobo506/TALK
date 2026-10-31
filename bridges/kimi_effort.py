"""351-D：Kimi 角色的思考强度受管落地。

Kimi CLI 没有按次强度参数（`kimi --help` 只有 `-m/--model`），强度来自角色
`config.toml` 里 `[models."<alias>"] default_effort`。因此这里做三件事：

- ``resolve_target_effort``：只按**公开绑定事实**决定目标强度（用户覆盖 > 模型默认），
  能力未知/不在清单内时返回 ``None``，调用方保持原配置，不猜；
- ``set_model_default_effort``：在**原文**上只改目标模型段的这一个键，其余字节保持不动
  （配置里可能有登录生成内容，不能整份重写）；
- ``apply_role_config_effort``：临时文件 + ``os.replace`` 原子替换，失败不动原文件。

本模块不读凭据、不启动模型；只处理调用方明确给出的角色 config 路径。
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

# Kimi 模型条目已知的强度字面量（与 setup 的 PUBLIC_MODEL_FIELDS 契约一致）。
EFFORT_VALUES = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")


def _normalize(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip().lower()
    return item if item in EFFORT_VALUES else None


def resolve_target_effort(binding: Any) -> str | None:
    """按公开绑定返回本次应写入的强度；无法安全确定时返回 None（保持原配置）。

    - 旧服务没有 ``effective_effort`` → None；
    - ``effort_options`` 非空时必须在其中；
    - 设有用户覆盖但没有任何清单/来源 → None（不把“无法校验”当“可以写入”）。
    """
    if not isinstance(binding, dict):
        return None
    target = _normalize(binding.get("effective_effort"))
    if target is None:
        return None
    options = binding.get("effort_options")
    override = binding.get("effort_override")
    has_override = isinstance(override, str) and bool(override.strip())
    if isinstance(options, list) and options:
        allowed = {_normalize(value) for value in options} - {None}
        if target not in allowed:
            return None
    elif has_override:
        return None
    if has_override and not isinstance(binding.get("effort_source"), str):
        return None
    return target


def _section_bounds(text: str, alias: str) -> tuple[int, int] | None:
    """返回 ``[models."alias"]`` 段的正文起止（不含标题行）；找不到返回 None。"""
    for quote in ('"', "'"):
        header = "[models.%s%s%s]" % (quote, alias, quote)
        index = text.find(header)
        if index < 0:
            continue
        start = text.find("\n", index)
        if start < 0:
            return (len(text), len(text))
        start += 1
        end = len(text)
        cursor = start
        while True:
            line_end = text.find("\n", cursor)
            line = text[cursor:] if line_end < 0 else text[cursor:line_end]
            stripped = line.strip()
            if stripped.startswith("[") and not stripped.startswith("[["):
                end = cursor
                break
            if line_end < 0:
                end = len(text)
                break
            cursor = line_end + 1
        return (start, end)
    return None


_EFFORT_LINE = re.compile(r'^(?P<indent>[ \t]*)default_effort[ \t]*=[ \t]*"[^"]*"[ \t]*$', re.MULTILINE)


def set_model_default_effort(text: str, alias: str, effort: str) -> tuple[str, str]:
    """在原文里设置 ``models.<alias>.default_effort``，返回 ``(新文本, 模式)``。

    模式：``replace``（已有键被替换）、``insert``（段内没有该键时插入）。
    段不存在时抛 ``ValueError('kimi_model_section_missing')``，绝不新建模型段。
    """
    if _normalize(effort) is None:
        raise ValueError("kimi_effort_invalid")
    bounds = _section_bounds(text, alias)
    if bounds is None:
        raise ValueError("kimi_model_section_missing")
    start, end = bounds
    body = text[start:end]
    line = 'default_effort = "%s"' % effort
    updated, count = _EFFORT_LINE.subn(line, body)
    if count:
        return text[:start] + updated + text[end:], "replace"
    # 段内没有该键：插到段首（段标题下一行），保持其余内容与缩进不变。
    return text[:start] + line + "\n" + text[start:], "insert"


def apply_role_config_effort(config_path: Path, alias: str, effort: str) -> str:
    """原子地把角色配置里目标模型的强度改成 ``effort``，返回模式。

    - 先读原文、算新文；内容没变化直接返回 ``unchanged``；
    - 写入同目录临时文件后 ``os.replace``；任何异常都不改动原文件。
    """
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    updated, mode = set_model_default_effort(text, alias, effort)
    if updated == text:
        return "unchanged"
    handle, temp_name = tempfile.mkstemp(prefix=".effort-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return mode
