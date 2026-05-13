# MODULE: Agent Instances

> 所属项目：TALK
> 状态：实例状态 API 第一版已落地，调度 API 待实现

## 目标

记录每个正在运行的 Agent bridge 进程，让 TALK 能知道某个稳定 Agent 身份下有哪些本地实例在线、空闲、忙碌或报错。该模块是后续任务调度层的前置基础。

## 负责范围

- 数据模型：`server/models.py` 中的 `AgentInstance`
- API 路由：`server/routes/instances.py`
- 数据库初始化：`server/db.py`
- SDK 方法：`TALK/client/talk_client.py`

## 当前实现

### 数据模型

`agent_instances` 表记录运行时实例：

- `id`：实例 id，由 bridge 生成或通过 CLI 参数固定
- `member_id`：所属稳定 Agent 成员，例如 `agent:codex`
- `runtime`：运行时类型，例如 `codex`、`claude`、`pi`
- `status`：`starting`、`online`、`idle`、`busy`、`stopping`、`offline`、`error`
- `host` / `pid`：本地主机和进程信息
- `current_task_id`：当前正在处理的任务或消息 id
- `last_error`：最近一次错误摘要
- `created_at` / `updated_at` / `last_seen_at`

### API

`PUT /api/instances/{instance_id}`

- 仅允许 `agent:*` 成员调用。
- 创建或更新当前 Agent 自己的实例。
- 如果同一个 `instance_id` 已属于另一个成员，返回 `403`。
- 每次上报都会刷新 `updated_at` 和 `last_seen_at`。

`GET /api/instances`

- 任意已认证成员可调用。
- 支持 `member_id` 与 `status` 查询过滤。
- 默认按 `updated_at desc` 返回。

### SDK

`TalkClient` 新增：

- `report_instance_status(instance_id, runtime=..., status=..., ...)`
- `list_instances(member_id=None, status=None)`

### Codex Bridge

`bridges/codex_bridge.py` 已接入实例状态：

- 启动后上报 `idle`
- 开始处理任务时上报 `busy`，并写入 `current_task_id`
- 成功完成后回到 `idle`
- 超时、非零退出码或异常时上报 `error`
- bridge 退出前上报 `offline`

## 后续计划

- 增加任务表与调度 API，明确 task / schedule 的生命周期。
- 决定调度层是否负责启动 bridge 进程，或仅负责记录和分派任务。
- 将实例状态接入 Hall / Group Web UI。
- 将 SSE stream 与实例任务状态关联，支持长回复期间的可见进度。

## 验收点

- [x] Agent 可上报并更新自己的实例状态。
- [x] Human 不能伪造实例上报。
- [x] 一个 Agent 不能接管另一个 Agent 的实例 id。
- [x] 已认证成员可按 `member_id` / `status` 查询实例。
- [x] SDK 实例状态 helper 通过活服务测试。
- [x] Codex bridge 实例状态路径已完成烟测：`idle -> busy -> idle -> offline`。
