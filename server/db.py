"""Database initialization and configuration loading."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

# ── Config ───────────────────────────────────────────────────────────

_CFG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def _load_config() -> dict:
    with open(_CFG_PATH, "rb") as f:
        return tomllib.load(f)


CONFIG = _load_config()

HOST: str = CONFIG["server"]["host"]
PORT: int = CONFIG["server"]["port"]
PUBLIC_URL: str = CONFIG["server"]["public_url"]
WS_PING_INTERVAL: int = CONFIG["server"].get("ws_ping_interval", 20)
WS_PING_TIMEOUT: int = CONFIG["server"].get("ws_ping_timeout", 45)
REVOKE_WINDOW_SEC: int = CONFIG["server"].get("revoke_window_sec", 120)
LOG_PATH: Path = Path(CONFIG.get("logging", {}).get("path", "./logs/talk.log"))
LOG_LEVEL: str = str(CONFIG.get("logging", {}).get("level", "INFO")).upper()
BACKUP_DIR: Path = Path(CONFIG.get("backup", {}).get("dir", "./backups"))
BACKUP_KEEP_LAST: int = int(CONFIG.get("backup", {}).get("keep_last", 7))
UPLOAD_MAX_MB: int = CONFIG["storage"]["upload_max_mb"]
FILE_RETENTION_DAYS: int = CONFIG["storage"].get("file_retention_days", 0)
STORAGE_DIR: Path = Path(CONFIG["storage"]["storage_dir"])
DB_PATH: str = CONFIG["storage"]["db_path"]

# ── Engine ───────────────────────────────────────────────────────────

_db_url = f"sqlite:///{DB_PATH}"
engine = create_engine(_db_url, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create all tables if they don't exist."""
    # Import models so SQLModel.metadata knows about them
    import server.models  # noqa: F401

    SQLModel.metadata.create_all(engine)

    # Enable WAL mode for better concurrent read performance
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(messages)").fetchall()
        }
        if "caption" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN caption TEXT")
        if "filename" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN filename TEXT")
        if "size_bytes" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN size_bytes INTEGER")
        if "mime" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN mime TEXT")
        if "reply_to" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN reply_to INTEGER REFERENCES messages(id)")
        if "revoked_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN revoked_at TIMESTAMP")
        if "revoked_by" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN revoked_by TEXT")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_files_sha256 ON files (sha256)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_messages_from_id ON messages (from_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_messages_to_ids ON messages (to_ids)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_member_id ON agent_instances (member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_runtime ON agent_instances (runtime)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_status ON agent_instances (status)")
        conn.exec_driver_sql(
            """
            UPDATE messages
            SET
              filename = COALESCE(filename, (SELECT files.filename FROM files WHERE files.id = messages.file_id)),
              size_bytes = COALESCE(size_bytes, (SELECT files.size_bytes FROM files WHERE files.id = messages.file_id)),
              mime = COALESCE(mime, (SELECT files.mime FROM files WHERE files.id = messages.file_id)),
              content = COALESCE(content, (SELECT files.filename FROM files WHERE files.id = messages.file_id))
            WHERE type = 'file' AND file_id IS NOT NULL
            """
        )
        conn.commit()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLModel session."""
    with Session(engine) as session:
        yield session
