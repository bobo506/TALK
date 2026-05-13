"""Synchronous wrapper around the async TALK SDK."""

from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import Future
from threading import Thread
from typing import Any, Callable

from TALK.client.talk_client import TalkClient

SyncHandler = Callable[[dict[str, Any]], Any]


class TalkClientSync:
    """Sync facade that owns a dedicated event loop in a background thread."""

    def __init__(self, base_url: str, api_key: str, **kwargs: Any) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, name="talk-client-sync", daemon=True)
        self._thread.start()
        self._client = TalkClient(base_url, api_key, **kwargs)

    @property
    def member_id(self) -> str | None:
        return self._client.member_id

    def on_message(self, handler: SyncHandler) -> SyncHandler:
        self._client.on_message(self._wrap_handler(handler))
        return handler

    def on_presence(self, handler: SyncHandler) -> SyncHandler:
        self._client.on_presence(self._wrap_handler(handler))
        return handler

    def on_revoke(self, handler: SyncHandler) -> SyncHandler:
        self._client.on_revoke(self._wrap_handler(handler))
        return handler

    def register(self, member_id: str, *, display_name: str, poll_hint: int | None = None) -> dict[str, Any]:
        return self._submit(self._client.register(member_id, display_name=display_name, poll_hint=poll_hint))

    def send_text(
        self,
        text: str,
        to: str | list[str] | tuple[str, ...] | None = None,
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.send_text(text, to=to, reply_to=reply_to))

    def send_file(
        self,
        path,
        *,
        caption: str | None = None,
        to: str | list[str] | tuple[str, ...] | None = None,
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.send_file(path, caption=caption, to=to, reply_to=reply_to))

    def revoke(self, message_id: int) -> dict[str, Any]:
        return self._submit(self._client.revoke(message_id))

    def download_file(self, file_id: str, save_to=None):
        return self._submit(self._client.download_file(file_id, save_to=save_to))

    def me(self) -> dict[str, Any]:
        return self._submit(self._client.me())

    def list_members(self) -> list[dict[str, Any]]:
        return self._submit(self._client.list_members())

    def report_instance_status(
        self,
        instance_id: str,
        *,
        runtime: str,
        status: str,
        host: str | None = None,
        pid: int | None = None,
        current_task_id: str | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.report_instance_status(
                instance_id,
                runtime=runtime,
                status=status,
                host=host,
                pid=pid,
                current_task_id=current_task_id,
                last_error=last_error,
            )
        )

    def list_instances(
        self,
        *,
        member_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._submit(self._client.list_instances(member_id=member_id, status=status))

    def create_task(
        self,
        target_member_id: str,
        content: str,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.create_task(target_member_id, content, title=title))

    def list_tasks(
        self,
        *,
        target_member_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._submit(self._client.list_tasks(target_member_id=target_member_id, status=status))

    def claim_task(self, task_id: int, *, instance_id: str | None = None) -> dict[str, Any]:
        return self._submit(self._client.claim_task(task_id, instance_id=instance_id))

    def complete_task(
        self,
        task_id: int,
        *,
        status: str,
        result_message_id: int | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.complete_task(
                task_id,
                status=status,
                result_message_id=result_message_id,
                last_error=last_error,
            )
        )

    def fetch_history(
        self,
        *,
        before: int | None = None,
        since: int | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._submit(self._client.fetch_history(before=before, since=since, q=q, limit=limit))

    def run(self) -> None:
        self._submit(self._client.run())

    def close(self) -> None:
        try:
            self._submit(self._client.close())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def _submit(self, coroutine):
        future: Future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @staticmethod
    def _wrap_handler(handler: SyncHandler):
        if inspect.iscoroutinefunction(handler):
            return handler

        async def wrapped(payload: dict[str, Any]) -> Any:
            return await asyncio.to_thread(handler, payload)

        return wrapped
