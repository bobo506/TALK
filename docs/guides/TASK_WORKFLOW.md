# TALK 使用流程：固定交付包与本地校验

本指南只覆盖**项目本地的使用流程**：交付时写一份固定结构的 JSON 交付包，用本地脚本做机械校验，
聊天/TALK 回复只报短结论和文件路径。不改 TALK 服务端、MCP/HTTP/SDK/bridge 实现、数据库或任务状态语义。

配套脚本：`scripts/talk_workflow.py`（仅标准库，无需额外依赖）。

## 1. 为什么这样做

| 旧痛点 | 现在的做法 |
| --- | --- |
| `get_task` 与 `collect_result` 重复取全文 | 交付包固定路径 + 固定字段，取一次就够 |
| runner 报 succeeded，但推送失败只能读正文才发现 | 交付结论由执行者显式声明 `complete/partial/blocked`，脚本拒绝把 runner 状态当结论 |
| 交付后 Codex 再拼进度、重复提交推送 | 执行者写进度草稿，Codex 只做收尾；详细证据留在交付包文件里 |

目标是在正常收尾路径上减少往返次数。**不承诺**固定工具轮数，也不承诺计费或额度节省。

## 2. 快速上手

```bash
# 1) 校验交付包（带上本次任务号，防止旧文件/别的任务报告被当成当前交付）
python scripts/talk_workflow.py validate .tmp/workflow-usage-1/development.json --expect-task-id 38

# 2) 需要时输出有界摘要（同样带 --expect-task-id）
python scripts/talk_workflow.py summary .tmp/workflow-usage-1/development.json --expect-task-id 38

# 3) 机器可读输出 / 收紧摘要上限
python scripts/talk_workflow.py summary .tmp/workflow-usage-1/development.json --expect-task-id 38 --max-chars 800 --json
```

`--expect-task-id` 是可选参数：**默认调用都要传**，省略时行为与旧版一致（只做格式校验）。
它只做一件事——核对“这份包是不是本次任务的交付”：`38` 与 `#38` 视为同一个任务号，
不一致就非零退出并给短错误，不吐报告内容。

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 校验通过（可能有脱敏警告）或摘要输出成功 |
| 1 | 交付包不合法：缺字段、类型/长度/条数越界、自报矛盾，或与 `--expect-task-id` 不一致 |
| 2 | 用法错误、文件不存在、非 UTF-8、JSON 解析失败（含嵌套过深）、文件超过 64 KiB |

## 3. 交付包字段（schema = `talk-delivery-1`）

顶层只允许下列 10 个字段，**出现未知字段一律拒收**。

| 字段 | 类型 | 上限 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `task_id` | string | 64 | 是 | **提交者本次的 TALK 任务号**，可写 `38` 或 `#38`（脚本等价规范化）；复核关联的开发任务号写在 `baseline.diff_note` 等说明文字里，不要占用 `task_id` |
| `conclusion` | enum | — | 是 | `complete` / `partial` / `blocked`，由执行者显式声明 |
| `completed` | string[] | 20 条 × 300 字 | 是 | 已完成项；`complete`/`partial` 时必须非空 |
| `unfinished` | string[] | 20 条 × 300 字 | 是 | 未完成项，可为空数组但不能缺省 |
| `blocked` | string[] | 20 条 × 300 字 | 是 | 阻塞项，可为空数组但不能缺省 |
| `changed_files` | string[] | 50 条 × 200 字 | 是 | **仓库相对路径**，禁止绝对路径 |
| `baseline` | object | — | 是 | `{ref, diff_note}`，实际基线 + 差异说明 |
| `verification` | object[] | 20 条 | 是 | `{check, result, evidence}`，`result` 为 `pass`/`fail`/`not_run` |
| `limitations` | string[] | 20 条 × 300 字 | 是 | 已知限制、未验证项 |
| `progress_draft` | object | — | 是 | `{summary, next}`，进度草稿（正式进度仍由 Codex 维护） |

子对象上限：`baseline.ref` ≤ 120、`baseline.diff_note` ≤ 300、`verification.check` ≤ 120、
`verification.evidence` ≤ 300、`progress_draft.summary`/`next` ≤ 300。所有文本必须单行，不允许换行或制表符。

## 4. 机械规则（校验器强制，不是建议）

1. **结论与清单互斥**：`complete` 时 `unfinished`/`blocked` 必须为空；`partial` 必须列出 `unfinished` 或 `blocked`；`blocked` 必须有 `blocked` 条目。
2. **结论与验证互斥**：`complete` 时 `verification` 里不允许出现 `result: "fail"`——“本次交付可用”与“某项验证失败”是自报矛盾，不能用“验收另算”豁免，应改报 `partial`/`blocked` 或修复后重跑。
   `partial`/`blocked` 仍可如实记录失败测试；`not_run` 是“确实没跑”，不算失败，可以出现在 `complete` 里。
