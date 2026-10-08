# Project Progress

Updated: 2026-10-08 22:43 (Asia/Shanghai)：#191补正仍未独立通过；单语句无绑定分支与字段完整性经隔离实测存在缺口，已派DeepSeek #192同设计片第二次定向补正。190/191均未收取，生产实现未改，K2.8真实接单延期保持。

## 当前角色与协作

- 项目D:/claude-test/TALK，project_id=prj_e8fe7066bbec，分支codex/terminal-return-codex，常规推送持续授权。当前Codex为决策Agent，MCP实测agent:codex/kind=agent。
- 用户当前临时分工：DeepSeek开发、Codex独立复核；Kimi额度不足期间不派Kimi。新任务派发前仍读取最新development_requirements，任务包保留本次明确分工；默认派发后结束，由用户通知完成再收取。
- Codex负责范围、裁决、正式进度和Git，不默认操作浏览器。共享目录开发完成暂停后复核。当前切片为#190工程设计的#192第二次定向补正，完成后由Codex独立验证。

## 当前切片：#191补正复核仍有缺口，#192第二次定向补正

- 本次用户分工仍DeepSeek开发、Codex独立验证；已派前重读最新development_requirements，caller=agent:codex/kind=agent，项目passive/version6，不派Kimi。
- #190/msg2692、#191/msg2693都为合法自身号一致talk-delivery-1 complete自报、runner succeeded/submitted；两项均未独立验收/收取/发布。191自报11完成/0未完成/0阻塞、13产物/11验证，格式不等于业务通过。
- 191已补齐F2共用构造覆盖schedule、F3离册与身份状态阶梯、F4实际对照后置B2并约束project/task/attempt与连接证据；F5并存行/版本区分和F6凭据范围已改善。B1拆为B1a登记/绑定与B1b任务快照，两者仍待审。
- 仍需R1：合同及探针以binding行作FROM锚点，未配置角色无行时所有LEFT JOIN事实也消失。Codex直接执行原文SQL并AST提取实际probe SQL，隔离假库在入册未配置/禁用未配置/未注册未配置/human未配置四例均0行；已配置查询还遗漏来源/provider/connection/model/alias/展示名六字段。建议一行请求pair锚点联查，保留无绑定事实且全快照字段一次取得，禁止第二读或ORM缓存猜状态。
- R2：B14把runner_missing指纹写非null，须统一为runtime/fingerprint=null；alias实际传给Kimi --model，是调用选择参数，不能当纯展示；明确partial存储必填五项与派生runtime分开。历史L1-1状态不当当前已核事实，唯一入口检查只约束生产插入路径而非测试fixture。
- R3：TaskHall规则允许授权审查含脱敏标识，服务端不自动混入完整绑定；凭据禁令保持。Codex裁决首期不加read_receipt任务字段：常量计数不能证明执行SQL，无项目实际0SQL；方案版本/真实事件计数仅留隔离验证证据，避免额外schema。
- #192已派agent:deepseek，created_by=agent:codex，创建时queued/assigned，Hall=group:task-90e82a1ccf8b439e95e5244d74f82531；只写.tmp/role-model-binding-design-final-fix/新稿/样例/changes/隔离探针与自身192合法报告。禁止改原190/191稿、独立review、正式代码/测试/文档/.talk/Key/生产数据，协调方仅维护进度。
- 依据：.tmp/role-model-binding-design-fix-review/review.json、independent-probe-results.json、independent_probe.py、original-191/与original_manifest.json（13稿）；此前原190七稿/788非进度源hash通过。派发包/回执.tmp/role-model-binding-design-final-fix-dispatch/。源码基线仍10555ca，191复核时HEAD=c3ec201仅两份协调方进度变更。
- 下一步：默认派后结束，用户通知192完成后读取完整摘要，定向核R1–R3、F1–F6与原稿/源保护；通过后按192→191→190收取、发布已审合同和拆片计划并Git收尾。本次是同设计片第二次补正，不开后端片；若仍有关键缺口先汇总由用户裁决。K2.8真实接单继续延期。

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
- 通用角色绑定runtime/model_source(builtin/custom_api)/provider_id/connection_ref/model_id/展示名和新任务快照已进入#190工程合同设计/#191/#192补正，尚未开发到数据库/API/UI；身份、职责、决策分级独立。相同运行器复用适配，模型与连接分别核验；用户API凭据不进入角色名或任务快照。
- Codex被动I-0 #178/#179已验，I-1/I-2用户页面验收通过；I-3A #180/#181、I-3B #182/#183/#184、I-3C #185/#186已通过收取发布，I-3文档同步闭合（规格提交d474321）。I-3B最新MCP说明运行进程重载未核，真实主动I-4/G8/正常到期/取消/同连接排队未验。
- 项目passive/version6、effective=null/not_bound；controller_assignment=agent:codex/version13仅历史兼容，不赋权或自动唤回会话。175-O1测试维护、Schema maximum=600/clamp评估另片。
- 超时分别核验：CodexW300用户现用；DeepSeek桌面T65/W50/余量15；Kimi660000ms仅模板，实际T未知，不启用主动长等待。bridge执行预算3600秒、身份GET单次15秒，独立于宿主工具/发起者等待预算。真实质量、速度与成本优势未测。

## 恢复依据

- 正式历史docs/PROGRESS_HISTORY.md；最终代码审查.tmp/kimi-k28-executor-final-review/，任务收取.tmp/kimi-k28-executor-receipt/acceptance.json；本次应用.tmp/kimi-k28-executor-application/application.json、final-verification.json、application-helper-verification.json与README.md。
- .tmp应用包与回执为本机忽略文件；外置Key不随Git复制。Codex身份回退备份C:/Users/Administrator/.codex/backups/talk-identity-20261007T091123256850Z/config.toml。前次usage-gate在UTC13:16为continue（session19%/weekly23%），本轮UTC13:44 usage-gate实测continue（session29%/weekly24%），仅当时采样。

恢复指令：继续项目。先恢复#190/#191/#192当前状态；用户通知192完成后按本次DeepSeek开发／Codex独立验证分工取件。K2.8验证仍延后到下次使用，不能把任务创建或设计交付视为真实接入验收通过。
