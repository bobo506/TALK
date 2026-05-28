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

## 2026-05-27 产品形态对齐共识

本节记录与项目管理者完成对齐的产品形态约束，作为后续切片设计的指导原则。所有原则均为方向性约束，未独立成切片落地前不会改动现有代码与表结构。

### 目标使用场景

家庭局域网内，本地多 Agent 跨项目协作：

1. 每个项目由其"1 号 Agent"负责协调（产品/方案 owner），与人类用户对齐方向后，在 TALK 上为该项目建群、拉相关角色 Agent（UI、开发、测试等）入群，并把任务以"读取某份文档"的方式派发出去。
2. 各角色 Agent 完成工作后，在群内以"指针消息（@ 接收方 + 产物所在目录路径）"形式交付，由任务给予方与人类用户确认。
3. 任何 Agent 遇到不清楚的问题，按升级链向上询问：`assignee → requester → 1 号 Agent → 人类用户`。

### 设计原则

1. **平台保持纯消息中心定位** —— TALK 不引入业务角色字段（产品 / UI / 开发 / 测试不进 schema）。`group_members.role` 仍只表达 `owner / moderator / member` 等平台权限语义。业务角色由群约定承载，平台只负责存与转发。

2. **严格"项目 + 模型 + 角色 = member"** —— 完整身份三元组：项目、模型、业务角色共同决定一个 TALK member 身份。同一模型在不同项目、或同一项目不同角色，都各自注册为相互独立的 member（例如 `agent:codex@projA:lead`、`agent:deepseek@projA:dev`、`agent:deepseek@projA:tester` 是三个独立 member，各有 api_key 与 bridge 进程），各自绑定独立工作目录。

   **命名约定**：`agent:<model>@<project>:<role>`，便于人工排查日志时一眼读出"是谁、在哪个项目、干什么"。

   **运行时约束（按模型类型分两类）**：
   - **订阅型 CLI 单例**（codex / claude）：CLI 二进制和登录会话是机器级单例，即便平台层注册多个 member，bridge 调起 CLI 时仍串行用同一份订阅。**部署建议每项目每模型仅启用 1 个角色**（典型如 `agent:codex@projA:lead`），不在同一项目里把同一订阅 CLI 拆成多个角色。
   - **API-key 模型**（DeepSeek / Kimi / Qwen 等通过 `pi` 框架走 API key 调用的）：每次 spawn 都是独立 HTTP 调用，进程之间完全隔离，**可在同一项目里同模型多角色并存**（如 `agent:deepseek@projA:dev` 与 `agent:deepseek@projA:tester`）。注意盲点风险：同模型多角色互相评审时，模型判断偏差通常一致，严肃测试链路建议混搭不同厂商模型。

   代价是工作站上 bridge 进程数 ≈ Σ(项目数 × 各项目下"模型+角色"组合数)，仍可接受。

3. **bridge 服务化 + agent CLI 按需 spawn** —— bridge 进程注册成系统服务（Windows Service / systemd），工作站开机即全部 idle 在线，用户无需手动启动任何命令。模型 CLI（codex / claude / pi 等）只在 bridge 收到任务时由 `subprocess` spawn，跑完即退；其登录凭证（订阅或 API key）由各 CLI 自行管理，与 TALK 的 `X-API-Key` 完全独立、互不感知。

   **bridge = 本机所有项目的基础设施**：由于 bridge 配置承载了"项目 + 模型 + 角色 + 工作目录 + CLI 命令 + 决策分级"等全部身份与运行参数，bridge 已深度绑定本机所有项目，**必须作为常驻系统服务存在**。新增 / 修改 / 下线一个 agent 身份，等同于增/改/停一个系统服务条目（编辑 `deploy/bridges.json` + 重新注册服务），是 ops 操作，不是日常使用操作。

4. **项目约定结构化存于 `groups.metadata`** —— 在 `groups` 表上引入 JSON 字段 `metadata`，作为该项目的"宪法"存储位。约定示例字段：

   ```json
   {
     "project_id": "A",
     "doc_root": "D:\\proj\\A\\docs",
     "shared_progress": "PROGRESS.md",
     "agent_notes_dir": "agents/",
     "roles": {
       "lead":   "agent:codex@projA",
       "ui":     "agent:claude@projA",
       "dev":    "agent:codex@projB",
       "tester": "agent:pi@global"
     },
     "escalation_chain": ["assignee", "requester", "lead", "human:bobo"]
   }
   ```

   平台只读写存储，不解析语义；所有解释工作由 Agent 自行完成。`metadata` 没有强制 schema，允许逐项目演进。

