# 本地信任模式：免登录、无人类账号

状态：L1 候选已实现，等待独立复核；L2 工作区自动创建仍是规划，未实现。各切片须单独授权。

## 一、目标与边界

**目标**
1. 打开 TALK 页面**不需要登录**；不存在人类账号/密码/API Key 的登录概念。
2. 页面操作者默认拥有当前 `human` 的全部能力（建项目、开角色、启停、恢复、删除、配置等）。
3. AI 角色保持独立身份与密钥，**只能看自己的任务/结果**（现状已如此）；不得借页面信任获得其他角色的可见性。
4. 首次在某个目录启用 TALK MCP 时，自动完成“注册项目 + 运行时绑定 + `.talk` 标记”，不建角色、不启角色。

**非目标**
- 不做公网可用的多用户账号体系；不引入密码/验证码/注册流程。
- 不改变任务/角色/会话的项目隔离语义。
- 不自动创建或启动角色（角色仍由页面手动创建）。

## 二、主体模型

本地信任模式下有两类主体：

| 主体 | 来源 | 权限 |
|---|---|---|
| **操作者（operator）** | 页面/本机/受信局域网请求，无 Key | 原 `human` 的全部权限（含 human-only 接口） |
| **AI 角色（agent）** | `X-API-Key` 解析出的现有成员 | 原有受限权限：只看自己的任务/结果，不能改 desired_state |

实现建议：保留一个**内置操作主体**（内部 `members` 行，`kind="human"`，如 `human:operator` / 显示“本机操作员”，随机不可猜 `api_key` 且从不发放），仅用于：
- `created_by` / `maintainer_member_id` / `from_id` 等现有外键；
- 审计归属；
- 让既有 `_require_human` 检查零改动通过。

它**不是账号**：页面不展示、不可登录、不出现在成员/角色选择列表、不参与 @ 提及；现有 `human:bobo` 等历史人类行保留，密钥模式下原有登录能力保持。

## 三、鉴权矩阵

配置新增：
```toml
[server]
auth_mode = "trusted"        # trusted | key
trusted_networks = ["loopback", "private"]   # 默认；public 始终拒绝
```

| 请求 | 无 Key | 合法 agent Key | 非法/未知 Key |
|---|---|---|---|
| loopback | operator | 该 agent | 401 |
| 私网（10/8、172.16/12、192.168/16、fc00::/7） | operator | 该 agent | 401 |
| 公网 IP | 401 / WS 4001 | 401 / WS 4001 | 401 / WS 4001 |

- trusted 模式先检查直连来源，公网或未知来源对全部需鉴权的 REST/SSE/WS 一律拒绝，即使携带有效 Key；不信任 `X-Forwarded-For`。`GET /api/auth/mode` 和 `GET /api/setup/status` 公开返回非敏感元数据。
- `private` 使用 Python `ipaddress.is_private` 语义，也包含链路本地地址（IPv4 `169.254/16`、IPv6 `fe80::/10`）。不希望信任链路本地时，使用 `auth_mode = "key"`，或在网络层限制为明确允许的网段；当前 `trusted_networks` 不支持显式 CIDR。
- 同源反向代理会使后端看到代理的受信地址，从而绕过来源闸门；公网暴露必须使用 key 模式或网络层限制。
- 升级后采用默认 `auth_mode = "trusted"` 是鉴权行为变更；需要保留密钥登录的部署须明确设置 `auth_mode = "key"`。
- `auth_mode="key"` 时完全退回现行为（保留登录），供未来公网/共享部署使用。
- 无 Key 但带 `Authorization: Bearer` 等其它凭据不改变判断（仍按来源）。
- 审计：operator 的写操作记录 remote IP、路径与操作类型；不记录请求体中的秘密（现有规则）。

## 四、页面与实时通道

