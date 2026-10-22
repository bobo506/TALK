# Project Progress

Updated: 2026-10-22 17:37（Asia/Shanghai）。用户允许验收额度，明确“只要不给kimi派发任务”。已完成K3及旧K2.8原账号各三轮原生验收、原API正常重载；没有创建或派发任何TALK任务。三个Kimi仍停止，常规派发暂停。本片按该授权收尾，不开下一片。

## 当前交付

- 身份agent:codex/agent、项目prj_e8fe7066bbec/lead。用户指定当前Codex直接实施/验收，不派DeepSeek/Kimi；全部称自检。产品提交6f1a293已推送，证据根`.tmp/execution-session-kimi-v1/`。
- K2.8/K3共用kimi-code适配，按角色/模型/请求者/工作线/HOME/配置权限/服务代次/基础合同隔离。API/MCP/SDK元数据、领取前合同/续轮预检、正式runtime分派已接线，首轮完整/续轮增量/新窗恢复、可靠60%/条件十次使用原内核。
- Kimi2.0.2首轮原Agent创建、续轮明确session恢复并核原模型/工具/subagents；正式prompt与上下文消息同ID/SHA双证明计数。首轮先预留未知ID，再一次CAS绑定真实ID，ACK/计数原事务归并。未知/重复不重跑；送达后失败仍计数，预检/工具/自动介绍不计。
- 上下文数取原生token_counting，容量取精确模型配置，输出maxTokens不当容量；非法/未来/配置冲突不兜底，读数恢复不清零。sidecar不存新增助手正文/凭据，Windows argv超限明确拒绝。

## 验证与实机加载

- 开发阶段338项相关Python通过，最后收紧未来时间校验后Kimi29项定点复验通过，不叠加计数。真实CLI配本地假模型21轮/21请求通过，证据`native-integration/b27d4189/`，含K3/review兼容性、K2.8/tools、60%及受控隐藏指标10→11。生产K3原档实际为tools，实机保原档，未改权限。
- 用户允许后只读核原human入口：两个目标stopped/无owner/can_start；不启动接单bridge。原K3及旧K2.8均保原独立HOME/登录、精确alias及tools档，通过产品通道/独立sidecar/内存用例直接三轮。用例编号未写生产任务表，没有派发/领取/收取。
- K3前两轮原生ID session_20efd6a4-9a46-4f9b-843e-95fd7d36b08c，计数1→2；第3新ID session_5aeefb96-e6b3-4aaa-982e-fd6a9c35eeba，计数1。K2.8前两轮session_5d72aa7a-c3a3-4602-9035-c80362406be6，第3新ID session_4418b8b3-a7ae-4d92-9c06-814ee14ccff1，同样计数1→2/1。
- 两款模型续轮未重发暗号/基础标记仍返回“松涛38 / 白鹭76”，新窗完整恢复“白鹭76”。6次真实llm.request精确模型/alias、6条directive SHA均匹配，六尝试confirmed、零通道残留、六个原生进程均退出，无工具调用。用量分别6962/7430/6887与7025/7506/7167，容量均1048576，属于低占用；60%/10次仍为受控边界证据。
- 原API沿已核launcher的stop.request正常重载，新launcher18580/child10600，健康及创建时间通过；未强杀、启停角色或解除owner。三个Kimi仍stopped/无owner，原DSH/Codex代次/实例及模型/Key/权限保持。
- 302条生产既有任务逐行SHA、原配置/绑定、五角色记录及286全文/暂停保持，TALK新增任务0。原普通沙箱Key读取失败保留；本次按授权经审批，仅用同一原Key内存认证做只读核验及正常API加载，不换凭据/登录。
- 证据`.tmp/execution-session-kimi-v1/account-validation/`含readiness、逐轮结果、原生stdout/stderr、sidecar、模型请求审计、api-reloaded与final-verification。产品代码本轮未改，338项证据保持，不重复模型探针。

## 当前边界与Git收尾

- K2.8/K3共用适配的开发、自检、原账号原生验收及API加载完成；按用户要求没有生产TALK任务派发/领取/收取实测，不冒称该链或人工验收通过。另一K2.8成员未单独做本片实机；当前不启动任何Kimi服务或恢复派发。
- TALK页面不改；286、日志手动跨设备/全根留存、全入口21600及宿主统一启动排期保持。MCP客户端T未重测，660000仅模板，不主动长等待/自动唤回；任务21600与Windows清理各10秒分开。
- [Kimi适配](spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)、[使用说明](guides/EXECUTION_SESSION_USAGE.md)、用户手册、AGENTS/简报/bridge模块及本快照/历史已同步。本轮仅8份文档；按常规提交/推送收尾，版本见Git日志。既有未跟踪产物保持。精确额度百分比未读取，不臆测。
- 完整历史见[PROGRESS_HISTORY.md](PROGRESS_HISTORY.md)。本轮验收权限不扩大为持续派发或无限期使用额度。

## 下一步

- 等用户确认本片里程碑；Kimi常规任务暂停保持，若后续需要启动/派发，先按用户新指示及原普通入口核验，不自动解除归属。
- 下一功能及宿主随TALK统一启动仍须单独说明范围和验收并获确认，不自动派发。

恢复指令：继续项目（先读本快照与Kimi实机边界；不派Kimi任务、不恢复286、不重放单次生产脚本）。
