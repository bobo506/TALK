# TALK 使用流程：固定交付包、本地校验与只读交付摘要

本指南覆盖项目本地的交付流程：交付时写一份固定结构的 JSON 交付包，用本地脚本做机械校验，
聊天/TALK 回复只报短结论和文件路径；另外说明本片新增的 MCP 只读交付摘要工具
`talk_get_delivery`（有界摘要 + 可追溯按需补读）。

配套脚本：`scripts/talk_workflow.py`（仅标准库，无需额外依赖）。
配套工具：`talk_get_delivery`（只读；不自动收取结果、不改变任务状态，第 6 节）。

## 1. 为什么这样做

| 旧痛点 | 现在的做法 |
| --- | --- |
| `get_task` 与 `collect_result` 重复取全文 | 交付包固定路径 + 固定字段，取一次就够；MCP 侧用 `talk_get_delivery` 只取有界摘要 |
| runner 报 succeeded，但推送失败只能读正文才发现 | 交付结论由执行者显式声明 `complete/partial/blocked`，脚本和 MCP 摘要都拒绝把 runner 状态当结论 |
| 交付后 Codex 再拼进度、重复提交推送 | 执行者写进度草稿，Codex 只做收尾；详细证据留在交付包文件里 |
| 长报告被截断后要点丢失 | 摘要显式标注所有省略并给出补读参数，detail 模式按稳定引用分页重建全文 |

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

## 6. MCP 只读交付摘要与补读（`talk_get_delivery`）

本片在既有任务工具集里新增**一个**只读工具 `talk_get_delivery`：按 `task_id` 读取交付摘要，
并按稳定引用分页补读完整结果。既有 `talk_get_task` / `talk_collect_result` 等工具的默认合同不变；
本工具**不会**为了摘要自动 collect / accept，也不改变任何任务状态，不读本机文件。

### 6.1 三种状态必须分开看

| 字段 | 含义 | 不能当成什么 |
| --- | --- | --- |
| `runner_status.status` | `agent_tasks.status`：`queued/running/succeeded/failed/canceled` | 不是业务结论；`succeeded` 只表示 runner 已结束 |
| `runner_status.workflow_status` | 协作流转：`assigned/in_progress/submitted/completed/...` | 不是业务结论；`submitted` 只表示成果已提交 |
| `delivery_conclusion.value` | 业务结论：`complete/partial/blocked`，只认通过本地 `talk-delivery-1` 校验的结构化自报 | `invalid`/`unknown` 时不得推断完成 |

- `delivery_conclusion.trusted_source=true` 只有一个来源：结果消息正文是合法 `talk-delivery-1` JSON，
  并且通过 `scripts/talk_workflow.py` 的同一套校验；它仍然只是执行者自报，**不是独立验收证明**。
- 除此之外还必须**核对报告自身声明的任务号**：工具取任务记录自身的 `id`，与自报 `task_id` 规范化后
  比对（`38` 与 `#38` 等价，沿用 CLI 规则）；错号、缺号或无法比对一律 `value=invalid`、
  `trusted_source=false`，`delivery_conclusion.task_id_check` 会回显 `declared / expected / matches`，
  且错号报告的结构化内容不会进入 `counts` 与 `preview`。
  这只约束结构化字段与业务结论，**不影响**按 `result_message_id` 分页补读完整原文。
- 自由文本旧报告 → `value=unknown`、`source=unstructured_text`；能解析成 JSON 但校验不过 →
  `value=invalid`，并给出至多 5 条校验问题（例如 `complete` 与 `result: "fail"` 自报矛盾）。
- runner 结束**不等于**用户目标完成；结果正文里出现“完成 / complete”这类词不会被拿来猜结论。

### 6.2 summary 模式（默认）

- 返回有界摘要：`task_ref`、`runner_status`、`delivery_conclusion`、`counts`、`preview`
  （顺序固定为 阻塞 → 未完成 → 已完成）、`summary_text`、`limits`、`read_more`。
- 正常情况下 `summary_text` ≤ **1200 字符**、整个 JSON 响应 ≤ **6000 字符**；这是两个独立预算，
  `limits` 会同时给出两个实测值，**不承诺**把整份交付报告无损压进 1200 字符。
