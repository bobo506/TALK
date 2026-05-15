"""FastAPI entry point for TALK platform."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from server.auth import resolve_member_by_key
from server.db import (
    FILE_RETENTION_DAYS,
    HOST,
    PORT,
    REVOKE_WINDOW_SEC,
    STORAGE_DIR,
    UPLOAD_MAX_MB,
    WS_PING_INTERVAL,
    WS_PING_TIMEOUT,
    engine,
    init_db,
)
from server.logging_config import configure_logging
from server.models import Member, MessageCreate
from server.routes import files, groups, instances, members, messages, tasks
from server.ws_hub import hub

configure_logging()
logger = logging.getLogger("talk")
START_TIME = time.monotonic()

WS_CLOSE_INVALID_API_KEY = 4001
WS_CLOSE_IDLE_TIMEOUT = 4002


def _format_validation_error(exc: ValidationError) -> str:
    return "; ".join(error["msg"] for error in exc.errors()) or "invalid websocket payload"


async def _send_ws_error(ws: WebSocket, error: str) -> None:
    await ws.send_json({"type": "send_ack", "ok": False, "error": error})


async def _heartbeat_loop(ws: WebSocket, state: dict[str, float]) -> None:
    while True:
        await asyncio.sleep(WS_PING_INTERVAL)

        if time.monotonic() - state["last_seen"] > WS_PING_TIMEOUT:
            await ws.close(code=WS_CLOSE_IDLE_TIMEOUT, reason="Ping timeout")
            return

        try:
            await ws.send_json({"type": "ping"})
        except Exception:
            return


async def _handle_ws_send_event(ws: WebSocket, member: Member, payload: object) -> None:
    try:
        body = MessageCreate.model_validate(payload)
    except ValidationError as exc:
        await _send_ws_error(ws, _format_validation_error(exc))
        return

    with Session(engine) as session:
        try:
            await messages.create_message(body, member, session)
        except HTTPException as exc:
            await _send_ws_error(ws, str(exc.detail))


async def _handle_ws_event(ws: WebSocket, member: Member, raw_text: str) -> None:
    try:
        event = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid WS JSON from %s", member.id)
        return

    if not isinstance(event, dict):
        logger.warning("Ignoring non-object WS event from %s", member.id)
        return

    event_type = event.get("type")
    if event_type == "pong":
        return
    if event_type == "ping":
        await ws.send_json({"type": "pong"})
        return
    if event_type == "send":
        await _handle_ws_send_event(ws, member, event.get("payload"))
        return

    logger.warning("Ignoring unsupported WS event from %s: %s", member.id, event_type)


def _check_db_health() -> str:
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")
    return "ok"


def _check_storage_health() -> str:
    storage_path = STORAGE_DIR.resolve()
    storage_path.mkdir(parents=True, exist_ok=True)
    probe_path = storage_path / ".healthcheck"
    probe_path.write_text("ok", encoding="utf-8")
    probe_path.unlink(missing_ok=True)
    return "ok"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http exception",
                extra={
                    "event": "exception",
                    "method": request.method,
                    "path": request.url.path,
                    "member_id": getattr(request.state, "member_id", None),
                },
            )
            raise

        logger.info(
            "http request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "cost_ms": round((time.perf_counter() - start) * 1000, 2),
                "member_id": getattr(request.state, "member_id", None),
            },
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database")
    init_db()
    with Session(engine) as session:
        cleanup_stats = files.purge_expired_files(session, FILE_RETENTION_DAYS)
    if FILE_RETENTION_DAYS > 0:
        logger.info(
            "Expired file cleanup finished",
            extra={
                "event": "startup_cleanup",
                "deleted": cleanup_stats["deleted"],
                "missing_on_disk": cleanup_stats["missing_on_disk"],
                "retention_days": FILE_RETENTION_DAYS,
            },
        )
    else:
        logger.info("Expired file cleanup disabled", extra={"event": "startup_cleanup_disabled"})
    logger.info("TALK server ready", extra={"event": "startup_ready", "host": HOST, "port": PORT})
    yield


app = FastAPI(title="TALK", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(members.router)
app.include_router(members.setup_router)
app.include_router(groups.router)
app.include_router(instances.router)
app.include_router(tasks.router)
app.include_router(messages.router)
app.include_router(files.router)


@app.get("/healthz")
def healthz():
    db_status = "ok"
    storage_status = "ok"
    http_status = 200

    try:
        db_status = _check_db_health()
    except Exception:
        logger.exception("healthz db check failed", extra={"event": "healthz_db_error"})
        db_status = "error"
        http_status = 503

    try:
        storage_status = _check_storage_health()
    except Exception:
        logger.exception("healthz storage check failed", extra={"event": "healthz_storage_error"})
        storage_status = "error"
        http_status = 503

    return JSONResponse(
        {
            "status": "ok" if http_status == 200 else "error",
            "db": db_status,
            "storage": storage_status,
            "uptime_sec": int(time.monotonic() - START_TIME),
            "online_members": hub.online_members_count(),
        },
        status_code=http_status,
    )


@app.get("/api/config")
def get_public_config():
    return {
        "revoke_window_sec": REVOKE_WINDOW_SEC,
        "max_upload_bytes": UPLOAD_MAX_MB * 1024 * 1024,
        "ws_ping_interval": WS_PING_INTERVAL,
        "ws_ping_timeout": WS_PING_TIMEOUT,
        "file_retention_days": FILE_RETENTION_DAYS,
    }


@app.get("/api/events")
async def sse_events(
    request: Request,
    token: str = Query(...),
):
    """Server-Sent Events stream authenticated via ?token=<api_key>."""
    with Session(engine) as session:
        member = resolve_member_by_key(token, session)

    if member is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    async def event_generator():
        queue = await hub.subscribe_events(member.id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=WS_PING_INTERVAL)
                    yield event
                except asyncio.TimeoutError:
                    yield hub.format_sse_event("ping", {})
        finally:
            await hub.unsubscribe_events(member.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(...),
):
    """WebSocket connection authenticated via ?token=<api_key>."""
    with Session(engine) as session:
        member = resolve_member_by_key(token, session)

    if member is None:
        await ws.close(code=WS_CLOSE_INVALID_API_KEY, reason="Invalid API key")
        return

    await hub.connect(member.id, ws)
    heartbeat_state = {"last_seen": time.monotonic()}
    heartbeat_task = asyncio.create_task(_heartbeat_loop(ws, heartbeat_state))

    try:
        while True:
            data = await ws.receive_text()
            heartbeat_state["last_seen"] = time.monotonic()
            await _handle_ws_event(ws, member, data)
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await hub.disconnect_and_broadcast(member.id, ws)


app.mount("/", StaticFiles(directory="web", html=True), name="web")
