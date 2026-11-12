# Project Progress

## 当前快照（2026-11-12 23:15，正式端到端验收完成）

- **正式 E2E 完成（第 2 项，2026-11-12 23:00–23:15）**：
  - **冷启动**：`stop --apply --wait` → `stop_status=stopped`、进程 absent、8000 端口关闭、无 TALK 子进程残留；`serve --apply --detach` → runtime `7684`、API child `16628`、`startup_state=complete`、宿主 serving；Terra `ins_97da886ad353`（gen70）、K2.8 `ins_3deacebf9459`（gen71）running/ready。
  - **持久性**：projects=1、tasks=713、messages=2686、groups=714、project_agents=10，冷启动前后一致；项目根 `D:\claude-test\TALK`；最近任务 713/712/711… 正常。
  - **真实运行器任务**：Terra（714）与 K2.8（715）各执行一次冷启动验收任务，均 `succeeded/submitted`，结果消息均为 `DONE`，已收取。
  - **双工作区隔离**：临时项目 B `prj_2272dff51013`，`ensure` 后 B runtime `11556` startup complete（attach-api）；A 角色保持 running/ready；停 B → A healthz ok、角色实例不变；清理：B 项目 DELETE 204、GET 404、W-D1 三表 0 孤儿、B runtime 目录与 `wsB` 目录删除。
  - 最终：healthz ok、online 3、宿主 serving、Terra/K2.8 running/ready。
  - 证据：`.tmp/e2e-formal/{pre-state,persistence,dispatch,runner-tasks,runner-results,ensure-b,final-state,summary}.json`。
- **限制**：UI 工作区切换/选择持久化未在浏览器验证（API 级）；临时 B 未创建角色（B 角色启动由 2026-11-09 W3c E2E 覆盖）；异常 kill/断电恢复未验证（第 12 项）。
- **下一步候选**：①异常关机后的选择性自启动与退出恢复（第 12 项）；②外部桌面运行器接入（第 13 项）；③Windows 桌面程序外壳（第 14 项）；④旧分支/工作区归档（第 16 项）；⑤历史候选结案（347/348、`prj_accept`）；⑥非阻断残余（`host_unreachable`、legacy guard/空 native-home、delete 90s 窗口）。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
