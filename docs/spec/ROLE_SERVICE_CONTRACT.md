# 角色受管服务合同（R1-3）

> 2026-10-17：旧K2.8单角色试迁移正式验收通过。262由本轮原受管实例完成并独立核验/收取；用户随后确认页面关闭→刷新不自启→再启动ready三步均通过，服务generation7 stopped/generation8 ready佐证，当前新实例仍由原manager持Popen。原ID/Key/绑定/历史保持，其它角色未迁移/启停。本轮仅文档收尾，沿用c129a63/161证据，不外推长任务、主动等待或完整日志已完成。

> 2026-10-17真实旧K2.8试迁移补正：用户明确批准共用runner改managed_cli且仍只启动旧角色。首次真实stop暴露通用CLI未监听停止文件；Codex直接补停止处理及9新测，CLI/Kimi/Codex相关共161项通过。修正后真实启动→正常控制文件关闭/释放原owner→同manager再次ready已通过；262最小接单已派待通知后核验，人类页面与其它角色/完整日志仍待。原自动拒绝/stop_timeout/正常恢复及最终结果均留痕。


> 2026-10-17：260[宿主模板与内置执行预算](ROLE_HOST_RUNTIME_CONFIGURATION_DESIGN.md)已收取，Codex直接修正配置校验/预算快照后74项相关验证通过，本轮发布。逐runtime模板与内置默认21600/可覆盖、旧global/custom兼容已接线；公开仅预算数值/来源，claim/report协议、ready/stop/MCP超时与身份/unknown/unverified/owner守卫保持。5角色真实平移及原生能力仍待，未启停生产。

> 2026-10-17：259已完成[旧身份补录产品片A](ROLE_LEGACY_ATTACH_DESIGN.md)。宿主仅将精确legacy_attach加入可信选择来源，保留choice_id/六维匹配、归档/绑定/能力/归属与owner检查；补录接口不生成配置作业或start动作，不代表真实原生就绪。反向操作键冲突与非法名称由Codex直接修正，162项相关回归及2项WAL探针通过；5角色真实登记/启停仍待。

> 2026-10-16新增已确认需求（待实施）：[完整异常日志与旧角色统一受管](ROLE_RUNTIME_LOGGING_AND_MANAGEMENT_REQUIREMENTS.md)。详细错误须持久留存并可跨重启追溯，旧角色保留身份/历史迁入同一宿主启停；以下所有权、能力登记与真实验收守卫保持。本需求仍待实施，不接管外部PID、改变能力或启停实例；254事务返修已独立通过，未扩入本需求。

> 2026-10-16自动首次启动后端已独立通过：[实施合同](ROLE_AUTO_START_DESIGN.md)定义新create显式auto_start意图、真实配置完成后同事务一次start入队及人工意图优先；254已收取，255前端显式意图与反馈独立通过并收取，待人工页面验收。下面世代/所有权/就绪/能力守卫保持，入队不等于ready；不以bound/provisioned绕过unverified/unknown或声称生产已启动。

状态：2026-10-12，223–229代码复核与页面反馈补正完成并收取，用户本轮页面基础验收通过。2026-10-13，235–237默认关闭的请求worker接线独立通过，真实原生运行器及完整创建页面仍未验。原设计见 [ROLE_LIFECYCLE_DESIGN.md](ROLE_LIFECYCLE_DESIGN.md)，实施顺序见 [ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md](ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md)。

## 范围与执行者

R1-3实现服务意图、宿主claim/report、实例就绪、逐角色启动/关闭和项目全部启动。服务端不创建或停止进程；`scripts/role_service_host.py serve`是受管子进程的常驻持有者。启动TALK、启动管理器均不隐式启动角色；旧请求/无auto_start意图保存配置保持原行为。新create显式auto_start意图只在真实配置完成后入队一次，新页面已显式提交该意图，旧请求与绑定重置不追补；页面与真实原生能力仍分别待验。脚本`start`、`stop`、`start-all`只写请求，`status`只读；短命请求进程不持有子进程。

固定决策/执行产品分级已停用，具体任务`created_by`与主动/被动规则保持。删除/归档、外部桌面引导、正常退出清理在R1-4；真实发起者主动链路在I-4。

## 六个API

