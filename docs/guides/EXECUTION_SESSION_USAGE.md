# 连续任务的原生会话复用

2026-10-22 20:20：DeepSeek/DSH、Codex、Kimi Code及用户批准形态的WorkBuddy内置独立CLI实际任务链均已接通。Kimi K2.8/K3共用适配，303—308均已收取；WorkBuddy309→310同原生ID/计数1→2，311新ID恢复基础/计数1，三条生产派发/领取/交付/收取通过。WorkBuddy403项联合自检及安装版16次正式投递边界通过。验后WorkBuddy及三个Kimi角色停止、无owner，临时宿主已退出；Kimi常规开发暂停。另一K2.8成员未单独实机；TALK页面保持。真实模型为低占用，60%/缺数10/11边界按受控证据说明，人工里程碑待确认。WorkBuddy结论限于独立CLI，不等同控制原桌面窗口。

## 选择规则

先由任务发起者判断是否属于同一功能工作线，再检查上下文：

- 同一工作线、角色、发起者、项目、工作区、基础合同、运行配置及服务代次均可核时，可靠占用低于60%续用；达到或超过60%，下一次投递前新建会话。
- 仅指标单纯不可得且窗口身份、来源和完整计数可信时，最多累计10次实际交办，第11次新建会话。首轮计1；工具、预检和未送达失败不计；重复回执不重计；送达后的模型失败不倒扣。
- 指标恢复不会清零计数；可靠低占用可以超过10次。身份/来源异常、非法值、配置变化或送达不明不能借十次规则强行续用。
- 不同工作线或显式`force_new=true`可以提前换窗。在途任务不会因越过60%被强杀。

“同窗”指执行角色的底层原生会话。每个TALK任务仍有独立任务号、Hall、交付和收取记录，网页“查看完整对话”仍打开该任务Hall。桌面GUI显示/手工续写与缓存费用收益不在本次验证结论内。

## 首轮完整，续轮只给增量

首轮提供完整`base_context`：项目背景、实际角色、范围与权限、固定规则、交付格式和恢复所需信息；本次工作写在`content`。保存服务端返回的基础任务ID。

续轮只提供稳定的`continuity_key`、首个`base_task_id`及本轮`content`；可附基线、授权或验收差异。发起者不用再生成完整背景。bridge仅在新原生窗口首轮取回并投递完整基础介绍，续轮不会补回固定介绍或旧任务Hall历史。自动或主动换窗时，从冻结基础合同恢复完整首轮。

服务端统一为REST/SDK/MCP冻结派发时的项目开发要求：只在基础合同附一次，逐任务另存私有审计快照，公开响应仅保留摘要哈希。项目要求变化后，旧基础引用返回422，应按新要求创建基础任务；不能默默沿用旧规则。正文不按标题子串删除或猜测去重。只读预检仍在独立spawn中执行，必要时读取完整基础合同；它不进入正式窗口或增加交办次数，这部分模型开销仍存在。Kimi原prompt预检可以保留独立原生记录，不将其当作正式窗口轮次。

## 实际入口

源码及已加载API支持绑定为`bound`且`runtime=dsh/codex/kimi-code/workbuddy`的普通顶层`general`任务。实机版本为DSH `0.1.5-rc.2`、Codex `0.163.0`、Kimi `2.0.2`、WorkBuddy `5.8.3`内置CodeBuddy Code `2.161.0`。Kimi和WorkBuddy已完成生产任务链，验后停止；适用各自已核验的本地命令/模型/权限组合。项目须登记绝对`project_root_path`，并与bridge实际工作目录一致。其它runtime以及子任务、review/test/rework保持原路径；不支持的执行会话选择会明确拒绝。

REST `POST /api/tasks`、异步`TalkClient.create_task`、同步`TalkClientSync.create_task`和MCP `talk_delegate_task`均支持可选`execution_session`。不传该字段时保持旧行为。MCP的既有长连接须重连并刷新工具目录，确认schema出现此参数；本次用户重连后MCP296→297已实际验证同窗、增量回想及计数1→2，SDK/API亦已验证可用。无需修改现有桌面MCP配置。

