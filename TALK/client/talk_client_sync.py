"""Synchronous wrapper around the async TALK SDK."""

from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import Future
from datetime import datetime
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
        group_id: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.send_text(text, to=to, reply_to=reply_to, group_id=group_id))

    def send_file(
        self,
        path,
        *,
        caption: str | None = None,
        to: str | list[str] | tuple[str, ...] | None = None,
        reply_to: int | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.send_file(path, caption=caption, to=to, reply_to=reply_to, group_id=group_id))

    def revoke(self, message_id: int) -> dict[str, Any]:
        return self._submit(self._client.revoke(message_id))

    def reply(
        self,
        message_id: int,
        *,
        text: str,
        to: str | list[str] | tuple[str, ...] | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.reply(message_id, text=text, to=to, group_id=group_id))

    def download_file(self, file_id: str, save_to=None):
        return self._submit(self._client.download_file(file_id, save_to=save_to))

    def me(self) -> dict[str, Any]:
        return self._submit(self._client.me())

    def list_members(self) -> list[dict[str, Any]]:
        return self._submit(self._client.list_members())

    def create_group(
        self,
        name: str,
        *,
        group_id: str | None = None,
        description: str | None = None,
        member_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.create_group(
                name,
                group_id=group_id,
                description=description,
                member_ids=member_ids,
            )
        )

    def list_groups(self) -> list[dict[str, Any]]:
        return self._submit(self._client.list_groups())

    def get_group(self, group_id: str) -> dict[str, Any]:
        return self._submit(self._client.get_group(group_id))

    def update_group(
        self,
        group_id: str,
        *,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        return self._submit(self._client.update_group(group_id, name=name, description=description))

    def upsert_group_member(
        self,
        group_id: str,
        member_id: str,
        *,
        role: str = "member",
    ) -> dict[str, Any]:
        return self._submit(self._client.upsert_group_member(group_id, member_id, role=role))

    def remove_group_member(self, group_id: str, member_id: str) -> dict[str, Any]:
        return self._submit(self._client.remove_group_member(group_id, member_id))

    def create_discussion(
        self,
        group_id: str,
        topic: str,
        participant_ids: list[str] | tuple[str, ...],
        *,
        max_rounds: int = 2,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.create_discussion(group_id, topic, participant_ids, max_rounds=max_rounds)
        )

    def list_discussions(self, *, group_id: str | None = None) -> list[dict[str, Any]]:
        return self._submit(self._client.list_discussions(group_id=group_id))

    def get_discussion(self, discussion_id: int) -> dict[str, Any]:
        return self._submit(self._client.get_discussion(discussion_id))

    def update_discussion(self, discussion_id: int, *, status: str) -> dict[str, Any]:
        return self._submit(self._client.update_discussion(discussion_id, status=status))

    def append_discussion_turn(
        self,
        discussion_id: int,
        *,
        message_id: int,
        stance: str,
        target_member_id: str | None = None,
        round_index: int = 1,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.append_discussion_turn(
                discussion_id,
                message_id=message_id,
                stance=stance,
                target_member_id=target_member_id,
                round_index=round_index,
            )
        )

    def list_discussion_turns(self, discussion_id: int) -> list[dict[str, Any]]:
        return self._submit(self._client.list_discussion_turns(discussion_id))

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

    def create_task_schedule(
        self,
        target_member_id: str,
        content: str,
        *,
        title: str | None = None,
        run_at: datetime | str | None = None,
        interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        return self._submit(
            self._client.create_task_schedule(
                target_member_id,
                content,
                title=title,
                run_at=run_at,
                interval_seconds=interval_seconds,
            )
        )

    def list_task_schedules(
        self,
        *,
        target_member_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._submit(self._client.list_task_schedules(target_member_id=target_member_id, status=status))

    def get_task_schedule(self, schedule_id: int) -> dict[str, Any]:
        return self._submit(self._client.get_task_schedule(schedule_id))

    def update_task_schedule(self, schedule_id: int, *, status: str) -> dict[str, Any]:
        return self._submit(self._client.update_task_schedule(schedule_id, status=status))

    def run_due_task_schedules(self) -> dict[str, Any]:
        return self._submit(self._client.run_due_task_schedules())

    def fetch_history(
        self,
        *,
        before: int | None = None,
        since: int | None = None,
        q: str | None = None,
        group_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._submit(
            self._client.fetch_history(before=before, since=since, q=q, group_id=group_id, limit=limit)
        )

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
