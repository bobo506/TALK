# Project Progress

## Latest

Updated: 2026-07-16 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- TH-3 终端工具已提交为 `ff8f8a8`，TH-4 claim lease / attempt 已提交为 `a5aa3bb`；TH-5 Project Blackboard + Task Hall 完整流程已完成并进入人工验收门禁。
- Web UI、async SDK、bundled runner、真实 Codex / pi CLI 与对应 Task Hall 结果回写已经贯通；项目管理者现在可以从项目黑板直观看到并验收完整流程。
- 全量回归 `321 tests` 全绿；Browser 真实交互覆盖委派、Hall 消息、runner 回写、结果收取和完成态，控制台无 error / warning。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务；项目侧栏同步列出对应 Task Hall。
- 人类可从页面选择项目 Agent 并委派任务；详情面板显示精确协作状态、attempt 与租约，并按权限提供 Hall、澄清 / 接受、结果收取和未领取取消动作。
- 新增活服务整链测试：任务创建后由真实 bundled runner claim、执行并写入唯一 Task Hall，再由请求者收取为 `completed`。
- Codex / pi 队列 worker 使用独立任务命令，不向嵌套模型暴露 TALK 结果投递工具；runner 成为唯一 Hall 结果写入者，真实 pi 复测从 3 条重复结果收敛为 1 条。
- 真实 Codex 当前任务命令精确返回 `Codex Task Hall connected.`；真实 pi 完成领取、单条 Hall 回写与收取，但逐字指令遵循仍弱于 Codex。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 运行中任务取消尚未开放；lease 已能识别并终止失去持有权的 runner，但还缺请求者触发的协作中断状态。
- `talk_wait_tasks` 目前是客户端轮询而非服务端事件等待；Agent 发现结果尚未提供项目业务角色字段。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- 无 lease 的历史 `running` 任务不会自动回收；业务重试上限与退避策略尚未定义。
- 项目级 `Members / Activity` 独立页面、observer 与返工尚未实现；当前 Hall 列表继续兼容无 `project_id` 的旧 Group。
- pi 的真实模型在“逐字回复”类任务上可能改写为简短确认，属于模型输出质量边界；基础设施已保证只写一条结果并正确推进状态。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. 由项目管理者按页面验收说明完成一次真实可视化验收：创建 Task Hall、观察 runner 执行结果、进入 Hall、收取结果。
2. 验收通过后关闭 Task Hall 当前里程碑，再决定运行中协作取消、返工 / observer、后台 schedule 或项目级 Members / Activity 的优先级。

## Verification

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_codex_bridge.py`：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `node --check web\app.js` 与 `git diff --check`：通过。
- 定向 Web / runner / client 测试：`Ran 124 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：清理真实验收服务后 `Ran 321 tests in 98.917s ... OK`；首次并行运行有一个既有 WS 降级测试 2 秒清理超时，该用例随后连续两次单测通过。
- Browser 真实交互：登录、项目空态、委派、Hall 消息、runner 回写、结果待收取、点击收取、已结束分栏全部通过；最终控制台 error / warning 为 0。
- 真实 CLI：Codex 与 pi 均完成 claim → 执行 → 单条 Hall 结果 → collect；Codex 精确遵循测试正文，pi 基础确认链通过但逐字遵循仍有质量差异。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
