"""SQLModel data models for TALK platform."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field as PydField, StrictBool, field_validator, model_validator
from sqlalchemy import CheckConstraint, Column, Index, JSON, text
from sqlmodel import Field, Session, SQLModel, select

from server.hall_types import DEFAULT_HALL_TYPE, HALL_TYPES


# ── ORM models (SQLite tables) ──────────────────────────────────────


class Member(SQLModel, table=True):
    __tablename__ = "members"

    id: str = Field(primary_key=True)  # 'human:bobo' / 'agent:AI1'
    kind: str  # 'human' | 'agent'
    display_name: str
    api_key: str = Field(unique=True, index=True)
    poll_hint: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # 全局禁用（UI #3 / 软删）：非空 = 已禁用，被鉴权拒绝；保留行以维持 messages.from_id 归属。
    disabled_at: Optional[datetime] = Field(default=None, index=True)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: Optional[str] = Field(default=None, foreign_key="groups.id", index=True)
    from_id: str = Field(foreign_key="members.id", index=True)
    to_ids: Optional[str] = None  # JSON array string; NULL = broadcast
    type: str  # 'text' | 'file'
    content: Optional[str] = None
    file_id: Optional[str] = Field(default=None, foreign_key="files.id")
    reply_to: Optional[int] = Field(default=None, foreign_key="messages.id")
    caption: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    mime: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = Field(default=None, foreign_key="members.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def to_list(self) -> list[str] | None:
        if self.to_ids is None:
            return None
        return json.loads(self.to_ids)


class File(SQLModel, table=True):
    __tablename__ = "files"

    id: str = Field(primary_key=True)  # uuid4
    filename: str
    mime: Optional[str] = None
    size_bytes: int
    sha256: str = Field(index=True)
    uploader_id: str = Field(foreign_key="members.id")
    path: str  # disk relative path
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: str = Field(primary_key=True)
    name: str
    description: Optional[str] = None
    type: str = Field(default=DEFAULT_HALL_TYPE, index=True)
    project_id: Optional[str] = Field(default=None, foreign_key="projects.project_id", index=True)
    created_by: str = Field(foreign_key="members.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GroupMember(SQLModel, table=True):
    __tablename__ = "group_members"

    group_id: str = Field(foreign_key="groups.id", primary_key=True)
    member_id: str = Field(foreign_key="members.id", primary_key=True, index=True)
    role: str = Field(default="member", index=True)  # chat role: owner | moderator | member
    # 协作层（PROJECT_INTEGRATION §5.2）：业务角色 + 决策分级，按 (群, 成员) 存储。
    # business_role 自由文本（lead / dev / ui / tester / reviewer / ...）；decision_tier ∈ {decision, execution}。
    business_role: Optional[str] = Field(default=None, index=True)
    decision_tier: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Project(SQLModel, table=True):
    """A project that integrates with TALK (registered via `talk init`)."""

    __tablename__ = "projects"

    project_id: str = Field(primary_key=True)  # CLI-generated, e.g. 'prj_a1b2c3d4e5f6'
    display_name: str
    description: Optional[str] = None
    project_root_path: Optional[str] = None
    # 项目级“开发要求”：只保存最新纯文本，无版本号/历史；NULL 表示无内容。
    # 主控派发新任务前读取，并把派发时快照写进任务正文。
    development_requirements: Optional[str] = None
    # 项目主控模式“意向”（C1a）：passive（默认）/ active。
    # 只表示项目保存的配置意向，**不代表任何会话已生效**；生效状态见 MCP 只读输出的
    # effective_mode / effective_status（本片恒为 null / not_bound）。
    controller_mode: str = Field(default="passive")
    # 模式版本：非负整数，初始 0；只在意向实际变化时 +1（同值幂等不增）。
    # 写入必须走专用 CAS 入口（PATCH /api/projects/{id}/controller-mode），
    # 普通元数据 PATCH / 注册 / CLI 重注册都不得旁路修改。
    controller_mode_version: int = Field(default=0)
    # 长期项目主控指定（C1b-S）：项目内具体 member_id 为身份，NULL = 未指定。
    # 长期保存、无期限、不续租；名册 sync / 成员禁用 / 服务重启都不自动清除或转移，
    # 只能由 human 经专用 CAS 入口（PATCH /api/projects/{id}/controller-assignment）解除或更换。
    # 刻意不加外键：成员行缺失时要能如实报告 member_missing，而不是写入失败或静默置空。
    controller_member_id: Optional[str] = Field(default=None)
    # 指定版本：非负整数，初始 0；只在指定实际变化时 +1（同值幂等不增）。
    # 与 controller_mode_version 相互独立，不复用。
    controller_assignment_version: int = Field(default=0)
    maintainer_member_id: str = Field(foreign_key="members.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectAgent(SQLModel, table=True):
    """Per-(project, agent) profile path index (PROJECT_INTEGRATION §7.1).

    Server stores only the relative paths to the agent's `.talk/` profile files;
    the actual file content stays in the project repo and is read by the bridge.
    member_id is plain TEXT (no FK) so a profile can be synced before the agent
    self-registers as a Member.
    """

    __tablename__ = "project_agents"

    project_id: str = Field(foreign_key="projects.project_id", primary_key=True)
    member_id: str = Field(primary_key=True)
    identity_path: Optional[str] = None
    soul_path: Optional[str] = None
    user_path: Optional[str] = None
    memory_pointer: Optional[str] = None
    business_role: Optional[str] = Field(default=None, index=True)
    decision_tier: Optional[str] = Field(default=None, index=True)
    capability_summary: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRoleDescription(SQLModel, table=True):
    """项目角色说明：human 为角色名称下固定短标签/解释保存的自定义文本（ROLE-DESC-B1）。

    设计事实（``.tmp/role-description-0/design.md`` §3.1）：

    - **独立表**，刻意不加在 ``project_agents`` 上：名册 ``POST /sync`` 是全量替换
      （先删后插），挂在那张表上的手工字段会被 sync 抹掉；
    - 主键 ``(project_id, member_id)`` 天然实现同角色跨项目隔离；
    - ``member_id`` 不加外键：名册 sync 全量增删、成员可能暂缺；成员离开名册时说明行保留
      （“离册保留、回册恢复”是预期行为，不是脏数据），项目删除时才显式清理；
    - 无行 = 使用前端默认文案；有行 = human 自定义说明（原文保留，不 strip、不折叠换行）。
    """

    __tablename__ = "project_role_descriptions"

    project_id: str = Field(foreign_key="projects.project_id", primary_key=True)
    member_id: str = Field(primary_key=True)
    description: str
    updated_by: str = Field(foreign_key="members.id")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentInstance(SQLModel, table=True):
    __tablename__ = "agent_instances"

    id: str = Field(primary_key=True)
    member_id: str = Field(foreign_key="members.id", index=True)
    runtime: str = Field(index=True)
    status: str = Field(index=True)
    # 角色生命周期 R1-1（合同 §4.2 / §10.4）：只加列，旧行保持 NULL。
    # ``NULL`` = 该实例未声明项目 / 无启动动作关联，**不**回填猜测值；
    # ``project_id`` 一旦非空不可改写/清空，``launch_id`` 一旦非空不可改写/清空；
    # 不新增 ``generation`` 列：世代由不可变 launch 行推导。
    project_id: Optional[str] = Field(default=None, index=True)
    launch_id: Optional[str] = Field(default=None, index=True)
    process_started_at: Optional[datetime] = None
    host: Optional[str] = None
    pid: Optional[int] = None
    current_task_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


TASK_MAX_DELEGATION_DEPTH_DEFAULT = 1
TASK_MAX_RUNNING_DESCENDANTS_DEFAULT = 3
TASK_MAX_RUNNING_PER_TARGET_DEFAULT = 1
TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT = 8
TASK_AUTHORIZED_SLICE_BUDGET_DEFAULT = 2
TASK_AUTHORIZED_SLICE_BUDGET_MAX = 3
TASK_AUTHORIZATION_TTL_DEFAULT_SECONDS = 90 * 60
TASK_AUTHORIZATION_TTL_MIN_SECONDS = 60
TASK_AUTHORIZATION_TTL_MAX_SECONDS = 90 * 60
TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT = 1
TASK_MAX_CLARIFICATION_ROUNDS_LIMIT = 2

# 项目级“开发要求”纯文本上限：用于创建与更新的同一套校验（按字符数计算）。
PROJECT_DEVELOPMENT_REQUIREMENTS_MAX_CHARS = 20000

# 项目角色说明上限（ROLE-DESC-B1）：说明是短文本，不照搬开发要求的 20000。
# 长度按 **Unicode 码点** 计算（Python ``len()`` 即码点计数，代理对在 Python 3 中只算 1）。
PROJECT_ROLE_DESCRIPTION_MAX_CHARS = 2000

# 项目主控模式意向（C1a）：只允许这两个枚举；新建/旧项目一律默认 passive。
PROJECT_CONTROLLER_MODES = ("passive", "active")
PROJECT_CONTROLLER_MODE_DEFAULT = "passive"

# SQLite INTEGER 为有符号 64 位：超出该范围的值无法绑定，会在写入层抛 OverflowError。
# 版本类入参在请求校验层就用它做上界，避免异常输入变成 HTTP 500。
SQLITE_SIGNED_INTEGER_MAX = 9223372036854775807

# 项目主控指定的配置有效性状态（C1b-S1）。只描述“保存的指定 + 当前名册/成员事实”，
# 与在线状态、会话确认、任务授权无关：`assigned` 也不代表在线或已 ACK。
PROJECT_ASSIGNMENT_UNASSIGNED = "unassigned"  # 未指定
PROJECT_ASSIGNMENT_ASSIGNED = "assigned"  # 已指定且成员已注册、未禁用、在项目名册中且为 agent
PROJECT_ASSIGNMENT_MEMBER_MISSING = "member_missing"  # 指定成员已不存在（members 行缺失）
PROJECT_ASSIGNMENT_MEMBER_DISABLED = "member_disabled"  # 指定成员已被全局禁用
PROJECT_ASSIGNMENT_NOT_IN_ROSTER = "not_in_roster"  # 指定成员不在该项目名册（project_agents）
PROJECT_ASSIGNMENT_NOT_AGENT = "not_agent"  # 指定指向的不是 agent 成员
# 状态判定优先级（同一指定可能同时命中多个问题，取第一条如实报告）：
# member_missing → member_disabled → not_in_roster → not_agent → assigned。
PROJECT_ASSIGNMENT_STATUSES = (
    PROJECT_ASSIGNMENT_UNASSIGNED,
    PROJECT_ASSIGNMENT_ASSIGNED,
    PROJECT_ASSIGNMENT_MEMBER_MISSING,
    PROJECT_ASSIGNMENT_MEMBER_DISABLED,
    PROJECT_ASSIGNMENT_NOT_IN_ROSTER,
    PROJECT_ASSIGNMENT_NOT_AGENT,
)


def normalize_development_requirements(value: Optional[str]) -> Optional[str]:
    """归一化项目级开发要求：保留原文与换行，只做长度校验和空值归一。

    - ``None`` 或全空白文本（含 ``""``）统一归一为 ``None``，表示“无内容/清空”；
    - 非空文本原样保留（不 strip、不折叠换行），仅校验字符数上限；
    - 超长直接抛 ``ValueError``，由 FastAPI 转成 422，创建与更新语义一致。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("development_requirements must be a string or null")
    if len(value) > PROJECT_DEVELOPMENT_REQUIREMENTS_MAX_CHARS:
        raise ValueError(
            "development_requirements must be at most "
            f"{PROJECT_DEVELOPMENT_REQUIREMENTS_MAX_CHARS} characters"
        )
    if not value.strip():
        return None
    return value


def normalize_role_description(value: Optional[str]) -> Optional[str]:
    """归一化项目角色说明（ROLE-DESC-B1）：先判空白归 ``None``，再查 2000 码点上限。

    与 :func:`normalize_development_requirements` 的关键差异（设计 §3.2-D8，**不照搬**）：
    那里是先查长度再判空白，会让“超长全空白”得到 422；角色说明要求“超长全空白”按
    **恢复默认**（``None``）处理，因此本函数必须**先归空白、后查长度**。这是唯一事实，
    前后端必须同序，不得分叉。

    - ``None`` 或全空白文本（含 ``""``）→ ``None``（删除自定义说明 = 恢复默认）；
    - 空白判定沿用 Python ``str.isspace()`` 语义（``str.strip()`` 无参时移除的字符集与
      ``str.isspace()`` 完全一致），包含 U+001C–U+001F、U+0085、U+00A0、U+2000–U+200A、
      U+2028/U+2029、U+202F、U+205F、U+3000 等；前端不得改用 JS ``trim()``（会多算 U+FEFF、
      漏算 U+001C–U+001F/U+0085），否则归一化分叉会让空白保存在前端永远“未确认”；
    - 非空白文本原样保留（不 strip、不折叠换行），只校验 Unicode 码点数上限；
    - 非空白且超长抛 ``ValueError``，由 FastAPI 转成 422。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("description must be a string or null")
    if not value.strip():
        return None
    if len(value) > PROJECT_ROLE_DESCRIPTION_MAX_CHARS:
        raise ValueError(
            "description must be at most "
            f"{PROJECT_ROLE_DESCRIPTION_MAX_CHARS} characters"
        )
    return value


def normalize_controller_member_id(value: Optional[str]) -> Optional[str]:
    """归一化主控指定成员 ID：``None`` 保持 ``None``（解除指定），字符串去首尾空白。

    空字符串或全空白字符串不视为“解除”，直接抛 ``ValueError``（由 FastAPI 转 422）：
    解除必须显式传 ``null``，避免客户端把“没填”和“清空”混为一谈。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("member_id must be a string or null")
    normalized = value.strip()
    if not normalized:
        raise ValueError("member_id must be a non-empty string, or null to clear the assignment")
    return normalized


def resolve_controller_assignment_status(project: Project, session: "Session") -> str:
    """按当前库内事实计算项目主控指定的配置有效性状态（只读，不修改任何数据）。

    判定优先级见 ``PROJECT_ASSIGNMENT_STATUSES`` 上方的说明。本函数只回答
    “保存的指定现在是否有效”，不回答在线、ACK、会话归属或授权。
    """
    member_id = (project.controller_member_id or "").strip()
    if not member_id:
        return PROJECT_ASSIGNMENT_UNASSIGNED
    member = session.get(Member, member_id)
    if member is None:
        return PROJECT_ASSIGNMENT_MEMBER_MISSING
    if member.disabled_at is not None:
        return PROJECT_ASSIGNMENT_MEMBER_DISABLED
    if session.get(ProjectAgent, (project.project_id, member_id)) is None:
        return PROJECT_ASSIGNMENT_NOT_IN_ROSTER
    if member.kind != "agent":
        return PROJECT_ASSIGNMENT_NOT_AGENT
    return PROJECT_ASSIGNMENT_ASSIGNED


# ════════════════════════════════════════════════════════════════════
# 全局运行器登记 + 项目角色绑定（ROLE-BINDING-B1a）
#
# 实施依据：``docs/spec/ROLE_MODEL_BINDING_DESIGN.md`` §2–§6、§7.3、§10–§11 与
# ``docs/spec/ROLE_MODEL_BINDING_IMPLEMENTATION_PLAN.md`` §1(B1a)。
#
# 本片只做“登记 + 绑定 + 单语句事实读取”：不启动进程、不调用模型、不读凭据、
# 不探测连接、不改任务表/任务权限、不输出任何 binding_match（B2 才定义实际证据）。
# ════════════════════════════════════════════════════════════════════

# 枚举：运行器接入程度（合同 §3.2）。登记 ≠ 加入项目 ≠ 允许启动。
RUNNER_ADAPTER_ADAPTED = "adapted"
RUNNER_ADAPTER_DISCOVERABLE = "discoverable"
RUNNER_ADAPTER_UNVERIFIED = "unverified"
RUNNER_ADAPTER_RETIRED = "retired"
RUNNER_ADAPTER_STATUSES = (
    RUNNER_ADAPTER_ADAPTED,
    RUNNER_ADAPTER_DISCOVERABLE,
    RUNNER_ADAPTER_UNVERIFIED,
    RUNNER_ADAPTER_RETIRED,
)
RUNNER_ADAPTER_STATUS_DEFAULT = RUNNER_ADAPTER_UNVERIFIED

# 枚举：运行器控制能力（角色生命周期 R1-1，合同 §12）。只声明控制来源，
# 不表示已核验/可启动；旧行默认 ``unknown``。
RUNNER_CONTROL_MANAGED_CLI = "managed_cli"
RUNNER_CONTROL_EXTERNAL_SESSION = "external_session"
RUNNER_CONTROL_UNKNOWN = "unknown"
RUNNER_CONTROL_KINDS = (
    RUNNER_CONTROL_MANAGED_CLI,
    RUNNER_CONTROL_EXTERNAL_SESSION,
    RUNNER_CONTROL_UNKNOWN,
)
RUNNER_CONTROL_KIND_DEFAULT = RUNNER_CONTROL_UNKNOWN

# 枚举：模型来源（合同 §4.1）。
MODEL_SOURCE_BUILTIN = "builtin"
MODEL_SOURCE_CUSTOM_API = "custom_api"
MODEL_SOURCES = (MODEL_SOURCE_BUILTIN, MODEL_SOURCE_CUSTOM_API)

# 角色生命周期 R1-1（合同 §4.1.1–§4.1.4 / §7 / §8）：
# - 模型选择目录的来源等级只描述“这条登记从哪来”，**不是**能力验证；
# - 角色来源只有 managed（新流程创建）/ imported（历史名册补录）；
# - 权限策略来源只用于审计，判定始终只看 review_exempt；
# - 独占身份引用守卫的稳定错误码。
MODEL_CHOICE_SOURCE_DECLARED = "declared"
MODEL_CHOICE_SOURCE_NATIVE_CONFIG = "native_config"
MODEL_CHOICE_SOURCE_VERIFIED = "verified"
MODEL_CHOICE_SOURCE_KINDS = (
    MODEL_CHOICE_SOURCE_DECLARED,
    MODEL_CHOICE_SOURCE_NATIVE_CONFIG,
    MODEL_CHOICE_SOURCE_VERIFIED,
)
MODEL_CHOICE_SOURCE_KIND_DEFAULT = MODEL_CHOICE_SOURCE_DECLARED

MODEL_CHOICE_ID_PREFIX = "rmc_"
MODEL_CHOICE_ALIAS_MAX_CHARS = 64

PROJECT_ROLE_ORIGIN_MANAGED = "managed"
PROJECT_ROLE_ORIGIN_IMPORTED = "imported"
PROJECT_ROLE_ORIGINS = (PROJECT_ROLE_ORIGIN_MANAGED, PROJECT_ROLE_ORIGIN_IMPORTED)

ROLE_NAME_MAX_CHARS = 64
OPERATION_KEY_MIN_CHARS = 8
OPERATION_KEY_MAX_CHARS = 128
ROLE_DESCRIPTION_FINGERPRINT_VERSION = 1
#: 存量角色补录请求指纹版本（ROLE_LEGACY_ATTACH_DESIGN §原子补录、幂等与来源）。
ROLE_LEGACY_ATTACH_PAYLOAD_VERSION = 1

PROJECT_ROLE_POLICY_SOURCE_MIGRATION = "migration_decision_tier"
PROJECT_ROLE_POLICY_SOURCE_HUMAN = "human_grant"
PROJECT_ROLE_POLICY_SOURCE_DEFAULT = "default"
PROJECT_ROLE_POLICY_SOURCES = (
    PROJECT_ROLE_POLICY_SOURCE_MIGRATION,
    PROJECT_ROLE_POLICY_SOURCE_HUMAN,
    PROJECT_ROLE_POLICY_SOURCE_DEFAULT,
)

# 一次性策略迁移标记（合同 §8.3）：写入 schema_migrations 后永不重跑，
# 因此重复 init_db() 不会覆盖 human 后来的人工改权。
ROLE_POLICY_MIGRATION_KEY = "r1_1_project_role_policy_backfill"

# choice_id 投影来源（合同 §5.2）：只信创建操作映射，不按 model_id 反查猜测。
CHOICE_SOURCE_CREATION_OPERATION = "creation_operation"
CHOICE_SOURCE_CREATION_OPERATION_MISMATCH = "creation_operation_mismatch"
CHOICE_SOURCE_LEGACY_MANUAL = "legacy_manual"
# 存量角色补录（ROLE_LEGACY_ATTACH_DESIGN §投影与宿主守卫）：独立补录映射与**当前绑定**
# 六维精确相等时给 ``legacy_attach``；映射存在但对不上（含与创建映射并存的双映射冲突）
# 时给 ``legacy_attach_mismatch`` 并把 ``choice_id`` 置空，**不**按 model_id 反查猜测。
CHOICE_SOURCE_LEGACY_ATTACH = "legacy_attach"
CHOICE_SOURCE_LEGACY_ATTACH_MISMATCH = "legacy_attach_mismatch"

# 角色身份投影（合同 §5.2）：managed / imported（有角色行）/ legacy（仅老名册）。
ROLE_IDENTITY_MANAGED = "managed"
ROLE_IDENTITY_IMPORTED = "imported"
ROLE_IDENTITY_LEGACY = "legacy"

IDENTITY_EXCLUSIVE_REFERENCE_REFUSED = "identity_exclusive_reference_refused"

# 角色生命周期 R1-2：跨宿主配置作业（`docs/spec/ROLE_PROVISION_CONTRACT.md` §1）。
# 作业只承接已有服务端身份的宿主三步（身份档 / Key 文件 / 启动前检查）；服务端**不保存、
# 不返回、不记录**任何 Key、凭据路径、绝对路径、argv 或原始异常文本。
PROVISION_STEP_PROFILE = "profile"
PROVISION_STEP_KEY_FILE = "key_file"
PROVISION_STEP_PREFLIGHT = "preflight"
PROVISION_STEP_ORDER = (
    PROVISION_STEP_PROFILE,
    PROVISION_STEP_KEY_FILE,
    PROVISION_STEP_PREFLIGHT,
)

PROVISION_STEP_STATE_PENDING = "pending"
PROVISION_STEP_STATE_SUCCEEDED = "succeeded"
PROVISION_STEP_STATE_FAILED = "failed"
PROVISION_STEP_STATE_SKIPPED = "skipped"
PROVISION_STEP_STATES = (
    PROVISION_STEP_STATE_PENDING,
    PROVISION_STEP_STATE_SUCCEEDED,
    PROVISION_STEP_STATE_FAILED,
    PROVISION_STEP_STATE_SKIPPED,
)

PROVISION_JOB_STATUS_PENDING = "pending"
PROVISION_JOB_STATUS_RUNNING = "running"
PROVISION_JOB_STATUS_SUCCEEDED = "succeeded"
PROVISION_JOB_STATUS_PARTIAL = "partial"
PROVISION_JOB_STATUS_FAILED = "failed"
PROVISION_JOB_STATUSES = (
    PROVISION_JOB_STATUS_PENDING,
    PROVISION_JOB_STATUS_RUNNING,
    PROVISION_JOB_STATUS_SUCCEEDED,
    PROVISION_JOB_STATUS_PARTIAL,
    PROVISION_JOB_STATUS_FAILED,
)

# ACK 只接受终态；`failed` 之外不允许携带 error_code；error_code 是 ≤64 的安全 token。
PROVISION_ACK_STATES = (
    PROVISION_STEP_STATE_SUCCEEDED,
    PROVISION_STEP_STATE_FAILED,
    PROVISION_STEP_STATE_SKIPPED,
)
PROVISION_ERROR_CODE_MAX_CHARS = 64

# 本作业登记的单角色档案路径：固定根 ``.talk/agents/<role_dir>/`` + 固定 basename。
# 只允许登记**仓库相对路径**；拒绝绝对路径/``..``/控制字符/混合目录（见
# ``normalize_provision_roster_paths``）。
PROVISION_ROSTER_PATH_ROOT = (".talk", "agents")
PROVISION_ROSTER_PATH_BASENAMES = {
    "identity_path": "IDENTITY.md",
    "soul_path": "SOUL.md",
    "user_path": "USER.md",
}

# ── 角色生命周期 R1-4a：请求驱动创建 / 恢复（REQUEST_CONTRACT §2–§9）──────
# 本段只声明数据事实与稳定错误码；全部判定与写事务在
# ``server.role_provision_requests`` 的共享守卫模块内实现，路由与既有
# ``projects`` 入口共用同一份规则，避免两套判定。

#: 请求种类：仅 create / recover。
ROLE_REQUEST_KIND_CREATE = "create"
ROLE_REQUEST_KIND_RECOVER = "recover"
ROLE_REQUEST_KINDS = (ROLE_REQUEST_KIND_CREATE, ROLE_REQUEST_KIND_RECOVER)

