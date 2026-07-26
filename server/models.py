"""SQLModel data models for TALK platform."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydField, model_validator
from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel

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
        if self.maintainer_member_id is not None:
            self.maintainer_member_id = self.maintainer_member_id.strip() or None
        return self


class ProjectUpdate(BaseModel):
    """Partial update — only fields explicitly provided are applied."""

    display_name: Optional[str] = None
    description: Optional[str] = None
    project_root_path: Optional[str] = None

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
        return self


class ProjectOut(BaseModel):
    project_id: str
    display_name: str
    description: Optional[str]
    project_root_path: Optional[str]
    maintainer_member_id: str
    created_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_orm_project(cls, project: Project) -> "ProjectOut":
        return cls(
            project_id=project.project_id,
            display_name=project.display_name,
            description=project.description,
            project_root_path=project.project_root_path,
            maintainer_member_id=project.maintainer_member_id,
            created_at=project.created_at,
            last_seen_at=project.last_seen_at,
        )


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


class ProjectAgentOut(BaseModel):
    member_id: str
    identity_path: Optional[str]
    soul_path: Optional[str]
    user_path: Optional[str]
    memory_pointer: Optional[str]
    business_role: Optional[str]
    decision_tier: Optional[str]
    capability_summary: list[str]
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
            display_name=display_name,
            availability=availability,
            instances=instances or [],
            updated_at=agent.updated_at,
        )


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
