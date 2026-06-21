# 审议协议、信息类型与 Hall 类型 — 设计 + 切片方案

> 状态：Design（2026-06-20 与项目管理者多轮讨论定稿）。承接 [`POSITIONING.md`](POSITIONING.md)（定位与 4 类场景）。
> 覆盖：信息类型（discussion stance 终集）、结束归一模型、决策人、Hall 类型 / RolePack、@所有人、人设网页编辑、切片方案 D1–D5。
> 命名为草案，实现时可微调。

---

## 1. 信息类型（discussion 标签三层）

- **第 1 层 `turn_kind`（结构）**：`demand`（发起，推进 round，驱动防失控刹车）/ `reply`（回应）。
- **第 2 层 `stance`（语义）**：见下。
- **第 3 层 `action`（bridge 机制）**：`send_message` / `mark_stance` / …，是"怎么发"，不在本设计范围。

**`stance` 终集：**

| 类别 | stance | 含义 |
|---|---|---|
| 内容 | `question` | 提问 / 求助；**头脑风暴的主题也用它** |
| | `answer` | 带内容回答；**头脑风暴里每个"想法"= 回答主题，用它**（不引入 `idea`） |
| 表态 | `agree` | 同意 |
| | `disagree` | 反对 + 理由 |
| | `optimize` | 改进 / 补充（yes-and） |
| 触发信号 | `escalate` | **僵局断路器**：参与者主动请求移交决策人（见 §2）。这是**唯一由参与者发出的 handoff 触发 stance**——只给失败模式留逃生口 |
| 决策人产出 | `decision` | **定论**（原 `synthesis` 改名；覆盖"归纳"与"裁决"） |
| 社交（降级、不计实质轮次） | `greeting` | 打招呼 |
| | `closure` | 纯社交收尾，**不承载"结束"语义** |

变化：**去掉 `idea`；`synthesis` → `decision`；`closure` 降级为纯社交。**

---

## 2. 结束归一模型（单一出口 → 决策人）

- **决策人** = 群里 `decision_tier=decision` 的成员 或 `human`（**主持人 = 裁决人，同一主体**；复用 P3-1 的 decision_tier）。
- **单一出口 `handoff`（= 讨论中说的 X）**："讨论阶段结束 → 移交决策人"，由 `status` 承载（是**状态转移**，不是 stance）。
- **4 种 reason 触发 handoff：**
  - `consensus` 谈出结论
  - `deadlock` 谈不拢（= `escalate` 信号，或自动检测到连续 `disagree`）
  - `timeout` 聊太久（`demand` 轮到上限）
  - `manual` 人工中止（人发"别聊了"指令）
- **决策人收到后产出 1 条 `decision`（定论）** → `status=resolved`；决策人也可说"继续" → 回 `active`。
- **只有 `deadlock` 有参与者触发 stance（`escalate`）；`consensus` / `timeout` / `manual` 没有专门 stance：**
  - `consensus`（顺利收敛）：**决策人直接产出 `decision`（带 `end_reason=consensus`）收口**，不需要参与者打标——这条 `decision` 本身就标记"达成共识、结论在此"。
  - `timeout`：系统刹车自动触发；`manual`：人发指令触发。
  - 设计原则:**只给失败模式（僵局）留一个参与者断路器 `escalate`；成功路径靠决策人 `decision` 收口，不设单独的"达成共识"标签**（给出错打标，不给成功打标）。

**生命周期：** `active` →（任一 reason）**handoff 移交决策人** → 决策人 `decision` → `resolved`（或回 `active`）。

**`status` 集合建议：** `active` / `resolved` / `canceled`；**结束原因单独记 `end_reason`**（consensus / deadlock / timeout / manual）。旧值 `escalated` 迁移为 `resolved` + `end_reason=deadlock`。

> 要点：**第 1 层只管结构 / 刹车（demand 轮），第 2 层只管语义，"是否结束"统一由 `status` + handoff 承载。** demand 轮上限只是"防失控刹车"，触发的是 `timeout` reason，催决策人收口，**不等于"谈出结论"**。

---

## 3. Hall 类型 / RolePack