#: 请求状态机（合同 §2）：revision 每次有效变更 +1，attempts 每次领取 +1。
ROLE_REQUEST_STATUS_REQUESTED = "requested"
ROLE_REQUEST_STATUS_LEASED = "leased"
ROLE_REQUEST_STATUS_CREATED = "created"
ROLE_REQUEST_STATUS_PROVISIONED = "provisioned"
ROLE_REQUEST_STATUS_FAILED = "failed"
ROLE_REQUEST_STATUS_CANCELED = "canceled"
ROLE_REQUEST_STATUSES = (
    ROLE_REQUEST_STATUS_REQUESTED,
    ROLE_REQUEST_STATUS_LEASED,
    ROLE_REQUEST_STATUS_CREATED,
    ROLE_REQUEST_STATUS_PROVISIONED,
    ROLE_REQUEST_STATUS_FAILED,
    ROLE_REQUEST_STATUS_CANCELED,
)
#: 仍**占用**同角色名额的状态（部分唯一索引 + 跨 kind 占用检查）。
#: ``failed`` / ``canceled`` 的旧行永久保留但不再占用。
ROLE_REQUEST_ACTIVE_STATUSES = (
    ROLE_REQUEST_STATUS_REQUESTED,
    ROLE_REQUEST_STATUS_LEASED,
    ROLE_REQUEST_STATUS_CREATED,
)
#: worker 可通过 claim 发现的状态（合同 §4：覆盖 requested、失效 leased、失联 created）。
ROLE_REQUEST_CLAIMABLE_STATUSES = ROLE_REQUEST_ACTIVE_STATUSES
#: report 只接受这两个结果。
ROLE_REQUEST_REPORT_OUTCOMES = (
    ROLE_REQUEST_STATUS_PROVISIONED,
    ROLE_REQUEST_STATUS_FAILED,
)

#: 宿主项目配置预算（合同 §2）：未建配置行时 GET 返回 disabled/version0。
ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT = 900
ROLE_PROVISION_HOST_LEASE_SECONDS_MIN = 30
ROLE_PROVISION_HOST_LEASE_SECONDS_MAX = 1800
ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT = 2
ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MIN = 1
ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_MAX = 4
ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT = 3
ROLE_PROVISION_HOST_MAX_ATTEMPTS_MIN = 1
ROLE_PROVISION_HOST_MAX_ATTEMPTS_MAX = 10
ROLE_PROVISION_HOST_LABEL_MAX_CHARS = 64
ROLE_REQUEST_PAYLOAD_VERSION = 1
ROLE_REQUEST_LIST_LIMIT_DEFAULT = 50
ROLE_REQUEST_LIST_LIMIT_MAX = 200

# 稳定错误码白名单（合同 §3/§5/§6/§7/§9；错误响应与日志只落码，不落正文）。
ROLE_REQUEST_ERROR_NOT_FOUND = "role_request_not_found"
ROLE_REQUEST_ERROR_KEY_CONFLICT = "role_request_key_conflict"
ROLE_REQUEST_ERROR_KIND_INVALID = "role_request_kind_invalid"
ROLE_REQUEST_ERROR_PAYLOAD_INVALID = "role_request_payload_invalid"
ROLE_REQUEST_ERROR_CONFIRM_REQUIRED = "role_request_confirm_required"
ROLE_REQUEST_ERROR_ROLE_CONFLICT = "role_request_role_conflict"
ROLE_REQUEST_ERROR_PAYLOAD_MISMATCH = "role_provision_payload_mismatch"
ROLE_REQUEST_ERROR_OPERATION_CONFLICT = "operation_key_conflict"
ROLE_REQUEST_ERROR_OPERATION_MISMATCH = "role_request_operation_mismatch"
ROLE_REQUEST_ERROR_SOURCE_REQUIRED = "provision_lease_required"
ROLE_REQUEST_ERROR_LEASE_INVALID = "role_request_lease_invalid"
ROLE_REQUEST_ERROR_LEASE_SECONDS_INVALID = "role_request_lease_seconds_invalid"
ROLE_REQUEST_ERROR_LEASE_CONFLICT = "role_request_lease_conflict"
ROLE_REQUEST_ERROR_REVISION_CONFLICT = "role_request_revision_conflict"
ROLE_REQUEST_ERROR_STATUS_CONFLICT = "role_request_status_conflict"
ROLE_REQUEST_ERROR_RETRY_EXHAUSTED = "role_request_retry_exhausted"
ROLE_REQUEST_ERROR_NOT_RESUMABLE = "role_request_not_resumable"
ROLE_REQUEST_ERROR_CANCEL_REFUSED = "role_request_cancel_refused"
ROLE_REQUEST_ERROR_MEMBER_CREATED = "member_created"
ROLE_REQUEST_ERROR_CHOICE_UNAVAILABLE = "role_request_choice_unavailable"
ROLE_REQUEST_ERROR_BINDING_MISMATCH = "role_request_binding_mismatch"
ROLE_REQUEST_ERROR_CREDENTIAL_MISMATCH = "role_request_credential_mismatch"
ROLE_REQUEST_ERROR_CREDENTIAL_STALE = "role_request_credential_stale"
ROLE_REQUEST_ERROR_COMPLETION_INCOMPLETE = "role_request_completion_incomplete"
ROLE_REQUEST_ERROR_STALE_REPORT = "role_request_stale_report"
ROLE_REQUEST_ERROR_MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"
ROLE_REQUEST_ERROR_SUPERSEDED = "superseded"
ROLE_REQUEST_ERROR_HOST_MISMATCH = "role_request_host_mismatch"
ROLE_PROVISION_HOST_ERROR_DISABLED = "provision_host_disabled"
ROLE_PROVISION_HOST_ERROR_VERSION_CONFLICT = "provision_host_version_conflict"
ROLE_PROVISION_HOST_ERROR_BUSY = "provision_host_busy"
ROLE_PROVISION_HOST_ERROR_CONFIG_INVALID = "provision_host_config_invalid"
# R1-4c-a 自动首次启动的四个稳定码（AUTO_START_DESIGN §6.3）：只落码、不落异常
# 正文。原配置 disabled / 来源无效等上游拒绝仍走 ``provision_host_disabled`` 等
# 既有码，不绕过。
ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED = (
    "auto_start_control_kind_not_managed"
)
ROLE_REQUEST_ERROR_AUTO_START_CONFIG_DISABLED = "auto_start_config_disabled"
ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT = (
    "auto_start_manual_intent_present"
)
ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED = "auto_start_enqueue_failed"

# ── 角色生命周期 R1-4c-a：配置成功后自动首次启动（AUTO_START_DESIGN）────────

#: 自动启动动作的审计身份：经原请求 ``created_by`` / 意图 / launch 锚点追源到
#: 发起的人类，**不**冒充 human，也不创建任何新成员或权限入口。
ROLE_AUTO_START_ACTOR = "system:auto-start"

#: 自动启动意图状态机（AUTO_START_DESIGN §2/§6.2）。``NULL`` = 无意图（旧请求 /
#: 旧客户端 / recover）；``pending`` 只是尚未处理；``enqueued`` 只是已投递事实，
#: **都不等于服务 ready**；``not_eligible`` 如实未入队；``failed`` 入队内部故障。
ROLE_AUTO_START_STATUS_PENDING = "pending"
ROLE_AUTO_START_STATUS_ENQUEUED = "enqueued"
ROLE_AUTO_START_STATUS_NOT_ELIGIBLE = "not_eligible"
ROLE_AUTO_START_STATUS_FAILED = "failed"
ROLE_AUTO_START_STATUSES = (
    ROLE_AUTO_START_STATUS_PENDING,
    ROLE_AUTO_START_STATUS_ENQUEUED,
    ROLE_AUTO_START_STATUS_NOT_ELIGIBLE,
    ROLE_AUTO_START_STATUS_FAILED,
)

#: A6 ``report`` 与**请求驱动** C4 ``ACK`` 允许落库的稳定宿主错误码白名单
#: （REQUEST_CONTRACT §2/§3/§8）：``last_error_code`` 与作业步骤 ``error_code`` 只接受
#: 下表列出的有限稳定码；未知串（含误传假凭据/token/路径片段）一律 422 且零写入，
#: **不**做“任意安全字符串”泛化接受，也不靠删错误信息规避泄漏。新增宿主码必须先按
#: 合同登记到本白名单。前段是请求/恢复语义码，中段是 ``scripts/role_provision.py``
#: 已发布的宿主稳定码，末段是既有三步作业契约已使用的步骤码。
ROLE_REQUEST_HOST_ERROR_CODES = frozenset(
    {
        ROLE_REQUEST_ERROR_MANUAL_RECOVERY_REQUIRED,
        "profile_write_failed",
        "key_file_write_failed",
        "key_write_failed",
        "key_permissions_failed",
        "preflight_failed",
        "native_login_unverified",
        "step_probe_failed",
        "role_key_unknown",
        "role_key_stale",
        "identity_mismatch",
        "provision_lock_busy",
        "path_escape_refused",
        "symlink_refused",
        "key_root_inside_repo",
        "profile_root_invalid",
        "operator_key_missing",
        "ack_failed",
        "ack_stale",
        "resume_required",
        "http_error",
        "not_apply_mode",
        "cli_executable_missing",
        # R1-4b 宿主 worker 有限新增码：只表示“拒绝覆盖非本人已知旧代文件”与
        # “Key 已发布但不含 Key 的来源元数据写入失败（不回滚 Key）”。
        "role_key_foreign_refused",
        "key_provenance_write_failed",
        # R1-4b 返修 F2：单轮 IO 预算在副作用/ACK/report 边界前耗尽时的精确宿主码。
        # 合同 §8 要求新增宿主码必须登记进本集合，否则 report/ACK 会 422 并丢失错误形状；
        # 本码与 ``scripts/role_provision_worker.WORKER_ERROR_CODES`` 保持一一对应。
        "worker_io_budget_exceeded",
        # R1-4c-a 自动首次启动分类码（AUTO_START_DESIGN §6.3）：由服务端在
        # report(provisioned) 的成功分支登记进请求行 ``auto_start_error_code``，
        # 只落稳定码、不落异常正文。
        ROLE_REQUEST_ERROR_AUTO_START_CONTROL_KIND_NOT_MANAGED,
        ROLE_REQUEST_ERROR_AUTO_START_CONFIG_DISABLED,
        ROLE_REQUEST_ERROR_AUTO_START_MANUAL_INTENT_PRESENT,
        ROLE_REQUEST_ERROR_AUTO_START_ENQUEUE_FAILED,
    }
)

# 绑定有效性阶梯（合同 §4.4，先命中先返回）。``no_project`` 只属于任务快照。
ROLE_BINDING_NO_PROJECT = "no_project"
ROLE_BINDING_MEMBER_MISSING = "member_missing"
ROLE_BINDING_MEMBER_DISABLED = "member_disabled"
ROLE_BINDING_NOT_IN_ROSTER = "not_in_roster"
ROLE_BINDING_NOT_AGENT = "not_agent"
ROLE_BINDING_UNCONFIGURED = "unconfigured"
ROLE_BINDING_PARTIAL = "partial"
ROLE_BINDING_RUNNER_MISSING = "runner_missing"
ROLE_BINDING_RUNNER_RETIRED = "runner_retired"
ROLE_BINDING_BOUND = "bound"
ROLE_BINDING_STATES = (
    ROLE_BINDING_NO_PROJECT,
    ROLE_BINDING_MEMBER_MISSING,
    ROLE_BINDING_MEMBER_DISABLED,
    ROLE_BINDING_NOT_IN_ROSTER,
    ROLE_BINDING_NOT_AGENT,
    ROLE_BINDING_UNCONFIGURED,
    ROLE_BINDING_PARTIAL,
    ROLE_BINDING_RUNNER_MISSING,
    ROLE_BINDING_RUNNER_RETIRED,
    ROLE_BINDING_BOUND,
)

# 任务绑定快照（B1b，合同 §7.1）：schema 版本与固定 13 键。
# 键顺序与合同 §7.1 / 样例 ``snapshot_schema.keys`` 逐项一致；**不含** read_receipt，
# 也不含任何“读取回执/语句计数/版本哈希”字段（合同 §7.1、R3/D8）。
ROLE_BINDING_SNAPSHOT_SCHEMA_VERSION = "role-binding-snapshot-1"
TARGET_BINDING_SNAPSHOT_KEYS = (
    "schema_version",
    "snapshot_at",
    "state",
    "runner_id",
    "runtime",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
    "model_display_name",
    "binding_fingerprint",
    "note",
)

# 定量规则（合同 §3.1、§3.3、§4.2）。
# 只用 ``\Z`` 而不是 ``$`` 收尾：``$`` 允许在末尾换行符**之前**匹配（R3 定向修正），
# 会让 ``model:test\n`` 之类的存储值被误判为合法；写入侧仍先 ``strip()`` 归一化合法输入。
RUNNER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:\-]{0,63}\Z")
RUNNER_RUNTIME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._\-]{0,31}\Z")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._:/@\-]+\Z")
# 有限启发式（合同 §5.4）：只挡常见形态，不承诺识别任意真实 Key；看到“不疑似”不等于已证明安全。
CREDENTIAL_LIKE_PATTERN = re.compile(r"[A-Za-z0-9+/=_\-]{40,}")
CREDENTIAL_URL_PATTERN = re.compile(r"://[^/\s]*:[^/\s]*@")
RUNNER_DISPLAY_NAME_MAX_CHARS = 64
RUNNER_ADAPTER_NOTE_MAX_CHARS = 500
RUNNER_CAPABILITIES_MAX_ITEMS = 32
RUNNER_CAPABILITY_MAX_CHARS = 64
SAFE_TOKEN_MAX_CHARS = 128
MODEL_DISPLAY_NAME_MAX_CHARS = 64


class RunnerRegistry(SQLModel, table=True):
    """全局运行器登记事实（B1a，合同 §3.1）。

    - ``runner_id`` 是人工指定的稳定 slug，``runtime`` 是运行器族标识；两者登记后
      **不可改**（PATCH 只允许 display_name / adapter_status / adapter_note /
      capabilities），避免已冻结的配置快照与登记事实分叉；
    - ``adapter_status`` 只描述接入程度，**不代表在线、可用或已获授权**；
    - ``capabilities`` 只描述登记事实，不参与任何权限、路由或执行判定；
    - 不读取、不搬运、不校验任何凭据正文；登记不自动加入项目，也不启动任何进程。
    """

    __tablename__ = "runner_registry"

    runner_id: str = Field(primary_key=True)
    runtime: str = Field(index=True)
    display_name: str
    adapter_status: str = Field(default=RUNNER_ADAPTER_STATUS_DEFAULT, index=True)
    adapter_note: Optional[str] = None
    capabilities: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    # 控制能力分类（角色生命周期 R1-1，合同 §12）：managed_cli / external_session /
    # unknown。只声明“谁可能启动/停止它”，**不**代表已核验、在线或允许启动；
    # 旧行一律 'unknown'（页面不提供启动按钮）。独立入口 PATCH .../control-kind 写入，
    # 避免与既有 PATCH /api/runners/{id} 的四字段白名单冲突。
    control_kind: str = Field(default=RUNNER_CONTROL_UNKNOWN, index=True)
    # 登记人 member_id：刻意不加外键，沿用 project_agents.member_id 先例。
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRoleBinding(SQLModel, table=True):
    """项目角色 → 运行器/模型绑定行（B1a，合同 §4.1）。

    - 主键 ``(project_id, member_id)``；**独立于 ``project_agents``**，因为项目名册
      ``POST /sync`` 是全量替换（先删后插），挂在那张表上的人工配置会被抹掉；
    - ``member_id`` 刻意不加外键：成员离册/被删后行保留，读取时按 §4.4 阶梯如实报告
      ``not_in_roster`` / ``member_missing``，**不自动删除、不猜默认模型**；
    - ``model_alias`` 是原生运行器的**调用选择参数**（不是展示字段，也不是 ``model_id``）；
      ``model_display_name`` 才是纯展示字段；两者都不参与六维内容指纹；
    - 五个存储必填字段（``runner_id`` / ``model_source`` / ``provider_id`` /
      ``connection_ref`` / ``model_id``）在**存储层可空**：写入 API 一律要求非空（§4.2），
      但旧库/手工行可能缺失或留下非法值，读取时按 §4.5 如实报 ``partial``，而不是
      让整次读取 500。唯一允许为 NULL 的语义就是“这一行内容不完整”。
    """

    __tablename__ = "project_role_bindings"

    project_id: str = Field(foreign_key="projects.project_id", primary_key=True)
    member_id: str = Field(primary_key=True)
    runner_id: Optional[str] = Field(default=None, index=True)
    model_source: Optional[str] = None
    provider_id: Optional[str] = None
    connection_ref: Optional[str] = None
    model_id: Optional[str] = None
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None
    updated_by: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunnerModelChoice(SQLModel, table=True):
    """已适配运行器的模型选择目录（角色生命周期 R1-1，合同 §4.1.1）。

    - ``choice_id`` 是服务端生成的稳定不透明 ID（``rmc_<12hex>``），创建后**永不**重新
      指向另一组选择维度，也不复用；
    - 唯一键覆盖**选择维度** ``(runner_id, model_id, model_source, provider_id,
      connection_ref, model_alias)``：同运行器同 ``model_id`` 的不同 provider/connection/
      alias 可并存（这正是 B1a 六维事实的维度）；
    - ``model_alias`` 属于选择维度（调用选择参数），``model_display_name`` / ``source_kind``
      / ``capabilities`` / ``retired_at`` 只描述展示与来源，可改；
    - ``retired_at`` 是**软下架**：只影响新选择，不回写历史绑定；
    - ``runner_id`` 不加外键级联：运行器退役时选择行保留，读取阶梯如实报告。
    """

    __tablename__ = "runner_model_choices"
    __table_args__ = (
        Index(
            "ux_runner_model_choices_dim",
            "runner_id",
            "model_id",
            "model_source",
            "provider_id",
            "connection_ref",
            "model_alias",
            unique=True,
        ),
        Index("ix_runner_model_choices_runner", "runner_id", "retired_at"),
    )

    choice_id: str = Field(primary_key=True)
    runner_id: str
    model_id: str
    model_source: str
    provider_id: str
    connection_ref: str
    model_alias: str = Field(default="")
    model_display_name: Optional[str] = None
    source_kind: str = Field(default=MODEL_CHOICE_SOURCE_KIND_DEFAULT)
    capabilities: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    retired_at: Optional[datetime] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRole(SQLModel, table=True):
    """项目角色身份与生命周期归属（角色生命周期 R1-1，合同 §4.1.2）。

    - 只存“人工角色名 + 生命周期归属 + 凭据版本”：运行器/模型事实的唯一来源仍是
      ``project_role_bindings``，本表刻意不重复存 ``runner_id``/``model_id``；
    - ``role_name`` 仅在**未归档**时项目内唯一（部分唯一索引 ``ux_project_roles_active_name``），
      归档后同名可重建且必然获得新 ``member_id``；
    - ``identity_exclusive`` 是创建时记录的持久标记（创建时该 member 全局仅此一条未归档
      角色行），一旦为 1 即受独占引用守卫保护；
    - ``archived_at`` 是软归档：保留历史归属，不物理删除成员/任务/消息；
    - 本表**没有** ``status`` 列：行存在即事实存在。
    """

    __tablename__ = "project_roles"
    __table_args__ = (
        Index(
            "ux_project_roles_active_name",
            "project_id",
            "role_name",
            unique=True,
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True, index=True)
    role_name: str
    origin: str = Field(default=PROJECT_ROLE_ORIGIN_MANAGED)
    identity_exclusive: int = Field(default=0)
    credential_version: int = Field(default=1)
    key_issued_at: Optional[datetime] = None
    key_rotated_at: Optional[datetime] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: Optional[datetime] = None


class RoleCreationOperation(SQLModel, table=True):
    """创建幂等与身份分配（角色生命周期 R1-1，合同 §4.1.3 / §7.2）。

    - ``operation_key`` 由调用方显式提供（禁止由名称/模型派生），是本表的唯一幂等键；
    - **没有** ``status``/``error_code`` 列：行 = 已提交操作，失败 = 没有行，
      因此不存在任何需要人肉回收的 ``pending``/``failed`` 残行；
    - 行与全部身份事实在**同一个** ``BEGIN IMMEDIATE`` 事务（TX-ALL）内写入；
    - ``UNIQUE(project_id, member_id)`` 供 ``GET roles`` 的 ``choice_id`` 反查使用。
    """

    __tablename__ = "role_creation_operations"
    __table_args__ = (
        Index(
            "ux_role_creation_operations_identity",
            "project_id",
            "member_id",
            unique=True,
        ),
    )

    operation_key: str = Field(primary_key=True)
    request_fingerprint: str
    project_id: str = Field(index=True)
    requested_role_name: str
    runner_id: str
    choice_id: str
    member_id: str = Field(index=True)
    committed_at: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleLegacyAttachOperation(SQLModel, table=True):
    """存量角色补录幂等与来源审计（ROLE_LEGACY_ATTACH_DESIGN §原子补录、幂等与来源）。

    - 与 ``RoleCreationOperation`` **完全独立**：补录沿用已有身份，不能伪造“创建了新身份”
      的事实，因此不写入、也不复用 ``role_creation_operations``；
    - ``operation_key`` 由调用方显式提供，是本表的唯一幂等键；
    - **没有** ``status``/``error_code`` 列：行 = 已提交补录，失败 = 没有行；
    - 行与 ``project_roles`` / 缺失时的精确绑定在**同一个** ``BEGIN IMMEDIATE`` 事务内写入；
    - ``UNIQUE(project_id, member_id)`` 供 ``GET roles`` 的 ``choice_id`` 反查使用；
    - 只存公开审计元数据：**不含** Key、凭据、路径、argv 或请求原文。
    """

    __tablename__ = "role_legacy_attach_operations"
    __table_args__ = (
        Index(
            "ux_role_legacy_attach_operations_identity",
            "project_id",
            "member_id",
            unique=True,
        ),
    )

    operation_key: str = Field(primary_key=True)
    request_fingerprint: str
    project_id: str = Field(index=True)
    member_id: str = Field(index=True)
    runner_id: str
    choice_id: str
    derived_role_name: str
    committed_at: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRolePolicy(SQLModel, table=True):
    """独立于固定分级的权限持久源（角色生命周期 R1-1，合同 §4.1.4 / §8）。

    - ``review_exempt`` ⇔ 原 ``decision_tier='decision'`` 的“可豁免复核”行为，不新增权限；
    - 独立于 ``project_agents``：名册 sync 是全量替换，挂在那张表上的字段会被抹掉；
    - 行是“曾获得/被授予的豁免事实”，离册/归档后**保留**（“离册保留、回册恢复”），
      但“当前是否可用”由读路径按当前名册/角色状态现算（保留事实 ≠ 当前权限）。
    """

    __tablename__ = "project_role_policies"

    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True)
    review_exempt: int = Field(default=0)
    source: str = Field(default=PROJECT_ROLE_POLICY_SOURCE_DEFAULT)
    granted_by: Optional[str] = None
    granted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SchemaMigration(SQLModel, table=True):
    """一次性迁移标记（角色生命周期 R1-1，合同 §8.3）。

    ``key`` 存在即代表该迁移已执行；因此重复 ``init_db()`` 不会重跑回填、
    也不会覆盖 human 后续的人工改权。
    """

    __tablename__ = "schema_migrations"

    key: str = Field(primary_key=True)
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectRoleStartup(SQLModel, table=True):
    """Explicit next-project-load preference; never inferred from last running state."""
    __tablename__ = "project_role_startup"
    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True)
    enabled: bool = False
    revision: int = 1
    updated_by: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectStartupCycle(SQLModel, table=True):
    """Seals one runtime generation's roster, including an empty project."""
    __tablename__ = "project_startup_cycles"
    project_id: str = Field(primary_key=True)
    activation_id: str = Field(primary_key=True)
    runtime_pid: int
    runtime_started_at: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleStartupActivation(SQLModel, table=True):
    """One attempt per role/runtime; audit is separate from service readiness."""
    __tablename__ = "role_startup_activations"
    __table_args__ = (Index("ix_role_startup_latest", "project_id", "member_id", "created_at"),)
    project_id: str = Field(primary_key=True)
    activation_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True)
    enabled: bool
    preference_revision: int
    expected_generation: int
    status: str = "pending"
    lease_hash: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    launch_id: Optional[str] = None
    recovery_id: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleStartupPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class ProjectStartupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activation_id: str = PydField(pattern=r"^[a-f0-9]{32}$")


