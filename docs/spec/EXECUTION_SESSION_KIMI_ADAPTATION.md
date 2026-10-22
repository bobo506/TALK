# Kimi Code 会话复用共用适配与自检

2026-10-22。用户明确继续开发Kimi适配，仍由当前Codex自行执行，不派DeepSeek/Kimi。本片实现、修正与验证均为Codex自检，没有外部独立复核。基线`56060b8f302ad4529c694e445b62a57360d40a76`。

## 共用范围与隔离

本机三个Kimi角色均绑定同一`kimi-code`运行器。`agent:kimi`选`kimi-code/k3`；两个K2.8角色选`kimi-code/kimi-for-coding`。两种模型共用`kimi_execution_native.py`和`kimi_execution_channel.py`，不按模型复制实现。角色、请求者、工作线、精确模型/绑定、HOME、配置权限、服务代次与基础合同共同隔离窗口；共用代码不等于共用原生会话、身份或计数。

原受管HOME公开模型配置中的K3与K2.8容量均为1048576；这是配置声明，未作为本片真实模型压力验收。实现逐次读取精确模型配置，不硬编码该值。原模型/Key/绑定/权限、TALK页面、286暂停及宿主统一启动排期保持。

## 实现

- API允许`bound/runtime=kimi-code`的普通顶层general任务。SDK/MCP参数沿用既有`execution_session`；bridge领取前基础合同/正常澄清、领取及租约守卫、正式runtime分派均已接线。不传字段保持原行为，不新增数据库列。
- 仅核验本机Kimi Code `2.0.2`的受控原生prompt命令。首轮按原`--agent-file/--skills-dir/--model`创建；续轮用明确`--session`恢复，因该版CLI禁止`--session`和`--agent-file`同传，恢复时不重发Agent文件，独立核验原生`profile.bind/config.update`中的模型、系统指令、工具及subagents边界。
- 首轮原生ID只能在CLI创建后得知。调用模型前先持久预留尝试，sidecar既有NOT NULL列以空串标记“ID尚未知”；CLI退出后核精确指令双证明，再以持有者/租约/通道/窗口/尝试的一次CAS绑定真实ID，最终ACK与计数按原事务提交。空串从不作为原生会话ID调用或公开；失败/取消不自动重跑。
- 正式送达须同时存在原生`turn.prompt(origin=user)`和同prompt ID、同SHA的`context.append_message(origin=user)`。自动日期/权限介绍、工具、预检、配置回执不计。未知送达、额外用户输入、权限变化、取消及失败结果会拒绝续用；已证明送达后的模型失败仍计数。
- 当前上下文数来自原生`token_counting`记录，容量来自同一精确模型的原生配置；`llm.request.maxTokens`是输出预算，不作容量。保留来源时间和磁盘cut。60%与条件10/11使用现有规划/计数内核，不复制规则。非法/未来/身份异常不走缺数兜底，恢复读数不清零。
- sidecar只存最小状态、SHA和回执，不新增助手正文、认证或完整配置存储。只读当前通道原生文件；不修改原生会话文件、不读或复制登录凭据。Windows命令行超过原生限制时明确拒绝，不截断正文。

## 自检及原生验证

最终一轮相关Python **338项通过**：规划内核、DSH指标/既有通道、Codex既有通道、Kimi格式/启动约束、API、MCP及普通领取入口。包含缺数十次、可靠低占用超过十次、读数恢复、取消/模型失败后的计数、双证明、权限/模型/工作线漂移、一次CAS、租约丢失与重复尝试不重跑。完整输出`.tmp/execution-session-kimi-v1/tests-final-2.txt`。

使用本机真实`kimi.exe 2.0.2`、独立HOME/sidecar及本机回环假模型完成**21轮/21次本地请求**，不使用真实账号或消耗Kimi额度。原生wire及真实CLI恢复均由安装版产生：

