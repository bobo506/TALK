# Project Progress

Updated: 2026-10-23 10:44（Asia/Shanghai）。用户明确上一轮验收通过，电脑重启后能正常启动角色服务。新增反馈“启动TALK额外弹出Python黑色窗口”已由Codex直接修正、自检，后台管理器完整退出后再次启动生效；窗口视觉待用户复验。

## 当前职责与范围

- 当前Codex `agent:codex / prj_e8fe7066bbec / lead` 直接修正和收尾，未派DeepSeek/Kimi/子代理，不称独立复核。Kimi开发暂停、286保护及下一无关切片先确认保持。
- 上片 `ed5842a` 的按钮缩小、角色启停和电脑重启后启动已获用户人验通过。跨聊天持续驻留没有额外实测，不据此扩展证明。

## 本片完成与验证

- 根因已隔离复现：Windows分离启动的venv包装器会另建可见解释器控制台，SW_HIDE不能保证整个子链无窗口。两个后台入口改用CREATE_NO_WINDOW，去掉互斥的DETACHED_PROCESS；分组/显式detach的BREAKAWAY、原日志文件及生命周期保持。
- 仅改API→runtime入口和显式detach入口，原角色spawn_hidden创建策略不改。真实隔离自动启动/显式detach均为console=false/visible=false，模块加载、正常运行、API重启/单实例和正常停止通过；24项Python通过，语法/差异检查通过。证据 `.tmp/no-console-fix/`。
- 原代码新增控制台断言先复现失败；探针与失败证据保留，失败隔离用例的进程已限定清理。本轮未读生产Key、改绑定/模型/配置/历史任务，未启停生产角色或解除owner。

## 当前部署边界

- 新显示方式在后台管理器完整退出后、再次启动TALK时生效；没有热替换当前生产API/runtime，也没有宣称当前已打开的窗口已关闭。原终端启动API仍由原终端显示日志，后台管理器不额外开Python窗口。
- 用户已重启电脑，旧09:58的runtime12856等PID仅为历史，不能拿作当前运行事实；本轮未重新探测生产进程/角色。当前角色状态以用户实际页面为准。
- 上片314任务/286/角色名称/模型/Key保护证据及七角色实测保持历史语义。详细范围见[修复记录](spec/ROLE_START_REBOOT_FIX_20261023.md)和[启动指南](guides/TALK_RUNTIME.md)。

## 下一步

- 用户下一次正常启动TALK时复验不再弹出额外Python窗口；原终端日志入口保持。当前授权范围内若仍有问题由Codex直接修正，下一无关新片先确认。
- 本轮基线 `ed5842a`，产品/文档随本片Git提交与常规推送收尾。历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
