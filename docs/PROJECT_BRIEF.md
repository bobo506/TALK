# TALK — 项目简报

> 本文件是所有参与开发的 agent 的**必读公共上下文**。

## 项目定位

TALK 是部署在**家庭局域网**的轻量级 AI 智能体聊天中转平台。核心能力：
- 多个 AI Agent 之间互相发送消息和文件包
- 人类用户通过 Web UI 用 `@` 向任意 Agent 下达任务
- 所有通信统一中转，消息持久化，便于回溯

## 系统架构

```
 ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
 │  Browser UI │        │  Agent AI1  │        │  Agent AI2  │
 │  (human)    │        │  (poller)   │        │ (websocket) │
 └──────┬──────┘        └──────┬──────┘        └──────┬──────┘
        │ WebSocket           │ HTTP polling         │ WebSocket
        └─────────────────────┼──────────────────────┘
                              ▼
                  ┌────────────────────────┐
                  │   FastAPI Server       │
                  │   REST API + WS Hub    │
                  │   X-API-Key 鉴权       │
                  └────────────┬───────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  SQLite  +  Local FS    │
                  │  talk.db   storage/     │
                  └─────────────────────────┘
```

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 + FastAPI + uvicorn |
| ORM | SQLModel (Pydantic + SQLAlchemy) |
| 数据库 | SQLite（WAL 模式），文件 `talk.db` |
| 文件存储 | 本地磁盘 `storage/files/` |
| 前端 | 单页 HTML + Vanilla JS + Tailwind CSS (CDN) |
| 测试 | Python `unittest`（M3-4 已落首轮后端自动化测试） |
| 鉴权 | `X-API-Key` header（WebSocket 用 `?token=`） |
| 配置 | `config.toml`（tomllib 读取） |

## 运维基线

- 健康检查：提供 `GET /healthz`，返回 `status / db / storage / uptime_sec / online_members`；任一子检查异常时返回 `503`
- 日志：使用标准库 `logging` 输出 JSON 结构化日志，默认写入 `logs/talk.log` 并按天切割；覆盖 HTTP 请求、WebSocket 连接/广播事件与异常堆栈
- 备份：提供 `scripts/backup_db.py`，基于 `sqlite3.Connection.backup()` 做 WAL 模式下的在线热备；默认写入 `backups/backup_YYYY-MM-DD.db` 并保留最近 7 份
- 配置：`config.toml` 新增 `[logging]` 与 `[backup]` 段，可分别调整日志路径、日志级别、备份目录和保留份数

## 数据模型（核心表）

```sql
CREATE TABLE members (
  id           TEXT PRIMARY KEY,       -- 'human:bobo' / 'agent:AI1'
  kind         TEXT NOT NULL,          -- 'human' | 'agent'
  display_name TEXT NOT NULL,
  api_key      TEXT UNIQUE NOT NULL,
  poll_hint    INTEGER,
  created_at   DATETIME NOT NULL
);

CREATE TABLE messages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  from_id      TEXT NOT NULL REFERENCES members(id),
  to_ids       TEXT,                   -- JSON 数组；NULL = 广播
  type         TEXT NOT NULL,          -- 'text' | 'file'
  content      TEXT,                   -- type=text: 消息正文；type=file: 兼容字段（通常与 filename 相同）
  file_id      TEXT REFERENCES files(id), -- type=file 时必填
  caption      TEXT,                   -- type=file: 可选附言
  filename     TEXT,                   -- type=file: 冻结的文件名快照
  size_bytes   INTEGER,                -- type=file: 冻结的文件大小快照
  mime         TEXT,                   -- type=file: 冻结的 MIME 快照
  revoked_at   DATETIME,               -- 撤回时间；NULL = 未撤回
  revoked_by   TEXT REFERENCES members(id), -- 撤回者；当前仅允许发送者本人
  created_at   DATETIME NOT NULL
);

CREATE TABLE files (
  id           TEXT PRIMARY KEY,       -- uuid4
  filename     TEXT NOT NULL,
  mime         TEXT,
  size_bytes   INTEGER NOT NULL,
  sha256       TEXT NOT NULL,
  uploader_id  TEXT NOT NULL REFERENCES members(id),
  path         TEXT NOT NULL,
  created_at   DATETIME NOT NULL
);

CREATE TABLE agent_instances (
  id              TEXT PRIMARY KEY,       -- bridge 进程实例 id
  member_id       TEXT NOT NULL REFERENCES members(id), -- 所属 agent:* 成员
  runtime         TEXT NOT NULL,          -- codex | claude | pi | ...
  status          TEXT NOT NULL,          -- starting | online | idle | busy | stopping | offline | error
  host            TEXT,
  pid             INTEGER,
  current_task_id TEXT,
  last_error      TEXT,
  created_at      DATETIME NOT NULL,
  updated_at      DATETIME NOT NULL,
  last_seen_at    DATETIME NOT NULL
);
```

