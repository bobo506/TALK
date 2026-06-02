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
- `root_message_id`：可选，本轮讨论范围的起点消息；旧记录可为空
- `requester_id`：可选，当前范围里提出要求的成员，可以是 human，也可以是 agent
- `assignee_id`：可选，当前范围里被要求回复/执行的成员
- `scope_text`：可选，去掉开头 mention 后的任务范围文本；作为模型控制上下文，不应直接展示在可见回复中
- `status`：`active`、`resolved`、`escalated`、`canceled`
- `max_rounds`：默认 2，用于两轮分歧后升级给 human 判断

`discussion_turns` 记录一次关键发言：

- `session_id`
- `turn_index`：同一 session 内自动递增顺序
- `message_id`：引用 Hall 中的真实消息，不复制正文
- `speaker_id`
- `target_member_id`
- `turn_kind`：`demand` 或 `reply`；`demand` 表示一次新需求，`reply` 表示一次可见回复
- `stance`：`question`、`answer`、`agree`、`optimize`、`disagree`、`escalate`、`greeting`、`closure`
- `round_index`：仅 `demand` turn 推进扩展轮次；历史记录和 visible reply 默认记为 `reply`

### API

- `POST /api/discussions`：Group 成员创建讨论，参与者必须同属该 Group
- `GET /api/discussions?group_id=<id>`：列出当前成员可见讨论
- `GET /api/discussions/{id}`：读取单个讨论
- `PATCH /api/discussions/{id}`：更新讨论状态
- `POST /api/discussions/{id}/turns`：追加当前成员本人消息对应的 turn
- `GET /api/discussions/{id}/turns`：按 `turn_index, message_id` 返回稳定顺序

### Bridge 动作协议

bridge 会从模型最终输出中解析并移除动作指令，执行 TALK 内动作后再把可见文本发回 Hall。当前推荐使用无 Windows 高风险命令元字符的安全行协议：

```text
TALK_ACTION send_message to=agent:codex stance=question body=请给出下一步计划
TALK_ACTION mark_stance stance=agree
TALK_ACTION final_to_human to=human:bobo body=这是整理后的最终答案
TALK_ACTION escalate_to_human to=human:bobo body=请你做最终判断
```

为兼容已有 bridge 输出，旧 XML 标签仍可解析，但 pi 默认 system prompt 只教授安全行协议：

```text
<talk-action type="send_message" to="agent:codex" stance="question">请给出下一步计划</talk-action>
<talk-action type="mark_stance" stance="disagree"></talk-action>
<talk-action type="escalate_to_human" to="human:bobo">请你做最终判断</talk-action>
```

- `send_message`：在同一 Group Hall 里用当前 agent 身份发送 `@agent:*` 消息；目标必须是当前 Group 内存在的 `agent:*` 成员。若找不到可复用 discussion，会按当前请求者、目标 agent 和发出的消息自动创建带范围锚点的 session。
- `mark_stance`：把 bridge 的可见回复记录为当前 discussion 的一个 turn。
- `final_to_human`：把共识后的最终答案发送给指定 human，并把 discussion 标为 `resolved`。
- `escalate_to_human`：向指定 human 发送仲裁请求，并把 discussion 标为 `escalated`。
- 当最近两条 turn 都是不同 agent 的 `disagree`，或自动讨论回合达到上限，bridge 会自动在同一 Hall `@human:*` 请求最终判断。

### 请求者局部范围与有限状态控制

