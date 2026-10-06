# 固定主控版调度合同历史归档

> 2026-10-06归档。下方完整保留发布发起者合同之前的旧合同原文；旧固定主控方案不再作为后续实施依据。历史C2-A1/C2-B实现和验证事实保持，当前目标合同见[CONTROLLER_MODE_DESIGN.md](CONTROLLER_MODE_DESIGN.md)。

# 主被动调度实施合同（C2，C2-A1/C2-B代码复核通过，页面/主动链路待验收）

> C2-B-UX补充状态：#164开发经#165独立实际接线/生命周期与回归复核通过并已收取；离页丢弃未保存模式选择、返回saved，状态行去版本，内部CAS保留。新增接线33/模式30/十二Node178/恢复7与12/集成15/Python12通过，页面/真实HTTP仍待人工验收。后续已登记按任务发起者调度/取消固定主控，须另行修订本合同执行门禁；当前旧主控门禁继续如实描述。
> 2026-10-06当前状态：C2-A1经#156开发/#157实际代码独立审查/#158修正/#159定向复核通过，F-1重读错误缺包装/统计已关闭，三项任务已收取。代码实现与运行中MCP加载、真实主动链路验收分开；Codex当前连接已通过新字段和短预算加载检查。C2-B经#160开发/#161独立审查/#162修正/#163定向复核通过，恢复入口和降级记录两项关闭，相关任务已收取，界面待用户验收；C2-C约定消费者与指南仍待开发，effective_mode仍null/not_bound。下方原方案基线/源码行号是2026-10-05设计时记录，原临时报告保持不改。
>
> 用户新增的通用终端适配要求见[TERMINAL_MCP.md](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)。单次等待必须匹配各终端实际工具调用上限并留余量；DeepSeek桌面65秒时选50秒，Codex保持用户现用300秒。到期正常返回不自动续等，主动消费者再次核验模式/身份/指定/总预算后才决定下一次调用；适配通过必须有客户端预算与正常到期/错误分类的证据。

> 2026-10-05 Codex 开工裁决：#152方案经#153独立复核、#154修订与#155定向复核，足够作为C2-A1开工依据。下方正文从已审修订版落盘，并回填#155的R1–R5；原临时开发/复核文件只读保留。设计确认不表示主动功能已实现，当前MCP的effective_mode仍为null/not_bound。
>
> R1响应阶段超时归一、R2正预算校验、R3身份固定形状、R5早退结果属于C2-A1实现验收；R4逐动作前重新读配置属于C2-C提示词合同，仍为约定级，不新增所有权/ACK/租约。前端C2-B已实现“参与任务”双横线保留一条，页面待验收；低风险版本耗尽与真正取消另登记，不扩大首片。


> 本片只做方案修订，不修改任何业务代码 / 数据库 / 运行配置 / 权限 / 服务。执行者 agent:kimi；完成后暂停，由 Codex 交 DeepSeek 定向复核，再决定是否实施。
> 修订对象：#152 原方案 `.tmp/controller-mode-c2-plan/report.md`（22401 字节，SHA256=e087793ebe6541965928c449f340647c44a263cdf794618de8ead53676c91144，只读不覆盖）；修订依据：#153 独立复核 `.tmp/controller-mode-c2-plan-review/review.md`（21548 字节，SHA256=90f2dfa05790a37ec83d48311d3aeed7645b3ad6df3d14da52c111af5963a499）结论"需修订、无阻塞"及 Codex 裁决。P1–P7 逐项修订对照见同目录 `revisions.md`。
> 原方案已通过部分（§2 项目设置交互 / CAS 与账号项目隔离 / 长期唯一主控 / 授权边界 / §8 桌面提示词合同 / §7 双横线归属）保留；本版替换 §4–§6 的执行合同与切片定义，并按 P1–P7 收紧 §1/§5/§9 表述。

## 0. 基线与范围

- 实际基线：分支 `codex/terminal-return-codex`，HEAD `9689062d45895b8a8a639e660c12153afa640154`（"收取主被动方案复核并派发定向修订"），`git status --porcelain` 无输出。相对 #153 复核基线 `b7fe7ce` 仅 3 个 docs 文件（PROGRESS / PROGRESS_HISTORY / DEVELOPMENT_ROADMAP），业务源码 diff 为空。
- 实际差异：本片只新增 `.tmp/controller-mode-c2-plan-fix/` 下的 report.md / revisions.md / development.json（`.tmp/` 不入库）；业务源码 diff 为空。原件（#152 方案与开发包、#153 复核与证据）全部只读，不覆盖。
- 当前事实核对（本轮实际读取，非猜测）：
  - `talk_list_agents` 对项目路径返回 `controller_mode`（requested_mode/requested_version/effective_mode=null/effective_status=not_bound）与 `controller_assignment`（member_id/version/status）；非项目路径两者为 `null`。
  - 项目 `prj_e8fe7066bbec` 长期主控指定：`agent:codex`，status `assigned`（仅职责配置有效，不代表在线/ACK/授权）。
  - Web 端已有"项目主控"指定/解除面板（C1b-S2），没有任何主被动模式开关 UI（`web/` 下无 `controller_mode` 引用）。
  - 入口身份事实（任务包告知，本片不改动）：主控工具返回 #152/#153 `task_ref.created_by=human:bobo`，而长期 `controller_assignment=agent:codex`。当前 Codex 桌面请求者身份未经核验，不能猜成 `agent:codex`，也不能把 human 凭据当 agent 自证（详见 §5.2 与 §6 C2-C）。

## 1. 实际代码核对证据

#153 已逐条独立确认原 §1 证据表的文件与行号全部命中、业务零改动，本版不重复全部探针，仅保留原表并增补修订点涉及的新核对行（本轮实际读取）。

