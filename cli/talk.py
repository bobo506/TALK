"""`talk` CLI — project integration scaffolding.

Implements the `talk init` flow from ``docs/spec/PROJECT_INTEGRATION.md`` §3:
scaffold a project-local ``.talk/`` directory and (optionally) register the
project with a TALK server via ``POST /api/projects``.

Run as a module::

    python -m cli.talk init --name "自行车计划" --key bobo-key
    python -m cli.talk init --root /path/to/project --no-register

The server-facing pieces (`register_project`) accept an injectable HTTP client
so the flow can be exercised against an in-process FastAPI TestClient in tests.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import yaml

from cli.profiles import member_dir_name, member_id_from_dir_name

DEFAULT_SERVER = "http://127.0.0.1:8000"


# ── scaffolding ──────────────────────────────────────────────────────


def generate_project_id() -> str:
    """Generate a CLI-side project id, e.g. ``prj_a1b2c3d4e5f6``."""
    return f"prj_{uuid4().hex[:12]}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_yaml(path: Path, data: Any) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _agents_md(display_name: str) -> str:
    return f"""# {display_name} — TALK 项目协作规则

> 本文件由 `talk init` 生成，定义本项目接入 TALK 后**对所有 Agent 的组织级规则**。
> 个人语气/风格/边界属于各 Agent 自己的 `SOUL.md`，不写在这里
> （见 `agents/<member_id>/SOUL.md`，PROJECT_INTEGRATION §5.3.1）。

## Agent 决策分级

- **决策 Agent**：方向明确、无重大不确定项时可自主连续推进多个切片；遇产品方向、
  破坏性接口/数据变更、部署/权限风险或重大体验分歧时先确认。
- **执行 Agent**：每个切片完成后暂停、汇总进度，等决策 Agent 或项目管理者确认。
- 未明确声明分级的 Agent，默认按**执行 Agent** 处理。

## 切片节奏与提交

- 每完成一个可能影响功能的切片，都要：必要验证 → 更新进度 → 记录变更文件 → 提交可回溯版本。
- 连续开发带批次刹车：每次恢复默认最多 2 个明确切片；涉及数据库/协议/部署/跨模块时，
  默认 1 个切片后暂停汇总。

## 文档与语言

- 进度快照写 `docs/PROGRESS.md`，完整历史写 `docs/PROGRESS_HISTORY.md`。
- 面向人阅读的描述用中文；代码标识、API 路径、命令、配置键等技术字面量用反引号保留原文。

## 业务角色

业务角色（lead / dev / ui / tester / reviewer 等）在 `groups.yaml` 按群定义，
与决策分级是两个正交维度。
"""


def _agents_readme() -> str:
    return """# Agent Profiles

每个接入本项目的 Agent 在此目录下拥有一个 `<member_id>/` 子目录，存放其身份层四件套
（PROJECT_INTEGRATION §5.3）：

```
agents/
└── agent:<id>/
    ├── IDENTITY.md   # 必需 — 我是谁、Agent 类型、擅长领域
    ├── SOUL.md       # 必需 — 语气、决策风格、不可逾越的边界
    ├── USER.md       # 可选 — 这个项目里的搭档信息
    └── MEMORY.md     # 可选 — 长期记忆（或指向外部存储的指针）
```

用 `talk add-agent agent:<id>` 生成占位文件后按需填写。
身份层与 `AGENTS.md`（组织规则）职责分离：前者是个人规则，后者是项目统一要求。
"""


def scaffold_project(
    root: Path,
    *,
    display_name: str,
    server_url: str = DEFAULT_SERVER,
    description: Optional[str] = None,
    maintainer: Optional[str] = None,
    project_id: Optional[str] = None,
    create_default_group: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Create the ``.talk/`` directory tree under ``root``.

    Returns the project metadata that was written to ``project.yaml``.
    Raises ``FileExistsError`` if ``.talk/`` already exists and ``force`` is
    not set.
    """
    root = Path(root)
    talk_dir = root / ".talk"
    if talk_dir.exists() and not force:
        raise FileExistsError(f".talk already exists at {talk_dir} (use force to overwrite)")

    project_id = project_id or generate_project_id()
    (talk_dir / "agents").mkdir(parents=True, exist_ok=True)

    project_meta: dict[str, Any] = {
        "version": 1,
        "project_id": project_id,
        "display_name": display_name,
        "description": description,
        "talk_server": server_url,
        "created_at": _iso_now(),
        "maintainer": maintainer,
    }
    _write_yaml(talk_dir / "project.yaml", project_meta)

    groups_doc: dict[str, Any] = {"groups": []}
    if create_default_group:
        groups_doc["groups"].append(
            {"id": "group:default", "name": f"{display_name} 默认群", "members": []}
        )
    _write_yaml(talk_dir / "groups.yaml", groups_doc)

    _write_text(talk_dir / "AGENTS.md", _agents_md(display_name))
    _write_text(talk_dir / "agents" / "README.md", _agents_readme())
    _write_text(talk_dir / ".gitignore", "memory/\ncache/\n")

    return project_meta