首轮MCP/REST请求示例（将示例值换为实际项目和工作线）：

```json
{
  "project_id": "prj_xxx",
  "target_member_id": "agent:deepseek",
  "title": "功能A第一片",
  "content": "本轮：实现指定范围，验收……",
  "execution_session": {
    "schema": "talk-execution-session-request-1",
    "version": 1,
    "continuity_key": "feature/a",
    "base_context": "完整项目背景、角色、固定规则、范围与权限、交付要求……"
  }
}
```

续轮使用相同项目/发起者/目标及工作线，将元数据改为：

```json
{
  "schema": "talk-execution-session-request-1",
  "version": 1,
  "continuity_key": "feature/a",
  "base_task_id": 123,
  "baseline_change": "本轮基线变化（可省略）",
  "authorization_change": "本轮授权变化（可省略）",
  "acceptance_difference": "本轮验收差异（可省略）"
}
```

`123`必须是首个基础任务；不能引用另一个续接任务或其它发起者的基础任务。提前换窗再加`"force_new": true`，不必重发完整介绍。基础内容、工作区或绑定发生变化时，应创建新的基础任务。

Python SDK示例：

```python
from TALK.client import TalkClient

async with TalkClient(base_url="http://127.0.0.1:8000", api_key=api_key) as client:
    first = await client.create_task(
        "agent:deepseek", "第一轮增量", project_id="prj_xxx",
        execution_session={
            "schema": "talk-execution-session-request-1", "version": 1,
            "continuity_key": "feature/a", "base_context": "完整基础介绍……",
        },
    )
    # 首轮交付、复核/收取并满足本项目逐片确认后，再创建续轮。
    next_task = await client.create_task(
        "agent:deepseek", "下一轮增量", project_id="prj_xxx",
        execution_session={
            "schema": "talk-execution-session-request-1", "version": 1,
            "continuity_key": "feature/a", "base_task_id": first["id"],
        },
    )
```

会话复用不代替逐片确认、独立复核、人工验收或任务权限。原生进程按本次任务创建，保留本次任务/Hall/权限控制信息；各运行器按明确ID恢复自己的旧原生历史。

## 查看与故障处理

`GET /api/tasks/{id}`或SDK `get_task`返回`execution_session_state`，可核验`native_session_id`、`reused/first_turn`、`decision`、`confirmed_count`、送达/轮次结果及`last_snapshot`。后者包含实际token数和容量；未知不填0%。`context_status`说明本轮投递前的规划读数，`last_snapshot`是本轮结束后的观测，两者时点不同。`GET /api/tasks/{id}/execution-session-base`只对该任务双方返回冻结基础合同。

本地`.talk/execution-session-store.sqlite3`持久记录窗口、通道、尝试、计数、快照与回执；不存助手正文。相同任务尝试重复进入会在再次调用模型前拒绝；计数、回执和尝试确认原子提交。未知送达、取消或租约丢失使旧窗口不可续用，不自动重跑模型。普通角色重启改变launch后新开窗口，不接管旧进程/旧launch；崩溃遗留且原生writer不能证明退出时保守阻止通道接管，需要核查，不能删除账本或清零绕过。

成功spawn传输文件默认清理，失败证据保留。可用`TALK_EXECUTION_SESSION_STORE`指定绝对sidecar路径；`TALK_EXECUTION_SESSION_RETAIN_SPAWNS=1`仅供必要取证；指标新鲜度默认21600秒（与任务执行超时/MCP客户端上限分别解释）。headless实际MCP工具上限T仍未核验，本功能不启用主动长等待或自动唤回。

本机运行已加载：原manager18856保持，DeepSeek普通stop/start到generation30；原API正常重载，4个可空列只新增、不回填旧任务。本项目根路径从空登记为`D:\claude-test\TALK`，角色模型/Key/HOME/绑定和286暂停保持。293/294同ID且计数1→2，295新ID且计数1，三条均成功收取；两次均能在增量中回想基础验证码。

