# MODULE: Agent Tasks

> 所属项目：TALK
> 状态：任务队列与显式触发调度 API 第一版已落地；Task Hall 目标态已确认，尚未实现

## 目标

提供一个服务端任务队列，让人类或其它已认证成员可以把一段工作请求记录为 task，由目标 `agent:*` 成员的 bridge 实例领取、执行并回写最终状态。当前阶段只做任务记录和分派，不由 TALK 自动启动 bridge 进程。

## 负责范围

- 数据模型：`server/models.py` 中的 `AgentTask`、`AgentTaskSchedule`
- API 路由：`server/routes/tasks.py`
- 数据库初始化：`server/db.py`
- SDK 方法：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`

## 当前实现

> 本节只描述已经落地的行为。后文“Task Hall 目标态”是下一阶段合同，不应被理解为现有 API 已具备对应字段或状态。

### 数据模型

`agent_tasks` 表记录任务生命周期：

- `id`：自增任务 id
- `schedule_id`：可选来源 schedule id；普通即时任务为空
- `target_member_id`：目标 Agent 成员，例如 `agent:codex`
- `created_by`：任务创建者
- `content`：任务正文
- `title`：可选短标题
- `status`：`queued`、`running`、`succeeded`、`failed`、`canceled`
- `claimed_by`：领取任务的 Agent
- `instance_id`：处理任务的 Agent 实例
- `result_message_id`：任务完成后对应的 TALK 消息，可为空
- `last_error`：失败原因摘要
- `created_at` / `updated_at` / `claimed_at` / `finished_at`

`agent_task_schedules` 表记录延迟或周期性任务计划：

- `id`：自增 schedule id
- `target_member_id`：目标 Agent 成员
- `created_by`：创建者
- `content` / `title`：将来物化为 task 的任务正文与标题
- `schedule_type`：`once` 或 `interval`
- `status`：`active`、`paused`、`completed`、`canceled`
- `next_run_at`：下一次到期时间
- `interval_seconds`：周期秒数；一次性计划为空
- `last_run_at` / `last_task_id`：最近一次物化记录
- `created_at` / `updated_at`

### API

`POST /api/tasks`

- 任意已认证成员可创建任务。
- `target_member_id` 必须是已存在的 `agent:*` 成员。
- 创建后状态为 `queued`。

`GET /api/tasks`

- 已认证成员可读取任务。
- Human 当前可读取全部任务；Agent 只能读取目标是自己或自己创建的任务。
- 支持 `target_member_id` 与 `status` 查询过滤。

`POST /api/tasks/{task_id}/claim`

- 仅允许 `agent:*` 成员调用。
- 只有任务目标 Agent 可以领取该任务。
- 只允许领取 `queued` 任务。
- 可传 `instance_id`，且该实例必须属于当前 Agent。
- 领取后任务变为 `running`；关联实例会变为 `busy`，并写入 `current_task_id`。

`POST /api/tasks/{task_id}/complete`

- 仅允许任务目标 Agent 调用。
- 只允许完成 `running` 任务。
- 终态限定为 `succeeded`、`failed`、`canceled`。
- `failed` 必须提供 `last_error`。
- 可传 `result_message_id`，该消息必须由当前 Agent 发送。
- 成功或取消后关联实例回到 `idle`；失败后关联实例进入 `error` 并记录 `last_error`。

`POST /api/tasks/schedules`

- 任意已认证成员可创建延迟或周期性任务计划。
- `target_member_id` 必须是已存在的 `agent:*` 成员。
- 请求字段：`content` 必填，`title` 可选，`run_at` 可选，`interval_seconds` 可选。
- 未传 `interval_seconds` 时为一次性计划；传入后为周期计划。

`GET /api/tasks/schedules`

- Human 当前可读取全部 schedule；Agent 只能读取目标是自己或自己创建的 schedule。
- 支持 `target_member_id` 与 `status` 查询过滤。

`GET /api/tasks/schedules/{schedule_id}`

- 读取当前成员可见的单个 schedule。

`PATCH /api/tasks/schedules/{schedule_id}`

- Human 或 schedule 创建者可更新状态。
- 当前支持 `active`、`paused`、`canceled`。
- `completed` / `canceled` 计划不能恢复为 active 或 paused。

`POST /api/tasks/schedules/run-due`

- 显式物化当前已到期的 `active` schedule，返回 `created_tasks` 与 `updated_schedules`。
- Human 会触发全部到期 schedule；Agent 只会触发目标为自己或自己创建的到期 schedule。
- 一次性 schedule 物化后变为 `completed`；周期 schedule 物化后保持 `active`，并将 `next_run_at` 推进到当前时间之后。
- TALK 当前不自动启动后台调度器；该接口供 bridge、人工脚本或后续服务端调度器调用。

### SDK

`TalkClient` 与 `TalkClientSync` 新增：

- `create_task(target_member_id, content, title=None)`
- `list_tasks(target_member_id=None, status=None)`
- `claim_task(task_id, instance_id=None)`
- `complete_task(task_id, status=..., result_message_id=None, last_error=None)`
- `create_task_schedule(target_member_id, content, title=None, run_at=None, interval_seconds=None)`
- `list_task_schedules(target_member_id=None, status=None)`
- `get_task_schedule(schedule_id)`
- `update_task_schedule(schedule_id, status=...)`
- `run_due_task_schedules()`

## Task Hall 目标态（2026-07-15 确认）

### 产品合同

- **一项委派任务自动创建一个独立 Task Hall**，任务与 Hall / thread 一一关联，不把多个执行任务混在同一个长期群聊中。
- 每个 Task Hall 有且只有一个请求者 A 和一个执行者 B。A 负责定义任务、补充澄清、获取结果与验收；B 负责提问、接受、执行和提交结果。
- Task Hall 必须归属一个 `project_id`，可选关联父任务 / 总目标，便于主 Agent 从实际操作终端拆分并行任务后再汇总。
- “1 对 1”是写入与执行关系；项目所有者 / 决策 Agent 拥有只读观察、介入、取消和验收权限，具体权限矩阵在实现切片确定。
- Task Hall 是可见黑板线程：任务原文、疑问与答复、状态变化、最终结果和异常都持久化到 TALK，不能只存在某个 CLI / Desktop 会话里。

### 标准流程

```text
A 创建并指派
  -> B 有疑问：clarification_requested -> A 补充 -> B accepted
  -> B 无疑问：accepted
  -> in_progress
  -> submitted
  -> A 的终端获取结果并验收
  -> result_collected / completed
