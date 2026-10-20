# 查询恢复后轮询错误状态残留补正

日期：2026-10-20 16:32（Asia/Shanghai）。**代码及针对性验证完成，现有DeepSeek进程尚未加载。** 用户在285人验后对“先处理DeepSeek错误残留，再回日志B2b”回复“好的”。本轮按已交付问题直接修正规则由Codex补正并自检，不新派任务或调用模型，Kimi暂停派发保持。

## 范围和实现

- 基线`54101f8`，本人MCP为`agent:codex/agent`、项目`prj_e8fe7066bbec`、业务角色lead。DeepSeek无current_task_id，项目/全局queued及running为空，原执行者无在途开发，Codex单方补正。
- 原worker查询成功只记录恢复日志，实例error随30秒心跳保留。只改`bridges/cli_bridge.py`，新增`tests/test_queue_poll_status_recovery.py`及必要文档；不改服务端90秒新鲜度、权限/Key/模型绑定/DB/任务和启停协议，不手写旧实例idle。
- 查询错误上报、恢复及受管心跳共用状态锁。进程内来源和状态版本限定只恢复本轮询自己的最新错误；执行锁/当前任务/busy/其它来源error保持，普通任务/消息/offline上报即使文案相同也使旧恢复失效。
- 真实查询再次成功才能恢复idle并清当前last_error。错误上报失败仍保留本地来源，恢复PUT失败下次再试；状态失败不冒充查询失败或增加连续失败计数，取消继续传播。
- 正常成功不新增网络状态请求；受管和非受管适用，非受管不加心跳。旧内部worker调用者不传新可选回调时保调用合同。

## 验证

新增首5项使用真实run_bridge/worker、隔离假客户端，旧代码3失败/1错误/1通过：受管及非受管不恢复、日志关闭且错误上报失败后worker退出、恢复PUT不重试。首次修正剩1失败，原因是新增诊断辅助漏`task_id=None`，已修正；原日志保留。

最终新14项覆盖busy/无任务号执行error、其它来源同文案、后续任务、锁等待、重复错误、offline、取消、重试及真实诊断计数。联合原心跳/轮询/CLI/正常停止共**170项Python通过，0失败/错误/跳过，3.813秒**，属于Codex自检。没有生产故障注入、真实CLI/模型调用或Browser，不把隔离验证当实机加载。

证据`.tmp/queue-poll-status-recovery/`：6份原文件冻结/SHA、`first-reproduction.log`、`first-fix.log`、`fixed-reproduction.log`、`expanded-tests.log`、`targeted-tests.log/json`及只读`loading-plan.json`。

## 已准备的单角色正常加载

16:32只读核DeepSeek gen21、实例`ins_39ba69bf6dfe`/bridge12612、原manager11612及创建时间，原归属在、can_stop=true；全局无在途任务，其他四角色服务stopped、API原进程保持。本轮尚未启停，新代码未进入旧bridge，error/unknown尚不能记恢复。

实际加载只需原human入口对**单个DeepSeek普通stop→原宿主确认旧Popen正常退出/释放→普通start**，沿原Key/ID/模型/工作目录及manager加载新bridge。实施前重核无任务/原世代/进程/归属/绑定；停止或归属不收敛则停止，不强杀、清owner或接管。不重载API/宿主、不启动Kimi或原已停Codex，不派测试任务/调用模型。加载后核新实例/原父链、running/ready/idle、两次新鲜心跳及其它角色/API/绑定保持，再由用户确认角色页。

按[AGENTS部署门禁](../../AGENTS.md#开发节奏与确认规则)“但遇到产品方向、破坏性接口/数据变更、部署/权限风险、重大用户体验分歧时，必须先确认”，本次实际角色加载另行确认；代码/验证/进度/Git先收尾。日志B2b本轮不派发。
