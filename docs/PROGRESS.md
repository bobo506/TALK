# Project Progress

Updated: 2026-10-15 23:04 (Asia/Shanghai)：用户新增“以后新角色配置成功后自动启动”要求；246原入口准备继续，247顺序方案准备已派，尚未实现或启生产服务。

## 已确认状态

- TALK / prj_e8fe7066bbec，分支codex/terminal-return-codex。页面业务版本5de19e8已获用户本轮整体验收通过，d4a9b37251cc308e93a33f416e72be7748d717ef为上轮8docs收尾；原245独立/静态证据沿用，无新代码或重复测试。
- 用户选择刚创建“Kimi k2.8”验证实际执行能力，member=agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c。最近实例读取offline/无实例、bound、runner unverified/控制unknown；旧K28的195固定串不套给新身份，当前未启动真实模型/执行器。
- 用户现明确要求以后配置完成自动启动。已记录已确认需求docs/spec/ROLE_AUTO_START_REQUIREMENTS.md（待实施）：新人类创建完整配置后自动走受管启动→实际ready；保留手动开关/单状态反馈，失败如实显示，人工关闭优先，旧角色/恢复不追溯自启动，原能力门控不绕过。

## 当前任务

- 246 DeepSeek新角色入口只读/零模型准备仍按原包，最后单次快照running/in_progress；已在其Hall通知新增方向而不扩大原权限。只准备命令/新身份/alias/tools/单次退出/必要本人Key内部只读核验与预算依据，Codex独立核后才试实际代码任务。
- 247 DeepSeek“新角色配置完成后自动启动服务的后端方案准备”，Hall group:task-a0f5d3de28e84fe09dd7966c9b450efd，queued仅派发快照；明确完成246后顺序做，只写.tmp/role-auto-start-prep/，不改源码/docs/Git、不真实启动/读秘密。给真实入口、授权/幂等/世代、配置成功与服务状态分离、崩溃/重复/人工关闭/host离线边界及最小单片任务包，由Codex独立复核后开发。
- 派发前实读latest development_requirements/caller agent:codex/kind=agent，DeepSeek busy/current_task246；未重复派246、未取消有用准备，不并行改码。用户前端Codex/DeepSeek核、后端宿主DeepSeek/Codex核分工保持，不改永久配置。
- 当前只7相关需求/进度/合同实施提示docs提交普通推送，174非docs保护源0漂移，证据.tmp/role-auto-start-prep/及publication.json；旧临时私有遗留排除，不纳入或清理。

## 下一步

- 默认派发后结束，用户“246好了”/“247好了”后分别取合法交付及独立核；准备齐后真实新角色试验/自动启动单片实施，保留测试、独立复核、人工验收和Git收尾，不把方案complete当功能完成。
- 当前已发布配置仍不自动启动；本次不启动CLI/模型/worker或批量历史角色，不修改生产名册/绑定/Key/原生默认模型，不放开unknown/unverified。真实自动启动/原生能力/退出清理与I-4未验，T/W按终端实际预算核，未核T不开主动长等待。
- 常规推送bobo506/TALK持续授权，只精确相关docs/后续已核源，私有/.talk/临时/db不提交。恢复“继续项目”承接246/247，不主动轮询等待。
