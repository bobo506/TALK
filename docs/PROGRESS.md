# Project Progress

## Latest
Updated: 2026-06-20 (Asia/Shanghai) — 分支 `claude/phase3-collab-and-ui`（基于已合入 `main` 的 Phase 1+2，PR #1；已 push）。本轮：Phase 3 前两片（P3-1/P3-2）+ Web UI #2/#3 全栈 + 测试数据清理 + **审议方向设计定稿**（`spec/POSITIONING.md` 定位/4 类场景；`spec/DELIBERATION.md` 信息类型终集/结束归一/Hall 类型/@所有人/人设编辑(a)/切片 D1–D5；MEMORY 已关闭；结束机制确认走"单一出口 handoff + 仅 deadlock 有参与者断路器 escalate"）。**下一步 = 从 D1 开写**（新窗口说"继续项目"恢复）。Claude = **决策 Agent**。完整记录见 `docs/PROGRESS_HISTORY.md`。

### 1) Current Progress（分支 `claude/phase3-collab-and-ui`）
- **P3-1 ✓**（`533bc5d`）：群成员 `business_role`/`decision_tier` 存储 + `PUT members` API。
- **P3-2 ✓**（`51da887`）：bridge 注入"你在本群的业务角色"（黑盒待真机）。
- **UI #2 删 Hall 全栈 ✓**（`53846b8`/`5578ac2`/`a54e4d3`）：`DELETE /api/groups/{id}` 级联删 + 前端删除按钮/二次确认；右侧删除已真机验收。
- **UI #3 全局禁用 agent 全栈 ✓**（`4cec246`/`dea5ff9`/`05db723`）：`Member.disabled_at` 软删 + 拒鉴权 + `PATCH`；前端"所有 Agent"列表禁用/启用开关；功能已真机验收。
- **数据清理 ✓**：群 31→1（仅留 `test-run20`）、成员→5（agent `codex`/`pi`/`pi-kimi` + human `bobo`/`qa`）。

### 2) Open Questions / Pending Confirmation
- **P3-2 业务角色注入黑盒待真机**：pi/codex 在群里是否按业务角色行动（同 Phase 2 注入，攒一次真机黑盒）。
- **UI #3 禁用开关端到端待真机**：功能已验，但运行中 server 需重启加载 UI #3 后端 `PATCH` 端点后才能跑通"禁用 → 该 agent key 被 403"。

### 3) Next Plan
- **MEMORY 方向已关闭**：连续性由项目 `PROGRESS.md` + 身份注入承载（见 `spec/POSITIONING.md §5`）。
- **新方向（已沉淀 `spec/POSITIONING.md`）**：优先做**审议类协议**——头脑风暴（轮流 + 表态 + 归纳）、评审（针对产物的收敛式批评），由 **Hall 类型 / RolePack** 框架承载；协调类（1/2）借 CCB；非技术受众 / Web 低门槛接入列为远期。
- **设计已定稿**：审议协议、信息类型（stance 终集：去 `idea`、`synthesis`→`decision`、`closure` 降级）、结束归一模型（单一出口 `handoff` → 决策人 = `decision_tier`/human，4 种 `end_reason`）、Hall 类型/RolePack、@所有人、人设网页编辑(a)、切片 D1–D5 —— 见 [`spec/DELIBERATION.md`](spec/DELIBERATION.md)。
- **下一步**：从 **D1（Hall `type` + 模板地基，纯 server）** 开写（在本分支 `claude/phase3-collab-and-ui`）。

### 4) Verification
- 子集全绿：`groups` 14/14、`member_disable` 4、`cli_bridge` 60、鉴权子集（messages/discussions/instances/tasks/files/projects）69。
- 唯一偶发：`test_websocket` presence 时序仅在机器过载（曾跑 464s/499s）时失败，隔离单跑 10/10 通过，与本轮改动无关。
- 前端：JS 语法 / CSS 配平 / ID 一致 / 逻辑复核通过 + 运行中 server 实测确认服务新文件。

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
