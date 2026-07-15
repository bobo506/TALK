# TALK 定位、使用场景与 Hall 类型

> 文档状态：Design / 定位与场景沉淀（2026-07-15，与项目管理者讨论后更新 Hall 分类与优先级）。
> 关系：承接 `PROJECT_INTEGRATION.md` §1 的"基础设施化"定位，聚焦**使用场景分类 + Hall 类型/RolePack + 通用化方向**；实现层细节见 `PROJECT_INTEGRATION.md` 与各 `MODULE_*.md`。
> 本文不涉及代码改动，作为后续实施方向的合同。

---

## 1. 定位精炼：跨模型委派 + 可见协作

- TALK 是给实际项目使用的**跨模型 Agent 协作基础设施**。任一支持 TALK client / MCP 的交互终端，都能把其他模型 Agent 当作“跨模型子 Agent”来委派工作；终端本身是否原生支持 subagent，不影响这项能力。
- 产品层 Hall 分为两类：
  - **Task Halls**：一项委派任务对应一个独立 Hall，由请求者 A 指派给执行者 B，执行关系为 1 对 1；当前优先完成。
  - **Discussion Halls**：多个业务角色围绕主题讨论、评审和形成共识；已有设计与实现保留，具体产品效果在 Task Hall 跑通后继续。
- TALK 与 **CCB**（`docs/调研/` 中评估的 Agent 协调框架）的关系仍是 **TALK 在功能上覆盖 CCB（TALK ⊇ CCB）**：Task Hall 承接 Mailbox / Callback / Attempt 等可靠委派机制，Discussion Hall 提供额外的可观测、人在环和多角色共享上下文。
- TALK 不替代 Codex / Claude Code 等终端，也不要求把桌面端与 CLI 合并成同一会话。前台终端负责理解总目标、拆分、委派、汇总和验收；TALK 负责持久化任务、路由给目标 Agent 的 runner，并把澄清与结果带回。
- `bridge` / `runner` 是领取并驱动目标模型执行的**基础设施进程**，不是第三种 Agent 角色，也不额外代表一份模型订阅。逻辑身份仍是 TALK 中的 `member_id`；同一成员可有多个交互入口，但同一任务只能被一个 runner 领取执行。

---

## 2. 两条性质轴

| 轴 | 场景 | TALK 相对 CCB 的增量 | 策略 |
|---|---|---|---|
| **Task Hall / 协调类** | 1 单次任务协作、2 任务分配 | 1 对 1 委派、可靠状态、可见澄清与结果回传 | **当前优先**；先跑通跨终端委派闭环 |
| **Discussion Hall / 审议类** | 3 头脑风暴、4 评审 | CCB 没有的多角色共享上下文与人在环审议 | 设计与已有实现保留；Task Hall 后继续 |

---

## 3. 使用场景（4 类 + 1 横切机制）

### 3.1 协调类

**场景 1 · 单次任务协作**
- 流：主 Agent 终端（据人类要求）→ 通过 TALK 创建一个 Task Hall 并指派 B → B 的 runner 领取 → B 有疑问则在该 Hall 提问，否则接受并执行 → B 提交结果 → A 的终端查询 / 等待并获取结果 → A 汇总、验收后继续项目。
- 适合：测试、验证、问题咨询。

**场景 2 · 任务分配**
- 流：主 Agent 在推进总目标时按业务角色拆出若干任务；**每项任务分别创建一个 1 对 1 Task Hall**，并行交给不同 Agent；主 Agent 保留整合与最终验收责任。
- 适合：推进项目进度、按前端 / 后端 / ui 分工完成一个切片。
- Task Hall 的标准主流程：`assigned → clarification_requested（可选）→ accepted → in_progress → submitted → result_collected / completed`。失败、取消、返工与超时是异常分支，实施时另行细化。
- “1 对 1”约束的是任务的请求者与执行者以及写入 / 执行关系；项目所有者或决策 Agent 可以观察、介入和验收，但不因此成为第三个执行参与者。

> **1 与 2 相对 CCB**，本质是把委派、确认、澄清、执行和回调结果做成前端可见的任务线程。底层投递确认 / 回调 / 重试 / 失败分类可借 CCB（`PROJECT_INTEGRATION §9.4`），但状态变化与关键消息必须在 Task Hall 留痕。

### 3.2 审议类（Discussion Halls，后续继续）

**场景 3 · 头脑风暴**
- 流：主持人（**人 或 host agent**）在 Hall 发起主题 → 每个 agent 轮流发表一个想法，每发完一个其他 agent 依次表态（同意 / 反驳 + 理由）→ 全部发表完 → 主持人归纳总结。
- 适合：决策、想法落地、收集创造性思维、开拓方向。
- 形态：**发散**。

**场景 4 · 评审**
- 流：一个 agent 产出物（代码 / 设计 / 文档 / 报告）→ 其他 agent **针对该具体产物**给结构化评审意见 → 作者据此修改。
- 适合：code review、设计评审、文案 / 报告评审。
- 形态：**收敛**（有标的、挑毛病、求改进），与头脑风暴的发散互补。

### 3.3 横切机制 · 升级 / 仲裁
- agent 间分歧谈不拢 → 升级给人裁决。贯穿 1 / 2 / 3 / 4。
- 现状：**已部分实现**（`escalate` stance + bridge `_maybe_escalate_disagreement` 自动 @ 人类）。