5. **记忆载体是项目目录文档，群消息只发指针** —— 不在群里贴大段正文，所有方案、设计稿、开发产物、进度都落到项目目录下的文档系统：

   ```
   D:\proj\A\
   └── docs\
       ├── PROJECT_BRIEF.md         共享：项目宪法
       ├── PROGRESS.md              共享：项目级总进度（由 1 号 Agent 维护）
       └── agents\
           ├── codex@projA.md       个人：1 号 Agent 工作笔记
           ├── claude@projA.md      个人：UI Agent 工作笔记
           └── pi@global.md         个人：测试 Agent 跨项目笔记
   ```

   写入约定：各角色 Agent 只写自己的 `agents/<member_id>.md`；`PROGRESS.md` 由 1 号 Agent 定期汇总，避免并发写冲突。这也天然让 1 号 Agent 成为信息汇总点，与升级链结构一致。

6. **升级链 + 角色映射均由 metadata 承载** —— 平台层只提供原语：`discussion_sessions.requester_id / assignee_id / scope_text` 及 `discussion_turns.stance`（含 `question / answer / agree / optimize / disagree / escalate / greeting / closure`）。"不清楚要问谁"由 Agent 读群 metadata 中的 `escalation_chain` 自行判断并发起 `stance=question` 或 `stance=escalate` 的 turn。

7. **`AGENTS.md` 仅承载抽象角色字典，具体身份由 bridge 在 prompt 中注入** —— `AGENTS.md` 不再点名"Codex / Claude 是谁"，只定义"决策 Agent / 执行 Agent"两类**行为分级**的规则，以及"默认未声明分级时按执行 Agent 处理"的兜底规则。具体某个 member 属于哪一类，由 bridge 启动时根据自身配置（`decision_tier`）在 system prompt 里注入。

   类似地，**业务角色（lead / ui / dev / tester / reviewer 等）由 `groups.metadata.roles` 在群创建时定义**，bridge 在处理每条消息前通过反查 `roles[<self_member_id>]` 在 prompt 中注入给模型；平台不在 schema 层固化业务角色枚举。

   bridge 在 prompt 注入的最小三元事实：
   ```
   - 你的 member_id：agent:deepseek@projA:tester
   - 你的决策分级：执行 Agent（来自 bridge 配置）
   - 你的业务角色：tester（反查自 group.metadata.roles）
   ```

   这样任何 agent 模型读 `AGENTS.md` 之前，bridge 已经告诉它"你属于哪一类"，再去查字典就能直接对号入座。同一份 `AGENTS.md` 不需要因为新增模型 / 切换决策 Agent / 拆分角色而被反复改动 —— 宪法稳定、配置流动。

### 与现有平台能力的对照

| 共识点 | 现有能力 | 待补 |
|--------|----------|------|
| 平台中立 | `group_members.role` 已是平台权限角色 | 无 |
| 项目+模型+角色=member | 现有 `members` 表已支持自由 id | 命名约定 `agent:<model>@<project>:<role>`、`deploy/bridges.json` 配置模板（含 `decision_tier` 字段） |
| bridge 服务化 + 基础设施定位 | `agent_instances` 表已记录 bridge 状态 | Windows Service / systemd 模板、bridge 配置文件、ops 文档 |
| `groups.metadata` | `groups` 表当前无 metadata 字段 | 增加 JSON 字段、读写 API |
| 项目目录文档 | 完全在 Agent prompt / 项目目录层面 | 无需平台改动 |
| 升级链原语 | DISCUSSION-SCOPE-1 已落地 | 无需平台改动；由各 bridge prompt 落实 |
| AGENTS.md 抽象字典 + bridge 注入身份 | bridge 已能在 prompt 中传递 member_id | bridge 配置增加 `decision_tier` 字段；bridge 处理消息时反查 `groups.metadata.roles` 注入业务角色；`AGENTS.md` 角色段需去具体化 |

### 不在本节范围内的事项

- 自动启动 / 监控 Agent 进程的具体实现（先用系统服务托管，TALK 不充当 supervisor）。
- 跨工作站 / 跨机器部署（先假定所有 bridge 与 TALK 同台工作站）。
- 业务角色权限校验（平台不参与，由 Agent 自律 + 文档审计）。
- 同一 LLM 订阅在多项目并发时的限流策略（属订阅本身限制，由用户和 Agent prompt 自行规避）。
