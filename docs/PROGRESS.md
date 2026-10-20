# Project Progress

Updated: 2026-10-20 21:21（Asia/Shanghai）。用户明确取消固定10轮，改用上下文占用达到窗口上限60%换新会话；灵活选择、首轮完整/续轮增量/换窗恢复保持。已同步需求/使用说明草稿和手册未上线提示，TALK尚未采集相关指标或实现续用；287已收取，下一取证/实现片仍待确认。

## 最新需求：首轮完整、续轮增量、换窗恢复

- 派发者按工作关联性决定同角色续用/新建执行对话，系统按上下文占用>=60%换新窗，取消固定10轮及后备轮数。新窗首轮带当前完整任务介绍，续轮只带任务与变化内容；协调输出和bridge不能重复固定包装或全量Hall历史。
- 占用使用DSH同类projectedTokens/pressureTokens及contextWindow，可含估算，TALK尚未采集；桌面实机值未读取。建议下条指令投递前按原始比例判断，不强停在途任务；缺失/过期/错会话模型保持未知、建议新窗，不填0%。采样/异常/并发和配置入口待实现片明确，60%不称实测最优。
- [机制需求与使用说明草稿](spec/EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)已落盘；[用户手册](guides/USER_MANUAL.md)说明当前没有该操作入口，真实上线同片补齐选择/上下文占用及未知提示/换窗/恢复步骤和人验。不能把草稿写成已可用。
- 新方向允许同功能多个独立TALK任务共用执行会话，旧287同任务修复候选不作产品限制；任务账本/权限/隔离与owner守卫保持。记录需求不授权S0或实现派发。

## 当前完成：287只读核查与补正

- 本人MCP实测`agent:codex`/agent、lead、project `prj_e8fe7066bbec`。开始实查时DeepSeek原`ins_00acba0f8a9b`/PID12284上报idle/无当前任务，已暂停；未重派或唤回。页面旧交叉复核要求不改，按AGENTS最新分工由Codex独立实查/直接修正，Kimi额度暂停保持。
- 287原结果2893为合法complete自报；原11份交付和原始MCP结果保留，不追改。接受的是补正后的只读方案，非当前产品续接或缓存优化验收。详[287复核与补正](spec/EXECUTION_SESSION_CACHE_REVIEW_287.md)和[原切片合同](spec/EXECUTION_SESSION_CACHE_AUDIT.md)。
- 独立核对42冻结/14安装源码SHA、102引用及源哈希、原合成测量复现、MCP/本地交付一致及真实287校验；9项独立纯函数/静态探针通过。均为静态/合成，不是模型或产品回归。
- 六组补正：默认源码与实机证据边界；retry累计/缺失cache/total与reasoning口径；续接不保证少输入；task/attempt/execution/launch与目录身份隔离；home锁失败不在同home fresh；历史pycache短暂写入冻结区如实记偏差。严格全程零写入不标通过，现42源一致且无pycache。
- 补正方案及原证据索引在`.tmp/execution-session-cache-audit-v1/independent-review287/`；`corrected/`是Codex副本，原`deepseek/`未覆写。`collect-receipt.json`确认287 completed，结果仍2893。

## 核查结论与未知

- 默认bridge/headless每次新进程/新会话，未保存原生session id或接跨任务续用。原生持久化仅证明保存，默认DSH usage字段存在但bridge无结构化采集；实际argv/profile/预检补丁/native home未读，不把默认源码外推为当前实机事实。
- 实际缓存命中率、费用/收益保持未知；少追加应用层prompt不能证明模型少输入，恢复仍可能带完整有效历史。缓存字段缺失不填0，retry不同attempt累加，total/reasoning不重复求和。
- 本轮没有产品/生产修改、启停、原生CLI/真实模型/ACP探针、Browser或真实会话/认证/profile/环境值/DB/生产日志读取。用户手册无操作变化，不新增步骤。

## 下一步（未确认/未派发）

按上述新需求重新给出具体下一片建议，先说明目的/范围/不变项/验收并获用户确认。S0只读补齐DeepSeek实际argv/transport、预检补丁、native home/有效插件开关仍是候选，未执行/派发；不得把需求澄清或写手册当作新取证/实现授权。

usage侧车、同任务修复续接、跨任务实验继续是后续建议，各片另行确认。日志导出覆盖/全根留存和全入口执行预算21600待办保持，不借本片提前宣称完成或批准实施。

## 既有完成与边界保持

- 285管理账号未入群只读查看已加载且人验；仅human:bobo，读200/写403，不自动入群，原162 Python/81 Node证据保持。
- DeepSeek状态补正00bdcff/170相关自检、02c7692普通加载及页面人验保持；未重启角色/API或更改绑定。282/279/280/278已有局部验证/人验不代表日志整项完成。
- 286上次核queued/accepted但control_status=paused、无实例/结果、未收取；233份约8.78MB旧候选原位保留未集成，不恢复/重用。284接收内核关闭、三张表保留，不删库表或启用上传。
- 日志仍按本机采集/诊断/导出留存，跨设备手动转移；HTTP接收/来源/outbox不列当前必做。角色/Key/模型/绑定/owner/启停守卫、终端等待预算不变。
- 每片先获明确确认；已授权片内复核/直接修正/自检/进度Git收尾不重复询问。默认派发后结束，由用户通知取件；Kimi及其它Kimi角色暂停新派发，直到用户明确恢复。

## 交接

- 产品基线510c9c4、287收尾795edb7、机制文档329a44d；本轮仅更新会话机制需求/手册/PROGRESS/PROGRESS_HISTORY/PROJECT_BRIEF/DEVELOPMENT_ROADMAP，交接版本以最终HEAD为准。原源码与未跟踪产物不改不清理。
- 287补正时6份UTF-8文档、7个新增本地链接、Git差异/范围及收取回执自检通过，见independent-review287/final-verification.json；此为287历史证据，不当作本轮新检查。不把Codex修正后的自检称为他人独立复核。
- 已确认287方案及本轮新交办机制要求；S0及所有实现/模型实验未批准、未派发。精确额度占比未读取，不作推断。
- 上轮机制文档6份UTF-8/7个新增链接自检为历史证据，见`.tmp/execution-session-window-requirements/verification.json`，不当作本轮新检查；本轮不运行产品测试或真实缓存对照。
- 本轮60%规则更新的6份UTF-8文档、5个新增本地链接、Git差异/范围、固定轮数移除及手册未上线标记自检通过，证据`.tmp/execution-session-window-context60/verification.json`，含3份安装公开源码/说明哈希。

恢复指令：继续项目（恢复60%上下文阈值、已取消十轮及首轮/续轮机制；287已收取，不重复派发，不自动开启S0或实现）。
