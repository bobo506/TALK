# 退出闭环正常加载方案（337复验已通过）

**2026-10-25 23:17实际完成：** 用户明确“是”授权本方案一次正常后台重载。原stop --wait返回0/stopped，回执省略activation原值；UTC15:12:55原13252及11去重PID全absent、五角色stopped/无owner后启动新runtime4956（UTC15:13:22.151066）。新shutdown=idle且其余初始字段为空，startup一轮complete、worker无错、五宿主serving；小D按用户true/rev1自动gen80/ins_3d1a0388545c/PID7868 ready/idle，真实同实例心跳60.090351秒，另四停止。APIuptime15705→15909连续，五binding/配置/要求/偏好及250/286完整公开响应相同。

本片正常加载已完成，无需再次重启API或后台。停止对象为旧版，phase unknown属于兼容；没有为验证新版阶段再停第二次，真实生产故障注入/断电/完整异常恢复不外推。275/236/旧冻结及332至337原材料保持，产品仍b9e2de0；证据`.tmp/runtime-shutdown-fix1/deployment-20261025/`中的before/stop-result/stopped/start-request/ready/heartbeat/RESULT/freeze-and-archives.json。本次许可已执行，后续新停启仍按明确任务边界处理。下方保留原始可审方案与当时未执行状态，不代表当前仍待执行。

2026-10-25。本方案已准备，尚未执行生产停启。337正式2983 complete、无必须修正项，原17份154086字节交付已核验归档并收取；产品仍b9e2de0，没有后续产品/正式测试修改。上片选择性自启动的一次正常停启许可已执行，本片生产加载不由该旧许可自动延伸。

## 当前只读事实

UTC15:04:44：原runtime13252仍UTC12:04:08启动、running/present、api_mode=external、startup_state=complete、worker空闲/无错、五宿主serving。健康文件没有本片shutdown字段，说明后台尚未换代加载退出进度。DeepSeek gen78/ins_9c7bcef519c6 running/ready，另四stopped/无owner，无running任务。

小D自启动保持用户true/revision1/UTC10:50:31，另四false/rev0；五完整binding、角色公开配置、项目开发要求、用户偏好及250/286完整公开任务与上片最终快照逐字段相同。250failed/2767未收取、286queued/accepted/paused保持。原API持续健康，uptime15307秒；本片仅后台/CLI变更，**不需要重启API**。

只读证据：`.tmp/runtime-shutdown-fix1/pickup337/deployment-preflight.json`。仅原CLI消费既有运行清单、既有human凭据正常API认证；无额外配置正文/Key/DB/私有state/native/session/log读取。

## 取得本次正常重载许可后执行

1. 刷新同一只读预检，确认无新运行任务、worker空闲、当前角色/偏好/保护项；记录实际runtime/五宿主/当前bridge的去重PID及创建时刻，不用上片“12个PID”数量套用新实例。如用户选择或在途任务改变，以新事实重新核定计划，不回写旧选择。
2. 用原统一入口提交一次普通停止并等原runtime实际退出：

   ```powershell
   python -B scripts/talk_runtime.py stop --config D:/claude-test/TALK-private/talk-runtime.json --apply --wait --wait-seconds 300
   ```

   只有退出码0、stop_status=stopped、本代健康stopped且原后台与所属宿主/bridge确证退出、五角色stopped/无owner才继续。停止对象目前是旧版后台，没有shutdown详情，回执phase=unknown属于旧格式兼容，不把它说成新版退出阶段生产验证。
3. API保持运行；用原入口隐藏启动一次新后台：

   ```powershell
   python -B scripts/talk_runtime.py serve --config D:/claude-test/TALK-private/talk-runtime.json --apply --attach-api --detach
   ```

4. 新runtime必须实际换代、running/present、shutdown.phase=idle且started_at/completed_at/error_code为空、pending_members为空，startup_state=complete、worker无错、五宿主serving。新runtime按原用户选择自动启动小D；确认新实例ready/idle、同实例真实心跳至少推进60秒；其它四保持停止。已自动ready不再手动start，不PUT偏好或重放activation。
5. 完整比较五binding/公开角色配置/要求、用户偏好和250/286；API uptime连续，不关闭/重启外部API、不启动第二API。记录新代及真实结果后更新进度。本轮仅一次后台正常重载，不为可选覆盖再停第二次、不派额外非阻断复核。

## 失败边界与证据口径

停止回blocked/timeout/incomplete/generation_changed/unverified或进程/归属无法确证时，保存回执和公开错误，暂停后续serve；不强杀/CAS/清锁/删除健康或stop marker，不把“请求已提交”当退出完成。等待超时不会替用户清理所有权。

新后台加载/自动恢复失败也只记录实际错误，不扩大为回滚代码、另一次停启或私有扫描许可。51项全量与真实合成CLI是协调方正常权限结果，DeepSeek独立完成13项等待测试、25条原探针及六状态/55固定码定向验证；337接受了当前范围但保留其本人ACL/隐藏进程限制。本轮加载不能外推为新版所有失败阶段的生产注入、真实断电/OS重启、整项异常恢复或原生模型能力全部验收。
