# 开发历史 · TALK

<!--
项目根：d:\claude-test\TALK
最后更新：2026-06-02 5.x agent-to-agent 通信主线关闭（黑盒复测通过）

## 2026-06-07 5.7+ 对话质量打磨 + PROJECT_INTEGRATION 长期方向沉淀

**背景**：5.x 主线在 6/2 ship 之后，黑盒发现 agent-to-agent 对话仍有质量问题（pi 自称 "qa"、pi-kimi 把名字拆成 "pi 和 kimi"、双向 "已经XX啦" 汇报体循环）。本轮针对这些问题做三次迭代修复，最终在 `group:1488c22048e3` (test-run17) 上验证对话自然收敛。同时把 ClawSwarm / OpenClaw Control Center / Multica 三份对比报告的启示整理成 `docs/spec/PROJECT_INTEGRATION.md`，作为 5.x 关闭后下一阶段的长期方向草案。

### Prompt 与对话质量（三次迭代）

| 迭代 | 改动 | 解决的问题 | 副作用 |
|------|------|-----------|--------|
| 第一次 | per-call prompt 加 "你是 {member_id}（完整 ID，不要拆解为多个名字）。" 独占首行 | 身份混乱、连字符 ID 拆解 | pi 陷入 "自我介绍" 模式，任务被淹没 |
| 第二次 | 改紧凑内嵌："你是 {member_id}。{sender} 对你说：{task}" 同一行 | 任务动词重新获得焦点；身份锚仍有效 | 元叙述 "已经XX啦" 双向循环汇报仍出现 |
| 第三次 | 废弃 pi/codex 分支的 `discussion_context` 注入；`FUNCTION_CALLING_SYSTEM_PROMPT` 加反元叙述规则 | 元叙述循环汇报根治 | 残留：visible reply + talk_send 双通道下偶尔有凑数 visible（治本在 PROJECT_INTEGRATION §9.3 结构化块） |

### 涉及代码改动

- `bridges/cli_bridge.py` `build_cli_prompt` + `build_cli_task_prompt` 紧凑身份注入，废弃 discussion_context 在 pi/codex 分支
- `bridges/cli_bridge.py` `FUNCTION_CALLING_SYSTEM_PROMPT` 增加反元叙述规则
- `bridges/talk_tools_extension.ts` `talk_send` promptGuidelines 增加 "用自己 member_id 身份写 body"
- `tests/test_cli_bridge.py` 翻转 4 处旧的 `assertNotIn("agent:pi"…)` 断言为 `assertIn`；新增 inline 身份注入测试 + task path 身份测试；两个老测试（scope_text / requester_id 断言）改为锁定 "不应在 prompt 里"
- `tests/test_codex_bridge.py` 同步翻转 2 处旧断言

### 文档

- `docs/spec/INTERACTION_FRAMEWORK.md` §5.3 表格修正（身份从系统层挪到单次调用层）+ 增加 2026-06-06 三次修正备注
- **新增 `docs/spec/PROJECT_INTEGRATION.md`** — TALK 基础设施化方向设计草案

### 黑盒验证

测试群：`group:1488c22048e3` (test-run17)，pi 0.78.0，人类指令：`@agent:pi 去跟 agent:pi-kimi 打个招呼`

**验收结论**：
- ✅ pi 自称 "pi"（无 qa 幻觉）
- ✅ pi-kimi 自称 "pi-kimi" 整体识别（无拆解）
- ✅ 无双向 "已经XX啦" 循环汇报
- ✅ 整体语气像两个有思想的人在交流兴趣点
- ⚠️ 残留小问题：pi 对 human 报告 "已经向 pi-kimi 发送了问候"（可接受）；第二轮 talk_send 后 visible reply 凑数（治本待 §9.3 结构化块）

### 单测验证

- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：81 tests 通过

---

## 2026-06-02 黑盒复测：agent-to-agent 通信端到端验证

**背景**：Pi extension dispatch 根因定位与规避完成后，按 PROGRESS.md 下一步执行完整黑盒复测。

**测试环境**：
- TALK Server `127.0.0.1:8000`，群 `group:88f99bd38f3f` (test-run16)
- pi CLI v0.78.0 (Google provider)，bridges 以 `--no-extensions --extension talk_tools_extension.ts` 启动
- Bridges 在线: agent:pi + agent:pi-kimi；agent:codex 未安装（跳过）

**Case 1: `@agent:pi 去跟agent:pi-kimi打个招呼`** ✅ PASS
- agent:pi 通过 `talk_send` 工具向 agent:pi-kimi 发送问候
- 多轮交互共 7 turns，Session #78 status=resolved, max_rounds=2
- 账本: demand=1 (greeting), reply=6 (answer×4 + closure×2)

**Case 2: `@agent:codex 通知 agent:pi 项目进度已更新`** ⚠️ SKIP
- codex CLI 未安装于本环境，非代码缺陷

**Case 3: `@agent:pi 问 agent:pi-kimi 它现在忙不忙`** ✅ PASS
- agent:pi `talk_send` → agent:pi-kimi 回复"不忙，暂时空闲"
- 5 turns, Session #79 max_rounds=2 正确限制
- 账本: demand=2, reply=3, round_index max=2

**验证**：
- Agent-to-Agent 消息: 12 条（from_id 含 agent:pi/agent:pi-kimi, to_ids 含对方）
- discussion_turns: demand=3, reply=9（turn_kind 同时出现）
- round_index 刹车正确: max=2，达到上限后自动 closure
- `--no-extensions` 规避方案在 pi 0.78.0 下有效

**结论**：5.x agent-to-agent 通信主线关闭。方案 D 端到端验证通过。

---

## 2026-06-02 Pi extension dispatch 根因定位与规避（plan-mode 工具覆盖）

**背景**：pi bridge 注册的 `talk_send` extension 工具从未被 LLM 调用，四轮黑盒/探针/源码插桩后定位根因并修复。

**根因**：pi 自带的 `plan-mode` 扩展 (`@earendil-works/pi-coding-agent/extensions/plan-mode/index.ts:343-345`) 在 `rebindSession` 事件回调里无条件 `pi.setActiveTools(NORMAL_MODE_TOOLS)`，全量替换当前激活工具集，抹掉 `talk_send`。

**修复**：
1. `bridges/pi_bridge.py` `DEFAULT_PI_COMMAND` 与 `DEFAULT_PI_TOOLS_COMMAND` 均追加 `--no-extensions`，禁用自动发现扩展（含 plan-mode）；`--extension` 显式加载不受影响
2. `tests/test_pi_bridge.py` 新增两条断言确保两档命令均含 `--no-extensions`
3. `docs/spec/INTERACTION_FRAMEWORK.md` 新增 §6.5 Pi runtime 工具覆盖陷阱与规避、§6.6 Windows MCP UTF-8 强制、§6.7 Codex 非交互 MCP approval 闸门
4. Upstream issue 提交至 `earendil-works/pi`，含复现步骤、源码定位、推荐修复

**验证**：py_compile 通过，79 tests 通过，echo_tool 探针确认规避方案有效。

---

## 2026-06-02 codex MCP approval / UTF-8 修复

**背景**：Codex 非交互 `exec` 默认取消 MCP tool call，Windows 下 MCP 子进程需显式 UTF-8 环境。

**修复**：
1. `bridges/codex_bridge.py` 默认命令追加 `--dangerously-bypass-approvals-and-sandbox`
2. 默认 MCP 配置追加 `env.PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`
3. `tests/test_codex_bridge.py` 新增覆盖 approval bypass、UTF-8 env、per-call TALK_* 不 hardcode

**验证**：py_compile 通过，13 tests 通过，独立 probe 确认 talk_send MCP 可写入 TALK_DEFERRED_FILE。

---

## 2026-06-01 codex MCP 路径集成（方案 D 延续）

**背景**：方案 D 已为 pi 建立了 JSONL + env-var 契约（`talk_tools_extension.ts`），codex 需要同等能力但用 MCP server 替代 TS extension。

**改动点 1 — 新增 `bridges/talk_send_mcp.py`**：
- 最小 stdio MCP server（裸 JSON-RPC 2.0 over stdin/stdout，~140 行）
- 暴露 `talk_send` 工具，从 `os.environ` 读取 TALK_DEFERRED_FILE / TALK_GROUP_ID / TALK_API_KEY
- 把 `{tool:"talk_send", target, body, stance, group_id}` 追加到 JSONL，返回"talk_send 已登记"
- 协议支持 MCP initialize / tools/list / tools/call，codex CLI 通过 `-c mcp_servers.talk_send.*` 配置连接

**改动点 2 — 修改 `bridges/codex_bridge.py`**：
- `run_bridge` 注入 `TALK_API_KEY` / `TALK_BASE_URL` / `TALK_MEMBER_ID` 环境变量（类比 pi_bridge:63-66）
- `default_codex_command()` 拆为 discussion（read-only sandbox）和 tools（workspace-write sandbox）两档，均注册 talk_send MCP server
- 新增 `--codex-execution-profile {discussion,tools}` 参数，默认 discussion
- Windows 下自动检测 Codex CLI 路径（AppData/Local/OpenAI/Codex/bin/codex.exe）

**改动点 3 — 修改 `bridges/cli_bridge.py`**：
- `build_cli_prompt` / `build_cli_task_prompt` 的 codex 分支从 v0 文本协议切换为 function-calling 祈使句风格
- 条件从 `runtime == "pi"` 扩展为 `runtime in ("pi", "codex")`
- 移除了 DISCUSSION_PROTOCOL_INSTRUCTIONS 中 v0 文本协议教学对 codex 的注入（execute_talk_actions 保留作兜底）

**改动点 4 — 保留 `execute_talk_actions`**：不动，作为文本协议兜底兼容。

**改动点 5 — 新增测试**：
- `test_codex_deferred_talk_send_via_mcp_equivalent_to_pi_path`：用 fake CLI 模拟 codex spawn MCP 写 JSONL → bridge 消费 → 写 demand turn
- 验证 codex 路径产物与 pi 路径等价（visible reply 先于 talk_send、demand turn 写入账本）
- 更新 `test_build_cli_prompt_for_pi_does_not_duplicate_restraint_instructions` 适配统一后的 prompt

**验证结果**：
```
py_compile: talk_send_mcp.py / codex_bridge.py / cli_bridge.py → OK
tests.test_cli_bridge: 54 tests OK（含新增 codex MCP 等价测试）
tests.test_discussions: 16 tests OK
tests.test_pi_bridge: 3 tests OK
MCP server 协议验证: initialize / tools/list / tools/call → 通过
git diff --check: 通过（仅 Windows CRLF 提示）
```

**不变的部分**：
- `_can_create_deferred_file` / `_read_and_execute_deferred_actions` / `_record_deferred_demand_turns` 完全不动
- `talk_tools_extension.ts` 继续为 pi 服务
- `execute_talk_actions` 保留作为文本协议兜底

---

## 2026-06-01 docs 目录二次整理

**背景**：docs/ 根目录存在 18 个重复文件（MODULE_*.md、PRODUCT.md、SDK.md 等），同时 docs/spec/ 和 docs/guides/ 已有对应副本。

**操作**：
- 逐对比较根目录副本与 spec/guides 副本，确认所有 spec/guides 副本内容不低于根目录副本：
  - DEPLOY.md、QUICKSTART.md、QUICKSTART_AGENT.md：guides 副本有路径修正（../../deploy/talk.service、../spec/SDK.md）
  - MODULE_agent_example.md：spec 副本已将 SDK.md 路径更新为 docs/spec/SDK.md
  - MODULE_discussions.md：spec 副本有额外 turn_kind 字段和验收点内容（较根目录多 642 字节）
  - LOCAL_LAB_DESIGN.md、SDK.md、MODULE_bridges.md 等 8 个文件：仅 CRLF/LF 差异，内容相同
  - PRODUCT.md、QUICKSTART_USER.md、MODULE_files.md 等 5 个文件：完全一致
- 删除全部 18 个根目录重复文件
- 不创建空的 iterations/、validation/、milestones/ 目录（已确认不存在）

**引用更新**：
- `docs/PROJECT_BRIEF.md`：目录结构树、11 条模块索引链接（→ spec/MODULE_*.md）、3 条 Addendum 引用（→ spec/或 guides/）
- `AGENTS.md`：模块文档指引明确路径为 spec/MODULE_xxx.md
- `CLAUDE.md`：部署/快速启动链接指向 docs/guides/
- `README.md`：Quickstart/Deploy/SDK 链接指向 docs/guides/ 和 docs/spec/

**验证**：
- `rg --files docs` → 结构符合目标
- 旧路径搜索（`docs/(MODULE_|PRODUCT\.md|SDK\.md|...)`）→ 无残留，仅新路径引用
- Markdown 本地链接校验 → 通过
- `git diff --check` → 通过

---

最后更新：2026-06-01 5.5 方案 D：discussion_turns 显式交互账本
最新条目在顶部。条目数 > 30 时，最旧条目自动归档到 PROGRESS_archive.md
-->

## 2026-08-27 Kimi 迁移到官方 Kimi Code CLI

**背景**：当前固定拓扑中的 Reviewer 名义上是 Kimi，但实际由 pi runtime 加载 `moonshotai-cn/kimi-k3`。项目管理者已经在本机安装 Kimi Code CLI，并确认改用本家 CLI。本切片只完成 bridge、活动成员拓扑和项目文档迁移；不启动 Server/bridge，不创建新验收任务，不进入 TH-7。

### 完成事项

- 新增 `bridges/kimi_bridge.py`，默认成员为 `agent:kimi`、runtime 为 `kimi-code`，使用官方 `kimi --auto --output-format stream-json ... -p` 和 argv prompt 传输；`--auto` 避免无人值守 bridge 卡在权限询问，实际能力仍受 Agent 文件工具白名单约束。
- bridge 启动时在临时目录生成三份受控 Kimi Agent 文件：Group Hall 讨论无工具、Task Hall 领取前预检无工具、任务执行默认 `review` 档开放 `Read / Grep / Glob / Bash`；显式 `--kimi-task-profile tools` 才额外开放 `Edit / Write`。
- 三份 Agent 文件均设置 `subagents: []`，并把 `--skills-dir` 指向受控空目录；项目 `.talk/agents/agent_kimi/` 的 IDENTITY / SOUL / USER 通过既有 profile 机制注入系统提示词。
- 通用 bridge 新增 Kimi `stream-json` 解析与结果归一化，忽略 Tool / meta 事件，提取最后一条非空 Assistant 文本；覆盖消息处理、任务预检、协议修复、任务执行和 Review/Test 门禁。
- Kimi 纳入紧凑身份 prompt 规则；pi 专属中文最终答复归一化保持不变。
- `.talk/groups.yaml`、`AGENTS.md` 与各 Agent 角色档案切换到 `agent:kimi`；移除旧活动档案 `.talk/agents/agent_pi/`，但不迁移或删除数据库中的旧成员历史。
- `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_bridges.md`、`docs/spec/MODULE_tasks.md`、`docs/spec/LOCAL_LAB_DESIGN.md` 已同步官方 Kimi CLI 入口、当前拓扑、权限档位和已知会话边界。pi bridge 仍保留为兼容入口。

### 验证

- `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q`：`Ran 119 tests`，`OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_profiles tests.test_talk_cli -q`：`Ran 196 tests in 9.713s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 389 tests in 109.913s`，`OK`。
- `python bridges/kimi_bridge.py --help` 正常；`py_compile bridges/cli_bridge.py bridges/kimi_bridge.py tests/test_kimi_bridge.py` 通过；`git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机 Kimi Code CLI `0.38.0` 能正确解析 `--output-format stream-json`、受控 `--agent-file` 和 `--skills-dir`，并输出 JSON meta；随后因本机尚未登录或配置默认模型返回 `No model configured`、退出码 1。该调用没有模型答案，因此真实端到端验收仍待完成。
- 本切片无前端改动，未重复 Browser 验证；未启动 TALK Server/bridge，未创建任务，也未触碰已取消的 `#10/#11`。
- 已创建中文提交 `522635d`（`迁移 Kimi 到官方 CLI bridge`）。首次沙箱内 push 因无可用凭据失败，外部凭据 push 曾被授权门禁拒绝；项目管理者随后明确授权该远端与分支，推送成功：`14bd3d8..522635d  codex/task-hall -> codex/task-hall`。

### 当前结论与下一步

- 官方 Kimi Code CLI bridge 的实现与自动化回归完成，当前活动 Reviewer 身份统一为 `agent:kimi`。
- 项目管理者先执行 `kimi login` 或配置 Kimi Code 默认模型；随后同步项目 profile 并从全新根任务启动 Codex → DeepSeek → Kimi 的真实 TH-6d 验收。
- 本切片涉及 bridge 与跨模块配置，按决策 Agent 批次刹车暂停；真实三 Agent 人工验收通过前不进入 TH-7。

### 变更文件

- `bridges/cli_bridge.py`
- `bridges/kimi_bridge.py`
- `tests/test_kimi_bridge.py`
- `.talk/groups.yaml`
- `.talk/agents/README.md`
- `.talk/agents/agent_codex/IDENTITY.md`
- `.talk/agents/agent_codex/USER.md`
- `.talk/agents/agent_deepseek/USER.md`
- `.talk/agents/agent_kimi/IDENTITY.md`
- `.talk/agents/agent_kimi/SOUL.md`
- `.talk/agents/agent_kimi/USER.md`
- `.talk/agents/agent_kimi/MEMORY.md`
- 删除 `.talk/agents/agent_pi/` 下四份旧活动档案
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_tasks.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-22 推送修复并安全收束旧验收任务树

**背景**：DeepSeek 非持久化预检切片已经提交但尚未推送；真实三 Agent 验收遗留根任务 `#10` 与 Development 子任务 `#11`，分别停在 `running/in_progress` 和 `queued/assigned`。项目管理者要求先提交 GitHub 并继续。本切片只处理推送和旧树收束，不启动 bridge、不创建新验收任务。

### 完成事项

- 将本地领先的 5 个提交推送到 GitHub `origin/codex/task-hall`；本地与远端均指向 `cf12e8f`。
- 只读确认旧树范围严格为 `#10/#11`，无 Review/Test 关系或澄清记录；`#11` 从未 claim，`#10` 的旧租约早已过期。
- 按项目脚本创建操作前 SQLite 在线备份 `backups/backup_2026-08-22.db`，并通过完整性检查。
- 使用无 lifespan 的本地 ASGI 请求走正式鉴权和 `cancel-tree` API：先读取树并验证任务 id 为 `[10, 11]`，再由根请求者取消整树。
- `#10/#11` 均进入 `canceled/canceled`，根控制为 `canceled`、检查点原因为 `manual_cancel`；claim、实例、token 与租约全部清除。
- 两个 Task Hall 与其中 3 条历史消息保持不变；未启动 Server/bridge，未创建新任务。临时操作脚本已删除。
- 顺手纠正 `MODULE_tasks.md` 中已经过时的预检重试和本地 `pi-kimi` 拓扑描述，使其与已落地 bridge 行为和当前三 Agent 配置一致。

### 验证

- GitHub push：`5583bad..cf12e8f  codex/task-hall -> codex/task-hall`；本地与远端 SHA 均为 `cf12e8fdcef84dfc7e6a7d679d85be79b2d3665d`。
- 操作前备份与操作后 `talk.db` 的 `PRAGMA quick_check` 均返回 `ok`。
- `GET /api/tasks/10/tree` 与 `POST /api/tasks/10/cancel-tree` 均返回 `200`。
- SQLite 只读复核：`#10/#11 = canceled/canceled`，根 `control_status=canceled`，Hall 数为 2、Hall 历史消息数为 3。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks.AgentTaskTests.test_checkpoint_and_cancel_tree_enforce_roles_and_preserve_history -q`：`Ran 1 test in 1.842s`，`OK`。首次把测试类名误写为不存在的 `TaskApiTests`，该次未执行任何用例；更正为真实类名后通过。
- 8000 端口无监听；Git 工作树在文档更新前保持干净。

### 当前结论与下一步

- 旧验收树已经永久停止，不会在重新启动 bridge 后被误领；历史证据和恢复备份仍保留。
- 下一切片从全新根任务开始真实三 Agent 验收，依次验证 Codex 根协调、DeepSeek Development、Kimi3 Review/Test 与项目管理者人工验收；等待项目管理者确认后开始。

### 变更文件

- `docs/spec/MODULE_tasks.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 避免 DeepSeek 预检会话持久化

**背景**：此前给预检增加 3 轮上限后，DeepSeek Harness 每次 `headless` 调用仍会创建持久会话；单轮又可能包含正常判断和协议修复，因此出错时仍会生成多个无效对话窗口。项目管理者决定保留领取前澄清，但要求预检不产生窗口，并把 DeepSeek 跨轮询限制为 1 轮。本切片只处理该 bridge 行为，不启动现有 bridge、不处理旧 `#10/#11`、不进入三 Agent 验收。

### 完成事项

- 新增项目内 `.talk/dsh/preflight-ephemeral.cordis.yml`，只关闭 DSH 的 `session-persistence-jsonl` 和 `session-checkpoint-policy`。
- 通用 bridge 在 `runtime=dsh`、使用官方 `dsh / dsh.cmd / dsh.exe` 启动命令且 `--project` 下存在补丁时，只为 Task Hall 预检追加 `--patch`；正式任务命令保持原样，因此成功执行仍只保留一个正常 DSH 会话。
- 显式 `--task-preflight-command` 继续优先，自定义命令与缺失补丁时保持旧行为，避免隐式改写第三方命令。
- 新增 `--task-preflight-max-attempts 1..3`；DeepSeek 默认 1 轮，其他 runtime 默认 3 轮。单轮内的协议修复和信息不足时的澄清流程均保留。
- 新增自动注入、显式覆盖、缺失补丁回退、runtime 默认上限和 DeepSeek 一轮失败终止回归测试。

### 验证

- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 147 tests in 1.139s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 380 tests in 156.709s`，`OK`。
- `python bridges/cli_bridge.py --help`：正常展示 `--task-preflight-max-attempts {1,2,3}`。
- DSH `--dump-config` 确认补丁后的 `session-persistence-jsonl` 与 `session-checkpoint-policy` 均为 `disabled: true`。
- 真实最小 DSH 调用退出码为 0；调用前后用户级 sessions 目录均为 55 个文件，新增或改写为 0。此次未启动 TALK bridge，旧 `#10/#11` 现场未变。

### 当前结论与下一步

- DeepSeek 的澄清判断仍在，但预检与同轮协议修复不再出现在 DSH 会话列表；失败至多 1 轮，成功后只有正式执行会保留一个会话。
- 下一切片仍需先安全处理旧 `#10/#11`，再从新根任务执行 Codex → DeepSeek → Kimi3 的 Development / Review / Test / 人工验收完整闭环；等待项目管理者确认后开始。

### 变更文件

- `.talk/dsh/preflight-ephemeral.cordis.yml`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 修复委派弹窗卡片与两阶段上下文

**背景**：TH-6d 真实验收发现 `.task-create-panel.modal-card` 没有背景、边框和阴影，页面内容会透过弹窗；根任务与子任务又复用静态“执行 Agent”标签，无法直观看出先选根负责人、再为各子任务选执行者的两阶段关系。项目管理者要求本切片单独修复该前端问题。

### 完成事项

- 为通用 `.modal-card` 补齐实体背景、边框、圆角、文字颜色和阴影，任务创建弹窗不再透明；Group 创建和 Agent 人设等现有 modal 同时获得一致的卡片壳。
- 任务弹窗新增 dialog 语义及标题、上下文说明和 Agent 标签锚点；根模式显示“委派根任务 / 根任务负责人 / 创建根任务 Hall”，子模式显示“创建子任务 / 子任务执行 Agent / 创建子任务 Hall”。
- 根模式说明“根任务开始后再从详情创建子任务”，子模式说明“当前 Agent 只执行子任务，根负责人继续协调和汇总”；缺少 Agent 时的校验提示也随模式切换。
- 更新前端资源 cache-busting 版本，避免浏览器继续使用旧 CSS / JS。
- 前端静态测试新增卡片视觉属性、dialog / 可访问名称和动态两阶段文案断言；模块合同与用户手册同步当前按钮和字段名称。

### 验证

- `node --check web\app.js`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_task_web_ui -q`：`Ran 2 tests in 0.707s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 376 tests in 106.338s`，`OK`。
- Codex Browser 使用隔离临时 TALK 服务真实登录并分别打开根任务和子任务弹窗：两种模式计算背景均为 `rgb(255, 254, 250)`，具有实线边框、`14px` 圆角和阴影；DOM 中标题、说明、Agent 标签、下拉框可访问名称和提交按钮全部与模式一致，控制台无 error / warning。
- 隔离服务仅使用临时成员、项目、根任务和数据库；验证后关闭页面与服务并清理全部临时文件，现有 `talk.db` 和旧 `#10/#11` 现场未修改。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek 多行 prompt、预检无限重试和委派弹窗两个前端问题均已完成修复及自动化 / Browser 验证。
- 下一步等待项目管理者确认后安全处理旧 `#10/#11` 现场，并从新根任务重新执行真实三 Agent 完整验收；本切片不继续该操作。

### 变更文件

- `web/index.html`
- `web/app.js`
- `web/style.css`
- `tests/test_task_web_ui.py`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 限制任务预检最多连续尝试 3 次

**背景**：TH-6d 真实验收曾观察到 DeepSeek 预检协议输出无效后，worker 在每个轮询中执行正常提示和协议修复提示，两次均失败后仍在后续轮询继续调用，数分钟内生成至少 24 个无效 DSH session。项目管理者明确要求本切片只增加 3 次限制，不连续处理前端问题。

### 完成事项

- 将预检命令、超时、非零退出和无效协议结果统一包装为 `TaskPreflightError`；同一轮正常输出无效时仍保留一次协议修复机会。
- 任务 worker 按 task id 记录连续预检失败，最多进入 3 个轮询尝试；前两次上报实例错误，第 3 次不再等待下一轮。
- 达到上限后，bridge 领取 poison task，在对应 Task Hall 写入“已停止重试”的用户可见说明，并以 `failed` + `last_error` 完成任务，使终态持久化且不会进入第 4 次模型调用。
- 任一预检成功会清除该任务此前的失败计数；某个任务预检失败不会阻止 worker 继续处理同轮其它排队任务。
- 当前失败计数保存在 worker 进程内：达到第 3 次后的 `failed` 状态持久化；若在达到上限前人为重启 bridge，未完成计数不会跨进程继承。本切片未增加数据库字段或任务 API。
- 用户手册补充“自动预检连续失败 3 次”的恢复说明。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- 3 条新增定向用例：协议修复仍失败会抛出专用错误；连续失败严格停在第 3 次并持久化任务失败；成功预检会清零先前计数。结果为 `Ran 3 tests in 0.005s`，`OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 143 tests in 0.543s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 376 tests in 105.860s`，`OK`。
- 测试使用受控 fake runner 精确统计预检次数，确认没有第 4 次调用；本切片没有调用真实 DeepSeek 模型。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek 多行 prompt 丢失与预检无限重试两个 bridge 阻断项均已完成代码修复和自动化验证。
- 下一切片建议单独修复委派任务弹窗背景及根任务/子任务上下文标签，等待项目管理者确认后开始。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 修复 DeepSeek Windows 多行 prompt 丢失

**背景**：TH-6d 真实验收确认 TALK 以多行最终 argv 调用全局 `dsh.cmd` 时，Windows npm shim 的 `%*` 转发只把首行送入 Harness。升级 `@deepseek-ai/dsh` 至 `0.1.0-rc.8` 后问题仍在，因此本切片只修复命令启动边界；项目管理者明确要求逐项处理，本次没有顺带修改预检重试或前端问题。

### 完成事项

- 通用 bridge 在 Windows 解析到 `dsh.cmd` 后，会读取同目录全局 npm 树中的 `@deepseek-ai/dsh/package.json`，校验包名、`bin` 配置、入口存在且未逃逸包目录。
- 校验通过后，bridge 使用 npm 目录内的 `node.exe` 或系统 Node 直接启动 Harness JavaScript 入口，并保留原命令其余参数；任务预检和正式执行因共用 `run_cli_command` 均获得相同修复。
- 识别范围严格限定为官方 `dsh.cmd`；manifest 无效、入口异常、Node 不可用或命令为其他 `.cmd` 时保持原命令，不改变其他 CLI 行为。
- 新增官方 DSH shim 解析、非 DSH `.cmd` 保持原样以及中文多行 prompt 作为单个最终 argv 完整传输的回归测试。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 140 tests in 0.574s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 373 tests in 105.003s`，`OK`。
- 本机解析探针确认配置中的 `dsh.cmd --profile headless` 实际转换为 `node.exe ...\@deepseek-ai\dsh\lib\bin.js --profile headless`。
- 通过修复后的 `run_cli_command` 执行一次受控真实四行模型探针，DeepSeek 同时识别两行令牌并只返回 `DSH_MULTILINE_OK`，证明首行之后的正文和末行约束均未丢失。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek Windows 多行 prompt 丢失已修复，现有 bridge 启动配置无需改写。
- 预检协议失败后的跨轮询无限重试仍是独立阻断项；下一切片建议只处理该问题，等待项目管理者确认后开始。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 DeepSeek Harness `0.1.0-rc.8` 受控升级与验证

**背景**：TH-6d 真实三 Agent 人工验收已确认本机 `@deepseek-ai/dsh 0.1.0-rc.6` 经 Windows `dsh.cmd` 接收 TALK 多行 prompt 时只保留首行。项目管理者发现上游已发布 `0.1.0-rc.8`，决定先升级运行时基线，再进入 bridge 修复切片。

### 完成事项

- 两次手工 `npx @deepseek-ai/dsh@next --version` 尝试都在 npm `idealTree` 依赖解析阶段触及约 2 GiB 的 V8 堆上限；日志确认 DSH 尚未启动，全局版本仍为 `0.1.0-rc.6`。
- 在没有 DSH 进程运行时，为 `C:\Users\Administrator\.dsh` 建立临时结构化备份：121 个真实文件逐一校验 SHA-256，510 个 Junction 的相对路径、类型与目标全部一致。
- 通过仅对单次安装进程设置 `NODE_OPTIONS=--max-old-space-size=4096`，执行固定版本全局安装；npm 完成 `added 23 / removed 100 / changed 428 packages`，全局 DSH 升级为 `0.1.0-rc.8`。
- npm 11.16 的 `allow-scripts` 提示仅表示尚未记录审批；安装日志确认 6 个生命周期脚本均已执行且退出码为 0，没有再次执行或放宽全局脚本策略。
- 全部升级验证通过后，先移除备份内 510 个 Junction 本身，再递归删除唯一临时备份目录；复核确认目录不存在。

### 验证

- `dsh --version` 与 `npm list -g @deepseek-ai/dsh --depth=0` 均返回 `0.1.0-rc.8`。
- `dsh --help` 与 `dsh --profile headless --help` 正常，现有 `headless` profile 可加载。
- Node 直接加载 `node-pty` 与 `koffi`，分别确认 `spawn` 与 `load` 导出可用。
- 最小真实模型请求 `dsh --profile headless '只回复 DSH_RC8_OK，不要使用工具。'` 返回 `DSH_RC8_OK`，验证现有登录、模型调用与会话存储链路。
- 临时 `NODE_OPTIONS` 未持久化；收尾时无 Node/npm/npx/DSH 残留进程，项目工作区在文档同步前保持干净。

### 当前结论与下一步

- DeepSeek Harness 运行时升级完成，但上游发行说明没有声明修复外部 npm `.cmd` 多行 argv 边界；本次也未修改 TALK bridge，因此不能把升级视为验收阻断项已修复。
- 下一切片继续绕过 `dsh.cmd` 调用 Harness Node 入口，并为预检失败增加跨轮询有界重试/退避与回归测试；完成后再做受控真实多行 prompt 探针。

### 变更文件

- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 TH-6d 真实三 Agent 人工验收中断与故障诊断

**背景**：`c01a6a9` 已把本地拓扑收敛为 Codex、DeepSeek Harness、Kimi3，但此前未调用真实模型。项目管理者按 TH-6d 人工验收说明启动 TALK Server 与三个 bridge，并从 Project Blackboard 创建真实任务树。本轮未修改功能代码；只完成现场复核、故障诊断、验收结论纠正和上下文交接。

### 实际验收进展

- 本地项目 Agent 索引确认包含 `agent:codex`（Lead / decision）、`agent:deepseek`（Dev / execution）、`agent:pi`（Reviewer / execution），三个 member 曾成功注册实例。
- 首次 `talk sync` 受本机 SOCKS proxy 环境影响，`httpx` 报缺少 `socksio`；通过在当前 PowerShell 清除 `ALL_PROXY / HTTP_PROXY / HTTPS_PROXY` 并为 localhost 设置 `NO_PROXY` 后恢复。这是本机启动环境问题，不是 TH-6d 协议缺陷。
- 核对数据库后确认 `group:talk-dev` 从未创建；`.talk/groups.yaml` 只保存本地角色/profile 元数据。此前要求去该 Hall 成员面板删除 Claude / pi-kimi、加入 DeepSeek 的指引错误，后续人工验收不再包含该步骤。
- Human 创建根任务 `#10` 并分配给 `agent:codex`；根任务成功 claim 并进入 `running/in_progress`。随后从根详情创建 Development 子任务 `#11` 并分配给 `agent:deepseek`。
- 截止收尾复核，旧 bridge 进程均已停止；数据库保留 `#10 running/in_progress` 与 `#11 queued/assigned` 现场，作为后续故障修复与清理依据。

### 验收发现 1：委派任务弹窗与流程文案

- Codex in-app Browser 真实复现：委派任务遮罩存在，但 `.task-create-panel.modal-card` 本身透明，标题和标签直接叠在 Blackboard 上。
- 计算样式确认卡片为 `background: rgba(0,0,0,0)`、`border: 0`、`box-shadow: none`。CSS 中卡片外观仅应用于 `.group-create-panel / .details-card / #composer / .auth-card`，`.modal-card` 只定义尺寸和滚动，导致任务弹窗漏掉背景层。
- 根任务与子任务共用静态标签“执行 Agent”。实际流程是两阶段：首次“＋委派任务”选择根任务负责人；根运行后再从详情点击“创建开发 / Review / Test 子任务”选择子任务执行 Agent。旧验收说明虽分别写了 Codex / DeepSeek，却未说明选择发生在两个窗口，造成误导。
- 后续修复应补齐 modal card 背景/边框/阴影，并按上下文显示“根任务负责人”与“子任务执行 Agent”及必要帮助文案。

### 验收发现 2：DeepSeek Harness 未接收 Development

- `#11` 始终保持 `queued/assigned`、`attempt=0`、无 claim；DeepSeek instance 进入 `error`，错误为 `task queue worker failed: task preflight did not return a valid TALK_TASK_PREFLIGHT decision`。
- `headless` profile 为官方默认空覆盖，实际 provider/model 为 `deepseek-official/deepseek-v4-pro`，证明 Harness 登录和模型调用可用；不是 API Key、模型或任务正文配置错误。
- 只读解码 `$DSH_HOME` 的持久 session 后确认，TALK 生成的完整多行预检 prompt 经 Windows `dsh.cmd` 后，模型实际只收到第一行“你是 agent:deepseek，通过 dsh CLI bridge 接入 TALK。”；任务编号、标题、正文和 `TALK_TASK_PREFLIGHT` 输出合同全部丢失。DeepSeek 因此把调用当成接入握手并返回就绪说明。
- 根因位于 TALK `--prompt-transport argv` 与 Windows npm `.cmd/cmd.exe` 包装的多行参数兼容边界。Harness 已在 Windows profile 内默认使用 `pwsh`，但这发生在模型工具层，不能修复进入 Harness 之前的 `dsh.cmd` 参数损失。
- 首选修复：原生 Windows 继续运行 TALK，但 bridge 绕过 `dsh.cmd`，直接调用 Harness Node 入口并添加多行 prompt 回归；WSL/Linux 可作为后备环境，不作为第一修复路径。

### 验收发现 3：预检失败无限重试

- `_prepare_task_before_claim()` 每次轮询先调用一次预检，协议解析失败后再调用一次 repair prompt；两次仍失败会抛错。
- `run_task_queue_worker()` 捕获异常后只上报 instance error，随后继续下一轮轮询同一 queued task，没有任务级失败计数、退避或 poison-task 隔离。
- 真实现场数分钟内生成至少 24 个 DSH 一次性 session，存在重复计费、额度消耗与日志膨胀风险。项目管理者已被提示立即停止 DeepSeek bridge；2026-08-21 复核时相关进程均不存在。
- 后续必须增加跨轮询有界失败策略，并让相同阻断任务进入可观察、可人工恢复的状态；不能仅依靠一次调用内的 repair retry。

### 当前结论与下一步

- TH-6d 实现层的自动化与隔离浏览器闭环仍有效，但真实 Codex → DeepSeek → Kimi3 人工验收未完成，里程碑不能判定通过，也不能进入 TH-7。
- 项目管理者决定先修复验收阻断项：优先处理 DeepSeek Windows 多行 prompt 与预检重试保护，再修复任务弹窗视觉和两阶段标签。
- 修复完成后先安全处理旧 `#10/#11` 现场，从干净根任务重新跑 Development、Review、Test、自动暂停和人工验收完整闭环。

### 验证与变更文件

- 只读验证：Codex Browser DOM/截图/计算样式、SQLite 任务与 instance 状态、DSH Zstandard session 解码、官方 Harness 本地包源码与文档、Git 状态与进程状态。
- 未修改功能代码、数据库或 Harness 用户配置；未继续执行 Review / Test。
- 变更文件：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

---

## 2026-08-16 本地 Agent 拓扑收敛：Codex + Kimi3 + DeepSeek Harness

**背景**：项目管理者明确后续本地暂时只使用 3 个 Agent：Codex、通过 pi 接入的 Kimi3、通过 DeepSeek Harness 接入的 DeepSeek 各类模型；Claude Code 不再纳入当前本地拓扑。本片仅收敛 bridge 模型锁定、项目配置和相关文档，不调用真实模型。

### 完成事项

- 本地拓扑固定为：`agent:codex` = Lead / decision，`agent:deepseek` = DeepSeek Harness / Dev / execution，`agent:pi` = Kimi3 / Reviewer / execution。
- `.talk/groups.yaml` 移除 `agent:claude` 与 `agent:pi-kimi`，新增 `agent:deepseek`；保留 `agent:pi` member ID，避免现有 TALK Key 与历史消息迁移。
- 删除重复的 `agent_pi-kimi` profile，将 `agent_pi` 身份收敛为 Kimi3，新增 `agent_deepseek` 四件套 profile，并同步 Codex 的同伴 Agent 说明。
- `bridges/pi_bridge.py` 新增 `--pi-provider / --pi-model`；默认命令、Task runner 命令与领取前预检命令会统一注入锁定的 provider / model，且自定义 `--pi-command` 的原有覆盖语义保持不变。
- 本机 pi 全局默认仍是 DeepSeek，因此 TALK 启动命令显式锁定 `--pi-provider moonshotai-cn --pi-model kimi-k3`，不修改用户级 pi 配置。
- 确认已安装官方 `@deepseek-ai/dsh 0.1.0-rc.6`；使用通用 bridge 的 `argv` transport 调用 `dsh.cmd --profile headless`，无需新建专用 bridge。
- `AGENTS.md`、`PROJECT_BRIEF.md` 与 `MODULE_bridges.md` 已同步新拓扑、身份、命令和已知边界。

