# Project Progress

## Latest

Updated: 2026-08-27 (Asia/Shanghai)

- 当前分支：`codex/task-hall`；当前 Codex 为决策 Agent。本切片已创建中文本地提交 `迁移 Kimi 到官方 CLI bridge`，`origin/codex/task-hall` 仍为 `14bd3d8`；外部推送等待项目管理者明确授权。
- Kimi 活动成员已从 `agent:pi`（pi + Kimi3）迁移为 `agent:kimi`（官方 Kimi Code CLI）；当前本地 dogfood 固定拓扑为 `agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:kimi`（Kimi Code / Reviewer / execution）。
- 新增 `bridges/kimi_bridge.py`：讨论与领取前预检无工具，任务默认 `review` 档开放 `Read / Grep / Glob / Bash`，显式 `tools` 档才额外开放 `Edit / Write`；所有档位禁用子 Agent，并用受控空 `--skills-dir` 隔离自动发现的 Skills。CLI 显式使用 `--auto` 避免无人值守权限询问，能力范围仍由工具白名单限制。
- 通用 bridge 已接入 Kimi `stream-json` 最终 Assistant 文本提取，Group Hall、任务预检、正式执行和 Review/Test 门禁均走统一归一化。
- pi bridge 及其测试仍保留为兼容入口，但 `agent:pi` / `agent:pi-kimi` 不再是当前活动成员；旧数据库历史不迁移、不删除。
- TH-6d 的实现层自动化与隔离浏览器闭环仍有效，但新三 Agent 真实人工验收尚未执行，不进入 TH-7。

## Current Snapshot

- `.talk/groups.yaml` 与项目角色档案已切换到 `agent:kimi`；旧 `.talk/agents/agent_pi/` 活动档案已移除，新增 `.talk/agents/agent_kimi/`。
- Kimi Code CLI 本机版本为 `0.38.0`，命令与受控 Agent 文件可被 CLI 正确解析；真实模型冒烟在调用前被本机配置门禁拦截：`No model configured`。
- 项目管理者需在本机执行 `kimi login`（或在 Kimi Code 中配置 `default_model`）后，才能启动真实 Kimi bridge 并完成三 Agent 验收。
- 当前 TALK Server 与三个 bridge 均未启动；本切片没有创建新任务、没有改动旧 `#10/#11`。旧树保持 `canceled/canceled`，不得复用。

## Current Boundaries

- Kimi `review` 档没有 `Edit / Write`，但包含 `Bash` 以运行检查与测试；这是 TALK 系统合同和 Kimi 工具白名单约束，不是操作系统级只读沙箱。
- Kimi Code CLI 当前没有本切片已验证的无会话开关；每次 `-p` 调用可能保留官方会话记录。本项目不自动删除这些记录，后续再评估归档策略。
- 当前仍没有正式的全能力 Tester；Kimi 可执行 API、日志和自动化检查，真实浏览器人工验收仍由项目管理者完成。
- 附件正文注入、跨实例消息级原子去重、普通 Codex Desktop 自动注册 TALK MCP、项目级 Members / Activity 页面仍未完成。

## Next Slice

1. 项目管理者完成 `kimi login` 或默认模型配置，并确认 Kimi CLI 可返回一次最小真实结果。
2. 同步 `.talk/groups.yaml` 到 TALK Server，启动 Server、Codex、DeepSeek、Kimi 三个 bridge，从全新根任务重新执行 Development / Review / Test / 人工验收完整闭环。
3. 只有真实三 Agent 人工验收通过后才进入 TH-7；不得复用已取消的 `#10/#11`。

## Verification

- Kimi / 通用 bridge 定向回归：`.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q` → `Ran 119 tests`，`OK`。
- Bridge / profile / CLI 组合回归：`.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_profiles tests.test_talk_cli -q` → `Ran 196 tests in 9.713s`，`OK`。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 389 tests in 109.913s`，`OK`。
- `python bridges/kimi_bridge.py --help`、`py_compile` 和 `git diff --check` 均通过；`git diff --check` 只有 Windows LF/CRLF 提示。
- 本机真实 Kimi 命令正确读取受控无工具 Agent 文件并输出 `stream-json` meta，随后因未登录/未配置默认模型退出码为 1；未产生模型答案，不能记为端到端通过。
- 本切片没有前端改动，因此未重复执行 Browser 验证。
- 本地 Git 提交已创建；首次沙箱内 push 因无可用凭据失败，外部凭据 push 又被授权门禁拒绝，因此本轮没有把提交推送到 GitHub。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是兼容入口的临时规避，等待 upstream 修复后移除。
- Tester 操作系统级硬隔离、Kimi 会话保留策略、附件正文注入和跨实例消息级去重仍需后续加强。

## References

- 当前 bridge 合同：`docs/spec/MODULE_bridges.md`
- 当前任务合同：`docs/spec/MODULE_tasks.md`
- 用户操作手册：`docs/guides/USER_MANUAL.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