| 能力 | 文件：行 | 事实 |
|---|---|---|
| 模式字段与默认值 | `server/models.py:112-116` | `Project.controller_mode` 默认 `passive`；`controller_mode_version` 默认 0；只允许 passive/active（`models.py:213-215`） |
| 主控指定字段 | `server/models.py:117-124` | `controller_member_id` 可空、`controller_assignment_version` 独立，刻意不复用模式版本 |
| 模式 CAS 写入 | `server/routes/projects.py:507-558` | `PATCH /api/projects/{id}/controller-mode`，仅 human；条件 UPDATE（project_id + 版本 + 意向实际变化）原子 +1；陈旧版本 409（含同值）；合法同值 200 不增版本；项目不存在 404 |
| 模式版本耗尽缺口（定性已更正，见 §6 C2-A2） | `server/routes/projects.py:528-540` 对比 `projects.py:603-608, 645-652` | controller-assignment 有 `version < SQLITE_SIGNED_INTEGER_MAX` 耗尽保护与显式 exhausted 409 分支，controller-mode 没有。真实机制（#153 内存 SQLite+pydantic 探针，非真实服务实测）：版本达 2^63-1 后再变更，条件 UPDATE 命中写入，SQLite 把列从 INTEGER **静默退化为 REAL**（9.223372036854776e+18）→ `ProjectOut.controller_mode_version: int` 校验失败（int_parsing_size）→ 该 PATCH 返回 500，且同一项目后续任何走 `ProjectOut` 的读取（含 GET 项目）也 500；请求模型 `expected_version` 上界为 MAX，等值永不成立 → 该端点**永久锁死**。自然变更到 MAX 不可现实达到（需 2^63-1 次真实意向变化），定低风险 |
| 主控指定 CAS 写入 | `server/routes/projects.py:561-665` | 仅 human；已有其他指定时 409 须先解除；候选校验；同值 200、陈旧 409、耗尽 409 |
| 项目读取输出 | `server/models.py:1360-1401` | `ProjectOut` 同携两组字段；status 由 `resolve_controller_assignment_status`（`models.py:308-326`）实时计算 |
| MCP 只读输出 | `bridges/talk_task_tools.py:298-391` | `controller_mode_summary` / `controller_assignment_summary` 与开发要求复用同一次项目 GET（`talk_task_tools.py:397-401`）；旧后端缺字段 → supported=false / unsupported；非项目路径显式 null（`470-472`） |
| MCP 工具描述边界 | `bridges/talk_task_tools.py:92-122, 1033-1048` | 工具描述明确"保存 active ≠ 已生效 ≠ 已唤回会话，不产生等待/调度/派发或任何授权" |
| stdio 顺序处理 | `bridges/talk_send_mcp.py:125-191` | `main()` 逐行 `for line in sys.stdin`，`dispatch_tool` 同步执行（行 173）；等待阻塞期间主循环不读 stdin；无 signal/select/线程（#153 全仓确认），`notifications/cancelled` 在 dispatch 阻塞时读不到。桌面入口 `bridges/talk_terminal_mcp.py:161` 复用同一 `main(include_deferred_send=False)` |
| 等待实现 | `bridges/talk_task_tools.py:875-1019` | `wait_tasks` 同步阻塞轮询，最长/默认 600 秒；轮询 0.5s 指数退避至 5s 上限；sleep 已按剩余 deadline 截断（行 1017）；`return_reason` 现状仅 `matched` / `timeout` / `api_error`；建议客户端预算 ≥660s（行 39） |
| 单次 HTTP 超时写死 | `bridges/talk_task_tools.py:172-174` | `_api_request` 内 `urlopen(request, timeout=10)` 固定 10 秒，无参数；受控等待若只限制轮询总循环，一次 HTTP 仍可超出剩余预算（§5.3 的 deadline 记账必须覆盖它） |
| 身份解析现状（双源） | `bridges/talk_task_tools.py:202-207` | `_member_id()` **优先取 `TALK_MEMBER_ID` 环境变量**，否则才 `GET /api/members/me`；受控门禁不得复用它（§5.2） |
| 身份反查 API | `server/routes/members.py:103-106`、`server/models.py:498-505` | `GET /api/members/me` 按 API Key 反查返回 `MemberOut`，含 `id` 与 `kind`（human/agent）、`disabled_at`；这是服务端事实，不受桌面 UI / 模型 / 会话标题影响（DSH_DESKTOP_TALK_MCP §4："请求者身份来自密钥，入口忽略继承的 TALK_MEMBER_ID"） |
| dispatch 不传身份 | `bridges/talk_task_tools.py:1323-1329` | `dispatch_tool("talk_wait_tasks")` 只传 project_id/task_ids/workflow_statuses/timeout_seconds 四个参数，服务端与桥内均无请求者身份与项目模式校验——通用 wait 今天对一切调用者同一行为 |
| query_stats 现状覆盖 | `bridges/talk_task_tools.py:906, 944-949, 979-985` | `query_stats.http_requests` 只统计 `wait_tasks` 轮询循环里带 `stats=` 的任务 GET / list_tasks；`_member_id()` 的 `/api/members/me`（行 206）与 `list_agents` 的项目/成员 GET 不带 stats，不计入任何 query_stats；`list_agents` 返回结构里**没有** query_stats 字段 |
| 工具集合数量 | `bridges/talk_task_tools.py:1022-1277` | TOOL_SCHEMAS 恰 9 个：list_agents / delegate_task / get_task / list_tasks / wait_tasks / reply_task / cancel_task / collect_result / get_delivery；本方案不新增工具 |
| 客户端预算事实来源 | `deploy/dsh/desktop-talk-mcp.patch.template.yml:54`、`deploy/dsh/talk-mcp.patch.template.yml:36` | 桌面模板与本机已配置 `toolCallTimeoutMs: 65000`（65 秒，单次 tools/call 上限）；**65 秒是配置事实** |
| 660 秒来源定性 | `docs/spec/MODULE_bridges.md:204`、`deploy/kimi-code/mcp.talk.template.json:16`、`bridges/talk_task_tools.py:39` | "Codex 用户级 MCP 调用预算 660 秒"、Kimi 模板 `toolTimeoutMs: 660000`、`WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS=660` 均为**既有文档/模板依据**，本片未读取运行中的宿主配置，不能写成"当前已核验可用" |
| 既有 bridge 提示词注入 | `bridges/cli_bridge.py:1160, 1226-1227, 2359, 2776, 2911` | 任务 prompt 注入业务角色（协作层）；任务正文（含派发时开发要求快照）来自 `agent_tasks.content` 存储值 |
| 派发时快照 | `bridges/talk_task_tools.py:478-513` | `delegate_task` 派发前读取项目最新开发要求并拼入存储正文；模式字段当前不参与派发路径 |
| 前端主控面板 | `web/index.html:256-275`、`web/workspace.js:727-1088` | C1b-S2 完整指定/解除 UI：CAS + saveToken + 请求序号 + 上下文绑定 + 焦点记忆 + 安全整数检查（`controllerVersionSafe`，`workspace.js:759`）+ 409/400 只重读不自动重写 + 旧服务/失效指定降级文案 |
| 前端项目设置页结构 | `web/index.html:238-255`、`workspace.js:618-676`、`workspace.js:779-793` | "项目设置"是角色列表固定首项，与具体角色详情互斥；项目级面板可见性统一由 `renderTaskDetailsPanel` 同步 |
| 前端无模式 UI | `web/` 无 `controller_mode`；`tests/workspace_controller_ui.test.cjs:528` | 现有契约测试显式断言主控代码块不写 `project.controller_mode`；C2 开关是全新 UI |
| "参与任务"双横线 | `web/workspace.css:76` + `web/workspace.css:61` | 容器 `#role-details-tasks-panel` border-top 与内部 `.role-task-section` border-top 叠加出双线（#153 确认结构成立，本片不改 CSS） |

