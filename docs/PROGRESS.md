# Project Progress

Updated: 2026-10-25 08:31（Asia/Shanghai）。一次已授权元数据核查确认旧K2.8的native专属目录内一处目录联接。Codex最小补正仅清该联接入口，121项隔离回归零失败/跳过；待冻结交DeepSeek定向复核。生产仍r2 failed/unsafe_resource，未加载/重试；下一自启动片未开工。

## 当前运行与真实删除

- agent:codex / prj_e8fe7066bbec / lead。用户原终端重启后新runtime17580/external，API健康，初始六宿主serving、worker空闲无错。完成旧K2.8 manager步骤后剩五宿主serving，无强杀/接管终端。
- agent:workbuddy正式重试r3，观测r4/5 cleaning，UTC16:32:32.772268（本地00:32）r6 complete；credentials preserved/identity_disabled=false，其它清理步骤complete。角色接口已移除它，未查看私有目录或手工删除文件。
- 本轮仅普通start恢复DeepSeek gen68/ins_e463b3ea6ebf/PID7476，running/ready/idle，同实例心跳推进60.088815秒；其它四保留角色停止无owner。前轮心跳证据保持。
- 两目标之外五角色完整公开配置/绑定/要求与before一致；286仍queued/accepted/paused。另两个managed K2.8/workbuddy-k3保留。

## K2.8 当前必要补正

- 精确目标agent:kimi-code-k28-preview已通过330历史任务守卫；UTC00:04:15.883386正式删除接受r1 pending，角色归档/绑定清除。UTC00:04:20.452278 r2 failed/unsafe_resource：manager/profiles complete、credentials preserved、private_state failed、startup_config pending、identity_disabled=false。未自动重试或手动绕过资源保护。
- 唯一阻挡为250：2026-10-16已failed/failed、有finished_at/无lease，原result2767未收取。collect-result只接受submitted；旧“不收取/追改250”保持，未生产collect/cancel/resume或改DB。前后公开250任务/原结果逐字段相同。
- 仅server/role_deletions.py + tests/test_role_deletion.py补正：只有failed/failed、明确已结束、无claim/lease、无保留预算且非暂停/待人工控制的历史不再误拦。不更改任务/结果/绑定快照；queued/running/paused/submitted/缺证/混合活动任务及其它原守卫保持。
- 最终四模块143/143通过，4新增包含在内不相加；修前2反例失败、首个组合2夹具迁移基线失败原日志保持，修正后定向4及最终143全过。未改前端/本机清理，不重复Node或原283全组。
- 330独立143/143关联回归及5项真实隔离API探针通过，无必须修正项；正式2974与本地交付等值，UTC23:50:35已收取completed。9份/81785字节原交付归档零错配；45新快照和原50/64/79、329归档保持。
- 复核者披露临时调试wrapper曾向review之外写出38合成DB并声明清除，正式验证已以正确冻结wrapper重跑；不声称全程唯一写根合规。报告第4.3节混写两次失败原因，协调说明已纠正，原报告/日志不改。详补正合同。
- 330实际new_no_candidate新窗/count1，末公开snapshot26.0273%，未续329。该守卫已实际放行目标，公开250原任务/2767结果全字段不变；286 paused保持。后续资源拒绝已通过一次授权元数据定位为native内目录联接，不能因新自检通过就称生产清完。
- 页面实际HTTP资产匹配v3，原workspaceRoles函数以本次公开角色响应执行，显示5角色且排除两目标；这是实际页面筛选/HTTP证据，未替代真人浏览器验收。旧K2.8清理失败只保留独立清理区，角色不回常用列表。

## 下一步和授权

用户明确授权的一次最小元数据核查已执行：1309条、native目录360/普通文件949，唯一目录reparse/tag0xA0000003。不读资源内容/Key/原生会话日志正文、不输出私有路径/目标、不跟链接或改资源。此例外已用完，不扩大继续扫描或手工清理许可。

当前仅scripts/role_delete.py + tests/test_role_delete_local.py新增规范native成员根后代的目录联接入口HANDLE删除；不遍历目标，固定父目录并核打开属性/tag/路径/身份。根、profiles/roles/control/凭据/workbuddy-native链接、硬链接/符号链接/其它tag仍拒绝，通用NativeFile/日志/API/页面不改。

9新测试包含在最终四模块121/121内，64.868秒，零失败/错误/跳过。修前4中2失败、初次本机锁夹具1失败及沙箱符号链接2skip原日志保持，正常沙箱外完整121通过，不把重叠组累计；详新合同。产品待冻结交DeepSeek，尚无新独立通过结论。

新材料role-delete-native-junction-v1，旧330/327/328/329报告及冻结保持。只改runtime清理器，复核后先按原入口普通stop/drain，再serve --attach-api --detach恢复runtime，API无需为此补正重启；当前未生产停启/重试，不接管external API或另开第二API。随后正式retry旧K2.8到complete并核250/286/五保护角色、恢复DeepSeek及心跳。默认派后用户通知取件。

用户已经授权：当前真实验证全部通过后，继续一个此前讨论的选择性项目自启动切片，Codex开发、DeepSeek独立复核，人工验收等用户返回。当前K2.8未闭合，不提前开新功能；不扩大连续多片或生产私有访问权限。

详[目录联接补正](spec/ROLE_DELETE_NATIVE_JUNCTION_20261025.md)、[330合同](spec/ROLE_DELETE_FAILED_TASK_HISTORY_20261025.md)、[实际加载记录](spec/ROLE_DELETE_USER_FIX_DEPLOYMENT_20261024.md)及[历史](PROGRESS_HISTORY.md)。
