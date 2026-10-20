# 会话机制第二片：DSH上下文指标采集与内核适配

当前状态：2026-10-20 23:22（Asia/Shanghai），289首次候选经Codex独立实查、直接补正和自检后集成，已收取completed，结果2895原自报保持。正式Node34/Python44/既有288的106项全过，共184项；采集器未加载、真实占用仍未知。详[289复核](DSH_CONTEXT_METRICS_REVIEW_289.md)和[调用说明](../guides/DSH_CONTEXT_METRICS.md)。下方创建状态仅保派发时历史，原冻结任务包不覆写。

派发状态：2026-10-20 22:45（Asia/Shanghai），实际任务289，创建`queued/assigned`，creator `agent:codex`、target `agent:deepseek`，Hall `group:task-2fe861b89f60455287e3da370f809adf`。22份项目公开材料979,318字节、29份原生公开源码458,397字节已冻结，逐SHA清单及原合同/请求/脱敏入口事实/创建回执在`coordination/`。当前无开发交付或独立验收结论；下方原合同保持，冻结任务包不随本节更新覆写。

## 授权、目的与不变项

2026-10-20，用户在288收尾后对“下一片建议接入DSH真实上下文指标，待确认后开始”明确回复“可以，继续吧”。据此批准本片：核验实际入口与已安装原生指标接口，实现从DSH原生会话projection读取上下文值的采集器及到288内核的适配。当前只形成可测试、可挂载的采集代码，不将授权扩大为运行中角色加载、创建/恢复原生会话或MCP派发。

- 基线`15f77b279993dbf952291f8f8d141756cd07768c`；协调、范围及首次交付独立实查/直接修正为`agent:codex`，首次实现/自测/交付后暂停为`agent:deepseek`，project `prj_e8fe7066bbec`。Kimi继续暂停新任务；派发前读取项目要求，页面旧交叉复核文字只作原样快照，以AGENTS本次分工优先，不改页面。
- 288统一内核已集成，106项及11,994组阈值检查保持。按[总体需求](EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)实现原始占用，不能改回10轮或把累计计费/缓存命中率当上下文占用。
- 保TALK任务、Task Hall、权限/收取、owner、配置/Key/模型绑定、原生历史及角色启停不变。正式bridge/host/API/MCP/任务schema和288模块不在本片可写范围，不顺带接续用/自动换窗/页面/缓存实验。

## 已有事实与未知

Codex派发前只读核对当前实例`ins_00acba0f8a9b`、PID12284、父PID11612：通用`bridges.cli_bridge`、headless、argv transport，未见ACP入口；不输出完整argv或环境。机器进程读取的首个普通沙箱调用被系统拒绝，随后相同PID/白名单字段的只读提权核对成功，未启停进程。

已安装npm包`@deepseek-ai/dsh`版本`0.1.5-rc.2`；公开源码确认`ctx.sessionProjections.snapshot(session, ["contextPressure"])`返回所选view及`asOfSeq`，token-meter提供`projectedTokens/pressureTokens/contextWindow`。14:44 UTC白名单复核未在实际命令中直接匹配这份安装的绝对bin.js路径，不能据此把安装版本认作当前进程版本，也不能反推它必定使用其它版本；入口关联仍未知。实际native home、完整有效插件组合及运行中projection仍未取得，不能根据源码或路径命名推断已生效。

分子和容量是独立last-wins槽；`request/context`只在相关配置变化时追加，不一定每个请求都有。projection当前cut不等于同一请求原子样本。原headless只输出最终正文，当前bridge未传结构化占用；本片交付前不得声称真实数值已经到达TALK。

## 隔离白名单与交付

公开项目源码/指定文档和已安装DSH相关源码冻结于`.tmp/dsh-context-metrics-v1/baseline/`、`native-baseline/`，manifest及脱敏运行事实/原包/创建回执在`coordination/`。执行者只能写`.tmp/dsh-context-metrics-v1/deepseek/**`。

候选产品白名单：

- `candidate/bridges/dsh_context_capture.mjs`：只读原生接口的可挂载采集器。
- `candidate/bridges/dsh_context_metrics.py`：标准库规范化/验证及288输入适配。
- `candidate/tests/test_dsh_context_capture.mjs`、`candidate/tests/test_dsh_context_metrics.py`：对应测试。

另可写本片README、合成输入/原始回执、证据及`delivery.json`；不扩产品白名单，不改正式文件/Git/进度文档/baseline/coordination或旧产物。只能读取冻结公开材料及coordination脱敏事实，不能读取真实会话/日志/数据库/owner/认证/Key或完整环境，不用生产profile/dump初始化目录，不导入/启动DSH应用、CLI/ACP或额外模型，不启停服务。缺失事实如实列未知；不为补证扩大读取范围。

## 实现合同

### 原生采集器