## 2. 项目设置页主被动开关（交互合同，沿用 v1 已通过部分）

### 2.1 位置与形态

- 位置：角色页 → 列表首项"项目设置" → 右侧项目级面板区，新增**"调度模式"面板**，排在"项目开发要求"与"项目主控"面板**之后**。与开发要求、主控面板同级互斥于具体角色详情。
- 形态：单选两态（被动 / 主动）或等价开关 + "保存"按钮。**默认显示被动**。不用滑块自动提交，必须显式保存（与主控指定同一交互纪律）。

### 2.2 最小文案（中文，界面用）

- 标题：调度模式；副标：`项目级 · 仅保存设置意向`。
- 被动说明：派发任务后本轮结束，由你通知完成后再读取与收取。当前所有项目默认此模式。
- 主动说明：主控会话在等待期间继续取件、交独立复核并收尾。**保存"主动"只是设置意向，不等于已生效**：没有任何会话因此被唤醒或自动运行；已结束的桌面对话仍需人工唤回。
- 当前状态行（分两行，刻意分开显示）：
  - `已保存设置：被动 / 主动`（仅模式名，内部版本保护保留）
  - `实际执行：尚无生效的主动调度（本版本不支持自动生效）` —— 不得把 `effective_mode=null` 显示成"主动已启用"。
- 前置提示：无主控、或主控指定当前不可用（not_in_roster / member_disabled / member_missing / not_agent / unknown）时，仍可保存模式意向，但显示明确提示：`已保存"主动"，但当前主控指定不可用：<原因>，不会因此产生任何主动调度。`

### 2.3 读写与降级规则（复用 C1a CAS，不新增第二套模式字段）

| 场景 | 行为 |
|---|---|
| 加载 | `GET /api/projects/{id}` 读 `controller_mode` / `controller_mode_version`；加载中禁用控件并显示"读取中…" |
| 权限 | human 可切换并保存；agent 账号只读（控件禁用 + 提示"由项目负责人管理"） |
| 保存 | 只走 `PATCH /api/projects/{id}/controller-mode`，`expected_version` 原样回传上次读取的版本，不自己 +1，不用普通项目 PATCH 旁路 |
| 保存核实 | 必须核实响应同项目、字段存在且 `controller_mode` 与提交值一致，否则报"服务未确认本次保存" |
| 旧服务 | 响应缺 `controller_mode` 字段或接口 404：明确"当前服务不支持调度模式设置"，禁用保存，不把缺失当成 passive |
| 409 陈旧版本 | 只重新 GET 取最新版本与模式，不自动替用户重写；提示"设置已被他人修改，已刷新到最新状态，请确认后再保存" |
| 400/422/其他失败 | 显示服务端 detail，当前面板会话保留选择可重试；离页时未保存选择仍丢弃 |
| 离开/返回模式面板 | 任务/群聊/具体角色/关黑板等离开边界丢弃模式未保存selection，返回按确认saved；同页重绘保留，不自动PATCH/确认、不清其它草稿；保存在途真实结果照常核实 |
| 项目/账号切换 | 面板状态绑定 项目+账号+请求序号；切换后迟到响应不得回填；保存中用 saveToken（复用 C1b-S2 的所有权模式，`workspace.js:1003-1072`） |
| 安全整数 | 版本非 `Number.isSafeInteger` 或 <0 时禁止写入并提示（对齐 `workspace.js:759`）；版本接近 2^63-1 的耗尽场景前端如实提示，后端耗尽保护缺口见 §6 C2-A2（低风险可选加固） |
| 与主控面板关系 | 两块面板独立读写、各自 CAS 字段；解除/更换主控不自动改模式，切模式不自动改主控；文案互相指引 |

## 3. 按场景的调度行为（沿用 v1 已通过部分）

| 场景 | 行为 | 依据 |
|---|---|---|
| 被动（默认） | 派发后本轮结束；执行完成由人通知，请求者在原会话 `talk_get_delivery` → `talk_collect_result`；不以持续短轮询替代 | #151 已验收路径；DEVELOPMENT_ROADMAP "项目级默认被动" |
| 主动 + 主控会话活着 + 已获本次业务授权 | 主控在已获授权范围内继续：等待在途任务 → 读取交付 → 派发独立复核任务给另一执行者 → 收取复核 → 裁决收尾；每一步仍走既有工具与权限，active 不新增任何派发权限 | 权限仍在服务端；MCP 九个工具不变 |
| 主动 + 主控会话已结束 | 不发生任何自动行为；需人工唤回外部原生桌面对话；切换按钮不负责唤醒 | DSH_DESKTOP_TALK_MCP §5.4；不引入 ACK/租约/自动唤醒 |
| 主动 + 无主控或主控失效 | 不产生主动调度；UI 与 MCP 只读输出如实提示；保存的设置意向保持 | `resolve_controller_assignment_status` 如实报失效原因 |
| 模式主动转被动 | 正在等待的受控消费者在下一检查节点退出（如实返回原因），不取消在途任务、不重复收取；之后一切按被动 | 见 §4、§5 |
| 执行 Agent 侧 | 模式对执行者完全不可见也不可依赖：不因模式变化被取消、不自行立项、不扩展第 2 轮 | 现有 claim/lease 与任务协议不变 |

红线（本片不变项）：角色职责、长期唯一主控、业务授权沿用现合同；`active` 不是新的派发权限来源；执行 Agent 不得因看到 active 而自行创建任务。

## 4. 执行合同：谁读模式、在哪检查、如何停止

当前没有任何实际程序读取模式做执行决策：`effective_mode` 恒为 `null` / `not_bound`，无赋值点（#153 全仓确认）。消费节点按下表设计，**每条标注强制级别**，不混用"约定"与"代码强制"：

