# Project Progress

Updated: 2026-10-22 17:17（Asia/Shanghai）。用户明确继续Kimi适配，仍由当前Codex自行开发。K2.8/K3共用适配已完成开发、自检及本机真实CLI配本地假模型验证；Kimi额度暂停保持，生产加载/真实账号验收未完成，不称全角色完成。本片等最小实机安排确认，不开新片。

## 当前交付

- 身份agent:codex/agent、项目prj_e8fe7066bbec/lead。用户本片明确由Codex自行实施，不派DeepSeek/Kimi，全部工作称自检。基线56060b8，证据根`.tmp/execution-session-kimi-v1/`。
- 三个Kimi角色同为kimi-code运行器：K3 alias=kimi-code/k3；两个K2.8 alias=kimi-code/kimi-for-coding。共用两份Kimi适配模块，按角色/模型/请求者/工作线/HOME/配置权限/服务代次/基础合同隔离窗口和计数，不复制两套模型实现。
- API/MCP/SDK元数据、领取前基础合同和续轮预检、正式runtime分派已接线；首轮完整/续轮增量/新窗恢复、可靠60%及单纯缺数可信计数10/11复用原内核。Kimi2.0.2首轮原Agent创建、续轮明确session恢复并核模型/工具/subagents；原生用户prompt与上下文消息同ID/SHA双证明后计数。
- 首轮CLI创建后才获原生ID：先以既有sidecar空串预留未知ID，再持有者/租约/窗口/通道/尝试一次CAS绑定，ACK/计数按原事务归并。无schema变更，不重跑重复/不明尝试。预检/工具/自动介绍不计；已证明送达后的取消/失败仍计数并停用旧窗。
- 上下文数取原生token_counting，容量取精确模型配置；llm.request.maxTokens是输出预算，不当容量。非法/未来/配置冲突不兜底，恢复读数不清零；sidecar不新增助手正文/凭据。Windows argv超长明确拒绝，不截断。

## 验证与保护

- 338项相关Python一次全过（tests-final-2.txt），覆盖三运行器、内核/指标/计数、API、MCP及Kimi普通领取入口；最后收紧未来时间校验后Kimi29项定点复验全过（tests-final-kimi.txt），不重复累计用例。全部为Codex自检。
- 本机真实kimi.exe2.0.2、独立HOME/sidecar、回环假模型21轮/21本地请求通过，证据`native-integration/b27d4189/`。K3/review与K2.8/tools各5轮：1→2同ID/计数1→2、增量回想星河42；3强制新窗恢复杉木53；4结束6000/10000后5换窗。受控隐藏指标1..10同窗，第11换窗恢复。未消耗真实Kimi账号额度，不冒称自然缺数或真实模型压力测试。
- 302条生产既有任务逐行SHA、原config/绑定、五角色服务记录、286全文/暂停均保持。未派Kimi生产任务、未重载API或启停角色。三个Kimi DB记录stopped/无process_launch，DB快照不作当前在线证明。原人工操作Key被当前沙箱拒绝读取，未调用human API或换凭据。
- 原DSH/Codex适配/内核、原Kimi bridge/身份/模型/Key/HOME/权限保持；上片Codex300→301真实同窗、302恢复及DSH293–297证据不重跑、不追改。TALK页面保持；286、日志手动跨设备/全根留存、全入口21600及宿主统一启动排期不扩展。
- 已读终端MCP预算要求：Kimi实际客户端T未重测，660000仅模板事实；不主动长等待/自动唤回。执行预算沿原入口21600；Windows taskkill/Popen退出各10秒清理等待，与MCP W分开。

## 文档与Git收尾

- [Kimi适配与待验范围](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)、用户手册、AGENTS/简报/bridge模块、本快照/历史已同步当前边界，既有历史结果保持。
- 本片代码/测试9份：两份Kimi新模块、cli_bridge、execution_session_store、server/execution_session_tasks，以及Kimi/Codex/API/MCP四份测试；另8份文档。git diff --check通过，既有未跟踪产物保留；按常规提交/推送收尾，具体版本见当前Git日志。
- 完整记录见[历史进度](PROGRESS_HISTORY.md)。额度精确百分比未读取，不臆测。

## 下一步（同片待确认）

- 用户明确允许后，才临时使用原Kimi账号和原API/宿主，对K3与一个K2.8各做首轮/续轮/force_new三轮最小生产验收，核原生会话/计数/完整恢复，并由合法原请求者收取。必要普通启停按原归属守卫；不自动解除owner、不改Key/绑定/模型/权限，不据此恢复常规派发。
- 真实账号/加载未完成前不称全角色可用；本片遗漏继续在本功能内补齐。下一功能、宿主统一启动和其它新片仍须另行确认。

恢复指令：继续项目（先读Kimi适配及待确认范围；TALK页面不改、Kimi额度/286暂停；不重放已用生产脚本）。
