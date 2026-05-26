# MODULE: Agent Bridges

> 所属项目：TALK
> 状态：通用 CLI bridge 第一版已落地，Codex / pi bridge 保持专用入口

## 目标

把外部 Agent 运行时接入 TALK，使它们以 `agent:*` 成员身份接收任务、调用本地模型/CLI/API 框架，并把结果发回 TALK。

## 负责范围

- 桥接脚本：`bridges/`
- 当前已实现：`bridges/cli_bridge.py`、`bridges/codex_bridge.py`、`bridges/pi_bridge.py`
- 依赖 SDK：`TALK/client/`

## 当前实现

### 通用 CLI bridge

- `bridges/cli_bridge.py` 是通用 CLI bridge：负责 TALK 成员注册、实例状态上报、消息触发、任务队列轮询、任务认领、调用本地 CLI 命令、发送结果与完成任务状态。
- 默认要求通过 `--command` 传入本地 CLI 命令；该命令应把最终回复写到 `stdout`。
- prompt 传递支持两种方式：`--prompt-transport stdin` 会通过标准输入传入任务 prompt；`--prompt-transport argv` 会把任务 prompt 追加为最后一个命令行参数。
- 可通过 `--name` 设置 Agent 成员名，例如 `pi` 会注册为 `agent:pi`；也可直接传完整 `agent:*`。
- 可通过 `--runtime` 设置实例上报 runtime，例如 `pi`、`codex`、`claude`。
- 可通过 `--bridge-label` 设置错误回复中的桥接名称，例如 `pi bridge`。
- 通用桥与 Codex 桥共享消息过滤、运行锁、任务队列、超时、回复截断和状态上报语义。
- 子进程输出会逐行优先按 UTF-8 解码，并在 Windows 下兜底尝试系统代码页，避免本地 CLI / 系统工具输出中文时出现替换字符乱码或不同输出行互相拖累编码判断。
- bridge 会过滤 Windows `taskkill` 进程清理提示，避免 Codex CLI 退出时的进程管理噪声混入前端聊天回复。
- bridge prompt 现在明确要求接入 agent 以 TALK Group Hall 参与者身份行动，而不是把自己当作 TALK 管理员或功能说明书。
- 模型最终输出中的安全行协议 `TALK_ACTION ...` 会被 bridge 解析为 TALK 内动作；旧 `<talk-action ...>` 标签仍兼容解析，动作行不会出现在最终可见聊天正文中。
- bridge 会把消息开头连续 `@member_id` 块视为 Group Hall 路由头，传给 CLI 的任务正文会剥掉整段路由头；正文中间的 `@agent:*` 保留为普通文本提及。
- CLI 非 0 退出或超时时，bridge 给聊天里只发送简短失败提示，不回显 `stderr / stdout / traceback / 本地路径`；详细错误只保留在任务或实例错误记录中。
- 若模型把 malformed 动作协议、控制语法或内部字段残留在可见正文中，bridge 会隔离该回复，替换为确认范围的简短自然语言，避免把协议片段展示给 human 或其它 agent。
- `send_message` 动作会在同一 Group Hall 中代表当前 agent 发送 `@agent:*` 消息，并自动创建或复用 active discussion 记录 turn。
- `send_message` 动作的目标必须是当前 Group 内存在的 `agent:*` 成员；目标不存在或不在 Group 内时不发送，并向直接请求者给出简短说明。
- `mark_stance` 动作用于把当前回复标记为 `answer / agree / optimize / disagree / greeting / closure` 等讨论立场；连续两条不同 agent 的 `disagree` 会自动 `@human:*` 请求最终判断。
- `final_to_human` 动作用于把达成共识后的最终答案发送给 human，并将 discussion 标为 `resolved`。
- `escalate_to_human` 动作可显式向指定 `human:*` 成员发起仲裁，并将 discussion 标记为 `escalated`。
- agent-to-agent 讨论现在默认最多 3 个实质自动 turn；`greeting / closure` 这类非实质 turn 不计入收口阈值。普通轻扩展允许对方再回答 1 个实质 turn，之后由收到回复的一方自动收口并标记 `resolved`；最近一条为 `disagree` 时仍允许额外 1 个实质 turn 并在超限后升级给 human。
- agent-to-agent prompt 会注入“请求者局部范围”控制上下文，约束模型只围绕当前直接提问/派活者的请求回答，避免把 docs、版本号、施工档或其它无关上下文卷入讨论。
- 控制上下文包含 `discussion_id / root_message_id / requester_id / assignee_id / scope_text` 等字段，只用于约束模型；bridge 会拦截这些内部字段泄漏到可见回复。
- bridge 会优先沿 `reply_to` / `root_message_id` 复用 discussion scope；已结束 scope 不会因为普通 agent 回复继续触发模型续聊。
- agent 普通可见回复若属于 active discussion，即使没有显式 `mark_stance`，也会记录 turn；明确的打招呼/在线确认类短回复会记录为 `greeting`，其它普通回复默认记录为 `answer`。
- 当模型只输出动作且来源是另一个 agent 时，bridge 不再额外发送默认回执，避免 action-only 回执继续触发对方 bridge。

