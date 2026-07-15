# Project Progress

## Latest

Updated: 2026-07-15 (Asia/Shanghai)

- 当前分支：`codex/task-hall`，基线为已收尾的 Discussion 分支提交 `1da4797`。
- 当前里程碑：实现一任务一 Hall、请求者与执行者 1 对 1 的 Task Hall 最小闭环。
- `agent-docs/BLACKBOARD.md` 属于本地协作文件，从本分支起不再纳入项目版本控制。
- 上一里程碑 BS-3a 已完成自动化收口修复，五模块共 147 个测试通过；真实模型汇总质量补验不阻塞 Task Hall。

## Current Snapshot

- 当前执行者：Codex；项目管理者已授权开始 Task Hall，按数据库 / 协议单切片完成后暂停验收。
- 产品合同已确认：Task Halls 与 Discussion Halls 分区；当前优先 Task Hall；每项委派任务自动建立独立 Hall，并归属于项目。
- Task Hall 标准流程：分配任务 -> 可选澄清 -> 接受 -> 执行 -> 提交结果 -> 请求者收取结果并完成。
- 现有基础：`AgentTask` 已提供 `queued/running/succeeded/failed/canceled` 队列状态；Group Hall 已支持 `type=task`、成员、消息和文件。
- 终端定位：实际操作终端负责发起、查询和收取结果；目标 Agent runner 负责领取、执行和回传，TALK 保存全过程。

## Pending Decisions

- 首个实现切片需结合现有模型决定：Task Hall 复用 `groups.type=task`，还是增加专用 thread 实体。
- 目标生命周期需与现有五种任务状态保持向后兼容，避免破坏当前 runner 和 API 客户端。
- BS-3a 仍保留一次真实 Codex / pi 最终汇总质量补验；这是 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 复核现有 `AgentTask`、Group、消息、成员和任务 API / 测试，确定最小兼容的数据关联方案。
2. 实现 Task Hall 数据与 API 地基：项目归属、一任务一 Hall、请求者 / 执行者关联及生命周期兼容。
3. 补迁移与自动化测试，完成后暂停并提交验收，不提前进入 MCP、runner 或 Web UI。

后续顺序：终端 TALK MCP / client -> runner 领取与回传 -> Project Blackboard + Task Hall UI -> 跨模型端到端人工验收。

## Verification Baseline

- BS-3a：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge` -> `Ran 147 tests ... OK`。
- Task Hall 产品文档：`git diff --check`、Markdown 本地链接和关键术语检查已通过；尚未开始功能代码验证。
- 历史测试、验收结果与完整切片记录见 `docs/PROGRESS_HISTORY.md`。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
