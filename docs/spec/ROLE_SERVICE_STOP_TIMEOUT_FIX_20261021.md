# DeepSeek异常退出后的关闭超时与单次恢复

2026-10-21（Asia/Shanghai）。用户报告点击DeepSeek关闭后一直“关闭中”，明确确认修复关闭超时反馈、暂停任务误阻挡，并只对DeepSeek进行单次已关闭恢复。没有新TALK任务/派发、角色启动或其它角色恢复。本轮由Codex直接实施与自检，不称为其它执行者的独立复核。

## 实际问题与授权边界

- API已恢复，但旧manager11612和bridge12284均已退出。19:20:19用户提交stop，generation24、动作`9abffcb4-d485-4f14-9073-a69811da0587`一直pending、无人claim；19:22:19截止后，19:22:59公开GET仍为stopping/pending。
- `expire_due_launches`在控制动作中收敛，GET是只读投影，不会触发该写入；投影只处理running失联，没有处理stopping过期，导致页面无限关闭中。不能据此声称进程仍在退出。
- 原人工恢复守卫把所有queued/running任务都当活跃；286实际为queued、control_status=paused、自身根、无parent/claimed_by/instance/claim_token/lease，却仍阻挡恢复。用户要求保留286暂停，不取消、恢复、收取或集成该任务。
- 用户确认本片包括必要验证/加载和DeepSeek单次人工恢复，不扩大为自动清理归属、恢复其它角色、启动DeepSeek或新功能派发。原API/恢复权限、精确代次和原start/实例/host校验保持。

## 产品补正

1. `server/role_services.py`：当前同角色/项目/代次stop仍为pending/claimed且超过截止时，GET投影为unknown、`stop_timeout`和明确中文核实提示。数据库及原stop动作不改，旧归属继续保留、启动仍受保护；恰到截止仍按既有边界等待，旧代次不得影响新代次。
2. `server/role_service_recovery.py`：仅排除明确paused、queued、自身根、无parent、领取凭据/实例/租约全为空的任务。SQL使用`IS NOT TRUE`，缺控制状态/根身份的NULL不能误被排除。running、pause_requested、普通queued、子任务或任何残余领取均继续阻断。plan到apply间任务恢复active也阻断。
3. `web/workspace.js`：超时显示“关闭超时（状态待核实）”，提示检查原宿主、确认停止后人工恢复；不误称启动失败或已经关闭，继续轮询到真实恢复结果，不自动发start/恢复请求。`index.html`更新workspace缓存版本。

## 自检与失败证据

| 范围 | 最终结果 |
| --- | --- |
| 生命周期、人工恢复、恢复CLI | 90 Python通过 |
| 页面静态/服务接线合同 | 12 Python通过 |
| VM加载真实workspace的渲染、按钮、轮询接线 | 26 Node通过 |
| 合计 | 128项、零跳过 |

新增7项Python用例在补正前有5项失败；新增页面用例在补正前失败。首次完整后端运行有1个失败/3个错误：TestClient启动会补旧库任务默认字段、修复NULL根身份，影响夹具对照并触发后续幂等重放。对照改为规范化后的恢复前状态，损坏输入用真实SQLite事务直接验证，保留SQL NULL反例。页面静态测试另有一个早已陈旧的缓存版本断言，冻结HTML证明此前就不匹配；已按本次workspace资源精确版本更新。原失败日志均保留，不弱化活跃任务/权限/并发保护。

原8份源/测试快照、前后测试及实机证据位于`.tmp/deepseek-stop-diagnostic-20261021/fix/`，索引`verification.json`。未用Browser，页面实际效果交用户验收。

## 加载与实际恢复

- 只读核现有human操作身份`human:bobo`、原API健康/创建时间及原启动器SHA，记录配置/绑定哈希、五角色及286完整行哈希；无running任务。既有恢复CLI核本机hostname、指定health、旧manager/bridge不存在、无替代宿主或同实例/launch进程，未知或访问拒绝不当成不存在。
- 19:41经原启动器正常关闭/重开API，无强杀、无reload自动重启；新launcher22360/child22332，healthz正常。加载后先验证DeepSeek变为unknown/stop_timeout、归属仍在/can_start=false；配置、所有角色记录及进程事实和286保持，HTML/JS返回字节与本地一致。
- 既有human-only plan和apply明确`--confirm-stopped`，原gen24/start `ba5ad779-0cf6-493f-a4d0-87a97181255f`/实例`ins_00acba0f8a9b`/host与准备证据一致后执行。19:42:24得到审计`eea3c70a-0bc6-4284-b755-7cbcca3fac73`，gen24→25、confirmed_by=human:bobo、reason=original_host_exited、非重放。
- 最终API公开desired/observed均stopped、ownership_held=false、can_start=true、can_stop=false、无错误；旧实例标offline，原心跳时间保持，未伪造原stop成功回执。其它四角色记录、所有记录角色进程仍不存在、配置/绑定和286全文哈希均保持，running任务0、没有新派发。

DeepSeek宿主管理器仍未启动；本次完成关闭状态恢复，不包含后续启动链路。会话机制290已收取与离线实现边界、Kimi额度暂停、日志/21600待办均保持。

## 人工验收

正常TALK地址登录，Ctrl+F5刷新角色页，DeepSeek应显示“未启动（已关闭）”，不再停留“关闭中”。本次只核对关闭结果，无需启动角色。若仍不符，保留实际提示反馈。后续同类stop超时应显示“关闭超时（状态待核实）”，在明确人工恢复前不能重复启动。恢复条件与命令见[人工恢复指南](../guides/ROLE_SERVICE_RECOVERY.md)。
