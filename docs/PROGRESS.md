# Project Progress

Updated: 2026-10-27 15:05（Asia/Shanghai）。用户明确派大K开发新建角色至正常启停的完整流程、Codex复核；347已领取开发，候选隔离，待交付核验。

## 当前状态

- 347「完善新建角色到正常启停的完整流程」按用户明确分工交新大K开发、Codex独立复核；派时queued/assigned，随后只读核到running/in_progress、原ins_b3f454d21921领取。首正式开发任务，不另派模型测试；不因领取就认定模型任务成功。
- 347隔离根`.tmp/role-creation-complete-20261027/`，474项baseline/candidate源字节一致，base `de90147445408996df996ff233ff4aec5549bdfa`、manifest SHA256 `581d8c7535419b52c75ec34dba290580feca0a02cefcc6157ff02f86c4018073`，排除config/Key/DB及临时产物。大K仅修改candidate和delivery，baseline及正式产品暂停；要求保存关闭/刷新、自动配置与必要授权引导、模型及宿主、正常启停和可靠状态，优先打通Kimi并核实其他运行器，不能虚称支持；运行器名称修正含本片，删除清理及版本提醒仍后续。
- 派发未返回主动跟进句柄，当前连接仍not_bound、等待预算未核；按用户通知后取件并由Codex核验，不用轮询冒充主动跟进。未生产加载或改生产服务/配置，344/2990仍失败未收取。

- 用户确认新大K启动成功。核服务最初gen1/ready/idle；按用户既定开发分工，将新member的宿主task_profiles设为tools，其他配置值保持，正常stop原runtime23268并确认原进程退出，重启runtime23792六宿主serving，小D依原true/rev1自动ready；大K因原自启动false在重载后停止，已按用户原运行状态正常启动gen3，实例ins_b3f454d21921 ready/idle，实际宿主命令权限为tools，心跳推进30秒。未改角色启动偏好，未派任务或调用模型；native_login公开状态仍unverified，不能以ready声称实际模型任务已验。

- DeepSeek独立复核345的完整报告结论不通过，提出四项必须修正：provider与当前绑定核对、同名模型公开参数冲突、异常结构受控失败、角色可写权限配置边界。正式结果2991已核验收讫completed；MCP业务结论unknown，收取不等于通过。本人22/27 Python通过，5项受ACL限制未运行；42项Node进程内通过，原node子进程EPERM保留。报告位于`.tmp/kimi-role-onboarding-20261027/review/REPORT.md`。
- Codex在`.tmp/kimi-role-onboarding-fix1-20261027/candidate/`集中修正四项，最终33 Python及75 Node合成测试通过；一次中间测试因预期错误文案改变失败，调整后通过。新快照474份、排除了先前基线包含的合成测试数据库等，manifest SHA256 `5a7f5cbbb14a5fea5ebcf8e48e76b5ae4cba004676186690a071369e80b45c7b`，相对清理后旧候选只改五文件。原345候选、清单、报告及失败保留。
- 346/2992核验收讫completed，完整报告条件通过/无新增必须修正；本人30 Python通过、3项ACL not_run、75 Node进程内通过，标准Node runner EPERM保留。Codex对同一固定快照补跑3项全过，属协调方证据。复核后474项零错配/零extras；MCP业务结论unknown保持。原生登录/模型及浏览器人验未做。
- 七个受审文件已按前后SHA集成，HTTP页面与源匹配；未真实登录/运行模型。移除新增角色可写task-profile，沿用宿主逐成员配置默认review，新成员开发权限需配置；不声称同账户信任边界已加固。
- 页面active/version7，但当前Codex连接effective not_bound；346派发无主动跟进句柄，实际客户端上限和明确等待预算未核，不能声称该连接已启用主动等待。按用户通知取件；不猜测缺配置、未重载或宿主限制为确切原因。
- 原runtime19744正常stop --wait先超时，随后自行complete/absent；新runtime19376启动后四旧宿主各失败3次，小D离线。用户授权后，仅核本次脱敏后台事件及错误末尾的固定类型/位置：宿主确已启动但私有健康文件临时创建CreateFileW错误5，非创建进程失败。四目录在当前进程的同函数私有临时文件探针均成功且已清理，进程token显示未受限/已提权，具体差异未明，不声称根因已彻底确定。19376正常stop成功/absent；同入口重启runtime940仍四宿主失败，940亦正常stop成功/absent，两个新宿主入口退出。API仍由用户原终端持有；需用户在原终端按原方式重启API，让既有启动链恢复后台，再核实六宿主/小D与偏好。未放宽ACL/强杀/清锁/读取原生会话或密钥内容。344/2990及250/286保持。

