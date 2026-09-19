> **已被新决策替代（2026-09-19）**：用户确认页面唯一指定项目主控、保留现有任务权限、长期保存直到人工解除或更换，无期限且无需续租。本文为历史设计档案；会话绑定、ACK、租约、自动过期和任意Agent自行绑定均不作为当前实施要求。当前合同见 `PROJECT_INTEGRATION.md` 的“C1b-S：长期项目主控指定”节。此前复核通过仅针对旧假设，不能覆盖新方案。

> 归档说明（Codex，2026-09-19）：以下为 #108 合同 v3 的原文存档，已由 #109 独立定向复核通过，前序复核见 #105/#107。它是待政策确认的设计，不是已实现接口规范。原文中的“本轮不提交/仅临时文件”等描述属于执行者交付时点，不限制本次主控归档。原文相对证据路径均以本地 `.tmp/c1b-0/` 为基准；临时证据不随 Git 分发。
>
> 原稿 SHA-256：`f44b82d39b4edf3a696c1e391ff3d96d829706c3f144f8ab0a6a45b1e83e66be`。主控确认 R1/R1-a/R1-b 关闭；D1/D2/D3 尚未批准。D1 待确认摘要须区分 human 角色不受名册限制与跳过活跃绑定/版本检查，不把“无条件”解释成绕过并发保护；强制释放使用专用入口。
>
> 两项非阻塞观察留到实施任务处理：权限矩阵行标签可简化；端点测试须补 renew 的陈旧 epoch/错误 token、release 的错误 token 格，按正文矩阵和 L4 定义断言。模型脚本通过不等于 FastAPI 端点行为已验证。

---

# C1b-0 主控会话归属与生效确认：最小合同与实施切片建议（v3 修订稿）

- 类型：**设计切片**（合同设计，不是生产实现）。本文只描述推荐合同与切片边界，**本轮不改**业务代码 / 数据库 / API 实际行为，不自动绑定主控，不启停服务，不写真实项目配置，不派生任务，不 commit/push。
- 版本：**v3 修订稿（R1 定向修订）**。承接 #104 原稿（逐字节留存为 `contract-v1.md`，38623 字节，sha256 `bcc95b128fdf17c31027e7ae5bb1010cc022796160754beacecce7fe52e2661d`）、#105 独立复核（`review.json` / `review-notes.md`，实际结论 **blocked**）、#106 v2 修订（`revision-notes.md`）与 #107 独立复验（`re-review.json` / `re-review-notes.md`，实际结论 **blocked**，唯一阻塞项 **R1**）。#106 v2 文本逐字节留存为 `contract-v2.md`（68050 字节，sha256 `dc6bdbb2ea0e44d48d99d2a9a40635c9f3a3e039ea00b3f7bb34ef4ffa52daf0`）。
- 本版**只做 R1 定向修订**（#108，采用 Codex 技术裁决的 review 方案 a：缺必填字段统一 422，不采用“角色感知可选 schema”方案），外加两个关联小项；**不重做** #107 已确认通过的 P1-1 / P1-2 / P2-2 主体、五项 P3 与证据口径。R1 修正范围、逐格改动与限制见 `final-revision-notes.md`，本次修订索引见本文 §11.1。
- 基线：`D:/claude-test/TALK`，分支 `codex/terminal-return-codex`，commit `c20640b6c57f4b73d37e4d3c5dcbfcd9819272d5`。`git --no-optional-locks status --porcelain` 仅显示 `M docs/PROGRESS.md`（主控派发记录，本片保留不动）；本片产物全部在 `.gitignore:206` 忽略的 `.tmp/c1b-0/` 下，不污染工作区。
- 证据口径：`源码`＝本轮实际读取的仓库源码/文档；`既有实测`＝仓库内已记录的真实终端试验；`探针`＝隔离临时库实测（`.tmp/c1b-0/probe_identity.py`，进程内 `TestClient`）；`未验证`＝没有证据，不推断。
- 结论性质：**设计完成 ≠ 主控能力已实现**。`effective_mode` 当前仍恒为 `null`、`effective_status=not_bound`（`server/routes/projects.py`、`bridges/talk_task_tools.py:267`），本文不改变该事实。
- 范围声明：本修订**只做条款/请求体/状态/用例的一致性修正**，不扩大为会话凭证系统、不新增业务功能、不改任务权限。

---

## 0. 本次修订采用的假设与待确认项

#105 复核认定 D1/D2/D3 属于**待项目管理者决定的推荐政策**，不能自行当作已授权实施。为使合同可被独立检查和实现，本稿按“一致的推荐假设”写完整条款，并逐项标注状态。

| 编号 | 对应 | 本稿采用的一致假设 | 状态 |
| --- | --- | --- | --- |
| A1 | D1 授权范围 | C1b-1 只允许「human 无条件 `bind` / `force-release`」+「`ProjectAgent` 名册内 agent 在**无活跃归属或归属已过期**时 `bind`」；agent 间接管（同 member 新会话抢占、跨 member `takeover`）**不在 C1b-1 实现** | **待项目管理者确认（推荐政策）**；C1b-1 动工前必须显式确认，未确认不得实施 |
| A2 | D2 派发入口 | `active` 意向**不**影响派发 / 领取 / 完成 / 收取 / 门禁；只在 `talk_list_agents` 增加只读提示字段 | **待项目管理者确认（推荐政策）** |
| A3 | D3 重启与过期 | 绑定行与 token 哈希**持久化**；重启不批量清空；无后台 sweeper，过期只在写路径懒回收 | **待项目管理者确认（推荐政策）** |
| A4 | P3-5 | `controller_mode=passive` 时 `ack` **被拒绝**（409 `controller_mode_passive`），不写库 | 本修订直接采纳（技术一致性所需，可由管理者改判） |
| A5 | P3-1 | 默认回滚＝**停用新路由/工具并保留数据**；删表属于显式人工决策且须先归档 | 本修订直接采纳（技术一致性所需） |
| A6 | state_version 定位 | `state_version` 是**只增的观测计数器**，不作为 CAS 输入；实际 CAS 由 `binding_token_hash + owner_epoch + lease_expires_at (+ controller_mode_version)` 承担 | 本修订直接采纳（消除“字段说明与实际请求不符”） |
| A7 | 错误码风格 | 控制器错误沿用既有**字符串 `detail`**，以稳定码 `controller_*` 开头；不引入对象型 `detail` | 本修订直接采纳（与 `messages.py:303-312`、`projects.py:401-410`、MCP `talk_task_tools.py:146-152` 兼容） |

**A1–A3 未确认前，本文只作为设计与复核对象，不构成实施授权。**

---

## 1. 现状：现有 API / MCP / bridge 到底能可信提供什么标识

### 1.1 唯一可信的服务端身份

| 信号 | 源码依据 | 能证明 | 不能证明 |
| --- | --- | --- | --- |
| `X-API-Key` → `Member` | `server/auth.py:resolve_member_by_key/get_current_member` | 请求方持有该 member 的共享密钥；`disabled_at` 时 403 | 哪个进程 / 终端 / 原生会话；模型是否在运行；属于哪个项目 |
| `Member` 字段 | `server/models.py:19` | `id/kind/display_name/api_key/poll_hint/created_at/disabled_at` | **无 project 维度、无 session 维度、无过期** |
| `ProjectAgent(project_id, member_id)` | `server/models.py:122`（human `sync` 全量替换，`server/routes/projects.py:285`） | 项目内“名册”记录（含 `business_role`/`decision_tier`） | 不是认证范围；任务创建只校验 `_ensure_project_exists`（`server/routes/tasks.py:104`），**不校验成员是否在该项目名册内** |
| `AgentInstance` | `server/models.py:148`，`server/routes/instances.py:25` | `id/member_id/runtime/status/host/pid/current_task_id/*_at`；跨 member 抢同一 id → 403 | 无 `project_id`、无原生会话 id、无终端产品枚举；`id` 由客户端自选；`pid/host/runtime` 服务端不校验 |
| WS/SSE | `server/ws_hub.py:Hub._connections`、`server/main.py:358/303` | 仅按 `member_id` 索引的在线连接；内存态 | 无 connection id、不持久化、无会话 |
| MCP 工具身份 | `bridges/talk_task_tools.py:114/164/171` | `TALK_BASE_URL` / `TALK_API_KEY` / `TALK_PROJECT_ID` / `TALK_MEMBER_ID` 环境变量 | 全是进程启动时的声明；`bridges/talk_terminal_mcp.py:89` 还显式 `pop("TALK_MEMBER_ID")`，只认密钥真实身份 |

**项目读权限口径（本稿明确，供 §3.2/§7.1 引用）**：`GET /api/projects`（`projects.py:194`）与 `GET /api/projects/{project_id}`（`projects.py:204`）只依赖 `get_current_member`，`_get_project`（`projects.py:49`）只查存在性；因此**任意已认证成员可读任意项目**，读接口不校验名册。写接口（`POST/PATCH/DELETE`、`sync`、`controller-mode`）才是 human-only（`projects.py:169/256/297/342/378/421` 的 `_require_human`）。新 `GET .../controller` 与既有读口径一致；跨项目的边界是“**写入互不影响、读按项目 URL 各取一行**”，不是“不可读”。

### 1.2 探针实测（隔离临时 sqlite + 进程内 `TestClient(main.app)`，未连真实 `talk.db`）

全部 11 项通过，结果见 `.tmp/c1b-0/probe_identity_result.json`（复跑留痕 `review_probe_rerun_stdout.json`）。

**证据口径修正（本次修订按 #105 复核注记收紧表述，结论方向不变）**：全部探针都在**同一进程、同一 `TestClient`** 内完成，是**进程内模拟**，不是真实 HTTP 网络往返，也不是真实双进程；其中 F 的“第二个进程”与 A/B 的“另一个会话”都是**同一进程内的模拟措辞**，H 用短路桩替换 `_api_request` 观测方法序列，**不是真实 HTTP 观察**。

| 探针 | 结果 | 含义 | 证据强度（修正后） |
| --- | --- | --- | --- |
| A 同一 API Key 注册两个 instance id | `PUT sess-A=200, PUT sess-B=200` | instance id 是**客户端标签**，同一凭证可有任意多个“会话” | 进程内两次 `PUT`（真实 HTTP 路由，非真实双会话） |
| B 同一 member 模拟“另一会话”覆盖 `sess-A` | 200，`runtime/pid` 被改写 | 实例记录**无互斥**，先写不保护后写 | 进程内 `PUT`（同进程模拟，非真实双进程） |
| C 跨 member 抢同一 id | 403 `instance belongs to another member` | 现有唯一约束是 member 归属 | 进程内请求，源码 `instances.py:37-41` 一致 |
| D `PRAGMA table_info(agent_instances)` | 无 `project_id`、无 `*session*` | 实例表没有项目/原生会话维度 | 直读隔离库 schema |
| E 未登记进项目的 agent 创建该项目任务 | 201，`project_id=prj_c1b0` | **项目是客户端声明的作用域，不是认证边界** | 进程内请求，源码 `tasks.py:104` 一致 |
| F 同一 member 用同一 `claim_token` 续租两次 | `claim=200, heartbeat1=200, heartbeat2=200` | `claim_token` 是 **bearer 令牌**：**校验只绑 member，不校验进程/实例/会话**（源码 `tasks.py:2676` 只比对 `claim_token`） | **同一进程模拟第二次心跳**；证明的是“校验无进程维度”，**不代表**真实双进程实测 |
| G 非 `created_by` 调 `collect-result` | 403 | 收取权只属于原请求者，主控身份不能代收 | 进程内请求，源码 `tasks.py:2486` 一致 |
| H `talk_list_agents` 全过程方法序列 | `['GET /api/projects/...', 'GET /api/projects/.../agents', 'GET /api/members']` | 只读工具当前**零写入**，这是必须保持的基线 | **短路桩观测**（替换 `_api_request`），非真实 HTTP；真实 HTTP 断言留待 C1b-1 |
| I `GET /api/projects/{id}/controller` | 404 | C1b 端点尚未存在 | 进程内请求 |
| J 项目详情 | `controller_mode=passive, controller_mode_version=0`，无其它 `controller*` 键 | C1a 只有意向与版本，无任何生效/绑定字段 | 进程内请求 + 源码 `models.py:1240` |
| 0 human 注册项目 | 201 | 探针前置条件（human-only 项目写权限） | 进程内请求；**不计入 A–J 的 10 项**，合计 11 项 |