- 页面启动先调 `GET /api/auth/mode`：`trusted` → 直接进入主界面（隐藏登录层、移除 Key 输入/登出）；`key` → 保留现有登录。
- `apiFetch` 在 trusted 模式不发送 `X-API-Key`；收到 401 时显示“本地信任未启用/网络不在受信范围”，不弹登录。
- SSE（`/api/events?token=`）与 WebSocket（`?token=`）在 trusted 模式下允许**无 token** 连接并映射 operator；agent 仍用 token。
- 非 loopback 访问时，页面顶部显示“局域网可信模式：同网设备可控制”提示。
- 上传/下载/文件预览与 REST 使用同一主体判定。

## 五、权限语义改名

- 现有 `_require_human` / `human-only` 的**判定不变**（operator 是 `kind="human"` 的内置行），但文案与文档统一改为“仅操作者（人类界面）/ agent 不可调用”。
- Agent 越权仍返回 403，错误码不变。
- `GET /api/members` 等列表过滤内置 operator；角色/绑定/任务创建目标的候选中不出现它。

## 六、数据与兼容

- 新增内置 operator 行（启动时 ensure，幂等）；`api_key` 随机 48 字节，不展示、不发放、不写日志。
- 新项目 `maintainer_member_id` 默认 operator；已有项目/任务/消息归属不改。
- 页面创建的任务 `created_by=operator`；页面消息 `from=operator`；页面显示“本机操作员”或按现有“人类”样式。
- 现有 `human:bobo` 等行保留；其历史任务/消息正常展示。
- 迁移只加配置与一行内置成员；不回填、不重写历史。

## 七、工作区自动创建（第二阶段）

任务 617 的候选实现待独立复核，尚未完成无 Key 的终端任务工具链：现有终端任务和发送工具仍要求 `TALK_API_KEY`。首次注册接口与启动器接入的隔离验证不代表完整 MCP 场景可用；后续需经授权修改相应工具并验证。

**触发**：`TALK_WORKSPACE_AUTO_ENSURE=1` 且项目目录（cwd/`--project-root`）存在、未提供 `project_id` 时尝试自动创建。普通终端入口默认关闭；DSH 与 Kimi 启动器默认启用，可用环境变量 `0` 禁用。明确提供项目 ID 时仍要求 `TALK_API_KEY`；首次自动创建可以不带 Key，但这不代表后续任务工具已支持无 Key。

**接口草案**：`POST /api/local/workspaces/ensure`（trusted 模式、无 Key 即 operator；`auth_mode=key` 时要求 human Key）
```json
{"project_root": "D:\\work\\demo", "display_name": "demo", "operation_key": "optional-idempotency"}
```
服务端幂等执行（按规范化绝对路径去重）：
1. 注册项目（`maintainer=operator`，`project_root_path` 规范化）；
2. 启用该项目 provision host（host_label=本机名）；
3. 生成 `~/.talk/runtimes/<project_id>/runtime.json`（project_root/state_dir/key_root/base_url/operator_key_file 指向本机既有路径）；
4. 写 `<root>/.talk/project.yaml`（project_id/server）与 `<root>/.talk/runtime.local.json`（database_file/config_file）；
5. 确保该项目 runtime 运行（`--apply --attach-api`，不创建/启动任何角色）；
6. 返回 `{project_id, display_name, runtime_state, needs_role: true}`。

**启动器**：拿到 project_id 后设置 `TALK_PROJECT_ID`；若 `needs_role=true`，任务工具返回明确提示“工作区已创建，请在 TALK 页面创建角色后使用”，不伪造成功。
**不建角色、不启角色、不写仓库内其它文件**（除 `.talk/` 两个标记）。
**并发/幂等**：同一路径并发 ensure 只产生一个项目；重复调用返回既有项目。

**终端 Agent 加入项目（L3 候选）**：`POST /api/local/workspaces/join` 接收 `project_id`，沿用当前请求鉴权，仅允许 Agent Key；human、无 Key 的本地 operator 返回 `403 join_requires_agent`，项目不存在返回 `404 project_not_found`。接口幂等创建当前 Agent 的 `ProjectAgent` 名册行，保留已有行，并不创建角色或角色 Key，也不修改项目及 runtime。启动器拿到 project_id 后，如有 Key 则调用 join（包括已有项目）；失败会中止启动并显示 HTTP 状态，无 Key 首次 ensure 时跳过。ensure 仍要求 human/operator，因此 Agent Key 不能用于首次 ensure，需先完成工作区注册。

