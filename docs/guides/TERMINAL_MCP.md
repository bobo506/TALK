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

## Kimi Code 独立会话入口（L1-1 准备）

上面是通用说明；本节是官方 Kimi Code CLI 的独立主控入口准备。**它只做到“配置可用 + 工具可发现”，真实模型主控闭环尚未运行**，三层结论见本节末尾。

### 本机已核对事实（2026-09-15 只读检查）

| 项 | 结果 | 依据 |
|---|---|---|
| CLI 路径 | `C:\Users\Administrator\.kimi-code\bin\kimi.exe` | 文件系统只读检查；它是单文件 Node 运行时（内部名 `node`，文件版本 24.15.0 是内置 Node 版本，不是 CLI 版本） |
| CLI 版本 | 已安装 `0.38.0`；更新通道最新 `0.43.0` | CLI 自身更新日志 `~/.kimi-code/updates/rollout.log` 的 `current` / `latest` 字段 |
| 用户级配置 | `~/.kimi-code/config.toml` 仅有 `providers` / `models` / `thinking` / `services` 段 | 只读解析段名，未输出任何值 |
| 用户级 MCP | **不存在** `~/.kimi-code/mcp.json` | 目录枚举；新增工作区级配置不会覆盖已有用户级 MCP 配置 |
| 工作区可信 | `D:\claude-test\TALK` 已登记为可信目录 | `~/.kimi-code/workspace-trust/wd_talk_59d2e3395d35` |
| 会话隔离 | Kimi 会话按工作区分目录保存 | `~/.kimi-code/sessions/wd_talk_59d2e3395d35/...` |
| 本片未测 | `kimi --version`、`kimi doctor`、`/mcp` 均未执行 | 当前沙箱拒绝启动工作区外程序（`Access is denied`）且无审批通道；这是环境限制，不是 Kimi 或 TALK 的产品失败 |

官方一手文档（2026-09-15 抓取；已安装 CLI 为 `0.38.0`，与文档不保证逐条对应）：

- MCP 配置：<https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html> —— `mcp.json` 分用户级 `~/.kimi-code/mcp.json`（`$KIMI_CODE_HOME/mcp.json`）与工作区级 `<工作目录>/.kimi-code/mcp.json` 两级，同名条目工作区级覆盖用户级；stdio 条目支持 `command` / `args` / `env` / `cwd` / `enabled` / `startupTimeoutMs` / `toolTimeoutMs` / `enabledTools` / `disabledTools`；**会话进行中修改 `mcp.json` 不会注册进已打开的会话**，只对新会话生效；MCP 工具名为 `mcp__<server>__<tool>`。
- 命令参考：<https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command.html> —— 主命令参数为 `-p` / `--session` / `--continue` / `--model` / `--agent` / `--agent-file` / `--skills-dir` / `--add-dir` 等，**没有** `--mcp-config` 这类“按会话指定 MCP 文件”的参数，所以本项目的“按会话加载”只能靠工作区级 `.kimi-code/mcp.json`（且只影响新会话）。
- Agents：<https://www.kimi.com/code/docs/en/kimi-code-cli/customization/agents.html> —— agent 文件的 `tools` 白名单同时决定“模型可见工具”和“执行前复核”，MCP 工具按 `mcp__<server>__*` 匹配。

### 入口组成（本片新增，未改任务协议）

| 文件 | 作用 |
|---|---|
| `deploy/kimi-code/mcp.talk.template.json` | 无密钥配置模板；占位符必须用下面的命令替换，模板本身不会被 CLI 读取 |
| `scripts/kimi_talk_precheck.py` | `config` 生成/写入配置；`check` 用真实身份做只读连接检查；`probe` 按配置真实拉起 stdio MCP 并核对工具目录 |
| `scripts/kimi_talk_mcp_launch.py` | Kimi 侧 `command` 指向的无密钥启动器：先取 `TALK_API_KEY`（环境变量优先，其次仓库外密钥文件），再交给既有终端入口 |
| `bridges/talk_terminal_mcp.py` | 既有普通终端入口，本片未修改；工具集与只读边界仍由它决定 |

### 三步接入