class RoleDeletion(SQLModel, table=True):
    """Minimal tombstone cleanup state; no plaintext credentials or local paths."""
    __tablename__ = "role_deletions"
    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True)
    status: str = "pending"
    revision: int = 1
    revoke_identity: bool = False
    credential_digest: Optional[str] = None
    lease_hash: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    steps: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error_code: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleProvisionJob(SQLModel, table=True):
    """跨宿主配置作业（角色生命周期 R1-2，PROVISION_CONTRACT §1）。

    - ``operation_key`` 直接复用 R1-1 ``role_creation_operations.operation_key``
      作为**唯一**恢复锚点，因此同时是本表主键；
    - 只记录宿主三步 ``profile`` / ``key_file`` / ``preflight`` 的状态机事实；
    - 本表**不存** Key、凭据路径、绝对路径、argv 或原始异常文本；
    - ``revision`` 是 ACK 的 CAS 版本：每次状态变更 +1，迟到/旧尝试回报一律拒绝；
    - ``credential_version`` 是**本次作业代际**绑定的角色凭据版本快照（R1-2 补正 F1）：
      创建/续跑时从 ``project_roles.credential_version`` 取当前值写入；ACK 必须同时命中
      快照与角色当前值，因此凭据轮换后旧成功证明立即失效。轮换本身不改作业行，
      续跑时若发现版本已变，服务端强制重置 ``key_file``/``preflight`` 两个凭据相关步骤；
    - 行本身的创建/续跑只写本表，**不**重建 ``Member``/``ProjectRole``、不重发 Key、
      不改绑定/说明/权限策略/名册（合同 §0）。
    """

    __tablename__ = "role_provision_jobs"
    __table_args__ = (
        Index("ix_role_provision_jobs_project", "project_id", "member_id"),
        Index("ix_role_provision_jobs_status", "status"),
    )

    operation_key: str = Field(primary_key=True)
    project_id: str
    member_id: str
    status: str = Field(default=PROVISION_JOB_STATUS_PENDING)
    steps: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    resume_of: Optional[str] = None
    revision: int = Field(default=1)
    credential_version: int = Field(default=1)
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleProvisionRequestRow(SQLModel, table=True):
    """人类创建 / 恢复**意图**（角色生命周期 R1-4a，REQUEST_CONTRACT §2）。

    命名刻意带 ``Row`` 后缀：既有 ``RoleProvisionRequest`` 是
    ``POST .../roles/{member_id}/provision`` 的**请求体 schema**，两者语义完全不同，
    不能同名。

    本表**只保存意图与租约事实**，永久保留（``failed``/``canceled`` 行不物理删除）：

    - ``request_key`` 是全局主键，沿既有 8–128 安全 operation token；``kind=create``
      时按合同 §2 等于原创建 ``operation_key``（该 ``RoleCreationOperation`` 由 create
      意图驱动、与意图同事务提交），``kind=recover`` 使用全新键；
    - ``payload`` 是**规范化后**的意图载荷（create 四字段 / recover 成员 + 期望版本），
      ``request_fingerprint`` 复用既有创建指纹或恢复指纹，用于“同键同载荷幂等、异载荷 409”；
    - ``choice_snapshot`` 是 create 提交时冻结的六维绑定快照（含内容指纹），首次创建必须
      与当前选择逐维一致；recover 为 ``None``（其预期绑定来自原创建操作）；
    - ``origin_operation_key`` 在 create 成功时同事务回填，recover 在提交时从实际原创建
      操作解析，**不能**由调用者任意指定；
    - 租约只存 ``SHA256`` 哈希：``lease_token_hash`` / ``lease_generation`` /
      ``lease_config_version`` / ``lease_host`` / 时间窗；明文 token 只在 claim 响应出现
      一次；``disable`` 后再 ``enable`` 换代即旧 token 永久失去写资格；
    - ``report_outcome`` / ``report_revision`` / ``report_credential_version`` 保存
      **本次终态提交**的精确事实，用于区分“同一次提交的只读重放”与“异结果/旧代覆盖”；
    - 本表**不存** Key、凭据路径、绝对路径、argv 或异常正文；``last_error_code`` 只落
      稳定白名单错误码。
    """

    __tablename__ = "role_provision_requests"
    __table_args__ = (
        Index("ix_role_provision_requests_project_status", "project_id", "status"),
        Index(
            "ix_role_provision_requests_project_origin",
            "project_id",
            "origin_operation_key",
        ),
        Index(
            "ix_role_provision_requests_project_member", "project_id", "member_id"
        ),
        # 活动同名 create：项目内同一角色名同时只能有一个未终结的创建意图。
        Index(
            "ux_role_provision_requests_active_create_name",
            "project_id",
            "role_name",
            unique=True,
            sqlite_where=text(
                "kind = 'create' AND status IN ('requested','leased','created')"
            ),
        ),
        # 活动同成员 recover：同一成员同时只能有一个未终结的恢复意图。
        Index(
            "ux_role_provision_requests_active_recover_member",
            "project_id",
            "member_id",
            unique=True,
            sqlite_where=text(
                "kind = 'recover' AND status IN ('requested','leased','created')"
            ),
        ),
        # R1-4c-a：自动启动锚点的普通索引（非唯一；幂等锚点语义由业务守卫保证）。
        Index(
            "ix_role_provision_requests_auto_start_launch",
            "auto_start_launch_id",
        ),
    )

    request_key: str = Field(primary_key=True)
    project_id: str
    kind: str
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    request_fingerprint: str
    choice_snapshot: Optional[dict] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    #: create 意图提交时的规范化角色名（活动同名部分唯一索引 + 占用检查用）；recover 为 NULL。
    role_name: Optional[str] = None
    #: create 成功同事务回填；recover 提交时保存目标成员。
    member_id: Optional[str] = None
    origin_operation_key: Optional[str] = None
    expected_credential_version: Optional[int] = None
    status: str = Field(default=ROLE_REQUEST_STATUS_REQUESTED)
    revision: int = Field(default=1)
    attempts: int = Field(default=0)
    lease_generation: int = Field(default=0)
    lease_token_hash: Optional[str] = None
    lease_host: Optional[str] = None
    lease_claimed_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    lease_config_version: Optional[int] = None
    report_outcome: Optional[str] = None
    report_revision: Optional[int] = None
    report_credential_version: Optional[int] = None
    last_error_code: Optional[str] = None
    #: R1-4c-a（AUTO_START_DESIGN §2）：人类创建意图是否含“配置成功后自动启动一次”
    #: 的规范布尔值。独立落列、**不进**共享创建指纹；旧行默认 0（不追溯）。同
    #: ``request_key`` 重放时参与严格比较，异值 409 ``role_request_key_conflict``。
    auto_start_intent: int = Field(default=0)
    #: 意图状态（``ROLE_AUTO_START_STATUS_*``）：配置 failed/canceled 绝不产生
    #: launch，也绝不后台重试；``pending``/``enqueued`` 都不能当服务 ready 展示。
    auto_start_status: Optional[str] = None
    #: 本意图唯一投递出的 start 动作锚点；非空 = 已投递（幂等锚点：重复/迟到回报、
    #: 页面刷新、worker 重试都**不**据此产生第二次启动）。
    auto_start_launch_id: Optional[str] = None
    #: 稳定白名单分类码（``ROLE_REQUEST_ERROR_AUTO_START_*``），不落异常正文。
    auto_start_error_code: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None


class RoleProvisionHostConfig(SQLModel, table=True):
    """项目级宿主在线配置（角色生命周期 R1-4a，REQUEST_CONTRACT §2/§3）。

    - 主键 ``project_id``；**未建行 = 未启用**，GET 返回 ``enabled=false`` /
      ``config_version=0``（不伪造配置行）；
    - 默认关闭（``enabled=0``）：没有真实部署/启用授权，测试必须显式走 enable CAS；
    - ``lease_seconds`` / ``max_active_leases`` / ``max_attempts`` 是项目预算，
      enable 与 claim 都按范围校验（30–1800 / 1–4 / 1–10）；
    - ``config_version`` 初始 0，每次 enable/disable 由 CAS 成功 +1：租约记录领取时的
      ``lease_config_version``，换代后旧租约立即失去写资格，再 enable 也不复活旧 token；
    - 本表不含任何凭据、路径或 argv。
    """

    __tablename__ = "role_provision_host_config"

    project_id: str = Field(primary_key=True)
    enabled: int = Field(default=0)
    host_label: Optional[str] = None
    lease_seconds: int = Field(default=ROLE_PROVISION_HOST_LEASE_SECONDS_DEFAULT)
    max_active_leases: int = Field(
        default=ROLE_PROVISION_HOST_MAX_ACTIVE_LEASES_DEFAULT
    )
    max_attempts: int = Field(default=ROLE_PROVISION_HOST_MAX_ATTEMPTS_DEFAULT)
    config_version: int = Field(default=0)
    updated_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleCredentialRotation(SQLModel, table=True):
    """一次恢复意图的**凭据轮换执行事实**（角色生命周期 R1-4a，REQUEST_CONTRACT §2/§7）。

    - 主键 ``intent_key`` = 该 recover 请求的 ``request_key``：同一个恢复意图最多执行
      一次轮换，唯一性由主键保证，重放先查本表而不是先比对当前版本；
    - 只保存 ``before``/``after`` 版本号与操作者/时间，**不保存也不重放任何 Key**；
    - 普通 failed resume 不删除本行，也不自动生成第二次轮换；再次轮换必须由人类新的
      恢复意图（新 ``intent_key``）驱动。
    """

    __tablename__ = "role_credential_rotations"
    __table_args__ = (
        Index("ix_role_credential_rotations_member", "project_id", "member_id"),
    )

    intent_key: str = Field(primary_key=True)
    project_id: str
    member_id: str
    before_credential_version: int
    after_credential_version: int
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# 请求体 schema（全部 ``extra="forbid"``；字段值的归一化与稳定错误码由共享守卫模块决定）。
class RoleProvisionHostEnableRequest(BaseModel):
    """``POST /role-provision-host/enable``（合同 §3）：CAS 启用 + 预算。"""

    model_config = ConfigDict(extra="forbid")

    host_label: str
    expected_version: int
    lease_seconds: Optional[int] = None
    max_active_leases: Optional[int] = None
    max_attempts: Optional[int] = None


class RoleProvisionHostDisableRequest(BaseModel):
    """``POST /role-provision-host/disable``（合同 §3）：CAS 关闭。"""

    model_config = ConfigDict(extra="forbid")

    expected_version: int


class RoleRequestCreate(BaseModel):
    """``POST /role-requests``（合同 §3）：创建 / 恢复意图。

    ``kind`` 互斥载荷由共享规则验证：``create`` 必须且只能给四字段（外加可选
    ``auto_start``），``recover`` 必须且只能给 ``member_id`` +
    ``expected_credential_version``（携带 ``auto_start`` 非 None 同样 422）。
    ``confirm`` 必须显式为 ``true``（human 明确意图），否则 422。
    """

    model_config = ConfigDict(extra="forbid")

    request_key: str
    kind: str
    confirm: bool = False
    role_name: Optional[str] = None
    runner_id: Optional[str] = None
    choice_id: Optional[str] = None
    role_description: Optional[str] = None
    member_id: Optional[str] = None
    expected_credential_version: Optional[int] = None
    #: R1-4c-a（AUTO_START_DESIGN §2）：可选自动首次启动意图；缺省/None/false 规范为
    #: false（旧请求/旧客户端兼容，不自动启动）。recover 携带非 None 值按互斥载荷
    #: 422 ``role_request_payload_invalid``（恢复本身不自动启动）。
    auto_start: Optional[bool] = None


class RoleRequestClaimRequest(BaseModel):
    """``POST /role-requests/{request_key}/claim``（合同 §3/§5）。"""

    model_config = ConfigDict(extra="forbid")

    host: str
    expected_revision: int
    lease_seconds: Optional[int] = None


class RoleRequestReportRequest(BaseModel):
    """``POST /role-requests/{request_key}/report``（合同 §3/§8）。

    刻意不接受 ``member_id`` / Key / 路径 / argv：成员身份由服务端从请求事实取。
    """

    model_config = ConfigDict(extra="forbid")

    lease_token: str
    expected_revision: int
    outcome: str
    error_code: Optional[str] = None


class RoleRequestRevisionRequest(BaseModel):
    """``cancel`` / ``resume`` 共用的 CAS 请求体（合同 §3/§9）。"""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    confirm: bool = False


# ── 角色生命周期 R1-3：受管 CLI 服务启停（合同 §4.1.5 / §4.1.6 / §10）──────

# 人工意图（只有 human 能写）。
ROLE_SERVICE_DESIRED_STOPPED = "stopped"
ROLE_SERVICE_DESIRED_RUNNING = "running"
ROLE_SERVICE_DESIRED_STATES = (
    ROLE_SERVICE_DESIRED_STOPPED,
    ROLE_SERVICE_DESIRED_RUNNING,
)

# 宿主证据收敛后的受管状态（页面文案见设计 §11.2）。
ROLE_SERVICE_OBSERVED_NOT_STARTED = "not_started"
ROLE_SERVICE_OBSERVED_STARTING = "starting"
ROLE_SERVICE_OBSERVED_RUNNING = "running"
ROLE_SERVICE_OBSERVED_STOPPING = "stopping"
ROLE_SERVICE_OBSERVED_STOPPED = "stopped"
ROLE_SERVICE_OBSERVED_FAILED = "failed"
ROLE_SERVICE_OBSERVED_UNKNOWN = "unknown"
ROLE_SERVICE_OBSERVED_STATES = (
    ROLE_SERVICE_OBSERVED_NOT_STARTED,
    ROLE_SERVICE_OBSERVED_STARTING,
    ROLE_SERVICE_OBSERVED_RUNNING,
    ROLE_SERVICE_OBSERVED_STOPPING,
    ROLE_SERVICE_OBSERVED_STOPPED,
    ROLE_SERVICE_OBSERVED_FAILED,
    ROLE_SERVICE_OBSERVED_UNKNOWN,
)

# 本次由谁管理（合同 §4.1.5 的 manager_kind）。
ROLE_SERVICE_MANAGER_CLI_PROCESS = "cli_process"
ROLE_SERVICE_MANAGER_EXTERNAL_SESSION = "external_session"
ROLE_SERVICE_MANAGER_HOST_DESKTOP = "host_desktop"
ROLE_SERVICE_MANAGER_KINDS = (
    ROLE_SERVICE_MANAGER_CLI_PROCESS,
    ROLE_SERVICE_MANAGER_EXTERNAL_SESSION,
    ROLE_SERVICE_MANAGER_HOST_DESKTOP,
)

# 动作与动作状态机（合同 §4.1.6）。
ROLE_SERVICE_ACTION_START = "start"
ROLE_SERVICE_ACTION_STOP = "stop"
ROLE_SERVICE_ACTIONS = (ROLE_SERVICE_ACTION_START, ROLE_SERVICE_ACTION_STOP)

ROLE_SERVICE_LAUNCH_PENDING = "pending"
ROLE_SERVICE_LAUNCH_CLAIMED = "claimed"
ROLE_SERVICE_LAUNCH_REPORTED = "reported"
ROLE_SERVICE_LAUNCH_EXPIRED = "expired"
ROLE_SERVICE_LAUNCH_STATES = (
    ROLE_SERVICE_LAUNCH_PENDING,
    ROLE_SERVICE_LAUNCH_CLAIMED,
    ROLE_SERVICE_LAUNCH_REPORTED,
    ROLE_SERVICE_LAUNCH_EXPIRED,
)

# 回报 outcome：start 只收 ready/failed，stop 只收 stopped/failed（合同 §10.2）。
ROLE_SERVICE_OUTCOME_READY = "ready"
ROLE_SERVICE_OUTCOME_FAILED = "failed"
ROLE_SERVICE_OUTCOME_STOPPED = "stopped"
ROLE_SERVICE_START_OUTCOMES = (ROLE_SERVICE_OUTCOME_READY, ROLE_SERVICE_OUTCOME_FAILED)
ROLE_SERVICE_STOP_OUTCOMES = (ROLE_SERVICE_OUTCOME_STOPPED, ROLE_SERVICE_OUTCOME_FAILED)

# last_result：人工关闭记 ``stopped``，**不是** ``failed``（合同 §4.1.5）。
ROLE_SERVICE_RESULT_SUCCESS = "success"
ROLE_SERVICE_RESULT_FAILED = "failed"
ROLE_SERVICE_RESULT_STOPPED = "stopped"
ROLE_SERVICE_RESULTS = (
    ROLE_SERVICE_RESULT_SUCCESS,
    ROLE_SERVICE_RESULT_FAILED,
    ROLE_SERVICE_RESULT_STOPPED,
)

# 三独立就绪事实（合同 §10.3）：native_login / model_alias / readiness.service。
ROLE_SERVICE_NATIVE_LOGIN_UNVERIFIED = "unverified"
ROLE_SERVICE_NATIVE_LOGIN_VERIFIED = "verified"
ROLE_SERVICE_NATIVE_LOGIN_NOT_APPLICABLE = "not_applicable"
ROLE_SERVICE_MODEL_ALIAS_RESOLVED = "resolved"
ROLE_SERVICE_MODEL_ALIAS_UNRESOLVED = "unresolved"
ROLE_SERVICE_MODEL_ALIAS_UNCONFIGURED = "unconfigured"
ROLE_SERVICE_READINESS_READY = "ready"
ROLE_SERVICE_READINESS_FAILED = "failed"
ROLE_SERVICE_READINESS_UNKNOWN = "unknown"
ROLE_SERVICE_READINESS_PENDING = "pending"

# 本片实现的服务生命周期稳定错误码（合同 §10.6，逐字一致）。
ROLE_SERVICE_ERROR_GENERATION_CONFLICT = "generation_conflict"
ROLE_SERVICE_ERROR_ALREADY_RUNNING = "already_running"
ROLE_SERVICE_ERROR_ALREADY_STOPPED = "already_stopped"
ROLE_SERVICE_ERROR_LAUNCH_NOT_FOUND = "launch_not_found"
ROLE_SERVICE_ERROR_LAUNCH_NOT_PENDING = "launch_not_pending"
ROLE_SERVICE_ERROR_LAUNCH_EXPIRED = "launch_expired"
ROLE_SERVICE_ERROR_LAUNCH_ACTION_MISMATCH = "launch_action_mismatch"
ROLE_SERVICE_ERROR_EXPECTED_INSTANCE_MISMATCH = "expected_instance_mismatch"
ROLE_SERVICE_ERROR_STALE_REPORT = "stale_report"
ROLE_SERVICE_ERROR_REPORT_CONFLICT = "report_conflict"
ROLE_SERVICE_ERROR_REPORT_UNAUTHORIZED = "report_unauthorized"
ROLE_SERVICE_ERROR_CLAIM_EXPIRED = "claim_expired"
ROLE_SERVICE_ERROR_READINESS_TIMEOUT = "readiness_timeout"
ROLE_SERVICE_ERROR_NATIVE_LOGIN_UNVERIFIED = "native_login_unverified"
ROLE_SERVICE_ERROR_MODEL_ALIAS_UNRESOLVED = "model_alias_unresolved"
ROLE_SERVICE_ERROR_CLI_MISSING = "cli_missing"
ROLE_SERVICE_ERROR_IDENTITY_MISMATCH = "identity_mismatch"
ROLE_SERVICE_ERROR_UNKNOWN_OWNER = "unknown_owner"
ROLE_SERVICE_ERROR_STOP_TIMEOUT = "stop_timeout"
ROLE_SERVICE_ERROR_INSTANCE_PROJECT_IMMUTABLE = "instance_project_immutable"
ROLE_SERVICE_ERROR_INSTANCE_LAUNCH_IMMUTABLE = "instance_launch_immutable"
ROLE_SERVICE_ERROR_INSTANCE_PROJECT_NOT_IN_ROSTER = "instance_project_not_in_roster"
# 实现选择（R1-3 新增，如实登记，不改变上面合同码的语义）：
# - ``control_kind_not_managed``：运行器未声明 ``managed_cli``，服务端在**启动**
#   入口就如实拒绝，而不是建一个没有宿主能领取的 launch 让它挂到 readiness_timeout；
#   停止入口**不**受此限制（已受管的进程必须始终可停）。
# - ``role_not_in_roster`` / ``member_disabled``：角色/名册/禁用资格检查的稳定拒绝码。
ROLE_SERVICE_ERROR_CONTROL_KIND_NOT_MANAGED = "control_kind_not_managed"
ROLE_SERVICE_ERROR_ROLE_NOT_IN_ROSTER = "role_not_in_roster"
ROLE_SERVICE_ERROR_MEMBER_DISABLED = "member_disabled"
ROLE_SERVICE_ERROR_ROLE_BINDING_MISSING = "role_binding_missing"
ROLE_SERVICE_ERROR_ROLE_NOT_FOUND = "role_not_found"
ROLE_SERVICE_ERROR_ROLE_ARCHIVED = "role_archived"
ROLE_SERVICE_ERROR_PROJECT_NOT_FOUND = "project_not_found"
# 运行期只读投影诊断；不改写启动回执、不据此释放进程归属。
ROLE_SERVICE_ERROR_INSTANCE_UNAVAILABLE = "instance_unavailable"
ROLE_SERVICE_ERROR_INSTANCE_IDENTITY_MISMATCH = "instance_identity_mismatch"
ROLE_SERVICE_ERROR_INSTANCE_HEARTBEAT_EXPIRED = "instance_heartbeat_expired"

# 动作截止时间（秒）：claim 与 report 都必须落在
# ``claimed_at ≤ report_time ≤ launch_expires_at`` 内（合同 §10.2/§10.5）。
ROLE_SERVICE_LAUNCH_TTL_SECONDS = 120
# 就绪与运行期实例心跳 TTL（秒）：超过不产生就绪，运行期只读投影降为待核实。
ROLE_SERVICE_INSTANCE_FRESH_SECONDS = 90
# 批量“全部启动”单次最多处理的角色数（防止一次请求无限扩张）。
ROLE_SERVICE_START_ALL_MAX_MEMBERS = 200


def new_role_service_launch_id() -> str:
    """动作 ID：``uuid4`` 字符串（合同 §4.1.6）。"""
    return str(uuid4())


def new_expected_instance_id() -> str:
    """预分配的全新实例 ID：``ins_<12hex>``（合同 §4.1.6）。"""
    return f"ins_{secrets.token_hex(6)}"


def new_role_service_host_token() -> str:
    """owner/claim token 明文：只在响应里出现一次，库里只存 sha256 哈希。"""
    return secrets.token_urlsafe(32)


