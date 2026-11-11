# WorkBuddy 5.9.3 ACP 协议只读研究（2026-11-09）

状态：**只读研究 + W-B1 真实探针已完成**（2026-11-09 23:51–00:20，未改产品代码）。探针结论：HTTP 协议全部打通，但**外部拉起的 CLI 账号未登录**（`Authentication required`）；stdio `--acp` 在本机未跑通。详见第十节。

## 一、结论摘要

1. 5.9.3 的 ACP 不再由桌面主进程在固定端口提供“全局 connect”入口；桌面改为**每会话拉起一个 WorkBuddy CLI 子进程（`@genie/agent-cli` 2.165.0）**，由该 CLI 在 `127.0.0.1:<动态端口>` 提供 `--serve` HTTP 服务，ACP 走 **HTTP SSE**：`GET/POST/DELETE /api/v1/acp`。
2. 旧握手 `POST /api/v1/acp/connect` 已不是对外入口（桌面端口上 404）；连接标识改为 **`Acp-Connection-Id` 响应头**（对 `GET /api/v1/acp` 的 SSE 响应）→ 后续 `POST`/`DELETE` 必须回带同名请求头。
3. TALK 不必再扫描桌面端口。可行路径有两条：
   - **A（推荐先验证）**：TALK 自行以 `ELECTRON_RUN_AS_NODE=1` 启动 WorkBuddy 自带 CLI（`cli/dist/codebuddy-lite-wb.mjs --serve --port <空闲端口>`），复用 `~/.workbuddy` 登录态，再按新协议连 `http://127.0.0.1:<port>/api/v1/acp`；
   - **B**：以 `--acp`（stdio，ndJsonStream）启动同一 CLI，像 kimi/codex 桥一样走 stdin/stdout，彻底避开端口与连接 id。
4. 主要风险不在协议，而在**认证与运行环境**：CLI 由桌面注入 `ELECTRON_RUN_AS_NODE`、`WORKBUDDY_CONFIG_DIR`、`CODEBUDDY_FORCE_LITE_WB_BUNDLE` 等环境；桌面登录态是否可被外部拉起的 CLI 复用、模型调用是否需要额外 connector token，必须真实 E2E 验证。

## 二、版本与证据来源（均为只读）

- 桌面：`WorkBuddy.exe` FileVersion **5.9.3**；`resources/app.asar` 181,996,084 B。
- 内置 CLI：`resources/app.asar.unpacked/cli/package.json` → `@genie/agent-cli` **2.165.0**，入口 `cli/dist/codebuddy-lite-wb.mjs`（9.88 MB）。
- 本机配置目录：`C:\Users\<user>\.workbuddy`（`settings.json`、`workbuddy.db`、`cli-env/` 等，桌面已登录）。
- 抽取/检索产物：`.tmp/wb-asar/`（`main__server.js`、`main__sidecar-manager.js`、`main__account.js`、`main__cli-prewarm-pool.js`、`main__acp.js`、CLI ACP 相关片段）、`.tmp/wb-acp-index.json`（app.asar 内 ACP 路径清单）。
- 旧诊断（含 5.9.3 桌面端口实测 404）：`.tmp/workbuddy-acp-593-diagnosis.md`。

## 三、5.9.3 新协议事实（代码证据）

### 3.1 CLI 是 ACP 服务端

`cli/dist/codebuddy-lite-wb.mjs` 的 ACP HTTP 控制器：

| 路由 | 行为 |
|---|---|
| `GET /api/v1/acp` | 建立 ACP 连接：无 `acp-connection-id` 时由 `connectionGuard.issueToken()` 分配新连接；返回 SSE，响应头 **`Acp-Connection-Id`**；连接数超限 → 503 `Connection limit reached` |
| `POST /api/v1/acp` | JSON-RPC 请求；**必须**带 `acp-connection-id` 请求头，缺失 → 400 `Missing acp-connection-id header`；响应可 JSON 或 SSE |
| `DELETE /api/v1/acp` | 带 `acp-connection-id` 关闭连接（`revokeToken` + 关闭 transport） |
| `POST /api/v1/acp/connect` | 旧握手；仅特定上下文存在，桌面端口实测 404，不能再作为发现入口 |

