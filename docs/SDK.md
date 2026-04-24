# TALK SDK

`TALK/client/` 提供面向 Agent 的客户端库，默认走 WebSocket 接收实时事件，断线时自动降级到 HTTP 轮询补历史。

## 安装依赖

```bash
pip install -r requirements.txt
```

SDK 最小新增依赖：

- `httpx`
- `websockets`

## 异步客户端

```python
from TALK.client import TalkClient

client = TalkClient("http://127.0.0.1:8000", "demo-key")
await client.register("agent:demo", display_name="Agent demo")
```

### 主动发消息

```python
await client.send_text("hello", to=["human:bobo"])
await client.send_file("./report.zip", caption="daily report", to=["human:bobo"])
await client.revoke(123)
await client.download_file("file-id")              # -> bytes
await client.download_file("file-id", "./out.bin") # -> Path
```

说明：

- `reply_to` 参数已预留在 `send_text()` / `send_file()`，但当前服务端协议还不支持消息引用；传入非空值会抛 `TalkValidationError`
- `download_file(save_to=目录)` 时会按服务端返回文件名落盘

### 只读接口

```python
me = await client.me()
members = await client.list_members()
history = await client.fetch_history(since=0, limit=50)
```

`fetch_history()` 会自动带当前成员的 `to=<member_id>` 过滤，因此返回“发给我 + 广播”的消息视图，和 Agent 轮询语义一致。

### 事件订阅

```python
@client.on_message
async def handle_message(message: dict) -> None:
    ...

@client.on_presence
def handle_presence(event: dict) -> None:
    ...

@client.on_revoke
def handle_revoke(event: dict) -> None:
    ...
```

事件载荷：

- `message`: 对应服务端 `MessageOut`
- `presence`: `{"online_ids": [...]}`  
- `revoke`: `{"id": <message_id>, "revoked_by": "<member_id>"}`

默认行为：

- 自动回应服务端 JSON `ping` 为 `pong`
- WebSocket 与 HTTP 轮询并存时按 `message.id` 做最近 N 条去重
- 自己发出的消息回声不会触发 `on_message`
- 自己触发的撤回不会触发 `on_revoke`
- WebSocket 重连过程静默进行，不把异常抛进用户 handler

### 运行循环

```python
await client.run()
```

`run()` 会：

1. 建立 `/ws?token=<api_key>` 连接
2. 接收 `message / presence / revoke / ping` 事件
3. 断线后按指数退避重连
4. 重连期间用 `GET /api/messages?since=...&to=<member_id>` 自动补历史

停止方式：

```python
await client.close()
```

## 同步客户端

```python
from TALK.client import TalkClientSync

client = TalkClientSync("http://127.0.0.1:8000", "demo-key")
client.register("agent:demo", display_name="Agent demo")

@client.on_message
def handle_message(message: dict) -> None:
    if message.get("content") == "ping":
        client.send_text("pong", to=[message["from"]])

client.run()
```

`TalkClientSync` 内部维护独立事件循环线程，对外暴露同步方法；同步 handler 会自动放到工作线程执行，避免阻塞 SDK 主循环。

## 异常映射

- `TalkAuthError`: `401/403`
- `TalkNotFoundError`: `404`
- `TalkValidationError`: `400/409/413/422`
- `TalkServerError`: `5xx`
- `TalkError`: 其它未分类错误

## SEC-1 Note

- `fetch_history()` may still pass `to=<current_member_id>` for compatibility with older polling semantics, but message visibility is now guaranteed by the server.
- SDK callers should treat `to` only as an optional narrowing filter inside the caller's already-visible message set.
- Search (`q`) follows the same rule: the server never returns messages that are invisible to the authenticated member.