| 入口 | 权限与行为 |
| --- | --- |
| `POST /api/projects/{project_id}/roles/{member_id}/service/start` | human写启动意图，分配新世代与预期实例；不等于启动成功 |
| `POST /api/projects/{project_id}/roles/{member_id}/service/stop` | human写关闭意图，沿用原start归属；已证明停止时幂等返回 |
| `POST /api/projects/{project_id}/role-services/start-all` | human批量请求；可用`member_ids`重试子集，逐角色结果，部分失败不整体回滚 |
| `GET /api/projects/{project_id}/role-services` | 已认证只读服务投影，用于刷新/轮询 |
| `POST /api/role-service-launches/{launch_id}/claim` | 目标agent或合法human宿主领取，核角色/项目/动作/实例/host及原归属 |
| `POST /api/role-service-launches/{launch_id}/report` | 核领取身份、世代、动作、host、claim/owner token及时间窗，写观测结果 |

`role_service_state`保存期望、世代、当前动作与原进程归属；`role_service_launches`保存一次动作及其回执。库内仅保存token哈希；token只在受权claim交互与宿主私有证明中使用，公共服务投影不返回token、argv或私有绝对路径。

## 请求、就绪与重放

启动成功必须由本次预分配`expected_instance_id`、`launch_id`、世代及合法时间窗的实例/回报证明；旧实例心跳和“命令已提交”不能证明成功。实例的项目/launch关联不可改写或清空。

首次回报核`claimed_at ≤ report ≤ launch_expires_at`及全部归属。相同完整载荷重放只返回原receipt，过截止也不再改当前状态；异载荷`report_conflict`；被新动作取代后的旧动作首次回报`stale_report`。start与stop分别有动作与领取证明，stop不能用新start覆盖旧owner。

## 活进程所有权与关闭

- `ownership_held=true`意味着原进程归属未释放。spawn后失败、未就绪或停止失败仍保留原归属，禁止重启覆盖；原关闭入口保持可达。纯预检失败且明确未spawn可以释放归属。
- 宿主持有原Popen句柄与不可替换的原始事实。关闭核项目/member/host/owner/instance、实际OS PID与进程创建时刻、私有控制路径及磁盘记录一致性。PID只作诊断；新管理器不凭PID/磁盘文件重新认领旧进程。
- 已成功发布的证明缺失、不可读、篡改或控制路径非法时，稳定拒绝`unknown_owner`，不写控制文件、不停止、不清记录。仅明确`record_persisted=false`且记录路径真实缺失、无reparse时，允许凭完整原始内存事实关闭本次进程；其余身份核对保持。
- spawn即登记句柄，存储异常保留活进程；进程已退出但失败回报尚未确认时保留原证明。只有证明停止并完成相应确认后才回收句柄/记录。当前runner分类变化不撤销原stop，新start仍须满足受管分类。
- 私有目录/记录复用R1-2 DACL、路径与锁保护；按项目/角色/launch保存，不互相覆盖。operator Key从环境或文件读取，角色Key只传文件路径，token/Key不新增明文argv通道。

## 运行期心跳与只读状态

2026-10-18补正：启动成功回执是历史事实，公共角色列表与服务投影还须核当前运行证据。仅原持久状态为`running`时，读取当前启动的预分配实例，核项目/member/launch/世代与原进程归属关联，且实例为`idle`或`busy`、`last_seen_at`在90秒内，才保持当前`running/ready`。实例缺失或offline/error、归属不匹配、心跳过期分别投影为`unknown/unknown`并附`instance_unavailable`、`instance_identity_mismatch`、`instance_heartbeat_expired`；不将失联直接证明为已停止。

以上只影响本次GET投影，不回写`role_service_state`、启动回执、世代或owner，不产生stop/start动作。原`last_result`仍是上次动作结果；启动/关闭门控保持原持久状态及所有权守卫，不因失联允许重复启动。匹配实例重新上报近期心跳后，投影可恢复为`running/ready`，不新建launch或认领进程。桥接心跳也不替代宿主原Popen证明、原生模型或主动等待验收。

通用CLI及复用它的Codex/Kimi/DSH受管入口每30秒按已有实例PUT协议刷新心跳。刷新与状态变更串行，保留最近状态、当前任务、错误和受管关联；短暂网络错误留待下轮重试，诊断只记录异常类型，取消/正常退出先结束心跳再沿原清理路径上报offline。非受管旧入口保持原上报行为。

页面在角色页可见时持续轮询启停中、运行中及上述失联状态，离页/切项目/切账号停表并丢弃迟到响应；全部关闭/未启动后停止续期。失联显示“运行状态待核实”，不显示为启动失败或已关闭；尚未收敛的批量结果单列“待核实”，不纳入失败重试集合。状态发现通常在最后心跳90秒过期后的下一次2秒轮询，不承诺瞬时发现或在网络不可用时证明进程退出。

### CLI bridge正常停止处理（真实验收补正）

