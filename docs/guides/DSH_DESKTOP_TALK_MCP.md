# DeepSeek Harness 桌面端接入 TALK 任务工具

本指南面向 **DeepSeek Harness 桌面端**（已安装 0.2.0-rc.2，Electron 应用）。目标链路是：

```text
桌面独立会话 → TALK MCP（既有 bridges/talk_terminal_mcp.py）→ TALK 任务 → 现有 Agent/bridge 执行 → 桌面原会话读取/收取
```

桌面在这里只是**任务发起工具客户端**：不替换受管 CLI、不新增 DeepSeek worker/member、不重做服务端。执行仍然由现有 `agent:codex` / `agent:kimi` / `agent:deepseek` bridge 承担。

一句话结论：**桌面端没有 MCP 配置表单，接入入口就是桌面 profile 的 YAML patch 层文件**；模板 `deploy/dsh/desktop-talk-mcp.patch.template.yml` 按下面的步骤落到 `%USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml` 即可。

**本机当前状态（2026-10-05）**：桌面 profile 的 `mcp-talk` 配置已备份/追加并读回校验，用户已完成人工验收：DeepSeek 桌面 → TALK → Kimi → TALK → 原 DeepSeek 桌面对话派发/交付/收取闭环通过（任务 #151）。当前结果见第 5.4 节；65 秒工具超时下的长等待稳定性另列待办。

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

### 3.2 先备份（唯一时间戳名，禁止 `-Force` 覆盖）

```powershell
$patchFile = "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml"
$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "$patchFile.bak-manual-$stamp"
if (Test-Path -LiteralPath $backup) { throw "备份名已存在，停止：$backup" }
Copy-Item -LiteralPath $patchFile -Destination $backup
"已备份到 $backup"
```

不要用固定名 `cordis.patch.yml.bak-manual` 加 `-Force`：那会覆盖上一次的备份，之后要核对"原始字节"就无据可依。还原时同样只从**本次**的唯一备份取，不覆盖更新的备份（见第 6 节）。

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

也可以用 PowerShell 一次性追加。下面这段**只渲染模板里 `- insert:` 起始的配置块**：模板头部的说明注释既不会被占位符替换改写、也不会写进 patch 文件；模板与目标文件的读写都显式使用 **UTF-8（无 BOM）**：

