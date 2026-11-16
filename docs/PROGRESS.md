# Project Progress

## Latest

Updated: 2026-11-16 17:35 (+08:00)

**当前结论**：第 3 项 HTTP MCP `/mcp` 已完成（K2.8 开发、Terra 独立复核 4 轮后 **approved**，提交 `2be7a3f`）；Terra 的 Codex 命令执行已恢复（根因：runner 继承 Low 完整性标签，改 Medium 后正常；已把仓库根目录及子树统一为 Medium）。`/mcp` 代码已入库，但生产 `8000` 仍运行旧代码，**未重启 API**，端点尚未对外生效。

### 1) Current Progress
- 路线图 13 项：第 1（角色 Key 恢复）、第 2（四终端 MCP 接入）、第 3（HTTP `/mcp`）已完成；第 4→13 项待推进。
- 角色：Terra（codex，`gpt-6.1-terra`）、K2.8（kimi-code，`kimi-for-coding`）、Astra（codex，仅咨询）均 running；Terra 命令/读写能力已验收（#796/#797）。
- 终端发起身份：`agent:codex-t` / `kimi-t` / `dsh-t` / `workbuddy-t` 已建立并接入 MCP。
- `/mcp` 交付：`server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`（32 项）；`server/main.py` 注册；`bridges/talk_task_tools.py`/`initiator_followup.py` 增加 contextvar 优先、env 兜底。
- 安全设计：回调地址只信 ASGI scope 或配置 loopback URL；工具级失败只回静态消息，完整异常写日志；四方法 params 统一校验；客户端不回传原始异常文本。
- 运行环境：Codex CLI 钉 `0.164.0`；Kimi Code CLI `2.0.2`；Terra runner 与仓库根目录完整性标签为 **Medium**（手动修复，重建/升级后需复查）。

### 2) Open Questions / Pending Confirmation
- 无。下一片（第 4 项）范围与验收需按惯例先向用户确认。
- 已知环境限制：`test_runtime_log_authentication` 在 Terra 沙箱运行环境返回 503；管理员上下文单独运行 1 passed in 3.01s，判定为环境限制，非 `/mcp` 代码问题。

### 3) Next Plan
- 第 4 项：启动器检测已安装运行器（Codex/KimiCode/WorkBuddy/DSH），幂等生成/更新 MCP 配置与成员（已存在则跳过，不重复写）。
- 分工恢复：**Terra 开发、K2.8 复核**；协调者只做范围/授权/判断与收尾。
- 后续顺序：第 5 项（启动器按检测结果登记并启动执行侧 role host）→ 6→13。

### 4) Verification
- `pytest tests/test_mcp_http.py -q`：32 passed（Terra 终验 #806 与 K2.8 #805 各自复跑）。
- `pytest tests/test_talk_task_tools.py -q`：21 passed；`tests/test_auth_trusted.py tests/test_talk_terminal_mcp.py`：Terra 环境 23 passed + 1 已知 503，K2.8 环境 24 passed。
- Terra 能力：`echo hi` 1.31s、`git status` 1.48s、`python -c` 1.34s；临时目录与工作区写入 3.02s/2.96s；写 `.codex` 按预期被拒绝。
- 未验证：生产 `8000` 未重启，`/mcp` 尚未在真实生产进程验证；反代/桌面入口未实测。

### 5) Changed Files
- 新增：`server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`。
- 修改：`server/main.py`、`bridges/talk_task_tools.py`、`bridges/initiator_followup.py`、`docs/PROGRESS.md`、`docs/PROGRESS_HISTORY.md`。
- 提交：`2be7a3f`（/mcp）；此前 `3f2888b`（Astra 的 runner 标签记录）、`278c681`、`e72ef4b` 等文档提交。

## Recent Notes
- 归档/备份：`D:\backups\codex-sandbox-rebuild-20261116-1345`、`D:\backups\talk-acl-20261116-0035`、`D:\backups\talk-legacy-convert-20261116-1025`；诊断日志 `D:\agent-trash\talk-diag\codex-spawn.log`。
- 临时目录：仓库根仍有 `.tmp-acceptance`（历史）与 `.tmp-tests`（含 `mcp-799-archive`）；均未跟踪，未清理。
- 恢复：说“继续项目”。
- 环境事件（2026-11-14 22:51）：系统 Python `Lib` 被便携运行时覆盖；已补 `python312.zip` 与 4 个 `.pyd`，依赖在 `Python312\talk-deps`。全局 `pip` 未装回。
- 运行器环境（2026-11-15）：Codex CLI 临时钉 `0.164.0`；Kimi Code CLI 2.0.2（`~/.kimi-code/bin/kimi.exe` 与 `%APPDATA%\npm\kimi.exe`）。新版本适配见路线图第 12 项。
- 事故相关：桌面误删清单 `D:\desktop-deleted-20261114.txt`；本机沙箱/服务重建记录见 `PROGRESS_HISTORY.md` 2026-11-16 各段。
