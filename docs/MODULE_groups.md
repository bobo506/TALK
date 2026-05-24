# MODULE: Groups / Hall

> 所属项目：TALK
> 状态：`GROUP-1 / HALL-1` 后端与 Web UI 第一版已落地，SDK helper 已接入

## 目标

为 TALK 增加正式的讨论房间模型。Group 是一个讨论房间，Hall 是 Group 内共享的消息时间线。该模块为后续多 Agent 讨论、左侧频道导航、SSE 流式输出和任务状态可视化提供房间作用域。

## 负责范围

- 数据模型：`server/models.py` 中的 `Group`、`GroupMember`、`Message.group_id`
- API 路由：`server/routes/groups.py`
- 消息作用域：`server/routes/messages.py`
- WebSocket 定向推送：`server/ws_hub.py`
- 数据库初始化 / 迁移：`server/db.py`

## 当前实现

### 数据模型

`groups` 表记录讨论房间：

- `id`：Group id，例如 `group:lab`；未指定时服务端自动生成 `group:<uuid>`
- `name`：显示名称
- `description`：可选描述
- `created_by`：创建者成员 id
- `created_at` / `updated_at`

`group_members` 表记录 Group 成员：

- `group_id`
- `member_id`
- `role`：`owner`、`moderator`、`member`
- `created_at`

`messages.group_id` 记录消息所属 Hall：

- `NULL`：旧的 legacy/global 消息流
- 非空：属于对应 Group Hall

## API

`POST /api/groups`

- 已认证成员可创建 Group。
- 请求字段：`id` 可选、`name` 必填、`description` 可选、`member_ids` 可选。
- 创建者自动加入 Group，角色为 `owner`。
- `member_ids` 中的成员会以 `member` 角色加入。

`GET /api/groups`

- Human 当前可列出全部 Group。
- Agent 只能列出自己加入的 Group。

`GET /api/groups/{group_id}`

- Human 当前可读取任意 Group。
- Agent 只能读取自己加入的 Group。

`PATCH /api/groups/{group_id}`

- 当前仅允许 human 成员更新 Group 显示元数据。
- 请求字段：`name` 必填，`description` 可选。
- 更新后会刷新 `updated_at` 并返回最新 Group 快照。

`PUT /api/groups/{group_id}/members/{member_id}`

- 当前仅允许 human 成员管理 Group 成员。
- 可添加成员或更新成员角色。
- 角色限定为 `owner`、`moderator`、`member`。

`DELETE /api/groups/{group_id}/members/{member_id}`

- 当前仅允许 human 成员移除 Group 成员。

## Hall 消息语义

`POST /api/messages` 新增可选 `group_id`：

- 发送 Group 消息时，发送者必须是该 Group 成员。
- 文本正文或文件附言开头的 `@member_id` 仍会解析为 `to_ids`。
- Group 内 `to_ids` 只表示 mention / 注意力路由，不限制同组成员读取 Hall。
- Group 内 mention 目标必须是同一个 Group 的成员。

`GET /api/messages?group_id=<id>`：

- 读取指定 Group 的 Hall 时间线。
- 调用者必须是该 Group 成员。
- 返回该 Group 内所有消息，包括未 mention 当前成员的消息。

不传 `group_id`：

- 保持旧行为，只读取 `messages.group_id IS NULL` 的 legacy/global 消息流。
- 旧的广播、direct、pair view、搜索、分页和撤回逻辑继续适用。

## WebSocket 推送

- Legacy/global 消息继续按旧规则推送：广播给所有在线成员，direct 推送给发送者和接收者。
- Group 消息推送给该 Group 的成员。
- 非 Group 成员不会通过 WebSocket 收到 Group 消息。

## 当前边界