```powershell
$repo = 'D:/claude-test/TALK'
$tplPath = "$repo/deploy/dsh/desktop-talk-mcp.patch.template.yml"
# 显式按 UTF-8 读取模板（File.ReadAllText 同时会剥掉可能存在的 BOM）
$tpl = [System.IO.File]::ReadAllText($tplPath, [System.Text.UTF8Encoding]::new($false))
# 只取行首的 `- insert:`：模板注释里也出现过该字样，所以必须按行首锚定
$m = [regex]::Match($tpl, '(?m)^- insert:')
if (-not $m.Success) { throw '模板里找不到行首的 - insert: 块' }
$block = $tpl.Substring($m.Index)
$block = $block.Replace('__PYTHON__',   'D:/claude-test/TALK/.venv/Scripts/python.exe')
$block = $block.Replace('__REPO__',     $repo)
$block = $block.Replace('__SERVER__',   'http://127.0.0.1:8000')
$block = $block.Replace('__PROJECT__',  'prj_e8fe7066bbec')
$block = $block.Replace('__KEY_FILE__', ($env:USERPROFILE + '/.talk/agent-deepseek.key').Replace('\','/'))
if ($block -match '__[A-Z_]+__') { throw '仍有未替换的占位符' }
# 目标文件同样显式 UTF-8 读取；原有内容原样保留，只在末尾追加
$patchFile = "$env:USERPROFILE\.dsh\profiles\desktop\cordis.patch.yml"
$existing  = [System.IO.File]::ReadAllText($patchFile, [System.Text.UTF8Encoding]::new($false))
$text = $existing.TrimEnd() + "`n`n" + $block.TrimEnd() + "`n"
[System.IO.File]::WriteAllText($patchFile, $text, (New-Object System.Text.UTF8Encoding $false))
```

写入前先打印 `$block` 检查一遍；模板里不能出现密钥正文。这段脚本**只追加**，不改动原有条目，模板注释不会进入 patch 文件。

> 写入前请先按第 3.2 节备份，并确认目标目录可写。若宿主文件沙箱只允许写仓库工作区（例如受限执行环境），备份与写入都会以 `PermissionError/拒绝访问` 失败；此时应按本文档流程改为人工在授权会话里落地，不要绕过沙箱。

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

> 主控没有操作 GUI 或自动启停桌面/bridge；配置准备的 0a–0c 证据见 `.tmp/dsh-desktop-mcp-1/`。用户已在桌面对话完成人工派发/交付/收取验收（#151，见第 5.4 节）；表内核心链路按用户确认记为通过，不表示九个工具的全部动作与长等待都已测试。

| # | 步骤 | 预期结果 | 本片状态 |
|---|---|---|---|
| 0a | 离线校验模板结构 | 顶层数组、`mcp-talk` 行存在、config 字段全在安装版 schema 内、无密钥正文 | **已执行**（`logs/validate-template.log`，`ok=true`） |
| 0b | 用既有入口做 stdio 工具目录核对 | `initialize` + `tools/list` 返回九个工具、`serverInfo.name=talk_tools_mcp` | **已执行**（`logs/probe-desktop-template.log`，`tools_match=true`） |
| 0c | 用本人 `agent:deepseek` 凭据做只读身份/项目核对 | `ok=true`、member=`agent:deepseek`、project=`prj_e8fe7066bbec` | **已执行**（`logs/check-identity.log`） |
| 1 | 在桌面新开**独立调度会话**，不复用也不续写 worker 正在写入的任务会话 | 会话正常打开，工作区是预期项目 | 桌面对话核心链路已通过；新建独立会话/工作区细节未逐项记录 |
| 2 | 确认 TALK MCP 已加载（工具可见） | 九个 `mcp__talk__*` 工具可见 | 核心工具实际调用通过；九工具逐项显示未单独记录 |
| 3 | 用 `talk_list_agents` 列项目 Agent 并核身份 | 看到 `agent:codex` / `agent:kimi` / `agent:deepseek` 及其 `availability` | 准备阶段身份预检已通过；本次桌面调用未单独记录 |
| 4 | 由用户在桌面**明确**派一个限定任务 | 任务在 TALK 创建成功，带上范围与验收标准 | 通过：#151，由 agent:deepseek 派给 Kimi |
| 5 | 现有 bridge 领取并执行 | 任务从 `queued` 走到 `submitted`，结果消息落在该任务 Hall | 通过：用户确认 Kimi 领取/执行/交付；runner succeeded |
| 6 | **用户通知后**，在同一桌面会话读取并收取 | `talk_get_delivery` 读到交付摘要 → `talk_collect_result` 后 `workflow_status=completed` | 通过：用户确认收取；#151 completed |

验收支持**人工唤回**即可：本片不扩展无人值守、不启用自动转审、不做 600 秒等待改造。等待调用超时不等于执行者任务已取消。若单次请求 `talk_wait_tasks(600s)`，客户端单工具超时需覆盖该等待时长及通信余量；当前 65 秒配置不满足，未在本片调整。

### 5.1 #147 配置准备历史（实际写入结果见第 5.3 节）

上表 0a–0c 是 #145 的离线/只读证据；本片在它们之上补做了目标确认与候选校验，**真实 profile 文件尚未被修改**：

- **目标已逐进程确认**：运行中的桌面 Host 进程命令行里直接带着 profile 路径 `C:\Users\Administrator\.dsh\profiles\desktop`（`--expose-internals .../dsh-desktop-host/lib/index.js` 之后的参数），其工作目录也是该目录；桌面主进程环境里**没有** `DSH_HOME` 覆盖，`User`/`Machine` 级也未设置，因此本次运行解析到默认 home。目标文件据此锁定为 `C:\Users\Administrator\.dsh\profiles\desktop\cordis.patch.yml`。
- **目标层无冲突**：该文件是顶层数组、原有 6 个条目，既没有 `id: mcp-talk` 也没有 `serverName: talk`；home 层 `%USERPROFILE%\.dsh\cordis.patch.yml` 不存在。按“追加不覆盖”处理即可。
- **候选已渲染并离线校验通过**：只渲染 `- insert:` 配置块（模板头部注释不入档），5 个占位符全部替换，含空格/中文/单引号的路径转义自测通过，字段集合与安装版 0.2.0-rc.2 的 stdio schema 一致；与真实目标文件的“内存合并”结果保持原文件字节为前缀、原有条目一条不变、只多出一个 `mcp-talk`。既有入口 `probe` 返回九个工具，只读身份核对返回 `agent:deepseek` / `prj_e8fe7066bbec`。
- **尚未落盘**：本片所在会话的宿主文件沙箱只允许写仓库工作区，向 `%USERPROFILE%\.dsh\profiles\desktop\` 建立同目录时间戳备份即被拒绝（`PermissionError: [Errno 13]`；该目录对沙箱用户只有读+执行权限）。按“先备份再写、不绕过沙箱、不擅自扩大权限”的约束，本片停在此处并交付候选，**没有**改动真实 profile。候选块与只读证据在 `.tmp/dsh-desktop-mcp-2/`（`.tmp/` 不入库，属临时产物）：`candidate/talk-mcp-insert-block.yml` 是替换好全部占位符的 `- insert:` 块，`candidate/render-metadata.json`、`logs/validate-candidate.json`、`logs/probe-candidate.log`、`logs/check-identity.log` 是校验与探针证据。

因此上表第 1–6 步仍然全部是**用户接入阶段的人工验收步骤**；配置落地需要在有该目录写权限的会话里按第 3 节执行。

### 5.2 #149 落地保护修正（经 #150 独立复核通过）

`#148` 独立复核在候选重渲染、安装版 schema、内存合并、R1 修正与权限处理都通过的同时，列出两项低中保护缺口：原落地脚本没有候选块哈希守卫（同 `id`/`serverName` 但改过 `command`/`env` 的候选也能通过写后校验），以及写前哈希检查与 `os.replace` 之间存在目标外部修改窗口。本片按决策裁决**先补缺口**，仍然**没有**写真实 profile：

