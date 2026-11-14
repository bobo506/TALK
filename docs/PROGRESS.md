# Project Progress

## Latest

Updated: 2026-11-14 22:08 (+08:00)

### 1) Current Progress
- 便携版 `D:\TALK-portable`（8132）运行中；A（Chrome/授权 UI）与 B（WorkBuddy）均已由用户验收通过。
- 角色：test02（WorkBuddy）running/ready；test01（DSH）、test03（Codex）stopped；test（Kimi）not_started（需原生登录）。
- 任务：6 个；4 成功（test03/DSH×2/WorkBuddy），2 个失败为已修复的 DSH model patch 历史问题；当前无执行中任务。
- 包：`D:\TALK-portable-clean.zip` 21,755,645 bytes/1,440 files，SHA256 `1B9E79E8…8B11`。
- 生产 TALK 8000 健康，runtime `7936` 未动。

### 2) Open Questions / Pending Confirmation
- test01/test03 是否现在重启做长任务观察。
- 是否需要 Mac 启动器端到端（目前仅路径检测，单实例锁 Windows-only）。
- 另一台干净 Windows、升级/迁移、构建脚本 `_ssl` 仍未验收。

### 3) Next Plan
1. 需要时手动启动 test01/test03，做一次长任务/多轮任务观察。
2. 另一台干净 Windows 首次启动/升级迁移验收。
3. 如确需 Mac，单独做跨平台启动器单实例与打包切片。

### 4) Verification
- A：15 项 launcher + 65 项 DOM 测试；用户真实 Chrome/关窗验收通过。
- B：19 项 portable/WorkBuddy 测试；test02 真实启动，任务 6 返回 `PORTABLE-WD-7805ED test02 已收到`。
- Codex/DSH：native setup/DSH patch 52 项测试；test03/test01 真实任务成功。
- 未验证：Mac 真机、另一台干净 Windows、WorkBuddy 长任务。

### 5) Changed Files
- 最近提交：`e6922f1`、`b6ef803`、`8399c2b`、`0ba75db`、`6e068fb`、`e2e2c9e`。
- 详细完成记录见 `docs/PROGRESS_HISTORY.md` 顶部；已推送 `origin/codex/terminal-return-codex`，0/0。

## Recent Notes
- A/B 验收说明：`docs/guides/PORTABLE_PACKAGE.md`、`docs/guides/USER_MANUAL.md`。
- 恢复：说“继续项目”。
