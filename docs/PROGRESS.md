# Project Progress

Updated: 2026-10-09 09:55 (Asia/Shanghai)：K2.8最小任务#195领取/固定串回传/收取通过，约17秒领取、26秒完成；未改业务文件。实际模型版本/开发能力/主动等待仍待验。B1a人工API门禁及B1b未派保持。

## 当前角色与协作

- 项目D:/claude-test/TALK，project_id=prj_e8fe7066bbec，分支codex/terminal-return-codex，常规推送持续授权。当前Codex为决策Agent，MCP实测agent:codex/kind=agent。
- 用户当前临时分工：DeepSeek开发、Codex独立复核；Kimi额度不足期间不派Kimi。新任务派发前仍读取最新development_requirements，任务包保留本次明确分工；默认派发后结束，由用户通知完成再收取。
- Codex负责范围、裁决、正式进度和Git，不默认操作浏览器。共享目录开发完成暂停后复核。本轮#193/#194开发已暂停，Codex独立复核通过；用户授权若仍失败可由Codex补修，本次无须补改代码。当前等待B1a人工API验收，不并行改码。

## 当前切片：B1a 已通过独立复核并收取，待人工 API 验收

- DeepSeek #193/msg2695 开发、#194/msg2696 定向修正，原始报告/失败记录保留；已按194→193收取，两项succeeded/completed。代码7文件（4改3增）：db/main/models/projects、runners路由与两份新测试；正式文档由Codex同步。
- 实现两表/幂等迁移、human写登记及角色绑定、已认证读取、GET agents附加配置/状态、原文单SQL与批量事实助手、阶梯/指纹/并发upsert。登记仅为配置事实，不改变角色身份、权限或运行器，也不调用模型。
- Codex独立实际差异审查，正常日志配置下6模块124项全部通过（55新测试，含既有文件9项），0失败/错误/跳过；原三个问题的实际助手/API隔离探针均通过：项目删除单角色/批量404、runtime不可解析派生三字段/指纹null、存储末尾换行partial/指纹null。GET/PUT/清空/sync等回归已覆盖。
- R1–R4已闭合、review approved；793份冻结源核验无缺失，复核前仅4允许源+2协调进度变化，原193 db/main/runners未改，194七文件冻结保持。SQL SHA256 a812ee474b4710f5eac29f773fb02f39dec70201c3fdd0abc66709f7b17f0f1e 与合同/计划原文逐字符一致，任务表/tasks.py/bridge/MCP/SDK/web未改。
- 194消息混排导致MCP结构化摘要unknown；完整msg2696嵌入JSON与本地development.json逐对象一致，本地validate expect194通过，原消息/报告不改。不是结构化MCP验收通过，业务结论来自独立源码与验证。
- 未重跑全量881项或24个WinError5的pristine对照；193原26个非零结果保留，不能宣称全量通过/均非回归。未重启服务、迁移生产库、启动运行器、调用真实模型或操作浏览器。空名册沿用旧读取边界，事务视图不承诺全局最新。
- K2.8最小任务证据.tmp/kimi-k28-receipt-smoke/：dispatch、delivery-195、review和acceptance；单次显式30秒观察立即命中submitted（1轮/1GET），未启controlled_wait或改passive。
- 独立证据与收取回执.tmp/runner-role-binding-b1a-fix-review/；原193冻结与审查.tmp/runner-role-binding-b1a-review/，194交付备份delivery-194/，两个任务包/原报告均保持。本机忽略文件不随Git发行。
- [人工API验收](guides/ROLE_MODEL_BINDING_ACCEPTANCE.md)：重启加载新后端，使用本人human Key和测试项目/角色，经/api/runners与binding端点验证登记→绑定→改名→retired→清空及权限。代码通过不代表生产已加载；本轮暂停B1a，不派B1b。

## 已完成与当前状态