- 修订脚本（临时产物，`.tmp/` 不入库）：`.tmp/dsh-desktop-mcp-2-fix/probes/apply_target_patch.py`，sha256 `ecd9235164a76d5a0f682eef3e308ded133476d1e36bbf20c641f5a7a32288f6`。接口：`--expect-block-sha256` 与 `--expect-target-sha256` 必填且必须是 64 位十六进制，`--log` 必填（默认拒绝覆盖同名日志），其余为 `--target` / `--block` / `--log-overwrite` / `--attempts-note`。
- 候选哈希守卫：候选字节读入后立即复算并比对钉住值，不匹配就在任何备份、临时文件、替换写入之前拒绝。
- 替换前二次核对：写完同目录临时文件后**重新读取真实目标**复核已审哈希；目标已变即停止，只清理本次临时文件、保留备份供核对，绝不覆盖外部新内容。写后校验失败的自动回滚同样先核验"目标仍是本次写入的字节"，已被外部改动就停止交人工，不用旧备份覆盖。
- 附带加固：写入前预检重复 `id: mcp-talk` / `serverName: talk`；备份名唯一且用独占创建，拒绝覆盖既有备份，按原始字节存；`--target` / `--block` / `--log` 走白名单，不能借参数指向任意外部目录；默认目标与默认候选各自钉住本片已审完整 sha256 —— 目标 `4366d52223a9abebe1f8735d980226783a74a32fe8b927b9f187c2e1eb02b085`，候选 `41eeab30f709afd07485d892a65a29ff11241902f479e7d790e99497f9760dea`。
- 隔离 fixture 证据：`.tmp/dsh-desktop-mcp-2-fix/fixture-results.json`（14 组，`all_pass=true`），覆盖正常追加、篡改候选提前拒绝、目标初始哈希不符拒绝、替换前外部改动拒绝并完整保留外部内容、写后失败回滚与"外部已改则不回滚"、重复条目预检、备份名碰撞、日志目的地隔离、哈希参数与路径白名单，并复核 `#147`/`#148` 的原脚本、候选、日志与 mtime 证据未被覆写。
- **残余限制（不得当成已消除）**：最后一次核对与 `os.replace` 之间仍有跨进程写入窗口，本实现只能把窗口压到最小并保证"发现即停"，不能宣称两次哈希消除了该竞态；脚本不新增 CRLF 通用支持（CRLF 目标会在写后 `post_lf_only` 校验失败并回滚），真实目标条件明确为 UTF-8 无 BOM + LF。
- #149 交付时真实 profile **尚未写入**；其后 #150 定向独立复核通过，主控核对对象与完整哈希后经宿主审批通道完成实际写入，结果见第 5.3 节。

