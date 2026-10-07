# 按任务发起者调度与固定主控退役实施合同（v3，I-1加载与I-2代码通过；页面验收通过；真实链路待后续）

> 2026-10-06 Codex发布：#166原设计经#167独立复核、#168修订、#169独立复核、#170六项修订与#171定向复核后，合看确认合同设计通过。#171逐R-1..R-6独立回源码，10完成/0未完成/0阻塞，原#167/#169的partial记录保持；#166/#168/#170/#171已收取。
>
> **2026-10-07当前I-1源码/当前Codex MCP加载已通过；I-2页面退役经174/175独立代码复核通过并收取，用户2026-10-07确认I-1/I-2本轮页面验收通过。** 入口Key切换、消费者/文案与真实主动链路尚待后续。下方草拟正文及2026-10-06加载门禁按当时快照理解，现状以文末2026-10-07实施状态与PROGRESS为准。effective_mode仍null/not_bound，保存active仍是意向。
>
> 配套[实施拆分计划](INITIATOR_MODE_IMPLEMENTATION_PLAN.md)；[旧固定主控合同归档](CONTROLLER_MODE_DESIGN_FIXED_CONTROLLER_ARCHIVE.md)。两条非阻塞清单建议纳入实施计划“Codex发布补充”，不重开已通过的设计。
>
> 下方为#170已审正文。其“本片/当前HEAD/现行正式合同/正式文档diff为空”等开工快照均指#170草拟时（91b2bf2、业务9272020），不是发布后的状态；原稿提及“#166/#168不收取”为当时约束，本次已收取。旧合同已归档，后续新实施以本正式合同为准。源码行号以实施时实读为准，静态数量不代表测试通过。


> 本文档是“按任务发起者调度、取消固定主控”的**实施合同修订草稿**，用于在通过 DeepSeek 定向复核与 Codex 裁决后整体替换 `docs/spec/CONTROLLER_MODE_DESIGN.md` 的现行内容。撰写：agent:kimi（任务 #170，在 #168 稿基础上做六项残余定向修订）。
>
> 本稿以 #168 修订稿（`.tmp/initiator-mode-design-fix/contract_draft.md`，sha256 `c41cf55b…667b`）为完整底稿，仅闭合 #169 独立复核（结论 partial，11 完成/6 未完成/0 阻塞）的六项残余 R-1–R-6；#168 已闭合的 #167 复核 2 项 P1 + 5 项 P2、6 条直接措辞问题与 Codex 已裁决设计选项 D-1–D-4（见 §11）**原样保留、不回退**。逐项“原句→新句→位置”对照见同包 `changes.md`。
>
> **状态标记约定**：本节与全文区分两类内容——
> - 【现行事实】：源码/测试行号证据沿用 #168 在 HEAD `603538bbe3f038c933da62c83fc414e5f70fed51`、#169 在 HEAD `9e3e34d` 两轮的实读；`9e3e34d→91b2bf2` 仅三份主控记录（PROGRESS/PROGRESS_HISTORY/DEVELOPMENT_ROADMAP），业务源码与 `9272020` 基线及当前 HEAD `91b2bf239513a240d3f9c8c7bbe8db16f1a345df` 逐字节一致，本片开工已对派发包 26 个对象逐一实测命中（见 §0）；
> - 【新方案·未实施】：本合同定义的目标行为，**当前代码、数据库、运行配置、UI 均未实现**；D-1–D-4 是**已确定的设计选项**，不是已实现的代码，不得以本合同的存在宣称已生效。
>
> 前置确认：用户已确认 #164/#165 两条人工反馈验收通过并通知“167 ok”；DEVELOPMENT_ROADMAP「2026-10-06 新增后续计划」与「发起者合同设计选项裁决（2026-10-06，未实施）」是本合同的需求与裁决来源。模型名称获取/展示与成员命名规则按路线图另拆片，本合同不展开（见 §10）。

## 0. 基线与范围

- 实际基线：分支 `codex/terminal-return-codex`，当前 HEAD `91b2bf239513a240d3f9c8c7bbe8db16f1a345df`（“记录168合同修订交付并派发169定向复核”）；`9e3e34d→91b2bf2` 仅三份主控记录（`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`、`docs/spec/DEVELOPMENT_ROADMAP.md`），业务源码与 `9272020` 基线逐字节一致。本轮对派发包 `.tmp/initiator-mode-design-final-fix-dispatch/source_manifest.json` 登记的 **26 个对象**（#169 复核时 19 个 + 新增 #169 两报告、`MODULE_bridges.md`、`MODULE_webui.md`、两份页面测试、`talk_send_mcp.py`）逐一实测：文件大小与 sha256 **全部命中**，即业务源码、旧稿、复核报告相对 `9272020` 业务基线零差异。#169 报告内“当时 HEAD 9e3e34d”为复核时事实，保留不追改；#168 稿内“当前 HEAD 603538b”为其开工时实读，同样保留为历史记录。
- 快照目录事实（修订 #166 原稿 §0 的过时表述）：`.tmp/initiator-mode-design-dispatch/` **当前实际存在**，含 `task.md`、`source_manifest.json`、`baseline/CONTROLLER_MODE_DESIGN.md`（与现行正式合同逐字节相同）。#166 原稿“快照目录不存在”是该稿撰写时的当时观察，保留为历史索引、不追改原稿；本稿按当前实际存在目录与当前源码核对。
- 本片只做方案修订：新增 `.tmp/initiator-mode-design-final-fix/` 下四个文件（不入库）；业务源码、数据库、运行配置、凭据、服务、正式文档 diff 均为空；旧 #166/#167/#168/#169 文件一律不追改。
- 修订对象：现行 `docs/spec/CONTROLLER_MODE_DESIGN.md`（固定主控版 C2 合同）。其 §2 项目设置交互 / CAS / 离页丢弃、§5 受控等待的预算/记账/统计机制、#156–#165 已实现的 C2-A1/C2-B 代码与测试，作为**机制资产**保留并改造；其中“调用者等于指定主控”（现行 G6/G7）与 assignment 版本退出依赖被本合同**取消**。

## 1. 实际源码核对证据索引（行号沿用 #168@603538b / #169@9e3e34d 实读；业务内容与 9272020 基线及当前 HEAD 91b2bf2 逐字节一致）