| 场景 | 证据 |
|---|---|
| K3、隔离review档兼容性 | 1→2同ID/计数1→2，只发增量仍从原生历史取回“星河42”；3 force_new恢复“杉木53”；4结束6000/10000后5换ID；生产K3原档实际为tools，下方实机按原档验证 |
| K2.8、原tools档 | 同一实现完成上述五轮；工具仍为Read/Grep/Glob/Bash/Edit/Write，未跨到K3窗口 |
| 条件十轮兜底 | 真实CLI连续十轮同ID/计数1..10，第11新ID/计数1并恢复基础介绍；通过测试专用子类受控隐藏指标，未篡改原生wire，不声称安装版自然缺数 |

最终证据根`.tmp/execution-session-kimi-v1/native-integration/b27d4189/`。K3同窗ID`session_ef807fd3-af61-42c7-85b6-473260ad2c7e`，K2.8同窗ID`session_9973bb6c-0bf7-469d-833a-3326533fc397`；缺数第1..10为`session_d8246b35-9edd-418f-83c2-08b6d45a9dc0`，第11为`session_68cb4522-3415-401b-b60c-05332644b37b`。原探针失败及后续修正证据均保留，不修改旧结果。

开发阶段保护核对：302条既有任务逐行SHA、原配置/绑定、五角色服务记录及286全文/暂停保持，当时未重载API或启停角色。原人工操作Key在普通沙箱读取被拒；下方用户授权验收后，只读核验/正常加载通过审批使用同一原Key在内存认证，不输出或复制凭据。

## 真实账号原生验收与API加载（2026-10-22 17:34）

用户回复“允许，只要不给kimi派发任务，目前的额度支持验收”。据此仅做直接原生验收，没有TALK任务创建、派发、领取或收取，也未启动接单bridge。使用原角色独立HOME/登录、精确模型alias及原tools档，通过产品Kimi通道、隔离sidecar和内存验收用例运行，不把用例编号写入生产任务表。

| 角色/模型 | 首轮与续轮 | force_new |
|---|---|---|
| agent:kimi / kimi-code/k3 | `session_20efd6a4-9a46-4f9b-843e-95fd7d36b08c`，计数1→2；续轮未重发“松涛38 / 白鹭76”仍正确回复 | `session_5aeefb96-e6b3-4aaa-982e-fd6a9c35eeba`，计数1，完整基础恢复“白鹭76” |
| agent:kimi-code-k28-preview / kimi-code/kimi-for-coding | `session_5d72aa7a-c3a3-4602-9035-c80362406be6`，计数1→2；同样正确回想 | `session_4418b8b3-a7ae-4d92-9c06-814ee14ccff1`，计数1，完整基础恢复“白鹭76” |

原生wire核对6次llm.request，模型与alias均精确匹配，没有工具调用。K3三轮用量6962/7430/6887，K2.8为7025/7506/7167，容量均1048576；这是低占用真实模型验证，60%及10/11边界仍以上节受控验证为据。续轮directive未包含暗号或基础标记字面值；六条正式prompt SHA逐条与回执一致，六尝试均confirmed、零遗留通道，六个原生进程均退出。

原API经已核launcher的stop.request正常关闭/重开，新launcher18580/child10600，健康与创建时间核验通过，未强杀、重建或解除任何角色归属。三个Kimi服务仍stopped/无owner/can_start；原DSH/Codex代次及进程事实保持。302条生产任务逐行SHA、配置/绑定、五角色记录、286全文及暂停均不变。

证据`.tmp/execution-session-kimi-v1/account-validation/`：readiness、逐轮JSON/原生stdout与stderr、独立sidecar、模型请求审计、api-reloaded及final-verification。生产原权限两角色均tools，未沿用隔离review测试来变更权限。此前Key读取失败保留，未更换凭据或重新登录。

## 生产短文本派发、领取、交付与收取（2026-10-22 18:02）

用户进一步明确“可以做TALK生产任务派发、领取、收取闭环……只要不是给kimi安排开发任务就可以”。本轮以原human:bobo入口创建/收取六条general短文本，Kimi只回复标记，没有安排开发、工具或文件操作；Codex继续负责实查与自检，不称独立复核。每次创建前读取最新项目开发要求，保留其旧分工快照，本次用户授权只适用短文本验收。

