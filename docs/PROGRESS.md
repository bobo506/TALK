# Project Progress

Updated: 2026-10-25 00:46（Asia/Shanghai）。WorkBuddy正式清理complete并已移除、DeepSeek已恢复。旧K2.8的已终止failed历史误拦补正330已交DeepSeek定向独立复核，派发queued/assigned；Codex产品修改暂停。新守卫未加载，K2.8尚未删除，下一自启动片尚未开工。

## 当前运行与真实删除

- agent:codex / prj_e8fe7066bbec / lead。用户已原终端正常重启API；新runtime11200/六宿主serving、worker无错，原非service公开角色投影/要求保持。
- agent:workbuddy正式重试r3，观测r4/5 cleaning，UTC16:32:32.772268（本地00:32）r6 complete；credentials preserved/identity_disabled=false，其它清理步骤complete。角色接口已移除它，未查看私有目录或手工删除文件。
- 原DeepSeek普通start恢复gen66/ins_203aa34895b9/PID8092，running/ready/idle，同实例心跳推进90.105977秒；其它五个现存角色停止无owner。
- 两目标之外五角色完整公开配置/绑定/要求与before一致；286仍queued/accepted/paused。另两个managed K2.8/workbuddy-k3保留。

## K2.8 当前必要补正

- 精确目标agent:kimi-code-k28-preview已解除历史实例误拦，但正式delete因role_has_active_tasks拒绝，未建墓碑/清绑定。
- 唯一阻挡为250：2026-10-16已failed/failed、有finished_at/无lease，原result2767未收取。collect-result只接受submitted；旧“不收取/追改250”保持，未生产collect/cancel/resume或改DB。前后公开250任务/原结果逐字段相同。
- 仅server/role_deletions.py + tests/test_role_deletion.py补正：只有failed/failed、明确已结束、无claim/lease、无保留预算且非暂停/待人工控制的历史不再误拦。不更改任务/结果/绑定快照；queued/running/paused/submitted/缺证/混合活动任务及其它原守卫保持。
- 最终四模块143/143通过，4新增包含在内不相加；修前2反例失败、首个组合2夹具迁移基线失败原日志保持，修正后定向4及最终143全过。未改前端/本机清理，不重复Node或原283全组。
- 新守卫尚未加载；143只是Codex自检，不代称独立通过。原327/328/329结果、50/64/79快照、250历史及286保护保持。

## 下一步和授权

补正eb6cf6c已推送；45份/2054979字节新冻结源/快照零漂移，原50/64/79快照和329原15份报告归档零错配。330于UTC16:45:50派DeepSeek queued/assigned，唯一写role-delete-failed-history-v1/review/，Codex产品/正式测试/冻结暂停；默认用户通知完成后取件。沿base327请求相容续329窗，创建state=null，实际决定待回执，不预称复用或独立通过。

通过后正常加载API、正式删除旧K2.8并核250不变；当前许可持续覆盖必要验证/修复，不重复询问同范围，外部API仍需原终端正常重启。330属于当前必要修正，不是下一新功能。

用户已经授权：当前真实验证全部通过后，继续一个此前讨论的选择性项目自启动切片，Codex开发、DeepSeek独立复核，人工验收等用户返回。当前K2.8未闭合，不提前开新功能；不扩大连续多片或生产私有访问权限。

详[失败历史补正合同](spec/ROLE_DELETE_FAILED_TASK_HISTORY_20261025.md)、[实际加载记录](spec/ROLE_DELETE_USER_FIX_DEPLOYMENT_20261024.md)及[历史](PROGRESS_HISTORY.md)。