内置CLI及复用它的Kimi/Codex bridge在显式受管project/launch且有TALK_ROLE_SERVICE_CONTROL_FILE时，监听本launch对应的绝对控制路径；文件名遵循宿主同一sanitize规则。旧手动入口或未配置控制环境不增加监听，非法明确路径拒绝启动；缺失/暂不可读/非精确shutdown内容不当停止。宿主仍是写停止文件、验证原Popen已退出并report的唯一归属持有方，bridge不清owner或采信外部PID。

停止监听有界读64字节、默认0.25秒轮询；正常停止先取消并等待本bridge连接/消息任务，再沿原finally取消任务worker、上报offline并关闭客户端。连接错误及外部取消仍传播并回收监听任务，不吞失败；在途CLI沿既有取消路径回收其自持子进程。该轮询不是终端MCP预算或服务端强停保证，HTTP/原生清理仍可能超宿主20秒，此时保持原stop_timeout与owner守卫。

## 运行器能力与网络恢复

服务端按`managed_cli`和角色状态允许启动请求；宿主另核三档、本人Key、选择/绑定指纹、实际入口parser、模型alias和原生隔离能力登记。按钮可用不代表原生能力已经验收。

内置Codex/Kimi/DSH配方使用真实仓库parser核argv。未知或未经人类核验的原生配方稳定拒绝；Codex/DSH没有可直接使用的模型参数或缺少本地命令模板时不猜参数。子进程只继承系统必要环境，其HOME/原生会话/缓存/临时目录按角色隔离，不自动复制认证目录。

客户端把连接、成功响应正文、HTTPError正文读取中的`URLError`/`OSError`/`HTTPException`转换成稳定宿主错误并关闭响应；`IncompleteRead`属于`HTTPException`而非`OSError`。完整HTTP错误码保持。监督器轮询及动作边界保留原句柄，允许后续恢复，连续相同读错误去重；`once`/`max_rounds`预算保持，不捕`BaseException`或`KeyboardInterrupt`。逐动作边界的裸本地OSError可能降级为`host_unreachable`，这是当前诊断限制，内部具体错误码和归属证明不变。

宿主默认HTTP超时15秒、就绪60秒、停止20秒、轮询1秒。这些是HTTP/进程预算，不能替代终端MCP等待预算；终端适配仍按 [TERMINAL_MCP.md](../guides/TERMINAL_MCP.md) 核验实际客户端上限和返回余量。

## 可选请求worker（R1-4b）

`serve --provision-worker`只接只读计划，另加`--provision-worker-apply`才真实消费人类配置意图；未开启时不加载worker。独立线程每次最多一轮，主循环非阻塞收集并继续poll/stop，worker不持有Popen。配置完成不自动启动角色，未知原生能力仍拒绝。使用与实际参数见[worker指南](../guides/ROLE_REQUEST_WORKER.md)。

每次请求前检查当前资格/取消和剩余IO预算；outcome=reported仅表示业务失败结果已送达，宿主CLI仍退出1。once/max_rounds退出最多两段有界grace、单段上限180秒，未结束请求停止并登记；完整Ctrl+C/宿主退出清理后续，不承诺强制回收未完成线程或绝对硬网络期限。原服务所有权、停止和有限等待合同保持。

## 页面行为

human可操作逐角色“启动/关闭”和“全部启动”；agent只读。服务状态独立于任务列表。`running`且`readiness_service=ready`才显示启动成功；关闭完成显示“未启动（已关闭）”，不显示启动失败；未知状态如实展示。

批量分别显示启动请求、已启动、启动中、跳过、失败。已运行或仍持有归属的角色不新建start；仅安全失败子集可重试，持有失败进程先关闭。后到失败更新原批次，后续stop/新动作取代旧世代时结束旧pending，不冒认异代成功，计数不重复。角色页离开、切项目或切账号即停止轮询并作废迟到响应。

## 验证与限制

#225已独立通过上一轮四文件功能/安全/前端变异验证；#226独立实跑host28项、服务55项，共83项，零失败/错误/跳过，另有真实回环4项与旧源码负向敏感性。Codex最终复查同一探针4项通过，负向harness2项通过：旧源码恰好检出5/6新增用例、9条测试/子测试错误，正常响应控制项保持通过。原失败、partial和沙箱管道错误不改写；不把这些套件重复累计成全仓新运行。

原Node194项沿用未变化源码证据；本片真实进程证据仅为临时DB、假Key、固定文本受控Python子进程及随机回环端口。真实模型版本、账号登录、原生CLI启停、多角色原生隔离、主动等待及真实页面尚未验收。未知能力稳定拒绝通过，不等于原生适配完成。人工步骤见 [受管服务验收指南](../guides/ROLE_SERVICE_ACCEPTANCE.md)。