| 消费者 | 强制级别 | 读取方式 | 检查节点 |
|---|---|---|---|
| 主控发起会话（Codex 桌面 / DeepSeek 桌面 / Kimi Code 的 MCP 会话） | **约定级**：提示词/宿主约定，无代码强制、不可自动验证；MCP 返回配置不等于宿主遵守 | `talk_list_agents`（C2-A1 起新增 `caller_identity` 字段，与模式/指定同响应返回，见 §6） | 每次**开始一段主动推进前**：核对 ①`caller_identity.member_id` == `controller_assignment.member_id` ②`controller_assignment.status` == assigned ③`controller_mode.requested_mode` == active ④记录 requested_version 供后续比对。任一不满足 → 按被动收尾并如实告知用户 下一动作前均重新调用talk_list_agents核对caller_identity.kind=agent、身份与指定一致、assigned、active及最新两版本；matched只表示任务状态，不能作为资格凭证。 |
| 主动等待消费者（`talk_wait_tasks`） | **代码级**（C2-A1 落地后，模拟时钟单测可验证）：桥内受控门禁 + 低频重读 + 显式退出 | 受控模式下由工具自身发 `GET /api/members/me`（入口一次）与 `GET /api/projects/{id}`（入口一次 + 每 30 秒重读），全部计入 query_stats | 进入等待前一次门禁 + 每个重读节点一次比对；模式转被动/版本变化 → `mode_changed` 退出；主控更换/解除/失效/版本变化 → `controller_changed` 退出；不等满超时、不消费剩余预算。完整合同见 §5 |
| 执行 bridge（cli/kimi/codex bridge） | 代码级现状（不读模式） | 无 | 无检查节点；在途任务不因模式切换被取消或重复收取（收取仍仅原请求者） |
| Web UI | 展示层 | 项目 GET | 不承担执行语义 |

停止语义（主动→被动 / 主控更换 / 主控解除）：

1. 没有任何后台调度循环存在，所以"停止继续调度"= 受控等待消费者按上表退出 + 主控会话后续动作按最新读取结果走被动。无需也不引入取消广播。
2. 已派发、在途、已提交未收取的任务保持原状；模式切换不触碰任务状态。被动切换不取消在途任务、不重复收取。
3. 主控更换/解除后，新主控会话开始主动推进前同样按上表核对；旧主控会话下一次读取即自然失效。

明确边界：不引入 ACK、租约、自动唤醒或模型常驻新框架；已结束的外部原生桌面对话只能由用户重新打开/通知（人工唤回），模式开关永远不做这件事。

## 5. 受控等待合同（C2-A1 可直接按表编码）

### 5.0 现状硬约束

- MCP stdio 通道顺序处理：一次 `talk_wait_tasks` 阻塞期间，同一连接的其它工具调用全部排队（`talk_send_mcp.py:125-191`）。
- `wait_tasks` 同步阻塞轮询，客户端取消不终止程序侧等待（无检测源，见 §5.4-B）；Windows 下客户端退出不保证带走子进程。
- 桌面客户端单工具预算 65 秒（配置事实，§1）< 通用等待默认/最长 600 秒；任何超过"65 − 余量"的等待都会被客户端提前掐断，但程序侧继续跑到截止。
- 单次 HTTP 请求写死 10 秒超时（§1），预算合同必须把它纳入记账（§5.3）。

### 5.1 启用边界（唯一选择，不留互斥方案）

**选择：显式选择受控等待，默认关闭。** `talk_wait_tasks` 新增一个可选布尔参数 `controlled_wait`（默认 `false`；非布尔值直接报错）。受控语义**仅在** `controlled_wait=true` 且下列进入门禁全部通过时启用；`controlled_wait` 省略或为 `false` 的一切调用与当前行为逐字节一致——没有身份 GET、没有项目重读、返回结构无新字段、`return_reason` 集合不变、默认/最大 600 秒与 clamp 行为不变。

进入门禁（`controlled_wait=true` 时，按序检查，任一不过**报错、不执行任何等待**，绝不静默降级为普通等待——否则主控会误以为自己在受控状态）：

| # | 条件 | 不满足时 |
|---|---|---|
| G1 | `project_id` 可解析（参数或 `TALK_PROJECT_ID`） | 报错：受控等待必须有项目上下文 |
| G2 | timeout_seconds必须显式传入且requested > 0，为有限正数；bool、非数值、NaN、inf、0与负值一律拒绝 | 报错，不采用600秒默认；非受控路径的既有clamp与非法值语义保持 |
| G3 | `GET /api/members/me` 成功，取得 `id` 与 `kind` | 报错（身份获取失败，安全方向=拒绝） |
| G4 | `kind == "agent"` | 报错：human 凭据不能驱动受控主动等待 |
| G5 | `GET /api/projects/{id}` 成功且含模式/指定字段（非旧服务） | 报错：当前服务不支持受控等待（不猜 passive/active） |
| G6 | `controller_assignment.status == "assigned"` | 报错并回显实际 status（unassigned / not_in_roster / member_disabled / member_missing / not_agent / unknown） |
| G7 | 身份 `id` == `controller_assignment.member_id` 且 `requested_mode == "active"` | 报错：调用者不是当前指定主控，或项目模式意向不是主动 |

门禁全过后记录**进入快照** `{requested_mode, requested_version, member_id, assignment_version, status}`，随后进入轮询循环。返回结构在现有字段上**新增且仅新增**三个字段（仅受控路径）：`controlled_wait: true`、`controlled_entry: <快照>`、`controlled_rechecks: <重读次数>`；非受控路径返回结构逐字段不变。

**兼容测试矩阵**（C2-A1 验收必须逐行覆盖；失败策略只有两类：进入期=**报错**，运行期=**显式原因正常退出**，不存在第三种"降级"）：

| 场景 | controlled_wait | 行为 | 失败类别 |
|---|---|---|---|
| 一切现有调用（含被动项目桌面受控单任务显式等待） | 省略/false | 与现状逐字节一致；回归测试断言零新增 HTTP、返回无新字段、return_reason 仅 matched/timeout/api_error | — |
| 非项目路径 | true | G1 报错，不等待 | 进入报错 |
| 旧服务（项目响应缺字段） | true | G5 报错，不等待 | 进入报错 |
| 身份 GET 失败 / 非 agent 身份 / human 凭据 | true | G3/G4 报错，不等待 | 进入报错 |
| 身份 ≠ 指定主控（含"桌面会话实为 human:bobo 凭据"情形） | true | G7 报错，不等待 | 进入报错 |
| status ≠ assigned | true | G6 报错并回显实际 status | 进入报错 |
| requested_mode = passive | true | G7 报错 | 进入报错 |
| timeout_seconds 省略 / 非法 | true | G2 报错 | 进入报错 |
| 门禁全过，任务命中 | true | `matched` 提前返回（命中优先于重读退出） | — |
| 门禁全过，预算耗尽 | true | `timeout`（timed_out=true） | — |
| 运行中模式转被动 / requested_version 变化 / 模式字段消失 | true | 下一重读节点 `mode_changed` 正常退出（timed_out=false，tasks 为本轮轮询集合） | 运行退出 |
| 运行中主控更换 / 解除 / status 失效 / assignment_version 变化 / 指定字段消失 | true | 下一重读节点 `controller_changed` 正常退出 | 运行退出 |
| 运行中项目重读或任务轮询 API 错误 | true | 沿用现有 `api_error` 显式抛错（不吞成超时） | 运行报错 |

