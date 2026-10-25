# 项目自启动：角色详情控件缺失修正

用户在API重载和强制刷新后，角色详情仍看不到“随项目自动启动”。本次属于既有切片的人工验收缺陷修正，由Codex修正、DeepSeek定向复核，不是新功能。原334 complete、333 partial、332 failed及各阶段原始报告保持。

## 实际根因和证据

- 通过用户现有Chrome TALK页面确认：human bobo、角色“小D”已选中，角色详情只有启停/删除，缺少自启动控件；页面加载的是workspace.js?v=20261025-role-startup-v1。截图.tmp/project-role-autostart-ui-fix1/before.png。没有点击启停、删除或勾选设置。
- app.js的真实loadProjectAgents从GET /api/projects/{project_id}/agents取数，直接保存响应；workspaceRoleStartupPanel要求role.startup存在。原实现只给/roles的ProjectRoleListItem加startup，遗漏/agents的ProjectAgentOut及其组装函数。
- UTC06:55:28原human正常只读GET证明：五角色/agents均没有startup键，/roles则均enabled=false/revision0/last_activation=null；五角色binding均bound、control_kind均managed_cli。故控件被隐藏，浏览器刷新无助；不归因用户位置或缓存。
- 原服务端测试只覆盖/roles；原Node控件测试手工构造带startup的role，因此漏掉真实API DTO到页面的链路。Codex之前没有先核该链路就指导入口，现补齐实证，不把旧测试通过当实际页面已可用。

## 最小改动

仅2份产品共5行：ProjectAgentOut增加可选startup字段、from_orm_agent参数及透传；_project_agent_outs调用既有startup_projection。GET /agents与POST /sync共用此公开组装函数，不改旧字段或权限、前端入口/显示守卫、选择写入/启停执行、数据库表/配置/绑定。新增字段复用/roles相同公开投影，不暴露内部lease/token/路径。

正式验证新增tests/test_project_role_startup_roster.py与tests/role_startup_roster_render.cjs。真实隔离TestClient的GET /agents JSON经Node子进程输入真实app.js loadProjectAgents和workspaceRoleStartupPanel，不手工补startup；验证默认未勾选→PUT true→刷新列表仍勾选→PUT false→刷新还原，页面渲染仅GET且不产生launch/activation/cycle。另验/agents与/roles执行审计一致、跨项目不串选择、只读不改审计/偏好、无内部lease泄漏。

改产品前新2测试均失败（2F/0E），其中页面实际渲染visible=false，red.log原样保留。修正后关联Python、上述真实接口到页面链路及原9项Node控件检查集中执行；实际计数以final.log和node-selfcheck.json为准，不能把这些自检称独立通过。

最终自检：95项关联Python中的93项旧回归通过，新2项首次因夹具问题1F/1E（Node UTF-8输出被Windows GBK解码、SQLModel提交过期后空model_dump）失败，原final.log及runner混合编码解码错误保留。仅修测试为显式UTF-8和refresh后快照，新2项在final2.log复跑全过；不同用例并集95，不称同一轮95全过。产品5行在首次关联跑后未改。原9项Node控件测试全过；未为归档重新跑一遍，真实工具输出计数保存node-selfcheck.json。

## 交接、加载与保持边界

新冻结后只交DeepSeek一次定向复核：核真实/agents响应及/sync共享组装兼容、默认/保存回读后的控件可见、只读/权限/项目隔离；不重做334的runtime/MF-1R及已过MF-2/MF-3，不为非阻断项再开任务。复核唯一写.tmp/project-role-autostart-ui-fix1/review/；所有产品/正式测试/新旧冻结和旧报告暂停只读。

修正当前未加载到外部API；本轮不提前启停生产或让用户反复重启。独立通过后统一安排必要的一次正常API加载，并在用户原页面实际确认控件可见；后台11280正常重载仍是原加载方案的未完成步骤，不把本次修正或截图当成完成了后台加载/真实自动启动。

不读取生产配置正文/清单/角色Key/DB/侧账本/private state/HOME/native session/log；原human凭据只正常认证公开GET。本次未做生产PUT、勾选、启停/删除/恢复/CAS/sweep，原一次元数据/定向恢复许可已用完，不复用、不授复核者。五角色模型/绑定、250failed/2767未收取、286queued/accepted/paused及默认false保持；现有DSH继续原状态，下一无关片不自动开。
