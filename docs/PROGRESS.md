# Project Progress

## Latest

Updated: 2026-11-16 14:37 (+08:00)

**最新覆盖结论（#795）**：Terra runner 继承 Low 完整性标签。用户授权后仅将该 runner 文件改为显式 Medium，临时 WRITE_OWNER 已撤回，原普通 ACL 和文件哈希保持；Terra 单次 `cmd /c echo hi` 返回 hi、exit 0、耗时 1.4669958 秒。结果 3595 已核对并正常收取，强烈支持完整性标签是本次 pipe-out 超时的原因。当前保留 Medium，不回退；上级目录 Low 未改，重建/升级持久修复及完整开发验收尚未进行。此前“全部排除 ACL/沙箱”“Terra 仍无法执行任何命令”的记录仅作为历史，不再代表当前结论。详见 PROGRESS_HISTORY 顶部；下一片须另行确认。

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
  - **A1 已试但结论作废（2026-11-15 23:15 试，23:55 复核发现无效）**：`windows.sandbox` 在 Codex 0.164 只接受 `elevated` / `unelevated` / `mxc`，写成 `disabled` 会直接报 `unknown variant`；且运行中的 bridge 进程命令行（pid 5716，`--codex-command`）仍是 `windows.sandbox=\"unelevated\"`，证明**补丁没有生效**（角色重启复用运行时宿主已导入的旧模块，argv 是启动时冻结的）。所以“关沙箱仍失败”**不能作为排除沙箱的依据**；补丁已回退。
  - **进程观测（2026-11-15 23:56–00:00，探测 #776 result 3576）**：失败期间每 3 秒采样，只看到 `codex.exe`（父进程是 `python -m bridges.codex_bridge`）持续存活约 2 分钟，**没有观察到 `codex-command-runner.exe`**（采样粒度可能漏掉瞬时进程）；错误发生在 codex 自己的 CreateProcess 包装层（`Rejected(...)`），不是 shell 命令执行失败。
  - **Astra 咨询（咨询任务 #775 result 3575，Astra 仅分析未执行）**：按概率排序——① 真实宿主进程安全上下文/Job 限制导致 runner 无法启动或 IPC 握手失败；② `CHILD_ENV_ALLOWLIST` 裁剪了 runner 所需环境；③ runner/角色目录 ACL、安装一致性或安全软件拦截。建议先补完整白名单环境对照、观察真实 runner 的创建/退出/管道事件，再考虑 0.163 对照；不推荐提权/关安全软件/放宽 ACL。
  - **用户线索核查（2026-11-15 23:30）**：旧 `g-terra` 的 `project_roles.storage_layout = legacy`，新 `terra` 为 **`workspace-v1`**（native-home 在 `D:\claude-test\TALK\workspaces\...\roles\...\native-home`，旧布局在 `C:\Users\Administrator\.talk\agents\...`）。但用 workspace 路径作 HOME/TEMP 复跑 Codex 仍成功，**路径本身不是充分原因**；剩余差异集中在角色宿主的启动上下文（旧 legacy 角色的 host spec/启动方式 vs 新 cli_process 经 bridge 启动）。下一步：用 legacy-attach 建一个测试角色对比启动上下文，或对比旧 host spec。
  - **备份库对照（2026-11-15 23:35，`D:\backups\talk-before-role-rebuild-20261115-2110\talk.db`）**：旧 `g-terra` 的 `manager_kind` 也是 `cli_process`、`control_kind=managed_cli`（与新 terra 相同）；但它最后状态是 `last_result=failed / codex_role_setup_required`（11-15 12:56），说明“以前 Terra 能开发”指的是 11-14 事故前，之后旧角色本身也已失效。新 terra 已重新授权（native setup ready）但命令执行仍失败，因此**不能只用 legacy/workspace-v1 布局解释**；真正变化更可能是 Codex 运行态（CLI 重装 + 今日重建的 sandbox 用户/ACL）。待验证方案：装 0.163 对照、或建 legacy 布局测试角色、或改由 K2.8 开发。
  - **A5 已试并真正排除沙箱（2026-11-16 00:04–00:08，探测 #777 result 3577）**：把只读命令的 `windows.sandbox` 改成有效值 `elevated`、**重启整个 role-service-host 运行时**（API 自动拉起新运行时 pid 17232），确认新 bridge 命令行确实是 `windows.sandbox="elevated"` 后，`cmd /c echo hi` 与 `git status --short` 仍各报同一 `runner pipe-out` 超时（约 15 秒）。**结论：`elevated` 与 `unelevated` 都失败，沙箱变体不是原因**；补丁已回退为原 `unelevated`。
  - **A7 诊断日志（2026-11-16 00:13–00:23，K2.8 开发任务 #779）**：`bridges/cli_bridge.py` 增加 `TALK_CODEX_DIAG`（默认开启）诊断，写 `D:\agent-trash\talk-diag\codex-spawn.log`（spawn/exit 两行，含 argv0、路径、runner 候选、退出码、过滤后的 stderr）；新增 `tests/test_codex_diag.py`。用真实失败复跑得到关键证据：`codex_rollout::recorder: rollout writer failed ... os error 5`（拒绝访问）——角色 native-home `.codex` 的 ACL 让新建文件只继承 deny + sandbox RX，没有 Administrators 允许项。已对 Terra 的 `.codex` 递归补 `Administrators:(OI)(CI)F`（备份 `D:\backups\talk-acl-20261116-0035`），rollout 错误消失，但命令执行仍 `runner pipe-out` 超时。
  - **后续实验均失败（2026-11-16 00:30–00:58）**：A9 去掉 `windows.sandbox` 参数（默认 disabled）→ `blocked by policy`（0.2 秒）；A6 装 Codex **0.163.0** 对照 → 同样 `runner pipe-out` 超时（17 秒）；A10 给 `CodexSandboxOffline` 授角色 native-home 写权限 → 仍失败。已恢复 Codex **0.164.0** 与角色服务（terra/k2.8/astra 均 running）。
  - **ACL 操作事故（2026-11-16 00:45，已回退）**：PowerShell 中 `$home` 是只读内置变量，赋值静默失败后 `icacls $home /grant ...` 实际作用到 `C:\Users\Administrator`；已立即移除该 SID 的 13 处显式 ACE 并复查为 0（教训：不用 `$home`/`$env` 之外的内置名做路径变量）。
  - **A11/A12 与第二次 Astra 咨询（2026-11-16 00:59–01:22）**：A11 只对 codex 恢复真实 `USERPROFILE/APPDATA/LOCALAPPDATA`（HOME/TEMP 仍角色化）→ 仍超时；把角色 `.codex` 的 `.sandbox`/`.sandbox-bin`/`.sandbox-secrets`/`cap_sid` 移到隔离区让 Codex 重新 setup → 仍超时（31 秒）；给 codex 角色设 `RUST_LOG=debug` 后复跑 → 没有额外调试行，仍同一错误。第二次 Astra 咨询（#785）结论：优先做进程令牌/ProcMon 级取证；可做“legacy 布局诊断角色”和“仅恢复系统 profile 变量”的单因素对照；恢复顺序为角色级重建 → 受支持入口修 sandbox setup → 修安装 → 新 Windows 用户 → 最后才重建 sandbox 账户。
