# Project Progress

## Latest

Updated: 2026-08-21 (Asia/Shanghai)

- 当前分支：`codex/task-hall`；当前 Codex 为决策 Agent。
- TH-6d 代码、自动化回归与隔离浏览器闭环保持完成，但 2026-08-16 开始的本地三 Agent 真实人工验收**尚未通过**，当前暂停验收且不进入 TH-7。
- 本地 dogfood 拓扑固定为 `agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:pi`（pi + `moonshotai-cn/kimi-k3` / Reviewer / execution）；Claude Code 与重复的 `agent:pi-kimi` 不再使用。
- DeepSeek Harness 本机全局版本已从 `0.1.0-rc.6` 固定升级至 `0.1.0-rc.8`；CLI、`headless` profile、原生模块与最小真实模型调用均通过，临时备份已在验证成功后清理。
- 人工验收已创建根任务 `#10`（Codex）和 Development 子任务 `#11`（DeepSeek）；DeepSeek 未认领 `#11`。当前所有 bridge 进程均已停止，数据库仍保留 `#10 running/in_progress`、`#11 queued/assigned` 的现场快照。
- 验收发现两个前端问题：委派任务弹窗卡片透明；根任务与子任务共用“执行 Agent”标签，未清楚说明两阶段分配关系。
- 验收发现两个 DeepSeek 接入问题：Windows `dsh.cmd` 的 argv 边界丢失多行 prompt，只把首行送入 Harness；预检协议失败后 bridge 会跨轮询无限重试并重复调用模型。
- 项目管理者决定先升级 DeepSeek Harness 运行时基线，再修复上述验收阻断项；运行时升级现已完成，下一步仍优先处理 Windows 多行 prompt 与预检重试保护。

## Current Snapshot

- Web UI 的实际委派流程是两阶段：先从“＋委派任务”创建根任务并选择根负责人，再从根详情的“创建开发 / Review / Test 子任务”选择子任务类型与子任务执行 Agent。
- `group:talk-dev` 实际不存在于 `talk.db`；`.talk/groups.yaml` 只提供本地角色/profile 元数据，不代表服务端已有同名 Hall。此前要求在该群成员面板删除/添加 Agent 的人工指引无效，已从后续计划移除。
- TH-6d 服务端合同仍包含任务树控制、有限授权、澄清、Development / Review / Test / rework 关系、结构化质量门禁和里程碑人工验收。
- `pi_bridge.py` 已能显式锁定 `moonshotai-cn/kimi-k3`；DeepSeek Harness 已升级到 `0.1.0-rc.8`，但当前仍通过通用 bridge + `dsh.cmd --profile headless` 接入，此 Windows 启动方式已被真实验收证明不适合多行 TALK prompt。
- 2026-08-21 只读复核时，本地 Server 与三个 bridge 均未运行；旧任务树 `#10/#11` 仅作为故障证据保留，修复后应先安全清理或另建验收任务树。

## Current Boundaries

- `.modal-card` 只定义尺寸与滚动，没有卡片背景、边框和阴影；视觉卡片样式只覆盖 `.group-create-panel` 等选择器，导致 `.task-create-panel.modal-card` 透明。
- 根任务和子任务弹窗共用静态“执行 Agent”标签；建议按上下文改为“根任务负责人”和“子任务执行 Agent”，并补充两阶段说明。
- DeepSeek Harness `0.1.0-rc.8` 的 `headless` profile、登录和 `deepseek-v4-pro` 调用本身可用；故障仍位于 TALK `--prompt-transport argv` 经 Windows npm `dsh.cmd` 包装的多行参数传输边界。首选修复是绕过 `.cmd`，直接调用 Harness Node 入口，并增加多行 prompt 回归测试。
- 一个预检轮询会先运行正常提示，再运行一次协议修复提示；两次输出都无效后，worker 仅上报 error 并在下一轮继续，曾在数分钟内生成至少 24 个无效 DSH session。必须增加失败上限、退避或 poison-task 隔离，避免重复计费/消耗额度。
- 当前仍没有正式的全能力 Tester；Kimi3 可执行 API、日志和自动化检查，浏览器仍由项目管理者人工验收。
- 附件正文注入、跨实例消息级原子去重、普通 Codex Desktop 自动注册 TALK MCP、项目级 Members / Activity 页面仍未完成。

## Next Slice

1. 优先修复 DeepSeek Windows 接入：绕过 `dsh.cmd` 传递多行 prompt，并为预检失败实现有界重试/退避；添加 Windows 多行 argv 与跨轮询失败保护测试，再做一次受控真实模型探针。
2. 修复委派任务弹窗背景和上下文标签，使用 Codex Browser 验证根任务/子任务两阶段流程与可访问名称。
3. 修复验证通过后，安全处理旧 `#10/#11` 现场，从新根任务开始重新执行 Codex → DeepSeek → Kimi3 的 Development / Review / Test / 人工验收完整闭环。
4. 只有真实三 Agent 人工验收通过后才进入 TH-7；之后再处理正式 Tester、附件正文注入、跨实例去重等债务。

## Verification

- 上一实现切片的全量回归保持为 `.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 370 tests ... OK`；三 Agent 拓扑定向回归为 `Ran 145 tests ... OK`。本次只升级本机外部运行时并同步文档，未修改功能代码，因此未重新运行代码测试。
- `dsh --version` 与 `npm list -g @deepseek-ai/dsh --depth=0` 均确认 `0.1.0-rc.8`；`dsh --profile headless --help` 正常加载现有 profile。
- npm 全局安装的 6 个生命周期脚本结果均为退出码 0；`node-pty` 与 `koffi` 原生模块可加载，最小真实请求返回 `DSH_RC8_OK`。
- `.dsh` 临时备份曾校验 121 个真实文件 SHA-256 与 510 个 Junction 结构；升级验证通过后已安全删除，`NODE_OPTIONS` 未持久化且无残留 Node/DSH 进程。
- Codex Browser 真实复现弹窗：`.task-create-panel` 计算样式为透明背景、无边框、无阴影；DOM 确认根/子任务模式都使用“执行 Agent”。
- SQLite 只读核对：`#10 = running/in_progress -> agent:codex`，`#11 = queued/assigned -> agent:deepseek` 且从未 claim；最新 DeepSeek instance error 为 `task preflight did not return a valid TALK_TASK_PREFLIGHT decision`。
- DSH 持久 session 只读解码确认：provider/model 为 `deepseek-official/deepseek-v4-pro`，但实际用户消息仅保留 prompt 第一行；Harness 将其理解为接入握手，未看到任务正文和 `TALK_TASK_PREFLIGHT` 合同。
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
