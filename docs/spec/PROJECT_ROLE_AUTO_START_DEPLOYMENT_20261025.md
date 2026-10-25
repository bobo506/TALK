# 项目角色选择性自启动：复核闭合与正常加载方案

**2026-10-25 18:52最新实测：** 用户报告“用原来的启动命令启动了”。UTC10:50:58 API uptime76秒，/agents已返回与/roles一致的startup，335控件补正已实际加载。现有Chrome human bobo/小D详情实看“随项目自动启动”可见且已勾选；公开API显示小Denabled=true/revision1/updated_at=UTC10:50:31，另四false/revision0。该选择由用户保存，本Agent未勾选或PUT；必须保留，不能再按旧方案一律写回false。截图user-restart-20261025-1850/visible.jpg。

旧runtime11280仍UTC04:33:28启动，原12PID及创建时刻均相同、五宿主serving，原DSH gen76/ins_aa6223b0735e运行/idle；只有API更换，没有后台换代，旧startup_state=failed保持。五绑定/角色公开配置/250与286完整任务相同，无running任务；控件“显示并保存”问题已真实闭合，下一代自动启动仍待后台正常重启实测。若继续后台重载，应以用户最新选择为准，小Dtrue应由新runtime本代一次执行；先观察自动启动结果，已ready就不重复手动start。其余四保持false/停止。原stop被审批拒绝的事实保留，Agent未绕过或执行停机；用户尚未报告后台stop/serve完成，不作已执行推断，不要求再次重启已更新的API。

**2026-10-25 18:37最新：** 控件人工验收返修335 complete/2981已收取，无必须修正；d3c9c96补齐真实页面/agents DTO，197冻结及旧63/116/162、原332至334保持，335原19份42557字节归档。原始未修改独立2测试中1项受CreatePipe沙箱限制1E；文件重定向下同2项、独立/sync探针和缺字段负向对照通过，原失败不改。当前外部API仍缺本次/agents补正，14:42的重载只加载了初版；因此本次需在正常停后台后由用户原终端重启API一次，不能仅凭startup路由存在跳过本补正加载。

加载前只读预检通过：runtime11280/五宿主/当前DSH桥共12PID均present且有真实创建时刻；无running任务、worker空闲，五自启动选项全false，仅DSH gen76运行/idle，其它四停止。五完整binding/要求及250/286公开响应与派前相同。预检两次脚本断言/字段错误未产生生产写入，改按公开observed_instance_id后通过，原事实存deployment-20261025-1834/。

随后原CLI普通stop/drain请求被自动审批在CreateProcess前拒绝，未执行；理由是停后台/五宿主会造成中断，现有证据只有API重载和方案准备，缺少用户对后台停机的明确确认。没有绕过或改用其它停机方法。**现待用户明确授权一次正常停旧后台/五宿主、用户原终端重启API、再恢复后台及原DSH；五选择保持false，不改配置/模型/Key/绑定/250/286。** 用户答复前不实际停启、勾选或读取额外私有资料；独立复核不再追加，下一无关片不自动开。

2026-10-25 14:36（Asia/Shanghai）。本文件是可审的加载方案，尚未执行生产停启或启用任何角色的自启动选择。正式加载需按本片既定边界取得明确确认；原一次元数据/侧账本恢复例外均已用完，不延伸到本轮。

## 复核已经完成

- 334正式结果2980为complete，无必须修正；任务succeeded/submitted，UTC06:33:30.383042正常收取completed。333原partial/2979与review failed、332原failed/2978保留，不追改或收取失败332。
- DeepSeek本次独立重跑10项原MF-1探针（含333四类失败反例，断言未改）及7项新增判断，共17项通过；MF-2/MF-3已由333独立通过，不重复全面首审。Codex本轮16正式+10原探针共26项自检保持，不能相加冒称43项不同用例。
- 058e153实现之后产品/正式测试/web没有变化。162份4240533字节新冻结、旧63/116与332原33/333原29归档均零错配；334原交付15份36242字节按manifest归档在fix2/pickup334/334-original-review。正式消息与本地delivery逐字段一致。
- 334实际reuse_session，续333原窗/count2，末376821/1000000=37.6821%，没有复用332被tainted的旧窗。公开五角色完整binding/开发要求及250/286整份公开任务响应与派前相同。
- 沙箱限制原样保留：DeepSeek探针内部对私有ACL发布使用已注明的plain-publish替代，本次未独立验证真实ACL；真实断电/原生模型/浏览器交互仍未验。不再为这些非阻断观察追加复核任务。

## 只读加载前现状

UTC06:35:11公开API/原运行器status实测：API healthz=ok/db=ok/storage=ok，uptime23480秒，新startup POST不在运行API的OpenAPI中，五角色startup公开字段均null。这是旧API事实，不能当成已保存false或已加载新功能。

