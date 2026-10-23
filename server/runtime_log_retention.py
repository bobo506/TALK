"""Automatic local retention worker. Explicit configuration only, no UI actions."""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from pathlib import Path

from sqlalchemy import or_, select

from bridges import runtime_log_retention as retention
from server.models import AgentTask, AgentTaskRelation
from server.runtime_diagnostics_sources import RuntimeDiagnosticsProvider

logger = logging.getLogger("talk")


@contextlib.contextmanager
def task_guard(engine, project, member, task_ids):
    """Short non-blocking SQLite write reservation; no task data is changed.

    The reservation prevents a task being resumed/reassigned between the
    terminal-state check and filesystem expiration. Busy DB means protect.
    """
    with engine.connect() as conn:
        previous = conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        try:
            conn.exec_driver_sql("PRAGMA busy_timeout=0")
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            # Walk both directions, including ancestors of the logged tasks.
            # A missing/foreign/unfinished connected task or bounded-out graph
            # protects the run. Cycles terminate via visited IDs.
            safe = bool(task_ids) and len(task_ids) <= retention.MAX_TASKS and all(
                type(i) is int and i > 0 for i in task_ids)
            pending, visited = set(task_ids), set()
            deadline = time.monotonic() + .1
            while safe and pending:
                if len(visited | pending) > retention.MAX_TASKS or time.monotonic() >= deadline:
                    safe = False
                    break
                ids = list(pending)[:128]
                pending.difference_update(ids)
                found = {}
                statement = select(AgentTask.id, AgentTask.project_id, AgentTask.target_member_id,
                    AgentTask.status, AgentTask.workflow_status, AgentTask.control_status,
                    AgentTask.parent_task_id, AgentTask.root_task_id,
                    AgentTask.execution_session).where(AgentTask.id.in_(ids))
                for row in conn.execute(statement).mappings():
                    found[row["id"]] = row
                for task_id in ids:
                    row = found.get(task_id)
                    if (row is None or row["project_id"] != project
                            or (task_id in task_ids and row["target_member_id"] != member)
                            or row["status"] not in {"succeeded", "failed", "canceled"}
                            or row["workflow_status"] not in {"completed", "canceled"}
                            or row["control_status"] != "active"):
                        safe = False
                        break
                    session = row["execution_session"]
                    if session is not None and not isinstance(session, dict):
                        safe = False
                        break
                    for ref in (row["parent_task_id"], row["root_task_id"],
                                (session or {}).get("base_task_id")):
                        if ref is not None:
                            if type(ref) is not int or ref <= 0:
                                safe = False
                                break
                            pending.add(ref)
                if not safe:
                    break
                direct = select(AgentTask.id).where(or_(
                    AgentTask.parent_task_id.in_(ids), AgentTask.root_task_id.in_(ids),
                    AgentTask.execution_session["base_task_id"].as_integer().in_(ids))).limit(retention.MAX_TASKS+1)
                related = select(AgentTaskRelation.source_task_id, AgentTaskRelation.target_task_id,
                                 AgentTaskRelation.trigger_task_id).where(or_(
                        AgentTaskRelation.source_task_id.in_(ids), AgentTaskRelation.target_task_id.in_(ids),
                        AgentTaskRelation.trigger_task_id.in_(ids))).limit(retention.MAX_TASKS+1)
                pending.update(conn.execute(direct).scalars())
                relations = conn.execute(related).all()
                if len(relations) > retention.MAX_TASKS:
                    safe = False
                    break
                pending.update(ref for row in relations for ref in row if ref is not None)
                visited.update(ids)
                pending.difference_update(visited)
            yield safe
        finally:
            conn.rollback()
            conn.exec_driver_sql(f"PRAGMA busy_timeout={int(previous)}")


class RetentionService:
    def __init__(self, engine, config, *, clock=retention.utcnow, poll_seconds=30):
        self.engine, self.clock, self.poll_seconds = engine, clock, poll_seconds
        self.stop_event = threading.Event()
        self.thread = None
        self.groups = {}
        section = config.get("runtime_log_retention", {})
        if (not isinstance(section, dict)
                or set(section) - {"enabled", "retention_days", "max_total_bytes", "interval_seconds"}
                or type(section.get("enabled", False)) is not bool):
            raise ValueError("retention_config_invalid")
        self.enabled = isinstance(section, dict) and section.get("enabled") is True
        self.policy = {}
        if not self.enabled:
            return
        storage = config.get("storage")
        configured_db = storage.get("db_path") if isinstance(storage, dict) else None
        actual_db = engine.url.database
        if (not isinstance(configured_db, str) or not configured_db.strip()
                or not Path(configured_db).is_absolute()
                or engine.dialect.name != "sqlite" or not actual_db or actual_db == ":memory:"
                or Path(configured_db).resolve() != Path(actual_db).resolve()):
            # Missing binding, TestClient and alternate databases cannot act on sources.
            self.enabled = False
            return
        if retention.os.name != "nt":
            self.enabled = False
            logger.error("Log retention unavailable: unsupported platform")
            return
        provider = RuntimeDiagnosticsProvider.from_config(config)
        if provider._config_error:
            raise ValueError("retention_sources_invalid")
        for source in provider.sources:
            root = Path(source.root)
            with retention.pinned(root), retention.NativeFile(root, directory=True) as handle:
                canonical = handle.path
            self.groups.setdefault(canonical, set()).add((source.project_id, source.member_id))
        self.policy = {
            "retention_days": section.get("retention_days", 30),
            "max_total_bytes": section.get("max_total_bytes", 1024**3),
            "interval_seconds": section.get("interval_seconds", 86400),
        }
        days, size, interval = self.policy.values()
        import math
        if (type(days) not in (int, float) or not math.isfinite(days) or not 0 < days <= 36500
                or type(size) is not int or not 1 <= size <= 2**63-1
                or type(interval) is not int or not 60 <= interval <= 604800):
            raise ValueError("retention_policy_invalid")

    def tick(self):
        result = []
        for root, scopes in self.groups.items():
            if self.stop_event.is_set():
                break
            result.append(retention.sweep(root, scopes,
                lambda p, m, ids: task_guard(self.engine, p, m, ids),
                now=self.clock(), stop=self.stop_event, **self.policy))
        return result

    def start(self):
        if not self.enabled or self.thread is not None:
            return
        def work():
            while not self.stop_event.is_set():
                try:
                    self.tick()  # Startup catch-up; the root's persisted due time gates later ticks.
                except Exception as exc:
                    logger.error("Log retention degraded: %s", type(exc).__name__)
                self.stop_event.wait(self.poll_seconds)
        self.thread = threading.Thread(target=work, name="talk-log-retention", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                logger.error("Log retention shutdown pending")
