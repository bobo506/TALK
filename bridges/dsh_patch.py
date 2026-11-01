"""DSH 角色 patch 的结构化校验（启动门槛用，不做整文件字节比对）。

背景（2026-11-01 小d 启动失败）：遗留 DeepSeek 宿主曾要求角色私有 patch 与
「用户确认时的整份文本」逐字节相等（其中含 ``reasoningEffort: max``）。但同一角色
的 patch 又是产品逐任务写强度的载体（``bridges/dsh_effort.py``），一旦按绑定把强度
写成 ``low``，宿主就再也起不来，只能人工回写——本次事故即如此。

本模块把门槛收敛到**确认过的模型事实**：

- ``agent-default-model.config.provider`` / ``.model`` 必须与确认值一致；
- ``llm-deepseek.config.reasoningEffort`` 只要求存在且属于已确认档位
  （``off`` / ``low`` / ``high`` / ``max``），具体值由 TALK 按绑定逐任务写入；
- 注释、空白、行尾与字段顺序变化不再造成启动失败。

解析器只认 TALK 自己写出的形态（``- id: ...`` 列表项 + 两级 ``key: value`` 嵌套）；
其它结构一律 fail-closed，返回可读原因而不抛异常。
"""
from __future__ import annotations

from bridges.dsh_effort import normalize_effort

MODEL_ROW_ID = "agent-default-model"
EFFORT_ROW_ID = "llm-deepseek"
CONFIRMED_PROVIDER = "deepseek-official"
CONFIRMED_MODEL = "deepseek-flash"


class PatchStructureError(ValueError):
    """patch 不是受支持的简单映射列表。"""


def _scalar(raw: str) -> str:
    """取标量值：去掉行内注释与成对引号。"""
    value = raw
    cut = value.find(" #")
    if cut >= 0:
        value = value[:cut]
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_patch_rows(text: str) -> list[dict[str, object]]:
    """把 patch 解析成行映射列表；结构不受支持时抛 ``PatchStructureError``。"""
    rows: list[dict[str, object]] = []
    row: dict[str, object] | None = None
    block: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            if not stripped.startswith("- "):
                raise PatchStructureError("第 %d 行不是列表项" % number)
            key, sep, raw = stripped[2:].partition(":")
            key = key.strip()
            if not sep or not key:
                raise PatchStructureError("第 %d 行列表项缺少键" % number)
            row = {}
            rows.append(row)
            value = _scalar(raw)
            block = None if value else key
            row[key] = value or {}
            continue
        if row is None:
            raise PatchStructureError("第 %d 行出现在列表项之前" % number)
        key, sep, raw = stripped.partition(":")
        key = key.strip()
        if not sep or not key:
            raise PatchStructureError("第 %d 行缺少键" % number)
        if indent == 2:
            value = _scalar(raw)
            block = None if value else key
            row[key] = value or {}
            continue
        if indent == 4 and block is not None:
            value = _scalar(raw)
            if not value:
                raise PatchStructureError("第 %d 行嵌套值不能为空" % number)
            container = row.get(block)
            if not isinstance(container, dict):
                raise PatchStructureError("第 %d 行嵌套层级不匹配" % number)
            container[key] = value
            continue
        raise PatchStructureError("第 %d 行缩进层级不受支持" % number)
    if not rows:
        raise PatchStructureError("没有任何列表项")
    return rows


def patch_problem(text: str) -> str | None:
    """返回启动门槛的拒绝原因；``None`` 表示可以启动。"""
    try:
        rows = parse_patch_rows(text)
    except PatchStructureError as exc:
        return "结构无法识别（%s）" % exc
    models = [item for item in rows if item.get("id") == MODEL_ROW_ID]
    efforts = [item for item in rows if item.get("id") == EFFORT_ROW_ID]
    if len(models) != 1:
        return "需要且只需要一个 %s 段（实际 %d 个）" % (MODEL_ROW_ID, len(models))
    if len(efforts) != 1:
        return "需要且只需要一个 %s 段（实际 %d 个）" % (EFFORT_ROW_ID, len(efforts))
    model_config = models[0].get("config")
    if not isinstance(model_config, dict):
        return "%s 缺少 config 映射" % MODEL_ROW_ID
    if model_config.get("provider") != CONFIRMED_PROVIDER:
        return "provider 与确认值不一致（需要 %s）" % CONFIRMED_PROVIDER
    if model_config.get("model") != CONFIRMED_MODEL:
        return "model 与确认值不一致（需要 %s）" % CONFIRMED_MODEL
    effort_config = efforts[0].get("config")
    if not isinstance(effort_config, dict):
        return "%s 缺少 config 映射" % EFFORT_ROW_ID
    effort = effort_config.get("reasoningEffort")
    if not isinstance(effort, str) or not effort.strip():
        return "缺少 reasoningEffort（由 TALK 按绑定逐任务写入）"
    if normalize_effort(effort) is None:
        return "reasoningEffort 不在已确认档位（off/low/high/max）"
    return None
