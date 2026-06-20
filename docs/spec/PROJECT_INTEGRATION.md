# TALK 项目接入与 Agent 协作完整体系 — 设计草案

> 文档状态:**Design Draft / Not yet implemented**
> 起草日期:2026-06-06
> 文档目的:沉淀 TALK 从"独立产品"向"基础设施层"的定位转变,以及配套的**项目接入机制 + Agent 元数据双层架构**。本文档不涉及任何代码改动,仅作为后续实施方向的合同。
>
> 决策来源:三天黑盒 debug + pi-vs-claude-code / ClawSwarm / OpenClaw Control Center 三份对比评估报告 + 与项目管理者多轮架构讨论。

---

## 1. 定位重校准:TALK 是基础设施,不是终点项目

### 1.1 旧定位(隐含)

历史上 TALK 被当作一个**独立、自含的多 Agent 通信平台**:你部署 TALK,在里面建群,接入 Agent,完成协作。`AGENTS.md` / `CLAUDE.md` / 所有 profile 都在 TALK 项目根下,看似 TALK 自己就是工作的终点。

### 1.2 新定位(明确)

TALK 的最终形态是**给其他项目使用的多 Agent 协作基础设施**。其他项目通过接入 TALK 获得 Agent 间的通信、讨论、文件交换、任务调度能力,但 Agent 的**身份、风格、记忆、业务角色**都归项目自己持有,不归 TALK 持有。

### 1.3 类比体系

| 基础设施 | 上层应用 | 类比角色 |
|----------|----------|----------|
| Slack | 公司 workspace | TALK : 项目 |
| Git server | 代码 repo | TALK : 项目 |
| npm registry | 发布的 package | TALK : 项目 |
| **TALK** | **项目的 Agent 协作** | — |

Slack 的类比最贴切:Slack 自己不知道你公司怎么管,只提供 channel / message / file / app integration 等机制;每家公司在自己的 workspace 内建结构、邀人、定 culture。**TALK 在新定位里就是 Agent 版的 Slack**。

### 1.4 当前与目标态的关系

当前 TALK 自己作为一个项目在 dogfood,所有 profile 暂时建在 TALK 根目录下;**这是过渡状态,不是终态**。目标态下:

- TALK 项目根下保留 TALK **自身作为一个项目** 的 `.talk/` 配置(自用 + 作为外部项目的参考模板)
- 其他项目通过 `talk init` 在各自根目录下建立独立的 `.talk/`
- 同一个 Agent(如 `agent:pi-kimi`)在不同项目里可以有不同的画像,**各项目互不影响**

---

## 2. 整体架构:三层叠加

```text
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1:项目接入层 (Project Integration)                       │
│  • 每个使用 TALK 的项目在根目录持有 .talk/                       │
│  • 包含 project.yaml(元数据)+ AGENTS.md(项目规则)             │
│  • talk init / talk add-agent / talk create-group 由 CLI 维护    │
│  • 项目侧持有,git 版本控制                                       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2:Agent 元数据 双层架构                                  │
│  • 协作层(我们现有):决策分级 + 业务角色                       │
│    - 跟项目 / group 绑定,定义"做什么、能自主到什么程度"         │
│    - 存储:groups.yaml + groups.metadata.roles                  │
│  • 身份层(借鉴 ClawSwarm):IDENTITY/SOUL/USER/MEMORY            │
│    - 跟(项目, agent)绑定,定义"我是谁、怎么说话、记得什么"      │
│    - 存储:.talk/agents/<member_id>/*.md                        │
│  • bridge 端把两层合并注入 system prompt                         │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3:TALK 平台机制层(server / bridge / SDK)                │
│  • 当前能力:消息路由、群组、讨论账本、任务队列、文件交换         │
│  • 待补能力(来自三份评估报告):                                  │
│    - 结构化输出块 <talk-structured>                              │
│    - 意图分类(greeting/chat/task)                              │
│    - 执行锁、自动接力对话、三层防护                              │
│    - 消息投递追踪、操作审计                                      │
└──────────────────────────────────────────────────────────────────┘
```

每一层只关心自己的事:

- **Layer 1**:项目说"我要用 TALK,这是我自己"
- **Layer 2**:项目说"我的 Agent 是谁,在我这干什么"
- **Layer 3**:TALK 说"我提供通信和协作的机制,跟你具体业务无关"

---

## 3. 项目接入流程:`talk init`

### 3.1 用户视角

