# Project Progress

## Latest
Updated: 2026-05-29 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md` 抽象角色字典 + bridge 启动时注入的 `decision_tier`。
- 当前 Claude 角色：执行 Agent（bridge 注入 `decision_tier=execution`）。
- 5.3 落地后，bridge 已将 `member_id / decision_tier / 业务角色` 三元事实注入 prompt；PROGRESS.md 本节为过渡机制，待 `groups.metadata` 落地上线后可精简。

### 2) Current Progress
- **修复项 5.1 + 5.2 + 5.3 已完成**（2026-05-29 第一轮）：

  **5.1 visible_reply 调度顺序修正**：
  - `handle_incoming_message()` 中 `client.reply()` 移到 `execute_talk_actions()` 之前，确保 visible_reply 先回 sender
  - 删除 `"已按讨论协议继续推进。"` 和 `"({bridge_label} finished without visible output.)"` 两个 fallback
  - Action 错误通知作为 follow-up relay

  **5.2 去除 prompt 中具体例句**：
  - `RESPONSE_STYLE_INSTRUCTIONS` 中移除 `"for example '<agent id> 在线。'"`

  **5.3 Agent 角色注入框架（基础设施切片）**：
  - 新增 `--decision-tier` CLI 参数（`decision` / `execution`，缺省 `execution`）
  - 新增 `_decision_tier_line()` 中文分级描述 + `_build_group_member_context()` 群成员上下文获取
  - `build_cli_prompt()` / `build_cli_task_prompt()` 注入三元事实 + 群成员清单 + 约束（只能提及清单内成员，metadata 缺失走严格策略）
  - pi 和非 pi prompt 格式同步更新
  - 新建 `deploy/bridges.example.json` 含 `decision_tier` 字段

- **5.3 修复回炉**（Claude 作为执行 Agent，2026-05-29 第二轮，针对 `test_after_5.3.md` 黑盒测试结果排查）：

  **背景**：第一轮 5.3 落地后跑黑盒测试，codex 表现达预期，但 pi 全线 FAIL —— 反复出现"bobo"幻觉名、自封"方案评审者"、寒暄场景持续扩展。诊断发现根因不是 5.3 设计或注入逻辑，而是 **pi 自己的 `DEFAULT_SYSTEM_PROMPT`（在 commit 3c7ca9a 引入）硬编码了 `to=human:bobo` 与 `"评审方案"`**，且通过 `--system-prompt` argv 以 system role 高权重传给 pi CLI，**直接压垮了 5.3 在 user prompt 末尾的群成员清单注入**。codex 没有这种 system prompt 硬编码所以 5.3 对它生效。

  **P0：`bridges/pi_bridge.py` 去硬编码**：
  - 删除 `DEFAULT_SYSTEM_PROMPT` 中两处 `to=human:bobo`，改为 `to=「清单内的 human id」`（CJK 角括号避免触发 shell metacharacter 守卫）
  - 删除 `"评审方案"` 自封定位（pi 把这个当成核心能力主动招揽工作）
  - 加入"回复克制"段（一两句话回应寒暄、不要追问、不要主动 offer 服务）
  - 加入"身份与成员清单"段（明确声明用户消息开头的 `[系统]` 块是唯一身份事实，禁止使用清单外的任何名字）

  **P1：`bridges/cli_bridge.py` pi 路径让 5.3 真正生效**：
  - `build_cli_prompt()` pi 分支：`[系统]` 块从 prompt **末尾**挪到 **开头**（高权重位置），格式：身份 + 决策分级 + 群成员清单 + 回复克制 + `[用户消息]` 标签 + 任务正文
  - `build_cli_task_prompt()` pi 分支：同样调整，开头 `[系统]` + 回复克制 + `[任务]` + 标题/正文
  - pi 现在也拿到了"回复克制"指引（之前完全没拿到 `RESPONSE_STYLE_INSTRUCTIONS`，这是寒暄持续扩展的另一个原因）

  **5.1 / 5.2 / 5.3 设计层完全未动** —— 这次只补 pi 路径的实现遗漏 + 清理 pi system prompt 硬编码。codex 路径不变。

### 3) Open Questions / Pending Confirmation
- `groups.metadata` JSON 字段仍待修复项 5.4 落地；当前 5.3 按 metadata 缺失走严格默认策略。
- PROGRESS.md 第 1 节"Current Agent Role"过渡声明可在 5.4 上线后精简。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
- Web UI 尚未展示 discussion session/turn。
- Group 删除 / 归档语义、Schedule 后台触发策略、未读/关注状态和文档编辑锁仍待后续确认。

### 4) Next Plan
1. 项目管理者重启 server / Codex bridge / pi bridge 后，复跑 `D:\claude-test\black box test\talk\codexscenario-1-scope-fix\test_after_5.3.md`（结果区已清空回模板状态）。本轮重点验证 pi 路径：
   - pi 不再出现 `bobo` / `paddy` 等清单外人名（场景 2/3/6 重点看）
   - pi 不再自称"方案评审"或类似自封角色（场景 1/9 重点看）
   - pi 在寒暄场景下用一两句话收口，不主动追问项目/任务/协作（场景 1/2/3/8 重点看）
   - codex 路径保持不变（不应被打坏）
   - 不变量保持：场景 4/5 继续 PASS
2. 黑盒测试通过后，继续修复项 5.4：`groups.metadata` JSON 字段落地与读写 API
3. 5.4 就绪后，回头打开 5.3 的"按角色注入"分支（`_build_group_member_context()` 中 `metadata.roles` 线路无需返工）

### 5) Verification
- `py_compile bridges/cli_bridge.py bridges/codex_bridge.py bridges/pi_bridge.py tests/test_cli_bridge.py tests/test_pi_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — **48 tests 全部通过**（含新增 2 个 5.3 P1 回归测试）
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` — **24 tests 全部通过**（确认未打坏 codex / discussions / SDK 路径）
- 全量 `unittest discover -s tests` — 150 tests，**1 failure：`tests.test_websocket` 的 presence timing 超时（环境因素，非本轮引入）**
  - 已确认 `test_websocket.py` / `test_support.py` / `server/ws_hub.py` 不 import 任何 `bridges/*` 代码，与本轮改动无关
  - 重跑本测试集每个测试平均 40s（正常应 < 1s），符合本机此刻负载偏高（项目管理者手动起着 server + codex/pi bridge）的特征
  - PROGRESS_HISTORY 早前已记过类似 WS timing flakiness
  - 第一轮 5.1-5.3 落地的验证记录也未跑 test_websocket，复合佐证此为已知 timing 不稳定测试
- 本轮代码相关测试总计 **72 tests** 全部通过（上一轮 70 + 新增 2）
- Not run by design: 真实 Codex+pi 长链路体验自测；由项目管理者复跑 `test_after_5.3.md` 黑盒验证

### 6) Changed Files
本轮（5.3 修复回炉）改动：
- `bridges/pi_bridge.py`（P0：删 bobo 硬编码 + 删评审方案自封 + 加回复克制 + 加身份清单约束）
- `bridges/cli_bridge.py`（P1：pi 路径 `[系统]` 块从末尾挪到开头 + 加回复克制指引）
- `tests/test_pi_bridge.py`（P0 回归：禁止 system prompt 含具体人名 / 自封角色 / 缺少"成员清单"约束）
- `tests/test_cli_bridge.py`（P1 回归：pi prompt 须以 `[系统]` 开头 + 必含"回复克制" + 群成员清单注入位置在 `[用户消息]` 之前）
- `docs/PROGRESS.md`

上一轮（5.1+5.2+5.3 首次落地）未动，列表见 git 历史 commit `2877130`。

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
