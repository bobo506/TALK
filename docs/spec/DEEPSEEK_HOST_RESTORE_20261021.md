# DeepSeek原宿主恢复与单次普通启动

2026-10-21 21:10（Asia/Shanghai）。用户明确回复“允许恢复宿主并启动DeepSeek”，Codex按本次单角色授权恢复原宿主管理器，再通过普通入口启动一次。未修改产品代码、角色配置、模型、Key或原生HOME，未恢复286或派发新任务。

## 原因与授权

- 关闭超时补正版本`36107c6`已发布，128项自检通过；用户反馈“是关闭状态”，关闭状态页面验收通过。
- 用户随后19:47:59提交的start gen26从未claimed/reported，后续关闭使当前状态为gen27 stopped、无归属。只读检查确认原DeepSeek manager11612已不存在，未见替代宿主；旧health时间不能代表进程仍存活。该次启动请求没有进入原生模型执行阶段。
- TALK API入口已恢复，但角色宿主管理器并不随API恢复而自动启动。用户另行明确允许恢复原DeepSeek宿主并普通启动一次；其它角色、286暂停、原配置和不派新任务的边界保持。

## 实际操作

1. 只读核本人`agent:codex`、项目`prj_e8fe7066bbec`、DeepSeek原身份与绑定；保存配置/绑定/286完整行哈希及其它四角色基线。原API launcher22360/child22332保持，没有再次重启API。
2. 使用原入口`.tmp/legacy-role-page-control/deepseek-next/deepseek_member_entry.py`及原choice `rmc_3a5435e0e283`，核入口SHA256为`11c3cf955831d19fbd8005c4ba2f2549d5dcb62fd490c473a492ca89aaeb483e`，隐藏恢复宿主管理器。wrapper3284/manager18856；新宿主只处理`agent:deepseek`，恢复后先核就绪且没有接管旧进程或自动启动角色。
3. 使用既有人类操作身份向普通`/api/projects/prj_e8fe7066bbec/roles/agent:deepseek/service/start`提交一次请求。保存同一请求回执并观察，不重复提交start，不再调用已关闭恢复，也不直接写生产数据库。
4. 本次generation28，launch `6ca1765d-7fd0-4cfa-b3f6-a5179b32c8fa`，新实例`ins_ffc603d6fc88`、bridge22812。真实OS父链为22812→18856，符合本次manager创建的新Popen。

## 验证结果

- 21:06:41公开状态为running/ready，ownership=true、无错误；同一实例idle、current_task_id为空，running任务数0。
- 同一实例真实心跳从13:05:39.129391 UTC推进至13:06:39.185264 UTC，间隔60.055873秒；manager health同步更新至13:06:39.617495 UTC。已验证跨工具调用后的周期心跳，未以首次ready或旧health代替持续上报。
- 配置、全部绑定、286完整行哈希及其它四角色记录与操作前一致；286仍queued/control_status=paused，没有领取/实例/租约。其它角色未启停，没有新任务派发。
- 原模型alias `deepseek-flash`及reasoning `max`保持，没有额外原生模型探针或任务执行。本次验证宿主、普通启动与真实心跳，不扩为模型调用或会话机制上线验收。
- 本轮只有操作记录及指南更新，无产品代码变化；不重复运行已通过的128项关闭超时自检。文档另做UTF-8、本地新增链接及Git差异检查。

原始只读诊断见`.tmp/deepseek-start-diagnostic-20261021/diagnostic.json`；本次证据见同目录`restore/`内的`preflight.json`、`manager-start-receipt.json`、`manager-ready.json`、`start-request.json`、`role-ready.json`、`heartbeat-first.json`和`verification.json`。原关闭恢复及失败证据保留在`.tmp/deepseek-stop-diagnostic-20261021/`，不覆写、不提交临时产物。

## 页面验收与后续边界

刷新正常TALK入口的角色页，DeepSeek应显示“启动成功”，任务仍为空闲；本次启动页面结果待用户确认。上一片“已关闭”的人工验收已经通过，不需要再次执行关闭或重复启动。

只启动TALK API不能恢复所有角色宿主。若普通启动请求无人领取，应先核原宿主管理器与现有动作；获授权恢复对应原宿主后，再观察或按当前状态执行普通启动，避免重复请求。本次未实现宿主开机自启，也未验证注销、重启或Codex沙箱服务停止后的持续驻留。

290已收取及离线会话机制边界不变，真实采集加载、原生续用、任务/MCP/API接线和ACK存储仍未完成；Kimi暂停新派发、286和日志/21600待办保持。后续每片先确认，本次结束后不派新任务。