| 能力 | 文件：行 | 【现行事实】 |
|---|---|---|
| 任务创建者写入 | `server/routes/tasks.py:1644-1646`（`create_task` → `_create_task_with_hall`） | `created_by=current.id`，即服务端按 API Key 反查出的调用成员；`AgentTaskCreate`（`server/models.py:906-1014`）**没有** created_by 请求字段 |
| created_by 不可改 | `server/routes/tasks.py` 全文 | 25 条路由中无任何修改已建任务 created_by 的端点；created_by 是创建即固定的事实 |
| 任务输出携带归属字段 | `server/models.py:1150-1173`（`AgentTaskOut`） | 同时暴露 `project_id`（1153）与 `created_by`（1173），新 G8“逐任务读取并整批判定”有真实可实现入口 |
| 任务可读性 | `server/routes/tasks.py:82-85` | `_ensure_task_visible`：human 或 `created_by`/`target_member_id` 之一；其他人 404（“不存在”与“不可见”同形 404，拒绝信息不会泄漏其它任务存在性） |
| 任务列表可见性 | `server/routes/tasks.py:1709-1711` | 非 human 只列 `created_by==self` 或 `target==self` 的任务 |
| 收取资格 | `server/routes/tasks.py:2487-2501` | `collect-result` 仅 `created_by==current.id`（2493-2495 越权 403）；human 对自己创建的任务天然可读可收 |
| 取消（未领取） | `server/routes/tasks.py:2512-2536`、`bridges/talk_task_tools.py:757-765` | 仅 created_by；MCP 侧额外限制仅 queued |
| 领取/心跳/完成 | `server/routes/tasks.py` claim/heartbeat/complete 端点 | `_require_agent` + `target_member_id==current.id`，claim_token/租约/树治理照旧 |
| 顶层治理授权 | `server/routes/tasks.py:367-383` | may_delegate 及六项预算/租约覆盖仅 human 可授 |
| 子任务派发 | `server/routes/tasks.py:386-441` | parent 运行中 + `may_delegate` + epoch + 深度/并发预算门禁；非 human 须为 parent 执行者或根 created_by（398） |
| 模式字段 | `server/models.py:112-116` | `controller_mode` 默认 passive、`controller_mode_version` 默认 0 |
| 主控指定字段 | `server/models.py:117-124`、`server/models.py:292-326` | `controller_member_id`/`controller_assignment_version` 独立版本；`resolve_controller_assignment_status` 实时计算配置有效性 |
| 模式/指定 CAS 写入 | `server/routes/projects.py:507-558`、`561-665` | 两个 PATCH 均仅 human（525、582 `_require_human`）；条件 UPDATE 原子 +1；409/200/404 语义见现行合同 §1 |
| 项目输出 | `server/models.py:1360-1401` | `ProjectOut` 同携模式与指定两组字段，指定状态实时计算 |
| 身份反查 | `server/routes/members.py:102-106` | `GET /api/members/me` 按 API Key 反查返回 id/kind/disabled_at；终端入口忽略继承的 `TALK_MEMBER_ID`（`bridges/talk_task_tools.py:299-320` 的 `_identity_from_api` 不复用环境变量优先的 `_member_id()`） |
| 受控等待现状 | `bridges/talk_task_tools.py:1225-1620` | G1–G7 门禁已实现，其中 **G6=assignment.status==assigned（1365-1371）、G7=调用者==指定主控（1372-1378）且模式 active（1379-1385）**；30 秒重读含指定比对（1454-1471）；`controller_changed` 在退出枚举（94-99）；单次 deadline 全记账；错误归一 api_error |
| 普通等待兼容 | `bridges/talk_task_tools.py:1108-1222` | `controlled_wait` 省略/false 与旧版逐字段一致：默认/最大 600 秒（954-966）、`_normalize_task_ids`（969-985）旧归一化、无身份 GET、无项目重读、返回无新字段 |
| 受控参数严格性 | `bridges/talk_task_tools.py:1016-1047` | `_normalize_controlled_wait` 只接受 true/false；`_controlled_wait_timeout` 拒 bool/非数值/NaN/inf/≤0、clamp 600，可复用于新 G2 |
| 进入期失败记录 | `bridges/talk_task_tools.py:1273-1301` | `record_entry_failure`：纯策略拒绝写 `return_reason=null`，API/网络失败写 `api_error`；保留 `entry_gate`/`entry_error`；G1/G2 在发出任何 HTTP 前直接报错不写记录 |
| HTTP 错误归一 | `bridges/talk_task_tools.py:226-281` | `_api_request` 把 404 与 5xx 同样包成 `TalkToolError("TALK API HTTP <code>: …")`（250-261）；失败尝试在发请求前已计数（243-245）；**当前没有结构化状态码出口**，新 G8 需要新增（见 §4.4） |
| 受控死分支现状 | `bridges/talk_task_tools.py:1394-1424` | `poll_round_tasks` 含“无 `task_ids` 时按项目拉 `GET /api/tasks`”分支（1410-1424）；D-3 生效后受控路径不可达；本轮逐行核对：现有测试集中**没有任何用例**以 controlled_wait=true 且省略 task_ids 通过门禁进入该分支（见 §9 I-1 与 changes.md P2-5） |
| 工具集合 | `bridges/talk_task_tools.py:1673-1969` | TOOL_SCHEMAS 恰 9 个；本方案不新增工具 |
| list_agents 只读输出 | `bridges/talk_task_tools.py:528-616` | 项目路径返回 `caller_identity`（三键）+ `controller_mode` + `controller_assignment`；非项目路径三者均 null；`controller_assignment_summary`（472-525）独立于门禁，缺字段已能 `supported=false` 降级 |
| bridge 固定主控文案残留 | `bridges/talk_task_tools.py:66-72`（`WAIT_COUNTING_NOTE`“需由主控在外部实测”，经 `_wait_payload:1098` 每次等待返回）、`147-150`（`PROJECT_REQUIREMENTS_SNAPSHOT_NOTE`“由主控在派发时…”，经 `snapshot_task_content:412-429` 在 `delegate_task:619-654` **持久写入每个新任务正文**）、`1682`（`talk_list_agents` 工具描述“主控派发新任务前应先读取…”）、`100-113`/`1631-1656`/`1784-1848`（受控门禁与工具描述中的指定主控条件） | 退役片需逐项处理的 bridge 侧提示/输出/快照正文（详见 §6 表）；旧存储任务快照/结果/历史原文不追改 |
| stdio 顺序处理 | `bridges/talk_send_mcp.py:125-191`（通用分派 171-185） | 逐行同步 dispatch；等待阻塞期间同连接其它调用排队；无取消检测源 |
| 工具内部分派 | `bridges/talk_task_tools.py:2015-2022` | `dispatch_tool` 已透传 `controlled_wait` 参数，预计无需改 |
| 单次 HTTP 超时 | `bridges/talk_task_tools.py:226-281` | `_api_request` 默认 10 秒、受控路径按剩余预算 clamp；连接/读取阶段超时归一为 TalkToolError |
| 派发时快照 | `bridges/talk_task_tools.py:619-654` | `delegate_task` 派发前读项目开发要求并拼入存储正文 |
| 前端主控面板 | `web/index.html:256-275`、`web/workspace.js:727-1090` | C1b-S2 指定/解除 UI：CAS + saveToken + 请求序号 + 安全整数检查 + 409/400 只重读不自动重写 |
| 前端模式面板 | `web/index.html:276-308`、`web/workspace.js:1104-1280`（C2-B/#164） | 调度模式面板：离页丢弃未保存选择、返回按已确认 saved、状态行去版本、内部 CAS 保留、409 恢复入口、agent 只读 |
| 模式面板对主控的依赖 | `web/workspace.js:1121`（状态键 controllerId/controllerStatus）、`1129-1150`（`controllerModeControllerState`/`controllerModeUnavailableReason`/`controllerModeAvailabilityNote`）、`1258`、`1277-1278`、`1372-1376`（保存“主动”提示分支，1142 调用 `controllerStatusMeta`） | 模式面板读取指定状态生成“主控不可用”提示；`controllerStatusMeta`（743）落在待删主控区块内但被模式面板调用，并在 `module.exports`（1529）导出给 Node 页面测试 |
| 前端主控面板外部调用点 | `web/app.js:879-882`（`refreshProjectWorkspace` 内 `reloadControllerAssignment()`）、`1054-1062`（`renderTaskDetailsPanel` 内 `renderControllerPanel()`） | 删除 workspace.js 中同名函数而不改 app.js 会导致刷新与每次详情重绘抛 `ReferenceError` |
| 前端主控文案残留点 | `web/index.html:120`（“任务由主控分配”）、`web/index.html:245`（“供主控派发任务前读取”）、`web/workspace.js:624`（副标题 `workspaceControllerSummary`）、`643`（“开发要求 · 主控 · 调度模式”）、`654/699`（“项目主控”徽标） | 退役片需逐一处理的可见文案 |
| 客户端预算事实 | `deploy/dsh/desktop-talk-mcp.patch.template.yml:54`、`deploy/dsh/talk-mcp.patch.template.yml:36` | DeepSeek 桌面/CLI 模板 `toolCallTimeoutMs: 65000`（65 秒，配置事实） |
| Kimi 模板预算 | `deploy/kimi-code/mcp.talk.template.json:16` | `toolTimeoutMs: 660000`（模板事实，非运行中已核验能力） |
| 现有测试规模（R-1 口径修正） | `tests/test_talk_controlled_wait.py`（29）/ `test_talk_task_tools.py`（17，含 1056 行 `assertIn("主控", result["counting_note"])`）/ `test_project_controller_mode.py`（31）/ `test_project_controller_assignment.py`（44）/ `test_controller_web_ui.py`（5）/ `workspace_controller_mode_ui.test.cjs`（**静态用例定义 30**，75 行引用 `controllerStatusMeta`）/ `workspace_controller_ui.test.cjs`（**静态用例定义 33**，144-151 断言 `controllerStatusMeta` 导出） | 计数口径=行首 `test(` 用例定义数（#169 实测 33/30）；裸 `grep 'test('` 的 35/39 命中多出的是 `assert.ok(!/…/.test(...))` 正则方法调用（ui 292/528，mode 133/135/181/202/235/248/318/484/815），不是用例；两份文件**无循环展开用例**（`for` 循环均在单个用例内部）。本片未跑测试，静态数量不是通过数。历史通过数单列：mode=30/30（#164/#165 当时通过证据，见 `.tmp/controller-mode-c2-b-ux/implementation.md:45`、`.tmp/controller-mode-c2-b-ux-review/review.md:125`）。本合同引用其覆盖范围；改造片须同步更新并回归 |