其他事实：
- `isWebUiRequest` 需同时带两个 Web UI 头；普通本机非浏览器客户端按 `webUi=false` 处理。
- `--serve` 的 Web UI 密码（`--auth password|none`）只影响 Web UI/网关；本机 ACP 走连接 id + 连接数上限，不要求密码。
- ACP 会话方法沿用 ACP 标准：`initialize`、`session/new`、`session/load`、`session/prompt`、`session/set_mode`、`session/set_config_option` 等（`/main/acp.js` 与 CLI 内置方法表一致）。
- CLI 帮助明确：`--serve` 启 HTTP（Web UI、REST、ACP over HTTP SSE）；`--acp` 启 stdio ACP（`ndJsonStream`）；`--acp-transport` 仅配合 `--acp`（默认 `stdio`，可选 `streamable-http`）；`--port` 默认自动分配。

### 3.2 桌面如何拉起 CLI（TALK 可复用）

`main/sidecar-manager.js`：每会话以 `process.execPath`（WorkBuddy.exe）+ `ELECTRON_RUN_AS_NODE=1` 运行 CLI：

```
<WorkBuddy.exe> <cli/dist/codebuddy-lite-wb.mjs> --serve --no-session-persistence \
  --setting-sources user --settings '{"sandbox":{"allowUnsandboxedCommands":false}}' \
  [--mcp-config ... --strict-mcp-config]   # port: 0，由 IPC 上报 endpoint
```

`main/server.js::buildAgentCliRuntimeEnv` 注入的关键环境：

```
ELECTRON_RUN_AS_NODE=1
CODEBUDDY_CONFIG_DIR=<user>\.workbuddy
WORKBUDDY_CONFIG_DIR=<user>\.workbuddy
WORKBUDDY_DATA_FOLDER_NAME=.workbuddy
CODEBUDDY_FORCE_LITE_WB_BUNDLE=1
DISABLE_AUTOUPDATER=1
CODEBUDDY_GIT_REPO_SCAN_DISABLED=1
CODEBUDDY_PROMPT_SUGGESTION_DISABLED=1
```

- `main/sidecar-manager.js` 用 `GET /api/v1/health` 探测宿主运行时；`main/cli-prewarm-pool.js` 用 `getActiveEndpoints()` 收集已激活会话的 `http://127.0.0.1:<port>/api/v1/acp`（内部状态，不对外）。
- CLI 侧 `--port` 支持固定端口（桌面预热激活即 `--port <n>`），因此 TALK 可自行分配空闲端口，无需解析输出。

### 3.3 桌面 ACP 客户端的行为（与 TALK 需要做的一致）

`main/account.js`（桌面侧的通用 ACP 客户端）：
- 以 `Accept: text/event-stream` 打开 `GET /api/v1/acp`，读响应头 `Acp-Connection-Id` 并保存；
- 之后每个 JSON-RPC `POST` 都带 `Acp-Connection-Id`，并可按 `Last-Event-ID` 重连；
- 关闭时 `DELETE` 带同一头。

## 四、与旧 TALK 适配器的差异

| 项 | 旧 `bridges/workbuddy_acp.py`（5.8.x） | 5.9.3 现状 |
|---|---|---|
| 端点发现 | 扫描桌面固定端口 | 桌面端口无 ACP；需 TALK 自拉 CLI 或另寻会话端点 |
| 握手 | `POST /api/v1/acp/connect`，取 `connectionId`+`sessionToken` | 无 connect；`GET /api/v1/acp` SSE 的响应头 `Acp-Connection-Id` |
| 鉴权头 | `acp-connection-id` + `acp-session-token` | 仅 `Acp-Connection-Id`；另有连接数上限/Web UI 密码（不影响本机非浏览器） |
| 会话 | 桌面单例内多会话 | 每会话一个 CLI 进程（动态端口） |
| 启动依赖 | 桌面必须运行并登录 | 仍需登录态；但可由 TALK 直接启动 CLI（复用 `~/.workbuddy`） |

## 五、两条集成方案

### 方案 A：TALK 拉起 CLI + HTTP ACP（改动较小，贴合现状）

1. 在 `server/role_host_resolution`/`workbuddy_role_host` 中解析 CLI 路径（`%LOCALAPPDATA%\Programs\WorkBuddy\resources\app.asar.unpacked\cli\dist\codebuddy-lite-wb.mjs`），用 `WorkBuddy.exe` + `ELECTRON_RUN_AS_NODE=1` 启动，或用系统 `node`（本机已装，但分发版不应依赖）。
2. TALK 分配空闲端口（或 `--port 0` 后探测），启动参数参照桌面：`--serve --no-session-persistence --setting-sources user --settings '{"sandbox":{"allowUnsandboxedCommands":false}}'`。
3. 就绪探测：`GET /api/v1/health`（带 `X-CodeBuddy-Request: 1`）或 TCP 连通。
4. ACP 客户端改造：`GET /api/v1/acp` SSE 取 `Acp-Connection-Id` → `POST` 带该头 → `DELETE` 关闭；删除 `/connect` 与固定端口扫描。
5. 复用现有 `prompt_once`/`list_models` 的 JSON-RPC 调用层，只替换传输层。

