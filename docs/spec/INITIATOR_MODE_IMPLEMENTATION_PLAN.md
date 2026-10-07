# 发起者调度与固定主控退役实施拆分计划（v3，I-1加载/I-2代码通过，本轮页面验收通过）

> 2026-10-06由Codex随[正式合同](CONTROLLER_MODE_DESIGN.md)发布，来源为#170稿并经#171独立定向复核通过。旧partial与原件保留，#166/#168/#170/#171已收取。正文中的“本片/当前HEAD/未收取/正式文档零改动”仅为#170草拟时的历史快照；本次发布尚未改变业务代码、UI、权限、Key或运行服务。
>
> I-1由DeepSeek开发、Kimi独立复核；I-2随后由Kimi开发、DeepSeek复核。按当次项目开发要求重新确认分工；I-1/I-2串行并纳同一人工验收轮。I-0步骤准备和I-3文本起草可单独安排，实际Key切换/真实验收按就绪条件执行。
>
> 2026-10-07现状：I-1 172/173代码与当前Codex MCP加载通过；I-2 174/175代码独立复核通过并收取，用户2026-10-07确认本轮页面验收通过。I-0当前Codex入口被动新任务闭环经178/179独立核验与收取通过；I-3A指南经180/181独立通过已发布并收取，完整I-3/I-4尚未就绪，保存active仍意向。下方保留已审历史正文，末尾当前实施状态替代当时未实施/旧加载门禁；“Codex发布补充”已纳I-1。


> 配套 `.tmp/initiator-mode-design-final-fix/contract_draft.md`（任务 #170，agent:kimi；以 #168 计划为完整底稿，仅闭合 #169 复核残余 R-1–R-6）。本计划给出精确差异、切片、验证矩阵；不修改任何代码/配置/数据。D-1–D-4 已由 Codex 裁决（见合同 §11），本计划按定案编写，不再是开放项。

## 0. 基线与交付差异

- 基线：`codex/terminal-return-codex` @ 当前 HEAD `91b2bf239513a240d3f9c8c7bbe8db16f1a345df`（业务基线 `92720207702db8603f49506a15d25cf194e8b0cb`；`9e3e34d→91b2bf2` 仅 `docs/PROGRESS.md`/`docs/PROGRESS_HISTORY.md`/`docs/spec/DEVELOPMENT_ROADMAP.md` 三份主控记录，业务源码同 9272020）。派发包 `.tmp/initiator-mode-design-final-fix-dispatch/source_manifest.json` 登记的 **26 个对象**（19 + 新增 7）本轮逐一实测，大小与 sha256 全部命中，业务零差异。
- 本片（#170）实际差异：仅新增 `.tmp/initiator-mode-design-final-fix/` 下 `contract_draft.md`、`implementation_plan.md`、`changes.md`、`development.json` 四个文件；业务源码/数据库/配置/正式文档零改动。旧 `.tmp/initiator-mode-design/`、`-review/`、`-fix/`、`-fix-review/` 文件不追改；#166/#168 不收取。

## 1. 精确差异预览（实施片将产生的改动，当前均未做）

### I-1 工具片（`bridges/talk_task_tools.py` + 测试；DeepSeek 开发 / Kimi 复核）

