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
| K3、原review档 | 1→2同ID/计数1→2，只发增量仍从原生历史取回“星河42”；3 force_new恢复“杉木53”；4结束6000/10000后5换ID |
| K2.8、原tools档 | 同一实现完成上述五轮；工具仍为Read/Grep/Glob/Bash/Edit/Write，未跨到K3窗口 |
| 条件十轮兜底 | 真实CLI连续十轮同ID/计数1..10，第11新ID/计数1并恢复基础介绍；通过测试专用子类受控隐藏指标，未篡改原生wire，不声称安装版自然缺数 |

最终证据根`.tmp/execution-session-kimi-v1/native-integration/b27d4189/`。K3同窗ID`session_ef807fd3-af61-42c7-85b6-473260ad2c7e`，K2.8同窗ID`session_9973bb6c-0bf7-469d-833a-3326533fc397`；缺数第1..10为`session_d8246b35-9edd-418f-83c2-08b6d45a9dc0`，第11为`session_68cb4522-3415-401b-b60c-05332644b37b`。原探针失败及后续修正证据均保留，不修改旧结果。

保护核对：302条既有任务逐行SHA、原配置/绑定、五角色服务记录及286全文/暂停保持。未创建生产任务、未重载API或启停角色。三个Kimi数据库记录均stopped/无process_launch；DB快照不作当前进程在线证明。读取原人工操作Key被当前沙箱拒绝，未进入human API启停或尝试其它凭据；后续加载需沿原授权入口核实。

## 未完成的实机验收与预算

**开发与隔离自检完成，生产加载和真实账号验收未完成。** 用户此前Kimi额度暂停尚未明确解除，故未向Kimi派任何生产验收/开发任务，也未调用付费模型。不能据本地假模型通过称全角色功能已真正可用或人工验收通过。

下一步只待本片最小实机安排确认：沿原API/宿主普通加载，精确K3及一个K2.8角色各做首轮/续轮/force_new三轮任务，核原生ID/计数/基础恢复并由合法原请求者收取；如需临时开启角色，在核验安全状态后按普通start/stop恢复原状态。不改模型/Key/绑定/权限，不自动解除owner，不恢复Kimi常规派发或286；其它新片与宿主统一启动仍另行确认。

执行预算沿原入口，单次任务默认21600秒；取消/超时仅清理本次Popen及其子树，Windows taskkill及Popen退出各有10秒等待，清理可额外消耗20秒，不与模型执行预算混称。原MCP主动等待客户端上限T未重测；不启用主动长等待，W未配置。Kimi模板`toolTimeoutMs=660000`只作模板事实，不作为实际宿主能力。已读[终端预算要求](../guides/TERMINAL_MCP.md)，本片不新增模型侧TALK MCP，不宣称主动等待适配完成。

原生接口依据为[官方会话说明](https://www.kimi.com/code/docs/en/kimi-code-cli/guides/sessions.html)及精确`@moonshot-ai/kimi-code@2.0.2`公开源码：原生print入口、profile/turn/context/token_counting事件与配置映射。冻结公开源码在本片`upstream/`；网页/源码只用于接口核对，安装版实际文件和测试是本片验证依据。
