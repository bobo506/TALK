# 287执行会话/缓存只读核查独立复核与补正

## 结论与范围

用户明确确认的只读方案片已完成首次交付独立实查。原交付的定位和基本方向可用，计数、收益及隔离边界存在问题，Codex已在DeepSeek暂停后直接补正方案并自检；接受的是补正后的方案，不是会话复用或缓存优化上线验收。

任务287，project `prj_e8fe7066bbec`，creator `agent:codex`，target `agent:deepseek`；原结果2893自报`complete`，提交时runner `succeeded/submitted`。MCP结果与本地原交付JSON一致，正文SHA-256为`1ff4ff66926e55a54882e077880aa5b128a63d743304fb6eb789a6e8ca99c3a4`。开始核查时DeepSeek原`ins_00acba0f8a9b`/PID12284上报`idle`、无当前任务；本轮未重新派发或唤回。2026-10-20 20:27:10（Asia/Shanghai）收取后为`succeeded/completed`，结果仍2893；回执保存在`independent-review287/collect-receipt.json`，原自报不追改。

产品基线`510c9c42311e5c4784d8d2227211dc419ee78853`，派发文档提交`ac6fdf5`。原11份交付、首次自报和失败/偏差描述保留在`.tmp/execution-session-cache-audit-v1/deepseek/`；独立证据与补正副本在`independent-review287/`，未修改原件。

## 可确认的事实

- 冻结bridge的默认路径每次调用新建CLI进程，不保存原生session id，也没有续接状态表；Kimi/Codex默认命令亦未注入resume。自定义命令/profile不在本次材料中，不能外推覆盖其行为。
- 已安装`@deepseek-ai/dsh` `0.1.5-rc.2`默认headless使用随机session id、提交一个任务并flush；其startup不提供resume参数。默认持久化插件启用时会保留会话，保存会话不等于下一任务续用。
- 预检补丁仅在指定条件下追加到预检命令；本片未读实际`.talk/`补丁和有效profile，不能证明本机当前预检已经完全临时化。实际argv/prompt transport、native home及profile覆盖继续未知；没有借独立复核开启S0生产取证。
- 默认DSH适配器存在input/output/cacheRead/可得total/reasoning用量字段，headless默认输出和bridge没有结构化usage接线；真实命中率、费用及复用收益没有证据，本片均未测。
- 合成输入显示任务正文和Hall历史在预检/正式提示中重复出现，原字符/字节测量可以复现；它们不是token数或供应商缓存命中证据。

## 首次交付发现与直接补正

| 组 | 原问题 | 补正与证据 |
|---|---|---|
| R1 默认源码/运行事实 | 部分摘要将默认持久化、预检临时化或未续接写成当前实机确定事实，限制段才说明argv/profile未知 | 每项结论明确默认分支、插件启用条件及运行未知；实际有效配置须后续单片确认取证。headless `lib/index.js:134/163`、`startup.js:20`；bridge `resolve_task_preflight_command` |
| R2 usage口径 | 把重试写成同turn/step替换；total/reasoning被列为不重叠bucket；未说明投影默认0丢失缓存可得性 | 同结算修订替换；retry-started保留totals并开启新attempt累计，失败attempt可得usage也可能计入。total汇总及reasoning细分不能再次相加；缺失与显式0分开，不能用聚合默认0证明未命中。provider `mapUsage`、token-meter `bucketsFrom`/`tokenUsageProjectionDefinition` |
| R3 续接收益 | 声称同任务修复续接收益明确，可避免重发原prompt | 仅避免应用层再次追加整段正文；原生buildRequest仍`session.deriveMessages()`生成历史，恢复可能带上前次输出/工具结果。不得推断输入或费用下降，须授权真实对照；当前默认off。agent-loop `lib/index.js:1166–1218` |
| R4 隔离/路径 | 哈希字符串直接相加；缺attempt/execution/launch/阶段约束；把同目录大小写/短路径变体当异工作区反例 | canonical JSON命名空间；校验task/attempt/execution generation/service launch/正文/阶段。可证明同一目录的别名为正例，真正异目录拒绝；未知目录身份拒绝。重启默认失效旧映射，不据PID或末尾turn/end重建owner |
| R5 锁冲突 | home独占要求与“锁失败继续同home fresh”矛盾；自建锁被当成可保护外部桌面 | home级锁失败只能等待/拒绝；session级冲突另建需明确存储并发合同。未合作的桌面不受自建锁保护，需先证实home隔离/独占；不抢占、不复制认证、不放宽既有owner守卫 |
| R6 只读偏差 | 首次纯函数导入曾在冻结目录生成pycache，执行者清除后仍笼统标边界pass | 历史偏差如实保留，不称全程白名单零写入通过。独立核对42份冻结文件字节/哈希一致、现无pycache；正式产品未改。Codex自检用`python -B`及禁止bytecode，不覆写原件 |

