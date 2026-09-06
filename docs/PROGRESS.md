# Project Progress

## Latest

- **当前优先事项改为界面评估与简化，TH-7 暂缓**。用户要求非编程人员也能看懂任务交接、完成状态与下一步；本次审计已完成，尚未修改产品代码或批准具体布局。
- 本次真实浏览器发现：从黑板 #15 经侧栏切换 Hall #9 后，标题变为 #9，但质量门禁与树操作仍沿用 #15 的任务树。另有完成态仍显示暂停/终止、无权限入口缺少可见反馈、主子任务平铺、技术信息过多与窄窗口横向溢出。

Updated: 2026-09-06 21:24 (Asia/Shanghai)

- 当前项目：TALK；当前分支：`codex/task-hall`；本轮 Codex 为决策 Agent，角色来源为 `AGENTS.md`。
- **TH-6d 已通过人工验收并完成任务树收尾**。项目管理者于 2026-09-06 确认“16，17，18都是已完成的状态，已验收，继续收尾”；服务端核对人工验收检查点已解除，`authorization_epoch=2`。
- 根任务 `#15` 与 Development `#16`、Review `#17`、Test `#18` 均为 `succeeded/completed`；Review=`approved`、Test=`passed`，最新冻结集仍为 `[16]`。
- 当前 Codex Desktop 会话通过 SDK/API 重新领取根任务、提交最终汇总消息 `#2480`，并依据项目管理者本次验收及收尾授权，以原请求者身份完成根结果收取。
- 本轮仅处理验收收尾与文档同步，未新增开发任务、未增加开发额度、未进入 TH-7。收尾基线为已推送的 `dd1f682`（记录 Kimi 三 Agent 真实验收结果）。
- GitHub 已推送：项目管理者明确回复“推送吧”后，验收收尾提交 `272b50b` 已推送到公开仓库 `bobo506/TALK` 的 `codex/task-hall` 分支；`git ls-remote` 核对远端与该提交一致。本次公开推送授权已满足，未修改 GitHub 权限或 Codex 自动审批策略。

## Current Snapshot

- 本地 dogfood 固定拓扑：`agent:codex`（Lead / decision）、`agent:deepseek`（DeepSeek Harness / Dev / execution）、`agent:kimi`（官方 Kimi Code CLI / Reviewer / execution）。旧 `agent:pi` / `agent:pi-kimi` 仅保留兼容入口和历史。
- 根任务 `#15`：`TH-6d 三 Agent 验收 V2（Kimi Code）`；项目 `prj_e8fe7066bbec`；Task Hall 为 `group:task-2d0cf86216b742f3adc157a3695ebeef`。最终结果 `#2480`，验收前汇总 `#2479`。
- 子任务结果：Development `#16` → `#2476`；Review `#17` → `#2477`；Test `#18` → `#2478`。Review/Test 都绑定冻结的 `#16`，门禁仍有效。
- 根树运行中 / 非终态后代均为 `0`，剩余开发切片额度为 `0`。根任务已完成；`control_status=active` 是验收释放检查点后的控制字段，不表示仍有任务运行。
- `.tmp/th6d-native-kimi-acceptance-v2.txt`：65 bytes、UTF-8 无 BOM、LF，SHA-256 为 `602FBC88D523943F2798942F0F898B354834372C1BC53AEECBF3233FAC2743DF`。V1/V2 两个验收文件保持 untracked，不进入提交。
- 本轮恢复时 `8000` 端口未运行；项目管理者启动后，`GET /healthz` 返回 `status/db/storage=ok`。收尾没有启动 DeepSeek / Kimi / 嵌套 Codex bridge；既有结果可直接验收。`codex-desktop-th6d-v2` 在根任务完成后回到 `idle`。

## Current Boundaries

