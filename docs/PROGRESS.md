# Project Progress

## Latest

Updated: 2026-08-21 (Asia/Shanghai)

- 当前分支：`codex/task-hall`；当前 Codex 为决策 Agent。
- TH-6d 代码、自动化回归与隔离浏览器闭环保持完成，但 2026-08-16 开始的本地三 Agent 真实人工验收**尚未通过**，当前暂停验收且不进入 TH-7。
- 本地 dogfood 拓扑固定为 `agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:pi`（pi + `moonshotai-cn/kimi-k3` / Reviewer / execution）；Claude Code 与重复的 `agent:pi-kimi` 不再使用。
- DeepSeek Harness 本机全局版本已从 `0.1.0-rc.6` 固定升级至 `0.1.0-rc.8`；CLI、`headless` profile、原生模块与最小真实模型调用均通过，临时备份已在验证成功后清理。
- 人工验收已创建根任务 `#10`（Codex）和 Development 子任务 `#11`（DeepSeek）；DeepSeek 未认领 `#11`。当前所有 bridge 进程均已停止，数据库仍保留 `#10 running/in_progress`、`#11 queued/assigned` 的现场快照。
- 验收发现两个前端问题：委派任务弹窗卡片透明；根任务与子任务共用“执行 Agent”标签，未清楚说明两阶段分配关系。
- DeepSeek Windows 多行 prompt 丢失问题已修复：通用 bridge 识别并校验官方 `dsh.cmd` npm shim 后，直接以 Node 启动 Harness；配置命令保持不变，非 DSH `.cmd` 不受影响。
- DeepSeek 预检跨轮询无限重试已修复：同一任务最多 3 个连续预检轮询，第 3 次仍失败时写入 Task Hall 提示并持久化为 `failed`，不会进入第 4 次；预检成功会清零此前失败计数。

## Current Snapshot

- Web UI 的实际委派流程是两阶段：先从“＋委派任务”创建根任务并选择根负责人，再从根详情的“创建开发 / Review / Test 子任务”选择子任务类型与子任务执行 Agent。
- `group:talk-dev` 实际不存在于 `talk.db`；`.talk/groups.yaml` 只提供本地角色/profile 元数据，不代表服务端已有同名 Hall。此前要求在该群成员面板删除/添加 Agent 的人工指引无效，已从后续计划移除。
- TH-6d 服务端合同仍包含任务树控制、有限授权、澄清、Development / Review / Test / rework 关系、结构化质量门禁和里程碑人工验收。
- `pi_bridge.py` 已能显式锁定 `moonshotai-cn/kimi-k3`；DeepSeek Harness 已升级到 `0.1.0-rc.8`。DeepSeek 配置仍写作通用 bridge + `dsh.cmd --profile headless`，但 Windows 实际子进程已由 bridge 安全解析为官方 Harness Node 入口，不再经过会截断多行参数的 `.cmd` 转发。
- 2026-08-21 只读复核时，本地 Server 与三个 bridge 均未运行；旧任务树 `#10/#11` 仅作为故障证据保留，修复后应先安全清理或另建验收任务树。

## Current Boundaries

- `.modal-card` 只定义尺寸与滚动，没有卡片背景、边框和阴影；视觉卡片样式只覆盖 `.group-create-panel` 等选择器，导致 `.task-create-panel.modal-card` 透明。
- 根任务和子任务弹窗共用静态“执行 Agent”标签；建议按上下文改为“根任务负责人”和“子任务执行 Agent”，并补充两阶段说明。
- DeepSeek Harness `0.1.0-rc.8` 的 `headless` profile、登录和 `deepseek-v4-pro` 调用本身可用；Windows npm `dsh.cmd` 多行参数边界已由 Node 入口直启方案修复，并有 shim 识别、非 DSH 保持原样和多行单 argv 回归覆盖。
- 一个预检轮询仍包含正常提示和最多一次协议修复，因此 3 个轮询上限最多触发 6 次预检 CLI 调用；上限由 worker 进程内计数，达到第 3 次后的 `failed` 终态会持久化，但达到上限前若人为重启 bridge，未完成计数不会跨进程继承。
- 当前仍没有正式的全能力 Tester；Kimi3 可执行 API、日志和自动化检查，浏览器仍由项目管理者人工验收。
- 附件正文注入、跨实例消息级原子去重、普通 Codex Desktop 自动注册 TALK MCP、项目级 Members / Activity 页面仍未完成。

## Next Slice

1. 下一切片单独修复委派任务弹窗背景和上下文标签，使用 Codex Browser 验证根任务/子任务两阶段流程与可访问名称；开始前等待项目管理者确认。
2. 修复验证通过后，安全处理旧 `#10/#11` 现场，从新根任务开始重新执行 Codex → DeepSeek → Kimi3 的 Development / Review / Test / 人工验收完整闭环。
3. 只有真实三 Agent 人工验收通过后才进入 TH-7；之后再处理正式 Tester、附件正文注入、跨实例去重等债务。

## Verification

- 多行 prompt 切片定向回归：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q` → `Ran 140 tests in 0.574s`，`OK`。
- 多行 prompt 切片全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 373 tests in 105.003s`，`OK`。
- 本机命令解析确认 `dsh.cmd --profile headless` 被转换为 `node.exe ...\@deepseek-ai\dsh\lib\bin.js --profile headless`；受控真实四行 prompt 同时携带首行、中文正文与末行约束，模型只返回 `DSH_MULTILINE_OK`。
- 预检重试切片定向回归：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q` → `Ran 143 tests in 0.543s`，`OK`。
- 预检重试切片全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 376 tests in 105.860s`，`OK`；模拟失败严格停在第 3 次，没有调用真实模型。
- `dsh --version` 与 `npm list -g @deepseek-ai/dsh --depth=0` 均确认 `0.1.0-rc.8`；`dsh --profile headless --help` 正常加载现有 profile。
- npm 全局安装的 6 个生命周期脚本结果均为退出码 0；`node-pty` 与 `koffi` 原生模块可加载，最小真实请求返回 `DSH_RC8_OK`。
- `.dsh` 临时备份曾校验 121 个真实文件 SHA-256 与 510 个 Junction 结构；升级验证通过后已安全删除，`NODE_OPTIONS` 未持久化且无残留 Node/DSH 进程。
- Codex Browser 真实复现弹窗：`.task-create-panel` 计算样式为透明背景、无边框、无阴影；DOM 确认根/子任务模式都使用“执行 Agent”。
- SQLite 只读核对：`#10 = running/in_progress -> agent:codex`，`#11 = queued/assigned -> agent:deepseek` 且从未 claim；最新 DeepSeek instance error 为 `task preflight did not return a valid TALK_TASK_PREFLIGHT decision`。
- 修复前 DSH 持久 session 只读解码曾确认：provider/model 为 `deepseek-official/deepseek-v4-pro`，但实际用户消息仅保留 prompt 第一行；该根因现已修复，旧 session 仍只作为历史证据保留。
- `group:talk-dev` 数据库查询返回空；2026-08-21 进程核对确认旧 Server/bridge 进程均已停止。
- `git status --short --branch` 在汇总前为干净的 `codex/task-hall...origin/codex/task-hall`；仅出现无法读取用户级 global ignore 的沙箱警告，不影响仓库状态判断。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- Tester 操作系统级硬隔离、附件正文注入和跨实例消息级去重仍需后续加强。

## References

- 当前模块合同：`docs/spec/MODULE_bridges.md`
- 用户操作手册：`docs/guides/USER_MANUAL.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
