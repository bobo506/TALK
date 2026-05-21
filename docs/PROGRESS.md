# Project Progress

## Latest
Updated: 2026-05-21 17:35 (Asia/Shanghai)

### 1) Current Agent Role
- 角色来源：`AGENTS.md`。
- 当前 Codex 角色：决策 Agent。
- 当前 Claude 角色：执行 Agent。

### 2) Current Progress
- `BRIDGE-WINDOWS-CMD-1` 验收期修复已完成：修复 Windows 下 bridge 直接调用 `codex` / `pi` 找不到命令的问题。
- `bridges/cli_bridge.py` 在启动子进程前会用 `shutil.which()` 解析命令入口，使 `pi` 可解析到 `pi.CMD`。
- `bridges/codex_bridge.py` 默认优先使用 `~\AppData\Local\OpenAI\Codex\bin\codex.exe`，避免命中 WindowsApps 中会 `Access is denied` 的 `codex.exe`。
- `PI-BRIDGE-1` 已完成：新增 `bridges/pi_bridge.py`，默认注册 `agent:pi`，默认 runtime 为 `pi`，默认调用 `pi --print --mode text`。
- 通用 `bridges/cli_bridge.py` 已支持 `--prompt-transport stdin|argv`：Codex 继续用 stdin；pi 默认用 argv，把 TALK prompt 追加为最后一个命令行参数。
- 新增 `tests/test_pi_bridge.py`，并扩展 `tests/test_cli_bridge.py` 覆盖 argv prompt 传递与 pi queued task 路径。
- 本机已确认 `pi --help` 与 `pi --version` 可执行，版本为 `0.74.1`。
- `docs/MODULE_bridges.md` 与 `docs/PROJECT_BRIEF.md` 已同步 pi bridge 入口、启动命令和当前边界。

### 3) Open Questions / Pending Confirmation
- 用户在前端 `@agent:codex` / `@agent:pi` 后未收到回复；已定位为 bridge 本地命令启动失败，数据库中两个实例均曾上报 `[WinError 2] 系统找不到指定的文件。`。需重启 bridge 后重新发送消息验收。
- 真实 pi 模型调用仍依赖本机 `pi` 的 provider/API key 配置；本轮未消耗真实模型请求，只验证 CLI 入口与桥接参数。
- Codex + pi 双 Agent 同时运行的真实端到端回合尚未执行；下一步应进入人工验收或补一个双桥 smoke 脚本。
- 本里程碑验收必须同时覆盖 Web UI：此前 Web UI 第一版质量不达标，后续已按 `image_gen` 视觉稿方向重做并记录在 `docs/MODULE_webui.md` 的 `WEB-VISUAL-2 Addendum`，需要和双 Agent bridge 一起验收。
- Group 删除 / 归档语义仍需项目管理者确认：历史 Hall 消息应保留、归档还是随 Group 删除。
- Schedule 当前仅记录并显式物化，不内置后台调度循环；后续需决定由 bridge 轮询、系统定时脚本，还是服务端后台 worker 触发。
- 未读/关注状态、文档编辑锁仍待实现。

### 4) Next Plan
1. 提交本次 `BRIDGE-WINDOWS-CMD-1` 验收期修复。
2. 重启 Codex / pi bridge，再在前端重新发送 `@agent:codex` 与 `@agent:pi` 消息。
3. 按里程碑门禁暂停，继续 Codex + pi 双 bridge 与 Web UI 视觉/交互的联合人工验收。

### 5) Verification
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge` passed，18 tests。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_encoding` passed，3 tests。
- `git diff --check` passed（仅换行提示）。
- `.venv\Scripts\python.exe -m py_compile bridges\cli_bridge.py bridges\codex_bridge.py bridges\pi_bridge.py tests\test_cli_bridge.py tests\test_codex_bridge.py tests\test_pi_bridge.py` passed。
- `.venv\Scripts\python.exe -m unittest tests.test_cli_bridge tests.test_codex_bridge tests.test_pi_bridge tests.test_encoding` passed，19 tests。
- `.venv\Scripts\python.exe bridges\pi_bridge.py --help` passed。
- `.venv\Scripts\python.exe bridges\codex_bridge.py --help` passed。
- `pi --help` passed。
- `pi --version` returned `0.74.1`。
- `.venv\Scripts\python.exe -u -m unittest -v` passed，105 tests。
- `git diff --check` passed（仅换行提示）。
- `scripts/check-progress.ps1` 与 `scripts/check-git-ready.ps1` 当前工作树不存在，本轮无法运行这两个历史门禁脚本。

### 6) Changed Files
- `bridges/cli_bridge.py`
- `bridges/codex_bridge.py`
- `tests/test_cli_bridge.py`
- `tests/test_codex_bridge.py`
- `bridges/pi_bridge.py`
- `bridges/cli_bridge.py`
- `tests/test_pi_bridge.py`
- `tests/test_cli_bridge.py`
- `docs/MODULE_bridges.md`
- `docs/PROJECT_BRIEF.md`
- `docs/PROGRESS.md`
- `docs/PROGRESS_HISTORY.md`

## Recent Notes
- 完整历史见 `docs/PROGRESS_HISTORY.md`。
