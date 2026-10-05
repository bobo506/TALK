# DeepSeek Harness 桌面端接入 TALK 任务工具

本指南面向 **DeepSeek Harness 桌面端**（已安装 0.2.0-rc.2，Electron 应用）。目标链路是：

```text
桌面独立会话 → TALK MCP（既有 bridges/talk_terminal_mcp.py）→ TALK 任务 → 现有 Agent/bridge 执行 → 桌面原会话读取/收取
```

桌面在这里只是**任务发起工具客户端**：不替换受管 CLI、不新增 DeepSeek worker/member、不重做服务端。执行仍然由现有 `agent:codex` / `agent:kimi` / `agent:deepseek` bridge 承担。

一句话结论：**桌面端没有 MCP 配置表单，接入入口就是桌面 profile 的 YAML patch 层文件**；模板 `deploy/dsh/desktop-talk-mcp.patch.template.yml` 按下面的步骤落到 `%USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml` 即可。

---

## 1. 从已安装版本核对到的配置事实

以下事实全部来自**本机已安装的 0.2.0-rc.2**（只读核对安装目录与 `app.asar` 内的公开配置/加载代码），不是从 CLI 或 headless 推测的。

| 项 | 结论 | 依据（安装版实际位置） |
|---|---|---|
| 安装版本与位置 | `DeepSeek Harness 0.2.0-rc.2`，安装目录 `D:\deepseek harness` | 注册表 Uninstall 项 `InstallLocation`；`resources/app.asar` 根 `package.json` = `@deepseek-ai/dsh-desktop` 0.2.0-rc.2 |
| 使用的 profile | `desktop`（Electron 保留 profile） | `lib/main.js`：`resolveDesktopPaths()` 返回 `profile = <DSH_HOME>/profiles/desktop`，并以该目录为 cwd 启动 Host 子进程 |
| 桌面启动方式 | `runProfile({ profile: "desktop", patchFiles: [], args: ["--no-open","--port","19387"] })` | `node_modules/@deepseek-ai/dsh-desktop-host/lib/index.js` |
| profile 保存位置 | `%USERPROFILE%\.dsh\profiles\desktop\`（即 `<DSH_HOME>/profiles/desktop`） | 同上；本机实际存在 `cordis.yml` / `cordis.patch.yml` / `package.json` / `pnpm-workspace.yaml` |
| 组合包来源 | `dsh-base` + `dsh-web-app` | profile 的 `package.json` → `dsh.profile.bundles` |
| **MCP 配置入口** | **`<DSH_HOME>/profiles/desktop/cordis.patch.yml`**（用户 patch 层），格式是顶层 YAML 数组的 loader patch | `@deepseek-ai/dsh-app-boot`：`loadProfileDirectory()` 读该文件作为 profile 用户层 |
| 插件条目格式 | `- insert:` / `- id:` + `name:` + `config:`；`!!js` 表达式可用 | `@deepseek-ai/cordis-plugin-include` 的 `PatchOptions`；`parsePatchList()` 要求顶层数组，否则报错 |
| 配置优先级 | bundle 层 → **profile 用户层** → **home 用户层**（`<DSH_HOME>/cordis.patch.yml`）→ 启动参数 `--patch` 层 | `dsh-app-boot` 的 `readProfilePatches()` |
| 桌面是否吃 `--patch` | **不吃**：桌面启动时 `patchFiles` 为空，只组合两份用户 patch 文件 | `dsh-desktop-host/lib/index.js` |
| GUI 里能配 MCP 吗 | **不能**。桌面只有 `ui-plugin-manager`（Plugins 页，按 pnpm 管理 profile 的 **bundle**：安装/启停/卸载）与 `ui-settings-plugin-inventory`（只读 Plugin 清单） | `dsh/node_modules/@deepseek-ai/dsh-web-app/cordis.patch.yml` 的行 id；0.2.0-rc.2 全部包中没有任何 MCP 服务器表单 |
| 重载方式 | 保存 patch 文件后由 **HMR 热重载**（无需重启）；HMR 不可用时改动重启后生效 | `dsh-base` 的 `hmr` 行 = `@deepseek-ai/dsh-hmr`，`disabled: !!js "!ctx.get('profileContext')"`；`dsh-hmr/README.zh.md` 说明它注册 profile manifest 与**两份用户 patch** 的监听 |
| 重载时延 | 文件监听默认 `awaitWriteFinish`，约 2 秒写入稳定窗口后才触发 | `dsh-hmr/README.zh.md` |
| 回滚 | 删掉追加的 `- insert:` 块即可；桌面自身还有"备份 profile patch 并只保留内置 bundle"的恢复路径（会生成 `cordis.patch.yml.bak-<时间戳>`） | `lib/main.js` 的 `DesktopProjectManager.disableAllPlugins()` / `sanitizeProfile()` |

关于"CLI 拒绝 `desktop` profile"：`dsh` 命令行在 `--profile desktop` 启动/dump 时被**显式拒绝**（"profile \"desktop\" is managed exclusively by the Electron application"，见 `@deepseek-ai/dsh/lib/bin.js` 的 `rejectElectronProfile`）。这个拒绝只作用于 CLI 自己的启动路径，**不代表桌面不可用 MCP**：桌面 Host 直接用同一个 loader 组合同一份 `cordis.patch.yml`，只是我们必须放弃"用 CLI 对 desktop profile 做 `--dump-config` 校验"这条路。

插件与工具命名（`@deepseek-ai/dsh-mcp-client`，同为 0.2.0-rc.2）：

- 每个服务器一条配置项；stdio 分支字段为 `serverName` / `transport` / `command` / `args` / `env` / `cwd`，另有 `toolCallTimeoutMs`（默认 `60000`）、`failOnStartupError`（默认 `false`）、`maxInstructionBytes`、`reconnect.*`。
- 模型侧工具名固定为 `mcp__<serverName>__<工具名>`；本文用 `serverName: talk`，所以是 `mcp__talk__talk_list_agents` 这一族。
- stdio 子进程环境以**清洗过的父环境**为基座（删除匹配 `/KEY|PASSWORD|SECRET|TOKEN/i` 与 `DSH_*` 的变量），再合并配置里显式声明的 `env`。所以"配置里给密钥文件**路径**"是有效写法，"指望继承 `TALK_API_KEY` 环境变量"不是。
- 首次连接先起一个临时 stdio 探测进程，再起实际服务进程；这是 MCP 客户端的既有行为。

---

## 2. 前置条件

- TALK 服务已启动，项目已注册，角色已同步；目标 Agent 的 bridge 已在线（角色 `offline` 时任务不会被领取）。
- Python 3.11+，且已安装仓库 `requirements.txt`（MCP 入口是 Python stdio 服务）。
- **仓库外**已准备好本人 TALK 成员密钥文件，默认 `%USERPROFILE%\.talk\agent-deepseek.key`：只含一行可打印 ASCII，不带 BOM 与多余内容。不要放进仓库，也不要写进任何被提交的文件。
- 已安装的桌面端版本与本文核对的一致（0.2.0-rc.2）。若版本不同，请重新核对第 1 节的入口与字段，不要直接照搬。

---

## 3. 接入步骤

### 3.1 确认目标文件

推荐只影响桌面 profile：

```text
%USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml
```

备选（会影响**所有** profile，包括既有 headless/web 配置）：`%USERPROFILE%\.dsh\cordis.patch.yml`。本机当前不存在 home 层文件，所以默认按 profile 层走。

该文件是**顶层 YAML 数组**，里面通常已经有桌面自己写的设置项（例如 `ui-theme`、`agent-default-model`）。**追加**我们的 `- insert:` 块，不要覆盖整个文件。

### 3.2 先备份

```powershell
$patchFile = "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml"
Copy-Item $patchFile "$patchFile.bak-manual" -Force
```

### 3.3 替换模板占位符

模板是 `deploy/dsh/desktop-talk-mcp.patch.template.yml`（无密钥）。需要替换 5 个占位符，全部填**真实绝对路径**：

| 占位符 | 填什么 | 示例 |
|---|---|---|
| `__PYTHON__` | Python 解释器绝对路径 | `D:/claude-test/TALK/.venv/Scripts/python.exe` |
| `__REPO__` | TALK 仓库根目录 | `D:/claude-test/TALK` |
| `__SERVER__` | TALK 服务地址 | `http://127.0.0.1:8000` |
| `__PROJECT__` | 已注册项目 id | `prj_e8fe7066bbec` |
| `__KEY_FILE__` | 仓库外密钥文件绝对路径（**只写路径**） | `C:/Users/Administrator/.talk/agent-deepseek.key` |