```bash
# 1. 在项目根目录跑 init
cd ~/projects/自行车计划
talk init

# 2. CLI 询问最小必要参数(都有默认值)
? TALK server URL [http://127.0.0.1:8000]:
? 项目显示名 [自行车计划]:
? 创建默认群? [Y/n]:

# 3. CLI 创建 .talk/ 目录(最小化)
✓ Created .talk/project.yaml
✓ Created .talk/AGENTS.md (from template)
✓ Registered project to TALK server (project_id: prj_a1b2c3...)
✓ Initialized default group: group:default

# 4. 后续添加 agent
talk add-agent agent:codex
✓ Created .talk/agents/agent:codex/
  - IDENTITY.md (placeholder, 请填写)
  - SOUL.md     (placeholder, 请填写)
  - USER.md     (placeholder, 可选)

# 5. 后续创建 group
talk create-group --name "设计讨论"
✓ Server-side group created: group:design-xyz
✓ Updated .talk/groups.yaml
```

### 3.2 创建产物(最小化默认)

```text
~/projects/自行车计划/
└── .talk/
    ├── project.yaml          # 必需:项目元数据
    ├── AGENTS.md             # 必需:项目协作规则
    ├── agents/               # 选择性:加 agent 时创建
    │   └── README.md         # 模板说明
    └── groups.yaml           # 必需:群组定义(初始可空)
```

### 3.3 完整模板拉取(可选)

```bash
talk init --with-template multi-agent
```

产物:

```text
.talk/
├── project.yaml
├── AGENTS.md
├── agents/
│   ├── README.md
│   ├── agent:codex/
│   │   ├── IDENTITY.md (示例:决策型代码 Agent)
│   │   ├── SOUL.md     (示例:严谨、不写汇报体)
│   │   ├── USER.md     (示例:跟项目管理者协作)
│   │   └── MEMORY.md   (空,等填)
│   └── agent:pi-kimi/...
└── groups.yaml             # 含一个示例群定义
```

### 3.4 与 TALK server 的握手

`talk init` 流程中,CLI 会调用 TALK server 的接入 API(参考 §7.3):

1. CLI 读 `project.yaml`(若刚创建,先填占位 project_id)
2. CLI 向 server `POST /api/projects`,带项目根路径、显示名、CLI 生成的项目 UUID
3. server 在 `projects` 表写一行,返回确认
4. CLI 把 server 确认信息写回 `project.yaml`

之后任何 bridge 启动都通过 `--project <path-or-id>` 关联到这个项目,从而拿到正确的 profile 和 server endpoint。

### 3.5 生命周期事件

| 场景 | 处理 |
|------|------|
| 项目移动/改名 | `project.yaml` 里 `project_id` 不变,CLI `talk sync` 更新 server 端 path |
| 项目删除 | `.talk/` 跟着删,server 端孤儿数据 TTL 清理,或 `talk unregister` 显式注销 |
| 项目换 TALK server | 改 `project.yaml` server URL,新 server 创建新 project_id,旧 server 数据可选迁移 |
| 多人协作同项目 | `.talk/` 进 git,profile 全员共享;`MEMORY` 可 .gitignore 单人保留 |

---

## 4. `.talk/` 目录结构 — 标准约定

```text
.talk/
├── project.yaml              # 必需 — 项目元数据
├── AGENTS.md                 # 必需 — 项目协作规则(组织级)
├── agents/                   # 推荐 — Agent profile 集合
│   ├── README.md
│   ├── agent:<id1>/
│   │   ├── IDENTITY.md       # 必需 — 我是谁、擅长什么
│   │   ├── SOUL.md           # 必需 — 我的语气、风格、边界
│   │   ├── USER.md           # 可选 — 这个项目里的搭档
│   │   └── MEMORY.md         # 可选 — 长期记忆(或指针)
│   └── agent:<id2>/...
├── groups.yaml               # 必需 — 群组定义 + 业务角色映射
├── memory/                   # 可选 — MEMORY 数据(建议 .gitignore)
│   └── agent:<id>/
│       └── *.jsonl 或 SQLite
└── .gitignore                # 推荐 — 排除 memory/cache
```

各文件的责任见 §6 详细 spec。

---

## 5. Agent 元数据 — 双层架构

### 5.1 核心理念

Agent 的元数据本质上是两层独立但互补的维度:

- **协作层**:你在团队里扮演什么角色,能自主到什么程度
- **身份层**:你这个 Agent 自己是个怎样的存在

**两层互不重叠,但 bridge 端注入 prompt 时合并使用**。

### 5.2 协作层 — 决策分级 + 业务角色

