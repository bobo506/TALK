# 288会话内核首次独立实查与集成

更新：2026-10-20 22:20（Asia/Shanghai）。结论：DeepSeek首次候选经Codex独立实查、直接补正和自检后集成；288已正常收取`completed`。本片只完成离线规则/提示内核，整项会话机制未接通、未部署。

## 身份、原件与范围

- 用户通知“好了”后取件；MCP本人`agent:codex`/agent，项目`prj_e8fe7066bbec`，DeepSeek为idle/无当前任务。页面开发要求仍为旧交叉复核文字，按AGENTS最新分工处理，不改页面、不派Kimi或返修。
- 288创建者`agent:codex`，执行者`agent:deepseek`；结果2894为合法`talk-delivery-1`、task_id匹配、原complete自报，runner为succeeded/submitted。自报仅为索引，独立检查实际模块/测试后才验收。
- 产品基线`48526a7851561cd81a42deb3bb82652105df2089`；22份冻结文件逐份SHA保持。7份执行者原产物原位保留并记SHA，没有覆写候选、原README、交付JSON或原测试日志。MCP原文两页按稳定SHA拼接，与本地delivery.json语义一致。
- 正式新增`bridges/execution_sessions.py`、`tests/test_execution_sessions.py`。未修改原bridge/host/API/MCP/schema/配置，不做真实会话/日志读取、CLI/模型探针、Browser或服务启停。生产路径无新模块导入。

## 实查发现与直接补正

1. **无候选绕过当前通道检查。** 原候选只在有candidate时检查独占，无candidate直接产出可投递新窗。新增独立`execution_channel`输入，所有投递先确认当前目标通道ready、无writer且独占；未知/busy返回无正文的wait。旧候选的可用事实不能用于当前新作用域。
2. **续轮仍要求并复制完整基础正文。** 原入口每轮必须传正文，archive每次再复制一份。改为续轮可只给版本/SHA引用，archive也只留引用；完整正文由未来接线层保存一次并在重建时显式提供。需要新窗但无正文则明确拒绝，取回匹配正文再规划，避免新窗误发增量。新/续轮实际正文与action一致。
3. **非法Unicode可直接抛编码异常。** 标识/任务/基础文本加入UTF-8合法性校验，返回不含原文的拒绝；候选非法ID不能当已核实会话。
4. **留档重建未核对投递回执。** 重建现在核对合同引用、模式、投递SHA/字节长度；任务权限或Hall内容修改后不能沿用旧投递摘要重建。

原60%整数比较、projected优先且非法不回退、未知不当0、作用域/launch/会话代次/基础合同隔离、不同task同工作线可续、候选busy守卫和新Hall边界经实查保持。真实指标来源仍是调用方事实，统一输入不证明token-meter分子/容量是同次原子采样；接线必须分别核实来源和新鲜度。

## 验证与证据

证据根`.tmp/execution-session-core-v1/independent-review288/`：

| 项目 | 结果及证据 |
| --- | --- |
| 原候选复跑 | 原98项全通过；`original-tests.txt`。未重写开发者原日志 |
| 独立初始反例 | 6项为1失败/5异常；`before-fix.txt`。包括无候选实际绕过、缺少显式当前通道/引用接口及非法Unicode异常；缺接口的TypeError不称线上运行故障 |
| 修正后自检 | 正式106项全通过，0失败/0错误/0跳过；`final-tests.txt`。包含原98项适配及8项新增回归 |
| 独立反例复跑 | 原6项针对性探针全过；`after-fix.txt` |
| 阈值独立交叉核验 | 容量1至2000、零值/容量/超容量及60%邻点共11,994组，与整数规则一致；`verification.json` |
| 原件/冻结/MCP | 7原件、22冻结SHA均一致，2894正文SHA与本地JSON一致，无本片pycache；`original-hashes.json`、`mcp-original*.json`、`verification.json` |
| 无接线边界 | AST标准库依赖检查及bridge/server/scripts/TALK的静态导入检查通过，生产导入为空；`verify.py`、`verification.json` |
| 收取 | 22:19正常collect，workflow completed、结果2894保持；`collect-receipt.json` |

初始探针第一次运行因审查脚本根目录层级写错未载入模块；纠正脚本后重新执行形成上述`before-fix.txt`，该失败不计产品缺陷。后续自检结果只称Codex自检，不称另一执行者独立复核。原自报不追改；没有跑无关完整产品回归。

## 文档与后续

新增[内核调用说明](../guides/EXECUTION_SESSION_KERNEL.md)，明确当前通道输入、引用留档、重建及完整正文取回边界；更新[首片状态](EXECUTION_SESSION_CORE_SLICE_1.md)、[总体需求](EXECUTION_SESSION_WINDOW_REQUIREMENTS.md)、简报/模块/排期和进度。用户手册继续明确没有真实操作入口，离线内核不冒充已上线设置。

下一片建议先接DSH上下文指标的最小适配与脱敏来源证据：核验实际版本/有效入口，将可关联会话、模型、修订和各字段时刻的真实数值送入统一样本；先不启用原生会话续用或MCP派发。缺失/过期保持未知。该片目的、范围、权限与验收需先确认，当前没有派发或实施；原生会话/锁/ACK/任务接线及生产加载也未获本次自动开片授权。
