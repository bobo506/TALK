# Project Progress

## Latest

Updated: 2026-07-15 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- TH-2 async / sync client 与 bundled runner 接入切片已完成。
- client 已覆盖项目化创建、单任务读取、执行 / 协作状态过滤、澄清、接受与结果收取；runner 会把结果写入对应 Task Hall。
- 全量回归 `304 tests` 全绿；当前按执行 Agent 单切片门禁暂停，等待项目管理者或决策 Agent 验收后再进入终端 MCP。

## Current Snapshot

- `TalkClient` / `TalkClientSync.create_task()` 新增可选 `project_id`；`list_tasks()` 新增 `workflow_status` / `project_id` 过滤。
- async / sync client 新增 `get_task()`、`request_task_clarification()`、`accept_task()`、`collect_task_result()`。
- 通用 CLI runner 和 Codex 兼容处理入口均从 claim 响应读取 `hall_group_id`，结果消息先写入 Task Hall，再关联到 `result_message_id`。
- 无 `hall_group_id` 的旧任务仍按原行为写入全局时间线，保持兼容。
- 活服务测试覆盖 async / sync 完整流程；bridge 测试分别锁定 Hall 回传和旧任务兼容分支。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 终端 MCP 尚未提供 Agent 发现、委派、等待、纠偏 / 取消和批量结果收集工具。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- observer、取消 / 返工、lease / attempt、Project Blackboard 和 Task Hall Web UI 尚未实现。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 设计并实现终端 TALK MCP 的 Task Hall 能力：Agent 发现、项目化委派、查询 / 等待、Hall 回复、取消和结果收集。
2. 为 MCP 工具补权限、状态流转与活服务测试；完成后暂停，不提前进入 Web UI。

后续顺序：终端 MCP 能力 -> claim lease / attempt -> Project Blackboard + Task Hall UI -> 跨模型端到端人工验收。

## Verification

- `.venv\Scripts\python.exe -m py_compile TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py bridges\codex_bridge.py tests\test_talk_client.py tests\test_cli_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -v`：`Ran 12 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge -v`：`Ran 85 tests ... OK`；`tests.test_codex_bridge`：`Ran 19 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_pi_bridge -v`：`Ran 26 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 304 tests ... OK`。
- 本切片无前端改动，不需要 Browser 验证。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
