# Project Progress

## Latest

Updated: 2026-08-16 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- 项目管理者确认本地 dogfood 暂时只使用 3 个 Agent：`agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:pi`（pi + Kimi3 / Reviewer / execution）；Claude Code 与重复的 `agent:pi-kimi` 不再使用。
- `pi_bridge.py` 已增加 `--pi-provider / --pi-model`，可将消息、Task runner 与预检统一锁定到 `moonshotai-cn/kimi-k3`；DeepSeek Harness 通过通用 bridge + `dsh.cmd --profile headless` 接入。
- 当前 Codex 为决策 Agent；本轮按数据库 / 协议 / 前端高风险单切片刹车，仅完成 TH-6d，不直接进入 TH-7。
- TH-6a1 至 TH-6c 的任务树、有限授权、中断、澄清、runner 预检与 Review / 返工门禁保持完成状态。
- TH-6d 已完成：根任务可标记 `milestone_test_required`；Test 必须覆盖完整最新冻结版本集，并在所有必需 Review 通过后创建。
- `failed` Test 可触发返工；返工形成新冻结版本后，旧 Review / Test 结论自动失去覆盖资格，必须重新 Review 并对最新完整冻结集执行 Test。
- 非里程碑批次在额度耗尽、既有任务安全收尾且 Review 通过后自动进入 `awaiting_human / batch_limit`；里程碑 Test 通过后自动进入 `awaiting_human / milestone`。
- Human 可通过 `POST /api/tasks/{id}/accept-milestone` 或 Blackboard 的“人工验收通过”完成当前里程碑验收；动作递增授权 epoch，但不自动增加下一批开发额度。
- Project Blackboard 已增加根治理、Review / Test 门禁摘要、类型化子任务创建、澄清答复、人工决策、暂停 / 风险检查点 / 有限恢复 / 里程碑验收 / 整树终止入口。
- TH-6d 自动化与真实浏览器闭环均已通过，当前按里程碑门禁暂停，等待项目管理者人工验收。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务，并可进入每项独立 Task Hall。
- Human 创建可委派根任务时可选择 1–3 个开发切片额度和里程碑 Test，并可从根详情创建 `development / review / test / rework` 子任务；根执行 Agent 通过 API / SDK 执行同一合同。
- 根详情展示控制状态、检查点、授权 epoch、剩余切片、非终态后代、每个最新冻结版本的 Review 结论和完整 Test 结论。
- Review / Test 继续使用独立 Task Hall 和结构化 `gate_verdict`；服务端不从自然语言猜测通过结论。
- 根任务成功完成前会原子检查非终态后代、最新开发 / 返工结果、必需 Review 和里程碑 Test；旧 `general` 任务保持兼容。
- async / sync SDK 已支持 `milestone_test_required` 和 `accept_task_milestone()`；数据库迁移会为旧任务回填 `false` 并建立索引。
- 用户手册已同步当前 Blackboard 控制、质量任务和里程碑人工验收操作。

## Current Boundaries

- 服务端能验证任务类型、冻结关系、Reviewer 分离和结构化结论，但不能从自由文本业务角色证明第三方 Tester 具备隔离服务、API、浏览器和日志权限；管理员仍需配置真实工具能力。
- `.talk/groups.yaml` 已收敛为 Codex / DeepSeek / Kimi3 三个 Agent，但运行中 `group:talk-dev` 的旧成员关系不会被 `talk sync` 自动删除，人工验收前需在群成员面板删除 Claude / pi-kimi 并加入 DeepSeek。
- 当前仍没有正式的全能力 Tester；Kimi3 可在 `tools` 档执行 API / 日志 / 测试检查，浏览器仍由项目管理者人工验收。
- Review / Test 结论必须由对应质量任务 runner / SDK 随 `complete` 提交，Human Web 页面只负责查看与控制，不能手工伪造 verdict。
- 单任务运行中取消仍未开放；整树暂停 / 终止已由服务端撤权，第三方 runner 需自行实现最长约 5 秒的控制探针。
- 附件只重放文件元数据，执行前自动下载与正文注入尚未定义。
- 预检失败后的跨轮询重试没有独立上限与退避；多个 bridge 实例的消息级原子去重仍未完成。
- 普通 Codex Desktop 会话尚未自动注册 TALK MCP；TH-7 再补通用终端接入包装。
- 项目级 `Members / Activity` 独立页面和 observer 视图尚未实现。

## Next Slice

1. 启动 TALK Server 与 Codex / DeepSeek Harness / Kimi3 三个 bridge，注册 `agent:deepseek`，同步项目 Agent 索引并人工调整 `group:talk-dev` 成员。
2. 项目管理者用新三 Agent 拓扑人工验收 TH-6d：重点检查里程碑 Test 通过后的自动暂停、门禁摘要、人工验收按钮以及返工后旧结论失效。
3. 验收通过后进入 TH-7：补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。
4. 后续再处理正式 Tester profile、附件正文注入、预检退避和跨实例消息级去重。

## Verification

- Python 编译检查：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、async / sync SDK 与相关测试文件通过 `py_compile`。
- JavaScript 语法检查：`node --check web/app.js` 通过。
- 定向任务测试曾分别验证里程碑 Test、批次自动检查点、Test 失败返工、旧结论失效、Web 静态入口和 SDK 活服务行为，均通过。
- 最终全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q`，`Ran 370 tests in 122.729s ... OK`。
- Codex in-app Browser 真实验证：Human 登录并创建带里程碑 Test 的可委派根任务；页面创建开发子任务；本地测试 Agent 完成 Review 与完整 Test；根任务自动显示 `awaiting_human / milestone` 和 `passed`；点击“人工验收通过”后恢复 `active`、授权 epoch 从 1 增至 2、剩余开发额度仍为 0。
- 浏览器页面控制台 `error / warning` 为 0；质量任务表单已补稳定可访问名称。
- `usage-gate.cmd guard --provider codex --json` 返回 `decision=continue`；session / weekly 精确百分比均为 `null`，未臆测具体用量。本轮仍按高风险单切片和里程碑人工验收门禁停止。
- 本地 runtime 核对：Codex `0.144.4`、pi `0.84.1`、DeepSeek Harness `dsh 0.1.0-rc.6`；`dsh --profile headless --help` 确认支持一次性 argv 任务。
- pi 模型核对：`moonshotai-cn/kimi-k3` 存在，`pi auth check --provider moonshotai-cn --model kimi-k3 --json --no-refresh` 返回 `ready`。
- 定向回归：`.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge tests.test_talk_cli -q` → `Ran 145 tests ... OK`；`py_compile` 与 `git diff --check` 通过。
- 未调用 Kimi3 / DeepSeek 真实模型，未消耗模型额度；真实 bridge 往返留待人工验收。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- Tester 操作系统级硬隔离、附件正文注入、预检退避和跨实例消息级去重仍需后续加强。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 用户操作手册：`docs/guides/USER_MANUAL.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
