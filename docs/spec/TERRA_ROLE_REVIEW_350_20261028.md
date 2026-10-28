# 350 Terra延迟启动返修：大K复验与集成记录

## 结论

**350复验通过，349经返修后闭合。** 两任务已由原创建者大K正常收取为`completed`。原349首次不通过及350返修材料均保留，不改写历史。

## 复验证据

- 修正仅2个文件：`server/role_provision_requests.py`和`tests/test_role_auto_start.py`；fix1 baseline 485文件无漂移，manifest SHA256 `9408e7d8869663d8445780a0760092a8e6590a29284c2390ad59b3fbc140247d`。
- `enqueue_pending_auto_start`新增`auto_start_status == ROLE_AUTO_START_STATUS_PENDING`门；`not_eligible/failed/enqueued/None`等状态即使native ready也不再新增launch或改成enqueued。
- 349原失败反例修正后2/2通过；正常pending、四种非pending状态及重复回调3/3通过。
- 正确candidate根Node 111项全部通过。Python相关285项有9项Windows `ADMINI~1`短路径差异，与349复核相同且baseline同现，属于既有环境差异，不冒充产品通过。
- patch可在fix1 baseline应用，结构化交付`task_id=350`合法。

## 集成

生产根比候选基线更旧，单复制349/350的10个差异文件不足以运行，前端实测发现`index.html`等依赖缺口。已按实际差异补齐18个依赖文件，共集成28个代码/测试/页面文件；未整目录覆盖，未改生产配置、数据库、Key或其他角色。

集成后：

- 28个文件与fix1 candidate逐项SHA一致。
- 前端创建/集成/服务/绑定/目录Node共111项全部通过。
- 状态门及正常pending定向测试通过。
- 真实API重启、生产角色创建/启停、真实设备授权、模型调用及浏览器人验尚未执行，不能把源码集成和合成验证冒称生产可用。

详349[首次复核](TERRA_ROLE_REVIEW_349_20261028.md)与350[返修合同](TERRA_ROLE_FIX1_20261028.md)。
