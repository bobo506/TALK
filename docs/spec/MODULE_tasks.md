# MODULE: Agent Tasks

> 所属项目：TALK
> 状态：Task Hall 数据 / API、async / sync client、bundled runner Hall 回传及 Codex MCP / pi 终端工具已实现；可靠性约束和 Web UI 待后续切片

## 目标

提供一个服务端任务队列，让人类或其它已认证成员可以把一段工作请求记录为 task，由目标 `agent:*` 成员的 bridge 实例领取、执行并回写最终状态。当前阶段只做任务记录和分派，不由 TALK 自动启动 bridge 进程。

## 负责范围

- 数据模型：`server/models.py` 中的 `AgentTask`、`AgentTaskSchedule`
- API 路由：`server/routes/tasks.py`；自动生成 Task Hall 的结构保护涉及 `server/routes/groups.py`
- 数据库初始化：`server/db.py`
- SDK 方法：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`

## 当前实现

> 本节只描述已经落地的行为。后文“Task Hall 目标态”同时保留尚未完成的终端、runner 与 Web 合同。

### 数据模型

`agent_tasks` 表记录任务生命周期：

- `id`：自增任务 id
- `schedule_id`：可选来源 schedule id；普通即时任务为空
- `project_id`：可选项目归属；新 Task Hall 调用应提供，空值只为旧客户端和现有 schedule 兼容
- `hall_group_id`：唯一关联的 `groups.type=task` Hall id
- `target_member_id`：目标 Agent 成员，例如 `agent:codex`
- `created_by`：任务创建者
- `content`：任务正文
- `title`：可选短标题
- `status`：runner 执行五态，保持 `queued`、`running`、`succeeded`、`failed`、`canceled`
- `workflow_status`：协作流程状态，支持 `assigned`、`clarification_requested`、`accepted`、`in_progress`、`submitted`、`completed`、`failed`、`canceled`
- `claimed_by`：领取任务的 Agent
- `instance_id`：处理任务的 Agent 实例
- `result_message_id`：任务完成后对应的 TALK 消息，可为空
- `last_error`：失败原因摘要
- `created_at` / `updated_at` / `claimed_at` / `finished_at` / `result_collected_at`

即时任务和 schedule 物化任务都会原子创建一个独立 Task Hall。Hall 当前只包含请求者与执行者：请求者为 `owner`，执行者为 `member`。关联 Task Hall 不能通过普通 Group API 增删成员或独立删除。

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
- 请求者与目标成员必须不同。
- 可传 `project_id`，且项目必须存在；省略时按旧客户端兼容为无项目归属。
- 创建后执行状态为 `queued`、协作状态为 `assigned`，并自动返回唯一 `hall_group_id`。

`GET /api/tasks`

- 已认证成员可读取任务。
- Human 当前可读取全部任务；Agent 只能读取目标是自己或自己创建的任务。
- 支持 `target_member_id`、执行 `status`、`workflow_status` 与 `project_id` 查询过滤。

`GET /api/tasks/{task_id}`

- Human 延续现有管理视角；Agent 只能读取目标是自己或自己创建的任务，其他 Agent 得到 `404`。

`POST /api/tasks/{task_id}/request-clarification`

- 仅执行者可调用；把 `assigned` 推进为 `clarification_requested`。
- 实际问题正文通过对应 Task Hall 的消息时间线发送；处于该状态时不能 claim。

`POST /api/tasks/{task_id}/accept`

- 仅执行者可调用；把 `assigned` 或 `clarification_requested` 推进为 `accepted`。

`POST /api/tasks/{task_id}/collect-result`

- 仅原请求者可调用；任务必须处于 `submitted` 且存在 `result_message_id`。
- 调用后协作状态变为 `completed` 并记录 `result_collected_at`；重复调用幂等返回。

`POST /api/tasks/{task_id}/cancel`

- 仅原请求者可调用；重复取消同一任务会幂等返回。
- 当前只允许取消尚未领取的 `queued` 任务，并同步把执行状态与协作状态更新为 `canceled`。
- 已进入 `running` 的任务会返回 `409`；在 claim lease / attempt 与 runner 中断协议落地前，不伪造运行中任务已被停止。

`POST /api/tasks/{task_id}/claim`

- 仅允许 `agent:*` 成员调用。
- 只有任务目标 Agent 可以领取该任务。
- 只允许领取 `queued` 任务。
- 可传 `instance_id`，且该实例必须属于当前 Agent。
- `clarification_requested` 必须先接受，不能直接领取；旧客户端从 `assigned` 直接领取仍兼容。
- 领取后执行状态变为 `running`、协作状态变为 `in_progress`；关联实例会变为 `busy`，并写入 `current_task_id`。

`POST /api/tasks/{task_id}/complete`

- 仅允许任务目标 Agent 调用。
- 只允许完成 `running` 任务。
- 终态限定为 `succeeded`、`failed`、`canceled`。
- `failed` 必须提供 `last_error`。
- 可传 `result_message_id`，该消息必须由当前 Agent 发送。
- `result_message_id` 可来自对应 Task Hall；为兼容尚未升级的 bridge，暂时也接受旧全局时间线，但拒绝其它 Hall 的消息。
- `succeeded` 将协作状态推进为 `submitted`；`failed` / `canceled` 同步为同名协作状态，不会误标为请求者已收取。
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
- 每次物化都创建独立 Task Hall；schedule 尚无 `project_id` 字段，因此当前物化 Hall 保持无项目归属，项目化 schedule 后续另片处理。
- TALK 当前不自动启动后台调度器；该接口供 bridge、人工脚本或后续服务端调度器调用。

### SDK

`TalkClient` 与 `TalkClientSync` 已提供：

- `create_task(target_member_id, content, title=None, project_id=None)`
- `list_tasks(target_member_id=None, status=None, workflow_status=None, project_id=None)`
- `get_task(task_id)`
- `request_task_clarification(task_id)`
- `accept_task(task_id)`
- `collect_task_result(task_id)`
- `cancel_task(task_id)`
- `claim_task(task_id, instance_id=None)`
- `complete_task(task_id, status=..., result_message_id=None, last_error=None)`
- `create_task_schedule(target_member_id, content, title=None, run_at=None, interval_seconds=None)`
- `list_task_schedules(target_member_id=None, status=None)`
- `get_task_schedule(schedule_id)`
- `update_task_schedule(schedule_id, status=...)`
- `run_due_task_schedules()`

### Bundled runner

- `bridges/cli_bridge.py` 的任务队列 runner 会从 claim 响应读取 `hall_group_id`，把成功或失败的可见结果写入对应 Task Hall，再用该消息的 `id` 完成任务。
- `bridges/codex_bridge.py` 的兼容任务处理入口采用同一 Hall 回传规则；实际 Codex 队列 worker 继续复用通用 runner。
- 旧任务若没有 `hall_group_id`，runner 会保留原有全局时间线回传行为，服务端继续接受这类兼容结果。

### 终端工具

- Codex 使用 `bridges/talk_send_mcp.py`，pi 使用 `bridges/talk_tools_extension.ts`；两端共同提供 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result` 八个 Task Hall 工具，原有 deferred `talk_send` 保持兼容。
- bridge 会从项目目录的 `.talk/project.yaml` 注入默认 `TALK_PROJECT_ID`；调用方仍可在工具参数中显式覆盖项目。
- `talk_list_agents` 会结合项目 Agent profile、成员与实例状态返回可委派对象及在线 / 忙闲情况。
- `talk_wait_tasks` 当前采用最长 30 秒的有界客户端轮询，等待澄清、提交、完成、失败或取消状态；尚未引入服务端事件等待协议。
- `talk_reply_task` 把正文写入对应 Task Hall，并可附带请求澄清或接受任务动作；`talk_collect_result` 在请求者读取结果后把 `submitted` 推进为 `completed`。
- `talk_cancel_task` 遵循服务端安全边界，只能由原请求者取消尚未领取的任务；可选取消原因会先写入 Task Hall。

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
- 当前 `queued / running / succeeded / failed / canceled` 五态继续作为 runner 执行状态；已新增独立 `workflow_status` 表达产品语义，claim / complete 自动同步两套状态。旧库按执行状态回填协作状态。
- B 提出澄清时任务不能被误标为执行中；B 提交结果也不等于 A 已经收取 / 验收。`submitted` 与 `result_collected / completed` 必须可区分。