用户重连MCP后的补验：296首条要求记住“青竹47”，回复“已记住”；297仅引用base_task_id=296并询问暗号，没有重发暗号或基础介绍，回复“青竹47”。两条原生ID均为`session-357a3c78-7ddc-47a0-bcb9-745a57cda64c`，计数1→2，第二条`reused=true/context_status=known`，两条均已正常收取。最终指标21447/1000000，属于低占用；该证据证明底层原生会话续用，桌面GUI显示仍由用户观察。

### Codex 入口与验收

Codex当前核验版本`0.163.0`，使用原受管命令、gpt-6.1-sol/xhigh、独立CODEX_HOME及read-only/never权限；以私有app-server stdio创建/明确ID续接，不连接桌面daemon或新增端口。版本、未知命令参数、HOME/模型/权限不符会拒绝，不自动降模型或改登录。其它Codex命令/权限组合需另核，不能沿用本次实际组合的验收结论。

同功能选择和参数沿用上方示例，目标换为`agent:codex`；请求者必须是另一个合法member。当前桌面MCP身份也为agent:codex，直接向同名目标派发会按既有规则400拒绝。本片真实验收由已授权human:bobo通过普通SDK/API创建并收取，未改变桌面身份或借用DeepSeek身份。MCP参数/双runtime分派已有隔离验证，不能把该桌面自派路径写成已通过。

Codex读原生最近请求`last_token_usage.total_tokens / model_context_window`，保留来源时间，不使用累计计费量。预检采用独立非持久化过程；只对经合同引用声明的续轮解释历史上下文边界，不跳过正常澄清，也不保证原生窗口一定能续用。正式原生UserMessage及指令SHA确认后才计数；原生延迟落盘、正常resume设置回执、自动AGENTS/环境介绍和工具调用均不计轮次。

实机300→301的原生ID为`01a162a3-eee4-7f63-b8d7-54ee978f0e71`，计数1→2，第二轮未重发暗号仍回复“海星84 / 银杏73”；302 force_new为`01a162a6-bdc5-7a30-978e-82fd55d2e9a6`，计数1并恢复“银杏73”。三条均完成收取，真实容量475000。原298首轮保留；299发现预检缺口后由原请求者取消，未正式投递，不追改失败。详[Codex实现与验收](../spec/EXECUTION_SESSION_CODEX_ADAPTATION.md)。

原Codex宿主已正常恢复、单角色重载到generation21，原模型/Key/绑定/权限保持；API正常重载且297条既有任务哈希保持。原DSH运行状态保持。MCP上限T未重测，不启用主动长等待；原任务执行预算、有限RPC和清理边界详验收记录。

### Kimi Code 共用适配与原生验收

K2.8和K3共用一套`kimi-code`适配，选择精确角色和已有模型别名即可；各角色、模型、工作线、HOME和计数仍隔离，不需要维护两套实现。当前仅核验CLI `2.0.2`；首次沿原Agent文件创建，续轮以明确`--session`恢复原生权限配置，配置或工具边界不符时拒绝。

实现已接入同一REST/SDK/MCP参数、基础合同、60%与条件十轮规则。原K3及旧K2.8均保原tools档，先各三轮原生验收，用户随后明确允许短文本生产验收、禁止开发派发。303→304的K3与306→307的K2.8均同原生ID/计数1→2、增量回想，305/308新窗完整恢复/计数1，六条均完成收取；容量1048576。验后三个Kimi角色停止，临时宿主正常drain；302条旧任务、原配置Key绑定权限和286保持。另一K2.8成员未单独实机，常规开发暂停。此前K3/review是隔离兼容验证，生产保持原权限。

正式送达须原生用户prompt与上下文消息双SHA相符；预检、自动介绍、工具及重复回执不计。指标使用原生上下文计数与精确模型配置的容量，`llm.request.maxTokens`为输出预算，不作窗口容量。Windows原生argv长度受系统限制，超限会明确失败，不截断基础介绍。详[Kimi实现、自检及待验范围](../spec/EXECUTION_SESSION_KIMI_ADAPTATION.md)。

### WorkBuddy内置引擎独立CLI

