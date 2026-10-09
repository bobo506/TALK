# Project Progress

Updated: 2026-10-09 08:35 (Asia/Shanghai)：#193独立116测试通过但额外探针复现3个漏测边界，未验收/收取；已派DeepSeek #194同B1a定向修正，原代码与报告冻结。K2.8真实使用继续延期。

## 当前角色与协作

- 项目D:/claude-test/TALK，project_id=prj_e8fe7066bbec，分支codex/terminal-return-codex，常规推送持续授权。当前Codex为决策Agent，MCP实测agent:codex/kind=agent。
- 用户当前临时分工：DeepSeek开发、Codex独立复核；Kimi额度不足期间不派Kimi。新任务派发前仍读取最新development_requirements，任务包保留本次明确分工；默认派发后结束，由用户通知完成再收取。
- Codex负责范围、裁决、正式进度和Git，不默认操作浏览器。共享目录开发完成暂停后复核。当前#193待#194同B1a定向修正；DeepSeek开发暂停后Codex独立复核，协调方只维护进度，不并行改业务代码。

## 当前切片：#193未通过独立复核，#194定向修正已派发

- #193/msg2695为合法自身号一致complete自报，succeeded/submitted，未收取；实际7文件在约定范围，4改3增，功能代码未提交。新登记/绑定API、单角色原文SQL/批量助手/状态阶梯/迁移候选已实现，但独立验收尚未通过，不进入B1b。
- Codex独立读实际模型/接口/校验/SQL/迁移和测试，6模块116项0失败/0错误/0跳过（含47新测试、既有项目/角色说明/开发要求和test_files9）。未用全局logging.disable，未重跑全量881或24环境失败pristine对照，不能宣称全量通过或均非回归。
- R1[P2]：在前置项目检查后、事实SQL前另一连接删除项目，单角色GET仍200/binding_state=null，GET agents仍200/[null,null]。API应以最终project_exists映射404，不靠先前ORM缓存；成功项目状态不可null，单角色/批量/PUT读回需统一，事实助手不固化HTTP错误、任务原400保持。
- R2[P2]：登记runtime为空时真实GET状态runner_missing/指纹null，但runtime空字符串、display为旧名、status=adapted；合同要求三派生字段均null。统一输出可解析性，覆盖空/全空白/登记缺失及单角色/批量，不写回存储或因身份优先误遮蔽可解析值。
- R3[P2]：正则$允许末尾换行前匹配，真实存储model_id含末尾换行被当安全token，GET bound且指纹非null。应全串匹配，必填字段非法=>partial/指纹null，runner slug同类检查；API归一化与五必填/可选字段边界不变。
- R4[P2]：原193报告把881例非零结果标pass（24 WinError5+2测试入口日志伪失败，无pristine对照）；原文保留，不追改。新交付如实记录自身验证和原全量限制，不跑就not_run，不能替全量下已通过/全部非回归结论。
- 原193源码/测试7文件冻结.tmp/runner-role-binding-b1a-review/original-193/，全部交付备份delivery-193/；review.json、independent-tests.json/.log、independent-edge-probe-results.json/probe_edges.py、scope-check.json供定向复验。793源核验仅4允许源码+2协调方进度变化、无缺失；diff-check通过，原任务/bridge/web/SDK等保持。
- #194已派agent:deepseek，created_by=agent:codex，创建时queued/assigned，Hall=group:task-08c7886fea2e4b66b3650964b1f5ca0f。派前重读最新development_requirements/caller=agent:codex/kind=agent/passive6；用户本次DeepSeek开发/Codex验证覆盖常规交叉审查，不派Kimi。实际后续状态以工具查询为准。
- #194默认只动models/projects与两份新test中的必要回归；不改原193 db/main/runners，不扩B1a，不改任务表/快照/tasks.py/bridge/MCP/SDK/web/正式文档/.talk/Key/生产数据。报告只写.tmp/runner-role-binding-b1a-fix/自身194完整合法JSON；完成暂停不提交/推送。原193冻结与review只读，派发包/快照/回执.tmp/runner-role-binding-b1a-fix-dispatch/。
- 下一步：默认派后结束，用户通知194完成后取完整摘要，独立核R1–R4的修正diff/交错回归/输出布局/全串匹配和真实测试，原报告与范围保护；通过才194→193收取、同步正式文档/进度并统一提交功能。B1b须B1a独立验收后另派；K2.8真实使用继续延期。

## 已完成与当前状态

- 运行器/模型角色绑定设计#190/msg2692、#191/msg2693、#192/msg2694已独立通过并收取，正式合同/实施计划/样例752ea1e已推送；14状态/27列/1SQL、11快照13键/指纹、790源保护与WAL已有事务视图证据通过。原失败/草稿/报告保持，实际证据B2后置。本次A19纯文档笔误澄清不改变已审设计。
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
- 通用角色绑定runtime/model_source(builtin/custom_api)/provider_id/connection_ref/model_id/展示名和新任务快照设计已由#190–#192复核发布，当前#193经审查待#194修正；尚未验收数据库/API实现，任务快照/UI仍后置；身份、职责、决策分级独立。相同运行器复用适配，模型与连接分别核验；用户API凭据不进入角色名或任务快照。
- Codex被动I-0 #178/#179已验，I-1/I-2用户页面验收通过；I-3A #180/#181、I-3B #182/#183/#184、I-3C #185/#186已通过收取发布，I-3文档同步闭合（规格提交d474321）。I-3B最新MCP说明运行进程重载未核，真实主动I-4/G8/正常到期/取消/同连接排队未验。
- 项目passive/version6、effective=null/not_bound；controller_assignment=agent:codex/version13仅历史兼容，不赋权或自动唤回会话。175-O1测试维护、Schema maximum=600/clamp评估另片。
- 超时分别核验：CodexW300用户现用；DeepSeek桌面T65/W50/余量15；Kimi660000ms仅模板，实际T未知，不启用主动长等待。bridge执行预算3600秒、身份GET单次15秒，独立于宿主工具/发起者等待预算。真实质量、速度与成本优势未测。

## 恢复依据

- 正式历史docs/PROGRESS_HISTORY.md；最终代码审查.tmp/kimi-k28-executor-final-review/，任务收取.tmp/kimi-k28-executor-receipt/acceptance.json；本次应用.tmp/kimi-k28-executor-application/application.json、final-verification.json、application-helper-verification.json与README.md。
- .tmp应用包与回执为本机忽略文件；外置Key不随Git复制。Codex身份回退备份C:/Users/Administrator/.codex/backups/talk-identity-20261007T091123256850Z/config.toml。前次usage-gate在UTC13:16为continue（session19%/weekly23%），本轮UTC13:44 usage-gate实测continue（session29%/weekly24%），仅当时采样。

恢复指令：继续项目。先恢复#190/#191/#192当前状态；用户通知192完成后按本次DeepSeek开发／Codex独立验证分工取件。K2.8验证仍延后到下次使用，不能把任务创建或设计交付视为真实接入验收通过。
