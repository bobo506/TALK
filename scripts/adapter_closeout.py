#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C3 适配收尾共享入口：``run_closeout`` 与 K28 显式 ``closeout`` 子命令。

正式依据
--------
- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_DESIGN.md`` §3–§7：显式 scope、来源确认顺序、
  公开白名单与漂移指纹、plan / apply / verify 与人工受权写入；
- ``docs/spec/ADAPTER_BINDING_CLOSEOUT_IMPLEMENTATION_PLAN.md`` §3（C3）：共享
  ``adapter_closeout.py::run_closeout`` 加 K28 显式 closeout 子命令，显式只读加载 native
  有效来源、核选择/覆盖层/scope，先输出可审阅补登记 dry-run；真实应用再交人类确认。

本模块做什么
------------
- 只在**显式动作**下工作：``plan`` / ``dry-run`` / ``verify`` 全程只读，``apply`` 必须由
  显式动作 + human 凭据触发，并完整复用 C2 的 ``apply_plan``（human 身份、参数/来源重核、
  写后最新读回、零盲重试）；
- native 来源由本入口**显式只读加载**：只有当前运行入口实际会解析到的文件（``KIMI_CODE_HOME``
  或默认 home），叠加不可证明的覆盖层检查与真实 argv 的完整受控契约（alias、受控命令、
  执行分级），全部成立才把来源标记为 ``confirmed``。显式 ``--native-config`` 指向未被
  入口选中的文件时一律 ``blocked``；读到文件、摘要正确或传入 fixture 本身都不构成 confirmed；
- ``plan`` 只输出可审阅计划、公开来源证据、拟新增/no_op/差异/冲突与恢复索引，以及供人工
  审批的 application 包草稿。该包只按白名单投影输入，写计数与条目从有效 C2 计划条目重算；
  本轮不执行生产 apply。

本模块不做什么
--------------
- 不启动 bridge / 服务 / 模型 / 子进程，不调用 MCP 工具，不注册成员，不同步名册；
- 不创建、复制、修改凭据或扩大 ACL；CLI 只接受显式 ``--key-env`` 或仓库外 ``--key-file``，
  没有明文 ``--key`` 参数；
- 不把整份 native 配置、provenance 内部摘要、原始来源路径或凭据写进任何产物/日志；
- 不把登记挂到 launch / 心跳 / claim / 首次接入 / MCP 初始化 / 后台任务上。

退出码：``0`` ready / applied / verified；``1`` blocked / partial；``2`` 用法或输入错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
# 复用既有模块：仓库根（``server.models``）与 scripts 目录（C1/C2/K28 入口）。
# 只调整 ``sys.path``，不打开文件、不读环境、不触网、不启进程。
for _path_entry in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

import adapter_binding_facts as facts  # noqa: E402
import kimi_k28_executor as k28  # noqa: E402
import talk_adapter_registry as registry  # noqa: E402
# 复用既有凭据形状判定（``registry`` 已导入同一函数，不新增重依赖）。
from server.models import looks_like_credential  # noqa: E402

__all__ = [
    "ACTIONS",
    "APPLICATION_SCHEMA",
    "CloseoutError",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "VERIFY_SCHEMA",
    "argv_selection_evidence",
    "build_application_package",
    "load_effective_native_source",
    "main",
    "native_source_record",
    "run_closeout",
]

# ---------------------------------------------------------------------------
# schema 标识与常量
# ---------------------------------------------------------------------------

PLAN_SCHEMA = "adapter-closeout-plan-v1"
RESULT_SCHEMA = "adapter-closeout-result-v1"
VERIFY_SCHEMA = "adapter-closeout-verify-v1"
APPLICATION_SCHEMA = "adapter-closeout-application-v1"

ACTIONS: tuple[str, ...] = ("plan", "dry-run", "apply", "verify")
READ_ONLY_ACTIONS: tuple[str, ...] = ("plan", "dry-run", "verify")

# native 配置路径的**文档化**选择优先级：显式参数 > 环境选择器 > 默认 home。
PATH_PRIORITY: tuple[str, ...] = (
    "explicit_argument",
    "env:KIMI_CODE_HOME",
    "default_home",
)
CONFIG_PATH_SELECTOR_ENV = "KIMI_CODE_HOME"
# 已知惰性变量：argv 已显式写入固定命令，该环境变量不会改变最终选择。
INERT_ENV_VARS: tuple[str, ...] = ("TALK_KIMI_COMMAND",)
# 其余形如 KIMI_* / TALK_KIMI_* 的变量都可能构成无法枚举的覆盖层。
_UNPROVEN_ENV_PATTERN = re.compile(r"^(?:KIMI|TALK_KIMI)_[A-Za-z0-9_]*$")
# 本机实际入口证据（``bridges/kimi_bridge.py::_build_kimi_command``）：真正交给原生 CLI 的
# argv 只带 ``--output-format/--agent-file/--skills-dir/[--model]/-p``，**不转发任何
# 配置路径选择器**；``bridges/cli_bridge.py`` 用 ``create_subprocess_exec`` 且不覆盖 env，
# 因此原生 CLI 继承本进程环境，按 ``KIMI_CODE_HOME`` 或默认 home 解析有效配置。
# 下列旗标若出现在真实 argv 中，说明本入口假定的“未被选中的文件”可能真的生效，必须重新核。
_CONFIG_SELECTOR_FLAGS: tuple[str, ...] = (
    "--native-config",
    "--config",
    "--config-file",
    "--config-path",
    "--kimi-home",
    "--home",
)

MAX_DOCUMENT_BYTES = 512 * 1024
DEFAULT_HTTP_TIMEOUT_SECONDS = registry.DEFAULT_HTTP_TIMEOUT_SECONDS

CONFIRMED = "confirmed"
BLOCKED = "blocked"

# ---------------------------------------------------------------------------
# 稳定错误与稳定原因码（只回 code / 字段名 / 固定说明）
# ---------------------------------------------------------------------------

_REASON_DETAILS: dict[str, str] = {
    "E_CLOSEOUT_ACTION_INVALID": "closeout 动作必须是 plan/dry-run/apply/verify",
    "E_CLOSEOUT_TARGET_INVALID": "显式目标不是合法的服务/项目/成员/profile",
    "E_CLOSEOUT_NATIVE_MISSING": "没有找到可读的原生配置来源；不猜测、不代填",
    "E_CLOSEOUT_NATIVE_PARSE_FAILED": "原生配置无法解析为有效来源",
    "E_CLOSEOUT_SOURCE_UNSELECTED": "显式给出的 native 配置未被当前运行入口的实际解析规则选中；读到文件不等于生效来源",
    "E_CLOSEOUT_OVERRIDE_UNKNOWN": "存在无法证明生效顺序的覆盖层；不把读到文件当作已确认来源",
    "E_CLOSEOUT_ARGV_MISMATCH": "真实 argv 的最终模型选择与固定 alias 常量不一致",
    "E_CLOSEOUT_ARGV_COMMAND_MISMATCH": "真实 argv 的受控命令或执行分级与固定契约不一致",
    "E_CLOSEOUT_ALIAS_MISSING": "原生配置里没有该 alias 条目，无法核对公开元组",
    "E_CLOSEOUT_PLAN_REQUIRED": "apply/verify 必须显式给出计划文档",
    "E_CLOSEOUT_PLAN_INVALID": "计划不是本入口或 C2 生成的合法计划文档",
    "E_CLOSEOUT_TARGET_MISMATCH": "显式目标与已审计划的 server/project/member/adapter 不一致",
    "E_CLOSEOUT_SCOPE_MISSING": "apply 必须显式给出 host/workspace scope，不从已审计划静默补",
    "E_CLOSEOUT_SCOPE_MISMATCH": "本次显式 scope 与已审阅计划记录的 scope 不一致",
    "E_CLOSEOUT_CREDENTIAL_MISSING": "必须显式给出凭据来源（环境变量名或仓库外 key_file）",
    "E_CLOSEOUT_CLIENT_MISSING": "缺少显式 HTTP 客户端边界",
    "E_CLOSEOUT_PACKAGE_UNAVAILABLE": "该计划不能生成可审阅 application 包",
    "E_CLOSEOUT_NOT_APPLIED": "计划尚未处于可应用状态；先修正 blocked/冲突并重新 plan",
}

_ENVELOPE_CODES: frozenset[str] = frozenset(_REASON_DETAILS)


class CloseoutError(ValueError):
    """稳定错误码异常：只携带 ``code`` / ``field``，不携带原值、路径或凭据。"""

    def __init__(self, code: str, *, field: Optional[str] = None) -> None:
        super().__init__(code)
        self.code = code
        self.field = field

    def __str__(self) -> str:  # pragma: no cover - 便于阅读的稳定文本
        return self.code if self.field is None else f"{self.code}:{self.field}"


def _reason(
    code: str, *, field: Optional[str] = None, reason_code: Optional[str] = None
) -> dict[str, Any]:
    detail = _REASON_DETAILS.get(code) or getattr(facts, "_REASON_DETAILS", {}).get(code)
    if detail is None:
        detail = getattr(registry, "_REASON_DETAILS", {}).get(code, code)
    item: dict[str, Any] = {"code": code, "field": field, "detail": detail}
    if reason_code is not None:
        item["reason_code"] = reason_code
    return item


