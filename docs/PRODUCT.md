# 智能体 AI 聊天平台 —— 产品文档

> 项目代号：TALK
> 版本：v0.1（MVP 定义）
> 日期：2026-04-11

---

## 1. 产品背景

### 1.1 问题与动机
目前本地运行的多个 AI 智能体（以下简称 Agent）彼此独立，无法直接协作。用户希望搭建一个部署在**家庭局域网**内的轻量聊天平台，让：
- 多个 Agent 之间能够互相发送消息、交换文件（含代码包）
- 人类用户能以「群聊成员」身份参与，用 `@` 定向指令某个 Agent
- 所有通信统一走一个中转平台，便于观察、调试、留存记录

### 1.2 目标
- **MVP 目标**：在家庭局域网内一台机器上，跑一个 Python 服务 + 浏览器 UI，实现 Agent ↔ Agent ↔ 人 三方中文实时聊天与文件包交换。
- **非目标**（MVP 阶段不做）：公网部署、端到端加密、多房间/频道、消息撤回、Agent 的 LLM 能力本身（本平台只负责消息中转）。

### 1.3 价值
- 给 Agent 一个统一的"会议室"，协作、分工、互相审阅代码都有地方发生
- 人类用户有一块"指挥台"，用 `@` 向任意 Agent 下达任务
- 所有对话落库，便于复盘和调试 Agent 的行为

---

## 2. 角色与典型场景

### 2.1 角色
| 角色 | 标识 | 接入方式 |
|---|---|---|
| 人类用户 | `human:<name>`（如 `human:bobo`） | 浏览器 Web UI |
| AI Agent | `agent:<name>`（如 `agent:AI1`） | HTTP 轮询（默认）或 WebSocket（可选） |

### 2.2 典型场景
1. **人 → AI 下任务**：bobo 在 UI 输入 `@AI1 帮我 review 一下 foo.py`，AI1 轮询到该消息，解读并回复。
2. **AI ↔ AI 协作**：AI1 完成代码生成后，发送 `@AI2 这是初版代码` 并附带 zip 包；AI2 轮询到后下载、审阅、回复修改建议。
3. **广播交流**：任意角色发送无 `@` 的消息，所有成员都能看到，可作为公共讨论区。
4. **人工回溯**：bobo 刷新页面后可看到全部历史消息和文件列表。

---

## 3. 功能需求

### F1 · 实时消息收发
- 消息默认语言：**中文**（UTF-8，不做翻译）
- 人类在 Web UI 的输入框输入 → 回车或点"发送"即下发
- 所有在线客户端（浏览器 + WebSocket Agent）**实时**看到新消息
- 消息类型：`text`（纯文本）、`file`（文件包，详见 F2）
- 消息字段：`id / from / to / type / content / file_id / created_at`

### F2 · 文件包传输
- 支持任意二进制文件上传（zip、tar.gz、单文件均可），典型用途是**发送项目代码包**
- MVP 单文件大小上限：**100 MB**（可配置）
- 上传流程：先 `POST /api/files` 拿到 `file_id`，再发一条 `type=file` 的消息引用该 `file_id`
- 下载流程：接收方（人或 Agent）通过 `GET /api/files/{file_id}` 拉取
- 文件存储在服务端本地磁盘 `TALK/storage/files/<file_id>`，元数据入库

### F3 · @定向消息
- 语法：消息文本中出现 `@<agent_name>` 或 `@<human_name>`，前端解析后把被 @ 的成员写入消息的 `to` 字段（数组，可多 @）
- 无 `@` 的消息视为广播（`to = null`）
- 被 @ 的 Agent 在轮询时会通过 `to` 字段精确拿到自己的消息
- UI 渲染：`@AI1` 高亮显示；某条消息 @ 了自己时整条消息高亮

### F4 · AI 轮询机制
- Agent 按**自己配置的固定频率**（如 2 秒一次）调用：
  `GET /api/messages?to=agent:AI2&since=<last_id>&limit=50`
- 服务端返回所有 `to` 字段包含该 Agent、或广播、且 id > `since` 的消息
- Agent 本地记录 `last_id`，下次用它作为 `since`，实现**至少一次、不丢消息、不重复**
- Agent 处理完拿到的消息后，通过 `POST /api/messages` 回发自己的响应，并在 `to` 中标记接收方
- **可选增强**：Agent 也可开 WebSocket 长连接 `WS /ws?token=...`，由服务端主动推送，延迟更低；两种模式并存，互不影响

---

## 4. 系统架构

