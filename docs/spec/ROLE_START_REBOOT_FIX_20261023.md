# 重启后角色启停修复与改名按钮缩小

记录：2026-10-23 09:58（Asia/Shanghai）。基线 `adbeb5d`，当前Codex直接实施和自检，未派发开发/复核任务。

## 需求与实际原因

用户验收要求改名按钮缩小至原1/4，并优先修复重启电脑后所有角色启动/关闭卡住。现场原API为用户终端的独立uvicorn；原runtime9720/子进程13468已不存在，健康文件停于00:58。三个遗留owner不因重启自动释放，四个无owner角色也没有宿主领取请求。K3到期start仍在GET投影为starting。DSH旧manager PID1004已被系统进程复用；旧K2.8清单指向不存在的Key文件。

## 最终实现

- 改名按钮17×17、图标12px、间距8px，面积为原34×34的1/4；保留键盘焦点与aria-label。资源版本 `20261023-role-control-v4`。
- `.talk/runtime.local.json` 仅存本机私有清单路径和精确数据库绑定，Git忽略。显式统一入口会保存绑定；API启动/人类启停可确保独立管理器运行，管理器用OS锁防重并以external模式观察现有API，不接管API进程。隔离数据库不读生产清单、不启动生产宿主。
- GET按当前generation/launch/deadline投影启动超时，不写原回执；无owner失败可重试，已领取的旧归属继续保护。stop超时仍unknown，不伪造已停止。
- human关闭请求可对已绑定本机遗留角色做双次本地证据核验，使用原恢复计划/CAS并记录原human审计。原宿主存活则正常关闭；活进程/证据不明/活动任务/替代执行端/在途动作仍拒绝。GET、Agent或后台不会自动解除归属。
- OS启动时间与实际创建时间区分旧进程及PID复用；未知仍拒绝。CLI状态/stop也不能把复用PID当作控制权。
- 兼容旧API的 `idempotent_stopped=true` 与默认 `observed=stopping` 组合：前端确认已关闭，并强制完成一次资格刷新，避免启动按钮继续禁用或关闭中悬挂。
- 旧K2.8仅将既有role-key-file的失效路径替换为原本人文件；通过 `/api/members/me` 反查精确身份，原Key不复制/重签、不改模型/绑定。私有清单其余字段逐项相等，原Key mtime保持。

## 实际验收

用户两次在原终端正常退出/重启API加载核心修复。三个旧owner经本轮明确修复范围内的human普通关闭逐项恢复；原角色失败记录保留。

| 角色 | 本轮启动→关闭代际 | 本轮就绪实例 |
|---|---|---|
| agent:codex | 34→35 | `ins_e66cea66c51e` |
| agent:deepseek | 43→44 | `ins_c7dba67825d6` |
| agent:kimi | 28→29 | `ins_76ad735497a3` |
| agent:kimi-code-k28-preview | 29→30 | `ins_369b9d59cfde` |
| agent:prj-e8fe7066bbec.kimi-k2-8-7c1c334c | 23→24 | `ins_ee7f1a829ba2` |
| agent:prj-e8fe7066bbec.workbuddy-k3-61b7e314 | 14→15 | `ins_f5f68de4b6d3` |
| agent:workbuddy | 3→4 | `ins_7f8266b82e78` |

所有七个角色均真实ready、实例心跳、原宿主普通关闭并释放归属。另对Codex/DSH/新WorkBuddy启动采样35秒，三个实例周期心跳均推进，runtime12856与宿主保持。最终七宿主serving、七原生角色stopped/no owner/can_start=true。没有派发任务或调用模型。

现场Job证据：runtime实际解释器12856在Job中，其venv包装器4196不在Job；API解释器13512在Job中，包装器14684和终端11412不在Job。解释器单字段不能代表外层终端归属，[CPython启动器实现](https://github.com/python/cpython/blob/main/PC/venvlauncher.c)仅作机制参考，现场以OS父链采样为准。调查中按解释器单字段做额外脱离的候选隔离试验未收敛，候选逻辑已撤销，未部署；失败日志保留，最终隔离回归通过、探针进程0。

## 验证与保护

- 首轮相关Python115项通过（`unit-v2.log`）。最终宿主/实际隔离API启动与正常重启/本地恢复/PID专项31项通过（`verified-final.log`）；前端名称/服务37项通过（`node-final.log`）。首次导入错误及候选Job试验失败日志保留，不算通过证据。
- 七角色记录 `smoke.json`；周期心跳 `heartbeat.json`；父链 `job-inventory.json`；最终状态/保护校验 `final-current.json`。目录 `.tmp/role-start-reboot-fix/`。
- 314条任务逐行SHA相同，286暂停保持；名称“小C/小D/小K”等与全部原绑定保持。config.toml不改；私有运行清单仅旧K2.8文件引用一项变更。消息最大ID2955保持，无旧私信回放。
- 实际HTTP首页/JS/CSS与工作区文件SHA一致，语法与差异检查通过。未做Browser/computer-use或真实点击人验；全部是Codex自检。

## 当前边界与人验

当前API仍由用户原终端管理，后台管理器独立运行；不自动重启外部API，不安装开机任务/服务。完整API独立驻留可按统一入口正常切换。真实再重启电脑/结束聊天后的复查未发生，不能将本轮采样冒称最终驻留通过。原生模型/桌面控制能力不在本轮扩展范围。

请Ctrl+F5刷新，用人类账号检查按钮大小、逐角色启动/关闭，以及关闭后重新启动。若有遗留归属，可再次明确点击关闭，由本机证明/CAS处理；核验失败会保留归属并提示。未获下一无关切片授权。

## 2026-10-23 10:44 后续人工验收与额外Python窗口修正

用户明确上一轮验收通过，实际重启电脑后角色服务能正常启动。此为电脑重启后人工验收事实，不重写此前未验状态的时间语义。

新增截图反馈为启动TALK多出 `.venv/Scripts/python.exe` 黑色窗口。隔离原策略得到console=true/visible=true，新策略得到console=false/visible=false且模块导入/退出正常；无控制台父进程的原子进程策略也能继承无控制台。仅将 `server/local_runtime.py` API自启动入口及 `scripts/talk_runtime.py` 显式detach入口的DETACHED_PROCESS替换为CREATE_NO_WINDOW，保留其余创建标志。没有把历史原生角色路径的DLL限制外推为本入口限制；原生角色spawn_hidden行为保持。Windows的NO_WINDOW与DETACHED不能叠加，参见[Microsoft创建标志说明](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)。

新增回归通过隔离辅助进程只附加到本次用例自己创建的runtime检查控制台，权限不足/进程不存在不能当作无控制台。旧版本先复现失败；修正后24项Python通过，覆盖自动拉起和显式detach的真实运行/无控制台/正常API重启及单实例/正常停止。证据 `probe-results.json`、`nested-results.json`、`before.log`、`after.log` 均在 `.tmp/no-console-fix/`。失败用例退出顺序已修正，已删除配置导致不能正常drain的唯一空宿主临时进程经精确路径/PID核对后清理，生产进程未触碰。

用户手册、启动指南、进度同步。该修正后台管理器完整退出后、再次启动TALK生效；未热替换当前生产进程，未为窗口调整停角色/解除owner，未改生产Key、模型、绑定或历史任务。当前窗口未宣称已关闭，视觉效果待用户正常重启后复验。