def _sha256_hex(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# native 有效来源：显式只读加载 + 覆盖层 + 真实 argv 选择
# ---------------------------------------------------------------------------


def _empty_native_public() -> dict[str, Any]:
    return {
        "config_source": {
            "path_origin": None,
            "priority": list(PATH_PRIORITY),
            "shadowed_selectors": [],
            "documented_by": "kimi_k28_executor.default_kimi_config_path",
            "parsed": False,
            "runtime_selected": None,
            "selector_forwarded_to_runtime": False,
        },
        "override_layer": {
            "status": "unknown",
            "checked_env_vars": [CONFIG_PATH_SELECTOR_ENV, *INERT_ENV_VARS],
            "unproven_env_var_count": None,
        },
        "argv_selection": {"status": "not_run"},
        "native_entry": {"alias_present": None},
    }


def _runtime_config_path(env: Mapping[str, Any]) -> Optional[Path]:
    """当前运行入口实际会解析到的原生配置文件（继承环境，不启进程）。"""
    try:
        return k28.default_kimi_config_path(dict(env))
    except (OSError, TypeError, ValueError):
        return None


def _runtime_config_path_origin(env: Mapping[str, Any]) -> str:
    if str(env.get(CONFIG_PATH_SELECTOR_ENV) or "").strip():
        return f"env:{CONFIG_PATH_SELECTOR_ENV}"
    return "default_home"


def native_source_record(
    *,
    config: Any = None,
    status: str = BLOCKED,
    origin: str = "unknown",
    public: Any = None,
    blocked: Any = (),
) -> dict[str, Any]:
    """构造一条来源记录（真实加载与本入口的注入边界共用同一形状）。

    字段：``status`` / ``origin`` / ``config``（内部，不序列化）/ ``public``（公开白名单）/
    ``blocked``（稳定原因）。``config`` 只用于内存核验，绝不进入任何产物。
    """
    return {
        "status": status if status in (CONFIRMED, BLOCKED) else BLOCKED,
        "origin": origin if origin in facts.CONFIG_ORIGINS else "unknown",
        "config": config if isinstance(config, Mapping) else None,
        "public": _plain(public) if isinstance(public, Mapping) else _empty_native_public(),
        "blocked": [_plain(item) for item in blocked] if blocked else [],
    }


def load_effective_native_source(
    *, config_path: Any = None, environ: Any = None
) -> dict[str, Any]:
    """显式只读加载 native 有效来源；不确定就 blocked，不代填。

    - 生效来源只有一个：当前运行入口继承环境后实际解析到的文件（``KIMI_CODE_HOME`` 或
      默认 home）。显式 ``config_path`` 只有在**与该解析结果指向同一文件**时才可能
      ``confirmed``；否则稳定 ``blocked``——本入口的桥接 argv 不转发任何配置选择器，
      读到文件、摘要正确都不等于生效来源；
    - 任何无法证明惰性的 ``KIMI_*`` / ``TALK_KIMI_*`` 环境变量都视为未知覆盖层；
    - 文件不存在、不可读或解析失败分别落稳定原因码，不回显解析器正文；
    - 公开白名单只出现选择器标签与布尔，不出现路径、配置正文或内部摘要。
    """
    env = dict(os.environ) if environ is None else {str(k): v for k, v in environ.items()}
    public = _empty_native_public()
    public["config_source"]["selector_forwarded_to_runtime"] = False
    blocked: list[dict[str, Any]] = []

    selectors: list[str] = []
    if str(env.get(CONFIG_PATH_SELECTOR_ENV) or "").strip():
        selectors.append(f"env:{CONFIG_PATH_SELECTOR_ENV}")
    if config_path is not None:
        selectors.append("explicit_argument")
    unproven = sorted(
        key
        for key, value in env.items()
        if _UNPROVEN_ENV_PATTERN.fullmatch(key)
        and key != CONFIG_PATH_SELECTOR_ENV
        and key not in INERT_ENV_VARS
        and str(value or "").strip()
    )
    public["override_layer"] = {
        "status": "none" if not unproven else "unknown",
        "checked_env_vars": [CONFIG_PATH_SELECTOR_ENV, *INERT_ENV_VARS],
        "unproven_env_var_count": len(unproven),
    }
    if unproven:
        blocked.append(_reason("E_CLOSEOUT_OVERRIDE_UNKNOWN", field="override_layer"))

    selected = _runtime_config_path(env)
    runtime_origin = _runtime_config_path_origin(env)
    chosen: Optional[Path] = None
    if config_path is not None:
        public["config_source"]["path_origin"] = "explicit_argument"
        public["config_source"]["shadowed_selectors"] = [
            item for item in selectors if item != "explicit_argument"
        ]
        try:
            chosen = Path(str(config_path)).expanduser().resolve()
        except (OSError, TypeError, ValueError):
            chosen = None
        runtime_selected = (
            chosen is not None and selected is not None and chosen == selected
        )
        public["config_source"]["runtime_selected"] = bool(runtime_selected)
        public["config_source"]["effective_path_origin"] = runtime_origin
        if not runtime_selected:
            # 该文件没有被当前入口的实际解析规则选中：即使能读到、能解析，也不是生效来源。
            blocked.append(
                _reason("E_CLOSEOUT_SOURCE_UNSELECTED", field="config_path")
            )
    else:
        chosen = selected
        public["config_source"]["path_origin"] = runtime_origin
        public["config_source"]["runtime_selected"] = chosen is not None
        public["config_source"]["effective_path_origin"] = runtime_origin

    config: Optional[dict] = None
    if chosen is None:
        blocked.append(_reason("E_CLOSEOUT_NATIVE_MISSING", field="config_path"))
    else:
        try:
            exists = chosen.is_file()
        except OSError:
            exists = False
        if not exists:
            blocked.append(_reason("E_CLOSEOUT_NATIVE_MISSING", field="config_path"))
        else:
            try:
                loaded = k28.load_native_config(chosen)
            except k28.K28ExecutorError:
                blocked.append(
                    _reason("E_CLOSEOUT_NATIVE_PARSE_FAILED", field="config_path")
                )
            else:
                if isinstance(loaded, Mapping):
                    config = dict(loaded)
                    public["config_source"]["parsed"] = True
                else:  # pragma: no cover - tomllib 只会返回表
                    blocked.append(
                        _reason("E_CLOSEOUT_NATIVE_PARSE_FAILED", field="config_path")
                    )

    return native_source_record(
        config=config,
        status=BLOCKED if blocked else CONFIRMED,
        origin="native_profile_loaded" if config is not None else "unknown",
        public=public,
        blocked=blocked,
    )


def _parse_bridge_argv(argv: Sequence[str]) -> tuple[Optional[str], Optional[str]]:
    """用**既有 bridge parser** 解析真实 argv；不启动任何进程。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from bridges import kimi_bridge  # noqa: PLC0415 - 延迟导入保持导入期零副作用

    parsed = kimi_bridge.build_parser().parse_args(list(argv))
    return (
        getattr(parsed, "kimi_model", None),
        getattr(parsed, "kimi_command", None),
    )


def argv_selection_evidence(adapter: Any) -> dict[str, Any]:
    """真实 argv 的最终模型选择证据（检查对象 == 执行对象）。

    只用 ``kimi_k28_executor.build_bridge_argv`` 生成、再用 ``bridges.kimi_bridge`` 的
    parser 解析同一份 argv，核对**完整受控契约**：最终 ``--kimi-model`` alias、受控
    ``--kimi-command`` 与显式执行分级三项同时成立才算 ``ok``；任一项缺失/不匹配即
    ``blocked``。另外确认桥接 argv 没有夹带配置路径选择器（本入口假定原生 CLI 按
    ``KIMI_CODE_HOME`` / 默认 home 解析来源）。不启动 bridge/服务/模型，也不使用原生 CLI
    的 ``--version`` / ``--help`` 解析模型配置。
    """
    public: dict[str, Any] = {
        "argv_builder": "kimi_k28_executor.build_bridge_argv",
        "argv_parser": "bridges.kimi_bridge.build_parser",
        "flag": "--kimi-model",
        "starts_process": False,
        "native_cli_probe": "not_run",
    }
    if adapter != facts.K28_ADAPTER:
        return {"status": "not_applicable", "public": {**public, "status": "not_applicable"}}
    try:
        profile = facts.adapter_profile(adapter)
        argv = k28.build_bridge_argv()
        # 先扫选择器：夹带配置路径就说明本入口假定的"未被选中的文件"可能真的生效，
        # 不进入解析，直接稳定 blocked。
        selector_flags = sorted(
            {str(item) for item in argv if str(item) in _CONFIG_SELECTOR_FLAGS}
        )
        if selector_flags:
            public.update(
                {
                    "status": "blocked",
                    "config_selector_forwarded": True,
                    "config_selector_flags": selector_flags,
                    "matches_fixed_alias": False,
                    "command_matches_controlled": False,
                    "decision_tier_matches": False,
                }
            )
            return {"status": "blocked", "public": public}
        parsed_model, parsed_command = _parse_bridge_argv(argv)
        decision_tier = k28.resolve_argv_decision_tier(argv)
    except Exception:  # noqa: BLE001 - 解析/导入失败不回流正文
        return {"status": "blocked", "public": {**public, "status": "blocked"}}

    expected = profile.explicit_argv_alias
    alias_matches = bool(parsed_model) and parsed_model == expected == k28.MODEL_ALIAS
    command_matches = (
        bool(parsed_command) and parsed_command == k28.CONTROLLED_KIMI_COMMAND
    )
    tier_expected = k28.DECISION_TIER
    tier_matches = decision_tier == tier_expected
    matches = alias_matches and command_matches and tier_matches
    public.update(
        {
            "status": "ok" if matches else "blocked",
            "argv_alias_sha256": _sha256_hex(parsed_model),
            "profile_alias_sha256": _sha256_hex(expected),
            "hard_alias_sha256": _sha256_hex(k28.MODEL_ALIAS),
            "matches_fixed_alias": alias_matches,
            "command_contract": "explicit_fixed_contract",
            "command_matches_controlled": command_matches,
            "decision_tier": decision_tier,
            "decision_tier_expected": tier_expected,
            "decision_tier_matches": tier_matches,
            "config_selector_forwarded": bool(selector_flags),
            "config_selector_flags": selector_flags,
        }
    )
    return {"status": "ok" if matches else "blocked", "public": public}


# ---------------------------------------------------------------------------
# 只读来源边界：每次调用都重新读取实际有效来源（plan→apply 漂移检查）
# ---------------------------------------------------------------------------


class _SourceBoundary:
    """C2 ``source_provider`` 的可注入实现。

    每次调用都重新执行只读加载、重新核 scope / 选择 / 公开元组，并让 C1/C2 重算公开
    ``source_fingerprint``；调用方不复用旧计划里的 ready/confirmed/候选。
    """

    def __init__(
        self,
        *,
        adapter: str,
        host_scope: Any,
        workspace_scope: Any,
        host_shared_runner: Any,
        multi_workspace_on_host: Any,
        loader: Callable[[], dict[str, Any]],
    ) -> None:
        self.adapter = adapter
        self.host_scope = host_scope
        self.workspace_scope = workspace_scope
        self.host_shared_runner = host_shared_runner
        self.multi_workspace_on_host = multi_workspace_on_host
        self._loader = loader
        self.calls = 0
        self.last: Optional[dict[str, Any]] = None

    # -- C2 边界 ---------------------------------------------------------
    def __call__(self, target: Any) -> Any:  # noqa: ARG002 - target 只用于 C2 契约
        self.calls += 1
        outcome = self._resolve()
        self.last = outcome
        if outcome["status"] != "ready":
            return None
        return dict(outcome["facts"])

    # -- 内部 ------------------------------------------------------------
    def _resolve(self) -> dict[str, Any]:
        public = _empty_native_public()
        blocked: list[dict[str, Any]] = []
        try:
            profile = facts.adapter_profile(self.adapter)
        except facts.AdapterBindingFactsError as exc:
            return {
                "status": "blocked",
                "public": public,
                "blocked": [_reason(exc.code, field=exc.field)],
                "facts": None,
                "scope": None,
                "origin": "unknown",
                "native_status": "unknown",
            }

        scope: Optional[dict[str, Any]] = None
        try:
            scope = facts.runner_id_for(
                profile.runtime,
                host_scope=self.host_scope,
                workspace_scope=self.workspace_scope,
                host_shared_runner=self.host_shared_runner,
                multi_workspace_on_host=self.multi_workspace_on_host,
            )
        except facts.AdapterBindingFactsError as exc:
            blocked.append(_reason(exc.code, field=exc.field))

        config: Any = None
        provenance: Any = None
        origin = "unknown"
        # ``native_status`` 只反映“原生有效来源是否真的被本入口核到”，与 scope/选择结论分开：
        # 未加载一律 not_run，加载了但不等于 confirmed 一律 blocked，绝不据空 blocked 列表自动确认。
        native_status = "not_applicable" if profile.adapter != facts.K28_ADAPTER else "unknown"
        if profile.adapter == facts.K28_ADAPTER:
            argv = argv_selection_evidence(profile.adapter)
            public["argv_selection"] = argv["public"]
            if argv["status"] != "ok":
                if not argv["public"].get("command_matches_controlled", True) or not argv[
                    "public"
                ].get("decision_tier_matches", True):
                    blocked.append(
                        _reason("E_CLOSEOUT_ARGV_COMMAND_MISMATCH", field="kimi_command")
                    )
                if not argv["public"].get("matches_fixed_alias", True):
                    blocked.append(
                        _reason("E_CLOSEOUT_ARGV_MISMATCH", field="model_alias")
                    )
                if argv["public"].get("config_selector_forwarded"):
                    blocked.append(
                        _reason("E_CLOSEOUT_OVERRIDE_UNKNOWN", field="argv_selection")
                    )
            record = self._loader()
            if not isinstance(record, Mapping):
                record = native_source_record()
            if record.get("status") == CONFIRMED and isinstance(record.get("config"), Mapping):
                native_status = CONFIRMED
            else:
                native_status = BLOCKED
            record_public = record.get("public")
            if isinstance(record_public, Mapping):
                public["config_source"] = _plain(
                    record_public.get("config_source") or public["config_source"]
                )
                public["override_layer"] = _plain(
                    record_public.get("override_layer") or public["override_layer"]
                )
            record_blocked = record.get("blocked")
            if isinstance(record_blocked, Sequence) and not isinstance(
                record_blocked, (str, bytes)
            ):
                blocked.extend(_plain(item) for item in record_blocked)
            if record.get("status") == CONFIRMED and isinstance(record.get("config"), Mapping):
                config = record["config"]
                origin = str(record.get("origin") or "unknown")
                entry = facts.read_alias_facts(config, profile.explicit_argv_alias)
                if "unavailable" in entry:
                    blocked.append(
                        _reason(
                            "E_CLOSEOUT_ALIAS_MISSING",
                            field="model_alias",
                            reason_code=entry.get("unavailable"),
                        )
                    )
                    public["native_entry"] = {"alias_present": False}
                else:
                    # 只回 alias 摘要；provider/model 等公开元组等选择核验通过后再回填，
                    # 避免未核候选（含疑似凭据/非法值）进入产物。
                    public["native_entry"] = {
                        "alias_present": True,
                        "alias_sha256": _sha256_hex(profile.explicit_argv_alias),
                    }
                    provenance = facts.native_provenance_for(
                        config, origin=origin, confirmed=True
                    )

        if profile.adapter == facts.K28_ADAPTER:
            selection = facts.resolve_model_selection(
                config=config,
                explicit_argv_alias=profile.explicit_argv_alias,
                declared=None,
                hard=profile.hard,
                native_provenance=provenance,
                required_hard_fields=profile.required_hard_fields,
            )
        else:
            # 泛用 K3 / DSH / Codex 不继承 K28 固定 alias，也不借其已核来源代填。
            selection = facts.resolve_model_selection(
                config=None,
                explicit_argv_alias=None,
                declared=None,
                hard=profile.hard,
                native_provenance=None,
                required_hard_fields=profile.required_hard_fields,
            )
        if selection.get("status") != "ready":
            for item in selection.get("blocked") or []:
                blocked.append(_plain(item))
            return {
                "status": "blocked",
                "public": public,
                "blocked": blocked,
                "facts": None,
                "scope": scope,
                "origin": origin,
                "native_status": native_status,
            }

        native_projection: Mapping[str, Any] = {}
        try:
            native_projection = facts.public_config_identity(
                selected_alias=selection.get("alias"),
                native=selection.get("native"),
                hard=selection.get("hard_contract"),
                declared=selection.get("declared_contract"),
                default_alias=None,
                default_alias_confirmed=False,
            )["projection"].get("native") or {}
        except facts.AdapterBindingFactsError:
            native_projection = {}
        if isinstance(public.get("native_entry"), Mapping):
            public["native_entry"] = {
                **public["native_entry"],
                "provider_id": native_projection.get("provider_id"),
                "model_id": native_projection.get("model_id"),
                "model_display_name": native_projection.get("model_display_name"),
                "capabilities": list(native_projection.get("capabilities") or []),
            }

        if scope is None or blocked:
            # 任一步骤未通过（scope / argv / native 来源 / 选择）都不产出候选。
            return {
                "status": "blocked",
                "public": public,
                "blocked": blocked,
                "facts": None,
                "scope": None if scope is None else scope,
                "origin": origin,
                "native_status": native_status,
            }

        runner_id = scope["runner_id"]
        runner_fields = {
            "runner_id": runner_id,
            "runtime": profile.runtime,
            "display_name": k28.DISPLAY_NAME,
            "adapter_status": "unverified",
            "adapter_note": None,
            "capabilities": list(selection["native"].get("capabilities") or []),
        }
        binding_fields: dict[str, Any] = {"runner_id": runner_id}
        sources: dict[str, Any] = {}
        for name, meta in selection["fields"].items():
            binding_fields[name] = meta["value"]
            sources[name] = {"source": meta["source"]}
        sources.update(
            {
                "runner_id": {"source": "hard_contract"},
                "runtime": {"source": "hard_contract"},
                "host_scope": {"source": "declared"},
                "workspace_scope": {"source": "declared"},
            }
        )
        source_context = {
            "host_scope": scope["host_scope"],
            "workspace_scope": scope["workspace_scope"],
            "host_shared_runner": self.host_shared_runner,
            "multi_workspace_on_host": self.multi_workspace_on_host,
            "origin": origin,
            "selection": selection,
        }
        facts_payload = {
            "runner_fields": runner_fields,
            "binding_fields": binding_fields,
            "sources": sources,
            "source_context": source_context,
        }
        return {
            "status": "ready",
            "public": public,
            "blocked": [],
            "facts": facts_payload,
            "scope": scope,
            "origin": origin,
            "native_status": native_status,
        }


# ---------------------------------------------------------------------------
# 目标 / scope 公开证据
# ---------------------------------------------------------------------------


def _resolve_target(
    *, target: Any, server: Any = None
) -> tuple[Optional[registry.RegistryTarget], Optional[dict[str, Any]]]:
    """把显式目标收敛成 C2 的 ``RegistryTarget``；失败只回稳定原因。"""
    if target is None:
        target = {
            "server": server if server is not None else k28.DEFAULT_BASE_URL,
            "project_id": None,
            "member_id": k28.MEMBER_ID,
            "adapter": facts.K28_ADAPTER,
        }
    if isinstance(target, registry.RegistryTarget):
        raw: dict[str, Any] = {
            "server": target.server,
            "project_id": target.project_id,
            "member_id": target.member_id,
            "adapter": target.adapter,
        }
    elif isinstance(target, Mapping):
        raw = {
            "server": target.get("server") if target.get("server") is not None else server,
            "project_id": target.get("project_id"),
            "member_id": target.get("member_id"),
            "adapter": target.get("adapter", target.get("member_id")),
        }
    else:
        return None, _reason("E_CLOSEOUT_TARGET_INVALID", field="target")
    if raw.get("project_id") is None:
        return None, _reason("E_CLOSEOUT_TARGET_INVALID", field="project_id")
    if raw.get("member_id") is None:
        return None, _reason("E_CLOSEOUT_TARGET_INVALID", field="member_id")
    if raw.get("server") is None:
        raw["server"] = k28.DEFAULT_BASE_URL
    try:
        targets = registry.iter_targets({"server": raw["server"], "targets": [raw]})
    except registry.AdapterRegistryError as exc:
        return None, _reason(
            "E_CLOSEOUT_TARGET_INVALID" if exc.code == "E_TARGET_INVALID" else exc.code,
            field=exc.field,
        )
    return targets[0], None


def _public_scope(
    outcome: Optional[Mapping[str, Any]],
    target: registry.RegistryTarget,
    *,
    host_shared_runner: Any = False,
    multi_workspace_on_host: Any = False,
) -> dict[str, Any]:
    scope = (outcome or {}).get("scope")
    if not isinstance(scope, Mapping):
        return {"status": "blocked", "blocked": list((outcome or {}).get("blocked") or [])}
    try:
        runtime: Any = facts.adapter_profile(target.adapter).runtime
    except facts.AdapterBindingFactsError:
        runtime = None
    return {
        "status": "ready",
        "host_scope": scope.get("host_scope"),
        "workspace_scope": scope.get("workspace_scope"),
        "scope_mode": scope.get("scope_mode"),
        "runner_id": scope.get("runner_id"),
        "runtime": runtime,
        "host_shared_runner": host_shared_runner,
        "multi_workspace_on_host": multi_workspace_on_host,
        "source": "caller_explicit_scope",
    }


# ---------------------------------------------------------------------------
# plan / dry-run
# ---------------------------------------------------------------------------


def _boundary(
    *,
    adapter: str,
    host_scope: Any,
    workspace_scope: Any,
    host_shared_runner: Any,
    multi_workspace_on_host: Any,
    loader: Optional[Callable[[], dict[str, Any]]],
    native_config_path: Any,
    environ: Any,
) -> _SourceBoundary:
    effective_loader = loader
    if effective_loader is None:
        effective_loader = lambda: load_effective_native_source(  # noqa: E731
            config_path=native_config_path, environ=environ
        )
    return _SourceBoundary(
        adapter=adapter,
        host_scope=host_scope,
        workspace_scope=workspace_scope,
        host_shared_runner=host_shared_runner,
        multi_workspace_on_host=multi_workspace_on_host,
        loader=effective_loader,
    )


_NATIVE_STATUSES: tuple[str, ...] = (
    CONFIRMED,
    BLOCKED,
    "not_run",
    "unknown",
    "not_applicable",
)


def _native_source_status(outcome: Any) -> str:
    """来源结论必须与实际核验一致：没跑过一律 ``not_run``，跑了但不是 confirmed 一律 blocked。"""
    if not isinstance(outcome, Mapping) or not outcome:
        return "not_run"
    value = outcome.get("native_status")
    return value if isinstance(value, str) and value in _NATIVE_STATUSES else "unknown"


def _closeout_limits(action: str) -> list[str]:
    if action == "apply":
        # apply 会走 C2 受信路径真实写；描述必须与实际动作一致，不得再称"只读"。
        return [
            "本次动作 apply 会按已审计划通过 C2 受信路径执行真实登记写（POST/PATCH/PUT）；本入口本身不构成生产授权",
            "写入目标与 scope 必须先与已审计划逐项一致；不一致或缺失时先零写阻断，不做静默派生",
            "无 CAS：最近读→写之间仍存在竞争窗口，本地锁不代表全局防覆盖",
            "实际后端模型版本、开发能力与宿主主动等待未由本入口核验",
            "HTTP 客户端默认直连显式服务地址、不读环境代理；确需代理时显式加 --env-proxy",
        ]
    return [
        f"本次动作 {action} 只读，不执行生产登记写；真实 apply 仍需 human 凭据与人工确认",
        "无 CAS：最近读→写之间仍存在竞争窗口，本地锁不代表全局防覆盖",
        "实际后端模型版本、开发能力与宿主主动等待未由本入口核验",
        "HTTP 客户端默认直连显式服务地址、不读环境代理；确需代理时显式加 --env-proxy",
    ]


def _plan_projection(plan: Mapping[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    requires_accept = False
    for entry in plan.get("entries") or []:
        if not isinstance(entry, Mapping):
            continue
        runner = entry.get("runner") if isinstance(entry.get("runner"), Mapping) else {}
        binding = entry.get("binding") if isinstance(entry.get("binding"), Mapping) else {}
        item = {
            "index": entry.get("index"),
            "member_id": entry.get("member_id"),
            "adapter": entry.get("adapter"),
            "status": entry.get("status"),
            "runner": {
                "action": runner.get("action"),
                "live_action": runner.get("live_action"),
                "conflict_fields": list(runner.get("conflict_fields") or []),
            },
            "binding": {
                "action": binding.get("action"),
                "live_action": binding.get("live_action"),
                "conflict_fields": list(binding.get("conflict_fields") or []),
                "binding_state": binding.get("binding_state"),
            },
            "requires_accept_change": bool(entry.get("requires_accept")),
            "blocked": _plain(entry.get("blocked") or []),
        }
        if isinstance(entry.get("source_fingerprint"), Mapping):
            item["source_fingerprint"] = _plain(entry["source_fingerprint"])
        if entry.get("requires_accept"):
            requires_accept = True
        items.append(item)
    return {
        "counts": _plain(plan.get("summary") or {}),
        "plan_status": plan.get("plan_status"),
        "requires_accept_change": requires_accept,
        "items": items,
    }


def _plan_recovery_index(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for entry in plan.get("entries") or []:
        if not isinstance(entry, Mapping):
            continue
        status = entry.get("status")
        if status == "ready":
            resume = True
            reason = None
            next_action = "按已审阅计划 apply；若来源漂移则重新 plan"
        else:
            resume = False
            blocked = entry.get("blocked") or []
            reason = (blocked[0] or {}).get("code") if blocked else "E_CLOSEOUT_NOT_APPLIED"
            next_action = "先补齐来源/scope/资格并重新 plan，不猜写"
        index.append(
            {
                "index": entry.get("index"),
                "member_id": entry.get("member_id"),
                "adapter": entry.get("adapter"),
                "resume": resume,
                "reason": reason,
                "next_action": next_action,
            }
        )
    return index


def _run_plan(
    *,
    action: str,
    target: Any,
    host_scope: Any,
    workspace_scope: Any,
    host_shared_runner: Any,
    multi_workspace_on_host: Any,
    native_loader: Optional[Callable[[], dict[str, Any]]],
    native_config_path: Any,
    environ: Any,
    client: Any,
    credential: Any,
    accept_change: Any,
    server: Any,
) -> dict[str, Any]:
    limits = _closeout_limits(action)
    resolved_target, target_error = _resolve_target(target=target, server=server)
    if target_error is not None or resolved_target is None:
        return _blocked_document(
            PLAN_SCHEMA, action, [target_error or _reason("E_CLOSEOUT_TARGET_INVALID")], limits
        )
    if client is None:
        return _blocked_document(
            PLAN_SCHEMA, action, [_reason("E_CLOSEOUT_CLIENT_MISSING", field="client")], limits
        )
    if not isinstance(credential, str) or not credential.strip():
        return _blocked_document(
            PLAN_SCHEMA,
            action,
            [_reason("E_CREDENTIAL_INVALID", field="credential")],
            limits,
        )
    if not isinstance(accept_change, bool):
        return _blocked_document(
            PLAN_SCHEMA, action, [_reason("E_FLAG_NOT_BOOL", field="accept_change")], limits
        )

    boundary = _boundary(
        adapter=resolved_target.adapter,
        host_scope=host_scope,
        workspace_scope=workspace_scope,
        host_shared_runner=host_shared_runner,
        multi_workspace_on_host=multi_workspace_on_host,
        loader=native_loader,
        native_config_path=native_config_path,
        environ=environ,
    )
    try:
        plan = registry.build_plan(
            server=resolved_target.server,
            targets=(resolved_target,),
            source_provider=boundary,
            client=client,
            credential=credential,
            accept_change=accept_change,
        )
    except registry.AdapterRegistryError as exc:
        return _blocked_document(
            PLAN_SCHEMA, action, [_reason(exc.code, field=exc.field)], limits,
            target=resolved_target.as_public_dict(),
        )

    outcome = boundary.last
    native_public = _plain((outcome or {}).get("public") or _empty_native_public())
    native_blocked = _plain((outcome or {}).get("blocked") or [])
    scope_public = _public_scope(
        outcome,
        resolved_target,
        host_shared_runner=host_shared_runner,
        multi_workspace_on_host=multi_workspace_on_host,
    )
    status = plan.get("plan_status")
    closeout_status = (
        "blocked"
        if native_blocked or status == "blocked"
        else ("ready" if status == "complete" else "partial")
    )
    document: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "action": action,
        "closeout_status": closeout_status,
        "target": resolved_target.as_public_dict(),
        "scope": scope_public,
        "native_source": {
            **native_public,
            "status": _native_source_status(outcome),
            "blocked": native_blocked,
        },
        "plan": _plain(plan),
        "proposed": _plan_projection(plan),
        "recovery_index": _plan_recovery_index(plan),
        "limits": limits,
    }
    try:
        document["application"] = build_application_package(document)
    except CloseoutError as exc:
        # 计划本身可用但包不可生成时，仍要回一个稳定的、可审阅的失败形状，不抛 traceback。
        document["application"] = {
            "schema": APPLICATION_SCHEMA,
            "available": False,
            "blocked": [_reason(exc.code, field=exc.field)],
            "limits": limits,
        }
    return document


def _blocked_document(
    schema: str,
    action: str,
    blocked: Sequence[Mapping[str, Any]],
    limits: Sequence[str],
    **extra: Any,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": schema,
        "action": action,
        "closeout_status": "blocked",
        "blocked": [_plain(item) for item in blocked],
        "limits": list(limits),
    }
    for key, value in extra.items():
        if value is not None:
            document[key] = _plain(value)
    return document


# ---------------------------------------------------------------------------
# apply / verify
# ---------------------------------------------------------------------------


def _coerce_plan_document(plan: Any) -> tuple[Optional[dict[str, Any]], Any, Optional[dict[str, Any]]]:
    """返回 ``(C2 plan, 记录 scope, 错误原因)``；只接受本入口或 C2 的计划文档。"""
    if not isinstance(plan, Mapping):
        return None, None, _reason("E_CLOSEOUT_PLAN_REQUIRED", field="plan")
    if plan.get("schema") == PLAN_SCHEMA:
        c2_plan = plan.get("plan")
        scope = plan.get("scope") if isinstance(plan.get("scope"), Mapping) else None
        if not isinstance(c2_plan, Mapping) or c2_plan.get("schema") != registry.PLAN_SCHEMA:
            return None, scope, _reason("E_CLOSEOUT_PLAN_INVALID", field="plan")
        return dict(c2_plan), scope, None
    if plan.get("schema") == registry.PLAN_SCHEMA:
        return dict(plan), None, None
    return None, None, _reason("E_CLOSEOUT_PLAN_INVALID", field="plan")


_TARGET_FIELDS: tuple[str, ...] = ("server", "project_id", "member_id", "adapter")


def _explicit_target_fields(
    target: Any,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """只收敛调用方**确实给出**的目标字段（``None`` 视为省略，不当默认值用）。"""
    if isinstance(target, registry.RegistryTarget):
        raw: Any = {
            "server": target.server,
            "project_id": target.project_id,
            "member_id": target.member_id,
            "adapter": target.adapter,
        }
    elif isinstance(target, Mapping):
        raw = target
    elif target is None:
        return {}, None
    else:
        return None, _reason("E_CLOSEOUT_TARGET_INVALID", field="target")
    explicit: dict[str, Any] = {}
    for key in _TARGET_FIELDS:
        value = raw.get(key)
        if value is not None:
            explicit[key] = value
    return explicit, None


def _plan_target_baseline(c2_plan: Mapping[str, Any]) -> dict[str, Any]:
    """已审计划记录的目标：写操作真正会落到这里的 server/project/member/adapter。"""
    entries = c2_plan.get("entries") or []
    first = entries[0] if entries and isinstance(entries[0], Mapping) else {}
    return {
        "server": c2_plan.get("server"),
        "project_id": first.get("project_id"),
        "member_id": first.get("member_id"),
        "adapter": first.get("adapter"),
    }


def _run_apply(
    *,
    target: Any,
    host_scope: Any,
    workspace_scope: Any,
    host_shared_runner: Any,
    multi_workspace_on_host: Any,
    native_loader: Optional[Callable[[], dict[str, Any]]],
    native_config_path: Any,
    environ: Any,
    client: Any,
    credential: Any,
    accept_change: Any,
    plan: Any,
    server: Any,
) -> dict[str, Any]:
    limits = _closeout_limits("apply")
    c2_plan, recorded_scope, plan_error = _coerce_plan_document(plan)
    if plan_error is not None or c2_plan is None:
        return _blocked_document(RESULT_SCHEMA, "apply", [plan_error], limits)
    if client is None:
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason("E_CLOSEOUT_CLIENT_MISSING", field="client")], limits
        )
    if not isinstance(credential, str) or not credential.strip():
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason("E_CREDENTIAL_INVALID", field="credential")], limits
        )
    if accept_change is not None and not isinstance(accept_change, bool):
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason("E_FLAG_NOT_BOOL", field="accept_change")], limits
        )

    # 1) 目标：显式字段必须与已审计划逐项一致；只有真正省略的字段才按计划派生。
    #    写操作实际落在计划记录的 project/adapter 上，因此不能用显式 target 覆盖选 profile。
    explicit, target_error = _explicit_target_fields(target)
    if target_error is not None or explicit is None:
        return _blocked_document(
            RESULT_SCHEMA, "apply", [target_error or _reason("E_CLOSEOUT_TARGET_INVALID")], limits
        )
    baseline = _plan_target_baseline(c2_plan)
    for key in ("project_id", "member_id", "adapter"):
        if key in explicit and explicit[key] != baseline.get(key):
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_TARGET_MISMATCH", field=key)],
                limits,
            )
    # 显式 server 既可能来自 target，也可能来自独立的 server 参数（CLI --server）；
    # 一律与已审计划的地址比对，错配先零写阻断。
    explicit_server = explicit.get("server", server)
    if explicit_server is not None:
        try:
            given_server = registry.normalize_server(explicit_server)
            planned_server = registry.normalize_server(baseline.get("server"))
        except registry.AdapterRegistryError:
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_TARGET_INVALID", field="server")],
                limits,
            )
        if given_server != planned_server:
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_TARGET_MISMATCH", field="server")],
                limits,
            )
    merged_target = {**baseline, **explicit}
    merged_target["server"] = baseline.get("server")
    resolved_target, target_error = _resolve_target(
        target=merged_target, server=baseline.get("server")
    )
    if target_error is not None or resolved_target is None:
        return _blocked_document(
            RESULT_SCHEMA, "apply", [target_error or _reason("E_CLOSEOUT_TARGET_INVALID")], limits
        )

    # 2) scope：apply 的 host 必显式；workspace 除显式 host-shared 外必显式；
    #    一律不从已审计划静默补，缺失/错配先零写拒绝。
    if not isinstance(host_shared_runner, bool):
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason("E_FLAG_NOT_BOOL", field="host_shared_runner")], limits
        )
    if not (isinstance(host_scope, str) and host_scope.strip()):
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason("E_CLOSEOUT_SCOPE_MISSING", field="host_scope")], limits
        )
    if host_shared_runner:
        if workspace_scope is not None:
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_SCOPE_INVALID", field="workspace_scope")],
                limits,
            )
    elif not (isinstance(workspace_scope, str) and workspace_scope.strip()):
        return _blocked_document(
            RESULT_SCHEMA,
            "apply",
            [_reason("E_CLOSEOUT_SCOPE_MISSING", field="workspace_scope")],
            limits,
        )

    effective_host = host_scope
    effective_workspace = workspace_scope
    effective_shared = host_shared_runner
    if isinstance(recorded_scope, Mapping):
        if "host_scope" in recorded_scope and effective_host != recorded_scope.get("host_scope"):
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_SCOPE_MISMATCH", field="host_scope")],
                limits,
            )
        if (
            "workspace_scope" in recorded_scope
            and effective_workspace != recorded_scope.get("workspace_scope")
        ):
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_SCOPE_MISMATCH", field="workspace_scope")],
                limits,
            )
        recorded_shared = recorded_scope.get("host_shared_runner")
        if isinstance(recorded_shared, bool) and recorded_shared != effective_shared:
            return _blocked_document(
                RESULT_SCHEMA,
                "apply",
                [_reason("E_CLOSEOUT_SCOPE_MISMATCH", field="host_shared_runner")],
                limits,
            )

    boundary = _boundary(
        adapter=resolved_target.adapter,
        host_scope=effective_host,
        workspace_scope=effective_workspace,
        host_shared_runner=effective_shared,
        multi_workspace_on_host=multi_workspace_on_host,
        loader=native_loader,
        native_config_path=native_config_path,
        environ=environ,
    )
    try:
        result = registry.apply_plan(
            plan=c2_plan,
            client=client,
            credential=credential,
            source_provider=boundary,
            accept_change=accept_change,
            server=server if server is not None else resolved_target.server,
        )
    except registry.AdapterRegistryError as exc:
        return _blocked_document(
            RESULT_SCHEMA, "apply", [_reason(exc.code, field=exc.field)], limits,
            target=resolved_target.as_public_dict(),
        )

    outcome = boundary.last
    native_public = _plain((outcome or {}).get("public") or _empty_native_public())
    native_blocked = _plain((outcome or {}).get("blocked") or [])
    return {
        "schema": RESULT_SCHEMA,
        "action": "apply",
        "closeout_status": _apply_closeout_status(result),
        "target": resolved_target.as_public_dict(),
        "scope": _public_scope(
            outcome,
            resolved_target,
            host_shared_runner=effective_shared,
            multi_workspace_on_host=multi_workspace_on_host,
        ),
        "native_source": {
            **native_public,
            "status": _native_source_status(outcome),
            "blocked": native_blocked,
        },
        "result": _plain(result),
        "recovery_index": _apply_recovery_index(result),
        "limits": limits,
    }


def _apply_closeout_status(result: Mapping[str, Any]) -> str:
    """closeout 层结论：全部 blocked → blocked；有成功项 → partial/complete。"""
    status = result.get("result_status")
    statuses = [
        entry.get("status")
        for entry in (result.get("entries") or [])
        if isinstance(entry, Mapping)
    ]
    if status == "complete":
        return "complete"
    if any(item in ("applied", "no_op") for item in statuses):
        return "partial"
    if statuses and all(item == "blocked" for item in statuses):
        return "blocked"
    return str(status)


def _apply_recovery_index(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for entry in result.get("entries") or []:
        if not isinstance(entry, Mapping):
            continue
        recovery = entry.get("recovery") if isinstance(entry.get("recovery"), Mapping) else {}
        index.append(
            {
                "index": entry.get("index"),
                "status": entry.get("status"),
                "resume": bool(recovery.get("resume")),
                "reason": recovery.get("reason"),
                "writes": _plain(entry.get("writes") or {}),
            }
        )
    return index


def _run_verify(
    *,
    client: Any,
    credential: Any,
    plan: Any,
    server: Any,
) -> dict[str, Any]:
    limits = _closeout_limits("verify")
    c2_plan, _recorded_scope, plan_error = _coerce_plan_document(plan)
    if plan_error is not None or c2_plan is None:
        return _blocked_document(VERIFY_SCHEMA, "verify", [plan_error], limits)
    if client is None:
        return _blocked_document(
            VERIFY_SCHEMA, "verify", [_reason("E_CLOSEOUT_CLIENT_MISSING", field="client")], limits
        )
    if not isinstance(credential, str) or not credential.strip():
        return _blocked_document(
            VERIFY_SCHEMA, "verify", [_reason("E_CREDENTIAL_INVALID", field="credential")], limits
        )
    try:
        verified = registry.verify_plan(
            plan=c2_plan,
            client=client,
            credential=credential,
            server=server,
        )
    except registry.AdapterRegistryError as exc:
        return _blocked_document(VERIFY_SCHEMA, "verify", [_reason(exc.code, field=exc.field)], limits)
    return {
        "schema": VERIFY_SCHEMA,
        "action": "verify",
        "closeout_status": verified.get("verify_status"),
        "verify": _plain(verified),
        "limits": limits,
    }


# ---------------------------------------------------------------------------
# application 包（人工审批用；不含凭据值与真实凭据路径）
# ---------------------------------------------------------------------------

_CREDENTIAL_PLACEHOLDER = "<HUMAN_KEY_ENV 或仓库外 key_file 的显式来源>"

# 每条目预计写方法：只由计划动作映射，不猜服务端行为。
_RUNNER_WRITE_METHODS = {"create": "POST /api/runners", "update": "PATCH /api/runners/{runner_id}"}
_BINDING_WRITE_METHODS = {
    "create": "PUT /api/projects/{project_id}/agents/{member_id}/binding",
    "update": "PUT /api/projects/{project_id}/agents/{member_id}/binding",
}

# 包输入只按白名单投影：未知嵌套键、非标量、疑似凭据一律丢弃，绝不照抄原值。
_TARGET_PUBLIC_KEYS: tuple[str, ...] = ("server", "project_id", "member_id", "adapter")
_SCOPE_PUBLIC_KEYS: tuple[str, ...] = (
    "status",
    "host_scope",
    "workspace_scope",
    "scope_mode",
    "runner_id",
    "runtime",
    "host_shared_runner",
    "multi_workspace_on_host",
    "source",
)
_NATIVE_CONFIG_SOURCE_KEYS: tuple[str, ...] = (
    "path_origin",
    "effective_path_origin",
    "priority",
    "shadowed_selectors",
    "documented_by",
    "parsed",
    "runtime_selected",
    "selector_forwarded_to_runtime",
)
_NATIVE_OVERRIDE_KEYS: tuple[str, ...] = (
    "status",
    "checked_env_vars",
    "unproven_env_var_count",
)
_NATIVE_ARGV_KEYS: tuple[str, ...] = (
    "status",
    "argv_builder",
    "argv_parser",
    "flag",
    "starts_process",
    "native_cli_probe",
    "matches_fixed_alias",
    "command_contract",
    "command_matches_controlled",
    "decision_tier",
    "decision_tier_expected",
    "decision_tier_matches",
    "config_selector_forwarded",
    "argv_alias_sha256",
    "profile_alias_sha256",
    "hard_alias_sha256",
)
_NATIVE_ENTRY_KEYS: tuple[str, ...] = (
    "alias_present",
    "alias_sha256",
    "provider_id",
    "model_id",
    "model_display_name",
    "capabilities",
)
_ENTRY_ACTIONS: tuple[str, ...] = ("create", "no_op", "update", "conflict", "blocked")
_DROP = object()


def _safe_label(value: Any) -> Optional[str]:
    """公开标签白名单投影：拒绝空白、超长、控制符与疑似凭据，不照抄原值。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 128:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        return None
    if looks_like_credential(text):
        return None
    return text


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        projected = _safe_label(value)
        return projected if projected is not None else _DROP
    if isinstance(value, (list, tuple)):
        items = [_safe_value(item) for item in value]
        if any(item is _DROP for item in items):
            return _DROP
        return items
    # 嵌套映射与其它类型：不回原值。
    return _DROP


def _project(raw: Any, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key in keys:
        if key not in raw:
            continue
        value = _safe_value(raw[key])
        if value is _DROP:
            continue
        out[key] = value
    return out


def _safe_reason(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    code = _safe_label(value.get("code"))
    if code is None:
        return None
    item: dict[str, Any] = {
        "code": code,
        "field": _safe_label(value.get("field")),
        "detail": _safe_label(value.get("detail")),
    }
    reason_code = _safe_label(value.get("reason_code"))
    if reason_code is not None:
        item["reason_code"] = reason_code
    return item


def _safe_reasons(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    reasons: list[dict[str, Any]] = []
    for item in value:
        reason = _safe_reason(item)
        if reason is not None:
            reasons.append(reason)
    return reasons


def _planned_writes(runner_action: Any, binding_action: Any) -> list[str]:
    return [
        method
        for method in (
            _RUNNER_WRITE_METHODS.get(runner_action),
            _BINDING_WRITE_METHODS.get(binding_action),
        )
        if method
    ]


def _validated_plan_entries(plan: Any) -> list[dict[str, Any]]:
    """从**有效 C2 计划条目**重算条目与计数，不信任 ``summary`` / ``proposed`` 等展示元数据。

    任何形状不符或疑似凭据的字段都稳定拒绝，不回原值、不产生半条记录。
    """
    if not isinstance(plan, Mapping) or plan.get("schema") != registry.PLAN_SCHEMA:
        raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="plan")
    raw_entries = plan.get("entries")
    if (
        isinstance(raw_entries, (str, bytes))
        or not isinstance(raw_entries, Sequence)
        or not raw_entries
    ):
        raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="entries")
    entries: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="entries")
        index = raw.get("index", position)
        if not isinstance(index, int) or isinstance(index, bool) or index != position:
            raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="index")
        labels: dict[str, str] = {}
        for key in ("member_id", "adapter", "project_id"):
            label = _safe_label(raw.get(key))
            if label is None:
                raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field=key)
            labels[key] = label
        status = raw.get("status")
        if status not in ("ready", "blocked"):
            raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="status")

        def side_action(side: str) -> Optional[str]:
            meta = raw.get(side)
            if not isinstance(meta, Mapping):
                return None
            action = meta.get("action")
            return action if action in _ENTRY_ACTIONS else None

        runner_action = side_action("runner")
        binding_action = side_action("binding")
        binding_meta = raw.get("binding") if isinstance(raw.get("binding"), Mapping) else {}
        requires_accept = raw.get("requires_accept")
        entries.append(
            {
                "index": index,
                "member_id": labels["member_id"],
                "adapter": labels["adapter"],
                "project_id": labels["project_id"],
                "status": status,
                "runner_action": runner_action,
                "binding_action": binding_action,
                "binding_state": _safe_label(binding_meta.get("binding_state")),
                "requires_accept_change": bool(requires_accept)
                or runner_action == "conflict"
                or binding_action == "conflict",
                "planned_writes": _planned_writes(runner_action, binding_action),
            }
        )
    return entries