```powershell
# 1) 在仓库外准备本人密钥（不回显、不写进仓库；-Encoding ascii 避免写入 BOM）
$k = Read-Host '粘贴 agent:kimi 的 TALK API Key'
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.talk" | Out-Null
Set-Content -Path "$env:USERPROFILE\.talk\agent-kimi.key" -Value $k -NoNewline -Encoding ascii
Remove-Variable k

# 2) 生成配置（默认只打印；确认后再写入工作区）
python scripts/kimi_talk_precheck.py config
python scripts/kimi_talk_precheck.py config --write D:/claude-test/TALK --allow-git-workspace

# 3) 预检：真实身份（只读）与工具目录
python scripts/kimi_talk_precheck.py check --project-root D:/claude-test/TALK --expect-member agent:kimi --expect-project prj_e8fe7066bbec
python scripts/kimi_talk_precheck.py probe --config D:/claude-test/TALK/.kimi-code/mcp.json
```

- 密钥只从环境变量或那个仓库外文件读取；`mcp.json` 里只有真实绝对路径与该文件位置，**没有任何密钥正文**。密钥文件若落在仓库内，启动器会直接拒绝并提示改到仓库外。
- 密钥文件只应包含一行可打印 ASCII：写入了 BOM（PowerShell 5.1 的 `-Encoding utf8` 会写）会被容忍并剥掉，但混入空格、换行以外的多余内容会被明确拒绝，避免真正调用时只得到难懂的编码错误。
- `check` 会用 `GET /api/members/me` 核对“凭证对应的成员与项目”；身份不是 `--expect-member`（默认 `agent:kimi`）时判失败，避免拿 `human:bobo` 等他人凭证冒充本人身份通过。
- `probe` 只发 `initialize` + `tools/list`，用占位密钥、不访问服务端，因此输出里 `identity_verified=false`；它证明的是“配置可解析、进程可启动、工具目录正确”。
- 写入 `D:/claude-test/TALK/.kimi-code/mcp.json` 会让**该工作区的新 Kimi 会话**多出这九个工具；是否提交到 Git 由操作者决定（本片未改 `.gitignore`），用完可删除该文件即回到原状。

### 与 bridge worker 的分离

- bridge 的任务会话由 `bridges/kimi_bridge.py` 用 `--agent-file` 启动，生成的 agent 文件只列 `Read / Grep / Glob / Bash`（`tools` 档加 `Edit / Write`）且 `subagents: []`；按官方 agents 文档的 `tools` 白名单语义，`mcp__talk__*` 不在其中，因此 bridge worker 不会拿到主控工具。
- 普通终端入口（本节入口）与 bridge worker 是两套独立启动：前者由工作区级 `mcp.json` 拉起一个只含 TALK 任务工具的 stdio 进程，后者由 bridge 拉起并隐藏主控工具。`probe` 的输出可用于核对独立入口的工具目录，不代表 bridge worker 的可见工具。

### 三层结论（必须分开表述）

1. **配置可用**：本片已验证——生成/写入的配置是合法 JSON、只含真实绝对路径，按其中 `command`/`args`/`cwd` 能真实拉起 stdio MCP 并返回 `serverInfo`。
2. **连接预检**：依赖**本人 `agent:kimi` 凭证**。本片执行环境没有该凭证（`check` 返回中文失败原因），因此真实项目/身份核对在本片是**阻塞项**，需由凭证持有人按上面第 1、3 步执行。
3. **真实模型主控闭环**：**未运行**。本片不派发嵌套任务、不启动额外模型 Agent、不做等待实验；闭环属于下一片。

### 下一片：Kimi 真实主控闭环的有限任务包（本片未执行）

