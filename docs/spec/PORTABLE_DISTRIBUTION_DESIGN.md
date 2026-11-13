# TALK 免安装文件夹分发设计（2026-11-13 方案草案）

> 状态：方案草案；**阶段 1 已实现（2026-11-13，`1b2392b`，735-737 approved）**，阶段 2-4 未实现，不构成后续开工授权。目标形态是“拷贝一个文件夹即可使用”，不做安装包、Windows 服务或托盘常驻；提供一个随文件夹分发的**便携桌面窗口启动器**：点击启动 TALK 服务并打开桌面窗口，关闭窗口即退出服务（2026-11-13 用户补充）。

## 1. 决策与目标

- 2026-11-13 用户决定：**14 不走安装流程**，改为免安装文件夹分发；13 外部桌面运行器不做，暂时全部使用 CLI 接入；17 WorkBuddy ACP 5.9.3 适配关闭。
- 目标：
  1. 把 TALK 产品代码、Python 运行时、默认配置和启动脚本放进一个文件夹；
  2. 拷贝到另一路径/另一台 Windows 机器后，双击启动脚本即可完成首次初始化并打开页面；
  3. 数据、日志、上传、宿主状态都在文件夹内，便于整体搬移和备份；
  4. 升级时替换程序文件、保留数据与配置；
  5. 不把真实 Key、开发机绝对路径、测试产物带进分发包；
  6. 提供便携桌面窗口启动器：点击启动服务并打开 TALK 桌面窗口，关闭窗口即退出服务；打开页面后按运行器/角色状态弹窗提示（详见 §6/§7）。
- 非目标：自动更新服务、多用户服务器部署、内置 Codex/Kimi/DSH 客户端、WorkBuddy 内置 ACP、macOS/Linux 首版；不做安装包、Windows 服务、托盘常驻；桌面窗口启动器是便携程序，不是安装型应用外壳。

## 2. 现状阻碍（实测）

| 位置 | 当前事实 | 免安装需要 |
|---|---|---|
| `run.ps1` | 固定 `.venv/Scripts/python.exe` | 使用随附 Python 或可配置解释器 |
| `.venv` | 依赖开发机基础 Python，venv 不可靠跨机复制 | 随附 embeddable Python + site-packages，或明确要求系统 Python |
| `config.toml` | `db_path=D:/claude-test/TALK/talk.db`；`storage/log/backup` 相对；`runtime_diagnostics.sources`、`backend_diagnostics` 写死 `D:/claude-test/TALK` | 生成相对/`TALK_HOME` 派生路径；去掉开发机诊断源 |
| `D:\claude-test\TALK-private\talk-runtime.json` | 运行清单在仓库外，含 `project_root`、`key_root`、`state_dir`、`operator_key_file`、固定 `hosts` | 迁到 `config/runtime.json`，路径由 `TALK_HOME` 派生；新装不配置 legacy 固定宿主 |
| `TALK-private\keys`、`C:\Users\...\.talk\keys` | 两套 Key 目录并存 | 统一 `TALK_KEYS_DIR`（默认便携文件夹外，见 §6） |
| `C:\Users\...\.talk\role-service-host` | 宿主状态、health、native session | 迁到 `data/state` |
| `D:\claude-test\TALK\talk.db`、`storage`、`logs`、`backups` | 开发实例数据 | 迁到 `data/` |
| `workspaces/` | workspace-v1 角色数据 | 迁到 `data/workspaces` |
| `.talk/project.yaml` | 开发项目元数据 | 首次启动在项目根生成；不复制开发项目 |
| Codex/Kimi/DSH CLI | 系统安装、登录独立维护 | 分发前检测并给出安装/登录提示；不打包 vendor CLI |
| 仓库体积 | 当前约 71.8 GB（含 `.venv`、`.tmp*`、测试产物、workspaces、日志） | 构建脚本按 allowlist 复制，严禁整仓打包 |

## 3. 推荐目录布局