def hash_role_service_token(token: str) -> str:
    """token → 库内哈希（与 R1-1 的 ``hashlib.sha256`` 先例一致）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RoleServiceState(SQLModel, table=True):
    """角色服务生命周期状态（角色生命周期 R1-3，合同 §4.1.5）。

    - 主键 ``(project_id, member_id)``；默认 ``desired_state='stopped'``
      （保存配置 ≠ 启动）；
    - ``generation`` 是启动/停止世代号，用**条件更新**保证同一角色同一时刻只有一个
      动作生效（后到者 ``409 generation_conflict``）；
    - ``owner_host`` / ``process_launch_id`` 记录**原 start** 的宿主与动作归属：
      stop 动作不覆盖它，正常停服成功后才清空；无法证明已停时保留供诊断，
      **不重新认领**（合同 §10.7）；
    - ``pid`` / ``process_started_at`` 只作诊断提示，不用于所有权判定；
    - ``spawned`` 是宿主在 ``start`` 失败回报里给出的**已落盘区分事实**：
      ``True`` = 宿主确实 spawn 过（无论是否已就绪），失败**不**释放原所有权；
      ``False`` = 纯预检失败（没有产生进程），失败可安全释放所有权并允许重试；
      ``None`` = 旧宿主未上报，回退按“回报是否带 pid”判断（保守：带 pid 即视为已 spawn）。
      该列只由宿主回报写入，绝不由意图写入口直接设置。
    - 本表不存任何 token/Key 明文。
    """

    __tablename__ = "role_service_state"

    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True, index=True)
    desired_state: str = Field(default=ROLE_SERVICE_DESIRED_STOPPED)
    observed_state: str = Field(default=ROLE_SERVICE_OBSERVED_NOT_STARTED)
    manager_kind: str = Field(default=ROLE_SERVICE_MANAGER_CLI_PROCESS)
    control_kind: str = Field(default=RUNNER_CONTROL_UNKNOWN)
    generation: int = Field(default=0)
    current_launch_id: Optional[str] = Field(default=None, index=True)
    observed_instance_id: Optional[str] = None
    owner_host: Optional[str] = None
    process_launch_id: Optional[str] = None
    spawned: Optional[bool] = None
    pid: Optional[int] = None
    process_started_at: Optional[datetime] = None
    last_result: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = None


class RoleServiceLaunch(SQLModel, table=True):
    """每次启动/停止动作的 CAS/幂等记录（角色生命周期 R1-3，合同 §4.1.6）。

    - ``action`` 显式区分 ``start``/``stop``；
    - ``expected_instance_id`` 由服务端在创建动作时**预分配**（start 是全新
      ``ins_<12hex>``，stop 沿用原 start 的实例 ID）；无 ``none_`` 占位实例，
      所有权未知直接拒绝 ``unknown_owner``；
    - ``launch_expires_at`` 是一等列：claim 与 report 都必须在
      ``claimed_at ≤ report_time ≤ launch_expires_at`` 内；
    - ``owner_token_hash`` **只在 start claim 生成**；stop 沿用原 start 的哈希并要求
      宿主提交已持有的明文，绝不重新发行原进程所有权；
    - ``report_fingerprint`` 用于“同一完整载荷重放只读返回原 receipt”，
      不允许靠相同 outcome 冒充同一载荷；
    - 库内只有 token 哈希，绝不存明文。
    """

    __tablename__ = "role_service_launches"
    __table_args__ = (
        Index(
            "ux_role_service_launches_generation",
            "project_id",
            "member_id",
            "generation",
            unique=True,
        ),
        Index("ix_role_service_launches_state_expiry", "state", "launch_expires_at"),
        Index("ix_role_service_launches_role", "project_id", "member_id"),
    )

    launch_id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    member_id: str = Field(index=True)
    action: str
    generation: int
    state: str = Field(default=ROLE_SERVICE_LAUNCH_PENDING)
    expected_instance_id: str
    target_start_launch_id: Optional[str] = None
    launch_expires_at: datetime
    claim_member_id: Optional[str] = None
    claim_host: Optional[str] = None
    claim_token_hash: Optional[str] = None
    owner_token_hash: Optional[str] = None
    first_instance_seen_at: Optional[datetime] = None
    report_fingerprint: Optional[str] = None
    claimed_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    instance_id: Optional[str] = None
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleServiceRecovery(SQLModel, table=True):
    """人类明确确认原进程已停止的独立审计；不伪造原宿主停止回执。"""

    __tablename__ = "role_service_recoveries"

    project_id: str = Field(primary_key=True)
    member_id: str = Field(primary_key=True)
    operation_key: str = Field(primary_key=True)
    recovery_id: str = Field(default_factory=lambda: str(uuid4()), unique=True)
    request_fingerprint: str
    previous_generation: int
    generation: int
    process_launch_id: str
    instance_id: str
    owner_host: str
    confirmed_by: str
    reason: str
    recovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    before_state: dict = Field(sa_column=Column(JSON, nullable=False))


def new_provision_step(*, attempts: int = 1) -> dict:
    """单步初值（合同 §1）：启动即 ``pending``、``error_code``/``updated_at`` 为空。"""
    return {
        "state": PROVISION_STEP_STATE_PENDING,
        "attempts": attempts,
        "error_code": None,
        "updated_at": None,
    }


def build_fresh_provision_steps() -> dict:
    """新建作业的三步初值：全部 ``pending`` 且 ``attempts=1``（首次创建即一次尝试）。"""
    return {step: new_provision_step(attempts=1) for step in PROVISION_STEP_ORDER}


def normalize_provision_steps(raw: Optional[dict]) -> dict:
    """把存储/入参 ``steps`` 归一为固定三步 × 白名单四字段。

    返回**全新** dict（不原地改调用方的对象），并丢弃任何多余键：公开响应因此天然
    不可能夹带 Key/路径/argv/异常文本等额外字段（合同 §2.4 白名单）。
    """
    source = raw if isinstance(raw, dict) else {}
    normalized: dict = {}
    for step in PROVISION_STEP_ORDER:
        entry = source.get(step)
        if not isinstance(entry, dict):
            entry = {}
        state = entry.get("state")
        if state not in PROVISION_STEP_STATES:
            state = PROVISION_STEP_STATE_PENDING
        attempts = entry.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            attempts = 0
        error_code = entry.get("error_code")
        if not isinstance(error_code, str):
            error_code = None
        updated_at = entry.get("updated_at")
        if not isinstance(updated_at, str):
            updated_at = None
        normalized[step] = {
            "state": state,
            "attempts": attempts,
            "error_code": error_code,
            "updated_at": updated_at,
        }
    return normalized


def compute_provision_job_status(steps: Optional[dict]) -> str:
    """按合同 §1.1 **唯一算法**从三步状态聚合出作业状态（纯函数）。

    服务端（A 端）实现、宿主脚本（B 端）只读消费；这里不引入任何“上次动作/百分比”
    之类的猜测状态。
    """
    normalized = normalize_provision_steps(steps)
    states = [normalized[step]["state"] for step in PROVISION_STEP_ORDER]
    if PROVISION_STEP_STATE_FAILED in states:
        if PROVISION_STEP_STATE_PENDING in states:
            return PROVISION_JOB_STATUS_PARTIAL
        if all(state == PROVISION_STEP_STATE_FAILED for state in states):
            return PROVISION_JOB_STATUS_FAILED
        return PROVISION_JOB_STATUS_PARTIAL
    if all(state == PROVISION_STEP_STATE_PENDING for state in states):
        return PROVISION_JOB_STATUS_PENDING
    if PROVISION_STEP_STATE_PENDING in states:
        return PROVISION_JOB_STATUS_RUNNING
    return PROVISION_JOB_STATUS_SUCCEEDED


def serialize_provision_job(
    job: RoleProvisionJob,
    *,
    role_credential_version: Optional[int] = None,
    expected_binding_fingerprint: Optional[str] = None,
) -> dict:
    """公开响应白名单（合同 §2.4）：固定字段 + 归一后的三步，绝不夹带凭据。

    ``credential_version`` 只是作业代际绑定的凭据版本**计数**（不是凭据本身），
    供宿主脚本在本地副作用前捕获并在 ACK 时回传做原子校验（补正 F1）。

    ``role_credential_version``（R1-2 followup 补正 G1）是**读取时角色行当前**的凭据版本
    计数（仍不是凭据本身）：宿主脚本据此判断作业代际是否已被轮换作废，从而不再把
    “旧成功”无条件当成免 ACK 的 no-op。作业快照与当前值不一致时必须显式续跑。
    调用方未提供时如实为 ``null``，不猜等于快照值。

    ``expected_binding_fingerprint``（R1-2 followup 补正 G3）是**本作业锚定的创建操作**
    所选 choice 的六维事实指纹（与 ``GET .../binding`` 的 ``binding_fingerprint`` 同一
    算法/维度，只是内容哈希，不含凭据/路径/argv）。宿主脚本据此把“不可变的预期来源”
    与**本次读取**的绑定逐对比较，而不是只看形状或采信另一次投影的 ``choice_source``。
    """
    return {
        "operation_key": job.operation_key,
        "project_id": job.project_id,
        "member_id": job.member_id,
        "status": job.status,
        "revision": job.revision,
        "credential_version": int(job.credential_version or 1),
        "role_credential_version": (
            None if role_credential_version is None else int(role_credential_version)
        ),
        "expected_binding_fingerprint": expected_binding_fingerprint,
        "resume_of": job.resume_of,
        "steps": normalize_provision_steps(job.steps),
        "created_by": job.created_by,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def provision_member_dir_name(member_id: object) -> str:
    """``.talk/agents/<dir>`` 的目录名（与 ``cli.profiles.member_dir_name`` 同一映射）。

    R1-2 补正 F8：``provision/roster-paths`` 必须把三条路径绑定到**目标角色自己**的
    目录，不能借用另一个角色的档案路径。
    """
    return str(member_id).replace(":", "_")


def normalize_provision_roster_paths(
    identity_path: object,
    soul_path: object,
    user_path: object,
    *,
    expected_member_dir: Optional[str] = None,
) -> dict:
    """校验并归一化本作业登记的三个**单角色目录**相对路径。

    规则（任一不满足即 ``ValueError``，API 层映射 ``422 provision_roster_path_invalid``）：

    - 必须是字符串、非空、且不含任何控制字符（``ord < 32`` 或 DEL）；
    - 反斜杠统一归一为 ``/``，并去掉首尾空白；
    - 拒绝绝对路径（Windows 盘符 ``X:\\``/``X:/``、前导 ``/`` 或 ``\\\\``）；
    - 拒绝任何 ``..`` 段；
    - 三条路径必须**恰好**是 ``.talk/agents/<role_dir>/<BASENAME>``：同一
      ``<role_dir>``，且 ``identity_path``/``soul_path``/``user_path`` 的 basename
      分别为 ``IDENTITY.md``/``SOUL.md``/``USER.md``（多一层子目录同样拒绝）；
    - 给了 ``expected_member_dir`` 时（补正 F8），``<role_dir>`` 必须**恰好**等于
      目标角色自己的目录名，拒绝把 A 角色的档案路径登记给 B 角色。

    返回**全新** dict，只含三个白名单字段；不读文件、不写文件、不触网。
    """
    values = {
        "identity_path": identity_path,
        "soul_path": soul_path,
        "user_path": user_path,
    }
    normalized: dict = {}
    directories: set[str] = set()
    for field, basename in PROVISION_ROSTER_PATH_BASENAMES.items():
        value = values[field]
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(
                f"{field} must not be empty or contain control characters"
            )
        candidate = value.replace("\\", "/").strip()
        if not candidate:
            raise ValueError(f"{field} must be a non-empty relative path")
        if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
            raise ValueError(f"{field} must not be an absolute path")
        segments = candidate.split("/")
        if any(segment == ".." for segment in segments):
            raise ValueError(f"{field} must not contain a '..' segment")
        if (
            len(segments) != 4
            or segments[0] != PROVISION_ROSTER_PATH_ROOT[0]
            or segments[1] != PROVISION_ROSTER_PATH_ROOT[1]
            or not segments[2]
            or segments[2] in (".", "..")
            or segments[3] != basename
        ):
            raise ValueError(
                f"{field} must be exactly .talk/agents/<role_dir>/{basename}"
            )
        directories.add(segments[2])
        normalized[field] = "/".join(segments)
    if len(directories) != 1:
        raise ValueError(
            "roster paths must share the same .talk/agents/<role_dir>/ prefix"
        )
    if expected_member_dir is not None and next(iter(directories)) != expected_member_dir:
        raise ValueError(
            "roster paths must bind to the target member's own .talk/agents/<role_dir>/"
        )
    return normalized


def looks_like_credential(value: str) -> bool:
    """有限启发式凭据形态检查（合同 §4.2、§5.4）。

    只覆盖 ``sk-`` 前缀、``Bearer ``、``scheme://user:pass@`` 与连续 ≥ 40 位
    base64/hex 风格串；**不是**安全证明，只用于尽早 422 降低误入概率。
    """
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    if lowered.startswith("sk-") or "bearer " in lowered:
        return True
    if CREDENTIAL_URL_PATTERN.search(value):
        return True
    return bool(CREDENTIAL_LIKE_PATTERN.search(value))


def is_safe_identifier_token(
    value: Optional[str], *, max_chars: int = SAFE_TOKEN_MAX_CHARS
) -> bool:
    """安全 token 规则（合同 §4.2）：字符白名单 + 长度 + 有限凭据启发式。

    匹配是**整串**判定（``fullmatch`` + 结尾锚点）：存储值末尾的换行/制表等控制字符
    一律判为不可解析，不做 ``strip()`` 掩盖坏值（R3）。
    """
    if not isinstance(value, str):
        return False
    if not value or len(value) > max_chars:
        return False
    if not SAFE_TOKEN_PATTERN.fullmatch(value):
        return False
    return not looks_like_credential(value)


def normalize_safe_identifier_token(
    value: Optional[str],
    *,
    field: str,
    max_chars: int = SAFE_TOKEN_MAX_CHARS,
    required: bool = True,
) -> Optional[str]:
    """归一化并校验安全 token；可选字段全空白归 ``None``，不静默截断、不静默丢弃。"""
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        if required:
            raise ValueError(f"{field} must be a non-empty string")
        return None
    if not is_safe_identifier_token(normalized, max_chars=max_chars):
        raise ValueError(f"{field} is not a safe identifier token")
    return normalized


def normalize_runner_id(value: Optional[str]) -> str:
    """``runner_id`` slug 规则（合同 §3.1）。"""
    if not isinstance(value, str):
        raise ValueError("runner_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("runner_id is required")
    if not RUNNER_ID_PATTERN.fullmatch(normalized):
        raise ValueError("runner_id must match ^[a-z0-9][a-z0-9._:\\-]{0,63}$")
    return normalized


def normalize_runner_runtime(value: Optional[str]) -> str:
    """``runtime`` 族标识规则（合同 §3.1）。"""
    if not isinstance(value, str):
        raise ValueError("runtime must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("runtime is required")
    if not RUNNER_RUNTIME_PATTERN.fullmatch(normalized):
        raise ValueError("runtime must match ^[a-z0-9][a-z0-9._\\-]{0,31}$")
    return normalized


def normalize_runner_display_name(value: Optional[str]) -> str:
    if not isinstance(value, str):
        raise ValueError("display_name must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("display_name is required")
    if len(normalized) > RUNNER_DISPLAY_NAME_MAX_CHARS:
        raise ValueError(
            f"display_name must be at most {RUNNER_DISPLAY_NAME_MAX_CHARS} characters"
        )
    return normalized


def normalize_runner_adapter_status(value: Optional[str]) -> str:
    if not isinstance(value, str):
        raise ValueError("adapter_status must be a string")
    normalized = value.strip().lower()
    if normalized not in RUNNER_ADAPTER_STATUSES:
        raise ValueError(
            f"adapter_status must be one of {list(RUNNER_ADAPTER_STATUSES)}"
        )
    return normalized


def normalize_runner_adapter_note(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("adapter_note must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > RUNNER_ADAPTER_NOTE_MAX_CHARS:
        raise ValueError(
            f"adapter_note must be at most {RUNNER_ADAPTER_NOTE_MAX_CHARS} characters"
        )
    return normalized


def normalize_runner_capabilities(value: Optional[list[str]]) -> list[str]:
    """``capabilities`` 定量规则（合同 §3.3）：不静默截断、不静默丢弃空白项、不去重。"""
    if value is None:
        raise ValueError("capabilities must be an array of strings")
    if not isinstance(value, list):
        raise ValueError("capabilities must be an array of strings")
    if len(value) > RUNNER_CAPABILITIES_MAX_ITEMS:
        raise ValueError(
            f"capabilities must contain at most {RUNNER_CAPABILITIES_MAX_ITEMS} items"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("capabilities items must be strings")
        stripped = item.strip()
        if not stripped:
            raise ValueError("capabilities items must not be blank")
        if len(stripped) > RUNNER_CAPABILITY_MAX_CHARS:
            raise ValueError(
                "capabilities items must be at most "
                f"{RUNNER_CAPABILITY_MAX_CHARS} characters"
            )
        if stripped in seen:
            raise ValueError("capabilities items must be unique after normalization")
        seen.add(stripped)
        normalized.append(stripped)
    return normalized


def normalize_runner_control_kind(value: Optional[str]) -> str:
    """``control_kind`` 枚举归一（合同 §12）。"""
    if not isinstance(value, str):
        raise ValueError("control_kind must be a string")
    normalized = value.strip().lower()
    if normalized not in RUNNER_CONTROL_KINDS:
        raise ValueError(f"control_kind must be one of {list(RUNNER_CONTROL_KINDS)}")
    return normalized


def normalize_model_choice_source_kind(value: Optional[str]) -> str:
    """模型选择的来源等级（合同 §4.1.1）：只描述来源，**不**表示可用。"""
    if not isinstance(value, str):
        raise ValueError("source_kind must be a string")
    normalized = value.strip().lower()
    if normalized not in MODEL_CHOICE_SOURCE_KINDS:
        raise ValueError(
            f"source_kind must be one of {list(MODEL_CHOICE_SOURCE_KINDS)}"
        )
    return normalized


def normalize_role_name(value: Optional[str]) -> str:
    """项目角色名规则（合同 §7.3）：先 ``strip()``，1–64 Unicode 码点，允许纯中文。

    空/全空白 → ``ValueError``（API 层映射 ``422 role_name_invalid``）。
    """
    if not isinstance(value, str):
        raise ValueError("role_name must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("role_name must be a non-empty string")
    if len(normalized) > ROLE_NAME_MAX_CHARS:
        raise ValueError(
            f"role_name must be at most {ROLE_NAME_MAX_CHARS} characters"
        )
    return normalized


def normalize_operation_key(value: Optional[str]) -> str:
    """``operation_key`` 规则（合同 §7.3）：调用方显式提供，8–128 安全 token。"""
    normalized = normalize_safe_identifier_token(
        value, field="operation_key", max_chars=OPERATION_KEY_MAX_CHARS
    )
    assert normalized is not None  # required=True
    if len(normalized) < OPERATION_KEY_MIN_CHARS:
        raise ValueError(
            f"operation_key must be at least {OPERATION_KEY_MIN_CHARS} characters"
        )
    return normalized


def normalize_model_source(value: Optional[str]) -> str:
    if not isinstance(value, str):
        raise ValueError("model_source must be a string")
    normalized = value.strip().lower()
    if normalized not in MODEL_SOURCES:
        raise ValueError(f"model_source must be one of {list(MODEL_SOURCES)}")
    return normalized


def normalize_model_display_name(value: Optional[str]) -> Optional[str]:
    """``model_display_name`` 是纯展示字段（合同 §4.1），只做长度与空白归一。"""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("model_display_name must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MODEL_DISPLAY_NAME_MAX_CHARS:
        raise ValueError(
            f"model_display_name must be at most {MODEL_DISPLAY_NAME_MAX_CHARS} characters"
        )
    return normalized


def is_parseable_stored_runner_id(value: Optional[str]) -> bool:
    """``partial`` 判定用：绑定行存储的 ``runner_id`` 是否可解析（合同 §4.5）。

    整串匹配（``fullmatch`` + 结尾锚点）：``runner:dsh-cli\\n`` 这类带末尾控制字符的
    存储值不可解析，不 ``strip()`` 掩盖（R3）。
    """
    return isinstance(value, str) and bool(RUNNER_ID_PATTERN.fullmatch(value))


def is_parseable_stored_runtime(value: Optional[str]) -> bool:
    """派生 ``runtime`` 的可解析判定（合同 §4.4 序 7、§4.5）。

    登记行存在但 ``runtime`` 为空/全空白/不匹配 §3.1 slug（含末尾控制字符）时不可解析，
    读取侧一律落到 ``runner_missing``，并让三个派生字段同为空（R2）。
    """
    return isinstance(value, str) and bool(RUNNER_RUNTIME_PATTERN.fullmatch(value))


def is_parseable_stored_model_source(value: Optional[str]) -> bool:
    return (
        isinstance(value, str)
        and value.strip().lower() in MODEL_SOURCES
    )


def binding_fingerprint(facts: Optional[dict]) -> Optional[str]:
    """配置内容指纹（合同 §2）：六值全部可解析才给出，否则 ``null``。

    ``sha256('runner_id|runtime|model_source|provider_id|connection_ref|model_id')``；
    - ``runtime`` 由登记表派生；登记事实不可解析（``runner_missing``）时 ``runtime`` 不可
      解析 → 指纹为 ``null``；
    - 指纹与“当前是否有效”无关：无效行只要六值可解析就有指纹；
    - 指纹**不含** ``model_alias`` / ``model_display_name``，因此指纹相同 **不等于**
      完整调用配置相同（alias 是原生调用选择参数）。
    """
    if not facts:
        return None
    runner_id = facts.get("runner_id")
    runtime = facts.get("runtime")
    model_source = facts.get("model_source")
    provider_id = facts.get("provider_id")
    connection_ref = facts.get("connection_ref")
    model_id = facts.get("model_id")
    if not is_parseable_stored_runner_id(runner_id):
        return None
    if not is_parseable_stored_runtime(runtime):
        return None
    if not is_parseable_stored_model_source(model_source):
        return None
    if not is_safe_identifier_token(provider_id):
        return None
    if not is_safe_identifier_token(connection_ref):
        return None
    if not is_safe_identifier_token(model_id):
        return None
    payload = "|".join(
        [runner_id, runtime, model_source, provider_id, connection_ref, model_id]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stored_required_fields_parseable(facts: dict) -> bool:
    """``partial`` 只由绑定行**存储必填五项**触发（合同 §4.5）。

    派生 ``runtime`` 不参与：登记表查不到 ``runner_id`` 时若五项齐全，仍应落到序 7
    ``runner_missing``，不能被 ``partial`` 抢先。
    """
    if not is_parseable_stored_runner_id(facts.get("runner_id")):
        return False
    if not is_parseable_stored_model_source(facts.get("model_source")):
        return False
    if not is_safe_identifier_token(facts.get("provider_id")):
        return False
    if not is_safe_identifier_token(facts.get("connection_ref")):
        return False
    if not is_safe_identifier_token(facts.get("model_id")):
        return False
    return True


def resolve_role_binding_state(facts: Optional[dict]) -> Optional[str]:
    """按合同 §4.4 阶梯计算绑定状态（读取时现算，只读，不修改任何数据）。

    优先级严格按序，先命中先返回：
    ``member_missing → member_disabled → not_in_roster → not_agent → unconfigured →
    partial → runner_missing → runner_retired → bound``。

    - 身份/名册事实先于绑定内容事实（“离册 + runner retired”报 ``not_in_roster``）；
    - ``project_exists = 0`` **不是**一种 ``binding_state``：返回 ``None``，由调用 API
      映射原错误码（项目接口 404、任务创建 400），事实助手本身不固定 HTTP 状态码；
    - 不自动清理行、不用成员名/模型名/历史惯例猜出运行器或模型。
    """
    if not facts:
        return None
    if not facts.get("project_exists"):
        return None
    if not facts.get("member_exists"):
        return ROLE_BINDING_MEMBER_MISSING
    if facts.get("member_disabled_at") is not None:
        return ROLE_BINDING_MEMBER_DISABLED
    if not facts.get("in_roster"):
        return ROLE_BINDING_NOT_IN_ROSTER
    if facts.get("member_kind") != "agent":
        return ROLE_BINDING_NOT_AGENT
    if not facts.get("binding_exists"):
        return ROLE_BINDING_UNCONFIGURED
    if not _stored_required_fields_parseable(facts):
        return ROLE_BINDING_PARTIAL
    runtime = facts.get("runtime")
    if not facts.get("runner_exists") or not is_parseable_stored_runtime(runtime):
        return ROLE_BINDING_RUNNER_MISSING
    if facts.get("runner_status") == RUNNER_ADAPTER_RETIRED:
        return ROLE_BINDING_RUNNER_RETIRED
    return ROLE_BINDING_BOUND


def _derived_runner_fields(
    facts: dict,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """运行器三个派生字段（``runtime`` / ``runner_display_name`` / ``runner_status``）。

    合同 §4.2/§4.4 序 7（R2 定向修正）：登记事实不可解析（登记行缺失，或登记行存在但
    ``runtime`` 为空/全空白/不合法）时**三者一律 ``null``**，不能只把 ``runtime`` 清空而
    照返展示名与状态。判定只看**登记事实可解析性**，不看成员身份/名册：离册、禁用、非
    agent 的保留行只要登记事实可解析，仍照常派生出运行器字段（§7.2）。
    """
    if not facts.get("runner_exists") or not is_parseable_stored_runtime(
        facts.get("runtime")
    ):
        return None, None, None
    return (
        facts.get("runtime"),
        facts.get("runner_display_name"),
        facts.get("runner_status"),
    )


def build_role_binding_out(facts: Optional[dict]) -> Optional["RoleBindingOut"]:
    """把事实行转成 ``RoleBindingOut``；没有存储行（``binding_exists = 0``）返回 ``None``。

    行存在时**按存储值照返**（即使当前无效）：有效性写在 ``binding_state``，
    运行器派生字段来自登记表，并统一经 :func:`_derived_runner_fields` 规范化——
    登记事实不可解析时三者如实为 ``null``。
    """
    if not facts or not facts.get("binding_exists"):
        return None
    runtime, runner_display_name, runner_status = _derived_runner_fields(facts)
    return RoleBindingOut(
        runner_id=facts.get("runner_id"),
        runtime=runtime,
        runner_display_name=runner_display_name,
        runner_status=runner_status,
        model_source=facts.get("model_source"),
        provider_id=facts.get("provider_id"),
        connection_ref=facts.get("connection_ref"),
        model_id=facts.get("model_id"),
        model_alias=facts.get("model_alias"),
        model_display_name=facts.get("model_display_name"),
        binding_state=resolve_role_binding_state(facts),
        binding_fingerprint=binding_fingerprint(facts),
        updated_by=facts.get("updated_by"),
        updated_at=facts.get("updated_at"),
    )


# ── 单语句事实读取（合同 §7.3；B1b 复用同一助手，不复制第二份） ──────

_BINDING_FACTS_SQL_ANCHOR = (
    "WITH requested(project_id, member_id) AS (\n"
    "    SELECT :project_id AS project_id, :member_id AS member_id\n"
    ")"
)

# 以下 SQL 原文与合同 §7.3 / 计划 §2.3 的 fenced SQL 逐字符一致
# （sha256 = a812ee474b4710f5eac29f773fb02f39dec70201c3fdd0abc66709f7b17f0f1e，2484 字符）。
_BINDING_FACTS_SQL_BODY = """
SELECT
    req.project_id                                   AS requested_project_id,
    req.member_id                                    AS requested_member_id,
    p.project_id                                     AS project_id,
    (p.project_id IS NOT NULL)                       AS project_exists,
    m.id                                             AS member_id,
    (m.id IS NOT NULL)                               AS member_exists,
    m.kind                                           AS member_kind,
    m.disabled_at                                    AS member_disabled_at,
    pa.member_id                                     AS roster_member_id,
    (pa.member_id IS NOT NULL)                       AS in_roster,
    b.project_id                                     AS binding_project_id,
    b.member_id                                      AS binding_member_id,
    (b.project_id IS NOT NULL)                       AS binding_exists,
    b.runner_id                                      AS runner_id,
    r.runner_id                                      AS registry_runner_id,
    (r.runner_id IS NOT NULL)                        AS runner_exists,
    r.runtime                                        AS runtime,
    r.display_name                                   AS runner_display_name,
    r.adapter_status                                 AS runner_status,
    b.model_source                                   AS model_source,
    b.provider_id                                    AS provider_id,
    b.connection_ref                                 AS connection_ref,
    b.model_id                                       AS model_id,
    b.model_alias                                    AS model_alias,
    b.model_display_name                             AS model_display_name,
    b.updated_by                                     AS updated_by,
    b.updated_at                                     AS updated_at
