# 删除角色人工验收缺陷修正（2026-10-24）

2026-10-24 23:43：329定向独立复核complete/2973已核验并收取completed，无必须修正项。产品不追加修改；正常加载及两个真实角色删除仍待按[具体方案](ROLE_DELETE_USER_FIX_DEPLOYMENT_20261024.md)确认，尚未执行。原始阶段叙述按时间保留。

## 329 独立结果与协调方收尾

正式裸JSON通过talk-delivery-1校验，task_id=329、作者agent:deepseek、Task Hall与2973一致，且与本地delivery.json逐字段等值；不是从runner succeeded推断通过。UTC15:42:57.123595已正式收取completed。

取件重算79份/2964423字节新快照零错配，源77匹配/AGENTS与PROJECT_BRIEF两份预期协调文档漂移；原50份/2074815字节、64份/2581366字节快照零错配。产品/正式测试与4ef58bc没有差异，329的15份/190160字节报告、脚本与日志另存coordination/329-original-review/，保留原API严格步骤探针失败及Python环境失败，不扫描isolated合成scratch。

| 独立检查 | 实际结果与边界 |
| --- | --- |
| 历史实例/managed复证/轮换严格/pending租约核心 | API8项通过；另1项严格步骤顺序/身份形状探针失败，列为P3并保留原失败 |
| 实际大树、无进展/占用失败、配置内存/幂等 | 5/5通过；240文件在80操作预算下7轮pending、最后complete。配置发布两项用普通临时文件/Python复制替代，未独立证明真实私有ACL原子发布 |
| 独立整页JS | 8/8通过；行和计数消失、设置回退、多墓碑/失败重试、非human及项目/账户/revision隔离 |
| 规定Node六文件 | 82/82通过，进程内真实JS/合成DOM，未真人浏览器验收 |
| 规定完整Python九模块 | 283项中271通过/5失败/7错误；ACL、CreatePipe、子进程启动/teardown限制，不能称独立283全过。定向58已包含，不重复累计 |

三项非阻断观察按用户优先完成功能的约定留档，不因此开启新返修：pending报告尚无严格步骤前缀/identity形状校验，但仅受信human/runtime可持有效租约报告，complete仍独立校验；provision锁失败可能将manager步骤标失败而非profiles，但cleanup_busy/文件保留/不自动循环正确；后端保留pending墓碑供清理区使用，用户可见常用角色列表已经排除，不能把“列表消失”解释成立即删库。原327/328的P3与限制保持。

329实际new_no_candidate新窗/count1/session-6f404675-b02c-411d-90e6-836fb2e2897d，没有续328。初始context_status=unavailable/no_candidate；末snapshot可用381537/1000000=38.1537%。这些来自任务公开execution_session_state，不读取私有会话补数，也不倒写原报告的“无占用声明”。

协调方另以公开接口核七个角色完整binding/binding_state与派前逐字段相同（含WorkBuddy已因用户原删除而为null），286仍queued/accepted/paused，DeepSeek原实例idle/无任务。独立复核者仅证明未触碰生产，没有独立实时查询这些保护；两类证据分开记录。本轮未启停/加载或再次delete/retry，原生Key/生产配置/DB/私有日志未读取。

证据：review/report.md、checks.json、原始logs；coordination/329-received.json、329-formal-delivery.json、329-pickup-verification.json、329-collected-raw.json、protection-after-review.json和329-original-review/manifest.json。下一步仅按具体加载方案确认，选择性自启动未批准、不实施。

用户实测旧 K2.8 Preview 提示“仍有在线或状态未确认的实例”，WorkBuddy接入验证提示“清理中”后“清理失败”，要求确认删除后即从角色列表消失。本轮是已授权删除切片的使用缺陷修正，由 Codex 开发、自测，DeepSeek 独立复核。选择性自启动尚未获确认，继续留待后续。

## 实际对象与只读诊断

本轮对象为 `agent:kimi-code-k28-preview` 与 `agent:workbuddy`；不是另两个独立角色 `agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c`、`agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314`。诊断只用原 human 凭据正常认证公开角色/实例 API，并按公开 PID/创建时间读取 OS 进程元数据；不读取生产配置正文或摘要、角色 Key、数据库、私有目录或原生会话日志。