| 位置 | 现状 | 改为 |
|---|---|---|
| `CONTROLLED_WAIT_EXIT_REASONS`（94-99） | 含 `controller_changed` | 移除 `controller_changed`；受控正常退出枚举 = matched/timeout/mode_changed；**api_error 为错误路径，不进枚举** |
| `WAIT_COUNTING_NOTE`（66-72） | “…需由主控在外部实测。”（经 `_wait_payload:1098` 每次等待返回） | “…需由任务发起者（调用方）在外部实测。”；同步改 `tests/test_talk_task_tools.py:1056` 的 `assertIn("主控", result["counting_note"])` 断言为新措辞 |
| `PROJECT_REQUIREMENTS_SNAPSHOT_NOTE`（147-150） | “以下内容由主控在派发时从项目读取并写入任务正文…”（经 `snapshot_task_content:412-429` 在 `delegate_task:619-654` **持久写入每个新任务正文**） | “以下内容由任务发起者在派发时从项目读取并写入任务正文…”；**只对新派发生效，旧存储任务快照/结果/历史原文不追改** |
| `CONTROLLED_WAIT_NOTE`（100-113；R-3 名称修正，实际常量名是 `CONTROLLED_WAIT_NOTE`，非 `CONTROLLER_WAIT_NOTE`）、`wait_tasks` docstring（1631-1656）、`talk_wait_tasks` 工具描述（1784-1848） | 描述 G6=assigned、G7=调用者==指定主控、`controller_changed` 退出 | 重写为新门禁 G1–G8（项目上下文/显式预算/agent 身份/模式字段支持/模式 active 前置/严格非空正整数 task_ids/逐任务 created_by+项目核验整批拒绝）；明示“target/角色/模型名不是协调资格”；退出枚举去掉 `controller_changed`，api_error 单列为错误路径 |
| `CONTROLLER_ASSIGNMENT_NOTE`/`UNSUPPORTED`/`UNKNOWN`（170-198）与 `list_agents` 工具描述（1691-1699） | 指定有效性说明 | 按 D-1 加弃用注记：“该指定为历史兼容字段，已弃用，不再决定任何协调/调度，不产生任何权限”；输出字段与降级行为不变 |
| `talk_list_agents` 工具描述（1682） | “主控派发新任务前应先读取它与角色清单” | “任务发起者派发新任务前应先读取它与角色清单” |
| `CONTROLLER_MODE_NOTE`（153-158）与注释行 86、151-152、168-169、473、610 | 含“主控会话绑定/唤回主控会话”措辞 | “主控会话”→“发起者会话”；纯注释同步；不改字段语义 |
| `_wait_tasks_controlled`（1225-1620） | G5 要求模式+指定字段均存在；G6/G7 校验指定；快照含 assignment 三键；30 秒重读含指定比对；`selected_task_ids = _normalize_task_ids(task_ids)` 在 **1253 行、早于 G3 身份 GET**（宽松归一化） | G5 只要求模式字段；**G6=模式 active（用 G5 同一响应判定，前置，零新增请求）**；**G7=task_ids 严格校验（新助手，见下行），执行位置固定在 G6 之后**——新助手替换现行 1253 行对 true 路径的宽松 `_normalize_task_ids` 调用，不得在 G3 之前做运行层严格校验；**G8=逐任务存在+可见+同项目+created_by==caller，整批拒绝（分类见合同 §4.4）**；快照改为 `{requested_mode, requested_version, caller_member_id, task_ids, verified_task_count}`（其中 `task_ids`=G7 合法后按首次出现顺序稳定去重的调用者 ID 列表，规则见合同 §4.1）；重读只比对模式/版本/字段存在性 |
| 新增严格校验助手（紧邻 `_normalize_task_ids:969-985`） | 无 | 新 `_controlled_task_ids`：受控 true 专用——拒 None/省略、非数组、空数组、bool、float（含 1.0）、字符串、0/负数；先校验全部，非法项整批报错并指明；合法后按首次出现顺序稳定去重。**在 G6 之后调用**（不在 G3 之前执行运行层严格校验）；到达 G7 的非法输入按进入参数错误：http_requests=2（身份+项目）、任务 GET=0、`entry_gate=G7`、`return_reason=null`、恰一条 entry JSONL（计数口径见合同 §4.3 表下注）。`selected_task_ids` 初始为 `None`，仅 G7 全部合法后赋值为去重列表；G3–G6 失败及 G7 非法失败时 entry JSONL `task_ids=null`（不落盘原始非法任意类型、不新增原始输入字段），G8 失败记录完整已合法去重列表（R-6）。**`_normalize_task_ids` 原样保留给 false/省略路径（旧语义逐字节不变）** |
| 结构化状态码出口（`_api_request:226-281`） | 404 与 5xx 同样包成 `TalkToolError("TALK API HTTP <code>: …")`，无结构化状态码 | 新增 `TalkApiHttpError(TalkToolError)` 携带 `.status`（HTTPError 分支抛出，消息文本形态保持兼容）；G8 只按 `.status == 404` 判业务拒绝，不解析整段错误文案；其它 HTTP/网络失败仍 `api_error` |
| `poll_round_tasks`（1394-1424）无 ID 项目级受控分支 | D-3 生效后受控路径不可达的死代码 | **移除该分支**（1410-1424 的 `GET /api/tasks` 项目查询 else 路径）；保留普通 false 项目查询路径（`_wait_tasks_legacy` 不动）。本轮逐行核对：现有 29 项受控测试中**没有任何用例**以 true+省略 task_ids 通过门禁覆盖该分支，故无需删旧用例；新增 true 省略/空数组拒绝用例 |
| `recheck_project`（1454-1471） | 含指定字段/版本/成员/状态比对 → `controller_changed` | 删除指定比对，只保留模式字段存在性/模式值/版本比对 → `mode_changed` |
| 进入期错误消息（1361-1385） | G5/G6/G7 指定主控措辞 | 按新 G5/G6/G7/G8 重写；G8 的 404 措辞仅“不存在或对当前调用者不可见”，只回显调用者提交的 ID |
| `bridges/talk_task_tools.py:2015-2022`（`dispatch_tool` 透传）与 `bridges/talk_send_mcp.py:171-185`（通用分派） | `controlled_wait` 参数已透传；通用分派按 TOOL_SCHEMAS 名称分发 | 预计无需改；复核时确认（**索引校正**：#166 计划把 2015-2022 误标在 talk_send_mcp.py，实际属 talk_task_tools.py） |
| `tests/test_talk_controlled_wait.py`（29 项） | 旧门禁用例：255-360 进入门禁用例（含 G6-not-assigned/G7-not-controller/G7-passive）、362-405 进入快照断言（assignment 三键）、428 `controller_changed` 退出、1230-1330 实服务门禁用例等 | 改造为新门禁矩阵（合同 §4.3 全表逐行）：删/改固定主控用例；新增——模式 passive 在 G6 拒绝且零任务 GET；task_ids 省略/空/非数组/bool/float(1.0)/字符串/0/负数/混合非法整批拒绝；重复 ID 稳定去重且各一次 GET；404→`return_reason=null`；其它 HTTP→`api_error`；中途预算耗尽按进入错误；冒名/target≠creator/跨项目/混合 creator/旧 human 任务；保留 legacy 项目级轮询用例（1209-1227）不变 |
| `tests/test_talk_task_tools.py`（17 项） | 1056 行断言 counting_note 含“主控” | 改为新措辞断言；其余非受控用例不动 |