```

- `failed`、`canceled`、`timed_out`、`rework_requested` 属于异常或返工分支，后续随状态机设计补齐。
- 当前 `queued / running / succeeded / failed / canceled` 五态继续兼容；目标态是产品语义。是否扩充数据库枚举，或由 task 状态 + Hall 事件组合表达，在首个实现切片决定并提供迁移方案。
- B 提出澄清时任务不能被误标为执行中；B 提交结果也不等于 A 已经收取 / 验收。`submitted` 与 `result_collected / completed` 必须可区分。

### 混合终端运行模型

- 用户在 Codex、Claude Code 等实际操作终端中推进总目标；该终端里的主 Agent 负责拆分、选择目标角色、委派、等待 / 查询结果和最终整合。
- 每个可交互终端只需接入 TALK MCP / client，就能获得跨模型“子 Agent 委派”能力；不要求终端原生支持 subagent。
- 目标 Agent 的 `bridge` / `runner` 负责轮询、领取并驱动 CLI / 模型执行。它是基础设施，不是额外 Agent 角色，也不是额外订阅入口。
- Desktop 与 CLI 不共享对话上下文并不阻塞流程：TALK 是跨入口的持久化真相源。为了避免重复执行，同一任务只能由一个 runner 持有有效 claim / lease。
- 默认委派深度为 1，主 Agent 保留整合与验收责任；递归委派、循环检测和更深链路以后按可靠性需求开放。

### 终端能力合同（名称为草案）

TALK MCP / client 至少应覆盖以下能力，具体方法名在实施时统一：

| 能力 | 草案名称 | 说明 |
|---|---|---|
| 发现可委派对象 | `talk_list_agents` | 按项目查询成员、业务角色、在线 / 忙闲状态 |
| 创建委派 | `talk_delegate_task` | 指定 `project_id`、目标成员、任务标题与正文，自动创建 Task Hall |
| 查询任务 | `talk_get_task` / `talk_list_tasks` | 查询自己创建或分配给自己的任务及状态 |
| 等待变化 | `talk_wait_tasks` | 等待澄清、状态变化或结果，避免终端盲轮询 |
| 回复与纠偏 | `talk_reply_task` / `talk_steer_task` | 回答疑问、补充约束、请求返工 |
| 取消任务 | `talk_cancel_task` | 按权限取消未完成任务 |
| 收集结果 | `talk_collect_results` | 获取一个或多个子任务结果供主 Agent整合 |

### 数据关联草案

在不破坏现有表的前提下，`agent_tasks` 后续至少需要表达：

- `project_id`：所属项目；
- `task_hall_id` 或 `thread_id`：对应 Task Hall；
- `parent_task_id` / `root_goal_id`：可选父任务或总目标；
- 请求者、执行者与实际 runner / instance 的区分；
- `accepted_at`、`submitted_at`、`result_collected_at` 等关键节点；
- claim / lease、attempt 与幂等键，防止多个 runner 重复执行。

字段名与 Task Hall 最终复用 `groups` 还是独立 thread 实体，均属于实现决策；体验层的一任务一 Hall、1 对 1 执行、项目归属和结果可收取不变。

### 项目级 Web 信息架构

- Web UI 以 Project 为一级范围，默认进入项目黑板，而不是把所有 Hall 平铺在全局侧栏。
- 项目内至少分为：`Blackboard`、`Task Halls`、`Discussion Halls`、`Members`、`Activity`。
- Blackboard 按“待执行者确认 / 待请求者澄清 / 执行中 / 结果待收取 / 已完成”等状态聚合任务；点击一行进入对应 Task Hall。
- Discussion Halls 单独呈现多角色讨论，不与 Task Hall 的 1 对 1 执行状态混排。

## 当前边界

- 当前支持 schedule 记录与显式 `run-due` 物化，但没有内置后台调度循环。
- 当前不实现任务重试、超时回收、抢占、重新排队。
- 当前不由 TALK 服务端创建或管理 bridge 进程。
- 当前任务 API 不替代消息系统；任务结果仍建议通过普通 TALK 消息记录，并用 `result_message_id` 关联。
- 当前尚未自动创建 Task Hall，也没有澄清 / 接受 / 提交 / 结果收取的完整状态和项目黑板；这些属于上述目标态。

## 后续计划

1. 定稿 Task Hall 的存储关联与向后兼容状态映射，先落 `project_id`、一任务一 Hall 和 1 对 1 权限边界。
2. 打通创建、澄清、接受、执行、提交与结果收取 API，并补 claim / lease 幂等约束。
3. 提供终端 TALK MCP / client 的委派、查询 / 等待、纠偏 / 取消与结果收集能力。
4. 建项目 Blackboard + Task Hall Web UI，并进行一轮跨模型端到端人工验收。
5. 后续再决定 schedule 后台触发、长任务 SSE、document lock 与递归委派策略。

## 验收点

- [x] Human 可创建目标为 Agent 的任务。
- [x] 任务目标必须是已存在的 `agent:*` 成员。
- [x] Agent 只能看到目标为自己或自己创建的任务。
- [x] Human 与错误 Agent 不能领取他人任务。
- [x] Agent 可领取自己的 `queued` 任务。
- [x] 领取任务时会联动实例状态为 `busy` 并写入 `current_task_id`。
- [x] Agent 可将 `running` 任务完成为 `succeeded` / `failed` / `canceled`。
- [x] 失败完成必须提供 `last_error`，并将实例状态置为 `error`。
- [x] SDK task helper 通过活服务测试。
- [x] Human 可创建一次性或周期性 schedule。
- [x] Agent 只能看到目标为自己或自己创建的 schedule。
- [x] `run-due` 可将到期一次性 schedule 物化为 queued task，并将 schedule 标为 `completed`。
- [x] `run-due` 可将到期周期 schedule 物化为 queued task，并推进 `next_run_at`。
- [x] 暂停的 schedule 不会被 `run-due` 物化。
- [x] SDK schedule helper 通过活服务测试。
