"""SQLModel data models for TALK platform."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydField, model_validator
from sqlalchemy import Column, Index, JSON, text
from sqlmodel import Field, Session, SQLModel

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

# 枚举：模型来源（合同 §4.1）。
MODEL_SOURCE_BUILTIN = "builtin"
MODEL_SOURCE_CUSTOM_API = "custom_api"
MODEL_SOURCES = (MODEL_SOURCE_BUILTIN, MODEL_SOURCE_CUSTOM_API)

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
    decision_tier: Optional[str] = None
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
    decision_tier: Optional[str] = None

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


class AgentTaskComplete(BaseModel):
    status: str
    result_message_id: Optional[int] = None
    last_error: Optional[str] = None
    claim_token: Optional[str] = None
    gate_verdict: Optional[AgentTaskGateVerdict] = None

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


class AgentTaskClaimOut(AgentTaskOut):
    claim_token: str


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
    decision_tier: Optional[str] = None
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
            created_by=runner.created_by,
            created_at=runner.created_at,
            updated_at=runner.updated_at,
        )


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
    identity_path: Optional[str]
    soul_path: Optional[str]
    user_path: Optional[str]
    memory_pointer: Optional[str]
    business_role: Optional[str]
    decision_tier: Optional[str]
    capability_summary: list[str]
    # 角色说明（ROLE-DESC-B1）：无自定义记录 = null（前端据此回退默认文案）。
    # 纯展示文本，不参与 business_role / decision_tier / 主控指定 / 任务权限的任何判定。
    role_description: Optional[str] = None
    # 角色运行器/模型绑定（ROLE-BINDING-B1a）：附加字段，旧客户端忽略未知字段即可。
    # binding = null 表示没有存储行（不伪造默认模型）；binding_state 按合同 §4.4 阶梯
    # 读取时实时计算，只描述配置事实，不改变 business_role / decision_tier / 任务权限。
    binding: Optional[RoleBindingOut] = None
    binding_state: Optional[str] = None
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
        availability: str = "offline",
        instances: Optional[list[AgentInstanceOut]] = None,
        role_description: Optional[str] = None,
        binding: Optional[RoleBindingOut] = None,
        binding_state: Optional[str] = None,
    ) -> "ProjectAgentOut":
        return cls(
            member_id=agent.member_id,
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