### 混合终端运行模型

- 用户在 Codex、Claude Code 等实际操作终端中推进总目标；该终端里的主 Agent 负责拆分、选择目标角色、委派、等待 / 查询结果和最终整合。
- 每个可交互终端只需接入 TALK MCP / client，就能获得跨模型“子 Agent 委派”能力；不要求终端原生支持 subagent。
- 目标 Agent 的 `bridge` / `runner` 负责轮询、领取并驱动 CLI / 模型执行。它是基础设施，不是额外 Agent 角色，也不是额外订阅入口。
- Desktop 与 CLI 不共享对话上下文并不阻塞流程：TALK 是跨入口的持久化真相源。为了避免重复执行，同一任务只能由一个 runner 持有有效 claim / lease。
- 默认委派深度为 1，主 Agent 保留整合与验收责任；递归委派、循环检测和更深链路以后按可靠性需求开放。

### 终端能力合同

TALK MCP / pi extension 已覆盖以下能力：

| 能力 | 草案名称 | 说明 |
|---|---|---|
| 发现可委派对象 | `talk_list_agents` | 按项目查询成员、业务角色、在线 / 忙闲状态 |
| 创建委派 | `talk_delegate_task` | 指定 `project_id`、目标成员、任务标题与正文，自动创建 Task Hall |
| 查询任务 | `talk_get_task` / `talk_list_tasks` | 查询自己创建或分配给自己的任务及状态 |
| 等待变化 | `talk_wait_tasks` | 等待澄清、状态变化或结果，避免终端盲轮询 |
| 回复与纠偏 | `talk_reply_task` | 回答疑问、补充约束，并执行澄清 / 接受动作；返工状态后续补齐 |
| 取消任务 | `talk_cancel_task` | 原请求者取消尚未领取的任务 |
| 收集结果 | `talk_collect_result` | 获取单个子任务结果并完成收取动作 |

