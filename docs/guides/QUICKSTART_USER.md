# TALK 家庭用户快速开始

这份文档给第一次接触 TALK 的家庭用户。目标只有一个：解压便携包、双击启动，在窗口里看到可用界面。

> 不需要安装 Python，也不需要 Docker：整个 TALK 就在一个文件夹里，删掉文件夹就算卸载。
> 想在服务器或用 Docker 跑（偏技术），见文末「附：用 Docker 运行」。

## 1. 先准备三样东西

- 一台 Windows 10/11 x64 电脑
- Chrome 或 Edge 浏览器（启动器优先用 Chrome 应用窗口，其次 Edge，都没有时用系统默认浏览器）
- TALK 便携包：到 [Releases](https://github.com/bobo506/TALK/releases/tag/v0.1.0) 下载 `TALK-portable-0.1.0.zip`

## 2. 解压

解压到任意可写目录（建议非系统盘，避免 OneDrive 同步目录）。打开后应能看到：

```text
TALK/
  start-gui.bat  stop.bat  status.bat
  server/  web/  scripts/  runtime/  README-PORTABLE.txt
```

## 3. 第一次启动

1. 双击 `start-gui.bat`；
2. 首次启动会自动生成：
   - `config/`：`config.toml`、`runtime.json`
   - `data/`：`talk.db`、`storage/`、`logs/`、`backups/`、`state/`、`workspaces/`、`project/`
   - `data/keys/operator.key`：本机管理员 Key
   - 一个默认项目和管理员账号 `human:operator`
3. 随后自动打开应用窗口（无地址栏、无标签页）；本机访问默认免登录；
4. **关闭窗口不会停止服务**。要停止，点页面右上角「退出服务」，或运行 `stop.bat`。

## 4. 本机管理员 Key

- 位置：包内 `data/keys/operator.key`
- 备份、换机、用命令行或 SDK 调用时需要它
- 想让它不跟着文件夹被复制：启动前设置环境变量 `TALK_KEYS_DIR` 指向包外目录

## 5. 让家里的其它设备访问

默认只监听本机 `127.0.0.1:8000`，别的设备访问不到。要开放：

1. 用记事本打开 `<包>/config/config.toml`，把这一段改成：

```toml
[server]
host = "0.0.0.0"
port = 8000
public_url = "http://<本机局域网IP>:8000"
auth_mode = "trusted"
trusted_networks = ["loopback", "private"]
```

2. 找本机局域网 IP：Windows 在 `cmd` 里执行 `ipconfig`，看 `IPv4 地址` 那一行；macOS 用 `ipconfig getifaddr en0`；
3. 先 `stop.bat`，再双击 `start-gui.bat`；
4. 其它设备浏览器打开 `http://<本机局域网IP>:8000`。

如果不想把 `private` 加进 `trusted_networks`，其它设备访问时需要带管理员 Key（见第 4 节）。

## 6. 停止与查看状态

- 页面右上角「退出服务」：有任务在跑会提示等待；没有任务时停止整机（服务、角色进程、浏览器托盘）；
- `stop.bat`：同样的停止效果；
- `status.bat`：查看服务与角色状态。

## 7. 备份与换机

- 备份：复制整个 `data/` 目录即可
  - `data/talk.db`：聊天记录、任务、角色绑定
  - `data/keys/`：凭据（含 `operator.key`）
  - `data/storage/`：上传的文件
- 换机：新机器解压同版本便携包 → 先 `stop.bat` 停止 → 用旧 `data/` 覆盖新包的 `data/` → 启动
- 只想要聊天记录：单独备份 `data/talk.db` 也够用（不含 Key 与上传文件）

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| 双击没反应、窗口没出来 | 看 `logs/launcher/` 与 `data/logs/` 下的日志；被杀软拦截时先放行 |
| 8000 端口被占用 | 先 `status.bat` 确认，再停掉占用程序，或改 `config/config.toml` 的 `port` |
| 关了窗口服务还在跑 | 设计如此；用页面「退出服务」或 `stop.bat` |
| 想换端口 | 改 `config/config.toml` 的 `port`，同时把 `public_url` 改成一致 |
| 提示"未检测到可用的运行器" | 安装 Codex / KimiCode / DSH / WorkBuddy 任一后重启 TALK |

## 9. 接下来可以做什么

- 在页面里创建角色：选运行器 → 选模型 → 保存，再按需启动或勾选"随项目自动启动"；
- 创建任务并指定执行角色，在任务 Hall 里看对话与交付；
- 更完整的说明见[便携版说明](PORTABLE_PACKAGE.md)、[便携包交接](PORTABLE_HANDOVER.md)、[用户手册](USER_MANUAL.md)；
- Agent 开发者入口见[Agent 快速开始](QUICKSTART_AGENT.md)。

## 附：用 Docker 运行（可选，偏技术）

仓库里仍保留 `Dockerfile` 与 `docker-compose.yml`，适合在服务器或开发机上跑：

```bash
docker compose up -d
```

然后打开 <http://127.0.0.1:8000>。

注意这条路用的是**仓库根目录的 `config.toml`** 与仓库内数据，和便携包的 `config/`、`data/`、`data/keys` 布局不同，两套不要混用同一份数据。

排查顺序：

1. `docker --version` 能输出版本；
2. Docker Desktop（或 dockerd）在运行；
3. 在项目根目录（能看到 `docker-compose.yml`）执行；
4. `docker compose ps` 中 `talk` 为 running；
5. 8000 被占用时：Windows `netstat -ano | findstr :8000`，macOS/Linux `lsof -i :8000`；
6. 容器日志：`docker compose logs talk`。
