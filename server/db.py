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
        # ROLE-BINDING-B1b（合同 §7.1/§10）：按列存在性幂等增列，只 ADD COLUMN、
        # 不重建表、不改列类型、不删除列，**不回填旧任务**（旧行的两列保持 NULL）。
        if "target_binding_snapshot" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN target_binding_snapshot JSON"
            )
        if "target_binding_state" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN target_binding_state TEXT"
            )
        # 292：只 ADD 可空列/JSON，不回填旧行；旧任务字段保持 NULL 即旧行为。
        if "execution_session" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN execution_session JSON"
            )
        if "execution_session_base_text" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN execution_session_base_text TEXT"
            )
        if "execution_session_state" not in task_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_tasks ADD COLUMN execution_session_state JSON"
            )
        if "execution_session_audit" not in task_columns:
            conn.exec_driver_sql("ALTER TABLE agent_tasks ADD COLUMN execution_session_audit JSON")
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
        project_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(projects)").fetchall()
        }
        if "development_requirements" not in project_columns:
            conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN development_requirements TEXT")
        # C1a 主控模式意向/版本：老库兼容幂等增列，旧行由 DEFAULT 得到 passive / 0，
        # 不重建表、不删除或改写既有数据。
        if "controller_mode" not in project_columns:
            conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN controller_mode TEXT NOT NULL DEFAULT 'passive'"
            )
        if "controller_mode_version" not in project_columns:
            conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN controller_mode_version INTEGER NOT NULL DEFAULT 0"
            )
        # C1b-S1 长期主控指定/版本：同样按列存在性幂等增列。旧项目保持“未指定 / 0”，
        # 不自动指定 lead / Codex，也不改写既有数据。
        if "controller_member_id" not in project_columns:
            conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN controller_member_id TEXT")
        if "controller_assignment_version" not in project_columns:
            conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN controller_assignment_version INTEGER NOT NULL DEFAULT 0"
            )
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
        # 角色生命周期 R1-1（合同 §4.2）：只增列、只加索引，不重建表、不改旧行。
        # 旧运行器一律 control_kind='unknown'（页面不提供启动按钮）。
        runner_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(runner_registry)").fetchall()
        }
        if "control_kind" not in runner_columns:
            conn.exec_driver_sql(
                "ALTER TABLE runner_registry ADD COLUMN control_kind TEXT NOT NULL DEFAULT 'unknown'"
            )
        instance_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(agent_instances)").fetchall()
        }
        if "project_id" not in instance_columns:
            conn.exec_driver_sql("ALTER TABLE agent_instances ADD COLUMN project_id TEXT")
        if "process_started_at" not in instance_columns:
            conn.exec_driver_sql(
                "ALTER TABLE agent_instances ADD COLUMN process_started_at TIMESTAMP"
            )
        if "launch_id" not in instance_columns:
            conn.exec_driver_sql("ALTER TABLE agent_instances ADD COLUMN launch_id TEXT")
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
        # ROLE-BINDING-B1a：runner_registry / project_role_bindings 两张新表由
        # ``SQLModel.metadata.create_all`` 建表（旧库同样只新增表）。这里按列存在性之外
        # 的幂等索引补齐（表已存在时 create_all 不会补索引）；只增量、不重建表、
        # 不改列类型、不删除列，也不改全局 SQLite 引擎参数。
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_runner_registry_runtime "
            "ON runner_registry (runtime)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_runner_registry_adapter_status "
            "ON runner_registry (adapter_status)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_project_role_bindings_project_id "
            "ON project_role_bindings (project_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_project_role_bindings_runner_id "
            "ON project_role_bindings (runner_id)"
        )
        # 2026-10-28：绑定行增加准备阶段从官方模型目录取回的默认思考强度（仅展示，可空）。
        # 旧行保持 NULL，列表不显示强度；不参与六维指纹与有效性判定。
        binding_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(project_role_bindings)"
            ).fetchall()
        }
        if "default_effort" not in binding_columns:
            conn.exec_driver_sql(
                "ALTER TABLE project_role_bindings ADD COLUMN default_effort TEXT"
            )
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_member_id ON group_members (member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_role ON group_members (role)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_business_role ON group_members (business_role)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_group_members_decision_tier ON group_members (decision_tier)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_members_disabled_at ON members (disabled_at)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_member_id ON agent_instances (member_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_runtime ON agent_instances (runtime)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_agent_instances_status ON agent_instances (status)")
        # 角色生命周期 R1-1（合同 §4.1.1/§4.1.3/§4.1.4/§4.4）：新表由 create_all 建，
        # 这里补齐幂等索引（表已存在时 create_all 不会补索引）；只增量、不重建表。
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_runner_registry_control_kind "
            "ON runner_registry (control_kind)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_instances_project_id "
            "ON agent_instances (project_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_instances_launch_id "
            "ON agent_instances (launch_id)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_runner_model_choices_dim "
            "ON runner_model_choices (runner_id, model_id, model_source, provider_id, "
            "connection_ref, model_alias)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_runner_model_choices_runner "
            "ON runner_model_choices (runner_id, retired_at)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_project_roles_active_name "
            "ON project_roles (project_id, role_name) WHERE archived_at IS NULL"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_project_roles_member ON project_roles (member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_creation_operations_member "
            "ON role_creation_operations (member_id)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_role_creation_operations_identity "
            "ON role_creation_operations (project_id, member_id)"
        )
        # 存量角色补录（ROLE_LEGACY_ATTACH_DESIGN §原子补录、幂等与来源）：新表由
        # ``create_all`` 增量创建（旧库只多一张表），这里补齐幂等索引。补录**不**自动执行：
        # 没有任何回填、不重建旧表、不改历史角色/名册/绑定，重复 init_db() 幂等。
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_role_legacy_attach_operations_identity "
            "ON role_legacy_attach_operations (project_id, member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_legacy_attach_operations_project_id "
            "ON role_legacy_attach_operations (project_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_legacy_attach_operations_member_id "
            "ON role_legacy_attach_operations (member_id)"
        )
        # 角色生命周期 R1-2（PROVISION_CONTRACT §1）：跨宿主作业表由 create_all 建，
        # 这里补齐幂等索引；只增量、不重建表、不新增迁移回填，重复 init_db() 不改旧行。
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_jobs_project "
            "ON role_provision_jobs (project_id, member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_jobs_status "
            "ON role_provision_jobs (status)"
        )
        # R1-2 补正 F1：作业代际需要绑定角色凭据版本快照。表已存在时只增量补列，
        # 不改旧行（旧行按默认 1 解释），重复 init_db() 无副作用。
        provision_job_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(role_provision_jobs)"
            ).fetchall()
        }
        if "credential_version" not in provision_job_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_provision_jobs "
                "ADD COLUMN credential_version INTEGER NOT NULL DEFAULT 1"
            )
        # 角色生命周期 R1-3（合同 §4.1.5/§4.1.6/§4.4）：两张服务生命周期表由
        # ``SQLModel.metadata.create_all`` 建表（旧库同样只新增表），这里补齐幂等索引。
        # 索引幂等、不重建表、不改列类型、不回填旧行，重复 ``init_db()`` 无副作用。
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_role_service_launches_generation "
            "ON role_service_launches (project_id, member_id, generation)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_launches_state_expiry "
            "ON role_service_launches (state, launch_expires_at)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_launches_role "
            "ON role_service_launches (project_id, member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_launches_project_id "
            "ON role_service_launches (project_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_launches_member_id "
            "ON role_service_launches (member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_state_member_id "
            "ON role_service_state (member_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_service_state_current_launch_id "
            "ON role_service_state (current_launch_id)"
        )
        # R1-3 返修 F2：``role_service_state`` 需要区分“宿主已 spawn 的失败”与
        # “纯预检失败的失败”。旧库只增量补一个可空列，不回填、不改旧行；旧行按
        # ``NULL``（未知）解释，报告时回退按 pid 判断。重复 init_db() 无副作用。
        state_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(role_service_state)"
            ).fetchall()
        }
        if "spawned" not in state_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_service_state ADD COLUMN spawned BOOLEAN"
            )
        # 角色生命周期 R1-4a（REQUEST_CONTRACT §2）：三张请求/配置/轮换表由
        # ``SQLModel.metadata.create_all`` 建表（旧库只新增表），这里补齐幂等索引与
        # 两个**部分唯一索引**。只增量、不重建表、不回填旧行，重复 ``init_db()`` 无副作用。
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_requests_project_status "
            "ON role_provision_requests (project_id, status)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_requests_project_origin "
            "ON role_provision_requests (project_id, origin_operation_key)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_requests_project_member "
            "ON role_provision_requests (project_id, member_id)"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ux_role_provision_requests_active_create_name "
            "ON role_provision_requests (project_id, role_name) "
            "WHERE kind = 'create' "
            "AND status IN ('requested','leased','created')"
        )
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ux_role_provision_requests_active_recover_member "
            "ON role_provision_requests (project_id, member_id) "
            "WHERE kind = 'recover' "
            "AND status IN ('requested','leased','created')"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_credential_rotations_member "
            "ON role_credential_rotations (project_id, member_id)"
        )
        # 角色生命周期 R1-4c-a（AUTO_START_DESIGN §2）：``role_provision_requests``
        # 增量 4 列 + 1 普通索引，全部按列存在性幂等 ADD COLUMN；旧行由默认值
        # ``0/NULL/NULL/NULL`` 得到“无意图”，不重建表、不回填、不改写旧行，
        # 重复 init_db() 无副作用。
        role_request_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(role_provision_requests)"
            ).fetchall()
        }
        if "auto_start_intent" not in role_request_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_provision_requests "
                "ADD COLUMN auto_start_intent INTEGER NOT NULL DEFAULT 0"
            )
        if "auto_start_status" not in role_request_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_provision_requests "
                "ADD COLUMN auto_start_status TEXT"
            )
        if "auto_start_launch_id" not in role_request_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_provision_requests "
                "ADD COLUMN auto_start_launch_id TEXT"
            )
        if "auto_start_error_code" not in role_request_columns:
            conn.exec_driver_sql(
                "ALTER TABLE role_provision_requests "
                "ADD COLUMN auto_start_error_code TEXT"
            )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_role_provision_requests_auto_start_launch "
            "ON role_provision_requests (auto_start_launch_id)"
        )
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
        # ROLE-BINDING-B1b：仅新增任务快照状态索引；不新增任何回执/计数列。
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agent_tasks_target_binding_state "
            "ON agent_tasks (target_binding_state)"
        )
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
        # 角色生命周期 R1-1 一次性权限策略迁移（合同 §8.3）：
        # 仅当迁移标记不存在时，把当时的 decision_tier='decision' 名册行回填为
        # review_exempt=1 / source='migration_decision_tier'；回填与标记**同一事务**。
        # 标记存在即跳过，因此重复 init_db() 不会重跑，也不会覆盖 human 后续的人工改权；
        # 迁移只改“策略来源”，不扩大权限（非 decision 行不产生策略行）。
        migration_key = server.models.ROLE_POLICY_MIGRATION_KEY
        migration_applied = conn.exec_driver_sql(
            "SELECT key FROM schema_migrations WHERE key = ?", (migration_key,)
        ).fetchone()
        if migration_applied is None:
            conn.exec_driver_sql(
                """
                INSERT OR IGNORE INTO project_role_policies (
                    project_id, member_id, review_exempt, source,
                    granted_by, granted_at, updated_at
                )
                SELECT
                    project_id, member_id, 1, ?,
                    NULL, datetime('now'), datetime('now')
                FROM project_agents
                WHERE decision_tier = 'decision'
                """,
                (server.models.PROJECT_ROLE_POLICY_SOURCE_MIGRATION,),
            )
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO schema_migrations (key, applied_at) VALUES (?, datetime('now'))",
                (migration_key,),
            )
        conn.commit()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLModel session."""
    with Session(engine) as session:
        yield session


def begin_immediate_write(session: Session) -> bool:
    """把当前 ``Session`` 提升为**真实 SQLite 写事务**（``BEGIN IMMEDIATE``）。

    角色生命周期 R1-1 的引用守卫（合同 §7.5 第 3 条）与 TX-ALL（§7.2）要求
    “校验读取”和“新增写入”落在**同一个实际写事务**里。但 SQLAlchemy 的
    ``Session.in_transaction`` 只是 ORM 逻辑事务：pysqlite 在首个 DML 之前不会真正
    ``BEGIN``，因此守卫读取时 ``driver_connection.in_transaction`` 仍是 ``False``，
    读校验并不在写锁内（这正是独立探针 F2 观察到的事实）。

    本函数显式发一次 ``BEGIN IMMEDIATE`` 取得 SQLite 写锁，使同一 Session 随后的
    读取与写入都处于同一个实际写事务；并发写者要么在锁上等待，要么在提交后读到
    最新事实。只影响调用方自己的连接，**不修改**全局引擎参数、不做隔离级别或
    ``get_session`` 读事务策略的全局调整。

    已经处于实际事务中（同一请求里先发生过 DML）时不重复 ``BEGIN``，直接复用；
    这种情形下写锁已由前一条写语句取得，守卫仍在同一实际写事务内。

    返回 ``True`` 表示本次调用真正取得写锁，``False`` 表示复用了已存在的实际事务。
    """
    connection = session.connection()
    driver = connection.connection.driver_connection
    if driver is not None and bool(getattr(driver, "in_transaction", False)):
        return False
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    return True
