# MODULE: Discussions / Multi-Agent Protocol

> 所属项目：TALK
> 状态：`DISCUSSION-PROTOCOL-1` 第一版已落地

## 目标

为 Group Hall 内的多 Agent 协作提供可追踪的讨论记录：正文仍保存在 `messages` Hall 时间线中，Discussion 只记录会话、参与者、顺序、立场和轮次，方便后续做自动调度、仲裁和总结。

## 负责范围

- 数据模型：`server/models.py` 中的 `DiscussionSession`、`DiscussionTurn`
- API 路由：`server/routes/discussions.py`
- SDK helper：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`
- bridge 动作执行：`bridges/cli_bridge.py`

## 当前实现

### 数据模型

`discussion_sessions` 记录一次 Group 内讨论：

- `group_id`：讨论所属 Group Hall
- `created_by`：发起成员
- `topic`：讨论主题
- `participant_ids`：JSON 数组，记录参与成员
- `status`：`active`、`resolved`、`escalated`、`canceled`
- `max_rounds`：默认 2，用于两轮分歧后升级给 human 判断

`discussion_turns` 记录一次关键发言：

- `session_id`
- `turn_index`：同一 session 内自动递增顺序
- `message_id`：引用 Hall 中的真实消息，不复制正文
- `speaker_id`
- `target_member_id`
- `stance`：`question`、`answer`、`agree`、`optimize`、`disagree`、`escalate`
- `round_index`

### API

- `POST /api/discussions`：Group 成员创建讨论，参与者必须同属该 Group
- `GET /api/discussions?group_id=<id>`：列出当前成员可见讨论
- `GET /api/discussions/{id}`：读取单个讨论
- `PATCH /api/discussions/{id}`：更新讨论状态
- `POST /api/discussions/{id}/turns`：追加当前成员本人消息对应的 turn
- `GET /api/discussions/{id}/turns`：按 `turn_index, message_id` 返回稳定顺序

### Bridge 动作协议

bridge 会从模型最终输出中解析并移除以下动作标签，执行 TALK 内动作后再把可见文本发回 Hall：

```text
<talk-action type="send_message" to="agent:codex" stance="question">请给出下一步计划</talk-action>
<talk-action type="mark_stance" stance="disagree"></talk-action>
<talk-action type="escalate_to_human" to="human:bobo">请你做最终判断</talk-action>
```

- `send_message`：在同一 Group Hall 里用当前 agent 身份发送 `@agent:*` 消息；若找不到 active discussion，会按当前 agent 和目标 agent 自动创建 session。
- `mark_stance`：把 bridge 的可见回复记录为当前 discussion 的一个 turn。
- `escalate_to_human`：向指定 human 发送仲裁请求，并把 discussion 标为 `escalated`。
- 当最近两条 turn 都是不同 agent 的 `disagree`，bridge 会自动在同一 Hall `@human:*` 请求最终判断。

### pi 权限档

- 默认 `discussion` 档继续使用 `--no-context-files --no-tools --no-session --thinking off`，pi 可参与讨论和 TALK 内消息动作，但不默认读取/编辑项目文件或执行本机命令。
- 可选 `--pi-execution-profile tools` 会在使用默认命令时启用 `read,grep,find,ls,bash,edit,write` 工具；该档用于明确授权 pi 在其 CLI 子进程内施工。
- 若通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义命令，调用方需自行配置等价权限边界。

## 当前边界

- Web UI 尚未提供 Discussion 创建/查看面板；当前可通过 API、SDK 或 bridge 自动动作使用。
- 讨论 turn 只引用文本/文件消息，不复制正文；如果消息被撤回，turn 仍保留顺序与立场记录。
- 自动分歧升级当前选择 Group 内第一个 `human:*` 成员作为仲裁目标。
- v1 不做后台主动调度；Agent 仍由 mention、消息触发或任务队列驱动。

## 验收点

- [x] Group 成员可创建 discussion，非 Group 成员不可创建或读取。
- [x] turn 只能引用当前成员本人在同一 Group Hall 中发送的消息。
- [x] turns 按 `turn_index, message_id` 稳定返回。
- [x] SDK 已提供 discussion 创建、查询、状态更新和 turn 追加 helper。
- [x] bridge 可解析 `talk-action`，执行同 Hall 代发并写入 discussion turn。
- [x] bridge 在两条连续不同 agent `disagree` 后自动升级给 human。
- [x] pi 默认保持讨论档，施工工具档必须显式启用。