## 2. 需求映射（用户已确认结论 1–5 + Codex 裁决 D-1–D-4）

| # | 确认结论 | 本合同落点 |
|---|---|---|
| 1 | 不再长期指定协调者；任务 `created_by` 即协调归属；不猜终端/模型身份、不引入会话绑定/ACK/租约 | §3、§4（新门禁以 created_by 为准） |
| 2 | 主被动为项目统一设置、只约束发起侧；执行/复核侧正常交付，切被动不取消在途；任何已有派发权限且获授权的 Agent 可发起；同一成员不同任务职责可不同 | §3、§7 |
| 3 | 各 Agent 用自身 API Key；Codex 入口实测 `caller_identity=human:bobo` 待切换；不靠自称补身份、不改历史 created_by、不绕授权 | §5（身份接入与历史衔接步骤，本片只定步骤不操作） |
| 4 | 取消固定主控标签/选择界面；受控等待改为“调用者是待跟进任务发起者”；工具约束代码核验、提示词辅助；active 不产生新权限 | §4（新门禁）、§6（退役兼容）、§7（UI/提示词） |
| 5 | 模型名称获取/展示、成员命名规则另拆片 | §10 明确出范围 |
| D-1 | `controller_assignment` 只读输出**暂留至少一个兼容版本**，注记明确弃用且不再决定协调/调度，不新增权限 | §6 退役表（已定案） |
| D-2 | 本期继续**拒绝** human 受控主动入口，不新增权限提案；human 用于管理与旧任务原身份收尾 | §4.1 G4、§5（已定案） |
| D-3 | 受控 true **强制显式非空 task_ids**、严格正整数型（bool/float 含 1.0/字符串/非正数均拒绝），先校验全部再稳定去重，按首次出现顺序逐唯一 ID 核验、各计一次 GET，非法项整批拒绝；false/省略及旧归一化行为不变 | §4.1 新 G7、§4.3 矩阵（已定案） |
| D-4 | 原 human `PATCH controller-assignment` **暂留兼容并标弃用**，CAS 与权限保持，不直接删库/数据/端点 | §6 退役表（已定案） |

## 3. 核心语义：按任务发起者调度【新方案·未实施】

1. **唯一协调归属依据**：任务的 `created_by`。它由服务端在创建时写入（`server/routes/tasks.py:1644-1646`），请求体不可指定（`server/models.py:906-1014`），且全路由无任何修改入口（§1），因此是**创建即固定、不可变**的事实。`target_member_id`（执行者）、业务角色标签（business_role）、决策分级（decision_tier）、模型名、终端名都不是协调资格。
2. **主被动是项目统一设置，只约束发起侧**：
   - 被动（默认）：派发后本轮结束，由人通知完成后再读取/收取。
   - 主动：发起者在**已获本次授权的任务流程内**等待交付、读取结果、安排独立复核并收尾；每一步走既有工具与既有权限。
   - 执行/复核侧不感知模式：正常完成已接任务；模式切换不取消在途任务、不重复收取、不扩大其派发权限、不自动开启下一片。
3. **角色范围绑定具体任务**：发起者身份只对“自己创建的任务”成立（`created_by == 调用者`），不自动套到根任务或全项目；同一成员可在任务 A 是发起者、在任务 B 是执行者。子任务继续遵守已有 `may_delegate`/epoch/预算门禁（`server/routes/tasks.py:386-441`），模式不改变决策分级。
4. **任何已有派发权限且获本次授权的 Agent 都可发起**：服务端 `POST /api/tasks` 顶层创建不要求 decision_tier；`talk_delegate_task` 对所有持有者可用。“可以发起”仍受每次任务授权的约束，active 不是授权来源。

## 4. 受控等待新合同【新方案·未实施；机制沿用 C2-A1】

### 4.0 不变项（兼容合同）

- `controlled_wait` 省略或为 `false` 的一切调用与现状**逐字段一致**：默认/最大 600 秒、clamp 行为、`_normalize_task_ids` 旧归一化语义（`None`→项目级、字符串 `int()` 通过、浮点截断、静默去重）、无身份 GET、无项目重读、返回结构无新字段、`return_reason` 仅 matched/timeout/api_error、对一切调用者同一行为。九个工具数量不变。
- 单次 deadline 记账、HTTP 剩余预算 clamp、30 秒重读节奏、query_stats 计数口径、JSONL 统计、进入期报错/运行期显式退出的二分失败策略，全部沿用 C2-A1 已实现机制。

### 4.1 进入门禁（新编号 G1–G8，顺序固定，任一不过=报错、不等待、绝不静默降级）