### 验证

- `codex.cmd --version` → `0.144.4`；`pi.cmd --version` → `0.84.1`；`dsh.cmd --version` → `0.1.0-rc.6`。
- `dsh.cmd --profile headless --help` 在隔离的临时 `DSH_HOME` 中确认接受 argv 任务并输出最终 assistant 消息。
- `pi.cmd --list-models kimi` 确认 `moonshotai-cn/kimi-k3`；`pi.cmd auth check --provider moonshotai-cn --model kimi-k3 --json --no-refresh` 返回 `status=ready`。
- 项目 profile 扫描结果精确为 `agent:codex / agent:deepseek / agent:pi`。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge tests.test_talk_cli -q` → `Ran 145 tests in 9.073s ... OK`。
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py` 与 `git diff --check` 通过。

### 边界 / 待验收

- 未实际调用 Kimi3 或 DeepSeek 模型，未运行真实 TALK 消息 / Task Hall 往返；避免未经确认消耗模型额度。
- `talk sync` 只全量替换项目 Agent 索引，不会删除运行中 Group 的旧成员关系；启动 `agent:deepseek` 并同步索引后，仍需在 `group:talk-dev` 成员面板人工移除 Claude / pi-kimi、加入 DeepSeek。
- 当前无独立全能 Tester；Kimi3 可做 API / 日志 / 自动化检查，浏览器操作由项目管理者完成。
- TH-6d 里程碑仍保持 `awaiting_human`，不进入 TH-7。

### 变更文件

- `bridges/pi_bridge.py`、`tests/test_pi_bridge.py`
- `.talk/groups.yaml`、`.talk/agents/`
- `AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

---

## 2026-07-31 TH-6d：里程碑 Test 门禁、Blackboard 控制与人工验收

**背景**：TH-6c 已落地任务类型、冻结关系、结构化 Review 与两轮返工，但 Test 尚未成为根任务完成门禁，批次安全收尾和里程碑通过后也不会自动暂停。项目管理者确认继续 TH-6d。该切片同时涉及数据库、任务协议和前端真实交互，按决策 Agent 高风险单切片刹车完成后暂停等待人工验收，不进入 TH-7。

### 数据与服务端状态机

- 根任务新增 `milestone_test_required`，仅可委派根任务可开启；旧库迁移回填 `false` 并建立索引。
- `GET /api/tasks/{id}/tree` 新增 `test_gate`，返回是否必需、当前完整冻结版本 id 集、覆盖它的 Test、结构化结论和满足状态。
- 里程碑 Test 只能在全部最新必需 Review 通过后创建，并且必须精确覆盖根任务的完整最新冻结版本集；质量任务使用版本语义槽阻止重复或并发终结结论。
- `failed` Test 可作为返工触发器；返工成功后冻结版本切换，旧 Review / Test 结论不再覆盖新版本，必须重新取得门禁。
- 根任务成功完成前统一检查非终态后代、最新冻结结果、必需 Review 与里程碑 Test；旧 `general` 根任务保持兼容。
- 非里程碑批次额度耗尽后，既有开发与 Review 安全收尾即自动进入 `awaiting_human / batch_limit`。
- 里程碑 Test 得到 `passed` 后，根任务原子进入 `awaiting_human / milestone` 并撤销活动 claim；Human 新入口 `POST /api/tasks/{id}/accept-milestone` 验收后递增授权 epoch、清除检查点，但不自动增加开发额度。
- Review / Test 的 `blocked`、runner 失败或取消会释放未形成终结结论的版本槽，允许安全重试。

### SDK 与 Project Blackboard

- async / sync `create_task()` 增加 `milestone_test_required`，新增 `accept_task_milestone()`。
- 根任务创建表单增加委派开关、1–3 个切片额度和里程碑 Test 标记。
- 类型化子任务表单支持 `development / review / test / rework / general`、Review 策略、冻结任务多选和返工触发任务。
- 任务详情新增治理卡，展示根控制状态、检查点、授权 epoch、剩余切片、非终态后代、Review 门禁和 Test 门禁。
- 页面补齐提交最新澄清答复、释放人工决策、暂停整树、风险检查点、授权继续一批、人工验收通过、终止整树等动作。
- 质量任务下拉框增加稳定的可访问名称；Web 资源更新缓存版本。

### 验证

- Python `py_compile` 覆盖模型、迁移、任务路由、async / sync SDK 和相关测试文件；`node --check web/app.js` 通过。
- 新增自动化覆盖：里程碑 Test 通过后暂停且根任务不能提前完成、Human 人工验收、非里程碑批次安全检查点、Test 失败触发返工、返工后旧 Test 失效、旧库字段回填和 Web 控制入口。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q`，`Ran 370 tests in 122.729s ... OK`。
- Codex in-app Browser 真实贯通：Human 创建带里程碑 Test 的根任务并从页面创建开发子任务；Review 与完整 Test 通过后，页面显示 `awaiting_human / milestone`、Review `approved`、Test `passed` 和“人工验收通过”；验收后根恢复 `active`、epoch `1 -> 2`、剩余开发额度保持 0。
- 页面控制台没有 `error / warning`；临时隔离服务与浏览器验收数据库已停止并清理。
- `usage-gate.cmd guard --provider codex --json` 返回 `decision=continue`；session / weekly 精确百分比均为 `null`，本轮仍按高风险单切片与里程碑门禁停止。

### 文档与边界

- 同步 `docs/spec/MODULE_tasks.md`、`docs/PROJECT_BRIEF.md`、`docs/guides/USER_MANUAL.md` 和当前进度快照。
- 服务端可强制冻结关系和结构化门禁，但无法从自由文本角色证明第三方 Tester 的操作系统级工具能力；正式运行仍需配置能启动隔离服务、调用 API、控制浏览器和读取日志的 Tester。
- TH-6d 当前等待项目管理者人工验收；验收通过前不进入 TH-7。

### 变更文件

- `server/models.py`
- `server/db.py`
- `server/routes/tasks.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `tests/test_tasks.py`
- `tests/test_task_web_ui.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROJECT_BRIEF.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-07-26 TH-6c：结构化 Review、返工关系门禁与角色发现

**背景**：TH-6b 已让 bundled runner 在领取前完成预检与澄清，但任务仍缺少开发 / Review / Test / 返工的强类型、显式关系和服务端质量门禁。项目管理者授权继续下一切片，并说明暂时无暇人工验收。由于本轮涉及数据库、任务协议与跨模块 runner，按决策 Agent 的高风险批次刹车只推进 TH-6c，不进入 TH-6d。

### 数据与服务端合同

- `agent_tasks` 新增 `task_kind`、`review_policy`、JSON `gate_verdict`；旧任务迁移为 `general`。
- 新增 `agent_task_relations`，记录 `reviews / tests / reworks`、触发任务和冻结版本轮次；迁移补齐索引与唯一约束。
- 类型化任务只允许作为子任务；同根、同项目、当前 `authorization_epoch`、授权有效期和非终态后代上限由服务端校验。
- `general / development` 消耗授权切片；`review / test / rework` 不消耗新的开发切片。
- `development` 默认 `required` Review；低风险 `batch` 一次覆盖同批次 2–3 项；`exempt` 仅 Human 或项目 `decision_tier=decision` 的 Agent 可授权。
- Reviewer 必须与所有被审任务执行者不同。开发 / 返工成功必须引用结果消息；Review / Test 成功必须提交匹配类型的结构化 verdict，负向结论必须带 findings。
- `GET /api/tasks/{id}/relations` 返回显式关系；`quality-context` 向质量任务创建者 / 执行者只读开放关联任务、触发任务及完整 Task Hall。
- 类型化任务树只有在所有非终态后代结束、最新开发 / 返工成功且必需 Review 为 `approved` 时才能完成；纯 `general` 旧流程不被追溯阻断。
- 同一质量问题最多自动返工两轮；第 2 轮返工再次得到 `changes_requested` 时，根任务在同一事务进入 `awaiting_human / review_exhausted` 并撤销其它 claim。

### Review 冻结版本语义槽

独立集成审查发现，若允许同一冻结版本重复创建 Review，后续 `approved` 可以覆盖先前 `changes_requested`，并绕过返工上限。最终合同收敛为：

- Review relation 按当前冻结版本轮次 `0 / 1 / 2` 占用唯一语义槽，并发创建只能一条成功。
- `approved / changes_requested` 是终结语义，保留槽位；原版本不能再次 Review。
- runner `failed`、任务 `canceled` 或结构化 `blocked` 不形成批准 / 变更结论，会在完成或取消事务中释放槽位，允许同一冻结版本重试。
- 根门禁因此不会把未变化版本上的后续结论当作对既有变更请求的覆盖。

### Runner、SDK 与工具

- bundled runner 为 Review / Test 注入显式 `TALK_GATE_VERDICT` 合同，读取关系授权的完整质量上下文，首次格式错误有界纠正一次。
- runner 只把解析出的结构化结论传给 `complete`；若 Task Hall 结果回写失败，任务按 `failed` 完成且不携带 verdict，避免服务端 422 后卡在 `running`。
- async / sync SDK 支持类型、Review 策略、关联任务、触发任务、结构化 verdict，以及 relations / quality-context helper。
- CLI 从 `.talk/groups.yaml` 聚合自由业务角色、决策分级和能力列表；跨群组角色稳定去重，分级冲突显式报错。
- 项目 Agent API 与 `talk_list_agents` 返回 `business_role`、`decision_tier`、`capability_summary`、实例列表和聚合可用状态。
- Python MCP 与 Pi extension 保持原有八个工具名，扩展 typed delegate、类型过滤、关系读取和项目 Agent 富化结果。

### 验证与审查

- Python `py_compile` 覆盖服务端模型 / 迁移 / 路由、CLI、async / sync SDK、runner 与 Python 工具；Pi TypeScript 通过 Node 语法检查。
- 服务端 + runner 定向回归：`Ran 166 tests in 39.405s ... OK`。
- CLI / SDK / Python MCP / Pi 工具联合回归：`Ran 48 tests ... OK`。
- 最终全量回归：`Ran 366 tests in 147.008s ... OK`。
- 首次全量命令因外部 5 分钟工具时限被终止，没有最终结果；提高时限后从头完整重跑通过。
- 独立只读集成审查覆盖权限 / epoch / 项目范围、切片非消费、批量 Review、两轮返工原子暂停、结构化 verdict、关系上下文、并发唯一性、旧 `general` 兼容与角色发现；修复上述两个失败路径后无剩余阻断项。
- `usage-gate.cmd` 返回 `decision=continue`，但没有提供 session / weekly 精确百分比；未臆测具体额度，仍按数据库 / 协议高风险单切片规则停止。
- 本切片未修改 Web，按 Browser 约定无需页面验证。

### 当前边界

- `test` 类型、关系和结构化 verdict 已持久化，但根任务 Test 门禁、最新冻结版本失效、Blackboard 质量控制与测试通过后的人工验收暂停属于 TH-6d。
- Review 的“只读”由 bundled runner prompt 约束；服务端不能替代第三方 Reviewer 的操作系统文件写权限隔离。
- Web 尚无 Review / 返工创建、关系查看、结构化结论和质量检查点入口。
- 项目管理者本轮暂时无暇人工验收；自动化与代码审查完成后按高风险单切片规则暂停，未把验收门禁永久取消。

### 变更文件

- 服务端：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`server/routes/projects.py`
- SDK / CLI / 工具：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`、`cli/talk.py`、`bridges/cli_bridge.py`、`bridges/talk_task_tools.py`、`bridges/talk_tools_extension.ts`
- 测试：`tests/test_tasks.py`、`tests/test_projects.py`、`tests/test_cli_bridge.py`、`tests/test_talk_cli.py`、`tests/test_talk_client.py`、`tests/test_talk_task_tools.py`
- 文档：`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_tasks.md`、`docs/guides/USER_MANUAL.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

### 下一步

1. 暂停并提交 / 推送 TH-6c 可回溯版本。
2. 项目管理者恢复后进入 TH-6d：里程碑 Test 门禁、最新冻结版本、Blackboard 控制、批次自动检查点与人工验收暂停。
3. TH-6d 构成下一处里程碑门禁，完成后必须提供人工验收说明并等待确认。

## 2026-07-26 TH-6b：runner 领取前预检、自动澄清与完整 Hall 重放

**背景**：TH-6a3 已建立澄清轮次和服务端状态门禁，但 bundled runner 仍会从 `assigned` 直接 claim，正式执行也只获得任务标题 / 正文。本轮属于 runner / 协议高风险切片，按批次刹车只完成 TH-6b，并同步落实项目管理者确认的 Codex 决策 Agent 身份，不进入 TH-6c Review 门禁。

### Agent 分级

- `AGENTS.md` 明确当前普通 Codex 项目会话按决策 Agent 工作；bridge 内成员继续以启动时注入的 `decision_tier` 为权威，未声明的其它成员仍按执行 Agent。
- `.talk/groups.yaml` 已有 `agent:codex = lead + decision`。通用 CLI bridge 在传入 `--project` 且没有显式 `--decision-tier` 时会从项目配置解析分级；显式命令行覆盖保持最高优先级。
- Codex / pi 的普通任务和预检 prompt 都携带解析后的决策分级，避免模型只看到业务角色而不知道行为边界。

### 实现

- 对带 Task Hall 的 `assigned / clarification_answered` 任务，runner 会先分页读取完整 Hall，再以独立只读 / 无工具命令做领取前预检；Codex 预检不挂载 TALK MCP，pi 预检不启用本地工具或 extension。
- 预检信息充分时先 `accept`，随后才 `claim`；信息不足时把一批集中问题写入同一个 Task Hall，并以问题消息 id 原子登记澄清轮次。`clarification_requested / needs_decision` 不会重复唤醒。
- 自动问题使用稳定的任务 / 澄清轮次标记。若进程在“问题消息已发送、澄清动作尚未登记”之间退出，下次轮询会复用已有问题完成登记，不重复调用模型或再发一条消息。
- `accepted` 表示预检已完成，runner 重启后可以直接 claim；`clarification_answered` 会携带 A 的显式答复重新预检。
- Hall 以 500 条为一页向前分页，去重后按消息 id / 时间顺序重放。正式执行 prompt 复用同一份完整上下文，包含任务原文、问题、答复和可见文件元数据；附件正文仍不自动下载。
- 解析器只接受显式结构化结论，兼容单行 `TALK_TASK_PREFLIGHT`、显式标记后的多行 JSON 以及真实 Pi 出现的嵌套 / `ready` 变体；纯自然语言不会被猜测为接受。
- 成功命令首次返回无效格式时，runner 会用同一个只读 / 无工具命令纠正一次；超时、非零退出或再次无效都不会 claim，也不会消耗澄清轮次。
- Codex 重复任务执行实现收敛为共享 `cli_bridge.handle_queued_task`，保留 Codex command adapter 和原测试替换点，减少两套 runner 行为漂移。

### 测试

- 单元测试覆盖项目分级解析与显式覆盖、预检 prompt 合同、结构化变体解析、首次格式纠正、完整分页顺序、充分后先 accept 再 claim、同 Hall 澄清、等待状态过滤和中断窗口恢复。
- Codex / pi 测试锁定预检命令始终为只读 / 无工具配置，即使正式执行选择 tools profile 也不会在领取前修改项目或调用 TALK 投递工具。
- 活服务 E2E 覆盖 `created -> 自动提问 -> clarification_requested -> Human 回答并显式提交 -> 重新预检 -> accept -> claim -> execute -> complete`；正式执行 prompt 断言能看到答复中的 `8123`。
- Python `py_compile` 通过。
- 定向回归：`Ran 168 tests in 28.697s ... OK`。
- 全量回归：`Ran 348 tests in 154.472s ... OK`。
- 较早的一次混合定向命令误含不存在的测试模块，并命中既有 WebSocket 降级用例的固定 2 秒退出超时；该用例随后连续单跑两次通过，最终全量回归也通过。本切片没有修改 WebSocket 降级路径。
- 真实 Codex 只读预检返回可解析的显式结构化结论。真实 Pi 返回显式多行 `ready=false`，基础设施安全阻止 claim；但它忽略了正文中已给出的信息并要求重复任务，记录为模型理解质量残余，不伪造成语义验收通过。
- 本切片没有修改 Web 页面，按 Browser 验证约定无需做页面验证。

### 用户手册影响

- `docs/guides/USER_MANUAL.md` 已用非技术语言说明 Agent 会在领取前检查完整 Task Hall；信息不足会在原 Hall 提问并保持待响应，Human 明确提交答复后 Agent 会重新读取全部上下文。

### 变更文件

- `AGENTS.md`
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_task_hall_e2e.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. 暂停等待项目管理者确认本切片。
2. 确认后进入 TH-6c：任务类型、任务关系、结构化 Review / 返工门禁与业务角色发现。
3. 后续 TH-6d 再实现里程碑黑盒测试、Blackboard 控制、批次自动检查点与人工验收暂停。

## 2026-07-20 TH-6a3：Task Hall 有界澄清轮次与决策阻塞

**背景**：TH-6a0 已冻结“一批集中问题 + 一批完整答复”按轮计数、默认 1 轮、绝对上限 2 轮的合同；旧实现只有 `clarification_requested` 状态，普通回复与完整答复无法区分，也没有额度耗尽后的阻塞。由于本轮涉及数据库、协议和根控制传播，按高风险切片刹车只完成 TH-6a3，不进入 runner 自动预检或 Web 控制入口。

### 实现

- `agent_tasks` 新增 `max_clarification_rounds / clarification_round_count`；旧库默认回填 1 / 0。创建任务只接受 1–2 轮，schedule 物化任务保持默认 1 轮。
- 新增 `agent_task_clarification_rounds` 账本，按任务和轮次保存问题消息、答复起止消息与时间；`task_id + round_index` 唯一，配合条件更新保证并发请求只建立一轮。
- B 必须先在 Task Hall 发送问题，再调用 `request-clarification` 登记边界；A 可连续补充多条，最后调用 `submit-clarification-answer` 明确结束答复。普通 Hall 回复不会改变状态。
- 新增 `clarification_answered / needs_decision`。显式答复后仍禁止直接 claim，B 必须 `accept`；额度耗尽时任务进入 `needs_decision`，根任务进入 `awaiting_human / needs_decision`，活动 claim 被撤销。
- 新增 `resolve-clarification`：Human、当前任务请求者或根请求者可补充范围后释放，或增加一轮额度；绝对上限仍为 2。根控制保持等待，需单独 `resume-tree` 恢复，防止解决局部澄清时意外放开全树。
- async / sync SDK 新增轮次查询、问题登记、答复提交和人工释放 helper；Python MCP 与 pi extension 的 `talk_reply_task` 使用当前 Hall 消息 id 作为问题 / 答复边界，并支持人工释放动作。
- 旧无 Hall / 无轮次账本的澄清任务保留兼容接受路径；旧客户端从 `assigned` 直接 claim 继续兼容，但新澄清三态均受服务端 claim 门禁约束。

### 测试

- 覆盖 1–2 轮创建边界、错误发送者边界、普通回复不推进、重复问题 / 答复幂等、多条答复起止边界和明确接受后才能 claim。
- 覆盖额度耗尽进入 `needs_decision / awaiting_human`、错误解决者拒绝、增加一轮、显式恢复根控制、绝对上限 2 和再次耗尽。
- 使用两个并发客户端同时登记不同问题，验证仅一个请求成功、计数为 1 且只有一条账本记录。
- 迁移测试验证旧任务字段回填及轮次唯一索引；async / sync SDK 与 Task Hall 工具活服务流程均贯通新协议。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -q`：`Ran 32 tests in 17.814s ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 337 tests in 118.141s ... OK`。
- Python `py_compile`、TypeScript `node --experimental-strip-types --check` 与 `git diff --check`：通过。
- 本切片无 Web 代码改动，不需要 Browser 验证。

### 用户手册影响

- 已同步 `docs/guides/USER_MANUAL.md`：使用非技术语言说明普通消息不会自动结束澄清、默认一轮 / 最多两轮和额度耗尽会暂停；页面尚无提交答复或人工决策入口，因此只说明需项目负责人协助，不写启动服务、API 或开发命令。

### 变更文件

- `server/models.py`
- `server/db.py`
- `server/routes/tasks.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/talk_task_tools.py`
- `bridges/talk_tools_extension.ts`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `tests/test_talk_task_tools.py`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. TH-6b：让 bundled runner 在 claim 前预检任务充分性，自动进入同 Hall 澄清、等待显式答复，并分页重放完整任务 / Hall 上下文。
2. TH-6c / TH-6d：再进入 Review / Test 门禁与 Blackboard 最终用户控制入口；本高风险切片完成后先暂停汇总，不连续开启下一切片。

---

## 2026-07-20 TH-6a2.2：bundled runner 最长 5 秒协作中断

**背景**：TH-6a2.1 已能在服务端持久化暂停 / 检查点 / 整树终止并立即撤销运行 claim，但 bundled runner 默认每 30 秒才续租一次，导致本地 CLI 进程不能在合同要求的 5 秒窗口内感知控制。本轮按 runner 高风险切片只补协作中断，不进入澄清轮次、Web 控制入口或 Review/Test 门禁。

### 实现

- `bridges/cli_bridge.py` 将 bundled runner 默认 claim heartbeat 调整为 5 秒，并新增 5 秒硬上限；即使启动参数显式传入更长的 `--task-heartbeat-interval`，有效 claim / 控制探针也不会被放宽。
- claim heartbeat 继续由服务端原子校验根控制状态。暂停、检查点、整树终止或其它 claim 失效返回 `404 / 409` 时，runner 抛出 `TaskLeaseLostError` 并取消正在等待的命令。
- 通用 CLI runner 与 Codex 兼容 runner 共用上述守卫；命令协程取消会进入 `run_cli_command` 的既有清理路径，终止并回收本地子进程。
- 控制中断后 runner 不发送 Task Hall 结果消息、不调用 `complete`；暂停 / 检查点的 `queued / accepted` 回队和整树终止的 `canceled` 状态继续由服务端作为唯一真相源。
- 服务不可达时 runner 无法接收新的控制事实，仍由现有本地租约截止时间提供最终失效保护；第三方 runner 也仍需自行实现相同协议。

### 测试

- 新增有效 claim / 控制探针间隔测试，覆盖默认 30 秒配置被硬性收敛到 5 秒、显式更短间隔和短租约自适应。
- 新增真实 Python 子进程取消测试，确认取消执行协程会及时终止本地进程。
- 通用 CLI runner 覆盖 `paused / awaiting_human / canceled` 三类控制撤销，Codex runner 单独覆盖共享守卫接入；均断言本地命令被取消，且没有发送结果或调用 `complete`。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge -q`：`Ran 112 tests in 0.643s ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 153 tests in 15.782s ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 334 tests in 97.578s ... OK`。
- 本切片无 Web 改动，不需要 Browser 验证。

### 用户手册影响

- 已检查 `docs/guides/USER_MANUAL.md`：暂停 / 继续 / 整树终止尚无最终用户页面入口，仍不能写成可操作步骤，因此本轮不修改用户手册；模块合同和进度文档记录后台能力已完成。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. TH-6a3：实现澄清轮次账本、显式答复提交、`clarification_answered / needs_decision` 与服务端 claim 门禁。
2. TH-6b：在轮次合同落地后接 runner 领取前预检、完整 Hall 上下文重放和自动澄清闭环。

---

## 2026-07-20 TH-6a2.1：根控制状态与有限批次授权服务端落地

**背景**：项目管理者确认 TH-6a0 的有限批次与随时喊停合同，并授权以决策 Agent 身份推进下一切片。由于本轮涉及数据库 / 协议和权限边界，按批次刹车只完成 TH-6a2.1 服务端控制面，不进入 bundled runner 协作中断或 Web 控制按钮。

### 已完成

- `agent_tasks` 根任务新增 `control_status`、`authorization_epoch`、`authorized_slice_budget`、`reserved_slice_count`、`authorization_expires_at`、`checkpoint_reason`；控制状态与到期时间补齐索引。
- 新建可委派根任务默认获得 2 个切片、90 分钟授权，Human 可显式设为 1–3 个切片与 60–5400 秒；恢复会递增 epoch、重置本批次预留数并生成新到期时间。
- 新后代创建必须提交当前 `authorization_epoch`，并在同一条条件更新中原子检查根仍在运行、控制状态为 `active`、授权未过期、epoch 未陈旧、切片额度和非终态后代硬预算均有余额；并发创建只有预算内请求成功。
- claim 已把根控制状态与授权到期加入原子条件；过期创建 / claim 会把根任务推进到 `awaiting_human / time_limit`。旧 epoch 即使在恢复后晚到，也不能消费新批次授权。
- 新增 `pause-tree / resume-tree / checkpoint / cancel-tree / tree` 五个接口，传入任一后代 id 均解析到根任务，并分别约束根请求者、Human 管理者和根执行者权限。
- 暂停 / 检查点立即把运行任务安全回到 `queued / accepted`，清除 claim token、lease 与实例占用；整树终止取消全部非终态任务；Hall、消息、attempt、完成结果与历史任务行均保留。陈旧 runner 的心跳和完成写回由现有状态 / token 门禁拒绝。
- async / sync SDK 的 `create_task` 新增授权额度、有效期与 epoch 参数，并新增五个任务树控制 helper；活服务测试贯通暂停、恢复、检查点、查询和终止。

### 迁移与兼容

- 历史根任务回填为 `active`；历史不可委派任务使用 `epoch=0 / budget=0`，旧完成与结果收取不变。
- 历史可委派根任务使用 `epoch=1 / budget=2`，当前已有后代数计入 `reserved_slice_count`，避免升级后凭空获得额外切片；后代不复制根控制字段。
- 当前还没有 `task_kind`，所以每个新后代暂统一消费 1 个切片；`review / test / rework` 的免计与批次安全收尾后自动 `batch_limit` 检查点留待 TH-6c 的任务关系实现。
- 服务端现已立即撤销本地 runner 的执行与写回资格，但不会强杀正在运行的未知进程；bundled runner 最长 5 秒检查和本地子进程停止留待 TH-6a2.2。

### 验证

- `python -m py_compile server/models.py server/db.py server/routes/tasks.py TALK/client/talk_client.py TALK/client/talk_client_sync.py tests/test_tasks.py tests/test_talk_client.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -q`：`Ran 29 tests ... OK`；覆盖旧库迁移、历史委派树回填、并发切片预留、权限、暂停 / 恢复、检查点、整树终止、到期、陈旧 epoch，以及控制状态持久化后心跳 / 完成立即失效。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -q`：`Ran 12 tests in 17.354s ... OK`；async / sync 活服务控制流程通过。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 331 tests in 71.979s ... OK`。
- `git diff --check`：通过，仅有 Windows 工作区既有 LF / CRLF 转换提示。本切片没有前端改动，不需要 Browser 验证。

### 用户手册影响

- 已复核 `docs/guides/USER_MANUAL.md`：本轮只有服务端 API 与 SDK，还没有普通用户可见按钮，runner 也未完成主动中断，因此不把暂停 / 继续 / 整树终止提前写成正式操作步骤；手册现有“当前版本边界”保持正确。

### 变更文件

- 功能：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`。
- 测试：`tests/test_tasks.py`、`tests/test_talk_client.py`。
- 文档：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

### 下一步

- TH-6a2.2：实现 bundled runner 最长 5 秒控制检查、本地子进程协作中断与服务端暂停 / 终止状态联动。该切片涉及真实执行中断，完成后应暂停汇总并进行独立人工 / 黑盒验收准备。

## 2026-07-20 用户手册骨架与项目内同步规则

**背景**：项目管理者提出，任务暂停、澄清、Review 等机制最终都需要用非技术语言告诉普通使用者，同时确认不应让 TALK 的项目特有规则影响其它项目，也不应把开发环境启动命令混入最终产品操作手册。

### 已确认并完成

- 保持用户级全局 `project-framework` skill 不变；用户手册同步规则只落在 TALK 的 `docs/PROJECT_BRIEF.md`。
- 新增 `docs/guides/USER_MANUAL.md`，明确以“系统已经部署完成”为前提，只面向日常使用 TALK 的家庭成员或项目成员。
- 手册首版记录当前已验证的登录、项目黑板、任务委派、Task Hall 沟通、澄清补充、结果收取、未开始任务取消，以及全局消息流 / Group Hall 的使用方式。
- 尚未提供最终用户入口的暂停、继续、整树终止、澄清轮次和 Review/Test 只作为当前版本边界，不提前写成可操作步骤。
- `QUICKSTART_USER.md` 继续负责家庭管理员首次安装与启动，`DEPLOY.md` 负责部署运维，`QUICKSTART_AGENT.md` 负责开发者和 Agent 接入；普通用户手册不包含 Docker、Python、API、测试或本地开发启动命令。
- `docs/guides/QUICKSTART.md` 已增加日常用户手册入口；`PROJECT_BRIEF.md` 目录结构已登记新文档。
- 后续每个用户可见功能切片都要检查手册影响；只有真实入口落地并完成验证后才转写为正式操作步骤，里程碑人工验收需按手册从头复现。

### 验证

- `git diff --check`：通过，仅有现有 Windows LF / CRLF 转换提示。
- 用户手册技术命令关键词扫描：未发现开发步骤；`Python / Docker / API / 数据库` 只出现在“普通用户无需了解”的范围声明中。
- `USER_MANUAL.md`、`QUICKSTART.md`、`PROJECT_BRIEF.md` 的本地 Markdown 链接检查：全部可解析。
- 未运行功能测试：本切片只修改 Markdown 文档，没有修改产品代码。

### 变更文件

- `docs/guides/USER_MANUAL.md`
- `docs/guides/QUICKSTART.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

- TH-6a2.1：实现根任务控制状态、有限批次授权和服务端暂停 / 继续 / 检查点 / 整树终止控制面；完成时继续按本规则判断哪些内容可进入用户手册。

## 2026-07-18 TH-6a1：任务树与服务端硬预算落地

**背景**：项目管理者确认 TH-6a0 合同后，授权开始第一个数据库 / 协议代码切片。由于本轮未注入 `decision_tier`，按 `AGENTS.md` 兜底作为执行 Agent，只完成 TH-6a1 并在验证、进度落盘后暂停。

### 已完成

- `agent_tasks` 新增 `parent_task_id`、`root_task_id`、`delegation_depth`、`may_delegate`，以及根任务保存的 `max_delegation_depth`、`max_running_descendants`、`max_running_per_target`、`max_nonterminal_descendants`。
- 新根任务创建后 `root_task_id` 指向自身；旧数据库升级时，每个历史任务回填为独立根、深度 0、`may_delegate=false`，默认治理值为 1 / 3 / 1 / 8，并补齐父任务、根任务和深度索引。
- 顶层自定义治理仅允许 Human 设置；普通 Agent 仍可按旧接口创建顶层任务，但不能为自己授予委派能力或放宽根预算。
- 创建子任务要求父任务处于 `running / in_progress`、父任务已获 `may_delegate`，调用者是父执行者、根请求者或 Human；项目从父任务继承，深度和非终态后代预算由服务端事务校验。
- 非终态后代预留通过更新根任务的条件语句串行化并发创建；子任务 claim 通过同一条件更新原子校验根仍在运行、根运行后代和单目标运行预算，直接 REST API 与第三方客户端无法绕过。
- `TalkClient` / `TalkClientSync.create_task` 新增父任务、委派权限和四项根预算参数；活服务测试分别用异步和同步 SDK 创建一层子任务并验证父根关联、深度与项目继承。
- `docs/spec/MODULE_tasks.md` 已同步当前实现、迁移兼容、已知边界与后续实施顺序；TH-6a2 的控制状态、有限授权和 runner 协作中断没有提前实现。

### 验证

- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py TALK\client\talk_client.py TALK\client\talk_client_sync.py tests\test_tasks.py tests\test_talk_client.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -v`：`Ran 23 tests ... OK`；覆盖旧库迁移、委派权限、深度 / 项目继承、非终态创建竞争、根运行并发和单目标 claim 竞争。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -q`：`Ran 12 tests ... OK`。
- Task Hall / SDK / runner / 工具 / bridge 跨模块回归：`Ran 128 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 325 tests in 103.757s ... OK`。

### 变更文件

- 功能：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`。
- 测试：`tests/test_tasks.py`、`tests/test_talk_client.py`。
- 文档：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

### 已知边界与下一步

- 当前根任务尚无 `control_status`、授权 epoch 或切片额度；Human 仍不能通过服务端暂停整棵树，bundled runner 也没有最长 5 秒的暂停 / 终止轮询。
- 根任务当前仍可在后代未结束时自行完成，整树汇总与质量门禁要在后续控制、Review/Test 切片中收敛。
- 下一候选切片是 TH-6a2；按执行 Agent 规则，本轮不提交、不推送、不自动继续，等待项目管理者或决策 Agent 确认。

## 2026-07-18 TH-6a0：任务治理、可中断推进与质量门禁合同冻结

**背景**：TH-5 已贯通“页面委派 → bundled runner → Task Hall 结果 → Human 收取”的基础链路。项目管理者随后确认，下一阶段不能只补递归委派和澄清，还要把开发后的独立 Review、里程碑黑盒测试、人工验收，以及“主 Agent 有限自主推进、Human 可随时喊停”纳入正式流程。本切片只冻结协议和实施顺序，没有修改功能代码。

### 已确认的总体流程

```text
Human 有限批次授权
  -> 主 Agent 分配 development
  -> 开发 Agent 实现并自测
  -> 独立 review（不通过则 rework，最多自动两轮）
  -> 未到检查点时在剩余额度内继续
  -> 里程碑完整自动化回归 + 黑盒 / E2E test
  -> 根任务 awaiting_human
  -> Human 验收、调整、继续一批或终止