def _agent_profile_files(member_id: str) -> dict[str, str]:
    return {
        "IDENTITY.md": (
            f"# {member_id} — IDENTITY\n\n"
            "## 名字\n<短名>\n\n"
            f"完整 ID：`{member_id}`，作为整体看待，不拆解。\n\n"
            "## Agent 类型\n<对话型 / 决策型代码 / ...>\n\n"
            "## 擅长领域\n- <...>\n\n"
            "## 不擅长\n- <...>\n"
        ),
        "SOUL.md": (
            f"# {member_id} — SOUL\n\n"
            "## 语气\n<...>\n\n"
            '## 风格\n- 直接说要说的内容，不写"已经XX啦"汇报体\n- <...>\n\n'
            "## 决策风格\n<...>\n\n"
            "## 不可逾越的边界（Hard Limits）\n"
            "- 以自己 member_id 身份回应，不冒充请求者\n- <...>\n"
        ),
        "USER.md": (
            f"# {member_id} — USER（在本项目中）\n\n"
            "## 项目所有者\n<human:xxx —— ...>\n\n"
            "## 同伴 Agent\n- <...>\n\n"
            "## 项目偏好\n- <...>\n"
        ),
        "MEMORY.md": (
            f"# {member_id} — MEMORY\n\n"
            "## <日期>\n- <长期记忆，持续追加>\n"
        ),
    }


def scaffold_agent(root: Path, member_id: str, *, force: bool = False) -> Path:
    """Create ``.talk/agents/<dir>/`` placeholder profile for ``member_id``.

    Requires ``.talk/`` to already exist (run ``talk init`` first).
    """
    talk_dir = Path(root) / ".talk"
    if not (talk_dir / "project.yaml").exists():
        raise FileNotFoundError(f"no .talk/project.yaml under {root}; run `talk init` first")
    agent_dir = talk_dir / "agents" / member_dir_name(member_id)
    if agent_dir.exists() and not force:
        raise FileExistsError(f"agent profile already exists at {agent_dir} (use force to overwrite)")
    agent_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in _agent_profile_files(member_id).items():
        _write_text(agent_dir / fname, content)
    return agent_dir


def load_project(root: Path) -> dict[str, Any]:
    path = Path(root) / ".talk" / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no .talk/project.yaml under {root}; run `talk init` first")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_groups(root: Path) -> dict[str, Any]:
    path = Path(root) / ".talk" / "groups.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    if not isinstance(doc, dict):
        doc = {}
    if not isinstance(doc.get("groups"), list):
        doc["groups"] = []
    return doc


def save_groups(root: Path, doc: dict[str, Any]) -> None:
    _write_yaml(Path(root) / ".talk" / "groups.yaml", doc)


# Maps a sync-payload field to the profile filename it indexes. ``MEMORY.md`` is
# surfaced as ``memory_pointer`` — a pointer to where this agent's memory lives.
_SYNC_PROFILE_FILES: dict[str, str] = {
    "identity_path": "IDENTITY.md",
    "soul_path": "SOUL.md",
    "user_path": "USER.md",
    "memory_pointer": "MEMORY.md",
}