不变项：九工具数量；普通 wait 路径逐字节；`_api_request` 计数/deadline/clamp 机制；`_normalize_task_ids` 旧语义；服务端零改动；`effective_mode` 恒 null。

### I-2 UI 退役片（`web/` + 测试；Kimi 开发 / DeepSeek 复核）

**完整调用链清单（P1-1 闭合：不把 727-1090 整块删除就算退役；先解除模式面板依赖再删共享助手）**：

| 位置 | 删/改/保留 | 说明 |
|---|---|---|
| `web/index.html:256-275` `#controller-panel` 区块 | 删 | 主控面板整体移除 |
| `web/index.html:120` | 改 | “任务由主控分配；…”→“任务由发起者分配；选中任务后可在详情中创建子任务。” |
| `web/index.html:245` | 改 | “供主控派发任务前读取”→“供任务发起者派发任务前读取” |
| `web/index.html:276-308` 模式面板 | 保留+改文案 | 283 hint 与 299 主动说明改为合同 §7.1 发起者语义；结构/CAS/radio/按钮不动 |
| `web/index.html:9-10,527-528` | 改 | 四处静态资源版本一致递增（新切片标识） |
| `web/app.js:879-882` | 删调用 | `refreshProjectWorkspace` 内 `reloadControllerAssignment()` 调用与注释删除；保留 `reloadControllerMode()` |
| `web/app.js:1054-1062` | 删调用 | `renderTaskDetailsPanel` 内 `renderControllerPanel()` 调用与注释删除；保留 `renderControllerModePanel()`；不改同函数的其它同步点 |
| `web/workspace.js:1129-1150`（`controllerModeControllerState`/`controllerModeUnavailableReason`/`controllerModeAvailabilityNote`） | 删 | 模式面板的主控依赖三函数，随主控概念一并删除 |
| `web/workspace.js:1121` | 改 | `controllerModeUI` 状态键 `controllerId`/`controllerStatus` 删除 |
| `web/workspace.js:1258`、`1277-1278` | 删 | 模式读取/应用中对 controller 两字段的回写删除 |
| `web/workspace.js:1372-1376` | 改 | 保存“主动”提示分支改为固定文案（不再查指定状态）：`已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。` |
| `web/workspace.js:743` `controllerStatusMeta` | 删（**在上列依赖点删除之后**） | 其唯一现存调用 1142 随 1138-1144 删除而消失；随后删函数本体与 `CONTROLLER_STATUSES`（734-741） |
| `web/workspace.js:1529` `module.exports` | 改 | 移除 `controllerStatusMeta` 导出（Node 页面测试同步改造，见测试行） |
| `web/workspace.js:624` | 改 | 副标题去掉 `workspaceControllerSummary()`：`参与协作的助手`（无项目时不再显示“项目主控：无项目”） |
| `web/workspace.js:643` | 改 | “开发要求 · 主控 · 调度模式”→“开发要求 · 调度模式” |
| `web/workspace.js:654`、`699` | 删 | “项目主控”/“项目主控（当前指定）”徽标两行删除 |
| `web/workspace.js:727-1090` 其余主控面板逻辑 | 删 | `controllerUI`（751）、`controllerEl`（752）、`controllerContextValid`（753-755）、`controllerAssignedLabel`（757）、`controllerVersionSafe`（759）、`workspaceControllerBadge`（760-762）、`workspaceControllerSummary`（763-768）、`controllerCandidate`（770-774）、`renderControllerPanel`（779-793）、`syncControllerCandidates`/`syncControllerPanel`（795-870 区间）、`loadControllerAssignment`/`applyControllerRead`（873-911 区间）、焦点记忆与 `controllerFocusable`/`controllerFocusTarget`、`reloadControllerAssignment`（982 起）、`saveControllerAssignment`（989-1075 区间）、`rereadControllerState`（1079-1090 区间）；**精确边界以实施时实读为准，逐个函数删除并核对无残留引用** |
| `web/workspace.js:1497-1509` 事件绑定（R-2 区间修正，原稿 1500-1509 不完整） | 删 | **整段 controller 绑定 1497-1509 删除**：1497-1499 `controller-clear-btn` listener（调用 `saveControllerAssignment(null)`，该函数按计划 989-1075 区间删除，不删此绑定即留悬空引用）、1500 `controller-retry-btn`（同 if 块内）、1502-1509 `controller-assign-btn`（含 `controller-candidate-select` 取值调用 `saveControllerAssignment`）；**1510-1520 调度模式面板事件绑定保持不动** |
| `web/workspace.css` / `web/style.css` | 删（以实际引用核对） | 主控专属选择器（`#controller-panel`、`.controller-heading/.controller-hint/.controller-current/.controller-detail/.controller-assign-row/.controller-toolbar/.controller-status`、`.role-controller-badge` 等）；`.controller-mode-*` 全部保留 |
| 后端字段/端点 | 保留 | D-4：`PATCH controller-assignment` 暂留兼容并标弃用；前端不再调用 |