- 所有省略都显式可见：`preview.<区块>.omitted`、`read_more.omitted` 和 `summary_text` 末尾的
  `[摘要截断：...]` 都会列出被省略的字段，`counts` 始终是真实数量；收缩顺序是
  已完成 → 未完成 → 阻塞，**不会**在隐藏阻塞项的同时只报完成。
- 旧任务没有结构化报告时，摘要仍给 `unknown` 加一段带 `trusted=false` 的短预览（≤300 字符），
  并指向 `read_more` 的补读参数。

### 6.3 detail 模式（按需补读）

```json
{"task_id": 42, "mode": "detail", "result_message_id": 411, "offset": 0, "limit": 2000}
```

- `result_message_id` 必填（取自 summary 的 `runner_status.result_message_id` 或 `read_more.params`），
  它是**稳定引用**，用来防止把两份结果拼在一起。
- `offset` 从 0 开始，`limit` 默认 2000、上限 4000 字符；按 `offset` 顺序拼接各页可**无损重建**完整结果，
  每页都能核对 `page.total_chars` 与 `reference.content_sha256`，末页 `page.done=true`、`next_offset=null`。
- `fields` 可指定 `talk-delivery-1` 顶层字段（如 `blocked`、`verification`）只读结构化值；
  结果不是合法结构化自报时返回 `status=unavailable`，不会猜内容。
- 调用者补读时应保留 summary/上一页返回的完整参数，包括 `result_message_id` 与 `expect_sha256`；仅携带消息 ID 不能发现同一消息正文发生变化。
- 数据变化会**拒绝旧引用**：`result_message_id` 已改变，或 `expect_sha256` 与当前内容不一致时，
  返回 `status=stale_reference` + `reset_required=true` + `next_params`，**且不返回任何正文**；
  必须按 `next_params` 从 `offset=0` 重新开始，禁止拼接两份结果。
- 无结果引用、结果消息不可见时返回 `status=unavailable`，不会退回扫描整个 Hall 历史。
- 非法游标直接报错：`offset` 为负或超过结果长度、`limit` 越界、`fields` 含未知字段都会被拒绝。

### 6.4 怎么把结构化交付写成结果消息

执行者完成任务时，把交付包 JSON **原样作为结果消息正文**（TALK 结果消息即 `result_message_id` 指向的那条）：

```text
{"task_id":"42","conclusion":"partial","completed":["..."],"unfinished":["..."],"blocked":[],
 "changed_files":["bridges/talk_delivery.py"],
 "baseline":{"ref":"881ce12","diff_note":"只新增只读工具与测试"},
 "verification":[{"check":"python -m unittest tests.test_talk_delivery","result":"pass","evidence":"全部通过"}],
 "limitations":["..."],"progress_draft":{"summary":"...","next":"..."}}
```

