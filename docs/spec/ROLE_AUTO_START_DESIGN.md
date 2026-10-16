# 新角色配置完成后自动首次启动：实施合同

2026-10-16，249修订方案经Codex独立复核，以下技术决策确认用于首个后端切片。**2026-10-16，254定向返修后经Codex独立实际代码复核、63项相关回归及9项API/SQLite边界探针通过并收取，后端8源随本轮发布。原250失败历史及原P1/P2证据保留；前端auto_start载荷/文案仍未接线，生产与真实受管生命周期另验。** 原始需求见[已确认需求](ROLE_AUTO_START_REQUIREMENTS.md)；本合同只修订[创建配置请求](ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md)、[配置作业](ROLE_PROVISION_CONTRACT.md)及[受管服务](ROLE_SERVICE_CONTRACT.md)中“新页面创建的完整配置成功后由人类再点启动”的目标行为，旧客户端/旧请求原样兼容。

## 1. 用户行为与范围

- 新页面创建角色时将显式携带自动首次启动意图；完整配置成功后系统自动执行一次既有角色启动。手动关闭/再启动继续可用，不另加默认关闭的勾选项。
- 本后端片仅提供意图保存与同事务启动入队，前端载荷/文案随后由Codex对接。前端未接线前不得宣称保存角色已自动启动。
- 不追溯存量角色、旧请求或绑定重置；不改变原生/外部启动入口，不隐含设置“随项目自动启动”，不扩为全局自启动、无限重试、原生登录或退出清理。

## 2. 数据与兼容

`RoleProvisionRequestRow`增量4列，幂等加列迁移、无需重建旧行：

| 列 | 默认与语义 |
| --- | --- |
| `auto_start_intent` | INTEGER NOT NULL DEFAULT 0，人类创建意图的规范布尔值 |
| `auto_start_status` | NULL；有意图时pending，随后enqueued/not_eligible/failed |
| `auto_start_launch_id` | NULL，可索引；该请求已投递的唯一动作锚点 |
| `auto_start_error_code` | NULL，稳定码，禁止异常正文/秘密 |

- `RoleRequestCreate`增加可选`auto_start`；缺省/None/false规范为false。recover传非None值仍422互斥载荷错误，恢复本身不自动启动。
- 四字段创建payload、共享`build_role_creation_fingerprint`、版本常量、`RoleCreationOperation`与C1/completion严格比较原样。不得把auto_start塞入共享payload/指纹，也不新增fingerprint_version列。
- 同request_key除既有项目/kind/指纹外，额外比较规范auto布尔值；异值409 `role_request_key_conflict`。准确重放纯读，先于实时目录检查，不刷新快照/意图。
- 只读投影增量4字段：`auto_start`、`auto_start_status`、`auto_start_launch_id`、`auto_start_error_code`。所有既有API路径/方法、租约、写权限保持；claim/report不新增调用者可写字段。
- `pending`仅是尚未处理的意图，`enqueued`仅是已投递事实，都不能当服务ready。配置失败/取消不产生launch或后台重启；结合请求终态解释意图状态，不能显示虚假启动中。

## 3. 自动首次启动与人工意图

- 仅新create请求持有意图、真实`require_completion_facts`成功，且首次`report(provisioned)`进入有效非重放分支时，才尝试自动入队。
- 同一外层写锁内，读取角色服务状态：无行或`generation==0`才有资格。已有任何非零世代则保持现有人工/服务动作，不生成新世代，记`not_eligible/auto_start_manual_intent_present`。
- 当前初始默认stopped不落状态行；既有start/stop提交均将generation推进至至少1。新自动流程也会形成非零世代，不能永久把“有行”解释为一定由human创建。
- 自动入队后人工stop沿既有世代/所有权合同失效pending动作或关闭所属进程。完成回报重放、迟到回报、页面刷新、worker重试不产生第二次启动；无无限后台重投。
- 服务端仍按实际`control_kind`/绑定等守卫判断，宿主仍按`verified-runtimes`预检；`adapter_status=unverified`与`control_kind=unknown`不是同一事实，不修改原门控或伪造ready。

## 4. 事务与审计

1. `report_request`保留外层`BEGIN IMMEDIATE`、身份/租约/世代/版本/真实完成事实校验，先flush配置报告终态。
2. 嵌套SAVEPOINT内复用同一受管start核心，完成全部state CAS/launch写入并实际flush；共享核心不能commit、rollback或另开BEGIN。人工start薄包装继续负责原事务和human审计，行为/错误码保持。
3. 入队成功释放保存点，在同一外层事务记录enqueued与launch锚点；可恢复入队异常回滚保存点全部写后，须确认driver实际写事务仍活动、同一事务内已flush的provisioned事实仍可读，才记录failed/稳定码、保留配置成功。若RAISE(ROLLBACK)等撤销外层事务或连接失效则上抛500，禁止另起事务补写auto状态，不按异常文案分类。
4. 外层只有一个commit。外层DB写/提交失败整体回滚，按原错误协议返回并允许有效租约下安全重试；不吞失效session或承诺数据库失败仍成功。已提交回报精确重放零写入。
5. 自动动作审计可用`system:auto-start`，通过请求created_by/意图/launch锚点追溯原human，不把宿主operator当启动授权人；不创建假human成员或新权限入口。

4个新增稳定码：`auto_start_control_kind_not_managed`、`auto_start_config_disabled`、`auto_start_manual_intent_present`、`auto_start_enqueue_failed`。原配置disabled/来源无效等上游守卫不绕过；具体拒绝优先按真实入口既有校验。

## 5. 本片验收与实际能力边界

- 隔离验证成功入队一次；未配置成功/旧请求/恢复/无意图零启动；同键异意图409、旧库两次迁移与旧创建重放保持。
- 验证stop-before-report、先手动start/stop、先自动入队再stop、重复/迟到回报、精确重放无额外世代/动作；四条件ready和所有权边界不变。
- 真实SQLite触发器验证launch插入失败、部分state更新后失败的SAVEPOINT回滚；区分RAISE(ABORT)局部降级与RAISE(ROLLBACK)外层撤销500/原事实保持，去故障同token/revision重试恰好一次；双连接无半提交。测试必须覆盖实际实施函数，不能仅复用方案原型冒充产品通过。
- 配置成功与服务就绪分开。真实运行还依赖常驻宿主、真实受管能力/已登记runtime、原生登录与实例就绪；unknown/control未登记不能绕过。pending不是实际模型工作证明。
- 首片只后端8个白名单源码/测试文件，宿主/worker/前端不改，禁止生产DB/真实Key/native凭据操作。前端、真实原生/异常退出/主动等待仍分别待验。