```text
TALK/
  server/ web/ scripts/ bridges/ cli/ docs/ examples/   # 产品代码
  requirements.txt
  README.md
  VERSION

  runtime/
    python/                    # embeddable Python 3.12 x64
      python.exe
      Lib/site-packages/       # pip --target 安装的依赖
      python312._pth           # 包含 app root 与 site-packages

  config/
    config.toml                # 首次启动生成；相对路径
    runtime.json               # 首次启动生成；相对路径

  data/
    talk.db                    # SQLite WAL
    storage/                   # 上传文件
    logs/                      # talk.log、runtime 日志
    backups/                   # DB 备份
    state/                     # role-service-host（宿主/runtime/native）
    workspaces/                # workspace-v1 角色数据
    project/                   # 默认项目根（见 §5）

  start.bat                   # 启动桌面窗口启动器（无窗口参数时回退浏览器）
  TALK.exe                    # 便携桌面窗口启动器（或 launcher/launcher.py）
  stop.bat
  status.bat
  README-PORTABLE.txt
```

- 产品代码仍从仓库根运行；`runtime/python`、`data`、`config` 与代码分离，升级只替换代码和 runtime。
- 不设置 `keys/` 在分发包内为默认（见 §6）。

## 4. 路径与配置规则

- 所有入口先 `cd /d "%~dp0"`，并导出 `TALK_HOME=<文件夹绝对路径>`；配置中不写开发机绝对路径。
- `config.toml`：便携模式放在 `config/config.toml`，由启动脚本设置 `TALK_CONFIG` 指向它；`server/db.py` 增加 `TALK_CONFIG` 环境变量支持，未设置时回退仓库根 `config.toml`（开发实例兼容）。配置中的相对路径按 `TALK_HOME`/启动 cwd 解析，由首次启动生成：
  - `db_path = "./data/talk.db"`；`storage_dir="./data/storage"`；`logging.path="./data/logs/talk.log"`；`backup.dir="./data/backups"`；
  - 删除开发机的 `runtime_diagnostics.sources` 与 `backend_diagnostics` 绝对路径；如需要，按 `TALK_HOME` 生成或留空。
  - 默认 `auth_mode="trusted"`、`trusted_networks=["loopback"]`，仅本机可信；局域网使用由用户显式放宽。
- `config/runtime.json` 由首次启动生成，至少包含：
  - `project_id`、`project_root`（默认 `data/project`）、`base_url`、`operator_key_file`、`key_root`、`state_dir`；
  - `api_argv` 使用 `runtime/python/python.exe -m scripts.talk_api ...`；
  - `hosts: []`（新装不使用 legacy 固定宿主）；
  - `provision_worker: true`；runner 配方 `codex`/`kimi`/`dsh`（按检测到的 CLI 路径）；`workbuddy` 不启用。
- `.talk/project.yaml` 在默认项目根生成；项目根与代码根分离，避免升级覆盖用户文件。若 `api_argv` 的 `-m` 需要代码根，启动脚本设置 `PYTHONPATH` 为 `TALK_HOME`（实现阶段需验证 `talk_runtime` 对 API 子进程的 cwd/PYTHONPATH 处理）。
- 所有路径只从 `TALK_HOME`/配置派生；构建后对分发包做 `D:\claude-test`、`C:\Users\Administrator` 等字符串扫描。

## 5. 首次启动流程

`start.bat`：

1. 检查 `runtime/python/python.exe`、`config/`、`data/`；
2. 若未初始化：
   - 生成 `TALK_KEYS_DIR/operator.key`（默认见 §6）；
   - 初始化数据库（建表）；
   - 创建首个 human 管理员（复用 `scripts/create_admin.py` 或直接调用服务层），显示一次 Key/提示；
   - 生成 `config.toml`、`config/runtime.json`；
   - 生成默认项目根 `data/project`，运行 `python -m cli.talk init` 注册项目并生成 `.talk/project.yaml`；
   - 检测 runner CLI（`codex`、`kimi`、`dsh`）并写入运行时配置；缺失只提示，不阻止启动；
3. 检查 8000 端口/单实例锁；默认启动 `TALK.exe` 桌面启动器；启动器启动 `talk_runtime serve --config config/runtime.json --apply`（受控持有/监控）并等待 `/healthz`；无 WebView2 或命令行回退时，改为 `--detach` + 系统浏览器，并提示窗口/关闭行为差异；
4. `/healthz` 成功后由启动器打开桌面窗口（`http://127.0.0.1:8000/`）；失败时保留日志并给出明确原因（端口占用、Python 缺失、DB 迁移失败、runner 未配置）。
5. 失败时保留日志并给出明确原因（端口占用、Python 缺失、DB 迁移失败、runner 未配置）。

