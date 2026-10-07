# Codex TALK 成员身份切换与回退清单

> 2026-10-07由Codex发布：Kimi #176起草、DeepSeek #177独立复核A–I通过，176/177已收取。原稿与原复核保留；本清单纳入177-N1–N4文字澄清并记录N5复核边界，不改权限或业务实现。
> 176/177准备通过只表示步骤经过独立审查；当时未切Key/改配置/备份/重连/试派。2026-10-07用户已另行明确授权实际执行，最新状态见下节，原准备与复核记录仍按各自阶段理解。
> 下文原记录的“本片/本轮”指#176准备或明确标注的历史证据；最新实际配置进展由下节另行记录，不追改原稿。来源分为【派发包事实】、【源码事实】、【指南事实】、【待核验】，每类均按其日期与范围理解。

## 最新实际执行状态（2026-10-07，Codex当前入口被动闭环验收通过）

- 用户既有“切换到codex吧”授权持续有效。前次只替换`C:/Users/Administrator/.codex/config.toml`的`[mcp_servers.talk.env].TALK_API_KEY`为既有`agent:codex`凭据，完整TOML其它字段保持；未新建/重置成员或Key。
- 完整仓库外备份`C:/Users/Administrator/.codex/backups/talk-identity-20261007T091123256850Z/config.toml`字节核对通过；必要回退恢复完整副本、重连并核human身份。配置实施回执`.tmp/initiator-mode-identity-switch/execution.json`无密钥。
- 前次API/名册/独立`--check`通过，而当时聊天仍human；重开后及本轮当前聊天`talk_list_agents`实测`agent:codex/kind=agent/note=null`，Phase C通过，当前入口已加载本人Key。
- Phase D新任务178目标DeepSeek，实际created_by=agent:codex、项目正确、独立Hall；只读核验经Kimi179独立A-H复核通过、阻塞0。179消息含说明文字及JSON，MCP默认unknown；本地合法179报告与稳定分页完整消息中的JSON一致，按实际独立证据裁决，原报告/消息不追改。
- Codex先179后178收取成功，collected_at分别2026-10-07T09:50:04.854837与09:50:07.538516，均succeeded/completed，原msg2681/2680保持。原报告partial记录的下游步骤已由主控完成，Phase D/E验收收尾通过，范围仅Codex当前入口与被动新任务闭环。
- 验收回执`.tmp/initiator-mode-identity-receipt/acceptance.json`；身份/任务快照、六源指纹与开发复核证据在`.tmp/initiator-mode-identity-verify/`及`.tmp/initiator-mode-identity-review/`。无需重切Key、重复176/177或重启uvicorn。
- 前次human177项/创建164项/在途0/7旧failed及旧human仍可读为历史盘点，本轮未重测。历史created_by与权限保持，Codex本人Key不自动获得human旧任务收取资格。
- 项目passive/version6、effective null/not_bound，assignment仅兼容。660仅前次实读配置；本轮无wait，真实G8/主动消费者/长等待/正常到期/取消/排队/其它终端身份未验收。里程碑收尾后暂停，I-3/I-4按原依赖另片。

## 0. 范围界定（只改一个入口的一个键）

- 本次切换**只改“Codex 桌面 TALK MCP 入口”的 `TALK_API_KEY`**：从当前 `human:bobo` 凭据换成 `agent:codex` 本人既有成员 Key。
- `TALK_API_KEY` 是 **TALK 成员鉴权**凭据：经 `X-API-Key` header 由服务端反查 `members` 表确定身份（【源码事实】`server/auth.py:12-16` 反查、19-38 401/403 出口；`bridges/talk_terminal_mcp.py:87-89` 只从环境变量读取）。它与 **Codex 模型供应商 API Key / 模型登录配置**是两套东西，互不替代，本片不涉及后者。
- 范围外且**不宣称已切换**：其它 MCP 服务、Codex 模型设置、DeepSeek/Kimi 执行入口（bridge `--key` 或启动器密钥文件）。`agent:deepseek` / `agent:kimi` 的自身身份只登记为**后续分别核验**，本清单不覆盖、不声明三方都已完成。
- 用户配置路径（含 Codex 桌面 MCP 配置文件实际位置）只能作为**实施前核验候选**；本片未重读、未生效，一律标【待核验】。

