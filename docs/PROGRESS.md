# Project Progress

Updated: 2026-10-25 20:56（Asia/Shanghai）。用户授权一个下一片：Codex开发、DeepSeek独立核实。按原排期第8项，当前“正常后台退出进度与有限等待”已实现并交DeepSeek336首审；不扩大为整项异常恢复或生产加载。

## 已完成

- 日志自动清理、默认执行24小时、两个指定旧角色真实删除保持。选择性项目自启动334/335已独立通过；原runtime11280/12PID正常退出后，新runtime13252一轮complete，小D自动gen78/ready/idle、同实例心跳90.130226秒，其余四停止；上片运行验证闭合。
- 本片仅scripts/talk_runtime.py产品变更：退出阶段/pending成员/错误/完成时刻，已退出宿主stopped投影；新增显式stop --apply --wait --wait-seconds N，默认300秒、最大900秒。旧不带wait的停止语义保持。
- 等待只跟踪原project/pid/started_at/activation；stopped健康加原进程退出才成功，阻挡/超时/异常退出/新代/未知均不冒报完成。原所属Popen/任务归属、外部API及失败事实保持。
- 最终47项严格合成配置隔离回归全过，0失败/错误/跳过，包含真实合成CLI正常/超时/随后完成及外部API保留。原40项首轮2E、随后两项/46项/3项均分别留档，不相加冒称更多独立用例。

## 当前边界

- 当前身份agent:codex / prj_e8fe7066bbec / lead。仅本片开发/隔离验证；没有生产启停/加载/偏好写入或任务修改，现有小D用户true/rev1保持保护，250failed/2767及286paused不动。最后完整公开保护对比仍是上片20:05，本轮不冒称再次完整核验。
- 新使用说明[退出指南](guides/RUNTIME_SHUTDOWN.md)、[本片合同](spec/PROJECT_RUNTIME_SHUTDOWN_20261025.md)；证据.tmp/runtime-shutdown-v1/。早期直接unittest入口存在server默认配置导入链，不算严格配置隔离；最终47项已走既有run_isolated防护，不读真实默认配置。
- 纯授权补记cde4620不单独推送；用户明确有代码更新则推送，本轮代码及配套文档普通推送既有公开bobo506/TALK当前分支。旧推送审批拒绝保持为历史。

## 下一步

1. 代码760fe12已推送；DeepSeek首审336创建queued/assigned，原生执行会话state=null，不预称已领取/同窗。236份8982718字节新冻结零漂移，旧冻结/332至335原交付保持；唯一写.tmp/runtime-shutdown-v1/review，产品/正式测试/新旧冻结暂停。自检不能替代独立通过，尚未部署本片。
2. 默认用户通知336完成再取件；必要集中修正/定向复验，不为非阻断观察增加轮次，不主动等待/唤回。
3. 本片闭合后再明确下一范围；真实断电/OS重启、完整在途任务中断恢复、桌面外壳和实际模型上报不由本片证明。

详[历史](PROGRESS_HISTORY.md)及[上一片真实自启动证据](spec/PROJECT_ROLE_AUTO_START_DEPLOYMENT_20261025.md)。
