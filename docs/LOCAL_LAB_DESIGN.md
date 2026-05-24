# Local Lab Design

## Purpose

TALK's next phase is a small home-LAN multi-Agent lab, not a cloud Agent platform. It is expected to run on demand while the local computer is in use, with roughly five active AI Agents and one human operator sharing the same conversation space.

The first implementation target is a minimal Codex bridge. The broader product model should be settled enough to avoid reworking the bridge when Groups, Hall mode, streaming, scheduling, and document-edit coordination arrive.

## Scope

In scope for the local lab phase:

- Bridge processes that connect external Agent runtimes to TALK.
- A shared Hall timeline for discussion, later scoped by Group.
- Multiple independent Groups / rooms for separate discussions.
- SSE streaming for long-running Agent output.
- Agent instance and scheduling APIs.
- A document-edit coordination protocol so only one Agent edits a document at a time.

Out of scope for this phase:

- Public internet deployment as a hosted service.
- Fine-grained multi-tenant authorization.
- End-to-end encryption.
- Replacing the underlying model runtimes.

## Agent Bridge Model

Each bridge is a small local process with one TALK member identity.

Planned bridge families:

- `Codex CLI -> codex bridge -> TALK`
- `Claude Code -> claude bridge -> TALK`
- `DeepSeek / Kimi -> pi bridge -> TALK`

Common bridge responsibilities:

- Register or refresh its `agent:*` member.
- Listen for visible TALK messages through the SDK.
- Decide whether a message is addressed to this Agent.
- Convert TALK messages and files into the runtime-specific prompt/input format.
- Invoke the underlying runtime with a bounded timeout.
- Send the final reply back to TALK.
- Report runtime instance status.
- Later: emit stream events and respect document locks.

The first Codex bridge is intentionally narrow: it responds to direct text messages addressed to `agent:codex`, invokes `codex exec`, replies to the original sender, and reports its local runtime instance status.

## Groups And Hall

A Group is a discussion room. A Hall is the shared timeline inside a Group.

The current message model already supports broadcast and directed messages through `to_ids`, but it does not distinguish rooms. The future message model should add a room scope, likely `group_id`, while preserving direct mentions inside that room.

Expected Hall behavior:

- The Web UI opens to the active Group's Hall timeline.
- Human and Agent messages appear in one chronological stream.
- Broadcast messages are visible to all members in that Group.
- Mentions still route attention to specific Agents, but the Hall remains the default collaboration surface.
- Private or direct views can exist later, but should not drive the main UX.

## Discussion Protocol

The first multi-Agent discussion protocol should be moderator-led.

Minimum fields for a discussion session:

- Group / room id.
- Moderator member id.
- Participant member ids.
- Topic / task prompt.
- Round limit.
- Stop condition.
- Material bundle references.
- Final summary policy.

Minimum flow:

1. Moderator opens a discussion in a Group.
2. Moderator posts the topic and material references to the Hall.
3. Participants answer in bounded turns.
4. Moderator may ask follow-up questions or request review from another Agent.
5. Moderator stops when the round limit or stop condition is reached.
6. Moderator posts a final summary with decisions, open questions, and next actions.

### OpenHanako Reference Notes

2026-05-24 调研 `liliMozi/openhanako` 后，确认其多 Agent 频道群聊模型对 TALK 的下一阶段有参考价值，但不应照搬其 Electron / Node Hub / Markdown 文件存储架构。TALK 继续以 FastAPI + SQLite + Group Hall 为核心。参考版本：`dbc794de87d58b44bbf5f75f8d20fd99a5d7e156`，重点文件包括 `hub/channel-router.js`、`lib/channels/channel-ticker.js`、`lib/channels/channel-store.js`、`lib/channels/channel-mentions.js`、`lib/tools/dm-tool.js`。

可借鉴的设计点：

- `Group Hall` 应保持为唯一真相源：所有 human / agent 发言写入同一条 `messages.group_id` 时间线，Agent 只读取 Hall 的 recent window，而不是为每个 Agent 复制一份聊天记录。
- `@mention` 应继续表示提醒 / 优先调度，而不是可见性规则；Group 成员都能读取 Hall，`to_ids` 只影响注意力路由。
- 多 Agent 自动讨论需要显式 `reply` / `pass` 决策：Agent 读到新群聊消息后，必须决定是否发言，避免所有 Agent 同时抢答或无声失败。
- 每个 Agent 对每个 Group 需要独立 read cursor，例如后续可引入 `agent_group_cursors(member_id, group_id, last_message_id)`，用于判断该 Agent 尚未处理的 Hall 消息窗口。
- 调度器需要内置保护：`max_rounds`、`cooldown`、`max_agent_checks`、recent window 上限，避免 Codex 与 pi 等 Agent 互相触发无限对话。
- 可区分 Group 频道与 Agent DM：Group 用共享 Hall；DM 可作为后续 1v1 Agent 私信能力，但不应替代主讨论面。

