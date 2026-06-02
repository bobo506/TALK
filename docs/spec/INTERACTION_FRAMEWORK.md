# Agent 交互框架设计

> TALK 多 Agent 通信的交互模型、消息分类体系与协议设计方案。
> 本文档面向外部分享与技术讨论，可作为项目的核心设计亮点。

---

## 1. 设计动机

传统 Agent 通信方案（如 `TALK_ACTION` 文本协议标签）让模型在“自然人对话”和“结构化协议指令”两个信道上同时输出，导致模型频繁失败。当前方向是把**通信协议下沉到 function-calling 层**，让模型只需要判断“我是否要对谁说什么”，由 bridge 层机械执行协议。

在这个基础上，TALK 抽象出**统一的消息四分类模型**，并通过 `discussion_sessions + discussion_turns` 形成显式交互账本：模型负责语义判断，bridge 负责记录需求/回复、轮次和刹车。

---

## 2. 消息四分类模型

### 2.1 核心概念

任何一条消息，都可以从两个维度进行划分：

| 维度 | 取值 | 含义 |
|------|------|------|
| **方向** | 发出 / 收到 | 消息从谁到谁 |
| **性质** | 需求 / 回复 | 消息是“发起一个请求”还是“回应一个请求” |

组合得到四种消息类型：

```text
                    方向
               发出          收到
        ┌──────────┬──────────┐
   需求 │ 发出，需求 │ 收到，需求 │   ← talk_send（function-calling）
性质    ├──────────┼──────────┤
   回复 │ 发出，回复 │ 收到，回复 │   ← visible reply（bridge 自动）
        └──────────┴──────────┘
```

### 2.2 TALK 系统中的映射

| 类型 | TALK 对应 | 触发方式 | 账本记录 |
|------|----------|---------|---------|
| **发出，需求** | `talk_send` 工具调用 | agent 主动调用 | `discussion_turns.turn_kind = demand` |
| **收到，需求** | bridge 收到被 `talk_send` 发出的消息 | Hall 消息到达目标 agent | 通过既有 `demand` turn 归入 session |
| **发出，回复** | `client.reply()` visible reply | bridge 自动发 CLI stdout | `discussion_turns.turn_kind = reply` |
| **收到，回复** | bridge 收到 visible reply | Hall 消息到达目标 agent | 通过 `reply_to` 引用定位相关消息，再查账本 |

### 2.3 区分机制

消息的性质（需求 vs 回复）不再由 `reply_to` 唯一判定，而由交互账本判定：

- `discussion_turns.turn_kind = demand`：本条 Hall 消息是一次新需求。
- `discussion_turns.turn_kind = reply`：本条 Hall 消息是一次可见回复。
- `discussion_turns.round_index`：该需求属于第几轮扩展。
- `reply_to`：只表示 UI 引用、消息可读性和定位辅助，不承担“需求/回复/轮次”的协议状态。

这条边界很重要：`reply_to` 可以帮助用户理解“这句话在回复哪条消息”，也可以帮助 bridge 找到候选 discussion，但最终协议状态必须以 `discussion_turns` 为准。

---

## 3. 交互轮次模型

### 3.1 基本定义

- **一轮交互** = 一个完整的“发出需求 → 收到需求 → 发出回复 → 收到回复”闭环。
- **第 1 轮**通常由 human 触发：human → agent → `talk_send` → other agent。
- **第 2 轮**允许任一 agent 扩展一次：可以是收到第 1 轮需求的一方扩展，也可以是原发起方收到 visible reply 后扩展。
- **第 3 轮及以后**禁止新需求，只能回复、收口或升级 human。

### 3.2 轮次图示

```text
第 1 轮                              第 2 轮（可选，整个 session 最多一次）
┌─────────────────────┐       ┌──────────────────────────┐
│ human → pi          │       │ pi-kimi 回复时可扩展       │
│ pi → talk_send      │ ───→  │ 或 pi 收到回复后可扩展      │
│ pi-kimi → visible   │       │ 写入 demand round_index=2 │
└─────────────────────┘       └──────────────────────────┘
                  ↓
       已出现 demand round_index=2 后禁止继续 talk_send
```

