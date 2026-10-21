# 292完整会话链路的实查与验收

2026-10-22 01:06（Asia/Shanghai）。DeepSeek首次交付后已暂停；Codex独立检查实际19份候选，发现缺口后直接补正并自检、集成及实机验证。修正后的测试属于Codex自检，未称他人独立复核。292于01:03:04收取为completed，原结果2898及SHA `ef617e7fb6f02ac692fbd803c3d9176b9e0c80d74e1ca35d095cfb46eed3f19b`保持。

## 首次交付与补正

原始候选/证据及本地交付均冻结在`.tmp/execution-session-usable-v1/independent-review292/original/`；80项目/57原生冻结及当前安装57源SHA核对通过，实际候选路径恰19项，不接纳额外文件。原候选complete是执行者自报，原先未生产加载，不能作整体完成结论。

实查复现并直接补正的主要问题：

1. 执行分支跳过既有模型预检；恢复原预检/澄清及非持久化隔离，仅预检副本补冻结基础合同，正式续轮仍增量。
2. 任务租约丢失不及时取消、父取消可能遗留子执行；沿原租约守卫中断并收束子执行，通道租约丢失也取消原生调用。
3. 原生query虽读当前projection，规划仍用上次sidecar快照；改为query挂载采集器并从当前registry/cut输出经适配器校验的新快照，保留原始来源时间，不把观察时间冒充来源时间。
4. 运行指纹只扫描前32个权限事件、插件名取错属性且漏推理配置；改读原生有效sandbox/approval/preset、部署默认、真实插件名及reasoning selection。未知权限不能授权续用，query与投递之间再次比对指纹。
5. 同任务尝试可在查到重复回执前再次调用模型；新增持久尝试预留，重复/遗留尝试在再次投递前拒绝，不自动模型重跑。
6. 续轮送达不明仍可能active，计数、回执、清单与尝试状态多次提交；未知送达停用旧窗，确认计数/回执/尝试/快照单事务CAS，故障回滚不留下半个确认。
7. 回执冲突漏查代次/修订/结果等字段，摘要指标取错字段，状态容许任意嵌套值及跨任务状态；补严格回执/摘要/状态类型及任务关联，未确认结果不再自称“未计数”，未知轮次不报成功。
8. 异常回包路径先赋值后校验、清理目录未经边界核验；先验证路径，清理只允许本次受控spawn子目录；未验证版本拒绝，当前只承诺安装版`0.1.5-rc.2`。
9. 续轮未保存当前开发要求的独立审计，标题子串可能阻止附加要求；REST/SDK/MCP统一由服务端首基础合同附要求一次，逐任务私有审计，要求变化后拒绝旧基础引用，不改历史。

## 验证结果

- 原候选独立回归：522 Python中521过；35采集/3 runner Node过。唯一失败为原基线已有的角色清单长度断言`1523 < 1500`，未修改无关角色清单实现或删断言。
- 修正后完整相关组：533 Python中532过，仍同一已知长度断言；35采集/4 runner Node过。最后调整后的定向164 Python及5 runner Node全部通过，涵盖新增API审计/状态、runtime边界、整个CLI、SDK及MCP接线。新增探针验证重复任务不调两次模型、未知送达停用、冲突ACK、当前query优先、两类租约中断、可靠低值超过10次、恢复不清零、事务注入回滚、未验证错误路径不写出等。
- 安装版DSH+假模型：14次真实投递，59.9%同native ID，60%下一次不同ID；缺数1..10同ID计数1..10，第11不同ID且完整首轮。读取query不调用模型。4个独立TALK任务的SDK/MCP→REST→claim→bridge→DSH→ACK→状态/结果读回通过，同窗、force_new、首轮/增量与跨发起者引用拒绝均验证。
- 第一次隔离API复跑因复用夹具硬编码18090失败，已保留；v2改用自身fake服务端口后通过。原记录中的预备配置/目录错误也保留，没有包装成产品失败或通过。

## 实际加载与3条真实任务

原manager18856存在、DeepSeek空闲、无running任务后，通过普通human stop关闭DeepSeek；仅集成19份白名单源码/测试。沿原API launcher的正常stop机制重载，新增`execution_session`、`execution_session_base_text`、`execution_session_state`、`execution_session_audit`四个可空列。迁移后292条历史旧列逐行哈希保持，新增列均NULL；随后只允许292正常收取改变流程字段。

API就绪检查曾把venv包装PID6320误当实际launcherPID，报一次未就绪；只读核实其子launcher2624和API子10876的父子关系、创建时间及新schema通过，没有重复重启或强杀。原manager仍18856，普通start后DeepSeek generation30、launch `205e7f05-1b0c-4e96-becf-8cbb154f75a6`、实例`ins_7a91214893c6` running/ready。

首条真实创建因旧项目`project_root_path=null`被422拒绝，未建任务、未调模型。核本地`.talk/project.yaml`项目ID一致后，仅登记本项目根为`D:\claude-test\TALK`；原profile读写仍human-only，其它项目字段不变。该必要元数据初始化已明确记录，不能称全部项目配置从未改变。角色模型/Key/HOME/绑定、286暂停及其它角色保持。

| 实际任务 | 原生ID | 事实 |
|---|---|---|
| 293 | `session-729a2e89-716d-4bd7-831f-005a36865ea3` | 完整首轮，计数1 |
| 294 | 同293 | 只发增量，实际投递前指标known，计数2；模型成功回想首轮验证码 |
| 295 | `session-8ac3ad08-679a-4211-8ecc-389e382a7539` | force_new，新窗完整恢复，计数1；模型再次返回基础验证码 |

三条均succeeded/completed并收取；三个真实ACK均已计数，sidecar无助手正文、通道已释放，无在途任务。真实容量均1000000，293结束projected17063、294结束17501、295结束17232；不把这些低占用结果当真实60%压力试验。60%/缺数10/11来自受控原生边界验证，未以烧token方式触发真实上限。

## 状态与剩余门禁

当前DSH链路已工程接通并能实际使用，[实际入口与说明](../guides/EXECUTION_SESSION_USAGE.md)已给出。现有Codex旧MCP连接尚无新参数，需重连刷新目录；SDK/API已可直接使用，fresh MCP schema/dispatch已隔离验证，不改当前桌面MCP配置。其它runtime不冒称支持，桌面GUI显示/手动续写和缓存/费用收益未验；headless实际工具上限T未核，不启用主动长等待。

完整功能当前等待项目管理者人工里程碑验收；在此之前不派宿主统一启动或其它新片。286/Kimi额度暂停、日志/21600等待办保持。本轮没有修宿主自启动或自动解除任何owner。

完整证据索引：`.tmp/execution-session-usable-v1/independent-review292/`的`preparation.json`、`checks/`、`final-targeted.txt`、`final-runner.txt`、`native-replay/`、`api-replay-v2/`、`integrated-manifest.json`、`production/`及`collection-receipt.json`。原始失败证据不覆盖，生产新任务引用与交付结果保留。
