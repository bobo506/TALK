#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C1 离线适配事实模块：内存配置对象 + 显式上下文 → plan 侧可登记事实。

正式依据（发布澄清优先于任何 .tmp 参考探针）：

- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_DESIGN.md`` §2–§5：复用既有 schema 与归一化、
  稳定 scope 标识、选择顺序与来源确认、白名单/隐私/漂移指纹；
- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_IMPLEMENTATION_PLAN.md`` §1：C1 只新增本模块与
  对应测试，不读真实配置文件/环境/Key，不联网、不访问 DB、不写文件、不启动进程。

边界：

- 纯函数 + 纯内存：不打开真实 native 配置、不读环境变量或 Key、不访问网络或 DB、
  不写文件、不启动子进程、不导入 MCP 工具模块、不调用 ``load_native_config``；
- 真实配置加载与受信写入属于 C2/C3；本模块的 ``ready`` 只代表“离线事实自洽”，
  **不代表任何角色已经绑定**；
- 错误只回稳定 ``code`` / 已知字段名 / 固定说明，不回显调用方原值、候选 alias、
  解析器异常正文或 ``ValidationError`` 文本。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from pydantic import ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# 复用既有模块：仓库根（``server.models``）与 scripts 目录（``kimi_k28_executor``）。
# 只调整 ``sys.path``，不打开文件、不读环境、不触网、不启进程。
for _path_entry in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

import kimi_k28_executor  # noqa: E402
from server.models import (  # noqa: E402
    RUNNER_ID_PATTERN,
    RoleBindingInput,
    RunnerCreate,
    RunnerUpdate,
    looks_like_credential,
    normalize_model_display_name,
    normalize_model_source,
    normalize_runner_capabilities,
    normalize_runner_runtime,
    normalize_safe_identifier_token,
)

__all__ = [
    "AdapterBindingFactsError",
    "AdapterProfile",
    "ADAPTER_NAMES",
    "BINDING_WRITE_FIELDS",
    "CODEX_ADAPTER",
    "CONFIG_ORIGINS",
    "DEFAULT_ALIAS_FIELD",
    "DSH_ADAPTER",
    "K28_ADAPTER",
    "K28_REQUIRED_HARD_FIELDS",
    "K3_ADAPTER",
    "K3_REQUIRED_HARD_FIELDS",
    "PUBLIC_CONFIG_SCHEMA",
    "PUBLIC_SOURCE_FIELDS",
    "RUNNER_CREATE_FIELDS",
    "RUNNER_UPDATE_FIELDS",
    "SOURCE_ENUM",
    "SOURCE_FINGERPRINT_SCHEMA",
    "SCOPE_PAYLOAD_SCHEMA",
    "UNVERIFIED_SOURCE_REQUIRED_HARD_FIELDS",
    "adapter_profile",
    "build_entry",
    "canonical_json",
    "invalid_fields_from_error",
    "is_opaque_connection_ref",
    "native_default_alias",
    "native_provenance_for",
    "public_config_identity",
    "read_alias_facts",
    "resolve_model_selection",
    "runner_id_for",
    "sanitize_sources",
    "scope_digest",
    "source_fingerprint",
]

# ---------------------------------------------------------------------------
# 字段元组：从既有 schema 的 model_fields 派生（不手抄字段名清单）
# ---------------------------------------------------------------------------

RUNNER_CREATE_FIELDS: tuple[str, ...] = tuple(RunnerCreate.model_fields)
RUNNER_UPDATE_FIELDS: tuple[str, ...] = tuple(RunnerUpdate.model_fields)
BINDING_WRITE_FIELDS: tuple[str, ...] = tuple(RoleBindingInput.model_fields)

# ---------------------------------------------------------------------------
# scope 标识（合同 §3）
# ---------------------------------------------------------------------------

RUNNER_ID_PREFIX = "runner:"
RUNNER_ID_MAX_CHARS = 64
RUNNER_ID_DIGEST_HEX = 32  # 128 bit
RUNNER_ID_RUNTIME_MAX_CHARS = (
    RUNNER_ID_MAX_CHARS - len(RUNNER_ID_PREFIX) - 1 - RUNNER_ID_DIGEST_HEX
)  # 24

SCOPE_PAYLOAD_SCHEMA = "adapter-scope-v1"
# 显式不透明 token：拒绝空、内部空白、路径分隔符、控制符、非 ASCII 与超长。
SCOPE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+~\-]{0,127}$")

DEFAULT_ALIAS_FIELD = "default_model"

# ---------------------------------------------------------------------------
# 来源白名单 / 指纹（合同 §5）
# ---------------------------------------------------------------------------

SOURCE_ENUM: tuple[str, ...] = (
    "argv_explicit_selection",
    "native_default_confirmed",
    "native_parse",
    "hard_contract",
    "declared",
    "fixture",
    "unknown",
)

# ``sources`` 只允许这些公开字段名；其余键（含未知/嵌套/自造键）整条丢弃。
PUBLIC_SOURCE_FIELDS: tuple[str, ...] = (
    "model_alias",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_display_name",
    "runner_id",
    "runtime",
    "host_scope",
    "workspace_scope",
    "note",
)

CONFIG_ORIGINS: tuple[str, ...] = (
    "native_profile_loaded",
    "override_layer",
    "unknown",
)

SOURCE_FINGERPRINT_SCHEMA = "adapter-source-fingerprint-v1"
SOURCE_FINGERPRINT_ALGORITHM = "sha256(canonical_json(nonsecret_inputs))[:32]"
SOURCE_FINGERPRINT_NORMALIZATION = (
    "公开文字先做 NFKC 归一化并 strip（大小写不折叠）；再按 "
    "JSON(sort_keys=True, separators=(',',':'), ensure_ascii=False) 规范化；"
    "最后 sha256 取前 32 个十六进制字符。alias 只以完整 64 hex SHA256 参与输入。"
)

PUBLIC_CONFIG_SCHEMA = "adapter-public-config-v1"
PUBLIC_CONFIG_NATIVE_FIELDS: tuple[str, ...] = (
    "provider_id",
    "model_id",
    "model_display_name",
    "capabilities",
)
PUBLIC_CONFIG_HARD_FIELDS: tuple[str, ...] = (
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
)
PUBLIC_CONFIG_DECLARED_FIELDS: tuple[str, ...] = ("model_source", "connection_ref")

# 声明只能补这些公开字段；其余声明键不进入任何产物。
DECLARED_FIELDS: tuple[str, ...] = (
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
    "model_display_name",
)

# ---------------------------------------------------------------------------
# connection_ref 收窄（合同 §3）
# ---------------------------------------------------------------------------

