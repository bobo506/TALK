# Project Progress

## Latest

Updated: 2026-11-16 20:05 (+08:00)

**当前结论**：第 4 项“启动器自动检测运行器并幂等接入 MCP”已完成（Terra 开发、K2.8 复核；切片 A `c033683`、切片 B `c73587f`）。第 3 项 `/mcp` 已在库（`2be7a3f`）；生产 `8000` 仍运行旧代码，`/mcp` 尚未对外生效，需重启 API。

### 1) Current Progress
- 路线图 13 项：第 1（角色 Key 恢复）、第 2（四终端 MCP 接入）、第 3（HTTP `/mcp`）、第 4（启动器自动接入 MCP）已完成；第 5→13 项待推进。
- 角色：Terra（codex，`gpt-6.1-terra`）、K2.8（kimi-code，`kimi-for-coding`）、Astra（codex，仅咨询）均 running；Terra 命令/读写能力已验收（#796/#797）。
- 终端发起身份：`agent:codex-t` / `kimi-t` / `dsh-t` / `workbuddy-t` 已建立并接入 MCP。
- 第 4 项交付：`scripts/mcp_onboarding.py`（四类检测、key 发现兼容 `-t`/`_t`、四端 stdio 配置生成、幂等、备份、只读成员检查、`--check/--apply`）、`tests/test_mcp_onboarding.py`（24 项）、`scripts/talk_desktop.py` 启动前调用（失败仅告警）、`tests/test_talk_desktop.py`（19 项 + 3 subtests）。
- `/mcp` 交付：`server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`（32 项）；`server/main.py` 注册；工具层 contextvar 优先、env 兜底。
- 运行环境：Codex CLI 钉 `0.164.0`；Kimi Code CLI `2.0.2`；Terra runner 与仓库根目录完整性标签为 **Medium**（手动修复，重建/升级后需复查）。

### 2) Open Questions / Pending Confirmation
- 无。第 5 项范围与验收需按惯例先确认。
- 已知限制：本切片不创建成员（缺失只报 `member_missing`）；真实 HOME 的 `--apply` 未执行（验收用临时 HOME/repo）；真实桌面窗口未实测。
- 已知环境限制：`test_runtime_log_authentication` 在 Terra 沙箱运行环境返回 503；管理员上下文单独运行 1 passed in 3.01s，判定为环境限制。

### 3) Next Plan
- 第 5 项：启动器按检测结果登记并启动执行侧 role host（角色运行器）。
- 分工：**Terra 开发、K2.8 复核**；协调者只做范围/授权/判断与收尾。
- 后续顺序：第 6 项（GUI 合并启动）→ 7→13。

### 4) Verification
- `pytest tests/test_mcp_onboarding.py -q`：24 passed；`pytest tests/test_talk_desktop.py -q`：19 passed + 3 subtests。
- 真实 `--check`：exit 0、303ms、四个 `-t` 成员均在 `members_ok`、`configs_written=[]`、无 Key 输出；真实四端配置 md5/mtime/大小不变、无新增 `.bak`。
- `pytest tests/test_mcp_http.py -q`：32 passed；`tests/test_talk_task_tools.py`：21 passed。
- 未验证：生产 `8000` 未重启（`/mcp` 未生效）；真实 HOME `--apply`、真实客户端加载、桌面窗口均未实测。

### 5) Changed Files
- 第 4 项：新增 `scripts/mcp_onboarding.py`、`tests/test_mcp_onboarding.py`；修改 `scripts/talk_desktop.py`、`tests/test_talk_desktop.py`。
- 第 3 项：新增 `server/routes/mcp.py`、`bridges/talk_tool_registry.py`、`bridges/talk_call_context.py`、`tests/test_mcp_http.py`；修改 `server/main.py`、`bridges/talk_task_tools.py`、`bridges/initiator_followup.py`。
- 提交：`c033683`、`c73587f`（第 4 项）；`2be7a3f`（第 3 项）；docs 提交 `f461eff` 等。

## Recent Notes
- 归档/备份：`D:\backups\codex-sandbox-rebuild-20261116-1345`、`D:\backups\talk-acl-20261116-0035`、`D:\backups\talk-legacy-convert-20261116-1025`；诊断日志 `D:\agent-trash\talk-diag\codex-spawn.log`。
- 临时目录：仓库根仍有 `.tmp-acceptance`（历史）与 `.tmp-tests`（含 `mcp-799-archive`）；均未跟踪，未清理。
- 恢复：说“继续项目”。
- 环境事件（2026-11-14 22:51）：系统 Python `Lib` 被便携运行时覆盖；已补 `python312.zip` 与 4 个 `.pyd`，依赖在 `Python312\talk-deps`。全局 `pip` 未装回。
- 运行器环境（2026-11-15）：Codex CLI 临时钉 `0.164.0`；Kimi Code CLI 2.0.2（`~/.kimi-code/bin/kimi.exe` 与 `%APPDATA%\npm\kimi.exe`）。新版本适配见路线图第 12 项。
- 事故相关：桌面误删清单 `D:\desktop-deleted-20261114.txt`；本机沙箱/服务重建记录见 `PROGRESS_HISTORY.md` 2026-11-16 各段。