### 5.3 主控实际配置落地（2026-10-05；人工验收见第 5.4 节）

- **已写入**：`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`。执行前再次核对桌面主进程 PID 3084 的启动时间与 Host PID 13068 的实际 profile 参数，仍对应此目录；脚本、候选与目标完整哈希均与独立复核一致。
- **唯一备份**：同目录 `cordis.patch.yml.bak-talk-mcp-2-fix-20261005-180915`，1045 字节，SHA-256 `4366d52223a9abebe1f8735d980226783a74a32fe8b927b9f187c2e1eb02b085`。原文件和备份内容不复制到仓库。
- **实际写入成功**：经宿主审批通道执行已审修订脚本，`rc=0`、`ok=true`；候选/原目标哈希、重复预检、唯一备份核验、替换前二次核对全部通过。独立读回再次核验原字节前缀和原六项设置完整保留，仅新增一个 `mcp-talk`，无临时文件残留。
- **写后文件**：2275 字节，SHA-256 `245407f8390e5086c2bfde3f268241484028b12a183951089b2541deae2398d6`，与已审合并计划一致；显式环境仅 UTF-8 开关与 TALK 密钥文件路径。继续复用既有启动器、TALK MCP 和执行 bridge。
- **证据**：`.tmp/dsh-desktop-mcp-2-fix/logs/apply-target-20261005-codex-1.json`、`logs/codex-post-apply-check.json`。#147–#150 的已完成交付已收取，历史 partial/无效原报告保持；这不代表桌面闭环已经验收。
- **落地后的验收步骤（核心闭环已通过，细项记录边界见表格与第 5.4 节）**：在桌面新建独立调度对话，调用 `talk_list_agents`（项目 `prj_e8fe7066bbec`），确认工具可用和三名角色/最新开发要求；明确授权一个限定的只读任务交现有 Agent 执行；完成后在同一桌面对话先 `talk_get_delivery` 再 `talk_collect_result`。完整步骤与预期见第 5 节表格。
- **主控落地阶段的验证边界**：当时只确认配置落盘与读回，没有操作 GUI、调用桌面模型或派发测试；随后用户的真实调用验收另记在第 5.4 节。主控未自动重启桌面或 bridge，65 秒单工具超时仍不支持 600 秒长等待。

### 5.4 用户桌面闭环验收通过（2026-10-05）

