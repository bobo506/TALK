# Kimi Code + K2.8 Preview 独立执行入口

> 本指南属于切片 187/188/189（189 为定向补正片）的**局部文档**，只覆盖
> `agent:kimi-code-k28-preview` 这条执行入口的准备、检查、启动、停止与最小验收步骤。
> 现有 `agent:kimi` / K3 角色、全局 `default_model`、官方 CLI 登录态都不在本片范围内。

配套文件：

| 文件 | 作用 |
| --- | --- |
| `scripts/kimi_k28_executor.py` | 合同 / 离线检查 / argv 渲染 / 启动门禁与只读身份核验入口 |
| `deploy/kimi-code/k28-executor.contract.template.json` | 配置合同模板（占位符，不会被程序读取） |
| `deploy/kimi-code/k28-executor.launch.template.ps1` | 启动模板（本身不含密钥） |
| `bridges/kimi_bridge.py` | 既有 Kimi Code bridge，本入口**复用**它，未修改 |
| `tests/test_kimi_k28_executor.py` | 针对性离线测试 |

## 1. 这条入口是什么

`agent:kimi-code-k28-preview` 是一个**执行侧**成员：接 TALK 任务、用官方 Kimi Code CLI
执行、把结果回写 TALK。它不新建模型推理循环，只是把既有 `bridges/kimi_bridge.py`
按一条固定合同配置起来：

- `member_id = agent:kimi-code-k28-preview`、`business_role = dev`、`decision_tier = execution`；
- `runtime = kimi-code`，prompt 走 `argv`（TALK prompt 作为 `-p` 的最后一个参数）；
- **受控固定命令**：入口 argv 里显式写入 `kimi --output-format stream-json -p`
  （等于 bridge 的 `DEFAULT_KIMI_COMMAND`）。`command_override_allowed=false`：
  任何非该值的 `--kimi-command` 都被拒绝，`TALK_KIMI_COMMAND` 环境继承同样不生效。
  只有走这条受控分支，三档才会生成带 `--model` 与 `--agent-file` 的 Agent 文件；
- 任务执行档 `tools`（`Read/Grep/Glob/Bash` + `Edit/Write`）；
  **讨论与领取前预检仍然无工具**，三个运行档都 `subagents: []`；
- 模型 alias 显式锁定 `kimi-code/kimi-for-coding`，三档命令都带 `--model`；
- **固定执行分级**：argv 显式写入 `--decision-tier execution`（远端名册核验的就是
  `execution`）。既有 `cli_bridge.resolve_decision_tier` 会先看显式值，因此本地
  `.talk/groups.yaml` 里的 `decision` 或缺省都不能把实际运行改成 decision；
- **统一服务地址**：只读身份预检与实际 bridge argv 使用**同一个** `--base-url`，
  非默认端口（如 `19091`）不会出现“验 19091、跑 8000”；
- 项目绑定 `prj_e8fe7066bbec`，工作目录 `D:/claude-test/TALK`；
- 实例 id 由成员 id 派生（`agent:kimi-code-k28-preview:<uuid4>`），与 `agent:kimi` 无关；
- **不改**全局 `default_model`（当前仍为 `kimi-code/k3`），不登录/登出/更新官方 CLI，
  不复用 `agent:kimi` 的 TALK Key 或官方登录凭据。

## 2. 模型来源：四件事必须分开看

| 概念 | 本入口取值 | 说明 |
| --- | --- | --- |
| 运行器 | `bridges/kimi_bridge.py` | 复用既有 bridge，不是新运行器 |
| 模型来源 | `builtin` | 由官方 CLI 自己读取本机 native 配置与登录态 |
| provider / 连接引用 | `managed:kimi-code` / `native-kimi-code-managed-login` | 引用既有 managed 连接，不是新认证 |
| 配置别名（CLI `--model` 取值） | `kimi-code/kimi-for-coding` | 本机 `config.toml` 的 `models` 键 |
| 后端 model ID | `kimi-for-coding` | 别名背后真正传给服务的模型 ID |
| 显示名 | `K2.8 Preview` | 只是给人看的名字，**不得当 API 模型 ID 使用** |