### 1.3 各终端真实接入差异（基于仓库已有实测，不做第三方版本网络调研）

| 终端/宿主 | 连接方式 | 身份 | 原生会话可观测/可恢复 | 同凭证双会话 | 已知限制（文档明写） |
| --- | --- | --- | --- | --- | --- |
| Codex Desktop / Codex CLI | MCP stdio → `bridges/talk_terminal_mcp.py` | API Key → member（忽略继承的 `TALK_MEMBER_ID`） | 协议层存在 `thread/resume` 等，但**本机无受支持入口接回正在使用的 Desktop 会话**（`.tmp/codex-terminal-return/REPORT.md`） | 未验证 | `codex app-server daemon` 在 Windows 不支持；没有“客户端已展示”回执 |
| 官方 Kimi Code CLI 0.38.0 | 工作区级 `.kimi-code/mcp.json` → `scripts/kimi_talk_mcp_launch.py` → 同入口 | `agent:kimi` | **有且已实测恢复**：会话 id `session_<uuid>`，`kimi -S <session_id> -p` 续接（`docs/guides/TERMINAL_MCP.md:168`） | 未验证（#64/#65 是顺序两次会话） | 会话中改 MCP 配置只对新会话生效；仅可信工作区加载；不保证其它版本 |
| DeepSeek Harness `dsh` | ①bridge 轮询 ②主控 stdio MCP ③ACP 薄驱动 | `agent:deepseek` | **headless 无 resume**；**ACP 有 `session/new|list|resume|close`**，零模型同 ID 恢复实测通过、真机 `prompt --resume` 复用同一 sessionId | 未验证 | `session/resume` 返回**不含 sessionId**；仅有人值守、同工作区 |
| WorkBuddy 桌面 5.5.6 | 用户级 MCP 界面导入，复用同入口 | 专用 `agent:workbuddy` | **桌面无跨会话 resume 概念**；只到“同对话沿用上下文” | 未验证 | 88 号提前收取**无法确认是模型还是客户端自动化**；服务端日志只有 `member_id`，无 actor |
| 通用 bridge（`bridges/cli_bridge.py`） | 轮询 REST + 实例上报 | `--key` + `--name` | 参数层**无 session/resume token**，只有 `--instance-id`（默认 `f"{member_id}:{uuid4()}"`，`:3547`） | 同实例有运行锁；跨实例未测 | 崩溃/强杀后的 `offline` 未验证 |

**关键结论**：Kimi 与 DSH 的**原生 session id 真实存在**，但它们只对**宿主/驱动进程**可见；`scripts/dsh_acp_drive.py` 处理的 ACP `sessionId` **从未上报 TALK**（`bridges/` 全目录无任何上报原生会话 id 的调用）。MCP 子进程本身看不到宿主会话 id，只能看到“自己被谁拉起、活了多久”。

### 1.4 缺口清单（明确缺失，不推断）

1. 实例无 `project_id`：`GET /api/instances` 也不按项目过滤；项目侧只能靠 `ProjectAgent` 名册反查，会带上该 member 在**所有**项目的实例。
2. 无原生 session id 进入服务端模型；`AgentInstance.id` 无外部可验证语义。
3. 无 connection id / 会话表 / 连接持久化（重启即丢）。
4. 实例无心跳、无 TTL、无过期回收；`offline` 完全靠进程自报。
5. 无 per-session / per-instance 鉴权：同一 member 的密钥可写任意 `instance_id`。
6. 无终端/产品类型受控枚举（只有自由文本 `runtime`）。
7. **同凭证双会话从未实测**；“服务端能否区分两个同 member 会话”目前答案是不能。
8. WS/SSE 路径不检查 `disabled_at`（与本设计无关，登记为既有差异）。

---

## 2. 最小“主控会话”标识合同

### 2.1 命名

服务端对象叫 **主控会话绑定（controller session binding）**，不叫“主控身份”。它是**项目维度的一行登记**，不是新的认证主体。

### 2.2 最小字段（新表 `project_controller_bindings`，一项目最多一行）

| 字段 | 类型/默认 | 作用 | 强度 |
| --- | --- | --- | --- |
| `project_id` | TEXT PK → `projects.project_id` | 项目维度隔离；跨项目互不影响 | 服务端 |
| `owner_member_id` | TEXT NULL → `members.id` | 服务端从 `X-API-Key` 解析，**不接受请求体传入** | 服务端认证 |
| `holder_label` | TEXT NULL | 客户端自报会话标签 `cs_[A-Za-z0-9_-]{8,64}`；给人看，用于同凭证两会话的人工区分 | **仅客户端标识** |
| `instance_id` | TEXT NULL → `agent_instances.id` | 可选；写入时必须 `instance.member_id == owner_member_id`（复用 `tasks.py:1111 _ensure_instance_owner` 口径：不存在→400 `instance_id not found`，属他人→403 `instance belongs to another member`） | 服务端校验归属 |
| `owner_epoch` | INTEGER NOT NULL DEFAULT 0 | 归属世代；**每次归属字段实际写入（A→B 或 A→NULL）+1**，单调递增不回绕；持久化在行内，跨重启保留 | 服务端 |
| `state_version` | INTEGER NOT NULL DEFAULT 0 | **只增的观测计数器**：任一状态字段被接受变更时 +1；**不作为任何请求的 CAS 输入**（见 §5.1 说明） | 服务端（观测） |
| `binding_token_hash` | TEXT NULL | `sha256`（服务端签发的一次性明文 token）；**只存哈希** | 服务端能力令牌 |
| `ack_state` | TEXT NOT NULL DEFAULT `none` | `none` / `acknowledged`；取 `acknowledged` 时 `ack_epoch`/`ack_mode_version` 必非空 | 自报 |
| `ack_at` / `ack_epoch` / `ack_mode_version` | NULL | ACK 时间；ACK 时的 `owner_epoch`；ACK 覆盖的 `projects.controller_mode_version`（与 `expected_mode_version` 同值，由 CAS 保证） | 自报 |
| `lease_expires_at` | TIMESTAMP NULL | 租约到期；**`bind` 必写非空值**；NULL 视为“无有效租约”（等价过期），**不视为无限期** | 服务端时钟 |
| `heartbeat_at` | TIMESTAMP NULL | 最近一次续租/心跳 | 服务端时钟 |
| `bound_at` / `updated_at` | NOT NULL | 时间戳 | 服务端 |
| `last_reason` | TEXT NULL | **“最近一次写路径落库的原因”**（不等于派生状态）：`released` / `force_released` / `expired` / `mode_changed` | 服务端 |

**`last_reason` 语义（P3-2）**：只有**写路径**（`release` / `force-release` / 写路径懒回收 / 归属变更）才会落库。纯读 `GET` 派生出的 `expired` **不会**改写 `last_reason`：一个行可能“派生为 expired 而 `last_reason` 仍是 null”。UI 不得把 `last_reason` 当状态字段用。

**不新增**：`projects` 不加列（沿用 C1a 的 `controller_mode` / `controller_mode_version`）；`agent_instances` 不加列；不改 `AgentTask`。

### 2.3 生成 / 持久化 / 恢复 / 重连（含 P1-2 幂等与恢复规则）

1. 客户端**先生成** `holder_label`（`cs_` + 随机），并在**同一原生会话内复用**；跨会话默认换新标签。宿主若已提供原生会话 id（如 Kimi `session_<uuid>`、DSH ACP `sessionId`），可把它作为标签原文或派生值传入——但服务端**不校验其真实性**，也**不把它当凭证**。
2. `POST .../controller/bind` 首次登记 → 服务端生成 `binding_token = uuid4().hex`（与 `claim_token` 同风格），**明文只在本次 201 响应返回一次**，落库只存 `sha256`；同时 `owner_epoch += 1`（首次为 0→1）。
   - **不携带 `binding_token` 时的 `expected_epoch` 规则（#107 疑点修正，唯一口径）**：`expected_epoch` **可选且不参与任何判定**——首次登记走 INSERT，没有可比较的库存世代；接管“空/已过期”行走的是**归属/租约条件**（§5.1），不是世代条件。省略或携带（含任意值）**结果相同**：既不返回 409 `controller_epoch_stale`，也不因该字段返回 422。接管成功的 `owner_epoch` 一律**严格增大**，实际新值以响应回传的 `owner_epoch` 为准（不承诺恰好 +1，见 §5.1 记账规则）。客户端若要与本地记录比对，应使用响应值而不是请求值。
3. **持有 token 的进程**是唯一能 `ack` / `renew` / `release` 的一方。恢复/重连＝同一进程继续用同一 token 调 `renew`；**服务端永不重新签发同一 epoch 的 token**。
4. **`bind` 的幂等分支（P1-2）**：`bind` 请求体可携带可选 `binding_token`。**携带 `binding_token` 时 `expected_epoch` 必须同时提供（`#107` 疑点修正）**：缺失时请求体不完整，在 L2 返回 **422**，不进入任何写路径。理由：幂等判定要求“同 `owner_epoch`”，若允许省略 `expected_epoch`，持有者重试会被迫退化为“member + hash 二元组”，既放大了与合法持有者误判 409 `controller_binding_held` 的空间，也让幂等判据与 §5.1 的 where 条件不一致。服务端仅在**同 member + 同 `owner_epoch` + `sha256(binding_token)==binding_token_hash`** 三元组同时成立时判为幂等重试：
   - 命中 → `200` 返回**当前绑定现状**（`bound=true`），**绝不回传明文 token**，`state_version` 不变，`holder_label` 保留首次值；
   - 携带了 token 但哈希不符或库中已清空 → `409 controller_token_invalid`；
   - 携带了 token 且哈希匹配，但归属已释放（`owner_member_id IS NULL`）或租约已过期 → `409 controller_not_bound` / `409 controller_lease_expired`，**同样不重发 token**，客户端须重新 `bind`（新 token、`owner_epoch` 严格增大）。
   - `holder_label` / `instance_id` **不参与**幂等判定（客户端标签不是安全边界）。
5. **首次响应丢失（201 丢失，客户端没有 token）的恢复规则（P1-2 明确禁止项）**：
   - 服务端**不得**因为 `holder_label` 相同、`instance_id` 相同或 member 相同而返回、重建或以任何方式取回明文 token 或哈希；
   - 此时裸重试 `bind`（无 token）→ `409 controller_binding_held`；
   - 两条合法恢复路径：① **等租约自然到期**（默认 120s，最长不超过 `lease_seconds`）后重新 `bind`（`owner_epoch` 严格增大）；② **human 显式 `force-release`** 立即释放再 `bind`；
   - 客户端判据是 `GET .../controller` 的派生状态（`released` / `expired` / `not_bound`），不是本地标签猜测；
   - 结论：**“幂等重试”只对仍持有 token 的进程成立**；token 丢失＝按新会话处理，不存在“凭 label 认领”的第三条路。