优点：保留现有 SSE/JSON-RPC 代码与结构化输出逻辑；缺点：要处理端口、连接 id、进程生命周期与连接上限。

### 方案 B：CLI `--acp` stdio（传输最简单）

1. 用同样方式启动 CLI，但参数改为 `--acp`（默认 stdio ndJsonStream），不启 HTTP。
2. TALK 桥直接按 ACP JSON-RPC 行协议读写 stdin/stdout（与 kimi/codex 桥同构），无需端口/连接 id。
3. 需要确认 `--acp` 模式下的工具/沙箱/配置项与 `--serve` 等价，且支持现有 effort/config option。

优点：无端口与连接 id、生命周期清晰、最接近 TALK 既有桥模式；缺点：传输层重写，若 `--acp` 与 `--serve` 能力不等价则需回退。

**建议（按 W-B1 实测修订）**：**采用方案 A（HTTP SSE）**。探针已实际跑通启动、健康检查、SSE 连接、`initialize`、`session/new`（含模型与权限配置）与 `session/prompt` 调用路径；唯一阻塞是**账号登录态**（见第十节）。方案 B 的 `--acp` 在本机未产生任何 ACP 帧（进程退出 0 或无输出），暂不采用，留作后续可选。

## 六、适配器改造点（供后续实施切片）

- `bridges/workbuddy_acp.py`：删除固定端口扫描与 `/connect` 握手；新增 SSE 连接建立 + `Acp-Connection-Id` 管理；或新增 stdio 传输实现。
- `scripts/workbuddy_role_host.py` / `workbuddy_bridge.py`：决定 CLI 由谁拉起（建议宿主拉起，随角色生命周期），注入桌面同等环境（**不复制凭据**，仅指向共享 config dir）。
- `server/workbuddy_effort.py`：强度探测走同一连接（`session/set_config_option` 或模型能力查询），错误码沿用 `workbuddy_acp_runtime_unavailable`。
- `server/runner_versions.py`：ACP 基线从 5.8.3 更新为新协议基线（先探针后定）。
- 测试：fake ACP HTTP/SSE 服务（`Acp-Connection-Id` 缺失 400、连接上限 503、DELETE 关闭）+ fake stdio ndjson；真实 E2E：hy4/w-d 强度、消息、general 任务、结构化交付。

## 七、风险与未验证项

1. **登录态复用未验证**：外部拉起的 CLI 是否能直接用 `~/.workbuddy` 的账号登录完成模型调用；桌面在部分模式还会注入 `connectorTokenEnv`，纯配置目录是否足够必须实测。
2. **沙箱/工具差异**：桌面给 CLI 传 `--settings` 沙箱配置；TALK 侧若省略可能放宽或收紧工具权限，需与用户确认边界。
3. **版本耦合**：CLI 2.165.0 与桌面 5.9.3 绑定；未来升级需重新探测（`runner_versions` 已有版本面板可扩展）。
4. **连接上限与进程数**：`connectionGuard` 有最大连接数（16），TALK 每角色一进程时应无冲突，但需在 E2E 观察。
5. **本报告未做真实启动/调用**：所有结论来自静态 bundle 与既有 404 实测；协议细节（SSE 事件格式、session/new 参数）需在实施片用真实 CLI 校验。

## 八、建议的后续切片

1. **W-B1（只读探针）**：启动一次 CLI（固定空闲端口），`GET /api/v1/acp` 取连接 id、`initialize`、`session/new`，做一次最小 `session/prompt`（可要求单行 `OK`）；同时探 `--acp` stdio 是否等价。产出协议样本与失败点。
2. **W-B2（适配实现）**：按选定传输改造 `workbuddy_acp.py`/宿主，补 fake 服务测试；再真实 E2E hy4/w-d 强度、消息、任务与结构化交付；独立复核。

验收：真实模型单行回复 + 一次 general 任务落盘 + 强度选项非空 + 无桌面固定端口依赖；失败时错误码如实（不伪装 ready）。

## 九、证据索引

