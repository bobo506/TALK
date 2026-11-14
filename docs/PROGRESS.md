# Project Progress

## 当前快照（2026-11-14 19:40，便携 test01/test03 运行，DSH 任务 patch 待修）

- **test03 Codex**：native setup 根分离修复后，用户完成设备授权，角色 `running/ready`；任务执行成功，回复 `PORTABLE-207674 test03 已收到`。
- **test01 DSH**：角色 `running/ready`，但任务预检失败：缺 `native-home/model-deepseek-flash.patch.yml`；已派 Terra 760 生成 model patch，待 K2.8 复核。
- **native setup 修复**：project_root 用 `.talk` pointer，data_root=TALK_HOME 用 workspaces/native-home；759 复核 approved；D:\TALK-portable 已应用。
- **包**：`D:\TALK-portable-clean.zip` 21,753,137 bytes/1,440 files，SHA256 `7EFB88B6…AFDD`。
- **待做**：760 DSH patch；A 启动器（Chrome→Edge/default，含 Mac 检测）+ 授权 UI（去冗余文案、ready 隐藏、复制码）；B WorkBuddy 便携适配。
- **生产**：runtime `7936`/8000 未动。
- **提交**：`e2e2c9e`/`6ced903`/`e55d392`；756/758 待提交推送；760 后单独收尾。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部、[PORTABLE_PACKAGE.md](guides/PORTABLE_PACKAGE.md)。
