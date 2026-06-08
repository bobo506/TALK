# MODULE: Agent Tasks

> 所属项目：TALK
> 状态：任务队列与显式触发调度 API 第一版已落地

## 目标

提供一个服务端任务队列，让人类或其它已认证成员可以把一段工作请求记录为 task，由目标 `agent:*` 成员的 bridge 实例领取、执行并回写最终状态。当前阶段只做任务记录和分派，不由 TALK 自动启动 bridge 进程。

## 负责范围

- 数据模型：`server/models.py` 中的 `AgentTask`、`AgentTaskSchedule`
- API 路由：`server/routes/tasks.py`
- 数据库初始化：`server/db.py`
- SDK 方法：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`

## 当前实现

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

## 当前边界

- 当前支持 schedule 记录与显式 `run-due` 物化，但没有内置后台调度循环。
- 当前不实现任务重试、超时回收、抢占、重新排队。
- 当前不由 TALK 服务端创建或管理 bridge 进程。
- 当前任务 API 不替代消息系统；任务结果仍建议通过普通 TALK 消息记录，并用 `result_message_id` 关联。

## 后续计划

- 决定 schedule 的实际触发方式：bridge 轮询、系统定时脚本，或服务端后台 worker。
- 为长任务接入 SSE stream，让用户看到任务执行中的增量输出。
- 将任务状态接入 Hall / Group Web UI。
- 结合 document lock API，在任务领取前或执行前检查写入权限。

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