| # | 条件 | 不满足时 |
|---|---|---|
| G1 | `project_id` 可解析（参数或 `TALK_PROJECT_ID`） | 报错：受控等待必须有项目上下文 |
| G2 | `timeout_seconds` 显式传入、有限正数；bool/非数值/NaN/inf/0/负值拒绝 | 报错，不采用 600 秒默认 |
| G3 | 开始核验时剩余预算 > 0；`GET /api/members/me` 成功且响应含合法 id/kind | 报错（安全方向=拒绝，不猜身份） |
| G4 | `kind == "agent"` | 报错：human 凭据不作为 Agent 协调自证（**D-2 已定案**：本期维持拒绝，不开新权限提案；human 用于管理与旧任务原身份收尾，§5.3） |
| G5 | `GET /api/projects/{id}` 成功且响应含 `controller_mode`/`controller_mode_version`（新服务） | 报错：当前服务不支持受控等待；缺字段不猜 passive/active。**不再要求主控指定字段存在**：旧字段缺失不影响门禁，只在只读输出层如实降级（§6 D-1） |
| G6 | `requested_mode == "active"`（**用 G5 同一次项目响应判定，零新增请求**；前置到逐任务 GET 之前，passive/旧字段项目少发 N 次请求） | 报错：项目模式意向不是主动 |
| G7（新严格规则，D-3 已定案） | `task_ids` 必须**显式提供**（非省略/None）、为**数组类型**且**非空**；元素全部为**严格正整数**：bool、float（含 1.0 这类整数值浮点）、字符串、None、0、负整数、其它类型**一律拒绝**；**先校验全部元素**，任一非法即整批报错（不发任何任务 GET、不等待合法子集、不静默丢非法项）；全部合法后**稳定去重**（按首次出现顺序保留唯一 ID；重复不是错误）。**执行位置固定**：严格运行时校验就是 G7，在 G6 之后执行——新助手替换现行 `bridges/talk_task_tools.py:1253` 对 true 路径的宽松 `_normalize_task_ids` 调用（1253 位于 G3 身份 GET 之前，该前置位置与宽松语义均不得保留给 true 路径），也不得在 G3 之前做任何运行层严格校验。到达 G7 的非法输入（G1–G6 均已通过；含省略/空/混合非法）按进入参数错误：HTTP 恰 2 次（身份 1+项目 1）、任务 GET=0、`entry_gate=G7`、`return_reason=null`、恰一条 entry JSONL、无正常等待返回结构 | 报错：受控等待必须明确跟进的具体任务；非法项整批拒绝并如实指明 |
| G8 | 按 G7 去重后的顺序，**逐唯一 ID 各发恰好一次** `GET /api/tasks/{id}`：任务存在且对调用者可见、`task.project_id == 本项目`、`task.created_by == G3 身份` | **整批拒绝**（进入报错），语义与分类见 §4.4 |

**旧稿门禁编号映射**（#167 的 P2-1/P2-2 按旧稿编号定位，保留映射备查）：

| 旧稿（#166） | 本稿 | 说明 |
|---|---|---|
| 旧 G1–G4 | G1–G4 | 不变 |
| 旧 G5 | G5 | 收窄：不再要求指定字段 |
| 旧 G8（模式 active） | **G6** | 前置：信息在 G5 项目响应中零成本可得，后置只会多发 N 次任务 GET |
| 旧 G6（task_ids 非空） | **G7** | 扩展为 D-3 严格规则（P2-1 闭合点） |
| 旧 G7（逐任务核验） | **G8** | 扩展失败分类/预算语义（P2-2 闭合点） |
| 现行代码 G6（assignment==assigned）、G7a（调用者==指定主控） | **删除，无映射** | 固定主控依赖退役 |

- 门禁 HTTP（身份 1 次、项目 1 次、任务 N 次唯一 ID）全部计入同一 deadline 与 `query_stats.http_requests`（含失败尝试，`_api_request:243-245` 在发请求前自增）。
- **进入快照与返回结构**：受控路径返回结构在旧三字段上演进为 `controlled_wait: true`、`controlled_entry: <新快照>`、`controlled_rechecks: <次数>`；**非受控路径逐字段不变**。新 `controlled_entry` 键为 `{requested_mode, requested_version, caller_member_id, task_ids（去重后按首次出现顺序）, verified_task_count}`——**随新任务发起者合同演进，属受控路径内部键变化，旧消费者应重载 MCP 并按新合同读取**。`controlled_entry` 只在全部门禁通过后的返回结构中出现；进入核验未完成时不产生任何返回结构（直接报错）。**entry JSONL 的 `task_ids` 取值规则（R-6，统一 `record_entry_failure:1288` 与“调用者自己提交”表述）**：true 路径下 `selected_task_ids` 初始为 `None`，仅在 G7 全部合法后才设为“调用者显式提供、严格校验成功后按首次出现顺序稳定去重的 ID 列表”；G3–G6 失败及 G7 非法失败时 `task_ids=null`（未通过完整输入校验——G7 不部分保留合法子集、不落盘原始非法任意类型，由 `entry_gate`/`entry_error` 说明输入无效即可，不新增原始输入字段）；G8 失败日志可记录完整已合法输入去重列表，这些 ID 来自调用者而非任务响应，仅报错回显的不符/404 ID 也来自该列表，不断言 404 存在性、不给未核验任务响应事实；`controlled_entry` 成功快照只使用全部通过核验的事实；false 路径 JSONL/返回一切不变。entry 记录**不含逐任务响应内容，不泄露未验证任务信息**。

### 4.2 运行期：重读、退出与统计

- **任务归属是否需要运行期复核**：不需要。created_by 不可变（§1 证据），进入期核验一次即为全程事实。
- **每 30 秒重读**：只重读项目模式字段。`requested_mode ≠ active`、`requested_version` 与进入快照不一致、或模式字段缺失/失效 → `mode_changed` 正常退出（timed_out=false，tasks 为本轮轮询集合）。不再读取、不再比对主控指定字段。
- **正常退出枚举（受控路径）**：`matched` / `timeout` / `mode_changed`。**`controller_changed` 退役**：新合同不再读取主控指定，运行期不存在该类退出，`CONTROLLED_WAIT_EXIT_REASONS`（94-99）移除该值。
- **错误路径与正常枚举分开**：`api_error` **不是正常退出枚举值**，是错误路径——运行期任务轮询/项目重读的 TALK API/网络错误显式抛错（带真实 elapsed/rounds，恰落一条 `return_reason=api_error` 的 JSONL 统计），与 matched/timeout/mode_changed 的正常返回结构分开，不伪装成 timeout 或 matched。
- **检查顺序固定**：每轮先查任务命中（matched 优先），再按 30 秒节奏重读模式，再查 deadline，最后 sleep。matched 与 mode_changed 同时发生时返回 matched（确定且如实）。
- **deadline 归属**：剩余预算 ≤0 未发出下一请求 → 正常 `timeout`，返回最近一次成功轮询集合（从未轮询成功则 tasks=[]、task_count=0）；请求已发出后的网络/超时错误 → `api_error` 显式抛错。
- **只等待**：受控等待全程只读，不自动 collect/delegate、不改任务状态、不取消在途、不伪造 effective_mode 或调度互斥。
- **matched 边界**：`matched` 只表示任务状态命中，**不免除**下一动作前的资格检查；发起者在每个后续动作（读交付、派复核、收取、汇报）前按 §7.3 的约定级检查重读身份/模式/版本。

