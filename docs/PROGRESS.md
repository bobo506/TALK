# Project Progress

## 当前快照（2026-11-12 22:15，群聊拆除完成）

- **群聊管理界面已拆除（708 实现 / 709 复核 partial / 710 返修 / 711 approved）**：去掉「群聊」导航、房间列表/搜索/刷新、新建群聊、群成员增删、删除群聊及相关文案；保留任务 Hall（任务详情 →「查看完整对话」：消息/历史/发送/presence/只读与观察者逻辑）；不改后端、不删数据、不改接口。`web/app.js` -731 行、`web/index.html` -97 行，资源版本号已 bump。
- **复核中发现的回归已修**：`tests/workspace_project_switch.test.cjs` 曾引用已删除的 `refreshGroups()`；710 改用保留函数做截取边界，保留“切换项目不串 group”断言，删除仅针对已移除建群逻辑的用例；711 定向复验通过。
- **交付格式**：708/709/710/711 交付中有“无 json 围栏”或字段超长，均已记录（不伪造通过）。
- **部署**：前端静态资源，刷新即生效；本轮未重启 API/runtime。
- **W-D1 残余**：真实多进程并发未验；SQLite busy timeout 下 claim/start 可能 500（既有）；自动启动跳过会暂留 `desired=running/observed=stopped`。
- **下一步**：第 1 项 **多工作区隔离**——先设计/切片计划（角色 cwd、任务/消息归属、原生会话、服务生命周期、双工作区实测），确认后实施；第 2 项正式端到端验收随后。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