3. **任务号核对**：传 `--expect-task-id` 时，`task_id` 规范化后必须一致，否则退出 1、只给短错误、不回显报告内容，用于挡住旧文件或另一个任务的报告。
4. **不推断结论**：`succeeded` 属于 runner 任务状态，不是交付结论。脚本里没有 `status` 字段，写进来会被当未知字段拒收。
5. **未知字段拒收**：原任务正文、Hall 历史、完整 diff、stdout/stderr 长日志、runner 状态一律不属于交付包。
6. **体积受控**：交付包 ≤ 64 KiB、显式 UTF-8（容忍 BOM），避免把日志塞进 JSON；解析层错误（非 UTF-8、JSON 语法错、嵌套过深、超限）一律短错误 + 退出 2，不吐 traceback、不回显原文。
7. **密钥不落包**：可见的 `key=value`、`sk-`、`ghp_`、`Bearer` 形态会被脱敏成 `[REDACTED]` 并给出警告；未识别形态的密钥仍需靠“不要把密钥写进交付包”这条规则兜住。
8. **校验 ≠ 验收**：脚本只检查格式与自报一致性，不代表业务验收通过，不自动收取结果、不 accept、不改任务状态。

## 5. 摘要规则

- 只输出交付包里的允许字段，原始 JSON、未知字段、日志正文都不会出现。
- 总长有固定上限：默认 1200 字符，`--max-chars` 可调，但会被夹到 600–4000。
- 展示优先级：摘要头/基线 → 阻塞 → 未完成 → 已完成 → 变更文件 → 限制 → 验证 → 进度草稿。
- 被截断一定可见：页脚固定显示 `— 摘要 N/上限 字符｜已截断：是/否`；条目未展开时追加
  `[摘要截断：未完成7项、变更文件50项 未展开，详见交付包文件]`，**不会静默丢弃** blocked/partial 与未完成项。
- 单条文本超过预览长度（80 字符）会截断并计数提示。
- 摘要里的“字符数”只是长度指标，**不能当计费 token 或额度**使用。

## 6. 可复制模板

### 6.1 短任务包模板（发给执行 Agent）

```text
【任务】<一句话目标>
【任务号】<task_id>
【原需求】<2-4 条要点，不要粘贴整篇历史>
【范围 / 不变项】只改 <路径>；不改 <明确排除项>（如服务端实现、数据库、任务状态语义）
【基线】<分支或 commit>；开工前核对 git status，他人改动保留并报告
【验收标准】<可机械检查的条目>
【测试证据】给出真实运行命令与结果；不允许真实 push / 长等待 / 建真实任务
【交付物】<固定交付包路径>，用 scripts/talk_workflow.py 校验通过
【收尾】开发完成即暂停等独立复核；不自行 commit/push
```

### 6.2 审查任务包模板（发给复核 Agent）

```text
【复核对象】<交付包路径> + <变更文件清单>
【原需求】<同上，2-4 条要点>
【范围 / 不变项】<同任务包>
【实际基线 / 差异】<报告的基线> → <当前 HEAD>；用 git diff 核对
【验收标准】逐条判定；独立查看实际代码，不只采信开发者结论
【开发者测试证据】<命令 + 结果摘要>
【交付物】复核结论（agree / disagree + 具体问题 + 建议），发现问题交回开发者修正后再复核
```

### 6.3 交付包 JSON 模板（partial 示例，按需替换内容）

`task_id` 换成**提交者本次的 TALK 任务号**；复核要关联的开发任务号写在 `baseline.diff_note` 等说明文字里。

```json
{
  "task_id": "38",
  "conclusion": "partial",
  "completed": ["完成本地校验脚本与针对性测试"],
  "unfinished": ["独立复核未进行，等待复核 Agent 接手"],
  "blocked": [],
  "changed_files": ["scripts/talk_workflow.py", "docs/guides/TASK_WORKFLOW.md", "tests/test_talk_workflow.py"],
  "baseline": {"ref": "aa90682", "diff_note": "只新增本地脚本、指南与测试，未改生产实现"},
  "verification": [
    {"check": "python -m unittest tests.test_talk_workflow", "result": "pass", "evidence": "全部用例通过，未联网"}
  ],
  "limitations": ["本地校验只覆盖格式与自报一致性，不代表业务验收通过"],
  "progress_draft": {"summary": "本片实现完成，等待独立复核", "next": "复核通过后由 Codex 统一 commit/push"}
}
```

写完后两条命令都要跑，并带上本次任务号：`validate ... --expect-task-id <本次任务号>` 通过、`summary ... --expect-task-id <本次任务号>` 能给出短结论。

