# TALK 本机统一启动

Windows 本机受管运行入口将 API、角色配置 worker 和已确认的角色宿主一起启动。角色原生进程继续按页面的“启动 / 关闭”请求执行；启动入口本身不会批量启动模型。直接运行 `uvicorn` 仍是单独的后端开发入口，不会启动这些本机组件。

## 启动与维护

在项目根目录运行；清单必须放在仓库外，包含命令和凭据文件路径，不能填入 Key 正文。

```powershell
# 默认只读预览
.\run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json
# 隐藏窗口、独立常驻；命令结束后继续持有原子进程句柄
.\run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json -Apply
# 查看真实入口、API PID、宿主状态和 worker 最近完成时间
.\run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json -Action status
# 正常重载 API，保留原角色宿主和原生进程
.\run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json -Action reload-api -Apply
# 普通关闭角色 → 等待原宿主释放归属 → drain 宿主 → 关闭 API
.\run.ps1 -Config D:\claude-test\TALK-private\talk-runtime.json -Action stop -Apply
```

也可设置 `TALK_RUNTIME_CONFIG` 指向该清单。需要在控制台观察时追加 `-Foreground`。此处是显式启动，不安装开机计划任务。宿主日志在私有 `state_dir/runtime`，不把凭据放入 argv。`runtime/launcher.lock` 为随进程退出释放的 OS 锁；健康文件只作诊断，不能当作进程所有权凭据。

## 清单约束

`schema=talk-runtime-config-1`、`version=1`。必填 `project_id`、`project_root`、`base_url`、`operator_key_file`、`key_root`、`state_dir`、`api_argv`，路径均为绝对路径，Key 根和 human 凭据文件须在项目外。当前 API 地址只支持 HTTP 回环 `127.0.0.1 / localhost`，本入口不配置远端控制或 TLS。

- `api_argv` 使用项目 Python 的 `-m scripts.talk_api`，必须包含独立参数 `{control_file}`；入口替换成此次 API 子进程专属的私有退出文件。不要填旧 PID 或 shell 命令字符串。
- `hosts` 每项为 `member_id / argv / health_file / drain_file`，沿用已经核验的精确成员配方、原生 HOME、模型及本人 Key。健康和 drain 路径必须位于 `state_dir` 内。同一成员不能重复配置。
- `provision_worker=true` 随入口启动请求配置 worker，但不替人类启用项目配置、创建请求或更换绑定。worker 单轮 HTTP 为5秒、总预算120秒；独立串行线程执行，不阻塞角色宿主轮询。`provision_cli_executable` 可选，仅为现有配置步骤的存在性检查。
- 可选 `workbuddy={executable, models_home, key_files}` 为已确认的 WorkBuddy 内置 CLI 工厂。名册中已绑定的 WorkBuddy 角色使用独立宿主/HOME；`key_files` 仅映射原成员凭据路径，新配置角色从 `key_root` 解析本人 Key，并先核身份。它不控制桌面窗口。

本机清单沿用此前已核验的 DSH、Codex、三个 Kimi 的窄宿主配方；这些本机辅助文件仍是部署依赖，不能删除 `.tmp/legacy-role-page-control` 后继续使用原清单。WorkBuddy 工厂可自动发现新绑定角色。其它运行器的新成员需先准备并核验该成员的宿主配方，不能把某一成员的静态配方用于所有身份。

## 退出与故障

API 重载不退出或重建角色宿主。配置请求会在正常轮询中处理，角色页面启停仍经过原来 human-only、就绪和所有权守卫。

受管队列前两次连续网络传输异常仅记录诊断并重试，第三次或非传输异常正常报错；真实90秒心跳失联仍显示待核实。受管消息接收启动时取最新游标，重连只补新消息，避免将历史私信当成新交办；普通SDK默认历史读取语义保持。这些措施不保证机器/原生进程永不故障，真实退出仍需核查并按守卫恢复。

入口只管理自己创建并持有的 `Popen`。发现外部宿主时只观察；发现旧 owner 时显示 `recovery_required`，不会按 PID 接管、自动解除归属或伪造就绪。宿主启动失败按2/4/8秒退避，三次后停止尝试；新的服务代际才重新开放。API 意外退出保留原宿主，等待显式 `reload-api`。

正常停止遇到占用任务、API 不可达或宿主未释放归属时，入口保持运行并报告 `stop_blocked`，不会丢弃句柄。不要直接删除 stop/drain 文件、强杀入口或重新启动第二个管理器来绕过；核实原进程后使用现有人工恢复计划/CAS 流程。Windows 已确认 `exited` 的进程可作为“已停止”证据，`unknown / present` 均拒绝恢复；仍需精确旧代际和本地复查。

## 名称与人工验收

角色列表、详情和搜索优先使用当前项目的创建/保存名称。原生 bridge 重注册全局名称不会覆盖项目名称。人类账号可点击角色标题旁的方框铅笔图标修改；1—64字符、重名提示、取消及刷新后保留均可验收。改名不改变成员 ID、模型、Key、绑定或历史任务。旧“WorkBuddy接入验证”与新建角色是两个身份，各自保留。

检查启动入口 `status`、页面角色状态、配置请求进度，随后可测试改名与逐角色启停。页面视觉和交互效果由用户人工验收；自动化 DOM/API/进程验证不等同于人工验收。