### 5.2 可靠身份（P2）

- **唯一身份来源：`GET /api/members/me`**，服务端按 API Key 反查（`server/routes/members.py:103-106`），取 `id` 与 `kind`。**不得**使用 `TALK_MEMBER_ID`、模型名、业务角色标签或会话标题自证；现有 `_member_id()`（环境变量优先，`talk_task_tools.py:202-207`）**不得**复用于本门禁，C2-A1 新增专用辅助函数（如 `_caller_identity()`），每次受控调用恰好发一次身份 GET，结果计入 query_stats。

caller_identity固定为项目路径的三键对象：成功时{member_id:由members/me返回的id, kind:由其返回的kind, note:null}；获取失败或响应缺合法id/kind时{member_id:null, kind:null, note:简短中文原因}，note不含密钥或完整异常正文，不阻断原清单。非项目路径显式返回caller_identity:null，不额外请求members/me。true受控门禁仍必须核实真实服务端身份，不能用此null值猜测身份。
- **门禁性质：advisory**。它是桥内的自我保护与如实退出机制，**不是权限边界、不替换服务端任务权限**；派发/收取/澄清等权限仍由服务端既有规则裁决。`assigned` 只表示"指定在读取瞬间配置有效"，不代表在线、不代表已获某次任务授权；门禁通过也不等于会话活着。
- 身份相关失败的安全行为（全部=拒绝，不等待、不猜测）：身份 GET 失败 → 报错；`kind != agent` → 报错；身份 ≠ `controller_member_id` → 报错。绝不把 `assigned` 当成"在线/已授权"，也绝不因身份不明而放行。
- **当前入口身份不匹配事实（如实覆盖）**：主控工具返回 #152/#153 `task_ref.created_by=human:bobo`，而长期指定为 `agent:codex`。本方案不作两种猜测——不把当前 Codex 桌面请求者当成 `agent:codex`，也不把 human 凭据当作 agent 自证；也不通过改凭据、改主控指定或改权限来掩盖。直接推论：若当前桌面会话实际使用 human 凭据，G4 会拒绝受控等待，该会话一切行为保持现状被动语义（安全方向）；**本方案不宣称 Codex 主动受控入口已通过**。现有人工/通用任务流程（human 建任务、通用 wait、被动收取）完全保留、不受影响。
- 最小后续核验建议（不在本片实施）：C2-A1 落地 `caller_identity` 后，在 Codex 桌面会话调用一次 `talk_list_agents` 读取 `caller_identity.member_id` 并如实记录；若确认为 human 凭据，由 human 决策是否调整桌面接入的成员凭据（决策项，属 C2-C 前置，不在 C2-A1/B 范围内擅自变更）。

### 5.3 预算与退出合同（数值与枚举本版定死，实现片照表编码）

**新增常量（值已定）**：

| 常量 | 值 | 含义 |
|---|---|---|
| `CONTROLLED_WAIT_RECHECK_INTERVAL_SECONDS` | `30.0` | 受控等待期间项目模式/指定的低频重读间隔（距上次项目读取 ≥30 秒时在下一循环节点重读一次；60 秒预算内约 1–2 次） |
| `WAIT_CLIENT_MARGIN_SECONDS` | `5.0` | 客户端单工具预算的最低参考余量（网络 + 序列化 + 客户端处理）；按终端选择更大的余量，DeepSeek桌面当前50秒/65秒留15秒 |

**预算规则**：

1. **单次预算（程序强制）**：受控等待的 `deadline = 开始时刻 + effective_timeout`，`effective_timeout = min(requested, 600)`（>600 沿用现有 clamp 并照常标注 requested/effective；这与旧契约一致）。`timeout_seconds` 必须显式传入（G2）。客户端余量至少参考5秒，桌面65秒下原≤60秒为参考边界；2026-10-06按用户讨论确定调用策略为50秒，留15秒返回余量，Codex保持用户现用300秒。其它终端先核验实际工具超时；预算匹配由调用方/适配配置/提示词保证——**工具无法读取宿主客户端预算，工具侧唯一的强制上限是600秒clamp**。本次写入适配要求，未新增按宿主自动限长功能，也未改真实客户端配置；C2-C须把显式预算带入实际消费者。
2. **deadline 记账覆盖一切**：进入期身份 GET、进入期项目 GET、每轮任务轮询 HTTP、每次项目重读 HTTP、每次 sleep，全部计入同一个 deadline。发任何 HTTP 前计算 `remaining = deadline − now`：`remaining ≤ 0` → 不再发请求，直接按 `timeout` 退出；否则该请求的超时取 `min(10.0, remaining)`（C2-A1 给 `_api_request` 加可选超时参数，默认 10.0，旧调用行为不变）。sleep 沿用现有按剩余 deadline 截断（`talk_task_tools.py:1017`）。请求被剩余预算掐断时按 `api_error` 显式报错（信息含已等待时长与轮次），**不伪装成正常 timeout**。 连接阶段与响应头/响应体读取阶段的超时，至少在受控路径都必须归一为TalkToolError/api_error，不能让裸TimeoutError或网络OSError逃出工具层；其它网络错误不能一概误标为超时。实现须有连接与响应阶段的注入异常单测，并保持旧通用调用错误分类兼容。socket单请求timeout不等于任意慢速响应的端到端硬截止，未具备中断机制时如实声明该边界。
3. **总预算归属（不夸大）**：工具只强制"程序单次等待"的 deadline。"主控一段推进"的总预算（建议值：连续受控等待 ≤5 次 或 累计等待 ≤10 分钟，超出即按"派发后结束、等人通知"被动收尾）由**主控会话按提示词自我管理**，属于约定级，本片**没有**任何代码强制执行它，也没有持久化计数器；不得写"总预算已被强制执行"。
4. **600 秒项目目标不改**：通用 wait 默认/最大 600 秒与现有返回契约保持；受控短预算是新入口的明确限定，不重设通用默认。
5. **预算事实定性**：65 秒 = 桌面模板/本机已配置的上限（配置事实）；660 秒（Codex 侧）仅既有文档/模板依据，未读取运行宿主配置，不得写"当前已核验可用"；pwsh 0xC0000142 只保留观察记录，不作前置条件。

**`return_reason` 完整枚举（本版定死）**：