`stop.bat`：`talk_runtime stop --apply --wait`，等待并报告结果。
`status.bat`：只读 `talk_runtime status` + `healthz`。

## 5.1 桌面窗口启动器（2026-11-13 用户补充）

目标：点击启动器 → 启动 TALK 服务 → 在**桌面窗口**（非浏览器标签页）打开 TALK → 关闭窗口即退出服务。

### 技术选项

| 方案 | 说明 | 取舍 |
|---|---|---|
| **A. pywebview + Edge WebView2（推荐）** | 随附 Python 运行；原生窗口嵌入 WebView2；关闭窗口由 Python 进程收尾 | 需要目标机有 WebView2 Runtime（Win10/11/Edge 常见）；`pywebview` + `pythonnet` 进依赖；无浏览器地址栏 |
| B. Edge/Chrome `--app` + 关闭探测 | 轻量，无额外 webview 依赖；以 app 窗口打开 | 本质仍是浏览器引擎/进程；关闭窗口的探测不稳定；可能残留后台进程 |
| C. C# WinForms/WPF + WebView2 | 原生 exe，行为最可控 | 需额外 .NET/WebView2 构建链，与 Python 打包分离 |

- 首版推荐 A；如果目标机缺少 WebView2 Runtime，启动器明确提示安装（或回退 B 并说明差异），不能静默失败。
- 启动器与 TALK 服务同目录；窗口标题/图标使用 TALK；外部链接交给系统浏览器，窗口内只允许 `http://127.0.0.1:<port>`。

### 生命周期

1. 启动器单实例：已有一个启动器窗口时，第二次点击聚焦/提示，不启动第二个服务。
2. 服务未运行：启动 `talk_runtime serve --config config/runtime.json --apply`（由启动器持有/监控），轮询 `/healthz`；失败弹窗显示原因。
3. 页面：打开 `http://127.0.0.1:8000`；默认 trusted loopback 无需登录；key 模式显示登录页，由用户在窗口内输入。
4. 关闭窗口：
   - 先尝试优雅 `talk_runtime stop --apply --wait`；
   - 有运行中任务/停止被阻塞时，弹窗提示，**默认取消关闭并保持服务**；用户明确确认后才继续（遵守现有忙任务停止守卫，不强制杀）；
   - 服务不是本次启动器拉起的（已由外部运行）时，询问“只关闭窗口/同时停止服务”，默认只关闭窗口；
   - 停止完成后退出启动器。
5. 启动器崩溃/被强杀：服务可能仍在；`status.bat`/`stop.bat` 可查看/停止；下次启动器发现已运行则附挂。
6. 不安装 Windows 服务、不写开机启动、不做托盘常驻。

### 登录与安全

- 默认只绑定 `127.0.0.1`；窗口只访问回环地址。
- key 模式不在启动器内嵌凭据；由用户在窗口登录页输入。
- WebView2 使用独立 profile（建议 `data/launcher-profile`），不读取系统浏览器 Cookie/Key。
- 启动器不提供任意 URL 导航、本地文件访问或开发者工具入口（可选调试开关仅开发包）。

## 5.2 运行器检测弹窗（2026-11-13 用户补充）

打开页面/项目后检测本机运行器与项目角色数，用弹窗提示。数据来源：

- `GET /api/runners/versions`：各运行器是否探测到、版本、与 TALK 验证基线关系（现有接口）；
- `GET /api/projects/{project}/agents`：项目角色数；
- 需要后端补充一个只读的“已适配/支持”标记，或由前端使用固定 allowlist（Codex、Kimi Code、DSH；WorkBuddy 内置 ACP 按 17 关闭，不计入）。

### 判定与文案

1. **项目角色数为 0，且至少一个“已适配且本机可用”的运行器**：
   `已适配 Codex、Kimi Code 运行器，可创建角色`（多个用顿号/逗号分隔；只列真正可用的）。
   按钮：`创建角色`（跳到创建角色）、`知道了`。
2. **没有“已适配且本机可用”的运行器**：
   `缺少 Codex、Kimi Code、DSH 运行器，请先安装或适配其他运行器`（列出 TALK 支持的运行器；缺哪个列哪个）。
   按钮：`查看运行器状态`（项目设置）、`知道了`。
