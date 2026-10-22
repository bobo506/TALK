# WorkBuddy内置引擎独立CLI会话适配

2026-10-22 20:05，生产验证进行中。用户先批准补齐WorkBuddy，再明确选择“允许以内置引擎作为独立运行器接入”。本片由当前Codex直接实现、调试和自检，不称独立复核。当前代码基线`bbfd7fe`。

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

## 生产验证当前状态

原human:bobo和原agent:workbuddy Key身份核验通过；初始项目未登记该成员，独立CLI运行器未登记。308条旧任务、五角色状态/归属、原配置/绑定、286全文/暂停及WorkBuddy原models/settings/mcp已固定保护基线。只读阶段无新TALK任务、未启停既有角色；后续按本片授权补原身份项目登记和独立CLI配置，普通启停及三条短文本闭环完成后再更新本节，不能提前称生产通过。

一次诊断误将原models数组完整输出，导致两项Key进入本次工具日志，已告知用户。随后改固定字段白名单、扫描本片50份产物未含凭据正文；未擅自换Key。不可复述该输出、复制含密钥原配置或提交凭据。此为实际诊断失误，不冒称日志已被撤回。

接口参考：[官方headless](https://www.codebuddy.ai/docs/cli/headless)、[CLI参考](https://www.codebuddy.ai/docs/cli/cli-reference)；具体兼容性以本机安装版源码/实际CLI证据为准。桌面方案核查参考[WorkBuddy任务对话](https://www.workbuddy.cn/docs/workbuddy/Conversation)和[Open API](https://open.workbuddy.cn/docs/openapi)，不把云任务或本地助理单消息接口当作桌面窗口控制能力。
