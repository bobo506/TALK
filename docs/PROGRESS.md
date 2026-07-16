# Project Progress

## Latest

Updated: 2026-07-15 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- TH-3 终端 Task Hall 工具切片已完成；TH-2 已提交为 `99e8a28`。
- Codex MCP 与 pi extension 已具备 Agent 发现、项目化委派、查询 / 有界等待、Hall 回复、安全取消和结果收取能力。
- 全量回归 `309 tests` 全绿；当前按执行 Agent 单切片门禁暂停，等待项目管理者或决策 Agent 验收后再进入 claim lease / attempt。

## Current Snapshot

- `bridges/talk_send_mcp.py` 在保留 deferred `talk_send` 的同时新增八个 Task Hall 工具；`bridges/talk_tools_extension.ts` 提供同名 pi 工具面。
- `talk_list_agents` 结合项目 Agent profile、成员和实例状态；`talk_delegate_task` 会创建项目任务及专属 Task Hall。
- `talk_reply_task`、`talk_wait_tasks`、`talk_collect_result` 贯通澄清、回复、接受、提交和结果收取；等待采用最长 30 秒的有界轮询。
- async / sync client 与服务端新增 `cancel_task` / `POST /api/tasks/{id}/cancel`；仅原请求者可幂等取消未领取任务。
- bridge 会从 `.talk/project.yaml` 注入默认 `TALK_PROJECT_ID`；Codex discussion profile 与 pi 的 discussion / tools profile 都能访问对应工具。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 运行中任务取消尚未开放；必须先有 claim lease / attempt 与 runner 中断协议，避免服务端状态与真实执行脱节。
- `talk_wait_tasks` 目前是客户端轮询而非服务端事件等待；Agent 发现结果尚未提供项目业务角色字段。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- observer、返工、lease / attempt、Project Blackboard 和 Task Hall Web UI 尚未实现。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 设计 claim lease / attempt 与幂等约束，明确心跳、过期回收和重领规则。
2. 更新 runner 与服务端状态机并补并发 / 超时回收测试；完成后暂停，不提前进入 Web UI。

后续顺序：claim lease / attempt -> Project Blackboard + Task Hall UI -> 跨模型端到端人工验收。

## Verification

- `.venv\Scripts\python.exe -m py_compile server\routes\tasks.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\talk_task_tools.py bridges\talk_send_mcp.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_tasks.py tests\test_talk_client.py tests\test_talk_task_tools.py tests\test_pi_bridge.py tests\test_codex_bridge.py`：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_task_tools -v`：`Ran 4 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -v`：`Ran 12 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_codex_bridge -v`：`Ran 29 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 309 tests ... OK`。
- 本切片无前端改动，不需要 Browser 验证。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
