# 338忙任务退出保护：正常加载与验收

**2026-10-26 10:27用户人工确认：** 用户回复“启动成功”，本轮实际页面启动状态基础验收通过；原部署自检/90.075601秒心跳/保护项保持，未追加生产忙态注入、停启或新开发。338本轮收尾闭合，后续仅按用户要求明确下一新功能。

**2026-10-26 10:21部署自检完成，页面人工验收待用户刷新确认。** 用户已在原API终端重启，新API自动带起runtime18784（UTC02:17:38.088854），未另行serve/手动start角色。五宿主serving、shutdown idle、startup complete/worker无错；小D按原true/rev1自动gen82/ins_b65106fc9fdb/PID18580 ready/idle，同实例心跳推进90.075601秒；其余四false/rev0/stopped/无owner。新APIuptime168秒，源码指纹及重启后HTTP页面/app.js/workspace.js与已复核3203044一致。五完整binding/角色配置/项目要求/偏好及250/286整份公开响应相同，无running任务。

本次原runtime4956普通stop于UTC02:09:55开始，首次CLI退出1/blocked、draining_hosts/runtime_host_stop_timeout，记录未覆盖。只读观察原后台自身重试，UTC02:11:38.117003最终shutdown complete/pending空/error与worker_error清空；UTC02:14:47及02:16:01原11PID全部absent、五角色stopped/无owner，才请求用户重启原API。没有第二次stop、强杀/CAS/清锁或读取私有日志来“修复”超时。原blocked回执不改写为0/stopped，最终同代完成及OS证据独立保存stopped.json。

证据在deployment-20261026/的before、stop-intent、stop-result、两次stop-observation、stopped、api-check、start-request、ready、heartbeat、static-check、RESULT、freeze-and-archives.json。275新/原冻结及332至338原归档零错配，产品/正式测试未改。忙时拒绝/编号/claim守卫采用338既有独立17核心Python/31页面和正常权限19/221证据；本轮无生产忙态注入，不将静态HTTP字节核验冒充真人页面验收，不外推强制取消/原生子链管理/断电恢复。

2026-10-26。用户明确“执行实际加载与验收”，授权本次正常更新API/后台并验证338；不重复引用已执行的上片停启许可。代码3203044已推送，338/2984独立核验收取，无必须修正；本轮不开发新功能。

## 正常加载顺序

1. 原统一CLI只正常消费既有启动清单，原human凭据只用于API认证。公开GET保存五完整binding/角色配置/项目要求/用户选择、250/286整份任务、运行任务、API健康与原后台元数据；确认当前实例无忙任务、worker空闲、所属PID及创建时刻可核。只核运行器入口/本后台所属进程，不增加原生子进程树扫描。
2. 从原CLI一次普通stop --apply --wait --wait-seconds300，核本代stopped、原后台/宿主/角色入口确证退出、五角色stopped/无owner；回blocked/timeout/unknown则保现场，仅只读观察原后台既有重试。只有同代最终complete/error空、所属PID退出与角色归属释放重新确证后才继续；原失败回执保持，不强杀/CAS/清锁或另起服务。
3. 本片API与后台都需新版。原API为external，现有reload-api明确不拥有它：先核其是否已在实现提交后正常启动；仍旧时由用户原终端Ctrl+C后重跑原API命令，不从协调脚本终止外部API或另起第二API。此处若需用户动作，属于原终端操作边界，不另索同范围许可。
4. 新API正常启动可能自动恢复已登记后台；先观察原status，若新代已在运行则不重复serve。只有仍stopped且API新鲜健康、旧所属进程均已退出，才从原CLI serve --apply --attach-api --detach恢复一次后台。外部API始终不接管。
5. 核实际新API启动、runtime新代、五宿主serving、startup complete/worker无错、shutdown idle。保留用户小Dtrue/rev1及其余四false，按保存选择自动启动；ready后不手动start，不PUT偏好，核同实例心跳至少推进60秒。完整比较绑定/配置/要求/偏好/250/286，记录所有真实结果。

## 验收口径

普通加载/退出与小D恢复使用真实生产元数据。页面静态新版本与实际app函数链核对，用户可刷新实际页面验收。忙时拒绝关闭、编号显示、停止后claim拒绝与零写入，已有338独立17核心Python/31页面和正常权限19/221证据；不为制造忙态修改生产任务/租约/实例、不伪造claim/report或中断真实工作。若未实际遇到自然忙态，明确区分生产加载验证与隔离/独立行为验证，不宣称做过生产忙任务故障注入。

用户明确责任边界保持：有任务执行/运行器忙则挡住退出，空闲正常关闭TALK自身服务与运行器入口，内部子进程由对应运行器负责。原生进程树管理/退出证明切片已撤回，不作为本轮验收门槛。

本轮证据写.tmp/role-busy-stop-v1/deployment-20261026/，不覆盖旧冻结/原报告/旧部署证据；不读生产配置正文/Key摘要/DB/private/HOME/native/session/log，原启动清单与human凭据仅由原用途消费。250failed/2767未收取、286paused、五角色绑定与用户选择保持。无需追加DeepSeek非阻断复核或下一片。
