# WorkBuddy内置引擎独立CLI会话适配

2026-10-22 20:20，代码、自检与生产短任务闭环完成，待人工里程碑确认。用户先批准补齐WorkBuddy，再明确选择“允许以内置引擎作为独立运行器接入”。本片由当前Codex直接实现、调试和自检，不称独立复核。产品提交`9ac1dbf`，原开发基线`bbfd7fe`。

## 范围与入口

- 本机WorkBuddy桌面5.8.3包含官方CodeBuddy Code 2.161.0 lite产物。本片运行该引擎作为独立CLI运行器`workbuddy`，不等同控制桌面任务窗口；桌面MCP历史验收不替代本片证据。
- 实际配方为原WorkBuddy.exe加包内`cli/bin/codebuddy`，显式`ELECTRON_RUN_AS_NODE=1`、`CODEBUDDY_FORCE_LITE_WB_BUNDLE=1`。只接受精确2.161.0；普通Node/缺省bundle首次help失败原证据保留，不改安装包或升级。
- `workbuddy_bridge.py`生成本地受控命令；讨论/预检无工具，正式任务保留默认权限与内置工具，不绕过审批。当前配置显式空MCP，禁用后台任务，设置来源固定，项目模型覆盖及继承模型重定向拒绝。
- `CODEBUDDY_CONFIG_DIR`为角色独立存储，`WORKBUDDY_CONFIG_DIR`只引用原模型目录；不复制模型Key或原桌面会话。原`agent:workbuddy`身份/Key复用，当前桌面模型`kimi-k3`对应独立CLI精确alias `custom-local:kimi-k3`。新增项目角色/运行器事实不改原五角色的模型、绑定或权限。

## 会话、送达与指标

- 首轮预留尝试后传明确新UUID；续轮只按原生ID `--resume`，不用“最近会话”。API/MCP/SDK基础合同、普通领取前预检和正式runtime分派均接线；首轮完整、续轮增量、新窗恢复使用同一规划内核。
- stdout的`--replay-user-messages`回执与原生JSONL必须同用户ID、conversationRequestId及正文SHA。自己的proof文件只保存这些最小事实、配置指纹与原生容量；不保存正文/助手答复或凭据。未知送达不重跑，已证实送达后的失败/取消仍计数并停用旧窗口。
- 计数只认原生`startsNewUserRequest=true`的正式输入；工具、提醒和预检不计。自身持久proof、原生磁盘cut、workspace/session/model及新旧指纹逐次核对；重复尝试、额外写入、未来时间、身份或配置漂移拒绝续用。
- 占用取最新原生assistant `providerData.usage.totalTokens`，不使用跨轮累计成本；容量取精确模型`maxInputTokens`并与原生result的`modelUsage.contextWindow`核对，不把maxOutputTokens当容量。非法/冲突不走缺数兜底，恢复指标不清零。
- 60%与条件十次复用现有规划/计数/store事务：可靠低占用可超过十次；仅单纯缺数且完整可信计数时第10可发、第11新窗。

## 宿主与预算

新增`workbuddy_role_host.py`为单项目/单成员窄入口，缺省dry-run，`--apply`及原human/角色Key路径、精确runtime验证与原成员显示名须显式提供。只消费普通start/stop动作，持有原Popen，不采用PID接管、所有权恢复或自动重启。drain期间只处理本成员stop，空handles后正常退出。

外层默认执行预算21600秒已通过真实parser校验；取消/超时只清理本次进程树，Windows taskkill和退出等待各10秒。CLI当前没有配置MCP工具，未启用其主动等待；引擎源码默认MCP工具超时3600000毫秒只是源码事实，不当作实际宿主验收。TALK发起侧仍沿现有Codex入口，不新增长等待或自动唤回。终端实际T/W/余量/取消与同连接排队要求继续按[终端指南](../guides/TERMINAL_MCP.md)执行，不据工具可发现声称等待适配通过。

## 自检证据

- 联合相关Python **403项全部通过**，包括WorkBuddy原生格式/双证明/来源和权限隔离、计数/取消/重复，API/MCP/普通领取及宿主，以及DSH/Codex/Kimi与原角色服务回归。日志`.tmp/execution-session-workbuddy-v1/tests-final.txt`。
- 安装版引擎配本机假模型**16轮正式输入、17次本地模型请求**通过：同ID1→2/增量回想、force_new完整基础恢复、5900/10000续用、6000/10000后下一轮新ID，以及受控隐藏指标连续第1..10同ID、第11新ID/计数1。正式输入记录共16，非正式模型请求不算投递轮数；不消耗真实模型额度。
- 原生证据`.tmp/execution-session-workbuddy-v1/native-integration/b77bf085/`含逐轮结果、请求与原生格式审计。native组同窗`8c3190cd-b4dc-4a75-bca8-26f1f823ca46`；缺数组第1..10为`bda2cb66-02e3-4410-944a-025e4c0cca3f`，第11为`6434c3c8-fd63-44dc-abd3-4edb39069b20`。
- 最初部分辅助测试误用方法名/SQLite连接未显式关闭已修；MCP旧1500字符总长度断言在移除新配方后仍复现1523。改为实例摘要严格300字符和总响应2000字符，并保留单实例/字段/无历史日志校验，未改MCP产品输出；原失败日志保留。

## 生产闭环与最终状态

复用原`agent:workbuddy`身份和Key，保留其全局名称“WorkBuddy接入验证”。原项目没有该成员，现只新增本成员身份档、项目名册、imported角色、独立CLI运行器`runner:workbuddy-embedded-cli`及模型选择`rmc_150e9866f272`/精确绑定；不生成新Key。名册按原五成员完整快照追加，原五成员业务字段保持，同步产生的时间戳正常更新。首次补录422后保留已成功登记的事实，只补未完成绑定；新角色正常`not_started`状态修正了临时验收脚本的`stopped`假设，没有修改产品或重建角色。