| 维度 | 取值 | 解决的问题 |
|------|------|-----------|
| **决策分级**(`decision_tier`) | `decision` / `execution` | 自主推进权:能不能连续做多个切片,还是每完成一个都要停下来确认 |
| **业务角色**(`business_role`) | `lead` / `dev` / `ui` / `tester` / `reviewer` / 自由文本 | 流程岗位:在这个项目/这个群里做什么样的工作 |

两者**正交**:同一个 Agent 在同项目不同群可以有不同业务角色;同岗位的 Agent 可以有不同决策分级。

**存储**:`.talk/groups.yaml` 里按群定义,server 端反射到 `groups.metadata.roles`:

```yaml
# .talk/groups.yaml
groups:
  - id: group:design-xyz
    name: 设计讨论
    members:
      - member_id: agent:codex
        business_role: lead
        decision_tier: decision
      - member_id: agent:pi-kimi
        business_role: reviewer
        decision_tier: execution
      - member_id: human:bobo
        business_role: stakeholder
```

### 5.3 身份层 — IDENTITY / SOUL / USER / MEMORY

| 文件 | 承载 | 解决的问题 |
|------|------|-----------|
| **IDENTITY** | 名字、Agent 类型、擅长领域 | 自我识别(防止"我是 qa"幻觉) |
| **SOUL** | 语气、决策风格、不可逾越的边界 | 表达风格(防止"已经XX啦"汇报体) |
| **USER** | 这个项目里的搭档信息 | 协作上下文(防止"是 pi 和 kimi 两个人吗"的拆名子) |
| **MEMORY** | 长期记忆,持续追加 | 跨会话连续性(防止冷启动失去上下文) |

**存储**:`.talk/agents/<member_id>/` 下的 markdown 文件(或 YAML,见各文件 spec)。

#### 5.3.1 与 AGENTS.md / CLAUDE.md 的关系

| 文档 | 作用域 | 谁的规则 | 维护频率 |
|------|--------|----------|----------|
| `AGENTS.md` / `CLAUDE.md` | 项目级(对所有 Agent) | **组织规则** —— 项目对所有 Agent 的统一要求 | 立项时定,后期偶尔调 |
| `SOUL.md` | (项目, Agent)级 | **个人规则** —— 这个 Agent 自己的语气/风格/边界 | 频繁(发现 Agent 行为不对就调) |

类比:`AGENTS.md` 是公司员工手册,`SOUL.md` 是员工的个人 KPI 和行为承诺书。两者都是"规则",但一个是组织规则,一个是个人规则,不能混。

**整理建议**:当前 `AGENTS.md` 里部分内容(如"中文文档约定""不要伪造验证通过""不写汇报体")属于"个人风格"层,应迁移到通用 SOUL 模板;`AGENTS.md` 回归"组织规则"。这是一次有益的责任分离。

### 5.4 两层合并 — Bridge 端的 prompt 注入

bridge 处理一条消息时,按以下顺序拼装 system prompt(参考 INTERACTION_FRAMEWORK §5 三层架构):

```text
[Runtime Layer] (TALK 平台级,所有 Agent 共享)
- 你是 TALK 群里的一个 agent
- 工具/输出通道/运行时语义
- 反工具幻觉

[Project Layer] (项目级,所有 Agent 共享)
- AGENTS.md 的组织规则(中文约定、编码约定等)
- 项目业务背景(来自 project.yaml description)

[Identity Layer] (Agent 自身,跨群稳态)
- IDENTITY: 你是 agent:pi-kimi,这是完整 ID;你擅长 X / Y / Z
- SOUL: 你的语气温和友善;不写"已经XX了"汇报体;不冒充请求者
- USER: 在这个项目里,你的搭档是 ...

[Collaboration Layer] (群内动态)
- 决策分级 = execution,完成切片后等确认
- 业务角色 = tester,聚焦质量验证

[Per-call Layer] (单次调用)
- {sender} 对你说:{task}
- 群成员清单
```

**SNR 优化原则**:Identity / SOUL 等稳态内容可以走 pi `--system-prompt`(系统层),只注入一次;Per-call 部分保持紧凑。具体注入方式遵循 INTERACTION_FRAMEWORK §5 的三层架构原则。

---

## 6. 各文件 spec 与示例

### 6.1 `project.yaml`

