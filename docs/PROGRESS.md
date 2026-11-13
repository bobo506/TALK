# Project Progress

## 当前快照（2026-11-13 22:10，14 免安装阶段 1 完成）

- **14 阶段 1 已完成**：`TALK_CONFIG`、便携路径（`TALK_HOME`/`TALK_KEYS_DIR`/data 目录）、幂等 bootstrap（config/runtime/Key/管理员/默认项目/.talk）、`start/stop/status.bat`；`local_runtime` 绑定已按 `TALK_CONFIG` 修复；提交 `1b2392b`。
- **验证**：10 项便携测试（隔离 bootstrap→随机端口 API→startup HTTP 200→stop）、76 项 startup 回归、29 项 local_runtime 补跑通过；737 独立复核 approved。
- **非阻断残余（阶段 1）**：Key ACL 未收紧；真实双击 bat/浏览器回退未验；首次端口未参数化；未跟踪测试残留 `portable-phase1-d45aswhw/`；便携无 project_id 自动恢复未做。
- **宿主生命周期**：runtime `9960`、仅 Terra `6164`/K2.8 `13884` 两个 owned 宿主；Terra gen86、K2.8 gen84 ready；healthz ok；任务 0。
- **下一步**：阶段 2——桌面窗口启动器（pywebview/WebView2、关闭即停、单实例）+ 运行器检测弹窗；阶段 3 embeddable/打包；阶段 4 干净机器 E2E。
- **其他范围**：13 关闭（仅 CLI）；17 ACP 与会议关闭；15a/15b/实例清理已完成。
- **提交**：`1b2392b`（阶段 1）；此前 `1b065fa`/`59f5406`/`b650567`/`1e2cd0b`/`055c24d`/`c660c33`/`bb5724f`/`5277d9c`/`0b45f60`/`25925bc`/`4783839`/`8bfc1f7`/`afb93df`/`27bfb2a`；本次文档另提交。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部。