**路径含空格或中文怎么填**（例如仓库放在 `D:/deepseek harness` 或 `C:/用户/我的 项目`）：

- 统一用正斜杠 `/`，不要用 `\`（YAML 里反斜杠是转义字符）。
- 整段路径**保留模板里已有的单引号**：`command: 'D:/Program Files/Python/python.exe'`、`cwd: 'D:/我的 项目/TALK'`、`- 'D:/我的 项目/TALK/scripts/dsh_talk_mcp_launch.py'`。
- `args` 里每个 `- '...'` 就是**一个**参数，空格不会拆参；不要手动加引号嵌套，也不要把路径写成两条。
- 路径里如果本身带单引号，把单引号写成两个（YAML 转义）。

### 3.4 追加到 patch 文件

用编辑器把替换好的 `- insert:` 整块贴到 `cordis.patch.yml` **末尾**（顶层列表项顶格，缩进与文件内既有的 `- id:` 项一致）。

也可以用 PowerShell 一次性追加（避免 BOM）：

```powershell
$repo = 'D:/claude-test/TALK'
$tpl  = Get-Content -Raw "$repo/deploy/dsh/desktop-talk-mcp.patch.template.yml"
$tpl  = $tpl.Replace('__PYTHON__',   'D:/claude-test/TALK/.venv/Scripts/python.exe')
$tpl  = $tpl.Replace('__REPO__',     $repo)
$tpl  = $tpl.Replace('__SERVER__',   'http://127.0.0.1:8000')
$tpl  = $tpl.Replace('__PROJECT__',  'prj_e8fe7066bbec')
$tpl  = $tpl.Replace('__KEY_FILE__', "$env:USERPROFILE/.talk/agent-deepseek.key".Replace('\','/'))
$patchFile = "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml"
$existing  = Get-Content -Raw $patchFile
$text = $existing.TrimEnd() + "`n`n" + $tpl
[System.IO.File]::WriteAllText($patchFile, $text, (New-Object System.Text.UTF8Encoding $false))
```

写入前先打印 `$text` 检查一遍；模板里不能出现密钥正文。

### 3.5 重载

1. 保存后等 **2 秒以上**（HMR 的写入稳定窗口），配置会重新组合并挂载 `mcp-talk`。
2. 如果想确认它有没有被组合进去：桌面「设置 → 插件」的只读清单里应能看到 `mcp-talk` 行（该清单是当前 Loader 条目的只读投影）。
3. 没生效时的兜底：**退出并重新打开桌面 App**（HMR 不可用时改动只在重启后生效）。patch 文件语法错误会让 profile 启动失败并报错；此时用第 3.2 节的备份还原。
4. **不要**试图用 `dsh --profile desktop` 做校验——CLI 会直接拒绝该 profile。

### 3.6 在独立会话里确认工具

新建一个**独立调度会话**（不要续写 worker 正在写入的任务会话），然后：

- 让模型列出它可用的 TALK 工具，或直接调用 `mcp__talk__talk_list_agents`；
- 预期能拿到九个工具：`talk_list_agents`、`talk_delegate_task`、`talk_get_task`、`talk_list_tasks`、`talk_wait_tasks`、`talk_reply_task`、`talk_cancel_task`、`talk_collect_result`、`talk_get_delivery`。
- 没有 `talk_send`：它依赖 bridge 在当前轮结束后处理延迟记录，独立入口不展示也不接受。

---

## 4. 身份、范围与权限合同

- **请求者身份来自密钥**：服务端按 API Key 反查成员，入口忽略继承的 `TALK_MEMBER_ID`。桌面 UI、模型或会话标题都不能改变身份。
- **工具范围**：桌面主控只拿到上面九个任务工具；它们是任务/项目读写的受控接口，不是管理员接口。
- **角色页主控指定和业务标签不自动授予权限**：`talk_list_agents` 暴露的项目要求与主控模式字段是**配置意向**，不等于职责已经生效；生产环境里的主控指定、`decision_tier`、群内业务标签与既有权限**都不因本接入改变**。接入入口本身也不会让任何成员升级为决策/主控角色。
- **授权来自用户**：由用户在桌面会话里**明确**要求发起某个受控 TALK 任务，才构成这一次派发的授权；单次独立顶层任务仍需业务授权，不能只因接口允许创建就视为已获授权。
- **不新增执行者**：执行仍由现有 bridge 承担。本接入不新增 worker、不新增 member、不改 launcher/MCP 服务/bridge/服务端/数据库。
- **权限边界在服务端**：工具参数里的 `project_id` 只是取值覆盖，不是权限隔离边界。
- 如果发现"现有身份无法使用某个指定工具"，正确做法是**记录实际缺口与最小建议**并交主控，不擅自改权限或创建新成员。本片未发现必须修改既有程序的缺口。

---

## 5. 手工验收步骤（含本片已执行/未执行标注）

> 本片**没有**操作 GUI、没有启停桌面或 bridge、没有发起真实委派。下面第 1–6 步全部是**预期步骤**，需要在用户接入阶段人工执行；第 0 步的一部分已由本片以只读方式执行，证据见 `.tmp/dsh-desktop-mcp-1/`。

| # | 步骤 | 预期结果 | 本片状态 |
|---|---|---|---|
| 0a | 离线校验模板结构 | 顶层数组、`mcp-talk` 行存在、config 字段全在安装版 schema 内、无密钥正文 | **已执行**（`logs/validate-template.log`，`ok=true`） |
| 0b | 用既有入口做 stdio 工具目录核对 | `initialize` + `tools/list` 返回九个工具、`serverInfo.name=talk_tools_mcp` | **已执行**（`logs/probe-desktop-template.log`，`tools_match=true`） |
| 0c | 用本人 `agent:deepseek` 凭据做只读身份/项目核对 | `ok=true`、member=`agent:deepseek`、project=`prj_e8fe7066bbec` | **已执行**（`logs/check-identity.log`） |
| 1 | 在桌面新开**独立调度会话**，不复用也不续写 worker 正在写入的任务会话 | 会话正常打开，工作区是预期项目 | 未执行（需 GUI） |
| 2 | 确认 TALK MCP 已加载（工具可见） | 九个 `mcp__talk__*` 工具可见 | 未执行（需 GUI） |
| 3 | 用 `talk_list_agents` 列项目 Agent 并核身份 | 看到 `agent:codex` / `agent:kimi` / `agent:deepseek` 及其 `availability` | 未执行（需 GUI/模型） |
| 4 | 由用户在桌面**明确**派一个限定任务 | 任务在 TALK 创建成功，带上范围与验收标准 | 未执行 |
| 5 | 现有 bridge 领取并执行 | 任务从 `queued` 走到 `submitted`，结果消息落在该任务 Hall | 未执行 |
| 6 | **用户通知后**，在同一桌面会话读取并收取 | `talk_get_delivery` 读到交付摘要 → `talk_collect_result` 后 `workflow_status=completed` | 未执行 |

验收支持**人工唤回**即可：本片不扩展无人值守、不启用自动转审、不做 600 秒等待改造。等待超时不会取消执行者任务，主控若用 `talk_wait_tasks`，客户端单工具超时必须大于 600 秒（建议 ≥ 660 秒）。

---

## 6. 回滚

1. 删掉 `cordis.patch.yml` 里追加的 `- insert:` 块，或直接用第 3.2 节的备份覆盖回去。
2. 等 HMR 重载（约 2 秒写入稳定窗口）；不生效就重启桌面 App。
3. 工具随之消失，其余桌面设置不受影响。若桌面已因 patch 语法错误无法启动，恢复备份后重启；桌面自身的恢复路径也会把 profile patch 备份成 `cordis.patch.yml.bak-<时间戳>`。

---

## 7. 限制、缺口与未验证项

**本片未验证（不得当成已通过）**

- **桌面内真实加载与工具可见**：未在 GUI 里实测；HMR 生效与 `mcp-talk` 行出现都属于预期，需要用户接入阶段人工确认。
- **桌面进程实际使用的 `DSH_HOME`**：本片只核对了路径解析代码与本机默认目录 `%USERPROFILE%\.dsh`；没有重新确认运行中的桌面进程是否有进程级 `DSH_HOME` 覆盖。若桌面用了别的 home，patch 文件要放到那个 home 下。
- **CLI 侧的 desktop profile 组合校验**：CLI 显式拒绝该 profile，所以"桌面组合树"无法用 `--dump-config` 旁证。
- **真实委派/收取闭环**：本片没有派发任务、没有调用模型、没有收取结果。

**已知限制**

- `talk_wait_tasks` 最长等待 600 秒，而模板沿用既有覆盖层的 `toolCallTimeoutMs: 65000`。要在桌面里用长等待，请把它调大（例如 `660000`），否则客户端会提前取消。
- stdio 协商会先起一个临时探测进程，属于 MCP 客户端既有行为，不是 TALK 新增逻辑。
- 桌面 profile patch 与 home patch 都会被 HMR 监听；两者都写同一条 `id` 时以**后加载**的 home 层为准（home 层优先级更高）。
- TALK 的 claim/租约与进程内运行锁只约束**受管任务**；桌面会话与 bridge worker 若同时写同一个 DSH 会话，仍可能互相干扰——"单执行 owner"是使用约束，不是服务端强制。因此第 5 步要求开**独立**调度会话。
- 桌面 GUI 只按 pnpm 管理 profile 的 bundle；想"在界面上一键开关 TALK MCP"属于桌面自身功能，不在本仓库范围。

**缺口与建议**

- 本片未发现必须修改既有程序才能接入的缺口；`scripts/dsh_talk_mcp_launch.py`、`bridges/talk_terminal_mcp.py`、`scripts/dsh_talk_precheck.py` 均直接复用、未改动。
- 后续若要让桌面支持"不改 YAML 就能配 MCP"，那是桌面端产品能力，需要单独立项并由主控裁决，不在本仓库擅自实现。

---

## 8. 可复现的离线校验命令

以下命令都在 TALK 仓库根目录执行，全部零模型、不派发任务、不写真实 DSH home：

```powershell
# 1) 模板结构 / 字段 / 无密钥 的离线核对（对照已安装 0.2.0-rc.2 的 schema 与 bundle 行）
python -X utf8 .tmp\dsh-desktop-mcp-1\probes\validate_desktop_template.py

# 2) 渲染一份隔离副本（只落在 .tmp 内），再用既有入口核对 stdio 工具目录
python -X utf8 .tmp\dsh-desktop-mcp-1\probes\render_desktop_template.py .tmp\dsh-desktop-mcp-1\isolated\desktop-talk-mcp.patch.yml
python -X utf8 scripts\dsh_talk_precheck.py probe --patch .tmp\dsh-desktop-mcp-1\isolated\desktop-talk-mcp.patch.yml

# 3) 只读身份与项目核对（读取仓库外本人密钥文件，只打印身份/项目/角色状态，不打印密钥）
python -X utf8 scripts\dsh_talk_precheck.py check --server http://127.0.0.1:8000 `
    --project prj_e8fe7066bbec --expect-member agent:deepseek --expect-project prj_e8fe7066bbec
```

`probe` 只证明"配置可解析、进程可启动、工具目录正确"，不访问服务端；`check` 证明"凭证对应成员与项目正确"。两者都**不代表**桌面内已经加载成功——那需要第 5 步的人工验收。

相关既有文档：[普通终端接入 TALK 任务工具](TERMINAL_MCP.md)、[任务工作流](TASK_WORKFLOW.md)。
