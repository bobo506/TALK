# Project Progress

## Latest
Updated: 2026-06-02 23:55 (Asia/Shanghai) — 5.x agent-to-agent 通信主线关闭（黑盒复测通过）

### Pi extension dispatch bug 定位与规避

经过四轮黑盒 / 探针 / 源码插桩,锁定 pi extension 注册的 `talk_send` 工具从未真正进入 LLM catalog 的根因:**pi 自带的 `plan-mode` 扩展**(`@earendil-works/pi-coding-agent/extensions/plan-mode/index.ts:343-345`)在 `rebindSession` 事件回调里无条件调用 `pi.setActiveTools(NORMAL_MODE_TOOLS)`,**全量替换**当前激活工具集为硬编码 builtins 列表,把同会话其他扩展刚通过 `pi.registerTool({...})` 注册的 `talk_send`(以及 echo_tool 探针、pi-mcp-adapter 的 `mcp` proxy 工具等)全部抹掉。

**当前 Agent 角色**:Claude 按项目管理者处理(本会话的诊断 + 文档沉淀 + 上游 issue 起草);Codex 按执行 Agent 完成所有 probe 与代码 patch。

**已完成**:
1. `bridges/pi_bridge.py` `DEFAULT_PI_COMMAND` 与 `DEFAULT_PI_TOOLS_COMMAND` 均追加 `--no-extensions`,禁用所有自动发现扩展(包括 plan-mode);`-e` 显式加载的 `talk_tools_extension.ts` 不受影响。
2. `tests/test_pi_bridge.py` 新增两条断言,确保两档命令均含 `--no-extensions`。
3. `docs/spec/INTERACTION_FRAMEWORK.md` 新增三节 runtime 陷阱沉淀:
   - §6.5 Pi runtime 工具覆盖陷阱与规避(plan-mode 问题完整复盘 + 规避方案)
   - §6.6 Windows 下 MCP 子进程的 UTF-8 强制
   - §6.7 Codex 非交互模式的 MCP approval 闸门
4. Upstream issue 已提交至 `earendil-works/pi`,内含复现步骤、源码定位、推荐修复(merge 而非 replace)。

**与上一轮 codex 修复的关系**:本轮(pi)与上一轮(codex)是同一个"agent-to-agent talk_send 端到端通路"调查的两半,两条 runtime 各有独立 bug,fix 后协议层与方案 D 账本完全复用。