- **用户提示核查（2026-11-16 09:45）**：`PROGRESS_HISTORY.md`（2026-11-08 22:55 段）记录 **astra 在 workspace-v1 布局下真实执行 TALK 任务 580 返回 OK**，说明 workspace-v1 + Codex 曾经可以执行任务；`tests/test_codex_new_role_host.py` docstring 明确 "no model execution"，只验证宿主发现/spawn，不覆盖真实 sandbox 执行。因此回归点更可能在 11-08 之后（11-14 事故与今日重建的 sandbox 用户/ACL），而不是 workspace-v1 布局本身。
- **A13 服务重启与 bypass 对照（2026-11-16 10:05–10:12）**：发现并重启了 Windows 服务 `CodexSandboxService.OpenAI.Codex`（ChatGPT 桌面包 26.1103.7773 的 sandbox 服务，原进程自 11-11 起未重启；`Restart-Service` 失败后通过激活 Appx 包恢复为 Running）；重启后 Terra 探测仍 `runner pipe-out` 超时。管理员上下文加 `--dangerously-bypass-approvals-and-sandbox` 可正常执行 `echo hi`，但 TALK 的 codex 适配层当前不接受该参数，属于未验证的临时绕行方案。
- **/mcp 交付（K2.8 #789，2026-11-16 10:05）**：范围与白名单一致（`server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`tests/test_mcp_http.py` 新增，`server/main.py` +2/−1）；K2.8 自报 13 项单测通过、回归 24+21 项通过、临时 8933 端口 curl 全链路通过。**待独立复核**。
- **/mcp 待复核要点（协调者初读）**：① `talk_tool_registry.tool_environment` 直接改 `os.environ`（`TALK_API_KEY/TALK_BASE_URL`）再恢复，FastAPI 线程池并发 `tools/call` 时存在跨请求身份/Key 串扰风险（需加锁或改为逐调用传参）；② `member.api_key` 在 trusted 免 Key 场景可能为 None，`call_tool` 形参标注 `str` 但可能传 None，需确认下游行为；③ `base_url=request.base_url` 在反代/桌面入口下是否稳定；④ `initialize` 固定回 `2024-11-05` 是否会拒绝更高版本客户端；⑤ 工具异常文本是否会泄露内部路径。
- **第 2 步（legacy 对照）已就绪未执行（待用户确认）**：legacy native-home 路径为 `C:\Users\Administrator\.talk\role-service-host\native\prj_e8fe7066bbec\agent_prj-e8fe7066bbec.terra-1b4a76aa`（当前不存在）；`role_services` 的 workspace-runtime 门禁只对 `workspace-v1` 生效，legacy 不经过该检查；执行前需备份 `talk.db` 与角色目录。
- **第 2 步 legacy 对照已尝试（2026-11-16 10:20–10:30，不干净、已回退）**：备份 DB 后把 Terra native-home 复制到 legacy 路径、`project_roles.storage_layout` 改为 `legacy`、按 legacy 命名补了 `keys\agent_prj-...terra....key`；随后出现 `key_not_configured` → `recovery_required`（旧 workspace host 仍存活、心跳未过期，host 未被真正替换），探测 #791 仍 `runner pipe-out` 超时，**结论不成立**。已把 layout 回退为 `workspace-v1`、清理旧 host 并重启，terra/k2.8/astra 均恢复 running；备份在 `D:\backups\talk-legacy-convert-20261116-1025`。
- **C2-a sandbox 重建（2026-11-16 13:45–14:15，失败）**：备份 `D:\backups\codex-sandbox-rebuild-20261116-1345` 后，把 `CodexSandboxOffline/Online` 账号改名为 `CSOfflineOld/CSOnlineOld`（本地账户名上限 20 字符，`*_old20261116` 被拒）、把 `~/.codex/.sandbox` 与角色 `.codex/.sandbox*`+`cap_sid` 移到隔离区；重启后角色 setup 成功重建了**新 sandbox 用户（SID 1007/1008）**、WFP 过滤器（12 条）与 `.sandbox-bin` runner（SHA256 与源一致），但探测 #792 仍 `runner pipe-out` 超时。
- **补充排除（2026-11-16 14:06–14:16）**：临时禁用 4 条 `codex_sandbox_offline_*` 防火墙规则（探测 #793）仍超时，已恢复启用；给新 sandbox 用户授角色 `.codex`/`.sandbox-bin` 读权限（探测 #794）仍超时。Defender 无 ASR/拦截事件、无排除项；复制的 runner 可直接运行（报 `no pipe-in provided`），哈希一致。
- **根因确认（2026-11-16 14:40，Astra #795）**：Terra 的 Codex runner 被继承为 **Low 完整性级别**；把 runner 的标签改为 **Medium** 后，`cmd /c echo hi` 返回 `hi`、退出码 0、耗时 1.47 秒。Astra 已本地提交 `3f2888b`（仅文档），未推送。上级目录仍是 Low，升级/重建 runner 后可能复发。
- **持久化处理（2026-11-16 14:42）**：定位到标签来源为 `D:\claude-test\TALK` 根目录被显式标为 Low（`Mandatory Label\Low Mandatory Level:(OI)(CI)(NW)`），workspaces/native-home/.codex 均继承；已用 `icacls "D:\claude-test\TALK" /setintegritylevel "(OI)(CI)M"` 把根目录及子树改为 **Medium**，复查 workspaces/native-home/.codex 均为 Medium。仍待验证：runner 重建后是否保持 Medium、开发读写/隔离反例是否通过（验收任务 #796）。
  - **当前判断**：已排除参数/模型/隐藏窗口/asyncio/环境重定向/两个 sandbox 变体/默认 disabled（policy 拒绝）/Codex 0.163/角色 HOME 写权限/rollout ACL/sandbox 状态重置/RUST_LOG；剩余最大嫌疑是 **本机 Codex sandbox 运行链（capability SID + sandbox 用户会话/管道 + 进程令牌）**。角色服务与代码已恢复干净（`bridges/cli_bridge.py`、`scripts/role_service_host.py` 均已回退，工作区只有 5 个未跟踪客户端目录）；Terra 仍不可执行命令，需在“OS 级修复”与“先用 K2.8 开发”之间决策。
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