- 运行器/模型角色绑定设计#190/msg2692、#191/msg2693、#192/msg2694已独立通过并收取，正式合同/实施计划/样例752ea1e已推送；14状态/27列/1SQL、11快照13键/指纹、790源保护与WAL已有事务视图证据通过。原失败/草稿/报告保持，实际证据B2后置。本次A19纯文档笔误澄清不改变已审设计。
- #187/msg2689入口开发、#188/msg2690与#189/msg2691补正，经Codex独立82项测试（0跳过）、六项启动边界及冻结文件核验通过，已189→188→187验收收取。入口代码与指南提交a4757c3，接入准备提交abab3cb，均已推送；原失败/开发报告保留。
- 新成员agent:kimi-code-k28-preview已POST注册201，独立Key的GET /api/members/me确认kind=agent。Key在C:/Users/Administrator/.talk/agent-kimi-code-k28-preview.key，随机生成并限制ACL；Key明文不入仓库、聊天、日志或命令参数。
- 本地groups.yaml和独立profile=.talk/agents/agent_kimi-code-k28-preview/{IDENTITY,SOUL,USER}.md已准备dev/execution；scan_agents共4条，原三条字段保持。2026-10-09人类同步已完成，apply_roster回执human_sync_verified/project_roster_applied均true；MCP实测名册codex/deepseek/kimi/kimi-code-k28-preview四条，新角色dev/execution。原agent身份403保持历史，不修改权限。
- check --require-key与launch --dry-run已通过；在线check唯一失败为新成员未入册。原native K3默认值、Codex入口与既有profile共15文件SHA保持。用户本次已启动入口，MCP最新kimi-code实例上报idle（2026-10-09T01:46:05.488125 UTC，pid22828，current_task_id=null）；实例上报可能滞后，不能据此宣称实时心跳或实际模型。最小任务#195/msg2697由该实例attempt1领取并完成，from/claimed_by均为本人，返回K28_RECEIVED_20261009；合法自身号JSON+独立固定串/时序/来源核验后已收取，succeeded/completed。真实模型后端版本、开发能力与主动宿主T/W仍未验。

## K2.8当前使用与后续验收

1. 名册同步已完成，无需重复执行.tmp/kimi-k28-executor-application/apply_roster.py。原包、回执与只读roster-preflight-20261009.json保留；该脚本为临时human入口，不是未来添加角色产品流程。
2. 已按用户要求执行一次无工具/无文件修改的最小收件回传#195，claim约17.235秒、总25.915秒，结果已收取。下一步如用户要求，可再验只读文件/小型开发任务及实际模型/成本；本轮不自动继续派任务。
3. 用户要求保留K2.8启动命令；PowerShell先进入项目目录，TALK后端需已运行：

```powershell
cd D:\claude-test\TALK
.\.venv\Scripts\python.exe -X utf8 scripts\kimi_k28_executor.py launch
```

入口自动读取本人外置Key，固定alias=kimi-code/kimi-for-coding，runtime=kimi-code、model_source=builtin、provider=managed:kimi-code、connection_ref=native-kimi-code-managed-login、backend=kimi-for-coding，dev/execution。展示K2.8 Preview，alias滚动升级、不承诺永久后端版本；停止Ctrl+C。K3原生default_model仍kimi-code/k3。正式指南docs/guides/KIMI_K28_EXECUTOR.md。

## 后续计划与边界

- 共5组合8方向：Codex仅分配；WorkBuddy＋K3、DSH＋DeepSeek Flash、Kimi Code＋K3各分配/执行；Kimi Code＋K2.8仅执行。WorkBuddy90/91仅历史分配侧，未证明其执行能力或当前可派成员。
- 通用角色绑定runtime/model_source(builtin/custom_api)/provider_id/connection_ref/model_id/展示名和新任务快照设计已由#190–#192复核发布，B1a数据库/API代码已独立验收并收取，待人工API验收和生产加载；B1b任务快照/MCP/UI仍后置；身份、职责、决策分级独立。相同运行器复用适配，模型与连接分别核验；用户API凭据不进入角色名或任务快照。
- Codex被动I-0 #178/#179已验，I-1/I-2用户页面验收通过；I-3A #180/#181、I-3B #182/#183/#184、I-3C #185/#186已通过收取发布，I-3文档同步闭合（规格提交d474321）。I-3B最新MCP说明运行进程重载未核，真实主动I-4/G8/正常到期/取消/同连接排队未验。
- 项目passive/version6、effective=null/not_bound；controller_assignment=agent:codex/version13仅历史兼容，不赋权或自动唤回会话。175-O1测试维护、Schema maximum=600/clamp评估另片。
- 超时分别核验：CodexW300用户现用；DeepSeek桌面T65/W50/余量15；Kimi660000ms仅模板，实际T未知，不启用主动长等待。bridge执行预算3600秒、身份GET单次15秒，独立于宿主工具/发起者等待预算。真实质量、速度与成本优势未测。

## 恢复依据

- 正式历史docs/PROGRESS_HISTORY.md；最终代码审查.tmp/kimi-k28-executor-final-review/，任务收取.tmp/kimi-k28-executor-receipt/acceptance.json；本次应用.tmp/kimi-k28-executor-application/application.json、final-verification.json、application-helper-verification.json与README.md。
- .tmp应用包与回执为本机忽略文件；外置Key不随Git复制。Codex身份回退备份C:/Users/Administrator/.codex/backups/talk-identity-20261007T091123256850Z/config.toml。历史usage采样见PROGRESS_HISTORY；本轮未读取精确额度，不外推此前使用比例。

恢复指令：继续项目。先核B1a人工API验收是否完成；通过后按当前development_requirements与用户指定分工派B1b任务配置快照。K2.8名册与最小任务收件回传已核，实际模型版本/开发能力仍待验；项目内添加角色保存后自动入册与配置校验为后续已明确方向，当前尚未实现。