- 正文整体可以套一层 ```` ```json ```` 围栏，摘要会剥掉围栏再校验；围栏之外不要混入解释文字。
- `task_id` 必须是**这份报告自身所属任务**的真实 TALK 任务号（不是被复核的开发任务号、不是
  `review-42` 这类自造标签）：工具会拿它与任务记录的实际 `id` 比对，错号即判 `invalid`/不可信。
  关联的开发/复核任务号写在 `baseline.diff_note` 等说明文字里。
- 正文必须是**完整**的 JSON 对象；字段与上限见第 3、4 节，本地校验通过的结构化自报才会被摘要认作可信来源。
- 也可以额外把同一份 JSON 写到 `.tmp/<切片>/development.json`，两条路径内容保持一致即可。

### 6.5 降级行为（不要假装旧报告已经迁移）

- 旧任务的结果消息仍是自由文本：摘要只给 `unknown` + 短预览 + 补读入口，**不会**自动改写旧消息，
  也**不会**声称旧报告已迁移成结构化交付。
- bridge 会对过长回复做截断（默认 `--max-reply-chars 12000`，截断处追加 `[truncated N chars]`）；
  被截断的交付 JSON 不再合法，摘要会判 `invalid` 或按自由文本给 `unknown`，需要重新提交完整结果；分页只能恢复服务器已保存的正文，不能恢复上传前已经缺失的部分。
- 结果正文超过 64 KiB 时按 `too_large` 处理，不按结构化自报解析，但原文仍可用 detail 模式分页补读。
- 摘要里的 `chars` 只是字符数指标，不是计费 token，也不是额度。
- 普通终端入口 `--check` 会输出 `delivery_defaults`，把上述上限、可信来源与补读合同一并打印出来。

## 7. 可复制模板

### 7.1 短任务包模板（发给执行 Agent）

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

### 7.2 审查任务包模板（发给复核 Agent）

```text
【复核对象】<交付包路径> + <变更文件清单>
【原需求】<同上，2-4 条要点>
【范围 / 不变项】<同任务包>
【实际基线 / 差异】<报告的基线> → <当前 HEAD>；用 git diff 核对
【验收标准】逐条判定；独立查看实际代码，不只采信开发者结论
【开发者测试证据】<命令 + 结果摘要>
【交付物】复核结论（agree / disagree + 具体问题 + 建议），发现问题交回开发者修正后再复核
```

### 7.3 交付包 JSON 模板（partial 示例，按需替换内容）

`task_id` 必须写**报告自身（本次提交）的 TALK 任务号**，不能写被复核/被关联的开发任务号；
复核要关联的开发任务号写在 `baseline.diff_note` 等说明文字里。复核者尤其注意：报告是你本次任务的报告，
`task_id` 不是你在复核的那个任务号，也不是 `review-42` 这类自造标签。

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

### 7.4 短结论回复模板（聊天/TALK 只报这些）

```text
结论：complete | partial | blocked
交付包：<相对路径>（校验：通过）
已完成：<1 条>
未完成/阻塞：<1 条，没有就写“无”>
测试：<命令> → <结果一行>
```

### 7.5 派发调用约束（已实测，直接照抄）

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

## 8. 分工与收尾节奏

- 默认分工沿用 AGENTS.md：后端及本地脚本由 DeepSeek 开发、Kimi 独立复核；前端由 Kimi 开发、DeepSeek 独立复核。Codex 只做范围、摘要、分歧裁决与文档/Git 收尾。
- 开发完成即**暂停**，等独立复核，不在复核期间并行改码。
- 执行者可准备 `progress_draft`；正式进度文档仍由 Codex 维护。
- 必要验证与进度整理结束后，统一由 Codex 提交/推送，避免“边做边推、重复 push”。
- 已知权限障碍（例如推送凭据被拒）：**一次**明确报 `partial`/`blocked`，不重复试探、不申请用户级权限。
- Codex 不把原任务正文与 Hall 历史回灌上下文；需要细节时按路径按段展开交付包文件。

## 9. 常见错误与修法

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

## 10. 限制与非目标

- 只做本地格式与自报一致性校验，不做业务正确性判断，不自动收取/accept 任务。
- `--expect-task-id` 只核对任务号字符串，不证明内容归属；防的是“旧文件 / 别的任务报告”这类明显错配。
- 派发约束只记录已实测的最小调用；本片不新增服务端分支、不猜测子任务权限。
- 密钥脱敏是启发式，覆盖不了所有形态；硬要求是不要把密钥正文写进交付包。
- 摘要上限用字符数衡量，与计费 token、模型额度无关。
- `talk_get_delivery` 只是**只读**入口：不 collect、不 accept、不改任务状态，也不读本机文件；
  它的可信结论只等于“结果消息里有一份通过 schema 校验且与实际任务号匹配的结构化自报”，不等于独立验收通过。
- 本指南不改变 TALK 服务端、数据库与任务状态语义；MCP 任务工具集只新增上述一个只读工具，
  既有工具输出未改。新增工具需要 MCP 客户端重连后才会出现在工具目录里，未重连前不能声称宿主已加载。

- 当前入口必须由执行者/主控显式调用，尚未在 bridge 或 MCP 内自动强制执行；文件校验不能防止漏报事实，也不能保证所有调用者遵守流程。