6. **进程重启且未持久化 token** ⇒ 视为**新会话**（同第 5 条）。
7. **token 明文落盘约束**：明文 `binding_token` 只允许保存在**仓库之外**的客户端私有位置（例如 OS 用户配置目录）。若实现确需写入工作区，必须同时满足：(a) 路径被 `.gitignore` 覆盖且**不位于仓库根内**；(b) 实现文档明确标注“非安全存储”；(c) 明文不得出现在 TALK 消息、任务正文、交付包、日志、工具描述或错误响应中（`ControllerBindingOut` 只暴露哈希存在的布尔含义）。本片**不实现**该落盘，只在接口中说明。

### 2.4 与认证 member / project 的绑定

- `owner_member_id` 从 `get_current_member` 取，**请求体不能指定**；项目由 URL 路径 + `projects` 表存在性确定（沿用 `_get_project`，项目不存在 → 404）。
- 一行一项目：同 member 在两个项目是**两条独立绑定**，各有自己的 `owner_epoch` / `state_version` / token，互不影响。
- 读面（准确口径）：任何**已认证成员**都可 `GET` 任意项目的绑定状态（与 §1.1 的既有项目读权限一致）；写入权限由 §3.2 限制。跨项目**写入**互不影响；不存在“跨项目隐式继承归属”。
- `holder_label` / `instance_id` 都**不能**当认证用；`instance_id` 只用来把绑定关联到既有实例视图，缺失时绑定照常成立。

### 2.5 同凭证两个会话如何区分

| 手段 | 能区分吗 | 说明 |
| --- | --- | --- |
| `X-API-Key` | ❌ | 同 member 共用 |
| `holder_label` | ❌（可伪造） | 只用于展示与人工判断；**不参与幂等判定、不用于认领秘密** |
| `instance_id` | ❌（可伪造/可复用） | 探针 A/B 已证明同一 member 可任意注册与改写 |
| `binding_token` | ✅（能力令牌） | 只有签发时拿到明文的进程能续租/ACK/释放；另一个会话拿不到 |
| `owner_epoch` | ✅（CAS 前置条件） | 阻止旧会话覆盖新归属；持久化、单调、不回收 |
| `state_version` | ❌（仅观测） | 供读侧判断“是否发生过变更”，不参与鉴权与 CAS |

### 2.6 强度分级与禁止事项

- **仅是客户端标识**：`holder_label`、`instance_id`、`pid`、`host`、`runtime`、`TALK_MEMBER_ID` 环境变量、MCP 配置路径。
- **需要服务端授权**：`bind` / `ack` / `renew` / `release` 的权限判定、`takeover`、`force-release`、以及对**既有任务权限**的任何扩权。
- **能力令牌**：`binding_token` 只证明“**同一个客户端进程（或拿到该令牌的进程）在持续活动**”。
- **明确禁止**：
  1. 禁止把 nonce / token 包装成“宿主原生会话认证”或“模型已运行”的证明；UI 与工具描述不得写“已生效 / 运行中”。
  2. 禁止用模型名、`business_role=lead`、`decision_tier` 推断主控身份或自动升权。
  3. 禁止把 `holder_label` 或 `instance_id` 当安全边界；**禁止凭它们返回/重建/取回 token**（§2.3.5）。
  4. 禁止在只读工具（`talk_list_agents` / `talk_get_task` / `talk_get_delivery` / 新 `talk_controller_status`）里偷偷写 ACK 或续租；`GET` 端点**只计算派生状态，不写库**（续租只能由显式 `renew` 触发）。
  5. 禁止把明文 `binding_token` 写入仓库内文件、提交、消息或交付包（§2.3.7）。

---

## 3. 谁可以申请 / 批准 / 接管 / 释放（权限矩阵）

### 3.1 操作定义

`read`（只读状态）、`bind`（登记/幂等重试）、`ack`（确认读取并承诺遵循当前 active 意向）、`renew`（续租）、`release`（持有者主动释放）、`force-release`（human 强制解绑）、`takeover`（从有效持有者手中接走）。

### 3.2 权限矩阵（v2 起：按“能力”而非“身份”判定，逐格唯一归类；**v3 按 R1 修正 422 归类与 403 前置条件**）

| 操作 | human（无 token） | human（自己 bind 的会话，持有效 token） | 当前持有会话（token 有效） | 原持有会话（token 陈旧/epoch 落后） | 同 member 其他会话（无 token） | 名册内其他 agent（无 token） | 名册外 agent / 未认证 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `read` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 未认证 → 401 |
| `bind`（请求体完整） | ✅（A1） | ✅（幂等 200，不重发 token；须带 `expected_epoch`） | ✅（幂等 200） | ✅ **仅当归属为空/已过期**（否则 409 `controller_binding_held`），新登记时 epoch 严格增大 | ✅（A1，无归属时）/ 活跃归属 → 409 `controller_binding_held` | ✅（A1） | ❌ 403 `controller_not_authorized` |
| `ack`（请求体完整） | ❌ **422**（缺 `binding_token`/`expected_epoch`/`expected_mode_version`，见下行） | ✅ | ✅ | ❌ 409 `controller_epoch_stale` | ❌ 409 `controller_token_invalid`（token 错，且 epoch 不落后） | ❌ 同左 | ❌ 同左 |
| `renew`（请求体完整） | ❌ **422**（缺 `binding_token`/`expected_epoch`） | ✅ | ✅ | ❌ 409 `controller_epoch_stale` | ❌ 409 `controller_token_invalid` | ❌ 同左 | ❌ 同左 |
| `release`（请求体完整） | ❌ **422**（缺 `binding_token`/`expected_epoch`；**引导走 `force-release`，仅文案层**） | ✅ 记账 `released` | ✅ 记账 `released` | ❌ 409 `controller_epoch_stale` | ❌ 409 `controller_token_invalid` | ❌ 同左 | ❌ 同左 |
| `force-release`（请求体完整，含非空 `expected_epoch`） | ✅ 仅 human | ✅ 仅 human | ❌ 403（非 human 到达角色鉴权，agent 不得强制） | ❌ 403（同左） | ❌ 403（同左） | ❌ 403（同左） | ❌ 403（同左） |
| `takeover`（有效归属被占用） | ⚠️ **C1b-1 不实现**，C1b-2 定策略（A1/D1） | 同左 | ❌（应先 `release`） | ❌ | ❌ | ❌ | ❌ |

**读法（列前置条件）**：`ack`/`renew`/`release` 三行的“human（无 token）”格写的是**请求体完整时**的归类；**human 无 token 必然意味着请求体不完整**（`binding_token` 是必填字段），实际首个命中层是 **L2 → 422**，与同 member 无 token 会话、名册内其他 agent 得到**同一个** 422。上表“请求体完整”列的前置条件与 §7.3.1 决策表逐格一致；`❌ 422` 表示被拒且不写库，不是“允许”。

要点（相应修订 #105 的 P2-1 / P2-2；**#108 按 R1 方案 a 再修订**）：

- **判定顺序（唯一表述，与 §7.3 L0–L4 同源）**：L0 认证（401）→ L1 资源（404）→ **L2 请求体完整性（422，角色盲）** → L3 角色/授权（403）→ L4 状态与能力（409）。矩阵里每一格只对应**一个**错误码。**缺必填字段一律 422，与调用者是 human 还是 agent 无关**；只有请求体完整后，才按角色 → 归属 → `expected_epoch` → token → 租约 → 模式的顺序判定 403/409。
- **R1 修正（删除不可达承诺）**：v2 曾写“无 token 的 human 调 `ack`/`renew`/`release` → 403 `controller_not_authorized`”。该承诺在本分层下**不可达**（缺字段必先命中 L2 422；若带伪值则到 L4 才判 token，403 无从识别“无 token”）。v3 **删除该可执行承诺**，改为 **422**；“human 应改用 `force-release`”只作为**响应文案 / 用户说明**，不改变状态码。
- **ACK 不允许代签**：`ack` 的语义是“某个客户端进程声称已读取并承诺遵循”。无 token 的 human 调 `ack` → **422**（请求体缺必填字段），不写库、不代签；human 若自己 `bind` 并在**同一会话持有 token**，则与 agent 持有者同权（能力路径，不是身份路径），权限与状态码**不变**。
- **`release` 只有一条路径**：合法 token 持有者；`binding_token` 与 `expected_epoch` **必填**。无 token 的 human **不能**用 `release`（缺字段 → 422，提前阻断），需走 `force-release`（记账 `force_released`）；因此不存在“human 冒充普通释放绕过 `force_released` 记账”的通道（P2-2，该结论不依赖具体状态码）。human 本人是合法 holder 时按 holder 路径走，记账 `released`（用例 10）。
- **接管必须显式**：不得靠轮询/心跳超时自动抢占。归属**过期**后重新 `bind` 不算抢占（有明确过期证据）。
- **默认不强制取消原任务**：`bind`/`force-release`/`takeover` 都**不触碰** `AgentTask`（不 cancel、不 pause、不 requeue）。

### 3.3 与 C1a 模式配置、任务权限如何共存

| 既有合同 | 本设计的态度 |
| --- | --- |
| `PATCH /api/projects/{id}/controller-mode`（human-only，DB 层 CAS，`projects.py:360-411`） | **完全不动**。绑定不修改也不推进 `controller_mode_version`；模式切换仍由 human 单独操作 |
| `controller_mode` 零执行语义 | 保持不变：绑定不赋予任何任务/预算/门禁权限 |
| `collect-result` 只认 `created_by` | **不放宽**（探针 G 已证）。主控要收取必须自己就是原请求者 |
| `claim`/`complete`/`heartbeat` 认 `target_member_id` + `claim_token` | 不变；主控归属不产生新令牌、不绕过 token |
| 项目读接口只校验认证、不校验名册（§1.1） | 新 `GET .../controller` 与该口径一致；Task Hall 读权限仍＝`GroupMember` 行（human 无旁路），本片不改 |
| 根治理/预算只能 human 授予；`authorization_epoch` 防陈旧授权 | 不变；`owner_epoch` 是**项目主控登记**的独立计数器，**不得**替换或复用 `authorization_epoch` |
| `ProjectAgent.decision_tier=="decision"` 仅用于 review 豁免 | 不作为主控权限依据 |

### 3.4 需要单列的授权决策（不得擅自实现）

- **agent 间接管**（同 member 新会话 / 不同 member）属于新增授权策略，必须由项目管理者/Codex 裁决（见 §9 D1，本稿按 A1 假设书写）；C1b-1 只做 human `force-release` 与过期后重绑。
- **把主控纳入 `accept-milestone` 或预算授予**属于破坏性变更，**本设计明确不做**。

---

## 4. 状态表：requested / ACK / 生效 / 租约 / 失效

### 4.1 证据分级（谁能证明什么）

| 证据 | 证明了 | 没证明 |
| --- | --- | --- |
| 有效 `X-API-Key` | 持有某 member 的共享密钥 | 哪个进程/终端/会话；模型是否在运行 |
| `AgentInstance` 上报 | 某进程自报存在（member 级校验） | 进程真的在推理；不是同 member 别的进程 |
| `binding_token` 命中 | 某客户端进程持有服务端签发的令牌，是绑定时的那个进程（或拿到令牌者） | 宿主原生会话未结束；模型会继续；宿主能被唤醒 |
| `ack_state=acknowledged` | token 持有人**声称**已读到 active 意向与职责边界，且 ACK 时的模式版本经 CAS 校验等于当时的 `RV` | **模型真的在等待/推进**；不代表零续行或后台唤醒 |
| `heartbeat_at`/`lease_expires_at` 有效 | 客户端进程在最近 T 秒内仍能发起 HTTP 请求 | 它正在处理任务；会话结束后依然自证存活 |
| `AgentTask` 状态与门禁结论 | 任务层**真实副作用**（唯一硬凭据） | 与主控归属无关 |