```

- 主 Agent 获得有限批次授权而非无限自治：普通小切片默认 2 个，纯文档 / 配置可显式授权到 3 个，高风险 / 跨模块默认 1 个。
- 批次、时间、风险、额度、Review、澄清或里程碑边界会自动暂停；Human 也可随时撤销尚未消费的授权。
- Review 覆盖每个功能切片，但低风险同模块任务允许 2–3 个批量审查；黑盒测试只在可独立体验的里程碑运行。
- 里程碑测试通过不等于自动进入下一阶段，根任务必须等待 Human 显式确认。

### 冻结的任务树与预算合同

- 新增 `parent_task_id / root_task_id / delegation_depth / may_delegate` 语义，旧任务迁移后各自成为独立根并保持兼容。
- 根任务统一保存最大深度、根运行并发、单目标并发和非终态后代预算；默认分别为 1、3、1、8。
- 创建子任务时校验调用者、父任务、根控制状态、委派权限、深度和非终态预算；claim 时再次原子校验根与单目标并发。
- 子任务默认不能继续委派，只有根控制者显式提高深度并授权具体任务后才能突破默认能力边界。
- 直接 REST API、TALK 自带工具和第三方客户端适用相同拒绝规则，不能依赖 runner 工具裁剪或进程内锁。

### 冻结的有限授权与暂停合同

- 根任务使用独立 `control_status`：`active / pause_requested / paused / awaiting_human / cancel_requested / canceled`，不污染现有执行五态和协作状态。
- 每次 Human “继续一批”生成新的 `authorization_epoch`、切片预算和有效期；陈旧主 Agent 不能使用旧授权继续创建任务。
- `pause-tree` 立即禁止新建后代和 claim；bundled runner 最多每 5 秒检查控制指令，安全终止本地子进程并失效 claim token。
- 暂停后的任务保留 Hall、消息、attempt 与现场，可恢复为 `queued / accepted` 后重新领取；整树终止与可恢复暂停严格区分。
- 第三方 runner 若不支持协作中断，服务端至少撤销写回资格并依靠租约回收，不承诺跨机器强杀未知进程。

### 冻结的澄清与质量门禁合同

- 澄清默认最多 1 轮、显式可提高到 2 轮；一轮是 B 的集中问题批次与 A 的完整答复，不按消息数计数。
- A 可连续补充多条消息，以 `submit-clarification-answer` 显式结束答复；额度耗尽仍不足时进入 `needs_decision` 并暂停根任务。
- 新增 `general / development / review / test / rework` 任务类型；Review / Test 使用独立 Task Hall 和结构化 `gate_verdict`，不能从自然语言猜测通过结论。
- Review 结论为 `approved / changes_requested / blocked`，测试结论为 `passed / failed / blocked`；返工产生新任务并保留旧结果。
- 旧冻结版本的 Review / 测试结论在新返工后失效；必需 Review 或里程碑最新测试未通过时，服务端拒绝根任务提交成功结果。
- `business_role` 保持项目自定义自由文本；工具和项目 API 返回角色与能力摘要，但质量强语义由 `task_kind`、任务关系和门禁结论提供。

### 实施顺序

1. TH-6a1：任务树字段、迁移和服务端硬预算。
2. TH-6a2：有限批次授权、暂停 / 继续 / 整树终止与 runner 协作中断。
3. TH-6a3：澄清轮次账本、答复提交和 `needs_decision`。
4. TH-6b：runner 领取前预检、完整 Hall 上下文与自动澄清。
5. TH-6c：Review / 返工门禁和角色发现。
6. TH-6d：里程碑测试、Blackboard 控制和人工验收暂停。
7. TH-7：Codex Desktop / 通用终端接入。

### 验证与变更

- 验证：仅文档切片；完成 Markdown 结构、关键合同覆盖和 `git diff --check` 检查，未运行功能测试。
- 变更文件：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 提交状态：当前按执行 Agent 规则未提交，等待项目管理者确认是否进入 TH-6a1 或先提交文档切片。
- 下一步：TH-6a1，实现任务树字段、旧库迁移和服务端硬预算并发测试。

---

## 2026-07-16 Task Hall 委派深度、并发预算与澄清轮次决策

**背景**：项目管理者在准备切换上下文前，确认需要为跨终端委派加入类似 Codex 子 Agent 的递归与并发保护，并讨论任务执行者领取前是否只允许一次澄清机会。本轮只核对现状、冻结产品规则和更新进度，没有修改功能代码。

### 现状核对

- bundled runner 的嵌套任务命令默认不向执行模型暴露 TALK 委派工具，因此标准路径近似默认委派深度 1；但这是客户端 / runner 软保护。
- `POST /api/tasks` 仍允许任意已认证成员创建任务，`agent_tasks` 尚无父任务、根任务、委派深度、委派授权或任务树预算字段；自定义客户端仍可能递归创建任务。
- 单个 bridge 进程使用共享运行锁串行调用模型，但多个 bridge 实例之间没有根任务级 / 项目级并发上限；claim 只防止同一任务被重复执行，不限制任务树扇出。
- Task Hall 已有 `clarification_requested`、Hall 消息、`accept` 和待澄清禁止 claim 的基础状态，但没有澄清轮次、明确的答复提交动作或额度耗尽后的阻塞状态。Discussion Hall 的 `max_rounds` 与该流程无关。

### 已确认的硬保护默认值

- 服务端默认最大委派深度为 1；子任务默认不能继续委派，只有主控显式授权时才能获得继续拆分能力。
- 单个根任务同时执行的子任务上限为 3；单个目标 Agent 同时执行上限为 1；单个根任务累计非终态子任务上限为 8。
- 保护必须在任务创建、领取等服务端入口原子校验，覆盖 TALK 自带工具、直接 REST API 和第三方客户端，不能只依赖 bundled runner 的工具裁剪或进程内锁。
- 实现需要补父任务 / 根任务关联、委派深度与授权、并发 / 扇出预算等字段；具体字段名可在 TH-6a 收敛，但已确认的默认行为保持不变。

### 已确认的澄清规则

- 默认最多 1 个澄清轮次；复杂任务可由主控在委派时显式提高到 2 轮，不允许无限追问。
- 一轮表示“B 的一批集中问题 + A 的完整答复”，而不是只能写一个问句或一条消息。B 应一次汇总所有已知疑问，可在同一 Hall 消息中使用多个编号问题。
- A 可以在同一 Hall 连续补充多条说明，最后通过显式“提交澄清答复”动作结束该轮并唤醒 B；普通回复消息不应过早触发 B 重新判断。
- B 被唤醒后携带任务原文和按时间排序的完整 Hall 上下文重新预检；信息充分才 `accept → claim → execute`。
- 澄清额度耗尽后仍无法执行时，任务必须进入 `blocked / needs_decision`（最终状态名在实现时收敛）并交回主控修改、取消或显式授权，禁止强制领取或猜测执行。

### 下次恢复顺序

1. TH-6a：先落服务端任务树、深度 / 并发预算和澄清轮次协议及数据库迁移、SDK / 工具契约与并发测试。
2. TH-6b：再接 bundled runner 领取前预检、同 Hall 提问 / 等待 / 唤醒、完整分页上下文重放和幂等保护。
3. TH-7：最后补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。

### 验证与变更

- 验证：完成代码与协议的只读核对；本轮没有功能代码变更，因此未运行测试套件。
- 变更文件：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 待确认：无；产品默认值和失败 / 阻塞原则已由项目管理者确认。

---

## 2026-07-16 TH-5 人工验收反馈与后续澄清 / 终端接入决策

**人工反馈**：项目管理者已通过页面委派任务并成功拿到返回结果，确认 Project Blackboard → bundled runner → 对应 Task Hall → 结果收取的基础链路可用。本轮未继续开发，只沉淀下一阶段需求与当前边界。

### 已确认的澄清流程

- 一项任务始终使用创建时生成的同一个 Task Hall，请求者 A 与执行者 B 的成员关系固定。
- B 在领取前发现信息不足时，应先把问题写入该 Hall，并将任务置为 `queued / clarification_requested`；“停止领取”只表示暂不 claim / 执行，runner 仍继续监听任务和 Hall。
- A 在同一 Hall 回复后，B 应携带原始任务和按时间排序的全部问答重新判断；信息充分则 `accept → claim → execute`，仍不足则继续在同一 Hall 提问。
- 当前服务端已有提问、回复、`clarification_requested`、`accept` 和待澄清禁止 claim 的基础能力，但 bundled runner 仍会直接领取 `assigned` 任务，尚无领取前预检、等待答复和重新唤醒闭环。

### 上下文边界

- Hall 消息会完整持久化，A / B 都有读取权限；Web 和 async client 支持分页读取。
- `talk_get_task` 当前只返回最近 50 条 Hall 消息，正式 runner prompt 目前仅包含任务标题 / 正文，因此“消息已保存”不等于“执行模型已获得完整上下文”。
- TH-6 必须在每次预检和正式执行前分页读取 Hall，并按顺序注入任务原文、B 的问题、A 的回答及后续多轮澄清；还需覆盖重复唤醒幂等与等待期间不 claim。
- 文件消息可保留附件元数据，但附件正文自动下载 / 注入策略仍待后续确定。

### 终端委派方向

- 通过 TALK bridge 启动的 Codex CLI 和 pi 已提供 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result`。
- CLI 已具备直接自然语言委派的底层能力；普通 Codex Desktop 会话尚未自动注册 TALK MCP，需要增加项目上下文、成员身份、API Key 与工具注册的接入包装。
- TH-7 目标链路：终端 A 委派 → B 在 Hall 澄清 → 终端 A 读取并回复 → B 执行 → 结果回同一 Hall → 终端 A 收取。

### 下次恢复顺序

1. 先开发 TH-6 领取前预检、自动澄清和完整 Hall 上下文重放。
2. TH-6 通过自动化与真实模型验收后，再进入 TH-7 Codex Desktop / 通用终端接入包装。

---

## 2026-07-16 TH-5：Project Blackboard、Task Hall Web UI 与真实跨模型链路

**背景**：项目管理者明确表示逐片确认缺少直观价值，希望等“任务创建 → runner 执行 → 结果写入 Task Hall → 人类收取”整个流程可见后再介入。本轮因此把 Web 可视化、bundled runner 活服务链路和真实 Codex / pi CLI 冒烟作为同一个里程碑收口。

### Project Blackboard / Task Hall Web UI

- Web UI 登录后以 Project 为一级工作范围，默认打开项目任务黑板；当前项目按成员保存在本地浏览器。
- 黑板按“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务，并在详情面板保留待确认、待澄清、已接受等精确协作状态。
- 新增页面委派表单，可选择项目 Agent、填写标题与正文；创建后服务端自动生成的 Task Hall 会出现在项目 Hall 列表。
- 任务详情显示请求者、执行者、运行状态、attempt 与租约，并按权限提供进入 Hall、请求澄清、接受、收取结果和取消未领取任务动作。
- Task Hall 继续复用既有消息时间线、回复和文件能力；任务状态每 5 秒刷新，runner 回写后黑板自动进入“结果待收取”。

### runner 输出所有权修复

- 真实 pi 冒烟首次发现：嵌套模型调用 TALK 工具写入 Hall 后，runner 又回写 visible reply，单任务产生 3 条重复结果。
- Codex / pi bridge 现在为队列 worker 解析独立 `task_command`：保留 discussion / tools 权限档，但不暴露 TALK 结果投递工具；交互消息继续使用原命令，不影响终端 Task Hall 工具。
- 新增任务专用 system prompt，明确单轮执行、优先遵循任务正文、避免无必要反问，并由 runner 独占 Hall 结果写入与 complete。
- 真实 pi 复测结果从 3 条收敛为 1 条；Codex 当前任务命令同样只写一条结果。

### 自动化与真实验收

- 新增 `tests/test_task_web_ui.py`，锁定 Project Blackboard / Task Hall 静态结构、项目任务 API 与安全 `textContent` 渲染。
- 新增 `tests/test_task_hall_e2e.py`，在活 FastAPI 服务上贯通 SDK 创建、runner claim / 执行、Hall 结果、complete 和请求者 collect。
- Browser 真实交互贯通登录、空黑板、页面委派、进入 Hall、发送协作消息、runner 结果出现、收取完成与“已结束”分栏；1280px 四列布局修正后无多余横向滚动，控制台 error / warning 为 0。
- 真实 Codex 0.144.4 使用当前无 TALK MCP 的任务命令返回 `Codex Task Hall connected.`，单条 Hall 结果并完成收取。
- 真实 pi 0.80.3 使用当前无 TALK 工具的任务命令完成 claim、单条 Hall 回写与收取；模型会把逐字回复要求改写为简短确认，记录为模型输出质量边界，不视为基础设施链路失败。

### 验证

- Python `py_compile`、`node --check web\app.js`、`node --experimental-strip-types --check bridges\talk_tools_extension.ts` 与 `git diff --check`：通过。
- 定向 Web / runner / client：`Ran 124 tests ... OK`。
- 全量回归：清理真实验收服务后 `Ran 321 tests in 98.917s ... OK`。
- 首次全量运行时一个既有 WebSocket 降级测试在固定 2 秒清理窗口超时；关闭并行真实服务后该用例连续两次单测通过，第二轮全量也通过。

### 下一步

- 当前已达到人工验收门禁：项目管理者可只通过页面完成一次真实委派、观察结果进入对应 Hall 并收取。
- 人工验收通过后关闭 Task Hall 当前里程碑，再决定运行中协作取消、返工 / observer、后台 schedule 或项目级 Members / Activity 的优先级。

---

## 2026-07-16 TH-4：claim lease / attempt 与 runner 过期回收

**背景**：项目管理者接受 TH-3，并明确逐片人工验收缺少直观价值，后续人工介入点应放在完整委派流程里程碑。本轮先提交 TH-3 为 `ff8f8a8`，再补齐同一任务只能由一个有效 runner 持有的可靠性协议。

### 实现

- `AgentTask` 新增 `attempt`、私有 `claim_token`、`lease_expires_at` 与 `heartbeat_at`；旧库通过 `init_db()` 增量迁移并建立租约截止索引。
- claim 改为数据库条件更新，多个实例并发领取只有一个成功；同一实例重复 claim 保持 attempt / token 不变。
- 新增 `POST /api/tasks/{id}/heartbeat` 与 `POST /api/tasks/requeue-expired`。过期 claim 回到 `queued / accepted`，旧实例进入 `error`，下一次领取递增 attempt 并生成新 token。
- complete 原子校验当前 token 和未过期租约；陈旧 token 与重领后缺少 token 的提交均被拒绝。首次 attempt 暂时允许省略 token，兼容尚未升级的第三方 runner。
- async / sync client 新增 heartbeat 与过期回收 helper，并扩展 claim / complete 参数。
- bundled runner 默认使用 120 秒 lease、30 秒心跳；轮询前先回收自己的过期任务。租约丢失时取消本地子进程，不发送 Hall 结果，也不提交陈旧完成状态。
- 运行中取消的错误提示同步调整：lease 基础已经存在，剩余缺口是请求者触发的 runner 协作中断协议。

### 验证

- Python `py_compile` 覆盖模型、迁移、路由、client、runner 与相关测试：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- 定向 tasks / client / CLI bridge / Codex bridge / Task Hall tools：`Ran 141 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 313 tests ... OK`。
- 新测试覆盖真实并发 claim、幂等重试、心跳续租、过期回队、attempt 递增、陈旧完成拒绝、SDK 活服务和 runner 租约丢失取消。
- `git diff --check`：通过；本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- 无 lease 字段的历史 `running` 任务不会被自动回收，避免升级时误终止旧 runner。
- 当前仍只允许取消未领取任务；运行中取消需要协作中断状态与 runner 主动停止协议。
- 下一切片进入 Project Blackboard + Task Hall Web UI，让项目管理者第一次可以从页面直观看到并操作完整任务流程。

---

## 2026-07-15 TH-3：终端 MCP / pi Task Hall 工具闭环

**背景**：TH-2 已完成 async / sync client 与 bundled runner Hall 回传，并提交为 `99e8a28`。本轮按项目管理者确认推进一个终端接入切片，让 Codex 与 pi 的实际操作终端可以发现 Agent、委派任务、处理澄清并收取结果。

### 实现

- 新增 `bridges/talk_task_tools.py`，统一实现 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result` 八个 HTTP-backed Task Hall 工具及 schema / dispatch。
- `bridges/talk_send_mcp.py` 在保留 deferred `talk_send` 的基础上注册全部 Task Hall 工具；`bridges/talk_tools_extension.ts` 为 pi 提供同名工具面。
- Codex discussion profile 与 pi 的 discussion / tools profile 均获得对应工具；bridge 从项目目录 `.talk/project.yaml` 注入默认 `TALK_PROJECT_ID`。
- Agent 发现结合项目 profile、成员与实例状态；等待采用最长 30 秒的有界轮询；Hall 回复可同时推进请求澄清或接受动作。
- 服务端及 async / sync client 新增取消动作。只有原请求者可幂等取消未领取任务；运行中取消返回 `409`，避免在没有 lease / runner 中断协议时伪造停止。
- 新增 MCP 真实工具调用、桥接项目上下文、pi 工具面一致性与活服务完整委派流程测试；现有 task、client 和 bridge 测试同步扩展。

### 验证

- Python `py_compile` 覆盖服务端、两套 client、bridge、Task Hall 工具和相关测试：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `tests.test_talk_task_tools`：`Ran 4 tests ... OK`；`tests.test_talk_client`：`Ran 12 tests ... OK`。
- `tests.test_pi_bridge + tests.test_codex_bridge`：`Ran 29 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 309 tests ... OK`。
- `git diff --check`：通过；本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- `talk_wait_tasks` 当前是客户端有界轮询，不是服务端事件流；Agent 发现结果尚未带项目业务角色。
- 取消当前只覆盖未领取任务；运行中取消、超时回收和重领需要 claim lease / attempt 与 runner 中断协议。
- 按执行 Agent 单切片门禁暂停，等待验收后再进入 claim lease / attempt，不提前开发 Project Blackboard / Task Hall Web UI。

---

## 2026-07-15 TH-2：async / sync client 与 bundled runner Task Hall 接入

**背景**：TH-1 已完成 Task Hall 数据 / API 地基。本轮按项目管理者确认，只推进一个 SDK / runner 切片：让实际终端 client 能使用项目化任务与协作动作，并让 bundled runner 的最终结果落到任务专属 Hall。

### 实现

- `TalkClient` 与 `TalkClientSync.create_task()` 新增可选 `project_id`；`list_tasks()` 新增 `workflow_status` 与 `project_id` 过滤。
- async / sync client 新增 `get_task()`、`request_task_clarification()`、`accept_task()` 与 `collect_task_result()`，覆盖 TH-1 已落地的单任务查询和协作动作 API。
- 通用 `cli_bridge` runner 与 `codex_bridge` 兼容任务处理入口会从 claim 响应读取 `hall_group_id`，将成功或失败的可见结果写入对应 Task Hall，再用消息 id 完成任务。
- 旧任务没有 `hall_group_id` 时继续写入全局时间线，保持服务端与 runner 的兼容路径。
- `tests/test_talk_client.py` 新增 sync 活服务全流程，并扩展 async 流程覆盖项目过滤、澄清、接受、Hall 结果、提交和收取；bridge 测试分别覆盖 Task Hall 回传与旧任务兼容。

### 验证

- `py_compile` 覆盖两套 client、两条 bridge 入口和三份相关测试文件：通过。
- `tests.test_talk_client`：`Ran 12 tests ... OK`。
- `tests.test_cli_bridge`：`Ran 85 tests ... OK`；`tests.test_codex_bridge`：`Ran 19 tests ... OK`。
- `tests.test_tasks + tests.test_pi_bridge`：`Ran 26 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 304 tests ... OK`。
- 本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- 当前 client 已具备项目化创建、查询与协作动作；终端 MCP 仍缺 Agent 发现、委派、等待、纠偏 / 取消和批量结果收集工具。
- observer、返工、lease / attempt、Project Blackboard 与 Task Hall Web UI 仍未进入实现。
- 按执行 Agent 单切片门禁暂停，等待项目管理者或决策 Agent 验收后再进入终端 MCP 切片。

---

## 2026-07-15 TH-1：Task Hall 数据 / API 地基

**背景**：项目管理者确认先实现 Task Hall，并批准首个数据库 / 协议切片采用“复用 Group + 双状态”方案：不新增 thread 表，`AgentTask.status` 继续服务现有 runner，另设协作状态表达澄清、接受、提交和结果收取。

### 决策与实现

- `AgentTask` 新增可选 `project_id`、唯一 `hall_group_id`、`workflow_status` 和 `result_collected_at`；`init_db()` 为旧库补列、建索引，并把旧五态回填为对应协作状态。
- `POST /api/tasks` 原子创建 `groups.type=task` Hall，请求者与执行者固定为不同成员；请求者是 `owner`、执行者是 `member`。schedule 每次物化也建立独立无项目 Hall。
- 保留执行五态 `queued/running/succeeded/failed/canceled`；协作状态新增 `assigned/clarification_requested/accepted/in_progress/submitted/completed/failed/canceled`。
- 新增 `GET /api/tasks/{id}`、`workflow_status/project_id` 列表过滤，以及 `request-clarification`、`accept`、`collect-result` 三类动作；澄清状态阻止 claim，成功 complete 只到 `submitted`，请求者收取后才到 `completed`。
- 关联 Task Hall 不能通过普通 Group API增删成员或独立删除，避免一任务一 Hall 的 1 对 1 结构被拆散。
- 为兼容现有外部客户端，`project_id` 暂时可为空；结果消息接受对应 Hall 或旧全局时间线，但拒绝其它 Hall。bundled runner 改为 Hall 回传留到下一切片。

### 测试与验证

- `tests/test_tasks.py` 从 11 个扩展到 16 个测试，新增项目关联 / 自动建 Hall、完整协作流程、权限、结构保护、schedule Hall 和旧库迁移覆盖。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py server\routes\groups.py tests\test_tasks.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -v`：`Ran 16 tests ... OK`。
- 任务相关七模块最终回归：`Ran 200 tests ... OK`；其余十四模块：`Ran 103 tests ... OK`，最终代码合计 303 项通过。
- 核心实现完成后的单次 unittest discovery 曾 `Ran 303 tests ... OK`。最后一次单进程复跑在活服务测试退出阶段未结束而被工具超时终止，无断言失败；随后以上述 200 + 103 分批复跑覆盖全部模块，不把超时轮次记为通过。
- 纯后端数据库 / API 切片，无前端或 Browser 验证。

### 文档与下一步

- 更新 `docs/spec/MODULE_tasks.md`、`docs/PROJECT_BRIEF.md`、`docs/PROGRESS.md` 和本历史记录，使实现态、兼容边界和后续顺序一致。
- 下一切片扩展 async / sync client 与 bundled runner：支持项目化委派、协作动作和 Task Hall 结果回传；完成后仍按单切片暂停验收。

---

## 2026-07-15 Task Hall 开工前清理

**完成**

- 明确 `agent-docs/BLACKBOARD.md` 为本地协作文件；保留本地文件和 `.gitignore` 规则，从 Git 索引移除，不再作为项目文件维护。
- 将 `docs/PROGRESS.md` 从混合历史记录精简为当前快照，仅保留 Task Hall 目标、待决实现选择、下一切片、验证基线和有效技术债。
- 已完成切片、历史测试和长期方向未删除，仍由本文件及 `docs/spec/PROJECT_INTEGRATION.md` 保存。

**下一步**

- 进入 Task Hall 数据 / API 地基切片；先复核现有任务、Group、消息和成员模型，再确定一任务一 Hall 的最小兼容关联方案。

---

## 2026-07-15 BS-3a：汇总 grounding + bridge 推断 decision（Discussion 分支收尾）

**背景**：BS-3 真机 v2 证明 BS-2b 的通用历史块在技术上已注入，但模型仍可能忽略实际意见、引用旧成见或私信重问；汇总纯 prose 又统一被记为 `answer`，导致 session 虽可能被 closure 收掉，却留下 `end_reason=null`。项目管理者确认先做一个限定范围的 Discussion 收尾切片，再关闭当前分支并转入 Task Hall。

### 决策

- **D-i 采用内联 grounding**：汇总触发时按 `discussion_turns` 为每个 `agent:*` 参与者选择首条 `answer` reply，再按 `message_id` 取回原文。决策人的前置意见与其他 Agent 一样纳入；后续闲聊 / 重复 answer 不进入材料。
- **D-ii 采用 bridge 推断**：仅在 active 多方 brainstorm、human 单独定向当前决策人、文本明确要求汇总、全部 Agent 意见取齐、CLI 成功并返回非空回复时，把回复强制记为 `decision`，再复用 `_resolve_if_decision_maker` 收口。
- **D-iii 保持原协议**：决策人先贡献一条普通 `answer`，最终再单独产出 `decision`。

### 实现

- `bridges/cli_bridge.py`
  - 新增汇总意图 markers 与 `_is_brainstorm_summary_request`，校验 Hall 类型、human 来源、单目标、决策人身份和 active 多方参与关系。
  - 新增 `_brainstorm_summary_grounding`：必须取齐每位 Agent 的首条意见原文，单条最多 4000 字；撤回、正文缺失或成员不全时返回空，不自动收口。
  - 汇总轮使用专用材料块替代通用 BS-2b 历史；其它多方轮次保持原行为。
  - 成功汇总 prose 或错误 mark stance 均归一为 `decision`；CLI 超时 / 失败或无可见回复不触发。
- `tests/test_cli_bridge.py`
  - 覆盖首条意见选择、决策人意见包含、后续噪声剔除、成员未齐拒绝、直接点名守卫，以及完整的 prose → `decision` → `resolved+consensus` 路径。

### 文档

- `docs/spec/MODULE_discussions.md`：补当前 `decision/end_reason` 能力、BS-3a 行为合同和验收点。
- `docs/spec/DELIBERATION.md`：登记 D-i / D-ii / D-iii 决策、严格守卫、BS-3 与 BS-3a 状态。
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`：登记分支收尾、验证和残余人工验收。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge`：`Ran 85 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge`：`Ran 147 tests ... OK`。
- 真实模型最终汇总质量未在本切片重跑：检查时 8000 / 8001 / 8010 均无 server 监听，存在此前留下的 bridge 重连进程；未擅自终止这些进程或把自动化结果写成真机通过。

### 分支交接

- `claude/phase3-collab-and-ui` 在本片提交并推送后关闭开发。
- 已从最终提交 `1da4797` 创建并切换到 `codex/task-hall`，进入 Task Hall 数据 / API 最小闭环；本轮只完成分支接力，不提前开发下一切片。

---

## 2026-07-15 Task Hall 产品方向收敛（文档切片）

**背景**：项目管理者重新确认 TALK 的实际使用方式：用户在 Codex、Claude Code 等真实终端中推进总目标，主 Agent 在过程中按角色把子任务通过 TALK 分给其他模型 Agent；任务完成后，结果必须回到 TALK，来源终端再查询 / 等待并整合。Desktop 与 CLI 不共享同一对话上下文可以接受，TALK 承担跨入口持久化真相源。

### 已确认决策

- 产品级 Hall 分为 **Task Halls** 与 **Discussion Halls**。当前先完成 Task Hall，Discussion Hall 的多角色讨论效果后续继续。
- 一项委派任务自动建立一个独立 Task Hall；执行关系固定为请求者 A ↔ 执行者 B 1 对 1。项目所有者 / 决策 Agent 可观察、介入和验收，但不成为第三个执行参与者。
- 标准流程为：A 指派 → B 可选提问 → B 接受 → 执行 → 提交结果 → A 的终端获取并验收。提交结果与来源终端已收取结果需要可区分。
- 任一接入 TALK MCP / client 的交互终端都获得跨模型“子 Agent 委派”能力，不依赖终端原生 subagent 功能。
- bridge / runner 是独占领取并驱动目标模型执行的基础设施，不是第三类 Agent，也不代表额外订阅；TALK 通过 claim / lease 防止同一任务被多个 runner 重复执行。
- Web UI 按 Project 组织，默认提供 Blackboard 聚合 Task Hall 状态；Task Halls 与 Discussion Halls 分区，点击黑板任务进入对应独立 Hall。

### 文档落盘

- `docs/spec/POSITIONING.md`：更新产品定位、Hall 两类结构、混合终端 / runner 模型和当前优先级。
- `docs/spec/MODULE_tasks.md`：新增 Task Hall 产品合同、标准流程、终端能力、数据关联草案与 Web 信息架构；明确区分现有实现和目标态。
- `docs/spec/PROJECT_INTEGRATION.md`：补充项目级任务关联、终端接入、路线调整和关键决策记录。
- `docs/PROJECT_BRIEF.md`：同步公共上下文、当前前端与目标态差异、模块索引状态。
- `docs/spec/PRODUCT.md`：标记为历史 MVP 基线，避免“多房间不做”继续覆盖当前方向。
- `docs/spec/DELIBERATION.md`：保留已有 Discussion Hall 设计与代码，标记 BS-3 等后续工作在 Task Hall 里程碑后恢复。
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`：登记方向、当前状态、实现待决项与下一步。

### 实现待决项

- Task Hall 最终直接复用 `groups.type=task`，还是新增专用 thread 实体。
- 目标流程如何兼容现有 `queued/running/succeeded/failed/canceled`，是否引入独立 `submitted` / `result_collected` 状态。

这些是首个实现切片需要定稿的技术选择，不改变“一任务一 Hall、1 对 1 执行、项目聚合、结果可收取”的产品合同。

### 验证

- `git diff --check`：通过。
- Markdown 本地链接校验：通过。
- 关键术语一致性检查：通过。
- 纯文档切片，未运行代码测试或 Browser 验证。

### 下一步

- 由决策 Agent / 项目管理者验收本次方向文档。
- 下一开发切片从 Task Hall 数据模型与 API 最小闭环开始；涉及数据库 / 协议，完成后暂停验收。

---

## 2026-07-15 BS-2b：多方场发言可见性（真机 v2 卡第二步的修复，决策 Agent 自行开发）

**背景**：BS-3 真机验收 v2 第一步（各自想法）正常，但第二步"逐一表态"时 agent 反馈"不知道对方发了哪条"——卡住。诊断根因：pi/codex 的 prompt（`build_cli_prompt` 紧凑分支）**只含触发消息 + 角色注入**，无任何 Hall 历史；`discussion_context`（带 turns 的那段）对 pi/codex 是 5.x 时故意砍掉的（防"已经XX啦"元叙述），且它本就不含 turn 的正文内容。→ 表态/汇总这类"对别人发言的反应"结构上拿不到别人说了什么。

### 完成事项（仅 `bridges/cli_bridge.py` + `tests/test_cli_bridge.py`）

- `_shared_discussion_history(client, group_id, discussion, current_message_id, self_id)`：只对 >2 参与者的多方场生效；`client.fetch_history(group_id, since=root-1)` 拉本场从开场起的群发言，拼成"speaker：内容（截 240）"回顾块（剔除当前触发消息/空内容/撤回，最多 24 条），框成"【本场已有发言…请勿逐条复述】"。1:1/free/无场 → 空串；拉历史失败（无方法/404）降级空串不阻断。
- `build_cli_prompt` 加 `shared_history` 参数：pi/codex 紧凑分支在"任务行"后注入该块；通用分支也注入。默认空串 → 非多方场行为不变。
- `handle_incoming_message`：build prompt 前计算 `shared_history`（discussion 已由 BS-2 解析，含 agent 触发与 human 触发两路）。

### 为什么这次注入是安全的（对照 5.x 教训）

5.x 砍 `discussion_context` 是因为那段是**协议字段**（assignee_id/requester_id/remaining_auto_turns…），模型会把它当"任务完成状态"复述。本片注入的是**真实发言内容**（人读 Hall 看到的东西），且明确框为"仅供参考、勿复述"，且**只在多方 brainstorm 场**注入——1:1/free 的既有紧凑 prompt 一字未动。真机行为仍需重测确认（BS-3 v2 重跑）。

### 验证

- **自验（2026-07-15）**：`unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge` → `Ran 143 tests ... OK`（`test_cli_bridge` +3：多方拼块/1:1 空/prompt 注入）。另跑临时脚本验降级与剔除逻辑。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- 重跑 BS-3 真机 v2：第二步表态应能看到彼此想法；继续验到第四步 decision 收口。

---

## 2026-07-15 BS-2：bridge 多方场记账 + 回合预算按 N 放大（决策 Agent 继续自行开发）

**背景**：编排 v1（`spec/DELIBERATION.md §8`）第二片，管理者授权决策 Agent 继续直接开发。BS-1 建好"场"后，本片让 bridge 把真实头脑风暴流量记进这个场，并解除 1:1 回合预算对多方场的误伤。

### 完成事项（仅 `bridges/cli_bridge.py` + `tests/test_cli_bridge.py`）

- `_discussion_auto_turn_budget(discussion)`：多方场（>2 参与者）预算 = agent 数²+1（想法 N + 表态 N×(N-1) + decision 1）；1:1/无场保持常量 3。接入四处：agent 发送者刹车阈值（固定 `DISCUSSION_EXTENSION_CLOSE_TURNS` → `预算+1`，1:1 阈值仍为 4 不变）、deferred talk_send 预算、控制上下文 `remaining_auto_turns`。
- `_active_multiparty_discussion`：只匹配 active 且 >2 参与者的场——human 的普通消息不会被记进 1:1 讨论（既有流程零污染）。
- **human 发送者记账**：human 发起/点名（人驱动编排）时，agent 的可见回复记 turn 到多方场（`infer_reply_stance` → answer）；显式 `mark_stance`/talk_send 的 agree/disagree/decision 走原有路径落**同一场**（`_resolve_discussion_id` 的 participants 匹配可命中），D3-3a decision 收口链路依旧生效。human 发送者不注入 discussion 上下文、不受刹车（prompt 与 1:1 行为零变化）。

### 验证

- **自验（2026-07-15）**：`unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge` → `Ran 140 tests ... OK`（`test_cli_bridge` 78 = 75+3：预算缩放、human 广播回复记账到多方场、agent 消息在多方场 5 实质轮不触发 1:1 阈值收尾）。
- **已知观察点（留 BS-3 真机）**：表态/汇总的 stance 依赖 agent 实际用带 stance 的工具（模板文案已教）；纯口头回复会被记为 `answer`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `agent-docs/BLACKBOARD.md`（执行记录）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- **BS-3 真机验收 v2**：重启 server + 三 bridge，人按四阶段驱动一轮，验 turns 落账 + `resolved+end_reason=consensus`。

---

## 2026-07-14 BS-1：@所有人 × brainstorm 自动建多方 discussion + 模板四阶段（决策 Agent 获授权自行开发）

**背景**：编排 v1（`spec/DELIBERATION.md §8`）第一片。真机验收 v1 证实 @所有人 广播建不出 1:1 discussion、收口无处挂；BS-1 给后续 turns/decision 一个挂载点。**管理者本轮明确授权决策 Agent 直接开发本片**（工单仍走黑板留痕）。

### 完成事项

- `server/routes/messages.py`：
  - `_resolve_recipients` 返回 `(resolved_to, mention_all)`（唯一调用方 `create_message` 同步解包）。
  - 新增 `_maybe_create_brainstorm_discussion`：@所有人 且群 `type=brainstorm` → 消息落库后自动建多方 `DiscussionSession`（`root_message_id`=开场消息、`participant_ids`=全体群成员含发送者、`topic`=去 mention 正文截 80（空则"头脑风暴"）、`requester_id`=发送者、`max_rounds=agent 数+2`）。
  - 幂等守卫：该群已有 `active` 且参与者=全体成员的场次 → 跳过（一群同时一场）。
  - 容错：全程 `try/except`+`logger.warning`，建场失败不影响消息发送。
- `server/hall_types.py`：brainstorm `protocol_guidance` 改为四阶段协议（①需求 ②各自想法含决策人 ③点名表态 agree/disagree(否决附看法) ④决策人 decision 收口；未轮到不抢跑）；facilitator norm=「先贡献，等指示后汇总产出 decision」、contributor norm=「给想法；被点名时明确 agree/disagree」。
- 测试：`tests/test_messages.py` +4（建场字段断言含 max_rounds=4 / 幂等 / free 群不建 / 定向不建）；`tests/test_cli_bridge.py` 2 处文案断言同步。

### 验证

- **自验（2026-07-14）**：`unittest tests.test_messages tests.test_discussions tests.test_hall_types tests.test_cli_bridge` → `Ran 118 tests ... OK`；`tests.test_groups` 16/16。diff 自检（单调用方 / 挂钩位置 / 幂等 / 异常不阻断）。
- 限制：真机上 agent 回复是否落 turns 依赖 BS-2（bridge 侧），本片只建"场"。

### 变更文件

- `server/routes/messages.py` / `server/hall_types.py`
- `tests/test_messages.py` / `tests/test_cli_bridge.py`
- `agent-docs/BLACKBOARD.md`（工单 + 执行回贴）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- BS-2（bridge：广播 turns 落账 + 表态透传 + 多方回合预算）；执行者待管理者定。

---

## 2026-07-14 真机验收 v1（三 agent 头脑风暴）+ 编排 v1 设计定稿

**背景**：D3-1~3c 落地并推 GitHub（`8e1f029`）后，按黑板验收指南真机跑第一轮头脑风暴：「验收测试群」（brainstorm），codex=决策人(facilitator)、pi/pi-kimi=contributor，人（qa）发 `@所有人 …想 3 个点子…codex 最后收敛成结论`。

### 结果与发现

- **通过项**：三个 agent 均直接给出实质想法（消息 2412/2413/2416/2417/2418），氛围贴合头脑风暴——**D2 的 Hall 类型注入真机生效**；@所有人 展开/触发正常。
- **缺口 ①（结构）**：整轮**未创建任何 `discussion_session`**——现有创建路径是 1:1（`_resolve_discussion_id` 依赖 `peer_id`，requester↔assignee），@所有人 的 N 方广播建不出讨论 → turns/decision 收口（D3-3a）无处可挂。
- **缺口 ②（行为）**：无"该你归纳"的信号，codex（决策人）表现同普通贡献者，只报自己的点子、未汇总。
- **环境修复（codex 两层）**：`~/.codex/config.toml` 的 `service_tier="default"` 非法（删除后过配置解析）→ 又暴露老 CLI(v0.130.0-alpha.5) 不支持 `gpt-5.6-sol`（API 400）→ 管理者重装独立新 CLI，`_default_codex_exe()` 改走 PATH（删除写死的旧安装路径）。修复后 codex 正常回复。

### 决策（管理者 2026-07-14 定稿）

头脑风暴编排 v1 = **人驱动 + 四阶段**：① 人发需求（server 自动建多方 discussion）→ ② 每个 agent **含决策人**各给想法(answer) → ③ 人逐一点名，其他角色对每个想法一次表态（agree / disagree+自己的看法）→ ④ 人请决策人汇总(decision) → D3-3a 自动收口。已写入 `spec/DELIBERATION.md §8`；切片 **BS-1(server)/BS-2(bridge)/BS-3(真机 v2)**；D3-3d、timeout/manual、自动编排推迟。

### 变更文件

- `bridges/codex_bridge.py` + `tests/test_codex_bridge.py`（管理者改 codex 路径，随 BS-1 一并收口提交）
- `docs/spec/DELIBERATION.md`（§8 编排 v1）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

---

## 2026-07-14 D3-3c：收口 `end_reason` 归一（deadlock vs consensus）

**背景**：D3-3 第三片。修掉 D3-3b 的临时不精确——决策人收口时按讨论是否经 deadlock 移交，落 `deadlock` 或 `consensus`。`timeout`（轮次阈值语义待定）/ `manual`（缺人类"停"指令机制）本片刻意不做、显式 defer。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py` `_resolve_if_decision_maker`：确认「决策人 + stance=decision」后取讨论 turns（`_list_discussion_turns`，`try/except` 包裹）；若有 `stance="escalate"` 的 turn → `end_reason="deadlock"`，否则 `consensus`；取 turns 失败退化 `consensus`（收口不因此失败）。`stance!=decision` 早返回仍在最前（普通轮次零开销）；加 `isinstance(turn, dict)` 防御。
- `tests/test_cli_bridge.py`：+2（含 escalate turn → deadlock 收口、取 turns 失败 → consensus 退化）；既有 consensus / 非决策人不收口用例保持覆盖。

### 明确未做（defer）

- `timeout` / `manual` 两种 `end_reason` 未接入。
- 未删 / 未改 `escalated` 状态（D3-3d）。未改 server / prompt / 显式动作 / 其它切片。

### 验证

- **决策 Agent 复核（2026-07-14）**：`git diff` 仅 `_resolve_if_decision_maker` 内改动；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 75 tests ... OK`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- **D3-3d（破坏性）**：`escalated` 下线——旧 `escalated`→`resolved+deadlock` 迁移、从 `_DISCUSSION_STATUSES` 移除、bridge 改写不再写 `escalated`。**做前请管理者确认**（唯一有回滚风险的一片）。

---

## 2026-07-14 D3-3b：自动 handoff 目标从"只找 human"扩到"决策人"

**背景**：D3-3 第二片。把系统**自动**发起 handoff 的移交目标从"群里第一个 human"改为"本群决策人"（复用 D3-3a 的 `_find_decision_maker`，decision_tier=decision agent 优先、否则回退 human）。这样 deadlock 能交给 agent 决策人，它随后产出 `decision` → D3-3a 自动收口，闭环。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py`：
  - `_maybe_escalate_disagreement`（连续两轮 disagree 触发）自动目标 `_find_human_reviewer` → `_find_decision_maker`（消息文案/turn/target 一并更新；仍记 `escalate` turn + `status=escalated`）。
  - `_send_human_escalation` 的 fallback（未显式传 `human_id` 时）`_find_human_reviewer` → `_find_decision_maker`；显式传入 `human_id` 行为不变。
- **未动**（复核确认）：显式 `escalate_to_human` / `final_to_human`（agent 主动要人类裁决）保持 human-only；`escalated` 状态、`end_reason`、server、prompt 均未碰。
- `tests/test_cli_bridge.py`：更新 disagree 自动 handoff 用例断言 agent 决策人目标；+2（无决策人回退 human、显式 escalate_to_human 仍 human-only）。

### 已知临时不精确（留 D3-3c）

- deadlock 触发的收口目前仍被 D3-3a 标成 `end_reason=consensus`（D3-3a 对决策人 decision 一律 consensus）。D3-3c 会按触发原因归一（deadlock/timeout/manual）。

### 验证

