# Project Progress

Updated: 2026-10-20 21:48（Asia/Shanghai）。用户明确“那确定了，动手开发吧”，288已派DeepSeek首次实现会话选择、60%换窗及首轮完整/续轮增量的离线内核，创建queued/assigned。默认用户通知完成后取件；尚无开发交付/独立验收/集成结论，不开启真实采集/续用或部署。

## 当前开发：288会话机制内核首片

- 本人MCP实测`agent:codex`/agent、lead、project `prj_e8fe7066bbec`；页面最新开发要求仍旧交叉复核文本，原样存快照，按AGENTS最新约定：DeepSeek首次实现/自测/交付暂停，Codex独立实查/直接修正。Kimi额度暂停所有新派发保持。
- 用户已确认机制并要求开发，本次拆出[首片合同](spec/EXECUTION_SESSION_CORE_SLICE_1.md)：只实现纯数据统一规划入口和测试，不依赖或改真实DSH配置。真实指标采集/原生会话创建恢复/任务MCPAPI/页面和部署另片确认，不将本次授权扩大为自动连续开片或启停。
- 288：creator `agent:codex`、target `agent:deepseek`，Hall `group:task-793daa1d8d874e3d966ac5a181a2190c`；独立顶层四参数，创建queued/assigned。派发前DeepSeek原`ins_00acba0f8a9b`/PID12284为idle/无当前任务，queued仅286且paused、running为空。
- 基线`48526a7851561cd81a42deb3bb82652105df2089`；22份公开源/测试/指定文档共1,149,727字节冻结在`.tmp/execution-session-core-v1/baseline/`。manifest、身份/要求快照、原合同/请求及创建回执在`coordination/`，均执行者只读；唯一可写`deepseek/`，候选仅`candidate/bridges/execution_sessions.py`和`candidate/tests/test_execution_sessions.py`，其它为本片测试/交付产物。
- 必验：显式新/续用、结构化工作线/角色/工作区/配置/会话代次/基础合同匹配，同工作线不同任务可续；busy/无独占不得同home fresh绕过；原始整数阈值59.9%可续/60%换窗，projected优先/非法未知过期不当0、无轮数兜底；新窗完整/续窗只增量和必要新Hall、任务独立留档可还原、输入不变。
- 仅标准库离线合成测试，python -B避免冻结区pycache；模块不IO/读环境/启动进程/创建真实会话，正式bridge不导入新模块。不改正式源/测试/文档/Git、配置/Key/绑定/owner或286产物，不读真实会话/profile/生产日志DB，不启停/原生CLI/ACP/额外模型/Browser。
- 执行者交真实288完整裸JSON及README/代码/测试回执后暂停；Codex优先取只读交付摘要再独立看实际代码/反例，有问题直接修正并自检，不默认追加返修/回审。内核通过不等于真实采集/原生续用/桌面同窗/MCP增量派发或缓存效果通过。

## 已确认的整项机制

- 派发者按工作关联性选择同角色续用/新建；系统按上下文占用>=60%换窗，已取消固定10轮及任何轮数后备。新窗首轮完整介绍，续窗只任务与变化，协调输出和bridge均不重复固定包装/全量Hall。
- 允许DSH同类projectedTokens/pressureTokens/contextWindow估算；数值须标来源/采样/会话与模型，不把累计计费或缓存率当占用。建议每次投递前检查，不强停在途任务；未知不按0%，建议新窗；详细采集/异常/并发接线尚未实施。
- [最新需求与使用说明草稿](spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)已更新开发状态；手册仍标未上线，真实入口落地同片补齐选择/占用/换窗/恢复及人验。本首片无用户操作变化，不提前编造步骤。

## 已有结果和边界保持

- 287已独立实查、六组方案补正和9项针对性探针通过，结果2893原complete/11产物保留，已收取completed。见[287复核](spec/EXECUTION_SESSION_CACHE_REVIEW_287.md)；源码默认无续用接线、实际argv/profile/home与真实usage/收益未知不因开始本片而改变。
- 285管理账号只读查看及DeepSeek状态00bdcff/02c7692已加载人验；282/279/280/278原局部验证/人验保持。未重启API/宿主/角色或改绑定。
- 286仍普通中止：上次及本次派发前核为queued但paused，不恢复/收取/重用；原233份约8.78MB候选原位保留未集成。284接收内核关闭/三表保留，不删库表或启用上传。
- 日志按本机采集/诊断/导出/留存、跨设备手动转移；日志覆盖/全根留存与全入口21600预算待办保持，不开其它功能。角色/Key/模型/owner/启停权限、终端等待预算和原失败证据不改。

## 下一步与交接

- 当前仅288已派，不主动等待/唤回/重派；用户通知完成再取件。相关执行者暂停后由Codex独立实查/直接修正，必要验证/进度/Git收尾按同片授权完成；下一片先说明目的/范围/不变项/验收并获确认。
- 原生指标和会话适配、派发/MCP存档与增量指令分离、实机加载/页面验收仍待，不根据本次开始开发自动部署或迁移。每片先确认及人工里程碑门禁继续有效。
- 本轮正式仓库仅新增首片合同、更新PROGRESS/PROGRESS_HISTORY/PROJECT_BRIEF/DEVELOPMENT_ROADMAP及总需求；原产品源和既有未跟踪产物不改不清理。交接版本以最终HEAD为准，产品基线48526a7固定。
- 精确额度占比未读取，不作推断；不把派发/冻结自检当成开发者测试或独立验收。
- 派发准备自检通过：22冻结SHA及非文档正式源一致、6份UTF-8文档、10个新增本地链接、Git差异/范围与288创建回执，见`.tmp/execution-session-core-v1/coordination/verification.json`。本轮无产品测试/真实模型探针。

恢复指令：继续项目（恢复288当前授权和状态，不重复派发；用户通知完成后取件，不自动开启后续片）。