def scan_agents(root: Path) -> list[dict[str, Any]]:
    """Build the agent profile-path index from ``.talk/agents/`` (for `talk sync`).

    Each subdirectory under ``.talk/agents/`` is one agent; its directory name is
    reversed back to a ``member_id`` (see :func:`member_id_from_dir_name`). Paths
    are relative to ``root`` with forward slashes so they are stable across OSes;
    a missing profile file yields ``None`` for that field. Returns entries sorted
    by ``member_id`` to match the server's index ordering.
    """
    agents_dir = Path(root) / ".talk" / "agents"
    if not agents_dir.exists():
        return []

    entries: list[dict[str, Any]] = []
    for child in sorted(agents_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue  # skips agents/README.md and any dotted dirs
        entry: dict[str, Any] = {"member_id": member_id_from_dir_name(child.name)}
        for field, fname in _SYNC_PROFILE_FILES.items():
            fpath = child / fname
            entry[field] = fpath.relative_to(root).as_posix() if fpath.exists() else None
        entries.append(entry)
    entries.sort(key=lambda e: e["member_id"])
    return entries


# ── server registration ──────────────────────────────────────────────


def register_project(
    server_url: str,
    api_key: str,
    project_meta: dict[str, Any],
    *,
    http: Any = None,
) -> dict[str, Any]:
    """Register a project with the TALK server (``POST /api/projects``).

    ``http`` is an optional injected client exposing ``.post(url, json=, headers=)``
    (httpx.Client or FastAPI TestClient). When omitted, a short-lived
    ``httpx.Client`` bound to ``server_url`` is created and closed.
    """
    payload = {
        "project_id": project_meta.get("project_id"),
        "display_name": project_meta["display_name"],
        "description": project_meta.get("description"),
        "project_root_path": project_meta.get("project_root_path"),
        "maintainer_member_id": project_meta.get("maintainer"),
    }

    owns_client = http is None
    if http is None:
        import httpx

        http = httpx.Client(base_url=server_url, timeout=10.0)
    try:
        resp = http.post("/api/projects", json=payload, headers={"X-API-Key": api_key})
    finally:
        if owns_client:
            http.close()

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"registration failed: HTTP {resp.status_code} {resp.text}")
    return resp.json()


def create_group(
    server_url: str,
    api_key: str,
    *,
    name: str,
    group_id: Optional[str] = None,
    description: Optional[str] = None,
    project_id: Optional[str] = None,
    member_ids: Optional[list[str]] = None,
    http: Any = None,
) -> dict[str, Any]:
    """Create a group via ``POST /api/groups`` (used by ``talk create-group``).

    ``http`` is injectable like :func:`register_project`.
    """
    payload: dict[str, Any] = {"name": name}
    if group_id:
        payload["id"] = group_id
    if description:
        payload["description"] = description
    if project_id:
        payload["project_id"] = project_id
    if member_ids:
        payload["member_ids"] = member_ids

    owns_client = http is None
    if http is None:
        import httpx

        http = httpx.Client(base_url=server_url, timeout=10.0)
    try:
        resp = http.post("/api/groups", json=payload, headers={"X-API-Key": api_key})
    finally:
        if owns_client:
            http.close()

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"create group failed: HTTP {resp.status_code} {resp.text}")
    return resp.json()


def sync_project(
    server_url: str,
    api_key: str,
    project_id: str,
    agents: list[dict[str, Any]],
    *,
    http: Any = None,
) -> list[dict[str, Any]]:
    """Sync the local agent index to the server (``POST /api/projects/{id}/sync``).

    Full-replace semantics on the server side: the returned list is the project's
    complete agent index after the sync. ``http`` is injectable like
    :func:`register_project`.
    """
    owns_client = http is None
    if http is None:
        import httpx

        http = httpx.Client(base_url=server_url, timeout=10.0)
    try:
        resp = http.post(
            f"/api/projects/{project_id}/sync",
            json={"agents": agents},
            headers={"X-API-Key": api_key},
        )
    finally:
        if owns_client:
            http.close()

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"sync failed: HTTP {resp.status_code} {resp.text}")
    return resp.json()


# ── CLI ──────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    display_name = args.name or root.name
    meta = scaffold_project(
        root,
        display_name=display_name,
        server_url=args.server,
        description=args.description,
        maintainer=args.maintainer,
        force=args.force,
    )
    talk_dir = root / ".talk"
    print(f"✓ Created {talk_dir / 'project.yaml'} (project_id: {meta['project_id']})")
    print(f"✓ Created {talk_dir / 'AGENTS.md'}")
    print(f"✓ Created {talk_dir / 'groups.yaml'}")
    print(f"✓ Created {talk_dir / 'agents' / 'README.md'}")

    if args.no_register:
        print("• Skipped server registration (--no-register)")
        return 0
    if not args.key:
        print("• No --key provided; skipped server registration. Re-run with --key to register.")
        return 0

    result = register_project(
        args.server,
        args.key,
        {**meta, "project_root_path": str(root)},
    )
    print(f"✓ Registered to TALK server (project_id: {result['project_id']})")
    return 0


