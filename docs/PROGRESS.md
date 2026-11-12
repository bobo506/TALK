# Project Progress

## 当前快照（2026-11-12 20:05，W-D1 验收通过）

- **W-D1「工作区登记与重关联」全链路完成并验收通过**：诊断 → 诊断 API → 登记/操作状态机 → 编排内核（文件事务/补偿）→ 受保护提交入口（令牌/幂等/忙预检）→ 领取/启动并发守卫 → 项目设置页面入口 + 本机原生目录选择。用户 2026-11-12 验收通过（面板排版、三按钮样式、选择窗置顶）。
- **部署状态**：API 已 reload 加载 4b/预览 `candidate_root`/picker；runtime 在 4b 时重启一次；Terra/K2.8 running/ready；`submitted=[]`。
- **W-D1 残余（非阻断）**：部署环境“临时项目真实重定向成功”演练未做；真实多进程并发未验；SQLite busy timeout 下 claim/start 可能 500（既有行为）；自动启动跳过会暂留 `desired=running/observed=stopped` 至下次 reconcile。
- **下一步候选**（详见 [DEVELOPMENT_ROADMAP.md](spec/DEVELOPMENT_ROADMAP.md)）：
  1. W-D1 真实重定向演练（一次性临时项目，闭合最后安全验证）
  2. 多工作区隔离（角色 cwd/任务/原生会话/服务生命周期 + 双工作区实测）
  3. 正式端到端验收（冷启动/双工作区/退出清理/重开持久性）
  4. 群聊与会议（持续上下文、轮次/迟到回复、主持与总结）
  5. 异常关机后的选择性自启动与退出恢复
  6. 外部桌面运行器接入
  7. Windows 桌面程序外壳/正式使用目录与迁移
  8. 旧开发分支与工作区归档收尾
  9. 历史候选结案确认（347/348 等旧候选、WorkBuddy ACP 暂停项）
- **恢复**：说“继续项目”；已完成切片的完整记录见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
