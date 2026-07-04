# Project Progress

## Latest
Updated: 2026-07-04 (Asia/Shanghai) — 分支 `claude/phase3-collab-and-ui`。**D3-2（bridge 接 `decision`）** 由执行 Agent 按黑板工单完成、决策 Agent 复核（单行 `ACTION_STANCES` 改动、护栏未破、`test_cli_bridge` 67 全绿）通过 + 收口提交。D3 三片：D3-1 ✓（数据层）、**D3-2 ✓**（bridge stance）、D3-3（结束归一 + 决策人收口 + 编排 + escalated 下线）。已推 GitHub 到 BUGFIX-1（`6ed5179`）；D3-1/D3-2 本轮提交待推。**下一步**：D3-3（重头片）。Claude = **决策 Agent**。

### 1) Current Progress（分支 `claude/phase3-collab-and-ui`）
- **P3-1 ✓**（`533bc5d`）：群成员 `business_role`/`decision_tier` 存储 + `PUT members` API。
- **P3-2 ✓**（`51da887`）：bridge 注入"你在本群的业务角色"（黑盒待真机）。
- **UI #2 删 Hall 全栈 ✓**（`53846b8`/`5578ac2`/`a54e4d3`）：`DELETE /api/groups/{id}` 级联删 + 前端删除按钮/二次确认；右侧删除已真机验收。
- **UI #3 全局禁用 agent 全栈 ✓**（`4cec246`/`dea5ff9`/`05db723`）：`Member.disabled_at` 软删 + 拒鉴权 + `PATCH`；前端"所有 Agent"列表禁用/启用开关；功能已真机验收。
- **数据清理 ✓**：群 31→1（仅留 `test-run20`）、成员→5（agent `codex`/`pi`/`pi-kimi` + human `bobo`/`qa`）。
- **D1 ✓**（`f20811a`）：新增 `server/hall_types.py` 内置 4 类 Hall 模板（`free`/`task`/`brainstorm`/`review`）；`groups.type` 模型列 + `init_db()` 旧库迁移 + `ix_groups_type`；`POST /api/groups` 支持创建时指定 `type`，默认 `free`，非法值 `422`；`GroupOut` 回显 `type`；新增认证只读 `GET /api/hall-types`。
- **D2 ✓**（`411269f`）：bridge `_build_group_member_context` 按群 `type` 注入"本群类型/流程指引"+ 角色职责（`free` 不注入保零回归；模板取自 server `GET /api/hall-types`、进程级缓存、失败优雅降级）；SDK 新增 `get_hall_types`（async + sync parity）。`test_cli_bridge` 65 测试全绿（5 个 D2 用例 + P3-2 零回归）。
- **@所有人 ✓**（`6e645bb`）：`@所有人`/`@all`（`所有人`精确、`all`大小写不敏感）在群作用域把 `to_ids` 展开为全体群成员（排除发送者），非群发 `@所有人`→`400`；`_extract_leading_mentions` 改三元组 + `_resolve_recipients(sender_id)`；前端 `@` 下拉加"所有人"项 + `@所有人`/`@all` 高亮。`test_messages` 27 全绿 + `node --check` 通过。是 D3 头脑风暴的前置依赖。
- **人设编辑(a) ✓**（`8eaf092`）：`cli/profiles.py` 新增 `resolve_profile_path`（双层路径穿越防御）/`write_profile_file`（读侧不动）；human-only `GET`/`PUT /api/projects/{id}/agents/{member_id:path}/profile` 读写 IDENTITY/SOUL/USER（无 `project_root_path`→400、穿越→400）；business_role 复用 P3-1 `PUT group member`（保留 role/decision_tier）；前端 Hall 成员行"编辑人设"按钮（agent+canManage+project_id 守卫）+ 模态。`test_projects`/`test_profiles` 32 全绿（含穿越/human-only/round-trip 落盘）+ `node --check`。bridge 不变（文件即真相源）。
- **BUGFIX-1 ✓**（`28298bd`）：真机黑盒验收回归修复（仅 `web/app.js`）——① `@` 下拉因输入处理器引用未定义的 `activeGroup` 抛 `ReferenceError`、所有 mention 下拉全废 → 改取 `getActiveGroup()`；② 保存人设后"编辑人设"按钮卡 disabled → 渲染前先清 `agentProfileSaving`；③ `@所有人` 高亮经真机确认本就正常（原现象=测试环境）。`node --check` + 真机 Chrome 复验三条通过。
- **D3-1 ✓**（`afc1eb7`）：审议数据层地基（纯加法·零回归）——`_DISCUSSION_STANCES` 加 `decision`、新增 `_DISCUSSION_END_REASONS`（consensus/deadlock/timeout/manual）；`DiscussionSession.end_reason` 列 + `init_db()` 旧库迁移 + 索引；`DiscussionSessionOut` 回显、`DiscussionSessionUpdate` 可选 `end_reason`（校验）、更新端点按 `model_fields_set` 落值；`_DISCUSSION_STATUSES`/`escalated` 未动。`test_discussions`(9)+`test_cli_bridge`(65) 74 全绿（含 escalated 零回归 + 旧库迁移）。
- **D3-2 ✓（已验证·本轮提交）**：bridge 接 `decision`（纯 plumbing）——`bridges/cli_bridge.py` 仅 `ACTION_STANCES` 加 `decision`（动作解析不再把 `stance=decision` 抹成 `None`）；护栏未破（`NON_SUBSTANTIVE_STANCES`/轮次刹车元组/`infer_*`/prompt/`escalated` 均未动 → `decision` 计入实质轮次、不受 turn limit）。`test_cli_bridge` 67 全绿（+2：decision 解析保留、decision talk_send 轮次耗尽不被 skip vs answer 被 skip）。