---

## 4. Hall 分类 / RolePack

- 产品信息架构固定为 **Task Halls / Discussion Halls** 两类。现有 `groups.type`（`task` / `brainstorm` / `review` / `free`）是实现层模板：`task` 对应 Task Hall；`brainstorm`、`review` 和通用讨论归入 Discussion Hall。
- **Task Hall** 的体验合同是“一任务一 Hall、一请求者一执行者、归属一个项目、状态和结果可追踪”。其存储最终复用 `groups` 还是新增专用 thread 实体，留待实现切片决定，但不得破坏上述合同。
- **Discussion Hall** 的 type / RolePack 继续作为软模板，打包三样：
  1. **协议 / 流程**：自由讨论 / 头脑风暴（轮流 + 表态 + 归纳）/ 评审；
  2. **预期角色清单**：如主持人、参与者、作者、评审人、lead、dev …；
  3. **每个角色的行为规范**：在这个 Hall 类型里该怎么做。
- 复用现有：`business_role`（P3-1 每成员业务角色，自由文本）+ discussion 机制（轮次 / `stance` 含 agree / disagree / optimize）。
- 创建 Hall 选类型 → 自动配角色 + 把"这是个 X 会、你是 Y 角色、流程如此、你该干嘛"注入各 agent 提示。
- 这是 `PROJECT_INTEGRATION §9.4` 登记的 **RolePack** 思路的具体化。

**两条硬原则：**
1. **协议强度按类别区分**：Discussion Hall 的 type 是软预设，不强制每步按机器流程走；Task Hall 的任务生命周期是服务端可校验的状态，不只靠 prompt 自觉。教训仍适用：不要把大段协议字段硬注进 prompt。
2. **数据驱动、用户可自定义**：type / 角色不写死成代码枚举；内置几个领域中立模板，用户可定义自己领域的（接 §6 通用化）。

---

## 5. 连续性 / 记忆 决策

- **不做 server 端记忆系统**（原拟的 COLD / WARM / RESUME 取消）。理由：本场景的 agent 是**带仓库文件权限的 CLI agent**，连续性由两层承载：
  - **项目状态** = 项目自己的 `docs/PROGRESS.md`（project-framework，所有 agent 在仓库里共享读写）；
  - **个人风格 / 搭档 / 边界** = `SOUL.md` / `USER.md`（Phase 2 已注入）。
- **也不注入 `MEMORY.md`**：与上述重叠，无独立使用场景。`project_agents.memory_pointer` 保留备用，暂不消费。
- **何时才需要 server 记忆**（满足任一才重启此方向）：agent 无文件权限（纯 API）/ 记忆需跨项目共享或平台检索 / 需自动摘要与重要性排序。当前都不沾。

---

## 6. 通用化方向 与 受众分层

- **内核领域无关**：Hall / 角色 / 头脑风暴 / 评审 / 任务中转 与"编程"无关，同样适用调研、评估、文案等非编程项目。`business_role` 已是自由文本；"项目"只是一个工作目录，不必是 git 仓库。
- 通用化的主要工作：① type / 角色做成用户可自定义模板（别硬编码编程角色）；② 内置领域中立模板；③ 文档话术去代码中心化。
- **受众分层（一个诚实的代价）**：
  - 现状受众 = **开发者**（CLI agent + bridge + `.talk/` + git + 终端接入）。
  - **远期（暂不做，已标记）**：非技术受众 + 低门槛 Web 接入（纯 Web 创建 Hall / 选类型 / 拉 agent，免终端）。这是一笔实打实的 UX / 打包成本。**待核心场景全跑通后再考虑。**
  - 即"内核通用"很便宜，但"非技术受众可用"另算账，两者不要混。

---

## 7. 与现有实现的接点 / 优先级

**已有（可复用）：**
- 身份注入（Phase 2）、业务角色存储 + 注入（P3-1 / P3-2）、`discussion_sessions` / `turns` + `stance`（含 agree / disagree / optimize）、`escalate` 升级。

**待建（按优先级）：**
1. **Task Hall 闭环** —— 一任务一 Hall、1 对 1 指派、澄清 / 接受 / 执行 / 提交 / 结果获取、项目级黑板聚合。
2. **终端委派接口** —— 通过 TALK MCP / client 提供发现 Agent、创建任务、查询 / 等待、纠偏 / 取消、收集结果的稳定能力；任一终端都可调用。
3. **可靠协调机制** —— 借鉴 CCB 的投递确认、lease、回调、重试与失败分类，避免重复执行和结果丢失。
4. **Discussion Halls** —— 保留已完成的 brainstorm 基础，后续继续真机验收、评审流程与 Web 审议视图。
5. **（远期）非技术受众 + 低门槛 Web 接入**。

> 注：MEMORY 方向已关闭（见 §5）。Phase 3 协作层的实质（业务角色存储 + 注入）已由 P3-1 / P3-2 落地。
> **Task Hall 的详细目标合同见 [`MODULE_tasks.md`](MODULE_tasks.md)；审议协议、信息类型、结束归一模型与已完成切片见 [`DELIBERATION.md`](DELIBERATION.md)。**