## 鉴权机制

- 所有 `/api/*` 请求必须携带 `X-API-Key: <token>` header
- WebSocket `/ws` 用 query `?token=<api_key>`
- 服务端按 key 反查 `members` 表确定身份
- `POST /api/members`（注册）例外，不要求鉴权
- `GET /api/members/me` 用于前端按 API Key 自动识别当前成员

## 当前前端交互约定

- 文本消息与文件附言都使用“消息开头连续 `@member_id` 块”决定接收者
- 实际路由以服务端解析结果为准；前端只负责 `@` 自动补全与输入提示
- 无开头 mention 时按广播处理
- 中途出现的 `@` 仅作为正文提及展示，不承担路由语义
- 成员自动补全与 mention 校验均来自 `GET /api/members` 返回的数据，而不是前端写死角色前缀
- 文件消息卡片始终依赖消息快照渲染；若文件实体已过期删除，历史卡片仍保留，但下载会失败并提示“已过期”
- 发送者可在 `revoke_window_sec`（默认 120 秒）内撤回自己的消息；撤回后消息流改为灰色占位“XX 撤回了一条消息”，文件实体本身保留

## 项目目录结构

```
TALK/
├── CLAUDE.md              # 项目入口（自动加载）
├── config.toml            # 服务配置
├── requirements.txt       # Python 依赖
├── run.sh                 # 一键启动
├── server/
│   ├── main.py            # FastAPI 入口
│   ├── logging_config.py  # 结构化日志配置
│   ├── models.py          # SQLModel 数据模型 + API schemas
│   ├── db.py              # SQLite 初始化 + config 加载
│   ├── auth.py            # API Key 鉴权依赖
│   ├── ws_hub.py          # WebSocket 连接管理
│   └── routes/
│       ├── members.py     # 成员注册/列表
│       ├── instances.py   # Agent 运行实例状态
│       ├── messages.py    # 消息收发
│       └── files.py       # 文件上传下载（M2）
├── web/
│   ├── index.html         # 单页 UI
│   ├── app.js             # 前端逻辑
│   └── style.css          # 自定义样式
├── examples/
│   └── agent_poller.py    # 示例 Agent 轮询脚本
├── bridges/
│   └── codex_bridge.py    # Codex CLI bridge（local-lab MVP）
├── scripts/
│   └── backup_db.py       # SQLite 在线热备脚本
├── tests/
│   ├── test_support.py    # 后端测试基类与隔离环境
│   └── test_*.py          # M3-4 首轮自动化测试
├── logs/                  # 结构化日志输出目录
├── backups/               # SQLite 备份输出目录
├── storage/files/         # 上传文件实体
├── docs/
│   ├── PROJECT_BRIEF.md   # 本文件
│   ├── PRODUCT.md         # PM 完整产品文档
│   ├── MODULE_*.md        # 模块 spec
│   └── PROGRESS.md        # 进度追踪
└── talk.db                # SQLite 数据库（运行时生成）
```

## 模块索引

| 模块文档 | 负责范围 | 涉及文件 | 状态 |
|----------|----------|----------|------|
| [MODULE_members_auth.md](MODULE_members_auth.md) | 成员注册 + API Key 鉴权 | `server/auth.py`, `server/routes/members.py` | M1 已实现，已补 `GET /api/members/me`、Agent 自注册与首轮自动化测试 |
| [MODULE_messages.md](MODULE_messages.md) | 消息发送与拉取 | `server/routes/messages.py` | M2 已支持服务端 mention 路由解析、文件附言、历史分页、搜索、消息撤回与自动化测试 |
| [MODULE_websocket.md](MODULE_websocket.md) | WebSocket 连接管理与推送 | `server/ws_hub.py`, `server/main.py`(ws端点) | M1 已实现，有改进点 |
| [MODULE_files.md](MODULE_files.md) | 文件上传下载 | `server/routes/files.py` | M2 已实现，已支持按保留期清理与首轮自动化测试 |
| [MODULE_webui.md](MODULE_webui.md) | 浏览器端 Web UI | `web/index.html`, `web/app.js`, `web/style.css` | M2 已实现，已补渲染优化、过期文件反馈、历史翻页、搜索与撤回态渲染 |
| [MODULE_agent_example.md](MODULE_agent_example.md) | 示例 Agent 轮询脚本 | `examples/agent_poller.py` | M2 已实现，支持文件收发、附言回执与 Agent 自注册 |
| [MODULE_bridges.md](MODULE_bridges.md) | 外部 Agent bridge 接入 | `bridges/` | Codex bridge MVP 已落地，local-lab 方向持续设计中 |
| [MODULE_instances.md](MODULE_instances.md) | Agent 运行实例状态与调度基础 | `server/routes/instances.py`, `server/models.py`, `TALK/client/` | 实例状态 API 第一版已落地，调度 API 待实现 |

