# Project Progress

Updated: 2026-10-09 11:03 (Asia/Shanghai)：#196 B1b独立177项及并发/回滚/原文不可变探针通过，已收取succeeded/completed；正式规格和API验收同步，统一Git收尾。B2/B3/B4未派。

## 当前角色与协作

- 项目D:/claude-test/TALK，project_id=prj_e8fe7066bbec，分支codex/terminal-return-codex，常规推送持续授权。当前Codex为决策Agent，MCP实测agent:codex/kind=agent。
- 用户当前临时分工：DeepSeek开发、Codex独立复核；Kimi额度不足期间不派Kimi。新任务派发前仍读取最新development_requirements，任务包保留本次明确分工；默认派发后结束，由用户通知完成再收取。
- Codex负责范围、裁决、正式进度和Git，不默认操作浏览器。共享目录开发完成暂停后复核。本轮#193/#194开发已暂停，Codex独立复核通过；用户授权若仍失败可由Codex补修，本次无须补改代码。用户本次继续指令允许进入B1b，人工API逐项步骤仍无已测报告；#196开发暂停后Codex独立复核通过并收取；本轮无Codex业务代码补修。

## 当前切片：B1b #196已复核通过并收取，待API人工验收

- DeepSeek #196/msg2698纯JSON合法自身196一致complete，完整10字段与本地报告逐对象一致、validate通过；Codex实读实际diff/关键断言并独立验证，已收取succeeded/completed。代码3改1增：models/db/tasks、新test_task_binding_snapshot；旧test_tasks保持。
- 新任务两列/13键在_create_task_with_hall开头统一构造，复用B1a事实/阶梯/指纹，普通/子/schedule均覆盖，无项目no_project；旧NULL不回填，客户端不能写，原权限/错误码/事务边界保持。
- 独立7模块177项0失败/错误/跳过，正常日志；WAL双线程100提交/400快照（one198/two202）无撕裂，最终事实前删项目400无任务/Hall，真实关系唯一冲突409同次回滚且不mock commit。
- 子授权事务内预扣1，快照失败400后0、父快照不变，无子任务/Hall；SQLite JSON原文直接比较，claim/heartbeat/到期重排/重领/改绑定/complete/cancel均原文字节和状态保持。首轮探针误用human遭原403拒绝，改目标agent后通过，非产品修正。
- 797源核验无缺失/越界，审查期间4代码/测试冻结保持；SQL hash a812ee474b4710f5eac29f773fb02f39dec70201c3fdd0abc66709f7b17f0f1e不变。原报告/失败历史不追改；.tmp/runner-role-binding-b1b-review/保存original-196、delivery-196、独立tests/edges/raw-lifecycle/scope/review/acceptance，approved/0 open。
- 未重载生产服务、执行生产迁移、读凭据、调用模型或操作浏览器；881/pristine未重跑，不宣称全仓回归通过。正式规格与[快照API人工验收](guides/TASK_BINDING_SNAPSHOT_ACCEPTANCE.md)同步：加载后核旧NULL、新13键、改绑定只影响新任务及生命周期不变；人工步骤仍未自报已测，B2/B3/B4另片，本轮收尾后暂停。

## 已完成与当前状态

- B1a #193/#194经Codex独立124项测试及原失败边界复验通过，已194→193收取、2dd2ec7推送；两表/登记绑定API、单SQL事实读取及阶梯已实现。原26个全量非零/报告保持；881及pristine未重跑，不宣称全量通过。194混排原JSON与合法本地报告一致，MCP结构化unknown保持；证据.tmp/runner-role-binding-b1a-fix-review/。人工API逐项测试未由用户报告，本次继续授权进入B1b。
- K2.8 #195最小无工具回传由本人instance领取、17.235秒claim/25.915秒总完成，固定串K28_RECEIVED_20261009正确，msg2697合法195一致，已收取succeeded/completed；.tmp/kimi-k28-receipt-smoke/保存证据。实际后端版本/开发能力/主动等待仍待验。
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

恢复指令：继续项目。#196已独立复核收取；先核B1a/B1b人工API验收或新的明确继续授权，再按最新要求定B3工具/角色添加/实际证据设计的下一明确片。K2.8最小回传已通过，不扩大为实际模型版本/开发能力或主动适配验收。
