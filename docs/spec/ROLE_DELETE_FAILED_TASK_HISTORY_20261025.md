# 删除角色：已终止失败历史兼容补正（2026-10-25）

本轮是用户已授权删除功能的必要修正，由Codex开发、自检，DeepSeek独立复核。用户允许当前全部验证完成后进入一个下一选择性项目自启动切片；当前K2.8验证未闭合，不提前开新片、不重写历史任务。

2026-10-25 08:31：330守卫已实际放行的事实与原独立结论保持；后续资源失败经一次授权元数据定位为native内目录联接。Codex仅清入口的121项自检补正在[另份合同](ROLE_DELETE_NATIVE_JUNCTION_20261025.md)，待DeepSeek复核/正常runtime加载，不改本轮任务分类、250原失败结果或330报告。

2026-10-25 08:08实际加载：用户原终端重启后runtime17580，新任务守卫正式放行旧K2.8删除r1，250原failed/2767结果全字段不改。后续r2清理private_state报unsafe_resource，资源尚未清完；页面实际筛选已排除两目标。仅恢复DeepSeek gen68且真实心跳推进60.088815秒，五保护角色/286保持。此处资源原因尚未确定，不追改330原结论，当前等待一次最小只读元数据核查授权，详[加载记录](ROLE_DELETE_USER_FIX_DEPLOYMENT_20261024.md)。

## 实际发现

用户正常重启原API后，已核新API健康、runtime11200/六宿主serving、worker空闲无错，原完整非service角色投影/要求与重载前一致，286 paused保持。旧K2.8历史实例误拦已解除，正式删除随后被另一个守卫拒绝：`role_has_active_tasks`。

公开API只读定位唯一阻挡为250：旧agent:kimi-code-k28-preview的历史任务，2026-10-16已status=failed/workflow_status=failed，有finished_at、lease_expires_at=null，原结果2767未收取。正常collect-result仅接受submitted，failed行没有可用的普通收取路径。历史记录明确保留250失败、不收取/追改，本轮仍不调用生产收取/取消/恢复或直接改库。删除前后两次公开250任务/原结果逐字段相同。

与此同时，按原正式入口重试agent:workbuddy，revision3 pending→观测revision4/5 cleaning→revision6 complete，私有状态/启动配置已由正常runtime清完，credentials preserved/identity_disabled=false。最终时间UTC2026-10-24T16:32:32.772268（本地10月25日00:32），角色接口不再返回它。协调方没有查看私有目录或手工删除文件，完整步骤以受信runtime正式回执为证。

原DeepSeek正常恢复gen66/ins_203aa34895b9/PID8092，running/ready/idle，同实例真实心跳推进90.105977秒。其它五个现存角色停止无owner；相对两目标之外的五个角色公开配置/绑定/项目要求与before一致，286 queued/accepted/paused保持。K2.8仍未产生墓碑，仍绑定原模型；失败历史补正尚未加载生产API。

## 最小实现

仅改 `server/role_deletions.py` 与 `tests/test_role_deletion.py`。

删除事务内原任务守卫改为分类判断；原completed/canceled兼容行为保持，queued/running和paused仍先拒绝。额外只认可同时满足全部证据的终止失败历史：

- runner状态和workflow状态均为failed；finished_at存在且不在未来。
- claim_token与lease_expires_at都为空；保留预算reserved_slice_count为0或旧NULL。
- control_status只接受旧NULL、active或canceled；pause_requested/paused/awaiting_human/cancel_requested及未知值不放行。

这是读取既有失败事实，不把failed改成completed、不收取或迁移旧结果，不写任务/消息/任务绑定快照，也不额外吊销共享身份。未完成发起者义务/全局任务、另一条活动任务、未收取submitted成果仍阻挡；服务、实例、启动/配置请求、定时任务、独占证明、租约与资源归属原守卫保持。没有新表、接口参数或生产配置开关；原Key轮换策略不变。

## 验证与限制

- 4项新增真实隔离API测试覆盖：已结束失败历史的完整删除闭环及任务/结果逐字段保持；失败结果确实不可collect；global/creator历史保持；17组缺证/活动/暂停/不一致状态拒绝；混合已失败与活动任务仍拒绝。
- 修前4项中2失败/2通过，原始before.log保留。首个143组合141通过/2失败，是合成旧任务在TestClient启动迁移补齐NULL默认值后与迁移前快照不同；测试已将删除前基线移到正常API初始化之后，未改迁移或任务产品代码。原selfcheck.log失败保留；补正后4项定向通过。
- 最终同四模块143/143通过、零失败/错误/跳过，102.836秒；包括删除、轮换独占、任务队列及绑定快照，4项定向与组合重叠不累计。未改前端/本机清理，未重复Node或完整283组；既往329相关证据与限制保持。
- 所有服务测试经原run_isolated.py合成配置wrapper，生产配置/DB/Key未用作夹具；测试隔离库/文件只在本片.tmp根。真正生产250仅GET且未变，未借失败历史补正解除286或改失败结果。

源码和安全证据在 `.tmp/role-delete-failed-history-v1/` 新冻结；原50/64/79快照及327/328/329报告保持，不重写原结论。独立复核唯一写根为 `review/`，产品冻结后暂停。

## 2026-10-25 07:50：330独立复核通过并已收取

用户通知330完成。正式结果2974由agent:deepseek在正确Task Hall提交，talk-delivery-1业务complete，与本地delivery逐字段一致。协调方核对报告、探针、原始日志及冻结后验收；UTC23:50:35.761278收取workflow completed，runner succeeded，无必须修正项。产品和正式测试仍为eb6cf6c，未因取件再改代码或重复整组测试。

独立四模块143/143通过，115.197秒，零失败/错误/跳过；另5项真实隔离API探针通过，覆盖22种拒绝状态、5种混合义务、6组旧守卫及完整删除前后任务/消息保持。143与协调方143分别计证据，不相加为新增测试；独立5项包含自己的内部子场景，不另累计。正式检查使用冻结隔离wrapper及本片review隔离根，未使用生产夹具。

取件核新45份/2054979字节快照零错配，源仅AGENTS/PROJECT_BRIEF为派发后预期协调文档漂移；原50/64/79快照和329原15份归档零错配。330正式交付显式列出的9份/81785字节已复制到coordination/330-original-review/并逐项核验，未扫描scratch或私有目录，旧报告和失败日志保持。

两项审计说明单独保留：

- 复核者披露临时调试wrapper遗漏mkdtemp重定向，曾向唯一review写根之外的.tmp-tests写出38个合成DB，并声明均已清除；正式143与5项证据已用正确冻结wrapper重跑。因此不能声称全过程严格遵守唯一写根，过程偏差不以产品通过掩盖；没有据此追加生产访问或产品返修。
- 原report第4.3节把两种失败原因混写：before.log的2项失败是真实旧守卫409；selfcheck.log的2项失败才是TestClient初始化迁移与快照基线不同。本合同原记录和原始日志可区分两者；原报告不追改，以此协调说明纠正。

330实际new_no_candidate新窗/count1，原生session-b0cb3ab9-4176-4693-8f99-d41cd1746f4b；未续329。初始context_status unavailable/no_candidate，末公开snapshot260273/1000000=26.0273%，不读私有会话推断未续原因。

当前已加载的仍是329修复；330补正独立通过不等于生产加载。后续按已授权方案正常停止原后台，待用户原终端重启external API，再正式删除旧K2.8、核250原任务/结果保持并恢复DeepSeek。两个目标全部闭合后才实施已授权的一个选择性项目自启动切片；无须重复同一范围确认。
