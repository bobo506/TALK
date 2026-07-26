# Project Progress

## Latest

Updated: 2026-07-26 (Asia/Shanghai)

- 当前分支：`codex/task-hall`。
- 项目管理者已确认当前 Codex 为决策 Agent；`AGENTS.md` 现明确本项目普通 Codex 会话按决策 Agent 工作，bridge 内成员仍以启动时注入的 `decision_tier` 为准。
- `.talk/groups.yaml` 已配置 `agent:codex = lead + decision`；通用 CLI bridge 在提供 `--project` 且未显式传 `--decision-tier` 时会从该文件解析分级，命令行显式值继续优先。
- TH-5 Project Blackboard + Task Hall 基础可视化链路已人工验收。
- TH-6a1 任务树与硬预算、TH-6a2 根控制 / 有限授权 / runner 协作中断、TH-6a3 有界澄清轮次均已完成。
- TH-6b runner 领取前预检、同 Hall 自动澄清和完整上下文重放已完成。
- TH-6c 已完成：新增 `general / development / review / test / rework`、独立任务关系、`required / batch / exempt` Review 策略、结构化 `gate_verdict`、两轮返工门禁与项目 Agent 角色 / 能力发现。
- Review / Test runner 会读取关系授权的关联 Task Hall 完整上下文，并只接受显式 `TALK_GATE_VERDICT`；首次格式错误会有界纠正一次。
- 同一冻结版本的 Review 使用唯一语义槽：`approved / changes_requested` 禁止原版本重审覆盖，`failed / canceled / blocked` 释放槽位允许重试；并发双 Review 只能有一个创建成功。
- 第二轮返工再次得到 `changes_requested` 时，根任务原子进入 `awaiting_human / review_exhausted` 并撤销其它 claim；类型化任务树缺少必需 Review 时不能完成。
- 项目管理者本轮暂时无暇人工验收。TH-6c 没有 Web 改动，已完成自动化与独立代码审查；按高风险单切片刹车暂停，不直接进入 TH-6d。

## Current Snapshot

- Web UI 登录后默认进入项目黑板，以“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务，并可进入对应 Task Hall。
- Human 可从页面委派普通任务、查看 Hall、收取结果和取消未领取任务；根控制、澄清提交与质量任务尚无完整 Web 入口。
- 类型化任务仅作为子任务创建；`development / general` 消耗开发切片，`review / test / rework` 不额外消耗切片，但仍受同根、同项目、授权 epoch、有效期和非终态上限约束。
- `GET /api/tasks/{id}/relations` 返回显式关系；`quality-context` 向 Review / Test / Rework 的创建者和执行者只读开放关联任务、触发任务及其完整 Hall。
- 开发 / 返工成功必须引用结果消息；Review / Test 成功必须提交匹配类型的结构化结论，负向结论必须带具体发现。
- 类型化任务树完成前会检查非终态后代和每个最新开发 / 返工版本的必需 Review；旧 `general` 任务继续兼容原五态流程。
- async / sync SDK、CLI、Python MCP 与 Pi extension 已同步新字段、关系查询、类型过滤和项目 Agent 富化发现，工具名仍保持原有八个。

## Current Boundaries

- Web UI 尚无提交澄清答复、轮次提示、`needs_decision` 处理、根控制或人工验收门禁入口。
- Web UI 尚无 Review / 返工任务的创建、关系查看、结构化结论或质量检查点入口。
- `test` 类型、关系和结构化结论已经持久化，但根任务 Test 门禁、最新冻结版本失效、Blackboard 控制和通过后自动暂停留待 TH-6d。
- bundled runner 通过 Review prompt 约束“只读审查”，服务端能控制任务和数据写回，但不能替代操作系统对第三方 Reviewer 的文件写权限隔离。
- 附件只重放文件元数据，执行前自动下载与正文注入尚未定义。
- 预检失败后的跨轮询重试没有独立上限与退避；多个 bridge 实例在极窄并发窗口内仍可能都先发出问题，服务端动作会阻止重复状态推进，但消息级跨实例原子去重尚未实现。
- 真实 Pi 冒烟能安全返回“信息不足”并阻止 claim，但曾忽略已给出的任务正文、要求请求者重复内容；这是模型理解质量残余，结构化解析层不会把它误判为接受。
- 单任务运行中取消尚未开放；整树终止通过服务端撤权和 runner 控制探针生效，第三方 runner 需自行实现相同协议。
- 普通 Codex Desktop 会话尚未自动注册 TALK MCP；TH-7 再补通用终端接入包装。

## Next Slice

1. TH-6d：实现里程碑黑盒测试、最新冻结版本 Test 门禁、Blackboard 控制、批次自动检查点与人工验收暂停；这是下一处里程碑门禁。
2. TH-7：补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。
3. 后续再处理附件正文注入、预检退避和跨实例消息级去重。

## Verification

- Python `py_compile` 覆盖服务端模型 / 迁移 / 任务与项目路由、CLI、async / sync SDK、runner 与 Python 工具；Pi TypeScript 通过 Node 语法检查。
- 服务端 + runner 定向回归：`Ran 166 tests in 39.405s ... OK`。
- CLI / SDK / Python MCP / Pi 工具联合回归：`Ran 48 tests ... OK`，并被最终全量回归再次覆盖。
- 最终全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q`，`Ran 366 tests in 147.008s ... OK`。
- 独立集成审查补获并验证两条失败路径：Hall 回写失败不得提交 `failed + gate_verdict`；同冻结版本不得以重复 / 并发 Review 覆盖 `changes_requested`。
- 首次全量命令曾因外部 5 分钟工具时限被终止且没有产出最终结果；提高时限后的完整重跑通过，未把前一次超时记为成功。
- `usage-gate.cmd guard --provider codex --json` 返回 `decision=continue`；精确 session / weekly 百分比为 `null`，未臆测具体用量。本轮仍按数据库 / 协议高风险单切片刹车停止。
- 本切片未修改 Web 代码，按 Browser 验证约定无需执行页面验证。

## Known Debt

- 双通道输出仍可能让 Agent 的 visible reply 退化，结构化输出块方案延后处理。
- pi 的 `--no-extensions` 仍是临时规避，等待 upstream 修复后移除。
- 预检问题的模型语义质量、附件正文注入和跨实例消息级去重仍需后续加强。
- 里程碑 Test 门禁、Blackboard 质量控制、自动人工验收暂停和 Reviewer 文件系统硬只读边界尚未完成。

## References

- 当前模块合同：`docs/spec/MODULE_tasks.md`
- 平台集成设计：`docs/spec/PROJECT_INTEGRATION.md`
- 完整历史：`docs/PROGRESS_HISTORY.md`