### 4.2 派生状态表（`GET` 计算，不写库）

记 `now` 为服务端时间，`R` = `projects.controller_mode`，`RV` = `projects.controller_mode_version`。下表**自上而下第一个命中即结果**（顺序即优先级）：

| 序 | 条件 | `effective_status` | `effective_mode` | 建议 C2 文案 |
| --- | --- | --- | --- | --- |
| 1 | 后端无绑定字段 | `unsupported` | `null` | 后端不支持主控会话登记 |
| 2 | 无绑定行 | `not_bound` | `null` | 未登记主控会话 |
| 3 | `owner_member_id IS NULL`（显式/强制释放后） | `released` | `null` | 已释放主控会话 |
| 4 | `lease_expires_at IS NULL` 或 `lease_expires_at <= now` | `expired` | `null` | 主控会话租约已过期 |
| 5 | `R=passive` | `bound_passive` | `passive` | 已登记主控（项目当前被动） |
| 6 | `ack_state=none` | `awaiting_ack` | `null` | 已配置主动 · 会话未确认 |
| 7 | `ack_epoch==owner_epoch` 且 `ack_mode_version==RV` | `acknowledged` | `active` | 已确认 · 无运行证明 |
| 8 | 其余（ACK 存在但 epoch 或 mode_version 不匹配） | `ack_stale` | `null` | 确认已失效（配置或归属已变更） |

**注意**：
- 第 4 行把 `lease_expires_at IS NULL` 归入 `expired`（P3-3）：`bind` 必写非空租约，NULL 只可能来自异常/历史数据，**不赋予无限期**。
- 第 4 行先于第 5 行：过期且项目 passive 时显示 `expired`，不显示 `bound_passive`。
- 第 6/7/8 行只在 `R=active` 时可达：`ack` 在 passive 下会被拒绝（A4/P3-5），所以不存在“passive 下新写入的 ACK”。
- `acknowledged` 是本设计允许的**最高**证据等级，含义严格限定为“会话已确认读取并承诺遵循”，**不等价于生效、运行中、会被唤醒**。
- 按此顺序：`active → passive` 时状态回落为 `bound_passive`（旧 ACK 被保留但不再生效）；再切回 `active` 时 `RV` 已推进两次，旧 ACK 落到第 8 行 `ack_stale`，必须重新 `ack`。

### 4.3 失效规则与检查节点

| 触发 | 后果 |
| --- | --- |
| human 切换 `passive`↔`active`（`RV` 变化） | 旧 ACK 立即失去效力：停在 `passive` 显示为 `bound_passive`，切回 `active` 后因 `ack_mode_version != RV` 显示为 `ack_stale`，需重新 `ack`。ACK 时若 `expected_mode_version != RV` → 409 `controller_mode_changed`；若 `RV` 相符但模式为 passive → 409 `controller_mode_passive`（不写库） |
| `takeover` / 过期后重绑 | `owner_epoch` 增大（严格）；旧 token 哈希清空 ⇒ 旧会话 `renew`/`ack`/`release` 全部 409（`controller_epoch_stale`） |
| 显式 `release`（token 持有者） | `owner_member_id=NULL`，`owner_epoch+1`，token 哈希清空，`lease_expires_at=now`，`last_reason='released'` |
| human `force-release` | 同上，但 `last_reason='force_released'`；已 released 时重复调用返回 200 且**不写任何字段** |
| 心跳缺失 | 派生 `expired`；**写路径**做懒回收时落库 `last_reason='expired'`（P3-2：纯读不落库，不新增后台 sweeper） |
| 服务重启 | 绑定行与 token 哈希持久化；租约未过期则旧会话仍可 `renew`；过期则派生 `expired`。**不在启动时批量清空**（A3/D3） |

检查节点（被动/主动切换）：
1. **派发前**：主控读 `talk_list_agents.controller_mode`（含新 `binding`）→ 若 `effective_status=acknowledged` 才按主动模式继续等待/推进收尾；否则按被动、派发后结束本轮。
2. **等待轮次**：只做只读状态核对，**不重复 ACK**；发现 `ack_stale`/`expired` 立即停止主动推进。
3. **人工切换后**：旧 ACK 失效；**结束会话切 active 仍需用户唤回**（产品边界，C1b 不承诺自动唤醒 Desktop 会话）。
4. **收取/汇总前**：`collect-result` 仍只认 `created_by`，与绑定状态无关。
5. **旧会话不能覆盖新归属**：`ack`/`renew`/`release`/`force-release` 必须带 `expected_epoch`；`bind` 在**携带 `binding_token` 时必填**（缺失 → L2 422），**不携带 token 时可选且不参与判定**（§2.3.2）。`expected_epoch` 与库存不符一律 409 `controller_epoch_stale`（且仅在请求体完整、通过 L3 后判定），服务端不“猜”最新值。

---

## 5. 并发保护

### 5.1 最少必要字段、CAS 语义与原子操作（v2）

字段：`owner_epoch`（**CAS 主键之一，持久化**）、`lease_expires_at`、`heartbeat_at`、`binding_token_hash`、`state_version`（仅观测）。

**`state_version` 的准确定位（A6，回应“字段说明与实际请求 CAS 不符”）**：所有请求体都不携带 `expected_state_version`；因此实现**不得**把 `state_version` 写进 where 条件，也不得声称它承担并发保护。它只用于读侧观测（“这一行是否发生过变更”）和排障。真正的并发保护来自：

1. `binding_token_hash`（能力）+ `owner_epoch`（世代）——防止旧会话覆盖新归属；
2. `lease_expires_at`（时间窗口）——防止过期会话继续写入；
3. `projects.controller_mode_version`（配置世代）——防止用旧模式确认新模式（ACK 专用）。

所有状态变更都落在**单条条件 UPDATE**（沿用 `claim_task` / `heartbeat_task` / C1a `controller-mode` 的写法，`rowcount != 1` 即冲突/未命中），不依赖“先读后写”；`ack` 与 `projects` 的关联条件必须在**同一事务**内完成（子查询/关联条件或先在同事务读 `projects` 行再加条件）。

| 操作 | 请求体要点 | 单条条件 UPDATE 的 where | 幂等性 |
| --- | --- | --- | --- |
| `bind`（首次登记） | `{holder_label（必填）, binding_token?, expected_epoch?, instance_id?, lease_seconds?}`；**带 `binding_token` 时 `expected_epoch` 必填**（缺 → L2 422） | **INSERT**（PK=`project_id`）；`IntegrityError` → `rollback` → 重读行 → 转下表两分支 | 见 §2.3.4；无 token 时**不幂等**；无 token 时 `expected_epoch` 不参与判定（§2.3.2） |
| `bind`（接管空行/过期行） | 同上 | `project_id=? AND (owner_member_id IS NULL OR lease_expires_at IS NULL OR lease_expires_at <= now)`；**where 不含 `expected_epoch`**（无 token 时该字段不参与判定） | `rowcount=0` → 重读：活跃归属 → 409 `controller_binding_held` |
| `bind`（幂等重试） | 同上 + `binding_token`（+ 必填 `expected_epoch`，否则 L2 422，不进入本行） | **不写库**：同事务读行后按 `project_id=? AND owner_member_id=? AND owner_epoch=? AND binding_token_hash=? AND lease_expires_at IS NOT NULL AND lease_expires_at > now` 比较 | 命中 → 200 回现状，**不重发 token**，`state_version` 不变；不满足租约条件 → 409 `controller_lease_expired` |
| `ack` | `{binding_token（必填）, expected_epoch（必填）, expected_mode_version（必填）, lease_seconds?}` | `binding_token_hash=? AND owner_epoch=? AND lease_expires_at IS NOT NULL AND lease_expires_at > now` **且同事务** `projects.controller_mode='active' AND projects.controller_mode_version=expected_mode_version` | 同 `(epoch, mode_version)` 重复 ack → 200，`state_version` 不变 |
| `renew` | `{binding_token（必填）, expected_epoch（必填）, lease_seconds?}` | `binding_token_hash=? AND owner_epoch=? AND lease_expires_at IS NOT NULL AND lease_expires_at > now` | 重复 renew → 200，租约取较大值 |
| `release` | `{binding_token（必填）, expected_epoch（必填）}` | `binding_token_hash=? AND owner_epoch=? AND owner_member_id IS NOT NULL` | 重复 release → 409 `controller_not_bound`（token 已清空，无法识别同一持有者；客户端以 `GET` 状态为恢复判据） |
| `force-release` | `{expected_epoch（必填）}`；**请求体完整后**才判 human-only | `project_id=? AND owner_member_id IS NOT NULL AND owner_epoch=?` | `rowcount=1` 的那一次才 `owner_epoch+1` 并写 `last_reason='force_released'`；`rowcount=0` → 重读：`owner_member_id IS NULL` → 200 幂等**不改任何字段、不二次加 epoch、不重写 last_reason**；epoch 不同 → 409 `controller_epoch_stale`；无行 → 409 `controller_not_bound`；**缺 `expected_epoch` → L2 422（先于 403 角色判定）** |
| 懒过期回收 | 由`ack`/`renew`/`release`/`force-release`等写路径触发 | `owner_member_id IS NOT NULL AND (lease_expires_at IS NULL OR lease_expires_at <= now)` | `rowcount=0` 不视为错误；成功则 `owner_member_id=NULL`、`owner_epoch+1`、清 token 哈希、`last_reason='expired'` |

**`renew` 的“取较大租约”与 `state_version` 递增口径**：单条 UPDATE 内用 `CASE WHEN lease_expires_at > :new_expiry THEN lease_expires_at ELSE :new_expiry END` 保证只延长、不回缩；`state_version` 只在**字段值确实变化**时 +1（同一 token 的重复 `renew`（新到期时间不晚于现值）与重复 `ack` 都是 200 且 `state_version` 不变，用于验证幂等）。

**`owner_epoch` 记账规则（回应“epoch 持久化 / ABA”）**：
- `owner_epoch` 落在表内，**随行持久化**，服务重启不清零、不回收、不回绕；SQLite `INTEGER` 为 64 位，单调 +1 不会实用级别回绕。
- 每一次**归属字段的实际写入**（A→B 或 A→NULL）恰好 `+1`，由**那一条 `rowcount=1` 的 UPDATE** 完成；因此“先懒回收（+1）再 bind（+1）”在同一项目上是两次归属变更，外部只保证 **严格增大**，不承诺“每次重绑恰好 +1”。用例一律断言 `after > before`，不断言差值（首次 INSERT 除外，为 0→1）。
- **ABA 不适用**：epoch 只增不回收；任何归属变更都同时清空/替换 `binding_token_hash`，旧 token 在**任何**后续状态下都无法再次匹配（不存在“epoch 回到旧值 + 旧 token 复活”的组合）；token 明文服务端不保存，无法重签。

**`ack` 的模式版本防护（P1-1）**：`expected_mode_version` 是**必填**字段，ACK 的写路径只使用**请求携带的**版本值比对当前 `RV`，并把该值写入 `ack_mode_version`——服务端**不得**改为读取当时的 `RV` 落库。由此：
- 会话读到 `RV=3` 后 human 并发改为 4：ACK 的 where 条件不命中 → **不写** `ack_state`/`ack_mode_version` → 409 `controller_mode_changed`；不存在“读旧模式却确认新版本”的窗口。
- §4.2 第 7 行的 `ack_mode_version==RV` 因此是**事后失效检测**（用于后续模式切换），而不是唯一防线。