3. 项目已有角色：**不显示条件 1 的“可创建角色”提示**（避免重复打扰）；条件 2 是否仍显示见待确认项。
4. 探测失败/未知：不要误报“缺少”；显示“运行器状态未知，请检查运行器版本/路径”，或只保留设置面板提示（待确认）。

### 交互

- 使用现有 modal 组件；每个项目/每次启动器会话最多弹一次；`知道了` 后本会话不再弹；创建角色后自动不再满足条件 1。
- 弹窗不阻塞页面操作；不自动改绑定、不自动安装/登录运行器。
- 运行器名称使用产品显示名；WorkBuddy 内置不列入“可创建角色”，如检测到 WorkBuddy 仅在设置中显示不支持说明。

## 6. Key 与安全

- **分发包不带真实 Key**；首次启动生成 operator key 与管理员；角色 Key 由创建/恢复流程生成。
- 默认 `TALK_KEYS_DIR = %LOCALAPPDATA%\TALK\keys`（便携文件夹外），避免整个文件夹被复制/转发时泄露；支持 `TALK_KEYS_DIR` 覆盖。
- 若用户要求完全自包含（U 盘搬移），可选 `keys/` 放在 `data/keys`，但 README 必须显著警告“文件夹即凭据”；构建/分发默认不包含。
- 默认 bind `127.0.0.1`；局域网访问需用户显式改配置；日志不输出 Key；`keys` 目录 ACL 仅当前用户。
- 分发包构建后检查：无 `.key`/`credential.json`、无 `.env`、无真实 DB、无 native session。

## 7. 运行时与依赖

- 推荐 **embeddable Python 3.12 x64** + `pip install --target runtime/python/Lib/site-packages -r requirements.txt`；`python312._pth` 写入 `Lib\site-packages`、`TALK_HOME`（或启动脚本设 PYTHONPATH）。
- 备选：随附 venv（体积小，但 `pyvenv.cfg` 依赖基础 Python 路径，跨机不可靠）；或要求系统 Python（不符合“拷贝即用”）。
- `requirements.txt` 当前 8 个直接依赖；SQLite 随 Python 自带。
- 不打包 `tests/`、`.git`、`.tmp*`、`.venv`、`logs`、`backups`、`storage`、`workspaces`、`talk.db`、`.talk`、agent 私有目录。
- 包体预估：代码 + docs + embeddable Python + wheels 约 100–200 MB（构建时实测）。

## 8. 启动、单实例与端口

- 使用现有 `talk_runtime` 的 launcher lock 与 `--detach`；不引入 Windows 服务/计划任务。
- `start.bat` 先检查 8000 端口与本机 runtime 健康：
  - 已运行：直接打开页面/提示；
  - 端口被其它进程占用：失败并提示释放或修改 `config.toml`/`runtime.json` 端口（首版不自动改端口）；
  - 单实例由现有锁和 PID/健康证明保证。
- 启动脚本无控制台弹窗可用 `CREATE_NO_WINDOW`（现有 `talk_runtime` 已处理）。

## 9. 升级、备份与迁移

- 升级：替换 `server/ web/ scripts/ bridges/ cli/ docs/ runtime/python/`；保留 `data/`、`config/`、`TALK_KEYS_DIR`；启动时自动迁移 DB；升级前 `data/backups` 备份。
- 版本：`VERSION` + `config/runtime.json` 版本；不匹配时先备份再迁移。
- 开发实例迁移（可选）：复制 `talk.db`、`storage/`、`keys/`、`workspaces/` 到便携目录；legacy 角色不迁移（按 2026-11-08 决定，正式包只带 workspace-v1）。
- 回滚：保留上一份程序文件夹；数据不回滚，按备份恢复。

## 10. 运行器前提

- CLI：Codex、Kimi Code、DSH 需目标机已安装并登录；TALK 只检测路径/版本/绑定，不打包、不代登录。
- WorkBuddy 内置 ACP 不纳入（17 关闭）；相关角色在便携版创建时应提示不支持。
- 首次启动/项目设置显示检测结果：已找到/未找到/版本未知；不把“未找到”显示为可用。

## 11. 构建与分发