FROM requested AS req
LEFT JOIN projects              AS p  ON p.project_id  = req.project_id
LEFT JOIN members               AS m  ON m.id          = req.member_id
LEFT JOIN project_agents        AS pa ON pa.project_id = req.project_id AND pa.member_id = req.member_id
LEFT JOIN project_role_bindings AS b  ON b.project_id  = req.project_id AND b.member_id  = req.member_id
LEFT JOIN runner_registry       AS r  ON r.runner_id   = b.runner_id;"""

BINDING_FACTS_SQL = _BINDING_FACTS_SQL_ANCHOR + _BINDING_FACTS_SQL_BODY

# 27 个唯一列别名（顺序与 SQL 一致）；无项目分支用它构造全 null 事实。
BINDING_FACTS_COLUMNS = (
    "requested_project_id",
    "requested_member_id",
    "project_id",
    "project_exists",
    "member_id",
    "member_exists",
    "member_kind",
    "member_disabled_at",
    "roster_member_id",
    "in_roster",
    "binding_project_id",
    "binding_member_id",
    "binding_exists",
    "runner_id",
    "registry_runner_id",
    "runner_exists",
    "runtime",
    "runner_display_name",
    "runner_status",
    "model_source",
    "provider_id",
    "connection_ref",
    "model_id",
    "model_alias",
    "model_display_name",
    "updated_by",
    "updated_at",
)


def read_role_binding_facts(
    session: Session, *, project_id: Optional[str], member_id: str
) -> dict:
    """一条 SQL 取齐项目/成员/名册/绑定/登记事实（合同 §7.3）。

    - 带项目：``session.execute(text(BINDING_FACTS_SQL), {...}).mappings().one()``，
      **恰好 1 行**（五个 LEFT JOIN 右表都是主键等值连接），无绑定行时仍返回 1 行；
    - ``project_id is None``：**不执行 SQL**（语句数 0），返回全 ``null`` 事实，只有
      ``requested_member_id`` 是请求值；``state`` 由调用方按 ``no_project`` 处理（B1b）；
    - 本助手**不固定 HTTP 错误码**：``project_exists = 0`` 只作为事实返回；
    - 不追加第二条补查询，也不用早先 ORM 缓存/成员对象推断状态。
    """
    if project_id is None:
        facts = {column: None for column in BINDING_FACTS_COLUMNS}
        facts["requested_member_id"] = member_id
        return facts
    row = session.execute(
        text(BINDING_FACTS_SQL),
        {"project_id": project_id, "member_id": member_id},
    ).mappings().one()
    return dict(row)


def build_binding_facts_batch_sql(member_count: int) -> str:
    """批量事实读取 SQL：与单条助手**同一段 SELECT/JOIN**，只把请求 CTE 换成多行。

    列集合、别名、空行语义、状态语义与单条严格一致；仍是一条语句、每个请求 pair
    恰好 1 行（含无绑定行）。
    """
    if member_count < 1:
        raise ValueError("member_count must be >= 1")
    values = ", ".join(f"(:p{index}, :m{index})" for index in range(member_count))
    anchor = f"WITH requested(project_id, member_id) AS (\n    VALUES {values}\n)"
    return anchor + BINDING_FACTS_SQL[len(_BINDING_FACTS_SQL_ANCHOR):]


def read_role_binding_facts_batch(
    session: Session, *, project_id: str, member_ids: list[str]
) -> list[dict]:
    """一次 SQL 批量取多个角色的绑定事实（GET /agents 用，避免逐角色 N+1）。

    空请求直接返回 ``[]``（不查库、不改数据）；返回顺序不保证，调用方按
    ``requested_member_id`` 建索引。
    """
    if not member_ids:
        return []
    sql = build_binding_facts_batch_sql(len(member_ids))
    params: dict[str, str] = {}
    for index, member_id in enumerate(member_ids):
        params[f"p{index}"] = project_id
        params[f"m{index}"] = member_id
    rows = session.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


# ── 任务绑定快照（B1b，合同 §7.2/§7.3；复用 B1a 单语句事实助手） ──────


class TargetBindingSnapshotProjectMissing(LookupError):
    """``project_exists = 0``：事实助手不固定 HTTP 错误码，只把“项目不存在”交给调用方。

    项目名册/绑定接口把它映射为 **404**，任务创建映射为 **400**（合同 §7.3、§11）。
    本异常**不带** HTTP 语义，``server/models.py`` 不依赖 FastAPI。
    """

    def __init__(self, project_id: Optional[str]) -> None:
        super().__init__(f"project not found: {project_id}")
        self.project_id = project_id


# 每个状态的 note 文案（合同 §7.1 只固定 key 与 schema_version，note 是自由文本；
# 这里按 `ROLE_MODEL_BINDING_EXAMPLES.json` 的合成样例给出确定性说明）。
# note 与快照其它字段一样**永不**包含凭据正文（合同 §5.2/§5.3）。
_TARGET_BINDING_SNAPSHOT_NOTES: dict[str, Optional[str]] = {
    ROLE_BINDING_NO_PROJECT: "任务无项目归属；无绑定上下文。普通无项目任务与 schedule 物化都走这里。",
    ROLE_BINDING_MEMBER_MISSING: "身份已不存在；保留存储但记录失效原因",
    ROLE_BINDING_MEMBER_DISABLED: "成员被全局禁用；绑定存储保留但不有效",
    ROLE_BINDING_NOT_IN_ROSTER: "角色已离册，绑定行保留但不有效；不报 bound、不自动删除、不猜模型",
    ROLE_BINDING_NOT_AGENT: "kind != agent；保留存储但不有效",
    ROLE_BINDING_UNCONFIGURED: "角色尚未配置运行器/模型绑定；不猜测默认值",
    ROLE_BINDING_PARTIAL: "绑定存储必填字段不完整；有值的字段照存，缺的为 null",
    ROLE_BINDING_RUNNER_MISSING: (
        "登记事实不可解析（登记行缺失或 runtime 不可解析）；runtime 与内容指纹均为 null"
    ),
    ROLE_BINDING_RUNNER_RETIRED: "运行器登记为 retired；不用于新绑定，但历史快照保留",
    ROLE_BINDING_BOUND: None,
}


def build_target_binding_snapshot(facts: Optional[dict], state: str) -> dict:
    """按合同 §7.1/§7.2 构造固定 13 键的任务快照对象（纯计算，不查库、不写库）。

    - 键顺序与 :data:`TARGET_BINDING_SNAPSHOT_KEYS` 一致，**无** ``read_receipt``；
    - ``state`` 由调用方给出（``no_project`` 只属于任务快照），并写入同一个对象；
    - 行值**照存**（``runner_id`` / ``model_source`` / ``provider_id`` / ``connection_ref`` /
      ``model_id`` / ``model_alias`` / ``model_display_name``）；没有绑定行时这些值为 ``null``；
    - ``runtime`` 走与 B1a 相同的派生规则：登记事实不可解析时如实为 ``null``（R2）；
    - ``binding_fingerprint`` 复用 :func:`binding_fingerprint`（六值全部可解析才给出）；
    - ``snapshot_at`` 是 UTC ISO8601；**任何状态都不猜运行器或模型**。
    """
    snapshot_source = facts or {}
    runtime, _runner_display_name, _runner_status = _derived_runner_fields(snapshot_source)
    return {
        "schema_version": ROLE_BINDING_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "runner_id": snapshot_source.get("runner_id"),
        "runtime": runtime,
        "model_source": snapshot_source.get("model_source"),
        "provider_id": snapshot_source.get("provider_id"),
        "connection_ref": snapshot_source.get("connection_ref"),
        "model_id": snapshot_source.get("model_id"),
        "model_alias": snapshot_source.get("model_alias"),
        "model_display_name": snapshot_source.get("model_display_name"),
        "binding_fingerprint": binding_fingerprint(snapshot_source),
        "note": _TARGET_BINDING_SNAPSHOT_NOTES.get(state),
    }


def resolve_target_binding_snapshot(
    *,
    project_id: Optional[str],
    target_member_id: str,
    session: Session,
) -> dict:
    """解析任务创建时的目标角色绑定快照（合同 §7.3，B1b 唯一快照构造入口）。

    - ``project_id is None``：**不执行任何 SQL**（语句数 0），直接 ``state="no_project"``、
      绑定字段全 ``null``，两列仍写非 NULL（合同 §7.6）；
    - 带项目：复用 B1a 的 :func:`read_role_binding_facts`（**同一条 SQL、同一个助手**，
      不复制第二份 SQL、不做 ORM 补查），``project_exists = 0`` 时抛
      :class:`TargetBindingSnapshotProjectMissing`，由调用 API 保持原错误码（任务创建 400）；
    - 状态按 §4.4 阶梯现算；snapshot 与 state 同源，``snapshot["state"]`` 即列值；
    - 只读：不 UPDATE 任何行，不自动清理绑定行，也不用早先 ORM 缓存推断状态。
    """
    facts = read_role_binding_facts(
        session, project_id=project_id, member_id=target_member_id
    )
    if project_id is None:
        return build_target_binding_snapshot(facts, ROLE_BINDING_NO_PROJECT)
    state = resolve_role_binding_state(facts)
    if state is None:
        raise TargetBindingSnapshotProjectMissing(project_id)
    return build_target_binding_snapshot(facts, state)


class AgentTask(SQLModel, table=True):
    __tablename__ = "agent_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_id: Optional[int] = Field(default=None, foreign_key="agent_task_schedules.id", index=True)
    project_id: Optional[str] = Field(default=None, foreign_key="projects.project_id", index=True)
    hall_group_id: Optional[str] = Field(default=None, foreign_key="groups.id", index=True, unique=True)
    parent_task_id: Optional[int] = Field(default=None, foreign_key="agent_tasks.id", index=True)
    root_task_id: Optional[int] = Field(default=None, foreign_key="agent_tasks.id", index=True)
    delegation_depth: int = Field(default=0, index=True)
    may_delegate: bool = Field(default=False)
    max_delegation_depth: Optional[int] = None
    max_running_descendants: Optional[int] = None
    max_running_per_target: Optional[int] = None
    max_nonterminal_descendants: Optional[int] = None
    control_status: Optional[str] = Field(default=None, index=True)
    authorization_epoch: Optional[int] = None
    authorized_slice_budget: Optional[int] = None
    reserved_slice_count: Optional[int] = None
    authorization_expires_at: Optional[datetime] = Field(default=None, index=True)
    checkpoint_reason: Optional[str] = None
    milestone_test_required: bool = Field(default=False, index=True)
    max_clarification_rounds: int = Field(default=TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT)
    clarification_round_count: int = Field(default=0)
    target_member_id: str = Field(foreign_key="members.id", index=True)
    created_by: str = Field(foreign_key="members.id", index=True)
    content: str
    title: Optional[str] = None
    task_kind: str = Field(default="general", index=True)
    review_policy: Optional[str] = Field(default=None, index=True)
    gate_verdict: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    status: str = Field(default="queued", index=True)
    workflow_status: str = Field(default="assigned", index=True)
    attempt: int = Field(default=0)
    claimed_by: Optional[str] = Field(default=None, foreign_key="members.id", index=True)
    instance_id: Optional[str] = Field(default=None, foreign_key="agent_instances.id", index=True)
    claim_token: Optional[str] = None
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    heartbeat_at: Optional[datetime] = None
    result_message_id: Optional[int] = Field(default=None, foreign_key="messages.id")
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claimed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result_collected_at: Optional[datetime] = None
    # ROLE-BINDING-B1b（合同 §7.1）：任务创建时冻结的绑定快照与状态。
    # 仅旧任务/旧库为 NULL（= 未记录）；新任务一律写入对象与非 NULL 状态，
    # 写入后不可变（claim/heartbeat/complete/cancel/requeue/重领都不改这两列）。
    target_binding_snapshot: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    target_binding_state: Optional[str] = Field(default=None, index=True)
    # 292：任务级执行会话复用元数据。NULL = 该任务走旧的一次性独立会话，
    # 行为与历史任务完全一致；基础任务另存冻结正文，续接任务只存引用/哈希。
    execution_session: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    execution_session_base_text: Optional[str] = None
    # 每任务冻结当前要求供审计；不在公开任务响应或续轮提示中反复输出。
    execution_session_audit: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # bridge 完成后回传的最小窗口状态（不含正文/凭据），供任务响应核验。
    execution_session_state: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )


class AgentTaskClarificationRound(SQLModel, table=True):
    __tablename__ = "agent_task_clarification_rounds"
    __table_args__ = (
        Index("uq_task_clarification_round_index", "task_id", "round_index", unique=True),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="agent_tasks.id", index=True)
    round_index: int
    status: str = Field(default="requested", index=True)
    question_message_id: int = Field(foreign_key="messages.id")
    answer_start_message_id: Optional[int] = Field(default=None, foreign_key="messages.id")
    answer_end_message_id: Optional[int] = Field(default=None, foreign_key="messages.id")
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    answered_at: Optional[datetime] = None


class AgentTaskRelation(SQLModel, table=True):
    __tablename__ = "agent_task_relations"
    __table_args__ = (
        Index(
            "uq_agent_task_relation_source_target_type",
            "source_task_id",
            "target_task_id",
            "relation_type",
            unique=True,
        ),
        Index(
            "uq_agent_task_relation_type_target_round",
            "relation_type",
            "target_task_id",
            "round_index",
            unique=True,
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_task_id: int = Field(foreign_key="agent_tasks.id", index=True)
    target_task_id: int = Field(foreign_key="agent_tasks.id", index=True)
    relation_type: str = Field(index=True)
    trigger_task_id: Optional[int] = Field(
        default=None,
        foreign_key="agent_tasks.id",
        index=True,
    )
    round_index: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTaskSchedule(SQLModel, table=True):
    __tablename__ = "agent_task_schedules"

    id: Optional[int] = Field(default=None, primary_key=True)
    target_member_id: str = Field(foreign_key="members.id", index=True)
    created_by: str = Field(foreign_key="members.id", index=True)
    content: str
    title: Optional[str] = None
    schedule_type: str = Field(index=True)  # once | interval
    status: str = Field(default="active", index=True)  # active | paused | completed | canceled
    next_run_at: datetime = Field(index=True)
    interval_seconds: Optional[int] = None
    last_run_at: Optional[datetime] = None
    last_task_id: Optional[int] = Field(default=None, foreign_key="agent_tasks.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiscussionSession(SQLModel, table=True):
    __tablename__ = "discussion_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: str = Field(foreign_key="groups.id", index=True)
    created_by: str = Field(foreign_key="members.id", index=True)
    topic: str
    participant_ids: str
    root_message_id: Optional[int] = Field(default=None, foreign_key="messages.id", index=True)
    requester_id: Optional[str] = Field(default=None, foreign_key="members.id", index=True)
    assignee_id: Optional[str] = Field(default=None, foreign_key="members.id", index=True)
    scope_text: Optional[str] = None
    status: str = Field(default="active", index=True)
    end_reason: Optional[str] = Field(default=None, index=True)  # consensus/deadlock/timeout/manual; None=not ended or unmarked
    max_rounds: int = 2
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def participant_list(self) -> list[str]:
        return json.loads(self.participant_ids)


class DiscussionTurn(SQLModel, table=True):
    __tablename__ = "discussion_turns"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="discussion_sessions.id", index=True)
    turn_index: int = Field(index=True)
    message_id: int = Field(foreign_key="messages.id", index=True)
    speaker_id: str = Field(foreign_key="members.id", index=True)
    target_member_id: Optional[str] = Field(default=None, foreign_key="members.id", index=True)
    turn_kind: str = Field(default="reply", index=True)
    stance: str = Field(index=True)
    round_index: int = Field(default=1, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── API schemas (request / response) ────────────────────────────────


class MemberCreate(BaseModel):
    id: str  # 'human:bobo' / 'agent:AI1'
    display_name: str
    api_key: str
    poll_hint: Optional[int] = None


class MemberDisableUpdate(BaseModel):
    """`PATCH /api/members/{id}` body — toggle a member's global disabled state."""

    disabled: bool


class MemberOut(BaseModel):
    id: str
    kind: str
    display_name: str
    poll_hint: Optional[int] = None
    created_at: datetime
    disabled_at: Optional[datetime] = None


class MessageCreate(BaseModel):
    to: Optional[list[str]] = None  # None = broadcast
    group_id: Optional[str] = None
    type: str = "text"
    content: Optional[str] = None
    file_id: Optional[str] = None
    reply_to: Optional[int] = None
    caption: Optional[str] = None

    @model_validator(mode="after")
    def validate_payload(self) -> MessageCreate:
        if self.content is not None:
            self.content = self.content.strip() or None
        if self.caption is not None:
            self.caption = self.caption.strip() or None
        if self.group_id is not None:
            self.group_id = self.group_id.strip() or None

        if self.type == "text":
            if not self.content:
                raise ValueError("content is required for text messages")
            if self.file_id is not None:
                raise ValueError("file_id is only allowed for file messages")
            if self.caption is not None:
                raise ValueError("caption is only allowed for file messages")
            return self

        if self.type == "file":
            if not self.file_id:
                raise ValueError("file_id is required for file messages")
            return self

        raise ValueError("type must be 'text' or 'file'")


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    group_id: Optional[str]
    from_field: str = PydField(alias="from", serialization_alias="from")
    to: Optional[list[str]]
    type: str
    content: Optional[str]
    file_id: Optional[str]
    reply_to: Optional["MessageReplyOut"]
    caption: Optional[str]
    filename: Optional[str]
    size_bytes: Optional[int]
    mime: Optional[str]
    revoked: bool
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    created_at: datetime

    @classmethod
    def from_orm_msg(cls, msg: Message, *, reply_to: Optional["MessageReplyOut"] = None) -> "MessageOut":
        is_revoked = msg.revoked_at is not None
        return cls(**{
            "id": msg.id,
            "group_id": msg.group_id,
            "from": msg.from_id,
            "to": msg.to_list,
            "type": msg.type,
            "content": None if is_revoked else msg.content,
            "file_id": msg.file_id,
            "reply_to": reply_to,
            "caption": None if is_revoked else msg.caption,
            "filename": None if is_revoked else msg.filename,
            "size_bytes": None if is_revoked else msg.size_bytes,
            "mime": None if is_revoked else msg.mime,
            "revoked": is_revoked,
            "revoked_at": msg.revoked_at,
            "revoked_by": msg.revoked_by,
            "created_at": msg.created_at,
        })


class MessageRevokeOut(BaseModel):
    id: int
    revoked_at: datetime
    revoked_by: str


class MessageReplyOut(BaseModel):
    id: int
    from_id: str
    preview: Optional[str]
    type: str
    revoked: bool = False


class FileOut(BaseModel):
    file_id: str
    filename: str
    size_bytes: int


_GROUP_ROLES = {"owner", "moderator", "member"}
_DECISION_TIERS = {"decision", "execution"}


class GroupMemberOut(BaseModel):
    member_id: str
    role: str
    business_role: Optional[str] = None
    # 固定“决策/执行”分级已取消：本字段仅为旧数据/旧客户端兼容保留，公开 schema 明确
    # 标记 deprecated，且不参与身份、权限、协调或任何判定（R1-2 补正 F7）。
    decision_tier: Optional[str] = PydField(default=None, deprecated=True)
    created_at: datetime


