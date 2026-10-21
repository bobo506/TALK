# 290条件十次备用：首次独立实查与直接补正

2026-10-21（Asia/Shanghai）。290已完成首次独立实查、直接补正和离线集成，280项通过，产品提交57cb119已推送。此前API拒绝连接使collect失败，原回执保持；用户随后明确允许仅恢复原API并补收。19:12原启动器恢复、healthz正常，19:13:09已收取为completed，结果2896及原文SHA不变。没有派新任务、启动角色或加载会话机制，恢复证据见本节末尾。

## 身份、原件与范围

- 本人`agent:codex`/agent、lead，project `prj_e8fe7066bbec`。最新页面开发要求仍旧交叉复核，按AGENTS本次分工覆盖，未改页面。交付后已核DeepSeek idle、current_task为空，才串行整合/修改；Kimi仍暂停新任务。
- task290、creator `agent:codex`、target `agent:deepseek`，Hall `group:task-57de85e8ddd64baeae1006f1cadfbf63`，最近可读runner succeeded、workflow submitted、结果2896。两页原文SHA为`6c4b8963cea32eb64fdb73ed1a82abf1bb8828dd529f1cf920e5c4991f28f6b2`，拼接与本地交付JSON一致；complete为执行者自报，不等于独立验收。
- 产品基线`ad46037d26286f45e3302bb208a75a3c7ff544e2`；取件HEAD为`2d9d7f89f5acb681cc276e6aaac1b22615828b7e`。19份公开冻结材料SHA保持；执行者27个实际文件（含4个pycache）全部保留、SHA不变，自报23个交付文件与这些缓存区分记录。
- 原件与证据在`.tmp/execution-session-fallback-v1/deepseek/`，Codex复核在同根`independent-review290/`。正式产品仅两Python模块和两对应测试；JS采集器、运行中bridge/host、配置/Key/绑定/owner/历史任务保持。

## 独立发现及修正

原候选156项内核、71项适配测试复跑通过，独立探针和路径检查仍发现以下问题：

1. 缺容量优先返回missing，掩盖非法projected；pressure缺失也能把unknown projected改成tokens_missing。
2. missing提前返回，未检查剩余来源超cut或同事件/时间顺序矛盾。
3. 缺数证明只有可解析的observed_at，没有当前时钟/年龄核验，2099年的证明仍获续用。
4. 原始样本缺容量或过期可掩盖其它显式非法数值，再被可兜底声明覆盖。
5. 同revision的旧低读数可覆盖高占比；同一事件的冲突值也可覆盖，导致缺数后继续旧窗。
6. 非字符串outcome（如list）触发TypeError；窗口交办历史倒序revision未完整检查。
7. 候选适配测试依赖本机冻结目录，直接放正式仓库会无法运行。

Codex补全部字段/来源优先检查、原始样本备用前校验、显式`fallback_clock`、观测`now`及倒退/冲突守卫、安全outcome和历史顺序校验；宿主能力声明仅接受三种helper原因。正式测试改为仓库模块/Node入口、独立临时输出，原两项冻结对照保留为基线规范JSON固定哈希，无`.tmp`依赖。

首次补正自检曾出现10个内核断言/子例和1个适配断言失败：原无分类调用的详细原因被新拦截覆盖、旧测试把同一事件的高低值当新观测、来源通用检查遮住既有具体原因。已保留日志并修正原因兼容、将测试新低读数放到真实较新时刻、保留具体顺序原因优先；未弱化禁止续窗的断言。修正部分均称Codex自检，不冒称他人独立复核。

## 最终证据

| 检查 | 结果 |
| --- | --- |
| `python -B -X utf8 tests/test_execution_sessions.py` | 170通过 |
| `python -B -X utf8 tests/test_dsh_context_metrics.py` | 76通过，含实际模拟采集输出跨语言联测 |
| `node tests/test_dsh_context_capture.mjs` | 34通过、零跳过，JS未修改 |
| 总计 | 280项唯一用例；不把原候选/冻结复跑重复相加 |
| 原件/冻结 | 27/27及19/19 SHA一致，MCP原文与本地JSON一致 |
| 静态边界 | 两模块仅标准库，未接运行bridge/host/API/MCP；正式测试无临时交付目录依赖 |

原探针、原227项复跑、首轮补正失败、最终日志、固定对照哈希、验证JSON和collect失败回执分别保留，汇总索引为`independent-review290/verification.json`。本地证据文件不随产品提交，必要结论在本记录留存。

## 当前验收边界与后续

离线规则已满足：同功能/scope/通道先验；可靠60%优先；仅单纯缺数且可信窗口计数时最多10次；ACK幂等、首轮累计、恢复不清零、非法/矛盾不备用；最后高占比不会由旧低值或未知覆盖。新窗完整、续窗增量、权限和合同引用规则保持。详[最终API与宿主责任](../guides/EXECUTION_SESSION_FALLBACK.md)。

当前仍无真实ACK/锁/CAS/持久化。调用者必须原子保存可靠观测和真实送达历史；遗漏高占比持久化可能错误延长备用，不能凭纯函数声称历史可信。字符串revision仅支持精确相同，真实接线需可核的顺序事实。

采集器未加载，实际版本/home/插件/上下文读数未知；原生续用、协调端增量生成及任务/MCP/API/页面尚未接通。没有读真实配置/profile/会话/凭据/日志/DB，没有CLI/ACP/模型/Browser调用或主动等待。此前API退出原因未核定；用户随后明确允许仅恢复API并补收290。恢复未扩大为角色启停或新片派发，后续切片继续先确认。

## API恢复与补收（2026-10-21 19:12–19:14）

- 用户明确“允许”恢复原TALK API入口并补收290；只恢复API，角色服务保持原状，不派发新任务。
- 恢复前原health仍写running，但launcher5236/child13952均不存在，8000端口空闲，无stop.request；数据库只读核290为submitted/结果2896、running任务0。五角色记录中的PID均已不存在，不将旧实例idle或health标签当在线事实。
- 核原启动器SHA为77e92903624f621616c40512ad3e44defb5e6cf8a8272f39c37a2c506ac01cc6，按原`.venv`/127.0.0.1:8000/无reload入口隐藏启动；新launcher7764、child10096，原Popen与创建时间可核、automatic_restart=false，healthz正常。没有复制认证、改配置或启动角色。
- MCP核本人agent:codex/agent；页面旧要求保持，按AGENTS本次分工。task290 creator/target与原结果2896匹配，原文SHA6c4b8963cea32eb64fdb73ed1a82abf1bb8828dd529f1cf920e5c4991f28f6b2未变；19:13:09正常collect，workflow completed，原自报不追改。
- 跨工具调用后再次核API进程/healthz正常，配置SHA、五角色generation/launch/owner/PID及进程创建事实均与恢复前相同，五个记录进程仍不存在，running任务0。原失败回执保留，新增证据在`independent-review290/api-recovery-20261021/`的preflight/start/api-restored/collection/final-check。
- 本轮仅运行恢复、账本收取和文档状态收尾，产品代码未改，不重复执行此前280项测试。会话机制仍是离线实现，真实指标采集/原生续用/任务接线/ACK存储尚未启用；本次不增加自动恢复角色或连续开片授权。