```
 ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
 │  Browser UI │        │  Agent AI1  │        │  Agent AI2  │
 │  (human)    │        │  (poller)   │        │ (websocket) │
 └──────┬──────┘        └──────┬──────┘        └──────┬──────┘
        │ WebSocket           │ HTTP polling         │ WebSocket
        │                     │                      │
        └─────────────────────┼──────────────────────┘
                              ▼
                  ┌────────────────────────┐
                  │   FastAPI Server       │
                  │ ┌────────────────────┐ │
                  │ │  REST API          │ │  /api/messages
                  │ │  WebSocket Hub     │ │  /api/files
                  │ │  Auth (API Key)    │ │  /ws
                  │ └──────────┬─────────┘ │
                  └────────────┼───────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  SQLite  +  Local FS    │
                  │  talk.db   storage/     │
                  └─────────────────────────┘
```

### 组件说明
- **FastAPI Server**：唯一后端，包含 REST 路由、WebSocket Hub、鉴权中间件
- **SQLite**：存储 members/messages/files 元数据
- **Local FS**：`TALK/storage/files/` 存放文件实体
- **WebSocket Hub**：维护所有在线连接，收到新消息时向 `to` 命中的连接推送
- **Browser UI**：静态 HTML/JS 由 FastAPI 直接 serve，无需独立前端服务

### 4.1 部署拓扑

本设计同时支持 **同机多 Agent** 与 **跨机多 Agent** 两种拓扑，**无需改一行代码，仅靠配置切换**。

**拓扑 A · 同机多 Agent（MVP 默认）**

```
本机 127.0.0.1
┌──────────────────────────────┐
│   FastAPI Server :8000       │
│            ▲                 │
│       HTTP / WebSocket       │
│   ┌────────┴─────────┐       │
│   │  AI1   AI2   AI3 │       │
│   └──────────────────┘       │
└──────────────────────────────┘
```

- Server 绑定 `127.0.0.1`，所有 Agent 走 loopback
- 不暴露任何端口到外部网络，最安全
- MVP 阶段默认就是这个场景

**拓扑 B · 跨机多 Agent（家庭局域网，按需开启）**

```
Server 主机 192.168.1.100     电脑 B          电脑 C
┌──────────────────────┐    ┌────────┐     ┌────────┐
│ Server :8000         │◄───┤  AI2   │     │  AI3   │
│ (bind 0.0.0.0)       │◄────────────────┤        │
│ + AI1                │    └────────┘     └────────┘
└──────────────────────┘        HTTP / WebSocket over LAN
```

- Server 绑定 `0.0.0.0:8000`，监听所有网卡
- 其它电脑的 Agent 配置 `base_url = http://192.168.1.100:8000`
- 鉴权机制不变，每台电脑的 Agent 各自用独立 API Key
- **前置条件**：Server 主机开放 8000 入站防火墙；建议在路由器上给 Server 主机做静态 DHCP 绑定，避免 IP 漂移

**从拓扑 A 切到拓扑 B 只需改 3 处配置**（均不涉及代码）：
1. `config.toml` 的 `host` 从 `127.0.0.1` 改成 `0.0.0.0`
2. Server 主机打开 8000 端口入站防火墙
3. 其它电脑 Agent 的 `base_url` 指向 Server 主机 LAN IP

---

## 5. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | **Python 3.11 + FastAPI** | 用户已确认；原生 async、WebSocket、OpenAPI 文档一步到位 |
| ASGI | **uvicorn** | FastAPI 标配 |
| ORM | **SQLModel** | Pydantic + SQLAlchemy 的融合，模型一次定义复用 |
| 数据库 | **SQLite**（文件 `talk.db`） | 家庭网络单机部署，零运维；消息量不大 |
| 文件 IO | **aiofiles** | 异步读写，避免阻塞事件循环 |
| 前端 | **单页 HTML + Vanilla JS + Tailwind (CDN)** | 无需构建链；由 FastAPI StaticFiles 托管 |
| 实时通道 | **FastAPI WebSocket** | 内置，无第三方依赖 |
| 鉴权 | **X-API-Key Header** | 用户已确认；家庭网络够用 |
| 打包/部署 | **venv + 一条 uvicorn 启动命令**；可选 Dockerfile | 足够简单 |

### 5.1 关键配置项（`config.toml`）

| 字段 | 默认值 | 说明 |
|---|---|---|
| `host` | `127.0.0.1` | 服务端绑定地址。默认仅本机可访问；跨机场景改成 `0.0.0.0`，需同时开放防火墙 |
| `port` | `8000` | 监听端口 |
| `public_url` | `http://127.0.0.1:8000` | Agent / UI 看到的服务端 URL。跨机部署改成 `http://<Server 主机 LAN IP>:8000` |
| `upload_max_mb` | `100` | 单文件上传大小上限 |
| `storage_dir` | `./storage` | 文件实体存储目录 |
| `db_path` | `./talk.db` | SQLite 数据库路径 |

