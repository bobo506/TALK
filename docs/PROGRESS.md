# Project Progress

## Latest
Updated: 2026-06-15 (Asia/Shanghai) — Phase 1 基础接入 · 切片 1：`projects` 表 + 注册/查询 API

### 1) Current Agent Role
- 角色来源：`AGENTS.md`；本轮启动角色：Claude = **决策 Agent**（本轮由项目管理者改 PROGRESS 显式声明）。
- 当前 Codex 角色：执行 Agent。
- 当前分支：`claude/project-integration-phase1`（从 `main` 新开）。切片 1 已提交本地 `52ccf78`，**尚未 push**（等管理者确认是否 push / 开 PR）。`AGENTS.md` 角色定义改动属管理者治理改动，未纳入本切片 commit。
- 用量门禁：`~/.claude/usage.json` 为空，无法读取占比；按"无法获取用量"规则节制——Phase 1 涉及数据库改动，本轮 1 片即暂停汇总。

### 2) Current Progress
- **核心主线重启**：前端/对话质量支线收尾后，项目管理者确认回到 `PROJECT_INTEGRATION.md` §12 四阶段路线，选定 **Phase 1 基础接入** 为起点。
- **切片 1 完成**：server 端落地 `projects` 表 + 完整注册/查询 CRUD API（整条主线的最小地基）。
  - `Project` ORM 表：`project_id`(PK) / `display_name` / `description` / `project_root_path` / `maintainer_member_id`(FK→members) / `created_at` / `last_seen_at`。
  - `POST /api/projects`（注册，缺省生成 `prj_<hex12>`，maintainer 缺省取当前成员并校验）、`GET`（列表 / 详情）、`PATCH`（部分更新，`model_fields_set` 实现真 PATCH）、`DELETE`（注销 204）。
  - 写操作限人类成员（`_require_human`），读操作任意已鉴权成员；与 groups 路由同构。
- 8 个新单测 + 全套件 178/178 通过，无回归。

### 3) Open Questions / Pending Confirmation
- **本切片已提交分支 `claude/project-integration-phase1`（52ccf78）**：是否 push GitHub / 开 PR 等管理者确认。
- `last_seen_at` 暂等于 `created_at`；bridge 连接时刷新逻辑留待 bridge `--project` 切片。
- （支线遗留，未启动）成员软删除、Hall 删除真实 API + 二次确认——非主线，暂缓。

### 4) Next Plan
1. 本轮按刹车规则暂停，等管理者确认是否 push + 是否继续下一片。
2. Phase 1 续切片候选：① `groups.project_id` NULLABLE 字段扩展 + 旧群向后兼容；② `talk` CLI 脚手架（`talk init` 写 `.talk/` + 调注册 API）；③ TALK 自身 dogfood `.talk/` 目录建立。
3. 之后进入 Phase 2 身份层（IDENTITY/SOUL + bridge `--project` 注入）。

### 5) Verification
- `python -m unittest tests.test_projects -v` → 8/8 通过。
- `python -m unittest discover -s tests -q` → **178/178 通过**，无回归。
- 未做：CLI、`groups.project_id` 扩展、`/api/projects/{id}/agents|groups|sync` 子资源、bridge `--project`——均为后续切片。

### 6) Changed Files
- `server/models.py`（新增 Project ORM + 3 个 schema）
- `server/routes/projects.py`（新文件）
- `server/main.py`（注册路由）
- `server/db.py`（projects 索引）
- `tests/test_projects.py`（新文件）
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 未来方向

来自三份评估报告（`docs/调研/` 系列：pi-vs-claude-code、ClawSwarm、OpenClaw Control Center、Multica）与 `docs/spec/PROJECT_INTEGRATION.md` 设计草案，作为 5.x agent 通信主线关闭后的下一阶段方向（暂未启动实施）：

- **TALK 基础设施化**：从"独立产品"重新定位为"给其他项目使用的多 Agent 协作基础设施"
- **项目接入机制**：`talk init` + `.talk/` 目录约定 + 项目级 server API
- **Agent 元数据双层架构**：
  - 协作层（已有概念，未完全实施）：决策分级 + 业务角色
  - 身份层（待引入，借鉴 ClawSwarm）：IDENTITY / SOUL / USER / MEMORY 四件套，按项目分配
