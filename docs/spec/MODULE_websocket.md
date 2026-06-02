# MODULE: WebSocket 连接管理

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M1 已实现，已补 WebSocket 心跳 / send / 鉴权共用逻辑、SSE 只读事件流与自动化测试

## 目标

维护所有在线客户端（浏览器 + Agent）的 WebSocket 长连接，在新消息落库后实时推送给相关连接，实现低延迟的消息送达。

## 负责范围

- 文件：`server/ws_hub.py`, `server/main.py`（WebSocket 与 SSE 端点）
- 端点：`WS /ws?token=<api_key>`、`GET /api/events?token=<api_key>`

## 接口契约

### 对外提供

- **`hub.broadcast(msg_out: MessageOut)`**：供消息模块在落库后调用，按 `to` 字段精准推送或全量广播
- **`hub.connect(member_id, ws)`** / **`hub.disconnect(member_id, ws)`**：连接生命周期管理
- **`hub.subscribe_events(member_id)`** / **`hub.unsubscribe_events(member_id, queue)`**：SSE 订阅生命周期管理
- **`presence` 推送**：连接建立时向当前连接发送在线快照；成员首次上线/最后下线时向所有在线连接广播 `{"type":"presence","payload":{"online_ids":[...]}}`
- **`ping / pong` 心跳**：服务端周期性下发 `{"type":"ping"}`，客户端回 `{"type":"pong"}`；超过超时时间无任何入站帧时，服务端主动断开连接
- **`send` 入站事件**：客户端可发送 `{"type":"send","payload":{...MessageCreate...}}`，其行为与 `POST /api/messages` 等价；失败时返回 `{"type":"send_ack","ok":false,"error":"..."}`
- **SSE 只读事件流**：`GET /api/events?token=<api_key>` 返回 `text/event-stream`；事件名为 `message / presence / revoke / ping`，`data:` 为对应 payload JSON
- **SSE 断线补发**：`GET /api/events` 支持浏览器自动发送的 `Last-Event-ID` header，也支持 `last_event_id=<id>` query 参数；服务端会补发当前成员可见且 `message.id > last_event_id` 的历史消息快照

### 依赖外部

- `server/models.py` — `MessageOut` 用于序列化推送数据
- `server/db.py` — `engine`、`WS_PING_INTERVAL`、`WS_PING_TIMEOUT`
- `server/auth.py` — `resolve_member_by_key()`，供 REST / WS 共享 API Key 查表逻辑
- `server/routes/messages.py` — `create_message()`，供 REST / WS 共享消息创建与广播逻辑

## 关键约束

- 推送逻辑：`to=null`（广播）→ 推送给所有在线 WS/SSE 连接；`to=[ids]` → 只推送给 `to` 列表中的连接 + 发送者自己
- 连接断开时自动清理，不应有僵尸连接
- WS / SSE 端点鉴权与 REST 一致（通过 `token` query 参数查 `members` 表）
- `presence` 只按“成员是否至少存在一条 WS 或 SSE 在线连接”统计，不区分同一成员的多标签页数量

## 当前实现现状

- `Hub` 类：单例 `hub` 实例，内部维护 WebSocket 连接列表与 SSE 事件队列列表（member_id → 多连接/多队列）
- `broadcast()`：序列化 `MessageOut` 为 JSON，按目标列表同时推送给 WS 与 SSE，自动清理异常 WS 连接
- `presence`：连接建立后先向当前连接下发在线成员快照；当成员从“离线→在线”或“在线→离线”切换时，向所有在线 WS/SSE 连接广播 presence 事件
- WS 端点（`main.py`）：`?token=` 鉴权 → `hub.connect()` → 启动心跳任务 → 循环接收入站事件（`pong` / `ping` / `send`）→ 断开时 `hub.disconnect_and_broadcast()`
- SSE 端点（`main.py`）：`?token=` 鉴权 → 解析可选 `Last-Event-ID` / `last_event_id` → `hub.subscribe_events()` → 输出在线快照 → 按当前成员可见性补发缺失消息快照 → 按 `text/event-stream` 输出实时事件；空闲超过 `WS_PING_INTERVAL` 时输出 `ping` 事件；断开时 `hub.unsubscribe_events()`
- 推送格式：`{"type": "message", "payload": {MessageOut 字段}}`
- presence 格式：`{"type": "presence", "payload": {"online_ids": ["human:bobo", "agent:AI1"]}}`
- SSE 格式：
  ```text
  event: message
  data: {"id":1,"group_id":"group:lab",...}
  ```
  其中 `message / revoke` 会带 `id:` 字段，便于客户端做 Last-Event-ID / 去重扩展。
