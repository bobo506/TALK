# DSH上下文采集挂载与接线方案（291复核补正版）

2026-10-21。本文由Codex在291首次交付独立实查后补正，作为后续实施依据；原始9份交付保留于`.tmp/execution-session-live-entry-s0/deepseek/`。这是方案，未加载插件、改运行配置或启用原生会话续用。

## 已核结论与限制

- 冻结的npm DSH `0.1.5-rc.2`默认headless入口等待loader后创建新UUID会话，执行task、flush并退出；没有暴露resume参数，也未调用已有的`agents.resume`。当前TALK没有跨任务续接线，不能仅靠增加采集器实现会话复用。
- 默认profile组合顺序为bundle、profile patch、home patch、argv中的各个overlay；公开loader支持将本机插件文件作为候选入口。额外overlay是可行候选，实际用户patch、动态include及插件激活仍未核完整，不能保证当前真实树可无冲突加载。
- 当前磁盘版本和公开文件SHA已核；实际进程已加载的原生字节、有效环境/插件树和live projection未证明。空白名单投影不表示没有插件，文件存在或binding=bound不代表实际模型/权限已验证。
- 本片不实现插件、传输、bridge开关、锁/CAS/ACK存储或resume；未执行原生应用、模型或合成挂载链。已有288/289/290产品及280项离线证据保持。

## 原生挂载与生命周期

候选新增TALK侧Cordis插件`bridges/dsh_context_host.mjs`，从现有`bridges/dsh_context_capture.mjs`使用`mountContextCapture(ctx)`，或显式传完整依赖调用`createContextCapture`。不得只创建一个没有session/projection监听器的collector。

1. 插件apply阶段注册`session/created`，通过注入的`sessions`和`sessionProjections`访问原生服务。源码中的headless在`agents.create`前等待loader settle，支持事件前安装监听的静态论证；真实加载及事件先后仍是实施验收项。
2. 创建事件中只绑定明确属于本次受管执行的主会话，过滤subagent/parentSession；第二个主会话不能覆盖第一个。同步完成track，再注册该handle的输出监听，确保collector观察当前事件后才read，避免依赖未验证的回调顺序。旧handle迟到回调必须失效，监听与输出监听均要释放。
3. 每个track字段由明确来源映射，不能将snake_case request直接传入track。`nativeSessionId`只取live session.id；其余12个scope标识与workspacePath逐一映射为camelCase，sessionGeneration单独给出；`hostAttestation`必须是`{verified:true,source:<已核调用来源>}`。这个标签不是跨进程认证，不能用它替代真实宿主/配置证据。
4. 在当前主会话`turn/end`处理完成后同步read并原子写输出；读数必须满足live身份、cwd、cut/seq、字段来源和事件连续性。baseline cut取实际registry值；新空会话合成例可为-1，不能硬写-1，也不能据此给既有值补造来源时间。
5. `session/disposed`解除handle；插件卸载执行capture.dispose并释放输出监听。无turn/end、读取/输出失败、回调冲突或来源缺口均保持unknown。正常终态快照不能被dispose时的错误标记无条件覆盖。

候选overlay中的插件路径由真实工作区生成；本仓库应是`D:/claude-test/TALK/bridges/dsh_context_host.mjs`，不能复制原稿的`C:/claude-test/TALK`示例。overlay只注入正式任务命令，不进入临时预检命令，也不修改持久profile或安装包。

## 标识、指纹与信任来源

| 字段 | 来源与约束 |
|---|---|
| continuity_key | 协调方明确指定的稳定功能工作线；同功能不同task/attempt沿用。不能生成成task-id/attempt-id，否则会破坏跨任务续用。不同功能仍新窗。 |
| task/attempt/run身份 | 用于审计、幂等和一次spawn的传输隔离，独立于continuity_key。预检、repair及gate重跑各有独立run标识/目录，不共享输出。 |
| native session ID/generation | live原生服务事实和可信通道绑定记录；不是从任务号猜测。当前一次性新窗的generation可为1，但它与服务generation28不同，也不因读数恢复或不同task而重置同一窗口。 |
| workspace_identity | 规范化且已核真实工作区身份；与collector使用的cwd字符串及真实目录证据一致，不能只用路径存在代替核验。 |
| model_binding_fingerprint | 优先使用已核项目角色binding指纹及修订事实；另以原生request/context核对provider/model。不能另造一个只含alias/model的摘要，丢掉已有绑定信息后声称同一绑定。 |
| config_permission_fingerprint | 必须来自可核的配置/权限/插件manifest及修订来源。只有启动规格声明时应保留该限制；实际有效配置未知或动态变化不能核实时，不允许续窗或十次兜底。当前片不扩读真实配置来补造此证明。 |

