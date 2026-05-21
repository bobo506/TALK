# Project Progress

## Latest
Updated: 2026-05-21 16:54 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `CLI-BRIDGE-1` 已完成：新增 `bridges/cli_bridge.py` 通用 CLI bridge，实现成员注册、实例状态上报、消息触发、任务队列轮询、任务认领、CLI stdin/stdout 调用、结果回复与任务完成。
- `bridges/codex_bridge.py` 已改为复用通用 CLI bridge 的 Codex 兼容入口，保留 `--codex-command`、默认 `codex exec` 命令和原 helper 兼容面。
- 新增 `tests/test_cli_bridge.py` 覆盖通用 CLI 参数、prompt、命令执行、回复格式与 queued task 完成路径；Codex 旧测试继续通过。
- `docs/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步通用 CLI bridge、Codex 兼容入口和 pi 接入方向。

### 3) Open Questions / Pending Confirmation
- 用户方向判断已确认：先把 Codex bridge 泛化为通用 CLI bridge，是更快跑通 Codex + pi 双 Agent 的路线。
- pi 的具体 CLI 启动命令 / stdin/stdout 协议仍需确认；如果 pi 不能直接从 stdin 读 prompt 并向 stdout 写最终回复，需要补一个很薄的 pi adapter。
- Group 删除 / 归档语义仍需项目管理者确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- 未读/关注状态、文档编辑锁仍待实现。

### 4) Next Plan
1. 提交本次 `CLI-BRIDGE-1` 切片。
2. 下一切片建议：基于 `bridges/cli_bridge.py` 落一个 `pi` 启动示例 / adapter，并用 fake CLI 或真实 pi 命令跑通 `agent:codex <-> agent:pi` 的最小任务回合。
3. 若 pi 命令可直接适配 stdin/stdout，可优先做配置与验收脚本；否则先实现 pi adapter。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge` passed，13 tests。
- `.venv\Scripts\python.exe bridges\cli_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，102 tests。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
