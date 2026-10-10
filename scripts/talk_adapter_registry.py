#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C2 受信应用 CLI/helper：适配收尾登记与角色绑定的 ``plan`` / ``apply`` / ``verify``。

正式依据
--------
- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_DESIGN.md`` §2/§5/§6/§7：复用既有 human 写 API 与
  ``server.models`` 原 schema/归一化；plan 零写；apply 先按本次凭据核 ``kind=human``，
  再重核服务地址、本次参数、project/member、目标资格、schema 与**当前来源指纹**；
  写后一律最新 ``GET /api/runners`` / ``GET binding`` 完整重判；不确定即该条 binding
  ``PUT=0``，且不盲重试写。
- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_IMPLEMENTATION_PLAN.md`` §2（C2）：只新增本模块与
  对应测试；无生产写、不新增服务端 API/权限、不改旧任务快照。

边界（本片不做）
----------------
- 不读真实 native 配置/Key，不猜默认值、不伪造 ``confirmed``：真实来源事实由调用方通过
  **可注入边界** ``source_provider(target) -> {runner_fields, binding_fields, sources,
  source_context}`` 提供；真实文件读取、生效覆盖层确认与 K28 closeout 接线属 C3。
- 不启动/停止/重启进程与服务，不注册成员，不同步名册，不调用模型，不做长等待，不操作
  生产 HTTP/SQLite；隔离 TestClient/内存 SQLite 内的写入由测试驱动。
- 无 CAS：本 helper 不宣称跨 HTTP 原子性；``最近读 → 写`` 的竞争窗口如实保留，本地锁
  不能当作全局防覆盖。

凭据
----
只从环境变量（``--key-env NAME``）或**显式仓库外** ``--key-file PATH`` 取得；没有
``--key`` 明文参数，不自动发现、不复制、不创建、不写入清单/日志/输出。

退出码
------
``0`` 结论为 complete/verified；``1`` partial/blocked/failed/unverified；``2`` 用法或
输入错误（稳定原因码，不含凭据与 raw body）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from pydantic import ValidationError

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# 复用既有模块：仓库根（``server.models``）与 scripts 目录（``adapter_binding_facts``）。
# 只调整 ``sys.path``，不打开文件、不读环境、不触网、不启进程。
for _path_entry in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

import adapter_binding_facts as facts  # noqa: E402
from server.models import (  # noqa: E402
    ROLE_BINDING_BOUND,
    ROLE_BINDING_MEMBER_DISABLED,
    ROLE_BINDING_MEMBER_MISSING,
    ROLE_BINDING_NOT_AGENT,
    ROLE_BINDING_NOT_IN_ROSTER,
    ROLE_BINDING_STATES,
    ROLE_BINDING_UNCONFIGURED,
    RUNNER_ADAPTER_RETIRED,
    RoleBindingInput,
    RunnerCreate,
    RunnerOut,
    RunnerUpdate,
    looks_like_credential,
    normalize_safe_identifier_token,
)

__all__ = [
    "AdapterRegistryError",
    "BINDING_READ_FIELDS",
    "MUTABLE_RUNNER_FIELDS",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "RUNNER_READ_FIELDS",
    "SPEC_SCHEMA",
    "TARGET_BLOCKED_STATES",
    "VERIFY_SCHEMA",
    "RegistryTarget",
    "apply_plan",
    "build_plan",
    "iter_targets",
    "load_credential",
    "main",
    "normalize_server",
    "plan_spec",
    "spec_source_provider",
    "verify_plan",
]

# ---------------------------------------------------------------------------
# schema 标识与字段集合（全部从既有 schema 的 model_fields 派生，不手抄清单）
# ---------------------------------------------------------------------------

PLAN_SCHEMA = "adapter-registry-plan-v1"
RESULT_SCHEMA = "adapter-registry-result-v1"
VERIFY_SCHEMA = "adapter-registry-verify-v1"
SPEC_SCHEMA = "adapter-registry-source-spec-v1"

RUNNER_READ_FIELDS: tuple[str, ...] = tuple(RunnerOut.model_fields)
MUTABLE_RUNNER_FIELDS: tuple[str, ...] = tuple(RunnerUpdate.model_fields)
BINDING_READ_FIELDS: tuple[str, ...] = tuple(RoleBindingInput.model_fields)
RUNNER_CREATE_FIELDS: tuple[str, ...] = tuple(RunnerCreate.model_fields)

# 登记后不可变的两键：与四可变字段一起用于 runtime/retired/冲突判定。
RUNNER_IMMUTABLE_FIELDS: tuple[str, ...] = ("runner_id", "runtime")

# 目标资格阶梯里会**阻断** apply 的四类身份/名册状态（unconfigured 本身不是资格失败）。
TARGET_BLOCKED_STATES: tuple[str, ...] = (
    ROLE_BINDING_MEMBER_MISSING,
    ROLE_BINDING_MEMBER_DISABLED,
    ROLE_BINDING_NOT_IN_ROSTER,
    ROLE_BINDING_NOT_AGENT,
)

READ_ACTIONS: tuple[str, ...] = ("create", "no_op", "update", "conflict", "blocked")

# 读回/写回元数据的白名单：只允许已知公开字段名与已知稳定原因码回流，
# 非法或额外内容不照抄可修改 plan / 服务状态里的任意值。
_HTTP_REASON_PATTERN = re.compile(r"^http_\d{3}$")
_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,63}$")
# 结果/阻断原因里允许出现的固定 token（传输、HTTP、绑定阶梯与内部细分原因）。
_REASON_TOKEN_WHITELIST: frozenset[str] = frozenset(
    {
        "transport_error",
        "timeout",
        "invalid_json",
        "invalid",
        "http_error",
        "ok",
        "unavailable",
        "unknown",
        "not_in_roster",
        "project_member_mismatch",
        "duplicate_runner_id",
    }
) | frozenset(ROLE_BINDING_STATES)
# 已知稳定错误码 = 本模块 + C1 模块的固定原因码表（两边都以不变量形式维护）。
# 依赖下文的 ``_REASON_DETAILS``，因此在 ``_reason`` 之后完成绑定。
_KNOWN_REASON_CODES: frozenset[str] = frozenset()
# 允许在 plan 元数据里出现的字段名（两个模块的已知公开字段名并集）。
_KNOWN_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "adapter",
        "agents",
        "accept_change",
        "binding",
        "binding_fields",
        "binding_state",
        "capabilities",
        "client",
        "confirmed",
        "connection_ref",
        "credential",
        "declared",
        "default_alias_confirmed",
        "detail",
        "entries",
        "entry",
        "expected",
        "expected.binding",
        "expected.runner",
        "field",
        "hard",
        "host_scope",
        "host_shared_runner",
        "identity",
        "key_env",
        "key_file",
        "ledger",
        "member_id",
        "model_alias",
        "model_display_name",
        "model_id",
        "model_source",
        "multi_workspace_on_host",
        "out",
        "path",
        "plan",
        "project",
        "project_id",
        "provider_id",
        "required_hard_fields",
        "runner",
        "runner_fields",
        "runner_id",
        "runners",
        "runtime",
        "schema",
        "selection",
        "server",
        "source_context",
        "source_facts",
        "source_fingerprint",
        "source_provider",
        "sources",
        "spec",
        "targets",
        "workspace_scope",
    }
) | frozenset(MUTABLE_RUNNER_FIELDS) | frozenset(BINDING_READ_FIELDS)

MAX_DOCUMENT_BYTES = 512 * 1024
MAX_CREDENTIAL_CHARS = 512
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
# 仅文档化约定名：``load_credential`` 不接受“隐式默认来源”，调用方必须显式给出
# ``--key-env NAME`` 或 ``--key-file PATH``，不做任何自动发现。
DEFAULT_KEY_ENV = "TALK_ADAPTER_REGISTRY_KEY"

_SERVER_PATTERN = re.compile(r"^https?://[A-Za-z0-9.\-]+(?::\d{1,5})?$")

# ---------------------------------------------------------------------------
# 稳定错误与稳定原因码（只回 code/字段名/固定说明，不回原值、解析器正文或 raw body）
# ---------------------------------------------------------------------------

_REASON_DETAILS: dict[str, str] = {
    "E_SPEC_INVALID": "来源清单不是合法的结构化对象",
    "E_PLAN_INVALID": "计划不是本模块生成的合法 adapter-registry-plan-v1",
    "E_TARGETS_EMPTY": "计划至少需要一个显式目标",
    "E_TARGET_INVALID": "目标标识不是可接受的公开标签",
    "E_TARGET_MISMATCH": "adapter profile 与显式 member_id 不一致",
    "E_UNKNOWN_ADAPTER": "未知的适配 profile 名称",
    "E_SERVER_INVALID": "服务地址不是合法的 http(s) 根地址",
    "E_SERVER_MISMATCH": "本次服务地址与计划不一致",
    "E_CLIENT_SERVER_UNKNOWN": "无法确认 HTTP 客户端指向的服务地址",
    "E_PLAN_PARAM_MISMATCH": "本次参数与计划不一致；需要重新 plan",
    "E_PLAN_ENTRY_BLOCKED": "计划中该条为 blocked，拒绝在 apply 阶段猜写",
    "E_SOURCE_UNAVAILABLE": "缺少当前可核验来源事实",
    "E_SOURCE_DRIFT": "当前来源指纹与计划不一致；需要重新 plan",
    "E_PLAN_STALE": "当前来源载荷与计划载荷不一致；需要重新 plan",
    "E_STATE_DRIFT": "服务端当前状态与计划分类不一致；需要重新 plan",
    "E_STATE_UNREADABLE": "服务端状态读取失败或形状不符合既有 schema",
    "E_TARGET_NOT_ELIGIBLE": "目标角色当前不具备绑定资格（身份/名册）",
    "E_RUNNER_READ_FAILED": "未能取得完整可信的运行器清单",
    "E_RUNNER_RETIRED": "目标运行器已 retired，不自动复启",
    "E_RUNNER_RUNTIME_CONFLICT": "目标 runner_id 已有不同 runtime 的登记，禁止改写",
    "E_RUNNER_CONFLICT": "运行器四个可变字段存在差异，默认冲突",
    "E_RUNNER_NOT_CONFIRMED": "写后读回不能确认目标运行器状态",
    "E_BINDING_READ_FAILED": "未能取得完整可信的绑定读取结果",
    "E_BINDING_NOT_BOUND": "既有绑定字段相同但状态不是 bound",
    "E_BINDING_CONFLICT": "既有绑定与计划绑定存在差异，默认冲突",
    "E_BINDING_NOT_CONFIRMED": "写后读回不能确认目标绑定状态",
    "E_CHANGE_NOT_ACCEPTED": "存在差异但未显式 accept-change，拒绝写入",
    "E_IDENTITY_UNVERIFIED": "本次凭据不是 human 成员或身份核验失败，零写",
    "E_CREDENTIAL_SOURCE_MISSING": "必须显式给出凭据来源（环境变量名或仓库外 key_file）",
    "E_CREDENTIAL_SOURCE_CONFLICT": "凭据来源只能给出一个",
    "E_CREDENTIAL_INVALID": "凭据值不是可接受的非空单行文本",
    "E_KEY_FILE_IN_REPO": "key_file 必须位于仓库之外",
    "E_KEY_FILE_UNREADABLE": "key_file 不存在、不是文件或不可读",
    "E_SCOPE_MISMATCH": "来源事实的 runner_id 与显式 scope 派生结果不一致",
    "E_RUNTIME_MISMATCH": "来源事实的 runtime 与适配 profile 不一致",
    "E_FLAG_NOT_BOOL": "scope 标志必须是严格布尔值",
    "E_WRITE_UNKNOWN": "写请求结果未知，且读回无法确定",
    "E_WRITE_FAILED": "写请求返回明确失败；本条不继续，只保留最新观察事实",
    "E_OUTPUT_FAILED": "输出写入失败",
    "E_CLI_INVALID_INPUT": "命令行输入不是可接受的形状",
}