R1–R6是首次交付的独立实查发现；补正副本和最后文档是Codex直接修正后的自检结果，没有追加他人独立回审。

## 补正后的最小方案

1. 当前继续每个TALK任务独立交付、完成及收取；跨任务复用和同任务修复复用均保持off。方案提出可能的后续入口，不写成产品参数已存在，不因方案验收自动修改默认值。
2. 如后续确认测量，应保留每个请求/结算/attempt、阶段（预检/正式/修复）、可得性与配置版本。相同结算修订去重，真实retry attempt相加；无usage、缺cache字段、不完整流和未观测失败均不能填0或宣称完整计费。
3. `inputTokens`在cache字段缺失时按适配器退回prompt总量，不能称已证明的未缓存输入。命中占比须有有效prompt侧分母及cache可得性；有未知请求时保持整体未知，或明确已知子集覆盖率。total/reasoning不重复相加，provider未提供cacheWrite不能凭投影0证明未写。
4. 任何续接候选先校验规范序列化的项目/成员/真实工作区/runtime及runner/实际native home命名空间/配置绑定与有效权限/提示基线，再校验task/attempt/execution/service launch/正文/阶段。模型绑定只证明配置事实，不冒称实际后端版本已核验。
5. 预检永不进入正式复用表。未来门禁修复只读当前执行新增输出序列，不重放旧TALK动作/工具副作用；失败、取消、超时或重启使候选失效。map、PID及单个turn/end都不能授权接管旧进程或所有权。
6. 先证实实际home隔离和约定粒度的独占；home级锁失败不在同home新建写入。外部入口不合作时无法凭自建锁证明独占，保持关闭，不为了续接引入自动接管。
7. “续用会话”“稳定请求前缀”和“缓存命中/成本改善”分开验收；应用层少追加正文不等于实际少输入，真实优化只按另获授权的对照数据判断。

完整补正副本为`independent-review287/corrected/report.md`及`acceptance.md`；本文件为随Git保存的复核结论与方案约束。

## 验证与限制

- 独立重核42份冻结SHA、14份安装源码SHA、102处引用范围/锚点及引用源哈希；复跑纯函数合成指标，与原产物一致。
- 原MCP消息2893与本地交付包语义一致、正文哈希匹配；冻结workflow校验真实task_id=287通过。原11份交付均未被覆写。
- 9项独立纯函数/静态探针全部通过：同结算去重、修订替换、retry累计、失败attempt累计、缓存缺失被投影抹为0、reasoning不可重复求和、非法total保留缺失、cache优先字段及请求历史装配。只提取已检查源码纯函数在隔离VM执行，不导入/运行DSH入口，不触发模型/网络/原生会话。
- 证据：`integrity-results.json`、`usage-probe-results.json`、`correction-index.json`、`original-artifacts.json`与`mcp-original.json`。未跑产品回归；本片没有产品代码变更，不把这些检查写成真实运行器、实际缓存或完整日志验收。
- 补正后收尾自检：6份正式文档UTF-8、7个新增本地链接、Git范围/差异检查通过；原11份产物和42冻结源保持，287收取回执一致，证据`final-verification.json`。
- 未读真实会话/profile/Key/环境值/数据库/生产日志，未启停服务/角色、未改模型绑定或owner、未执行额外模型/ACP探针。286/旧候选、Kimi额度暂停、本机日志和21600预算待办保持；无用户操作变化，不新增手册步骤。

## 下一片建议（未批准/未派发）

建议S0只读补齐当前DeepSeek的脱敏有效argv/prompt transport、预检禁用行及SHA、实际native home和无凭据的有效插件开关，以闭合默认源码与实机接线之间的差距。验收应做到可关联当前角色/实例/launch，公开结果无正文/Key/完整环境；不启动模型、不启停服务、不修改配置，不用dump初始化原生profile。

S0涉及本片未开放的运行证据，只能在用户确认具体取证范围后实施/派发。usage采集、同任务续接、跨任务实验均为后续建议，不能由287收取或旧“按原计划继续”自动开启。