运行示例：

```bash
python bridges/cli_bridge.py --name pi --runtime pi --bridge-label "pi bridge" --key pi-key --base-url http://127.0.0.1:8000 --command "<pi CLI command that reads stdin>"
```

### Codex 兼容入口

- `bridges/codex_bridge.py` 会自注册为 `agent:codex`（可通过 `--name` 修改）。
- `bridges/codex_bridge.py` 现在复用通用 CLI bridge 实现，但保留原有 `--codex-command` 参数、默认 Codex 命令和 helper 函数兼容面。
- 默认只处理直接发给自己的文本消息，不自动响应普通广播消息。
- Group Hall 中直接 `@agent:codex` 的文本消息也会被处理；bridge 回复会保留原消息的 `group_id`，因此回复写回同一个 Hall，而不是落到全局 direct 流。
- 启动后会通过实例 API 上报运行状态，默认实例 id 为 `agent:codex:<uuid>`，也可用 `--instance-id` 固定。
- 处理任务时状态从 `idle` 切到 `busy`，完成后回到 `idle`；命令失败、超时或异常时上报 `error`，进程退出前上报 `offline`。
- 默认同时轮询 `/api/tasks?target_member_id=<member_id>&status=queued`，按 `id` 从小到大认领属于自己的排队任务。
- 任务队列模式下，bridge 会通过 `/api/tasks/{id}/claim` 认领任务，调用 Codex CLI 后用直接文本消息把结果发给 `created_by`，再通过 `/api/tasks/{id}/complete` 写入 `succeeded / failed` 与 `result_message_id / last_error`。
- 消息触发与任务队列触发共用同一把运行锁，同一 bridge 实例不会并发启动多个 Codex CLI 进程。
- Codex 入口收到任务后调用可配置的 Codex CLI 命令，默认：

```bash
codex exec --skip-git-repo-check --sandbox workspace-write --color never -
```

- bridge 通过 stdin 把 TALK 任务传给 Codex，并把 Codex 输出作为 `reply_to` 回复给原发送者；若原消息属于 Group Hall，则同时携带相同 `group_id`。
- 命令、工作目录、超时、回复最大长度、是否响应广播、是否先发 ACK 都可通过 CLI 参数配置。
- 任务队列轮询间隔可通过 `--task-poll-interval` 配置；如只想保留旧的消息触发模式，可用 `--disable-task-queue` 关闭。

### pi 兼容入口

- `bridges/pi_bridge.py` 会自注册为 `agent:pi`（可通过 `--name` 修改）。
- `bridges/pi_bridge.py` 复用通用 CLI bridge 实现，默认 runtime 为 `pi`，默认错误标签为 `pi bridge`。
- 本机已确认 `pi` CLI 支持 `--print` 非交互模式，版本为 `0.74.1`。
- 默认 pi 命令为：

```bash
pi --print --mode text --no-context-files --no-tools --no-session --thinking off --system-prompt "<short TALK chat boundary>"
```

