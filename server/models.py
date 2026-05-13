"""SQLModel data models for TALK platform."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydField, model_validator
from sqlmodel import Field, SQLModel


# ── ORM models (SQLite tables) ──────────────────────────────────────


class Member(SQLModel, table=True):
    __tablename__ = "members"

    id: str = Field(primary_key=True)  # 'human:bobo' / 'agent:AI1'
    kind: str  # 'human' | 'agent'
    display_name: str
    api_key: str = Field(unique=True, index=True)
    poll_hint: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
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


class AgentTask(SQLModel, table=True):
    __tablename__ = "agent_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    target_member_id: str = Field(foreign_key="members.id", index=True)
    created_by: str = Field(foreign_key="members.id", index=True)
    content: str
    title: Optional[str] = None
    status: str = Field(default="queued", index=True)
    claimed_by: Optional[str] = Field(default=None, foreign_key="members.id", index=True)
    instance_id: Optional[str] = Field(default=None, foreign_key="agent_instances.id", index=True)
    result_message_id: Optional[int] = Field(default=None, foreign_key="messages.id")
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claimed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ── API schemas (request / response) ────────────────────────────────


class MemberCreate(BaseModel):
    id: str  # 'human:bobo' / 'agent:AI1'
    display_name: str
    api_key: str
    poll_hint: Optional[int] = None


class MemberOut(BaseModel):
    id: str
    kind: str
    display_name: str
    poll_hint: Optional[int] = None
    created_at: datetime


class MessageCreate(BaseModel):
    to: Optional[list[str]] = None  # None = broadcast
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


class AgentTaskCreate(BaseModel):
    target_member_id: str
    content: str
    title: Optional[str] = None

    @model_validator(mode="after")
    def validate_task_create(self) -> "AgentTaskCreate":
        self.target_member_id = self.target_member_id.strip()
        self.content = self.content.strip()
        if self.title is not None:
            self.title = self.title.strip() or None
        if not self.target_member_id:
            raise ValueError("target_member_id is required")
        if not self.content:
            raise ValueError("content is required")
        return self


class AgentTaskClaim(BaseModel):
    instance_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_task_claim(self) -> "AgentTaskClaim":
        if self.instance_id is not None:
            self.instance_id = self.instance_id.strip() or None
        return self


class AgentTaskComplete(BaseModel):
    status: str
    result_message_id: Optional[int] = None
    last_error: Optional[str] = None

    @model_validator(mode="after")
    def validate_task_complete(self) -> "AgentTaskComplete":
        self.status = self.status.strip().lower()
        if self.status not in _TASK_TERMINAL_STATUSES:
            raise ValueError(f"status must be one of {sorted(_TASK_TERMINAL_STATUSES)}")
        if self.last_error is not None:
            self.last_error = self.last_error.strip() or None
        if self.status == "failed" and not self.last_error:
            raise ValueError("last_error is required when status is failed")
        return self


class AgentTaskOut(BaseModel):
    id: int
    target_member_id: str
    created_by: str
    content: str
    title: Optional[str]
    status: str
    claimed_by: Optional[str]
    instance_id: Optional[str]
    result_message_id: Optional[int]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    claimed_at: Optional[datetime]
    finished_at: Optional[datetime]