| 模型 | 首轮/同窗续轮 | 新窗恢复 | 结果消息 |
|---|---|---|---|
| K3 / agent:kimi | 303→304：`session_e9184946-9730-44b3-b3da-5b2b558bf8e2`，计数1→2 | 305：`session_61157b63-30e2-412c-aaaa-1d1a2be2cfdf`，计数1 | 2909/2910/2911 |
| K2.8 / agent:kimi-code-k28-preview | 306→307：`session_25479f95-9055-4729-81d7-774b679be0a4`，计数1→2 | 308：`session_95e380ac-c5c2-4881-97d1-7a4e07c46d09`，计数1 | 2912/2913/2914 |

六条均由精确角色/新实例真实领取并交付，human收取后为succeeded/completed、有result_collected_at。首轮回复“已记住”；续轮增量未重发暗号或基础标记，正确回复“海棠42 / 鹿鸣57”；force_new恢复基础后回复“鹿鸣57”。双prompt/context的ID及SHA逐条匹配，原生llm.request模型与alias精确对应，正式请求共六次、无工具调用；只读sidecar六尝试confirmed、通道0。必要模型预检另有原生调用，不计入正式送达次数。

首轮/force_new决策的context_status=unavailable来自无候选或主动新窗，完成后的last_snapshot均available；续轮决策context_status=known。K3用量7107/7652/7133，K2.8为7252/7803/7259，容量均1048576。本轮没有填充真实大上下文，60%及缺数10/11仍以上述受控边界验证为据。

起始两个原宿主均不存在、角色停止无owner且没有待执行旧任务。临时沿原窄入口恢复：K3 manager10708/gen25/ins_ec8cf7085581，旧K2.8 manager5524/gen26/ins_754ac10862f9。三条各收取后普通stop，最终K3 gen26、旧K2.8 gen27均stopped/无owner；待宿主异步发布空handles后正常drain退出，仅删除本轮写入的drain标记，第三Kimi始终停止。API10600未重载，DSH/Codex代次/实例/归属保持；302条原任务逐行SHA、原配置/绑定、Key文件mtime、权限与286全文/暂停均不变。

证据`.tmp/execution-session-kimi-v1/production-validation/`含readiness、逐任务request/requirements/created/status/result/collected/accepted、启停/宿主回执、native-audit及final-verification；脚本不自动重复创建任务。验收辅助脚本曾误把首轮context_status要求为reliable，303已成功但尚未收取时断言停止，核对原生读数后仅收取原303，未重建或重跑模型。停止后宿主健康回报短暂仍含旧handle，改为等原异步清理完成后正常drain，未改产品。K3第三条首次权限审批超时被拒，按系统允许仅重试一次后成功；超时没有风险判定，未绕过权限。原失败证据保留。

本轮没有产品源码变化，原338项和最后Kimi29项定点自检保持，不重复无关测试或真实模型探针。人工里程碑待用户确认；本次短验收不恢复Kimi常规开发派发，也不自动开启下一片。

## 当前边界与预算

**K2.8/K3共用适配的开发、自检、原生真实账号验收及生产TALK任务闭环已完成。** 三个Kimi角色均保持停止，常规开发派发仍暂停；人工里程碑待用户确认。另一K2.8成员的独立HOME/登录尚未按本片单独实机，共用代码和隔离规则已有覆盖。后续启动沿原普通入口，派发遵守最新授权；下一片及宿主统一启动另行确认。

执行预算沿原入口，单次任务默认21600秒；取消/超时仅清理本次Popen及其子树，Windows taskkill及Popen退出各有10秒等待，清理可额外消耗20秒，不与模型执行预算混称。原MCP主动等待客户端上限T未重测；不启用主动长等待，W未配置。Kimi模板`toolTimeoutMs=660000`只作模板事实，不作为实际宿主能力。已读[终端预算要求](../guides/TERMINAL_MCP.md)，本片不新增模型侧TALK MCP，不宣称主动等待适配完成。

原生接口依据为[官方会话说明](https://www.kimi.com/code/docs/en/kimi-code-cli/guides/sessions.html)及精确`@moonshot-ai/kimi-code@2.0.2`公开源码：原生print入口、profile/turn/context/token_counting事件与配置映射。冻结公开源码在本片`upstream/`；网页/源码只用于接口核对，安装版实际文件和测试是本片验证依据。
