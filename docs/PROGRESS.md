# Project Progress

Updated: 2026-10-20 09:03（Asia/Shanghai）。281方案已独立实查并收取；原16单测复跑通过，独立8边界反例暴露7失败/1错误。Codex补正A本地采集合同，原型及B接收不直接采纳；产品/生产未改。280人验保持，顺序仍日志收尾→全入口预算统一→会话复用。

## 281已复核收取，准备本地A实现

- [281复核](spec/ROLE_HOST_RUNTIME_EVIDENCE_REVIEW_281.md)、[A补正合同](spec/ROLE_HOST_RUNTIME_EVIDENCE_DESIGN.md)。实际193冻结副本/产品基线197fe7a未变；原msg2888完整合法complete、作者DeepSeek/ins_a3d16c467fec/Hall一致，SHA8217945f7ad5b3d28b2c215538e50971d9680761aff5658e2caa2b5f5639a8cf与本地一致。稳定引用ok，UTC01:03:17.285773收取completed，原自报/失败/原型不改。
- 独立8反例确认序号10000封顶/launch seq0、133次无谓观测、整体失败假空集合、错launch归因、接收同轮两态冲突/嵌套host/跨host幂等冲突。原16项可复跑不抵消缺陷；仅修订正式设计，不能说原型修后全过。
- A固定真实循环边界/60秒采样、序号≤2^53-1、未知null、不混scope、有界32 poll/256条检查、取消/异常传播及原Popen只读；不增HTTP/DB/认证/配置/页面。B接收方案未批准，received_at保持缺失；C全根治理另片，不提前预算/会话。
- 证据.tmp/host-runtime-evidence-v1/independent-review/原件/复跑/8反例/CLI/detail/verification/稳定引用/收取齐全。冻结gap/export输出由Codex另加断言，CLI真实隔离fixture验证--json须加--detail才含extra；ACL WinError 5/plain替身限制保留，无生产日志/DB/Key读取或启停。
- 当前MCP反查本人agent:codex/agent、项目prj_e8fe7066bbec/lead，DeepSeek及K3新鲜idle；原页面旧交叉复核文本保持。usage-gate返回continue但session/weekly比例均null，只据批次/范围刹车，不臆测额度。下一片拟派DeepSeek按A合同隔离首次实现，交付暂停后Codex独立检查。

## 当前身份与协作

- 项目prj_e8fe7066bbec，桌面MCP本人agent:codex/agent、业务lead，负责协调/独立实查/直接修正自检/集成与正式进度Git。
- DeepSeek和Kimi K3首次执行、自测后暂停；279/280及281方案已收尾，下一片仅DeepSeek的本地A实现，当前正式产品未改。不派两个K2.8，不自动等待/唤回或收取未通知任务；页面旧交叉复核文本未改，按用户/AGENTS最新分工。
- 本轮只推进当前日志功能的281复核及后续A隔离派发，不并开B/C或其它功能。用量来源比例未提供，按批次/范围控制；完整历史见PROGRESS_HISTORY。

## 279已加载并通过实机核验

- 代码86a4fb5；[合同](spec/ROLE_QUEUE_POLL_DIAGNOSTICS_DESIGN.md)、[复核](spec/ROLE_QUEUE_POLL_DIAGNOSTICS_REVIEW_279.md)。Codex独立5反例后直接修正导出来源/间隔/时刻校验，290 Python及24 Node全过、零跳过。固定12键、真实轮询/连续失败/恢复、取消及模型任务分离；旧schema/权限/预算/启停租约保持。
- 原msg2886/partial、SHA1c9779a72ee03e10b03a4be208a04dc20cd3c51fda7e3486b542a0f00d1bd423及原失败保持，UTC14:34:17.193394已收取。原合同13为计数笔误，正式改12，冻结表格/报告不追改。
- 用户本轮明确“允许”关启DeepSeek/K3/两个K2.8并重载API；UTC14:54:12重核空闲、真实原Popen归属与配置后，4角色普通stop释放owner、API原启动器正常重载至15792/9808、原manager普通start恢复4角色。Codex始终stopped/gen18；没有宿主重启/强停/解除归属或改模型绑定。
- 第二次启动审批因循环仍列Codex而拦截，命令未执行；缩为四角色白名单后获批执行，不绕过审批。此前开发授权不足的原批量停服拒绝记录保持，由本次用户明确许可闭合。
- UTC14:57:09→14:59:39：4新实例仍原manager直接子进程、ready/idle且心跳各推进约150秒；查询成功seq31→106，每份真实下载完整，12字段/开始成功配对/30秒间隔正确，Agent403/匿名401，配置/绑定保持且无在途任务。生产未故意制造异常或调用模型验收失败恢复，相关分支已有隔离证据。
- 实机证据.tmp/queue-poll-diagnostics-v1/independent-review/deploy/：各stop/start回执、api-ready、live-first279/live-final279及4份真实JSONL；授权/审批原件、源/测试/收取证据同上级保留。

## 280已独立通过并合入，用户页面人验通过

- [格式合同](spec/ROLE_BINDING_SUMMARY_FORMAT_REQUIREMENTS.md)、[复核](spec/ROLE_BINDING_SUMMARY_FORMAT_REVIEW_280.md)。列表统一状态 · 运行器 · 模型 · 可得思考强度；缺值按用户最新要求省略项/分隔，不显示占位或猜Kimi值；精确旧Kimi登记名短显Kimi Code、保实际K3/K2.8模型及自定义名。
- Codex实查五文件实际diff、36冻结源及SHA/patch，未发现需修正项；独立20套workspace288项、当前API五角色真实JS列表渲染1项均通过，零跳过。既有保护断言保持，两测试仅版本串；不重跑未变后端测试。
- 原msg2887/complete，作者K3、旧接单ins_664e5bfefeff在279重启前完成，SHA0e7c2392ef0b54e8a2db60f7dd85deb9f77b4e06eb6845961706082daad94af2。MCP结果仅progress_draft.summary追加交付路径，其他9顶层字段/next与本地一致，两原件保持；UTC15:01:30.355501由原creator收取completed。
- 五候选正式字节等于已测副本，版本20261019-role-binding-summary-v1，八引用/九静态资源HTTP字节全部一致。280只有静态文件更新，无额外API/宿主/角色重启；未由Codex Browser验证视觉/键盘/窄屏。
- 证据.tmp/role-binding-summary-v1/independent-review/：archive、original-candidate/patch/报告、verification、实际公开bindings/actual-rendered-lines、integrated、live-static、stable-result-reference及collect-receipt。

## 最近运行事实与下一步

- 最新279实机：DS ins_a3d16c467fec/gen19/manager16796；K3 ins_940b81b256c9/gen19/17540；旧K28 ins_37442980db95/gen22/9204；页面K28 ins_17649ed04774/gen19/12976；Codex关闭。均为当时观测，未来操作须重新核归属/空闲，不用历史PID接管。
- 用户本轮明确280“验收通过，按原计划继续”：Codex/DS强度及三个Kimi缺值/短名的绑定行页面门禁闭合。沿原人类登录，无新账号/Key；不额外推断键盘/窄屏专项或完整日志整项已验收。
- 278原页面人验保持。完整日志整项仍有宿主独立心跳、跨宿主来源/查询及全根空间治理；不跳全入口预算/选择性自启动。六小时、真实主动等待/取消排队、跨沙箱驻留/冷启动、255完整创建ready等原未验边界保持。

恢复指令：继续项目。