- 讨论范围不固定绑定 human，而是绑定“当前直接提问/派活者”的请求：谁提出要求，回复者就围绕谁的这条要求回复。
- bridge 会优先沿 `reply_to` / `root_message_id` 找到候选 discussion scope；`reply_to` 只作为 UI 引用和定位辅助，不承担“需求/回复/轮次”的协议状态。已 `resolved / escalated / canceled` 的 scope 不会因为普通 agent 回复而继续触发模型续聊。
- agent-to-agent prompt 会注入控制上下文：`discussion_id / root_message_id / requester_id / assignee_id / scope_text / current_message_id` 等字段。这些字段只用于约束模型，禁止出现在可见聊天回复中。
- 如果模型可见回复泄漏内部字段名、控制上下文或 malformed 动作协议残留，bridge 会替换为“我需要先确认当前请求范围后再继续。”，避免把内部 ID 或协议片段暴露给用户或其它 agent。
- agent 普通可见回复若属于 active discussion，即使没有显式 `mark_stance`，也会记录一个 `turn_kind=reply` 的 turn；明确的打招呼/在线确认类短回复会记录为 `greeting`，其它普通回复通过 `infer_reply_stance()` 显式兜底为 `answer`，便于后续 UI 展示讨论轮次。
- function-calling `talk_send` 成功发送后会创建或复用 discussion，并追加 `turn_kind=demand`。bridge 通过当前 session 里最大的 `demand.round_index` 判断是否继续暴露 `TALK_DEFERRED_FILE`：小于 2 才允许扩展，达到 2 后只允许回复、收口或升级 human。
- 讨论按 `question -> answer -> agree/optimize/disagree -> resolved/escalated` 推进，默认只允许 3 个实质自动 turn。`greeting / closure` 不计入收口阈值，避免把打招呼和在线确认误算成议题讨论。普通轻扩展允许对方再回答 1 个实质 turn，随后由收到回复的一方自动发出稳定但按 agent 区分的话术并标记 `closure/resolved`；最近一条为 `disagree` 时允许额外 1 个实质 turn 供对方回应，超限后仍升级 human。
- agent-to-agent prompt 会明确禁止引入与当前请求范围无关的项目、文档、版本号或施工档内容；想引申但不确定是否仍在范围内时，默认先向请求者追问确认。
- 当模型只输出动作且来源是另一个 agent 时，bridge 不再额外发送“已按讨论协议继续推进。”这类默认回执，避免无意义消息继续触发对方 bridge。
- bridge 会清理开头或结尾的孤立协议残片，例如 `mark_stance`、`update`、`动作已记录...`，避免动作词泄漏到可见聊天正文。
- bridge 会把消息开头连续 `@member_id` 块视为路由头并从模型任务正文中剥离；正文中间的 `@agent:*` 仍保留为普通提及。

### pi 权限档

- 默认 `discussion` 档继续使用 `--no-context-files --no-tools --no-session --thinking off`，pi 可参与讨论和 TALK 内消息动作，但不默认读取/编辑项目文件或执行本机命令。
- 可选 `--pi-execution-profile tools` 会在使用默认命令时启用 `read,grep,find,ls,bash,edit,write` 工具；该档用于明确授权 pi 在其 CLI 子进程内施工。
- 若通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义命令，调用方需自行配置等价权限边界。

## 当前边界

- Web UI 尚未提供 Discussion 创建/查看面板；当前可通过 API、SDK 或 bridge 自动动作使用。
- 讨论 turn 只引用文本/文件消息，不复制正文；如果消息被撤回，turn 仍保留顺序与立场记录。
- 自动分歧升级当前选择 Group 内第一个 `human:*` 成员作为仲裁目标。
- v1 不做后台主动调度；Agent 仍由 mention、消息触发或任务队列驱动。
- v1 的范围越界识别主要依赖结构化 scope、prompt 约束和内部字段泄漏拦截，不做复杂自然语言分类。

## 验收点

- [x] Group 成员可创建 discussion，非 Group 成员不可创建或读取。
- [x] turn 只能引用当前成员本人在同一 Group Hall 中发送的消息。
- [x] turns 按 `turn_index, message_id` 稳定返回。
- [x] SDK 已提供 discussion 创建、查询、状态更新和 turn 追加 helper。
- [x] bridge 可解析 `talk-action`，执行同 Hall 代发并写入 discussion turn。
- [x] `discussion_turns.turn_kind` 已区分 `demand / reply`，bridge 使用显式账本控制第 2 轮扩展和第 3 轮刹车。
- [x] bridge 在两条连续不同 agent `disagree` 后自动升级给 human。
- [x] bridge 已支持安全行协议、`final_to_human`、自动回合上限和 action-only 回执抑制。
- [x] discussion session 已记录可选任务范围锚点，bridge 会按 reply/root scope 限制 agent-to-agent 续聊。
- [x] 已结束 scope 不再因普通 agent 回复自动开启无关话题。
- [x] bridge 已支持开头 mention 集群剥离、CLI 错误可见安全提示、malformed 协议残留拦截、非 Group agent 代发拦截、非实质 turn 过滤和轻扩展一轮收口。
- [x] pi 默认保持讨论档，施工工具档必须显式启用。