CONNECTION_REF_PATTERN = re.compile(r"[A-Za-z0-9._\-]{1,128}\Z")
EXECUTABLE_SUFFIXES: tuple[str, ...] = (".exe", ".cmd", ".bat", ".ps1", ".sh")
PATH_LIKE_CONNECTION_REFS = (".", "..")

# ---------------------------------------------------------------------------
# 适配 profile 名称（合同 §4 表格）
# ---------------------------------------------------------------------------

K28_ADAPTER = "agent:kimi-code-k28-preview"
K3_ADAPTER = "agent:kimi"
DSH_ADAPTER = "agent:deepseek"
CODEX_ADAPTER = "agent:codex"
ADAPTER_NAMES: tuple[str, ...] = (K28_ADAPTER, K3_ADAPTER, DSH_ADAPTER, CODEX_ADAPTER)

# DSH / Codex 只有 runtime 已知（合同 §4）；真实模型与连接来源本片未核。
RUNTIME_DSH = "dsh"
RUNTIME_CODEX = "codex"

K28_REQUIRED_HARD_FIELDS: tuple[str, ...] = (
    "model_source",
    "connection_ref",
    "provider_id",
    "model_id",
    "model_alias",
)
# 泛用 K3 没有固定模型硬常量；provider/model 仍由选中 native 条目或合法声明提供。
K3_REQUIRED_HARD_FIELDS: tuple[str, ...] = ()
# 来源未核 profile：任一来源字段缺失即 blocked，不用 unknown/展示名等伪绑定补位。
UNVERIFIED_SOURCE_REQUIRED_HARD_FIELDS: tuple[str, ...] = (
    "model_source",
    "connection_ref",
    "provider_id",
    "model_id",
)

# ---------------------------------------------------------------------------
# 稳定错误与稳定原因码
# ---------------------------------------------------------------------------

_REASON_DETAILS: dict[str, str] = {
    "E_SOURCE_UNAVAILABLE": "该字段没有可用来源；缺失即拒绝，不用默认值或推测值补齐",
    "E_SOURCE_UNCONFIRMED": "来源未确认或摘要不匹配；未核来源不得当作已核事实",
    "E_SOURCE_CONFLICT": "声明或硬契约与已核事实冲突；声明不得覆盖已核事实",
    "E_SELECTION_NOT_READY": "缺少完整且可登记的选择核验结果；不能仅凭绑定载荷生成事实条目",
    "E_FIELD_INVALID": "该字段不是既有规则接受的值；不回显原值",
    "E_CONNECTION_REF_INVALID": "connection_ref 必须是不透明标识，拒绝路径与可执行后缀",
    "E_RUNNER_PAYLOAD_INVALID": "运行器登记载荷未通过既有 RunnerCreate 校验",
    "E_BINDING_PAYLOAD_INVALID": "绑定载荷未通过既有 RoleBindingInput 校验",
    "E_RUNNER_BINDING_ID_MISMATCH": "runner.runner_id 与 binding.runner_id 不一致",
    # 以下仅以异常形式抛出（不进入 blocked 产物）。
    "E_SCOPE_MISSING": "缺少必填的显式 scope；不得用 hostname/实例名/路径推测",
    "E_SCOPE_INVALID": "scope 不是合法的显式不透明 token",
    "E_SCOPE_COLLISION": "该 runner_id 已被另一个 (host, workspace) 占用",
    "E_RUNTIME_INVALID": "runtime 未通过既有 runtime 归一化",
    "E_FLAG_NOT_BOOL": "该标志必须是严格布尔值",
    "E_RUNNER_ID_INVALID": "生成的 runner_id 不满足既有 slug 规则",
    "E_LEDGER_INVALID": "ledger 必须是只读映射或 None",
    "E_UNKNOWN_ADAPTER": "未知的适配 profile 名称",
    "E_TARGET_INVALID": "目标标识不是可接受的公开标签",
}


class AdapterBindingFactsError(ValueError):
    """稳定错误码异常：只携带 ``code`` / ``field``，不携带调用方原值或解析器正文。"""

    def __init__(self, code: str, *, field: Optional[str] = None) -> None:
        super().__init__(code)
        self.code = code
        self.field = field

    def __str__(self) -> str:  # pragma: no cover - 仅用于便于阅读的稳定文本
        return self.code if self.field is None else f"{self.code}:{self.field}"


def _reason(
    code: str, *, field: Optional[str] = None, reason_code: Optional[str] = None
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "field": field,
        "detail": _REASON_DETAILS.get(code, code),
    }
    if reason_code is not None:
        item["reason_code"] = reason_code
    return item


def _blocked(reasons: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "blocked", "blocked": list(reasons)}
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


# ---------------------------------------------------------------------------
# 基础工具（规范化 / 摘要）
# ---------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """把 Mapping/序列转成可确定性 JSON 化的纯 Python 值；其它类型原样保留。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def canonical_json(payload: Any) -> str:
    """合同 §3/§5 规范 JSON：UTF-8、非 ASCII 原样、键排序、紧凑分隔。"""
    return json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalized_text(value: str) -> str:
    """公开文字规范化：NFKC + strip，大小写不折叠。"""
    return unicodedata.normalize("NFKC", value).strip()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_short(text: str, *, hex_chars: int = RUNNER_ID_DIGEST_HEX) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:hex_chars]


def _alias_sha256(alias: Any) -> Optional[str]:
    """alias 只以完整 64 hex SHA256 参与指纹/公开投影；非字符串或空白 → None。"""
    if not isinstance(alias, str):
        return None
    text = normalized_text(alias)
    if not text:
        return None
    return _sha256_hex(text)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _fingerprint_text(value: Any) -> Optional[str]:
    """指纹输入里的公开文字：非字符串/空白/疑似凭据一律丢弃（不回显）。"""
    if not isinstance(value, str):
        return None
    text = normalized_text(value)
    if not text or looks_like_credential(text):
        return None
    return text


def _public_token(value: Any, *, field: str) -> Optional[str]:
    try:
        return normalize_safe_identifier_token(value, field=field)
    except (TypeError, ValueError):
        return None


def _public_model_source(value: Any) -> Optional[str]:
    try:
        return normalize_model_source(value)
    except (TypeError, ValueError):
        return None


def _public_display_name(value: Any) -> Optional[str]:
    try:
        return normalize_model_display_name(value)
    except (TypeError, ValueError):
        return None