- **`groups.type`**：先 4 个 —— `free` / `task` / `brainstorm` / `review`。
- **type → 模板** `{ protocol_guidance, roles:[{role, norm}] }`：server 内置；**软预设**（注入流程"指引"，非硬状态机——5.x 硬注协议字段压垮信噪比的教训）；**数据驱动、用户可自定义**（先内置领域中立模板，后续 `.talk/` 覆盖）。
- 创建 Hall 选 type → 可预置成员 `business_role` + bridge 注入"这是 X 会、你是 Y 角色、流程如此、你该干嘛"。
- 这是 `PROJECT_INTEGRATION §9.4` 的 RolePack 思路落地。

---

## 4. @所有人

- mention 解析支持 `所有人` / `all` → `to_ids = 全体群成员`，每个 agent 被触发。
- **被 @所有人 时直接给实质内容（想法 / 评审意见），不回"收到"**（写进协议指引）——避免"双重收口"那类噪音。
- 用于：头脑风暴开场、评审征求意见、决策人喊话。

---

## 5. 人设网页编辑（方案 a）

- **网页编辑的是项目里的 `.talk/agents/<id>/{IDENTITY,SOUL,USER}.md` 文件**：server 加读写端点（用 `projects.project_root_path` + `project_agents` 的相对路径定位文件）；**bridge 不变**（仍读文件，文件是唯一真相源，可进 git）。
- 前提：项目文件在 server 可访问的机器上（家庭 LAN 一般同机，成立）。
- 顺带：**业务角色 / 职责（`business_role`）的网页编辑也补上**（DB，顺 P3-1，在 Hall 成员面板 / agent 管理页）。

---

## 6. 切片方案

| 切片 | 内容 | 层 |
|---|---|---|
| **D1** | Hall `type` + 模板地基：`groups.type` + 迁移、内置模板注册表、`GET /api/hall-types`、`create_group` 接收 `type` | server |
| **D2** | bridge 注入 `type` + 角色规范（扩展 P3-2 的 `_build_group_member_context`） | bridge |
| **@所有人** | mention 解析支持"所有人" + 前端 `@` 下拉项（头脑风暴前置依赖） | server + 前端 |
| **人设编辑(a)** | server 读写 `.talk/*.md` 端点 + 前端编辑页（IDENTITY/SOUL/USER + business_role） | server + 前端 |
| **D3** | 头脑风暴协议：stance 终集落地（+`decision`、`escalate` 信号、结束归一 + `end_reason`）、轮流 + 表态约定、决策人 `decision` 收口；轻编排（决策人驱动） | server + bridge |
| **D4** | 评审流程：review session（标的产物 / 作者 / 评审人）+ `optimize`/`disagree` 批评 + 修订轮 + `decision` 收口 | server + bridge |
| **D5（可选）** | Web UI：Hall type 选择 + 审议视图（轮次 / 表态 / 定论） | 前端 |

**建议顺序：** D1 → D2 →（@所有人）→（人设编辑）→ D3 → D4 →（D5）。
（人设编辑管理者要求优先，可提到 D2 之后、D3 之前，或与 D1/D2 并行。）

---

## 7. 与现有实现的差异 / 迁移点

- **stance**：新增 `decision`（=原 `synthesis`）、去 `idea`、`closure` 降级 → 改 `_DISCUSSION_STANCES`、模型校验、bridge `ACTION_STANCES` / `NON_SUBSTANTIVE_STANCES` / `infer_*`。
- **status / 结束**：引入 `end_reason`；`escalated` 旧值迁移为 `resolved + deadlock`；`closure` 不再当结束。
- **兼容**：现有讨论流程是任务式（requester/assignee、demand/reply、`_maybe_escalate_disagreement`），改动须保证不回归（沿用单测兜底）。
- **复用**：`discussion_sessions`/`turns`、`business_role`（P3-1）、注入（P3-2）、`decision_tier`（决策人）、`escalate` 升级机制。

> 关联：定位与场景见 `POSITIONING.md`；接入与基础设施见 `PROJECT_INTEGRATION.md`；讨论账本现状见 `MODULE_discussions.md`。