- **工作区/会话**：在 `D:\claude-test\TALK` 新开独立 Kimi 会话，不复用 bridge worker 会话，也不复用本次准备片所用的会话。
- **身份**：`agent:kimi`（`decision_tier=execution`，见 `AGENTS.md`）；按明确项目与任务授权，不因模型名称升权，不改 `groups.yaml` 角色等级、不新建管理员。
- **有限协调授权**：由项目管理者显式授予本次“主控协调”职责；子任务须遵守服务端 parent / epoch / 预算门禁；单次独立顶层测试需明确业务授权，不能只因 API 允许创建就视为获得授权。本次 #67 经 Codex 明确授权为唯一顶层 general，不增加子任务预算。
- **1 个无破坏性委派**：委派 `agent:deepseek` 完成一个只读、范围明确、可回滚的切片（顶层任务、省略 `task_kind` 即 `general`），正文写清范围、验收标准和交付包路径。
- **不同角色复核**：由与被委派者不同的身份（`agent:codex` 或人工）独立复核实际代码/交付，不只采信执行者结论。
- **原会话读取与汇总**：回到发起会话，`talk_wait_tasks` 等状态 → `talk_get_delivery` 读取完整交付摘要（按 `read_more` 分页补读）→ `talk_collect_result` 收取 → 在会话内给出汇总。
- **成功证据**：工具调用记录、真实任务号、交付摘要中的 `delivery_conclusion` 与验证证据、`collect` 后 `workflow_status=completed`；同时确认未串项目、未自派递归、未重复主控、未越权新增预算。
- **失败清理**：未领取任务用 `talk_cancel_task` 取消；已运行任务由原请求者或人工走既有 `cancel-tree`；不删除历史任务与服务数据；Kimi 会话记录删除或保留由操作者决定。

## 首轮验收

1. 用 `--check` 确认身份和默认项目正确。
2. 在 MCP 客户端中检查能看到九个工具：`talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result`、`talk_get_delivery`。
3. 调用 `talk_list_agents` 确认目标角色并读取顶层 `development_requirements` 最新项目要求；经用户授权后委派一个范围明确的任务。REQ-1新实现会在 `talk_delegate_task` 创建任务时将非空要求追加到正文作为快照，旧任务不会随项目要求变化。
4. 目标 bridge 在线时执行任务；终端通过查询或有界等待读取进展，需要补充信息时在同一任务中回复并提交澄清答复。
5. 任务进入 `submitted` 后先检查成果，再调用 `talk_collect_result`；预期变为 `completed`，并可在现有任务页面看到结果。

## 当前范围与验证

- 这是 TH-7 的第一片接入包装，没有修改任务协议、页面、数据库或 bridge 的执行方式。
- 入口暴露九个工具：八个 Task Hall 工具加只读交付摘要 `talk_get_delivery`（完整结果按 `result_message_id` 分页补读）；旧 `talk_send` 依赖 bridge 在当前轮结束后处理延迟记录，因此普通终端不展示也不接受它。原 `talk_send_mcp.py` bridge 入口继续保留原有九工具行为。
- 没有自动安装到任何桌面客户端、编辑用户级 MCP 配置、启动角色服务或开放远程 MCP 服务；具体客户端安装与真实模型验收属于下一片。
- L1-1 只新增 Kimi 独立会话的模板、生成/预检脚本与启动器，并核对既有入口的工具目录；没有修改 `bridges/` 下任何工具合同，没有激活任何工作区级 `mcp.json`（避免影响现有与新开的 bridge 会话）。
- 自动化已在隔离服务和数据库中验证：中文与空格目录启动、配置优先级、只读检查、错误诊断、stdio 工具目录、委派→提交→查询→收取。执行方通过测试 API 模拟，没有调用真实模型或修改现有验收数据。
- Kimi 相关新增验证在隔离环境完成：配置生成/写盘边界、密钥来源与仓库外约束、身份不符拒绝、按生成的配置真实拉起 stdio MCP 得到九个工具。受限沙箱禁止匿名管道时，stdio 探针退化为文件型通道并在 stderr 留下 `STDIO_FALLBACK_FILE_STDIO` 标记。

回归命令（TALK 仓库根目录）：

```powershell
python -X utf8 -m unittest tests.test_kimi_talk_entry tests.test_dsh_talk_entry tests.test_talk_terminal_mcp tests.test_talk_task_tools -q
```


### 2026-09-15 独立复核补充（#63）

- 上文“本片未测”描述 #62 开发环境的限制。#63 已实测 Kimi CLI `0.38.0 --version/--help`，并以真实匿名管道发现九个工具；本人 `agent:kimi` 环境变量凭证对项目 `prj_e8fe7066bbec` 的只读身份检查通过。没有把占位凭证的工具探针当作身份验证。
- 运行 `check` 时显式指定 `--expect-project`，才能与独立给定的期望项目比较；省略时使用配置解析的项目，不能额外证明选择的是操作者期望项目。
- 激活前应明确本机 `.kimi-code/` 配置的 Git 忽略策略，当前不自动添加忽略项或激活配置。外部本人密钥文件实测、真实会话加载配置、模型委派与收取闭环仍未完成。


