# Project Progress

## Latest

Updated: 2026-08-27 (Asia/Shanghai)

- 当前分支：`codex/task-hall`；当前 Codex 为决策 Agent。Kimi prompt mode 修复提交 `921fbb1`（`修复 Kimi prompt 模式参数冲突`）已推送到 `origin/codex/task-hall`。
- Kimi 活动成员已从 `agent:pi`（pi + Kimi3）迁移为 `agent:kimi`（官方 Kimi Code CLI）；当前本地 dogfood 固定拓扑为 `agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:kimi`（Kimi Code / Reviewer / execution）。
- 项目管理者已完成 Kimi 登录；真实 `kimi -p` 最小调用返回 `KIMI_LOGIN_OK`。Kimi Code CLI 版本为 `0.38.0`。
- 第一次原生三 Agent 验收树为根任务 `#12`、Development `#13`、Review `#14`。DeepSeek 已真实完成 `#13` 并生成受控验收文件；Kimi 在 `#14` 领取前预检暴露真实兼容问题：Kimi `0.38.0` 拒绝同时使用 `--prompt` 与 `--auto`。
- `bridges/kimi_bridge.py` 已移除 prompt mode 的 `--auto`；Kimi 讨论与预检仍无工具，任务默认 `review` 档仅开放 `Read / Grep / Glob / Bash`，能力范围由受控 Agent 文件白名单限制。真实 Read 工具冒烟返回 `KIMI_PROMPT_TOOL_OK`。
- 旧根任务 `#12` 随后因嵌套 Codex CLI workspace 额度耗尽失败；该失败不是 TALK 协议或 Kimi 登录问题。新的验收树已改由当前 Codex Desktop 会话直接作为 Lead，通过 SDK/API 协调 DeepSeek 与 Kimi，没有启动嵌套 Codex bridge。
- 第二次真实验收树已跑通自动门禁：根任务 `#15`、Development `#16`、Review `#17`、Test `#18`。DeepSeek 完成受控开发；Kimi Review 为 `approved` 且无 findings；Kimi Test 为 `passed` 且实跑 `119` 项定向回归。根任务已由服务端自动进入 `control_status=awaiting_human`、`checkpoint_reason=milestone`。
- 通用 bridge 已接入 Kimi `stream-json` 最终 Assistant 文本提取，Group Hall、任务预检、正式执行和 Review/Test 门禁均走统一归一化。
- pi bridge 及其测试仍保留为兼容入口，但 `agent:pi` / `agent:pi-kimi` 不再是当前活动成员；旧数据库历史不迁移、不删除。
- TH-6d 的实现层自动化与原生三 Agent 任务树均已通过；当前停在人工验收门禁。项目管理者点击“人工验收通过”前不宣告 TH-6d 完成、不进入 TH-7。

## Current Snapshot

- `.talk/groups.yaml` 已同步到 TALK Server，活动档案扫描结果精确为 `agent:codex / agent:deepseek / agent:kimi` 三个成员；旧数据库 `agent:pi` 仅保留历史记录。
- 旧任务 `#12/#13/#14` 保留为失败现场，不复用。新根任务 `#15` 的 Task Hall 为 `group:task-2d0cf86216b742f3adc157a3695ebeef`；Lead 汇总消息为 `#2479`。
- Development `#16` 已 `succeeded/completed`，结果消息 `#2476`；Review `#17` 已 `succeeded/completed`，结果消息 `#2477`、门禁 `approved`；Test `#18` 已 `succeeded/completed`，结果消息 `#2478`、门禁 `passed`。Review/Test 都通过 relation 绑定冻结的 `#16`。
- `.tmp/th6d-native-kimi-acceptance-v2.txt` 为本轮受控产物：65 bytes、UTF-8 无 BOM、末尾 LF，SHA-256 为 `602FBC88D523943F2798942F0F898B354834372C1BC53AEECBF3233FAC2743DF`。V1/V2 两个验收文件都保持 untracked，不进入提交。
- TALK Server、DeepSeek bridge 与 Kimi bridge 当前保持运行，供项目管理者在 `http://127.0.0.1:8000` 执行人工验收。当前 Codex Desktop instance 已回报 `idle`。

## Current Boundaries

- Kimi `review` 档没有 `Edit / Write`，但包含 `Bash` 以运行检查与测试；这是 TALK 系统合同和 Kimi 工具白名单约束，不是操作系统级只读沙箱。
- Kimi Code CLI 当前没有本切片已验证的无会话开关；每次 `-p` 调用可能保留官方会话记录。本项目不自动删除这些记录，后续再评估归档策略。
- 当前仍没有正式的全能力 Tester；Kimi 可执行 API、日志和自动化检查，真实浏览器人工验收仍由项目管理者完成。
- 附件正文注入、跨实例消息级原子去重、普通 Codex Desktop 自动注册 TALK MCP、项目级 Members / Activity 页面仍未完成。

## Next Slice

1. 项目管理者打开 `http://127.0.0.1:8000`，进入根任务 `#15`，依次查看 Development `#16`、Review `#17`、Test `#18` 的 Task Hall 与根 Hall 汇总消息 `#2479`。
2. 确认页面显示“里程碑待人工验收”、Review=`approved`、Test=`passed` 后，点击“人工验收通过”，再通知当前 Codex 会话继续收尾。
3. 人工验收完成后核对根树最终状态、更新 TH-6d 结论并提交推送；随后再决定是否进入 TH-7。旧 `#10/#11/#12/#13/#14` 均不得复用。

## Verification

- Kimi 登录冒烟：`kimi -p "只输出 KIMI_LOGIN_OK"` → `KIMI_LOGIN_OK`。
- Kimi prompt mode 真实工具冒烟：使用临时 Read-only Agent 文件读取受控 marker → `KIMI_PROMPT_TOOL_OK`，退出码 `0`；临时 Agent 文件已删除。
- Kimi / 通用 bridge 定向回归：`.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q` → `Ran 119 tests in 0.913s`，`OK`。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 389 tests in 170.772s`，`OK`。
- Kimi Review `#17` 真实执行文件内容、字节、BOM、末尾换行、SHA-256、Git tracked 状态与结果消息一致性核验 → `approved`，`findings=[]`。
- Kimi Test `#18` 独立执行 `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q` → `Ran 119 tests in 1.052s`，`OK`；同时完成 marker 黑盒、Git 状态和 Review 门禁核验 → `passed`，`findings=[]`。
- 服务端任务树快照：Review gate 指向冻结 `#16` 且 verdict=`approved`；Test gate 的 `frozen_task_ids=[16]`、verdict=`passed`、`satisfied=true`；根任务 `#15` 自动暂停为 `awaiting_human/milestone`。
- `py_compile` 与 `git diff --check` 通过；`git diff --check` 只有 Windows LF/CRLF 提示。
- 第一次真实验收确认 DeepSeek 能领取并完成 Development；Kimi 的失败发生在领取前预检且安全重试三次后停止，没有误认领任务。
- 本切片没有前端改动；自动化与 API/任务树黑盒已通过，真实浏览器中的最终人工验收按门禁留给项目管理者执行。

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