### 4.3 兼容测试矩阵（实施片验收必须逐行覆盖）

| 场景 | controlled_wait | 预期 | 类别 |
|---|---|---|---|
| 一切现有调用 | 省略/false | 与现状逐字节一致；零新增 HTTP；return_reason 仅 matched/timeout/api_error；`_normalize_task_ids` 旧语义不变 | 兼容回归 |
| false + 项目级查询（省略 task_ids） | false | 旧项目级轮询路径照常可用（现行用例 `tests/test_talk_controlled_wait.py:1209-1227` 保留） | 兼容回归 |
| 非项目路径 | true | G1 报错 | 进入报错 |
| 旧服务（缺模式字段） | true | G5 报错 | 进入报错 |
| 身份 GET 失败/响应缺 id/kind | true | G3 报错 | 进入报错 |
| human 凭据 | true | G4 报错（D-2） | 进入报错 |
| 模式为 passive | true | **G6 报错**（零任务 GET，http_requests=2） | 进入报错 |
| task_ids 省略/None/空数组 | true | G7 报错（零任务 GET，http_requests=2；计数口径见表下注） | 进入报错 |
| task_ids 非数组（字符串/数字/对象整体） | true | G7 报错 | 进入报错 |
| 元素为 bool（true/false） | true | G7 整批拒绝 | 进入报错 |
| 元素为 float（含 1.0 整数值浮点） | true | G7 整批拒绝，**不截断** | 进入报错 |
| 元素为字符串（含 "5"） | true | G7 整批拒绝，**不 int() 转换** | 进入报错 |
| 元素为 0/负整数 | true | G7 整批拒绝 | 进入报错 |
| 合法 ID 与非法项混合 | true | G7 整批拒绝，指明非法项；不等待合法子集、不静默丢非法项 | 进入报错 |
| 重复 ID（如 [7,7,9]） | true | G7 稳定去重为 [7,9]（按首次出现顺序）；G8 逐唯一 ID 各一次 GET（任务 GET 恰 2 次，http_requests=2+2=4） | 正常/进入 |
| 任务不存在/对调用者 404 | true | G8 整批拒绝：`return_reason=null`，措辞仅“不存在或不可见”，只回显调用者提交的 ID | 进入报错 |
| 第 k/N 个任务 GET 为其它 HTTP/网络错误 | true | G8 按 `api_error` 分类计失败尝试：`return_reason=api_error`，http_requests=2+k | 进入报错 |
| G8 核验中途剩余预算耗尽 | true | 按**进入错误**停止并说明核验进行到第几/共几个，**不进入轮询**；不与运行期正常 timeout 混淆 | 进入报错 |
| 任务属于其它项目（跨项目，含 project_id 为 null 的旧任务） | true | G8 整批拒绝 | 进入报错 |
| 混合发起者（任一 created_by ≠ 调用者） | true | G8 整批拒绝，指明不符项 ID | 进入报错 |
| 调用者是 target 而非 creator（执行者等自己执行的任务） | true | G8 拒绝：target 身份不是协调资格 | 进入报错 |
| 冒名：用他方 Key 等别人创建的任务 | true | G8 拒绝（Key 反查身份 ≠ created_by） | 进入报错 |
| 门禁全过、任务命中 | true | matched 提前返回（命中优先） | 正常 |
| 门禁全过、预算耗尽 | true | timeout（timed_out=true） | 正常 |
| 运行中模式转被动/版本变化/字段消失 | true | 下一重读节点 mode_changed 退出 | 运行退出 |
| 运行中项目重读或任务轮询 API 错误 | true | api_error 显式抛错，恰一条统计 | 运行报错 |
| 运行中主控指定变化 | true | **不产生任何退出**（不再读取指定字段） | 语义保持 |
| 模式切换在途任务 | — | 不取消在途、不重复收取（任务状态不受模式影响） | 语义保持 |
| 旧 human 任务（created_by=human:bobo）+ agent Key | true | G8 拒绝：agent 不能跟进 human 创建的任务；该任务由 human 侧被动收取（§5.3） | 进入报错 |

**G7 非法输入计数口径（R-4 表下注，与门禁表/§4.4/计划一致）**：到达 G7 的非法输入（G1–G6 均已通过，含省略/空/非数组/混合非法）恰 2 次 HTTP（身份 1+项目 1）、任务 GET=0、`entry_gate=G7`、`return_reason=null`、恰一条 entry JSONL（`task_ids=null`）、无正常等待返回结构。更早门禁拒绝的输入按相应门禁计数，**不能称所有非法输入一律 2 次**：G1/G2 在发出任何 HTTP 前报错（http_requests=0、不写 entry 记录）；身份 GET 失败在 G3 拒绝（http_requests=1）；human 凭据在 G4 拒绝（http_requests=1）；旧服务/缺模式字段在 G5、passive 在 G6（http_requests=2）。宿主/MCP schema 先拒绝且未进入 wait 函数的输入属**外层拒绝**，不归本函数 G7 统计、不产生 entry 记录，不编造 entry 日志。

### 4.4 进入期 G8 的失败分类、预算与消息语义（P2-2 闭合，新规则）

- **404 = 业务拒绝**：逐任务 GET 返回 404（“不存在”与“对调用者不可见”同形，`server/routes/tasks.py:82-85`）按 G8 业务拒绝处理：`record_entry_failure(gate="G8", api_error=False)`，JSONL `return_reason=null`；错误措辞**只有**“任务 <id> 不存在或对当前调用者不可见”，只回显 G7 校验通过后来自调用者提交去重列表中的 task_id（ID 来自调用者而非任务响应），**不断言任务“不存在”**，不携带任何任务内容。
- **其它 HTTP/网络失败 = api_error**：5xx、401/403、连接/读取超时、OSError 等按 `api_error=True` 分类，计入失败尝试（发请求前已计数）。
- **可靠状态码识别**：现行 `_api_request`（250-261）只把状态码编进错误文案。I-1 须在桥内新增**结构化状态码出口**（如 `TalkApiHttpError(TalkToolError)` 子类携带 `.status`，HTTPError 分支抛出，消息文本形态保持兼容），G8 只按 `.status == 404` 判定业务拒绝，**不得脆弱解析整段错误文案**。
- **预算语义**：每个唯一 ID 发 GET **之前**检查 `remaining() > 0`；不足即按**进入错误**停止（`api_error=False`，`entry_error` 如实说明“任务核验进行到第 k/N 个时剩余预算耗尽，未完成核验”），不进入轮询、不借运行期正常 timeout 混淆。每次 GET 之后、发下一请求之前同样核对能否合法继续（与现行 1399-1400/1410-1411 同型）。保留既有边界：socket 单请求超时不等于端到端硬抢占，同步 stdio 无硬中断。
- **计数/记录预期**（N = 去重后唯一 ID 数）：
  - G7 非法输入（未进入 G8）：http_requests = 2（身份 1+项目 1，任务 GET=0）；恰一条 entry 记录（`entry_gate="G7"`、`return_reason=null`、`task_ids=null`）；更早门禁或外层拒绝的计数见 §4.3 表下注。
  - 全部通过（0 次失败）：http_requests = 2 + N；进入运行期。
  - 第 k 个 404：http_requests = 2 + k；恰一条 entry 记录（`entry_gate="G8"`、`return_reason=null`、`task_ids`=完整已合法去重列表）；整批拒绝。
  - 第 k 个 api_error：http_requests = 2 + k；恰一条 entry 记录（`entry_gate="G8"`、`return_reason=api_error`、`task_ids`=完整已合法去重列表）。
  - 第 k 个**之前**预算耗尽：http_requests = 2 + (k-1)；恰一条 entry 记录（`entry_gate="G8"`、`return_reason=null`、`task_ids`=完整已合法去重列表），`entry_error` 说明核验未完成。
  - 不存在“部分失败后等待合法子集”的语义：任一不符即整批拒绝。
