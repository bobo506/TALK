# Project Progress

## Latest

Updated: 2026-07-18 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- 项目管理者已于 2026-07-18 明确授权当前 Codex 作为决策 Agent，并授权提交、推送 TH-6a0 / TH-6a1；本次按协议与实现边界拆分为两笔中文提交。
- TH-5 Project Blackboard + Task Hall 完整流程已提交为 `04fade4` 并推送；项目管理者已从页面委派任务并成功拿到 runner 返回结果，基础可视化链路人工验收通过。
- TH-6a0 协议文档切片已完成：任务树硬预算、有限批次授权、自动检查点、随时暂停 / 继续 / 整树终止、澄清轮次以及开发 → Review → 里程碑黑盒测试 → 人工验收门禁已写入 `docs/spec/MODULE_tasks.md`。
- TH-6a1 已完成：`agent_tasks` 新增 `parent_task_id / root_task_id / delegation_depth / may_delegate` 与四项根治理预算；旧任务迁移为独立根，保持不可继续委派，并回填默认预算。
- 创建子任务时服务端强制父任务仍在执行、调用者有权、父任务已获委派权限、项目继承、深度和非终态后代预算；领取子任务时再次原子校验根运行后代与单目标运行预算，并发请求不能通过直接 API 绕过。
- async / sync SDK 的 `create_task` 已暴露父任务、委派权限和四项根预算参数；活服务测试已贯通一层子任务创建、项目继承和安全取消。
- 已冻结默认保护值：最大委派深度 1、单个根任务同时执行子任务 3、单个目标 Agent 同时执行 1、单个根任务累计非终态子任务 8；子任务默认不可继续委派，只有主控显式授权后才能突破默认能力边界。
- 澄清默认最多 1 轮；一轮可集中提出多个编号问题，A 可连续补充多条消息并以显式“提交澄清答复”结束该轮。额度耗尽后仍不充分时必须阻塞并交回主控决策，不能强制领取或猜测执行。
- 主 Agent 只获得有限批次授权：普通小切片默认 2 个、纯文档 / 配置可显式提高到 3 个、高风险 / 跨模块批次默认 1 个；批次、时间、风险、额度、Review 或里程碑边界进入 `awaiting_human`，Human 可随时暂停并撤销后续推进权限。
- 质量流水线已冻结为独立 Task Hall：`development / review / test / rework` 通过任务关系和结构化 `gate_verdict` 形成门禁；高风险逐片 Review，低风险可批量 Review，黑盒测试只在里程碑运行，测试通过后仍必须暂停等待人工验收。
- CLI 终端已具备 `talk_delegate_task` 等八个 Task Hall 工具；Codex Desktop 与其它普通终端仍需接入包装，才能在非 bridge 会话中直接自然语言委派。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务；项目侧栏同步列出对应 Task Hall。
- 人类可从页面选择项目 Agent 并委派任务；详情面板显示精确协作状态、attempt 与租约，并按权限提供 Hall、澄清 / 接受、结果收取和未领取取消动作。
- Task Hall 原始任务、提问、回答和结果均持久化在同一个 Hall，固定请求者 A 与执行者 B 均有读取权限；Web 可分页查看，SDK 可分页拉取。
- `talk_get_task` 当前只自动返回最近 50 条 Hall 消息；bundled runner 正式执行 prompt 目前只含任务标题 / 正文，尚未自动注入澄清历史。
- `clarification_requested`、Hall 回复、`accept` 和“待澄清禁止 claim”的服务端基础能力仍在；缺口是 runner 对 `assigned` 任务会直接 claim，没有领取前预检、等待 A 回复和重新唤醒 B 的自动流程。
- bundled runner 的嵌套任务命令仍默认不暴露 TALK 委派工具；服务端现已支持显式 `parent_task_id` 委派，并强制深度、根运行后代、单目标运行和非终态后代预算。默认根任务不可委派，只有 Human 可授予顶层委派能力或覆盖根预算。
- 单个 bridge 进程继续通过共享运行锁串行执行任务；多个 bridge 实例领取同一任务树的后代时，服务端会统一执行根级和单目标并发限制，但尚无项目级跨根总预算。
- 任务澄清目前没有轮次计数、答复提交动作或额度耗尽后的阻塞状态；Discussion Hall 的 `max_rounds=2` 属于另一套讨论协议，不能替代 Task Hall 澄清限制。
- 当前还没有根任务 `control_status`、批次授权 epoch、暂停传播、任务类型 / 关系或结构化 Review/Test 结论；TH-6a1 只让任务树和基础预算成为硬保护，暂停与质量流程仍未生效。
- 通过 TALK bridge 启动的 Codex CLI / pi 已可发现 Agent、委派、等待、读取 Hall、回复和收取；普通 Codex Desktop 会话尚未自动注册 TALK MCP。

## Current Boundaries

