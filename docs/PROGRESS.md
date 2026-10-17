# Project Progress

Updated: 2026-10-17 16:41（Asia/Shanghai）。用户继续后恢复盘点发现新Kimi回评收件人错误（message2816、非264任务），先派DeepSeek 265定位/必要最小补正，交付暂停后Codex复核直接修正。两K2.8已有迁移/264与人工验收保持，当前错误原因和循环健康待核；agent:kimi迁移暂后排。默认派后结束，用户通知265完成取件。

## 当前身份与分工

- 项目prj_e8fe7066bbec，MCP实际caller agent:codex/kind agent；当前协调、独立复核和正式docs/Git收尾由Codex负责。用户最新分工优先：DeepSeek首次实现/测试后暂停，Codex复核并直接修正、自检；不往返返修或默认追加回审。
- 默认派后结束、用户通知后取件，共享目录一次一方改码；Codex不操作Browser。DeepSeek263已收取，当前265首次执行中，原服务保留，迁移其自身最后才正常退旧入口。

## 当前265：回评收件人异常定位与最小补正已派

- 用户继续后原计划迁agent:kimi；恢复MCP实际caller agent:codex/kind agent、业务lead，最新项目要求仍旧页面分工，按用户已确认DeepSeek首次执行/Codex复核修正约定。DeepSeek最新idle/current_task=null仅为上报，不把旧心跳当真实健康证明。
- 新已迁移角色ins_b587917b65ec/PID11056于UTC08:33:52.158658上报error/current_task_id=2816/last_error=invalid recipient mention: @human:user。2816是Codex的264复核留言消息号，不是新任务；264原结果/接单及人类页面验收仍通过，原件不追改。本轮尚不能判定错误来自模型/提示/bridge何处，也未证队列已死或服务异常退出，不能只据error自动重启/清状态。
- 265已派agent:deepseek，UTC08:40:21.205497，Hall group:task-c1e0557f3e7f46b68fc90d7408f4bd40，queued/assigned为创建快照。先用隔离fake CLI/TALK定位真实消息路径、单条异常后循环健康；仅证据明确/语义清晰时最小修正，否则给复现和具体候选建议，不为消error硬改语义。
- 开发仅可改bridges/cli_bridge.py、bridges/kimi_bridge.py、tests/test_cli_bridge.py、tests/test_kimi_bridge.py，新增材料只在.tmp/legacy-role-page-control/kimi-reply-recipient/developer/；正式5协调docs由Codex维护。server/SDK/页面/配置/三档/已验收原件只读，不能放宽未知收件人400、猜人类/广播/吞错假报成功，正常Task Hall/合法mention/取消/停止和后续任务不能退化。若需扩围先交具体原因，不越界。
- 准备/开发禁止生产写/SQL状态修复、服务启停/强停/接管、真实模型/登录/native写、新Key/绑定/共享能力或新任务回评；保两K2.8现有进程/原manager/API，DeepSeek与Codex最后。完整日志体系仍另片，不能以单条日志打印宣称跨重启完整留存。
- 基线697cbc4/865跟踪SHA及4实现路径/5协调docs白名单已冻结，包/原事实/最新身份及页面要求/usage在kimi-reply-recipient/coordination/。usage-gate本次确实continue（UTC08:38:09.112303），session/weekly百分比null，不臆测。默认派后结束、用户通知265完成再收取，开发期间不读候选diff或并行改码。

## 下一步与人工门禁

1. 用户通知265后读完整交付/实际差异与原始复现，确认DeepSeek暂停再由Codex独立核；有问题直接修正并自检，不追加返修/回审。不能把message2816当task_id，交付必须自身265。
2. 先明确该条错误与后续消息/任务循环健康并完成必要验证/收尾；如需加载修正，只走原manager正常受管关闭/启动，按实际授权/门禁执行，不凭PID接管，不重复登录或撤销已通过的264/人工步骤。
3. 再由DeepSeek准备agent:kimi原模型/命令/可信Key与保ID迁移包；当前binding unconfigured，不猜/重建替代、不复制K2.8任务档或认证。DeepSeek/Codex自身最后；日志/删除/T-W及255其它页面另片。

## 已完成与恢复所需事实

- 新页面Kimi k2.8迁移已发布697cbc4：原ID/Key/alias保持，独立native登录/固定探针、同原manager受管启停及264固定回传/作者/Hall/领取实例均核通过；264结果2815/复核2816已收取，用户明确新角色页面三步均通过，当前generation5/ins_b587917b65ec及manager17908。随后发生本轮265收件人错误，验收历史与当前异常分开保留，不能称现在实例idle。完整证据remaining-role-next/independent-review263/smoke264/，原state追加265恢复指引而不改原结果/失败报告。
- 旧agent:kimi-code-k28-preview迁移已发布11bd14e，262原结果2809/复核2810已收取且人类页面三步通过；263时用户曾关至generation9，本轮又正常启至generation10，保其当前运行状态。旧宿主私有pilot/prj_e8fe7066bbec/agent_kimi-code-k28-preview/drain.request只供宿主收工：原manager先停角色、handles空再退出；新角色独立同名控制文件在自己的成员目录。API私有api-service/stop.request供原launcher正常退出，不删活动记录/强停。
- 263文案/下一角色准备已复核补正收取，原2812 partial保持；角色提示“请先「关闭」并确认已停止，再重新启动。”，关闭中→未启动含义已确认。默认隔离Node23/静态实际资源匹配、辅助原7+根5共12通过；诊断误报原反例1失败保留，根副本修正为自检。本轮沿用已通过源码测试，不重复累计。
- c129a63补通用CLI停止文件监听及清理，9新增/相关161项通过；原stop_timeout与原控制台正常Ctrl+C恢复事实保留。259保ID补录ea21d81/162相关回归+2WAL、260内置配方42738d9/74验证保持。受管配方默认21600可覆盖，通用bridge默认600/旧手动入口尚未全部统一。
- 完整异常日志仍待实施：脱敏持久保存类型/消息/完整堆栈/因果链与项目/角色/实例/任务/阶段，跨重启可追查；旧task queue worker failed初因未知。当前生产bridge stdout丢弃的限制未解决，不称已有完整日志、六小时或主动等待通过。
- 角色删除保历史/隔离其它角色，正式应用private目录与开发仓库隔离、255其它验收等已有要求保持。详情见相关规格及PROGRESS_HISTORY；原258/256/257、254/255/253/251历史报告不追改。
- 无新的精确额度；此前usage-gate continue但session/weekly百分比null，不当0或推测比例。恢复指令：继续项目。