- `.tmp/wb-asar/main__sidecar-manager.js`：桌面拉起 CLI 的 argv/端口/环境（`--serve`、`ELECTRON_RUN_AS_NODE`）。
- `.tmp/wb-asar/main__server.js`：`resolveCLIPath`、`buildAgentCliRuntimeEnv`、`/api/v1/health` 探测。
- `.tmp/wb-asar/main__account.js`：`Acp-Connection-Id` 客户端行为（GET 取头、POST/DELETE 回带）。
- `cli/dist/codebuddy-lite-wb.mjs`：ACP HTTP 控制器（GET/POST/DELETE、400/503、连接 guard）。
- `cli/bin/startup-profile.cjs`：`--serve/--acp/--a2a/--prewarm` 模式。
- `.tmp/workbuddy-acp-593-diagnosis.md`：5.9.3 桌面端口 404 实测。

## 十、W-B1 探针实测（2026-11-09 23:51–00:20）

**启动方式（可复现）**：以 `WorkBuddy.exe` + `ELECTRON_RUN_AS_NODE=1` 运行 `cli/dist/codebuddy-lite-wb.mjs --serve --no-session-persistence --setting-sources user --settings '{"sandbox":{"allowUnsandboxedCommands":false}}' --port <空闲端口> --host 127.0.0.1`，环境设 `CODEBUDDY_CONFIG_DIR`/`WORKBUDDY_CONFIG_DIR=<用户>\.workbuddy`、`CODEBUDDY_FORCE_LITE_WB_BUNDLE=1` 等。约 10s 后 `GET /api/v1/health` 返回 200（pid/port 正常），说明 **CLI 可被 TALK 独立拉起，不依赖桌面进程存活**。

**HTTP 协议实测（全部成功）**：
- `GET /api/v1/acp`（`Accept: text/event-stream`）→ 200 SSE，响应头含 **`acp-connection-id`** 与 **`acp-session-token`**（新协议两者都要收）。
- `POST /api/v1/acp` `initialize` → 200，`protocolVersion=1`、`promptCapabilities(image/embeddedContext)`、`loadSession=true`、`multitaskSupport=true`、`authMethods=[iOA, external, internal, selfhosted]`。
- `POST` `session/new` → 200，返回 `sessionId`、可用模型列表（`auto/glm-5v-turbo/glm-5.1/glm-5.0-turbo/glm-5.0/glm-4.7/kimi-k2.5/minimax-m2.7/deepseek-v3-2-volc/custom-local:*`，含 credits/最大输入）、权限模式配置项（default/acceptEdits/plan/auto/dontAsk/bypassPermissions）。**消息与强度所需的模型/配置数据在这里可得**。
- `POST` `session/prompt`（“只回复 OK”）→ 200，返回 `stopReason=refusal`，`_meta["codebuddy.ai/errorMessage"] = {"message":"Authentication required. Please use /login command to sign in to your account","category":"auth"}`。

**结论**：传输层与 ACP 会话层已完全打通；**唯一阻塞是账号登录态**。外部拉起的 CLI 不会自动复用桌面的登录（仅指向 `~/.workbuddy` 不够，桌面是向子进程注入凭据）。解决办法需在实施前定：
1. **一次性 CLI 登录（建议先验证）**：在终端启动同一 CLI 执行 `/login` 完成账号登录，使其持久化到 CLI 自己的凭据存储；之后 TALK 拉起的 CLI 直接复用。属用户一次性授权动作，符合 Codex/Kimi 的既有模式。
2. 由桌面注入 token（`connectorTokenEnv`）：需要读取/转交账号秘密，**不符合当前秘密边界**，除非用户明确授权最小范围。
3. 仅驱动桌面自己的会话（内部 IPC）：不可稳定自动化，不采用。

**方案 B（stdio）实测**：`--acp` 进程可启动但退出码 0、无任何 JSON-RPC 帧；`--serve --acp --acp-transport stdio` 无 stdout 帧输出（阻塞）。**本机未跑通，暂不采用**；如后续确认正确调用方式可再评估。

**探针产物**：`.tmp/wb-probe/`（`probe.py`、`acp_probe_v2.py`、`stdio_probe.py`、`acp-result-v2.json`、`cli.*.log`、`stdio*.err.log`）。探针进程已清理，未改动 WorkBuddy/TALK 产品代码。