### 3.3 关键约束

| 约束 | 机制 | 层级 |
|------|------|------|
| 第 2 轮不强求 | agent 自主判断是否需要扩展 | 模型语义判断 |
| 第 2 轮全局限额 | 同一 active session 最多出现一次 `demand round_index=2` | bridge 账本判断 |
| 第 3 轮禁止新需求 | `max(demand.round_index) >= 2` 时不创建 `TALK_DEFERRED_FILE` | bridge 硬拦截 |
| visible reply 不涨需求轮次 | 只写 `turn_kind=reply` | bridge 账本记录 |
| `reply_to` 不污染协议状态 | 只做引用和定位辅助 | 数据语义约束 |

---

## 4. 技术实现：方案 D 账本架构

```text
┌──────────────────────────────────────────────┐
│ 第 1 层：模型自主判断                         │
│ • human 指令 → 模型可调用 talk_send            │
│ • agent 消息 → 模型自然回复，必要时可扩展一次    │
│ • 不用关键词兜底触发代发                       │
├──────────────────────────────────────────────┤
│ 第 2 层：Bridge 协议执行                       │
│ • talk_send → 写入 JSONL 延迟执行文件          │
│ • bridge 先发送 visible reply，再执行 talk_send │
│ • talk_send 可带 reply_to=当前消息 id 作引用    │
├──────────────────────────────────────────────┤
│ 第 3 层：显式交互账本                          │
│ • talk_send 成功后追加 turn_kind=demand         │
│ • visible reply 成功后追加 turn_kind=reply      │
│ • round_index 只由 demand turn 推进             │
├──────────────────────────────────────────────┤
│ 第 4 层：Bridge 硬刹车                         │
│ • 读取 active session 最大 demand round_index  │
│ • 小于 2 才暴露 TALK_DEFERRED_FILE             │
│ • 达到 2 后只能回复、收口或升级 human           │
└──────────────────────────────────────────────┘
```

---

## 5. Prompt 分层架构(SNR 与可扩展性)

### 5.1 问题

Function-calling 转向后,bridge 仍需要让模型获取若干信息:角色与身份、runtime 行为约束(单轮 print 模式、输出通道)、反工具幻觉约束、当前 sender 与 task。如果全部塞进单次调用 prompt,会出现两个反向问题:

1. **任务 SNR 被稀释**:打招呼一类短指令(~13 字)被 400-600 字脚手架包裹,信噪比 ~30-50x,模型注意力分散,反而执行不利落。
2. **不可扩展**:每加一个新工具就要在 bridge prompt 里重申"我有什么、什么时候用"这种 case-级规则,工具数量 N → prompt 复杂度 O(N),且难免穷举不全。

### 5.2 三层架构

按 **生命周期 + 责任归属** 把 prompt 拆成三层:

```text
┌─────────────────────────────────────────────────────────┐
│ 工具自描述层  生命周期:工具注册时一次  责任人:工具作者   │
│  • name / description / parameters / promptGuidelines   │
│  • runtime(pi/codex)启动时自动注入模型 catalog          │
│  • bridge 不重复转述                                     │
├─────────────────────────────────────────────────────────┤
│ 系统层        生命周期:bridge 启动到关闭  责任人:bridge  │
│  • 角色与输出通道("你是 TALK 群里的 agent")              │
│  • runtime 单轮语义                                      │
│  • 反工具幻觉约束("清单外的工具不存在")                  │
│  • 注入点:pi `--system-prompt` / codex base instructions │
├─────────────────────────────────────────────────────────┤
│ 单次调用层    生命周期:每条消息            责任人:bridge │
│  • 谁(sender) 对你说了什么(task)                        │
│  • 群成员清单                                            │
│  • discussion_context(若存在)                            │
│  • 注入点:CLI prompt argv                                │
└─────────────────────────────────────────────────────────┘
```

### 5.3 各层职责边界

