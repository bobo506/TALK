# Project Progress

## 当前快照（2026-11-14 20:20，便携 test01/test03 任务均可执行）

- **test01 DSH**：763 宿主启动前生成 `model-deepseek-flash.patch.yml`；765 复核 approved；现场清空手工 patch、重启 runtime/test01 后自动生成，任务 `PORTABLE-DSH-A54D82` 成功。
- **test03 Codex**：native setup 根分离 + 设备授权已完成；任务 `PORTABLE-207674` 成功；running/ready。
- **A 启动器/授权 UI**：Chrome→Edge→默认浏览器（含 Windows/macOS 路径）；ready 后授权栏隐藏；两段冗余文案删除；验证码可复制/选中。764 复核 approved；真实 Chrome 桌面验收待用户，Mac 未端到端。
- **包**：`D:\TALK-portable-clean.zip` 21,755,007 bytes/1,440 files，SHA256 `F3E88C59…D26F`；D:\TALK-portable 已应用。
- **B WorkBuddy**：待开始；需本机 WorkBuddy 安装，不能打包本体。
- **生产**：runtime `7936`/8000 未动。
- **待做**：用户视觉验收 A（关窗停服务、授权栏、复制码）；B WorkBuddy 便携适配。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部、[PORTABLE_PACKAGE.md](guides/PORTABLE_PACKAGE.md)。