**建议的 W-B2（实施片，待 token 来源确定后）**：
1. 先解决模型网关 token 来源（见 10.1），确认外部拉起 CLI 可完成一次真实模型调用；
2. 适配器采用方案 A：角色宿主拉起 CLI（固定空闲端口 + 环境变量），就绪探测 `/api/v1/health`，ACP 客户端改为 `GET` SSE 取 `acp-connection-id`/`acp-session-token` → `POST` 回带 → `DELETE` 关闭；删除固定端口扫描与 `/connect`；
3. 强度探测复用 `session/new` 返回的模型/配置或 `session/set_config_option`；错误码沿用 `workbuddy_acp_runtime_unavailable`；
4. 真实 E2E：hy4/w-d 强度、消息、general 任务、结构化交付；独立复核（避开 WorkBuddy 线路）。

### 10.1 账号登录验证（2026-11-10 09:47–10:05）

- 以 `--auth none` 启动 CLI 后，`GET /api/v1/auth/account/status` 返回 `authenticated=true`、`userId=b52c1803-…`；`POST /api/v1/auth/account/login {"method":"internal"}` 返回官方 `authUrl`（`https://www.workbuddy.cn/login?platform=workbuddy&state=…&version=2.165.0`）。
- 用户打开该 URL 完成登录后：`account/status` 仍显示 authenticated；ACP `authenticate`（method=`internal`）返回 `userinfo.userName="火🔥🔥火"`；但 **`-p "只回复 OK"` 与新进程的 ACP `session/prompt` 仍返回 `Authentication required`**。
- 代码归因：模型网关鉴权走 `CustomTokenAuthenticationStorage`——只从 **`process.env.CODEBUDDY_AUTH_TOKEN`**（或 product config custom token / `CODEBUDDY_API_KEY`）读取；桌面在拉起每个 CLI 子进程时注入该 token（`buildSessionDeltaEnv`/`connectorTokenEnv`）。账号登录态（ACP userinfo）**不等于**模型网关 token，仅靠 `~/.workbuddy` 账号配置无法满足；`settings.json` 中也没有对应 env 字段。
- **结论**：TALK 独立拉起 CLI 的“进程 + HTTP + ACP + 账号登录接口”全部可用，但**没有受支持的模型 token 来源**。需要用户决策：
  1. 用户提供 `CODEBUDDY_AUTH_TOKEN` 或 `CODEBUDDY_API_KEY`（放仓库外 key 文件，TALK 仅以 env 注入子进程）——最快，但属用户显式授权的最小秘密范围；
  2. 授权 TALK 研究桌面注入机制（读取桌面进程环境/加密凭据）——涉及秘密边界且跨版本脆弱，不推荐；
  3. 暂停 WorkBuddy 无头适配（保留现有“运行器版本警告 + effort_error”提示）。
- 方案 B（stdio）即便可用也会遇到同一 token 问题，故仍不采用。

### 10.2 决策（2026-11-10）：暂停 WorkBuddy 无头适配

- 用户确认：**WorkBuddy 走订阅模式，本身不提供 API Key/接口 token**。因此“用户提供 `CODEBUDDY_AUTH_TOKEN`”方案不可行；读取桌面注入的凭据又超出秘密边界且跨版本脆弱。
- **结论：暂停本项无头适配**。保留现有用户可见提示（运行器版本面板的桌面版本警告、绑定 `effort_error=workbuddy_acp_runtime_unavailable`），WorkBuddy 角色继续不可用；不修改 TALK 产品代码。
- 重新启动条件：WorkBuddy 官方开放可用于本机的 ACP/API 凭据，或提供受支持的“外部会话/第三方客户端”接入方式；届时从本研究第十节继续（协议与探针脚本已就绪，`.tmp/wb-probe/`）。
- 已清理探针 CLI 进程；WorkBuddy 桌面未改动。

### 10.3 更正（2026-11-10 下午，Astra 反证后）

**10.1/10.2 的“5.9.3 改架构 / 缺 token 是唯一阻塞”结论撤回**，证据如下：
1. `.tmp/wb-builtin-research/authenticated-probe.json`（11-05 15:47）：`workbuddyVersion=5.9.3`、`embeddedCliVersion=2.165.0`、transport 为 “desktop-owned embedded CLI ACP over loopback; normal connect/initialize handshake”，模型 `deepseek-v4.1-flash` 返回 `OK`。**成功时已是 5.9.3**。
2. 三个 bundle 文件（CLI、sidecar-manager、server）与当时保存源码一致；“5.9.3 才切换架构”不成立。
3. 我此前的 404 探针用的是 **`GET /api/v1/acp`** 与桌面 Electron 端口；正确握手是 **`POST /api/v1/acp/connect`**（`X-CodeBuddy-Request: 1`）→ `{connectionId, sessionToken}` → `POST /api/v1/acp`。`connect()` 仍保留，非 ACP 模式/错误进程也会 404。
4. “模型认证只能靠 `CODEBUDDY_AUTH_TOKEN`”未获证明：独立 CLI 失败只说明**独立启动条件**不具备模型访问能力；桌面托管 CLI 才是 Nov 5 成功路径。