def _public_capabilities(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    try:
        capabilities = normalize_runner_capabilities(list(value))
    except (TypeError, ValueError):
        return None
    if any(looks_like_credential(item) for item in capabilities):
        return None
    return capabilities


def _public_connection_ref(value: Any) -> Optional[str]:
    text = _public_token(value, field="connection_ref")
    if text is None or not is_opaque_connection_ref(text):
        return None
    return text


def _public_label(value: Any, *, field: str) -> str:
    """目标标识（adapter / member_id / project_id）：公开标签，拒绝空白与疑似凭据。"""
    if not isinstance(value, str):
        raise AdapterBindingFactsError("E_TARGET_INVALID", field=field)
    text = normalized_text(value)
    if not text or len(text) > 128:
        raise AdapterBindingFactsError("E_TARGET_INVALID", field=field)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise AdapterBindingFactsError("E_TARGET_INVALID", field=field)
    if looks_like_credential(text):
        raise AdapterBindingFactsError("E_TARGET_INVALID", field=field)
    return text


# ---------------------------------------------------------------------------
# connection_ref 收窄
# ---------------------------------------------------------------------------


def is_opaque_connection_ref(value: Any) -> bool:
    """只接受 ``[A-Za-z0-9._-]{1,128}`` 的不透明标识。

    额外收窄（本合同允许的“更严”）：拒绝 ``.`` / ``..`` 这类路径字面量与
    ``.exe/.cmd/.bat/.ps1/.sh`` 可执行后缀；不解析 URL、凭据路径或命令行。
    """
    if not isinstance(value, str):
        return False
    if value in PATH_LIKE_CONNECTION_REFS:
        return False
    if not CONNECTION_REF_PATTERN.fullmatch(value):
        return False
    return not value.lower().endswith(EXECUTABLE_SUFFIXES)


# ---------------------------------------------------------------------------
# scope 与 runner_id（合同 §3）
# ---------------------------------------------------------------------------


def _normalize_scope_token(value: Any, *, field: str, required: bool) -> Optional[str]:
    if value is None:
        if required:
            raise AdapterBindingFactsError("E_SCOPE_MISSING", field=field)
        return None
    if not isinstance(value, str):
        raise AdapterBindingFactsError("E_SCOPE_INVALID", field=field)
    text = value.strip()
    if not text:
        raise AdapterBindingFactsError("E_SCOPE_MISSING" if required else "E_SCOPE_INVALID", field=field)
    if not SCOPE_TOKEN_PATTERN.fullmatch(text):
        raise AdapterBindingFactsError("E_SCOPE_INVALID", field=field)
    if looks_like_credential(text):
        # 疑似凭据不得借 scope → runner_id / 指纹 / 错误绕出。
        raise AdapterBindingFactsError("E_SCOPE_INVALID", field=field)
    return text


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise AdapterBindingFactsError("E_FLAG_NOT_BOOL", field=field)
    return value


def _normalized_runtime(runtime: Any) -> str:
    if not isinstance(runtime, str):
        raise AdapterBindingFactsError("E_RUNTIME_INVALID", field="runtime")
    try:
        return normalize_runner_runtime(runtime)
    except (TypeError, ValueError) as exc:
        raise AdapterBindingFactsError("E_RUNTIME_INVALID", field="runtime") from exc


def scope_digest(runtime: str, host_scope: str, workspace_scope: Optional[str]) -> str:
    """规范载荷 ``{"schema":"adapter-scope-v1","scope":[runtime,host,workspace]}`` 的摘要。"""
    payload = canonical_json(
        {
            "schema": SCOPE_PAYLOAD_SCHEMA,
            "scope": [runtime, host_scope, workspace_scope],
        }
    )
    return _sha256_short(payload)


def runner_id_for(
    runtime: Any,
    *,
    host_scope: Any,
    workspace_scope: Any = None,
    host_shared_runner: Any = False,
    multi_workspace_on_host: Any = False,
    ledger: Any = None,
) -> dict[str, Any]:
    """仅凭**显式稳定适配上下文**生成 runner ID。

    - ``runner_id = "runner:" + runtime[:24] + "-" + sha256(规范载荷)[:32]``，恒 ≤ 64；
    - ``host_scope`` 必填；``workspace_scope`` 缺省只在显式 ``host_shared_runner=True``
      时合法，两者互斥；缺省 workspace 以 JSON ``null`` 表示；
    - 两个标志必须是严格布尔值；``multi_workspace_on_host`` 只是发现状态，不参与派生，
      模型/alias/发现状态变化不改 ID；
    - 不依赖持久 ledger；``ledger`` 仅作可选**只读**额外检查，绝不写入。
    """
    runtime_token = _normalized_runtime(runtime)
    host_token = _normalize_scope_token(host_scope, field="host_scope", required=True)
    workspace_token = _normalize_scope_token(
        workspace_scope, field="workspace_scope", required=False
    )
    shared = _strict_bool(host_shared_runner, field="host_shared_runner")
    _strict_bool(multi_workspace_on_host, field="multi_workspace_on_host")

    if workspace_token is None:
        if not shared:
            raise AdapterBindingFactsError("E_SCOPE_MISSING", field="workspace_scope")
        scope_mode = "host_shared"
    else:
        if shared:
            raise AdapterBindingFactsError("E_SCOPE_INVALID", field="host_shared_runner")
        scope_mode = "workspace"

    assert host_token is not None
    digest = scope_digest(runtime_token, host_token, workspace_token)
    short_runtime = runtime_token[:RUNNER_ID_RUNTIME_MAX_CHARS]
    runner_id = f"{RUNNER_ID_PREFIX}{short_runtime}-{digest}"
    if not RUNNER_ID_PATTERN.fullmatch(runner_id) or len(runner_id) > RUNNER_ID_MAX_CHARS:
        raise AdapterBindingFactsError("E_RUNNER_ID_INVALID", field="runner_id")

    record = (host_token, workspace_token, scope_mode)
    if ledger is not None:
        if not isinstance(ledger, Mapping):
            raise AdapterBindingFactsError("E_LEDGER_INVALID", field="ledger")
        existing = ledger.get(runner_id)
        if existing is not None and tuple(existing) != record:
            raise AdapterBindingFactsError("E_SCOPE_COLLISION", field="runner_id")

    return {
        "runner_id": runner_id,
        "digest": digest,
        "scope_mode": scope_mode,
        "host_scope": host_token,
        "workspace_scope": workspace_token,
        "scope": {"host_scope": host_token, "workspace_scope": workspace_token, "scope_mode": scope_mode},
        "canonical_payload": canonical_json(
            {
                "schema": SCOPE_PAYLOAD_SCHEMA,
                "scope": [runtime_token, host_token, workspace_token],
            }
        ),
        "ledger_used": ledger is not None,
        "discovery_state_used": False,
        "runtime_truncated": len(runtime_token) > RUNNER_ID_RUNTIME_MAX_CHARS,
    }


# ---------------------------------------------------------------------------
# native 来源与 provenance（合同 §4）
# ---------------------------------------------------------------------------


def _internal_config_digest(config: Any) -> Optional[str]:
    """**内部** provenance 核验摘要：只在内存比较，绝不进入导出的公开指纹。"""
    try:
        return _sha256_hex(canonical_json(config))
    except (TypeError, ValueError):
        return None


def native_provenance_for(config: Any, *, origin: Any, confirmed: Any = False) -> dict[str, Any]:
    """构造来源确认标记。

    ``confirmed`` 默认 ``False``：**创建摘要本身不证明来源生效**，只有入口在掌握有效
    配置、选择参数与覆盖层情况后显式传 ``True`` 才算确认；非严格布尔值直接拒绝。
    未知 ``origin`` 一律落 ``unknown``（不回显调用方原值）。
    """
    if not isinstance(confirmed, bool):
        raise AdapterBindingFactsError("E_FLAG_NOT_BOOL", field="confirmed")
    normalized_origin = origin if origin in CONFIG_ORIGINS else "unknown"
    return {
        "origin": normalized_origin,
        "confirmed": confirmed,
        "selector": DEFAULT_ALIAS_FIELD,
        "config_content_sha256": _internal_config_digest(config),
    }


def native_default_alias(config: Any, *, provenance: Any = None) -> dict[str, Any]:
    """``default_model`` 只有在来源被确认且摘要一致时才算已核实的最终选择。

    ``origin=override_layer`` / 未确认 / 摘要不匹配一律 ``unconfirmed``。未确认分支
    只返回 alias 摘要，不回显原 alias。
    """
    if not isinstance(config, Mapping):
        return {
            "status": "absent",
            "alias": None,
            "alias_sha256": None,
            "origin": None,
            "reason": "config_not_a_table",
        }
    value = config.get(DEFAULT_ALIAS_FIELD)
    if not isinstance(value, str) or not value.strip():
        return {
            "status": "absent",
            "alias": None,
            "alias_sha256": None,
            "origin": None,
            "reason": "no_default_model",
        }
    alias = normalized_text(value)
    alias_sha256 = _alias_sha256(alias)
    if not isinstance(provenance, Mapping):
        return {
            "status": "unconfirmed",
            "alias": None,
            "alias_sha256": alias_sha256,
            "origin": None,
            "reason": "no_provenance_supplied",
        }
    origin = provenance.get("origin")
    origin = origin if origin in CONFIG_ORIGINS else "unknown"
    if origin != "native_profile_loaded" or provenance.get("confirmed") is not True:
        return {
            "status": "unconfirmed",
            "alias": None,
            "alias_sha256": alias_sha256,
            "origin": origin,
            "reason": "provenance_not_confirmed",
        }
    digest = _internal_config_digest(config)
    if digest is None or provenance.get("config_content_sha256") != digest:
        return {
            "status": "unconfirmed",
            "alias": None,
            "alias_sha256": alias_sha256,
            "origin": origin,
            "reason": "provenance_digest_mismatch",
        }
    return {
        "status": "confirmed",
        "alias": alias,
        "alias_sha256": alias_sha256,
        "origin": origin,
        "reason": "ok",
    }


def read_alias_facts(config: Any, alias: Any) -> dict[str, Any]:
    """以 alias 读取原生公开元组（复用 ``kimi_k28_executor.native_model_binding``）。

    失败只返回稳定 ``unavailable`` 原因码与固定说明：不拼原 alias、不回显解析器正文。
    """
    if not isinstance(config, Mapping):
        return {"unavailable": "config_not_a_table", "reason": "配置对象不是表结构"}
    if not isinstance(alias, str) or not alias.strip():
        return {"unavailable": "alias_missing", "reason": "没有可核对的选中 alias"}
    try:
        info = kimi_k28_executor.native_model_binding(config, normalized_text(alias))
    except kimi_k28_executor.K28ExecutorError:
        return {
            "unavailable": "native_parser_rejected_config",
            "reason": "native 解析器拒绝该配置",
        }
    if not info.get("alias_present"):
        return {"unavailable": "alias_not_found", "reason": "native 配置里没有该 alias 条目"}
    capabilities = _public_capabilities(info.get("capabilities"))
    if capabilities is None:
        return {
            "unavailable": "capabilities_invalid",
            "field": "capabilities",
            "reason": "能力列表未通过公开字段校验",
        }
    return {
        "alias_present": True,
        "provider_id": info.get("provider"),
        "model_id": info.get("model_id"),
        "model_display_name": info.get("display_name"),
        "capabilities": capabilities,
        "tool_use": bool(info.get("tool_use")),
    }


# ---------------------------------------------------------------------------
# 选择顺序与来源确认（合同 §4）
# ---------------------------------------------------------------------------


def _clean_declared(declared: Mapping[str, Any]) -> tuple[Optional[dict[str, str]], Optional[str]]:
    """人工声明只保留已知公开字段的非空白文本；返回 ``(cleaned, bad_field)``。"""
    cleaned: dict[str, str] = {}
    for key, value in declared.items():
        if not isinstance(key, str) or key not in DECLARED_FIELDS:
            continue
        if value is None:
            continue
        if not isinstance(value, str):
            return None, key
        text = normalized_text(value)
        if text:
            cleaned[key] = text
    return cleaned, None


def resolve_model_selection(
    *,
    config: Any,
    explicit_argv_alias: Any = None,
    declared: Any = None,
    hard: Any = None,
    native_provenance: Any = None,
    required_hard_fields: Any = (),
) -> dict[str, Any]:
    """按合同 §4 依次确定最终 alias、核对硬契约、只补机器不可得的公开字段。

    顺序：必需 hard 缺失阻断 → 最终 argv alias 优先 / 已确认 native default 次之 →
    hard alias 逐字核验 → 声明不得覆盖已核事实 → 以选中 alias 读元组 → 核对
    provider/model → 组装字段并复用既有归一化。
    """
    if declared is None:
        declared_map: Mapping[str, Any] = {}
    elif isinstance(declared, Mapping):
        declared_map = declared
    else:
        return _blocked([_reason("E_FIELD_INVALID", field="declared")])

    if hard is None:
        hard_map: Mapping[str, Any] = {}
    elif isinstance(hard, Mapping):
        hard_map = hard
    else:
        return _blocked([_reason("E_FIELD_INVALID", field="hard")])

    if required_hard_fields is None:
        required_source: Sequence[Any] = ()
    elif isinstance(required_hard_fields, (list, tuple, set, frozenset)):
        required_source = tuple(required_hard_fields)
    else:
        return _blocked([_reason("E_FIELD_INVALID", field="required_hard_fields")])
    required: list[str] = []
    for item in required_source:
        if not isinstance(item, str) or item not in BINDING_WRITE_FIELDS:
            return _blocked([_reason("E_FIELD_INVALID", field="required_hard_fields")])
        required.append(item)

    hard_alias = hard_map.get("model_alias")
    if hard_alias is None:
        hard_alias_value: Optional[str] = None
    elif isinstance(hard_alias, str):
        hard_alias_value = normalized_text(hard_alias) or None
    else:
        return _blocked([_reason("E_FIELD_INVALID", field="model_alias")])

    missing = [field for field in required if _is_blank(hard_map.get(field))]
    if missing:
        return _blocked([_reason("E_SOURCE_UNAVAILABLE", field=field) for field in missing])

    # 1) 最终 alias：显式 argv 优先，其次才是已确认有效的 native default。
    alias_source: Optional[str]
    if explicit_argv_alias is not None:
        if not isinstance(explicit_argv_alias, str) or not explicit_argv_alias.strip():
            return _blocked(
                [_reason("E_SOURCE_UNAVAILABLE", field="model_alias")],
                alias_source="argv_explicit_selection",
            )
        alias = normalized_text(explicit_argv_alias)
        alias_source = "argv_explicit_selection"
    else:
        default = native_default_alias(config, provenance=native_provenance)
        if default["status"] == "absent":
            return _blocked([_reason("E_SOURCE_UNAVAILABLE", field="model_alias")])
        if default["status"] != "confirmed":
            return _blocked(
                [_reason("E_SOURCE_UNCONFIRMED", field="model_alias")],
                alias_source="unknown",
            )
        alias = default["alias"]
        alias_source = "native_default_confirmed"

    # 2) hard alias 逐字核验：相同 provider/model 不等于同一次调用别名。
    if hard_alias_value is not None and alias != hard_alias_value:
        return _blocked(
            [_reason("E_SOURCE_CONFLICT", field="model_alias")],
            alias_source=alias_source,
        )

    cleaned, bad_field = _clean_declared(declared_map)
    if cleaned is None:
        return _blocked(
            [_reason("E_FIELD_INVALID", field=bad_field)], alias_source=alias_source
        )

    declared_alias = cleaned.get("model_alias")
    if declared_alias is not None and declared_alias != alias:
        return _blocked(
            [_reason("E_SOURCE_CONFLICT", field="model_alias")],
            alias_source=alias_source,
        )

    # 3) 以选中 alias 读取原生公开元组。
    facts = read_alias_facts(config, alias)
    if "unavailable" in facts:
        return _blocked(
            [
                _reason(
                    "E_SOURCE_UNAVAILABLE",
                    field=facts.get("field", "model_alias"),
                    reason_code=facts["unavailable"],
                )
            ],
            alias_source=alias_source,
        )

    # 4) 原生元组与硬契约常量核对（model_id/alias 串配即阻断）。
    conflicts: list[dict[str, Any]] = []
    for field in ("provider_id", "model_id"):
        expected = hard_map.get(field)
        if _is_blank(expected):
            continue
        if facts.get(field) != expected:
            conflicts.append(_reason("E_SOURCE_CONFLICT", field=field))
    if conflicts:
        return _blocked(conflicts, alias_source=alias_source)

    # 5) 组装字段：机器可得优先，声明只补不可得公开字段。
    resolved: dict[str, dict[str, Any]] = {
        "model_alias": {"value": alias, "source": alias_source}
    }
    for field in ("provider_id", "model_id"):
        machine = facts.get(field)
        if _is_blank(machine):
            if field in cleaned:
                resolved[field] = {"value": cleaned[field], "source": "declared"}
            else:
                return _blocked(
                    [_reason("E_SOURCE_UNAVAILABLE", field=field)], alias_source=alias_source
                )
        else:
            if field in cleaned and cleaned[field] != machine:
                return _blocked(
                    [_reason("E_SOURCE_CONFLICT", field=field)], alias_source=alias_source
                )
            resolved[field] = {"value": machine, "source": "native_parse"}

    display = facts.get("model_display_name")
    if _is_blank(display):
        if "model_display_name" in cleaned:
            resolved["model_display_name"] = {
                "value": cleaned["model_display_name"],
                "source": "declared",
            }
        else:
            resolved["model_display_name"] = {"value": None, "source": "unknown"}
    else:
        if "model_display_name" in cleaned and cleaned["model_display_name"] != display:
            return _blocked(
                [_reason("E_SOURCE_CONFLICT", field="model_display_name")],
                alias_source=alias_source,
            )
        resolved["model_display_name"] = {"value": display, "source": "native_parse"}

    for field in ("model_source", "connection_ref"):
        machine = hard_map.get(field)
        declared_value = cleaned.get(field)
        if machine is not None:
            if not isinstance(machine, str) or not normalized_text(machine):
                return _blocked(
                    [_reason("E_FIELD_INVALID", field=field)], alias_source=alias_source
                )
            machine_text = normalized_text(machine)
            if declared_value is not None and declared_value != machine_text:
                return _blocked(
                    [_reason("E_SOURCE_CONFLICT", field=field)], alias_source=alias_source
                )
            resolved[field] = {"value": machine_text, "source": "hard_contract"}
        elif declared_value is not None:
            resolved[field] = {"value": declared_value, "source": "declared"}
        else:
            return _blocked(
                [_reason("E_SOURCE_UNAVAILABLE", field=field)], alias_source=alias_source
            )

    # 6) 复用既有归一化做最后一道校验；失败只回字段名。
    errors: list[dict[str, Any]] = []
    try:
        resolved["model_source"]["value"] = normalize_model_source(
            resolved["model_source"]["value"]
        )
    except (TypeError, ValueError):
        errors.append(_reason("E_FIELD_INVALID", field="model_source"))
    for field in ("provider_id", "model_id"):
        try:
            resolved[field]["value"] = normalize_safe_identifier_token(
                resolved[field]["value"], field=field
            )
        except (TypeError, ValueError):
            errors.append(_reason("E_FIELD_INVALID", field=field))
    try:
        resolved["model_alias"]["value"] = normalize_safe_identifier_token(
            resolved["model_alias"]["value"], field="model_alias"
        )
    except (TypeError, ValueError):
        errors.append(_reason("E_FIELD_INVALID", field="model_alias"))
    try:
        resolved["model_display_name"]["value"] = normalize_model_display_name(
            resolved["model_display_name"]["value"]
        )
    except (TypeError, ValueError):
        errors.append(_reason("E_FIELD_INVALID", field="model_display_name"))

    connection: Optional[str]
    try:
        connection = normalize_safe_identifier_token(
            resolved["connection_ref"]["value"], field="connection_ref"
        )
    except (TypeError, ValueError):
        connection = None
        errors.append(_reason("E_FIELD_INVALID", field="connection_ref"))
    if connection is not None and not is_opaque_connection_ref(connection):
        connection = None
        errors.append(_reason("E_CONNECTION_REF_INVALID", field="connection_ref"))
    resolved["connection_ref"]["value"] = connection

    if errors:
        return _blocked(errors, alias_source=alias_source)

    # 7) 已核实公开事实契约（供公开投影使用；值都经过上面的核验/归一化）。
    hard_contract: dict[str, Any] = {}
    for name in PUBLIC_CONFIG_HARD_FIELDS:
        if name == "model_alias":
            hard_contract[name] = hard_alias_value
            continue
        meta = resolved.get(name)
        if isinstance(meta, Mapping) and meta.get("source") == "hard_contract":
            hard_contract[name] = meta.get("value")
        elif not _is_blank(hard_map.get(name)):
            hard_contract[name] = hard_map.get(name)
    declared_contract: dict[str, Any] = {}
    for name in PUBLIC_CONFIG_DECLARED_FIELDS:
        if name not in cleaned:
            continue
        meta = resolved.get(name)
        if isinstance(meta, Mapping) and meta.get("value") is not None:
            declared_contract[name] = meta.get("value")
        else:
            declared_contract[name] = cleaned[name]

    return {
        "status": "ready",
        "alias": resolved["model_alias"]["value"],
        "alias_sha256": _alias_sha256(resolved["model_alias"]["value"]),
        "alias_source": alias_source,
        "hard_alias": hard_alias_value,
        "hard_contract": hard_contract,
        "declared_contract": declared_contract,
        "fields": resolved,
        "native": {
            "provider_id": facts.get("provider_id"),
            "model_id": facts.get("model_id"),
            "model_display_name": facts.get("model_display_name"),
            "capabilities": list(facts.get("capabilities") or []),
        },
        "required_hard_fields": required,
    }


# ---------------------------------------------------------------------------
# 来源白名单 / 公开投影 / 漂移指纹（合同 §5）
# ---------------------------------------------------------------------------


def sanitize_sources(sources: Any) -> dict[str, Any]:
    """``sources`` 只保留已知公开字段名与 ``{"source": 枚举}``。

    丢弃 ``value``、未知键与任何嵌套结构；非法/缺失来源落 ``unknown``。
    """
    out: dict[str, Any] = {}
    if not isinstance(sources, Mapping):
        return out
    for key, meta in sources.items():
        if not isinstance(key, str) or key not in PUBLIC_SOURCE_FIELDS:
            continue
        source = meta.get("source") if isinstance(meta, Mapping) else None
        if not isinstance(source, str) or source not in SOURCE_ENUM:
            source = "unknown"
        out[key] = {"source": source}
    return out


def public_config_identity(
    *,
    selected_alias: Any = None,
    native: Any = None,
    hard: Any = None,
    declared: Any = None,
    default_alias: Any = None,
    default_alias_confirmed: Any = False,
) -> dict[str, Any]:
    """正式合同 §5 的公开事实投影与 ``config_identity.content_sha256``。

    投影逐键固定；缺失为 ``null``；存在值先经既有归一化，非法值落 ``null``。
    整份 config / ``providers`` / ``api_key``/``token``/路径/环境变量都不进入投影；
    alias 只以完整 64 hex SHA256 出现。
    """
    if not isinstance(default_alias_confirmed, bool):
        raise AdapterBindingFactsError("E_FLAG_NOT_BOOL", field="default_alias_confirmed")
    native_map = native if isinstance(native, Mapping) else {}
    hard_map = hard if isinstance(hard, Mapping) else {}
    declared_map = declared if isinstance(declared, Mapping) else {}

    projection = {
        "schema": PUBLIC_CONFIG_SCHEMA,
        "selected_alias_sha256": _alias_sha256(selected_alias),
        "default_alias_sha256": (
            _alias_sha256(default_alias) if default_alias_confirmed else None
        ),
        "native": {
            "provider_id": _public_token(native_map.get("provider_id"), field="provider_id"),
            "model_id": _public_token(native_map.get("model_id"), field="model_id"),
            "model_display_name": _public_display_name(
                native_map.get("model_display_name")
            ),
            "capabilities": _public_capabilities(native_map.get("capabilities")),
        },
        "hard": {
            "model_source": _public_model_source(hard_map.get("model_source")),
            "provider_id": _public_token(hard_map.get("provider_id"), field="provider_id"),
            "connection_ref": _public_connection_ref(hard_map.get("connection_ref")),
            "model_id": _public_token(hard_map.get("model_id"), field="model_id"),
            "model_alias_sha256": _alias_sha256(hard_map.get("model_alias")),
        },
        "declared": {
            "model_source": _public_model_source(declared_map.get("model_source")),
            "connection_ref": _public_connection_ref(declared_map.get("connection_ref")),
        },
    }
    return {
        "schema": PUBLIC_CONFIG_SCHEMA,
        "projection": projection,
        "content_sha256": _sha256_hex(canonical_json(projection)),
    }


def source_fingerprint(
    *,
    adapter: Any = None,
    runtime: Any = None,
    host_scope: Any = None,
    workspace_scope: Any = None,
    selected_alias: Any = None,
    alias_source: Any = None,
    config_identity: Any = None,
) -> dict[str, Any]:
    """plan→apply 来源漂移指纹（与既有 binding_fingerprint 分开）。

    输入固定为 schema / adapter / runtime / host_scope / workspace_scope /
    选中 alias 的完整 SHA256 / alias 来源枚举 / ``config_identity``；缺失值 ``null``，
    未知来源 ``unknown``。原 alias、整份 config 与任何疑似凭据都不进入指纹输入。
    """
    identity: dict[str, Any] = {"origin": "unknown", "content_sha256": None}
    if isinstance(config_identity, Mapping):
        origin = config_identity.get("origin")
        identity["origin"] = origin if origin in CONFIG_ORIGINS else "unknown"
        digest = config_identity.get("content_sha256")
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            identity["content_sha256"] = digest
    inputs = {
        "schema": SOURCE_FINGERPRINT_SCHEMA,
        "adapter": _fingerprint_text(adapter),
        "runtime": _fingerprint_text(runtime),
        "host_scope": _fingerprint_text(host_scope),
        "workspace_scope": _fingerprint_text(workspace_scope),
        "selected_alias_sha256": _alias_sha256(selected_alias),
        "alias_source": alias_source if alias_source in SOURCE_ENUM else "unknown",
        "config_identity": identity,
    }
    return {
        "schema": SOURCE_FINGERPRINT_SCHEMA,
        "algorithm": SOURCE_FINGERPRINT_ALGORITHM,
        "normalization": SOURCE_FINGERPRINT_NORMALIZATION,
        "fingerprint": _sha256_short(canonical_json(inputs)),
        "nonsecret_inputs": inputs,
    }


# ---------------------------------------------------------------------------
# plan 条目（合同 §2 / §5）
# ---------------------------------------------------------------------------


def invalid_fields_from_error(exc: ValidationError, allowed: Sequence[str]) -> list[str]:
    """只从 ``ValidationError`` 抽取**已知字段名**；绝不回流原值或错误正文。"""
    names: set[str] = set()
    allowed_set = tuple(allowed)
    for err in exc.errors():
        for part in err.get("loc") or ():
            if isinstance(part, str) and part in allowed_set:
                names.add(part)
        message = str(err.get("msg", ""))
        for key in allowed_set:
            if key in message:
                names.add(key)
        if err.get("type") == "extra_forbidden":
            names.add("<extra_field>")
    return sorted(names)


def _selection_binding_errors(selection: Any, binding: RoleBindingInput) -> list[dict[str, Any]]:
    """选择结果与实际 schema 载荷闭合；失败只回固定原因/字段名。"""
    if not isinstance(selection, Mapping) or selection.get("status") != "ready":
        return [_reason("E_SELECTION_NOT_READY", field="selection")]
    fields = selection.get("fields")
    expected_fields = set(BINDING_WRITE_FIELDS) - {"runner_id"}
    if not isinstance(fields, Mapping) or set(fields) != expected_fields:
        return [_reason("E_SELECTION_NOT_READY", field="selection")]
    values: dict[str, Any] = {"runner_id": binding.runner_id}
    for name in BINDING_WRITE_FIELDS:
        if name == "runner_id":
            continue
        meta = fields[name]
        if (
            not isinstance(meta, Mapping) or "value" not in meta
            or meta.get("source") not in SOURCE_ENUM
        ):
            return [_reason("E_SELECTION_NOT_READY", field=name)]
        values[name] = meta["value"]
    try:
        selected_binding = RoleBindingInput(**_plain(values))
    except ValidationError:
        return [_reason("E_SELECTION_NOT_READY", field="selection")]
    if (
        _public_token(selection.get("alias"), field="model_alias") != selected_binding.model_alias
        or selection.get("alias_source") != fields["model_alias"]["source"]
    ):
        return [_reason("E_SOURCE_CONFLICT", field="model_alias")]
    for name in BINDING_WRITE_FIELDS:
        if getattr(selected_binding, name) != getattr(binding, name):
            return [_reason("E_SOURCE_CONFLICT", field=name)]
    native = selection.get("native")
    if not isinstance(native, Mapping):
        return [_reason("E_SELECTION_NOT_READY", field="selection")]
    if _public_capabilities(native.get("capabilities")) is None:
        return [_reason("E_FIELD_INVALID", field="capabilities")]
    # 投影里的来源事实也须与载荷相容；缺失值仍为缺失，不伪造 native/hard 来源。
    for container, names in (
        (native, ("provider_id", "model_id", "model_display_name")),
        (selection.get("hard_contract"), PUBLIC_CONFIG_HARD_FIELDS),
        (selection.get("declared_contract"), PUBLIC_CONFIG_DECLARED_FIELDS),
    ):
        if not isinstance(container, Mapping):
            return [_reason("E_SELECTION_NOT_READY", field="selection")]
        for name in names:
            value = container.get(name)
            if _is_blank(value):
                continue
            try:
                projected = RoleBindingInput(**{**binding.model_dump(), name: _plain(value)})
            except ValidationError:
                return [_reason("E_FIELD_INVALID", field=name)]
            if getattr(projected, name) != getattr(binding, name):
                return [_reason("E_SOURCE_CONFLICT", field=name)]
    return []


def _selection_projection_inputs(selection: Mapping[str, Any]) -> dict[str, Any]:
    """从选择结果派生**已验证公开值**的投影输入（未验证来源一律落 null）。"""
    hard_source = selection.get("hard_contract")
    hard_source = hard_source if isinstance(hard_source, Mapping) else {}
    declared_source = selection.get("declared_contract")
    declared_source = declared_source if isinstance(declared_source, Mapping) else {}
    hard: dict[str, Any] = {}
    for name in PUBLIC_CONFIG_HARD_FIELDS:
        if name in hard_source:
            hard[name] = hard_source.get(name)
        elif name == "model_alias":
            hard[name] = selection.get("hard_alias")
        else:
            hard[name] = None
    declared = {name: declared_source.get(name) for name in PUBLIC_CONFIG_DECLARED_FIELDS}
    native = selection.get("native") if isinstance(selection.get("native"), Mapping) else {}
    return {
        "selected_alias": selection.get("alias"),
        "alias_source": selection.get("alias_source"),
        "native": native,
        "hard": hard,
        "declared": declared,
    }


def build_entry(
    *,
    adapter: Any,
    member_id: Any,
    project_id: Any,
    runner_fields: Any,
    binding_fields: Any,
    sources: Any = None,
    source_context: Any = None,
) -> dict[str, Any]:
    """plan 条目：ready 前实例化既有 schema、核 runner/binding ID 一致、收窄连接引用。

    ``ready`` 只输出两个既有 schema 的 ``model_dump`` 白名单 + 脱敏 sources +
    公开投影与来源指纹；``blocked`` 不回候选 runner/binding，也不生成指纹。
    ``source_context`` 识别键：``host_scope`` / ``workspace_scope`` / ``origin`` /
    ``selection``（必需的 ``resolve_model_selection`` ready 结果，与绑定六字段一致）。
    没有选择核验结果时阻断，不将 schema 合法等同于来源已核。
    """
    adapter_label = _public_label(adapter, field="adapter")
    member_label = _public_label(member_id, field="member_id")
    project_label = _public_label(project_id, field="project_id")

    context = source_context if isinstance(source_context, Mapping) else {}
    sanitized = sanitize_sources(sources)
    base: dict[str, Any] = {
        "adapter": adapter_label,
        "member_id": member_label,
        "project_id": project_label,
        "sources": sanitized,
    }

    runner_map = runner_fields if isinstance(runner_fields, Mapping) else None
    binding_map = binding_fields if isinstance(binding_fields, Mapping) else None
    if runner_map is None:
        return {
            **base,
            "status": "blocked",
            "blocked": [
                {
                    **_reason("E_RUNNER_PAYLOAD_INVALID"),
                    "invalid_fields": [],
                }
            ],
        }
    if binding_map is None:
        return {
            **base,
            "status": "blocked",
            "blocked": [
                {
                    **_reason("E_BINDING_PAYLOAD_INVALID"),
                    "invalid_fields": [],
                }
            ],
        }

    try:
        runner = RunnerCreate(**_plain(runner_map))
    except ValidationError as exc:
        return {
            **base,
            "status": "blocked",
            "blocked": [
                {
                    **_reason("E_RUNNER_PAYLOAD_INVALID"),
                    "invalid_fields": invalid_fields_from_error(exc, RUNNER_CREATE_FIELDS),
                }
            ],
        }

    try:
        binding = RoleBindingInput(**_plain(binding_map))
    except ValidationError as exc:
        return {
            **base,
            "status": "blocked",
            "blocked": [
                {
                    **_reason("E_BINDING_PAYLOAD_INVALID"),
                    "invalid_fields": invalid_fields_from_error(exc, BINDING_WRITE_FIELDS),
                }
            ],
        }

    if runner.runner_id != binding.runner_id:
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_RUNNER_BINDING_ID_MISMATCH", field="runner_id")],
        }
    if not is_opaque_connection_ref(binding.connection_ref):
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_CONNECTION_REF_INVALID", field="connection_ref")],
        }
    if _public_capabilities(runner.capabilities) is None:
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_FIELD_INVALID", field="capabilities")],
        }

    selection = context.get("selection")
    selection_errors = _selection_binding_errors(selection, binding)
    if selection_errors:
        return {**base, "status": "blocked", "blocked": selection_errors}
    projection_inputs = _selection_projection_inputs(selection)

    alias = projection_inputs.get("selected_alias")
    if not isinstance(alias, str) or not alias.strip():
        alias = binding.model_alias
    alias_source = projection_inputs.get("alias_source")
    if not isinstance(alias_source, str) or alias_source not in SOURCE_ENUM:
        alias_source = (sanitized.get("model_alias") or {}).get("source")

    default_confirmed = alias_source == "native_default_confirmed"
    projection = public_config_identity(
        selected_alias=alias,
        native=projection_inputs.get("native"),
        hard=projection_inputs.get("hard"),
        declared=projection_inputs.get("declared"),
        default_alias=alias if default_confirmed else None,
        default_alias_confirmed=default_confirmed,
    )
    origin = context.get("origin")
    identity = {
        "origin": origin if origin in CONFIG_ORIGINS else "unknown",
        "content_sha256": projection["content_sha256"],
    }
    fingerprint = source_fingerprint(
        adapter=adapter_label,
        runtime=runner.runtime,
        host_scope=context.get("host_scope"),
        workspace_scope=context.get("workspace_scope"),
        selected_alias=alias,
        alias_source=alias_source,
        config_identity=identity,
    )

    return {
        **base,
        "status": "ready",
        "blocked": [],
        "runner": runner.model_dump(),
        "binding": binding.model_dump(),
        "public_config_identity": projection,
        "source_fingerprint": fingerprint,
    }