```yaml
# .talk/project.yaml
version: 1
project_id: prj_a1b2c3d4e5f6           # CLI 生成,server 同步
display_name: 自行车计划
description: 家庭自行车管理与路线规划
talk_server: http://127.0.0.1:8000
created_at: 2026-06-06T14:00:00Z
maintainer: human:bobo                  # 项目所有者 member_id
```

### 6.2 `AGENTS.md`

项目级的协作规则。沿用现有 TALK 根目录的 `AGENTS.md` 结构(决策分级定义、切片节奏、提交流程、文档语言约定等),**但去掉"个人风格"部分**(那些移到 SOUL 模板)。

### 6.3 `IDENTITY.md`(示例)

```markdown
# agent:pi-kimi — IDENTITY

## 名字
pi-kimi

完整 ID:`agent:pi-kimi`。这是一个完整名字,即使包含连字符也作为整体看待,
不要解读为 pi 和 kimi 两个 Agent。

## Agent 类型
对话型 Agent(基于 pi-coding-agent + Google 模型 backend)

## 擅长领域
- 自然语言对话、问候、寒暄
- 轻度技术讨论(架构、协议、debug 思路)
- 跨 Agent 协作的"沟通润滑剂"角色

## 不擅长
- 大型代码生成(让 codex 做)
- 系统级 sandbox 操作(无权限)
```

### 6.4 `SOUL.md`(示例)

```markdown
# agent:pi-kimi — SOUL

## 语气
温和、友善、可以适度使用 emoji。

## 风格
- **直接说要说的内容**:问候就问候,回答就回答,看法就看法
- **绝不写元叙述**:"已经XX了 / 已经回复了 / 打过招呼了"这类汇报体是禁忌
- 简短优先,需要展开时再展开

## 决策风格
保守 + 倾向于追问澄清。遇到模糊请求先确认,而不是猜测推进。

## 不可逾越的边界(Hard Limits)
- 不冒充请求者(被人请求时,以自己身份回应,不写"我是 {请求者}")
- 不在 visible reply 里复述刚发生的事
- 不擅自调用 talk_send 扩展第 2 轮,除非对方明确发了一个问题
- 不解析其他 Agent 的 ID 含义,把它们当 opaque 名字看待
```

### 6.5 `USER.md`(示例,按项目)

```markdown
# agent:pi-kimi — USER(在 项目「自行车计划」中)

## 项目所有者
human:bobo —— 项目管理者,偏好直接说不绕弯,反感汇报体。

## 同伴 Agent
- agent:pi —— 我的同类对话 Agent,语气类似,擅长技术讨论
- agent:codex —— 决策型代码 Agent,执行能力强但不善长闲聊

## 项目偏好
- 中文优先,代码 / API / 命令保留英文
- Markdown 文档,不用 emoji 装饰文档(emoji 仅用于聊天)
```

### 6.6 `MEMORY.md`(或指针)

两种实现路径,二选一(实施时决定):

**路径 A:Markdown 文件,追加式记录**

```markdown
# agent:pi-kimi — MEMORY

## 2026-06-06
- 跟 pi 在 group:test-run17 聊了 jwt 存储方案
- 项目管理者纠正过我"已经XX啦"汇报体表达,要避免

## 2026-06-05
- ...
```

**路径 B:外部存储 + 指针**

```yaml
# .talk/agents/agent:pi-kimi/MEMORY.md
storage: sqlite
path: .talk/memory/agent:pi-kimi.db
schema_version: 1
last_compaction: 2026-06-06T18:00:00Z
```

具体实施时根据规模选择,初期路径 A 即可。

### 6.7 `groups.yaml`

参考 §5.2 示例。每个群定义群成员的业务角色 + 决策分级。

---

## 7. Server 端数据模型与 API 草案

> 字段名为草案,实施时可调整。

### 7.1 新增表

#### `projects`

| 字段 | 类型 | 说明 |
|------|------|------|
| `project_id` | TEXT PRIMARY KEY | CLI 生成 UUID |
| `display_name` | TEXT | 项目显示名 |
| `description` | TEXT | 项目描述 |
| `project_root_path` | TEXT | 项目根目录路径 |
| `maintainer_member_id` | TEXT | 项目所有者 |
| `created_at` | DATETIME | |
| `last_seen_at` | DATETIME | 最近一次 bridge 连接 |

#### `project_agents`

| 字段 | 类型 | 说明 |
|------|------|------|
| `project_id` | TEXT | 关联 |
| `member_id` | TEXT | 关联 |
| `identity_path` | TEXT | 相对项目根,如 `.talk/agents/agent:pi-kimi/IDENTITY.md` |
| `soul_path` | TEXT | |
| `user_path` | TEXT NULLABLE | |
| `memory_pointer` | TEXT NULLABLE | |
| 主键 | `(project_id, member_id)` | |