### 2026-09-15 Kimi 0.38.0 真实闭环实测（#64–#69）

- **信任是加载前提**：该版本仅在可信工作区加载项目级MCP配置。未受信的 headless `-p` 会话会跳过配置；配置生成/stdio探针通过不代表原生会话已加载。用户应在指定目录的Kimi信任提示中确认；`/mcp` 可用于无模型状态自检（本次未实测TUI路径，实际通过模型工具清单及调用确认加载）。不要为了诊断而信任更大目录或覆盖用户级配置。
- 本次用户授权信任 `D:/claude-test/TALK/.tmp/l1-kimi-live/session-workspace`，该目录仅保存无密钥MCP配置，启动器绑定实际TALK项目根。仓库根 `.kimi-code/mcp.json` 已撤回；信任与隔离配置保留，未推广到所有工作区。API Key从本人runner环境继承，不落盘。
- 用 `--agent-file` 新开会话，白名单仅 Read/Grep/Glob 与9个TALK工具，禁用子代理。实际 `wire.jsonl` 工具集为12个；不能只靠prompt禁止派生。首次启动和恢复以 `subprocess` 列表argv传参，避免PowerShell原生命令引号截断。
- 同会话续接使用本机help支持的 `kimi --output-format stream-json -S <session_id> -p <提示正文>`，cwd保持一致；不要同时传 `--agent-file`。本次实测 profile 白名单在恢复后保持不变，仍需每次核对，不保证其它版本/会话相同。
- 真实链路：Kimi创建#67→DeepSeek交付→Codex独立检查→原session读取消息2542并收取。当前主控直接读该Hall会403，必须由原请求者合法转交成果，不能读取数据库或借用其它身份绕过。成果有JSON围栏导致summary为unknown时，按稳定结果引用读取detail并校验原文；不能仅凭runner成功验收。
- #67收取返回completed，时间为2026-09-15T14:12:22.756535Z。此结论覆盖单项目、单次显式授权委派、人工独立验收/唤回；不是连续无人值守、多工作区、DSH/WorkBuddy或页面进程管理验收。此前“未运行”小节保留为准备阶段记录，以本次补充为最新状态。


## DeepSeek Harness（DSH）独立会话入口（L1-2；#70 开发、#71 复核、#72 返工）

DSH 是 `@deepseek-ai/dsh` 承载的独立会话入口，与上面“普通终端”和“Kimi Code”两节是并列关系。**本节只做到“配置可生成 + 组合树可核对 + 工具可发现”，真实模型主控闭环仍未运行**（三层结论见 Kimi 一节同一写法）。

### 入口组成（新增文件，未改任务协议）

| 文件 | 作用 |
|---|---|
| `deploy/dsh/talk-mcp.patch.template.yml` | 无密钥 `--patch` 覆盖层模板；占位符必须由生成命令替换，模板本身不能被 DSH 直接读取 |
| `scripts/dsh_talk_precheck.py` | `config` 渲染/写盘覆盖层；`dump` 让 DSH 组合覆盖层并导出配置树；`probe` 按覆盖层拉起 stdio MCP 核对工具目录；`check` 做只读身份与项目核对 |
| `scripts/dsh_talk_mcp_launch.py` | DSH 侧 `command` 指向的无密钥启动器：先在自身进程内解析密钥（环境变量优先，其次仓库外密钥文件），再交给既有终端入口 |
| `bridges/talk_terminal_mcp.py` | 既有普通终端入口，未修改；工具集与只读边界仍由它决定 |

覆盖层同时做两件事：注册 `mcp-talk`（九个 TALK 工具）与收窄原生工具（13 条 `disabled` 行 + `read-only` 沙箱 + `approval: never`）。这些是**组合层事实**，不是提示词约定。

### 生成与预检步骤