- **口径一致**：全稿统一为——进入期失败=报错（entry JSONL，`return_reason` ∈ {null, api_error}，无返回结构）；运行期正常退出 ∈ {matched, timeout, mode_changed}；运行期错误=api_error 显式抛错（恰一条统计）。

## 5. 权限与历史衔接【部分现行事实 + 新方案步骤，本片不操作】

### 5.1 权限维持现状（不变项）

普通派发/领取/执行/提交/读取/收取、澄清协议、树治理、授权预算（may_delegate/深度/并发/切片/TTL，仅 human 可授）、human 管理权限（模式/指定 CAS、accept-milestone、成员禁用）全部维持现状。本方案**不新增、不收窄**任何服务端权限。human 继续用于管理与旧任务原身份收尾（D-2）。

### 5.2 created_by 可改性核对结论（代码事实，非猜测）

`AgentTaskCreate` 无 created_by 字段（`server/models.py:906-1014`）；任务路由无更新 created_by 的端点（§1）。因此“迁移历史发起者”在现有 API 下本就无合法入口，本合同明确**不做**也**不允许**为此新增入口。

### 5.3 Codex 入口 Key 切换与历史任务衔接（只定步骤，本片绝不读取/输出/写入密钥）

现状事实（任务包告知 + 历史实测记录）：Codex 桌面 MCP 入口 `caller_identity=human:bobo`，旧任务 `created_by=human:bobo`。切换步骤（后续身份接入片 I-0 交付、其人工门禁执行，需备份与如实核验）：

1. **切换前收尾**：盘点 human:bobo 创建的在途/已提交未收取任务；能收尾的先由 human 凭据/页面走完收取（human 身份对其创建的任务有完整读取/收取权限，`server/routes/tasks.py:82-85, 2487-2501`）。暂不能收尾的保留原状，**不迁移 created_by、不给所有 Agent 放宽收取**。
2. **备份**：备份当前 Codex 桌面 MCP 配置（仅追加/替换 Key 项前的完整文件快照），记录可回退路径。
3. **切换**：把 Codex 桌面 MCP 入口的 `TALK_API_KEY` 换为 `agent:codex` 本人 Key；不共用人类 Key、不用模型自称补身份。
4. **核验**：重连后 `talk_list_agents` 实测 `caller_identity.member_id == agent:codex`；试派一个无破坏性任务，核对新任务 `created_by == agent:codex`。核验失败即回退备份并如实记录。
5. **衔接规则**：切换后，Codex 以 agent:codex 创建的新任务按本合同跟进；历史 human:bobo 任务继续由 human 凭据/页面收取——agent:codex 对旧任务无 created_by 资格（受控等待 G8 会拒绝，这是预期安全行为，不是缺陷）。
6. DeepSeek/Kimi 入口同理核验自身 Key 与 `caller_identity` 一致；本片不操作、不承诺已完成。

**明确不做**：不追改历史任务发起者；不给 agent 放开对他人任务的收取；不引入终端识别或同一 member 多会话互斥（本设计不承诺这两项）。

## 6. 固定主控退役兼容【新方案·未实施；D-1/D-4 已定案】

优先**最小兼容**方案，分步退役，绝不为删 UI 直接删库/改历史数据：

| 对象 | 处理 | 理由/风险 |
|---|---|---|
| `Project.controller_member_id` / `controller_assignment_version` 字段 | **保留**，不删库、不清历史值 | 历史数据与审计事实；删除是不可逆破坏性变更，须另案确认 |
| `PATCH /api/projects/{id}/controller-assignment` | **保留但弃用标记**（D-4 已定案）：仍仅 human 可写、CAS 与候选校验不变，但写入结果不再被任何调度/门禁读取 | 直接删端点会破坏旧客户端；保留的成本是“有人写了一个不再生效的指定”，由文案与只读注记如实说明 |
| `controller_assignment_status` / `resolve_controller_assignment_status` | 保留（ProjectOut 继续携带），但不再决定调度 | 旧服务/旧客户端按事实降级 |
| `talk_list_agents` 的 `controller_assignment` 只读输出 | **暂留至少一个兼容版本并加弃用注记**（D-1 已定案）：note 改为“该指定为历史兼容字段，已弃用，不再决定任何协调/调度，不产生任何权限” | 给旧消费者一个如实降级窗口；缺字段仍按 supported=false 降级 |
| 受控等待对 assignment 的依赖（现行 G6/G7、`controller_changed`、recheck 指定比对） | **移除**：新门禁不读取指定字段；`controller_changed` 枚举退役；`recheck_project` 删除指定比对（1454-1471）；`poll_round_tasks` 无 ID 项目级受控分支（1410-1424）随 D-3 移除（死分支，见 §9 I-1） | 这是本合同的核心变更 |
| Web UI 主控选择/提示 | **移除可见入口**（完整调用链清单见 §9 I-2，不是整块删除）：`web/index.html:256-275` 主控面板区块、`web/workspace.js:727-1090` 主控面板逻辑（注意 743 `controllerStatusMeta` 被模式面板 1142 调用、1529 导出，须先解除模式面板依赖再删共享助手）、`web/app.js:879-882`/`1054-1062` 两处调用点、`web/workspace.js:624/643/654/699` 文案与徽标、`web/index.html:120`“任务由主控分配”、`web/index.html:245`“供主控派发任务前读取” | 只移除可见 UI 与其前端逻辑，不动后端字段/端点 |
| bridge 侧活跃提示/输出/快照正文 | **逐项改写**（精确位置见 §1 与 §9 I-1）：`PROJECT_REQUIREMENTS_SNAPSHOT_NOTE`（147-150，写入每个新任务正文）“由主控在派发时”→“由任务发起者在派发时”；`WAIT_COUNTING_NOTE`（66-72，每次等待返回）“需由主控在外部实测”→“需由任务发起者（调用方）在外部实测”；`talk_list_agents` 工具描述（1682）“主控派发新任务前应先读取…”→“任务发起者派发新任务前应先读取…”；`CONTROLLER_ASSIGNMENT_*` 注记（170-198）加弃用前缀（D-1）；受控门禁注释/注记/工具描述/错误消息（86、100-113、1361-1385、1631-1656、1784-1848）随新 G1–G8 重写 | 新任务用“任务发起者/协调方”等准确词；**旧存储任务快照/结果/历史原文不追改**，不做全仓无差别替换 |
| 旧客户端/旧 MCP 进程 | 旧进程内旧 G6/G7 代码继续按旧行为运行（代码事实）；能力缺口按事实降级，不做运行时热修补 | 分步加载要求见下 |
| **分步加载顺序与过渡窗口** | **I-1 工具先行、MCP 重连加载后，I-2 UI 才退役主控面板**。窗口期（工具已改、UI 未改）如实登记：页面仍展示主控面板/徽标与“主控指定不可用”提示，但旧指定已**零执行意义**，旧页面**不能继续被描述为新调度资格依据**，也不得宣称新主动生效已验收；窗口期不进行或宣称真实主动消费者验收。**I-1/I-2 串行开发、独立复核、可分别提交回退，但纳入同一人工验收轮**以缩短窗口（详见 §9） | 避免“前端先显示不实生效”与“指定仍被当有效职责”两类误导 |
| `effective_mode` | 仍恒 `null`/`not_bound`，直到真实消费者链路验收通过（§9 I-4）；不虚构自动运行 | 沿用 C2 既有纪律 |

