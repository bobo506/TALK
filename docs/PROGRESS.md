# Project Progress

## 当前快照（2026-11-14 02:00，14 阶段2b 启动器候选 approved，待人工关窗验收）

- **14 阶段2b**：Edge 应用窗口启动器候选 `df0d1fc`，746 独立复核 approved；owned 关窗停服、attach 保活、单实例、Edge 缺失/启动超时保护、82 项测试通过；真实人工关窗待用户验收。
- **已知限制（2b）**：页面内链接可导航；关窗后无法取消，忙任务/停止失败可能残留服务；`start-gui.bat` 首次 bootstrap 属阶段 3。
- **14 阶段2a**：运行器检测弹窗已上线并视觉验收（`f5075cf`/`8ba6ef6`）；阶段1 `1b2392b`。
- **运行态**：生产 runtime `7936`（API `4968`）、Terra/K2.8 两宿主 ready；healthz ok；projects=1；2b 测试只用 8124，不碰 8000。
- **下一步**：阶段3 embeddable Python + 便携包构建（含首次 bootstrap、detach breakaway 回退）；阶段4 干净路径/另一用户 E2E。
- **已知残余**：Key ACL、真实双击 bat/浏览器、端口参数化、跨类型 seen、无焦点陷阱等非阻断项。
- **提交**：`df0d1fc`（2b 候选）、`f5075cf`/`8ba6ef6`（2a）、`1b2392b`（1）、此前宿主生命周期 `1b065fa` 等；均已推送或待收尾推送。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
