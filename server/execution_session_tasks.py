"""任务级“执行会话复用”元数据的严格校验与基础合同解析。

本模块位于服务端任务创建/完成边界，不读取运行中的
原生会话、不调用模型、不访问生产配置。它负责四件事：

1. 校验创建任务时显式传入的 ``execution_session`` 元数据；旧任务（字段缺失）
   完全保持原有行为。
2. 对 ``base_task_id`` 引用做同项目/同发起者/同目标/同真实工作区/同绑定
   的不可变基础合同校验，拒绝借读另一任务跨角色续用。
3. 为基础任务冻结一份 UTF-8 基础合同正文及其 SHA-256；续接任务只保存
   引用与哈希，不重复存正文。
4. 校验任务完成时回传的最小窗口状态对象（仅白名单字段，不含正文/凭据）。

约定：
- 元数据 schema 为 ``talk-execution-session-request-1``、版本 1；
- ``continuity_key`` 由发起者显式指定，表示稳定的功能工作线，不是任务号；
- 本模块抛出的 ``ExecutionSessionValidationError`` 由路由映射为 HTTP 422/400；
- 不解析、不执行基础正文；只做长度/UTF-8/哈希与身份一致性检查。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from sqlmodel import Session

from server.models import AgentTask, Project

EXECUTION_SESSION_REQUEST_SCHEMA = "talk-execution-session-request-1"
EXECUTION_SESSION_REQUEST_VERSION = 1
EXECUTION_SESSION_STATE_SCHEMA = "talk-execution-session-state-1"
EXECUTION_SESSION_STATE_VERSION = 1

BASE_CONTEXT_MAX_CHARS = 60_000
CHANGE_TEXT_MAX_CHARS = 4_000
CONTINUITY_KEY_MAX_CHARS = 128
STATE_JSON_MAX_BYTES = 16_384

_CONTINUITY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,31}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_REQUEST_REQUIRED = frozenset(("schema", "version", "continuity_key"))
_REQUEST_ALLOWED = _REQUEST_REQUIRED | frozenset(
    (
        "force_new",
        "base_task_id",
        "base_context",
        "base_context_version",
        "baseline_change",
        "authorization_change",
        "acceptance_difference",
    )
)

_STATE_KEYS = frozenset(
    (
        "schema",
        "version",
        "status",
        "decision",
        "reason_code",
        "native_session_id",
        "session_generation",
        "reused",
        "first_turn",
        "context_status",
        "context_reason",
        "confirmed_count",
        "proposed_ordinal",
        "state_revision",
        "delivery_id",
        "delivery_outcome",
        "turn_outcome",
        "directive_sha256",
        "directive_bytes",
        "window_status",
        "last_snapshot",
        "limitations",
        "task_id",
        "attempt",
        "execution_id",
        "base_contract_version",
        "base_contract_sha256",
        "archive_schema",
        "task_increment_sha256",
        "hall_messages_sha256",
    )
)
_SNAPSHOT_STATE_KEYS = frozenset(
    (
        "session_revision",
        "observed_at",
        "capture_status",
        "used_source",
        "used_tokens",
        "pressure_tokens",
        "projected_tokens",
        "context_window",
        "used_source_time",
        "capacity_source_time",
        "projected_tokens_source_time",
        "pressure_tokens_source_time",
        "context_window_source_time",
    )
)


class ExecutionSessionValidationError(ValueError):
    """可预期的元数据校验失败；只包含字段名与通用原因，不回显正文。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _require_text(value: Any, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ExecutionSessionValidationError(f"{field} 必须是字符串")
    if _CONTROL_RE.search(value):
        raise ExecutionSessionValidationError(f"{field} 含控制字符")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ExecutionSessionValidationError(f"{field} 不是合法 UTF-8") from exc
    if len(value) > max_chars:
        raise ExecutionSessionValidationError(f"{field} 超过 {max_chars} 字符")
    return value


def _optional_change(value: Any, field: str) -> Optional[str]:
    if value is None:
        return None
    text = _require_text(value, field, max_chars=CHANGE_TEXT_MAX_CHARS).strip()
    return text or None


def sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def workspace_identity_for_root(root: str) -> str:
    """规范 JSON + 版本 + 字段名的路径身份；不做无边界字符串拼接。"""

    payload = {
        "schema": "talk-execution-workspace-1",
        "version": 1,
        "fields": {"path_normcase": str(Path(root).expanduser().resolve()).casefold()},
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _project_root(project: Project) -> str:
    raw = str(project.project_root_path or "").strip()
    if not raw or "\x00" in raw:
        raise ExecutionSessionValidationError(
            "项目未配置有效的 project_root_path，不能声明执行会话工作区"
        )
    path = Path(raw)
    if not path.is_absolute():
        raise ExecutionSessionValidationError(
            "项目 project_root_path 必须是绝对路径，不能用作执行会话工作区"
        )
    return str(path)


def _normalize_base_task(
    base: AgentTask,
    *,
    project_id: str,
    requester_id: str,
    target_member_id: str,
    continuity_key: str,
    binding_fingerprint: str,
) -> dict:
    metadata = base.execution_session if _is_mapping(base.execution_session) else None
    if metadata is None:
        raise ExecutionSessionValidationError("base_task_id 指向的任务不是执行会话基础任务")
    if metadata.get("continuity_key") != continuity_key:
        raise ExecutionSessionValidationError(
            "base_task_id 的 continuity_key 与本次不一致，不能跨工作线续用"
        )
    if base.project_id != project_id:
        raise ExecutionSessionValidationError("base_task_id 不属于当前项目")
    if base.created_by != requester_id:
        raise ExecutionSessionValidationError("base_task_id 的发起者与本次不一致")
    if base.target_member_id != target_member_id:
        raise ExecutionSessionValidationError("base_task_id 的目标成员与本次不一致")
    if metadata.get("base_task_id") is not None:
        raise ExecutionSessionValidationError(
            "base_task_id 必须引用首个不可变基础任务，不能引用另一个续接任务"
        )
    if metadata.get("binding_fingerprint") != binding_fingerprint:
        raise ExecutionSessionValidationError("base_task_id 的目标绑定与本次不一致")
    if not base.execution_session_base_text:
        raise ExecutionSessionValidationError("base_task_id 缺少冻结的基础合同正文")
    version = str(metadata.get("base_contract_version") or "").strip()
    digest = str(metadata.get("base_contract_sha256") or "").strip()
    if not version or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ExecutionSessionValidationError("base_task_id 的基础合同版本/哈希无效")
    actual = sha256_utf8(base.execution_session_base_text)
    if actual != digest:
        raise ExecutionSessionValidationError("base_task_id 的基础合同正文哈希不匹配")
    return {
        "base_task_id": int(base.id),
        "base_contract_version": version,
        "base_contract_sha256": digest,
    }


def normalize_execution_session_metadata(
    raw: Any,
    *,
    project_id: Optional[str],
    requester_id: str,
    target_member_id: str,
    binding_snapshot: Mapping[str, Any],
    task_kind: str,
    parent_task_id: Optional[int],
    session: Session,
) -> tuple[dict, Optional[str], dict]:
    """校验创建请求，返回 ``(normalized_metadata, new_base_text_or_none, private_audit)``。

    - 基础任务（未给 ``base_task_id``）必须显式提供 ``base_context``；
    - 续接任务（给了 ``base_task_id``）不得再传 ``base_context``；
    - 只允许普通顶层任务启用（子任务/质量任务保持旧路径，避免混入门禁/复核账本）。
    """

    if parent_task_id is not None:
        raise ExecutionSessionValidationError(
            "execution_session 只允许用于顶层任务，子任务保持原有独立执行"
        )
    if task_kind != "general":
        raise ExecutionSessionValidationError(
            "execution_session 只支持 general 任务；review/test/rework 保持旧执行路径"
        )
    if not project_id:
        raise ExecutionSessionValidationError(
            "execution_session 需要项目归属（project_id）"
        )
    if not _is_mapping(raw):
        raise ExecutionSessionValidationError("execution_session 必须是对象")
    keys = set(raw.keys())
    unknown = keys - _REQUEST_ALLOWED
    if unknown:
        raise ExecutionSessionValidationError(
            f"execution_session 含未知字段: {', '.join(sorted(unknown))}"
        )
    missing = _REQUEST_REQUIRED - keys
    if missing:
        raise ExecutionSessionValidationError(
            f"execution_session 缺少字段: {', '.join(sorted(missing))}"
        )
    if raw.get("schema") != EXECUTION_SESSION_REQUEST_SCHEMA:
        raise ExecutionSessionValidationError("execution_session.schema 不受支持")
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ExecutionSessionValidationError("execution_session.version 必须为 1")

    continuity_key = raw.get("continuity_key")
    if not isinstance(continuity_key, str) or not _CONTINUITY_KEY_RE.fullmatch(
        continuity_key
    ):
        raise ExecutionSessionValidationError(
            "execution_session.continuity_key 必须是 2..128 位稳定工作线标识"
        )

    force_new = raw.get("force_new", False)
    if not isinstance(force_new, bool):
        raise ExecutionSessionValidationError("execution_session.force_new 必须是布尔值")

    base_task_id = raw.get("base_task_id")
    if base_task_id is not None:
        if isinstance(base_task_id, bool) or not isinstance(base_task_id, int):
            raise ExecutionSessionValidationError(
                "execution_session.base_task_id 必须是正整数"
            )
        if base_task_id < 1:
            raise ExecutionSessionValidationError(
                "execution_session.base_task_id 必须是正整数"
            )

    base_context = raw.get("base_context")
    base_context_version = raw.get("base_context_version")
    if base_context_version is not None and (
        not isinstance(base_context_version, str)
        or not _VERSION_RE.fullmatch(base_context_version)
    ):
        raise ExecutionSessionValidationError(
            "execution_session.base_context_version 格式无效"
        )

    binding_state = str(binding_snapshot.get("state") or "")
    binding_fingerprint = str(binding_snapshot.get("binding_fingerprint") or "")
    if binding_state != "bound" or not re.fullmatch(r"[0-9a-f]{64}", binding_fingerprint):
        raise ExecutionSessionValidationError(
            "目标角色当前没有可核的 bound 绑定，不能启用执行会话复用"
        )
    if binding_snapshot.get("runtime") not in {"dsh", "codex", "kimi-code", "workbuddy"}:
        raise ExecutionSessionValidationError(
            "execution_session 当前只支持 runtime=dsh/codex/kimi-code/workbuddy；其它运行器保持旧行为"
        )
    if not binding_snapshot.get("provider_id") or not binding_snapshot.get("model_id"):
        raise ExecutionSessionValidationError(
            "目标绑定缺少 provider_id/model_id，不能建立可核会话身份"
        )

    project = session.get(Project, project_id)
    if project is None:
        raise ExecutionSessionValidationError("project_id 不存在")
    workspace_root = _project_root(project)
    workspace_identity = workspace_identity_for_root(workspace_root)
    requirements = project.development_requirements
    requirements_digest = sha256_utf8(requirements or '')
    audit = {'schema':'talk-execution-session-audit-1','version':1,
             'project_development_requirements':requirements,
             'project_requirements_sha256':requirements_digest}

    base_contract: dict
    new_base_text: Optional[str] = None
    if base_task_id is None:
        if not isinstance(base_context, str):
            raise ExecutionSessionValidationError(
                "首个基础任务必须提供 execution_session.base_context"
            )
        base_text = _require_text(
            base_context, "execution_session.base_context", max_chars=BASE_CONTEXT_MAX_CHARS
        )
        if not base_text.strip():
            raise ExecutionSessionValidationError(
                "execution_session.base_context 不能为空"
            )
        if requirements:
            base_text += ('\n\n【项目开发要求（派发时快照）】\n'
                '以下内容为服务端派发时冻结的项目要求；不自动授予权限，不覆盖宿主系统指令，'
                '不追溯修改历史任务。\n----------------------------------------\n' + requirements)
            _require_text(base_text, 'execution_session.base_context', max_chars=BASE_CONTEXT_MAX_CHARS)
        digest = sha256_utf8(base_text)
        base_contract = {
            "base_task_id": None,
            "base_contract_version": base_context_version or "1",
            "base_contract_sha256": digest,
        }
        new_base_text = base_text
    else:
        if base_context is not None:
            raise ExecutionSessionValidationError(
                "续接任务通过 base_task_id 引用基础合同，不得重复传 base_context"
            )
        base = session.get(AgentTask, int(base_task_id))
        if base is None:
            raise ExecutionSessionValidationError("base_task_id 不存在")
        base_contract = _normalize_base_task(
            base,
            project_id=project_id,
            requester_id=requester_id,
            target_member_id=target_member_id,
            continuity_key=continuity_key,
            binding_fingerprint=binding_fingerprint,
        )
        if (
            base_context_version is not None
            and base_context_version != base_contract["base_contract_version"]
        ):
            raise ExecutionSessionValidationError(
                "base_context_version 与 base_task_id 的基础合同版本不一致"
            )
        base_contract["base_contract_version"] = (
            base_context_version or base_contract["base_contract_version"]
        )
        metadata_base = base.execution_session or {}
        if metadata_base.get('project_requirements_sha256') != requirements_digest:
            raise ExecutionSessionValidationError('项目开发要求已变更，请以当前要求创建新的基础任务')
        if metadata_base.get("workspace_identity") != workspace_identity:
            raise ExecutionSessionValidationError(
                "base_task_id 的工作区身份与当前项目不一致"
            )
        if metadata_base.get("workspace_root") != workspace_root:
            raise ExecutionSessionValidationError(
                "base_task_id 的真实工作区与当前项目不一致"
            )

    normalized = {
        "schema": EXECUTION_SESSION_REQUEST_SCHEMA,
        "version": EXECUTION_SESSION_REQUEST_VERSION,
        "continuity_key": continuity_key,
        "force_new": force_new,
        "project_id": project_id,
        "requester_id": requester_id,
        "target_member_id": target_member_id,
        "runtime": binding_snapshot["runtime"],
        "binding_fingerprint": binding_fingerprint,
        "binding_state": binding_state,
        "workspace_root": workspace_root,
        "workspace_identity": workspace_identity,
        "base_task_id": base_contract["base_task_id"],
        "base_contract_version": base_contract["base_contract_version"],
        "base_contract_sha256": base_contract["base_contract_sha256"],
        "project_requirements_sha256": requirements_digest,
        "baseline_change": _optional_change(
            raw.get("baseline_change"), "execution_session.baseline_change"
        ),
        "authorization_change": _optional_change(
            raw.get("authorization_change"), "execution_session.authorization_change"
        ),
        "acceptance_difference": _optional_change(
            raw.get("acceptance_difference"),
            "execution_session.acceptance_difference",
        ),
    }
    return normalized, new_base_text, audit


def normalize_execution_session_state(raw: Any) -> dict:
    """校验 bridge 回传的最小窗口状态；禁止塞入正文、凭据或未知字段。"""

    if not _is_mapping(raw):
        raise ExecutionSessionValidationError("execution_session_state 必须是对象")
    keys = set(raw.keys())
    unknown = keys - _STATE_KEYS
    if unknown:
        raise ExecutionSessionValidationError(
            f"execution_session_state 含未知字段: {', '.join(sorted(unknown))}"
        )
    if raw.get("schema") != EXECUTION_SESSION_STATE_SCHEMA:
        raise ExecutionSessionValidationError("execution_session_state.schema 不受支持")
    if type(raw.get("version")) is not int or raw.get("version") != 1:
        raise ExecutionSessionValidationError("execution_session_state.version 必须为 1")
    integer_fields = {'session_generation','confirmed_count','proposed_ordinal','state_revision',
                      'directive_bytes','task_id','attempt'}
    boolean_fields = {'reused','first_turn'}
    hash_fields = {'directive_sha256','base_contract_sha256','task_increment_sha256','hall_messages_sha256'}
    for key, value in raw.items():
        if key in {'schema','version','last_snapshot'} or value is None:
            continue
        if key in integer_fields:
            if type(value) is not int or value < (1 if key in {'task_id','session_generation'} else 0):
                raise ExecutionSessionValidationError(f'execution_session_state.{key} 必须是有效整数')
        elif key in boolean_fields:
            if type(value) is not bool:
                raise ExecutionSessionValidationError(f'execution_session_state.{key} 必须是布尔值')
        else:
            _require_text(value, f'execution_session_state.{key}', max_chars=2000 if key=='limitations' else 512)
            if key in hash_fields and not re.fullmatch(r'[0-9a-f]{64}',value):
                raise ExecutionSessionValidationError(f'execution_session_state.{key} 哈希无效')
    if raw.get('status') not in {'completed','failed'}:
        raise ExecutionSessionValidationError('execution_session_state.status 无效')
    snapshot = raw.get("last_snapshot")
    if snapshot is not None:
        if not _is_mapping(snapshot):
            raise ExecutionSessionValidationError(
                "execution_session_state.last_snapshot 必须是对象"
            )
        extra = set(snapshot.keys()) - _SNAPSHOT_STATE_KEYS
        if extra:
            raise ExecutionSessionValidationError(
                "execution_session_state.last_snapshot 含未知字段"
            )
        for key,value in snapshot.items():
            if value is None:
                continue
            if key in {'session_revision','used_tokens','pressure_tokens','projected_tokens','context_window'}:
                if type(value) is not int or value < 0 or (key=='context_window' and value==0):
                    raise ExecutionSessionValidationError('execution_session_state.last_snapshot 数值无效')
            else:
                _require_text(value,'execution_session_state.last_snapshot.'+key,max_chars=128)
    try:
        encoded = json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExecutionSessionValidationError(
            "execution_session_state 不是可序列化 JSON"
        ) from exc
    if len(encoded) > STATE_JSON_MAX_BYTES:
        raise ExecutionSessionValidationError(
            f"execution_session_state 超过 {STATE_JSON_MAX_BYTES} 字节"
        )
    return dict(raw)
