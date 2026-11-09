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

**建议的 W-B2（实施片）**：
1. 先做一次性 CLI 登录验证（用户操作），确认外部拉起 CLI 可完成一次真实模型调用；
2. 适配器采用方案 A：角色宿主拉起 CLI（固定空闲端口 + 环境变量），就绪探测 `/api/v1/health`，ACP 客户端改为 `GET` SSE 取 `acp-connection-id`/`acp-session-token` → `POST` 回带 → `DELETE` 关闭；删除固定端口扫描与 `/connect`；
3. 强度探测复用 `session/new` 返回的模型/配置或 `session/set_config_option`；错误码沿用 `workbuddy_acp_runtime_unavailable`；
4. 真实 E2E：hy4/w-d 强度、消息、general 任务、结构化交付；独立复核（避开 WorkBuddy 线路）。
