# 339首审两项集中返修

用户于2026-10-26明确授权读取339报告、核验后收取。此前一次自动审批拒绝因旧“不读取/收取339”边界；未绕过，明确授权到达后才读取完整5506字符/报告并收讫339/2985为completed。MCP业务unknown/自由文本与原partial结论保持，收讫不等于验收通过。原11份111542字节普通材料归档到D:/claude-test/TALK/.tmp/initiator-followup-fix1/pickup339，未归档合成DB/私有ACL临时状态。

## 两项修正

MF-1：环境预算为空时，delegate原来绕过显式start的flow，走旧/api/tasks。现在只在有同连接同项目未停止flow时取其显式budget，复核真实owner/模式/版本/任务scope，经/api/tasks/followup原子守卫加入原批次；保原deadline/budget，限20项。没有环境预算且没有flow保持旧派发。过期、身份变更、模式切换拒绝写入，不借用其它身份的flow。已有环境配置的原路径也不续原flow预算。

MF-2：stop幂等且保首个终止原因；collect成功后的状态更新持锁，写入真实collected事实但已停止则保持stopped、next_action=notify_user；迟到错误也不改原stop原因。已dispatch的HTTP无法承诺撤回，可能收取完成或结果未知，按实际回执/未知记录，不重试、不取消执行者。stop先于dispatch时原alive守卫零写入，不持有本地状态锁跨HTTP；delegated的同类终态检查移到锁内。

产品只改bridges/initiator_followup.py，正式测试只改tests/test_initiator_followup.py。7项新增（显式review/rework同flow及原子参数、过期/身份/模式拒绝、收取前停止、在途成功/失败后终态）原5F/1E，修后整模块32通过。原独立探针的两项正确性断言不改字节通过；其第一条断言旧缺陷仍存在的观察测试不作为修后验收。244关联Python含6真实stdio全过、自建Job结束active=0；只属协调方普通用户/严格合成环境，不冒称独立复核或当前Codex/Kimi/DSH宿主适配。T10/W4/余量5及取消/EOF/同连接查询证据在coordinator/related/isolated/stdio-evidence.jsonl，页面未变，不重复Node。

## 原独立记录与新复验

339原237为231过/6E，6E为CreatePipe受限未实际执行；另非pipe231、Node35、HTTP1、路由守卫2过。报告披露一次绕过守卫直接导入，读根config、打开日志及刷新pyc，未打印配置、未连生产DB/API；不能把原报告当无污染独立验收。该偏差保留，不读取私有日志/配置去扩大排查，也不清理后称原始。

新复验须force_new请求全新原生会话，正式回执决定实际是否新窗；唯一新写根fix1/review。默认规定wrapper在任何server导入前注入合成配置，在本进程中运行238非pipe正式测试和5原探针，共243；不直接python -c导入tests/server，不尝试用文件通道替代6真实stdio。固定日志/TEMP/-B，源集合/hash/reparse与helper副本前后检查。协调方35项冻结入口验证用于接线自检，不代替复核者本人。若无CreatePipe权限，6真实stdio继续按未运行/引用协调证据记录，不为全过放宽权限。

只重核两项必须修正及必要兼容，不扩原7项非阻断观察。核验声明服务端审计、pre-POST分类、其它入口等观察保留，不增表/新权限/新产品需求。原295/旧归档与Kimi宿主原286/294/289/290及339至342原报告保持；旧294目录100extras/61dirs不清理，不改称原始干净。

## 加载与范围

342/2988已完整核验M2-1通过并收讫，31份36501字节普通原交付归档在kimi-role-host-deploy-20261026/pickup342；实际reuse_session/count3/末57.8171%，不输出原生ID。Kimi宿主MF-1和复核包已闭合，未称实际模型/真人页面通过。

生产预检：原runtime18784/五宿主serving、api_mode=external、shutdown idle、无running任务；大K原bound/choice、gen1未领取到期/无owner/can_start true。11文件Kimi补丁只做apply --check通过、未应用；公开配置差量为kimi.enabled=true及大K逐成员tools，未写配置。后台重载会加载339代码，故先闭合本原片。完成本复验后需刷新合并加载方案，再按一次具体正常重载许可操作，外部API归原终端、不另开API、不强杀/CAS/清锁、不重复创建大K。

本轮源在C隔离worktree，D生产源码/配置/服务未改。六binding/模式passive6/要求/用户自启动选择/250failed及2767未收取/286paused保持；不另派K3.1模型验证，后续首正式开发交新角色的授权保持。原一次后台停启授权不延伸，本次明确“先不重启服务”。