## 7. 页面与消费者合同【新方案·未实施】

### 7.1 项目设置页

- 调度模式面板**保留**，继续显式保存主被动（human 可写、agent 只读、CAS、409 只重读不自动重写）。
- #164/#165 已验收行为**全部保持、不回退**：未保存模式选择离页丢弃、返回已确认 saved、同页重绘保留、保存在途真实结果照常核实、内部 CAS 保留、409 仅 GET 重读、agent 只读、其它编辑区草稿不回归、静态资源版本纪律。
- 模式面板**解除对主控指定的全部依赖**（1129-1150 三函数、1121/1258/1277-1278 状态键、1372-1376 提示分支随主控概念删除）；保存“主动”的提示改为固定文案，不再查询指定状态。
- 文案改写为发起者语义（草稿）：
  - 被动说明：`派发任务后本轮结束，由你通知完成后再读取与收取。当前所有项目默认此模式。`
  - 主动说明：`任务发起者在等待期间继续读取交付、交独立复核并收尾。保存“主动”只是设置意向，不等于已生效：没有任何会话因此被唤醒或自动运行；已结束的对话仍需人工唤回。`
  - “实际执行”行保持：`尚无生效的主动调度（本版本不支持自动生效）`，直到 §9 I-4 验收。
  - 删除原“无主控/主控不可用”前置提示（主控概念已退役）；模式保存不再依赖任何指定状态。
  - 面板 hint 改为：`这里保存的是项目的调度模式意向：只记录设置，不唤醒任何会话、不自动运行任务。模式只约束任务发起侧：被动为派发后结束、由你通知后继续；主动为任务发起者在已获授权的任务流程内等待交付、读取结果、安排独立复核并收尾。`

### 7.2 模式语义边界

- `active` 只针对**发起方**在已获授权的任务流程内的行为；不能唤醒已结束会话、不能自动接管别人创建的任务、不能取消或干预执行者在途任务。
- 执行/复核者**不读模式、不依赖模式**：正常完成已接任务并交付；模式变化不产生任何执行侧动作。

### 7.3 C2-C 提示词（按新发起者规则重写，约定级）

- 主动推进资格改述为：`caller_identity.member_id` == 待跟进任务的 `created_by`、kind=agent、项目模式 active 且版本与记录一致；资格依据**任务包现有职责与任务 created_by**，不依模型自报、终端名或固定主控标签。
- 每次后续动作（读交付、派复核、收取、汇报）前重新 `talk_list_agents` 核对身份/模式/版本（约定级，无代码强制；matched 不是资格凭证）。
- 逐步派发复核/收取均按现有权限与任务授权；不开发自动转审引擎、后台常驻或全角色界面。
- 约定级与代码级边界区分写明：代码级=受控等待门禁（G1–G8）与服务端权限；约定级=发起者会话的推进纪律与总预算自我管理。

## 8. 等待预算与终端适配【现行事实沿用】

必读并执行 `docs/guides/TERMINAL_MCP.md`「终端适配必查：工具超时与等待预算」：

| 项 | 记录要求 | 当前事实 |
|---|---|---|
| 客户端单次工具上限 T | 各终端自行核验配置键/取值/单位/依据来源 | DeepSeek 桌面 65000ms（配置事实，`deploy/dsh/desktop-talk-mcp.patch.template.yml:54`）；Codex 当前会话的 T **本轮未新核验**（660 秒仅旧文档/模板依据）；Kimi 模板 `toolTimeoutMs: 660000` 是模板事实 |
| 显式等待 W | 显式传 `timeout_seconds`，W+余量≤T，余量≥5 秒参考 | DeepSeek 桌面 W=50 秒（留 15 秒）；Codex 保持用户现用 W=300 秒；其它终端按真实 T 定 |
| 执行者任务预算 | 与等待预算分别记录 | bridge 执行超时（现用 3600 秒）与等待时长互不影响；等待到期不取消/重派/重启执行者任务 |

- 保留既有边界：同步 stdio 占用（等待期间同连接其它调用排队）、客户端取消不会立即停止程序侧等待、socket 单请求超时不等于端到端硬截止。
- 正常到期（timeout）/命中（matched）/API 错误（api_error）/客户端取消/后续查询验证**分开记录**，不得混为“任务完成”或“普通到期”。
- 本片不启动终端、不调用生产长等待；模板检查或源码检查不得称为真实终端通过。

## 9. 实施切片总览（详见 implementation_plan.md）

| 片 | 内容 | 建议分工 | 人工门禁 |
|---|---|---|---|
| I-0 身份接入准备 | Key 切换步骤文档化与备份方案（§5.3），不执行切换 | Codex 主导，Kimi/DeepSeek 提供核验清单 | 切换与回退由用户确认后执行 |
| I-1 发起者受控工具与测试 | `talk_wait_tasks` 新门禁 G1–G8（含 G7 严格 task_ids、G8 失败分类与结构化状态码）、`controller_changed` 退役、受控死分支移除、list_agents 弃用注记（D-1）、bridge 侧提示/快照文案改写、测试改造 | DeepSeek 开发 / Kimi 复核 | 无页面变化；MCP 重连后加载检查 |
| I-2 主控 UI 退役及说明 | §6 表内 UI 移除与文案（含 app.js 两处调用点、模式面板主控依赖点、共享助手退役顺序）、模式面板发起者语义文案、测试同步 | Kimi 开发 / DeepSeek 复核 | 与 I-1 同一人工验收轮（用户页面验收） |
| I-3 C2-C 提示词与指南修订 | §7.3 提示词、TERMINAL_MCP/DSH_DESKTOP/AGENTS 等指南同步（精确清单见 implementation_plan §1 I-3 表） | Kimi 起草 / DeepSeek 复核文本；正式文档由 Codex 收尾落盘 | 文档评审 |
| I-4 真实消费者验收 | Codex 自身 Key 创建任务→按模式跟进→执行者只交付；DeepSeek 自身 Key 另起一任务同理；记录 return_reason/重读/身份实测 | Codex 组织，用户验收 | 人工验收；通过前 effective_mode 保持 null |