## 1. 176准备阶段事实基线（历史）

- 【派发包事实】当前 TALK 入口 `caller_identity=human:bobo / kind=human`；`requested_mode=passive / version 6`，`effective_mode=null / not_bound`（`.tmp/initiator-mode-identity-prepare-dispatch/dispatch_context.json`；版本为用户页面保存后的新读取，不回写历史 version4 记录）。
- 【已实测（历史证据，本片未重测）】当前 Codex 目录/短只读路径 I-1 加载核验通过：九工具目录、G1–G8 运行时注记一致、human true 按 G4 拒绝（`.tmp/initiator-mode-tools-loadcheck/2026-10-07-loaded.json`，该文件快照 requested_version=4）。真实 Agent G8、主动消费者、长等待/取消排队、其它终端**均未验收**。
- 【已实测（历史证据）】I-1/I-2 本轮用户页面验收通过（`.tmp/initiator-mode-ui-receipt/acceptance.json`；不推断键盘/窄屏/HTTP 并发/故障恢复逐项覆盖）。
- 【源码事实】身份唯一可靠来源是服务端按 Key 反查：`GET /api/members/me`（`server/routes/members.py:103-106`）；终端入口剔除继承的 `TALK_MEMBER_ID`（`bridges/talk_terminal_mcp.py:93-94`），`caller_identity` 不复用环境变量/模型名/标签自证（`bridges/talk_task_tools.py:318-339`、342-360）。
- 【源码事实】任务 `created_by` 创建即固定且不可改：`create_task` 写 `created_by=current.id`（`server/routes/tasks.py:1644-1646`），`AgentTaskCreate` 无 `created_by` 请求字段（`server/models.py:906-1030`），全部任务路由无修改端点。
- 【源码事实】协调资格边界：`collect-result` 仅 `created_by==current.id`（`server/routes/tasks.py:2486-2508`，检查在 2494-2495）；未领取取消仅 `created_by`（2511-2541）；任务可读性=human 或 `created_by`/`target_member_id`（82-85）；领取/完成仅 agent 且 target==self（`_require_agent` 67-72）。

## 2. 176准备阶段实施前检查清单（当时尚待核验；当前进展见顶部）

| 事实 | 当前状态 | 说明 |
|---|---|---|
| Codex 桌面 MCP 配置目标文件/节与键名 | 【待核验】 | 本片未读任何含凭据的用户配置。实施前由用户/管理员在本人环境按可用官方来源核实实际文件、`mcp` 条目结构与 `env` 写法；不凭记忆编造配置键、路径或 UI 按钮。 |
| `TALK_API_KEY` 注入方式 | 【源码事实】 | 终端入口只从环境变量读取，无 `--key` 参数（`bridges/talk_terminal_mcp.py:87-89`；【指南事实】`TERMINAL_MCP.md:14`）。MCP 客户端侧如何把 env 传给 stdio 进程属宿主配置，【待核验】。 |
| `agent:codex` 既有成员 Key 的安全提供 | 【待核验】+边界 | 由管理员（用户）通过安全渠道提供给本机操作使用；**不创建/重置账号或 Key**（注册对已存 agent 同 Key 幂等、异 Key 409：【源码事实】`server/routes/members.py:42-91`），不把密钥发到聊天、不写进命令历史/日志/交付包。 |
| 账号/名册/权限检查 | 【源码事实】+【待核验】 | 需确认：`agent:codex` 成员存在、未禁用（`disabled_at` 为空，否则 403，`server/auth.py:31-36`）、在项目 `prj_e8fe7066bbec` 名册中（`list_agents` 项目路径只列名册内且未禁用 agent：`bridges/talk_task_tools.py:571-593`）。名册当前内容本片未查，标【待核验】；预期已含（当前拓扑见 `MODULE_bridges.md` 固定拓扑表），实施前以服务端实际响应为准。 |
| 配置备份/回退路径 | 本清单第 5 节定义 | 备份=目标配置文件的完整副本，放**仓库外**、不进 Git/日志；回退=恢复副本并按宿主方式重连。 |
| 最小变更面 | 见第 6 节变更表 | 仅目标 MCP 条目的 `TALK_API_KEY` 一个值。 |

