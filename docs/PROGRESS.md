# Project Progress

Updated: 2026-10-22 20:05（Asia/Shanghai，实施中）。用户已确认WorkBuddy自带官方引擎作为独立CLI运行器接入，由当前Codex直接开发/自检。代码已接线，403项联合自检及安装版16轮本地假模型通过，生产短文本闭环待验；不等同桌面窗口控制，不转宿主自启。

## 当前交付

- WorkBuddy片：新native/channel/bridge及单角色host，API/MCP/普通领取与宿主配方已接线；模型源只读引用、会话HOME独立、stdout与原生双ID/SHA证明，真实usage/input容量、同窗/60%/条件十次/基础恢复均按原内核。403项联合Python通过；安装版16次正式投递/17次fake模型请求通过（含60%与受控10→11）。当前未使用真实模型或新增TALK任务；原human/WorkBuddy Key已验证、308条历史/五角色/原配置/286基线固定，准备只补WorkBuddy项目登记/独立运行器后普通加载与三条短验收。详[本片实现和边界](spec/EXECUTION_SESSION_WORKBUDDY_ADAPTATION.md)。
- 桌面调查已核预填深链仅prepareInput，官方本地助理Open API未提供指定会话/创建新窗参数，未把包内CLI当桌面证明。computer-use只查看/展开桌面，截图失败后可访问文本读取成功，未发消息/改设置。用户随后选择独立CLI方案，桌面自动控制不在本片新交付内。
- 一次诊断误把models数组完整输出，导致两项原Key进入本次工具日志，已如实告知用户；未复述或擅自换Key。改用固定字段白名单，50份本片产物精确扫描无凭据正文，证据private-metadata-safe.json。后续不得输出原models/settings/mcp对象或完整异常。
- 身份agent:codex/agent、项目prj_e8fe7066bbec/lead。用户指定本会话直接实施/验收，不派DeepSeek/Kimi开发；全部称自检。产品提交6f1a293已推送，本轮产品源码不变，新增生产验收和8份文档收尾。
- K2.8/K3共用kimi-code适配，按角色/模型/请求者/工作线/HOME/配置权限/服务代次/基础合同隔离。API/MCP/SDK、领取前预检、正式原生分派及持久计数已接线；首轮完整/续轮增量/新窗恢复、可靠60%/条件十次用原内核。
- Kimi2.0.2正式prompt/context双ID/SHA证明送达，首轮预留未知原生ID、一次CAS绑定，失败/取消/重复不重跑。指标取token_counting和精确模型容量，输出maxTokens不作容量，非法/未来/配置冲突不兜底；首轮计1、工具/预检不计、恢复读数不清零。

## 验证与实机

- 开发阶段338项相关Python通过，最后收紧未来时间后Kimi29项定点复验通过，不叠加计数。真实CLI配本地假模型21轮通过，含60%和受控缺数10→11。原账号直接原生两模型各三轮已通过，17:37零TALK任务阶段记录保留；生产K3/旧K2.8原tools权限保持。
- 用户最新授权后，原human:bobo创建/收取六条general短文本，Kimi不开发、不调用工具或文件。303→304的K3同ID session_e9184946-9730-44b3-b3da-5b2b558bf8e2，306→307的K2.8同ID session_25479f95-9055-4729-81d7-774b679be0a4，两者计数1→2；305/308均新ID恢复基础、计数1。六任务succeeded/completed，结果消息2909—2914均已收取。
- 续轮增量未重发暗号/基础标记仍正确答“海棠42 / 鹿鸣57”，新窗答“鹿鸣57”。原生双SHA和精确模型/alias逐条通过，正式请求6、无工具，必要预检另计；产品sidecar六尝试confirmed、通道0。真实低占用用量K3 7107/7652/7133、K2.8 7252/7803/7259，容量1048576；60%/10次压力边界仍为受控证据。
- 临时恢复两个原窄宿主并普通start/stop：K3 manager10708/gen25→26，旧K2.8 manager5524/gen26→27；最终stopped/无owner/可启动。临时宿主空handles后正常drain退出，第三Kimi始终停止。API10600未重载，DSH/Codex代次/实例保持，无owner恢复、强杀、改Key/登录/绑定/权限。
- 302条原生产任务逐行SHA、配置/绑定、Key文件mtime、286全文/暂停、其它角色均保持，恰好新增303—308六条验收任务。证据`.tmp/execution-session-kimi-v1/production-validation/`含各阶段回执、原生审计、正常启停/drain及最终保护核对；此前account-validation证据保持。
- 辅助脚本首轮错误断言与宿主健康异步回报已处理，只收取原303、等清理完成，无重复模型或产品修正。305权限审核首次超时，按系统允许一次重试后成功；原失败留存，详Kimi适配与历史。

## 当前边界与收尾

- 当前三种运行器DSH/Codex/Kimi Code的功能开发和生产任务链已接通，WorkBuddy尚未适配。旧2026-09-17记录仅WorkBuddy桌面MCP有人值守的单任务委派/读取/收取，不覆盖会话恢复；当前项目可派名单也没有该成员，不能从历史注册推断当前项目可派。另一K2.8成员独立HOME/登录未单独实机。三个Kimi仍停止，开发派发暂停，人工里程碑待确认。
- TALK页面不改，286、日志手动跨设备/全根留存、全入口21600及宿主统一启动排期保持。Kimi MCP客户端T未重测，660000仅模板，不宣称主动长等待适配通过。
- [Kimi适配](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)、用户手册、AGENTS/简报/bridge模块与进度/历史已同步，按常规提交/推送收尾；既有未跟踪产物保持。精确额度百分比未读取，不臆测。

## 下一步

- 继续当前已授权WorkBuddy内置引擎独立CLI片：实现真实会话/指标/用户ACK适配、同窗/60%/条件10→11、基础恢复、API/MCP/普通任务分支及必要宿主配方，完成针对性自检/安装版假模型边界与真实账号短闭环后收尾；模型/Key/绑定/权限及286保护保持，不向Kimi派开发任务。不能把CLI结果写成桌面窗口控制通过。
- 整项完成前不提前转宿主统一启动；下一片仍按AGENTS先确认，不自动派发、启停或解除归属，286保持暂停。
- 完整记录见[PROGRESS_HISTORY.md](PROGRESS_HISTORY.md)。恢复指令：继续项目（先读本快照，Kimi常规开发仍暂停，不恢复286、不重放单次生产脚本）。
