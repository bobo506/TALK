# 页面角色请求的宿主 worker（R1-4b）

2026-10-13，235/236开发返修、Codex接手G1/G2、237独立复核整链已收取。2026-10-14完整创建/配置页面经Codex开发、238/239独立复核闭合并收取，见[页面验收](ROLE_CREATION_PAGE_ACCEPTANCE.md)；完整功能仍待人工验收。本轮没有启用生产项目、部署human凭据或启动原生运行器。

2026-10-14 #240/#241目录与真实运行器ID补正已独立闭合发布。先重载服务端再刷新页面；worker流程无变更，仍需管理员原有私有凭据和同机部署。创建/配置不要求运行器已具备受管启动能力，未核验的Kimi登记不等于原生能力通过。

协议见[创建配置请求合同](../spec/ROLE_CREATION_PROVISION_REQUEST_CONTRACT.md)。页面只提交人类意图和读取进度，角色Key仅由受信宿主接收一次性响应并私有落盘。服务端与worker必须同机；页面可以来自局域网。

## 操作者准备

当前本机部署记录（2026-10-14，用户明确授权）：项目`prj_e8fe7066bbec`、宿主`PC-202312301323`，operator文件为`D:/claude-test/TALK-private/operator.key`，角色Key根为`D:/claude-test/TALK-private/keys`，均已准备并核验私有权限。本次仅处理“Kimi k2.8”的确定请求后退出，已provisioned；宿主开关开启不代表常驻worker已运行。后续自动处理需明确启动常驻worker，仍不自动启原生CLI。三份身份档存项目`.talk/agents/`；**Key根必须在仓库外，不能指定项目根或其子目录。**

- 使用现有human账号的operator Key文件，保存在仓库外；没有内置验收账号。agent Key不能创建/启用项目请求。Key正文不写命令、页面或任务。
- 明确项目ID、项目根、宿主标签和仓库外角色Key根。宿主标签必须等于该项目role-provision-host设置，生成三档和Key的目标路径须与服务管理器一致。
- 项目宿主配置与worker默认关闭。human通过`GET /api/projects/{id}/role-provision-host`读取版本，再通过`POST /enable`提交`host_label/expected_version`；这是部署时的显式操作。本轮未替操作者执行。
- 请求从human提交的`role-requests`发现，目标member/origin取真实事实。新角色不需要逐个手写member/operation_key清单或复制角色Key。

## 独立运行

以下均为参数示例，先替换实际标识、目录和仓库外operator文件路径。

默认关闭，零HTTP和文件/数据库写入：

```powershell
.venv/Scripts/python.exe -X utf8 scripts/role_provision_worker.py --project "<项目ID>" --host "<宿主标签>" --once
```

只读发现计划：加`--enable`，不加`--apply`；只GET，不领取、创建、轮换、写文件或ACK/report。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/role_provision_worker.py --project "<项目ID>" --host "<宿主标签>" --base-url "http://127.0.0.1:8000" --project-root "D:/claude-test/TALK" --key-root "D:/TALK-private/keys" --operator-key-file "D:/TALK-private/operator.key" --enable --once
```

准备妥当后在同一命令加`--apply`真实处理；去掉`--once`则轮询，`--max-rounds N`限制轮次。输出为脱敏JSON，无`--json`选项。每轮最多处理一个请求，默认轮询2秒、发现上限20、单轮IO预算120秒、单请求超时15秒；可用`--poll-interval/--discovery-limit/--io-budget-seconds/--timeout-seconds`调整。每次HTTP调用重新核当前资格/取消与剩余预算，不给旧工作套后来代际。

## 接入服务管理器

已有`role_service_host.py serve`命令可加`--provision-worker`接只读计划；只有同时加`--provision-worker-apply`才领取并配置。保持原operator、项目根、Key根、宿主标签及真实运行器参数。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/role_service_host.py serve --project "<项目ID>" --host "<宿主标签>" --base-url "http://127.0.0.1:8000" --project-root "D:/claude-test/TALK" --key-root "D:/TALK-private/keys" --operator-key-file "D:/TALK-private/operator.key" --provision-worker
```

worker在独立线程串行推进，不持有服务的Popen所有权；慢配置不阻塞主循环poll/stop。宿主新增选项为`--provision-worker-discovery-limit/--provision-worker-io-budget-seconds/--provision-worker-max-rounds`；后者限制serve轮次。没有单独worker轮询间隔选项，沿serve的`--poll-interval`。

保存并配置不会启动角色CLI、登录原生账号或调用模型。真实启动仍由单独的人类服务意图触发，并受既有运行器能力/所有权检查约束。

## 失败和恢复

create只接一次201里的Key；响应丢失或200 reused不返Key，先核本机当前本人Key，无则`manual_recovery_required`，需human新recover意图。recover在角色锁下先核本机当前有效Key，已有就续跑；没有才按固定before版本轮换一次，重复意图不再次轮换、不重读旧Key。

私有Key与`<成员目录名>.credential.json`分别原子发布，元数据只记member/version/source/intent/时间。元数据失败不删除已发布有效Key；下次本人认证及服务端版本核验后修复。专用恢复仅替换来源可证的本人已知旧代，未知/异成员文件拒覆；普通旧脚本stale拒覆保持。

禁用/换代/到期/取消后停止受影响后续工作；已创建成员保持。预算耗尽且无法报告时请求可能仍为created，待租约失效重领；次数耗尽或failed须human resume，不自动清零。`outcome=reported`表示失败结果已送达，仍是业务失败，worker和host CLI退出1；provisioned为成功，关闭/只读/停止退出0。

## 已有证据和限制

237独立正式50、相关旧320、原6、检出3与独立13探针分别0失败/错误/跳过；包含隔离临时uvicorn、真实WorkerTransport、子进程CLI 0/1、真实私有Key/DACL与三档、失败/恢复/预算/取消/凭据负向。只证明Windows/Python3.12的隔离代码链路，不证明生产部署、原生登录/模型/CLI或完整页面已验。

主循环非阻塞收集worker；once/max_rounds退出收尾最多两段有界grace，每段按预算+超时+5秒计算、上限180秒，未结束则请求停止并如实记结果未回收。完整Ctrl+C/宿主退出清理仍在后续R1-4，socket超时不等于滴流网络的绝对墙钟期限。租约/文件检查存在检查到副作用间的真实窗口，不外推恶意宿主、动态路径替换或跨机互斥防护。