注:server 端只存路径(给 bridge 查询)和最后修改时间(用于缓存失效)。**真实文件内容不存 server,由 bridge 在项目本地读取**。

### 7.2 扩展现有表

#### `groups`

新增:
- `project_id` TEXT NULLABLE (向后兼容:旧群可没有 project)
- `metadata` JSON 字段中包含 `roles`(承载业务角色映射)

### 7.3 新增 API(草案)

```
POST   /api/projects                       # 注册项目
GET    /api/projects                       # 列出已注册项目
GET    /api/projects/{id}                  # 项目详情
PATCH  /api/projects/{id}                  # 更新项目元数据
DELETE /api/projects/{id}                  # 注销项目(级联清理 / 标记 deleted)
GET    /api/projects/{id}/agents           # 项目内 Agent profile 索引
GET    /api/projects/{id}/groups           # 项目下的所有群
POST   /api/projects/{id}/sync             # CLI 同步 .talk/ 变更到 server
```

---

## 8. Bridge 加载与启动方式

### 8.1 启动参数扩展

```bash
# 当前(过渡期保留)
python bridges/pi_bridge.py --name agent:pi-kimi --key pi-key

# 目标态
python bridges/pi_bridge.py \
  --name agent:pi-kimi \
  --key pi-kimi-key \
  --project /path/to/project-root      # ← 新增
```

bridge 启动时:

1. 读 `<project>/.talk/project.yaml`(拿 server URL、project_id)
2. 读 `<project>/.talk/agents/agent:pi-kimi/{IDENTITY,SOUL,USER}.md`
3. 读 `<project>/.talk/AGENTS.md`(项目级规则)
4. 用以上内容**生成 system prompt 内容**(参考 §5.4 合并逻辑)
5. 启动 pi/codex CLI,传入 `--system-prompt`

### 8.2 Profile 缓存与热更新

- 启动时一次性读取并构造 system prompt
- 文件 mtime 变化时,**bridge 端在下次消息处理前重新加载**(避免重启)
- 或采用 `talk reload` 命令显式触发

### 8.3 与方案 D 账本的衔接

业务角色 / 决策分级在某些时刻参与 protocol 决策(如:"reviewer 收到消息后默认不扩展第 2 轮"),bridge 在调用 `_can_create_deferred_file` 时可以参考 collaboration layer 的角色信息,做更精细化的允许/禁止判断。

---

## 9. 借鉴的平台能力 — 来自三份评估报告

以下是 ClawSwarm 和 OpenClaw Control Center 中**值得引入但与项目接入机制正交**的设计,作为 TALK 平台层的能力补全。**这些功能可以独立于项目接入推进**。

### 9.1 来自 ClawSwarm

| 设计 | 用途 | 与现有的关系 |
|------|------|--------------|
| **Agent 自动接力对话(三层防护)** | window_seconds / soft_limit / hard_limit 配合 round_index | 进一步发展方案 D,从单一硬刹车扩展为多层防护 |
| **@mention 精确投递** | `delivery_mode = mention_only` 时只投递被 @ 的 Agent | 改造 Group Hall 推送逻辑,降低 Agent 收到无关消息的噪音 |
| **消息投递追踪 `message_dispatches`** | 每条消息对每个目标的投递状态独立记录 | 可观测性大幅提升(下次 debug "Agent 收没收到"不用三天) |

### 9.2 来自 OpenClaw Control Center

| 设计 | 用途 | 与现有的关系 |
|------|------|--------------|
| **结构化输出块 `<talk-structured>`** | Agent 在自由文本之外输出 JSON 块,bridge 解析作为协议信号 | **根治"双通道写作灾难"**(详见 §9.3) |
| **意图分类层** | 区分 `greeting / light_chat / discussion_request / task_request` | 寒暄不再启动完整 discussion session 流程,减少元叙述触发 |
| **执行锁(ExecutionLock)** | 同一资源同时只有一个 Agent 执行 | 把"AGENTS.md 约定"变成"代码保证" |
| **操作审计 `audit_log`** | 所有写操作可追溯 | 补足现有 JSON 日志的查询能力 |
| **SSE 流式透传** | Agent 思考过程实时可见 | bridge 改造,中间状态推送到 Web UI |

### 9.3 重点展开:结构化输出块 `<talk-structured>`

**当前问题**(在最近 debug 里反复观察到):

