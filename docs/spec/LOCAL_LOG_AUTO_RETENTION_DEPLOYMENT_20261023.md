# 后台自动日志清理：正式启用记录

## 2026-10-23 20:53独立部署复核通过

319 DeepSeek独立复核为complete/pass，结果2960已于UTC12:52:34正式收取；未发现产品修正项。39份冻结/实际来源匹配，config/policy/state/新run/lease、API健康及新旧进程时序、仅DSH恢复/其它六最新实例offline、日周期与helper无sweep/伪造均通过。取件协调方再核远端与本地JSON及39份材料，证据coordination/319-acceptance.json；原独立报告/限制在review-deployment保持不改。

复核者未获Git旧对象导致旧config全字段独立diff受限；Codex补读取4d3d781旧对象自检，旧SHA与批准基线一致、解析差异仅批准字段、当前SHA3654bdc3…一致，未输出/保存旧配置。该补证只称协调方自检，不改写独立报告。原stopped快照健康数组5/7，独立复核另用旧WorkBuddy PID缺席补齐；旧解释器PID12344被新host复用，不作为旧进程不存在证据。

319实际原生回执new_no_candidate/reused=false，新session-48dfb7c1-20dd-42c7-a0b4-30599b5066a9/count1、基础合同SHA同315、末占用30.8189%；未续318，未强拼候选，原因只记录无候选、不推测根因。任务级claimed_by/instance/delivery均确认，复核实时实例仍idle/null而非预告working/319，不能写成已观察到working。

本片已正式启用并完成代码/首次部署独立复核：每日检查、启动补检，五已登记范围的30天保留/1GiB软预算，正常使用无需前台操作。首次生产0删除是保护缺证旧run；30天长期效果/未来容量/生产到期删除与410、其它成员/OS、私有输出仍未实跑。摘要HTTP200为partial，与后台容量complete分开。完整日志整项及真实主被动功能未在本片完成；下一切片另行明确确认。

## 2026-10-23 20:26加载核验（待独立部署复核）

用户已回复“已重新启动”。生产API健康ok、DB/storage ok；新统一runtime14584和七个新宿主serving。后台由API首次启动自行执行：UTC12:20:23.836218，完整盘点532,532,295逻辑字节（约508MiB），454个legacy_or_unclosed run全部保护，deleted_files/bytes均0，errors空，capacity_scan complete、未超1GiB；持久next_check=1792844423.836218，即次日UTC12:20:23。核验脚本没有调用sweep或手工写policy/state。

通过原human普通start只恢复原先running的DeepSeek：gen54、ins_057877d1df52、bridge PID8652，running/ready/idle；实际last_seen由UTC12:22:09推进到12:26:10，其余六角色保持原stopped/无owner。新bridge对应manifest身份/PID匹配，run.lease以WinError32拒绝第二可写句柄，closed不存在，证明新活跃写入器已加载；未停止它来制造关闭凭据。

真实人类日志摘要HTTP200、scope严格为本项目DeepSeek、返回2条摘要，scan.complete=false/truncated=true、scanned_bytes=133480910；它是部分查询，不能当全量日志查询通过。原host客户端5秒预算不足，辅助核验改用既有10秒扫描预算+5秒余量的15秒HTTP预算，实际约8.078秒；只改临时核验helper，未改产品超时/扫描限制。后台容量盘点complete与这项摘要查询partial是两个不同结果。

配置SHA仍3654bdc3…不变，根policy的五对project/member与批准配置精确一致。证据在coordination/deployment-{loaded,restored,heartbeat,producer}.json、deployment-producer-check.log；旧停服/配置应用证据保持。代码318独立通过，生产实际加载/保护/恢复证据交DeepSeek另做部署复核；不把自检或0删除说成30天长期容量验证，也不扩大五成员范围到WorkBuddy/manager。

## 2026-10-23 20:06执行状态

用户已明确确认启用及正常重载，并另行授权收取317。317已completed、原partial/2958不改。原无running任务、唯一DSH running且真实idle/心跳新鲜，其它六角色stopped；原统一入口正常drain后runtime/七manager退出、全角色无owner。未强杀或解除归属。

批准的配置已于UTC12:05:20应用，除下列已审字段外保持完全相同，新SHA为`3654bdc3c9a9c14d2435a9e6ada099de25e883e76c9e602a0e4cada73bf7012d`。只读构造预检1根/5范围/策略正确，未建线程/连接DB/sweep。现等待用户原终端重启external API，随后检查后台实际生效并仅普通start恢复DSH；其余六个仍停。配置落盘不等于已加载，生产policy/删除尚未执行。

