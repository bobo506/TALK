# Project Progress

Updated: 2026-10-25 18:37（Asia/Shanghai）。335 complete/2981已收取，无必须修正；加载前只读预检通过，但普通停旧后台/五宿主被自动审批在执行前拒绝，缺少用户明确后台停机确认。未实际停机或绕过，补正尚未加载；待明确授权后按具体方案统一加载并实看控件。

## 当前事实

- 身份agent:codex / prj_e8fe7066bbec / lead已实核。335正式complete，UTC10:33:06.725371收取completed；19份42557字节原交付归档ui-fix1/pickup335/335-original-review，正式消息与本地delivery一致。实际续333/334窗/count3，末44.7013%。
- 真实/agents DTO→实际loader/控件链路在独立文件重定向下2项通过，独立/sync探针及缺字段负对照通过；未修改运行2项原有CreatePipe环境1E保留。197新/旧63/116/162及332原33/333原29/334原15零错配，产品d3c9c96未再改；不重审runtime或新增非阻断任务。
- 控件缺失根因为页面从/agents取数而原只给/roles填startup；2产品5行已补。当前生产外部API尚无本次/agents补正，因此此前重载初版API不等于已加载此补正；用户页面尚待一次正常加载实看，不称已显示。
- 公开五完整binding/项目开发要求及250/286整份公开任务与派前相同；250failed/failed/原2767未收取，286queued/accepted/paused，332failed/2978、333partial/2979、334complete/2980保持。
- 原CLI/公开接口加载预检通过：runtime11280+五宿主10PID+当前DSH桥10360共12PID present且有创建时刻；无running任务、worker空闲、仅DSH gen76/原实例idle，其它四停止；五startup均false/revision0。原记录deployment-20261025-1834/before.json。
- 普通stop/drain命令被自动审批在CreateProcess前拒绝，理由是会中断生产后台/五宿主，而现有记录只有API重载/方案准备，缺用户明确后台停机确认；没有执行或尝试绕过。旧后台/API/角色继续运行。
- 本次只正常认证公开GET和既有CLI status、已知PID元数据；未勾选/启停/删除/恢复、未读配置正文/角色Key/DB/侧账本/private state/HOME/native/log。原一次元数据/定向恢复许可已用完，不复用。预检初两次脚本断言/字段错误未生产写入，记录保留。

## 下一步

1. 请用户明确授权按[具体加载方案](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)正常停旧后台及五宿主（短暂中断），用户原终端重启API，再原attach-api/detach启动后台、仅恢复原DSH并核60秒真实心跳。
2. 授权前不再发停机命令；不接管外部API或开第二API，不强杀/CAS/清锁，不代勾选/改配置/模型/Key/绑定/250/286。授权后同范围不重复询问。
3. 加载后原页面实际检查“随项目自动启动”可见且默认未勾选，保存/真实下代启动或断电人验另按用户安排。本片不再追加复核，下一无关切片先确认。

详[加载方案与审批记录](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)、[控件返修](spec/PROJECT_ROLE_AUTO_START_UI_FIX_20261025.md)和[历史](PROGRESS_HISTORY.md)。