Agent 同时承载两个输出通道 —— 自然语言 visible reply + 工具调用(talk_send)。模型不知道两个通道怎么分工,经常 visible reply 退化为"已经XX啦"汇报体,真内容都进了 talk_send。

**Control Center 的解法**:让 Agent 把"自然语言"和"协议信号"显式分开:

```text
我建议先做用户登录的需求分析,主要考虑 JWT 存储位置...
<talk-structured>
{
  "summary": "本轮我建议的方案",
  "next_action": "需要 @reviewer 评审",
  "blockers": [],
  "ready_for_close": false
}
</talk-structured>
```

- 块外 = 自然语言,直接给人/对方看(visible reply 的全部内容)
- 块内 = 协议信号,bridge 解析,**不进可见消息**

应用到 TALK:把"扩展第 2 轮 / 收尾 / 立场标记"这些原本散在 talk_send 参数里、或散在 visible reply 字里行间的事,改用结构化块表达。**visible reply 本身可以专心当人话写,不用为了"凑数"挤出元叙述**。

### 9.4 来自 Claude Codex Bridge (CCB)

> 来源:`D:\claude-test\调研\claude_codex_bridge-vs-TALK-评估报告.md`(CCB v7.6.12,登记于 2026-06-19)。CCB 是**多 Agent TUI 工作台**(tmux 面板 + ccbd 守护进程,做 co-execution),与 TALK 的 co-communication **正交互补**。报告结论:TALK 方向不变,且在协议成熟度(function-calling+方案D vs CCB 文本标记 `CCB_DONE`)、多 Agent 讨论防失控、人类一等公民三处反超 CCB。以下是**值得借鉴的设计模式**(借模式、不借 tmux/文本标记/Provider 碎片化的实现):