| 内容 | 工具自描述层 | 系统层 | 单次调用层 |
|------|:---:|:---:|:---:|
| 工具 name / 参数 schema | ✅ |  |  |
| "什么时候调这个工具" | ✅ promptGuidelines |  |  |
| 你是谁、有什么通道 |  | ✅ |  |
| 本会话单轮运行 |  | ✅ |  |
| 清单外工具不存在 |  | ✅ |  |
| 当前 sender + task |  |  | ✅ |
| 群成员清单 |  |  | ✅ |
| 当前 discussion 上下文 |  |  | ✅ |

### 5.4 可扩展性

加一个新工具(例如 `talk_create_task`)的标准动作:

1. 在 `bridges/talk_tools_extension.ts`(pi)或 `bridges/talk_send_mcp.py`(codex)中加 `registerTool({...})`,写好 description / promptGuidelines / parameters。
2. 在 bridge 启动命令里把它列进 `--tools`(pi)或 `mcp_servers` 配置(codex)。
3. 如果走延迟执行,在 `cli_bridge._read_and_execute_deferred_actions` 里加一个分支调对应 SDK。

**系统层 prompt 与单次调用 prompt 均无需修改。** bridge prompt 跟工具数量 O(1) 解耦,bridge 代码也不需要按工具数量做条件分发。

### 5.5 SNR 估算

| 版本 | 系统层字数 | 单次调用 wrapping | task 字数 | per-call SNR |
|------|---:|---:|---:|---:|
| 5.5 前(全塞 per-call) | ~10 | ~200 | 13 | 15x |
| 全打包到 per-call(中间草稿,被否决) | ~10 | ~600 | 13 | 45x |
| **三层架构(当前方案)** | ~200 | ~50 | 13 | **4x** |

系统层 200 字仅在会话级被读取一次,不与单次任务争注意力。per-call SNR 从 15x → 4x 改善近 4 倍。

### 5.6 注意事项

- **系统层避免条件句**。"如果 X 则 Y,如果 A 则 B" 会让模型每次推理时都做一次 case 匹配。改用事实陈述("你的输出通道:可见回复 + 调用清单内的工具"),把 case 选择交回工具自描述层。
- **单次调用层避免重复系统层信息**。否则等于把系统层信息搬回了 per-call,SNR 又被打回原形。
- **反幻觉约束写成约束式而非黑名单**。"清单外工具不存在" > "你没有 ls / cat / grep / bash / 上网 / 记忆库 / …",后者随工具空间膨胀永远列不全。

---

## 6. 通信协议：talk_send 工具

### 6.1 工具定义

```text
talk_send(target, body, stance?)
  - target: 目标 member_id（如 agent:codex）
  - body:   消息正文
  - stance: 消息立场（question | greeting | answer | agree | disagree | closure）
```

工具接口保持稳定；轮次、session、账本写入都由 bridge 处理。

### 6.2 延迟执行机制（agent_end 钩子）

```text
1. bridge 收到消息 → 读取 active discussion 账本
2. 若允许扩展 → 创建 JSONL 临时文件 → 设置 TALK_DEFERRED_FILE
3. spawn CLI（带 talk_send extension）
4. agent 调 talk_send → extension 写入 JSONL
5. agent 生成 visible reply
6. bridge 发送 visible reply 给 sender，并记录 turn_kind=reply
7. bridge 读 JSONL，逐条执行 talk_send，并记录 turn_kind=demand
8. bridge 清理 JSONL 临时文件
```

**时序保证**：visible reply 始终在 deferred `talk_send` 之前到达；账本也应尽量贴近该时序记录。

### 6.3 reply_to 引用机制

`talk_send` 执行时可以继续继承当前消息 id 为 `reply_to`：

```text
human #2090
  └── pi talk_send #2101      (reply_to=2090, turn_kind=demand, round_index=1)
       └── pi-kimi visible #2102 (reply_to=2101, turn_kind=reply)
            └── pi talk_send #2103 (reply_to=2102 或当前消息, turn_kind=demand, round_index=2)
```

这里的 `reply_to` 只帮助 UI 展示和 bridge 定位候选 discussion；真正决定是否允许继续扩展的是该 session 中已有的 `demand` turn。

