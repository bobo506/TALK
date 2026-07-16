# Project Progress

## Latest

Updated: 2026-07-16 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- TH-5 Project Blackboard + Task Hall 完整流程已提交为 `04fade4` 并推送；项目管理者已从页面委派任务并成功拿到 runner 返回结果，基础可视化链路人工验收通过。
- 下一阶段方向已确认：补齐“B 领取前判断 → 同一 Hall 提问 → A 回答 → B 带完整上下文重新判断 → accept / claim / execute”的自动澄清闭环。
- CLI 终端已具备 `talk_delegate_task` 等八个 Task Hall 工具；Codex Desktop 与其它普通终端仍需接入包装，才能在非 bridge 会话中直接自然语言委派。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务；项目侧栏同步列出对应 Task Hall。
- 人类可从页面选择项目 Agent 并委派任务；详情面板显示精确协作状态、attempt 与租约，并按权限提供 Hall、澄清 / 接受、结果收取和未领取取消动作。
- Task Hall 原始任务、提问、回答和结果均持久化在同一个 Hall，固定请求者 A 与执行者 B 均有读取权限；Web 可分页查看，SDK 可分页拉取。
- `talk_get_task` 当前只自动返回最近 50 条 Hall 消息；bundled runner 正式执行 prompt 目前只含任务标题 / 正文，尚未自动注入澄清历史。
- `clarification_requested`、Hall 回复、`accept` 和“待澄清禁止 claim”的服务端基础能力仍在；缺口是 runner 对 `assigned` 任务会直接 claim，没有领取前预检、等待 A 回复和重新唤醒 B 的自动流程。
- 通过 TALK bridge 启动的 Codex CLI / pi 已可发现 Agent、委派、等待、读取 Hall、回复和收取；普通 Codex Desktop 会话尚未自动注册 TALK MCP。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 运行中任务取消尚未开放；lease 已能识别并终止失去持有权的 runner，但还缺请求者触发的协作中断状态。
- `talk_wait_tasks` 目前是客户端轮询而非服务端事件等待；Agent 发现结果尚未提供项目业务角色字段。
- Hall 数据完整持久化不等于模型自动获得完整上下文；TH-6 必须分页读取并按顺序重放任务原文、B 的问题与 A 的答复。
- 文件消息可保留元数据，但附件正文是否在任务执行前自动下载和注入尚未定义。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- 无 lease 的历史 `running` 任务不会自动回收；业务重试上限与退避策略尚未定义。
- 项目级 `Members / Activity` 独立页面、observer 与返工尚未实现；当前 Hall 列表继续兼容无 `project_id` 的旧 Group。
- pi 的真实模型在“逐字回复”类任务上可能改写为简短确认，属于模型输出质量边界；基础设施已保证只写一条结果并正确推进状态。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. TH-6：实现领取前预检与同 Hall 自动澄清闭环；B 提问后保持 `queued / clarification_requested` 并继续监听，A 回复后 B 带完整分页 Hall 上下文重新判断，信息充分才 `accept → claim → execute`。
2. TH-6 验收覆盖多轮澄清、消息顺序、重复唤醒幂等、等待期间不 claim，以及最终执行 prompt 确实包含原始任务和全部澄清文本。
3. TH-7：在现有 `talk_delegate_task` 工具基础上补 Codex Desktop / 通用终端接入包装，并贯通“终端 A 委派 → B 澄清 → A 回复 → B 执行 → 终端 A 收取”。

## Verification

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_codex_bridge.py`：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `node --check web\app.js` 与 `git diff --check`：通过。
- 定向 Web / runner / client 测试：`Ran 124 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：清理真实验收服务后 `Ran 321 tests in 98.917s ... OK`；首次并行运行有一个既有 WS 降级测试 2 秒清理超时，该用例随后连续两次单测通过。
- Browser 真实交互：登录、项目空态、委派、Hall 消息、runner 回写、结果待收取、点击收取、已结束分栏全部通过；最终控制台 error / warning 为 0。
- 真实 CLI：Codex 与 pi 均完成 claim → 执行 → 单条 Hall 结果 → collect；Codex 精确遵循测试正文，pi 基础确认链通过但逐字遵循仍有质量差异。
- 2026-07-16 人工页面测试：项目管理者成功拿到委派任务返回结果；本次收工仅记录后续设计与边界，没有新增代码验证。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