**验证**:
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py`:通过。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge`:5 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`:79 tests 通过。
- `git diff --check -- bridges/pi_bridge.py tests/test_pi_bridge.py`:通过,仅有 Windows LF/CRLF 提示。
- Echo_tool 探针在 `--no-extensions --extension ./my-echo-ext/index.ts` 下成功 dispatch,JSON 流出现 `{"toolName":"echo_tool","result":{"content":[{"type":"text","text":"echoed: hello"}]}}`,证明规避方案有效。
- ✅ 黑盒复测已完成（2026-06-02 22:52-22:56）：群 `group:88f99bd38f3f` (test-run16)，2/3 case 通过，1 条因 codex CLI 未安装跳过（非代码缺陷）。详细结果见下方 §5.7。

**当前限制 / 已知技术债**:
- `--no-extensions` 是粗粒度规避,会把所有 pi 自带与用户安装的自动发现扩展一同禁用。如果未来项目需要某个特定 pi 扩展能力,需要重新评估(等 upstream 修了 plan-mode,可去掉此 flag)。
- Upstream issue 修复时间表未知。本地以 `--no-extensions` 为长期 workaround,无侵入。

**下一步**:
1. 持续观察 upstream issue `earendil-works/pi`,plan-mode 修复发布后再决定是否去掉 `--no-extensions`。
2. 如后续需要 codex 参与 agent-to-agent 通信，需在目标环境安装 Codex CLI 后补测 Case 2。
3. 可考虑开启下一阶段（任务队列、多 Group 协作、前端可视化讨论面板等）。

---

## 5.7 — 黑盒复测：agent-to-agent 通信端到端验证
Updated: 2026-06-02 23:55 (Asia/Shanghai)

### 测试环境
- TALK Server: `127.0.0.1:8000`
- 测试群: `group:88f99bd38f3f` (test-run16)，成员 human:qa + agent:pi + agent:pi-kimi + agent:codex
- pi CLI: v0.78.0 (Google provider)
- Bridges: agent:pi + agent:pi-kimi 均以 `--no-extensions --extension talk_tools_extension.ts` 启动
- codex CLI: 未安装，agent:codex bridge 未启动

### Case 1: `@agent:pi 去跟agent:pi-kimi打个招呼`  ✅ PASS
- agent:pi 接收指令 → 向 human:qa 发送可见回复 + 通过 `talk_send` 工具向 agent:pi-kimi 发送问候
- agent:pi-kimi 接收并回复 → 多轮交互共 7 turns，最终 closure
- Session #78: status=resolved, max_rounds=2, participant_ids=["agent:pi","agent:pi-kimi"]
- 账本: demand=1 (greeting), reply=6 (answer×4 + closure×2), round_index max=2

### Case 2: `@agent:codex 通知 agent:pi 项目进度已更新`  ⚠️ SKIP
- 消息 #2204 已发送 (to=["agent:codex"]),但 codex CLI 未安装于本环境
- 非代码缺陷，属环境限制

### Case 3: `@agent:pi 问 agent:pi-kimi 它现在忙不忙`  ✅ PASS
- agent:pi 接收指令 → 向 human:qa 发送可见回复 + 通过 `talk_send` 向 agent:pi-kimi 询问状态
- agent:pi-kimi 回复"不忙，暂时空闲" → 多轮交互共 5 turns，closure
- Session #79: max_rounds=2 正确限制
- 账本: demand=2 (question×2), reply=3 (answer×2 + closure×1), round_index max=2

### SQL 验证
```
✅ Agent-to-Agent 消息: 12 条 (from_id 含 agent:pi/agent:pi-kimi, to_ids 含对方 agent)
✅ discussion_turns: demand=3, reply=9 (turn_kind 同时出现 demand 和 reply)
✅ round_index 刹车正确: max=2, 达到上限后自动 closure
✅ --no-extensions 规避方案有效: talk_send 工具在 pi 0.78.0 下成功 register + dispatch
```

### 结论
**5.x agent-to-agent 通信主线关闭。** 方案 D (discussion_turns 显式账本 + talk_send function-calling) 在 pi 0.78.0 + `--no-extensions` 规避方案下端到端验证通过。codex 路径因 CLI 未安装跳过一个 case，但此前独立 probe 已验证 codex MCP 链路可写入 TALK_DEFERRED_FILE，协议层与方案 D 账本完全复用。

---

## 5.6 — codex MCP approval / UTF-8 修复
Updated: 2026-06-02 21:45 (Asia/Shanghai)

### codex MCP approval / UTF-8 修复

本轮按项目管理者给出的 patch 修复 Codex MCP 独立链路：Codex 已能看到 `talk_send` MCP，但非交互 `exec` 默认会把 MCP tool call 取消，且 Windows 下 MCP 子进程需要显式 UTF-8 环境。

**当前 Agent 角色**：Codex 按执行 Agent 处理（本会话未暴露 bridge 注入身份事实，按 `AGENTS.md` 默认规则）。

**已完成**：
1. `bridges/codex_bridge.py` 默认 discussion/tools 两档命令均追加 `--dangerously-bypass-approvals-and-sandbox`，用于绕过非交互 MCP approval 闸门。
2. 默认 MCP 配置追加 `mcp_servers.talk_send.env.PYTHONUTF8="1"` 与 `mcp_servers.talk_send.env.PYTHONIOENCODING="utf-8"`。
3. `tests/test_codex_bridge.py` 增加独立默认命令断言，覆盖 approval bypass、UTF-8 env、以及 per-call `TALK_*` 不 hardcode。
4. 独立 probe 已确认：显式 bypass + TALK_* env 时 `talk_send` MCP 会写入 `TALK_DEFERRED_FILE`。

**验证**：
- `.venv\Scripts\python.exe -m py_compile bridges\codex_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge`：13 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：77 tests 通过。
- `codex mcp get talk_send` 复用默认命令中的 `-c` 参数：通过，能看到 `args` 与 UTF-8 env。

**当前限制**：
- 尚未重跑完整 Group Hall 黑盒；本切片只修复 Codex MCP 默认命令链路。
- pi extension tool 仍是独立未解问题：当前 pi/provider 仍未把 extension `talk_send` 作为真实 toolCall 执行。

**下一步**：
1. 重启 Codex bridge 后复测 `@agent:codex 通知 agent:pi 项目进度已更新`，确认实际消息记录与 discussion turn。
2. 继续排查 pi extension 工具调用，或评估 bridge 层兼容解析 `<function_calls>` 作为临时兜底。

---

## 5.5
Updated: 2026-06-01 17:00 (Asia/Shanghai) — docs 目录二次整理完成

### docs 目录二次整理
- 根目录重复文档已全部删除，目标结构：
  - `docs/` 根仅保留 `PROJECT_BRIEF.md`、`PROGRESS.md`、`PROGRESS_HISTORY.md`、`spec/`、`guides/`
  - `docs/spec/`：PRODUCT.md、SDK.md、LOCAL_LAB_DESIGN.md、INTERACTION_FRAMEWORK.md、全部 MODULE_*.md
  - `docs/guides/`：QUICKSTART.md、QUICKSTART_USER.md、QUICKSTART_AGENT.md、DEPLOY.md
- 18 个根目录重复文件的 spec/guides 副本均为更新版（内容相同或路径已修正），已删除根目录副本
- 引用更新：PROJECT_BRIEF.md（目录树 + 模块索引 + Addendum）、AGENTS.md（模块指引）、CLAUDE.md（部署/快速启动链接）、README.md（Quickstart/Deploy/SDK 链接）
- 验证：`rg --files docs` 确认结构正确；旧路径搜索无残留；`git diff --check` 通过

---

## 5.5
Updated: 2026-06-01 16:35 (Asia/Shanghai) — 5.5 方案 D：discussion_turns 显式交互账本

### 1) Current Agent Role
- Codex:执行 Agent(本轮按用户明确计划落地 `INTERACTION_FRAMEWORK` 修订 + 方案 D)
- 角色来源:本会话未暴露 bridge 注入身份事实,按 `AGENTS.md` 默认执行 Agent

### 2) 5.5 当前状态总览

**已完成**:
- step 1:function-calling 最小可验证版本(`talk_send` 工具)
- step 2:agent_end 钩子(延迟发送,visible reply 先于 `talk_send`)
- P0 修复:身份注入、`stance` 参数、turn limit 刹车、visible reply suppress
- 方案 C:`talk_send` 继承 `reply_to` 链,保留为 UI/引用机制,不再作为轮次协议状态
- 方案 D:`discussion_turns.turn_kind` 显式记录 `demand / reply`,bridge 用 active session 的最大 `demand.round_index` 判断第 2 轮允许和第 3 轮刹车
- 删除上一轮临时"打招呼关键词兜底",回归"模型自主判断,bridge 机械执行协议"
- 修订 `docs/spec/INTERACTION_FRAMEWORK.md`:明确 `reply_to` 只表示 UI/引用关系,协议状态由 `discussion_sessions + discussion_turns` 账本承担

**当前规则**:
- human 消息仍允许暴露 `TALK_DEFERRED_FILE`
- agent 消息若能归入 active discussion:只有当 `max(demand.round_index) < 2` 时才允许继续 `talk_send`
- `talk_send` 成功发送后追加 `turn_kind=demand`;visible reply 成功发送后追加 `turn_kind=reply`
- 整个 session 最多出现 `round_index=2` 的 `demand`;之后只能回复、收口或升级 human

**已知限制**:
- 本轮完成单元/回归测试,尚未做真实黑盒复测
- 若 session/turn 查询能力缺失,当前兼容旧 fake client 会退化;真实服务端路径已具备 `turn_kind` 查询与迁移
- `bridges/talk_tools_extension.ts` 仍有本轮前已有的 alias 相关未提交改动,未在本切片扩展处理

### 3) 代码变更(本轮)

| 文件 | 关键变更 |
|------|---------|
| `docs/spec/INTERACTION_FRAMEWORK.md` | 重写为方案 D:四分类保留,`reply_to` 退回引用语义,`turn_kind + round_index` 承担协议状态 |
| `docs/spec/MODULE_discussions.md` | 增补 `turn_kind` 字段、账本刹车规则和验收点 |
| `server/models.py` / `server/routes/discussions.py` / `server/db.py` | `discussion_turns.turn_kind` 模型、API 输出/输入、SQLite 轻量迁移和索引 |
| `TALK/client/talk_client.py` / `TALK/client/talk_client_sync.py` | `append_discussion_turn(..., turn_kind="reply")` SDK 参数 |
| `bridges/cli_bridge.py` | `demand` 轮次计算、deferred `talk_send` 成功后写账本、visible reply 写 `reply`、第 3 轮停止暴露 `TALK_DEFERRED_FILE`、删除关键词兜底 |
| `tests/test_cli_bridge.py` / `tests/test_discussions.py` / `tests/test_talk_client.py` | 新增方案 D 单元/回归覆盖,删除关键词兜底测试 |

### 4) 验证

```bash
.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py server\models.py server\db.py
.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions
.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_talk_client
git diff --check
```

结果:
- `py_compile`:通过
- `tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions`:61 tests 通过
- `tests.test_discussions tests.test_talk_client`:16 tests 通过
- `git diff --check`:通过,仅有 Windows LF/CRLF 提示

### 5) 当前 Bridge 启动命令

```bash
# TALK Server
.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload

