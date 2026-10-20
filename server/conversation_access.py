"""Read-only conversation observer policy (Group / Task Hall).

背景：管理账号需要在不加入 Group / Task Hall 的前提下查看对话（历史、成果、实时
更新）。本片只提供**最小只读旁观**能力，不改变任何发送 / 撤回 / 成员管理语义。

配置来源（服务端进程启动时读取的 ``config.toml``）：

.. code-block:: toml

    [conversation_access]
    observer_member_ids = ["human:bobo"]

规则：

- 默认空列表 / 未配置 = 未启用，所有人维持旧的“读对话需成员”规则。
- 只有出现在名单中、且经鉴权反查 ``kind == "human"``、未禁用的成员，
  才可以越过“读 Group 对话需成员”的判断。
- 非法配置一律 fail closed（视为空名单）：非列表、星号、非字符串条目、
  控制字符、超量条目、非法成员 ID 形态都不会退化成 “所有 human 可看”。
- Agent 即使被误列入名单也不会获得该权限（``kind`` 校验兜底）。
- 名单只能通过服务端配置文件维护；本片不提供任何 API 写入口，
  不新建身份 / 表，也不改动 ``models.py`` / ``auth.py`` / ``db.py``。
"""

from __future__ import annotations

import logging
import re

from sqlmodel import Session, select

import server.db as db
from server.models import GroupMember, Member

logger = logging.getLogger("talk")

# 名单上限：这是一个“少量管理账号”的显式配置，超量视为配置错误并整体关闭。
_MAX_OBSERVER_IDS = 16
# 成员 ID 形态：与现有 human:xxx / agent:xxx 约定一致；不允许星号与控制字符。
_MEMBER_ID_RE = re.compile(r"^(?:human|agent):[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# 同一种非法配置只告警一次，避免每次读消息都刷日志。
_warned_reasons: set[str] = set()


def _warn_once(reason: str) -> None:
    if reason in _warned_reasons:
        return
    _warned_reasons.add(reason)
    logger.warning(
        "conversation_access config rejected, observer access disabled",
        extra={"event": "conversation_access_config_rejected", "reason": reason},
    )


def observer_member_ids() -> frozenset[str]:
    """Return the validated observer id list; empty when unset or invalid.

    每次调用都从 ``server.db.CONFIG`` 现读，配置缺失 / 非法一律返回空集（fail closed）。
    """
    section = db.CONFIG.get("conversation_access")
    if section is None:
        return frozenset()
    if not isinstance(section, dict):
        _warn_once("section_not_table")
        return frozenset()

    raw_ids = section.get("observer_member_ids")
    if raw_ids is None:
        return frozenset()
    if not isinstance(raw_ids, list):
        _warn_once("observer_member_ids_not_list")
        return frozenset()
    if len(raw_ids) > _MAX_OBSERVER_IDS:
        _warn_once("observer_member_ids_too_many")
        return frozenset()

    validated: list[str] = []
    for entry in raw_ids:
        if not isinstance(entry, str):
            _warn_once("observer_member_id_not_string")
            return frozenset()
        if "*" in entry:
            _warn_once("observer_member_id_wildcard")
            return frozenset()
        if not _MEMBER_ID_RE.fullmatch(entry):
            _warn_once("observer_member_id_invalid")
            return frozenset()
        validated.append(entry)
    return frozenset(validated)


def is_conversation_observer(member: Member | None) -> bool:
    """Whether this authenticated member may read any Group / Task Hall.

    只读旁观，不隐含任何写入 / 发送 / 成员管理资格；Agent 与已禁用成员
    即使出现在配置名单中也不获得权限。
    """
    if member is None:
        return False
    if member.kind != "human":
        return False
    if member.disabled_at is not None:
        return False
    return member.id in observer_member_ids()


def is_group_member(group_id: str, member_id: str, session: Session) -> bool:
    return session.get(GroupMember, (group_id, member_id)) is not None


def can_read_group_conversation(group_id: str, member: Member, session: Session) -> bool:
    """Group 对话读权限：成员可读；已配置且合法的人工观察者可只读旁观。"""
    if is_group_member(group_id, member.id, session):
        return True
    return is_conversation_observer(member)


def active_human_observer_ids(session: Session) -> list[str]:
    """当前仍合法的观察者 id（存在、human、未禁用），用于实时投递合并。"""
    configured = observer_member_ids()
    if not configured:
        return []
    rows = session.exec(select(Member).where(Member.id.in_(sorted(configured)))).all()
    return sorted(
        member.id
        for member in rows
        if member.kind == "human" and member.disabled_at is None
    )


def merge_observer_targets(member_ids: list[str], session: Session) -> list[str]:
    """把当前合法的观察者并入 Group 消息的实时投递目标。

    仅用于 Group 消息 / 撤回的 WS+SSE 投递；调用方必须保证这是 Group 消息。
    发送 / mention 使用的成员集合不经过这里，保持严格成员语义。
    """
    observers = active_human_observer_ids(session)
    if not observers:
        return member_ids
    existing = set(member_ids)
    return [*member_ids, *[mid for mid in observers if mid not in existing]]