## 八、安全边界与风险（需确认）

1. **局域网可信**：任何能访问 TALK 端口的设备都可作为 operator 控制一切。必须：
   - 公网 IP 一律拒绝；
   - 页面显示“局域网可信模式”提示；
   - 建议后续提供可选的 IP 白名单（本片不做）；
   - 端口只监听配置的 host（默认 127.0.0.1；开放局域网需显式改配置并知情）。
2. **本机任意进程**同理可操作；这是免登录的固有代价。
3. Agent Key 仍是唯一 agent 身份；不得在页面/日志泄露。
4. 现有 `human:bobo` 的 key 仍可登录（若 `auth_mode=key`）；trusted 模式下忽略登录但 key 仍可解析为 agent?（`human` key 解析为 human → 仍具人类权限；属于历史兼容，不额外扩权）。

## 九、测试与验收

- 鉴权矩阵单测：loopback/私网/公网 × 无 Key/合法 agent Key/非法 Key，断言主体与状态码。
- 人类专属接口：trusted 无 Key 可调用；agent Key 仍 403；`auth_mode=key` 时缺少 Key 头通常为 422，日志端点保持 401。
- 页面：无登录直接进入；登出/Key 输入隐藏；401 提示；SSE/WS 无 token 可连。
- Agent 隔离回归：`GET /api/tasks` 仍只返回自己的；跨项目/跨角色不可见。
- Workspace ensure：幂等、路径规范化、写文件位置、runtime 配置、不建角色、不启角色；并发重复。
- 真实 E2E：新目录首次 MCP → ensure → 页面出现项目 → 手动建角色 → 启动 → 派任务。
- 安全反例：公网来源被拒；非受信网络无 Key 被拒；agent 不能调用 operator 接口。

## 十、切片与工作量

| 切片 | 内容 | 规模 |
|---|---|---|
| **L1** | 鉴权主体与矩阵（operator 内置行、`auth_mode`、SSE/WS）、页面免登录、权限文案/列表过滤、测试与文档 | M |
| **L2** | `POST /api/local/workspaces/ensure` + runtime 配置生成/写 `.talk` + MCP 启动器接入 + 测试 | M |
| **L3** | 文档/用户手册更新、旧登录入口降级说明、真实 E2E 与验收 | S |

依赖：L2 依赖 L1；L3 随两片收尾。建议 L1 独立复核上线后再做 L2。

## 十一、已确认（2026-11-10）与剩余细节

**已确认**
1. **内置隐藏操作主体可接受**：保留 `human:operator` 内部行（“本机操作员”：不展示、不可登录、不发放 Key、仅用于外键与审计）；页面无人类账号概念。
2. **公网来源一律拒绝**：只有 loopback 与私网段可映射 operator；公网 IP 直接 401/403，不提供放行开关。
3. 局域网可信：同网设备可操作，页面显示“局域网可信模式”提示（后续可选 IP 白名单，不在本片）。
4. `auth_mode` 默认：当前实例 `trusted`；安装包默认 `trusted`，保留 `key` 模式供未来公网/共享部署。
5. 工作区自动创建（L2）：只建项目 + runtime 绑定 + `.talk` 标记，不建角色、不启角色。

**实施时仍需敲定的小项**
1. 内置 operator 的展示名与 ID 最终取值（`human:operator` / “本机操作员”）。
2. 页面顶部提示的文案与出现条件（仅非 loopback 来源显示，还是常驻）。
3. L2 `needs_role` 的提示文案与页面引导位置。
4. 登录模式（`auth_mode=key`）保留哪些入口：仅隐藏，还是提供管理员开关页。

> 排期说明：本规划先不实施；用户决定**优先做 WorkBuddy 内置模型适配**，L1/L2 在本轮之后排。
