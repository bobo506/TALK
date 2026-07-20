# MODULE: Agent Tasks

> 所属项目：TALK
> 状态：Task Hall 数据 / API、SDK、bundled runner、终端工具、claim lease / attempt 与 Project Blackboard / Task Hall Web UI 已实现，基础可视化链路已通过人工验收；TH-6a1 任务树与硬预算、TH-6a2 根控制 / 有限授权 / runner 协作中断、TH-6a3 澄清轮次已实现，runner 自动预检和 Review/Test 门禁仍待后续切片

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
- `parent_task_id`：直接父任务；根任务为空
- `root_task_id`：任务树根 id；根任务创建后指向自身
- `delegation_depth`：根任务为 0，后代为父任务深度 + 1
- `may_delegate`：当前任务执行者是否可继续创建子任务；默认 `false`
- `max_delegation_depth` / `max_running_descendants` / `max_running_per_target` / `max_nonterminal_descendants`：只保存在根任务上的统一治理预算；后代字段为空并读取根任务
- `max_clarification_rounds`：当前任务允许的澄清轮数，默认 1，绝对上限 2
- `clarification_round_count`：已经开启的澄清轮数；同一轮的多条问题或答复消息不会重复计数
- `target_member_id`：目标 Agent 成员，例如 `agent:codex`
- `created_by`：任务创建者
- `content`：任务正文
- `title`：可选短标题
- `status`：runner 执行五态，保持 `queued`、`running`、`succeeded`、`failed`、`canceled`
- `workflow_status`：协作流程状态，支持 `assigned`、`clarification_requested`、`clarification_answered`、`needs_decision`、`accepted`、`in_progress`、`submitted`、`completed`、`failed`、`canceled`
- `attempt`：成功 claim 的递增次数；首次领取为 1，租约过期重领后递增
- `claimed_by`：领取任务的 Agent
- `instance_id`：处理任务的 Agent 实例
- `claim_token`：当前 attempt 的私有持有令牌，只在 claim 响应返回，不通过普通任务查询暴露
- `lease_expires_at` / `heartbeat_at`：当前 claim 的租约截止时间与最近一次续租时间
- `result_message_id`：任务完成后对应的 TALK 消息，可为空
- `last_error`：失败原因摘要
- `created_at` / `updated_at` / `claimed_at` / `finished_at` / `result_collected_at`

即时任务和 schedule 物化任务都会原子创建一个独立 Task Hall。Hall 当前只包含请求者与执行者：请求者为 `owner`，执行者为 `member`。关联 Task Hall 不能通过普通 Group API 增删成员或独立删除。

`agent_task_clarification_rounds` 保存任务澄清轮次账本：每条记录包含 `task_id / round_index / status`、B 的 `question_message_id`、A 答复的起止消息 id 和请求 / 答复时间；`task_id + round_index` 唯一，防止并发请求重复消耗轮次。

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
- 顶层任务可传 `may_delegate` 和四项根治理预算；只有 Human 可以授予顶层委派权限或覆盖默认预算，普通 Agent 创建的顶层任务保持默认限制且不可继续委派。
- 可传 `max_clarification_rounds=1|2`；省略时默认 1，不接受 0、3 或无限轮次。
- 带 `parent_task_id` 时创建子任务：父任务必须处于 `running / in_progress`、父任务已获 `may_delegate`，调用者必须是父任务执行者、根请求者或 Human；`project_id` 从父任务继承，不能改写。
- 子任务深度和非终态后代数量由服务端在创建事务中校验；后代并发和同目标并发由 claim 条件更新再次原子校验，直接 REST API 不能绕过。
- 创建后执行状态为 `queued`、协作状态为 `assigned`，并自动返回唯一 `hall_group_id`。

`GET /api/tasks`

- 已认证成员可读取任务。
- Human 当前可读取全部任务；Agent 只能读取目标是自己或自己创建的任务。
- 支持 `target_member_id`、执行 `status`、`workflow_status` 与 `project_id` 查询过滤。

`GET /api/tasks/{task_id}`

- Human 延续现有管理视角；Agent 只能读取目标是自己或自己创建的任务，其他 Agent 得到 `404`。

`POST /api/tasks/{task_id}/request-clarification`

- 仅执行者可在未领取且根控制为 `active` 时调用；B 必须先在对应 Task Hall 发送集中问题，再以 `question_message_id` 登记边界。为兼容既有工具，省略 id 时会使用 Hall 中 B 最近一条未撤回消息。
- 从 `assigned` 或 `clarification_answered` 开启下一轮，并原子递增 `clarification_round_count`；同一问题边界重复调用幂等返回，并发不同请求只有一个能建立该轮。
- 轮次额度已耗尽时不再创建新账本记录，任务进入 `needs_decision`，根任务同步进入 `awaiting_human / needs_decision` 并撤销全树活动 claim。

