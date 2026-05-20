# MODULE: Agent Bridges

> 所属项目：TALK
> 状态：Codex bridge MVP 已落地

## 目标

把外部 Agent 运行时接入 TALK，使它们以 `agent:*` 成员身份接收任务、调用本地模型/CLI/API 框架，并把结果发回 TALK。

## 负责范围

- 桥接脚本：`bridges/`
- 当前已实现：`bridges/codex_bridge.py`
- 依赖 SDK：`TALK/client/`

## 当前实现

- `bridges/codex_bridge.py` 会自注册为 `agent:codex`（可通过 `--name` 修改）。
- 默认只处理直接发给自己的文本消息，不自动响应普通广播消息。
- 启动后会通过实例 API 上报运行状态，默认实例 id 为 `agent:codex:<uuid>`，也可用 `--instance-id` 固定。
- 处理任务时状态从 `idle` 切到 `busy`，完成后回到 `idle`；命令失败、超时或异常时上报 `error`，进程退出前上报 `offline`。
- 默认同时轮询 `/api/tasks?target_member_id=<member_id>&status=queued`，按 `id` 从小到大认领属于自己的排队任务。
- 任务队列模式下，bridge 会通过 `/api/tasks/{id}/claim` 认领任务，调用 Codex CLI 后用直接文本消息把结果发给 `created_by`，再通过 `/api/tasks/{id}/complete` 写入 `succeeded / failed` 与 `result_message_id / last_error`。
- 消息触发与任务队列触发共用同一把运行锁，同一 bridge 实例不会并发启动多个 Codex CLI 进程。
- 收到任务后调用可配置的 Codex CLI 命令，默认：

```bash
codex exec --skip-git-repo-check --sandbox workspace-write --color never -
```

- bridge 通过 stdin 把 TALK 任务传给 Codex，并把 Codex 输出作为 `reply_to` 回复给原发送者。
- 命令、工作目录、超时、回复最大长度、是否响应广播、是否先发 ACK 都可通过 CLI 参数配置。
- 任务队列轮询间隔可通过 `--task-poll-interval` 配置；如只想保留旧的消息触发模式，可用 `--disable-task-queue` 关闭。

## 运行示例

```bash
python bridges/codex_bridge.py --key codex-key --base-url http://127.0.0.1:8000
```

Web UI 中发送：

```text
@agent:codex 总结一下当前项目结构
```

## 后续计划

- 接入 Group / Hall 消息上下文。
- 接入 SSE 流式输出。
- 接入文档编辑锁协议，避免多个 Agent 同时写同一文件。
- 增加 `pi` bridge，用于 DeepSeek / Kimi。

## 验收点

- [x] bridge helper 逻辑有单元测试覆盖。
- [x] Codex bridge 已接入任务队列 helper：可认领 queued task、运行 Codex、发送结果消息并完成任务状态。
- [x] `python bridges/codex_bridge.py --help` 可正常输出参数说明。
- [x] 在临时 TALK server / 临时 SQLite / 临时 storage 中完成 `@agent:codex -> codex exec --sandbox read-only -> reply_to` 端到端验收，收到 `TALK_BRIDGE_SMOKE_OK`。
- [x] 在临时 TALK server 中验证 Codex bridge 实例状态路径：`idle -> busy -> idle -> offline`。