- 因 `pi --print` 接收 prompt 参数而非 stdin，pi 入口默认使用 `--prompt-transport argv`，即把 TALK 任务 prompt 追加为最后一个命令行参数。
- Group Hall 中直接 `@agent:pi` 的文本消息也会被处理；bridge 回复会保留原消息的 `group_id`，因此回复写回同一个 Hall。
- pi 默认入口只保留运行隔离：禁止自动加载 `AGENTS.md` / `CLAUDE.md` 上下文文件，禁止工具调用，不保存/恢复会话，并关闭 thinking，以减少回复延迟和避免把普通聊天误输出成项目状态报告。
- pi 默认命令使用中文 `--system-prompt` 放置 Group Hall 参与者身份、讨论协议和 TALK 动作边界，避免边界说明混入用户消息正文。
- pi 的 TALK prompt 现在只传去掉开头连续 `@member_id` 路由头后的用户原文；队列任务默认只传 `content`，有 `title` 时传 `标题：<title>\n\n<content>`。
- pi prompt 不再包含 `用户消息`、`回复要求`、`Sender`、`TALK message id` 或 `TALK group id` 等包装文本；但 bridge 回复仍会保留原消息 `group_id`，确保 Group Hall 回复写回同一个 Hall。
- 默认 system prompt 要求 pi 是 TALK Group Hall 参与者，可与人类和其他 agent 交流、评审方案、提出优化/分歧，并在需要时输出 `TALK_ACTION` 安全行协议；默认讨论模式下不声称能读取项目文件、执行命令或编辑文件。
- 默认 system prompt 不再包含原始 `<talk-action ...>` 示例、斜杠、竖线、尖括号或 `&`，避免 Windows 下 `pi.cmd` 启动链把 prompt 误解释为命令管道或重定向。
- 可通过 `--pi-execution-profile tools` 在使用默认命令时显式启用 `read,grep,find,ls,bash,edit,write` 工具，让 pi CLI 子进程具备可施工能力；默认 `discussion` 档不启用工具。
- 当 pi 在中文能力/自我介绍问题上成功返回明显非中文、阿拉伯语语言标签或错误声称自己可读文件/执行命令时，通用 bridge 会把回复兜底替换为中文能力说明；正常中文回复或用户明确要求英文时不干预。
- 当用户任务中明确包含“一句话 / one sentence / single sentence”等约束时，通用 bridge 会在成功回复后做一层兜底收敛，只回传第一句或第一行，避免模型忽略简短回复要求。
- 可通过 `TALK_PI_COMMAND` 或 `--pi-command` 覆盖默认命令，例如切到 DeepSeek / Kimi provider。
- 如果覆盖 `TALK_PI_COMMAND` / `--pi-command`，需要自行保留等价上下文、session、工具权限和 `--system-prompt` 边界；否则 pi 可能重新读取项目上下文、错误启用工具或重新把自己当成 coding assistant。

## 运行示例

```bash
python bridges/codex_bridge.py --key codex-key --base-url http://127.0.0.1:8000
python bridges/pi_bridge.py --key pi-key --base-url http://127.0.0.1:8000
```

Web UI 中发送：

```text
@agent:codex 总结一下当前项目结构
@agent:pi 总结一下当前项目结构
```

## 后续计划

- 完善 Group / Hall 历史上下文读取，让 Agent 可按需看到同一 Hall 的近期消息。
- 为 Group Hall 的 HTTP fallback 轮询补充 Agent group cursor；当前 Group 触发主要依赖 WebSocket 实时推送。
- 接入 SSE 流式输出。
- 接入文档编辑锁协议，避免多个 Agent 同时写同一文件。
- 增加双 Agent 最小回合验收脚本：同时启动 Codex / pi bridge，验证 `agent:codex` 与 `agent:pi` 可在 TALK 中完成一轮消息或任务往返。
- 将 Discussion Session / Turn 状态接入 Web UI，显示多 Agent 讨论轮次、立场和升级仲裁提示。

## 验收点

- [x] bridge helper 逻辑有单元测试覆盖。
- [x] 通用 CLI bridge 已抽出，可通过 `--name / --runtime / --command` 接入新的本地 CLI Agent。
- [x] 通用 CLI bridge 支持 `stdin` 与 `argv` 两种 prompt 传递方式。
- [x] Codex bridge 已接入任务队列 helper：可认领 queued task、运行 Codex、发送结果消息并完成任务状态。
- [x] pi bridge 已落地：默认调用 `pi --print --mode text`，通过 argv 传入 TALK prompt。
- [x] `python bridges/cli_bridge.py --help` 可正常输出参数说明。
- [x] `python bridges/codex_bridge.py --help` 可正常输出参数说明。
- [x] `python bridges/pi_bridge.py --help` 可正常输出参数说明。
- [x] 在临时 TALK server / 临时 SQLite / 临时 storage 中完成 `@agent:codex -> codex exec --sandbox read-only -> reply_to` 端到端验收，收到 `TALK_BRIDGE_SMOKE_OK`。
- [x] 在临时 TALK server 中验证 Codex bridge 实例状态路径：`idle -> busy -> idle -> offline`。
- [x] 通用 CLI bridge 在处理 Group Hall 消息时会把回复写回原 `group_id`，避免触发 `cannot_reply_to_different_group`。
- [x] 通用 CLI bridge 已对 Windows 本地 CLI 输出做编码兜底和 `taskkill` 噪声过滤，避免 Codex 在线回复前出现乱码进程终止提示。
- [x] pi bridge 默认通过极短 `--system-prompt` 放置身份/能力边界，并把用户 prompt 收敛为原文，避免包装文本干扰 pi 的自然回复。
- [x] bridge 已支持安全行动作协议：代发 `@agent:*`、记录 stance、发送最终答案、回合上限与升级 human。
- [x] bridge 已支持请求者局部范围约束：scope 记录、reply/root 复用、已结束 scope 停止续聊和内部字段泄漏拦截。
- [x] pi bridge 默认保持讨论档，并提供显式 `--pi-execution-profile tools` 施工工具档。