**I-2 自检（新增硬门禁，R-2 符号集补全）**：全仓 grep `controllerUI|controllerStatusMeta|reloadControllerAssignment|renderControllerPanel|workspaceControllerBadge|workspaceControllerSummary|controllerCandidate|controllerAssignedLabel|saveControllerAssignment|loadControllerAssignment|controllerEl|CONTROLLER_STATUSES|controller-clear-btn|controller-candidate-select` 归零或仅剩弃用注记/历史文档——**限定需要退役的运行时 web 调用/元素/导出**（已删函数引用、已删 DOM id、已删导出），**不全仓删除兼容后端或历史文本**（服务端 `PATCH controller-assignment`、兼容输出与历史记录/旧任务快照保持）；`web/app.js` 无对已删函数的任何引用（防 ReferenceError）；浏览器控制台无未捕获异常（人工验收轮核对）。保留全部 app.js load/render 同步点（`reloadControllerMode()`/`renderControllerModePanel()`）、共享 `controllerStatusMeta` 先解依赖后删、模式保存/离页复位/在途响应等 #164/#165 已闭合项不回退。

**测试去留（P1-1 矩阵）**：

| 测试 | 处置 |
|---|---|
| `tests/workspace_controller_ui.test.cjs`（静态用例定义 **33**；R-1 修正：原稿 35 为裸 `grep 'test('` 假计数，多出的 2 个是 292/528 行 `assert.ok(!/…/.test(...))` 正则方法调用；无循环展开用例） | **删除**（对象为被移除的主控面板；其中 144-151 `controllerStatusMeta` 断言随导出移除失效）。其“页面无主控入口”语义由 `test_controller_web_ui.py` 的否定断言承接。本片未跑测试，静态数量不是通过数 |
| `tests/workspace_controller_mode_ui.test.cjs`（静态用例定义 **30**；R-1 修正：原稿 39 为裸 `grep 'test('` 假计数，多出的 9 个是 133/135/181/202/235/248/318/484/815 行正则 `.test()` 调用；无循环展开用例，`for` 循环均在单个用例内部。历史通过数 **30/30** 为 #164/#165 当时通过证据，单列来源：`.tmp/controller-mode-c2-b-ux/implementation.md:45`、`.tmp/controller-mode-c2-b-ux-review/review.md:125`；本片未跑测试，静态数量不是通过数） | 保留+改造：75 行 `controllerStatusMeta` 引用删除；162-207“主控不可用提示”用例改写为固定文案断言；811-817 隔离纪律（不写 `/controller-assignment`）保留且更简单；**#164/#165 已验收行为用例（离页丢弃未保存选择、返回按 saved、同页重绘保留、在途真实结果、409 GET-only、agent 只读）全部保留不改语义** |
| `tests/test_controller_web_ui.py`（5） | 改造：14-160 主控面板契约改为**不存在断言**（index.html 无 `controller-panel` 区块；workspace.js 无 `/controller-assignment` 写调用）；167-291 模式面板契约更新文案与位置断言（删除 controller-panel 位置先后断言）；静态版本断言换新值 |
| `tests/test_project_controller_assignment.py`（44） | **不动**（服务端 PATCH 端点按 D-4 保留，CAS/权限不变） |
| `tests/test_project_controller_mode.py`（31） | **不动**（模式 CAS/字段不变） |
| #164/#165 行为新核对矩阵 | 离页复位/同页保留/在途真实结果/内部 CAS/409 GET-only/agent 只读/REQ-2 草稿隔离：逐一映射到 workspace_controller_mode_ui.test.cjs 既有保留用例与 test_controller_web_ui.py 契约断言，I-2 交付时逐行确认无回退 |

不变项：模式面板 CAS/离页丢弃/409 恢复/agent 只读（#164/#165 行为不回退）；开发要求编辑区；角色说明编辑区；任务页其它交互；后端 API；数据库。

### I-3 提示词/指南片（文档；Kimi 起草 / DeepSeek 复核文本；正式文档由 Codex 收尾落盘）

**精确清单（P2-3 闭合；按本轮实读定位；“主控”逐一按语义区分：固定指定→退役/弃用注记；泛指协调方→改为“任务发起者/协调方”；历史实测/验收记录→不改）**：