- Kimi `review` 档开放 `Read / Grep / Glob / Bash`，没有 `Edit / Write`；工具白名单不是操作系统级只读沙箱。
- Kimi Code CLI `0.38.0` prompt mode 参数冲突已在 `921fbb1` 修复；官方会话可能保留，不自动删除或续接。
- Kimi 已完成自动化、文件和 API 检查；完整浏览器 Tester 能力与操作系统级硬隔离仍未完成。本次浏览器人工验收由项目管理者完成。
- 普通 Codex Desktop 自动注册 TALK MCP、附件正文注入、跨实例消息级原子去重、项目级 Members / Activity 独立页面仍未完成。
- 旧任务 `#10/#11/#12/#13/#14` 保留历史，不复用；旧 `#12` 的嵌套 Codex CLI 额度失败是 2026-08-27 的运行事实，不代表本日额度状态。

## Next Slice

1. 先评审面向普通使用者的“任务总览—任务详情—新建任务”简化方案。建议制作三屏可点击原型，再按单个前端交互切片开发；不能把审计建议当作具体布局已批准。
2. 优先修复任务切换后旧任务树残留、操作目标错配，以及完成态/访问权限提示不一致。详情先回答成果、当前阶段、是否需要人操作；技术信息按需展开。
3. TH-6d 已验收并推送，补充推送记录 b15be87 也已到远端。本次查询 codex/task-hall 无 PR、尚未合并 main；功能里程碑完成不等于分支已合并结束。TH-7 暂不开始，后续开发再按需启动 bridge。
4. 完整本地审计含 5 步截图与建议：`.tmp/ui-audit-20260906/report.md`（本机未跟踪产物）；关键结论已写入本快照与历史。下次输入 `继续项目` 从界面简化恢复。

## Verification

- 2026-09-06 界面审计：Codex 内置浏览器 769px/1280px 截图已保存并逐张核对；检查创建弹窗、Escape 退出、成果入口、跨 Hall 切换，并只读核对 web/app.js。窗口尺寸已恢复。未创建任务、发送消息或执行树控制；未做完整无障碍/端到端回归，未进入当前账号无权限的 #15 消息记录。以下为此前验收收尾的验证记录。

- 项目管理者已完成页面人工验收；本轮 SDK/API 核对验收后 `active`、`checkpoint_reason=null`、`authorization_epoch=2`，没有代替用户调用验收接口。
- 真实根任务完成与收取：`#15` 重新领取（attempt=`2`）→ 最终消息 `#2480` → `succeeded/submitted` → 原请求者收取后 `succeeded/completed`。整树 `#15/#16/#17/#18` 均完成，Test 门禁 `satisfied=true`，无非终态后代，剩余额度为 `0`。
- 本轮定向回归：`.venv\Scripts\python.exe -m unittest tests.test_tasks.AgentTaskTests.test_passed_milestone_test_pauses_for_human_acceptance_before_root_completion tests.test_tasks.AgentTaskTests.test_task_workflow_clarification_accept_submit_and_collect -q` → `Ran 2 tests in 1.219s`，`OK`。
- 受控 V2 产物重新核对字节数、UTF-8、无 BOM、LF 与 SHA-256，全部通过。
- 文档检查：5 份变更文件的 UTF-8 解码、16 个本地 Markdown 链接、进度快照长度与变更范围检查通过；`git diff --check` 通过。
- 2026-08-27 的既有全量回归 `389 tests / OK` 与 Kimi 独立定向回归 `119 tests / OK` 继续保留为历史证据，本轮未重跑全量回归。
- 本轮无代码或前端交互改动；用户手册补充“人工验收后由根负责人提交，再由请求者收取”的既有步骤。

## Known Debt

- 双通道 visible reply 质量、pi 兼容入口的 `--no-extensions` 临时规避仍需后续处理。
- Tester 硬隔离、Kimi 会话保留策略、附件正文注入和跨实例消息级去重仍需后续加强。

## References

- 当前任务合同：`docs/spec/MODULE_tasks.md`
- 当前 bridge 合同：`docs/spec/MODULE_bridges.md`
- 用户操作手册：`docs/guides/USER_MANUAL.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