`GET /api/tasks/{task_id}/clarification-rounds`

- 当前任务可见成员可按轮次顺序读取问题与答复消息边界。

`POST /api/tasks/{task_id}/submit-clarification-answer`

- 仅原请求者可调用；A 可先连续发送多条补充，再用最后一条答复的 `answer_message_id` 明确提交整批答复。
- 服务端从问题边界之后找到 A 的第一条未撤回消息作为答复起点，并保存显式结束边界；普通 Hall 回复本身不会改变任务状态。
- 提交成功后任务进入 `clarification_answered`；相同结束边界重复提交幂等返回。

`POST /api/tasks/{task_id}/resolve-clarification`

- 仅 Human 管理者、当前任务请求者或根任务请求者可释放 `needs_decision`。
- 可选择只补充范围后继续，或把额度增加 1 轮；总额度仍不能超过 2。释放后任务回到 `clarification_answered`，根任务继续保持 `awaiting_human`，必须再经既有 `resume-tree` 明确恢复推进权限。

`POST /api/tasks/{task_id}/accept`

- 仅执行者可调用；新协议只允许把 `assigned` 或 `clarification_answered` 推进为 `accepted`。
- 有显式轮次账本的 `clarification_requested` 不能直接接受，必须由请求者先提交答复；无账本的历史澄清状态保留兼容接受路径。

`POST /api/tasks/{task_id}/collect-result`

- 仅原请求者可调用；任务必须处于 `submitted` 且存在 `result_message_id`。
- 调用后协作状态变为 `completed` 并记录 `result_collected_at`；重复调用幂等返回。

`POST /api/tasks/{task_id}/cancel`

- 仅原请求者可调用；重复取消同一任务会幂等返回。
- 当前只允许取消尚未领取的 `queued` 任务，并同步把执行状态与协作状态更新为 `canceled`。
- 已进入 `running` 的任务会返回 `409`；claim lease 已能阻止陈旧 runner 回写，但运行中取消仍需 runner 协作中断协议。

`POST /api/tasks/{task_id}/claim`

- 仅允许 `agent:*` 成员调用。
- 只有任务目标 Agent 可以领取该任务。
- claim 使用条件更新保证并发领取只有一个请求成功；同一实例重复 claim 当前任务保持幂等。
- 可传 `instance_id`，且该实例必须属于当前 Agent。
- 可传 `lease_seconds`（默认 120 秒，范围 5–3600 秒）；成功领取生成私有 `claim_token`、递增 `attempt` 并返回 `lease_expires_at`。
- `clarification_requested / clarification_answered / needs_decision` 均不能直接领取；B 必须完成澄清协议并显式接受。旧客户端从 `assigned` 直接领取仍兼容。
- 领取后执行状态变为 `running`、协作状态变为 `in_progress`；关联实例会变为 `busy`，并写入 `current_task_id`。

`POST /api/tasks/{task_id}/heartbeat`

- 仅目标 Agent 可用当前 `claim_token` 续租；陈旧 token、已结束任务或已经到期的租约返回 `409`。
- 到期后才抵达的心跳会把任务安全回到 `queued / accepted`，旧 token 随即失效。

`POST /api/tasks/requeue-expired`

- 仅 Agent 可调用，并只回收目标为自己的过期 `running` 任务。
- 回收会清除当前 claim 持有者，把旧实例标记为 `error`；下一次 claim 进入新的 attempt。

`POST /api/tasks/{task_id}/complete`

- 仅允许任务目标 Agent 调用。
- 只允许完成 `running` 任务。
- 终态限定为 `succeeded`、`failed`、`canceled`。
- `failed` 必须提供 `last_error`。
- bundled runner 会提交当前 `claim_token`；token 不匹配、租约已过期或重领后缺少 token 的完成请求均被拒绝，防止陈旧 attempt 覆盖新结果。
- 为兼容尚未升级的第三方 runner，首次 attempt 暂时允许省略 token；任务一旦发生重领就必须携带 token。
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