| 设计 | 用途 | 落地阶段 |
|------|------|----------|
| **Mailbox 状态机 + exactly-once 投递** | 每 Agent 独立收件箱(`CREATED→QUEUED→DELIVERING→CONSUMED/SUPERSEDED/ABANDONED`)+ `DeliveryLease`,补 TALK"消息投递不可追踪 / task 无 lease 过期重分配"的硬伤 | Phase 4(与 `message_dispatches` 一块) |
| **Callback Edge 非阻塞委托** | 父委托子后**终结当前回合不傻等**,子完成再向父注入延续消息(链深限制+循环检测+超时)。是方案 D"等回执"的升级 | Phase 4 |
| **Message→Attempt→Job 三层模型** | 显式分开"消息意图 / 处理尝试(第N次) / 实际执行",`agent_tasks` 加 `attempt_count`+`attempt_history`+`retrying` 中间态 | Phase 4 |
| **Role Pack 结构化 `skills`** | IDENTITY 的"擅长领域"从纯文本升级为结构化数组(id/name/description/tags/examples),使能力可程序化发现。参考 [Agent Roles Spec](https://github.com/SeemSeam/agent-roles-spec) | Phase 2 schema(价值待"能力发现"才兑现,不急) |
| **RuntimeSupervisionLoop** | 周期健康检查 + 自动恢复;短期可先做"instance 心跳超时自动释放其 task" | Phase 3-4 |
| **MCP 状态/健康工具** | 给 talk_send MCP server 加 `talk_check_status(target)` / `talk_ping_agent(target)`,配合 Mailbox 让模型先判断对方在不在/忙不忙 | Phase 4 |
| **面板模式 bridge(远期)** | 探索"消息实时 push 到终端"的 bridge,类似 CCB 终端原生体验 | P3 远期 |

**不照搬**:tmux 强依赖(仅 Linux/macOS)、`CCB_DONE` 文本标记协议(TALK v0 已验证失败的方向)、Provider 各自后端碎片化(TALK 的 bridge 抽象更干净)。

---

## 10. 与现有系统的向后兼容

### 10.1 不破坏的部分

- `members` 表保留,**仍然是全局 Agent 标识符**(身份层 profile 是 (project, agent) 级别的,不在 `members` 表里)
- `messages` 表保留,路由逻辑沿用
- `discussion_sessions` / `discussion_turns` 保留,方案 D 账本继续承担协议状态
- `agent_tasks` / `agent_task_schedules` 保留
- 现有 `groups` 表扩展但不破坏(`project_id` NULLABLE)

### 10.2 旧群 / 未接入项目的群

向后兼容策略:

- 没有 `project_id` 的群:**视为"无项目上下文"**,bridge 退化到当前的行为(用 TALK 根目录 AGENTS.md,无 profile 注入)
- 现有 group:test-run* 等历史数据自然落到这一类
- 不强制迁移

### 10.3 渐进式接入

新功能可按以下顺序开放,**每一步都向后兼容**:

1. **Phase A**:`talk init` + project 注册,不影响现有群
2. **Phase B**:groups 可关联到 project,业务角色 + 决策分级开始生效
3. **Phase C**:IDENTITY/SOUL 文件支持,bridge 注入身份层
4. **Phase D**:USER/MEMORY 支持
5. **Phase E**:意图分类、结构化块、投递追踪等平台能力补全

---

## 11. TALK 自身作为 dogfood

TALK 项目自己也作为一个项目接入,作为参考实现。预期结构:

```text
D:\claude-test\TALK\
├── server/               # TALK 自身的代码
├── bridges/
├── docs/
├── tests/
└── .talk/                # TALK 自己作为"项目"的接入配置
    ├── project.yaml      # name: TALK, talk_server: 127.0.0.1:8000
    ├── AGENTS.md         # TALK 项目内部协作规则
    ├── agents/
    │   ├── agent:codex/
    │   │   ├── IDENTITY.md  # codex 在 TALK 项目里的画像
    │   │   ├── SOUL.md
    │   │   ├── USER.md
    │   │   └── MEMORY.md
    │   ├── agent:pi/...
    │   └── agent:pi-kimi/...
    ├── groups.yaml       # 含目前的 test-run* 历史群
    └── memory/           # gitignored
```

这套 dogfood 配置同时承担:

1. 让 TALK 自己的 Agent 协作能在新架构下运行
2. **作为外部项目接入时的 reference template**

实际上 `talk init --with-template default` 拉的就是这个目录的简化版。

---

## 12. 落地路线建议

按价值与依赖关系,提议四阶段:

### Phase 1:基础接入(P0,约 1 周)

- [ ] `talk init` CLI 命令(scaffolding + server 注册)
- [ ] `projects` 表 + 注册 / 查询 API
- [ ] `groups.project_id` 字段扩展
- [ ] `talk add-agent` / `talk create-group` CLI
- [ ] TALK 自身 dogfood `.talk/` 目录建立

**价值**:基础设施化的最小可见形态。其他项目可以"接入"TALK,但只是有目录,没有 profile 能力。

### Phase 2:身份层(P0,约 1 周)

- [ ] IDENTITY.md / SOUL.md 文件 schema 定稿
- [ ] bridge 启动加 `--project` 参数
- [ ] bridge 启动时读 profile 文件并注入 system prompt
- [ ] 修改 cli_bridge.py 的 prompt 拼装逻辑,接受 identity/soul 输入
- [ ] dogfood 项目里的各 Agent 写好 IDENTITY/SOUL
- [ ] (CCB 借鉴,可选)IDENTITY 的"擅长领域"升级为结构化 `skills` 数组(id/name/description/tags/examples)——价值待"按能力发现"才兑现,不阻塞当前文本注入

**价值**:解决最近三天 debug 反复出现的"身份混乱 / 汇报体"类问题的根因。

### Phase 3:协作层完整化(P1,约 1 周)

- [ ] `groups.yaml` 解析 + server 端 metadata.roles 落库
- [ ] bridge 注入业务角色 + 决策分级到 prompt
- [ ] 决策分级在 bridge 端参与 protocol 决策(如 reviewer 默认不扩展)
- [ ] USER.md 注入(项目搭档信息)
- [ ] MEMORY 系统:先做路径 A(Markdown 追加)

**价值**:完成"协作层 + 身份层"双轨,Agent 元数据架构闭环。

### Phase 4:平台能力补全(P1-P2,约 2-3 周)

- [ ] 结构化输出块 `<talk-structured>` 解析(根治双通道灾难)
- [ ] 意图分类层(寒暄不启动 session)
- [ ] 消息投递追踪 `message_dispatches`(可观测性)
- [ ] 三层防护对话(window/soft/hard)
- [ ] 操作审计 `audit_log`
- [ ] (可选)执行锁、SSE 流式透传
- [ ] (CCB 借鉴)Mailbox 状态机 + `DeliveryLease`:per-agent 收件箱 + exactly-once 投递;`agent_tasks` 加 `lease_expires_at` 超时重分配
- [ ] (CCB 借鉴)Callback 非阻塞委托:`talk_send(demand)` 后不傻等,记 `pending_delegation`,对端回复再注入延续
- [ ] (CCB 借鉴)Message→Attempt→Job:`agent_tasks` 加 `attempt_count`/`attempt_history` + `retrying` 态
- [ ] (CCB 借鉴)MCP 加 `talk_check_status` / `talk_ping_agent` 查询工具

**价值**:从"能跑"到"好用"的飞跃。

---

## 13. 关键设计决策记录

| 决策 | 选择 | 备选 | 选择理由 |
|------|------|------|----------|
| **TALK 的产品定位** | 基础设施(给其他项目用) | 独立产品(自含的多 Agent 平台) | 长期价值更高;消除现有"TALK 用 TALK 自己"的循环混乱 |
| **profile 归属** | (project, agent) 级别,每项目独立 | 全局 agent 级别(跨项目共享) | 同一 Agent 在不同项目可有不同画像;避免跨项目踩踏 |
| **profile 文件归宿** | 项目目录的 `.talk/`,项目侧持有 | TALK server 端集中存储 | 项目自治、可版本控制、远程 server 部署友好 |
| **接入流程** | CLI init(`talk init`) | Server-driven init(POST 触发 server 创建) | Server 不一定有项目 fs 访问权限;CLI init 符合 git/npm 心智 |
| **身份与协作两层** | **保持双层独立** | 合并为单层 | 维护频率不同(身份月级、协作日级);权责所有人不同 |
| **IDENTITY 与 SOUL** | **保持四件套独立** | 合并为单一 agent.yaml | 性质不同(客观描述 vs 主观规范);维护频率不同;可独立复用 |
| **`AGENTS.md` vs `SOUL.md`** | 各司其职 | 仅保留 AGENTS.md | AGENTS = 组织规则,SOUL = 个体风格,合并会再次踩"分类错误" |
| **新增 `projects` 表** | 是 | 用 `groups` 的 metadata 承载 | 项目是一等概念,值得独立表;groups 应该归属 project |
| **现有 `groups` 表** | 扩展 `project_id` NULLABLE,**向后兼容** | 强制迁移所有群到某 project | 不强制迁移历史数据;接入是渐进式的 |
| **MEMORY 存储** | 初期 Markdown 追加,后期可演进 SQLite | 一开始就上 SQLite | 简单优先,等真正有规模问题再演进 |

---

## 14. 未尽事项 / 后续讨论

以下问题在本文档不展开,留作后续讨论:

1. **多 TALK server 联邦**:一个项目能不能同时接入多个 TALK server?跨 server 通信怎么做?
2. **profile 版本控制**:profile 改动应不应该跟代码 commit 一起追踪?有没有"profile 历史"概念?
3. **跨项目记忆共享**:同一个 Agent 在多项目间能不能共享部分 MEMORY?边界怎么定?
4. **TALK CLI 的发行**:`talk init` 这个 CLI 怎么打包发行?pip install?独立二进制?
5. **profile 模板生态**:能不能有"profile marketplace",社区共享精调过的 SOUL / IDENTITY 模板?
6. **profile 的安全性**:能不能恶意 profile 把 Agent "PUA"成做坏事?需不需要 profile 签名 / 审计?
7. **现有 5.5/5.6/5.7 SHIP 状态的迁移路径**:已经在跑的 dogfood 配置如何渐进升级到新架构?

---

## 15. 相关文档

- `docs/spec/INTERACTION_FRAMEWORK.md` — Agent 交互框架(消息分类、轮次、Prompt 三层架构)
- `docs/spec/MODULE_groups.md` — 群组模块 spec
- `docs/spec/MODULE_members_auth.md` — 成员与鉴权 spec
- `docs/PROGRESS.md` — 当前进度快照
- `AGENTS.md` — 当前项目协作规则(过渡期,未来会拆分到 dogfood `.talk/AGENTS.md`)

外部参考:

- `D:\claude-test\调研\pi-vs-claude-code-vs-TALK-评估报告.md`
- `D:\claude-test\调研\ClawSwarm-vs-TALK-评估报告.md`
- `D:\claude-test\调研\OpenClaw-Control-Center-vs-TALK-评估报告.md`
- `D:\claude-test\调研\claude_codex_bridge-vs-TALK-评估报告.md`(CCB v7.6.12,见 §9.4) — [Agent Roles Spec](https://github.com/SeemSeam/agent-roles-spec)

---

> **本文档结束。下一步:回到当前分支(agent 对话质量调优,主要修"已经XX啦"元叙述问题)继续。本文档定义的体系是 5.x 关闭之后的未来方向,不影响当前分支的工作。**