```powershell
# 1) 在仓库外准备本人密钥（启动器默认读 ~/.talk/agent-deepseek.key；不回显、不写进仓库）
# 2) 生成覆盖层：默认只打印；--write 默认拒绝写进仓库与已存在文件
python scripts/dsh_talk_precheck.py config
python scripts/dsh_talk_precheck.py config --write "<隔离目录>/talk-mcp.patch.yml"     # 仓库外
python scripts/dsh_talk_precheck.py config --write ".tmp/<切片>/talk-mcp.patch.yml" --allow-in-repo

# 3) 零模型预检：组合树 / 工具目录 / 只读身份
python scripts/dsh_talk_precheck.py dump --patch "<覆盖层>" --dsh-home "<隔离 DSH_HOME>" --out "<dump 输出路径>"
python scripts/dsh_talk_precheck.py probe --patch "<覆盖层>"
python scripts/dsh_talk_precheck.py check --server http://127.0.0.1:8000 --project prj_e8fe7066bbec `
    --expect-member agent:deepseek --expect-project prj_e8fe7066bbec
```

边界：

- `dump`/`probe`/`check` 的路径参数一律按**调用者当前目录**解析成绝对路径后再传下游。`dump` 的子进程 cwd 固定为 `dsh_home.parent`，而 DSH 会把 `--patch` 原样拼在自己的 cwd 上，所以相对 `--patch` 必须由脚本先解析；否则 DSH 会去 `<dsh_home.parent>/<相对路径>` 找覆盖层并报 `failed to read overlay`（#71 定位、#72 修复并补回归）。
- `dump` 在覆盖层不存在、子进程无法启动或超时时，输出中文短错误并返回 1，不再抛 traceback；`--out` 的父目录会自动创建。
- `probe` 只用占位密钥、只发 `initialize` + `tools/list`，不访问服务端：`tools_match=true` 只证明“配置可解析、进程可启动、工具目录正确”，不代表身份核对或真实主控通过。
- `check` 需要**本人 `agent:deepseek` 凭证**；显式给出 `--expect-project` 时按它核对，避免只比较“实际请求的项目”。

### 已核对事实与对 #70 诊断偏差的纠正（#71 复核、#72 返工）

- 版本与环境：本机 DSH `0.1.5-rc.1`。修复后按**相对** `--patch`（含中文与空格目录）运行 `dump` 退出码 0，组合树含 `mcp-talk` 行、`read-only` 与 13 条 `disabled` 行；同一命令在修复前返回 1，stderr 显示被拼成 `<dsh_home.parent>/<相对路径>` 的 ENOENT。
- 凭证传递（纠正 #70）：**只在启动环境注入 `TALK_API_KEY` 不足以通过 `dsh-mcp-client` 的基座过滤**——DSH 子进程 seam 按 `/KEY|PASSWORD|SECRET|TOKEN/i` 与 `DSH_*` 清洗父环境，`mcp-client` 又以清洗结果为基座。可行做法只有：覆盖层 `config.env` 给出**求值为 string** 的值，或让启动器在自身进程内读**仓库外密钥文件**；后者的真实可读性尚未经真实被测会话验证。
- 会话恢复（纠正 #70）：`headless` **没有** resume；`dsh-agent-loop` 的声明式 `resumeSessionId` 只在启动时恢复“配置 agent”，而 `headless run()` 不使用配置 agent、自造新会话，因此 patch 无法让新会话变成旧会话。`dsh-sdk-jsonrpc-server` 无持久会话恢复（只有 `initialize/session/prompt/shutdown`）；原生续接能力在 ACP（`session/resume`），该方案**尚未实测**，属后续切片。
- 权限（纠正 #70）：不要把 `danger-full-access` 写成默认建议；受限沙箱里的 EPERM 属嵌套执行现象，普通受控终端即可复核 spawn，并保持 `read-only` 沙箱与 `approval: never` 不变，不修改安全控制。
- 仍未验证：DSH 原生主控链路（模型侧工具可见、委派 `agent:kimi`、异身份验收、同会话收取）**未发生**；上述 `dump`/`probe` 证据停在配置层与进程层。

### ACP 原生会话入口（L1-2 续；#74）

`headless` 不能恢复原会话，原生续接能力在 ACP。本片新增一个**薄驱动**（验证工具，不是正式页面功能），
它只做 ACP 传输、会话控制与输出取证，不实现模型推理循环、不代替模型调用 TALK 工具。

| 文件 | 作用 |
|---|---|
| `scripts/dsh_acp_drive.py` | ACP v1 薄驱动：`spec` 渲染无密钥会话规格；`handshake` 零模型真实握手；`lifecycle` 零模型建会话→持久化→同 ID 恢复→失配/未知/重复拒绝；`prompt` 单条提示（需 `--allow-model`） |
| `deploy/dsh/acp-session.template.json` | 无密钥会话规格模板：`session/new` / `session/resume` 的 `mcpServers` 只含 TALK 启动器绝对路径与 `TALK_DSH_KEY_FILE`（路径，不是密钥） |
| `deploy/dsh/acp-overlay.template.yml` | ACP profile 的 `--patch` 覆盖层（**无占位符、可直接使用**）：仍禁 13 条原生/派生工具、只读沙箱；**不再覆盖 `approval`**（#76：`read-only + policy: never` 不匹配任何 preset），**不再 insert MCP**（ACP 的 MCP 是按会话声明的） |
| `scripts/dsh_talk_precheck.py` | `dump` 新增 `--profile`（默认 `headless`，行为不变）；ACP 覆盖层的组合树用 `--profile acp` 核对 |
| `tests/test_dsh_acp_drive.py` | 模拟 ACP 进程 + 隔离 TALK 服务的针对性测试（传输/下游参数/失败/恢复语义/权限/超时/凭证遮蔽/工具可达） |

#### 从本机原生代码核对的 ACP 契约（只读核对，非实测）

本机 `dsh` 核心为 `0.1.5-rc.1`（与 #71 一致），它自带并挂载的 ACP 插件
`@deepseek-ai/dsh-acp` / `@deepseek-ai/dsh-acp-app` 为 `0.1.5-rc.2`，ACP SDK 为 `1.4.0`；
ACP 协议版本为 `1`：

- 方法：`initialize` / `session/new` / `session/list` / `session/resume` / `session/close` /
  `session/prompt` / `session/cancel`；服务端反向请求 `session/request_permission`，通知 `session/update`。
- `initialize` 返回 `agentCapabilities.sessionCapabilities = {close, list, resume}`；
  `session/new` 参数为 `{cwd, mcpServers}`，返回 `{sessionId, configOptions}`；
  `session/resume` 参数为 `{sessionId, cwd, mcpServers?}`，**返回结果里没有 sessionId**——
  所以“同 ID 恢复”不能靠返回值自证，驱动改用四条证据：服务端接受该 ID、工作区不符被拒、
  **重复 resume（会话已在活动中）被拒**、恢复后该 ID 不再出现在 `session/list`。
- `session/list` **过滤活动会话**（#75 真机实证）：新建后该 ID 应不可见，`session/close`
  之后才作为持久化条目可见；驱动据此把“close 后可见”当作持久化证据（#76 D3）。
- `session/resume` 的错误分支（工作区不符 / 会话不可恢复 / 已在活动中）都是 `invalidParams`。
- stdio MCP 条目的 `env` 是 `{name, value}` 数组；`dsh-mcp-client` 的子进程环境 =
  `{...scrubbedParentEnv(), ...声明的 env}`，而 `scrubbedParentEnv()` 会按
  `/KEY|PASSWORD|SECRET|TOKEN/i` 与 `DSH_*` 清洗父环境——这正是 #70 记录的过滤现象，
  也是本片把 TALK 凭证改成“**声明 env 里只放密钥文件路径**”的原因。
- `dsh --profile acp` 由 `@deepseek-ai/dsh-acp-app` 提供：无额外参数，占用 stdio，stdin EOF 触发退出。

#### 使用步骤（零模型优先）

```powershell
# 1) 仓库外准备本人密钥（不回显、不写进仓库）
$k = Read-Host '粘贴 agent:deepseek 的 TALK API Key'
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.talk" | Out-Null
Set-Content -Path "$env:USERPROFILE\.talk\agent-deepseek.key" -Value $k -NoNewline -Encoding ascii
Remove-Variable k

