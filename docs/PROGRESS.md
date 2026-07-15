# Project Progress

## Latest

Updated: 2026-07-15 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- Task Hall 数据 / API 地基切片已完成：复用 `groups.type=task`，自动一任务一 Hall，保留 runner 五态并新增独立协作状态。
- 最终代码全量覆盖分两批完成：任务相关七模块 `200 tests` + 其余十四模块 `103 tests`，合计 `303 tests` 全绿。
- 当前按数据库 / 协议切片门禁暂停，等待项目管理者或决策 Agent 验收后再进入 SDK / runner 接入。

## Current Snapshot

- `AgentTask` 已新增 `project_id`、唯一 `hall_group_id`、`workflow_status`、`result_collected_at`，旧库会补列并按原五态回填协作状态。
- `POST /api/tasks` 会原子创建独立 Task Hall；请求者为 `owner`、执行者为 `member`，双方必须不同。
- Task Hall 成员不能通过普通 Group API 改写，Hall 也不能脱离关联 task 独立删除。
- 协作流程已支持 `assigned -> clarification_requested -> accepted -> in_progress -> submitted -> completed`；`failed/canceled` 同步保留。
- 新增单任务读取、项目 / 协作状态过滤、请求澄清、接受和收取结果 API；claim / complete 自动同步执行状态与协作状态。
- schedule 物化任务同样自动创建独立 Hall；schedule 尚无项目字段，因此当前物化 Hall 为无项目归属。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- SDK 尚未暴露项目参数、协作状态过滤和三类动作 helper。
- bundled bridge 仍把结果发到旧全局时间线；服务端暂时兼容，下一片改为使用 `hall_group_id`。
- observer、取消 / 返工、lease / attempt、Project Blackboard 和 Task Hall Web UI 尚未实现。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 扩展 async / sync TALK client：项目化委派、单任务读取、协作状态过滤、澄清 / 接受 / 收取结果。
2. 让 bundled CLI / Codex runner 把任务结果写入对应 Task Hall，并保持旧任务兼容。
3. 补 SDK 活服务与 bridge 自动化测试；完成后暂停，不提前进入 Web UI。

后续顺序：终端 MCP 能力 -> claim lease / attempt -> Project Blackboard + Task Hall UI -> 跨模型端到端人工验收。

## Verification

- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py server\routes\groups.py tests\test_tasks.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -v`：`Ran 16 tests ... OK`。
- 任务相关七模块最终回归：`Ran 200 tests ... OK`；其余十四模块：`Ran 103 tests ... OK`，最终代码合计 303 项通过。
- 核心实现完成后的单次 unittest discovery 也曾 `Ran 303 tests ... OK`；最后一次单进程复跑在活服务测试退出阶段未结束而被工具超时终止，无断言失败，随后用上述 200 + 103 分批复跑覆盖全部模块。
- 本切片为后端数据库 / API 改动，无前端或 Browser 验证。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
