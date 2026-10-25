# 删除角色：专属原生目录内的目录联接兼容（2026-10-25）

这是用户已授权删除缺陷的必要返修，由Codex开发、自检，DeepSeek独立复核。330已经独立收取并实际加载，旧K2.8删除被接受，但资源清理r2在private_state报unsafe_resource；角色保持逻辑移除，不能因此宣称资源已全部清完。下一选择性项目自启动片仍等当前真实验证闭合后实施。

## 已授权的一次元数据核查

用户明确授权：原运行器配置加载函数消费talk-runtime.json只定位state_dir，再看该精确目标专属目录的文件类型、链接数和重解析标记；不读资源内容/Key/原生会话日志正文、不跟链接、不改资源。只执行一次inspect_metadata.py --inspect-authorized，1309条元数据：native目录360、普通文件949，其中一个目录reparse/tag2684354563（0xA0000003），无其它阻挡元数据。未输出私有路径/文件名/联接目标，原清理器拒绝该入口的原因得到确认；不需要读取其目标才能修正入口清理。

这次一次性例外已执行完，不转为继续扫描私有目录、原生HOME内容或手工删除许可。原250 failed/failed及结果2767、286 paused、其它五角色绑定/要求和共享身份保护保持；DeepSeek gen68/ins_e463b3ea6ebf已恢复且真实心跳60.088815秒。两个目标已被页面实际v3筛选排除，WorkBuddy实际complete，旧K2.8资源仍failed。

## 最小实现

产品仅scripts/role_delete.py；测试仅tests/test_role_delete_local.py。API、页面、任务分类、通用NativeFile和日志留存不改。

仅在规范state_dir/native/<project>/<member>这个普通目录根的后代，遇到目录联接时删除入口本身：

- 固定所有普通父目录；不对联接调用exists/resolve、遍历或读取目标，规范化只用于已固定的普通父目录。
- CreateFileW以OPEN_REPARSE_POINT和BACKUP_SEMANTICS打开联接，申请DELETE/READ_ATTRIBUTES，只共享读；不共享写/删除。核对实际HANDLE的目录属性、reparse tag仅0xA0000003、完整打开路径及原lstat的dev/ino/size/mtime身份，再SetFileInformationByHandle(FileDispositionInfo)并关闭相同HANDLE。
- 被替换为另一联接/普通目录、属性或身份变化、打开/删除被占用均失败，不按路径另删、不接管进程。入口计入原单轮预算；已有进展仍原pending/下轮续，不把真实错误变成自动重试。
- native成员根自身、profiles、roles、control、credentials、workbuddy-native及其链接策略保持原拒绝；普通硬链接、符号链接、其它/未知reparse tag继续拒绝。共享原生登录、模型和联接指向的数据不作为目标。

Windows的OPEN_REPARSE_POINT语义及按同一HANDLE设置删除依据[Microsoft符号链接操作说明](https://learn.microsoft.com/en-us/windows/win32/fileio/symbolic-link-effects-on-file-systems-functions)和[SetFileInformationByHandle文档](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)。实际安全性还通过本轮真实Windows合成联接、外部哨兵数据与竞态验证，不以文档代替运行证据。

## 验证

新增9项含真实目录联接/断开联接/循环联接/分批完成、目标树字节保持、同名联接替换拒绝/重试、真实只读HANDLE占用拒绝/释放后重试、根联接/普通硬链接/文件与目录符号链接继续拒绝；成功路径还拦截Python对联接和外部目标的跟随stat。

修前4项中2真实反例失败/2保护通过，before.log保留；首个shell因日志根未建而未执行，不当产品失败。初改4项通过；首轮本机32中1失败是锁夹具用了不参与数据/删除共享检查的metadata-only HANDLE，修为真实GENERIC_READ HANDLE，产品不为该夹具放宽。随后沙箱33项零失败但两个符号链接子场景因系统权限skip；日志均保持。

最终正常沙箱外同四模块121/121通过、64.868秒、零失败/错误/跳过，包含33本机、18runtime、38删除API、32轮换；9新和各定向组重叠不累计。生产配置被原run_isolated.py合成wrapper替代，所有夹具在本片isolated根；未用生产DB/Key/实际资源作测试夹具。未改前端，不重跑Node/旧全283，也不把330原143重复相加。

## 冻结、复核和加载顺序

新源码/普通证据冻结在role-delete-native-junction-v1，唯一独立写根review/；DeepSeek只审普通代码和合成资源，不运行生产metadata/部署helper、不读生产配置/Key/DB/实际profile/state/HOME/会话日志，不操作生产启停/删除/claim/report/sweep/CAS。原330、327/328/329交付、新旧快照、250失败历史不改；过程写根偏差也不追删原报告。

本次新清理器未加载、未重试生产墓碑；一次元数据授权不扩为手动删除联接或目标。独立通过后沿本次既有正常加载/指定目标验证范围，先确认无running任务/worker空闲且仅原DeepSeek idle，再普通stop/drain及核原进程退出，通过原统一serve --attach-api --detach入口只恢复runtime，不重启或接管external API；API产品未改。该正常入口先按普通代码和隔离模式验证，不另起第二API。再正式retry旧K2.8并跟踪complete，保250原任务/结果、共享凭据和五保护角色，只恢复原DeepSeek并核心跳。若原入口或归属证据不足，保留现场，不强杀/CAS或绕私有保护。

只有新runtime加载不代表本目标complete，只有逻辑列表移除也不替代专属资源清理。全部验证通过才开已授权下一片；默认派DeepSeek后结束，用户通知后取件。