需要派生摘要时，采用带schema/version及字段名的规范JSON，明确UTF-8、key排序、紧凑分隔符、路径规范化和字段类型规则后哈希。禁止无字段边界拼接：`ab+c`与`a+bc`在哈希前已相同。这是编码歧义，无需攻击SHA算法即可发生。

## request、snapshot与bridge边界

- 候选request使用严格schema/version和字段白名单，区分scope、一次spawn身份和宿主证据。requestPath、outputPath、allowedRoot只由本次可信bridge创建；路径不可从插件输入任意指定后自行宣布可信。传输协议尚未实现，不修改289/290现有schema。
- 新建每次spawn独立的私有目录，禁止复用旧attempt文件。路径按真实目录组件比较，核父目录/目标及junction、symlink和Windows驱动器规则，不能用字符串startswith；原子替换前后仍须保持隔离，拒绝已有未知输出或越界路径。
- 插件输出保留原collector `talk-dsh-context-snapshot-1`格式；如需run/request摘要绑定，应在独立传输封套中明确约定，不能向collector快照随意追加字段。桥接用自己保存的请求和绑定事实校验，不把同一个未核输出里的ID/revision复制成expected_scope后称已独立验证。
- `adapt_context_snapshot`需要12个scope字段及native_session_id、session_generation、session_revision；显式给trusted_host、now和max_age_seconds，严格保持现有校验。read的观测时间和源事件时间不能互换。合成例的60秒新鲜度不是60%换窗阈值，生产新鲜度另定。
- bridge仅在本次子进程退出后读一次对应输出，体积/JSON/schema/身份/来源失败就unknown，无轮询、补旧文件或模型重跑。退出后文件只表示捕获时的历史读数，不能证明原生会话仍live，也不能授权下一任务续接。真正投递前必须有有效原生通道及新鲜身份/占用证明。
- 无真实窗口绑定、完整送达历史或ACK持久化时，不能把离线规划或文件生成当成已发送/已计数。

## 不可得分类与失败处理

| 情况 | 处理 |
|---|---|
| 可靠指标可用 | 保持同功能/身份配置/通道先验，再用原整数60%判断；可靠低值不受10次硬限。 |
| 仅合法源样本过期 | adapter的used_sample_expired、capacity_sample_expired、pressure_sample_expired可分类为source_expired。只有身份/来源等检查和完整计数、备用时钟全部可信时才可能十次备用，不能笼统禁止，也不能把过期数据当当前known。 |
| 无快照的宿主能力声明 | build_metrics_unavailability只接受metrics_not_provided、no_usage_sample、runtime_unsupported。capacity_missing须由adapter验证快照后分类，不能由宿主无快照时凭空声明。 |
| 未来、非法、错身份/配置、事件缺口或冲突 | 保持阻断，不改写成单纯missing或source_expired，不用十次绕过。 |
| request/路径/运行中采集/输出失败 | 捕获并产生unknown/短错误码，避免改写任务业务结果；禁止向模型回复或日志泄露正文、凭据和原始异常。 |
| 插件导入或激活失败 | 原生loader会抛错，可能在模型执行前中止，不能承诺“任何采集失败均不影响任务”。第一实现片只能默认关闭、隔离验收；隔离缺口未闭合前不生产启用。不得失败后自动重跑模型以掩盖启动错误。 |

生成request/overlay等在spawn前已确定失败时，可以保持本次原始命令且明确采集关闭；一旦spawn后是否执行过模型无法证明，不得自动回退再跑一次。回滚是经确认后对后续启动关闭新增开关，保留旧证据，不追改原任务结果。

## 实施候选与验收门禁

后续候选为插件、独立传输模块及对应隔离测试；bridge真实接线、宿主参数/原生入口变更须按后续单片范围确认。默认不开启，不把本方案直接加载到当前角色。首个实现片应验证实际collector与合成service/projection的生命周期、真实字段映射和传输，不冒称真实DSH挂载或resume。

验收必须覆盖加载/激活失败、监听顺序反例与解除、多主/子会话隔离、原子输出/路径越界、缺失/超限/旧attempt、repair每spawn隔离、指纹字段分隔、跨task稳定工作线、59.9/60、缺数/合法过期与非法区分、10/11、读数恢复不清零，以及默认关闭时既有命令/超时/业务状态不变。预检不采集、无自动模型重跑、无真实配置/会话读取。

当前headless无resume的事实意味着最终仍需单独的原生续接入口方案，不能用“采集完成”代替“会话续用完成”。按照用户顺序，291收尾后先处理宿主统一启动链路；采集实现和续接入口保留后续，不能跳过该排序。

客户端T、显式W/返回余量、执行者21600与取消/同连接边界按[终端适配要求](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)分别核验；headless T当前unknown/not_run，仍不启用主动等待。

源码与复核证据索引见[291独立复核](EXECUTION_SESSION_LIVE_ENTRY_REVIEW_291.md)。