- **决策 Agent 复核（2026-07-14）**：`git diff bridges/cli_bridge.py` 仅两处自动路径改目标；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 73 tests ... OK`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3c：`end_reason` 归一到 deadlock/timeout/manual 各触发点。

---

## 2026-07-05 D3-3a：决策人 `decision` 收口 → `resolved`+`end_reason=consensus`

**背景**：D3-3（头脑风暴协议编排）拆 4 片，本片 D3-3a 是第一片——新增"决策人产出定论则收口"的路径，不碰现有 escalate/final 流程、不删 `escalated`。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- SDK `update_discussion` 加可选 `end_reason`（`talk_client.py` async + `talk_client_sync.py`）：未传时 body 只含 `status`（向后兼容，服务端 `model_fields_set` 不动 end_reason）。
- `bridges/cli_bridge.py`：
  - 新增 `_find_decision_maker(client, group_id)`：先找 `decision_tier=="decision"` 成员，否则回退第一个 `human:`。
  - `_update_discussion_status` 加 `end_reason` 透传（现有调用零变化）。
  - 新增 `_resolve_if_decision_maker`：`stance!="decision"` 先早返回（普通轮次不查 group，零开销）；决策人发 `decision` → `resolved`+`end_reason=consensus`；**非决策人不收口**。
  - 三落点挂钩：`_record_deferred_demand_turns`（deferred talk_send）、`execute_talk_actions` 的 send_message 分支、`handle_incoming_message` 回复路径。
- `tests/test_cli_bridge.py`：所有 `FakeClient.update_discussion` 加 `end_reason=None` 形参；+4 用例（决策人 send 收口、非决策人不收口、无 decision_tier 时 human 回退不收口、决策人 mark_stance 收口）。

### 验证

- **决策 Agent 独立复跑（2026-07-05）**：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_discussions` → `Ran 80 tests ... OK`（test_cli_bridge 71 + test_discussions 9）；bridge diff 逐条复核，护栏（非决策人不收口 / 现有 escalate/final/escalated 未动）确认。

### 变更文件

- `TALK/client/talk_client.py` / `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3b：handoff 目标从"只找 human"扩到"决策人（decision_tier=decision 优先）"。

---

## 2026-07-04 D3-2：bridge 接 `decision` 立场（plumbing，纯加法）

**背景**：承接 D3-1（`afc1eb7`，server 已认 `decision`）。本片让 bridge 也把 `decision` 当合法、实质、不受轮次刹车的立场正确接住。纯机械改动，不碰编排/prompt/escalated（D3-3）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py`：仅 `ACTION_STANCES` 加 `decision` → 动作解析（`stance not in ACTION_STANCES → None`）不再把 `stance=decision` 抹掉。
- **护栏未破**（复核确认）：`NON_SUBSTANTIVE_STANCES`（仍 `{greeting, closure}`）→ `decision` 被 `_substantive_discussion_turns` 当实质轮次；自动轮次刹车元组（仍 `{greeting, answer, agree, closure}`）→ `decision` 不受 turn limit skip；`infer_*`/prompt/`escalated` 均未动。
- `tests/test_cli_bridge.py`：+2 —— `decision` `TALK_ACTION` 解析后 stance 保留（不被置 None）+ 计入实质轮次；轮次预算耗尽时 `decision` deferred talk_send 不被 skip（对照 `answer` 被 skip）。

### 验证

- **决策 Agent 复核（2026-07-04）**：`git diff bridges/cli_bridge.py` 仅 1 行；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 67 tests ... OK`（原 65 + 2 D3-2）。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3（重头）：结束归一 + 决策人 `decision` 收口 + 轻编排 + prompt 指引 + `escalated`→`resolved+deadlock` 迁移下线。

---

## 2026-07-04 D3-1：审议数据层地基（stance `decision` + `end_reason`，纯加法）

**背景**：进入审议主线 D3（头脑风暴协议）。因改动面大（stance/status 迁移 + 结束归一 + 决策人收口 + 轻编排），拆为 3 片：D3-1 数据层、D3-2 bridge stance、D3-3 结束归一/编排/escalated 下线。本片 D3-1 只做数据层地基，**纯加法、零回归**。执行 Agent 实现，决策 Agent 复核验证后落库。

**现状对齐**：`DELIBERATION §7` 的 stance 迁移点（去 `idea`、`synthesis`→`decision`）是设计期写法、与现状不符——当前 `_DISCUSSION_STANCES` 早已无 `idea`/`synthesis`，故本片对 stance 只新增 `decision`。`escalated` 仍被 bridge 使用，本片不删（迁移/下线留 D3-3）。

### 完成事项

- `server/models.py`：`_DISCUSSION_STANCES` 加 `decision`；新增 `_DISCUSSION_END_REASONS = {consensus, deadlock, timeout, manual}`；`_DISCUSSION_STATUSES` 未动。`DiscussionSession` 加 `end_reason`（可空、索引）；`DiscussionSessionOut`(+`from_orm_session`) 回显；`DiscussionSessionUpdate` 加可选 `end_reason` + 校验（非 None 时须 ∈ 集合，否则 422）。
- `server/db.py`：`init_db()` 为旧 `discussion_sessions` 补 `end_reason` 列 + `ix_discussion_sessions_end_reason` 索引。
- `server/routes/discussions.py`：`update_discussion` 仅当 `end_reason` 在 `body.model_fields_set` 时更新该字段（status-only PATCH 保留原 end_reason）。
- `tests/test_discussions.py`：+5 组（`decision` stance turn、end_reason PATCH round-trip、非法 end_reason 422、status-only 保留、`escalated` 零回归 + 旧 schema 迁移补列）。

### 验证

- **决策 Agent 独立复跑（2026-07-04）**：`.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` → `Ran 74 tests ... OK`（9 discussion + 65 cli_bridge）；diff 逐条吻合工单、纯加法未破 `_DISCUSSION_STATUSES`/`escalated`。

### 变更文件

- `server/models.py` / `server/db.py` / `server/routes/discussions.py`
- `tests/test_discussions.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-2：bridge `ACTION_STANCES` / stance 推断接 `decision`（仍不删 escalated）。

---

## 2026-06-28 真机黑盒验收（A/B/C）+ BUGFIX-1

**背景**：D1/D2/@所有人/人设编辑(a) 落地后，真机黑盒验收前端 3 项已开发功能。由**无项目经验的 agent 当黑盒测试者**（真·黑盒：只按 Web UI 行为测、不看代码），决策 Agent 出验收工单 + 复核。fixture 用 `scripts/seed_acceptance.py` 种入（隔离临时项目根 `.tmp-acceptance`，建 brainstorm 类型 Hall「验收测试群」+ 设 business_role），避免污染仓库已提交的 `.talk/` profile。注入行为（D2/P3-2）本轮主动不验——头脑风暴协议引擎（D3）尚未开发，那部分留待 D3 连同结构化流程一起真机验。

### 验收结果（测试者）

- **A=@所有人**：FAIL —— `@` 下拉不弹、`@所有人` 未高亮。
- **B=禁用/启用开关**：PASS —— 禁用出"已禁用"标记 + 不可加入，启用还原。
- **C=编辑人设**：PASS —— 读已有/从空白新建/持久化/business_role 改 reviewer 均正常；附带发现保存后"编辑人设"按钮卡 disabled。

### 根因定位（决策 Agent 复核代码）

- **A 下拉**：`@所有人` 提交（`6e645bb`）在 `msgInput` 输入处理器写了 `Boolean(activeGroup)`，但该作用域无 `activeGroup`（模块级只有 `activeGroupId`）→ 输入 `@` 即 `ReferenceError`，整段下拉构建抛错，所有 mention 下拉全废。**决策 Agent 当时 diff 复核漏判作用域**——黑盒补上了静态复核盲区。
- **A 高亮**：`buildMentionFragment`+`isAllMentionToken` 静态看正确；疑测试环境（消息绕过正常渲染注入）。
- **C 按钮**：`saveAgentProfileEditor` 成功路径在 `try` 内、清 `agentProfileSaving`（在 `finally`）之前就 `renderGroupMembersPanel()` → 按钮以 saving 态渲染成 disabled 后无人再刷新。

### BUGFIX-1（执行 Agent 修，仅 `web/app.js`）

- Bug 1：输入处理器 mention 块内加 `const activeGroup = getActiveGroup();`。
- Bug 3：保存成功路径在重渲染前调 `setAgentProfileSaving(false)`。
- Bug 2：无代码改动；真机 Chrome 复现确认 `@所有人` 已渲染为 `<span class="mention">` → 原现象=测试环境，非缺陷。

### 验证

- **决策 Agent 复核（2026-06-28）**：`git diff web/app.js` 仅 2 处确定性修复、与根因吻合；`node --check web/app.js` 通过；执行 Agent 用真机系统 Chrome 复验三条（下拉出现所有人+成员、`@pi` 过滤、`@所有人` 高亮、保存后按钮即恢复）。前端运行时 bug 无单测覆盖，以 diff 复核 + 真机为准。
- **结论**：A/B/C 三项前端真机验收闭环。

### 变更文件

- `web/app.js`（BUGFIX-1）
- `scripts/seed_acceptance.py`（fixture 种子，新增·未提交）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 备注（架构对齐 2026-06-28）

管理者确认 TALK 架构理解：TALK 是中转 hub，背后真正干活的是 agent 框架（codex/pi/claude 这类，经 bridge 以 CLI 子进程接入）；codex 与 Claude Code 是同类不同厂的框架，CLI 是接入面。衍生候选「`claude_bridge`」（让 Claude Code/Codex 成为一等公民 worker）记入 PROGRESS Next Plan，暂不排期。

### 下一步

- 进 D3（头脑风暴协议）。

---

## 2026-06-25 人设编辑(a)：网页读写 `.talk/*.md` + business_role

**背景**：承接 D1（`f20811a`）/ D2（`411269f`）/ @所有人（`6e645bb`）。按 `agent-docs/BLACKBOARD.md` 的"人设编辑(a)"工单，让 human 在 Web UI 编辑某 agent 在某项目的人设文件（`<project_root>/.talk/agents/<dir>/{IDENTITY,SOUL,USER}.md`）与其在当前 Hall 的 `business_role`。文件即唯一真相源、**bridge 不变**（仍用 `cli/profiles.py` 读同一批文件）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `cli/profiles.py`（只新增写侧，读侧不动）：`PROFILE_FILES` 映射；`resolve_profile_path`（**双层路径穿越防御**：member 目录必须单段 + `resolve()` 后 `is_relative_to(agents_root)`）；`write_profile_file`（`mkdir parents` + `encoding="utf-8"` 写）。
- `server/models.py`：`AgentProfileOut`（project_id/member_id/identity/soul/user）+ `AgentProfileUpdate`（三字段 Optional，按 `model_fields_set` 选择性写）。
- `server/routes/projects.py`：human-only `GET`/`PUT /api/projects/{project_id}/agents/{member_id:path}/profile`；无 `project_root_path`→400；路径穿越 `ValueError`→400；PUT 仅写 body 出现的字段、写后重读返回。（用 `{member_id:path}` 让含 `/` 的穿越 member_id 进到校验而非 404。）
- `web/index.html` / `web/app.js` / `web/style.css`：Hall 成员行（agent + 可管理 + 群有 `project_id`）显示"编辑人设"；模态编辑 IDENTITY/SOUL/USER + business_role；保存人设走新 `PUT .../profile`，business_role 变化时复用 `PUT /api/groups/{id}/members/{member_id}`（保留原 role/decision_tier）。
- `tests/test_projects.py`：缺文件读取→null、三件套 round-trip（含落盘断言）、局部更新、无 root→400、路径穿越→400（断言外部无文件）、agent 禁止读写→403。

### 验证

- **决策 Agent 独立复跑（2026-06-25）**：`.venv\Scripts\python.exe -m unittest tests.test_projects tests.test_profiles -v` → `Ran 32 tests ... OK`；`node --check web/app.js` 通过；diff 逐条对齐、双层穿越防御复核。
- 前端"编辑人设"弹窗真机点选 + 保存持久化**未起服务真机点选**（待后续攒一次前端真机）。

### 变更文件

- `cli/profiles.py`
- `server/models.py`
- `server/routes/projects.py`
- `web/index.html` / `web/app.js` / `web/style.css`
- `tests/test_projects.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- 审议主线进 D3（头脑风暴协议）；改动面大，按 `spec/DELIBERATION.md §7` 迁移点实施。

---

## 2026-06-24 @所有人：mention 解析"所有人/all" + 前端下拉

**背景**：承接 D1（`f20811a`）/ D2（`411269f`）。按 `agent-docs/BLACKBOARD.md` 的"@所有人"工单，让 Hall 里 `@所有人`/`@all` 把消息 `to_ids` 展开为全体群成员（每个 agent 因此被 mention 触发），是头脑风暴（D3）的前置依赖。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `server/routes/messages.py`：
  - 新增 `_ALL_MENTION_TOKENS = {"所有人", "all"}` + `_is_all_token`（`所有人` 精确、`all` 大小写不敏感）。
  - `_extract_leading_mentions` 改为返回三元组 `(recipients, invalid_mention, mention_all)`；遇 all-token 不按具体成员校验、置 `mention_all`、继续消费。
  - `_resolve_recipients` 加 `sender_id`；`mention_all` 时仅群作用域允许（legacy/全局 → `400 "所有人 mention is only allowed in a group"`），返回 `sorted(全体群成员 - 发送者)`。
  - `create_message` 传 `sender_id=current.id`。
- `web/app.js`：`ALL_MENTION_ID="所有人"` + `isAllMentionToken`；`@` 下拉在群作用域（query 命中）顶部 prepend"所有人（全体成员）"项 → `completeMention("所有人")`；`@所有人`/`@all` 放行为 `.mention` 高亮。
- `tests/test_messages.py`：+4 用例（`@所有人` 展开除发送者、`@ALL` 大小写、混用具体 mention 时全体优先、全局 `@所有人`→400）；既有单 mention/广播/非法 mention 回归由原测试覆盖。

### 验证

- **决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_messages -v` → `Ran 27 tests ... OK`；`node --check web/app.js` 通过；diff 与工单逐条对齐。
- 前端"所有人"下拉点选 + 发出后全体高亮**未起服务真机点选**（待后续攒一次前端真机）。

### 变更文件

- `server/routes/messages.py`
- `web/app.js`
- `tests/test_messages.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3（头脑风暴协议）或 人设编辑(a) 二选一（新会话再定）。

---

## 2026-06-24 D2：bridge 注入 Hall `type` + 角色规范

**背景**：承接 D1（`f20811a`）。按 `agent-docs/BLACKBOARD.md` 的 D2 工单，让 bridge 在每条消息上下文里按本群 Hall `type` 注入流程指引 + 当前 agent 的角色职责（软预设、纯追加，不引入硬状态机）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `TALK/client/talk_client.py`：新增异步 SDK helper `get_hall_types()`（`GET /api/hall-types`）；`talk_client_sync.py` 加同步 parity。
- `bridges/cli_bridge.py`：
  - 模块级缓存 `_HALL_TYPE_TEMPLATES` + `_get_hall_type_templates(client)`（取一次复用；任何异常含 `AttributeError` → 返回 `{}` 不写缓存，绝不抛）。
  - 扩展 `_build_group_member_context`：`free`/缺省 `type` 不注入（保 P3-2 字节不变）；非 `free` 注入 `本群类型：{label}（{type}）。流程指引：…`；`business_role` 与模板 `roles[].role` 大小写不敏感匹配则追加 `你的角色职责：{norm}`；模板不可用 / client 无 `get_hall_types` → 降级为成员清单 + business_role。
- `tests/test_cli_bridge.py`：`setUp/tearDown` reset 缓存防串扰；新增 5 个 D2 用例（review+reviewer、brainstorm+Contributor 大小写、role 不匹配、free 不取模板、模板接口异常降级），P3-2 两个用例零回归。

### 验证

- **决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge -v` → `Ran 65 tests ... OK`；diff 与工单逐条对齐。
- 注入行为（agent 是否实际遵循）属黑盒，待真机攒一次（与 P3-2 同桶）。

### 变更文件

- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- 在 @所有人 / 人设编辑(a) 间二选一，再进 D3/D4。

---

## 2026-06-24 D1：Hall `type` + 模板地基（纯 server）

**背景**：按 `agent-docs/BLACKBOARD.md` 中 Claude（决策 Agent）给执行 Agent 的 D1 工单推进。目标是给 Hall 增加 `type` 维度，并建立服务端内置、数据驱动的 Hall 类型模板注册表，作为后续 D2/D3/D5 的协议地基。本切片严格不改 bridge、不改 discussion stance/状态机、不做前端。

### 完成事项

- 新增 `server/hall_types.py` 作为 Hall 类型模板单一来源：
  - `free`
  - `task`
  - `brainstorm`
  - `review`
  - 每项包含 `label` / `protocol_guidance` / `roles:[{role,norm}]`
  - 暴露 `HALL_TYPES` 与 `DEFAULT_HALL_TYPE`
- `server.models.Group` 增加 `type` 字段，默认 `free` 并建索引。
- `GroupCreate` 支持可选 `type`，创建时默认 `free`，输入会 `.strip().lower()`，非法值返回 `422`。
- `GroupOut` 回显 `type`。
- `server.db.init_db()` 增加旧库迁移：若 `groups.type` 不存在则 `ALTER TABLE` 加 `TEXT NOT NULL DEFAULT 'free'`，并创建 `ix_groups_type`。
- `server.routes.groups` 创建与输出路径均带上 `type`。
- 新增认证只读 API `GET /api/hall-types`，返回 4 类内置模板。
- 增加测试覆盖：
  - 默认创建 Hall 回显 `type="free"`
  - 创建时指定 `"type":"BrainStorm"` 归一为 `brainstorm`
  - 非法 `type` 返回 `422`
  - `GET /api/hall-types` 返回结构与认证要求
  - 旧 schema 迁移后老 Hall 自动获得 `type="free"` 并创建索引

### 验证

- **决策 Agent（Claude）独立复核（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_hall_types tests.test_groups tests.test_member_disable -v` → `Ran 23 tests ... OK`，确认执行 Agent 自测结论；代码与工单逐条对齐。
- `python -m pytest tests/test_groups.py -q`：未运行；全局 Python 无 `pytest`。
- `.venv\Scripts\python.exe -m pytest tests/test_groups.py -q`：未运行；项目 `.venv` 也无 `pytest`。
- `.venv\Scripts\python.exe -m unittest tests.test_groups -v`：16/16 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_hall_types -v`：3/3 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_member_disable -v`：4/4 通过。
- 验证噪声：测试期间 `TimedRotatingFileHandler` 在 Windows 上尝试重命名被占用的 `logs/talk.log`，出现 `PermissionError` 日志噪声；测试退出码仍为 0，本切片未处理该日志轮转问题。

### 变更文件

- `server/hall_types.py`
- `server/models.py`
- `server/db.py`
- `server/routes/groups.py`
- `server/routes/hall_types.py`
- `server/main.py`
- `tests/test_groups.py`
- `tests/test_hall_types.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `agent-docs/BLACKBOARD.md`

### 待确认 / 下一步

- 待决策 Agent/项目管理者确认是否 `git commit`。
- 确认后下一片按设计进入 D2：Hall `type` → bridge prompt 注入；本轮执行 Agent 已按规则暂停。

## 2026-06-20（下午）定位再校准 + 审议方向设计定稿（仅文档，无代码）

与管理者多轮讨论后,把 Phase 3 的剩余方向从"server 端 MEMORY"转向"审议类协议",并沉淀两份 spec:

- **`spec/POSITIONING.md`**:TALK 定位为审议层,**TALK ⊇ CCB**（任务委派 TALK 也能做,CCB 仅作机制借鉴）;4 类使用场景（单次任务协作 / 任务分配 / 头脑风暴 / 评审）+ 升级横切;Hall 类型/RolePack（软预设、数据驱动、可自定义）;通用化（领域无关,非编程项目亦可）+ 受众分层（非技术受众/Web 低门槛接入列为远期）。
- **`spec/DELIBERATION.md`**:信息类型 stance 终集（去 `idea`、`synthesis`→`decision`、`closure` 降级）；**结束归一模型**——单一出口 `handoff` → 决策人（= `decision_tier`/human）,4 种 `end_reason`（consensus/deadlock/timeout/manual）,仅 `deadlock` 有参与者断路器 `escalate`,成功收敛靠决策人 `decision` 收口；Hall 类型；@所有人（展开全体、直接回内容不回执）；人设网页编辑走方案 (a)（改 `.talk/*.md` 文件、bridge 不变）；切片方案 D1–D5。

**关键决策**:① MEMORY 方向关闭（连续性靠项目 `PROGRESS.md` + 身份注入）；② 人设网页编辑 = 方案 (a)；③ 结束机制 = 单一 handoff + 仅 deadlock 有 escalate（"给出错打标不给成功打标"）。
**下一步**:从 D1（Hall `type` + 模板地基,纯 server）开写。

## 2026-06-20 Phase 3 协作层（前两片）+ Web UI #2/#3（全栈）+ 测试数据清理

分支 `claude/phase3-collab-and-ui`（基于已合入 main 的 Phase 1+2，PR #1）。决策 Agent 在管理者授权下自主连续开发。

### Phase 3 协作层
- **P3-1（`533bc5d`）群成员业务角色/决策分级存储**：`GroupMember` 加 `business_role`（自由文本）/ `decision_tier`（`decision`|`execution`）两列；`PUT /api/groups/{id}/members/{member_id}` 接收并全量替换，`GroupOut.members` 返回；`GroupMemberUpdate` 校验 decision_tier 枚举（大小写归一）；`db.py` 幂等列迁移 + 索引。+3 单测。对齐 `PROJECT_INTEGRATION.md` §5.2 groups.yaml 角色模型。
- **P3-2（`51da887`）bridge 注入业务角色**：`bridges/cli_bridge._build_group_member_context` 在群成员清单后追加"你在本群的业务角色：{business_role}。"（取自 P3-1 群成员数据中当前 member 条目）；`decision_tier` 维持由 bridge 启动参数 `--decision-tier` 注入，避免双源冲突。纯追加，无 business_role 时字节不变。+2 单测。**行为黑盒待真机**（pi/codex）。

### Web UI #2 删 Hall（全栈）
- 后端（`53846b8`）：`DELETE /api/groups/{id}`，仅人类；子表先删后删群（group_members / 该群 messages / discussion_sessions / discussion_turns），顺序保证无论 SQLite FK 是否启用都正确（运行时未开 FK）。+3 单测。
- 前端（`5578ac2`）：群成员面板红色"删除此 Hall"按钮（仅人类）→ `window.confirm` 二次确认 → `DELETE` → 本地 `groups` 移除 + 若当前群则 `setActiveGroup(null)`。新增 `.room-danger-btn`。
- 收尾（`a54e4d3`）：移除左侧 Hall 列表从未接线的 `::after content:"删除"` 残留（`padding-right:78px` 致名称换 2 行），`.room-chip` 改 `nowrap`/省略号。
- **管理者真机验收：右侧删除点选通过。**

### Web UI #3 全局禁用 agent（全栈）
- 后端（`4cec246`）：`Member.disabled_at` 软删（保留行 + `messages.from_id` 归属 + 群成员关系，不自动退群）；`get_current_member` 对已禁用成员返回 403；`PATCH /api/members/{id}`（仅人类、仅 agent 目标）切换启用/禁用；`MemberOut` 暴露 `disabled_at`；`db.py` 幂等列迁移 + 索引。+4 单测；鉴权子集 69 测无回归。
- 前端（`dea5ff9`）：右侧列表只列 agent（不展示 human）；每行禁用/启用开关（仅人类）→ `PATCH`；已禁用置灰 + "已禁用"徽标、"加入"禁用。新增 `toggleMemberDisabled` + 样式。
- 收尾（`05db723`）：列表既已 agent-only，移除每行冗余 `agent` 标签 + 过时"点角色筛选"提示，标题改"所有 Agent"，按钮加 `nowrap`（解决名字被挤 / "已在 Hall"换行）。
- **管理者真机验收：功能通过。**（端到端"禁用→403"需重启 server 加载 `PATCH` 端点后验。）

### 测试数据清理（管理者授权）
- API 删 30 个老测试群，仅留 `test-run20`（`group:843d8433bae1`），群 31→1。
- 直接删 DB 清掉 5 个测试成员（agent：ui52226 / testpi / pi@projA:tester；human：tester / ui52226），仅 0 消息者才删以保归属。现存 5 成员 = agent `codex`/`pi`/`pi-kimi` + human `bobo`/`qa`。

### 验证
- 子集全绿：groups 14/14、member_disable 4、cli_bridge 60、鉴权子集（messages/discussions/instances/tasks/files/projects）69；唯一偶发 = `test_websocket` presence 过载时序（隔离 10/10，与改动无关）。
- 前端：JS 语法 / CSS 配平 / ID 一致 / 逻辑复核 + 运行中 server 实测服务新文件。

### 下一步
- P3-3 MEMORY（完整 server 端 COLD/WARM/RESUME，独立子阶段）在本分支做；先出切片拆分方案。

## 2026-06-20 Phase 2 闭环 · 切片 10：CLI `talk sync`（本地 `.talk/agents/` → server 索引）

**背景**：切片 9 把 server 端 `project_agents` 表 + `/agents` + `/sync` 做完，但缺一个本地侧入口把 `.talk/agents/` 的 profile 索引推到 server。本片补上 `talk sync` 子命令，Phase 2 从"server 端完整"收口成"本地 → server 索引"的完整闭环。决策 Agent 在管理者授权自主开发下完成。

### 改动

- `cli/profiles.py`：新增 `member_id_from_dir_name(dir_name)` —— `member_dir_name` 的逆映射（首个 `_` 还原为 `:`，如 `agent_pi-kimi` → `agent:pi-kimi`）；kind 前缀（agent/human）不含 `_`，对磁盘上的单冒号 member_id 无歧义。
- `cli/talk.py`：
  - `scan_agents(root)`：扫描 `.talk/agents/` 各子目录，逆出 member_id，构造相对项目根的正斜杠路径（跨 OS 稳定）；缺失文件→`None`；`MEMORY.md` 映射为 `memory_pointer`；按 member_id 排序，与 server 索引顺序一致。跳过 `agents/README.md` 与点目录。
  - `sync_project(server_url, api_key, project_id, agents, *, http=None)`：`POST /api/projects/{id}/sync`，可注入 http 客户端（同 `register_project`/`create_group`）；非 2xx → `RuntimeError`。
  - `cmd_sync` + `sync` 子命令：`--project`/`--server` 默认取本地 `project.yaml`；`--key` 必填；无 project_id/无 key → 退 1。
- `tests/test_talk_cli.py`：+11 用例（逆映射、scan 排序/缺失文件→None/空目录、sync 真服务端往返、全量替换、报错、cmd 默认 project_id、缺 key、未 init）。

### 验证

- `python -m unittest tests.test_talk_cli tests.test_projects` → 44/44 通过。
- 全套件 `python -m unittest discover -s tests` → **237/237 通过**（较切片 9 的 226 增 11 个新测），无回归。
- 真实 dogfood 数据 `python -c "from cli.talk import scan_agents; ..." .` → 正确逆出 3 个 agent（`agent:codex` / `agent:pi` / `agent:pi-kimi`，含连字符名），路径正确。
- server 往返由 in-process TestClient 覆盖（POST `/sync` → DB → GET `/agents` 一致；含全量替换：删本地一个 profile 再 sync，server 镜像为剩余一个）。未做真实运行 server 的端到端手测（留待人工验收或集成）。

### 待确认 / 下一步

- Phase 2 server 端 + 本地侧入口均已闭环。下一阶段候选：② Phase 3 协作层（业务角色注入 + MEMORY，属新阶段/产品方向，开工前需确认范围）；③ 清两个 discussion 遗留小毛病（管理者已记"以后再修"）；④ Web UI #2 删 Hall / #3 全局禁用 agent（全栈，#3 涉数据模型）。

## 2026-06-16 Phase 2 身份层 · 切片 8c：codex bridge --project 注入 base_instructions

**背景**：管理者确认 8c 后一起测。codex 的系统层 = `-c base_instructions=<json>`（接缝在 8b 已认明）。与 pi 8b 同构实现。

### 改动

- `bridges/codex_bridge.py`：
  - `_build_codex_command(codex_exe, *, profile, system_instructions)`：命令构造参数化，`base_instructions` 可注入；`default_codex_command` 改由它构建（去重）。
  - `resolve_codex_command(args)`：env(`TALK_CODEX_COMMAND`)/自定义 `--codex-command` 覆盖→原样尊重；`--project` + 非空 profile→把 `compose_system_prompt(CODEX_SYSTEM_INSTRUCTIONS, profile)` 注入 `base_instructions`；否则与现状字节一致（严格 opt-in）。
  - `run_bridge` 改用 `resolve_codex_command`（执行档切换 + 注入合一）。
- `tests/test_codex_bridge.py`：+5 用例（无 project 默认 / 工具档 workspace-write / 注入 base_instructions / 空 profile 字节一致 / env 覆盖）。

### 与 pi 8b 的关键差异

codex 命令的 `_codex_config_arg` 本就 `json.dumps(ensure_ascii=False)` + `shlex.quote`，任意 profile 内容（引号/换行）天然 shlex 安全——**无 pi 8b 那个 repr→shlex bug**。

### 验证

- 单测 `test_codex_bridge` 18/18（13 原有 + 5 新；原有 `default_codex_command` 测试在重构后仍绿）。
- 真机黑盒（codex.exe 已装）：`resolve_codex_command` 用 dogfood `agent:codex` profile → shlex 往返通过（argc 20）、codex.exe 路径解析正确、`base_instructions` 含基础提示 + profile（header/SOUL/IDENTITY 标记齐）。
- 全套件 220 个仅 1 个 `test_websocket` presence 时序测试在 **499s 过载**下偶发失败；隔离单跑 19/19 通过，与本改动无关（8c 只动 codex_bridge）。commit 820aee8。

### 待确认 / 下一步

- **人工验收（管理者，pi + codex 一起测）**：起真实 bridge（`python bridges/pi_bridge.py --key <k> --project <根>` / `python bridges/codex_bridge.py --key <k> --project <根>`），在 Group Hall 观察两者身份/风格是否按各自 dogfood profile 收敛。
- 切片 9：server `project_agents` 表 + `GET /api/projects/{id}/agents` + `POST /api/projects/{id}/sync`（profile 路径索引/同步，纯服务端）。

## 2026-06-16 Phase 2 身份层 · 切片 8b：pi bridge --project 注入（B 方案，含黑盒发现的 shlex bug 修复）

**背景**：管理者选定 B 方案（人设作背景进系统层），并告知本机已装 pi/codex（解锁黑盒验证）。本片把 pi 的 `--system-prompt` 接到 `compose_system_prompt`，`--project` 给定时注入 profile。

### 改动

- `bridges/cli_bridge.py`：`build_parser` 加共享 `--project` 参数（缺省 None）。
- `bridges/pi_bridge.py`：
  - `_build_pi_command(system_prompt, *, execution_profile)`：命令构造参数化，系统提示可注入；`DEFAULT_PI_COMMAND`/`TOOLS` 改由它构建。
  - `resolve_pi_command(args)`：用户/env 覆盖命令→原样尊重；`--project` + 非空 profile→注入；否则与现状字节一致（严格 opt-in，零回归）。
  - `run_bridge` 改用 `resolve_pi_command`（执行档切换 + 注入合一）。
- `tests/test_pi_bridge.py`：+4 注入用例 + 工具档测试改用 `resolve_pi_command`。

### 黑盒发现并修复的真 bug（关键）

- 命令里系统提示原用 `{x!r}`（repr）。`parse_command` 用 `shlex.split(posix=True)` 再解析，repr 的 `\'` 转义与 POSIX 单引号语义**不兼容**——真实 profile 含引号/换行时 shlex 报 `No closing quotation`；repr 还把换行传成字面 `\n`。改 `shlex.quote(x)`：正确往返 + 保留真换行。**默认命令也受益**（此前 pi 收到的是字面 `\n`）。

### 验证

- 全套件 **215/215**（干净跑，无并发）；之前并发跑出现的 2 个 timeout 经隔离单跑确认为 websocket/SSE 时序测试的负载偶发，与改动无关。
- 真机黑盒（pi 0.79.3）：① resolve 命令 shlex 往返通过、profile 真注入（header+SOUL+IDENTITY 标记齐、真换行保留）；② 短系统提示 pi **采纳人设**（自称指定名）→ 证明 pi honors 注入；③ DEFAULT 与 INJECTED 行为完全一致 → 零回归。
- 已知：pi 在裁剪 flag（无 tools/extension）的 text 模式下，长系统提示（DEFAULT 与 INJECTED 都如此）会空输出，是 pi CLI 自身怪癖、非本改动引入。完整"pi 不再自称 qa"端到端需用生产 function-calling 命令跑真实 bridge+server 闭环——**留人工验收**。commit 1c17304。

### 待确认 / 下一步

- **人工验收（管理者）**：用 `python bridges/pi_bridge.py --key <k> --project D:\claude-test\TALK`（或目标项目根）起真实 pi bridge，在 Group Hall 里观察身份/风格是否按 dogfood profile 收敛。
- 切片 8c：codex bridge 注入（系统层接缝 = `-c base_instructions=<json>`，已认明）。
- 切片 9：server `project_agents` 表 + `/agents` + `/sync` 子资源。

## 2026-06-15 Phase 2 身份层 · 切片 7：agent profile 加载器（地基）

**背景**：管理者授权进入 Phase 2 身份层并自主开发切片。Phase 2 最敏感的是 bridge prompt 注入（前次三天 debug 战场），故先做零风险的纯函数地基。

- `cli/profiles.py`（新模块，纯文件系统、无重依赖）：`member_dir_name`（从 cli/talk.py 收归此处作唯一权威）、`AgentProfile` dataclass、`load_profile(root, member_id)`（读 IDENTITY/SOUL/USER，缺文件→None，空白→None，`is_empty` 让调用方回退不注入）、`compose_identity_block()`（拼接紧凑块，空 profile→""）。
- `cli/talk.py`：`member_dir_name` 改从 `cli.profiles` import 并再导出（去重，slice 5 测试经再导出仍通过）。
- `tests/test_profiles.py`：7 用例，含对仓库已提交 dogfood `.talk/agents/agent_codex/` 的**真实数据**加载校验。
- 验证：test_profiles 7/7；全套件 **208/208**，无回归。commit ffa80b2。

### 待确认（切片 8 注入策略——需管理者拍板）

bridge 把 profile 注入 prompt 有多种路径、且直接改 agent 现有行为，当前环境无 pi/codex CLI 无法黑盒验证，故暂停等管理者选型。三个候选：
1. **系统层注入**（§5.4 推荐）：把 SOUL 拼进 CLI 命令的 `--system-prompt`，稳态只注一次；但需改各 runtime（pi/codex）命令构造，复杂。
2. **per-call 紧凑注入**：在现有 `你是 {member_id}。{sender} 对你说:{task}` 旁加 SOUL/USER 块；改动小但稳态内容进了 per-call 层，且需防"独立首行触发自我介绍"老坑。
3. **混合**：IDENTITY 维持现状 per-call 紧凑身份锚，只把 SOUL（风格/边界）+ USER（搭档）注入，避免重复自我介绍。
- 共同安全设计：`--project` 缺省时行为与现状**字节一致**（严格 opt-in，零回归）。

## 2026-06-15 Phase 1 收尾 · 切片 5–6：CLI 子命令 + 项目群子资源

**背景**：与管理者确认"先收 Phase 1 尾巴再进 Phase 2"，并约定功能/人工验收推迟到 Phase 2 之后（Phase 1 是管道层，单测兜底；首个可观察行为在 Phase 2 身份注入）。管理者授权连做这两片。`project_agents` 表 / `/api/projects/{id}/agents` / `/sync` 明确并入 Phase 2（消费者是 bridge profile 加载），不在本收尾内。

### 切片 5：`talk add-agent` / `talk create-group` 子命令（commit da0dad7）

- `cli/talk.py`：
  - `member_dir_name()`：member_id→目录名的 `:`→`_` 净化**公共 helper**（Windows 安全；Phase 2 bridge 查 profile 复用同一映射）。
  - `scaffold_agent()`：`.talk/agents/<净化名>/` 生成 IDENTITY/SOUL/USER/MEMORY 占位模板；要求先 `talk init`；FileExistsError 防覆盖 + force。
  - `create_group()`：`POST /api/groups`（http client 可注入）。
  - `load_project` / `load_groups` / `save_groups`：`.talk/` YAML 读写。
  - `cmd_add_agent` / `cmd_create_group`：create-group 默认从本地 `project.yaml` 取 server URL 与 project_id，成功后把群追加进本地 `groups.yaml`。
  - `main()` 捕获 FileNotFoundError → 缺 `.talk/` 给干净 ✗ + exit 1。
- `tests/test_talk_cli.py`：+10 用例。实跑 `add-agent agent:codex` 生成 `agent_codex/` 正确。

### 切片 6：`GET /api/projects/{id}/groups`（commit 99b9076）

- `server/routes/projects.py`：`list_project_groups` 按 project_id 过滤，可见性沿用 `GET /api/groups`（human 全部 / agent 仅已入群），复用 groups 路由 `_group_out`，项目不存在 404；projects.py 单向 import groups.py（无循环）。
- `tests/test_projects.py`：+2 用例（按项目过滤 + 未知项目 404 / agent 可见性）。

### 验证

- 逐片：`test_talk_cli` 18/18；`test_projects`+`test_groups` 18/18。
- 全套件：切片 5 后 **199/199**、切片 6 后 **201/201**，均无回归。

### 待确认 / 下一步

- **Phase 1 全部完成**（接入机制 + 4 CLI 子命令 + dogfood 模板 + 项目群子资源）。
- 分支 `claude/project-integration-phase1` 现含 8 个 commit（切片 1–6 + AGENTS.md 治理 + docs），**未 push**，等管理者确认 push / 开 PR。
- 测试策略：Phase 1 单测兜底，功能/人工验收待 Phase 2 之后合并做一次（首个可观察行为）。
- 下一阶段 **Phase 2 身份层**：bridge 加 `--project` → 读 `.talk/agents/<member_id 净化>/{IDENTITY,SOUL}.md` → 注入 system prompt（落地 `member_dir_name` 映射）；并入 `project_agents` 表 + `/api/projects/{id}/agents` + `/sync`。

## 2026-06-15 Phase 1 基础接入 · 切片 2–4：groups 关联 + talk CLI + TALK dogfood

**背景**：切片 1（projects 表 + API）完成后，项目管理者明确改 `AGENTS.md` 角色定义（决策 Agent 默认只给方案、需明确要求才开发），并授权 Claude 按 1→2→3 顺序自主连续开发 Phase 1 余下三片。本批次三片一气呵成，每片独立验证 + 提交到分支 `claude/project-integration-phase1`。

### 切片 2：`groups.project_id` 字段扩展 + 旧群向后兼容（commit 523fffe）

- `server/models.py`：Group 新增 `project_id`（NULLABLE，FK→projects.project_id，index）；GroupCreate 接受+strip 校验；GroupOut 暴露。
- `server/routes/groups.py`：create_group 设置前校验项目存在（不存在 400）；`_group_out` 输出 project_id。
- `server/db.py`：幂等 `ALTER TABLE groups ADD COLUMN project_id` + `ix_groups_project_id`。
- `tests/test_groups.py`：+3 用例（关联项目 / 无项目向后兼容 / 未知项目 400）。
- **向后兼容**：project_id 默认 NULL，历史群与未接入项目的群行为不变（§10.2）。

