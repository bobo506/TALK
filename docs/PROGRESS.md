# Project Progress

## Latest
Updated: 2026-06-15 (Asia/Shanghai) — Phase 1 基础接入 · 切片 1–4 完成（接入机制 + CLI + dogfood）

### 1) Current Agent Role
- 角色来源：`AGENTS.md`；本轮启动角色：Claude = **决策 Agent**（管理者显式声明）。管理者本轮另改 `AGENTS.md`：决策 Agent **默认只给方案、需管理者明确要求才开发**。
- 当前 Codex 角色：执行 Agent。
- 当前分支：`claude/project-integration-phase1`（从 `main` 新开）。切片 1–4 已提交本地（`41ad2dd`→`dec9d25`），**尚未 push**（等管理者确认 push / 开 PR）。
- `AGENTS.md` 角色定义改动属管理者治理改动，**未纳入**任何切片 commit，留工作区待管理者处理。

### 2) Current Progress
- **核心主线重启**：回到 `PROJECT_INTEGRATION.md` §12 四阶段路线，**Phase 1 基础接入已基本成型**。管理者授权连做切片 2→3→4。
- **切片 1**（`41ad2dd`）：`projects` 表 + 注册/查询 CRUD API（`POST/GET/PATCH/DELETE /api/projects`，写操作限人类成员）。
- **切片 2**（`523fffe`）：`groups.project_id` NULLABLE 扩展，群可归属 project；旧群保持无项目上下文，向后兼容。
- **切片 3**（`570c18d`）：`talk` CLI 脚手架——`python -m cli.talk init` 生成 `.talk/` + 可选注册到 server；`register_project` http client 可注入便于测试；新增 `pyyaml` 依赖；Windows GBK 控制台 UTF-8 输出修复。
- **切片 4**（`dec9d25`）：TALK 自身 dogfood `.talk/`（用 CLI 生成基座 + 三 agent 身份层四件套 + 带角色/分级的 groups.yaml），同时作为外部接入参考模板。
- 全套件 **189/189 通过**，无回归。

### 3) Open Questions / Pending Confirmation
- **分支待 push / 开 PR**：切片 1–4 在 `claude/project-integration-phase1`，等管理者确认。
- **`:`→`_` 目录净化约定待 ratify**：member_id 含 `:`，Windows 不能做目录名，agent 目录采用 `agent:codex → agent_codex/`；bridge 在 Phase 2 查 profile 时需落地同样的净化映射。
- `last_seen_at` 暂等于 `created_at`；bridge `--project` 连接刷新逻辑留待 Phase 2。

### 4) Next Plan
1. 等管理者确认是否 push 分支 / 开 PR。
2. **Phase 2 身份层**：bridge 加 `--project` 参数 → 读 `.talk/agents/<member_id>/{IDENTITY,SOUL}.md` → 注入 system prompt（须落地 member_id→目录 `:`→`_` 净化）。根治 dogfood 反复出现的身份混乱/汇报体。
3. Phase 1 收尾项（按需）：§7.3 子资源 `/api/projects/{id}/agents|groups|sync`、`talk add-agent` / `talk create-group` 子命令。

### 5) Verification
- 逐片：`test_groups`+`test_projects` 16/16；`test_talk_cli` 8/8。
- `python -m unittest discover -s tests` → 切片 2 后 181/181、切片 3 后 **189/189**，均无回归。
- `python -m cli.talk init` 实跑生成结构正确；dogfood `.talk/` 全部 YAML 可解析、3×4 profile 齐全、`memory/` 忽略生效。

### 6) Changed Files（切片 1–4 累计）
- 新增 `server/routes/projects.py`、`cli/__init__.py`、`cli/talk.py`、`tests/test_projects.py`、`tests/test_talk_cli.py`
- 新增 `.talk/`（project.yaml / AGENTS.md / groups.yaml / agents 三套 profile / .gitignore，共 17 文件）
- 改 `server/models.py`、`server/main.py`、`server/db.py`、`server/routes/groups.py`、`tests/test_groups.py`、`requirements.txt`
- 改 `docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

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
