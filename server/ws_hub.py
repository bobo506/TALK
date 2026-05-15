"""WebSocket connection hub broadcast utilities."""

from __future__ import annotations

import asyncio
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
        self._event_queues: Dict[str, List[asyncio.Queue[str]]] = {}

    async def connect(self, member_id: str, ws: WebSocket) -> None:
        await ws.accept()
        was_online = self._is_online(member_id)
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

    async def subscribe_events(self, member_id: str) -> asyncio.Queue[str]:
        was_online = self._is_online(member_id)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._event_queues.setdefault(member_id, []).append(queue)
        logger.info(
            "sse connect",
            extra={
                "event": "sse_connect",
                "member_id": member_id,
                "online_members": self.online_members_count(),
                "sse_connections": self._event_count(),
            },
        )
        self._queue_sse_event(queue, "presence", self._presence_payload_dict())
        if not was_online:
            await self.broadcast_presence()
        return queue

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

    async def unsubscribe_events(self, member_id: str, queue: asyncio.Queue[str]) -> None:
        status_changed = self._remove_event_queue(member_id, queue)
        logger.info(
            "sse disconnect",
            extra={
                "event": "sse_disconnect",
                "member_id": member_id,
                "online_members": self.online_members_count(),
                "sse_connections": self._event_count(),
            },
        )
        if status_changed:
            await self.broadcast_presence()

    async def broadcast(self, msg_out: MessageOut, *, targets: list[str] | None = None) -> None:
        payload_dict = msg_out.model_dump(by_alias=True)
        payload = json.dumps({"type": "message", "payload": payload_dict}, ensure_ascii=False, default=str)
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
            self._queue_sse_event_for_member(mid, "message", payload_dict, event_id=msg_out.id)

        status_changed = False
        for mid, ws in dead:
            status_changed = self._remove_connection(mid, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def broadcast_revoke(self, message: Message, *, targets: list[str] | None = None) -> None:
        if message.id is None or message.revoked_by is None:
            return

        payload_dict = {
            "id": message.id,
            "revoked_by": message.revoked_by,
        }
        payload = json.dumps(
            {
                "type": "revoke",
                "payload": payload_dict,
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
            self._queue_sse_event_for_member(member_id, "revoke", payload_dict, event_id=message.id)

        status_changed = False
        for member_id, ws in dead:
            status_changed = self._remove_connection(member_id, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def broadcast_presence(self) -> None:
        payload_dict = self._presence_payload_dict()
        payload = json.dumps({"type": "presence", "payload": payload_dict}, ensure_ascii=False)
        dead: list[tuple[str, WebSocket]] = []

        for member_id, sockets in self._connections.items():
            for ws in sockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((member_id, ws))

        for member_id in list(self._event_queues):
            self._queue_sse_event_for_member(member_id, "presence", payload_dict)

        status_changed = False
        for member_id, ws in dead:
            status_changed = self._remove_connection(member_id, ws) or status_changed

        if status_changed:
            await self.broadcast_presence()

    async def _send_presence(self, ws: WebSocket) -> None:
        await ws.send_text(json.dumps({"type": "presence", "payload": self._presence_payload_dict()}, ensure_ascii=False))

    def _presence_payload_dict(self) -> dict[str, list[str]]:
        return {"online_ids": sorted(self._online_member_ids())}

    def _remove_connection(self, member_id: str, ws: WebSocket) -> bool:
        conns = self._connections.get(member_id, [])
        was_online = self._is_online(member_id)

        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(member_id, None)

        return was_online and not self._is_online(member_id)

    def _remove_event_queue(self, member_id: str, queue: asyncio.Queue[str]) -> bool:
        was_online = self._is_online(member_id)
        queues = self._event_queues.get(member_id, [])

        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._event_queues.pop(member_id, None)

        return was_online and not self._is_online(member_id)

    def _targets_for_message_out(self, msg_out: MessageOut) -> list[str]:
        if msg_out.to is None:
            return list(self._online_member_ids())
        return list(set(msg_out.to) | {msg_out.from_field})

    def _targets_for_message(self, message: Message) -> list[str]:
        recipients = message.to_list
        if recipients is None:
            return list(self._online_member_ids())
        return list(set(recipients) | {message.from_id})

    def _online_member_ids(self) -> set[str]:
        return set(self._connections) | set(self._event_queues)

    def _is_online(self, member_id: str) -> bool:
        return member_id in self._connections or member_id in self._event_queues

    def _queue_sse_event_for_member(
        self,
        member_id: str,
        event_type: str,
        payload: object,
        *,
        event_id: int | None = None,
    ) -> None:
        for queue in self._event_queues.get(member_id, []):
            self._queue_sse_event(queue, event_type, payload, event_id=event_id)

    def _queue_sse_event(
        self,
        queue: asyncio.Queue[str],
        event_type: str,
        payload: object,
        *,
        event_id: int | None = None,
    ) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(self.format_sse_event(event_type, payload, event_id=event_id))

    @staticmethod
    def format_sse_event(event_type: str, payload: object, *, event_id: int | None = None) -> str:
        lines: list[str] = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {event_type}")
        data = json.dumps(payload, ensure_ascii=False, default=str)
        for line in data.splitlines() or [""]:
            lines.append(f"data: {line}")
        return "\n".join(lines) + "\n\n"

    def _count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    def _event_count(self) -> int:
        return sum(len(v) for v in self._event_queues.values())

    def online_members_count(self) -> int:
        return len(self._online_member_ids())


hub = Hub()
