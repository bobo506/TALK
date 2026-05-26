# Project Progress

## Latest
Updated: 2026-05-26 11:12 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `BASIC-CODEX-PI-FLOW-ACCEPT-1` 已完成：重启 TALK server、Codex bridge、pi bridge 后，跑通真实 Codex + pi Group Hall 讨论验收。
- 验收 Group：`group:c52be0b773e6`；human 消息 `#138` 触发 Codex，Codex 消息 `#139` 同 Hall 代发给 `@agent:pi`，pi 消息 `#141` 回复 Codex，Codex 消息 `#142` 将最终结论发给 `@human:bobo`。
- Discussion session `#6` 已创建并从 `active` 变为 `resolved`；server 健康检查保持 `status=ok`，Codex / pi 实例最终均回到 `idle` 且 `last_error=None`。
- 项目管理者新增 4 条后续使用建议已记录为待办：自定义 agent 显示名称；无指定 agent 消息按广播要求所有 agent 接收并回复；删除 Group；自定义角色性格。
- 当前 bridge/server 已以当前工作区代码重启；日志落在 `logs/talk-server.current.*.log`、`logs/codex-bridge.current.*.log`、`logs/pi-bridge.current.*.log`。

### 3) Open Questions / Pending Confirmation
- 本轮首次验收脚本因 PowerShell -> Python 临时脚本编码问题，把中文消息写成 `????`（消息 `#136`）；重试时改用 ASCII 源码内的 Python Unicode escape，消息 `#138` 已确认中文正确入库。
- 长轮询验收脚本高频 `fetch_history` 时偶发 `httpx.ReadError` / `RemoteProtocolError`，但 server 健康检查保持正常，消息与 discussion 均已落库；若后续要做自动验收脚本，应单独降低轮询频率或排查 HTTP 连接复用。
- Discussion turns 当前只记录了 Codex 的 `question` 与最终 `answer`；pi 的普通回复消息存在，但未作为 turn 记录，因为本轮 pi 没有输出 `mark_stance` 动作。后续如要完整 UI 展示讨论轮次，需要补“agent 回复自动落 turn”或强化 pi stance 输出。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 进入人工验收：浏览器打开 `http://127.0.0.1:8000/`，用 `human:bobo` 的 API Key 登录，查看 Group `smoke-codex-pi-20260526-b` 中 `#138` 到 `#142` 的完整回合。
2. 验收通过后，下一批建议优先拆需求：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
3. 若先补工程质量，建议处理：自动验收脚本 UTF-8 输入、HTTP 轮询偶发 `ReadError`、pi 回复 turn 记录缺失。

### 5) Verification
- `Invoke-RestMethod http://127.0.0.1:8000/healthz` passed：`status=ok / db=ok / storage=ok / online_members=3`。
- Live smoke passed：`human:bobo -> agent:codex -> agent:pi -> agent:codex -> human:bobo`，消息 `#138` 到 `#142` 均在同一 Group Hall。
- DB verification passed：discussion session `#6` status=`resolved`，Codex / pi 最新实例 status=`idle` 且 `last_error=None`。
- First attempt failed as expected due to temporary PowerShell script encoding: message `#136` became `????` and Codex returned `#137` requesting resend。
- Not rerun: backend unit test suite；本轮只改进度文档并做真实运行验收。

### 6) Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