### 6.4 方案 D 判断逻辑

```python
talk_send_allowed = False
if sender is human:
    talk_send_allowed = True
elif discussion is None:
    talk_send_allowed = message.reply_to is None
else:
    talk_send_allowed = max_demand_round(discussion.turns) < 2
```

执行成功后：

```python
if action == "talk_send" and sent_ok:
    round_index = min(max_demand_round(turns) + 1, 2)
    append_turn(turn_kind="demand", round_index=round_index)

if visible_reply_sent and active_discussion:
    append_turn(turn_kind="reply")
```

如果 session 或 turn 查询失败，bridge 应保守处理，避免消息风暴；不能退回关键词兜底或纯 prompt 约束。

### 6.5 Pi runtime 工具覆盖陷阱与规避

Pi 内置的 `plan-mode` 扩展(自带,负责 `/plan` 交互)在 `rebindSession` 事件回调里无条件执行:

```ts
// @earendil-works/pi-coding-agent/extensions/plan-mode/index.ts:343-345
pi.setActiveTools(NORMAL_MODE_TOOLS);
// NORMAL_MODE_TOOLS = ["read","bash","edit","write","grep","find","ls","questionnaire","subagent"]
```

这是**全量替换**而非 merge,会把同会话内其他扩展刚通过 `pi.registerTool({...})` 注册的工具**全部抹掉**。时序:

```
1. AgentSession._refreshToolRegistry() → setActiveToolsByName([...,"talk_send",...]) ✅
2. rebindSession 事件 fire
3. plan-mode 回调:setActiveTools(NORMAL_MODE_TOOLS)  ❌ talk_send 在这一步丢失
4. LLM 拿到的工具清单 = NORMAL_MODE_TOOLS,无 talk_send
```

**规避方案(当前采用)**:bridge 启动 pi 时加 `--no-extensions`,禁用所有自动发现扩展(包括 plan-mode),`-e` 显式加载的 `talk_tools_extension.ts` 不受影响。

```
pi --print --mode text --no-context-files --no-builtin-tools --no-extensions
   --tools talk_send --no-session --thinking off
   --extension <path>
   --system-prompt <system-layer-prompt>
```

`--no-builtin-tools`(禁 read/bash/edit/write 等)与 `--no-extensions`(禁自动发现扩展)正交,两者均保留可获得最小化、可预测的工具表面 —— LLM 只看到 `talk_send`。

**已向上游提 issue**(`@earendil-works/pi-coding-agent`):plan-mode 的 `setActiveTools` 应改为 merge 语义,保留非 plan-mode 主管的外部扩展工具。

### 6.6 Windows 下 MCP 子进程的 UTF-8 强制

Windows 系统默认 codepage 是 cp936(中文环境),Python MCP server 启动时若继承默认 codepage 处理中文 args / stdin 会触发 `invalid unicode code point` 初始化失败。Codex bridge 在 `mcp_servers.<name>.env` 中显式强制 UTF-8:

```python
-c mcp_servers.talk_send.env.PYTHONUTF8="1"
-c mcp_servers.talk_send.env.PYTHONIOENCODING="utf-8"
```

其他语言的 MCP server 同样需要相应的 UTF-8 强制(Node 设置 `LANG=C.UTF-8` 或 `--unicode-encoding=utf8` 等)。新增 MCP server 时这是 Windows 环境下的常规检查项。

### 6.7 Codex 非交互模式的 MCP approval 闸门

Codex `exec` 默认对 MCP tool call 走 approval 闸门,在非交互(`-` stdin)模式下没人能确认,默认 deny,日志显示 `user cancelled MCP tool call`。Bridge 通过 `--dangerously-bypass-approvals-and-sandbox` 显式放行:

```
codex exec --skip-git-repo-check --ignore-rules
           --sandbox <read-only|workspace-write> --color never
           --dangerously-bypass-approvals-and-sandbox
           -c base_instructions=...
           -c mcp_servers.talk_send.command=...
           -c mcp_servers.talk_send.args=...
```