**共同人工验收轮（P2-4 已定案）**：I-1/I-2 串行开发、各自独立复核、可分别提交回退，但**纳入同一人工验收轮**；在工具已改而 UI 未改、指南身份未准备的过渡阶段，**不进行或宣称真实主动消费者验收**，并明确登记遗留界面状态/限制（§6 过渡窗口行）；I-4 以 I-0 Key 切换核验完成 + I-1 已重连加载 + I-3 指南就绪为前提；不并行改码。

## 10. 明确出范围

- 模型名称获取/上报、页面以模型名替代裸 ID 展示：按路线图另拆片，本合同只保留 member_id 作为内部身份键。
- 成员默认/自定义命名与重名规则：留完整角色页面设计，本片不定规则。
- human 受控主动入口：D-2 已定案本期拒绝，不登记新提案。
- 自动转审引擎、后台常驻调度、全角色界面、取消协议（旧 C2-D）：均不在本片。

## 11. Codex 裁决记录（D-1–D-4 已定案，不再是开放项）

- **D-1**：`talk_list_agents.controller_assignment` 只读输出**暂留至少一个兼容版本**，注记明确弃用且不再决定协调/调度，不新增权限。→ §6 退役表、I-1 注记改写。
- **D-2**：本期**继续拒绝** human 受控主动入口，不新增权限提案；human 用于管理与旧任务原身份收尾。→ §4.1 G4、§5.3。
- **D-3**：受控 true **强制显式非空 task_ids**、严格正整数型（bool/float 含 1.0/字符串/非正数均拒绝），先校验全部再稳定去重，按首次出现顺序逐唯一 ID 核验、各计一次 GET，非法项整批拒绝；false/省略及旧 `_normalize_task_ids` 语义不变。→ §4.1 G7、§4.3 矩阵、I-1 死分支移除。
- **D-4**：原 human `PATCH controller-assignment` **暂留兼容并标弃用**，CAS 与权限保持，不直接删库/数据/端点。→ §6 退役表、I-3 文档注记。

以上四条经 #167 独立源码可行性核验（可行且无矛盾），但均为**已确定的设计选项，当前未实现**，不得写成已实现。

## 12. 未实施/未实测声明（如实）

- 本片零代码/零配置/零数据库改动；§3–§9 全部为目标设计，未实施；D-1–D-4 为已确定设计选项而非已实现行为。
- 未运行任何测试、未启动服务/终端/MCP、未创建真实任务、未做真实等待或 Key 切换、未读取/输出/写入任何凭据。
- `caller_identity=human:bobo` 为历史实测记录，本轮未重测；Codex 客户端真实 T 未新核验；Kimi `toolTimeoutMs: 660000` 仅为模板事实。
- 行号证据沿用 #168 在 HEAD `603538b`、#169 在 HEAD `9e3e34d` 的实读（`9e3e34d→91b2bf2` 仅三份主控记录，业务内容与 `9272020` 基线及当前 HEAD `91b2bf2` 逐字节一致），后续代码变化需复核者重新核对。
- 现行固定主控实现（C2-A1 工具、C2-B 页面、C1b-S2 主控面板）在本合同实施前**继续有效**；本合同通过复核与裁决前，不作为任何开发依据。#166/#168 稿与 #167/#169 复核报告为历史文件，不追改；#166/#168 仍不收取。


## I-1历史实施状态与预算边界补充（2026-10-06，加载状态已由后节替代）

- #172经#173独立实际代码复核通过，六模块162项及七探针通过，任务已收取；源码实现G1–G8与任务发起者归属。旧UI/自身Key/消费者/真实主动链路待后续，当前连接实测仍G1–G7，须先重连加载。
- 上文原v3草拟正文的“现行事实/新方案未实施/本片/当前HEAD/未收取”等按#170当时快照理解；I-1实现已由本节替代，I-0/I-2/I-3/I-4目标仍未验收。当前实施状态以本节及PROGRESS为准，原审查/草稿历史不追改。
- §4.4预算边界：每个后续GET必须有剩余预算，未完成整批核验时预算耗尽仍入口错误；若末次响应已全部通过归属核验、不需下一GET，则按独立P4已验路径进入首轮并正常timeout返回已核验集合。socket不提供端到端硬截止，这一路不是未核验集合进入运行期，也不授权追加请求或自动续等。
- O1计数说明显式点名G8 GET、O2旧timeout schema描述与实际clamp文字差异登记I-3后续同步；未改已复核代码。

## 当前实施状态（2026-10-07）

- 当前 Codex MCP 的九工具目录、新 G1–G8 及发起者/assignment 弃用注记与运行时一致；显式 W=1 秒 false 对历史已收取任务立即 matched，human true 按 G4 拒绝，后续查询正常。当前入口加载门禁通过；短路径不代表真实 Agent G8、主动消费者、长等待/取消排队或其它终端通过。证据 .tmp/initiator-mode-tools-loadcheck/2026-10-07-loaded.json，旧失败证据保留。
- I-2 #174 经 #175 实际代码/全部差异独立复核通过并收取，固定主控页面功能依赖已退役；模式 human 写/agent 读、CAS/409、#164/#165 行为保留，四资源版本 20261007-initiator-mode-ui。独立 149 Node（同进程）/12 Python 页面契约及符号/导航探针通过，默认进程隔离 spawn EPERM 未取得项目用例结果。当前 UI 行为与边界见 MODULE_webui、USER_MANUAL 和 [人工验收步骤](../guides/INITIATOR_MODE_UI_ACCEPTANCE.md)。
- caller_identity 仍 human:bobo，requested passive/version4、effective null/not_bound；旧指定 agent:codex/version13 只兼容回显，不作为资格依据。I-0 实际身份切换、I-3 消费者/现行文案、I-4 真实主动链路尚未实施；本轮没有自动唤醒/生效，也未改变权限或历史发起者。
- I-1/I-2 本轮用户页面验收已于2026-10-07通过，人工门禁释放；主控未操作浏览器，用户未逐项声明键盘/窄屏/真实 HTTP 并发等可选项，不外推覆盖。#175 O-1 测试说明/stub 整理非阻塞，O-2 角色说明 hint/两旧注释随 I-3 同步；旧正文的未实施状态及复核原件均作历史，不追改。

## I-0步骤准备已通过（2026-10-07）

- 176经177独立全文/限定源码/指南出处复核通过并由原human入口收取。正式[切换与回退清单](../guides/CODEX_TALK_IDENTITY_SWITCH.md)由Codex发布，保留原稿/报告，补清行号、快照免责声明、执行者预算与F4恢复主体；复核窗口仅三份进度管理差异、业务/交付SHA未变的事实不扩大并行审改范围。
- 此结论只覆盖准备步骤，§5.3的实际Key切换/备份/重连/试派均未执行；caller仍human:bobo。原I-0执行需用户确认，实施前核配置/安全Key/名册/宿主预算并刷新旧任务；不迁移历史created_by、不放宽收取、不将active意向或步骤审查当作主动消费者生效。