## 3. 旧 human 任务衔接表（快照，非切换时事实）

来源：`.tmp/initiator-mode-identity-prepare-dispatch/human_task_inventory.json`（2026-10-07 07:23 UTC，本项目 `talk_list_tasks` 返回集，`project_id=prj_e8fe7066bbec`）。

| 类别 | 数量/编号 | 处置 |
|---|---|---|
| 返回任务总数 | 175 | 快照仅覆盖本次调用返回集与该项目，不是跨项目全面盘点 |
| 其中 human 创建 | 162 | 全部 `created_by=human:bobo` |
| 在途/已提交待收取（queued/running/assigned/in_progress/submitted/待澄清） | **0**（本次快照未发现） | 无需要切换前强行收尾的在途项 |
| 172–175（I-1/I-2 开发与复核） | 均已收取 completed | 见 inventory `sample_completed` |
| 历史 failed 且 `result_collected_at=null` | 7 项：122 / 35 / 31 / 24 / 21 / 14 / 12 | **保持原失败**：不当作在途、不重新开启、不自动收取；只登记继续由 human 管理 |

快照附带 `filters_applied` 免责声明：筛选摘要本身不构成完整性证明（原文 `not a completeness claim`）。表中0仅表示当次返回集经所列筛选未发现，不外推其它项目、其它时间或未经核对的状态；真正切换前应重新读取并检查全部相关状态。

列表 API 覆盖核对（【源码事实】）：`GET /api/tasks` 无分页/limit 参数，human 可见全部、按 `created_at` 倒序返回（`server/routes/tasks.py:1698-1740`）；非 human 只列 `created_by==self 或 target==self`（1710-1711）。因此快照由 human 凭据取得时覆盖本项目全部任务，但**不能把快照当切换时刻的事实**：真正切换前必须用当时 human 凭据刷新清单，并重新确认在途为 0 或先收尾。

## 4. 本任务链的衔接（本 I-0 与随后独立复核不在上述快照中）

- 当前本 I-0 任务及其后 Codex 转交 `agent:deepseek` 的独立复核任务，均 `created_by=human:bobo`，创建于快照之后。**真正切换前**：先刷新清单，由原 human 入口完成本链的收取；切换不得以未完成本链为代价。
- 若届时仍有未能收尾的 human 任务：**保留 human 可恢复管理入口**（Web UI 或 human 凭据终端）。human 身份对自己创建的任务天然可读可收（`server/routes/tasks.py:82-85`、2494-2495）；`agent:codex` 对旧 human 任务无 `created_by` 资格，受控等待 G8 会整批拒绝——这是**预期安全行为，不是缺陷**（【指南事实】合同 §4.3 末行、§5.3 第 5 条）。
- 明确禁止：迁移历史任务 `created_by`、放宽 Agent 对他人任务的收取、或写“以后 Codex 本人 Key 能处理所有 human 旧任务”。

## 5. 已审分阶段步骤（176/177只准备，实际进展见顶部）

**Phase A 准备（已完成）**：176交付本清单、失败矩阵与旧任务衔接表；177独立复核通过，双方已收取。仅准备步骤，未改配置。

**Phase B 用户/管理员实际实施**（需用户确认后执行）：
1. 用 human 凭据刷新任务清单（第 3、4 节），在途先收尾；
2. 核实第 2 节全部【待核验】项（配置目标/键名、Key 安全到位、名册与未禁用）；
3. 备份目标 MCP 配置文件完整副本到仓库外（不进 Git/日志），记录回退路径；
4. 只改目标条目的 `TALK_API_KEY` 为 `agent:codex` 本人 Key；
5. 按宿主方式重连 stdio MCP 入口。**注意层级区分**：重启 uvicorn HTTP 服务与重连 stdio MCP 是不同层，前者不足以刷新 MCP 入口（【指南事实】`TERMINAL_MCP.md:416`；本片期间宿主配置重载方式仍【待核验】）。