补充说明：
- 文件消息现已内嵌 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段
- 文件实体默认按 `config.toml` 的 `file_retention_days` 保留；过期后会在服务启动时清理磁盘文件和 `files` 记录，但历史消息快照仍保留

## 公共依赖说明

所有后端模块共享以下基础设施（不属于任何单一模块）：
- `server/models.py` — ORM 模型 + API schemas（所有后端模块都会引用）
- `server/db.py` — 数据库引擎 + 配置加载 + `get_session` 依赖
- `config.toml` — 服务配置

修改这些公共文件时需评估对所有模块的影响。

## 2026-05-13 Local Lab Addendum

- 新增 `docs/LOCAL_LAB_DESIGN.md`，用于收敛本地多 Agent 实验室阶段的设计边界。
- local-lab 阶段已确认方向：Codex / Claude Code 走本地 CLI bridge；DeepSeek / Kimi 走本地 `pi` 框架 bridge；后续加入 Group、Hall、SSE、实例/调度 API 与文档编辑协调协议。
- `bridges/codex_bridge.py` 是第一版 Codex 接入 MVP：通过 TALK SDK 自注册、监听发给 `agent:codex` 的文本任务、调用 `codex exec`，再用 `reply_to` 回复原发送者。
- `agent_instances` 表与 `/api/instances` 第一版已落地；Codex bridge 已接入 `idle / busy / error / offline` 状态上报。
## 2026-04-23 Data Model Addendum

- `messages.reply_to INTEGER NULL REFERENCES messages(id)` was added for first-level reply/reference support.
- Reply rendering is intentionally flat: only the direct parent summary is returned, with no recursive tree expansion.
- Message REST and WebSocket payloads may now include:
  - `reply_to.id`
  - `reply_to.from_id`
  - `reply_to.preview`
  - `reply_to.type`
  - `reply_to.revoked`
- `reply_to.preview` is precomputed server-side to avoid frontend N+1 fetches.
- Public `GET /api/config` now exposes frontend-safe runtime constants such as `revoke_window_sec`, `max_upload_bytes`, `ws_ping_interval`, `ws_ping_timeout`, and `file_retention_days`.

## 2026-04-23 Visibility Addendum

- `GET /api/messages` now enforces message visibility on the server side instead of trusting the caller's `to` filter.
- Clients can only retrieve messages that match the same delivery rules used by WebSocket broadcast:
  - sender can always see their own messages
  - everyone can see broadcast messages
  - recipients can see directed or group messages that include them
- `to=<member_id>` is now only a secondary filter on top of that visible set.
- `to=<other_member>` produces a safe pair view: broadcast, direct messages between the two members, and shared group messages where both are recipients.
- Search (`q`) is also restricted to the caller's visible set, so keyword queries cannot leak hidden messages.

## 2026-04-24 Onboarding Docs Addendum

- `docs/QUICKSTART.md` 现已降为入口索引页，分别指向家庭用户与 Agent 开发者两份独立快速启动文档
- 新增 `docs/QUICKSTART_USER.md`：面向家庭新手，只走 Docker Desktop + 浏览器路径
- 新增 `docs/QUICKSTART_AGENT.md`：面向 Agent 开发者，只走 Python bare metal + SDK 路径
- `docs/SDK.md` 的异步示例现已补齐 `asyncio.run(main())` 包装，可直接复制到 `.py` 文件运行
- 首次管理员引导页的 `api_key` 输入已支持浏览器端安全随机生成、显隐切换与一键复制，新手无需手动编造登录密钥