只读核对到的本机事实（2026-10-08，来自 `C:/Users/Administrator/.kimi-code/config.toml`）：

```toml
default_model = "kimi-code/k3"

[providers."managed:kimi-code"]
type = "kimi"

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
display_name = "K2.8 Preview"
capabilities = [ "thinking", "always_thinking", "image_in", "video_in", "tool_use", "dynamically_loaded_tools" ]
```

`kimi-code/kimi-for-coding` 这个别名可以**原地升级**后端版本，所以本入口只承诺“锁定别名”，
不承诺永久锁 K2.8 Preview 这个后端版本。CLI 版本从 `~/.kimi-code/updates/rollout.log`
最后一条 `current` 读取为 `2.0.2`（只读解析，本片没有执行 `kimi --version`）。

## 3. 安全准备（三类凭据不要混）

1. **TALK Key（本入口真正需要的）**：新成员 `agent:kimi-code-k28-preview` 在 TALK 注册后
   取得的**本人** API Key。写到**仓库外**的文件，默认
   `~/.talk/agent-kimi-code-k28-preview.key`（只放一行可打印 ASCII），或用环境变量
   `TALK_K28_KEY`（优先于文件）。不要复用 `agent:kimi` 的 Key
   （`~/.talk/agent-kimi.key`）——脚本会直接拒绝。
2. **官方 native managed 登录凭据**：由官方 Kimi Code CLI 自行读取与维护，本入口
   **不读取、不复制、不导出、不修改**，也不做登录/登出/更新。别把 native 登录态当成
   TALK 身份，反过来也一样。
3. **native `config.toml`**：本入口只读解析，用于核对 alias / provider / model /
   `tool_use` 与项目绑定；检查前后 sha256 必须一致，`default_model` 不改。

密钥只在本入口进程内使用：`contract` / `check` / `render` 全程零密钥；
`launch` 从环境或仓库外文件读取后，只作为 Python 对象注入既有 bridge，
不进入命令行、日志、报告或仓库文件。失败信息是短中文提示，且经过脱敏：
HTTP 错误路径**只回 HTTP 状态与固定短说明，不读取、不回显服务端正文**
（文件来源的 Key 可以是任意可打印 ASCII，正文可能原样回显它）；同时报告路径会用
本次实际解析出的 Key 做**精确掩码**兜底，不依赖 `sk-`/`ghp_` 前缀或全局环境变量。

## 4. 离线检查（可反复跑，默认不联网）

```bash
python scripts/kimi_k28_executor.py contract
python scripts/kimi_k28_executor.py check
python scripts/kimi_k28_executor.py check --require-key
python scripts/kimi_k28_executor.py check --require-key --online-identity   # 额外做一次只读在线核验
python scripts/kimi_k28_executor.py check --require-key --base-url http://127.0.0.1:19091
python scripts/kimi_k28_executor.py render --base-url http://127.0.0.1:19091
```

`check` 逐项核对并在发现问题时以退出码 `1` 结束：

| 检查项 | 覆盖的失败边界 |
| --- | --- |
| `member_identity` | 成员 id 被改成别的成员 |
| `runner_binding` | `runtime` / `prompt_transport` 偏离合同 |
| `task_tool_profile` | 任务档被降到 `review` |
| `model_alias_lock` | `--kimi-model` 被换成别的 alias（如 `kimi-code/k3`） |
| `base_url_contract` | `base_url` 为空；非默认端口时 argv 与只读预检必须用同一个值 |
| `execution_budget` | 执行预算不是显式正整数 |
| `native_config_present` | `config.toml` 缺失或无法解析 |
| `native_model_alias` | native 配置里**没有**这个 alias |
| `native_model_binding` | alias 的 `provider` / `model` / `tool_use` 不符，或配置类型非法（短错误、不崩 traceback） |
| `default_model_untouched` | 检查前后配置文件 sha256 必须一致（只读，不改全局默认） |
| `controlled_command_contract` | 合同固定命令与 bridge 的 `DEFAULT_KIMI_COMMAND` 不一致（漂移时拒绝启动） |
| `command_override` | 任何自定义 `--kimi-command` 都被拒绝（`command_override_allowed=false`） |
| `decision_tier_binding` | 用既有 bridge parser + `resolve_decision_tier` 解析**同一份 argv**：必须得到 `execution`，本地 `groups.yaml` 的 decision 不算数 |
| `model_lock_and_tool_isolation` | 三档命令是否都锁模型、都带受控 `--agent-file`；讨论/预检是否仍无工具 |
| `project_binding` | `.talk/project.yaml` 的 `project_id` 不是本项目 |
| `key_env_contract` | `--key-env` 只接受合同变量 `TALK_K28_KEY`，其它名字直接报错（不静默忽略） |
| `talk_identity_key` | 凭据来源；仓库内密钥文件、复用 `agent:kimi` 的 Key 都会被拒 |
| `identity_binding` | 离线身份报告不一致；或（`--online-identity`）只读在线身份/名册不一致 |

