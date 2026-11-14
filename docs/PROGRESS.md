# Project Progress

## 当前快照（2026-11-14 14:20，便携 DSH test01 已启动）

- **test01 启动成功**：便携 runtime 补全 `codex/kimi/dsh` 宿主配方并重启；DSH host 已 serving，重新 start 后 launch claimed，角色 `running/ready`、实例 idle。
- **根因**：全新便携 `config/runtime.json` 缺宿主配方，`dsh_spec` 返回 None，host 不拉起；已合并配方，已有 config 只补缺失 key。
- **包**：`D:\TALK-portable-clean.zip` 21,752,690 bytes/1,440 files，SHA256 `5E17CC53…2780`；`D:\TALK-portable` 已同步并运行 test01。
- **其他修复**：关窗 API 5s 超时、运行器/模型 seed、角色配置宿主 seed、桌面隐藏退出；用户已确认前两项。
- **生产**：runtime `7936`/8000 未动。
- **待做**：Codex/Kimi 真实启动（原生登录）待用户；构建脚本 `_ssl`、阶段4 另一台干净 Windows/升级迁移。
- **提交**：`e2e2c9e`（host seed）、`6ced903`（文档）、`e55d392`（关窗/运行器/退出）；755 配方修复待提交/推送。
- **恢复**：说“继续项目”；详情见 [PROGRESS_HISTORY.md](PROGRESS_HISTORY.md) 顶部、[PORTABLE_PACKAGE.md](guides/PORTABLE_PACKAGE.md)。