# 已知稳定错误码 = 本模块 + C1 模块的固定原因码表；plan 元数据只允许这些 code 回流。
_KNOWN_REASON_CODES = frozenset(_REASON_DETAILS) | frozenset(
    getattr(facts, "_REASON_DETAILS", {}) or {}
)


class AdapterRegistryError(ValueError):
    """稳定错误码异常：只携带 ``code`` / ``field``，不携带凭据、原值或 raw body。"""

    def __init__(self, code: str, *, field: Optional[str] = None) -> None:
        super().__init__(code)
        self.code = code
        self.field = field

    def __str__(self) -> str:  # pragma: no cover - 便于阅读的稳定文本
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


def _plain(value: Any) -> Any:
    """把 Mapping/序列转成可确定性 JSON 化的纯 Python 值；其它类型原样保留。"""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _same(left: Any, right: Any) -> bool:
    try:
        return _canonical(left) == _canonical(right)
    except (TypeError, ValueError):  # pragma: no cover - 非 JSON 化输入
        return False


def _target_label(value: Any, *, field: str) -> str:
    """公开标签（project_id / member_id / adapter）：拒绝空白、控制符与疑似凭据。"""
    if not isinstance(value, str):
        raise AdapterRegistryError("E_TARGET_INVALID", field=field)
    text = value.strip()
    if not text or len(text) > 128:
        raise AdapterRegistryError("E_TARGET_INVALID", field=field)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise AdapterRegistryError("E_TARGET_INVALID", field=field)
    if looks_like_credential(text):
        raise AdapterRegistryError("E_TARGET_INVALID", field=field)
    try:
        normalize_safe_identifier_token(text, field=field)
    except (TypeError, ValueError) as exc:
        raise AdapterRegistryError("E_TARGET_INVALID", field=field) from exc
    return text


def normalize_server(value: Any) -> str:
    """把显式服务地址规范成 ``scheme://host[:port]`` 根地址（拒绝路径/凭据/查询）。"""
    if not isinstance(value, str):
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    text = value.strip().rstrip("/")
    if not text or not _SERVER_PATTERN.fullmatch(text):
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    try:
        parts = urlsplit(text)
    except ValueError as exc:  # pragma: no cover - 平台/解析器相关，仍归稳定错误
        raise AdapterRegistryError("E_SERVER_INVALID", field="server") from exc
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    try:
        port = parts.port
    except ValueError as exc:
        raise AdapterRegistryError("E_SERVER_INVALID", field="server") from exc
    if port is not None and not 1 <= port <= 65535:
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    if looks_like_credential(parts.netloc):
        raise AdapterRegistryError("E_SERVER_INVALID", field="server")
    return f"{parts.scheme}://{parts.netloc}"


# ---------------------------------------------------------------------------
# 目标与来源清单
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryTarget:
    """一个显式目标：服务地址 + 项目 + 成员 + 适配 profile 名称。"""

    server: str
    project_id: str
    member_id: str
    adapter: str

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "project_id": self.project_id,
            "member_id": self.member_id,
            "adapter": self.adapter,
        }


def iter_targets(spec: Any) -> tuple[RegistryTarget, ...]:
    """从显式来源清单取目标；清单只描述事实，**不采信**其自带的 ready/指纹。"""
    if not isinstance(spec, Mapping):
        raise AdapterRegistryError("E_SPEC_INVALID", field="spec")
    server = normalize_server(spec.get("server"))
    raw_targets = spec.get("targets")
    if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes)):
        raise AdapterRegistryError("E_SPEC_INVALID", field="targets")
    if not raw_targets:
        raise AdapterRegistryError("E_TARGETS_EMPTY", field="targets")

    targets: list[RegistryTarget] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw_targets:
        if not isinstance(item, Mapping):
            raise AdapterRegistryError("E_SPEC_INVALID", field="targets")
        project_id = _target_label(item.get("project_id"), field="project_id")
        member_id = _target_label(item.get("member_id"), field="member_id")
        adapter_raw = item.get("adapter", member_id)
        adapter = _target_label(adapter_raw, field="adapter")
        key = (project_id, member_id, adapter)
        if key in seen:
            raise AdapterRegistryError("E_TARGET_INVALID", field="targets")
        seen.add(key)
        targets.append(
            RegistryTarget(
                server=server,
                project_id=project_id,
                member_id=member_id,
                adapter=adapter,
            )
        )
    return tuple(targets)


def spec_source_provider(spec: Any) -> Callable[[RegistryTarget], Any]:
    """把清单里的**内存来源事实**包成可注入边界；忽略清单自带的 ready/指纹字段。"""
    if not isinstance(spec, Mapping):
        raise AdapterRegistryError("E_SPEC_INVALID", field="spec")
    raw_targets = spec.get("targets")
    index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    if isinstance(raw_targets, Sequence) and not isinstance(raw_targets, (str, bytes)):
        for item in raw_targets:
            if not isinstance(item, Mapping):
                continue
            project_id = item.get("project_id")
            member_id = item.get("member_id")
            adapter = item.get("adapter", member_id)
            if (
                isinstance(project_id, str)
                and isinstance(member_id, str)
                and isinstance(adapter, str)
            ):
                index[(project_id, member_id, adapter)] = item

    def provider(target: RegistryTarget) -> dict[str, Any]:
        raw = index.get((target.project_id, target.member_id, target.adapter))
        if raw is None:
            return {}
        # 只取四类来源事实；清单里的 status/source_fingerprint/expected 等一律忽略。
        return {
            "runner_fields": raw.get("runner_fields"),
            "binding_fields": raw.get("binding_fields"),
            "sources": raw.get("sources"),
            "source_context": raw.get("source_context"),
        }

    return provider


# ---------------------------------------------------------------------------
# 凭据（仅环境变量或显式仓库外 key_file）
# ---------------------------------------------------------------------------


def load_credential(
    *,
    key_env: Optional[str] = None,
    key_file: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
) -> str:
    """取得本次受信进程的凭据：环境变量或显式仓库外 key_file，二者之一。

    - 没有 ``--key`` 这类明文参数入口，也不自动发现/复制/创建凭据；
    - 失败只回稳定原因码，不回显凭据值、文件内容或路径正文。
    """
    if key_env is not None and key_file is not None:
        raise AdapterRegistryError("E_CREDENTIAL_SOURCE_CONFLICT")
    if key_env is None and key_file is None:
        raise AdapterRegistryError("E_CREDENTIAL_SOURCE_MISSING")

    if key_env is not None:
        name = key_env if isinstance(key_env, str) else ""
        if (
            not name
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name)
            or "KEY" not in name.upper()
        ):
            raise AdapterRegistryError("E_CREDENTIAL_SOURCE_MISSING", field="key_env")
        source = environ if environ is not None else os.environ
        value = source.get(name)
        if not isinstance(value, str):
            raise AdapterRegistryError("E_CREDENTIAL_SOURCE_MISSING", field="key_env")
    else:
        root = Path(repo_root) if repo_root is not None else REPO_ROOT
        try:
            candidate = Path(str(key_file)).expanduser()
        except (TypeError, ValueError) as exc:
            raise AdapterRegistryError("E_KEY_FILE_UNREADABLE", field="key_file") from exc
        try:
            resolved = candidate.resolve()
            root_resolved = Path(root).resolve()
        except OSError as exc:  # pragma: no cover - 平台相关
            raise AdapterRegistryError("E_KEY_FILE_UNREADABLE", field="key_file") from exc
        if root_resolved == resolved or root_resolved in resolved.parents:
            raise AdapterRegistryError("E_KEY_FILE_IN_REPO", field="key_file")
        if not resolved.is_file():
            raise AdapterRegistryError("E_KEY_FILE_UNREADABLE", field="key_file")
        try:
            value = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AdapterRegistryError("E_KEY_FILE_UNREADABLE", field="key_file") from exc

    if not isinstance(value, str):
        raise AdapterRegistryError("E_CREDENTIAL_INVALID", field="credential")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > MAX_CREDENTIAL_CHARS
        or any(ord(char) < 33 or ord(char) == 127 for char in normalized)
    ):
        raise AdapterRegistryError("E_CREDENTIAL_INVALID", field="credential")
    return normalized


def _read_json_document(path: Any, *, code: str) -> Any:
    """读取显式 JSON 文档；失败只回稳定原因码，不回显正文或 traceback。"""
    try:
        candidate = Path(str(path))
    except (TypeError, ValueError) as exc:
        raise AdapterRegistryError(code, field="path") from exc
    try:
        if not candidate.is_file():
            raise AdapterRegistryError(code, field="path")
        size = candidate.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise AdapterRegistryError(code, field="path")
        text = candidate.read_text(encoding="utf-8")
    except AdapterRegistryError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AdapterRegistryError(code, field="path") from exc
    try:
        return json.loads(text.lstrip("\ufeff"))
    except (ValueError, RecursionError) as exc:
        raise AdapterRegistryError(code, field="path") from exc