- `create_task(target_member_id, content, ..., max_clarification_rounds=1)`
- `list_tasks(target_member_id=None, status=None, workflow_status=None, project_id=None)`
- `get_task(task_id)`
- `list_task_clarification_rounds(task_id)`
- `request_task_clarification(task_id, question_message_id=None)`
- `submit_task_clarification_answer(task_id, answer_message_id=...)`
- `resolve_task_clarification(task_id, allow_additional_round=False)`
- `accept_task(task_id)`
- `collect_task_result(task_id)`
- `cancel_task(task_id)`
- `claim_task(task_id, instance_id=None, lease_seconds=120)`
- `heartbeat_task(task_id, claim_token=..., lease_seconds=120)`
- `requeue_expired_tasks()`
- `complete_task(task_id, status=..., result_message_id=None, last_error=None, claim_token=None)`
- `create_task_schedule(target_member_id, content, title=None, run_at=None, interval_seconds=None)`
- `list_task_schedules(target_member_id=None, status=None)`
- `get_task_schedule(schedule_id)`
- `update_task_schedule(schedule_id, status=...)`
- `run_due_task_schedules()`

### Bundled runner

- `bridges/cli_bridge.py` 的任务队列 runner 会从 claim 响应读取 `hall_group_id`，把成功或失败的可见结果写入对应 Task Hall，再用该消息的 `id` 完成任务。
- `bridges/codex_bridge.py` 的兼容任务处理入口采用同一 Hall 回传规则；实际 Codex 队列 worker 继续复用通用 runner。
- runner 默认申请 120 秒租约；claim 心跳同时承担根控制探针，默认及硬上限均为每 5 秒一次，即使显式传入更长的 `--task-heartbeat-interval` 也不会放宽控制检查上限。每轮队列轮询仍会先回收属于自己的过期 claim，再领取 queued task。
- runner 在本地命令执行期间持续验证 token。服务端因暂停、检查点、整树终止或其它 claim 失效原因返回 `404 / 409` 时，通用 CLI 与 Codex runner 都会取消执行协程；`run_cli_command` 收到取消后终止并回收本地子进程，不发送结果、不调用 `complete`。正常完成时仍携带 token 回写，由服务端再次做原子校验。
- Codex / pi bridge 为队列 worker 使用独立任务命令：保留所选 read-only / workspace-write 能力，但不向嵌套模型暴露 TALK 结果投递工具；Task Hall 的结果消息只由 runner 写入，避免模型工具调用与 runner 可见输出形成重复结果。
- 旧任务若没有 `hall_group_id`，runner 会保留原有全局时间线回传行为，服务端继续接受这类兼容结果。

### 终端工具