风险面控制依赖两个事实:
- MCP catalog 只暴露 `talk_send` 一个工具(bridge 配置,LLM 无法绕开)
- `--sandbox` 仍受 profile(`read-only` / `workspace-write`)控制,bypass flag 只关 approval,不放行 sandbox 写权限

未来 codex 提供 per-tool approval policy 后,应改为只放行 `talk_send`,而非全局 bypass。

---

## 7. 方案 C 定位

方案 C（`talk_send` 自动继承 `reply_to` 链 + 链深度刹车）是可追踪的过渡方案，但不再作为最终协议状态来源。

| 方面 | 方案 C | 方案 D |
|------|--------|--------|
| 轮次来源 | `reply_to` 链深度 / `reply_to.from_id` | `discussion_turns.turn_kind + round_index` |
| 优点 | 实现轻，容易追踪消息链 | 语义清晰，支持任一 agent 发起第 2 轮 |
| 缺点 | 污染 `reply_to` 语义，把引用关系当协议状态 | 需要轻量账本迁移和 bridge 写 turn |
| 当前状态 | 保留 `reply_to` 作为 UI 引用 | 正式采用 |

---

## 8. 演进历史与测试数据

### 8.1 协议演进

| 阶段 | 协议 | 问题 | 状态 |
|------|------|------|------|
| v0 | `TALK_ACTION` 文本标签 | 模型无法可靠输出协议 | 已降为兼容路径 |
| v1 | function-calling `talk_send` | 消息风暴 | 已迭代 |
| v2 | + stance + turn limit | 汇报体、重复回复 | 已迭代 |
| v3 | + agent_end 钩子 + suppress | 接近理想 | 已保留 |
| v4 | + `reply_to` 链 depth | 能刹车但语义混用 | 过渡方案 |
| v5 | + `discussion_turns` 显式账本 | 支持任一方第 2 轮扩展 | 当前方案 |

### 8.2 关键决策

| 决策 | 原因 | 状态 |
|------|------|------|
| 元数据走环境变量，不塞进 prompt | 避免模型混淆 | 保留 |
| `talk_send` 不直接发 HTTP | 保证 visible reply 时序 | 保留 |
| `reply_to` 只做引用/可读性 | 避免用 UI 字段承载协议状态 | 当前约束 |
| `turn_kind` 区分需求/回复 | 让 bridge 可机械判断轮次 | 当前约束 |
| 删除关键词兜底 | 自然语言关键词容易误伤，违背模型自主判断方向 | 当前约束 |
| agent-to-agent 一刀切禁用 deferred file | 会堵住正常第 2 轮扩展 | 已废弃 |
| Prompt 按生命周期分三层 | 控制 per-call SNR;工具扩展时 prompt O(1) 不需要改 | 当前约束 |

---

## 9. 设计原则总结

1. **模型只管语义，bridge 管协议**：模型判断是否需要联系谁；协议执行、账本记录和刹车由 bridge 负责。
2. **消息四分类覆盖所有场景**：需求/回复 × 发出/收到 = 4 种类型。
3. **轮次显式入账**：需求轮次不从 `reply_to` 猜，而从 `discussion_turns` 查。
4. **第 2 轮允许但全局限额**：任一 agent 可以扩展一次，但整个 session 最多一个 `round_index=2` 的 demand。
5. **时序保证第一**：visible reply 始终先于 deferred `talk_send`，账本尽量保持同序。
6. **Prompt 按生命周期分层**：工具描述归工具自己,角色与 runtime 不变量归系统层,sender/task/上下文归单次调用层。bridge prompt 跟工具数量 O(1) 解耦。

---

## 10. 相关文档

- `docs/spec/LOCAL_LAB_DESIGN.md` — 本地实验室设计（含 function-calling 转向决策）
- `docs/spec/MODULE_bridges.md` — Bridge 模块技术 spec
- `docs/spec/MODULE_discussions.md` — Discussion 协议 spec
- `docs/PROGRESS.md` — 最新进度快照
- `bridges/talk_tools_extension.ts` — `talk_send` 工具实现
- `bridges/cli_bridge.py` — Bridge 层协议执行
