# Project Progress

Updated: 2026-10-25 14:58（Asia/Shanghai）。人工验收发现自启动控件仍缺：实际页面从/agents取数，原只给/roles填startup。Codex已2产品5行补正；93关联+新2复跑通过（不同Python并集95）、9Node通过，原失败保留。待新冻结交DeepSeek一次定向复核，随后暂停产品；尚未生产加载。

## 当前事实

- 实际Chrome human bobo/小D详情无控件，页面确加载新版workspace.js；截图ui-fix1/before.png。公开GET五/agents均无startup而/roles均false/revision0，绑定全bound/managed_cli。刷新无助的根因是实际页面接口DTO遗漏，不是控件位置；前次指导未先核实这条链路，已纠正。
- 仅server/models.py+server/routes/projects.py共5行补ProjectAgentOut startup字段/参数/透传及既有公开投影；GET /agents和POST /sync共享组装。前端显示守卫、权限、选择写入/启停、数据库表和生产配置不变。
- 新增真实隔离API响应→实际app.js loadProjectAgents→workspaceRoleStartupPanel链路，默认/保存true/回读/保存false及审计/项目隔离/只读均通过。改前新2测试2F；95关联首次93旧通过，新2夹具编码/过期快照1F/1E，修夹具后2项复跑全过，不同Python并集95；不是单轮95全过。9原Node测试过，不为归档重跑。日志在.tmp/project-role-autostart-ui-fix1/。
- 334 complete/2980已收取，原MF-1R/2/3独立闭合仍保持；本返修不重做runtime首审。旧63/116/162及332原33/333原29/334原15报告均保留；332failed/2978、333partial/2979不追改。
- 用户已重载含startup的新API，但尚无本次/agents补正；原runtime11280/五宿主仍旧，DSH gen76/原实例idle，另四停止。五选择默认false，250failed/2767未收取、286queued/accepted/paused保护保持。
- 本次实际浏览器只读观察及原human公开GET；没有勾选/启停/删除/恢复或读生产配置正文/角色Key/DB/侧账本/private state/HOME/native/log。原一次元数据/定向恢复例外已用完，不复用或授复核者。

## 下一步

1. 完成修正Git/新冻结后交DeepSeek一次定向复核，仅核真实/agents/sync接口兼容及页面默认/保存回读可见，不重做334/runtime或非阻断观察；唯一写ui-fix1/review，产品/正式测试/新旧冻结暂停。
2. 默认派后用户通知完成再取件，不主动等待/唤回，不另发可执行Hall消息。独立通过后统一正常加载补正、实看用户页面控件；当前不让用户反复刷新/重启。
3. 仍按[原加载方案](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)补齐后台正常重载，默认false且仅恢复原DSH；不自动勾选，不改模型/Key/绑定/250/286，不强杀/CAS/清锁。下一无关片先确认。

详[本次验收返修](spec/PROJECT_ROLE_AUTO_START_UI_FIX_20261025.md)、[加载记录](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)和[历史](PROGRESS_HISTORY.md)。