| 值 | 路径 | 语义 |
|---|---|---|
| `matched` | 通用 + 受控 | 命中目标协作状态（现状不变） |
| `timeout` | 通用 + 受控 | 预算耗尽（timed_out=true；受控路径含"剩余预算不足不再发请求"情形） |
| `api_error` | 通用 + 受控 | TALK API 错误（含被剩余预算掐断的请求超时），显式抛错，不吞成超时（现状不变） |
| `mode_changed` | 仅受控 | 重读节点发现：requested_mode ≠ active、requested_version 与进入快照不一致、或模式字段缺失/不支持（三项中先命中的模式类条件） |
| `controller_changed` | 仅受控 | 重读节点发现：指定成员更换/解除、assignment_version 与进入快照不一致、status ≠ assigned、或指定字段缺失/不支持 |

受控路径deadline已耗尽、尚未发出下一请求时，返回上一轮已成功轮询的任务集合；若从未完成任务轮询，tasks=[]、task_count=0。remaining<=0时不再发HTTP请求；请求已经发出后的网络超时保持api_error，不伪装正常timeout。

不新增 `cancelled` 原因（见 §5.4-B）。检查顺序固定：每轮先查任务命中（matched 优先），再按 30 秒节奏查模式（先）与指定（后），再查 deadline，最后 sleep——同一轮里"任务命中"与"模式变更"同时发生时返回 `matched`，如实且确定。

**状态转移**：

```text
[调用] controlled_wait=false → 旧状态机（matched/timeout/api_error），本版不变
[调用] controlled_wait=true
  → G1–G7 任一失败：[进入报错]（不轮询、不等待）
  → 门禁全过：[受控等待]（记录进入快照）
      ├─ 任务命中 → [返回 matched]
      ├─ 重读节点模式条件失败 → [返回 mode_changed, timed_out=false]
      ├─ 重读节点指定条件失败 → [返回 controller_changed, timed_out=false]
      ├─ deadline 耗尽 / 剩余预算不足发请求 → [返回 timeout, timed_out=true]
      └─ 任何 API 错误 → [抛错 api_error]
```

### 5.4 两类"中途停止"分开表述（P3）

**A. 模式或主控变更（本片覆盖）**：只有"实际模式/指定变化"才在 §5.3 的重读检查节点退出（`mode_changed` / `controller_changed`）。被动切换不取消在途任务、不重复收取；退出后主控会话按最新读取结果走被动。

**B. 客户端 notifications/cancelled（本片不覆盖，如实声明）**：现同步 stdio 主循环在 `dispatch_tool` 执行期间完全不读 stdin，无 signal/select/工作线程（#153 全仓确认），**不存在可检测的客户端取消来源**，取消消息在 dispatch 阻塞时读不到。本片**不增加真正监听**，因此：不写"客户端取消会被下一节点感知"，不新增 `cancelled` 返回原因；若没有任何模式/指定变化，客户端取消后程序仍可能继续跑到任务命中或预算截止。工具描述与指南保持并强化这句实话。真正的取消支持如需推进，登记为独立后续片 **C2-D**（见 §6），不混入本片"已覆盖"。

### 5.5 排队、错误呈现、能力边界与降级（沿用 v1，措辞收紧）

- 等待占用通道期间其它工具调用排队是机制事实；超时返回结构（`timed_out=true`）与 API 错误（显式抛错）继续分开，不把错误吞成超时。
- 等待中的会话不能同连接并行派发/取消/收取其它任务；需要这些动作就结束等待或另开会话。写进 UI 提示与提示词。
- 降级方式：任何一步不满足（预算不够、模式/主控失效、总预算耗尽、API 错误）→ 退出等待，按被动流程收尾并如实告知用户；降级不是失败，是默认路径。
- 桌面入口默认被动；受控主动等待只在预算满足的入口可用，且入口可用性以 §5.3-5 的来源定性为准，不预设"Codex 侧已核验可用"。

## 6. 依赖有序的实施切片

如实界定：**现合同没有主动调度的执行入口**（effective 恒 null），"配置 UI"与"执行配套"分片推进；在 C2-A/C 完成前，前端开关保存的永远只是设置意向，UI 文案必须保持 §2.2 的分离显示，不伪造生效状态。

