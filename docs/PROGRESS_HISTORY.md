# 开发历史 · TALK

## 2026-10-07 I-1当前Codex入口加载通过；派#174给Kimi实施I-2页面退役

- 用户按重连说明后再次“继续项目”；目录实测九工具、新G1–G8与发起者/assignment弃用说明，实时list_agents注记一致。显式W=1秒false对已收取173立即matched（0.031秒、HTTP1/poll1），human true按G4拒绝，随后get173仍completed。当前入口I-1加载前置通过，原2026-10-07旧加载失败证据不覆盖，新增.tmp/initiator-mode-tools-loadcheck/2026-10-07-loaded.json。
- caller_identity仍human:bobo，requested passive/version4、effective null/not_bound，指定agent:codex/version13仅兼容回显；未改Key/模式/指定/任务状态、未新建加载测试任务。MCP stdio入口和uvicorn HTTP服务是独立进程层，单重启uvicorn不等于刷新MCP；本轮只认目录与运行时实测，不推断用户具体刷新操作。短路径不是Agent G8/主动消费者/长等待、取消排队或其它终端适配通过。
- 最新开发要求确认Kimi负责文字/设计/交互/前端、DeepSeek后端/其它并交叉复核；usage-gate continue但两精确百分比null，不臆测低使用率。I-1/I-2串行且同人工验收轮，本轮只派一个明确切片。
- #174“174-发起者模式页面与固定主控入口退役”给agent:kimi，初始queued/assigned，created_by=human:bobo，Hall group:task-9f7cb72a8f85454ca97934cb3a20bc4c。顶层最小参数；包.tmp/initiator-mode-ui-dispatch/task.md，基线237dfca/I-1功能1fbdf78/UI业务9272020，32来源对象SHA派前匹配，receipt/manifest留存。正式进度后续管理变化不构成业务基线更换。
- 任务按正式合同§6/7.1与I-2调用链逐项移除面板/徽标/绑定/CSS/app.js调用/模式对指定的依赖；保留模式human写/agent读、CAS/409/重试、164/165离页与在途行为、REQ2/角色说明隔离和其它任务交互。删除退役面板测试并以无入口契约承接，保留模式和实际接线/导航回归，四资源版本同步；后端/DB/权限/Key/MCP/配置/历史零改动。模型展示/身份切换/I-3/I-4排除。
- 执行者须完整自身174裸JSON交付并expect174校验，保留本地实现/runner/probe/日志与限制，开发后暂停、不写正式进度/不Git收尾；收到用户通知后才收取交付索引并另派DeepSeek独立实际代码审查，不在开发时并行审改、不把代码测试/DOM存根冒充用户页面验收。

## 2026-10-07 恢复核验：当前TALK MCP仍旧版，I-2未派发

- 用户“继续项目”后按决策角色恢复，I-1功能与正式文档1fbdf78已提交推送，工作区干净。当前目录仍九工具、wait G1–G7/controller_changed，无发起者与弃用说明；talk_list_agents实时返回旧固定主控注记，caller_identity=human:bobo、requested_mode=passive/version4、effective=null/not_bound，指定agent:codex/version13，均为读取事实，未修改。
- 最新development_requirements仍Kimi负责文字/设计/交互/前端、DeepSeek后端/其它并交叉复核。加载未通过，未派I-2；按实施计划须先重连现有TALK MCP入口并刷新会话，再核目录/运行时及短预算只读路径。未重连、改Key/模式/指定、试派、长等待或外推实际Agent G8/宿主适配通过。
- 只保存必要加载证据.tmp/initiator-mode-tools-loadcheck/2026-10-07.json，更新两份正式进度；源码/测试未改，不重复162项或既有审查。

## 2026-10-06 #173独立代码复核通过，收取I-1；当前MCP仍旧版待重连

- 用户通知“173 ok”。msg2675含前言+完整JSON，MCP摘要为unknown/自由文本，不从runner succeeded推业务结论；按项目兼容流程读取本地development.json并summary --expect-task-id 173校验通过，complete、10完成/0未完成/0blocked、7验证/5限制。稳定result_message_id2675/SHA806e422fdde69227b48394acf82a306b3a1595047f66d14aa75f0d25674c9464分两页无损读4254字符，嵌入JSON与本地包去schema比较一致；原消息/receipt/接受记录存.tmp/initiator-mode-tools-receipt/，原MCP unknown保持不追改。
- Kimi独立实读四份代码完整456/5/925/3行差异，六模块162项独立复跑无失败/错误/跳过，七项自写探针含宽松G7变异检出均通过。G1–G8/created_by与项目归属、严格输入/去重/日志、结构化404分类、首轮复用/模式重读/快照、false19键/query_stats/HTTP/错误文本、九工具/服务端权限和终端清单同步均通过，主控原25对象hash/大小全匹配，未重复整套测试或改代码。
- Codex对具体预算疑点补读正式§4.4、源码局部和独立P4证据，接受末次响应已完成整批核验且无需后续GET时进入首轮正常timeout；中途未核验完成仍按入口错误。该边界与“每次GET之后、发下一请求之前核预算”和socket非硬截止一致，补文档明确，不改变实现或原复核。tuple仅内部Python可达/公开JSON不产tuple，200非对象/缺归属安全拒绝，均接受独立结论。
- 收取173/172 completed（服务端原记录未补时区）：#173/msg2675：2026-10-06T15:55:30.704157；#172/msg2674：2026-10-06T15:55:35.028860。#173服务端unknown与本地有效complete并存，#172结构化complete自报/独立通过分开；旧设计166–171和167/169 partial原结论不追改。
- O1 WAIT_COUNTING_NOTE未显式枚举G8 GET但计数正确、O2 timeout_seconds描述超600报错与实际clamp不符且为旧基线文本，非阻塞登记I-3文字同步，本轮不顺手改已审代码。
- 本轮真实只读加载检查：ALL_TOOLS wait描述仍G1–G7/含controller_changed，list_agents无弃用且实际mode/assignment note仍主控会话/固定指定原说明。当前连接尚未加载I-1，不能用源码/--check自测充加载完成。caller_identity=human:bobo，effective null/not_bound、旧UI/自身Key/真实主动链路未变；client T/W/取消排队边界未新验证。
- 同步正式合同/实施计划/模块与项目简报/终端加载说明及进度，区分源码已通过和连接未加载、I-2/I-4待验收；四已审代码与正式记录本轮统一提交常规推送，原临时交付保留。依据实施计划“I-2必须晚于I-1加载”，本片收尾后先由用户重连TALK MCP（必要时重开会话刷新目录），再核目录/运行时注记/身份/短只读路径，不越过门禁新派I-2、不额外生产等待/试派。后续角色Key/指南/模型展示/命名按原排期。

## 2026-10-06 #172工具交付，派#173独立代码复核

- 用户通知“172 ok”。#172/msg2674完整合法talk-delivery-1/自身号匹配、complete自报，11完成/0未完成/0blocked，7文件/10验证/7限制，无省略；runner succeeded/submitted，finished_at=2026-10-06T14:45:27.610430（服务端原记录未补时区）。只是开发者结论，未独立验收/收取/提交。
- 实际四份工作区代码/测试差异1074增/315删：talk_task_tools（456行diff）、talk_terminal_mcp（5）、test_talk_controlled_wait（925）、test_talk_task_tools（3）；server/web/DB/API权限/Key/模式/配置/共享服务无改，talk_send_mcp核对无需改。开发交付.tmp/initiator-mode-tools/implementation、development、run_tests、test-log。
- 自报实现G1–G8/created_by+project整批入口核验、G6同响应active/G7严格输入及稳定去重/G8各唯一ID一次GET、结构化TalkApiHttpError/404业务拒绝/其它api_error、入口IDs日志来源、五键快照、受控无ID死分支退役、模式重读去指定依赖/controller_changed退役、兼容只读弃用注记与发起者文案。判断包含G8响应复用首轮、200非对象null拒绝、Pythonlist/tuple数组适配，独立复核须评估而非照采理由。
- 开发自报六模块37+17+12+44+31+21=162通过，无失败/错误/跳过；真实隔离SQLite+LiveTalkServer归属与只读性、普通false旧19键/query_stats/HTTP/日志兼容通过。主控只读完整交付，不重复全探索或跑全量；源码与运行中MCP分开，重连/旧UI/自身Key/真实主动链路not_run。
- 超出原清单的一处terminal_mcp wait_defaults.entry_gates由7改8及注释同步已如实上报；Codex看实际最小差异，明确纳本片配套范围保留并独立复核，不扩终端运行配置/默认预算/生命周期。原17派发来源未改项全匹配，Git实际HEADc2283b8，7ce→c228仅三主控记录，四业务差异未提交。
- 派前再次读取最新development_requirements，Kimi交叉复核DeepSeek开发不变、caller_identity=human:bobo。最小顶层参数派#173“173-发起者受控等待工具独立复核”给agent:kimi，queued/assigned，Hall group:task-d4b111b836824eafa7b68a66f061a71f；包.tmp/initiator-mode-tools-review-dispatch/task.md，派前25对象清单/四份Git基线源码快照/114128B development.diff已落盘。
- 复核按A–I实际完整代码/测试审查，不只看自报，独立复跑六模块及必要关键探针；重点G8请求前后/最后响应过deadline与入口失败统计、首轮复用计数/模式重读、数组边界/异常响应、false兼容和九工具/--check/文案/权限不变。自测启动器只静音logging并用标准unittest发现/结果/退出码，Kimi仍须独立核验，不污染原日志；隔离验证允许、不启动生产/模型/浏览器/长等待。
- 开发已暂停，审查只新增.tmp/initiator-mode-tools-review/报告/真实本号裸JSON及探针日志，不改源码/正式docs、不自行提交/收取/转派。若发现问题partial交回DeepSeek，原报告保留；通过才由Codex收取172/173并提交功能代码、检查加载后再排I-2。根代理本轮仅三份正式记录提交常规推送，四代码改动不入本轮提交；默认派后结束，用户通知173完成再取件。

## 2026-10-06 I-1工具实现派#172

- 以正式合同提交7ce331937a6b7eaae197cfcbd0886a14d0879f37为干净基线，业务仍9272020；再次读取当前development_requirements，DeepSeek后端/其它、Kimi独立复核，caller_identity=human:bobo。
- 派前17对象清单已保存.tmp/initiator-mode-tools-dispatch/source_manifest.json，含工具/分派、三测试、server归属证据、正式合同/计划/归档、模块/终端预算规范与171审查。最小顶层参数创建#172“172-发起者受控等待工具实现”，agent:deepseek，queued/assigned，Hall group:task-75a3a065edb045b29eb3109303e3ca22；实际server任务正文和开发要求快照存同目录task.md。
- 范围tool主文件/controlled_wait与task_tools测试，必要时terminal_mcp断言；send_mcp预计不改。按新G1–G8/created_by+project整批核验/strict ID顺序与计数/入口日志/结构化HTTP404错误/模式重读去assignment依赖实施；false逐字段/九工具/服务端权限/CAS兼容，弃用只读输出及bridge新快照/工具措辞，171两条非阻塞清单建议一并覆盖。
- 必要验证为完整本片受控/普通工具/terminal相关测试、假HTTP/模拟时钟与按需隔离端点，覆盖正式矩阵；不重复无关UI178/整库全量，不使用生产凭据/真实模式/长等待或重载共享服务。真实终端T/W/取消排队边界保留，不把源码单测当宿主验收。I-1/I-2后续同一人工验收轮，旧UI/自身Key/真实链路仍待后续。
- 交付.tmp/initiator-mode-tools/{development.json,implementation.md}及必要证据，实际本号完整talk-delivery-1裸JSON/格式校验，完成暂停。由Codex收件再派Kimi独立实际代码审查，审查后裁决收取/Git/文档；开发与复核不并行。根代理只补三份正式派发记录，业务差异不入本轮文档提交，默认派后结束、用户通知#172完成再取件。

## 2026-10-06 #171六项复核通过，收取设计链并发布发起者合同

- 用户通知“171完成”。#171/msg2673完整合法talk-delivery-1/自身号匹配、complete，10完成/0未完成/0blocked，2文件/9验证/5限制，无省略。DeepSeek独立实读R-1计数、R-2事件/符号、R-3常量、R-4校验位置/计数、R-5文档范围/历史、R-6日志来源均闭合，合看#167/#169已闭合部分无倒退，Codex接受设计。仅静态审查，不冒称未来实现测试或实机通过。
- 本轮顺序收取171/170/168/166，workflow completed（服务端原记录未补时区）：#171/msg2673：2026-10-06T14:10:23.130465；#170/msg2672：2026-10-06T14:10:26.664346；#168/msg2670：2026-10-06T14:10:29.831910；#166/msg2668：2026-10-06T14:10:34.359117。167/169原partial此前收取事实与失败原件保持，166–171设计链全部收取。
- 发布docs/spec/CONTROLLER_MODE_DESIGN.md为#170经#171已审v3正式合同，标题/发布头明确设计确认且未实施、草拟时HEAD/本片/未收取等历史限定；完整保留已审正文。配套INITIATOR_MODE_IMPLEMENTATION_PLAN.md，原固定主控合同原正文完整归档CONTROLLER_MODE_DESIGN_FIXED_CONTROLLER_ARCHIVE.md。发布溯源与原/source SHA/收取记录存.tmp/initiator-mode-publication/publication.json，原临时稿/报告不追改。
- #171两条非阻塞清单建议并入计划“Codex发布补充”：tests/test_talk_controlled_wait.py:1043/1046/1075同步G1–G8/controller_changed退役/任务发起者计数说明；talk_task_tools.py:1684-1690模式描述按发起者措辞同步，字段/effective语义保持。只补实施清单，不重开设计或权限。
- 发布前主控实测30对象hash/大小一致、工作区干净/HEAD795473d；归档保留旧合同原正文校验通过。171的Git CLI受限而用只读.git对象证据，主控另查实际HEAD。33/30静态定义数不是通过数；本轮无实现测试/模型/浏览器/服务/真实等待/Key操作。
- usage-gate返回continue，精确session/weekly百分比null；不根据reason推断具体额度，按批次约束。最新development_requirements仍DeepSeek后端/其它、Kimi文字/设计/交互/前端、交叉复核。下一项I-1工具实现可独立于I-0凭据实切开展，之后I-2退役UI，I-1/I-2串行独立复核及同一人工验收轮；I-4需自身身份/工具加载/UI/指南齐备。
- 设计发布不改变业务基线9272020、旧固定主控门禁/UI、server/DB/权限/Key/模式/共享服务，caller_identity仍human:bobo、effective null/not_bound。历史creator不迁移，实际Key切换和真实主动链路待后续；各终端T/W/取消排队边界保持。模型展示/命名另片。正式六份文档收尾提交，随后按合同派下一工具片。

## 2026-10-06 #170六项修订交付，派#171独立定向复核

- 用户通知“170完成”。#170/msg2672完整合法talk-delivery-1/自身号匹配，complete为自报，8完成/0未完成/0blocked，4文件/7验证/4限制，无省略；runner succeeded/submitted，finished_at=2026-10-06T13:38:02.574099（服务端原记录未补时区）。尚未独立确认，#166/#168/#170未收取、新合同未发布。
- 四文件位于.tmp/initiator-mode-design-final-fix/：contract_draft.md（48615B/f05206338b3a6be069985fb21c167b02c750ded11b62b6acf80391c5225c6011）、implementation_plan.md（28304B/b0a06caf391b7f187bf6cf13425d8ae5247f4f6fe4f2f5d58e40893dab9bcecc）、changes.md（14987B/e43d04b48c5c3a9e96460b7166f9304d3881eb2e6649ebe994fe7f16c6cb5a74）、development.json（7473B/ad4d11fcc87dbea7e6ccfa842dd81149ea51f307b12994ca1a3e005af546c7bd）。旧#166–#169原件保持，新稿在#168底稿上定向修改。
- 自报R-1静态test定义33/30、宽搜35/39误计/无循环展开/本片未跑测试/历史mode30分开；R-2事件删1497-1509完整、保留模式1510-1520，补退役grep符号；R-3改CONTROLLED_WAIT_NOTE；R-4落实G7校验位置和到达G7非法输入恰2HTTP/0任务GET/entry null与外层schema边界；R-5补MODULE_webui:274及MODULE_bridges历史保存/新实施说明；R-6输入完整校验前None/null、通过后稳定去重ID与G8日志不泄漏响应。原D-1..D-4、预算/失败/兼容/过渡/独立复核等不回退，均待#171确认。
- #170验证仅静态定位、26对象开工/结束hash与自身task_id格式校验，实施/浏览器/模型/终端/服务/真实等待/Key均not_run；用例静态数不是通过数。主控核对原26对象hash/大小一致、新四文件hash登记、工作区干净/HEADc835591，91b2bf2→c835591仅三份主控记录，业务保持9272020。旧审查HEAD/原partial不追改。
- 派前读取最新development_requirements，Kimi文字设计交互/前端、DeepSeek后端/其它、双方交叉复核不变，caller_identity=human:bobo。最小顶层参数派#171“171-发起者调度合同六项修订定向复核”给agent:deepseek，queued/assigned，Hall group:task-2be42a04587a49d4a2d551f5ba8f30a5；包.tmp/initiator-mode-design-final-review-dispatch/task.md及派前30对象清单（原26+#170四文件）已落盘。
- 审查只新增.tmp/initiator-mode-design-final-review/{review.md,development.json}，逐R-1..R-6回相关源码/文稿、差异直接回归与30对象hash，沿用#167/#169已闭合部分，不重新完整旧审查。核对校验/统计/日志/active输入顺序和false兼容；历史引文与当前规范、自报修复与旧partial区分。不运行未来实现/实机，不转派收取，真实本号裸JSON/格式校验，完成暂停由Codex裁决。
- #167/#169原partial已收取事实保持，#166/#168/#170通过新审查并合看后才收取/发布/拆实施。当前业务/测试/DB/API/权限/UI/配置/Key/共享服务零改动，effective null/not_bound及终端实T/W证据边界保持；模型展示/命名另片。本轮三份正式记录收尾提交常规推送，默认派后结束、用户通知#171再取件。

## 2026-10-06 #169复核六处残余，收取partial并派#170定向修订

- 用户通知“169好了”。#169/msg2671完整合法talk-delivery-1/自身号匹配、partial，11完成/6未完成/0blocked，2文件/6验证/5限制，无省略。独立实际源码/文档核对P1-2/P2-1/P2-2/P2-4/P2-5及A/C/F直接回归主体闭合，但P1-1未完全闭合。Codex接受六项发现，不发布新合同、不收取#166/#168。
- R-1：contract:59、plan:68/69、changes:21用35/39计入正则.test()，实际静态test定义33/30且无循环展开，历史mode30/30须独立说明。R-2：plan:58漏workspace1497-1499清空按钮调用旧saveControllerAssignment，删除范围须1497-1509而保留模式1510-1520；grep门禁须补save/loadControllerAssignment、controllerEl、CONTROLLER_STATUSES、clear/candidate元素。R-3常量CONTROLLED_WAIT_NOTE误拼；R-4严格校验位置/计数未定；R-5遗漏MODULE_webui:274及MODULE_bridges退出方式；R-6进入日志task_ids来源未定。
- Codex抽验静态33/30、宽搜35/39、事件边界/旧调用证据一致，主控工作区干净/HEAD91b2bf2、原19对象hash/大小匹配。#169报告旧HEAD9e3e34d保留；仅静态审查、无测试/服务/终端/模型/真实等待/Key操作，数量不是通过数；reviewer git status受限，主控另核。原报告和#166目录当时观察均不追改。
- 收取#169/msg2671于2026-10-06T13:19:35.662576，workflow completed，原业务partial保持（服务端原记录未补时区）；#167原partial已收取事实保持，#166/msg2668/#168/msg2670仍submitted/未收取。
- Codex明确R-4：运行时G7严格校验在G6 active之后，不保留true1253宽松正规化；前门禁全过/到达G7非法输入HTTP恰2、任务GET0、entry_gate=G7/return_reason=null/恰一条entry，无正常返回；更早门禁拒绝按各自计数，外层schema拒绝不虚构本函数日志。R-6：true selected_task_ids初始None，G7完整合法后才稳定去重赋值，之前/非法日志task_ids=null；G8记录调用者合法去重列表，不落任意非法原输入或未核验任务响应；false原行为不动。均为待实施精确裁决。
- Codex纳MODULE_webui:274入I-3；MODULE_bridges:214-220保留旧C2-A1历史事实并新增新实施规则/替代说明，204/210旧日期与600/660沿用212现行预算覆盖，不机械删除普通协调称谓。D-1..D-4/404与API错误/预算与入口字段/true死分支/legacy保留/I-1和I-2共同人工验收轮等已闭合内容不重开。
- 派前读取最新development_requirements仍Kimi文字设计交互/前端、DeepSeek其它/后端，交叉复核；caller_identity=human:bobo。最小顶层参数派#170“170-发起者调度合同六项残余定向修订”给agent:kimi，queued/assigned，Hall group:task-6b3b8815151a48dca6741ee6c014de3c；包.tmp/initiator-mode-design-final-fix-dispatch/task.md与派前26对象快照（原19+审查2+模块2+页面测试2+talk_send_mcp）已落盘。
- #170只新增.tmp/initiator-mode-design-final-fix/完整合同/拆分/changes/development，六项必要定位/计数与完整性校验；旧#166–#169原件/业务/正式文档/测试/DB/API/配置/Key/共享服务只读。真实本号裸JSON、格式校验、完成暂停再交DeepSeek定向复核。新合同未发布，业务同9272020，身份切换/模型展示/命名另片。
- 本轮仅三份正式进度/裁决/派发记录，差异检查后中文提交常规推送，默认派发后结束、用户通知#170完成再取件。

## 2026-10-06 #168合同修订交付，派#169独立定向复核

- 用户通知“168 ok”。#168/msg2670完整合法talk-delivery-1/自身号匹配，complete为结构化自报，12完成/0未完成/0blocked，4文件/6验证/5限制，无省略；runner succeeded/submitted，finished_at=2026-10-06T12:14:53.321339（服务端原记录未补时区）。不将自报当独立验收，#166/#168仍未收取，新合同未发布。
- Kimi仅新增.tmp/initiator-mode-design-fix/四文件：contract_draft.md（44197B/c41cf55b4ffa0e8ab2020c16d8fd51169e5ef32fb385de478b48eb1237ea667b）、implementation_plan.md（23322B/1a2723fefa8995a2e27919c55db2e0184eb7f17a4934f14dc0fcb81b9e0f3c34）、changes.md（17228B/49a042505588a239966604d107e4841a58655f9c22a509236933ddf1fcc547a6）、development.json（8279B/2a7c1495e48917139a4c46eb4668f9f2f2a52b157ba437158489278ad72c4dc6）；旧#166/#167原件及正式合同保持。
- 自报补齐两P1：I-2 load/render完整接线、模式面板controllerStatusMeta共享依赖及导出/徽标/测试去留；bridge新任务要求快照、每次等待计数说明、工具描述及注记退役。五P2：严格ID/稳定去重；任务404业务拒绝与其它API错误、预算耗尽、入口计数/信息；精确活跃文档与历史排除；工具/UI串行且共同人工验收和加载/身份前置；true无ID死分支移除及现有用例存在性。G6 active前置、G7输入、G8逐任务核验与旧编号映射，另补行号/TaskOut/api_error/入口键/目录事实等直接措辞。设计D-1..D-4不变，TalkApiHttpError为待实施建议，不称现有事实。
- 验证仅静态源码/文档核对、15对象前后hash、自身task_id格式校验；实现测试/浏览器/模型/服务/真实任务/等待/Key均not_run。用例计数非通过数，部分UI函数区间近似已披露，原#166目录不存在观察不追改。本轮主控核对旧15对象全匹配、工作区干净、HEAD9e3e34d；#168HEAD603538b→派时9e3e34d仅三份主控记录，业务保持9272020。
- 派前读取最新development_requirements，Kimi文字/设计/交互/前端、DeepSeek其他/后端、交叉复核要求不变，当前caller_identity=human:bobo。最小顶层参数派#169“169-发起者调度合同修订定向复核”给agent:deepseek，queued/assigned，Hall group:task-a20f356f11234398b837730fcb367eb8。包.tmp/initiator-mode-design-fix-review-dispatch/task.md和派前19对象快照（10源+#166三稿+#167两报告+#168四文件）已落盘。
- 独立审查七项和直接回归，回源码核对新稿不能仅采信自报；沿用#167已闭合A/C/F，核对真实调用/导出依赖、输入/HTTP失败与false兼容、预算/入口信息、活跃文案精确退役、过渡/身份前置与旧用例事实，静态数量和历史通过数分开。不重复完整原审查、不跑未来实现/真实链路。仅新增.tmp/initiator-mode-design-fix-review/{review.md,development.json}，真实本号裸JSON交付、格式校验，完成暂停。
- #167原partial已收取事实保持（2026-10-06T11:55:16.374963）；#166/#168通过#169并合看后才收取/发布合同/拆实施。当前业务/权限/DB/API/UI/配置/Key/共享服务零改动；模型名称另片、命名留全角色页。默认派发后结束，用户通知#169完成再取件，本轮三份正式记录收尾提交常规推送。

## 2026-10-06 #167合同复核发现缺口，收取partial并派#168定向修订

- 用户通知“167 ok”。#167/msg2669完整合法talk-delivery-1、自身号匹配、partial，11完成/8未完成/0blocked，验证12/限制6，无省略。独立回源码抽验成立、10源+3稿hash命中、A/C/F已闭合、B/D/E/G仍有缺口；Codex接受具体发现，#166不收取、不发布有缺口草稿，不从runner succeeded推通过。
- 两项P1：I-2未列app.js reload/renderController调用点、模式面板/导出controllerStatusMeta及指定状态依赖，照删除清单会ReferenceError/回退已验收模式；退役文案遗漏bridge PROJECT_REQUIREMENTS_SNAPSHOT_NOTE/WAIT_COUNTING_NOTE/工具“主控派发”，旧称呼继续输出和写入新任务。五项P2：非法/重复ID规则、逐任务GET失败/预算/不可见措辞、I-3精确活跃文档与历史排除、中间上线窗口、true无ID死分支与旧用例去留；另有行号/API错误口径/TaskOut/前置active/entry键等非阻塞建议。
- 独立复核未跑测试/服务/终端/等待/Key，用例计数不代表通过；reviewer git status沙箱拒绝，主控另查实际HEAD603538b/工作区干净，e9eed23之后仅三份记录，原13对象hash一致；新返修15对象快照已在派发前落盘，包含原稿和原审查。原166/167报告/观察不追改。
- 收取#167/msg2669于2026-10-06T11:55:16.374963，workflow completed（服务端原记录未补时区），原业务partial保持。#166/msg2668仍submitted/未收取，旧#164/#165人工验收及收取事实保持。
- Codex按独立可行性结果确定D-1只读输出至少一兼容版本暂留弃用、D-2保持拒绝human受控主动不新开提案、D-3true严格显式正整数列表/全校验后稳定去重/唯一ID各GET一次、false旧行为不变、D-4旧human PATCH暂留兼容弃用。同时I-1/I-2串行审查并同一人工验收轮、过渡不宣称主动消费者通过；404进入业务拒绝/null与其它API错分开，不泄露不可见存在性；当前只是已定设计，不是已实现。
- 派前读取最新development_requirements仍Kimi文字设计/DeepSeek交叉复核，当前Key身份human:bobo。最小顶层参数派#168“168-发起者调度合同缺口定向修订”给agent:kimi，queued/assigned，Hall group:task-8fd33bb4bcf7467687c5b966964bf6d1。包.tmp/initiator-mode-design-fix-dispatch/task.md、15对象快照同目录；新交付.tmp/initiator-mode-design-fix/完整合同/拆分/changes/development。全部旧稿/正式文档/业务/配置只读，未改实际Key/UI/服务。
- 任务要求逐P1/P2及直接措辞关闭，补全部共享依赖与活跃文案清单/历史排除、输入/预算错误矩阵与可靠HTTP判码、阶段加载/回退和受控死分支旧用例退役，前置active节约任务GET；仅静态引用/源码/交付校验，不冒称未来实现测试已过。完成暂停后再交DeepSeek定向复核，合看#167已闭合内容后裁决发布与实施。
- 本轮仅PROGRESS/HISTORY/路线图正式收件/裁决/派发记录，UTF-8、明确范围/差异检查后中文提交常规推送；源/旧稿/原审查未变。默认派后结束，由用户通知#168完成再取件；模型上报/页面名称与全角色命名仍另片。

## 2026-10-06 #166合同草稿交付，派#167独立源码与合同复核

- 用户通知“166完成”。#166/msg2668完整合法结构化talk-delivery-1、自身号匹配、complete自报，7完成/0未完成/0阻塞，验证5/限制5，无省略；runner succeeded/workflow submitted，未收取。三份临时草稿不代表新规则已实现，不以格式自报代替独立业务验收。
- Kimi仅新增.tmp/initiator-mode-design/contract_draft.md（28521B/sha a449daee4edc6425e36de4de6c1652d1469fe77356e87336e68e77012214a21e）、implementation_plan.md（8246B/sha db04be5168b74b4aadfee2f38238f77196896e4825c45ab4ebc576ccee7cc577）、development.json（4782B/sha3167554f85759ff31c004cf2571f46bb01ff6346569715b59fa14d53b9a2fa8b）。工作区干净，正式合同/业务/DB/API/运行配置/凭据无改。
- 自报草稿覆盖created_by协调归属、新G1-G8/显式非空task_ids/同项目同creator整批核验、controller_changed退役和普通wait兼容；权限/历史human身份衔接、最小兼容退役、分步加载、预算与I-0..I-4拆分明确。D-1只读assignment暂留弃用、D-2保持human受控拒绝、D-3显式task_ids、D-4旧human PATCH暂留弃用列裁决；主控交独立审查，尚不发布/操作。
- #166自报基线9272020，收件实际e9eed23仅六份主控验收/派发文档变化，业务零差异。报告称原派发快照目录不存在；主控收件核对目录现存在，10文件hash/bytes与当前一致，原观察/报告不追改，不因文档HEAD变化误判源码漂移。新审查13文件对象快照存.tmp/initiator-mode-design-review-dispatch/source_manifest.json。
- 派前重读最新development_requirements仍Kimi文字设计/DeepSeek交叉复核，当前身份仍human:bobo。最小独立顶层参数派#167“167-发起者调度与固定主控退役合同独立复核”给agent:deepseek，queued/assigned，Hall group:task-66b3bee677e147c098824090256f1826；包同新目录task.md，交付.tmp/initiator-mode-design-review/，禁止修改原稿/正式文档/业务或实际切Key。
- 独立任务要求核对真实创建/可见性/collect/Key身份事实、单多ID与混合creator/跨项目/部分不可读、门禁兼容/模式退出/统计/deadline和matched边界、历史任务收尾/分步加载、退役API与UI兼容、I-0准备到实际切换节点、预算/取消排队与能力未实测标识。仅实际源码与合同矩阵/文档检查，不重跑全功能或把未来测试称已通过；发现阻塞返Kimi，非阻塞建议单列。
- 本轮PROGRESS/HISTORY/路线图收件派发记录UTF-8写入、范围/差异检查后中文提交常规推送；原稿/源对象保持不变，#166未收取，#164/#165验收事实保持。默认派发后结束，用户通知#167完成后裁决、正式发布再拆实施片。

## 2026-10-06 用户验收#164/#165通过，派#166发起者调度合同修订

- 用户明确“验收通过，继续下一项”。Codex记录本次离页复位/去版本两条人工反馈验收通过，功能92720207702db8603f49506a15d25cf194e8b0cb已推送、工作区干净；不将该确认外推为键盘/:has/HTTP竞态/Agent密钥只读或受控GET故障全部实机通过。已收取#164/#165保持completed，不重复收取。
- 按已确认路线，先修订按任务created_by发起者协调、项目统一主被动只影响发起侧、取消固定主控的实施合同，再拆身份/工具/UI/消费者；模型名称另案。派前读取最新development_requirements仍Kimi文字设计/DeepSeek交叉复核，当前入口caller_identity仍human:bobo，未改Key。
- 最小独立顶层参数派#166“166-发起者调度与固定主控退役实施合同修订”给agent:kimi，queued/assigned，Hall group:task-9269233cd1da4f5a89ea88f171e0d968；包.tmp/initiator-mode-design-dispatch/task.md、源码快照与旧合同副本同目录，交付.tmp/initiator-mode-design/。Kimi仅写contract_draft/implementation_plan/development三项，完成暂停，之后DeepSeek独立核对实际源码与新旧合同，不自行开发、派发、收取或commit/push。
- 合同必须闭合任务发起者资格/单多任务与混合creator/跨项目/字段缺失、controlled_wait=true新门禁及每30秒重读/退出/统计、普通wait兼容与agent入口限制、现有权限/历史human任务收尾、原指定字段/API/MCP/页面退役兼容、身份配置安全核验、C2-C分步加载与预算/取消排队验证矩阵。不新增会话绑定/ACK/租约，不让目标角色或模型名自证协调者。
- 角色仅针对具体任务，授权和决策分级仍保留；active不允许执行者自行开新任务。各Agent自身API Key是后续接入目标，历史created_by不改/普通收取不扩权；模型上报与全角色命名不纳本片。TERMINAL_MCP预算段已按要求读取，任务包明确DeepSeek50/Codex现用300与未核验T/模板边界。
- 正式PROGRESS/路线图/简报/模块及QA记录普通反馈验收与#166下一片，当前旧主控门禁/服务/凭据均未更改；完整草稿待独立复核后才发布现行合同。文档UTF-8写入，范围/差异检查后中文提交常规推送，默认派发后结束，由用户通知#166完成再取件。

## 2026-10-06 #165独立复核通过，收取#164/#165并收尾人工反馈修正

- 用户通知“165好了”。#165/msg2667完整合法talk-delivery-1/自身号匹配/complete，8完成/0未完成/0阻塞，验证9/限制5，无省略；非仅runner状态判验收。独立实际源码/真实导航事件与生命周期检查、必要复跑覆盖#164两条人工反馈，0功能缺陷。Codex核对对象一致与具体争议后接受实现，页面尚待用户再验。
- #165新增临时probe_wiring.cjs加载真实workspace.js与抽取app.js导航函数，经真实事件处理器验证群聊/具体角色/任务/任务Hall/关黑板/项目/账号7类入口，离页清未保存selection、返回已确认saved、全程0PATCH且其它草稿保持；33/33断言通过。保存按钮一次PATCH/正确expected_version、在途离开/续选/迟到成功失败/A→B→A/账号不串不锁独立验证成立，app.js/CSS无改。
- 独立复跑模式30/30、十二份workspace Node178/178（进程内）、恢复7/7与12/12、集成15/15、Python四页面契约12/12、语法均通过。默认隔离spawn EPERM导致用例未执行，如实not_run不判业务失败，不把开发者默认隔离自报当独立证据。不重跑98后端/全库/C2-A1。
- 复核开始d8c3635、结束51c3035中间仅三份主控文档；本次收尾HEAD8ce30c2相对51c3035也仅四份计划文档。业务原8文件+205/-18与基线946490f一致，收尾前11文件sha/bytes与派发快照相符（复核报告核对10文件，主控额外核对workspace.css），未更换审查对象。
- 非阻塞P3-1手册错误已裁决：原manual_draft.md称“两窗口同值可能不409”错误；Codex按server/routes/projects.py:519/548-556核对，陈旧版本无论同值/异值均409，合法当前版本同值才200；若点选等于本地saved前端不发PATCH。正式USER_MANUAL改可靠步骤：两窗口初始被动，A保存主动，B保持旧已保存被动、不刷新再选主动保存，即旧版本409只GET刷新；列可跳过人工未测。原#164包/原历史中旧判断保留纠正索引，不追改。
- 非阻塞P3-2离页返回提示区空字符串不是功能缺陷，radio/已保存行/禁用保存已经明确配置，本次不扩业务打磨。真实浏览器视觉/键盘/:has/HTTP竞态未测；Agent只读需管理员现成密钥、409后GET失败需受控故障，普通用户可跳过列未人工验证。新接线探针仍DOM存根，不冒充浏览器验收。
- 收取#165/msg2667于2026-10-06T10:45:05.197670，#164/msg2666于2026-10-06T10:45:08.837644，workflow均completed（服务端原记录未补时区）；原#160–#163也已收取，不重复收取。正式合同/模块/用户手册/简报/路线图及QA同步离页丢弃、同页保留、在途真实结果/去版本而CAS保留；PROGRESS收短为页面待验收与后续索引。
- 静态资源20261006-controller-mode-c2b-ux四处一致，后端/API/DB/MCP/运行配置/凭据及真实指定权限未变；强刷新现有页面即可。用户验收两方向未保存离页复位、任务/群聊/具体角色三入口、显式保存往返保持、已保存状态无版本、同页面选择保留，主动仍意向不自动生效。
- 本轮明确暂存15文件（8业务/测试/QA+7正式文档），源码/测试与已审快照一致，仅Codex追加QA证据/文档。差异与范围检查后中文提交常规推送，提交以Git收尾版本为准；不强推/改历史。已登记发起者调度/取消固定主控/各自API身份/模型名称展示/全角色名称规则后置均仍计划，不借本轮实现；里程碑暂停新开发等页面验收。

## 2026-10-06 用户确认后续计划：发起者调度、模型展示与成员名称暂缓

- 用户明确要求把前述主被动/主控讨论结果、获取模型名称并替代页面裸成员ID展示加入后续计划；同时新增成员名称来源问题，留到完整角色页面再考虑。Codex按决策职责维护现有正式文档，不派新任务/不改当前#165复核包或业务。
- 已登记方向：具体任务发起者created_by即协调责任归属，任何已有权限且获授权的Agent可发起；项目统一主被动只影响发起侧，执行/复核正常完成任务、在途任务保持。后续去掉固定项目主控标签/选择，同步受控等待按任务发起者核验、UI/MCP/指南/测试；不是仅改提示词或删按钮。旧指定字段兼容、混合发起者等待/历史收取衔接仍须实施合同明确。
- 用户指出human:bobo源于Codex当前使用人类API Key；只读talk_list_agents再次确认caller_identity为human:bobo/kind human。后续各Agent用自身Key、服务端反查并验证新任务发起者准确，当前未改凭据；原历史归属不追改。
- 模型能力检查：Member有display_name，AgentInstance只有runtime/status等、无模型字段；现有MCP列出的是CLI Bridge注册显示名，不能当具体型号。Kimi支持启动model参数，Codex现有桥沿用运行器配置；未询问/启动模型、没有已确认具体型号。后续从实际运行端获取可核实模型并上报，配置值与实际会话型号区分、切换更新/无信息降级；页面改展示，内部member_id鉴权/关联不改。
- 当前自定义display_name与模型名、运行器、业务角色分别处理；默认/自定义名称和重名区分留全角色页面设计，不提前定名或批量改名。详细计划写DEVELOPMENT_ROADMAP新节，PROGRESS短索引与PROJECT_BRIEF恢复入口同步；旧合同已实现事实/旧交付保留。
- 排期保持先#164/#165复核及人工反馈验收，再按新方向修订消费者/身份合同并按最新开发要求拆片；不直接按旧固定主控C2-C任务继续。本轮四份文档显式UTF-8写入、diff检查与读取核对后单独中文提交常规推送，#164八个业务/测试/QA文件不纳入。此为计划记录，无功能上线/页面人工验收或凭据调整。

## 2026-10-06 #164交付，派#165离页复位与文案独立复核

- 用户通知“164好了”。#164/msg2666完整合法结构化talk-delivery-1、自身号匹配、complete自报，5完成/0未完成/0阻塞，无省略；runner succeeded/workflow submitted、未收取。Kimi开发结束暂停，格式与测试自报不替代独立实际代码验收。
- 实际8跟踪文件+205/-18：workspace.js +15/-4、模式Node测试+167/-6、index四资源版本+4/-4、controller Python契约+8/-1、三Python版本断言各+1/-1、design-qa+8/-0。业务稳定946490f与收件HEAD d8c3635间仅三份主控文档；8文件sha/bytes吻合实施说明，连同app.js/style.css/workspace.css快照存.tmp/controller-mode-c2-b-ux-review-dispatch/source_manifest.json，开发未改app.js/CSS。
- 自报!visible清模式selection，未触碰request/saveToken/saving，原生命周期接线复用；同页保留，返回按确认saved，保存在途真实结果仍可入账；状态行去版本但CAS保留。静态资源20261006-controller-mode-c2b-ux。具体接线与迟到边界交独立审查，不由Codex重复完整审码。
- 开发者自报模式30、十二份workspace Node178（默认隔离与进程内）、四Python契约12、恢复7/12和集成15及语法通过；本片后端未改未重跑98。真实浏览器视觉/键盘/HTTP竞态未测，DOM存根不外推实机通过。原集成探针仅id接线、实际重试目标须源码核对，不重复旧证据措辞。
- 最新development_requirements已读仍Kimi前端/DeepSeek交叉复核。最小独立顶层参数派#165“165-调度模式离页复位与状态文案独立复核”给agent:deepseek，queued/assigned，Hall group:task-554148e9af934cfa9f81105159a4cda8。任务包.tmp/controller-mode-c2-b-ux-review-dispatch/task.md；独立交付.tmp/controller-mode-c2-b-ux-review/。限定新增量/真实离页接线/同页不吞选择/在途续选/迟到项目账号安全与CAS/恢复回归；复核期禁止并行改业务。
- 草稿普通验收涵盖两方向离页复位/显式保存保持/状态行去版本。409两窗口步骤可能同值成功不触发，任务要求独立判断可靠步骤或列未测；Agent现有密钥只读/409后GET失败可跳过列人工未测，不造账号/断网/改配置。正式旧文档含版本待复核通过后同步，不提前称人工通过。
- 用户确认主控边界：目前是长期责任指定，硬关联主要为受控主动等待；普通派发现有权限未收紧，DeepSeek桌面仍可在用户授权下派发。本次仅解释，不新增独占派发权限/主动执行。保存active仅意向、effective仍null/not_bound。
- 本轮仅PROGRESS/PROGRESS_HISTORY/DEVELOPMENT_ROADMAP收件派发记录，明确暂存三文件中文提交常规推送；#164业务八文件不提交。默认派发后结束，用户通知#165完成再读取裁决；#164未收取，C2-C不启动。

## 2026-10-06 用户人工验收反馈，派#164离页复位与文案简化

- 用户实际发现：已保存被动，选择主动未保存，切其它页再返回仍选主动，容易误判当前配置；比较保存值标记/离页重置两种方式，倾向第二种。Codex采纳离开项目设置放弃模式未保存点选、返回已确认保存模式；用户明确要求状态行去“（版本 2）”只留模式名。属于人操作发现的新反馈，不推原C2-B人工验收通过。
- 用户询问“Agent只读；冲突后读取失败时重试可见、保存暂禁、读取成功后明确保存”含义与操作。解释前者为现有Agent密钥登录只能查看；后者是两窗口版本冲突且GET再次失败的边界恢复，不是每次保存均需重试。普通用户无现有Agent密钥或受控故障条件可跳过并列人工未测，不要求新建账号/故意断网。原独立代码/探针验证与用户实机验收分开。
- 本次开工HEAD946490fc34601d1b5e38830a29eaef385b105529，工作区干净，原C2-B功能已提交推送；#160–#163已收取，不重派/重收原任务。派前重读最新development_requirements仍Kimi前端/DeepSeek交叉复核、Codex范围与收尾。
- 最小独立顶层参数派#164“调度模式离页复位与状态文案简化”给agent:kimi，queued/assigned，Hall group:task-ec14aaa7567344c19ea252811c4c376f；任务包.tmp/controller-mode-c2-b-ux-dispatch/task.md，交付.tmp/controller-mode-c2-b-ux/。完成暂停后另派DeepSeek独立复核，原#161/#163证据不追改。
- 任务包定义真实可见→离开边界（任务/群聊/具体角色/项目账号）、无离页自动PATCH/确认弹窗、返回匹配确认保存值、同页重绘不吞选择；保存在途/续选后离页/迟到成功失败/A→B→A不串不锁。删展示版本仍保留内部CAS/安全整数/响应核实；原409 reloadNeeded及GET-only/暂禁保存、旧服务/agent只读/独立CAS/其它编辑器草稿/单分隔线不回归。
- 范围仅模式状态与必要最小app.js生命周期接线、相关行为/契约测试、资源版本四处一致与design-qa；正式合同/手册在代码落实并独立复核后同步。要求新验收草稿区分普通两条反馈与可跳过边界；两窗口同值可能不触发409，步骤需可靠或标未测，不能冒充人工通过。不扩C2-C/后端/运行配置/权限/服务生命周期。
- 本轮仅三份正式进度/路线图派发记录，UTF-8写入并差异检查后中文提交常规推送，Codex不操作浏览器/不重复完整探索审查；默认派发后结束，用户通知#164完成再取件/安排DeepSeek复核。尚未落地新离页行为，现有用户手册/合同不提前写为已可用。

## 2026-10-06 #163定向复核通过，C2-B实现确认并收取，交人工页面验收

- 用户通知“163 ok”。#163/msg2665合法完整talk-delivery-1、自身task_id匹配、complete、6完成/0未完成/0阻塞、验证10/限制6，无省略。实际独立复核F-1/F-2增量/全部状态生命周期、直接回归与版本/手册恢复，非只采信开发者；Codex合看#161原片主体A/B/D及C/E其余独立审查和#163定向结论，确认C2-B实现通过，两项关闭，不从runner或格式单独推业务验收。
- F-1：409置reloadNeeded，重读失败保持；重试真实绑定workspace.js:1503→loadControllerMode只GET，无自动PATCH；保存按钮/函数双重拦截旧CAS，成功读取清位并更新安全版本后由用户明确保存；反复失败仍可恢复，400/422/500/404/缺字段/未知模式/unsafe/agent不误置位；项目账号/request/saveToken和迟到纪律未变。F-2：design-qa入库记录首次:has/无本地降级、旧浏览器选中/禁用样式缺失、原生radio可用、实机未测。
- #163独立Node语法、新增23、九文件153（--test-isolation=none）、原恢复7/7、新恢复12/12、集成15/15、Python四页面契约12/12通过；开工/结束10文件sha/bytes一致，修前文本与#161 manifest相符，增量+18/-5、+108/-2、+3/-2及5文件资源版本/直接断言一致，app.js/css未变。默认Node逐文件隔离在复核沙箱spawn EPERM，Kimi双模式自报不算默认隔离已独立确认；不重跑98后端/全库/C2-A1。
- P3-1证据措辞：#162 implementation/development称集成探针核实重试调用目标，但原探针只覆盖id接线。真实绑定只GET由#163源码核对成立；Codex在design-qa/模块/本记录澄清，不改#162或#161原件，不返业务开发。P3-2重试GET在途短暂未保存文案/保存禁用为非阻塞可选UX，本片不扩改。
- 主控收尾前复验10/10源码/QA hash与#163快照一致，无替换审查对象。依次收取#163/msg2665（2026-10-06T03:59:09.896485）、#162/msg2664（03:59:11.904748）、#160/msg2662（03:59:13.849989），workflow均completed，时间为服务端原记录未补时区。#161此前已收取02:58:18.859405，原partial保留；#162混排MCPunknown保留，本地合法complete/原JSON与本地一致和独立修正验收分开，不追改历史结论。
- 用户手册新增“调整项目调度模式”与409自动重读失败的只读重试/暂禁保存/成功后明确保存步骤，当前边界补保存active只意向。同步PROJECT_BRIEF、MODULE_webui、CONTROLLER_MODE_DESIGN状态和路线图；PROGRESS收短为当前里程碑/限制/证据索引/后续，原历史详情保持。design-qa新增独立证据、默认隔离限制和P3-1澄清。
- 当前静态资源20261006-controller-mode-c2b-f1四处一致，现有服务无需重启，浏览器强刷新即可。入口角色→项目设置→调度模式，现有human密钥可操作/agent只读，管理员提供现有密钥，不新建测试账号/变更真实项目配置。人工验收覆盖两态显式保存及刷新保持、实际执行仍无生效、无主控提示、两窗口冲突/GET失败恢复、具体角色/任务群聊互斥、单分隔线/窄屏/键盘；浏览器视觉/:has外观、真实HTTP竞态未实测，不能称页面验收通过。
- 业务源码/测试9文件与#163已审快照保持；Codex仅QA证据说明/7份正式文档聚焦收尾。必要验证沿用独立结果，统一diff --check、源码hash和明确暂存17文件检查后中文提交并常规推送授权origin codex/terminal-return-codex；未改后端/API/DB/MCP/bridge/运行配置、实际模式/指定/权限、服务生命周期，不新增主动链路/取消/唤醒。
- 收尾前HEAD4f6cb956cd14e85c12e9176103fda537a52a9617；业务从795dc19以来无已提交改动，中间提交仅主控三份文档。功能提交以本轮Git收尾版本为准，不为自引用hash另造业务变更。任务包与临时交付/源码快照索引保留，变更文件以Git本轮明确列表为准。
- 按项目里程碑门禁暂停新开发，等待用户页面验收。C2-C约定消费者/指南与真实主动链路另派，依各终端实际客户端预算显式wait（DeepSeek50/Codex现用300），配置active不等于权限/会话生效/自动唤醒，effective仍null/not_bound；C2-A2版本耗尽与C2-D真正取消仅登记。本轮不为等待开自动轮询/浏览器或启停服务。

## 2026-10-06 #162定向修正交付，派#163给DeepSeek定向复核

- 用户通知“162 ok”。#162/msg2664 runner succeeded/workflow submitted/未收取，但结果“说明+JSON”混排，MCP unknown自由文本；未从预览或succeeded推业务complete。按稳定结果引用4000+1047完整补读5047字符，sha a6c5de382289e0bded52bdafa271f842d888afe208ff722f619b976b39e10645，提取JSON与本地development.json逐字段一致；本地summary --expect-task-id162合法complete（6完成/0未完成/0阻塞、验证10/限制4），原结果/报告保持不改。合法自报仍非独立验收，#160/#162未收取。
- F-1自报修正以reloadNeeded状态位实现409后需重读：失败保持/重试可见，只GET恢复、需重读时按钮与函数入口暂禁保存，读成功clear/更新安全版本、用户明确保存；保持初读失败只读重试，422等非重读错误与上下文边界。F-2已在design-qa入库节记录首次:has/无本地兜底、旧浏览器失样式/原生radio不受影响、实机未测；不增CSS兜底。新手册恢复草稿单独保存，原#160草稿不追改。
- 实测本次修前→修后精确增量：workspace.js +18/-5，105023B/sha f7cfc0fb652b64972c7a6def8fad1db45a937cba82af213f90d6b7c524647f61；新Node测试+108/-2，34786B/sha 9a2125ac28df5c7174da808be31b83b078dd4e36697db5ae1eda35002104869c；design-qa +3/-2，12126B/sha 5f5caad98fab9d9d84a8079354a59393f61119a94907b1a1d640bee169bae419。另index.html四处资源版本20261006-controller-mode-c2b-f1及四Python契约仅版本串/一NotIn同步；app.js/css与#161原10文件快照完全未变，8变更/2未变与报告吻合。现10文件sha/bytes快照.tmp/controller-mode-c2-b-fix-review-dispatch/source_manifest.json。
- 开发者自报JS/测试语法通过、新增23/23和九文件153/153（默认逐文件隔离与--test-isolation=none两模式均过）；原7项恢复探针现7/7、新12项恢复探针12/12、接线15/15，资源版本变更后Python四契约12/12。原probe第3项恒真记录detail由saveBtn.disabled=false→true，为已授权需重读暂禁保存，不宣称语义完全相同、不改旧失败证据；新probe实断言GET-only/禁保存/新版明确保存正确。
- 本轮实际HEAD770e08cb8b7fda2b5c3e390e9d0a6ee34b38cfec；#162开发基线97089b9与当前仅三份主控记录docs差异，业务未提交。主控只处理交付索引/必要格式补读/文件增量与快照，不重复完整审代码或测试。
- 派前重读最新development_requirements，仍Kimi开发/DeepSeek交叉复核、Codex裁决/收尾。最小独立顶层参数派#163“调度模式冲突恢复修正定向复核”给agent:deepseek，queued/assigned，Hall group:task-8ce666fbc31347d28b0dd5f064b4b4e6。包副本.tmp/controller-mode-c2-b-fix-review-dispatch/task.md，复核交付.tmp/controller-mode-c2-b-fix-review/。限定F-1/F-2实际修前修后增量/直接生命周期与语义回归、版本同步、手册恢复草稿，独立复跑原7/新12/新增23/九文件153及版本契约12；无具体疑点不重做#161全片审查/98后端/C2-A1。
- #163须独立看实际代码、开工/结束核对业务hash，禁止改业务/原证据/正式文档；自身真实任务号校验，完整同一裸JSON结果，不再混说明。Kimi暂停，复核期间无并行改业务码；合看原#161主体独立审与本次定向结论后才能验收。浏览器视觉/键盘/:has外观与真实HTTP竞态、端到端仍未测，留用户页面验收，未新增主控浏览器操作。
- 本轮仅正式PROGRESS/HISTORY/路线图收件派发记录，UTF-8写入并差异检查后中文提交常规推送；10业务/测试/QA文件保持未审收尾不暂存。默认派后结束、用户通知#163完成后读取/裁决，通过再收取#160/#162/#163并同步模块/手册、业务Git与人工页面验收。

## 2026-10-06 #161复核发现两项缺口，收取复核并派#162定向修正

- 用户通知“161 ok”。talk_get_delivery #161/msg2663为合法完整talk-delivery-1、自身任务号匹配、业务partial、11完成/3未完成/0阻塞、验证10/限制7，无省略；runner succeeded/workflow submitted不推业务通过。主控采纳明确验收缺口，未因用户完成通知或主体测试通过将C2-B验收。
- DeepSeek实际阅读全部10文件/diff/新增552行测试及整体接线/生命周期/必要后端只读合同；A/B/D agree，C/E主体agree。独立node语法通过、新增20/九文件150、Python四份12全部复现，15/15集成探针通过；409恢复探针6/7，一项失败：409自动GET失败后error提示点重试、loaded=true导致retry hidden，而旧版本保存仍可点。失败证据和源探针保留，不追改。
- F-1为恢复入口不可用与文案不一致，涉及明文验收C，返Kimi增加最小实际GET重试入口及行为断言，恢复后用安全最新版本明确手动保存，不自动PATCH/用保存代替重读；允许需重读状态暂禁旧版本保存但不扩其他流程。F-2为design-qa未记录首次:has/无本地兜底/旧浏览器样式降级，补一句事实和未测限制，无需新CSS兜底。手册恢复分支新草稿另存，原#160/#161报告/探针不追改。
- #161复核成果已收取，返回workflow completed、msg2663，result_collected_at=2026-10-06T02:58:18.859405（服务端原时间未补时区）；这仅收取完成的独立审查工作，业务partial/F-1/F-2仍保留，#160未收取。正式业务尚未提交。
- 本轮开工HEAD97089b99358d58ea87e76fecebfc15ba208f9905；主控复验source_manifest 10/10 sha/bytes一致。原业务+514/-11及新增552行仍为修前基线；3个拟改文件原文本精确保存.tmp/controller-mode-c2-b-fix-dispatch/pre_fix/。复核者观察主控仅三份docs提交，不触业务事实保持。
- 重读最新development_requirements后按Kimi开发/DeepSeek交叉复核，最小独立顶层参数派#162“调度模式冲突恢复入口与降级记录修正”给agent:kimi，queued/assigned，Hall group:task-1d731e1378bc44688506509e7702e669；任务包副本.tmp/controller-mode-c2-b-fix-dispatch/task.md，交付.tmp/controller-mode-c2-b-fix/。限定workspace.js/新增Node测试/design-qa两项修正；确需资源版本允许四处+四Python断言一致同步，不扩其它业务。完成暂停后另派DeepSeek定向复核。
- 修正验证要求原7项恢复探针（原脚本不改）、新增控件可达/GET-only/安全最新版本/跨上下文及Node九文件必要回归；原探针若因禁旧保存出现预期语义差异，保留输出并以新探针验证正确语义，不篡改旧失败证据。仅资源版本变化才补Python页面契约，不无故重跑98后端/全库/C2-A1。
- 限制保留：无真实浏览器视觉/键盘/:has外观或HTTP并发；复核Node默认spawn EPERM以--test-isolation=none完成（隔离语义不同、未冒充默认通过）；原控件依赖Tailwind CDN与间距56px为已披露实践/视觉待验项，不扩修。有效模式仍null/not_bound，active意向不自动唤醒。
- 本轮仅正式进度/路线图按UTF-8维护、差异检查后中文提交常规推送，未提交业务源码；默认派后结束，由用户通知#162完成再读交付/派定向复核，通过后完成#160与修正任务收取/手册模块/业务Git及用户页面验收。

## 2026-10-06 收到#160交付，派#161给DeepSeek独立复核

- 用户通知“160已完成”。talk_get_delivery #160/msg2662为合法完整talk-delivery-1，自身task_id160匹配、自报complete、9完成/0未完成/0阻塞、验证6/限制3、10变更文件，无摘要省略；runner succeeded/workflow submitted/未收取。格式和自报通过不代表独立业务验收，#160保持未收取待复核。
- 交付实现模式面板/意向和执行分行/human可保存-agent只读/专用CAS/409重读/旧服务降级/项目账号序号与saveToken/单分隔线/资源四处一致。开发者证据Node新增20+九文件合计150、Python四份页面契约12、后端定向98通过，JS语法检查通过；浏览器视觉/键盘、真实HTTP竞态未测。主控只读取必要交付索引/实现说明与实际差异，不重复完整审代码或测试。
- 实际HEAD48939d2000feef5a9506855be977f2f228203105；与开发业务基线795dc19之间仅三份主控派发文档，业务源码无提交差异。implementation.md“HEAD未变/主控未补记”旧说明以Git事实为准，原件不改。当前9已跟踪业务/测试/QA文件差异+514/-11，新tests/workspace_controller_mode_ui.test.cjs未跟踪552行/28608字节；所有10文件bytes/SHA256快照保存在.tmp/controller-mode-c2-b-review-dispatch/source_manifest.json。
- 派前重读最新development_requirements，仍Kimi前端、DeepSeek独立交叉复核，Codex裁决/收尾。最小独立顶层参数派#161“调度模式界面与角色分隔线独立复核”给agent:deepseek，返回queued/assigned，Hall group:task-425a2b43e60345628fd87d36d05ef232；未附加子任务字段或手写编号。
- 复核包含原#160任务/范围不变项、完整验收合同、实际基线和精确差异/源码快照、开发者命令与证据/限制、A–E代码关注点（整体接线、项目账号/迟到/409/saveToken、独立CAS、旧服务权限/安全版本、视觉及语义边界）、手册草稿检查；要求独立实际代码检查及必要Node/Python回归，不只信自报/字符串测试，不为无疑点重跑98后端/全库/C2-A1。发现问题交Kimi修正，DeepSeek不得自行改业务码。
- 复核仅可写.tmp/controller-mode-c2-b-review/报告/合法自身#161交付/隔离证据，完整裸JSON结果并validate；任务包副本.tmp/controller-mode-c2-b-review-dispatch/task.md。开发已暂停，复核期间不并行改业务码；不启停服务/改真实模式指定、不浏览器操作、不生产长等待。
- 本轮仅正式进度/路线图收件及派发记录，以UTF-8写入、差异检查后中文提交常规推送，Kimi的10业务/测试/QA文件保持待审未暂存。默认派发后结束，用户通知#161完成再读取/裁决，通过后收取#160/#161、更新模块/手册和业务Git，用户页面验收后继续下一阶段。

## 2026-10-06 用户确认C2-B，派#160给Kimi开发

- 用户回复“可以”，确认项目设置调度模式界面及角色“参与任务”双横线保留一条。按当前development_requirements，Kimi开发、完成暂停后DeepSeek独立检查实际代码，Codex裁决/正式文档/Git；本次未提前派复核、未并行改业务码。
- 派前HEAD 795dc19ff9c315d03ff72f3741f0bdefe936461d，工作区干净；按项目分别查询queued/running均为空。最新角色实例只是上报事实，未核验实时存活。当前Key human:bobo、模式passive；配置不作为主动等待授权，本轮不持续等待。
- 已读取本片Web UI模块、C2设计§2/§6/§7和TASK_WORKFLOW派发/交付约定。最小顶层参数project/target/title/content（不手写编号、不附加子任务字段）派#160“项目设置调度模式界面与角色分隔线清理”，agent:kimi，返回queued/assigned，Hall group:task-d20c3d46e1334442a279f07ad18447f5。
- 任务范围前端面板、单分隔线、相关Node/Python契约测试、资源版本一致；文案严格区分已保存设置和实际执行，human可保存/agent只读，旧服务/404/非法版本降级，409只重读，400/422等保留选择，账号/项目/请求序号/saveToken保护及独立CAS。不改后端/API/数据库/运行配置/真实模式或指定，不扩C2-A2/C/D，不声称自动唤醒/主动生效。
- 允许根design-qa.md仅本片证据和.tmp/controller-mode-c2-b/完整交付/实现说明/手册草稿；正式文档由Codex收尾。开发交付须实际自身#160、合法talk-delivery-1、完整裸JSON结果正文，本地validate；要求真实命令/结果/限制与审查索引，开发完成暂停，不自行commit/push。任务包副本.tmp/controller-mode-c2-b-dispatch/task.md。
- 本轮仅主控正式进度/路线图派发记录，以UTF-8维护并差异检查后中文提交常规推送；不浏览器验证、不启停服务、不读历史Hall或重复审查。默认派发后结束，用户通知#160完成再取件，之后派DeepSeek独立复核，页面由用户验收。

## 2026-10-06 重开窗口恢复，Codex连接C2-A1加载检查通过

- 用户要求“继续项目”；恢复项目背景、当前进度与AGENTS决策身份，读取终端预算/重连验收要求。开工HEAD `11977a87ec4a10cc3e4af0cab52ccafc237d256a`，工作区干净，与origin同分支跟踪引用一致，远程为授权的bobo506/TALK。
- 当前TALK工具目录共九个，wait已暴露controlled_wait；真实项目list_agents返回caller_identity三键，Key身份human:bobo/kind human/note null。模式passive/version0，主控指定agent:codex/version13/assigned，effective null/not_bound。项目最新开发要求仍Kimi文字/设计/交互/前端、DeepSeek后端/其他，双方交叉复核，Codex范围与收尾；实例上报不作为已核验存活证据。
- 用本人可读已完成#159，显式timeout_seconds=5、controlled_wait=false，返回matched、timed_out=false、workflow completed、msg2661；程序elapsed_seconds=0.016，poll_rounds=1/http_requests=1。随后相同历史任务和5秒预算、controlled_wait=true，预期按G4明确拒绝human凭据。再调用list_agents成功，确认正常返回/门禁拒绝后当前连接可查询。没有新建任务、重复收取或修改凭据/模式/指定。
- 当前Codex连接加载卡点解除；这些短预算检查不等于真实主动等待适配通过。客户端实际长预算未重核，300秒调用、正常等待到期、网络/API错误、客户端超时/取消及排队恢复、DeepSeek桌面目录刷新均未在本轮验证；不外推660秒能力，不测试生产长等待，不启停/重载服务、不操作浏览器。
- 本轮仅更新PROGRESS/HISTORY真实恢复证据，无业务代码修改和新任务派发。下一切片C2-B仍由Kimi实现/DeepSeek独立复核，任务包带角色“参与任务”上方双横线仅保留一条；C2-C消费者/真实主动链路等仍后续，页面效果由用户验收。
- 两份进度按UTF-8写入，执行文档差异检查后中文提交并向授权分支常规推送；不重做代码审查或无关测试。

## 2026-10-06 按用户要求保存进度，准备重开窗口

- 用户要求“先汇总下进度，我需要重开窗口”；本次仅维护进度快照与历史，不开启切片、不派任务或主动等待。
- C2-A1工具实现经#157原片审查及#159修正定向复核确认通过，F-1关闭；#152–#159相关设计/开发/复核任务均已收取，无在途开发任务。独立验证为29+29+31项及错误探针，完整证据与限制保留在前一条记录，不重复执行完整审查。
- 稳定功能提交 `9ee0ac0`、此前进度补记 `4a67871` 均已常规推送。本次交接开工HEAD `4a678715e6ce8f5110980d039e3c86479bf1880a`，工作区干净，与 `origin/codex/terminal-return-codex` 比较为0/0；分支未配置upstream，恢复时显式指定正常推送目标，不修改跟踪设置。快照澄清新增测试已纳入功能提交，未跟踪口径仅指收尾前历史状态。
- 当前连接此前只读核验仍无caller_identity/controlled_wait，加载验收待完成；重开聊天窗口不保证MCP进程重建。新窗口先核对字段/目录，按TERMINAL_MCP重连验收段处理。通用终端预算要求已入AGENTS与指南：DeepSeek桌面客户端65秒下显式wait50秒，Codex保留用户现用wait300秒，其它终端按实际上限留返回余量；不表示已改真实运行配置或实现自动续等。
- 下一切片仍C2-B前端主被动界面，Kimi实现/DeepSeek交叉复核，并带角色“参与任务”上方双横线保留一条；加载与人工验收门禁后再派发，派前重读实际development_requirements。C2-C真实消费者/主动链路及取消等边界未实现。新窗口恢复指令：`继续项目`。
- 本次变更文件仅docs/PROGRESS.md、docs/PROGRESS_HISTORY.md，按UTF-8写入，文档差异检查后中文提交并常规推送；不启停服务、不改凭据/模式/指定、不操作页面。

## 2026-10-06 #159复核通过，C2-A1确认收取并规范全部终端超时适配

- 用户新增明确要求：终端超时报错必须写进适配要求，今后每个终端都考虑；同时通知#159完成。讨论聚焦单次wait返回在客户端时限内，DeepSeek桌面工具上限65秒时选W50，Codex保持用户现用W300；未要求更改客户端配置或取消宿主进度更新规则。主动模式到期后下一轮需Agent再次调用且有资格/剩余总预算，工具不自动续等，任务执行不会因读取到期而重启/取消。
- #159/msg2661合法完整talk-delivery-1、task_id匹配、自报complete无省略，completed8/unfinished0/blocked0、verification8/limitations5；Kimi实际定向复核结论agree/F-1已修好无新问题。独立核对合同/修正前后代码hash、+49/-28/+189增量、共用poll错误兼容与一次统计/计数、JSONL附加字段直接消费者兼容；仓库无固定键集JSONL解析入口，新增failure_stage不进返回。主控核对3业务文件仍与已审hash一致，不重复完整审代码或测试。
- 独立复跑controlled_wait29 OK/14.202s、task_tools/terminal29 OK/41.440s、controller_mode31 OK/13.223s，原探针False/0→True/1、api_error，新探针HTTP500/超时两例恰好一条api_error记录且失败GET最后/无非GET/实际30秒重读节点，exit0。与#157对原片A–E/G/H检查合看后，Codex确认C2-A1工具实现通过，F-1关闭；本次定向审不冒充重审全片/全库，ACP旧沙箱WinError5整套不计为本轮通过。
- 证据：.tmp/controller-mode-c2-a1-fix-review/review.md 7172字节/SHA256 cd5f971479a76cfcbbadf87e491be7a0fa3de1d92b554361369e6cd1d1c35d36，development.json4651/hashe8b05faa68f409ea3886822df9f4143aba1919ab518db063229dbb594190639f。已审源码hash：talk_task_tools101189/a98ac7a2878938c47337bc00cfa4364d275cfe185021a9efea1f6ac23e5c3a85；terminal8642/0a197814da98673956982788343b78db61e04e9946e527b361aeb5427d08f0b2；测试67002/5745c5f31399d338caa4542e8684432ce9435c78dfe55939152fe5fe14edac7e。实际累计numstat工具+752/-59、terminal+18，新测试新增另计，开发者+812笔误与#157未收取旧状态不追改原件。
- 已依次收取#159/msg2661（2026-10-06T00:52:47.520546）、#158/msg2660（00:52:50.346496）、#156/msg2658（00:52:53.446218），workflow全部completed，时间为服务端记录；#157此前已completed，原partial/MCPunknown保持，未重复收取。设计#152–#155均此前收取，开发/复核链#156–#159关闭。
- 用户要求写入AGENTS必读指引及跨终端预算决策、TERMINAL_MCP通用适配必查：核验实际客户端上限T与来源/单位/加载方式、显式W与余量、执行者预算分开、正常到期/命中/API错误/客户端超时/取消分类、同连接后续查询/排队边界、总预算有限续等与真实宿主证据。DeepSeek65/W50、Codex现用W300，Kimi660000仅模板不外推实际。原跨终端统一600目标按新用户决策收紧，库default/max600兼容合同不改，至少参考5秒余量允许更大，DS当前留15秒。
- 正式合同状态更新为C2-A1已实现/其余待开发，原设计基线/临时报告保持；模块/简报/终端指南与桌面指南同步工具形状、重连验收和无新Web操作步骤。user manual日常页面不变。规范是本次落盘的要求，不表示已新增按宿主自动读取预算/自动限长或C2-C消费者，更不表示已调整真实desktop/codex配置。
- 当前Codex MCP只读读回has_caller_identity=false，wait工具目录描述未出现controlled_wait；mode仍passive、effective null/not_bound，assignment agent:codex/version13。确认当前连接尚未暴露新合同，未通过旧连接假测新功能。当前工具集无可调用重载入口，本轮未启停服务/进程，真实桌面目录本轮未刷新核验；客户端需重连并重建/加载MCP进程与目录，按指南只读核对字段及本人可读历史任务返回，不能把源码通过写成运行中已加载。
- 残余范围：取消无检测源/同连接排队、sockettimeout非任意慢响应端到端硬截止、阶段≤5次/≤10分钟仅提示词约定、effective_mode仍null/not_bound；真实主动宿主/660秒/模型/长等待/浏览器未测，原DLL0xC0000142根因未明。C2-B界面（带参与任务双横线保留一条）、C2-C实际约定消费者/预算/指南与主动验收后续，C2-A2低风险可选/C2-D真正取消不扩片。不改数据库/权限/凭据/mode/指定/执行CLI/外部profile，不新建测试任务或自动等待。
- 收尾前HEAD47e8fff3beb1da43a150032922a52c3112d163a3，已由9ee0ac0将已审3业务文件、6份正式规范/合同/指南及3份进度文档统一提交常规推送，12文件2392+/111-，新增测试1503行，源码hash/文档UTF-8与围栏/新增指南链接目标/暂存范围/diff --check均通过。进度快照缩短，完整链与新决策保存在历史；本轮结束于代码收尾和MCP加载验收说明，不开启下一实现切片，下一步C2-B由Kimi/DeepSeek交叉复核且先按人工验收/用量门禁恢复。

## 2026-10-05 #158 F-1修正交付收到，派#159定向复核

- 用户通知“158完成了”。talk_get_delivery #158/msg2660合法完整talk-delivery-1，task_id匹配、自报complete、无省略；completed10/unfinished0/blocked0、changed_files2/verification6/limitations7，runner succeeded/workflow submitted。开发者已暂停，格式有效不等于业务验收，#156/#158均未收取；#157复核工作已在前轮收取，原partial与MCPunknown自由文本不追改。
- 开工e01d78ae75c1b9c078c140a0c71cd1b2c1553ce3→当前6d0a5f32f5e1143a5abc48a2b628af24e639d146仅主控3份进度文档变化，分支codex/terminal-return-codex。主控核对修正前snapshot-before/talk_task_tools.py 99644字节/hashbb59cf9b1d7c690b50cf65faab2138f1b3394d33f48e6382bcfa9d5c1ad85715、test_talk_controlled_wait.py 57408/hashf8ec6040cde9b3371893df4ac92686e5ba6b2b755e3850e1796ffbf54ed6fe45，与#156/#157冻结值一致。
- 修正后对象主控实测：bridges/talk_task_tools.py 101189字节/SHA256 a98ac7a2878938c47337bc00cfa4364d275cfe185021a9efea1f6ac23e5c3a85；tests/test_talk_controlled_wait.py 67002/hash5745c5f31399d338caa4542e8684432ce9435c78dfe55939152fe5fe14edac7e；terminal8642/hash0a197814da98673956982788343b78db61e04e9946e527b361aeb5427d08f0b2保持不变。相对修正前git diff --no-index --numstat工具+49/-28、测试+189/0（返回1表示有差异）；累计git diff --numstat实际工具+752/-59、terminal+18/0，新测试未跟踪。开发者累计+812/-59是笔误，本次修正增量正确，正式记录用实测。交付progress_draft的#157未收取亦为旧状态笔误，以前轮completed为准，不因此重复收取或改原件。
- 实现自报：新增fail_as_api_error(exc, stage)统一运行期错误出口，poll/recheck except均接入；重读失败显式TalkToolError含真实elapsed/rounds，恰好一条api_error JSONL，失败GET只计一次http_requests、controlled_rechecks仍仅成功重读计入。JSONL新failure_stage=poll/recheck仅内部记录，不进返回/query_stats四键；退出次序/分类/9工具/其他门禁与旧false路径保持。实际代码与新增直接风险交Kimi定向审，Codex不重复完整审查或测试。
- 新增2测试方法：假时钟矩阵HTTP500/超时/已有一次成功重读后失败，以及真实_api_request+假urlopen的HTTP500/read TimeoutError计数链。自报controlled_wait29 OK/14.334s、task_tools/terminal29 OK/43.243s、controller_mode31 OK/13.617s；新probe_recheck_fix.py HTTP500/超时两例record1/api_error/stage recheck、HTTP13/项目GET2、失败为最后请求/无非GET；原#157探针False/0→True/1，api_error。原probe脚本3558/hash05aa2d982996536cc0628aa6945303ebca39862c240f9b8d81beecc9867c5cb3、旧txt179/hash0cc673f3acb2bef36d3986ece6e54fcfcee9f7764dbfa2f0613e0bd0e013ccad，主控核对仍保持。
- 本地目录.tmp/controller-mode-c2-a1-fix/，notes.md 9598字节/hashb7a4c8c387857721585e3a073ac1297e61cb086bc2b438d7f2c4d3bed6c6fe3f、development.json 6776/hash608bdaeb81cb9d41b7d2db887c9da9478964a5c41f9dba929ddd03fa575d6a6a。新probe_recheck_fix.txt和probe_original_review_after_fix.txt为开发者记录实际控制台输出的逐字转录，stdout/stderr重定向受沙箱拒绝，不能称自动原始日志。ACP整套现成WinError5未重跑、不算通过，未重跑全库。
- 派前读取最新development_requirements仍按双方交叉复核、Kimi文字设计交互前端/DeepSeek后端其他；mode passive/version0、effective null/not_bound仅配置事实。最小独立顶层派#159“受控等待重读错误修正定向复核”给agent:kimi，queued/assigned；不手写标题编号，无子任务字段。开发者暂停，复核期间不并行改业务码。
- #159包包含原需求/正式合同hash、F-1原定位与修正目标、修正前快照/后源码完整hash及本次/累计增量区别、测试/转录日志/沙箱限制、历史任务状态纠正；仅审F-1实际增量与共用poll错误出口兼容、准确一次统计/计数、stage内部字段及直接统计读取兼容、正常次序/无新增泄密等具体新增风险，必要新测试/旧探针和controlled_wait关键回归；不重做#157 A–H完整审查/设计/216项全库。复核执行与业务通过分开，通过后主控合看原片独立审查与定向结论收尾。
- #159只写.tmp/controller-mode-c2-a1-fix-review/完整review/development及必要证据，显式UTF-8/实际任务号校验；TALK结果正文只能完整裸JSON，避免#157说明+JSON混排。原件/快照/业务源码/正式文档不改，未授权启停/重载/真实模型/长等/浏览器/凭据/mode/指定/权限/派发或收取他人任务/commit/push。S-1–S-3、pi旧wait、C2-A2/B/C/D不扩片，双横线仅下一C2-B；没有新用户入口，不称开关可用，取消无源/同步排队/总预算仅约定/硬deadline限制保留。
- 本轮仅PROGRESS/HISTORY/路线图收件/派发记录，明确暂存3份文档并diff --check后中文提交常规推送，3份业务差异保持未提交待复核。派后结束，由用户通知#159完成，不主动轮询；通过再处理#156/#158收取、模块/说明及业务Git收尾，MCP重载和真实主动链路未验收如实分开。

## 2026-10-05 #157复核发现F-1，收取复核并派#158定向修正

- 用户通知“157完成了”。talk_get_delivery #157/msg2659为unknown自由文本，不从succeeded推断业务通过；按稳定结果引用完整补读3028字符（SHA256 f7e56ebacf5ba20af397aa9db4f6fed75510dc3e7721abebd04e2ac55638f6dc），正文是“说明+JSON”混排，未因包含JSON而追改MCP结论。旧入口summary .tmp/controller-mode-c2-a1-review/development.json --expect-task-id157有效talk-delivery-1、partial，无截断；6完成/1未完成/0阻塞，6验证/4限制。未完成指F-1需开发者修正，独立复核执行本身已完成。
- Kimi独立核对合同hash/实际源码与冻结三文件hash、约790行helper变动及直接链路，认为可维护性可接受，测试为行为验证；A参数/旧语义、B G1–G7门禁、C快照/30秒/matched、D deadline/R5、E R1归一、G身份三键、H说明/check均通过。F项正常计数/返回通过，但重读GET失败错误包装与落盘不通过。复核启动基线2ad9fbf，之后主控e01d78a仅进度文档；主控本次再次核对三业务文件仍与#156冻结hash一致。
- F-1中等：bridges/talk_task_tools.py原1580 recheck_project()位于只包poll_round_tasks的try/except之外；进入门禁后运行至30秒重读GET遇HTTP4xx/5xx或网络超时，TalkToolError直接抛出但缺已等待时长/轮询次数，且没有任何wait-stats JSONL。不是静默降级、不是普通timeout，也不是权限问题，但违反明确api_error验收/观测性合同。主控采纳独立证据，裁决需修正后定向复核，#156不能直接通过。
- 证据冻结：review.md 16477字节/SHA256 afafef2e45233830e5e1b253489cf70261e2f2b34d761780d55eaff700a16ca8；development.json 4300/hashcc502792e0a8390ab147ca84348b82b5bca06707ebf76f1a9250607ba1edb0bb；probe_recheck_error.py 3558/hash05aa2d982996536cc0628aa6945303ebca39862c240f9b8d81beecc9867c5cb3；txt 179/hash0cc673f3acb2bef36d3986ece6e54fcfcee9f7764dbfa2f0613e0bd0e013ccad。原件目录.tmp/controller-mode-c2-a1-review/保持不改。主控读取探针txt确认HTTP500原文、has_elapsed_rounds_wrapper=False、stats_records=0，sleep0.5/1/2/4/5×5已到重读节点；不重复执行复核代码或测试。
- 独立复跑：controlled_wait 27 OK/13.441s；task_tools+terminal29 OK/40.003s；controller_mode31 OK/12.344s，三源码ast.parse通过。原开发者空日志不能作为可读原始证据，复核以自己实际退出状态/计数为准。ACP现成WinError5未重跑、不算通过。未重载MCP/桌面/真实主动链路/660秒/模型/长等待/浏览器，取消无检测源、同连接排队、总预算仅约定等已知边界保持。S-1 HTTPError detail略少、S-2 check两身份GET、S-3 list_agents无query_stats均非阻塞，不扩整改。
- Codex接受独立复核执行并收取#157：workflow completed、result_message_id2659、result_collected_at2026-10-05T14:24:03.464981（服务端记录）。该收取不代表#156业务验收；#156仍submitted未收取，原#157 partial/MCPunknown记录与原件保留。
- 派前读取最新development_requirements仍为DeepSeek后端/其他、Kimi文字设计交互前端、双方交叉复核；controller_mode passive/version0，effective null/not_bound；assignment agent:codex/version13/assigned仅配置事实，不据此改变权限。按最小独立顶层参数派#158“受控等待重读错误统计定向修正”给agent:deepseek，返回queued/assigned，title不手写编号，当前HEAD e01d78ae75c1b9c078c140a0c71cd1b2c1553ce3。
- #158包含原需求/合同、F-1定位/触发/预期/实际/探针hash、修正前3源码hash及实际基线、既有独立测试与沙箱限制。只改talk_task_tools与controlled_wait测试及.tmp/controller-mode-c2-a1-fix/，先保存修正前快照便于区分本次增量与#156累计差异，terminal hash保持；运行期重读错误须显式api_error真实elapsed/rounds、恰好一次JSONL/失败GET计数，至少HTTP错误/超时注入与定向回归，原探针保持。其它G门禁/旧路径/正常退出/deadline/身份/9工具/只读等不退化。
- 本次不改正式合同/模块/手册/业务数据库/web/CSS/launchers/桌面配置/凭据/指定/mode/权限，不启停真实服务/重载/模型/长等/浏览器，不修S项或pi旧wait/C2-A2/B/C/D；仅工具内部错误处理，无新UI/用户入口、不称开关可用。交付正文只能完整裸JSON，不能介绍+JSON混排；显式UTF-8、实际task_id/expect-task-id、本次前后hash/增量/测试/限制/草稿齐全，完成暂停后由Kimi定向审，执行者不commit/push。
- 本轮只同步PROGRESS/HISTORY/路线图，明确暂存3份文档，git diff --check后中文提交常规推送；业务3文件继续工作区待修正复核。派后结束，由用户通知#158完成，不主动轮询。角色“参与任务”上方双横线保留一条仍并入下一C2-B前端片。

## 2026-10-05 #156实现交付收到，派#157独立复核

- 用户通知“156已完成”。talk_get_delivery #156/msg2658为合法完整talk-delivery-1、task_id匹配、自报complete且无省略，completed12/unfinished0/blocked0、verification7/limitations11；runner succeeded/workflow submitted。格式与自报有效不代表业务验收，#156未收取，开发者完成后已暂停。
- 实际开工基线599f59cda844f7b71095a708931900f5bf898eea，主控HEAD2ad9fbfbff919e9b0315cbbf38b985bea114a850仅有派发进度文档差异。主控独立核对工作区清单与hash：bridges/talk_task_tools.py +731/-59，99644字节/SHA256 bb59cf9b1d7c690b50cf65faab2138f1b3394d33f48e6382bcfa9d5c1ad85715；bridges/talk_terminal_mcp.py +18，8642字节/hash0a197814da98673956982788343b78db61e04e9946e527b361aeb5427d08f0b2；新增tests/test_talk_controlled_wait.py 57408字节/hashf8ec6040cde9b3371893df4ac92686e5ba6b2b755e3850e1796ffbf54ed6fe45。三文件未提交；完整实际代码检查交Kimi，Codex不重复审查或重跑开发者套件。
- 开发者自报：controlled_wait严格bool/default false、旧等待无额外HTTP/字段；true G1–G7核验项目/显式有限正timeout/Key服务端agent身份/支持完整mode与assignment/assigned/本人指定且active；30秒重读与mode/controller变化退出；deadline覆盖进入HTTP/轮询/重读/sleep，remaining<=0不发请求，HTTP min(10,remaining)；R5最近成功任务集合/空集合；R1连接/getresponse/read裸超时与网络OSError归一；caller_identity项目固定三键/失败不阻断/非项目null无额外请求；新HTTP失败尝试同样计数，schema/dispatch/描述/--check九工具同步。上述均待独立核对。
- 自报测试：new controlled_wait 27 OK/13.7s（19假HTTP时钟+8真实隔离服务）；task_tools/terminal/controller_mode 60 OK/53.7s；assignment/development_requirements 65 OK/28.2s；delivery/dsh_entry/kimi_entry 91 OK/13.5s。既有回归216、新27，共243，不重复计数。measure_payload项目清单1407→1486字符、增79且旧<1500断言未放宽。test_dsh_acp_drive整套未取得通过：报告30项中18项Popen/CreatePipe WinError5、失败点scripts/dsh_acp_drive.py:182；不能当成通过，由复核判断影响。
- 本地入口.tmp/controller-mode-c2-a1/development.json、notes.md、measure_payload.py；主控核对regress-tasktools.txt/probe.txt均0字节。开发者称stdout/stderr重定向受沙箱限制，原始日志未落盘，现有证据为实际退出状态与摘要；复核包明确不能把空文件当原始日志，必要复跑须独立记结果/限制。
- 未验证/边界：未重载MCP、未重连桌面、无真实主动宿主或660秒能力验收；sockettimeout不提供任意慢响应端到端硬截止；同步stdio未消费客户端cancel、同连接请求排队；阶段≤5次/≤10分钟仅提示词约定；effective_mode仍null/not_bound，无互斥/自动唤醒/新权限。pi独立wait旧30秒无新门禁为非活动兼容路径且超范围，--check两个身份GET未去重已登记，C2-A2/C2-B/C2-C/C2-D尚未开发。仅工具合同，不能称开关已可用。
- 派前再次读取最新development_requirements，仍按DeepSeek后端/Kimi文字设计前端/双方交叉复核。按最小顶层参数派#157“主被动受控等待与身份核验独立复核”给agent:kimi，返回queued/assigned；标题未手写编号。包含原需求、正式合同hash、实际基线/三文件hash、差异、不变项、逐项验收、开发测试及日志/沙箱限制。
- #157须独立审实际源码及必要直接链路，重点旧false请求/返回/异常兼容，G1–G7拒绝不降级，30秒/两版本变化、matched优先边界、进入预算未核验与已核验后正常空timeout、R1响应异常归一、R5最近成功集合、计数/身份三键/保密与说明一致，必要定向测试；不做全库/真实模型/长等待/浏览器。只写.tmp/controller-mode-c2-a1-review/完整裸JSON/报告和证据，不改源码/原件/正式文档、不启停服务或改凭据/模式/指定、不commit/push。发现问题交回DeepSeek修正再审，复核工作完成与业务通过分开。
- 本轮只同步PROGRESS/HISTORY/路线图，明确暂存这3份文档，git diff --check后中文提交常规推送，业务3文件保持未提交。派后结束主控等待，由用户通知#157完成再取件；下一前端C2-B继续带角色“参与任务”双横线保留一条。

## 2026-10-05 C2-0收尾提交推送，派#156实现C2-A1

- 正式实施合同与设计收尾由599f59cda844f7b71095a708931900f5bf898eea提交推送（5份文档334+/9-），C2-0形成可回溯版本后才开启实现片。CONTROLLER_MODE_DESIGN.md为48591字节/SHA256 2f9e4c1682ed840c53635d0dad15bcdb66191cb12ce4b2da106f979fe5388452，含#155 R1–R5回填；原方案/复核不改。
- 派前再次读取最新development_requirements，职责仍为DeepSeek后端/其他、Kimi文字/设计/前端、交叉复核；当前实例仅上报available，不外推心跳或主控生效。按最小独立顶层参数派#156“主被动调度受控等待与身份核验实现”给agent:deepseek，返回queued/assigned；title不手写编号，基线599f59c。
- 本片范围：talk_task_tools的严格bool controlled_wait默认false/旧通用兼容、G1–G7受控进入门禁、API Key服务端身份、独立模式/指定版本快照、30秒低频重读与变化退出、明确单次deadline/HTTP与sleep剩余预算、受控连接/响应超时归一、R5最近任务集合早退、新GET请求计数、项目caller_identity固定三键/非项目null/失败不阻断清单；必要terminal检查说明与相关测试。九任务工具数量保持。
- 开发包明确门禁预算核验未完成不得开始轮询或退回普通等待，已通过门禁但尚未轮询deadline耗尽才正常timeout空集合；网络请求已发后的异常是api_error而非正常timeout，socket timeout不冒充端到端硬截止。旧非受控默认/最大600、请求次数/返回/query_stats四键/错误分类保持，不放宽payload断言掩盖输出膨胀。
- 必要测试为模拟时钟/假HTTP的旧兼容、严格输入/各门禁、版本与字段变化、重读节奏、剩余deadline与最近/空集合、连接/getresponse/read裸超时与OSError、10秒默认/受控clamp、新GET失败尝试计数、caller_identity形状/非项目/失败降级、schema-dispatch链与目录数量/有界输出，以及现有MCP/wait/terminal相关回归。无需真实模型/长等待或全库重复，完成暂停后由Kimi独立审实际源码。
- 不扩片：server/API/数据库/web/CSS/静态版本/launcher/桌面patch/运行器/凭据/指定/实际mode均不改；C2-A2耗尽仅登记，真正取消C2-D/约定级总预算/真实主动C2-C/UI C2-B未实施。双横线仅后续前端片。MCP重载需后续收尾，本片不启停服务或真实工具探针。
- 交付约定.tmp/controller-mode-c2-a1/完整talk-delivery-1 development.json及必要局部日志，实际task_id156校验、裸JSON提交TALK，正式进度/Git由Codex维护；用户手册影响注明仅工具合同、不能写开关已可用。派后结束，不主动等待/轮询，由用户通知完成再收件。
- 主控本次只改PROGRESS/HISTORY/路线图派发记录，git diff --check后中文提交常规推送；执行代码差异不混进主控文档提交。设计旧#152–#155全部收取，当前唯一待交付#156。

## 2026-10-05 #155定向复核认可可开工，C2-0正式合同落盘并收取

- 用户通知“155 ok了”。#155/msg2657合法完整talk-delivery-1、自报complete仅复核工作，completed13/unfinished0/blocked0、verification9/limitations6，无省略。结论为修订足够作为C2-A1开工依据、无旧合同退化，但R1/R4中等与R2/R3/R5低项需回填，不是无条件通过。
- 独立复核确认七份方案/原件hash、业务源码零改动、P1 opt-in兼容门禁、P2 Key身份与human/Agent边界、P3取消未监听、P5低风险耗尽、P7计数披露。R1来自urllib响应阶段裸TimeoutError与项目except的静态核对，非真实网络实测；R4为matched不能代表仍有active资格、各动作前仅约定级重读，检查至动作仍有竞态。复核review.md 21365字节/hash876f66a780ae11a5d52881e75a98dddd5fc359c60524c8165afc6e7767596bcf；未重跑耗尽探针/真实服务模型等待。
- Codex裁决采用可开工并完成文本回填，正式合同docs/spec/CONTROLLER_MODE_DESIGN.md从#154已审report.md（hash20010d18…9ebed92）复制，原件及开发/复核包均保持只读。正式标题明确功能待实现/设计确认不等于active生效。
- R1定为C2-A1必做验收：至少受控路径连接/响应头/响应体超时或网络异常归一TalkToolError/api_error，不能裸异常逃出；其它网络错误不一概标超时，旧通用错误分类不退化；socket timeout不冒充端到端硬截止。R2 strict正数排除bool/非数/NaN/inf/0/负值，仅受控新语义。R3项目caller_identity成功/失败固定member_id/kind/note三键，非项目null且不额外身份GET，失败不阻断旧清单/不泄密。
- R4正式合同回填matched只为任务命中，每次派复核/收取/汇报前重新核对身份/kind、mode/assignment及两版本；这是提示词约定，读取至动作竞态仍存在，不引入所有权/ACK/租约。R5正常deadline早退沿用上一轮成功轮询集合，未轮询则tasks=[]/task_count0；请求已发后的网络错误不能吞成正常timeout。
- 已收取#155（msg2657，2026-10-05T12:36:37.635549）、#154（msg2656，12:36:48.489249）、#152（msg2654，12:36:56.729585），全部workflow completed，时间为服务端记录；#153此前已收取。收取不追改#152原partial/代码块unknown，也不表示功能已实现；设计链路#152→#153→#154→#155关闭。
- 正式方案链接同步PROJECT_BRIEF与路线图，第3阶段转C2-A1准备；C2-A2低概率耗尽为可选加固、C2-D真正取消后续，C2-B页面和C2-C真实主动链路仍需人工验收。双横线仅下一前端片处理，当前UI不改、effective_mode仍null。
- 本轮开工前usage-gate decision continue，session/weekly百分比null如实保留；先设计正式文档/进度格式校验、中文提交常规推送，再派一个DeepSeek后端/MCP实现片、Kimi独立复核，不由Codex代实现或重复完整审查。未读取密钥/改凭据/指定/权限、启停服务、操作浏览器或真实模型等待。

## 2026-10-05 收到#154方案修订，派#155给DeepSeek定向复核

- 用户通知“154 ok”。#154/msg2656为合法完整talk-delivery-1，task_id154匹配、自报complete仅修订工作完成，completed9/unfinished0/blocked0/verification7/limitations6，摘要无省略。runner succeeded/workflow submitted；未将自报完成当独立验收，#154与#152暂未收取。
- 修订自报P1–P7逐项覆盖：controlled_wait显式opt-in默认false，旧默认/最大600、clamp与返回保持；G1–G7进入门禁/运行变化退出明确；身份唯一members/me，human:bobo与agent:codex不匹配如实处理；取消无监听/无cancelled、C2-D另记；预算重读30秒/余量5秒、HTTP min(10,remaining)与sleep/deadline、五个return_reason确定；段总预算≤5次或≤10分钟仅提示词约定无代码强制；版本耗尽低风险可选非前置；C2-C实际提示词/指南落点与约定级边界补清；所有身份/项目GET纳入wait计数与工具披露。
- 冻结修订对象：.tmp/controller-mode-c2-plan-fix/report.md 44210字节/SHA256 20010d1880e58147d14e1a03d0f150ed81ef9a4f3b3982456f62101499ebed92；revisions.md 11965字节/SHA256 2365a505d523f17c9d4dfb2d175a895d365096ddf4d125db71dfcf45d38ed665；development.json 6775字节/SHA256 fb101a064a65fb82fdad47c56f44d0ceb310a70d998ca543b1e101d2c0842c14。原四件只读/哈希不变为开发者自报，定向复核会独立确认。
- #154自报实际基线9689062d45895b8a8a639e660c12153afa640154，业务源码零改动，仅.tmp三文件；主控当前Git工作区干净。7项自测证据包含原件hash、实际wait/dispatch/API身份/10秒HTTP/计数/9工具/预算来源/本地validate154；真实模型/等待/页面/服务not_run。主控只读交付与§5.3预算/退出，完整设计/源码定向核对仍交独立执行者。
- 派前重新读取development_requirements，仍为Codex决策、Kimi文字/设计/交互/前端、DeepSeek后端及其他、双方独立复核。按最小独立顶层参数派#155“主被动开关修订方案定向复核”给agent:deepseek，返回queued/assigned；不附父子任务字段、不手写标题编号，派后结束主控等待。
- #155包包含原需求/范围/不变项、三文件完整hash、实际基线与自测证据、P1–P7逐项验收及开工判定。只查修订与直接新增风险，不重复#153全部源码或耗尽探针；重点确认旧wait请求/返回不退化、caller_identity新增GET/失败降级、参数到dispatch的实施路径、实际API/摘要字段映射、deadline与HTTP预算保证边界、matched优先时后续取件/转审节点仍复查最新模式与指定、计数披露完整。
- DeepSeek只写.tmp/controller-mode-c2-plan-fix-review/复核及必要局部证据，原方案/修订/代码不改、不做真实服务/模型/长等/浏览器。要求完整裸talk-delivery-1、本次task_id155，复核工作完成与方案通过分开；完成暂停由Codex裁决。方案足够且未覆盖范围如实则通过，不因功能未开发否定设计，也不因self-report complete免审。
- 本轮仅PROGRESS/HISTORY/路线图收件与派发状态同步，git diff --check后中文提交常规推送，未正式发布设计或开始实现。已验收桌面#151保持，双横线只在后续前端片修；未来受控入口身份仍需真实核验，不擅改凭据或指定。

## 2026-10-05 #153复核完成需修订，收取复核并派#154给Kimi

- 用户通知“153已完成”。#153/msg2655为合法完整talk-delivery-1、task_id153匹配、schema自报complete，completed9/unfinished0/blocked0、verification10、limitations9，摘要无省略。complete仅表示独立复核完成；实际设计结论为需修订，P1–P4中等/P5–P7低，无阻塞，业务实现尚未开始。
- DeepSeek独立确认原方案/开发包hash与实际基线、原文件行号、模式/指定两套CAS、前端当前无mode UI、双横线实际结构、无生产侧模式执行消费者；复核期间HEAD从911e117前进到b7fe7ce仅主控docs变化，业务源码零改动。内存SQLite/pydantic探针证实MAX+1路径静默存REAL、响应校验失败、合法expected_version不能再写；未触碰业务库、服务、浏览器、模型或真实等待。
- 主控接受独立复核工作并收取#153：workflow completed、result_message_id2655、收取时间2026-10-05T11:43:01.235806（服务端记录）。方案未通过，不收取#152为已验收；#152原partial/代码块unknown及原报告保留，独立工作完成与方案通过明确分开。
- 冻结复核对象：.tmp/controller-mode-c2-plan-review/review.md 21548字节/SHA256 90f2dfa05790a37ec83d48311d3aeed7645b3ad6df3d14da52c111af5963a499；development.json 7614字节/SHA256 3568d88b8a895588bbd7c0de34aba61636bd1ee8cfd3a21a4c31a7f12aa177e3。原#152方案/包hash e087793e…6c91144、03d40926…0ea2b68d保持，修订写新目录不覆盖。
- Codex裁决需修订：P1新受控wait必须明确启用与旧调用兼容边界，优先默认关闭的显式选择；P2自身身份用API Key反查/api/members/me而非环境/模型标签；P3模式变化检测不等于客户端取消检测，同步stdio取消通知未读到时不能宣称下一节点会响应；P4先确定预算规则/余量/检查节奏/枚举与HTTP/sleep剩余deadline、谁管理总预算，不能留实现者二选一；P5耗尽机制改正并降为低风险可选，不阻塞正常开关主线；P6约定级消费者与实际可验证入口/验收补清；P7身份/项目新增GET计入http_requests并披露。
- 额外事实纳入P2修订：当前主控MCP创建#152/#153的created_by=human:bobo，与长期controller_assignment=agent:codex不同。不能将人类凭据猜成Agent身份，不能借提示词更改指定/密钥/权限；保留既有人工/通用流程，受控入口支持边界及最小核验建议需如实说明，未凭此判桌面MCP连接失败。
- 派前读取最新development_requirements仍为Kimi文字/设计/交互/前端、DeepSeek后端及其他、双方交叉复核；usage-gate decision continue，session/weekly百分比null如实保留。按最小独立顶层参数派#154“主被动开关方案定向修订”给agent:kimi，返回queued/assigned，基线b7fe7ce（执行者记录实际HEAD）。
- #154仅写.tmp/controller-mode-c2-plan-fix/report.md、revisions.md、development.json，逐P1–P7对应修订/证据，禁止改代码/配置/原证据/正式进度或真实模型等待；保留UI/CAS/长期指定/有限授权/桌面提示词已通过合同，双横线并入后续前端片。要求完整裸JSON、本次实际task_id154，无法裸输出则如实记录宿主包装限制。完成暂停，后续DeepSeek定向复核，确认后再拆实施。
- 本轮只更新PROGRESS/HISTORY与路线图，git diff --check后中文提交常规推送。派#154后结束主控等待，用户通知再取件，不因active配置自动开始等待、改身份或立项。桌面#151核心验收与现有执行服务继续保持。

## 2026-10-05 收到#152主被动开关设计，派#153给DeepSeek独立复核

- 用户通知“152好了”。#152/msg2654 runner succeeded、workflow submitted，结果正文为说明+Markdown代码块内JSON，MCP识别unstructured_text/unknown，不能从结束状态或内容词汇推断业务完成。通过稳定结果引用detail完整读2968字符，sha256=0f1df63e7f120be20e5e1f2babc54ea842d3b7d27fadac4b36e0de4beed5a3a7；未读Hall历史或追改原消息。
- 按旧文本/本地交付兼容路径运行python scripts/talk_workflow.py summary .tmp/controller-mode-c2-plan/development.json --expect-task-id 152，合法partial、未截断：completed8/unfinished2/blocked0、verification6（真实页面/模型/等待not_run）。partial保留独立复核和实施未做，本地合法不冒充MCP结构化有效或业务已验收。
- 本地方案report.md为22401字节/hash e087793ebe6541965928c449f340647c44a263cdf794618de8ead53676c91144，development.json4585字节/hash03d409264e8de5878d923b2aec0577e3d7d2ce760333222455903dca0ea2b68d。自报基线36ac16adbbbdb1860ed70dee9b6640684e5ad887；主控当前业务工作区干净，911e117只为派发/提示词文档。方案与原交付不改。
- 方案提出C2-A1等待模式消费者合同→A2模式版本耗尽保护→B项目设置开关与双横线→C真实会话主动链路。仍承认effective=null无主动执行入口；主控只按交付摘要和方案相关节做审查索引，不重复完整源码审查，顺序尚未批准进入实现。
- 派前再次读取development_requirements，仍为Kimi文字/设计/前端、DeepSeek后端及其他、双方独立交叉复核；controller_mode passive/version0、effective null/not_bound，长期指定Codex/version13仅职责配置。按最小独立顶层参数派#153“主被动开关方案独立复核”给agent:deepseek，返回queued/assigned，未手写标题编号。
- 复核包包含原需求/范围/不变项、实际基线与两个文件完整hash、开发者校验及not_run证据、六项验收标准。具体疑点交DeepSeek独立判断：65秒预算与报告“>60秒必掐”表述、取消通知能否在同步stdio下被读到、mode检查是否真能感知取消、通用wait变更对非主控/被动/旧服务的兼容、C2-C实际模式消费者与身份依据待定、版本耗尽风险与优先级。不是只采信自报行号，也不提前裁定方案失败。
- DeepSeek只写.tmp/controller-mode-c2-plan-review/，不改源码/原方案/运行配置或正式进度，不做真实长等待/模型任务/浏览器；完成暂停，由Codex裁决返Kimi修订或通过后拆开发片。要求复核TALK结果完整裸JSON、本次task_id153；不得将verdict添加为未知顶层字段。
- #152复核前暂未收取，本轮未派实施片。正式仅PROGRESS/HISTORY与路线图同步，git diff --check后中文提交常规推送；派#153后结束主控等待，由用户通知完成再取件。双横线仍留后续前端片，桌面MCP#151核心验收保持。

## 2026-10-05 继续主被动开关阶段，派#152给Kimi做交互/执行合同设计

- 用户询问未来主被动开关是否解决持续等待、DeepSeek桌面MCP是否已适配及如何提示连接，并授权继续下一步开发。确认#151已人工验收核心接入；主被动开关会统一使用流程，主动模式还需真实消费者、等待超时/取消配套，不能承诺按钮自然消除DLL或同步阻塞问题。
- 派发前读取最新项目development_requirements：Codex决策/分配/验收，Kimi文字/设计/交互/前端，DeepSeek后端及其他，双方交叉复核。talk_list_agents当前requested_mode=passive/requested_version=0/effective_mode=null/effective_status=not_bound；长期controller_assignment=agent:codex/version13/status assigned。两执行角色availability=available为上报摘要，不把指定等同在线/生效/新增权限。
- 按路线图第3阶段派#152“主被动开关交互与执行合同设计”给agent:kimi，创建返回queued/assigned；最小独立顶层参数，仅project_id/target/title/content，标题不手写编号。实际派发基线36ac16a；后续主控进度提交不改变任务包冻结要求。
- 本片C2-0只核对相关实际源码并交方案：项目设置UI/文案、C1a human CAS与陈旧响应保护、长期唯一主控与真实模式消费者、主控变更及主动转被动的生效节点、授权范围内取件/转审/收尾、同步MCP等待/取消/排队边界、外部桌面对话结束需人工唤回，给有序可实施片与必要验收。保持用户取消旧ACK/token/租约方案；不创建新模型框架或重复worker，不重新做桌面CLI适配。
- Kimi仅写.tmp/controller-mode-c2-plan/方案/证据/完整talk-delivery-1结果；校验真实task_id152，完整裸JSON提交TALK，完成暂停。正式进度/Git由Codex维护，开发与复核顺序执行；完成后再派DeepSeek独立核对实际代码与方案。本轮不等待/轮询#152。
- 双横线修正列入下一合适前端实现片，当前设计片不改UI；后续工作区登记/加载、角色隔离、启停/按项目自启动、群聊、桌面封装仍依路线图，不在本包并行实施。
- 桌面指南新增日常连接提示词：独立调度对话调用已配置MCP/list_agents，限定项目、先读最新要求，用户明确交办再派发，派后结束、人通知完成再取件；当前长期主控Codex保持，提示词本身不改身份/配置或授予长期主控。TALK与需要执行的角色服务仍须运行。
- 验证/收尾：派发前usage-gate decision=continue，百分比均null如实保留；本轮只改PROGRESS/HISTORY、路线图及桌面指南，git diff --check后中文提交并常规推送。未改业务代码、实际mode/超时/权限、启停服务、操作浏览器或跑模型探针。

## 2026-10-05 用户补充确认DeepSeek等待期间持续处于任务状态

- 用户亲眼确认刚才DeepSeek一直显示处于任务状态，补充为桌面本轮持续活动的人工观察；结合已有300秒主动wait及同步MCP源码证据，进一步支持本次超时/排队与主动等待有关的判断。该显示不改变#151已完成/已收取的业务记录，也不证明pwsh DLL错误由等待造成。
- 维持默认被动流程：派发后结束本轮，用户通知完成再读取并收取。仅补充PROGRESS/HISTORY的证据来源，未改代码/配置/任务状态或联系其他Agent；文档格式检查后中文提交并常规推送。

## 2026-10-05 澄清主动等待限制，DeepSeek桌面继续被动收取

- 用户认为本次“环境抖动”源于DeepSeek主动等待任务完成，类似此前Codex主动等待；当前项目已采用被动接收。按该澄清将超时/查询排队优先归入主动长等待的调用方式限制，桌面MCP核心接入验收维持通过。
- 主控仅定点查看现有源码：talk_send_mcp.main逐行读stdin并同步dispatch工具；talk_task_tools.wait_tasks同步阻塞轮询，客户端取消不能立即结束程序侧等待。因此前一wait尚未返回时，同一MCP连接的后续请求无法处理；300秒请求也超当前65秒客户端预算。源码机制支持超时/排队解释，未复现本次日志时序，不宣称已确认所有异常根因。
- DeepSeek桌面调度同样沿用“派发后结束本轮，用户通知完成再读取交付并收取”，默认不调用主动长wait，也不以连续短轮询替代；如未来明确需要主动模式再评估超时、取消与排队。pwsh两次0xC0000142仍作为原因未明的独立观察，不能证明由等待引起，不设为核心验收阻塞或自动派整改。
- 同步PROGRESS/HISTORY、桌面指南、MODULE_bridges、DEVELOPMENT_ROADMAP，仅文档说明修正。未改代码、实际超时配置或服务，未派任务、联系其他Agent、做浏览器/模型/长等待测试。git diff --check后中文提交并按持续授权常规推送。

## 2026-10-05 用户#151桌面核心闭环验收通过，接入切片关闭

- 用户确认DeepSeek桌面→TALK→Kimi→TALK→原DeepSeek桌面对话全通，Kimi正常领取、执行并交付，原桌面会话收取成功。桌面TALK MCP接入切片人工验收通过，现有npm执行bridge和身份凭据继续使用。
- 主控只读核对任务元数据：#151“桌面连通性只读探测：仅回复 DESKTOP_TALK_OK”，created_by=agent:deepseek、target_member_id=agent:kimi、status=succeeded、workflow_status=completed、result_message_id=2648、result_collected_at=2026-10-05T10:34:20.741165（服务端记录）。该结果已由桌面请求者收取，主控不重复收取。
- 主控talk_get_delivery因不在该Task Hall返回403，未绕过成员权限读取正文或操作GUI；元数据为主控核实，桌面实际操作和业务闭环以用户反馈为验收来源。用户未逐项提供九个工具显示/全部动作、独立新建会话步骤或HMR触发方式的证据，不扩大通过范围。
- 用户说明Hall消息2649–2653来自先前DeepSeek桥接会话与Kimi互报在线，Kimi因无决策人在场转为待命；按此记录来源，不计入本次探测结果，不删除历史或作为新立项授权。
- 用户反馈talk_wait_tasks(300s)超客户端工具超时后中断，服务端等待仍会跑完，随后get_task/list_tasks一度排队超时；pwsh两次0xC0000142（DLL初始化失败）。轻量状态查询最终取回结果，业务闭环完成。300秒请求超过当前配置toolCallTimeoutMs=65000的上限；取消/排队机制与DLL环境原因未独立核验，不作已证实因果归因。
- 默认仍按“派发后结束，用户通知完成再取件”。仅在显式需要等待时考虑低于桌面客户端上限的单次有界等待（如30–45秒）并限定总预算；未修改实际timeout、启用自动高频轮询或更改项目600秒等待目标。长等待/排队与pwsh环境问题独立登记待办。
- 正式同步PROGRESS/HISTORY、DSH_DESKTOP_TALK_MCP指南、MODULE_bridges、DEVELOPMENT_ROADMAP：核心验收通过，接入门禁关闭；跨重启、多工作区、无人值守、并发与长等待稳定性仍未验收。指南回滚说明补清复制备份会恢复目标内容，必须先核对期间其它设置，不能靠是否加Force判断覆盖行为。
- 本轮仅文档收尾，git diff --check后中文提交并常规推送；没有派新任务、改代码或运行配置、重跑模型、启停服务或操作浏览器。角色页“参与任务”上方双横线保留一条继续并入下一合适前端切片，尚未实施。

## 2026-10-05 #150定向复核通过，真实桌面MCP配置落地，暂停人工验收

- 用户通知“150已完成”。#150/msg2647是JSON但不符合talk-delivery-1：额外verdict/defects/handoff、两条completed超300字符、complete与unfinished互斥，MCP业务invalid，原件`.tmp/dsh-desktop-mcp-2-fix-review/talk-delivery-1.json`同样校验失败。主控未采信截断预览或追改原结果；保留原件与sha256，创建decision/delivery-normalized.json与normalization.json，仅长项拆分、额外元数据移入limitations，真实unfinished保留令副本conclusion=partial。按实际任务号150校验及完整摘要通过，来源/原complete与MCPinvalid明确保留。
- 独立业务结论：Kimi verdict pass仅限落地保护，defects为空，唯一轻微观察为backup_failed报告缺temp_files_created=0键、不影响保护。实际修订脚本hash ecd9235164a76d5a0f682eef3e308ded133476d1e36bbf20c641f5a7a32288f6、候选hash41eeab30…f9760dea、指南hash696ee408…53c8c3与自报一致；源码确认两项缺口补齐。独立A正常、B同id候选篡改提前拒绝、D替换前外变保留、F失败时外变不覆旧备份均通过；规范化路径边界、独立日志/唯一备份、原证据不变等静态审查无疑点，未重复14组全量。
- 写入前主控只读复查脚本/候选/真实目标/指南完整hash都匹配，日志新路径不存在；默认沙箱CIM查询拒绝，经require_escalated只读确认主进程3084仍2026/10/4 9:32:29启动，host13068参数仍明确对应C:/Users/Administrator/.dsh/profiles/desktop。未读取完整环境/密钥正文或私人会话。
- 经宿主require_escalated审批通道执行已审脚本（先钉住脚本hash，再显式给真实target、原候选及完整expect-target/expect-block hash、新日志，不开log-overwrite），实际rc0/ok=true，无stderr。候选hash/原文件hash/重复预检、唯一字节备份核对、同目录temp写入、replace前二次核对、原子替换和10项写后校验全部通过，原执行者沙箱备份阻碍已解决；无审批拒绝或绕过权限。
- 真实目标`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`写后2275字节，SHA-256 `245407f8390e5086c2bfde3f268241484028b12a183951089b2541deae2398d6`。唯一同目录备份`cordis.patch.yml.bak-talk-mcp-2-fix-20261005-180915`为原1045字节，SHA-256 `4366d52223a9abebe1f8735d980226783a74a32fe8b927b9f187c2e1eb02b085`；没有覆盖旧备份。
- 主控独立读回另存安全摘要`fix/logs/codex-post-apply-check.json`：10检查全过，原六项结构/字节前缀完整保留、仅新增一个mcp-talk/serverName=talk，Python/原launcher映射正确，env仅PYTHONUTF8+TALK_DSH_KEY_FILE路径，无temp残留。fix指.tmp/dsh-desktop-mcp-2-fix/，实际执行日志`logs/apply-target-20261005-codex-1.json`。真实原配置与备份不复制入仓库，只留路径/长度/hash/布尔检查证据。
- 依据已完成范围及独立复核收取#147/msg2644、#148/msg2645、#149/msg2646、#150/msg2647，四任务workflow_status=completed。#147原partial、#148旧文本unknown、#150原invalid历史保持，不把收取当整体GUI/闭环通过；规范化副本是主控格式整理，未假称来自原MCP结构化自报。
- 正式文档同步：指南保留已审R1与保护修订，顶部标当前已落盘避免重复追加，历史5.1/5.2标明任务阶段，新增5.3实际写入/备份/证据/待验收，回滚仅撤本次块并防覆盖期间其它改动；MODULE_bridges与DEVELOPMENT_ROADMAP更新实际阶段，PROGRESS当前快照转人工验收。仅五份授权文档入Git，外部配置/备份与临时脚本不入Git，格式检查后中文提交常规推送。
- 人工验收门禁：暂停下一切片，用户在DeepSeek桌面新建独立调度对话，确认TALK九工具与talk_list_agents三角色/项目要求，明确授权限定只读任务，经原bridge执行后在原桌面对话get_delivery→collect；工具缺失可由用户按指南重载/重开桌面。本轮未操作GUI、自动重启/启停bridge、调用桌面模型或派测试任务；HMR实际加载/GUI工具可见/真实闭环/长等仍not_run。
- 剩余限制：65秒工具超时不支持600秒长等，默认人通知后取件；最终hash检查至replace仍非跨进程原子CAS，保留如实声明；实际配置readback只证明落盘，不代替运行验收。角色页双横线继续并入下一合适前端切片，尚未实现；不恢复内置CLI替换路线。

## 2026-10-05 #149保护修正交付，派#150定向独立复核

- 用户通知“149 ok”。#149/msg2646完整裸talk-delivery-1有效，task_id149匹配，无摘要截断，self-report complete：completed9/unfinished0/blocked0、15验证（含真实GUI not_run）、8限制。complete仅指保护修正片，真实接入并未完成；主控完整读取preview/summary，仍需独立复核。
- 修订临时脚本`.tmp/dsh-desktop-mcp-2-fix/probes/apply_target_patch.py` sha256 `ecd9235164a76d5a0f682eef3e308ded133476d1e36bbf20c641f5a7a32288f6`；原#147脚本保留。自报候选强制64位hash守卫、replace前二次重读原hash、写后仅仍本次版本才回滚；外变时停止/保留外文/manual_action_required。必填独立日志、唯一独占备份、重复写前预检与目标/候选/log路径及默认对象hash钉住一并补齐。
- 定向fixtures A–N 14组all_pass=true，`fixture-results.json` hash6def09e1…e1cef6d；覆盖正常原条目/字节备份、同id篡改候选提前拒绝、初始hash变化、替换前外部写入保留、失败可回滚及外变不回滚、重复/备份碰撞/日志/参数/路径/真实未写/旧证据不变。D/F/H用进程内包装模块函数模拟，非测试专用分支，交复核判断是否证明确实保护路径；不重复全量测试。
- 自报原#147/#148全部文件sha/字节/mtime前后不变；真实目标1045字节/无BOM/LF、完整hash4366d52223a9abebe1f8735d980226783a74a32fe8b927b9f187c2e1eb02b085保持，无外部backup/temp，没复制私人原文件。候选hash41eeab30…f9760dea和内存合并hash245407f8…e2398d6/2275字节不变；未请求真实写入升级权限。
- 仓库唯一开发差异仍指南，#149相对#147 +21/-3，新hash696ee40890c0f2bd9a8fe57d1dbda9d83fe8e561f86aec153c8cc7092e53c8c3；§3.2唯一时间戳备份/禁-Force覆盖、§6同步、新§5.2保护状态/接口证据；原R1/§5.1/§7保留，未改模板/旧功能代码/正式进度或Git。
- 保留真实限制：最终hash检查到os.replace仍非跨进程原子CAS；不扩写CRLF支持，真实目标LF。GUI/HMR工具可见、独立会话派发执行收取、长等待均未验；65秒工具超时不支持600秒长等。保护可通过不等于整个desktop接入完成。
- 派发前读取最新项目要求，按双方交叉复核派Kimi #150“桌面TALK MCP落地保护定向复核”，顶层general最小参数，标题仅名称。#149基线44c14c0；Codex派发进度46b9faf为中间唯一提交，复核实际基线46b9faf与唯一指南差异。任务包包含原需求/范围/不变项、实际hash/接口和证据、未验限制及验收标准。
- #150独立检查真实修订源码/fixture/指南，重点重证B候选篡改提前拒绝、D替换前外变保留、F失败时外变不覆旧备份、A正常字节保护；路径规范化/真实默认hash/日志与备份/异常路径有疑点再定向补测。提供后续主控正确命令与前置检查摘要但禁止执行对真实目标写入，不操作GUI/模型/派发收取/重启/安装/PATH/Git，仅写.tmp/dsh-desktop-mcp-2-fix-review/。
- #147/#148/#149保持submitted，定向复核后统一裁决；通过再由主控经宿主审批通道尝试真实唯一备份+追加，当前未有此升级请求或自动审批拒绝。Codex仅更新PROGRESS/HISTORY、格式检查并常规提交推送，指南待审不暂存；派发后结束，用户通知#150完成再取件。

## 2026-10-05 #148候选复核通过，落地保护先修，派#149

- 用户通知“148已完成”。#148/msg2645有前言和Markdown围栏，MCP自由文本unknown且预览截断，不据此验收；按项目本地回退执行 `python -X utf8 scripts/talk_workflow.py summary .tmp/dsh-desktop-mcp-2-review/delivery.json --expect-task-id 148`，合法实际号匹配、完整摘要未截断，结论partial，完成10/未完成4/阻塞0。没有把MCPunknown追改成结构化partial。
- 独立复核确认#147事实：安装0.2.0-rc.2/Python3.12.1/PyYAML6.0.3；桌面主进程与host实际profile/cwd证明、白名单只读PEB范围可信。Kimi自写重渲染候选与开发者字节一致（1229字节/28行/hash41eeab30…f9760dea），独立从app.asar抽取stdio10字段、unknown=[]，路径6项转义通过；原目标1045字节/LF/6条/hash4366d522…02b085保持，内存合并2275字节/hash245407f8…e2398d6，前缀与原条目不变，仅增mcp-talk。
- 权限与边界独立成立：profile目录仅原4文件，无备份或临时残留，home层不存在；ACL与backup_failed Errno13一致，仍是执行者沙箱拒绝，主控未发过require_escalated真实写入审批、无自动审查拒绝。Host路由401/404、GUI可见/派发收取及长等仍not_run；file工具目录探针不能外推真实桌面加载。
- R1指南§3.4复核通过：行首锚定配置块、显式UTF8、PS5.1产物无BOM/CRLF、原两条保留仅一mcp-talk；其新增未写状态/回滚前置/home说明与事实一致。实际仓库差异仍仅指南（+34/-11/hashb2df2b5a…2848），复核没改仓库或开发证据，只写.tmp/dsh-desktop-mcp-2-review/。
- 落地脚本隔离fixtures五组通过：正常追加与字节备份、初始hash拒绝、重复写后回滚、CRLF失败回滚、额外insert篡改拒绝。但Kimi另发现两项低中缺口：没有候选hash钉住（同id/serverName篡改command可过写后校验），首次目标hash到os.replace之间外部写入可能被覆盖。另有日志硬编码会覆旧证据、无重复写前预检、固定.bak-manual -Force覆盖旧备份及仅LF观察。
- Codex裁决：候选/R1/取证已完成范围复核可信，但真实写入前必须先修两项保护，不直接运行旧脚本。按最新开发要求派DeepSeek #149“桌面TALK MCP落地保护修正”，顶层general最小参数、名称无手写编号；实际基线44c14c0，开发交付指南尚未提交。#147/#148暂不收取，保持原partial/unknown历史，待修正及定向复核统一裁决。
- #149只在.tmp/dsh-desktop-mcp-2-fix/复制修订临时apply脚本，保留#147/#148全部原件：强制候选完整hash、保留初始原hash并在替换前重核、外部变更时不覆盖/保守回滚、显式独立日志、唯一不覆盖备份/重复写前检查；不扩写CRLF或永久安装器。唯一授权仓库文档为现指南§3.2唯一备份及相关准确说明，保留R1/所有未验项。
- 必要隔离fixture覆盖同id候选篡改提前拒绝、初始hash变化、备份后替换前外部写入保留、写后仍本版本可回滚/已外变不覆盖、正常前缀/条目/备份、重复/备份碰撞/独立日志。双重hash降低窗口但不能宣称消除最终检查后的跨进程竞态。禁止真实profile/backup写入或该升级审批、GUI/模型/派发收取/重启/PATH/Git，只读metadata/hash允许，不复制私人原文件。
- 修正完成交Kimi独立定向复核；通过后主控再经现有宿主审批通道尝试真实备份追加，实际目标需重新核验。Codex本轮仅正式记录格式检查/提交推送，开发指南不暂存，派发后结束由用户通知#149完成；双横线前端待办继续保留。

## 2026-10-05 #147交付候选、真实备份受沙箱阻碍，派#148独立复核

- 用户通知“147完成了”。#147/msg2644合法talk-delivery-1、实际任务号匹配，完整preview/summary合读无截断：partial，completed9/unfinished4/blocked1，runner succeeded/submitted。仍需独立复核，不收取为整体接入完成。
- 开发自报逐进程核验：运行desktop主进程3084（2026/10/4启动）环境块无DSH_HOME，host13068命令行与cwd明确指向`C:/Users/Administrator/.dsh/profiles/desktop`；User/Machine无覆盖仅补充。PEB只读探针仅回显白名单。安装0.2.0-rc.2、Python3.12.1；目标补丁6既有条目无TALK冲突，home层不存在。证据待#148独立审查，不以默认目录推测替代。
- 候选仅配置块，28行/1229字节/sha256 `41eeab30f709afd07485d892a65a29ff11241902f479e7d790e99497f9760dea`。自报31/31实际安装schema对照、路径转义及内存合并通过（原6条/原字节前缀保留，仅新增mcp-talk）；probe九工具/rc0/serverInfo匹配、transport=file；check只读agent:deepseek/prj_e8fe7066bbec通过，外置key只记路径。file回退不是真实GUI加载证据。
- 真实写入未发生：写前原哈希守卫通过，同目录唯一备份`cordis.patch.yml.bak-talk-mcp-2-20261005-165149`创建被PermissionError Errno13拒绝，脚本backup_failed即停。目录对沙箱用户仅ReadAndExecute；没有跳过备份、绕过沙箱或改其它目录。Host19387只读路由401/health404，GUI/HMR工具可见与真实派发收取均not_run。
- 仓库实际差异仅`docs/guides/DSH_DESKTOP_TALK_MCP.md`（自报+34/-11）：§3.4 R1限定配置块替换并显式UTF8读写、§5.1未写状态、§6回滚前置、§7home证据；PS5.1自测无BOM/CRLF、原前缀/原2条保留、仅1个insert/mcp-talk。模板/旧功能代码/正式进度未被开发者修改；临时证据仅.tmp/dsh-desktop-mcp-2/。
- 派发前读取最新项目开发要求，按双方交叉复核派Kimi #148“DeepSeek桌面MCP接入候选独立复核”，顶层general最小参数、名称不带手写编号。开发基线2433d34，期间Codex仅进度提交8addafe；复核实际基线8addafe与唯一指南差异。任务包包含原需求/不变项、实际差异、全部必要证据、明确验收与剩余未验范围。
- #148必须独立审查目标进程证据/白名单、候选schema/身份工具目录、有效合并/无私人副本、指南R1和权限失败处理；额外只读审查临时apply_target_patch.py的目标限制、候选/目标哈希守卫、备份唯一性、幂等/重复冲突、写后保护/错误回滚，必要隔离fixture验证。禁止真实profile/backup/key写入、GUI/模型/派发收取/重启或Git，只写.tmp/dsh-desktop-mcp-2-review/。
- 主控裁决路线：独立复核通过后，拟通过宿主现有require_escalated审批通道尝试真实备份与仅追加（需重新核验实际目标/原文件未变）；当前尚未请求此审批，也不存在自动审批审查的拒绝，不能把执行者无审批通道的PermissionError误报为自动审核拒绝。不跳过备份、不让用户接管本可经授权完成的动作；若审批明确拒绝则按实际原因报告限制。
- 本轮Codex仅更新正式连续性记录、格式检查与提交推送，指南待复核不提交；#147保持submitted。派发后结束，由用户通知#148完成再收取，不轮询，不恢复内置CLI替换，角色页双横线待办保持。

## 2026-10-05 派#147桌面TALK MCP配置接入

- #145/#146已收取并以2433d34提交推送6文件，暂存格式检查通过。派发前重新读取项目最新development_requirements，按DeepSeek后端/其它执行、Kimi独立复核分工，派#147“DeepSeek桌面TALK MCP配置接入”；实际基线2433d34，工作区干净，顶层general最小参数、标题只名称。
- 本片使已审模板落到实际desktop profile：先核验安装版本与实际进程/启动路径DSH_HOME事实，不以默认目录/环境快照推定目标；检查两层补丁冲突、隔离渲染和只读schema/probe/check。目标不明或权限受阻则只交候选和具体缺失项，不盲写、不绕过宿主审批。
- 授权仅已确认的真实desktop/cordis.patch.yml追加TALK MCP块、同目录唯一时间戳原始字节备份与安全临时写入；写前哈希防外部变化、写后原配置保留/重复条目核验，失败仅撤回本次变更，避免覆盖他人后续修改。私人配置/备份不进仓库，凭证只写外置文件路径，身份权限和现有npm执行服务保持。
- 仅允许公开无模型只读host/loader状态核验加载；不可用则留GUI待用户验收。禁止GUI、自动重启/杀进程/安装/PATH/bridge启停、模型、真实派发/收取、自动长等。独立桌面会话有限派发到原执行服务、原会话读交付收取仍待用户接入验收。
- 仓库改动只授权指南§3.4的R1配置块限定替换与UTF8读写，以及本片准确状态/回滚/用户验收说明；其它助手/证据只.tmp/dsh-desktop-mcp-2/。不修改模板、旧功能代码或正式进度，不写Git。完成交完整裸JSON并按实际任务号校验，禁止旧式“结论+路径”；加载或闭环未验仍partial。
- Codex本轮仅更新派发连续性记录并格式检查/提交推送，派发后结束，由用户通知#147完成再收取摘要与派Kimi复核；角色页双横线待办继续保留。

## 2026-10-05 #146独立复核通过，收取#145/#146桌面MCP配置准备

- 用户通知“146完成”。#146/msg2643为旧式自由文本+本地路径，MCP业务结论unknown，截断预览不作为完整交付。按项目允许的本地回退执行 `python -X utf8 scripts/talk_workflow.py summary .tmp/dsh-desktop-mcp-1-review/review.json --expect-task-id 146`：校验通过，完整摘要未截断，复核结论complete；同意#145原partial（配置准备完成，真实激活未验）。不把MCP unknown改写为结构化complete。
- Kimi独立从安装版app.asar抽取代码核对：桌面0.2.0-rc.2、desktop host patchFiles=[]、bundle→profile→home→overlays层序、parsePatchList顶层数组及insert语义、MCP stdio schema九个config键、工具命名与环境合并、CLI拒绝desktop profile、HMR两份用户patch监听/2秒稳定写窗口与无MCP图形表单。现有profile patch已存在，指南要求追加保留原设置正确。
- 复核独立重跑：schema validator rc0/ok=true/unknown_config_keys=[]；九工具tools_match=true、serverInfo=talk_tools_mcp 2.0.0、transport=pipe；key文件只读身份member=agent:deepseek及项目匹配；含空格中文路径space_path_single_arg=true。开发原探针transport=file，两种测试运输均不证明桌面真实MCP加载。
- R1（低、非阻塞）：指南§3.4全文Replace把模板头部占位符注释一并替换；配置功能不受影响。Codex裁决配置准备通过，下一接入片限定配置块替换处理。reconnect.enabled=true与安装版默认相同为无害冗余；只读清单mcp-talk预期仍待实际GUI确认。
- 未完成保持：实际桌面进程DSH_HOME确认、GUI/HMR工具可见、独立桌面会话有限派发→旧bridge执行→原会话读交付并收取。原模板65秒工具超时不覆盖600秒长等，默认人工通知后取件；不把原desktop调查/cmd换行/S1a当接入前置。
- 依据独立复核收取#145/msg2642、#146/msg2643，两任务workflow_status=completed；#145原partial与#146旧式MCPunknown历史保持。此前两项未跟踪模板/指南现纳入Git，同步正式进度/桥模块/路线图，仅格式检查，不重复完整测试。
- 下一明确片为桌面profile接入：先核验实际目标与已有配置、唯一备份、离线预检，再仅追加TALK MCP块，保留原配置与既有执行程序；不自动重启、模型调用或派测试任务，完成交Kimi独立复核后用户验收。角色页双横线待办不在本片。

## 2026-10-05 #145桌面MCP配置准备交付，派#146独立复核

- 用户通知“145 ok 了”；读取#145/msg2642合法结构化完整摘要（preview及summary_text合看），任务succeeded/submitted，自报partial，已完成10项、未完成4项、阻塞0。格式/任务号有效只代表自报一致，不提前收取或视为业务验收。
- 开发派发基线33e7633；期间Codex仅提交范围文档10e314f。实际差异为两个新未跟踪文件：`deploy/dsh/desktop-talk-mcp.patch.template.yml`、`docs/guides/DSH_DESKTOP_TALK_MCP.md`；无已跟踪功能代码变动。临时报告/探针/原日志在`.tmp/dsh-desktop-mcp-1/`。
- 开发自报：依据已安装桌面0.2.0-rc.2源码，用户配置是`~/.dsh/profiles/desktop/cordis.patch.yml`顶层loader补丁数组；模板注册mcp-talk，五项占位符，env仅外置TALK key文件路径。指南包含位置/格式、合并、重载、身份权限、人工验收与回滚。上述版本/合并/HMR断言交独立复核核实，尚非桌面实测结论。
- 自报证据：`logs/validate-template.log`离线结构/schema ok；`logs/probe-desktop-template.log`经既有入口返回9工具、tools_match=true、serverInfo=talk_tools_mcp 2.0.0、returncode0，实际transport=file；`logs/check-identity.log`只读身份agent:deepseek及项目prj_e8fe7066bbec匹配。file回退仅证明测试入口服务可列工具，不证明真实桌面stdio接通。
- 保留未完成/限制：实际GUI保存/加载与9个工具可见、独立桌面对话有限派发→既有bridge执行→原会话读交付/收取、实际进程DSH_HOME核验仍待人工接入；CLI拒绝desktop profile，不能拿headless dump作证明。模板toolCallTimeoutMs=65000不能直接覆盖600秒长等，当前默认人工通知后取件。同一会话并发写入仍需避开，非技术互斥保证。
- 派发前按最新项目开发要求（Codex决策、Kimi文字/设计/交互/前端、DeepSeek后端/其它、双方交叉复核）交Kimi #146“DeepSeek桌面TALK MCP配置独立复核”。顶层最小general参数、标题无手写编号；复核实际基线10e314f，两项新文件及安装源码/原日志必须独立检查。
- #146任务包完整包含原需求、范围/不变项、实际基线/差异、开发证据和验收标准。重点检查loader数组/层序与保留已有配置、真实MCP schema/Windows路径和launcher映射、key文件与身份项目权限、HMR版本依据、65秒超时说明、人工验收未测标记和回滚。仅离线/只读定向检查，禁止GUI、真实profile/key修改、模型、真实派发/收取、服务重启/安装/PATH、Git及全量回归；只写`.tmp/dsh-desktop-mcp-1-review/`，发现问题交开发者修复。
- 现有npm DSH、TALK MCP与执行bridge继续使用；不恢复内置CLI替换/S1b/dsh.cmd运输调查，不新增重复worker/member。角色页双横线小改动继续并入下一合适前端切片，尚未实现。
- Codex仅记录正式进度，不重复完整审查或操作浏览器；#145保持submitted，#146派发后结束等待，由用户通知完成再取件。两项开发交付先不提交；本轮仅进度记录格式检查并常规提交推送。

## 2026-10-05 用户收窄桌面目标为MCP接入，派#145配置准备

- 用户明确认为已有桌面能显示历史chat/TALK任务，当前无需改动之前的执行程序，目标仅适配桌面MCP，使其可分配TALK任务。Codex据此收窄：桌面作为MCP工具客户端，既有MCP服务/launcher、TALK任务服务与npm bridge继续复用。前面S1a是已完成额外调查，不是本需求的前置；S1b/直接exec/参数运输/内置CLI替换停止当前推进，历史事实保留。
- 主控读取最新development_requirements，派DeepSeek #145「DeepSeek桌面TALK MCP接入配置准备」，基线33e7633、派发前工作区干净；完成后Kimi独立复核。授权仅新增一种符合安装版格式的deploy/dsh桌面配置模板、docs/guides/DSH_DESKTOP_TALK_MCP.md及.tmp/dsh-desktop-mcp-1/报告/交付/验证。
- 本片须核查实际桌面MCP配置加载入口/格式/重载方式，复用dsh_talk_mcp_launch.py与talk_terminal_mcp.py，提供具体路径/外部TALK key占位、身份/项目/工具范围和一轮手工委派/同会话收取验收；不凭历史CLI/ACP闭环外推桌面已接入，不为适配制造新服务器或worker。已有launcher/bridge/后端、真实profile/配置/权限不改。
- 先离线/必要只读预检，不自动真实派发/collect/调用模型，不读取provider凭证或私人会话正文，不操作GUI/启停现有服务/改PATH/安装依赖。实际桌面保存/重载留配置包独立复核后的接入阶段；若需改既有代码须证据和最小建议交主控，不自行越界。双横线UI待办继续下一前端片。
- 本轮usage-gate continue但精确百分比null，遵守一片刹车。主控只同步范围与派发记录，diff格式检查后提交推送；派发后结束，由用户通知#145完成再取件。

## 2026-10-05 #144定向复核pass，S1a正式收取与文档收尾

- #144/msg2641有效task_id144结构化complete，独立结论pass；13项定向验证通过，修订报告/交付与#142已审证据逐项一致，五个补正产物哈希重算MATCH，原问题关闭。此次只核修订，不重跑原探针；主体隔离/安装版源码/真实home快照沿用#142独立审核。
- Codex据此收取#144/#143/#141，均workflow_status=completed，结果消息2641/2640/2638；#142此前已收取。流程收取不回写原141错误或142 partial/needs_changes，正式当前结论以143修订+142独立证据+144复核为准。S1a调查完成，不代表消除已发现CLI限制。
- 已证实桌面内置CLI0.2.0-rc.2在临时home/项目隔离环境下可无凭证无模型自省，headless dump初始化4文件，desktop保留profile拒绝，临时home补丁路径见输出。原p5仅三个独立参数+中文保真；Kimi k2单参数内嵌LF经当前桌面dsh.cmd截断（只first-line进入argv、exit1），直接exec Electron exe与实际桥参数运输未测，不泛化所有入口。
- 元数据结论限已采样profiles（跳过node_modules）/顶层/凭证指标，sessions/storages为聚合指标；无全文件字节级零写入或逐进程因果证明。keep21/去重20+新增5=最终25、p1–p5退出码0/0/1/0/1、字节/字符口径均核对；进程数前后5未存证，不作为独立证据。未做网络抓包，短耗时不证明绝对零网络。
- 同步MODULE_bridges与DEVELOPMENT_ROADMAP，更新PROGRESS为S1a已收取快照，原调查与补正关系可追溯；本轮无功能代码变更，不重复执行模型/探针/全量测试，不启停服务或操作GUI。正式文档diff格式检查后统一提交推送，临时产物不随Git跟踪。
- 现有npm0.1.5-rc.2 headless bridge继续复用；桌面MCP配置加载、GUI续聊、直接exec/桥参数运输及S1b真实任务契约均未执行。后续可先核查桌面MCP配置复用范围，内置CLI替换和真实模型另列任务包/授权。本轮完成单片收尾后暂停扩片，用户双横线小改动留下一合适前端切片，不另开任务。

## 2026-10-05 #143报告补正交付，派#144定向复核

- #143/msg2640有效task_id143结构化complete自报，结论仅指报告补正完成；原141/142报告、交付、日志与消息保持。新增.tmp/dsh-desktop-s1a-fix/六文件（修订报告/交付/对照及3份日志），无被跟踪实现变更；当前HEAD86fed33、工作区干净，#141/#143仍暂未收取。
- 执行者报告已统一p5多个独立参数/中文不截断与单参数内嵌LF经当前dsh.cmd截断的区别，引用#142 k2证据；统一p1–p5退出码0/0/1/0/1、keep21项/最终25变量名，收窄真实home为采样元数据不变、进程数5为当时观察未存证，并区分字节/字符口径。以上待实际修订定向复核，不把自报校验当最终验收。
- 主控读取最新development_requirements，派Kimi #144「桌面CLI报告补正定向复核」，基线86fed33。审查仅比较修订文件与#142已审证据、计数/退出码/来源/限制一致性，不重复主体调查或任何探针；旧错误可作为更正引用保留，不能机械按词出现判残留。只写.tmp/dsh-desktop-s1a-fix-review/。
- #143领取期间看见Codex两份PROGRESS修改、随后057cacd→86fed33，属于派发后主控记录提交的阶段差异，非执行者代码改动。现有npm bridge保持，S1b真实执行、直接exec/参数运输、GUI/MCP保存配置未执行；角色双横线小改动继续等后续前端切片。
- 本轮只更新正式进度并派发复核，未改代码、未重跑探针或启停服务；diff格式检查后提交推送。派发后结束，由用户通知#144完成再取件裁决并同步正式模块结论。

## 2026-10-05 #142复核发现参数误判，收取复核工作并派#143报告修订

- #142/msg2639有效task_id142结构化partial，独立结论needs_changes。Kimi独立检查实际脚本/安装版源码、10份输出哈希及原始快照，确认临时home隔离、自省/初始化等主体证据成立；真实home仅profiles（跳过node_modules）与顶层/凭证元数据采样，sessions/storages为聚合指标，保留无法证明字节级零写入及逐条进程归因的限制。
- 唯一必须修正事实：#141 p5是三个独立参数，不含单参数内嵌换行，只证明多参数/中文未截断；Kimi k2隔离探针实测单参数内嵌LF经过当前桌面dsh.cmd后仅first-line进入argv。原“多行argv未截断”结论错误，直接exec Electron exe未测，不能泛化所有入口。证据.tmp/dsh-desktop-s1a-review/logs/k2-newline-arg.console-evidence.txt，原报告/脚本/日志保留。
- 主控采纳复核，将#142复核工作收取为completed但保留原partial/needs_changes；#141仍未收取。按最新development_requirements派DeepSeek #143「桌面CLI隔离验证报告补正」，基线057cacd、工作区干净，仅新.tmp/dsh-desktop-s1a-fix/内写修订报告/交付，不覆盖原141/142产物，不改代码/真实环境，不重跑探针。
- 修订包要求统一p5/总论/验证/限制/进度草稿口径，核对系统环境变量计数（原22、Kimi21）、按p1–p5标记退出码0/0/1/0/1，进程数5补注为当时开发者观察未留独立证据；禁止用现在输出补造历史。真实home表述保持采样边界，npm绕过分支不命中不构成必须改代码依据。完成后再交Kimi定向复核，Codex维护正式文档/收尾。
- 本轮不启动S1b真实模型、ACP/SDK、GUI/MCP保存配置或桥适配；双横线前端待办继续保留。派发后结束主控等待，由用户通知#143完成再取件。只更新进度文档，diff格式检查后提交推送。

## 2026-10-05 #141隔离验证交付，派#142独立复核

- #141/msg2638有效结构化complete自报，task_id141匹配、无阻塞/未完成；本地.tmp/dsh-desktop-s1a/含报告、脚本、安装版抽取源码、原始快照与脱敏输出，工作区被跟踪文件未改，HEAD为Codex此前文档提交6c1a6fa。正式业务验收尚未完成，#141暂未收取。
- 执行者报告：桌面内置CLI0.2.0-rc.2的version/help/headless dump在临时home成功，desktop profile被拒、临时headless初始化4文件；临时home补丁标记出现在dump层标签。真实home部分元数据快照相同、背景变化早于探针窗口；内联diff数组键缺陷已披露，转用单独脚本重算。多行中文argv错误回显、凭证隔离、零模型/未联网拉取等均为待独立核实的证据与自报，未由Codex重复实测。
- 按最新development_requirements派Kimi #142「DeepSeek桌面内置CLI隔离验证独立复核」，带原需求、实际基线与文档提交前移、全部证据索引及验收边界。重点独立重算原始快照，核对递归范围/目录mtime和因果限制、环境与凭证解析路径、多行单参数保真、零网络表述的证据强度、npm绕过分支未命中不能证明必须新增bridge代码。
- 审查仅写.tmp/dsh-desktop-s1a-review/，必要安全自省用自身临时环境，不覆写开发者证据、不读私人正文、不改真实home或启停进程；无真实模型、GUI、MCP保存配置、ACP/SDK或桥开发。共享开发已暂停，用户通知#142完成后取件裁决；双横线小改动继续等后续前端片。
- 本轮仅更新正式PROGRESS/HISTORY与派发审查，不执行S1a探针或全量测试；进度文档通过git diff --check后提交推送，派发后结束主控等待。

## 2026-10-05 F2人工验收通过，派#141隔离启动验证并登记横线小改动

- 用户明确“验收通过，继续下一项”，F2人工门禁释放；功能f743962与进度f731789均已推送。保留#140原partial/needs_changes报告及其文档补正事实，不推断用户每个极端场景均逐项实测。
- 用户另反馈角色页“参与任务”上方两条横线，要求仅保留一条，并在后续切片顺手改。已登记至路线图与当前快照，尚未改UI；下一合适前端包并入，不专门派片，不混入DSH验证。
- 主控读取最新development_requirements，按DeepSeek执行/Kimi独立复核派#141「DeepSeek桌面内置CLI隔离启动验证」。基线f731789、派发前工作区干净；只写.tmp/dsh-desktop-s1a/。依据#128修订报告§5.1/#129复验，先检查初始化和home解析，再用显式桌面shim路径、临时home/项目与隔离子进程env做无凭证无模型自省。
- 任务要求不继承真实凭证，不读私人会话正文，元数据快照区分桌面/bridge背景活动，无法归因写unknown；多行argv仅可在无模型模式安全验证，无法做到列not_run。不得由help成功外推真实执行契约通过。既有npm bridge与TALK MCP不改；S1b真实模型、ACP/SDK、GUI续聊/MCP保存配置、自启动另片。
- usage-gate返回continue但精确百分比为null，按项目单片刹车。派发后结束，由用户通知#141完成再收取交付并派Kimi审查；本轮仅同步验收状态、用户待办与派发进度，不启停服务、不操作浏览器。

## 2026-10-05 #140独立复核收取，F2文档补正与收尾

- #140/msg2637有效结构化partial，独立结论needs_changes（低严重度，仅文档）。实际功能范围、入口零残留/无空引用、混合样式、子任务弹窗打开→初始化→POST携带parent_task_id与authorization_epoch→关闭取消、原权限门控均通过。复核者逐文件运行Node148/148、页面契约9/9与8组自写真实函数切片探针通过；逐文件方式因沙箱test runner子进程限制，断言未跳过。
- 唯一问题为CONTROLLER_ASSIGNMENT_ACCEPTANCE第13行当前版本仍写f1-fix，回归步骤引用“上述版本”随之过期。Codex按决策角色文档维护职责直接将该一处更新为20261005-role-desc-f2，核对index四处资源一致，并复跑页面契约9项全过；证据.tmp/remove-top-task-entry-close/python-contract-tests.log。未改功能代码，不为一行文档补正再派开发任务。
- 问题关闭后主控正式收取#140与#139，workflow_status均为completed；原#140partial/needs_changes报告保留，不改写历史为原报告pass。同步MODULE_webui/验收指南，B1/F1已人工通过，F2仍待用户检查页面效果。
- 2026-10-05必要验证与正式进度完成后，创建f743962“移除顶部新建任务入口并保留详情子任务流程”，14文件+63/-51，已常规推送origin/codex/terminal-return-codex；PROGRESS/HISTORY另作进度收尾提交。真实浏览器视觉/点击与真实创建落库未由Agent验证，未启停真实服务、未做真实派发或全量Python回归。F2完成后按前端切片/人工门禁暂停，桌面MCP未派发。

## 2026-10-05 #139顶部入口移除交付，派#140独立复核

- Kimi #139/msg2636有效结构化complete自报，任务号匹配且无摘要省略；删除顶部新建任务DOM、专属绑定/禁用同步/样式，更新空态和过期注释，保留共享弹窗、详情子任务与公共API/MCP/SDK/pi及权限。资源20261005-role-desc-f2，五份授权入口文档已同步，后端未改。
- 开发者报告Node148、页面契约9、5组真实app.js函数切片探针及两份JS语法检查通过，日志索引在.tmp/remove-top-task-entry/logs/；未做真实浏览器、全量Python或真实派发，不能将自报与模拟执行当独立验收。
- 主控读取最新development_requirements，按Kimi开发/DeepSeek交叉复核派#140「顶部新建任务入口移除独立复核」。审查包带原需求、基线a240128、14份开发变更与2份主控进度变更区分、测试证据与边界；重点实际子任务打开/初始化/创建/取消链路、混合样式、版本和文档准确性，只写.tmp审查目录、不并行改码。
- #139暂未收取，开发已暂停；派发后结束主控等待，由用户通知#140完成再取件裁决。当前开发与进度改动未提交，独立复核通过后统一收尾，页面效果交用户验收。

## 2026-10-05 角色说明人工验收通过，派#139移除顶部入口

- 用户明确“验收通过，继续下一项”，角色说明B1/F1人工验收门禁释放；此前旧后端只读提示已解释，不推断用户具体重启过程或每项边界测试均逐一执行。功能c147d09与进度a240128已推送。
- 主控读取最新development_requirements，确认前端Kimi、DeepSeek独立复核；派#139「移除顶部新建任务入口」，基线a240128、派发前工作区干净。范围仅顶部按钮及专属代码/样式/空态/旧注释与必要文档，保留共享创建弹窗、详情子任务、公共API/MCP/SDK/pi与权限。
- #139完成暂停，用户通知后取件并派独立审查。正式PROGRESS由Codex维护，业务与授权局部入口文档由Kimi修改，不并行改码；本轮不派桌面MCP任务。验收与派发记录随F2收尾提交推送。


## 2026-10-05 #138复验通过，角色说明里程碑提交推送并等待人工验收

- #138/msg2635有效结构化complete；DeepSeek独立核对N1-N5全部关闭，实跑Node148/页面9/后端104与3项自写探针全过，原始日志非空、数字可复算。探针包含真实app.js函数切片，仍不等于真实鼠标/焦点/视觉验收，限制如实保留。
- Codex据此收取#135/#137/#138，均completed，#136此前已收取。#137自由文本MCPunknown历史保持；不因独立复验改写原报告格式。同步MODULE_webui与验收指南，资源20261005-role-desc-f1-fix。
- 2026-10-05正常授权git add/commit/push均成功，旧自动审批额度故障本轮未再出现。提交c147d09“实现项目角色说明编辑并整理已复核控件与文档”已推送origin/codex/terminal-return-codex（23文件），包含B1/F1、已审#123/#124清理及既有相关文档；本次不重复开发者/复核者完整测试。
- 功能已可独立体验，依AGENTS人工验收门禁暂停新片：用户按ROLE_DESCRIPTION_ACCEPTANCE验证名称→说明→任务位置、保存刷新/恢复默认、草稿/焦点光标/长摘要。F2顶部新建任务移除仍待实施，桌面MCP也未新派。此处暂停来自项目既定里程碑规则。
- 本轮另提交PROGRESS/PROGRESS_HISTORY作为收尾交接；真实页面未验证，服务未自动重启。


## 2026-10-05 #137前端修正交付，派#138定向复验

- Kimi #137本地delivery.json经summary --expect-task-id137校验通过，complete自报；TALK msg2634带前言，MCP仍为自由文本unknown，不改写原消息事实。报告N1-N5已落地：空白保存按钮、摘要两行截断、三类404错误、名称/说明/任务静态分段、只读可复制及5项行为回归。
- 开发自报Node148（角色说明21）、页面契约9、后端相关104与JS语法通过；本次有非空node-tests.log/python-tests.log待复核验证。真实浏览器焦点/光标与视觉仍待人工，不因模拟测试通过视作页面验收。
- 按最新开发要求派DeepSeek #138「角色说明前端修正定向复验」，只核对修正与必要回归，特别区分真实app.js执行和源码/测试桩证据。#135/#137暂未收取，F2另片未启动。
- 正式进度更新；未并行改码，未提交推送。用户通知#138完成后取件。


## 2026-10-05 #136审查收取，主控裁决先补齐F1细节，派#137

- #136/msg2633有效结构化complete；独立审查认可主体实现，Node143、页面9、后端104、回归567通过，另169项中145通过24受子进程管道限制（可执行合计712，非全量通过）。原始日志缺失与fake DOM焦点局限保留，不把直接handler调用当真实disabled按钮可用。
- 主控采纳实际发现但未接受直接放行#135：N1超长全空白被UI禁保存、N2摘要未截断、N3非名册404误降级均应补齐；N4说明在任务表后不符合用户名称下原需求，授权最小拆为名称/静态说明/任务三段，继续保留静态编辑器节点；N5补跨项目/账号/超长空白等行为回归。无需再设计轮次。
- #136审查工作已正式收取completed，原报告通过结论保留；#135暂未收取。按最新开发要求派Kimi #137「角色说明前端验收细节修正」，完成交DeepSeek定向复验。F2独立待做，未并入；不派桌面MCP任务。
- 正式进度更新；本轮未改业务代码、未重复全量验证、未提交推送。用户通知#137完成后取件。


## 2026-10-05 桌面端显示TALK会话的人工验证

- 用户先观察到DeepSeek Harness桌面端继承此前对话，随后明确核实：桌面端最新chat对应TALK #133任务。将“桌面UI能显示TALK任务会话”更新为人工确认，证据限定为#133，来源为用户核对；Codex未操作桌面或读取私人会话。
- 同步MODULE_bridges与PROGRESS当前结论。未据此确认有效DSH_HOME路径一致、桌面续聊成功、双端并发安全或内置CLI受管适配通过；S1a/S1b仍未执行，现有运行器未切换。#136仍按原流程等用户通知取件。
- 本轮仅更新上述三份文档，差异格式检查通过；未提交推送。


## 2026-10-05 #135前端F1交付，派#136独立复核

- #135/msg2632有效结构化complete自报，静态同级编辑面板、默认/自定义说明、草稿/迟到响应隔离、保存核实与缓存/列表同步、Python空白集合、只读/降级均已实现。F2顶部入口移除仍未做，后端B1与既有修改保留。
- 开发者报告Node143、页面契约9、后端相关104、排除4个完整子进程模块的Python567通过，JS语法通过；真实浏览器光标/焦点未验证，fake DOM能力限制如实保留。主控未重复完整审查或测试。
- 按最新development_requirements派DeepSeek #136「角色说明前端编辑独立复核」，重点静态DOM、真实同步链路、保存期间续输/切换/迟到响应、缓存更新、空白/404边界与回归；只写.tmp/role-description-f1-review/。#135暂未收取，开发暂停、禁止并行改码。
- git status确认20项M+3项未跟踪（含后端和前端新增测试）；正式进度更新，未提交推送。默认用户通知#136完成后再取件。


## 2026-10-05 后端B1验收收取，派#135前端编辑

- #134/msg2631为自由文本，MCP结论unknown；本地delivery.json的task_id误填talk-delivery-1，summary --expect-task-id 134失败。Codex依据任务与review.md明确归属，在同目录新增delivery-normalized-by-codex.json，仅改task_id为134，校验通过；原文件与原消息完整保留，不冒称执行者原交付有效。
- 独立review.md判实现通过，无阻断；Kimi报告实跑针对性16项及565+169=734项回归通过。开发者排除的是4个完整模块169项，非仅24项；原732/708/24因full-suite.log空文件无法复验，保留限制，不采作最终验收证据。
- 非阻断N1（projects.py路径member_id.strip归一化）作为低优先级后端待办；N2（空日志与not_run口径不一致）已纳入后续交付日志要求。按独立代码复核结论接受后端B1，#133/#134正式收取completed；界面功能尚未完成。
- 派Kimi #135「角色说明前端编辑实现」，只做F1，后续交DeepSeek独立复核；#132前端N1-N7相关约束均进入任务包，重点静态兄弟面板、草稿/迟到响应、Python空白集合、保存后即时列表重绘。F2顶部入口移除不并行。
- 本轮只改进度与归一化交付副本；未自行重复全量代码审查或测试，未Git提交推送。等待用户通知#135完成再取件。


## 2026-10-05 #133后端交付，派#134独立代码复核

- #133/msg2630有效结构化complete自报，新增角色说明独立表、GET/sync批量填充、human专用PUT、项目删除清理及16项针对性测试；实际diff显示models +93、projects约+134/-1，测试为新增文件，原14项工作区改动保留。前端F1/F2尚未实现。
- 自报16项测试通过；全量命令已尝试，732项中708通过、24项因create_pipe WinError5受限；另排除4个完整模块的回归报告discovered734/running565全绿。主控未重复完整测试，已要求Kimi核实数量差异、排除范围与相关覆盖，不把环境限制当全部通过。
- 按最新项目开发要求派Kimi #134「角色说明后端实现独立复核」，独立读实际代码/测试并做必要验证，只写.tmp/role-description-b1-review/。允许恢复默认响应审计字段为null以表达无记录状态。#133暂不收取，不并行实现F1/F2。
- 正式进度同步；默认派发后结束，用户通知#134完成再取件。未提交推送，后端实现仍待独立复核。


## 2026-10-04 #132设计复核通过与任务标题单编号规范，派#133后端B1

- DeepSeek #132/msg2629为有效结构化complete，独立逐项核对R1设计与实际代码，确认#130的B1/B2及D1-D12全部闭合、无新阻断，准许进入B1/F1/F2实施。N1-N7为非阻断实施细节：F1须补app.js同步调用与测试桩、保存后显式重绘列表、静态面板放在role-details-panel外；空白集合/测试清单、F2过期注释与pi白名单验收也须落实。仅静态复核，未做页面或接口验证。
- Codex据此正式收取#125/#131/#132，workflow_status均completed；#130此前已收取。#131本地结构化交付校验通过并经#132独立复核，但TALK结果msg2628仍为自由文本、MCP结论unknown，不改写原事实。设计验收不等于B1/F1/F2已实现。
- 用户指出近期任务标题有双编号。根因是Codex将被复核任务号放进title开头，服务端按新task.id再次加前缀；如#132标题显示“132-131-…”。用户选择只规范后续，不回写#130–#132历史标题。已在TASK_WORKFLOW明确title只写任务名称、关联编号写content；服务端继续自动加真实编号。
- 已按最新项目development_requirements派DeepSeek #133独立后端B1切片，标题“133-角色说明持久化与接口实现”仅一个真实编号。开发完成即暂停，等用户通知后取件并交Kimi独立代码复核；F1/F2不并行改码。当前原13项M保留，另增TASK_WORKFLOW与进度文档修改；Git自动审批额度故障无恢复证据，本轮未提交推送。

## 2026-10-04 #131设计R1交付，派#132定向复核

- Kimi #131已完成角色说明设计R1修订，正文位于 `.tmp/role-description-0/design.md`；B1将顶部“新建任务”明确改为已确认移除，独立列前端F2；B2改为静态DOM编辑区，避免动态详情重绘销毁textarea；D1-D12含列表首个非空行、GET/sync统一填充、归一化/幂等、项目删除清理、REST/MCP/bridge边界等逐项落地。仅设计，未实现B1/F1/F2。
- 本地 `.tmp/role-description-revision-0/delivery.json` 用 `scripts/talk_workflow.py summary --expect-task-id 131` 可读出complete，校验通过；但#131 TALK结果msg2628发为自由文本，MCP `talk_get_delivery` 结论unknown。这两种证据分开记录，不把本地自报或runner succeeded冒充MCP有效结构化交付，也未收取#131。
- Codex核读R1正文，并依据#130复核要点派DeepSeek #132定向独立复核：核对B1/B2与D1-D12确实关闭、特别检查静态面板在动态容器外的可实现性。按默认协作，派发后待用户通知完成再取件；#125/#131暂不收取。git status仍见原13项修改，无业务改码或服务操作。
- 正式进度文件同步当前状态，未提交/推送；此前Git自动审批工作区额度错误没有恢复证据，本轮不绕过。

## 2026-10-04 #130独立复核收取，派#131修订#125设计

- #125/msg2621为有效结构化complete自报，但原设计稿第4/5节把已确认移除的顶部“新建任务”误列为保持现状/待用户回答。Codex核读正文后依项目分工派DeepSeek #130独立复核，未重复设计或改业务代码。
- #130/msg2627为有效结构化complete；独立核对实际代码与正式记录，确认独立表、专用PUT、REQ2式草稿/请求隔离方向可行；指出两项实施前阻断：顶部入口决策与设计矛盾，动态角色详情replaceChildren在任务轮询重绘时可能丢输入焦点/内容。另列12项非阻断精化，详情见 `.tmp/role-description-review-0/review.md`。复核限于静态检查，未启动服务或真实页面；其沙箱无法运行git status。主控已于2026-10-04收取#130，workflow_status=completed。
- 主控裁决：顶部入口移除列独立前端小切片F2；角色说明编辑区采用静态DOM，避免动态详情重建；REST随既有agents列表可读，MCP talk_list_agents与bridge prompt不新增说明；空白恢复默认、last-write-wins维持；项目删除时新说明表显式清理。已将这些及D1-D12交Kimi #131修订原设计稿；原#125交付消息与delivery.json保留，#125暂不收取，待修订后定向复核。
- 本轮正式文件只更新PROGRESS/PROGRESS_HISTORY，无业务代码或服务改动；原13项工作区改动未覆盖。Git自动审批工作区额度故障无恢复证据，本轮未提交/推送。默认派发后结束，待用户通知#131完成再取件。

## 2026-10-04 新窗口交接汇总（#129收尾后）

- 用户要求先汇总再新开对话，本轮不派新任务、不启动服务或探针。当前#126–#129均已收取，#125设计已交付但正文尚未审；下一窗口不要重复派发设计或重做已关闭的F1–F7。
- 将PROGRESS压缩为恢复快照；为避免丢失原快照的细节，把压缩前全文归档到本文件末尾“2026-10-04压缩前进度快照”。既有完整切片记录继续保留。
- 本轮git status确认13个已修改文件；新增于前次12项的是MODULE_bridges。无业务改码，当前已审代码与正式文档仍未提交。前次自动审批返回工作区额度不足、命令未执行，此错误无恢复证据，本轮不重试或绕过。常规推送授权仍有效，额度/审批恢复后按明确清单收尾。
- 新窗口先读AGENTS、PROJECT_BRIEF与PROGRESS，再按选定事项读取唯一相关模块。恢复指令“继续项目”。

## 2026-10-04 #129复验通过，DSH-DESKTOP-0调查报告收尾

- #129/msg2626有效structured complete，Kimi独立核对实际修订报告、asar 16字节头及定向条目、287/279计数、bridge静态代码和#128交付包，确认F1–F7关闭。主控采纳为后续隔离验证的调查依据，不将报告复验当作桌面适配验收。
- #126/#127/#128/#129于11:58:37/40/44/47 UTC正式收取，结果msg2623–2626，workflow_status均completed；#126原MCPunknown/本地partial、#127 partial保持原状。原报告和复核证据保留，修订报告作为后续引用版本。
- 正式同步MODULE_bridges：当前PATH npm0.1.5-rc.2、桌面0.2.0-rc.2，旧0.1.0-rc.8属于历史受控验证；不把旧测试外推新版。User/Machine未覆盖不能排除进程覆盖，目录并存不直接证明相同有效home；真实桌面home/UI恢复仍未验证。TALK锁不约束外部桌面写入，单owner是使用约束。
- O1缓存/会话目录计数自然增长为非阻塞观察，不作为兼容性依据；后续引用须附快照时点，不读取私人会话复验。S1a隔离无凭证启动验证与S1b真实模型契约均未执行；前者先查副作用及真实home隔离，后者另列范围。现有运行器不切换，本轮不新派任务，#125设计仍待独立复核。
- 主控仅维护正式模块说明和进度，未重复完整调查、未业务改码或启动探针。Git仍受此前工作区额度导致自动审批未完成影响，未获恢复信息，不重试或绕过，记录本地保存，未提交推送。

## 2026-10-04 #128报告补正交付，派Kimi #129定向复验

- #128 succeeded/submitted，msg2625是实际任务号128的有效structured complete，摘要无省略；仅表示报告补正自报完成，不代表桌面适配验收。逐项回应F1–F7，区分已确认/推断/未验证，S1a无凭证隔离探针与S1b真实模型契约分步，均未执行。
- 修订文件为.tmp/dsh-desktop-0/report-revised.md、delivery-revised.json，原#126/#127保留。开发者报告本地validate通过、User/Machine环境为空、既存12项改动不动；本轮主控未重复完整调查或运行探针。
- 派发前读取最新项目开发要求，Kimi最新上报idle；创建顶层general #129“129-定向复验DSH桌面兼容报告补正”，queued/assigned。要求独立核对实际文本与#127证据，逐项F1–F7给关闭状态，特别避免以无User/Machine覆盖推定实际Electron环境，或以DSH_SHELL共存证明唯一注入来源；非阻塞措辞建议与适配实测缺口分开，不重开全量调查。
- #129只写.tmp/dsh-desktop-rereview-0/，不改业务/正式文档/真实环境、不启动探针或模型、不读取私人会话、不Git操作；完成暂停，用户通知后取件。#126–#128暂未收取，#125设计仍待读取及独立复核，现有运行器保持。
- 主控更新进度，Git仍待此前自动审批工作区额度故障解决，本轮不绕过或重试提交，记录本地保存。

## 2026-10-04 #127独立复核partial，派DeepSeek #128补正调查报告

- Kimi #127 succeeded/submitted，msg2624有效partial。独立确认桌面0.2.0-rc.2/npm0.1.5-rc.2、asar/runtime/入口及现有bridge静态调用链；包存在不等于启动或会话兼容通过，未执行真实CLI/模型或桌面UI验证。
- 核心问题F1/F2：#126调查进程DSH_HOME不能当作User/Machine或运行中Electron环境事实；默认目录和文件时间只能辅助推断，桌面实际home与会话恢复仍未证实。TALK claim/runlock只约束自身受管执行，不能保证外部桌面不同时写会话，未发现互斥也不能证明完全不存在。
- 其余修正F3–F7：准确限定被拒命令与执行环境；修正asar pickle头/偏移方法说明和包计数（287总数、279同版本）；隔离无凭证探针S1a与真实模型S1b分步，--dump-config/启动可能写文件；未独立核查缓存schema则删除细节或明确仅开发者观察。绝对路径调用不以PATH注册为前提，npm shim绕过不触发不自动证明桌面必须新增解析器。
- 派发前读取最新项目开发要求并确认DeepSeek空闲，创建顶层general #128“128-补正DSH桌面兼容报告的证据边界与验证分步”，queued/assigned。只新增.tmp/dsh-desktop-0/report-revised.md与delivery-revised.json，逐条回应F1–F7，保留原#126和#127；不改业务代码、正式文档、真实配置，不启停进程、不做隔离探针/真实模型调用或Git操作。完成后暂停，交Kimi聚焦复验。
- #126/#127暂未正式收取，保留各自partial/unknown事实；#125设计仍待读取和独立复核。主控仅维护进度，本轮无业务改码。Git仍受此前自动审批工作区额度故障阻碍，本地记录未提交推送，不重试或绕过。

## 2026-10-04 读取#126 partial调查，派Kimi #127独立复核

- #126 succeeded/submitted，msg2623为自由文本，MCP业务unknown；改用本地talk_workflow summary .tmp/dsh-desktop-0/delivery.json --expect-task-id 126验证，得到有效partial，未完成/限制保持原状，不将runner成功当适配完成。
- 报告核对桌面0.2.0-rc.2打包入口与npm0.1.5-rc.2、现有headless桥、会话目录和默认home；--help/--version等启动探针受执行者沙箱限制未跑，实际桌面查看/续接及内置CLI受管执行均未验证，不切换、不卸载、不改PATH或真实配置。
- 主控将需审慎核对的推理列入复核包：agent自身环境/会话mtime不自动证明Electron有效home；claim/运行锁不自动约束外部桌面session写入；asar含包不证明可运行；npm shim特殊处理不自动证明桌面需新增分支；绝对路径调用未必需要PATH注册；具体命令拒绝不能泛化所有路径/宿主能力不可读。
- 派发前读取最新项目要求，确认Kimi空闲。创建#127“127-独立复核DSH桌面兼容调查与隔离验证方案”，queued/assigned，仅写.tmp/dsh-desktop-review-0/，不改#126原报告或业务文件、不做真实模型/会话操作。#126暂未收取，等待用户通知#127后裁决。
- 为避免重复占用执行者，仅核对#125已succeeded/submitted、msg2621有效complete，尚未读取设计正文或安排其复核，不把状态核对写成验收。旧未提交代码保持，进度记录本地保存，Git仍待此前审批额度故障解决。

## 2026-10-04 登记项目角色配置与选择性自动启动计划

- 用户要求将刚讨论方案登记为后续计划：全局终端接入与项目角色名册分层，在项目角色列表手动从已接入运行器中添加角色、填写名称/说明，设置手动启停与自动启动。支持同运行器多个独立角色，避免把软件安装列表当项目成员列表。
- 自启动范围明确为当前加载项目中已配置且启用自启动的角色服务，不启动全局所有已接入终端；多工作区切换、进程所有权、失败回退和关闭清理留实施合同细化。桌面/CLI不同入口不自动成为两个角色，共享会话仍待实际兼容验证。
- 更新DEVELOPMENT_ROADMAP并关联W1/I1/I2/R1/U2/D1/U1；只登记，不新增派发，不扩#125/#126设计调查范围，不修改业务代码或真实运行配置。记录本地保存，Git仍待此前宿主自动审批额度问题解决。

## 2026-10-04 页面反馈与DSH桌面适配需求，派#125/#126设计调查

- 用户确认项目设置、解除与指定主控正常，提出角色文字可编辑及桌面端适配。关于顶部“新建任务”，主控说明与已删角色“交办任务”共享弹窗，用户明确也移除，任务由主控分配；本次不扩大为删除公共API/MCP/SDK或任务详情子任务入口。
- 角色说明当前按business_role硬编码（lead为统筹等），并非随项目实际主控指定变化。用户要求可保存文本、默认现有文字；按项目+member保存的方案交Kimi #125设计，连同短标签/解释一致性、sync不覆盖、权限/并发/草稿保护等最小合同，不直接改码。顶部移除确认通过Task Hall msg2620补充给#125。
- DSH本机通过快捷方式定位D:/deepseek harness/DeepSeek Harness.exe，文件版本0.2.0-rc.2，内置dsh.cmd存在；PATH仍指向npm0.1.5-rc.2。官方仓库desktop/README声明同DSH_HOME共享sessions/settings/workspaces等产品数据，执行包及desktop profile分离；这是当前文档而非本机共享验证。未读取凭证/私人会话，不调整PATH、不启停进程；进程路径CIM读取拒绝后仅用快捷方式与文件元数据。
- DeepSeek #126只读核查安装版与现有bridge的home/profile/session兼容、单角色单执行入口、桌面内置CLI/ACP/SDK可行性及最小隔离验证方案。Kimi #125同时仅在各自.tmp目录做设计，双方无业务代码写入；后续分别交叉复核，一次一片实施。
- 用户将未来App启动目标改为自动启动已接入终端服务，更新路线图旧不自启方向；工作区范围、失败隔离、已有进程所有权仍需落合同。角色列表应显示项目实际角色，不能把每个可支持运行器或同模型多端自动变成重复角色；WorkBuddy已有有人值守闭环不等于无人值守服务适配完成。
- 工作区仍有#123/#124已审清理六文件及正式文档未提交，HEAD d681269。此前自动审批额度错误未收到恢复信息，本轮不重试/绕过提交；新工作限设计与调查，代码/文档都保留本地。

## 2026-09-23 MANUAL-TASK-CLEANUP-1独立复核通过并收取，Git待审批恢复

- #124/msg2619为有效structured complete，Kimi独立逐行核对基线d681269上的六文件+7/-23，确认仅移除旧黑板隐藏刷新/委派控件及专属引用/样式，保留可见入口、共享函数、刷新finally、子任务与公共后端，三份契约仅更新资源版本，未发现缺陷。
- Kimi实际复跑Node127/127（--test-isolation=none）、Python页面契约7/7、两JS语法与git diff --check通过。Codex读取完整摘要、核对工作区范围，无额外业务修改；不重复全量测试。真实浏览器未测，all-members-list为既有且带空值守卫的旧引用，本片未扩展。
- Codex确认开发/复核收尾，#123/msg2618于14:10:15.331228Z、#124/msg2619于14:10:18.737574Z正式收取，均completed。#122保留failed/unknown，不因续做成功追改。证据.tmp/manual-task-cleanup-resume-1/与.tmp/manual-task-cleanup-review-1/。
- 同步MODULE_webui、验收指南、DEVELOPMENT_ROADMAP及进度，当前缓存版本20260923-manual-task-cleanup-1。用户简要回归可见新建任务、刷新与角色项目设置即可，未新增产品功能，不派新任务。
- 提交/推送仍受此前自动审批工作区额度不足的review failure阻碍，暂无错误已解决的证据，本轮不重复尝试或绕过。所有改动本地保留，HEAD仍d681269；额度/审批恢复后正常提交明确文件清单并推送。不能称此版本已上传GitHub。

## 2026-09-23 恢复双方交叉复核，Kimi重启后领取#124

- #123完成：msg2618有效structured complete，succeeded/submitted；核对继承#122六文件+7/-23且未再次改码，补跑Node127、页面契约7、探针16及语法/diff检查通过。尚未独立验收或正式收取，保留#122失败与旧交付缺失事实。
- 用户确认Kimi恢复额度、要求恢复DeepSeek/Kimi协作。AGENTS结束此前临时分工，新任务按项目开发要求分配与交叉复核；已开发的DeepSeek成果直接交Kimi检查，不为恢复分工重复开发。派发前已读取最新development_requirements。
- 已派顶层general #124“124-独立复核隐藏黑板控件清理与中断恢复成果”，基线d681269，限定只读实际代码、复跑必要测试、核对中断恢复/空DOM/可见入口，不改业务代码或正式文档，不commit/push。证据.tmp/manual-task-cleanup-review-1/。
- 初始Kimi最近上报offline，用户表示重启后，本轮只读确认#124 running/in_progress（updated_at=2026-09-23T10:19:34.816811）；不创建重复任务，不持续轮询。用户通知完成再收取。
- 前次提交#123恢复记录时，自动审批系统因工作区额度不足未能完成审查，git add/commit命令未执行，不能绕过；AGENTS与进度变更留本地，尚未提交推送。此为宿主审批失败，不代表项目代码或Kimi额度有问题。审批恢复后随切片收尾处理。

## 2026-09-23 中断后恢复：#122失败，派#123续做交付

- 用户外出时表示要Ctrl+C DeepSeek，返回后报告此前任务失败并明确要求重新操作。只读确认#122 runner/workflow均failed，finished_at=2026-09-23T05:29:31.707464，msg2617仅“DeepSeek Harness bridge运行失败，错误详情已记录”；没有有效结构化交付，不凭此确认具体失败原因。
- Codex核对现场：HEAD d681269，原六文件仍有+7/-23未提交改动，删除/资源版本差异初查符合#122范围。旧.tmp/manual-task-cleanup-1/有EVIDENCE.md、probe_dom_ids.cjs、baseline/但未见delivery.json；EVIDENCE写complete和有交付包不等于当前实际完整交付，需续做核实。未回滚或代替执行者改码。
- 派发前重新读取项目开发要求；DeepSeek最近实例上报error/current_task_id=null，记录PID15844仍存在，但这不证明bridge已恢复或新任务已领取。已创建#123“123-恢复隐藏黑板控件清理并补齐验证交付”，queued/assigned，基线d681269；派发成功不等同执行成功。
- #123明确复用现有六文件，只修本片遗漏，核实或补跑Node/Python与语法检查，完整交付使用新任务号；新证据放.tmp/manual-task-cleanup-resume-1/，旧证据与#122失败保留。不派Kimi，Codex后续独立检查、文档/Git收尾。用户通知后取件，不持续等待。

## 2026-09-23 #121补正核查收尾，派#122清理已确认残留

- #121/msg2616为合法partial自报：R1/R2/R3调查已补正，未完成项为调查范围外的实际删除、未做真实浏览器及可选保留说明。Codex按只读调查范围验收，保留partial和未测试边界，不强行改写为完整实现。#120/msg2615与#121/msg2616于03:37:44.126206Z、03:37:48.230983Z收取，均workflow completed；#120原错误报告不覆盖。
- Codex独立复核当前web引用、刷新函数、human授权路径、同步SDK参数，并实际读取git show 15874ba -- web/index.html：确认隐藏组在双栏改版时被可见新建/刷新入口替代，不依赖执行者临时脚本来推断历史。当前HEAD3c24017相对fdc6c4b仅进度文档差异，web仍eb45298。
- 正式结论：保留共享创建/公共后端；删除候选仅index.html隐藏blackboard-actions容器及两个按钮、style.css该规则、app.js两个常量/两个绑定/三处disabled同步。核心human根创建七参数与MCP/SDK能力区分成立。附带纠正#121表格：resume-tree允许human或根请求者（_require_tree_manager），列表按身份过滤，不能称“三个human-only端点”；accept-milestone才是明确human-only。此旁支表述不影响清理范围，主控记录裁决，不再为报告措辞循环返工。
- 按用户之前确认无用即清理的授权，主控批准纯前端重复残留清理，未扩大为删除手动创建能力或破坏性API变更。重新读取项目开发要求，按临时分工派DeepSeek顶层general #122“122-清理旧黑板隐藏刷新与委派控件”，queued/assigned，基线3c24017。
- #122范围限制为3个web文件、资源缓存版本与3份Python页面契约期望；保留可见入口/共享函数/后端权限，要求语法、既有Node与页面契约验证。执行者不改正式文档或提交，Codex后续检查。证据.tmp/manual-task-audit-1/与.tmp/manual-task-cleanup-1/。

## 2026-09-23 #120独立检查发现报告漏项，派#121定向补正

- #120结果msg2615为有效结构化complete自报、runner succeeded/workflow submitted；工作区无跟踪文件变动。Codex读取audit.md并独立检查eb45298删除diff、前端DOM/CSS/调用点、公共任务路由、MCP委派、SDK及schedule实现；未重复跑无代码改动的全量测试。
- 认可公共POST /api/tasks、Task Hall、MCP/SDK、共享弹窗仍有必要调用方，不能随角色快捷入口一起删除。角色交办按钮专属绑定确已移除。
- R1：web/index.html:115旧blackboard-actions容器始终带hidden，style.css:67为display:none !important；app.js仍绑定旧刷新/委派按钮并更新disabled。报告把3个源码调用点都写成现网有效入口，没有检查用户可达性，因此“没有可安全清理残留”不能验收。要求核查隐藏组的专属DOM/样式/绑定及可见新入口依赖，输出最小清理候选而非直接删除。
- R2：移除人类图形入口不等于删除授权能力；tasks.py保护human根治理参数，SDK create_task仍支持这些参数。要求区分图形入口、MCP参数面和human REST/SDK授权路径，纠正“只能general、任务树不能启动”的过度断言。R3收紧源码可达/真实使用、CLI/MCP入口、schedule有Hall但无项目归属、主控管理迁移与交办专属残留的表述。
- 派发前重新读取项目开发要求，按用户临时分工创建DeepSeek顶层general #121“121-交办代码用途核查补正：隐藏黑板控件与授权路径”，queued/assigned，基线fdc6c4b。只写.tmp/manual-task-audit-1/audit-revised.md及delivery-revised.json，保留#120历史；不改业务代码，不操作真实权限或启停服务，不派Kimi。
- #120暂未收取；用户通知#121后由Codex继续独立检查。此次是调查报告返工，不是业务代码缺陷修复或删除授权。

## 2026-09-23 临时改为DeepSeek执行、Codex检查，派发代码用途核查#120

- 用户同意先核查交办功能代码取舍，并明确暂时所有执行工作交DeepSeek、Codex检查。临时分工已记录AGENTS；仍读取项目最新development_requirements，保留原项目要求快照，在任务包明确本次用户指令覆盖分工冲突，不修改页面配置。
- 派发前工作区干净，实际基线a021384。向agent:deepseek创建顶层general任务#120“120-手动交办入口移除后的代码用途核查”，返回queued/assigned；未派Kimi或其它任务，不启动持续等待。
- 任务仅调查入口专属、仍有调用的共享前端、MCP/CLI/SDK依赖的公共任务后端及残留，给出有源码行号支持的保留/可删/待决策表；仅可写.tmp/manual-task-audit-1/audit.md与delivery.json。禁止删除代码、改变权限/真实任务或启停服务，完成暂停。
- 用户通知完成后Codex独立检查实际代码与报告，再确定是否存在值得实施的清理切片；数据/外部接口兼容影响另行确认。

## 2026-09-23 ROLE-SETTINGS-1人工验收通过并正式收取

- 用户明确反馈“可以，验证通过”，确认eb45298页面整理版本验收通过。覆盖结论按用户本次整体反馈记录，不补称每项键盘、窄屏尺寸或竞态场景均单独验证；Codex本轮只维护收尾记录，无新代码改动或派发。
- TALK服务已恢复。先只读核对结果仍为118/msg2613、119/msg2614且未收取，再分别正式收取成功；两项workflow_status均为completed，收取时间分别为2026-09-23T02:36:52.979196Z与02:36:56.264582Z。保留118自由文本unknown/本地有效包complete与119结构化complete的原证据差异。
- 同步当前进度、验收说明及模块验收状态。当前切片结束；Kimi新任务仍暂停，后端/共享任务创建代码取舍保持独立待办，不自动开启新片。

## 2026-09-23 ROLE-SETTINGS-1由Codex直接完成余项，待页面验收

- 用户因Kimi额度未恢复，明确要求本次不派任务，由Codex直接处理。未给Kimi、DeepSeek或子Agent派新任务；#118/#119既有开发/独立复核证据保留，不把Codex自测写成新的独立复核。
- 修正#119 F1：human已指定主控时，候选框和指定按钮保持可见且禁用；失效指定仍占用唯一主控位并可解除。指定成功焦点从禁用按钮移到解除按钮，解除后回候选框；保存中不提前移动焦点、用户切走不抢焦，直接覆盖保护不变。
- 本轮实际Node127/127、Python页面契约7/7通过；已有用例更新并加强禁用处理器不能覆盖、解除后恢复可选断言。未复跑后端全量，未操作真实浏览器；#119既有21项探针仅为修正前证据。Node使用--test-isolation=none。日志.tmp/role-settings-1/codex-node-20260923.log。
- 整片合入#118项目设置独立首项/角色详情精简与专属交办入口移除；保留共享任务创建系统和所有后端权限。同步MODULE_webui、USER_MANUAL与CONTROLLER_ASSIGNMENT_ACCEPTANCE；资源统一20260923-role-settings-1。修改文件为web/app.js、index.html、workspace.js、workspace.css，7份既有测试与新增workspace_role_settings.test.cjs，以及上述3份说明和2份进度。
- 本轮只读MCP检查#118/#119均连接拒绝（WinError10061），未能正式收取；历史结果分别msg2613/msg2614，保留118服务端unknown/本地包complete差异。服务恢复后补收取，不启动新任务。页面代码完成提交推送后交用户验收；不重启共享服务、不更改真实主控/凭证。

## 2026-09-21 ROLE-SETTINGS-1独立复核完成，因Kimi额度暂停

- #118由Kimi交付项目设置独立页、候选选择器和角色详情交办快捷入口移除，基线485bc94；msg2613含引言使MCP结论unknown，本地development.json实际任务号118校验complete。后端/API/MCP及共享任务创建能力未改。
- #119由DeepSeek独立复核，msg2614结构化交付complete，运行succeeded、任务submitted；独立检查实际代码、测试改动和真实workspace.js调用链，无阻塞代码缺陷。Node127/127（--test-isolation=none，未证明逐文件进程隔离）、页面契约7/7、独立整文件探针21/21通过。旧保存归属、迟到响应、版本和错误分支覆盖未削弱；未重跑后端88或全量测试，未操作真实浏览器。
- F1展示差异待调整：已有主控时当前隐藏候选整行并提示先解除，原要求为可见但置灰。主控按原要求记录待修，不把复核通过等同最终页面验收。恢复后修正并定向复核；MODULE_webui、USER_MANUAL中旧入口/展示说明随后同步。
- 其他非阻塞限制：开发者logs目录不存在，复核已实际复跑并留证；部分焦点旧测试用设置上下文桩，新增整文件测试与独立探针补充真实链路；角色列表点击后焦点丢失为既有行为，本片不扩展。
- 用户明确Kimi额度不足，暂不再给Kimi派发。本轮无新任务、不转派其他Agent；#118/#119未正式收取，前端与测试改动留工作区待恢复，不作为已验收版本提交。本次仅记录进度。
- 证据：.tmp/role-settings-1/development.json、review.json、review-notes.md、probe-role-settings-119.cjs。恢复后先处理候选置灰，再补正式说明、收取、提交推送与人工验收；后端交办相关代码保留/删除仍为已登记的独立后续事项。

## 2026-09-20 页面反馈获准开发，登记交办代码后续取舍

- 用户确认已给Kimi充值，要求将已讨论页面反馈分配执行；此前暂不派发约束解除。范围：角色列表首项项目设置，项目开发要求/项目主控集中独立显示，具体角色页缩短；移除角色详情交办任务入口。
- 用户明确相关后端代码后续确认保留或删除。路线图新增独立待办，先核查角色入口专属、共享页面、MCP/CLI公共任务能力的依赖；确定无用途后再清理，不因删快捷入口直接删除主控派发所需的任务API。当前片不清后端、不改权限。

## 2026-09-20 响应式补验与交办入口说明

- 用户补充实测：窗口化浏览器并缩窄后比例正常，记录为该范围响应式人工验收通过，不推断全部尺寸/键盘/并发时序覆盖。
- 澄清角色页“交办任务”用于在TALK页面手动创建任务并预选当前角色。用户认为当前使用方式缺少场景，保留既定移除该角色快捷入口的待办；不扩大为删除任务系统/API。
- 延续暂不派发要求，仅维护文档，未修改页面代码、未创建任务。

## 2026-09-20 C1b-S2基本验收与页面整理建议（暂不派发）

- 用户对5ae15b7页面版本反馈“基本确认通过”，未声明所有高级时序/账号/窄屏步骤逐项覆盖；不得记录为全范围人工验收。
- 用户建议项目开发要求和项目主控独立一页，入口放角色列表第一位，以缩短角色详情。拟采用角色标签内的“项目设置”首项，点击后右侧显示项目级两块内容，具体角色仍展示自身职责/参与任务与主控标记。此处为待实施整理方案，没有改代码。
- 核对workspace.js角色详情“交办任务”确为可用快捷入口：调用setTaskCreateOpen(true)并预选role.member_id，并非无效按钮。按当前主控派发的使用方式，建议移除此角色详情入口，保留任务系统和API；不把删除按钮扩大为权限变更。
- “窗口拉伸”是验收指引中手动缩小浏览器窗口检查响应式，不是TALK内功能。已将指南改为更明确的窗口还原/拖动边缘说明，窄屏效果仍未人工确认。
- 用户明确Kimi额度不足、暂时不用分配任务；本轮仅记录，未派发、未转交其它Agent、未修改页面代码。

## 2026-09-20 C1b-S2角色页主控指定/解除收尾（#112–#117，待人工验收）

- 基线b634f234312548e9ed698d5784786ba1adef2632。Kimi #112开发、DeepSeek #113核心复核通过；Codex要求#114补齐成功回焦/迟到重绘，#115独立确认后又发现A→B→A旧PATCH提前清理新saving与切角色抢焦，#116以独立saveToken与角色绑定焦点修正，#117静态走查无返工但解释器被拒，partial如实保留。
- Codex在当前环境仅补齐验证缺口，未重复完整代码审查/未改业务：controller33、Node全量117、Python页面契约7、r116探针34、旧交互64/接线44、前后端契约6全部通过。旧r114探针exit1、72/73，唯一失败精确钉旧-focus串，现版本-owner，所有行为断言通过；不是73/73。补跑日志与verification.json在.tmp/c1b-s2/codex-verify/。#112服务器因引言unknown，本地包实际任务号校验有效；不改原报告。
- 页面项目级主控面板+列表/详情标记，以member_id消歧；human指定/解除、其他角色置灰、agent只读，失效指定保留原因与解除入口。专用PATCH+安全版本门禁、409重读不自动写、请求上下文隔离与保存所有权，不新增定时器、不改REQ2草稿/ROLE1耗时或任务权限。指定长期有效，无续租/ACK；后端不改。
- 资源四处20260919-c1b-s2-owner；指定成功到可见解除入口，解除成功到tabindex=-1状态行；离开角色页迟到响应不重绘其它列表，旧请求不得清理新saving，切角色不跨角色回焦。
- 已知边界：点击空白body极短窗口可能回焦；切角色再切回按当前同角色语义回焦；A→B→A且不再保存时服务器旧请求可能晚于重读取落库，需刷新。S1候选/CAS窗口保持披露，不扩范围。真实浏览器/窄屏与实际缓存效果未测，自动化不是人工验收。未改真实指定、启停共享服务或新增凭证。
- 正式收取2026-09-20 UTC：112/msg2607于01:42:08.062855；113/msg2608于01:42:11.152997；114/msg2609于01:42:14.750142；115/msg2610于01:42:18.223107；116/msg2611于01:42:21.656369；117/msg2612于01:42:24.757578。workflow completed不改写117 partial。
- 文档同步MODULE_webui/PROJECT_INTEGRATION/简报/路线/进度，正式验收指南docs/guides/CONTROLLER_ASSIGNMENT_ACCEPTANCE.md。必要diff检查后统一提交推送，暂停后续切片，等待用户验收。

## 2026-09-19 C1b-S1长期主控指定后端收尾（#110/#111）

- 基线c1d3d06，HEAD d10c73a期间仅文档提交。#110开发五个业务/测试文件，#111独立代码复核通过，Codex接受本片并发候选窗口限制，正式收取110/msg2605于13:13:42.084732Z、111/msg2606于13:13:45.507280Z。
- 项目保存controller_member_id与独立controller_assignment_version；旧库幂等增列null/0。human专用PATCH controller-assignment指定/解除，严格版本范围、单条UPDATE CAS、同值不写、陈旧/已占用/耗尽409、候选非法400；禁止普通项目入口旁路。sync/禁用/缺失/重启不自动清空，读取报告有效性，不改业务角色/决策分级。
- MCP复用一次项目GET输出controller_assignment，旧服务unsupported/无项目null，仍9工具；C1a/开发要求/既有任务权限不变。没有页面、会话绑定、ACK、租约、自动派发或自动转审。
- #111独立新增44、定向54、spawn模块169、未筛选全量716项全部通过（包含重叠不相加），补齐#110沙箱24项限制；开发报告引用44项日志缺失由独立复跑替代。#111服务器因引言/JSON围栏为unknown，本地review.json经实际任务号111校验complete，保留区别。
- 竞态探针：候选检查与CAS之间并发移出名册/禁用，可能200保存，读取立即报告无效；这不扩大权限或破坏唯一性，Codex本片接受已披露限制，不声称提交时原子保证。未来可事务加固，S2须显示无效原因并可解除。并发仅单进程多线程SQLite WAL，跨进程未验证。
- 运行中断：原110于16:03:07领取，16:05:40最后心跳、16:07:40任务租约到期，业务文件16:05–16:06修改，空regress1.txt/旧测试库journal与日志停在16:07附近。API连接拒绝、无DSH进程，旧页面状态不是持续模型执行。uvicorn父1936/子18836仍在，用户Ctrl+C无效；Codex核验身份后仅强停两者并确认释放8000。用户重启TALK后API恢复，再重启DeepSeek后20:30:43重新领取原110、20:31:13心跳恢复。未重复派发。重载是怀疑方向，未有直接栈证据确定根因；不用--reload仅为规避措施。
- 最终测试证据来自恢复后隔离库；不宣称真实库完整性已验收或用户重启没有加载未提交代码。当前MCP需重载新实现才能在线确认；主控未重复全量测试或改真实主控配置。API合同同步PROJECT_INTEGRATION，完整本地证据.tmp/c1b-s1/。S1数据/协议片收尾后暂停，下一片S2页面由Kimi开发、DeepSeek复核，页面效果交用户验收。

## 2026-09-19 自动转审后续需求登记

- 用户要求将前面讨论的自动化完整登记、未来择期开发。已在DEVELOPMENT_ROADMAP新增独立待办：默认检查角色、固定检查要求、开发派发时验收标准、实际交付/代码差异/测试证据自动组包；检查者独立判断，异常与分歧返回主控，审查不替代人工验收。
- 记录后续需设计的触发状态、幂等去重、授权/收取、禁止自审、共享目录暂停及返工边界；这些为实施前核对项，不虚构已实现或已授权自动派发。
- 仅文档登记，不排期、不创建自动化、不改变当前#110开发或人工转审流程。

## 2026-09-19 用户确认长期项目主控指定，替代会话租约设计

- 用户明确三项：页面唯一指定主控、供Agent读取遵守；现有任务权限不加“仅主控派发”拦截；指定长期保存直到人工解除/更换，不设期限、不续租。不能将旧合同中的ACK/租约/自动过期当本次需求。
- 角色按独立member_id识别，支持将来同项目多个Kimi/DeepSeek成员，不以模型名硬编码。用户当前Codex桌面终端为主控的使用方式不扩大为模型能力断言。
- 当前切片分为S1后端/API/MCP读取，S2角色页唯一指定/解除及置灰；旧设计归档加替代声明，项目简报/集成合同/路线/进度同步。无真实配置和服务变更。
- 自动转审另列后续：固定检查要求+原任务验收标准+交付与实际差异；有分歧回到主控。当前仍人工转交，不因将来自动化改变现在任务权限。多角色创建入口/启动接入也单独排片。

## 2026-09-19 C1b-0主控会话合同设计收尾（#104–#109）

- 基线 `c20640b6c57f4b73d37e4d3c5dcbfcd9819272d5`。DeepSeek #104设计、Kimi #105发现四项问题、DeepSeek #106修订、Kimi #107定位残留R1、DeepSeek #108按Codex方案a定向修正、Kimi #109独立复核通过。Codex确认R1/R1-a/R1-b关闭，不以流程完成改写历史blocked。
- 设计明确ACK携带模式版本并原子比较、绑定令牌与epoch幂等、首次响应丢失恢复、持有者释放与human强制释放分离；缺必填字段统一422，请求完整后按既定层级鉴权/检查冲突；bind带token时epoch必填。凭证只在仓库外私有位置保存，epoch持久化防旧归属复活，state_version仅观测。
- #105独立31项C1a测试与11项隔离身份探针通过；探针为进程内模拟，H为短路桩。#107独立文本检查39项通过但仍发现语义冲突，说明关键词检查不足。#109逐段核对v2→v3差异，独立模型脚本12项检查（28场景）通过；旧脚本31/39，其8项失配确认是陈旧措辞/计数或原缺陷断言，无有效需求误删。主控未重复全量代码审查或测试。
- 已复核v3正文归档 `docs/spec/C1B_CONTROLLER_CONTRACT_REVIEWED.md`，保留原文并附主控状态说明；原稿SHA-256为 `f44b82d39b4edf3a696c1e391ff3d96d829706c3f144f8ab0a6a45b1e83e66be`。本地完整证据 `.tmp/c1b-0/`。两项非阻塞观察留待实施：矩阵标签措辞、renew/release部分错误格补齐测试，不为此重复设计返工。
- 正式收取（2026-09-19 UTC）：104/msg2599于06:56:38.325143；105/msg2600于06:56:40.841146；106/msg2601于06:56:44.315166；107/msg2602于06:56:46.784387；108/msg2603于06:56:50.370392；109/msg2604于06:56:52.907784。#105服务端因说明/JSON围栏判unknown，本地review.json实际号校验有效、结论blocked，保留差异。
- D1/D2/D3仍待用户批准：推荐名册内agent空闲/过期绑定、human专用强制释放；既有任务入口不加新门禁；持久化绑定并按租约过期。D1摘要须澄清human不受名册限制不等于绕过活跃归属/版本检查。政策确认后再排C1b-1，不擅自实施。
- 限制：只有设计，没有新端点/表/MCP工具或在线变更；不证明真实宿主会话稳定性、跨进程并发、模型ACK或副作用隔离，同凭证旧会话仍可调用既有写工具。未启停共享服务。主控归档及进度diff检查通过后提交/推送，暂停等待策略确认。

## 2026-09-19 C1a项目主控模式配置基础（#100–#103）

- 基线 `a23b6443f5d1fae3db01292bfc921381b27c87aa`，分支codex/terminal-return-codex；DeepSeek #100开发，Kimi #101复核partial，DeepSeek #102修正，Kimi #103独立复验通过，Codex确认收尾。
- Project新增controller_mode/controller_mode_version默认passive/0；老库幂等增列，保留数据。human专用PATCH controller-mode须mode和expected_version，数据库条件UPDATE实现CAS，实际变化才+1，同值合法不增，陈旧版本即使同值也409。普通注册/PATCH/sync不旁路修改。
- MCP talk_list_agents复用一次项目GET返回controller_mode摘要，与开发要求同源；requested为配置意向，effective_mode恒null/not_bound。非项目null、旧后端unsupported，工具仍9个；active不自动执行/等待/授权/唤回，没有会话所有权或前端。
- #101独立178项通过但探针发现expected_version=2**63导致SQLite绑定OverflowError/HTTP500。#102加有符号64位上界并补2测试；#103复验31+44项及原探针9/开发新探针4/独立新探针4全部通过，真实422及拒绝后库不变，上界正常409、合法CAS200、陈旧409，原29项保留完整。未把测试计数重复叠加为全量运行，未改变原partial结论。
- 正式收取（2026-09-19 UTC）：100/msg2595于01:23:15.478475，101/msg2596于01:23:18.454528，102/msg2597于01:23:21.093970，103/msg2598于01:23:23.993394；流程completed不改写#101历史验收未通过。
- 变更：server/models.py、server/db.py、server/routes/projects.py、bridges/talk_task_tools.py、新增tests/test_project_controller_mode.py；主控同步进度/历史/简报/路线/项目集成/终端指南。原交付与复验保留.tmp/c1a/；主控未重复执行完整代码审查或全量测试。
- 限制：仅隔离测试，未启停共享服务/MCP、未改真实库/模式；并发为单进程多线程HTTP+SQLite WAL，跨进程未验证。异常后端负版本透传、实际存储版本耗尽处理未扩大修复；不宣称生效/自动执行。下一片C1b身份/生效合同、C2按钮待用户指示。


## 2026-09-18 ROLE-1人工验收通过

- 用户在代码 `ff656b7` 推送后明确回复“可以，验收通过”，确认本片角色说明与参与任务耗时页面验收完成。与#99独立复核证据分开记录；未推断逐个窄屏尺寸或其它早期里程碑已覆盖。
- 同步当前进度、模块、路线、简报及验收指南，解除本片人工验收门禁；保留原型键显示加固等非阻塞待办。仅文档收尾，没有新代码或任务派发。


## 2026-09-18 ROLE-1角色说明与参与任务耗时（#98/#99）

- 基线 `0fd58aad2903adc3303a3fc10e8ba5a6fae19d04`，Kimi #98开发、DeepSeek #99独立复核通过。Codex确认无阻塞后正式收取：98/msg2593于14:07:23.831854Z、99/msg2594于14:07:26.613949Z（2026-09-18）。
- 显示映射统一：lead保持统筹与原说明；dev/developer/reviewer显示执行工作，说明为执行分配工作、提交结果、交叉验证其他角色成果。tester/ui不变，不改business_role/decision_tier/权限。
- 参与任务表替换“承担工作”为“执行耗时”，参与集合、发起/委派关系、筛选和查看操作不变；task_kind/general及其它页面类型展示保留。复用workspaceTaskDuration与唯一计时器，列表/角色表双处逐秒更新textContent，不增加网络或重建表，claimed_at至finished_at不计排队/待收取。
- DeepSeek独立复跑新增Node6+既有78=84项、Python页面契约5项通过，另有9项真实函数/DOM探针，补强双处渲染、生命周期/登出清理、REQ-2草稿焦点不受影响的证据。主控做git diff --check与收尾，未重复全量测试。
- 低级别非阻塞发现：自由文本角色为constructor/toString/valueOf/__proto__等原型键时对象字面量查找命中原型，可能显示异常文案；label为旧问题，description路径同类风险；现有角色不受影响，仅展示，无权限变化。接受本片并登记未来加固，不声称问题不存在。
- 在线状态：98一度queued/assigned未领取，用户重启执行bridge后自动领取完成，无重复派发。用户重启MCP后list_agents新字段与工具说明已加载；按最新要求派99，创建返回及get_task均确认真实存储正文包含快照（含DeepSeek“其他未提及内容”），没有额外测试任务。旧任务不追改在线实验未做，保留隔离测试证据。
- 变更文件：web/workspace.js、web/index.html、tests/workspace_role_duration.test.cjs、tests/test_task_web_ui.py、tests/test_requirements_web_ui.py；主控同步当前/历史进度、模块、路线、简报及验收指南。资源版本20260918-role-1，交付/复核/探针在 `.tmp/role-1/`。
- 限制：未做真实浏览器/HTTP端到端或窄屏视觉；终态最多约5秒轮询后反映，沿用既有口径；超99小时窄列观感留用户验收。本片收尾后暂停，用户Ctrl+F5刷新检查说明/列/走秒与固定值。


## 2026-09-18 独立任务类型暂缓决策

- 用户理解当前独立派发统一登记general，并明确选择继续沿用，未来可能需要按检查/执行/返工实际工作分类，仅先记录。
- 已同步TASK_WORKFLOW现行用法、DEVELOPMENT_ROADMAP暂缓项及当前进度。现有非general类型涉及子任务合同与流程门禁，将来需评估分类/流程解耦或顶层支持，不能当作纯显示改名。当前不改派发代码、真实任务或历史类型；此前角色说明/耗时列建议没有因此自动启动。


## 2026-09-18 REQ-2用户验收与角色页建议

- 用户明确“验收通过”，同时跳过验收指南第5项（agent只读及桌面/窄屏布局检查）和第6项（更新后MCP读取要求及新委派快照的在线验证）。接受该人工验收范围；两项继续标记未人工验证，已有权限/快照自动化与独立复核证据保留，不推断当前MCP已加载新实现。
- 用户建议Codex保留“统筹任务”，Kimi与DeepSeek统一“执行工作”，说明包含提交成果及交叉验证；另询问参与任务表“承担工作”列的类型/意义以及换成耗时的可行性。本轮只核对现有显示逻辑并提出意见，未实施或派发。
- 源码确认该列混合参与关系与任务类别：目标角色可为统筹与汇总或普通任务/执行工作/检查/测试/返工；发起角色显示委派与跟进。当前独立顶层派发使用general，人工审查任务也可能显示普通任务，因此不能作为真实工作职责的可靠分类。建议替换执行耗时列，沿用claimed_at到finished_at口径，任务关系仍可在详情查看。


## 2026-09-18 REQ-2角色页项目开发要求编辑区（#94–#97）

- 基线 `cdc8416c77d919cb14acc17b6bfb98bcd4732a64`，分支 `codex/terminal-return-codex`。Kimi #94开发，DeepSeek #95独立复核partial，Kimi #96返工，DeepSeek #97独立复审通过；Codex据实际代码独立复核证据验收，不把最初测试通过等同功能无缺陷。
- 编辑区为项目级、仅角色页出现；human可编辑保存/清空、agent只读；保存仅PATCH要求字段且核实响应同项目/字段存在/值一致。项目账号隔离内存草稿、迟到响应/保存中编辑防护、Unicode20000码点、旧后端缺字段禁止保存，不自动保存placeholder。退出登录/刷新会失去未保存内存草稿。
- #95发现R1群聊路径面板漏隐藏、R2 JS trim/Python strip特殊空白不一致导致真实保存误报失败；R3职责提示文案建议。#96将可见性调用移入app.js统一详情刷新点、判空对齐Python集合、调整文案；资源版本 `20260918-req2-rework`。
- #97独立复跑Node7文件78/78、Python49+95通过（页面5项包含在49中）。隔离副本还原旧调用图时nav测试4过2失败、修复控制组6过；两失败实际是群聊及群聊返回角色场景，已在返工笔记追加更正。全Unicode判空集合29码点与Python零分歧，25例真实隔离PATCH原4例误报清零；审查更新后的探针未掩盖问题。主控仅做范围与收尾检查，不重复全量测试。
- 正式收取：94/msg2589于11:56:32.654359Z、95/msg2590于11:56:35.499319Z、96/msg2591于11:56:39.210416Z、97/msg2592于11:56:43.120937Z，均为2026-09-18。#95保留partial结论，completed只是流程收取，不改写历史验收事实。
- 代码/测试：web/index.html、web/workspace.js、web/workspace.css、web/app.js、tests/test_task_web_ui.py、新增tests/test_requirements_web_ui.py、tests/workspace_requirements_ui.test.cjs、tests/workspace_requirements_nav.test.cjs。证据在 `.tmp/req-2/`；正式同步AGENTS、TASK_WORKFLOW、模块/接口/简报/路线/终端指南、当前/历史进度及新增人工验收指南。
- 职责分工按已确认需求改为角色页项目开发要求单一维护；AGENTS保留角色分级、规范、审查与收尾，并规定派发前读取。真实项目要求未写入，字段不可读/未配置时不能默认为已配置，有会话明确分工则按该分工，否则请用户配置。
- 限制：没有真实浏览器验证，未重启共享服务/MCP、未操作真实库；UI/部署生效待用户人工验收。直接REST/schedule/pi TS不自动快照属既定范围。孤立代理码点经转义JSON使后端SQLite编码500为既有待办，本片未修；Node --test受EPERM时逐文件运行同断言。验收前不开始下一片。


## 2026-09-18 REQ-1 项目级开发要求后端与主控工具（#92/#93）

- Git收尾：本地提交成功；向 `origin` 的 `codex/terminal-return-codex` 推送被自动审批拒绝，未执行。拒绝理由为远程归属及推送授权证据未获认可，目标 `https://github.com/bobo506/TALK.git`；随后用户明确授权本次及今后该项目推送，按新授权重试成功：`ada3b71..b32ef7c` 已推送至 `codex/terminal-return-codex`。持续授权同步AGENTS.md。

- 用户于2026-09-17授权继续，按后端/工具与前端拆片；DeepSeek #92开发后暂停，Kimi #93只读独立审查，Codex据审查与测试证据验收。基线 `ada3b71bf2ae8e2fd8f12fbf7a39fa95b9be4851`，分支 `codex/terminal-return-codex`。
- Project新增 `development_requirements` 最新纯文本（20000字符、默认NULL、保留换行）；老库通过幂等ALTER增列保留数据。项目API沿用human写、认证成员读；省略不改、空白/null清空；CLI只在显式字段时透传，SDK没有项目helper未凭空扩展。
- `talk_list_agents` 顶层实时返回要求一次；`talk_delegate_task` 将非空要求追加到原任务正文，读取失败不派发、空要求保留旧行为，旧任务不追改；执行bridge从claim存储正文取快照。无新MCP工具/版本历史/前端变更。
- Kimi独立检查实际代码并审查测试runner，在Windows Python3.12.1环境分批覆盖638项（162+319+67+90）全部通过，其中新增21项已包含在162项内；补齐DeepSeek环境24项WinError5限制。主控未重复全量运行，执行git diff --check完成收尾检查。
- 开发者把含失败的319/638组标pass、基线4模块169项与复核67项计数不一致，保留原报告作审计，不将其视为全量通过证据；以独立复核复跑为准。#92 msg2587因说明/JSON围栏被MCP识别unknown，本地development.json经summary --expect-task-id 92通过；#93 msg2588为合法结构化交付。
- 正式收取：#92于2026-09-18T01:52:18.241690、#93于01:52:20.924785，均completed。交付/接口/复核证据位于 `.tmp/req-1/development.json`、`interface.md`、`review.json`、`review-notes.md`。
- 代码变更：`server/models.py`、`server/db.py`、`server/routes/projects.py`、`bridges/talk_task_tools.py`、`cli/talk.py`、`tests/test_project_development_requirements.py`；正式同步进度/历史/简报/路线/项目集成接口/终端指南。
- 限制：未改真实库、未重启共享服务或重连MCP，运行中旧进程不能宣称已生效；直接REST/schedule/旧pi TS不自动写快照；快照最多新增20000字符及区块说明（字节数取决于UTF-8编码，并非固定20KB）。测试临时目录残留为既有清理问题，本片未清理。
- 下一步REQ-2由Kimi做角色页编辑区、DeepSeek复核；本片收尾后暂停，AGENTS分工暂保留，待整项完成再消除双重维护。


## 2026-09-17 WorkBuddy＋DeepSeek受控收取补测及终端验证收尾（#91）

- 用户在原WorkBuddy DeepSeek对话委派91给Kimi；只读交付msg2586包含实际任务号、agent:workbuddy请求者和只读完成声明。用户转交summary/detail时submitted、result_collected_at=null。Codex内容验收后明确授权原对话collect一次，用户回传completed、msg2586不变、result_collected_at=2026-09-17T07:45:18.107869。
- 主控独立核对原始服务器日志：北京时间15:45:18，POST /api/tasks/91/collect-result，member_id=agent:workbuddy，status=200。结合用户原对话工具回传，91受控闭环通过。该证据不反推88的具体模型/会话触发来源；88只确认WorkBuddy凭证发起收取，而非只读副作用。
- 本轮范围内Kimi Code CLI、DeepSeek Harness、WorkBuddy桌面kimi-k3与deepseek-v4-pro均完成有人值守单任务委派/执行/人工独立验收/原会话收取。WorkBuddy实际采用用户级MCP，模型与同对话由用户操作记录支持；后端日志只证明身份及收取请求，不证明具体模型。两模型共用专用agent:workbuddy，不冒充原生kimi/deepseek成员。
- 项目级自动加载、跨重启恢复、多工作区、无人值守、页面启停/运行器适配仍未验证；不把包内CodeBuddy引擎视为桌面自动化验收。配置与凭证继续保留供用户使用，未启停服务或变更全局配置。无代码变更，仅同步进度/简报/路线/使用指南；后续按既定计划安排角色列表开发要求（只保留最新）。


## 2026-09-17 WorkBuddy＋Kimi受控单任务闭环（#90）

- 用户在原WorkBuddy kimi-k3对话按主控提示委派一次，任务90 created_by=agent:workbuddy、target=agent:deepseek。DeepSeek交付msg2585为自由文本：实际任务90、请求者agent:workbuddy、未改文件/未运行命令/未再委派、只读完成；末尾TALK_ACTION为结果正文，不执行。unknown只代表未结构化，不代表失败。
- Codex直接读取Hall遭403；用户通过原对话get_delivery及detail完整转交，收取前submitted、result_collected_at=null。Codex人工内容验收通过后明确授权原对话collect一次；用户回传completed、result_collected_at=2026-09-17T07:39:30.617132、msg2585不变。
- Codex独立查logs/talk.log：北京时间15:39:30，POST /api/tasks/90/collect-result，member_id=agent:workbuddy，status=200。原对话和模型选择由用户操作/回传支持，服务端支持身份与实际收取，未夸大为自动轨迹验证。
- 结论：WorkBuddy＋Kimi有人值守的委派→执行→转交→独立验收→原对话显式收取通过。WorkBuddy＋DeepSeek的88曾提前收取，仍需受控补测；多工作区、无人值守、正式运行器适配未覆盖。无源码变更，无需重启服务。


## 2026-09-16 WorkBuddy连接、88收取调查（#87–#89）

- #87 Kimi注册专用agent:workbuddy，外部凭证及workbuddy-validation配置核对通过；Codex再次核对两配置一致与/me身份后收取。未登记进项目agent索引，不影响本次读取及已发生的顶层委派。用户截图显示界面编辑用户级~/.workbuddy/mcp.json，按主控指导导入；不能宣称项目级加载已通过。用户回传kimi-k3与deepseek-v4-pro的list_agents成功结果。
- WorkBuddy DeepSeek对话创建#88，created_by=agent:workbuddy、target=agent:kimi，结果msg2580为135字符自由文本（任务号/请求者/只读完成）。人工验收内容满足连通性要求，不把unknown结构化结论当失败。Codex读Hall403，由用户从原对话转交正文。发现completed和收取时间早于预期，未让用户重复collect。
- #89 DeepSeek只读调查，预检因任务号疑问请求澄清；Codex明确89后状态clarification_answered，22:49:00启动预检子进程，最终正常交付。没有发现WorkBuddy占用导致不领取；不把预检中尚未claim误判为答复无效。
- 原始logs/talk.log证明：北京时间22:28:35，member_id=agent:workbuddy，POST /api/tasks/88/collect-result，status=200；22:28:37，human:bobo GET /api/messages 403。Codex亲自抽查这两条和collect_result源码，确认收取发生在自身失败读取之前。只读接口代码无收取写入，明确收取接口写result_collected_at；#89已收取。
- 归因边界：足以确认WorkBuddy凭证发起显式收取HTTP请求，排除本次Codex读取造成收取；请求序列吻合MCP collect_result。未读取WorkBuddy具体会话轨迹，不能确认模型还是客户端自动化，也不能确认同一对话按批准执行。当前HEAD与运行中MCP代码版本未交叉验证。无需继续泛查或立即改代码，后续受控补测保留真实工具轨迹。
- 证据：.tmp/l2-workbuddy/task88-investigation/report.json及脱敏证据；不复制私人对话/凭证入库。调查未改88、未新建复现任务、未实施修复。当前仍有Kimi委派收取及DeepSeek受控收取验证未完成；正式运行器适配与无人值守不在本次结论内。


## 2026-09-16 WorkBuddy接入准备调查与独立复核（#85–#86）

- 基线e4adf2a。DeepSeek调查、Kimi独立复核，均为partial，主控已收取调研成果，未运行桌面连接/模型/委派收取。确认桌面WorkBuddy5.5.6与包内CodeBuddy Code2.137.1；包内headless/ACP入口不能代替桌面验收。配置中kimi-k3/deepseek-v4-pro不等于账号或工具调用可用。
- 采纳复核修正：项目级隔离配置优先，不要求用户选择另一产品，不预设必须重启；官方项目级.workbuddy/mcp.json与引擎.mcp.json存在差异，实际通过桌面配置入口及状态灯判定。直接env模板参数与现有MCP入口匹配，但“无需改代码”仅为配置方案，未经真实连接实测。仓库外密钥文件方案仍有启动器复用与文件访问待验证项。
- 复核查无WorkBuddy专用成员，下一步准备agent:workbuddy及项目权限和独立凭证，不复用现有kimi/deepseek身份。用户按最短GUI步骤完成连接与两模型各自验证；未授权本轮修改全局配置/启停应用。模型委派及收取须分阶段经主控验收，不自动一次全跑。
- #86原报告task_id误写talk-delivery-1，MCP及本地expect-task-id86均拒绝。Codex保留原件，另存review-normalized-by-codex.json仅改任务号，validate通过；review-normalization-note.json记录原哈希和消息2578。收取不改写服务器invalid事实，不冒充执行者已正确交付。
- 证据均在.tmp/l2-workbuddy/：discovery.json、capability-matrix.md、isolation-plan.md、无密钥模板、review.json、review-notes.md及主控整理副本。本轮不改代码，不重跑已有无关测试；后续真实连接待凭证与用户操作。


## 2026-09-16 DSH真实模型单任务主控闭环（#80–#84）

- 基线1bf186b。用户提供本人TALK凭证，Codex仅保存到仓库外约定路径，不入版本库。#80身份/配置通过，但执行宿主CreatePipe被拒，未发起模型；#81切换到Kimi已验证可运行环境作为操作员，受测模型仍是DSH deepseek-v4-flash（deepseek-official）。保持read-only+ask、默认拒绝权限、13项工具禁用，无权限询问。
- #81原生ACP session `730ca24f-50d7-4bb3-b5cc-895d6097bdb6` 真实调用list_agents与delegate，服务端#82 created_by=agent:deepseek，target=agent:kimi；操作员未代替模型委派。#82只读核对resume代码和已有测试，不改代码、不重跑测试，交付行号存在偏移，以函数/用例名为准。Codex核对互斥resume/new分支、拒绝异常链及断言，认可源码级结论。
- Codex读取82 Hall遇403，由合法目标成员Kimi获取服务器结果快照：消息2563，正文SHA256 `f55696a8a3c77109ecc629a33130ea2ab41267962d7f018675adc0ab5ce27407`；本地已审文件SHA256 `ab0f9ed8356127db2f4ae4399ff0933ecc3277d47f9f0b085fb6bb347d1cd5b5`。主控本轮独立重算服务器哈希与JSON逐字段相等，差异仅末尾换行。
- #84一次驱动prompt恢复同session/cwd/DSH_HOME，原始取证requests为initialize→session/resume→session/prompt→session/close，无session/new；原生模型get_delivery两次（含detail）、collect_result(82)一次，退出码0。复核者服务器读回completed与result_collected_at=`2026-09-16T08:14:18.429954`。Codex核对原始驱动记录，不把agentText单独当证据。model_calls=1仅指一次驱动prompt，不推断底层模型请求次数。
- 80/81/83/84由Codex收取；82由DSH原模型收取。80早期blocked与83归属核查partial不因流程completed改写。
- 插曲：共享工作区四文件出现标为#80资源告警清理的额外改动，报告声称Kimi Hall同意；#83新会话无法确认旧会话作者。用户选择不继续追溯，允许备份并恢复1bf186b。已保存四文件、SHA256清单与patch于 `.tmp/l1-dsh-live/resource-cleanup-backup/`，不纳入本片修复。ResourceWarning仍待后续独立处理。
- 证据：`.tmp/l1-dsh-live/execution-kimi.json`、`kimi-readonly.json`、`codex-review82.json`、`server-82-result-body.txt`、`resume-delivery.json`、`live80/evidence/acp-prompt.json`、`resume82/evidence/acp-resume-collect82.json`。试验结束仅删除隔离DSH_HOME内模型凭证副本，保留会话与证据，不动原模型配置及外部本人TALK凭证。
- 结论限于有人值守、单工作区、一次委派、人工独立验收与原会话收取。无人值守、多工作区、页面启停和运行器适配未验收；无新增页面，无需重启TALK服务。下一片WorkBuddy验证，再角色列表开发要求UI；本轮不继续新片。


## 2026-09-16 DSH ACP薄驱动及两轮修正收尾（#74–#79）

- 基线 `3fcbf44`，分支 `codex/terminal-return-codex`。六任务均于本轮收取，保留早期partial与not_run事实；#79最终独立复核通过。本片无真实模型请求、无真实委派，不是DSH主控闭环验收。
- #74新增ACP传输/会话薄驱动、两个无密钥模板、30项测试，扩展precheck dump的profile选项并维护终端指南。#75独立发现下游前导连字符参数、read-only+never不匹配preset、列表过滤活动会话三问题；#76修复为参数等号/无冲突分离形式、ACP read-only+ask并默认拒绝权限、活动隐藏→close可见→resume隐藏的真实语义，原headless不变。
- #77独立验证真实DSH 0.1.5-rc.1与内置ACP rc.2：零模型initialize/new/list/close/resume、错误cwd/未知ID/重复恢复拒绝通过，隔离DSH_HOME持久化成立。ACP30例29过，唯一失败是假密钥落入共享test_support设置的仓库内.tmp-tests，触发正确的凭证保护。
- #78仅改测试夹具：显式解析TMPDIR/TEMP/TMP、resolve确保仓库外、finally清理；缺密钥负例隔离HOME/USERPROFILE，不读取正式凭证。不改共享test_support、安全拒绝代码，不跳过测试、不mock拒绝逻辑。开发宿主CreatePipe拒绝导致18例not_run。
- #79 Kimi独立核对实际增量与快照一致，运行 `python -X utf8 -m unittest tests.test_dsh_acp_drive -v` 30项全部通过（26.349秒），`python -X utf8 -m unittest tests.test_dsh_talk_entry -v` 18项全部通过（6.499秒）。模拟ACP进程下验证父环境密钥清洗、声明路径传递、九工具目录与talk_list_agents可达，外部临时目录清理、缺密钥响亮失败；未重复无疑点的真实生命周期。证据 `.tmp/l1-dsh-acp/review2.json`、`rework-review.json`、`rework2.json`。
- 限制：真实模型工具可见性、真实委派及同会话收取未测，需合法本人凭证来源。测试模拟管道有一条ResourceWarning（unclosed file），记录后续处理，不再次自动返工。未启停共享服务、未修改全局信任/权限、未推断服务器无凭证。
- 变更文件：`scripts/dsh_acp_drive.py`、`scripts/dsh_talk_precheck.py`、`deploy/dsh/acp-overlay.template.yml`、`deploy/dsh/acp-session.template.json`、`tests/test_dsh_acp_drive.py`、`docs/guides/TERMINAL_MCP.md`；Codex同步进度、简报和路线。无最终用户页面变化，无需为本片重启TALK服务。下一片DSH真实模型验证，再WorkBuddy；开发要求UI仍排后。


## 2026-09-16 DSH 入口准备、返工与独立复核收尾（#70–#73）

- 用户先授权主动接收结果，随后明确恢复被动模式；主控已停止主动等待，#72/#73由用户通知收取。四任务均已收取。基线 `9423d02`，分支 `codex/terminal-return-codex`。
- DeepSeek #70交付模板和两个预检/启动脚本；Kimi #71独立发现dump相对patch错误及缺少入库测试；DeepSeek #72修正并新增18项，Kimi #73独立复跑18项/61项组合回归、真实DSH中文空格相对路径dump通过，确认未改模板/启动器hash及冻结范围。Codex差异空白检查通过，不重复全量审查。
- 变更：`deploy/dsh/talk-mcp.patch.template.yml`、`scripts/dsh_talk_mcp_launch.py`、`scripts/dsh_talk_precheck.py`、`tests/test_dsh_talk_entry.py`、`docs/guides/TERMINAL_MCP.md`。新增无密钥MCP配置覆盖层、调用方cwd绝对化、身份/项目检查与错误处理；目录探针含九工具，13行disabled仅为配置层证据。正式进度、路线和简报同步由Codex完成。
- 真实DSH模型未运行，零任务委派。0.1.5-rc.1 headless硬编码新session、不能靠resumeSessionId patch恢复；sdk-jsonrpc不提供持久会话恢复；原生ACP session/resume可作后续方案，尚未实测。不是DSH主控验收通过。
- 凭证边界：子进程基座过滤KEY/TOKEN等，普通启动仅注入环境变量仍需MCP config显式转发，或使用仓库外本人密钥文件；执行者当前拿不到凭证，不代表服务器没有该成员密钥。未读取生产密钥/写外部文件/禁用沙箱。文件真实可读、原生模型工具清单、ACP同会话能力仍待验证。
- #71在不同上下文复跑spawn成功，嵌套EPERM不等同产品不支持；无需将danger-full-access作为默认路径。#73次要观察：期望项目CLI默认值保守拒绝、异常短错误不含详细路径/秒数、非UTF-8控制台中文显示，记录为限制，不因此再返工。
- 用户手册影响：仅开发者终端入口，无新增最终用户页面；更新TERMINAL_MCP，不把尚未可用的主控流程写成页面操作。下一片DSH真实身份/ACP接入，再WorkBuddy；开发要求UI只保存最新内容仍待办。

## 2026-09-15 Kimi 原生主控单任务闭环实测收尾（#64–#69）

- 基线 `29e5021`。#64 两次会话未加载MCP，首次还发生未授权的原生子代理派生；#65 用0.38.0实现和真实cwd/信任状态确认隔离目录未受信，第二次只换配置位置未换cwd。前序失败/partial保留，不伪报通过。根目录临时MCP已由Codex撤回，避免共享bridge副作用。
- 用户明确授权后，仅新增隔离目录信任 `workspace-trust/wd_session-workspace_d9ad240fdb6a`。#66以受控agent-file（3只读+9MCP、subagents空）启动原生session_e7d95ad9-b799-4593-a8cf-19da479d780d，真实调用list_agents和delegate，恰好创建#67给DeepSeek。首次PowerShell引号失败未进入模型，改subprocess列表argv后跑通。Codex明确授权一次顶层general作为测试例外，不授予全局委派预算。
- #67只读核验N1数字保留、空白回退、幂等，结果消息2542。Codex通过MCP读Hall遭403，不绕过权限；#68由原请求者agent:kimi合法转交原文和结构化包。正文SHA256 `6d64c0120142b9a7e520f8dc1ddfc4652dca972e804d6055d48e99c7034f7299`，本地task67-delivery校验通过。Codex独立读实际函数及flush调用点，从源码AST提取函数执行4输入向量和重复归一化断言全部通过；不是完整API/E2E测试。
- #69恢复同一原生session（`-S`，不是另开会话），真实调用get_delivery summary→消息2542的detail→collect_result(67)。Codex在工具执行层解析原始session4-stream.jsonl，确认三次工具调用、同session标识及收取返回 `workflow_status=completed`、`result_collected_at=2026-09-15T14:12:22.756535`。白名单恢复维持12工具，无新派发/派生；引擎429自动重试不算另一个会话，不声称只有一次底层推理请求。
- #64/#65/#66/#68/#69已统一收取，#67已由原Kimi模型收取。#66服务器消息有围栏、#68服务器单字段超长使摘要unknown/invalid，主控使用合法本地包按实际任务号核对；#69最终JSON已合法。收取流程状态不覆盖每份原始业务结论。
- 结论：Kimi Code 0.38.0在受信隔离目录、单项目、一次显式授权顶层任务、人工异身份检查及唤回下完成真实主控闭环。未验证全自动审查/唤回、正式根目录启用、外部密钥文件、跨工作区、DSH或WorkBuddy。保留用户授权的隔离信任、配置和.tmp审计，不清理/重启服务。
- 本片功能源码零改动，更新进度、简报、路线、TERMINAL_MCP信任/恢复/权限说明；下一片按用户最新顺序继续DSH再WorkBuddy。开发要求UI（只保存最新无版本）保留待办，不抢先切换路线。

## 2026-09-15 L1-1 Kimi 独立主控入口准备与复核

- 基线 `eeea11d`，DeepSeek #62 开发、Kimi #63 独立只读复核，均已收取。#62 原自报 partial：缺本人凭证、沙箱不能启动 CLI；#63 在自身环境补齐相应证据，在本片声明范围内 PASS。收取的是入口准备成果，不是全部 L1 主控能力验收。
- 新增 `deploy/kimi-code/mcp.talk.template.json`、`scripts/kimi_talk_precheck.py`、`scripts/kimi_talk_mcp_launch.py`、`tests/test_kimi_talk_entry.py`，更新 `docs/guides/TERMINAL_MCP.md` 和 `docs/spec/MODULE_tasks.md`；复用既有普通终端 MCP，未修改 bridge 工具合同/任务协议/数据库/用户级认证。
- 独立验证：14 项新测试、29 项终端入口与任务工具回归通过；生成配置无密钥；真实匿名管道 `initialize/tools/list` 返回九工具含 `talk_get_delivery`，明确 `identity_verified=false/network_calls=0`。另用 runner 注入的本人 `agent:kimi` 凭证，对真实项目 `prj_e8fe7066bbec` 只读 check 得 `identity_verified=true`；无效凭证 401 且不回显。CLI `--version/--help` 实测 `0.38.0`、无 `--mcp-config`。Codex 完成差异空白检查，不重复全量审查。
- 限制：未激活工作区配置、未启动模型闭环；两级 mcp.json 加载/新会话生效仍据官方文档，需下一片真实会话验证。真实本人外部密钥文件未走通（隔离测试覆盖读取，真实身份用环境变量）；开发的文件型 stdio 退化与复核的正常管道证据分开保留。
- 轻微待办：显式 `--expect-project` 才有独立期望项目断言，缺省与解析项目相同；激活前决定 `.kimi-code/` Git 忽略策略。复核认为不阻塞本片，主控接受并记录，未顺手改实现。
- 用户新需求已记入路线与进度：角色列表项目级开发要求，面向主控保存职责/交叉复核等，仅最新内容，不设版本号/历史；派发前读取，已派发任务按原包执行。以后替代 AGENTS 相应分工部分，当前未实施，不改变当前规则。
- 本轮收尾更新正式进度、路线及简报；下一片建议开发要求，Kimi 真实主控闭环仍为待办，不自动激活配置、不新增任务、不启停共享服务。

## 2026-09-14 N1 统一任务标题开发、返工与独立复核收尾

- 用户授权 Kimi 开发 N1；基线 `ca2b40857c11d5850e1d8ebc2d0fc6fd128b7ea4`，分支 `codex/terminal-return-codex`。#58 开发，#59 独立复核后，Codex 收尾发现 `base == str(task_id)` 错误吞掉合法数字名称；#60 最小修复，#61 再次独立复核 PASS。四项均已收取，页面人工验收待完成。
- 创建唯一入口 `_create_task_with_hall` 在 flush 后同事务写“真实编号-任务名称”及 Hall 名，Web/MCP/SDK/schedule 复用；前端下拉避免重复拼编号。空白统一“未命名任务”，不以正文回退，保持 wait 短引用不携带任务正文的合同。历史标题不迁移。
- 返工删除吞名条件，纠正一个错误测试预期、增加两个测试（标题用例 10→12）；同值纯数字保留为 `60-60`。#61 独立检查实际函数、API/列表/详情/Hall及测试断言；旧逻辑等价复现可触发三个失败向量，不声称取得已覆盖的 #58 原始工作区快照。
- 验证：#61 独立运行 `tests.test_task_title` 12 项，`tests.test_tasks/tests.test_talk_task_tools/tests.test_talk_client` 76 项，Node 标题测试 4 项、独立 API 探针 6 项全部通过；未改部分继承 #59 的 50 项 Node 及其它定向证据。Codex `git diff --check` 通过，未重复完整审查/全量测试。
- 限制：真实浏览器未验收；子进程管道 E2E 受复核沙箱 spawn/WinError 5 限制未运行，Node 使用进程内执行。人工复制已带旧编号标题可产生双编号，现有产品无自动复制路径，本片不扩展任意标题清洗；Hall 名沿用80字符截断。共享服务未重启，线上加载新代码需另确认。
- 交付：#58/#60/#61 为合法完整 JSON 结果；#59 的说明与代码围栏导致 MCP 判 unknown，按本地 `.tmp/n1-task-title/review.json` 经 `summary --expect-task-id 59` 校验获取完整报告，未凭 runner succeeded 验收。#61 复核前后关键文件哈希一致。
- 变更文件：`server/routes/tasks.py`、`web/app.js`、`tests/test_tasks.py`、`tests/test_task_title.py`、`tests/workspace_task_title.test.cjs`、`docs/spec/MODULE_tasks.md`、`docs/guides/USER_MANUAL.md`；Codex 同步 `docs/PROGRESS.md`、本历史、路线及简报入口。
- Git 收尾：首次推送因远端归属与外发信任未验证被自动审批拒绝；随后用户明确确认 `bobo506/TALK` 为其仓库并授权推送。N1 提交 `2b917ce` 已成功推送至 `origin/codex/terminal-return-codex`，阻塞解除。
- 下一步：用户验收新任务标题与已有耗时页面；再按路线推进 L1，当前不自动派发下一片。默认被动等待约定不变。

## 2026-09-14 群聊前移与桌面开发顺序调整

- 用户要求群聊后续功能前移到第7阶段，桌面端在基本功能完成后再开发。路线与当前进度已同步：第1–6阶段为任务名、主控验证、模式、工作区、隔离及角色管理；第7阶段群聊，第8阶段起桌面封装及整体验收。
- 为保持依赖一致，普通Web角色启停入口并入第6阶段；桌面阶段只接原生目录选择、窗口/启动退出与既有Web功能。未派发开发、未修改功能代码。


## 2026-09-14 桌面工作区与多终端主控路线规划

- 用户要求记录：所有角色作为主控的验证；Kimi Code/DSH/WorkBuddy不同入口可用性与是否需独立适配；Windows桌面程序自动启动TALK但不自动启动角色、原生目录新增/加载工作区、角色列表手动启停、A/B同角色独立会话、关窗退出所属所有服务。保留Codex Desktop与原生运行器，不重建Agent框架。
- 创建spec/DEVELOPMENT_ROADMAP.md汇总完整需求、现有/缺口矩阵、N/L/C/W/I/R/D/U/A/G切片顺序、验收与未知项。标题仍为编号-任务名称；主控模式默认被动并保留最小续等约定。新增/加载不等于复制仓库，任务记录当前为逻辑隔离，不声称已实现每目录独立数据库。
- 定向源码核对：Project已有project_root_path，ProjectAgent按project/member存资料；AgentInstance无明确project字段，worker任务发现主要按目标member筛选。多目录进程/会话/任务领取隔离须在正式角色启停UI前落地，不能只切前端列表或cwd。
- 官方Kimi Code MCP、WorkBuddy MCP与模型配置页面已打开核对；这些仅支持通用接入候选，不证明本机主控全流程。按宿主适配、按模型验证，不能把WorkBuddy中的Kimi当成Kimi Code CLI。
- 计划明确服务所有权及正常/异常退出、不误杀外部独立终端、运行中停止与任务记录一致性。切换工作区是否自动停旧服务、具体桌面技术壳和历史标题迁移在对应切片细化，默认建议保留旧工作区服务直到手动停止/应用关闭。
- 同步PROJECT_BRIEF入口、PROGRESS、群聊与历史回传文档链接。仅文档，无代码/用户配置/服务操作/任务派发；检查后统一提交推送现有授权分支，下一步由用户决定何时开工。


## 2026-09-13 任务命名需求修正

- 用户确认顶部项目选择已区分项目，取消标题中的项目名称前缀；最新目标格式为“编号-任务名称”，例如58-主控模式切换，取代此前“项目名称-编号-任务名称”。已同步待办与当前进度；仅记录，不改代码或历史任务名称，主控模式按钮待办不变。


## 2026-09-13 后续模式按钮与命名需求记录

- 用户要求仅记录后续两项改动：保留Codex Desktop的前端主控主动/被动切换；任务名称统一为“项目名称-编号-任务名称”，项目名称可取目录名。
- 已写入BRAINSTORM_NEXT与当前进度。主动保持等待并遵守最小续等规则，被动结束本轮由用户通知；工具响应携带模式但不承诺唤醒已结束会话或覆盖宿主指令。没有开发功能、派任务、修改现有任务名。
- 用户同时询问Kimi Code官方API重新配置。只读核对本机当前为managed:kimi-code官方托管登录、默认kimi-code/k3；未读取或输出凭证，未代改认证或启停bridge。


## 2026-09-13 最小续等行为约定

- 用户明确只采纳#57建议1，暂不考虑降低推理强度与进一步用量归因方案。#57咨询已收取；#56部分验证也已收取，但模拟端点A/B未运行，不将静态证据写成运行时替换成功。
- AGENTS新增：原工具仍运行、无新用户输入或异常时，只按原运行标识续等；不重复查询任务、读文件/diff/历史或展开方案，不重复发起内部请求；更高优先级要求的沟通仅保留最短必要说明。完成/超时结束/异常/新输入时退出此路径，避免盲目续等。
- 当前默认由用户通知主控收取，只有明确要求持续等待时采用该约定。仅修改项目提示词与进度，不改代码、模型/推理强度、全局配置或超时参数，不做新的等待实验；不能保证内部推理为零或承诺固定用量节省。


## 2026-09-13 左侧任务列表执行耗时

- 用户确认HH:MM:SS耗时切片，并要求主控持续等待。基线d9a32fe；Kimi #54实现、DeepSeek #55独立复核PASS，无返修，两项已收取completed。
- 复用claimed_at→finished_at；排队、待收取不计入，重试取最近一次claim。执行中本地单timer每秒原地更新、终态冻结；缺失/无效时间显示—，小时不回卷。无需后端/协议/DB改动，既有5秒状态轮询不变。澄清/人工决策阶段无有效结束时间时显示—。
- 独立48项回归通过（新Node7+既有Node39+Python2），73个真实/合成时间样本与独立Python期望一致；11种状态门控与完成后冻结、timer生命周期、零额外网络/重绘验证通过。Codex不重复完整测试或代码审查。视觉验收留用户；6位微秒在V8可解析，Safari/WebKit未测，未做真实HTTP端到端验证。
- 等待观察：4次talk_wait_tasks，内部600秒预算；#54两次内部耗时600.032（超时）/83.032（命中）秒，#55为600.032（超时）/47.734（命中）秒；外层往返分别605.111/89.315/603.138/52.917秒。各exec实际yield=60000ms，受当前宿主指令约束，未实际采用项目目标600000ms，不能作为60秒与600秒对照。外层functions.wait分别11/1/10/0次，其中一次为1000ms短续等；此次仍有主动调用造成的干扰，不量化token或额度节省。主控未结束等待让用户再来收取。
- 修改文件：web/workspace.js、web/app.js、web/style.css、web/index.html、tests/test_task_web_ui.py、新tests/workspace_task_duration.test.cjs；同步MODULE_webui、USER_MANUAL、PROGRESS与本历史。临时开发/复核材料不入库。
- 用户验收：刷新现有TALK页面进入任务列表，观察已结束项耗时固定、执行中每秒递增、未开始项—；等待收取不应增加完成耗时。视觉布局尚待确认，完成本片提交推送后停止扩展。


## 2026-09-13 用户指定600秒项目等待目标

- #52 Kimi官方资料调研、#53 DeepSeek本机调研均已收取。二进制发现原句不证明当前会话加载路径；model_instructions_file 是否能替换该开发者层指令未证实，未改安装或用户配置。
- 用户明确要求先从60秒改为600秒。仅改TALK AGENTS的项目默认目标：exec/wait的yield_time_ms=600000，前提为宿主工具能力与更高优先级指令允许；当前会话仍按其避免超过60秒阻塞的要求执行，不能宣称600秒目标已实际生效。
- 内部TALK等待600秒、用户级MCP超时660秒保持。此前yield600000的短程试验约53.6秒直接返回、未触发55秒保护；连续600秒能力和计费节省仍未验证。本次只有规则/进度文档改动，不新增等待实验。


## 2026-09-13 外层 yield 只读对照实验

- 用户批准咨询后的最小实验；Kimi #50、DeepSeek #51 咨询此前均收取完成，两份完整 JSON 已由真实 talk_get_delivery 识别为结构化自报、任务号匹配、无省略，补齐新版真实结构化入口验证。候选建议未直接当作已验证能力。
- 控制条件：同一已完成任务 #50，talk_wait_tasks(task_ids=[50], timeout_seconds=45, workflow_statuses=["clarification_requested"])。等待不会自然命中的状态，不改任务/服务/配置；两组顺序运行，各一次，只改变 exec 外层 yield。没有另派 Agent、没有跑600秒实验。
- A组 yield_time_ms=1000：exec 在1.0秒返回 running cell，随后1次 functions.wait(yield_time_ms=60000) 返回完成；执行单元测得工具往返53.411秒，TALK内部45.032秒、13轮/13 HTTP请求，return_reason=timeout。B组 yield_time_ms=60000：exec 在49.3秒直接返回完成，工具往返49.313秒，TALK内部45.031秒、13轮/13 HTTP请求；0次functions.wait。两组结果任务均 succeeded/completed。TALK内部耗时与外层往返耗时不同，不把差额直接归因为模型。
- 两组等待中均0条用户进度消息；只在实验开始、A/B阶段切换、结果出现时说明。A比B多一次续等工具调用及调用它的模型续行；没有单轮计费数据，不换算额度节省。
- 结论：本样本确认主动短yield可以制造额外续行，B证明当前环境能至少约49秒直接等到结果，不能断言宿主必须更短周期唤醒。只各测一次、非随机顺序，不能外推600秒零续行，也未验证60秒以上边界；当前更高优先级沟通/阻塞约束仍存在，不越过该约束验证长阻塞。
- 已将显式60秒外层等待习惯写入 TALK AGENTS；内部600秒默认及用户级660秒超时不变，其他项目/全局配置未改。长任务仍可能每60秒续等，不将其记为已消除。当前片结束，无需重复实验或启动受管入口改造。


## 2026-09-13 默认完整摘要、去重与真实重连验证

- 用户要求优先减少外层续等与无变化更新，并取消摘要默认机械截断。只读核对 MCP 超时仍为 660 秒，它不控制外层 functions.wait；公开配置参考本轮未找到可确认关闭外层续行/进度的开关，当前宿主还有更高优先级沟通约束。项目规则要求避免无变化播报，但未实现或证实配置级消除；两项等待问题仍待解决，不把摘要变更算作已完成等待优化。未修改用户配置、模型、权限或服务。
- 前版 b02127e 已提交推送；用户重连后，真实 talk_get_delivery 对 #45/结果2521 返回旧文本 unknown；两页 773 字符与整页内容一致，hash 一致，收取时间/状态未变。完成的是旧版入口冒烟；本次新合同仍需再次重连后验证，未重跑长等待实验。
- 本片基线 b02127e。DeepSeek #46 开发、Kimi #47 初审，发现显式限长时可见裁剪与 text_truncated 不一致，并指出重复正文；DeepSeek #48 返修去重，同时补齐此前 MCP 响应缺少的验证证据、限制及下一步。Kimi #49 最终独立复核 PASS：155 项定向测试（47.220s）+17 项独立断言全过。
- 合法结构化摘要默认不设 1200/6000 总字符上限、不按条目机械裁剪。CLI 完整输出；MCP 三类正文只在 preview.items，其它核心内容完整保留在同次响应 summary_text。独立夹具末尾阻塞/完成/未完成、证据、限制、next 均保留，6 个 sentinel 各出现一次。保留 schema/任务号绑定/64 KiB 拒收、只读、stable reference 与 detail 分页；格式通过仍不代表业务验收。
- 显式 text_limit=600 的独立夹具裁到486，标志与 omitted 一致；仅 json_limit=3586 缩 preview、正文未裁，文本标志 false；极小 json_limit=200 可触发可见最小兜底，JSON 仍可能超预算并明确报告。旧文本仍 unknown+300字符预览，省略可补读。默认无机械裁剪不等于接受无限输入，也不补回上传前丢失内容。
- 同夹具返修前后 JSON 3990→4466，重复条目13→0，原缺失验证/限制/next 从0→1；信息补齐导致总长度增加，不把字符数当 token 或额度。本轮中途共享额度五小时51%、周33%，不可分摊为本片成本；完成当前片后暂停。
- 用户发现 dsh 历史 pwsh 调用显示结果未持久化/unknown。核对 #48 已提交，#49 派给 Kimi且已完成；独立复核重新运行155项测试通过，未因该旧记录盲目重复测试、终止进程或重派任务。unknown 本身不是测试失败证据。
- 修改文件：scripts/talk_workflow.py；bridges/talk_delivery.py、talk_task_tools.py、talk_terminal_mcp.py；tests/test_talk_workflow.py、test_talk_delivery.py、test_talk_terminal_mcp.py；docs/guides/TASK_WORKFLOW.md；AGENTS.md；docs/spec/MODULE_bridges.md、TERMINAL_RETURN_DRAFT.md；docs/PROGRESS.md、PROGRESS_HISTORY.md。临时报告不入库，页面与用户手册未变化。
- #46–#49 已全部收取 completed，收尾3项编码测试与 git diff --check 通过。本片统一提交/推送 codex/terminal-return-codex，不合并 main；新版本重连后只需一个已有合法结构化结果的真实完整性冒烟。等待/唤醒能力仍为后续问题，不扩展下一片。


## 2026-09-13 恢复并补齐第二片 Git 收尾

- 用户指出昨日停在收尾承诺处。实际核对 HEAD 仍为 881ce12，本片12个文件已落盘但未提交；不能把昨日“统一提交推送”的收尾计划当成已完成事实。
- 当前用量工具读数五小时已用1%、周已用25%；昨日96%门禁已过期。沿用Kimi已完成的140项定向测试、13项专项断言及真实管道证据，不重复完整代码审查/测试；仅对收尾文档做编码和Git差异检查，并补办统一commit/push到已授权分支。
- 当前宿主工具目录仍不含talk_get_delivery；真实入口冒烟仍待用户重连后执行。未重启服务、未改用户配置、未开新优化片。


## 2026-09-12 MCP 只读交付摘要与可追溯补读

- 用户授权下一片，并担心 1200 字符截断影响含义。Codex 限定新增单一只读工具，保留旧默认合同；摘要作为索引，省略必须可见，按结果引用与内容 hash 分页补读，不能猜业务成功。
- 基线 881ce12。DeepSeek #42 开发、Kimi #43 全面独立复核，129 项测试与真实匿名管道通过，但发现 parse_delivery_report 未传 expect_task_id，别的任务报告可能被当有效自报。DeepSeek #44 返修；Kimi #45 针对性复核通过：交付测试51项+任务工具/MCP/原CLI共89项=140项，另13项独立断言通过；真实匿名管道stdio退化0次。开发环境管道受限的缺测已由独立复核补齐。
- 结构化解析、结论和detail字段三条路径均绑定实际task.id；错号complete/partial/blocked为invalid/untrusted，错号内容不进入结构化预览；合法7/#7规范化通过，自由文本unknown，完整服务器原文分页仍可读取。只读查看无collect/accept副作用，服务端API/数据库/旧工具/角色列表/等待未改。
- 摘要文本上限1200字符，正常JSON响应上限6000字符，显式显示计数/省略/补读；detail默认2000、上限4000字符，可选择结构化字段。携带结果消息ID和expect_sha256发现引用或内容变化，stale不返回正文，需从头读取；仅ID不能识别同ID内容改变。源按结果ID及Hall作用域定位，不扫描完整历史或根据消息路径读本地文件。
- 开发样例9451字符报告：摘要文本901/1200、JSON4004/6000；阻塞与未完成各20项、各3显示17省略；10页重建hash一致。25万字符自由文本：JSON2710、preview300、结论unknown；Kimi检查分页无损与限制。字符指标不代表额度节省，分页只能取已存内容，不能补回bridge上传前已截断的部分。
- 本轮主控按期望任务号校验报告，实际拦截#43误写review-42。核对TALK任务43的结果消息明确指向review.json后，保留原件，另写review-task43.json更正元数据并记来源，审查FAIL证据未改。#44/#45报告实际任务号正确。截断时只补读verification、unfinished、blocked、limitations必要字段。
- #42–#45已收取完成。当前宿主工具目录不含talk_get_delivery，未重连、不宣称真实宿主已加载；隔离LiveTalkServer与stdio测试不替代宿主端到端冒烟。pi TypeScript扩展未改。
- 等待工具调用：#42为600秒超时仍running，后404.297秒命中；#43为298.875秒；#44为434.485秒；#45为600.031秒超时仍running，后72.891秒命中。这是调用等待时间，不是完整Agent工时或计费时间；仍有宿主续行和无变化消息，本片没有解决等待成本。
- 用量工具前后读数：五小时59%→96%、周19%→25%，仅账号共享窗口快照，不足以证明独占归因或节省。usage-gate返回continue但session/weekly读数为null，实际额度以可用应用工具为准。>=90%触发收尾：本片必要文档/验证/提交推送后暂停，不启新片。
- 变更文件：bridges/talk_delivery.py、bridges/talk_task_tools.py、bridges/talk_terminal_mcp.py、tests/test_talk_delivery.py、tests/test_talk_task_tools.py、tests/test_talk_terminal_mcp.py、docs/guides/TASK_WORKFLOW.md、AGENTS.md、docs/spec/MODULE_bridges.md、docs/spec/TERMINAL_RETURN_DRAFT.md、docs/PROGRESS.md、docs/PROGRESS_HISTORY.md。用户页面无变化，最终用户手册不变；临时报告不入库。Codex仅文档和必要Git核对，不重复完整代码审查。
- 收尾统一commit/push到已授权codex/terminal-return-codex，不合并main；额度恢复和MCP重连后只补一次只读宿主冒烟，再决定下一优化片。恢复指令：继续项目。


## 2026-09-12 使用流程第一片：本地交付校验与摘要

- 用户要求逐项优化协调消耗，先调整使用流程，并指出只靠提示词可能不可靠。Codex 将本片限制为本地脚本、短模板及调用约定，不改生产 MCP/HTTP/SDK/bridge/数据库/任务状态或等待配置。
- 基线 `aa90682`。DeepSeek #38 新增脚本、指南、测试；Kimi #39 独立复核原版 44 项通过，发现深嵌套 JSON 未捕获异常。Codex 另要求完成声明与 fail 验证互斥，并增加显式任务号核对。DeepSeek #40 返修，Kimi #41 最终 PASS_WITH_LIMITATIONS，独立运行 `python -m unittest tests.test_talk_workflow tests.test_encoding` 共 63 项通过，并自行构造失败夹具验证。
- 本地 `validate` / `summary` 使用 UTF-8、严格字段与自报一致性校验；complete 不能带未完成/阻塞或 fail 验证。`--expect-task-id` 支持 `38`/`#38` 等价匹配，不匹配短错误非零；深嵌套输入短错误非零，无 traceback/原文回显。摘要默认硬上限 1200 字符，关键阻塞优先并标记截断。没有联网或自动收取副作用。
- 已在本轮实际使用摘要读取：开发报告 1033/1200 字符未截断，返修及最终复核各 1110/1200 字符且已截断。#40 报告一处“未截断”证据措辞过时，命令 exit 0 属实，正式汇总以实测与 #41 为准；不据此扩大代码返修。Codex 未重复全量代码审查/测试，仅运行摘要和必要文档/Git核对。
- 两次派发因顶层子任务类型/质量任务参数组合不合规遭 422；修正后正常创建 #38/#39，后续 #40/#41 直接使用最小字段成功。指南固定顶层 `project_id/target_member_id/title/content`，不把内部 quality 称谓当作新增 task_kind。用户询问重复标题时，列表核对仅一条复核 #39，标题 #38 指复核对象；界面重复显示原因未验证。
- 开发等待 429.422 秒，初审等待 223.781 秒；返修一次 600.032 秒等待超时但任务仍 running，随后 88.032 秒等待命中；最终复核等待 278.906 秒。这些是各工具调用等待耗时，不是 Agent 完整工时或计费耗时。仍有宿主续行、无变化更新和必要的状态查询，未证明减少用量；用户观察的此前 10 个百分点无法从现有工具读数精确分摊。
- #38/#39/#40/#41 成果均已收取。指南分工保持前端 Kimi/DeepSeek 复核、后端相反；执行者准备进度草稿、Codex维护正式进度，验证与文档结束后统一提交推送。AGENTS 已链接本地入口；校验仍由调用者显式执行，未接入 bridge/MCP 自动强制，不能证明事实或内容归属，启发式脱敏不保证覆盖所有密钥形态。
- 变更文件：`scripts/talk_workflow.py`、`tests/test_talk_workflow.py`、`docs/guides/TASK_WORKFLOW.md`、`AGENTS.md`、`docs/spec/MODULE_bridges.md`、`docs/spec/TERMINAL_RETURN_DRAFT.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。临时交付报告不入库；无用户界面变化，检查后不修改最终用户手册；不启停服务、不操作浏览器、不改用户配置。
- 本片收尾统一提交并推送既有授权分支 `codex/terminal-return-codex`，不合并 main；到此暂停，下一片先确定 MCP 交付摘要/业务完成信息合同，不同时实施其它优化。

## 2026-09-12 临时材料清理与指定分支推送完成

- 用户确认目标分支 `codex/terminal-return-codex`，并明确要求派 DeepSeek 操作。任务 #37 负责本地 Git 整理及正常推送；Codex 负责结果核对、必要推送补办与进度收尾。
- 操作前 `HEAD=7b6fbcf`，仅新增 414 个 `.tmp` 文件和两个 `web/.preview-*.html`。操作前远端目标分支不存在；DeepSeek 报告同时核对该提交尚未发布。
- DeepSeek 建立仅本地备份 `backup/pre-cleanup-7b6fbcf`，安全整理未发布末端提交；新 `HEAD=d323c91`，父提交仍为 `4c09544`。新提交仅修改 `.gitignore`，完整保留用户已有 `.tmp/th7-terminal-v1/` 规则，补充 `.tmp/` 与 `web/.preview-*.html`。
- Codex 独立核对：原 416 个路径缺失 0；`a1b5cf3..HEAD` 内新增临时路径 0；排除临时路径与 `.gitignore` 后，业务文件差异 0。原已发布历史中的 `.tmp/mem1_e2e/talk-test.db` 未纳入本次改写，不声称仓库所有历史均无临时文件。
- DeepSeek 的 push 因沙箱无法创建 `remote-https` 子进程管道失败。Codex 按用户既有明确目标授权执行正常 `git push origin HEAD:refs/heads/codex/terminal-return-codex` 成功；随后 `ls-remote` 核对远端为 `d323c91fbd9cce9c1842a4524e859ef9c0c42ba5`。任务 #37 成果已收取，工作流为 completed。
- 未删除本地文件、未强推、未推送备份引用、未合并 main、未重写已发布历史。业务代码无变化，未重跑业务测试或操作浏览器、服务。清理后工作区干净；随后由 Codex 更新本条历史与当前快照，随收尾提交推送。
- 变更文件：`.gitignore`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。当前版本继续先使用，消耗优化维持暂缓；下一功能方向仍为会议轮次与原终端往返最小合同，本轮未展开开发。

## 2026-09-12 使用决策与优化暂缓

用户确认当前版本先用，外层续等、重复更新、消耗归因、断线续接、取消/进程生命周期与大规模ID输出暂列待办。仅在用户反馈额度消耗仍快时重新评估，不自动派发或定时监控。详细清单见spec/TERMINAL_RETURN_DRAFT.md末节。此轮仅文档记录，无新测试/状态查询。

## 2026-09-12 十分钟等待实现与独立复核完成

- 开发DeepSeek #31/#32，返修#34；Kimi #33/#35/#36独立复核，最终PASS_WITH_LIMITATIONS。#31与#35分别被默认600秒整轮执行预算终止，未误判为测试失败；用户重启两bridge后已核对均显式--timeout 3600。
- 功能：wait_tasks默认/上限600秒，结果/失败/澄清等目标状态提前返回；任务摘要最多20条，命中路径仅列命中任务，完整ID列表O(N)，可按任务ID追溯；query_stats仅保留程序实测计数，取消不立即停止同步等待，不承诺Windows退出清理/断线补领/零模型回合。
- 证据：最终开发27项40.650秒（墙钟42.460），Kimi正常管道27项36.059秒；#36规模补测墙钟10.457+11.564=22.021秒。45/300/1000任务摘要恒20，1000任务返回12248字符；报告中严格有界与普遍ID包含声明已更正。临时300任务探针错误下界断言无效，不作为实现失败。
- 当前Codex真实客户端（返修前已加载版本）：单次600秒等待工具600秒、客户端604.269秒、内部123次HTTP、8次外层续等；已有成果立即返回工具0.016秒、客户端4.205秒。返修未改等待循环，未重复长测试；最新返修输出需MCP重连生效。
- 耗时：#34执行559.230秒；#36从08:20:59.736326至08:26:26.151472 UTC，326.415秒。历史#33独立复核321.091秒。各测试嵌在执行时间内，不可重复相加；早期两项真实隔离等待有重叠，不可相加作为墙钟。
- 收尾裁决：保留完整轻量ID索引，非严格输出上界；主控日常等待仅传当前task_ids，避免项目全量结果进入上下文。取消/断线恢复另列，不扩大本片。无浏览器验证、无远端推送。临时报告/日志不提交。
- 改动文件：bridges/talk_task_tools.py、bridges/talk_terminal_mcp.py、两个对应tests、MODULE_bridges、TERMINAL_RETURN_DRAFT、WAIT_TEST_RECORDS及进度快照/历史。


## 2026-09-12 单个300秒MCP请求验证通过

- 重连后仅调用一次long_wait_probe(seconds=300, marker=single-mcp-300s-20260912)。工具返回elapsed_seconds=300.0，标记一致，结果进入当前原对话；配置单工具超时360秒。确认此条件下单个stdio MCP请求可持续5分钟，没有用多个短MCP请求拼接。
- 纠正前次实验解释：两次实验均由Codex显式设置外层functions.exec yield_time_ms=1000，因此早期返回running cell及随后续等不能证明宿主强制每分钟唤醒模型。本次外层仍有续等和模型回合，不能声称已实现等待期零模型消耗，也没有量化节省比例。
- 未验证取消、断线补领、真实任务完成提前返回、回合结束后的外部主动唤醒；探针只是同步sleep。返回server_tool_calls=1为探针固定字段，单次调用结论依据实际工具调用轨迹，不将该字段冒充独立计数。
- 已移除用户级配置中本次添加的talk_wait_probe独立块，并用TOML解析比较确认其它配置保持不变；已加载工具可能留到下次重连。临时脚本保留在.tmp/mcp-long-wait-probe/，未提交。生产TALK等待上限和超时配置未修改。
- 下一步建议单独授权一个小切片：DeepSeek放宽现有wait_tasks的有界等待至300秒，匹配客户端超时并保留任务/成果引用及短摘要；Kimi独立复核。外层等待策略也须避免主动设置过短yield；当前环境有定期沟通要求，尚不能承诺整个等待零模型回合。断线/取消/提前完成与信息连续性须专项验证，不因本次探针通过而视为完成。


## 2026-09-12 准备单请求长等待实验

- 用户授权再试一次。Codex仅编写隔离实验夹具（非生产功能），本地0秒stdio initialize/list/call通过；新增用户级talk_wait_probe配置tool_timeout_sec=360，既有TALK/密钥不变。当前工具目录仍未加载新工具，需重连后试一次300秒。未运行长等待、不声称节省额度；探针/配置仅本地，恢复细节见TERMINAL_RETURN_DRAFT。

---

## 2026-09-11 5分钟等待实验

- 用户授权实验。现有MCP短等待经单个functions执行单元组合，实测305秒、9次超时请求，任务#30保持completed，无业务修改。宿主提前yield，仍需5次functions.wait；不能声称零模型参与、单MCP300秒或额度节省验证通过。单请求超时/取消/断线/成果提前返回留待隔离测试。仅记录结果，无功能代码变更。

---

## 同类工具等待机制调研（#30）

- 用户指定D:/claude-test/调研，DeepSeek完成只读相关章节调研并提交；LLM-Wiki-Gist未读完。Codex未重复阅读报告全集，仅取摘要并核对wait_tasks的30秒硬上限与程序循环。
- 首选转向单次工具调用持续等待，先验证当前Desktop的长调用预算；服务端task事件不是最小验证前提，外部唤醒/受管终端保留后续选项。详细报告在.tmp，主要结论及修正写入TERMINAL_RETURN_DRAFT。
- 未进行等待实验、未改功能/配置/服务、未浏览器操作；无节省比例或自动回传成功声明。

---

## 2026-09-11 Codex原会话回传接入核验

- 用户授权Codex首片并要求会话信息准确连续。从6bdf380建立codex/terminal-return-codex，DeepSeek #28探索，Kimi #29只读复核PASS_WITH_LIMITATIONS。
- 本机daemon路径不支持Windows；协议具备resume/turn与状态字段，但当前Desktop原会话外部安全接入未验证。Kimi指出“入口不存在”推断过强、proxy/过载部分证据不足、报告路径误写；决策Agent在设计文档明确纠正，不把这些当已证事实。
- 连续性合同无明显缺项，另起宿主读同一threadId仍不能证明原窗口同步/唯一执行者，故未写替代代码。需用户决定保留Desktop人工续办，或接受受管理Codex入口的进一步设计与迁移验证。
- 只有设计/进度文档变化及.tmp本地探针证据；无真实模型调用、原会话修改、服务启停、数据库/用户配置变更。没有运行无关代码测试或宣称端到端已通；Git只本地文档提交，不推送。

---

## 2026-09-11 统一终端回传设计草案

- 用户要求仅设计，覆盖Codex/Kimi/DeepSeek发起终端。新增TERMINAL_RETURN_DRAFT.md，区分通用通知、原会话路由与运行时适配；自动续接接口先验证，不将MCP通知等同于唤醒模型。
- 当前MCP实测1322字符，3角色各1实例且无last_error，确认已加载有界输出。官方CodexApp Server支持会话恢复/新回合，但当前Desktop可接入性未实测；Kimi/DSH同样待核验。
- 仅文档变更，无开发派发、无服务或浏览器操作，不声称回传机制已实现。

---

## 2026-09-11 MCP角色列表有界输出完成

- 用户要求修正完整历史角色列表造成上下文浪费。DeepSeek #26开发、Kimi #27独立复核PASS，双方已收取；Codex只协调和维护文档，未重复开发/代码审查/测试。
- bridges/talk_task_tools.py默认每角色按last_seen_at只返回最新一条实例及6个必要字段，项目与非项目来源均覆盖，去除历史实例和last_error。保留instances数组及既有availability语义，新增未核验心跳提示与工具描述。
- tests/test_talk_task_tools.py新增3项行为回归。Kimi独立实测工具8/8+终端8/8通过（含stdio）；DeepSeek环境CreatePipe限制下缺测已被补齐。大历史/长日志测试验证payload<1500字符并无日志标记；开发者另有13.6MB→约0.6KB样例，后者并非真实计费token指标。
- 未改后端接口、数据库、前端、用户配置；旧pi扩展和check提示完善留作非阻断后续。驻留旧MCP进程需重连加载，未由Codex操作重启。
- 工具修复两文件与进度文档本地保存；临时证据/.tmp/预览不提交，不推送。前一页面切片9a4c0d7待用户页面验收。到此停止新切片。

---

## 2026-09-11 第二项独立复核完成

- DSH默认模型改为deepseek-flash后，#25成功审查#23，结论PASS。DeepSeek独立核对CSS级联、DOM结构和模式切换，实际39项Node、2项Python通过；Node测试首次沙箱派生受限后逐文件执行，无真实浏览器验收。Codex仅读取审查摘要，不重复审查代码和测试。
- Kimi改动workspace.js、workspace.css、index.html及新增workspace_task_chat_layout.test.cjs；同步webui模块说明。页面由用户验收，未推送。新增测试含弱字符串断言、缺少实际CSS渲染覆盖的限制保留。

---

## 2026-09-11 第二项开发已交付、审查被过期模型阻塞

- 用户要求继续昨日额度中断的工作，并调查Codex消耗。新规则为执行Agent承担开发/自测/独立审查，Codex默认不做computer use，页面交用户验收；已同步AGENTS。
- 昨日创建codex/task-chat-layout（基线a0fe577），Kimi任务#23完成：任务完整对话使用task-chat-mode隐藏重复详情栏并改双栏；任务页及普通群聊保留原结构。Kimi报告39项Node、2项Python通过；本轮Codex没有重复运行或查看完整代码，没有声称浏览器通过。昨日只查看改动前页面与虚构布局预览，不能当作最终验收。
- 本轮创建DeepSeek只读审查#24，提供需求/不变项/基线/文件/测试证据。预检即失败：deepseek-v4.1-flash-expires-on-0910到期，服务建议deepseek-flash。尚未审查；已请用户修改DSH默认模型，未改用户级配置、未重启服务。
- 消耗证据：昨日talk_list_agents完整历史输出标记原始约64718 tokens，含旧错误日志；输出被截断，不能直接换算实际计费或用户观察的30%。重复文档读取、轮询、浏览器截图/树亦有成本，无法精确分摊。整改为工具执行层筛选摘要、避免重复背景读取、取消Codex默认页面验证。
- 当前保留Kimi未提交代码与测试，#23仍submitted，#24failed。不伪造审查或收取；模型修正后仅续办审查。临时预览/.tmp不提交；GitHub推送授权问题沿用既有记录。

---

## 2026-09-10 Kimi 首次实际前端开发：成果按钮可收起

- 用户指定前端交给官方 Kimi Code 测试执行角色，并明确“两项改动一样样来，小心点”。本轮只完成第一项；Codex 负责范围、示例预览、复核、浏览器验证和文档/Git，Kimi 负责代码与测试。启动使用 `--kimi-task-profile tools`；业务角色 reviewer 不阻止本次明确授权的开发，未改全局角色配置。
- 从 main/8197ce9 创建 `codex/ui-result-toggle`。先在真实 #19 复现不能收起，再提供本地示例预览；预览与既有 .tmp 保留且不提交。
- TALK 任务 #21 在 09:04:27 UTC 领取，09:14:27 失败，耗时达到默认600秒；留下局部代码与测试，没有完整报告。错误文本仅为 bridge 未返回结果，不能进一步确认是断线还是执行耗时导致。用户随后说明连接曾中断。没有把此失败报告当作开发成功。
- Codex 发现初稿的项目切换保护和重绘测试不足，发出复核反馈；创建同一切片的续办 #22，明确仅补这几处。#22 于09:15:39领取、09:24:59成功提交，结果消息2496；本会话恢复后独立复核、反馈并收取为completed。#21失败历史保留，未做自动重试或并行改码。
- 最终实现：成果按钮在查看/收起之间切换；加载中可关闭并作废请求；旧成功/错误不回填。状态绑定项目/账号/任务，空项目切换与返回也清除旧展开；详情刷新保留用户状态。补无障碍属性，保持权限、文件、撤回与错误内容。未改第二项完整对话侧栏、CSS、后端、bridge或协议。
- Codex 独立验证32项Node、2项Python页面契约、两份JS语法及diff检查通过。真实页面#19开关/键盘/刷新、#19↔#9任务切换、空项目往返、#20无权限提示通过；浏览器实际379×577无横向溢出，未声称宽屏与真实账号切换验证。详细证据见design-qa.md。
- 变更：web/workspace.js、web/app.js、web/index.html、tests/workspace_result_ui.test.cjs、tests/test_task_web_ui.py；Codex同步docs/guides/USER_MANUAL.md、docs/spec/MODULE_webui.md、design-qa.md、docs/PROGRESS.md、docs/PROGRESS_HISTORY.md。
- 受测版本已本地提交37d88c7，main未合并。gh查询PR返回HTTP401；随后git push被自动审批拒绝，理由为尚未明确授权把非公开代码/文档发送到具体远端https://github.com/bobo506/TALK.git。未推送、未创建PR、不通过其它渠道绕过；等待用户批准目的地。用户验收第一项后再处理第二项；在线状态误报与会议语义仍单列。

---

## 2026-09-09 收工汇总与任务页面两项待修反馈

- 用户要求“这两点先记下，下次再修改和继续测试，今天先汇总进度”。当前 Codex 为决策 Agent，本轮仅维护进度文档，没有派发新任务或开始修复。
- UI 待办 1：点击“查看成果”可展开反馈，但再次点击不能收起；用户希望再次点击同一按钮能折叠已展示内容。下次验证展开/收起切换和任务切换后的状态。
- UI 待办 2：点击“查看完整对话”进入任务对话页面后，右侧一列重复展示任务页已有信息；用户认为无需展示，要求移除该列。下次先提供布局预览，再实施并在真实浏览器中验证。
- 两项均来源于用户直接观察，本轮仅通过文本搜索确认相关入口位于 web/app.js 的任务按钮和 web/workspace.js 的成果展示逻辑；未打开浏览器复现，未修改页面，不声称修复或验证通过。
- 今日已完成：当前 Codex 的 TALK MCP 接入，以及任务 #20 向真实 DeepSeek 的委派、执行、返回、复核和收取；任务已 completed，临时 bridge 已正常退出。完整记录见下方试运行条目，本地提交为 0396f24。该试运行验证的是只读勘察，实际代码开发和返工仍待后续验证。
- 已确认后续分工：Codex 编写任务/复核/维护进度，DeepSeek 按单切片执行；模型跟随 DSH 保存的默认值。执行角色需读取最小必要项目与模块背景，不自动继承当前 Codex 整段对话。
- 其余未完成项：历史实例 idle/busy 导致角色可用状态误报；完整会议轮次隔离与原终端返回仍未开发，数据库约束方案须兼容 legacy discussion scope 和历史数据。
- 下一次从 main 恢复，先安排两项界面修复和真实测试；在线状态修复另列小片，会议合同继续由 Codex 收敛后再委派。后续派发前检查实际 bridge，不能仅依赖现有 available 标记。
- 变更仅 docs/PROGRESS.md、docs/PROGRESS_HISTORY.md；验证为文档差异检查，不重跑未改动的代码测试。原服务与用户 Harness 不作启停；数据库、密钥、用户配置、截图、日志和 .tmp 均不提交。本日文档提交暂留本地，未推送。

---

## 2026-09-09 当前 Codex 经 TALK 委派 DeepSeek 的首次真实试运行

- 用户确认 DeepSeek 暂时使用 DSH 保存的默认模型，并希望后续由 Codex 编写明确任务、通过 TALK 交给 DeepSeek 执行。Codex 继续承担决策、复核和进度维护；执行 Agent 一次一片。
- 用户在本机配置当前 Codex 的 TALK stdio MCP；实际发现八个工具。服务启动后，--check 和 talk_list_agents 均成功，派发身份为 human:bobo、项目为 prj_e8fe7066bbec。用户级配置和密钥不进入项目仓库。
- 用户授权“小任务试试水”。创建任务 #20「试运行：只读勘察会议轮次隔离」，范围为读取必需项目/讨论文档与相关代码、报告实际 cwd/main/a1b5cf3、三个带定位的发现和最小切片建议；禁止改文件、运行测试、启动服务和自行委派。
- 首次真实派发停在 queued/assigned。发现项目角色列表按保存的状态汇总，未判断 last_seen_at；最新历史 DeepSeek idle 心跳仍停在 2026-09-08。只读进程检查确认仅 Harness 在运行，TALK bridge 未运行。server/routes/projects.py 与 bridges/talk_task_tools.py 的 _availability 都只看状态；该问题未在本轮修复，旧的 available/busy 不能证明当前在线。
- 为完成已授权试运行，临时运行现有 run_bridge，固定实例 agent:deepseek:codex-smoke-task-20，使用现有成员与 dsh --profile headless；预检/任务沿用现有逻辑。14:39:57 UTC 领取，14:40:58 UTC 提交，真实执行约 61 秒。监督程序在任务提交后取消自身 bridge 并正常退出，没有终止用户服务或已有 Harness。
- DeepSeek 交回实际环境与三项缺口：Message 无直接会议字段，同群 active discussion 无唯一约束，已结束 discussion 仍可经 API 追加 turn。Codex 对照 models/discussions/db 复核，并在任务 Hall 补充：已有 message_id 普通索引；当前 discussion 也承载请求者局部 scope；消息归属唯一不能代替显式跨轮引用规则，草案须先做兼容性设计，尚未授权实施。
- 结果消息 #2491，复核消息 #2492；原请求者调用 talk_collect_result 后任务 #20 变为 completed，收取时间 14:41:58 UTC。确认委派 → 领取 → 真实模型读取项目 → 提交 → 本会话复核/收取的闭环通过。
- 验证：执行前后 git status 相同，无 tracked diff，原有未跟踪 .tmp 保留；未运行单元测试，未声称完成代码开发/返工、Kimi 调用、其它客户端接入或无人值守验收。Codex 随后只更新本快照/历史并检查文档差异。
- 后续建议：先评估修正历史实例误报在线，再收敛会议轮次与原终端请求合同。当前小任务已完成，不自动开始下一片。查看入口为现有 TALK 页面中的任务 #20。

---

## 2026-09-08 最终合并完成与头脑风暴方向交接

- 用户于额度中断后要求继续同一收尾任务；恢复时确认 2a1d007 已提交且工作区无已跟踪变更，没有重复开发或重复跑已通过测试。
- codex/th7-terminal-integration 已推送，PR #5「接入普通终端任务工具与只读连接检查」以 merge 合入 main，合并版本 f2237393d9e446a680d7ef727bad7315bf8ecc43。本地主工作区已切回 main 并快进，文件树与受测 2a1d007 完全一致。
- 本批链路：PR #3 → task-hall（3e2483d）→ PR #4 → main（541e668）；旧 PR #2 自动 merged；原 TH-7a 的 5781ee6 → cherry-pick 2a1d007 → PR #5 → main（f223739）。所有功能合并保留历史，不强推、不删旧工作树或分支。
- 验证沿用合并前已完成结果：稳定基线 383 项非 WebSocket + 10 项独立 WebSocket + 20 项 Node；终端切片 13 项独立测试及真实 --check 通过。单进程 WebSocket 阻塞及拆分验证限制保留在快照。此次恢复仅推送/合并及文档收尾，没有声称重新完成全部测试。
- 新增 docs/spec/BRAINSTORM_NEXT.md，准确记录用户确认的群聊统一头脑风暴、人工 / 原终端 Agent 主持、群复用、一群一活动轮、@所有人 开场/追问、明确汇总结束、迟到与引用消息隔离、会议结果回原终端等要求；标明尚未实现及待定实现细节。
- 同步 PROGRESS.md 当前 main 状态与下一步，PROJECT_BRIEF 增加最新约定入口。没有开始会议功能开发，没有安装用户级 MCP、发送群消息或变更真实运行数据。
- 下一窗口从 main 和这份产品约定恢复，先明确最小会议往返合同再开发。原 .tmp/th7-terminal-v1 仍停在旧 5781ee6，仅作原始记录，不能误作当前开发入口。

---

## 2026-09-08 稳定基线合并与 TH-7a 增量接入

- 用户确认群聊 Codex 回复及前述 UI 问题全部修正，并明确授权按“已验收分支链合入稳定基线 → 接入 5781ee6 → 单独验证再合并”收尾。
- PR #3 以 merge 方式合入 task-hall（3e2483d），再通过 PR #4 合入 main（541e668）；旧 PR #2 随其提交进入默认分支自动标记 merged，未丢弃历史或强推。
- 合并前稳定基线 383 项非 WebSocket Python 测试、10 项逐个独立进程 WebSocket 测试、20 项 Node 测试全部通过。首次单进程完整 discover 在 WebSocket 连接状态检查长时间阻塞，停止的仅是本轮测试子进程；拆分复测通过，未修改功能代码。日志仅保留 .tmp。
- 从 main 的 541e668 创建 codex/th7-terminal-integration，cherry-pick -x 原 5781ee6。功能代码无冲突，仅 PROGRESS / PROGRESS_HISTORY 有冲突，人工整合保留 UI 验收修复、TH-7a 原开发记录及最新产品决定。
- 集成后终端/任务工具 13 项通过；从其它工作目录以现有 QA 账号运行真实 --check，返回 ok=true，项目与 Codex / DeepSeek / Kimi 角色正确。没有创建生产任务、发送群消息、安装用户级 MCP 或操作现有 bridge。
- 下一步将此独立切片合入 main，然后补记最终合并版本与头脑风暴产品约定交接；本轮不开始新功能。原 5781ee6 分支及旧工作树保留，避免误清理本地资料。

---

## 2026-09-08 TH-7a：复制验收基线并完成普通终端接入入口

- 用户明确要求“先复制一个当前分支，然后在这个基础上先做一个最小开发切片”，原分支由用户明天验收合并。Codex 按已获授权的决策 Agent 开发一片后收尾。
- 从 `codex/ui-workspace-v1` 的已推送版本 `6affa86f2c2db0b3d011e7db2f5e5cf49b0ad5ba` 创建 `codex/th7-terminal-v1`，独立 worktree 为 `D:/claude-test/TALK/.tmp/th7-terminal-v1`。原目录继续保持原分支，原 PR #3 和浏览器页面未改动。
- 新增 `bridges/talk_terminal_mcp.py`：任意工作目录可通过绝对路径启动；服务/项目来源按显式参数、环境变量、已有 `.talk/project.yaml` 排序；要求项目与环境密钥，忽略继承的成员身份提示。输入、输出、错误统一 UTF-8。
- 新增 `--check`，只读核对成员身份、项目角色和可用状态，结果不打印密钥；配置缺失、非法地址、无效 YAML、HTTP 错误与连接错误通过退出码和 stderr 反馈。
- 复用原 MCP 循环和八个 HTTP 任务工具；给原循环添加默认开启的延迟发送开关。独立入口关闭 `talk_send` 的目录展示与调用，防止登记无人回收的延迟消息；原 bridge 九工具合同保持兼容。
- `python -X utf8 -m unittest tests.test_talk_terminal_mcp tests.test_talk_task_tools -q`：13 项全部通过，其中新入口 8 项、既有工具 5 项。隔离真实 HTTP 服务 + MCP 子进程覆盖中文/空格目录、只读检查无写入、错误诊断、工具目录及委派→提交→查询→收取；目标角色执行由测试 API 模拟，没有消耗模型额度或写入生产数据。
- `--help` 与 `git diff --check` 通过。没有重跑无关 Web 或全量后端测试；没有声称已完成具体桌面客户端安装或真实模型验收。
- 变更文件：`bridges/talk_terminal_mcp.py`、`bridges/talk_send_mcp.py`、`tests/test_talk_terminal_mcp.py`；接入指南 `docs/guides/TERMINAL_MCP.md` 与快速开始链接、任务模块、简报、进度快照与本历史。
- 本轮只提交新分支的局部代码与文档，未推送新分支、更新旧 PR、合并或修改用户级 MCP 配置。本片是 TH-7 的技术接入入口，完整客户端接入里程碑留待下一片。
- 下一步：用户先验收合并原界面分支，再对齐新分支到稳定基线；如使用 squash，基于 `6affa86` 仅迁移本片增量。随后确认具体客户端安装与一次真实委派流程。


---

## 2026-09-08 Codex 普通终端 PATH 补修

- 用户重启后群聊仍报错。只读检查最新实例确认进程已更换，但 stderr 仍为 Codex 0.144.4 / gpt-6-astra HTTP 400。核对启动命令没有显式 CLI 覆盖；普通终端的持久化 PATH 缺少 Desktop 的原生 CLI 目录，而 Codex 应用工具环境包含它。
- 修正上批验证遗漏：Windows 在 PATH 没有可用原生 exe 时，进一步查找当前用户 LOCALAPPDATA/OpenAI/Codex/bin 下根目录及一层版本目录中的 codex.exe，按文件更新时间选择；空/不完整/不可读安装安全回退。PATH 原生 CLI 和显式命令的优先级不变，不修改系统 PATH、不安装或更改模型。
- 启动时向 stderr 输出 `[Codex bridge] CLI:` 和实际可执行文件，便于用户确认加载情况，不输出完整命令或凭证。
- 两份 bridge 测试 137 项通过，新增普通终端查找、多个安装/不完整目录与缺失/不可读目录回归；diff 检查通过。使用用户 bridge 同款 Python 3.12，移除 Desktop PATH，真实调用找到原生 0.153.4 并返回 TALK_ORDINARY_TERMINAL_OK，退出码 0。
- 没有发送真实 TALK 消息、操作群成员或终止用户进程。用户需再重启一次 bridge 加载本次补丁；群聊回复仍待复验。变更仅 codex_bridge.py、对应测试、bridge 模块与快照/历史；不推进 TH-7。

---

## 2026-09-08 群聊验收修复与 Codex CLI 兼容

- 用户已人工验收任务 #19：DeepSeek 回复“验收通过”，查看成果并确认后状态变为完成。此前 #15/#16/#17/#18 的完成基线继续保留。
- 按本轮反馈修复同一 UI 分支：创建和添加群成员只列当前项目角色与其他真人账号，排除当前账号、禁用成员；旧 pi / pi-kimi 不属于当前项目角色，不再作为邀请候选，没有删除历史成员。当前登录 QA Tester，bobo 是另一个账号，归入“其他用户”。创建者继续由服务端自动入组。
- 邀请、成员列表与 @ 候选统一简短名称；人工昵称保留，@ 候选排除自己，实际插入的成员 ID 和路由协议不变。右侧合并为一份“群聊成员”，展示人数、职责与在线状态；添加表单可展开/收起，管理按钮再显示角色设置、移除与删除群聊。修复旧 CSS 强制隐藏添加表单的问题。
- Codex 真实失败原因：PATH 优先找到 npm CLI 0.144.4，模型 gpt-6-astra 返回 HTTP 400，要求新版 CLI。Windows 默认命令改为优先 PATH 内原生 codex.exe（排除 WindowsApps 别名），保留用户显式命令与环境配置。现有原生 CLI 0.153.4 使用相同模型实际返回 TALK_CODEX_PROBE_OK；未改变模型或执行权限参数，也没有代发 TALK 群消息。
- 群聊 CLI 失败时，实例 last_error 记录清理后的 stderr（回退 stdout / 通用提示），最多 4000 字符；群内继续显示简短错误，便于定位原因。
- 验证：Node 20 项、Python 页面与两类 bridge 137 项通过；JS 语法及 git diff --check 通过。内置浏览器验证新建邀请候选、@ 候选/插入、管理折叠、添加表单展开收起、1440px 桌面与 390px 无横向溢出；控制台未捕获错误。未提交真实成员增删或新群聊，未替用户重启现有 bridge；真实群聊回复仍需重启 Codex bridge 后复验。
- 变更文件：web 下 5 份页面/样式/脚本、两份 bridge、4 份测试、Web/bridge 模块文档、用户手册、design-qa.md 和进度快照/历史。资源版本 20260908-members-2。临时截图只保留本地，不提交数据库、日志或聊天内容。
- 并行分支连续性：此前按用户要求复制到 .tmp/th7-terminal-v1，分支 codex/th7-terminal-v1，提交 5781ee6，已完成普通终端 MCP 入口与连接检查，13 项测试通过，尚未推送。当前修复仅在 codex/ui-workspace-v1；待 UI 验收合并后再对齐 TH-7，避免混入当前 PR。
- 下一步：用户刷新页面并重启 Codex bridge，复验群聊后收尾 PR #3；暂不开始桌面客户端或下一个功能切片。

---

## 2026-09-08 界面批次公开推送与 PR 收尾

- 用户明确回复“可以推送，然后下一步做什么”，授权将前述界面代码、测试及相关文档公开推送到 `bobo506/TALK` 的 `codex/ui-workspace-v1`。本次自动审批通过，无需更改 GitHub 权限或本机审批策略。
- `git push -u origin codex/ui-workspace-v1` 成功，`git ls-remote` 核对功能 head 为 `df3877a4eae32914eb2a47ac239068fccd77a620`。临时截图、数据库、验收标记与本地辅助文件没有进入提交。
- 创建中文 PR #3「简化任务、群聊与角色工作台并修复上下文串用」：`https://github.com/bobo506/TALK/pull/3`，head `codex/ui-workspace-v1`，base `codex/task-hall`；创建时包含 5 个前置界面提交、12 个文件。
- `gh pr list` 返回鉴权 401，使用已有 GitHub 连接器完成查询与 PR 创建。没有要求用户重新登录或改变权限；Git 推送正常。
- 分支核对：远端 `main` 为 `6e8fcec`，`codex/task-hall` 为 `b15be87`，后者领先主分支 64 个提交。旧 PR #2 仍 open，其 head `1da4797` 已被 `codex/task-hall` 包含。没有合并分支、关闭旧 PR 或开启新切片。
- 下一步建议：先检查前置分支链，在集成分支完成完整回归与真实新建任务到完成、普通群聊创建/收发验收，再统一合入 `main`，之后确定 TH-7 的最小切片。当前只补记进度，不重跑此前已通过测试。

---

## 2026-09-08 群聊导航切片

- 用户明确要求在任务和角色之间增加“群聊”标签，点击显示群聊房间列表，并移除底部“对话与房间”。额度中断后继续同一切片，未重启其它 Agent 服务或另开切片。
- 左侧统一“任务 / 群聊 / 角色”；复用现有普通群聊、成员管理、消息搜索与收发。群聊只列当前项目和历史无项目普通房间，任务专属对话保留在任务详情“查看完整对话”。移除旧列表及全局消息流的前端入口，没有删除历史数据或后端 API。
- 群聊标签恢复最近可进入的普通房间，否则选首个可进入房间；没有房间则显示空状态，不请求/发送旧全局消息。新增群聊携带当前项目，创建后进入新房间；新建弹窗关闭时恢复入口焦点。
- 任务、群聊、角色各自显示对应列表与内容。历史加载、轮询、分页和分批渲染绑定房间/账号/时间线版本，切换后丢弃迟到响应，避免旧房间消息混入新房间。
- 验证：Node 17 项通过（含群聊过滤、无全局回落、旧房间响应隔离、创建项目归属与导航），Python 页面契约 2 项及群聊创建/项目关联 2 项通过；JS 语法与 diff 检查通过。
- 真实浏览器验证：现有 test-run20 群聊、搜索空结果、新建弹窗/Escape/焦点恢复、任务 #9 完整对话、角色页不显示旧列表、群聊刷新、768px 与 390px 无横向溢出；控制台无捕获错误。真实项目中未创建房间或发送消息；没有声称完成浏览器真实创建提交或完整聊天回归。
- 变更文件：`web/index.html`、`web/app.js`、`web/workspace.js`、`web/workspace.css`、两份 UI 测试、项目简报、Web UI 模块、用户手册、快照/历史与 `design-qa.md`。静态资源版本 `20260908-chats-1`，截图仅保留 `.tmp/group-chat-20260908/`。
- 同一 `codex/ui-workspace-v1` 分支本地提交；此前公开推送审批仍待明确授权，本轮没有重试推送或创建 PR。等待用户验收本次导航，不继续 TH-7。

---

## 2026-09-07 UI-WORKSPACE-1 验收微调：默认显示密度 80%

- 项目管理者已查看双栏版本，表示唯一需要调整的是页面内容大小，浏览器缩放到原来的 80% 较合适。
- `web/workspace.css` 对宽度至少 701px 的桌面界面统一缩放为 0.8，并补偿页面、工作台和弹窗视口高度；窄屏保留现有尺寸。没有修改信息内容、数据或操作流程。
- 资源版本更新为 `20260907-density-1`；在浏览器 100% 下即可查看新密度，避免与用户原先的 80% 浏览器缩放叠加。
- 浏览器实测 1488×1056：标题栏 70→56，搜索框 44→35.2，标题行高 42→33.6，工作台仍铺满窗口；弹窗 496px 宽且遮罩覆盖视口。769px 角色页无横向溢出，390px 的缩放仍为 1、搜索框仍为 44px。
- 页面契约 2 项通过，diff 检查通过；未重复无关后台回归。截图在 `.tmp/workspace-density-20260907/`，仅保留本地。
- 本次变更文件：`web/workspace.css`、`web/index.html`、`tests/test_task_web_ui.py`、进度快照/历史、Web UI 模块、`design-qa.md`。同分支本地提交；前次公开推送审批仍待明确授权，本轮没有重试推送。

---

## 2026-09-07 UI-WORKSPACE-1：任务 / 角色双栏工作台

- 用户在界面审计后要求先看预览，确认“任务要求”保留原始目标/限制/完成标准、普通页面移除技术详情，并增加同级“角色”入口。任务与角色两张预览获得确认后，用户授权开发一个切片；额度中断后本轮继续验证收尾。
- 从 `f60c077` 创建 `codex/ui-workspace-v1`。新增 `web/workspace.js`、`web/workspace.css`，调整页面骨架及现有 JS 事件；没有改变 API、数据库、bridge 或 TH-6d 任务状态。
- 任务模式仅在左侧列主任务，支持全部/进行中/待我处理/已结束筛选与搜索；右侧显示负责人、状态、成果入口、分工流转及默认折叠的原始任务要求。子任务从流转中进入，可返回主任务。
- 角色模式读取当前项目配置，展示职责、实际参与任务和工作状态，支持过滤、任务跳转、交办时预选该角色。统筹者已归入根任务的委派子项不重复占据角色列表。
- 修复跨 Hall/任务/项目/账号的异步树响应污染，树按钮执行前验证根归属，异步操作完成不抢回用户当前选择；完成态不显示暂停/终止。成果访问失败在详情内可见，静默刷新不抹除提示或无故重建未变化的页面。
- 实际浏览器覆盖：#15→左侧 Hall #9、#9 文本成果、受限 #15、角色预选/搜索/筛选、空项目、子任务返回、Escape/焦点。390px 与 769px 无横向页面溢出，手机标题栏遮挡修复并复测。生成预览与实现分别同输入并列核对，未将不同任务的示例文案写入真实数据。
- 验证：`node --check web/app.js`、`node --check web/workspace.js`；`node --test tests/workspace_ui.test.cjs` 11 项通过；Python 页面契约与两条任务工作流共 4 项通过。没有重跑完整后台回归，也没有在真实项目中提交测试任务或消息。
- 变更文件：`web/index.html`、`web/app.js`、`web/workspace.js`、`web/workspace.css`、`tests/test_task_web_ui.py`、`tests/workspace_ui.test.cjs`、`design-qa.md`、本快照/历史、Web UI 模块、项目简报、用户手册。
- 本地服务在中断后重启，最终保留内置浏览器预览。已有 API Key 可登录；仅验收已完成任务视图无需启动其它角色的 bridge。截图/生成图/临时验收文件不进入公开提交。
- 提交 `15874ba` 已完成；推送 `origin codex/ui-workspace-v1` 被 Codex 自动审批拒绝，理由为缺少本次具体内容与公开目的地的明确授权。没有绕过拦截、修改权限或创建 PR；等待项目管理者明确授权后继续远端同步。
- 待验收：双栏信息层级与易读性。创建弹窗仍保留高级任务配置术语，角色页不是进程管理器；下一轮如需继续简化，先确认弹窗方向。TH-7 暂缓。

---

## 2026-09-06 面向非编程使用者的界面评估

- 用户在 TH-6d 验收后要求重新评估界面：减少无意义数据，让非编程人员看懂任务转交、完成状态和下一步；中断后继续本次评估。TH-7 在界面方向明确前暂缓，具体布局尚未批准。
- 使用 Product Design audit 与项目进度框架完成 5 步真实浏览器审计：窄窗口总览、桌面总览及 #15 详情、创建弹窗、受限成果入口、可访问的 #9 Hall。原始截图与完整报告在 `.tmp/ui-audit-20260906/`，仅保留本地。
- 优先缺陷：从 #15 黑板经侧栏进入 #9 Hall，详情更新为 #9，门禁仍显示上一任务树 #16 的 Review/Test。源码确认 getContextTask 与 selectedTaskTree 使用不同上下文，树按钮可能指向旧任务；未执行控制操作验证服务端结果。
- 其它问题：完成态仍显示 active/暂停/终止；非成员 Hall 在侧栏禁用但详情入口仍可点，点击后无可见反馈；主子任务平铺；技术字段、重复 Hall 列表与空列挤占空间；769px 详情横向截断。创建弹窗底色与焦点显示良好，Escape 可关闭，但焦点未返回入口。
- 建议按“先修状态及操作一致性，再做总览/详情/创建三屏简化”推进。主任务组织工作，子任务展开查看；成果与下一步优先，内部 ID/租约/epoch 收入技术详情。必须保留提交、验收、收取、整体完成的真实语义，不能隐式扩大委派授权。
- 本次只读页面导航及源码核对，无产品代码、任务、消息或授权额度变更；恢复原始浏览器尺寸并返回 #15 黑板。没有重跑功能全量测试或宣称完整无障碍合规。
- 分支状态核对：远端补充推送记录 b15be87 已成功，codex/task-hall 相对 main ahead 64/behind 0，未查到 PR、尚未合并；TH-6d 仍为已验收基线。此次仅维护两份进度文档与本地审计产物，未发布截图。
- 下一步：评审简化方案并制作可点击原型；代码开发按前端交互切片推进。

---

## 2026-09-06 公开推送授权与远端核验

- 项目管理者针对上一轮说明的公开仓库 `bobo506/TALK`、`codex/task-hall` 分支和 5 份验收收尾文档明确回复“推送吧”。
- 重新执行 `git push origin codex/task-hall` 成功，远端从 `dd1f682` 前进至 `272b50b`（完成 TH-6d 人工验收与任务树收尾）。
- `git ls-remote origin refs/heads/codex/task-hall` 返回 `272b50bab74ab62f6f01e9181d5826bfa0baa4d4`，与本地 HEAD 一致；tracked 工作区干净，仅保留 V1/V2 两个 untracked 验收产物。
- 更新 `docs/PROGRESS.md` 与本历史记录，清除已解决的推送待授权状态；本轮仅补记推送结果，不修改代码、不重跑已通过测试、不进入 TH-7。
- 上轮拒绝来自 Codex 自动审批，GitHub 账号和仓库权限已足够；本轮未修改 GitHub 权限、仓库可见性、Codex 审批策略或项目长期授权规则。此次授权仅记录为本次验收文档及其推送收尾。

---

## 2026-09-06 TH-6d 人工验收通过与根任务收尾

**角色与授权**：当前 Codex 为 `AGENTS.md` 指定的决策 Agent。项目管理者确认“16，17，18都是已完成的状态，已验收，继续收尾”，本轮完成既有里程碑收尾，不开启 TH-7。

**人工验收核对**：

- 本轮恢复时 `http://127.0.0.1:8000` 无服务响应；项目管理者启动 TALK Server 后，`GET /healthz` 返回 `status/db/storage=ok`。
- 页面人工验收由项目管理者完成；SDK/API 核对根任务 `#15` 从此前的 `awaiting_human/milestone` 变为 `active`、`checkpoint_reason=null`、`authorization_epoch=2`。
- Review `#17` 仍为 `approved`，Test `#18` 仍为 `passed`、`satisfied=true`，冻结集为 `[16]`；Development `#16`、Review `#17`、Test `#18` 都已 `succeeded/completed`。本轮没有重新调用人工验收接口。

**根任务最终收尾**：

- 沿用 `agent:codex` 与 `codex-desktop-th6d-v2`，通过正式 SDK/API 重新领取根任务 `#15`（attempt=`2`），在原 Task Hall 写入最终汇总消息 `#2480`，提交为 `succeeded/submitted`。
- 依据项目管理者本次验收及收尾授权，以原请求者 `human:bobo` 身份调用结果收取接口；根任务最终为 `succeeded/completed`。
- 最终任务树 `#15/#16/#17/#18` 全部为 `succeeded/completed`；运行中和非终态后代均为 `0`，剩余开发切片额度为 `0`，最新 Review/Test 门禁保持有效。
- 根任务的 `control_status=active` 表示人工验收检查点已释放，不表示根任务仍运行；完成状态以 `status/workflow_status` 为准。Codex Desktop instance 回到 `idle`。
- 本轮未启动或重跑其它 Agent bridge，未新增子任务、未扩大开发授权；旧失败任务和 V1/V2 两个 untracked 验收文件保留。

**验证**：

- `.venv\Scripts\python.exe -m unittest tests.test_tasks.AgentTaskTests.test_passed_milestone_test_pauses_for_human_acceptance_before_root_completion tests.test_tasks.AgentTaskTests.test_task_workflow_clarification_accept_submit_and_collect -q` → `Ran 2 tests in 1.219s`，`OK`。覆盖里程碑人工验收后根任务重新领取和提交、结果收取及请求者权限。
- V2 产物重新核对：65 bytes、UTF-8 无 BOM、LF、SHA-256=`602FBC88D523943F2798942F0F898B354834372C1BC53AEECBF3233FAC2743DF`，通过。
- 真实 SDK/API 完成根任务提交、收取与最终树断言；没有直接修改数据库状态。
- 文档检查：5 份变更文件 UTF-8 正常，16 个本地 Markdown 链接有效，进度快照少于 90 行；`git diff --check` 通过。
- 2026-08-27 的 `389` 项全量回归与 Kimi `119` 项独立定向回归为既有通过证据，本轮未重跑全量回归。本轮无代码或前端交互改动，浏览器验收由项目管理者完成。

**文档同步与变更文件**：

- `docs/PROGRESS.md`：替换等待验收快照，记录最终状态、角色、证据、边界与 TH-7 建议。
- `docs/PROGRESS_HISTORY.md`：归档本轮授权、验收、收尾与验证事实。
- `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_tasks.md`：TH-6d 状态同步为人工验收通过，保留完整浏览器 Tester 等未完成边界。
- `docs/guides/USER_MANUAL.md`：说明人工验收解除检查点后，根负责人提交最终汇总、根请求者收取结果的既有流程，不把人工验收等同于自动提交根结果。

**提交与推送限制**：已创建本地验收收尾提交。首次推送被自动审批以未验证目标归属为由拒绝；随后通过只读 GitHub API 确认登录账号与仓库 owner 均为 `bobo506`，admin/push 权限为 true。补齐证据后再次审批仍拒绝，理由为目标 `bobo506/TALK` 是公开仓库，本轮 5 份项目进度、模块和用户手册文档的公开披露需要用户明确授权。未通过其它通道绕过；待项目管理者明确授权后再推送 `codex/task-hall`。

**待确认与下一步**：TH-6d 无待验收问题；剩余收尾事项为取得上述公开推送授权并核对推送结果。TH-7 尚未启动，后续再确认 Codex Desktop / 通用终端接入包装的最小范围。完整浏览器 Tester 能力、操作系统级硬隔离、Kimi 会话策略与既有技术债继续保留。

---

<!--
项目根：d:\claude-test\TALK
最后更新：2026-09-06 TH-6d 收尾文档公开推送成功并核对远端

## 2026-08-27 TH-6d 原生三 Agent V2 自动门禁通过，等待人工验收

**目标**：在 Kimi prompt mode 参数修复提交 `921fbb1` 上，用当前 Codex Desktop 会话作为 Lead、DeepSeek Harness 作为 Dev、官方 Kimi Code CLI 作为 Reviewer/Tester，重新执行一棵不复用旧失败任务的完整验收树。

**运行拓扑**：

- TALK Server：`http://127.0.0.1:8000`
- Lead：当前 Codex Desktop 会话，以 `agent:codex` SDK/API 身份协调；没有启动额度耗尽的嵌套 Codex bridge。
- Dev：`agent:deepseek`，DeepSeek Harness bridge。
- Reviewer/Tester：`agent:kimi`，官方 Kimi Code CLI `0.38.0`，`review` 工具档。
- 项目档案同步结果精确为 `agent:codex / agent:deepseek / agent:kimi` 三个活动成员。

**任务树与证据**：

- 根任务 `#15`：`TH-6d 三 Agent 验收 V2（Kimi Code）`，`may_delegate=true`、里程碑 Test 必需、授权批次仅 1 个 Development 切片。当前 Task Hall 为 `group:task-2d0cf86216b742f3adc157a3695ebeef`。
- Development `#16`：DeepSeek 只创建 `.tmp/th6d-native-kimi-acceptance-v2.txt`，未改 tracked 文件；任务结果消息 `#2476`。文件为 65 bytes、UTF-8 无 BOM、末尾 LF，SHA-256 为 `602FBC88D523943F2798942F0F898B354834372C1BC53AEECBF3233FAC2743DF`。
- Review `#17`：Kimi 原生 bridge 真实领取并完成，relation `reviews -> #16`；独立核对三行内容、编码、字节、哈希、Git 状态和 Development 结果消息，门禁 `approved`、`findings=[]`，结果消息 `#2477`。
- Test `#18`：Kimi 原生 bridge 真实领取并完成，relation `tests -> #16`；独立运行 `119` 项 Kimi/通用 bridge 定向回归，`1.052s`、`OK`，并完成 marker/Git/Review 黑盒核验，门禁 `passed`、`findings=[]`，结果消息 `#2478`。
- Lead 在根 Task Hall 写入汇总消息 `#2479`，明确自动门禁通过但不代替项目管理者宣告里程碑完成。

**服务端门禁状态**：

- Review gate 当前 verdict=`approved`，覆盖冻结 Development `#16`。
- Test gate 的 `frozen_task_ids=[16]`、verdict=`passed`、`satisfied=true`。
- 根任务 `#15` 已自动撤销 Lead claim 并进入 `control_status=awaiting_human`、`checkpoint_reason=milestone`；这是预期的人工作业门禁，不是失败或阻塞。
- Test `#18` 已由 Lead 收集为 `succeeded/completed`；当前 Codex Desktop instance 回报 `idle`。

**额外验证**：修复后 Lead 全量回归为 `389 tests in 170.772s`、`OK`；Kimi 独立定向回归为 `119 tests in 1.052s`、`OK`。

**待人工验收**：打开 `http://127.0.0.1:8000`，进入任务 `#15`，检查三项子任务与质量门禁后点击“人工验收通过”。当前 Server、DeepSeek bridge 与 Kimi bridge 保持运行；V1/V2 两个 `.tmp` 验收文件保持 untracked，不进入 Git。

---

## 2026-08-27 Kimi Code prompt mode 参数修复与首次真实验收中断收尾

**背景**：项目管理者完成 Kimi Code 登录后，启动 `agent:codex / agent:deepseek / agent:kimi` 原生拓扑执行 TH-6d 真实验收。第一次任务树为根任务 `#12`、Development `#13`、Review `#14`。

**真实验收结果**：

- DeepSeek 真实领取并完成 `#13`，结果消息 `#2473`；生成 `.tmp/th6d-native-kimi-acceptance.txt`，内容为三行受控 marker，UTF-8 无 BOM、CRLF、61 bytes，SHA-256 为 `CC4B2278EDFEB377BA3B32575BBE8168D66F2F8F311D5E48612C52116F897B3F`。
- Kimi 在 `#14` 领取前预检阶段连续三次安全失败，错误为 `Cannot combine --prompt with --auto.`，结果消息 `#2474`；任务没有被误认领，证明领取前门禁按设计止损。
- 根任务 `#12` 随后因嵌套 Codex CLI workspace 额度耗尽失败，结果消息 `#2475`。该失败属于运行额度限制，不是 TALK 协议、Kimi 登录或 DeepSeek 执行缺陷；旧树保留现场，不再复用。

**根因与修复**：

- Kimi Code CLI `0.38.0` 的 prompt mode（`-p/--prompt`）本身就是非交互执行，并明确拒绝与 `--auto` 同时使用。
- `bridges/kimi_bridge.py` 的默认命令移除 `--auto`；讨论、预检与任务执行的能力边界继续由临时 Agent 文件的工具白名单控制。
- `tests/test_kimi_bridge.py` 增加反向锁定，确保所有 prompt mode 命令都不含 `--auto`；`docs/spec/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 同步真实 CLI 合同。
- 使用临时 Read-only Agent 文件执行真实 Kimi 工具调用，成功读取受控 marker 并返回 `KIMI_PROMPT_TOOL_OK`，退出码为 `0`；临时 Agent 文件随后删除。

**验证**：

- `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q` → `Ran 119 tests in 0.913s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q` → `Ran 389 tests in 170.772s`，`OK`。
- `py_compile` 与 `git diff --check` 通过；仅有 Windows LF/CRLF 提示。

**恢复决策**：新的干净验收树不再启动嵌套 Codex bridge，由当前 Codex Desktop 会话直接以 `agent:codex` Lead 身份通过 SDK/API 协调 DeepSeek 与 Kimi。Test 门禁通过后保留 `awaiting_human`，等待项目管理者人工验收。

---

## 2026-06-07 5.7+ 对话质量打磨 + PROJECT_INTEGRATION 长期方向沉淀

**背景**：5.x 主线在 6/2 ship 之后，黑盒发现 agent-to-agent 对话仍有质量问题（pi 自称 "qa"、pi-kimi 把名字拆成 "pi 和 kimi"、双向 "已经XX啦" 汇报体循环）。本轮针对这些问题做三次迭代修复，最终在 `group:1488c22048e3` (test-run17) 上验证对话自然收敛。同时把 ClawSwarm / OpenClaw Control Center / Multica 三份对比报告的启示整理成 `docs/spec/PROJECT_INTEGRATION.md`，作为 5.x 关闭后下一阶段的长期方向草案。

### Prompt 与对话质量（三次迭代）

| 迭代 | 改动 | 解决的问题 | 副作用 |
|------|------|-----------|--------|
| 第一次 | per-call prompt 加 "你是 {member_id}（完整 ID，不要拆解为多个名字）。" 独占首行 | 身份混乱、连字符 ID 拆解 | pi 陷入 "自我介绍" 模式，任务被淹没 |
| 第二次 | 改紧凑内嵌："你是 {member_id}。{sender} 对你说：{task}" 同一行 | 任务动词重新获得焦点；身份锚仍有效 | 元叙述 "已经XX啦" 双向循环汇报仍出现 |
| 第三次 | 废弃 pi/codex 分支的 `discussion_context` 注入；`FUNCTION_CALLING_SYSTEM_PROMPT` 加反元叙述规则 | 元叙述循环汇报根治 | 残留：visible reply + talk_send 双通道下偶尔有凑数 visible（治本在 PROJECT_INTEGRATION §9.3 结构化块） |

### 涉及代码改动

- `bridges/cli_bridge.py` `build_cli_prompt` + `build_cli_task_prompt` 紧凑身份注入，废弃 discussion_context 在 pi/codex 分支
- `bridges/cli_bridge.py` `FUNCTION_CALLING_SYSTEM_PROMPT` 增加反元叙述规则
- `bridges/talk_tools_extension.ts` `talk_send` promptGuidelines 增加 "用自己 member_id 身份写 body"
- `tests/test_cli_bridge.py` 翻转 4 处旧的 `assertNotIn("agent:pi"…)` 断言为 `assertIn`；新增 inline 身份注入测试 + task path 身份测试；两个老测试（scope_text / requester_id 断言）改为锁定 "不应在 prompt 里"
- `tests/test_codex_bridge.py` 同步翻转 2 处旧断言

### 文档

- `docs/spec/INTERACTION_FRAMEWORK.md` §5.3 表格修正（身份从系统层挪到单次调用层）+ 增加 2026-06-06 三次修正备注
- **新增 `docs/spec/PROJECT_INTEGRATION.md`** — TALK 基础设施化方向设计草案

### 黑盒验证

测试群：`group:1488c22048e3` (test-run17)，pi 0.78.0，人类指令：`@agent:pi 去跟 agent:pi-kimi 打个招呼`

**验收结论**：
- ✅ pi 自称 "pi"（无 qa 幻觉）
- ✅ pi-kimi 自称 "pi-kimi" 整体识别（无拆解）
- ✅ 无双向 "已经XX啦" 循环汇报
- ✅ 整体语气像两个有思想的人在交流兴趣点
- ⚠️ 残留小问题：pi 对 human 报告 "已经向 pi-kimi 发送了问候"（可接受）；第二轮 talk_send 后 visible reply 凑数（治本待 §9.3 结构化块）

### 单测验证

- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：81 tests 通过

---

## 2026-06-02 黑盒复测：agent-to-agent 通信端到端验证

**背景**：Pi extension dispatch 根因定位与规避完成后，按 PROGRESS.md 下一步执行完整黑盒复测。

**测试环境**：
- TALK Server `127.0.0.1:8000`，群 `group:88f99bd38f3f` (test-run16)
- pi CLI v0.78.0 (Google provider)，bridges 以 `--no-extensions --extension talk_tools_extension.ts` 启动
- Bridges 在线: agent:pi + agent:pi-kimi；agent:codex 未安装（跳过）

**Case 1: `@agent:pi 去跟agent:pi-kimi打个招呼`** ✅ PASS
- agent:pi 通过 `talk_send` 工具向 agent:pi-kimi 发送问候
- 多轮交互共 7 turns，Session #78 status=resolved, max_rounds=2
- 账本: demand=1 (greeting), reply=6 (answer×4 + closure×2)

**Case 2: `@agent:codex 通知 agent:pi 项目进度已更新`** ⚠️ SKIP
- codex CLI 未安装于本环境，非代码缺陷

**Case 3: `@agent:pi 问 agent:pi-kimi 它现在忙不忙`** ✅ PASS
- agent:pi `talk_send` → agent:pi-kimi 回复"不忙，暂时空闲"
- 5 turns, Session #79 max_rounds=2 正确限制
- 账本: demand=2, reply=3, round_index max=2

**验证**：
- Agent-to-Agent 消息: 12 条（from_id 含 agent:pi/agent:pi-kimi, to_ids 含对方）
- discussion_turns: demand=3, reply=9（turn_kind 同时出现）
- round_index 刹车正确: max=2，达到上限后自动 closure
- `--no-extensions` 规避方案在 pi 0.78.0 下有效

**结论**：5.x agent-to-agent 通信主线关闭。方案 D 端到端验证通过。

---

## 2026-06-02 Pi extension dispatch 根因定位与规避（plan-mode 工具覆盖）

**背景**：pi bridge 注册的 `talk_send` extension 工具从未被 LLM 调用，四轮黑盒/探针/源码插桩后定位根因并修复。

**根因**：pi 自带的 `plan-mode` 扩展 (`@earendil-works/pi-coding-agent/extensions/plan-mode/index.ts:343-345`) 在 `rebindSession` 事件回调里无条件 `pi.setActiveTools(NORMAL_MODE_TOOLS)`，全量替换当前激活工具集，抹掉 `talk_send`。

**修复**：
1. `bridges/pi_bridge.py` `DEFAULT_PI_COMMAND` 与 `DEFAULT_PI_TOOLS_COMMAND` 均追加 `--no-extensions`，禁用自动发现扩展（含 plan-mode）；`--extension` 显式加载不受影响
2. `tests/test_pi_bridge.py` 新增两条断言确保两档命令均含 `--no-extensions`
3. `docs/spec/INTERACTION_FRAMEWORK.md` 新增 §6.5 Pi runtime 工具覆盖陷阱与规避、§6.6 Windows MCP UTF-8 强制、§6.7 Codex 非交互 MCP approval 闸门
4. Upstream issue 提交至 `earendil-works/pi`，含复现步骤、源码定位、推荐修复

**验证**：py_compile 通过，79 tests 通过，echo_tool 探针确认规避方案有效。

---

## 2026-06-02 codex MCP approval / UTF-8 修复

**背景**：Codex 非交互 `exec` 默认取消 MCP tool call，Windows 下 MCP 子进程需显式 UTF-8 环境。

**修复**：
1. `bridges/codex_bridge.py` 默认命令追加 `--dangerously-bypass-approvals-and-sandbox`
2. 默认 MCP 配置追加 `env.PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`
3. `tests/test_codex_bridge.py` 新增覆盖 approval bypass、UTF-8 env、per-call TALK_* 不 hardcode

**验证**：py_compile 通过，13 tests 通过，独立 probe 确认 talk_send MCP 可写入 TALK_DEFERRED_FILE。

---

## 2026-06-01 codex MCP 路径集成（方案 D 延续）

**背景**：方案 D 已为 pi 建立了 JSONL + env-var 契约（`talk_tools_extension.ts`），codex 需要同等能力但用 MCP server 替代 TS extension。

**改动点 1 — 新增 `bridges/talk_send_mcp.py`**：
- 最小 stdio MCP server（裸 JSON-RPC 2.0 over stdin/stdout，~140 行）
- 暴露 `talk_send` 工具，从 `os.environ` 读取 TALK_DEFERRED_FILE / TALK_GROUP_ID / TALK_API_KEY
- 把 `{tool:"talk_send", target, body, stance, group_id}` 追加到 JSONL，返回"talk_send 已登记"
- 协议支持 MCP initialize / tools/list / tools/call，codex CLI 通过 `-c mcp_servers.talk_send.*` 配置连接

**改动点 2 — 修改 `bridges/codex_bridge.py`**：
- `run_bridge` 注入 `TALK_API_KEY` / `TALK_BASE_URL` / `TALK_MEMBER_ID` 环境变量（类比 pi_bridge:63-66）
- `default_codex_command()` 拆为 discussion（read-only sandbox）和 tools（workspace-write sandbox）两档，均注册 talk_send MCP server
- 新增 `--codex-execution-profile {discussion,tools}` 参数，默认 discussion
- Windows 下自动检测 Codex CLI 路径（AppData/Local/OpenAI/Codex/bin/codex.exe）

**改动点 3 — 修改 `bridges/cli_bridge.py`**：
- `build_cli_prompt` / `build_cli_task_prompt` 的 codex 分支从 v0 文本协议切换为 function-calling 祈使句风格
- 条件从 `runtime == "pi"` 扩展为 `runtime in ("pi", "codex")`
- 移除了 DISCUSSION_PROTOCOL_INSTRUCTIONS 中 v0 文本协议教学对 codex 的注入（execute_talk_actions 保留作兜底）

**改动点 4 — 保留 `execute_talk_actions`**：不动，作为文本协议兜底兼容。

**改动点 5 — 新增测试**：
- `test_codex_deferred_talk_send_via_mcp_equivalent_to_pi_path`：用 fake CLI 模拟 codex spawn MCP 写 JSONL → bridge 消费 → 写 demand turn
- 验证 codex 路径产物与 pi 路径等价（visible reply 先于 talk_send、demand turn 写入账本）
- 更新 `test_build_cli_prompt_for_pi_does_not_duplicate_restraint_instructions` 适配统一后的 prompt

**验证结果**：
```
py_compile: talk_send_mcp.py / codex_bridge.py / cli_bridge.py → OK
tests.test_cli_bridge: 54 tests OK（含新增 codex MCP 等价测试）
tests.test_discussions: 16 tests OK
tests.test_pi_bridge: 3 tests OK
MCP server 协议验证: initialize / tools/list / tools/call → 通过
git diff --check: 通过（仅 Windows CRLF 提示）
```

**不变的部分**：
- `_can_create_deferred_file` / `_read_and_execute_deferred_actions` / `_record_deferred_demand_turns` 完全不动
- `talk_tools_extension.ts` 继续为 pi 服务
- `execute_talk_actions` 保留作为文本协议兜底

---

## 2026-06-01 docs 目录二次整理

**背景**：docs/ 根目录存在 18 个重复文件（MODULE_*.md、PRODUCT.md、SDK.md 等），同时 docs/spec/ 和 docs/guides/ 已有对应副本。

**操作**：
- 逐对比较根目录副本与 spec/guides 副本，确认所有 spec/guides 副本内容不低于根目录副本：
  - DEPLOY.md、QUICKSTART.md、QUICKSTART_AGENT.md：guides 副本有路径修正（../../deploy/talk.service、../spec/SDK.md）
  - MODULE_agent_example.md：spec 副本已将 SDK.md 路径更新为 docs/spec/SDK.md
  - MODULE_discussions.md：spec 副本有额外 turn_kind 字段和验收点内容（较根目录多 642 字节）
  - LOCAL_LAB_DESIGN.md、SDK.md、MODULE_bridges.md 等 8 个文件：仅 CRLF/LF 差异，内容相同
  - PRODUCT.md、QUICKSTART_USER.md、MODULE_files.md 等 5 个文件：完全一致
- 删除全部 18 个根目录重复文件
- 不创建空的 iterations/、validation/、milestones/ 目录（已确认不存在）

**引用更新**：
- `docs/PROJECT_BRIEF.md`：目录结构树、11 条模块索引链接（→ spec/MODULE_*.md）、3 条 Addendum 引用（→ spec/或 guides/）
- `AGENTS.md`：模块文档指引明确路径为 spec/MODULE_xxx.md
- `CLAUDE.md`：部署/快速启动链接指向 docs/guides/
- `README.md`：Quickstart/Deploy/SDK 链接指向 docs/guides/ 和 docs/spec/

**验证**：
- `rg --files docs` → 结构符合目标
- 旧路径搜索（`docs/(MODULE_|PRODUCT\.md|SDK\.md|...)`）→ 无残留，仅新路径引用
- Markdown 本地链接校验 → 通过
- `git diff --check` → 通过

---

最后更新：2026-06-01 5.5 方案 D：discussion_turns 显式交互账本
最新条目在顶部。条目数 > 30 时，最旧条目自动归档到 PROGRESS_archive.md
-->

## 2026-08-27 Kimi 迁移到官方 Kimi Code CLI

**背景**：当前固定拓扑中的 Reviewer 名义上是 Kimi，但实际由 pi runtime 加载 `moonshotai-cn/kimi-k3`。项目管理者已经在本机安装 Kimi Code CLI，并确认改用本家 CLI。本切片只完成 bridge、活动成员拓扑和项目文档迁移；不启动 Server/bridge，不创建新验收任务，不进入 TH-7。

### 完成事项

- 新增 `bridges/kimi_bridge.py`，默认成员为 `agent:kimi`、runtime 为 `kimi-code`，使用官方 `kimi --auto --output-format stream-json ... -p` 和 argv prompt 传输；`--auto` 避免无人值守 bridge 卡在权限询问，实际能力仍受 Agent 文件工具白名单约束。
- bridge 启动时在临时目录生成三份受控 Kimi Agent 文件：Group Hall 讨论无工具、Task Hall 领取前预检无工具、任务执行默认 `review` 档开放 `Read / Grep / Glob / Bash`；显式 `--kimi-task-profile tools` 才额外开放 `Edit / Write`。
- 三份 Agent 文件均设置 `subagents: []`，并把 `--skills-dir` 指向受控空目录；项目 `.talk/agents/agent_kimi/` 的 IDENTITY / SOUL / USER 通过既有 profile 机制注入系统提示词。
- 通用 bridge 新增 Kimi `stream-json` 解析与结果归一化，忽略 Tool / meta 事件，提取最后一条非空 Assistant 文本；覆盖消息处理、任务预检、协议修复、任务执行和 Review/Test 门禁。
- Kimi 纳入紧凑身份 prompt 规则；pi 专属中文最终答复归一化保持不变。
- `.talk/groups.yaml`、`AGENTS.md` 与各 Agent 角色档案切换到 `agent:kimi`；移除旧活动档案 `.talk/agents/agent_pi/`，但不迁移或删除数据库中的旧成员历史。
- `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_bridges.md`、`docs/spec/MODULE_tasks.md`、`docs/spec/LOCAL_LAB_DESIGN.md` 已同步官方 Kimi CLI 入口、当前拓扑、权限档位和已知会话边界。pi bridge 仍保留为兼容入口。

### 验证

- `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge -q`：`Ran 119 tests`，`OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_kimi_bridge tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_profiles tests.test_talk_cli -q`：`Ran 196 tests in 9.713s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 389 tests in 109.913s`，`OK`。
- `python bridges/kimi_bridge.py --help` 正常；`py_compile bridges/cli_bridge.py bridges/kimi_bridge.py tests/test_kimi_bridge.py` 通过；`git diff --check` 通过，仅有 Windows LF/CRLF 提示。
- 本机 Kimi Code CLI `0.38.0` 能正确解析 `--output-format stream-json`、受控 `--agent-file` 和 `--skills-dir`，并输出 JSON meta；随后因本机尚未登录或配置默认模型返回 `No model configured`、退出码 1。该调用没有模型答案，因此真实端到端验收仍待完成。
- 本切片无前端改动，未重复 Browser 验证；未启动 TALK Server/bridge，未创建任务，也未触碰已取消的 `#10/#11`。
- 已创建中文提交 `522635d`（`迁移 Kimi 到官方 CLI bridge`）。首次沙箱内 push 因无可用凭据失败，外部凭据 push 曾被授权门禁拒绝；项目管理者随后明确授权该远端与分支，推送成功：`14bd3d8..522635d  codex/task-hall -> codex/task-hall`。

### 当前结论与下一步

- 官方 Kimi Code CLI bridge 的实现与自动化回归完成，当前活动 Reviewer 身份统一为 `agent:kimi`。
- 项目管理者先执行 `kimi login` 或配置 Kimi Code 默认模型；随后同步项目 profile 并从全新根任务启动 Codex → DeepSeek → Kimi 的真实 TH-6d 验收。
- 本切片涉及 bridge 与跨模块配置，按决策 Agent 批次刹车暂停；真实三 Agent 人工验收通过前不进入 TH-7。

### 变更文件

- `bridges/cli_bridge.py`
- `bridges/kimi_bridge.py`
- `tests/test_kimi_bridge.py`
- `.talk/groups.yaml`
- `.talk/agents/README.md`
- `.talk/agents/agent_codex/IDENTITY.md`
- `.talk/agents/agent_codex/USER.md`
- `.talk/agents/agent_deepseek/USER.md`
- `.talk/agents/agent_kimi/IDENTITY.md`
- `.talk/agents/agent_kimi/SOUL.md`
- `.talk/agents/agent_kimi/USER.md`
- `.talk/agents/agent_kimi/MEMORY.md`
- 删除 `.talk/agents/agent_pi/` 下四份旧活动档案
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_tasks.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-22 推送修复并安全收束旧验收任务树

**背景**：DeepSeek 非持久化预检切片已经提交但尚未推送；真实三 Agent 验收遗留根任务 `#10` 与 Development 子任务 `#11`，分别停在 `running/in_progress` 和 `queued/assigned`。项目管理者要求先提交 GitHub 并继续。本切片只处理推送和旧树收束，不启动 bridge、不创建新验收任务。

### 完成事项

- 将本地领先的 5 个提交推送到 GitHub `origin/codex/task-hall`；本地与远端均指向 `cf12e8f`。
- 只读确认旧树范围严格为 `#10/#11`，无 Review/Test 关系或澄清记录；`#11` 从未 claim，`#10` 的旧租约早已过期。
- 按项目脚本创建操作前 SQLite 在线备份 `backups/backup_2026-08-22.db`，并通过完整性检查。
- 使用无 lifespan 的本地 ASGI 请求走正式鉴权和 `cancel-tree` API：先读取树并验证任务 id 为 `[10, 11]`，再由根请求者取消整树。
- `#10/#11` 均进入 `canceled/canceled`，根控制为 `canceled`、检查点原因为 `manual_cancel`；claim、实例、token 与租约全部清除。
- 两个 Task Hall 与其中 3 条历史消息保持不变；未启动 Server/bridge，未创建新任务。临时操作脚本已删除。
- 顺手纠正 `MODULE_tasks.md` 中已经过时的预检重试和本地 `pi-kimi` 拓扑描述，使其与已落地 bridge 行为和当前三 Agent 配置一致。

### 验证

- GitHub push：`5583bad..cf12e8f  codex/task-hall -> codex/task-hall`；本地与远端 SHA 均为 `cf12e8fdcef84dfc7e6a7d679d85be79b2d3665d`。
- 操作前备份与操作后 `talk.db` 的 `PRAGMA quick_check` 均返回 `ok`。
- `GET /api/tasks/10/tree` 与 `POST /api/tasks/10/cancel-tree` 均返回 `200`。
- SQLite 只读复核：`#10/#11 = canceled/canceled`，根 `control_status=canceled`，Hall 数为 2、Hall 历史消息数为 3。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks.AgentTaskTests.test_checkpoint_and_cancel_tree_enforce_roles_and_preserve_history -q`：`Ran 1 test in 1.842s`，`OK`。首次把测试类名误写为不存在的 `TaskApiTests`，该次未执行任何用例；更正为真实类名后通过。
- 8000 端口无监听；Git 工作树在文档更新前保持干净。

### 当前结论与下一步

- 旧验收树已经永久停止，不会在重新启动 bridge 后被误领；历史证据和恢复备份仍保留。
- 下一切片从全新根任务开始真实三 Agent 验收，依次验证 Codex 根协调、DeepSeek Development、Kimi3 Review/Test 与项目管理者人工验收；等待项目管理者确认后开始。

### 变更文件

- `docs/spec/MODULE_tasks.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 避免 DeepSeek 预检会话持久化

**背景**：此前给预检增加 3 轮上限后，DeepSeek Harness 每次 `headless` 调用仍会创建持久会话；单轮又可能包含正常判断和协议修复，因此出错时仍会生成多个无效对话窗口。项目管理者决定保留领取前澄清，但要求预检不产生窗口，并把 DeepSeek 跨轮询限制为 1 轮。本切片只处理该 bridge 行为，不启动现有 bridge、不处理旧 `#10/#11`、不进入三 Agent 验收。

### 完成事项

- 新增项目内 `.talk/dsh/preflight-ephemeral.cordis.yml`，只关闭 DSH 的 `session-persistence-jsonl` 和 `session-checkpoint-policy`。
- 通用 bridge 在 `runtime=dsh`、使用官方 `dsh / dsh.cmd / dsh.exe` 启动命令且 `--project` 下存在补丁时，只为 Task Hall 预检追加 `--patch`；正式任务命令保持原样，因此成功执行仍只保留一个正常 DSH 会话。
- 显式 `--task-preflight-command` 继续优先，自定义命令与缺失补丁时保持旧行为，避免隐式改写第三方命令。
- 新增 `--task-preflight-max-attempts 1..3`；DeepSeek 默认 1 轮，其他 runtime 默认 3 轮。单轮内的协议修复和信息不足时的澄清流程均保留。
- 新增自动注入、显式覆盖、缺失补丁回退、runtime 默认上限和 DeepSeek 一轮失败终止回归测试。

### 验证

- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 147 tests in 1.139s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 380 tests in 156.709s`，`OK`。
- `python bridges/cli_bridge.py --help`：正常展示 `--task-preflight-max-attempts {1,2,3}`。
- DSH `--dump-config` 确认补丁后的 `session-persistence-jsonl` 与 `session-checkpoint-policy` 均为 `disabled: true`。
- 真实最小 DSH 调用退出码为 0；调用前后用户级 sessions 目录均为 55 个文件，新增或改写为 0。此次未启动 TALK bridge，旧 `#10/#11` 现场未变。

### 当前结论与下一步

- DeepSeek 的澄清判断仍在，但预检与同轮协议修复不再出现在 DSH 会话列表；失败至多 1 轮，成功后只有正式执行会保留一个会话。
- 下一切片仍需先安全处理旧 `#10/#11`，再从新根任务执行 Codex → DeepSeek → Kimi3 的 Development / Review / Test / 人工验收完整闭环；等待项目管理者确认后开始。

### 变更文件

- `.talk/dsh/preflight-ephemeral.cordis.yml`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 修复委派弹窗卡片与两阶段上下文

**背景**：TH-6d 真实验收发现 `.task-create-panel.modal-card` 没有背景、边框和阴影，页面内容会透过弹窗；根任务与子任务又复用静态“执行 Agent”标签，无法直观看出先选根负责人、再为各子任务选执行者的两阶段关系。项目管理者要求本切片单独修复该前端问题。

### 完成事项

- 为通用 `.modal-card` 补齐实体背景、边框、圆角、文字颜色和阴影，任务创建弹窗不再透明；Group 创建和 Agent 人设等现有 modal 同时获得一致的卡片壳。
- 任务弹窗新增 dialog 语义及标题、上下文说明和 Agent 标签锚点；根模式显示“委派根任务 / 根任务负责人 / 创建根任务 Hall”，子模式显示“创建子任务 / 子任务执行 Agent / 创建子任务 Hall”。
- 根模式说明“根任务开始后再从详情创建子任务”，子模式说明“当前 Agent 只执行子任务，根负责人继续协调和汇总”；缺少 Agent 时的校验提示也随模式切换。
- 更新前端资源 cache-busting 版本，避免浏览器继续使用旧 CSS / JS。
- 前端静态测试新增卡片视觉属性、dialog / 可访问名称和动态两阶段文案断言；模块合同与用户手册同步当前按钮和字段名称。

### 验证

- `node --check web\app.js`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_task_web_ui -q`：`Ran 2 tests in 0.707s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 376 tests in 106.338s`，`OK`。
- Codex Browser 使用隔离临时 TALK 服务真实登录并分别打开根任务和子任务弹窗：两种模式计算背景均为 `rgb(255, 254, 250)`，具有实线边框、`14px` 圆角和阴影；DOM 中标题、说明、Agent 标签、下拉框可访问名称和提交按钮全部与模式一致，控制台无 error / warning。
- 隔离服务仅使用临时成员、项目、根任务和数据库；验证后关闭页面与服务并清理全部临时文件，现有 `talk.db` 和旧 `#10/#11` 现场未修改。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek 多行 prompt、预检无限重试和委派弹窗两个前端问题均已完成修复及自动化 / Browser 验证。
- 下一步等待项目管理者确认后安全处理旧 `#10/#11` 现场，并从新根任务重新执行真实三 Agent 完整验收；本切片不继续该操作。

### 变更文件

- `web/index.html`
- `web/app.js`
- `web/style.css`
- `tests/test_task_web_ui.py`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 限制任务预检最多连续尝试 3 次

**背景**：TH-6d 真实验收曾观察到 DeepSeek 预检协议输出无效后，worker 在每个轮询中执行正常提示和协议修复提示，两次均失败后仍在后续轮询继续调用，数分钟内生成至少 24 个无效 DSH session。项目管理者明确要求本切片只增加 3 次限制，不连续处理前端问题。

### 完成事项

- 将预检命令、超时、非零退出和无效协议结果统一包装为 `TaskPreflightError`；同一轮正常输出无效时仍保留一次协议修复机会。
- 任务 worker 按 task id 记录连续预检失败，最多进入 3 个轮询尝试；前两次上报实例错误，第 3 次不再等待下一轮。
- 达到上限后，bridge 领取 poison task，在对应 Task Hall 写入“已停止重试”的用户可见说明，并以 `failed` + `last_error` 完成任务，使终态持久化且不会进入第 4 次模型调用。
- 任一预检成功会清除该任务此前的失败计数；某个任务预检失败不会阻止 worker 继续处理同轮其它排队任务。
- 当前失败计数保存在 worker 进程内：达到第 3 次后的 `failed` 状态持久化；若在达到上限前人为重启 bridge，未完成计数不会跨进程继承。本切片未增加数据库字段或任务 API。
- 用户手册补充“自动预检连续失败 3 次”的恢复说明。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- 3 条新增定向用例：协议修复仍失败会抛出专用错误；连续失败严格停在第 3 次并持久化任务失败；成功预检会清零先前计数。结果为 `Ran 3 tests in 0.005s`，`OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 143 tests in 0.543s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 376 tests in 105.860s`，`OK`。
- 测试使用受控 fake runner 精确统计预检次数，确认没有第 4 次调用；本切片没有调用真实 DeepSeek 模型。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek 多行 prompt 丢失与预检无限重试两个 bridge 阻断项均已完成代码修复和自动化验证。
- 下一切片建议单独修复委派任务弹窗背景及根任务/子任务上下文标签，等待项目管理者确认后开始。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 修复 DeepSeek Windows 多行 prompt 丢失

**背景**：TH-6d 真实验收确认 TALK 以多行最终 argv 调用全局 `dsh.cmd` 时，Windows npm shim 的 `%*` 转发只把首行送入 Harness。升级 `@deepseek-ai/dsh` 至 `0.1.0-rc.8` 后问题仍在，因此本切片只修复命令启动边界；项目管理者明确要求逐项处理，本次没有顺带修改预检重试或前端问题。

### 完成事项

- 通用 bridge 在 Windows 解析到 `dsh.cmd` 后，会读取同目录全局 npm 树中的 `@deepseek-ai/dsh/package.json`，校验包名、`bin` 配置、入口存在且未逃逸包目录。
- 校验通过后，bridge 使用 npm 目录内的 `node.exe` 或系统 Node 直接启动 Harness JavaScript 入口，并保留原命令其余参数；任务预检和正式执行因共用 `run_cli_command` 均获得相同修复。
- 识别范围严格限定为官方 `dsh.cmd`；manifest 无效、入口异常、Node 不可用或命令为其他 `.cmd` 时保持原命令，不改变其他 CLI 行为。
- 新增官方 DSH shim 解析、非 DSH `.cmd` 保持原样以及中文多行 prompt 作为单个最终 argv 完整传输的回归测试。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 140 tests in 0.574s`，`OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 373 tests in 105.003s`，`OK`。
- 本机解析探针确认配置中的 `dsh.cmd --profile headless` 实际转换为 `node.exe ...\@deepseek-ai\dsh\lib\bin.js --profile headless`。
- 通过修复后的 `run_cli_command` 执行一次受控真实四行模型探针，DeepSeek 同时识别两行令牌并只返回 `DSH_MULTILINE_OK`，证明首行之后的正文和末行约束均未丢失。
- `git diff --check`：通过，仅有 Git 对工作区 LF/CRLF 转换的提示。

### 当前结论与下一步

- DeepSeek Windows 多行 prompt 丢失已修复，现有 bridge 启动配置无需改写。
- 预检协议失败后的跨轮询无限重试仍是独立阻断项；下一切片建议只处理该问题，等待项目管理者确认后开始。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 DeepSeek Harness `0.1.0-rc.8` 受控升级与验证

**背景**：TH-6d 真实三 Agent 人工验收已确认本机 `@deepseek-ai/dsh 0.1.0-rc.6` 经 Windows `dsh.cmd` 接收 TALK 多行 prompt 时只保留首行。项目管理者发现上游已发布 `0.1.0-rc.8`，决定先升级运行时基线，再进入 bridge 修复切片。

### 完成事项

- 两次手工 `npx @deepseek-ai/dsh@next --version` 尝试都在 npm `idealTree` 依赖解析阶段触及约 2 GiB 的 V8 堆上限；日志确认 DSH 尚未启动，全局版本仍为 `0.1.0-rc.6`。
- 在没有 DSH 进程运行时，为 `C:\Users\Administrator\.dsh` 建立临时结构化备份：121 个真实文件逐一校验 SHA-256，510 个 Junction 的相对路径、类型与目标全部一致。
- 通过仅对单次安装进程设置 `NODE_OPTIONS=--max-old-space-size=4096`，执行固定版本全局安装；npm 完成 `added 23 / removed 100 / changed 428 packages`，全局 DSH 升级为 `0.1.0-rc.8`。
- npm 11.16 的 `allow-scripts` 提示仅表示尚未记录审批；安装日志确认 6 个生命周期脚本均已执行且退出码为 0，没有再次执行或放宽全局脚本策略。
- 全部升级验证通过后，先移除备份内 510 个 Junction 本身，再递归删除唯一临时备份目录；复核确认目录不存在。

### 验证

- `dsh --version` 与 `npm list -g @deepseek-ai/dsh --depth=0` 均返回 `0.1.0-rc.8`。
- `dsh --help` 与 `dsh --profile headless --help` 正常，现有 `headless` profile 可加载。
- Node 直接加载 `node-pty` 与 `koffi`，分别确认 `spawn` 与 `load` 导出可用。
- 最小真实模型请求 `dsh --profile headless '只回复 DSH_RC8_OK，不要使用工具。'` 返回 `DSH_RC8_OK`，验证现有登录、模型调用与会话存储链路。
- 临时 `NODE_OPTIONS` 未持久化；收尾时无 Node/npm/npx/DSH 残留进程，项目工作区在文档同步前保持干净。

### 当前结论与下一步

- DeepSeek Harness 运行时升级完成，但上游发行说明没有声明修复外部 npm `.cmd` 多行 argv 边界；本次也未修改 TALK bridge，因此不能把升级视为验收阻断项已修复。
- 下一切片继续绕过 `dsh.cmd` 调用 Harness Node 入口，并为预检失败增加跨轮询有界重试/退避与回归测试；完成后再做受控真实多行 prompt 探针。

### 变更文件

- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-08-21 TH-6d 真实三 Agent 人工验收中断与故障诊断

**背景**：`c01a6a9` 已把本地拓扑收敛为 Codex、DeepSeek Harness、Kimi3，但此前未调用真实模型。项目管理者按 TH-6d 人工验收说明启动 TALK Server 与三个 bridge，并从 Project Blackboard 创建真实任务树。本轮未修改功能代码；只完成现场复核、故障诊断、验收结论纠正和上下文交接。

### 实际验收进展

- 本地项目 Agent 索引确认包含 `agent:codex`（Lead / decision）、`agent:deepseek`（Dev / execution）、`agent:pi`（Reviewer / execution），三个 member 曾成功注册实例。
- 首次 `talk sync` 受本机 SOCKS proxy 环境影响，`httpx` 报缺少 `socksio`；通过在当前 PowerShell 清除 `ALL_PROXY / HTTP_PROXY / HTTPS_PROXY` 并为 localhost 设置 `NO_PROXY` 后恢复。这是本机启动环境问题，不是 TH-6d 协议缺陷。
- 核对数据库后确认 `group:talk-dev` 从未创建；`.talk/groups.yaml` 只保存本地角色/profile 元数据。此前要求去该 Hall 成员面板删除 Claude / pi-kimi、加入 DeepSeek 的指引错误，后续人工验收不再包含该步骤。
- Human 创建根任务 `#10` 并分配给 `agent:codex`；根任务成功 claim 并进入 `running/in_progress`。随后从根详情创建 Development 子任务 `#11` 并分配给 `agent:deepseek`。
- 截止收尾复核，旧 bridge 进程均已停止；数据库保留 `#10 running/in_progress` 与 `#11 queued/assigned` 现场，作为后续故障修复与清理依据。

### 验收发现 1：委派任务弹窗与流程文案

- Codex in-app Browser 真实复现：委派任务遮罩存在，但 `.task-create-panel.modal-card` 本身透明，标题和标签直接叠在 Blackboard 上。
- 计算样式确认卡片为 `background: rgba(0,0,0,0)`、`border: 0`、`box-shadow: none`。CSS 中卡片外观仅应用于 `.group-create-panel / .details-card / #composer / .auth-card`，`.modal-card` 只定义尺寸和滚动，导致任务弹窗漏掉背景层。
- 根任务与子任务共用静态标签“执行 Agent”。实际流程是两阶段：首次“＋委派任务”选择根任务负责人；根运行后再从详情点击“创建开发 / Review / Test 子任务”选择子任务执行 Agent。旧验收说明虽分别写了 Codex / DeepSeek，却未说明选择发生在两个窗口，造成误导。
- 后续修复应补齐 modal card 背景/边框/阴影，并按上下文显示“根任务负责人”与“子任务执行 Agent”及必要帮助文案。

### 验收发现 2：DeepSeek Harness 未接收 Development

- `#11` 始终保持 `queued/assigned`、`attempt=0`、无 claim；DeepSeek instance 进入 `error`，错误为 `task queue worker failed: task preflight did not return a valid TALK_TASK_PREFLIGHT decision`。
- `headless` profile 为官方默认空覆盖，实际 provider/model 为 `deepseek-official/deepseek-v4-pro`，证明 Harness 登录和模型调用可用；不是 API Key、模型或任务正文配置错误。
- 只读解码 `$DSH_HOME` 的持久 session 后确认，TALK 生成的完整多行预检 prompt 经 Windows `dsh.cmd` 后，模型实际只收到第一行“你是 agent:deepseek，通过 dsh CLI bridge 接入 TALK。”；任务编号、标题、正文和 `TALK_TASK_PREFLIGHT` 输出合同全部丢失。DeepSeek 因此把调用当成接入握手并返回就绪说明。
- 根因位于 TALK `--prompt-transport argv` 与 Windows npm `.cmd/cmd.exe` 包装的多行参数兼容边界。Harness 已在 Windows profile 内默认使用 `pwsh`，但这发生在模型工具层，不能修复进入 Harness 之前的 `dsh.cmd` 参数损失。
- 首选修复：原生 Windows 继续运行 TALK，但 bridge 绕过 `dsh.cmd`，直接调用 Harness Node 入口并添加多行 prompt 回归；WSL/Linux 可作为后备环境，不作为第一修复路径。

### 验收发现 3：预检失败无限重试

- `_prepare_task_before_claim()` 每次轮询先调用一次预检，协议解析失败后再调用一次 repair prompt；两次仍失败会抛错。
- `run_task_queue_worker()` 捕获异常后只上报 instance error，随后继续下一轮轮询同一 queued task，没有任务级失败计数、退避或 poison-task 隔离。
- 真实现场数分钟内生成至少 24 个 DSH 一次性 session，存在重复计费、额度消耗与日志膨胀风险。项目管理者已被提示立即停止 DeepSeek bridge；2026-08-21 复核时相关进程均不存在。
- 后续必须增加跨轮询有界失败策略，并让相同阻断任务进入可观察、可人工恢复的状态；不能仅依靠一次调用内的 repair retry。

### 当前结论与下一步

- TH-6d 实现层的自动化与隔离浏览器闭环仍有效，但真实 Codex → DeepSeek → Kimi3 人工验收未完成，里程碑不能判定通过，也不能进入 TH-7。
- 项目管理者决定先修复验收阻断项：优先处理 DeepSeek Windows 多行 prompt 与预检重试保护，再修复任务弹窗视觉和两阶段标签。
- 修复完成后先安全处理旧 `#10/#11` 现场，从干净根任务重新跑 Development、Review、Test、自动暂停和人工验收完整闭环。

### 验证与变更文件

- 只读验证：Codex Browser DOM/截图/计算样式、SQLite 任务与 instance 状态、DSH Zstandard session 解码、官方 Harness 本地包源码与文档、Git 状态与进程状态。
- 未修改功能代码、数据库或 Harness 用户配置；未继续执行 Review / Test。
- 变更文件：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

---

## 2026-08-16 本地 Agent 拓扑收敛：Codex + Kimi3 + DeepSeek Harness

**背景**：项目管理者明确后续本地暂时只使用 3 个 Agent：Codex、通过 pi 接入的 Kimi3、通过 DeepSeek Harness 接入的 DeepSeek 各类模型；Claude Code 不再纳入当前本地拓扑。本片仅收敛 bridge 模型锁定、项目配置和相关文档，不调用真实模型。

### 完成事项

- 本地拓扑固定为：`agent:codex` = Lead / decision，`agent:deepseek` = DeepSeek Harness / Dev / execution，`agent:pi` = Kimi3 / Reviewer / execution。
- `.talk/groups.yaml` 移除 `agent:claude` 与 `agent:pi-kimi`，新增 `agent:deepseek`；保留 `agent:pi` member ID，避免现有 TALK Key 与历史消息迁移。
- 删除重复的 `agent_pi-kimi` profile，将 `agent_pi` 身份收敛为 Kimi3，新增 `agent_deepseek` 四件套 profile，并同步 Codex 的同伴 Agent 说明。
- `bridges/pi_bridge.py` 新增 `--pi-provider / --pi-model`；默认命令、Task runner 命令与领取前预检命令会统一注入锁定的 provider / model，且自定义 `--pi-command` 的原有覆盖语义保持不变。
- 本机 pi 全局默认仍是 DeepSeek，因此 TALK 启动命令显式锁定 `--pi-provider moonshotai-cn --pi-model kimi-k3`，不修改用户级 pi 配置。
- 确认已安装官方 `@deepseek-ai/dsh 0.1.0-rc.6`；使用通用 bridge 的 `argv` transport 调用 `dsh.cmd --profile headless`，无需新建专用 bridge。
- `AGENTS.md`、`PROJECT_BRIEF.md` 与 `MODULE_bridges.md` 已同步新拓扑、身份、命令和已知边界。

### 验证

- `codex.cmd --version` → `0.144.4`；`pi.cmd --version` → `0.84.1`；`dsh.cmd --version` → `0.1.0-rc.6`。
- `dsh.cmd --profile headless --help` 在隔离的临时 `DSH_HOME` 中确认接受 argv 任务并输出最终 assistant 消息。
- `pi.cmd --list-models kimi` 确认 `moonshotai-cn/kimi-k3`；`pi.cmd auth check --provider moonshotai-cn --model kimi-k3 --json --no-refresh` 返回 `status=ready`。
- 项目 profile 扫描结果精确为 `agent:codex / agent:deepseek / agent:pi`。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge tests.test_talk_cli -q` → `Ran 145 tests in 9.073s ... OK`。
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py` 与 `git diff --check` 通过。

### 边界 / 待验收

- 未实际调用 Kimi3 或 DeepSeek 模型，未运行真实 TALK 消息 / Task Hall 往返；避免未经确认消耗模型额度。
- `talk sync` 只全量替换项目 Agent 索引，不会删除运行中 Group 的旧成员关系；启动 `agent:deepseek` 并同步索引后，仍需在 `group:talk-dev` 成员面板人工移除 Claude / pi-kimi、加入 DeepSeek。
- 当前无独立全能 Tester；Kimi3 可做 API / 日志 / 自动化检查，浏览器操作由项目管理者完成。
- TH-6d 里程碑仍保持 `awaiting_human`，不进入 TH-7。

### 变更文件

- `bridges/pi_bridge.py`、`tests/test_pi_bridge.py`
- `.talk/groups.yaml`、`.talk/agents/`
- `AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

---

## 2026-07-31 TH-6d：里程碑 Test 门禁、Blackboard 控制与人工验收

**背景**：TH-6c 已落地任务类型、冻结关系、结构化 Review 与两轮返工，但 Test 尚未成为根任务完成门禁，批次安全收尾和里程碑通过后也不会自动暂停。项目管理者确认继续 TH-6d。该切片同时涉及数据库、任务协议和前端真实交互，按决策 Agent 高风险单切片刹车完成后暂停等待人工验收，不进入 TH-7。

### 数据与服务端状态机

- 根任务新增 `milestone_test_required`，仅可委派根任务可开启；旧库迁移回填 `false` 并建立索引。
- `GET /api/tasks/{id}/tree` 新增 `test_gate`，返回是否必需、当前完整冻结版本 id 集、覆盖它的 Test、结构化结论和满足状态。
- 里程碑 Test 只能在全部最新必需 Review 通过后创建，并且必须精确覆盖根任务的完整最新冻结版本集；质量任务使用版本语义槽阻止重复或并发终结结论。
- `failed` Test 可作为返工触发器；返工成功后冻结版本切换，旧 Review / Test 结论不再覆盖新版本，必须重新取得门禁。
- 根任务成功完成前统一检查非终态后代、最新冻结结果、必需 Review 与里程碑 Test；旧 `general` 根任务保持兼容。
- 非里程碑批次额度耗尽后，既有开发与 Review 安全收尾即自动进入 `awaiting_human / batch_limit`。
- 里程碑 Test 得到 `passed` 后，根任务原子进入 `awaiting_human / milestone` 并撤销活动 claim；Human 新入口 `POST /api/tasks/{id}/accept-milestone` 验收后递增授权 epoch、清除检查点，但不自动增加开发额度。
- Review / Test 的 `blocked`、runner 失败或取消会释放未形成终结结论的版本槽，允许安全重试。

### SDK 与 Project Blackboard

- async / sync `create_task()` 增加 `milestone_test_required`，新增 `accept_task_milestone()`。
- 根任务创建表单增加委派开关、1–3 个切片额度和里程碑 Test 标记。
- 类型化子任务表单支持 `development / review / test / rework / general`、Review 策略、冻结任务多选和返工触发任务。
- 任务详情新增治理卡，展示根控制状态、检查点、授权 epoch、剩余切片、非终态后代、Review 门禁和 Test 门禁。
- 页面补齐提交最新澄清答复、释放人工决策、暂停整树、风险检查点、授权继续一批、人工验收通过、终止整树等动作。
- 质量任务下拉框增加稳定的可访问名称；Web 资源更新缓存版本。

### 验证

- Python `py_compile` 覆盖模型、迁移、任务路由、async / sync SDK 和相关测试文件；`node --check web/app.js` 通过。
- 新增自动化覆盖：里程碑 Test 通过后暂停且根任务不能提前完成、Human 人工验收、非里程碑批次安全检查点、Test 失败触发返工、返工后旧 Test 失效、旧库字段回填和 Web 控制入口。
- 全量回归：`.venv\Scripts\python.exe -m unittest discover -s tests -q`，`Ran 370 tests in 122.729s ... OK`。
- Codex in-app Browser 真实贯通：Human 创建带里程碑 Test 的根任务并从页面创建开发子任务；Review 与完整 Test 通过后，页面显示 `awaiting_human / milestone`、Review `approved`、Test `passed` 和“人工验收通过”；验收后根恢复 `active`、epoch `1 -> 2`、剩余开发额度保持 0。
- 页面控制台没有 `error / warning`；临时隔离服务与浏览器验收数据库已停止并清理。
- `usage-gate.cmd guard --provider codex --json` 返回 `decision=continue`；session / weekly 精确百分比均为 `null`，本轮仍按高风险单切片与里程碑门禁停止。

### 文档与边界

- 同步 `docs/spec/MODULE_tasks.md`、`docs/PROJECT_BRIEF.md`、`docs/guides/USER_MANUAL.md` 和当前进度快照。
- 服务端可强制冻结关系和结构化门禁，但无法从自由文本角色证明第三方 Tester 的操作系统级工具能力；正式运行仍需配置能启动隔离服务、调用 API、控制浏览器和读取日志的 Tester。
- TH-6d 当前等待项目管理者人工验收；验收通过前不进入 TH-7。

### 变更文件

- `server/models.py`
- `server/db.py`
- `server/routes/tasks.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `tests/test_tasks.py`
- `tests/test_task_web_ui.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROJECT_BRIEF.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

---

## 2026-07-26 TH-6c：结构化 Review、返工关系门禁与角色发现

**背景**：TH-6b 已让 bundled runner 在领取前完成预检与澄清，但任务仍缺少开发 / Review / Test / 返工的强类型、显式关系和服务端质量门禁。项目管理者授权继续下一切片，并说明暂时无暇人工验收。由于本轮涉及数据库、任务协议与跨模块 runner，按决策 Agent 的高风险批次刹车只推进 TH-6c，不进入 TH-6d。

### 数据与服务端合同

- `agent_tasks` 新增 `task_kind`、`review_policy`、JSON `gate_verdict`；旧任务迁移为 `general`。
- 新增 `agent_task_relations`，记录 `reviews / tests / reworks`、触发任务和冻结版本轮次；迁移补齐索引与唯一约束。
- 类型化任务只允许作为子任务；同根、同项目、当前 `authorization_epoch`、授权有效期和非终态后代上限由服务端校验。
- `general / development` 消耗授权切片；`review / test / rework` 不消耗新的开发切片。
- `development` 默认 `required` Review；低风险 `batch` 一次覆盖同批次 2–3 项；`exempt` 仅 Human 或项目 `decision_tier=decision` 的 Agent 可授权。
- Reviewer 必须与所有被审任务执行者不同。开发 / 返工成功必须引用结果消息；Review / Test 成功必须提交匹配类型的结构化 verdict，负向结论必须带 findings。
- `GET /api/tasks/{id}/relations` 返回显式关系；`quality-context` 向质量任务创建者 / 执行者只读开放关联任务、触发任务及完整 Task Hall。
- 类型化任务树只有在所有非终态后代结束、最新开发 / 返工成功且必需 Review 为 `approved` 时才能完成；纯 `general` 旧流程不被追溯阻断。
- 同一质量问题最多自动返工两轮；第 2 轮返工再次得到 `changes_requested` 时，根任务在同一事务进入 `awaiting_human / review_exhausted` 并撤销其它 claim。

### Review 冻结版本语义槽

独立集成审查发现，若允许同一冻结版本重复创建 Review，后续 `approved` 可以覆盖先前 `changes_requested`，并绕过返工上限。最终合同收敛为：

- Review relation 按当前冻结版本轮次 `0 / 1 / 2` 占用唯一语义槽，并发创建只能一条成功。
- `approved / changes_requested` 是终结语义，保留槽位；原版本不能再次 Review。
- runner `failed`、任务 `canceled` 或结构化 `blocked` 不形成批准 / 变更结论，会在完成或取消事务中释放槽位，允许同一冻结版本重试。
- 根门禁因此不会把未变化版本上的后续结论当作对既有变更请求的覆盖。

### Runner、SDK 与工具

- bundled runner 为 Review / Test 注入显式 `TALK_GATE_VERDICT` 合同，读取关系授权的完整质量上下文，首次格式错误有界纠正一次。
- runner 只把解析出的结构化结论传给 `complete`；若 Task Hall 结果回写失败，任务按 `failed` 完成且不携带 verdict，避免服务端 422 后卡在 `running`。
- async / sync SDK 支持类型、Review 策略、关联任务、触发任务、结构化 verdict，以及 relations / quality-context helper。
- CLI 从 `.talk/groups.yaml` 聚合自由业务角色、决策分级和能力列表；跨群组角色稳定去重，分级冲突显式报错。
- 项目 Agent API 与 `talk_list_agents` 返回 `business_role`、`decision_tier`、`capability_summary`、实例列表和聚合可用状态。
- Python MCP 与 Pi extension 保持原有八个工具名，扩展 typed delegate、类型过滤、关系读取和项目 Agent 富化结果。

### 验证与审查

- Python `py_compile` 覆盖服务端模型 / 迁移 / 路由、CLI、async / sync SDK、runner 与 Python 工具；Pi TypeScript 通过 Node 语法检查。
- 服务端 + runner 定向回归：`Ran 166 tests in 39.405s ... OK`。
- CLI / SDK / Python MCP / Pi 工具联合回归：`Ran 48 tests ... OK`。
- 最终全量回归：`Ran 366 tests in 147.008s ... OK`。
- 首次全量命令因外部 5 分钟工具时限被终止，没有最终结果；提高时限后从头完整重跑通过。
- 独立只读集成审查覆盖权限 / epoch / 项目范围、切片非消费、批量 Review、两轮返工原子暂停、结构化 verdict、关系上下文、并发唯一性、旧 `general` 兼容与角色发现；修复上述两个失败路径后无剩余阻断项。
- `usage-gate.cmd` 返回 `decision=continue`，但没有提供 session / weekly 精确百分比；未臆测具体额度，仍按数据库 / 协议高风险单切片规则停止。
- 本切片未修改 Web，按 Browser 约定无需页面验证。

### 当前边界

- `test` 类型、关系和结构化 verdict 已持久化，但根任务 Test 门禁、最新冻结版本失效、Blackboard 质量控制与测试通过后的人工验收暂停属于 TH-6d。
- Review 的“只读”由 bundled runner prompt 约束；服务端不能替代第三方 Reviewer 的操作系统文件写权限隔离。
- Web 尚无 Review / 返工创建、关系查看、结构化结论和质量检查点入口。
- 项目管理者本轮暂时无暇人工验收；自动化与代码审查完成后按高风险单切片规则暂停，未把验收门禁永久取消。

### 变更文件

- 服务端：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`server/routes/projects.py`
- SDK / CLI / 工具：`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`、`cli/talk.py`、`bridges/cli_bridge.py`、`bridges/talk_task_tools.py`、`bridges/talk_tools_extension.ts`
- 测试：`tests/test_tasks.py`、`tests/test_projects.py`、`tests/test_cli_bridge.py`、`tests/test_talk_cli.py`、`tests/test_talk_client.py`、`tests/test_talk_task_tools.py`
- 文档：`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_tasks.md`、`docs/guides/USER_MANUAL.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

### 下一步

1. 暂停并提交 / 推送 TH-6c 可回溯版本。
2. 项目管理者恢复后进入 TH-6d：里程碑 Test 门禁、最新冻结版本、Blackboard 控制、批次自动检查点与人工验收暂停。
3. TH-6d 构成下一处里程碑门禁，完成后必须提供人工验收说明并等待确认。

## 2026-07-26 TH-6b：runner 领取前预检、自动澄清与完整 Hall 重放

**背景**：TH-6a3 已建立澄清轮次和服务端状态门禁，但 bundled runner 仍会从 `assigned` 直接 claim，正式执行也只获得任务标题 / 正文。本轮属于 runner / 协议高风险切片，按批次刹车只完成 TH-6b，并同步落实项目管理者确认的 Codex 决策 Agent 身份，不进入 TH-6c Review 门禁。

### Agent 分级

- `AGENTS.md` 明确当前普通 Codex 项目会话按决策 Agent 工作；bridge 内成员继续以启动时注入的 `decision_tier` 为权威，未声明的其它成员仍按执行 Agent。
- `.talk/groups.yaml` 已有 `agent:codex = lead + decision`。通用 CLI bridge 在传入 `--project` 且没有显式 `--decision-tier` 时会从项目配置解析分级；显式命令行覆盖保持最高优先级。
- Codex / pi 的普通任务和预检 prompt 都携带解析后的决策分级，避免模型只看到业务角色而不知道行为边界。

### 实现

- 对带 Task Hall 的 `assigned / clarification_answered` 任务，runner 会先分页读取完整 Hall，再以独立只读 / 无工具命令做领取前预检；Codex 预检不挂载 TALK MCP，pi 预检不启用本地工具或 extension。
- 预检信息充分时先 `accept`，随后才 `claim`；信息不足时把一批集中问题写入同一个 Task Hall，并以问题消息 id 原子登记澄清轮次。`clarification_requested / needs_decision` 不会重复唤醒。
- 自动问题使用稳定的任务 / 澄清轮次标记。若进程在“问题消息已发送、澄清动作尚未登记”之间退出，下次轮询会复用已有问题完成登记，不重复调用模型或再发一条消息。
- `accepted` 表示预检已完成，runner 重启后可以直接 claim；`clarification_answered` 会携带 A 的显式答复重新预检。
- Hall 以 500 条为一页向前分页，去重后按消息 id / 时间顺序重放。正式执行 prompt 复用同一份完整上下文，包含任务原文、问题、答复和可见文件元数据；附件正文仍不自动下载。
- 解析器只接受显式结构化结论，兼容单行 `TALK_TASK_PREFLIGHT`、显式标记后的多行 JSON 以及真实 Pi 出现的嵌套 / `ready` 变体；纯自然语言不会被猜测为接受。
- 成功命令首次返回无效格式时，runner 会用同一个只读 / 无工具命令纠正一次；超时、非零退出或再次无效都不会 claim，也不会消耗澄清轮次。
- Codex 重复任务执行实现收敛为共享 `cli_bridge.handle_queued_task`，保留 Codex command adapter 和原测试替换点，减少两套 runner 行为漂移。

### 测试

- 单元测试覆盖项目分级解析与显式覆盖、预检 prompt 合同、结构化变体解析、首次格式纠正、完整分页顺序、充分后先 accept 再 claim、同 Hall 澄清、等待状态过滤和中断窗口恢复。
- Codex / pi 测试锁定预检命令始终为只读 / 无工具配置，即使正式执行选择 tools profile 也不会在领取前修改项目或调用 TALK 投递工具。
- 活服务 E2E 覆盖 `created -> 自动提问 -> clarification_requested -> Human 回答并显式提交 -> 重新预检 -> accept -> claim -> execute -> complete`；正式执行 prompt 断言能看到答复中的 `8123`。
- Python `py_compile` 通过。
- 定向回归：`Ran 168 tests in 28.697s ... OK`。
- 全量回归：`Ran 348 tests in 154.472s ... OK`。
- 较早的一次混合定向命令误含不存在的测试模块，并命中既有 WebSocket 降级用例的固定 2 秒退出超时；该用例随后连续单跑两次通过，最终全量回归也通过。本切片没有修改 WebSocket 降级路径。
- 真实 Codex 只读预检返回可解析的显式结构化结论。真实 Pi 返回显式多行 `ready=false`，基础设施安全阻止 claim；但它忽略了正文中已给出的信息并要求重复任务，记录为模型理解质量残余，不伪造成语义验收通过。
- 本切片没有修改 Web 页面，按 Browser 验证约定无需做页面验证。

### 用户手册影响

- `docs/guides/USER_MANUAL.md` 已用非技术语言说明 Agent 会在领取前检查完整 Task Hall；信息不足会在原 Hall 提问并保持待响应，Human 明确提交答复后 Agent 会重新读取全部上下文。

### 变更文件

- `AGENTS.md`
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_task_hall_e2e.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. 暂停等待项目管理者确认本切片。
2. 确认后进入 TH-6c：任务类型、任务关系、结构化 Review / 返工门禁与业务角色发现。
3. 后续 TH-6d 再实现里程碑黑盒测试、Blackboard 控制、批次自动检查点与人工验收暂停。

## 2026-07-20 TH-6a3：Task Hall 有界澄清轮次与决策阻塞

**背景**：TH-6a0 已冻结“一批集中问题 + 一批完整答复”按轮计数、默认 1 轮、绝对上限 2 轮的合同；旧实现只有 `clarification_requested` 状态，普通回复与完整答复无法区分，也没有额度耗尽后的阻塞。由于本轮涉及数据库、协议和根控制传播，按高风险切片刹车只完成 TH-6a3，不进入 runner 自动预检或 Web 控制入口。

### 实现

- `agent_tasks` 新增 `max_clarification_rounds / clarification_round_count`；旧库默认回填 1 / 0。创建任务只接受 1–2 轮，schedule 物化任务保持默认 1 轮。
- 新增 `agent_task_clarification_rounds` 账本，按任务和轮次保存问题消息、答复起止消息与时间；`task_id + round_index` 唯一，配合条件更新保证并发请求只建立一轮。
- B 必须先在 Task Hall 发送问题，再调用 `request-clarification` 登记边界；A 可连续补充多条，最后调用 `submit-clarification-answer` 明确结束答复。普通 Hall 回复不会改变状态。
- 新增 `clarification_answered / needs_decision`。显式答复后仍禁止直接 claim，B 必须 `accept`；额度耗尽时任务进入 `needs_decision`，根任务进入 `awaiting_human / needs_decision`，活动 claim 被撤销。
- 新增 `resolve-clarification`：Human、当前任务请求者或根请求者可补充范围后释放，或增加一轮额度；绝对上限仍为 2。根控制保持等待，需单独 `resume-tree` 恢复，防止解决局部澄清时意外放开全树。
- async / sync SDK 新增轮次查询、问题登记、答复提交和人工释放 helper；Python MCP 与 pi extension 的 `talk_reply_task` 使用当前 Hall 消息 id 作为问题 / 答复边界，并支持人工释放动作。
- 旧无 Hall / 无轮次账本的澄清任务保留兼容接受路径；旧客户端从 `assigned` 直接 claim 继续兼容，但新澄清三态均受服务端 claim 门禁约束。

### 测试

- 覆盖 1–2 轮创建边界、错误发送者边界、普通回复不推进、重复问题 / 答复幂等、多条答复起止边界和明确接受后才能 claim。
- 覆盖额度耗尽进入 `needs_decision / awaiting_human`、错误解决者拒绝、增加一轮、显式恢复根控制、绝对上限 2 和再次耗尽。
- 使用两个并发客户端同时登记不同问题，验证仅一个请求成功、计数为 1 且只有一条账本记录。
- 迁移测试验证旧任务字段回填及轮次唯一索引；async / sync SDK 与 Task Hall 工具活服务流程均贯通新协议。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -q`：`Ran 32 tests in 17.814s ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 337 tests in 118.141s ... OK`。
- Python `py_compile`、TypeScript `node --experimental-strip-types --check` 与 `git diff --check`：通过。
- 本切片无 Web 代码改动，不需要 Browser 验证。

### 用户手册影响

- 已同步 `docs/guides/USER_MANUAL.md`：使用非技术语言说明普通消息不会自动结束澄清、默认一轮 / 最多两轮和额度耗尽会暂停；页面尚无提交答复或人工决策入口，因此只说明需项目负责人协助，不写启动服务、API 或开发命令。

### 变更文件

- `server/models.py`
- `server/db.py`
- `server/routes/tasks.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/talk_task_tools.py`
- `bridges/talk_tools_extension.ts`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `tests/test_talk_task_tools.py`
- `docs/spec/MODULE_tasks.md`
- `docs/guides/USER_MANUAL.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. TH-6b：让 bundled runner 在 claim 前预检任务充分性，自动进入同 Hall 澄清、等待显式答复，并分页重放完整任务 / Hall 上下文。
2. TH-6c / TH-6d：再进入 Review / Test 门禁与 Blackboard 最终用户控制入口；本高风险切片完成后先暂停汇总，不连续开启下一切片。

---

## 2026-07-20 TH-6a2.2：bundled runner 最长 5 秒协作中断

**背景**：TH-6a2.1 已能在服务端持久化暂停 / 检查点 / 整树终止并立即撤销运行 claim，但 bundled runner 默认每 30 秒才续租一次，导致本地 CLI 进程不能在合同要求的 5 秒窗口内感知控制。本轮按 runner 高风险切片只补协作中断，不进入澄清轮次、Web 控制入口或 Review/Test 门禁。

### 实现

- `bridges/cli_bridge.py` 将 bundled runner 默认 claim heartbeat 调整为 5 秒，并新增 5 秒硬上限；即使启动参数显式传入更长的 `--task-heartbeat-interval`，有效 claim / 控制探针也不会被放宽。
- claim heartbeat 继续由服务端原子校验根控制状态。暂停、检查点、整树终止或其它 claim 失效返回 `404 / 409` 时，runner 抛出 `TaskLeaseLostError` 并取消正在等待的命令。
- 通用 CLI runner 与 Codex 兼容 runner 共用上述守卫；命令协程取消会进入 `run_cli_command` 的既有清理路径，终止并回收本地子进程。
- 控制中断后 runner 不发送 Task Hall 结果消息、不调用 `complete`；暂停 / 检查点的 `queued / accepted` 回队和整树终止的 `canceled` 状态继续由服务端作为唯一真相源。
- 服务不可达时 runner 无法接收新的控制事实，仍由现有本地租约截止时间提供最终失效保护；第三方 runner 也仍需自行实现相同协议。

### 测试

- 新增有效 claim / 控制探针间隔测试，覆盖默认 30 秒配置被硬性收敛到 5 秒、显式更短间隔和短租约自适应。
- 新增真实 Python 子进程取消测试，确认取消执行协程会及时终止本地进程。
- 通用 CLI runner 覆盖 `paused / awaiting_human / canceled` 三类控制撤销，Codex runner 单独覆盖共享守卫接入；均断言本地命令被取消，且没有发送结果或调用 `complete`。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge -q`：`Ran 112 tests in 0.643s ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge -q`：`Ran 153 tests in 15.782s ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 334 tests in 97.578s ... OK`。
- 本切片无 Web 改动，不需要 Browser 验证。

### 用户手册影响

- 已检查 `docs/guides/USER_MANUAL.md`：暂停 / 继续 / 整树终止尚无最终用户页面入口，仍不能写成可操作步骤，因此本轮不修改用户手册；模块合同和进度文档记录后台能力已完成。

### 变更文件

- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

1. TH-6a3：实现澄清轮次账本、显式答复提交、`clarification_answered / needs_decision` 与服务端 claim 门禁。
2. TH-6b：在轮次合同落地后接 runner 领取前预检、完整 Hall 上下文重放和自动澄清闭环。

---

## 2026-07-20 TH-6a2.1：根控制状态与有限批次授权服务端落地

**背景**：项目管理者确认 TH-6a0 的有限批次与随时喊停合同，并授权以决策 Agent 身份推进下一切片。由于本轮涉及数据库 / 协议和权限边界，按批次刹车只完成 TH-6a2.1 服务端控制面，不进入 bundled runner 协作中断或 Web 控制按钮。

### 已完成

- `agent_tasks` 根任务新增 `control_status`、`authorization_epoch`、`authorized_slice_budget`、`reserved_slice_count`、`authorization_expires_at`、`checkpoint_reason`；控制状态与到期时间补齐索引。
- 新建可委派根任务默认获得 2 个切片、90 分钟授权，Human 可显式设为 1–3 个切片与 60–5400 秒；恢复会递增 epoch、重置本批次预留数并生成新到期时间。
- 新后代创建必须提交当前 `authorization_epoch`，并在同一条条件更新中原子检查根仍在运行、控制状态为 `active`、授权未过期、epoch 未陈旧、切片额度和非终态后代硬预算均有余额；并发创建只有预算内请求成功。
- claim 已把根控制状态与授权到期加入原子条件；过期创建 / claim 会把根任务推进到 `awaiting_human / time_limit`。旧 epoch 即使在恢复后晚到，也不能消费新批次授权。
- 新增 `pause-tree / resume-tree / checkpoint / cancel-tree / tree` 五个接口，传入任一后代 id 均解析到根任务，并分别约束根请求者、Human 管理者和根执行者权限。
- 暂停 / 检查点立即把运行任务安全回到 `queued / accepted`，清除 claim token、lease 与实例占用；整树终止取消全部非终态任务；Hall、消息、attempt、完成结果与历史任务行均保留。陈旧 runner 的心跳和完成写回由现有状态 / token 门禁拒绝。
- async / sync SDK 的 `create_task` 新增授权额度、有效期与 epoch 参数，并新增五个任务树控制 helper；活服务测试贯通暂停、恢复、检查点、查询和终止。

### 迁移与兼容

- 历史根任务回填为 `active`；历史不可委派任务使用 `epoch=0 / budget=0`，旧完成与结果收取不变。
- 历史可委派根任务使用 `epoch=1 / budget=2`，当前已有后代数计入 `reserved_slice_count`，避免升级后凭空获得额外切片；后代不复制根控制字段。
- 当前还没有 `task_kind`，所以每个新后代暂统一消费 1 个切片；`review / test / rework` 的免计与批次安全收尾后自动 `batch_limit` 检查点留待 TH-6c 的任务关系实现。
- 服务端现已立即撤销本地 runner 的执行与写回资格，但不会强杀正在运行的未知进程；bundled runner 最长 5 秒检查和本地子进程停止留待 TH-6a2.2。

### 验证

- `python -m py_compile server/models.py server/db.py server/routes/tasks.py TALK/client/talk_client.py TALK/client/talk_client_sync.py tests/test_tasks.py tests/test_talk_client.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -q`：`Ran 29 tests ... OK`；覆盖旧库迁移、历史委派树回填、并发切片预留、权限、暂停 / 恢复、检查点、整树终止、到期、陈旧 epoch，以及控制状态持久化后心跳 / 完成立即失效。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -q`：`Ran 12 tests in 17.354s ... OK`；async / sync 活服务控制流程通过。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 331 tests in 71.979s ... OK`。
- `git diff --check`：通过，仅有 Windows 工作区既有 LF / CRLF 转换提示。本切片没有前端改动，不需要 Browser 验证。

### 用户手册影响

- 已复核 `docs/guides/USER_MANUAL.md`：本轮只有服务端 API 与 SDK，还没有普通用户可见按钮，runner 也未完成主动中断，因此不把暂停 / 继续 / 整树终止提前写成正式操作步骤；手册现有“当前版本边界”保持正确。

### 变更文件

- 功能：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`。
- 测试：`tests/test_tasks.py`、`tests/test_talk_client.py`。
- 文档：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

### 下一步

- TH-6a2.2：实现 bundled runner 最长 5 秒控制检查、本地子进程协作中断与服务端暂停 / 终止状态联动。该切片涉及真实执行中断，完成后应暂停汇总并进行独立人工 / 黑盒验收准备。

## 2026-07-20 用户手册骨架与项目内同步规则

**背景**：项目管理者提出，任务暂停、澄清、Review 等机制最终都需要用非技术语言告诉普通使用者，同时确认不应让 TALK 的项目特有规则影响其它项目，也不应把开发环境启动命令混入最终产品操作手册。

### 已确认并完成

- 保持用户级全局 `project-framework` skill 不变；用户手册同步规则只落在 TALK 的 `docs/PROJECT_BRIEF.md`。
- 新增 `docs/guides/USER_MANUAL.md`，明确以“系统已经部署完成”为前提，只面向日常使用 TALK 的家庭成员或项目成员。
- 手册首版记录当前已验证的登录、项目黑板、任务委派、Task Hall 沟通、澄清补充、结果收取、未开始任务取消，以及全局消息流 / Group Hall 的使用方式。
- 尚未提供最终用户入口的暂停、继续、整树终止、澄清轮次和 Review/Test 只作为当前版本边界，不提前写成可操作步骤。
- `QUICKSTART_USER.md` 继续负责家庭管理员首次安装与启动，`DEPLOY.md` 负责部署运维，`QUICKSTART_AGENT.md` 负责开发者和 Agent 接入；普通用户手册不包含 Docker、Python、API、测试或本地开发启动命令。
- `docs/guides/QUICKSTART.md` 已增加日常用户手册入口；`PROJECT_BRIEF.md` 目录结构已登记新文档。
- 后续每个用户可见功能切片都要检查手册影响；只有真实入口落地并完成验证后才转写为正式操作步骤，里程碑人工验收需按手册从头复现。

### 验证

- `git diff --check`：通过，仅有现有 Windows LF / CRLF 转换提示。
- 用户手册技术命令关键词扫描：未发现开发步骤；`Python / Docker / API / 数据库` 只出现在“普通用户无需了解”的范围声明中。
- `USER_MANUAL.md`、`QUICKSTART.md`、`PROJECT_BRIEF.md` 的本地 Markdown 链接检查：全部可解析。
- 未运行功能测试：本切片只修改 Markdown 文档，没有修改产品代码。

### 变更文件

- `docs/guides/USER_MANUAL.md`
- `docs/guides/QUICKSTART.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### 下一步

- TH-6a2.1：实现根任务控制状态、有限批次授权和服务端暂停 / 继续 / 检查点 / 整树终止控制面；完成时继续按本规则判断哪些内容可进入用户手册。

## 2026-07-18 TH-6a1：任务树与服务端硬预算落地

**背景**：项目管理者确认 TH-6a0 合同后，授权开始第一个数据库 / 协议代码切片。由于本轮未注入 `decision_tier`，按 `AGENTS.md` 兜底作为执行 Agent，只完成 TH-6a1 并在验证、进度落盘后暂停。

### 已完成

- `agent_tasks` 新增 `parent_task_id`、`root_task_id`、`delegation_depth`、`may_delegate`，以及根任务保存的 `max_delegation_depth`、`max_running_descendants`、`max_running_per_target`、`max_nonterminal_descendants`。
- 新根任务创建后 `root_task_id` 指向自身；旧数据库升级时，每个历史任务回填为独立根、深度 0、`may_delegate=false`，默认治理值为 1 / 3 / 1 / 8，并补齐父任务、根任务和深度索引。
- 顶层自定义治理仅允许 Human 设置；普通 Agent 仍可按旧接口创建顶层任务，但不能为自己授予委派能力或放宽根预算。
- 创建子任务要求父任务处于 `running / in_progress`、父任务已获 `may_delegate`，调用者是父执行者、根请求者或 Human；项目从父任务继承，深度和非终态后代预算由服务端事务校验。
- 非终态后代预留通过更新根任务的条件语句串行化并发创建；子任务 claim 通过同一条件更新原子校验根仍在运行、根运行后代和单目标运行预算，直接 REST API 与第三方客户端无法绕过。
- `TalkClient` / `TalkClientSync.create_task` 新增父任务、委派权限和四项根预算参数；活服务测试分别用异步和同步 SDK 创建一层子任务并验证父根关联、深度与项目继承。
- `docs/spec/MODULE_tasks.md` 已同步当前实现、迁移兼容、已知边界与后续实施顺序；TH-6a2 的控制状态、有限授权和 runner 协作中断没有提前实现。

### 验证

- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py TALK\client\talk_client.py TALK\client\talk_client_sync.py tests\test_tasks.py tests\test_talk_client.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -v`：`Ran 23 tests ... OK`；覆盖旧库迁移、委派权限、深度 / 项目继承、非终态创建竞争、根运行并发和单目标 claim 竞争。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client -q`：`Ran 12 tests ... OK`。
- Task Hall / SDK / runner / 工具 / bridge 跨模块回归：`Ran 128 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 325 tests in 103.757s ... OK`。

### 变更文件

- 功能：`server/models.py`、`server/db.py`、`server/routes/tasks.py`、`TALK/client/talk_client.py`、`TALK/client/talk_client_sync.py`。
- 测试：`tests/test_tasks.py`、`tests/test_talk_client.py`。
- 文档：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。

### 已知边界与下一步

- 当前根任务尚无 `control_status`、授权 epoch 或切片额度；Human 仍不能通过服务端暂停整棵树，bundled runner 也没有最长 5 秒的暂停 / 终止轮询。
- 根任务当前仍可在后代未结束时自行完成，整树汇总与质量门禁要在后续控制、Review/Test 切片中收敛。
- 下一候选切片是 TH-6a2；按执行 Agent 规则，本轮不提交、不推送、不自动继续，等待项目管理者或决策 Agent 确认。

## 2026-07-18 TH-6a0：任务治理、可中断推进与质量门禁合同冻结

**背景**：TH-5 已贯通“页面委派 → bundled runner → Task Hall 结果 → Human 收取”的基础链路。项目管理者随后确认，下一阶段不能只补递归委派和澄清，还要把开发后的独立 Review、里程碑黑盒测试、人工验收，以及“主 Agent 有限自主推进、Human 可随时喊停”纳入正式流程。本切片只冻结协议和实施顺序，没有修改功能代码。

### 已确认的总体流程

```text
Human 有限批次授权
  -> 主 Agent 分配 development
  -> 开发 Agent 实现并自测
  -> 独立 review（不通过则 rework，最多自动两轮）
  -> 未到检查点时在剩余额度内继续
  -> 里程碑完整自动化回归 + 黑盒 / E2E test
  -> 根任务 awaiting_human
  -> Human 验收、调整、继续一批或终止
```

- 主 Agent 获得有限批次授权而非无限自治：普通小切片默认 2 个，纯文档 / 配置可显式授权到 3 个，高风险 / 跨模块默认 1 个。
- 批次、时间、风险、额度、Review、澄清或里程碑边界会自动暂停；Human 也可随时撤销尚未消费的授权。
- Review 覆盖每个功能切片，但低风险同模块任务允许 2–3 个批量审查；黑盒测试只在可独立体验的里程碑运行。
- 里程碑测试通过不等于自动进入下一阶段，根任务必须等待 Human 显式确认。

### 冻结的任务树与预算合同

- 新增 `parent_task_id / root_task_id / delegation_depth / may_delegate` 语义，旧任务迁移后各自成为独立根并保持兼容。
- 根任务统一保存最大深度、根运行并发、单目标并发和非终态后代预算；默认分别为 1、3、1、8。
- 创建子任务时校验调用者、父任务、根控制状态、委派权限、深度和非终态预算；claim 时再次原子校验根与单目标并发。
- 子任务默认不能继续委派，只有根控制者显式提高深度并授权具体任务后才能突破默认能力边界。
- 直接 REST API、TALK 自带工具和第三方客户端适用相同拒绝规则，不能依赖 runner 工具裁剪或进程内锁。

### 冻结的有限授权与暂停合同

- 根任务使用独立 `control_status`：`active / pause_requested / paused / awaiting_human / cancel_requested / canceled`，不污染现有执行五态和协作状态。
- 每次 Human “继续一批”生成新的 `authorization_epoch`、切片预算和有效期；陈旧主 Agent 不能使用旧授权继续创建任务。
- `pause-tree` 立即禁止新建后代和 claim；bundled runner 最多每 5 秒检查控制指令，安全终止本地子进程并失效 claim token。
- 暂停后的任务保留 Hall、消息、attempt 与现场，可恢复为 `queued / accepted` 后重新领取；整树终止与可恢复暂停严格区分。
- 第三方 runner 若不支持协作中断，服务端至少撤销写回资格并依靠租约回收，不承诺跨机器强杀未知进程。

### 冻结的澄清与质量门禁合同

- 澄清默认最多 1 轮、显式可提高到 2 轮；一轮是 B 的集中问题批次与 A 的完整答复，不按消息数计数。
- A 可连续补充多条消息，以 `submit-clarification-answer` 显式结束答复；额度耗尽仍不足时进入 `needs_decision` 并暂停根任务。
- 新增 `general / development / review / test / rework` 任务类型；Review / Test 使用独立 Task Hall 和结构化 `gate_verdict`，不能从自然语言猜测通过结论。
- Review 结论为 `approved / changes_requested / blocked`，测试结论为 `passed / failed / blocked`；返工产生新任务并保留旧结果。
- 旧冻结版本的 Review / 测试结论在新返工后失效；必需 Review 或里程碑最新测试未通过时，服务端拒绝根任务提交成功结果。
- `business_role` 保持项目自定义自由文本；工具和项目 API 返回角色与能力摘要，但质量强语义由 `task_kind`、任务关系和门禁结论提供。

### 实施顺序

1. TH-6a1：任务树字段、迁移和服务端硬预算。
2. TH-6a2：有限批次授权、暂停 / 继续 / 整树终止与 runner 协作中断。
3. TH-6a3：澄清轮次账本、答复提交和 `needs_decision`。
4. TH-6b：runner 领取前预检、完整 Hall 上下文与自动澄清。
5. TH-6c：Review / 返工门禁和角色发现。
6. TH-6d：里程碑测试、Blackboard 控制和人工验收暂停。
7. TH-7：Codex Desktop / 通用终端接入。

### 验证与变更

- 验证：仅文档切片；完成 Markdown 结构、关键合同覆盖和 `git diff --check` 检查，未运行功能测试。
- 变更文件：`docs/spec/MODULE_tasks.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 提交状态：当前按执行 Agent 规则未提交，等待项目管理者确认是否进入 TH-6a1 或先提交文档切片。
- 下一步：TH-6a1，实现任务树字段、旧库迁移和服务端硬预算并发测试。

---

## 2026-07-16 Task Hall 委派深度、并发预算与澄清轮次决策

**背景**：项目管理者在准备切换上下文前，确认需要为跨终端委派加入类似 Codex 子 Agent 的递归与并发保护，并讨论任务执行者领取前是否只允许一次澄清机会。本轮只核对现状、冻结产品规则和更新进度，没有修改功能代码。

### 现状核对

- bundled runner 的嵌套任务命令默认不向执行模型暴露 TALK 委派工具，因此标准路径近似默认委派深度 1；但这是客户端 / runner 软保护。
- `POST /api/tasks` 仍允许任意已认证成员创建任务，`agent_tasks` 尚无父任务、根任务、委派深度、委派授权或任务树预算字段；自定义客户端仍可能递归创建任务。
- 单个 bridge 进程使用共享运行锁串行调用模型，但多个 bridge 实例之间没有根任务级 / 项目级并发上限；claim 只防止同一任务被重复执行，不限制任务树扇出。
- Task Hall 已有 `clarification_requested`、Hall 消息、`accept` 和待澄清禁止 claim 的基础状态，但没有澄清轮次、明确的答复提交动作或额度耗尽后的阻塞状态。Discussion Hall 的 `max_rounds` 与该流程无关。

### 已确认的硬保护默认值

- 服务端默认最大委派深度为 1；子任务默认不能继续委派，只有主控显式授权时才能获得继续拆分能力。
- 单个根任务同时执行的子任务上限为 3；单个目标 Agent 同时执行上限为 1；单个根任务累计非终态子任务上限为 8。
- 保护必须在任务创建、领取等服务端入口原子校验，覆盖 TALK 自带工具、直接 REST API 和第三方客户端，不能只依赖 bundled runner 的工具裁剪或进程内锁。
- 实现需要补父任务 / 根任务关联、委派深度与授权、并发 / 扇出预算等字段；具体字段名可在 TH-6a 收敛，但已确认的默认行为保持不变。

### 已确认的澄清规则

- 默认最多 1 个澄清轮次；复杂任务可由主控在委派时显式提高到 2 轮，不允许无限追问。
- 一轮表示“B 的一批集中问题 + A 的完整答复”，而不是只能写一个问句或一条消息。B 应一次汇总所有已知疑问，可在同一 Hall 消息中使用多个编号问题。
- A 可以在同一 Hall 连续补充多条说明，最后通过显式“提交澄清答复”动作结束该轮并唤醒 B；普通回复消息不应过早触发 B 重新判断。
- B 被唤醒后携带任务原文和按时间排序的完整 Hall 上下文重新预检；信息充分才 `accept → claim → execute`。
- 澄清额度耗尽后仍无法执行时，任务必须进入 `blocked / needs_decision`（最终状态名在实现时收敛）并交回主控修改、取消或显式授权，禁止强制领取或猜测执行。

### 下次恢复顺序

1. TH-6a：先落服务端任务树、深度 / 并发预算和澄清轮次协议及数据库迁移、SDK / 工具契约与并发测试。
2. TH-6b：再接 bundled runner 领取前预检、同 Hall 提问 / 等待 / 唤醒、完整分页上下文重放和幂等保护。
3. TH-7：最后补 Codex Desktop / 通用终端接入包装并做完整跨终端验收。

### 验证与变更

- 验证：完成代码与协议的只读核对；本轮没有功能代码变更，因此未运行测试套件。
- 变更文件：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 待确认：无；产品默认值和失败 / 阻塞原则已由项目管理者确认。

---

## 2026-07-16 TH-5 人工验收反馈与后续澄清 / 终端接入决策

**人工反馈**：项目管理者已通过页面委派任务并成功拿到返回结果，确认 Project Blackboard → bundled runner → 对应 Task Hall → 结果收取的基础链路可用。本轮未继续开发，只沉淀下一阶段需求与当前边界。

### 已确认的澄清流程

- 一项任务始终使用创建时生成的同一个 Task Hall，请求者 A 与执行者 B 的成员关系固定。
- B 在领取前发现信息不足时，应先把问题写入该 Hall，并将任务置为 `queued / clarification_requested`；“停止领取”只表示暂不 claim / 执行，runner 仍继续监听任务和 Hall。
- A 在同一 Hall 回复后，B 应携带原始任务和按时间排序的全部问答重新判断；信息充分则 `accept → claim → execute`，仍不足则继续在同一 Hall 提问。
- 当前服务端已有提问、回复、`clarification_requested`、`accept` 和待澄清禁止 claim 的基础能力，但 bundled runner 仍会直接领取 `assigned` 任务，尚无领取前预检、等待答复和重新唤醒闭环。

### 上下文边界

- Hall 消息会完整持久化，A / B 都有读取权限；Web 和 async client 支持分页读取。
- `talk_get_task` 当前只返回最近 50 条 Hall 消息，正式 runner prompt 目前仅包含任务标题 / 正文，因此“消息已保存”不等于“执行模型已获得完整上下文”。
- TH-6 必须在每次预检和正式执行前分页读取 Hall，并按顺序注入任务原文、B 的问题、A 的回答及后续多轮澄清；还需覆盖重复唤醒幂等与等待期间不 claim。
- 文件消息可保留附件元数据，但附件正文自动下载 / 注入策略仍待后续确定。

### 终端委派方向

- 通过 TALK bridge 启动的 Codex CLI 和 pi 已提供 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result`。
- CLI 已具备直接自然语言委派的底层能力；普通 Codex Desktop 会话尚未自动注册 TALK MCP，需要增加项目上下文、成员身份、API Key 与工具注册的接入包装。
- TH-7 目标链路：终端 A 委派 → B 在 Hall 澄清 → 终端 A 读取并回复 → B 执行 → 结果回同一 Hall → 终端 A 收取。

### 下次恢复顺序

1. 先开发 TH-6 领取前预检、自动澄清和完整 Hall 上下文重放。
2. TH-6 通过自动化与真实模型验收后，再进入 TH-7 Codex Desktop / 通用终端接入包装。

---

## 2026-07-16 TH-5：Project Blackboard、Task Hall Web UI 与真实跨模型链路

**背景**：项目管理者明确表示逐片确认缺少直观价值，希望等“任务创建 → runner 执行 → 结果写入 Task Hall → 人类收取”整个流程可见后再介入。本轮因此把 Web 可视化、bundled runner 活服务链路和真实 Codex / pi CLI 冒烟作为同一个里程碑收口。

### Project Blackboard / Task Hall Web UI

- Web UI 登录后以 Project 为一级工作范围，默认打开项目任务黑板；当前项目按成员保存在本地浏览器。
- 黑板按“待响应 / 执行中 / 结果待收取 / 已结束”四列聚合任务，并在详情面板保留待确认、待澄清、已接受等精确协作状态。
- 新增页面委派表单，可选择项目 Agent、填写标题与正文；创建后服务端自动生成的 Task Hall 会出现在项目 Hall 列表。
- 任务详情显示请求者、执行者、运行状态、attempt 与租约，并按权限提供进入 Hall、请求澄清、接受、收取结果和取消未领取任务动作。
- Task Hall 继续复用既有消息时间线、回复和文件能力；任务状态每 5 秒刷新，runner 回写后黑板自动进入“结果待收取”。

### runner 输出所有权修复

- 真实 pi 冒烟首次发现：嵌套模型调用 TALK 工具写入 Hall 后，runner 又回写 visible reply，单任务产生 3 条重复结果。
- Codex / pi bridge 现在为队列 worker 解析独立 `task_command`：保留 discussion / tools 权限档，但不暴露 TALK 结果投递工具；交互消息继续使用原命令，不影响终端 Task Hall 工具。
- 新增任务专用 system prompt，明确单轮执行、优先遵循任务正文、避免无必要反问，并由 runner 独占 Hall 结果写入与 complete。
- 真实 pi 复测结果从 3 条收敛为 1 条；Codex 当前任务命令同样只写一条结果。

### 自动化与真实验收

- 新增 `tests/test_task_web_ui.py`，锁定 Project Blackboard / Task Hall 静态结构、项目任务 API 与安全 `textContent` 渲染。
- 新增 `tests/test_task_hall_e2e.py`，在活 FastAPI 服务上贯通 SDK 创建、runner claim / 执行、Hall 结果、complete 和请求者 collect。
- Browser 真实交互贯通登录、空黑板、页面委派、进入 Hall、发送协作消息、runner 结果出现、收取完成与“已结束”分栏；1280px 四列布局修正后无多余横向滚动，控制台 error / warning 为 0。
- 真实 Codex 0.144.4 使用当前无 TALK MCP 的任务命令返回 `Codex Task Hall connected.`，单条 Hall 结果并完成收取。
- 真实 pi 0.80.3 使用当前无 TALK 工具的任务命令完成 claim、单条 Hall 回写与收取；模型会把逐字回复要求改写为简短确认，记录为模型输出质量边界，不视为基础设施链路失败。

### 验证

- Python `py_compile`、`node --check web\app.js`、`node --experimental-strip-types --check bridges\talk_tools_extension.ts` 与 `git diff --check`：通过。
- 定向 Web / runner / client：`Ran 124 tests ... OK`。
- 全量回归：清理真实验收服务后 `Ran 321 tests in 98.917s ... OK`。
- 首次全量运行时一个既有 WebSocket 降级测试在固定 2 秒清理窗口超时；关闭并行真实服务后该用例连续两次单测通过，第二轮全量也通过。

### 下一步

- 当前已达到人工验收门禁：项目管理者可只通过页面完成一次真实委派、观察结果进入对应 Hall 并收取。
- 人工验收通过后关闭 Task Hall 当前里程碑，再决定运行中协作取消、返工 / observer、后台 schedule 或项目级 Members / Activity 的优先级。

---

## 2026-07-16 TH-4：claim lease / attempt 与 runner 过期回收

**背景**：项目管理者接受 TH-3，并明确逐片人工验收缺少直观价值，后续人工介入点应放在完整委派流程里程碑。本轮先提交 TH-3 为 `ff8f8a8`，再补齐同一任务只能由一个有效 runner 持有的可靠性协议。

### 实现

- `AgentTask` 新增 `attempt`、私有 `claim_token`、`lease_expires_at` 与 `heartbeat_at`；旧库通过 `init_db()` 增量迁移并建立租约截止索引。
- claim 改为数据库条件更新，多个实例并发领取只有一个成功；同一实例重复 claim 保持 attempt / token 不变。
- 新增 `POST /api/tasks/{id}/heartbeat` 与 `POST /api/tasks/requeue-expired`。过期 claim 回到 `queued / accepted`，旧实例进入 `error`，下一次领取递增 attempt 并生成新 token。
- complete 原子校验当前 token 和未过期租约；陈旧 token 与重领后缺少 token 的提交均被拒绝。首次 attempt 暂时允许省略 token，兼容尚未升级的第三方 runner。
- async / sync client 新增 heartbeat 与过期回收 helper，并扩展 claim / complete 参数。
- bundled runner 默认使用 120 秒 lease、30 秒心跳；轮询前先回收自己的过期任务。租约丢失时取消本地子进程，不发送 Hall 结果，也不提交陈旧完成状态。
- 运行中取消的错误提示同步调整：lease 基础已经存在，剩余缺口是请求者触发的 runner 协作中断协议。

### 验证

- Python `py_compile` 覆盖模型、迁移、路由、client、runner 与相关测试：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- 定向 tasks / client / CLI bridge / Codex bridge / Task Hall tools：`Ran 141 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 313 tests ... OK`。
- 新测试覆盖真实并发 claim、幂等重试、心跳续租、过期回队、attempt 递增、陈旧完成拒绝、SDK 活服务和 runner 租约丢失取消。
- `git diff --check`：通过；本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- 无 lease 字段的历史 `running` 任务不会被自动回收，避免升级时误终止旧 runner。
- 当前仍只允许取消未领取任务；运行中取消需要协作中断状态与 runner 主动停止协议。
- 下一切片进入 Project Blackboard + Task Hall Web UI，让项目管理者第一次可以从页面直观看到并操作完整任务流程。

---

## 2026-07-15 TH-3：终端 MCP / pi Task Hall 工具闭环

**背景**：TH-2 已完成 async / sync client 与 bundled runner Hall 回传，并提交为 `99e8a28`。本轮按项目管理者确认推进一个终端接入切片，让 Codex 与 pi 的实际操作终端可以发现 Agent、委派任务、处理澄清并收取结果。

### 实现

- 新增 `bridges/talk_task_tools.py`，统一实现 `talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result` 八个 HTTP-backed Task Hall 工具及 schema / dispatch。
- `bridges/talk_send_mcp.py` 在保留 deferred `talk_send` 的基础上注册全部 Task Hall 工具；`bridges/talk_tools_extension.ts` 为 pi 提供同名工具面。
- Codex discussion profile 与 pi 的 discussion / tools profile 均获得对应工具；bridge 从项目目录 `.talk/project.yaml` 注入默认 `TALK_PROJECT_ID`。
- Agent 发现结合项目 profile、成员与实例状态；等待采用最长 30 秒的有界轮询；Hall 回复可同时推进请求澄清或接受动作。
- 服务端及 async / sync client 新增取消动作。只有原请求者可幂等取消未领取任务；运行中取消返回 `409`，避免在没有 lease / runner 中断协议时伪造停止。
- 新增 MCP 真实工具调用、桥接项目上下文、pi 工具面一致性与活服务完整委派流程测试；现有 task、client 和 bridge 测试同步扩展。

### 验证

- Python `py_compile` 覆盖服务端、两套 client、bridge、Task Hall 工具和相关测试：通过。
- `node --experimental-strip-types --check bridges\talk_tools_extension.ts`：通过。
- `tests.test_talk_task_tools`：`Ran 4 tests ... OK`；`tests.test_talk_client`：`Ran 12 tests ... OK`。
- `tests.test_pi_bridge + tests.test_codex_bridge`：`Ran 29 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 309 tests ... OK`。
- `git diff --check`：通过；本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- `talk_wait_tasks` 当前是客户端有界轮询，不是服务端事件流；Agent 发现结果尚未带项目业务角色。
- 取消当前只覆盖未领取任务；运行中取消、超时回收和重领需要 claim lease / attempt 与 runner 中断协议。
- 按执行 Agent 单切片门禁暂停，等待验收后再进入 claim lease / attempt，不提前开发 Project Blackboard / Task Hall Web UI。

---

## 2026-07-15 TH-2：async / sync client 与 bundled runner Task Hall 接入

**背景**：TH-1 已完成 Task Hall 数据 / API 地基。本轮按项目管理者确认，只推进一个 SDK / runner 切片：让实际终端 client 能使用项目化任务与协作动作，并让 bundled runner 的最终结果落到任务专属 Hall。

### 实现

- `TalkClient` 与 `TalkClientSync.create_task()` 新增可选 `project_id`；`list_tasks()` 新增 `workflow_status` 与 `project_id` 过滤。
- async / sync client 新增 `get_task()`、`request_task_clarification()`、`accept_task()` 与 `collect_task_result()`，覆盖 TH-1 已落地的单任务查询和协作动作 API。
- 通用 `cli_bridge` runner 与 `codex_bridge` 兼容任务处理入口会从 claim 响应读取 `hall_group_id`，将成功或失败的可见结果写入对应 Task Hall，再用消息 id 完成任务。
- 旧任务没有 `hall_group_id` 时继续写入全局时间线，保持服务端与 runner 的兼容路径。
- `tests/test_talk_client.py` 新增 sync 活服务全流程，并扩展 async 流程覆盖项目过滤、澄清、接受、Hall 结果、提交和收取；bridge 测试分别覆盖 Task Hall 回传与旧任务兼容。

### 验证

- `py_compile` 覆盖两套 client、两条 bridge 入口和三份相关测试文件：通过。
- `tests.test_talk_client`：`Ran 12 tests ... OK`。
- `tests.test_cli_bridge`：`Ran 85 tests ... OK`；`tests.test_codex_bridge`：`Ran 19 tests ... OK`。
- `tests.test_tasks + tests.test_pi_bridge`：`Ran 26 tests ... OK`。
- 全量 `.venv\Scripts\python.exe -m unittest discover -s tests -q`：`Ran 304 tests ... OK`。
- 本切片无前端改动，不需要 Browser 验证。

### 边界与下一步

- 当前 client 已具备项目化创建、查询与协作动作；终端 MCP 仍缺 Agent 发现、委派、等待、纠偏 / 取消和批量结果收集工具。
- observer、返工、lease / attempt、Project Blackboard 与 Task Hall Web UI 仍未进入实现。
- 按执行 Agent 单切片门禁暂停，等待项目管理者或决策 Agent 验收后再进入终端 MCP 切片。

---

## 2026-07-15 TH-1：Task Hall 数据 / API 地基

**背景**：项目管理者确认先实现 Task Hall，并批准首个数据库 / 协议切片采用“复用 Group + 双状态”方案：不新增 thread 表，`AgentTask.status` 继续服务现有 runner，另设协作状态表达澄清、接受、提交和结果收取。

### 决策与实现

- `AgentTask` 新增可选 `project_id`、唯一 `hall_group_id`、`workflow_status` 和 `result_collected_at`；`init_db()` 为旧库补列、建索引，并把旧五态回填为对应协作状态。
- `POST /api/tasks` 原子创建 `groups.type=task` Hall，请求者与执行者固定为不同成员；请求者是 `owner`、执行者是 `member`。schedule 每次物化也建立独立无项目 Hall。
- 保留执行五态 `queued/running/succeeded/failed/canceled`；协作状态新增 `assigned/clarification_requested/accepted/in_progress/submitted/completed/failed/canceled`。
- 新增 `GET /api/tasks/{id}`、`workflow_status/project_id` 列表过滤，以及 `request-clarification`、`accept`、`collect-result` 三类动作；澄清状态阻止 claim，成功 complete 只到 `submitted`，请求者收取后才到 `completed`。
- 关联 Task Hall 不能通过普通 Group API增删成员或独立删除，避免一任务一 Hall 的 1 对 1 结构被拆散。
- 为兼容现有外部客户端，`project_id` 暂时可为空；结果消息接受对应 Hall 或旧全局时间线，但拒绝其它 Hall。bundled runner 改为 Hall 回传留到下一切片。

### 测试与验证

- `tests/test_tasks.py` 从 11 个扩展到 16 个测试，新增项目关联 / 自动建 Hall、完整协作流程、权限、结构保护、schedule Hall 和旧库迁移覆盖。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\db.py server\routes\tasks.py server\routes\groups.py tests\test_tasks.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks -v`：`Ran 16 tests ... OK`。
- 任务相关七模块最终回归：`Ran 200 tests ... OK`；其余十四模块：`Ran 103 tests ... OK`，最终代码合计 303 项通过。
- 核心实现完成后的单次 unittest discovery 曾 `Ran 303 tests ... OK`。最后一次单进程复跑在活服务测试退出阶段未结束而被工具超时终止，无断言失败；随后以上述 200 + 103 分批复跑覆盖全部模块，不把超时轮次记为通过。
- 纯后端数据库 / API 切片，无前端或 Browser 验证。

### 文档与下一步

- 更新 `docs/spec/MODULE_tasks.md`、`docs/PROJECT_BRIEF.md`、`docs/PROGRESS.md` 和本历史记录，使实现态、兼容边界和后续顺序一致。
- 下一切片扩展 async / sync client 与 bundled runner：支持项目化委派、协作动作和 Task Hall 结果回传；完成后仍按单切片暂停验收。

---

## 2026-07-15 Task Hall 开工前清理

**完成**

- 明确 `agent-docs/BLACKBOARD.md` 为本地协作文件；保留本地文件和 `.gitignore` 规则，从 Git 索引移除，不再作为项目文件维护。
- 将 `docs/PROGRESS.md` 从混合历史记录精简为当前快照，仅保留 Task Hall 目标、待决实现选择、下一切片、验证基线和有效技术债。
- 已完成切片、历史测试和长期方向未删除，仍由本文件及 `docs/spec/PROJECT_INTEGRATION.md` 保存。

**下一步**

- 进入 Task Hall 数据 / API 地基切片；先复核现有任务、Group、消息和成员模型，再确定一任务一 Hall 的最小兼容关联方案。

---

## 2026-07-15 BS-3a：汇总 grounding + bridge 推断 decision（Discussion 分支收尾）

**背景**：BS-3 真机 v2 证明 BS-2b 的通用历史块在技术上已注入，但模型仍可能忽略实际意见、引用旧成见或私信重问；汇总纯 prose 又统一被记为 `answer`，导致 session 虽可能被 closure 收掉，却留下 `end_reason=null`。项目管理者确认先做一个限定范围的 Discussion 收尾切片，再关闭当前分支并转入 Task Hall。

### 决策

- **D-i 采用内联 grounding**：汇总触发时按 `discussion_turns` 为每个 `agent:*` 参与者选择首条 `answer` reply，再按 `message_id` 取回原文。决策人的前置意见与其他 Agent 一样纳入；后续闲聊 / 重复 answer 不进入材料。
- **D-ii 采用 bridge 推断**：仅在 active 多方 brainstorm、human 单独定向当前决策人、文本明确要求汇总、全部 Agent 意见取齐、CLI 成功并返回非空回复时，把回复强制记为 `decision`，再复用 `_resolve_if_decision_maker` 收口。
- **D-iii 保持原协议**：决策人先贡献一条普通 `answer`，最终再单独产出 `decision`。

### 实现

- `bridges/cli_bridge.py`
  - 新增汇总意图 markers 与 `_is_brainstorm_summary_request`，校验 Hall 类型、human 来源、单目标、决策人身份和 active 多方参与关系。
  - 新增 `_brainstorm_summary_grounding`：必须取齐每位 Agent 的首条意见原文，单条最多 4000 字；撤回、正文缺失或成员不全时返回空，不自动收口。
  - 汇总轮使用专用材料块替代通用 BS-2b 历史；其它多方轮次保持原行为。
  - 成功汇总 prose 或错误 mark stance 均归一为 `decision`；CLI 超时 / 失败或无可见回复不触发。
- `tests/test_cli_bridge.py`
  - 覆盖首条意见选择、决策人意见包含、后续噪声剔除、成员未齐拒绝、直接点名守卫，以及完整的 prose → `decision` → `resolved+consensus` 路径。

### 文档

- `docs/spec/MODULE_discussions.md`：补当前 `decision/end_reason` 能力、BS-3a 行为合同和验收点。
- `docs/spec/DELIBERATION.md`：登记 D-i / D-ii / D-iii 决策、严格守卫、BS-3 与 BS-3a 状态。
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`：登记分支收尾、验证和残余人工验收。

### 验证

- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge`：`Ran 85 tests ... OK`。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge`：`Ran 147 tests ... OK`。
- 真实模型最终汇总质量未在本切片重跑：检查时 8000 / 8001 / 8010 均无 server 监听，存在此前留下的 bridge 重连进程；未擅自终止这些进程或把自动化结果写成真机通过。

### 分支交接

- `claude/phase3-collab-and-ui` 在本片提交并推送后关闭开发。
- 已从最终提交 `1da4797` 创建并切换到 `codex/task-hall`，进入 Task Hall 数据 / API 最小闭环；本轮只完成分支接力，不提前开发下一切片。

---

## 2026-07-15 Task Hall 产品方向收敛（文档切片）

**背景**：项目管理者重新确认 TALK 的实际使用方式：用户在 Codex、Claude Code 等真实终端中推进总目标，主 Agent 在过程中按角色把子任务通过 TALK 分给其他模型 Agent；任务完成后，结果必须回到 TALK，来源终端再查询 / 等待并整合。Desktop 与 CLI 不共享同一对话上下文可以接受，TALK 承担跨入口持久化真相源。

### 已确认决策

- 产品级 Hall 分为 **Task Halls** 与 **Discussion Halls**。当前先完成 Task Hall，Discussion Hall 的多角色讨论效果后续继续。
- 一项委派任务自动建立一个独立 Task Hall；执行关系固定为请求者 A ↔ 执行者 B 1 对 1。项目所有者 / 决策 Agent 可观察、介入和验收，但不成为第三个执行参与者。
- 标准流程为：A 指派 → B 可选提问 → B 接受 → 执行 → 提交结果 → A 的终端获取并验收。提交结果与来源终端已收取结果需要可区分。
- 任一接入 TALK MCP / client 的交互终端都获得跨模型“子 Agent 委派”能力，不依赖终端原生 subagent 功能。
- bridge / runner 是独占领取并驱动目标模型执行的基础设施，不是第三类 Agent，也不代表额外订阅；TALK 通过 claim / lease 防止同一任务被多个 runner 重复执行。
- Web UI 按 Project 组织，默认提供 Blackboard 聚合 Task Hall 状态；Task Halls 与 Discussion Halls 分区，点击黑板任务进入对应独立 Hall。

### 文档落盘

- `docs/spec/POSITIONING.md`：更新产品定位、Hall 两类结构、混合终端 / runner 模型和当前优先级。
- `docs/spec/MODULE_tasks.md`：新增 Task Hall 产品合同、标准流程、终端能力、数据关联草案与 Web 信息架构；明确区分现有实现和目标态。
- `docs/spec/PROJECT_INTEGRATION.md`：补充项目级任务关联、终端接入、路线调整和关键决策记录。
- `docs/PROJECT_BRIEF.md`：同步公共上下文、当前前端与目标态差异、模块索引状态。
- `docs/spec/PRODUCT.md`：标记为历史 MVP 基线，避免“多房间不做”继续覆盖当前方向。
- `docs/spec/DELIBERATION.md`：保留已有 Discussion Hall 设计与代码，标记 BS-3 等后续工作在 Task Hall 里程碑后恢复。
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`：登记方向、当前状态、实现待决项与下一步。

### 实现待决项

- Task Hall 最终直接复用 `groups.type=task`，还是新增专用 thread 实体。
- 目标流程如何兼容现有 `queued/running/succeeded/failed/canceled`，是否引入独立 `submitted` / `result_collected` 状态。

这些是首个实现切片需要定稿的技术选择，不改变“一任务一 Hall、1 对 1 执行、项目聚合、结果可收取”的产品合同。

### 验证

- `git diff --check`：通过。
- Markdown 本地链接校验：通过。
- 关键术语一致性检查：通过。
- 纯文档切片，未运行代码测试或 Browser 验证。

### 下一步

- 由决策 Agent / 项目管理者验收本次方向文档。
- 下一开发切片从 Task Hall 数据模型与 API 最小闭环开始；涉及数据库 / 协议，完成后暂停验收。

---

## 2026-07-15 BS-2b：多方场发言可见性（真机 v2 卡第二步的修复，决策 Agent 自行开发）

**背景**：BS-3 真机验收 v2 第一步（各自想法）正常，但第二步"逐一表态"时 agent 反馈"不知道对方发了哪条"——卡住。诊断根因：pi/codex 的 prompt（`build_cli_prompt` 紧凑分支）**只含触发消息 + 角色注入**，无任何 Hall 历史；`discussion_context`（带 turns 的那段）对 pi/codex 是 5.x 时故意砍掉的（防"已经XX啦"元叙述），且它本就不含 turn 的正文内容。→ 表态/汇总这类"对别人发言的反应"结构上拿不到别人说了什么。

### 完成事项（仅 `bridges/cli_bridge.py` + `tests/test_cli_bridge.py`）

- `_shared_discussion_history(client, group_id, discussion, current_message_id, self_id)`：只对 >2 参与者的多方场生效；`client.fetch_history(group_id, since=root-1)` 拉本场从开场起的群发言，拼成"speaker：内容（截 240）"回顾块（剔除当前触发消息/空内容/撤回，最多 24 条），框成"【本场已有发言…请勿逐条复述】"。1:1/free/无场 → 空串；拉历史失败（无方法/404）降级空串不阻断。
- `build_cli_prompt` 加 `shared_history` 参数：pi/codex 紧凑分支在"任务行"后注入该块；通用分支也注入。默认空串 → 非多方场行为不变。
- `handle_incoming_message`：build prompt 前计算 `shared_history`（discussion 已由 BS-2 解析，含 agent 触发与 human 触发两路）。

### 为什么这次注入是安全的（对照 5.x 教训）

5.x 砍 `discussion_context` 是因为那段是**协议字段**（assignee_id/requester_id/remaining_auto_turns…），模型会把它当"任务完成状态"复述。本片注入的是**真实发言内容**（人读 Hall 看到的东西），且明确框为"仅供参考、勿复述"，且**只在多方 brainstorm 场**注入——1:1/free 的既有紧凑 prompt 一字未动。真机行为仍需重测确认（BS-3 v2 重跑）。

### 验证

- **自验（2026-07-15）**：`unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge` → `Ran 143 tests ... OK`（`test_cli_bridge` +3：多方拼块/1:1 空/prompt 注入）。另跑临时脚本验降级与剔除逻辑。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- 重跑 BS-3 真机 v2：第二步表态应能看到彼此想法；继续验到第四步 decision 收口。

---

## 2026-07-15 BS-2：bridge 多方场记账 + 回合预算按 N 放大（决策 Agent 继续自行开发）

**背景**：编排 v1（`spec/DELIBERATION.md §8`）第二片，管理者授权决策 Agent 继续直接开发。BS-1 建好"场"后，本片让 bridge 把真实头脑风暴流量记进这个场，并解除 1:1 回合预算对多方场的误伤。

### 完成事项（仅 `bridges/cli_bridge.py` + `tests/test_cli_bridge.py`）

- `_discussion_auto_turn_budget(discussion)`：多方场（>2 参与者）预算 = agent 数²+1（想法 N + 表态 N×(N-1) + decision 1）；1:1/无场保持常量 3。接入四处：agent 发送者刹车阈值（固定 `DISCUSSION_EXTENSION_CLOSE_TURNS` → `预算+1`，1:1 阈值仍为 4 不变）、deferred talk_send 预算、控制上下文 `remaining_auto_turns`。
- `_active_multiparty_discussion`：只匹配 active 且 >2 参与者的场——human 的普通消息不会被记进 1:1 讨论（既有流程零污染）。
- **human 发送者记账**：human 发起/点名（人驱动编排）时，agent 的可见回复记 turn 到多方场（`infer_reply_stance` → answer）；显式 `mark_stance`/talk_send 的 agree/disagree/decision 走原有路径落**同一场**（`_resolve_discussion_id` 的 participants 匹配可命中），D3-3a decision 收口链路依旧生效。human 发送者不注入 discussion 上下文、不受刹车（prompt 与 1:1 行为零变化）。

### 验证

- **自验（2026-07-15）**：`unittest tests.test_cli_bridge tests.test_messages tests.test_discussions tests.test_hall_types tests.test_codex_bridge` → `Ran 140 tests ... OK`（`test_cli_bridge` 78 = 75+3：预算缩放、human 广播回复记账到多方场、agent 消息在多方场 5 实质轮不触发 1:1 阈值收尾）。
- **已知观察点（留 BS-3 真机）**：表态/汇总的 stance 依赖 agent 实际用带 stance 的工具（模板文案已教）；纯口头回复会被记为 `answer`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `agent-docs/BLACKBOARD.md`（执行记录）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- **BS-3 真机验收 v2**：重启 server + 三 bridge，人按四阶段驱动一轮，验 turns 落账 + `resolved+end_reason=consensus`。

---

## 2026-07-14 BS-1：@所有人 × brainstorm 自动建多方 discussion + 模板四阶段（决策 Agent 获授权自行开发）

**背景**：编排 v1（`spec/DELIBERATION.md §8`）第一片。真机验收 v1 证实 @所有人 广播建不出 1:1 discussion、收口无处挂；BS-1 给后续 turns/decision 一个挂载点。**管理者本轮明确授权决策 Agent 直接开发本片**（工单仍走黑板留痕）。

### 完成事项

- `server/routes/messages.py`：
  - `_resolve_recipients` 返回 `(resolved_to, mention_all)`（唯一调用方 `create_message` 同步解包）。
  - 新增 `_maybe_create_brainstorm_discussion`：@所有人 且群 `type=brainstorm` → 消息落库后自动建多方 `DiscussionSession`（`root_message_id`=开场消息、`participant_ids`=全体群成员含发送者、`topic`=去 mention 正文截 80（空则"头脑风暴"）、`requester_id`=发送者、`max_rounds=agent 数+2`）。
  - 幂等守卫：该群已有 `active` 且参与者=全体成员的场次 → 跳过（一群同时一场）。
  - 容错：全程 `try/except`+`logger.warning`，建场失败不影响消息发送。
- `server/hall_types.py`：brainstorm `protocol_guidance` 改为四阶段协议（①需求 ②各自想法含决策人 ③点名表态 agree/disagree(否决附看法) ④决策人 decision 收口；未轮到不抢跑）；facilitator norm=「先贡献，等指示后汇总产出 decision」、contributor norm=「给想法；被点名时明确 agree/disagree」。
- 测试：`tests/test_messages.py` +4（建场字段断言含 max_rounds=4 / 幂等 / free 群不建 / 定向不建）；`tests/test_cli_bridge.py` 2 处文案断言同步。

### 验证

- **自验（2026-07-14）**：`unittest tests.test_messages tests.test_discussions tests.test_hall_types tests.test_cli_bridge` → `Ran 118 tests ... OK`；`tests.test_groups` 16/16。diff 自检（单调用方 / 挂钩位置 / 幂等 / 异常不阻断）。
- 限制：真机上 agent 回复是否落 turns 依赖 BS-2（bridge 侧），本片只建"场"。

### 变更文件

- `server/routes/messages.py` / `server/hall_types.py`
- `tests/test_messages.py` / `tests/test_cli_bridge.py`
- `agent-docs/BLACKBOARD.md`（工单 + 执行回贴）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`

### 下一步

- BS-2（bridge：广播 turns 落账 + 表态透传 + 多方回合预算）；执行者待管理者定。

---

## 2026-07-14 真机验收 v1（三 agent 头脑风暴）+ 编排 v1 设计定稿

**背景**：D3-1~3c 落地并推 GitHub（`8e1f029`）后，按黑板验收指南真机跑第一轮头脑风暴：「验收测试群」（brainstorm），codex=决策人(facilitator)、pi/pi-kimi=contributor，人（qa）发 `@所有人 …想 3 个点子…codex 最后收敛成结论`。

### 结果与发现

- **通过项**：三个 agent 均直接给出实质想法（消息 2412/2413/2416/2417/2418），氛围贴合头脑风暴——**D2 的 Hall 类型注入真机生效**；@所有人 展开/触发正常。
- **缺口 ①（结构）**：整轮**未创建任何 `discussion_session`**——现有创建路径是 1:1（`_resolve_discussion_id` 依赖 `peer_id`，requester↔assignee），@所有人 的 N 方广播建不出讨论 → turns/decision 收口（D3-3a）无处可挂。
- **缺口 ②（行为）**：无"该你归纳"的信号，codex（决策人）表现同普通贡献者，只报自己的点子、未汇总。
- **环境修复（codex 两层）**：`~/.codex/config.toml` 的 `service_tier="default"` 非法（删除后过配置解析）→ 又暴露老 CLI(v0.130.0-alpha.5) 不支持 `gpt-5.6-sol`（API 400）→ 管理者重装独立新 CLI，`_default_codex_exe()` 改走 PATH（删除写死的旧安装路径）。修复后 codex 正常回复。

### 决策（管理者 2026-07-14 定稿）

头脑风暴编排 v1 = **人驱动 + 四阶段**：① 人发需求（server 自动建多方 discussion）→ ② 每个 agent **含决策人**各给想法(answer) → ③ 人逐一点名，其他角色对每个想法一次表态（agree / disagree+自己的看法）→ ④ 人请决策人汇总(decision) → D3-3a 自动收口。已写入 `spec/DELIBERATION.md §8`；切片 **BS-1(server)/BS-2(bridge)/BS-3(真机 v2)**；D3-3d、timeout/manual、自动编排推迟。

### 变更文件

- `bridges/codex_bridge.py` + `tests/test_codex_bridge.py`（管理者改 codex 路径，随 BS-1 一并收口提交）
- `docs/spec/DELIBERATION.md`（§8 编排 v1）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

---

## 2026-07-14 D3-3c：收口 `end_reason` 归一（deadlock vs consensus）

**背景**：D3-3 第三片。修掉 D3-3b 的临时不精确——决策人收口时按讨论是否经 deadlock 移交，落 `deadlock` 或 `consensus`。`timeout`（轮次阈值语义待定）/ `manual`（缺人类"停"指令机制）本片刻意不做、显式 defer。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py` `_resolve_if_decision_maker`：确认「决策人 + stance=decision」后取讨论 turns（`_list_discussion_turns`，`try/except` 包裹）；若有 `stance="escalate"` 的 turn → `end_reason="deadlock"`，否则 `consensus`；取 turns 失败退化 `consensus`（收口不因此失败）。`stance!=decision` 早返回仍在最前（普通轮次零开销）；加 `isinstance(turn, dict)` 防御。
- `tests/test_cli_bridge.py`：+2（含 escalate turn → deadlock 收口、取 turns 失败 → consensus 退化）；既有 consensus / 非决策人不收口用例保持覆盖。

### 明确未做（defer）

- `timeout` / `manual` 两种 `end_reason` 未接入。
- 未删 / 未改 `escalated` 状态（D3-3d）。未改 server / prompt / 显式动作 / 其它切片。

### 验证

- **决策 Agent 复核（2026-07-14）**：`git diff` 仅 `_resolve_if_decision_maker` 内改动；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 75 tests ... OK`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- **D3-3d（破坏性）**：`escalated` 下线——旧 `escalated`→`resolved+deadlock` 迁移、从 `_DISCUSSION_STATUSES` 移除、bridge 改写不再写 `escalated`。**做前请管理者确认**（唯一有回滚风险的一片）。

---

## 2026-07-14 D3-3b：自动 handoff 目标从"只找 human"扩到"决策人"

**背景**：D3-3 第二片。把系统**自动**发起 handoff 的移交目标从"群里第一个 human"改为"本群决策人"（复用 D3-3a 的 `_find_decision_maker`，decision_tier=decision agent 优先、否则回退 human）。这样 deadlock 能交给 agent 决策人，它随后产出 `decision` → D3-3a 自动收口，闭环。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py`：
  - `_maybe_escalate_disagreement`（连续两轮 disagree 触发）自动目标 `_find_human_reviewer` → `_find_decision_maker`（消息文案/turn/target 一并更新；仍记 `escalate` turn + `status=escalated`）。
  - `_send_human_escalation` 的 fallback（未显式传 `human_id` 时）`_find_human_reviewer` → `_find_decision_maker`；显式传入 `human_id` 行为不变。
- **未动**（复核确认）：显式 `escalate_to_human` / `final_to_human`（agent 主动要人类裁决）保持 human-only；`escalated` 状态、`end_reason`、server、prompt 均未碰。
- `tests/test_cli_bridge.py`：更新 disagree 自动 handoff 用例断言 agent 决策人目标；+2（无决策人回退 human、显式 escalate_to_human 仍 human-only）。

### 已知临时不精确（留 D3-3c）

- deadlock 触发的收口目前仍被 D3-3a 标成 `end_reason=consensus`（D3-3a 对决策人 decision 一律 consensus）。D3-3c 会按触发原因归一（deadlock/timeout/manual）。

### 验证

- **决策 Agent 复核（2026-07-14）**：`git diff bridges/cli_bridge.py` 仅两处自动路径改目标；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 73 tests ... OK`。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3c：`end_reason` 归一到 deadlock/timeout/manual 各触发点。

---

## 2026-07-05 D3-3a：决策人 `decision` 收口 → `resolved`+`end_reason=consensus`

**背景**：D3-3（头脑风暴协议编排）拆 4 片，本片 D3-3a 是第一片——新增"决策人产出定论则收口"的路径，不碰现有 escalate/final 流程、不删 `escalated`。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- SDK `update_discussion` 加可选 `end_reason`（`talk_client.py` async + `talk_client_sync.py`）：未传时 body 只含 `status`（向后兼容，服务端 `model_fields_set` 不动 end_reason）。
- `bridges/cli_bridge.py`：
  - 新增 `_find_decision_maker(client, group_id)`：先找 `decision_tier=="decision"` 成员，否则回退第一个 `human:`。
  - `_update_discussion_status` 加 `end_reason` 透传（现有调用零变化）。
  - 新增 `_resolve_if_decision_maker`：`stance!="decision"` 先早返回（普通轮次不查 group，零开销）；决策人发 `decision` → `resolved`+`end_reason=consensus`；**非决策人不收口**。
  - 三落点挂钩：`_record_deferred_demand_turns`（deferred talk_send）、`execute_talk_actions` 的 send_message 分支、`handle_incoming_message` 回复路径。
- `tests/test_cli_bridge.py`：所有 `FakeClient.update_discussion` 加 `end_reason=None` 形参；+4 用例（决策人 send 收口、非决策人不收口、无 decision_tier 时 human 回退不收口、决策人 mark_stance 收口）。

### 验证

- **决策 Agent 独立复跑（2026-07-05）**：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_discussions` → `Ran 80 tests ... OK`（test_cli_bridge 71 + test_discussions 9）；bridge diff 逐条复核，护栏（非决策人不收口 / 现有 escalate/final/escalated 未动）确认。

### 变更文件

- `TALK/client/talk_client.py` / `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3b：handoff 目标从"只找 human"扩到"决策人（decision_tier=decision 优先）"。

---

## 2026-07-04 D3-2：bridge 接 `decision` 立场（plumbing，纯加法）

**背景**：承接 D3-1（`afc1eb7`，server 已认 `decision`）。本片让 bridge 也把 `decision` 当合法、实质、不受轮次刹车的立场正确接住。纯机械改动，不碰编排/prompt/escalated（D3-3）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `bridges/cli_bridge.py`：仅 `ACTION_STANCES` 加 `decision` → 动作解析（`stance not in ACTION_STANCES → None`）不再把 `stance=decision` 抹掉。
- **护栏未破**（复核确认）：`NON_SUBSTANTIVE_STANCES`（仍 `{greeting, closure}`）→ `decision` 被 `_substantive_discussion_turns` 当实质轮次；自动轮次刹车元组（仍 `{greeting, answer, agree, closure}`）→ `decision` 不受 turn limit skip；`infer_*`/prompt/`escalated` 均未动。
- `tests/test_cli_bridge.py`：+2 —— `decision` `TALK_ACTION` 解析后 stance 保留（不被置 None）+ 计入实质轮次；轮次预算耗尽时 `decision` deferred talk_send 不被 skip（对照 `answer` 被 skip）。

### 验证

- **决策 Agent 复核（2026-07-04）**：`git diff bridges/cli_bridge.py` 仅 1 行；`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` → `Ran 67 tests ... OK`（原 65 + 2 D3-2）。

### 变更文件

- `bridges/cli_bridge.py` / `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-3（重头）：结束归一 + 决策人 `decision` 收口 + 轻编排 + prompt 指引 + `escalated`→`resolved+deadlock` 迁移下线。

---

## 2026-07-04 D3-1：审议数据层地基（stance `decision` + `end_reason`，纯加法）

**背景**：进入审议主线 D3（头脑风暴协议）。因改动面大（stance/status 迁移 + 结束归一 + 决策人收口 + 轻编排），拆为 3 片：D3-1 数据层、D3-2 bridge stance、D3-3 结束归一/编排/escalated 下线。本片 D3-1 只做数据层地基，**纯加法、零回归**。执行 Agent 实现，决策 Agent 复核验证后落库。

**现状对齐**：`DELIBERATION §7` 的 stance 迁移点（去 `idea`、`synthesis`→`decision`）是设计期写法、与现状不符——当前 `_DISCUSSION_STANCES` 早已无 `idea`/`synthesis`，故本片对 stance 只新增 `decision`。`escalated` 仍被 bridge 使用，本片不删（迁移/下线留 D3-3）。

### 完成事项

- `server/models.py`：`_DISCUSSION_STANCES` 加 `decision`；新增 `_DISCUSSION_END_REASONS = {consensus, deadlock, timeout, manual}`；`_DISCUSSION_STATUSES` 未动。`DiscussionSession` 加 `end_reason`（可空、索引）；`DiscussionSessionOut`(+`from_orm_session`) 回显；`DiscussionSessionUpdate` 加可选 `end_reason` + 校验（非 None 时须 ∈ 集合，否则 422）。
- `server/db.py`：`init_db()` 为旧 `discussion_sessions` 补 `end_reason` 列 + `ix_discussion_sessions_end_reason` 索引。
- `server/routes/discussions.py`：`update_discussion` 仅当 `end_reason` 在 `body.model_fields_set` 时更新该字段（status-only PATCH 保留原 end_reason）。
- `tests/test_discussions.py`：+5 组（`decision` stance turn、end_reason PATCH round-trip、非法 end_reason 422、status-only 保留、`escalated` 零回归 + 旧 schema 迁移补列）。

### 验证

- **决策 Agent 独立复跑（2026-07-04）**：`.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` → `Ran 74 tests ... OK`（9 discussion + 65 cli_bridge）；diff 逐条吻合工单、纯加法未破 `_DISCUSSION_STATUSES`/`escalated`。

### 变更文件

- `server/models.py` / `server/db.py` / `server/routes/discussions.py`
- `tests/test_discussions.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3-2：bridge `ACTION_STANCES` / stance 推断接 `decision`（仍不删 escalated）。

---

## 2026-06-28 真机黑盒验收（A/B/C）+ BUGFIX-1

**背景**：D1/D2/@所有人/人设编辑(a) 落地后，真机黑盒验收前端 3 项已开发功能。由**无项目经验的 agent 当黑盒测试者**（真·黑盒：只按 Web UI 行为测、不看代码），决策 Agent 出验收工单 + 复核。fixture 用 `scripts/seed_acceptance.py` 种入（隔离临时项目根 `.tmp-acceptance`，建 brainstorm 类型 Hall「验收测试群」+ 设 business_role），避免污染仓库已提交的 `.talk/` profile。注入行为（D2/P3-2）本轮主动不验——头脑风暴协议引擎（D3）尚未开发，那部分留待 D3 连同结构化流程一起真机验。

### 验收结果（测试者）

- **A=@所有人**：FAIL —— `@` 下拉不弹、`@所有人` 未高亮。
- **B=禁用/启用开关**：PASS —— 禁用出"已禁用"标记 + 不可加入，启用还原。
- **C=编辑人设**：PASS —— 读已有/从空白新建/持久化/business_role 改 reviewer 均正常；附带发现保存后"编辑人设"按钮卡 disabled。

### 根因定位（决策 Agent 复核代码）

- **A 下拉**：`@所有人` 提交（`6e645bb`）在 `msgInput` 输入处理器写了 `Boolean(activeGroup)`，但该作用域无 `activeGroup`（模块级只有 `activeGroupId`）→ 输入 `@` 即 `ReferenceError`，整段下拉构建抛错，所有 mention 下拉全废。**决策 Agent 当时 diff 复核漏判作用域**——黑盒补上了静态复核盲区。
- **A 高亮**：`buildMentionFragment`+`isAllMentionToken` 静态看正确；疑测试环境（消息绕过正常渲染注入）。
- **C 按钮**：`saveAgentProfileEditor` 成功路径在 `try` 内、清 `agentProfileSaving`（在 `finally`）之前就 `renderGroupMembersPanel()` → 按钮以 saving 态渲染成 disabled 后无人再刷新。

### BUGFIX-1（执行 Agent 修，仅 `web/app.js`）

- Bug 1：输入处理器 mention 块内加 `const activeGroup = getActiveGroup();`。
- Bug 3：保存成功路径在重渲染前调 `setAgentProfileSaving(false)`。
- Bug 2：无代码改动；真机 Chrome 复现确认 `@所有人` 已渲染为 `<span class="mention">` → 原现象=测试环境，非缺陷。

### 验证

- **决策 Agent 复核（2026-06-28）**：`git diff web/app.js` 仅 2 处确定性修复、与根因吻合；`node --check web/app.js` 通过；执行 Agent 用真机系统 Chrome 复验三条（下拉出现所有人+成员、`@pi` 过滤、`@所有人` 高亮、保存后按钮即恢复）。前端运行时 bug 无单测覆盖，以 diff 复核 + 真机为准。
- **结论**：A/B/C 三项前端真机验收闭环。

### 变更文件

- `web/app.js`（BUGFIX-1）
- `scripts/seed_acceptance.py`（fixture 种子，新增·未提交）
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 备注（架构对齐 2026-06-28）

管理者确认 TALK 架构理解：TALK 是中转 hub，背后真正干活的是 agent 框架（codex/pi/claude 这类，经 bridge 以 CLI 子进程接入）；codex 与 Claude Code 是同类不同厂的框架，CLI 是接入面。衍生候选「`claude_bridge`」（让 Claude Code/Codex 成为一等公民 worker）记入 PROGRESS Next Plan，暂不排期。

### 下一步

- 进 D3（头脑风暴协议）。

---

## 2026-06-25 人设编辑(a)：网页读写 `.talk/*.md` + business_role

**背景**：承接 D1（`f20811a`）/ D2（`411269f`）/ @所有人（`6e645bb`）。按 `agent-docs/BLACKBOARD.md` 的"人设编辑(a)"工单，让 human 在 Web UI 编辑某 agent 在某项目的人设文件（`<project_root>/.talk/agents/<dir>/{IDENTITY,SOUL,USER}.md`）与其在当前 Hall 的 `business_role`。文件即唯一真相源、**bridge 不变**（仍用 `cli/profiles.py` 读同一批文件）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `cli/profiles.py`（只新增写侧，读侧不动）：`PROFILE_FILES` 映射；`resolve_profile_path`（**双层路径穿越防御**：member 目录必须单段 + `resolve()` 后 `is_relative_to(agents_root)`）；`write_profile_file`（`mkdir parents` + `encoding="utf-8"` 写）。
- `server/models.py`：`AgentProfileOut`（project_id/member_id/identity/soul/user）+ `AgentProfileUpdate`（三字段 Optional，按 `model_fields_set` 选择性写）。
- `server/routes/projects.py`：human-only `GET`/`PUT /api/projects/{project_id}/agents/{member_id:path}/profile`；无 `project_root_path`→400；路径穿越 `ValueError`→400；PUT 仅写 body 出现的字段、写后重读返回。（用 `{member_id:path}` 让含 `/` 的穿越 member_id 进到校验而非 404。）
- `web/index.html` / `web/app.js` / `web/style.css`：Hall 成员行（agent + 可管理 + 群有 `project_id`）显示"编辑人设"；模态编辑 IDENTITY/SOUL/USER + business_role；保存人设走新 `PUT .../profile`，business_role 变化时复用 `PUT /api/groups/{id}/members/{member_id}`（保留原 role/decision_tier）。
- `tests/test_projects.py`：缺文件读取→null、三件套 round-trip（含落盘断言）、局部更新、无 root→400、路径穿越→400（断言外部无文件）、agent 禁止读写→403。

### 验证

- **决策 Agent 独立复跑（2026-06-25）**：`.venv\Scripts\python.exe -m unittest tests.test_projects tests.test_profiles -v` → `Ran 32 tests ... OK`；`node --check web/app.js` 通过；diff 逐条对齐、双层穿越防御复核。
- 前端"编辑人设"弹窗真机点选 + 保存持久化**未起服务真机点选**（待后续攒一次前端真机）。

### 变更文件

- `cli/profiles.py`
- `server/models.py`
- `server/routes/projects.py`
- `web/index.html` / `web/app.js` / `web/style.css`
- `tests/test_projects.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- 审议主线进 D3（头脑风暴协议）；改动面大，按 `spec/DELIBERATION.md §7` 迁移点实施。

---

## 2026-06-24 @所有人：mention 解析"所有人/all" + 前端下拉

**背景**：承接 D1（`f20811a`）/ D2（`411269f`）。按 `agent-docs/BLACKBOARD.md` 的"@所有人"工单，让 Hall 里 `@所有人`/`@all` 把消息 `to_ids` 展开为全体群成员（每个 agent 因此被 mention 触发），是头脑风暴（D3）的前置依赖。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `server/routes/messages.py`：
  - 新增 `_ALL_MENTION_TOKENS = {"所有人", "all"}` + `_is_all_token`（`所有人` 精确、`all` 大小写不敏感）。
  - `_extract_leading_mentions` 改为返回三元组 `(recipients, invalid_mention, mention_all)`；遇 all-token 不按具体成员校验、置 `mention_all`、继续消费。
  - `_resolve_recipients` 加 `sender_id`；`mention_all` 时仅群作用域允许（legacy/全局 → `400 "所有人 mention is only allowed in a group"`），返回 `sorted(全体群成员 - 发送者)`。
  - `create_message` 传 `sender_id=current.id`。
- `web/app.js`：`ALL_MENTION_ID="所有人"` + `isAllMentionToken`；`@` 下拉在群作用域（query 命中）顶部 prepend"所有人（全体成员）"项 → `completeMention("所有人")`；`@所有人`/`@all` 放行为 `.mention` 高亮。
- `tests/test_messages.py`：+4 用例（`@所有人` 展开除发送者、`@ALL` 大小写、混用具体 mention 时全体优先、全局 `@所有人`→400）；既有单 mention/广播/非法 mention 回归由原测试覆盖。

### 验证

- **决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_messages -v` → `Ran 27 tests ... OK`；`node --check web/app.js` 通过；diff 与工单逐条对齐。
- 前端"所有人"下拉点选 + 发出后全体高亮**未起服务真机点选**（待后续攒一次前端真机）。

### 变更文件

- `server/routes/messages.py`
- `web/app.js`
- `tests/test_messages.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- D3（头脑风暴协议）或 人设编辑(a) 二选一（新会话再定）。

---

## 2026-06-24 D2：bridge 注入 Hall `type` + 角色规范

**背景**：承接 D1（`f20811a`）。按 `agent-docs/BLACKBOARD.md` 的 D2 工单，让 bridge 在每条消息上下文里按本群 Hall `type` 注入流程指引 + 当前 agent 的角色职责（软预设、纯追加，不引入硬状态机）。执行 Agent 实现，决策 Agent 复核验证后落库。

### 完成事项

- `TALK/client/talk_client.py`：新增异步 SDK helper `get_hall_types()`（`GET /api/hall-types`）；`talk_client_sync.py` 加同步 parity。
- `bridges/cli_bridge.py`：
  - 模块级缓存 `_HALL_TYPE_TEMPLATES` + `_get_hall_type_templates(client)`（取一次复用；任何异常含 `AttributeError` → 返回 `{}` 不写缓存，绝不抛）。
  - 扩展 `_build_group_member_context`：`free`/缺省 `type` 不注入（保 P3-2 字节不变）；非 `free` 注入 `本群类型：{label}（{type}）。流程指引：…`；`business_role` 与模板 `roles[].role` 大小写不敏感匹配则追加 `你的角色职责：{norm}`；模板不可用 / client 无 `get_hall_types` → 降级为成员清单 + business_role。
- `tests/test_cli_bridge.py`：`setUp/tearDown` reset 缓存防串扰；新增 5 个 D2 用例（review+reviewer、brainstorm+Contributor 大小写、role 不匹配、free 不取模板、模板接口异常降级），P3-2 两个用例零回归。

### 验证

- **决策 Agent 独立复跑（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_cli_bridge -v` → `Ran 65 tests ... OK`；diff 与工单逐条对齐。
- 注入行为（agent 是否实际遵循）属黑盒，待真机攒一次（与 P3-2 同桶）。

### 变更文件

- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md` / `docs/PROGRESS_HISTORY.md`（决策 Agent 收口）

### 下一步

- 在 @所有人 / 人设编辑(a) 间二选一，再进 D3/D4。

---

## 2026-06-24 D1：Hall `type` + 模板地基（纯 server）

**背景**：按 `agent-docs/BLACKBOARD.md` 中 Claude（决策 Agent）给执行 Agent 的 D1 工单推进。目标是给 Hall 增加 `type` 维度，并建立服务端内置、数据驱动的 Hall 类型模板注册表，作为后续 D2/D3/D5 的协议地基。本切片严格不改 bridge、不改 discussion stance/状态机、不做前端。

### 完成事项

- 新增 `server/hall_types.py` 作为 Hall 类型模板单一来源：
  - `free`
  - `task`
  - `brainstorm`
  - `review`
  - 每项包含 `label` / `protocol_guidance` / `roles:[{role,norm}]`
  - 暴露 `HALL_TYPES` 与 `DEFAULT_HALL_TYPE`
- `server.models.Group` 增加 `type` 字段，默认 `free` 并建索引。
- `GroupCreate` 支持可选 `type`，创建时默认 `free`，输入会 `.strip().lower()`，非法值返回 `422`。
- `GroupOut` 回显 `type`。
- `server.db.init_db()` 增加旧库迁移：若 `groups.type` 不存在则 `ALTER TABLE` 加 `TEXT NOT NULL DEFAULT 'free'`，并创建 `ix_groups_type`。
- `server.routes.groups` 创建与输出路径均带上 `type`。
- 新增认证只读 API `GET /api/hall-types`，返回 4 类内置模板。
- 增加测试覆盖：
  - 默认创建 Hall 回显 `type="free"`
  - 创建时指定 `"type":"BrainStorm"` 归一为 `brainstorm`
  - 非法 `type` 返回 `422`
  - `GET /api/hall-types` 返回结构与认证要求
  - 旧 schema 迁移后老 Hall 自动获得 `type="free"` 并创建索引

### 验证

- **决策 Agent（Claude）独立复核（2026-06-24）**：`.venv\Scripts\python.exe -m unittest tests.test_hall_types tests.test_groups tests.test_member_disable -v` → `Ran 23 tests ... OK`，确认执行 Agent 自测结论；代码与工单逐条对齐。
- `python -m pytest tests/test_groups.py -q`：未运行；全局 Python 无 `pytest`。
- `.venv\Scripts\python.exe -m pytest tests/test_groups.py -q`：未运行；项目 `.venv` 也无 `pytest`。
- `.venv\Scripts\python.exe -m unittest tests.test_groups -v`：16/16 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_hall_types -v`：3/3 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_member_disable -v`：4/4 通过。
- 验证噪声：测试期间 `TimedRotatingFileHandler` 在 Windows 上尝试重命名被占用的 `logs/talk.log`，出现 `PermissionError` 日志噪声；测试退出码仍为 0，本切片未处理该日志轮转问题。

### 变更文件

- `server/hall_types.py`
- `server/models.py`
- `server/db.py`
- `server/routes/groups.py`
- `server/routes/hall_types.py`
- `server/main.py`
- `tests/test_groups.py`
- `tests/test_hall_types.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `agent-docs/BLACKBOARD.md`

### 待确认 / 下一步

- 待决策 Agent/项目管理者确认是否 `git commit`。
- 确认后下一片按设计进入 D2：Hall `type` → bridge prompt 注入；本轮执行 Agent 已按规则暂停。

## 2026-06-20（下午）定位再校准 + 审议方向设计定稿（仅文档，无代码）

与管理者多轮讨论后,把 Phase 3 的剩余方向从"server 端 MEMORY"转向"审议类协议",并沉淀两份 spec:

- **`spec/POSITIONING.md`**:TALK 定位为审议层,**TALK ⊇ CCB**（任务委派 TALK 也能做,CCB 仅作机制借鉴）;4 类使用场景（单次任务协作 / 任务分配 / 头脑风暴 / 评审）+ 升级横切;Hall 类型/RolePack（软预设、数据驱动、可自定义）;通用化（领域无关,非编程项目亦可）+ 受众分层（非技术受众/Web 低门槛接入列为远期）。
- **`spec/DELIBERATION.md`**:信息类型 stance 终集（去 `idea`、`synthesis`→`decision`、`closure` 降级）；**结束归一模型**——单一出口 `handoff` → 决策人（= `decision_tier`/human）,4 种 `end_reason`（consensus/deadlock/timeout/manual）,仅 `deadlock` 有参与者断路器 `escalate`,成功收敛靠决策人 `decision` 收口；Hall 类型；@所有人（展开全体、直接回内容不回执）；人设网页编辑走方案 (a)（改 `.talk/*.md` 文件、bridge 不变）；切片方案 D1–D5。

**关键决策**:① MEMORY 方向关闭（连续性靠项目 `PROGRESS.md` + 身份注入）；② 人设网页编辑 = 方案 (a)；③ 结束机制 = 单一 handoff + 仅 deadlock 有 escalate（"给出错打标不给成功打标"）。
**下一步**:从 D1（Hall `type` + 模板地基,纯 server）开写。

## 2026-06-20 Phase 3 协作层（前两片）+ Web UI #2/#3（全栈）+ 测试数据清理

分支 `claude/phase3-collab-and-ui`（基于已合入 main 的 Phase 1+2，PR #1）。决策 Agent 在管理者授权下自主连续开发。

### Phase 3 协作层
- **P3-1（`533bc5d`）群成员业务角色/决策分级存储**：`GroupMember` 加 `business_role`（自由文本）/ `decision_tier`（`decision`|`execution`）两列；`PUT /api/groups/{id}/members/{member_id}` 接收并全量替换，`GroupOut.members` 返回；`GroupMemberUpdate` 校验 decision_tier 枚举（大小写归一）；`db.py` 幂等列迁移 + 索引。+3 单测。对齐 `PROJECT_INTEGRATION.md` §5.2 groups.yaml 角色模型。
- **P3-2（`51da887`）bridge 注入业务角色**：`bridges/cli_bridge._build_group_member_context` 在群成员清单后追加"你在本群的业务角色：{business_role}。"（取自 P3-1 群成员数据中当前 member 条目）；`decision_tier` 维持由 bridge 启动参数 `--decision-tier` 注入，避免双源冲突。纯追加，无 business_role 时字节不变。+2 单测。**行为黑盒待真机**（pi/codex）。

### Web UI #2 删 Hall（全栈）
- 后端（`53846b8`）：`DELETE /api/groups/{id}`，仅人类；子表先删后删群（group_members / 该群 messages / discussion_sessions / discussion_turns），顺序保证无论 SQLite FK 是否启用都正确（运行时未开 FK）。+3 单测。
- 前端（`5578ac2`）：群成员面板红色"删除此 Hall"按钮（仅人类）→ `window.confirm` 二次确认 → `DELETE` → 本地 `groups` 移除 + 若当前群则 `setActiveGroup(null)`。新增 `.room-danger-btn`。
- 收尾（`a54e4d3`）：移除左侧 Hall 列表从未接线的 `::after content:"删除"` 残留（`padding-right:78px` 致名称换 2 行），`.room-chip` 改 `nowrap`/省略号。
- **管理者真机验收：右侧删除点选通过。**

### Web UI #3 全局禁用 agent（全栈）
- 后端（`4cec246`）：`Member.disabled_at` 软删（保留行 + `messages.from_id` 归属 + 群成员关系，不自动退群）；`get_current_member` 对已禁用成员返回 403；`PATCH /api/members/{id}`（仅人类、仅 agent 目标）切换启用/禁用；`MemberOut` 暴露 `disabled_at`；`db.py` 幂等列迁移 + 索引。+4 单测；鉴权子集 69 测无回归。
- 前端（`dea5ff9`）：右侧列表只列 agent（不展示 human）；每行禁用/启用开关（仅人类）→ `PATCH`；已禁用置灰 + "已禁用"徽标、"加入"禁用。新增 `toggleMemberDisabled` + 样式。
- 收尾（`05db723`）：列表既已 agent-only，移除每行冗余 `agent` 标签 + 过时"点角色筛选"提示，标题改"所有 Agent"，按钮加 `nowrap`（解决名字被挤 / "已在 Hall"换行）。
- **管理者真机验收：功能通过。**（端到端"禁用→403"需重启 server 加载 `PATCH` 端点后验。）

### 测试数据清理（管理者授权）
- API 删 30 个老测试群，仅留 `test-run20`（`group:843d8433bae1`），群 31→1。
- 直接删 DB 清掉 5 个测试成员（agent：ui52226 / testpi / pi@projA:tester；human：tester / ui52226），仅 0 消息者才删以保归属。现存 5 成员 = agent `codex`/`pi`/`pi-kimi` + human `bobo`/`qa`。

### 验证
- 子集全绿：groups 14/14、member_disable 4、cli_bridge 60、鉴权子集（messages/discussions/instances/tasks/files/projects）69；唯一偶发 = `test_websocket` presence 过载时序（隔离 10/10，与改动无关）。
- 前端：JS 语法 / CSS 配平 / ID 一致 / 逻辑复核 + 运行中 server 实测服务新文件。

### 下一步
- P3-3 MEMORY（完整 server 端 COLD/WARM/RESUME，独立子阶段）在本分支做；先出切片拆分方案。

## 2026-06-20 Phase 2 闭环 · 切片 10：CLI `talk sync`（本地 `.talk/agents/` → server 索引）

**背景**：切片 9 把 server 端 `project_agents` 表 + `/agents` + `/sync` 做完，但缺一个本地侧入口把 `.talk/agents/` 的 profile 索引推到 server。本片补上 `talk sync` 子命令，Phase 2 从"server 端完整"收口成"本地 → server 索引"的完整闭环。决策 Agent 在管理者授权自主开发下完成。

### 改动

- `cli/profiles.py`：新增 `member_id_from_dir_name(dir_name)` —— `member_dir_name` 的逆映射（首个 `_` 还原为 `:`，如 `agent_pi-kimi` → `agent:pi-kimi`）；kind 前缀（agent/human）不含 `_`，对磁盘上的单冒号 member_id 无歧义。
- `cli/talk.py`：
  - `scan_agents(root)`：扫描 `.talk/agents/` 各子目录，逆出 member_id，构造相对项目根的正斜杠路径（跨 OS 稳定）；缺失文件→`None`；`MEMORY.md` 映射为 `memory_pointer`；按 member_id 排序，与 server 索引顺序一致。跳过 `agents/README.md` 与点目录。
  - `sync_project(server_url, api_key, project_id, agents, *, http=None)`：`POST /api/projects/{id}/sync`，可注入 http 客户端（同 `register_project`/`create_group`）；非 2xx → `RuntimeError`。
  - `cmd_sync` + `sync` 子命令：`--project`/`--server` 默认取本地 `project.yaml`；`--key` 必填；无 project_id/无 key → 退 1。
- `tests/test_talk_cli.py`：+11 用例（逆映射、scan 排序/缺失文件→None/空目录、sync 真服务端往返、全量替换、报错、cmd 默认 project_id、缺 key、未 init）。

### 验证

- `python -m unittest tests.test_talk_cli tests.test_projects` → 44/44 通过。
- 全套件 `python -m unittest discover -s tests` → **237/237 通过**（较切片 9 的 226 增 11 个新测），无回归。
- 真实 dogfood 数据 `python -c "from cli.talk import scan_agents; ..." .` → 正确逆出 3 个 agent（`agent:codex` / `agent:pi` / `agent:pi-kimi`，含连字符名），路径正确。
- server 往返由 in-process TestClient 覆盖（POST `/sync` → DB → GET `/agents` 一致；含全量替换：删本地一个 profile 再 sync，server 镜像为剩余一个）。未做真实运行 server 的端到端手测（留待人工验收或集成）。

### 待确认 / 下一步

- Phase 2 server 端 + 本地侧入口均已闭环。下一阶段候选：② Phase 3 协作层（业务角色注入 + MEMORY，属新阶段/产品方向，开工前需确认范围）；③ 清两个 discussion 遗留小毛病（管理者已记"以后再修"）；④ Web UI #2 删 Hall / #3 全局禁用 agent（全栈，#3 涉数据模型）。

## 2026-06-16 Phase 2 身份层 · 切片 8c：codex bridge --project 注入 base_instructions

**背景**：管理者确认 8c 后一起测。codex 的系统层 = `-c base_instructions=<json>`（接缝在 8b 已认明）。与 pi 8b 同构实现。

### 改动

- `bridges/codex_bridge.py`：
  - `_build_codex_command(codex_exe, *, profile, system_instructions)`：命令构造参数化，`base_instructions` 可注入；`default_codex_command` 改由它构建（去重）。
  - `resolve_codex_command(args)`：env(`TALK_CODEX_COMMAND`)/自定义 `--codex-command` 覆盖→原样尊重；`--project` + 非空 profile→把 `compose_system_prompt(CODEX_SYSTEM_INSTRUCTIONS, profile)` 注入 `base_instructions`；否则与现状字节一致（严格 opt-in）。
  - `run_bridge` 改用 `resolve_codex_command`（执行档切换 + 注入合一）。
- `tests/test_codex_bridge.py`：+5 用例（无 project 默认 / 工具档 workspace-write / 注入 base_instructions / 空 profile 字节一致 / env 覆盖）。

### 与 pi 8b 的关键差异

codex 命令的 `_codex_config_arg` 本就 `json.dumps(ensure_ascii=False)` + `shlex.quote`，任意 profile 内容（引号/换行）天然 shlex 安全——**无 pi 8b 那个 repr→shlex bug**。

### 验证

- 单测 `test_codex_bridge` 18/18（13 原有 + 5 新；原有 `default_codex_command` 测试在重构后仍绿）。
- 真机黑盒（codex.exe 已装）：`resolve_codex_command` 用 dogfood `agent:codex` profile → shlex 往返通过（argc 20）、codex.exe 路径解析正确、`base_instructions` 含基础提示 + profile（header/SOUL/IDENTITY 标记齐）。
- 全套件 220 个仅 1 个 `test_websocket` presence 时序测试在 **499s 过载**下偶发失败；隔离单跑 19/19 通过，与本改动无关（8c 只动 codex_bridge）。commit 820aee8。

### 待确认 / 下一步

- **人工验收（管理者，pi + codex 一起测）**：起真实 bridge（`python bridges/pi_bridge.py --key <k> --project <根>` / `python bridges/codex_bridge.py --key <k> --project <根>`），在 Group Hall 观察两者身份/风格是否按各自 dogfood profile 收敛。
- 切片 9：server `project_agents` 表 + `GET /api/projects/{id}/agents` + `POST /api/projects/{id}/sync`（profile 路径索引/同步，纯服务端）。

## 2026-06-16 Phase 2 身份层 · 切片 8b：pi bridge --project 注入（B 方案，含黑盒发现的 shlex bug 修复）

**背景**：管理者选定 B 方案（人设作背景进系统层），并告知本机已装 pi/codex（解锁黑盒验证）。本片把 pi 的 `--system-prompt` 接到 `compose_system_prompt`，`--project` 给定时注入 profile。

### 改动

- `bridges/cli_bridge.py`：`build_parser` 加共享 `--project` 参数（缺省 None）。
- `bridges/pi_bridge.py`：
  - `_build_pi_command(system_prompt, *, execution_profile)`：命令构造参数化，系统提示可注入；`DEFAULT_PI_COMMAND`/`TOOLS` 改由它构建。
  - `resolve_pi_command(args)`：用户/env 覆盖命令→原样尊重；`--project` + 非空 profile→注入；否则与现状字节一致（严格 opt-in，零回归）。
  - `run_bridge` 改用 `resolve_pi_command`（执行档切换 + 注入合一）。
- `tests/test_pi_bridge.py`：+4 注入用例 + 工具档测试改用 `resolve_pi_command`。

### 黑盒发现并修复的真 bug（关键）

- 命令里系统提示原用 `{x!r}`（repr）。`parse_command` 用 `shlex.split(posix=True)` 再解析，repr 的 `\'` 转义与 POSIX 单引号语义**不兼容**——真实 profile 含引号/换行时 shlex 报 `No closing quotation`；repr 还把换行传成字面 `\n`。改 `shlex.quote(x)`：正确往返 + 保留真换行。**默认命令也受益**（此前 pi 收到的是字面 `\n`）。

### 验证

- 全套件 **215/215**（干净跑，无并发）；之前并发跑出现的 2 个 timeout 经隔离单跑确认为 websocket/SSE 时序测试的负载偶发，与改动无关。
- 真机黑盒（pi 0.79.3）：① resolve 命令 shlex 往返通过、profile 真注入（header+SOUL+IDENTITY 标记齐、真换行保留）；② 短系统提示 pi **采纳人设**（自称指定名）→ 证明 pi honors 注入；③ DEFAULT 与 INJECTED 行为完全一致 → 零回归。
- 已知：pi 在裁剪 flag（无 tools/extension）的 text 模式下，长系统提示（DEFAULT 与 INJECTED 都如此）会空输出，是 pi CLI 自身怪癖、非本改动引入。完整"pi 不再自称 qa"端到端需用生产 function-calling 命令跑真实 bridge+server 闭环——**留人工验收**。commit 1c17304。

### 待确认 / 下一步

- **人工验收（管理者）**：用 `python bridges/pi_bridge.py --key <k> --project D:\claude-test\TALK`（或目标项目根）起真实 pi bridge，在 Group Hall 里观察身份/风格是否按 dogfood profile 收敛。
- 切片 8c：codex bridge 注入（系统层接缝 = `-c base_instructions=<json>`，已认明）。
- 切片 9：server `project_agents` 表 + `/agents` + `/sync` 子资源。

## 2026-06-15 Phase 2 身份层 · 切片 7：agent profile 加载器（地基）

**背景**：管理者授权进入 Phase 2 身份层并自主开发切片。Phase 2 最敏感的是 bridge prompt 注入（前次三天 debug 战场），故先做零风险的纯函数地基。

- `cli/profiles.py`（新模块，纯文件系统、无重依赖）：`member_dir_name`（从 cli/talk.py 收归此处作唯一权威）、`AgentProfile` dataclass、`load_profile(root, member_id)`（读 IDENTITY/SOUL/USER，缺文件→None，空白→None，`is_empty` 让调用方回退不注入）、`compose_identity_block()`（拼接紧凑块，空 profile→""）。
- `cli/talk.py`：`member_dir_name` 改从 `cli.profiles` import 并再导出（去重，slice 5 测试经再导出仍通过）。
- `tests/test_profiles.py`：7 用例，含对仓库已提交 dogfood `.talk/agents/agent_codex/` 的**真实数据**加载校验。
- 验证：test_profiles 7/7；全套件 **208/208**，无回归。commit ffa80b2。

### 待确认（切片 8 注入策略——需管理者拍板）

bridge 把 profile 注入 prompt 有多种路径、且直接改 agent 现有行为，当前环境无 pi/codex CLI 无法黑盒验证，故暂停等管理者选型。三个候选：
1. **系统层注入**（§5.4 推荐）：把 SOUL 拼进 CLI 命令的 `--system-prompt`，稳态只注一次；但需改各 runtime（pi/codex）命令构造，复杂。
2. **per-call 紧凑注入**：在现有 `你是 {member_id}。{sender} 对你说:{task}` 旁加 SOUL/USER 块；改动小但稳态内容进了 per-call 层，且需防"独立首行触发自我介绍"老坑。
3. **混合**：IDENTITY 维持现状 per-call 紧凑身份锚，只把 SOUL（风格/边界）+ USER（搭档）注入，避免重复自我介绍。
- 共同安全设计：`--project` 缺省时行为与现状**字节一致**（严格 opt-in，零回归）。

## 2026-06-15 Phase 1 收尾 · 切片 5–6：CLI 子命令 + 项目群子资源

**背景**：与管理者确认"先收 Phase 1 尾巴再进 Phase 2"，并约定功能/人工验收推迟到 Phase 2 之后（Phase 1 是管道层，单测兜底；首个可观察行为在 Phase 2 身份注入）。管理者授权连做这两片。`project_agents` 表 / `/api/projects/{id}/agents` / `/sync` 明确并入 Phase 2（消费者是 bridge profile 加载），不在本收尾内。

### 切片 5：`talk add-agent` / `talk create-group` 子命令（commit da0dad7）

- `cli/talk.py`：
  - `member_dir_name()`：member_id→目录名的 `:`→`_` 净化**公共 helper**（Windows 安全；Phase 2 bridge 查 profile 复用同一映射）。
  - `scaffold_agent()`：`.talk/agents/<净化名>/` 生成 IDENTITY/SOUL/USER/MEMORY 占位模板；要求先 `talk init`；FileExistsError 防覆盖 + force。
  - `create_group()`：`POST /api/groups`（http client 可注入）。
  - `load_project` / `load_groups` / `save_groups`：`.talk/` YAML 读写。
  - `cmd_add_agent` / `cmd_create_group`：create-group 默认从本地 `project.yaml` 取 server URL 与 project_id，成功后把群追加进本地 `groups.yaml`。
  - `main()` 捕获 FileNotFoundError → 缺 `.talk/` 给干净 ✗ + exit 1。
- `tests/test_talk_cli.py`：+10 用例。实跑 `add-agent agent:codex` 生成 `agent_codex/` 正确。

### 切片 6：`GET /api/projects/{id}/groups`（commit 99b9076）

- `server/routes/projects.py`：`list_project_groups` 按 project_id 过滤，可见性沿用 `GET /api/groups`（human 全部 / agent 仅已入群），复用 groups 路由 `_group_out`，项目不存在 404；projects.py 单向 import groups.py（无循环）。
- `tests/test_projects.py`：+2 用例（按项目过滤 + 未知项目 404 / agent 可见性）。

### 验证

- 逐片：`test_talk_cli` 18/18；`test_projects`+`test_groups` 18/18。
- 全套件：切片 5 后 **199/199**、切片 6 后 **201/201**，均无回归。

### 待确认 / 下一步

- **Phase 1 全部完成**（接入机制 + 4 CLI 子命令 + dogfood 模板 + 项目群子资源）。
- 分支 `claude/project-integration-phase1` 现含 8 个 commit（切片 1–6 + AGENTS.md 治理 + docs），**未 push**，等管理者确认 push / 开 PR。
- 测试策略：Phase 1 单测兜底，功能/人工验收待 Phase 2 之后合并做一次（首个可观察行为）。
- 下一阶段 **Phase 2 身份层**：bridge 加 `--project` → 读 `.talk/agents/<member_id 净化>/{IDENTITY,SOUL}.md` → 注入 system prompt（落地 `member_dir_name` 映射）；并入 `project_agents` 表 + `/api/projects/{id}/agents` + `/sync`。

## 2026-06-15 Phase 1 基础接入 · 切片 2–4：groups 关联 + talk CLI + TALK dogfood

**背景**：切片 1（projects 表 + API）完成后，项目管理者明确改 `AGENTS.md` 角色定义（决策 Agent 默认只给方案、需明确要求才开发），并授权 Claude 按 1→2→3 顺序自主连续开发 Phase 1 余下三片。本批次三片一气呵成，每片独立验证 + 提交到分支 `claude/project-integration-phase1`。

### 切片 2：`groups.project_id` 字段扩展 + 旧群向后兼容（commit 523fffe）

- `server/models.py`：Group 新增 `project_id`（NULLABLE，FK→projects.project_id，index）；GroupCreate 接受+strip 校验；GroupOut 暴露。
- `server/routes/groups.py`：create_group 设置前校验项目存在（不存在 400）；`_group_out` 输出 project_id。
- `server/db.py`：幂等 `ALTER TABLE groups ADD COLUMN project_id` + `ix_groups_project_id`。
- `tests/test_groups.py`：+3 用例（关联项目 / 无项目向后兼容 / 未知项目 400）。
- **向后兼容**：project_id 默认 NULL，历史群与未接入项目的群行为不变（§10.2）。

### 切片 3：`talk` CLI 脚手架（commit 570c18d）

- `cli/talk.py`：`scaffold_project()`（纯文件系统，生成 `.talk/{project.yaml,AGENTS.md,groups.yaml,agents/README.md,.gitignore}`，FileExistsError 防误覆盖 + force 重写）；`register_project()`（POST /api/projects，**http client 可注入**，便于对进程内 FastAPI TestClient 端到端测试）；`generate_project_id()`；argparse 子命令 `init`；`_force_utf8_streams()` 解决 Windows GBK 控制台打印 ✓/中文路径报错。
- `requirements.txt`：显式新增 `pyyaml>=6,<7`（此前为隐式依赖）。
- `tests/test_talk_cli.py`：8 用例（脚手架/默认群/防覆盖/id 格式/注册成功/注册失败/init --no-register/init 防覆盖）。
- 实跑 `python -m cli.talk init` 生成结构正确，中文 UTF-8 正常。

### 切片 4：TALK 自身 dogfood `.talk/` 目录（commit dec9d25）

- 用切片 3 的 CLI 生成基座（真实 dogfood CLI），再补三个 agent 的身份层四件套 `agents/agent_{codex,pi,pi-kimi}/{IDENTITY,SOUL,USER,MEMORY}.md`（内容取自 §6.3–6.6 示例 + dogfood 实况）。
- `groups.yaml`：`group:talk-dev` 群，按 §5.2 标注业务角色 + 决策分级。
- **关键设计决策（待 ratify）**：`member_id` 含 `:`，Windows 文件系统禁止目录名含 `:`，故 agent 目录按 **`:` → `_`** 净化（`agent:codex` → `agent_codex/`）。已在 `.talk/agents/README.md` 记录；bridge 在 Phase 2 查 profile 时需做同样净化映射。spec 的 `agent:<id>/` 记法在 Windows 下即采用此适配。
- `memory/` 被 `.talk/.gitignore` 忽略（已 `git check-ignore` 验证命中）。

### 验证

- 逐片：`test_groups`+`test_projects` 16/16；`test_talk_cli` 8/8。
- 全套件 `python -m unittest discover -s tests`：切片 2 后 **181/181**，切片 3 后 **189/189**，均无回归。
- dogfood `.talk/` 全部 YAML 可解析、3×4 profile 齐全、角色映射正确。

### 待确认 / 下一步

- 分支 `claude/project-integration-phase1` 含切片 1–4（commit 41ad2dd→dec9d25），**未 push**，等管理者确认 push / 开 PR。
- `AGENTS.md` 角色定义改动是管理者治理改动，**未纳入**任何切片 commit，留工作区待管理者处理。
- Phase 1 已基本成型（接入机制 + CLI + dogfood 模板）。下一阶段 Phase 2 身份层：bridge `--project` 加载 profile + IDENTITY/SOUL 注入 system prompt，届时需落地 member_id→目录的 `:`→`_` 净化映射。
- 仍未做（§7.3 子资源）：`/api/projects/{id}/agents|groups|sync`、`talk add-agent` / `talk create-group` 子命令。

## 2026-06-15 Phase 1 基础接入 · 切片 1：`projects` 表 + 注册/查询 API

**背景**：前端精修支线收尾、5.x 主线关闭后，项目管理者确认回到核心主线。从 `docs/spec/PROJECT_INTEGRATION.md` §12 登记的四阶段路线选定 **Phase 1 基础接入**作为重启起点。本切片落地整条主线的最小地基——server 端 `projects` 表与项目注册/查询 CRUD API（对应 §7.1 表结构、§7.3 API 草案、§3.4 talk init 握手）。

**当前角色**：Claude = 决策 Agent（本轮由项目管理者改 PROGRESS 显式声明）；用量文件 `~/.claude/usage.json` 为空 → 按"无法获取用量"规则，且 Phase 1 涉及数据库改动 → 本轮 1 片即暂停汇总。

### 改动内容

- `server/models.py`：新增 `Project` ORM 表（`project_id` 主键、`display_name`、`description`、`project_root_path`、`maintainer_member_id` FK→members、`created_at`、`last_seen_at`）；新增 `ProjectCreate` / `ProjectUpdate` / `ProjectOut` 三个 Pydantic schema。`ProjectCreate` 校验 project_id 不含空白、display_name 必填；`ProjectUpdate` 用 `model_fields_set` 实现真正的部分更新（PATCH 只动显式传入字段，支持 `talk sync` 只改 path 的场景）。
- `server/routes/projects.py`（新文件）：`POST /api/projects`（注册，project_id 缺省时服务端生成 `prj_<hex12>`，maintainer 缺省取当前成员并校验存在）、`GET /api/projects`（列表）、`GET /api/projects/{id}`（详情）、`PATCH /api/projects/{id}`（部分更新元数据）、`DELETE /api/projects/{id}`（注销，204）。写操作 `_require_human` 限人类成员，读操作任意已鉴权成员可访问。沿用 `get_current_member` / `get_session` 依赖与 groups 路由同构。
- `server/main.py`：import 并 `include_router(projects.router)`（排在 groups 之后）。
- `server/db.py`：`init_db` 增加 `CREATE INDEX IF NOT EXISTS ix_projects_maintainer_member_id`（与既有显式索引管理风格一致；新表的索引本由 `Field(index=True)` + `create_all` 生成，此行用于幂等）。
- `tests/test_projects.py`（新文件）：8 个用例覆盖——人类注册+任意成员可读、服务端生成 id、maintainer 必须存在、重复 id 409、agent 注册/改/删均 403、部分 PATCH 不动未传字段、注销后 GET 404、校验拒绝空 display_name / 含空格 project_id。

### 验证

- `python -m unittest tests.test_projects -v` → 8/8 通过。
- `python -m unittest discover -s tests -q` → **178/178 通过**，无回归（动了 models/db/main 全局 import 文件，全套件复跑确认）。
- 未做：CLI（`talk init`）、`groups.project_id` 字段扩展、`/api/projects/{id}/agents|groups|sync` 子资源、bridge `--project` 加载——均为 Phase 1 后续切片 / Phase 2 内容。

### 待确认 / 下一步

- 下一片候选（Phase 1 续）：① `groups.project_id` NULLABLE 字段扩展 + 旧群向后兼容；② `talk` CLI 脚手架（`talk init` 写 `.talk/` + 调注册 API）；③ TALK 自身 dogfood `.talk/` 目录建立。
- `last_seen_at` 当前等于 `created_at`，bridge 连接时刷新的逻辑留待 bridge `--project` 切片接入。

## 2026-06-11 Web UI 精修支线收尾（浅色工作台多轮微调）

### Current Progress
在 `WEB-WINDOWS-LIGHT-REDESIGN-1` 浅色三栏基础上，按项目管理者多轮反馈完成一整轮视觉/布局精修，前端支线本轮收尾。**纯 `web/` 改动，未动后端 / API / 数据模型。**

- **字体收小并分级**：`--font-control 13→11`、`--font-body 15→13`、`--font-section 16→14`、`--font-title 19→16`；全站字重从 750–850 一档档降为 750 / 600 / 450 / 400 四级，消除"满屏粗体"。
- **比例对齐预览稿、中间消息区约占 2/3**：三栏从 `324 / 1fr / 380` 收窄为 `196px / 1fr / 252px`（1440 宽下中栏约 66%）；顶部查询区由"标题下方堆叠"改为"标题右侧同行"，修掉"搜索"按钮被压成竖排的问题；消息区底部 160px 死留白改为 16/24px，气泡 86% 宽、行高 1.55→1.6。
- **清爽化**：统一三栏底色（`--panel` 提亮）、柔化所有边框线（`--line` 调淡）、右侧卡片去投影变平面、加大模块间留白；顶部输入框改为悬浮大圆角卡片（圆角 18px、最大 860px）。
- **右侧成员栏重排**：成员行从横向挤压（重叠竖排 bug）改为可读布局，名字超长省略号截断；「所有成员」列表撑满到面板底部、内部滚动。
- **成员信息去冗余**：每个成员原本显示「短名 / display_name(含重复 id) / 类型标签」三处，简化为「短名 + 类型标签(agent/human)」；当前 Hall 成员 meta 从「角色 · 在线 · display_name」简化为「角色 · 在线」。
- **去掉角色下拉框**：owner/moderator/member 切换下拉是管理控件、非固定类型，按管理者要求移除（角色仍在 meta 文字可见）；连带删除已无调用者的 `updateGroupMemberRole()` 死函数。
- **group id 移位 + 顶栏精简**：group id 从右侧成员卡副标题移到中间 Hall 标题右侧的代码风格小标签；删右侧「· N 位成员 · 全部」副标题与「✎ 点击名称可重命名」提示；删顶部假窗口控件 `- □ ×`、中间「Hall 协作」、右侧 `human:qa`（DOM 保留但隐藏，避免 app.js 赋值报错）；标题栏高度 `52px→42px`（全站 6 处高度计算同步）。
- 静态资源版本号最终更新为 `20260611-ui-refine`。

### Decisions / Pending
- **成员软删除（决策已定，本轮未实现）**：将来做"agent 管理功能"时，成员删除采用**软删除 = 标记禁用**，保留历史消息归属、UI 隐藏；不做硬删除（避免破坏 `messages.from_id` 等外键引用）。需新增 `members` 禁用字段 + `PATCH/DELETE /api/members/{id}` 后端接口 + 前端入口，属全栈改动。
- 左侧"删除 Hall"入口仍为视觉态，后端 Group 删除 API 与二次确认弹窗待补（沿用上一轮遗留）。

### Verification
- `node --check web/app.js`：通过；CSS 花括号 194/194 平衡；`git diff --check`：通过（仅 LF/CRLF 提示）。
- Browser 实测（精修早期几轮）：以 `human:qa` 登录 `http://127.0.0.1:8000/` 进入 `test-run19 Hall`，用 `preview_inspect` 核验计算样式——三栏 `240/948/252`（中栏 66%）、body 14px/400、标题 17px/750、composer 圆角浮卡、成员行纵向无重叠、`all-members-list` 封顶滚动均符合预期。
- 后续几轮（成员去冗余、去下拉、填满、顶栏精简）以"服务端返回的 app.js/index.html 字节校验 + CSS 花括号 + 项目管理者在自己浏览器确认"验证；预览 MCP 截图工具因 SSE 长连接挂起未用。

### Changed Files
- `web/index.html`、`web/style.css`、`web/app.js`
- `docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`

### Next Plan
1. 前端支线已收尾，等项目管理者最终验收。
2. 下一阶段候选：agent 管理功能（含成员软删除）、Hall 删除真实 API + 二次确认、或回到后端主线（`PROJECT_INTEGRATION` 路线）。

## 2026-06-10 Web UI 浅色 Windows 风格重设计落地

### Current Progress
- `WEB-WINDOWS-LIGHT-REDESIGN-1` 已按用户确认的预览稿落地到正式 `web/`。
- 主界面改为浅色 Windows 风格三栏：左侧 Hall 列表，中间消息时间线，右侧当前 Hall 成员 / 所有成员详情。
- 登录页和首次管理员页同步匹配同一套浅色面板、字体层级、控件和按钮样式。
- 左侧 Hall 名称显示成员数 `(x)`，并支持按 Hall 名称、ID、成员 ID、昵称或 kind 做本地过滤。
- 右侧成员区常驻：当前 Hall 成员列表保留角色与在线状态，可移除成员；下方所有成员列表支持加入成员，并可点击 `human / agent` 角色标签多选筛选上方列表。
- Hall 标题可点击并聚焦重命名表单；当前 Hall 消息搜索新增正文命中高亮。
- 静态资源版本号更新为 `20260610-windows-redesign`。

### Verification
- `node --check web\app.js`：通过。
- `git diff --check -- web\index.html web\style.css web\app.js`：通过，仅有 Windows LF/CRLF 提示。
- `/healthz`：本地服务返回 ok。
- Browser 登录页验证：浅色风格正常，无横向溢出，无控制台 error。
- Browser Hall 验证：`human:qa` 进入 `test-run19 Hall` 后，当前成员 3 个、所有成员 10 个、删除按钮圆角、标题可重命名、左侧活动 Hall 显示删除入口，无控制台 error。
- Browser 桌面验证：1600x900 viewport 下三栏为 `324px / 896px / 380px`，`scrollWidth == clientWidth`。

### Changed Files
- `web/index.html`
- `web/style.css`
- `web/app.js`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
- 等项目管理者人工验收新版登录页与 Hall 页面。
- 下一切片建议优先补 Hall 删除真实 API / 二次确认弹窗，再继续做成员详情或未读状态。

---

## 2026-06-07 21:52 (Asia/Shanghai)
### Current Progress
- `WEB-WORKBENCH-REDESIGN-1` 已完成第一版：按 Product Design 方向把 Web UI 从横向工具条聊天页重构为“多 Agent 协作工作台”。
- 主界面改为左侧 `Hall 控制台` + 右侧消息时间线：左侧承载全局 / Group Hall 切换、新建 Group、成员面板和在线成员状态；右侧承载历史搜索、消息流和 composer。
- 保留现有 DOM id 与前端行为契约，不改 API，不引入框架或构建链。
- 视觉系统从单一深蓝收敛为中性暗色工作台，辅以 teal / indigo / amber 状态色，保留 8px 控件圆角与密集操作布局。
- 顺手修正 highlight.js 浏览器脚本路径，避免 `lib/common.min.js` 在浏览器中触发 `require is not defined`。
- 静态资源版本号更新为 `20260607-workbench-redesign`。
### Open Questions / Pending Confirmation
- 本轮是页面结构与视觉基线第一版，尚未新增 discussion session/turn、任务队列或实例状态面板等新功能入口。
- 左侧 Hall 列表在 Group 很多时会独立滚动；后续可继续做分组、未读/关注状态或归档入口。
- 当前 Browser 验证使用本地已有 human API Key 登录，仅做视觉和布局检查；未做完整发消息/建群/成员管理回归。
### Next Plan
1. 请项目管理者人工查看新版 Web UI 的整体方向。
2. 若方向认可，下一切片可继续补“讨论/任务/实例状态”的可视化信息区。
3. 若希望更偏家庭聊天，可回调左侧工作台密度；若希望更偏 Agent Ops，可继续强化状态、轮次和任务面板。
### Verification
- `python` HTML nesting check：通过。
- `git diff --check -- web\index.html web\style.css`：通过，仅有 Windows LF/CRLF 提示。
- Browser 桌面验证：`http://127.0.0.1:8000/` 登录后左侧控制台、右侧时间线、composer 正常渲染，无横向溢出。
- Browser 移动验证：390x844 viewport 下无横向溢出，工作台切为单列，控制台、搜索区、消息区和输入区可见。
- Browser 资源检查：页面已加载 `highlightjs/cdn-release@11.11.1/build/highlight.min.js`，替换旧的 `highlight.js/lib/common.min.js`。
### Changed Files
- `web/index.html`
- `web/style.css`
- `docs/MODULE_webui.md`
## 2026-06-02 22:36 — pi plan-mode 扩展覆盖规避 patch

### 背景
项目管理者给出 Step 2/Step 3 最终 patch：`pi` 默认 function-calling 档需要同时禁用内置工具和自动发现扩展，避免自动发现的 plan-mode 在 `rebindSession` 中重置 active tools 后覆盖显式注册的 `talk_send`。

### Current Progress
- `bridges/pi_bridge.py` 的 `DEFAULT_PI_COMMAND` 追加 `--no-builtin-tools --no-extensions`，保留 `--tools talk_send` 与显式 `--extension <talk_tools_extension.ts>`。
- `DEFAULT_PI_TOOLS_COMMAND` 追加 `--no-extensions`，让施工档工具表面也由 bridge 控制。
- `tests/test_pi_bridge.py` 更新默认命令断言，并新增两条测试覆盖默认档与施工档禁用自动发现扩展。
- `docs/PROGRESS.md` 中该切片的验证项已从“待重跑”更新为本轮实际结果。

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge`：5 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：79 tests 通过。
- `git diff --check -- bridges/pi_bridge.py tests/test_pi_bridge.py`：通过，仅有 Windows LF/CRLF 提示。

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 等项目管理者/决策 Agent 确认后，重启 `agent:pi` / `agent:pi-kimi` 做真实 Group Hall 黑盒复测。
2. 若真实黑盒仍未触发 `talk_send`，继续抓取 pi CLI 输出、extension 注册信息和 bridge env/prompt dump。

## 2026-06-02 21:45 — codex MCP approval / UTF-8 修复

### 背景
项目管理者指出 Codex 走 MCP 独立链路，不能把 pi extension bug 与 Codex MCP 混在一起判断。本轮先独立 probe `codex exec + talk_send MCP`，再按给定 patch 修复默认命令。

### Current Progress
- 独立 probe 确认：Codex `mcp_servers.talk_send` 配置可被 `codex mcp get` 识别，且模型能产生真实 `mcp_tool_call talk_send`。
- 在默认 `codex exec --sandbox read-only` 非交互模式下，MCP 调用会失败为 `user cancelled MCP tool call`，`TALK_DEFERRED_FILE` 不会写入。
- 加 `--dangerously-bypass-approvals-and-sandbox` 后，MCP approval 闸门被绕过；显式注入 `TALK_API_KEY/TALK_GROUP_ID/TALK_DEFERRED_FILE` 后，`talk_send_mcp.py` 成功写 JSONL。
- Windows 下 MCP server 需要显式 UTF-8 环境；否则初始化阶段可能出现 `invalid unicode code point`。
- `bridges/codex_bridge.py` 已在 discussion/tools 两档默认命令中加入 approval bypass flag 和 UTF-8 MCP env。
- `tests/test_codex_bridge.py` 已补独立默认命令断言，覆盖 bypass flag、`PYTHONUTF8/PYTHONIOENCODING`、以及 per-call `TALK_*` 不 hardcode。

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\codex_bridge.py tests\test_codex_bridge.py`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge`：13 tests 通过。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：77 tests 通过。
- `codex mcp get talk_send` 复用 `default_codex_command()` 中解析出的 `-c` 参数：退出码 0，输出包含 `command: python`、`args: D:/claude-test/TALK/bridges/talk_send_mcp.py`、`env: PYTHONIOENCODING=*****, PYTHONUTF8=*****`。

### Changed Files
- `bridges/codex_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 重启 Codex bridge，重新黑盒验证 `@agent:codex 通知 agent:pi 项目进度已更新` 是否产生真实消息记录和 discussion turn。
2. pi extension tool 仍需继续排查，或评估 bridge 层兼容解析 `<function_calls>` 文本兜底。

## 2026-06-01 23:24 — pi extension tool probe

### 背景
项目管理者提出高概率假设：`--no-builtin-tools` 可能把 extension tools 一起屏蔽，导致模型 catalog 为空并伪造 `<read>` / `<function>` 文本。本轮执行最小验证切片。

### Current Progress
- `bridges/pi_bridge.py` 默认命令去掉 `--no-builtin-tools`，只保留 `--tools talk_send` 白名单。
- `tests/test_pi_bridge.py` 同步调整默认命令断言。
- 直接 probe 设置 `TALK_DEFERRED_FILE` / `TALK_GROUP_ID` / `TALK_API_KEY` 后运行 pi，要求使用 `talk_send` 向 `agent:pi-kimi` 发送“你好”。
- 对照验证内置 `read` 工具：`pi --print --mode json --tools read` 能产生真实 `toolCall/toolResult` 并读取 `config.toml`。
- 临时 `echo_tool` extension probe：显式 extension 加载不报错，但模型只输出文本形式 `<function_calls><invoke name="echo_tool">...`，没有真实 `toolCall/toolResult`，输出文件为空。
- 坏路径 / 抛错 extension probe：pi 会明确报错，说明不是“extension 加载错误完全静默吞掉”。

### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge`：59 tests 通过。
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py bridges\cli_bridge.py`：通过。
- `talk_send` probe：`TALK_DEFERRED_FILE` 仍为空，未执行。

### Conclusion
- 假设 A（`--no-builtin-tools` 屏蔽 extension tools）未命中。
- 假设 C 可收窄：不是简单“扩展加载静默失败”，因为坏扩展会报错；更像是当前 pi/provider 对显式 extension tool 没进入可执行 function-call 通道。
- 假设 B 或 provider/tool-call 兼容问题仍在：模型能看见/复述 `talk_send` / `echo_tool` 名字，但只以普通文本输出 `<function_calls>`，pi 没有把它当 toolCall 执行。

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 暂停，等待项目管理者确认下一步。
2. 候选方向一：继续排查 pi extension tool catalog / provider tool-call 支持。
3. 候选方向二：在 bridge 层解析 pi 输出里的 `<function_calls>/<invoke name="talk_send">` 作为兼容兜底，但不能把工具使用规则重新塞回 per-call prompt。

## 2026-06-01 23:10 — 5.5 Prompt 三层架构改造

### 背景
项目管理者要求按 `docs/spec/INTERACTION_FRAMEWORK.md` §5 将 bridge prompt 拆成三层：工具自描述层 / 系统层 / 单次调用层，降低 per-call SNR，并让未来新增工具时 bridge prompt 复杂度保持 O(1)。

### Current Progress
- `bridges/cli_bridge.py` 新增 `FUNCTION_CALLING_SYSTEM_PROMPT`，作为 pi/codex 共用系统层 prompt。
- `build_cli_prompt()` 的 pi/codex 分支改为只输出动态信息：`sender 对你说:task`、群成员清单、discussion context。
- `build_cli_task_prompt()` 的 pi/codex 分支同步瘦身，不再注入身份、任务 id、项目根目录等系统层/元信息。
- `bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT` 改为引用公共系统层 prompt。
- `bridges/codex_bridge.py` 通过 `-c base_instructions=...` 注入系统层 prompt；修复 `mcp_servers.talk_send.args` 的 TOML quoting；默认命令改用 `_default_codex_exe()` 探测到的本地 Codex CLI，并加 `--ignore-rules` 避免聊天 bridge 读取项目规则。
- `bridges/talk_tools_extension.ts` 和 `bridges/talk_send_mcp.py` 强化 `talk_send` 工具自描述，把“何时联系、转告、询问、通知或打招呼给另一成员”放在工具层。
- 测试新增/调整：最小 per-call prompt、工具增长 O(1)、系统层 prompt 进入 pi/codex 默认命令、codex config quoting。

### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions tests.test_codex_bridge`：74 tests 通过。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py bridges\codex_bridge.py bridges\talk_send_mcp.py`：通过。
- `git diff --check`：通过，仅有 Windows LF/CRLF 提示。
- `codex.exe --version`：本地 OpenAI Codex bin 可运行，版本 `codex-cli 0.130.0-alpha.5`；PATH 上 WindowsApps `codex.exe` 在当前 shell 报 Access is denied，因此默认命令改用本地路径探测。
- Codex 最小执行：修复后不再出现 `mcp_servers.talk_send.args expected a sequence`，说明 MCP config quoting 已正确。
- `usage-gate guard --provider codex --json`：`decision=continue`，session 46%，weekly 22%。

### Blackbox Result
- 已启动 TALK Server 与 `agent:pi` / `agent:pi-kimi` / `agent:codex` bridge，并在 `group:test-run15` 发送三条 UTF-8 正常指令：
  - `@agent:pi 去跟agent:pi-kimi打个招呼`
  - `@agent:codex 通知 agent:pi 项目进度已更新`
  - `@agent:pi 问 agent:pi-kimi 它现在忙不忙`
- 未通过验收：未产生 `agent:pi -> agent:pi-kimi` 或 `agent:codex -> agent:pi` 的实际消息记录；`discussion_sessions / discussion_turns` 无对应 demand/reply turn。
- `logs/pi_prompt_dump.log` 证实 per-call prompt 已降为 `sender + task + 群成员清单`，不含系统层字样。
- 直接 pi 工具探针中，pi 仍输出伪 `<read>` 文本，没有执行 `talk_send` extension；残余风险集中在 pi runtime extension tool catalog / tool execution 链路。

### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `bridges/codex_bridge.py`
- `bridges/talk_tools_extension.ts`
- `bridges/talk_send_mcp.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Next
1. 暂停功能扩展，先排查 pi extension 工具调用链。
2. 确认 `--extension` 注册的 `talk_send` 是否实际进入 pi tool catalog，以及 `--tools talk_send` 是否需要命名空间或不同运行模式。
3. 工具链修复后重跑 `group:test-run15` 三条黑盒验收。

## 2026-06-01 16:35 — 5.5 方案 D：discussion_turns 显式交互账本

### 背景
项目管理者指出上一轮“打招呼关键词兜底”违背原架构方向：应让模型自主判断自然语言需求，bridge 只机械执行 function-calling 协议。进一步评估方案 A/B/C 后，确认采用方案 D：`reply_to` 只保留 UI/引用语义，需求/回复/轮次由 `discussion_sessions + discussion_turns` 显式账本记录。

### Current Progress
- 修订 `docs/spec/INTERACTION_FRAMEWORK.md`：保留四分类模型和 function-calling 方向，明确 `reply_to` 不再承担“需求/回复/轮次”的协议状态。
- 给 `discussion_turns` 增加 `turn_kind`：`demand | reply`；历史迁移默认 `reply`。
- API / SDK 已支持 `append_discussion_turn(..., turn_kind=...)`，输出也包含 `turn_kind`。
- bridge 已改为读取 active session 中最大 `demand.round_index`：小于 2 才创建 `TALK_DEFERRED_FILE`，达到 2 后禁止继续 `talk_send`。
- deferred `talk_send` 成功后追加 `turn_kind=demand`；visible reply 成功后追加 `turn_kind=reply`。
- 删除上一轮临时的“明确打招呼/问好关键词兜底”代码和测试。
- 保留 `talk_send` 消息继承当前消息 `reply_to` 的行为，但只作为 UI 引用和定位辅助，不再用于轮次判定。

### Changed Files
- `docs/spec/INTERACTION_FRAMEWORK.md`
- `docs/spec/MODULE_discussions.md`
- `docs/PROJECT_BRIEF.md`
- `server/models.py`
- `server/db.py`
- `server/routes/discussions.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `tests/test_talk_client.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py server\models.py server\db.py`：通过
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions`：61 tests 通过
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_talk_client`：16 tests 通过
- `git diff --check`：通过，仅有 Windows LF/CRLF 提示

### Next
- 重启服务和 bridge 后，在 `group:96b88a2357a7` 黑盒复测 `@agent:pi 去跟agent:pi-kimi打个招呼`。
- 重点验收：第 1 轮 `demand round_index=1`、任一 agent 可产生一次第 2 轮 `demand round_index=2`、之后不再暴露 `TALK_DEFERRED_FILE`。
- 若模型仍不调用 `talk_send`，继续排查 pi CLI / extension / tool-calling 链路，而不是恢复关键词兜底。

---

## 2026-06-01 14:40 — 5.5 打招呼场景 bridge 兜底修复

### 背景
项目管理者重启服务并在 `group:96b88a2357a7` 连续测试 `@agent:pi 去跟agent:pi-kimi打个招呼`，结果 pi 只向 human 回复“好的，我去...”，没有实际调用 `talk_send`，因此也没有产生 `agent:pi -> agent:pi-kimi` 消息，方案 C 的 `reply_to` 链深度刹车未被验证到。

### Current Progress
- 确认当前问题不是成员缺失：群内有 `human:qa`、`agent:pi`、`agent:pi-kimi`。
- 确认失败形态：`talk_send` / `TALK_ACTION` 均未触发，deferred 文件为空，数据库只新增 pi 给 human 的确认回复。
- 在 `bridges/cli_bridge.py` 增加窄范围兜底：human 明确要求“去跟 agent:X 打招呼/问好”，且模型给出承诺式回复但未触发发送动作时，由 bridge 生成 `send_message` 动作。
- 兜底消息仍走既有 `execute_talk_actions`，因此会复用群成员校验、`reply_to` 继承、discussion turn 记录等路径。

### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

### Verification
- `python -m py_compile bridges/cli_bridge.py bridges/pi_bridge.py`：通过
- `python -m unittest tests.test_cli_bridge.CliBridgeTests.test_human_greeting_request_falls_back_when_pi_skips_tool_call tests.test_cli_bridge.CliBridgeTests.test_greeting_send_message_action_records_non_substantive_turn tests.test_cli_bridge.CliBridgeTests.test_handle_incoming_message_executes_send_message_action`：通过
- `python -m unittest tests.test_cli_bridge tests.test_pi_bridge`：53 tests 通过
- 未做真实黑盒复测：需要项目管理者重启 bridge 后再发测试消息

### Next
- 重启 `agent:pi` / `agent:pi-kimi` 后复测打招呼场景。
- 若打招呼通过，再确认是否需要为“转告/询问”设计独立兜底策略。

---

## 2026-06-01 — 5.5 回复质量优化 + preview 方案回退 + 交互框架文档

### 背景
方案 C 落地后黑盒测试发现 3 处回复质量残留（汇报体、原文引用、extension 暴露机制），实施了 4 项修复。preview 方案因人类消息也以 @ 开头被否决回退。整理了完整的交互框架文档。

### Current Progress
- **去汇报体**：agent 调 talk_send 时 suppress visible reply（JSONL 文件非空判断，兼容旧协议测试）
- **prompt 微调**：不要引用发送的原文
- **extension 中性化**：TALK_DEFERRED_FILE 未设时返回 "已处理。" 而非暴露机制文本
- **preview 方案回退**：`reply_to.preview` 无法区分 human @mention 和 talk_send @mention，回退到 `reply_to.from_id`
- **交互框架文档**：新建 `docs/spec/INTERACTION_FRAMEWORK.md`，系统阐述消息四分类模型、轮次约束、三层防线架构、协议演进历史

### Changed Files
- `bridges/cli_bridge.py`
- `bridges/talk_tools_extension.ts`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/spec/INTERACTION_FRAMEWORK.md`（新建）

### Verification
- `py_compile` 通过
- 52 tests 全过

### Next
- 确定 pi 侧第 2 轮方案（discussion turn 追踪 / 查父消息 / 保持现状）
- 继续黑盒测试

---

## 2026-05-31 — docs 目录整理：spec / guides 分层

### 背景
项目管理者确认 `docs/` 当前平铺文档过多，希望先整理为少量高频目录；同时确认暂不创建“产品迭代”和“技术验证”空目录，等有真实内容再补。

### Current Progress
- 保留根目录锚点文档：`docs/PROJECT_BRIEF.md`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 新增 `docs/spec/`，并移入 `PRODUCT.md`、`SDK.md`、`LOCAL_LAB_DESIGN.md`、全部 `MODULE_*.md`。
- 新增 `docs/guides/`，并移入 `QUICKSTART.md`、`QUICKSTART_USER.md`、`QUICKSTART_AGENT.md`、`DEPLOY.md`。
- 暂未创建 `iterations/`、`validation/`、`milestones/` 空目录。
- 已更新 `PROJECT_BRIEF` 目录树和模块索引，修正 README、AGENTS、CLAUDE、进度历史和文档内相对链接。

### Changed Files
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
- `docs/spec/*`
- `docs/guides/*`

### Verification
- `rg` 旧路径模式搜索：未发现计划关注的旧路径模式残留。
- Markdown 本地链接校验：通过。
- `git diff --check`：通过；仅有既有 Windows 换行提示。
- 未运行后端测试：本切片仅移动和修正文档。

### Next
- 继续原 5.5 P0 后续：重启 pi bridge + pi-kimi bridge 后跑黑盒测试。
- 后续出现真实迭代计划、技术验证报告或里程碑验收材料时，再分别创建对应目录。

---

## 2026-05-31 — 5.5 Step 2+ P0 热修复：身份幻觉 + 消息风暴 + stance 参数

### 背景
Step 2 agent_end 钩子落地后，项目管理者在 group:83aae24462b7 跑黑盒测试（10:19），发送 `@agent:pi 你去和 agent:pi-kimi 打个招呼`。结果 42 条消息，pi ↔ pi-kimi 陷入无限循环对话，暴露三个致命问题：
1. **消息风暴**：双方互相调用 talk_send，无刹车机制
2. **身份幻觉**：pi 自称 "agent:codex"
3. **重复发起**：pi-kimi 把连续对话的后续消息当成全新打招呼请求

### Current Progress
- **`talk_send` 加 `stance` 参数**：支持 question / greeting / answer / agree / disagree / closure，JSONL 记录带 stance
- **Bridge 层 turn limit 刹车**：`_read_and_execute_deferred_actions` 新增 `current_turn_count` / `max_auto_turns` 参数，greeting/answer/agree/closure 类型在 turn ≥ 3 时自动丢弃
- **Prompt 注入 `member_id`**：pi prompt 新增 `"你是 agent:pi。"` 前缀，防止身份幻觉
- **Prompt agent-to-agent 约束**：新增 "如果只是其他 agent 在寒暄/闲聊/确认，直接简短回复即可，不要再调用 talk_send"
- **Discussion 上下文对齐**：`_discussion_context_text` 增加 talk_send 说明
- **Extension promptGuidelines 更新**：告知模型区分 human 指令 vs agent 寒暄，强调 stance 必填

### Changed Files
- `bridges/talk_tools_extension.ts`
- `bridges/cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

### Verification
- `py_compile` 全部通过
- 52 tests 全部通过（49 cli + 3 pi）
- turn limit 刹车单元测试通过（turn=0 全执行，turn=3 greeting 跳过 question 照发）
- 未经真实 pi 端到端验证（需重启 bridge 后跑黑盒测试）

### Next
- 重启 pi/pi-kimi bridge 后跑黑盒测试验证三个 P0 问题
- 如仍有消息风暴，考虑 bridge 层更激进刹车

---

## 2026-05-31 — 5.5 Step 2：agent_end 钩子

### Current Progress
- **talk_send 改为延迟执行**：extension 不再直接 HTTP POST，改为写入 JSONL 临时文件；bridge 在 visible reply 发送后才读取执行
- **修复 step 1 遗留 bug**：`talk_tools_extension.ts` 中 `sendToTalk` 重复调用（两次同语句）
- **时序修复**：visible reply → deferred talk_send → cleanup，确保 sender 先看到回复再触发跨 agent 消息
- **回退兼容**：`TALK_DEFERRED_FILE` env 不存在时扩展仍走直接 HTTP POST 模式
- **新函数**：`_read_and_execute_deferred_actions(filepath, client, group_id)` — 读 JSONL、逐条用 TALK SDK 发送
- **临时文件生命周期**：bridge spawn pi 前 `mkstemp` 创建，`finally` 清理（`os.unlink` + `os.environ.pop`）
- **向后兼容**：TALK_ACTION 文本协议解析代码全部保留，不做删除

### Changed Files
- `bridges/talk_tools_extension.ts`
- `bridges/cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

### Verification
- `py_compile` 全部通过
- 52 tests 全部通过（49 cli + 3 pi）
- 未经真实 pi 端到端验证（需重启 bridge 后跑黑盒测试）

### Next
- 5.5 step 3：扩展工具集（`talk_reply` / `talk_list_agents` / `talk_escalate` / `talk_mark_stance`），支持 `stance` 参数
- 黑盒验证 step 2 deferred 时序

---

## 2026-05-30 — 5.5 Step 1：function-calling 最小可验证版本

### Current Progress
- **pi bridge 切换到 function-calling 模式**，注册 `talk_send` 工具（通过 `talk_tools_extension.ts` pi 扩展）
- **双向通信验证通过**：pi（kimi-k2.6）→ pi-kimi（kimi-k2.6），消息均正确入群时间线（`group_id` 正确注入）
- **架构共识落地**：元数据（group_id / decision_tier / member_id）走环境变量，不放 prompt；用户消息放最前面；不声明 agent 身份避免与 pi 内核冲突
- **prompt 极简化**：从最初 ~800 字降到 ~130 字，system prompt 仅 8 字
- **prompt 迭代路径**：R1 方括号格式被 LLM 当元数据跳过 → R2 自然语言但上下文太长淹没指令 → R3 去掉身份声明 + 括号备注，模型不再内部冲突
- **工具集污染修复**：确认所有内置工具会让模型切到代码助手模式，必须 `--no-builtin-tools --tools talk_send`
- **反幻觉黑名单"粉象效应"修复**：正常路径不列禁止名单；fallback（清单不可用）保留
- **多 bridge 环境变量 key 冲突修复**：`if not in os.environ` → 无条件覆盖
- **DeepSeek 模型确认不适合 function-calling**：pi 切 kimi-k2.6 后解决
- **时序问题**：`talk_send` 在 visible reply 之前（`--print` 限制），留给 step 2 `agent_end` 钩子

### Changed Files
- `bridges/talk_tools_extension.ts`（新建）
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `deploy/bridges.example.json`（新建）

### Verification
- `py_compile` 全部通过
- 72 tests 全部通过（cli/codex/pi/discussions/talk_client）
- 群内测试：pi ↔ pi-kimi 10 条消息全部正确入群时间线

### Next
- 5.5 step 2：`agent_end` 钩子解决时序问题
- 5.5 step 3-4：迁移所有 bridge，删除 TALK_ACTION 文本协议

## 2026-05-30 第五轮 (Asia/Shanghai) — 诊断 + 方向调整：协议机制层重构立项
### 背景
- 第四轮"信使场景"上线后跑黑盒测试，pi 仍然不发 TALK_ACTION，新冒出"系统 prompt 整段泄漏给用户"（场景 5 #460 "决策分级是：高自主权"、"本群成员清单（member_id）：[人类: 小白] [agent: pi]" —— 这些字串我代码里根本没写过）和"完全偏题回复"（场景 9 #470 触发"分组讨论已经开始"会议主持模板）等新症状
- 项目管理者判断"模型不应该会忽视指令"，要求复查代码并做诊断

### 诊断过程
1. **代码复查**找到 2 个原则性问题 + 4 个设计问题：
   - 原则性：`_build_group_member_context()` 静默失败（group_id 为空或 get_group 报错都返回 "")
   - 原则性：`build_cli_prompt` pi 分支降级时无告警（清单为空时 [系统] 块只剩身份+决策分级）
   - 设计：系统 prompt 太"对话式"，pi 把它当对话内容来 paraphrase
   - 设计：缺 few-shot 示例
   - 设计："系统 块"引用与 `[系统]` 实际不一致
   - 设计：系统 prompt 是一坨无结构长字符串
2. **加 prompt dump 诊断**（`bridges/cli_bridge.py` 新增 `_dump_prompt()` / `_dump_diagnostic()`，环境变量 `TALK_DUMP_PROMPT=1` 启用）
3. **项目管理者手动重启 pi bridge + 跑场景 1/5/2，dump 写入 `logs/pi_prompt_dump.log`**
4. **dump 结论非常清晰**：
   - `group_id` 正常（`group:139f88c27756`）
   - `group_member_ctx` 非空（107 chars）
   - 群成员清单完整含 `agent:codex / agent:pi / human:qa`
   - 决策分级文案与代码一致（`执行 Agent — 每次只处理一个已确认请求...`）
   - **prompt 注入完全正确，但 pi 仍然乱回**
5. **项目管理者提供 `disler/pi-vs-claude-code` 项目对比报告**（桌面 `pi-vs-claude-code-vs-TALK-评估报告.md`），第 3.3 节直指根因：TALK 的"自由文本嵌结构化协议标签"（`TALK_ACTION send_message to=agent:codex stance=question body=...`）架构本身让 LLM 不可能可靠输出 —— 任何模型在"对人说自然语言"+"对 bridge 说协议指令"双信道下都会失败
6. **`bridges/pi_bridge.py:22-23` 自证**：pi CLI 当前以 `--no-tools` 启动，明确禁用了原生 function-calling 能力。我们自己关掉了更可靠的路径

### Current Progress
- **5.3 状态：接受当前实现作为过渡版本**。dump 证明 5.1-5.3 已落地的设计（调度顺序、去硬编码、群成员清单注入、决策分级注入、自我介绍模板）全部正确，pi 是收到这些事实的，剩余"pi 不输出 TALK_ACTION"问题是协议机制层的，不是 prompt 文案层
- **`bridges/cli_bridge.py` 加入 prompt dump 工具**（73 行）：`_dump_prompt()` 完整记录 spawn LLM CLI 前的 prompt + 上下文元数据；`_dump_diagnostic()` 记录注入失败时的诊断信息；`_build_group_member_context()` 失败路径加诊断 log。全部通过 `TALK_DUMP_PROMPT=1` 环境变量 gated，默认关闭、零运行时影响；将来排查 prompt 问题随时可用
- **`docs/spec/LOCAL_LAB_DESIGN.md` 新增 "2026-05-30 Agent 通信协议方向调整：从文本协议标签转向 function-calling" 章节**，包含触发证据、根因分析、新方向工具集设计（`talk_send` / `talk_reply` / `talk_list_agents` / `talk_escalate` / `talk_mark_stance`）、与现有 5.1-5.3 工作的关系、5.5 落地阶段规划

### Next Plan
- **5.4 优先**：`groups.metadata` JSON 字段落地（与协议机制正交）
- **5.5 立项**：agent 通信协议改造 function-calling，4 阶段落地（详见 `docs/spec/LOCAL_LAB_DESIGN.md` 新章节）
- 5.4 落地后 5.3 的 `metadata.roles` 反查线路自动激活，无需返工
- 5.5 落地后预计可删 `cli_bridge.py` 中 800+ 行文本协议解析/清理/推断/兼容代码

### Verification
- 改动只涉及 `bridges/cli_bridge.py` 增加诊断函数 + 文档更新，不动其它代码
- `py_compile bridges/cli_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` 全过（dump 代码默认关闭，不影响测试）
- 实证：prompt dump 文件 `D:\claude-test\TALK\logs\pi_prompt_dump.log` 3 条 dump 验证注入正确

### Changed Files
- `bridges/cli_bridge.py`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-30 第四轮 (Asia/Shanghai) — 5.3 回炉热修第二弹
### 背景
- 第三轮（同日早些时候）把"回复克制"重写为 A/B/C 三类区分以解决"pi 不执行 TALK_ACTION"问题。但黑盒复测后发现两个新问题：
  - **#431 铁证**：pi 把 `"A 类。"` 直接当话术输出（"A 类。你好，我是 Talk Group Hall 里的 pi..."），显式标签污染回复
  - **关键词匹配脆弱**：B 类触发词清单 `"请和、让、去问、去找、联系、通知"` 不全，用户消息"你**去和** codex 打个招呼"里的"去和"不在清单里，pi 按字面匹配失败 → 默认走 A 类 → 不执行 TALK_ACTION
- 测试结果分布：场景 1/2/3/9 FAIL，4/5/6/7 PASS，8 MILD。"无敷衍机械文案 / 无 bobo 幻觉 / 无越界扩展 / 无 codex 模板"四类已修问题没有回归。
- 项目管理者点出根因方向："关键词匹配很难穷尽，应该用场景类型描述"。

### Current Progress
- **`bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`**：把"回复克制"段彻底重写：
  - 放弃 A/B/C 字母标签 + 关键词清单
  - 改用 **场景类型描述**：【信使场景】/【自身询问场景】/【agent 互回场景】
  - **信使场景的判定核心是"意图焦点"语义判断**：让 pi 自己问"用户期望谁回答这个问题、谁去做这件事？"，答案是另一个成员就是信使场景
  - **"拿不准时优先按信使处理"** 兜底——错执行比不执行容易补救
  - **自身询问场景兜底**：被问"介绍下你自己"必须说出 member_id + 本群是否有角色（直接修场景 9）
  - **显式禁止输出场景标签**：封掉"A 类。"那种泄漏
- **`tests/test_pi_bridge.py`**：测试断言换成新关键词（信使场景 / 意图焦点 / 拿不准时优先按信使处理 / member_id / 本群没有给我分配特定业务角色）；`assertNotIn "A 类——"` / `"B 类——"` / `"C 类——"` 防字母标签回归

### Open Questions / Pending Confirmation
- 待项目管理者**只重启 pi bridge** + **新建测试群**（不复用 `group:2b3c9432ac73`）后复跑 `test_after_5.3.md`
- 重点验证：场景 1/2/3 pi 是否真的发 TALK_ACTION 联系 codex；场景 9 是否说出 member_id + 承认无角色；pi 回复不含场景标签
- 已 PASS 的场景 4/5/6/7 不应回归
- **遗留**：场景 8 codex 对 SQL 评审 FAIL（codex 走 cli_bridge.py 非 pi 分支，那里克制只有英文 `RESPONSE_STYLE_INSTRUCTIONS`），不在 5.3 范围内；待 5.4 后单独处理

### Verification
- `py_compile bridges/pi_bridge.py tests/test_pi_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` 首次跑遇到 1 个 timing flaky（与本轮改动无关），立即重跑 24 tests 全过
- 本轮总计 72 tests 全过

### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 第三轮 (Asia/Shanghai) — 5.3 回炉热修
### 背景
- 第二轮回炉完成后开始重测 `test_after_5.3.md`，刚跑场景 2 就发现 pi 收到 `@agent:pi 请和 codex 互相确认在线状态` 只对 human 回了 `嘿，我是 pi！👋 有什么可以帮你的吗？`，未用 TALK_ACTION 联系 codex，120s 静默。场景 1 同样：pi 收到"你去和 codex 打个招呼"也未联系 codex。
- 用户暂停测试，把测试 agent 抓取的消息流（s1-s6 的 JSON）留在测试目录供诊断。

### 根因
- 第二轮回炉时加的"回复克制"措辞过宽：`打招呼/确认在线/寒暄请求只用一两句话回应`。
- pi 看到用户消息里有"确认在线状态"几个字，触发字面匹配，**忽略了"请和 codex 互相"将任务转交给 codex 的语义**，只对 human 敷衍一句就停下。
- 同样的"克制"在 `pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT` 和 `cli_bridge.py` 的 pi `[系统]` 块里**各放了一份**，双重保险变成双重压制。

### Current Progress
- **`bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`**：把"回复克制"重写为显式区分 **A/B/C 三类**：
  - **A 类**（用户直接问候/确认状态）：一两句话简短回应
  - **B 类**（用户派 pi 联系另一个 agent）：**必须**用 TALK_ACTION send_message 真的发消息；先简短承接 human 再发 action
  - **C 类**（agent 间互回）：一两句即停，不主动追问/扩展
  - 加 B 类判定信号清单（"请和、让、去问、去找、联系、通知" + agent 名）和"识别到 B 类时优先执行任务转交，不要被 A 或 C 的简短规则覆盖"兜底
- **`bridges/cli_bridge.py`**：`build_cli_prompt` 和 `build_cli_task_prompt` 的 pi 分支**删除重复的"回复克制"行**；语义规则统一由 pi `DEFAULT_SYSTEM_PROMPT` 承载
- **`tests/test_pi_bridge.py`**：加 assertion 守住 A/B/C 区分 + `必须用 TALK_ACTION send_message` + `先简短承接用户一句`等关键短语
- **`tests/test_cli_bridge.py`**：原 `test_build_cli_prompt_for_pi_includes_role_restraint_instructions` 重写为 `test_build_cli_prompt_for_pi_does_not_duplicate_restraint_instructions`，断言 cli_bridge 不再重复注入

### Open Questions / Pending Confirmation
- 待项目管理者**只重启 pi bridge**（codex bridge 与 server 本轮未动）+ **新建测试群**（不复用 `646ab3e4fe7f`，那个含失败试跑的 6 条消息会污染场景 4/5）后复跑 `test_after_5.3.md`
- 重点验证 pi 在场景 1/2 必须真的用 TALK_ACTION 联系 codex（不能再敷衍一句就停）
- 旁观察：第二轮测试时测试 agent 创建群没加 `group:` 前缀（纯 hex `646ab3e4fe7f`），server 接受了；后续可以在 SDK 或 server 加格式规范化

### Verification
- `py_compile bridges/pi_bridge.py bridges/cli_bridge.py tests/test_pi_bridge.py tests/test_cli_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` — 24 tests 全过
- 本轮总计 72 tests 全过

### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 第二轮 (Asia/Shanghai) — 5.3 修复回炉
### 背景
- 第一轮 5.1/5.2/5.3 落地后跑黑盒测试 `test_after_5.3.md`：codex 表现达预期，但 pi 全线 FAIL —— 反复"bobo"幻觉名（场景 2/3/6）、自封"方案评审"（场景 1/9）、寒暄持续扩展（场景 1/2/3/8）。
- 诊断：根因不是 5.3 设计错误或注入逻辑，而是 `bridges/pi_bridge.py` 的 `DEFAULT_SYSTEM_PROMPT`（commit `3c7ca9a` 引入，先于 5.1-5.3）硬编码了 `to=human:bobo` 与"评审方案"，并通过 `--system-prompt` argv 以 system role 高权重传给 pi CLI，压垮了 5.3 在 user prompt 末尾的群成员清单注入。codex 没有 system prompt 硬编码所以 5.3 对它生效。

### Current Progress
- **P0：`bridges/pi_bridge.py` 去硬编码**
  - 删除 `DEFAULT_SYSTEM_PROMPT` 中两处 `to=human:bobo`，改为 `to=「清单内的 human id」`（CJK 角括号避免触发 shell metacharacter 守卫）
  - 删除"评审方案"自封定位
  - 新增"回复克制"段（一两句话回应寒暄、不要追问、不要主动 offer 评审/优化/规划等服务）
  - 新增"身份与成员清单"段（明确声明用户消息开头的 `[系统]` 块是唯一身份事实，禁止使用清单外的任何名字 — 即便在过往记忆里出现过）
- **P1：`bridges/cli_bridge.py` pi 路径让 5.3 真正生效**
  - `build_cli_prompt()` 和 `build_cli_task_prompt()` 的 pi 分支：`[系统]` 块从 prompt 末尾挪到开头（高权重位置），新增 `[用户消息]` / `[任务]` 分段
  - pi 现在也拿到了"回复克制"指引（之前完全没拿到 `RESPONSE_STYLE_INSTRUCTIONS`，这是寒暄持续扩展的另一根因）

### Open Questions / Pending Confirmation
- 待项目管理者复跑黑盒测试 `D:\claude-test\black box test\talk\codexscenario-1-scope-fix\test_after_5.3.md`（结果区已清空回模板状态）
- 重点验证 pi 路径：bobo/paddy 应消失、不应自封角色、寒暄一两句即收口；codex 路径不应被打坏；场景 4/5 不变量应保持
- 5.1 / 5.2 / 5.3 第一轮代码完全未动；codex 路径完全未动

### Verification
- `py_compile bridges/cli_bridge.py bridges/codex_bridge.py bridges/pi_bridge.py tests/test_cli_bridge.py tests/test_pi_bridge.py` 通过
- `unittest tests.test_pi_bridge tests.test_cli_bridge` — 48 tests 全过（含新增 2 个 5.3 P1 回归测试）
- `unittest tests.test_codex_bridge tests.test_discussions tests.test_talk_client` — 24 tests 全过（确认未打坏 codex/discussions/SDK 路径）
- 全量 `unittest discover` — 150 tests，1 个 known-flaky `test_websocket.py` presence timing failure（与本轮改动无关，独立重跑前历史已记录类似 WS timing flakiness）
- 未做真实 Codex+pi 长链路主观体验自测（按黑盒测试设计要求保留给无项目记忆 agent）

### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`（本文件）

---

## 2026-05-29 (Asia/Shanghai)
### Current Progress
- **修复项 5.1（visible_reply 调度顺序修正）**：`handle_incoming_message()` 中将 `client.reply()` 移到 `execute_talk_actions()` 之前，确保 visible_reply 先回 sender；删除 `"已按讨论协议继续推进。"` 和 `"({bridge_label} finished without visible output.)"` 两个 fallback 文案；action 错误通知作为 follow-up relay。
- **修复项 5.2（去除 prompt 中具体例句）**：`RESPONSE_STYLE_INSTRUCTIONS` 中移除 `"for example '<agent id> 在线。'"` 具体例句，仅保留抽象风格指令。
- **修复项 5.3（Agent 角色注入框架）**：
  - 新增 `--decision-tier` CLI 参数（`decision` / `execution`，缺省 `execution`），bridge 启动配置注入
  - 新增 `_decision_tier_line()` 中文分级描述辅助函数
  - 新增 `_build_group_member_context()`：bridge 在 spawn LLM CLI 前调用 `GET /api/groups/{id}` 获取群成员清单和 metadata，动态拼入 prompt
  - `build_cli_prompt()` 和 `build_cli_task_prompt()` 均注入身份三元事实（`member_id` + `decision_tier` + 业务角色）和群成员约束（只能提及清单内成员）
  - metadata 缺失时走默认严格策略："本群无角色约定，只严格回应字面请求，不要主动扩展话题，不要假设这是项目讨论环境，不要指名群外成员"
  - 新建 `deploy/bridges.example.json` 模板，含 `decision_tier` 字段和字段参考
- pi 和非 pi prompt 格式均同步更新为中文身份声明（"你是 {member_id}，通过 {runtime} CLI bridge 接入 TALK"）
- 测试同步更新：9 个 pi prompt 测试适配新格式，2 个 FakeClient 补充 `get_group` 方法
### Open Questions / Pending Confirmation
- `groups.metadata` 字段尚未落地（待修复项 5.4），5.3 按"metadata 缺失 → 默认严格策略"实现
- PROGRESS.md 第 1 节"Current Agent Role"过渡声明在 5.3 落地后可简化
### Verification
- `py_compile` 10 文件全部通过
- `unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_discussions tests.test_talk_client` 全部通过，70 tests
- 未做真实 Codex+pi 长链路主观体验自测
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `deploy/bridges.example.json`（新建）

## 2026-05-27 00:13 (Asia/Shanghai)
### Current Progress
- 在 `codex/scenario-1-scope-fix` 上补强场景 1 寒暄收口边界：确认 `greeting / closure` 都由 `NON_SUBSTANTIVE_STANCES` 排除，不计入实质 turn。
- 普通可见回复记录改走 `infer_reply_stance()`，寒暄返回 `greeting`，其它路径显式返回 `answer`，避免空 stance 落库。
- 动作转发仍可沿用动作自身 stance；若传入空默认值，会兜底为 `answer`。
- 新增测试覆盖：普通回复 stance 兜底、`greeting / closure` 过滤、已有寒暄 turn 不触发收口。
### Open Questions / Pending Confirmation
- `greeting` 识别仍采用保守关键词法；若后续黑盒验收发现“报个到 / 认识一下”等说法漏标较多，再考虑由模型结构化输出 `is_greeting`。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交本次补强。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，复验黑盒场景 1。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge` passed，43 tests。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，59 tests。

## 2026-05-27 00:06 (Asia/Shanghai)
### Current Progress
- 已在分支 `codex/scenario-1-scope-fix` 完成 `SCENARIO1-GREETING-TURNS-1`：收口阈值改为只统计实质 turn，避免把打招呼/在线确认当成议题讨论轮次。
- `discussion_turns.stance` 白名单新增 `greeting / closure`；bridge 会把明确的打招呼/在线确认类短消息记录为 `greeting`，自动收口消息记录为 `closure`。
- `greeting / closure` 被视为非实质 turn，不计入普通收口或分歧升级阈值；`disagree` 仍保留 human 裁决路径。
- `_send_agent_scope_closure()` 保留硬兜底 `resolved` 状态更新，但收口话术改为按 agent id 稳定挑选，避免不同 agent 复读同一句固定机器话。
- 新增/调整测试覆盖：代发打招呼动作为 `greeting` turn、非实质 turn 不触发收口、自动收口记录 `closure`、discussion API 接受 `greeting / closure`。
- 文档已同步 `docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续可由无项目记忆的黑盒测试 agent 复验场景 1。
- `greeting` 识别采用保守规则：任务范围像打招呼/在线确认，且回复较短、包含问候/在线确认特征时才标记为非实质 turn；其它回复仍默认 `answer`。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `SCENARIO1-GREETING-TURNS-1`。
2. 项目管理者重启 server / Codex bridge / pi bridge 后，优先复验黑盒场景 1：打招呼不应过早收口，也不应复读固定收口话术。
3. 若场景 1 通过，再继续处理测试文档中的下一类问题。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions tests.test_pi_bridge` passed，57 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` first run hit existing WebSocket fallback timing timeout once; immediate rerun passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`pause_before_next_slice`，weekly=84%，本轮提交后不再开启新切片。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `server/models.py`
- `tests/test_cli_bridge.py`
- `tests/test_discussions.py`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 18:16 (Asia/Shanghai)
### Current Progress
- `BRIDGE-SAFE-EXTEND-1` 已完成：修复黑盒测试暴露的 bridge 输出安全、开头多 mention、非 Group agent 委托和轻扩展收口问题。
- bridge 现在把消息开头连续 `@member_id` 块视为路由头，传给 CLI 的任务正文会剥离整段路由头；正文中间的 `@agent:*` 仍保留。
- CLI 失败/超时时，聊天可见回复只显示简短失败提示，不再回显 `stderr / stdout / traceback / 本地路径`；任务 `last_error` 仍可记录详细错误。
- malformed 动作协议或内部控制语法残留不会展示到可见回复；`send_message` 目标必须是当前 Group 内存在的 `agent:*`。
- 普通轻扩展允许对方再回答 1 个 turn；随后收到回复的一方自动收口并将 discussion 标记为 `resolved`。`disagree` 场景仍保留 human 裁决路径。
- 新增/调整单元测试覆盖：多 mention 路由头剥离、正文中间 mention 保留、CLI 失败输出安全、malformed 动作残留拦截、缺失 Group agent 代发拦截、轻扩展一轮回答和自动收口。
- 文档已同步 `docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮仍按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 复验自然对话效果。
- malformed 协议残留拦截采用“控制语法特征”隔离，不做自然语言意图分类；如果未来模型出现新型协议泄漏，可继续收敛规则。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `BRIDGE-SAFE-EXTEND-1`。
2. 重启当前正在运行的 Codex / pi bridge，使新 bridge 逻辑生效。
3. 让无项目记忆测试 agent 复验：多 mention 不报路径错误、`TALK_ACTION` 残留不显示、缺失 agent 不代发、轻扩展只多一轮并收口。
4. 复验通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_discussions.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_discussions` passed，52 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `usage-gate guard --provider codex --json` decision=`continue`，session=82%，weekly=76%。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 15:17 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-SCOPE-1` 已完成：为多 Agent 自动交流加入“请求者局部范围”约束，回复必须围绕当前直接提问/派活者的请求。
- `discussion_sessions` 新增可选范围锚点：`root_message_id / requester_id / assignee_id / scope_text`；旧记录允许为空，`init_db()` 会为既有 SQLite 表补列和索引。
- bridge 现在优先沿 `reply_to` / `root_message_id` 复用 discussion scope；已 `resolved / escalated / canceled` 的 scope 不再因普通 agent 回复继续触发模型续聊。
- agent-to-agent prompt 会传入控制上下文和消息原文，要求模型服从当前 scope 且不要把内部 ID/字段展示到可见回复；若可见回复泄漏内部字段，bridge 会替换为确认范围的简短回复。
- agent 普通可见回复若属于 active discussion，即使没有显式 `mark_stance`，也会按 `answer` 记录 turn。
- 新增/调整单元测试覆盖：打招呼 resolved scope 不再续聊、agent 给 agent 派活时 scope prompt 正确、普通 agent 回复自动记 turn、内部字段泄漏拦截、discussion scope API 校验。
- 文档已同步 `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_discussions.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 本轮按项目管理者要求不做真实 Codex+pi 长链路主观体验自测；后续由无项目记忆的黑盒测试 agent 验收自然对话效果。
- 范围越界识别当前主要依赖结构化 scope、prompt 约束和内部字段泄漏拦截；未做复杂自然语言分类。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 提交 `DISCUSSION-SCOPE-1`。
2. 准备黑盒验收任务单，让无项目记忆测试 agent 验证“打招呼不发散”“agent 给 agent 派活不偏题”“内部字段不泄漏”。
3. 验收通过后，再拆下一批使用建议：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\db.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py tests\test_discussions.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge` passed，38 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- Not run by design: 真实 Codex+pi 长链路体验自测；留给无项目记忆黑盒测试 agent。
### Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 11:12 (Asia/Shanghai)
### Current Progress
- `BASIC-CODEX-PI-FLOW-ACCEPT-1` 已完成：重启 TALK server、Codex bridge、pi bridge 后，跑通真实 Codex + pi Group Hall 讨论验收。
- 本轮先清理旧的重复 bridge 进程与 8000 端口上的 uvicorn reload 孤儿进程，再用当前 `.venv` 启动 server、Codex bridge、pi bridge；server 以无 `--reload` 方式运行，避免继续出现 reload 父子孤儿进程；bridge 日志写入 `logs/*current*.log`。
- 验收 Group 为 `group:c52be0b773e6`：human 消息 `#138` 正确触发 Codex；Codex 消息 `#139` 同 Hall 代发给 `@agent:pi`；pi 消息 `#141` 回复 Codex；Codex 消息 `#142` 将最终结论发给 `@human:bobo`。
- Discussion session `#6` 已创建，参与者为 `agent:codex` 与 `agent:pi`，状态从 `active` 变为 `resolved`。
- 项目管理者新增 4 条后续使用建议已记录到当前进度待办：自定义 agent 显示名称；无指定 agent 消息按广播要求所有 agent 接收并回复；删除 Group；自定义角色性格。
### Open Questions / Pending Confirmation
- 本轮首次验收脚本因 PowerShell -> Python 临时脚本编码问题，把中文消息写成 `????`（消息 `#136`）；重试时改用 ASCII 源码内的 Python Unicode escape 后已确认消息 `#138` 中文正确入库。
- 长轮询验收脚本高频 `fetch_history` 时偶发 `httpx.ReadError` / `RemoteProtocolError`，但 server 健康检查保持正常，消息与 discussion 均已落库；后续如要做自动验收脚本，应降低轮询频率或排查 HTTP 连接复用。
- Discussion turns 当前只记录了 Codex 的 `question` 与最终 `answer`；pi 的普通回复消息存在，但未作为 turn 记录，因为本轮 pi 没有输出 `mark_stance` 动作。后续如要完整 UI 展示讨论轮次，需要补“agent 回复自动落 turn”或强化 pi stance 输出。
- `docs/p.drawio` 仍是未跟踪文件，本轮未修改。
### Next Plan
1. 进入人工验收：浏览器打开 `http://127.0.0.1:8000/`，用 `human:bobo` 的 API Key 登录，查看 Group `smoke-codex-pi-20260526-b` 中 `#138` 到 `#142` 的完整回合。
2. 验收通过后，下一批建议优先拆需求：agent 自定义显示名称、广播语义、删除 Group、角色性格配置。
3. 若先补工程质量，建议处理：自动验收脚本 UTF-8 输入、HTTP 轮询偶发 `ReadError`、pi 回复 turn 记录缺失。
### Verification
- `Invoke-RestMethod http://127.0.0.1:8000/healthz` passed：`status=ok / db=ok / storage=ok / online_members=3`。
- Live smoke passed：`human:bobo -> agent:codex -> agent:pi -> agent:codex -> human:bobo`，消息 `#138` 到 `#142` 均在同一 Group Hall。
- DB verification passed：discussion session `#6` status=`resolved`，Codex / pi 最新实例 status=`idle` 且 `last_error=None`。
- First attempt failed as expected due to temporary PowerShell script encoding: message `#136` became `????` and Codex returned `#137` requesting resend。
- Not rerun: backend unit test suite；本轮只改进度文档并做真实运行验收。
### Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-26 01:22 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-FSM-TOKEN-SAFE-1` 已完成：按 `docs/p.drawio` 的有限状态机思路，为多 Agent 讨论加入安全动作协议、回合上限、最终答案动作和偏题抑制。
- `bridges/cli_bridge.py` 现在同时解析旧 `<talk-action ...>` 与新 `TALK_ACTION ...` 安全行协议；新增 `final_to_human`，可发送最终答案给 human 并把 discussion 标为 `resolved`。
- agent-to-agent 讨论默认最多 3 个自动 turn；最近一条为 `disagree` 时允许额外 1 个 turn。超限时 bridge 不再调用模型，直接 `@human:*` 请求最终判断并标记 `escalated`。
- agent-to-agent prompt 注入极短讨论上下文：原始话题、当前阶段、剩余回合和 human 目标，并明确禁止引入项目、文档、版本号或施工档等无关话题。
- bridge 会清理开头或结尾的孤立协议残片，例如 `mark_stance`、`update`、`动作已记录...`；模型只输出动作且来源是另一个 agent 时，不再额外发送默认回执。
- `bridges/pi_bridge.py` 默认 system prompt 改为只教授 `TALK_ACTION` 安全行协议，继续避开 Windows `pi.cmd` 高风险命令元字符。
- `tests/test_cli_bridge.py` 与 `tests/test_pi_bridge.py` 已补回归测试，覆盖安全行协议、`final_to_human`、协议残片清理、action-only agent 回执抑制、回合上限升级和 pi prompt 高风险字符限制。
- `docs/spec/MODULE_discussions.md` 与 `docs/spec/MODULE_bridges.md` 已同步当前协议边界。
### Open Questions / Pending Confirmation
- 需要重启 codex bridge 与 pi bridge；旧进程不会自动加载新的协议解析、回合上限和 pi 默认 `--system-prompt`。
- `docs/p.drawio` 是本次评估输入，未被本切片修改；当前仍是未跟踪文件，是否纳入仓库需后续由项目管理者确认。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收，重点观察 pi 不再露出 `mark_stance`、讨论不再跑题、Codex 不再跟随偏题、自动回合数受限。
### Next Plan
1. 提交 `DISCUSSION-FSM-TOKEN-SAFE-1`。
2. 重启 TALK server（如仍是旧进程）、codex bridge 与 pi bridge。
3. 在 Group Hall 重试：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
4. 验收达成共识后能 `final_to_human` 回给 human；若分歧或超限，则自动转 human 裁决。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，34 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge tests.test_discussions` passed，37 tests。
- 分批验证 passed：`tests.test_codex_bridge tests.test_groups tests.test_messages` 37 tests；`tests.test_files tests.test_healthz tests.test_instances tests.test_members_auth tests.test_tasks` 28 tests；`tests.test_encoding tests.test_setup` 6 tests；`tests.test_talk_client` 11 tests；`tests.test_sse` 6 tests。
- `tests.test_websocket` 聚合运行在当前环境超时；已用逐用例 30s 超时脚本验证 `WebSocketTests` 10 个用例全部单独 passed。
- `.venv\Scripts\python.exe -m unittest` 当前环境超时，未作为通过项记录。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_discussions.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:51 (Asia/Shanghai)
### Current Progress
- `WEB-REPLY-COMPACT-1 / PI-CMD-METACHAR-HOTFIX-1` 已完成：优化多 Agent 讨论中的引用展示，并修复 pi 默认 prompt 在 Windows `pi.cmd` 启动链下被误解释为命令的问题。
- `web/app.js` 的回复引用渲染现在会区分双方互相回复与引用第三方：双方互相回复显示 `A 回复 B` 短文本；引用第三方仍保留原引用框和预览。
- `web/style.css` 新增紧凑引用条样式，去掉大背景与左边框，仅保留小号灰色文本，并继续支持已加载原消息的点击跳转。
- `web/index.html` 静态资源版本号更新为 `20260525-reply-compact`，避免浏览器继续拿旧 CSS/JS。
- `bridges/pi_bridge.py` 默认 system prompt 移除原始 `<talk-action ...>` 示例、`agree|optimize|...` 竖线写法和 Windows 高风险命令元字符，避免 `pi.cmd` 把 prompt 当作管道/重定向语法解析。
- `tests/test_pi_bridge.py` 新增默认 prompt 不包含 `| / < / > / &` 的回归断言。
- `docs/spec/MODULE_webui.md` 与 `docs/spec/MODULE_bridges.md` 已同步本次行为边界。
### Open Questions / Pending Confirmation
- 需要重启 pi bridge；正在运行的旧 pi 进程不会自动加载新的默认 `--system-prompt`。
- Web UI 刷新页面即可加载新静态资源；若仍看到旧引用框，先强制刷新浏览器缓存。
- Codex + pi 双 Agent 真实端到端讨论回合仍需人工验收，重点观察 codex 代发给 pi、pi 回复不再出现 `optimize` 命令错误、双方互相回复时引用条是否紧凑。
### Next Plan
1. 提交本次 hotfix。
2. 重启 pi bridge；必要时一并重启 TALK server 与 codex bridge，确保 server API、bridge 协议和前端资源同版。
3. 重试用户原句：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\pi_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_pi_bridge tests.test_cli_bridge` passed，28 tests。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest` passed，129 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
- Browser / in-app browser：已打开 `http://127.0.0.1:8000/` 并确认页面加载 `style.css?v=20260525-reply-compact` 与 `app.js?v=20260525-reply-compact`；受当前 browser 安全/只读执行环境限制，未能构造临时消息样例做视觉断言。
### Changed Files
- `bridges/pi_bridge.py`
- `tests/test_pi_bridge.py`
- `web/app.js`
- `web/style.css`
- `web/index.html`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:21 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-PROTOCOL-1-HOTFIX-1` 已完成：修复 bridge 在 `/api/discussions` 返回 404 时直接抛 `TalkNotFoundError` 的问题。
- 根因：用户实际验收时 codex bridge 已尝试执行 `talk-action`，但 TALK server 可能仍是旧进程或尚未加载 `server/routes/discussions.py`，导致 SDK 在 `client.list_discussions(...)` 处收到 404。
- `bridges/cli_bridge.py` 现在将 discussion API 的 404 视为“讨论记录暂不可用”，跳过 session/turn 写入，但继续执行 `send_message` 代发、可见回复和其它可完成动作。
- `tests/test_cli_bridge.py` 新增 discussion API 缺失时仍能代发 `@agent:*` 且不崩溃的回归测试。
### Open Questions / Pending Confirmation
- 仍建议重启 TALK server、codex bridge、pi bridge，让 server API 与 bridge 协议版本一致；否则可以代发，但不会记录 discussion turn。
### Next Plan
1. 提交 hotfix。
2. 重启服务与 bridge 后重试用户原句：`@agent:codex 帮我把“人类是怎么进化来的？”这个问题拿去问下@agent:pi，然后你们讨论下答案。`
3. 观察 Group Hall 是否出现 codex 代发给 pi 的 `@agent:pi ...` 消息，以及 `/api/discussions` 是否记录 session/turn。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_discussions tests.test_pi_bridge` passed，31 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 16:10 (Asia/Shanghai)
### Current Progress
- `DISCUSSION-PROTOCOL-1` 已完成：新增可记录多 Agent 讨论协议，Discussion Session / Turn 结构化记录讨论参与者、顺序、立场和轮次。
- `server/models.py` 新增 `DiscussionSession`、`DiscussionTurn` 及请求/响应 schema；`server/db.py` 补充 discussion 相关索引。
- 新增 `server/routes/discussions.py` 并接入 `server/main.py`：支持创建/读取/更新 discussion、追加/查询 ordered turns；非 Group 成员不可访问，turn 只能引用当前成员本人在同一 Group Hall 的消息。
- `TALK/client/talk_client.py` 与 sync wrapper 新增 discussion helper，SDK 可创建 session、追加 turn、查询 turns。
- `bridges/cli_bridge.py` 新增 Group Hall 参与者 prompt、`talk-action` 解析与执行：`send_message` 可同 Hall 代发 `@agent:*` 并自动创建/复用 discussion，`mark_stance` 可记录当前回复立场，连续两条不同 agent 的 `disagree` 后自动 `@human:*` 升级仲裁。
- `bridges/pi_bridge.py` 默认 system prompt 改为 TALK Group Hall 参与者身份与动作协议；默认仍是讨论档，新增 `--pi-execution-profile tools` 显式施工档，使用默认命令时启用 `read,grep,find,ls,bash,edit,write`。
- 新增 `docs/spec/MODULE_discussions.md`，并同步 `docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_groups.md`、`docs/spec/MODULE_bridges.md`。
### Open Questions / Pending Confirmation
- 需要重启 codex/pi bridge 后才能加载本次新协议。
- Web UI 尚未展示 discussion session/turn；当前通过 API、SDK 与 bridge 自动动作使用。
- pi 施工档只在显式 `--pi-execution-profile tools` 时启用；后续若让 pi 真正施工，需要按任务明确授权并验收。
- Codex + pi 双 Agent 真实端到端讨论仍需人工验收。
### Next Plan
1. 提交 `DISCUSSION-PROTOCOL-1`。
2. 重启 bridge 后，在 Group Hall 验收 Codex 向 pi 转交计划、pi 回复优化/分歧、两轮分歧升级 human。
3. 后续补 Web UI discussion 面板，并评估与任务队列、文档锁、SSE 的联动。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\discussions.py server\main.py TALK\client\talk_client.py TALK\client\talk_client_sync.py bridges\cli_bridge.py bridges\pi_bridge.py tests\test_discussions.py tests\test_cli_bridge.py tests\test_pi_bridge.py tests\test_talk_client.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_discussions tests.test_cli_bridge tests.test_pi_bridge` passed，30 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed，11 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge tests.test_groups tests.test_messages` passed，37 tests。
- `.venv\Scripts\python.exe -m unittest` passed，128 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `server/models.py`
- `server/routes/discussions.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_discussions.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_discussions.md`
- `docs/spec/MODULE_groups.md`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 12:21 (Asia/Shanghai)
### Current Progress
- `PI-SYSTEM-PROMPT-BOUNDARY-1` 已完成：按项目管理者确认，将 pi 的身份/能力边界从用户 prompt 中移到默认 `pi --system-prompt`，避免 `TALK...` 等包装文本被 pi 当成用户没说完的正文。
- `bridges/pi_bridge.py` 默认命令恢复极短中文 `--system-prompt`，同时继续保留 `--no-context-files --no-tools --no-session --thinking off`。
- `bridges/cli_bridge.py` 的 pi 消息 prompt 现在只返回去掉 `@agent:pi` 后的用户原文，例如 `@agent:pi 你好` 精确传给 pi 为 `你好`。
- pi 队列任务 prompt 默认只传 `content`；如存在 `title`，传 `标题：<title>\n\n<content>`。
- pi prompt 不再包含 `用户消息`、`用户任务`、`回复要求`、`Sender`、`TALK message id`、`TALK task id`、`Task creator`、`TALK group id` 或 `Project root`；但实际回复仍携带原消息 `group_id` 写回同一个 Group Hall。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签回复时才替换；正常中文或用户明确要求英文时不干预。
- `tests/test_cli_bridge.py` 已更新 pi prompt 断言：普通消息精确等于去 mention 后原文、队列任务只保留正文/标题、Group Hall 回复仍保留原 `group_id`。
- `tests/test_pi_bridge.py` 已更新默认命令断言：必须包含 `--system-prompt` 与隔离参数。
- `docs/spec/MODULE_bridges.md` 已同步 pi system prompt 分离边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次修复。
- 重启后建议验收：`@agent:pi 你好`、`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 如果用户使用 `TALK_PI_COMMAND` 或 `--pi-command` 自定义 pi 命令，需要自行带上等价 `--system-prompt` 和隔离参数。
### Next Plan
1. 提交本次 `PI-SYSTEM-PROMPT-BOUNDARY-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，23 tests。
- 分组显式全量 passed，合计 121 tests：`tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_pi_bridge` 35 tests；`tests.test_files tests.test_groups tests.test_healthz tests.test_members_auth tests.test_messages` 40 tests；`tests.test_instances tests.test_tasks tests.test_talk_client` 27 tests；`tests.test_setup tests.test_sse tests.test_websocket` 19 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed；仅提示 Windows 工作区后续可能将 LF 替换为 CRLF，无 whitespace error。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 11:41 (Asia/Shanghai)
### Current Progress
- `PI-MINIMAL-PROMPT-1` 已完成：按项目管理者确认，将 pi bridge 输入包装改为“用户原话优先”的极简 prompt，减少英文元指令对 pi 语言选择和身份判断的干扰。
- `bridges/cli_bridge.py` 中 pi 消息 prompt 现在以 `用户消息：` 开头，直接放去掉 `@agent:pi` 后的原话；pi 队列任务 prompt 以 `用户任务：` 开头，只有任务标题存在时才作为用户任务内容的一部分保留。
- pi prompt 后置一条中文短边界：`你是 TALK 群聊里的 pi，按用户语言自然回复。默认不要声称能读取项目文件、执行命令、编辑文件或调用工具。不要输出 <Language: ...> 之类语言标签。`
- pi prompt 不再传入 `Sender`、`TALK message id`、`TALK task id`、`Task creator` 或 `TALK group id`；但实际回复仍携带原消息 `group_id` 写回同一个 Group Hall。
- 非 pi runtime 的执行型 prompt 保持不变；Codex bridge 不受影响。
- `normalize_pi_reply_language(...)` 保留为异常兜底：中文请求得到非中文/语言标签回复时才替换；正常中文或用户明确要求英文时不干预。
- `tests/test_cli_bridge.py` 已更新 pi prompt 断言：用户原话在最前、无不必要元信息、包含中文短边界、Group Hall 回复仍保留原 `group_id`。
- `docs/spec/MODULE_bridges.md` 已同步 pi 极简 prompt 边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次极简 prompt 修复。
- 重启后建议验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 不会自动改写；本次修复只影响后续新回复。
- 单条显式全量 `unittest` 本轮 300 秒超时且无失败栈；分组运行同一模块集合合计 120 tests 全部通过。
### Next Plan
1. 提交本次 `PI-MINIMAL-PROMPT-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- 分组显式全量 passed，合计 120 tests：bridge/pi/encoding 34 tests；files/groups/healthz/auth/messages 40 tests；instances/tasks/client 27 tests；setup/sse/websocket 19 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` timeout after 300s，无失败栈。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-25 11:16 (Asia/Shanghai)
### Current Progress
- `PI-LANGUAGE-REPLY-1` 验收期修复已完成：根据用户反馈，排查最近 Group Hall 消息，确认 `#38 -> #39` 为中文功能问题却返回 `<Language: ar>` 阿拉伯语；`#40 -> #41` 明确要求中文却返回英文，并误称自己能读文件、执行命令、编辑文件。
- 根因判断：消息已正确写入同一个 Group Hall，路由和 `group_id` 回复不是问题；问题在于 pi 撤销命令级强 system prompt 后，TALK prompt 语言跟随约束不足，且缺少窄范围后处理来拦住明显跑语种/能力误述。
- `bridges/cli_bridge.py` 新增 `PI_CHAT_INSTRUCTIONS`：pi 继续是自然聊天的 TALK chat member，但明确要求回复语言跟随用户任务；用户要求中文时使用简体中文；不要输出 `<Language: ...>` 标签；能力介绍只能描述轻量聊天、回答问题、拆解任务、参与 Group Hall 协作，不得声称默认 bridge 模式能读文件、执行命令、编辑文件或调用工具。
- `bridges/cli_bridge.py` 新增 pi 成功输出后的中文归一化兜底：当中文任务/能力问题得到明显非中文回复或语言标签回复时，替换为中文能力说明；真实 CLI 失败或超时不做替换，避免遮盖错误。
- `tests/test_cli_bridge.py` 新增回归覆盖：pi prompt 语言要求、能力边界、中文能力问题的非中文回复替换、阿拉伯语语言标签替换、明确要求英文时不误替换、Group Hall 中 pi 回复仍保留原 `group_id`。
- `docs/spec/MODULE_bridges.md` 已同步 pi 语言跟随与中文能力兜底边界；默认 `pi_bridge.py` 命令仍不使用 `--system-prompt`。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge；正在运行的旧 pi bridge 不会自动加载本次修复。
- 重启后建议验收：`@agent:pi 你好啊，你有哪些功能？`、`@agent:pi 你好啊，你有哪些功能？用中文回复`、`@agent:pi 请用英文介绍你有哪些功能`。
- 旧消息 `#39` / `#41` 不会自动改写；本次修复只影响后续新回复。
- `python -m unittest` discovery 在本轮环境中超时但无失败栈；显式模块列表全量 120 tests 已通过，后续可单独排查 discovery 阻塞原因。
### Next Plan
1. 提交本次 `PI-LANGUAGE-REPLY-1` 修复。
2. 用户重启 pi bridge 后继续人工验收语言跟随和能力边界。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，22 tests。
- `.venv\Scripts\python.exe -u -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_encoding tests.test_files tests.test_groups tests.test_healthz tests.test_instances tests.test_members_auth tests.test_messages tests.test_pi_bridge tests.test_setup tests.test_sse tests.test_talk_client tests.test_tasks tests.test_websocket` passed，120 tests。
- `.venv\Scripts\python.exe -m unittest` 超时 120 秒；`.venv\Scripts\python.exe -m unittest -v` 超时 300 秒，均未输出失败栈。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 22:15 (Asia/Shanghai)
### Current Progress
- `PI-NATURAL-CHAT-1` 验收期修正已完成：按用户确认，将 pi 调整为“自然回答的 TALK 聊天成员”，不再用强 system prompt 或 bridge 弱回复替换限制它的回答风格。
- 设计判断已确认：方向上与 OpenHanako 一致，平台应负责上下文/权限隔离；Agent 在频道里默认是聊天成员，不应因为 bridge 从 TALK 代码项目根目录启动，就自动成为 TALK 项目的开发 Agent。
- `bridges/pi_bridge.py` 默认命令已移除 `--system-prompt`，只保留 `--no-context-files --no-tools --no-session --thinking off`，用于防止 pi 自动读取 TALK 代码项目上下文、调用工具或恢复旧会话。
- `bridges/cli_bridge.py` 已移除能力问题弱回复替换逻辑；pi 的成功输出不再被 bridge 改写。
- pi 的消息与任务 prompt 不再包含 `Project root`，只标识为 `TALK chat member`，并携带发送人/任务创建人、消息或任务 id、可选 group id 与用户任务。
- `tests/test_cli_bridge.py` 已覆盖 pi 消息/任务 prompt 不含项目根路径；`tests/test_pi_bridge.py` 已覆盖 pi 默认命令不再包含 `--system-prompt`，但仍保留隔离参数。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge 后重新验收；正在运行的旧 pi bridge 不会自动加载本次修正。
- 重启后建议验收：`@agent:pi 你好`、`@agent:pi 你能做啥？给我介绍下`、`@agent:pi 随便聊两句`，观察 pi 是否自然回答，同时不再输出 TALK 项目进度报告。
- 后续可把“上下文/工具/文件权限由平台管理”的设计沉淀为 Group/Agent 协议，而不是依赖各 bridge 的 CLI 参数。
### Next Plan
1. 提交本次 `PI-NATURAL-CHAT-1` 验收期修正。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 自然聊天回复。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，17 tests。
- `.venv\Scripts\python.exe -m unittest` passed，115 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 22:00 (Asia/Shanghai)
### Current Progress
- `PI-CAPABILITY-REPLY-1` 验收期修复已完成：修复用户在 Group Hall 询问 `@agent:pi 你能做啥？/ 给我介绍下` 时，pi 只回复 `ok` 或在线待命话术的问题。
- 现场排查确认：消息 id 32 -> 33 为 `@agent:pi 你能做啥？` 后回复 `ok`；消息 id 36 -> 37 为 `@agent:pi 你能做啥？给我介绍下` 后回复 `Pi agent online. What task would you like me to help with?`。消息已正确进入同一个 Group Hall，说明问题不在路由，而在 pi 默认提示词缺少能力介绍边界，以及模型弱回复没有兜底。
- `bridges/pi_bridge.py` 已补充默认 system prompt：当用户询问能力或介绍时，pi 应说明自己适合轻量聊天、回答问题、拆解任务和参与 TALK 群聊协作，并说明默认桥接模式不读取项目文件、不调用工具。
- `bridges/cli_bridge.py` 已新增能力问题弱回复兜底：当任务问“你能做啥 / 你能做什么 / 介绍下”等，而 CLI 成功输出只有 `ok`、`standing by` 或在线待命话术时，bridge 会替换为一条可验收的能力说明。
- `tests/test_cli_bridge.py` 已覆盖 pi 能力问题弱回复替换；`tests/test_pi_bridge.py` 已覆盖 pi 默认 system prompt 包含能力介绍边界。
- `docs/spec/MODULE_bridges.md` 已同步 pi 能力介绍提示词与弱回复兜底边界。
### Open Questions / Pending Confirmation
- 需要用户重启 pi bridge 后重新发送 `@agent:pi 你能做啥？给我介绍下` 验收；正在运行的旧 pi bridge 不会自动加载本次修复。
- 如果用户使用 `TALK_PI_COMMAND` 或 `--pi-command` 自定义 pi 命令，需要保留默认命令中的 system prompt 边界，或自行提供等价提示词。
### Next Plan
1. 提交本次 `PI-CAPABILITY-REPLY-1` 验收期修复。
2. 用户重启 pi bridge 后，继续在 Group Hall 验收 pi 能力介绍回复。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，18 tests。
- `.venv\Scripts\python.exe -m unittest` passed，116 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:53 (Asia/Shanghai)
### Current Progress
- `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复已完成：修复 Codex 回复中 `taskkill` 噪声已被过滤后，正文“在线。”仍显示为 `鍦ㄧ嚎銆` 一类 mojibake 的问题。
- 现场排查确认：数据库最新 Codex 回复已不再包含 PID 清理提示，但 `content` 中“在线。”被错误解码成 mojibake，说明上一版噪声过滤生效但编码选择仍不够细。
- 根因是 Codex stdout 中混合了不同编码来源：Windows `taskkill` 行更像系统代码页，Codex 正文行是 UTF-8；按整段输出选择单一编码会互相拖累。
- `bridges/cli_bridge.py` 的 `decode_subprocess_output(...)` 已改为逐行选择编码；同一 stdout 中 GBK 清理提示和 UTF-8 正文可以分别正确解码。
- `tests/test_cli_bridge.py` 已新增混合编码行回归测试，覆盖 GBK `taskkill` 行 + UTF-8 `codex 在线。` 行的组合。
- `docs/spec/MODULE_bridges.md` 已同步通用 CLI bridge 的逐行解码边界。
### Open Questions / Pending Confirmation
- 需要用户再次重启 Codex bridge 后重新发送 `@agent:codex 你好` 验收；正在运行的旧 Codex bridge 不会自动加载本次修复。
- 历史消息 id 29 已经写入数据库，仍会保留旧 mojibake 内容；本次修复只影响后续新回复。
### Next Plan
1. 提交本次 `CODEX-BRIDGE-MIXED-ENCODING-1` 验收期修复。
2. 用户重启 Codex bridge 后，继续在 Group Hall 验收 Codex 回复内容是否干净且中文正常。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_encoding` passed，18 tests。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:41 (Asia/Shanghai)
### Current Progress
- `CODEX-BRIDGE-OUTPUT-1` 验收期修复已完成：修复 Codex 在 Group Hall 回复“在线”前混入 Windows 进程终止提示且中文乱码的问题。
- 现场排查确认：最新 Codex 回复已写回 Group Hall，说明 `GROUP-BRIDGE-REPLY-1` 的同 Hall 回复修复已生效；但消息内容包含乱码的 `taskkill` PID 成功提示，对应 Windows 进程清理输出被错误编码解码后混入回复。
- `bridges/cli_bridge.py` 已新增 `decode_subprocess_output(...)`：优先 UTF-8，并在出现替换字符时兜底尝试系统代码页、`gbk`、`cp936`，降低 Windows 本地 CLI 中文输出乱码概率。
- `format_cli_reply(...)` 现在会对 stdout / stderr 做 `taskkill` 噪声过滤，避免 Codex CLI 退出清理子进程时的 PID 提示出现在前端聊天回复里。
- `tests/test_cli_bridge.py` 已新增 GBK 输出解码与中英文/乱码 `taskkill` 过滤回归测试。
- `docs/spec/MODULE_bridges.md` 已同步通用 CLI bridge 的 Windows 输出编码与进程清理噪声过滤边界。
### Open Questions / Pending Confirmation
- 需要用户重启 Codex bridge 后重新发送 `@agent:codex 你好` 验收；正在运行的旧 Codex bridge 不会自动加载本次修复。
- 历史消息 id 23 已经写入数据库，仍会保留旧乱码内容；本次修复只影响后续新回复。
### Next Plan
1. 提交本次 `CODEX-BRIDGE-OUTPUT-1` 验收期修复。
2. 用户重启 Codex bridge 后，继续在 Group Hall 验收 Codex 回复内容是否干净。
3. 继续 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，25 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，114 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 21:37 (Asia/Shanghai)
### Current Progress
- `GROUP-BRIDGE-REPLY-1` 验收期修复已完成：修复 Group Hall 中 `@agent:codex` / `@agent:pi` 后 bridge 已收到消息但回复失败的问题。
- 现场排查确认：用户新建 group 后发送的两条消息都已写入 `messages.group_id`，`to_ids` 分别为 `["agent:codex"]` 与 `["agent:pi"]`，且两个 bridge 都已领取到对应消息。
- 两个实例失败原因一致：`agent_instances.last_error` 为 `cannot_reply_to_different_group`，说明 bridge 处理了消息，但回复时没有保留原 Hall 上下文。
- `bridges/cli_bridge.py` 已抽出 `handle_incoming_message(...)`，统一处理 ACK、CLI 调用、最终回复和状态上报；当原消息带有 `group_id` 时，ACK 与最终 `reply_to` 都会携带同一个 `group_id`。
- CLI prompt 现在包含 `TALK group id`，便于 Codex / pi 等外部 Agent 感知当前消息来自哪个 Group Hall。
- `tests/test_cli_bridge.py` 已新增 Group Hall prompt 与同 group 回复回归测试，覆盖 `group_id` 传递行为。
- `docs/spec/MODULE_bridges.md` 已同步 Codex / pi Group Hall 当前能力与后续 HTTP fallback group cursor 边界。
### Open Questions / Pending Confirmation
- 需要用户重启 Codex bridge 与 pi bridge 后重新验收；正在运行的旧进程不会自动加载本次代码修复。
- 本次现场失败的旧消息不会自动重试；重启 bridge 后需在前端 Group Hall 中重新发送新的 `@agent:codex` / `@agent:pi` 消息。
- Group Hall 的实时触发当前主要依赖 WebSocket；Agent group cursor / HTTP fallback 轮询仍留作当前验收后的下一阶段设计。
### Next Plan
1. 提交本次 `GROUP-BRIDGE-REPLY-1` 验收期修复。
2. 用户重启 Codex / pi bridge 后，继续在前端 Group Hall 验收双 Agent 回复。
3. 验收通过后，再评估下一阶段多 Agent 自动讨论协议。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py tests\test_cli_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_talk_client` passed，23 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，112 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-24 16:41 (Asia/Shanghai)
### Current Progress
- `OPENHANAKO-REF-1` 文档沉淀已完成：用户提供 `liliMozi/openhanako` 作为多 Agent 拉群交流参考后，已把对 TALK 有帮助的设计点记录到项目文档。
- `docs/spec/LOCAL_LAB_DESIGN.md` 已新增 OpenHanako 参考笔记，记录参考版本 `dbc794de87d58b44bbf5f75f8d20fd99a5d7e156` 与重点文件：`hub/channel-router.js`、`lib/channels/channel-ticker.js`、`lib/channels/channel-store.js`、`lib/channels/channel-mentions.js`、`lib/tools/dm-tool.js`。
- 已记录可借鉴点：Group Hall 作为真相源、`@mention` 只表示提醒/调度、Agent 显式 `reply/pass`、Agent group cursor、`max_rounds / cooldown / max_agent_checks` 等调度保护。
- 已记录不照搬内容：Electron / Node Hub 架构、Markdown 文件频道存储、主动心跳、长期记忆、人格系统、复杂桌面工作台。
- `docs/spec/MODULE_groups.md` 已补充 Group/Hall 后续协议参考，明确 TALK 继续使用 SQLite 的 `groups / group_members / messages` 扩展。
### Open Questions / Pending Confirmation
- OpenHanako 参考只作为当前验收后的下一阶段设计素材；是否实现 Agent group cursor、`reply/pass` 决策协议和自动讨论调度器，需等 Codex + pi + Web UI 联合验收完成后再确认。
### Next Plan
1. 提交本次 `OPENHANAKO-REF-1` 文档沉淀。
2. 继续当前范围冻结分支的 Codex + pi 双 bridge 与 Web UI 视觉/交互联合人工验收。
3. 验收通过后，再基于 OpenHanako 参考评估下一阶段多 Agent 自动讨论协议。
### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 18:13 (Asia/Shanghai)
### Current Progress
- `PI-BRIDGE-CHAT-1` 验收期修复已完成：针对用户反馈的 pi 回复慢、回复过长、即使要求一句话仍带入项目状态报告的问题，收敛 pi bridge 默认运行方式。
- `bridges/pi_bridge.py` 默认命令从裸 `pi --print --mode text` 调整为聊天验收模式：增加 `--no-context-files --no-tools --no-session --thinking off`，并通过 `--system-prompt` 要求 pi 只回复 TALK 用户任务、不要读取/总结项目文件或进度。
- 通用 `bridges/cli_bridge.py` 新增“一句话”兜底：当任务文本包含“一句话 / one sentence / single sentence”等约束时，CLI 成功输出会在 bridge 层收敛为第一句或第一行后再发回 TALK。
- `tests/test_pi_bridge.py` 已覆盖 pi 默认命令中的上下文/工具/session/thinking/system prompt 收敛参数。
- `tests/test_cli_bridge.py` 已覆盖“一句话”输出收敛逻辑。
- `docs/spec/MODULE_bridges.md` 已同步 pi 默认命令的新边界，并提醒自定义 `TALK_PI_COMMAND` / `--pi-command` 时需自行保留收敛参数。
### Open Questions / Pending Confirmation
- 需用户重启 pi bridge 后在前端人工验收：`@agent:pi 只用一句话回复：你在线吗？` 应返回简短一句，不再输出项目状态报告。
- 如果用户当前通过 `TALK_PI_COMMAND` 或 `--pi-command` 自定义了 pi 命令，需要同步加入本次默认命令中的收敛参数；否则会绕过默认修复。
- 本轮未真实调用 DeepSeek/pi 模型 API，只通过命令参数、单元测试和全量测试验证 bridge 行为。
### Next Plan
1. 提交本次 `PI-BRIDGE-CHAT-1` 修复。
2. 用户重启 pi bridge 后继续前端人工验收。
3. 验收通过后继续 Codex + pi 双 Agent 回复链路与 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_pi_bridge` passed，12 tests。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，110 tests。
- `node --check web\app.js` passed。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/pi_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_pi_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:59 (Asia/Shanghai)
### Current Progress
- `WEB-MENTION-ENTER-1` 验收期修复已完成：修复前端在 `@` 补全下拉打开时按 Enter 会先发送裸 `@`，导致服务端返回 `invalid recipient mention: @` 的问题。
- `web/app.js` 的消息发送快捷键现在会在 mention 下拉框可见时让出 Enter，避免与补全选择逻辑抢事件顺序。
- mention 补全逻辑已调整为：下拉框打开时，Enter / Tab 都会选择当前高亮项；若没有高亮项，则选择首个候选。
- mention 候选项增加 `mousedown` 防 blur 处理，鼠标点击选择 `agent:pi` / `agent:codex` 时会稳定补全到输入框。
- `web/index.html` 已更新 `app.js` 版本参数，浏览器刷新后会加载本次修复。
### Open Questions / Pending Confirmation
- 需用户刷新前端页面后继续人工验收：输入 `@`，分别用 Enter 和鼠标选择 `agent:pi` / `agent:codex`，确认不再出现裸 `@` 错误。
- Codex + pi 双 bridge 的真实端到端回复仍在人工验收中；本切片只修复前端 mention 补全误发送问题。
### Next Plan
1. 提交本次 `WEB-MENTION-ENTER-1` 修复。
2. 用户刷新页面后复测 `@` 补全选择。
3. 重启 Codex / pi bridge，继续双 Agent 回复与 Web UI 视觉/交互联合验收。
### Verification
- Browser / in-app browser 手工验证 passed：输入裸 `@` 后按 Enter 会补全为首个候选，不再出现 `invalid recipient mention: @`。
- Browser / in-app browser 手工验证 passed：输入 `@agent:p` 后鼠标点击 `agent:pi` 候选，会稳定补全为 `@agent:pi `。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，108 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `web/app.js`
- `web/index.html`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:35 (Asia/Shanghai)
### Current Progress
- `BRIDGE-WINDOWS-CMD-1` 验收期修复已完成：修复 Windows 下 bridge 直接调用 `codex` / `pi` 找不到命令的问题。
- 用户在前端 `@agent:codex` / `@agent:pi` 后未收到回复；排查确认 TALK 服务在线，消息已正确写入 `messages.to_ids`，bridge 进程在线并轮询任务，但 `agent_instances` 中 Codex / pi 均上报 `error`，`last_error` 为 `[WinError 2] 系统找不到指定的文件。`。
- `bridges/cli_bridge.py` 在启动子进程前会用 `shutil.which()` 解析命令入口，使 `pi` 可解析到 `pi.CMD`。
- `bridges/codex_bridge.py` 默认优先使用 `~\AppData\Local\OpenAI\Codex\bin\codex.exe`，避免命中 WindowsApps 中会 `Access is denied` 的 `codex.exe`。
- 新增测试覆盖：通用命令入口解析，以及 Codex 默认命令的环境变量覆盖路径。
### Open Questions / Pending Confirmation
- 需用户重启 Codex / pi bridge 后，在前端重新发送 `@agent:codex` 与 `@agent:pi` 消息完成回复验收。
- 当前已有旧 bridge 进程处于错误状态；建议在启动新 bridge 前先在原终端 `Ctrl+C` 停掉旧进程，避免多个实例同时处理。
### Next Plan
1. 提交本次 `BRIDGE-WINDOWS-CMD-1` 验收期修复。
2. 重启 Codex / pi bridge，再在前端重新发送消息验收。
3. 验收通过后，继续完成 Web UI 视觉/交互联合验收。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，18 tests。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 17:01 (Asia/Shanghai)
### Current Progress
- `PI-BRIDGE-1` 已完成：新增 `bridges/pi_bridge.py`，默认注册 `agent:pi`，默认 runtime 为 `pi`，默认错误标签为 `pi bridge`。
- `pi_bridge.py` 默认调用 `pi --print --mode text`；可通过 `TALK_PI_COMMAND` 或 `--pi-command` 覆盖，例如切换 provider / model。
- 通用 `bridges/cli_bridge.py` 已支持 `--prompt-transport stdin|argv`：Codex 继续用 stdin，pi 默认用 argv，把 TALK prompt 追加为最后一个命令行参数。
- 新增 `tests/test_pi_bridge.py`，覆盖 pi 默认身份、默认命令、argv prompt 传递方式与自定义 `--pi-command`。
- 扩展 `tests/test_cli_bridge.py`，覆盖通用 bridge 的 argv prompt 传递以及 queued task 调用时传递 `prompt_transport`。
- 本机已确认 `pi --help` 与 `pi --version` 可执行，版本为 `0.74.1`。
- `docs/spec/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步 pi bridge 入口、启动命令和当前边界。
### Open Questions / Pending Confirmation
- 真实 pi 模型调用仍依赖本机 `pi` 的 provider/API key 配置；本轮未消耗真实模型请求，只验证 CLI 入口与桥接参数。
- Codex + pi 双 Agent 同时运行的真实端到端回合尚未执行；下一步应进入人工验收或补一个双桥 smoke 脚本。
- 本里程碑验收必须同时覆盖 Web UI：此前 Web UI 第一版质量不达标，后续已按 `image_gen` 视觉稿方向重做并记录在 `docs/spec/MODULE_webui.md` 的 `WEB-VISUAL-2 Addendum`，需要和双 Agent bridge 一起验收。
### Next Plan
1. 提交本次 `PI-BRIDGE-1` 切片。
2. 按里程碑门禁暂停，提供 Codex + pi 双 bridge 与 Web UI 视觉/交互的联合人工验收步骤。
3. 验收通过后，下一候选切片是双 Agent 最小回合脚本 / 讨论 runner。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_encoding` passed，19 tests。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `pi --help` passed。
- `pi --version` returned `0.74.1`。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，105 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。
### Changed Files
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-21 16:54 (Asia/Shanghai)
### Current Progress
- `CLI-BRIDGE-1` 已完成：新增 `bridges/cli_bridge.py` 通用 CLI bridge，承接 TALK 成员注册、实例状态上报、消息触发、任务队列轮询、任务认领、CLI stdin/stdout 调用、结果回复与任务完成。
- `bridges/codex_bridge.py` 已收敛为 Codex 兼容入口：复用通用 CLI bridge 实现，同时保留 `--codex-command`、默认 `codex exec` 命令、`CodexRunResult` 和原 helper 函数兼容面。
- 通用 CLI bridge 支持 `--name / --runtime / --bridge-label / --command`：例如后续 `pi` 可注册为 `agent:pi`，以 `runtime=pi` 上报实例，并使用可配置命令读取 stdin prompt、输出 stdout 回复。
- 新增 `tests/test_cli_bridge.py`，覆盖通用 CLI 参数必填、runtime prompt、错误回复标签、stdin/stdout 命令执行、queued task 认领/回复/完成路径。
- `tests/test_codex_bridge.py` 继续通过，确认 Codex 旧兼容面未破坏。
- `docs/spec/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步通用 CLI bridge、Codex 兼容入口和 pi 接入方向。
### Open Questions / Pending Confirmation
- 用户方向判断已确认：先把 Codex bridge 泛化为通用 CLI bridge，是更快跑通 Codex + pi 双 Agent 的路线。
- pi 的具体 CLI 启动命令 / stdin/stdout 协议仍需确认；若 pi 不能直接从 stdin 读 prompt 并向 stdout 写最终回复，需要补一个很薄的 pi adapter。
- 本轮未做真实 Codex + pi 双进程端到端验收；下一切片应优先补 pi 启动示例 / adapter 与最小双 Agent 回合验证。
### Next Plan
1. 提交本次 `CLI-BRIDGE-1` 切片。
2. 下一切片：基于 `bridges/cli_bridge.py` 落 `pi` 启动示例 / adapter，并用 fake CLI 或真实 pi 命令跑通 `agent:codex <-> agent:pi` 的最小任务回合。
3. 若 pi 命令可直接适配 stdin/stdout，优先做配置与验收脚本；否则先实现 pi adapter。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge` passed，13 tests。
- `.venv\Scripts\python.exe bridges\cli_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，102 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。
### Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 23:16 (Asia/Shanghai)
### Current Progress
- `TASK-SCHEDULE-1` 已完成：新增 `agent_task_schedules` 表与 `/api/tasks/schedules` API 第一版。
- `agent_tasks` 新增可选 `schedule_id`，用于追踪由 schedule 物化出的 queued task。
- Schedule 支持一次性计划与周期计划：未传 `interval_seconds` 为 `once`，传入后为 `interval`。
- 新增 `POST /api/tasks/schedules/run-due`：显式物化当前到期的 active schedule，返回 `created_tasks` 与 `updated_schedules`。
- 一次性 schedule 物化后状态变为 `completed`；周期 schedule 物化后保持 `active` 并推进 `next_run_at`。
- Schedule 列表与读取沿用任务可见性：Human 可读全部，Agent 只能读目标为自己或自己创建的 schedule。
- Schedule 状态更新支持 `active`、`paused`、`canceled`；completed / canceled 不可恢复为 active 或 paused。
- SDK 已新增 async/sync schedule helper：创建、列表、读取、更新状态、运行到期计划。
- `docs/spec/MODULE_tasks.md` 与 `docs/PROJECT_BRIEF.md` 已同步数据模型、接口契约、当前边界和验收点。
### Open Questions / Pending Confirmation
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- Group 删除 / 归档语义仍需确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- 文档编辑锁协议、任务状态接入 Hall / Group Web UI 仍待实现。
### Next Plan
1. 提交本次 `TASK-SCHEDULE-1` 切片。
2. 下一候选切片：文档编辑锁协议，或将任务 / schedule 状态接入 Hall / Group Web UI。
3. Group 删除 / 归档语义需项目管理者确认后再做。
### Verification
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/slice-usage-gate.ps1 -Agent codex` returned `continue`。
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\tasks.py server\db.py tests\test_tasks.py tests\test_talk_client.py TALK\client\talk_client.py TALK\client\talk_client_sync.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_tasks tests.test_talk_client` passed，22 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，97 tests。
- `git diff --check` passed（仅换行提示）。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-progress.ps1 -Strict -RequireHistory` passed。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-git-ready.ps1` passed。
### Changed Files
- `server/models.py`
- `server/routes/tasks.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/spec/MODULE_tasks.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 18:13 (Asia/Shanghai)
### Current Progress
- `GROUP-UPDATE-1` 已完成：新增 `PATCH /api/groups/{group_id}`，human 可更新 Group 名称与描述，agent 不可更新。
- `GroupUpdate` schema 已加入服务端校验：`name` 必填且去空白，`description` 可选且空字符串归一为 `None`。
- SDK 已新增 async/sync `update_group(...)` helper。
- Web UI 已在 Hall 成员面板顶部加入 Group 设置表单，保存后会刷新 room strip、成员面板与 mention/presence 相关视图。
- 静态资源 cache busting 已更新到 `20260520-group-meta`。
- Group 删除未在本切片实现：删除会影响历史 Hall 消息可见性，属于需要项目管理者确认的数据语义。
- `docs/spec/MODULE_groups.md` 已同步接口契约、Web UI 能力、当前边界和验收点。
### Open Questions / Pending Confirmation
- Group 删除 / 归档语义仍需确认：历史 Hall 消息应保留、归档还是随 Group 删除。
### Next Plan
1. 下一候选切片：确认并实现 Group 删除 / 归档语义，或文档编辑锁协议。
2. 如继续前端 / SSE 相关切片，保持 Browser 真实页面烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\models.py server\routes\groups.py tests\test_groups.py tests\test_talk_client.py` passed。
- `node --check web\app.js` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_talk_client` passed，15 tests。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，92 tests。
- `git diff --check` passed（仅换行提示）。
- Browser 真实页面验证 passed：human 在成员面板更新 Group 名称与描述后，Hall 标题、房间按钮、成员面板输入值和空时间线文案均同步刷新。
### Changed Files
- `server/models.py`
- `server/routes/groups.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_groups.py`
- `tests/test_talk_client.py`
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 17:19 (Asia/Shanghai)
### Current Progress
- `BRIDGE-TASK-QUEUE-1` 已完成：Codex bridge 默认同时轮询 `/api/tasks?target_member_id=<member_id>&status=queued`，按任务 `id` 从小到大认领属于自己的 queued task。
- 新增任务 prompt 构造路径：把 `created_by / task id / title / content / workdir` 注入 Codex CLI stdin，区别于原有消息触发 prompt。
- 新增 `handle_queued_task(...)`：认领任务、运行 Codex CLI、格式化输出、向任务创建者发送直接文本结果消息，并通过 `/api/tasks/{id}/complete` 写入 `succeeded / failed`、`result_message_id` 与 `last_error`。
- 新增任务队列后台 worker：与消息处理共用 `run_lock`，保证单个 bridge 实例不会并发启动多个 Codex CLI 进程。
- CLI 新增 `--task-poll-interval` 与 `--disable-task-queue`；默认开启任务队列轮询，保留旧的消息触发模式。
- `docs/spec/MODULE_bridges.md` 已同步任务队列行为、CLI 开关与验收点。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；本轮是 bridge/任务协议相关切片，按协议完成 1 个切片后暂停汇总并提交。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测；本切片未改前端，因此未做 Browser 真实页面验证。
### Next Plan
1. 提交本次 `BRIDGE-TASK-QUEUE-1` 切片。
2. 后续如需推送，当前分支会包含上一条 `SSE-BACKFILL-1` 本地提交与本次 bridge 提交。
3. 下一候选切片：Group 重命名/删除 UI，或文档编辑锁协议。
4. Browser runtime 恢复后，补一次 Web UI SSE 真实浏览器烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile bridges\codex_bridge.py tests\test_codex_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge` passed，8 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_codex_bridge tests.test_tasks tests.test_talk_client` passed，25 tests。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe -m unittest` passed，90 tests。
### Changed Files
- `bridges/codex_bridge.py`
- `tests/test_codex_bridge.py`
- `docs/spec/MODULE_bridges.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-20 10:38 (Asia/Shanghai)
### Current Progress
- `SSE-BACKFILL-1` 已完成：`GET /api/events` 已支持 `Last-Event-ID` header 与 `last_event_id` query 参数。
- 连接建立时会先完成 SSE 实时订阅并发送在线快照，再按当前成员可见性补发 `message.id > last_event_id` 的历史消息快照，降低重连窗口中的事件丢失风险。
- 补发查询覆盖全局可见消息与当前成员所在 Group 的 Hall 消息，并会过滤对当前成员不可见的消息。
- 撤回消息按当前 `MessageOut` 快照语义补发：`revoked=true`，正文、附言和文件快照字段保持隐藏。
- 若同一消息同时出现在补发结果和实时队列中，服务端会按 SSE `id:` 去重后再输出。
- `docs/spec/MODULE_websocket.md` 已同步接口契约、当前实现与验收标准。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；本轮按协议切片规则完成 1 个切片后暂停汇总。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测；本切片未改前端，因此未做 Browser 真实页面验证。
### Next Plan
1. 提交本次 `SSE-BACKFILL-1` 切片。
2. 下一候选切片：Group 重命名/删除 UI，或 Codex bridge task-queue integration。
3. Browser runtime 恢复后，补一次 Web UI SSE 真实浏览器烟测。
### Verification
- `.venv\Scripts\python.exe -m py_compile server\main.py tests\test_sse.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，6 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_sse tests.test_websocket tests.test_messages` passed，39 tests。
- `.venv\Scripts\python.exe -m unittest` passed，88 tests。
- `git diff --check` passed，仅有换行提示。
### Changed Files
- `server/main.py`
- `tests/test_sse.py`
- `docs/spec/MODULE_websocket.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 20:24 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-BATCH-GUARD-1` 已完成：已在全局 `project-framework` skill 与 TALK `AGENTS.md` 中加入连续开发批次刹车规则。
- 决策 Agent 每次恢复默认最多连续推进 2 个明确切片；若都是小型文档/配置切片，可最多 3 个。
- 涉及前端真实交互、数据库/协议、部署/权限或跨模块协作时，默认 1 个切片后暂停汇总。
- 决策 Agent 连续工作约 60-90 分钟后，不应开启新切片，应先完成当前切片的必要验证、汇总进度、提交/推送，并输出下一步建议。
- 软停止信号仅保留两项：后续任务需要重新读取另一个模块文档，或 Agent 明显开始依赖“回忆前文”才能继续判断。
- 若环境提供 5 小时额度或 token 用量占比，仍保留达到或超过 90% 时必须完成当前切片收尾的规则；若环境未暴露精确占比，不臆测百分比。
### Open Questions / Pending Confirmation
- 当前环境仍未暴露精确 token/5 小时额度占比；后续继续按批次、工作时长、上下文接近上限与两项软停止信号控制连续开发。
- Browser runtime 初始化问题仍待从 Codex Desktop / Browser 后端侧恢复后补测。
### Next Plan
1. 提交并推送全局 `project-framework` skill 更新。
2. 提交并推送 TALK 本地规则与进度更新。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed。
- `git diff --check` in `C:\Users\Administrator\.codex\skills\project-framework` passed，仅有换行提示。
- `git diff --check` in TALK passed，仅有换行提示。
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:26 (Asia/Shanghai)
### Current Progress
- `WORKFLOW-GUARD-1` 已完成：已在 `AGENTS.md` 中补充 Browser 验证失败诊断规则与 token/额度占比收尾规则。
- Browser 失败诊断确认：`node_repl` 可执行，`browser-client.mjs` 可 import，但 `setupAtlasRuntime(...)` 阻塞超时，失败点在 Codex Browser 运行时初始化/后端连接，不是 TALK 页面代码。
- 规则明确：若 `node_repl` 与 import 正常但 Browser runtime 初始化阻塞，应记录限制，改用静态检查、后端测试、必要的临时隔离服务验证，并提示项目管理者从 Codex Desktop / Browser 后端侧恢复后补测。
- token/额度规则明确：若运行环境提供 5 小时额度或 token 用量占比，达到或超过 90% 时不得开启新切片，必须先完成当前切片收尾、汇总进度、提交/推送并输出 `继续项目`。
- 当前工具上下文未暴露 5 小时额度或 token 用量占比，Agent 不应臆测具体百分比，继续沿用上下文 80%-90% 接近上限规则。
### Open Questions / Pending Confirmation
- 需要项目管理者在 Codex Desktop 侧重启/恢复 in-app Browser 或检查 Browser/Chrome 后端后，再补 Web UI 真实浏览器验证。
- 若未来 Codex 暴露精确 token/额度占比，可进一步把该信号纳入自动化提醒或进度模板。
### Next Plan
1. 提交并推送本次流程规则补充切片。
2. Browser 恢复可用后，补 Web UI SSE 兜底真实页面烟测。
3. 下一功能候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
### Verification
- `node_repl` 最小执行 `nodeRepl.write("node_repl ok")` passed。
- `browser-client.mjs` import passed，导出 `setupAtlasRuntime`。
- `setupAtlasRuntime(...)` 30 秒超时；使用 `Promise.race` 的 5 秒超时探针也未返回，说明初始化过程阻塞。
- `git diff --check` 待提交前执行。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-16 19:04 (Asia/Shanghai)
### Current Progress
- `WEB-SSE-UI-1` 已完成：Web UI 已接入 `GET /api/events?token=...` SSE 事件流作为实时兜底。
- 浏览器优先使用 WebSocket；如果当前浏览器不支持 WebSocket，或 WebSocket 断开/报错，会打开 SSE 并显示 `SSE 已连接 / SSE 兜底中 / SSE 重连中 · 轮询兜底` 状态。
- WebSocket 恢复后会主动关闭 SSE，避免同一浏览器同时占用两条实时通道。
- SSE 与 WS 共用前端实时事件处理逻辑，统一处理 `message / revoke / presence`，`ping` 事件只用于保持连接。
- HTTP 轮询仍保留为断线与事件缺口补漏通道，不承担在线成员状态。
- `docs/spec/MODULE_webui.md` 已同步接口依赖、当前实现、验收标准和本切片 addendum。
### Open Questions / Pending Confirmation
- Codex in-app Browser 插件本轮连接两次超时，未完成真实浏览器前端烟测；临时隔离服务已关闭并清理。
- SSE `Last-Event-ID` replay/backfill 尚未实现；客户端仍需用历史接口和 HTTP 轮询补漏。
### Next Plan
1. 提交并推送本次 Web UI SSE 兜底切片。
2. 下一候选切片：SSE `Last-Event-ID` replay/backfill，或 Group 重命名/删除 UI。
3. 如浏览器插件恢复可用，补一轮真实 Web UI SSE 兜底烟测。
### Verification
- `node --check web\app.js` passed。
- `git diff --check` passed，仅有换行提示。
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed，3 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed，10 tests。
- `.venv\Scripts\python.exe -m unittest` passed，85 tests。
- Browser 插件连接两次超时；临时隔离服务已关闭并清理。
### Changed Files
- `web/app.js`
- `web/index.html`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:25 (Asia/Shanghai)
### Current Progress
- `DOC-LANG-1` 已完成：已在 `AGENTS.md` 中加入 TALK 文档语言约定。
- 项目文档中的描述性内容应尽量使用中文。
- 代码标识、API 路径、命令、配置键、协议名、库名、错误码、commit hash 等技术字面量可以保留原始写法。
- 该规则覆盖需求说明、设计说明、进度记录、验收说明、变更摘要和面向人阅读的解释文字。
### Open Questions / Pending Confirmation
- 本规则切片没有新增待确认问题。
### Next Plan
1. 提交并推送本次文档规则切片。
2. 明天用 `继续项目` 恢复。
### Verification
- 本次文档规则更新前，`git status --short` 为空。
- `git diff --check` 已通过，仅有换行提示。
### Changed Files
- `AGENTS.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`
## 2026-05-15 18:21 (Asia/Shanghai)
### Current Progress
- End-of-day TALK summary completed.
- Confirmed TALK worktree was clean before this summary update.
- Confirmed today's implementation commit `bfb28a3 feat: add group sdk ui and sse events` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed today's workflow/documentation commit `d9a10d5 更新 Agent 协作规则与进度拆分` exists locally and had been pushed earlier to GitHub branch `codex/local-lab-codex-bridge`.
- Confirmed standalone `project-framework` skill repository was updated and pushed at `7756b08 更新项目连续性管理规则`.
- Current recovery instruction for the next session: say `继续项目`.
### Open Questions / Pending Confirmation
- Web UI SSE integration is still the recommended next implementation slice.
- Remaining pending areas: SSE replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, Codex bridge task-queue integration, and environmental deployment/onboarding verification.
### Next Plan
1. Resume tomorrow with `继续项目`.
2. Prefer Web UI SSE fallback/integration unless project priority changes.
### Verification
- `git status --short` was clean before this summary update.
- `git log -3 --oneline` showed `d9a10d5`, `bfb28a3`, and `99578f3`.
- Prior verification for the completed code slice: full `.venv\Scripts\python.exe -m unittest` passed with `85` tests; `node --check web\app.js` passed; `git diff --check` passed with line-ending warnings only.
### Changed Files
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 18:02 (Asia/Shanghai)
### Current Progress
- `PROJECT-FRAMEWORK-RULES-1` completed: updated the local `project-framework` skill with the new project-management workflow rules.
- Added role authority rules: `AGENTS.md` is the source of truth; Codex is currently the decision Agent and Claude is currently the execution Agent for TALK.
- Added development cadence rules: decision Agents may continue through multiple clear slices; execution Agents must complete one slice, summarize progress, then wait for confirmation.
- Added required per-slice summary behavior for all Agent roles, plus local git/GitHub submission expectations and Chinese GitHub-facing descriptions.
- Added context handoff/clear flow: summarize, persist, verify, and submit before clearing context or opening a new window; otherwise output `继续项目`.
- Added milestone acceptance gate: pause at independently usable milestones and provide a Chinese acceptance package before continuing.
- Split progress management so `docs/PROGRESS.md` stays short and completed slice history lives in `docs/PROGRESS_HISTORY.md`.
- Synced TALK docs in `AGENTS.md`, `docs/PROJECT_BRIEF.md`, and this progress set.
### Open Questions / Pending Confirmation
- GitHub push/PR behavior is conditional on available remote credentials and should be handled by the active Agent at submission time.
### Next Plan
1. Commit this workflow/documentation slice after verification.
2. Resume implementation from the current candidate list when requested.
### Verification
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\project-framework` passed.
- `git diff --check` passed with line-ending warnings only.
### Changed Files
- `C:\Users\Administrator\.codex\skills\project-framework\SKILL.md`
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## 2026-05-15 历史迁移（来自 PROGRESS.md）

### 2026-05-15 11:04 (Asia/Shanghai)
#### Current Progress
- `SSE-1` completed: added read-only `GET /api/events?token=...` as a Server-Sent Events stream for clients that cannot or should not hold a WebSocket.
- SSE authentication uses the existing API key member resolution path; invalid tokens return `401`.
- The stream emits `presence`, `message`, `revoke`, and idle `ping` events; `message` and `revoke` include SSE `id:` set to the message id.
- `server/ws_hub.py` now fans out realtime updates to both WebSocket connections and per-member SSE queues, drops the oldest queued SSE event when a member queue is full, and counts online members across the WebSocket/SSE union.
- Added live streaming tests for invalid token rejection, presence/message delivery, and revoke delivery.
- Synced `docs/spec/MODULE_websocket.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Web UI has not integrated the new SSE stream yet; this slice only provides the backend event contract.
- SSE `Last-Event-ID` replay/backfill is not implemented; clients should still use message history APIs after reconnect when they need gap recovery.
#### Next Plan
- Continue with one of: Web UI SSE fallback/integration, SSE `Last-Event-ID` replay/backfill, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_sse` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_websocket` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `85` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `server/main.py`
- `server/ws_hub.py`
- `tests/test_sse.py`
- `tests/test_support.py`
- `docs/spec/MODULE_websocket.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:52 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-MEMBERS-1` completed: active Group Hall now exposes a members panel from the top room strip.
- Human users can add members not yet in the Group, update member roles among `owner / moderator / member`, and remove other members.
- Agent users retain a read-only member list in the UI; server-side permission remains authoritative.
- Successful member changes replace the active Group snapshot and immediately refresh room metadata, scoped presence, and `@` autocomplete.
- Static asset cache-busting updated to `20260515-group-members`.
- Synced `docs/spec/MODULE_webui.md`, `docs/spec/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group rename/delete UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- Chrome headless smoke test against an isolated temporary TALK server verified login, Group creation, members panel open, member add, role update, member removal, and no horizontal overflow at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-15 10:37 (Asia/Shanghai)
#### Current Progress
- `SDK-GROUP-1` completed: async SDK now exposes `create_group`, `list_groups`, `get_group`, `upsert_group_member`, and `remove_group_member`.
- Sync SDK parity added for the same Group helpers; sync `reply()` was also exposed for parity with the async client.
- Message helpers now support Hall scope: `send_text`, `send_file`, `reply`, and `fetch_history` can carry `group_id`.
- Added live SDK coverage that creates a Group, updates/removes a member, sends a Hall message, reads Hall history as an Agent, and verifies the Hall message does not leak into legacy/global history.
- Synced `docs/spec/SDK.md`, `docs/spec/MODULE_groups.md`, `docs/PROJECT_BRIEF.md`, and this progress file.
#### Open Questions / Pending Confirmation
- No new open questions from this slice.
#### Next Plan
- Choose the next slice from: SSE stream event contract, Group member management UI, document-edit lock API, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client` passed with `10` tests.
- Full `.venv\Scripts\python.exe -m unittest` passed with `82` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_talk_client.py`
- `docs/spec/SDK.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:33 (Asia/Shanghai)
#### Current Progress
- `WEB-GROUP-1` completed: Web UI now exposes a real Group/Hall room strip above the workspace tools.
- Added global timeline / Group Hall switching, `GET /api/groups` loading, active Group persistence per user, and disabled entries for Groups the current user cannot enter.
- Added a lightweight new Group panel with name, optional ID, optional description, and initial member checkboxes; creation succeeds through `POST /api/groups` and automatically enters the new Hall.
- Hall scope now flows through the browser: history and polling include `group_id`, text/file send payloads include `group_id`, WebSocket events are appended only when they belong to the active room, and switching rooms clears reply state.
- Hall UX now scopes online members and `@` autocomplete to the current Group members and uses a placeholder that states Hall mentions are reminders rather than visibility restrictions.
- Synced `docs/PROJECT_BRIEF.md`, `docs/spec/MODULE_webui.md`, `docs/spec/MODULE_groups.md`, and this progress file.
#### Open Questions / Pending Confirmation
- Group member management after creation, Group rename/delete, unread/attention state, SDK helpers, SSE stream integration, and multi-Agent discussion protocol remain future slices.
#### Next Plan
- Commit this Web UI Group/Hall follow-up if accepted.
- Then continue with one of: SDK group helpers, Group member management UI, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- Chrome headless smoke test against an isolated temporary TALK server/database/storage verified login, Group creation with `agent:codex`, Hall message send, Hall-specific placeholder, and that switching back to global hides the Hall message.
- `.venv\Scripts\python.exe -m unittest tests.test_groups tests.test_messages` passed with `26` tests.
- `git diff --check` passed with line-ending warnings only.
- Full `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_webui.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 16:03 (Asia/Shanghai)
#### Current Progress
- Project role boundary updated: Codex is now authorized as a decision Agent and can maintain relevant project/module/progress/decision docs directly.
- Group/Hall docs synced after `GROUP-1 / HALL-1`: added `docs/spec/MODULE_groups.md`.
- Updated `docs/PROJECT_BRIEF.md` with `groups`, `group_members`, `messages.group_id`, `server/routes/groups.py`, the module index entry, and the 2026-05-14 Group/Hall addendum.
#### Open Questions / Pending Confirmation
- None for documentation sync.
#### Next Plan
- Commit the current Web UI + Group/Hall backend + documentation set when accepted.
- Then choose the next slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `AGENTS.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_groups.md`
- `docs/PROGRESS.md`

### 2026-05-14 15:54 (Asia/Shanghai)
#### Current Progress
- `GROUP-1 / HALL-1` backend first slice completed from the confirmed contract.
- Added `groups` and `group_members` tables, `messages.group_id`, startup migration/index creation, `/api/groups` creation/list/detail/member add/update/remove APIs, and group-scoped message send/history behavior.
- Group Hall visibility now treats `to_ids` as mention/attention inside a Group: all Group members can read the Hall timeline, while non-members are rejected and old unscoped message history remains legacy/global only.
#### Open Questions / Pending Confirmation
- Documentation sync for `docs/PROJECT_BRIEF.md` and a new/updated Group/Hall module doc still needs explicit approval.
- Web UI Group/Hall navigation and SDK helpers are not implemented yet.
#### Next Plan
- If approved, sync Group/Hall docs and commit the current work.
- Otherwise continue with one follow-up slice: Web UI Group/Hall navigation, SDK group helpers, SSE stream events, document-edit locks, schedule API, or Codex bridge task-queue integration.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_groups` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_messages` passed with `23` tests.
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `81` tests.
#### Changed Files
- `server/models.py`
- `server/db.py`
- `server/main.py`
- `server/routes/groups.py`
- `server/routes/messages.py`
- `server/ws_hub.py`
- `tests/test_groups.py`
- `tests/test_messages.py`
- `tests/test_support.py`
- `docs/PROGRESS.md`

### 2026-05-14 15:15 (Asia/Shanghai)
#### Current Progress
- Resumed from `WEB-VISUAL-2` and reviewed the current Web UI diff instead of starting a new backend slice.
- Verified the real login page and authenticated chat page with Chrome headless at desktop and 500px widths.
- Fixed a CSS cascade bug where `.drop-hint` overrode Tailwind `.hidden`, causing the drag/drop overlay to stay visible over the composer when no file was being dragged.
#### Open Questions / Pending Confirmation
- `docs/USER.md` remains an untracked local credential note; it should not be committed as-is.
#### Next Plan
- Decide how to handle `docs/USER.md`, then commit the accepted Web UI visual changes.
- After Web UI is committed, choose the next backend/product slice: schedule API, Group/Hall, SSE, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- Chrome headless screenshots verified real login and authenticated chat pages; `#drop-hint` computed as `display: none` at 1440px and 500px.
#### Changed Files
- `web/style.css`
- `docs/PROGRESS.md`

### 2026-05-14 11:35 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-2` completed from the approved `image_gen` visual direction: the chat page now uses a `header + workspace-tools + messages + composer` structure.
- Online members and history/search controls are grouped into one workspace tools panel; the message timeline and composer now read as a single chat work area.
- The left channel/conversation area shown in the visual mockup remains deferred until the Group/Hall model exists, so the current page does not expose fake navigation.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page acceptance still depends on manual review in the user's browser session or a dedicated non-private test account.
#### Next Plan
- If the layout is accepted, commit the Web UI visual changes; then return to backend model work, likely Group/Hall or SSE, so future navigation/sidebar UI has real data behind it.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/` returned `200`.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview at desktop and 500px widths.
#### Changed Files
- `web/index.html`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 11:10 (Asia/Shanghai)
#### Current Progress
- `WEB-VISUAL-1` completed: login/setup now uses a unified dark card treatment with Chinese copy, branded mark, clearer fields, and primary/secondary button hierarchy.
- Chat workspace styling was refreshed across header, presence strip, search toolbar, timeline background, message bubbles, reply/file cards, and bottom composer.
- Added responsive safeguards for narrow screens: constrained auth card width, wrapping toolbar controls, composer min-width fixes, and stronger long-message wrapping.
#### Open Questions / Pending Confirmation
- Real authenticated chat-page visual acceptance still depends on manual review or a provided non-private test login key; Codex in-app browser automation continues to time out when connecting.
#### Next Plan
- Review the visual result in a normal browser session; if accepted, commit and push `WEB-VISUAL-1`.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- Chrome headless screenshot checks completed for the real login page and a temporary chat-shell preview using the current served `style.css`.
- Codex in-app browser automation retry still timed out while connecting.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:55 (Asia/Shanghai)
#### Current Progress
- Re-ran full backend regression after the Web UI polish changes; all `74` unit tests passed.
- Confirmed the local TALK service health endpoint still returns `status=ok`.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on browser/manual review; automated in-app browser control was previously timing out in this environment.
#### Next Plan
- Commit and push the Web UI polish changes if the current UI review scope is accepted.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
- `git diff --check` passed with line-ending warnings only.
- `GET http://127.0.0.1:8000/healthz` returned `status=ok`.
- In-app browser automation retry against `http://127.0.0.1:8000/` timed out while connecting.
#### Changed Files
- `docs/PROGRESS.md`

### 2026-05-14 10:49 (Asia/Shanghai)
#### Current Progress
- `CHAT-UI-1` completed from browser review comments: search toolbar, composer controls, drag/drop hint, logout, remove-file, cancel-reply, and send/file labels are now Chinese.
- Search toolbar now separates primary search from secondary clear/load-more actions; composer now has a defined container and distinct file/input/send controls.
- Empty message timeline now shows a Chinese empty-state explanation instead of a visually unexplained blank area.
#### Open Questions / Pending Confirmation
- Visual acceptance still depends on manual refresh because Codex in-app browser automation is still timing out when connecting to the browser runtime.
#### Next Plan
- If the chat UI review is accepted, commit and push the Web UI polish changes.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:15 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` follow-up completed: added cache-busting query strings for `/style.css` and `/app.js`, placed the create-admin button contrast styles directly in HTML classes, and replaced raw Clipboard API permission errors with Chinese copy-fallback guidance.
- If browser copy permission is denied, the setup key field is focused and selected so the user can press `Ctrl+C` manually.
#### Open Questions / Pending Confirmation
- Whether to replace the current API-key-first login model with a human password flow is a product/auth decision. Recommended direction is dual-mode auth: human password login with hashed password plus generated API keys for Agent/SDK use.
#### Next Plan
- If approved, design `AUTH-2`: password-based human login without breaking existing `X-API-Key` Agent authentication.
#### Verification
- `node --check web\app.js` passed.
- `git diff --check` passed with line-ending warnings only.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-14 10:01 (Asia/Shanghai)
#### Current Progress
- `SETUP-UX-2` completed from browser diff comments: added a visible `管理员 ID` format hint, changed `显示名称` to `昵称`, added client-side `human:*` validation, and restyled `创建管理员` as a compact bordered primary button.
- Synced `docs/spec/MODULE_webui.md` to reflect the updated first-admin setup labels and ID-format hint.
#### Open Questions / Pending Confirmation
- In-app browser automation currently times out while connecting to the browser runtime, so the page needs a manual refresh or later browser recheck for visual confirmation.
#### Next Plan
- Continue with the next local-lab slice after UI review is accepted: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
#### Verification
- `node --check web\app.js` passed.
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed with `3` tests.
- `GET http://127.0.0.1:8000/` returned `200`.
#### Changed Files
- `web/index.html`
- `web/app.js`
- `web/style.css`
- `docs/spec/MODULE_webui.md`
- `docs/PROGRESS.md`

### 2026-05-13 16:07 (Asia/Shanghai)
#### Current Progress
- `TASK-1` completed: added `AgentTask` / `AgentTaskCreate` / `AgentTaskClaim` / `AgentTaskComplete` / `AgentTaskOut`, `/api/tasks`, database indexes, async SDK helpers, sync SDK wrappers, and documentation.
- Task API first slice supports creating queued tasks for existing `agent:*` members, listing visible tasks, Agent-only claim, and Agent-only completion as `succeeded` / `failed` / `canceled`.
- Task claim and completion now update linked `AgentInstance`: claim sets `busy` and `current_task_id`; success/cancel returns to `idle`; failure sets `error` and `last_error`.
- Project rule updated in `AGENTS.md`: development execution Agents may directly update `docs/PROGRESS.md` after actual code, test, or documentation work.
- Documentation synced across project brief, SDK, local-lab design, instances module, and new tasks module.
#### Open Questions / Pending Confirmation
- Schedule API is still not implemented: delayed / recurring trigger shape remains open.
- Retry, task timeout recovery, stale `running` cleanup, requeue/cancel UI, and Codex bridge task-queue consumption remain future work.
#### Next Plan
- Choose the next local-lab slice: schedule API, Group/Hall room model, SSE stream contract, document-edit lock API, or Codex bridge task-queue integration.
- If continuing scheduler work, define whether schedules create one-off tasks at trigger time and how failed scheduled tasks should be retried or surfaced.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_tasks` passed with `7` tests.
- `.venv\Scripts\python.exe -m unittest tests.test_talk_client.TalkClientTests.test_task_helpers` passed.
- `.venv\Scripts\python.exe -m unittest` passed with `74` tests.
#### Changed Files
- `AGENTS.md`
- `server/models.py`
- `server/routes/tasks.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `TALK/client/talk_client_sync.py`
- `tests/test_tasks.py`
- `tests/test_talk_client.py`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/MODULE_instances.md`
- `docs/spec/MODULE_tasks.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/spec/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:47 (Asia/Shanghai)
#### Current Progress
- `INSTANCE-1` completed: added `AgentInstance` / `AgentInstanceUpdate` / `AgentInstanceOut`, `/api/instances`, database indexes, SDK helpers, and module documentation.
- Codex bridge now reports its runtime instance state with a stable optional `--instance-id`; task handling updates status to `busy`, success returns to `idle`, failures become `error`, and shutdown reports `offline`.
- Added coverage for instance API permissions, ownership protection, filters, invalid status validation, and SDK helpers.
#### Open Questions / Pending Confirmation
- Task and schedule API semantics are still not implemented: task table shape, retry behavior, process ownership, and scheduler/bridge responsibility split remain open.
- Group / Hall / SSE / document-lock implementation details remain pending after this instance-status foundation.
#### Next Plan
- Choose the next local-lab slice: scheduler task API, Group/Hall room model, SSE stream contract, or document-edit lock API.
- When scheduler work starts, decide whether TALK launches bridge processes or only routes tasks to already-running instances.
#### Verification
- `.venv\Scripts\python.exe -m unittest tests.test_instances tests.test_talk_client tests.test_codex_bridge` passed with `19` tests.
- `.venv\Scripts\python.exe -m unittest` passed with `66` tests.
- Isolated bridge instance smoke passed: `idle -> busy -> idle -> offline`, reply content `TALK_BRIDGE_INSTANCE_SMOKE_OK`.
#### Changed Files
- `server/models.py`
- `server/routes/instances.py`
- `server/main.py`
- `server/db.py`
- `TALK/client/talk_client.py`
- `bridges/codex_bridge.py`
- `tests/test_instances.py`
- `tests/test_talk_client.py`
- `docs/spec/MODULE_instances.md`
- `docs/spec/MODULE_bridges.md`
- `docs/spec/LOCAL_LAB_DESIGN.md`
- `docs/PROJECT_BRIEF.md`
- `docs/spec/SDK.md`
- `docs/PROGRESS.md`

### 2026-05-13 15:24 (Asia/Shanghai)
#### Current Progress
- Created an ignored local `.venv` from `requirements.txt`; dependency imports resolved consistently there (`pydantic 2.13.4`, `pydantic-core 2.46.4`, `fastapi 0.136.1`, `websockets 15.0.1`).
- Full regression passed: `.venv\Scripts\python.exe -m unittest` ran `60` tests successfully.
- Real Codex bridge smoke test passed with isolated temporary TALK server/database/storage: `human:smoke` sent `@agent:codex`, the bridge invoked real `codex exec --sandbox read-only`, and the reply used `reply_to` with content `TALK_BRIDGE_SMOKE_OK`.
#### Open Questions / Pending Confirmation
- Codex bridge remains MVP-level and still needs instance status, streaming, file/material handling, and document-lock integration.
- The `pi` framework path for DeepSeek / Kimi still needs local verification.
#### Next Plan
- Choose the next implementation slice: bridge instance status, Group/Hall model, SSE streaming contract, or document-edit lock API.
- Continue the local-lab protocol design before broad service-model changes.

### 2026-05-13 15:10 (Asia/Shanghai)
#### Current Progress
- Added `docs/spec/LOCAL_LAB_DESIGN.md` as the thin local-lab design note.
- Added `bridges/codex_bridge.py` as the Codex bridge MVP: direct text message in, configurable `codex exec` invocation, `reply_to` answer out.
- Added `docs/spec/MODULE_bridges.md` and updated `docs/PROJECT_BRIEF.md` to register the new bridge module.
- Added `tests/test_codex_bridge.py` covering bridge routing, prompt construction, reply formatting, and subprocess stdin piping.
#### Open Questions / Pending Confirmation
- Real TALK server smoke test for Codex bridge remains pending.
- Full test suite is blocked by the local `.codex_pydeps` pydantic / pydantic-core mismatch.
#### Next Plan
- Clean or rebuild the Python dependency environment, then run full tests.
- Start TALK locally, run the Codex bridge, and verify one `@agent:codex` browser-to-bridge-to-reply loop.
- After the smoke test, continue with Group / Hall / SSE / instance-scheduler design and implementation.

### 2026-05-12 17:36 (Asia/Shanghai)
#### Current Progress
- Product decisions confirmed: DeepSeek / Kimi will use the locally installed `pi` framework; TALK should add Groups, Hall shared timeline mode, SSE streaming, and instance/scheduling API layers.
- A document editing coordination protocol is now required so multiple Agents do not edit the same document at the same time.
- Existing communication specs were checked. Current TALK supports member identity, API-key auth, server-side leading-mention routing, broadcast/direct/group-style `to_ids`, REST polling, WebSocket events, file exchange, replies, and SDK callbacks, but not a formal discussion protocol or document lock protocol.
- Temporary role decision: until the next progress summary, Codex may act as both decision Agent and execution Agent because the dedicated decision Agent is unavailable.
#### Open Questions / Pending Confirmation
- Document editing coordination still needs exact rules for lock scope, timeout, stale-lock recovery, conflict handling, and UI/API visibility.
- The local `pi` framework needs a quick workstation-level verification before bridge implementation.
#### Next Plan
- Write the next-phase local-lab design note covering bridge layout, `pi` integration, Groups, Hall, SSE, instance/scheduler APIs, and document-edit coordination.
- Define the first moderator-led multi-Agent discussion protocol before implementation.
- Implement the minimum local-lab path after the protocol and data model changes are stable.

### 2026-04-24 23:11 (Asia/Shanghai)
#### Current Progress
- `DOC-2` completed: fixed the remaining mojibake deployment section in `CLAUDE.md`, added explicit UTF-8 write rules plus SDK import-path notes to `AGENTS.md` / `CLAUDE.md`, and added `tests/test_encoding.py` as an encoding regression guard.
- Full regression still passes with `54` tests, including `3` new encoding-guard cases.
- The intended usage model is now explicit: TALK is a local home-LAN multi-Agent lab used on demand while the local computer is on, not a 24/7 permanently running service.
- The planned backend mix is now explicit: `Claude Code` / `Codex` through local CLI bridges, and `Kimi` / `DeepSeek` through API bridges.
- The next product direction is now explicit: moderator-led AI discussion with automatic transcript retention and support for passing shared documents/materials during the discussion.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The discussion phase still needs a concrete protocol for moderator behavior, round limits, material-sharing rules, and summary output.
#### Next Plan
- Write the next-phase design note for local experimental mode and one-command startup.
- Define a unified bridge contract for mixed CLI/API Agent backends.
- Define the first moderator-led discussion protocol with transcript retention, bounded rounds, and material passing.
- Implement the minimum local-lab path first, then return to lower-priority deployment validation tasks.

### 2026-04-24 22:01 (Asia/Shanghai)
#### Current Progress
- `DOC-1` completed: split onboarding into `docs/guides/QUICKSTART_USER.md` and `docs/guides/QUICKSTART_AGENT.md`, and reduced `docs/guides/QUICKSTART.md` to a short index page.
- `QUICKSTART_USER` now follows a family-user path with Docker Desktop, explicit browser verification, `config.toml` before/after examples, LAN IP lookup, and ordered troubleshooting.
- `QUICKSTART_AGENT` now follows a Python bare-metal + SDK path with PowerShell/bash command pairs, real example repo URLs, and a full runnable Agent sample.
- `docs/guides/DEPLOY.md` now includes prerequisites for Docker Compose, Linux `systemd`, and bare metal deployment.
- `docs/spec/SDK.md` async examples now all include `asyncio.run(main())`, and `SETUP-1` now supports browser-side key generation, reveal/hide, and one-click copy in the first-admin UI.
- Related docs were synced after implementation, and full regression still passes with `51` unit tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART_USER.md` has not yet been run end-to-end by a first-time non-project user, so there may still be hidden onboarding assumptions.
- The task card asks for a second clean-session newcomer dry run and readability feedback; that external acceptance has not been performed yet in this environment.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, generated key, automatic sign-in, and second-open login behavior match the task card.
- Run one clean-session newcomer walkthrough against `docs/guides/QUICKSTART_USER.md`, collect friction points, and trim any remaining expert assumptions.

### 2026-04-24 19:25 (Asia/Shanghai)
#### Current Progress
- `SETUP-1` completed: added unauthenticated `GET /api/setup/status`, CLI bootstrap script `scripts/create_admin.py`, Web UI first-run admin creation flow, and setup coverage in `tests/test_setup.py`.
- `QUICKSTART` and `DEPLOY` now document first-run bootstrap via the Web UI and `python scripts/create_admin.py`, including the Docker path `docker compose exec talk python scripts/create_admin.py`.
- The old onboarding blocker is removed at the code level: first human account creation no longer requires opening `/docs` and manually calling `POST /api/members`.
- Regression coverage expanded again; full `python -m unittest` is now green with `51` tests, including `3` new setup-specific cases.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- The new first-run setup flow has test coverage, but a real browser smoke test for “empty DB -> create admin -> auto login -> reopen -> normal login form” is still pending.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Run one real browser smoke test for `SETUP-1` on a fresh DB and confirm the first-run form, automatic sign-in, and second-open login behavior match the task card.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:39 (Asia/Shanghai)
#### Current Progress
- `SDK-1` completed: added `TALK/client/` with async `TalkClient`, sync `TalkClientSync`, HTTP exception mapping, WebSocket-first event flow, reconnect plus HTTP polling fallback, message dedupe, and SDK docs/demo.
- `MSG-4` completed: added first-level message reply support across database, REST, WebSocket, Web UI, and SDK; reply summaries now travel with history and live events.
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `deploy/talk.service`, `README.md`, `docs/guides/QUICKSTART.md`, and `docs/guides/DEPLOY.md` for Docker, systemd, and bare-metal deployment paths.
- `SEC-1` completed: `GET /api/messages` now enforces visibility in SQL, aligns with WebSocket delivery semantics, and treats `to` as a narrowing filter rather than an access-control boundary.
- Regression coverage expanded across SDK and message flows; full `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 20:38 (Asia/Shanghai)
#### Current Progress
- `SEC-1` completed: `GET /api/messages` now enforces message visibility in SQL and matches WebSocket delivery semantics instead of trusting the caller's `to` filter.
- `to=<member_id>` is now only a narrowing filter on the caller's visible set; `to=<other_member>` returns a safe pair view without exposing third-party private messages.
- Added regression coverage in `tests/test_messages.py` for third-party private message isolation, `to` filter escape attempts, broadcast visibility, pair-view filtering, and search visibility boundaries.
- Added startup indexes for `messages.from_id` and `messages.to_ids`, and updated `docs/spec/MODULE_messages.md`, `docs/PROJECT_BRIEF.md`, and `docs/spec/SDK.md` to document the new server-enforced visibility contract.
- Full regression check passed: `python -m unittest` is green with `48` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup are still unverified.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- First human account creation still relies on `/docs` plus `POST /api/members`; there is still no dedicated first-run bootstrap flow.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Decide whether to turn first human account creation into a dedicated bootstrap flow, or explicitly accept `/docs` as the administrator-only setup path for now.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:59 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/guides/QUICKSTART.md` for first install/login/use, and `docs/guides/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
- `deploy/talk.service` and the Linux deployment path are documented but not yet validated on a clean Linux host.
- `docs/guides/QUICKSTART.md` has not yet been run end-to-end by a first-time non-project user, so there may still be onboarding friction.
- Outside `DEPLOY-1`, one known product-side gap remains: `GET /api/messages` history visibility still relies on the caller using the expected `to=<member_id>` view and is not yet fully tightened to WebSocket-level visibility semantics.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:57 (Asia/Shanghai)
#### Current Progress
- `DEPLOY-1` completed: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `deploy/talk.service` to support Docker and systemd deployment paths.
- Added human-facing deployment docs: `README.md` as the root entry, `docs/guides/QUICKSTART.md` for first install/login/use, and `docs/guides/DEPLOY.md` for Docker, systemd, bare-metal, reverse proxy, backup, and restore workflows.
- `CLAUDE.md` now points operators to the new deployment entry docs and templates.
- Docker docs now include writable path bootstrap steps for a clean machine: `storage/`, `logs/`, `backups/`, and `talk.db`.
- Regression check passed: `python -m unittest` remains green with `43` tests.
#### Open Questions / Pending Confirmation
- Docker was not available in the current workstation environment, so `docker compose config` and real container startup were not verified here.
#### Next Plan
- Run one real Docker smoke test on a machine with Docker: `docker compose up -d --build`, open Web UI, create one account, send one message, upload one file, then restart and confirm persistence.
- Run one real Linux host smoke test for `deploy/talk.service` following `docs/guides/DEPLOY.md`.
- Collect first-run feedback from a non-project user against `docs/guides/QUICKSTART.md` and remove any remaining setup friction.

### 2026-04-23 19:48 (Asia/Shanghai)
#### Current Progress
- `MSG-4` completed: backend now supports first-level message replies via `messages.reply_to`, server-side validation, REST history reply summaries, and WebSocket payload parity.
- Web UI now supports reply composition, inline reply strips, jump-to-origin highlight, revoked-origin placeholder handling, and runtime config loading from public `GET /api/config`.
- `SDK-1` follow-up completed: `TALK/client/talk_client.py` now supports `reply_to` and `client.reply(message_id, text=...)`.
- Docs updated for `MODULE_messages`, `MODULE_webui`, and `PROJECT_BRIEF` addenda covering reply semantics and `/api/config`.
- Automated verification passed: `python -m unittest` is green with `43` total tests, including new reply/config coverage in `tests/test_messages.py` and the SDK reply shortcut test.
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- Confirm the next product card after `MSG-4`; current reply support is intentionally flat and does not attempt nested thread rendering.
- If the next task stays in messaging, the highest-risk follow-up is tightening history visibility filtering in `GET /api/messages` so HTTP history matches WebSocket visibility more strictly.
- If manual UX acceptance is required, run the local browser flow for reply creation, jump-to-origin, revoke-after-reply, and `/api/config`-driven upload limit behavior.

### 2026-04-23 19:25 (Asia/Shanghai)
#### Current Progress
- `SDK-1` ?????????? `TALK/client/`????? `TalkClient`?????? `TalkClientSync`?????? `register/send_text/send_file/revoke/download_file/me/list_members/fetch_history/run` ??????
- SDK ??????? WebSocket ?????JSON `ping/pong` ??????????????? HTTP `since` ??????????? N ? `message.id` ???????? WS `from_field` ? REST `from` ?????
- ?? `examples/agent_sdk_demo.py`?????? `24` ????????? `agent:<name>`????? `ping` ??????? `pong`?????????? Agent??
- ?? `docs/spec/SDK.md` ?? SDK API ?????? `docs/spec/MODULE_agent_example.md` ?? SDK ?????`server/routes/files.py` ?? `HTTP_413_REQUEST_ENTITY_TOO_LARGE` ?? `HTTP_413_CONTENT_TOO_LARGE`?
- ?? `tests/test_talk_client.py` ? 6 ? `unittest` ???????/?????????????WS ????????????????? handler????????????? `36` ? `unittest`?`python -m unittest` ???
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- ?????????? SDK ?????????????? `reply_to` / ?????????????????????????????
- ?????? Agent ????????????????????????????????? Agent ???????/?????
- ???????????????????????? `docs/PROGRESS.md`????????????????

### 2026-04-22 23:29 (Asia/Shanghai)
#### Current Progress
- `WS-1` 已完成：WebSocket 心跳 `ping/pong`、空闲超时断开、入站 `send`、WS/REST 共用消息创建链路与鉴权重构均已落地。
- `FILE-1` 已完成：文件上传接入 `sha256` 秒传去重，采用 A 方案保留多条记录共享实体路径，并修正共享实体的过期清理逻辑。
- `OPS-1` 已完成：新增 `/healthz`、结构化日志、在线热备脚本、日志/备份配置段与运维文档，手动验收与自动化测试均通过。
- `MSG-3` 已完成：支持消息撤回、撤回态历史回放、WS `revoke` 实时同步、Web UI 撤回按钮与撤回占位渲染，文件消息撤回后实体保留。
- 当前全量自动化测试共 `30` 个 `unittest` 用例，`python -m unittest` 已全绿。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进下一个已确认任务卡，优先选择新的业务能力点，而不是重复打磨已通过验收的模块。
- 低优先清理两个工程尾项：`413` 弃用告警，以及前端撤回窗口时长与后端配置的统一读取方式。
- 保持后续任务的代码、模块文档与 `docs/PROGRESS.md` 同步更新。

### 2026-04-22 22:06 (Asia/Shanghai)
#### Current Progress
- 在现有 `tests/` 骨架上继续扩完 `M3-4`：新增 `tests/test_websocket.py` 4 个 `unittest` 用例，覆盖无效 token 拒绝、首次 presence 快照、上下线 presence 变更、实时消息推送、`since` 对齐去重，以及断线后通过 HTTP `since` 补历史。
- 扩充 `tests/test_files.py` 4 个上传链路用例，覆盖成功上传落盘/落库、上传鉴权拒绝、超限文件拒绝、上传后 `type=file` 消息对 `filename / size_bytes / mime` 的快照冻结。
- 为了让基于 FastAPI `TestClient` 的自动化测试可直接运行，`requirements.txt` 已补入 `httpx>=0.27,<1`。
- 测试基类已补应用注入与隔离能力：`tests/test_support.py` 现在会把临时 SQLite 引擎注入 `server.main`，并在每个用例前后清空 `hub` 连接状态，避免 WS 单测串扰。
- 已同步更新 `docs/spec/MODULE_websocket.md` 与 `docs/spec/MODULE_files.md` 的当前实现现状和验收标准，反映本轮新增自动化覆盖。
- 当前全量自动化测试为 `15` 个 `unittest` 用例，已通过 `python -m unittest` 全量验证。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 如继续补 `M3-4`，优先补 WebSocket 广播路径与“同一成员多连接”场景，补齐 `MODULE_websocket` 里仍未打勾的验收项。
- 低优先处理进度文档收口：按既定建议评估是否把 `docs/PROGRESS.md` 的历史段进一步收敛到双文件结构。
- 后续每完成一项功能，继续同步对应模块文档与 `docs/PROGRESS.md`，避免进度积压。

### 2026-04-21 23:29 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
- 今日开发先收口到这里；相关模块文档与项目简报已对齐到当前状态，包含 `tests/` 测试骨架与已覆盖的后端行为范围。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:08 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
- `M3-4` 已启动首轮自动化测试：新增 `tests/` 目录与 7 个 `unittest` 用例，覆盖成员自注册、消息 mention/分页/搜索，以及文件过期清理与下载错误分支；整套测试已跑通。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在现有 `tests/` 骨架上继续扩 `M3-4`，优先补 WebSocket/presence 与文件上传链路的自动化覆盖。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 23:00 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
- `MEM-1` 已补完真实链路验收：在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 验证了 Agent 首次注册、重复注册刷新、冲突 key 拒绝、`GET /api/members/me` 与成员列表读取。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 第二批核心功能已收口，下一步优先切到第三批里的 `M3-4` 单元测试，把这轮成员注册、消息分页/搜索、文件过期行为收敛成可重复执行的自动化测试。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 22:14 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
- `MSG-1` 已完成首轮落地：消息接口新增 `q` 关键词搜索参数，支持按正文 / 文件附言 / 文件名筛选；浏览器端历史工具条新增搜索与清除入口，搜索结果与历史分页共用同一套翻页交互。
- `MEM-1` 已完成首轮落地：`POST /api/members` 对 `agent:*` 新增幂等自注册语义，首次创建返回 `201`，同一 `id + api_key` 重复提交返回 `200` 并刷新 `display_name / poll_hint`；示例轮询 Agent 已同步改为识别 `200=已注册`、`409=真实冲突`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 继续推进第二批剩余项，优先做 `MEM-1` 真实链路手工验收，确认 Agent 首次注册、重复启动和冲突 key 行为都符合预期。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 按既定路线继续评估第二批后续项与第三批工程项的启动顺序，优先选择低风险、可快速验收的实现面。

### 2026-04-21 21:52 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
- 第二批已启动：`GET /api/messages` 新增 `before` 历史分页游标，浏览器端历史加载改为“先拉最新一页”，并增加“加载更早消息”按钮做向前翻页；实时增量仍继续使用 `since`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 在 `MSG-2` 基础上继续实现 `MSG-1` 消息搜索，并优先复用现有消息列表渲染与分页交互。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 21:48 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
- M3 已启动：Web UI 已支持安全 Markdown 渲染、代码高亮和多行输入框（`Enter` 发送、`Shift+Enter` 换行），文本消息和文件附言都可直接展示结构化内容。
- 第一批联动能力已完成首轮落地：WebSocket 新增 `presence` 推送，浏览器端新增在线成员条和新消息提示音；在线状态仍以 WS 为主、HTTP 轮询仅继续承担消息兜底。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 按既定路线进入第二批，优先实现 `MSG-2` 历史分页，再评估与 `MSG-1` 消息搜索的接口复用。
- 后续每完成一项功能，立即同步对应模块文档和 `docs/PROGRESS.md`，不再积压到统一收尾时处理。
- 在浏览器端最终验收前，继续把 M3 剩余体验项收敛在低风险的前端和 WebSocket 变更范围内。

### 2026-04-21 19:58 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 消息接收者解析已下沉到服务端：`POST /api/messages` 现在会统一解析文本正文或文件附言开头的连续 `@mention`，优先以服务端解析结果决定 `to_ids`，无效 mention 返回 `400`；无开头 mention 时继续兼容显式 `to` 字段。
- Web UI 消息列表已完成一轮性能优化：历史消息改为分帧批量渲染，实时/轮询消息改为 `DocumentFragment` 批量插入，并用内存 `Set` 做去重，减少大批量消息下的 DOM 压力；同时修正了历史加载与 WS 并发时 `lastId` 被旧值回退的问题。
- Web UI 发送错误提示已收敛为直接回显服务端 `detail`，前端不再承担真实路由决策，只保留 `@` 自动补全和基础输入提示。
#### Open Questions / Pending Confirmation
- 文件生命周期策略尚未确定：当前实现会长期保留 `files` 表记录和 `storage/files/<file_id>` 实体；如引入删除/清理，需要先确认“历史文件消息是否必须永久可下载”以及删除后的预期行为。
#### Next Plan
- 等待项目管理者确认文件生命周期策略，优先建议先明确“已被消息引用的文件是否永久保留”这一条基线规则。
- 策略确认后，按决策实现对应的文件保留/清理方案，并补充 API/前端在文件缺失场景下的用户可见行为。
- 在本轮已确认改动稳定后，同步更新 `docs/spec/MODULE_messages.md`、`docs/spec/MODULE_webui.md` 与 `docs/spec/MODULE_files.md` 的实现状态描述。

### 2026-04-14 00:12 (Asia/Shanghai)
#### Current Progress
- M2 核心链路已完成浏览器端整链路验收：登录、文本消息、文件发送、Agent 下载/回复、浏览器端下载、刷新后自动登录、WS 断开后轮询兜底均已验证通过。
- 成员鉴权链路已补齐：`GET /api/members/me` 已实现，`GET /api/members` 已要求鉴权；Web UI 登录已改为仅凭 API Key 自动识别当前成员。
- Web UI 已完成一轮细化：加入连接状态徽标、WS 自动重连（指数退避）、页内失败提示，不再依赖 `prompt` 和阻断式 `alert`。
- 文件消息协议已扩展：支持 `caption`，并在消息中冻结 `filename / size_bytes / mime` 快照；旧历史文件消息会在服务启动时按 `file_id` 自动回填这些字段。
- 接收者表达已统一为 `@mention` 模式：文本正文与文件附言都只解析“消息开头连续 mention 块”作为接收者；无开头 mention 时按广播处理；无效 mention 会在发送前红色提示并阻止发送。
- 相关文档已同步到当前实现：`AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/spec/MODULE_members_auth.md`、`docs/spec/MODULE_messages.md`、`docs/spec/MODULE_files.md`、`docs/spec/MODULE_webui.md`、`docs/spec/MODULE_agent_example.md`。
#### Open Questions / Pending Confirmation
- None
#### Next Plan
- 评估是否将当前“前端解析开头 mention 后写入 `to`”的规则下沉到后端，收敛为服务端统一解析逻辑，避免不同客户端各自实现一套。
- 继续处理 Web UI 可用性问题，优先考虑消息列表性能（虚拟滚动/分页）和文件生命周期策略（删除/清理）。
- 如需继续完善文档，补齐 `MODULE_files.md` 以外的状态细节，并在后续每轮确认后的实现落地后同步更新。

### 2026-04-13 00:00 (Asia/Shanghai)
#### Current Progress
- M2 核心能力已基本落地：文件上传下载 API、Web UI 文件收发、示例 Agent 文件收发已完成。
- 文件 API、静态资源路由和示例 Agent 的基础链路已在隔离环境中验证通过。
- 浏览器端 Web UI 仍待整链路手动验收。

#### Open Questions / Pending Confirmation
- 下一步优先做 `/api/me` 还是继续细化 Web UI。
- 是否安装 auto-resume hook 到 `~/.claude/settings.json`。

#### Next Plan
- 先完成浏览器端整链路验收，再决定 `/api/me` 与 Web UI 细化的优先级。

## 2026-04-12

**完成**

- **M1 MVP 代码全部落地并通过 API 端到端验证**：按 [§9 目录结构](spec/PRODUCT.md) 创建 `server/`、`web/`、`examples/` 完整代码骨架
- `server/models.py`：SQLModel 定义 members/messages/files 三张表 + Pydantic 请求/响应 schemas，`from` 关键字用 `Field(alias="from")` 解决
- `server/db.py`：用 `tomllib` 读取 `config.toml`，创建 SQLite engine（WAL 模式），提供 `get_session` 依赖
- `server/auth.py`：`X-API-Key` header → Member 查表鉴权依赖
- `server/ws_hub.py`：单例 Hub 维护 member_id → WebSocket 连接池，按 to_ids 精准推送或全量广播
- `server/routes/members.py`：POST 注册（自动推导 kind + 唯一性校验）、GET 列表
- `server/routes/messages.py`：POST 发消息（落库 + WS 广播）、GET 拉消息（since 游标 + to 过滤 + limit）
- `server/main.py`：FastAPI lifespan 初始化 DB，挂载 REST 路由 + WS 端点 + StaticFiles
- `web/`：暗色主题单页 UI（Tailwind CDN），含 @ 自动补全下拉框、WS 实时接收 + HTTP 轮询 3s 降级双通道、localStorage 保存登录态
- `examples/agent_poller.py`：纯 stdlib（无第三方依赖）Agent 脚本，自动注册 → 轮询 → 回声应答
- `config.toml` + `requirements.txt` + `run.sh` 基础设施
- **API 端到端验证通过**：注册 human:bobo + agent:AI1 + agent:AI2 → 定向消息 + 广播消息 → AI1 拉到所有消息 / AI2 只拉到广播 → TestBot Agent 自动注册+轮询+回复 → 中文 UTF-8 存储正确 → OpenAPI `/docs` 200 OK
- **建立全局项目文档结构规范**：创建 `~/.claude/CLAUDE.md`（文档结构标准 + MODULE 统一模板 + 模块拆分原则 + Agent 路由规则）
- **TALK 项目文档重构为 "1+N" 结构**：
  - `talk.md` → `docs/spec/PRODUCT.md`（PM 完整产品文档，位置标准化）
  - 新建 `CLAUDE.md`（项目级路由入口，指引 agent 先读 PROJECT_BRIEF 再读对应 MODULE）
  - 新建 `docs/PROJECT_BRIEF.md`（~100 行公共上下文：架构图 + 技术栈 + 数据模型 + 模块索引表）
  - 新建 6 份 MODULE spec：`MODULE_members_auth` / `MODULE_messages` / `MODULE_websocket` / `MODULE_files` / `MODULE_webui` / `MODULE_agent_example`，每份含目标、范围、接口契约、约束、现状、待改进、验收标准
- **改进 progress skill**：触发词增加"继续项目"，§3.4 强化为必须用 AskUserQuestion 等待用户指示才能行动
- **清理记忆文件**：删除已过期的 `project_sql_exam.md`，更新 `user_sql_background.md` 去除考试上下文
- 为 TALK 补充**部署拓扑**章节 [§4.1](spec/PRODUCT.md)：画出"拓扑 A 同机多 Agent"和"拓扑 B 跨机多 Agent"两张 ASCII 图，明确从 A 切到 B 只需 3 处配置修改（`host` / 防火墙 / Agent base_url），**零代码改动**
- 新增 [§5.1 关键配置项](spec/PRODUCT.md)：`config.toml` 的 6 个字段（`host / port / public_url / upload_max_mb / storage_dir / db_path`）及默认值，并在备注里留下"默认 `127.0.0.1` 的安全理由"
- [§12 验证步骤](spec/PRODUCT.md) 补了第 9 步：跨机部署端到端验证流程
- Plan 文件与 [TALK/talk.md](spec/PRODUCT.md) 双份同步，保持两份文档内容一致
- 创建并落地 `project-progress` skill：[SKILL.md](C:\Users\bobo\.claude\skills\progress\SKILL.md) 211 行，含两种操作分发（summarize/resume）、三源素材采集、同日合并、首次初始化、计划自动迁移、历史归档、auto-resume hook 文档化
- 首次运行本 skill 并生成本进度文件 `docs/PROGRESS.md`
- **改进 skill 项目根裁定逻辑**（SKILL.md 从 211 行 → 256 行）：把原本 "git → cwd" 的 2 级回退换成 **5 级 Tier 算法**：Tier1 git 根 → Tier2 IDE 打开文件的最近项目祖先 → Tier3 cwd 自带项目标记 → Tier4 cwd 是多项目父目录时 AskUserQuestion 让用户选 → Tier5 回退 cwd 并显式警告。定义统一的 8 种"项目标记"（`.git/` / README / package.json / pyproject.toml / Cargo.toml / go.mod / requirements.txt / **已存在的 `docs/PROGRESS.md`**）。新增 §1.3 透明度约束，要求 Tier 2/3 命中时在输出开头标注来源，Tier 4 必须询问，Tier 5 必须警告
- **M2 文件上传下载 API 完成**：`server/routes/files.py` 实现 `POST /api/files` 与 `GET /api/files/{file_id}`，支持鉴权、sha256、`upload_max_mb` 限流、磁盘落盘、404 与超限处理；`server/models.py` 新增 `FileOut`
- **M2 Web UI 文件收发完成**：`web/` 补齐文件按钮、拖拽上传、待发送文件面板、文件消息气泡与下载按钮；前端发送 `type=file` 消息时将 `content` 固定写为文件名
- **M2 示例 Agent 文件收发完成**：`examples/agent_poller.py` 支持 `--send-file` + `--send-to` 启动参数发送文件，并在收到文件消息后下载到 `examples/downloads/<agent_name>/`
- **今日验证完成**：文件 API 在隔离环境下通过上传/下载/404/超限验证；示例 Agent 在临时本地服务中通过文件发送与下载验证；前端静态资源路由可正常访问

**决策**

- Server 默认 `host = 127.0.0.1`：安全优先。开箱即用只允许本机访问；用户显式改 `0.0.0.0` 时自然会意识到需要同步加固防火墙和 API Key
- 不自动修改 `~/.claude/settings.json` 安装 auto-resume hook：settings 是共享配置，改动风险高，按工作习惯先确认再动
- skill 的进度文件统一放 `<项目根>/docs/PROGRESS.md`（非项目根下），归档文件同目录的 `PROGRESS_archive.md`
- 项目根裁定规则（未来需要改进 skill）：当前 cwd 是多项目的父目录时，`git rev-parse` + cwd 回退不够用，应额外参考 IDE 打开文件的最近项目祖先
- Python `from` 关键字冲突：MessageOut 模型用 `Field(alias="from", serialization_alias="from")` + `populate_by_name=True` 解决，API 输出保持 `"from"` 不带下划线
- `POST /api/members` 不要求鉴权（注册是引导流程，无先有 key 的鸡蛋问题）；`GET /api/members` 暂不鉴权（供 UI @ 补全用，M3 再收紧）
- `examples/agent_poller.py` 纯 stdlib 实现（urllib.request + json），零第三方依赖，便于任意环境即跑
- Web UI 采用 WS 实时 + HTTP 轮询 3s 双通道降级策略：WS 断开后自动靠轮询兜底
- 文档结构采用 "1+N" 模式：全局规范放 `~/.claude/CLAUDE.md`，项目路由放项目根 `CLAUDE.md`，agent 只读 PROJECT_BRIEF + 自己的 MODULE
- CLAUDE.md vs Skill 边界：规则/标准放 CLAUDE.md（自动加载），复杂流程放 Skill（触发执行）
- Claude 角色定位为项目管理者/产品经理，代码开发分配给其他 agent
- `type=file` 消息的 `content` 字段用于保存文件名，供 Web UI 与 Agent 接收端直接展示；本阶段不支持"文件 + 额外文字附言"同发

## 2026-04-11

**完成**

- 确定 TALK 项目方向：家庭局域网内的 AI Agent 聊天中转平台，支持 Agent ↔ Agent 和 人 ↔ Agent 通过 `@` 定向交互
- 通过 4 轮关键决策问答冻结技术栈：**Python + FastAPI** / **SQLite 全部持久化** / **HTTP 轮询 + WebSocket 可选** / **X-API-Key 鉴权**
- 撰写产品文档初版 [talk.md](spec/PRODUCT.md)，覆盖 13 个章节：产品背景、角色场景、F1–F4 功能需求、系统架构、技术选型、数据模型（含 SQL schema）、API 设计（REST + WebSocket）、关键流程（轮询/发消息/文件传输）、项目目录结构、非功能需求、M1/M2/M3 里程碑、端到端验证、待定议题
- Plan 文件 [prancy-soaring-eagle.md](C:\Users\bobo\.claude\plans\prancy-soaring-eagle.md) 完成并经用户批准
- 调研确认无任何既有 skill 可响应"汇总今日进度/继续开发"关键词
- 设计并通过 3 轮 AskUserQuestion 敲定 `project-progress` skill 方案：
  - 进度文件位置：`<项目根>/docs/PROGRESS.md`
  - 素材来源：git + 对话上下文 + `.claude/plans/` 三源融合
  - 默认内置：同日去重合并、首次自动初始化、文件头元信息
  - 已选增强：plan 文件联动、后续计划自动迁移、历史 >30 归档、auto-resume hook（文档化）
- 建立 [C:\Users\bobo\.claude\skills\project-progress\](C:\Users\bobo\.claude\skills\project-progress\) 目录

**决策**

- TALK 的 MVP 范围排除：公网部署、E2E 加密、多房间、消息撤回、Agent 自身 LLM 能力
- SQLite 够用，不上 PostgreSQL —— 家庭局域网单机场景零运维优先
- 前端不引入构建链（无 Vue/React/Vite），Vanilla JS + Tailwind CDN 即可
- 消息 `to_ids` 用 JSON 数组 + `NULL` 表广播的单表设计，避免引入额外 mention 关联表
- `id` 单调递增兼做 `since` 游标，实现 Agent 至少一次送达、不丢不重

## 2026-10-04压缩前进度快照（归档，不作为当前行动指令）

# Project Progress

Updated: 2026-10-04 (Asia/Shanghai)

## 当前状态

- 2026-10-04用户反馈：项目设置、解除/指定主控已验证正常；不扩称清理后全部刷新/创建场景均人工验收。新需求：①确认移除顶部“新建任务”（与已删角色快捷入口共享弹窗），保留主控公共派发，本次不扩大删除子任务入口；②角色名称下固定职责标签/说明改为可保存文本，默认沿用现有文字，按项目+member隔离，不以文字改变真实主控/权限；③适配本机DeepSeek Harness桌面；④未来TALK App启动自动拉起已接入终端服务，替代旧默认不自启方向，具体工作区范围/进程所有权另定。
- DSH-DESKTOP-0调查报告已收尾：#129/msg2626有效complete，Kimi独立复验确认#128修订F1–F7关闭；#126–#129已正式收取（msg2623–2626，completed）。保留#126本地partial/MCPunknown及#127 partial，不把流程收取改写为适配通过。MODULE_bridges同步实际npm0.1.5-rc.2与桌面0.2.0-rc.2的已知事实、推断边界、S1a/S1b未验证项；现有运行器不变。本轮未派新任务。#125设计已submitted（msg2621有效complete），仍待读取及独立复核。
- DSH初查：桌面D:/deepseek harness/DeepSeek Harness.exe文件版本0.2.0-rc.2，有内置resources/runtime/cli/bin/dsh.cmd；当前PATH的dsh仍为npm0.1.5-rc.2。官方当前文档称相同DSH_HOME共享会话等数据、desktop运行包/profile隔离，但本机两端home/会话可见与恢复尚未验证，不宣称同窗口或可卸载CLI。角色名册与终端适配分离，WorkBuddy加入某项目角色并完成接入后才显示，不因安装自动加入。

- MANUAL-TASK-AUDIT-1核查收尾：Codex确认公共任务API/MCP/SDK、共享弹窗与可见入口保留；旧黑板隐藏刷新/委派控件为可清理重复残留。#120/#121已正式收取（msg2615/msg2616，completed），保留#120原报告错误及#121自报partial，不将调查未执行删除/浏览器改称测试通过。主控另纠正#121“resume-tree仅human”附带误述：实际也允许根请求者，列表按身份过滤。正式裁决见DEVELOPMENT_ROADMAP代码取舍节。
- MANUAL-TASK-CLEANUP-1开发与独立复核完成：#122中断失败（msg2617）记录保留；DeepSeek #123续做交付complete，Kimi #124独立复核complete通过，无缺陷。Kimi实际复跑Node127/页面契约7、两JS语法及diff检查通过，六文件+7/-23精确符合范围。#123/#124于2026-09-23正式收取（msg2618/msg2619，completed）。删除旧隐藏控件及专属代码，可见新建/刷新/子任务与公共后端保持；资源20260923-manual-task-cleanup-1，真实页面待用户简要回归。证据.tmp/manual-task-cleanup-resume-1/及.tmp/manual-task-cleanup-review-1/。已恢复项目开发要求规定的双方交叉复核，AGENTS已同步。本轮未开新片。
- Git收尾受限：此前提交恢复记录的自动审批未能完成，返回工作区额度不足（review failure，并非判定操作不安全）；命令未执行。AGENTS及进度修改已本地保存，尚未提交推送，不绕过审批。待审批恢复后正常收尾。

- ROLE-SETTINGS-1已完成且用户于2026-09-23确认页面验收通过（代码eb45298已推送）：#118 Kimi开发、#119 DeepSeek独立复核complete通过（msg2614）；2026-09-23用户明确授权Codex直接处理剩余工作、暂不派任务。Codex将已有主控时的候选隐藏改为可见置灰，指定后焦点到解除、解除后回候选，原覆盖保护不变；实际复跑Node127、页面契约7通过。#119独立证据Node127/页面7/探针21只覆盖修正前版本，最新小改未另派独立复核，Codex未操作真实浏览器；用户随后确认验证通过，不扩称逐项键盘/时序场景全覆盖。资源20260923-role-settings-1，正式验收见docs/guides/CONTROLLER_ASSIGNMENT_ACCEPTANCE.md。#118/#119已在服务恢复后于2026-09-23正式收取（msg2613/msg2614，workflow_status=completed）；保留#118服务器unknown与本地包complete差异。本轮无新派发。

- 2026-09-20用户反馈C1b-S2“基本确认通过”，提出待落实的页面整理：角色列表首项增加“项目设置”，点击后独立显示项目开发要求与项目主控；具体角色页不再堆叠项目级面板。建议移除角色详情“交办任务”快捷入口（实际是打开现有创建任务弹窗并预选该成员），不删除任务系统/API或改变既有权限。用户未找到“窗口拉伸”：该项指浏览器窗口缩窄的人工响应式检查，不是TALK功能，用户随后实测窗口化浏览器并缩窄，反馈比例正常；响应式人工检查按该实际范围通过。原因Kimi额度不足曾暂不派发；用户随后确认充值并授权派发#118；2026-09-21再次因额度不足暂停给Kimi派发，按最新约束执行。

- C1b-S2页面已完成并通过收尾验证，待用户人工验收：#112开发→#113核心复核→#114焦点/迟到重绘修正→#115通过并发现保存归属问题→#116修正→#117静态复核通过但解释器受限partial。Codex补跑Node117、页面契约7、跨边界6及34/64/44探针通过；旧r114探针72/73唯一旧版本断言失配。保留#117 partial与#112服务器unknown事实；#112–#117已收取(msg2607–2612)。资源20260919-c1b-s2-owner，验收见docs/guides/CONTROLLER_ASSIGNMENT_ACCEPTANCE.md；用户基本验收与窗口缩窄检查已通过，后续按反馈做页面整理。

- C1b-S1后端已完成：DeepSeek #110开发，Kimi #111独立复核通过，Codex确认并正式收取（msg2605/2606）。新增长期主控指定/解除、独立版本CAS、配置状态、MCP只读输出；无租约/ACK/派发拦截。独立未筛选全量716项通过，补齐24项spawn缺口；并发名册/禁用窗口按已披露限制接受，详见PROJECT_INTEGRATION和历史。#111服务器unknown与本地有效complete分开记录。下一步S2角色页，当前无页面效果可验收。
- #110曾因服务/执行链路中断停滞，用户重启TALK和DeepSeek bridge后原任务重新领取并完成；具体根因仍未定。现在建议共享开发服务不带--reload；故障时间线写入历史，不将功能复核当真实库完整性验证。

- 2026-09-19用户已确认当前三项：页面唯一指定项目主控，供Agent读取遵守；保留现有任务权限、不加仅主控派发拦截；指定长期保存，无期限/续租，直到人工解除或更换。旧C1b会话租约方案被替代，归档已标失效实施依据。下一片C1b-S1做后端指定/解除与MCP读取，S2再做页面；自动转审、专用检查要求及多角色创建/接入入口列后续。
- 多角色创建现状已核对：cli.talk add-agent建立独立member_id配置，sync同步项目名册，bridge --name使用独立TALK凭证注册运行；当前页面管理已有Agent，尚无完整新建/复制角色及启动实例流程。页面新增角色入口属于待设计项，不宣称双DSH/Kimi同项目已实测。建议新建/复制时生成独立角色身份及TALK接入凭证，再单独完成运行器接入；不把复制角色等同于启动进程。当前采用人工解除后另选；不再实现会话绑定。

- C1b-0设计已完成独立复核并收尾：#104设计→#105发现问题→#106修订→#107剩余R1→#108定向修订→#109通过。Codex确认R1/R1-a/R1-b关闭，#104–#109于2026-09-19正式收取（结果msg2599–2604）；保留#105/#107历史blocked和#105服务器unknown/本地有效报告的差异。已复核v3归档 `docs/spec/C1B_CONTROLLER_CONTRACT_REVIEWED.md`，基线 `c20640b`。该旧设计随后被用户确认的C1b-S长期指定方案替代，不启动原C1b-1。只完成设计，无业务代码/数据库/API改动；细节与验证边界见历史记录。
- C1a项目主控模式配置基础已完成：DeepSeek #100开发→Kimi #101发现版本参数越界500→DeepSeek #102定向修正→Kimi #103复验通过；#100–#103于2026-09-19全部收取（msg2595–2598），保留#101 partial事实。基线 `a23b644`。
- 项目保存passive/active意向与版本（默认passive/0），human专用原子CAS入口防陈旧覆盖；MCP同次项目GET暴露requested与effective=null/not_bound。expected_version限定0..2**63-1，越界422，合法陈旧409。保存active不产生任务、等待、授权或会话唤回。
- #101独立复跑178项；#103针对返工复跑31+44=75项及17项探针全部通过，原29测试未丢失。主控做范围/文档及git diff --check，不重复全量测试。接口正式说明 `docs/spec/PROJECT_INTEGRATION.md` C1a节；证据 `.tmp/c1a/`。
- C1a只在隔离库验证，未重启共享服务/MCP或操作真实模式，不能宣称在线字段已加载；并发覆盖单进程多线程SQLite WAL，未验证跨进程/跨主机。C1b身份绑定/所有权/生效确认和C2按钮未实现，仍默认用户通知后取件。本数据切片收尾后暂停。
- ROLE-1已完成独立复核并获用户页面验收通过（2026-09-18，已推送代码 `ff656b7`）：Kimi #98开发、DeepSeek #99复核通过；两项已于2026-09-18正式收取（msg2593/2594）。基线 `0fd58aa`，dev/developer/reviewer统一“执行工作”与交叉验证说明，lead统筹不变；参与任务表“承担工作”换“执行耗时”。仅显示改动，不改角色权限或general任务类型。
- 独立复跑Node84项、Python页面契约5项通过，另有9项独立探针，验证双处计时同步、终态固定、单timer生命周期及REQ-2草稿不受影响。用户已确认本片页面验收通过，未单独声明各窄屏尺寸覆盖；资源版本 `20260918-role-1`；主控未重复全量测试。证据 `.tmp/role-1/`，正式说明见MODULE_webui与PROJECT_REQUIREMENTS_ACCEPTANCE指南。
- 低优先级非阻塞待办：自定义业务角色若为constructor/toString等原型键，标签/说明可能显示异常；现有lead/reviewer/dev不受影响。本片不扩大返工，未来可用Map或自有键判定加固。
- MCP在线补验已完成读取与正常派发快照：用户重启后工具描述/字段更新，#99派发前读取最新要求（DeepSeek后端及其他未提及内容），创建返回和随后get_task均确认持久化正文含最新要求快照。旧任务不追改仍以隔离测试覆盖，未额外修改真实要求实验。
- #98曾queued/assigned无领取；用户重启Kimi/DeepSeek bridge后自动领取完成，未重复派发。此事实支持执行端恢复，不证明原进程中断的具体原因。
- REQ-2角色页项目开发要求编辑区开发完成并通过独立复审：Kimi #94开发→DeepSeek #95发现问题→Kimi #96返工→DeepSeek #97通过。#94–#97已于2026-09-18正式收取（msg2589–2592）；保留#95的partial/验收不通过事实。开发基线 `cdc8416`，已推送 `d3059ed`；用户已确认页面验收通过，明确跳过第5项（agent只读/桌面窄屏布局）与第6项（更新后MCP读取与委派快照在线链路），两项保留未人工验证，不将自动化证据改写成在线验收。
- R1统一详情刷新隐藏编辑区（群聊不再残留）、R2前后端空白语义对齐、R3职责说明修正。复核Node78项、Python49+95项全部通过；导航隔离阴性对照检出原问题，Unicode全码点判空集合与Python零分歧、25例真实隔离端点验证通过。主控未重复全量测试。
- 界面支持human保存/清空、agent只读，20000码点、项目/账号隔离内存草稿、迟到响应保护、保存中继续编辑、旧后端缺字段禁用保存。Agent未重启共享服务/MCP或填写真实要求；用户已确认其余页面验收通过，第5/6项未人工验证，步骤见 `docs/guides/PROJECT_REQUIREMENTS_ACCEPTANCE.md`。
- 职责分工改由项目开发要求统一维护，AGENTS与TASK_WORKFLOW不再重复固定模型映射；未读取有效要求且本次无明确分工时先由用户配置，不自动保存示例。孤立代理码点提交触发既有后端500仍为独立待办，前端不会假报成功。

- REQ-1提交 `b32ef7c` 已于2026-09-18推送至 `bobo506/TALK` 的 `codex/terminal-return-codex`。此前自动审批拒绝后，用户明确确认本次及今后本项目常规推送授权，重试成功；持续授权已记录AGENTS.md。
- REQ-1 后端/主控工具已完成：DeepSeek #92 开发、Kimi #93 独立复核通过，Codex 已于 2026-09-18 正式收取两项（msg2587/msg2588）。基线 `ada3b71`；新增项目最新开发要求字段、兼容迁移/API/CLI、角色清单读取与 MCP 新任务正文快照，旧任务不追溯修改。
- Kimi 在独立环境分批复跑全部638项通过（162+319+67+90），补齐开发者环境24项管道限制。开发报告含失败组标pass及基线计数不一致保留为记录，不采信其全量通过表述。#92服务端正文因说明/围栏为unknown，本地包任务号校验通过；验收依据独立代码复核与复跑。
- REQ-1接口边界保持：直接REST/schedule/旧pi扩展不自动写快照；源码与隔离验证不等于在线生效。REQ-1/REQ-2证据分别在 `.tmp/req-1/`、`.tmp/req-2/`。

- WorkBuddy桌面5.5.6两模型的有人值守单任务闭环均通过：kimi-k3委派90给DeepSeek、deepseek-v4-pro委派91给Kimi；用户在原对话读取并转交结果，Codex验收后明确授权原对话收取。90/msg2585于2026-09-17T07:39:30.617132Z、91/msg2586于07:45:18.107869Z收取。Codex独立核对两次服务器POST collect-result 200及agent:workbuddy身份；同对话/模型选择来自用户回传，不声称服务器可证明具体模型。
- 配置采用用户实际界面中的用户级MCP；专用凭证与准备配置位于仓库外。项目级自动加载、跨工作区、跨重启会话恢复、无人值守和TALK页面运行器适配未验收。无需为本轮改TALK业务代码；完整运行器适配仍是后续开发。
- 88提前收取调查89已收尾：日志证实agent:workbuddy收取请求先于Codex只读403，不是此次读取副作用；具体客户端/模型触发来源未定位，91补测不能反推88。86原交付错号保留，主控整理副本仅修正task_id。

- DSH ACP 薄驱动与测试已完成：#74开发→#75复核→#76返工→#77复核→#78夹具修正→#79最终复核，六项已正式收取；基线 `3fcbf44`。#77真实零模型握手、建会话/关闭/列表/同ID恢复及拒绝分支通过；#79独立复跑ACP 30项、入口18项全部通过。
- #78将测试假密钥放到明确校验的仓库外系统临时目录并清理，缺密钥负例隔离HOME；仓库内凭证禁令保留。开发环境18项因CreatePipe未运行，已由#79实际补齐。测试模拟ACP服务下的环境清洗与九工具可达通过，不代表真实模型工具可见。
- DSH真实模型单任务闭环已通过：#80身份/配置通过但CreatePipe阻塞；#81由Kimi操作员环境启动原生DSH（deepseek-v4-flash）委派#82；Codex源码级验收后#84恢复同一ACP session读取并收取82。80/81/83/84已由Codex收取，82由原生DSH收取，保留80的blocked结论。
- 原生session `730ca24f-50d7-4bb3-b5cc-895d6097bdb6`；82结果消息2563，收取时间 `2026-09-16T08:14:18.429954`。同cwd/DSH_HOME，resume而非new，get_delivery两次（含detail）、collect一次；主控独立核对原始驱动取证及服务器结果快照与本地JSON一致。无人值守、多工作区、正式页面运行器适配仍未验收。
- 资源告警额外改动由用户同意备份后撤回，四文件恢复1bf186b；备份 `.tmp/l1-dsh-live/resource-cleanup-backup/`。#83未闭环确认作者；不再为归属阻塞主线，不将未审修复纳入本片。原ResourceWarning保留为独立待办。
- 已有ACP工具提交 `1bf186b`。本轮只维护验收记录；试验结束清除隔离DSH_HOME中的模型凭证副本，保留会话证据及仓库外本人TALK凭证。恢复试验前须重新安全配置合法模型凭证。
- 继续采用用户通知后取件，不主动等待；本片收尾后暂停，下一项可安排角色列表项目级开发要求。

- 当前 Codex 为决策 Agent，分支 `codex/terminal-return-codex`。Kimi Code 0.38.0 单项目、单任务的真实主控试验已跑通：原生会话委派 #67→DeepSeek 只读执行→Codex 独立验收→同一 Kimi 会话读取并收取。不是所有终端/多工作区/无人值守主控能力验收。
- #64/#65 失败试验与诊断、#66 委派、#68 成果转交、#69 原会话收取均已由主控收取；#67 由原请求者 Kimi 于 2026-09-15T14:12:22.756535Z 收取。保留前序 partial/失败事实，不因流程 completed 改写业务结论。
- 受信隔离目录 `D:/claude-test/TALK/.tmp/l1-kimi-live/session-workspace` 的信任由用户明确授权后写入；配置仅在该目录，仓库根临时配置已撤回。保留审计与会话，不清理信任记录，不启停共享服务。
- 原生 session 为 `session_e7d95ad9-b799-4593-a8cf-19da479d780d`；初次通过 `--agent-file` 白名单限定 12 工具（Read/Grep/Glob+9 TALK，无派生），续接用 `-S`，实际工具调用与 profile 记录确认未扩张。一次顶层 general 委派由 Codex 明确授权，不代表修改全局 may_delegate/预算规则。
- #67 结果消息2542有JSON围栏；主控直接读Hall被403，原请求者合法转交后本地校验。Codex独立核对源码及4组纯函数输入/重复归一化断言，通过后原模型以 get_delivery detail 核对哈希再 collect。此人工转交路径已实测，尚未实现主控共享审查入口或自动唤回。
- L1-1 入口工具已推送 `29e5021`；N1已推送 `2b917ce`，新任务标题已实际生效，历史不迁移。耗时与整体页面仍未明确人工验收。

## 下一步与待办

- 2026-10-04已按用户要求登记后续“项目角色配置与自动启动”：全局接入运行器→项目角色列表选择添加→每角色手动启停/自动启动开关；只自启当前项目已配置且勾选的角色，支持同运行器多角色。细节见DEVELOPMENT_ROADMAP对应节，未排期、不新增任务，不扩大#125/#126。

- 自动转审已按用户要求详细登记于DEVELOPMENT_ROADMAP“自动转审与检查要求配置”节：默认检查角色、固定规范+任务验收标准+实际交付证据、独立判断、异常返回主控及去重/授权边界；未排期，不改变#110或当前手动转审流程。

1. DSH报告复验已通过；下一步可安排S1a隔离无凭证启动验证，先核对副作用与执行环境，不能绕过此前拒绝或直接操作真实home。S1b真实模型契约另列范围，桌面UI会话可见/恢复仍待验证。#125角色描述设计待读取及独立复核，再分片实施顶部入口移除、可编辑说明；项目角色配置与自动启动仅列后续。自动审批恢复后完成已复核代码及文档Git收尾，#122失败保留。
2. 当前项目开发要求已由MCP实际读取；后续派发继续每次读取最新要求并按既定一次一片/交叉复核流程推进。用户明确独立任务继续general，分类改造仅路线待办。
3. 低级别原型键显示加固、孤立代理码点后端500、既有临时目录残留为独立待办；多工作区/页面运行器/无人值守/群聊后续阶段仍按路线，不借本轮结果宣称完成。
4. 本项目常规推送持续授权目标 `bobo506/TALK`，分支 `codex/terminal-return-codex`；ROLE-SETTINGS-1人工验收已通过，本轮不自动开启新片。

## 等待与交付流程

- 用户已采纳#57建议1：AGENTS固化无新输入/异常时只按原运行标识续等，不额外查询、读文件/diff或重新展开方案；必须更新时最短说明，完成/异常/新输入及时处理。仅提示词约束，未量化节省。建议2（降低推理强度）和3（用量归因方案）不推进。
- 当前默认仍由用户通知主控收取，持续等待须用户明确要求。#56部分验证报告已收取，受DSH沙箱限制未运行A/B，Desktop指令替换范围仍未知；#57咨询已收取，本次不继续这些实验。

- 项目外层等待目标600秒仍以宿主能力/更高优先级指令允许为前提；本轮实际exec外层yield=60000ms，内部wait预算600秒。4次请求内部耗时600.032/83.032/600.032/47.734秒，持续主控等待到复核收取完成；不能宣称验证了外层600秒或节省token。
- 此前短程yield600000参数未报错、53.6秒返回；连续600秒阻塞能力未证实。用户级MCP超时660秒、执行者预算3600秒保持，未改全局配置。
- #50/#51完整结构化JSON入服务器与新MCP摘要真实入口已验证；#52/#53调研已收取，二进制原句命中不证明当前加载路径，替换配置能否覆盖开发者层指令未证实。无外部自动唤醒、断线补领或取消立即生效保证。
- 主控按TASK_WORKFLOW摘要读取，必要时按稳定引用补读；schema匹配只是自报，不替代独立复核。执行与复核分工派发前读取当前项目开发要求；Codex维护正式文档/Git，不重复全量探索。

恢复指令：继续项目。完整证据见PROGRESS_HISTORY.md。