**当前状态（复验中）**：本机 WorkBuddy 桌面**没有活跃 hosted CLI runtime**（`daemon.log`：`no active hosted CLI runtime (generation=0)`），因此暂时没有 ACP 端点可连。已准备 `.tmp/wb-probe/watch_hosted.py`：用户打开任意 WorkBuddy 对话触发桌面拉起 CLI 后，脚本扫描端口、`POST /api/v1/acp/connect`，用**第二次 `session/new` 的空白会话**做最小模型调用（绝不 prompt 第一次返回的桌面活动会话），并记录模型/stopReason/文本。

**仍需验证**：空白会话是否真的无历史（Nov 5 探针 `prompt_tokens≈128k`，疑似接入了已有上下文）；context 隔离；桌面未开对话时 TALK 能否工作（大概率要求桌面有活跃会话）。

### 10.4 宿主 CLI 实测成功，但确认与桌面当前对话冲突（2026-11-10 14:32）

**成功证据**（`.tmp/wb-probe/hosted-acp-result.json`）：
- 桌面拉起 hosted CLI 后，扫描到端口 `53631`，`POST /api/v1/acp/connect` 成功；
- `initialize` 成功；两次 `session/new`：第一次返回桌面当前会话 `558538d7…`，第二次得到新会话 `01a1c428…`（UUIDv7）；
- `set_config_option(model=deepseek-v4.1-flash)` 成功；`session/prompt` → `OK`，`stopReason=end_turn`，14.6s，无错误。

**致命冲突**：
1. `_meta.codebuddy.ai/continue=false` 实测**仍返回桌面当前会话**（`558538d7…`），不能据此新建而不绑定。
2. 同一连接第二次 `session/new` 后，桌面日志出现 `Killing session 558538d7… cleaned up (0 remaining)`，随后该对话被重新拉起——说明**新会话替换/清理了桌面当前会话**。
3. 因此用宿主 CLI 跑 TALK 任务会干扰用户正在使用的 WorkBuddy 对话，且无法做到“每角色独立上下文”；`DELETE /api/v1/acp` 还会显式关闭绑定会话。
4. 现有适配器 `bridges/workbuddy_acp.py` 已实现“两次 session/new + 只用第二个”，协议本身并不缺；缺的是**不与桌面对话冲突的独立 CLI 实例**。

