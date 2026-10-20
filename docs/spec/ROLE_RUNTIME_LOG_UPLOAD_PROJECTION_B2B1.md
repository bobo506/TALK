# B2b-1 真实写入器上传投影与服务端适配

2026-10-20 17:25方向调整（优先于下方旧方案）：用户澄清桌面应用目标：日志保存在产生日志的设备，跨设备分析通过导出文件并手动转移即可；当前不继续联网集中上传/接收。286由创建者agent:codex调用既有pause-tree普通中止，控制状态paused，当前领取已撤销；原DeepSeek已回idle/无当前任务，服务未停。隔离产物233份约8.78MB保留原位，不收取/验收/集成。原284关闭内核及三张日志表保留，不删库/表、不启用接收；HTTP上传、跨机器来源及outbox移出当前排期。本轮只处理日志方向，桌面内部本地服务/数据库及聊天/账号同步架构保持，未派新任务。 本文原任务合同保留历史，不再作为当前执行授权。

2026-10-20 17:12：本片已作为独立顶层task286派agent:deepseek，创建queued/assigned。精确基线52467765dfee05ada9ed79bad7d282f2deaf38a8，175公开源/指定文档冻结，原包/manifest/回执在.tmp/runtime-log-upload-projection-v1/coordination/；仅deepseek/隔离候选可写，自测交付暂停后Codex实查/直接修正。生产接收关闭，HTTP/查询后续，不主动等待，用户通知后取件。

日期：2026-10-20。范围：已批准B2服务端范围内的首个投影片。先实现真实writer→版本化上传JSON→服务端严格校验/再次投影→B2a的PreparedBatch；后续串行补HTTP、来源接口、读取投影/查询，再B3持久outbox。生产接收仍关闭。

## 固定边界

- 冻结当前已提交的真实writer及B2a内核，不改writer、models、接收内核、配置/认证/路由或已有51项内核测试。本片仅新增投影/DTO及新测试，候选隔离，首次执行DeepSeek，自测交付即暂停，Codex独立实查/直接修正。
- 第一片支持role标准事件/异常及transition、queue_poll；manager只支持manager_round_snapshot。launch_process_snapshot、其它manager生命周期事件及任意其它extra本片明确返回422/unsupported_event或unsupported_field，继续保留本地，后续补齐归因后再纳入；不得静默忽略、改作另一类或报已上传。尤其launch_process原记录具有目标role/instance/launch而缺manager_run.host，不能按当前owner/scope补造完整manager记录。
- 不做HTTP、公开查询/游标、outbox、后台线程、网络/模型、启动服务或生产操作。不能把投影通过当认证/入库通过，认证/来源/双向实例launch仍由原内核事务重核。

## 版本与接口

新增server/runtime_log_upload_models.py及server/runtime_log_projection.py；导入不读server.db/auth/config、不建库/目录或网络。固定UPLOAD_SCHEMA="talk-runtime-log-upload-1"，投影版本复用core.PROJECTION_VERSION="talk-runtime-log-projection-1"，writer_schema为现有talk-runtime-diagnostics-1，不能混用原内核BATCH_SCHEMA作为HTTP协议。

公开纯函数：project_writer_record(raw_record, *, scope, limits=None, sensitive_values=())返回新dict；build_upload_batch(raw_records, *, scope, source_revision, writer_run_id, batch_id, batch_seq, limits=None, sensitive_values=())返回上传dict；prepare_upload_batch(body, *, limits=None, sensitive_values=())返回原core.PreparedBatch。scope使用原RuntimeLogSourceScope，limits使用原RuntimeLogLimits。不能在prepare中把任意客户端payload直接装入PreparedRecord。

批次JSON仅允许schema/projection_version/scope/source_revision/writer_run_id/batch_id/batch_seq/records八键；scope仅原project_id/host/subject_kind/subject_id四键。records为已投影对象列表；服务端每项再次校验类型、版本、归因、白名单及脱敏后创建PreparedRecord。来源/批次版本和序号使用非bool正整数，ID沿原内核上限；source_id由scope推导，不接受客户端额外覆盖。