- Web UI 已有 Group 列表、默认 active Group 恢复、Hall 导航、新建 Group 面板和 Hall 内成员管理面板。
- Web UI 成员面板顶部已支持 human 更新当前 Group 名称与描述；Agent 仍只读。
- 创建后的成员增删/角色调整可走 API、SDK helper 或 Web UI 成员面板。
- SDK 已提供 Group API helper，并支持在 `send_text` / `send_file` / `reply` / `fetch_history` 中携带 `group_id`。
- 当前没有 Group 删除 API；删除语义需先确认历史 Hall 消息如何保留或归档。
- 当前没有成员管理权限细分；human 可管理 Group 成员，Agent 不可管理。
- 当前没有 Discussion Session 表；多 Agent 轮次、主持人规则和总结策略仍属后续协议。
- 当前没有 SSE stream；Group 只为后续 stream 提供作用域。

## 后续计划

- 确认 Group 删除 / 归档语义，并补充删除或归档入口。
- 在 Web UI 中补充更完整的未读/提醒状态。
- 设计并实现 Discussion Session / 多 Agent 讨论协议；参考 `openhanako` 的频道群聊模型时，只吸收调度思想，不照搬文件存储和桌面架构。
- 让 SSE stream 事件携带 `group_id` 并显示在对应 Hall。
- 将任务状态、实例状态和文档锁状态接入 Group/Hall 视图。

## 参考设计：OpenHanako Channel Model

2026-05-24 参考仓库：`liliMozi/openhanako`，参考版本：`dbc794de87d58b44bbf5f75f8d20fd99a5d7e156`。

对 TALK 有帮助的点：

- Channel transcript / Hall 应作为讨论真相源：TALK 已有 `messages.group_id`，后续多 Agent 讨论应继续写入同一 Group Hall 时间线。
- `@mention` 只作为提醒和调度优先级，不作为 Group 内可见性规则；这与 TALK 当前 `to_ids` 在 Group 内只表示注意力路由的语义一致。
- Agent 读取群聊后应显式选择 `reply` 或 `pass`，避免自动讨论时出现抢答、沉默或重复发言。
- 后续需要 Agent 级 cursor：每个 `agent:*` 对每个 `group_id` 记录处理到的 `last_message_id`，用于构造未读窗口和避免重复处理。
- 讨论调度必须有保护参数：`max_rounds`、`cooldown`、`max_agent_checks`、recent window 上限。

TALK 的差异化选择：

- 不采用 Markdown 文件作为频道存储；继续使用 SQLite 的 `groups / group_members / messages`。
- 当前验收分支不引入主动心跳、长期记忆、人格系统或复杂桌面工作台。
- DM / 私信能力可作为后续独立能力，不替代 Group Hall 的主协作路径。

## 验收点

- [x] 已认证成员可创建 Group，并自动成为 owner。
- [x] 创建 Group 时可添加初始成员。
- [x] Human 可列出全部 Group。
- [x] Agent 只能列出自己加入的 Group。
- [x] Human 可添加、更新、移除 Group 成员。
- [x] Agent 不能管理 Group 成员。
- [x] Group 消息只允许 Group 成员发送。
- [x] Group 内 mention 目标必须是同组成员。
- [x] Group Hall 对所有 Group 成员可见，即使消息 `to_ids` 只 mention 其中一人。
- [x] 非 Group 成员不能读取 Group Hall。
- [x] 不传 `group_id` 的旧消息历史不包含 Group 消息。
- [x] 旧消息测试、Group 测试和全量后端回归通过。
- [x] Web UI 可在全局消息流和 Group Hall 之间切换。
- [x] Web UI 可创建 Group、选择初始成员并自动进入新 Hall。
- [x] Human 可通过 API / SDK / Web UI 更新 Group 名称与描述。
- [x] Web UI 在 Hall 内发送消息时会携带 `group_id`，且切回全局后不会显示 Hall 消息。
- [x] SDK 可创建/读取 Group、管理成员，并在 Hall 内发送和读取消息。
- [x] Web UI 可在 Hall 内添加成员、调整角色和移除其他成员。