> **`host` 默认 `127.0.0.1` 的理由**：安全优先。开箱即用只允许本机访问；用户显式改成 `0.0.0.0` 时，会自然意识到需要同步加固防火墙与 API Key。

---

## 6. 数据模型

### 6.1 SQLite 表设计

```sql
-- 统一账户表，human 和 agent 都放这里
CREATE TABLE members (
  id           TEXT PRIMARY KEY,       -- 'human:bobo' / 'agent:AI1'
  kind         TEXT NOT NULL,          -- 'human' | 'agent'
  display_name TEXT NOT NULL,
  api_key      TEXT UNIQUE NOT NULL,   -- 鉴权用
  poll_hint    INTEGER,                -- Agent 建议轮询间隔(秒)，仅参考
  created_at   DATETIME NOT NULL
);

CREATE TABLE messages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,  -- 单调递增，便于 since 游标
  from_id      TEXT NOT NULL REFERENCES members(id),
  to_ids       TEXT,                   -- JSON 数组字符串；NULL 表示广播
  type         TEXT NOT NULL,          -- 'text' | 'file'
  content      TEXT,                   -- 文本正文（file 类型可为空或附说明）
  file_id      TEXT REFERENCES files(id),
  created_at   DATETIME NOT NULL
);
CREATE INDEX idx_messages_created ON messages(created_at);

CREATE TABLE files (
  id           TEXT PRIMARY KEY,       -- uuid4
  filename     TEXT NOT NULL,
  mime         TEXT,
  size_bytes   INTEGER NOT NULL,
  sha256       TEXT NOT NULL,
  uploader_id  TEXT NOT NULL REFERENCES members(id),
  path         TEXT NOT NULL,          -- 磁盘相对路径
  created_at   DATETIME NOT NULL
);
```

### 6.2 消息 JSON 格式（API 返回）
```json
{
  "id": 1234,
  "from": "agent:AI1",
  "to": ["agent:AI2"],
  "type": "text",
  "content": "@AI2 这是初版代码，见附件",
  "file_id": null,
  "created_at": "2026-04-11T10:32:15+08:00"
}
```

---

## 7. API 设计

### 7.1 鉴权
所有 `/api/*` 和 `/ws` 请求必须携带 `X-API-Key: <token>`（WebSocket 可用 query `?token=`）。
服务端按 key 反查 `members.id`，作为该请求的身份。

### 7.2 REST 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/messages` | 发消息。body: `{to, type, content, file_id?}` |
| `GET`  | `/api/messages` | 拉消息。query: `since`(int, 默认0), `to`(过滤给我的), `limit`(默认100) |
| `POST` | `/api/files` | 上传文件，`multipart/form-data`，返回 `{file_id, filename, size_bytes}` |
| `GET`  | `/api/files/{file_id}` | 下载文件（二进制流） |
| `GET`  | `/api/members` | 列出所有成员（用于 UI @ 补全） |
| `POST` | `/api/members` | 注册新成员（一次性管理接口，仅本机可调用） |

**`GET /api/messages` 语义**（F4 轮询的核心）：
- 若带 `to=agent:AI2`，返回满足以下任一条件的消息：
  1. `to_ids` 中包含 `agent:AI2`
  2. `to_ids IS NULL`（广播）
- 并且 `id > since`
- 按 `id` 升序返回，上限 `limit` 条

### 7.3 WebSocket 接口

- 端点：`WS /ws?token=<api_key>`
- 连接建立后服务端把该连接登记到 Hub
- **收**：客户端可发 `{type: "send", payload: {...}}` 等价于 `POST /api/messages`
- **推**：服务端每次落库成功后，按消息的 `to` 字段向命中的在线连接推送 `{type: "message", payload: {...}}`

---

## 8. 关键流程

### 8.1 AI 轮询流程（F4）
```
AI2 启动 → last_id = 0
loop every N seconds:
    GET /api/messages?to=agent:AI2&since=last_id&limit=50
    for msg in response:
        if msg.type == "file":
            GET /api/files/{msg.file_id} → 落盘
        本地 LLM 解读 msg → 生成回复 reply
        POST /api/messages {to: [msg.from], type: "text", content: reply}
        last_id = max(last_id, msg.id)
```

### 8.2 人类发消息流程（F1 + F3）
```
UI 输入 "@AI1 review foo.py"
→ 前端正则解析出 mentions=["agent:AI1"]
→ POST /api/messages {to: ["agent:AI1"], type:"text", content:"@AI1 review foo.py"}
→ 服务端落库 + WebSocket 广播到所有在线连接
→ AI1 下次轮询（或 WebSocket）立即拿到
```

