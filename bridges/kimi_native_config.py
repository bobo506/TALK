"""Kimi Code 角色 ``config.toml`` 的结构化校验（启动门槛；不比较整份文本）。

背景：DeepSeek 宿主曾要求角色 patch 与「确认基线」逐字节相等，而产品又按任务把强度
写进同一文件，结果改一次强度角色就再也起不来（2026-11-01 小d 事故）。Kimi 的强度写在
角色 ``config.toml`` 的 ``models.<alias>.default_effort``，与本模块校验的是同一份文件，
所以门槛只认**与绑定一致的模型事实**：

- ``models.<alias>`` 段必须存在，``model``（或兼容键 ``name``）与 ``provider``
  必须等于绑定值；
- ``provider`` 必须在该文件的 ``providers`` 表中声明；
- ``default_effort`` 由 TALK 按绑定逐任务写入，**不参与**校验；注释、空白、字段顺序
  同样不参与。

结构不可读时 fail-closed 并返回可读原因；本模块只读文件与公开绑定字段，不读取凭据值。
"""
from __future__ import annotations

import tomllib
from pathlib import Path

MAX_CONFIG_BYTES = 2 * 1024 * 1024


class KimiConfigError(ValueError):
    """``config.toml`` 不可读取、不可解析或结构不可识别。"""


def read_config_text(path: Path, *, max_bytes: int = MAX_CONFIG_BYTES) -> str:
    """读取角色配置原文；超过大小上限直接拒绝（与宿主既有守卫一致）。"""
    target = Path(path)
    if target.stat().st_size > max_bytes:
        raise KimiConfigError("config.toml 超过大小上限")
    return target.read_text(encoding="utf-8")


def config_problem(
    text: str, alias: str, model_id: str, provider_id: str
) -> str | None:
    """返回启动门槛的拒绝原因；``None`` 表示与绑定一致。"""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return "config.toml 无法解析（%s）" % type(exc).__name__
    models = data.get("models")
    if not isinstance(models, dict):
        return "config.toml 缺少 models 表"
    section = models.get(alias)
    if not isinstance(section, dict):
        return "没有模型 %s 的配置段" % alias
    native_model = section.get("model") or section.get("name")
    if not isinstance(native_model, str) or not native_model:
        return "模型 %s 缺少 model 字段" % alias
    if native_model != model_id:
        return "模型 %s 的 model 与绑定不一致（需要 %s）" % (alias, model_id)
    provider = section.get("provider")
    if not isinstance(provider, str) or not provider:
        return "模型 %s 缺少 provider 字段" % alias
    if provider != provider_id:
        return "模型 %s 的 provider 与绑定不一致（需要 %s）" % (alias, provider_id)
    providers = data.get("providers")
    if not isinstance(providers, dict) or provider not in providers:
        return "provider %s 未在 config.toml 的 providers 中声明" % provider
    return None
