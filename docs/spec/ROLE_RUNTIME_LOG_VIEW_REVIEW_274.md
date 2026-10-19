# 274日志查看后端：独立复核与直接修正

日期：2026-10-19。首次执行DeepSeek；首次交付独立检查、修正及最终自检Codex。275前端候选本轮未收取或合入，公共页面尚未上线。

## 原交付与范围

- task274 / result2847 / agent:deepseek / ins_7cb44d5a1f80，creator agent:codex，Hall group:task-96f3d6d53e1846c6ab31d07c3ec5a0b2。合法字符串274的complete自报与本地delivery.json一致；原正文SHA256：`3ebc3e891abb9d6c30f6ab13a754c966d9a159e350e695b062c3f11fcdc75009`。
- 基线4768c207c8b9e3fe105ba6b0a9800526e9542070。首次8个代码/测试文件均在白名单：新增query/models/sources、routes/runtime_diagnostics、三个测试，main仅导入和注册router；其余跟踪差异仅此前Codex两份派发进度。原代码、原交付/测试产物与精确SHA保存于`.tmp/runtime-log-view-v1/independent-review274/{original,original-artifacts,original-index.json}`，未追改原报告。
- 原自报43项测试、1项跳过；另自报27项旧日志回归。Hall2850明确保持暂停、不改码，另有索引问答不视为本桌面追加返修授权；本轮没有派新任务或交回DeepSeek修正。K3候选仍限自己目录。

## 首次独立发现与修正

首次7项独立反例的unittest统计为7个失败、1个错误（其中超长整数有2个失败子项）；随后补1项游标IO反例失败。全部使用假记录、自己的临时根、独立子进程或隔离ASGI，不是生产数据泄漏证据。

1. **冷启动死锁**：默认provider持普通Lock时递归创建默认codec，同线程再次拿同一锁，首次请求可能永久阻塞。改为可重入锁，保留进程级provider/签名世代；独立子进程冷启动回归通过。
2. **嵌套目录换链越界**：只校验配置根祖先和文件inode，不能阻止枚举后嵌套目录被换成junction；首个不完整页会返回根外假记录。读正文前额外核目录链、叶子reparse和实际已打开句柄的最终路径，必须仍在批准根且对应本条入口；无法证明则拒读。真实Windows换链反例已复测。
3. **增长文件超预算**：文件打开后追加超长行，旧迭代器可先读约2MiB再判断，反例预算仅2048字节。改为先检查时间、读取上限不超过已计入预算的打开时长度，单行有界并正确丢弃超长行余段；验证轮同样有界。
4. **错误分类与不当推断**：有cursor但文件PermissionError会被误报409 stale_cursor。区分已确认换文件/元数据变化与不可核验IO，游标无法安全读时503；普通部分扫描不把读取失败或预算不足写成“已确认来源变化”。保留原ref/detail的503 diagnostics_scan_incomplete合同。
5. **Unicode路径脱敏缺口**：POSIX规则仅覆盖ASCII组件，中文路径可进入消息与帧函数。扩展Unicode组件及正斜杠UNC形式，保持所有自由文本再净化与明确的启发式限制。
6. **非法输入500**：超长十进制limit/task_id触发Python整数转换异常，极端时区日期转UTC溢出。先限输入长度、按既有上限校验并捕获转换溢出；API返回422，坏记录时间标为不可解析。
7. **投影边界补正**：200字符preview后再加计数尾缀会超200；改为总长内明确省略。完整性标记数组超100项原来静默丢尾；现在拒绝投影，不伪称完整。新增聚焦回归覆盖。

Windows实际句柄路径核验依据[GetFinalPathNameByHandleW官方说明](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)，路径不对外输出。Linux通过`/proc/self/fd`分支验证已打开对象，本机未实跑；无等价能力的平台拒读，不宣称跨平台验证通过。

## 最终验证

- **81项通过，0失败、0错误、0跳过**：开发者三个测试模块43项、新增`tests/test_runtime_diagnostics_api_review.py`的11项针对性回归，以及原`tests.test_runtime_diagnostics`27项。用例数不等同273的67项矩阵全部通过，页面/健康补数仍未验。
- 命令：`python -X utf8 .tmp/runtime-log-view-v1/independent-review274/run_checks.py final-regression-81`。原始日志与计数位于同目录`final-regression-81/`，首次反例与中间失败全部保留；修正后验证称Codex自检，不称他人独立回审。
- 真实Windowsjunction/目录换链和随机回环HTTP路径均通过。所有DB/日志/测试根在审查目录，导入main前隔离engine/LOG_PATH；未改开发者原断言或覆盖原test-run.log。初次回归一项详情错误码差异已保原合同，另一项为测试客户端代理依赖错误；最终只在测试进程去除代理后直连随机端口通过，不安装依赖或改系统代理，不推断原自报skip的单一成因。

## 可用代码与部署边界

- 两GET路由、严格网络DTO与同机provider已实现：人类账号查看、项目/当前或历史角色对校验、逐记录scope、摘要/精确ref/详情、规范化分页/稳定签名和来源变动失效；Agent403。公开结果不含原始路径/源码行/extra/argv/env/配置/PID或凭据。
- 来源仅取`CONFIG.runtime_diagnostics.sources`的精确project_id/member_id/绝对root；缺省为空且503，无默认根或环境回退。本轮未写生产来源配置、读取生产日志/DB、重启API/角色、调用模型或部署页面；不据本轮宣称线上API已加载。
- 原持久schema/CLI/ready/owner/启停/恢复守卫及Key/绑定保持。没有跨宿主、健康新增心跳/预检事件、逐ref保留索引或全根清理。275需另行独立复核，双方暂停后才做跨线集成和正常部署/页面验收。
- 274由原creator agent:codex于UTC`2026-10-19T02:53:18.248428`正常收取，succeeded/completed，原结果2847及原complete报告不变。收取及完整证据位于`.tmp/runtime-log-view-v1/independent-review274/`。
