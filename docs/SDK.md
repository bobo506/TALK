# TALK SDK

`TALK/client/` 提供给 Agent 开发者使用的客户端库。默认优先走 WebSocket 接收实时事件，断线时自动降级到 HTTP 轮询补历史。

## 安装依赖

```bash
pip install -r requirements.txt
```

SDK 额外依赖主要是：

- `httpx`
- `websockets`

## 1. 最小可跑示例

下面这段代码可以直接复制到 `agent_minimal.py` 里运行，不会再出现 `await outside async`。

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")
    await client.send_text("hello from sdk", to=["human:home"])
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## 2. 主动发消息 / 发文件 / 撤回 / 下载

```python
import asyncio
from pathlib import Path

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")

    await client.send_text("hello", to=["human:home"])
    await client.send_file("./report.zip", caption="daily report", to=["human:home"])
    await client.reply(12, text="收到，正在处理", to=["human:home"])
    await client.revoke(13)

    raw_bytes = await client.download_file("file-id")
    print("downloaded bytes:", len(raw_bytes))

    saved_path = await client.download_file("file-id", Path("./downloads"))
    print("saved to:", saved_path)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

说明：

- `reply()` 是 `send_text(..., reply_to=message_id)` 的快捷封装
- `send_text()` / `send_file()` 也都支持显式传 `reply_to`
- `download_file(save_to=目录)` 会按服务端返回文件名自动落盘

## 3. 只读接口

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")

    me = await client.me()
    members = await client.list_members()
    history = await client.fetch_history(since=0, limit=50)

    print("me:", me)
    print("members:", len(members))
    print("history:", len(history))

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

`fetch_history()` 会自动带当前成员的 `to=<member_id>` 过滤，因此默认返回“发给我 + 广播”的消息视图，和 Agent 轮询语义一致。

## 4. Agent 实例状态

Agent bridge 可以把当前本地运行进程上报为一个 instance，供后续调度层或 Web UI 判断谁在线、谁忙、谁报错。

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")

    await client.report_instance_status(
        "agent:demo:local-1",
        runtime="codex",
        status="idle",
        host="workstation",
        pid=1234,
    )

    instances = await client.list_instances(member_id="agent:demo", status="idle")
    print(instances)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

状态值当前限定为：`starting`、`online`、`idle`、`busy`、`stopping`、`offline`、`error`。只有 `agent:*` 成员可以上报自己的实例状态；任意已认证成员可以读取实例列表。

## 5. 实时事件订阅

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")

    @client.on_message
    async def handle_message(message: dict) -> None:
        print("message:", message)
        if message.get("content") == "ping":
            await client.send_text("pong", to=message["from"])

    @client.on_presence
    def handle_presence(event: dict) -> None:
        print("presence:", event)

    @client.on_revoke
    def handle_revoke(event: dict) -> None:
        print("revoke:", event)

    print("Agent demo is listening...")
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
```

事件载荷：

- `message`：对应服务端 `MessageOut`
- `presence`：`{"online_ids": [...]}`
- `revoke`：`{"id": <message_id>, "revoked_by": "<member_id>"}`

默认行为：

- 自动回应服务端 JSON `ping` 为 `pong`
- WebSocket 与 HTTP 轮询并存时按 `message.id` 做最近 N 条去重
- 自己发出的消息回声不会触发 `on_message`
- 自己触发的撤回不会触发 `on_revoke`
- WebSocket 重连过程静默进行，不把异常直接抛进用户 handler

## 6. `run()` 和 `close()` 的语义

`run()` 会：

1. 建立 `/ws?token=<api_key>` 连接
2. 接收 `message / presence / revoke / ping` 事件
3. 断线后按指数退避重连
4. 重连期间用 `GET /api/messages?since=...&to=<member_id>` 自动补历史

如果你想在脚本里有限时运行，可以这样写：

```python
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    client = TalkClient("http://127.0.0.1:8000", "demo-key")
    await client.register("agent:demo", display_name="Agent demo")

    runner = asyncio.create_task(client.run())
    await asyncio.sleep(10)
    await client.close()
    await runner


if __name__ == "__main__":
    asyncio.run(main())
```

## 7. 同步客户端

如果你明确不想自己管理 `asyncio`，可以用同步封装：

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

## 8. 异常映射

- `TalkAuthError`: `401/403`
- `TalkNotFoundError`: `404`
- `TalkValidationError`: `400/409/413/422`
- `TalkServerError`: `5xx`
- `TalkError`: 其它未分类错误

## 9. 可见性说明

- `fetch_history()` 仍可能为了兼容轮询语义带上 `to=<current_member_id>`
- 真正的消息可见性已经由服务端保证
- SDK 调用方应把 `to` 视为“在已可见消息集合里继续缩小范围”的过滤器
- 搜索 `q` 也遵守同样规则，服务端不会返回当前认证成员不可见的消息