class GroupCreate(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    type: Optional[str] = None  # None -> 创建时落为 DEFAULT_HALL_TYPE
    project_id: Optional[str] = None  # NULL = 无项目上下文（向后兼容历史群）
    member_ids: list[str] = []

    @model_validator(mode="after")
    def validate_group_create(self) -> "GroupCreate":
        if self.id is not None:
            self.id = self.id.strip() or None
            if self.id is not None and any(ch.isspace() for ch in self.id):
                raise ValueError("id cannot contain whitespace")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name is required")
        if self.description is not None:
            self.description = self.description.strip() or None
        if self.type is None:
            self.type = DEFAULT_HALL_TYPE
        else:
            self.type = self.type.strip().lower()
            if self.type not in HALL_TYPES:
                raise ValueError(f"type must be one of {sorted(HALL_TYPES)}")
        if self.project_id is not None:
            self.project_id = self.project_id.strip() or None
        self.member_ids = list(dict.fromkeys(member_id.strip() for member_id in self.member_ids if member_id.strip()))
        return self


class GroupUpdate(BaseModel):
    name: str
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_group_update(self) -> "GroupUpdate":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name is required")
        if self.description is not None:
            self.description = self.description.strip() or None
        return self


class GroupMemberUpdate(BaseModel):
    role: str = "member"
    business_role: Optional[str] = None
    # 已弃用兼容入参：接受旧值并原样存储，但不再参与身份/权限/协调判定（R1-2 补正 F7）。
    decision_tier: Optional[str] = PydField(default=None, deprecated=True)

    @model_validator(mode="after")
    def validate_group_member_update(self) -> "GroupMemberUpdate":
        self.role = self.role.strip().lower()
        if self.role not in _GROUP_ROLES:
            raise ValueError(f"role must be one of {sorted(_GROUP_ROLES)}")
        if self.business_role is not None:
            self.business_role = self.business_role.strip() or None
        if self.decision_tier is not None:
            self.decision_tier = self.decision_tier.strip().lower() or None
            if self.decision_tier is not None and self.decision_tier not in _DECISION_TIERS:
                raise ValueError(f"decision_tier must be one of {sorted(_DECISION_TIERS)}")
        return self


class GroupOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    type: str
    project_id: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    members: list[GroupMemberOut]


_DISCUSSION_STATUSES = {"active", "resolved", "escalated", "canceled"}
_DISCUSSION_STANCES = {"question", "answer", "agree", "optimize", "disagree", "escalate", "greeting", "closure", "decision"}
_DISCUSSION_END_REASONS = {"consensus", "deadlock", "timeout", "manual"}
_DISCUSSION_TURN_KINDS = {"demand", "reply"}


class DiscussionSessionCreate(BaseModel):
    group_id: str
    topic: str
    participant_ids: list[str]
    root_message_id: Optional[int] = None
    requester_id: Optional[str] = None
    assignee_id: Optional[str] = None
    scope_text: Optional[str] = None
    max_rounds: int = 2

    @model_validator(mode="after")
    def validate_discussion_create(self) -> "DiscussionSessionCreate":
        self.group_id = self.group_id.strip()
        self.topic = self.topic.strip()
        self.participant_ids = list(dict.fromkeys(member_id.strip() for member_id in self.participant_ids if member_id.strip()))
        if self.requester_id is not None:
            self.requester_id = self.requester_id.strip() or None
        if self.assignee_id is not None:
            self.assignee_id = self.assignee_id.strip() or None
        if self.scope_text is not None:
            self.scope_text = self.scope_text.strip() or None
        if not self.group_id:
            raise ValueError("group_id is required")
        if not self.topic:
            raise ValueError("topic is required")
        if not self.participant_ids:
            raise ValueError("participant_ids is required")
        if self.root_message_id is not None and self.root_message_id <= 0:
            raise ValueError("root_message_id must be greater than 0")
        if self.max_rounds <= 0:
            raise ValueError("max_rounds must be greater than 0")
        return self


class DiscussionSessionUpdate(BaseModel):
    status: str
    end_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_discussion_update(self) -> "DiscussionSessionUpdate":
        self.status = self.status.strip().lower()
        if self.status not in _DISCUSSION_STATUSES:
            raise ValueError(f"status must be one of {sorted(_DISCUSSION_STATUSES)}")
        if self.end_reason is not None:
            self.end_reason = self.end_reason.strip().lower()
            if self.end_reason not in _DISCUSSION_END_REASONS:
                raise ValueError(f"end_reason must be one of {sorted(_DISCUSSION_END_REASONS)}")
        return self


class DiscussionSessionOut(BaseModel):
    id: int
    group_id: str
    created_by: str
    topic: str
    participant_ids: list[str]
    root_message_id: Optional[int]
    requester_id: Optional[str]
    assignee_id: Optional[str]
    scope_text: Optional[str]
    status: str
    end_reason: Optional[str]
    max_rounds: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_session(cls, session: DiscussionSession) -> "DiscussionSessionOut":
        return cls(
            id=int(session.id or 0),
            group_id=session.group_id,
            created_by=session.created_by,
            topic=session.topic,
            participant_ids=session.participant_list,
            root_message_id=session.root_message_id,
            requester_id=session.requester_id,
            assignee_id=session.assignee_id,
            scope_text=session.scope_text,
            status=session.status,
            end_reason=session.end_reason,
            max_rounds=session.max_rounds,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


class DiscussionTurnCreate(BaseModel):
    message_id: int
    target_member_id: Optional[str] = None
    turn_kind: str = "reply"
    stance: str
    round_index: int = 1

    @model_validator(mode="after")
    def validate_discussion_turn_create(self) -> "DiscussionTurnCreate":
        if self.message_id <= 0:
            raise ValueError("message_id must be greater than 0")
        if self.target_member_id is not None:
            self.target_member_id = self.target_member_id.strip() or None
        self.turn_kind = self.turn_kind.strip().lower()
        if self.turn_kind not in _DISCUSSION_TURN_KINDS:
            raise ValueError(f"turn_kind must be one of {sorted(_DISCUSSION_TURN_KINDS)}")
        self.stance = self.stance.strip().lower()
        if self.stance not in _DISCUSSION_STANCES:
            raise ValueError(f"stance must be one of {sorted(_DISCUSSION_STANCES)}")
        if self.round_index <= 0:
            raise ValueError("round_index must be greater than 0")
        return self


class DiscussionTurnOut(BaseModel):
    id: int
    session_id: int
    turn_index: int
    message_id: int
    speaker_id: str
    target_member_id: Optional[str]
    turn_kind: str
    stance: str
    round_index: int
    created_at: datetime


_INSTANCE_STATUSES = {"starting", "online", "idle", "busy", "stopping", "offline", "error"}


class AgentInstanceUpdate(BaseModel):
    runtime: str
    status: str
    host: Optional[str] = None
    pid: Optional[int] = None
    current_task_id: Optional[str] = None
    last_error: Optional[str] = None
    # 角色生命周期 R1-1（合同 §5.4 / §10.4）：全部可选，语义是“请求中显式出现的字段”。
    # 路由只赋值 ``model_fields_set`` 里的字段，因此旧心跳省略它们时保持原值、不被抹成 NULL。
    project_id: Optional[str] = None
    launch_id: Optional[str] = None
    process_started_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_instance_status(self) -> "AgentInstanceUpdate":
        self.runtime = self.runtime.strip()
        self.status = self.status.strip().lower()
        if not self.runtime:
            raise ValueError("runtime is required")
        if self.status not in _INSTANCE_STATUSES:
            raise ValueError(f"status must be one of {sorted(_INSTANCE_STATUSES)}")
        if self.host is not None:
            self.host = self.host.strip() or None
        if self.current_task_id is not None:
            self.current_task_id = self.current_task_id.strip() or None
        if self.last_error is not None:
            self.last_error = self.last_error.strip() or None
        if self.project_id is not None:
            self.project_id = self.project_id.strip() or None
        if self.launch_id is not None:
            self.launch_id = self.launch_id.strip() or None
        return self


class AgentInstanceOut(BaseModel):
    id: str
    member_id: str
    runtime: str
    status: str
    host: Optional[str]
    pid: Optional[int]
    current_task_id: Optional[str]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    # 角色生命周期 R1-1 附加字段（旧客户端忽略未知键即可）。
    project_id: Optional[str] = None
    launch_id: Optional[str] = None
    process_started_at: Optional[datetime] = None


_TASK_STATUSES = {"queued", "running", "succeeded", "failed", "canceled"}
_TASK_TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
_TASK_WORKFLOW_STATUSES = {
    "assigned",
    "clarification_requested",
    "clarification_answered",
    "needs_decision",
    "accepted",
    "in_progress",
    "submitted",
    "completed",
    "failed",
    "canceled",
}
_TASK_CONTROL_STATUSES = {
    "active",
    "pause_requested",
    "paused",
    "awaiting_human",
    "cancel_requested",
    "canceled",
}
_TASK_KINDS = {"general", "development", "review", "test", "rework"}
_TASK_REVIEW_POLICIES = {"required", "batch", "exempt"}
_TASK_RELATION_TYPES = {"reviews", "tests", "reworks"}
_TASK_REVIEW_VERDICTS = {"approved", "changes_requested", "blocked"}
_TASK_TEST_VERDICTS = {"passed", "failed", "blocked"}
_TASK_CHECKPOINT_REASONS = {
    "batch_limit",
    "risk_boundary",
    "milestone",
    "time_limit",
    "usage_limit",
    "review_exhausted",
    "needs_decision",
}
_SCHEDULE_STATUSES = {"active", "paused", "completed", "canceled"}
TASK_LEASE_DEFAULT_SECONDS = 120
TASK_LEASE_MIN_SECONDS = 5
TASK_LEASE_MAX_SECONDS = 3600


class AgentTaskCreate(BaseModel):
    target_member_id: str
    content: str
    title: Optional[str] = None
    task_kind: str = "general"
    review_policy: Optional[str] = None
    related_task_ids: list[int] = PydField(default_factory=list)
    trigger_task_id: Optional[int] = PydField(default=None, ge=1)
    project_id: Optional[str] = None
    parent_task_id: Optional[int] = PydField(default=None, ge=1)
    authorization_epoch: Optional[int] = PydField(default=None, ge=0)
    may_delegate: bool = False
    max_delegation_depth: Optional[int] = PydField(default=None, ge=0, le=8)
    max_running_descendants: Optional[int] = PydField(default=None, ge=1, le=32)
    max_running_per_target: Optional[int] = PydField(default=None, ge=1, le=32)
    max_nonterminal_descendants: Optional[int] = PydField(default=None, ge=1, le=128)
    slice_budget: Optional[int] = PydField(
        default=None,
        ge=1,
        le=TASK_AUTHORIZED_SLICE_BUDGET_MAX,
    )
    authorization_ttl_seconds: Optional[int] = PydField(
        default=None,
        ge=TASK_AUTHORIZATION_TTL_MIN_SECONDS,
        le=TASK_AUTHORIZATION_TTL_MAX_SECONDS,
    )
    milestone_test_required: bool = False
    max_clarification_rounds: int = PydField(
        default=TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT,
        ge=TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT,
        le=TASK_MAX_CLARIFICATION_ROUNDS_LIMIT,
    )
    # 292：可选执行会话元数据；缺失/None 时任务创建与执行完全保持旧行为。
    # 详细严格校验在 server/execution_session_tasks.py（路由层）完成。
    execution_session: Optional[dict] = None

    @model_validator(mode="after")
    def validate_task_create(self) -> "AgentTaskCreate":
        self.target_member_id = self.target_member_id.strip()
        self.content = self.content.strip()
        if self.title is not None:
            self.title = self.title.strip() or None
        if self.project_id is not None:
            self.project_id = self.project_id.strip() or None
        self.task_kind = self.task_kind.strip().lower()
        if self.task_kind not in _TASK_KINDS:
            raise ValueError(f"task_kind must be one of {sorted(_TASK_KINDS)}")
        if self.review_policy is not None:
            self.review_policy = self.review_policy.strip().lower() or None
        if self.review_policy is not None and self.review_policy not in _TASK_REVIEW_POLICIES:
            raise ValueError(
                f"review_policy must be one of {sorted(_TASK_REVIEW_POLICIES)}"
            )
        self.related_task_ids = list(dict.fromkeys(self.related_task_ids))
        if any(task_id < 1 for task_id in self.related_task_ids):
            raise ValueError("related_task_ids must contain positive task ids")
        if not self.target_member_id:
            raise ValueError("target_member_id is required")
        if not self.content:
            raise ValueError("content is required")
        if self.parent_task_id is None and self.task_kind != "general":
            raise ValueError(
                "development, review, test, and rework are only valid for child tasks"
            )
        if self.task_kind == "development":
            self.review_policy = self.review_policy or "required"
        elif self.task_kind == "rework":
            if self.review_policy not in {None, "required"}:
                raise ValueError("rework tasks require review_policy=required")
            self.review_policy = "required"
        elif self.review_policy is not None:
            raise ValueError(
                "review_policy is only valid for development and rework tasks"
            )
        if self.task_kind in {"general", "development"}:
            if self.related_task_ids or self.trigger_task_id is not None:
                raise ValueError(
                    "related_task_ids and trigger_task_id are only valid for quality tasks"
                )
        elif self.task_kind in {"review", "test"}:
            if not self.related_task_ids:
                raise ValueError(f"{self.task_kind} tasks require related_task_ids")
            if self.trigger_task_id is not None:
                raise ValueError(
                    f"trigger_task_id is not valid for {self.task_kind} tasks"
                )
        elif self.task_kind == "rework":
            if len(self.related_task_ids) != 1 or self.trigger_task_id is None:
                raise ValueError(
                    "rework tasks require exactly one original development task and a trigger_task_id"
                )
        if self.parent_task_id is not None and any(
            value is not None
            for value in (
                self.max_delegation_depth,
                self.max_running_descendants,
                self.max_running_per_target,
                self.max_nonterminal_descendants,
                self.slice_budget,
                self.authorization_ttl_seconds,
            )
        ):
            raise ValueError("child tasks inherit governance and authorization limits from their root task")
        if self.parent_task_id is not None and self.milestone_test_required:
            raise ValueError("milestone_test_required is only valid for root tasks")
        if self.milestone_test_required and not self.may_delegate:
            raise ValueError("milestone_test_required requires may_delegate=true")

        if self.parent_task_id is None and self.authorization_epoch is not None:
            raise ValueError("authorization_epoch is only valid when creating a child task")
        if self.parent_task_id is not None and self.authorization_epoch is None:
            raise ValueError("child task creation requires the current authorization_epoch")

        if not self.may_delegate and (
            self.slice_budget is not None or self.authorization_ttl_seconds is not None
        ):
            raise ValueError("slice authorization requires may_delegate=true")

        max_running = self.max_running_descendants or TASK_MAX_RUNNING_DESCENDANTS_DEFAULT
        max_per_target = self.max_running_per_target or TASK_MAX_RUNNING_PER_TARGET_DEFAULT
        max_nonterminal = self.max_nonterminal_descendants or TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT
        if self.max_delegation_depth == 0 and self.may_delegate:
            raise ValueError("may_delegate requires max_delegation_depth greater than zero")
        if max_per_target > max_running:
            raise ValueError("max_running_per_target cannot exceed max_running_descendants")
        if max_running > max_nonterminal:
            raise ValueError("max_running_descendants cannot exceed max_nonterminal_descendants")
        return self


class AgentTaskClaim(BaseModel):
    instance_id: Optional[str] = None
    lease_seconds: int = Field(
        default=TASK_LEASE_DEFAULT_SECONDS,
        ge=TASK_LEASE_MIN_SECONDS,
        le=TASK_LEASE_MAX_SECONDS,
    )

    @model_validator(mode="after")
    def validate_task_claim(self) -> "AgentTaskClaim":
        if self.instance_id is not None:
            self.instance_id = self.instance_id.strip() or None
        return self


class AgentTaskHeartbeat(BaseModel):
    claim_token: str
    lease_seconds: int = Field(
        default=TASK_LEASE_DEFAULT_SECONDS,
        ge=TASK_LEASE_MIN_SECONDS,
        le=TASK_LEASE_MAX_SECONDS,
    )

    @model_validator(mode="after")
    def validate_task_heartbeat(self) -> "AgentTaskHeartbeat":
        self.claim_token = self.claim_token.strip()
        if not self.claim_token:
            raise ValueError("claim_token is required")
        return self


class AgentTaskGateVerdict(BaseModel):
    verdict: str
    summary: str
    findings: list[str] = PydField(default_factory=list)

    @model_validator(mode="after")
    def validate_gate_verdict(self) -> "AgentTaskGateVerdict":
        self.verdict = self.verdict.strip().lower()
        self.summary = self.summary.strip()
        self.findings = [
            finding.strip()
            for finding in self.findings
            if finding.strip()
        ]
        if not self.verdict:
            raise ValueError("gate verdict is required")
        if not self.summary:
            raise ValueError("gate verdict summary is required")
        return self


class AgentTaskFollowupCreate(AgentTaskCreate):
    expected_mode_version: int = PydField(strict=True, ge=0)
    followup_task_ids: list[int] = PydField(default_factory=list, max_length=20)

    @field_validator("followup_task_ids", mode="before")
    @classmethod
    def strict_followup_ids(cls, value):
        if not isinstance(value, list) or any(type(i) is not int or not 0 < i <= 2**53-1 for i in value):
            raise ValueError("followup_task_ids must contain only positive safe integers")
        return value


class AgentTaskFollowupCollect(BaseModel):
    """Atomic active-creator collection guard; legacy manual collection unchanged."""
    expected_result_message_id: int = PydField(strict=True, gt=0)
    expected_content_sha256: str = PydField(pattern=r"^[0-9a-f]{64}$")
    expected_mode_version: int = PydField(strict=True, ge=0)


class AgentTaskComplete(BaseModel):
    status: str
    result_message_id: Optional[int] = None
    last_error: Optional[str] = None
    claim_token: Optional[str] = None
    gate_verdict: Optional[AgentTaskGateVerdict] = None
    execution_session_state: Optional[dict] = None

    @model_validator(mode="after")
    def validate_task_complete(self) -> "AgentTaskComplete":
        self.status = self.status.strip().lower()
        if self.status not in _TASK_TERMINAL_STATUSES:
            raise ValueError(f"status must be one of {sorted(_TASK_TERMINAL_STATUSES)}")
        if self.last_error is not None:
            self.last_error = self.last_error.strip() or None
        if self.claim_token is not None:
            self.claim_token = self.claim_token.strip() or None
        if self.status == "failed" and not self.last_error:
            raise ValueError("last_error is required when status is failed")
        return self


class AgentTaskTreeResume(BaseModel):
    slice_budget: int = PydField(ge=0, le=TASK_AUTHORIZED_SLICE_BUDGET_MAX)
    authorization_ttl_seconds: int = PydField(
        default=TASK_AUTHORIZATION_TTL_DEFAULT_SECONDS,
        ge=TASK_AUTHORIZATION_TTL_MIN_SECONDS,
        le=TASK_AUTHORIZATION_TTL_MAX_SECONDS,
    )


class AgentTaskTreeCheckpoint(BaseModel):
    reason: str

    @model_validator(mode="after")
    def validate_checkpoint_reason(self) -> "AgentTaskTreeCheckpoint":
        self.reason = self.reason.strip().lower()
        if self.reason not in _TASK_CHECKPOINT_REASONS:
            raise ValueError(f"reason must be one of {sorted(_TASK_CHECKPOINT_REASONS)}")
        return self


class AgentTaskClarificationRequest(BaseModel):
    question_message_id: Optional[int] = PydField(default=None, ge=1)


class AgentTaskClarificationAnswer(BaseModel):
    answer_message_id: int = PydField(ge=1)


class AgentTaskClarificationDecision(BaseModel):
    allow_additional_round: bool = False


class AgentTaskClarificationRoundOut(BaseModel):
    id: int
    task_id: int
    round_index: int
    status: str
    question_message_id: int
    answer_start_message_id: Optional[int]
    answer_end_message_id: Optional[int]
    requested_at: datetime
    answered_at: Optional[datetime]


class AgentTaskOut(BaseModel):
    id: int
    schedule_id: Optional[int]
    project_id: Optional[str]
    hall_group_id: Optional[str]
    parent_task_id: Optional[int]
    root_task_id: Optional[int]
    delegation_depth: int
    may_delegate: bool
    max_delegation_depth: Optional[int]
    max_running_descendants: Optional[int]
    max_running_per_target: Optional[int]
    max_nonterminal_descendants: Optional[int]
    control_status: Optional[str]
    authorization_epoch: Optional[int]
    authorized_slice_budget: Optional[int]
    reserved_slice_count: Optional[int]
    authorization_expires_at: Optional[datetime]
    checkpoint_reason: Optional[str]
    milestone_test_required: bool
    max_clarification_rounds: int
    clarification_round_count: int
    target_member_id: str
    created_by: str
    content: str
    title: Optional[str]
    task_kind: str
    review_policy: Optional[str]
    gate_verdict: Optional[dict]
    status: str
    workflow_status: str
    attempt: int
    claimed_by: Optional[str]
    instance_id: Optional[str]
    lease_expires_at: Optional[datetime]
    heartbeat_at: Optional[datetime]
    result_message_id: Optional[int]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    claimed_at: Optional[datetime]
    finished_at: Optional[datetime]
    result_collected_at: Optional[datetime]
    # ROLE-BINDING-B1b：只读输出；旧任务为 None 表示“未记录（legacy_unrecorded）”，
    # 不接收客户端写入，也不得推断成 unconfigured 或某个模型值（合同 §7.4/§10）。
    target_binding_snapshot: Optional[dict]
    target_binding_state: Optional[str]
    execution_session: Optional[dict] = None
    execution_session_state: Optional[dict] = None


class AgentTaskClaimOut(AgentTaskOut):
    claim_token: str


class ExecutionSessionBaseOut(BaseModel):
    """基础合同只读响应：只对同一基础任务/续接任务的参与者返回。"""

    task_id: int
    continuity_key: str
    project_id: str
    requester_id: str
    target_member_id: str
    base_contract_version: str
    base_contract_sha256: str
    base_context: str
    binding_fingerprint: str
    workspace_root: str
    workspace_identity: str


class AgentTaskRelationOut(BaseModel):
    id: int
    source_task_id: int
    target_task_id: int
    relation_type: str
    trigger_task_id: Optional[int]
    round_index: Optional[int]
    created_at: datetime


class AgentTaskReviewGateOut(BaseModel):
    development_task_id: int
    current_subject_task_id: int
    review_policy: str
    current_verdict: Optional[dict]
    review_task_id: Optional[int]
    rework_round: int


class AgentTaskTestGateOut(BaseModel):
    required: bool
    frozen_task_ids: list[int] = PydField(default_factory=list)
    test_task_id: Optional[int]
    current_verdict: Optional[dict]
    satisfied: bool


class AgentTaskQualityContextItem(BaseModel):
    relation: AgentTaskRelationOut
    task: AgentTaskOut
    messages: list[MessageOut]


class AgentTaskQualityContextOut(BaseModel):
    task_id: int
    relations: list[AgentTaskRelationOut]
    related_tasks: list[AgentTaskQualityContextItem]
    trigger_tasks: list[AgentTaskQualityContextItem]


class AgentTaskTreeOut(BaseModel):
    root: AgentTaskOut
    tasks: list[AgentTaskOut]
    running_descendants: int
    nonterminal_descendants: int
    remaining_slice_budget: int
    authorization_expired: bool
    relations: list[AgentTaskRelationOut] = PydField(default_factory=list)
    review_gates: list[AgentTaskReviewGateOut] = PydField(default_factory=list)
    test_gate: AgentTaskTestGateOut


class AgentTaskScheduleCreate(BaseModel):
    target_member_id: str
    content: str
    title: Optional[str] = None
    run_at: Optional[datetime] = None
    interval_seconds: Optional[int] = None

    @model_validator(mode="after")
    def validate_schedule_create(self) -> "AgentTaskScheduleCreate":
        self.target_member_id = self.target_member_id.strip()
        self.content = self.content.strip()
        if self.title is not None:
            self.title = self.title.strip() or None
        if not self.target_member_id:
            raise ValueError("target_member_id is required")
        if not self.content:
            raise ValueError("content is required")
        if self.interval_seconds is not None and self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")
        return self


class AgentTaskScheduleUpdate(BaseModel):
    status: str

    @model_validator(mode="after")
    def validate_schedule_update(self) -> "AgentTaskScheduleUpdate":
        self.status = self.status.strip().lower()
        if self.status not in {"active", "paused", "canceled"}:
            raise ValueError("status must be one of ['active', 'canceled', 'paused']")
        return self


class AgentTaskScheduleOut(BaseModel):
    id: int
    target_member_id: str
    created_by: str
    content: str
    title: Optional[str]
    schedule_type: str
    status: str
    next_run_at: datetime
    interval_seconds: Optional[int]
    last_run_at: Optional[datetime]
    last_task_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class AgentTaskScheduleRunOut(BaseModel):
    created_tasks: list[AgentTaskOut]
    updated_schedules: list[AgentTaskScheduleOut]


class ProjectCreate(BaseModel):
    project_id: Optional[str] = None  # CLI generates; server fills if omitted
    display_name: str
    description: Optional[str] = None
    project_root_path: Optional[str] = None
    development_requirements: Optional[str] = None
    maintainer_member_id: Optional[str] = None  # defaults to the registering member

    @model_validator(mode="after")
    def validate_project_create(self) -> "ProjectCreate":
        if self.project_id is not None:
            self.project_id = self.project_id.strip() or None
            if self.project_id is not None and any(ch.isspace() for ch in self.project_id):
                raise ValueError("project_id cannot contain whitespace")
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("display_name is required")
        if self.description is not None:
            self.description = self.description.strip() or None
        if self.project_root_path is not None:
            self.project_root_path = self.project_root_path.strip() or None
        self.development_requirements = normalize_development_requirements(
            self.development_requirements
        )
        if self.maintainer_member_id is not None:
            self.maintainer_member_id = self.maintainer_member_id.strip() or None
        return self


class ProjectUpdate(BaseModel):
    """Partial update — only fields explicitly provided are applied."""

    display_name: Optional[str] = None
    description: Optional[str] = None
    project_root_path: Optional[str] = None
    development_requirements: Optional[str] = None

    @model_validator(mode="after")
    def validate_project_update(self) -> "ProjectUpdate":
        if "display_name" in self.model_fields_set:
            if self.display_name is None or not self.display_name.strip():
                raise ValueError("display_name cannot be empty")
            self.display_name = self.display_name.strip()
        if "description" in self.model_fields_set and self.description is not None:
            self.description = self.description.strip() or None
        if "project_root_path" in self.model_fields_set and self.project_root_path is not None:
            self.project_root_path = self.project_root_path.strip() or None
        # 只有显式提供该字段才校验；“明确空文本或 null”视为清空，省略则保持原值。
        if "development_requirements" in self.model_fields_set:
            self.development_requirements = normalize_development_requirements(
                self.development_requirements
            )
        return self


class ProjectOut(BaseModel):
    project_id: str
    display_name: str
    description: Optional[str]
    project_root_path: Optional[str]
    development_requirements: Optional[str] = None
    # 模式“意向”与版本（C1a）：只读暴露保存值，不表示会话已生效/已授权。
    controller_mode: str = PROJECT_CONTROLLER_MODE_DEFAULT
    controller_mode_version: int = 0
    # 长期主控指定（C1b-S1）：保存的成员 ID 与独立版本，外加**实时计算**的配置有效性状态。
    # 状态只反映名册/成员事实，不表示在线、ACK、会话生效或授权。
    controller_member_id: Optional[str] = None
    controller_assignment_version: int = 0
    controller_assignment_status: str = PROJECT_ASSIGNMENT_UNASSIGNED
    maintainer_member_id: str
    created_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_orm_project(cls, project: Project, *, session: Session) -> "ProjectOut":
        """构造项目输出。

        ``session`` 必须由调用方传入：``controller_assignment_status`` 需要按当前
        名册与成员事实实时计算，不能靠项目行自己推断（否则会谎报“已指定有效”）。
        """
        return cls(
            project_id=project.project_id,
            display_name=project.display_name,
            description=project.description,
            project_root_path=project.project_root_path,
            development_requirements=project.development_requirements,
            controller_mode=project.controller_mode or PROJECT_CONTROLLER_MODE_DEFAULT,
            controller_mode_version=project.controller_mode_version or 0,
            controller_member_id=project.controller_member_id or None,
            controller_assignment_version=project.controller_assignment_version or 0,
            controller_assignment_status=resolve_controller_assignment_status(
                project, session
            ),
            maintainer_member_id=project.maintainer_member_id,
            created_at=project.created_at,
            last_seen_at=project.last_seen_at,
        )


class ProjectControllerModeUpdate(BaseModel):
    """`PATCH /api/projects/{project_id}/controller-mode` 请求体（C1a）。

    专用配置入口，与普通项目元数据 ``ProjectUpdate`` 分离：

    - ``mode``：保存的模式意向，只接受 ``passive`` / ``active``；
    - ``expected_version``：调用者读到的模式版本，必须显式提供（缺省即拒绝），
      取值非负且不超过 SQLite 有符号 64 位上界，超界在请求校验层 422。

    服务端在数据库写入层按 ``expected_version`` 做条件更新（CAS）：
    版本不匹配返回 409，合法同值请求返回 200 且不递增版本。
    """

    mode: str
    # strict：字符串 "0"、小数、布尔等一律拒绝，避免"类型不合法"被静默强转后当成有效版本。
    # le：加 SQLite 64 位上界，超界值（如 2**63）在进入写入层前就 422，而不是绑定报 500。
    expected_version: int = PydField(ge=0, le=SQLITE_SIGNED_INTEGER_MAX, strict=True)

    @model_validator(mode="after")
    def validate_controller_mode(self) -> "ProjectControllerModeUpdate":
        if self.mode not in PROJECT_CONTROLLER_MODES:
            raise ValueError(
                f"mode must be one of {list(PROJECT_CONTROLLER_MODES)}"
            )
        return self


class ProjectControllerAssignmentUpdate(BaseModel):
    """`PATCH /api/projects/{project_id}/controller-assignment` 请求体（C1b-S1）。

    专用配置入口，与普通项目元数据 ``ProjectUpdate`` 分离：

    - ``member_id``：**必填键**，取值是项目内具体成员 ID（字符串，去首尾空白）或显式 ``null``；
      ``null`` 表示解除指定，空字符串/全空白不是解除而是 422，缺失该键同样 422；
    - ``expected_version``：调用者读到的 ``controller_assignment_version``，必须显式提供，
      取值非负且不超过 SQLite 有符号 64 位上界，超界在请求校验层 422。

    服务端在数据库写入层按 ``expected_version`` 做条件更新（CAS）：版本不匹配返回 409，
    合法同值请求返回 200 且不递增版本；已有其他非 null 指定时不能直接覆盖，必须先显式解除。
    """

    # 无默认值 = 必填键，但允许显式 null（Pydantic v2 中 Optional 无默认即 required but nullable）。
    member_id: Optional[str]
    expected_version: int = PydField(ge=0, le=SQLITE_SIGNED_INTEGER_MAX, strict=True)

    @model_validator(mode="after")
    def validate_controller_assignment(self) -> "ProjectControllerAssignmentUpdate":
        self.member_id = normalize_controller_member_id(self.member_id)
        return self


class ProjectAgentEntry(BaseModel):
    """One agent's profile paths in a sync payload."""

    member_id: str
    identity_path: Optional[str] = None
    soul_path: Optional[str] = None
    user_path: Optional[str] = None
    memory_pointer: Optional[str] = None
    business_role: Optional[str] = None
    # 已弃用兼容字段：旧名册同步仍可携带并原样存储，但不再参与身份/权限/协调判定
    # （R1-2 补正 F7）。
    decision_tier: Optional[str] = PydField(default=None, deprecated=True)
    capability_summary: list[str] = PydField(default_factory=list)

    @model_validator(mode="after")
    def validate_entry(self) -> "ProjectAgentEntry":
        self.member_id = self.member_id.strip()
        if not self.member_id:
            raise ValueError("member_id is required")
        for field in ("identity_path", "soul_path", "user_path", "memory_pointer"):
            value = getattr(self, field)
            if value is not None:
                setattr(self, field, value.strip() or None)
        if self.business_role is not None:
            self.business_role = self.business_role.strip() or None
        if self.decision_tier is not None:
            self.decision_tier = self.decision_tier.strip().lower() or None
            if (
                self.decision_tier is not None
                and self.decision_tier not in _DECISION_TIERS
            ):
                raise ValueError(
                    f"decision_tier must be one of {sorted(_DECISION_TIERS)}"
                )
        self.capability_summary = list(
            dict.fromkeys(
                capability.strip()
                for capability in self.capability_summary
                if capability.strip()
            )
        )
        return self


class ProjectSyncRequest(BaseModel):
    """`POST /api/projects/{id}/sync` body — full replace of the agent index."""

    agents: list[ProjectAgentEntry] = []

    @model_validator(mode="after")
    def validate_sync(self) -> "ProjectSyncRequest":
        seen: set[str] = set()
        for entry in self.agents:
            if entry.member_id in seen:
                raise ValueError(f"duplicate member_id in sync payload: {entry.member_id}")
            seen.add(entry.member_id)
        return self


class RunnerCreate(BaseModel):
    """``POST /api/runners`` 请求体（合同 §3.4）。

    ``extra="forbid"``：出现未知字段 → 422，不做静默忽略；``runner_id`` / ``runtime``
    在此登记后不可改（更新走 ``RunnerUpdate``，出现这两个键同样 422）。
    """

    model_config = ConfigDict(extra="forbid")

    runner_id: str
    runtime: str
    display_name: str
    adapter_status: str = RUNNER_ADAPTER_STATUS_DEFAULT
    adapter_note: Optional[str] = None
    capabilities: list[str] = PydField(default_factory=list)

    @model_validator(mode="after")
    def validate_runner_create(self) -> "RunnerCreate":
        self.runner_id = normalize_runner_id(self.runner_id)
        self.runtime = normalize_runner_runtime(self.runtime)
        self.display_name = normalize_runner_display_name(self.display_name)
        self.adapter_status = normalize_runner_adapter_status(self.adapter_status)
        self.adapter_note = normalize_runner_adapter_note(self.adapter_note)
        self.capabilities = normalize_runner_capabilities(list(self.capabilities))
        return self


class RunnerUpdate(BaseModel):
    """``PATCH /api/runners/{runner_id}`` 请求体（合同 §3.4）。

    只允许改 ``display_name`` / ``adapter_status`` / ``adapter_note`` / ``capabilities``；
    出现 ``runner_id`` 或 ``runtime``（或任何未知字段）→ 422，避免已冻结快照与登记事实分叉。
    省略的字段保持原值；显式 ``null`` 的 ``adapter_note`` 表示清空说明。
    """

    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = None
    adapter_status: Optional[str] = None
    adapter_note: Optional[str] = None
    capabilities: Optional[list[str]] = None

    @model_validator(mode="after")
    def validate_runner_update(self) -> "RunnerUpdate":
        fields = self.model_fields_set
        if "display_name" in fields:
            if self.display_name is None:
                raise ValueError("display_name cannot be null")
            self.display_name = normalize_runner_display_name(self.display_name)
        if "adapter_status" in fields:
            if self.adapter_status is None:
                raise ValueError("adapter_status cannot be null")
            self.adapter_status = normalize_runner_adapter_status(self.adapter_status)
        if "adapter_note" in fields:
            self.adapter_note = normalize_runner_adapter_note(self.adapter_note)
        if "capabilities" in fields:
            if self.capabilities is None:
                raise ValueError("capabilities cannot be null")
            self.capabilities = normalize_runner_capabilities(list(self.capabilities))
        return self


class RunnerOut(BaseModel):
    """运行器登记输出（合同 §3.4）。只描述登记事实，不代表在线或可用。"""

    runner_id: str
    runtime: str
    display_name: str
    adapter_status: str
    adapter_note: Optional[str]
    capabilities: list[str]
    # 角色生命周期 R1-1 附加字段：旧键一个不减/不改名，只新增控制能力分类。
    control_kind: str = RUNNER_CONTROL_KIND_DEFAULT
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_runner(cls, runner: RunnerRegistry) -> "RunnerOut":
        return cls(
            runner_id=runner.runner_id,
            runtime=runner.runtime,
            display_name=runner.display_name,
            adapter_status=runner.adapter_status,
            adapter_note=runner.adapter_note,
            capabilities=list(runner.capabilities or []),
            control_kind=runner.control_kind or RUNNER_CONTROL_KIND_DEFAULT,
            created_by=runner.created_by,
            created_at=runner.created_at,
            updated_at=runner.updated_at,
        )


class RunnerControlKindUpdate(BaseModel):
    """``PATCH /api/runners/{runner_id}/control-kind`` 请求体（合同 §5.1）。

    独立入口：避免与既有 ``PATCH /api/runners/{id}`` 的四字段白名单冲突。
    只声明控制来源，不代表已核验或允许启动。
    """

    model_config = ConfigDict(extra="forbid")

    control_kind: str

    @model_validator(mode="after")
    def validate_control_kind(self) -> "RunnerControlKindUpdate":
        self.control_kind = normalize_runner_control_kind(self.control_kind)
        return self


class RunnerModelChoiceCreate(BaseModel):
    """``POST /api/runners/{runner_id}/model-choices`` 请求体（合同 §4.1.1）。

    ``model_alias`` 属于**选择维度**：空/缺省 = 空串（该运行器不支持或不指定显式 alias）。
    命中既有选择维度时只更新展示/来源字段；试图改动维度由路由映射
    ``409 choice_dimension_immutable``。

    字段值归一化刻意放在路由层：路由需要读取**原始** ``model_fields_set`` 才能区分
    “显式提供”与“缺省”，避免 pydantic 校验器赋值污染该集合。
    """

    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_source: str
    provider_id: str
    connection_ref: str
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None
    source_kind: Optional[str] = None
    capabilities: Optional[list[str]] = None


class RunnerModelChoiceUpdate(BaseModel):
    """``PATCH /api/runners/{runner_id}/model-choices/{choice_id}`` 请求体（合同 §4.1.1）。

    只允许改 ``model_display_name``/``capabilities``/``source_kind``/``retired_at``。
    选择维度字段被**接受**但一律 409 ``choice_dimension_immutable``（客户端应改为新建
    选择），其它未知字段 422。
    """

    model_config = ConfigDict(extra="forbid")

    model_id: Optional[str] = None
    model_source: Optional[str] = None
    provider_id: Optional[str] = None
    connection_ref: Optional[str] = None
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None
    capabilities: Optional[list[str]] = None
    source_kind: Optional[str] = None
    retired_at: Optional[datetime] = None


class RunnerModelChoiceOut(BaseModel):
    """模型选择输出（合同 §4.1.1）。只描述登记事实，不代表模型在线或可用。"""

    choice_id: str
    runner_id: str
    model_id: str
    model_source: str
    provider_id: str
    connection_ref: str
    model_alias: str
    model_display_name: Optional[str]
    source_kind: str
    capabilities: list[str]
    retired_at: Optional[datetime]
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_choice(cls, choice: RunnerModelChoice) -> "RunnerModelChoiceOut":
        return cls(
            choice_id=choice.choice_id,
            runner_id=choice.runner_id,
            model_id=choice.model_id,
            model_source=choice.model_source,
            provider_id=choice.provider_id,
            connection_ref=choice.connection_ref,
            model_alias=choice.model_alias or "",
            model_display_name=choice.model_display_name,
            source_kind=choice.source_kind,
            capabilities=list(choice.capabilities or []),
            retired_at=choice.retired_at,
            created_by=choice.created_by,
            created_at=choice.created_at,
            updated_at=choice.updated_at,
        )


class ProjectRoleCreate(BaseModel):
    """``POST /api/projects/{project_id}/roles`` 请求体（合同 §5.2 / §7.2）。

    ``role_name`` 的“非空/长度”校验与 ``operation_key`` 归一化刻意放在路由层，以便返回
    稳定码 ``422 role_name_invalid``（而不是通用校验错误）；``operation_key`` 必填且由
    调用方显式提供（禁止由名称/模型派生）。
    """

    model_config = ConfigDict(extra="forbid")

    role_name: str
    runner_id: str
    choice_id: str
    role_description: Optional[str] = None
    operation_key: str
    #: R1-4a：`operation_key` 命中 create 意图时，必须携带该意图的当前租约 token
    #: （见 REQUEST_CONTRACT §6）。旧调用方不传 = 不存在请求来源，保持 R1-1 行为。
    lease_token: Optional[str] = None


class ProjectRoleLegacyAttach(BaseModel):
    """``POST /api/projects/{project_id}/roles/legacy-attach`` 请求体。

    ROLE_LEGACY_ATTACH_DESIGN §接口与保留事实：严格只含 ``member_id`` / ``runner_id`` /
    ``choice_id`` / ``operation_key``。``extra="forbid"`` 拒绝 ``api_key``、``auto_start``、
    ``role_name``、``role_description`` 等任何额外字段：补录只登记**已有身份**，不生成/轮换
    Key、不改名、不写说明、不启动服务。字段值归一化放在路由层，以便返回稳定错误码。
    """

    model_config = ConfigDict(extra="forbid")

    member_id: str
    runner_id: str
    choice_id: str
    operation_key: str


class ProjectRoleUpdate(BaseModel):
    """``PATCH /api/projects/{project_id}/roles/{member_id}`` 请求体（合同 §5.2）。

    - ``role_name``：只改项目内角色名，**默认不动** ``members.display_name``；
    - ``role_description``：显式 ``null`` = 清除自定义说明；缺省 = 不修改；
    - ``review_exempt``：复核豁免**只能**由 human 经本入口授予/撤销；
    - 未知字段 → 422（``extra="forbid"``），不接受任何 agent 自建/自授入口。

    字段值归一化放在路由层：路由需要读取**原始** ``model_fields_set`` 才能区分
    “显式 ``null``”与“缺省”。
    """

    model_config = ConfigDict(extra="forbid")

    role_name: Optional[str] = None
    role_description: Optional[str] = None
    review_exempt: Optional[bool] = None


class ProjectRoleRunnerOut(BaseModel):
    """角色投影里的运行器部分（只读展示；不返回路径/argv/凭据）。"""

    runner_id: Optional[str] = None
    runtime: Optional[str] = None
    display_name: Optional[str] = None
    status: Optional[str] = None


class ProjectRoleModelOut(BaseModel):
    """角色投影里的模型部分（合同 §5.2 的 ``choice_id`` 可信来源）。

    ``choice_id`` 只来自创建操作映射且与当前绑定六维一致；失配/老名册一律 ``null``，
    并给出 ``choice_source`` 与 ``choice_binding_mismatch`` 说明，**不**按 model_id 猜。
    """

    choice_id: Optional[str] = None
    choice_source: str = CHOICE_SOURCE_LEGACY_MANUAL
    choice_binding_mismatch: bool = False
    model_id: Optional[str] = None
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None


class ProjectRoleServiceLaunchOut(BaseModel):
    """当前动作的公开只读投影（**不含**任何 token / 哈希 / 命令正文）。"""

    launch_id: str
    action: str
    state: str
    expected_instance_id: str
    launch_expires_at: datetime
    claimed_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    outcome: Optional[str] = None
    error_code: Optional[str] = None


class ProjectRoleServiceOut(BaseModel):
    """角色服务投影（R1-3 实现；合同 §3 / §5.2 / §11.2）。

    公开只读面：**不**返回 ``owner_token``/``claim_token``、argv、绝对路径或任何 Key。
    三个独立事实（``native_login`` / ``model_alias`` / ``readiness_service``）分列，
    不合并成一个假的 ``ready``。
    """

    desired: Optional[str] = None
    observed: Optional[str] = None
    last_action: Optional[str] = None
    last_result: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    control_kind: Optional[str] = None
    manager_kind: Optional[str] = None
    generation: int = 0
    current_launch: Optional[ProjectRoleServiceLaunchOut] = None
    observed_instance_id: Optional[str] = None
    native_login: str = ROLE_SERVICE_NATIVE_LOGIN_UNVERIFIED
    model_alias: str = ROLE_SERVICE_MODEL_ALIAS_UNCONFIGURED
    readiness_service: str = ROLE_SERVICE_READINESS_PENDING
    can_start: bool = False
    can_stop: bool = False
    #: 原 start 的进程归属是否仍未释放（失败/过期/unknown 也可能仍持有活进程）。
    #: 公开面只暴露布尔事实，不含 pid 之外的任何宿主内部记录。
    ownership_held: bool = False
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RoleServiceLaunchCommandOut(BaseModel):
    """claim 返回的**受限**启动事实（合同 §5.3）。

    只含合同字段：``action``/``runtime``/``runner_id``/``model_alias``/``project_root``/
    ``member_id``；**不**下发任意 shell 正文。宿主用本地登记的运行器入口组装 argv。
    """

    action: str
    runtime: Optional[str] = None
    runner_id: Optional[str] = None
    model_alias: Optional[str] = None
    project_root: Optional[str] = None
    member_id: str
    project_id: str


class RoleServiceLaunchClaimOut(BaseModel):
    """``POST /api/role-service-launches/{id}/claim`` 响应（合同 §5.3）。

    ``owner_token`` 只在 **start** claim 返回一次；stop 只返回新的 ``claim_token``。
    库里只存哈希，公共 GET/页面/日志不返回任何 token。
    """

    launch_id: str
    project_id: str
    member_id: str
    action: str
    generation: int
    expected_instance_id: str
    state: str
    claimed_at: datetime
    launch_expires_at: datetime
    claim_host: Optional[str] = None
    owner_token: Optional[str] = None
    claim_token: str
    command: RoleServiceLaunchCommandOut


class RoleServiceLaunchReportOut(BaseModel):
    """``POST /api/role-service-launches/{id}/report`` 的只读 receipt。

    重放同一完整载荷时**只读**返回本 receipt，即使已过截止也不改当前状态。
    """

    launch_id: str
    project_id: str
    member_id: str
    action: str
    generation: int
    state: str
    outcome: Optional[str] = None
    instance_id: Optional[str] = None
    error_code: Optional[str] = None
    reported_at: Optional[datetime] = None
    observed_state: Optional[str] = None
    replayed: bool = False


class RoleServiceLaunchClaimRequest(BaseModel):
    """claim 请求体（合同 §5.3）：``{host, expected_instance_id, owner_token?}``。"""

    model_config = ConfigDict(extra="forbid")

    host: str
    expected_instance_id: str
    owner_token: Optional[str] = None


class RoleServiceLaunchReportRequest(BaseModel):
    """report 请求体（合同 §5.3）。

    ``extra="forbid"``；未知字段 422。校验顺序与稳定错误码全部在服务层实现。

    ``spawned``（R1-3 返修新增，可选、向后兼容）是宿主对 ``start`` 失败的可验证区分：
    ``true`` = 已 spawn（失败不释放原所有权），``false`` = 纯预检失败（可安全释放）。
    旧宿主不传时按 ``pid is not None`` 回退判断。
    """

    model_config = ConfigDict(extra="forbid")

    generation: int
    action: str
    claim_token: str
    owner_token: Optional[str] = None
    outcome: str
    instance_id: Optional[str] = None
    pid: Optional[int] = None
    process_started_at: Optional[datetime] = None
    host: str
    error_code: Optional[str] = None
    spawned: Optional[bool] = None


class RoleServiceStartOut(BaseModel):
    """``POST .../service/start`` 响应（合同 §5.3）：**不返回任何 token**。"""

    project_id: str
    member_id: str
    role_name: Optional[str] = None
    launch_id: str
    generation: int
    action: str = ROLE_SERVICE_ACTION_START
    expected_instance_id: str
    launch_expires_at: datetime
    desired: str = ROLE_SERVICE_DESIRED_RUNNING
    observed: str = ROLE_SERVICE_OBSERVED_STARTING


class RoleServiceStopOut(BaseModel):
    """``POST .../service/stop`` 响应（合同 §5.3）。"""

    project_id: str
    member_id: str
    role_name: Optional[str] = None
    launch_id: Optional[str] = None
    generation: int
    action: str = ROLE_SERVICE_ACTION_STOP
    expected_instance_id: Optional[str] = None
    launch_expires_at: Optional[datetime] = None
    desired: str = ROLE_SERVICE_DESIRED_STOPPED
    observed: str = ROLE_SERVICE_OBSERVED_STOPPING
    idempotent_stopped: bool = False


class RoleServiceRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = PydField(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    expected_generation: int = PydField(strict=True, ge=0)
    expected_process_launch_id: str = PydField(min_length=1, max_length=200)
    expected_instance_id: str = PydField(min_length=1, max_length=200)
    expected_owner_host: str = PydField(min_length=1, max_length=200)
    confirmation: Literal["old_processes_confirmed_stopped"]
    reason: Literal["original_host_exited"]


class RoleServiceRecoveryPlan(BaseModel):
    project_id: str
    member_id: str
    expected_generation: int
    expected_process_launch_id: str
    expected_instance_id: str
    expected_owner_host: str
    process_pid: int
    process_started_at: datetime
    instance_last_seen_at: datetime
    checked_at: datetime


class RoleServiceRecoveryOut(BaseModel):
    project_id: str
    member_id: str
    operation_key: str
    recovery_id: str
    previous_generation: int
    generation: int
    confirmed_by: str
    recovered_at: datetime
    observed: Literal["stopped"] = "stopped"
    replayed: bool = False


class RoleServiceStartAllRequest(BaseModel):
    """``POST .../role-services/start-all`` 请求体（合同 §10.9）。

    ``member_ids`` 缺省/``null`` = 本项目全部角色；给定则只处理该子集
    （用于“只重试失败子集”）；出现跨项目或不存在 ID 时稳定拒绝。
    """

    model_config = ConfigDict(extra="forbid")

    member_ids: Optional[list[str]] = None


class RoleServiceStartAllMemberResult(BaseModel):
    """批量启动的逐角色结果：部分失败不整体回滚（合同 §10.9）。

    ``status`` 语义（R1-3 返修修正展示口径）：

    - ``requested``：本次**成功写入启动请求**（pending launch），但还没有任何宿主执行，
      ``observed`` 仍是 ``starting``/``readiness`` 仍是 ``pending``；
    - ``ready``：本次检查时该角色已收敛为 ``running`` + ``readiness_service=ready``
      （只有真实 ready 才算启动成功）；
    - ``skipped_running``：已 ``starting/running``，不重复启动（不重复 spawn）；
    - ``skipped_ownership_held``：失败/过期后原进程归属仍未释放，必须先关闭再重试；
    - ``failed``：意图写被稳定拒绝（如 ``control_kind_not_managed``）。
    """

    member_id: str
    role_name: Optional[str] = None
    status: str
    launch_id: Optional[str] = None
    generation: Optional[int] = None
    expected_instance_id: Optional[str] = None
    error_code: Optional[str] = None


class RoleServiceStartAllCounts(BaseModel):
    """批量计数：``started`` 只统计**实际 ready**，``requested`` 是本次写入的启动请求数。

    旧字段 ``started``/``skipped``/``failed`` 逐字保留（协议兼容），但语义按上面修正：
    只写入意图**不**再计入 ``started``，而是计入新增的 ``requested``。
    """

    started: int = 0
    requested: int = 0
    skipped: int = 0
    failed: int = 0


class RoleServiceStartAllOut(BaseModel):
    project_id: str
    requested: list[str]
    results: list[RoleServiceStartAllMemberResult]
    counts: RoleServiceStartAllCounts = PydField(
        default_factory=RoleServiceStartAllCounts
    )


class RoleServiceProjectionOut(ProjectRoleServiceOut):
    """``GET /api/projects/{project_id}/role-services`` 的单条投影。"""

    member_id: str
    role_name: Optional[str] = None
    archived: bool = False


class ProjectRoleListItem(BaseModel):
    """``GET /api/projects/{project_id}/roles`` 单条投影（合同 §5.2）。

    公开只读面：**不**返回 ``api_key``、``owner_token``、``claim_token``、绝对路径或 argv。
    """

    member_id: str
    role_name: str
    origin: str
    identity: str
    archived: bool
    identity_exclusive: bool
    runner: ProjectRoleRunnerOut = PydField(default_factory=ProjectRoleRunnerOut)
    model: ProjectRoleModelOut = PydField(default_factory=ProjectRoleModelOut)
    role_description: Optional[str] = None
    binding_state: Optional[str] = None
    service: Optional[ProjectRoleServiceOut] = None
    deletion: Optional[dict] = None
    startup: Optional[dict] = None


class RoleCredentialRotateOut(BaseModel):
    """``rotate-key`` 一次性响应（合同 §7.5）：``api_key`` 仅此一次出现。"""

    member_id: str
    api_key: str
    credential_version: int


class ProjectRoleTaskSummaryOut(BaseModel):
    """``GET /roles/{member_id}/tasks`` 只读非终态任务摘要。"""

    id: int
    title: Optional[str] = None
    status: str
    workflow_status: Optional[str] = None
    target_member_id: str
    created_by: str
    created_at: Optional[datetime] = None


class RoleProvisionRequest(BaseModel):
    """``POST .../roles/{member_id}/provision`` 请求体（PROVISION_CONTRACT §2.1）。

    ``extra="forbid"``；``operation_key`` 是 R1-1 创建操作的复用锚点，字段值的归一化
    与稳定错误码映射放在路由层（沿用 R1-1 ``create_project_role`` 的风格）。
    ``steps`` 只在 ``resume=true`` 时有意义：``null`` = 全部失败/待跑步骤。
    """

    model_config = ConfigDict(extra="forbid")

    operation_key: str
    resume: bool = False
    steps: Optional[list[str]] = None
    #: R1-4a：请求驱动角色必须显式给出精确来源；省略且存在来源行时拒绝旧人工旁路。
    request_key: Optional[str] = None
    lease_token: Optional[str] = None


class RoleProvisionAckRequest(BaseModel):
    """``POST .../roles/{member_id}/provision/ack`` 宿主回报体（PROVISION_CONTRACT §2.3）。

    本模型只做结构约束（``extra="forbid"``）；固定校验顺序与稳定错误码全部由路由层实现，
    乱序回报（旧 revision / 旧 attempt / 非 pending 步骤 / 旧凭据代际）必须被显式拒绝。

    ``credential_version``（补正 F1）是宿主在**本地副作用之前**捕获的作业代际凭据版本；
    服务端在写事务内同时比对作业快照与角色当前值，二者任一不符 → 409
    ``provision_credential_stale``，旧成功证明不得套到新代际。
    """

    model_config = ConfigDict(extra="forbid")

    operation_key: str
    step: str
    attempt: int
    revision: int
    credential_version: int
    state: str
    error_code: Optional[str] = None
    #: R1-4a：请求驱动角色必须显式给出精确来源；既有错误顺序与错误码保持不变。
    request_key: Optional[str] = None
    lease_token: Optional[str] = None


class RoleRequestRotateRequest(BaseModel):
    """``POST .../roles/{member_id}/rotate-key`` 的可选请求体（REQUEST_CONTRACT §7）。

    无 body 时保持旧 human 无请求来源路径（响应仍是 ``RoleCredentialRotateOut``）；
    一旦携带 ``request_key``，就必须同时给出 ``lease_token``，且响应换用**不带必填
    api_key** 的请求驱动结构（重放省略 Key），不把旧 schema 整体放宽。
    """

    model_config = ConfigDict(extra="forbid")

    request_key: str
    lease_token: str
    expected_credential_version: Optional[int] = None


class RoleProvisionStepOut(BaseModel):
    """作业单步公开投影（合同 §1/§2.4）：不含凭据、路径、argv 或异常文本。"""

    state: str
    attempts: int
    error_code: Optional[str] = None
    updated_at: Optional[str] = None


class RoleProvisionJobOut(BaseModel):
    """作业响应白名单（PROVISION_CONTRACT §2.4）。

    ``credential_version`` 是作业代际绑定的凭据版本计数（非凭据本身），宿主脚本据此在
    ACK 中回传同一代际事实。

    ``role_credential_version``（R1-2 followup 补正 G1）是**本次读取时角色行当前**的凭据
    版本计数（同样不是凭据本身）。两者不等即“作业快照已被轮换作废”：宿主脚本必须显式
    ``resume`` 重开凭据相关步骤，不能把旧成功当成免 ACK 的 no-op。

    ``expected_binding_fingerprint``（R1-2 followup 补正 G3）是本作业锚定的创建操作所选
    choice 的六维事实指纹（内容哈希，不含凭据/路径/argv）：宿主脚本把“不可变预期”与
    本次读取的绑定指纹逐对比较，避免分次 GET 之间的连接漂移被报成精确绑定通过。
    """

    operation_key: str
    project_id: str
    member_id: str
    status: str
    revision: int
    credential_version: int = 1
    role_credential_version: Optional[int] = None
    expected_binding_fingerprint: Optional[str] = None
    resume_of: Optional[str] = None
    steps: dict[str, RoleProvisionStepOut]
    created_by: str
    created_at: datetime
    updated_at: datetime


class RoleProvisionRosterPathsRequest(BaseModel):
    """``POST .../provision/roster-paths`` 请求体（单角色路径登记）。

    ``extra="forbid"``；三个路径值的归一化与稳定错误码由路由层
    （``normalize_provision_roster_paths``）实现，这里只做结构约束。
    """

    model_config = ConfigDict(extra="forbid")

    operation_key: str
    identity_path: str
    soul_path: str
    user_path: str


class RoleProvisionRosterPathsOut(BaseModel):
    """单角色路径登记响应白名单：只回写三个相对路径，不含 Key/绝对路径/argv。"""

    member_id: str
    identity_path: str
    soul_path: str
    user_path: str


class RoleBindingInput(BaseModel):
    """绑定写入体（合同 §4.1–§4.2）：行存在时必填键全部必填且非空白。"""

    model_config = ConfigDict(extra="forbid")

    runner_id: str
    model_source: str
    provider_id: str
    connection_ref: str
    model_id: str
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_role_binding(self) -> "RoleBindingInput":
        self.runner_id = normalize_runner_id(self.runner_id)
        self.model_source = normalize_model_source(self.model_source)
        self.provider_id = normalize_safe_identifier_token(
            self.provider_id, field="provider_id"
        )
        self.connection_ref = normalize_safe_identifier_token(
            self.connection_ref, field="connection_ref"
        )
        self.model_id = normalize_safe_identifier_token(self.model_id, field="model_id")
        self.model_alias = normalize_safe_identifier_token(
            self.model_alias, field="model_alias", required=False
        )
        self.model_display_name = normalize_model_display_name(self.model_display_name)
        return self


class RoleBindingUpdate(BaseModel):
    """``PUT /api/projects/{project_id}/agents/{member_id}/binding`` 请求体。

    ``binding`` 是**必填键**（无默认值 = required but nullable）：缺失 → 422；
    显式 ``null`` = 解除绑定（删除该行）；未知字段 → 422。
    """

    model_config = ConfigDict(extra="forbid")

    binding: Optional[RoleBindingInput]


class RoleBindingOut(BaseModel):
    """绑定读取输出（合同 §4.3）。

    ``runtime`` / ``runner_display_name`` / ``runner_status`` 从登记表读取时派生；
    ``binding_state`` 按 §4.4 阶梯读取时实时计算；``binding_fingerprint`` 是六维内容指纹
    （与有效性无关，登记事实不可解析时为 ``null``）。
    """

    runner_id: Optional[str] = None
    runtime: Optional[str] = None
    runner_display_name: Optional[str] = None
    runner_status: Optional[str] = None
    model_source: Optional[str] = None
    provider_id: Optional[str] = None
    connection_ref: Optional[str] = None
    model_id: Optional[str] = None
    model_alias: Optional[str] = None
    model_display_name: Optional[str] = None
    binding_state: Optional[str] = None
    binding_fingerprint: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class RoleBindingResponse(BaseModel):
    """``GET`` / ``PUT`` 单角色绑定的统一响应：存储行 + 读取时实时有效性状态。

    ``binding: null`` 表示**没有存储行**（不伪造默认运行器或模型）；``binding_state``
    回答“为什么没有可用绑定”（``unconfigured`` / 身份类状态 / ``partial`` / 运行器类状态）。
    成员已离册/已删除/被禁用/非 agent 时仍返回存储行与状态（不 404、不自动清理）。
    """

    project_id: str
    member_id: str
    binding: Optional[RoleBindingOut] = None
    binding_state: Optional[str] = None


class ProjectAgentOut(BaseModel):
    member_id: str
    archived: bool = False
    deletion: Optional[dict] = None
    # The role page reads this roster DTO, including its saved startup choice.
    startup: Optional[dict] = None
    # 项目内角色名为展示权威；与全局 Member.display_name 独立。
    role_name: Optional[str] = None
    identity_path: Optional[str]
    soul_path: Optional[str]
    user_path: Optional[str]
    memory_pointer: Optional[str]
    business_role: Optional[str]
    # 已弃用兼容字段：只回显旧存储值，不参与身份、权限、协调或绑定判定；
    # 公开 schema 明确标记 deprecated（R1-2 补正 F7），列本身不物理删除。
    decision_tier: Optional[str] = PydField(default=None, deprecated=True)
    capability_summary: list[str]
    # 角色说明（ROLE-DESC-B1）：无自定义记录 = null（前端据此回退默认文案）。
    # 纯展示文本，不参与 business_role / decision_tier / 主控指定 / 任务权限的任何判定。
    role_description: Optional[str] = None
    # 角色运行器/模型绑定（ROLE-BINDING-B1a）：附加字段，旧客户端忽略未知字段即可。
    # binding = null 表示没有存储行（不伪造默认模型）；binding_state 按合同 §4.4 阶梯
    # 读取时实时计算，只描述配置事实，不改变 business_role / decision_tier / 任务权限。
    binding: Optional[RoleBindingOut] = None
    binding_state: Optional[str] = None
    # 角色服务投影（R1-3）：附加字段，旧客户端忽略未知键即可。角色页的真实数据源是
    # ``GET /agents``，所以受管服务状态必须在这里一并给出；未登记服务时为 ``null``。
    service: Optional[ProjectRoleServiceOut] = None
    display_name: Optional[str]
    availability: str
    instances: list[AgentInstanceOut]
    updated_at: datetime

    @classmethod
    def from_orm_agent(
        cls,
        agent: ProjectAgent,
        *,
        display_name: Optional[str] = None,
        role_name: Optional[str] = None,
        availability: str = "offline",
        instances: Optional[list[AgentInstanceOut]] = None,
        role_description: Optional[str] = None,
        binding: Optional[RoleBindingOut] = None,
        binding_state: Optional[str] = None,
        service: Optional[ProjectRoleServiceOut] = None,
        archived: bool = False,
        deletion: Optional[dict] = None,
        startup: Optional[dict] = None,
    ) -> "ProjectAgentOut":
        return cls(
            member_id=agent.member_id,
            archived=archived,
            deletion=deletion,
            startup=startup,
            role_name=role_name,
            identity_path=agent.identity_path,
            soul_path=agent.soul_path,
            user_path=agent.user_path,
            memory_pointer=agent.memory_pointer,
            business_role=agent.business_role,
            decision_tier=agent.decision_tier,
            capability_summary=list(agent.capability_summary or []),
            role_description=role_description,
            binding=binding,
            binding_state=binding_state,
            service=service,
            display_name=display_name,
            availability=availability,
            instances=instances or [],
            updated_at=agent.updated_at,
        )


class RoleDescriptionUpdate(BaseModel):
    """`PUT /api/projects/{id}/agents/{member_id}/description` 请求体（ROLE-DESC-B1）。

    - ``description``：**必填键**（无默认值 = required but nullable）；
    - 校验顺序同 :func:`normalize_role_description`：先判空白归 ``None``（= 恢复默认/删除自定义），
      再对非空文本查 2000 Unicode 码点上限，非空超限 422；
    - 非空文本原样保留（不 strip、不折叠换行），换行与 ``<script>`` 等按字面存储。
    """

    description: Optional[str]

    @model_validator(mode="after")
    def validate_role_description(self) -> "RoleDescriptionUpdate":
        self.description = normalize_role_description(self.description)
        return self


class ProjectRoleDescriptionOut(BaseModel):
    """角色说明写入结果。

    ``description`` 是**归一化后**的值（空白 → ``null``，见设计 §3.3-D6）；``null`` 表示当前
    没有自定义记录（恢复默认），此时 ``updated_at`` / ``updated_by`` 同为 ``null``——
    响应如实描述“操作后库里的状态”，而不是“本次请求发生过什么”。
    """

    project_id: str
    member_id: str
    description: Optional[str]
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class AgentProfileOut(BaseModel):
    project_id: str
    member_id: str
    identity: Optional[str]
    soul: Optional[str]
    user: Optional[str]


class AgentProfileUpdate(BaseModel):
    identity: Optional[str] = None
    soul: Optional[str] = None
    user: Optional[str] = None


# ── 角色生命周期 R1-1：共享身份/选择事实助手 ─────────────────────────────
#
# 这些函数是各路由（projects / tasks / groups）共用的**同一份**判定，
# 避免“只守住了 sync 却漏掉群成员/Task Hall 自动成员”的分叉实现。


def slugify_role_name(value: Optional[str]) -> str:
    """把人工名称归一化为 slug（合同 §7.3）。

    NFKC → 小写 → 非 ``[a-z0-9]`` 折叠为 ``-`` → 去掉首尾 ``-`` → 截断 32。
    纯中文（折叠后为空）回退 ``role``，因此 ``member_id`` 不会退化成空 slug。
    """
    if not isinstance(value, str):
        return "role"
    normalized = unicodedata.normalize("NFKC", value).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    slug = slug[:32].strip("-")
    return slug or "role"


def build_role_member_id(project_id: str, role_name: str, suffix: str) -> str:
    """``agent:<project_slug>.<role_slug>-<8hex>``（合同 §7.3，P4）。"""
    return f"agent:{slugify_role_name(project_id)}.{slugify_role_name(role_name)}-{suffix}"


def new_role_member_id_suffix() -> str:
    return secrets.token_hex(4)


def new_role_api_key() -> str:
    return secrets.token_urlsafe(32)


def new_model_choice_id() -> str:
    """稳定不透明选择 ID：``rmc_<12hex>``（合同 §4.1.1）。"""
    return f"{MODEL_CHOICE_ID_PREFIX}{secrets.token_hex(6)}"


def build_role_creation_fingerprint(
    *,
    project_id: str,
    role_name: str,
    runner_id: str,
    choice_id: str,
    role_description: Optional[str],
) -> str:
    """创建操作请求指纹（合同 §7.2/§7.3）。

    参与项固定为 ``{project_id, role_name_normalized, runner_id, choice_id,
    role_description_or_empty, fingerprint_version}``，用规范化 JSON（键排序、紧凑分隔符、
    非 ASCII 原样）后取 ``sha256``——同 key 改介绍即视为异载荷。
    """
    payload = {
        "project_id": project_id,
        "role_name_normalized": role_name,
        "runner_id": runner_id,
        "choice_id": choice_id,
        "role_description_or_empty": role_description or "",
        "fingerprint_version": ROLE_DESCRIPTION_FINGERPRINT_VERSION,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_role_legacy_attach_fingerprint(
    *,
    project_id: str,
    member_id: str,
    runner_id: str,
    choice_id: str,
) -> str:
    """补录操作请求指纹（ROLE_LEGACY_ATTACH_DESIGN §原子补录、幂等与来源）。

    参与项固定为 ``{project_id, member_id, runner_id, choice_id, fingerprint_version}``，
    与创建指纹同一构造方式（键排序、紧凑分隔符、非 ASCII 原样、``sha256``）：同
    ``operation_key`` 改成员/运行器/选择，或跨项目重放，都会被判为异载荷并 409。
    角色名由服务端从当前成员事实派生，**不**进入指纹（调用方无法也无需指定）。
    """
    payload = {
        "project_id": project_id,
        "member_id": member_id,
        "runner_id": runner_id,
        "choice_id": choice_id,
        "fingerprint_version": ROLE_LEGACY_ATTACH_PAYLOAD_VERSION,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_role_provision_lease_token() -> str:
    """租约 token 明文：只在 claim 响应出现一次，库里只存 SHA256。"""
    return secrets.token_urlsafe(32)


def hash_role_provision_lease_token(token: str) -> str:
    """租约 token → 库内哈希（与 R1-1/R1-3 的 ``sha256`` 先例一致）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_role_recovery_fingerprint(
    *,
    project_id: str,
    member_id: str,
    expected_credential_version: int,
) -> str:
    """恢复意图请求指纹（REQUEST_CONTRACT §2）：只覆盖项目/成员/期望凭据版本。

    与创建指纹同一构造方式（键排序、紧凑分隔、非 ASCII 原样、``sha256``）：同键改成员
    或改期望版本即视为异载荷；**不含** Key、路径或 argv。
    """
    payload = {
        "project_id": project_id,
        "member_id": member_id,
        "expected_credential_version": int(expected_credential_version),
        "fingerprint_version": ROLE_REQUEST_PAYLOAD_VERSION,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def model_choice_dimension_facts(choice: Optional[RunnerModelChoice]) -> Optional[tuple]:
    """选择的六维事实（含 ``runner_id``）：与绑定行必须逐项一致才算同一次选择。"""
    if choice is None:
        return None
    return (
        choice.runner_id,
        choice.model_source,
        choice.provider_id,
        choice.connection_ref,
        choice.model_id,
        choice.model_alias or "",
    )


def role_binding_dimension_facts(binding: Optional[ProjectRoleBinding]) -> Optional[tuple]:
    """绑定行的六维事实（含 ``runner_id``）。"""
    if binding is None:
        return None
    return (
        binding.runner_id,
        binding.model_source,
        binding.provider_id,
        binding.connection_ref,
        binding.model_id,
        binding.model_alias or "",
    )


def exclusive_identity_owner_project(
    member_id: str, session: Session
) -> Optional[str]:
    """返回“本流程创建的独占身份”所属项目；不适用（历史/共享成员）时返回 ``None``。

    判定只看 ``project_roles.identity_exclusive=1`` 这个**持久标记**：一旦为 1，
    该 member 只归属创建项目，跨项目/全局引用都必须拒绝（合同 §7.5 第 3 条）。
    归档不改变归属（身份永不复用），因此这里刻意不过滤 ``archived_at``。
    """
    row = session.exec(
        select(ProjectRole)
        .where(ProjectRole.member_id == member_id)
        .where(ProjectRole.identity_exclusive == 1)
    ).first()
    return row.project_id if row is not None else None


def ensure_identity_exclusive_reference_allowed(
    member_id: str,
    reference_project_id: Optional[str],
    session: Session,
) -> None:
    """新独占身份引用守卫（合同 §7.5 第 3 条）。

    历史无 ``ProjectRole`` 或 ``identity_exclusive=0``（imported/共享）成员**完全保留旧行为**；
    只有新独占身份被限制在创建项目内，跨项目或全局（``project_id is None``）引用一律
    ``409 identity_exclusive_reference_refused``。调用方必须与新增写入处于同一写事务。
    """
    if reference_project_id is not None:
        role = session.get(ProjectRole, (reference_project_id, member_id))
        if role is not None and role.archived_at is not None:
            raise HTTPException(status_code=409, detail="role_archived")
    owner = exclusive_identity_owner_project(member_id, session)
    if owner is None:
        return
    if reference_project_id is None or reference_project_id != owner:
        raise HTTPException(
            status_code=409, detail=IDENTITY_EXCLUSIVE_REFERENCE_REFUSED
        )


def _table_exists(session: Session, table_name: str) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).first()
    return row is not None


def _table_columns(session: Session, table_name: str) -> set[str]:
    rows = session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


# R1-1 尚无 role_service_state 表：**不查询不存在的表、不伪造服务证据**。
# 一旦该表存在（R1-3 或测试构造的未来表），同一份独占证明必须补查其中的在用事实。
FUTURE_SERVICE_STATE_TABLE = "role_service_state"
FUTURE_SERVICE_STATE_COLUMNS = ("member_id", "desired_state", "observed_state")


def _service_state_in_use(member_id: str, session: Session) -> bool:
    if not _table_exists(session, FUTURE_SERVICE_STATE_TABLE):
        return False
    columns = _table_columns(session, FUTURE_SERVICE_STATE_TABLE)
    if not set(FUTURE_SERVICE_STATE_COLUMNS) <= columns:
        return False
    row = session.execute(
        text(
            "SELECT 1 FROM role_service_state WHERE member_id=:member_id "
            "AND (desired_state='running' "
            "OR observed_state IN ('starting','running','stopping')) LIMIT 1"
        ),
        {"member_id": member_id},
    ).first()
    return row is not None


def prove_exclusive_identity(
    project_id: str,
    member_id: str,
    session: Session,
    *,
    for_role_deletion: bool = False,
) -> dict:
    """独占引用证明（合同 §7.5，``rotate-key`` 与后续全局禁用共用）。

    在**同一写事务内**枚举全部兼容引用路径（不能只用新表自证），目标
    ``(project_id, member_id)`` 自身的那一行不算引用。返回分类清单：

    ``{"refusal": <稳定拒绝码|None>, "references": {...}}``

    判定顺序固定为：其它项目角色 → 旧 ``project_agents`` 跨项目 → 同项目名册行缺失
    → 绑定/说明跨项目 → 跨/全局群成员 → 在用实例/服务/在途任务。
    """
    other_roles = list(
        session.exec(
            select(ProjectRole)
            .where(ProjectRole.member_id == member_id)
            .where(ProjectRole.project_id != project_id)
            .where(ProjectRole.archived_at.is_(None))
        ).all()
    )
    other_roster = list(
        session.exec(
            select(ProjectAgent)
            .where(ProjectAgent.member_id == member_id)
            .where(ProjectAgent.project_id != project_id)
        ).all()
    )
    own_roster = session.get(ProjectAgent, (project_id, member_id))
    other_bindings = list(
        session.exec(
            select(ProjectRoleBinding)
            .where(ProjectRoleBinding.member_id == member_id)
            .where(ProjectRoleBinding.project_id != project_id)
        ).all()
    )
    other_descriptions = list(
        session.exec(
            select(ProjectRoleDescription)
            .where(ProjectRoleDescription.member_id == member_id)
            .where(ProjectRoleDescription.project_id != project_id)
        ).all()
    )
    group_refs = list(
        session.exec(
            select(GroupMember)
            .join(Group, Group.id == GroupMember.group_id)
            .where(GroupMember.member_id == member_id)
            .where(
                (Group.project_id.is_(None)) | (Group.project_id != project_id)
            )
        ).all()
    )
    active_instances = list(
        session.exec(
            select(AgentInstance)
            .where(AgentInstance.member_id == member_id)
            .where(
                AgentInstance.status.in_(
                    ("starting", "online", "idle", "busy", "stopping")
                )
            )
        ).all()
    )
    if for_role_deletion:
        # Deletion rechecks stale local process evidence; key rotation retains
        # its original strict instance policy by default.
        from server.role_deletions import _historical_local_instance_exited
        now = datetime.now(timezone.utc)
        active_instances = [row for row in active_instances
                            if not _historical_local_instance_exited(row, now)]
    active_tasks = list(
        session.exec(
            select(AgentTask)
            .where(
                (AgentTask.target_member_id == member_id)
                | (AgentTask.created_by == member_id)
            )
            .where(AgentTask.status.in_(("queued", "running")))
        ).all()
    )
    service_in_use = _service_state_in_use(member_id, session)

    references = {
        "other_project_roles": [row.project_id for row in other_roles],
        "other_project_roster": [row.project_id for row in other_roster],
        "own_project_roster": own_roster is not None,
        "other_project_bindings": [row.project_id for row in other_bindings],
        "other_project_descriptions": [row.project_id for row in other_descriptions],
        "cross_project_groups": [row.group_id for row in group_refs],
        "active_instances": [row.id for row in active_instances],
        "active_tasks": [row.id for row in active_tasks],
        "service_state_in_use": service_in_use,
    }

    refusal: Optional[str] = None
    if other_roles or other_bindings or other_descriptions:
        refusal = "rotate_shared_identity_refused"
    elif other_roster:
        refusal = "rotate_legacy_roster_reference_refused"
    elif own_roster is None:
        refusal = "rotate_identity_off_roster"
    elif group_refs:
        refusal = "rotate_group_reference_refused"
    elif active_instances or active_tasks or service_in_use:
        refusal = "rotate_identity_in_use"
    return {"refusal": refusal, "references": references}


# ── Runtime log receive tables (B2a, contract 283 correction) ───────
#
# These three tables are deliberately appended after all existing model
# definitions.  They add no columns, indexes or relationships to the existing
# business tables.  The source table stores only the public scope and audit
# counters; it never stores an API key, owner token, client path or native
# session.  Batch and event rows are written by
# ``server.runtime_log_receive_core`` in the same SQLite write transaction as
# the source counters and authorization recheck.
#
# ``received_at`` is kept as timezone-aware ISO-8601 TEXT instead of SQL
# ``DATETIME``: SQLite drops timezone information from datetime values, while
# receipt replay must preserve the exact first-commit timestamp (including the
# server clock's offset and a wall-clock rollback).


class RuntimeLogSource(SQLModel, table=True):
    """Credential-free server-side log source and its usage counters.

    The source scope is immutable.  ``source_id`` is the deterministic hash of
    ``(project_id, host, subject_kind, subject_id)`` and the unique scope index
    is a second database-level guard.  Revoking a source only flips ``active``
    and advances ``revision``; history, counters and ``next_event_seq`` remain
    so quotas cannot be reset by revoke/reactivate or by creating a new source.
    """

    __tablename__ = "runtime_log_sources"
    __table_args__ = (
        Index(
            "ux_runtime_log_sources_scope",
            "project_id",
            "host",
            "subject_kind",
            "subject_id",
            unique=True,
        ),
        Index("ix_runtime_log_sources_active", "active", "revision"),
        CheckConstraint("active IN (0, 1)", name="ck_runtime_log_sources_active"),
        CheckConstraint("revision >= 1", name="ck_runtime_log_sources_revision"),
        CheckConstraint("batch_count >= 0", name="ck_runtime_log_sources_batch_count"),
        CheckConstraint("event_count >= 0", name="ck_runtime_log_sources_event_count"),
        CheckConstraint("bytes_used >= 0", name="ck_runtime_log_sources_bytes_used"),
        CheckConstraint("next_event_seq >= 1", name="ck_runtime_log_sources_next_seq"),
    )

    source_id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    host: str
    subject_kind: str
    subject_id: str
    active: int = Field(default=1)
    revision: int = Field(default=1)
    batch_count: int = Field(default=0)
    event_count: int = Field(default=0)
    bytes_used: int = Field(default=0)
    next_event_seq: int = Field(default=1)
    created_at: str
    updated_at: str
    revoked_at: Optional[str] = None


class RuntimeLogBatch(SQLModel, table=True):
    """One accepted writer batch and its persistent, replayable receipt.

    ``(source_id, writer_run_id, batch_id)`` is the batch key.
    ``(source_id, writer_run_id, batch_seq)`` is a separate database uniqueness
    rule: the same sequence may not be reused for a different batch.  Sequence
    gaps are not interpreted as missing logs.  ``event_uids_json`` is a bounded
    ordered JSON list of event references; the full safe receipt is stored as
    canonical JSON as well, so a lost response can be replayed without reading
    or re-billing any event payload.
    """

    __tablename__ = "runtime_log_batches"
    __table_args__ = (
        Index(
            "ux_runtime_log_batches_key",
            "source_id",
            "writer_run_id",
            "batch_id",
            unique=True,
        ),
        Index(
            "ux_runtime_log_batches_seq",
            "source_id",
            "writer_run_id",
            "batch_seq",
            unique=True,
        ),
        CheckConstraint("batch_seq >= 1", name="ck_runtime_log_batches_seq"),
        CheckConstraint("event_count >= 1", name="ck_runtime_log_batches_event_count"),
        CheckConstraint("charged_bytes >= 0", name="ck_runtime_log_batches_charged"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_runtime_log_batches_content_sha",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(foreign_key="runtime_log_sources.source_id", index=True)
    writer_run_id: str
    batch_id: str
    batch_seq: int
    content_sha256: str
    event_count: int
    event_uids_json: str
    receipt_json: str
    charged_bytes: int
    received_at: str


class RuntimeLogEvent(SQLModel, table=True):
    """One stable event, deduplicated by the immutable source event key.

    The event identity is ``(source_id, writer_run_id, log_id)`` and
    ``event_uid`` is their deterministic hash.  Batch id, ordinal, receipt time
    and payload are deliberately *not* part of the identity, so repartitioning
    or reordering the same writer events reuses the original row, uid, first
    received time and source sequence.  ``payload_json`` is the canonical
    UTF-8 JSON produced by the trusted server-side projection; raw client JSON
    must never reach this row directly.
    """

    __tablename__ = "runtime_log_events"
    __table_args__ = (
        Index(
            "ux_runtime_log_events_key",
            "source_id",
            "writer_run_id",
            "log_id",
            unique=True,
        ),
        Index(
            "ux_runtime_log_events_received_seq",
            "source_id",
            "received_seq",
            unique=True,
        ),
        Index("ix_runtime_log_events_manager_run", "manager_run_id"),
        CheckConstraint("received_seq >= 1", name="ck_runtime_log_events_seq"),
        CheckConstraint("payload_bytes >= 0", name="ck_runtime_log_events_bytes"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_runtime_log_events_content_sha",
        ),
        CheckConstraint(
            "attribution_kind IN ('role_instance', 'role_launch', 'manager')",
            name="ck_runtime_log_events_attribution",
        ),
        CheckConstraint(
            "CASE "
            "WHEN attribution_kind = 'manager' THEN "
            "    (manager_run_id IS NOT NULL AND instance_id IS NULL AND launch_id IS NULL) "
            "WHEN attribution_kind = 'role_instance' THEN "
            "    (manager_run_id IS NULL AND instance_id IS NOT NULL AND launch_id IS NULL) "
            "WHEN attribution_kind = 'role_launch' THEN "
            "    (manager_run_id IS NULL AND instance_id IS NOT NULL AND launch_id IS NOT NULL) "
            "ELSE 0 END",
            name="ck_runtime_log_events_attribution_shape",
        ),
    )

    event_uid: str = Field(primary_key=True)
    source_id: str = Field(foreign_key="runtime_log_sources.source_id", index=True)
    writer_run_id: str
    log_id: str
    manager_run_id: Optional[str] = Field(default=None)
    member_id: str
    instance_id: Optional[str] = None
    launch_id: Optional[str] = None
    attribution_kind: str
    payload_json: str
    payload_bytes: int
    content_sha256: str
    received_at: str
    received_seq: int