- **用户确认链路全通**：DeepSeek 桌面对话 → TALK → Kimi → TALK → 原 DeepSeek 桌面对话。Kimi 正常领取、执行并交付，桌面原会话完成收取。
- **任务证据**：#151“桌面连通性只读探测：仅回复 DESKTOP_TALK_OK”，请求者 `agent:deepseek`、目标 `agent:kimi`，runner `succeeded`、workflow `completed`、结果消息 2648、收取时间 `2026-10-05T10:34:20.741165`（服务端记录）。主控只读核对任务元数据，正文/实际桌面操作结论来自用户反馈。
- **消息归属**：用户说明同 Hall 的 2649–2653 是此前 DeepSeek 桥接会话与 Kimi 互报在线，Kimi因没有决策人在场转为待命；这些不计入本次只读探测的结果，也不作为新立项授权。
- **等待超时观察**：用户调用 `talk_wait_tasks(300s)` 超过当前 `toolCallTimeoutMs: 65000` 后被客户端中断，反馈服务端等待仍继续，后续 `get_task`/`list_tasks` 一度排队超时；改用轻量状态查询后完成闭环。保留当前“人通知完成后取件”默认，显式需要等待时可先选低于客户端超时的单次有界等待（例如 30–45 秒），限定总预算；长等待的超时/取消/排队行为仍需单独核验，不能视为稳定性验收通过。
- **环境观察**：用户反馈 `pwsh` 两次以 `0xC0000142`（DLL 初始化失败）退出，未阻断最终业务闭环。仅记录现象，未查明原因，不归因于 TALK 代码或与等待超时建立已证实因果。
- **范围收尾**：桌面 MCP 接入切片人工验收通过，继续沿用现有执行服务和身份凭据；本次未调整超时配置、未开启自动轮询/无人值守或其它运行器改造。

---

## 6. 回滚

> 当前真实 profile 已写入（见第 5.3 节）。回滚只针对本次追加的 `mcp-talk` 块；只有确认期间没有其它改动时才还原本次唯一备份，否则仅移除该块，保留桌面或他人随后保存的设置。

1. 优先移除 `cordis.patch.yml` 末尾本次新增的 `- insert:`（`mcp-talk`）块；只有确认目标期间没有其它改动时，才从**本次唯一备份**还原（`Copy-Item -LiteralPath '<本次备份>' -Destination $patchFile`）。复制备份会还原目标内容，操作前必须核对后续设置，不能只依赖是否加 `-Force` 判断会不会覆盖。
2. 等 HMR 重载（约 2 秒写入稳定窗口）；不生效就重启桌面 App。
3. 工具随之消失，其余桌面设置不受影响。若桌面已因 patch 语法错误无法启动，恢复备份后重启；桌面自身的恢复路径也会把 profile patch 备份成 `cordis.patch.yml.bak-<时间戳>`。

---

## 7. 限制、缺口与未验证项

**仍未覆盖的范围**

- **工具动作覆盖**：用户已通过实际桌面对话验证核心 MCP 派发/交付/收取链路；九个工具的全部动作、插件清单逐项截图和 HMR 具体触发方式未分别验证。
- **桌面进程实际使用的 `DSH_HOME`**：`DSH-DESKTOP-MCP-2` 已对**当前运行中**的桌面进程逐进程确认（Host 进程命令行直接携带 `<home>\profiles\desktop`，主进程环境无 `DSH_HOME` 覆盖），并只读核对了本机默认 home 与 home 层文件。仍未覆盖的情况：桌面**重启**后若换了 `DSH_HOME`（例如从一个设置过该变量的 shell 启动），patch 文件就要放到那个 home 下；每次落地前应重新确认一次。
- **CLI 侧的 desktop profile 组合校验**：CLI 显式拒绝该 profile，所以"桌面组合树"无法用 `--dump-config` 旁证。
- **验收规模**：一次真实限定只读任务 #151 已由用户验收通过；跨重启会话恢复、多工作区、无人值守、多任务并发和长等待稳定性不在本次通过范围。

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