**结论（修订）**：WorkBuddy 内置模型**没有可用的隔离接入路径**：
- 独立 CLI：无模型访问能力（桌面凭据不注入）；
- 宿主 CLI：能调用模型，但绑定/替换桌面当前对话，不能多角色隔离；
- 官方 Open API（[open.workbuddy.cn/docs/openapi](https://open.workbuddy.cn/docs/openapi)）：
  - 本地助理 API：需注册第三方应用 + OAuth 用户授权，向 PC 助理发消息/查历史；**是否支持指定内置模型、是否按消息隔离上下文仍未验证**；
  - 云端任务 API + ACP：在云端沙箱执行，不能直接操作本机 `D:\` 工作区。

**建议**：暂停“TALK 角色直接跑 WorkBuddy 内置模型”的实现；如要继续，唯一值得评估的是**本地助理 Open API**（需你注册开发者应用并授权）。

**用户决定（2026-11-10 14:55）**：**暂停 WorkBuddy 适配**，保留现有版本警告/`effort_error` 提示；待厂商开放“外部客户端/独立实例”接入方式后再继续。协议事实、探测脚本（`.tmp/wb-probe/`）与本记录保留，届时可直接续做。

### 10.5 CDP 路线实测打通（2026-11-11 00:35，推翻“无隔离接入路径”）

**做法**：用 `WORKBUDDY_REMOTE_DEBUGGING_PORT=9222` 启动 WorkBuddy（启动前设置；`main/index.js` 在 app ready 前 `appendSwitch("remote-debugging-port", n)` + `remote-allow-origins` 仅 localhost）。CDP `/json` 得到页面 target（`file:///.../renderer/index.html`），WebSocket 连入后 `Runtime.evaluate`。

**实测结果**：
1. 页面全局存在 **`window.wb`**（不只是 `__wbInvoke`）；`wb.conversations.create/runPrompt/delete/list` 均可调用。
2. 创建：
```js
const conv = await wb.conversations.create({
  cwd: "D:\\work\\demo", title: "TALK 角色-xxx",
  transport: "local", mode: "craft", model: "deepseek-v4.1-flash"
});
// conv.info.id = 新会话 UUID；返回对象含 sendPrompt/runPrompt/configManager/ensureRuntime/on...
```
3. 发送与结果（**无需 ACP/CLI 端点**）：
```js
const r = await conv.runPrompt([{type:"text", text:"只回复 OK 两个字母"}], {emitUserMessage:true});
// r.content = [{type:"text", text:"OK"}], r.responseModel=deepseek-v4.1-flash, conv.info.state=idle
```
4. 清理：`await wb.conversations.delete(id)` 成功；`wb.conversations.list({transport:"local"})` 不再包含测试对话，**其他对话全部保留、未被替换**。
5. 测试对话在桌面 UI 可见（标题自动改为首条消息），符合“TALK 对话可见、不影响其他对话”的要求。

**能力面**：`conv.configManager` 有 `setModel/setMode/setPermissionMode/setThoughtLevel/setContextWindow/setSandboxMode`；`conv` 还有 `requests/artifacts/files/cancel/on` 等，可做模型/强度/权限设置、流式事件、上下文重置（新建 + 删除旧对话）。

**前提与风险**：
- **必须用调试模式启动 WorkBuddy**：TALK 运行在非交互会话时无法拉起 GUI（实测 0 进程），需用户双击 `start-workbuddy-debug.bat` 或带环境变量启动；测完应退出并用普通方式重启，关闭 9222。
- CDP 是**全控制调试口**，只能绑 loopback（`remote-allow-origins` 已限 localhost）；TALK 不得对外暴露该端口。
- `window.wb` 是**私有内部 API**，无版本承诺；WorkBuddy 升级可能改签名/字段。
- 权限/工具调用可能触发 permission 请求；需设置 `permissionMode`（如 bypassPermissions）并处理 `on` 事件，属 W-B2 实现细节。
- 不读取/复制账号凭据；只使用页面已有登录态。

**结论**：**“TALK 自动创建并驱动 WorkBuddy 专用对话”已实测可行**，且不依赖 ACP/CLI 端点或 Open API。下一步是 W-B2：把 CDP 客户端接入角色宿主/执行通道（创建/复用/设置模型强度/发任务/收结果/换新对话），并做真实任务 E2E；需用户每次以调试模式启动 WorkBuddy（或后续做受管启动器）。

### 10.6 W-B2 实现与部署（2026-11-11）

**实现（624 开发 / 625 返修 / 626 K2.8 独立复核 approved）**：
- `bridges/workbuddy_cdp.py`：CDP 客户端。`GET /json` 选 `renderer/index.html` 页面 target，校验只连
  loopback 且端口与端点一致；一次 `Runtime.evaluate` 内完成「create → setPermissionMode/setThoughtLevel
  → runPrompt → delete」，conversation 对象保留在页面全局（实测跨 evaluate 重新 `get` 的对话会卡在
  `working`；保留对象的三段 evaluate 可行）；页面 timer + finally 删除双保险；错误码
  `workbuddy_cdp_{unavailable,connect_failed,target_missing,create_failed,config_failed,prompt_failed,timeout,invalid_input}`。
- 成功判定：`state === "completed"` 且 `content` 为数组（真实桌面返回**没有** `stopReason`、没有 `usage`；
  624 首版按 ACP 形状判 `stopReason`，实机复验发现恒失败，625 修正）。
- `scripts/workbuddy_cdp_prompt.py`：与 ACP 适配器同形的一次性 stdin→stdout 适配器，支持
  `--delivery-contract/--expect-task-id`，同一对话内一次修复回合；退出码 2/3 与 ACP 一致。
- `bridges/workbuddy_bridge.py` 新增 `workbuddy-cdp:` 分支；强度与交付参数判断泛化到两种适配器；
  `scripts/workbuddy_role_host.py` 前缀白名单加入 `workbuddy-cdp:`；
  `scripts/workbuddy_acp_models.py` 增加 `--transport cdp`（显式模型清单登记，不探测桌面）。
- 旧 `workbuddy-acp:`/`custom-local:` 分支与错误码逐字未变；服务端/前端零改动。
- 测试：候选 70 项全过（62.4s），基线 `0d1b4f3` 60 项、唯一差异为基线缺少 `tests.test_workbuddy_cdp`
  的 loader error，`new_failures=0`。

**实机验证（2026-11-11 07:30–09:00，WorkBuddy 5.9.3 / Electron 37.10.3，调试端口 9222）**：
- 适配器直跑：chat 模式返回 `OK`（exit 0，约 25s）；task 模式 + 交付合同返回**有效** `talk-delivery-1` JSON（约 22s）；
  每次运行后 `wb.conversations.list` 数量回到基线（40），无残留对话，用户既有对话未被替换。
- 端到端：登记 `workbuddy-cdp:` 模型选择后，删除旧 ACP 角色并按同一名称新建 CDP 角色
  （`hy4` → `agent:prj-e8fe7066bbec.hy4-2bbb4889`，Hy4；`w-d 内置` → `agent:prj-e8fe7066bbec.w-d-a6718675`，
  DeepSeek-V4.1-Flash），start 后 `running/ready`；真实任务 627（191s）/628（60s）均 succeeded，
  交付包通过 `talk-delivery-1` 校验（`talk_get_delivery` 显示 complete 且任务号一致）。
- **迁移约束**：角色模型在创建时锁定（创建操作与绑定六维校验），不能原地把 ACP 绑定改成 CDP 别名，
  否则 start 报 `choice_unverified`；迁移必须删除旧角色并新建。

**已生效的运行时要求**：
- WorkBuddy 必须以 `WORKBUDDY_REMOTE_DEBUGGING_PORT=9222` 启动；启动前须清掉继承的
  `ELECTRON_RUN_AS_NODE=1`，否则 Electron 进程以 Node 模式立即退出（实测 exit 0、无日志、无 GUI）。
- 该环境变量只对本次进程有效；退出 WorkBuddy 后调试端口关闭。

**已知限制**：`window.wb` 为私有 API，桌面升级可能失效；逐角色思考强度来自登记时的模型清单
快照（`capabilities`），模型清单变化后需重跑登记；登记脚本要求桌面以调试端口运行（会真实枚举
`wb.models.list()`），桌面不可达时明确失败、不写半套。

### 10.7 WorkBuddy 版本升级适配检查清单（2026-11-11 用户确定）

**触发场景**：WorkBuddy 桌面升级、换账号套餐、或发现已登记的内置模型不可用/任务报
`workbuddy_cdp_create_failed`。TALK **不做自动刷新**，按本清单人工适配一遍。

1. **确认版本与 API 面**：`GET http://127.0.0.1:9222/json/version` 记录 WorkBuddy/Electron 版本；
   在页面检查 `window.wb.conversations.create/runPrompt/delete`、`wb.models.list()`、
   `conv.configManager.setThoughtLevel` 是否仍存在。
2. **以调试模式启动桌面**（完全退出后）：
   `$env:WORKBUDDY_REMOTE_DEBUGGING_PORT = "9222"; Start-Process "$env:LOCALAPPDATA\Programs\WorkBuddy\WorkBuddy.exe"`。
3. **适配器实机自检**：`scripts.workbuddy_cdp_prompt` chat 模式返回 `OK`（exit 0）；
   task 模式 + `--delivery-contract` 返回有效 `talk-delivery-1` JSON；运行后对话列表数量不变。
4. **刷新模型与强度**：
   `python -B -X utf8 -m scripts.workbuddy_acp_models register --api-base http://127.0.0.1:8000 --operator-key-file <真人 Key> --models <当前清单> --transport cdp`
   —— 会真实枚举并校验模型 id，更新已有 choice 的 `capabilities`（支持档位/默认档位）。
5. **核对页面与绑定**：角色页 `effort_options` 与模型下拉正确、绑定仍 `bound`；模型下线时任务会
   明确失败，需按“删除角色 → 重建”处理（角色模型不可原地更换）。
6. **回归**：跑 `tests.test_workbuddy_cdp`、`tests.test_workbuddy_cdp_gate`、
   `tests.test_workbuddy_effort` 与一次真实任务；记录版本、命令、证据路径与未验证项。
7. **边界**：不自动重启用户桌面、不读取/复制凭据、调试端口只留 loopback；升级后若 `window.wb`
   结构变化，先停用相关角色再适配。
