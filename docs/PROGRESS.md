# Project Progress

## Latest
Updated: 2026-06-15 (Asia/Shanghai) — Phase 2 身份层启动：切片 7 profile 加载器完成，切片 8 注入策略待管理者选型

### 0) Phase 2 进行中（用量门禁触发，暂停）
- **切片 7 完成**（`ffa80b2`）：`cli/profiles.py` profile 加载器（纯函数地基）+ 7 单测。
- **注入策略已定 = B 方案（系统层）**：管理者拍板——人设作为"背景底色"放进 agent 系统层（`--system-prompt`），不混进每条消息流（§5.4 路线）。
- **切片 8a 完成**（`fc15aa6`）：`compose_system_prompt(base, profile)` 纯函数——profile 作背景拼进系统提示，带"这是底色、别复述"框定；profile 为空时 base 原样返回（无 profile 成员零行为变化）。+3 单测。全套件 **211/211**。
- **切片 8b 待做（需真机验证）**：把 pi/codex bridge 的 `--system-prompt` 真正接到 `compose_system_prompt` + 加 `--project` 参数。**重活、改 agent 现有行为、本机无 pi/codex CLI 无法黑盒验证** → 留待有真机环境时做；严格 opt-in（`--project` 缺省字节一致）。
- **切片 9（安全，可并行）**：server `project_agents` 表 + `GET /api/projects/{id}/agents` + `POST /api/projects/{id}/sync`，纯服务端、可测、与 8b 正交。
- **暂停原因**：5 小时窗口已用约 86%（≥85% 红线）。按规则 + 管理者指示，做完一个小切片（8a）即停，等用量刷新再继续。

---

## Phase 1（已完成）
Updated: 2026-06-15 (Asia/Shanghai) — Phase 1 全部完成（接入机制 + 4 CLI 子命令 + dogfood + 项目群子资源）

### 1) Current Agent Role
- 角色来源：`AGENTS.md`；Claude = **决策 Agent**。管理者已改 `AGENTS.md`：决策 Agent **默认只给方案、需管理者明确要求才开发**（已提交 `d110a86`）。
- 当前 Codex 角色：执行 Agent。
- 当前分支：`claude/project-integration-phase1`（从 `main` 新开），含 8 个 commit（切片 1–6 + AGENTS.md 治理 + docs），**尚未 push**（等管理者确认 push / 开 PR）。

### 2) Current Progress
- **Phase 1 基础接入全部完成**（`PROJECT_INTEGRATION.md` §12 四阶段路线第一阶段）：
  - 切片 1（`41ad2dd`）：`projects` 表 + 注册/查询 CRUD API。
  - 切片 2（`523fffe`）：`groups.project_id` NULLABLE 扩展 + 旧群向后兼容。
  - 切片 3（`570c18d`）：`talk init` CLI 脚手架 + `pyyaml` 依赖 + Windows UTF-8 输出修复。
  - 切片 4（`dec9d25`）：TALK 自身 dogfood `.talk/`（CLI 生成 + 三 agent 身份层 + 角色/分级 groups.yaml）。
  - 切片 5（`da0dad7`）：`talk add-agent` / `talk create-group` 子命令 + `member_dir_name` 净化 helper。
  - 切片 6（`99b9076`）：`GET /api/projects/{id}/groups` 子资源。
- 全套件 **201/201 通过**，无回归（累计新增 28 个单测）。

### 3) Open Questions / Pending Confirmation
- **分支待 push / 开 PR**：切片 1–6 在 `claude/project-integration-phase1`，等管理者确认。
- **`:`→`_` 目录净化约定待 ratify**：已落地为 `member_dir_name()` helper（`agent:codex → agent_codex/`）；bridge 在 Phase 2 查 profile 须复用同一映射。
- **测试策略已定**：Phase 1 是管道层，单测兜底；功能/人工验收推迟到 **Phase 2 之后**合并做一次（首个可观察行为 = 身份注入改变 agent 行为）。
- `last_seen_at` 暂等于 `created_at`；bridge `--project` 连接刷新逻辑留待 Phase 2。

### 4) Next Plan
1. 等管理者确认是否 push 分支 / 开 PR。
2. **Phase 2 身份层**（下一阶段，待管理者点头）：bridge 加 `--project` → 读 `.talk/agents/<净化名>/{IDENTITY,SOUL}.md` → 注入 system prompt（复用 `member_dir_name`）；并入 `project_agents` 表 + `/api/projects/{id}/agents` + `POST /api/projects/{id}/sync`。根治 dogfood 反复出现的身份混乱/汇报体。

### 5) Verification
- 逐片单测全绿；`python -m unittest discover -s tests` → 切片 5 后 199/199、切片 6 后 **201/201**，无回归。
- `python -m cli.talk init` / `add-agent` 实跑生成结构正确；dogfood `.talk/` YAML 可解析、profile 齐全、`memory/` 忽略生效。

### 6) Changed Files（Phase 1 累计）
- 新增 `server/routes/projects.py`、`cli/__init__.py`、`cli/talk.py`、`tests/test_projects.py`、`tests/test_talk_cli.py`、`.talk/`（17 文件）
- 改 `server/models.py`、`server/main.py`、`server/db.py`、`server/routes/groups.py`、`tests/test_groups.py`、`requirements.txt`、`AGENTS.md`
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
