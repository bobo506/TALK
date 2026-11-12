# Project Progress

## 当前快照（2026-11-12 21:20，W-D1 演练完成 + 清理缺陷修复）

- **第 0 项「W-D1 真实重定向演练」完成**：临时项目 `prj_wd1e2e_*`，preview `marker_only` → relink `completed`、revision 2；项目根更新、新根指针写入、旧指针不变、runtime 配置 `project_root` 更新、旧根保留、删除项目 204；全程未碰现有项目。证据 `.tmp/e2e-wd1-real/<时间戳>/evidence.json`。
- **演练发现缺陷已修（705/706 approved）**：删除项目会残留 `workspace_registrations`/`workspace_relink_previews`/`workspace_operations` 孤儿行；现在删除前有非终态操作 → 409 `workspace_busy`，否则同事务清理三表；测试覆盖 active/completed/无行/跨项目。API 已 reload。
- **W-D1 残余**：真实多进程并发未验；SQLite busy timeout 下 claim/start 可能 500（既有）；自动启动跳过会暂留 `desired=running/observed=stopped`。
- **用户决定**：群聊按方案 A 拆除（去掉群聊页/建群/成员管理，任务 Hall 保留在任务详情）；后续优先级 0 → 1 → 2。
- **下一步**：群聊拆除切片（A）→ 第 1 项多工作区隔离（先设计/切片计划）→ 第 2 项正式端到端验收。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