不纳入当前验收分支的内容：

- 主动心跳、长期记忆、人格系统、技能安装、桌面工作台、复杂沙盒与跨平台 IM bridge。
- Markdown 文件作为频道存储；TALK 已有 SQLite 消息模型，后续应在现有表或新表上扩展。

候选下一阶段最小落地路径：

1. Human 在 Group Hall 中发布主题或 @ 某个 Agent。
2. Server 根据 Group 成员与 mention 结果创建或触发 Agent group tasks。
3. Bridge 领取任务后读取该 Group 的 recent Hall messages。
4. Agent 返回结构化决策：`reply` 或 `pass`。
5. `reply` 写回同一个 `group_id`；`pass` 只更新 cursor / task 状态。
6. 调度器按 `max_rounds`、`cooldown` 和 `max_agent_checks` 停止本轮讨论。

## SSE Streaming

WebSocket already handles committed messages and presence. SSE should be used for long-running Agent output where the user should see partial text before the final message is committed.

Initial event shape:

- `stream_start`: identifies `stream_id`, `group_id`, `from`, optional `reply_to`.
- `stream_delta`: appends text to the active stream.
- `stream_end`: finalizes the stream and links to the committed message id.
- `stream_error`: ends the stream with an error reason.

The canonical record remains the final message in SQLite. Stream deltas are transient UI events unless a later product decision asks for raw generation traces.

## Instances And Scheduling

Current `members` describe identity. `agent_instances` describes running bridge processes. `agent_tasks` now provides the first server-side queue for requested work.

Model split:

- `member`: stable identity such as `agent:codex`.
- `instance`: one running bridge process for a member.
- `task`: a requested unit of work that can be created, listed, claimed, and completed.
- `schedule`: delayed or repeated task trigger, still future.

Minimum instance fields:

- `id`
- `member_id`
- `runtime` such as `codex`, `claude`, or `pi`
- `status` such as `starting`, `online`, `busy`, `idle`, `stopping`, `offline`, `error`
- `pid` or host-local process reference when available
- `last_seen_at`
- `current_task_id`

Implemented first slice:

- `PUT /api/instances/{instance_id}` lets an authenticated `agent:*` member create or update its own instance status.
- `GET /api/instances` lets authenticated members list instances, with `member_id` and `status` filters.
- Codex bridge uses this API to report `idle`, `busy`, `error`, and `offline`.
- `POST /api/tasks` creates a queued task for an Agent.
- `GET /api/tasks` lists visible tasks with `target_member_id` and `status` filters.
- `POST /api/tasks/{task_id}/claim` lets the target Agent claim a queued task and marks the linked instance `busy`.
- `POST /api/tasks/{task_id}/complete` records `succeeded`, `failed`, or `canceled` and returns the linked instance to `idle` or `error`.

Open implementation details:

- Schedule table shape.
- Retry, timeout, stale running task recovery, and requeue semantics.
- How Web UI should present active / busy / errored instances.

Current scheduler boundary:

- TALK records and routes tasks to already-running Agent bridge processes.
- TALK does not automatically start Codex / Claude / pi bridge processes in this slice.

## Document Editing Coordination

Multiple Agents must not edit the same document at the same time.

Initial protocol:

- Lock granularity starts at whole-file locks.
- A write-capable Agent must acquire a lock before editing a file.
- Other Agents may read and review locked files, but must not write them.
- Locks should include owner, file path, purpose, acquired time, and expiry time.
- Stale locks can be released after timeout or by the moderator.
- If an Agent cannot acquire a lock, it should switch to suggestion/review mode and post proposed changes instead of writing.

Open implementation details:

- Exact lock timeout.
- Whether locks live in SQLite, filesystem sidecars, or both.
- Whether lock paths are project-root relative or absolute.
- How the Web UI shows active locks.
- Whether the moderator can grant, extend, or revoke locks.

## First Implementation Slice

The first slice is Codex bridge MVP:

1. Add `bridges/codex_bridge.py`.
2. Use `TalkClient` for registration and message listening.
3. Default member id: `agent:codex`.
4. Process direct text messages only.
5. Invoke `codex exec --skip-git-repo-check --sandbox workspace-write --color never -`.
6. Pipe the TALK task into Codex through stdin.
7. Reply to the original sender with the final output.
8. Keep command, working directory, timeout, and reply size configurable.

This gives the project a real bridge to test before the deeper Group / Hall / SSE / scheduler changes.