def _recomputed_counts(entries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(entries),
        "ready": 0,
        "blocked": 0,
        "runner_create": 0,
        "runner_update": 0,
        "runner_no_op": 0,
        "runner_conflict": 0,
        "binding_create": 0,
        "binding_update": 0,
        "binding_no_op": 0,
        "binding_conflict": 0,
    }
    for entry in entries:
        if entry.get("status") == "ready":
            counts["ready"] += 1
        elif entry.get("status") == "blocked":
            counts["blocked"] += 1
        for side in ("runner", "binding"):
            action = entry.get(f"{side}_action")
            if action in ("create", "update", "no_op", "conflict"):
                counts[f"{side}_{action}"] += 1
    counts["total_writes"] = (
        counts["runner_create"]
        + counts["runner_update"]
        + counts["binding_create"]
        + counts["binding_update"]
    )
    return counts


def _command_scope_parts(scope: Mapping[str, Any]) -> list[str]:
    """按计划的 scope 模式生成参数；host-shared 不丢，绝不生成 ``workspace=None`` 字面量。"""
    parts: list[str] = []
    host = _safe_label(scope.get("host_scope"))
    parts += ["--host-scope", host if host else "<显式 HOST_SCOPE>"]
    if bool(scope.get("host_shared_runner")):
        parts.append("--host-shared-runner")
    else:
        workspace = _safe_label(scope.get("workspace_scope"))
        parts += ["--workspace-scope", workspace if workspace else "<显式 WORKSPACE_SCOPE>"]
    return parts


