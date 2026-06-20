# Project Progress

## Latest
Updated: 2026-06-20 (Asia/Shanghai) — Phase 1+2 已合入 `main`（PR #1 `6e8fcec`）；新分支 `claude/phase3-collab-and-ui`（已 push），本轮连做 P3-1（群成员角色存储）+ P3-2（bridge 注入业务角色）+ UI #2 删 Hall（全栈）；groups 测试 14/14。UI #2 浏览器点选待管理者真机验。下一片 = UI #3 全局禁用 agent。Claude=决策 Agent（管理者授权自主开发）

### 0) Phase 3 协作层 + Web UI #2/#3（当前分支 `claude/phase3-collab-and-ui`，进行中）

- **Phase 1+2 已合入 `main`**：PR #1（merge commit `6e8fcec`，2026-06-20 管理者 merge）。本分支从 `main` 新开，承载 Phase 3（业务角色注入 + MEMORY）与 Web UI #2（删 Hall）/ #3（全局禁用 agent）。
- **切片 P3-1 完成（群成员业务角色/决策分级存储）**：`GroupMember` 加 `business_role`（自由文本）/`decision_tier`（`decision`|`execution`）两列；`PUT /api/groups/{id}/members/{member_id}` 接收并全量替换、`GroupOut.members` 返回；`GroupMemberUpdate` 校验 decision_tier 枚举（大小写归一）；`db.py` 加幂等列迁移 + 索引。+3 单测。对齐 `PROJECT_INTEGRATION.md` §5.2 的 groups.yaml 角色模型。
- **切片 P3-2 完成（bridge 注入业务角色）**：`bridges/cli_bridge._build_group_member_context` 在群成员清单后追加"你在本群的业务角色：{business_role}。"（business_role 取自 P3-1 群成员数据中当前 member 的条目）；`decision_tier` 维持由 bridge 启动参数 `--decision-tier` 注入（`_decision_tier_line`），避免双源冲突。纯追加，无 business_role 时字节不变。+2 单测。**行为黑盒验证待人工**（同 Phase 2 注入，需真机 pi/codex 在群里观察是否按业务角色行动）。
- **管理者已决策（2026-06-20）**：① UI #2 删 Hall = **连带删除消息**（级联清成员关系 + 该群所有消息）；② MEMORY = **完整 server 端 COLD/WARM/RESUME**——范围扩大为独立子阶段，排到本分支最后做。
- **切片 UI #2 删 Hall 完成（全栈）**：
  - 后端（`53846b8`）：`DELETE /api/groups/{id}`，仅人类；子表先删后删群（group_members / 该群 messages / discussion_sessions / discussion_turns），顺序保证无论 SQLite FK 是否启用都正确（运行时未开 FK）。+3 单测。
  - 前端：群成员面板加红色"删除此 Hall"按钮（`renderGroupMembersPanel` 按 `canManage` 显隐，仅人类）→ `window.confirm` 二次确认（含级联删除警告）→ `DELETE` → 从本地 `groups` 移除、若为当前群则 `setActiveGroup(null)` 重置。新增 `.room-danger-btn` 样式；资源版本号 `20260620-hall-delete`。
  - 验证：静态（JS 语法 / CSS 配平 / ID 一致 / 逻辑复核）通过；运行中 server 实测确认已服务新前端文件。**浏览器点选端到端待管理者**——运行中 server 为旧 Python 代码（无 `--reload`，缺 DELETE 端点），未停其进程，需重启后真机验。
- **本分支切片路线**：P3-1 存储 ✓ → P3-2 注入业务角色 ✓ → UI #2 删 Hall（全栈）✓ → **UI #3 全局禁用 agent（下一片：软删 `disabled_at` + `PATCH/DELETE /api/members/{id}` + 鉴权拒绝 + 前端入口）** → P3-3 MEMORY（完整 server 端，大，独立子阶段，最后做）。

### Phase 2（已合入 main · PR #1）