### 2) Open Questions / Pending Confirmation
- **✅ A/B/C 真机验收闭环（2026-06-28，黑盒 + BUGFIX-1）**：@所有人 下拉/高亮、UI#3 禁用/启用开关 + 禁用 agent 不可加入、人设编辑弹窗读写/持久化/business_role——均通过。
- **UI #3 "禁用 → 该 key 被 403" 运行时端到端**：黑盒只验了 UI 开关；"禁用后该 agent key 被拒鉴权"未单独跑，低优先。
- **D2 / P3-2 注入行为黑盒待真机**：agent 是否按注入的 Hall `type` 流程指引 / 业务角色实际行动——**本轮主动不验**（需 D3 头脑风暴协议把"注入的流程"变成可运行机制后，连同结构化流程一起真机验）。

### 3) Next Plan
- **MEMORY 方向已关闭**：连续性由项目 `PROGRESS.md` + 身份注入承载（见 `spec/POSITIONING.md §5`）。
- **新方向（已沉淀 `spec/POSITIONING.md`）**：优先做**审议类协议**——头脑风暴（轮流 + 表态 + 归纳）、评审（针对产物的收敛式批评），由 **Hall 类型 / RolePack** 框架承载；协调类（1/2）借 CCB；非技术受众 / Web 低门槛接入列为远期。
- **设计已定稿**：审议协议、信息类型（stance 终集：去 `idea`、`synthesis`→`decision`、`closure` 降级）、结束归一模型（单一出口 `handoff` → 决策人 = `decision_tier`/human，4 种 `end_reason`）、Hall 类型/RolePack、@所有人、人设网页编辑(a)、切片 D1–D5 —— 见 [`spec/DELIBERATION.md`](spec/DELIBERATION.md)。
- **下一步**：审议主线 D3 拆 3 片——**D3-1 ✓（数据层）**、**D3-2 ✓（bridge 接 `decision`）**；下一片 **D3-3（重头：结束归一 + 决策人 `decision` 收口 + 轻编排 + prompt 指引 + `escalated`→`resolved+deadlock` 迁移下线，server+bridge）**。之后 D4（评审）/ D5（Web 审议视图）。
  - 注意：`DELIBERATION §7` 的 stance 迁移点（去 `idea`/`synthesis`）与现状不符——现状 `_DISCUSSION_STANCES` 早已无 `idea`/`synthesis`，D3 对 stance 只是加 `decision`。