- SSE backfill 补发的是 `message` 事件快照；如果历史消息已撤回，补发 payload 会按 `MessageOut` 当前规则携带 `revoked=true` 并隐藏正文/文件快照字段。
- SSE 连接会先完成实时订阅再查询补发历史，降低重连窗口里的事件丢失风险；若同一事件同时进入补发结果和实时队列，服务端会按事件 id 去重。
- 心跳参数来自 `config.toml`：`ws_ping_interval` 默认 `20s`，`ws_ping_timeout` 默认 `45s`
- WS `send` 事件会复用消息模块的 `create_message()`，因此 mention 解析、文件消息校验、错误明细和 REST 保持一致；成功时只回广播消息本身，不额外发送成功 ack
- 浏览器端 `web/app.js` 已在收到 `ping` 时立即回 `pong`
- 已补 `tests/test_websocket.py`：通过 FastAPI `TestClient` 覆盖无效 token 拒绝、首次 presence 快照、上下线 presence 变更、心跳 ping/pong、超时断连、入站 `send` 成功与失败、广播消息全员送达、同一成员多连接送达、实时消息推送、`since` 去重对齐，以及断线后依赖 HTTP 轮询补历史的链路
- 已补 `tests/test_sse.py`：通过临时 uvicorn live server 覆盖 SSE 鉴权、presence 初始事件、消息事件、撤回事件与 SSE 连接清理

## 待改进点

- 无 WS 重连逻辑（客户端侧由前端 MODULE_webui 负责）
- Web UI 尚未接入 SSE；当前浏览器端仍使用 WebSocket + HTTP polling
- SSE 当前是只读事件流，不支持像 WS `send` 那样入站发送消息

## 验收标准

- [x] WS 连接成功建立并通过鉴权
- [x] 无效 token 连接被 close(4001) 拒绝
- [x] 发送定向消息后，目标成员的 WS 连接实时收到推送
- [x] 发送广播消息后，所有在线连接实时收到推送
- [x] 连接断开后从 Hub 中正确移除
- [x] 支持同一成员多个 WS 连接（多标签页场景）
- [x] 连接建立后当前连接能立即收到在线成员快照
- [x] 成员首次上线/最后下线时，所有在线连接都能收到 presence 更新
- [x] 服务端定期发送 `ping`，客户端 `pong` 后连接可持续存活
- [x] 超过 `ws_ping_timeout` 无任何入站帧时，服务端主动断开连接
- [x] 客户端可通过 `{"type":"send"}` 入站事件完成等价于 `POST /api/messages` 的消息发送
- [x] `send` 失败时返回 `send_ack` 且错误信息与 REST 错误语义一致
- [x] 已认证成员可建立 `GET /api/events?token=...` SSE 事件流
- [x] 无效 token 访问 SSE 返回 `401`
- [x] SSE 可收到 presence 初始事件
- [x] SSE 可收到目标成员可见的 message 事件
- [x] SSE 可收到目标成员可见的 revoke 事件
- [x] SSE 支持 `Last-Event-ID` / `last_event_id` 补发当前成员可见的历史消息快照
- [x] SSE 补发会过滤当前成员不可见消息，并保留撤回消息的当前快照语义
