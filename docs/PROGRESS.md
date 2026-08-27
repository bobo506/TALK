# Project Progress

## Latest

Updated: 2026-08-27 (Asia/Shanghai)

- 当前分支：`codex/task-hall`；当前 Codex 为决策 Agent。Kimi 迁移提交 `522635d` 与进度提交 `5b54df6` 已推送到 `origin/codex/task-hall`。
- Kimi 活动成员已从 `agent:pi`（pi + Kimi3）迁移为 `agent:kimi`（官方 Kimi Code CLI）；当前本地 dogfood 固定拓扑为 `agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:kimi`（Kimi Code / Reviewer / execution）。
- 项目管理者已完成 Kimi 登录；真实 `kimi -p` 最小调用返回 `KIMI_LOGIN_OK`。Kimi Code CLI 版本为 `0.38.0`。
- 第一次原生三 Agent 验收树为根任务 `#12`、Development `#13`、Review `#14`。DeepSeek 已真实完成 `#13` 并生成受控验收文件；Kimi 在 `#14` 领取前预检暴露真实兼容问题：Kimi `0.38.0` 拒绝同时使用 `--prompt` 与 `--auto`。
- `bridges/kimi_bridge.py` 已移除 prompt mode 的 `--auto`；Kimi 讨论与预检仍无工具，任务默认 `review` 档仅开放 `Read / Grep / Glob / Bash`，能力范围由受控 Agent 文件白名单限制。真实 Read 工具冒烟返回 `KIMI_PROMPT_TOOL_OK`。
- 旧根任务 `#12` 随后因嵌套 Codex CLI workspace 额度耗尽失败；该失败不是 TALK 协议或 Kimi 登录问题。后续新验收树改由当前 Codex Desktop 会话直接作为 Lead，通过 SDK/API 协调 DeepSeek 与 Kimi，不再启动嵌套 Codex bridge。
- 通用 bridge 已接入 Kimi `stream-json` 最终 Assistant 文本提取，Group Hall、任务预检、正式执行和 Review/Test 门禁均走统一归一化。
- pi bridge 及其测试仍保留为兼容入口，但 `agent:pi` / `agent:pi-kimi` 不再是当前活动成员；旧数据库历史不迁移、不删除。
- TH-6d 的实现层自动化与隔离浏览器闭环仍有效；原生 Kimi 参数缺陷已修复，但新的完整三 Agent 任务树尚未跑完，不进入 TH-7。

## Current Snapshot

- `.talk/groups.yaml` 已同步到 TALK Server，活动档案扫描结果精确为 `agent:codex / agent:deepseek / agent:kimi` 三个成员；旧数据库 `agent:pi` 仅保留历史记录。
- 旧任务 `#12/#13/#14` 保留为失败现场，不复用。`#13` 结果消息为 `#2473`；`#14` 参数冲突失败消息为 `#2474`；根任务额度失败消息为 `#2475`。
- `.tmp/th6d-native-kimi-acceptance.txt` 是 `#13` 生成的未跟踪验收产物，内容与 SHA-256 已核对；不会进入提交。
- 当前 TALK Server 与所有 bridge 在中断恢复时均已停止，`8000` 端口空闲。修复基线提交推送后，将只启动 DeepSeek 与 Kimi bridge；当前 Codex 会话直接承担 Lead。

## Current Boundaries

- Kimi `review` 档没有 `Edit / Write`，但包含 `Bash` 以运行检查与测试；这是 TALK 系统合同和 Kimi 工具白名单约束，不是操作系统级只读沙箱。
- Kimi Code CLI 当前没有本切片已验证的无会话开关；每次 `-p` 调用可能保留官方会话记录。本项目不自动删除这些记录，后续再评估归档策略。
- 当前仍没有正式的全能力 Tester；Kimi 可执行 API、日志和自动化检查，真实浏览器人工验收仍由项目管理者完成。
- 附件正文注入、跨实例消息级原子去重、普通 Codex Desktop 自动注册 TALK MCP、项目级 Members / Activity 页面仍未完成。

## Next Slice

1. 提交并推送 Kimi prompt mode 参数兼容修复与本次进度记录；验收产物不纳入提交。
2. 启动 TALK Server、DeepSeek bridge 与 Kimi bridge；由当前 Codex 会话从全新根任务执行 Development / Review / Test 闭环。
3. Test 门禁通过后保持根任务 `awaiting_human`，向项目管理者提供人工验收入口；只有项目管理者明确验收通过后才进入 TH-7。旧 `#10/#11/#12/#13/#14` 均不得复用。

## Verification

- Kimi 登录冒烟：`kimi -p "只输出 KIMI_LOGIN_OK"` → `KIMI_LOGIN_OK`。
- Kimi prompt mode 真实工具冒烟：使用临时 Read-only Agent 文件读取受控 marker → `KIMI_PROMPT_TOOL_OK`，退出码 `0`；临时 Agent 文件已删除。
- Kimi / 通用 bridge 定向回归：`.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q` → `Ran 119 tests in 0.913s`，`OK`。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 389 tests in 170.772s`，`OK`。
- `py_compile` 与 `git diff --check` 通过；`git diff --check` 只有 Windows LF/CRLF 提示。
- 第一次真实验收确认 DeepSeek 能领取并完成 Development；Kimi 的失败发生在领取前预检且安全重试三次后停止，没有误认领任务。
- 本切片没有前端改动，因此未重复执行 Browser 验证。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是兼容入口的临时规避，等待 upstream 修复后移除。
- Tester 操作系统级硬隔离、Kimi 会话保留策略、附件正文注入和跨实例消息级去重仍需后续加强。
- 嵌套 Codex CLI 当前 workspace 额度耗尽；本轮验收使用当前 Codex Desktop 会话作为实际操作终端，不把额度问题误判为产品缺陷。

## References

- 当前 bridge 合同：`docs/spec/MODULE_bridges.md`
- 当前任务合同：`docs/spec/MODULE_tasks.md`
- 用户操作手册：`docs/guides/USER_MANUAL.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
