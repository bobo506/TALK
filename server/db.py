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
        if "group_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN group_id TEXT REFERENCES groups(id)")
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
        task_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(agent_tasks)").fetchall()
        }
        if "schedule_id" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN schedule_id INTEGER REFERENCES agent_task_schedules(id)")
        if "project_id" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN project_id TEXT REFERENCES projects(project_id)")
        if "hall_group_id" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN hall_group_id TEXT REFERENCES groups(id)")
        if "workflow_status" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN workflow_status TEXT NOT NULL DEFAULT 'assigned'"
            )
            conn.exec_driver_sql(
                """
                UPDATE agent_tasks
                SET workflow_status = CASE status
                    WHEN 'running' THEN 'in_progress'
                    WHEN 'succeeded' THEN 'submitted'
                    WHEN 'failed' THEN 'failed'
                    WHEN 'canceled' THEN 'canceled'
                    ELSE 'assigned'
                END
                """
            )
        if "result_collected_at" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN result_collected_at TIMESTAMP")
        if "attempt" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0")
        if "claim_token" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN claim_token TEXT")
        if "lease_expires_at" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN lease_expires_at TIMESTAMP")
        if "heartbeat_at" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN heartbeat_at TIMESTAMP")
        if "parent_task_id" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN parent_task_id INTEGER REFERENCES agent_tasks(id)"
            )
        if "root_task_id" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN root_task_id INTEGER REFERENCES agent_tasks(id)"
            )
        if "delegation_depth" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN delegation_depth INTEGER NOT NULL DEFAULT 0"
            )
        if "may_delegate" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN may_delegate INTEGER NOT NULL DEFAULT 0"
            )
        if "max_delegation_depth" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN max_delegation_depth INTEGER")
        if "max_running_descendants" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN max_running_descendants INTEGER")
        if "max_running_per_target" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN max_running_per_target INTEGER")
        if "max_nonterminal_descendants" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN max_nonterminal_descendants INTEGER")
        if "control_status" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN control_status TEXT")
        if "authorization_epoch" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN authorization_epoch INTEGER")
        if "authorized_slice_budget" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN authorized_slice_budget INTEGER")
        if "reserved_slice_count" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN reserved_slice_count INTEGER")
        if "authorization_expires_at" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN authorization_expires_at TIMESTAMP")
        if "checkpoint_reason" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN checkpoint_reason TEXT")
        if "milestone_test_required" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN milestone_test_required INTEGER NOT NULL DEFAULT 0"
            )
        if "max_clarification_rounds" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN max_clarification_rounds INTEGER NOT NULL DEFAULT 1"
            )
        if "clarification_round_count" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN clarification_round_count INTEGER NOT NULL DEFAULT 0"
            )
        if "task_kind" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN task_kind TEXT NOT NULL DEFAULT 'general'"
            )
        if "review_policy" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN review_policy TEXT")
        if "gate_verdict" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN gate_verdict JSON")
        conn.exec_driver_sql(
            """
            UPDATE agent_tasks
            SET
              max_clarification_rounds = COALESCE(max_clarification_rounds, ?),
              clarification_round_count = COALESCE(clarification_round_count, 0),
              task_kind = COALESCE(task_kind, 'general'),
              milestone_test_required = COALESCE(milestone_test_required, 0)
            """,
            (server.models.TASK_MAX_CLARIFICATION_ROUNDS_DEFAULT,),
        )
        conn.exec_driver_sql(
            "UPDATE agent_tasks SET root_task_id = id WHERE root_task_id IS NULL"
        )
        conn.exec_driver_sql(
            """
            UPDATE agent_tasks
            SET
              max_delegation_depth = COALESCE(max_delegation_depth, ?),
              max_running_descendants = COALESCE(max_running_descendants, ?),
              max_running_per_target = COALESCE(max_running_per_target, ?),
              max_nonterminal_descendants = COALESCE(max_nonterminal_descendants, ?)
            WHERE parent_task_id IS NULL
            """,
            (
                server.models.TASK_MAX_DELEGATION_DEPTH_DEFAULT,
                server.models.TASK_MAX_RUNNING_DESCENDANTS_DEFAULT,
                server.models.TASK_MAX_RUNNING_PER_TARGET_DEFAULT,
                server.models.TASK_MAX_NONTERMINAL_DESCENDANTS_DEFAULT,
            ),
        )
        conn.exec_driver_sql(
            """
            UPDATE agent_tasks
            SET
              control_status = COALESCE(control_status, 'active'),
              authorization_epoch = COALESCE(
                authorization_epoch,
                CASE WHEN may_delegate = 1 THEN 1 ELSE 0 END
              ),
              authorized_slice_budget = COALESCE(
                authorized_slice_budget,
                CASE WHEN may_delegate = 1 THEN ? ELSE 0 END
              ),
              reserved_slice_count = COALESCE(
                reserved_slice_count,
                CASE
                  WHEN may_delegate = 1 THEN (
                    SELECT COUNT(*)
                    FROM agent_tasks AS child
                    WHERE child.root_task_id = agent_tasks.id
                      AND child.parent_task_id IS NOT NULL
                  )
                  ELSE 0
                END
              ),
              authorization_expires_at = CASE
                WHEN may_delegate = 1 THEN COALESCE(
                  authorization_expires_at,
                  datetime('now', '+' || ? || ' seconds')
                )
                ELSE NULL
              END
            WHERE parent_task_id IS NULL
            """,
            (
                server.models.TASK_AUTHORIZED_SLICE_BUDGET_DEFAULT,
                server.models.TASK_AUTHORIZATION_TTL_DEFAULT_SECONDS,
            ),
        )
        discussion_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(discussion_sessions)").fetchall()
        }
        if "root_message_id" not in discussion_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_sessions ADD COLUMN root_message_id INTEGER REFERENCES messages(id)")
        if "requester_id" not in discussion_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_sessions ADD COLUMN requester_id TEXT REFERENCES members(id)")
        if "assignee_id" not in discussion_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_sessions ADD COLUMN assignee_id TEXT REFERENCES members(id)")
        if "scope_text" not in discussion_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_sessions ADD COLUMN scope_text TEXT")
        if "end_reason" not in discussion_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_sessions ADD COLUMN end_reason TEXT")
        discussion_turn_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(discussion_turns)").fetchall()
        }
        if "turn_kind" not in discussion_turn_columns:
            conn.exec_driver_sql("ALTER TABLE discussion_turns ADD COLUMN turn_kind TEXT NOT NULL DEFAULT 'reply'")
        group_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(groups)").fetchall()
        }
        if "project_id" not in group_columns:
            conn.exec_driver_sql("ALTER TABLE groups ADD COLUMN project_id TEXT REFERENCES projects(project_id)")
        if "type" not in group_columns:
            conn.exec_driver_sql("ALTER TABLE groups ADD COLUMN type TEXT NOT NULL DEFAULT 'free'")
        group_member_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(group_members)").fetchall()
        }
        if "business_role" not in group_member_columns:
            conn.exec_driver_sql("ALTER TABLE group_members ADD COLUMN business_role TEXT")
        if "decision_tier" not in group_member_columns:
            conn.exec_driver_sql("ALTER TABLE group_members ADD COLUMN decision_tier TEXT")
        project_agent_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(project_agents)").fetchall()
        }
        if "business_role" not in project_agent_columns:
            conn.exec_driver_sql("ALTER TABLE project_agents ADD COLUMN business_role TEXT")
        if "decision_tier" not in project_agent_columns:
            conn.exec_driver_sql("ALTER TABLE project_agents ADD COLUMN decision_tier TEXT")
        if "capability_summary" not in project_agent_columns:
            conn.exec_driver_sql(
                "ALTER TABLE project_agents ADD COLUMN capability_summary JSON NOT NULL DEFAULT '[]'"
            )
        member_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(members)").fetchall()
        }
        if "disabled_at" not in member_columns:
            conn.exec_driver_sql("ALTER TABLE members ADD COLUMN disabled_at TIMESTAMP")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_files_sha256 ON files (sha256)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_messages_from_id ON messages (from_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_messages_group_id ON messages (group_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_messages_to_ids ON messages (to_ids)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_groups_created_by ON groups (created_by)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_groups_project_id ON groups (project_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_groups_type ON groups (type)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_projects_maintainer_member_id ON projects (maintainer_member_id)")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_project_agents_business_role "
            "ON project_agents (business_role)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_project_agents_decision_tier "
            "ON project_agents (decision_tier)"
        )
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_member_id ON group_members (member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_role ON group_members (role)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_business_role ON group_members (business_role)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_decision_tier ON group_members (decision_tier)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_members_disabled_at ON members (disabled_at)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_member_id ON agent_instances (member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_runtime ON agent_instances (runtime)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_status ON agent_instances (status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_target_member_id ON agent_tasks (target_member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_created_by ON agent_tasks (created_by)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_status ON agent_tasks (status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_claimed_by ON agent_tasks (claimed_by)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_instance_id ON agent_tasks (instance_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_schedule_id ON agent_tasks (schedule_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_project_id ON agent_tasks (project_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_parent_task_id ON agent_tasks (parent_task_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_root_task_id ON agent_tasks (root_task_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_delegation_depth ON agent_tasks (delegation_depth)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_control_status ON agent_tasks (control_status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_task_kind ON agent_tasks (task_kind)")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_milestone_test_required "
            "ON agent_tasks (milestone_test_required)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_review_policy ON agent_tasks (review_policy)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_authorization_expires_at ON agent_tasks (authorization_expires_at)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_tasks_hall_group_id ON agent_tasks (hall_group_id)"
        )
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_workflow_status ON agent_tasks (workflow_status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_tasks_lease_expires_at ON agent_tasks (lease_expires_at)")
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_clarification_rounds_task_id "
            "ON agent_task_clarification_rounds (task_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_clarification_rounds_status "
            "ON agent_task_clarification_rounds (status)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_clarification_round_index "
            "ON agent_task_clarification_rounds (task_id, round_index)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_relations_source_task_id "
            "ON agent_task_relations (source_task_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_relations_target_task_id "
            "ON agent_task_relations (target_task_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_relations_relation_type "
            "ON agent_task_relations (relation_type)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_relations_trigger_task_id "
            "ON agent_task_relations (trigger_task_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_task_relations_round_index "
            "ON agent_task_relations (round_index)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_relation_source_target_type "
            "ON agent_task_relations (source_task_id, target_task_id, relation_type)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_relation_type_target_round "
            "ON agent_task_relations (relation_type, target_task_id, round_index)"
        )
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_task_schedules_target_member_id ON agent_task_schedules (target_member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_task_schedules_created_by ON agent_task_schedules (created_by)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_task_schedules_schedule_type ON agent_task_schedules (schedule_type)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_task_schedules_status ON agent_task_schedules (status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_task_schedules_next_run_at ON agent_task_schedules (next_run_at)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_group_id ON discussion_sessions (group_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_created_by ON discussion_sessions (created_by)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_root_message_id ON discussion_sessions (root_message_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_requester_id ON discussion_sessions (requester_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_assignee_id ON discussion_sessions (assignee_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_status ON discussion_sessions (status)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_sessions_end_reason ON discussion_sessions (end_reason)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_session_id ON discussion_turns (session_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_turn_index ON discussion_turns (turn_index)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_message_id ON discussion_turns (message_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_speaker_id ON discussion_turns (speaker_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_target_member_id ON discussion_turns (target_member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_turn_kind ON discussion_turns (turn_kind)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_stance ON discussion_turns (stance)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_discussion_turns_round_index ON discussion_turns (round_index)")
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