`--identity-report <json>` 只是**离线 fixture**，命令与报告都不会把它标为在线已验证；
在线核验只有 `--online-identity` 或 `launch` 才会做。

常用边界复现（全部离线，用于评审时快速验证失败路径）：

```bash
python scripts/kimi_k28_executor.py check --kimi-config <不存在的路径>          # 配置缺失
python scripts/kimi_k28_executor.py check --kimi-command "kimi-wrapper"        # 自定义命令被拒
python scripts/kimi_k28_executor.py check --kimi-command "kimi --model kimi-code/k3 --output-format stream-json -p"  # 同 alias 也算覆盖，仍被拒
python scripts/kimi_k28_executor.py check --kimi-task-profile review           # 工具档不符
python scripts/kimi_k28_executor.py check --require-key                        # 凭据缺失
python scripts/kimi_k28_executor.py check --key-env TALK_OTHER                 # 非合同环境变量
python scripts/kimi_k28_executor.py check --require-key --online-identity      # 只读在线身份核验
```

未提供凭据且未加 `--online-identity` 时，`talk_identity_key` 记为 `not_run`（不是失败）；
加 `--require-key` 或 `--online-identity` 才要求必须可解析。

## 5. 启动门禁、只读身份核验与 dry-run 语义

`launch` 的顺序是固定的，任何一步失败都在**任何 bridge 注册、实例上报、模型调用之前**退出：

1. 解析本人 TALK Key（环境变量或仓库外文件；错误短中文、不打印正文）；
2. 走与 `check` **同一条**路径的启动前检查：受控固定命令合同、固定执行分级
   （argv 显式 `--decision-tier execution`，本地 `.talk/groups.yaml` 不得覆盖）、
   **本次实际使用的** `config.toml`（即 CLI 真正读取的那份，不接受“检查一个、启动另一个”）、
   alias/provider/model/tool_use、**与后续预检/argv 同一个** `--base-url`、项目
   `.talk/project.yaml` 绑定；
3. **只读**服务端身份核验（零写入、零模型）：
   - `GET /api/members/me`：Key 必须对应**已存在**的本人（`id == agent:kimi-code-k28-preview`）
     且 `kind == agent`；未注册 Key（HTTP 401）或他人 Key（id 不符）失败；
   - `GET /api/projects/prj_e8fe7066bbec/agents`：本人必须在项目名册中，且
     `business_role = dev`、`decision_tier = execution`；错误项目（404）、名册缺失、
     角色/分级不一致都失败；
   - 任一网络错误同样失败；HTTP 错误只回状态与固定短说明，服务端正文不进入报告或 stderr；
     本入口**不会**自动首次注册，既有 bridge 的 `client.register` 只做对已存在同 Key 本人的幂等更新。
4. 通过后才进入既有 `bridges/kimi_bridge.py`；进入前再用 bridge 自己的
   `resolve_decision_tier` 复核一次 argv 分级必须是 `execution`。

`launch --dry-run` 的语义是**只做第 1–2 步（离线）**并打印脱敏 argv：
它**不**做在线身份核验、**不**启动 bridge，输出里 `identity_verified=false`、
`online_identity_checked=false`，所以不能让 dry-run 通过冒充“身份已核”。