### 5.2 竞争场景 → 结果码（v2：包含新增的 token/模式/释放竞争）

| # | 场景 | 期望结果 |
| --- | --- | --- |
| 1 | 两会话同时 `bind` 无归属项目（首建行） | 恰好一个 201（INSERT 成功）；另一个 `IntegrityError`→`rollback`→重读→409 `controller_binding_held`；**不得产生第二行** |
| 2 | 两会话同时 `bind` 过期行 | 恰好一个 `rowcount=1` → 201；另一个 `rowcount=0` → 重读为活跃归属 → 409 `controller_binding_held` |
| 3 | 旧会话在归属变更后迟到 `ack` | 409 `controller_epoch_stale`（`owner_epoch` 先于 token 比对） |
| 4 | 旧会话迟到 `renew` | 409 `controller_epoch_stale`（同上；若归属已释放则 409 `controller_not_bound`） |
| 5 | 旧会话迟到 `release` | 409 `controller_epoch_stale`，**新归属不受影响** |
| 6 | 租约过期后另一会话 `bind` | 201；`owner_epoch` 严格增大；旧 ACK 全部失效 |
| 7 | 同一 token 并发 `renew` | 两者均 200，租约取较大值 |
| 8 | 同一 token 重复 `ack`（同 `epoch`、同 `expected_mode_version`） | 200，`state_version` 不变 |
| 9 | human 改模式（`RV+1`）与 `ack` 并发 | 一个方向 409 `controller_mode_changed`（ACK 不写库），另一个 200；**不允许**出现“ACK 版本已旧但仍记为 acknowledged” |
| 10 | human 切 `passive` 与 `ack` 并发 | ACK 侧 409（版本先变 → `controller_mode_changed`；版本未变 → `controller_mode_passive`）；两者都**不写** ack 字段 |
| 11 | 同一 token 并发 `release` ×2 | 恰好一个 200（`released`，`owner_epoch+1`）；另一个重读为 `owner_member_id IS NULL` → 409 `controller_not_bound` |
| 12 | 并发 `force-release` ×2（同 `expected_epoch`） | 恰好一次完成 `force_released` 记账（`owner_epoch+1`）；另一个 `rowcount=0`→重读 `owner_member_id IS NULL` → 200 幂等，**不改任何字段、不二次加 epoch** |
| 13 | 租约在 `ack` 瞬间过期 | `rowcount=0` → 重读分类：仍为非空过期/被懒回收 → 409 `controller_lease_expired` 或 409 `controller_not_bound`；两者都要求客户端重新 `bind` |
| 14 | 首次 201 响应丢失后的裸重试 `bind`（无 token） | 409 `controller_binding_held`；**不返回、不重建 token**（§2.3.5） |
| 15 | ABA（epoch 回绕） | **不适用**：epoch 持久化、单调 +1、不回收；归属变更即清/换 token 哈希，旧 token 永不复活 |
| 16 | 服务重启 | 绑定与哈希仍在；未过期可续租；过期派生 `expired` |
| 17 | 客户端进程死亡（无心跳） | 派生 `expired`；无后台清理；下一次写操作懒回收（落库 `last_reason='expired'`） |
| 18 | 只读 `GET` 并发 | 零写入（测试断言数据库无变更） |

### 5.3 “状态登记互斥” ≠ “实际副作用隔离”

- 本设计提供：**服务端单一归属登记 + 陈旧写入拒绝 + 状态可见 + 显式接管路径**。
- 本设计**不提供**：阻止旧会话继续用同一 API Key 调 `talk_delegate_task`、`talk_reply_task`、`talk_cancel_task`、`talk_send` 等既有写工具。探针 A–F 已证明同 member 的任意进程共享全部权限。
- 因此**不得宣称“已完全防双主控”**。真正的副作用隔离需要**按会话降权的凭证**（项目范围 + 主控范围 token，或 per-session 二次授权），属于新鉴权层，明确留作 C1b-3+ 的独立评估，不在本批承诺。

---

## 6. 向后兼容

### 6.1 旧客户端

- 旧客户端**不调用**新工具时，行为与现在**完全一致**：`controller_mode` 仍只是意向，`effective_mode=null`，被动协作不变。
- 现有 9 个 MCP 工具（`talk_list_agents` … `talk_get_delivery`）的**入参不变**；`talk_list_agents.controller_mode` 只做**加字段**（新增 `binding` 子对象），旧消费者忽略即可。
- 旧 bridge 的实例上报、claim/heartbeat/complete、预算与门禁协议**不改**。
- 只读工具（`talk_list_agents` / `talk_get_task` / `talk_get_delivery` / 新 `talk_controller_status`）保持纯 `GET`（探针 H 目前只是**短路桩方法序列**证据；C1b-1 必须补**真实 HTTP** 同款断言）。
- 错误码兼容：新增 `controller_*` 码全部落在**新端点**上；`detail` 仍是字符串（§7.3），既有客户端的字符串解析不受影响。

### 6.2 新 API / SDK / MCP 工具

| 项 | 结论 |
| --- | --- |
| REST | **新增**子资源 `/{project_id}/controller[...]`，**不改**已有路由签名与错误码 |
| SDK `TALK/client/` | 可扩展现有客户端：新增 5 个薄方法（`get_controller_binding` / `bind_controller` / `ack_controller` / `renew_controller` / `release_controller`）。**非必须**：REST 可先用 |
| MCP | **必须新增**：`talk_controller_status`（只读）+ `talk_controller`（`action=bind|ack|renew|release`）。工具总数 9 → 11 |
| 显式绑定客户端如何遵守 owner 校验 | `bind` 通过 `binding_token?` + `expected_epoch?`（**带 token 时 `expected_epoch` 必填**）；`ack`/`renew`/`release` 通过**必填** `binding_token` + `expected_epoch`（`ack` 另加必填 `expected_mode_version`）；字段不全的调用方在 **L2 统一 422**、**永远走不到**写路径，其余路径由 L4 409 兜底，不需要改造旧委派/收取 |
| MCP 层对 ACK 的约束 | `talk_controller` 的 `ack` **要求调用方显式传入** `expected_mode_version`；若工具层代为读取，必须使用**同一次读取**的值，并在 409 时如实上报，**禁止静默重取版本后自动重试**（防止把“读旧模式确认新版本”变成自动通过） |

### 6.3 诚实分层目标（不虚假承诺）

| 层 | 交付 | 保证 | 不保证 |
| --- | --- | --- | --- |
| **L1（C1b-1）** | 登记 + ACK + 租约 + 只读状态 + 诚实文案 | 服务端单项目单归属；陈旧/越权写入被拒；状态可被任何认证成员读到 | 不影响任何任务副作用；不阻止旧会话继续派发 |
| **L2（C1b-2）** | 接管策略、审计事件、过期可见性、派发前**建议性**提示 | 归属变更可追溯；`active` 且无 `acknowledged` 时给调用方明确警告 | 仍不阻断；仍不自动唤醒 |
| **L3（未排期）** | 会话级降权凭证（scope token） | 才可能真正隔离副作用 | 本批**不做**，不承诺 |

若无法用小改保证 L2 的“不破坏旧委派/收取”，则应停在 L1 并把差距写清楚。

---

## 7. 接口、字段与错误码草案 / DB 迁移 / 宿主指令

### 7.1 REST 草案（C1b-1，v2）