### 数据关联现状与后续

首个实现切片已确定复用 `groups.type=task`，不新增 thread 实体，并落地：

- `project_id`：所属项目，旧客户端兼容为空；
- `hall_group_id`：唯一对应 Task Hall；
- `created_by` / `target_member_id` / `claimed_by` / `instance_id`：区分请求者、执行者和实际 runner；
- `workflow_status` / `result_collected_at`：区分执行状态、结果提交与结果收取。

`parent_task_id` / `root_goal_id`、更细时间点、lease、attempt 与幂等键仍属于后续可靠性切片。

### 项目级 Web 信息架构

- Web UI 以 Project 为一级范围，默认进入项目黑板，而不是把所有 Hall 平铺在全局侧栏。
- 项目内至少分为：`Blackboard`、`Task Halls`、`Discussion Halls`、`Members`、`Activity`。
- Blackboard 按“待执行者确认 / 待请求者澄清 / 执行中 / 结果待收取 / 已完成”等状态聚合任务；点击一行进入对应 Task Hall。
- Discussion Halls 单独呈现多角色讨论，不与 Task Hall 的 1 对 1 执行状态混排。

## 当前边界

- 当前支持 schedule 记录与显式 `run-due` 物化，但没有内置后台调度循环。
- 当前不实现任务重试、超时回收、抢占、重新排队。
- 当前不由 TALK 服务端创建或管理 bridge 进程。
- 当前任务 API 不替代消息系统；澄清正文和结果正文仍通过 Task Hall 消息记录，并用动作 API / `result_message_id` 关联。
- async / sync client 与 Codex MCP / pi extension 已覆盖项目化创建、单任务读取、协作状态过滤、澄清、接受、等待、Hall 回复、安全取消和结果收取。
- bundled runner 已把新任务结果写入对应 Task Hall，但仍兼容无 `hall_group_id` 的旧任务全局回传。
- `talk_wait_tasks` 当前是最长 30 秒的客户端轮询，不是服务端事件流；Agent 发现结果也尚未提供项目业务角色字段。
- 当前取消只覆盖未领取任务；运行中取消必须等待 claim lease / attempt 与 runner 中断协议。
- 当前没有 Project Blackboard / Task Hall Web UI，也尚未实现 observer、返工和 lease / 超时回收。

## 后续计划

1. [x] 复用 `groups.type=task`，落 `project_id` / `hall_group_id` / `workflow_status`、一任务一 Hall 和 1 对 1 结构边界。
2. [x] 打通澄清、接受、claim 执行、提交与结果收取 API，并保持旧五态兼容。
3. [x] 扩展 async / sync client 的项目化委派、查询和协作动作，并让 bundled runner 把结果写入 Task Hall。
4. [x] 为 Codex MCP / pi extension 提供发现、委派、查询 / 有界等待、Hall 回复、安全取消与结果收集能力。
5. 补 claim lease / attempt / 幂等约束，再建 Project Blackboard + Task Hall Web UI。
6. 完成一轮跨模型端到端人工验收；后续再决定 schedule 项目化 / 后台触发、长任务 SSE、document lock 与递归委派策略。

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
- [x] 创建 task 自动建立唯一 `groups.type=task` Hall，并固定请求者 / 执行者 1 对 1 成员结构。
- [x] `project_id` 校验、项目 / 协作状态过滤和单任务读取通过自动化测试。
- [x] 澄清会阻止 claim；接受后可进入执行；成功提交与请求者收取结果可区分。
- [x] Task Hall 不能通过普通 Group API 改成员或独立删除。
- [x] 旧库新增字段、唯一索引与五态到协作状态回填通过迁移测试。
- [x] async / sync client 均可创建项目任务、按协作状态与项目过滤、读取单任务并执行澄清 / 接受 / 收取结果动作。
- [x] bundled runner 会把结果写入对应 Task Hall，并兼容无 Hall 的旧任务全局回传。
- [x] Codex MCP 与 pi extension 暴露一致的八个 Task Hall 工具，MCP 目录与真实工具调用通过自动化测试。
- [x] 活服务测试贯通发现、委派、澄清 / 回复、接受、领取、Hall 结果提交、等待与结果收取。
- [x] 原请求者可幂等取消尚未领取的任务；其他成员和运行中任务取消均被拒绝。