### 切片 3：`talk` CLI 脚手架（commit 570c18d）

- `cli/talk.py`：`scaffold_project()`（纯文件系统，生成 `.talk/{project.yaml,AGENTS.md,groups.yaml,agents/README.md,.gitignore}`，FileExistsError 防误覆盖 + force 重写）；`register_project()`（POST /api/projects，**http client 可注入**，便于对进程内 FastAPI TestClient 端到端测试）；`generate_project_id()`；argparse 子命令 `init`；`_force_utf8_streams()` 解决 Windows GBK 控制台打印 ✓/中文路径报错。
- `requirements.txt`：显式新增 `pyyaml>=6,<7`（此前为隐式依赖）。
- `tests/test_talk_cli.py`：8 用例（脚手架/默认群/防覆盖/id 格式/注册成功/注册失败/init --no-register/init 防覆盖）。
- 实跑 `python -m cli.talk init` 生成结构正确，中文 UTF-8 正常。

### 切片 4：TALK 自身 dogfood `.talk/` 目录（commit dec9d25）

- 用切片 3 的 CLI 生成基座（真实 dogfood CLI），再补三个 agent 的身份层四件套 `agents/agent_{codex,pi,pi-kimi}/{IDENTITY,SOUL,USER,MEMORY}.md`（内容取自 §6.3–6.6 示例 + dogfood 实况）。
- `groups.yaml`：`group:talk-dev` 群，按 §5.2 标注业务角色 + 决策分级。
- **关键设计决策（待 ratify）**：`member_id` 含 `:`，Windows 文件系统禁止目录名含 `:`，故 agent 目录按 **`:` → `_`** 净化（`agent:codex` → `agent_codex/`）。已在 `.talk/agents/README.md` 记录；bridge 在 Phase 2 查 profile 时需做同样净化映射。spec 的 `agent:<id>/` 记法在 Windows 下即采用此适配。
- `memory/` 被 `.talk/.gitignore` 忽略（已 `git check-ignore` 验证命中）。

### 验证

- 逐片：`test_groups`+`test_projects` 16/16；`test_talk_cli` 8/8。
- 全套件 `python -m unittest discover -s tests`：切片 2 后 **181/181**，切片 3 后 **189/189**，均无回归。
- dogfood `.talk/` 全部 YAML 可解析、3×4 profile 齐全、角色映射正确。

### 待确认 / 下一步

- 分支 `claude/project-integration-phase1` 含切片 1–4（commit 41ad2dd→dec9d25），**未 push**，等管理者确认 push / 开 PR。
- `AGENTS.md` 角色定义改动是管理者治理改动，**未纳入**任何切片 commit，留工作区待管理者处理。
- Phase 1 已基本成型（接入机制 + CLI + dogfood 模板）。下一阶段 Phase 2 身份层：bridge `--project` 加载 profile + IDENTITY/SOUL 注入 system prompt，届时需落地 member_id→目录的 `:`→`_` 净化映射。
- 仍未做（§7.3 子资源）：`/api/projects/{id}/agents|groups|sync`、`talk add-agent` / `talk create-group` 子命令。

## 2026-06-15 Phase 1 基础接入 · 切片 1：`projects` 表 + 注册/查询 API

**背景**：前端精修支线收尾、5.x 主线关闭后，项目管理者确认回到核心主线。从 `docs/spec/PROJECT_INTEGRATION.md` §12 登记的四阶段路线选定 **Phase 1 基础接入**作为重启起点。本切片落地整条主线的最小地基——server 端 `projects` 表与项目注册/查询 CRUD API（对应 §7.1 表结构、§7.3 API 草案、§3.4 talk init 握手）。

**当前角色**：Claude = 决策 Agent（本轮由项目管理者改 PROGRESS 显式声明）；用量文件 `~/.claude/usage.json` 为空 → 按"无法获取用量"规则，且 Phase 1 涉及数据库改动 → 本轮 1 片即暂停汇总。

### 改动内容

- `server/models.py`：新增 `Project` ORM 表（`project_id` 主键、`display_name`、`description`、`project_root_path`、`maintainer_member_id` FK→members、`created_at`、`last_seen_at`）；新增 `ProjectCreate` / `ProjectUpdate` / `ProjectOut` 三个 Pydantic schema。`ProjectCreate` 校验 project_id 不含空白、display_name 必填；`ProjectUpdate` 用 `model_fields_set` 实现真正的部分更新（PATCH 只动显式传入字段，支持 `talk sync` 只改 path 的场景）。
- `server/routes/projects.py`（新文件）：`POST /api/projects`（注册，project_id 缺省时服务端生成 `prj_<hex12>`，maintainer 缺省取当前成员并校验存在）、`GET /api/projects`（列表）、`GET /api/projects/{id}`（详情）、`PATCH /api/projects/{id}`（部分更新元数据）、`DELETE /api/projects/{id}`（注销，204）。写操作 `_require_human` 限人类成员，读操作任意已鉴权成员可访问。沿用 `get_current_member` / `get_session` 依赖与 groups 路由同构。
- `server/main.py`：import 并 `include_router(projects.router)`（排在 groups 之后）。
- `server/db.py`：`init_db` 增加 `CREATE INDEX IF NOT EXISTS ix_projects_maintainer_member_id`（与既有显式索引管理风格一致；新表的索引本由 `Field(index=True)` + `create_all` 生成，此行用于幂等）。
- `tests/test_projects.py`（新文件）：8 个用例覆盖——人类注册+任意成员可读、服务端生成 id、maintainer 必须存在、重复 id 409、agent 注册/改/删均 403、部分 PATCH 不动未传字段、注销后 GET 404、校验拒绝空 display_name / 含空格 project_id。

### 验证

- `python -m unittest tests.test_projects -v` → 8/8 通过。
- `python -m unittest discover -s tests -q` → **178/178 通过**，无回归（动了 models/db/main 全局 import 文件，全套件复跑确认）。
- 未做：CLI（`talk init`）、`groups.project_id` 字段扩展、`/api/projects/{id}/agents|groups|sync` 子资源、bridge `--project` 加载——均为 Phase 1 后续切片 / Phase 2 内容。

### 待确认 / 下一步

- 下一片候选（Phase 1 续）：① `groups.project_id` NULLABLE 字段扩展 + 旧群向后兼容；② `talk` CLI 脚手架（`talk init` 写 `.talk/` + 调注册 API）；③ TALK 自身 dogfood `.talk/` 目录建立。
- `last_seen_at` 当前等于 `created_at`，bridge 连接时刷新的逻辑留待 bridge `--project` 切片接入。

## 2026-06-11 Web UI 精修支线收尾（浅色工作台多轮微调）

### Current Progress
在 `WEB-WINDOWS-LIGHT-REDESIGN-1` 浅色三栏基础上，按项目管理者多轮反馈完成一整轮视觉/布局精修，前端支线本轮收尾。**纯 `web/` 改动，未动后端 / API / 数据模型。**

- **字体收小并分级**：`--font-control 13→11`、`--font-body 15→13`、`--font-section 16→14`、`--font-title 19→16`；全站字重从 750–850 一档档降为 750 / 600 / 450 / 400 四级，消除"满屏粗体"。
- **比例对齐预览稿、中间消息区约占 2/3**：三栏从 `324 / 1fr / 380` 收窄为 `196px / 1fr / 252px`（1440 宽下中栏约 66%）；顶部查询区由"标题下方堆叠"改为"标题右侧同行"，修掉"搜索"按钮被压成竖排的问题；消息区底部 160px 死留白改为 16/24px，气泡 86% 宽、行高 1.55→1.6。
- **清爽化**：统一三栏底色（`--panel` 提亮）、柔化所有边框线（`--line` 调淡）、右侧卡片去投影变平面、加大模块间留白；顶部输入框改为悬浮大圆角卡片（圆角 18px、最大 860px）。
- **右侧成员栏重排**：成员行从横向挤压（重叠竖排 bug）改为可读布局，名字超长省略号截断；「所有成员」列表撑满到面板底部、内部滚动。
- **成员信息去冗余**：每个成员原本显示「短名 / display_name(含重复 id) / 类型标签」三处，简化为「短名 + 类型标签(agent/human)」；当前 Hall 成员 meta 从「角色 · 在线 · display_name」简化为「角色 · 在线」。
- **去掉角色下拉框**：owner/moderator/member 切换下拉是管理控件、非固定类型，按管理者要求移除（角色仍在 meta 文字可见）；连带删除已无调用者的 `updateGroupMemberRole()` 死函数。
- **group id 移位 + 顶栏精简**：group id 从右侧成员卡副标题移到中间 Hall 标题右侧的代码风格小标签；删右侧「· N 位成员 · 全部」副标题与「✎ 点击名称可重命名」提示；删顶部假窗口控件 `- □ ×`、中间「Hall 协作」、右侧 `human:qa`（DOM 保留但隐藏，避免 app.js 赋值报错）；标题栏高度 `52px→42px`（全站 6 处高度计算同步）。
- 静态资源版本号最终更新为 `20260611-ui-refine`。

### Decisions / Pending
- **成员软删除（决策已定，本轮未实现）**：将来做"agent 管理功能"时，成员删除采用**软删除 = 标记禁用**，保留历史消息归属、UI 隐藏；不做硬删除（避免破坏 `messages.from_id` 等外键引用）。需新增 `members` 禁用字段 + `PATCH/DELETE /api/members/{id}` 后端接口 + 前端入口，属全栈改动。
- 左侧"删除 Hall"入口仍为视觉态，后端 Group 删除 API 与二次确认弹窗待补（沿用上一轮遗留）。

### Verification
- `node --check web/app.js`：通过；CSS 花括号 194/194 平衡；`git diff --check`：通过（仅 LF/CRLF 提示）。
- Browser 实测（精修早期几轮）：以 `human:qa` 登录 `http://127.0.0.1:8000/` 进入 `test-run19 Hall`，用 `preview_inspect` 核验计算样式——三栏 `240/948/252`（中栏 66%）、body 14px/400、标题 17px/750、composer 圆角浮卡、成员行纵向无重叠、`all-members-list` 封顶滚动均符合预期。
- 后续几轮（成员去冗余、去下拉、填满、顶栏精简）以"服务端返回的 app.js/index.html 字节校验 + CSS 花括号 + 项目管理者在自己浏览器确认"验证；预览 MCP 截图工具因 SSE 长连接挂起未用。

### Changed Files
- `web/index.html`、`web/style.css`、`web/app.js`
- `docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

### Next Plan
1. 前端支线已收尾，等项目管理者最终验收。
2. 下一阶段候选：agent 管理功能（含成员软删除）、Hall 删除真实 API + 二次确认、或回到后端主线（`PROJECT_INTEGRATION` 路线）。

## 2026-06-10 Web UI 浅色 Windows 风格重设计落地

### Current Progress
- `WEB-WINDOWS-LIGHT-REDESIGN-1` 已按用户确认的预览稿落地到正式 `web/`。
- 主界面改为浅色 Windows 风格三栏：左侧 Hall 列表，中间消息时间线，右侧当前 Hall 成员 / 所有成员详情。
- 登录页和首次管理员页同步匹配同一套浅色面板、字体层级、控件和按钮样式。
- 左侧 Hall 名称显示成员数 `(x)`，并支持按 Hall 名称、ID、成员 ID、昵称或 kind 做本地过滤。
- 右侧成员区常驻：当前 Hall 成员列表保留角色与在线状态，可移除成员；下方所有成员列表支持加入成员，并可点击 `human / agent` 角色标签多选筛选上方列表。
- Hall 标题可点击并聚焦重命名表单；当前 Hall 消息搜索新增正文命中高亮。
- 静态资源版本号更新为 `20260610-windows-redesign`。

### Verification
- `node --check web\app.js`：通过。
- `git diff --check -- web\index.html web\style.css web\app.js`：通过，仅有 Windows LF/CRLF 提示。
- `/healthz`：本地服务返回 ok。
- Browser 登录页验证：浅色风格正常，无横向溢出，无控制台 error。
- Browser Hall 验证：`human:qa` 进入 `test-run19 Hall` 后，当前成员 3 个、所有成员 10 个、删除按钮圆角、标题可重命名、左侧活动 Hall 显示删除入口，无控制台 error。
- Browser 桌面验证：1600x900 viewport 下三栏为 `324px / 896px / 380px`，`scrollWidth == clientWidth`。

### Changed Files
- `web/index.html`
- `web/style.css`
- `web/app.js`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
- 等项目管理者人工验收新版登录页与 Hall 页面。
- 下一切片建议优先补 Hall 删除真实 API / 二次确认弹窗，再继续做成员详情或未读状态。

---

## 2026-06-07 21:52 (Asia/Shanghai)
### Current Progress
- `WEB-WORKBENCH-REDESIGN-1` 已完成第一版：按 Product Design 方向把 Web UI 从横向工具条聊天页重构为“多 Agent 协作工作台”。
- 主界面改为左侧 `Hall 控制台` + 右侧消息时间线：左侧承载全局 / Group Hall 切换、新建 Group、成员面板和在线成员状态；右侧承载历史搜索、消息流和 composer。
- 保留现有 DOM id 与前端行为契约，不改 API，不引入框架或构建链。
- 视觉系统从单一深蓝收敛为中性暗色工作台，辅以 teal / indigo / amber 状态色，保留 8px 控件圆角与密集操作布局。
- 顺手修正 highlight.js 浏览器脚本路径，避免 `lib/common.min.js` 在浏览器中触发 `require is not defined`。
- 静态资源版本号更新为 `20260607-workbench-redesign`。
### Open Questions / Pending Confirmation
- 本轮是页面结构与视觉基线第一版，尚未新增 discussion session/turn、任务队列或实例状态面板等新功能入口。
- 左侧 Hall 列表在 Group 很多时会独立滚动；后续可继续做分组、未读/关注状态或归档入口。
- 当前 Browser 验证使用本地已有 human API Key 登录，仅做视觉和布局检查；未做完整发消息/建群/成员管理回归。
### Next Plan
1. 请项目管理者人工查看新版 Web UI 的整体方向。
2. 若方向认可，下一切片可继续补“讨论/任务/实例状态”的可视化信息区。
3. 若希望更偏家庭聊天，可回调左侧工作台密度；若希望更偏 Agent Ops，可继续强化状态、轮次和任务面板。
### Verification
- `python` HTML nesting check：通过。
- `git diff --check -- web\index.html web\style.css`：通过，仅有 Windows LF/CRLF 提示。
- Browser 桌面验证：`http://127.0.0.1:8000/` 登录后左侧控制台、右侧时间线、composer 正常渲染，无横向溢出。
- Browser 移动验证：390x844 viewport 下无横向溢出，工作台切为单列，控制台、搜索区、消息区和输入区可见。
- Browser 资源检查：页面已加载 `highlightjs/cdn-release@11.11.1/build/highlight.min.js`，替换旧的 `highlight.js/lib/common.min.js`。
### Changed Files
- `web/index.html`
- `web/style.css`
- `docs/MODULE_webui.md`
## 2026-06-02 22:36 — pi plan-mode 扩展覆盖规避 patch

### 背景
项目管理者给出 Step 2/Step 3 最终 patch：`pi` 默认 function-calling 档需要同时禁用内置工具和自动发现扩展，避免自动发现的 plan-mode 在 `rebindSession` 中重置 active tools 后覆盖显式注册的 `talk_send`。

### Current Progress
- `bridges/pi_bridge.py` 的 `DEFAULT_PI_COMMAND` 追加 `--no-builtin-tools --no-extensions`，保留 `--tools talk_send` 与显式 `--extension <talk_tools_extension.ts>`。
- `DEFAULT_PI_TOOLS_COMMAND` 追加 `--no-extensions`，让施工档工具表面也由 bridge 控制。
- `tests/test_pi_bridge.py` 更新默认命令断言，并新增两条测试覆盖默认档与施工档禁用自动发现扩展。
- `docs/PROGRESS.md` 中该切片的验证项已从“待重跑”更新为本轮实际结果。

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge`：5 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：79 tests 通过。
- `git diff --check -- bridges/pi_bridge.py tests/test_pi_bridge.py`：通过，仅有 Windows LF/CRLF 提示。

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 等项目管理者/决策 Agent 确认后，重启 `agent:pi` / `agent:pi-kimi` 做真实 Group Hall 黑盒复测。
2. 若真实黑盒仍未触发 `talk_send`，继续抓取 pi CLI 输出、extension 注册信息和 bridge env/prompt dump。

## 2026-06-02 21:45 — codex MCP approval / UTF-8 修复

### 背景
项目管理者指出 Codex 走 MCP 独立链路，不能把 pi extension bug 与 Codex MCP 混在一起判断。本轮先独立 probe `codex exec + talk_send MCP`，再按给定 patch 修复默认命令。

### Current Progress
- 独立 probe 确认：Codex `mcp_servers.talk_send` 配置可被 `codex mcp get` 识别，且模型能产生真实 `mcp_tool_call talk_send`。
- 在默认 `codex exec --sandbox read-only` 非交互模式下，MCP 调用会失败为 `user cancelled MCP tool call`，`TALK_DEFERRED_FILE` 不会写入。
- 加 `--dangerously-bypass-approvals-and-sandbox` 后，MCP approval 闸门被绕过；显式注入 `TALK_API_KEY/TALK_GROUP_ID/TALK_DEFERRED_FILE` 后，`talk_send_mcp.py` 成功写 JSONL。
- Windows 下 MCP server 需要显式 UTF-8 环境；否则初始化阶段可能出现 `invalid unicode code point`。
- `bridges/codex_bridge.py` 已在 discussion/tools 两档默认命令中加入 approval bypass flag 和 UTF-8 MCP env。
- `tests/test_codex_bridge.py` 已补独立默认命令断言，覆盖 bypass flag、`PYTHONUTF8/PYTHONIOENCODING`、以及 per-call `TALK_*` 不 hardcode。

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\codex_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge`：13 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：77 tests 通过。
- `codex mcp get talk_send` 复用 `default_codex_command()` 中解析出的 `-c` 参数：退出码 0，输出包含 `command: python`、`args: D:/claude-test/TALK/bridges/talk_send_mcp.py`、`env: PYTHONIOENCODING=*****, PYTHONUTF8=*****`。

### Changed Files
- `bridges/codex_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 重启 Codex bridge，重新黑盒验证 `@agent:codex 通知 agent:pi 项目进度已更新` 是否产生真实消息记录和 discussion turn。
2. pi extension tool 仍需继续排查，或评估 bridge 层兼容解析 `<function_calls>` 文本兜底。

## 2026-06-01 23:24 — pi extension tool probe

### 背景
项目管理者提出高概率假设：`--no-builtin-tools` 可能把 extension tools 一起屏蔽，导致模型 catalog 为空并伪造 `<read>` / `<function>` 文本。本轮执行最小验证切片。

### Current Progress
- `bridges/pi_bridge.py` 默认命令去掉 `--no-builtin-tools`，只保留 `--tools talk_send` 白名单。
- `tests/test_pi_bridge.py` 同步调整默认命令断言。
- 直接 probe 设置 `TALK_DEFERRED_FILE` / `TALK_GROUP_ID` / `TALK_API_KEY` 后运行 pi，要求使用 `talk_send` 向 `agent:pi-kimi` 发送“你好”。
- 对照验证内置 `read` 工具：`pi --print --mode json --tools read` 能产生真实 `toolCall/toolResult` 并读取 `config.toml`。
- 临时 `echo_tool` extension probe：显式 extension 加载不报错，但模型只输出文本形式 `<function_calls><invoke name="echo_tool">...`，没有真实 `toolCall/toolResult`，输出文件为空。
- 坏路径 / 抛错 extension probe：pi 会明确报错，说明不是“extension 加载错误完全静默吞掉”。

### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge`：59 tests 通过。
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py bridges\cli_bridge.py`：通过。
- `talk_send` probe：`TALK_DEFERRED_FILE` 仍为空，未执行。

### Conclusion
- 假设 A（`--no-builtin-tools` 屏蔽 extension tools）未命中。
- 假设 C 可收窄：不是简单“扩展加载静默失败”，因为坏扩展会报错；更像是当前 pi/provider 对显式 extension tool 没进入可执行 function-call 通道。
- 假设 B 或 provider/tool-call 兼容问题仍在：模型能看见/复述 `talk_send` / `echo_tool` 名字，但只以普通文本输出 `<function_calls>`，pi 没有把它当 toolCall 执行。

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 暂停，等待项目管理者确认下一步。
2. 候选方向一：继续排查 pi extension tool catalog / provider tool-call 支持。
3. 候选方向二：在 bridge 层解析 pi 输出里的 `<function_calls>/<invoke name="talk_send">` 作为兼容兜底，但不能把工具使用规则重新塞回 per-call prompt。

## 2026-06-01 23:10 — 5.5 Prompt 三层架构改造

### 背景
项目管理者要求按 `docs/spec/INTERACTION_FRAMEWORK.md` §5 将 bridge prompt 拆成三层：工具自描述层 / 系统层 / 单次调用层，降低 per-call SNR，并让未来新增工具时 bridge prompt 复杂度保持 O(1)。

### Current Progress
- `bridges/cli_bridge.py` 新增 `FUNCTION_CALLING_SYSTEM_PROMPT`，作为 pi/codex 共用系统层 prompt。
- `build_cli_prompt()` 的 pi/codex 分支改为只输出动态信息：`sender 对你说:task`、群成员清单、discussion context。
- `build_cli_task_prompt()` 的 pi/codex 分支同步瘦身，不再注入身份、任务 id、项目根目录等系统层/元信息。
- `bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT` 改为引用公共系统层 prompt。
- `bridges/codex_bridge.py` 通过 `-c base_instructions=...` 注入系统层 prompt；修复 `mcp_servers.talk_send.args` 的 TOML quoting；默认命令改用 `_default_codex_exe()` 探测到的本地 Codex CLI，并加 `--ignore-rules` 避免聊天 bridge 读取项目规则。
- `bridges/talk_tools_extension.ts` 和 `bridges/talk_send_mcp.py` 强化 `talk_send` 工具自描述，把“何时联系、转告、询问、通知或打招呼给另一成员”放在工具层。
- 测试新增/调整：最小 per-call prompt、工具增长 O(1)、系统层 prompt 进入 pi/codex 默认命令、codex config quoting。

### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：74 tests 通过。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py bridges\codex_bridge.py bridges\talk_send_mcp.py`：通过。
- `git diff --check`：通过，仅有 Windows LF/CRLF 提示。
- `codex.exe --version`：本地 OpenAI Codex bin 可运行，版本 `codex-cli 0.130.0-alpha.5`；PATH 上 WindowsApps `codex.exe` 在当前 shell 报 Access is denied，因此默认命令改用本地路径探测。
- Codex 最小执行：修复后不再出现 `mcp_servers.talk_send.args expected a sequence`，说明 MCP config quoting 已正确。
- `usage-gate guard --provider codex --json`：`decision=continue`，session 46%，weekly 22%。

### Blackbox Result
- 已启动 TALK Server 与 `agent:pi` / `agent:pi-kimi` / `agent:codex` bridge，并在 `group:test-run15` 发送三条 UTF-8 正常指令：
  - `@agent:pi 去跟agent:pi-kimi打个招呼`
  - `@agent:codex 通知 agent:pi 项目进度已更新`
  - `@agent:pi 问 agent:pi-kimi 它现在忙不忙`
- 未通过验收：未产生 `agent:pi -> agent:pi-kimi` 或 `agent:codex -> agent:pi` 的实际消息记录；`discussion_sessions / discussion_turns` 无对应 demand/reply turn。
- `logs/pi_prompt_dump.log` 证实 per-call prompt 已降为 `sender + task + 群成员清单`，不含系统层字样。
- 直接 pi 工具探针中，pi 仍输出伪 `<read>` 文本，没有执行 `talk_send` extension；残余风险集中在 pi runtime extension tool catalog / tool execution 链路。

### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `bridges/codex_bridge.py`
- `bridges/talk_tools_extension.ts`
- `bridges/talk_send_mcp.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 暂停功能扩展，先排查 pi extension 工具调用链。
2. 确认 `--extension` 注册的 `talk_send` 是否实际进入 pi tool catalog，以及 `--tools talk_send` 是否需要命名空间或不同运行模式。
3. 工具链修复后重跑 `group:test-run15` 三条黑盒验收。

## 2026-06-01 16:35 — 5.5 方案 D：discussion_turns 显式交互账本

### 背景
项目管理者指出上一轮“打招呼关键词兜底”违背原架构方向：应让模型自主判断自然语言需求，bridge 只机械执行 function-calling 协议。进一步评估方案 A/B/C 后，确认采用方案 D：`reply_to` 只保留 UI/引用语义，需求/回复/轮次由 `discussion_sessions + discussion_turns` 显式账本记录。

### Current Progress
- 修订 `docs/spec/INTERACTION_FRAMEWORK.md`：保留四分类模型和 function-calling 方向，明确 `reply_to` 不再承担“需求/回复/轮次”的协议状态。
- 给 `discussion_turns` 增加 `turn_kind`：`demand | reply`；历史迁移默认 `reply`。
- API / SDK 已支持 `append_discussion_turn(..., turn_kind=...)`，输出也包含 `turn_kind`。
- bridge 已改为读取 active session 中最大 `demand.round_index`：小于 2 才创建 `TALK_DEFERRED_FILE`，达到 2 后禁止继续 `talk_send`。
- deferred `talk_send` 成功后追加 `turn_kind=demand`；visible reply 成功后追加 `turn_kind=reply`。
- 删除上一轮临时的“明确打招呼/问好关键词兜底”代码和测试。
- 保留 `talk_send` 消息继承当前消息 `reply_to` 的行为，但只作为 UI 引用和定位辅助，不再用于轮次判定。

### Changed Files
- `docs/spec/INTERACTION_FRAMEWORK.md`
- `docs/spec/MODULE_discussions.md`
- `docs/PROJECT_BRIEF.md`
- `server/models.py`
- `server/db.py`
- `server/routes/discussions.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `tests/test_talk_client.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py server\models.py server\db.py`：通过
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions`：61 tests 通过
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_talk_client`：16 tests 通过
- `git diff --check`：通过，仅有 Windows LF/CRLF 提示

### Next
- 重启服务和 bridge 后，在 `group:96b88a2357a7` 黑盒复测 `@agent:pi 去跟agent:pi-kimi打个招呼`。
- 重点验收：第 1 轮 `demand round_index=1`、任一 agent 可产生一次第 2 轮 `demand round_index=2`、之后不再暴露 `TALK_DEFERRED_FILE`。
- 若模型仍不调用 `talk_send`，继续排查 pi CLI / extension / tool-calling 链路，而不是恢复关键词兜底。

---

## 2026-06-01 14:40 — 5.5 打招呼场景 bridge 兜底修复

### 背景
项目管理者重启服务并在 `group:96b88a2357a7` 连续测试 `@agent:pi 去跟agent:pi-kimi打个招呼`，结果 pi 只向 human 回复“好的，我去...”，没有实际调用 `talk_send`，因此也没有产生 `agent:pi -> agent:pi-kimi` 消息，方案 C 的 `reply_to` 链深度刹车未被验证到。

### Current Progress
- 确认当前问题不是成员缺失：群内有 `human:qa`、`agent:pi`、`agent:pi-kimi`。
- 确认失败形态：`talk_send` / `TALK_ACTION` 均未触发，deferred 文件为空，数据库只新增 pi 给 human 的确认回复。
- 在 `bridges/cli_bridge.py` 增加窄范围兜底：human 明确要求“去跟 agent:X 打招呼/问好”，且模型给出承诺式回复但未触发发送动作时，由 bridge 生成 `send_message` 动作。
- 兜底消息仍走既有 `execute_talk_actions`，因此会复用群成员校验、`reply_to` 继承、discussion turn 记录等路径。

### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Verification
- `python -m py_compile bridges/cli_bridge.py bridges/pi_bridge.py`：通过
- `python -m unittest tests.test_cli_bridge.CliBridgeTests.test_human_greeting_request_falls_back_when_pi_skips_tool_call tests.test_cli_bridge.CliBridgeTests.test_greeting_send_message_action_records_non_substantive_turn tests.test_cli_bridge.CliBridgeTests.test_handle_incoming_message_executes_send_message_action`：通过
- `python -m unittest tests.test_cli_bridge tests.test_pi_bridge`：53 tests 通过
- 未做真实黑盒复测：需要项目管理者重启 bridge 后再发测试消息

### Next
- 重启 `agent:pi` / `agent:pi-kimi` 后复测打招呼场景。
- 若打招呼通过，再确认是否需要为“转告/询问”设计独立兜底策略。

---

## 2026-06-01 — 5.5 回复质量优化 + preview 方案回退 + 交互框架文档

### 背景
方案 C 落地后黑盒测试发现 3 处回复质量残留（汇报体、原文引用、extension 暴露机制），实施了 4 项修复。preview 方案因人类消息也以 @ 开头被否决回退。整理了完整的交互框架文档。

### Current Progress
- **去汇报体**：agent 调 talk_send 时 suppress visible reply（JSONL 文件非空判断，兼容旧协议测试）
- **prompt 微调**：不要引用发送的原文
- **extension 中性化**：TALK_DEFERRED_FILE 未设时返回 "已处理。" 而非暴露机制文本
- **preview 方案回退**：`reply_to.preview` 无法区分 human @mention 和 talk_send @mention，回退到 `reply_to.from_id`
- **交互框架文档**：新建 `docs/spec/INTERACTION_FRAMEWORK.md`，系统阐述消息四分类模型、轮次约束、三层防线架构、协议演进历史

### Changed Files
- `bridges/cli_bridge.py`
- `bridges/talk_tools_extension.ts`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/spec/INTERACTION_FRAMEWORK.md`（新建）

### Verification
- `py_compile` 通过
- 52 tests 全过

### Next
- 确定 pi 侧第 2 轮方案（discussion turn 追踪 / 查父消息 / 保持现状）
- 继续黑盒测试

---

## 2026-05-31 — docs 目录整理：spec / guides 分层

### 背景
项目管理者确认 `docs/` 当前平铺文档过多，希望先整理为少量高频目录；同时确认暂不创建“产品迭代”和“技术验证”空目录，等有真实内容再补。

### Current Progress
- 保留根目录锚点文档：`docs/PROJECT_BRIEF.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 新增 `docs/spec/`，并移入 `PRODUCT.md`、`SDK.md`、`LOCAL_LAB_DESIGN.md`、全部 `MODULE_*.md`。
- 新增 `docs/guides/`，并移入 `QUICKSTART.md`、`QUICKSTART_USER.md`、`QUICKSTART_AGENT.md`、`DEPLOY.md`。
- 暂未创建 `iterations/`、`validation/`、`milestones/` 空目录。
- 已更新 `PROJECT_BRIEF` 目录树和模块索引，修正 README、AGENTS、CLAUDE、进度历史和文档内相对链接。