def _write_json_document(path: Any, payload: Any) -> None:
    try:
        target = Path(str(path))
    except (TypeError, ValueError) as exc:
        raise AdapterRegistryError("E_OUTPUT_FAILED", field="out") from exc
    text = json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, indent=2)
    try:
        target.write_text(text + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        # 只回稳定原因码：不回显路径正文、原始异常正文或 traceback。
        raise AdapterRegistryError("E_OUTPUT_FAILED", field="out") from exc


# ---------------------------------------------------------------------------
# HTTP 视图：只使用既有 GET/POST/PATCH/PUT 路径与既有 schema
# ---------------------------------------------------------------------------


def _transport_outcome(exc: BaseException) -> str:
    """按异常类型名归类传输失败（不导入 httpx、不回显异常正文）。"""
    name = type(exc).__name__
    if "Timeout" in name:
        return "timeout"
    return "transport_error"


class _RegistryView:
    """薄 HTTP 视图：形状校验 + 稳定结果码；不放行 raw body/异常正文。"""

    def __init__(self, client: Any, server: str, credential: str) -> None:
        self._client = client
        self._server = server
        self._headers = {"X-API-Key": credential, "Accept": "application/json"}

    # -- 底层 ------------------------------------------------------------
    def _request(
        self, method: str, path: str, *, body: Any = None
    ) -> dict[str, Any]:
        url = f"{self._server}{path}"
        try:
            response = self._client.request(method, url, headers=dict(self._headers), json=body)
        except Exception as exc:  # noqa: BLE001 - 只按类型名归类，不回显正文
            return {"outcome": _transport_outcome(exc), "status": None}
        status = getattr(response, "status_code", None)
        if not isinstance(status, int):
            return {"outcome": "transport_error", "status": None}
        if not 200 <= status < 300:
            return {"outcome": "http_error", "status": status}
        try:
            data = response.json()
        except Exception:  # noqa: BLE001 - 非 JSON 正文一律不回显
            return {"outcome": "invalid_json", "status": status}
        return {"outcome": "ok", "status": status, "data": data}

    # -- 读 --------------------------------------------------------------
    def me(self) -> dict[str, Any]:
        result = self._request("GET", "/api/members/me")
        if result["outcome"] != "ok":
            return {"outcome": result["outcome"], "status": result["status"], "identity": None}
        data = result["data"]
        if not isinstance(data, Mapping) or not isinstance(data.get("kind"), str):
            return {"outcome": "invalid", "status": result["status"], "identity": None}
        return {
            "outcome": "ok",
            "status": result["status"],
            "identity": {"kind": data["kind"]},
        }

    def get_project(self, project_id: str) -> dict[str, Any]:
        result = self._request("GET", f"/api/projects/{project_id}")
        if result["outcome"] != "ok":
            return {"outcome": result["outcome"], "status": result["status"], "reason": None}
        if not isinstance(result["data"], Mapping):
            return {"outcome": "invalid", "status": result["status"], "reason": "E_STATE_UNREADABLE"}
        return {"outcome": "ok", "status": result["status"], "reason": None}

    def list_agents(self, project_id: str) -> dict[str, Any]:
        result = self._request("GET", f"/api/projects/{project_id}/agents")
        if result["outcome"] != "ok":
            return {
                "outcome": result["outcome"],
                "status": result["status"],
                "members": None,
                "reason": None,
            }
        data = result["data"]
        if not isinstance(data, list):
            return {
                "outcome": "invalid",
                "status": result["status"],
                "members": None,
                "reason": "E_STATE_UNREADABLE",
            }
        members: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, Mapping) or not isinstance(item.get("member_id"), str):
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "members": None,
                    "reason": "E_STATE_UNREADABLE",
                }
            state = item.get("binding_state")
            if state is not None and (
                not isinstance(state, str) or state not in ROLE_BINDING_STATES
            ):
                # 未知服务状态安全阻断：不把原字符串带回任何输出。
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "members": None,
                    "reason": "E_STATE_UNREADABLE",
                }
            members.append({"member_id": item["member_id"], "binding_state": state})
        return {"outcome": "ok", "status": result["status"], "members": members, "reason": None}

    def list_runners(self) -> dict[str, Any]:
        result = self._request("GET", "/api/runners")
        if result["outcome"] != "ok":
            return {"outcome": result["outcome"], "status": result["status"], "runners": None, "reason": None}
        data = result["data"]
        if not isinstance(data, list):
            return {
                "outcome": "invalid",
                "status": result["status"],
                "runners": None,
                "reason": "E_RUNNER_READ_FAILED",
            }
        runners: list[dict[str, Any]] = []
        for item in data:
            reason = _runner_schema_error(item)
            if reason is not None:
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "runners": None,
                    "reason": reason,
                }
            runners.append(dict(item))
        return {"outcome": "ok", "status": result["status"], "runners": runners, "reason": None}

    def get_binding(self, project_id: str, member_id: str) -> dict[str, Any]:
        result = self._request(
            "GET", f"/api/projects/{project_id}/agents/{member_id}/binding"
        )
        if result["outcome"] != "ok":
            return {"outcome": result["outcome"], "status": result["status"], "data": None, "reason": None}
        data = result["data"]
        if not isinstance(data, Mapping):
            return {
                "outcome": "invalid",
                "status": result["status"],
                "data": None,
                "reason": "E_BINDING_READ_FAILED",
            }
        for key in ("project_id", "member_id", "binding", "binding_state"):
            if key not in data:
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "data": None,
                    "reason": "E_BINDING_READ_FAILED",
                }
        if not isinstance(data["project_id"], str) or not isinstance(data["member_id"], str):
            return {
                "outcome": "invalid",
                "status": result["status"],
                "data": None,
                "reason": "E_BINDING_READ_FAILED",
            }
        state = data["binding_state"]
        if state is not None and (
            not isinstance(state, str) or state not in ROLE_BINDING_STATES
        ):
            # 未知 binding_state 一律按读失败处理：只回稳定原因码，
            # 不把原字符串写进 reason_code / state / detail。
            return {
                "outcome": "invalid",
                "status": result["status"],
                "data": None,
                "reason": "E_BINDING_READ_FAILED",
            }
        binding = data["binding"]
        if binding is not None:
            if not isinstance(binding, Mapping):
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "data": None,
                    "reason": "E_BINDING_READ_FAILED",
                }
            if any(key not in binding for key in BINDING_READ_FIELDS):
                return {
                    "outcome": "invalid",
                    "status": result["status"],
                    "data": None,
                    "reason": "E_BINDING_READ_FAILED",
                }
        return {
            "outcome": "ok",
            "status": result["status"],
            "data": {
                "project_id": data["project_id"],
                "member_id": data["member_id"],
                "binding": dict(binding) if isinstance(binding, Mapping) else None,
                "binding_state": state,
            },
            "reason": None,
        }

    # -- 写（最多一次，不做盲重试） --------------------------------------
    def post_runner(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/runners", body=dict(payload))

    def patch_runner(self, runner_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/runners/{runner_id}", body=dict(payload))

    def put_binding(
        self, project_id: str, member_id: str, binding: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/projects/{project_id}/agents/{member_id}/binding",
            body={"binding": dict(binding)},
        )


def _runner_schema_error(item: Any) -> Optional[str]:
    """完整 RunnerOut schema 校验：缺键/额外键/坏类型/坏日期一律判读失败。

    不能只判断键存在：``created_at`` / ``updated_at`` 等字段必须能被既有
    ``RunnerOut`` 真正实例化（含日期解析），否则该条读回不可信。
    """
    if not isinstance(item, Mapping):
        return "E_RUNNER_READ_FAILED"
    for key in RUNNER_READ_FIELDS:
        if key not in item:
            return "E_RUNNER_READ_FAILED"
    if set(item) - set(RUNNER_READ_FIELDS):
        return "E_RUNNER_READ_FAILED"
    for key in ("runner_id", "runtime", "display_name", "adapter_status", "created_by"):
        if not isinstance(item.get(key), str) or not item.get(key):
            return "E_RUNNER_READ_FAILED"
    note = item.get("adapter_note")
    if note is not None and not isinstance(note, str):
        return "E_RUNNER_READ_FAILED"
    capabilities = item.get("capabilities")
    if not isinstance(capabilities, list) or any(
        not isinstance(entry, str) for entry in capabilities
    ):
        return "E_RUNNER_READ_FAILED"
    try:
        RunnerOut.model_validate({key: item[key] for key in RUNNER_READ_FIELDS})
    except (ValidationError, TypeError, ValueError):
        return "E_RUNNER_READ_FAILED"
    return None


# ---------------------------------------------------------------------------
# 归一化比较（复用既有 schema；失败不回流原值）
# ---------------------------------------------------------------------------


def _normalized_runner_mutable(observed: Any) -> Optional[dict[str, Any]]:
    if not isinstance(observed, Mapping):
        return None
    payload = {key: observed.get(key) for key in MUTABLE_RUNNER_FIELDS}
    try:
        model = RunnerUpdate(**payload)
    except ValidationError:
        return None
    return {key: getattr(model, key) for key in MUTABLE_RUNNER_FIELDS}


def _expected_runner_mutable(expected_runner: Mapping[str, Any]) -> dict[str, Any]:
    model = RunnerCreate(**dict(expected_runner))
    return {key: getattr(model, key) for key in MUTABLE_RUNNER_FIELDS}


def _normalized_binding(observed: Any) -> Optional[dict[str, Any]]:
    if not isinstance(observed, Mapping):
        return None
    payload = {key: observed.get(key) for key in BINDING_READ_FIELDS}
    try:
        model = RoleBindingInput(**payload)
    except ValidationError:
        return None
    return {key: getattr(model, key) for key in BINDING_READ_FIELDS}


def _binding_difference_fields(observed: Any) -> list[str]:
    """不可解析/不完整存储行（``partial``）的差异字段名；失败只回已知字段名。"""
    if not isinstance(observed, Mapping):
        return list(BINDING_READ_FIELDS)
    payload = {key: observed.get(key) for key in BINDING_READ_FIELDS}
    try:
        RoleBindingInput(**payload)
    except ValidationError as exc:
        names = facts.invalid_fields_from_error(exc, BINDING_READ_FIELDS)
        return names or list(BINDING_READ_FIELDS)
    return []


def _expected_binding(expected_binding: Mapping[str, Any]) -> dict[str, Any]:
    model = RoleBindingInput(**dict(expected_binding))
    return {key: getattr(model, key) for key in BINDING_READ_FIELDS}


# ---------------------------------------------------------------------------
# 来源事实 → plan 条目（复用 C1 build_entry）
# ---------------------------------------------------------------------------


def _profile_target(target: RegistryTarget) -> Optional[dict[str, Any]]:
    """核对 adapter profile 与显式 member/runtime；不一致即 blocked 原因。"""
    try:
        profile = facts.adapter_profile(target.adapter)
    except facts.AdapterBindingFactsError as exc:
        return {"blocked": [_reason("E_UNKNOWN_ADAPTER", field="adapter", reason_code=exc.code)]}
    if profile.member_id != target.member_id:
        return {"blocked": [_reason("E_TARGET_MISMATCH", field="member_id")]}
    return {"profile": profile}


def _scope_recheck(profile: Any, context: Mapping[str, Any], runner_id: str) -> Optional[dict[str, Any]]:
    host_scope = context.get("host_scope")
    workspace_scope = context.get("workspace_scope")
    host_shared = context.get("host_shared_runner", False)
    multi_workspace = context.get("multi_workspace_on_host", False)
    for field, value in (
        ("host_shared_runner", host_shared),
        ("multi_workspace_on_host", multi_workspace),
    ):
        if not isinstance(value, bool):
            return _reason("E_FLAG_NOT_BOOL", field=field)
    try:
        derived = facts.runner_id_for(
            profile.runtime,
            host_scope=host_scope,
            workspace_scope=workspace_scope,
            host_shared_runner=host_shared,
            multi_workspace_on_host=multi_workspace,
        )
    except facts.AdapterBindingFactsError as exc:
        return _reason(exc.code, field=exc.field)
    if derived["runner_id"] != runner_id:
        return _reason("E_SCOPE_MISMATCH", field="runner_id")
    return None


def _build_source_entry(target: RegistryTarget, raw: Any) -> dict[str, Any]:
    """用显式来源事实构造 C1 条目；任何不完整/冲突都 blocked（不回候选）。"""
    base: dict[str, Any] = {
        "adapter": target.adapter,
        "member_id": target.member_id,
        "project_id": target.project_id,
    }
    checked = _profile_target(target)
    if "blocked" in checked:
        return {**base, "status": "blocked", "blocked": checked["blocked"], "sources": {}}
    profile = checked["profile"]

    if not isinstance(raw, Mapping):
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_SOURCE_UNAVAILABLE", field="source_facts")],
            "sources": {},
        }
    sources = raw.get("sources")
    context = raw.get("source_context")
    try:
        entry = facts.build_entry(
            adapter=target.adapter,
            member_id=target.member_id,
            project_id=target.project_id,
            runner_fields=raw.get("runner_fields"),
            binding_fields=raw.get("binding_fields"),
            sources=sources,
            source_context=context,
        )
    except facts.AdapterBindingFactsError as exc:
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_SOURCE_UNAVAILABLE", field=exc.field, reason_code=exc.code)],
            "sources": {},
        }

    base["sources"] = entry.get("sources") or {}
    if entry.get("status") != "ready":
        return {**base, "status": "blocked", "blocked": list(entry.get("blocked") or [])}

    context_map = context if isinstance(context, Mapping) else {}
    scope_error = _scope_recheck(profile, context_map, entry["runner"]["runner_id"])
    if scope_error is not None:
        return {**base, "status": "blocked", "blocked": [scope_error]}
    if entry["runner"]["runtime"] != profile.runtime:
        return {
            **base,
            "status": "blocked",
            "blocked": [_reason("E_RUNTIME_MISMATCH", field="runtime")],
        }

    return {
        **base,
        "status": "ready",
        "blocked": [],
        "expected_runner": dict(entry["runner"]),
        "expected_binding": dict(entry["binding"]),
        "source_fingerprint": dict(entry["source_fingerprint"]),
    }