| 记录输出字段 | 从真实writer映射及约束 |
|---|---|
| projection_version / writer_schema | 固定为上述两个版本；拒绝未知版本。 |
| writer_run_id | 原顶层run_id，不改成manager_run_id；批次内与包头精确一致。 |
| project_id / host / subject_kind | project_id须与scope匹配；host/subject_kind取显式scope；host只是来源标签，不宣称密码学主机身份。 |
| member_id / instance_id / launch_id | role与scope.subject_id匹配，须真实非unknown实例，缺launch保null；manager原member/instance为unknown且launch缺失，输出member=unknown、instance/launch=null。不从owner或PID补身份。 |
| manager_run_id / manager_run | manager从raw.extra.manager_run提取实际run及完整白名单快照，提升到顶层，host与scope精确相同；role这两字段为null。manager_seq允许started/terminal共序号，不要求连续。 |
| log_id / recorded_at | 保原值且校验合法ID/有时区时间；不能用mtime/generated_at/接收时间替代。 |
| event / severity / phase / stage / pid / runtime | 保有界诊断事实；pid为写日志进程，不当子进程或归属依据；类型严格，不将bool当int。 |
| task_id / message_id / returncode / timeout / cancel_category / related_log_id | 按真实可空字段校验保留；任务号与消息号不混用，取消按原分类保留。 |
| budgets | 数值键固定cli_timeout_seconds/http_timeout_seconds/task_lease_seconds/task_heartbeat_interval_seconds/managed_heartbeat_interval_seconds/task_poll_interval_seconds/ready_timeout_seconds/stop_timeout_seconds/host_poll_interval_seconds/provision_worker_io_budget_seconds/provision_worker_timeout_seconds/mcp_wait_seconds；值null或有限非负数。字符串来源键仅cli_timeout_source/command_template_source/mcp_wait_budget_source，有界且保unknown，不捏造已适配预算。缺键不补造已知值。 |
| integrity | 真实redacted/redaction_kinds/truncated/truncated_fields/write_complete五键；再次脱敏/限制要合并标记，不得抹掉旧红删/截断事实，不把损坏改为完整。 |
| exception | 可空；按冻结writer的真实type/type_module/type_qualname/relation/message/str_empty/message_error/frames/frames_total/frames_omitted/context_present/context_suppressed/has_explicit_cause/cause_chain/chain_depth/chain_truncated/chain_cycle逐项严格投影。主异常和cause结构区别按实际writer保留；帧仅公开文件basename、line和function，source文本明确排除。复用现有16链/2048帧/16KiB异常文案上限，再遵守单条字节总限，不回传原始命令/输出。 |
| transition / queue_poll | 从extra同名键提升；transition固定冻结timeline的8键；queue_poll固定279的12键与状态/时间/序号/30秒间隔语义。不是任意extra透传。 |

输出记录只含表列键（可空项统一为null），没有raw extra/message/run_id/segment_file、内部路径/argv/env/原生stdout/stderr/认证/owner字段。原始writer允许并明确剔除顶层message/segment_file及异常frame.source；其余未知顶层/嵌套键拒绝，不能靠不断删掉报错字段假称兼容。所有文本再次使用既有sanitize_text及已知敏感值脱敏；路径字段只留basename，防止Windows/UNC/正斜杠泄露。不得修改输入对象。

## 预算与验收

最多200记录，最终完整上传包UTF-8实际编码不超过4MiB，每条完整投影记录不超过256KiB；不能只量payload或字符数。采用非递归或受控遍历先防循环/深度/节点/键/字符串越界，拒绝NaN/Infinity/非法Unicode/重复批内log_id，不能先无界json.dumps后才限长。处理预算10秒，超限/超时明确413/503，不能成功空包或悄悄丢条。其它形状/版本/归因错误沿RuntimeLogReceiveError给静态422或409，不回显原payload/Key/路径。

测试必须由冻结RuntimeDiagnostics/StageTimeline/QueuePollRecorder/LoopEvidenceRecorder在本片隔离根生成真实记录，不能只手写一个“兼容”小字典。覆盖role正常/异常/空str/cause/context/含敏感值与帧路径、真实transition/queue_poll的开始失败恢复取消、manager真实started/terminal及长序号；writer run和manager run不同须保留。明确验证launch_process/其它manager事件被拒，未声称全宿主日志上传已完成。

另外覆盖上传对象再次篡改未知字段/假scope/假host/版本、manager哨兵/角色launch、深嵌套/循环/大量键、256KiB/4MiB的中文多字节边界、200/201条、输入不变和导入无副作用。用隔离合成SQLite/合成Key及原内核做投影→注册来源→ingest→同批重放/换批事件去重验证，并复跑原内核51项；生产来源/DB/真实Key/实例/模型/服务禁止访问。

交付应含实际映射逐字段表、由真实writer生成的合成fixture、候选差异/测试命令与原始失败、已支持/明确拒绝及待后续范围；不要把本片称为HTTP接收/查询/真实上传完成。
