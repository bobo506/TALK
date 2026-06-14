# Project Progress

## Latest
Updated: 2026-06-11 (Asia/Shanghai) — Web UI 精修支线收尾

### 1) Current Agent Role
- 角色来源：`AGENTS.md`；本轮启动角色：Claude = 执行 Agent（PROGRESS 未单独声明 Claude，按兜底规则）。
- 当前 Codex 角色：决策 Agent。
- 当前分支：`main`（仓库现仅此一条分支，本地 + 远程同步）；全部已完成工作（5.x agent 通信主线 + Web UI 重设计/精修）均在 `main` 并已推送 GitHub。
- 历史特性分支 `codex/web-ui-feature`、`codex/local-lab-codex-bridge`、`codex/scenario-1-scope-fix` 内容已全部并入 `main`，本地 + 远程均已删除。

### 2) Current Progress
- 前端支线已收尾：在浅色三栏重设计基础上，按管理者多轮反馈完成一整轮视觉/布局精修（纯 `web/` 改动，未动后端 / API / 数据模型）。
- 字体整体收小并分级（control 11 / body 13 / section 14 / title 16），全站字重从 750–850 降为 750 / 600 / 450 / 400 四级，消除"满屏粗体"。
- 三栏收窄为 `196px / 1fr / 252px`，中间消息区约占 2/3；顶部查询区改为标题右侧同行（修掉"搜索"被压成竖排）；消息区去掉 160px 死留白。
- 清爽化：统一三栏底色、柔化边框、右侧卡片去投影、加大留白；顶部输入框改为悬浮大圆角卡片。
- 右侧成员栏重排（修重叠 bug）：成员信息去冗余为「短名 + 类型标签」；去掉角色下拉框（管理控件、非固定类型）；「所有成员」列表撑满到底部、内部滚动。
- group id 移到中间 Hall 标题右侧小标签；删右侧「· N 位成员 · 全部」副标题与「✎ 点击名称可重命名」提示。
- 顶部标题栏精简：删假窗口控件 `- □ ×`、「Hall 协作」、`human:qa`；标题栏高度 52→42px。
- 清理无用代码 `updateGroupMemberRole()`；静态资源版本号 `20260611-ui-refine`。

### 3) Open Questions / Pending Confirmation
- **成员软删除（决策已定，待实现）**：将来做"agent 管理功能"时采用软删除＝标记禁用，保留历史消息归属、UI 隐藏；不做硬删除（避免破坏 `messages.from_id` 等外键）。需 `members` 禁用字段 + `PATCH/DELETE /api/members/{id}` + 前端入口，属全栈改动，本轮不做。
- 左侧"删除 Hall"入口仍为视觉态，后端 Group 删除 API 与二次确认弹窗待补。
- 角色变更入口已随下拉框移除；如需在网页改成员角色，将来由 agent 管理功能统一提供。

### 4) Next Plan
1. 前端支线已收尾，等项目管理者最终验收。
2. 下一阶段候选：agent 管理功能（含成员软删除）、Hall 删除真实 API + 二次确认、或回到后端主线（PROJECT_INTEGRATION 路线）。

### 5) Verification
- `node --check web\app.js`：通过；CSS 花括号 194/194 平衡；`git diff --check`：通过（仅 LF/CRLF 提示）。
- Browser 实测（精修早期几轮）：以 `human:qa` 登录进入 `test-run19 Hall`，`preview_inspect` 核验计算样式——三栏 `240/948/252`（中栏 66%）、body 14px/400、标题 17px/750、composer 圆角浮卡、成员行无重叠均符合预期。
- 后续几轮以"服务端返回字节校验 + CSS 花括号 + 管理者浏览器确认"验证；预览 MCP 截图因 SSE 长连接挂起未用。

### 6) Changed Files
- `web/index.html`
- `web/style.css`
- `web/app.js`
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
