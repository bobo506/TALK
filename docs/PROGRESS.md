# Project Progress

Updated: 2026-10-23 00:49（Asia/Shanghai）。改名保存失败已修复：漏JSON请求头导致422，补齐后实际页面保存函数→apiFetch→HTTP验证200。29项Python、68项Node通过。另确认上片后台及原运行角色再次退出；只恢复API，三角色旧归属保留、当前unknown，跨会话驻留尚未解决。

## 当前职责与范围

- 当前Codex `agent:codex / prj_e8fe7066bbec / lead`，继续用户已授权片内发现问题后的自行修正/自检；不派DeepSeek/Kimi或子代理开发，不称独立复核。下一新片仍先确认，Kimi常规开发暂停与286保护保持。
- 本次只改角色名称提交的JSON请求头和具体失败提示，前端版本 `20261023-role-name-json-v2`；保原项目名权威、图标弹窗样式、全局名称/Key/模型/绑定。用户实际失败是Codex角色PATCH于00:41:05—07返回422，并非重名或权限问题。
- 原测试仅mock apiFetch、绕过真实请求封装，漏测Content-Type。新增真实保存函数→实际apiFetch→Node fetch→隔离HTTP回归先复现失败，再验证改名成功且全局名不改。新增格式/权限提示测试，失败保草稿可重试。29项相关Python、68项Node通过，语法/差异检查通过。
- 已从实际API获取页面代码，用合法human凭据对Codex进行同名保存：缺请求头422、修正后200，原名称保持；没有替用户决定新名称。静态资源与当前源码一致、首页新版本已提供，无需重载API/原生角色来加载这个前端修正。证据 `.tmp/role-name-save-fix/`。

## 后台真实现状（优先于上片00:31运行状态）

- 核验时8000端口不可达；旧runtime健康最后00:41:31为api_exited，23816/11220、三个原manager1004/20236/21444及bridge5680/7900/17768均OS确认absent。退出原因仍未确证。上片182秒/重载采样是当时通过，不能作为跨会话持续驻留通过的证据。
- 为验证改名，沿同一清单正常恢复入口：实际runtime9720、API子进程Popen13468，worker正常。DSH/Codex/新WorkBuddy旧owner仍在，入口按守卫报告recovery_required；三原生角色均unknown，**没有自动解除归属或重启**。另外三个Kimi及旧WorkBuddy原生角色仍stopped/no owner，其四宿主仅待命。
- 原314条任务逐行SHA、286暂停、配置/Keymtime/原模型及认证源、绑定保持。新WorkBuddy项目名仍WorkBuddy-k3，旧WorkBuddy接入验证身份保留；本次同名保存仅Codex项目角色普通updated_at更新，名称未改。
- 后台跨会话驻留及三角色逐个恢复仍待处理，不能宣称已稳定常驻或自动解除旧owner。下一片先说明进程所属Job/退出链诊断、独立后台启动方案及精确人工恢复范围并获确认；不安装开机任务/服务，不扩大此前DSH单次CAS授权。

## 已有工程证据与人验

- 四类运行器DSH/Codex/Kimi Code/WorkBuddy独立CLI的会话复用、60%及条件10/11、基础恢复/原生SHA与任务293—314证据保持；K2.8/K3共用适配。不是桌面窗口控制或主动MCP等待验收。
- 上片主体1b8e10d、收尾b81808c已推送，368项Python/67项Node及隔离/生产进程证据为当时事实；误触发旧私信回复2953—2955保留，游标防回放修正保持。详[上片记录](spec/ROLE_HOST_NAME_HEALTH_FIX_20261023.md)、[统一启动](guides/TALK_RUNTIME.md)。
- 用户人类账号Ctrl+F5后重试铅笔改名；本次没有使用Browser/computer-use，不把真实函数/HTTP验证称视觉/真实点击人验通过。后台三角色待核实属于已确认的后台退出事实，与本次422请求头错误分开。
- 本轮必要验证、进度/Git收尾后暂停。当前服务API可用，勿重放旧单次脚本、强杀/接管或自行解除归属；恢复指令 `继续项目`。历史见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
