# 会话机制第四片：DSH实机入口与采集器挂载核验（291）

2026-10-21 21:53（Asia/Shanghai）。用户明确回复“确认，派给DeepSeek”，291已创建，发起者agent:codex、执行者agent:deepseek，项目`prj_e8fe7066bbec`，独立Task Hall `group:task-50fe771b347747e6a8be8677e455511b`。创建回执为queued/assigned；本轮不主动等待或据此宣称执行完成。

## 本片目的与已确认顺序

核实当前受管DSH的入口、版本、无凭据配置/插件证据和289采集器可挂载位置，形成可直接实施的最小接线方案及隔离验收步骤。本片只读核验与方案，不加载采集器、不启停服务、不改配置、不调用额外模型或原生CLI。用户要求先回到会话复用功能；宿主随TALK统一启动的问题在291完成并收尾后优先处理，本片不提前混入修复。

288/289/290均已完成离线集成，290已completed、产品57cb119与280项既有离线验证保持。仍按同功能/工作线及身份配置先验、可靠<60%续/≥60%下一次新窗，只有单纯缺数且完整可信计数时才十次备用；首轮完整、续轮增量保持。真实加载、原生续用、任务/MCP/API接线和ACK存储未实现，本片不将方案写成上线。

## 基线、身份与隔离

- Git基线`67b1a58a6b38e0fa1a4e5e0020f7e01e05ead9c1`；实际MCP caller为agent:codex/agent、业务lead。页面开发要求仍旧交叉复核，原样快照保留；按AGENTS最新分工，由DeepSeek首次执行/自测/交付后暂停，Codex独立实查并直接修正，不派Kimi或追加返修/互审。
- 21:48只读核DeepSeek manager18856/bridge22812、实例`ins_ffc603d6fc88`、launch `6ca1765d-7fd0-4cfa-b3f6-a5179b32c8fa`，running/ready、idle/无任务；派发前最新MCP仍idle。配置/绑定、286整行及暂停、其它四角色记录保持，原模型配置deepseek-flash/max未改。
- 根`.tmp/execution-session-live-entry-s0/`，30份公开项目材料、57份公开安装源码及shim共1,835,498字节逐SHA冻结，详`coordination/manifest.json`。baseline/project、baseline/native、baseline/shims及coordination只读，执行者唯一可写deepseek/**。协调文档由Codex独占，不并行改产品。
- `entry-facts.json`关联当前实例/launch及脱敏命令事实；`config-projection.json`仅投影指定HOME级/profile级文件的插件声明、布尔开关、选定工具超时和profile bundle元数据，不保留完整配置/环境/凭据。原生HOME来源是已核宿主声明及启动回执，没有读取进程环境。
- 磁盘包为0.1.5-rc.2，但捕获时bridge空闲、没有原生子进程，不证明执行字节或实际挂载树。配置投影的空plugin_declarations不表示没有插件；缺层、动态include或未提取到的语法保留未知。完整原包与创建回执在coordination，不追改既有失败证据。

## 范围与验收

1. 事实表关联member/project/实例/launch与受管模板、headless/argv、磁盘解析链；区分进程事实、声明、磁盘版本和未证明的已加载内容，提供公开源码行号/SHA。
2. 根据公开源码追踪profile、bundle、用户patch、--patch与插件加载顺序，说明白名单投影能证明的有效配置及剩余未知；给出289 track/read/untrack的精确文件/函数/生命周期位置。
3. 最小接线方案须说明事件发生前挂载、身份/配置/cut与连续性、旧回调/缺口/解除监听、bridge传输白名单、289/290真实schema入口、隔离与回滚；若无适合挂载点，给源码阻断与最小候选路径，不擅自换运行器/模型。
4. 下一实现片的隔离验收须覆盖合成原生service/projection→实际采集器→Python适配→统一内核，以及59.9/60、缺样本/容量、非法/错身份/事件冲突、busy、首轮、10/11和读数恢复不清零。方案不冒充已实现，不重复启动真实应用或无关全套测试。
5. 按[终端适配预算要求](../guides/TERMINAL_MCP.md#终端适配必查工具超时与等待预算2026-10-06)分开登记客户端T、未来显式W与返回余量、执行者21600预算及取消/同连接排队边界。headless T尚未核验，旧桌面65秒或bridge21600不能代替；本片无主动wait或长等待验收。

## 允许读取与禁止区

只读冻结材料及Codex脱敏事实。确需补读公开安装源码时，仅限已指定DSH安装树内的文本JS/package元数据/公开bundle YAML，先核真实路径未越界，额外副本和SHA只写deepseek/extra-public，不导入/执行应用。真实配置、原生HOME及进程环境不由执行者自行扩读；需要额外事实先暂停交Codex裁定。

禁止改正式源/文档/Git/AGENTS、配置/绑定/Key/HOME/profile/patch/插件开关、生产DB/owner/token；禁止启停API/宿主/角色、注册/恢复原生会话、执行dump-config等会初始化profile的命令、额外模型/CLI/ACP/Browser、主动wait、其它Agent/子任务。286继续queued/paused，不恢复/取消/收取/集成；Kimi及其它角色不动。

## 交付与收尾

deepseek/**内提交事实表、具体挂载/接线方案、验收清单、可追溯引用和必要静态/合成证据。交付完整talk-delivery-1 JSON、task_id=291，冻结workflow validate必须带expect-task-id；最终TALK正文为完整裸JSON，不能只给路径。Python -B -X utf8，文本写入显式UTF-8，失败证据不覆写。

交付即暂停，由Codex首次独立实查、直接修正和最终收尾。默认派发后结束，用户通知“291好了”再取件，不增加自动等待/唤回。本轮只派发与文档记录，产品代码未变，不重复执行280项离线测试；正式文档另做UTF-8、本地链接、原请求保留和冻结SHA检查。