def cmd_add_agent(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    agent_dir = scaffold_agent(root, args.member_id, force=args.force)
    print(f"✓ Created {agent_dir} (IDENTITY/SOUL/USER/MEMORY placeholders)")
    print("• Fill in IDENTITY.md and SOUL.md, then commit.")
    return 0


def cmd_create_group(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    project = load_project(root)
    server_url = args.server or project.get("talk_server") or DEFAULT_SERVER
    project_id = args.project or project.get("project_id")
    if not args.key:
        print("✗ --key is required to create a group on the server", file=sys.stderr)
        return 1

    result = create_group(
        server_url,
        args.key,
        name=args.name,
        group_id=args.id,
        description=args.description,
        project_id=project_id,
        member_ids=args.members or None,
    )

    doc = load_groups(root)
    doc["groups"].append(
        {
            "id": result["id"],
            "name": result["name"],
            "members": [{"member_id": m["member_id"]} for m in result.get("members", [])],
        }
    )
    save_groups(root, doc)
    print(f"✓ Created group {result['id']} (project_id: {result.get('project_id')})")
    print(f"✓ Updated {root / '.talk' / 'groups.yaml'}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    project = load_project(root)
    server_url = args.server or project.get("talk_server") or DEFAULT_SERVER
    project_id = args.project or project.get("project_id")
    if not project_id:
        print("✗ no project_id in .talk/project.yaml; pass --project", file=sys.stderr)
        return 1
    if not args.key:
        print("✗ --key is required to sync with the server", file=sys.stderr)
        return 1

    agents = scan_agents(root)
    result = sync_project(server_url, args.key, project_id, agents)
    print(f"✓ Synced {len(result)} agent profile(s) (project_id: {project_id})")
    for entry in result:
        print(f"  • {entry['member_id']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="talk", description="TALK project integration CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold .talk/ and register the project")
    p_init.add_argument("--root", default=".", help="project root directory (default: cwd)")
    p_init.add_argument("--name", default=None, help="project display name (default: root dir name)")
    p_init.add_argument("--description", default=None, help="project description")
    p_init.add_argument("--server", default=DEFAULT_SERVER, help=f"TALK server URL (default: {DEFAULT_SERVER})")
    p_init.add_argument("--maintainer", default=None, help="maintainer member_id, e.g. human:bobo")
    p_init.add_argument("--key", default=None, help="X-API-Key used to register with the server")
    p_init.add_argument("--no-register", action="store_true", help="scaffold only; skip server registration")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing .talk/ directory")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add-agent", help="Scaffold an agent profile under .talk/agents/")
    p_add.add_argument("member_id", help="member id, e.g. agent:codex")
    p_add.add_argument("--root", default=".", help="project root directory (default: cwd)")
    p_add.add_argument("--force", action="store_true", help="overwrite an existing profile")
    p_add.set_defaults(func=cmd_add_agent)

    p_grp = sub.add_parser("create-group", help="Create a group on the server and record it in groups.yaml")
    p_grp.add_argument("--name", required=True, help="group display name")
    p_grp.add_argument("--id", default=None, help="explicit group id (default: server-generated)")
    p_grp.add_argument("--description", default=None, help="group description")
    p_grp.add_argument("--project", default=None, help="project_id to associate (default: local project.yaml)")
    p_grp.add_argument("--members", nargs="*", default=None, help="member_ids to add to the group")
    p_grp.add_argument("--server", default=None, help="TALK server URL (default: local project.yaml)")
    p_grp.add_argument("--root", default=".", help="project root directory (default: cwd)")
    p_grp.add_argument("--key", default=None, help="X-API-Key used to authenticate with the server")
    p_grp.set_defaults(func=cmd_create_group)

    p_sync = sub.add_parser("sync", help="Sync .talk/agents/ profile index to the server")
    p_sync.add_argument("--project", default=None, help="project_id to sync (default: local project.yaml)")
    p_sync.add_argument("--server", default=None, help="TALK server URL (default: local project.yaml)")
    p_sync.add_argument("--root", default=".", help="project root directory (default: cwd)")
    p_sync.add_argument("--key", default=None, help="X-API-Key used to authenticate with the server")
    p_sync.set_defaults(func=cmd_sync)

    return parser


def _force_utf8_streams() -> None:
    """Make stdout/stderr UTF-8 so Chinese paths and ✓/✗ glyphs print on Windows (GBK console)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def main(argv: Optional[list[str]] = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileExistsError, FileNotFoundError, RuntimeError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
