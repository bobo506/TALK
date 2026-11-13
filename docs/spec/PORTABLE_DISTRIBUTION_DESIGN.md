# TALK 免安装文件夹分发设计（2026-11-13 方案草案）

> 状态：方案草案，未实现，不构成开工授权。目标形态是“拷贝一个文件夹即可使用”，不做安装包、Windows 服务、托盘程序或应用外壳。

## 1. 决策与目标

- 2026-11-13 用户决定：**14 不走安装流程**，改为免安装文件夹分发；13 外部桌面运行器不做，暂时全部使用 CLI 接入；17 WorkBuddy ACP 5.9.3 适配关闭。
- 目标：
  1. 把 TALK 产品代码、Python 运行时、默认配置和启动脚本放进一个文件夹；
  2. 拷贝到另一路径/另一台 Windows 机器后，双击启动脚本即可完成首次初始化并打开页面；
  3. 数据、日志、上传、宿主状态都在文件夹内，便于整体搬移和备份；
  4. 升级时替换程序文件、保留数据与配置；
  5. 不把真实 Key、开发机绝对路径、测试产物带进分发包。
- 非目标：自动更新服务、多用户服务器部署、内置 Codex/Kimi/DSH 客户端、WorkBuddy 内置 ACP、macOS/Linux 首版。

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

  start.bat
  stop.bat
  status.bat
  README-PORTABLE.txt
```

- 产品代码仍从仓库根运行；`runtime/python`、`data`、`config` 与代码分离，升级只替换代码和 runtime。
- 不设置 `keys/` 在分发包内为默认（见 §6）。

## 4. 路径与配置规则

- 所有入口先 `cd /d "%~dp0"`，并导出 `TALK_HOME=<文件夹绝对路径>`；配置中不写开发机绝对路径。
- `config.toml` 保持在仓库根（`server/db.py` 现有读取位置），由首次启动生成：
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
3. 检查 8000 端口/单实例锁；启动 `talk_runtime serve --config config/runtime.json --apply --detach`；
4. 轮询 `/healthz`，成功后打开 `http://127.0.0.1:8000/`；
5. 失败时保留日志并给出明确原因（端口占用、Python 缺失、DB 迁移失败、runner 未配置）。

`stop.bat`：`talk_runtime stop --apply --wait`，等待并报告结果。
`status.bat`：只读 `talk_runtime status` + `healthz`。

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

## 13. 分阶段实施建议

- **阶段 1（切片）**：路径/配置抽象 + 便携目录 + 首次启动脚本 + start/stop/status；先用系统 Python/现有 venv 验证同机拷贝。  
- **阶段 2（切片）**：embeddable Python + 依赖安装 + 构建脚本/zip + 安全检查。  
- **阶段 3（切片）**：干净机器/另一用户 E2E + 升级/迁移 + 文档/用户手册更新。  
每片仍按“目的/范围/不变项/验收”先确认；开发和独立复核按项目任务流程执行。

## 14. 待确认决策

1. **Python 运行时**：embeddable（推荐）还是随附 venv/要求系统 Python？
2. **Key 位置**：默认 `%LOCALAPPDATA%\TALK\keys`（推荐，安全）还是文件夹内 `data/keys`（完全自包含，需警告）？
3. **默认项目根**：`data/project`（推荐，代码/数据分离）还是 TALK 文件夹根（兼容当前）？
4. **默认鉴权**：只信任 loopback（推荐）还是默认 trusted private？
5. **端口冲突**：明确失败（推荐）还是自动换端口？
6. **分发内容**：是否包含 `docs/`（建议包含）与 `tests/`（建议不包含）？
7. **首版平台**：仅 Windows x64（建议）还是同时考虑 Linux？