- 新增 `scripts/build_portable.py`（或 `.ps1`）：按 allowlist staging、安装依赖、生成 `runtime/python`、写 start/stop/status、压缩 zip、输出 SHA256。
- 构建后自动检查：
  - 禁止出现 `D:\claude-test`、`C:\Users\Administrator`、真实 Key、`talk.db`、`.tmp`、`.venv`；
  - 启动脚本/配置可解析；
  - zip 可解压到新路径并通过首次启动。
- 分发形式：zip；用户解压到任意目录；不写注册表、不装服务；删除文件夹即卸载（数据在文件夹内，Key 在 `%LOCALAPPDATA%`）。

## 12. 验收清单

1. 把 zip 解压到 `D:\TALK-portable`（与开发目录不同），双击 `start.bat`：首次初始化、页面打开、healthz ok。
2. 在另一个 Windows 用户/机器（无开发 Python、无 `.venv`）重复；只要求已安装支持的 runner CLI。
3. 创建项目/角色、启动 Codex 或 Kimi、派一个真实任务并收取；WorkBuddy 角色显示不支持。
4. 停止/重启：数据、任务、消息、角色、启动偏好保持；只拉起勾选自动启动的角色宿主。
5. 分发 zip 内无真实 Key/DB/开发绝对路径；`TALK_KEYS_DIR` 在文件夹外。
6. 8000 端口被占用时明确失败；第二次 `start.bat` 不重复实例。
7. 升级：替换程序文件、保留 data/config，迁移成功；回滚可用。
8. 删除文件夹后无残留服务/计划任务（Key 目录可另行删除）。
9. **启动器**：双击启动服务并打开桌面窗口；关闭窗口后服务停止、8000 关闭、无残留；有运行中任务时取消关闭或明确确认后才停止；第二次双击不重复启动服务。
10. **运行器弹窗**：项目无角色且有可用已适配运行器 → “已适配 xx 运行器，可创建角色”；无可用运行器 → “缺少 xxx 运行器…”；项目已有角色时不弹“可创建角色”；探测失败不误报缺少；每会话只弹一次。

## 13. 分阶段实施建议

- **阶段 1（已完成，`1b2392b`，735-737 approved）**：路径/配置抽象（`TALK_CONFIG`/`TALK_HOME`/`TALK_KEYS_DIR`）+ 便携目录 + 首次启动 bootstrap + CLI start/stop/status；隔离便携根 startup 已验证。
- **阶段 2（切片）**：桌面窗口启动器（启动服务/打开窗口/关闭即停/单实例）+ 运行器检测弹窗（前端 modal，含条件与去重）。
- **阶段 3（切片）**：embeddable Python + 依赖安装 + 构建脚本/zip + 安全检查。
- **阶段 4（切片）**：干净机器/另一用户 E2E + 升级/迁移 + 文档/用户手册更新。
每片仍按“目的/范围/不变项/验收”先确认；开发和独立复核按项目任务流程执行。

## 14. 待确认决策

1. **Python 运行时**：embeddable（推荐）还是随附 venv/要求系统 Python？
2. **Key 位置**：默认 `%LOCALAPPDATA%\TALK\keys`（推荐，安全）还是文件夹内 `data/keys`（完全自包含，需警告）？
3. **默认项目根**：`data/project`（推荐，代码/数据分离）还是 TALK 文件夹根（兼容当前）？
4. **默认鉴权**：只信任 loopback（推荐）还是默认 trusted private？
5. **端口冲突**：明确失败（推荐）还是自动换端口？
6. **分发内容**：是否包含 `docs/`（建议包含）与 `tests/`（建议不包含）？
7. **首版平台**：仅 Windows x64（建议）还是同时考虑 Linux？
8. **启动器技术**：pywebview + WebView2（推荐）还是 Edge app 窗口/C# WebView2？
9. **关闭时忙任务**：取消关闭并保持服务（推荐，遵守忙停止守卫）还是提示后强制停止？
10. **服务已在外部运行**：启动器只附挂、关闭窗口不停止（推荐）还是关闭时一并停止？
11. **弹窗条件 2**：无可用运行器时，项目已有角色是否仍弹（建议仍弹一次，避免角色无法执行）；“已适配”是否要求本机已安装（建议是，避免“可创建”误导）。
12. **弹窗频率**：每项目/每启动器会话一次（推荐）还是每次刷新都弹？