| 用户现象 | 证据 | 原因与修正 |
| --- | --- | --- |
| 旧 K2.8 无法删除 | 服务 stopped/无 owner；14 条公开历史实例均 offline，无当前任务；原进程 13 absent、1 previous_boot | GET 将过期心跳投影为 offline，删除守卫却仍按原存储状态拦截。仅对心跳超过90秒、同机、有效 PID、无当前任务且 OS 证明原进程已退出/复用的历史实例放行；不改历史状态 |
| WorkBuddy 清理失败 | 用户的删除已建立墓碑/归档并清除绑定；revision2，manager/profiles complete、credentials preserved、private_state failed、startup_config pending；error=cleanup_budget | 单轮120秒/4096操作预算被当作整个删除失败。已有实际文件删除进展时返回 pending，释放租约，原运行器下轮自动领取同一墓碑继续；无进展、占用、归属或路径错误仍失败 |
| 清理期间仍占角色列表 | 旧页面把 pending/cleaning/failed 墓碑继续显示为角色 | 后端接受删除即从常用列表排除；单独“已删除角色的资源清理”区域显示进度/失败/重试，设置选中时仍跟进清理；完成后去掉清理记录 |

公开证据为 `.tmp/role-delete-user-fix1/public-before.json`、`public-process-proof.json`、`protection-before-review.json`。WorkBuddy 的两条历史原进程也均 absent，共16条原进程已退出。仅凭公开投影无法恢复旧数据库原状态；原状态误拦由普通代码及隔离反例验证，不声称读取生产库证明。

## 保持的约束

- 新的历史实例例外同时用于删除事务内的独占身份证明。`prove_exclusive_identity` 默认保持原严格行为；只有删除显式启用，Key 轮换不放宽。新鲜/未来心跳、远端/缺 host、无 PID、未知状态、活动任务或 OS 无法证明退出仍阻止删除。运行服务、待领取启动、未闭环任务/定时任务/配置请求的原守卫保留。
- 分批不是不受限循环：每轮仍120秒/4096操作，原180秒租约及普通drain25秒预算保持；pending必须 manager complete、存在待办且无失败项/错误码，报告后清空 token哈希/到期时间，下轮签发新租约。旧token/旧revision不能回写；无实际删除进展的预算失败仍需显式重试。
- 清理仍限定专属档案/凭据/私有状态/启动映射，原路径、句柄、reparse/hardlink、共享登录及模型保护不变。配置原子替换成功立即更新内存配置，避免发布后的临时文件清理预算造成磁盘/内存不一致；已不存在的资源先幂等跳过。
- “角色已移除”表示项目访问/任务入口和常用列表已撤销；专属资源是否清完单独如实显示。用户最新要求取代原“清完后才从列表消失”的显示规则，不能把排除列表当作物理清理完成。
- 其它五个角色的完整公开 binding 与本次诊断开始时一致；两目标之外的身份/Key/模型/历史/日志不改。WorkBuddy 的绑定清空来自用户原删除，不是修复过程改动。286仍 queued/accepted/paused。

## Codex 自检与状态

| 检查 | 实际结果 |
| --- | --- |
| Python最终相关组合 | 283/283通过，零失败/错误/跳过，187.896秒 |
| Node最终六个页面组合 | 82/82通过，零失败/跳过，5.499秒 |
| 原始反例及中间失败 | 修前4项为3失败/1错误；首轮55项53通过/2失败，揭示独占证明重复拦截；后87项通过。整页夹具首次81/82，修正DOM ID后最终82通过。原日志均保留 |

283包含删除/清理、项目角色、轮换独占、runtime/服务、任务队列/绑定快照及实例回归，不把重叠定向87再次相加。新增覆盖真实 Windows 临时目录大树分批及真实隔离 TestClient→TalkRuntime 自动多轮→名册消失闭环；不是只断言 mock 返回。Node执行真实整页 JS 的删除响应、角色行消失、设置回退和后续轮询完成。隔离服务导入统一由合成配置 wrapper 拦截，未打开生产 config.toml。

总计365项为协调方自检，不替代独立复核。原327 partial/2971、328 complete/2972、原50/64快照及原审查报告保持。本轮只修代码/隔离验证，没有再次提交两目标删除/重试，没有启停或重载生产 API/runtime/宿主；静态文件刷新可能读到v3页面，但后端/清理器仍须复核后正常重载，不能称两个真实角色已成功清理。首次加载事实仍见[原加载记录](ROLE_DELETE_DEPLOYMENT_20261024.md)。

独立复核材料在 `.tmp/role-delete-user-fix1/` 新冻结，唯一复核写根为其 `review/`，不覆盖原报告。派发后产品暂停；默认用户通知完成后取件。具体生产加载按可审结果另行确认，不沿用上轮重载许可。
