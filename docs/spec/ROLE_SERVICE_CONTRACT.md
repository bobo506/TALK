# 角色受管服务合同（R1-3）

状态：2026-10-12，223–229代码复核与页面反馈补正完成并收取，用户本轮页面基础验收通过。2026-10-13，235–237默认关闭的请求worker接线独立通过，真实原生运行器及完整创建页面仍未验。原设计见 [ROLE_LIFECYCLE_DESIGN.md](ROLE_LIFECYCLE_DESIGN.md)，实施顺序见 [ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md](ROLE_LIFECYCLE_IMPLEMENTATION_PLAN.md)。

## 范围与执行者

R1-3实现服务意图、宿主claim/report、实例就绪、逐角色启动/关闭和项目全部启动。服务端不创建或停止进程；`scripts/role_service_host.py serve`是受管子进程的常驻持有者。启动TALK、启动管理器、保存配置均不隐式启动角色。脚本`start`、`stop`、`start-all`只写请求，`status`只读；短命请求进程不持有子进程。

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
