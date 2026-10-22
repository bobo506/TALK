# Codex 原生会话复用适配与自检

2026-10-22。用户明确本片由当前Codex直接开发，不交DeepSeek；本片实现、修正、测试及集成均为Codex自检，没有外部独立复核。TALK页面保持。本片不是新的执行者交付任务，300/301/302是验收任务号。

## 范围与实现

- 基线`28a69d91a4386c018180cd7a58e10422abf70f2f`，授权与8份原源冻结在`.tmp/execution-session-codex-v1/authorization-baseline.json`和`baseline/`。
- 新增`bridges/codex_execution_native.py`和`codex_execution_channel.py`；API允许bound/runtime=codex的普通顶层general任务，bridge按已核runtime分派。原来的可选execution_session合同及SDK/MCP参数保持，不传字段仍走原路径。
- 共用288规划内核、持久sidecar/锁/CAS/尝试幂等、基础合同与状态助手；不复制60%/10次规则，也不伪造DSH采集快照。DSH通道、内核、store、Codex旧入口及原native_driver/manager入口6份原源哈希保持。
- 当前核验CLI为`0.163.0`；从原受管任务薄驱动构造原生app-server私有stdio，沿用原gpt-6.1-sol/xhigh、独立CODEX_HOME、read-only/never及禁用功能和网络环境。不接桌面daemon、不新增监听端口、不读取或复制auth.json、不改变原Key/绑定。原生自身正常刷新登录缓存不等于替换登录。
- `thread/start`只分配新ID，首次指令后才落盘；复用明确thread ID，原生完整基础介绍只在新窗投递，续轮只投增量，每次任务仍保留当前控制信息。
- Codex正式送达以持久文件中的`event_msg/item_completed/UserMessage`及精确指令SHA确认；自动AGENTS/环境介绍、预检、工具及原生配置回执不计数。原生生成ID后才预留尝试，重复尝试不再次调模型；确认送达后模型失败仍计数，未知送达/未证终止停用旧窗。
- 指标取原生`token_count.info.last_token_usage.total_tokens`和`model_context_window`，不是累计计费用量。保留原生来源时间；可靠<60%续用、≥60%下次换窗。只有单纯缺数/来源过期且精确窗口身份与可信连续计数时才走十次备用，非法/未来/身份冲突不兜底，读数恢复不清零。

## 实机发现与修正

1. 原生文件延迟创建；以可信新线程的空cut表示尚无投递，不能据ID创建就计数。
2. 0.163.0持久化正式UserMessage，不能只识别旧user_message事件；已分离自动指令种子与真正任务输入。
3. Windows原生返回`\\?\`扩展路径；规范化后仍核会话ID、HOME、工作区、原生版本和模型。resume追加的同身份同设置回执仅按严格附加/配置摘要白名单接受，额外用户事件或设置变化拒绝。
4. 隔离领取前预检没有旧原生历史，曾错误要求重发上一轮暗号。只对经基础合同引用声明的Codex续轮补明确预检边界；不跳过预检、不承诺已续接，新增必要事实缺失仍正常澄清，force_new/首轮不套用此声明。正式执行仍独立核窗口/阈值与权限。
5. 本桌面MCP身份与目标均agent:codex，自派创建按既有规则400拒绝，未建任务。本片真实任务改由已授权的human:bobo普通SDK/API入口创建并由原请求者收取；未改桌面身份、未借DeepSeek身份，也不冒称该自派MCP路径通过。其它合法请求者的MCP参数/双runtime分派由隔离测试覆盖。

## 验证与生产证据

- 最后相关Python自检**205项全部通过**，覆盖Codex原生格式、规划/计数/来源过期、ACK/异常/取消/重复、元数据附加/设置冲突、预检仍可澄清、API/基础合同/状态、Codex原入口、双runtime桥接及DSH既有运行链路。`tests-final.txt`保留输出。
- 60%边界及缺数1..10/第11使用独立HOME、真实原生格式文件及假模型响应测试；最近用量与累计用量区分、可靠低值超过10轮、恢复不清零均有反例。真实模型仅低占用验证，不声称真实高占用压力试验。
- 零模型隔离协议探针及原生独立登录两轮证据在`native-probe/`和`live-native/`，早期失败保留。原生独立测试第二轮只问暗号，返回“松果62”；实际容量475000，未硬编码成DSH的1000000。

| TALK任务 | 原生ID | 结果 |
|---|---|---|
| 298 | `01a16298-e2c5-7691-bc25-5005bd2d95cc` | 原首轮完成/收取，计数1 |
| 299 | 未正式投递 | 预检错误要求重传暗号；原请求者取消，保留问题与失败记录，不计轮次 |
| 300 | `01a162a3-eee4-7f63-b8d7-54ee978f0e71` | 补正后完整首轮，回复“已记住”，计数1 |
| 301 | 同300 | 仅增量，回复“海星84 / 银杏73”，真实同窗、投递前指标known、计数2，无新增澄清 |
| 302 | `01a162a6-bdc5-7a30-978e-82fd55d2e9a6` | force_new，完整基础恢复、回复“银杏73”，计数1 |

300/301结束最近用量分别24054/24443，302为24067，容量均475000。原生文件的正式UserMessage SHA与三个任务directive_sha256逐个匹配；298/300/301/302四个尝试均confirmed，299无尝试记录，sidecar无在途通道/任务。三条补正后验收均succeeded/completed并收取。

原API沿原launcher正常重载，297条既有任务逐行哈希不变，无新数据库列或历史回填。Codex原来generation18/stopped、无owner/can_start，旧manager11768和旧bridge4960不存在；恢复原manager19564并普通start至19，修预检后普通stop/start至21。当前实例`ins_e98e909598ec`，running/ready/idle；API launcher20664/子20500。未调用任何owner恢复入口；其它角色、原配置/绑定、286全文及暂停哈希保持。`production/final-verification.json`保留最终核对。

## 使用与剩余边界

- [统一使用说明](../guides/EXECUTION_SESSION_USAGE.md)中的execution_session参数对当前DSH/Codex通用。必须由不同于目标的合法请求者派发；当前桌面agent:codex不能向同名角色自派，用户或其它已授权请求者可走普通入口。
- 当前只核验上述Codex版本、原受管命令/模型/权限组合；未知版本/入口/参数或权限不一致明确拒绝。其它Codex命令、升级后版本或权限组合不能沿用本次验收结论。
- 原生stdio RPC单次30秒；任务执行预算沿原受管入口默认21600秒，正常中断/退出分别有5/10秒清理预算。测试SDK观察总预算180秒，只结束读取，不自动重发/取消模型任务。
- 任务执行路径没有新增Codex模型侧TALK MCP，也未启用主动长等待；客户端MCP上限T未重新实测，不把300/660秒历史说明或本次能派发当作主动等待适配通过。API/取消/领取前澄清与同连接边界保留，终端约束见[TERMINAL_MCP](../guides/TERMINAL_MCP.md)。
- 全角色目标当前完成DSH与Codex，Kimi尚未适配且额度暂停；TALK页面不改。当前片已交付待用户确认，下一片及宿主统一启动修复不自动开启。

证据根：`.tmp/execution-session-codex-v1/`。原生模型/持久文件是本机验证来源；接口依据为[OpenAI Docs原生会话生命周期](https://learn.chatgpt.com/docs/app-server)与本机生成的0.163.0协议schema，官方文档不能代替安装版实测。