1. 必须有可调用的采集入口，使用已核验的DSH原生session/projection服务接口读取`contextPressure`和对应cut，不得仅接受一个自行发明的三数对象再声称接通原生采集。接口注册、监听/解除或按需读取的具体方式由执行者按冻结源码确定并说明；提供未来挂载示例，不改当前profile或headless驱动。
2. 读取明确选定的同一会话及当前会话代次，不能按最新文件/mtime/标题猜测对象；不扫描或重放聊天历史、不checkpoint/export所有投影，不读取/输出prompt、系统正文、工具输入输出或私有配置值。若原生API内部同步materialize的语义影响读取范围，须按源码如实说明，不能声称完全没有原生内存折叠。
3. 输出版本化的最小JSON快照，含原生会话ID、生命周期/代次、projection cut/修订、provider/model及绑定配置关联、projected/pressure/capacity的可得性、来源与观察时刻。工作区/native home/launch等由可信调用层显式提供并核对，不仅将caller标签贴到任意旧projection上。不能伪造实际后端模型或会话创建成功。
4. 指标来源分开记录：预计下一请求值、最近请求值、模型容量；有字段不等于可用。缺失不同于0、显式非法不得删除成“缺失”，非法projected不能降级成低pressure。不得采用累计usage或UI取整/封顶百分比；大整数与负值/布尔/非有限数须严格验证。
5. 区分当前registry精确cut、cachedSnapshot/持久checkpoint提示和无法证明当前的旧数据。读取时刻与原始数值/配置来源时刻不得混淆；来源无法关联、代次/配置变化、未知/未来/过期、修订倒退或挂载前来源不能核实时输出unknown。不能凭文件mtime、调用者当前时间或原始字段默认0构造known。
6. 来源信息不足时，提供可审原因；允许无真实采样/未加载状态，不为了交付complete捏造数值。首轮无历史按288首轮规则处理，不因缺指标循环新建空窗。
7. 不新增文件/网络/进程侧效应或持久写入，采集结果由显式调用方接收；监听实现须可解除、不串session、不泄漏异常正文，不改变原生projection或session对象。计划投递、锁/ACK/会话管理及真实运行加载不在此模块实施。

### Python适配与内核集成验证

1. 明确采集schema，Python端只接受预期版本/已核验采集入口的最小快照；保可得性/非法/未知信息，校验同项目/目标/发起者/工作线/工作区/runner/home/launch/会话代次/当前模型配置和修订，不把外部任意快照当可信事实。可信宿主来源确认由调用方提供并说明本片不实现跨进程认证。
2. 显式`now`和最大年龄预算，无隐含产品级秒数默认。合法时生成288的`context_sample`，未知时生成明确unknown/原因并确保内核不误续；旧状态不可被读取动作刷新成新样本。容量和用量各自来源时间/身份需要核对，不宣称同请求原子性。
3. 接口只做适配，不改288实现/计划规则，不IO、不读环境、不调用模型；提供调用组合示例或集成测试实际调用冻结288统一入口，验证59.9%续用、60%换新、非法/缺失/过期/错会话模型代次unknown走新窗完整、无候选首轮无需旧指标、busy通道仍wait。不能只验证三个字段复制成功。
4. 采集器、规范化和实际内核入参之间不能存在会导致非法projected变成合法pressure的语义丢失；全链路用同批合成样本核验。每个失败原因审计字段明确，错误/日志不回显原始秘密、prompt或无关字段。

## 验收与原始证据

- 按冻结原生源码列出接口/事件/字段/版本的引用行、SHA及行为；通过可审查的模拟原生service/session或已核对的纯函数提取验证，不能启动真实DSH应用或把模型行为标通过。原生接口调用被实际执行（测试替身），不是只有未被调用的helper。
- 采集测试覆盖：服务/会话缺失、projection缺失、合法0、59.9/60边界、不合法和大整数、非finite序列化、旧/错session/模型/launch/代次/cut、字段来源独立更新、cached提示不当当前、重复/乱序/压缩后修订、不可变与解除监听/异常（如使用监听）。
- Python及跨语言链路覆盖原始语义、身份/来源/时间校验、known/unknown和288最终action；保原106项测试，不为凑数量加镜像测试。
- Node用内置测试工具或标准库；Python用`-B -X utf8`防冻结区pycache。安装源码只读，不导入原生应用入口；实际执行命令、原始输出和限制都落deepseek/evidence/。不得覆盖旧失败回执。
- 交付README说明公开入口/schema/挂载示例、哪些事实已核/未知、原生内存折叠及来源局限；`delivery.json`为talk-delivery-1、本次真实任务号，通过冻结workflow `validate ... --expect-task-id <本次号>`。最终TALK正文发送完整裸JSON，不只给路径；完成暂停，Codex首次独立实查，发现问题直接修正并自检。

本片通过只表示原生读取接口与规范化代码、离线链路验证成立；运行中DSH数值尚未采到时必须明确“未加载/未知”，不能称真实采集上线、原生会话续用、MCP增量交办、桌面同步或费用改善通过。用户手册在真实入口上线同片补齐，不编造按钮/步骤。

## 终端预算核对

已读[终端适配必查](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)：当前事实为受管headless入口，桌面65秒客户端上限不能直接套用。现有桌面T=65000ms/W=50秒/余量15秒及Codex当前W=300秒仅为既有约定，不是这片实测。当前headless MCP客户端T和是否已重载仍待核验；外层bridge任务预算与客户端工具T分开，不能等同。

本片不改终端/MCP配置、不调用主动wait、不开自动唤回；因此不宣称主动等待已适配。正常到期/API错误/取消和同连接排队边界本片未验，保留为后续终端适配证据要求，不因采集器单元测试或工具可发现判通过。