- Codex 使用 `bridges/talk_send_mcp.py`，pi 使用 `bridges/talk_tools_extension.ts`；两端共同提供 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result` 八个 Task Hall 工具，原有 deferred `talk_send` 保持兼容。
- bridge 会从项目目录的 `.talk/project.yaml` 注入默认 `TALK_PROJECT_ID`；调用方仍可在工具参数中显式覆盖项目。
- `talk_list_agents` 会结合项目 Agent profile、成员与实例状态返回可委派对象及在线 / 忙闲情况。
- `talk_wait_tasks` 当前采用最长 30 秒的有界客户端轮询，默认也会返回 `clarification_answered / needs_decision`；尚未引入服务端事件等待协议。
- `talk_reply_task` 把正文写入对应 Task Hall，并可把该消息原子关联为请求澄清、提交澄清答复、释放人工决策或接受任务动作；`talk_collect_result` 在请求者读取结果后把 `submitted` 推进为 `completed`。
- `talk_cancel_task` 遵循服务端安全边界，只能由原请求者取消尚未领取的任务；可选取消原因会先写入 Task Hall。

### Project Blackboard / Task Hall Web UI

- Web UI 登录后以 Project 为一级范围，默认打开所选项目的任务黑板；项目选择和最近项目按成员保存在本地浏览器。
- Blackboard 以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合项目任务；待响应列包含待确认、待澄清和已接受待领取状态，详情面板保留精确协作状态。
- 人类可在项目内选择 Agent、填写标题与正文并创建任务；服务端自动建立的 Task Hall 会同步出现在项目 Hall 列表。
- 任务卡和详情面板展示请求者、执行者、运行状态、attempt 与活动租约，并按当前成员权限提供进入 Hall、请求澄清、接受、收取结果和取消未领取任务动作。
- Task Hall 继续复用既有消息时间线和文件 / 回复能力；项目任务每 5 秒刷新一次，runner 回写结果后可从 Hall 与黑板两处看到，并由请求者收取为完成态。
- Web 目前还没有“提交澄清答复”、轮次提示或 `needs_decision` 处理入口；TH-6a3 先完成服务端、SDK 和终端工具协议，页面闭环留待后续 Blackboard 控制切片。

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

`parent_task_id` / `root_task_id` / `delegation_depth` / `may_delegate` 与四项根治理预算已在 TH-6a1 落地；`control_status`、授权 epoch、切片额度、授权到期时间和检查点原因已在 TH-6a2.1 落地。claim lease、attempt 与私有 token 已落地；业务幂等键仍属于后续可靠性切片。

### 项目级 Web 信息架构

- Web UI 以 Project 为一级范围，默认进入项目黑板，而不是把所有 Hall 平铺在全局侧栏。
- 项目内至少分为：`Blackboard`、`Task Halls`、`Discussion Halls`、`Members`、`Activity`。
- Blackboard 按“待执行者确认 / 待请求者澄清 / 执行中 / 结果待收取 / 已完成”等状态聚合任务；点击一行进入对应 Task Hall。
- Discussion Halls 单独呈现多角色讨论，不与 Task Hall 的 1 对 1 执行状态混排。

## TH-6 治理、可中断推进与质量门禁合同（2026-07-18 确认）

### 设计原则

- 主 Agent 获得的是**有限批次授权**，不是一次确认后的无限自主推进。额度允许时可连续完成少量明确切片，但到达批次边界、重大风险点或里程碑后必须暂停并等待人类确认。
- “系统定期停下来”和“人类随时喊停”是两个独立能力：自动检查点负责防止任务持续扩张，人工暂停负责立即撤销尚未消费的推进授权。
- 关键限制必须由服务端原子校验。prompt、`AGENTS.md`、runner 工具裁剪和进程内锁继续作为行为指导，但不能替代服务端的任务树、预算、暂停和质量门禁。
- 现有 `status` 执行五态与 `workflow_status` 协作状态继续表达单个任务的执行事实；根任务控制状态单独建模，暂停不能伪装成失败、取消或完成。
- 开发、Review、测试与返工分别使用独立 Task Hall，保持每个 Hall 请求者 A ↔ 执行者 B 的 1 对 1 合同；主 Agent 通过根任务和任务关联组织流水线。

### 任务树与治理字段

TH-6a1 已按以下字段语义实现任务树与硬预算：

- `parent_task_id`：直接委派来源；顶层任务为空。
- `root_task_id`：整棵任务树的根任务；新根任务在创建后指向自身，旧任务迁移时也各自成为独立根。
- `delegation_depth`：根任务为 0，子任务为父任务深度 + 1。
- `may_delegate`：当前任务的执行者是否获得继续创建子任务的权限；兼容旧任务与普通直派任务默认 `false`。
- 根任务保存 `max_delegation_depth`、`max_running_descendants`、`max_running_per_target`、`max_nonterminal_descendants` 等治理值，后代读取根任务的统一预算，不能自行放宽。

默认硬保护值：

- 最大委派深度 1。
- 单个根任务同时运行的后代任务最多 3 个。
- 同一根任务内，单个目标 Agent 同时运行最多 1 个任务。
- 单个根任务累计非终态后代最多 8 个；非终态指执行状态仍为 `queued` 或 `running`。
- 子任务默认 `may_delegate=false`；只有根任务控制者显式提高深度并授予具体任务继续委派权限后才能突破默认边界。

创建带 `parent_task_id` 的任务时，服务端必须校验：调用者确实是父任务执行者或有权控制该根任务、父任务仍可继续协作、根控制状态允许推进、委派权限存在、深度未超限、非终态后代预算尚有余额。claim 时必须再次原子校验根控制状态、根并发和单目标并发，覆盖并发请求、直接 REST API 与第三方客户端。

当前已实现调用者权限、父任务执行状态、委派权限、项目继承、深度、非终态后代、根运行并发、单目标运行并发、根控制状态、授权到期时间和授权 epoch 校验。子任务创建必须提交根任务当前 `authorization_epoch`；切片预留和 claim 均通过条件更新串行化竞争请求，旧批次请求、直接 REST API 与第三方客户端不能绕过。旧任务迁移时各自回填为独立根，深度为 0、`may_delegate=false`，并获得默认治理值，旧完成 / 收取流程不变。

### 有限批次授权与自动检查点

TH-6a2.1 已实现以下根任务推进授权字段：

- `authorization_epoch`：每次人类重新授权时递增，便于拒绝陈旧主 Agent 使用旧授权继续创建任务。
- `authorized_slice_budget` / `reserved_slice_count`：当前批次允许启动与已预留的开发切片数。
- `authorization_expires_at`：当前批次授权到期时间；默认最长连续推进窗口遵循 `AGENTS.md` 的 60–90 分钟规则。
- `checkpoint_reason`：暂停原因，例如 `batch_limit`、`risk_boundary`、`milestone`、`time_limit`、`usage_limit`、`review_exhausted`、`needs_decision`、`manual_pause`。

当前根任务开启委派时默认获得 2 个切片、90 分钟授权；Human 可显式设置 1–3 个切片与 60–5400 秒有效期。恢复会递增 `authorization_epoch`、重置当前批次预留数并生成新的到期时间。历史可委派根任务回填为 `active / epoch=1`，已有后代数量计入默认额度，避免升级后凭空获得额外切片；历史不可委派任务保持兼容，授权额度为 0。

批次规则：

- 普通明确小切片默认最多连续 2 个；纯文档 / 配置批次可由人类显式授权到 3 个。
- 前端真实交互、数据库 / 协议、部署 / 权限或跨模块协作默认每批 1 个切片。
- 创建 `development` 任务时预留 1 个切片额度，防止并发创建绕过预算；`review`、`test` 不消费开发切片额度。
- 同一切片的 `rework` 不算新功能切片，但 Review 自动返工最多 2 轮；仍未通过时根任务进入 `awaiting_human`，由人类决定调整范围、继续或终止。
- 批次额度耗尽后，已创建任务及其 Review 可以安全收尾，但主 Agent 不能创建新的开发切片；收尾完成后根任务自动进入 `awaiting_human`。
- 到达可独立体验的里程碑时，无论额度是否仍有剩余，都必须在 Review、完整自动化回归和黑盒测试结束后进入 `awaiting_human`，不能自动开启下一阶段。

TH-6a2.1 尚无 `task_kind`，因此当前每个新后代统一按 1 个开发切片计数；`review / test / rework` 的免计或复用规则要等 TH-6c 的任务类型与关系落地。额度耗尽已能原子拒绝新后代，授权到期会在下一次创建或 claim 时把根任务推进到 `awaiting_human / time_limit`；“已创建任务安全收尾后自动因 `batch_limit` 进入等待”仍待后续任务关系与汇总逻辑补齐。

### 根任务控制状态与随时喊停

根任务新增独立 `control_status`：

```text
active -> pause_requested -> paused
active/paused -> awaiting_human
paused/awaiting_human -> active        # 仅人类重新授权
active/paused/awaiting_human -> cancel_requested -> canceled
```

- `active`：允许在当前授权和治理预算内创建、领取及执行任务。
- `pause_requested`：暂停请求已持久化；服务端立即禁止新建后代和新 claim，并通知运行中 runner 协作中断。
- `paused`：没有仍持有有效执行权的后代；Hall、消息、结果、attempt 和进度全部保留，可重新授权恢复。
- `awaiting_human`：系统因批次、风险、额度、Review、澄清或里程碑门禁主动暂停，语义上同样禁止继续推进。
- `cancel_requested` / `canceled`：终止整棵任务树；与可恢复的暂停严格区分。

控制动作合同：

- `POST /api/tasks/{task_id}/pause-tree`：根请求者、Human 管理者或根执行者均可请求暂停；传入任一后代 id 时先解析到根任务。
- `POST /api/tasks/{task_id}/resume-tree`：只有根请求者或 Human 管理者可调用；必须提交新的 `slice_budget` 与授权有效期，生成新 `authorization_epoch`。
- `POST /api/tasks/{task_id}/checkpoint`：主 Agent 主动汇总并进入 `awaiting_human`，用于风险、额度或产品方向需要人工判断的情况。
- `POST /api/tasks/{task_id}/cancel-tree`：只有根请求者或 Human 管理者可调用；排队任务取消，运行任务进入协作中断，最终整树终止。
- `GET /api/tasks/{task_id}/tree`：返回根任务、后代、当前授权、预算占用、质量门禁与控制状态，供终端和 Blackboard 使用。

以上五个服务端入口已在 TH-6a2.1 实现，并同步提供 async / sync SDK helper。当前 `tree` 返回根任务、全树任务、运行 / 非终态后代数、剩余切片额度和授权是否过期；质量门禁字段要等 TH-6c / TH-6d 再加入。权限按根请求者、Human 管理者和根执行者分级，传入后代 id 会先解析到根任务。

暂停传播规则：

- 服务端写入 `pause_requested` 后立即拒绝后代创建和 claim，不能等待主 Agent 下一轮 prompt 自查。
- bundled runner 在本地命令运行期间最多每 5 秒检查一次控制指令；收到暂停 / 终止后停止本地子进程，不写入伪成功结果。
- 暂停导致的协作中断把仍需继续的任务安全恢复为 `queued / accepted`，清除并失效当前 claim token；恢复后产生新 attempt，陈旧 runner 结果继续被服务端拒绝。
- 第三方 runner 若不支持协作中断，服务端至少立即撤销其写回资格并等待租约回收；TALK 不承诺跨机器强杀未知进程。

TH-6a2.1 已完成服务端部分：暂停 / 检查点会把运行任务安全回到 `queued / accepted`，清除 claim token 与实例占用；整树终止会取消所有非终态任务；心跳和完成接口会拒绝陈旧 claim。TH-6a2.2 已让 bundled runner 复用 claim 心跳作为最长 5 秒一次的控制探针：服务端撤销 claim 后会取消本地命令，并放弃结果消息与 `complete`，因此暂停后的安全回队和终止后的取消状态不会被陈旧 runner 覆盖。

### Task Hall 澄清轮次合同

- 默认 `max_clarification_rounds=1`，复杂任务可由根控制者在创建时显式提高到 2，不允许无限追问。
- 一轮是“B 的一批集中问题 + A 的完整答复”，不是一条 Hall 消息。服务端保存澄清轮次账本和问题 / 答复消息边界，不能按消息数量推断轮次。
- B 先把集中问题写入 Task Hall，再调用 `request-clarification` 原子登记本轮；任务进入 `clarification_requested`，禁止 claim。
- A 可以连续发送多条补充，最后调用 `POST /api/tasks/{task_id}/submit-clarification-answer` 显式提交本轮答复边界；普通 Hall 回复不会提前唤醒 B。
- 答复提交后任务进入 `clarification_answered`，runner 携带任务原文和分页读取的完整 Hall 上下文重新预检；充分则 `accept -> claim -> execute`，仍不足且有额度则开启下一轮。
- 额度耗尽仍无法执行时进入 `needs_decision`，同时使根任务进入 `awaiting_human`；Human 可补充范围、增加一次明确额度、改派或终止，系统不得强制领取或猜测执行。
- 根任务 `paused / awaiting_human / cancel_requested / canceled` 的控制状态优先于单任务澄清状态；即使答复已提交也不能绕过根控制门禁 claim。

### 开发、Review、测试与返工门禁

任务新增 `task_kind`：`general`、`development`、`review`、`test`、`rework`。旧任务迁移为 `general`，不被新质量门禁追溯阻断。

- `development`：实现一个明确切片，结果必须提供可审查的变更引用、修改文件、自测命令、结果和已知风险。
- `review`：独立 Reviewer 只读审查一个或多个开发 / 返工任务，结构化结论为 `approved`、`changes_requested` 或 `blocked`。
- `test`：Tester 对冻结版本执行里程碑级完整自动化回归和黑盒 / E2E 测试，结构化结论为 `passed`、`failed` 或 `blocked`。
- `rework`：针对 Review / 测试缺陷创建的新任务，必须关联原开发任务与触发返工的门禁任务，不能覆盖或篡改旧结果。

任务关系使用独立关联记录表达 `reviews`、`tests`、`reworks` 等关系，使一次低风险批量 Review 可以覆盖 2–3 个开发任务，测试任务也可以覆盖整个根任务的冻结版本。Review / 测试结论不得只从自然语言中猜测；`complete` 必须提交与 `task_kind` 匹配的结构化 `gate_verdict`。

Review 策略：

- 高风险切片逐片 `required` Review。
- 同模块低风险切片可标为 `batch`，一次 Review 最多覆盖当前授权批次内 2–3 个切片。
- 纯文案、注释或轻量配置可由具备决策权限的控制者显式标记 `exempt`；开发 Agent 不能自行豁免。
- Reviewer 必须与被审开发任务的执行者不同；Review Agent 默认只返回问题和结论，不直接修改开发结果。
- `changes_requested` 后由主 Agent 创建 `rework`；同一质量问题自动返工达到 2 轮仍未通过时必须暂停交回人类。

里程碑测试策略：

- 黑盒测试不在每个普通切片运行；开发 Agent 每个切片仍必须完成单元 / 定向测试，Tester 只在根任务标记的里程碑出场。
- Tester 必须能启动隔离服务、调用 API、控制浏览器并读取日志；仅修改业务角色名称而没有这些能力不算有效 Tester。
- 新返工发生后，针对旧变更版本的 Review / 测试通过结论失效；主 Agent 必须对最新冻结版本重新取得所需门禁结论。
- 有任一必需 Review 未通过，或里程碑尚无最新版本的 `passed` 测试时，服务端拒绝根任务提交成功结果。
- 里程碑测试通过后根任务自动进入 `awaiting_human`；Human 明确验收或重新授权前，主 Agent 不能继续下一阶段。

### 业务角色发现与权限边界

- `talk_list_agents` 与项目 Agent API 应返回项目业务角色、`decision_tier`、实例状态和能力摘要，便于主 Agent 建议开发者、Reviewer 与 Tester。
- `business_role` 仍是项目自定义自由文本，服务端不把 `dev / reviewer / tester` 固化成全局枚举；质量任务通过 `task_kind` 与门禁结论获得强语义。
- 主 Agent 可选择合适成员，但服务端仍强制 Reviewer 与被审开发者分离、根任务控制权限、门禁完整性和暂停传播。
- 当前 `.talk/groups.yaml` 把 `agent:pi` 与 `agent:pi-kimi` 都标为 `reviewer`，尚无具备黑盒运行能力的 `tester`；正式启用质量流水线前必须新增或重新配置具有相应工具权限的成员。

### 兼容、非目标与实施顺序

- 旧任务迁移后各自成为根任务，`task_kind=general`、`may_delegate=false`、无强制 Review / 测试门禁，继续兼容旧客户端完成与收取流程。
- TH-6 不自动启动或强杀 bridge 进程，不引入正式 CI/CD、灰度发布或复杂运维监控，也不要求每个普通切片执行浏览器黑盒测试。
- 控制、预算和质量门禁应先覆盖服务端与 bundled runner；第三方客户端可逐步升级，但不能绕过服务端拒绝行为。
- 实施顺序固定为：TH-6a1 任务树 / 硬预算 -> TH-6a2 暂停 / 授权控制 -> TH-6a3 澄清轮次 -> TH-6b runner 自动预检与澄清 -> TH-6c Review 门禁 -> TH-6d 里程碑测试 / Blackboard / 人工验收 -> TH-7 通用终端接入。

## 当前边界

- 当前支持 schedule 记录与显式 `run-due` 物化，但没有内置后台调度循环。
- 当前已实现 claim 租约过期回收与重新排队，但没有可配置的业务重试上限、退避或失败策略。
- 当前不由 TALK 服务端创建或管理 bridge 进程。
- 当前任务 API 不替代消息系统；澄清正文和结果正文仍通过 Task Hall 消息记录，并用动作 API / `result_message_id` 关联。
- async / sync client 与 Codex MCP / pi extension 已覆盖项目化创建、单任务读取、协作状态过滤、澄清、接受、等待、Hall 回复、安全取消和结果收取。
- bundled runner 已把新任务结果写入对应 Task Hall，但仍兼容无 `hall_group_id` 的旧任务全局回传。
- `talk_wait_tasks` 当前是最长 30 秒的客户端轮询，不是服务端事件流；Agent 发现结果也尚未提供项目业务角色字段。
- 单任务 `cancel` 仍只覆盖未领取任务；`cancel-tree` 已能立即撤销全树服务端执行权并取消非终态任务，bundled runner 会在最长 5 秒控制探针发现 claim 失效后终止本地命令。第三方 runner 仍需自行实现同一协议。
- TH-6a1 已实现任务树字段、旧库回填、委派权限及深度 / 根并发 / 单目标并发 / 非终态后代硬预算；async / sync SDK 已暴露对应创建参数。
- TH-6a2.1 已实现根任务 `control_status`、有限批次授权、旧 epoch 拒绝，以及暂停 / 恢复 / 检查点 / 整树终止的服务端传播；TH-6a2.2 已让 bundled runner 在本地执行期间最多每 5 秒响应 claim 撤销并停止子进程。服务不可达时无法接收新的控制事实，仍由现有本地租约截止时间提供最终失效保护。
- TH-6a3 已实现每任务 1–2 轮澄清额度、显式问题 / 答复边界账本、`clarification_answered / needs_decision`、人工释放动作和 claim 原子门禁；bundled runner 尚未自动预检、等待答复或重放完整 Hall 上下文，这部分属于 TH-6b。
- 根任务当前仍可在后代未结束时自行完成；整树汇总、完成条件和质量门禁要随控制 / Review/Test 后续切片收敛。
- 当前任务没有 `task_kind`、结构化 Review / 测试结论或任务关系记录；现有 `agent:pi` / `agent:pi-kimi` profile 也不具备完整黑盒测试能力，质量流水线尚不可启用。
- 无租约字段的历史 `running` 任务不会被自动回收，避免升级时误判仍在执行的旧 runner。
- Project Blackboard 与 Task Hall Web UI 已覆盖创建、查看、Hall 协作、接受 / 澄清、结果收取和安全取消；项目级 `Members / Activity` 独立页面、observer 与返工尚未实现。
- Codex 与 pi 真实 CLI 均已完成 Task Hall 技术链路冒烟；pi 在“逐字回复”类指令上的内容遵循仍弱于 Codex，属于模型输出质量边界，不影响单 Hall 结果投递与状态推进，需在项目管理者人工验收时继续观察。

## 后续计划

1. [x] 复用 `groups.type=task`，落 `project_id` / `hall_group_id` / `workflow_status`、一任务一 Hall 和 1 对 1 结构边界。
2. [x] 打通澄清、接受、claim 执行、提交与结果收取 API，并保持旧五态兼容。
3. [x] 扩展 async / sync client 的项目化委派、查询和协作动作，并让 bundled runner 把结果写入 Task Hall。
4. [x] 为 Codex MCP / pi extension 提供发现、委派、查询 / 有界等待、Hall 回复、安全取消与结果收集能力。
5. [x] 补 claim lease / attempt / token 幂等约束、runner 心跳、过期回收和陈旧结果拒绝。
6. [x] 建 Project Blackboard + Task Hall Web UI，形成项目内可见、可操作的完整委派流程。
7. [x] TH-6a0：冻结任务树治理、有限批次授权、随时暂停、澄清轮次与 Review/Test 质量门禁合同。
8. [x] TH-6a1：实现任务树字段、旧数据迁移、委派权限、深度 / 根并发 / 单目标并发 / 非终态后代硬预算及并发测试。
9. [x] TH-6a2.1：实现根任务控制状态、有限批次授权、暂停 / 继续 / 检查点 / 整树终止服务端控制面、SDK 与原子门禁。
10. [x] TH-6a2.2：实现 bundled runner 最长 5 秒控制检查、本地子进程协作中断与安全回队。
11. [x] TH-6a3：实现澄清轮次账本、显式答复提交、`clarification_answered / needs_decision` 与服务端 claim 门禁。
12. TH-6b：实现 runner 领取前预检、同 Hall 自动澄清、完整分页上下文重放和重复唤醒幂等保护。
13. TH-6c：实现任务类型 / 关系、结构化 Review 结论、批量 Review、返工与角色发现。
14. TH-6d：实现里程碑测试门禁、Blackboard 控制入口、最新版本失效规则与人工验收暂停。
15. TH-7：补 Codex Desktop / 通用终端接入包装，再评估 schedule 项目化、长任务事件等待、document lock 等后续能力。

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
- [x] 并发 claim 只有一个实例成功；同一实例重复 claim 保持 attempt / token 不变。
- [x] 心跳可续租，过期 claim 会安全回队并允许新 attempt 重领。
- [x] 陈旧 token 与重领后缺少 token 的 complete 均被拒绝；当前 runner 会携带 token 完成任务。
- [x] runner 丢失租约时会取消本地命令，且不会发送或提交陈旧结果。
- [x] Web UI 可按项目创建任务、查看黑板分栏与任务详情，并进入服务端自动创建的对应 Task Hall。
- [x] Browser 真实交互已贯通登录、委派、Hall 消息、bundled runner 领取 / 回写、结果待收取和请求者完成收取，控制台无 error / warning。
- [x] 真实 Codex / pi CLI 均已贯通领取、执行、单条 Hall 结果回写与结果收取；独立任务命令已消除 pi 同时调用 TALK 工具造成的重复结果。
- [x] 服务端原子强制任务树深度、根并发、单目标并发、非终态后代和委派授权预算，直接 API 不可绕过。
- [x] 服务端可随时暂停根任务树；暂停后禁止新建 / claim、立即撤销现有 claim，陈旧心跳与结果无法写回。
- [x] bundled runner 收到暂停 / 终止后最多 5 秒停止本地子进程，并按服务端状态安全回队或取消。
- [x] “继续一批”生成新的有限切片授权与 `authorization_epoch`；并发预留、到期和陈旧 epoch 由服务端原子拒绝。
- [ ] 批次安全收尾、风险、Review 或里程碑边界会按完整任务关系自动进入 `awaiting_human`。
- [x] 澄清按问题批次与显式答复边界计轮，普通回复不提前唤醒；额度耗尽进入 `needs_decision / awaiting_human`，claim 不能猜测执行。
- [ ] 必需 Review 未通过时根任务不能提交；低风险批量 Review、独立 Reviewer 和最多两轮自动返工受服务端约束。
- [ ] 里程碑最新冻结版本必须通过完整自动化回归和黑盒测试，随后自动暂停等待 Human 验收。
