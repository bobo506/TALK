# Terra 349集中返修：延迟启动只恢复pending

派发回执：**350「Terra延迟启动仅恢复pending（349集中返修）」**，2026-10-28 10:00:04（Asia/Shanghai）创建，目标`agent:deepseek`，初始`queued/assigned`。沿349工作线续轮，`execution_session_state=null`，不预称原生会话复用状态。自动跟进已停止为`creator_stopped`，未取消任务或主动等待。

## 独立复核结论

349本次不通过，需一个小范围集中返修。原交付9改1增及485文件保留，不直接修改原candidate。

独立证据：

- 合法结构化交付`task_id=349`格式通过，但自由文本MCP结论unknown，runner succeeded不代替业务验收。
- 在正确的candidate根复跑Node：51+1+31+14+14=111项全部通过。
- Python相关284项有9项失败，均为Windows短路径`C:\Users\ADMINI~1`与完整用户名的argv差异；baseline同一用例也失败，属于既有环境差异，不是349新增回归。
- 独立探针`review_probes349`最终为1失败/1通过：准备迟到的失败回写不会覆盖ready，符合预期；但`not_eligible`会被ready回调重新启动，违反合同。

## 必须修正

`server/role_provision_requests.py:enqueue_pending_auto_start`当前只检查`auto_start_intent`和`auto_start_launch_id`，没有限定`auto_start_status`。因此初始为`not_eligible/auto_start_config_disabled`的请求，在宿主后来启用且native准备ready后，会重新产生pending start launch。

独立反例`.tmp/terra-role-review-349-20261028/review_probes349.py`先得到正常pending，再在临时库精确改成`not_eligible/auto_start_config_disabled`，调用`enqueue_pending_auto_start`后实际新增1个launch，期望应为0。

## 返修范围

- 延迟回调只能恢复`ROLE_AUTO_START_STATUS_PENDING`且仍满足原`auto_start`意图的请求；`not_eligible`、`failed`、`enqueued`及其他状态不得因ready回调重新启动。
- 保持正常pending→ready恰好一次启动、重复回调零新增、人工操作/配置关闭零新增等既有语义。
- 新增或强化回归：初始`not_eligible/config_disabled`后ready不得新增launch且状态不被改成enqueued；正常pending仍恰好一次。
- 只改直接相关实现和既有测试，不重写其他Terra/0.164/页面逻辑，不处理其余6项页面需求、348或生产事项。

## 新冻结与写入

- 来源为349原candidate 485文件，原baseline和原candidate均不改。
- 新baseline：`.tmp/terra-role-fix1-20261028/baseline/`。
- manifest：`.tmp/terra-role-fix1-20261028/manifest.json`，SHA256 `9408e7d8869663d8445780a0760092a8e6590a29284c2390ad59b3fbc140247d`。
- 唯一写入：`.tmp/terra-role-fix1-20261028/candidate/`及`delivery/`。
- 独立探针和失败日志只读参考`.tmp/terra-role-review-349-20261028/`，不得修改或删除。

## 验证与交付

- 使用原隔离runner、系统Python3.12+venv依赖、临时库/假CLI和Node测试，先复现失败再验证修正。
- 必跑新反例、正常pending幂等、Terra/Codex直接相关Python回归和创建/服务/绑定/目录Node回归。既有9项短路径环境失败须单独标注，不得冒充产品通过或改断言。
- 交付REPORT、合法`talk-delivery-1 development.json`（写本次真实任务号）、patch、最终SHA、测试日志和未验证项。真实登录/模型/生产/浏览器人验不在权限内。
- 完成即冻结暂停，由大K复核；不commit/push、不集成、不生产加载、不自行派复核。
- 默认被动，用户通知后取件。