- **候选（未排期）**：`claude_bridge` —— 让 Claude Code/Codex 这类 agent 框架成为 TALK 一等公民 worker（现仅 codex/pi 特化 + 通用 cli_bridge）。管理者 2026-06-28 确认架构理解（TALK 背后真正干活的是 agent 框架），此项作为方向候选、暂不排期。

### 4) Verification
- **决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_hall_types tests.test_groups tests.test_member_disable -v` → `Ran 23 tests ... OK`（确认执行 Agent 自测结论）。
- `python -m pytest ...`：全局 Python 与 `.venv` 均无 `pytest`，未运行 pytest。
- `.venv\Scripts\python.exe -m unittest tests.test_groups -v`：16/16 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_hall_types -v`：3/3 通过（含旧 schema 迁移实测）。
- `.venv\Scripts\python.exe -m unittest tests.test_member_disable -v`：4/4 通过。
- 验证噪声：测试期间 Windows 日志轮转尝试重命名 `logs/talk.log` 时因文件被占用报 `PermissionError`，不影响测试退出码；需后续另片处理 logging 轮转健壮性时再看。
- 唯一偶发：`test_websocket` presence 时序仅在机器过载（曾跑 464s/499s）时失败，隔离单跑 10/10 通过，与本轮改动无关。
- D1 为纯 server 切片，未做前端/Browser 验证。
- **D2 决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge -v` → `Ran 65 tests ... OK`（含 5 个 D2 用例 + P3-2 零回归）；D2 为 bridge/SDK 切片，注入行为黑盒待真机。
- **@所有人 决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_messages -v` → `Ran 27 tests ... OK`（4 新用例 + 回归）；`node --check web/app.js` 通过；前端真机点选未做。
- **人设编辑(a) 决策 Agent 独立复跑（2026-06-25）**：`.venv\Scripts\python.exe -m unittest tests.test_projects tests.test_profiles -v` → `Ran 32 tests ... OK`（含路径穿越→400+断言外部无文件、human-only 403、三件套 round-trip 落盘）；`node --check web/app.js` 通过；前端真机点选未做。
- **真机黑盒验收（2026-06-28）**：无项目经验 agent 当测试者 + 决策 Agent 复核。fixture 经 `scripts/seed_acceptance.py`（临时项目根 `.tmp-acceptance`，建 brainstorm Hall「验收测试群」+ business_role）。A=@所有人 ✓（修 BUGFIX-1 后下拉/高亮均正常）、B=禁用开关 ✓、C=编辑人设 ✓。无需接 bridge。
- **BUGFIX-1 决策 Agent 复核（2026-06-28）**：`web/app.js` diff 仅 2 处确定性修复（与根因吻合：`getActiveGroup()` 取值、保存路径提前清 `agentProfileSaving`）+ `node --check` 通过 + 执行 Agent 真机 Chrome 三条复验；前端运行时 bug 无单测覆盖，以 diff 复核 + 真机为准。
- **D3-1 决策 Agent 独立复跑（2026-07-04）**：`.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` → `Ran 74 tests ... OK`（含 `decision` stance、`end_reason` PATCH/校验 422、status-only 保留 end_reason、`escalated` 零回归、旧库迁移补列）；diff 逐条吻合、纯加法未动 `_DISCUSSION_STATUSES`。
- **D3-2 决策 Agent 复核（2026-07-04）**：`git diff bridges/cli_bridge.py` 仅 1 行（`ACTION_STANCES` 加 `decision`）、护栏三处（NON_SUBSTANTIVE/轮次元组/infer）未动；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 67 tests ... OK`（+2 D3-2 用例：decision 解析保留、decision talk_send 轮次耗尽不被 skip）。

> Phase 1 / Phase 2 / Web UI #1 等已合入 `main` 的更早阶段记录，见 `docs/PROGRESS_HISTORY.md`。

---

## 未来方向

来自三份评估报告（`docs/调研/` 系列：pi-vs-claude-code、ClawSwarm、OpenClaw Control Center、Multica）与 `docs/spec/PROJECT_INTEGRATION.md` 设计草案：

- **TALK 基础设施化**：从"独立产品"重新定位为"给其他项目使用的多 Agent 协作基础设施"
- **项目接入机制**：`talk init` + `.talk/` 目录约定 + 项目级 server API
- **Agent 元数据双层架构**：
  - 协作层：决策分级 + 业务角色（P3-1/P3-2 已落地存储与注入）
  - 身份层（借鉴 ClawSwarm）：IDENTITY / SOUL / USER / MEMORY 四件套，按项目分配
- **平台能力补全**：
  - 结构化输出块 `<talk-structured>`（OpenClaw）—— 治本"双通道写作灾难"
  - 意图分类（OpenClaw）：greeting / chat / task，避免寒暄被当任务执行
  - Agent 自动接力对话三层防护（ClawSwarm）：window / soft / hard limit
  - 消息投递追踪 `message_dispatches`（ClawSwarm / Multica）—— 可观测性
  - 零信任安全模型（Multica）：agent vs human 隔离、凭证不可自读、操作审计
  - COLD / WARM / RESUME 上下文读取（Multica）—— MEMORY 实施方向
  - 任务失败 14 类精细分类与差异化重试（Multica）
- **四阶段落地路线**（详见 PROJECT_INTEGRATION.md §12）：
  1. 基础接入（`talk init` + `projects` 表）—— ✅ 已合入 main
  2. 身份层（IDENTITY/SOUL 文件 + bridge profile 加载）—— ✅ 已合入 main
  3. 协作层完整化（业务角色注入 + MEMORY 系统）—— 进行中（P3-1/P3-2 ✓，P3-3 MEMORY 待做）
  4. 平台能力补全（结构化块 + 意图分类 + 投递追踪 + 三层防护）—— 未启动

完整设计请参考 `docs/spec/PROJECT_INTEGRATION.md`（15 节，~580 行）。

---

## 当前已知技术债

- **双通道写作灾难残留**：agent 在调 talk_send 的同时仍要写 visible reply，有时 visible reply 退化为"凑数"。根治方案在 PROJECT_INTEGRATION §9.3 结构化输出块（Phase 4）。
- **`--no-extensions` 是粗粒度规避**：禁用所有 pi 自动发现扩展（含 plan-mode bug 源）。等 upstream `earendil-works/pi#5327` 修复后可去掉此 flag。
- **Phase 2/3 注入行为黑盒补测**：身份注入（Phase 2）已真机验；业务角色注入（P3-2）黑盒待真机。
- **遗留小毛病（管理者确认"以后再修"）**：早期 discussion 的双重收口语、个别 session 停在 `active` 未标 `resolved`——无害，纯观感。

---

## Recent Notes
- 🧩 **2026-06-20 Phase 3 + UI #2/#3**：群成员业务角色存储/注入、删 Hall、全局禁用 agent 全栈落地；清理测试数据（群 31→1、成员→5）。详见 `PROGRESS_HISTORY.md`。
- 🎯 **2026-06-07 5.7+ 对话质量收敛**：身份锚紧凑内嵌、反元叙述系统层、废弃 discussion_context 三招收住。
- 📐 **2026-06-07 PROJECT_INTEGRATION.md 立项**：TALK 重校准为"基础设施层"，规划 `.talk/` 约定 + 双层 Agent 元数据 + 四阶段路线。
- 🎉 **2026-06-02 5.x agent-to-agent 通信主线 SHIP**：方案 D（`discussion_turns` 账本）、Prompt 三层架构、talk_send function-calling 三条主线落地。
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
