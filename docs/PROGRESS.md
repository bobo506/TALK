# Project Progress

## 当前快照（2026-11-14 00:15，14 阶段2a 弹窗已上线并视觉验收）

- **14 阶段 2a 完成**：项目加载后运行器引导弹窗已部署；无角色且可用 → “已适配 xx，可创建角色”；无可用且确认 missing → “缺少 xx…”（有角色也弹一次）；仅 error/unknown 不误报；WorkBuddy 排除；每成员/项目/浏览器标签页会话一次。
- **视觉返修**：标题“运行器提示”、正文单句、无“知道了”、主按钮右对齐、卡片 560px/内边距/字号统一；用户截图验收通过。
- **运行态**：runtime `7936`（API `4968`）、仅 Terra/K2.8 两个宿主 serving，均 ready；healthz ok；projects=1、任务 0。
- **提交**：`f5075cf`（2a 主体）、`8ba6ef6`（视觉返修）；735-742 已收取，`submitted=[]`。
- **14 阶段 1 已完成**：`TALK_CONFIG`/便携路径/bootstrap/start-stop-status，`1b2392b`。
- **下一步**：阶段 2b 桌面窗口启动器（pywebview/WebView2、关闭即停、单实例，需用户窗口验收）；阶段 3 embeddable/打包；阶段 4 干净机器 E2E。
- **已知残余**：无 Tab 焦点陷阱；跨类型 seen 抑制；ready+missing 混合只弹 ready；真实无运行器环境未构造；Key ACL/真实双击 bat/端口参数化等阶段 1 非阻断项。
- **其他范围**：13 关闭（仅 CLI）；17 ACP 与会议关闭；15a/15b/实例清理完成。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
