# TALK 便携包使用与交接说明

> 适用版本：TALK 便携包（Windows x64）。本文覆盖“拿到包 → 启动 → 自动接入 → 创建角色 → 日常运维/排障”的完整流程。

## 1. 前置条件

- Windows 10/11 x64；
- 已安装 **Chrome 或 Edge**（桌面窗口启动器优先 Chrome 应用窗口，其次 Edge；都没有时回退系统默认浏览器）；
- 至少安装以下**运行器之一**（TALK 会自动检测并接入）：
  - Codex CLI（`codex --version` 可用，已登录）
  - KimiCode CLI（`kimi --version` 可用，已登录）
  - WorkBuddy 桌面端（默认安装路径存在）
  - DSH（`~/.dsh` 存在）
- 不需要安装 Python：包内自带 `runtime/python`。

## 2. 获取与解压

- 从 GitHub Releases 下载 `TALK-portable-<version>.zip`（当前版本：[v0.1.0](https://github.com/bobo506/TALK/releases/tag/v0.1.0)）；
- 解压到任意可写目录（建议非系统盘、路径不含中文空格也可，但避免 OneDrive 同步目录）；
- 解压后目录结构：

```text
TALK/
  server/ web/ scripts/ bridges/ cli/ ...   # 产品代码
  runtime/python/                            # 自带 Python 3.12
  config/                                    # 首次启动生成 config.toml / runtime.json
  data/                                      # 数据库、上传、日志、备份、状态、工作区、keys
  start-gui.bat  start.bat  stop.bat  status.bat
  README-PORTABLE.txt
```

## 3. 首次启动

1. 双击 `start-gui.bat`；
2. 首次运行会自动执行 `portable_bootstrap`：生成 `config/`、`data/`、默认项目、管理员 `human:operator` 与 **`data/keys/operator.key`**；
3. 浏览器窗口打开**加载页**，依次显示：
   - 启动服务 → 检测运行器 → 接入 MCP → 启动自动角色 → 检查更新/下载 → 就绪；
4. 检测到运行器时显示“本机已安装 X，可接入使用”，并**自动写入/跳过** MCP 配置（已有配置不重复写）；
5. 就绪后进入主页面。

> Key 默认在包内 `data/keys`。**整个文件夹被复制/转发时，Key 会一并被带走**；如需隔离，可设置环境变量 `TALK_KEYS_DIR` 指向包外目录。

## 4. 没有检测到运行器时

加载页/主页会显示琥珀色提示：

> 未检测到可用的运行器：服务已启动，但尚未接入 TALK，当前无法分配或接收任务。

安装 Codex / KimiCode / WorkBuddy / DSH 任意一类后，**重新启动 TALK** 即可自动接入；不需要手动改配置。

## 5. 创建执行角色

1. 打开“角色”页 → “创建角色”；
2. 选择运行器（Codex / KimiCode / WorkBuddy / DSH）→ 模型 → 思考强度；
3. 保存后角色出现在列表；按需点击“启动”，或勾选“随项目自动启动”；
4. 任务创建/转交时选择执行角色；终端发起身份（`codex-t` 等）不会出现在角色列表。

## 6. 日常使用

- **关闭窗口**：服务继续在后台运行（不会自动停止）；
- **退出服务**：页面右上角（"本机操作员"旁）“退出服务”，或运行 `stop.bat`；有任务在跑时会提示等待；
- **查看状态**：运行 `status.bat`；
- **重新打开**：再次运行 `start-gui.bat`（会接入已运行的服务）。

## 7. 数据、备份与迁移

所有运行数据都在 `data/`：

| 路径 | 内容 |
|---|---|
| `data/talk.db` | 数据库（任务、消息、角色、成员） |
| `data/storage/` | 上传文件 |
| `data/logs/` | 日志 |
| `data/backups/` | 数据库备份 |
| `data/state/` | 角色宿主/运行时状态 |
| `data/workspaces/` | 工作区角色数据 |
| `data/project/` | 默认项目根 |
| `data/keys/` | **TALK Key（含 operator.key）** |

备份：关闭 TALK 后整体复制 `data/` 即可；迁移：复制整个 `TALK/` 目录（含 `data/`）。

## 8. 升级

1. 关闭 TALK（`stop.bat`）；
2. 备份 `data/`；
3. 用新包替换**代码与 `runtime/`**，保留 `config/` 与 `data/`；
4. 重新 `start-gui.bat`。

## 9. 故障排查

| 现象 | 处理 |
|---|---|
| 端口被占用 | 关闭其他占用 8000 的程序，或改 `config/config.toml` 的 `server.port` |
| 加载页“启动阶段报错” | 查看 `logs/launcher/` 下的日志；确认 `data/` 可写 |
| 运行器不被识别 | 确认对应 CLI/程序可用且已登录；Codex 可运行 `python -m scripts.codex_role_host --check-version` 查看版本与能力 |
| 任务无法执行 | 角色页确认角色为 running；查看该角色日志与 `logs/` |
| MCP 工具不可见 | 确认运行器已重启；配置位置：Codex `~/.codex/config.toml`、Kimi `<项目>/.kimi-code/mcp.json`、WorkBuddy `~/.workbuddy/mcp.json`、DSH `~/.dsh/profiles/desktop/cordis.patch.yml` |

## 10. 卸载

关闭 TALK 后删除整个 `TALK/` 文件夹即可（`data/keys` 在包内，会一并删除）。如曾用 `TALK_KEYS_DIR` 指向包外，另行清理该目录。