def _command_target_parts(target: Mapping[str, Any], *, include_project: bool) -> list[str]:
    parts: list[str] = []
    server = _safe_label(target.get("server")) or k28.DEFAULT_BASE_URL
    parts += ["--server", server]
    if include_project:
        project_id = _safe_label(target.get("project_id"))
        parts += ["--project-id", project_id if project_id else "<显式 PROJECT_ID>"]
    member_id = _safe_label(target.get("member_id")) or k28.MEMBER_ID
    adapter = _safe_label(target.get("adapter")) or facts.K28_ADAPTER
    parts += ["--member-id", member_id, "--adapter", adapter]
    return parts


def build_application_package(document: Any) -> dict[str, Any]:
    """从 closeout 计划生成可审阅的人工 application 包草稿。

    - 输入按白名单投影：``target`` / ``scope`` / 计划条目 / 来源证据里的未知嵌套键与非标量
      一律丢弃，疑似凭据稳定拒绝；
    - 写计数与条目**从有效 C2 计划条目重算**，``summary`` / ``proposed`` 只作展示对照，
      绝不当写授权事实；
    - 命令按本计划的目标/scope 模式/来源选择生成，不生成 ``workspace=None`` 字面量。
    """
    if not isinstance(document, Mapping) or document.get("schema") != PLAN_SCHEMA:
        raise CloseoutError("E_CLOSEOUT_PACKAGE_UNAVAILABLE", field="plan")
    plan = document.get("plan")
    entries = _validated_plan_entries(plan)
    counts = _recomputed_counts(entries)
    target = _project(document.get("target"), _TARGET_PUBLIC_KEYS)
    scope = _project(document.get("scope"), _SCOPE_PUBLIC_KEYS)
    native = document.get("native_source") if isinstance(document.get("native_source"), Mapping) else {}
    native_source = {
        "status": _safe_label(native.get("status")),
        "config_source": _project(native.get("config_source"), _NATIVE_CONFIG_SOURCE_KEYS),
        "override_layer": _project(native.get("override_layer"), _NATIVE_OVERRIDE_KEYS),
        "argv_selection": _project(native.get("argv_selection"), _NATIVE_ARGV_KEYS),
        "native_entry": _project(native.get("native_entry"), _NATIVE_ENTRY_KEYS),
        "blocked": _safe_reasons(native.get("blocked")),
    }
    recorded_summary = (
        _plain(plan.get("summary")) if isinstance(plan, Mapping) and isinstance(plan.get("summary"), Mapping) else {}
    )
    recorded_projection = (
        _plain((document.get("proposed") or {}).get("counts"))
        if isinstance(document.get("proposed"), Mapping)
        and isinstance((document.get("proposed") or {}).get("counts"), Mapping)
        else {}
    )

    plan_path = ".tmp/adapter-closeout-c3-rework/real-k28-plan.json"
    plan_parts = [
        *_command_target_parts(target, include_project=True),
        *_command_scope_parts(scope),
        "--key-env",
        _CREDENTIAL_PLACEHOLDER,
        "--out",
        plan_path,
    ]
    apply_parts = [
        "--plan",
        plan_path,
        *_command_target_parts(target, include_project=True),
        *_command_scope_parts(scope),
        "--key-env",
        _CREDENTIAL_PLACEHOLDER,
    ]
    verify_parts = [
        "--plan",
        plan_path,
        "--server",
        _safe_label(target.get("server")) or k28.DEFAULT_BASE_URL,
        "--key-env",
        _CREDENTIAL_PLACEHOLDER,
    ]
    package_parts = [
        "--plan",
        plan_path,
        "--out",
        ".tmp/adapter-closeout-c3-rework/application.json",
    ]
    plan_command = "python scripts/adapter_closeout.py plan " + " ".join(plan_parts)
    return {
        "schema": APPLICATION_SCHEMA,
        "generated_from": {
            "plan_schema": PLAN_SCHEMA,
            "closeout_status": _safe_label(document.get("closeout_status")),
            "plan_status": _safe_label(plan.get("plan_status")) if isinstance(plan, Mapping) else None,
        },
        "target": target,
        "scope": scope,
        "source_context": native_source,
        "plan_summary": counts,
        "expected_writes": {
            "runner_create": counts["runner_create"],
            "runner_update": counts["runner_update"],
            "runner_no_op": counts["runner_no_op"],
            "binding_create": counts["binding_create"],
            "binding_update": counts["binding_update"],
            "binding_no_op": counts["binding_no_op"],
            "total_writes": counts["total_writes"],
        },
        "expected_entries": entries,
        "metadata_consistency": {
            "source_of_truth": "plan.entries",
            "recorded_summary_matches": bool(recorded_summary)
            and all(
                recorded_summary.get(key) == value
                for key, value in counts.items()
                if key in recorded_summary
            ),
            "recorded_projection_matches": bool(recorded_projection)
            and all(
                recorded_projection.get(key) == value
                for key, value in counts.items()
                if key in recorded_projection
            ),
            "display_metadata_is_not_write_authorization": True,
        },
        "commands": {
            "plan_read_only": plan_command,
            "plan_read_only_k28_entry": plan_command.replace(
                "python scripts/adapter_closeout.py", "python scripts/kimi_k28_executor.py closeout"
            ),
            "apply_human": "python scripts/adapter_closeout.py apply " + " ".join(apply_parts),
            "verify_read_only": "python scripts/adapter_closeout.py verify " + " ".join(verify_parts),
            "package_read_only": "python scripts/adapter_closeout.py package " + " ".join(package_parts),
            "source_selection": (
                "来源选择按当前运行入口实际解析（KIMI_CODE_HOME 或默认 home）；"
                "本入口不转发任何自定义配置路径选择器"
            ),
        },
        "read_back_steps": [
            "apply 后按同一条目重新 GET /api/runners，核对目标 runner_id、runtime、retired 与四个可变字段",
            "重新 GET 项目角色绑定，核对 project_id/member_id/七字段与 binding_state=bound",
            "读回失败或形状不符时保留原条目为失败/未知，不盲重试写",
        ],
        "verify_steps": [
            "执行 verify 子命令（只读），要求 verify_status=verified",
            "verify 只用已审阅计划与只读凭据，不触发任何写",
        ],
        "recovery_steps": [
            "来源或服务状态漂移时重新 plan，不复用旧计划的 ready/confirmed/候选",
            "写失败条目按 recovery_index 只恢复该条目，不整批重写",
            "runner 已 retired 或 runtime 冲突时不自动改写，交人工裁决",
        ],
        "unconfigured_reasons": native_source["blocked"],
        "limits": [item for item in (_safe_label(entry) for entry in (document.get("limits") or [])) if item],
        "excluded": [
            "凭据值",
            "真实凭据路径",
            "整份 native 配置",
            "原始来源路径",
            "provenance 内部摘要",
        ],
        "approval_required": True,
    }


