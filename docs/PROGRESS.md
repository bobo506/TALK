# Project Progress

## 当前快照（2026-11-14 09:40，便携版关窗/运行器/退出已修复）

- **便携版 8132**：关窗 API 优雅关闭超时已修（5s），真实 Edge 手动关窗连续验证通过；再次启动正常。
- **运行器**：全新便携 DB 自动 seed Codex/Kimi Code/DSH + 7 个默认模型，创建角色下拉不再为空；用户已确认选项出现。
- **退出按钮**：桌面模式（`?desktop=1`）隐藏右上角“退出”；普通浏览器保留。
- **包**：`D:\TALK-portable`（验收副本 8132）已同步；`D:\TALK-portable-clean.zip` 21,751,988 bytes/1,440 files，SHA256 `8F2D2FAB…07FB8`。
- **验证**：3 runners/7 models API 查询、Edge 关窗/8132 关闭、29 项 portable/launcher/build 测试通过（长 TEMP）。
- **生产**：runtime `7936`/API `4968` 未动，8000 正常；projects=1。
- **待做**：K2.8 复核本次修复；用户真实创建角色（原生登录/模型）验证；阶段4 另一台干净 Windows/升级迁移；构建脚本 `_ssl` 瞬时失败。
- **提交**：`df0d1fc`（2b）、`ff6d4b7`（3）、`403d571`（3 文档）；本次修复待提交/推送。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部、[PORTABLE_PACKAGE.md](guides/PORTABLE_PACKAGE.md)。