| 文件：位置 | 本片动作 | 语义类别 |
|---|---|---|
| `AGENTS.md:36`（“主控每次派发前读取当前项目 development_requirements…”） | 改为“任务发起者每次派发前读取…” | 协调称呼；不改决策分级/业务角色/已配置职责/收尾授权 |
| `AGENTS.md:55`（“派发后结束主控等待…持续主控等待”） | 改为“派发后结束发起者等待…持续发起者等待” | 协调称呼 |
| `AGENTS.md:64`（“主控优先执行 `talk_workflow.py summary`…”） | 改为“任务发起者（协调方）优先执行…” | 协调称呼 |
| `docs/guides/TERMINAL_MCP.md:63`（“bridge执行任务的超时与主控等结果的时长”） | “主控”→“发起者” | 预算段措辞 |
| `docs/guides/TERMINAL_MCP.md:74`（主动资格句“核验最新身份/模式/主控指定与剩余总预算”） | 改为“核验最新身份/模式/任务发起者归属与剩余总预算” | 主动资格（核心） |
| `docs/guides/TERMINAL_MCP.md:86-87`（C2-A1 门禁描述“本人为有效指定且模式active”等） | 按新 G1–G8 重写该段能力描述 | 工具合同描述 |
| `docs/guides/TERMINAL_MCP.md:94-95`（加载检查提及 `controller_assignment`、未被指定拒绝） | 加弃用注记（D-1）；门禁拒绝描述按新 G4–G8 更新 | 加载检查指引 |
| `docs/guides/TERMINAL_MCP.md:100、155-156`（Kimi 独立入口“主控入口/主控工具”措辞） | “主控”→“发起者/协调”措辞 | 协调称呼 |
| `docs/guides/TERMINAL_MCP.md:386、390、392-396`（REQ-1/C1a 段“主控工具/主控派发前读取/主控模式只读状态”） | 改为发起者语义；C1a 节标题/措辞同步 | 现行指引 |
| `docs/guides/DSH_DESKTOP_TALK_MCP.md:156、158`（连接提示词“读取…当前主控设置”“本项目当前指定仍为 agent:codex”） | 提示词改写为发起者语义；删除“当前指定”句 | 现行提示词（C2-C 材料） |
| `docs/guides/DSH_DESKTOP_TALK_MCP.md:165-166、170` | “桌面主控/交主控”→“桌面发起者/交协调方”；166 行指定不授权语义保留改为“指定（已弃用）不授予权限” | 协调称呼 |
| `docs/guides/DSH_DESKTOP_TALK_MCP.md:238-242`（50 秒预算与“有效指定 agent 且 active”资格句） | 资格句改为“任务发起者且模式 active”；预算数值不变 | 预算/资格 |
| `docs/spec/MODULE_webui.md:247-261`（C1b-S2 段）、`281-284`（空态文案段）、`290-292`（C2-B 段“开发要求、项目主控、调度模式”排列句）、`303-305`（“后续取消固定主控…已登记”句） | 跨模块正式文档：**本片只列定位与后续授权范围**；I-2 上线后由 Codex 收尾改为“主控面板已退役”说明与现行描述 | 模块 spec 现行节 |
| `docs/spec/MODULE_webui.md:274`（ROLE-DESC 节“说明不改变**主控**、business_role、decision_tier或权限”句，R-5 补入） | 随 I-3 待同步：改为“说明不改变**任务发起者归属**、business_role、decision_tier或权限”（主控概念已退役，固定概念改为准确语义）；正式落盘由 Codex 收尾 | 模块 spec 现行边界句（I-3 待同步，补漏） |
| `docs/spec/MODULE_bridges.md:214-220`（C2-A1 受控等待与身份核验节，#156–#159 实现/复核记录；R-5 经 Codex 判断纳入 I-3） | **214-220 现有 C2-A1 记录保存历史已实现/已测事实，不把旧 #156–#159 记录重写成新实现**；I-1 实施后经 Codex 收尾在该节新增当前发起者受控等待合同说明（或明确替代注记）：写新 G1–G8 门禁、运行期只重读模式、协调资格=任务发起者归属（created_by） | 模块 spec 现行节（历史保留 + 实施后新说明） |
| `docs/spec/MODULE_bridges.md:204、210`（2026-09-12 旧等待记载：“TALK主控等待目标600秒”“日常主控应显式传当前 task_ids”） | **保留日期与旧 600/660 事实**（212 行已有 2026-10-06 预算覆盖注记）；新说明明确按各终端实 T/W 执行；“日常主控”作为协调会话普通称谓**无需机械全删**，但不得继续作为固定指定资格依据 | 历史记录保留（预算/等待语境） |
| `docs/spec/PROJECT_INTEGRATION.md:763`（“主控派发前读取”）、`768-776`（C1a 节标题/措辞）、`781-806`（C1b-S 节） | 763/768-776 改发起者语义；781-806 节首加弃用注记（D-4：端点暂留兼容、不再被调度读取），正文历史实现描述不逐句改写 | 模块 spec 现行节 |
| `docs/guides/USER_MANUAL.md:32-44`（项目设置段：34 行主控段删除、40-44 调度模式段去掉“尚未指定主控或主控不可用…”句）、`66-70`（“根任务由项目主控统一分配/任务由主控分配/主控先指定根任务负责人”→发起者）、`162` | 随 I-2 同一验收轮由 Codex 收尾更新 | 最终用户手册现行指引 |
| `docs/PROJECT_BRIEF.md:7、9、17、19` | 当前简报同步（Codex 收尾） | 简报 |
| 工具模板/提示词 | 现行 `CONTROLLER_MODE_DESIGN.md` §8 桌面连接提示词由本合同 §7.3 取代（正式替换由 Codex 发布） | 提示词模板 |

**明确排除（不改）**：`docs/PROGRESS_HISTORY.md`、`docs/spec/C1B_CONTROLLER_CONTRACT_REVIEWED.md`、`docs/spec/BRAINSTORM_NEXT.md`、`docs/spec/TERMINAL_RETURN_DRAFT.md`、`docs/guides/CONTROLLER_ASSIGNMENT_ACCEPTANCE.md`（历史验收指南）、`TERMINAL_MCP.md`/`DSH_DESKTOP_TALK_MCP.md` 中的历史实测/验收记录段（如 TERMINAL_MCP 162-213、DSH 176/213-231/274）、`MODULE_bridges.md` 除上表 204/210/214-220 所列处理方式以外的全部段落（不扩写全模块）、`.tmp/` 全部原稿与复核报告、历史任务快照/结果正文。**本片不修改任何正式文档**，正式落盘由 Codex 在对应实施片收尾执行。**禁止“全仓无差别替换主控”**；不把每个“主控”都等同固定指定（如“主 Agent”“主控等待目标 600 秒”等历史/预算语境按上表类别处理）。

### I-0 身份接入准备（不执行切换）

- 产出切换/回退/核验步骤清单（合同 §5.3）：备份→换 Key→重连→`caller_identity` 实测→试派任务核对 `created_by`→失败回退；历史 human:bobo 任务收尾盘点表。
- 本片只交付步骤；执行需用户确认，且绝不读取/输出/写入密钥。

