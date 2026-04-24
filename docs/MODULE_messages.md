# MODULE: 消息收发

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M2 已实现，持续细化中

## 目标

实现纯文本消息的发送与拉取，支持定向消息（`@` 指定接收方）和广播消息。是 Agent 轮询机制（F4）的核心后端。

## 负责范围

- 文件：`server/routes/messages.py`
- 端点：
  - `POST /api/messages` — 发送消息
  - `GET /api/messages` — 拉取消息（轮询）

## 接口契约

### 对外提供

- **`POST /api/messages`**：接收 `{to, type, content?, file_id?, caption?}`，服务端统一解析开头 mention 路由，落库后触发 WebSocket 广播，返回 `MessageOut`
- **`POST /api/messages/{id}/revoke`**：仅发送者本人可在 `revoke_window_sec`（默认 120 秒）内撤回消息，返回 `{id, revoked_at, revoked_by}`
- **`GET /api/messages`**：支持参数 `since`(int), `before`(int), `to`(str), `q`(str), `limit`(int)，返回 `MessageOut[]`

### 依赖外部

- `server/auth.py` — `get_current_member` 鉴权
- `server/models.py` — `Message`, `MessageCreate`, `MessageOut` 模型
- `server/db.py` — `get_session`
- `server/ws_hub.py` — `hub.broadcast()` 实时推送

## 关键约束

- 消息 `id` 单调递增（INTEGER AUTOINCREMENT），兼做 `since` 游标
- `before` 用于向前翻页历史消息，语义为“返回 `id < before` 的更早消息”，结果仍按时间正序返回
- `to_ids` 为 JSON 数组字符串，`NULL` 表示广播
- `GET /api/messages` 的 `to` 过滤逻辑：返回 `to_ids` 包含该成员 **或** `to_ids IS NULL`（广播）的消息
- `q` 用于关键词搜索，当前匹配 `content / caption / filename`
- `since` 与 `before` 互斥，不能同时传入
- 两个端点都需要鉴权
- 消息撤回不做硬删；保留 `revoked_at / revoked_by` 审计字段，响应里改为 `revoked=true`
- 撤回消息仍保留原始 `type` 与 `file_id`，但对外隐藏正文/附言/文件名与文件快照字段
- **`type` 驱动 `content` 语义**（多态约定）：
  - `type=text`：`content` 为消息正文
  - `type=file`：`file_id` **必填**，指向 files 表；`caption` 可选，表示文件附言；`content` 保留为兼容字段，服务端会用文件快照重写为最终文件名
- 文件消息会冻结文件快照字段：`filename`, `size_bytes`, `mime`
- 服务端会校验消息负载：`text` 不允许带 `file_id/caption`，`file` 必须带 `file_id`
- 接收者以服务端解析的“正文/附言开头连续 mention 块”为准；无开头 mention 时继续兼容显式 `to` 字段；无效 mention 返回 `400`

## 当前实现现状

- `POST /api/messages`：从 `get_current_member` 获取发送者身份，落库，调用 `hub.broadcast()`，返回 `MessageOut`（`from` 字段用 Pydantic alias 解决 Python 关键字冲突）
- `POST /api/messages` 现在会优先解析文本正文或文件附言开头的连续 `@mention`，并用解析结果统一写入 `to_ids`
- `Message` / `MessageCreate` / `MessageOut` 已支持 `caption` 字段，用于文件消息附言
- 文件消息会从 `files` 表冻结 `filename / size_bytes / mime` 到消息记录中，作为历史快照返回给新客户端
- `GET /api/messages`：支持两类游标模式：`since + limit` 用于向后取增量；`before + limit` 用于向前翻页历史；初始历史加载在不传游标时返回最新一页
- `GET /api/messages` 现支持 `q` 关键词搜索，可在历史分页模式下筛选正文、文件附言和文件名
- `GET /api/messages` 当前仍先按游标和 `limit` 从数据库取，再在 Python 层按 `to` 过滤
- `server/db.py` 启动时会为旧版 SQLite 数据库自动补齐 `messages.caption` 列，兼容已有 `talk.db`
- `server/db.py` 启动时会为旧版 SQLite 数据库自动补齐 `messages.filename / size_bytes / mime` 列
- `server/db.py` 启动时会为旧版 SQLite 数据库自动补齐 `messages.revoked_at / revoked_by` 列
- 旧版文件消息若已有 `file_id` 但缺少快照字段，启动时会从 `files` 表自动回填
- `POST /api/messages/{id}/revoke` 已实现：仅 `from_id == 当前成员` 可撤回；超出 `revoke_window_sec=120` 秒返回 `403`
- 撤回后的 `GET /api/messages` 会返回 `revoked=true`，并将 `content / caption / filename / size_bytes / mime` 置空；`type` 保持原值，文件实体不删除
- 撤回成功后会通过 WebSocket 推送 `{"type":"revoke","payload":{"id":...,"revoked_by":...}}`，路由范围与原消息一致
- 已验证：定向消息正确送达指定 Agent，广播消息所有人可见；文件消息附言可端到端传递；无效 mention 会被服务端拒绝
- 已补自动化测试：`tests/test_messages.py` 覆盖开头 mention 优先级、无效 mention 拒绝、`before` 历史分页、`q` 对文件名/附言的搜索，以及撤回成功/超窗失败/他人撤回失败/历史撤回态/WS 撤回通知