| 片 | 内容 | 执行 / 独立复核 | 具体路径 | 改动 / 不变项 | 验收标准 | 必要测试 | 部署 / 重载 | 人工验收节点 |
|---|---|---|---|---|---|---|---|---|
| **C2-A1（第一可开发片）** | 受控等待消费者合同 + 可靠身份：`wait_tasks` 新增 `controlled_wait` 参数、G1–G7 进入门禁、30 秒重读与 `mode_changed`/`controller_changed` 退出、deadline 全记账（含 `_api_request` 可选超时）、`caller_identity` 加入 `list_agents`、计数与工具描述如实更新 | DeepSeek 开发 / Kimi 复核 | `bridges/talk_task_tools.py`（新常量、`_caller_identity()`、`_api_request` 可选 timeout、wait_tasks 受控分支、list_agents caller_identity、TOOL_SCHEMAS 两个工具描述、WAIT_COUNTING_NOTE）；`bridges/talk_send_mcp.py` 无需改（dispatch 在 talk_task_tools.py 内）；`tests/test_talk_task_tools.py` 及新增受控测试；`docs/guides/DSH_DESKTOP_TALK_MCP.md` 第 5.4 节后续由 Codex 同步 | 改：上列文件。不改：九个工具集合数量、被动默认、任务状态语义、通用 wait 默认/最大 600 秒与旧返回契约、桌面 patch 配置、服务端 API（身份/项目 GET 均为既有端点）、权限 | §5.1 兼容矩阵逐行通过；§5.3 常量/枚举/记账逐项落实；被动项目普通显式等待回归通过；非受控返回结构零新字段；受控新 GET（身份+项目+重读）全部计入 query_stats.http_requests；list_agents 描述披露 caller_identity 新增一次身份 GET；取消未响应等五件事写进工具描述 | 模拟时钟单测（沿用 `_monotonic`/`_sleep` 间接层）：门禁各失败分支、受控 matched/timeout、30 秒重读节奏与两类 changed 退出、per-request 超时 clamp、query_stats 计数断言、既有 wait 全量回归、list_agents caller_identity（含身份 GET 失败降级为 null+note、不阻断清单） | MCP 进程重载；桌面需重连刷新工具描述 | Codex 核对后由用户确认"桌面入口默认被动、受控等待仅预算满足入口可用、Codex 侧 660 秒未实测"的说明 |
| **C2-A2（可选加固，不阻塞 A1/B）** | controller-mode 版本耗尽保护补齐（对齐 assignment 的 `version < SQLITE_SIGNED_INTEGER_MAX` 条件与 exhausted 409 分支，约 3 行） | DeepSeek 开发 / Kimi 复核 | `server/routes/projects.py:528-558`、`tests/test_project_controller_mode.py` | 改：CAS 条件加耗尽保护。不改：字段、请求/响应 schema、语义 | 版本 = 2^63-1 时变更请求得到可控 409 而非静默退化锁死 | 边界单测 + 既有 C1a 测试回归 | 服务重启加载新代码 | 无需用户页面验收（无 UI）。定性：低风险可选（自然变更不可现实达到 MAX），保留登记即可，不作为开关主流程前置，不合并额外整改 |
| **C2-B（前端）** | 项目设置页"调度模式"开关（§2 全部交互/降级规则）+ 角色详情"参与任务"上方双横线只留一条（见 §7） | Kimi 开发 / DeepSeek 复核 | `web/index.html`、`web/workspace.js`、`web/workspace.css`、`tests/workspace_controller_ui.test.cjs` 及相关 Node/页面契约测试、静态资源版本四处一致 | 改：上述文件。不改：后端 API、主控面板逻辑、开发要求编辑区、任务页 | §2.2 文案区分已保存/实际执行；§2.3 全部降级与保护场景；effective=null 不显示为已启用；双横线只剩一条 | Node 页面契约 + Python `test_task_web_ui` / `test_controller_web_ui` 扩展；资源版本断言 | 仅静态资源版本号，无需服务重启 | 用户页面验收：开关各状态、agent 只读、409 演示、双横线视觉 |
| **C2-C（后续片，本版给出可实现最小路径，不再只写"待定"）** | 主控会话主动推进约定 + 真实主动链路验收。提示词由 Kimi 起草；链路验收由 Codex 组织 | Kimi（提示词）/ DeepSeek 复核提示词；真实链路验收另派并由用户人工验收 | 提示词落点：§8 主动版补充段（桌面侧人工粘贴，DSH_DESKTOP_TALK_MCP 由 Codex 同步）；代码前置：C2-A1 的 `caller_identity` 与受控 wait | 改：提示词与指南文档。不改：不引入 ACK/租约/自动唤醒；`effective_mode` 保持 null 事实 | 见下方"C2-C 最小路径与验收" | 提示词文本评审；真实链路证据（见下） | 桌面重连刷新工具描述后人工粘贴提示词 | 真实主控链路人工验收（参照 DEVELOPMENT_ROADMAP 最小验收）：桌面会话实际跑一条"受控等待 → 取件 → 派复核 → 收复核 → 收尾"链路，记录 return_reason、重读计数、退出行为与 caller_identity 实测值 |
| **C2-D（登记，未来可选，不属于本方案已覆盖范围）** | 真正的客户端取消支持：stdin 监听线程仅解析 `notifications/cancelled` 置事件标志，wait 轮询每轮检查；届时才新增 `cancelled` 返回原因 | 另派 | `bridges/talk_send_mcp.py`、`bridges/talk_task_tools.py` | — | 取消后等待在下一循环节点退出 | 模拟时钟单测 + 真实桌面取消人工验证；需评估 Windows 子进程生命周期与同连接顺序语义 | — | — |

**C2-C 最小路径（谁读、何时读、身份自证、允许节点、退出收尾、落点、三类边界）**：

1. **谁读/何时读**：主控会话（当前即 Codex 桌面 MCP 会话）每次**开始一段主动推进前**调用 `talk_list_agents`，同一次响应读取 `caller_identity`、`controller_mode`、`controller_assignment`。
2. **身份自证**：核对 `caller_identity.member_id == controller_assignment.member_id` 且 `caller_identity.kind == "agent"`（服务端按 Key 反查，非自报）。当前入口存在 `created_by=human:bobo` 与指定 `agent:codex` 的不匹配事实：若实测 `caller_identity` 为 human，则该会话**不是**受控主动入口，按被动收尾并报告用户，由 human 决策是否调整接入凭据——本方案不替其做决定、不改凭据。
3. **允许的推进节点（全部走既有九个工具与既有权限，active 不新增权限）**：`talk_wait_tasks(controlled_wait=true, timeout_seconds=显式预算)` 等在途任务 → `talk_get_delivery` 读交付 → `talk_delegate_task` 派独立复核给另一执行者 → 受控等待复核 → `talk_collect_result` 收取 → 裁决收尾并向用户汇报。 每次新动作（包括派复核、收取与最终汇报）前均重新读取talk_list_agents，检查可靠身份/kind、最新模式与指定/两版本；不满足即结束主动推进，按被动向用户说明当前状态，已经在途的任务保持。matched只表示任务命中，不能跳过检查。读取到实际动作间仍有竞态，此处仅约定级防护，不是代码强制互斥。
4. **退出/失败如何收尾**：受控等待以 `mode_changed`/`controller_changed`/`timeout` 退出 → 停止继续推进，按被动告知用户"已结束本轮，完成后请通知我取件"；`api_error` → 如实报错，不自动重试超过 1 次；段总预算（约定级，§5.3-3）耗尽 → 被动收尾。
5. **三类边界（如实区分）**：①**现有 repo 代码可落实**（C2-A1）：受控门禁、预算/退出、caller_identity、计数与描述；②**原生桌面人工提示/遵守**：主控会话"开始推进前先读清单、逐步不越授权"靠提示词，MCP 配置返回与提示词约定都不是代码强制，外部宿主不会自动遵守；③**尚无自动验证**：桌面宿主是否遵守提示词、模型是否不越权，只能靠真实链路人工验收，不伪造自动生效。
6. **验收证据**：桌面会话实际链路记录（各工具调用、return_reason、controlled_rechecks、caller_identity 实测值、退出/收尾文案），由用户人工确认；在 C2-C 落地前，UI 与提示词一律保持"尚无生效的主动调度"。

说明：C2-A1 先于 C2-B，因为 UI 开关保存 active 而没有任何消费者合同，只会制造"看起来像生效"的假状态；即使 A1 完成，主动模式仍要求主控会话活着且已获授权，UI 的"实际执行"行在 C2-C 落地前仍保持"尚无生效的主动调度"。

## 7. 双横线修复归属（并入 C2-B，本片不改 CSS）

- 事实：`#role-details-tasks-panel`（`workspace.css:76`）自身 `border-top` + 内部 `.role-task-section`（`workspace.css:61`）又一条 `border-top`，"参与任务"标题上方出现两条横线（#153 确认结构成立）。
- 范围：C2-B 中删除其中一条（建议移除 `.role-task-section` 的 `border-top`/`margin-top`，保留面板级分隔线），**仅留一条**，同步页面契约测试与 design-qa 记录。本修订片不改 CSS。
- 验收：角色详情"参与任务"上方只有一条分隔线；窄屏与桌面 80% 密度下一致；项目设置页/任务页布局不回归。

