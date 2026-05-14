"""WebSocket connection hub broadcast utilities."""

from __future__ import annotations

import json
import logging
from typing import Dict, List

from fastapi import WebSocket

from server.models import Message, MessageOut

logger = logging.getLogger("talk.ws")


class Hub:
    """Manages active WebSocket connections keyed by member_id."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, member_id: str, ws: WebSocket) -> None:
        await ws.accept()
        was_online = member_id in self._connections
        self._connections.setdefault(member_id, []).append(ws)
        logger.info(
            "ws connect",
            extra={
                "event": "connect",
                "member_id": member_id,
                "online_members": len(self._connections),
                "online_connections": self._count(),
            },
        )
        await self._send_presence(ws)
        if not was_online:
            await self.broadcast_presence()

    def disconnect(self, member_id: str, ws: WebSocket) -> None:
        self._remove_connection(member_id, ws)
        logger.info(
            "ws disconnect",
            extra={
                "event": "disconnect",
                "member_id": member_id,
                "online_members": len(self._connections),
                "online_connections": self._count(),
            },
        )

    async def disconnect_and_broadcast(self, member_id: str, ws: WebSocket) -> None:
        status_changed = self._remove_connection(member_id, ws)
        logger.info(
            "ws disconnect",
            extra={
                "event": "disconnect",
                "member_id": member_id,
                "online_members": len(self._connections),
                "online_connections": self._count(),
            },
        )
        if status_changed:
            await self.broadcast_presence()

    async def broadcast(self, msg_out: MessageOut, *, targets: list[str] | None = None) -> None:
        payload = json.dumps(
            {"type": "message", "payload": msg_out.model_dump(by_alias=True)},
            ensure_ascii=False,
            default=str,
        )
        target_members = targets if targets is not None else self._targets_for_message_out(msg_out)

        logger.info(
            "ws broadcast",
            extra={
                "event": "broadcast",
                "message_id": msg_out.id,
                "message_type": msg_out.type,
                "broadcast_all": msg_out.to is None,
                "target_members": len(target_members),
            },
        )

        dead: list[tuple[str, WebSocket]] = []
        for mid in target_members:
            for ws in self._connections.get(mid, []):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((mid, ws))

        status_changed = False
        for mid, ws in dead:
            status_changed = self._remove_connection(mid, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def broadcast_revoke(self, message: Message, *, targets: list[str] | None = None) -> None:
        if message.id is None or message.revoked_by is None:
            return

        payload = json.dumps(
            {
                "type": "revoke",
                "payload": {
                    "id": message.id,
                    "revoked_by": message.revoked_by,
                },
            },
            ensure_ascii=False,
            default=str,
        )
        target_members = targets if targets is not None else self._targets_for_message(message)

        logger.info(
            "ws revoke broadcast",
            extra={
                "event": "revoke",
                "message_id": message.id,
                "broadcast_all": message.to_ids is None,
                "target_members": len(target_members),
            },
        )

        dead: list[tuple[str, WebSocket]] = []
        for member_id in target_members:
            for ws in self._connections.get(member_id, []):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((member_id, ws))

        status_changed = False
        for member_id, ws in dead:
            status_changed = self._remove_connection(member_id, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def broadcast_presence(self) -> None:
        payload = self._presence_payload()
        dead: list[tuple[str, WebSocket]] = []

        for member_id, sockets in self._connections.items():
            for ws in sockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((member_id, ws))

        status_changed = False
        for member_id, ws in dead:
            status_changed = self._remove_connection(member_id, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def _send_presence(self, ws: WebSocket) -> None:
        await ws.send_text(self._presence_payload())

    def _presence_payload(self) -> str:
        return json.dumps(
            {
                "type": "presence",
                "payload": {"online_ids": sorted(self._connections.keys())},
            },
            ensure_ascii=False,
        )

    def _remove_connection(self, member_id: str, ws: WebSocket) -> bool:
        conns = self._connections.get(member_id, [])
        was_online = bool(conns)

        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(member_id, None)

        return was_online and member_id not in self._connections

    def _targets_for_message_out(self, msg_out: MessageOut) -> list[str]:
        if msg_out.to is None:
            return list(self._connections.keys())
        return list(set(msg_out.to) | {msg_out.from_field})

    def _targets_for_message(self, message: Message) -> list[str]:
        recipients = message.to_list
        if recipients is None:
            return list(self._connections.keys())
        return list(set(recipients) | {message.from_id})

    def _count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    def online_members_count(self) -> int:
        return len(self._connections)


hub = Hub()