### I-4 真实消费者验收（人工门禁）

- 前提（P2-4 同步）：**I-0 Key 切换核验完成 + I-1 已重连加载 + I-2 页面验收 + I-3 指南就绪**；过渡阶段不进行或宣称真实主动消费者验收。
- 场景 1：Codex 自身 Key（切换核验后）创建任务 → 项目模式 active 时对该任务受控等待/读交付/派复核/收取；Kimi 作为执行者只完成交付、不读模式。
- 场景 2：DeepSeek 自身 Key 发起另一任务，同理走完。
- 记录：各工具调用、return_reason、controlled_rechecks、caller_identity 实测、created_by 实测、退出/收尾文案。
- 通过前 `effective_mode` 保持 null/not_bound，UI “实际执行”行不变。

## 2. 切片依赖与顺序（含共同人工验收轮，P2-4 定案）

```
I-0（步骤文档，不执行） ─┐
                        ├─→ I-4（真实验收，需 I-0 核验 + I-1 加载 + I-2 验收 + I-3 就绪）
I-1（工具+测试） ──→ I-2（UI 退役，必须晚于 I-1 加载，合同 §6 分步加载）
                         └─ I-1/I-2 串行开发、独立复核、可分别提交回退，
                            但纳入同一人工验收轮；窗口期限制见合同 §6 过渡窗口行
I-3（提示词/指南）可与 I-1/I-2 并行起草，发布不早于 I-1
```

每片独立可审查、可回退（I-1 回退=还原 talk_task_tools 与测试；I-2 回退=还原 web 与版本号；无数据库/API 破坏性变化）。不并行改码（开发与复核期间禁止并行改码的仓库纪律不变）。

## 3. 验证矩阵（场景 × 手段 × 级别）

| 场景（合同 §4.3/§4.4/§5/§6） | 验证手段 | 级别 | 本片状态 |
|---|---|---|---|
| 普通 wait 省略/false 逐字节兼容（含 legacy 项目级轮询 1209-1227） | 模拟时钟单测 + 零新增 HTTP 断言 | 代码级 | 后续片执行，本片 not_run |
| G7 输入矩阵（省略/空/非数组/bool/float 1.0/字符串/0/负数/混合非法/重复去重计数；R-4：到达 G7 的非法输入断言 http_requests=2、任务 GET=0、entry_gate=G7、return_reason=null、恰一条 entry JSONL 且 task_ids=null；更早门禁按相应计数，外层 schema 拒绝不归 G7） | 假 HTTP 单测 | 代码级 | not_run |
| G8 分类矩阵（0/N/部分 GET 失败：404→return_reason=null；其它→api_error；中途预算耗尽→进入错误；HTTP 计数=2+k 族；R-6：G8 失败 entry 记录 task_ids=完整已合法去重列表，ID 来自调用者而非任务响应） | 假 HTTP + 模拟时钟单测，断言 JSONL entry 记录与 http_requests | 代码级 | not_run |
| G6 前置（passive/旧字段项目零任务 GET） | 单测断言请求序列 | 代码级 | not_run |
| matched/timeout/mode_changed/预算耗尽边界；controller_changed 不再出现 | 模拟时钟单测 | 代码级 | not_run |
| query_stats 计数（身份+项目+唯一任务+重读 GET 含失败） | 单测断言 | 代码级 | not_run |
| 服务端权限不变（collect 仅 created_by 等） | 现有 tests/test_tasks.py 回归 | 代码级 | not_run |
| UI 主控面板移除、app.js 调用点无残留、模式面板新文案与主控依赖解除、#164/#165 行为保持 | Node 页面契约 + Python web 测试 + grep 自检 | 代码级 | not_run |
| bridge 文案（SNAPSHOT_NOTE/WAIT_COUNTING_NOTE/list_agents 描述）改写且旧任务快照不追改 | 单测断言新措辞 + 旧数据不变 | 代码级 | not_run |
| Key 切换后 caller_identity/created_by 实测 | 真实 MCP 重连只读检查 | 人工/实测 | not_run（本片不操作） |
| Codex/DeepSeek 各自发起链路（核心例子） | 真实链路人工验收（I-1/I-2 同一验收轮之后） | 人工门禁 | not_run |
| 主动推进纪律（每动作前重读资格） | 提示词文本评审 + 真实链路观察 | 约定级 | not_run |

## 4. 裁决记录（已定案，见合同 §11）

- D-1：`controller_assignment` 只读输出暂留至少一个兼容版本 + 弃用注记，不新增权限。
- D-2：human 受控主动本期继续拒绝，不新增权限提案。
- D-3：受控 true 强制显式非空严格正整数 task_ids（先校验全部再稳定去重，逐唯一 ID 各一次 GET，非法整批拒绝）；false/省略旧语义不变。
- D-4：human `PATCH controller-assignment` 暂留兼容并标弃用，CAS/权限保持，不删库/数据/端点。

## 5. 本片未做事项（如实）

- 未改任何业务文件；未跑任何测试（文档片，验证仅限基线/manifest 核对、源码索引核对与交付包格式校验）。
- 未执行 Key 切换、未创建真实任务、未启动服务/终端、未读取/输出/写入任何凭据。
- 行号沿用 #168@603538b / #169@9e3e34d 实读（`9e3e34d→91b2bf2` 仅三份主控记录，业务源码与 9272020 基线及当前 HEAD `91b2bf2` 逐字节一致）；后续代码变化后需复核者重新确认。