# 2) 渲染无密钥会话规格（只打印；写盘需显式 --write）
#    ACP 覆盖层无占位符，可直接用仓库内文件；下表命令统一用变量 $overlay 指代。
$overlay = 'D:/claude-test/TALK/deploy/dsh/acp-overlay.template.yml'
python -X utf8 scripts/dsh_acp_drive.py spec --cwd D:/claude-test/TALK `
    --key-file "$env:USERPROFILE\.talk\agent-deepseek.key"

# 3) 零模型：真实 ACP 握手（不发起任何模型请求）
python -X utf8 scripts/dsh_acp_drive.py handshake --with-list `
    --dsh-home "<隔离或真实 DSH_HOME>" --patch $overlay `
    --cwd "<会话工作区>" --out "<取证 JSON>"

# 4) 零模型：建会话 → 持久化 → 同 ID 恢复 → 失配/未知/重复拒绝（模型调用数为 0）
python -X utf8 scripts/dsh_acp_drive.py lifecycle `
    --dsh-home "<DSH_HOME>" --patch $overlay --cwd "<会话工作区>" `
    --session-ref-out "<会话引用 JSON>"

# 5) 配置层：让 DSH 组合 acp profile + 覆盖层并导出配置树
python -X utf8 scripts/dsh_talk_precheck.py dump --profile acp `
    --patch $overlay --dsh-home "<DSH_HOME>" --out "<dump 输出>"

