# Project Progress

## Latest
Updated: 2026-05-30 (Asia/Shanghai) — 5.5 step 1 完成，function-calling 验证通过

### 1) Current Agent Role
- pi：执行 Agent（本切片负责 5.5 step 1 代码落地）
- 角色来源：bridge 注入 `decision_tier=execution`
- 5.3 已落地角色注入框架，`member_id / decision_tier` 通过 prompt + 环境变量注入

### 2) 5.5 Step 1 完成状态

**目标**：pi bridge 切换到 function-calling，注册 `talk_send` 工具，验证 pi → kimi 双向通信。

**验证通过**（2026-05-30 最后一轮测试）：

| 验证项 | 结果 |
|--------|------|
| pi 调用 `talk_send` 联系其他 agent | ✅ kimi-k2.6 模型可靠调用 |
| `group_id` 通过环境变量自动注入 | ✅ `TALK_GROUP_ID`，LLM 不需要传 |
| pi → pi-kimi 消息正确入群时间线 | ✅ `group=group:83aae24462b7` |
| pi-kimi → pi 回复正确入群时间线 | ✅ 双向通信打通 |
| 不再出现 TALK_ACTION 文本标签 | ✅ |
| 不再出现 `orchestrator/oracle` 等幻觉名 | ✅ |

**架构决策**（经过 4 轮 prompt 迭代后形成的最终方案）：

1. **元数据走环境变量，不放 prompt**：`group_id` → `TALK_GROUP_ID`，`decision_tier` → `TALK_DECISION_TIER`，`member_id` → `TALK_MEMBER_ID`
2. **不声明身份**：prompt 不给 `"你是 agent:pi"`，避免跟 pi 内核的"终端编码助手"身份冲突
3. **用户消息放最前面**，上下文在括号里作为辅助提示
4. **system prompt 极简化**：仅 `"按用户语言自然回复。"` 8 字
5. **成员清单**：prompt 逗号分隔 `"群成员：agent:pi, agent:pi-kimi, human:qa。"` + 环境变量 `TALK_GROUP_MEMBERS`

**最终 prompt 格式**（~130 chars）：
```
human:qa 对你说：去和 agent:pi-kimi 打个招呼

（群内有 agent:pi, agent:pi-kimi, human:qa 要向其他成员发消息时，使用 talk_send 工具。）
```

**已知限制**：
- **时序**：`talk_send` 在 visible reply 之前执行（`--print` 模式固有限制）。step 2 的 `agent_end` 钩子解决
- **模型依赖**：DeepSeek 对 function-calling 不可靠，pi 需要切 kimi-k2.6
- **旧协议共存**：TALK_ACTION 文本解析代码保留，后续统一迁移后删除

### 3) 当前代码变更清单（5.5 step 1）

| 文件 | 变更 |
|------|------|
| `bridges/talk_tools_extension.ts` | **新建** — pi 扩展，注册 `talk_send` 工具，从 `TALK_GROUP_ID` env 自动读取群 ID |
| `bridges/pi_bridge.py` | 默认命令改为 `--no-builtin-tools --tools talk_send --extension`；system prompt 极简；env var 注入（TALK_API_KEY 无条件覆盖，修复多 bridge key 冲突）|
| `bridges/cli_bridge.py` | prompt 极简化；`_build_group_member_context` 返回逗号分隔 + 写 `TALK_GROUP_MEMBERS` env；spawn 前注入 `TALK_GROUP_ID` / `TALK_DECISION_TIER`；`_decision_tier_line` 砍成 4 字；正常路径不列禁止名单（避免"不要想粉色大象"效应）；fallback 返回非空反幻觉提示 |
| `tests/test_pi_bridge.py` | 适配新 system prompt |
| `tests/test_cli_bridge.py` | 适配新 prompt 格式；新增 `BuildGroupMemberContextTests` 4 个回归用例（P2P/失败/空成员/正常路径）|
| `deploy/bridges.example.json` | **新建** — bridge 配置模板含 `decision_tier` 字段 |

### 4) 涉及的 Bug 修复（5.5 过程中发现并修复）

- **多 bridge key 冲突**：`pi_bridge.py` 用 `if "TALK_API_KEY" not in os.environ` 条件赋值，导致第二个 bridge 用第一个的 key → 改为无条件覆盖
- **provider 名称错误**：pi-kimi 用 `moonshot` 应为 `moonshotai-cn`，model `kimi2.6` 应为 `kimi-k2.6`
- **正常路径反幻觉黑名单引发"粉象效应"**：`严禁猜测 agent:oracle 等常见名` 反而让模型把自己当成 oracle → 正常路径不列禁止名单

### 5) 当前 Bridge 启动命令

```bash
# TALK Server
.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload

# agent:pi（kimi-k2.6，function-calling）
.venv\Scripts\python.exe bridges/pi_bridge.py --name "agent:pi" --key "pi-key" --decision-tier execution --pi-command "pi --provider moonshotai-cn --model kimi-k2.6 --print --mode text --no-context-files --no-builtin-tools --tools talk_send --extension D:/claude-test/TALK/bridges/talk_tools_extension.ts"

# agent:pi-kimi（kimi-k2.6，function-calling）
.venv\Scripts\python.exe bridges/pi_bridge.py --name "agent:pi-kimi" --key "pi-kimi-key" --decision-tier execution --pi-command "pi --provider moonshotai-cn --model kimi-k2.6 --print --mode text --no-context-files --no-builtin-tools --tools talk_send --extension D:/claude-test/TALK/bridges/talk_tools_extension.ts"

# agent:codex（未改，原样）
.venv\Scripts\python.exe bridges/codex_bridge.py --name "agent:codex" --key "codex-key" --decision-tier decision

# 诊断开关（可选）
set TALK_DUMP_PROMPT=1
```

### 6) 下一步计划（5.5 step 2）

1. 实现 `agent_end` 钩子：pi 输出后自动回传回复，pi 不需要显式"回复"
2. 解决 talk_send 在 visible reply 之前的时序问题
3. 保留 TALK_ACTION 文本协议兼容，不做删除

### 7) 数据库成员

```
agent:pi       key=pi-key       (kimi-k2.6 function-calling)
agent:pi-kimi  key=pi-kimi-key  (kimi-k2.6 function-calling)
agent:codex    key=codex-key    (原样未改)
human:qa       key=qa-test-key-789
```

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
