# Project Progress

Updated: 2026-10-25 07:55（Asia/Shanghai）。330独立复核通过并已收取，无必须修正项；正常停机完成，待用户原终端重启API加载补正。WorkBuddy已complete/移除，旧K2.8尚未删除；下一自启动片尚未开工。

## 当前运行与真实删除

- agent:codex / prj_e8fe7066bbec / lead。本轮先核runtime11200/六宿主健康、worker空闲/无running任务，再按既有授权普通stop；UTC23:55:20核runtime及六宿主12原PID全部absent、六角色stopped/无owner。API仍由用户原终端运行，已发重启操作提示。
- agent:workbuddy正式重试r3，观测r4/5 cleaning，UTC16:32:32.772268（本地00:32）r6 complete；credentials preserved/identity_disabled=false，其它清理步骤complete。角色接口已移除它，未查看私有目录或手工删除文件。
- 前轮DeepSeek gen66/ins_203aa34895b9的90.105977秒心跳证据保持；本轮正常关闭后gen67/stopped/无owner。API重启、K2.8删除验证后仅恢复原DeepSeek，其它四保留角色仍停止。
- 两目标之外五角色完整公开配置/绑定/要求与before一致；286仍queued/accepted/paused。另两个managed K2.8/workbuddy-k3保留。

## K2.8 当前必要补正

- 精确目标agent:kimi-code-k28-preview已解除历史实例误拦，但正式delete因role_has_active_tasks拒绝，未建墓碑/清绑定。
- 唯一阻挡为250：2026-10-16已failed/failed、有finished_at/无lease，原result2767未收取。collect-result只接受submitted；旧“不收取/追改250”保持，未生产collect/cancel/resume或改DB。前后公开250任务/原结果逐字段相同。
- 仅server/role_deletions.py + tests/test_role_deletion.py补正：只有failed/failed、明确已结束、无claim/lease、无保留预算且非暂停/待人工控制的历史不再误拦。不更改任务/结果/绑定快照；queued/running/paused/submitted/缺证/混合活动任务及其它原守卫保持。
- 最终四模块143/143通过，4新增包含在内不相加；修前2反例失败、首个组合2夹具迁移基线失败原日志保持，修正后定向4及最终143全过。未改前端/本机清理，不重复Node或原283全组。
- 330独立143/143关联回归及5项真实隔离API探针通过，无必须修正项；正式2974与本地交付等值，UTC23:50:35已收取completed。9份/81785字节原交付归档零错配；45新快照和原50/64/79、329归档保持。
- 复核者披露临时调试wrapper曾向review之外写出38合成DB并声明清除，正式验证已以正确冻结wrapper重跑；不声称全程唯一写根合规。报告第4.3节混写两次失败原因，协调说明已纠正，原报告/日志不改。详补正合同。
- 330实际new_no_candidate新窗/count1，末公开snapshot26.0273%，未续329。新守卫仍待API加载，独立通过不代称两个目标均已真实完成；250原失败任务/2767结果及286保护保持。

## 下一步和授权

补正eb6cf6c已推送，产品/正式测试取件后未再修改。新部署证据位于role-delete-failed-history-v1/deployment/，before/stop-request/中间观察/drained均保留，不覆盖前轮证据。新helper已准备只消费原运行器、正常human认证及公开接口，不另读配置/角色Key/DB/私有目录。

等待用户在原API终端Ctrl+C重跑原命令。回复后直接核新API/runtime/六宿主与250原任务/结果，正式删除旧K2.8跟进complete、核剩五角色/五宿主，恢复DeepSeek并核心跳/其它保护；同一已授权范围不重复申请确认。330属于当前必要修正，不是下一新功能。

用户已经授权：当前真实验证全部通过后，继续一个此前讨论的选择性项目自启动切片，Codex开发、DeepSeek独立复核，人工验收等用户返回。当前K2.8未闭合，不提前开新功能；不扩大连续多片或生产私有访问权限。

详[失败历史补正合同](spec/ROLE_DELETE_FAILED_TASK_HISTORY_20261025.md)、[实际加载记录](spec/ROLE_DELETE_USER_FIX_DEPLOYMENT_20261024.md)及[历史](PROGRESS_HISTORY.md)。