### Changed Files
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/spec/*`
- `docs/guides/*`

### Verification
- `rg` 旧路径模式搜索：未发现计划关注的旧路径模式残留。
- Markdown 本地链接校验：通过。
- `git diff --check`：通过；仅有既有 Windows 换行提示。
- 未运行后端测试：本切片仅移动和修正文档。

### Next
- 继续原 5.5 P0 后续：重启 pi bridge + pi-kimi bridge 后跑黑盒测试。
- 后续出现真实迭代计划、技术验证报告或里程碑验收材料时，再分别创建对应目录。

---

## 2026-05-31 — 5.5 Step 2+ P0 热修复：身份幻觉 + 消息风暴 + stance 参数

### 背景
Step 2 agent_end 钩子落地后，项目管理者在 group:83aae24462b7 跑黑盒测试（10:19），发送 `@agent:pi 你去和 agent:pi-kimi 打个招呼`。结果 42 条消息，pi ↔ pi-kimi 陷入无限循环对话，暴露三个致命问题：
1. **消息风暴**：双方互相调用 talk_send，无刹车机制
2. **身份幻觉**：pi 自称 "agent:codex"
3. **重复发起**：pi-kimi 把连续对话的后续消息当成全新打招呼请求

### Current Progress
- **`talk_send` 加 `stance` 参数**：支持 question / greeting / answer / agree / disagree / closure，JSONL 记录带 stance
- **Bridge 层 turn limit 刹车**：`_read_and_execute_deferred_actions` 新增 `current_turn_count` / `max_auto_turns` 参数，greeting/answer/agree/closure 类型在 turn ≥ 3 时自动丢弃
- **Prompt 注入 `member_id`**：pi prompt 新增 `"你是 agent:pi。"` 前缀，防止身份幻觉
- **Prompt agent-to-agent 约束**：新增 "如果只是其他 agent 在寒暄/闲聊/确认，直接简短回复即可，不要再调用 talk_send"
- **Discussion 上下文对齐**：`_discussion_context_text` 增加 talk_send 说明
- **Extension promptGuidelines 更新**：告知模型区分 human 指令 vs agent 寒暄，强调 stance 必填

### Changed Files
- `bridges/talk_tools_extension.ts`
- `bridges/cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

### Verification
- `py_compile` 全部通过
- 52 tests 全部通过（49 cli + 3 pi）
- turn limit 刹车单元测试通过（turn=0 全执行，turn=3 greeting 跳过 question 照发）
- 未经真实 pi 端到端验证（需重启 bridge 后跑黑盒测试）

### Next
- 重启 pi/pi-kimi bridge 后跑黑盒测试验证三个 P0 问题
- 如仍有消息风暴，考虑 bridge 层更激进刹车

---

## 2026-05-31 — 5.5 Step 2：agent_end 钩子

### Current Progress
- **talk_send 改为延迟执行**：extension 不再直接 HTTP POST，改为写入 JSONL 临时文件；bridge 在 visible reply 发送后才读取执行
- **修复 step 1 遗留 bug**：`talk_tools_extension.ts` 中 `sendToTalk` 重复调用（两次同语句）
- **时序修复**：visible reply → deferred talk_send → cleanup，确保 sender 先看到回复再触发跨 agent 消息
- **回退兼容**：`TALK_DEFERRED_FILE` env 不存在时扩展仍走直接 HTTP POST 模式
- **新函数**：`_read_and_execute_deferred_actions(filepath, client, group_id)` — 读 JSONL、逐条用 TALK SDK 发送
- **临时文件生命周期**：bridge spawn pi 前 `mkstemp` 创建，`finally` 清理（`os.unlink` + `os.environ.pop`）
- **向后兼容**：TALK_ACTION 文本协议解析代码全部保留，不做删除

### Changed Files
- `bridges/talk_tools_extension.ts`
- `bridges/cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

### Verification
- `py_compile` 全部通过
- 52 tests 全部通过（49 cli + 3 pi）
- 未经真实 pi 端到端验证（需重启 bridge 后跑黑盒测试）

### Next
- 5.5 step 3：扩展工具集（`talk_reply` / `talk_list_agents` / `talk_escalate` / `talk_mark_stance`），支持 `stance` 参数
- 黑盒验证 step 2 deferred 时序

---

## 2026-05-30 — 5.5 Step 1：function-calling 最小可验证版本

### Current Progress
- **pi bridge 切换到 function-calling 模式**，注册 `talk_send` 工具（通过 `talk_tools_extension.ts` pi 扩展）
- **双向通信验证通过**：pi（kimi-k2.6）→ pi-kimi（kimi-k2.6），消息均正确入群时间线（`group_id` 正确注入）
- **架构共识落地**：元数据（group_id / decision_tier / member_id）走环境变量，不放 prompt；用户消息放最前面；不声明 agent 身份避免与 pi 内核冲突
- **prompt 极简化**：从最初 ~800 字降到 ~130 字，system prompt 仅 8 字
- **prompt 迭代路径**：R1 方括号格式被 LLM 当元数据跳过 → R2 自然语言但上下文太长淹没指令 → R3 去掉身份声明 + 括号备注，模型不再内部冲突
- **工具集污染修复**：确认所有内置工具会让模型切到代码助手模式，必须 `--no-builtin-tools --tools talk_send`
- **反幻觉黑名单"粉象效应"修复**：正常路径不列禁止名单；fallback（清单不可用）保留
- **多 bridge 环境变量 key 冲突修复**：`if not in os.environ` → 无条件覆盖
- **DeepSeek 模型确认不适合 function-calling**：pi 切 kimi-k2.6 后解决
- **时序问题**：`talk_send` 在 visible reply 之前（`--print` 限制），留给 step 2 `agent_end` 钩子

### Changed Files
- `bridges/talk_tools_extension.ts`（新建）
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `deploy/bridges.example.json`（新建）

### Verification
- `py_compile` 全部通过
- 72 tests 全部通过（cli/codex/pi/discussions/talk_client）
- 群内测试：pi ↔ pi-kimi 10 条消息全部正确入群时间线

### Next
- 5.5 step 2：`agent_end` 钩子解决时序问题
- 5.5 step 3-4：迁移所有 bridge，删除 TALK_ACTION 文本协议

## 2026-05-30 第五轮 (Asia/Shanghai) — 诊断 + 方向调整：协议机制层重构立项
### 背景
- 第四轮"信使场景"上线后跑黑盒测试，pi 仍然不发 TALK_ACTION，新冒出"系统 prompt 整段泄漏给用户"（场景 5 #460 "决策分级是：高自主权"、"本群成员清单（member_id）：[人类: 小白] [agent: pi]" —— 这些字串我代码里根本没写过）和"完全偏题回复"（场景 9 #470 触发"分组讨论已经开始"会议主持模板）等新症状
- 项目管理者判断"模型不应该会忽视指令"，要求复查代码并做诊断

### 诊断过程
1. **代码复查**找到 2 个原则性问题 + 4 个设计问题：
   - 原则性：`_build_group_member_context()` 静默失败（group_id 为空或 get_group 报错都返回 "")
   - 原则性：`build_cli_prompt` pi 分支降级时无告警（清单为空时 [系统] 块只剩身份+决策分级）
   - 设计：系统 prompt 太"对话式"，pi 把它当对话内容来 paraphrase
   - 设计：缺 few-shot 示例
   - 设计："系统 块"引用与 `[系统]` 实际不一致
   - 设计：系统 prompt 是一坨无结构长字符串
2. **加 prompt dump 诊断**（`bridges/cli_bridge.py` 新增 `_dump_prompt()` / `_dump_diagnostic()`，环境变量 `TALK_DUMP_PROMPT=1` 启用）
3. **项目管理者手动重启 pi bridge + 跑场景 1/5/2，dump 写入 `logs/pi_prompt_dump.log`**
4. **dump 结论非常清晰**：
   - `group_id` 正常（`group:139f88c27756`）
   - `group_member_ctx` 非空（107 chars）
   - 群成员清单完整含 `agent:codex / agent:pi / human:qa`
   - 决策分级文案与代码一致（`执行 Agent — 每次只处理一个已确认请求...`）
   - **prompt 注入完全正确，但 pi 仍然乱回**
5. **项目管理者提供 `disler/pi-vs-claude-code` 项目对比报告**（桌面 `pi-vs-claude-code-vs-TALK-评估报告.md`），第 3.3 节直指根因：TALK 的"自由文本嵌结构化协议标签"（`TALK_ACTION send_message to=agent:codex stance=question body=...`）架构本身让 LLM 不可能可靠输出 —— 任何模型在"对人说自然语言"+"对 bridge 说协议指令"双信道下都会失败
6. **`bridges/pi_bridge.py:22-23` 自证**：pi CLI 当前以 `--no-tools` 启动，明确禁用了原生 function-calling 能力。我们自己关掉了更可靠的路径

### Current Progress
- **5.3 状态：接受当前实现作为过渡版本**。dump 证明 5.1-5.3 已落地的设计（调度顺序、去硬编码、群成员清单注入、决策分级注入、自我介绍模板）全部正确，pi 是收到这些事实的，剩余"pi 不输出 TALK_ACTION"问题是协议机制层的，不是 prompt 文案层
- **`bridges/cli_bridge.py` 加入 prompt dump 工具**（73 行）：`_dump_prompt()` 完整记录 spawn LLM CLI 前的 prompt + 上下文元数据；`_dump_diagnostic()` 记录注入失败时的诊断信息；`_build_group_member_context()` 失败路径加诊断 log。全部通过 `TALK_DUMP_PROMPT=1` 环境变量 gated，默认关闭、零运行时影响；将来排查 prompt 问题随时可用
- **`docs/spec/LOCAL_LAB_DESIGN.md` 新增 "2026-05-30 Agent 通信协议方向调整：从文本协议标签转向 function-calling" 章节**，包含触发证据、根因分析、新方向工具集设计（`talk_send` / `talk_reply` / `talk_list_agents` / `talk_escalate` / `talk_mark_stance`）、与现有 5.1-5.3 工作的关系、5.5 落地阶段规划

### Next Plan
- **5.4 优先**：`groups.metadata` JSON 字段落地（与协议机制正交）
- **5.5 立项**：agent 通信协议改造 function-calling，4 阶段落地（详见 `docs/spec/LOCAL_LAB_DESIGN.md` 新章节）
- 5.4 落地后 5.3 的 `metadata.roles` 反查线路自动激活，无需返工
- 5.5 落地后预计可删 `cli_bridge.py` 中 800+ 行文本协议解析/清理/推断/兼容代码

### Verification
- 改动只涉及 `bridges/cli_bridge.py` 增加诊断函数 + 文档更新，不动其它代码
- `py_compile bridges/cli_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` 全过（dump 代码默认关闭，不影响测试）
- 实证：prompt dump 文件 `D:\claude-test\TALK\logs\pi_prompt_dump.log` 3 条 dump 验证注入正确

### Changed Files
- `bridges/cli_bridge.py`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-30 第四轮 (Asia/Shanghai) — 5.3 回炉热修第二弹
### 背景
- 第三轮（同日早些时候）把"回复克制"重写为 A/B/C 三类区分以解决"pi 不执行 TALK_ACTION"问题。但黑盒复测后发现两个新问题：
  - **#431 铁证**：pi 把 `"A 类。"` 直接当话术输出（"A 类。你好，我是 Talk Group Hall 里的 pi..."），显式标签污染回复
  - **关键词匹配脆弱**：B 类触发词清单 `"请和、让、去问、去找、联系、通知"` 不全，用户消息"你**去和** codex 打个招呼"里的"去和"不在清单里，pi 按字面匹配失败 → 默认走 A 类 → 不执行 TALK_ACTION
- 测试结果分布：场景 1/2/3/9 FAIL，4/5/6/7 PASS，8 MILD。"无敷衍机械文案 / 无 bobo 幻觉 / 无越界扩展 / 无 codex 模板"四类已修问题没有回归。
- 项目管理者点出根因方向："关键词匹配很难穷尽，应该用场景类型描述"。

### Current Progress
- **`bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`**：把"回复克制"段彻底重写：
  - 放弃 A/B/C 字母标签 + 关键词清单
  - 改用 **场景类型描述**：【信使场景】/【自身询问场景】/【agent 互回场景】
  - **信使场景的判定核心是"意图焦点"语义判断**：让 pi 自己问"用户期望谁回答这个问题、谁去做这件事？"，答案是另一个成员就是信使场景
  - **"拿不准时优先按信使处理"** 兜底——错执行比不执行容易补救
  - **自身询问场景兜底**：被问"介绍下你自己"必须说出 member_id + 本群是否有角色（直接修场景 9）
  - **显式禁止输出场景标签**：封掉"A 类。"那种泄漏
- **`tests/test_pi_bridge.py`**：测试断言换成新关键词（信使场景 / 意图焦点 / 拿不准时优先按信使处理 / member_id / 本群没有给我分配特定业务角色）；`assertNotIn "A 类——"` / `"B 类——"` / `"C 类——"` 防字母标签回归

### Open Questions / Pending Confirmation
- 待项目管理者**只重启 pi bridge** + **新建测试群**（不复用 `group:2b3c9432ac73`）后复跑 `test_after_5.3.md`
- 重点验证：场景 1/2/3 pi 是否真的发 TALK_ACTION 联系 codex；场景 9 是否说出 member_id + 承认无角色；pi 回复不含场景标签
- 已 PASS 的场景 4/5/6/7 不应回归
- **遗留**：场景 8 codex 对 SQL 评审 FAIL（codex 走 cli_bridge.py 非 pi 分支，那里克制只有英文 `RESPONSE_STYLE_INSTRUCTIONS`），不在 5.3 范围内；待 5.4 后单独处理

### Verification
- `py_compile bridges/pi_bridge.py tests/test_pi_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` 首次跑遇到 1 个 timing flaky（与本轮改动无关），立即重跑 24 tests 全过
- 本轮总计 72 tests 全过

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 第三轮 (Asia/Shanghai) — 5.3 回炉热修
### 背景
- 第二轮回炉完成后开始重测 `test_after_5.3.md`，刚跑场景 2 就发现 pi 收到 `@agent:pi 请和 codex 互相确认在线状态` 只对 human 回了 `嘿，我是 pi！👋 有什么可以帮你的吗？`，未用 TALK_ACTION 联系 codex，120s 静默。场景 1 同样：pi 收到"你去和 codex 打个招呼"也未联系 codex。
- 用户暂停测试，把测试 agent 抓取的消息流（s1-s6 的 JSON）留在测试目录供诊断。

### 根因
- 第二轮回炉时加的"回复克制"措辞过宽：`打招呼/确认在线/寒暄请求只用一两句话回应`。
- pi 看到用户消息里有"确认在线状态"几个字，触发字面匹配，**忽略了"请和 codex 互相"将任务转交给 codex 的语义**，只对 human 敷衍一句就停下。
- 同样的"克制"在 `pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT` 和 `cli_bridge.py` 的 pi `[系统]` 块里**各放了一份**，双重保险变成双重压制。

### Current Progress
- **`bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`**：把"回复克制"重写为显式区分 **A/B/C 三类**：
  - **A 类**（用户直接问候/确认状态）：一两句话简短回应
  - **B 类**（用户派 pi 联系另一个 agent）：**必须**用 TALK_ACTION send_message 真的发消息；先简短承接 human 再发 action
  - **C 类**（agent 间互回）：一两句即停，不主动追问/扩展
  - 加 B 类判定信号清单（"请和、让、去问、去找、联系、通知" + agent 名）和"识别到 B 类时优先执行任务转交，不要被 A 或 C 的简短规则覆盖"兜底
- **`bridges/cli_bridge.py`**：`build_cli_prompt` 和 `build_cli_task_prompt` 的 pi 分支**删除重复的"回复克制"行**；语义规则统一由 pi `DEFAULT_SYSTEM_PROMPT` 承载
- **`tests/test_pi_bridge.py`**：加 assertion 守住 A/B/C 区分 + `必须用 TALK_ACTION send_message` + `先简短承接用户一句`等关键短语
- **`tests/test_cli_bridge.py`**：原 `test_build_cli_prompt_for_pi_includes_role_restraint_instructions` 重写为 `test_build_cli_prompt_for_pi_does_not_duplicate_restraint_instructions`，断言 cli_bridge 不再重复注入

### Open Questions / Pending Confirmation
- 待项目管理者**只重启 pi bridge**（codex bridge 与 server 本轮未动）+ **新建测试群**（不复用 `646ab3e4fe7f`，那个含失败试跑的 6 条消息会污染场景 4/5）后复跑 `test_after_5.3.md`
- 重点验证 pi 在场景 1/2 必须真的用 TALK_ACTION 联系 codex（不能再敷衍一句就停）
- 旁观察：第二轮测试时测试 agent 创建群没加 `group:` 前缀（纯 hex `646ab3e4fe7f`），server 接受了；后续可以在 SDK 或 server 加格式规范化

### Verification
- `py_compile bridges/pi_bridge.py bridges/cli_bridge.py tests/test_pi_bridge.py tests/test_cli_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` — 24 tests 全过
- 本轮总计 72 tests 全过

### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 第二轮 (Asia/Shanghai) — 5.3 修复回炉
### 背景
- 第一轮 5.1/5.2/5.3 落地后跑黑盒测试 `test_after_5.3.md`：codex 表现达预期，但 pi 全线 FAIL —— 反复"bobo"幻觉名（场景 2/3/6）、自封"方案评审"（场景 1/9）、寒暄持续扩展（场景 1/2/3/8）。
- 诊断：根因不是 5.3 设计错误或注入逻辑，而是 `bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`（commit `3c7ca9a` 引入，先于 5.1-5.3）硬编码了 `to=human:bobo` 与"评审方案"，并通过 `--system-prompt` argv 以 system role 高权重传给 pi CLI，压垮了 5.3 在 user prompt 末尾的群成员清单注入。codex 没有 system prompt 硬编码所以 5.3 对它生效。

### Current Progress
- **P0：`bridges/pi_bridge.py` 去硬编码**
  - 删除 `DEFAULT_SYSTEM_PROMPT` 中两处 `to=human:bobo`，改为 `to=「清单内的 human id」`（CJK 角括号避免触发 shell metacharacter 守卫）
  - 删除"评审方案"自封定位
  - 新增"回复克制"段（一两句话回应寒暄、不要追问、不要主动 offer 评审/优化/规划等服务）
  - 新增"身份与成员清单"段（明确声明用户消息开头的 `[系统]` 块是唯一身份事实，禁止使用清单外的任何名字 — 即便在过往记忆里出现过）
- **P1：`bridges/cli_bridge.py` pi 路径让 5.3 真正生效**
  - `build_cli_prompt()` 和 `build_cli_task_prompt()` 的 pi 分支：`[系统]` 块从 prompt 末尾挪到开头（高权重位置），新增 `[用户消息]` / `[任务]` 分段
  - pi 现在也拿到了"回复克制"指引（之前完全没拿到 `RESPONSE_STYLE_INSTRUCTIONS`，这是寒暄持续扩展的另一根因）

### Open Questions / Pending Confirmation
- 待项目管理者复跑黑盒测试 `D:\claude-test\black box test\talk\codexscenario-1-scope-fix\test_after_5.3.md`（结果区已清空回模板状态）
- 重点验证 pi 路径：bobo/paddy 应消失、不应自封角色、寒暄一两句即收口；codex 路径不应被打坏；场景 4/5 不变量应保持
- 5.1 / 5.2 / 5.3 第一轮代码完全未动；codex 路径完全未动

### Verification
- `py_compile bridges/cli_bridge.py bridges/codex_bridge.py bridges/pi_bridge.py tests/test_cli_bridge.py tests/test_pi_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过（含新增 2 个 5.3 P1 回归测试）
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` — 24 tests 全过（确认未打坏 codex/discussions/SDK 路径）
- 全量 `unittest discover` — 150 tests，1 个 known-flaky `test_websocket.py` presence timing failure（与本轮改动无关，独立重跑前历史已记录类似 WS timing flakiness）
- 未做真实 Codex+pi 长链路主观体验自测（按黑盒测试设计要求保留给无项目记忆 agent）

### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 (Asia/Shanghai)
### Current Progress
- **修复项 5.1（visible_reply 调度顺序修正）**：`handle_incoming_message()` 中将 `client.reply()` 移到 `execute_talk_actions()` 之前，确保 visible_reply 先回 sender；删除 `"已按讨论协议继续推进。"` 和 `"({bridge_label} finished without visible output.)"` 两个 fallback 文案；action 错误通知作为 follow-up relay。
- **修复项 5.2（去除 prompt 中具体例句）**：`RESPONSE_STYLE_INSTRUCTIONS` 中移除 `"for example '<agent id> 在线。'"` 具体例句，仅保留抽象风格指令。
- **修复项 5.3（Agent 角色注入框架）**：
  - 新增 `--decision-tier` CLI 参数（`decision` / `execution`，缺省 `execution`），bridge 启动配置注入
  - 新增 `_decision_tier_line()` 中文分级描述辅助函数
  - 新增 `_build_group_member_context()`：bridge 在 spawn LLM CLI 前调用 `GET /api/groups/{id}` 获取群成员清单和 metadata，动态拼入 prompt
  - `build_cli_prompt()` 和 `build_cli_task_prompt()` 均注入身份三元事实（`member_id` + `decision_tier` + 业务角色）和群成员约束（只能提及清单内成员）
  - metadata 缺失时走默认严格策略："本群无角色约定，只严格回应字面请求，不要主动扩展话题，不要假设这是项目讨论环境，不要指名群外成员"
  - 新建 `deploy/bridges.example.json` 模板，含 `decision_tier` 字段和字段参考
- pi 和非 pi prompt 格式均同步更新为中文身份声明（"你是 {member_id}，通过 {runtime} CLI bridge 接入 TALK"）
- 测试同步更新：9 个 pi prompt 测试适配新格式，2 个 FakeClient 补充 `get_group` 方法
### Open Questions / Pending Confirmation
- `groups.metadata` 字段尚未落地（待修复项 5.4），5.3 按"metadata 缺失 → 默认严格策略"实现
- PROGRESS.md 第 1 节"Current Agent Role"过渡声明在 5.3 落地后可简化
### Verification
- `py_compile` 10 文件全部通过
- `unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_discussions tests.test_talk_client` 全部通过，70 tests
- 未做真实 Codex+pi 长链路主观体验自测
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `deploy/bridges.example.json`（新建）

## 2026-05-27 00:13 (Asia/Shanghai)
### Current Progress
- 在 `codex/scenario-1-scope-fix` 上补强场景 1 寒暄收口边界：确认 `greeting / closure` 都由 `NON_SUBSTANTIVE_STANCES` 排除，不计入实质 turn。
- 普通可见回复记录改走 `infer_reply_stance()`，寒暄返回 `greeting`，其它路径显式返回 `answer`，避免空 stance 落库。
- 动作转发仍可沿用动作自身 stance；若传入空默认值，会兜底为 `answer`。
- 新增测试覆盖：普通回复 stance 兜底、`greeting / closure` 过滤、已有寒暄 turn 不触发收口。
### Open Questions / Pending Confirmation
- `greeting` 识别仍采用保守关键词法；若后续黑盒验收发现“报个到 / 认识一下”等说法漏标较多，再考虑由模型结构化输出 `is_greeting`。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交本次补强。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，复验黑盒场景 1。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` passed，43 tests。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，59 tests。

## 2026-05-27 00:06 (Asia/Shanghai)
### Current Progress
- 已在分支 `codex/scenario-1-scope-fix` 完成 `SCENARIO1-GREETING-TURNS-1`：收口阈值改为只统计实质 turn，避免把打招呼/在线确认当成议题讨论轮次。
- `discussion_turns.stance` 白名单新增 `greeting / closure`；bridge 会把明确的打招呼/在线确认类短消息记录为 `greeting`，自动收口消息记录为 `closure`。
- `greeting / closure` 被视为非实质 turn，不计入普通收口或分歧升级阈值；`disagree` 仍保留 human 裁决路径。
- `_send_agent_scope_closure()` 保留硬兜底 `resolved` 状态更新，但收口话术改为按 agent id 稳定挑选，避免不同 agent 复读同一句固定机器话。
- 新增/调整测试覆盖：代发打招呼动作为 `greeting` turn、非实质 turn 不触发收口、自动收口记录 `closure`、discussion API 接受 `greeting / closure`。
- 文档已同步 `docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续可由无项目记忆的黑盒测试 agent 复验场景 1。
- `greeting` 识别采用保守规则：任务范围像打招呼/在线确认，且回复较短、包含问候/在线确认特征时才标记为非实质 turn；其它回复仍默认 `answer`。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `SCENARIO1-GREETING-TURNS-1`。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，优先复验黑盒场景 1：打招呼不应过早收口，也不应复读固定收口话术。
3. 若场景 1 通过，再继续处理测试文档中的下一类问题。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，57 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` first run hit existing WebSocket fallback timing timeout once; immediate rerun passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`pause_before_next_slice`，weekly=84%，本轮提交后不再开启新切片。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `server/models.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 18:16 (Asia/Shanghai)
### Current Progress
- `BRIDGE-SAFE-EXTEND-1` 已完成：修复黑盒测试暴露的 bridge 输出安全、开头多 mention、非 Group agent 委托和轻扩展收口问题。
- bridge 现在把消息开头连续 `@member_id` 块视为路由头，传给 CLI 的任务正文会剥离整段路由头；正文中间的 `@agent:*` 仍保留。
- CLI 失败/超时时，聊天可见回复只显示简短失败提示，不再回显 `stderr / stdout / traceback / 本地路径`；任务 `last_error` 仍可记录详细错误。
- malformed 动作协议或内部控制语法残留不会展示到可见回复；`send_message` 目标必须是当前 Group 内存在的 `agent:*`。
- 普通轻扩展允许对方再回答 1 个 turn；随后收到回复的一方自动收口并将 discussion 标记为 `resolved`。`disagree` 场景仍保留 human 裁决路径。
- 新增/调整单元测试覆盖：多 mention 路由头剥离、正文中间 mention 保留、CLI 失败输出安全、malformed 动作残留拦截、缺失 Group agent 代发拦截、轻扩展一轮回答和自动收口。
- 文档已同步 `docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 复验自然对话效果。
- malformed 协议残留拦截采用“控制语法特征”隔离，不做自然语言意图分类；如果未来模型出现新型协议泄漏，可继续收敛规则。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `BRIDGE-SAFE-EXTEND-1`。
2. 重启当前正在运行的 Codex / pi bridge，使新 bridge 逻辑生效。
3. 让无项目记忆测试 agent 复验：多 mention 不报路径错误、`TALK_ACTION` 残留不显示、缺失 agent 不代发、轻扩展只多一轮并收口。
4. 复验通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions` passed，52 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`continue`，session=82%，weekly=76%。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 15:17 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-SCOPE-1` 已完成：为多 Agent 自动交流加入“请求者局部范围”约束，回复必须围绕当前直接提问/派活者的请求。
- `discussion_sessions` 新增可选范围锚点：`root_message_id / requester_id / assignee_id / scope_text`；旧记录允许为空，`init_db()` 会为既有 SQLite 表补列和索引。
- bridge 现在优先沿 `reply_to` / `root_message_id` 复用 discussion scope；已 `resolved / escalated / canceled` 的 scope 不再因普通 agent 回复继续触发模型续聊。
- agent-to-agent prompt 会传入控制上下文和消息原文，要求模型服从当前 scope 且不要把内部 ID/字段展示到可见回复；若可见回复泄漏内部字段，bridge 会替换为确认范围的简短回复。
- agent 普通可见回复若属于 active discussion，即使没有显式 `mark_stance`，也会按 `answer` 记录 turn。
- 新增/调整单元测试覆盖：打招呼 resolved scope 不再续聊、agent 给 agent 派活时 scope prompt 正确、普通 agent 回复自动记 turn、内部字段泄漏拦截、discussion scope API 校验。
- 文档已同步 `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 验收自然对话效果。
- 范围越界识别当前主要依赖结构化 scope、prompt 约束和内部字段泄漏拦截；未做复杂自然语言分类。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `DISCUSSION-SCOPE-1`。
2. 准备黑盒验收任务单，让无项目记忆测试 agent 验证“打招呼不发散”“agent 给 agent 派活不偏题”“内部字段不泄漏”。
3. 验收通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\db.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py tests\test_discussions.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` passed，38 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 11:12 (Asia/Shanghai)
### Current Progress
- `BASIC-CODEX-PI-FLOW-ACCEPT-1` 已完成：重启 TALK server、Codex bridge、pi bridge 后，跑通真实 Codex + pi Group Hall 讨论验收。
- 本轮先清理旧的重复 bridge 进程与 8000 端口上的 uvicorn reload 孤儿进程，再用当前 `.venv` 启动 server、Codex bridge、pi bridge；server 以无 `--reload` 方式运行，避免继续出现 reload 父子孤儿进程；bridge 日志写入 `logs/*current*.log`。
- 验收 Group 为 `group:c52be0b773e6`：human 消息 `#138` 正确触发 Codex；Codex 消息 `#139` 同 Hall 代发给 `@agent:pi`；pi 消息 `#141` 回复 Codex；Codex 消息 `#142` 将最终结论发给 `@human:bobo`。
- Discussion session `#6` 已创建，参与者为 `agent:codex` 与 `agent:pi`，状态从 `active` 变为 `resolved`。
- 项目管理者新增 4 条后续使用建议已记录到当前进度待办：自定义 agent 显示名称；无指定 agent 消息按广播要求所有 agent 接收并回复；删除 Group；自定义角色性格。
### Open Questions / Pending Confirmation
- 本轮首次验收脚本因 PowerShell -> Python 临时脚本编码问题，把中文消息写成 `????`（消息 `#136`）；重试时改用 ASCII 源码内的 Python Unicode escape 后已确认消息 `#138` 中文正确入库。
- 长轮询验收脚本高频 `fetch_history` 时偶发 `httpx.ReadError` / `RemoteProtocolError`，但 server 健康检查保持正常，消息与 discussion 均已落库；后续如要做自动验收脚本，应降低轮询频率或排查 HTTP 连接复用。
- Discussion turns 当前只记录了 Codex 的 `question` 与最终 `answer`；pi 的普通回复消息存在，但未作为 turn 记录，因为本轮 pi 没有输出 `mark_stance` 动作。后续如要完整 UI 展示讨论轮次，需要补“agent 回复自动落 turn”或强化 pi stance 输出。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 进入人工验收：浏览器打开 `http://127.0.0.1:8000/`，用 `human:bobo` 的 API Key 登录，查看 Group `smoke-codex-pi-20260526-b` 中 `#138` 到 `#142` 的完整回合。
2. 验收通过后，下一批建议优先拆需求：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
3. 若先补工程质量，建议处理：自动验收脚本 UTF-8 输入、HTTP 轮询偶发 `ReadError`、pi 回复 turn 记录缺失。
### Verification
- `Invoke-RestMethod http://127.0.0.1:8000/healthz` passed：`status=ok / db=ok / storage=ok / online_members=3`。
- Live smoke passed：`human:bobo -> agent:codex -> agent:pi -> agent:codex -> human:bobo`，消息 `#138` 到 `#142` 均在同一 Group Hall。
- DB verification passed：discussion session `#6` status=`resolved`，Codex / pi 最新实例 status=`idle` 且 `last_error=None`。
- First attempt failed as expected due to temporary PowerShell script encoding: message `#136` became `????` and Codex returned `#137` requesting resend。
- Not rerun: backend unit test suite；本轮只改进度文档并做真实运行验收。
### Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 01:22 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-FSM-TOKEN-SAFE-1` 已完成：按 `docs/p.drawio` 的有限状态机思路，为多 Agent 讨论加入安全动作协议、回合上限、最终答案动作和偏题抑制。
- `bridges/cli_bridge.py` 现在同时解析旧 `<talk-action ...>` 与新 `TALK_ACTION ...` 安全行协议；新增 `final_to_human`，可发送最终答案给 human 并把 discussion 标为 `resolved`。
- agent-to-agent 讨论默认最多 3 个自动 turn；最近一条为 `disagree` 时允许额外 1 个 turn。超限时 bridge 不再调用模型，直接 `@human:*` 请求最终判断并标记 `escalated`。
- agent-to-agent prompt 注入极短讨论上下文：原始话题、当前阶段、剩余回合和 human 目标，并明确禁止引入项目、文档、版本号或施工档等无关话题。
- bridge 会清理开头或结尾的孤立协议残片，例如 `mark_stance`、`update`、`动作已记录...`；模型只输出动作且来源是另一个 agent 时，不再额外发送默认回执。
- `bridges/pi_bridge.py` 默认 system prompt 改为只教授 `TALK_ACTION` 安全行协议，继续避开 Windows `pi.cmd` 高风险命令元字符。
- `tests/test_cli_bridge.py` 与 `tests/test_pi_bridge.py` 已补回归测试，覆盖安全行协议、`final_to_human`、协议残片清理、action-only agent 回执抑制、回合上限升级和 pi prompt 高风险字符限制。
- `docs/spec/MODULE_discussions.md` 与 `docs/spec/MODULE_bridges.md` 已同步当前协议边界。
### Open Questions / Pending Confirmation
- 需要重启 codex bridge 与 pi bridge；旧进程不会自动加载新的协议解析、回合上限和 pi 默认 `--system-prompt`。
- `docs/p.drawio` 是本次评估输入，未被本切片修改；当前仍是未跟踪文件，是否纳入仓库需后续由项目管理者确认。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收，重点观察 pi 不再露出 `mark_stance`、讨论不再跑题、Codex 不再跟随偏题、自动回合数受限。
### Next Plan
1. 提交 `DISCUSSION-FSM-TOKEN-SAFE-1`。
2. 重启 TALK server（如仍是旧进程）、codex bridge 与 pi bridge。
3. 在 Group Hall 重试：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
4. 验收达成共识后能 `final_to_human` 回给 human；若分歧或超限，则自动转 human 裁决。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，34 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions` passed，37 tests。
- 分批验证 passed：`tests.test_codex_bridge tests.test_groups tests.test_messages` 37 tests；`tests.test_files tests.test_healthz tests.test_instances tests.test_members_auth tests.test_tasks` 28 tests；`tests.test_encoding tests.test_setup` 6 tests；`tests.test_talk_client` 11 tests；`tests.test_sse` 6 tests。
- `tests.test_websocket` 聚合运行在当前环境超时；已用逐用例 30s 超时脚本验证 `WebSocketTests` 10 个用例全部单独 passed。
- `.venv\Scripts\python.exe -m unittest` 当前环境超时，未作为通过项记录。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_discussions.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:51 (Asia/Shanghai)
### Current Progress
- `WEB-REPLY-COMPACT-1 / PI-CMD-METACHAR-HOTFIX-1` 已完成：优化多 Agent 讨论中的引用展示，并修复 pi 默认 prompt 在 Windows `pi.cmd` 启动链下被误解释为命令的问题。
- `web/app.js` 的回复引用渲染现在会区分双方互相回复与引用第三方：双方互相回复显示 `A 回复 B` 短文本；引用第三方仍保留原引用框和预览。
- `web/style.css` 新增紧凑引用条样式，去掉大背景与左边框，仅保留小号灰色文本，并继续支持已加载原消息的点击跳转。
- `web/index.html` 静态资源版本号更新为 `20260525-reply-compact`，避免浏览器继续拿旧 CSS/JS。
- `bridges/pi_bridge.py` 默认 system prompt 移除原始 `<talk-action ...>` 示例、`agree|optimize|...` 竖线写法和 Windows 高风险命令元字符，避免 `pi.cmd` 把 prompt 当作管道/重定向语法解析。
- `tests/test_pi_bridge.py` 新增默认 prompt 不包含 `| / < / > / &` 的回归断言。
- `docs/spec/MODULE_webui.md` 与 `docs/spec/MODULE_bridges.md` 已同步本次行为边界。
### Open Questions / Pending Confirmation
- 需要重启 pi bridge；正在运行的旧 pi 进程不会自动加载新的默认 `--system-prompt`。
- Web UI 刷新页面即可加载新静态资源；若仍看到旧引用框，先强制刷新浏览器缓存。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收，重点观察 codex 代发给 pi、pi 回复不再出现 `optimize` 命令错误、双方互相回复时引用条是否紧凑。
### Next Plan
1. 提交本次 hotfix。
2. 重启 pi bridge；必要时一并重启 TALK server 与 codex bridge，确保 server API、bridge 协议和前端资源同版。
3. 重试用户原句：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge` passed，28 tests。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest` passed，129 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
- Browser / in-app browser：已打开 `http://127.0.0.1:8000/` 并确认页面加载 `style.css?v=20260525-reply-compact` 与 `app.js?v=20260525-reply-compact`；受当前 browser 安全/只读执行环境限制，未能构造临时消息样例做视觉断言。
### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `web/app.js`
- `web/style.css`
- `web/index.html`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:21 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-PROTOCOL-1-HOTFIX-1` 已完成：修复 bridge 在 `/api/discussions` 返回 404 时直接抛 `TalkNotFoundError` 的问题。
- 根因：用户实际验收时 codex bridge 已尝试执行 `talk-action`，但 TALK server 可能仍是旧进程或尚未加载 `server/routes/discussions.py`，导致 SDK 在 `client.list_discussions(...)` 处收到 404。
- `bridges/cli_bridge.py` 现在将 discussion API 的 404 视为“讨论记录暂不可用”，跳过 session/turn 写入，但继续执行 `send_message` 代发、可见回复和其它可完成动作。
- `tests/test_cli_bridge.py` 新增 discussion API 缺失时仍能代发 `@agent:*` 且不崩溃的回归测试。
### Open Questions / Pending Confirmation
- 仍建议重启 TALK server、codex bridge、pi bridge，让 server API 与 bridge 协议版本一致；否则可以代发，但不会记录 discussion turn。
### Next Plan
1. 提交 hotfix。
2. 重启服务与 bridge 后重试用户原句：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
3. 观察 Group Hall 是否出现 codex 代发给 pi 的 `@agent:pi ...` 消息，以及 `/api/discussions` 是否记录 session/turn。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_discussions tests.test_pi_bridge` passed，31 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:10 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-PROTOCOL-1` 已完成：新增可记录多 Agent 讨论协议，Discussion Session / Turn 结构化记录讨论参与者、顺序、立场和轮次。
- `server/models.py` 新增 `DiscussionSession`、`DiscussionTurn` 及请求/响应 schema；`server/db.py` 补充 discussion 相关索引。
- 新增 `server/routes/discussions.py` 并接入 `server/main.py`：支持创建/读取/更新 discussion、追加/查询 ordered turns；非 Group 成员不可访问，turn 只能引用当前成员本人在同一 Group Hall 的消息。
- `TALK/client/talk_client.py` 与 sync wrapper 新增 discussion helper，SDK 可创建 session、追加 turn、查询 turns。
- `bridges/cli_bridge.py` 新增 Group Hall 参与者 prompt、`talk-action` 解析与执行：`send_message` 可同 Hall 代发 `@agent:*` 并自动创建/复用 discussion，`mark_stance` 可记录当前回复立场，连续两条不同 agent 的 `disagree` 后自动 `@human:*` 升级仲裁。
- `bridges/pi_bridge.py` 默认 system prompt 改为 TALK Group Hall 参与者身份与动作协议；默认仍是讨论档，新增 `--pi-execution-profile tools` 显式施工档，使用默认命令时启用 `read,grep,find,ls,bash,edit,write`。
- 新增 `docs/spec/MODULE_discussions.md`，并同步 `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_groups.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 需要重启 codex/pi bridge 后才能加载本次新协议。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只在显式 `--pi-execution-profile tools` 时启用；后续若让 pi 真正施工，需要按任务明确授权并验收。
- Codex + pi 双 Agent 真实端到端讨论仍需人工验收。
### Next Plan
1. 提交 `DISCUSSION-PROTOCOL-1`。
2. 重启 bridge 后，在 Group Hall 验收 Codex 向 pi 转交计划、pi 回复优化/分歧、两轮分歧升级 human。
3. 后续补 Web UI discussion 面板，并评估与任务队列、文档锁、SSE 的联动。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\main.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py bridges\pi_bridge.py tests\test_discussions.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_talk_client.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge tests.test_pi_bridge` passed，30 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge tests.test_groups tests.test_messages` passed，37 tests。
- `.venv\Scripts\python.exe -m unittest` passed，128 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_groups.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 12:21 (Asia/Shanghai)
### Current Progress
- `PI-SYSTEM-PROMPT-BOUNDARY-1` 已完成：按项目管理者确认，将 pi 的身份/能力边界从用户 prompt 中移到默认 `pi --system-prompt`，避免 `TALK...` 等包装文本被 pi 当成用户没说完的正文。
- `bridges/pi_bridge.py` 默认命令恢复极短中文 `--system-prompt`，同时继续保留 `--no-context-files --no-tools --no-session --thinking off`。
- `bridges/cli_bridge.py` 的 pi 消息 prompt 现在只返回去掉 `@agent:pi` 后的用户原文，例如 `@agent:pi 你好` 精确传给 pi 为 `你好`。
- pi 队列任务 prompt 默认只传 `content`；如存在 `title`，传 `标题：<title>\n\n<content>`。
- pi prompt 不再包含 `用户消息`、`用户任务`、`回复要求`、`Sender`、`TALK message id`、`TALK task id`、`Task creator`、`TALK group id` 或 `Project root`；但实际回复仍携带原消息 `group_id` 写回同一个 Group Hall。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签回复时才替换；正常中文或用户明确要求英文时不干预。
- `tests/test_cli_bridge.py` 已更新 pi prompt 断言：普通消息精确等于去 mention 后原文、队列任务只保留正文/标题、Group Hall 回复仍保留原 `group_id`。
- `tests/test_pi_bridge.py` 已更新默认命令断言：必须包含 `--system-prompt` 与隔离参数。
- `docs/spec/MODULE_bridges.md` 已同步 pi system prompt 分离边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次修复。
- 重启后建议验收：`@agent:pi 你好`、`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 如果用户使用 `TALK_PI_COMMAND` 或 `--pi-command` 自定义 pi 命令，需要自行带上等价 `--system-prompt` 和隔离参数。
### Next Plan
1. 提交本次 `PI-SYSTEM-PROMPT-BOUNDARY-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，23 tests。
- 分组显式全量 passed，合计 121 tests：`tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_pi_bridge` 35 tests；`tests.test_files tests.test_groups tests.test_healthz tests.test_members_auth tests.test_messages` 40 tests；`tests.test_instances tests.test_tasks tests.test_talk_client` 27 tests；`tests.test_setup tests.test_sse tests.test_websocket` 19 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 11:41 (Asia/Shanghai)
### Current Progress
- `PI-MINIMAL-PROMPT-1` 已完成：按项目管理者确认，将 pi bridge 输入包装改为“用户原话优先”的极简 prompt，减少英文元指令对 pi 语言选择和身份判断的干扰。
- `bridges/cli_bridge.py` 中 pi 消息 prompt 现在以 `用户消息：` 开头，直接放去掉 `@agent:pi` 后的原话；pi 队列任务 prompt 以 `用户任务：` 开头，只有任务标题存在时才作为用户任务内容的一部分保留。
- pi prompt 后置一条中文短边界：`你是 TALK 群聊里的 pi，按用户语言自然回复。默认不要声称能读取项目文件、执行命令、编辑文件或调用工具。不要输出 <Language: ...> 之类语言标签。`
- pi prompt 不再传入 `Sender`、`TALK message id`、`TALK task id`、`Task creator` 或 `TALK group id`；但实际回复仍携带原消息 `group_id` 写回同一个 Group Hall。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签回复时才替换；正常中文或用户明确要求英文时不干预。
- `tests/test_cli_bridge.py` 已更新 pi prompt 断言：用户原话在最前、无不必要元信息、包含中文短边界、Group Hall 回复仍保留原 `group_id`。
- `docs/spec/MODULE_bridges.md` 已同步 pi 极简 prompt 边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次极简 prompt 修复。
- 重启后建议验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 不会自动改写；本次修复只影响后续新回复。
- 单条显式全量 `unittest` 本轮 300 秒超时且无失败栈；分组运行同一模块集合合计 120 tests 全部通过。
### Next Plan
1. 提交本次 `PI-MINIMAL-PROMPT-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- 分组显式全量 passed，合计 120 tests：bridge/pi/encoding 34 tests；files/groups/healthz/auth/messages 40 tests；instances/tasks/client 27 tests；setup/sse/websocket 19 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` timeout after 300s，无失败栈。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 11:16 (Asia/Shanghai)
### Current Progress
- `PI-LANGUAGE-REPLY-1` 验收期修复已完成：根据用户反馈，排查最近 Group Hall 消息，确认 `#38 -> #39` 为中文功能问题却返回 `<Language: ar>` 阿拉伯语；`#40 -> #41` 明确要求中文却返回英文，并误称自己能读文件、执行命令、编辑文件。
- 根因判断：消息已正确写入同一个 Group Hall，路由和 `group_id` 回复不是问题；问题在于 pi 撤销命令级强 system prompt 后，TALK prompt 语言跟随约束不足，且缺少窄范围后处理来拦住明显跑语种/能力误述。
- `bridges/cli_bridge.py` 新增 `PI_CHAT_INSTRUCTIONS`：pi 继续是自然聊天的 TALK chat member，但明确要求回复语言跟随用户任务；用户要求中文时使用简体中文；不要输出 `<Language: ...>` 标签；能力介绍只能描述轻量聊天、回答问题、拆解任务、参与 Group Hall 协作，不得声称默认 bridge 模式能读文件、执行命令、编辑文件或调用工具。
- `bridges/cli_bridge.py` 新增 pi 成功输出后的中文归一化兜底：当中文任务/能力问题得到明显非中文回复或语言标签回复时，替换为中文能力说明；真实 CLI 失败或超时不做替换，避免遮盖错误。
- `tests/test_cli_bridge.py` 新增回归覆盖：pi prompt 语言要求、能力边界、中文能力问题的非中文回复替换、阿拉伯语语言标签替换、明确要求英文时不误替换、Group Hall 中 pi 回复仍保留原 `group_id`。
- `docs/spec/MODULE_bridges.md` 已同步 pi 语言跟随与中文能力兜底边界；默认 `pi_bridge.py` 命令仍不使用 `--system-prompt`。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次修复。
- 重启后建议验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 不会自动改写；本次修复只影响后续新回复。
- `python -m unittest` discovery 在本轮环境中超时但无失败栈；显式模块列表全量 120 tests 已通过，后续可单独排查 discovery 阻塞原因。
### Next Plan
1. 提交本次 `PI-LANGUAGE-REPLY-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` passed，120 tests。
- `.venv\Scripts\python.exe -m unittest` 超时 120 秒；`.venv\Scripts\python.exe -m unittest -v` 超时 300 秒，均未输出失败栈。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 22:15 (Asia/Shanghai)
### Current Progress
- `PI-NATURAL-CHAT-1` 验收期修正已完成：按用户确认，将 pi 调整为“自然回答的 TALK 聊天成员”，不再用强 system prompt 或 bridge 弱回复替换限制它的回答风格。
- 设计判断已确认：方向上与 OpenHanako 一致，平台应负责上下文/权限隔离；Agent 在频道里默认是聊天成员，不应因为 bridge 从 TALK 代码项目根目录启动，就自动成为 TALK 项目的开发 Agent。
- `bridges/pi_bridge.py` 默认命令已移除 `--system-prompt`，只保留 `--no-context-files --no-tools --no-session --thinking off`，用于防止 pi 自动读取 TALK 代码项目上下文、调用工具或恢复旧会话。
- `bridges/cli_bridge.py` 已移除能力问题弱回复替换逻辑；pi 的成功输出不再被 bridge 改写。
- pi 的消息与任务 prompt 不再包含 `Project root`，只标识为 `TALK chat member`，并携带发送人/任务创建人、消息或任务 id、可选 group id 与用户任务。
- `tests/test_cli_bridge.py` 已覆盖 pi 消息/任务 prompt 不含项目根路径；`tests/test_pi_bridge.py` 已覆盖 pi 默认命令不再包含 `--system-prompt`，但仍保留隔离参数。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge 后重新验收；正在运行的旧 pi bridge 不会自动加载本次修正。
- 重启后建议验收：`@agent:pi 你好`、`@agent:pi 你能做啥？给我介绍下`、`@agent:pi 随便聊两句`，观察 pi 是否自然回答，同时不再输出 TALK 项目进度报告。
- 后续可把“上下文/工具/文件权限由平台管理”的设计沉淀为 Group/Agent 协议，而不是依赖各 bridge 的 CLI 参数。
### Next Plan
1. 提交本次 `PI-NATURAL-CHAT-1` 验收期修正。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 自然聊天回复。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，17 tests。
- `.venv\Scripts\python.exe -m unittest` passed，115 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 22:00 (Asia/Shanghai)
### Current Progress
- `PI-CAPABILITY-REPLY-1` 验收期修复已完成：修复用户在 Group Hall 询问 `@agent:pi 你能做啥？/ 给我介绍下` 时，pi 只回复 `ok` 或在线待命话术的问题。
- 现场排查确认：消息 id 32 -> 33 为 `@agent:pi 你能做啥？` 后回复 `ok`；消息 id 36 -> 37 为 `@agent:pi 你能做啥？给我介绍下` 后回复 `Pi agent online. What task would you like me to help with?`。消息已正确进入同一个 Group Hall，说明问题不在路由，而在 pi 默认提示词缺少能力介绍边界，以及模型弱回复没有兜底。
- `bridges/pi_bridge.py` 已补充默认 system prompt：当用户询问能力或介绍时，pi 应说明自己适合轻量聊天、回答问题、拆解任务和参与 TALK 群聊协作，并说明默认桥接模式不读取项目文件、不调用工具。
- `bridges/cli_bridge.py` 已新增能力问题弱回复兜底：当任务问“你能做啥 / 你能做什么 / 介绍下”等，而 CLI 成功输出只有 `ok`、`standing by` 或在线待命话术时，bridge 会替换为一条可验收的能力说明。
- `tests/test_cli_bridge.py` 已覆盖 pi 能力问题弱回复替换；`tests/test_pi_bridge.py` 已覆盖 pi 默认 system prompt 包含能力介绍边界。
- `docs/spec/MODULE_bridges.md` 已同步 pi 能力介绍提示词与弱回复兜底边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge 后重新发送 `@agent:pi 你能做啥？给我介绍下` 验收；正在运行的旧 pi bridge 不会自动加载本次修复。
- 如果用户使用 `TALK_PI_COMMAND` 或 `--pi-command` 自定义 pi 命令，需要保留默认命令中的 system prompt 边界，或自行提供等价提示词。
### Next Plan
1. 提交本次 `PI-CAPABILITY-REPLY-1` 验收期修复。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 能力介绍回复。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，18 tests。
- `.venv\Scripts\python.exe -m unittest` passed，116 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:53 (Asia/Shanghai)
### Current Progress
- `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复已完成：修复 Codex 回复中 `taskkill` 噪声已被过滤后，正文“在线。”仍显示为 `鍦ㄧ嚎銆` 一类 mojibake 的问题。
- 现场排查确认：数据库最新 Codex 回复已不再包含 PID 清理提示，但 `content` 中“在线。”被错误解码成 mojibake，说明上一版噪声过滤生效但编码选择仍不够细。
- 根因是 Codex stdout 中混合了不同编码来源：Windows `taskkill` 行更像系统代码页，Codex 正文行是 UTF-8；按整段输出选择单一编码会互相拖累。
- `bridges/cli_bridge.py` 的 `decode_subprocess_output(...)` 已改为逐行选择编码；同一 stdout 中 GBK 清理提示和 UTF-8 正文可以分别正确解码。
- `tests/test_cli_bridge.py` 已新增混合编码行回归测试，覆盖 GBK `taskkill` 行 + UTF-8 `codex 在线。` 行的组合。
- `docs/spec/MODULE_bridges.md` 已同步通用 CLI bridge 的逐行解码边界。
### Open Questions / Pending Confirmation
- 需要用户再次重启 Codex bridge 后重新发送 `@agent:codex 你好` 验收；正在运行的旧 Codex bridge 不会自动加载本次修复。
- 历史消息 id 29 已经写入数据库，仍会保留旧 mojibake 内容；本次修复只影响后续新回复。
### Next Plan
1. 提交本次 `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复。
2. 用户重启 Codex bridge 后，继续在 Group Hall 验收 Codex 回复内容是否干净且中文正常。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_encoding` passed，18 tests。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:41 (Asia/Shanghai)
### Current Progress
- `CODEX-BRIDGE-OUTPUT-1` 验收期修复已完成：修复 Codex 在 Group Hall 回复“在线”前混入 Windows 进程终止提示且中文乱码的问题。
- 现场排查确认：最新 Codex 回复已写回 Group Hall，说明 `GROUP-BRIDGE-REPLY-1` 的同 Hall 回复修复已生效；但消息内容包含乱码的 `taskkill` PID 成功提示，对应 Windows 进程清理输出被错误编码解码后混入回复。
- `bridges/cli_bridge.py` 已新增 `decode_subprocess_output(...)`：优先 UTF-8，并在出现替换字符时兜底尝试系统代码页、`gbk`、`cp936`，降低 Windows 本地 CLI 中文输出乱码概率。
- `format_cli_reply(...)` 现在会对 stdout / stderr 做 `taskkill` 噪声过滤，避免 Codex CLI 退出清理子进程时的 PID 提示出现在前端聊天回复里。
- `tests/test_cli_bridge.py` 已新增 GBK 输出解码与中英文/乱码 `taskkill` 过滤回归测试。
- `docs/spec/MODULE_bridges.md` 已同步通用 CLI bridge 的 Windows 输出编码与进程清理噪声过滤边界。
### Open Questions / Pending Confirmation
- 需要用户重启 Codex bridge 后重新发送 `@agent:codex 你好` 验收；正在运行的旧 Codex bridge 不会自动加载本次修复。
- 历史消息 id 23 已经写入数据库，仍会保留旧乱码内容；本次修复只影响后续新回复。
### Next Plan
1. 提交本次 `CODEX-BRIDGE-OUTPUT-1` 验收期修复。
2. 用户重启 Codex bridge 后，继续在 Group Hall 验收 Codex 回复内容是否干净。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，25 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，114 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:37 (Asia/Shanghai)
### Current Progress
- `GROUP-BRIDGE-REPLY-1` 验收期修复已完成：修复 Group Hall 中 `@agent:codex` / `@agent:pi` 后 bridge 已收到消息但回复失败的问题。
- 现场排查确认：用户新建 group 后发送的两条消息都已写入 `messages.group_id`，`to_ids` 分别为 `["agent:codex"]` 与 `["agent:pi"]`，且两个 bridge 都已领取到对应消息。
- 两个实例失败原因一致：`agent_instances.last_error` 为 `cannot_reply_to_different_group`，说明 bridge 处理了消息，但回复时没有保留原 Hall 上下文。
- `bridges/cli_bridge.py` 已抽出 `handle_incoming_message(...)`，统一处理 ACK、CLI 调用、最终回复和状态上报；当原消息带有 `group_id` 时，ACK 与最终 `reply_to` 都会携带同一个 `group_id`。
- CLI prompt 现在包含 `TALK group id`，便于 Codex / pi 等外部 Agent 感知当前消息来自哪个 Group Hall。
- `tests/test_cli_bridge.py` 已新增 Group Hall prompt 与同 group 回复回归测试，覆盖 `group_id` 传递行为。
- `docs/spec/MODULE_bridges.md` 已同步 Codex / pi Group Hall 当前能力与后续 HTTP fallback group cursor 边界。
### Open Questions / Pending Confirmation
- 需要用户重启 Codex bridge 与 pi bridge 后重新验收；正在运行的旧进程不会自动加载本次代码修复。
- 本次现场失败的旧消息不会自动重试；重启 bridge 后需在前端 Group Hall 中重新发送新的 `@agent:codex` / `@agent:pi` 消息。
- Group Hall 的实时触发当前主要依赖 WebSocket；Agent group cursor / HTTP fallback 轮询仍留作当前验收后的下一阶段设计。
### Next Plan
1. 提交本次 `GROUP-BRIDGE-REPLY-1` 验收期修复。
2. 用户重启 Codex / pi bridge 后，继续在前端 Group Hall 验收双 Agent 回复。
3. 验收通过后，再评估下一阶段多 Agent 自动讨论协议。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_talk_client` passed，23 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，112 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 16:41 (Asia/Shanghai)
### Current Progress
- `OPENHANAKO-REF-1` 文档沉淀已完成：用户提供 `liliMozi/openhanako` 作为多 Agent 拉群交流参考后，已把对 TALK 有帮助的设计点记录到项目文档。
- `docs/spec/LOCAL_LAB_DESIGN.md` 已新增 OpenHanako 参考笔记，记录参考版本 `dbc794de87d58b44bbf5f75f8d20fd99a5d7e156` 与重点文件：`hub/channel-router.js`、`lib/channels/channel-ticker.js`、`lib/channels/channel-store.js`、`lib/channels/channel-mentions.js`、`lib/tools/dm-tool.js`。
- 已记录可借鉴点：Group Hall 作为真相源、`@mention` 只表示提醒/调度、Agent 显式 `reply/pass`、Agent group cursor、`max_rounds / cooldown / max_agent_checks` 等调度保护。
- 已记录不照搬内容：Electron / Node Hub 架构、Markdown 文件频道存储、主动心跳、长期记忆、人格系统、复杂桌面工作台。
- `docs/spec/MODULE_groups.md` 已补充 Group/Hall 后续协议参考，明确 TALK 继续使用 SQLite 的 `groups / group_members / messages` 扩展。
### Open Questions / Pending Confirmation
- OpenHanako 参考只作为当前验收后的下一阶段设计素材；是否实现 Agent group cursor、`reply/pass` 决策协议和自动讨论调度器，需等 Codex + pi + Web UI 联合验收完成后再确认。
### Next Plan
1. 提交本次 `OPENHANAKO-REF-1` 文档沉淀。
2. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
3. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。
### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 18:13 (Asia/Shanghai)
### Current Progress
- `PI-BRIDGE-CHAT-1` 验收期修复已完成：针对用户反馈的 pi 回复慢、回复过长、即使要求一句话仍带入项目状态报告的问题，收敛 pi bridge 默认运行方式。
- `bridges/pi_bridge.py` 默认命令从裸 `pi --print --mode text` 调整为聊天验收模式：增加 `--no-context-files --no-tools --no-session --thinking off`，并通过 `--system-prompt` 要求 pi 只回复 TALK 用户任务、不要读取/总结项目文件或进度。
- 通用 `bridges/cli_bridge.py` 新增“一句话”兜底：当任务文本包含“一句话 / one sentence / single sentence”等约束时，CLI 成功输出会在 bridge 层收敛为第一句或第一行后再发回 TALK。
- `tests/test_pi_bridge.py` 已覆盖 pi 默认命令中的上下文/工具/session/thinking/system prompt 收敛参数。
- `tests/test_cli_bridge.py` 已覆盖“一句话”输出收敛逻辑。
- `docs/spec/MODULE_bridges.md` 已同步 pi 默认命令的新边界，并提醒自定义 `TALK_PI_COMMAND` / `--pi-command` 时需自行保留收敛参数。
### Open Questions / Pending Confirmation
- 需用户重启 pi bridge 后在前端人工验收：`@agent:pi 只用一句话回复：你在线吗？` 应返回简短一句，不再输出项目状态报告。
- 如果用户当前通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义了 pi 命令，需要同步加入本次默认命令中的收敛参数；否则会绕过默认修复。
- 本轮未真实调用 DeepSeek/pi 模型 API，只通过命令参数、单元测试和全量测试验证 bridge 行为。
### Next Plan
1. 提交本次 `PI-BRIDGE-CHAT-1` 修复。
2. 用户重启 pi bridge 后继续前端人工验收。
3. 验收通过后继续 Codex + pi 双 Agent 回复链路与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，12 tests。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，110 tests。
- `node --check web\app.js` passed。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:59 (Asia/Shanghai)
### Current Progress
- `WEB-MENTION-ENTER-1` 验收期修复已完成：修复前端在 `@` 补全下拉打开时按 Enter 会先发送裸 `@`，导致服务端返回 `invalid recipient mention: @` 的问题。
- `web/app.js` 的消息发送快捷键现在会在 mention 下拉框可见时让出 Enter，避免与补全选择逻辑抢事件顺序。
- mention 补全逻辑已调整为：下拉框打开时，Enter / Tab 都会选择当前高亮项；若没有高亮项，则选择首个候选。
- mention 候选项增加 `mousedown` 防 blur 处理，鼠标点击选择 `agent:pi` / `agent:codex` 时会稳定补全到输入框。
- `web/index.html` 已更新 `app.js` 版本参数，浏览器刷新后会加载本次修复。
### Open Questions / Pending Confirmation
- 需用户刷新前端页面后继续人工验收：输入 `@`，分别用 Enter 和鼠标选择 `agent:pi` / `agent:codex`，确认不再出现裸 `@` 错误。
- Codex + pi 双 bridge 的真实端到端回复仍在人工验收中；本切片只修复前端 mention 补全误发送问题。
### Next Plan
1. 提交本次 `WEB-MENTION-ENTER-1` 修复。
2. 用户刷新页面后复测 `@` 补全选择。
3. 重启 Codex / pi bridge，继续双 Agent 回复与 Web UI 视觉/交互联合验收。
### Verification
- Browser / in-app browser 手工验证 passed：输入裸 `@` 后按 Enter 会补全为首个候选，不再出现 `invalid recipient mention: @`。
- Browser / in-app browser 手工验证 passed：输入 `@agent:p` 后鼠标点击 `agent:pi` 候选，会稳定补全为 `@agent:pi `。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，108 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `web/app.js`
- `web/index.html`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:35 (Asia/Shanghai)
### Current Progress
- `BRIDGE-WINDOWS-CMD-1` 验收期修复已完成：修复 Windows 下 bridge 直接调用 `codex` / `pi` 找不到命令的问题。
- 用户在前端 `@agent:codex` / `@agent:pi` 后未收到回复；排查确认 TALK 服务在线，消息已正确写入 `messages.to_ids`，bridge 进程在线并轮询任务，但 `agent_instances` 中 Codex / pi 均上报 `error`，`last_error` 为 `[WinError 2] 系统找不到指定的文件。`。
- `bridges/cli_bridge.py` 在启动子进程前会用 `shutil.which()` 解析命令入口，使 `pi` 可解析到 `pi.CMD`。
- `bridges/codex_bridge.py` 默认优先使用 `~\AppData\Local\OpenAI\Codex\bin\codex.exe`，避免命中 WindowsApps 中会 `Access is denied` 的 `codex.exe`。
- 新增测试覆盖：通用命令入口解析，以及 Codex 默认命令的环境变量覆盖路径。
### Open Questions / Pending Confirmation
- 需用户重启 Codex / pi bridge 后，在前端重新发送 `@agent:codex` 与 `@agent:pi` 消息完成回复验收。
- 当前已有旧 bridge 进程处于错误状态；建议在启动新 bridge 前先在原终端 `Ctrl+C` 停掉旧进程，避免多个实例同时处理。
### Next Plan
1. 提交本次 `BRIDGE-WINDOWS-CMD-1` 验收期修复。
2. 重启 Codex / pi bridge，再在前端重新发送消息验收。
3. 验收通过后，继续完成 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，18 tests。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:01 (Asia/Shanghai)
### Current Progress
- `PI-BRIDGE-1` 已完成：新增 `bridges/pi_bridge.py`，默认注册 `agent:pi`，默认 runtime 为 `pi`，默认错误标签为 `pi bridge`。
- `pi_bridge.py` 默认调用 `pi --print --mode text`；可通过 `TALK_PI_COMMAND` 或 `--pi-command` 覆盖，例如切换 provider / model。
- 通用 `bridges/cli_bridge.py` 已支持 `--prompt-transport stdin|argv`：Codex 继续用 stdin，pi 默认用 argv，把 TALK prompt 追加为最后一个命令行参数。
- 新增 `tests/test_pi_bridge.py`，覆盖 pi 默认身份、默认命令、argv prompt 传递方式与自定义 `--pi-command`。
- 扩展 `tests/test_cli_bridge.py`，覆盖通用 bridge 的 argv prompt 传递以及 queued task 调用时传递 `prompt_transport`。
- 本机已确认 `pi --help` 与 `pi --version` 可执行，版本为 `0.74.1`。
- `docs/spec/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步 pi bridge 入口、启动命令和当前边界。
### Open Questions / Pending Confirmation
- 真实 pi 模型调用仍依赖本机 `pi` 的 provider/API key 配置；本轮未消耗真实模型请求，只验证 CLI 入口与桥接参数。
- Codex + pi 双 Agent 同时运行的真实端到端回合尚未执行；下一步应进入人工验收或补一个双桥 smoke 脚本。
- 本里程碑验收必须同时覆盖 Web UI：此前 Web UI 第一版质量不达标，后续已按 `image_gen` 视觉稿方向重做并记录在 `docs/spec/MODULE_webui.md` 的 `WEB-VISUAL-2 Addendum`，需要和双 Agent bridge 一起验收。
### Next Plan
1. 提交本次 `PI-BRIDGE-1` 切片。
2. 按里程碑门禁暂停，提供 Codex + pi 双 bridge 与 Web UI 视觉/交互的联合人工验收步骤。
3. 验收通过后，下一候选切片是双 Agent 最小回合脚本 / 讨论 runner。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_encoding` passed，19 tests。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `pi --help` passed。
- `pi --version` returned `0.74.1`。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，105 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。
### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 16:54 (Asia/Shanghai)
### Current Progress
- `CLI-BRIDGE-1` 已完成：新增 `bridges/cli_bridge.py` 通用 CLI bridge，承接 TALK 成员注册、实例状态上报、消息触发、任务队列轮询、任务认领、CLI stdin/stdout 调用、结果回复与任务完成。
- `bridges/codex_bridge.py` 已收敛为 Codex 兼容入口：复用通用 CLI bridge 实现，同时保留 `--codex-command`、默认 `codex exec` 命令、`CodexRunResult` 和原 helper 函数兼容面。
- 通用 CLI bridge 支持 `--name / --runtime / --bridge-label / --command`：例如后续 `pi` 可注册为 `agent:pi`，以 `runtime=pi` 上报实例，并使用可配置命令读取 stdin prompt、输出 stdout 回复。
- 新增 `tests/test_cli_bridge.py`，覆盖通用 CLI 参数必填、runtime prompt、错误回复标签、stdin/stdout 命令执行、queued task 认领/回复/完成路径。
- `tests/test_codex_bridge.py` 继续通过，确认 Codex 旧兼容面未破坏。
- `docs/spec/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步通用 CLI bridge、Codex 兼容入口和 pi 接入方向。
### Open Questions / Pending Confirmation
- 用户方向判断已确认：先把 Codex bridge 泛化为通用 CLI bridge，是更快跑通 Codex + pi 双 Agent 的路线。
- pi 的具体 CLI 启动命令 / stdin/stdout 协议仍需确认；若 pi 不能直接从 stdin 读 prompt 并向 stdout 写最终回复，需要补一个很薄的 pi adapter。
- 本轮未做真实 Codex + pi 双进程端到端验收；下一切片应优先补 pi 启动示例 / adapter 与最小双 Agent 回合验证。
### Next Plan
1. 提交本次 `CLI-BRIDGE-1` 切片。
2. 下一切片：基于 `bridges/cli_bridge.py` 落 `pi` 启动示例 / adapter，并用 fake CLI 或真实 pi 命令跑通 `agent:codex <-> agent:pi` 的最小任务回合。
3. 若 pi 命令可直接适配 stdin/stdout，优先做配置与验收脚本；否则先实现 pi adapter。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge` passed，13 tests。
- `.venv\Scripts\python.exe bridges\cli_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，102 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 23:16 (Asia/Shanghai)
### Current Progress
- `TASK-SCHEDULE-1` 已完成：新增 `agent_task_schedules` 表与 `/api/tasks/schedules` API 第一版。
- `agent_tasks` 新增可选 `schedule_id`，用于追踪由 schedule 物化出的 queued task。
- Schedule 支持一次性计划与周期计划：未传 `interval_seconds` 为 `once`，传入后为 `interval`。
- 新增 `POST /api/tasks/schedules/run-due`：显式物化当前到期的 active schedule，返回 `created_tasks` 与 `updated_schedules`。
- 一次性 schedule 物化后状态变为 `completed`；周期 schedule 物化后保持 `active` 并推进 `next_run_at`。
- Schedule 列表与读取沿用任务可见性：Human 可读全部，Agent 只能读目标为自己或自己创建的 schedule。
- Schedule 状态更新支持 `active`、`paused`、`canceled`；completed / canceled 不可恢复为 active 或 paused。
- SDK 已新增 async/sync schedule helper：创建、列表、读取、更新状态、运行到期计划。
- `docs/spec/MODULE_tasks.md` 与 `docs/PROJECT_BRIEF.md` 已同步数据模型、接口契约、当前边界和验收点。
### Open Questions / Pending Confirmation
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- Group 删除 / 归档语义仍需确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- 文档编辑锁协议、任务状态接入 Hall / Group Web UI 仍待实现。
### Next Plan
1. 提交本次 `TASK-SCHEDULE-1` 切片。
2. 下一候选切片：文档编辑锁协议，或将任务 / schedule 状态接入 Hall / Group Web UI。
3. Group 删除 / 归档语义需项目管理者确认后再做。
### Verification
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/slice-usage-gate.ps1 -Agent codex` returned `continue`。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\tasks.py server\db.py tests\test_tasks.py tests\test_talk_client.py TALK\client\talk_client.py TALK\client\talk_client_sync.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_talk_client` passed，22 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，97 tests。
- `git diff --check` passed（仅换行提示）。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-progress.ps1 -Strict -RequireHistory` passed。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-git-ready.ps1` passed。
### Changed Files
- `server/models.py`
- `server/routes/tasks.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 18:13 (Asia/Shanghai)
### Current Progress
- `GROUP-UPDATE-1` 已完成：新增 `PATCH /api/groups/{group_id}`，human 可更新 Group 名称与描述，agent 不可更新。
- `GroupUpdate` schema 已加入服务端校验：`name` 必填且去空白，`description` 可选且空字符串归一为 `None`。
- SDK 已新增 async/sync `update_group(...)` helper。
- Web UI 已在 Hall 成员面板顶部加入 Group 设置表单，保存后会刷新 room strip、成员面板与 mention/presence 相关视图。
- 静态资源 cache busting 已更新到 `20260520-group-meta`。
- Group 删除未在本切片实现：删除会影响历史 Hall 消息可见性，属于需要项目管理者确认的数据语义。
- `docs/spec/MODULE_groups.md` 已同步接口契约、Web UI 能力、当前边界和验收点。
### Open Questions / Pending Confirmation
- Group 删除 / 归档语义仍需确认：历史 Hall 消息应保留、归档还是随 Group 删除。
### Next Plan
1. 下一候选切片：确认并实现 Group 删除 / 归档语义，或文档编辑锁协议。
2. 如继续前端 / SSE 相关切片，保持 Browser 真实页面烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\groups.py tests\test_groups.py tests\test_talk_client.py` passed。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_talk_client` passed，15 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，92 tests。
- `git diff --check` passed（仅换行提示）。
- Browser 真实页面验证 passed：human 在成员面板更新 Group 名称与描述后，Hall 标题、房间按钮、成员面板输入值和空时间线文案均同步刷新。
### Changed Files
- `server/models.py`
- `server/routes/groups.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_groups.py`
- `tests/test_talk_client.py`
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 17:19 (Asia/Shanghai)
### Current Progress
- `BRIDGE-TASK-QUEUE-1` 已完成：Codex bridge 默认同时轮询 `/api/tasks?target_member_id=<member_id>&status=queued`，按任务 `id` 从小到大认领属于自己的 queued task。
- 新增任务 prompt 构造路径：把 `created_by / task id / title / content / workdir` 注入 Codex CLI stdin，区别于原有消息触发 prompt。
- 新增 `handle_queued_task(...)`：认领任务、运行 Codex CLI、格式化输出、向任务创建者发送直接文本结果消息，并通过 `/api/tasks/{id}/complete` 写入 `succeeded / failed`、`result_message_id` 与 `last_error`。
- 新增任务队列后台 worker：与消息处理共用 `run_lock`，保证单个 bridge 实例不会并发启动多个 Codex CLI 进程。
- CLI 新增 `--task-poll-interval` 与 `--disable-task-queue`；默认开启任务队列轮询，保留旧的消息触发模式。
- `docs/spec/MODULE_bridges.md` 已同步任务队列行为、CLI 开关与验收点。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；本轮是 bridge/任务协议相关切片，按协议完成 1 个切片后暂停汇总并提交。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测；本切片未改前端，因此未做 Browser 真实页面验证。
### Next Plan
1. 提交本次 `BRIDGE-TASK-QUEUE-1` 切片。
2. 后续如需推送，当前分支会包含上一条 `SSE-BACKFILL-1` 本地提交与本次 bridge 提交。
3. 下一候选切片：Group 重命名/删除 UI，或文档编辑锁协议。
4. Browser runtime 恢复后，补一次 Web UI SSE 真实浏览器烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\codex_bridge.py tests\test_codex_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge` passed，8 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge tests.test_tasks tests.test_talk_client` passed，25 tests。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe -m unittest` passed，90 tests。
### Changed Files
- `bridges/codex_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 10:38 (Asia/Shanghai)
### Current Progress
- `SSE-BACKFILL-1` 已完成：`GET /api/events` 已支持 `Last-Event-ID` header 与 `last_event_id` query 参数。
- 连接建立时会先完成 SSE 实时订阅并发送在线快照，再按当前成员可见性补发 `message.id > last_event_id` 的历史消息快照，降低重连窗口中的事件丢失风险。
- 补发查询覆盖全局可见消息与当前成员所在 Group 的 Hall 消息，并会过滤对当前成员不可见的消息。
- 撤回消息按当前 `MessageOut` 快照语义补发：`revoked=true`，正文、附言和文件快照字段保持隐藏。
- 若同一消息同时出现在补发结果和实时队列中，服务端会按 SSE `id:` 去重后再输出。
- `docs/spec/MODULE_websocket.md` 已同步接口契约、当前实现与验收标准。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；本轮按协议切片规则完成 1 个切片后暂停汇总。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测；本切片未改前端，因此未做 Browser 真实页面验证。
### Next Plan
1. 提交本次 `SSE-BACKFILL-1` 切片。
2. 下一候选切片：Group 重命名/删除 UI，或 Codex bridge task-queue integration。
3. Browser runtime 恢复后，补一次 Web UI SSE 真实浏览器烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\main.py tests\test_sse.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，6 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_sse tests.test_websocket tests.test_messages` passed，39 tests。
- `.venv\Scripts\python.exe -m unittest` passed，88 tests。
- `git diff --check` passed，仅有换行提示。
### Changed Files
- `server/main.py`
- `tests/test_sse.py`
- `docs/spec/MODULE_websocket.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 20:24 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-BATCH-GUARD-1` 已完成：已在全局 `project-framework` skill 与 TALK `AGENTS.md` 中加入连续开发批次刹车规则。
- 决策 Agent 每次恢复默认最多连续推进 2 个明确切片；若都是小型文档/配置切片，可最多 3 个。
- 涉及前端真实交互、数据库/协议、部署/权限或跨模块协作时，默认 1 个切片后暂停汇总。
- 决策 Agent 连续工作约 60-90 分钟后，不应开启新切片，应先完成当前切片的必要验证、汇总进度、提交/推送，并输出下一步建议。
- 软停止信号仅保留两项：后续任务需要重新读取另一个模块文档，或 Agent 明显开始依赖“回忆前文”才能继续判断。
- 若环境提供 5 小时额度或 token 用量占比，仍保留达到或超过 90% 时必须完成当前切片收尾的规则；若环境未暴露精确占比，不臆测百分比。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；后续继续按批次、工作时长、上下文接近上限与两项软停止信号控制连续开发。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测。
### Next Plan
1. 提交并推送全局 `project-framework` skill 更新。
2. 提交并推送 TALK 本地规则与进度更新。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed。
- `git diff --check` in `C:\Users\Administrator\.codex\skills\project-framework` passed，仅有换行提示。
- `git diff --check` in TALK passed，仅有换行提示。
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:26 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-GUARD-1` 已完成：已在 `AGENTS.md` 中补充 Browser 验证失败诊断规则与 token/额度占比收尾规则。
- Browser 失败诊断确认：`node_repl` 可执行，`browser-client.mjs` 可 import，但 `setupAtlasRuntime(...)` 阻塞超时，失败点在 Codex Browser 运行时初始化/后端连接，不是 TALK 页面代码。
- 规则明确：若 `node_repl` 与 import 正常但 Browser runtime 初始化阻塞，应记录限制，改用静态检查、后端测试、必要的临时隔离服务验证，并提示项目管理者从 Codex Desktop / Browser 后端侧恢复后补测。
- token/额度规则明确：若运行环境提供 5 小时额度或 token 用量占比，达到或超过 90% 时不得开启新切片，必须先完成当前切片收尾、汇总进度、提交/推送并输出 `继续项目`。
- 当前工具上下文未暴露 5 小时额度或 token 用量占比，Agent 不应臆测具体百分比，继续沿用上下文 80%-90% 接近上限规则。
### Open Questions / Pending Confirmation
- 需要项目管理者在 Codex Desktop 侧重启/恢复 in-app Browser 或检查 Browser/Chrome 后端后，再补 Web UI 真实浏览器验证。
- 若未来 Codex 暴露精确 token/额度占比，可进一步把该信号纳入自动化提醒或进度模板。
### Next Plan
1. 提交并推送本次流程规则补充切片。
2. Browser 恢复可用后，补 Web UI SSE 兜底真实页面烟测。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `node_repl` 最小执行 `nodeRepl.write("node_repl ok")` passed。
- `browser-client.mjs` import passed，导出 `setupAtlasRuntime`。
- `setupAtlasRuntime(...)` 30 秒超时；使用 `Promise.race` 的 5 秒超时探针也未返回，说明初始化过程阻塞。
- `git diff --check` 待提交前执行。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:04 (Asia/Shanghai)
### Current Progress
- `WEB-SSE-UI-1` 已完成：Web UI 已接入 `GET /api/events?token=...` SSE 事件流作为实时兜底。
- 浏览器优先使用 WebSocket；如果当前浏览器不支持 WebSocket，或 WebSocket 断开/报错，会打开 SSE 并显示 `SSE 已连接 / SSE 兜底中 / SSE 重连中 · 轮询兜底` 状态。
- WebSocket 恢复后会主动关闭 SSE，避免同一浏览器同时占用两条实时通道。
- SSE 与 WS 共用前端实时事件处理逻辑，统一处理 `message / revoke / presence`，`ping` 事件只用于保持连接。
- HTTP 轮询仍保留为断线与事件缺口补漏通道，不承担在线成员状态。
- `docs/spec/MODULE_webui.md` 已同步接口依赖、当前实现、验收标准和本切片 addendum。
### Open Questions / Pending Confirmation
- Codex in-app Browser 插件本轮连接两次超时，未完成真实浏览器前端烟测；临时隔离服务已关闭并清理。
- SSE `Last-Event-ID` replay/backfill 尚未实现；客户端仍需用历史接口和 HTTP 轮询补漏。
### Next Plan
1. 提交并推送本次 Web UI SSE 兜底切片。
2. 下一候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
3. 如浏览器插件恢复可用，补一轮真实 Web UI SSE 兜底烟测。
### Verification
- `node --check web\app.js` passed。
- `git diff --check` passed，仅有换行提示。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，3 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed，10 tests。
- `.venv\Scripts\python.exe -m unittest` passed，85 tests。
- Browser 插件连接两次超时；临时隔离服务已关闭并清理。
### Changed Files
- `web/app.js`
- `web/index.html`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:25 (Asia/Shanghai)
### Current Progress
- `DOC-LANG-1` 已完成：已在 `AGENTS.md` 中加入 TALK 文档语言约定。
- 项目文档中的描述性内容应尽量使用中文。
- 代码标识、API 路径、命令、配置键、协议名、库名、错误码、commit hash 等技术字面量可以保留原始写法。
- 该规则覆盖需求说明、设计说明、进度记录、验收说明、变更摘要和面向人阅读的解释文字。
### Open Questions / Pending Confirmation
- 本规则切片没有新增待确认问题。
### Next Plan
1. 提交并推送本次文档规则切片。
2. 明天用 `继续项目` 恢复。
### Verification
- 本次文档规则更新前，`git status --short` 为空。
- `git diff --check` 已通过，仅有换行提示。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
## 2026-05-15 18:21 (Asia/Shanghai)
### Current Progress
- End-of-day TALK summary completed.
- Confirmed TALK worktree was clean before this summary update.
- Confirmed today's implementation commit `bfb28a3 feat: add group sdk ui and sse events` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed today's workflow/documentation commit `d9a10d5 更新 Agent 协作规则与进度拆分` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed standalone `project-framework` skill repository was updated and pushed at `7756b08 更新项目连续性管理规则`.
- Current recovery instruction for the next session: say `继续项目`.
### Open Questions / Pending Confirmation
- Web UI SSE integration is still the recommended next implementation slice.
- Remaining pending areas: SSE replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, Codex bridge task-queue integration, and environmental deployment/onboarding verification.
### Next Plan
1. Resume tomorrow with `继续项目`.
2. Prefer Web UI SSE fallback/integration unless project priority changes.
### Verification
- `git status --short` was clean before this summary update.
- `git log -3 --oneline` showed `d9a10d5`, `bfb28a3`, and `99578f3`.
- Prior verification for the completed code slice: full `.venv\Scripts\python.exe -m unittest` passed with `85` tests; `node --check web\app.js` passed; `git diff --check` passed with line-ending warnings only.
### Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:02 (Asia/Shanghai)
### Current Progress
- `PROJECT-FRAMEWORK-RULES-1` completed: updated the local `project-framework` skill with the new project-management workflow rules.
- Added role authority rules: `AGENTS.md` is the source of truth; Codex is currently the decision Agent and Claude is currently the execution Agent for TALK.
- Added development cadence rules: decision Agents may continue through multiple clear slices; execution Agents must complete one slice, summarize progress, then wait for confirmation.
- Added required per-slice summary behavior for all Agent roles, plus local git/GitHub submission expectations and Chinese GitHub-facing descriptions.
- Added context handoff/clear flow: summarize, persist, verify, and submit before clearing context or opening a new window; otherwise output `继续项目`.
- Added milestone acceptance gate: pause at independently usable milestones and provide a Chinese acceptance package before continuing.
- Split progress management so `docs/PROGRESS.md` stays short and completed slice history lives in `docs/PROGRESS_HISTORY.md`.
- Synced TALK docs in `AGENTS.md`, `docs/PROJECT_BRIEF.md`, and this progress set.
### Open Questions / Pending Confirmation
- GitHub push/PR behavior is conditional on available remote credentials and should be handled by the active Agent at submission time.
### Next Plan
1. Commit this workflow/documentation slice after verification.
2. Resume implementation from the current candidate list when requested.
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed.
- `git diff --check` passed with line-ending warnings only.
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 历史迁移（来自 PROGRESS.md）

### 2026-05-15 11:04 (Asia/Shanghai)
#### Current Progress
- `SSE-1` completed: added read-only `GET /api/events?token=...` as a Server-Sent Events stream for clients that cannot or should not hold a WebSocket.
- SSE authentication uses the existing API key member resolution path; invalid tokens return `401`.
- The stream emits `presence`, `message`, `revoke`, and idle `ping` events; `message` and `revoke` include SSE `id:` set to the message id.
- `server/ws_hub.py` now fans out realtime updates to both WebSocket connections and per-member SSE queues, drops the oldest queued SSE event when a member queue is full, and counts online members across the WebSocket/SSE union.
- Added live streaming tests for invalid token rejection, presence/message delivery, and revoke delivery.
- Synced `docs/spec/MODULE_websocket.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Web UI has not integrated the new SSE stream yet; this slice only provides the backend event contract.
- SSE `Last-Event-ID` replay/backfill is not implemented; clients should still use message history APIs after reconnect when they need gap recovery.
#### Next Plan
- Continue with one of: Web UI SSE fallback/integration, SSE `Last-Event-ID` replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `85` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `server/main.py`
- `server/ws_hub.py`
- `tests/test_sse.py`
- `tests/test_support.py`
- `docs/spec/MODULE_websocket.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:52 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-MEMBERS-1` completed: active Group Hall now exposes a members panel from the top room strip.
- Human users can add members not yet in the Group, update member roles among `owner / moderator / member`, and remove other members.
- Agent users retain a read-only member list in the UI; server-side permission remains authoritative.
- Successful member changes replace the active Group snapshot and immediately refresh room metadata, scoped presence, and `@` autocomplete.
- Static asset cache-busting updated to `20260515-group-members`.
- Synced `docs/spec/MODULE_webui.md`, `docs/spec/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- Chrome headless smoke test against an isolated temporary TALK server verified login, Group creation, members panel open, member add, role update, member removal, and no horizontal overflow at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:37 (Asia/Shanghai)
#### Current Progress
- `SDK-GROUP-1` completed: async SDK now exposes `create_group`, `list_groups`, `get_group`, `upsert_group_member`, and `remove_group_member`.
- Sync SDK parity added for the same Group helpers; sync `reply()` was also exposed for parity with the async client.
- Message helpers now support Hall scope: `send_text`, `send_file`, `reply`, and `fetch_history` can carry `group_id`.
- Added live SDK coverage that creates a Group, updates/removes a member, sends a Hall message, reads Hall history as an Agent, and verifies the Hall message does not leak into legacy/global history.
- Synced `docs/spec/SDK.md`, `docs/spec/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group member management UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `82` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_talk_client.py`
- `docs/spec/SDK.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:33 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-1` completed: Web UI now exposes a real Group/Hall room strip above the workspace tools.
- Added global timeline / Group Hall switching, `GET /api/groups` loading, active Group persistence per user, and disabled entries for Groups the current user cannot enter.
- Added a lightweight new Group panel with name, optional ID, optional description, and initial member checkboxes; creation succeeds through `POST /api/groups` and automatically enters the new Hall.
- Hall scope now flows through the browser: history and polling include `group_id`, text/file send payloads include `group_id`, WebSocket events are appended only when they belong to the active room, and switching rooms clears reply state.
- Hall UX now scopes online members and `@` autocomplete to the current Group members and uses a placeholder that states Hall mentions are reminders rather than visibility restrictions.
- Synced `docs/PROJECT_BRIEF.md`, `docs/spec/MODULE_webui.md`, `docs/spec/MODULE_groups.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Group member management after creation, Group rename/delete, unread/attention state, SDK helpers, SSE stream integration, and multi-Agent discussion protocol remain future slices.
#### Next Plan
- Commit this Web UI Group/Hall follow-up if accepted.
- Then continue with one of: SDK group helpers, Group member management UI, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- Chrome headless smoke test against an isolated temporary TALK server/database/storage verified login, Group creation with `agent:codex`, Hall message send, Hall-specific placeholder, and that switching back to global hides the Hall message.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- `git diff --check` passed with line-ending warnings only.
- Full `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_webui.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:03 (Asia/Shanghai)
#### Current Progress
- Project role boundary updated: Codex is now authorized as a decision Agent and can maintain relevant project/module/progress/decision docs directly.
- Group/Hall docs synced after `GROUP-1 / HALL-1`: added `docs/spec/MODULE_groups.md`.
- Updated `docs/PROJECT_BRIEF.md` with `groups`, `group_members`, `messages.group_id`, `server/routes/groups.py`, the module index entry, and the 2026-05-14 Group/Hall addendum.
#### Open Questions / Pending Confirmation
- None for documentation sync.
#### Next Plan
- Commit the current Web UI + Group/Hall backend + documentation set when accepted.
- Then choose the next slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 15:54 (Asia/Shanghai)
#### Current Progress
- `GROUP-1 / HALL-1` backend first slice completed from the confirmed contract.
- Added `groups` and `group_members` tables, `messages.group_id`, startup migration/index creation, `/api/groups` creation/list/detail/member add/update/remove APIs, and group-scoped message send/history behavior.
- Group Hall visibility now treats `to_ids` as mention/attention inside a Group: all Group members can read the Hall timeline, while non-members are rejected and old unscoped message history remains legacy/global only.
#### Open Questions / Pending Confirmation
- Documentation sync for `docs/PROJECT_BRIEF.md` and a new/updated Group/Hall module doc still needs explicit approval.
- Web UI Group/Hall navigation and SDK helpers are not implemented yet.
#### Next Plan
- If approved, sync Group/Hall docs and commit the current work.
- Otherwise continue with one follow-up slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_groups` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_messages` passed with `23` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `server/models.py`
- `server/db.py`
- `server/main.py`
- `server/routes/groups.py`
- `server/routes/messages.py`
- `server/ws_hub.py`
- `tests/test_groups.py`
- `tests/test_messages.py`
- `tests/test_support.py`
- `docs/PROGRESS.md`

### 2026-05-14 15:15 (Asia/Shanghai)
#### Current Progress
- Resumed from `WEB-VISUAL-2` and reviewed the current Web UI diff instead of starting a new backend slice.
- Verified the real login page and authenticated chat page with Chrome headless at desktop and 500px widths.
- Fixed a CSS cascade bug where `.drop-hint` overrode Tailwind `.hidden`, causing the drag/drop overlay to stay visible over the composer when no file was being dragged.
#### Open Questions / Pending Confirmation
- `docs/USER.md` remains an untracked local credential note; it should not be committed as-is.
#### Next Plan
- Decide how to handle `docs/USER.md`, then commit the accepted Web UI visual changes.
- After Web UI is committed, choose the next backend/product slice: schedule API, Group/Hall, SSE, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- Chrome headless screenshots verified real login and authenticated chat pages; `#drop-hint` computed as `display: none` at 1440px and 500px.
#### Changed Files
- `web/style.css`
- `docs/PROGRESS.md`

### 2026-05-14 11:35 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-2` completed from the approved `image_gen` visual direction: the chat page now uses a `header + workspace-tools + messages + composer` structure.
- Online members and history/search controls are grouped into one workspace tools panel; the message timeline and composer now read as a single chat work area.
- The left channel/conversation area shown in the visual mockup remains deferred until the Group/Hall model exists, so the current page does not expose fake navigation.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page acceptance still depends on manual review in the user's browser session or a dedicated non-private test account.
#### Next Plan
- If the layout is accepted, commit the Web UI visual changes; then return to backend model work, likely Group/Hall or SSE, so future navigation/sidebar UI has real data behind it.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/` returned `200`.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 11:10 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-1` completed: login/setup now uses a unified dark card treatment with Chinese copy, branded mark, clearer fields, and primary/secondary button hierarchy.
- Chat workspace styling was refreshed across header, presence strip, search toolbar, timeline background, message bubbles, reply/file cards, and bottom composer.
- Added responsive safeguards for narrow screens: constrained auth card width, wrapping toolbar controls, composer min-width fixes, and stronger long-message wrapping.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page visual acceptance still depends on manual review or a provided non-private test login key; Codex in-app browser automation continues to time out when connecting.
#### Next Plan
- Review the visual result in a normal browser session; if accepted, commit and push `WEB-VISUAL-1`.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview using the current served `style.css`.
- Codex in-app browser automation retry still timed out while connecting.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:55 (Asia/Shanghai)
#### Current Progress
- Re-ran full backend regression after the Web UI polish changes; all `74` unit tests passed.
- Confirmed the local TALK service health endpoint still returns `status=ok`.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on browser/manual review; automated in-app browser control was previously timing out in this environment.
#### Next Plan
- Commit and push the Web UI polish changes if the current UI review scope is accepted.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/healthz` returned `status=ok`.
- In-app browser automation retry against `http://127.0.0.1:8000/` timed out while connecting.
#### Changed Files
- `docs/PROGRESS.md`

### 2026-05-14 10:49 (Asia/Shanghai)
#### Current Progress
- `CHAT-UI-1` completed from browser review comments: search toolbar, composer controls, drag/drop hint, logout, remove-file, cancel-reply, and send/file labels are now Chinese.
- Search toolbar now separates primary search from secondary clear/load-more actions; composer now has a defined container and distinct file/input/send controls.
- Empty message timeline now shows a Chinese empty-state explanation instead of a visually unexplained blank area.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on manual refresh because Codex in-app browser automation is still timing out when connecting to the browser runtime.
#### Next Plan
- If the chat UI review is accepted, commit and push the Web UI polish changes.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:15 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` follow-up completed: added cache-busting query strings for `/style.css` and `/app.js`, placed the create-admin button contrast styles directly in HTML classes, and replaced raw Clipboard API permission errors with Chinese copy-fallback guidance.
- If browser copy permission is denied, the setup key field is focused and selected so the user can press `Ctrl+C` manually.
#### Open Questions / Pending Confirmation
- Whether to replace the current API-key-first login model with a human password flow is a product/auth decision. Recommended direction is dual-mode auth: human password login with hashed password plus generated API keys for Agent/SDK use.
#### Next Plan
- If approved, design `AUTH-2`: password-based human login without breaking existing `X-API-Key` Agent authentication.
#### Verification
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:01 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` completed from browser diff comments: added a visible `管理员 ID` format hint, changed `显示名称` to `昵称`, added client-side `human:*` validation, and restyled `创建管理员` as a compact bordered primary button.
- Synced `docs/spec/MODULE_webui.md` to reflect the updated first-admin setup labels and ID-format hint.
#### Open Questions / Pending Confirmation
- In-app browser automation currently times out while connecting to the browser runtime, so the page needs a manual refresh or later browser recheck for visual confirmation.
#### Next Plan
- Continue with the next local-lab slice after UI review is accepted: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `GET http://127.0.0.1:8000/` returned `200`.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-13 16:07 (Asia/Shanghai)
#### Current Progress
- `TASK-1` completed: added `AgentTask` / `AgentTaskCreate` / `AgentTaskClaim` / `AgentTaskComplete` / `AgentTaskOut`, `/api/tasks`, database indexes, async SDK helpers, sync SDK wrappers, and documentation.
- Task API first slice supports creating queued tasks for existing `agent:*` members, listing visible tasks, Agent-only claim, and Agent-only completion as `succeeded` / `failed` / `canceled`.
- Task claim and completion now update linked `AgentInstance`: claim sets `busy` and `current_task_id`; success/cancel returns to `idle`; failure sets `error` and `last_error`.
- Project rule updated in `AGENTS.md`: development execution Agents may directly update `docs/PROGRESS.md` after actual code, test, or documentation work.
- Documentation synced across project brief, SDK, local-lab design, instances module, and new tasks module.
#### Open Questions / Pending Confirmation
- Schedule API is still not implemented: delayed / recurring trigger shape remains open.
- Retry, task timeout recovery, stale `running` cleanup, requeue/cancel UI, and Codex bridge task-queue consumption remain future work.
#### Next Plan
- Choose the next local-lab slice: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
- If continuing scheduler work, define whether schedules create one-off tasks at trigger time and how failed scheduled tasks should be retried or surfaced.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_tasks` passed with `7` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client.TalkClientTests.test_task_helpers` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
#### Changed Files
- `AGENTS.md`
- `server/models.py`
- `server/routes/tasks.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_instances.md`
- `docs/spec/MODULE_tasks.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/spec/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:47 (Asia/Shanghai)
#### Current Progress
- `INSTANCE-1` completed: added `AgentInstance` / `AgentInstanceUpdate` / `AgentInstanceOut`, `/api/instances`, database indexes, SDK helpers, and module documentation.
- Codex bridge now reports its runtime instance state with a stable optional `--instance-id`; task handling updates status to `busy`, success returns to `idle`, failures become `error`, and shutdown reports `offline`.
- Added coverage for instance API permissions, ownership protection, filters, invalid status validation, and SDK helpers.
#### Open Questions / Pending Confirmation
- Task and schedule API semantics are still not implemented: task table shape, retry behavior, process ownership, and scheduler/bridge responsibility split remain open.
- Group / Hall / SSE / document-lock implementation details remain pending after this instance-status foundation.
#### Next Plan
- Choose the next local-lab slice: scheduler task API, Group/Hall room model, SSE stream contract, or document-edit lock API.
- When scheduler work starts, decide whether TALK launches bridge processes or only routes tasks to already-running instances.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_instances tests.test_talk_client tests.test_codex_bridge` passed with `19` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `66` tests.
- Isolated bridge instance smoke passed: `idle -> busy -> idle -> offline`, reply content `TALK_BRIDGE_INSTANCE_SMOKE_OK`.
#### Changed Files
- `server/models.py`
- `server/routes/instances.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `bridges/codex_bridge.py`
- `tests/test_instances.py`
- `tests/test_talk_client.py`
- `docs/spec/MODULE_instances.md`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:24 (Asia/Shanghai)
#### Current Progress
- Created an ignored local `.venv` from `requirements.txt`; dependency imports resolved consistently there (`pydantic 2.13.4`, `pydantic-core 2.46.4`, `fastapi 0.136.1`, `websockets 15.0.1`).
- Full regression passed: `.venv\Scripts\python.exe -m unittest` ran `60` tests successfully.
- Real Codex bridge smoke test passed with isolated temporary TALK server/database/storage: `human:smoke` sent `@agent:codex`, the bridge invoked real `codex exec --sandbox read-only`, and the reply used `reply_to` with content `TALK_BRIDGE_SMOKE_OK`.
#### Open Questions / Pending Confirmation
- Codex bridge remains MVP-level and still needs instance status, streaming, file/material handling, and document-lock integration.
- The `pi` framework path for DeepSeek / Kimi still needs local verification.
#### Next Plan
- Choose the next implementation slice: bridge instance status, Group/Hall model, SSE streaming contract, or document-edit lock API.
- Continue the local-lab protocol design before broad service-model changes.

### 2026-05-13 15:10 (Asia/Shanghai)
#### Current Progress
- Added `docs/spec/LOCAL_LAB_DESIGN.md` as the thin local-lab design note.
- Added `bridges/codex_bridge.py` as the Codex bridge MVP: direct text message in, configurable `codex exec` invocation, `reply_to` answer out.
- Added `docs/spec/MODULE_bridges.md` and updated `docs/PROJECT_BRIEF.md` to register the new bridge module.
- Added `tests/test_codex_bridge.py` covering bridge routing, prompt construction, reply formatting, and subprocess stdin piping.
#### Open Questions / Pending Confirmation
- Real TALK server smoke test for Codex bridge remains pending.
- Full test suite is blocked by the local `.codex_pydeps` pydantic / pydantic-core mismatch.
#### Next Plan
- Clean or rebuild the Python dependency environment, then run full tests.
- Start TALK locally, run the Codex bridge, and verify one `@agent:codex` browser-to-bridge-to-reply loop.
- After the smoke test, continue with Group / Hall / SSE / instance-scheduler design and implementation.

### 2026-05-12 17:36 (Asia/Shanghai)
#### Current Progress
- Product decisions confirmed: DeepSeek / Kimi will use the locally installed `pi` framework; TALK should add Groups, Hall shared timeline mode, SSE streaming, and instance/scheduling API layers.
- A document editing coordination protocol is now required so multiple Agents do not edit the same document at the same time.
- Existing communication specs were checked. Current TALK supports member identity, API-key auth, server-side leading-mention routing, broadcast/direct/group-style `to_ids`, REST polling, WebSocket events, file exchange, replies, and SDK callbacks, but not a formal discussion protocol or document lock protocol.
- Temporary role decision: until the next progress summary, Codex may act as both decision Agent and execution Agent because the dedicated decision Agent is unavailable.
#### Open Questions / Pending Confirmation
- Document editing coordination still needs exact rules for lock scope, timeout, stale-lock recovery, conflict handling, and UI/API visibility.
- The local `pi` framework needs a quick workstation-level verification before bridge implementation.
#### Next Plan
- Write the next-phase local-lab design note covering bridge layout, `pi` integration, Groups, Hall, SSE, instance/scheduler APIs, and document-edit coordination.
- Define the first moderator-led multi-Agent discussion protocol before implementation.
- Implement the minimum local-lab path after the protocol and data model changes are stable.

### 2026-04-24 23:11 (Asia/Shanghai)
#### Current Progress
- `DOC-2` completed: fixed the remaining mojibake deployment section in `CLAUDE.md`, added explicit UTF-8 write rules plus SDK import-path notes to `AGENTS.md` / `CLAUDE.md`, and added `tests/test_encoding.py` as an encoding regression guard.
- Full regression still passes with `54` tests, including `3` new encoding-guard cases.
- The intended usage model is now explicit: TALK is a local home-LAN multi-Agent lab used on demand while the local computer is on, not a 24/7 permanently running service.
- The planned backend mix is now explicit: `Claude Code` / `Codex` through local CLI bridges, and `Kimi` / `DeepSeek` through API bridges.
- The next product direction is now explicit: moderator-led AI discussion with automatic transcript retention and support for passing shared documents/materials during the discussion.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The discussion phase still needs a concrete protocol for moderator behavior, round limits, material-sharing rules, and summary output.
#### Next Plan
- Write the next-phase design note for local experimental mode and one-command startup.
- Define a unified bridge contract for mixed CLI/API Agent backends.
- Define the first moderator-led discussion protocol with transcript retention, bounded rounds, and material passing.
- Implement the minimum local-lab path first, then return to lower-priority deployment validation tasks.

### 2026-04-24 22:01 (Asia/Shanghai)
#### Current Progress
- `DOC-1` completed: split onboarding into `docs/guides/QUICKSTART_USER.md` and `docs/guides/QUICKSTART_AGENT.md`, and reduced `docs/guides/QUICKSTART.md` to a short index page.
- `QUICKSTART_USER` now follows a family-user path with Docker Desktop, explicit browser verification, `config.toml` before/after examples, LAN IP lookup, and ordered troubleshooting.
- `QUICKSTART_AGENT` now follows a Python bare-metal + SDK path with PowerShell/bash command pairs, real example repo URLs, and a full runnable Agent sample.
- `docs/guides/DEPLOY.md` now includes prerequisites for Docker Compose, Linux `systemd`, and bare metal deployment.
- `docs/spec/SDK.md` async examples now all include `asyncio.run(main())`, and `SETUP-1` now supports browser-side key generation, reveal/hide, and one-click copy in the first-admin UI.
- Related docs were synced after implementation, and full regression still passes with `51` unit tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The task card asks for a second clean-session newcomer dry run and readability feedback; that external acceptance has not been performed yet in this environment.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, generated key, automatic sign-in, and second-open login behavior match the task card.
- Run one clean-session newcomer walkthrough against `docs/guides/QUICKSTART_USER.md`, collect friction points, and trim any remaining expert assumptions.

### 2026-04-24 19:25 (Asia/Shanghai)
#### Current Progress
- `SETUP-1` completed: added unauthenticated `GET /api/setup/status`, CLI bootstrap script `scripts/create_admin.py`, Web UI first-run admin creation flow, and setup coverage in `tests/test_setup.py`.
- `QUICKSTART` and `DEPLOY` now document first-run bootstrap via the Web UI and `python scripts/create_admin.py`, including the Docker path `docker compose exec talk python scripts/create_admin.py`.
- The old onboarding blocker is removed at the code level: first human account creation no longer requires opening `/docs` and manually calling `POST /api/members`.
- Regression coverage expanded again; full `python -m unittest` is now green with `51` tests, including `3` new setup-specific cases.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- The new first-run setup flow has test coverage, but a real browser smoke test for “empty DB -> create admin -> auto login -> reopen -> normal login form” is still pending.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, automatic sign-in, and second-open login behavior match the task card.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:39 (Asia/Shanghai)
#### Current Progress
- `SDK-1` completed: added `TALK/client/` with async `TalkClient`, sync `TalkClientSync`, HTTP exception mapping, WebSocket-first event flow, reconnect plus HTTP polling fallback, message dedupe, and SDK docs/demo.
- `MSG-4` completed: added first-level message reply support across database, REST, WebSocket, Web UI, and SDK; reply summaries now travel with history and live events.
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/talk.service`, `README.md`, `docs/guides/QUICKSTART.md`, and `docs/guides/DEPLOY.md` for Docker, systemd, and bare-metal deployment paths.
- `SEC-1` completed: `GET /api/messages` now enforces visibility in SQL, aligns with WebSocket delivery semantics, and treats `to` as a narrowing filter rather than an access-control boundary.
- Regression coverage expanded across SDK and message flows; full `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:38 (Asia/Shanghai)
#### Current Progress
- `SEC-1` completed: `GET /api/messages` now enforces message visibility in SQL and matches WebSocket delivery semantics instead of trusting the caller's `to` filter.
- `to=<member_id>` is now only a narrowing filter on the caller's visible set; `to=<other_member>` returns a safe pair view without exposing third-party private messages.
- Added regression coverage in `tests/test_messages.py` for third-party private message isolation, `to` filter escape attempts, broadcast visibility, pair-view filtering, and search visibility boundaries.
- Added startup indexes for `messages.from_id` and `messages.to_ids`, and updated `docs/spec/MODULE_messages.md`, `docs/PROJECT_BRIEF.md`, and `docs/spec/SDK.md` to document the new server-enforced visibility contract.
- Full regression check passed: `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:59 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/guides/QUICKSTART.md` for first install/login/use, and `docs/guides/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- Outside `DEPLOY-1`, one known product-side gap remains: `GET /api/messages` history visibility still relies on the caller using the expected `to=<member_id>` view and is not yet fully tightened to WebSocket-level visibility semantics.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:57 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/guides/QUICKSTART.md` for first install/login/use, and `docs/guides/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:48 (Asia/Shanghai)
#### Current Progress
- `MSG-4` completed: backend now supports first-level message replies via `messages.reply_to`, server-side validation, REST history reply summaries, and WebSocket payload parity.
- Web UI now supports reply composition, inline reply strips, jump-to-origin highlight, revoked-origin placeholder handling, and runtime config loading from public `GET /api/config`.
- `SDK-1` follow-up completed: `TALK/client/talk_client.py` now supports `reply_to` and `client.reply(message_id, text=...)`.
- Docs updated for `MODULE_messages`, `MODULE_webui`, and `PROJECT_BRIEF` addenda covering reply semantics and `/api/config`.
- Automated verification passed: `python -m unittest` is green with `43` total tests, including new reply/config coverage in `tests/test_messages.py` and the SDK reply shortcut test.
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- Confirm the next product card after `MSG-4`; current reply support is intentionally flat and does not attempt nested thread rendering.
- If the next task stays in messaging, the highest-risk follow-up is tightening history visibility filtering in `GET /api/messages` so HTTP history matches WebSocket visibility more strictly.
- If manual UX acceptance is required, run the local browser flow for reply creation, jump-to-origin, revoke-after-reply, and `/api/config`-driven upload limit behavior.

### 2026-04-23 19:25 (Asia/Shanghai)
#### Current Progress
- `SDK-1` ?????????? `TALK/client/`????? `TalkClient`?????? `TalkClientSync`?????? `register/send_text/send_file/revoke/download_file/me/list_members/fetch_history/run` ??????
- SDK ??????? WebSocket ?????JSON `ping/pong` ??????????????? HTTP `since` ??????????? N ? `message.id` ???????? WS `from_field` ? REST `from` ?????
- ?? `examples/agent_sdk_demo.py`?????? `24` ????????? `agent:<name>`????? `ping` ??????? `pong`?????????? Agent??
- ?? `docs/spec/SDK.md` ?? SDK API ?????? `docs/spec/MODULE_agent_example.md` ?? SDK ?????`server/routes/files.py` ?? `HTTP_413_REQUEST_ENTITY_TOO_LARGE` ?? `HTTP_413_CONTENT_TOO_LARGE`?
- ?? `tests/test_talk_client.py` ? 6 ? `unittest` ???????/?????????????WS ????????????????? handler????????????? `36` ? `unittest`?`python -m unittest` ???
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- ?????????? SDK ?????????????? `reply_to` / ?????????????????????????????
- ?????? Agent ????????????????????????????????? Agent ???????/?????
- ???????????????????????? `docs/PROGRESS.md`????????????????

### 2026-04-22 23:29 (Asia/Shanghai)
#### Current Progress
- `WS-1` 已完成：WebSocket 心跳 `ping/pong`、空闲超时断开、入站 `send`、WS/REST 共用消息创建链路与鉴权重构均已落地。
- `FILE-1` 已完成：文件上传接入 `sha256` 秒传去重，采用 A 方案保留多条记录共享实体路径，并修正共享实体的过期清理逻辑。
- `OPS-1` 已完成：新增 `/healthz`、结构化日志、在线热备脚本、日志/备份配置段与运维文档，手动验收与自动化测试均通过。
- `MSG-3` 已完成：支持消息撤回、撤回态历史回放、WS `revoke` 实时同步、Web UI 撤回按钮与撤回占位渲染，文件消息撤回后实体保留。
- 当前全量自动化测试共 `30` 个 `unittest` 用例，`python -m unittest` 已全绿。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进下一个已确认任务卡，优先选择新的业务能力点，而不是重复打磨已通过验收的模块。
- 低优先清理两个工程尾项：`413` 弃用告警，以及前端撤回窗口时长与后端配置的统一读取方式。
- 保持后续任务的代码、模块文档与 `docs/PROGRESS.md` 同步更新。

### 2026-04-22 22:06 (Asia/Shanghai)
#### Current Progress
- 在现有 `tests/` 骨架上继续扩完 `M3-4`：新增 `tests/test_websocket.py` 4 个 `unittest` 用例，覆盖无效 token 拒绝、首次 presence 快照、上下线 presence 变更、实时消息推送、`since` 对齐去重，以及断线后通过 HTTP `since` 补历史。
- 扩充 `tests/test_files.py` 4 个上传链路用例，覆盖成功上传落盘/落库、上传鉴权拒绝、超限文件拒绝、上传后 `type=file` 消息对 `filename / size_bytes / mime` 的快照冻结。
- 为了让基于 FastAPI `TestClient` 的自动化测试可直接运行，`requirements.txt` 已补入 `httpx>=0.27,<1`。
- 测试基类已补应用注入与隔离能力：`tests/test_support.py` 现在会把临时 SQLite 引擎注入 `server.main`，并在每个用例前后清空 `hub` 连接状态，避免 WS 单测串扰。
- 已同步更新 `docs/spec/MODULE_websocket.md` 与 `docs/spec/MODULE_files.md` 的当前实现现状和验收标准，反映本轮新增自动化覆盖。
- 当前全量自动化测试为 `15` 个 `unittest` 用例，已通过 `python -m unittest` 全量验证。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 如继续补 `M3-4`，优先补 WebSocket 广播路径与“同一成员多连接”场景，补齐 `MODULE_websocket` 里仍未打勾的验收项。
- 低优先处理进度文档收口：按既定建议评估是否把 `docs/PROGRESS.md` 的历史段进一步收敛到双文件结构。
- 后续每完成一项功能，继续同步对应模块文档与 `docs/PROGRESS.md`，避免进度积压。

### 2026-04-21 23:29 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
- 今日开发先收口到这里；相关模块文档与项目简报已对齐到当前状态，包含 `tests/` 测试骨架与已覆盖的后端行为范围。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:08 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:00 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 第二批核心功能已收口，下一步优先切到第三批里的 `M3-4` 单元测试，把这轮成员注册、消息分页/搜索、文件过期行为收敛成可重复执行的自动化测试。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 22:14 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进第二批剩余项，优先做 `MEM-1` 真实链路手工验收，确认 Agent 首次注册、重复启动和冲突 key 行为都符合预期。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 21:52 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在 `MSG-2` 基础上继续实现 `MSG-1` 消息搜索，并优先复用现有消息列表渲染与分页交互。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 21:48 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 按既定路线进入第二批，优先实现 `MSG-2` 历史分页，再评估与 `MSG-1` 消息搜索的接口复用。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 19:58 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
#### Open Questions / Pending Confirmation
- 文件生命周期策略尚未确定：当前实现会长期保留 `files` 表记录和 `storage/files/<file_id>` 实体；如引入删除/清理，需要先确认“历史文件消息是否必须永久可下载”以及删除后的预期行为。
#### Next Plan
- 等待项目管理者确认文件生命周期策略，优先建议先明确“已被消息引用的文件是否永久保留”这一条基线规则。
- 策略确认后，按决策实现对应的文件保留/清理方案，并补充 API/前端在文件缺失场景下的用户可见行为。
- 在本轮已确认改动稳定后，同步更新 `docs/spec/MODULE_messages.md`、`docs/spec/MODULE_webui.md` 与 `docs/spec/MODULE_files.md` 的实现状态描述。

### 2026-04-14 00:12 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 接收者表达已统一为 `@mention` 模式：文本正文与文件附言都只解析“消息开头连续 mention 块”作为接收者；无开头 mention 时按广播处理；无效 mention 会在发送前红色提示并阻止发送。
- 相关文档已同步到当前实现：`AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_members_auth.md`、`docs/spec/MODULE_messages.md`、`docs/spec/MODULE_files.md`、`docs/spec/MODULE_webui.md`、`docs/spec/MODULE_agent_example.md`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 评估是否将当前“前端解析开头 mention 后写入 `to`”的规则下沉到后端，收敛为服务端统一解析逻辑，避免不同客户端各自实现一套。
- 继续处理 Web UI 可用性问题，优先考虑消息列表性能（虚拟滚动/分页）和文件生命周期策略（删除/清理）。
- 如需继续完善文档，补齐 `MODULE_files.md` 以外的状态细节，并在后续每轮确认后的实现落地后同步更新。

### 2026-04-13 00:00 (Asia/Shanghai)
#### Current Progress
- M2 核心能力已基本落地：文件上传下载 API、Web UI 文件收发、示例 Agent 文件收发已完成。
- 文件 API、静态资源路由和示例 Agent 的基础链路已在隔离环境中验证通过。
- 浏览器端 Web UI 仍待整链路手动验收。

#### Open Questions / Pending Confirmation
- 下一步优先做 `/api/me` 还是继续细化 Web UI。
- 是否安装 auto-resume hook 到 `~/.claude/settings.json`。

#### Next Plan
- 先完成浏览器端整链路验收，再决定 `/api/me` 与 Web UI 细化的优先级。

## 2026-04-12

**完成**

- **M1 MVP 代码全部落地并通过 API 端到端验证**：按 [§9 目录结构](spec/PRODUCT.md) 创建 `server/`、`web/`、`examples/` 完整代码骨架
- `server/models.py`：SQLModel 定义 members/messages/files 三张表 + Pydantic 请求/响应 schemas，`from` 关键字用 `Field(alias="from")` 解决
- `server/db.py`：用 `tomllib` 读取 `config.toml`，创建 SQLite engine（WAL 模式），提供 `get_session` 依赖
- `server/auth.py`：`X-API-Key` header → Member 查表鉴权依赖
- `server/ws_hub.py`：单例 Hub 维护 member_id → WebSocket 连接池，按 to_ids 精准推送或全量广播
- `server/routes/members.py`：POST 注册（自动推导 kind + 唯一性校验）、GET 列表
- `server/routes/messages.py`：POST 发消息（落库 + WS 广播）、GET 拉消息（since 游标 + to 过滤 + limit）
- `server/main.py`：FastAPI lifespan 初始化 DB，挂载 REST 路由 + WS 端点 + StaticFiles
- `web/`：暗色主题单页 UI（Tailwind CDN），含 @ 自动补全下拉框、WS 实时接收 + HTTP 轮询 3s 降级双通道、localStorage 保存登录态
- `examples/agent_poller.py`：纯 stdlib（无第三方依赖）Agent 脚本，自动注册 → 轮询 → 回声应答
- `config.toml` + `requirements.txt` + `run.sh` 基础设施
- **API 端到端验证通过**：注册 human:bobo + agent:AI1 + agent:AI2 → 定向消息 + 广播消息 → AI1 拉到所有消息 / AI2 只拉到广播 → TestBot Agent 自动注册+轮询+回复 → 中文 UTF-8 存储正确 → OpenAPI `/docs` 200 OK
- **建立全局项目文档结构规范**：创建 `~/.claude/CLAUDE.md`（文档结构标准 + MODULE 统一模板 + 模块拆分原则 + Agent 路由规则）
- **TALK 项目文档重构为 "1+N" 结构**：
  - `talk.md` → `docs/spec/PRODUCT.md`（PM 完整产品文档，位置标准化）
  - 新建 `CLAUDE.md`（项目级路由入口，指引 agent 先读 PROJECT_BRIEF 再读对应 MODULE）
  - 新建 `docs/PROJECT_BRIEF.md`（~100 行公共上下文：架构图 + 技术栈 + 数据模型 + 模块索引表）
  - 新建 6 份 MODULE spec：`MODULE_members_auth` / `MODULE_messages` / `MODULE_websocket` / `MODULE_files` / `MODULE_webui` / `MODULE_agent_example`，每份含目标、范围、接口契约、约束、现状、待改进、验收标准
- **改进 progress skill**：触发词增加"继续项目"，§3.4 强化为必须用 AskUserQuestion 等待用户指示才能行动
- **清理记忆文件**：删除已过期的 `project_sql_exam.md`，更新 `user_sql_background.md` 去除考试上下文
- 为 TALK 补充**部署拓扑**章节 [§4.1](spec/PRODUCT.md)：画出"拓扑 A 同机多 Agent"和"拓扑 B 跨机多 Agent"两张 ASCII 图，明确从 A 切到 B 只需 3 处配置修改（`host` / 防火墙 / Agent base_url），**零代码改动**
- 新增 [§5.1 关键配置项](spec/PRODUCT.md)：`config.toml` 的 6 个字段（`host / port / public_url / upload_max_mb / storage_dir / db_path`）及默认值，并在备注里留下"默认 `127.0.0.1` 的安全理由"
- [§12 验证步骤](spec/PRODUCT.md) 补了第 9 步：跨机部署端到端验证流程
- Plan 文件与 [TALK/talk.md](spec/PRODUCT.md) 双份同步，保持两份文档内容一致
- 创建并落地 `project-progress` skill：[SKILL.md](C:\Users\bobo\.claude\skills\progress\SKILL.md) 211 行，含两种操作分发（summarize/resume）、三源素材采集、同日合并、首次初始化、计划自动迁移、历史归档、auto-resume hook 文档化
- 首次运行本 skill 并生成本进度文件 `docs/PROGRESS.md`
- **改进 skill 项目根裁定逻辑**（SKILL.md 从 211 行 → 256 行）：把原本 "git → cwd" 的 2 级回退换成 **5 级 Tier 算法**：Tier1 git 根 → Tier2 IDE 打开文件的最近项目祖先 → Tier3 cwd 自带项目标记 → Tier4 cwd 是多项目父目录时 AskUserQuestion 让用户选 → Tier5 回退 cwd 并显式警告。定义统一的 8 种"项目标记"（`.git/` / README / package.json / pyproject.toml / Cargo.toml / go.mod / requirements.txt / **已存在的 `docs/PROGRESS.md`**）。新增 §1.3 透明度约束，要求 Tier 2/3 命中时在输出开头标注来源，Tier 4 必须询问，Tier 5 必须警告
- **M2 文件上传下载 API 完成**：`server/routes/files.py` 实现 `POST /api/files` 与 `GET /api/files/{file_id}`，支持鉴权、sha256、`upload_max_mb` 限流、磁盘落盘、404 与超限处理；`server/models.py` 新增 `FileOut`
- **M2 Web UI 文件收发完成**：`web/` 补齐文件按钮、拖拽上传、待发送文件面板、文件消息气泡与下载按钮；前端发送 `type=file` 消息时将 `content` 固定写为文件名
- **M2 示例 Agent 文件收发完成**：`examples/agent_poller.py` 支持 `--send-file` + `--send-to` 启动参数发送文件，并在收到文件消息后下载到 `examples/downloads/<agent_name>/`
- **今日验证完成**：文件 API 在隔离环境下通过上传/下载/404/超限验证；示例 Agent 在临时本地服务中通过文件发送与下载验证；前端静态资源路由可正常访问

**决策**

- Server 默认 `host = 127.0.0.1`：安全优先。开箱即用只允许本机访问；用户显式改 `0.0.0.0` 时自然会意识到需要同步加固防火墙和 API Key
- 不自动修改 `~/.claude/settings.json` 安装 auto-resume hook：settings 是共享配置，改动风险高，按工作习惯先确认再动
- skill 的进度文件统一放 `<项目根>/docs/PROGRESS.md`（非项目根下），归档文件同目录的 `PROGRESS_archive.md`
- 项目根裁定规则（未来需要改进 skill）：当前 cwd 是多项目的父目录时，`git rev-parse` + cwd 回退不够用，应额外参考 IDE 打开文件的最近项目祖先
- Python `from` 关键字冲突：MessageOut 模型用 `Field(alias="from", serialization_alias="from")` + `populate_by_name=True` 解决，API 输出保持 `"from"` 不带下划线
- `POST /api/members` 不要求鉴权（注册是引导流程，无先有 key 的鸡蛋问题）；`GET /api/members` 暂不鉴权（供 UI @ 补全用，M3 再收紧）
- `examples/agent_poller.py` 纯 stdlib 实现（urllib.request + json），零第三方依赖，便于任意环境即跑
- Web UI 采用 WS 实时 + HTTP 轮询 3s 双通道降级策略：WS 断开后自动靠轮询兜底
- 文档结构采用 "1+N" 模式：全局规范放 `~/.claude/CLAUDE.md`，项目路由放项目根 `CLAUDE.md`，agent 只读 PROJECT_BRIEF + 自己的 MODULE
- CLAUDE.md vs Skill 边界：规则/标准放 CLAUDE.md（自动加载），复杂流程放 Skill（触发执行）
- Claude 角色定位为项目管理者/产品经理，代码开发分配给其他 agent
- `type=file` 消息的 `content` 字段用于保存文件名，供 Web UI 与 Agent 接收端直接展示；本阶段不支持"文件 + 额外文字附言"同发

## 2026-04-11

**完成**

- 确定 TALK 项目方向：家庭局域网内的 AI Agent 聊天中转平台，支持 Agent ↔ Agent 和 人 ↔ Agent 通过 `@` 定向交互
- 通过 4 轮关键决策问答冻结技术栈：**Python + FastAPI** / **SQLite 全部持久化** / **HTTP 轮询 + WebSocket 可选** / **X-API-Key 鉴权**
- 撰写产品文档初版 [talk.md](spec/PRODUCT.md)，覆盖 13 个章节：产品背景、角色场景、F1–F4 功能需求、系统架构、技术选型、数据模型（含 SQL schema）、API 设计（REST + WebSocket）、关键流程（轮询/发消息/文件传输）、项目目录结构、非功能需求、M1/M2/M3 里程碑、端到端验证、待定议题
- Plan 文件 [prancy-soaring-eagle.md](C:\Users\bobo\.claude\plans\prancy-soaring-eagle.md) 完成并经用户批准
- 调研确认无任何既有 skill 可响应"汇总今日进度/继续开发"关键词
- 设计并通过 3 轮 AskUserQuestion 敲定 `project-progress` skill 方案：
  - 进度文件位置：`<项目根>/docs/PROGRESS.md`
  - 素材来源：git + 对话上下文 + `.claude/plans/` 三源融合
  - 默认内置：同日去重合并、首次自动初始化、文件头元信息
  - 已选增强：plan 文件联动、后续计划自动迁移、历史 >30 归档、auto-resume hook（文档化）
- 建立 [C:\Users\bobo\.claude\skills\project-progress\](C:\Users\bobo\.claude\skills\project-progress\) 目录

**决策**

- TALK 的 MVP 范围排除：公网部署、E2E 加密、多房间、消息撤回、Agent 自身 LLM 能力
- SQLite 够用，不上 PostgreSQL —— 家庭局域网单机场景零运维优先
- 前端不引入构建链（无 Vue/React/Vite），Vanilla JS + Tailwind CDN 即可
- 消息 `to_ids` 用 JSON 数组 + `NULL` 表广播的单表设计，避免引入额外 mention 关联表
- `id` 单调递增兼做 `since` 游标，实现 Agent 至少一次送达、不丢不重