runtime11280（UTC04:33:28启动）running/present，api_mode=external，不拥有原API进程；startup_state=failed/8轮/HostError是旧版兼容问题留下的状态，不是新修正失败。worker_in_flight=false、worker_error=null，五宿主serving，宿主/解释器PID分别为：DSH15536/15712、Codex9496/5152、Kimi7548/9704、受管K2.8 15776/10732、受管WBK3 4340/7908。PID只用于随后核对，执行前必须刷新，不把旧快照当成实时许可。

仅DeepSeek gen76/ins_aa6223b0735e/PID10360 running/ready、任务334完成后idle，其它四角色stopped/无owner。250仍failed/failed、原结果2767未收取；286queued/accepted/paused；五binding/项目要求保持。

预检仅原CLI经既有load_config读取原talk-runtime.json，原human凭据仅正常GET公开角色/healthz/OpenAPI；没有独立读config.toml、角色Key/摘要、生产DB/侧账本/私有state/HOME/native/session/log。最初默认沙箱CLI退出1且未保留具体stderr，不推测原因；之后脚本误用/health收到404，按源码更正/healthz后预检通过。失败事实记fix2/pickup334/preflight-attempts.json；无生产写入。

## 确认后按顺序执行

**14:42实际进展补充：** 用户已提前重载API。UTC06:41:37公开实测新startup路由存在/uptime127秒，五startup均enabled=false/revision0/last_activation=null；原runtime11280/五宿主尚未重启、DSH原运行状态保持。本次仅只读，未后台启停或勾选。后续刷新预检后可续后台普通stop/drain及第4步，API新版本持续健康则第3步不重复执行。完整加载尚未完成。

1. **刷新只读预检。** 原human公开接口确认没有新领取/运行任务、worker空闲，保存五角色完整公开投影/binding/项目要求、250/2767及286；原CLI刷新runtime/五宿主PID和代际。若用户期间有手动启动/选择变化，以新事实为准，不用旧快照覆盖。
2. **正常停后台。** 用原统一入口`python -B scripts/talk_runtime.py stop --config D:/claude-test/TALK-private/talk-runtime.json --apply`；等待普通stop/drain退出、原runtime和五宿主/解释器PID消失、角色停止且无owner。不给强杀/CAS/清锁许可；未闭合则保存公开错误并停止后续加载，不冒称停止成功。
3. **用户重启原API终端。** API由用户外部终端持有，平台不能接管reload；后台退出后提示用户在原终端Ctrl+C，重跑原API启动命令。不得关闭其它终端、强杀API或启动第二API。API正常启动流程自动创建新增自启动设置/执行审计表，不手动修改或检查DB、生产配置或旧数据。
4. **用原入口启动后台。** API健康后用`python -B scripts/talk_runtime.py serve --config D:/claude-test/TALK-private/talk-runtime.json --apply --attach-api --detach`，保持原清单/凭据/绑定，不增改配置。新runtime自己的activation触发一次本代处理，不额外手工POST模拟或重放activation。
5. **核加载结果。** 新API存在startup POST及human设置入口；五角色公开startup可读，首次部署默认enabled=false、没有自动写true。新runtime实际代/activation、startup_state=complete、worker无错、五宿主serving；如果是unsupported/failed/unknown，只能报告未通过，不借旧API降级冒称新功能可用。
6. **只恢复原DeepSeek。** 等新宿主就绪后通过原公开受管start恢复DeepSeek，确认新实例ready/idle、同实例真实心跳至少推进一个60秒周期；其它四角色保持停止/无owner。再次逐字段比较五binding/公开配置/要求及250原失败结果、286paused，不写自动启动选择，不改模型/Key/旧任务。
7. **页面验收。** 检查新版静态资产/页面控件与公开返回匹配。用户可在角色页看到“随项目自动启动”默认未勾选；勾选只影响下一次实际后台启动，当前页面刷新不会拉起，人工停止后本代不自动重拉。实际保存选项/下一代自动启动及真实断电由用户后续验收明确安排，本次加载不代勾选或主动断电测试。

## 失败处理与完成条件

正常停启任一步失败，保留原错误/公开状态并报告，不追改历史、清锁、强杀或读取额外私有资料。回退若需代码切换、再次停启或超出方案的数据操作，应先给具体方案；不能删新增审计表来伪造未执行。

本次只批准本片加载及恢复原运行角色，不包含下一个新功能。加载的完成条件是新API/runtime确实生效、默认false和原保护不变、仅DeepSeek恢复且真实心跳推进；真实断电/原生模型/浏览器交互尚未验证的部分继续如实注明。加载后的常规核对不另派无必要审查任务。
