# 开发历史 · TALK

<!--
项目根：d:\claude-test\TALK
最后更新：2026-06-02 5.x agent-to-agent 通信主线关闭（黑盒复测通过）

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
