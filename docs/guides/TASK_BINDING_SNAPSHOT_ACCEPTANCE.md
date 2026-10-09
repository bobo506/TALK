# B1b 新任务绑定快照 API 验收

2026-10-09：DeepSeek #196开发，Codex独立177项及并发/回滚/快照原文探针通过，任务已收取。新任务冻结创建时的目标角色配置，旧任务不回填；实际模型对照、MCP/页面展示后置。

## 启动与入口

重启当前部署的后端加载新代码。本轮没有替用户重载生产服务或执行生产库迁移。普通本机入口：

```powershell
cd D:\claude-test\TALK
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

初始化幂等新增agent_tasks的target_binding_snapshot/target_binding_state及状态索引，旧行NULL不回填。打开[API文档](http://127.0.0.1:8000/docs)，在x-api-key输入框使用本人已有human TALK Key，先GET /api/members/me核实身份；Key不放任务或绑定正文。

选择测试项目和已注册agent角色。目标如有运行bridge，创建任务会真实接单；可选未运行bridge的测试角色只查API落库。下面的ID需替换为实际值。

## 核心步骤

1. GET /api/tasks/195这类升级前任务，新两列应均null，表示未记录，不回填或猜模型。
2. POST /api/tasks创建：

```json
{
  "project_id": "替换为实际测试项目ID",
  "target_member_id": "替换为实际测试agent成员ID",
  "content": "B1b API验收：只回复收到，不使用工具、不读写文件，完成后暂停。"
}
```

应201，两列均非null。快照schema_version=role-binding-snapshot-1，固定13键：schema_version、snapshot_at、state、runner_id、runtime、model_source、provider_id、connection_ref、model_id、model_alias、model_display_name、binding_fingerprint、note。state与列target_binding_state一致，snapshot_at为UTC。

角色未配置绑定时unconfigured/配置null，有效绑定时bound/保留当时值；配置有效不能认定实际模型已匹配。

3. 保存任务ID与快照；按[B1a绑定验收](ROLE_MODEL_BINDING_ACCEPTANCE.md)重新提交合法完整绑定体修改测试角色或alias，再建一个新任务。旧任务GET快照不变，新任务取新值；仅改alias时指纹相同，但新旧快照保留各自alias。
4. 创建时省略project_id，应no_project/配置字段全null，快照对象仍非null。不存在项目的创建保持400。
5. 正常领取/完成或取消后再GET，快照不变；客户端额外填写快照不能落库，服务端自行解析。写绑定只用输入合同字段，不复制响应派生字段。

任务/Task Hall正文不自动混入快照；子任务按自身目标、schedule物化no_project已在隔离测试验证，无需在生产run-due批量触发已有计划。

## 独立验证与限制

- 七模块177项0失败/错误/跳过，含新快照27项及既有任务/实例/项目/开发要求/B1a登记绑定。覆盖两列幂等/旧NULL、四情况创建、13键/阶梯、事实SQL1/0、已有事务和alias留证。
- WAL双线程100提交/400读取无撕裂；最终事实前项目删除400无任务/Hall；真实SQLite关系唯一冲突409同次回滚；子授权预扣1，快照失败恢复0且父快照不变。
- SQLite实际JSON原文直接比较：claim、heartbeat、到期重排、重领、改绑定、complete、cancel后原文字节/状态不变；到期重排沿用agent身份权限。
- 全量881/pristine未重跑，生产加载/生产迁移/人工步骤未验；实际模型版本/开发能力/主动宿主等待与MCP/页面消费不在本次范围。
- 原196报告保持，其单线程/模拟commit限制由协调方新增独立证据补充，不能追改为开发者做过这些验证。

本机证据.tmp/runner-role-binding-b1b-review/含冻结代码、原交付、177项日志、探针/review/收取回执；忽略产物不随Git发行。下一片待人工验收或明确继续授权。