# ---------------------------------------------------------------------------
# 服务端现状分类
# ---------------------------------------------------------------------------


def _classify_runner(
    runners: Sequence[Mapping[str, Any]], expected_runner: Mapping[str, Any]
) -> dict[str, Any]:
    """按完整 schema 事实分类：create / no_op / update / blocked。"""
    runner_id = expected_runner["runner_id"]
    matches = [item for item in runners if item.get("runner_id") == runner_id]
    if not matches:
        return {"action": "create", "conflict_fields": [], "reason_code": None}
    if len(matches) > 1:
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_RUNNER_CONFLICT",
            "detail": "duplicate_runner_id",
        }
    observed = matches[0]
    if observed.get("runtime") != expected_runner["runtime"]:
        return {
            "action": "blocked",
            "conflict_fields": ["runtime"],
            "reason_code": "E_RUNNER_RUNTIME_CONFLICT",
        }
    if observed.get("adapter_status") == RUNNER_ADAPTER_RETIRED:
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_RUNNER_RETIRED",
        }
    normalized = _normalized_runner_mutable(observed)
    if normalized is None:
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_RUNNER_READ_FAILED",
        }
    expected = _expected_runner_mutable(expected_runner)
    diffs = [field for field in MUTABLE_RUNNER_FIELDS if normalized[field] != expected[field]]
    if not diffs:
        return {"action": "no_op", "conflict_fields": [], "reason_code": None}
    return {"action": "update", "conflict_fields": diffs, "reason_code": None}


def _classify_binding(data: Mapping[str, Any], expected_binding: Mapping[str, Any]) -> dict[str, Any]:
    """按绑定阶梯与七字段分类：create / no_op / update / blocked。"""
    state = data.get("binding_state")
    if state in TARGET_BLOCKED_STATES:
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_TARGET_NOT_ELIGIBLE",
            "state": state,
        }
    observed = data.get("binding")
    if observed is None:
        if state in (None, ROLE_BINDING_UNCONFIGURED):
            return {"action": "create", "conflict_fields": [], "reason_code": None, "state": state}
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_BINDING_NOT_BOUND",
            "state": state,
        }
    normalized = _normalized_binding(observed)
    if normalized is None:
        # ``partial`` 等不可解析存储行同样属于“既有差异”：默认冲突，显式 accept 后才能覆盖。
        return {
            "action": "update",
            "conflict_fields": _binding_difference_fields(observed),
            "reason_code": None,
            "state": state,
        }
    expected = _expected_binding(expected_binding)
    diffs = [field for field in BINDING_READ_FIELDS if normalized[field] != expected[field]]
    if not diffs:
        if state == ROLE_BINDING_BOUND:
            return {"action": "no_op", "conflict_fields": [], "reason_code": None, "state": state}
        return {
            "action": "blocked",
            "conflict_fields": [],
            "reason_code": "E_BINDING_NOT_BOUND",
            "state": state,
        }
    return {"action": "update", "conflict_fields": diffs, "reason_code": None, "state": state}


# ---------------------------------------------------------------------------
# 客户端 ↔ 服务地址一致性（重核“服务地址”）
# ---------------------------------------------------------------------------


def _client_server(client: Any) -> Optional[str]:
    base = getattr(client, "base_url", None)
    if base is None:
        return None
    text = str(base).strip()
    if not text:
        return None
    try:
        return normalize_server(text)
    except AdapterRegistryError:
        return None


def _require_client_server(client: Any, server: str) -> None:
    base = _client_server(client)
    if base is None:
        raise AdapterRegistryError("E_CLIENT_SERVER_UNKNOWN", field="client")
    if base != server:
        raise AdapterRegistryError("E_SERVER_MISMATCH", field="client")


def _blocked_plan_entry(entry: dict[str, Any], reason: dict[str, Any]) -> dict[str, Any]:
    """把 ready 条目降级为 blocked：不保留 runner/binding 候选与指纹。"""
    return {
        "index": entry["index"],
        "adapter": entry["adapter"],
        "member_id": entry["member_id"],
        "project_id": entry["project_id"],
        "status": "blocked",
        "blocked": list(entry.get("blocked") or []) + [reason],
        "sources": entry.get("sources") or {},
    }


def _plan_status(entries: Sequence[Mapping[str, Any]]) -> str:
    if not entries:
        return "blocked"
    fully = all(
        entry.get("status") == "ready"
        and (entry.get("runner") or {}).get("action") in ("create", "no_op", "update")
        and (entry.get("binding") or {}).get("action") in ("create", "no_op", "update")
        for entry in entries
    )
    if fully:
        return "complete"
    if any(entry.get("status") == "ready" for entry in entries):
        return "partial"
    return "blocked"


def _plan_summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def count_action(side: str, action: str) -> int:
        return sum(1 for entry in entries if (entry.get(side) or {}).get("action") == action)

    return {
        "total": len(entries),
        "ready": sum(1 for entry in entries if entry.get("status") == "ready"),
        "blocked": sum(1 for entry in entries if entry.get("status") == "blocked"),
        "runner_create": count_action("runner", "create"),
        "runner_no_op": count_action("runner", "no_op"),
        "runner_update": count_action("runner", "update"),
        "runner_conflict": count_action("runner", "conflict"),
        "binding_create": count_action("binding", "create"),
        "binding_no_op": count_action("binding", "no_op"),
        "binding_update": count_action("binding", "update"),
        "binding_conflict": count_action("binding", "conflict"),
    }


# ---------------------------------------------------------------------------
# plan：只读（GET only，零写）
# ---------------------------------------------------------------------------


def _plan_entry(
    view: _RegistryView,
    index: int,
    target: RegistryTarget,
    source_provider: Callable[[RegistryTarget], Any],
    accept_change: bool,
) -> dict[str, Any]:
    try:
        raw = source_provider(target)
    except Exception:  # noqa: BLE001 - 来源边界异常不回流正文
        raw = None
    source_entry = _build_source_entry(target, raw)
    entry: dict[str, Any] = {
        "index": index,
        "adapter": source_entry["adapter"],
        "member_id": source_entry["member_id"],
        "project_id": source_entry["project_id"],
        "status": source_entry["status"],
        "blocked": list(source_entry.get("blocked") or []),
        "sources": source_entry.get("sources") or {},
    }
    if source_entry["status"] != "ready":
        return entry

    project = view.get_project(target.project_id)
    if project["outcome"] != "ok":
        return _blocked_plan_entry(
            entry,
            _reason(
                "E_STATE_UNREADABLE",
                field="project",
                reason_code=(
                    f"http_{project['status']}"
                    if project["status"] is not None
                    else project["outcome"]
                ),
            ),
        )
    agents = view.list_agents(target.project_id)
    if agents["outcome"] != "ok":
        return _blocked_plan_entry(
            entry,
            _reason(
                "E_STATE_UNREADABLE",
                field="agents",
                reason_code=(
                    f"http_{agents['status']}"
                    if agents["status"] is not None
                    else agents["outcome"]
                ),
            ),
        )
    if target.member_id not in {item["member_id"] for item in agents["members"]}:
        return _blocked_plan_entry(
            entry,
            _reason("E_TARGET_NOT_ELIGIBLE", field="member_id", reason_code="not_in_roster"),
        )
    runners_read = view.list_runners()
    if runners_read["outcome"] != "ok":
        return _blocked_plan_entry(
            entry,
            _reason("E_RUNNER_READ_FAILED", field="runners", reason_code=runners_read["reason"]),
        )
    binding_read = view.get_binding(target.project_id, target.member_id)
    if binding_read["outcome"] != "ok":
        return _blocked_plan_entry(
            entry,
            _reason(
                "E_BINDING_READ_FAILED",
                field="binding",
                reason_code=(
                    f"http_{binding_read['status']}"
                    if binding_read["status"] is not None
                    else binding_read["outcome"]
                ),
            ),
        )
    binding_data = binding_read["data"]
    if (
        binding_data["project_id"] != target.project_id
        or binding_data["member_id"] != target.member_id
    ):
        return _blocked_plan_entry(
            entry, _reason("E_STATE_DRIFT", field="binding", reason_code="project_member_mismatch")
        )

    runner_cls = _classify_runner(runners_read["runners"], source_entry["expected_runner"])
    binding_cls = _classify_binding(binding_data, source_entry["expected_binding"])
    blocked_reasons: list[dict[str, Any]] = []
    if runner_cls["action"] == "blocked":
        runner_reason = _reason(
            runner_cls["reason_code"], field="runner", reason_code=runner_cls.get("detail")
        )
        if runner_cls["conflict_fields"]:
            runner_reason["conflict_fields"] = list(runner_cls["conflict_fields"])
        blocked_reasons.append(runner_reason)
    if binding_cls["action"] == "blocked":
        blocked_reasons.append(
            _reason(binding_cls["reason_code"], field="binding", reason_code=binding_cls.get("state"))
        )
    if blocked_reasons:
        # 阻断即不产生 runner/binding 候选与指纹（此时尚未写入这些键）。
        entry["status"] = "blocked"
        entry["blocked"] = blocked_reasons
        return entry

    runner_action = runner_cls["action"]
    if runner_action == "update" and not accept_change:
        runner_action = "conflict"
    binding_action = binding_cls["action"]
    if binding_action == "update" and not accept_change:
        binding_action = "conflict"

    entry.update(
        {
            "status": "ready",
            "blocked": [],
            "expected": {
                "runner": dict(source_entry["expected_runner"]),
                "binding": dict(source_entry["expected_binding"]),
            },
            "source_fingerprint": dict(source_entry["source_fingerprint"]),
            "runner": {
                "action": runner_action,
                "live_action": runner_cls["action"],
                "conflict_fields": list(runner_cls["conflict_fields"]),
            },
            "binding": {
                "action": binding_action,
                "live_action": binding_cls["action"],
                "conflict_fields": list(binding_cls["conflict_fields"]),
                "binding_state": binding_cls.get("state"),
            },
            "requires_accept": bool(
                runner_cls["action"] == "update" or binding_cls["action"] == "update"
            ),
            "accept_change": bool(accept_change),
        }
    )
    return entry