本机WorkBuddy5.8.3自带CodeBuddy Code2.161.0，作为独立`workbuddy`运行器接入；以原WorkBuddy.exe和包内CLI启动，不控制或续接原WorkBuddy桌面任务窗口。角色`agent:workbuddy`沿原身份Key/模型源`custom-local:kimi-k3`，会话HOME独立，不复制桌面模型Key或历史。REST/SDK/MCP参数同上，目标换为该成员即可。

309→310同原生ID`21ca2f60-7439-47da-82b8-a5a4c3d72fa7`、计数1→2，第二条只发增量仍正确答“青禾42 / 鹿鸣57”；311新ID`600b5ced-5e22-4db8-838e-62561b15733b`恢复基础“鹿鸣57”、计数1。三条已收取。真实占用取最近原生assistant `usage.totalTokens`，容量按精确模型`maxInputTokens`并核result `contextWindow`；本次容量1000000。正式用户ID/请求ID/正文SHA须同时匹配stdout、原生JSONL和最小proof；工具/预检不计数。

角色现为stopped/gen2/无owner，临时宿主已退出。需要使用时，先在项目根目录由已授权管理员手动启动窄宿主，然后从普通角色页启动“WorkBuddy接入验证”：

```powershell
.venv\Scripts\python.exe -B -X utf8 scripts/workbuddy_role_host.py serve `
  --project prj_e8fe7066bbec --member agent:workbuddy `
  --workbuddy-executable C:/Users/Administrator/AppData/Local/Programs/WorkBuddy/WorkBuddy.exe `
  --workbuddy-models-home C:/Users/Administrator/.workbuddy `
  --workbuddy-display-name WorkBuddy接入验证 `
  --role-key-file C:/Users/Administrator/.talk/agent-workbuddy.key `
  --operator-key-file D:/claude-test/TALK-private/operator.key `
  --runtime-verified workbuddy --apply
```

去掉`--apply`仅打印计划；不输出或重建Key。启停保持普通所有权/Popen守卫，不能按健康文件接管进程。独立原生文件在`C:\Users\Administrator\.talk\role-service-host\native\prj_e8fe7066bbec\agent_workbuddy\.codebuddy\projects\<工作区编码>\<session-id>.jsonl`；最小proof在同HOME的`talk-execution-proofs/`。原桌面窗口不会自动显示这些独立CLI会话。当前显式空MCP，不宣称WorkBuddy主动长等待通过。403项自检、16次安装版正式投递边界及生产证据详[WorkBuddy适配](../spec/EXECUTION_SESSION_WORKBUDDY_ADAPTATION.md)。宿主随TALK统一启动仍为待单独确认的下一片。

### 页面任务厅与原生会话

目前TALK按任务分别创建Task Hall，296和297仍显示为两个任务窗口；页面未显示原生会话ID、复用/换窗状态、关联任务或同会话连续记录，因此仅靠当前页面无法核验是否续用。

受管DeepSeek以headless运行，使用独立`DSH_HOME`：本机为`C:\Users\Administrator\.talk\role-service-host\native\prj_e8fe7066bbec\agent_deepseek\.dsh`。原生会话在其`sessions/<工作区目录>/<native_session_id>/session.v3.jsonl.zstd`中；默认`~/.dsh`目录未发现本次会话。若用户现有DSH界面使用默认目录，它不会自动显示受管目录里的会话，也不会因headless任务自动弹窗。

2026-10-22只读补核：同一原生文件含41条记录，原生记录9/28为第一条业务正文/最终回复，36/38为第二条业务正文/最终回复。可读摘录在`.tmp/execution-session-usable-v1/independent-review292/visibility-296-297/native-conversation-excerpt.txt`，仅提取本测试正文和最终回复，不是完整对话导出。用户随后明确取消TALK页面改动，以角色原生会话是否连续为核实口径；上述同文件两轮记录已证实，页面展示差异不再作为本功能待补项。任务厅继续独立保留。

人工验收：在任务列表查看293、294、295及296、297的结果；按上面的参数使用同一功能连续交办，核对任务响应的native ID/计数和首轮/续轮变化。完成后确认本里程碑；下一片宿主统一启动问题仍需单独确认。
