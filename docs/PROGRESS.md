# Project Progress

Updated: 2026-10-20 17:03（Asia/Shanghai）。用户明确确认DeepSeek状态页面“验收通过”，修复/加载/人验门禁闭合。回原日志排期，B2b-1真实writer上传投影及严格PreparedBatch适配合同已固定，当前准备冻结和派发，尚未创建任务。生产接收仍关闭，Kimi继续暂停新派发。

## 当前工作：B2b-1投影片准备

- 详[切片合同](spec/ROLE_RUNTIME_LOG_UPLOAD_PROJECTION_B2B1.md)、[已批准B合同](spec/ROLE_RUNTIME_LOG_RECEIVE_DESIGN.md)。先真实writer→版本化上传对象→服务端严格再次投影→284 PreparedBatch，候选隔离、不改内核/路由/认证/配置/模型/生产。HTTP/来源接口/查询随后串行，B3 outbox后续，不冒称已接收或已跨机器。
- 首片支持role标准/异常及transition/queue_poll，manager仅manager_round_snapshot；launch_process和其它manager生命周期事件明确拒绝并保本地，待后续补归因，不静默丢弃或伪造manager事实。
- 首次执行DeepSeek、自测交付后暂停；Codex独立实查/直接修正、集成/正式进度/Git。须先提交合同与人验，再冻结公开源/指定文档、白名单和隔离根派发；本快照时尚未派发。
- usage-gate guard返回continue；精确用量比例null，未臆测百分比。当前DeepSeek新ins_00acba0f8a9b idle/无任务，实际派发前重核；不启停角色或测试模型。

## 最近完成

- DeepSeek查询恢复error残留：00bdcff直接补正、14新增及相关原例170项自检通过；02c7692记录用户批准的仅DeepSeek普通stop/start。gen23/ins_00acba0f8a9b/12284归原manager11612，ready/idle/无错误、同实例心跳推进60.059秒；API/其它角色/绑定保持。用户本轮明确确认“启动成功、绑定保持”页面验收通过，证据.tmp/queue-poll-status-recovery/human-acceptance.json，原失败及加载证据保留。详[补正记录](spec/QUEUE_POLL_STATUS_RECOVERY_FIX.md)。
- 285管理账号只读查看：代码9504a2c/加载8be3921/人验54101f8，162 Python/81 Node及未入群读200/写403保持，仅human:bobo名单、不自动入群；任务按钮统一“中止任务”，保原号重新派发规则。人验已闭合，详[285复核](spec/CONVERSATION_ACCESS_REVIEW_285.md)。
- 284已发布df437b8：三日志表/来源管理/事务内核默认关闭，51项最终自检，原失败保留；285获准加载时三表各0行、30旧表结构/旧业务数据保持。生产接收未启用、无HTTP/上传接线，详[284复核](spec/ROLE_RUNTIME_LOG_RECEIVE_REVIEW_284.md)。
- 282本地A/279轮询日志/280绑定行/278诊断页面已完成既有验证及用户人验；256/257历史needs_changes保留，258已闭合准备问题。本轮不重做旧迁移/模型验证，不改旧结果。完整记录见PROGRESS_HISTORY.md。

## 职责和不变项

- 本人agent:codex/agent、lead、project prj_e8fe7066bbec。页面development_requirements仍旧交叉分工，实际按AGENTS最新规则：DeepSeek首次执行，Codex独立实查并直接修正；Kimi额度耗尽暂停所有Kimi新派发，直到用户恢复，不因此停服/改绑定/删角色。
- 默认派发后结束、用户通知完成后取件，不自动等待/唤回/重派；不由Codex操作Browser。独立复核与修正自检如实区分，一次一片，候选与正式目录分离。
- API及角色/Key/模型/owner/启停守卫保持；日志接收生产启用和真实拓扑需独立验收。原local日志scope/ref/cursor/导出partial和脱敏保持，不在B自动删旧数据或开全根清理。
- 当前TALK目录不迁，未来main/worktree布局仅后续新项目，当前不开群聊分支。

## 下一步

固定干净基线、冻结副本/白名单后派DeepSeek一个B2b-1投影片，交付暂停后由Codex实查。日志B2b全部收尾再B3持久outbox/真实跨机器和C全根治理；日志整项后统一全入口执行预算21600，再会话复用。

恢复指令：继续项目。