def build_plan(
    *,
    server: Any,
    targets: Sequence[RegistryTarget],
    source_provider: Callable[[RegistryTarget], Any],
    client: Any,
    credential: Any,
    accept_change: bool = False,
) -> dict[str, Any]:
    """只读生成计划：显式 server/project/member/scope/来源/schema 全核验，零写。"""
    normalized_server = normalize_server(server)
    _require_client_server(client, normalized_server)
    if not isinstance(credential, str) or not credential.strip():
        raise AdapterRegistryError("E_CREDENTIAL_INVALID", field="credential")
    if not callable(source_provider):
        raise AdapterRegistryError("E_SOURCE_UNAVAILABLE", field="source_provider")
    if not isinstance(accept_change, bool):
        raise AdapterRegistryError("E_PLAN_INVALID", field="accept_change")
    target_list = tuple(targets)
    if not target_list:
        raise AdapterRegistryError("E_TARGETS_EMPTY", field="targets")

    view = _RegistryView(client, normalized_server, credential)
    entries = [
        _plan_entry(view, index, target, source_provider, accept_change)
        for index, target in enumerate(target_list)
    ]
    return {
        "schema": PLAN_SCHEMA,
        "server": normalized_server,
        "accept_change": accept_change,
        "entries": entries,
        "summary": _plan_summary(entries),
        "plan_status": _plan_status(entries),
    }


def plan_spec(
    spec: Any,
    *,
    client: Any,
    credential: Any,
    accept_change: bool = False,
) -> dict[str, Any]:
    """用显式来源清单（内存事实）生成计划；清单自带的 ready/指纹一律不采信。"""
    targets = iter_targets(spec)
    provider = spec_source_provider(spec)
    return build_plan(
        server=targets[0].server,
        targets=targets,
        source_provider=provider,
        client=client,
        credential=credential,
        accept_change=accept_change,
    )


# ---------------------------------------------------------------------------
# apply：受信写入（human 凭据 + 写后完整重判 + 零盲重试）
# ---------------------------------------------------------------------------


def _safe_metadata_field(value: Any) -> Optional[str]:
    """只允许已知形状的公开字段名回流；否则丢弃为 ``None``（不照抄原值）。"""
    if value is None:
        return None
    if not isinstance(value, str) or not _FIELD_NAME_PATTERN.fullmatch(value):
        return None
    if value not in _KNOWN_METADATA_FIELDS:
        return None
    if looks_like_credential(value):
        return None
    return value


def _safe_reason_code(value: Any) -> Optional[str]:
    """原因码只允许固定 token / ``http_NNN`` / 已知稳定错误码。"""
    if not isinstance(value, str):
        return None
    if _HTTP_REASON_PATTERN.fullmatch(value):
        return value
    if value in _REASON_TOKEN_WHITELIST or value in _KNOWN_REASON_CODES:
        return value
    return None


def _safe_metadata_fields(value: Any, *, allowed: Sequence[str]) -> list[str]:
    """字段名列表白名单：非列表/未知字段名一律丢弃，只保留已知字段。"""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    kept: list[str] = []
    for item in value:
        name = _safe_metadata_field(item)
        if name is not None and name in allowed:
            kept.append(name)
    return kept


def _sanitized_reason(value: Any) -> dict[str, Any]:
    """重建一条稳定阻断原因：未知 code 安全拒绝，其余值只回已知字段/原因码。"""
    if not isinstance(value, Mapping):
        raise AdapterRegistryError("E_PLAN_INVALID", field="blocked")
    code = value.get("code")
    if not isinstance(code, str) or code not in _KNOWN_REASON_CODES:
        raise AdapterRegistryError("E_PLAN_INVALID", field="blocked")
    detail = _REASON_DETAILS.get(code) or (getattr(facts, "_REASON_DETAILS", {}) or {}).get(code)
    if not isinstance(detail, str):
        raise AdapterRegistryError("E_PLAN_INVALID", field="blocked")
    item: dict[str, Any] = {
        "code": code,
        "field": _safe_metadata_field(value.get("field")),
        "detail": detail,
    }
    reason_code = _safe_reason_code(value.get("reason_code"))
    if reason_code is not None:
        item["reason_code"] = reason_code
    conflict_fields = _safe_metadata_fields(
        value.get("conflict_fields"),
        allowed=tuple(MUTABLE_RUNNER_FIELDS) + tuple(BINDING_READ_FIELDS),
    )
    if conflict_fields:
        item["conflict_fields"] = conflict_fields
    invalid_fields = _safe_metadata_fields(
        value.get("invalid_fields"),
        allowed=tuple(RUNNER_CREATE_FIELDS) + tuple(BINDING_READ_FIELDS),
    )
    if invalid_fields:
        item["invalid_fields"] = invalid_fields
    return item


