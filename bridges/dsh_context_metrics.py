"""DSH 上下文快照规范化与 288 执行会话内核输入适配。

本模块只使用调用方显式传入的 JSON 对象，不访问文件、环境变量、数据库或网络，
不启动进程，不调用模型，也不导入或修改 288 内核。它把
``talk-dsh-context-snapshot-1``（由 ``dsh_context_capture.mjs`` 从已核验的
原生 session/projection 接口采集）转换为
``bridges.execution_sessions.plan_execution_session`` 可接受的
``context_sample``，或返回带明确原因码的 unknown。

明确边界：

- ``trusted_host`` 是调用方显式提供的信任声明，不是跨进程认证；本片未实现
  签名、令牌或 IPC 身份证明。
- 快照中的原生计量字段来自已安装 DSH 的 ``contextPressure`` projection；
  用量与容量是独立 last-wins 来源，不宣称同一次请求的原子样本。
- 规范化只接受当前 schema、采集器模块名和已冻结的原生契约版本；外部任意
  JSON 即使字段齐全也不能自动成为 TALK 可信事实。
- unknown 不转成 0%，非法 projected 不回退成低 pressure；过期/未来/身份
  不符的样本不会因为本次读取动作而变成新样本。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "ADAPTER_SCHEMA",
    "MAX_SAFE_INTEGER",
    "SNAPSHOT_SCHEMA",
    "UNAVAILABILITY_SCHEMA",
    "adapt_context_snapshot",
    "build_metrics_unavailability",
]

SNAPSHOT_SCHEMA = "talk-dsh-context-snapshot-1"
ADAPTER_SCHEMA = "talk-dsh-context-adapter-1"
# 机器可判的指标不可得分类。它只描述“为什么没有可靠样本”，不伪装成有效
# 占比；未知/禁止原因一律 fallback_eligible=False。
UNAVAILABILITY_SCHEMA = "talk-dsh-context-unavailability-1"
UNAVAILABILITY_VERSION = 1
CAPTURE_MODULE = "dsh_context_capture"
CAPTURE_VERSION = "1.0.0"
PRODUCER_NATIVE_PACKAGE = "@deepseek-ai/dsh"
PRODUCER_NATIVE_FROZEN_VERSION = "0.1.5-rc.2"
PROJECTION_KEY = "contextPressure"
EXPECTED_STATE_VERSION = 4
PROJECTION_READ_API = "sessionProjections.snapshot"
SESSION_READ_API = "sessions.get"
MAX_SAFE_INTEGER = 9_007_199_254_740_991

_SNAPSHOT_TOP_FIELDS = frozenset(
    (
        "schema",
        "schema_version",
        "producer",
        "observed_at",
        "host",
        "session",
        "config",
        "metrics",
        "capture",
    )
)
_SCOPE_FIELDS = (
    "project_id",
    "target_member_id",
    "requester_id",
    "continuity_key",
    "workspace_identity",
    "runner_id",
    "native_home_namespace",
    "service_launch_id",
    "provider_id",
    "model_id",
    "model_binding_fingerprint",
    "config_permission_fingerprint",
)
_IDENTIFIER_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_METRIC_STATES = frozenset(("known", "missing", "invalid", "unverified", "unknown"))

# 有限白名单：只有这些“单纯不可得”原因才可能进入内核备用计数。任何身份/
# 配置/顺序/非法值/未知 producer 原因都不在此表，分类恒为不可兜底。
_FALLBACK_REASON_CATEGORIES = {
    "tokens_missing": "no_usage_sample",
    "capacity_missing": "capacity_missing",
    "used_sample_expired": "source_expired",
    "capacity_sample_expired": "source_expired",
    "pressure_sample_expired": "source_expired",
    "metrics_not_provided": "metrics_not_provided",
    "no_usage_sample": "no_usage_sample",
    "runtime_unsupported": "runtime_unsupported",
}
# 可信宿主在无快照时只能显式声明这三类事实；不能借该 helper 把错误样本
# 改写成 missing。identity_verified 仍要求精确 scope/native/generation。
_HOST_ATTESTABLE_REASONS = frozenset(
    ("metrics_not_provided", "no_usage_sample", "runtime_unsupported")
)
_IDENTITY_CHECK_KEYS = (
    "scope_match",
    "workspace_verified",
    "session_id_match",
    "generation_match",
    "revision_match",
    "session_live",
    "projection_exact",
    "model_match",
    "binding_match",
    "config_source_known",
)
_BLOCKED_CATEGORY_BY_REASON = {
    "trusted_host_unverified": "trust_unverified",
    "expected_scope_invalid": "scope_unverified",
    "snapshot_invalid": "schema_or_producer_blocked",
    "snapshot_schema_unsupported": "schema_or_producer_blocked",
    "snapshot_version_unsupported": "schema_or_producer_blocked",
    "producer_unsupported": "schema_or_producer_blocked",
    "observed_at_invalid": "source_time_blocked",
    "snapshot_future": "source_time_blocked",
    "sample_future": "source_time_blocked",
    "source_after_snapshot_cut": "source_order_blocked",
    "metric_source_order_invalid": "source_order_blocked",
    "config_changed_after_pressure_sample": "source_order_blocked",
    "capacity_changed_after_pressure_sample": "source_order_blocked",
    "capacity_precedes_current_config": "source_order_blocked",
    "source_event_time_inconsistent": "source_order_blocked",
    "projected_invalid": "invalid_metric",
    "projected_unverified": "unverified_metric",
    "projected_unknown": "unknown_metric",
    "pressure_invalid": "invalid_metric",
    "pressure_unverified": "unverified_metric",
    "pressure_unknown": "unknown_metric",
    "pressure_unavailable": "inconsistent_metric",
    "capacity_invalid": "invalid_metric",
    "capacity_unverified": "unverified_metric",
    "capacity_unknown": "unknown_metric",
    "capture_blocking_issue": "capture_blocked",
}


class _DataError(Exception):
    """Internal data validation error; only field/reason is exposed."""

    def __init__(self, field: str, code: str) -> None:
        super().__init__(f"{field}: {code}")
        self.field = field
        self.code = code


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _safe_int(value: Any, *, minimum: int = 0) -> bool:
    return _is_int(value) and minimum <= value <= MAX_SAFE_INTEGER


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _DataError(field, "not_mapping")
    return value


def _require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _DataError(field, "not_string")
    if not value or value != value.strip() or len(value) > 512:
        raise _DataError(field, "invalid_identifier")
    if _IDENTIFIER_CONTROL_RE.search(value):
        raise _DataError(field, "control_character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _DataError(field, "not_utf8") from exc
    return value


def _parse_time(value: Any, field: str) -> datetime:
    if isinstance(value, bool):
        raise _DataError(field, "bool_time")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise _DataError(field, "naive_time")
        try:
            return value.astimezone(timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise _DataError(field, "time_range") from exc
    if _is_int(value):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise _DataError(field, "time_range") from exc
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise _DataError(field, "empty_time")
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise _DataError(field, "invalid_time") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise _DataError(field, "naive_time")
        try:
            return parsed.astimezone(timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise _DataError(field, "time_range") from exc
    raise _DataError(field, "invalid_time")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _binding_fingerprint(
    scope: Mapping[str, Any],
    native_session_id: str,
    session_generation: int,
    session_revision: str | int,
) -> str:
    payload = {
        "scope": {field: scope[field] for field in _SCOPE_FIELDS},
        "native_session_id": native_session_id,
        "session_generation": session_generation,
        "session_revision": session_revision,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _window_binding(expected: Mapping[str, Any]) -> dict[str, Any]:
    scope = {field: expected[field] for field in _SCOPE_FIELDS}
    return {
        "native_session_id": expected["native_session_id"],
        "session_generation": expected["session_generation"],
        "session_revision": expected["session_revision"],
        "scope": scope,
        "scope_fingerprint": _binding_fingerprint(
            scope,
            expected["native_session_id"],
            expected["session_generation"],
            expected["session_revision"],
        ),
    }


def _identity_verified(audit: Mapping[str, Any]) -> bool:
    checks = audit.get("checks")
    if not isinstance(checks, Mapping):
        return False
    return all(checks.get(key) is True for key in _IDENTITY_CHECK_KEYS)


def _blocked_category(reason_code: str) -> str:
    mapped = _BLOCKED_CATEGORY_BY_REASON.get(reason_code)
    if mapped is not None:
        return mapped
    if reason_code.endswith("_future") or reason_code.endswith("_future_source"):
        return "source_time_blocked"
    if reason_code.startswith(("projected_", "pressure_", "capacity_")):
        return "invalid_or_unverified_metric"
    if reason_code.startswith(("session_", "generation_", "revision_")):
        return "session_identity_blocked"
    if reason_code.startswith(
        ("config_", "binding_", "permission_", "model_", "provider_")
    ):
        return "config_identity_blocked"
    if reason_code.startswith(("scope_", "workspace_", "host")):
        return "scope_identity_blocked"
    if reason_code.startswith(("snapshot_", "producer_")):
        return "schema_or_producer_blocked"
    return "blocked_unverified"


def _classify_unavailable(
    reason_code: str,
    audit: Mapping[str, Any],
    *,
    trust: str = "adapter_verified_snapshot",
) -> dict[str, Any]:
    """把一次不可得结果映射为有限分类；不采信调用方的 allow 标记。"""

    binding = audit.get("binding")
    identity_ok = _identity_verified(audit)
    producer_ok = audit.get("producer_supported") is True
    category = _FALLBACK_REASON_CATEGORIES.get(reason_code)
    eligible = bool(
        category is not None
        and isinstance(binding, Mapping)
        and identity_ok
        and (producer_ok or trust == "trusted_host_capability")
    )
    if category is None:
        category = _blocked_category(reason_code)
    checks = audit.get("checks")
    clean_checks = {
        key: value
        for key, value in (checks.items() if isinstance(checks, Mapping) else ())
        if isinstance(key, str) and isinstance(value, bool)
    }
    clean_binding = None
    if isinstance(binding, Mapping):
        raw_scope = binding.get("scope")
        if isinstance(raw_scope, Mapping):
            clean_binding = {
                "native_session_id": binding.get("native_session_id"),
                "session_generation": binding.get("session_generation"),
                "session_revision": binding.get("session_revision"),
                "scope": {
                    field: raw_scope.get(field) for field in _SCOPE_FIELDS
                },
                "scope_fingerprint": binding.get("scope_fingerprint"),
            }
    return {
        "schema": UNAVAILABILITY_SCHEMA,
        "version": UNAVAILABILITY_VERSION,
        "reason_code": reason_code,
        "category": category,
        "fallback_eligible": eligible,
        "window": clean_binding,
        "evidence": {
            "trust": trust,
            "trusted_host_source": (
                audit.get("trusted_host", {}).get("source")
                if isinstance(audit.get("trusted_host"), Mapping)
                else None
            ),
            "observed_at": audit.get("snapshot_observed_at"),
            "producer_supported": producer_ok,
            "identity_verified": identity_ok,
            "sample_present": False,
            "checks": clean_checks,
        },
    }


def _same_revision(left: Any, right: Any) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _normalize_revision(value: Any, field: str) -> str | int:
    if isinstance(value, str):
        return _require_identifier(value, field)
    if _safe_int(value):
        return value
    raise _DataError(field, "invalid_revision")


def _normalize_expected_scope(value: Any) -> dict[str, Any]:
    raw = _require_mapping(value, "expected_scope")
    normalized: dict[str, Any] = {}
    for field in _SCOPE_FIELDS:
        normalized[field] = _require_identifier(raw.get(field), f"expected_scope.{field}")
    normalized["native_session_id"] = _require_identifier(
        raw.get("native_session_id"), "expected_scope.native_session_id"
    )
    if not _safe_int(raw.get("session_generation"), minimum=1):
        raise _DataError("expected_scope.session_generation", "invalid_generation")
    normalized["session_generation"] = raw["session_generation"]
    normalized["session_revision"] = _normalize_revision(
        raw.get("session_revision"), "expected_scope.session_revision"
    )
    return normalized


def _base_audit(
    *, now: datetime, max_age_seconds: int, trusted_host: Mapping[str, Any] | None
) -> dict[str, Any]:
    return {
        "schema": ADAPTER_SCHEMA,
        "now": _iso(now),
        "max_age_seconds": max_age_seconds,
        "trusted_host": {
            "verified": bool(
                isinstance(trusted_host, Mapping)
                and trusted_host.get("verified") is True
            ),
            "source": None,
        },
        "checks": {},
        "metrics": {},
        "warnings": [],
    }


def _result(
    *,
    status: str,
    reason_code: str,
    context_sample: dict[str, Any] | None,
    audit: dict[str, Any],
    context_unavailability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": ADAPTER_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "reasons": [] if status == "known" else [reason_code],
        "context_sample": context_sample,
        "context_unavailability": context_unavailability,
        "audit": audit,
    }


def _fail(
    code: str, audit: dict[str, Any], *, checks: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if checks:
        audit["checks"].update(dict(checks))
    audit["unknown_reasons"] = [code]
    return _result(
        status="unknown",
        reason_code=code,
        context_sample=None,
        audit=audit,
        context_unavailability=_classify_unavailable(code, audit),
    )


def _check_trusted_host(trusted_host: Any) -> tuple[bool, str | None]:
    if not isinstance(trusted_host, Mapping):
        return False, None
    if trusted_host.get("verified") is not True:
        return False, None
    source = trusted_host.get("source")
    try:
        _require_identifier(source, "trusted_host.source")
    except _DataError:
        return False, None
    return True, source


def _check_producer(snapshot: Mapping[str, Any]) -> None:
    producer = _require_mapping(snapshot.get("producer"), "producer")
    if producer.get("module") != CAPTURE_MODULE:
        raise _DataError("producer.module", "unexpected_module")
    version = producer.get("version")
    if version != CAPTURE_VERSION:
        raise _DataError("producer.version", "invalid_version")
    contract = _require_mapping(producer.get("native_contract"), "producer.native_contract")
    if contract.get("package") != PRODUCER_NATIVE_PACKAGE:
        raise _DataError("producer.native_contract.package", "unexpected_package")
    if contract.get("frozen_version") != PRODUCER_NATIVE_FROZEN_VERSION:
        raise _DataError("producer.native_contract.frozen_version", "unexpected_version")
    if contract.get("projection_key") != PROJECTION_KEY:
        raise _DataError("producer.native_contract.projection_key", "unexpected_key")
    if (
        not _is_int(contract.get("expected_state_version"))
        or contract.get("expected_state_version") != EXPECTED_STATE_VERSION
    ):
        raise _DataError("producer.native_contract.expected_state_version", "unexpected_state")
    if contract.get("session_read_api") != SESSION_READ_API:
        raise _DataError("producer.native_contract.session_read_api", "unexpected_api")
    if contract.get("projection_read_api") != PROJECTION_READ_API:
        raise _DataError("producer.native_contract.projection_read_api", "unexpected_api")
    if contract.get("change_feed_api") != "sessionProjections.onChanged":
        raise _DataError("producer.native_contract.change_feed_api", "unexpected_api")


def _metric(
    snapshot: Mapping[str, Any],
    name: str,
    *,
    kind: str,
    observed_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    raw = _require_mapping(
        _require_mapping(snapshot.get("metrics"), "metrics").get(name),
        f"metrics.{name}",
    )
    state = raw.get("state")
    if not isinstance(state, str) or state not in _METRIC_STATES:
        raise _DataError(f"metrics.{name}.state", "invalid_state")
    value = raw.get("value")
    source = raw.get("source")
    if state in ("missing", "invalid", "unknown") and value is not None:
        raise _DataError(f"metrics.{name}.value", "state_value_inconsistent")
    if state == "missing" and source is not None:
        raise _DataError(f"metrics.{name}.source", "state_source_inconsistent")
    if state == "known":
        if not _safe_int(value):
            raise _DataError(f"metrics.{name}.value", "invalid_value")
        if kind == "capacity" and value <= 0:
            raise _DataError(f"metrics.{name}.value", "not_positive")
        raw_source = _require_mapping(source, f"metrics.{name}.source")
        if raw_source.get("kind") != "native_projection_change":
            raise _DataError(f"metrics.{name}.source.kind", "unexpected_source")
        seq = raw_source.get("seq")
        if not _safe_int(seq):
            raise _DataError(f"metrics.{name}.source.seq", "invalid_seq")
        source_time = _parse_time(
            raw_source.get("time"), f"metrics.{name}.source.time"
        )
        if source_time > observed_at or source_time > now:
            raise _DataError(f"metrics.{name}.source.time", "future_source")
        return {
            "state": "known",
            "value": value,
            "reason_code": "ok",
            "source": {
                "kind": "native_projection_change",
                "seq": seq,
                "time": _iso(source_time),
                "_time": source_time,
            },
        }
    if state == "unverified":
        if value is not None and not _safe_int(value):
            raise _DataError(f"metrics.{name}.value", "invalid_value")
        return {
            "state": "unverified",
            "value": value,
            "reason_code": _safe_reason(raw.get("reason_code")),
            "source": None,
        }
    return {
        "state": state,
        "value": None,
        "reason_code": _safe_reason(raw.get("reason_code")),
        "source": None,
    }


def _safe_reason(value: Any) -> str:
    if isinstance(value, str) and value and len(value) <= 80 and not _IDENTIFIER_CONTROL_RE.search(value):
        return value
    return "unknown"


def _config_value(
    snapshot: Mapping[str, Any],
    name: str,
    *,
    observed_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    raw = _require_mapping(
        _require_mapping(snapshot.get("config"), "config").get(name),
        f"config.{name}",
    )
    if raw.get("state") != "known":
        raise _DataError(f"config.{name}.state", "config_source_unverified")
    try:
        value = _require_identifier(raw.get("value"), f"config.{name}.value")
    except _DataError as exc:
        raise _DataError(exc.field, "config_value_invalid") from exc
    raw_source = _require_mapping(raw.get("source"), f"config.{name}.source")
    if raw_source.get("kind") != "request/context":
        raise _DataError(f"config.{name}.source.kind", "config_source_invalid")
    seq = raw_source.get("seq")
    if not _safe_int(seq):
        raise _DataError(f"config.{name}.source.seq", "config_source_invalid")
    try:
        source_time = _parse_time(
            raw_source.get("time"), f"config.{name}.source.time"
        )
    except _DataError as exc:
        raise _DataError(exc.field, "config_source_invalid") from exc
    if source_time > observed_at or source_time > now:
        raise _DataError(f"config.{name}.source.time", "config_source_future")
    return {
        "value": value,
        "seq": seq,
        "time": source_time,
        "time_iso": _iso(source_time),
    }


def _check_config(
    snapshot: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    observed_at: datetime,
    now: datetime,
    audit: dict[str, Any],
) -> tuple[datetime, int]:
    provider = _config_value(
        snapshot, "provider_id", observed_at=observed_at, now=now
    )
    model = _config_value(snapshot, "model_id", observed_at=observed_at, now=now)
    if provider["value"] != expected["provider_id"]:
        raise _DataError("config.provider_id.value", "provider_mismatch")
    if model["value"] != expected["model_id"]:
        raise _DataError("config.model_id.value", "model_mismatch")
    if provider["seq"] != model["seq"] or provider["time"] != model["time"]:
        raise _DataError("config.source", "config_source_inconsistent")
    config = _require_mapping(snapshot.get("config"), "config")
    binding = _require_mapping(
        config.get("model_binding_fingerprint"), "config.model_binding_fingerprint"
    )
    if binding.get("state") != "caller_attested":
        raise _DataError("config.model_binding_fingerprint.state", "binding_unverified")
    if binding.get("value") != expected["model_binding_fingerprint"]:
        raise _DataError(
            "config.model_binding_fingerprint", "binding_mismatch"
        )
    permission = _require_mapping(
        config.get("config_permission_fingerprint"),
        "config.config_permission_fingerprint",
    )
    if permission.get("state") != "caller_attested":
        raise _DataError(
            "config.config_permission_fingerprint.state", "permission_unverified"
        )
    if permission.get("value") != expected["config_permission_fingerprint"]:
        raise _DataError(
            "config.config_permission_fingerprint", "permission_mismatch"
        )
    audit["checks"]["model_match"] = True
    audit["checks"]["binding_match"] = True
    audit["checks"]["config_source_known"] = True
    audit["metrics"]["config_source_time"] = provider["time_iso"]
    audit["metrics"]["config_source_seq"] = provider["seq"]
    return provider["time"], provider["seq"]


def _check_host(
    snapshot: Mapping[str, Any],
    expected: Mapping[str, Any],
    audit: dict[str, Any],
) -> None:
    host = _require_mapping(snapshot.get("host"), "host")
    missing: list[str] = []
    for field in _SCOPE_FIELDS:
        if host.get(field) != expected[field]:
            missing.append(field)
    if missing:
        audit["checks"]["scope_match"] = False
        audit["mismatch_fields"] = missing
        raise _DataError("host", "scope_mismatch")
    if host.get("workspace_verified") is not True:
        raise _DataError("host.workspace_verified", "workspace_unverified")
    verification = _require_mapping(host.get("verification"), "host.verification")
    if verification.get("workspace") != "native_header_cwd_exact_match":
        raise _DataError("host.verification.workspace", "workspace_unverified")
    for field in ("native_home", "service_launch", "runner", "project_scope"):
        if verification.get(field) != "caller_attested":
            raise _DataError(f"host.verification.{field}", "host_attestation_invalid")
    attestation = _require_mapping(host.get("attestation"), "host.attestation")
    if attestation.get("verified") is not True:
        raise _DataError("host.attestation.verified", "host_unverified")
    _require_identifier(attestation.get("source"), "host.attestation.source")
    audit["checks"]["scope_match"] = True
    audit["checks"]["workspace_verified"] = True
    audit["binding"] = _window_binding(expected)


def _check_session(
    snapshot: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    audit: dict[str, Any],
) -> tuple[int, int]:
    session = _require_mapping(snapshot.get("session"), "session")
    if session.get("native_session_id") != expected["native_session_id"]:
        raise _DataError("session.native_session_id", "session_id_mismatch")
    lifecycle = _require_mapping(session.get("lifecycle"), "session.lifecycle")
    if lifecycle.get("state") != "live":
        raise _DataError("session.lifecycle.state", "session_not_live")
    if lifecycle.get("source") != SESSION_READ_API:
        raise _DataError("session.lifecycle.source", "session_source_unverified")
    if session.get("revision_source") != "projection_cut":
        raise _DataError("session.revision_source", "revision_source_invalid")
    if (
        not _is_int(session.get("generation"))
        or session.get("generation") != expected["session_generation"]
    ):
        raise _DataError("session.generation", "generation_mismatch")
    if session.get("generation_source") != "caller_bound_live_session":
        raise _DataError("session.generation_source", "generation_source_invalid")
    revision = _normalize_revision(session.get("revision"), "session.revision")
    if not _same_revision(revision, expected["session_revision"]):
        raise _DataError("session.revision", "revision_mismatch")
    projection = _require_mapping(session.get("projection"), "session.projection")
    if projection.get("key") != PROJECTION_KEY:
        raise _DataError("session.projection.key", "unexpected_key")
    if projection.get("authority") != "registry_snapshot":
        raise _DataError("session.projection.authority", "not_current_registry")
    if (
        not _is_int(projection.get("expected_state_version"))
        or projection.get("expected_state_version") != EXPECTED_STATE_VERSION
    ):
        raise _DataError("session.projection.expected_state_version", "unexpected_state")
    if projection.get("source") != PROJECTION_READ_API:
        raise _DataError("session.projection.source", "unexpected_api")
    if projection.get("cached_snapshot_used") is not False:
        raise _DataError("session.projection.cached_snapshot_used", "cached_not_current")
    if projection.get("checkpoint_used") is not False:
        raise _DataError("session.projection.checkpoint_used", "checkpoint_not_current")
    cut = projection.get("cut")
    if not _safe_int(cut):
        raise _DataError("session.projection.cut", "invalid_cut")
    if not _same_revision(cut, revision):
        raise _DataError("session.projection.cut", "cut_revision_mismatch")
    session_seq = session.get("session_seq")
    if not _safe_int(session_seq):
        raise _DataError("session.session_seq", "invalid_seq")
    if cut + 1 != session_seq:
        raise _DataError("session.projection.cut", "cut_seq_mismatch")
    if projection.get("session_seq") != session_seq:
        raise _DataError("session.projection.session_seq", "cut_seq_mismatch")
    audit["checks"]["session_id_match"] = True
    audit["checks"]["generation_match"] = True
    audit["checks"]["revision_match"] = True
    audit["checks"]["session_live"] = True
    audit["checks"]["projection_exact"] = True
    audit["metrics"]["session_revision"] = revision
    audit["metrics"]["session_seq"] = session_seq
    return cut, session_seq


def _age_us(now: datetime, source_time: datetime) -> int:
    age = now - source_time
    if age < timedelta(0):
        raise _DataError("time", "future_sample")
    return age // timedelta(microseconds=1)


def build_metrics_unavailability(
    *,
    reason_code: str,
    expected_scope: Mapping[str, Any],
    observed_at: datetime | str | int,
    trusted_host: Mapping[str, Any],
    producer_supported: bool = False,
) -> dict[str, Any]:
    """可信宿主在无当前快照时显式声明“指标不可得”的分类。

    只接受三种有限原因：未提供、尚无用量样本、运行器不提供该能力。调用方
    必须给出与精确 native session/generation/revision 及作用域绑定的预期值
    和可信宿主标签；本函数不读取外部状态，也不是跨进程认证。返回对象可直接
    作为 ``plan_execution_session(context_unavailability=...)`` 的输入。
    """

    if not isinstance(reason_code, str) or reason_code not in _HOST_ATTESTABLE_REASONS:
        raise ValueError("reason_code: not_attestable")
    trusted, trusted_source = _check_trusted_host(trusted_host)
    if not trusted:
        raise ValueError("trusted_host: unverified")
    try:
        expected = _normalize_expected_scope(expected_scope)
    except _DataError as exc:
        raise ValueError(f"expected_scope: {exc.field}") from exc
    try:
        observed = _parse_time(observed_at, "observed_at")
    except _DataError as exc:
        raise ValueError(f"observed_at: {exc.code}") from exc
    if not isinstance(producer_supported, bool):
        raise ValueError("producer_supported: must_be_bool")
    binding = _window_binding(expected)
    return {
        "schema": UNAVAILABILITY_SCHEMA,
        "version": UNAVAILABILITY_VERSION,
        "reason_code": reason_code,
        "category": _FALLBACK_REASON_CATEGORIES[reason_code],
        "fallback_eligible": True,
        "window": binding,
        "evidence": {
            "trust": "trusted_host_capability",
            "trusted_host_source": trusted_source,
            "observed_at": _iso(observed),
            "producer_supported": producer_supported,
            "identity_verified": True,
            "sample_present": False,
            "checks": {
                "trusted_host_verified": True,
                "trusted_scope_confirmed": True,
            },
        },
    }


def adapt_context_snapshot(
    snapshot: Mapping[str, Any],
    *,
    expected_scope: Mapping[str, Any],
    now: datetime | str | int,
    max_age_seconds: int,
    trusted_host: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one capture snapshot and produce a 288 ``context_sample``.

    ``now`` and ``max_age_seconds`` are required and explicit; there is no
    product-level freshness default. ``trusted_host`` must be the caller's
    explicit confirmation that the snapshot came from the in-process/trusted
    host side; this function cannot authenticate another process.

    Returns ``status="known"`` with ``context_sample`` only when identity,
    session revision, native provider/model/config binding, both source times
    and capacity all validate and fit the maximum age. Every other case returns
    ``status="unknown"`` with ``context_sample=None`` and a reason code.
    """

    try:
        now_value = _parse_time(now, "now")
    except _DataError as exc:
        raise ValueError(f"now: {exc.code}") from exc
    if not _safe_int(max_age_seconds):
        raise ValueError("max_age_seconds: invalid")
    audit = _base_audit(
        now=now_value, max_age_seconds=max_age_seconds, trusted_host=trusted_host
    )
    trusted, trusted_source = _check_trusted_host(trusted_host)
    if not trusted:
        return _fail("trusted_host_unverified", audit)
    audit["trusted_host"] = {"verified": True, "source": trusted_source}

    try:
        expected = _normalize_expected_scope(expected_scope)
    except _DataError:
        return _fail("expected_scope_invalid", audit)

    if not isinstance(snapshot, Mapping):
        return _fail("snapshot_invalid", audit)
    if set(snapshot.keys()) != _SNAPSHOT_TOP_FIELDS:
        audit["checks"]["snapshot_fields"] = False
        return _fail("snapshot_invalid", audit)
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        return _fail("snapshot_schema_unsupported", audit)
    if not _is_int(snapshot.get("schema_version")) or snapshot.get("schema_version") != 1:
        return _fail("snapshot_version_unsupported", audit)
    try:
        _check_producer(snapshot)
    except _DataError as exc:
        audit["producer_error"] = exc.code
        audit["error_field"] = exc.field
        return _fail("producer_unsupported", audit)
    audit["producer_supported"] = True
    try:
        observed_at = _parse_time(snapshot.get("observed_at"), "observed_at")
    except _DataError:
        return _fail("observed_at_invalid", audit)
    audit["snapshot_observed_at"] = _iso(observed_at)
    if observed_at > now_value:
        return _fail("snapshot_future", audit)
    try:
        capture = _require_mapping(snapshot.get("capture"), "capture")
        capture_status = capture.get("status")
        if capture_status not in ("available", "partial"):
            raise _DataError("capture.status", "capture_not_usable")
        blocking = capture.get("blocking_issues")
        if not isinstance(blocking, list) or any(
            not isinstance(item, str) or not item for item in blocking
        ):
            raise _DataError("capture.blocking_issues", "capture_not_usable")
        if blocking:
            audit["capture_blocking_issue_count"] = len(blocking)
            raise _DataError("capture.blocking_issues", "capture_blocking_issue")
    except _DataError as exc:
        audit["capture_error"] = exc.code
        audit["error_field"] = exc.field
        return _fail(exc.code, audit)
    audit["capture_status"] = capture_status

    try:
        _check_host(snapshot, expected, audit)
    except _DataError as exc:
        audit["identity_error"] = exc.code
        audit["error_field"] = exc.field
        return _fail(exc.code if exc.code != "scope_mismatch" else "scope_mismatch", audit)

    try:
        cut, _ = _check_session(snapshot, expected, audit=audit)
    except _DataError as exc:
        audit["session_error"] = exc.code
        audit["error_field"] = exc.field
        return _fail(exc.code, audit)

    try:
        config_time, config_seq = _check_config(
            snapshot, expected, observed_at=observed_at, now=now_value, audit=audit
        )
    except _DataError as exc:
        audit["config_error"] = exc.code
        audit["error_field"] = exc.field
        return _fail(exc.code, audit)

    try:
        projected = _metric(
            snapshot,
            "projected_tokens",
            kind="tokens",
            observed_at=observed_at,
            now=now_value,
        )
    except _DataError as exc:
        audit["metric_error"] = "projected"
        audit["error_field"] = exc.field
        return _fail(f"projected_{exc.code}", audit)
    try:
        pressure = _metric(
            snapshot,
            "pressure_tokens",
            kind="tokens",
            observed_at=observed_at,
            now=now_value,
        )
    except _DataError as exc:
        audit["metric_error"] = "pressure"
        audit["error_field"] = exc.field
        return _fail(f"pressure_{exc.code}", audit)
    try:
        capacity = _metric(
            snapshot,
            "context_window",
            kind="capacity",
            observed_at=observed_at,
            now=now_value,
        )
    except _DataError as exc:
        audit["metric_error"] = "capacity"
        audit["error_field"] = exc.field
        return _fail(f"capacity_{exc.code}", audit)

    # 缺字段不能抢先掩盖另一个字段的非法/不可信状态。所有已经存在的来源
    # 先过 cut、顺序及同事件时间校验，之后才允许分类为单纯 missing。
    for label, metric in (("projected", projected), ("pressure", pressure),
                          ("capacity", capacity)):
        if metric["state"] in ("invalid", "unverified", "unknown"):
            return _fail(f"{label}_{metric['state']}", audit)
    sources = [(config_seq, config_time)] + [
        (metric["source"]["seq"], metric["source"]["_time"])
        for metric in (projected, pressure, capacity)
        if metric["state"] == "known"
    ]
    if any(seq > cut for seq, _ in sources):
        return _fail("source_after_snapshot_cut", audit)
    times_by_seq = {}
    for seq, time in sources:
        if seq in times_by_seq and times_by_seq[seq] != time:
            return _fail("source_event_time_inconsistent", audit)
        times_by_seq[seq] = time
    if pressure["state"] == "known":
        pressure_source = pressure["source"]
        if config_seq > pressure_source["seq"] or config_time > pressure_source["_time"]:
            return _fail("config_changed_after_pressure_sample", audit)
        if capacity["state"] == "known" and (
            capacity["source"]["seq"] > pressure_source["seq"]
            or capacity["source"]["_time"] > pressure_source["_time"]
        ):
            return _fail("capacity_changed_after_pressure_sample", audit)
        if projected["state"] == "known" and (
            projected["source"]["seq"] < pressure_source["seq"]
            or projected["source"]["_time"] < pressure_source["_time"]
        ):
            return _fail("metric_source_order_invalid", audit)
    if capacity["state"] == "known" and config_seq > capacity["source"]["seq"]:
        return _fail("capacity_precedes_current_config", audit)
    ordered = sorted(times_by_seq.items())
    if any(left[1] > right[1] for left, right in zip(ordered, ordered[1:])):
        return _fail("metric_source_order_invalid", audit)

    if capacity["state"] != "known":
        if capacity["state"] == "missing":
            return _fail("capacity_missing", audit)
        if capacity["state"] == "invalid":
            return _fail("capacity_invalid", audit)
        if capacity["state"] == "unverified":
            return _fail("capacity_unverified", audit)
        return _fail("capacity_unknown", audit)

    if pressure["state"] != "known":
        # A projected value is derived from the pressure sample. Without a
        # known source time/identity for that sample, ordering cannot be
        # established; do not synthesize one.
        if projected["state"] == "known":
            return _fail("pressure_unavailable", audit)
        if pressure["state"] == "invalid":
            return _fail("pressure_invalid", audit)
        if pressure["state"] == "unverified":
            return _fail("pressure_unverified", audit)
        if pressure["state"] == "unknown":
            return _fail("pressure_unknown", audit)
        if projected["state"] == "invalid":
            return _fail("projected_invalid", audit)
        if projected["state"] == "unverified":
            return _fail("projected_unverified", audit)
        return _fail("tokens_missing", audit)

    if projected["state"] == "known":
        chosen = projected
        chosen_name = "projected"
    elif projected["state"] == "missing":
        chosen = pressure
        chosen_name = "pressure"
    elif projected["state"] == "invalid":
        # Explicitly invalid projected must never fall back to pressure.
        return _fail("projected_invalid", audit)
    elif projected["state"] == "unverified":
        return _fail("projected_unverified", audit)
    else:
        return _fail("projected_unknown", audit)

    used_time = chosen["source"]["_time"]
    pressure_time = pressure["source"]["_time"]
    capacity_time = capacity["source"]["_time"]
    used_seq = chosen["source"]["seq"]
    pressure_seq = pressure["source"]["seq"]
    capacity_seq = capacity["source"]["seq"]
    if any(seq > cut for seq in (config_seq, used_seq, pressure_seq, capacity_seq)):
        return _fail("source_after_snapshot_cut", audit)
    if used_seq < pressure_seq:
        return _fail("metric_source_order_invalid", audit)
    if config_seq > pressure_seq:
        return _fail("config_changed_after_pressure_sample", audit)
    if capacity_seq > pressure_seq:
        return _fail("capacity_changed_after_pressure_sample", audit)
    if config_seq > capacity_seq:
        return _fail("capacity_precedes_current_config", audit)
    times_by_seq = {}
    for seq, time in ((config_seq, config_time), (used_seq, used_time),
                      (pressure_seq, pressure_time), (capacity_seq, capacity_time)):
        if seq in times_by_seq and times_by_seq[seq] != time:
            return _fail("source_event_time_inconsistent", audit)
        times_by_seq[seq] = time
    if used_time < pressure_time:
        return _fail("metric_source_order_invalid", audit)
    if config_time > pressure_time:
        return _fail("config_changed_after_pressure_sample", audit)
    if capacity_time > pressure_time:
        return _fail("capacity_changed_after_pressure_sample", audit)

    try:
        used_age = _age_us(now_value, used_time)
        capacity_age = _age_us(now_value, capacity_time)
        pressure_age = _age_us(now_value, pressure_time)
    except _DataError:
        return _fail("sample_future", audit)
    if used_age > max_age_seconds * 1_000_000:
        return _fail("used_sample_expired", audit)
    if capacity_age > max_age_seconds * 1_000_000:
        return _fail("capacity_sample_expired", audit)
    if pressure_age > max_age_seconds * 1_000_000:
        return _fail("pressure_sample_expired", audit)

    # Config identity is current by exact value/source equality; its source
    # time is not a freshness clock for an old-but-unchanged model binding.
    sampled_at = min(used_time, capacity_time)
    context_sample: dict[str, Any] = {
        "native_session_id": expected["native_session_id"],
        "session_generation": expected["session_generation"],
        "session_revision": expected["session_revision"],
        "provider_id": expected["provider_id"],
        "model_id": expected["model_id"],
        "model_binding_fingerprint": expected["model_binding_fingerprint"],
        "context_window": capacity["value"],
        "sampled_at": _iso(sampled_at),
        "now": _iso(now_value),
        "max_age_seconds": max_age_seconds,
    }
    if chosen_name == "projected":
        context_sample["projected_tokens"] = chosen["value"]
    else:
        context_sample["pressure_tokens"] = chosen["value"]

    audit["capture_status"] = snapshot.get("capture", {}).get("status")
    audit["checks"].update(
        {
            "snapshot_schema": True,
            "producer_supported": True,
            "observed_at_not_future": True,
            "used_source_known": True,
            "capacity_source_known": True,
            "config_not_after_pressure": True,
            "capacity_not_after_pressure": True,
            "within_max_age": True,
            "source_seq_within_cut": True,
            "source_seq_order": True,
            "same_request_atomic": False,
            "cached_snapshot_used": False,
            "checkpoint_used": False,
        }
    )
    audit["metrics"] = {
        "chosen": chosen_name,
        "used_value": chosen["value"],
        "used_source_seq": chosen["source"]["seq"],
        "used_source_time": chosen["source"]["time"],
        "pressure_value": pressure["value"],
        "pressure_source_seq": pressure["source"]["seq"],
        "pressure_source_time": pressure["source"]["time"],
        "capacity_value": capacity["value"],
        "capacity_source_seq": capacity["source"]["seq"],
        "capacity_source_time": capacity["source"]["time"],
        "config_source_time": _iso(config_time),
        "config_source_seq": config_seq,
        "used_age_ms": used_age // 1000,
        "capacity_age_ms": capacity_age // 1000,
        "pressure_age_ms": pressure_age // 1000,
        "max_age_seconds": max_age_seconds,
        "same_request_atomic": False,
    }
    return _result(
        status="known",
        reason_code="ok",
        context_sample=context_sample,
        audit=audit,
    )
