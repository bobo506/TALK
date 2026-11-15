# Project Progress

## Latest

Updated: 2026-11-15 00:30 (+08:00)

### 1) Current Progress
- **项目状态：开发结束（用户 2026-11-14 确认）**。无进行中切片、无待办、无待收取任务（用户已人工核对对账无遗漏）。
- 最终功能集：便携分发阶段 1–3、Chrome 优先/授权 UI（A）、WorkBuddy 条件适配（B）；test01/test03/test02 均真实跑通任务，A/B 已由用户验收。
- 运行状态：生产 TALK `8000`（pid 4968）运行中；便携 `8132`、runtime `7936`/`8932` 已正常停止，无残留。
- 收尾清理：删除临时产物约 66 GB（`.tmp-tests` 40 GB/71,739 目录、`.tmp` 26 GB）；删除 598 个被误跟踪的测试 DB；陈旧副本归档至 `D:\TALK-archive-20261114`；D 盘可用 161.9 → 227.2 GB。
- 2026-11-15 晚：角色经删除重建后恢复——Terra（codex，`gpt-6.1-terra`）、K2.8（kimi-code，`kimi-for-coding`）在线；四条终端发起身份（codex-t/kimi-t/dsh-t/workbuddy-t）已建立并接入 MCP。第 3 项（HTTP MCP `/mcp`）派给 Terra 后**因 Codex 执行环境无法创建命令进程而 blocked**（见 Open Questions）。

### 2) Open Questions / Pending Confirmation
- **待用户决策（2026-11-15 22:15 复核后）**：Terra 的 Codex 0.164 在**角色宿主环境**里无法创建命令进程，第 3 项无法开发；管理员上下文用**完全相同参数**可正常执行（见下），根因指向 TALK 角色宿主的 Codex 适配层，而非 CLI/版本/参数。
  - Terra 两次交付（#772 result 3572、#773 result 3573）均 blocked、`changed_files: []`；错误：`Failed to create unified exec process: timed out after 15000ms connecting runner pipe-out`。
  - 对照实验（管理员上下文，Codex 0.164）：`echo hi` 1239ms 通过；加 TALK 全同参数（`--strict-config --disable apps/remote_plugin/plugins --sandbox read-only -c windows.sandbox="unelevated" --model gpt-6.1-terra`、stdin 传 prompt、隐藏窗口）1111–1552ms 通过；重定向 USERPROFILE/HOME/APPDATA/LOCALAPPDATA/TEMP 后仍通过。
  - 结论：差异在角色宿主的启动环境/CODEX_HOME/隔离方式；`codex-command-runner.exe` 本身可启动。沙箱初始化日志曾出现 `failed to grant ... ACE on user profile ... os error 32`。
  - **A1 已试并排除（2026-11-15 23:15，探测任务 #774 result 3574）**：把 `scripts/codex_role_host.py` 的 `windows.sandbox` 临时改为 `disabled` 并重启 Terra 后，`git status --short` 与 `cmd /c echo hi` 仍各两次报同一 `runner pipe-out` 超时（15.2–16.3 秒）；补丁已回退、Terra 已重启回原配置。结论：**与 sandbox 策略无关**，问题在 Codex 的 unified exec runner 管道在角色宿主环境里建不起来。
  - **用户线索核查（2026-11-15 23:30）**：旧 `g-terra` 的 `project_roles.storage_layout = legacy`，新 `terra` 为 **`workspace-v1`**（native-home 在 `D:\claude-test\TALK\workspaces\...\roles\...\native-home`，旧布局在 `C:\Users\Administrator\.talk\agents\...`）。但用 workspace 路径作 HOME/TEMP 复跑 Codex 仍成功，**路径本身不是充分原因**；剩余差异集中在角色宿主的启动上下文（旧 legacy 角色的 host spec/启动方式 vs 新 cli_process 经 bridge 启动）。下一步：用 legacy-attach 建一个测试角色对比启动上下文，或对比旧 host spec。
  - **备份库对照（2026-11-15 23:35，`D:\backups\talk-before-role-rebuild-20261115-2110\talk.db`）**：旧 `g-terra` 的 `manager_kind` 也是 `cli_process`、`control_kind=managed_cli`（与新 terra 相同）；但它最后状态是 `last_result=failed / codex_role_setup_required`（11-15 12:56），说明“以前 Terra 能开发”指的是 11-14 事故前，之后旧角色本身也已失效。新 terra 已重新授权（native setup ready）但命令执行仍失败，因此**不能只用 legacy/workspace-v1 布局解释**；真正变化更可能是 Codex 运行态（CLI 重装 + 今日重建的 sandbox 用户/ACL）。待验证方案：装 0.163 对照、或建 legacy 布局测试角色、或改由 K2.8 开发。
  - 选项：A2 深挖 `codex_bridge`/宿主 spawn、角色 HOME 与 HANDLE/Job 继承（改代码，较慢）；B 本切片改由 K2.8 开发、Terra 复核（立即推进，需确认）。
  - 附带：talk-delivery-1 校验要求 `task_id` 为**字符串**、`verification[].evidence` 单行、不得出现 `schema/status/blockers/incomplete` 字段；下次派发按此写。
