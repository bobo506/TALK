# B1a 运行器登记与角色绑定 API 验收

2026-10-09：DeepSeek #193 开发、#194 修正；Codex 独立六模块 124 项测试及原失败边界探针通过，193/194 已收取。登记/绑定为配置事实，不能据此认定运行器在线、模型已调用或实际模型匹配。B1b任务快照已通过独立代码复核并收取，另见[快照API验收](TASK_BINDING_SNAPSHOT_ACCEPTANCE.md)；MCP/页面展示和B2实际证据尚未实现。

## 启动与身份

2026-10-09用户重启后，Codex按明确授权确认实际服务表/任务字段已加载，快照核心代验收通过；本指南的human登记/绑定写入与变更步骤尚未在实际项目执行。后续使用项目既有启动方式，在项目根目录执行：

```powershell
cd D:\claude-test\TALK
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

启动时按原初始化流程幂等创建 `runner_registry`、`project_role_bindings` 两表及索引。仅新增表，不修改任务表/历史任务；隔离测试已验证旧库保留和重复初始化。

打开 [API 文档](http://127.0.0.1:8000/docs)，展开接口并点 Try it out，在 `x-api-key` 输入框使用现有 human 账号的 TALK API Key。无需创建新账号；未持有本人 Key 时按既有流程向项目管理者获取。先用 `GET /api/members/me` 核实 `kind=human`。Key 只用于请求鉴权，不能写入登记内容、绑定字段或任务消息。

选一个测试项目和已注册、已入册的 agent 角色，记录实际 `project_id`、`member_id`；使用未配置绑定的测试角色。下面的运行器和模型标识均为合成验收数据，不代表真实接入或真实模型。

## 核心步骤

1. `GET /api/runners` 应返回 200；`POST /api/runners` 写入下方登记应返回 201，再读可找到该行。重复同一 `runner_id` 返回 409。
2. `GET /api/projects/{project_id}/agents/{member_id}/binding` 在角色有效且无绑定时应为 `binding:null`、`binding_state:unconfigured`。
3. `PUT` 同一 binding 路径写入下方绑定应返回 200/`bound`，并带登记派生的 `runtime=dsh` 和非空 `binding_fingerprint`。`GET /api/projects/{project_id}/agents` 的对应角色与单角色结果一致。
4. `PATCH /api/runners/runner:b1a-acceptance-20261009` 写 `{"display_name":"验收登记改名"}`，绑定显示名随读取变化，指纹不变。写 `{"adapter_status":"retired"}` 后，原绑定读取为 `runner_retired`；再次写入该运行器的非空绑定返回 422。
5. `PUT` binding 路径写 `{"binding":null}` 清空，重复执行仍 200/`unconfigured`。登记首期没有 DELETE，验收登记保留为 retired。
6. 校验边界：不存在项目的单角色读取返回 404；未知写入字段、必填标识为空或含嵌入换行返回 422。用现有 agent 身份读登记/绑定可成功，写登记或绑定返回 403。测试标识没有连接文件或调用模型的副作用。

登记请求：

```json
{
  "runner_id": "runner:b1a-acceptance-20261009",
  "runtime": "dsh",
  "display_name": "B1a 验收登记",
  "adapter_status": "unverified",
  "capabilities": []
}
```

绑定请求：

```json
{
  "binding": {
    "runner_id": "runner:b1a-acceptance-20261009",
    "model_source": "builtin",
    "provider_id": "managed:deepseek",
    "connection_ref": "acceptance-local-ref",
    "model_id": "model:acceptance",
    "model_display_name": "合成验收模型"
  }
}
```

`bound` 表示当前身份/名册、存储字段与登记关系有效；即使登记为 unverified，也不能把它解释为实际适配已验证。`connection_ref` 仅为外置连接的标识，不是文件路径、URL 或凭据正文，服务不会解析或执行它。

## 已验证与限制

- 独立测试覆盖两表/幂等迁移、鉴权和字段校验、并发 upsert、离册保留/重入册恢复、项目删除清理、单 SQL 的 27 列事实、有效性阶梯与单角色/批量一致性。124 项全部通过，0 失败/错误/跳过；正常日志下既有文件测试 9 项通过。
- #193 的三处漏测边界已修正并独立复验：事实读取前项目删除时返回 404；登记 runtime 不可解析时 runtime/display/status 三派生字段及指纹全 null；存储必填标识末尾控制字符判 partial、指纹 null。
- 未重跑全量 881 项或 24 个 WinError5 的 pristine 对照。原 #193 的 26 个非零结果保留，不能据相关测试通过宣称全量通过或均非回归。
- 空名册不执行批量绑定事实 SQL，沿用既有读取边界；已有事务沿用自身数据库视图。读取不承诺跨接口时刻的全局最新状态。
- 实际服务加载和B1b快照核心路径已由Codex代验收，K28 #199最小回传通过并收取；此项不替代本指南human登记/绑定写入与变更步骤。没有修改实际项目绑定或操作浏览器；实际后端模型版本、页面和专门MCP消费未验。

本机复核证据索引：`.tmp/runner-role-binding-b1a-fix-review/`，包括冻结源码、124 项日志、独立边界探针、范围核验和收取回执；本机忽略产物不随 Git 发行。原 #193/#194 报告保持，194 混排消息的完整嵌入 JSON 已与本地合法交付逐对象核对；MCP 结构化摘要仍为 unknown，不把格式回退冒充结构化通过。
