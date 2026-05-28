# Project Progress

## Latest
Updated: 2026-05-27 00:13 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- 已在分支 `codex/scenario-1-scope-fix` 完成场景 1 针对性调整：收口阈值改为只统计实质 turn，避免把打招呼/在线确认当成议题讨论轮次。
- `discussion_turns.stance` 白名单新增 `greeting / closure`；bridge 会把明确的打招呼/在线确认类短消息记录为 `greeting`，自动收口消息记录为 `closure`。
- `greeting / closure` 被视为非实质 turn，不计入普通收口或分歧升级阈值；`disagree` 仍保留 human 裁决路径。
- 普通可见回复记录改走 `infer_reply_stance()`：寒暄返回 `greeting`，其它路径显式返回 `answer`；动作转发仍可沿用动作自身 stance，但空值会兜底为 `answer`。
- `_send_agent_scope_closure()` 保留硬兜底 `resolved` 状态更新，但收口话术改为按 agent id 稳定挑选，避免不同 agent 复读同一句固定机器话。
- 文档已同步 `docs/MODULE_discussions.md`、`docs/MODULE_bridges.md`。

### 3) Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续可由无项目记忆的黑盒测试 agent 复验场景 1。
- `greeting` 识别采用保守规则：任务范围像打招呼/在线确认，且回复较短、包含问候/在线确认特征时才标记为非实质 turn；其它普通可见回复显式记录为 `answer`。
- `docs/p.drawio` 作为本次协议评估输入保留在工作区，未被本切片修改；当前仍是未跟踪文件。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只是授权 pi CLI 子进程使用工具；是否让 pi 真正承担代码施工仍需按后续任务显式启动 `--pi-execution-profile tools`。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 提交场景 1 寒暄收口补强。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，优先复验黑盒场景 1：打招呼不应过早收口，也不应复读固定收口话术。
3. 若场景 1 通过，再继续处理测试文档中的下一类问题。
4. 已与项目管理者完成产品形态对齐（2026-05-27），共识写入 `docs/LOCAL_LAB_DESIGN.md` 新增"2026-05-27 产品形态对齐共识"章节，待后续按章节拆切片落地（优先级建议：`groups.metadata` 字段 → bridge 服务化模板 → 项目目录文档模板）。本轮不动代码与表结构。同一章节当日补充了两条细化：(a) 身份模型由"项目+模型=member"修正为"**项目+模型+角色=member**"，并区分订阅 CLI 单例与 API-key 模型的部署约束；(b) 新增原则 7：`AGENTS.md` 仅承载抽象角色字典，bridge 在 prompt 注入"member_id / decision_tier / 业务角色"三元事实。同步改写 `AGENTS.md` 的"角色与协作约束"与"当前 Agent 角色"两段，去除"Codex = 决策 Agent"等具体身份指派，改为纯抽象字典。
5. 已与项目管理者复盘 `codex/scenario-1-scope-fix` 分支黑盒测试结果（外部测试文档：`D:\claude-test\black box test\talk\codexscenario-1-scope-fix\test.md`），场景 1/2/3 FAIL，场景 4/5 PASS。归并为 3 个修复项，按以下顺序由后续开发承接（本轮 Claude 不动代码，开发另作安排）：

   **修复项 5.1：visible_reply 调度顺序修正**（覆盖原报告 A + B）
   - 规则：bridge 处理消息时，若 `visible_reply` 非空，**必须先回 sender，再执行任何 `TALK_ACTION` 副作用**；不论 sender 是 human 还是 agent。
   - 规则：若 `visible_reply` 为空，**不补任何 fallback 文案**；彻底删除 `cli_bridge.py` 中 "已按讨论协议继续推进。" 的 hard-coded fallback 分支。
   - 修复后效果：测试 #247 / #251 / #261 三类问题同时消除。
   - 影响代码：`bridges/cli_bridge.py` 内 visible_reply / fallback / action 执行调度逻辑。

   **修复项 5.2：去除 prompt 中可被照搬的具体例句**（覆盖原报告 C）
   - 规则：`bridges/cli_bridge.py` 的 `RESPONSE_STYLE_INSTRUCTIONS` 不应再给出 `"<agent id> 在线。"` 这种具体例句。建议直接移除该例句，仅保留"短句、贴近请求范围"的抽象指令；或保留多个变体并显式声明 `"these are formatting hints, do not copy the exact wording"`。
   - 修复后效果：codex 不再每条回复都以 "codex 在线，…" 起头，回复语言自然多样化。
   - 影响代码：`bridges/cli_bridge.py` 中 `RESPONSE_STYLE_INSTRUCTIONS` 常量。

   **修复项 5.3：建立 Agent 角色注入框架**（覆盖原报告 D + E；同时是 `docs/LOCAL_LAB_DESIGN.md` 2026-05-27 共识章节原则 7 的最小落地）
   - **真实定位**：这不是一个单点 bug 修复，而是"全 agent 角色管理"的基础设施切片。落地后 `AGENTS.md` 抽象角色字典才真正能被 agent 对号入座；本项 + 5.4 一起构成完整的角色框架。
   - 规则：bridge 在 spawn LLM CLI 前，按当前消息所属 `group_id` 调用 `GET /api/groups/{id}` 与 `GET /api/groups/{id}/members`，取得成员清单（含 `display_name`）和 metadata，再据此动态拼 prompt。
   - bridge 启动配置增加 `decision_tier` 字段（取值 `decision` / `execution`，缺省按 `execution` 处理）。
   - prompt 必须注入的"身份三元事实"：
     1. **`member_id`**：当前 agent 的完整身份（如 `agent:deepseek@projA:tester`）—— 已有部分实现，本项确认覆盖
     2. **`decision_tier`**：当前 agent 的决策分级（来自 bridge 启动配置）—— 新增
     3. **业务角色**：当前 agent 在本群的业务角色（反查 `metadata.roles[<self_member_id>]`，如有；缺失走缺省策略）—— 新增
   - prompt 同时注入：
     - **本群完整成员清单**（事实清单，禁止指名清单外成员）
     - **缺省策略**：若 `metadata.roles` 缺失或当前 agent 无角色，注入"本群无角色约定，只严格回应字面请求，不要主动扩展，不要假设这是项目讨论"
   - 修复后效果：
     - 所有 agent 进会话即知道自己 `member_id / decision_tier / 业务角色`，不再需要从 PROGRESS.md 临时声明读出（PROGRESS.md 第 1 节"Current Agent Role"可在 5.3 落地后简化甚至移除）
     - pi 不再幻觉出 `paddy / bobo` 之类非群成员名（经项目管理者确认，这两个名字不在项目任何文档中定义，判定为 pi CLI 自身训练污染）
     - 寒暄/在线确认类纯测试群内，pi 不再主动追问项目/模块/协作机会
   - 实现节奏：本项目前 `groups` 表尚无 `metadata` 字段（待修复项 5.4 落地），因此修复项 5.3 先按"metadata 缺失 → 默认严格策略"实现；待 `groups.metadata` 字段加入后再扩出"按角色注入"分支，无需返工成员清单注入逻辑与 `decision_tier` 注入。
   - 影响代码：`bridges/cli_bridge.py` 消息处理入口与 prompt 拼装函数；`deploy/bridges.example.json` 模板增加 `decision_tier` 字段。

   **5.3 落地前的过渡机制**：角色管理仍由 `docs/PROGRESS.md` 第 1 节"Current Agent Role"显式声明，沿用本轮当前做法。Claude 通过 `CLAUDE.md` 必读清单先读 `PROGRESS.md` 即可在每次会话开始确认自己的临时角色。

   **修复项 5.4（后置，依赖产品形态对齐切片）**：`groups.metadata` JSON 字段落地与读写 API；按 `docs/LOCAL_LAB_DESIGN.md` "2026-05-27 产品形态对齐共识"章节执行。修复项 5.3 在该字段就绪后回头打开"按角色注入"分支。

   **复跑要求**：5.1 + 5.2 + 5.3 完成后，重启 server / Codex bridge / pi bridge，复跑 `test.md` 中场景 1/2/3，确认：
   - 不再出现"已按讨论协议继续推进。"
   - pi 收到 human 任务后**先**回 human，**再**去找另一个 agent
   - codex 回复不再固定以 `"<id> 在线。"` 起头
   - 任何 agent 不再指名群外成员
   - 寒暄/在线确认场景下 agent 不主动扩展为项目讨论

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，59 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` first run hit existing WebSocket fallback timing timeout once; immediate rerun passed，11 tests。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` passed，43 tests。
- `usage-gate guard --provider codex --json` 上次 decision=`pause_before_next_slice`，weekly=84%；项目管理者已明确本轮可先忽略用量继续补强。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `server/models.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `docs/MODULE_discussions.md`
- `docs/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/LOCAL_LAB_DESIGN.md`（2026-05-27 新增产品形态对齐共识章节 + 当日补充身份三元组与 AGENTS.md 抽象字典原则，不涉及代码改动）
- `AGENTS.md`（同步去除具体身份指派，改为抽象角色字典；业务角色由 `groups.metadata.roles` 承载，不在本文件枚举）
- `CLAUDE.md`（砍成薄壳入口：保留必读清单、Claude 身份说明、部署/运维指路；移除与 `AGENTS.md` / `docs/PROJECT_BRIEF.md` 重复的开发者指引、技术栈速查、启动方式、运维说明、项目结构注意事项、定时备份参考、部署入口具体内容）

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