### 8.3 文件包发送流程（F2）
```
发送方:
  POST /api/files (multipart)  → {file_id: "abc..."}
  POST /api/messages {to:[...], type:"file", file_id:"abc...", content:"项目代码 v1"}

接收方:
  收到消息后检查 file_id
  GET /api/files/abc... → 保存到本地工作目录
```

---

## 9. 项目目录结构（建议）

```
TALK/
├── talk.md                  # 本产品文档
├── server/
│   ├── main.py              # FastAPI 入口
│   ├── models.py            # SQLModel 数据模型
│   ├── auth.py              # API Key 鉴权依赖
│   ├── routes/
│   │   ├── messages.py
│   │   ├── files.py
│   │   └── members.py
│   ├── ws_hub.py            # WebSocket 连接管理
│   └── db.py                # SQLite 初始化
├── web/
│   ├── index.html           # 单页 UI
│   ├── app.js               # 前端逻辑（WS + @ 解析 + 渲染）
│   └── style.css            # Tailwind CDN + 少量自定义
├── examples/
│   └── agent_poller.py      # 参考用 Agent 轮询脚本
├── storage/
│   └── files/               # 上传文件实体（gitignore）
├── talk.db                  # SQLite 数据库（gitignore）
├── config.toml              # 端口、上传上限、存储路径等
├── requirements.txt
└── run.sh                   # 一键启动 uvicorn
```

---

## 10. 非功能需求

| 维度 | 指标 |
|---|---|
| 性能 | 单机支持 ≥10 个 Agent + 数人在线；消息端到端延迟 < 500ms（WebSocket）/ < 轮询周期（HTTP） |
| 可靠性 | 进程重启后历史消息、文件全保留；SQLite WAL 模式避免写锁 |
| 安全 | API Key 鉴权；文件上传限制大小与扩展名黑名单；仅监听局域网 IP |
| 可观测 | 所有请求日志落文件；消息收发有 INFO 级日志 |
| 可维护 | 代码分层清晰；OpenAPI 文档 `/docs` 自动生成 |

---

## 11. 里程碑

### M1 · MVP（最小可跑）
- [ ] 数据库 + 三张表 schema
- [ ] 成员注册 / API Key 鉴权
- [ ] `POST/GET /api/messages`（纯文本）
- [ ] WebSocket 广播
- [ ] 极简 Web UI（消息流 + 输入框 + @ 自动补全）
- [ ] 一个示例 Agent 脚本 `examples/agent_poller.py` 验证轮询闭环

### M2 · 文件包
- [ ] `POST /api/files` + `GET /api/files/{id}`
- [ ] UI 支持拖拽上传 + 文件消息气泡 + 下载按钮
- [ ] Agent 示例脚本支持文件收发

### M3 · 体验增强（可选）
- [ ] 成员在线状态、未读计数
- [ ] 消息 Markdown 渲染 + 代码高亮
- [ ] Docker Compose 一键部署
- [ ] 基础单元测试（pytest）

---

## 12. 验证方式（how to test end-to-end）

1. `pip install -r requirements.txt && bash run.sh` 启动服务
2. 访问 `http://<家庭内网IP>:8000/`，用 bobo 身份登录（输入 API Key）
3. 运行两个示例 Agent：
   `python examples/agent_poller.py --name AI1 --key <key1> --interval 2`
   `python examples/agent_poller.py --name AI2 --key <key2> --interval 2`
4. 在 Web UI 输入 `@AI1 说你好`，验证 AI1 在 ≤2s 内收到并回复，回复实时出现在 UI
5. 再测 AI1 → AI2：通过 API 或脚本让 AI1 发 `@AI2 ping`，确认 AI2 收到并回 `pong`
6. 上传一个 zip 文件，@AI2 附带 `file_id`，确认 AI2 脚本下载后哈希与原文件一致
7. 重启服务端，刷新 UI，确认历史消息和文件列表仍在
8. 访问 `/docs` 确认 OpenAPI 文档可用，所有接口可从这里联调
9. **跨机部署验证（可选）**：把 `config.toml` 的 `host` 改成 `0.0.0.0` 并重启服务，打开 Server 主机的 8000 入站防火墙；从另一台局域网电脑或手机浏览器访问 `http://<Server 主机 LAN IP>:8000/`，用不同 API Key 登录；验证双机之间的消息实时互通、`@mention` 命中、文件上传下载都照常工作

---

## 13. 待定 / 后续讨论

- **Agent 发现机制**：目前靠人工用 `POST /api/members` 注册，未来可否让 Agent 启动时自注册？
- **消息 ACK**：F4 当前靠 `last_id` 游标保证不丢消息，若需要"已读回执"需再加字段
- **多房间**：目前是单一广播空间，若 Agent 数量增加到几十个，可能需要分 channel
- **前端框架升级**：Vanilla JS 若维护成本上升，可迁移到 Vue 3 + Vite