**Phase C 只读身份检查**（重连后）：
- `talk_list_agents`（项目路径）实测 `caller_identity.member_id == agent:codex` 且 `kind == agent`；`--check` 可辅助核对入口输出的 `member_id`（`bridges/talk_terminal_mcp.py:151-166`）；完整身份成功判据仍须从服务端反查同时核实 `member_id` 与 `kind`。不以 `TALK_MEMBER_ID`、模型名、会话标签自证。

**Phase D 一项无破坏性新任务核验**（经当时授权后）：
- 按当时 `development_requirements` 选择执行者（注意【源码事实】`server/routes/tasks.py:1103-1108` 请求者≠target、97-101 target 必须是 agent、104-106 项目须存在），创建最小无副作用任务；核对新任务 `created_by == agent:codex`（`AgentTaskOut.created_by`，`server/models.py:1173`）；
- 该任务按自身真实 task_id 交付、独立复核、收取；**本片只设计此步，不实际创建任务**。

**Phase E 成功收尾 / 失败回退**：成功=按第 7 节验收标准记录证据；失败=按第 8 节失败矩阵执行回退，未确认回退完成前不得继续新任务或臆测成功。

**模式边界**：当前项目模式 `passive` 即可完成 Phase C/D 的身份与创建归属核验；切 Key **不自动 active**、不宣称主动消费者已就绪；真正主动链路按 I-3/I-4 另行验收，`effective_mode` 在 I-4 通过前保持 `null/not_bound`。

## 6. 文件/字段变更表（实施时的最小变更）

| 对象 | 改前 | 改后 | 性质 |
|---|---|---|---|
| Codex 桌面 MCP 配置中 TALK 条目的 `env.TALK_API_KEY` | `human:bobo` 的 Key | `agent:codex` 的 Key | 唯一变更；具体文件/节/键名【待核验】 |
| 同条目 `command`/`args`/项目指向 | 不变 | 不变 | — |
| 其它 MCP 服务、Codex 模型设置 | 不变 | 不变 | 范围外 |
| TALK 服务端、数据库、历史任务、项目模式/指定 | 不变 | 不变 | 禁止顺改 |
| DeepSeek/Kimi 入口凭据 | 不变 | 不变 | 后续分别核验 |

## 7. 验收标准（切换成功判据，全部需服务端反查证据）

- A1：`caller_identity.member_id == "agent:codex"` 且 `kind == "agent"`（`talk_list_agents` 项目路径或服务端 `/api/members/me`，同时核实两个字段；`--check`仅作辅助）；
- A2：试派新任务的服务端记录 `created_by == "agent:codex"`；
- A3：项目模式未被本片改动（仍 `passive`），`controller_assignment` 仅兼容回显、不作为资格依据；
- A4：旧 human 任务仍可由 human 入口读取/收取（由 human 侧确认）；
- A5：`effective_mode` 保持 `null / not_bound`，无主动生效宣称。

## 8. 失败矩阵（每行：停止条件 / 回退与复查步骤 / 证据 / 需人处理边界）

