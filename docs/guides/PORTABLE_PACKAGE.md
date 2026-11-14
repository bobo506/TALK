# TALK 便携版（免安装）

当前交付（2026-11-14 凌晨构建，750 复核 approved）：

- 预配置验收副本：`D:\TALK-portable`（端口 **8132**，config/data/keys 在文件夹内；用于早上验收，避免与生产 8000 冲突）。
- 干净分发 zip：`D:\TALK-portable-clean.zip`（21,755,007 bytes，1,440 files，SHA256 `F3E88C59…D26F`；首次启动生成自己的配置/Key）。
- 2026-11-14 09:40 修复：关窗 API 优雅关闭 5s 超时；全新 DB 自动登记 Codex/Kimi Code/DSH + 默认模型；桌面模式隐藏右上角“退出”。
- 2026-11-14 13:50 修复：全新 DB 自动登记本机“角色配置宿主”（`role_provision_host_config`，enabled=1）；等待中的 Kimi Code test 角色已完成配置（服务未自动启动，启动需原生登录）。
- 2026-11-14 14:20 修复：全新 runtime 配置自动补 `codex`/`kimi`/`dsh` 宿主配方；DSH test01 已成功启动为 running/ready。已有 config 只补缺失 key，不覆盖自定义。
- 2026-11-14 14:40 复核：codex 仅在 `which` 绝对路径时写入，未安装时省略，避免相对 fallback 让整份配置被拒；测试已覆盖。
- 2026-11-14 17:10 修复：native setup 分离 project_root（.talk pointer）与 data_root（TALK_HOME workspaces）；Codex test03 已完成设备授权并启动。
- 2026-11-14 20:20：DSH 宿主启动前自动生成 model patch，test01 任务已成功；启动器 Chrome→Edge→默认浏览器（含 macOS 路径检测）；授权 ready 后整块隐藏、验证码可复制、两段冗余文案删除。Chrome 真实桌面与 Mac 端到端仍需用户验证。
- 构建脚本 `_ssl` 在 pip 后立即导入会瞬时失败（进程退出后恢复），因此当前交付包由暂存 runtime 组装；750 已如实记录，后续可修复构建脚本的可复现性。

## 使用

1. 双击 `start-gui.bat`（或预配置副本的同一文件）。
2. 首次启动会初始化 `config/`、`data/`、默认项目和管理员；随后打开 **Edge 应用窗口**（无地址栏/标签页），默认 `trusted` loopback，无需登录。
3. 关闭窗口后等待几秒，启动器会停止本启动器拉起的 TALK 服务；可用 `status.bat` 查看、`stop.bat` 停止。
4. 正式分发 zip 首次运行默认端口 **8000**；若本机已有 TALK 占用 8000，需先停止它或使用预配置 8132 副本/修改配置。预配置副本的 8132 不与生产冲突。

## 目录与数据

- `runtime/python`：embeddable Python 3.12.1 + 依赖（无需目标机 Python）。
- `config/`：`config.toml`、`runtime.json`（首次生成）。
- `data/`：`talk.db`、`storage/`、`logs/`、`backups/`、`state/`、`workspaces/`、`project/`。
- `keys/`：仅预配置验收副本内置；干净 zip 首次运行默认把 Key 放到 `%LOCALAPPDATA%\TALK\keys`，可用 `TALK_KEYS_DIR` 覆盖。
- 删除文件夹即卸载（Key 目录可另行删除）；不写注册表、不装 Windows 服务。

## 构建

```powershell
.venv\Scripts\python.exe -B -X utf8 scripts\build_portable.py --out .tmp\portable-build --zip
```

- 需要 Python 3.12.1 与网络/pip 源；首次会下载 `python-3.12.1-embed-amd64.zip`，安装 `requirements.txt` 到包内。
- 已知问题：pip 后立即 `import _ssl` 可能瞬时 DLL 失败（本机实测 30 秒仍失败，构建进程退出后恢复）；必要时在构建后单独复验，或后续把验证放到独立进程/更长等待。构建失败时保留 staging 与日志，不产出来源不明的 zip。
- 构建脚本会扫描真实 Key/DB、开发绝对路径、排除项；`TALK/client` SDK 已包含。

## 当前限制

- 启动器使用 Edge `--app` 窗口（不是 pywebview 原生窗口）；页面内链接仍可导航。
- 关窗后无法取消关闭；忙任务/停止失败时服务可能残留，需 `stop.bat`/`status.bat`（不强制杀）。
- 未验证真实人工关窗（仅自动关窗钩子）、另一台干净 Windows、升级/迁移；这些是阶段 4 剩余项。
- 未安装包、无 Windows 服务、无托盘常驻。

## 早上验收

1. 打开 `D:\TALK-portable\MORNING-ACCEPTANCE.txt`。
2. 双击 `D:\TALK-portable\start-gui.bat`，确认 Edge 应用窗口打开、页面可用。
3. 关闭窗口，等待几秒；`http://127.0.0.1:8132/healthz` 应不可达，任务管理器无残留 msedge/启动器。
4. 如需要干净包：解压 `D:\TALK-portable-clean.zip` 到新目录，双击 `start-gui.bat`（端口 8000；先确认 8000 未被生产 TALK 占用）。
