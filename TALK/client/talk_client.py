"""Async TALK SDK client."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import OrderedDict
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets

from TALK.client.exceptions import (
    TalkAuthError,
    TalkError,
    TalkNotFoundError,
    TalkServerError,
    TalkValidationError,
)

JsonDict = dict[str, Any]
Handler = Callable[[JsonDict], Any]

logger = logging.getLogger("talk.client")


class TalkClient:
    """Async client for TALK HTTP + WebSocket APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        poll_interval: float = 2.0,
        reconnect_initial_delay: float = 0.5,
        reconnect_max_delay: float = 8.0,
        dedupe_size: int = 512,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ws_url = self._derive_ws_url(self.base_url, api_key)
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.dedupe_size = dedupe_size
        self.timeout = timeout

        self._http: httpx.AsyncClient | None = None
        self._ws = None
        self._running = False
        self._closing = False
        self._member: JsonDict | None = None
        self._last_message_id = 0
        self._recent_message_ids: OrderedDict[int, None] = OrderedDict()

        self._message_handlers: list[Handler] = []
        self._presence_handlers: list[Handler] = []
        self._revoke_handlers: list[Handler] = []

    async def __aenter__(self) -> TalkClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @property
    def member_id(self) -> str | None:
        return None if self._member is None else str(self._member["id"])

    def on_message(self, handler: Handler) -> Handler:
        self._message_handlers.append(handler)
        return handler

    def on_presence(self, handler: Handler) -> Handler:
        self._presence_handlers.append(handler)
        return handler

    def on_revoke(self, handler: Handler) -> Handler:
        self._revoke_handlers.append(handler)
        return handler

    async def register(
        self,
        member_id: str,
        *,
        display_name: str,
        poll_hint: int | None = None,
    ) -> JsonDict:
        payload = {
            "id": member_id,
            "display_name": display_name,
            "api_key": self.api_key,
            "poll_hint": poll_hint,
        }
        member = await self._request_json("POST", "/api/members", json_body=payload)
        if member.get("id") == member_id:
            self._member = member
        return member

    async def send_text(
        self,
        text: str,
        to: str | list[str] | tuple[str, ...] | None = None,
        reply_to: int | None = None,
    ) -> JsonDict:
        payload: JsonDict = {"type": "text", "content": text}
        normalized_to = self._normalize_recipients(to)
        if normalized_to is not None:
            payload["to"] = normalized_to
        if reply_to is not None:
            payload["reply_to"] = reply_to
        return await self._request_json("POST", "/api/messages", json_body=payload)

    async def send_file(
        self,
        path: str | Path,
        *,
        caption: str | None = None,
        to: str | list[str] | tuple[str, ...] | None = None,
        reply_to: int | None = None,
    ) -> JsonDict:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise TalkNotFoundError(f"file not found: {file_path}")

        with file_path.open("rb") as fh:
            uploaded = await self._request_json(
                "POST",
                "/api/files",
                files={"file": (file_path.name, fh, "application/octet-stream")},
            )

        payload: JsonDict = {
            "type": "file",
            "file_id": uploaded["file_id"],
            "content": file_path.name,
        }
        normalized_to = self._normalize_recipients(to)
        if normalized_to is not None:
            payload["to"] = normalized_to
        if caption:
            payload["caption"] = caption
        if reply_to is not None:
            payload["reply_to"] = reply_to
        return await self._request_json("POST", "/api/messages", json_body=payload)

    async def reply(
        self,
        message_id: int,
        *,
        text: str,
        to: str | list[str] | tuple[str, ...] | None = None,
    ) -> JsonDict:
        return await self.send_text(text, to=to, reply_to=message_id)

    async def revoke(self, message_id: int) -> JsonDict:
        return await self._request_json("POST", f"/api/messages/{message_id}/revoke")

    async def download_file(self, file_id: str, save_to: str | Path | None = None) -> bytes | Path:
        client = await self._get_http()
        response = await client.get(f"/api/files/{file_id}")
        self._raise_for_status(response)
        content = response.content
        if save_to is None:
            return content

        target = Path(save_to).expanduser()
        if target.exists() and target.is_dir():
            filename = self._filename_from_headers(response.headers) or f"{file_id}.bin"
            target = target / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    async def me(self) -> JsonDict:
        member = await self._request_json("GET", "/api/members/me")
        self._member = member
        return member

    async def list_members(self) -> list[JsonDict]:
        return await self._request_json("GET", "/api/members")

    async def fetch_history(
        self,
        *,
        before: int | None = None,
        since: int | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[JsonDict]:
        member = await self._ensure_member()
        params: dict[str, Any] = {"limit": limit, "to": member["id"]}
        if before is not None:
            params["before"] = before
        if since is not None:
            params["since"] = since
        if q:
            params["q"] = q
        return await self._request_json("GET", "/api/messages", params=params)

    async def run(self) -> None:
        if self._running:
            raise RuntimeError("TalkClient.run() is already active")

        self._running = True
        self._closing = False
        reconnect_delay = self.reconnect_initial_delay

        try:
            await self._ensure_member()
            while not self._closing:
                try:
                    await self._run_websocket_session()
                    reconnect_delay = self.reconnect_initial_delay
                except asyncio.CancelledError:
                    raise
                except TalkAuthError:
                    raise
                except Exception as exc:
                    if self._closing:
                        break
                    logger.debug("WS disconnected, switching to HTTP fallback: %s", exc)
                    reconnect_delay = await self._run_http_fallback(reconnect_delay)
        finally:
            self._running = False

    async def close(self) -> None:
        self._closing = True
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _run_websocket_session(self) -> None:
        try:
            ws_kwargs: dict[str, Any] = {"ping_interval": None, "close_timeout": 1}
            if "proxy" in inspect.signature(websockets.connect).parameters:
                ws_kwargs["proxy"] = None

            async with websockets.connect(self.ws_url, **ws_kwargs) as ws:
                self._ws = ws
                async for raw in ws:
                    await self._handle_ws_event(raw)
        finally:
            self._ws = None

        if not self._closing:
            raise ConnectionError("websocket disconnected")

    async def _run_http_fallback(self, reconnect_delay: float) -> float:
        deadline = asyncio.get_running_loop().time() + reconnect_delay

        while not self._closing:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except TalkAuthError:
                raise
            except Exception as exc:
                logger.debug("HTTP fallback poll failed: %s", exc)

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(self.poll_interval, max(0.05, remaining)))

        self._ws = None
        return min(reconnect_delay * 2, self.reconnect_max_delay)

    async def _poll_once(self) -> None:
        messages = await self.fetch_history(since=self._last_message_id, limit=100)
        for payload in messages:
            await self._handle_message_payload(payload)

    async def _handle_ws_event(self, raw: str) -> None:
        event = json.loads(raw)
        event_type = event.get("type")
        payload = event.get("payload") or {}

        if event_type == "ping":
            if self._ws is not None:
                await self._ws.send(json.dumps({"type": "pong"}))
            return

        if event_type == "presence":
            await self._dispatch_handlers(self._presence_handlers, payload)
            return

        if event_type == "revoke":
            await self._handle_revoke_payload(payload)
            return

        if event_type == "message":
            await self._handle_message_payload(payload)
            return

        logger.debug("Ignoring unsupported WS event type=%s", event_type)

    async def _handle_message_payload(self, payload: JsonDict) -> None:
        payload = self._normalize_message_payload(payload)
        message_id = int(payload["id"])
        sender = payload.get("from")
        if sender == self.member_id:
            return
        if not self._remember_message_id(message_id):
            return
        self._last_message_id = max(self._last_message_id, message_id)
        await self._dispatch_handlers(self._message_handlers, payload)

    async def _handle_revoke_payload(self, payload: JsonDict) -> None:
        if payload.get("revoked_by") == self.member_id:
            return
        await self._dispatch_handlers(self._revoke_handlers, payload)

    async def _dispatch_handlers(self, handlers: list[Handler], payload: JsonDict) -> None:
        for handler in list(handlers):
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("TALK client handler failed")

    def _remember_message_id(self, message_id: int) -> bool:
        if message_id in self._recent_message_ids:
            self._recent_message_ids.move_to_end(message_id)
            return False

        self._recent_message_ids[message_id] = None
        while len(self._recent_message_ids) > self.dedupe_size:
            self._recent_message_ids.popitem(last=False)
        return True

    async def _ensure_member(self) -> JsonDict:
        if self._member is None:
            await self.me()
        assert self._member is not None
        return self._member

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
                trust_env=False,
            )
        return self._http

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: JsonDict | None = None,
        files: Any = None,
    ) -> Any:
        client = await self._get_http()
        response = await client.request(method, path, params=params, json=json_body, files=files)
        self._raise_for_status(response)
        if not response.content:
            return None
        return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        detail = payload.get("detail") if isinstance(payload, dict) else payload
        message = str(detail or f"HTTP {response.status_code}")

        if response.status_code in {401, 403}:
            raise TalkAuthError(message, status_code=response.status_code, payload=payload)
        if response.status_code == 404:
            raise TalkNotFoundError(message, status_code=response.status_code, payload=payload)
        if response.status_code in {400, 409, 413, 422}:
            raise TalkValidationError(message, status_code=response.status_code, payload=payload)
        if response.status_code >= 500:
            raise TalkServerError(message, status_code=response.status_code, payload=payload)
        raise TalkError(message, status_code=response.status_code, payload=payload)

    @staticmethod
    def _derive_ws_url(base_url: str, api_key: str) -> str:
        parts = urlsplit(base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        path = f"{parts.path.rstrip('/')}/ws"
        return urlunsplit((scheme, parts.netloc, path, f"token={api_key}", ""))

    @staticmethod
    def _normalize_recipients(to: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
        if to is None:
            return None
        if isinstance(to, str):
            return [to]
        return list(to)

    @staticmethod
    def _filename_from_headers(headers: httpx.Headers) -> str | None:
        disposition = headers.get("Content-Disposition")
        if not disposition:
            return None

        parser = BytesParser(policy=HTTP)
        message = parser.parsebytes(f"Content-Disposition: {disposition}\r\n\r\n".encode("utf-8"))
        return message.get_filename()

    @staticmethod
    def _normalize_message_payload(payload: JsonDict) -> JsonDict:
        if "from" in payload or "from_field" not in payload:
            return payload

        normalized = dict(payload)
        normalized["from"] = normalized.pop("from_field")
        return normalized