| # | 失败情形 | 停止条件 | 回退与复查步骤 | 证据 | 需人处理边界 |
|---|---|---|---|---|---|
| F1 | 配置解析/启动失败（MCP 进程起不来、配置非法） | 工具目录不可用或进程报错即停，不进行任何新任务/核验 | 恢复仓库外备份副本 → 按宿主方式重连 → 用原 human 凭据核 `caller_identity=human:bobo` 恢复 → 抽查一项旧 human 任务可读（`server/routes/tasks.py:82-85`） | 宿主报错原文（不含密钥）、恢复后身份实测 | 配置格式/键名问题由人按宿主官方资料修复，不猜键名、不试写 |
| F2 | 无效 Key（401）/ 错误 kind 或 member | `--check`/`/me` 401（`server/auth.py:26-30`）、403 disabled（31-36）或反查身份≠`agent:codex`/非 agent 即停 | 同 F1 回退并重连；恢复后复查 human 身份与旧任务可处理性 | HTTP 状态、身份响应三键 | Key 发放、成员禁用/名册属管理员操作，不自行注册/重置/解禁 |
| F3 | 无项目权限/名册缺失（`agent:codex` 不在名册或项目不可读） | `talk_list_agents` 项目路径报错或 agents 不含 `agent:codex`（`bridges/talk_task_tools.py:571-593`）即停 | 同 F1 回退；human 侧核名册 sync 与项目存在（`server/routes/tasks.py:104-106`） | 工具返回/错误原文、名册核对记录 | 名册修复由 human 走项目同步流程，本片不提供自动修法 |
| F4 | 身份正确但新任务归属异常（`created_by != agent:codex`） | Phase D 核验发现归属不符即停，不再派后续任务 | 当前agent:codex无权取消created_by不符的任务；若仍queued，只能由服务端实际created_by对应身份取消（`server/routes/tasks.py:2511-2541`）。实际记录者为human时由该human入口操作；无法取得对应身份时保留任务并交人处理，不借任意human身份绕过 → 回退备份并重连 → 复查原human身份 → 如实记录归属异常 | 任务 `AgentTaskOut` 归属字段、取消/回退记录 | 不改数据库、不迁移 `created_by`；归属异常属服务端事实，交人与 Codex 排查 |
| F5 | 回退后仍无法重连 | 恢复备份后重连仍失败即停，停止一切自动恢复尝试 | 保持人工接管：Web UI 与 human 凭据是独立管理入口；保留最后已知配置副本与错误原文；由用户按宿主文档修复 | 最后配置副本位置、报错原文、已尝试步骤清单 | 禁止在未确认回退时继续新任务或臆测成功；修复路径由人决定 |

## 9. 终端适配必查：工具超时与等待预算（本片仅准备，T/W 不变）

依据【指南事实】`TERMINAL_MCP.md`「终端适配必查」（55-80 行）：

| 项 | 当前记录 | 性质 |
|---|---|---|
| Codex 当前 W | `timeout_seconds=300`（用户既有用法，反馈未遇超时报错） | 【指南事实】`TERMINAL_MCP.md:68`；本片不改变 |
| Codex T（客户端单工具上限） | 660 秒仅为既有文档/工具建议依据（`WAIT_RECOMMENDED_CLIENT_TIMEOUT_SECONDS=660.0`，`bridges/talk_task_tools.py:39`）；本轮未重核运行配置 | 【待核验】：实施时按实际宿主配置键/取值/单位再核，不能把 660 当已验证能力 |
| 返回余量 | 参考 ≥5 秒（`WAIT_CLIENT_MARGIN_SECONDS=5.0`，`bridges/talk_task_tools.py:88-90`），W+余量≤T | 【源码事实】常量存在；实际余量【待核验】 |
| 外层函数交还预算 | 宿主更高指令优先，不能保证单次外层 600 秒阻塞；等待预算须与宿主函数调用时限匹配 | 【指南事实】`TERMINAL_MCP.md:62、74-75` |
| 执行者任务预算 | 本机DeepSeek/Kimi bridge历史配置为`--timeout 3600`（2026-09-12已核），通用bridge默认600秒；这是执行者整轮预算，实施时仍以实际配置为准。Codex桌面TALK MCP入口本身不承载执行者任务预算；等待到期不取消/重派/重启执行者任务 | 【历史指南事实】`MODULE_bridges.md:204-206`；`TERMINAL_MCP.md:63` |

取证要求（未验证一律 not_run）：
- 正常 `matched`/`timeout`：工具返回 `return_reason` 与 `query_stats` 如实区分（`bridges/talk_task_tools.py:1135-1166`）；
- API 错误：`api_error` 显式报错路径，不伪装成 timeout/matched（`bridges/talk_task_tools.py:1630-1667`）；
- 客户端取消/同连接后续排队恢复：同步 stdio 等待占用当前 MCP 连接，取消不会立即终止程序侧等待，后续调用排队（【指南事实】`TERMINAL_MCP.md:75`；`WAIT_CANCELLATION_NOTE`，`bridges/talk_task_tools.py:74-78`）；恢复能力须真实终端证据，本片未验证，登记 **not_run**；
- 本片不为准备做实际长等待/取消/重启；工具可发现（目录存在）**不等于**主动适配通过。

