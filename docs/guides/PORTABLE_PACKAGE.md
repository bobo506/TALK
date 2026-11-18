# TALK 便携版（免安装）

当前发布：`v0.1.0` → <https://github.com/bobo506/TALK/releases/tag/v0.1.0>

| 项 | 值 |
|---|---|
| 资产 | `TALK-portable-0.1.0.zip` |
| 大小 / 文件数 | 19,621,560 B / 1254 |
| sha256 | `9ec85731106aa2815f237d7be756ad908fab21c7748682e105e173ffd9221bb7` |
| 平台 | Windows x64（自带 Python 3.12.1，无需目标机 Python） |
| 历史 | 各次打包与冒烟记录见[开发历史](../PROGRESS_HISTORY.md) |

## 使用

1. 解压到任意可写目录（建议非系统盘，避免 OneDrive 同步目录），得到 `TALK/` 文件夹；
2. 双击 `start-gui.bat`；
3. 首次启动自动生成：
   - `config/`：`config.toml`、`runtime.json`
   - `data/`：`talk.db`、`storage/`、`logs/`、`backups/`、`state/`、`workspaces/`、`project/`
   - `data/keys/operator.key`、默认项目、管理员 `human:operator`
4. 随后打开应用窗口：优先 **Chrome** 应用窗口，其次 **Edge**，都没有时回退系统默认浏览器；默认 `trusted` + `loopback`，本机免登录；
5. **关闭窗口不停服务**。停止方式：页面右上角「退出服务」（有任务时提示等待），或 `stop.bat`；`status.bat` 查看状态。

## 目录与数据

- `runtime/python`：embeddable Python 3.12.1 + `requirements.txt` 依赖；
- `config/`：`config.toml`、`runtime.json`；
- `data/`：`talk.db`、`storage/`、`logs/`、`backups/`、`state/`、`workspaces/`、`project/`；
- `data/keys/`：管理员与角色 Key（默认在包内；`TALK_KEYS_DIR` 可指向包外）；
- 不写注册表、不装 Windows 服务；删除文件夹即卸载（Key 目录可另行删除）。

## 备份与换机

- 备份：复制整个 `data/`（`talk.db` 数据、`keys/` 凭据、`storage/` 上传文件）；
- 换机：新机器解压同版本包 → `stop.bat` 停止 → 用旧 `data/` 覆盖新包 `data/` → 启动；
- 只备份聊天记录：`data/talk.db` 单独足够（不含 Key 与上传文件）。

## 端口与局域网

- 默认端口 `8000`，仅监听 `127.0.0.1`；
- 开放给家里其它设备：改 `config/config.toml` 的 `host = "0.0.0.0"`、`public_url = "http://<本机IP>:8000"`、`trusted_networks = ["loopback", "private"]`，然后 `stop.bat` → `start-gui.bat`；
- 不改 `trusted_networks` 时，其它设备需携带管理员 Key 访问。

## 构建

```powershell
.venv\Scripts\python.exe -B -X utf8 scripts\build_portable.py --out <输出目录> --zip
```

- 需要 Python 3.12.1 与网络/pip 源；首次会下载 `python-3.12.1-embed-amd64.zip` 并把 `requirements.txt` 装进包内；
- 构建脚本会扫描数据库文件、真实密钥样式与允许目录外的开发绝对路径，命中即拒绝出包；
- `docs/` 不在打包白名单内（内部开发文档含主机名/内网 IP/本机路径），包内只保留 `README-PORTABLE.txt`；
- 已知问题：pip 安装后立即 `import _ssl` 可能瞬时失败，构建脚本自带重试（`_ssl import attempt n/10`）。

## 当前限制

- 仅 Windows x64；未验证另一台干净 Windows 的首次启动，以及旧版本升级/迁移；
- macOS 仅做路径检测，未端到端验证；
- 启动器使用浏览器应用窗口（不是 pywebview 原生窗口），页面内链接仍可导航；回退默认浏览器时关窗不会停服务，需 `stop.bat`；
- 忙任务或停止失败时服务可能残留，用 `status.bat` 查看、`stop.bat` 重试（不强制杀进程）。