- 以下项已由用户 2026-11-14 决定不再做：便携分发阶段 4 剩余项（另一台干净 Windows、升级迁移、构建脚本 `_ssl`）、Mac 启动器端到端、旧开发分支归档、历史实例清理、347/348 旧候选结案。

### 3) Next Plan
- 2026-11-15 用户提出“开箱即用 / 一体化启动”方向，清单见 `docs/spec/DEVELOPMENT_ROADMAP.md` 顶部（第 1、2 项已完成，第 3 项因 Codex 执行环境阻塞待决策，第 4→13 项待推进）。历史“项目结束”结论仅指 2026-11-14 前的范围。

### 4) Verification
- `D:\TALK-portable\stop.bat` → `stop_status=stopped`；8132/8932/7936 均 closed，8000 仍 LISTEN（pid 4968）。
- 清理前后磁盘：D 盘可用 161.9 GB → 227.2 GB。
- 证据保留：`D:\TALK-archive-20261114\cited-evidence`（140 个文档引用文件，4.8 MB）与 `root-stale-copies`。
- 未验证：无（本轮无代码改动，未运行测试套件）。
- GUI 入口：`tests/test_talk_desktop.py` 17 项通过（unittest）；真实开窗验证——attach 8000 不新增进程、临时根 8934 启动后关窗自动停服、`start-gui.bat` 双击路径 exit 0；桌面 `TALK.lnk` 已生成。

### 5) Changed Files
- 文档：`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`、`docs/spec/DEVELOPMENT_ROADMAP.md`、`.gitignore`。
- 删除 598 个误跟踪测试 DB（`.tmp-tests/**/talk.db`、`.tmp/mem1_e2e/talk-test.db`）。
- 新增：`scripts/talk_desktop.py`、`tests/test_talk_desktop.py`、`start-gui.vbs`、`install-shortcut.bat`；修改：`start-gui.bat`、`start.bat`、`docs/guides/USER_MANUAL.md`。

## Recent Notes
- 归档位置：`D:\TALK-archive-20261114\`（`cited-evidence`、`root-stale-copies`、`stray-profile-root-20261115`）。
- 恢复：说“继续项目”。
- 环境事件（2026-11-14 22:51）：本机系统 Python（`AppData\Local\Programs\Python\Python312`）的 `Lib` 被便携运行时目录覆盖，标准库丢失。修复：拷回 `python312.zip` 并补 4 个缺失 `.pyd`；依赖装到并列目录 `Python312\talk-deps`，由 `Lib\site-packages\talk-deps.pth` 前置。已实测该解释器可起完整 API（临时根 8934，`/api/members` 200，控制文件优雅停止）。全局 `pip` 仍未装回；重装 Python 需重做这两步。
- 运行器环境（2026-11-15）：Codex CLI **临时钉在 `0.164.0`**（TALK 目前只接受 0.163/0.164，属临时措施）；Kimi Code CLI 安装原生 `2.0.2` 到 `~/.kimi-code/bin/kimi.exe`（并在 `%APPDATA%\npm\kimi.exe` 留一份供现有进程识别）。新版本适配已登记为路线图第 12 项。