# 6) 模型阶段（**条件允许时才跑**）：单条提示，最多一次
python -X utf8 scripts/dsh_acp_drive.py prompt `
    --dsh-home "<DSH_HOME>" --patch $overlay --cwd "<会话工作区>" `
    --session-spec "<会话规格>" --allow-model --prompt-timeout 600 `
    --prompt-text "<任务正文>"
```

边界：

- `--patch` / `--dsh-home` 与 #72 一样先按调用者目录解析成绝对路径；ACP 服务进程的 cwd 固定为
  会话工作区，因此覆盖层里的 `!!js process.cwd()` 与会话工作区一致。
- 驱动**不会**把 `session/resume` 退化成 `session/new`，也不伪造同 ID；服务端拒绝时按失败退出。
- 下游参数（`--server-arg` / `--mcp-server-arg`，#76 D1）：**等号写法总是可用**
  （`--server-arg=-X`、`--server-arg=--profile`）；分离写法 `--server-arg -X` 也可用，但值不得与本
  驱动已注册的选项同名（如 `--cwd`），否则按用法错误退出（退出码 2），不把驱动选项静默传给下游。
- 权限请求默认按最保守的 `reject-once` 应答（`--permission allow` 才放行），应答内容进取证；
  覆盖层保留 DSH 默认的 `ask`，不存在自动批准路径。
- 超时、进程中途退出、MCP 启动失败都不会被记成成功；取证的 `model_calls` 如实区分 0/1。
- 驱动只把 `mcpServers` 原样交给 ACP 服务端：工具目录由被测会话内的模型可见性决定，
  **`probe` 式的“工具可发现”不等于模型已能委派**。
- ACP 服务进程的 stderr 默认写到系统临时目录的 `talk-dsh-acp-server.stderr.log`（可用
  `--stderr-log` 改到别处），取证里只带最后一段并做凭据遮蔽；stdout 只承载协议流量。

#### #76 返工：D1–D3 的结论与证据

- **D1（下游参数）**：`--server-arg` 现在接受前导连字符值，`-X utf8` 与 DSH `--profile` 都能传下去；
  测试用真实子进程的 `sys.orig_argv` 核对参数确实到达下游，并保留“缺值 / 与驱动选项同名”两个负例。
- **D2（覆盖层权限组合）**：真机 `dump --profile acp` 显示原生 preset 表为
  `read-only→ask`、`workspace-write→ask`、`danger-full-access→never`；原覆盖层强制
  `policy: never` 却保持只读沙箱，两个值不构成任何 preset，真实 `session/new` 报 `-32603 match no preset`。
  现覆盖层**不再覆盖 `approval`**，组合树里该行回落到 profile 默认表达式，在只读沙箱下求值为 `ask`
  （不自动放行，也不放宽沙箱）；**最终有效组合 = sandbox `read-only` + approval `ask`**，
  权限拒绝仍由驱动 `--permission reject`（默认）承担。未改全局 profile 与 headless 覆盖层。
