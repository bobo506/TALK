# Project Progress

Updated: 2026-10-08 21:49 (Asia/Shanghai)：用户授权继续通用运行器／模型绑定，指定DeepSeek开发、Codex独立验证。已派#190工程合同与后端首片方案，未改生产实现；K2.8真实接单仍延后到下次使用，名册人类同步仍待确认。

## 当前角色与协作

- 项目D:/claude-test/TALK，project_id=prj_e8fe7066bbec，分支codex/terminal-return-codex，常规推送持续授权。当前Codex为决策Agent，MCP实测agent:codex/kind=agent。
- 用户当前临时分工：DeepSeek开发、Codex独立复核；Kimi额度不足期间不派Kimi。新任务派发前仍读取最新development_requirements，任务包保留本次明确分工；默认派发后结束，由用户通知完成再收取。
- Codex负责范围、裁决、正式进度和Git，不默认操作浏览器。共享目录开发完成暂停后复核。当前切片为#190工程设计，完成后由Codex独立验证。

## 当前切片：#190通用角色运行器与模型绑定工程合同

- 用户本轮明确“可以继续，仍旧是deepseek开发，你来验证”；覆盖项目一般交叉复核安排的本次分工。已读取最新development_requirements，项目仍passive/version6，caller=agent:codex/kind=agent；不派Kimi。
- #190已派agent:deepseek，created_by=agent:codex，创建时queued/assigned，Hall=group:task-5091b385bd2040b2aa652fa3e1e711b9。此为任务创建状态，不代表已领取或交付。默认派发后结束，用户通知完成再取件。
- 本片先核查实际代码、形成可审合同与后端首片实施方案。绑定包括runtime、来源builtin/custom_api、provider/connection引用、model与展示名；明确项目身份/权限、旧角色与数据库兼容、新任务快照原子性/不可变性、配置值与实际模型证据区分。具体字段与API尚待设计/独立验证，不宣称已实现。
- DeepSeek仅写.tmp/role-model-binding-design/草稿、无密钥样例和talk-delivery-1报告；禁止改正式代码/测试/文档/.talk配置、生产DB/角色/凭据/默认模型，禁止启动服务/运行器、调用真实模型或生产等待。Codex可聚焦维护正式进度；完成后开发暂停再验证。
- 实际基线10555ca2a54fdafa56300b999921d7831bb41518，790份tracked文件指纹在.tmp/role-model-binding-design-dispatch/source_manifest.json；任务包task_content.md、dispatch_context.json与dispatch_result.json同目录。首片合同验收后再决定后端实现，不把设计交付视为运行器适配通过。
- 下一步：收到190完成通知后用talk_get_delivery核对自身任务号和完整摘要，独立核查实际代码/合同/证据；问题交回DeepSeek修正。通过后收取、发布已审合同/拆片计划并完成文档Git收尾。K2.8真实接单延期继续有效。

## 已完成与当前状态

- #187/msg2689入口开发、#188/msg2690与#189/msg2691补正，经Codex独立82项测试（0跳过）、六项启动边界及冻结文件核验通过，已189→188→187验收收取。入口代码与指南提交a4757c3，接入准备提交abab3cb，均已推送；原失败/开发报告保留。
- 新成员agent:kimi-code-k28-preview已POST注册201，独立Key的GET /api/members/me确认kind=agent。Key在C:/Users/Administrator/.talk/agent-kimi-code-k28-preview.key，随机生成并限制ACL；Key明文不入仓库、聊天、日志或命令参数。
- 本地groups.yaml和独立profile=.talk/agents/agent_kimi-code-k28-preview/{IDENTITY,SOUL,USER}.md已准备dev/execution；scan_agents共4条，原三条字段保持。服务端项目名册最后实测仍codex/deepseek/kimi三条：agent:codex同步请求HTTP403，需要人类身份。未收到人类同步成功确认，不把名册已配置/在线/验收通过作为既定事实。
- check --require-key与launch --dry-run已通过；在线check唯一失败为新成员未入册。原native K3默认值、Codex入口与既有profile共15文件SHA保持。运行器尚未启动，真实模型/claim→执行→结果→complete→收取闭环未验；用户已明确延后到下次使用。

