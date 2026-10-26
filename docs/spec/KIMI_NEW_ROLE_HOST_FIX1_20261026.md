# 340集中返修：健康降级、复核隔离与证据权限

340正式结果2986的自由文本报告为“必须修正/补证后复审”，MCP业务结构化结论仍为unknown。Codex已读完整结果及报告，正常收取为completed仅表示交付收讫，不表示独立验收通过。原19份249616字节普通交付逐项归档到D:/claude-test/TALK/.tmp/kimi-role-host-fix1/pickup340/340-original-review，未归档合成DB或私有ACL临时目录。实际执行为new_no_candidate/count1，末投影38.0217%；不输出或复制原生会话标识。

## MF-1：健康发布不得挡住停止

原publisher在claimable_actions之前失败，导致父serve把本轮动作当空列表，既不领取本人的stop，也不能在空句柄时drain。新代码先确认空句柄drain，健康发布改成非致命降级；每段连续失败只给一次固定错误码，不回显异常正文/路径，恢复后重置降级标记。本人stop及作用域过滤保持，活Popen句柄不释放、不因健康失败退出管理器；最终stopped健康发布失败也不把正常退出改成失败。

3个新增故障注入在修改前为1F/2E，修改后连同宿主/运行时共30项通过。覆盖持续健康失败时本人stop仍可返回两次且句柄保持、空句柄drain、主入口最终健康发布失败仍返回0；错误诊断固定且连续失败只一次。日志为本片coordinator/logs/mf1-before.log和mf1-after.log，原失败保留。

## MF-2：新建干净基准，不改旧证据

旧v1的286份10253562字节清单匹配且无额外文件；旧v2的294份10338896字节清单仍全匹配，但目录有100个额外文件。旧副本/清单/探针/失败记录保留原状，不能再说旧v2目录纯净。新包在D:/claude-test/TALK/.tmp/kimi-role-host-fix1/，采用新的baseline及baseline-manifest.json，不覆盖旧包。

新package/run_checks.py在导入server前固定合成配置、外部TEMP和诊断日志根，重定向RouteTestCase的临时目录，测试前后检查精确文件集合/哈希/额外目录/reparse，不读取未知多余文件的内容，也不跟随reparse。测试入口先在门控进程中等待，再分配到本次Windows Job后启动；结尾只清理该Job里自建的合成子进程并核对active=0，不枚举/操作其它进程。Job不使用breakaway或任何权限绕过，不能分配时保留not_run_or_incomplete。独立小探针已证实残留的1个合成子进程收敛到0，文件增加/篡改/缺失均可被检测。包内smoke只用合成文本和睡眠进程，无模型调用。

规定复核命令见包内package/REVIEW.md。默认仅3个故障注入、71个服务及2个静态页面Python测试和两组Node页面测试；不要求在已知受限环境反复跑私有DACL失败的整个套件。额外无子进程探针也必须在review内，设置日志/TEMP根，并沿合成配置注入。

## MF-3：区分协调自检与受限复核

旧190Python/40Node是Codex正常用户权限、合成配置自检结果，不能当DeepSeek沙箱全过。340本人实测Python190项28F/17E/0skip/exit1，Node40项exit0；另71项服务独立通过。私有DACL发布os.replace在其受限token下WinError5，普通replace对照成功；另有API子进程启动环境限制。原45项失败/错误与ACL证据不删、不改断言、不降低产品私有权限守卫，340本次结论保留partial/必须补证。通过plain publisher的逻辑探针不能证明私有DACL通过。

本次同一新wrapper的协调方完整关联结果、受限环境定向结果和逐套件清理/快照信息分别保存在coordinator独立目录；最终计数以相应outcomes.json与完整日志为准，必须标清执行者/权限，不冒充DeepSeek本人全量运行。本次定向复验只补MF-1/2/3及必要兼容，不重审所有非阻断建议。

## 范围与加载边界

顺带按340非阻断观察修正文案：宿主配置关闭时提示先开启，不承诺自动处理；只读刷新仍不重复创建或启动。未新增配置/报告模型并列展示、进程树管理、真实模型验证或权限放宽。

生产尚未集成/加载；大K原member/choice/gen1失败记录与其它角色/绑定/自启动选择保持，不重复创建、不复制其它角色凭据。原runtime18784、外部API、339原产品/295冻结及其未收取交付、250/2767/286均不由本次返修操作。独立通过后再准备具体正常加载方案、显式kimi.enabled及大K逐成员tools配方、普通start重试，不强杀/CAS/清锁/另开API。本次复核不是用户不需要的K3.1模型验证，后续首开发任务交新角色的授权保持。

## 本次协调方实测结果

新wrapper候选副本：workspace-write受限环境定向76Python/41Node全过；普通当前用户权限完整193Python为192过/1E/0skip、41Node全过。唯一E为原有test_explicit_detached_entry_has_no_console_and_preserves_restart：产品detach请求CREATE_BREAKAWAY_FROM_JOB，本测试Job禁止逃逸，Popen创建被拒。未开启breakaway或改断言，完整套件仍为partial。两轮源文件集合和SHA前后均干净，Job结束active=0；另synthetic漏进程探针1→0，文件额外/篡改/缺失反例均检出。执行者与权限、原日志索引见coordinator/evidence.json，不能写成DeepSeek本人全过。

候选副本是返修中验证点，保留不覆盖；正式baseline在提交后重新生成，须比对全部产品/正式测试/页面字节与已测候选相同。新wrapper另校验外部package脚本与baseline内固定副本字节一致；派发前会再跑定向验证这一守卫。原D339的295源/冻结和332至338旧归档清单重新核对零错配，四协调文档的既知差异保持。
