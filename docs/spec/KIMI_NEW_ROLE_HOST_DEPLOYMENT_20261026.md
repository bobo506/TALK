# Kimi新角色与339修正的正常加载方案

2026-10-26 21:26（Asia/Shanghai）准备；尚未执行生产改动。本次服务停启需明确许可，先前用户授权为取339报告、核验后收取，并明确本次先不重启。340至343必要返修已处理，当前没有新增必须修正；实际加载、当前宿主T/W/I-4及真人验收分别后置。

## 已有审查结论

- Kimi宿主/页面反馈e3654e3，健康发布与stop/drain返修ffa4be5：341产品缺陷独立通过，342关闭复核包M2-1。用户免单独K3.1模型验证，保既有角色与选模。
- 339显式flow接入及stop/collect竞争返修0a63b3bda08085fb97f2647c96736ecc341db7ed：343/2989完整报告已核，两项独立通过、无新增必须修正。本人243项0F/0E；6真实stdio因CreatePipe受限为6E/not_run，协调244含6stdio过仅作协调证据。正式执行回执new_force_new/count1、末24.4864%，不以创建null证明新窗。
- 343原13份70248字节普通报告/日志/JSON已逐项归档，原339 partial/过程偏差、旧6stdio限制及其它环境失败记录保持，不清理后称原始。

## 只读预检

证据根D:/claude-test/TALK/.tmp/kimi-role-host-deploy-20261026/。

- 原runtime18784，UTC02:17:38启动、api_mode=external、running/present、shutdown idle；原五宿主serving，DeepSeek实例18580当前空闲；本次没有running任务。
- API的OpenAPI未含/api/tasks/followup及/api/tasks/{task_id}/collect-followup-result，须用户原终端正常重启API才能加载已审服务端代码，统一入口不接管该API。
- 小D随项目启动仍true/revision1，其余五角色false/revision0，包含大K。保用户选择；本次只对大K进行普通首次重试，不代勾选自启动。
- 大K member=agent:prj-e8fe7066bbec.k-4bf013b9，choice=rmc_04e11ae89092，alias=kimi-code/k3.1-pro，gen1从未claim、到期readiness_timeout、无owner、can_start true。保原失败历史，普通请求下一代启动，沿原角色，不重复创建。
- D盘tracked源码清洁；已生成combined-reviewed-0a63b3b.patch及15文件固定前后SHA计划，git apply --check返回0，尚未应用。274个代码/正式测试/页面路径的计划内容与复核基准一致；未改文件有164处仅LF/CRLF差异，保其原字节。原raw字节比较未通过记录保留，不能把规范化内容一致冒称274原始字节相同。
- 拟在停机后仅按固定SHA集成15个已复核公开源码/文档文件，保其它文件及用户untracked的.talk/原生环境。集成后15文件逐字节匹配受审源、其它代码内容相同。

## 本次配置差量

仅修改仓库外原runtime清单：kimi.enabled=true，kimi.task_profiles[agent:prj-e8fe7066bbec.k-4bf013b9]=tools。已用真实公开DTO做纯host_spec规划，精确member/choice/alias及tools命中；未调用模型或修改清单。原hosts静态配方、WorkBuddy工厂、API/worker/路径与其它设置保持。凭据只由原入口按原路径正常消费，不打印/复制/哈希Key正文，不复制原生HOME/会话或凭据。

## 获许可后的顺序

1. 重核无running/角色busy及源/配置未被人修改；运行原普通stop --wait，保持现有忙保护。若blocked/超时，保留原句柄与错误现场，不强杀/CAS/清锁、不启动第二个后台。
2. stopped确认后核原已记录后台/宿主与DeepSeek自有入口退出、角色释放归属；只管理TALK本次持有的入口，不新增运行器内部原生进程树管理。
3. 集成15文件及配置差量；前后SHA/语义差量核验，Git仅提交本次具名源码与必要协调记录，不接触用户.talk/私有资料或旧快照。
4. 提醒用户在原API终端Ctrl+C，再用原命令重启。操作前确认后台已停止；不另开API或代管外部进程。
5. 用户确认API已重启后，先只读确认新路由及由原本机绑定自动带起的新后台；若未自动起，只在证实无旧管理器后用原attach-api/detach入口恢复一次。观察小D依原true选择自动恢复，不重复start；新Kimi宿主serving后，对现有大K普通start一次。
6. 核API健康、后台/宿主、角色ready与真实心跳，原六binding/要求/模式passive6/自启动选择/250 failed及2767未收取/286 paused保持。旧关闭及gen1失败历史保留。若原生环境/登录/CLI版本拒绝，如实给出正常配置入口，不复制凭据或冒称ready。
7. 请用户刷新页面验收大K启动/创建反馈。后续首个正式开发任务交该新角色；本轮不另派K3.1模型验证，也不把服务ready当提供商内部模型证明。

当前Codex连接或其它宿主的T/W实际加载与I-4尚未验，本次保passive/version6；不借本次后台正常加载把项目全局主动能力宣称全部完成。341至343归档/新旧快照仍保留，原D339源在获得本次加载许可前保持现状。


## 2026-10-26 21:58 执行回执

用户已明确授权本次正常加载并启动大K。旧18784首停blocked/host_stop_timeout后由原后台自行重试，UTC13:39:52 complete/error清空，12个已记录原入口全absent、全角色无owner。15个受审文件已按SHA集成，kimi仅新增enabled与大K tools，其余配置内存比较相同；无凭据副本/正文哈希。用户在原终端重启API后自动带新runtime19744（UTC13:48:44），六宿主serving、startup complete、shutdown idle/空错误、worker无错。原API由用户原终端管理，未另起API/第二后台。

小D原true/rev1自动gen84/ins_8b6f2d624400/PID12392 ready/idle；大K原角色仅一次普通start到gen2/ins_6ea3a5aecdd7/PID13912 ready/idle；两次公开同实例心跳推进330.686/330.504秒。其余四角色保持停止；大K自启动false/rev0也保持。六绑定/角色配置/用户自启动偏好与加载前相同，250/2767/286公开保护字段不变，模式passive6。真实HTTP role-creation.js与当前源字节相同（SHA eb2fcea7917cce43f922483321db7eee4dd4f8ebcf98a82a35e40552702753fd）。

正常加载自检完成，实际页面人验待刷新。未另派模型验证，不把服务ready当实际模型执行或T/W、I-4通过。证据位于既定部署根execution/，原blocked回执/12原PID创建时刻/源与配置差量/一次start/最终检查/心跳均保留。当前授权用于本次加载已执行，后续不重复停启；下一正式开发优先交新角色，需保持当前里程碑验收边界。