```powershell
# 1) 先离线检查（可加 --online-identity 验证在线身份，需可解析的 Key）
python scripts/kimi_k28_executor.py check --key-file "$env:USERPROFILE\.talk\agent-kimi-code-k28-preview.key" --require-key

# 2) 启动（配置门禁 + 只读在线身份核验 + 既有 bridge）
python scripts/kimi_k28_executor.py launch --key-file "$env:USERPROFILE\.talk\agent-kimi-code-k28-preview.key"

# 3) 只看脱敏 argv、不联网、不启动
python scripts/kimi_k28_executor.py launch --dry-run --key-file "<KEY_FILE>"
```

也可以直接用 `deploy/kimi-code/k28-executor.launch.template.ps1`（模板本身不含密钥）。

- **停止**：在启动该入口的终端 `Ctrl+C`；bridge 退出前会把实例状态上报为 `offline`。
- **回退**：直接不启动本入口即可，它不影响 `agent:kimi` / K3 与其它成员；
  本片没有修改任何全局配置，因此不存在需要还原的 native 配置改动。
- 本入口**不**自行注册成员、不创建任务、不改任务状态；注册由决策角色复核后处理。

## 6. 正式注册与项目名册接入

入口脚本不自动首次注册成员，也不写项目名册。正式接入需要：

1. 由决策角色在 TALK 注册/登记成员 `agent:kimi-code-k28-preview`
   （`kind=agent`、`display_name="Kimi Code · K2.8 Preview 执行"`），把独立随机 API Key 保存于仓库外；不在聊天、日志或命令参数中交付明文；
2. 把该成员加入项目 `prj_e8fe7066bbec` 的 agent 名册，`business_role=dev`、
   `decision_tier=execution`。本地 `.talk/groups.yaml` 与独立 profile 只是同步来源；
   `POST /api/projects/{project_id}/sync` 必须由人类身份执行，且会整体替换名册，
   因此载荷必须保留所有现有角色及其字段，写前重新核对基线；Agent Key 会被 HTTP 403 拒绝；
   `launch` 会用只读名册核验这一步，缺失或不一致直接拒绝启动；
3. 可选：为它准备独立身份档 `.talk/agents/agent_kimi-code-k28-preview/{IDENTITY,SOUL,USER}.md`；
   没有档时 bridge 只是不注入该成员的 profile，不影响模型锁与工具档；
4. 用 `check --require-key --online-identity` 确认 `member_id` / `project_id` / 名册角色就是本人；
5. 权限不足或名册字段不支持时应在角色页/项目 API 侧配置，本入口不实现平台侧改造。

## 7. 最小接单验收（注册后，由决策角色安排）

1. `check --require-key --online-identity` 通过（`ok=true`、`problems=[]`、
   `identity_verified=true`）；
2. 启动入口，`launch` 的只读身份核验通过后才进入 bridge；实例状态从 `idle` 开始上报，
   成员出现在项目名册中；
3. 派一个**最小**任务（读一个文件并回报一行结论），确认：
   `claim → 执行 → 结果消息 → complete`，且结果回到同一个 Task Hall；
4. 确认 `agent:kimi` 仍按 native 默认模型（`kimi-code/k3`）工作，两者互不影响；
5. 记录真实耗时、真实模型版本与额度表现（本片未测，不得用推断代替）。

## 8. 预算与等待（本片口径）

| 项 | 记录 |
| --- | --- |
| 客户端单次工具上限 `T` | **未核验**。`deploy/kimi-code/mcp.talk.template.json` 里的 `toolTimeoutMs: 660000` 只是模板事实，不是本机运行中上限 |
| 显式等待 `W` | 未启用。未核验 `T` 时不启用主动长等待，不把 600 秒通用默认当成宿主能力 |
| 返回余量 | 无（`W` 未启用） |
| bridge 执行预算 | 本入口显式 `--timeout 3600`（整轮执行预算，与发起者等待预算分开；到期只结束当前 CLI 调用，不等于取消任务） |
| 只读身份核验预算 | 每次 `launch` 最多两次 GET；单次请求超时 `HTTP_TIMEOUT_SECONDS = 15s`，不复用 bridge 的 3600 秒整轮预算 |
| 发起侧主动等待 | 不在本片范围，另片处理 |

