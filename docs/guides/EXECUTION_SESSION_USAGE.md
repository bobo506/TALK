# 连续任务的原生会话复用

2026-10-22：已接通当前 DeepSeek/DSH 链路，292已完成代码实查、修正和必要实机验证，用户已明确TALK页面不改，只需确认同功能任务进入角色同一原生会话；296/297原生文件已满足该核实口径。生产293→294已复用同一原生会话；295主动换窗并恢复基础介绍。60%与缺数10/11边界使用安装版DSH配假模型响应验证，未为撞阈值消耗真实模型长上下文。

## 选择规则

先由任务发起者判断是否属于同一功能工作线，再检查上下文：

- 同一工作线、角色、发起者、项目、工作区、基础合同、运行配置及服务代次均可核时，可靠占用低于60%续用；达到或超过60%，下一次投递前新建会话。
- 仅指标单纯不可得且窗口身份、来源和完整计数可信时，最多累计10次实际交办，第11次新建会话。首轮计1；工具、预检和未送达失败不计；重复回执不重计；送达后的模型失败不倒扣。
- 指标恢复不会清零计数；可靠低占用可以超过10次。身份/来源异常、非法值、配置变化或送达不明不能借十次规则强行续用。
- 不同工作线或显式`force_new=true`可以提前换窗。在途任务不会因越过60%被强杀。

“同窗”指底层DSH原生会话。每个TALK任务仍有独立任务号、Hall、交付和收取记录，网页“查看完整对话”仍打开该任务Hall。桌面GUI显示/手工续写与缓存费用收益不在本次验证结论内。

## 首轮完整，续轮只给增量

首轮提供完整`base_context`：项目背景、实际角色、范围与权限、固定规则、交付格式和恢复所需信息；本次工作写在`content`。保存服务端返回的基础任务ID。

续轮只提供稳定的`continuity_key`、首个`base_task_id`及本轮`content`；可附基线、授权或验收差异。发起者不用再生成完整背景。bridge仅在新原生窗口首轮取回并投递完整基础介绍，续轮不会补回固定介绍或旧任务Hall历史。自动或主动换窗时，从冻结基础合同恢复完整首轮。

服务端统一为REST/SDK/MCP冻结派发时的项目开发要求：只在基础合同附一次，逐任务另存私有审计快照，公开响应仅保留摘要哈希。项目要求变化后，旧基础引用返回422，应按新要求创建基础任务；不能默默沿用旧规则。正文不按标题子串删除或猜测去重。原模型只读预检仍在独立、非持久化spawn中执行，必要时读取完整基础合同；它不进入正式窗口或增加交办次数，这部分模型开销仍存在。

## 实际入口

支持绑定为`bound`、`runtime=dsh`的普通顶层`general`任务，当前核验原生版本为`0.1.5-rc.2`。项目须登记绝对`project_root_path`，并与bridge实际工作目录一致。其它runtime以及子任务、review/test/rework保持原路径；不支持的执行会话选择会明确拒绝。

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

会话复用不代替逐片确认、独立复核、人工验收或任务权限。每个原生进程及MCP连接均按本次任务新建，保留本次任务/Hall/权限控制信息；旧原生历史由DSH自己恢复。

## 查看与故障处理

`GET /api/tasks/{id}`或SDK `get_task`返回`execution_session_state`，可核验`native_session_id`、`reused/first_turn`、`decision`、`confirmed_count`、送达/轮次结果及`last_snapshot`。后者包含实际token数和容量；未知不填0%。`context_status`说明本轮投递前的规划读数，`last_snapshot`是本轮结束后的观测，两者时点不同。`GET /api/tasks/{id}/execution-session-base`只对该任务双方返回冻结基础合同。

本地`.talk/execution-session-store.sqlite3`持久记录窗口、通道、尝试、计数、快照与回执；不存助手正文。相同任务尝试重复进入会在再次调用模型前拒绝；计数、回执和尝试确认原子提交。未知送达、取消或租约丢失使旧窗口不可续用，不自动重跑模型。普通角色重启改变launch后新开窗口，不接管旧进程/旧launch；崩溃遗留且原生writer不能证明退出时保守阻止通道接管，需要核查，不能删除账本或清零绕过。

成功spawn传输文件默认清理，失败证据保留。可用`TALK_EXECUTION_SESSION_STORE`指定绝对sidecar路径；`TALK_EXECUTION_SESSION_RETAIN_SPAWNS=1`仅供必要取证；指标新鲜度默认21600秒（与任务执行超时/MCP客户端上限分别解释）。headless实际MCP工具上限T仍未核验，本功能不启用主动长等待或自动唤回。

本机运行已加载：原manager18856保持，DeepSeek普通stop/start到generation30；原API正常重载，4个可空列只新增、不回填旧任务。本项目根路径从空登记为`D:\claude-test\TALK`，角色模型/Key/HOME/绑定和286暂停保持。293/294同ID且计数1→2，295新ID且计数1，三条均成功收取；两次均能在增量中回想基础验证码。

用户重连MCP后的补验：296首条要求记住“青竹47”，回复“已记住”；297仅引用base_task_id=296并询问暗号，没有重发暗号或基础介绍，回复“青竹47”。两条原生ID均为`session-357a3c78-7ddc-47a0-bcb9-745a57cda64c`，计数1→2，第二条`reused=true/context_status=known`，两条均已正常收取。最终指标21447/1000000，属于低占用；该证据证明底层原生会话续用，桌面GUI显示仍由用户观察。

### 页面任务厅与原生会话

目前TALK按任务分别创建Task Hall，296和297仍显示为两个任务窗口；页面未显示原生会话ID、复用/换窗状态、关联任务或同会话连续记录，因此仅靠当前页面无法核验是否续用。

受管DeepSeek以headless运行，使用独立`DSH_HOME`：本机为`C:\Users\Administrator\.talk\role-service-host\native\prj_e8fe7066bbec\agent_deepseek\.dsh`。原生会话在其`sessions/<工作区目录>/<native_session_id>/session.v3.jsonl.zstd`中；默认`~/.dsh`目录未发现本次会话。若用户现有DSH界面使用默认目录，它不会自动显示受管目录里的会话，也不会因headless任务自动弹窗。

2026-10-22只读补核：同一原生文件含41条记录，原生记录9/28为第一条业务正文/最终回复，36/38为第二条业务正文/最终回复。可读摘录在`.tmp/execution-session-usable-v1/independent-review292/visibility-296-297/native-conversation-excerpt.txt`，仅提取本测试正文和最终回复，不是完整对话导出。用户随后明确取消TALK页面改动，以角色原生会话是否连续为核实口径；上述同文件两轮记录已证实，页面展示差异不再作为本功能待补项。任务厅继续独立保留。

人工验收：在任务列表查看293、294、295及296、297的结果；按上面的参数使用同一功能连续交办，核对任务响应的native ID/计数和首轮/续轮变化。完成后确认本里程碑；下一片宿主统一启动问题仍需单独确认。