| 方法 | 路径 | 权限 | 请求 | 响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/projects/{pid}/controller` | 任意已认证成员（与既有项目读口径一致，§1.1） | — | `ControllerBindingOut`（含派生 `effective_status`），**零写入** |
| `POST` | `/api/projects/{pid}/controller/bind` | 见 A1/D1 与 §3.2 | `{holder_label（必填）, binding_token?, expected_epoch?, instance_id?, lease_seconds?}`；**带 `binding_token` 时 `expected_epoch` 必填（缺 → 422）** | 201 首次 / 200 幂等：`{binding, binding_token}`（**token 仅 201 且仅此一次**；200 幂等**不含** token） |
| `POST` | `/api/projects/{pid}/controller/ack` | token 持有者（**请求体完整后**判角色/能力） | `{binding_token, expected_epoch, expected_mode_version, lease_seconds?}`（三者必填，缺任一 → 422，**与调用者角色无关**） | 200 `binding` |
| `POST` | `/api/projects/{pid}/controller/renew` | token 持有者（同上） | `{binding_token, expected_epoch, lease_seconds?}`（前两者必填，缺任一 → 422） | 200 `binding` |
| `POST` | `/api/projects/{pid}/controller/release` | **仅** token 持有者（同上） | `{binding_token, expected_epoch}`（两者必填，缺任一 → 422；无 token 的 human 应改用 `force-release`，该引导**仅在响应文案/用户说明**） | 200 `binding`（released） |
| `POST` | `/api/projects/{pid}/controller/force-release` | **human only（请求体完整后判定）** | `{expected_epoch}`（必填，缺 → 422） | 200 `binding`（released / 幂等） |

- `lease_seconds` 约束与任务租约对齐：`5..3600`，默认 `120`（`server/models.py:781-783` 定义 `TASK_LEASE_*`；`models.py:913-919` 为既有字段校验先例）。
- `instance_id` 校验沿用 `_ensure_instance_owner`（`server/routes/tasks.py:1111`）：不存在 → 400 `instance_id not found`；属于他人 → 403 `instance belongs to another member`。
- 首次登记的 `bind` 是 **INSERT**；并发唯一键冲突按 §5.2#1 映射为 409，不当 500（P3-4）。

### 7.2 `ControllerBindingOut`（同时作为 MCP `talk_list_agents.controller_mode.binding`）

```
{
  "project_id": "prj_...",
  "bound": true,
  "owner_member_id": "agent:kimi",
  "owner_display_name": "...",
  "holder_label": "cs_9f2c...",
  "instance_id": "agent:kimi:<uuid>" | null,
  "owner_epoch": 3,
  "state_version": 11,
  "state_version_note": "仅观测计数器，不参与并发校验",
  "ack_state": "acknowledged",
  "ack_at": "...", "ack_epoch": 2, "ack_mode_version": 4,
  "heartbeat_at": "...", "lease_expires_at": "...", "lease_seconds_remaining": 74,
  "bound_at": "...", "updated_at": "...",
  "last_reason": null,
  "last_reason_note": "最近一次写路径落库原因；纯读派生 expired 不会改写它",
  "effective_status": "acknowledged",
  "evidence_note": "ACK 仅表示确认读取并承诺遵循，不代表模型正在运行或会被唤醒"
}
```

**绝不返回** `binding_token`（除 `bind` 201 那一次）、`binding_token_hash`、其它项目的绑定行。

### 7.3 校验分层与错误码草案（v3：R1 定向统一，422 为先、无重复归类）

**适用范围（#108 明确，防止越界）**：本节 L0–L4 **只描述新增端点** `/{pid}/controller[...]` 的判定顺序，**不修改、也不重新描述**既有任务 / 消息 / 项目端点的 401/403/422 行为。既有全局约定（`get_current_member` 的 401、`_require_human` 的 403、FastAPI/Pydantic 的 422）保持原样，本设计既不扩大也不调整其顺序。

**`detail` 形状（A7）**：与既有实现一致，`detail` 是**字符串**，控制器错误以稳定码开头：`controller_xxx` 或 `controller_xxx: k1=v1, k2=v2`。依据：现有端点全部使用字符串 detail（`messages.py:303-312` 直接用裸码；`projects.py:401-410` 用“英文短语 + k=v”）；MCP 侧 `bridges/talk_task_tools.py:146-152` 会把 `detail` 直接格式化进错误文本，对象型 detail 会被字符串化成 Python dict。**不引入对象型 detail，也不改既有端点。**

**校验分层（自上而下，第一层命中即返回，不再继续判断）**：

| 层 | HTTP | 触发 | 说明 |
| --- | --- | --- | --- |
| L0 认证 | 401 | 缺少/无效 `X-API-Key`（沿用既有 `Invalid API key`） | 不进入业务判断 |
| L1 资源 | 404 | 项目不存在（沿用既有 `project not found`） | 先于任何写入 |
| L2 请求体校验 | **422** | `holder_label` 缺失/不合 `cs_[A-Za-z0-9_-]{8,64}`；`ack` 缺 `binding_token`/`expected_epoch`/`expected_mode_version`；`renew`、`release` 缺 `binding_token`/`expected_epoch`；`force-release` 缺 `expected_epoch`；**`bind` 携带 `binding_token` 却缺 `expected_epoch`**；`lease_seconds` 越界 5..3600；类型/范围错误 | 由 Pydantic 模型承担（与 `AgentTaskClaim` 同风格；跨字段条件用 `@model_validator(mode="after")` + `raise ValueError` 先例见 `models.py:921-925/936-941/1287-1293`）。**该层角色盲：缺字段一律 422，与 human/agent 身份无关，所以 human 无 token 时必然先命中本层** |
| L3 授权 | **403** | `controller_not_authorized`：**请求体完整且到达本层后**——名册外 agent 调 `bind`（A1）；非 human 调 `force-release` | 身份/角色不满足，与 token 正确性无关。**v2 的“无 token 的 human 调 `ack`/`renew`/`release` → 403”已删除**（R1：在 L2 先于 L3 的分层下不可达） |
| L4 状态与能力 | **409** | 见下表（按固定优先级判定） | token/epoch/租约/模式 |

**409 判定优先级（同一请求只返回一个码）**：
`controller_not_bound` → `controller_epoch_stale` → `controller_token_invalid` → `controller_lease_expired` → `controller_mode_changed` → `controller_mode_passive` → `controller_binding_held`。

| HTTP | `detail` 稳定码 | 触发（唯一定义） | C2 文案建议 |
| --- | --- | --- | --- |
| 409 | `controller_not_bound` | 无绑定行，或 `owner_member_id IS NULL`（已释放），而请求要求持有者身份（`ack`/`renew`/`release`）；`force-release` 遇到无行 | 尚未登记主控会话，请重新绑定 |
| 409 | `controller_epoch_stale` | 请求 `expected_epoch` 落后于库存 `owner_epoch` | 主控归属已变更，请重新读取状态 |
| 409 | `controller_token_invalid` | 请求携带的 token 与库存哈希不符，或库存哈希已清空/已替换 | 当前会话令牌无效，请重新绑定 |
| 409 | `controller_lease_expired` | 租约为空或已过期，仍尝试 `ack`/`renew`/`release`（或 token 有效但归属已过期） | 主控会话已过期 |
| 409 | `controller_mode_changed` | `ack` 的 `expected_mode_version != 当前 RV` | 项目模式已变更，请重新确认 |
| 409 | `controller_mode_passive` | `ack` 时 `RV` 相符但 `controller_mode=passive` | 项目当前为被动模式，无需确认；切到主动后再确认 |
| 409 | `controller_binding_held` | 存在**活跃**归属且请求方不是持有者（含无 token 的首建/接管尝试、首次 201 丢失后的裸重试） | 该项目已有主控会话，需先释放或由人工处理 |
| 403 | `controller_not_authorized` | 见 L3：**请求体完整后**才判定；非 human 调 `force-release`；名册外 agent 调 `bind`。**不含“human 无 token 调 `ack`/`renew`/`release`”**（该场景落在 422） | 无权限操作该项目主控 |
| 422 | 校验错误（FastAPI 默认结构） | 见 L2：**缺任一必填字段即命中，与角色无关**；含 human 无 token 调 `ack`/`renew`/`release`、`bind` 带 token 缺 `expected_epoch` | 参数不合法 |
| 401 / 404 | 沿用既有 | 未认证 / 项目不存在 | 沿用既有 |

**同时满足多条件时的例子（实现与测试都必须一致，v3 按 R1 改写）**：
- 同 member 另一会话**不带** token 调 `ack` → **422**（缺 `binding_token`）；**带错误** token → **409 controller_token_invalid**；**带正确** token → 它是持有者，**200**。§8.1 旧用例 4 的 403 归类作废（P2-1）。
- 无 token 的 human 调 `release`/`ack`/`renew` → **422**（缺必填字段，角色盲），不会成功、也不会写成 `released`（P2-2）。它和“同 member 无 token 会话”“名册内其他 agent 无 token”得到**同一个** 422；差异只在响应文案（human 文案额外提示“如需强制释放请用 `force-release`”），**文案不改变状态码**。
- human 带**错误 token** 调 `release` → **409 controller_token_invalid**（请求体完整 → 过 L3 → 在 L4 命中 token 校验）；只在**到达 token 校验**时才返回该码，**不是一律 409 压过更早的检查**：缺字段仍是 422，epoch 落后仍是 409 `controller_epoch_stale`。
- 旧 token + 旧 epoch + 模式已变 → **409 controller_epoch_stale**（epoch 优先于 token、优先于模式）。
- 非 human 调 `force-release` 且**请求体完整** → **403 controller_not_authorized**；缺 `expected_epoch` → **422**（先于 403）。两者都被拒，不存在“先 403 还是先 422”的歧义，见 §7.3.1。

#### 7.3.1 决策表（端点 × 角色 × 必填字段完整性 × 前置条件 → 首个命中层 → 预期错误）

本表是 §3.2 矩阵、§7.1 请求体、§7.3 分层与 §8.1 用例之间的**唯一裁决口径**：任一处条款与用例若与本表不一致，以本表为准并同步修订。`字段完整性` 指“本端点全部必填字段是否齐备且通过 L2 校验（含 `bind` 的 `expected_epoch` 条件必填）”。

| 端点 | 角色/会话 | 字段完整性 | 其它前置条件 | 首个命中层 | 预期错误 | 库变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 任意 | 未认证 | — | 无有效 API Key | L0 | 401 `Invalid API key`（既有） | 无 |
| 任意 | 已认证 | — | 项目不存在 | L1 | 404 `project not found`（既有） | 无 |
| `bind` | 任意已认证 | 缺 `holder_label` / 值不合规 | — | L2 | **422** | 无 |
| `bind` | 任意已认证 | 带 `binding_token` 但缺 `expected_epoch` | — | L2 | **422** | 无 |
| `bind` | 名册外 agent | 完整 | 名册外（A1） | L3 | **403 `controller_not_authorized`** | 无 |
| `bind` | human / 名册内 agent | 完整、无 token | 无归属行 → INSERT；空/过期行 → 条件 UPDATE | L4 | 201（首次）/ 200（接管） | 新增行 / 归属+epoch 变更 |
| `bind` | human / 名册内 agent | 完整、无 token | 归属**活跃** | L4 | **409 `controller_binding_held`** | 无 |
| `bind` | 合法持有者 | 完整、带 token + `expected_epoch` | member+epoch+hash 三元组匹配且租约有效 | L4 | 200（幂等，**不回传 token**，`state_version` 不变） | 无 |
| `bind` | 任意已认证 | 完整、带 token | epoch 落后 | L4 | 409 `controller_epoch_stale` | 无 |
| `bind` | 任意已认证 | 完整、带 token | epoch 相符但 hash 不符/已清空 | L4 | 409 `controller_token_invalid` | 无 |
| `ack` | **human（无 token）** | **不完整（缺 `binding_token`/`expected_epoch`/`expected_mode_version`）** | — | **L2** | **422**（**不是 403**） | 无 |
| `ack` | 同 member 其他会话 / 名册内其他 agent（无 token） | 不完整 | — | L2 | 422 | 无 |
| `ack` | 持有者 | 完整 | epoch 落后 | L4 | 409 `controller_epoch_stale` | 无 |
| `ack` | 持有者 | 完整 | epoch 相符、hash 不符 | L4 | 409 `controller_token_invalid` | 无 |
| `ack` | 持有者 | 完整 | 租约 NULL/过期 | L4 | 409 `controller_lease_expired` | 无 |
| `ack` | 持有者 | 完整 | 租约有效、`expected_mode_version != RV` | L4 | 409 `controller_mode_changed` | 无 |
| `ack` | 持有者 | 完整 | 版本相符但 `R=passive` | L4 | 409 `controller_mode_passive` | 无 |
| `ack` | 持有者 | 完整 | 全条件满足 | L4 | 200（`acknowledged`） | 写 ack 字段 |
| `renew` | **human（无 token）** | 不完整（缺 `binding_token`/`expected_epoch`） | — | **L2** | **422**（**不是 403**） | 无 |
| `renew` | 持有者 | 完整 | 租约过期 → 懒回收后重读 | L4 | 409 `controller_lease_expired` / `controller_not_bound` | 可能落 `last_reason='expired'` |
| `renew` | 持有者 | 完整 | 租约有效 | L4 | 200（租约取较大值） | 租约/心跳 |
| `release` | **human（无 token）** | 不完整（缺 `binding_token`/`expected_epoch`） | — | **L2** | **422**（**不是 403**；文案引导 `force-release`） | 无 |
| `release` | 持有者 | 完整 | hash/epoch 匹配、`owner_member_id IS NOT NULL` | L4 | 200（`released`） | 释放+epoch+清 hash |
| `release` | 原持有者（陈旧） | 完整 | epoch 落后 | L4 | 409 `controller_epoch_stale` | 无 |
| `force-release` | 任意已认证 | **缺 `expected_epoch`** | — | **L2** | **422**（先于角色判定） | 无 |
| `force-release` | **非 human（agent）** | 完整 | 到达 L3 | **L3** | **403 `controller_not_authorized`** | 无 |
| `force-release` | human | 完整 | 归属活跃、epoch 相符 | L4 | 200（`force_released`，epoch+1） | 释放+epoch+清 hash |
| `force-release` | human | 完整 | 已释放（`owner_member_id IS NULL`） | L4 | 200（幂等，**零字段变化**） | 无 |
| `force-release` | human | 完整 | epoch 落后 | L4 | 409 `controller_epoch_stale` | 无 |
| `force-release` | human | 完整 | 无绑定行 | L4 | 409 `controller_not_bound` | 无 |
| `GET .../controller` | 任意已认证 | — | — | — | 200（派生状态） | **零写入** |

### 7.4 DB 迁移策略与回滚（P3-1）

- **新增表**（`project_controller_bindings`）优先于给 `projects` 加列：建表走 `SQLModel.metadata.create_all` / `init_db()` 幂等路径；老库增列先例见 `server/db.py:278-287`（C1a），不重建表、不动既有行。
- 旧库升级后：无绑定行 ⇒ 全部项目自然落 `not_bound`，与当前行为一致。
- **回滚（修订 P3-1）**：默认回滚＝**停用新路由/新 MCP 工具并保留数据**（老客户端本就不调用新端点，停用即恢复原行为）。**不采用“删表即可”**：删表会丢失绑定历史并让 `owner_epoch` 归零，存在旧 token 在新 epoch 下语义混淆的风险。确需删表时，必须由 human 显式决策并在**先归档**（导出该表内容）之后执行。
- 不引入后台任务/定时器（`init_db` 里不加 sweeper）。

### 7.5 让外部宿主认识并调用

| 渠道 | 内容 | 诚实边界 |
| --- | --- | --- |
| MCP 工具描述 | `talk_controller_status` / `talk_controller` 的 `description` 写明“ACK 不等于运行、绑定不等于授权、必须显式 renew、ACK 必须携带读到的模式版本” | 工具描述存在**不等于**模型会调用或遵守 |
| `docs/guides/TERMINAL_MCP.md` | 新增“主控会话合同”小节 + 每个终端的配置步骤 | Kimi 会话中改配置只对新会话生效；DSH 的 `mcpServers` 按会话声明 |
| bridge 系统提示 | 仅在显式启用主控的会话里注入简短合同 | 提示词约定不保证零续行、不覆盖宿主指令 |
| `talk_list_agents` 顶层 | 加 `binding` 只读字段，让派发方在派发前就能看到状态 | 不写 ACK、不续租、不产生副作用 |

---

## 8. 推荐切片

### 8.1 C1b-1（一个可审查切片）

**范围**

1. 新表 `project_controller_bindings` + `init_db()` 幂等建表。
2. 服务层：`bind` / `ack` / `renew` / `release` / `force-release` / 懒过期，全部单条条件 UPDATE；首建 INSERT 冲突映射（§5.2#1）。
3. REST：§7.1 的六个端点（不含 `takeover`）。
4. MCP：`talk_controller_status`（只读）+ `talk_controller`（`bind|ack|renew|release`）；`talk_list_agents.controller_mode.binding` 加字段。
5. 测试（下表用例 1–24 对应的自动化用例）+ `.tmp/c1b-1/` 接口文档。

**不变项（硬约束）**
- 不改任务授权/预算/parent/epoch/门禁/收取/取消语义；不改 `claim_token` 合同。
- 不改 C1a `PATCH controller-mode` 的 CAS、权限、错误码。
- 项目默认仍 `passive`；`effective_mode` 只在派生状态下为 `active`，**不写库**。
- 现有 9 个 MCP 工具输入输出语义不变；只读工具保持纯 `GET`。
- 不新增后台任务/调度/唤醒；不启停服务；不改真实项目配置。

**验收用例（v2 起新增/改写项标注修订来源；**#108 追加用例 25/26**）**

| # | 用例 | 期望 |
| --- | --- | --- |
| 1 | 无归属项目 `bind` | 201，返回 token 与 `owner_epoch=1`（首次 0→1） |
| 2 | 同项目第二次 `bind`（另一会话、无 token） | 409 `controller_binding_held` |
| 3 | 持 token `ack`（active，`expected_mode_version=RV`） | 200，`effective_status=acknowledged`，`ack_mode_version==RV` |
| 4 | **（P1-1）** `ack` 缺 `expected_mode_version` | 422，库无变化（`ack_*` 与 `state_version` 均不变） |
| 5 | **（P1-1）** `ack` 带**过期** `expected_mode_version`（human 已 `RV+1`） | 409 `controller_mode_changed`；`ack_state` 仍 `none`、`ack_mode_version` 未被写成当前 `RV`（“读旧模式不能确认新版本”） |
| 6 | **（P3-5/A4）** `passive` 下调 `ack` | 409 `controller_mode_passive`，库无变化；派生状态仍 `bound_passive` |
| 7 | **（P2-1）** 同 member 另一会话：不带 token → 422；带错误 token → 409 `controller_token_invalid`；带正确 token → 200 | 三种输入三种结果，且**不再出现 403 归类** |
| 8 | **（P2-2 / R1 改写）** 无 token 的 human 调 `release`、`ack`、`renew` | 三者均 **422**（缺必填字段，角色盲），库无变化，`last_reason` 不变；`release` 的响应文案含“改用 `force-release`”**引导文本**，但状态码与 agent 无 token 时**相同**；不再承诺 403 |
| 9 | **（P2-2）** human 调 `force-release` | 200，`owner_member_id=null`，`owner_epoch` 严格增大，`last_reason='force_released'` |
| 10 | **（P2-2）** human 作为合法 holder（自己 bind 的会话、持 token）调 `release` | 200，`last_reason='released'`（**权限与 v2 一致，未因 R1 收紧**） |
| 11 | **（P1-2）** 持同 token + 同 member + 同 epoch 重复 `bind` | 200 回现状，**响应不含 token**，`state_version` 不变 |
| 12 | **（P1-2）** `bind` 带错误 token / 带旧 `expected_epoch` | 409 `controller_token_invalid` / 409 `controller_epoch_stale` |
| 13 | **（P1-2）** 首次 201 响应丢失：仅凭相同 `holder_label` 裸重试 `bind` | 409 `controller_binding_held`，**响应不含 token**；租约过期后再 `bind` → 201 新 token 且 `owner_epoch` 严格增大 |
| 14 | `active → passive → active` 后读状态 | 中间为 `bound_passive`；切回后为 `ack_stale`（`RV` 已推进） |
| 15 | `renew` 延长租约 | 200，`lease_expires_at` 前移 |
| 16 | 租约过期后读 | 派生 `expired`，且 **GET 不写库**（`last_reason` 不变） |
| 17 | 过期后另一会话 `bind` | 201，`owner_epoch` 严格增大，旧 token 失效 |
| 18 | 旧 token `renew`/`ack`/`release` | 全部 409（`controller_epoch_stale`），新归属不变 |
| 19 | **（P3-4）** 两会话同时首次 `bind` | 恰好一个 201、一个 409 `controller_binding_held`；表内仍只有一行 |
| 20 | **（P2-2 并发）** 并发 `force-release` ×2 | 恰好一次 `force_released` 记账与一次 epoch 增大；另一次 200 幂等且字段零变化 |
| 21 | **（P2-2 并发）** 并发同 token `release` ×2 | 恰好一个 200（`released`），另一个 409 `controller_not_bound` |
| 22 | 跨项目隔离与跨项目读 | A 项目绑定不影响 B；任意已认证成员可读 A/B 各自一行（与 §1.1 读口径一致） |
| 23 | 只读工具方法序列 | 仅 `GET`（复用探针 H 断言，但 **C1b-1 必须补真实 HTTP 版本**） |
| 24 | 旧客户端回归 + 并发矩阵 | 现有 9 工具与任务/门禁测试全绿；§5.2 全 18 项与表一致 |
| 25 | **（#108 关联小项 1）** `bind` 携带 `binding_token` **但缺 `expected_epoch`**；以及无 token 首绑分别**省略 / 携带** `expected_epoch` | 第一种 → **422**（库无变化，不误判为 409 `controller_binding_held`）；后两种 → 结果相同（201 或按归属状态 409 `controller_binding_held`），响应 `owner_epoch` 为权威新值 |
| 26 | **（#108 关联小项 2）** 非 human 调 `force-release`：请求体**完整** vs **缺 `expected_epoch`** | 完整 → **403 `controller_not_authorized`**；缺字段 → **422**（先命中 L2）；两者库均无变化 |

**可隔离验证**：以上 1–24 全部可在隔离临时库 + `TestClient` 完成（含并发线程竞争）；但都属**进程内**证据。

**必须真实终端验证（不能由隔离测试替代）**：
- 真实宿主（Kimi Code / DSH ACP / WorkBuddy / Codex Desktop）是否在**同一原生会话**内重复使用同一 `holder_label`；
- 同一 member **两个真实并发进程/会话**是否真的一个拿到 200、另一个拿到 409（含首次 201 丢失场景）；
- ACK 是否由**模型**发起而非操作者手写；
- WorkBuddy 用户级 MCP 是否**一个进程服务多个对话**（会让 holder_label 语义失真）。
- 这些在 C1b-1 完成、用户唤回后单独排片，不在隔离测试里伪造通过。

### 8.2 C1b-2（依赖 C1b-1）

`takeover` 策略落地（含 A1/D1 裁决结果）、`project_controller_events` 追加式审计、`project_controller_bindings` 的状态变更历史可读、派发前**建议性**提示字段（不阻断）、面向页面的项目级读接口。

### 8.3 C2（依赖 C1b-1/2）

主动/被动按钮、状态胶囊（§4.2 文案）、确认弹窗（“ACK 不代表运行”）、错误码文案映射、切换节点提示。**不得**只把 C1a 意向字段渲染成“已生效”。

---

## 9. 需要项目管理者 / Codex 裁决的关键问题（3 项，本稿按 A1–A3 假设书写）

### D1 首次绑定与接管的授权范围（**权限变更，含潜在破坏性**）

- **推荐（＝A1）**：C1b-1 只允许「human 无条件 `bind`/`force-release`」+「agent 成员在其 `ProjectAgent` 名册内的项目 `bind`（仅无归属/已过期时）」。**agent 间接管（同 member 新会话、跨 member）全部推到 C1b-2**，并要求 human 批准或 human 亲自执行。
- **理由**：不新增“项目成员制”，不因 `lead` 标签或模型名升权；把最有争议的接管路径隔离到一个可单独审查的切片。
- **备选**：①完全 human-only 绑定（最保守，但 active 模式几乎每次都要人工点击）；②允许任意 agent 在项目空闲时绑定（最省事，但等于把项目主控登记开放给所有 agent 成员）。
- **破坏性标注**：选项②会扩大现有 agent 权限边界；选项①会显著改变现有“派发即走”的自动化体验。二者都必须由人明确选择。
- **状态**：本稿所有 `bind` 权限条款都按推荐假设写；**未获确认前不得实施**（§0 A1）。

### D2 是否让 `active` 模式影响任务派发/收取入口（**破坏性变化**）

- **推荐（＝A2）**：**不**影响。`talk_delegate_task`、`claim`、`complete`、`collect-result`、门禁全部保持现状；`active` 且无 `acknowledged` 绑定时只在 `talk_list_agents` 增加**只读提示字段**（如 `binding_warning`），不阻断其他成员派发或收取。
- **理由**：探针 E 已证明项目不是认证边界；若用主控绑定阻断派发，会立刻破坏其他角色与旧客户端，并与“不能让主控归属自动获得他人任务权限”的既定边界冲突。
- **备选**：`active` 时要求派发方持有 `acknowledged` 绑定——**明确标记为破坏性**，需单独切片 + 用户授权 + 兼容期。

### D3 服务重启 / 进程死亡后的归属语义与是否引入后台清理（**运行语义**）

- **推荐（＝A3）**：绑定与 `binding_token_hash` **持久化**；重启后不批量清空，未过期可继续 `renew`，过期派生 `expired`；**不新增后台 sweeper**，过期只在写路径懒回收（沿用 `_try_requeue_expired_task` 的既有模式）。
- **理由**：与 SQLite 持久化语义一致；避免引入新的常驻线程（当前项目明确无后台清理线程）；懒过期已足够支撑 UI 与状态判断。
- **备选**：启动时清空所有绑定（更“干净”，但会让重启后的旧会话全部失效，且需要额外的启动副作用与回滚设计）。

---

## 10. 自检与未验证项

### 10.1 合同自检

| 检查 | 结论 |
| --- | --- |
| 是否与 C1a 现状一致（意向≠生效、`effective_status=not_bound`） | ✅ 未改 C1a，仅建议在其上叠加绑定 |
| 是否避免用模型名/标签认身份 | ✅ `owner_member_id` 只来自 API Key；`holder_label`/`instance_id` 明确降级为标签，且不参与幂等判定 |
| ACK 是否无法“读旧模式确认新版本” | ✅ `expected_mode_version` 必填 + 同请求 CAS（§5.1/§7.1/用例 5） |
| bind 幂等是否有明确载体与恢复规则 | ✅ `binding_token` 可选字段 + 三元组判定 + 201 丢失的两条恢复路径（§2.3.4/§2.3.5） |
| 缺失/错误 token 是否只有一种归类 | ✅ 缺必填字段一律 L2 422（**与角色无关，含 human 无 token**）/ 请求完整后 token 与库存不符 L4 409 `controller_token_invalid`（仅在到达 token 校验时）；v2 的“human 无 token → 403”承诺已删除，见 §7.3、§7.3.1、用例 7/8 |
| 释放是否双路径重叠 | ✅ `release` 仅 token 持有者；无 token 的 human 只能 `force-release`（其请求在 L2 被 422 提前阻断，引导仅在文案）；并发记账唯一（§3.2、§5.2#11/#12） |
| 校验分层是否可达（R1 自检） | ✅ §7.3.1 按“端点 × 角色 × 字段完整性 × 前置条件 → 首个命中层”逐格填写，且与 §3.2 矩阵、§7.1、§8.1 用例同码；**不带 token 的 human 不存在任何 403 承诺** |
| 是否破坏既有任务/门禁/收取 | ✅ §3.3 逐条列出并保持 |
| 是否承诺零续行/自动唤醒 | ✅ 明确不承诺 |
| 是否把 nonce 包装为宿主身份 | ✅ §2.6 明令禁止 |
| 是否一次实现整个方案 | ✅ 只给 C1b-1 单片 |
| 是否虚构验证 | ✅ 隔离探针实跑并如实标注“进程内模拟/短路桩”；真实终端项列为必须另测 |
| epoch/ABA 与 state_version 表述是否与实现一致 | ✅ epoch 持久化+单调+严格增大（不断言差值）；`state_version` 明确为观测计数器，不入请求、不入 where（§2.2/§5.1） |

### 10.2 未实现 / 未验证（不得当成已完成）

1. 本轮**没有**任何代码/数据库/API 行为改动；`GET /api/projects/{id}/controller` 现在返回 404（探针 I）。
2. **同 member 两真实并发会话/进程从未实测**；探针 A/B/F 均为**同进程模拟**；本设计的会话区分依赖 `binding_token`，其真实宿主行为需 C1b-1 后由真实终端验证。
3. 探针 H 是**短路桩方法序列**，不是真实 HTTP 观察；真实 HTTP 的只读零写入断言在 C1b-1 补齐。
4. 客户端是否会稳定复用同一 `holder_label`（同一原生会话内）**未知**。
5. WorkBuddy 用户级 MCP 是否单进程服务多对话**未知**；Kimi 会话中配置变更只对新会话生效（文档已写）。
6. 无后台 sweeper 属既有事实，本设计不新增；长期无活动的过期状态只能靠派生显示。
7. `groups.metadata.roles` 在数据库 schema 中**不存在**（只有 `GroupMember.business_role` / `ProjectAgent.business_role`），业务角色不作为本设计的权限来源。
8. WS/SSE 不检查 `disabled_at` 属既有差异，本设计不处理。
9. 跨进程/跨主机真并发未验证（现有并发覆盖为单进程多线程 + SQLite WAL）。
10. **本稿不解决** L3 的副作用隔离（§5.3），也不承诺自动唤醒；C2 前端仍未实现。

---

## 11. 逐项修订对照（回应 #105 的四项必修 + 五项 P3 + 证据口径；#108 追加 R1 定向修订见 §11.1）

| 编号 | #105 结论要点 | 本稿位置 | 修订方式 |
| --- | --- | --- | --- |
| P1-1 | `ack` 缺 `expected_mode_version`，CAS 承诺不可实现 | §2.2、§4.1、§4.3、§5.1（`ack` 行 + 模式版本防护段）、§6.2、§7.1、§7.3、§8.1 用例 3/4/5、§5.2#9/#10 | 新增**必填** `expected_mode_version`（缺失 422）；where 用**请求携带值**比对 `RV`，成功时把它写入 `ack_mode_version`；版本不符 409 `controller_mode_changed`；新增“读旧模式不能确认新版本”用例 |
| P1-2 | `bind` 幂等无 token 载体、201 丢失不可恢复 | §2.3.4、§2.3.5、§2.3.7、§2.5、§5.1（`bind` 三行）、§5.2#14、§7.1、§8.1 用例 11/12/13 | `bind` 增加可选 `binding_token`；只认「同 member + 同 epoch + 哈希匹配」三元组；200 幂等**不回传 token**；明文禁止凭 `holder_label`/`instance_id` 认领或取回秘密；给出“等租约到期”或“human force-release”两条恢复路径 |
| P2-1 | 缺失/错误 token 的 403/409 归类冲突 | §7.3（分层 L2/L3/L4 + 优先级 + §7.3.1 决策表）、§3.2、§8.1 用例 7 | 统一为：缺字段 422；token 与库存不符/已清空 409 `controller_token_invalid`；有效凭证但无角色权限 403 `controller_not_authorized`；并声明同一请求只返回一个码及判定优先级。**#108 再修订**：403 只在请求体完整且到达 L3 时返回；缺字段一律 422（参见 R1 行） |
| P2-2 | `release` 与 `force-release` 双路径重叠 | §3.2、§4.3、§5.1（`release`/`force-release` 行）、§5.2#11/#12、§7.1、§8.1 用例 8/9/10/20/21 | `release` 仅 token 持有者且 `binding_token`+`expected_epoch` 必填；无 token 的 human 在 L2 被 **422** 阻断并改走 `force-release`（记账 `force_released`；引导仅在文案层）；human 本人为合法 holder 时按 holder 路径；并发记账唯一（只有 `rowcount=1` 的那次 +1 并写 `last_reason`）。**#108 再修订**：v2 的 403 承诺删除（R1） |
| P3-1 | 回滚不应轻率删表 | §7.4 | 默认回滚＝停用新路由/工具、保留数据；删表需 human 显式决策且先归档；说明删表会让 `owner_epoch` 归零的语义风险 |
| P3-2 | `last_reason='expired'` 只在写路径落库 | §2.2、§4.3、§7.2 | 明确 `last_reason` 是“最近一次写路径落库原因”，纯读 GET 不改写；派生 `expired` 与 `last_reason` 可同时不一致；输出字段加注 |
| P3-3 | `ack` 的 `lease_expires_at IS NULL` 分支语义未定义 | §2.2、§4.2 第 4 行、§5.1、§5.2#13 | `bind` 必写非空租约；NULL 归入派生 `expired`；`ack`/`renew`/`release` 的 where 改为 `lease_expires_at IS NOT NULL AND lease_expires_at > now`，NULL 一律按过期处理（409 `controller_lease_expired` / `controller_not_bound`） |
| P3-4 | 首建行是 INSERT，唯一键冲突未映射 | §5.1（`bind` 首建行）、§5.2#1、§7.1、§8.1 用例 19 | 明确 `IntegrityError` → `rollback` → 重读 → 活跃归属 409 `controller_binding_held`（或转 UPDATE 分支，最多一次）；要求自动化用例断言“只有一行、无 500” |
| P3-5 | passive 下 `ack` 行为未定义 | §0 A4、§4.2、§4.3、§5.1、§5.2#10、§7.3、§8.1 用例 6 | 采纳“拒绝”：`RV` 相符但模式 passive → 409 `controller_mode_passive`，不写库；派生状态维持 `bound_passive`；新增用例覆盖 |
| 证据口径 | 探针 F 为模拟同凭证、H 为短路桩 | §1.2 表与“证据口径修正”段、§8.1 验证要求、§10.2 | F 改写为“同进程模拟第二次心跳”，结论严格限定为“校验无进程/实例维度”，不声称真实双进程；H 明确为短路桩，真实 HTTP 断言移交 C1b-1 |
| 其他核对 | epoch 持久化/ABA、`state_version` 与实际 CAS、凭证仓库外保存、跨项目读权限 | §2.2、§2.3.7、§3.1、§5.1、§1.1、§2.4 | epoch 明示持久化+严格增大（不断言差值）；`state_version` 降级为只增观测计数器、不入请求不入 where；明文 token 只允许仓库外私有位置（工作区内即属非安全存储）；项目读权限按源码写明“任意已认证成员可读、不校验名册” |

### 11.1 R1 定向修订（#108，采用 Codex 技术裁决的 review 方案 a）

| 编号 | #107 结论要点 | 本稿位置 | 修订方式 |
| --- | --- | --- | --- |
| R1 | “无 token 的 human 调 `ack`/`renew`/`release` → 403 `controller_not_authorized`”在 L2 必填 422 分层下**不可达**；用例 7/8 对同一缺字段输入按角色分码；§3.2 判定顺序与 §7.3 分层不是同一套表述 | §3.2（矩阵三格 + 要点）、§7.1 请求体列、§7.3（L2/L3 行、错误码表、多条件例子）、§7.3.1（**新增决策表**）、§8.1 用例 7/8、§10.1 自检行 | 采用**方案 a**（不采用角色感知可选 schema）：**缺必填字段一律 422，与角色无关**；**删除** human 无 token→403 的可执行承诺；“改用 `force-release`”降级为**响应文案 / 用户说明**；请求体完整后按既定层级处理角色 → 归属 → epoch → token；**错误 token 只在到达 token 校验时返回 409 `controller_token_invalid`**，不写成“压过更早检查的一律 409”；合法 human holder 权限不变；不扩展修改现有鉴权/框架的 401/403/422 全局顺序 |
| R1-a | `bind` 的 `expected_epoch` 声明可选但幂等三元组要求同 epoch，持有者重试结果未定义（#107 P3 级疑点） | §2.3.2（新增规则）、§2.3.4、§4.3 检查节点 5、§5.1（`bind` 三行）、§6.2、§7.1、§8.1 用例 25 | **携带 `binding_token` 时 `expected_epoch` 必填，缺失 → L2 422**（避免退化为 member+hash 二元组而误伤合法持有者）；**无 token 时可选且不参与判定**（首次 INSERT 无库存世代、接管走归属/租约条件），省略与携带结果一致，权威新值以响应 `owner_epoch` 为准 |
| R1-b | `force-release` 矩阵格写“非 human 一律 403”，但 agent 缺 `expected_epoch` 时按分层实际为 422 | §3.2 矩阵、§5.1（`force-release` 行）、§7.1、§7.3 L3、§7.3.1、§8.1 用例 26 | 措辞限定为**“请求体完整且到达角色鉴权时”**非 human → 403；缺 `expected_epoch` → L2 422（先于 403），消除同一格的两义 |

**#108 未改动项（与 #107 复验结论一致，不重做）**：P1-1（ACK 必填 `expected_mode_version` 与同事务 CAS）、P1-2 主体（bind 幂等三元组、201 丢失恢复、明文不回传）、P2-2 记账主体（并发释放唯一记账）、五项 P3、证据口径（探针 F/H）、epoch/ABA、`state_version` 仅观测、凭证仓外存储、跨项目读口径。D1/D2/D3 继续标注为**待项目管理者确认**，本次技术裁决**不构成实施授权**。

---

## 附：本稿相对 v1 的**未改动**部分

§1.1、§1.3、§1.4、§2.1、§2.6 的禁止事项主干、§3.3、§3.4、§4.1、§5.3、§6.1、§6.3、§8.2、§8.3、§9 的 D1/D2/D3 推荐政策与备选（仅补 A1–A3 状态标注）保持原判断；其余条款为本次一致性修订。