### 6.4 短结论回复模板（聊天/TALK 只报这些）

```text
结论：complete | partial | blocked
交付包：<相对路径>（校验：通过）
已完成：<1 条>
未完成/阻塞：<1 条，没有就写“无”>
测试：<命令> → <结果一行>
```

### 6.5 派发调用约束（已实测，直接照抄）

派发**独立顶层任务**（没有父任务的单发任务）时只传最小字段：

| 参数 | 传不传 | 说明 |
| --- | --- | --- |
| `project_id` / `target_member_id` | 传 | 目标项目与执行者 |
| `title` / `content` | 传 | 任务标题与正文（正文写清范围、验收标准、交付包路径） |
| `task_kind` | **省略** | 省略即默认 `general`，不要显式传子任务类型 |
| `related_task_ids` / `trigger_task_id` | **不要传** | 留给既有质量子任务合同，本流程省略 |
| `review_policy` | **不要传** | 只用于 `development` / `rework` |

- `development` / `review` / `test` / `rework` 这几种 `task_kind` 只用于**已有明确 parent 的既有子任务合同**，独立顶层任务不要用。
- 需要复核时，单独派发一条独立顶层任务，在 `content` 里写明复核对象路径与验收标准，不要靠 `related_task_ids` 挂靠。
- 本片不实现新的服务端分支，也不猜测子任务权限；固定用上面这组最小调用即可。

## 7. 分工与收尾节奏

- 默认分工沿用 AGENTS.md：后端及本地脚本由 DeepSeek 开发、Kimi 独立复核；前端由 Kimi 开发、DeepSeek 独立复核。Codex 只做范围、摘要、分歧裁决与文档/Git 收尾。
- 开发完成即**暂停**，等独立复核，不在复核期间并行改码。
- 执行者可准备 `progress_draft`；正式进度文档仍由 Codex 维护。
- 必要验证与进度整理结束后，统一由 Codex 提交/推送，避免“边做边推、重复 push”。
- 已知权限障碍（例如推送凭据被拒）：**一次**明确报 `partial`/`blocked`，不重复试探、不申请用户级权限。
- Codex 不把原任务正文与 Hall 历史回灌上下文；需要细节时按路径按段展开交付包文件。

## 8. 常见错误与修法

| 报错字段 | 含义 | 修法 |
| --- | --- | --- |
| `conclusion: contradiction` | 结论与清单矛盾（如 complete 却有未完成项） | 改成 `partial`，或把该项移出 `unfinished` |
| `verification[i].result: contradiction` | 写了 `complete`，但同包里有 `result: "fail"` | 改报 `partial`/`blocked`，或修复后重跑该项；确实没跑的写 `not_run` |
| `task_id: unexpected_task_id` | 交付包不是 `--expect-task-id` 指定的本次任务 | 核对任务号（`38` 与 `#38` 等价），或换成本次的交付包 |
| `conclusion: bad_enum` | 写了 `succeeded`/`done` 等 | 只能写 `complete`/`partial`/`blocked` |
| `verification: too_few_items` | 没有验证记录 | 至少写 1 条，跑不了的写 `result: "not_run"` |
| `changed_files[i]: not_relative_path` | 写了绝对路径 | 改成仓库相对路径，如 `scripts/talk_workflow.py` |
| `xxx: unknown_field` | 塞了原任务/Hall/日志/runner 状态 | 删除该字段，把结论写进对应结构化字段 |
| `ERROR ... 嵌套层级过深` | JSON 嵌套太深（如几万层数组） | 交付包应是结构化短文本，不是深层嵌套数据 |
| `ERROR 文件不是合法 UTF-8` | 文件是 GBK 或二进制 | 用 `encoding="utf-8"` 重写 |
| `ERROR 交付包过大` | 超过 64 KiB | 只保留结构化字段，日志留在文件系统里 |

## 9. 限制与非目标

- 只做本地格式与自报一致性校验，不做业务正确性判断，不自动收取/accept 任务。
- `--expect-task-id` 只核对任务号字符串，不证明内容归属；防的是“旧文件 / 别的任务报告”这类明显错配。
- 派发约束只记录已实测的最小调用；本片不新增服务端分支、不猜测子任务权限。
- 密钥脱敏是启发式，覆盖不了所有形态；硬要求是不要把密钥正文写进交付包。
- 摘要上限用字符数衡量，与计费 token、模型额度无关。
- 本指南不改变 TALK 服务端、bridge、数据库与任务状态语义；这些属于后续独立切片。

- 当前入口必须由执行者/主控显式调用，尚未在 bridge 或 MCP 内自动强制执行；文件校验不能防止漏报事实，也不能保证所有调用者遵守流程。
