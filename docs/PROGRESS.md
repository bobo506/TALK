# Project Progress

## Latest

Updated: 2026-07-26 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- 项目管理者已确认当前 Codex 为决策 Agent；`AGENTS.md` 现明确本项目普通 Codex 会话按决策 Agent 工作，bridge 内成员仍以启动时注入的 `decision_tier` 为准。
- `.talk/groups.yaml` 已配置 `agent:codex = lead + decision`；通用 CLI bridge 在提供 `--project` 且未显式传 `--decision-tier` 时会从该文件解析分级，命令行显式值继续优先。
- TH-5 Project Blackboard + Task Hall 基础可视化链路已人工验收。
- TH-6a1 任务树与硬预算、TH-6a2 根控制 / 有限授权 / runner 协作中断、TH-6a3 有界澄清轮次均已完成。
- TH-6b 已完成：bundled runner 在领取 Task Hall 任务前先以独立只读 / 无工具命令预检，分页读取并按时间顺序重放完整 Hall；信息充分才 `accept -> claim`，信息不足则在同 Hall 集中提问并登记澄清。
- 澄清等待中的任务不会重复唤醒；自动问题带稳定任务 / 轮次标记，可恢复“消息已发送但动作未登记”的中断窗口。答复显式提交后，runner 会带完整 Hall 重新预检。
- 正式执行 prompt 与预检复用同一份完整 Hall 上下文。附件消息目前只注入可见元数据，不自动下载正文。
- 预检只接受显式结构化结论；兼容单行、显式标记后的多行 JSON 及已观察到的嵌套 `ready` 变体。成功命令若首次格式无效，会以同一只读命令纠正一次；自然语言不会被猜测为接受。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务，并可进入对应 Task Hall。
- Human 可从页面委派任务、查看 Hall、收取结果和取消未领取任务；服务端 / SDK 已支持显式澄清答复、人工释放、根暂停 / 恢复 / 终止，但 Web 尚未覆盖这些新入口。
- Task Hall 原始任务、问题、答复和结果持久化在同一 Hall；bundled runner 现在会完整分页读取，不再只把标题 / 正文交给模型。
- `clarification_requested / needs_decision` 会保持等待；`clarification_answered` 会触发重新预检；`accepted` 可在 runner 重启后直接 claim。
- bundled runner 执行中的 claim 心跳同时是最长 5 秒控制探针；服务端撤销 claim 后，本地命令被取消且不会写回陈旧结果。
- 当前任务树仍只有治理预算和澄清协议，尚无 `task_kind`、任务关系、结构化 Review/Test 结论或质量门禁。

## Current Boundaries

- Web UI 尚无提交澄清答复、轮次提示、`needs_decision` 处理、根控制或人工验收门禁入口。
- 附件只重放文件元数据，执行前自动下载与正文注入尚未定义。
- 预检失败后的跨轮询重试没有独立上限与退避；多个 bridge 实例在极窄并发窗口内仍可能都先发出问题，服务端动作会阻止重复状态推进，但消息级跨实例原子去重尚未实现。
- 真实 Pi 冒烟能安全返回“信息不足”并阻止 claim，但曾忽略已给出的任务正文、要求请求者重复内容；这是模型理解质量残余，结构化解析层不会把它误判为接受。
- 单任务运行中取消尚未开放；整树终止通过服务端撤权和 runner 控制探针生效，第三方 runner 需自行实现相同协议。
- 根任务当前可以在后代未结束时自行完成；整树汇总、Review/Test 门禁和里程碑人工验收留待后续切片。
- 普通 Codex Desktop 会话尚未自动注册 TALK MCP；TH-7 再补通用终端接入包装。

## Next Slice

1. TH-6c：实现任务类型、任务关系、结构化 Review / 返工门禁与业务角色发现。
2. TH-6d：实现里程碑黑盒测试、Blackboard 控制、批次自动检查点与人工验收暂停。
3. TH-7：补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。

## Verification

- Python `py_compile`：`bridges/cli_bridge.py`、`bridges/codex_bridge.py`、`bridges/pi_bridge.py` 及相关测试文件通过。
- TH-6b 定向回归：`Ran 168 tests in 28.697s ... OK`。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q`，`Ran 348 tests in 154.472s ... OK`。
- 活服务 E2E 覆盖 `created -> 自动提问 -> 显式答复 -> 重新预检 -> accept -> claim -> 完成`，并验证正式执行 prompt 能读到答复中的 `8123`。
- 真实 Codex 只读预检返回可解析的结构化结论；真实 Pi 返回显式多行结构化阻塞结论，安全地不领取任务，但提问内容质量存在上述边界。
- 较早的混合定向命令曾命中既有 WebSocket 降级测试的固定 2 秒退出超时；该用例随后连续单跑两次通过，最终全量 348 项也通过。本切片未修改该路径。
- 本切片未修改 Web 代码，按 Browser 验证约定无需执行页面验证。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 预检问题的模型语义质量、附件正文注入和跨实例消息级去重仍需后续加强。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