## Codex发布补充（2026-10-06，纳入I-1）

- 同步更新tests/test_talk_controlled_wait.py:1043/1046/1075的三条同源断言：工具描述G1–G8、controller_changed退役、WAIT_COUNTING_NOTE采用任务发起者（调用方）措辞；原计划仅列另一文件1056，实施时两处一并核对。
- talk_list_agents工具描述退役清单补bridges/talk_task_tools.py:1684-1690的controller_mode段，按同一规则将固定“主控会话”说明改为“发起者会话”，字段形状及effective null/not_bound语义不变。
- 本补充来自#171独立复核建议，不改变权限、运行机制或已确定设计选项。未来实现测试和终端实测均待执行。


## I-1收尾与历史加载门禁（2026-10-06，已由后节替代）

- I-1开发172/独立复核173通过并收取；实际四文件，六模块162及七独立探针通过。terminal_mcp --check门禁清单G1–G8最小配套同步已纳本片范围。源码通过与实际MCP加载分开。
- 当前工具目录/运行时注记仍旧版，I-1加载未通过；按原依赖图，I-2须晚于I-1加载。先重连当前TALK MCP，按TERMINAL_MCP的I-1加载验收核验，再派页面退役。I-1/I-2仍纳同一人工验收轮。
- 173原消息格式导致MCP unknown、本地有效complete及实际独立证据并存，原消息/报告不追改；O1/O2非阻塞文字建议纳I-3。I-0身份切换与I-4真实链路未开展，effective null/not_bound保持。

## 当前实施状态与下一门禁（2026-10-07）

| 切片 | 当前结论 | 下一步/边界 |
|---|---|---|
| I-1 工具 | 172/173代码通过并收取，功能1fbdf78；当前Codex目录/运行时及短只读路径加载通过 | 不外推其它终端、真实Agent G8/主动消费者或长等待/取消排队 |
| I-2 页面 | 174/175独立实际代码复核通过并收取，14业务/测试文件、资源20261007-initiator-mode-ui | 与I-1同轮用户页面验收已于2026-10-07通过；后续先I-0步骤准备，再按依赖推进 |
| I-0 | 176/177准备通过已收取；配置/API/独立启动、当前caller及178/179被动新任务闭环独立通过，两项已由Codex收取 | 当前Codex入口验收通过；旧human归属保持，I-3/I-4与其它终端自身身份另片 |
| I-3 消费者/文案 | I-3A已发布收取；I-3B经182开发/183断言补正/184独立复核通过，四文件最小差异及USER_MANUAL/MODULE_webui已发布，三项已收取 | 角色hint待用户简验；MODULE_bridges/PROJECT_INTEGRATION剩余同步、175-O1维护另片，新MCP说明重载未核；尚不释放I-4 |
| I-4 真实链路 | not_run | 依身份/消费者及终端实际预算就绪后独立人工验收；effective仍null/not_bound |

- 175独立Node149/149（--test-isolation=none）、四页面Python12/12及符号/导航探针通过；默认隔离宿主spawn EPERM为not_run。后端75仅核开发日志/保护哈希，未重复运行。全43来源对象与tracked差异哈希一致，主控不重复全审/全测或操作浏览器。
- 固定主控页面调用链已退役，模式意向human写/agent读、CAS/409、164/165离页与在途行为保留；兼容assignment服务端不删，Key/权限/数据不改。用户本轮页面验收通过；未逐项声明的键盘、窄屏、HTTP并发等边界仍不外推覆盖，复测步骤见 [发起者模式页面验收](../guides/INITIATOR_MODE_UI_ACCEPTANCE.md)。

## I-0准备收尾（2026-10-07，实际切换未执行）

- 176 Kimi起草/177 DeepSeek独立复核通过并收取，26来源及实际稿SHA一致、约40处出处独立实读；无返工缺口。Codex已发布[身份切换与回退清单](../guides/CODEX_TALK_IDENTITY_SWITCH.md)，纳177-N1–N4文字澄清，N5只记录本次派包预先明示的进度管理边界，不修改AGENTS或扩并行审改。
- 源码/测试/Key/配置/模式零改动；caller仍human:bobo、passive/version6、effective null/not_bound。准备通过不等于身份切换、真实G8或消费者通过，配置/Key安全到位/宿主重载/真实预算仍待实施前核验；实际执行继续遵守本计划I-0“本片只交付步骤；执行需用户确认”门禁。

## I-0实际配置实施（2026-10-07配置实施快照；重连结果见下节）

- 用户2026-10-07明确授权“切换到codex吧”；现已备份用户配置并只替换TALK MCP的`env.TALK_API_KEY`为既有`agent:codex`凭据。服务端`/api/members/me`核`agent:codex / agent`、未禁用且在册；新凭据独立`--check`通过。当前聊天实际MCP仍返回`human:bobo / human`，宿主重连待用户操作，未创建新任务；不宣称当前会话切换成功。
- 切换前本项目human可见返回177项/human创建164项、在途0，176/177已收取；7项旧failed（122/35/31/24/21/14/12）保持。只读核旧human凭据仍可读177，历史created_by不迁移。项目响应整体不变：passive/version6、兼容assignment agent:codex/version13；当前MCP仍effective null/not_bound。配置`tool_timeout_sec=660`已读实值，未进行长等待/取消/排队测试，不当作客户端实际预算或主动适配通过。
- 在客户端设置的MCP服务器列表重启`talk`入口；若无法单独重连则完全退出并重开Codex。返回本会话后先`talk_list_agents`确认真实caller为agent:codex且kind=agent，再按最新开发要求派一项无破坏性身份任务、独立复核并收取，核新created_by；不再请求Key切换授权，不重复176/177。
- 上节零Key/配置改动和第116行只准备约束是176/177阶段记录；本次实际执行已取得另行明确授权，不需再次确认。备份与无密钥证据索引见PROGRESS。