# ---------------------------------------------------------------------------
# 共享入口
# ---------------------------------------------------------------------------


def run_closeout(
    action: str,
    *,
    target: Any = None,
    host_scope: Any = None,
    workspace_scope: Any = None,
    host_shared_runner: Any = False,
    multi_workspace_on_host: Any = False,
    native_loader: Optional[Callable[[], dict[str, Any]]] = None,
    native_config_path: Any = None,
    environ: Any = None,
    client: Any = None,
    credential: Any = None,
    accept_change: Any = None,
    plan: Any = None,
    server: Any = None,
) -> dict[str, Any]:
    """共享适配收尾入口：``plan`` / ``dry-run`` 只读，``apply`` 受信，``verify`` 只读。

    - scope 必须由调用方显式给出（缺省或非法一律 blocked，不从 hostname/实例/绝对路径/
      模型名推断）；
    - ``apply`` 必须显式传入计划文档与 human 凭据；``plan``/``verify`` 全程只读；
    - 每次调用都重新只读加载实际有效来源并重算公开 ``source_fingerprint``。
    """
    if not isinstance(action, str) or action not in ACTIONS:
        raise CloseoutError("E_CLOSEOUT_ACTION_INVALID", field="action")
    effective_accept = accept_change
    if action in ("plan", "dry-run"):
        if effective_accept is None:
            effective_accept = False
        return _run_plan(
            action=action,
            target=target,
            host_scope=host_scope,
            workspace_scope=workspace_scope,
            host_shared_runner=host_shared_runner,
            multi_workspace_on_host=multi_workspace_on_host,
            native_loader=native_loader,
            native_config_path=native_config_path,
            environ=environ,
            client=client,
            credential=credential,
            accept_change=effective_accept,
            server=server,
        )
    if action == "apply":
        return _run_apply(
            target=target,
            host_scope=host_scope,
            workspace_scope=workspace_scope,
            host_shared_runner=host_shared_runner,
            multi_workspace_on_host=multi_workspace_on_host,
            native_loader=native_loader,
            native_config_path=native_config_path,
            environ=environ,
            client=client,
            credential=credential,
            accept_change=effective_accept,
            plan=plan,
            server=server,
        )
    return _run_verify(client=client, credential=credential, plan=plan, server=server)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_CLI_USAGE_ERROR = (
    "E_CLI_USAGE: 参数或子命令不合法；已知子命令 plan|dry-run|apply|verify|package，"
    "已知参数 --server --project-id --member-id --adapter --host-scope --workspace-scope "
    "--host-shared-runner --native-config --accept-change --plan --out --timeout --key-env "
    "--key-file（--help 查看用法；没有明文 --key）"
)