## 8. 桌面连接提示词

### 8.1 DeepSeek 桌面连接提示词（现行被动版，沿用 v1 已通过合同，可复制）

```text
你已在本桌面端配置好 TALK MCP（服务器名 talk，工具前缀 mcp__talk__*）。这只是连接工具：它让你能调用 TALK 的任务接口，不代表任何权限或职责变化。

本项目 project_id=prj_e8fe7066bbec。当前长期项目主控是 agent:codex（由项目负责人在角色页指定，长期保存，直到人工解除或更换）。不要尝试更改主控指定、调度模式或任何项目配置。

开始前先调用 mcp__talk__talk_list_agents（project_id=prj_e8fe7066bbec），读取角色清单、项目开发要求、controller_mode 与 controller_assignment：
- controller_mode.requested_mode 是项目保存的模式意向；effective_mode 为 null 表示当前没有任何主动调度生效，即使 requested_mode 是 active 也一样。
- controller_assignment.status=assigned 只表示职责配置有效，不代表在线、已确认或已授权。

默认按被动协作：只执行我在本对话中明确交办的这一次任务。派发用 mcp__talk__talk_delegate_task，派发后结束本轮，不要调用 talk_wait_tasks 做长等待（当前客户端单工具预算不支持，且会阻塞同一连接上的其它查询）。完成后我会通知你，届时再用 mcp__talk__talk_get_delivery 读取交付摘要、用 mcp__talk__talk_collect_result 收取结果。

本次授权仅限我明确交办的这一个任务，不构成对其它任务的授权，也不改变任何成员的职责、权限或主控指定。
```

### 8.2 主动版补充段（C2-C 材料；仅在模式已保存 active、主控指定有效、且 C2-A1 已落地后使用；当前项目为被动，现在不用）

```text
本项目已保存"主动"调度模式意向。你只有在同时满足下列条件时才按主动推进，任一不满足立即回到被动（派发后结束、等我通知再取件），并如实告诉我哪一条不满足：
1) 调用 mcp__talk__talk_list_agents，确认 caller_identity.member_id 与 controller_assignment.member_id 完全一致、caller_identity.kind 为 agent、controller_assignment.status 为 assigned、controller_mode.requested_mode 为 active；记录 requested_version。 这不是只在整段开始检查一次：每次派复核、收取和汇报前都重新读取并核对最新两版本。matched不代表仍具备active资格；检查不满足就结束主动推进，按被动说明待办，不取消在途任务。
2) 等待只调用 mcp__talk__talk_wait_tasks 且必须显式传 controlled_wait=true 与 timeout_seconds（不超过我的单工具预算减 5 秒；桌面 65 秒预算时不超过 60）。若该调用报错（门禁拒绝），不要改参数重试冒充受控等待，直接按被动收尾。
3) 一段主动推进最多连续 5 次受控等待或累计 10 分钟，超出即按被动收尾。
4) 推进动作仅限：受控等待 → talk_get_delivery 读交付 → 派独立复核给另一执行者 → 受控等待复核 → talk_collect_result 收取 → 向我汇报裁决。每一步都是既有权限，模式不给你任何新权限。
5) 受控等待以 mode_changed / controller_changed / timeout 退出时，停止推进并告诉我原因；客户端取消不会立刻终止程序侧等待，取消后它仍可能跑到命中或截止。
6) 不要自行立项、不要取消或重复收取在途任务、不要改主控指定或模式。
```

说明：§8.1 严格区分连接工具 / 有限任务授权 / 长期主控指定；§8.2 是约定级提示词，无代码强制（§6 C2-C 边界②③），桌面宿主是否遵守只能人工验收。

## 9. 未实现 / 未实测范围（如实声明）

- 本片零代码改动；§2–§6 是可实施方案，未实施。C2-A1/A2/B/C/D 均未开始。
- `effective_mode` 恒 null：主动调度目前没有任何执行入口；C2-A/C 完成前 UI 与提示词必须保持"尚无生效的主动调度"表述。
- 原 v1 留白项（单次/总预算决策规则、重读节奏 N、return_reason 枚举）本版已定死（§5.1/§5.3），实现片照表编码；不再有"留实现片定稿"项。
- "主控一段推进总预算"为约定级建议值，无代码强制执行；工具只强制单次 deadline。
- Codex 侧 660 秒预算仅文档/模板依据，未读取运行宿主配置；桌面 65 秒为配置事实，本片不调整它。
- 当前 Codex 桌面请求者身份未核验；`created_by=human:bobo` 与指定 `agent:codex` 的不匹配按 §5.2/§6 处理，本方案不宣称 Codex 主动受控入口已通过，也不改凭据/指定/权限掩盖。
- 客户端取消无检测源：本片不覆盖真正取消（登记 C2-D），不新增 cancelled 原因；同连接排队为机制事实。
- pwsh 0xC0000142 根因未明，仅保留观察；未做 #151 逐请求时序复现。
- 未启停任何进程/服务/bridge，未建真实任务、未做真实等待/模型调用，未操作浏览器；未改 DSH CLI / 桌面配置；未更新正式进度/AGENTS，未 commit/push。

## Codex 定向复核回填与实施门禁（#155 R1–R5）

- R1：C2-A1必须对连接/响应读取阶段超时与网络异常做受控路径的工具错误归一，并测试统计/阶段信息；默认通用行为不退化。正常deadline早退与发出请求后的错误分开。
- R2：true受控路径显式有限正数且严格排除bool/非数/NaN/inf/0/负值；false/缺省保持旧语义。输入矩阵必须写入回归。
- R3：caller_identity成功/失败均三键，非项目null且不额外请求身份；身份不来自环境或会话标签。当前human:bobo请求者不能冒充agent:codex，支持边界保留，不自动改凭据/指定。
- R4：matched不是active资格证明；后续每次有新动作前重新核对最新身份/模式/指定和两版本。提示词只能约定级遵守，检查到动作间的竞态仍存在，已结束外部会话仍需人工唤回。
- R5：deadline早退沿用最近成功轮询集合；从未完成轮询返回tasks=[]/task_count=0。门禁失败与进入后正常deadline退出按前述状态表分开。
- 本合同是实施依据；C2-A1提交后必须Kimi独立审查实际代码，再由Codex收尾。C2-B真实页面及C2-C真实链路仍需用户验收，当前不得把保存active或通过设计写成功能生效。
