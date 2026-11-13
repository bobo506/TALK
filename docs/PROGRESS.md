# Project Progress

## 当前快照（2026-11-13 20:30，宿主生命周期已部署验证）

- **宿主生命周期已上线**：冷启动只拉起 2 个勾选角色宿主（Terra/K2.8），其余 5 角色无宿主；disabled 的 Astra 手动启动按需拉起（宿主约 2–4s、ready 约 11s），stop 后宿主保留；受控崩溃后运行中的 Terra/K2.8 外部宿主保留、已停止且未勾选的 Astra 外部宿主被核验终止，无 `recovery_required`。
- **当前运行态**：runtime `9960`（API `12440`）、仅 Terra `6164`/K2.8 `13884` 两个 owned 宿主 serving；Terra gen86/`ins_3c2b5b7cc58d`/`16152`、K2.8 gen84/`ins_d78ad89ee10f`/`7864` ready；healthz ok；任务 0。
- **已完成**：15a/15b、K2.8 3 条历史 idle 实例清理；733/734 已收取，`submitted=[]`。
- **范围**：13 关闭（仅 CLI）；14 免安装文件夹分发方案草案已出（`docs/spec/PORTABLE_DISTRIBUTION_DESIGN.md`，含桌面窗口启动器/关闭即停/运行器检测弹窗，12 项决策待确认）；17 ACP 与会议关闭；宿主上限/启动延迟预算未做。
- **已知残余**：archived+owned 契约无测试；deletion 外部宿主与 cleanup 的基线互锁待确认；`agent:pi` 1 条 busy/10 条 error 历史实例未处理；P2 长任务 kill 可不做；浏览器无自动化工具/截图。
- **提交**：`1b065fa`（宿主生命周期）、此前 `59f5406`/`b650567`/`1e2cd0b`/`055c24d`/`c660c33`/`bb5724f`/`5277d9c`/`0b45f60`/`25925bc`/`4783839`/`8bfc1f7`/`afb93df`/`27bfb2a`；本次验证记录另提交。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
