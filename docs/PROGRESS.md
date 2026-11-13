# Project Progress

## 当前快照（2026-11-14 02:50，14 阶段3 便携包已产出，待早上人工验收）

- **便携包已产出**：`D:\TALK-portable`（预配置验收副本，端口 8132，config/data/keys 在文件夹内）；`D:\TALK-portable-clean.zip`（20.7 MB，1,440 files，干净分发）。
- **验证**：包内 embeddable Python 3.12.1 + 依赖 + TALK/client 导入通过；8132 首启 bootstrap→Edge 窗口→自动关窗→服务停止/端口关闭，退出码 0；750 独立复核 approved（89 项回归）。
- **构建脚本限制**：pip 后 `_ssl` 瞬时 DLL 失败（进程退出后恢复），当前包由暂存 runtime 组装；一次在线构建可复现性待后续修。
- **14 阶段2b**：Edge 应用窗口启动器已提交 `df0d1fc`，746 approved；真实人工关窗待早上验收。
- **生产**：runtime `7936`（API `4968`）、Terra/K2.8 两宿主 ready；8000 未动；projects=1。
- **提交**：`ff6d4b7`（阶段3代码）、`df0d1fc`（2b）、`1974161`（2b 文档）、`f5075cf`/`8ba6ef6`（2a）、`1b2392b`（1）；均已推送或待本次文档提交推送。
- **下一步**：用户早上验收便携版/真实关窗；阶段4 补另一台干净 Windows、升级迁移；构建脚本 `_ssl` 修复。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部、[PORTABLE_PACKAGE.md](guides/PORTABLE_PACKAGE.md)。
