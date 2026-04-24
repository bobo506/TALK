# MODULE: Agent SDK 示例

> 所属项目：TALK  
> 状态：SDK-1 已落地

## 目标

提供一个可直接运行的最小 Agent 示例，展示如何通过 `TALK/client/` SDK 以几十行代码接入 TALK 平台，而不再手写 HTTP 轮询脚手架。

## 负责范围

- SDK 包：`TALK/client/`
- 示例脚本：`examples/agent_sdk_demo.py`
- 详细 API 文档：`docs/SDK.md`

## 当前实现

- `TalkClient`：异步客户端，负责 HTTP 请求、WebSocket 事件接收、自动重连、断线期 HTTP 轮询补历史和消息去重
- `TalkClientSync`：同步薄包装，内部维护独立事件循环线程，给同步 Agent 使用
- 事件订阅：支持 `on_message`、`on_presence`、`on_revoke`
- 最小示例：`examples/agent_sdk_demo.py` 启动后自注册 `agent:<name>`，收到包含 `ping` 的文本消息时回 `pong`

## 关键约束

- HTTP 请求统一自动携带 `X-API-Key`
- WebSocket 只负责接收事件；主动发消息仍通过 HTTP，减少状态分叉
- WebSocket 掉线后自动切到 `GET /api/messages?since=...&to=<member_id>` 轮询
- 轮询与 WebSocket 并发期间按最近 N 条 `message.id` 去重
- `reply_to` 参数已为未来协议预留，但当前服务端未支持，传入非空会报 `TalkValidationError`

## 示例用法

```bash
python examples/agent_sdk_demo.py --name demo --key demo-key
```

本地联调链路：

1. 启动 TALK server
2. 启动示例 Agent
3. 在 Web UI 发送 `@agent:demo ping`
4. 看到 Agent 回复 `pong`

## 验收点

- [x] 示例脚本使用 SDK 而非手写轮询
- [x] 示例脚本可本地自注册并跑通 `ping -> pong`
- [x] SDK 覆盖文本发送、文件发送、文件下载、撤回、成员查询、历史拉取
- [x] SDK 支持 WebSocket 事件、自动重连、轮询降级和去重
- [x] 详细 API 说明已收敛到 `docs/SDK.md`