## 待改进点

- `to` 过滤在 Python 层做（先全量取再过滤），消息量大时效率低。可优化为 SQL 层过滤（SQLite JSON 函数或调整表结构）
- `q` 当前使用简单关键词匹配，未做高亮、分词或全文索引
- 无消息已读状态/ACK 机制（产品文档标记为待定）
- `GET /api/messages` 的 `to` 过滤仍在 Python 层完成，撤回事件的 HTTP 历史补拉也共享这一限制

## 验收标准

- [ ] 发送定向消息后，目标 Agent 通过 `GET ?to=agent:XX&since=N` 能拉到
- [ ] 发送广播消息后，所有成员都能拉到
- [ ] 非目标 Agent 拉不到别人的定向消息
- [ ] `since` 游标正确工作，不丢消息、不重复
- [ ] `limit` 参数生效
- [ ] `before` 游标能返回更早历史消息，且结果保持时间正序
- [ ] `q` 参数能按正文 / 附言 / 文件名筛选消息，并可与 `before` 分页配合使用
- [ ] `type=file` 消息携带 `caption` 时，接收端能收到并渲染附言
- [ ] `type=file` 消息返回 `filename / size_bytes / mime` 快照，前端无需额外请求即可渲染
- [ ] 发送者可在 120 秒窗口内撤回自己的消息，超窗后返回 `403`
- [ ] 非发送者不能撤回他人消息
- [ ] 撤回后在线连接能实时收到 `revoke` 事件，离线后重新拉历史也能看到撤回态
- [ ] 文件消息撤回后实体文件仍保留，但消息快照对外隐藏
## MSG-4 Addendum

- `POST /api/messages` now accepts optional `reply_to`.
- Reply target validation is server-side: target message must exist, be visible to the current member, and not be revoked.
- `GET /api/messages` now returns `reply_to` summary on each message when applicable:
  - `reply_to.id`
  - `reply_to.from_id`
  - `reply_to.preview`
  - `reply_to.type`
  - `reply_to.revoked`
- `reply_to.preview` is the first 80 characters of text content or the file name snapshot.
- If the referenced message is later revoked, history still returns the `reply_to` object, but `preview` becomes `null` and `revoked=true`.
- WebSocket `message` payloads now mirror the REST shape and include the same `reply_to` summary.
- SQLite startup migration now backfills `messages.reply_to` for existing databases by adding the nullable column when missing.

## SEC-1 Addendum

- `GET /api/messages` visibility is now enforced server-side in SQL and aligned with WebSocket delivery semantics.
- Base visible set for the current member is:
  - messages sent by the current member
  - broadcast messages (`to_ids IS NULL`)
  - directed or group messages whose `to_ids` contains the current member
- `to` is no longer a trust boundary. It only narrows the caller's already-visible set.
- `GET /api/messages?to=<other_member>` now returns the pair view between the current member and that member, plus broadcast, plus shared group messages where both are recipients.
- Passing `to` for a third party can no longer reveal messages that are invisible to the caller.
- `q` search also runs only inside the caller's visible set.
- Startup now ensures indexes on `messages.from_id` and `messages.to_ids` to reduce avoidable scans under the tightened filter.