- `project_id` 为旧客户端兼容仍可为空；新 Task Hall 终端调用应提供项目。
- 运行中任务取消尚未开放；lease 已能识别并终止失去持有权的 runner，但还缺请求者触发的协作中断状态。
- `talk_wait_tasks` 目前是客户端轮询而非服务端事件等待；Agent 发现结果尚未提供项目业务角色字段。
- Hall 数据完整持久化不等于模型自动获得完整上下文；TH-6 必须分页读取并按顺序重放任务原文、B 的问题与 A 的答复。
- 服务端已有任务树与根治理预算字段，并在创建 / claim 入口原子拒绝越权、超深度和超预算请求；尚缺有限批次授权与控制状态字段，TH-6a2 仍需补人类暂停、恢复授权和 runner 协作中断。
- 根任务当前可以在后代未结束时自行完成；整树汇总、完成条件和 Review/Test 门禁留待后续控制与质量切片收敛。
- 澄清轮次应按“B 的集中问题批次 + A 的完整答复”计数，不按 Hall 消息条数计数；A 的普通补充消息不能过早唤醒 B，需新增显式答复提交动作或等价原子协议。
- 现有任务没有 `task_kind`、门禁关系和 `gate_verdict`；当前 `.talk/groups.yaml` 只有 reviewer 角色，没有具备启动隔离服务与浏览器能力的 tester，正式质量流水线启用前需补合适成员配置。
- 文件消息可保留元数据，但附件正文是否在任务执行前自动下载和注入尚未定义。
- bundled runner 仍兼容旧任务全局结果；第三方旧 runner 也可继续使用服务端兼容路径。
- 无 lease 的历史 `running` 任务不会自动回收；业务重试上限与退避策略尚未定义。
- 项目级 `Members / Activity` 独立页面、observer 与返工尚未实现；当前 Hall 列表继续兼容无 `project_id` 的旧 Group。
- pi 的真实模型在“逐字回复”类任务上可能改写为简短确认，属于模型输出质量边界；基础设施已保证只写一条结果并正确推进状态。
- BS-3a 真实模型最终汇总质量补验属于 Discussion Hall 后续项，不阻塞当前里程碑。

## Next Slice

1. TH-6a2：实现根控制状态、有限批次授权、暂停 / 继续 / 整树终止和 bundled runner 最长 5 秒控制检查；这是下一候选代码切片。
2. TH-6a3 / TH-6b：依次实现澄清轮次账本、显式答复提交、`needs_decision`，再接领取前预检、完整 Hall 上下文重放与自动澄清闭环。
3. TH-6c / TH-6d：实现 Review / 返工门禁、业务角色发现、里程碑黑盒测试、Blackboard 控制和人工验收暂停。
4. TH-7：最后补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。

## Verification

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_codex_bridge.py`：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `node --check web\app.js` 与 `git diff --check`：通过。
- 定向 Web / runner / client 测试：`Ran 124 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：清理真实验收服务后 `Ran 321 tests in 98.917s ... OK`；首次并行运行有一个既有 WS 降级测试 2 秒清理超时，该用例随后连续两次单测通过。
- Browser 真实交互：登录、项目空态、委派、Hall 消息、runner 回写、结果待收取、点击收取、已结束分栏全部通过；最终控制台 error / warning 为 0。
- 真实 CLI：Codex 与 pi 均完成 claim → 执行 → 单条 Hall 结果 → collect；Codex 精确遵循测试正文，pi 基础确认链通过但逐字遵循仍有质量差异。
- 2026-07-16 人工页面测试：项目管理者成功拿到委派任务返回结果；本次收工仅记录后续设计与边界，没有新增代码验证。
- 2026-07-16 委派治理讨论：完成现有代码与协议的只读核对，确认当前深度 / 并发主要是运行路径软保护，澄清尚无轮次限制；本次仅更新进度文档，未修改或运行功能代码。
- 2026-07-18 TH-6a0：完成任务树治理、可中断推进、澄清和 Review/Test 门禁合同落盘；文档检查结果见本轮历史记录，未运行功能测试。
- 2026-07-18 TH-6a1：`py_compile` 通过；任务路由 `Ran 23 tests ... OK`，活服务 SDK `Ran 12 tests ... OK`，Task Hall / runner / bridge 跨模块 `Ran 128 tests ... OK`，全量 `Ran 325 tests in 103.757s ... OK`。
- 2026-07-18 发布前复跑：全量 `Ran 325 tests`，其中 324 项通过；既有 `test_disconnect_falls_back_to_http_polling` 在固定 2 秒退出等待中超时。该用例随后连续单跑 2 次通过，`tests.test_tasks + tests.test_talk_client` 定向回归 `Ran 35 tests ... OK`；本次未修改 WebSocket 降级路径。

## Known Debt

- 双通道输出仍可能让 agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 业务角色注入与 BS-3a 最终汇总质量仍有低优先级真实模型补验。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