- **D3（会话列表语义）**：`session/list` 过滤活动会话，因此 lifecycle 改为
  “活动期隐藏 → close 后可见 → resume 同 ID 后再次隐藏”，并新增重复 resume 负例与
  “持久化条目数正好少一条”的身份证据；模拟进程在 `session/new` 时即登记 active，不再按驱动预期伪造协议。

#### 三层结论（#79独立复核后的当前状态）

1. **配置层**：D1–D3修正已核验，ACP采用 `read-only + ask`，驱动默认拒绝权限；13条原生/派生工具禁用，规格只传密钥文件路径。headless配置未改。
2. **零模型ACP生命周期与回归**：#77在隔离DSH_HOME中实测真实初始化、建会话、关闭持久化、列表及同ID恢复通过，错误工作区/未知ID/重复恢复拒绝符合协议。#79独立复跑ACP 30项、入口18项全部通过，补齐开发环境因CreatePipe拒绝而未运行的18项。假密钥夹具显式放在仓库外并清理，缺密钥负例隔离HOME，不弱化仓库内凭证禁令。九工具可达与环境传递证据来自模拟ACP服务进程，不能等同真实模型工具可见。模拟管道仍有一条ResourceWarning（unclosed file），未影响用例结果，后续处理。
3. **模型阶段（#80–#84）**：真实DSH deepseek-v4-flash已完成单任务闭环：本人身份调用工具→委派Kimi只读任务82→Codex独立验收→同一ACP session通过 `prompt --resume <会话引用文件>` 读取并收取82。DeepSeek执行宿主CreatePipe受限，实际由Kimi可运行环境操作原生DSH，未由操作员替代模型委派/收取。两次驱动prompt不代表两次底层模型请求。仅验证有人值守、同工作区；多工作区/无人值守/页面适配仍未验收。原始会话与脱敏证据保留在 `.tmp/l1-dsh-live/`，隔离模型凭证副本在试验结束后删除，后续恢复须重新准备合法模型配置。

### 回归命令

```powershell
python -X utf8 -m unittest tests.test_dsh_talk_entry tests.test_dsh_acp_drive -q
```


### WorkBuddy桌面验证结果（2026-09-17）

WorkBuddy5.5.6通过用户级MCP界面导入TALK条目，复用现有 `bridges/talk_terminal_mcp.py`，无需本轮修改业务代码。专用身份为 `agent:workbuddy`，凭证与准备配置留在仓库外；请勿将含密钥配置提交版本库。项目级文件自动读取尚未验证，不把包内CodeBuddy CLI/ACP能力等同桌面能力。

用户在桌面选kimi-k3完成任务90、选deepseek-v4-pro完成任务91：一次委派→执行者交付→原对话只读读取→Codex人工验收→明确指令原对话收取。服务端日志分别于北京时间15:39:30与15:45:18确认专用身份POST collect-result返回200；同对话及模型选择由用户回传支持。88提前收取的具体会话来源仍未定位，91补测不改变这一历史边界。

结论仅覆盖有人值守的单任务流程，不覆盖跨重启会话恢复、多工作区、无人值守和TALK页面运行器适配。连接先看实际MCP状态与只读工具调用，不预设必须重启。

## 2026-09-18 项目开发要求接入边界

REQ-1后端与主控工具已通过独立复核；项目API支持最新纯文本要求，角色页编辑区REQ-2已通过独立复审，页面效果待用户验收。MCP工具仍为九个，`talk_list_agents` 顶层新增要求字段，`talk_delegate_task` 派发时读取并保存正文快照，读取失败即报错，不静默创建缺少要求的任务。要求不能覆盖宿主系统指令或自动授予权限。

本片未重启服务或MCP；部署新服务代码并完成数据库启动迁移、让MCP加载新实现后方可使用。工具描述刷新需要客户端重连，不能把代码提交当作运行中宿主已经更新。直接REST、定时任务和旧pi TypeScript入口不自动追加快照。完整字段/清空/权限合同见 `docs/spec/PROJECT_INTEGRATION.md` 的REQ-1节。

角色页使用与人工验收见 [项目开发要求验收指南](PROJECT_REQUIREMENTS_ACCEPTANCE.md)。主控派发前读取项目最新要求；没有有效分工且本次会话无明确指定时，先请用户配置，不自动套用示例。