## 下次使用K2.8时

1. 先确认人类名册同步是否完成；完整保留原角色的准备包和说明在.tmp/kimi-k28-executor-application/。人类本地应用命令：`.\.venv\Scripts\python.exe -X utf8 .tmp/kimi-k28-executor-application/apply_roster.py`，终端getpass输入已有本人human Key。脚本核身份、包hash和当前完整名册基线，漂移停止；已验证agent身份仅1GET/0POST并拒绝。
2. 名册同步后，再运行只读`check --require-key --online-identity`。通过后启动下方入口，额度允许时安排最小读文件任务，记录真实模型版本、耗时与额度。当前没有执行这些后续步骤。
3. 用户要求保留K2.8启动命令；PowerShell先进入项目目录，TALK后端需已运行：

```powershell
cd D:\claude-test\TALK
.\.venv\Scripts\python.exe -X utf8 scripts\kimi_k28_executor.py launch
```

入口自动读取本人外置Key，固定alias=kimi-code/kimi-for-coding，runtime=kimi-code、model_source=builtin、provider=managed:kimi-code、connection_ref=native-kimi-code-managed-login、backend=kimi-for-coding，dev/execution。展示K2.8 Preview，alias滚动升级、不承诺永久后端版本；停止Ctrl+C。K3原生default_model仍kimi-code/k3。正式指南docs/guides/KIMI_K28_EXECUTOR.md。

## 后续计划与边界

- 共5组合8方向：Codex仅分配；WorkBuddy＋K3、DSH＋DeepSeek Flash、Kimi Code＋K3各分配/执行；Kimi Code＋K2.8仅执行。WorkBuddy90/91仅历史分配侧，未证明其执行能力或当前可派成员。
- 通用角色绑定runtime/model_source(builtin/custom_api)/provider_id/connection_ref/model_id/展示名和新任务快照已进入#190工程合同设计，尚未开发到数据库/API/UI；身份、职责、决策分级独立。相同运行器复用适配，模型与连接分别核验；用户API凭据不进入角色名或任务快照。
- Codex被动I-0 #178/#179已验，I-1/I-2用户页面验收通过；I-3A #180/#181、I-3B #182/#183/#184、I-3C #185/#186已通过收取发布，I-3文档同步闭合（规格提交d474321）。I-3B最新MCP说明运行进程重载未核，真实主动I-4/G8/正常到期/取消/同连接排队未验。
- 项目passive/version6、effective=null/not_bound；controller_assignment=agent:codex/version13仅历史兼容，不赋权或自动唤回会话。175-O1测试维护、Schema maximum=600/clamp评估另片。
- 超时分别核验：CodexW300用户现用；DeepSeek桌面T65/W50/余量15；Kimi660000ms仅模板，实际T未知，不启用主动长等待。bridge执行预算3600秒、身份GET单次15秒，独立于宿主工具/发起者等待预算。真实质量、速度与成本优势未测。

## 恢复依据

- 正式历史docs/PROGRESS_HISTORY.md；最终代码审查.tmp/kimi-k28-executor-final-review/，任务收取.tmp/kimi-k28-executor-receipt/acceptance.json；本次应用.tmp/kimi-k28-executor-application/application.json、final-verification.json、application-helper-verification.json与README.md。
- .tmp应用包与回执为本机忽略文件；外置Key不随Git复制。Codex身份回退备份C:/Users/Administrator/.codex/backups/talk-identity-20261007T091123256850Z/config.toml。前次usage-gate在UTC13:16为continue（session19%/weekly23%），本轮UTC13:44 usage-gate实测continue（session29%/weekly24%），仅当时采样。

恢复指令：继续项目。先恢复#190当前状态；用户通知完成后按本次DeepSeek开发／Codex独立验证分工取件。K2.8验证仍延后到下次使用，不能把任务创建或设计交付视为真实接入验收通过。