- **切片 10 完成（`talk sync`，`882b70c`，已合入 main）**：CLI 子命令 `talk sync` 扫描本地 `.talk/agents/` → `POST /api/projects/{id}/sync`，把 profile 路径索引推到 server，Phase 2 从"server 端完整"收口成"本地→server 索引"完整闭环。新增 `cli/profiles.member_id_from_dir_name`（`member_dir_name` 逆映射）+ `cli/talk.scan_agents`/`sync_project`/`cmd_sync`。+11 单测，全套件 **237/237**。真实 dogfood `.talk/agents/` 验证逆出 3 个 agent 正确。
- **切片 7 完成**（`ffa80b2`）：`cli/profiles.py` profile 加载器（纯函数地基）+ 7 单测。
- **注入策略 = B 方案（系统层）**：人设作"背景底色"进 agent 系统层，不混进消息流（§5.4）。
- **切片 8a 完成**（`fc15aa6`）：`compose_system_prompt(base, profile)` 纯函数（profile 作背景 + "别复述"框定；空 profile→base 原样）。
- **切片 8b 完成**（`1c17304`）：pi bridge `--project` → 注入 `--system-prompt`；`resolve_pi_command` 统一执行档 + 注入，严格 opt-in。**黑盒修复真 bug**：命令系统提示 `repr`→`shlex.quote`。
- **切片 8c 完成**（`820aee8`）：codex bridge `--project` → 注入 `-c base_instructions=<json>`；`resolve_codex_command` 同构 pi。codex 命令本就 json+shlex.quote 安全，无 pi 那个 repr bug。
- **现状**：pi/codex 两个 runtime 的身份层注入都打通，严格 opt-in（无 `--project` 字节一致）。单测全绿（codex 18/18、pi 13/13）；真机黑盒两者均确认 shlex 往返 + profile 真注入。
- **人工验收（2026-06-19，已带 `--project` 真实跑 `test-run20` / `group:843d8433bae1`）**：
  - codex 8c：先撞外部坑——codex 全局 `~/.codex/config.toml` 的 `service_tier="default"` 在 `codex-cli 0.130.0-alpha.5` 非法，codex exec 启动即退（与注入无关，黑盒对照确认；经黑板 `agent-docs/BLACKBOARD.md` 与 codex 协作改配置后恢复）。恢复后 codex 招呼自然、身份正确（自报 codex、点到 pi/qa），✅ 注入行为符合预期。
  - pi 8b：**先发现真问题再修复**——`@agent:pi` 只回 bridge 兜底句"我是 pi，已切换为中文回复…"。逐步黑盒定位（与 8b 注入/plan-mode/工具路由均无关）：**pi 0.79.8 经 Windows `pi.CMD` shim 时，`--system-prompt` 含换行就被 cmd.exe 截断 → pi 完全不产出 → bridge 中文兜底**。修复：`pi_bridge._single_line()` 把系统提示（含注入 profile）压成一行（commit `5b57042`）。**Hall 复验通过（2026-06-20）**：`@agent:pi 帮我问 codex 下午2点开会有没有空` → pi 听懂、转达 codex、codex 确认参会、pi 把结果回报给 qa（msg #2368–2373），全程真智能回复、带人设 emoji。pi 注入正式生效。
  - **决策（管理者）**：agent-to-agent 对"软邀请"不强行续聊、完成交办即回报人类（"打招呼就收"）= **可接受，维持现状，不动回合/收口逻辑**。
- **切片 9 完成**（`6d2bc47`）：server `project_agents` 表 + `GET /api/projects/{id}/agents` + `POST /api/projects/{id}/sync`（full-replace，镜像本地 `.talk/agents/`；仅人类；刷新 last_seen_at）。+6 单测，全套件 **226/226**。**Phase 2 server 端到此完整**（身份注入 + profile 路径索引/同步）。
- **CCB 调研已登记**（`b16ffdd`）：`PROJECT_INTEGRATION.md` §9.4 + Phase2/4 路线注入 CCB 借鉴方向（Mailbox/Callback/Attempt/RolePack-skills），只记录不写代码。
- **遗留小毛病（待处理，不阻断；管理者已确认"以后再修"）**：① codex"撤回+重发"招呼导致建了两个 discussion session（#84/#85）、pi 回了两次；② 早期两个 session 停在 `active` 未标 `resolved`（疑似小 bug；注：session#86 任务流已正常 resolved）；③ **双重收口**：任务做完、结果已回报人类后，两个 agent 仍各甩一句 `CLOSURE_LINES` 收口语（如 codex"嗯，先这样" + pi"那先聊到这儿"，msg #2374/#2375）——无害不死循环，纯观感，管理者确认保持现状、以后再收敛。
- **下一步候选**：① CLI `talk sync`（读本地 `.talk/agents/` 调 `/sync`，把 Phase 2 闭环到"本地→server 索引"）；② Phase 3 协作层（业务角色注入 + MEMORY）；③ 清两个 discussion 小毛病；④ UI #2/#3（删 Hall / 禁用 agent）。

> 注：全套件偶发的 `test_websocket` presence 时序测试失败仅在机器过载（曾跑 499s）时出现，隔离单跑稳定通过，与 Phase 2 改动无关。

### Web UI 侧支（测试中发现）
- **#1 新建 Hall 改弹窗 —— 已改并经管理者确认**：原"点 ＋"是在左侧 Hall 列表底部内联展开表单；改为居中模态弹窗（`#group-create-overlay` 遮罩 + `.modal-card`），字段：名称必填 / ID 可选 / 描述可选；**初始成员从"全员勾选墙"改为下拉添加 + 可删标签 chips**（解决 agent 多时卡片被撑满屏、像跳整页的问题），chips 加了柔和蓝底 + 拉开间距；关闭方式：取消 / × / 点遮罩 / ESC。纯前端，后端 `POST /api/groups` 逻辑未动。改文件：`web/index.html`、`web/style.css`、`web/app.js`（资源版本号 `20260619-hall-modal-2`）。验证：JS 语法 + CSS 花括号 + HTML/JS ID 一致 + 运行中 server 字节校验 + 管理者浏览器实看均通过。**已提交**（`1d3cdcf`，在本分支 `claude/project-integration-phase1`）。
- **#2 删除 Hall（待处理）**：当前前端无删除按钮、后端无 `DELETE /api/groups/{id}`。需后端删除 API（仅人类、级联清理成员关系）+ 前端入口 + 二次确认弹窗。全栈一片。
- **#3 全局移除/禁用 agent（待处理）**：当前只有"从 Hall 移除成员"（`DELETE /api/groups/{id}/members/{id}`）；缺"全局禁用/移除 agent 成员"。需 `members` 加禁用字段 + `PATCH/DELETE /api/members/{id}`（软删除，保留 `messages.from_id` 归属）+ 前端入口。最大一片，涉及数据模型。

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