def _sanitized_blocked(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AdapterRegistryError("E_PLAN_INVALID", field="blocked")
    return [_sanitized_reason(item) for item in value]


def _sanitized_expected(expected: Mapping[str, Any]) -> dict[str, Any]:
    """用既有 schema 重建 expected 载荷：未知/额外键直接拒绝，不照抄计划内容。"""
    raw_runner = expected.get("runner")
    raw_binding = expected.get("binding")
    if not isinstance(raw_runner, Mapping) or not isinstance(raw_binding, Mapping):
        raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
    try:
        runner = RunnerCreate(**{key: raw_runner.get(key) for key in RUNNER_CREATE_FIELDS})
    except (ValidationError, TypeError, ValueError) as exc:
        raise AdapterRegistryError("E_PLAN_INVALID", field="expected.runner") from exc
    try:
        binding = RoleBindingInput(
            **{key: raw_binding.get(key) for key in BINDING_READ_FIELDS}
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise AdapterRegistryError("E_PLAN_INVALID", field="expected.binding") from exc
    return {
        "runner": {key: getattr(runner, key) for key in RUNNER_CREATE_FIELDS},
        "binding": {key: getattr(binding, key) for key in BINDING_READ_FIELDS},
    }


def _validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise AdapterRegistryError("E_PLAN_INVALID", field="plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise AdapterRegistryError("E_PLAN_INVALID", field="schema")
    server = normalize_server(plan.get("server"))
    accept_change = plan.get("accept_change")
    if not isinstance(accept_change, bool):
        raise AdapterRegistryError("E_PLAN_INVALID", field="accept_change")
    entries = plan.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or not entries:
        raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
    checked: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
        if entry.get("status") not in ("ready", "blocked"):
            raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
        raw_index = entry.get("index", index)
        if (
            not isinstance(raw_index, int)
            or isinstance(raw_index, bool)
            or raw_index != index
        ):
            # 计划可被手工改过：index 必须是严格合法整型且与顺序一致。
            raise AdapterRegistryError("E_PLAN_INVALID", field="index")
        record = {
            "index": raw_index,
            "adapter": _target_label(entry.get("adapter"), field="adapter"),
            "member_id": _target_label(entry.get("member_id"), field="member_id"),
            "project_id": _target_label(entry.get("project_id"), field="project_id"),
            "status": entry["status"],
            "blocked": _sanitized_blocked(entry.get("blocked")),
        }
        if entry["status"] == "ready":
            expected = entry.get("expected")
            fingerprint = entry.get("source_fingerprint")
            runner_meta = entry.get("runner")
            binding_meta = entry.get("binding")
            if not isinstance(expected, Mapping) or not isinstance(fingerprint, Mapping):
                raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
            fingerprint_value = fingerprint.get("fingerprint")
            if not isinstance(fingerprint_value, str) or not re.fullmatch(
                r"[0-9a-f]{32}(?:[0-9a-f]{32})?", fingerprint_value
            ):
                raise AdapterRegistryError("E_PLAN_INVALID", field="source_fingerprint")
            if not isinstance(runner_meta, Mapping) or not isinstance(binding_meta, Mapping):
                raise AdapterRegistryError("E_PLAN_INVALID", field="entries")
            for meta, side in ((runner_meta, "runner"), (binding_meta, "binding")):
                if meta.get("action") not in READ_ACTIONS:
                    raise AdapterRegistryError("E_PLAN_INVALID", field=side)
            record.update(
                {
                    "expected": _sanitized_expected(expected),
                    "source_fingerprint": {"fingerprint": fingerprint_value},
                    "runner": {
                        "action": runner_meta["action"],
                        "conflict_fields": _safe_metadata_fields(
                            runner_meta.get("conflict_fields"),
                            allowed=MUTABLE_RUNNER_FIELDS,
                        ),
                    },
                    "binding": {
                        "action": binding_meta["action"],
                        "conflict_fields": _safe_metadata_fields(
                            binding_meta.get("conflict_fields"),
                            allowed=BINDING_READ_FIELDS,
                        ),
                    },
                }
            )
        checked.append(record)
    return {
        "schema": PLAN_SCHEMA,
        "server": server,
        "accept_change": accept_change,
        "entries": checked,
    }


def _cross_check_spec(spec: Any, plan: Mapping[str, Any]) -> None:
    """apply 时重核显式来源清单与计划的服务地址/目标一致（不一致即拒，零写）。"""
    targets = iter_targets(spec)
    if targets[0].server != plan["server"]:
        raise AdapterRegistryError("E_SERVER_MISMATCH", field="spec")
    plan_keys = [
        (entry["project_id"], entry["member_id"], entry["adapter"]) for entry in plan["entries"]
    ]
    spec_keys = [(item.project_id, item.member_id, item.adapter) for item in targets]
    if plan_keys != spec_keys:
        raise AdapterRegistryError("E_PLAN_PARAM_MISMATCH", field="targets")


def _empty_result_entry(plan_entry: Mapping[str, Any]) -> dict[str, Any]:
    def step(action: Optional[str]) -> dict[str, Any]:
        return {
            "action": action,
            "live_action": None,
            "outcome": "skipped",
            "http_status": None,
            "write": "none",
            "write_outcome": None,
            "conflict_fields": [],
        }

    runner_action = (plan_entry.get("runner") or {}).get("action")
    binding_action = (plan_entry.get("binding") or {}).get("action")
    return {
        "index": plan_entry.get("index"),
        "adapter": plan_entry.get("adapter"),
        "member_id": plan_entry.get("member_id"),
        "project_id": plan_entry.get("project_id"),
        "status": "blocked",
        "runner": step(runner_action),
        "binding": step(binding_action),
        "blocked": [],
        "writes": {"post_runner": 0, "patch_runner": 0, "put_binding": 0},
        "recovery": {"resume": False, "reason": None},
    }


def _entry_status(result: dict[str, Any]) -> str:
    runner_outcome = result["runner"]["outcome"]
    binding_outcome = result["binding"]["outcome"]
    if runner_outcome in ("failed",) or binding_outcome in ("failed",):
        return "failed"
    if runner_outcome in ("unknown",) or binding_outcome in ("unknown",):
        return "unknown"
    if runner_outcome == "blocked" or binding_outcome == "blocked":
        wrote = any(value for value in result["writes"].values())
        return "partial" if wrote else "blocked"
    if runner_outcome in ("created", "patched") or binding_outcome == "bound":
        return "applied"
    return "no_op"


def _apply_runner_step(
    view: _RegistryView,
    plan_entry: Mapping[str, Any],
    *,
    accept_change: bool,
) -> dict[str, Any]:
    step = {
        "action": plan_entry["runner"]["action"],
        "live_action": None,
        "outcome": "skipped",
        "http_status": None,
        "write": "none",
        "write_outcome": None,
        "conflict_fields": [],
    }
    expected_runner = plan_entry["expected"]["runner"]
    plan_action = plan_entry["runner"]["action"]
    plan_conflicts = sorted(plan_entry["runner"]["conflict_fields"])

    runners_read = view.list_runners()
    if runners_read["outcome"] != "ok":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_RUNNER_READ_FAILED", field="runners", reason_code=runners_read["reason"]
        )
        return step
    classification = _classify_runner(runners_read["runners"], expected_runner)
    step["live_action"] = classification["action"]
    step["conflict_fields"] = list(classification["conflict_fields"])

    if classification["action"] == "blocked":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason(
            classification["reason_code"], field="runner", reason_code=classification.get("detail")
        )
        return step
    if classification["action"] == "no_op":
        step["outcome"] = "no_op"
        return step
    if classification["action"] == "update":
        if not accept_change:
            step["outcome"] = "blocked"
            step["blocked_reason"] = _reason("E_CHANGE_NOT_ACCEPTED", field="runner")
            return step
        if plan_action != "update" or sorted(classification["conflict_fields"]) != plan_conflicts:
            step["outcome"] = "blocked"
            step["blocked_reason"] = _reason("E_STATE_DRIFT", field="runner")
            return step
        response = view.patch_runner(
            expected_runner["runner_id"],
            {key: expected_runner[key] for key in MUTABLE_RUNNER_FIELDS},
        )
        step["write"] = "patch"
        step["http_status"] = response["status"]
        step["write_outcome"] = _write_outcome(response)
        return _confirm_runner_step(view, step, expected_runner)

    # classification == create
    if plan_action != "create":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason("E_STATE_DRIFT", field="runner")
        return step
    response = view.post_runner({key: expected_runner[key] for key in RunnerCreate.model_fields})
    step["write"] = "post"
    step["http_status"] = response["status"]
    step["write_outcome"] = _write_outcome(response)
    return _confirm_runner_step(view, step, expected_runner)


def _write_outcome(response: Mapping[str, Any]) -> str:
    status = response.get("status")
    outcome = response.get("outcome")
    if outcome == "ok":
        return f"ok:{status}"
    if outcome == "http_error":
        return f"http_error:{status}"
    return str(outcome)


def _write_outcome_explicit_failure(
    write_outcome: Any, *, allow_existing_409: bool = False
) -> bool:
    """写请求是否返回**明确失败**的 HTTP 结果（合同 §6）。

    - 只有 ``POST`` 登记写请求的 ``409`` 属于已批准的同事实重分类，调用方须显式传入
      ``allow_existing_409=True``；``PATCH`` / ``PUT`` 的任何明确失败 HTTP（含 ``409``）
      都不得宣称成功，也不得据此继续本条绑定；
    - ``timeout`` / 未知传输 / 非 JSON 正文属于“结果未知”，仍走最新只读读回判定，
      但读回本身不把本次写请求改写成成功。
    """
    if not isinstance(write_outcome, str) or not write_outcome.startswith("http_error:"):
        return False
    if allow_existing_409 and write_outcome.split(":", 1)[1] == "409":
        return False
    return True


def _confirm_runner_step(
    view: _RegistryView, step: dict[str, Any], expected_runner: Mapping[str, Any]
) -> dict[str, Any]:
    """写后**必须**最新 GET /api/runners 完整重判；不确定即该条 binding PUT=0。

    写返回明确失败时仍读回并保留观察事实（``live_action`` / ``conflict_fields``），
    但**不得**据此宣称 ``created`` / ``patched``，也不得继续本条绑定。
    只有 ``POST`` 的 ``409`` 属于已批准的同事实重分类，其它方法的 ``409`` 是明确失败。
    """
    explicit_failure = _write_outcome_explicit_failure(
        step.get("write_outcome"), allow_existing_409=step.get("write") == "post"
    )
    runners_read = view.list_runners()
    if runners_read["outcome"] != "ok":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_RUNNER_READ_FAILED", field="runners", reason_code=runners_read["reason"]
        )
        return step
    classification = _classify_runner(runners_read["runners"], expected_runner)
    step["live_action"] = classification["action"]
    step["conflict_fields"] = list(classification["conflict_fields"])
    if explicit_failure:
        step["outcome"] = "failed"
        step["blocked_reason"] = _reason(
            "E_WRITE_FAILED", field="runner", reason_code=step.get("write_outcome")
        )
        return step
    if classification["action"] == "no_op":
        step["outcome"] = "created" if step["write"] == "post" else "patched"
        return step
    if classification["action"] == "blocked":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason(
            classification["reason_code"], field="runner", reason_code=classification.get("detail")
        )
        return step
    if classification["action"] == "update":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason("E_RUNNER_CONFLICT", field="runner")
        return step
    step["outcome"] = "unknown"
    step["blocked_reason"] = _reason("E_RUNNER_NOT_CONFIRMED", field="runner")
    return step


def _apply_binding_step(
    view: _RegistryView,
    target: RegistryTarget,
    plan_entry: Mapping[str, Any],
    *,
    accept_change: bool,
) -> dict[str, Any]:
    step = {
        "action": plan_entry["binding"]["action"],
        "live_action": None,
        "outcome": "skipped",
        "http_status": None,
        "write": "none",
        "write_outcome": None,
        "conflict_fields": [],
        "binding_state": None,
    }
    expected_binding = plan_entry["expected"]["binding"]
    plan_action = plan_entry["binding"]["action"]
    plan_conflicts = sorted(plan_entry["binding"]["conflict_fields"])

    binding_read = view.get_binding(target.project_id, target.member_id)
    if binding_read["outcome"] != "ok":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_BINDING_READ_FAILED",
            field="binding",
            reason_code=(
                f"http_{binding_read['status']}"
                if binding_read["status"] is not None
                else binding_read["outcome"]
            ),
        )
        return step
    data = binding_read["data"]
    if data["project_id"] != target.project_id or data["member_id"] != target.member_id:
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason(
            "E_STATE_DRIFT", field="binding", reason_code="project_member_mismatch"
        )
        return step
    classification = _classify_binding(data, expected_binding)
    step["live_action"] = classification["action"]
    step["conflict_fields"] = list(classification["conflict_fields"])
    step["binding_state"] = classification.get("state")

    if classification["action"] == "blocked":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason(
            classification["reason_code"], field="binding", reason_code=classification.get("state")
        )
        return step
    if classification["action"] == "no_op":
        step["outcome"] = "no_op"
        return step
    if classification["action"] == "update":
        if not accept_change:
            step["outcome"] = "blocked"
            step["blocked_reason"] = _reason("E_CHANGE_NOT_ACCEPTED", field="binding")
            return step
        if plan_action != "update" or sorted(classification["conflict_fields"]) != plan_conflicts:
            step["outcome"] = "blocked"
            step["blocked_reason"] = _reason("E_STATE_DRIFT", field="binding")
            return step
    elif classification["action"] == "create" and plan_action != "create":
        step["outcome"] = "blocked"
        step["blocked_reason"] = _reason("E_STATE_DRIFT", field="binding")
        return step

    response = view.put_binding(
        target.project_id,
        target.member_id,
        {key: expected_binding[key] for key in BINDING_READ_FIELDS},
    )
    step["write"] = "put"
    step["http_status"] = response["status"]
    step["write_outcome"] = _write_outcome(response)
    return _confirm_binding_step(view, step, target, expected_binding)


