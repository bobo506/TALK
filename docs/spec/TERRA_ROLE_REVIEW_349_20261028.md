# 349 Terra新角色首片：大K独立复核报告

## 结论

**349本次复核不通过，需集中返修后复验。** 原交付和485文件保留，不集成、不生产加载；结果2995保持`succeeded/submitted`、未收取。已派350进行单项返修，默认被动、用户通知后取件。

## 交付与冻结核验

- 本地`development.json`经`talk_workflow.py summary --expect-task-id 349`校验为合法`talk-delivery-1`，自报complete；MCP结果正文为自由文本，业务结论unknown，不能把runner成功当验收通过。
- baseline 484文件无漂移，manifest SHA256 `0ba997ebe35fd9cfc05ca670178a0335b47a75be217306b08e309c58d0ab3f76`。
- candidate 485文件，9改1增、零删除；声明SHA与独立重算一致，patch可在baseline应用。
- 原349 baseline/candidate/delivery未修改；新返修从该485文件另建冻结。

## 必须修正：MF-1 非pending状态被ready回调重新启动

`server/role_provision_requests.py:enqueue_pending_auto_start`只检查`auto_start_intent`和`auto_start_launch_id`，没有限制只能恢复`ROLE_AUTO_START_STATUS_PENDING`。

独立反例先在正常链路得到pending，再在临时库精确改成`not_eligible/auto_start_config_disabled`，native准备改为ready后调用该函数，实际新增1个pending start launch，期望应为0。这样会把最初不符合自动启动条件的请求重新激活，违背“配置关闭/非合格零新增”的合同。

返修应只恢复pending，保持`not_eligible`、`failed`、`enqueued`及其他状态不被ready回调重新启动；正常pending仍须恰好一次、重复回调零新增。

## 验证证据

- 正确candidate根Node：51项创建 + 1项集成 + 31项服务 + 14项绑定 + 14项目录，**111项全部通过**。
- Python相关284项有9项失败，全部是Windows短路径`C:\Users\ADMINI~1`与完整用户名导致的argv不相等。baseline的同一用例也失败，证明为既有环境差异，不是349新增回归；不改断言、不计为产品通过。
- 独立探针`.tmp/terra-role-review-349-20261028/review_probes349.py`最终为**1失败/1通过**：MF-1复现失败；迟到的准备失败回写不会覆盖ready，符合预期。失败日志`review-probes349-failing.log`保留。
- 初次探针夹具中直接关闭宿主会阻挡配置作业和report，后续已改为精确构造`not_eligible`状态后复测；最终结论只采用有效反例，不把夹具错误当产品缺陷。

## 未验证与边界

真实设备授权、真实账号模型目录、真实app-server握手/模型推理、生产API/宿主加载、真实角色启停和浏览器人验未执行。合成协议和测试不能外推这些场景通过。350仅处理MF-1，不混入其余6项角色页面需求、348、WorkBuddy或生产操作。