# ---------------------------------------------------------------------------
# 适配 profile（合同 §4；不可变，scope 由调用方显式传入）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterProfile:
    """不可变适配 profile。

    ``hard`` 使用只读映射、``required_hard_fields`` 使用元组；scope
    （``host_scope`` / ``workspace_scope``）由调用方显式传给 ``runner_id_for``，
    profile 本身不携带、也不推断任何 host/路径。
    """

    adapter: str
    member_id: str
    runtime: str
    explicit_argv_alias: Optional[str]
    hard: Mapping[str, Any]
    required_hard_fields: tuple[str, ...]
    scope_source: str = "caller_explicit_scope"

    def hard_value(self, field: str) -> Any:
        return self.hard.get(field)

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "member_id": self.member_id,
            "runtime": self.runtime,
            "explicit_argv_alias": self.explicit_argv_alias,
            "hard": dict(self.hard),
            "required_hard_fields": list(self.required_hard_fields),
            "scope_source": self.scope_source,
        }


def adapter_profile(name: Any) -> AdapterProfile:
    """按名称取适配 profile；``runtime`` / ``hard`` 常量在调用时读取，保持同源。

    K28 的 alias / provider / model / connection_ref 直接引用
    ``kimi_k28_executor`` 现有常量（不抄字面量、不改其 CLI 默认）；泛用 K3 不继承
    K28 固定 alias；DSH / Codex 本片只有 runtime 已知，来源不足即 blocked。
    """
    if not isinstance(name, str) or name not in ADAPTER_NAMES:
        raise AdapterBindingFactsError("E_UNKNOWN_ADAPTER", field="adapter")

    if name == K28_ADAPTER:
        hard = MappingProxyType(
            {
                "model_source": kimi_k28_executor.MODEL_SOURCE,
                "provider_id": kimi_k28_executor.PROVIDER_ID,
                "connection_ref": kimi_k28_executor.CONNECTION_REF,
                "model_id": kimi_k28_executor.MODEL_ID,
                "model_alias": kimi_k28_executor.MODEL_ALIAS,
            }
        )
        return AdapterProfile(
            adapter=name,
            member_id=name,
            runtime=kimi_k28_executor.RUNTIME,
            explicit_argv_alias=kimi_k28_executor.MODEL_ALIAS,
            hard=hard,
            required_hard_fields=K28_REQUIRED_HARD_FIELDS,
        )

    if name == K3_ADAPTER:
        return AdapterProfile(
            adapter=name,
            member_id=name,
            runtime=kimi_k28_executor.RUNTIME,
            explicit_argv_alias=None,
            hard=MappingProxyType({}),
            required_hard_fields=K3_REQUIRED_HARD_FIELDS,
        )

    if name == DSH_ADAPTER:
        return AdapterProfile(
            adapter=name,
            member_id=name,
            runtime=RUNTIME_DSH,
            explicit_argv_alias=None,
            hard=MappingProxyType({}),
            required_hard_fields=UNVERIFIED_SOURCE_REQUIRED_HARD_FIELDS,
        )

    return AdapterProfile(
        adapter=name,
        member_id=name,
        runtime=RUNTIME_CODEX,
        explicit_argv_alias=None,
        hard=MappingProxyType({}),
        required_hard_fields=UNVERIFIED_SOURCE_REQUIRED_HARD_FIELDS,
    )