def _confirm_binding_step(
    view: _RegistryView,
    step: dict[str, Any],
    target: RegistryTarget,
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """写后只读核 project/member、七字段与 bound；超时先 GET，不盲重试 PUT。

    PUT 返回明确失败 HTTP 时，即使读回到 bound 也只记录观察事实，
    不把本次写请求宣称成功（分开“观察事实”与“写结果”）。
    ``PUT`` 不享有 ``409`` 同事实重分类豁免，也至多写一次、不盲重试。
    """
    explicit_failure = _write_outcome_explicit_failure(
        step.get("write_outcome"), allow_existing_409=False
    )
    binding_read = view.get_binding(target.project_id, target.member_id)
    if binding_read["outcome"] != "ok":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_BINDING_READ_FAILED",
            field="binding",
            reason_code=(
                f"http_{binding_read['status']}"
                if binding_read["status"] is not None
                else binding_read["outcome"]
            ),
        )
        return step
    data = binding_read["data"]
    if data["project_id"] != target.project_id or data["member_id"] != target.member_id:
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_STATE_DRIFT", field="binding", reason_code="project_member_mismatch"
        )
        return step
    classification = _classify_binding(data, expected_binding)
    step["live_action"] = classification["action"]
    step["binding_state"] = classification.get("state")
    step["conflict_fields"] = list(classification["conflict_fields"])
    if explicit_failure:
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            "E_WRITE_FAILED", field="binding", reason_code=step.get("write_outcome")
        )
        return step
    if classification["action"] == "no_op":
        step["outcome"] = "bound"
        return step
    if classification["action"] == "update":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason("E_BINDING_NOT_CONFIRMED", field="binding")
        return step
    if classification["action"] == "blocked":
        step["outcome"] = "unknown"
        step["blocked_reason"] = _reason(
            classification["reason_code"], field="binding", reason_code=classification.get("state")
        )
        return step
    step["outcome"] = "unknown"
    step["blocked_reason"] = _reason("E_BINDING_NOT_CONFIRMED", field="binding")
    return step


def _apply_entry(
    view: _RegistryView,
    plan_entry: Mapping[str, Any],
    plan: Mapping[str, Any],
    source_provider: Callable[[RegistryTarget], Any],
    *,
    accept_change: bool,
) -> dict[str, Any]:
    target = RegistryTarget(
        server=plan["server"],
        project_id=plan_entry["project_id"],
        member_id=plan_entry["member_id"],
        adapter=plan_entry["adapter"],
    )
    result = _empty_result_entry(plan_entry)

    if plan_entry["status"] != "ready":
        result["blocked"] = list(plan_entry.get("blocked") or []) + [
            _reason("E_PLAN_ENTRY_BLOCKED", field="entry")
        ]
        result["recovery"] = {"resume": False, "reason": "E_PLAN_ENTRY_BLOCKED"}
        return result

    try:
        raw = source_provider(target)
    except Exception:  # noqa: BLE001 - 来源边界异常不回流正文
        raw = None
    fresh = _build_source_entry(target, raw)
    if fresh["status"] != "ready":
        code = "E_SOURCE_UNAVAILABLE" if not isinstance(raw, Mapping) else "E_SOURCE_DRIFT"
        result["blocked"] = list(fresh.get("blocked") or []) + [
            _reason(code, field="source_facts")
        ]
        result["recovery"] = {"resume": False, "reason": code}
        return result
    if (
        fresh["source_fingerprint"]["fingerprint"]
        != plan_entry["source_fingerprint"]["fingerprint"]
    ):
        result["blocked"] = [_reason("E_SOURCE_DRIFT", field="source_fingerprint")]
        result["recovery"] = {"resume": False, "reason": "E_SOURCE_DRIFT"}
        return result
    if not _same(
        {
            "runner": fresh["expected_runner"],
            "binding": fresh["expected_binding"],
        },
        plan_entry["expected"],
    ):
        result["blocked"] = [_reason("E_PLAN_STALE", field="expected")]
        result["recovery"] = {"resume": False, "reason": "E_PLAN_STALE"}
        return result

    project = view.get_project(target.project_id)
    if project["outcome"] != "ok":
        result["blocked"] = [
            _reason(
                "E_STATE_UNREADABLE",
                field="project",
                reason_code=(
                    f"http_{project['status']}"
                    if project["status"] is not None
                    else project["outcome"]
                ),
            )
        ]
        result["recovery"] = {"resume": True, "reason": "E_STATE_UNREADABLE"}
        return result

    eligibility = view.get_binding(target.project_id, target.member_id)
    if eligibility["outcome"] != "ok":
        result["blocked"] = [
            _reason(
                "E_BINDING_READ_FAILED",
                field="binding",
                reason_code=(
                    f"http_{eligibility['status']}"
                    if eligibility["status"] is not None
                    else eligibility["outcome"]
                ),
            )
        ]
        result["recovery"] = {"resume": True, "reason": "E_BINDING_READ_FAILED"}
        return result
    eligibility_data = eligibility["data"]
    if (
        eligibility_data["project_id"] != target.project_id
        or eligibility_data["member_id"] != target.member_id
    ):
        result["blocked"] = [
            _reason("E_STATE_DRIFT", field="binding", reason_code="project_member_mismatch")
        ]
        result["recovery"] = {"resume": False, "reason": "E_STATE_DRIFT"}
        return result
    state = eligibility_data["binding_state"]
    if state in TARGET_BLOCKED_STATES:
        result["blocked"] = [
            _reason("E_TARGET_NOT_ELIGIBLE", field="member_id", reason_code=state)
        ]
        result["recovery"] = {"resume": False, "reason": "E_TARGET_NOT_ELIGIBLE"}
        return result
    if state is not None and state not in (
        ROLE_BINDING_UNCONFIGURED,
        ROLE_BINDING_BOUND,
        "partial",
        "runner_missing",
        "runner_retired",
    ):
        result["blocked"] = [
            _reason("E_STATE_UNREADABLE", field="binding_state", reason_code=str(state))
        ]
        result["recovery"] = {"resume": False, "reason": "E_STATE_UNREADABLE"}
        return result

    agents = view.list_agents(target.project_id)
    if agents["outcome"] != "ok":
        result["blocked"] = [
            _reason(
                "E_STATE_UNREADABLE",
                field="agents",
                reason_code=(
                    f"http_{agents['status']}"
                    if agents["status"] is not None
                    else agents["outcome"]
                ),
            )
        ]
        result["recovery"] = {"resume": True, "reason": "E_STATE_UNREADABLE"}
        return result
    if target.member_id not in {item["member_id"] for item in agents["members"]}:
        result["blocked"] = [
            _reason("E_TARGET_NOT_ELIGIBLE", field="member_id", reason_code="not_in_roster")
        ]
        result["recovery"] = {"resume": False, "reason": "E_TARGET_NOT_ELIGIBLE"}
        return result

    runner_step = _apply_runner_step(view, plan_entry, accept_change=accept_change)
    result["runner"] = runner_step
    if runner_step["outcome"] in ("blocked", "failed", "unknown"):
        result["writes"]["post_runner"] = 1 if runner_step["write"] == "post" else 0
        result["writes"]["patch_runner"] = 1 if runner_step["write"] == "patch" else 0
        result["blocked"] = [runner_step["blocked_reason"]]
        result["recovery"] = {
            "resume": runner_step["outcome"] != "blocked",
            "reason": runner_step["blocked_reason"]["code"],
        }
        result["status"] = _entry_status(result)
        return result
    result["writes"]["post_runner"] = 1 if runner_step["write"] == "post" else 0
    result["writes"]["patch_runner"] = 1 if runner_step["write"] == "patch" else 0

    binding_step = _apply_binding_step(view, target, plan_entry, accept_change=accept_change)
    result["binding"] = binding_step
    result["writes"]["put_binding"] = 1 if binding_step["write"] == "put" else 0
    if binding_step["outcome"] in ("blocked", "failed", "unknown"):
        result["blocked"] = [binding_step["blocked_reason"]]
        result["recovery"] = {
            "resume": binding_step["outcome"] != "blocked",
            "reason": binding_step["blocked_reason"]["code"],
        }
        result["status"] = _entry_status(result)
        return result

    result["status"] = _entry_status(result)
    result["recovery"] = {"resume": False, "reason": None}
    return result


def _result_summary(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(entries),
        "applied": sum(1 for entry in entries if entry.get("status") == "applied"),
        "no_op": sum(1 for entry in entries if entry.get("status") == "no_op"),
        "partial": sum(1 for entry in entries if entry.get("status") == "partial"),
        "blocked": sum(1 for entry in entries if entry.get("status") == "blocked"),
        "failed": sum(1 for entry in entries if entry.get("status") == "failed"),
        "unknown": sum(1 for entry in entries if entry.get("status") == "unknown"),
        "runner_writes": sum(entry["writes"]["post_runner"] + entry["writes"]["patch_runner"] for entry in entries),
        "binding_writes": sum(entry["writes"]["put_binding"] for entry in entries),
    }


def _result_status(entries: Sequence[Mapping[str, Any]]) -> str:
    if all(entry.get("status") in ("applied", "no_op") for entry in entries):
        return "complete"
    if any(entry.get("status") in ("applied", "no_op", "partial") for entry in entries):
        return "partial"
    return "failed"


def apply_plan(
    *,
    plan: Any,
    client: Any,
    credential: Any,
    source_provider: Optional[Callable[[RegistryTarget], Any]] = None,
    spec: Any = None,
    accept_change: Optional[bool] = None,
    server: Any = None,
) -> dict[str, Any]:
    """受信应用：human 身份 → 参数/来源重核 → 逐条写后完整重判，零盲重试。"""
    checked_plan = _validate_plan(plan)
    if accept_change is not None and not isinstance(accept_change, bool):
        # 显式 accept-change 必须是严格布尔；字符串/数字/容器不得因 truthy 获得变更授权。
        raise AdapterRegistryError("E_PLAN_INVALID", field="accept_change")
    effective_accept = (
        checked_plan["accept_change"] if accept_change is None else accept_change
    )
    if effective_accept != checked_plan["accept_change"]:
        raise AdapterRegistryError("E_PLAN_PARAM_MISMATCH", field="accept_change")
    plan_server = checked_plan["server"]
    if server is not None and normalize_server(server) != plan_server:
        raise AdapterRegistryError("E_SERVER_MISMATCH", field="server")
    _require_client_server(client, plan_server)
    if not isinstance(credential, str) or not credential.strip():
        raise AdapterRegistryError("E_CREDENTIAL_INVALID", field="credential")
    if source_provider is None:
        if spec is None:
            raise AdapterRegistryError("E_SOURCE_UNAVAILABLE", field="source_provider")
        _cross_check_spec(spec, checked_plan)
        provider: Callable[[RegistryTarget], Any] = spec_source_provider(spec)
    else:
        if spec is not None:
            raise AdapterRegistryError("E_SPEC_INVALID", field="spec")
        if not callable(source_provider):
            raise AdapterRegistryError("E_SOURCE_UNAVAILABLE", field="source_provider")
        provider = source_provider

    view = _RegistryView(client, plan_server, credential)
    identity_result = view.me()
    if identity_result["outcome"] != "ok" or (
        (identity_result["identity"] or {}).get("kind") != "human"
    ):
        code = "E_IDENTITY_UNVERIFIED"
        reason = _reason(
            code,
            field="identity",
            reason_code=(
                f"http_{identity_result['status']}"
                if identity_result["status"] is not None
                else identity_result["outcome"]
            ),
        )
        entries = []
        for plan_entry in checked_plan["entries"]:
            entry = _empty_result_entry(plan_entry)
            entry["blocked"] = [reason]
            entry["recovery"] = {"resume": False, "reason": code}
            entries.append(entry)
        return {
            "schema": RESULT_SCHEMA,
            "server": plan_server,
            "accept_change": effective_accept,
            "identity": {"verified": False, "kind": None, "reason": reason},
            "entries": entries,
            "summary": _result_summary(entries),
            "result_status": "blocked",
        }

    entries = [
        _apply_entry(view, plan_entry, checked_plan, provider, accept_change=effective_accept)
        for plan_entry in checked_plan["entries"]
    ]
    return {
        "schema": RESULT_SCHEMA,
        "server": plan_server,
        "accept_change": effective_accept,
        "identity": {"verified": True, "kind": "human", "reason": None},
        "entries": entries,
        "summary": _result_summary(entries),
        "result_status": _result_status(entries),
    }