以下为原审查方案及确认依据，保留时点语义；无需再问本片部署授权。20:06的API待重启状态已由上述20:26加载事实更新。

## 已完成的代码验收

2026-10-23用户通知318完成后，Codex核验33份冻结、原317证据未改、318结果2959与本地JSON一致；DeepSeek独立132回归/27新测试/5原反例/27复核侧反例通过，F1—F5/P1全部关闭。318已收取。取件后仅按复核建议澄清合同“新增事件”措辞，未再改产品代码。

额外真实API加载自检通过：正式lifespan启动后台worker，真实隔离SQLite任务闭环，自动删除40天旧事件，详情HTTP410，未认证401/agent403，近期/活跃保留，持久daily due，API关闭worker正常停止。测试端口59899，非生产8000；记录在`.tmp/local-log-auto-retention-v1/coordination/api-smoke/`。这不替代生产验证。

## 原部署前只读核对（20:00前）

- 当前storage.db_path为`./talk.db`，解析到现有`D:/claude-test/TALK/talk.db`；本片enabled门禁要求绝对路径。
- 当前只有五个已登记来源范围，分别为DeepSeek、Codex和三个Kimi成员，project均为`prj_e8fe7066bbec`。其root指向各成员子目录，而writer的根是`D:/claude-test/TALK/logs/runtime`。
- 全根清理按member/instance/run三层布局遍历，policy也必须在writer根生效；不能直接在成员子目录开启，否则无法正确遍历/协调writer。拟将五个root统一为原总根，保留这五对(project,member)，不新增WorkBuddy/其它成员范围。
- 当前统一宿主running，API为external（由用户原终端运行）。无法通过受管reload-api重载外部API，不按PID强杀/接管它。
- 当前无runtime_log_retention配置，生产仍未启用；未写root policy、未删除生产日志、未启停角色/宿主/API。

## 已批准并应用的配置差异（原方案）

`.tmp/local-log-auto-retention-v1/coordination/deployment-config.patch`只包含以下差异，内存中已解析验证与原配置相比恰为这些字段；没有保存完整私有配置副本：

1. storage.db_path改为同一文件的绝对路径`D:/claude-test/TALK/talk.db`，不复制/迁移DB。
2. 五条已登记runtime_diagnostics.sources的root改为`D:/claude-test/TALK/logs/runtime`，项目/成员不改；provider仍按精确project/member过滤，新增的其它成员目录不因此获授权。
3. 新增：

```toml
[runtime_log_retention]
enabled = true
retention_days = 30
max_total_bytes = 1073741824
interval_seconds = 86400
```

原配置SHA256为`b839cdea0ddfe0dd97e91af7ced2825da4557c7af8c2ed307095568d8d7bdc3f`，曾用作应用前CAS基线并已核对通过；UTC12:05:20已应用，当前SHA3654bdc3…，不再是待应用状态。

## 确认后按正常流程加载

1. 核各角色任务/持有状态并记住原running/stopped集合；有工作未结束时不强停或解除owner。
2. 通过原统一入口正常停止并drain宿主/角色，确保旧producer不再执行旧期限/容量删除。使用原归属/Popen流程，不用旧PID判定或强制CAS。
3. 应用上述最小配置，保留其它配置、模型/Key/绑定/历史。用户在启动API的原终端Ctrl+C后重新运行原命令一次；新版API将按既有绑定启动新宿主。
4. 普通start恢复原先运行的角色，原本停止的保持停止。验证新writer lease/关闭证据、根policy、后台持久due/摘要、五范围隔离与角色健康。
5. 生产没有已关闭且超过30天的可信run时，删除0个也是正确结果；不修改历史时间/伪造closed来制造删除证据。旧/未知/空任务run仍保护，1GiB软预算不能越过它们。
6. 记录实际加载与保护结果，必要独立部署复验优先沿318的同一原生会话请求，仍服从60%/失效守卫；不据一次启动声称30天长期容量验证完成。

## 确认及回退边界

本方案涉及生产配置和服务重载，按AGENTS“涉及新的部署/权限/破坏性处置时，仍提交具体可审结果后确认”要求，在用户确认前不执行。日常自动清理不要求用户逐次批准；这里是本片首次部署确认，不是新增前台流程。

若加载失败，停用新worker并恢复本次配置字段；不删除已写policy/lease/关闭/审计痕迹来强行恢复旧删除，不回填历史，不强制解除owner，按实际失败证据处置。启用后的writer会保守服从已有根policy，即使worker停用也不自动重开旧破坏性策略。

317原partial保留；自动审批曾拒绝收取，用户随后明确授权，现已正常收取completed，报告/失败内容始终不改。此事不改变318代码验收结论。