## 10. 176准备验证与限制（历史记录，原件不追改）

**本片实际做的验证**：
- 派发包 `source_manifest.json` 登记 19 个对象逐一实测：文件大小与 sha256 **全部命中**当前工作区；
- 当前 Git HEAD `4ce691d54eb0dc7a48d6fada5f45bf514e4b9dea`，工作区干净；派发包记录 `dispatch_head=b37b6e6`（差异=派前八份正式文档补记本轮人工通过已提交，manifest 各文件内容 SHA 与当前一致，业务源码零差异）；
- 必读文档与限定源码全部实读：`PROJECT_BRIEF.md`、`MODULE_bridges.md`、合同 §5.3（`CONTROLLER_MODE_DESIGN.md:200-211`）与 §4.3/§8、`TERMINAL_MCP.md`、`TASK_WORKFLOW.md`、`QUICKSTART_AGENT.md`、`bridges/talk_terminal_mcp.py`（全文 192 行）、`bridges/talk_task_tools.py`（全文 2185 行）、`server/routes/tasks.py`、`server/routes/members.py`（全文 146 行）、`server/auth.py`（全文 38 行）、`server/models.py`（全文 1599 行）；以上路径均存在，无需改记实际位置；
- 交付包经 `python scripts/talk_workflow.py validate .tmp/initiator-mode-identity-prepare/development.json --expect-task-id 176` 通过。

**限制（如实）**：
- 本片未读/未写任何密钥与用户含凭据配置；Codex 桌面配置目标文件/节/键名/重载方式全部标【待核验】；
- 旧任务清单是 2026-10-07 07:23 UTC 快照，不能当切换时事实；未做跨项目盘点；
- 未跑业务测试（本片无业务改动，不重复 I-1/I-2 套件）；真实切换、重连、身份实测、试派、长等待/取消/排队全部 **not_run**，属后续阶段；
- 本片只完成准备，**未发生任何身份切换或真实验收**；已由177独立复核通过，正式文档/Git由Codex收尾；实际身份切换仍未执行。

## 11. 177独立复核与Codex发布裁决（2026-10-07）

- 177对原需求1–10/合同5.3与A–I逐项独立回源，约40处出处语义一致；原19来源与复核26对象大小/SHA全匹配，原176交付及本人177交付validate均退出0。业务/配置零差异，真实切换/重连/试派/长等待/取消排队和业务大套件均not_run；准备文档无业务变更，不要求重复业务测试。
- N1收取权限行号改为2494–2495；N2显式引用快照筛选非完整性保证；N3区分本机bridge历史3600、通用600与Codex MCP无执行者预算；N4明确F4只能由实际created_by身份取消，当前归属不符的Agent无权操作。均为已审语义的文字澄清，无返工缺口，原稿和报告保持。
- N5事实记录：本次派审包dynamic_note预先明示Codex仅可收尾三份进度/路线图记录。复核窗口4ce691d→b2e44ed正是该范围，原交付稿和业务来源SHA未变，复核不受影响。此处只记录本次明示边界，不改AGENTS、不扩大同时审改业务或稿件的范围。
- 补清身份判据：`--check`作为入口/member_id辅助核验，完整成功标准仍通过服务端反查同时确认`member_id=agent:codex`与`kind=agent`，不以成员ID前缀或标签替代kind。
- 177/msg2679、176/msg2678已由原human入口收取，result_collected_at原记录分别2026-10-07T08:41:43.618575/2026-10-07T08:41:45.750729；裁决与回执索引`.tmp/initiator-mode-identity-prepare-receipt/acceptance.json`。这仅完成本链收取，实际切换前仍须刷新其它旧任务。
- 实施前保留待核项：实际配置文件/节/键名/宿主重载、管理员安全提供现有agent:codex Key、实际名册/未禁用、真实T/W/余量/外层预算、刷新后旧任务盘点与当次试派授权/开发要求。实际实施不读取聊天中的Key、不变更模型供应商登录，不将准备通过声称为自身身份已切换或主动已生效。
