# MODULE: Agent Bridges

> 所属项目：TALK
> 状态：通用 CLI bridge 第一版已落地，Codex bridge 保持兼容入口

## 目标

把外部 Agent 运行时接入 TALK，使它们以 `agent:*` 成员身份接收任务、调用本地模型/CLI/API 框架，并把结果发回 TALK。

## 负责范围

- 桥接脚本：`bridges/`
- 当前已实现：`bridges/cli_bridge.py`、`bridges/codex_bridge.py`
- 依赖 SDK：`TALK/client/`

## 当前实现

### 通用 CLI bridge

- `bridges/cli_bridge.py` 是通用 CLI bridge：负责 TALK 成员注册、实例状态上报、消息触发、任务队列轮询、任务认领、调用本地 CLI 命令、发送结果与完成任务状态。
- 默认要求通过 `--command` 传入本地 CLI 命令；该命令必须从 `stdin` 读取 TALK 生成的任务 prompt，并把最终回复写到 `stdout`。
- 可通过 `--name` 设置 Agent 成员名，例如 `pi` 会注册为 `agent:pi`；也可直接传完整 `agent:*`。
- 可通过 `--runtime` 设置实例上报 runtime，例如 `pi`、`codex`、`claude`。
- 可通过 `--bridge-label` 设置错误回复中的桥接名称，例如 `pi bridge`。
- 通用桥与 Codex 桥共享消息过滤、运行锁、任务队列、超时、回复截断和状态上报语义。

运行示例：

```bash
python bridges/cli_bridge.py --name pi --runtime pi --bridge-label "pi bridge" --key pi-key --base-url http://127.0.0.1:8000 --command "<pi CLI command that reads stdin>"
```

### Codex 兼容入口

- `bridges/codex_bridge.py` 会自注册为 `agent:codex`（可通过 `--name` 修改）。
- `bridges/codex_bridge.py` 现在复用通用 CLI bridge 实现，但保留原有 `--codex-command` 参数、默认 Codex 命令和 helper 函数兼容面。
- 默认只处理直接发给自己的文本消息，不自动响应普通广播消息。
- 启动后会通过实例 API 上报运行状态，默认实例 id 为 `agent:codex:<uuid>`，也可用 `--instance-id` 固定。
- 处理任务时状态从 `idle` 切到 `busy`，完成后回到 `idle`；命令失败、超时或异常时上报 `error`，进程退出前上报 `offline`。
- 默认同时轮询 `/api/tasks?target_member_id=<member_id>&status=queued`，按 `id` 从小到大认领属于自己的排队任务。
- 任务队列模式下，bridge 会通过 `/api/tasks/{id}/claim` 认领任务，调用 Codex CLI 后用直接文本消息把结果发给 `created_by`，再通过 `/api/tasks/{id}/complete` 写入 `succeeded / failed` 与 `result_message_id / last_error`。
- 消息触发与任务队列触发共用同一把运行锁，同一 bridge 实例不会并发启动多个 Codex CLI 进程。
- Codex 入口收到任务后调用可配置的 Codex CLI 命令，默认：

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
- 基于 `bridges/cli_bridge.py` 增加 `pi` 启动配置 / 示例脚本，用于 DeepSeek / Kimi；如果 pi CLI 的 stdin/stdout 协议不能直接适配，再补一层很薄的 pi adapter。

## 验收点

- [x] bridge helper 逻辑有单元测试覆盖。
- [x] 通用 CLI bridge 已抽出，可通过 `--name / --runtime / --command` 接入新的本地 CLI Agent。
- [x] Codex bridge 已接入任务队列 helper：可认领 queued task、运行 Codex、发送结果消息并完成任务状态。
- [x] `python bridges/cli_bridge.py --help` 可正常输出参数说明。
- [x] `python bridges/codex_bridge.py --help` 可正常输出参数说明。
- [x] 在临时 TALK server / 临时 SQLite / 临时 storage 中完成 `@agent:codex -> codex exec --sandbox read-only -> reply_to` 端到端验收，收到 `TALK_BRIDGE_SMOKE_OK`。
- [x] 在临时 TALK server 中验证 Codex bridge 实例状态路径：`idle -> busy -> idle -> offline`。