- 用户重启API已确认，healthz正常；但新API PID22288启动事件显示在launcher.lock打开时PermissionError，后台仍停/小D离线。API进程低完整性RID4096、诊断进程高完整性RID12288；锁ACL未修改，诊断进程只读取得并释放锁成功。低完整性解释API不能写较高完整性对象，但此前四宿主异常的具体原因仍未最终证明。

- 第二次用户重启后API PID20124仍低完整性RID4096，后台未恢复。已核`D:/claude-test/TALK/.venv/Scripts/python.exe`继承Low标签；同一次探针系统Python RID12288、项目venv Python RID4096，四旧宿主argv首项正是该venv Python。经恢复授权，在后台停止、持正常启动锁时原子替换原清单，仅将四项宿主argv首项改为同版本系统Python；其他JSON值经语义比对不变，不修改ACL、角色绑定、Key或自启动选择。已验证系统Python能从原venv site-packages导入uvicorn/fastapi/sqlmodel。

- 用户按系统Python加venv依赖重启后，runtime23268 running、startup complete、worker无错、六宿主serving；小D原true/rev1自动gen88、ins_35a60b11066b ready/idle、同实例心跳推进60.099秒，其他五角色false/rev0及停止，旧大K停止/无owner。六绑定bound；API健康、HTTP页面与源码字节一致，无running任务；250/2767未收取、286 paused、344/2990未收取保持。active7且本Codex连接not_bound。未真实Kimi设备登录/模型或人工验收。

## 下一步与约束

- 用户明确后续目标：实现从新建角色到可正常启动、关闭的完整闭环；角色保存后完成各环节配置与加载，包含必要授权、所选模型、宿主和启停，状态须如实显示，见[路线图](spec/DEVELOPMENT_ROADMAP.md)。现由347隔离开发，尚未交付或验收。
- 用户澄清新建角色原应完成配置：经核原方向含一键配置/原生登录引导，早期交付只自动配置TALK侧而不含真实原生登录，后续Kimi独立宿主未补齐独立登录/模型准备，属于原有闭环未完成，近期setup仍需手工。另登记保存后关闭页面、自动刷新、不要求手输命令，见[路线图](spec/DEVELOPMENT_ROADMAP.md)；必要的用户授权仍需进行。
- 用户反馈新增角色时Kimi Code运行器名称仍包含K2.8等模型名称，不正确；后续核查并修正，见[路线图](spec/DEVELOPMENT_ROADMAP.md)，本次仅登记。
- 用户反馈删除大K后资源清理失败且重试无效；后续核查新角色是否复用身份档、专属凭据、状态及启动配置，确认专属且不复用后删除时直接清理，并修复清理重试，见[路线图](spec/DEVELOPMENT_ROADMAP.md)。这是用户反馈，尚未独立检查或实施清理。
- 用户登记后续需求：检查TALK适配的运行器是否有新版本，发现后仅提示用户，不自动下载、安装或更新；具体范围和排期开发前确定，见[路线图](spec/DEVELOPMENT_ROADMAP.md)。当前不开发该功能。
- 新大K已由用户确认启动，开发tools权限已配置加载；后续通过正常开发任务验证，不单独派模型验证。项目venv Python仍为低完整性，继续沿系统Python及原venv依赖启动方式。
- 新角色的工作区开发按用户原授权继续；不自动重派344，不自行启停或清理归属。真实服务加载、模型调用、主动跟进和页面人验均尚无本片通过记录。
- 历史见[历史](PROGRESS_HISTORY.md)。