## 9. 已验证 / 未验证边界

已验证（离线、零模型、零 TALK 写操作）：

- 合同字段分离（运行器 / `model_source=builtin` / provider 与连接引用 / 配置别名 /
  backend model ID / 显示名）；
- 受控固定命令：argv 显式携带合同命令；`TALK_KIMI_COMMAND` 继承为 K3 命令时，
  三档仍锁定 `kimi-code/kimi-for-coding` 且都带受控 `--agent-file`；
  任意自定义 `--kimi-command`（即使带同一 alias）被拒绝；
- native `config.toml` 只读解析：alias 存在、`provider=managed:kimi-code`、
  `model=kimi-for-coding`、`tool_use` 声明、`default_model` 检查前后未变；
  类型非法时给短错误、不崩 traceback；
- 工具档隔离：任务档含 `Edit/Write`，讨论/预检 `tools: []`，三档 `subagents: []`；
- 服务地址贯通：非默认端口（`19091`）的 `launch` 中，只读预检请求目标、
  fake bridge 收到的 `args.base_url`、`build_bridge_argv` 的 `--base-url` 三者一致；
  `render --base-url` 同样透传；
- 固定执行分级：本地 `.talk/groups.yaml` 写 `decision` 或缺省时，用既有 bridge parser +
  `resolve_decision_tier` 解析本入口 argv 仍得 `execution`；`launch` 注入的
  `args.decision_tier` 为 `execution`；
- 错误正文脱敏：HTTPError 正文原样回显非 `sk-` 前缀的文件 Key 时，`_http_get_json` 抛出的
  短错误、`identity_preflight` 的 report、`main` 的 stdout/stderr 都不含 Key 与正文，
  且该文件 Key 确实作为 `X-API-Key` 用于本次 loopback 请求；
- 启动门禁：错误 `project.yaml`、alias 缺失、身份核验失败都在 bridge 之前退出
  （测试断言 `run_bridge` 未被调用），失败文本不含 Key；
- 只读身份核验（mock HTTP + loopback HTTP）：本人+名册一致通过；
  他人 Key、`kind != agent`、未注册 401、名册缺失、角色/分级不符、网络失败都被拒绝；
  请求路径与 `X-API-Key` 头经 loopback 实证；
- `agent:kimi` 角色仍不带 `--model`（native 默认 K3 不受影响）；
- 生成命令的真实 argv 运输（假 CLI 子进程）：最后一个 argv 是完整多行中文 prompt，
  `-p` 在其前，最终 stream-json Assistant 被解析为可见回复；
- 失败脱敏：CLI 非 0 退出只回简短提示，不回显 stdout/stderr；
- 凭据安全：环境变量优先、仓库内密钥被拒、`agent:kimi` 的 Key 被拒、
  `render`/`contract` 输出不含密钥正文；`--key-env` 非合同变量直接报错。

未验证（不得当成已适配）：

- 真实 Kimi Code / K2.8 模型推理、真实返回与耗时（本片按规定不发真实模型请求）；
- 真实 TALK 服务上的在线身份核验与名册一致性（只有 mock/loopback，未连真实服务）；
- 真实取消、真实排队、正常到期待返与后续查询，以及宿主 MCP 工具目录重载；
- 新成员正式注册、项目名册接入、真实领取与交付闭环；
- 宿主 `T`（含 660000ms 模板值）的真实加载情况；
- 官方 CLI 版本命令本身（本片只用 `rollout.log` 只读解析，没有执行 `kimi --version`）。

## 10. 范围边界

- 本入口只改 `scripts/`、`deploy/kimi-code/`、本指南与新增测试；
  `bridges/kimi_bridge.py` 经评估**无需修改**（既有能力已覆盖），因此未改动。
- 不修改 `server/`、API、schema、数据库、全角色页面、`bridges/cli_bridge.py`
  与 `bridges/talk_task_tools.py` 通用合同。
- 不修改 `AGENTS.md`、`docs/PROJECT_BRIEF.md`、`docs/PROGRESS*.md`，
  不触碰冻结中的 185/186 对象与草稿。
- 本入口不做首次注册写入；启动前的身份核验全部是只读 GET。