原API使用原启动器正常加载：child10600→21996，launcher22340；没有停止原角色或解除所有权。新窄宿主manager4708按普通start得到generation1、instance `ins_be5cf2fc8b12`。原human:bobo创建并收取以下三条`general`短文本任务，WorkBuddy不开发、不执行工具或文件操作：

| 任务 | 原生session | 计数 | 答复 | 真实占用/容量 |
| --- | --- | --- | --- | --- |
| 309 | `21ca2f60-7439-47da-82b8-a5a4c3d72fa7` | 1 | 已记住 | 31606/1000000 |
| 310 | 同309 | 2 | 青禾42 / 鹿鸣57 | 32039/1000000 |
| 311 | `600b5ced-5e22-4db8-838e-62561b15733b` | 1 | 鹿鸣57 | 31603/1000000 |

三条均`succeeded/completed`并已收取，结果消息2936—2938。310正式输入没有重发暗号或基础标记，指令2523→1192字节；311的`force_new`恢复基础、指令2512字节。原生磁盘/proof/sidecar投递正文SHA及用户ID/请求ID逐条一致；正式输入3、助手记录3、无工具，三个尝试均confirmed/计数成功，通道0。独立原生HOME为`C:\Users\Administrator\.talk\role-service-host\native\prj_e8fe7066bbec\agent_workbuddy\.codebuddy`；必要预检使用独立进程，不计入这三个正式输入。真实模型均低占用，60%/缺数10→11仍依据上节受控验证，不冒称真实长上下文压力测试。

验后普通stop至generation2，角色`stopped`、无owner、可再次启动，manager空handles后正常drain退出；运行器仅在最终核对通过后标为`adapted`。308条原任务逐行SHA、286全文/暂停、原五服务行/绑定、原配置、角色Key文件mtime、WorkBuddy原models/settings/mcp文件SHA及mtime保持；只有309—311三条新增任务。没有所有权恢复、强杀、模型降级、原Key/登录/权限变更，原WorkBuddy桌面进程未启停。完整回执见`.tmp/execution-session-workbuddy-v1/production/`，含`native-audit.json`、`final-verification.json`和普通启停/drain证据。

## 使用与边界

### 23:10用户新角色补验

用户页面新建`workbuddy-k3`的运行器/模型选择正确，原创建意图仅requested、没有worker领取。本会话经正式worker只处理该意图，生成`agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314`及其独立Key/档案，精确绑定预检通过，provisioned。页面已有gen1/start未领取即过期，原失败保留；窄manager17772运行后普通start到gen2/ins_4501cac619eb、bridge19324，未恢复所有权或绕过守卫。

当前agent:codex经真实MCP派发并收取312—314：312→313同session `48d38738-4bf9-430f-830c-cce299e309e9`/计数1→2，增量仍回想“白鹭28 / 云杉64”；314新session `2880f855-925f-48df-b406-07dd33a9ba09`恢复“云杉64”/计数1。三条succeeded/completed，消息2939/2940/2944已收取；用量32101/32576/32128、容量1000000，未开发/工具调用。原生/proof/投递双ID/SHA一致，3confirmed尝试、通道0；311条原任务、原六角色/服务/绑定、配置/286和模型源保持，33份产物及18915份本角色独立HOME文件精确凭据匹配0。完整证据`.tmp/workbuddy-new-role-validation/`。

新角色及窄宿主保留running/ready/idle，便于用户继续使用。原“WorkBuddy接入验证”仍停止；以下手动启动说明适用于停止角色。配置worker未常驻、宿主随TALK统一启动仍待另片确认，本次手动处理原请求没有修复该部署缺口。源码没有变更，403项自检沿用，新增三条实机验证不叠加单测数量。

TALK页面不改，首轮/增量/换窗参数见[使用说明](../guides/EXECUTION_SESSION_USAGE.md)。原`agent:workbuddy`接入验证角色当前停止，手动启用时先启动已验证的窄宿主，再使用普通角色启动入口；新“workbuddy-k3”则按上节保持运行。不由页面绕过宿主所有权，也不自动恢复旧归属。本片四类运行器接线范围已覆盖DSH、Codex、Kimi Code及用户批准形态的WorkBuddy内置独立CLI，人工里程碑仍待用户确认；不外推其它版本/模型、另一K2.8成员独立HOME、桌面GUI控制或主动MCP长等待。宿主统一启动仍是另片，须先获确认。

一次诊断误将原models数组完整输出，导致两项Key进入本次工具日志，已告知用户。随后改固定字段白名单；最初50份、生产验后205份本片产物精确扫描均未含凭据正文，未擅自换Key。中断恢复后22:39最终综合复查通过：18份正式文件、209份本片产物、5444份独立原生HOME文件原值匹配0，本次原生writer进程0，新增链接/编码通过，回执`production/final-artifact-check.json`。先前历史绝对路径断言及工作区额度审批失败留存，审批恢复后正规重跑成功。不可复述原输出、复制含密钥原配置或提交凭据；此为实际诊断失误，不冒称工具日志已被撤回。

接口参考：[官方headless](https://www.codebuddy.ai/docs/cli/headless)、[CLI参考](https://www.codebuddy.ai/docs/cli/cli-reference)；具体兼容性以本机安装版源码/实际CLI证据为准。桌面方案核查参考[WorkBuddy任务对话](https://www.workbuddy.cn/docs/workbuddy/Conversation)和[Open API](https://open.workbuddy.cn/docs/openapi)，不把云任务或本地助理单消息接口当作桌面窗口控制能力。
