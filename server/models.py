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
