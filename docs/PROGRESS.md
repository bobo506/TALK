# Project Progress

## Latest

Updated: 2026-07-16 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- TH-3 终端 Task Hall 工具已提交为 `ff8f8a8`；TH-4 claim lease / attempt 可靠性切片已完成。
- 并发 claim、token 持有、runner 心跳、过期回收、重领与陈旧结果拒绝已形成闭环。
- 全量回归 `313 tests` 全绿。项目管理者已明确把人工介入点放到完整流程里程碑，下一步进入 Project Blackboard + Task Hall Web UI。

## Current Snapshot

- `AgentTask` 新增 `attempt`、私有 `claim_token`、`lease_expires_at` 与 `heartbeat_at`；普通任务查询不暴露 token。
- claim 采用条件更新，两个实例并发领取只有一个成功；同一实例重复请求保持幂等。
- 新增 heartbeat 与 expired requeue API 及 async / sync SDK；过期任务回到 `queued / accepted`，下一次 claim 递增 attempt。
- complete 校验当前 token 与未过期租约；陈旧 attempt 不能覆盖新结果，首次 attempt 仍保留旧 runner 无 token 兼容。
- bundled runner 默认 120 秒租约 / 30 秒心跳，每轮先回收过期任务；租约丢失会取消本地子进程且不回写结果。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 运行中任务取消尚未开放；lease 已能识别并终止失去持有权的 runner，但还缺请求者触发的协作中断状态。
- `talk_wait_tasks` 目前是客户端轮询而非服务端事件等待；Agent 发现结果尚未提供项目业务角色字段。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- 无 lease 的历史 `running` 任务不会自动回收；业务重试上限与退避策略尚未定义。
- observer、返工、Project Blackboard 和 Task Hall Web UI 尚未实现。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 实现 Project Blackboard：按待确认、待澄清、执行中、待收取、已完成聚合项目任务。
2. 实现 Task Hall 详情与操作：时间线、状态、回复、接受 / 收取、未领取取消，并做 Browser 真实交互验证。

后续顺序：Project Blackboard + Task Hall UI -> bundled runner 完整链路验证 -> 跨模型端到端人工验收。

## Verification

- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\talk_task_tools.py tests\test_tasks.py tests\test_talk_client.py tests\test_cli_bridge.py tests\test_codex_bridge.py`：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_talk_client tests.test_cli_bridge tests.test_codex_bridge tests.test_talk_task_tools -q`：`Ran 141 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 313 tests ... OK`。
- 本切片无前端改动，不需要 Browser 验证。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
