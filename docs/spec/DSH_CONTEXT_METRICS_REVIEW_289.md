# 289 DSH上下文采集/适配首次独立实查与集成

更新：2026-10-20 23:22（Asia/Shanghai）。结论：首次候选经Codex独立实查、直接补正和自检后集成，289正常收取completed。原生采集接口/适配及离线链路通过；未加载运行中的DSH，真实占用仍未知，不能称会话机制上线。

## 身份、基线与原件

- 用户通知“289好了”后取完整必要摘要，MCP本人agent:codex/agent；DeepSeek `ins_00acba0f8a9b`/PID12284为idle、无当前任务，确认暂停后接手。页面开发要求仍旧交叉复核，以AGENTS当前分工优先，不改页面、不返修/唤回或派Kimi。
- 289 creator `agent:codex`、target `agent:deepseek`、project `prj_e8fe7066bbec`。结果2895是合法talk-delivery-1、任务号匹配、原complete自报；收取前succeeded/submitted。原文4726字符，两页按稳定SHA拼接，SHA为`837a33ca37377c5b274bd1d02061ba5ab769d6bb12eabc949a464296b9a70173`，与本地JSON语义一致。自报不作为独立业务结论。
- 产品基线`15f77b279993dbf952291f8f8d141756cd07768c`，派发记录a058df9。15份开发原件全部原位保留、逐SHA保持；22份项目公开冻结/29份原生冻结共51份一致，无冻结区pycache。原Node --test runner的spawn EPERM失败回执保留，不伪称runner已通过。
- 正式新增两模块`bridges/dsh_context_capture.mjs`、`bridges/dsh_context_metrics.py`及两对应测试。既有288/bridge/host/配置/模型绑定/权限及生产路径不变；新模块无生产调用，不启停、无DSH应用/CLI/ACP/模型或真实会话/日志/数据库/凭据读取。

## 独立发现与直接修正

1. **来源序号没有约束在快照cut及有效顺序内。** 原Python只比较时间，能接受cut之后的来源，或同毫秒下配置/容量晚于压力、预计值早于压力的矛盾序号。现逐项限定来源<=cut，检查配置→容量→压力→预计值顺序，同序号须同时间，旧容量不能冒充当前配置的容量。压力来源也明确检查年龄。
2. **优先字段可通过矛盾状态被丢弃。** 原missing状态即使带显式非法projected值仍会回退到低pressure。现校验状态/值/来源一致性；非法状态类型转为unknown，不能抛未处理TypeError；producer只接受已支持版本。
3. **错误审计回显原始输入。** 原blocking_issues会整串复制异常文字，未验证宿主source也被输出。现只留阻塞数量/受控原因，宿主source通过校验后才记录，不回显原始异常或非法标识。
4. **原生身份/投影读取异常与旧回调边界。** 原部分id/header/seq读取可能直抛异常；挂载前的projection回调、session事件缺口/冲突重复未可靠阻止。现将原生读取失败转unknown，绑定初始cut并核对提交范围，session回调须对应原生eventAt同一事件、连续推进；保多会话隔离与解除监听，补合法Unicode检查和mount入口测试。

两端均保持projected优先、非法不回退、原始整数阈值、独立来源与无历史重放。原生session/event和disposed参数、projection onChanged/snapshot、eventAt及seq语义均对照冻结源码独立读取核对。仍不把snapshot的统一cut冒充同次请求原子采样，也不把caller-attested的home/绑定当作本模块独立查证。

## 验证与证据

证据根`.tmp/dsh-context-metrics-v1/independent-review289/`，原交付仍在deepseek/：

| 检查 | 结果/回执 |
| --- | --- |
| 原候选复跑 | 原Node27、Python35全部通过；`original-node-tests.log`、`original-python-tests.log`。Python使用正式副本仅适配测试路径和临时输出，不改原模块行为 |
| 独立初始反例 | Python初始6组形成10个失败断言/子例和1个TypeError；Node新增4项为3失败/1通过；`before-python-fix.log`、`before-node-fix.log`，不覆写原失败 |
| 修正后自检 | Node34、Python44、原288的106项全过，零失败/零跳过，共184项；`final-node-tests.log`、`final-python-tests.log`、`final-288-tests.log` |
| 独立反例复跑 | 最终9组Python探针通过，并检查unknown最终进入内核新窗完整；`after-independent.log` |
| 跨语言/挂载接口 | Node真实执行模拟原生服务调用、mount事件签名/解除、采集输出→Python→正式288；覆盖59.9/60/0、非法/缺失/过期与忙通道，不是只复制三个数 |
| 原件/冻结/回执 | 15原件/51冻结SHA、MCP JSON、现有产品不变、标准库及无生产Python导入检查通过；`verification.json`、`original-hashes.json`、`mcp-original*.json` |
| 文档/范围 | 11份UTF-8文档、28新增本地链接、两Python文件AST与Git差异/范围通过；`document-verification.json` |
| 收取 | 23:21:56正常collect，workflow completed、结果2895保持；`collect-receipt.json` |

以上独立发现后由Codex直接修正，修正结果称自检，没有追加他人独立回审。Python测试已改为加载仓库正式模块，跨语言文件使用每次独立临时目录，不依赖或覆盖原证据；未跑无关整套产品回归。原27/35自报和其not_run限制不追改。

## 当前限制及下一片建议

采集器未加载到原角色，原生版本/home/有效插件及运行中数值仍未核实；公开冻结版本不证明当前进程版本。native snapshot可能在内存materialize所有unit；采集器不直接修改或持久写入原生会话。原生provider/model与TALK配置标识若不同，后续接线须先建立可核关联，不通过任意改绑定/重贴标签绕过校验。

当前headless工具客户端T仍未知；bridge21600与工具超时不同，本片没有主动wait、取消/同连接排队或终端加载验收。原生续用、锁ACK/投递幂等、任务/MCP存档及页面/生产加载均未实现，不声称缓存/费用收益。

已同步[调用说明](../guides/DSH_CONTEXT_METRICS.md)、[本片合同](DSH_CONTEXT_METRICS_SLICE_2.md)、[总体需求](EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)及进度/排期/手册未上线标记。下一片建议先只读核验实际DSH启动入口、版本、有效插件/native home和采集器挂载位置，形成具体隔离联调/加载方案；不启停、不调用模型或读取会话正文/凭据。该片尚未确认/派发，不由289收取自动开启。