# ---------------------------------------------------------------------------
# verify：只读核验已应用结果
# ---------------------------------------------------------------------------


def verify_plan(
    *,
    plan: Any,
    client: Any,
    credential: Any,
    server: Any = None,
) -> dict[str, Any]:
    """只读核验：运行器存在/未 retired/四字段一致，绑定七字段一致且 bound。"""
    checked_plan = _validate_plan(plan)
    plan_server = checked_plan["server"]
    if server is not None and normalize_server(server) != plan_server:
        raise AdapterRegistryError("E_SERVER_MISMATCH", field="server")
    _require_client_server(client, plan_server)
    if not isinstance(credential, str) or not credential.strip():
        raise AdapterRegistryError("E_CREDENTIAL_INVALID", field="credential")

    view = _RegistryView(client, plan_server, credential)
    entries: list[dict[str, Any]] = []
    for plan_entry in checked_plan["entries"]:
        record: dict[str, Any] = {
            "index": plan_entry["index"],
            "adapter": plan_entry["adapter"],
            "member_id": plan_entry["member_id"],
            "project_id": plan_entry["project_id"],
            "verified": False,
            "blocked": [],
            "runner": {"present": False, "runtime_ok": False, "retired": False, "field_differences": []},
            "binding": {"binding_state": None, "bound": False, "seven_field_differences": []},
        }
        if plan_entry["status"] != "ready":
            record["blocked"] = list(plan_entry.get("blocked") or []) + [
                _reason("E_PLAN_ENTRY_BLOCKED", field="entry")
            ]
            entries.append(record)
            continue
        target = RegistryTarget(
            server=plan_server,
            project_id=plan_entry["project_id"],
            member_id=plan_entry["member_id"],
            adapter=plan_entry["adapter"],
        )
        runners_read = view.list_runners()
        if runners_read["outcome"] != "ok":
            record["blocked"].append(
                _reason("E_RUNNER_READ_FAILED", field="runners", reason_code=runners_read["reason"])
            )
            entries.append(record)
            continue
        runner_class = _classify_runner(
            runners_read["runners"], plan_entry["expected"]["runner"]
        )
        record["runner"]["present"] = runner_class["action"] != "create"
        record["runner"]["retired"] = runner_class["reason_code"] == "E_RUNNER_RETIRED"
        record["runner"]["runtime_ok"] = runner_class["reason_code"] != "E_RUNNER_RUNTIME_CONFLICT"
        record["runner"]["field_differences"] = list(runner_class["conflict_fields"])

        binding_read = view.get_binding(target.project_id, target.member_id)
        if binding_read["outcome"] != "ok":
            record["blocked"].append(
                _reason(
                    "E_BINDING_READ_FAILED",
                    field="binding",
                    reason_code=(
                        f"http_{binding_read['status']}"
                        if binding_read["status"] is not None
                        else binding_read["outcome"]
                    ),
                )
            )
            entries.append(record)
            continue
        data = binding_read["data"]
        if (
            data["project_id"] != target.project_id
            or data["member_id"] != target.member_id
        ):
            record["blocked"].append(
                _reason("E_STATE_DRIFT", field="binding", reason_code="project_member_mismatch")
            )
            entries.append(record)
            continue
        binding_class = _classify_binding(data, plan_entry["expected"]["binding"])
        record["binding"]["binding_state"] = binding_class.get("state")
        record["binding"]["bound"] = binding_class["action"] == "no_op"
        if binding_class["action"] == "update":
            record["binding"]["seven_field_differences"] = list(
                binding_class["conflict_fields"]
            )
        elif binding_class["action"] == "blocked":
            record["blocked"].append(
                _reason(
                    binding_class["reason_code"],
                    field="binding",
                    reason_code=binding_class.get("state"),
                )
            )
        record["verified"] = (
            runner_class["action"] == "no_op" and binding_class["action"] == "no_op"
        )
        entries.append(record)

    return {
        "schema": VERIFY_SCHEMA,
        "server": plan_server,
        "entries": entries,
        "summary": {
            "total": len(entries),
            "verified": sum(1 for entry in entries if entry["verified"]),
            "unverified": sum(1 for entry in entries if not entry["verified"]),
        },
        "verify_status": (
            "verified"
            if entries and all(entry["verified"] for entry in entries)
            else ("partial" if any(entry["verified"] for entry in entries) else "unverified")
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_client(server: str, timeout: float) -> Any:
    import httpx  # 局部导入：模块导入期不引入网络栈

    return httpx.Client(base_url=server, timeout=httpx.Timeout(timeout))


# 未知/错误参数只给固定用法错误码与已知参数名，不回显原 argv（可能夹带凭据形态）。
_CLI_USAGE_ERROR = (
    "E_CLI_USAGE: 参数或子命令不合法；"
    "已知子命令 plan|apply|verify，已知参数 "
    "--spec --plan --out --accept-change --server --timeout --key-env --key-file（--help 查看用法）"
)


class _StableArgumentParser(argparse.ArgumentParser):
    """argparse 默认错误会回显原 argv；这里统一替换成固定的稳定用法错误。"""

    def error(self, message: str) -> Any:  # noqa: ARG002 - 不回显 argparse 原文
        sys.stderr.write(_CLI_USAGE_ERROR + "\n")
        raise SystemExit(2)


def _http_timeout(value: Any) -> float:
    """``--timeout`` 必须是严格有限正值；非法值只触发稳定用法错误。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = _StableArgumentParser(
        prog="talk_adapter_registry.py",
        description=(
            "适配收尾受信应用（C2）：plan 只读生成计划、apply 由 human 凭据受信应用、"
            "verify 只读核验。凭据只来自 --key-env 或仓库外 --key-file，没有明文 --key。"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_credential_args(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--key-env",
            default=None,
            help=(
                "凭据所在环境变量名（不打印值，无隐式默认来源；"
                f"约定名 {DEFAULT_KEY_ENV}）"
            ),
        )
        target.add_argument("--key-file", default=None, help="仓库外的凭据文件路径")
        target.add_argument("--server", default=None, help="显式服务根地址（须与清单/计划一致）")
        target.add_argument(
            "--timeout",
            type=_http_timeout,
            default=DEFAULT_HTTP_TIMEOUT_SECONDS,
            help="单次 HTTP 超时秒数（严格有限正值；本片不长等待）",
        )

    plan_parser = sub.add_parser("plan", help="只读生成计划（GET only，零写）")
    plan_parser.add_argument("--spec", required=True, help="来源清单 JSON 路径")
    plan_parser.add_argument("--out", default=None, help="计划输出路径（默认打印到 stdout）")
    plan_parser.add_argument("--accept-change", action="store_true", help="显式接受既有差异")
    add_credential_args(plan_parser)

    apply_parser = sub.add_parser("apply", help="按计划受信应用（human 凭据）")
    apply_parser.add_argument("--plan", required=True, help="plan 生成的计划 JSON 路径")
    apply_parser.add_argument("--spec", required=True, help="本次重新读取的来源清单 JSON 路径")
    apply_parser.add_argument("--accept-change", action="store_true", help="显式接受既有差异")
    add_credential_args(apply_parser)

    verify_parser = sub.add_parser("verify", help="只读核验已应用结果")
    verify_parser.add_argument("--plan", required=True, help="plan 生成的计划 JSON 路径")
    add_credential_args(verify_parser)
    return parser


def _emit(payload: Any, out_path: Optional[str]) -> None:
    if out_path:
        _write_json_document(out_path, payload)
        return
    sys.stdout.write(json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    # argparse 用法错误（未知子命令/参数、非法 --timeout）由 _StableArgumentParser
    # 统一转成固定 E_CLI_USAGE + 退出码 2；--help 仍走 0。
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        credential = load_credential(key_env=args.key_env, key_file=args.key_file)
        if args.command == "plan":
            spec = _read_json_document(args.spec, code="E_SPEC_INVALID")
            # 先核 JSON 根/清单形状，再取 server：[]/null 根不得逃出稳定错误边界。
            targets = iter_targets(spec)
            server = normalize_server(args.server) if args.server else targets[0].server
            client = _default_client(server, args.timeout)
            payload = plan_spec(
                spec,
                client=client,
                credential=credential,
                accept_change=bool(args.accept_change),
            )
            _emit(payload, args.out)
            return 0 if payload["plan_status"] == "complete" else 1
        if args.command == "apply":
            plan = _read_json_document(args.plan, code="E_PLAN_INVALID")
            spec = _read_json_document(args.spec, code="E_SPEC_INVALID")
            checked = _validate_plan(plan)
            if args.server and normalize_server(args.server) != checked["server"]:
                raise AdapterRegistryError("E_SERVER_MISMATCH", field="server")
            client = _default_client(checked["server"], args.timeout)
            payload = apply_plan(
                plan=plan,
                spec=spec,
                client=client,
                credential=credential,
                accept_change=bool(args.accept_change),
            )
            _emit(payload, None)
            return 0 if payload["result_status"] == "complete" else 1
        plan = _read_json_document(args.plan, code="E_PLAN_INVALID")
        checked = _validate_plan(plan)
        if args.server and normalize_server(args.server) != checked["server"]:
            raise AdapterRegistryError("E_SERVER_MISMATCH", field="server")
        client = _default_client(checked["server"], args.timeout)
        payload = verify_plan(plan=plan, client=client, credential=credential)
        _emit(payload, None)
        return 0 if payload["verify_status"] == "verified" else 1
    except AdapterRegistryError as exc:
        # 只回稳定原因码/已知字段名：不含凭据、路径正文、raw body 或 traceback。
        sys.stderr.write(f"{exc}\n")
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        # 兜底输入/形状/IO 失败边界：同样只回固定原因码，不吐 traceback。
        sys.stderr.write("E_CLI_INVALID_INPUT\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