class _StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # noqa: ARG002 - 不回显 argparse 原文
        sys.stderr.write(_CLI_USAGE_ERROR + "\n")
        raise SystemExit(2)


def _http_timeout(value: Any) -> float:
    import math

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return parsed


def _default_client(server: str, timeout: float, *, env_proxy: bool = False) -> Any:
    """构造只读/受信 HTTP 客户端。

    本项目服务是显式给出的本机地址，默认**不读环境代理**（本机常见的
    ``ALL_PROXY=socks5://…`` 在缺少 ``socksio`` 时会直接在构造期失败）；
    确需经代理访问时由调用方显式传 ``--env-proxy``。
    """
    import httpx  # 局部导入：模块导入期不引入网络栈

    return httpx.Client(
        base_url=server,
        timeout=httpx.Timeout(timeout),
        trust_env=bool(env_proxy),
    )


def _read_json_document(path: Any, *, code: str) -> Any:
    try:
        candidate = Path(str(path))
    except (TypeError, ValueError) as exc:
        raise registry.AdapterRegistryError(code, field="path") from exc
    try:
        if not candidate.is_file():
            raise registry.AdapterRegistryError(code, field="path")
        if candidate.stat().st_size > MAX_DOCUMENT_BYTES:
            raise registry.AdapterRegistryError(code, field="path")
        text = candidate.read_text(encoding="utf-8")
    except registry.AdapterRegistryError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise registry.AdapterRegistryError(code, field="path") from exc
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise registry.AdapterRegistryError(code, field="path") from exc


