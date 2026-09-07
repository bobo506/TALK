# 普通终端接入 TALK 任务工具（TH-7a）

这个入口供支持本地 stdio MCP 的终端使用。终端中的主 Agent 可以发现项目角色、委派任务、查询进度、处理澄清和收取成果。目标角色仍由已有 bridge 执行任务。

## 启动前准备

- TALK 服务已经启动；目标项目已注册，角色已同步。
- 使用现有 TALK 成员的 API Key，可向项目管理者获取已分配账号的密钥；此入口不会注册账号或生成新密钥。
- Python 3.11+，已安装仓库的 `requirements.txt`。
- 仅检查连接、角色与历史任务时不需要启动其它 bridge；创建任务后，目标角色的 bridge 在线才会实际执行。

## 先检查连接

在终端或 MCP 客户端中设置 `TALK_API_KEY` 环境变量。密钥只从环境变量读取，不写入项目配置，也没有命令行 `--key` 参数。

以下使用 PowerShell，示例路径应替换为实际 TALK 仓库和参与协作的项目路径：

```powershell
& 'C:/talk/.venv/Scripts/python.exe' -X utf8 'C:/talk/bridges/talk_terminal_mcp.py' --project-root 'D:/my-project' --check
```

`--project-root` 读取该目录下已有的 `.talk/project.yaml`。如果项目还没有本地配置，可以显式指定服务与已注册项目：

```powershell
& 'C:/talk/.venv/Scripts/python.exe' -X utf8 'C:/talk/bridges/talk_terminal_mcp.py' --server 'http://127.0.0.1:8000' --project 'prj_example' --check
```

成功时输出一行 JSON，包含 `ok=true`、当前身份、项目和角色可用状态。`offline` 表示角色当前没有在线实例；检查通过不代表角色已经能执行任务。项目没有配置角色时，`agents` 返回空列表。

检查只读取身份、项目角色和成员，不创建任务或发送消息。失败时退出码为 `1`，错误写入 stderr；常见原因包括未设置密钥、密钥无效（401）、项目不存在（404）或服务不可达。

## 配置 MCP 客户端

将下面的值填入客户端的本地 stdio MCP 配置。使用绝对路径后，客户端从其它目录启动也能运行：

| 字段 | 值示例 |
|---|---|
| command | `C:/talk/.venv/Scripts/python.exe` |
| args | `["-X", "utf8", "C:/talk/bridges/talk_terminal_mcp.py", "--project-root", "D:/my-project"]` |
| env | `TALK_API_KEY`：现有成员密钥 |

正常 MCP 配置不要加 `--check`，因为检查模式会输出报告并退出。正常模式会等待 stdin 请求，stdout 只用于 MCP JSON-RPC；手动启动后没有欢迎文字属于正常现象。

支持的配置优先级：

1. `--server` / `--project` 显式参数。
2. `TALK_BASE_URL` / `TALK_PROJECT_ID` 环境变量。
3. `--project-root` 的 `.talk/project.yaml` 中的 `talk_server` / `project_id`；未传目录时尝试当前工作目录。
4. 服务地址默认 `http://127.0.0.1:8000`；项目必须提供，缺失时拒绝启动。

显式给出的项目目录必须存在有效 `.talk/project.yaml`，错误时不会悄悄换成其它项目。排查项目不符时先核对 `--check` 输出与环境变量。工具参数中显式传入的 `project_id` 仍遵守原有覆盖规则；默认项目不是权限隔离边界，权限由服务端校验。

身份由 API Key 对应的服务端成员决定；独立入口忽略继承的 `TALK_MEMBER_ID`。它不需要 `TALK_GROUP_ID` 或 `TALK_DEFERRED_FILE`。

## 首轮验收

1. 用 `--check` 确认身份和默认项目正确。
2. 在 MCP 客户端中检查能看到八个工具：`talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result`。
3. 调用 `talk_list_agents` 确认目标角色；经用户授权后委派一个范围明确的任务。
4. 目标 bridge 在线时执行任务；终端通过查询或有界等待读取进展，需要补充信息时在同一任务中回复并提交澄清答复。
5. 任务进入 `submitted` 后先检查成果，再调用 `talk_collect_result`；预期变为 `completed`，并可在现有任务页面看到结果。

## 当前范围与验证

- 这是 TH-7 的第一片接入包装，没有修改任务协议、页面、数据库或 bridge 的执行方式。
- 新入口只暴露八个任务工具；旧 `talk_send` 依赖 bridge 在当前轮结束后处理延迟记录，因此普通终端不展示也不接受它。原 `talk_send_mcp.py` bridge 入口继续保留原有九工具行为。
- 没有自动安装到任何桌面客户端、编辑用户级 MCP 配置、启动角色服务或开放远程 MCP 服务；具体客户端安装与真实模型验收属于下一片。
- 自动化已在隔离服务和数据库中验证：中文与空格目录启动、配置优先级、只读检查、错误诊断、stdio 工具目录、委派→提交→查询→收取。执行方通过测试 API 模拟，没有调用真实模型或修改现有验收数据。

回归命令（TALK 仓库根目录）：

```powershell
python -X utf8 -m unittest tests.test_talk_terminal_mcp tests.test_talk_task_tools -q
```
