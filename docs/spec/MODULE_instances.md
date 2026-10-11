# MODULE: Agent Instances

> 所属项目：TALK
> 状态：实例状态 API 已与任务 API 联动；角色生命周期 R1-1 项目维度及写入原子性经 #216/#217 独立复核通过（2026-10-11）

## 目标

记录每个正在运行的 Agent bridge 进程，让 TALK 能知道某个稳定 Agent 身份下有哪些本地实例在线、空闲、忙碌或报错。该模块是任务调度层的运行时状态基础。

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
- `project_id`：可选项目声明，旧行保持 NULL；非空后不可改写/清空。
- `launch_id`：可选启动关联，旧行保持 NULL；非空后不可改写/清空。R1-1 无服务协议，不接受首次非空关联。
- `process_started_at`：可选进程启动时间，不独立构成就绪或进程所有权证明。
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
- 写入先取得真实 SQLite 写锁，再读取实例归属、项目/launch 与名册并提交；同一实例首次项目声明竞争被串行化，同值重复 200、不同项目 409 `instance_project_immutable`。
- 可选字段只更新请求显式出现项：省略保持原值；一般可选字段显式 null 可清空，已有项目/launch 显式 null 或改值则 409。首次项目声明要求当前成员在册且角色（若存在）未归档，失败 422 `instance_project_not_in_roster`。
- 首次非空 launch 关联返回 422 `instance_launch_not_supported`；已有非空值同值重复或省略保持，替换/清空返回 409 `instance_launch_immutable`。真实 launch/expected_instance 验证在 R1-3，当前不把心跳当成服务启动成功。

`GET /api/instances`

- 任意已认证成员可调用。
- 支持 `member_id`、`status` 与可选 `project_id` 查询过滤；不传新参数时原行为保持。
- 默认按 `updated_at desc` 返回。

### SDK

`TalkClient` 新增：

- `report_instance_status(instance_id, runtime=..., status=..., ...)`
- `list_instances(member_id=None, status=None)`

同步客户端 `TalkClientSync` 也暴露同名实例 helper。

### Codex Bridge

`bridges/codex_bridge.py` 已接入实例状态：

- 启动后上报 `idle`
- 开始处理任务时上报 `busy`，并写入 `current_task_id`
- 成功完成后回到 `idle`
- 超时、非零退出码或异常时上报 `error`
- bridge 退出前上报 `offline`

## 后续计划

- 任务表与任务 API 第一版已拆到 `MODULE_tasks.md`。
- 当前后端只记录/分派任务和角色身份事实；宿主一键配置与受管服务启动分别在 R1-2/R1-3，启动 TALK 不启动全部适配服务。
- SDK 本片保持旧参数；项目/launch 上报与服务协议消费者待后续切片配套。生产迁移、真实模型/登录/隔离与宿主等待仍未验收。
- 将实例状态接入 Hall / Group Web UI。
- 将 SSE stream 与实例任务状态关联，支持长回复期间的可见进度。

## 验收点

- [x] Agent 可上报并更新自己的实例状态。
- [x] Human 不能伪造实例上报。
- [x] 一个 Agent 不能接管另一个 Agent 的实例 id。
- [x] 已认证成员可按 `member_id` / `status` / `project_id` 查询实例。
- [x] 可选字段省略保持、项目/launch 不可变与首次非空 launch 拒绝经隔离回归通过。
- [x] WAL 两连接首次项目声明竞争一方 200、另一方 409，真实写锁边界通过。
- [x] SDK 实例状态 helper 通过活服务测试。
- [x] Codex bridge 实例状态路径已完成烟测：`idle -> busy -> idle -> offline`。
- [x] 任务领取 / 完成会联动实例状态：`busy + current_task_id`，完成后回到 `idle`，失败后进入 `error`。