def _write_json_document(path: Any, payload: Any) -> None:
    try:
        candidate = Path(str(path))
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(
            json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise registry.AdapterRegistryError("E_OUTPUT_FAILED", field="path") from exc


def _emit(payload: Any, out_path: Optional[str]) -> None:
    if out_path:
        _write_json_document(out_path, payload)
        return
    sys.stdout.write(
        json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = _StableArgumentParser(
        prog="adapter_closeout.py",
        description=(
            "适配收尾共享入口（C3）：plan/dry-run 只读生成可审阅计划，apply 由 human 凭据"
            "受信应用，verify 只读核验。凭据只来自 --key-env 或仓库外 --key-file。"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_scope_args(
        target: argparse.ArgumentParser,
        *,
        require_project: bool,
        default_member: Any = k28.MEMBER_ID,
        default_adapter: Any = facts.K28_ADAPTER,
    ) -> None:
        target.add_argument(
            "--project-id",
            required=require_project,
            default=None,
            help="显式项目 id（不从路径/实例推断）",
        )
        target.add_argument("--member-id", default=default_member)
        target.add_argument("--adapter", default=default_adapter)
        target.add_argument("--host-scope", default=None, help="显式安装标识（必填）")
        target.add_argument("--workspace-scope", default=None, help="显式工作区标识")
        target.add_argument(
            "--host-shared-runner",
            action="store_true",
            help="显式声明 host 共享运行器（与 workspace-scope 互斥）",
        )

    def add_credential_args(target: argparse.ArgumentParser, *, server_default: Any) -> None:
        target.add_argument("--key-env", default=None, help="凭据所在环境变量名")
        target.add_argument("--key-file", default=None, help="仓库外的凭据文件路径")
        target.add_argument(
            "--server",
            default=server_default,
            help="显式服务根地址（apply 省略时取已审阅计划记录的地址）",
        )
        target.add_argument(
            "--timeout",
            type=_http_timeout,
            default=DEFAULT_HTTP_TIMEOUT_SECONDS,
            help="单次 HTTP 超时秒数（严格有限正值；本片不长等待）",
        )
        target.add_argument(
            "--env-proxy",
            action="store_true",
            help="显式允许读取环境代理变量；默认直连显式服务地址",
        )

    for name, help_text in (
        ("plan", "只读生成可审阅计划（GET only，零写）"),
        ("dry-run", "只读演练，与 plan 相同但不产生任何写（GET only）"),
    ):
        sub_parser = sub.add_parser(name, help=help_text)
        add_scope_args(sub_parser, require_project=True)
        sub_parser.add_argument("--native-config", default=None, help="显式 native 配置文件路径")
        sub_parser.add_argument("--accept-change", action="store_true", help="显式接受既有差异")
        sub_parser.add_argument("--out", default=None, help="计划输出路径（默认打印到 stdout）")
        add_credential_args(sub_parser, server_default=k28.DEFAULT_BASE_URL)

    apply_parser = sub.add_parser("apply", help="按已审阅计划受信应用（human 凭据）")
    apply_parser.add_argument("--plan", required=True, help="plan 生成的计划文档路径")
    # apply 省略的目标字段按已审计划派生；显式给出的字段必须与其逐项一致，
    # 因此这里不能用硬编码默认 member/adapter 冒充"用户给了值"。
    add_scope_args(
        apply_parser, require_project=False, default_member=None, default_adapter=None
    )
    apply_parser.add_argument("--native-config", default=None, help="显式 native 配置文件路径")
    apply_parser.add_argument("--accept-change", action="store_true", help="显式接受既有差异")
    add_credential_args(apply_parser, server_default=None)

    verify_parser = sub.add_parser("verify", help="只读核验已应用结果")
    verify_parser.add_argument("--plan", required=True, help="plan 生成的计划文档路径")
    verify_parser.add_argument("--server", default=None, help="显式服务根地址（默认取计划）")
    verify_parser.add_argument(
        "--timeout", type=_http_timeout, default=DEFAULT_HTTP_TIMEOUT_SECONDS
    )
    verify_parser.add_argument("--key-env", default=None, help="凭据所在环境变量名")
    verify_parser.add_argument("--key-file", default=None, help="仓库外的凭据文件路径")
    verify_parser.add_argument(
        "--env-proxy",
        action="store_true",
        help="显式允许读取环境代理变量；默认直连显式服务地址",
    )

    package_parser = sub.add_parser("package", help="从计划文档生成 application 包草稿（只读）")
    package_parser.add_argument("--plan", required=True, help="closeout 计划文档路径")
    package_parser.add_argument("--out", default=None, help="application 输出路径")
    return parser


def _target_from_args(args: argparse.Namespace, *, server: Any) -> dict[str, Any]:
    return {
        "server": server,
        "project_id": getattr(args, "project_id", None),
        "member_id": getattr(args, "member_id", None),
        "adapter": getattr(args, "adapter", None),
    }


def _require_plan_document(document: Any) -> Mapping[str, Any]:
    """CLI 侧**输入形状**校验：非法根（数组/null/标量）按用法错误退出 2。"""
    if not isinstance(document, Mapping) or document.get("schema") not in (
        PLAN_SCHEMA,
        registry.PLAN_SCHEMA,
    ):
        raise registry.AdapterRegistryError("E_CLOSEOUT_PLAN_INVALID", field="path")
    return document


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "package":
            document = _require_plan_document(
                _read_json_document(args.plan, code="E_CLOSEOUT_PLAN_REQUIRED")
            )
            try:
                payload = build_application_package(document)
            except CloseoutError as exc:
                sys.stderr.write(f"{exc}\n")
                return 2
            _emit(payload, args.out)
            return 0
        credential = registry.load_credential(key_env=args.key_env, key_file=args.key_file)
        if args.command in ("plan", "dry-run"):
            server = registry.normalize_server(args.server)
            client = _default_client(
                server, args.timeout, env_proxy=bool(getattr(args, "env_proxy", False))
            )
            payload = run_closeout(
                "plan" if args.command == "plan" else "dry-run",
                target=_target_from_args(args, server=server),
                host_scope=args.host_scope,
                workspace_scope=args.workspace_scope,
                host_shared_runner=bool(args.host_shared_runner),
                native_config_path=args.native_config,
                client=client,
                credential=credential,
                accept_change=bool(args.accept_change),
                server=server,
            )
            _emit(payload, args.out)
            return 0 if payload["closeout_status"] == "ready" else 1
        if args.command == "apply":
            document = _require_plan_document(
                _read_json_document(args.plan, code="E_CLOSEOUT_PLAN_REQUIRED")
            )
            plan_server = document.get("server") or (
                (document.get("plan") or {}).get("server")
                if isinstance(document.get("plan"), Mapping)
                else None
            )
            server = registry.normalize_server(args.server or plan_server or k28.DEFAULT_BASE_URL)
            client = _default_client(
                server, args.timeout, env_proxy=bool(getattr(args, "env_proxy", False))
            )
            payload = run_closeout(
                "apply",
                target=_target_from_args(args, server=None),
                host_scope=args.host_scope,
                workspace_scope=args.workspace_scope,
                host_shared_runner=bool(args.host_shared_runner),
                native_config_path=args.native_config,
                client=client,
                credential=credential,
                accept_change=True if args.accept_change else None,
                plan=document,
                server=server,
            )
            _emit(payload, None)
            return 0 if payload["closeout_status"] == "complete" else 1
        document = _require_plan_document(
            _read_json_document(args.plan, code="E_CLOSEOUT_PLAN_REQUIRED")
        )
        plan_server = document.get("server") or (
            (document.get("plan") or {}).get("server")
            if isinstance(document.get("plan"), Mapping)
            else None
        )
        server = registry.normalize_server(args.server or plan_server or k28.DEFAULT_BASE_URL)
        client = _default_client(
            server, args.timeout, env_proxy=bool(getattr(args, "env_proxy", False))
        )
        payload = run_closeout(
            "verify", client=client, credential=credential, plan=document, server=server
        )
        _emit(payload, None)
        return 0 if payload["closeout_status"] == "verified" else 1
    except registry.AdapterRegistryError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    except CloseoutError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, ImportError, RecursionError):
        sys.stderr.write("E_CLI_INVALID_INPUT\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