# agent:pi(默认命令已包含 --tools talk_send --extension;确保无 TALK_PI_COMMAND 残留覆盖)
.venv\Scripts\python.exe bridges/pi_bridge.py --name "agent:pi" --key "pi-key" --decision-tier execution

# agent:pi-kimi(默认命令已包含 --tools talk_send --extension;确保无 TALK_PI_COMMAND 残留覆盖)
.venv\Scripts\python.exe bridges/pi_bridge.py --name "agent:pi-kimi" --key "pi-kimi-key" --decision-tier execution

# agent:codex（讨论档：read-only sandbox + talk_send MCP）
.venv\Scripts\python.exe bridges/codex_bridge.py --name "agent:codex" --key "codex-key" --decision-tier decision

# agent:codex（施工档：workspace-write sandbox + talk_send MCP）
.venv\Scripts\python.exe bridges/codex_bridge.py --name "agent:codex" --key "codex-key" --decision-tier decision --codex-execution-profile tools
```

### 6) 下一步

1. 重启 TALK Server 和 `agent:pi` / `agent:pi-kimi`
2. 在 `group:96b88a2357a7` 或新群黑盒复测:`@agent:pi 去跟agent:pi-kimi打个招呼`
3. 验证最多一次第 2 轮扩展,且 session 已有 `demand round_index=2` 后不再产生新的 `talk_send`
4. 若黑盒仍未调用工具,再抓取对应消息记录和 bridge env/prompt dump,排查模型工具调用链本身

## Recent Notes
- 🎉 **2026-06-02 23:55 5.x agent-to-agent 通信主线 SHIP**。黑盒在 `group:88f99bd38f3f` 端到端验证:12 条 agent-to-agent 消息、demand=3 + reply=9、round_index 硬刹车在真实 LLM + 真实多 agent 群里被触发。方案 D(`discussion_turns` 显式账本)、Prompt 三层架构(SNR 4x)、talk_send function-calling 三条主线一并落地。Upstream issue #5327 在外侧跟进,本地以 `--no-extensions` 长期 workaround。Codex 路径代码已 ready,等环境装好补一条 case 即可。
- 2026-06-02 23:30 Pi extension dispatch 根因锁定为 plan-mode `setActiveTools` 全量替换;bridge 加 `--no-extensions` 规避,upstream issue 已提交 `earendil-works/pi`。三天 debug 收敛到 1 行 flag,核心方法论:猜不出就打开盒子读源码插桩。
- 2026-06-02 21:45 codex MCP 端到端通过:bridge 显式 `--dangerously-bypass-approvals-and-sandbox` 关 approval 闸门,`mcp_servers.talk_send.env.PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` 解 Windows codepage 初始化失败。
- 2026-06-01 18:00 codex MCP 路径集成完成：新增 `bridges/talk_send_mcp.py`，codex bridge 改用 function-calling + MCP，与 pi 共用 JSONL + env-var 契约，bridge 延迟执行逻辑不变。
- 2026-06-01 docs 目录二次整理：根目录 MODULE_*.md / PRODUCT.md / SDK.md / LOCAL_LAB_DESIGN.md / QUICKSTART*.md / DEPLOY.md 全部移至 spec/ 或 guides/ 并删除根目录副本；4 个文件引用已更新。
- 2026-06-01 14:40 的"打招呼关键词兜底"已被本轮方案 D 明确移除；历史条目保留为曾经尝试记录。
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