## I-0入口与178任务归属（2026-10-07收取前快照；验收结果见下节）

重开恢复时当前聊天talk_list_agents实测agent:codex/kind=agent/note=null；读取最新开发要求后派178给DeepSeek，当前聊天get_task核created_by=agent:codex、project_id=prj_e8fe7066bbec及独立Hall，读取时running/in_progress。身份与创建归属已核，真实任务号交付、Kimi独立复核与收取仍待完成；默认派发后结束用户通知取件。本轮无功能/配置/Key/模式写入，无wait/取消/排队/主动消费者实测；证据.tmp/initiator-mode-identity-verify/。I-3/I-4前置不据此提前宣称满足。

## I-0 Codex被动身份闭环验收通过（2026-10-07）

当前聊天实际caller为agent:codex/kind=agent；178 DeepSeek只读核验经179 Kimi独立A-H复核通过，两个新任务created_by=agent:codex、项目正确且独立Hall。Codex于2026-10-07T09:50:04.854837收取179、09:50:07.538516收取178，均succeeded/completed，原msg2681/2680保持。原partial的下游复核/收取已完成；179结果混排导致MCP默认unknown，本地合法179报告与完整消息JSON一致，按实际独立证据验收，原报告不追改。回执.tmp/initiator-mode-identity-receipt/acceptance.json。

通过范围仅Codex当前入口及被动派发/读取/交付/独立复核/收取；项目passive/version6、effective null/not_bound保持，660仅前次配置实读。真实G8/主动消费者/长等待/正常到期/取消/同连接排队/其它终端身份未验收。里程碑收尾后暂停，I-3消费者/现行指南/旧主控文案及I-4真实链路另片；历史human归属和权限保持。

## I-3A消费者指南发布（2026-10-07）

Kimi180起草经DeepSeek181独立A–F全文/实际源码依据复核通过、无阻塞，已正式发布[发起者消费者指南](../guides/INITIATOR_MODE_CONSUMER.md)及AGENTS/TERMINAL_MCP/DSH_DESKTOP现行三文本补丁（23进23删），原历史/报告保留。指南明确约定级资格与有限预算、每动作前重核、正常return_reason与API错误/客户端取消/总预算耗尽的区别；9链接/锚点验证通过。181/180均已由agent:codex收取为succeeded/completed，回执.tmp/initiator-mode-consumer-receipt/acceptance.json。

当前只I-3A指南范围通过；S-1/S-2工具计数/schema、175-O2角色hint/workspace注释及USER_MANUAL:162关联文字仍需下一片实际实施并复核，MODULE_webui/MODULE_bridges/PROJECT_INTEGRATION剩余同步未完成、175-O1测试维护另片。181建议S-1既有子串断言无需镜像同步改测试，关联文案同批完成。项目passive/version6、effective null/not_bound；未运行主动消费者/G8/长等待/取消/排队/其它终端身份验收，完整I-3与I-4门禁未释放。

## I-3B活跃文案与关联文档发布（2026-10-07，页面待简验）

Kimi #182完成S-1/G8计数注记、S-2/受控timeout既有clamp描述、175-O2角色hint及workspace两注释；原任务未授权测试改动，页面契约旧断言1项失败如实报partial。#183仅同步既有assertIn子串与对应注释，#184 DeepSeek独立A–F实际代码/文档复核通过、0阻塞/0返工，独立页面2+5及等待合同定向4项通过。四tracked文件10进8删；AST8302节点除两个描述字符串等价，JS注释外、HTML hint外不变，G1-G8/权限/计数/clamp/模式交互保持。开发54/65不重复声明为独立通过，浏览器/真实链路未运行。

Codex已发布USER_MANUAL与MODULE_webui，并追加I-2旧human身份快照和当前agent:codex、I-0/I-3A已完成的区别；按184→183→182收取，三项succeeded/completed、原msg2686/2685/2684与182 partial/失败保持。183自报25项数目不准，184实际核13来源中12保持+15冻结保持=27未变对象、0实际缺口；原报告不改。回执.tmp/initiator-mode-live-copy-receipt/acceptance.json，已审原稿/补正/复核证据保留。

页面简验：使用既有TALK服务和人类登录密钥，Ctrl+F5刷新后进入“角色”→任一具体角色→“角色说明”，确认提示写“不改变任务发起者归属、职责分级（business_role / decision_tier）或任务权限”。保持被动即可，无需服务重启。当前未宣称用户已验收本片；I-3还需MODULE_bridges/PROJECT_INTEGRATION同步，175-O1测试维护另片。既有JSON Schema maximum=600与运行clamp关系列后续独立评估，本片只描述同步、不改关键字。当前MCP进程新说明重载未核；项目passive/version6、effective null/not_bound，I-4真实G8/主动消费者/长等待/取消/排队未运行，门禁未释放。