- **平台能力补全**：
  - 结构化输出块 `<talk-structured>`（OpenClaw）—— 治本"双通道写作灾难"
  - 意图分类（OpenClaw）：greeting / chat / task，避免寒暄被当任务执行
  - Agent 自动接力对话三层防护（ClawSwarm）：window / soft / hard limit
  - 消息投递追踪 `message_dispatches`（ClawSwarm / Multica）—— 可观测性
  - 零信任安全模型（Multica）：agent vs human 隔离、凭证不可自读、操作审计
  - COLD / WARM / RESUME 上下文读取（Multica）—— MEMORY 实施方向
  - 任务失败 14 类精细分类与差异化重试（Multica）
- **四阶段落地路线**（详见 PROJECT_INTEGRATION.md §12）：
  1. 基础接入（`talk init` + `projects` 表）
  2. 身份层（IDENTITY/SOUL 文件 + bridge profile 加载）
  3. 协作层完整化（业务角色注入 + MEMORY 系统）
  4. 平台能力补全（结构化块 + 意图分类 + 投递追踪 + 三层防护）

完整设计请参考 `docs/spec/PROJECT_INTEGRATION.md`（15 节，~580 行）。

---

## 当前已知技术债

- **双通道写作灾难残留**：agent 在调 talk_send 的同时仍要写 visible reply，有时 visible reply 退化为"凑数"。根治方案在 PROJECT_INTEGRATION §9.3 结构化输出块（Phase 4）。
- **`--no-extensions` 是粗粒度规避**：禁用所有 pi 自动发现扩展（含 plan-mode bug 源）。等 upstream `earendil-works/pi#5327` 修复后可去掉此 flag。
- **codex 黑盒补测未完成**：当前测试环境未装 codex CLI，agent:codex 在群里的端到端流程只跑过独立 probe，未跑过完整 Group Hall 黑盒。环境装好即可补。
- **PROJECT_INTEGRATION.md 仅为草案**：四阶段路线、`.talk/` 约定、双层 Agent 元数据等均为后续工作，未启动实施。

---

## Recent Notes
- 🎯 **2026-06-07 08:50 5.7+ 对话质量收敛**：身份锚紧凑内嵌、反元叙述系统层、废弃 discussion_context 三招收住。黑盒 `group:1488c22048e3` 上 pi/pi-kimi 对话自然，无身份混乱、无循环汇报。
- 📐 **2026-06-07 08:30 PROJECT_INTEGRATION.md 立项**：TALK 从"独立产品"重校准为"基础设施层"，规划 `.talk/` 约定 + Agent 元数据双层架构 + 借鉴 ClawSwarm/OpenClaw/Multica 的平台能力 + 四阶段落地路线。
- 🔧 **2026-06-06 22:00 INTERACTION_FRAMEWORK §5.3 二次/三次修正**：身份注入从"独占首行"改"紧凑内嵌"；废弃 600 字"TALK 控制上下文"在 pi/codex 分支的注入。
- 🎉 **2026-06-02 23:55 5.x agent-to-agent 通信主线 SHIP**。方案 D（`discussion_turns` 显式账本）、Prompt 三层架构（SNR 4x）、talk_send function-calling 三条主线一并落地。Upstream issue #5327 在外侧跟进。
- 2026-06-02 23:30 Pi extension dispatch 根因锁定为 plan-mode `setActiveTools` 全量替换，bridge 加 `--no-extensions` 规避。
- 2026-06-02 21:45 codex MCP 端到端通过：`--dangerously-bypass-approvals-and-sandbox` + UTF-8 env。
- 2026-06-01 18:00 codex MCP 路径集成完成：新增 `bridges/talk_send_mcp.py`。
- 2026-06-01 docs 目录二次整理：根目录 *.md 全部移至 `spec/` 或 `guides/`。
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
