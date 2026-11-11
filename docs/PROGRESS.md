# Project Progress

## 收工快照（2026-11-12 00:45，W-D1 第 3a 片完成）

- **W-D1 第 3a 片「登记元数据与身份快照」完成（669 failed → 670 Terra / 671 K2.8 approved）**：新增表 `workspace_registrations`（`project_id` 主键、`revision` 默认 1、可空身份 platform/volume/file_id/collected_at、`updated_at`；不存路径/Key/主机名），`server/models.py` +14 行、`server/db.py` +1 行幂等索引；新增 `server/workspace_registry.py`（81 行：`get_registration`/`ensure_registration`/`save_identity` CAS）与 `tests/test_workspace_registry.py`（129 行）。旧库 `create_all` 只新增表（实测 38→39 表、既有表 schema/行全等）；**启动路径零调用、不自动回填**；CAS 冲突零写入；模块不自行 commit。
- **验证（671 独立复核）**：10 项全 pass、`new_failures=[]`；独立重跑 registry 5 项 3.884s OK、回归三包 31 项 5.492s OK（skipped=1 仅 8.3 平台不支持）；旧库迁移/无回填/CAS/身份校验均实证。
- **非阻断建议（留 3b）**：① `identity_platform` 应只保留 `os.name` 值（`nt`/`posix`），删除 `windows` 别名（当前表空、零迁移成本）；② Windows 文件 ID 可达 2^64-1，当前 2^63-1 上限会 fail-closed 拒收部分合法身份，需文档化或改无损存储；③ `save_identity` 对“未登记行”与“revision 冲突”同报 `workspace_revision_conflict`，3b 公开入口应区分或文档化。
- **669 失败记录**：Codex 运行时瞬时失败（PATH alias 警告，无代码产出）；按用户确认重试为 670 成功，未自动连续重派。
- **提交与推送**：四文件 + 本文档，随本片推送。
- **下一步**：第 3b 片「操作日志 + 阶段机 + 故障注入 + 恢复」，仍**不开放**提交入口；完成后才做第 4 片受保护提交入口与登记收口、第 5 片页面。
- **恢复**：说“继续项目”；先读本快照与 `PROGRESS_HISTORY.md` 顶部记录。

## 收工快照（2026-11-11 23:15，W-D1 第 2 片完成）

- **W-D1 第 2 片「只读诊断 API」完成（667 Terra / 668 K2.8 approved）**：新增 `server/routes/workspace_diagnostics.py`（134 行）与 `tests/test_workspace_diagnostics_api.py`（242 行），`server/main.py` 仅 +2 行注册路由。提供 `GET /api/projects/{id}/workspace-diagnostics`（根状态/身份/marker/issue、跨项目重复、`duplicate_check`、`binding=not_checked`）与 `POST /api/projects/{id}/workspace-relink-preview`（只读候选评估 + `blocked_reasons`，**不发 token、不写文件、不做 CAS**）。鉴权与既有入口一致或更严格（trusted 模式不自动建 operator）；marker 回显清洗、identity 剔除主机名、revision 为 sha256 摘要。
- **验证（668 独立复核）**：10 项全 `pass`、`new_failures=[]`；独立重跑 API 9 项（1 skip：8.3 本卷不支持）0 失败 1.656s，回归 22 项 0 失败 3.754s；8 种预览情形（含“旧根缺失→弱证据、不报强”）、只读快照与 DB 行数不变、`ensure_local_runtime` 未被调用、无 500/无敏感回显均实证。
- **非阻断注记**：`_human` 未填 `request.state.member_id`（仅影响访问日志可观测性）；preview 的 `duplicate_projects` 反映登记根重复、候选冲突在 `conflict_project_ids`（语义已在复核中确认自洽）。
- **本片无用户可见变化**；666 的 blocked 与裁定（强匹配留持久身份片）已记录。
- **提交与推送**：三个文件 + 本文档，随本片推送。
- **下一步**：第 3 片「重关联存储与事务内核」（身份快照 + 操作日志 + 阶段机/CAS + 故障注入，仍**不开放**提交入口）；需先确认范围，可能拆成 3a 存储/迁移与 3b 事务/恢复。
- **恢复**：说“继续项目”；先读本快照与 `PROGRESS_HISTORY.md` 顶部记录。

## 收工快照（2026-11-11 22:40，W-D1 第 1 片完成）

- **W-D1 第 1 片「只读诊断内核」完成（664 Terra / 665 K2.8 approved）**：新增 `server/workspace_diagnostics.py`（167 行）与 `tests/test_workspace_diagnostics.py`（158 行）。`inspect_root`（根状态 + 物理身份 + marker）、`detect_duplicates`（按卷+文件 ID 判同一物理目录）、`evaluate_move`（身份一致=强、仅标记=弱、标记冲突、不可验证）；身份不可得（`st_ino==0`/非整数）→ `workspace_identity_unknown` 且不参与“无重复”结论；marker 读取 64KiB 上限、拒绝链接/reparse、只取 `project_id` 标量。**本片无 API/DB/UI 改动，无用户可见变化。**
- **验证（665 独立复核）**：10 项全 `pass`、`new_failures=[]`；复核机 **0 skip** 重跑 `tests.test_workspace_diagnostics` 10/10（0.202s）、`tests.test_workspace_paths` 12/12（3.434s，既有守卫未放宽）；真实 junction/8.3 短名/大小写/symlink 判同；零副作用快照与 marker 链接拒绝均实证；`py_compile`/UTF-8/diff-check 通过。
- **边界**：`workspace_binding_*` 属后续切片；检测非原子、无硬超时、机器名非全局机器身份（设计已接受）；664 交付机 3 项 skip 因环境不支持，复核机已补足。
- **提交与推送**：两个新文件 + 本文档，随本片推送。
- **下一步**：第 2 片「只读诊断 API」（单项目 `GET /api/projects/{id}/workspace-diagnostics`、候选预览只读部分、分页/权限），需先确认范围。
- **恢复**：说“继续项目”；先读本快照与 `PROGRESS_HISTORY.md` 顶部记录。

## 收工快照（2026-11-11 22:10，W-D1 设计片完成）

- **W-D1 设计片（660 Terra 设计 / 661 K2.8 复核 / 662 返修 / 663 定向复验 approved）**：新增 [WORKSPACE_REGISTRATION_DESIGN.md](spec/WORKSPACE_REGISTRATION_DESIGN.md)（94 行，27,546 B，sha256 `805e9dbb…`，71 处 `path:line` 引用全部可解析、0 缺失/0 越界）。内容：现状盘点（带文件:行号）、四类判定（重复/缺失/移动/绑定失效，含稳定码与 unknown 区分）、检测+重关联 API 与页面合同、数据迁移与跨文件恢复/`recovery_required`、测试计划、5 个实现切片、5 项待裁决问题。**尚未实现**。
- **复核过程**：661 判 `changes_requested`（12 处行号漂移）；协调者逐条核对源码后裁定 **5 组属实、7 处为复核误判**（引用函数入口或正确字段行）；662 仅改属实项（差异 2 行）；663 定向复验 **approved**（5 组命中、7 处裁定成立、71 引用 0 缺失/0 越界、差异仅引用数字）。
- **待裁决（阻塞实现片）**：① 无 `.talk/project.yaml` 的候选能否重关联（推荐拒绝）；② 仅标记匹配、物理身份变化能否人工确认（推荐允许并标弱证据）；③ 任一其他登记根不可访问是否阻止（推荐阻止）；④ 是否重写本机指针/runtime 配置（推荐仅对可证明归属的文件做最小 CAS 改写，否则拒绝）；⑤ 谁能操作与忙状态范围（推荐仅 human/operator，运行/未知时禁止提交）。
- **流程问题（记录）**：662 曾因任务包“只写 `.tmp/wd1/`”与“修改设计稿”自相矛盾进入澄清（我的模板遗留，已答复把设计稿作为唯一写入例外）；663 结果消息围栏外含说明文字（格式违规），已按围栏内 JSON 提取校验并记录。
- **测试**：本片为设计/文档，产品代码零改动，未运行产品测试（如实标注）。
- **提交与推送**：设计稿 + 本文档 + 路线图第 9 项更新，随本片推送。
- **恢复**：说“继续项目”；先读本快照与 `PROGRESS_HISTORY.md` 顶部 W-D1 记录。

## 收工快照（2026-11-11 20:25，W-C4 清债）

- **本轮完成（任务 659 K2.8 独立复核 approved，结果消息 3448 已收取）**：**W-C4 删除残留清理与 `operation_key` 边界对齐**——`scripts/role_delete.py` 在删除事务完成、锁释放后尽力回收锁守卫与空壳（`profiles`、空的 `native-home`、`.talk/agents/<member>`、Key 锁守卫）；守卫被占用或可见 `.lock` 仍在时保留且不影响 `complete`；`server/models.py` 两个恢复请求模型 `max_length` 120→`OPERATION_KEY_MAX_CHARS`(128)，与契约 8–128 一致。
- **验证**：基线 187 项 / 3 失败（`tests.test_role_provision.CliAndSecretTests` 三个 CLI 子进程用例 exit 1，改动前同样失败）；候选 194 项 / 同 3 失败，`new_failures=0`；追加回归 `test_role_service_recovery_cli + test_role_provision_followup + test_workspace_paths + test_role_provision_requests` 100 项全过；`py_compile`、UTF-8、`git diff --check` 通过。证据 `.tmp/w-c4/`。
- **独立复核（659，K2.8）**：8 项逐条 `pass`（卫生 `pass_with_note`，文档差异已核实）；复核环境候选 194 / 基线 187（`git archive 2ade45e` 干净提取）均 **0 失败**，`new_failures=0`，**approved**；报告 `.tmp/w-c4-review/review.json`。
- **存量清理（2026-11-11 21:15，已授权执行）**：删除 23 项无主残留（14 个 legacy guard-only 目录 + 9 个 workspace 角色空壳，共 23 文件 / 736 B）。删除前逐项复核：成员不在名册、角色服务 `stopped/not_started`、无 queued/running 任务、非 reparse、guard 未被持有；明细 `.tmp/w-c4/residue-plan.json`、结果 `.tmp/w-c4/cleanup-result.json`。**遗留未删**：6 个 `native-home` 非空（含 `.dsh`/`LocalLow` 等原生登录态）的 workspace 残留、私有 Key 根（`TALK-private\keys`）下的 guard，均未扫描/未授权。
- **未做（需授权）**：上述 6 个含原生登录态的 workspace 残留与私有 Key 根 guard；真实删除 E2E 未做（会动生产数据）。
- **环境**：runtime `2172`、API 子进程 `14296` 仍在运行（`/healthz` ok、`auth=trusted`），本轮未重启服务、未改生产数据。
- **提交与推送**：`dce88f0`（主体）、`6a72411`（可见锁守卫补强），文档随切片提交；已按完整切片推送 `codex/terminal-return-codex`。
- **恢复**：说“继续项目”；先读本快照与 `PROGRESS_HISTORY.md` 顶部 W-C4 记录。

## 收工快照（2026-11-11 19:35，重启后）

- **服务状态（已恢复，detached 后台进程）**：runtime pid `2172`、API 子进程 `14296`，`startup_state=complete`，7 个宿主在，`/healthz` ok；页面 `http://127.0.0.1:8000` 正常。日志 `.tmp/talk-runtime.out.log` / `.tmp/talk-runtime.err.log`。该进程脱离本次会话，关窗口不影响。
- **角色**：hy4 / w-d 均 **stopped**；WorkBuddy 为普通启动（9222 未开），按用户决定暂不使用内置模型，故未启动这两个 CDP 角色。
- **本轮已完成并推送**：W-B4 思考强度、W-B5 弹窗改版、W-B6 查看对话/成果权限、W-B7 自动启动门、W-C1 SSE 过期测试、W-C2/W-C2b reload 瞬时断连重试；最近提交 `cf86b80`（W-C2/W-C2b），此前 `ee57eb3`（W-C1）、`ff9a40a`（W-B7）、`9affa69`（W-B5）、`ba75f01`（W-B6）、`e55b26f`（W-B4）。
- **人工验收**：用户已确认 W-B4 思考强度、W-B6 查看完整对话/成果通过；W-B5 已实际用「复制启动命令」启动成功。
- **测试**：`tests.test_role_services` 82/82；host+bridge 四模块 186 项全过；`new_failures=0`。
- **下一步（需要时）**：要用 hy4/w-d 内置模型时，先完全退出 WorkBuddy 并以调试模式启动：
  `$env:WORKBUDDY_REMOTE_DEBUGGING_PORT = "9222"; Start-Process "$env:LOCALAPPDATA\Programs\WorkBuddy\WorkBuddy.exe"`，再启动两个角色（页面点启动即可）。
- **重启 runtime 注意**：`serve` 必须带 `--apply`；若 PowerShell 报 `NO_PROXY`/`no_proxy` 重复键，先删小写重复项再 `Start-Process`。
- **可选遗留（非阻断，未授权不做）**：legacy `guard`/空 `native-home` **存量**残留（代码已由 W-C4 修，存量需单独授权清理）、终端自己作为新角色执行的 Key 交付 onboarding；`host_unreachable` 的协议级 at-least-once 边界（结果去重键、claim token 重签发）已记录为不默认做。~~`operation_key` >120 显式用例~~ 已由 W-C4 完成。

## W-C2 完成（2026-11-11 18:05，已提交 `cf86b80`）

- **复现（653 Terra）**：空闲轮询连续 `host_unreachable` 后 serve 继续并 `poll_recovered`（设计内）；start 的 report 断开时原版只上报一次、后续空轮不重报；bridge 发送任务结果/完成请求拒连时只调用一次 → 任务被标 failed 或停在 running（真实缺口）。
- **修复**：宿主 claim 对明确 ConnectionRefused 有界重试（0.2/0.5/1s），`host_unreachable` 时重放同一 report；bridge 结果/完成请求仅对 ConnectError/ConnectTimeout 重试（共 4 次）。654 K2.8 **approved**（候选 142/基线 137，24F+14E 逐名一致，`new_failures=0`）。
- **真实 E2E 发现第二缺口**：reload 停机约 3.2s，窗口前 5s start → 角色 4s 内 `bridge_process_exited`（bridge 启动首个 `PUT /api/instances` 无重试）→ **W-C2b（655）**：启动握手（注册+首次 PUT）共用 9s 预算，仅重试 ConnectError/ConnectTimeout/ConnectionResetError，同一 instance/载荷，握手完成前不接任务；超预算如实退出。658 K2.8 **approved**（候选 186 全过、基线 175，`new_failures=0`）。
- **修复后 E2E**：reload 窗口内 start → running（无 `bridge_process_exited`）；任务 656（reload 期间创建）→ succeeded（3445）；任务 657（执行中 reload、两次 ConnectError）→ succeeded（3446）。
- **残余边界**：宿主 claim/report 重试需宿主进程重启生效（本次 E2E 桥侧已生效）；超过 9s 的中断仍会失败；任务结果 POST 无去重键，只重试连接建立阶段，读写歧义错误不重放；claim 响应丢失无法收敛。

## W-C1 完成（2026-11-11 16:50，已提交 `ee57eb3`）

- **页面/测试债清理**：修复长期失败的 `tests.test_role_services.AvailabilityTests.test_sse_authentication_does_not_block_event_loop`（651 Terra / 652 K2.8 **approved**）。
- **根因**：测试过期——仍按旧签名 `main.sse_events(None, ...)` 传 request=None，且 patch 的 `_resolve_sse_member` 是一参；当前实现要求真实 Request 与 `(token, host)` 两参。
- **修复**：仅 `tests/test_role_services.py`：真实 Starlette Request（client=127.0.0.1）、两参慢鉴权 patch、新增 host 传递与 401 断言；原“事件循环推进/任务未完成/401”断言保留。产品代码零改动。
- **结果**：候选 `tests.test_role_services` 82/82 全绿；基线 `9affa69` 同命令仍有且仅有这 1 个失败；`new_failures=0`。此后测试套件不再有已知 SSE 失败。

## 人工验收（2026-11-11 16:20）

- 用户确认：**W-B4 思考强度通过**；**W-B6「查看完整对话/查看成果」通过**。
- W-B5 弹窗：用户已实际用「复制启动命令」启动成功（15:0x），视觉未单独评价。

## 用户决定（2026-11-11 15:35）

- **不做受管 WorkBuddy 调试启动器**：用户只在使用 w-d 内置模型时手动执行启动命令，不要求 WorkBuddy 常驻调试模式；保留现有弹窗/复制命令指引即可。
- **不做「角色换模型」入口**：角色不换模型；需要别的模型时删除后重建（新身份）。
- **模型清单变化不自动化**：WorkBuddy 升级/适配时人工执行一遍刷新——已写入 [WORKBUDDY_ACP_593_RESEARCH.md](spec/WORKBUDDY_ACP_593_RESEARCH.md) 10.7「版本升级适配检查清单」（含重跑 `register --transport cdp` 刷新模型与强度、实机自检、回归）。
- **auto-start 路径补启动门：已完成（649 开发 / 650 复核 approved）**——CDP 探测下沉到共享入队核心 `_enqueue_start_launch`；创建自动启动失败记 `auto_start_status=failed` + `auto_start_error_code=workbuddy_cdp_unavailable`、零 launch、请求保持 provisioned；项目启动配置逐角色 failed + 稳定码、不整体 500；人工启动 409 与零写入不变。候选 169/基线 163，唯一失败为既存 SSE，`new_failures=0`。
- **W-B7 真实 E2E（协调者）**：调试关闭时创建 `wb7-probe`（auto_start）→ `auto_start_status=failed`、`auto_start_error_code=workbuddy_cdp_unavailable`、generation 0、current_launch null；重开调试后创建 `wb7-probe2` → `auto_start_status=enqueued`、role 起至 running；两个探针角色已停止并删除（cleanup complete），hy4/w-d 已恢复 running。

## W-B4 完成（2026-11-11 14:20）

- **实现（8 文件）**：`bridges/workbuddy_cdp.py`（`list_models` 只读枚举 + effort 白名单 low/high/max + `setThoughtLevel` 下发）、`scripts/workbuddy_cdp_prompt.py`（诊断带实际 effort）、`scripts/workbuddy_acp_models.py`（`--transport cdp` 真实枚举校验模型、写/更新 choice `capabilities`：`effort:<level>` + `effort_default:<level>`）、`server/workbuddy_effort.py`（CDP 别名按六维匹配 choice 能力投影，纯 DB 无网络探测）、`server/routes/projects.py`（接线）、`tests/test_workbuddy_cdp.py`、`tests/test_workbuddy_effort.py`、手册。
- **复核**：641 K2.8 **approved**——候选 103 项 / 基线 100 项，唯一失败为既存 SSE，`new_failures=[]`；ACP 路径不变、读路径无 CDP 探测、六维失配不猜。
- **部署与登记**：API 受控 reload；`scripts.workbuddy_acp_models register --transport cdp` 更新 3 个 choice 能力。当前 hy4 `effort_options=["high"]`（默认 high），w-d `["low","high","max"]`（默认 high）。
- **真实 E2E**：w-d 设 `effort=max` → 200、`effective_effort=max`；非法 `ultra` 与 hy4 `low` → 422 `effort_not_supported`；任务 **643** succeeded，执行期间适配器 argv 实测含 `--effort max`。
- **人工验收：2026-11-11 用户确认通过。**
- **限制**：强度档位来自登记时快照，桌面模型清单变化后需重新登记；登记脚本在桌面不可达时失败（不写半套）。

## W-B5 弹窗完成（647 approved，已提交 `9affa69`）

- 640 Terra 复核 **changes_requested**：①复制竞态（旧弹窗异步回调清掉新弹窗引用 → 重复弹窗）；②无障碍（可访问名称、焦点）。
- 642 返修：`dialogActive()` 守卫、焦点陷阱/恢复、放大到 760 CSS（≈608 物理像素、标题 20/正文 16/命令 15/按钮 46）。
- 644 定向复验 **changes_requested**：①reject 分支仍缺守卫；②双失败焦点失守；③深色按钮对比度 1.77:1。
- 645 二次返修（complete，43/43）：reject 全分支守卫、双失败 `copy.focus()`、按钮改用 `--accent-bg/--accent-fg`；纯 JSON 交付。
- 647 Terra 最终定向复验 **approved**：候选 43/43、基线 39/39、`new_failures=0`；独立对抗 2/2（延迟 reject、双失败焦点）；浅/深按钮对比度 5.21:1 / 5.89:1（hover 4.59/5.78）。
- 截图：`.tmp/wb5/modal-light.png`、`.tmp/wb5/modal-dark.png`（协调者 headless Chrome 复验，608 物理像素）。
- **提交与推送：`9affa69`。用户已实际使用「复制启动命令」启动成功（视觉未单独评价）。**

## 已修 Bug（W-B6，646 开发 / 648 复核 approved，已提交 `ba75f01`）

- **现象**：任务详情点「查看完整对话」/「查看成果」提示「当前账号尚未加入这个任务对话…」（`web/app.js:1289`、`web/workspace.js:2576`），人工操作员无法查看。
- **根因**：`web/app.js::loadMyPermissions()` 以 `apiKey` 非空为前置；本地信任模式无 API Key → 权限请求被跳过 → `canViewAllConversations` 恒 false。服务端 `/api/members/me/permissions` 实际返回 true。
- **修复**：去掉 apiKey 前置（保留 `current()` 身份/序号/登出守卫）；`web/app.js` 1 行 + 测试新增 5 用例（无 Key 信任加载、false/401/403/字段不符拒绝、agent 拒绝、key 模式不回归、登出竞态）。
- **复核**：648 K2.8 **approved**——候选 29/29、基线 24/24，`new_failures=0`；未改 `canEnterGroup`、未改 `workspace.js`/后端。
- **真实浏览器证据（协调者）**：headless Chrome 加载页面后 `performance` 资源里出现 `GET /api/members/me/permissions`（fetch，364 bytes），响应 `{"member_id":"human:operator","can_view_all_conversations":true}`；页面 `apiKey` 为空，确认是信任模式路径。
- **人工验收：2026-11-11 用户确认「查看完整对话/查看成果」通过。**

## 收工快照（2026-11-11 10:50）

- **本轮完成**：**W-B3 未开调试模式时的启动拦截与弹窗**（630 Terra 开发 / 631 K2.8 独立复核 approved / 632 探测返修 / 633 定向复验 approved）＋真实 E2E（634/635/636）。
- **实现（7 文件）**：新增 `server/workbuddy_cdp.py`（仅 loopback、原始 socket、0.6s 预算的 CDP 探测）；`server/role_services.py` 单角色启动入口在 `_write_begin` 前拦截（仅 `native-workbuddy-cdp` / `workbuddy-cdp:` 绑定；不可用 → 409 `workbuddy_cdp_unavailable`、零 launch/零状态写入；start-all 逐角色返回该码）；`web/workspace.js` 启动 409 弹窗（标题「请以调试模式启动 WorkBuddy 再使用其内置模型」+ 两行启动命令 + 复制按钮，clipboard 失败回退 textarea；遮罩/Esc/知道了可关）；`web/app.js` 任务 `failed` 且 `last_error` 含该码时弹同一提示（同任务只弹一次）；`tests/test_workbuddy_cdp_gate.py`、`tests/workspace_role_services.test.cjs`、`docs/guides/USER_MANUAL.md` 一句说明。
- **返修**：630 首版用 httpx 探测，本机首请求 438ms > 0.4s 预算，真实 E2E 出现「调试端口正常却 409」误报；632 改原始 socket（实测 8–10ms），633 复核 approved（门测试 10/10；联合 92 项唯一失败为既存 SSE，`new_failures=0`）。
- **真实 E2E**：调试模式开 → 启动 hy4 200/running，任务 **634** succeeded；退出 WorkBuddy → start 返回 **409** 且 generation 不变、零 launch；重开调试 → start 200/running；调试关闭时任务 **635** failed，`last_error` 含 `workbuddy_cdp_unavailable`（前端失败弹窗数据链路成立）；重开调试后 **636** succeeded。
- **部署**：API 受控 reload（新 pid 17612）；runtime 与角色宿主未重启。当前 hy4 `agent:prj-e8fe7066bbec.hy4-2bbb4889` running（gen 5、`ins_b06c2ff5bce1`），w-d `agent:prj-e8fe7066bbec.w-d-a6718675` running。
- **对账**：本轮 submitted 任务已全部收取（630/631/632/633/634/636）；635 failed 无可收取结果，已记录。
- **已知限制**：既存 SSE 测试 `test_sse_authentication_does_not_block_event_loop` 失败（`server/main.py:460` 对 `request=None` 未容错），与本片无关，建议另片修；auto-start 路径未加门，由任务失败弹窗兜底；弹窗无 CSS 类（暗色主题观感非阻断）。
- **待办（按优先级）**：① 受管 WorkBuddy 调试启动器/开机引导；② `server.main.sse_events` 对 `request=None` 容错（既存测试债）；③ CDP 强度探测接入；④ "角色换模型"产品化入口；⑤ 既有 `host_unreachable`、legacy guard 残留等待办不变。
- **恢复**：说“继续项目”；先读本快照与 [WORKBUDDY_ACP_593_RESEARCH.md](spec/WORKBUDDY_ACP_593_RESEARCH.md) 10.5/10.6。

## 收工快照（2026-11-11 09:10）

- **本轮完成**：**W-B2 WorkBuddy CDP 执行通道**（624 Terra 开发 / 625 返修 / 626 K2.8 独立复核 **approved**）＋**内置模型恢复与真实任务 E2E**（627/628）。提交见 `git log -1`。
- **实现**：新增 `bridges/workbuddy_cdp.py`、`scripts/workbuddy_cdp_prompt.py`、`tests/test_workbuddy_cdp.py`；`bridges/workbuddy_bridge.py` 增 `workbuddy-cdp:` 分支、`scripts/workbuddy_role_host.py` 接受该前缀、`scripts/workbuddy_acp_models.py` 增 `--transport cdp`。旧 ACP/custom-local 分支逐字未变；服务端/前端零改动。候选 70 项全过、基线 60 项（唯一差异为基线无 CDP 测试模块的 loader error），`new_failures=0`。
- **实机（WorkBuddy 5.9.3，调试端口 9222）**：适配器 chat 返回 `OK`（25s）、task+交付合同返回有效 `talk-delivery-1` JSON（22s）；E2E 任务 **627**（Hy4，191s）与 **628**（DeepSeek-V4.1-Flash，60s）均 succeeded 且交付包校验通过；WorkBuddy 对话列表回到基线 40 条、无残留。
- **绑定恢复**：角色模型创建时锁定（六维校验），不能原地改；经用户确认后删除旧 `hy4`/`w-d 内置`（5 步清理 complete），按同名新建 CDP 角色：`hy4` = `agent:prj-e8fe7066bbec.hy4-2bbb4889`（`ins_0c9faa73efda`，pid 9732，Hy4），`w-d 内置` = `agent:prj-e8fe7066bbec.w-d-a6718675`（`ins_070295d46282`，pid 7784，DeepSeek-V4.1-Flash），均 `running/ready`。
- **模型选择**：登记 `workbuddy-cdp:hy4free`（`rmc_5c505bbca8c5`）、`workbuddy-cdp:deepseek-v4.1-flash`（`rmc_7fd4672d2b4d`）、`workbuddy-cdp:glm-5.3-flash`（`rmc_fc4b0e4069b3`），显示名“（内置·桌面）”。
- **部署边界**：未重启 API/runtime，只由 runtime 重组 workbuddy 角色宿主；新宿主加载工作区代码后启动。
- **运行时要求**：WorkBuddy 必须以 `WORKBUDDY_REMOTE_DEBUGGING_PORT=9222` 启动（仅 loopback；启动前清掉 `ELECTRON_RUN_AS_NODE`）；正常双击启动时角色任务会明确失败 `workbuddy_cdp_unavailable`，不会静默改道。
- **已知限制**：`window.wb` 为桌面私有 API，升级可能失效；CDP 绑定 `effort_options` 为空（强度按模型默认）；登记脚本按显式模型清单、不校验存在；适配器一处 CRLF 混入（非阻断）。
- **待办（按优先级）**：① 受管 WorkBuddy 调试启动器/开机引导（避免重启后忘开 9222）；② CDP 强度探测接入（`reasoning.supportedEfforts` → binding eager）；③ "角色换模型"产品化入口（当前只能删除重建）；④ 可选：`scripts/workbuddy_cdp_prompt.py` 行尾归一；⑤ 既有 `host_unreachable`、legacy guard 残留等待办不变。
- **恢复**：说“继续项目”；先读本快照与 [WORKBUDDY_ACP_593_RESEARCH.md](spec/WORKBUDDY_ACP_593_RESEARCH.md) 10.5/10.6。

## 收工快照（2026-11-11 00:45）

- **本轮完成**：W3c-3/4/6（隔离/恢复/工作区门，已验收）＋ **L1 本地信任模式**（免登录/隐藏 operator/公网拒绝，人工验收通过）＋ **L2 首次 MCP 自动创建工作区**（620 pass、E2E 通过）＋ **L3 终端 Agent 加入新项目**（623 pass、E2E 通过）＋ **WorkBuddy CDP 路线实测打通**（创建对话 + `runPrompt` 返回 OK，见 10.5）。
- **决策**：598 提出的“终止后不可逆”冲突按方案 A 落地：终止前的拒绝零终止零写入；已发起未确认 → 409 真实报告、零 DB 写入，重试走 `already_exited`。
- **环境（22:41 部署后）**：runtime A **23688**（加载 W3c-2a 自动清理）、API child **3816**（22:41 reload 部署 W3c-4，`operation_key` pattern 已在 openapi 可见）、`/healthz` ok、3 online；Terra/K2.8 running/ready；无 running 任务；隔离栈已停（证据 `.tmp/w3c3-e2e/E2E_SUMMARY.json`）。
- **命名调整（21:20）**：异常恢复按钮「终止孤儿并恢复」改名**「重置」**并仅在状态异常时显示；原「绑定重置」改名**「重新绑定」**（用户手册/恢复指南同步，Node 95 项通过）。
- **部署边界**：W3c-2a（自动清理）与 W3c-3（人工「重置」入口）均已生效；页面文案「重置」/「重新绑定」硬刷新可见。
- **当前状态（已修复并验收）**：W3c-6 已部署——runtime A 重启用**未设置** `TALK_WORKSPACE_RUNTIME_ENABLED` 的方式启动（runtime **19860**、API child **16224**），Astra `ins_1832024782b1`、Terra `ins_4556b2d5aacc`、K2.8 `ins_5d49d5e623e3` 均 `running/ready`；`/healthz` ok、4 online。开闸语义现为**默认开启、仅显式 `0/false/no/off` 关闭**。**2026-11-10 11:09 用户确认 Astra 启动成功，人工验收通过。**
- **WorkBuddy 内置适配（CDP 路线已打通，2026-11-11 00:35）**：用 `WORKBUDDY_REMOTE_DEBUGGING_PORT=9222` 启动桌面 → CDP 连页面 → 调用页面全局 `window.wb.conversations.create({cwd,title,transport:"local",mode:"craft",model})` 成功创建专用对话；`conv.runPrompt([{type:"text",text:"只回复 OK"}],{emitUserMessage:true})` 返回 `content:[{type:"text",text:"OK"}]`、`responseModel=deepseek-v4.1-flash`；`wb.conversations.delete(id)` 清理成功，**其他对话未被替换**。无需 ACP/CLI 端点。前提：WorkBuddy 必须以调试模式启动（TALK 非交互会话拉不起 GUI）、CDP 仅 loopback、`window.wb` 为私有 API 无版本承诺。下一步 **W-B2**：把 CDP 客户端接入角色执行通道（创建/设模型强度/发任务/收结果/换新对话），并做真实任务 E2E。详情 [WORKBUDDY_ACP_593_RESEARCH.md](spec/WORKBUDDY_ACP_593_RESEARCH.md) 10.5。
- **待办（按优先级）**：① **W-B2 WorkBuddy CDP 适配**（研究已通，待开发/复核/E2E）；② `host_unreachable` 在 API reload 窗口专项复现；③ legacy `guard`/空 `native-home` 残留；④ 可选补测：`operation_key` >120 字符显式用例；⑤ "终端自己作为新角色执行"的 Key 交付 onboarding（未做）。~~delete 90s 窗口~~ 已放弃（与既有安全合同冲突）。
- **L1 本地信任模式：已完成并人工验收通过**：页面免登录（刷新短暂加载属正常初始化）、右上角“本机操作员”、角色启停等人权恢复、成员列表隐藏 operator、agent Key 身份不变；API `pid 1404`、`/api/auth/mode=trusted`，代码 `7a0398c` + 页面修复 `35f896a`。Terra `ins_7ea85ea3f5f6`、Astra `ins_88b2a22ef6a8`、K2.8 `ins_5d49d5e623e3` 均 running/ready。
- **L2 首次 MCP 自动创建工作区：已完成、620 复核 pass、E2E 通过（`a8bfa9e`）**：`POST /api/local/workspaces/ensure` 按目录幂等注册项目、启用 provision host、生成独立 runtime 配置（每项目 state_dir/key_root）、写 `.talk/project.yaml` + `runtime.local.json`、以 `--attach-api` 启动 runtime；**不建角色/不启角色**。真实 E2E：临时目录 ensure 200 → `.talk`/runtime 就绪、无角色 → stop + DELETE 204，项目/进程/目录清理无残留。终端启动器 `TALK_WORKSPACE_AUTO_ENSURE=1` 才自动 ensure（DSH/Kimi 启动器默认设置）；显式 project 缺 Key 仍按基线报错。
- **L3 终端 Agent 加入新项目：已完成、623 复核 pass、E2E 通过（`62eb388`）**：`POST /api/local/workspaces/join` 让当前 Agent 用现有 Key 幂等加入 `ProjectAgent` 名册（不建角色/Key）；启动器 ensure 后自动 join，无 Key 跳过，human 的 403 `join_requires_agent` 视为无需加入。真实 E2E：临时项目 ensure 200 → join 新建/重复 already → `agent:deepseek` 在册 → stop + DELETE 204；无 ProjectRole。
- **环境**：runtime A **19860**、API child **1140**（L3 reload，含 `/api/local/workspaces/ensure|join`）；`/api/auth/mode=trusted`；Astra/Terra/K2.8 角色服务 running/ready（以页面/role-services 为准）。
- **已知边界**：终端现在以**全局 Agent**身份建/看任务，角色仍手动创建、由角色宿主执行；"终端自己作为新角色执行"需要角色 Key 交付，未做。WorkBuddy 适配转入 **W-B2（CDP）**。
- **恢复**：说“继续项目”；先读本快照与 [W3C_RECOVERY_CHAIN_20261109.md](spec/W3C_RECOVERY_CHAIN_20261109.md)。

## 收工快照（2026-11-09 17:30）

- **本轮完成**：W3c-1a 多工作区运行底座 `2781356`、W3c-1b shutdown 404/非绝对根 `1ff8b2b`、W3c-2a 孤儿 bridge 受控清理 `244f226`+`6a6d0c5`、WorkBuddy 版本适配提醒 `8e84fb3`；复核 583/585/592/594/596 均 **approved**；HEAD `4a74d46` 已推送。
- **环境**：生产 runtime A pid **3704**、API child **1952**、`/healthz` 正常；Terra/K2.8 idle；hy4/w-d 停用（WorkBuddy 5.9.3 ACP 不兼容，页面已提示版本警告与 `effort_error`）；项目仅 `prj_e8fe7066bbec`；无临时项目/runtime/角色；无 running 任务。
- **重要部署边界**：生产 runtime A 仍是旧 `talk_runtime` 代码，W3c-2a 修复待**下次 runtime 重启**才生效；API 已带 WorkBuddy 提醒改动。
- **待办（按优先级）**：① WorkBuddy ACP 5.9.3 只读研究 → 适配（路线图第 17 项后半，需用户确认开工）；② 人工显式恢复入口（586 必须修 2，忙孤儿）；③ delete 90s 新鲜度窗口（可选）；④ `host_unreachable` 在 API reload 窗口专项复现；⑤ 性能冷启动：`role-services` ~1s、`runners/versions` 首调 5–6.6s（可选）。
- **恢复**：说“继续项目”；先读本快照与 [W3C_RECOVERY_CHAIN_20261109.md](spec/W3C_RECOVERY_CHAIN_20261109.md)；WorkBuddy 诊断在 `.tmp/workbuddy-acp-593-diagnosis.md`。

## WorkBuddy 版本适配提醒完成（2026-11-09 17:20）

- **交付** `8e84fb3`（595 Terra 开发、596 K2.8 复核 **approved**；候选 Python 47 / Node 33 全过，基线 43/31 全过，`new_failures=0`）：运行器版本面板增加 WorkBuddy **桌面版本**探测（`version.dll` 只读，与 ACP 验证基线 **5.8.3** 比较），未适配/未知时返回 `adapter_warning`；`workbuddy_effort` 缓存探测错误码（TTL 60s），binding 空选项时投影 `effort_error`，页面显示“强度获取失败（原因）”。不自动改绑定/升级。
- **部署与实测**：API 受控 reload child **17496→1952**；`/api/runners/versions` → CLI `2.165.0` match、desktop `5.9.3`、`desktop_status=newer`、`adapter_warning` 正常；w-d binding（`refresh_effort=true`）→ `effort_options=[]`、`effort_error=workbuddy_acp_runtime_unavailable`。
- **环境说明**：Terra 会话 `LOCALAPPDATA` 被 role 沙箱重定向，导致其自测“未找到 WorkBuddy”；K2.8 以标准 `LOCALAPPDATA` 实测返回 5.9.3，生产 API 继承 Administrator 环境。
- **下一步**：WorkBuddy **ACP 5.9.3 协议适配研究**（只读：新握手/会话动态端口/`Acp-Connection-Id`）→ 实现/复核；586 建议的人工恢复入口与 delete 90s 窗口仍待排期。

## W3c-2a 完成：孤儿 bridge 受控清理与恢复链 E2E（2026-11-09 16:50）

- **修复**：`244f226`（588，592 approved）+ `6a6d0c5`（593，594 approved）——runtime 在宿主已死且 `ownership_held` 时，对“同机、同项目、两次查询均 idle、无 current_task、句柄创建时间与记录偏差 ≤5s”的本地孤儿 bridge 用 Windows 句柄 `TerminateProcess` 受控终止；`recovery_required` 语义不变，忙角色不杀。真实 E2E 发现并修复了 `recorded_process_state` +1s 容差导致的“永不清理”缺陷。详见 [W3C_RECOVERY_CHAIN_20261109.md](spec/W3C_RECOVERY_CHAIN_20261109.md)。
- **真实 E2E**：临时项目 B runtime B（新代码）→ 角色 ready `ins_48280c199d53` → **kill 宿主 7536 → bridge 6288 在 ~6s 内被自动终止**；90s 后 stop 走人工恢复（`idempotent_stopped`，gen 6）→ start ready `ins_d981d84a3696`（gen 7）；角色删除 5 步 complete、项目 B/workspace/keys 清理完成，仅剩 `prj_e8fe7066bbec`。
- **复核**：588 候选 64 / 基线 58（同名环境项，`new_failures=0`）；593 候选 65 / 基线 64 **全过**、`new_failures=0`。
- **残余**：① 人工显式恢复入口（忙孤儿）未做；② 终止后轮询仍用 `recorded_process_state`，可能提前记 `terminated`（可选 `WaitForSingleObject`）；③ delete 90s 窗口（可选）；④ `host_unreachable` 未复现（需 API reload 窗口专项）；⑤ guard/空 native-home 既有债务。生产 runtime A（pid 3704）需下次重启才带上本修复。
- **下一步**：WorkBuddy 版本适配提醒片（路线图第 17 项）→ WorkBuddy ACP 5.9.3 适配研究；再按需做人工恢复入口/delete 窗口。

## 待办登记：WorkBuddy 版本适配提醒（2026-11-09 15:15）

- 用户决定：hy4/w-d **不改绑**到 `models.json` 的 API 模型，内置模型继续走 ACP；等 K2.8 额度恢复后再开工。
- 已登记路线图第 17 项：**WorkBuddy 版本适配提醒**——只读探测桌面/CLI 版本 + 已适配范围对比 + 运行器版本面板/角色行提示 + `effort_options` 为空时暴露失败原因；**未开工**。
- 现状：W3c-2a 候选冻结（2 文件 +261，patch 备份 `.tmp/w3c2a-candidate-588.patch`），等 K2.8 复核；WorkBuddy 5.9.3 ACP 不兼容诊断在 `.tmp/workbuddy-acp-593-diagnosis.md`；hy4/w-d 当前不可用（内置 ACP 通道），不占用其他额度。

## W3c-1b 完成：shutdown 404 与非绝对根（2026-11-09 10:55）

- **修复** `1ff8b2b`（W3c-1b；584 Terra 开发、585 K2.8 复核 **approved**，候选 87 项 / 基线 84 项同 2 个 `ActualBootstrapTests` error、`new_failures=0`）：`talk_runtime.stop()` 在项目已删（404 `project not found`）时按“无角色”继续完成 drain/停止，其它 `HostError` 仍抛出；`configured_runtime` 在 `resolve()` 前拒绝非绝对 `project_root_path`。
- **部署**：API 受控 reload child_pid **1676→17496**；runtime A（pid 3704）未重启，`talk_runtime` 修复待下次 runtime 重启生效（已在临时项目 B 的 runtime 上验证同一代码路径）。
- **真实 E2E（W3c-1b）**：项目 B + runtime B（新代码，pid 10768/15188）+ dsh 角色与宿主（manager 23536）；**先删项目 → `stop --wait` 返回 `stop_status=stopped`、`phase=complete`、`error_code=null`**（修复前 `stop_blocked` / `project not found`）；随后同 ID 恢复项目 → 角色删除 5 步 complete → 删项目 → 再停 runtime 仍 `stopped`；项目/角色/`workspaces/<pB>`/`keys-b` 清理完成，仅剩 `prj_e8fe7066bbec`。
- **残余**：`.key.lock.guard` 残留归 legacy 清理片；`talk_runtime` 修复需下次 runtime 重启才作用于生产 A。
- **下一步**：W3c-2 恢复链（runtime 停/启、bridge 被 kill、恢复后 stop/delete、瞬时 `host_unreachable` 定位）；页面刷新验收 UI 清理。

## W3c-1 完成：多工作区运行底座（2026-11-09 10:20）

- **修复**：`2781356`（W3c-1a；582 Terra 开发、583 K2.8 复核 **approved**，候选 246 项 / 基线 240 项同名 2 error、`new_failures=0`）。本机 runtime 绑定按项目解析（`bind_local_runtime` 写 `<项目根>/.talk/runtime.local.json`，`--attach-api` 也写；`configured_runtime(engine, project_id)` fail-closed，不回退 ROOT）；生产调用点全部显式传 project；宿主与角色子进程受控注入 `PYTHONPATH=<仓库根>`，不再依赖 cwd。详见 [W3C_DUAL_WORKSPACE_FINDINGS_20261109.md](spec/W3C_DUAL_WORKSPACE_FINDINGS_20261109.md)。
- **部署**：API 受控 reload，child_pid **24028→1676**；运行时 pid **3704** 与 Terra/K2.8 宿主未重启；`/healthz` 200。
- **真实 E2E**：项目 B 的 runtime **首启 `startup_state=complete`**（pid 15076，自动写绑定）；B 角色 ready `ins_d6fa6cc54034`、A 角色 `ins_1dd4918c8a15`；**A 停 B 不停**（100s：B 宿主 18640/桥 7160 存活、心跳 <2s、service running），**反向同样**（A 宿主 18888/桥 19996、心跳 <7s）；修复前失败的 B 角色删除重试 5 步 complete；两个 iso 角色删除、项目 B 删除、`workspaces/<pB>` 与 `keys-b` 清理完成，仅剩 `prj_e8fe7066bbec`。
- **残余（非阻断）**：① 先删项目再停 runtime 会 `stop_blocked`（shutdown 查角色 404），本次按“同 ID 重建 → 停 runtime → 再删项目”恢复，建议后续修 shutdown 404 语义或文档固定顺序；② `configured_runtime` 对非绝对 `project_root_path` 建议补显式拒绝与用例；③ 角色删除后残留 `.key.lock.guard`（同类既有债务）。
- **下一步**：W3c-2 恢复链（runtime 停/启、bridge 被 kill、恢复后 stop/delete、瞬时 `host_unreachable` 定位）；页面刷新验收 UI 清理；推送本片。

## W3c-1 双工作区隔离：尝试后阻塞（2026-11-09 00:10）

- **结论**：W3c-1 不能作为纯验收完成；当前代码把“本机 runtime / 宿主 / 桥 / 删除凭据”四处硬绑定到“项目根 = TALK 仓库根”。详见 [W3C_DUAL_WORKSPACE_FINDINGS_20261109.md](spec/W3C_DUAL_WORKSPACE_FINDINGS_20261109.md)。
  - F1 runtime 绑定单项目：B 的 startup → `409 startup_local_runtime_unbound`，`startup_state=failed`；
  - F2 宿主 `cwd=project_root` + `-m scripts.*` → `ModuleNotFoundError: scripts`；
  - F3 宿主 `_local_facts` 要求项目根有 `.talk/runtime.local.json` → `dsh_host_config_invalid`；
  - F4 角色子进程环境白名单不含 PYTHONPATH，桥 `-m bridges.*` → `bridge_process_exited`；
  - F5 删除 cleanup 凭据同样要求单项目绑定 → B 角色删除 `local_runtime_required`。
- **已实测**：项目 B 注册、`workspaces/<pB>/workspace.json` 生成、A/B 两个 workspace-v1 角色开通均正常；A 角色 start → running/ready（`ins_c243b0b0a775`）；B 角色在四处阻塞下无法 ready。
- **当前环境**：runtime A pid **3704** 正常（healthz ok，3 在线）；runtime B 已 stop（pid 15536 退出）；本机绑定已恢复 A（`.talk/runtime.local.json` 与备份逐字一致）；A 临时角色 stop+delete 5 步 complete；**项目 B `prj_7e3fcc639c70` 与已归档临时角色、失败删除行保留为复现现场**（UI 会多一个“W3c 双工作区验收 B”）；证据在 `.tmp/w3c-dual-20261109/`。
- **下一步**：请项目管理者在 A（完整多项目底座）/ B（最小“外部项目根可运行”）/ C（收缩到 P3）中选一个；选 B 则先派修复片，完成后重跑 W3c-1 并按产品流程删除项目 B。

## 交接：W3c 剩余与下一步（2026-11-08 23:25）

**本轮角色**：协调/决策（任务发起、复核调度、Git 收尾）；开发 Terra、复核 K2.8。

W3c 未完成两项，按以下顺序各开一片（均需独立复核）：

1. **W3c-1 双工作区隔离（A 停 B 不停）**
   - 新建第二个项目（`POST /api/projects` 或页面），确认 `workspaces/<p2>/` 与 `workspace.json` 生成；
   - 为项目 B 建一个 workspace-v1 角色（dsh 最省事，免设备码）；准备第二份 runtime manifest（`project_id=p2`、独立端口/`state_dir`/`key_root`），启动 runtime B；
   - A、B 各起一个角色 → 停止 A 的角色 → 断言 B 的角色进程/实例/心跳不受影响（pid、`observed_instance_id`、bridge 存活）；再反向停 B 验 A；
   - 清理：停角色 → 删角色 → 删项目 B / 停 runtime B；记录隔离证据（launch/instance/进程快照）。
2. **W3c-2 恢复链**
   - 场景 a：角色 running 时停/启 runtime（或 kill 宿主）→ 重启后宿主重认领、角色恢复、无 stale ownership/409；
   - 场景 b：bridge 子进程被 kill → 宿主回报失败并释放（c53e59c 已做），下一次 start 正常；
   - 场景 c：恢复后 stop/delete 正常、无残留（含 `.provision.lock.guard`/空 native-home）；
   - 需补单元/接口测试 + 真实 E2E；已知瞬时 `host_unreachable`（重启后首次 start，launch 随后仍完成）在本片一并定位。

**已知债务（可后置，不阻塞 W3c）**：workspace 删除残留 guard/空目录；`test_codex_new_role_host` 在 venv 下 PID 断言失败（基线同因）；`run.ps1` 无 BOM（PS 5.1 解析失败）；`tests.test_conversation_access` 14 项 `project_id_required` 基线失败（另案）。

**当前环境**：运行时 pid **3704**（开闸）；Terra/K2.8 running；astra 停止；无待收取任务；HEAD `dfb38a2`（已推送 `origin/codex/terminal-return-codex`）。

## 性能、可靠性与 Codex 插件目录修复（2026-11-08 22:55）

- **性能片** `c527034`（570 approved）：binding 读取改为缓存优先 + 后台单线程按模型去重预热，ACP 探测移出 DB 会话；`/api/events` 认证与回填进线程池；`/healthz` 改唯一临时文件；pending start 在 reconcile（2s 循环）内拉起宿主；连接池 30+30/15s（事故应急，注释保留）。
  - 实测页面接口：roles 0.07s、layouts 0.10s、requests 0.23s、services 0.30s、agents 0.78s；
  - 新 workspace 角色首启：`to_claim` 27–52s → **10.0s**，`claim_to_report` 11.6s（dsh 桥冷启动）；legacy 0.5–1.9s / 2–8s。
- **可靠性片** `c53e59c`（573 approved）：过期未回报 claimed launch 仅在“本机 + 心跳不新鲜 + 非忙 + 进程证明已退出”时释放（写锁内二次核验、幂等、日志）；宿主在 bridge 退出时按原领取身份回报并释放句柄，失败保留重试；missing-instance + 退出证据时 stop 幂等 `stopped`，身份不符仍 409。190 项测试通过。
  - 安全边界（有意保留）：无退出证据或子进程仍存活时不自动释放，**人工显式 stop** 为恢复入口；已知非阻塞观察：服务端确定性 409 下宿主内存死句柄可能阻塞自动重启，重启宿主自愈。
- **Codex 插件目录** `33cbffd` + `939f2ea`（575/578 approved）：`--disable apps` 单独无效；`--disable apps --disable remote_plugin --disable plugins` 有效。实机：移除 astra 的 67.9MB/12412 条 `remote_plugin_catalog` 后跑真实 TALK 任务（580）返回 OK，目录未重建；576（仅 apps）仍会生成。
- **清理**：小G `agent:codex` 从项目删除（角色档案同步移除）、任务 286 取消、旧 astra/rest01 删除；删除前的 25 条历史 instance 行与 task 12 残留 reservation 已带备份修复（`.tmp/codex-instances-backup.json`、`.tmp/task12-backup.json`）。
- **决策**：`docs/spec/HOST_LIFECYCLE_DECISION.md`（560f23e）——当前实例常驻+预热；安装包阶段按需宿主/空闲退出、轮询退避、软上限+LRU、按项目分 runtime。
- **当前**：运行时 pid **3704**（开闸）；Terra/K2.8 running；astra 已停止（验证用）；无待收取任务。
- **下一步**：W3c 剩余（双工作区隔离 A 停 B 不停、恢复链）与安装包宿主治理 P1；页面刷新验收 UI 清理。

## 原生准备修复与 UI 清理（2026-11-08 14:35）

- **修复提交** `c35e343`（12 文件 +440/−58，567 后端 / 568 前端独立复核均 **approved**）：
  - codex / kimi / **dsh** 原生准备按 `ProjectRole.storage_layout` 解析：workspace-v1 写入 `workspaces/<p>/roles/<m>/native-home/{.codex,.kimi-code,.dsh}`，legacy 逐字不变，未知布局写入前拒绝；
  - codex 旧 `ready` 但目标配置缺失时回到 `requires_user_action/can_start`，可重新授权；codex `finish_native_login` 增加布局二次复核；
  - 前端整段删除“运行时隔离待启用”通知区（iso function/循环/死过滤），进行中行与既有流程不变；强度空态保留简短说明。
- **实机验证（运行时 pid 6700，开闸）**：
  - legacy：Terra `ins_d998b83452e2`、k2.8 `ins_827aa9eb8b89` start → ready；
  - **dsh 新布局角色**：`agent:prj-e8fe7066bbec.dsh-84640e53` 创建 → 启动 ready（`ins_278056e79d3c`）→ 停止 → 删除 5 步 complete（免设备码）；
  - astra / rest01：native-setup 现为 `requires_user_action/can_start=true`（`native_model_configuration_required`），等用户重新授权后启动验证。
- **任务列表**：原 26 个 submitted 已全部收取；当前仅剩 **286**（`agent:codex` 创建、manual_pause 旧排队）待用户决定是否取消。
- **页面**：刷新后不再出现“角色已准备，运行时隔离待启用”；已归档/已删除成员的开通请求行不再占顶部。
- **下一步**：用户重新授权 astra、rest01 → 验证启动；随后补 W3c 剩余（双工作区隔离、A 停 B 不停、恢复链）与文档收尾。

## W3c 完成快照（2026-11-08 12:55）

- **开闸**：`TALK_WORKSPACE_RUNTIME_ENABLED=1` 已随运行时启动（当前 pid **11868**，venv 解释器）；`capability.json` 正常，新布局角色不再 409 `workspace_runtime_not_ready`。
- **W3c 全链路实测（真实 API + 文件系统）**：
  - 临时 workspace-v1 角色 **create → start → stop → delete** 全部成功（workbuddy 运行时，3 个临时角色；`ins_0e2ae36f30d5` 等 ready；删除 5 步均 complete）；
  - 落点：`workspaces/<p>/roles/<m>/{profiles,native-home,sessions,state/{manager,records},logs}`；manager health 带 capability 绑定；`state.pid == agent_instances.pid`；
  - 删除后三档/sessions/state/logs/Key 均清除，仅按 legacy 语义保留 `profiles/.provision.lock.guard`（另有空 `native-home` 目录残留）。
- **legacy 对照**：Terra `start → ready → stop` 正常、pid 一致，无 `recovery_identity_mismatch`。
- **本段修复**：`7fe64eb`（workspace profile 解析 + 受管 pid 一致性；555 approved）、`1fc95f4`（workspace 删除 skip-guard/双锁/幂等；559 approved，259 项全绿）。
- **未完成/已知**：① 新 kimi/codex 角色启动需各自原生登录（设备码；astra 同）；② 重启后**首次** start 偶发瞬时 `host_unreachable`（launch 随后仍完成；根因待小片）；③ workspace 删除残留 `profiles/.provision.lock.guard` 与空 `native-home` 目录（legacy parity，可在后续片清理）；④ 双工作区隔离/恢复链/开闸后 A 停 B 不停尚未完整验收。
- **当前运行**：Terra `ins_b0e0cfe3f51f`、k2.8 `ins_302789c91529`。数据：project_roles 23（19 legacy + 4 workspace-v1，均归档）、role_provision_requests 31。

## 部署与修复快照（2026-11-08 09:55）

- **状态**：W3a+W3b 已部署并验证。运行时 pid **19252**（`.venv` 解释器直接启动，等价 `run.ps1`）、API child 23104，`/healthz` 200、`startup_state=complete`、`capability.json` 已发布（`talk-runtime-capability-1` / `talk-runtime-1` / `talk-manager-1` / legacy+workspace-v1），9 宿主 serving。
- **启动门**：仍默认关闭（`TALK_WORKSPACE_RUNTIME_ENABLED` 未设）。真实 409 验证：临时 workspace-v1 角色 `agent:prj_e8fe7066bbec.role-d0bf55b3` 开通成功后 `start` 返回 **409 `workspace_runtime_not_ready`**、零 launch/零状态写入；角色已删除。（**2026-11-10 W3c-6 起已改为默认开启、仅显式 `TALK_WORKSPACE_RUNTIME_ENABLED=0/false/no/off` 关闭**；本条为历史记录。）
- **部署前置修正（重要）**：`workspaces` 必须为**私有 DACL 且禁用继承**（仅当前用户+SYSTEM+Administrators），否则 provision 报 `profile_root_invalid`；仅删 `CodexSandboxOffline` 不够。残留 `workspaces/p-obzgux3bnrygqyi`（prj_alpha）、547 遗留测试进程 50515/51882、2.4GB 旧日志均已清理；备份 `backups/w3b-deploy-20261108/talk.db`（integrity ok）。
- **修复（549 开发 → 550 k2.8 复核 approved）**：`run.ps1`/venv 启动运行时导致 codex 角色 `start` 失败 `cli_incompatible`（`sys.executable` 与 `sys._base_executable` 路径不同，`verify_runtime_entry` 只认后者）。已改为接受两种规范化路径、其余校验不变；提交 `3d41b23`。**venv 下实测**：Terra（codex）`ins_0817aea719ae`、k2.8 `ins_efdc991ce69a` 均 running/ready。
- **已知限制**：① `test_codex_new_role_host` 的 PID 断言在 venv 下失败（启动器 pid 与解释器 pid 不同；基线同因，测试未适配）；② `run.ps1` 无 UTF-8 BOM，Windows PowerShell 5.1 解析失败（需 pwsh 7 或补 BOM）；③ workspace-v1 角色删除后 `workspaces/<p>/roles/<m>/profiles/*` 残留（本次手工清理，W3c 需修）。
- **数据**：projects 1、groups 548、messages 2504、project_roles 20（19 legacy + 1 已归档 workspace-v1 临时角色）、role_provision_requests 28。
- **下一步**：用户浏览器验收（默认门 409、legacy 启停、新角色开通提示）→ W3c 真实双工作区/开闸需另行授权 → 重建 astra → 小债务（`talk_delegate_task` schema 1/2 vs 3/5）。

## W3b 完成快照（2026-11-08 00:45，用户次日部署验收）

- **状态**：W3b 全部代码完成并推送；**未部署、启动门默认关闭**。终轮全量回归（547）：Python 3600 项 `124F/44E/0S`，168 个失败名**全部落在 544 基线集合内，零新增**；544 所报 24 项 W3b 测试失败 + 1 时序 + 1 夹具全部消失；Node 三套件 44 项全过。
- **提交链**：片 1 `b1466d2`/`29930a3`/`8b2c033`；片 2 `d0b81b0`/`a8050da`/`bf0cf4d`/`7b390c9`/`8c7629b`/`b0f6f54`；片 3 `2101cfb`/`4bd89c4`/`c4a5006`/`945c074`；测试合同 `5f44fc2`；设计与文档 `c2ed5a7`/`6be2ac5`/`a4d8fe4` 等。HEAD 以 `git log -1` 为准。
- **部署与验收**：见 [W3B_DEPLOY_ACCEPTANCE_20261108.md](spec/W3B_DEPLOY_ACCEPTANCE_20261108.md)。要点：W3a+W3b 同窗口、先备份 `talk.db`、清理 `workspaces/prj_alpha` 测试残留与 `CodexSandboxOffline` ACL；**开闸需显式设置 `TALK_WORKSPACE_RUNTIME_ENABLED=1` 并重启运行时**，默认保持关闭。
- **已知债务/限制**：168 项基线历史测试失败（非 W3b）；`talk_delegate_task` schema 澄清轮数 1/2 与服务端 3/5 不一致（待小片修）；`ActualBootstrapTests` 在 Windows 文件锁下不收敛；astra 未重建（等门可用后验证）。
- **下一步**：用户部署 W3a+W3b → 真实双工作区验收（W3c，需授权）→ 开闸启用新布局角色 → 重建 astra → 清偿小债务。

## 当前快照（2026-11-06 22:00）

- **角色/流程**：本会话 DeepSeek 负责协调、决策、文档与 Git 收尾；开发自测由 **Terra** 负责，**k2.8** 独立复核。协调者不重复跑测试、不在候选上执行开发动作；开发自测 → 协调者核对交付/差异 → k2.8 候选+基线复核 → 协调者决策/集成。交付硬门在 `docs/guides/TASK_WORKFLOW.md` 7.1.1，门禁脚本 `scripts/acceptance_gate.py`（7.1.2）。
- **当前状态**：B/C 完成并推送；**W1（数据边界）、W2a（路径唯一/规范化）、W2b（全页面工作区切换/群过滤/上次工作区）均已上线并验收**；GATE-1 已集成 `4eceef7`。最近提交：W2b `4b59603`，文档 `442f2ff` / `260d168`。API 运行 PID 22168（受控 reload），`/healthz` 200；页面加载 `app.js?v=20261106-workspace-w2b`。
- **数据**：projects 1（`prj_e8fe7066bbec` = `D:\claude-test\TALK`）；groups 478；tasks 477；messages 2431；project_agents 9；临时 W2B 验收项目/群/目录已清理。
- **工作区存储方向（2026-11-06 21:55 确定，见 [WORKSPACE_STORAGE_DECISION.md](spec/WORKSPACE_STORAGE_DECISION.md)）**：**中央 `talk.db` + `TALK/workspaces/<project_id>/` 每工作区目录**；任务/群/角色元数据仍中央库按 `project_id` 区分，工作区目录只放角色运行时、任务附件/日志/导出；真实项目目录（如 `D:\test`）在 TALK 外，只放 `.talk/project.yaml` 指针；**现在不拆每工作区 DB**；分发目标是文件夹绿色版（zip + 启动器），不做安装器/可配置 data_root。
- **W3b 开发授权（2026-11-07 11:35，用户外出前）**：W3a 与 W3b 将**同一窗口部署**，因此直接继续 W3b 开发（不再等 W3a 部署）。W3b 仍按"开发自测 → k2.8 独立复核 → 本地提交/推送"推进，**部署与真实浏览器验收留待用户回来**；286 排队任务用户明确忽略、不处理。当前在途：507（Terra，W3b 只读设计）。
- **W3 进展**：**W3a 全部完成（W3a-1 `22446d5` / 2a `2f4809a` / 2b-1 `340e52b` / 2b-2 `68d6522`），四段独立复核均 approved；验收说明见 `docs/spec/W3A_ACCEPTANCE_20261107.md`。** 尚未部署、未真实浏览器验收；建议 W3a+W3b 同窗口部署（新布局角色在 W3b 前不可运行）。W3b 只读设计已交 Terra（507）。低风险观察项留 W3b：服务端 start 意图 guard 收紧、git 形态新 Key 命名统一、junction 真实用例、`_workspace_key_target` 错误码粒度。
- **澄清额度（2026-11-06 完成）**：新建任务默认 3 次、硬上限 5 次（`ge=MIN=1`），用尽后 `needs_decision`+`awaiting_human`+`checkpoint_reason="clarification_limit"`；487 独立复核 approved（候选/基线各 68 项全绿、断言未弱化、无新增失败），本地提交 `e59629f`。**环境限制**：本机默认 Windows 临时目录不可写，`list_agents` 两项测试裸跑会假失败（基线同样），需显式设置可写 `TEMP`/`TMP`/`SQLITE_TMPDIR`。
- **自动推进授权（2026-11-07 00:30，用户睡前；00:35 细化）**：自动推进 **W3a-1 → W3a-2**（含隔离自证与验收包），每片走"开发自测 → 协调者核对 → k2.8 独立复核 → 本地提交/推送"；**W3b 依赖 W3a（import resolver/布局字段、需新布局角色验证），不在 W3a 验收前写产品代码**，余量只做 W3b 只读设计。**部署顺序**：W3a 验收后先单独 reload 部署澄清额度（无 schema）；W3a 与 W3b 一起验收、一个窗口一起部署（含 `talk.db` 备份 + `storage_layout` 迁移核对）。遇产品取舍/规格矛盾/需凭据时记录并停下等用户，不伪造通过。当前在途：W3a-2a。
- **待确认/遗留**：W2 遗留 run-due null 日程永久 skipped、web 422 原始 detail；真实浏览器双工作区/A 运行中切 B 已由用户验收（agent key 切换未点，API 已验证 agent 仅见 TALK）。
- **新增待办**：`runners/<runtime>/` 运行器适配数据目录（2026-11-06 决策，独立切片、排在 W3 之后）；Key 存放按部署形态自动判定（git 工作区→仓库外，正式部署→`TALK/keys/<project_id>/`）。
- **关键路径**：仓库 `D:\claude-test\TALK`；DB `talk.db`；操作人 Key `D:\claude-test\TALK-private\operator.key`（勿打印）；门禁 `scripts/acceptance_gate.py` + `TASK_WORKFLOW.md` 7.1.2；本轮候选/证据在 `.tmp/workspace-*`、`.tmp/acceptance-gate-*`。
- 恢复指令：`继续项目`（先读本快照、`PROGRESS_HISTORY.md`、`AGENTS.md`、`TASK_WORKFLOW.md`；W3 先设计再派发）。

> 2026-11-08 00:05（DeepSeek，**测试合同同步通过；终轮全量回归中**）：545 测试合同同步复核 approved（546）：9 个测试文件、70+/25-，拒绝断言仍为 409+零 launch+零状态、legacy 正向断言逐字保留、错误码为既定映射、9 模块 233 项独立重跑全绿；**已知缺陷保留**：`bridges/talk_task_tools.py` 的 `talk_delegate_task` schema 仍声明澄清默认 1/上限 2，与 `server/models.py` 的 3/5 不一致（非 W3b，待单独小片修）。提交 `5f44fc2`。**547 终轮全量回归进行中**；通过后即做进度汇总并停止开发。

> 2026-11-07 23:30（DeepSeek，**全量回归结果：24 项测试合同陈旧，需同步后再汇总**）：544 全量 Python 3599 项（146F/50E）、Node 44 项全过；基线 `8aacaf8` 对照后 **24 项为 W3b 引入的确定性测试失败，全部是"存量测试未随新合同更新"**（门控默认关闭 → 409；宿主夹具 `__new__` 构造不满足 workspace_context；错误码 `profile_root_invalid`→`workspace_link_refused`），**无跨模块产品破坏**；170 项为基线同败、约 51 项为 Windows 文件锁环境项、1 项时序敏感隔离通过。**545 已派**：只改测试（10 个文件）按新合同更新，不许放宽断言、不改产品；若查实产品缺陷则报告不硬改。545 绿后再跑一次全量回归，通过才做进度汇总。

> 2026-11-07 22:15（DeepSeek，**W3b 代码完成（片 1/2/3 全部）**）：3b-3 复核 approved（543）：协议矩阵、runtime ready 前 capability 绑定、服务端 claim/ready 二次校验 409 零写入、旧 manager 拒领均可接受；`owner_token` 复用非秘密 nonce、不构成身份认证；越界 `scripts/role_service_host.py` 经复核论证确属必需（规格片 3 白名单本就含它），**协调者予以追认**。提交 `945c074`。累计：片 1（`b1466d2`/`29930a3`/`8b2c033`）、片 2（`d0b81b0`/`a8050da`/`bf0cf4d`/`7b390c9`/`8c7629b`/`b0f6f54`）、片 3（`2101cfb`/`4bd89c4`/`c4a5006`/`945c074`）。**启动门仍默认关闭**。544（k2.8 全量回归）进行中；之后是用户手册/历史文档收尾，再等用户授权部署与 W3c 真实双工作区验收。已知环境限制：`ActualBootstrapTests` 两条在 Windows 文件锁下不收敛（基线同名同因）。

> 2026-11-07 21:20（DeepSeek，**3b-2 完成；按用户要求转完整版 3b-3**）：540 复核 approved（541）：2 项 `ActualBootstrap` 错误在基线 `a7b098e` 与候选**同名同计数**，判环境既有；WinError 5 项受控重跑未复现；候选零新增失败。提交 `c4a5006`（服务端消费 runtime 清单 + 默认关闭开关，四入口共用门）。用户确认**不简化**，**542（3b-3）进行中**：runtime 清单增 `manager_protocol` + 协议允许表、启动就绪前 manager capability 的 role/binding 校验（旧 manager 无 capability 不得 ready，错误码 `workspace_capability_unbound`）、服务端 ready 报告二次校验。门仍默认关闭。

> 2026-11-07 20:50（DeepSeek，**3b-1 完成；3b-2 采用轻量版版本证明**）：3b-1 复核 approved，提交 `4bd89c4`（runtime `runtime/capability.json` 原子发布 + manager health `capability` 块，74 项全绿）。与用户确认：版本证明取**轻量版**——部署级开关（默认关）+ runtime 清单（schema/布局/pid 存活/时间可解析）+ 缺证据拒绝；不引入版本矩阵/签名，manager 块仅诊断。**540（3b-2）进行中**：服务端 `workspace_runtime_capability` 消费清单，默认仍全拒；不会真正开生产门。

> 2026-11-07 20:35（DeepSeek，**W3b 片 3a 完成；3b 拆两片**）：3a 复核 approved，提交 `2101cfb`（恢复链按权威布局、workspace 只读角色目录、拒绝矩阵、stop 隔离；四模块 59 项全绿，基线 1 个既有失败）。3b 拆 **3b-1 能力证明数据面**（runtime 发布 `runtime/capability.json`、manager health 增 `capability` 块，538 进行中）与 **3b-2 服务端门消费能力证明**（默认关闭、部署级开关、旧 manager 拒绝、对抗测试）。门仍未打开。

> 2026-11-07 20:10（DeepSeek，**astra 暂缓；W3b 3a 重派**）：用户决定 astra 往后放，专注 W3b。已确认新角色创建失败码 `profile_root_invalid` 的直接原因是 `workspaces/` 里一个 `CodexSandboxOffline` 的测试残留 ACL（`prj_alpha`，project_root 指向 `.tmp-tests`）；更根本的是 12:05 重启运行时把 **W3a 代码带上了生产**，新角色一律 `workspace-v1`、而启动门仍关闭，所以"能建不能跑"。用户选择继续 W3b、暂不重建 astra。534 的候选已存 `.tmp/w3b-s3a-partial-534.patch`（`git apply --check` 通过）；**536 已重派 3a**，白名单扩入 `server/local_runtime.py`、`server/role_startup.py`，要求接通恢复调用链并处理两个失败的真实 CLI 测试。

> 2026-11-07 20:00（DeepSeek，**片 3a partial；准备重启**）：534 只完成"workspace manager health 路径解析 + 无证据时保守拒绝恢复"，但恢复调用链在 `server/local_runtime.py`、`server/role_startup.py`（不在白名单）未接通，正常恢复未实现；两个真实 CLI 合成测试仍失败（`runtime_stop_blocked`、8 秒超时）。候选已存 `.tmp/w3b-s3a-partial-534.patch`，工作区已回退干净。**3a 需扩白名单重派**。另：535 复现 astra 只回 `1.`（非偶发），用户计划重启后删除并手动重建 astra；若重建仍截断，再修 `bridges/codex_execution_native.py` 的 `item/completed` 收集。当前内存紧张，用户将重启电脑；重启后需 `run.ps1 -Action serve -Apply` 并手动 start 需要的角色服务。

> 2026-11-07 19:45（DeepSeek，**W3b 片 2 完成；片 3 开始**）：2c-2（四 channel store 路径解析，仅测试）533 approved，提交 `b0f6f54`。**W3b 片 1、片 2 全部完成并推送**，启动门仍关闭。片 3 拆 3a/3b：3a stop/recovery 角色隔离（534 进行中）；3b 能力绑定/版本证明（门默认仍关闭）；**W3c 真实双工作区验收与开闸需用户另行授权**。

> 2026-11-07 19:35（DeepSeek，**W3b 片 2c-1 完成**）：宿主在 workspace 分支注入 `TALK_EXECUTION_SESSION_STORE`（角色 `sessions/execution-session-store.sqlite3`），spawn 前逐级建/重核目录；缺键/不一致/运行中替换都拒绝；legacy 不设该变量、逐字不变。531 复核 approved：基线 43 项 / 候选 47 项（含真实 junction 反例）全绿，提交 `8c7629b`。2c-2（四 channel/store 读取验证与必要修补）进行中。

> 2026-11-07 19:20（DeepSeek，**W3b 片 2b 完成**）：2b-1 `a8050da`（runtime 传上下文 + 通用 host）、2b-2a `bf0cf4d`（codex/kimi host）、2b-2b `7b390c9`（dsh/workbuddy host）全部合入推送。2b-2b 首审发现 dsh 错误消息 7 处 `??` 乱码（527 changes_requested），528 返修后 529 定向复验 approved（乱码清零、逻辑未变、10 项全绿）。片 2c 拆两片：2c-1 宿主把角色 session store 经 `TALK_EXECUTION_SESSION_STORE` 传给子进程（530 进行中）；2c-2 核四 channel/store 读取并补必要修补。**启动门仍关闭。**

> 2026-11-07 14:50（DeepSeek，**W3b 片 2b-1 边界修正并重派**）：520 正当阻塞——只授权通用 host 无法落地，因为 runtime 把 `workspace_context` 放在 spec 里但 spawn 只传 argv，四 runner 又各自算 health/drain。已把 `scripts/talk_runtime.py` 纳入 2b-1 白名单（只做"显式把上下文传给通用 host"这一条链路），四 runner host 留 2b-2；521 重做中。520 顺带修正的 `tests/test_role_service_host.py` 测试准备顺序保留到 521 候选。

> 2026-11-07 14:25（DeepSeek，**W3b 片 1 完成并推送**）：片 1a 服务端统一意图门 `b1466d2`、片 1b 路径派生/Key 错误码/真实 junction `29930a3`、片 1c 错误码白名单与 worker 直报 `8b2c033`，三段独立复核均 approved（517 三树复跑全绿，并把争议的 `OSError 5 retention_open_unavailable` 裁决为**环境噪声**）。片 2 拆 2a/2b/2c 串行：2a `talk_runtime` 可信角色上下文 + 四 runner spec；2b `role_service_host` 与四 runner host 的 HOME/ownership/control/health/logs；2c execution session store 与四 channel。**服务端启动门在片 2/3 仍保持关闭**。

> 2026-11-07 13:10（DeepSeek，**运行时重启的连带影响已修复**）：12:02 重启运行时把各角色 `desired_state` 置为 stopped，重启后未自动拉起；导致 k2.8 停止、511 复核任务排队 1 小时无人领取（Terra 也停着）。已显式 start k2.8（`ins_2bdf58dad3b6`）与 Terra（`ins_201f69011e2d`），均 running/ready；511 等待 job 已重启。**运维注意**：今后重启运行时后，需要显式 start 需要的角色服务（或依赖 auto_start/启动偏好）。

> 2026-11-07 12:18（DeepSeek，**astra 可用性结论**）：astra 服务 running/ready，实际跑通两次咨询任务（510/512）。**限制**：多行回答会被截断成首段（510 得到 `1.`）；单行短答正常（512 正确返回 `4`）。**使用方式**：咨询时要求"一句话、单行、≤60 字"，仅答疑、不派操作任务、不要求改文档。若需长回答，先把问题拆成多个单行小问。

> 2026-11-07 12:10（DeepSeek，**运行时重启修复 astra；W3b 片1a 交付待复核**）：astra 之前卡启动的根因是 native 授权留下的宿主未被运行时重建、launch 无人 claim；按用户授权重启运行时后所有宿主 serving，astra 启动 **running/ready**（instance `ins_b4adf32cc411`），已发一次只答疑咨询（510）验证通路。注意：本次会话沙箱内 Python 无法写 `~/.talk/**`（`launcher.out` 被拒），`--detach` 失败；改用 **WMI `Win32_Process.Create`** 在沙箱外启动运行时（pid 17160），API `/healthz` 200。W3b 片 1a（服务端统一意图门，509）已交付：4 文件、88 项测试全绿，511 独立复核中；片 1b/2/3 未开始。

> 2026-11-07 11:40（DeepSeek，**Astra 咨询角色：已建，待用户授权**）：按用户要求在 codex 运行器新增模型选择 `gpt-6-astra`（choice `rmc_6ec2c7af90d5`），并创建咨询角色 **astra**（`agent:prj-e8fe7066bbec.astra-a88d641d`，role request `astra-consultant-20261107` 已 provisioned）。启动被 `native_authorization_required` 阻断：新角色 HOME 需在 **https://auth.openai.com/codex/device** 输入设备码 `44FW-7Z1DC`（会过期；过期后 cancel 再 start native-setup 可重发）。**用途约束**：astra 只做答疑咨询，不派操作任务、不改任何文档。授权后 start 服务并做 smoke 咨询。

> 2026-11-07 11:25（DeepSeek，**W3a 全部完成，待人工验收**）：W3a 四段全部合入并推送——W3a-1 路径合同 `22446d5`、W3a-2a 创建流程 `2f4809a`、W3a-2b-1 后端启动拒绝 `340e52b`、W3a-2b-2 前端提示（本次提交）。506 独立复核 **approved**：新载荷固定 `auto_start:false`、旧载荷原键重试、`storage_layout` 来自真实 `request_projection` 字段、提示仅 workspace-v1、legacy 不受影响、58/58 Node 测试、编码干净。**部署与真实浏览器验收未做**：W3a 新布局角色仍不可运行（设计如此，等 W3b）；建议 W3a+W3b 同一窗口部署，澄清额度可在 W3a 验收后先单独 reload。**下一步**：W3b 只读设计交 Terra（用户指定，不用大K）；验收说明待补。

> 2026-11-07 11:20（DeepSeek，**收件与改派安排**）：补收 489（W3a-1 复核 approved）、478（W3a 设计 complete）、426（旧返修 complete）。仍开放：**286** 为 2026-10-20 起 `manual_pause` 的排队任务，需发起者（codex）或用户在页面取消；**498（W3b 只读设计）** 因 hy4 执行器 `workbuddy_acp_timeout` 失败，**按用户要求改派 Terra**（不交给大K），等 505 完成后再派新任务（Terra 同一时刻只接一个任务）；大K 保留为备用开发/复核替补。

> 2026-11-07 11:10（DeepSeek，**W3a-2b-1 完成并推送**）：503（大K）实现后端启动拒绝——host 单角色 start/既有 pending 执行（写意图/claim/spawn 前）、start-all 逐角色跳过并报告、`talk_runtime` 固定+动态宿主 reconciliation、启动偏好 activation 只写 skipped 回执；新增最小只读 `GET role-storage-layouts`（只两键，不改 roles 公共投影）。504 独立复核 **approved**：9 文件 +257/−15，候选 63/63 对基线 56/56 零新增失败，相关回归 71+61 项全绿，断言未弱化、编码/越界通过。已提交并推送。**限制留痕**：①服务端 start 意图 API 在未传 guard 时仍会受理 workspace-v1 意图（实际拒绝在 host 执行层），直连调用会产生"被反复拒绝但不 claim"的 pending launch，建议 W3b 收紧；②`server/role_startup.py`、`server/routes/role_services.py` 超出设计建议白名单但为 activation 拒绝所必需（透传 guard），已在派发中授权。**下一步**：W3a-2b-2（`web/role-creation.js` 禁用新布局自动启动并提示）按用户要求交回 Terra。

> 2026-11-07 10:35（DeepSeek，**W3a-2a 完成并推送**）：492/494/496/499 四段合批：新角色与请求行写 `workspace-v1`、请求投影/冻结形态、路径登记接受 workspace-v1 引用、provision 真正写入（Key+三档案+`workspace-v1:` 登记）、worker 按"项目级目录→`workspace.json` 排他发布→建角色→角色目录→发布 Key→provision→复查租约→ACK"接线。500 独立复核 changes_requested（核心全过）；501 修两处（守卫测试适配、3 处中文乱码）；502 定向复验 **approved**（126 项四模块全绿、差异极简、断言实质）。已提交并推送 `2f4809a`。**503 在途**：W3a-2b-1 后端启动入口拒绝 workspace-v1 角色。另记：Terra 昨夜 497 僵尸（已停服务，待其重启后取消）；hy4 执行器模型失败退出码 2，暂不可用；大K 接替开发。

> 2026-11-07 02:00（DeepSeek，**W3a-2a 仍未完成，暂停自动推进**）：495 只补了回归测试（`tests/test_workspace_provision_flow.py`），未实现产品改动；它确认了一个真实缺陷——**worker 在未创建 `workspace.json` 时仍报 `provisioned`**（新增用例 `test_non_git_request_creates_workspace_and_profiles` 失败，111 项中 1 项失败）。当前 W3a-2a 已落地：新角色/请求行写 `workspace-v1`（492）、请求投影返回布局/冻结形态 + 路径登记接受 workspace-v1 引用（494）；**未落地：worker 目录/`workspace.json` 排他发布与调用顺序、provision 真正写入、请求创建时冻结 `deployment_shape`、完整集成场景**。工作区改动已作为 **WIP 提交（本地，未推送，勿部署）**。**下次续做建议**：先按设计第 27–33 行一次性完成 worker+provision 闭环（附失败用例名与白名单），再补 2b 启动拒绝/页面提示，最后两片一起送 k2.8 复核。W3a-1 已推送（`22446d5`）。

> 2026-11-07 01:50（DeepSeek，**W3a-2a 中间状态（勿部署）**）：工作区有未提交改动——492：新角色/新请求行写 `storage_layout="workspace-v1"`；494：请求投影返回布局/冻结形态、路径登记接受 workspace-v1 引用（149 项测试通过）。**495 正在收口 worker 目录/`workspace.json` 与 provision 真实写入**；在此之前新布局角色不具备可用开通流程，**禁止部署或启用**。W3a-1 已提交并推送（`22446d5`）。W3a-2b（启动拒绝 + 页面提示）未开始。

> 2026-11-07 00:57（DeepSeek，**W3a-1 完成并过审**）：488 交付（`project_roles`/`role_provision_requests` 幂等加 `storage_layout`、`server/workspace_paths.py` resolver、provision Key 形态守卫、profiles 兼容、`.gitignore`）→ 489 独立复核 **approved 8/8**：候选四模块 120 项、基线 113 项，无新增失败；复核者本机真实 symlink 用例通过（488 当时的 skip 属其会话权限）；未知 `storage_layout` 值 fail-closed 实证；workspace-v1 写盘被 `workspace_layout_not_ready` 阻断（留给 W3a-2）。提交 `22446d5`。遗留低风险项转 W3b：junction 真实用例、git 形态新 Key 命名与 legacy 统一、错误码粒度。

> 2026-11-06 23:35（DeepSeek，**澄清额度片完成并合入**）：485 实现（MIN=1/DEFAULT=3/LIMIT=5、`ge` 绑 MIN 防 1–2 轮回归、`clarification_limit`、加轮 +1 到 5 后 409）→ 486 返修定性（两项 `list_agents` 在基线 8849919 同签名复现，可写 TEMP/TMP 下 68 项全绿）→ 487 独立复核 **approved**（自建候选/基线隔离树各 68 项全绿 103.4s/104.3s，断言未弱化，仅 3 文件改动）。已提交 `e59629f`。**环境限制**：本机默认 Windows 临时目录不可写，裸跑这两个用例会假失败（基线同样），后续测试/验收须显式设可写 `TEMP`/`TMP`/`SQLITE_TMPDIR`。生产生效（reload API）未做，等用户授权。

> 2026-11-06 23:05（DeepSeek，**W3a 设计过审**）：483 交付设计稿 v3（只把全量 discover 命令加 `-t .` 并补根目录旧文件约束），484 定向复验 **approved 4/4**：v3−v2 仅 +3/−1 行；导入阶段实测带 `-t .` 加载 3492 用例 exit 0、不带则原样复现 ImportError；机理查明是多份测试在 import 期 `sys.path.insert(0, PROJECT_ROOT)` 抢占，导致根目录旧 `test_talk_runtime.py` 被命中（窄模式不触发，非问题消除）；编码/越界/无夹带通过。设计稿已镜像到 `docs/spec/W3A_DESIGN_20261106.md`（逐字保留 + 状态头）。W3a 实施待用户确认后拆两子包。

> 2026-11-06 22:57（DeepSeek，**澄清机制小优化已定**）：用户确定——新建任务澄清额度**默认 3、硬上限 5**；用尽后仍走 `needs_decision`+`awaiting_human`+释放认领，由发起者程序轮询 attention 通知并处理（不新增状态、不伪造 blocked）；同时加**提问质量门**（已尝试什么/两个选项+代价/建议默认/为何不能自决，驳回也计一轮）。已写入 `AGENTS.md`「澄清额度与提问质量门」；代码改动（`server/models.py` 常量与 Pydantic 边界、`server/routes/tasks.py` 升级原因标记、相关测试）作为独立小片实施，W3a 设计片收尾后串行进行（两者共用 `models.py`）。

> 2026-11-06 22:27（DeepSeek，**479 复核 changes_requested；交付格式两次无效**）：479 独立复核 W3a 设计稿：6 pass / 1 fail / 2 needs_change——fail 为建议命令 `python -m pytest` 不可用（应 `python -m unittest`，10 个测试文件均在）；needs_change 为 `server/db.py` 须进白名单（仓库无迁移模块，只在内联 `ALTER TABLE` 改 schema）、`workspaces/<p>/roles/<m>/` 目录链创建者与半创建恢复未写明；另 2 处行号差 1。479 与 480 两次投递均被判 `invalid`（数组字段写成字符串；单条 456>300；`complete` 与 `verification.result=fail` 自相矛盾），已按"已处理"收件，结论仅作 v2 修正依据。已把 `talk-delivery-1` 机械约束固化进 `TASK_WORKFLOW.md` 7.1.1（数组/对象类型、单条 20–300、`fail` 时结论必须 `partial`、禁 `schema` 字段）。481 正在出设计稿 v2（并入 Key 部署形态与 `runners/` 决策）。

> 2026-11-06 22:25（DeepSeek，**Key 存放与运行器目录决策**）：用户确定——①开发期本机 TALK 处于 git 工作区，Key 不落 TALK 目录（沿用仓库外 `~/.talk/keys`，现"拒绝仓库内 Key"守卫保留）；TALK 正式使用/分发后（数据根非 git 工作区），Key 作为角色要素落 `TALK/keys/<project_id>/`，`.gitignore` 补 `/keys/` 兜底。②TALK 下为终端运行器提供独立目录 `runners/<runtime>/`，只存适配数据/元数据（模型清单/别名、强度选项、版本基线、探测缓存），不放凭据/登录态、不托管 CLI 本体。已写入 `docs/spec/WORKSPACE_STORAGE_DECISION.md` 决策 7/8 与目录图，`DEVELOPMENT_ROADMAP.md` 登记为 W3 之后的独立切片；W3a 设计据此修正（原"仓库根工作区默认保留旧 Key 路径"改为按部署形态自动判定）。

> 2026-11-06 22:00（DeepSeek，**工作区存储方向确定**）：中央库 + 每工作区目录；真实项目在 TALK 外只放 `.talk/project.yaml`；`TALK/workspaces/<project_id>/` 放角色运行时/任务附件/日志；不拆库；文件夹绿色版分发。详见 `docs/spec/WORKSPACE_STORAGE_DECISION.md`。W3 先设计/拆分，不直接开发。

> 2026-11-06 19:45（DeepSeek，**创建 W2b 临时验收工作区**）：按用户选 1，创建 `prj_w2baccept20261106`（`W2B 验收工作区`，root `D:\claude-test\TALK\.tmp\w2b-acceptance-20261106\workspace`，human:bobo 维护者），群 `group:04d3aa77c928`（W2B 验收群）；Terra 同步返回 `identity_exclusive_reference_refused`（身份跨项目独占，W3 范围），因此验收项目 0 角色；任务必须 target agent，未创建占位任务。human 下拉应出现 2 项，agent 仍仅 TALK。待用户浏览器验收切换/刷新/回 A 数据不变；验收后删除临时项目/群/目录。

> 2026-11-06 17:00（DeepSeek，**W2b 通过并部署；待真实浏览器验收**）：477 复核 approved：19 文件范围合规；后端 agent 过滤真实用 ProjectAgent/ProjectRole；`setActiveProject` 全文无 stop/start/cancel；群/任务/Hall/角色随 activeProjectId；上次工作区按成员四态覆盖；独立重跑 68 项/48.2s、Node 406/406/6.5s；基线 b4b8d21 对照 8+16 项基线失败全部修正、新增失败=0，非弱化。已集成 19 文件（LF blob `507f348c`），提交推送 `4b59603`；reload API 后 PID 22168、`/` 命中 `app.js?v=20261106-workspace-w2b`，agent projects 1、groups 65，human groups 478。真实浏览器 A/B 未验；当前仅 1 个工作区，需临时第二工作区才能验收切换。

> 2026-11-06 16:45（DeepSeek，**W2b 476 complete；477 复核**）：476 交付 19 文件（18 tracked + 未跟踪 `tests/workspace_project_switch.test.cjs`），product 只 `server/routes/projects.py`、`web/app.js`、`web/index.html` + 2 文档，其余测试；后端 68 项/47.942s、Node 406 项/6.221s、`node --check`/diff-check 全绿；tracked diff LF blob `507f348c` 与本地一致。真实浏览器双工作区/运行中任务未验（limitation）。477 派 k2.8：Agent 可见性、群过滤/切换清理、全页面一致性、上次工作区 A/B、无 stop、19 文件断言是否弱化、残余风险；通过后集成/部署。

> 2026-11-06 16:30（DeepSeek，**W2b 派发 476**）：用户确认“刷新后仍停留在刷新前的工作区”后开 W2b。Terra 范围：①`GET /api/projects` human 全部/agent 只列 ProjectAgent 或 ProjectRole 已加入；②`loadGroups` 带 `project_id=activeProjectId`；③`setActiveProject` 重载 groups、清理不属于新项目的 activeGroup/历史、刷新 Hall/群/成员、**不调用任何 stop/start/取消**；④初始化先恢复上次项目再加载 tasks/agents/groups，无效回退；⑤创建群/任务/上传用 activeProjectId；⑥不新增创建工作区入口；⑦测试覆盖 A/B 刷新保持、不可用回退、Agent 可见性、群过滤/无 stop；⑧文档同步。候选基线 `b4b8d21`。

> 2026-11-06 16:20（DeepSeek，**GATE-1 通过并集成 `4eceef7`；W2b 待确认**）：475 终验 **approved**：F1–F5 全部修复；14 项 gate 测试独立复跑全绿、基线 c66ba07 27 项全绿/新增失败=0、无断言弱化；gate 自算 LF blob `cce2166d` 为唯一可过值，协调者本地 PS 管道 `202d37c0` 是 CRLF 污染，Terra 交付值正确；cp936 下 `--json` 两态 UTF-8 可解析；脚本无 `?{2,}` 占位；权限/边界干净。3 文件已应用到主工作树，提交推送 `4eceef7`。下一步 W2b：重点是把群聊/Hall 也按 activeProjectId 过滤，切换时清理跨项目会话选择但不停止任何运行任务/服务；任务/角色页已项目化，需验证全页面一致；Agent 只列已加入项目；最后刷新恢复上次工作区。

> 2026-11-06 16:05（DeepSeek，**474 fix2 全绿；475 复核**）：474 交付 complete：14 项 gate 测试/17.626s、27 项回归全绿；F1 stdout/stderr UTF-8、F2 脚本无 `?{2,}` 占位、F3 文档改 gate 自算 LF 口径、F4 真实 CLI exit 1/`--json` 测试、F5 delivery 模板/无 schema；候选 1 tracked + 2 未跟踪，无业务改动；交付 blob `cce2166` vs 本地 PS `202d37c`，已交 475 按 gate LF 口径查清。475 派 k2.8 逐项复验 F1–F5、14+27、基线 c66ba07、473 已通过项未回归；通过后集成。

> 2026-11-06 15:55（DeepSeek，**GATE-1 473 changes_requested；474 fix2**）：473 独立复验：候选 11 项/12.074s、27 项/20.106s 全绿，基线 c66ba07 27 项全绿、新增失败=0；范围/边界/白名单/AST/五类 CLI fail（partial/错 blob/new_failures/文档??/常量未授权，均 exit 1）、用法 exit 2、交付契约均通过。需小修：F1 `--json` 在 cp936 下输出 GBK（json.load 失败）；F2 脚本自身 159 行 `'??????????'` 占位、会触发自身 doc.encoding；F3 blob 口径文档受 PS 5.1 管道 CRLF 影响，gate 自算 LF `486ce64` 才可过，`4764dcf`（PS）与 `3f4d089`（无法复现）均被拒。F4 补 exit 1 CLI 单测、F5 补 delivery 模板/无 schema 说明。474 fix2 已派。

> 2026-11-06 15:35（DeepSeek，**472 合法交付；473 复核**）：472 重提合法 `talk-delivery-1`（无 `schema` 字段），结论 complete，沿用 471 的 11 项/20.963s 与 27 项/24.701s 证据；候选 1 tracked + 2 未跟踪，交付写 tracked diff blob `3f4d089…`（协调者本地 `4764dcf…`，已列入 473 疑问 A 要求查清口径）。473 派 k2.8：独立跑 11+27、基线 c66ba07、检查生成物白名单/常量授权/AST 误报、CLI 退出码 0/1/2、partial/blob/新增失败/文档编码/未授权常量五类真实 fail、交付无 schema、脚本不跑测试；通过后才集成。

> 2026-11-06 15:30（DeepSeek，**471 交付 invalid；472 只重提格式**）：471 fix1 代码/测试已完成：`tests.test_acceptance_gate` 11 项/20.963s、27 项回归全绿，候选 1 tracked + 2 未跟踪；但结果 JSON 多了 `schema` 字段，被 `talk-delivery-1` 以 `unknown_field` 拒收，业务结论 invalid，不能收货。按“交付契约必须合法”派 472：不改候选/不重跑测试，只按允许字段重提 task_id=472 的合法 JSON（tracked diff blob 以本机 `git diff | git hash-object` 为准），之后 k2.8 复验 fix1 的实际质量。这是 gate 交付 schema 检查的又一个真实用例。

> 2026-11-06 15:25（DeepSeek，**GATE-1 470 partial；471 补强**）：470 交付 partial：`scripts/acceptance_gate.py` + 8 测试 + 7.1.2 文档；8 项/10.5s、27 项回归全绿；候选 1 tracked + 2 未跟踪，tracked blob `4764dcf`。自报两项不足：①`allowed_untracked` 只核对清单，未证明是生成物，产品文件可混入；②常量授权只比 AST 语句，注释-only 提及未覆盖。按“发现问题补进脚本”原则，471 已派 fix1：固定生成物模式（`Microsoft/`、`.tmp-tests/`、`.tmp/`、`__pycache__/`、`*.pyc`、`*.log`、`*.db-wal/shm`、`.pytest_cache/`）拒绝产品文件；注释-only 不触发授权（注释不改变运行时常量），实际赋值变更未授权仍 fail；用测试锁定两种行为；8+ 项与 27 项回归全绿后交 k2.8。

> 2026-11-06 15:20（DeepSeek，**GATE-1 派发 470**）：W2a 已上线（PID 23780、路径规则真实校验通过）。按用户确认开 gate 脚本：`scripts/acceptance_gate.py` 读 manifest `talk-acceptance-gate-1` + delivery + review `talk-review-gate-1`，检查交付 complete、tracked diff blob/未跟踪文件、日志存在、复核 candidate+baseline 与新增失败=0、文档 strict UTF-8/`?{2,}`/U+FFFD、常量 `authorized_mutations`、主工作树干净；profile `code/doc`；退出码 0/1/2；不执行测试。新增 `tests/test_acceptance_gate.py`（≥6 正反例）与 `TASK_WORKFLOW.md` 7.1.2；候选基线 `c66ba07`。

> 2026-11-06 15:15（DeepSeek，**W2a 已部署并真实验证**）：经用户“先部署”授权，runtime 受控 reload 后 API PID 21360→**23780**，`/healthz` 200、marker 自动清理。真实 API：重复 `D:\claude-test\TALK`（exact/case）→409 `project_root_path_conflict`；相对路径→422 `project_root_path_relative`；不存在/文件→422 `project_root_path_invalid`；PATCH 清空→422 `project_root_path_required`；projects 仍 1、根路径未变、roles 18；tasks 469/groups 470（+6 为 W2a 任务/Hall）。W2a 无 schema 变更。

> 2026-11-06 15:05（DeepSeek，**W2a 通过并集成推送 `eb5b129`；部署待确认**）：469 终验 **approved**：第 811 行与期望精确相等、`?`=0/U+FFFD=0、strict UTF-8；与 fix1 仅该行不同；无代码/测试变化，467 的 223/223 全绿继续成立；主工作树干净、未跟踪测试在、diff blob `3da57f0b` 一致。W2a 5 文件已复制到主工作树（diff blob 与候选一致），提交推送 `eb5b129`。W2a 无 schema 变更，API reload 即可生效；待用户确认部署窗口。

> 2026-11-06 15:00（DeepSeek，**468 文档编码修复完成；469 终验**）：468 只改 `docs/spec/PROJECT_INTEGRATION.md:811`，交付自报该行 `?`=0、U+FFFD=0、strict UTF-8、相对 fix1 仅此一行；协调者用 Python 读回为“`project_root_path` 必须为绝对路径、存在且为目录；同一规范路径按 Windows 大小写不敏感只允许一个项目占用。”，候选 tracked diff blob `3da57f0b…`，主工作树干净；未跑测试。469 派 k2.8 快速终验：只核该行/编码/相对 fix1 仅此改动/无代码测试变化/diff-check；不重跑 223 项。

> 2026-11-06 14:55（DeepSeek，**467 仅剩文档编码；468 fix2；文档编码纳入门禁回归**）：467 独立复跑候选 9 模块 **223/223 全绿**（221.966s，无 skip）；基线 9b91650 同清单 193 项恰两项已知失败（assignment 缺 project_id、tool 数 9 vs 10），候选新增失败=0；fix1 仅改 `tests/test_project_controller_assignment.py` 两处，无断言弱化；`talk_follow_tasks` 确为 `TOOL_SCHEMAS` 第 10 个正式工具；W2a 路径验收 30 项通过；diff blob/日志/边界一致。**唯一阻断**：`docs/spec/PROJECT_INTEGRATION.md:811` 为 104 个字面 `?` 的 mojibake（464 已存在，fix1 未引入），需一行 UTF-8 重写。已建 fix2 候选派 468，并新增文档编码回归规则：文档变更必须附 strict UTF-8 + `?{2,}`/U+FFFD 扫描，开发/复核各跑一次（写入 TASK_WORKFLOW 7.1.1）。

> 2026-11-06 14:35（DeepSeek，**466 全绿；467 复核**）：466 交付 complete：9 模块 **223 项/231.071s 全绿**，日志 `.tmp/workspace-w2a-fix1-20261106/task-466-unittest.log`（尾部 `Ran 223 tests ... OK`）；只改两处测试——assignment 4 个 POST 补 `project_id="prj_ctl"`、`PROJECT_TOOL_NAMES` 追加 `talk_follow_tasks` 且长度 10；W2a 产品实现、`test_project_root_identity.py` 等保持 464 状态。候选 4 tracked + 1 未跟踪，tracked diff blob `02410106…`；生成物 `Microsoft/`、`.tmp-tests` 不纳入。467 已派 k2.8：独立跑 9 模块 + 基线 9b91650 逐名对照、检查两处测试无弱化、W2a 路径验收、changed_files/日志/diff blob。

> 2026-11-06 14:30（DeepSeek，**门禁回归规则已加入 TASK_WORKFLOW 7.1.1**）：用户确定——决策者发现任务包歧义/门禁漏检时，把**可机械化部分**补进 gate 规则/manifest 字段并加回归用例；不可机械化的留人工判断。规则/字段由决策者维护，脚本代码变更仍走开发/复核。已登记两例：①候选差异必须用 `candidate.tracked_diff_blob` + `candidate.untracked_files[]` 分开，禁止裸“blob”，预派发 lint 对照 `git status`；②工具面/常量集合变更必须在 manifest 声明 `authorized_mutations`（长度+元素），未声明即阻断。gate 脚本仍排在 W2a 之后做；465 的 diff blob / talk_follow_tasks 两例将作为首批回归用例。

> 2026-11-06 14:20（DeepSeek，**465 blocked 是任务歧义；466 澄清授权**）：465 未改任何文件，blocked 两点均非候选问题：①任务写的 `5dad2be3…` 是**候选 tracked diff blob**（`git diff | git hash-object --stdin`），Terra 误拿未跟踪新测试单文件 hash 对比，误判漂移；②`TOOL_SCHEMAS` 10 项（第 10 为 `talk_follow_tasks`），`PROJECT_TOOL_NAMES` 9 项；任务只授权改长度 10，未明确授权把 `talk_follow_tasks` 加入常量，故元组相等仍会失败。466 已澄清：diff blob 定义、明确授权追加常量+长度 10；继续修 assignment 测试 4 处 project_id；要求 9 套件全绿后交 k2.8。任务正文以后统一写“tracked diff blob”，不写裸 blob。

> 2026-11-06 14:10（DeepSeek，**W2a 464 partial；465 只修两项基线测试**）：464 实现 `project_root_path` 绝对/存在/目录、`resolve()` 规范落库、Windows 大小写不敏感唯一（409）、PATCH 清空拒绝，并新增 `tests/test_project_root_identity.py`；但指定 9 套件 223 项中 2 项失败，逐名对照基线 9b91650 同败：①`test_assignment_does_not_change_task_permissions` 4 个任务 POST 未补 `project_id`（W1 合同遗漏）；②`test_tool_surface...` 期望 9 工具、实际 10（`talk_get_delivery` 早已加入，测试未更新）。按硬门 partial 不收货，已建 fix1 候选派 465 只改这两处测试（不改 W2a 产品实现），要求 9 套件全绿 + 原始日志 + changed_files 排除 `Microsoft/`/`.tmp-tests` 生成物；之后 k2.8 复核。

> 2026-11-06 13:50（DeepSeek，**W1 部署验证完成；W2a 派发 464**）：W1 已用 runtime 受控 reload 部署（API PID 21360、迁移列/索引生效、无项目任务/群/上传 422、群过滤/run-due 200、数据计数 intact）。用户确认 W2a 先行。464 已派 Terra：项目根路径必须绝对/存在/为目录、`resolve()` 规范化落库、Windows 大小写不敏感唯一（409）、PATCH 不允许清空、失败不写库；更新假路径测试；新建 `tests/test_project_root_identity.py`；候选基线 `9b91650`。要求指定 9 套件全绿 + 原始日志 + changed_files（含未跟踪）才可 complete；交付后 k2.8 复核（固定清单+疑问）。

> 2026-11-06 11:25（DeepSeek，**W1 已部署并真实验证**）：经用户“部署”授权，使用 runtime 受控 reload（写 `reload-api.request`，不重启角色宿主）后 API 由 PID 3000 切到 **21360**，`/healthz` 200，marker 已被 runtime 清理。迁移核对：`files.project_id`、`agent_task_schedules.project_id` 及 `ix_*_project_id` 均存在；数据计数 tasks 463、groups 464、roles 18、files 0、schedules 0（比清理时多 6 任务/6 Hall，均为 W1 开发/复核任务，非丢失）。真实 API 检查：无项目任务/群/上传均 422、`GET /groups?project_id=prj_e8fe7066bbec` 200（464 个群均为该项目）、`run-due` 200、`/api/projects` 200；检查请求未新增数据。

> 2026-11-06 11:15（DeepSeek，**W1 通过并集成推送 `44f4d18`；部署待确认**）：463 终验 **approved**：fix2 相对 fix1 仅 `docs/spec/SDK.md:351` 一行；Python UTF-8 读回为正常中文；三份文档无 0x3F 连串/U+FFFD；无代码/测试变化，461 的 284/284 全绿继续成立。W1 17 文件已应用到主工作树（diff blob `06a6f841` 与候选一致，含未跟踪 `tests/test_workspace_boundary.py`），提交并推送 `44f4d18`。生产 API 未重启，迁移（files/schedules 补列+索引）尚未在运行实例执行；已备份生产库。待用户确认是否现在部署。

> 2026-11-06 11:10（DeepSeek，**462 fix2 文档修复完成；463 快速终验**）：462 只改 `docs/spec/SDK.md:351`，交付自报 UTF-8 正确、0x3F 为 0、相对 fix1 仅此一处；协调者用 Python `open(encoding='utf-8')` 读回该行为正常中文（“`GET /api/groups` 的 `project_id` 为空串或纯空白时视为未传，返回全部可见群。”），候选 blob `06a6f841…`，主工作树干净；未跑测试。463 派 k2.8 快速终验：只核 fix2 相对 fix1 是否仅该行、UTF-8/0x3F/U+FFFD、三份文档编码、未跟踪测试在、diff-check；不重跑 284 项。

> 2026-11-06 11:05（DeepSeek，**461 复验仅剩文档编码阻断；462 fix2**）：461 独立重跑候选 9 套件 **284/284 全绿**（138.839s，无 skip/xfail），基线 7571910 同 9 套件 279 真实项全绿（唯一 error 是新增测试模块在基线的预期 loader 失败），逐名无新增失败；4 套件更新无断言删除；run-due null 逐条 skipped、合法日程提交；群空串过滤忽略；SDK 同步/异步一致。**唯一阻断**：`docs/spec/SDK.md:351` 为字面 0x3F 乱码（15 个问号），需 UTF-8 重写。已建 fix2 候选（blob 同 ca39baa）派 Terra **462** 只修该行并扫描三份文档编码；不重跑 284 项。之后 k2.8 快速终验。

> 2026-11-06 10:50（DeepSeek，**460 fix1 complete；461 复验；交付硬门固化**）：460 交付 17 文件（16 tracked + 新测试 `test_workspace_boundary.py`），9 套件 284 项/156.4s 全绿，日志 `.tmp_fix_final.log`（579KB），中间 105 项全绿；4 套件按新合同更新、SDK 文档/测试补 project_id、run-due 对 null 日程逐条 skipped、群空串过滤归一。协调者只读核对：主工作树干净、候选 blob `ca39baa…`、日志尾部 `Ran 284 tests ... OK`；开发者日志无基线对照，已按新门禁把“候选+基线对照”列入 461 复验。`TASK_WORKFLOW.md` 新增 7.1.1 交付/复核硬门：全绿、基线对照、原始日志、未跟踪文件；协调者收货先查证据，缺失直接退开发。

> 2026-11-06 10:30（DeepSeek，**459 复核 changes_requested；460 fix1 返修**）：459 独立复核确认：范围/授权矩阵/strip/迁移（生产备份副本实测）通过；但 4 个既有测试套件未更新——`test_tasks` 3F/25E、`test_groups` 9F/1E、`test_task_binding_snapshot` 2F、`test_talk_client` 5E，共 50 项非通过；同基线 7571910 克隆 103 项全绿，排除环境；另 `docs/spec/SDK.md:51,137` 未跟 `send_file` 新签名、`run-due` 遇历史 null 日程整批中止。已建 fix1 候选（458 状态原样 + 未跟踪新测试），派 Terra **460** 修：4 套件按新合同更新（backward-compat 测试改 422）、SDK 文档/测试补 project_id、run-due 跳过 null 并逐条回报、群过滤空串归一化；要求全绿后交 k2.8 复验。

> 2026-11-06 10:25（DeepSeek，**W1 交付 partial；按新流程派 459 复核**）：458 交付 12 文件（11 tracked + 新测试 `test_workspace_boundary.py`），新测试 3 项与文件套件 9 项单独通过，但任务/群/文件/绑定快照/执行会话定向套件首次 108 项中 19 失败、26 错误；最后一次“历史无项目父任务派生子任务拒绝”改动后未复跑；自报曾误写主工作树文档后撤销，协调者核对主工作树 tracked 差异为空。协调者未自行跑测试，只读 diff 后整理 10 项疑问（project_id strip、群过滤空串、文件授权矩阵、SDK breaking、新测试未跟踪、19/26 失败名单、web 空 project、误写细节、迁移已数据验证、部署计划），与固定复核清单一并派 **459 k2.8 复核**。

> 2026-11-06 10:20（DeepSeek，**补充流程：疑问与固定复核项一并交复核**）：用户补充——协调者核对交付与预期差异后，把**发现的疑问、需要核实的内容与固定复核清单一并**交给独立复核角色；复核结论回来后协调者决策，确认缺陷交开发返修。已写入 `AGENTS.md`「协调者不重复开发自测」。W1（458）交付后按此执行：我只读交付/差异并整理疑问，与固定复核项一起派 k2.8，不自行跑测试。

> 2026-11-06 10:15（DeepSeek，**流程调整：协调者不参与开发执行/自测**）：用户明确——开发角色必须自测，协调者**不重复测试**，只核对交付/证据并判断；有疑问交复核（k2.8），确认不对交开发（Terra）修复；“简单说协调者不参与执行动作，只决策”。已写入 `AGENTS.md` 新小节「协调者不重复开发自测」：协调者保留范围、授权、收取、进度/文档与 Git 收尾等协调动作，但不重复运行开发测试、不在候选上执行开发动作。W1（458）交付后按此执行：只读核对交付/差异与 k2.8 结论，不自行跑测试。

> 2026-11-06 10:05（DeepSeek，**无项目历史清理完成；W1 已派 458**）：按用户“历史无项目数据全部清除 + prj_accept 一并删除”的确认，先备份 `backups/workspace-w1-backup-20261106.db`（11.48MB），再删除 `test-run20`（23 消息）与 `prj_accept`/`group:accept-bs`（15 消息，0 任务/0 角色）。清理后：projects 仅 `prj_e8fe7066bbec`；tasks 457（0 无项目）、groups 458（0 无项目）、messages 2411、files 0、schedules 0；`/healthz` 200。W1（458）已派 Terra：根任务/群/日程/文件强制 project_id，File 增加 project_id 并按项目授权，迁移补列，补测试；不改前端切换与角色运行时。

> 2026-11-06 09:55（DeepSeek，**B 部署验证通过；工作区模型改为“终端决定”**）：w-d 内置服务启动 gen5/`ins_2ffa80acc329`，任务 457 20s 返回 `WD_B_OK`、结构化 complete，已收取并停止（gen6），确认新 bridge 已加载；硬截止/repair 的真实慢流仍未在真实模型上压测（单测覆盖）。用户明确工作区模型：TALK 不自己定义工作区，工作区跟随发起任务的 Agent 终端（目录/`.talk/project.yaml`）；不提供页面创建工作区；已加入工作区仍可下拉切换；同时只激活一个视图；切换不得停止 A 工作区在跑的任务；登录恢复上次工作区；历史无项目数据全部清除；未来所有文件/任务/群必须带项目。`prj_e8fe7066bbec` 是 TALK 目录（`D:\claude-test\TALK`）的项目记录，保留；`prj_accept` 为测试项目待确认清理。只读盘点：无项目群仅 `test-run20`（23 消息），无项目任务/日程/文件均为 0。拟按 W1 数据边界→W2 前端切换→W3 角色运行时→W4 验收推进。


> 2026-11-06 01:25（DeepSeek，**B 完成并推送；454 设计已交付；等待用户决策**）：456 k2.8 复验 **approved**：fallback 在首轮 end_turn 后立即登记、deadline 三条件归类正确、窗口测试 10/10、4 滴流用例 30 批 0 失败、155 项 OK/44.8s、diff blob 一致、文档口径一致。fix3 已集成到主工作树，独立重跑 155 项 OK/45.1s、diff-check 干净，提交 `87d0014` 并推送 `origin/codex/terminal-return-codex`。447/448/452/455/453/456 已收取；449/451 failed 不可收取。C 已完成；454 设计（含 8 个待决问题）已交付并收取。下一步等用户确认工作区隔离的决策与顺序；B 的真实桌面部署验证需用户授权。


> 2026-11-06 01:12（DeepSeek，**455 fix3 交付；456 k2.8 定向复验**）：455 按 453 两条 finding 修复：首轮 `end_turn` 后立即登记 `repair_fallback`（任何后续 deadline 返回首轮→partial）、repair 异常按 deadline/timeout 归类（不再误报 `repair=failed`）、测试预算 2.2s。自测 155 项 OK/41.4s、4 个滴流用例 80 次全过；候选 7 文件 blob `f513821c…`。协调者已独立重跑 155 项 OK/41.4s、diff-check 干净。456 已派 k2.8 定向复验（重点：窗口测试是否真卡住、20 次独立循环、152+ 回归、范围/文档）。通过后集成 fix3 → 全量相关测试 → 提交/推送 B+C。

> 2026-11-06 01:10（DeepSeek，**454 工作区隔离设计完成；455 fix3 预检中**）：454 交付 `DESIGN.md`：现状核查 20 项能力（project_root_path 已存在但无规范化/唯一性/可访问性检查；任务 project_id 可空且部分列表不强制过滤；群 human 列表不按项目过滤、无项目历史群共享；日程无 project 字段、物化 project_id=None；文件无 project_id、blob 共享；Key 路径未按 project 分层；实例 project_id 可空；启动无选择工作区入口；本机 runtime 根受限于 TALK 代码根）。给出 4 个建议切片（登记兼容→数据/任务边界→角色运行时按工作区→加载切换验收）与 8 个待用户决定问题（project 复用/启动选几个/切换停不停旧服务/共享历史身份与文件/默认项目迁移/目录重关联/登录复用/目录选择入口）。该设计不等同开工授权。


> 2026-11-06 01:05（DeepSeek，**453 changes_requested；455 fix3 已派**）：k2.8 复核 fix2 判 changes_requested：主目标（`has_valid_delivery` 与 cli_bridge 候选扫描逐字一致、内嵌 JSON 不误触发 repair）通过，152 项 OK；但 repair 滴流超时双裁判竞态独立复现 6/44：①worker 吞截止异常导致 `repair=failed` 误标签；②首轮已返回但 fallback 未登记窗口抛 timeout→blocked。已从 fix2 补丁重建 fix3 候选（`.tmp/wb-delivery-repair-fix3-20261106`，7 文件，blob `5a168fda`），派 Terra 455：fallback 提前登记、deadline 异常权威标记、放宽测试预算并 20 次循环；455 排在 454 之后。复核材料在 `.tmp/wb-delivery-repair-review-fix2-20261106/k28/`。


> 2026-11-06 00:47（DeepSeek，**454 工作区隔离只读设计已派 Terra**）：按用户睡前指示，先完成 B 的复核/集成/提交，再推进“跨项目工作区隔离”。已派 Terra 454 做只读现状核查与分片方案（唯一可写 `.tmp/workspace-isolation-20261106/DESIGN.md`，不改产品代码/不启停服务）：核查当前 project/目录模型、角色/任务/Hall 隔离、前端下拉与全页面切换、启动流程，输出建议切片与**待用户决定问题**。该设计不等同开工授权；实现片等用户明天确认。C 已完成，B 待 453。


> 2026-11-06 00:45（DeepSeek，**修正检查点判定：451 不是确认卡死，终止过早**）：451 在 00:07 写 `unittest.log`、00:12 导出 diff、00:19 写探针并跑完 11 项、00:24:28 写 `REVIEW.md`；20 分钟检查点（00:22:52）时它仍有产出，我在 00:25:58 仅凭一次 15 秒零增长采样就终止了它，距 `REVIEW.md` 只有 90 秒，**证据不足**。449 才是确认卡死（约 95 分钟零 CPU/内存）。规则已收紧：零活动必须**持续 ≥10–15 分钟**且无新输出/产物才可终止；刚有产出时一律先重启等待。451 的 `REVIEW.md` 虽判 approved 但漏测内嵌 JSON 边界，已由 fix2 覆盖，不影响 B 的最终路径；hy4 稳定性仍待单独核查。

> 2026-11-06 00:30（DeepSeek，**hy4 复核发现内嵌 JSON 真缺陷；451 再次卡死；452 fix2 返修**）：449 的复核产物给出 changes_requested：Finding 1 指出 shim 的 validator 用整段 `parse_delivery_report`，而 cli_bridge 会补读内嵌 JSON；首轮“前言+合法 JSON+后记”会触发多余 repair，repair 超时返回首轮后仍被 normalize 判 complete，违反“repair 超时→partial”。我已直接复现（`parse=unstructured`、`normalize=complete`），确认有效。451 重派又卡死（写 `REVIEW.md` 后无交付），终止为 failed/blocked（3229）；其 approved 漏测该边界，不采纳为最终结论。**452 fix2 已派 Terra**：让 validator 与 cli_bridge 补读口径一致（首轮已含合法交付则不 repair），修复 Finding 1/2 并补测试；候选 fix2（7 文件，blob `a0fddd22`）。1 小时检查点等待，之后 **k2.8** 独立复核（hy4 稳定性后续单独查）。






> 2026-11-06 00:15（DeepSeek，**主动等待改为 1 小时检查点**）：用户指出 24 小时总预算对“卡死”场景不合适。现规则：后台等待 job 默认 `--timeout 3600`；到时未终态**不是任务失败**，发起者醒来核对任务状态与执行进程实际活动（CPU 时间/工作集增量、TCP 连接与输出增长；心跳只续租约、不算产出）。有活动但未完成→重启 job 再等 1 小时；长时间零活动（CPU/内存均不增长、连接空转）→按最小范围终止卡住进程，任务记 failed/blocked，报告用户定夺，不自动重派。单次 job 的 timeout 不设任务总时限。`scripts/talk_wait_task.py` 默认 86400→3600，AGENTS/TERMINAL_MCP 同步，24 项测试通过。

> 2026-11-05 21:55（DeepSeek，**447 partial→448 返修；等待预算改 24 小时；旧 worktree/分支已删除**）：447 核心实现完成（147 项通过），但 Terra 如实报 partial：`--timeout` 硬截止只按每行/单次 read 检查，SSE 零星滴流时无法保证总时长；已冻结并重建 fix1 候选（447 补丁 SHA256 记录），派 448 要求 daemon/watchdog 硬截止 + T1/T2 超时测试。另修主动等待预算：`scripts/talk_wait_task.py` 默认 `1800`→`86400` 秒（原 30 分钟上限是我沿用了文档示例、并非用户要求，长任务会被误杀），`AGENTS.md`/`TERMINAL_MCP.md` 同步为“不得短于任务执行预算”；`tests.test_talk_wait_task` 24 项通过。旧 worktree `C:\Users\Administrator\.codex\worktrees\kimi-role-host-fix\TALK` 与本地分支已删除，tag/补丁保留，远端分支未动。

> 2026-11-05 21:05（DeepSeek，**四项用户验收通过；428 已收取；主动模式启动缺口记录**）：用户确认四项验收通过；428 已正常收取。发现 444 派发后未启动后台等待 job：`initiator_wait` 只是按项目模式生成的**建议/命令模板**（代码注释明确“不启动进程”），真正的轮询由 `scripts/talk_wait_task` 完成，但**启动动作仍在发起 Agent 侧**，没有程序级强制；444 因此未收到完成通知，后已补收取。**用户 2026-11-05 决定暂不修（无伤大雅）**；如需再议，建议在 DSH harness 层按 `initiator_wait.action=start_background_wait` 自动启动等待 job，或由 tool 层提供等价自动等待。

> 2026-11-05 20:50（DeepSeek，**四项部署验证完成：版本/强度生效，446 结构化 complete**）：API 已重载，`/api/runners/versions` WorkBuddy `2.165.0/match`；`w-d 内置` 绑定 `effort_options=["low","high","max"]`/`source=adapter`；角色服务 generation 3、新实例 `ins_791ecfec0869` running。445 文件 16 字节正确但模型 JSON 在 changed_files 截断，bridge 诚实降级 partial；446 极简任务输出合法 JSON，Task Hall `complete`，文件 17 字节正确。代码 `fb35f2e` 已推送；验证文档随后推送。用户刷新页面即可看到强度下拉与版本面板；稳定 complete 需另开“格式修复回合”。

> 2026-11-05 20:45（DeepSeek，**四项全部完成开发与复核，待推送/部署验证**）：⑥思考强度 436/438（K2.8 定向复验 PASS，52 Python+29 Node，真实探测 deepseek/glm=low/high/max、hy4=high）、⑦CLI 版本 440/441（9 项，真实 CLI 2.165.0）、⑧结构化交付 443（126 项，K2.8 PASS）均已集成。443 任务正文误写 schema/整数 task_id，实际校验器要求无 schema、字符串 task_id；Terra 按实际校验器实现，共享 schema 未改。当前主工作树 `e38686e`，远端 `abf7e4d`，未推送；部署需重载 API（强度/版本）并重启 `w-d 内置` 角色（结构化 bridge），待用户授权后执行真机验证。

> 2026-11-05 20:05（DeepSeek，**WorkBuddy CLI 版本探针完成开发与复核，待 API 重载**）：Terra 440/441 为 `server/runner_versions.py` 增加 WorkBuddy 专用探针（只查 exe 与 `app.asar` 两个真实文件，asar 内 entry 只作参数；临时 config 隔离；5s 超时；错误 fail-closed），适配基线 `2.165.0`；9 项测试通过，K2.8 独立复核 PASS 并用 pwsh 确认 CLI `2.165.0`/exit 0。Python 探针在角色 HOME/DSH 沙箱中因 LOCALAPPDATA 隔离或 PermissionError 返回未知，属环境限制；生产 API 重载后复验页面。集成提交 `1d1e4cb`；下一步仅剩第 4 项结构化任务交付，然后统一推送。

> 2026-11-05 19:45（DeepSeek，**思考强度完成开发与复核，待 API 重载**）：Terra 436 实现按模型 ACP 强度探测、缓存、绑定读取/PUT 校验与前端“跟随模型默认”；K2.8 首轮唯一 NEEDS_CHANGES 是全局锁内 60s 网络探测阻塞并发请求，Terra 438 改为网络探测出全局锁 + 按模型 Event single-flight，K2.8 定向复验 PASS。52 Python + 29 Node 通过；真实探测 deepseek/glm=`low/high/max`、hy4=`high`；两轮复核报告均为 invalid 格式，按原文证据核过。集成提交 `43de6f4`；**运行页面需重载 API 后才生效**，本片未推送。下一步：第 3 项版本探针、第 4 项结构化交付。

> 2026-11-05 17:30（DeepSeek，**WorkBuddy 内置模型切片用户验收通过并推送**）：用户确认验收通过。真实角色 **w-d 内置**（`agent:prj-e8fe7066bbec.w-d-8d8e1bdb`）消息 3211→3212 `OK`（约 10s）；任务 435 领取 17:25:27、完成 17:25:55，写入 `D:\claude-test\TALK\.tmp\wb-acp-user-check\check.txt` 11 字节 `USER_ACP_OK`（hex `55 53 45 52 5F 41 43 50 5F 4F 4B`，无 BOM/换行），未改其它文件。任务结果为自由文本、非 `talk-delivery-1`，Task Hall 结论显示 unknown；结构化交付另开小片。代码 `1564191`、文档 `ec84ff4` 及本轮验收文档提交已推送 `codex/terminal-return-codex`。


> 2026-11-05 15:35（DeepSeek，**运行器版本提示已验收并推送；下一片=WorkBuddy 内置模型接入**）：用户人工验收通过（项目设置内面板位置/四条运行器/去掉多余分隔线），`3f6668c..17701d5` 已推送（含两个排查记录）。下一片按用户要求登记为 **WorkBuddy 内置（免自备 API Key）模型接入**；已知障碍：TALK 的 WorkBuddy 适配只接受 `custom-local:<id>`（`models.json` 自定义 API），嵌入 CLI 独立配置目录未登录 WorkBuddy 账号，`--help` 模型列表无桌面 UI 的 DeepSeek-V4.1-Flash，实调用返回 `Authentication required. Please use /login`；桌面登录态在桌面配置目录、按隔离规则不能复制。因此该片先做**只读可行性与设计**（官方登录流程在角色独立 HOME 的可行性、登录后模型列表、适配器改动范围），确认可行再实现。

> 2026-11-05 11:20（DeepSeek，**运行器版本提示：426/428/430 完成，K2.8 复核 PASS**）：在 425 基础上补齐——①426：接口固定返回 codex/kimi-code/dsh/workbuddy 四运行器（注册表无行也用默认名，额外 runtime 追加），首页 HTML 加 `Cache-Control: no-cache`；②428：版本块从侧栏移入项目设置详情页，位于「调度模式」与「角色配置宿主」之间，沿用相邻面板 kicker+h3+分隔线，样式改 CSS 类/主题变量、无内联颜色；③430：修复“从任务/群聊点角色页时面板不显示”的可见性回归（`renderWorkspaceList` 入口补同步，10 分钟缓存不重复请求）。K2.8 独立复核首轮 NEEDS_CHANGES（正是①的可见性问题），Terra 返修后定向复验 **PASS**；Python 40 项、Node 42 项通过，全量 Node 393 项仍 16 个基线失败逐名一致。**待你普通刷新验收**：角色页→项目设置，应在调度模式与角色配置宿主之间看到“运行器版本”面板；当前三个 CLI 均与适配基线一致（WorkBuddy 显示未知）。已知限制：真实浏览器未自动化；WorkBuddy 无 CLI 探针。提交随后推送（含 2 个排查记录）。

> 2026-11-04 23:55（DeepSeek，**运行器版本提示：已完成开发与复核，待页面刷新验收**）：新增 `server/runner_versions.py`（适配基线 codex 0.164.0 / kimi-code 2.0.2 / dsh 0.2.1-rc.5，探测本机 `--version`、3 秒超时、10 分钟缓存、失败归一 unknown）与只读 `GET /api/runners/versions`（按 `runner_registry` 去重，不动现有 PATCH）；角色页项目条下新增只读“运行器版本”行，一致时显示“已适配 X”，不一致时才提示“检测到 Y（有新版本/旧于适配），仅提示，不会自动更新”。Terra 开发 425；DeepSeek 复核：路由顺序无冲突、真实探针三路均 match（WorkBuddy 无探针→unknown）、新 Python 5 项 + 新 Node 4 项 + controller 33 项通过、全量 Node 393 项 16 失败与基线逐名一致。**集成时修了一处白名单外断言**：`tests/workspace_initiator_mode_ui.test.cjs` 的 workspace.js 缓存版断言改为 `20261104-runner-versions-v1`（否则新增 1 个失败）。已知限制：WorkBuddy 显示未知；提示行用内联颜色、深色主题下为固定橙色；未做真实浏览器验证（待刷新）。提交随后推送（含 2 个排查记录提交）。

> 2026-11-04 22:55（DeepSeek，**排查更新：Terra 延迟不在配置/MCP，指向模型回合本身**）：经用户允许只读 Terra native `.codex/config.toml`——**没有 `mcp_servers` 段**（仅 model/provider/effort=low/projects/cli_auth 存储方式），MCP 启动超时假设排除；`codex.exe --version/--help/exec --help` 实测 52–109ms，进程启动不是原因。结合同小时对照（小G gpt-6.1-sol 14s vs Terra gpt-6.1-terra 121s，同为 Codex 角色、同一 preflight 代码路径），现在最可能是 **gpt-6.1-terra 的单次模型回合约 120 秒**（预检 1 回合 + 执行 1 回合；两次冒烟 150–156s 也吻合），且 121–127s 的极窄离散更像“120 秒超时后重试成功”（Codex 侧），而非普通模型延迟。**尚未证实**：需 1 次计时探针（Terra HOME + 该模型，trivial exec）与/或查看 Codex 自身日志中的 120s 重试记录（私有运行数据，需再授权）。TALK 主代码不是原因；若确认，修复方向是换模型/调整 Codex 超时或接受每回合约 2 分钟。

> 2026-11-04 22:20（DeepSeek，**排查：Terra 固定约 122 秒领取延迟**）：已定位到**领取前预检**（`talk_wait_task` 无关；`run_task_queue_worker` 每 2 秒发现任务，`handle_queued_task` 先跑 `_prepare_task_before_claim` 的 Codex preflight，成功后才有 `claimed_at`）。数据（278 条任务的时间戳只读分析）：Terra（codex）n=31，近 8 次 121–127s、中位 122s；**同小时的小G（agent:codex，同为 codex）14s**；Kimi 8–9s、WorkBuddy 17s、DSH 角色 12–33s → 不是排队轮询、不是共享桥接、不是思考强度（小G xhigh 仍 14s），而是 **Terra 自身原生 Codex 环境**。Terra 的延迟自 2026-11-01 14:08（#388）起稳定出现；两次只读冒烟任务总耗时 150–156s 也符合“每次 `codex exec` 多约 120s”的固定开销。**最可能**：Terra 原生配置里的 MCP server 启动/握手超时（或等价固定等待）拖慢每次 CLI 调用；**尚未证实**（未读私有 native 配置）。确认方式（需你授权，二选一）：只读查看 Terra `~/.codex/config.toml` 的 `[mcp_servers]` 段；或用同一 native HOME 跑一次带 `mcp_servers={}` 覆盖的计时探针。确认后修复应是一小片（清理/修正该条配置）。本轮未改代码、未启停。

> 2026-11-04 22:05（DeepSeek，**等待工具识别“待澄清/需人工决策”已集成**）：`scripts/talk_wait_task.py` 新增 attention 退出——`clarification_requested`/`needs_decision` 时立即退出，输出 `TALK_TASK_ATTENTION … reason=<clarification|decision>`，**退出码 3**；`--json` 增加 `outcome`（done/attention/timeout/error）与 `reason`；终态/超时/错误行为不变。重复确认后接受一处**有意的行为变更**：argparse 用法错误由基线 2 改为 64（与脚本文档约定一致），Key/运行错误仍为 2；`TERMINAL_MCP.md` 与 `AGENTS.md` 已同步（attention 不是完成，应读问题→同任务答复→重起 job，不新建任务）。Terra 开发 424（交付 partial，主动如实上报退出码冲突），DeepSeek 复核并裁定：`tests.test_talk_wait_task` **23 项通过**；真实终态任务 424 实跑 `TALK_TASK_DONE … elapsed=0s`、exit 0。未验证：真实澄清任务触发 attention（只有单测合成状态）；真实后台通知/Hall 答复链路。提交随后推送。

> 2026-11-04 21:25（DeepSeek，**任务窗口只读展示交办内容：已完成并验收通过**）：任务 Hall 默认只读，顶部“任务交办内容”默认折叠为一行（标题/状态/展开），展开后显示正文与发起者/执行者/创建时间（正文区 `max-height:60vh` 内部滚动，无 sticky/fixed）；仅 `clarification_requested`/`needs_decision` 时开放输入。Terra 开发 421，DeepSeek 复核（候选仅 4 个白名单文件；三条 Node 套件 38 项通过；全量 393 项 377 通过、16 项既有失败与基线逐名一致）；用户实测后经 422（修 sticky 遮挡）与 423（改折叠形态，展开状态跨 5 秒轮询保持）两次集中返修；用户 21:22 确认验收通过。提交 `3dee4ce`→`d46b761`→`29842ea`（已集成，随后推送）。未做：真实浏览器自动化（人工验收代替）；输入区仍是“禁用可见”而非隐藏，“展开”按钮用浏览器默认样式。

> 2026-11-04 19:25（DeepSeek，**调度模式两态实机验收通过**）：主动态（v9）派发 419 后按规则启动后台 job，输出 `TALK_TASK_DONE task=419 status=succeeded workflow=submitted result=3195 elapsed=270s`（退出码 0），全程零模型轮询、由通知唤醒后取件（Terra 预检约 2 分钟：18:54:35 派发→18:56:38 领取→18:59:14 完成）。被动态（v10）派发 420 时**未启动任何等待 job**（19:17:07 派发→19:19:10 领取→19:21:40 完成），交付 3196 为完整 `talk-delivery-1`（complete、task_id 一致、verification pass、changed_files 空），已收取。419 的结果消息被截断为 78 字符（invalid），按已处理收取；420 未复现，暂按偶发观察。仍未验证：本会话 MCP 仍是旧代码，`initiator_wait` 回显需重连/重启后才可见；页面新文案需刷新浏览器。

> 2026-11-04 18:00（DeepSeek，**调度模式接通程序轮询；待真实两态验收**）：`active`=发起者派发后后台轮询、就绪时通知取件；`passive`=派发后结束、等操作人通知。`talk_delegate_task` 成功响应新增只读 `initiator_wait`（`saved_mode/action/command/requires_completion_notification`；active→`start_background_wait`+命令模板，passive→`end_turn`，读不到→`unknown`），在派发瞬间按项目模式求值、复用同一次项目 GET；`controller_mode` note、工具描述、页面副标/hint/两态说明/“实际执行”行/保存提示全部改为新语义（workspace.js 缓存版本 `20261104-initiator-wait-v1`）；`AGENTS.md` 等待规则改为按模式执行，主动但终端无通知能力时回落被动。验证：Python **153 项**（controller_mode 33、requirements 21、task_tools 21、followup 32、stdio 6、controlled_wait 37、role_creation_web_ui 3）+ Node **35 项**通过。**未验证**：新桥接代码要 MCP 重连/重启后才在真实会话生效；真实“主动自动起 job / 被动不起”两态待用户切一次模式实测；`test_controller_web_ui` 仍有 2 项**基线既有**失败（STATIC_VERSION 常量过期，与本片无关）。

> 2026-11-04 17:25（DeepSeek，**用户取消“主被动跟进完整接入与验证”，仅记录决策**）：理由是等待交付的需求已由当天的“程序轮询 + 完成通知”覆盖（后台 job 零模型轮询、终态通知后取件），不再需要主动链路。路线图第 7 项作废。**存量保持不动**：项目调度模式设置（仅意向、不会自动生效）、`talk_follow_tasks`、`controlled_wait` 等代码/工具保留，不再继续逐宿主验证等待预算/取消/并发，也不删除、不改页面；默认仍是“被动派发 + 程序轮询 + 完成通知”。`AGENTS.md`「发起者主被动与等待」补记该取消。本轮未改产品代码、未启停、未派发。

> 2026-11-04 17:10（DeepSeek，**用户取消“任务列表按真实对话窗口展示”，仅记录决策**）：原定继 90% 换窗之后做的“任务列表按真实对话窗口展示”（同窗多轮聚合、缓存命中率、窗口执行中状态）**整体取消**——窗口继续按任务维度保持原样，每任务一个 Task Hall，不改代码、不改页面。相关联的“任务窗口展示交办内容并去掉输入框”一条**保留**待后续确认（用户明确不一起取消），但不再依赖窗口聚合。路线图第 5 项作废、2026-11-03 近期顺序补记终止、文末 2026-10-27 登记加取消注记；使用说明补记该展示不再视为待补项。本轮未改产品代码、未启停、未派发。

> 2026-11-04 00:35（DeepSeek，**长等待改为“程序轮询 + 完成通知”**）：新增 `scripts/talk_wait_task.py`（只读 `GET /api/tasks/{id}`、Key 只从文件/环境读、进入终态即退出）与 `tests/test_talk_wait_task.py`（19 项通过）。`AGENTS.md`「发起者主被动与等待」与 `docs/guides/TERMINAL_MCP.md` 已加入规则、命令模板、退出码和预算，明确只在 DSH 验证、Codex/Kimi/WorkBuddy 未适配不外推。**默认策略同步改为**：派发后若终端具备后台通知或类似机制则自动等待，没有类似机制则保持被动、由操作人告知结果；人工验收里程碑与“不用跟”除外。真实验收：任务 418 由后台 job 等待 240 秒后**自动唤醒本会话**（无轮询回合），任务 417 同机制等待 231 秒；`toolCallTimeoutMs` 保持 65000，只用于普通 MCP 调用。未验证：会话关闭后通知丢失、其它终端。

> 2026-11-03 22:32（DeepSeek，**会话窗口换新 90% 已完成并验证**）：换窗阈值由 70% 改为 90%（原始整数 `used*10 >= capacity*9`，89.9% 续、90% 及以上下一次投递前新窗）；取消缺数 10/11 次备用——取不到可靠占比一律 `new_context_unknown` 新窗；不判断失效时间。旧 60%/70% 观测与旧计数状态保留只读兼容，`exact_comparison` 改为 `capacity_times_9`。Terra 按 413–416 开发（413 因候选目录缺失 blocked、414/415 partial、416 complete，均已按已处理收取），DeepSeek 独立复核实际 diff、独立探针（89.9 续 / 90、90.1 换 / 缺数新窗 / 旧观测可读）与整组测试：Python 323 项 OK（六套会话测试 + 任务 API），Node 采集 35 项通过。k2.8 启动加载新内核（generation 33 ready）后已正常停止回 generation 34。真实 90% 高占用与生产 API 重载未验证。提交 `8992e7f`。

> 2026-11-03 21:30（DeepSeek，用户决策、尚未开工）：近期顺序调整为 ①**会话窗口换新**——换窗阈值改为上下文占比 **90%**，**不判断失效时间、只看占比**；②**任务列表按真实对话窗口展示**（大工程）；跨项目角色创建/工作区隔离**整体后移**至基础功能完成后，其它待办等这两项完成后再议。本轮只记录决策、同步路线图并给出拆片建议，未改代码、未启停、未派发。

> 2026-11-03 15:20（DeepSeek，**DSH 多角色验收通过并推送**）：DSH 动态宿主/创建流程已完成本机验收。新建 managed 角色大D（`agent:prj-e8fe7066bbec.d-fec6cc7c`）和二D（`agent:prj-e8fe7066bbec.d-d2a55cb3`）均成功启动为 serving，smoke 任务 411/412 通过（只读 `git rev-parse --short HEAD` 退出码 0）；随后两个测试角色已删除，`dsh-dynamic` per-member 目录和独立 native 目录清理，小D 保持 serving/idle。跨项目角色创建与工作区隔离（所有运行器）已写入 [DEVELOPMENT_ROADMAP.md](spec/DEVELOPMENT_ROADMAP.md)。本地实现提交 `d2efa4a`/`4d60cb8`/`67bb011`/`1e60f40`，验收/路线记录 `4355874`；DSH 23 项测试通过。没有推送前状态保留在历史；本次按用户验收通过提交并推送 `codex/terminal-return-codex`。
>
> 2026-11-03 15:25（DeepSeek，当前角色：后端/开发与复核）：`AGENTS.md` 已补“派发颗粒度与执行输入”并精简上下文/额度三条为一条，提交 `3ddc7dc`（纯文档，未单独推送；远端仍为 `7b4dd78`）。下一片是跨项目/工作区落地：每项目独立角色配置、各运行器原生准备（DSH model patch、Codex/Kimi/WorkBuddy 登录/配置）、工作区切换与关闭清理；首个 Codex tools 任务的沙箱预热/超时仍后置。

> 2026-10-29 本轮更新：小K宿主凭据路径已被后续操作统一，既有恢复于20:30成功；下方19:25停止/路径分歧为历史快照。本轮修正页面定时器 Illegal invocation 导致等待不更新，104项测试通过；新请求真实页面验收待恢复浏览器确认框。见 [修复记录](spec/BINDING_RESET_TIMER_FIX_20261029.md)。
> 2026-10-29 晚补充（DeepSeek）：B1 后端**已闭环**——补上作业侧预期绑定指纹的补录回落（B1-d，`3a8091b`）后，20:30/20:44/20:45 三次恢复全部 `provisioned`，作业 `legacy-kimi-k3-20261017` 推进为 `succeeded`（`profile/key_file=skipped`、`preflight=succeeded`、revision 6），`credential_version` 保持 2，无多余轮换；用户确认小K 可正常启动与关闭。页面定时器修复与本文档其余改动由 GPT 完成、DeepSeek 代为提交。第 3 项仅剩 **3d 删除后资源清理提示闭环**。
> 2026-10-29 21:30（DeepSeek）：**3d 已完成**。删除被接受后角色立即离开列表；清理失败时角色回到列表（行内“删除未完成”），原因显示在详情“删除角色”按钮下方；删除独立清理面板与“重试清理”；再点删除即重试。旧大K 的失败行已由用户点重试清掉（`complete`，21:05）。版本 `20261029-role-delete-inline-v1`；全量 354 项 Node / 338 通过（16 项既有失败）。路线图第 3 项已全部完成，**可推送**，等用户确认；真实浏览器人验待。
> 2026-10-29 21:55（DeepSeek）：WorkBuddy 删除**已完成**（五步全 complete、roster 与 service 行删除、native 目录移除，21:48），3d 实机验收通过。大K 按用户授权执行 `recover-stopped`（generation 3→4，服务重置 stopped、旧宿主归属解除、实例置离线），宿主恢复 serving，启动/关闭/绑定重置可用。另修：同一成员已有更晚成功请求时，更早的失败请求不再弹“未完成”并清出本地跟踪（小K 刷新反复提示的根因，版本 `20261029-role-stale-request-v1`）；同时补正 3d 改版后的资源版本断言（3d 提交时全量跑在版本号更新前，遗留两处未覆盖）。
> 2026-10-29 22:45（DeepSeek）：外观模式完成。顶部左侧项目下拉框右边新增“自动/白天/夜间”三段控件：自动按 08:00–18:00 白天、其余夜间，跨边界与回到页面时自动重算；手动选择记在本机。四个样式文件 256 处颜色字面量收敛为语义变量，夜间整体换色（背景/面板/文字/边框/按钮/强调），首屏内联脚本避免闪白。版本 `20261029-theme-day-night-v1`；Node 全量 360 项 / 344 通过（16 项既有失败与基线一致），theme_mode 5 项通过；夜间实机四视图亮背景残留检测为 0。
> 2026-10-30 00:30（DeepSeek）：DSH 强度启动回填与 reload 卡死修复。新增仅 human 的 `POST /roles/{m}/binding/default-effort`（只改强度、不建不解绑定，未知值 422/无绑定 404）；强度枚举收敛到 `DEFAULT_EFFORT_VALUES` 共用；runtime 启动时读取 DSH 角色 `native/<member>/model-*.patch.yml` 的 `reasoningEffort` 回填一次。另修 `reload-api`：宿主长期保持 WebSocket 会让 uvicorn 优雅关闭一直等，导致旧 API 不退、reload 标记无限重试；现超时后终止旧子进程再启动。今晚因此发生一次 API 中断，靠重启 runtime 恢复；教训记入本文件。
> 2026-11-01 00:10（大K，进度汇总）：当前 `/healthz` 200（db/storage ok）。动态恢复修复 `48be9d4` 已上线，六套170项全过，大K/小D运行、其余角色启停验证后恢复关闭。351-A–F已形成 `6efe0ff`/`b1c3323`/`bc148ff`/`583ebc6` 四个实现与补测提交，各片提交记录均有授权加载与测试证据，任务351仍为 `succeeded/submitted`，待复核确认与收取；352提交 `4de489c`，任务已完成，Node 391项中375通过、16项既有失败不变，静态页面3项通过。当前分支领先远程6个本地提交，均未推送。本会话负责上线核验与进度收尾，不冒称351已复核。
> 2026-10-31 15:25（大K）：364/365动态角色恢复修复已完成独立补验并上线。六套170项全过；四产品文件与365冻结哈希一致，正常停启后七宿主serving。大K冷恢复为已关闭后重新启动至gen9/`ins_770346c0363b`，ready且同实例心跳推进；小D恢复运行，其余五角色逐一启停验证后保持关闭。未改DB/配置/绑定/Key/自启动偏好，286保持，未派任务或调用模型。既有内存泄漏未修，本次重启仅为临时缓解。
> 2026-11-01 00:40（DeepSeek，**P0 已修复，待 4–6 小时观察**）：按 Codex 复核意见完成内存泄漏修复（`scripts/role_provision.py` / `role_service_host.py` / `talk_runtime.py`）：DLL、函数原型、Structure 类改为进程内只建一次（role_provision 用惰性单例，保留 `ctypes.WinDLL` 可替换性），SID/字符串 `LocalFree` 覆盖成功、中途失败与提前返回三条路径。实测 `_publish_private_bytes` **55.5 KB/次 → 0.000 KB/次**（预热 200 次后连续 3×1000 次），`process_parents` 7.5 KB/次 → 0.00 KB/次；346 项相关测试全绿，另 137 项关联测试中 2 项失败，经 `git stash` 还原基线复现为既有环境问题。**尚未重启生产**，4–6 小时进程级观察待做。详见 [诊断文档](spec/MEMORY_LEAK_DIAGNOSIS_20261031.md)。
> 2026-10-31 13:45（DeepSeek，**诊断，已由 2026-11-01 修复**）：定位到一个可复现、量级足以造成严重内存压力的 TALK 泄漏（不在网页/API）——`talk_runtime` + 6 个角色宿主共用的「私有权限文件发布」路径，实测合计约 **27 MB/分钟 ≈ 1.6 GB/小时**（runtime 8.9、每个宿主 3.1），09:07 启动到 13:39 已占约 7.6 GB 私有提交，8 GB 机器又到临界（空闲物理 165 MB）。`talk_api` 本身平稳（113–125 MB），事故中是受害者。是否为 03:00 那次整机耗尽的首发原因无法证明，口径见文档 §6.0；当时建议先重启兜底。
> 2026-11-01 18:00（DeepSeek，**Codex 复核执行能力已补正**）：小G 原 `blocked by policy` 的根因是 Codex 0.164 在 Windows 默认关闭沙箱后端。任务模式已改为 cwd=项目根 + `workspace-write` + `windows.sandbox="elevated"` + 仓库外 TEMP 的 `--add-dir`，可写整仓并自己跑测试。实测完整 346 项 `Ran 346 tests in 296.940s / OK`（skipped=2），33 项 12.861s OK，仓库根写文件成功。常驻 worktree 方案已放弃（干净 worktree/TEMP 在仓库内会触发 `key_root_inside_repo`，346 出现 23 failures + 2 errors，worktree 已 purge）。旧 `.codex/config.toml` 对 0.164 报 `invalid transport`，已改名 `.codex/config.toml.stale-20261027`。370 已于 19:28 按用户要求收取并置 completed（保留 blocked 事实）；重派 371 发现 R1、`12c992f` 返修、377 定向复验通过；内存修复 369 已 approved。详见本地记录 `.tmp/diag-codex-20261101/REPO_WRITABLE_20261101.md`。
> 2026-11-01 19:52（DeepSeek，**小G 启动校验已修正**）：`codex_native_config_changed` 的差异只有一项——Codex 0.164 在沙箱修复后把 `[projects.'d:\claude-test\talk'] trust_level="trusted"` 写回 native `config.toml`；遗留入口仍按整份文本与预设比较，故误判。新增 [bridges/codex_native_config.py](../bridges/codex_native_config.py) 做结构化字段校验（忽略空白/注释/顺序，保留 `model`、`cli_auth_credentials_store=file`、项目根信任范围，拒绝未知字段与放宽沙箱值），遗留入口与正式 `codex_role_setup.read_config` 共用；同时修正 `write_config` 的嵌套表序列化。小G 宿主按 drain 标记正常重启为 17568，服务 generation 51/`ins_49e91fecc579`/ready；任务 384 实测 `git status --short` 与 `python -c "print('XIAOG_TASK_OK')"` 均退出 0（交付格式 invalid，仅作执行证据）。定向 48 项测试 OK；`test_codex_role_setup` 的 10 项既有 `ADMINI~1` 路径失败未变。正式宿主与 API 未重启，新校验对新建 Codex 角色下个自然重载生效；完整 workspace-write 开发能力未因此重新验收。
> 2026-11-01 20:53（DeepSeek，**Terra 宿主已重启**）：Terra 原宿主 11184（00:56 启动）按 drain 标记正常退出，runtime 拉起新宿主 17088（20:53:16）并 serving；服务保持 stopped、generation 11、未持有进程。Terra 配置无需修改，新宿主已加载结构化校验；API 4764 仍未重载，新建 Codex 角色需下次自然重载，Terra 自身启动校验在宿主侧已生效。
> 2026-11-01 22:24（DeepSeek，**Codex base_instructions 兼容已修复**）：386/387 的 `unknown configuration field base_instructions` 是正式宿主/桥接生成旧参数，与 `config.toml` 校验无关。`codex_role_host`/`codex_bridge` 三条命令统一改 `developer_instructions`；`codex_execution_native` 的 `-c` 白名单移除 `base_instructions`，旧命令在 TALK 层拒绝。组合回归 83 项 OK。Terra 正常关闭→宿主 18292→启动 generation 16/`ins_71c494b3c6c4` ready；任务 388 预检+执行通过（`TALK_PARAM_OK`），普通消息 3118/3119 返回 `PM_PARAM_OK`/`PM_PATH_OK`；实例 idle、心跳正常。详见 `.tmp/codex-param-fix-20261101/REPORT.md`。
> 2026-11-01 22:27（DeepSeek，**API 已重载**）：旧 API 4764 正常替换为 18248，`/healthz` 200、startup complete、worker 无错；7 个宿主保持 serving，Terra 宿主 18292 未动，服务 generation 16/`ins_71c494b3c6c4` running/ready、实例 idle（心跳 22:27:42）。API 重载只替换 API，不关闭角色宿主；页面刷新后即可线上验收。
> 2026-11-02 00:05（DeepSeek）：**351-G 已完成并加载**。真实接单走 `cli_bridge.run_task_queue_worker`，此前 `codex_bridge.handle_queued_task` 的强度逻辑从未被调用；现注册 `before_task` 钩子，每任务（预检+执行）从 `/agents` 读绑定并从启动模板重写命令（`-c model_reasoning_effort=` / `--effort`）。实测：小G、Terra 启动值 high/xhigh，改 low 后**不重启**即生效（rollout 与命令行双证据），任务 390/391 成功并收取。回归 171 项 + 新增 9 项通过。
> 2026-11-02 00:40（DeepSeek）：**小d 启动门槛已修**。`deepseek_native_patch_changed` 的根因是遗留 DSH 宿主按整份 patch 逐字节比对（基线 `reasoningEffort: max`），而逐任务钩子于 11-01 18:48 按绑定把同一行写成 `low`，此后每次启动都在预检阶段失败（`spawned=0`，未起进程/实例）；页面改回 max 只写 `effort_override`，不回写 patch，故重试仍失败。按用户选择先把 patch 回写 `max` 解锁启动，随后新增 [bridges/dsh_patch.py](../bridges/dsh_patch.py) 做结构化校验（provider/model 必须等于确认值，强度只认 off/low/high/max，注释/顺序/行尾不再阻断），遗留入口改为调用它，错误码保留 `deepseek_native_patch_changed`。新增 11 项测试 + 既有强度回归 23 项 OK；宿主同款系统 Python 实测当前 patch 通过、模拟 `low` 通过、模拟改 model 拒绝。**宿主已重启（15656 → 18084，runtime 状态 serving，00:38:01）**，新门槛已加载；patch 保持 `max`，七个宿主均 serving。
> 2026-11-02 19:40（DeepSeek）：**Kimi 启动门槛与强度对齐已修**。新增 [bridges/kimi_native_config.py](../bridges/kimi_native_config.py)：`config.toml` 只校验 `provider`/`model`（含 providers 声明），`default_effort` 不参与，结构不可读 fail-closed；产品宿主 `scripts/kimi_role_host.py` 与两个遗留入口（小K、Kimi k2.8）共用，遗留入口首次具备启动前置校验（`kimi_role_setup_required`，不再拖到任务期才报错）。另加 `cli_bridge.run_startup_hook` + `kimi_bridge.align_effort_at_startup`：角色启动时按绑定对齐一次强度，消息/首轮不再沿用旧值；对齐失败只留诊断、不阻断启动。验证：Kimi 套件 173 项、`test_cli_bridge` 122 项、`role_host_runtime_configuration` 40 项全过；三份真实配置在纯校验/产品宿主/两个遗留入口四条路径均判通过，改 `default_effort` 通过、改 provider/model 被拒；`test_kimi_talk_entry` 2 项既有失败（tool_count 10≠9）已在基线复现。**宿主侧校验需重启对应 Kimi 宿主才生效；启动对齐在下次角色启动即生效**；未启停生产。详见 [设计说明](spec/KIMI_CONFIG_GATE_STARTUP_EFFORT_20261102.md)。已完成宿主重启：小K 9648→12448、K2.8 14952→7732、k-d4bf0429 19392→3232，均 `serving`，三个角色服务保持 `stopped`、无在管进程；未启停角色服务。随后用 k2.8 做整链实机验证（19:50）：override 改 low → 启动 gen 29/`ins_026db48e7926` ready（约 2s）→ **未跑任务**配置即变 low（启动对齐生效）→ 消息 3130/3131 回复 `K28_STARTUP_OK` → 改回 high → stop/start gen 31 配置回到 high → stop gen 32；最终 stopped、override high、config high，无失败诊断与遗留进程。**2026-11-02 19:58 用户验收通过并推送**：`7d83b6f`（小d）+ `acab0a0`（Kimi）已推送至 `codex/terminal-return-codex`（`68deea1..acab0a0`）。
> 2026-11-02 20:25（本会话）：**动态 Codex/Kimi 角色删除误判已修**。`role_delete` 要求宿主 health 明确 `owned_launches=[]`，但 Codex/Kimi 动态宿主未发布该字段，导致无任务也停在 `manager_not_stopped`；GPT 10-30 的失败行即此原因。两宿主现发布 `list(self._handles)`（与 WorkBuddy 同口径），`role_delete` 严格判据未放宽；新增宿主单测、真实 HTTP 启停断言和“缺字段仍拒绝”回归，定向 **65 项 OK**（另 `test_role_deletion` 38 项 OK）。GPT 删除已重试到 `complete`（revision 6、五步全 complete），档案仅余永久 `.provision.lock.guard`，Key/metadata/roster/service 已移除；遗留 `codex-dynamic` health 先存 `.tmp/role-delete-gpt-20261102/` 再清理。Terra/k-d4 已按 drain 正常重载为新宿主 14148/10044，health 分别 `["0e38a4a7…"]`/`[]`；Terra 服务恢复到 running gen22/`ins_68b8e8da00e0`，k-d4 保持 stopped，其余宿主未动。动态宿主目录仍不在删除清理范围（已删的 k-4bf013b9 有残留），留作后续观察；未推送。
> 2026-11-02 20:55（本会话）：**删除修复完成真机闭环**。小K（`agent:kimi`，imported）页面删除 `complete`：manager/profiles/private_state/startup_config complete、credentials preserved；Key/metadata 保留、native home 移除、宿主 12448 退出、runtime 配置宿主条目移除；遗留 `kimi-next` 空日志目录已清。随后用一次性 Codex 角色“删除验证”（`agent:prj-e8fe7066bbec.role-9fad0c64`，gpt-6.1-sol）复现修复路径：宿主 18248 serving 且 health 明确 `owned_launches:[]`；取消未完成的官方授权（`failed/native_authorization_canceled`，device login 退出）后页面删除，revision 2 五步全 complete（**manager complete，不再 manager_not_stopped**），独占 Key/metadata/native/绑定移除、宿主退出、空 `codex-dynamic` 目录手工清理；其余 6 宿主 serving（Terra running、k-d4 stopped），`/healthz` 200。`k-4bf013b9` 遗留 health 也已存档并清理。动态宿主目录仍不在 `role_delete` 清理清单，属后续观察。小K 的 4 个已跟踪档案删除按用户要求不纳入本次提交。用户已确认删除验证通过，推送 `codex/terminal-return-codex`。
> 2026-11-02 22:55（DeepSeek）：**Codex 角色默认整仓可写（tools）已完成并验证**。`scripts/codex_role_host.py` 的 `host_spec` 与 CLI 默认档从 review 改为 tools；`codex.task_profiles` 只有显式写 review 的成员才只读，当前没有例外。tools 任务命令统一带 `-c windows.sandbox="elevated"`、`--add-dir`（仓库外临时根），review 仍用 `unelevated`；`bridges/codex_execution_native.py` 的 `-c` 白名单允许并在 TALK 层校验这两个受限值。63 项定向测试 OK；runtime 22:26 正常重启后 Terra 宿主 17224 `--task-profile tools`，任务 394 单命令 `TERRA_TOOLS_RETRY_OK` exit 0、任务 395 写入 `.tmp/terra-tools-write-20261102/ok.txt` 并读回 exit 0（SHA256 `8ED7691A...`），393/394/395 均已收取。**已知边界**：正式宿主首次 tools 任务会触发 Windows 沙箱初始化，本次首任务 393 因初始化超过模型 90s 工具等待返回 blocked；重试 394/395 正常，尚无预热优化。新增 4 个产品/测试文件修改已随文档提交为 `0c6c044`，未推送；提交前 tracked 工作树仅这 4 个代码/测试文件。
> 2026-11-02 22:55（DeepSeek）：**351 任务状态更正**。生产库 `agent_tasks` 中任务 351 已是 `succeeded/completed`、`result_collected_at=2026-11-01 16:00:34`；其结果 2998 是 w-d 在 10-30 08:21 因工具权限返回的 blocked，首轮未产出代码。后续 351-A–G 单独实现了详情页强度控件、`/binding/effort` 和逐任务执行。文档旧“任务 351 待按原权限收取”不成立；不再列为待收取。`12c992f` 已随 11-02 19:09 runtime 重启加载；远端分支 HEAD 为 8650aa0（推送已完成，本地 remote-tracking 未 fetch 的旧 ref 不代表未推送）。
> 2026-11-02 23:00（DeepSeek）：**删除角色后的动态宿主目录清理已完成**。`scripts/role_delete.py` 的 `private_state` 增加 `codex-dynamic`/`kimi-dynamic`：删除成员时移除其 per-member 目录，并且只在对应 project/category 目录为空时清理空父目录；其它角色/项目保留。新增回归覆盖“删除本角色后目录消失、`agent_other` 保留”。`tests.test_role_delete_local` + `tests.test_role_deletion` **73 项 OK**；本地提交 `ccf4521`，未推送。
> 2026-11-02 23:10（DeepSeek）：**PR #7 已关闭（已被当前分支覆盖）；DSH 多角色开发已派 Terra**。任务 396，基线 `f53b53b`，唯一写根 `.tmp/dsh-multi-role-20261102/candidate`（detached worktree），任务包 `.tmp/dsh-multi-role-20261102/TASK.md`。范围：DSH 动态宿主、连接/原生准备、MF-1/MF-2、多角色创建/启停/删除；现有小D固定宿主保持不变。Terra 交付后由 DeepSeek 复核，用户做真实 DSH 角色验收后再提交/推送；当前未推送。
Updated: 2026-11-02 23:10（Asia/Shanghai）。当前状态以顶部最新记录和“当前运行现场”为准；下方 B1 各节仅保留 2026-10-29 的历史排查背景，实际闭环见“旧任务与未解决项”。

## B1 历史未验收快照（已闭环，仅作背景）

- **B1 全链未通过**：请求创建、claim、`rotate-key`（Key 真落盘）、建作业、profile/key_file 已实证；
  `preflight` 与完成回写未走通。B1-c 修了 preflight 两处，**但尚未在任何进程上加载验证**。
- **小K 起不来**：宿主 argv 指向 `TALK-private\keys\agent_kimi.key`（32字节、10-17、已失效），
  worker 写的是 `.talk\keys\agent_kimi.key`（44字节、10-29、有效）；宿主报 `Invalid API key` 8 次。
  属 B1-b 的副作用，Key 路径统一方案（A 同步文件 / B 统一配置 / C 反向设 key_root）待定。
- **服务停止**：`runtime state=stopped`、8000 无监听、宿主全部 stopped，需在正常 PowerShell 启动。
- **`/api/tasks?project_id=...` 出现一次 500**，未定位。
- 本地领先远程约 59 个提交，未推送。

## B1-c 现场事实（2026-10-29 18:36 实测后）

- B1-b 生效：小K 恢复在 17:36:07 成功调用 `rotate-key` **201**，`agent_kimi.key` 与 `credential.json` 已落盘，`credential_version=2`（与 DB `api_key` 一致、身份为 `agent:kimi`）。
- 但配置作业 `preflight` 失败 `identity_mismatch`：`expected_binding_fingerprint` 对无创建操作的请求返回 None；`preflight` 的绑定来源白名单只认 `creation_operation`（补录角色投影为 `legacy_attach`）。
- B1-c 已修两处（指纹回落请求快照、来源白名单加 `legacy_attach`），`test_role_legacy_recover`/`test_role_provision_requests`/`test_role_provision_jobs` 共 80 项通过。
- **生效前提：必须重启整个后台（runtime/宿主）**，因为 preflight 在 worker 进程内；只重启 API 不够。

## B1-b 现场事实（2026-10-29 下午）

- 小K`agent:kimi`16:33的真实恢复请求为`failed`：claim后调`rotate-key`被409拒绝，`role_provision_jobs`零行。原B1-a只打通建请求/建作业/完成回写，换凭据动作无分支。
- 根因链：`C:/Users/Administrator/.talk/keys`下无`agent_kimi.key`（仅空锁守卫）→ worker判absent → 调rotate → 仅managed独占身份可换。该角色能启动是因为宿主常驻持有内存Key，凭据从未落盘。
- 三个旧角色均只在`prj_e8fe7066bbec`名册，无跨项目引用；小K有9条8-9月的`idle`残留实例（进程早已退出），原先会以`rotate_identity_in_use`阻断换Key。

## 当前身份与协作规则

- 本会话实核身份agent:codex；本片按用户最新明确授权本人修复，不冒认上轮大K身份。Git/GitHub操作全部交DeepSeek；本轮未执行Git或派发，本片改动待后续提交。

- 当前大K `agent:prj-e8fe7066bbec.k-d4bf0429`负责决策、拆包、分配和复核，明确保留，不得删除。旧成员`k-4bf013b9`的残留资源另行按归属清理。
- 349/350由DeepSeek开发、大K复核并正常收取completed。首个完整切片完成后，后续新任务按用户约定转为Terra开发、DeepSeek复核，大K只做决策和分配，不自动开工。
- 本日角色页面切片由用户直接指定DeepSeek单独开发、明确免去独立复核、由用户本人页面验收；这是本次明确授权，不改变上面的默认分工。
- `AGENTS.md`已结构化精简并持续人工调整，当前强调：新片先确认、合理颗粒度、单一写入方、独立复核、集中返修、生产权限保护、默认被动。
- Git规则：完整功能切片验收收尾后可推送一次，切片内部多次分布作业和返修只做本地保存。结果消息正文必须且只能是完整`development.json`，不得添加“已完成”“交付路径”等前后说明；旧自由文本结果不追改。

## 已完成实现与发布

- **角色页面三项精简（2026-10-28 晚，用户已验收）**：移除“上次自动启动未完成”提示；创建弹窗运行器/模型各占整行；角色列表文字可框选复制（拖选不导航、选区期间暂缓重绘）。同片返修两轮：下拉文字竖直裁切（定高38px挤16px内容区）、创建弹窗内部滚动条（`max-height`缺0.8界面缩放补偿）。改动5个产品文件+6个测试文件+4份文档，本地提交，未推送。报告与截图见`.tmp/role-list-select-20261028/`。
- **官方思考强度（2026-10-29 凌晨，用户已确认强度显示生效）**：`project_role_bindings` 新增可空 `default_effort`（仅展示，不参与六维指纹与有效性），准备完成时由 Codex 官方`model/list` / Kimi 模型条目写回；绑定行第四段只读该字段，取不到整项省略；创建弹窗模型下拉只显示模型名。存量已回填：codex`xhigh`、kimi`high`、G-terra`low`、大K`high`、Kimi k2.8`max`、DSH`max`；旧GPT与WorkBuddy为空（前者配置无强度，后者绑定模型`kimi-k3`不在当前`models.json`）。
- **角色详情按钮行（2026-10-29 凌晨）**：`绑定重置`移到角色开关操作行第4位（启动/关闭、删除角色之后），去掉按钮下方说明段落；G-terra 截图确认四个按钮齐全。旧角色（小G/小D/小K）仍无该按钮，见下方未解决项。
- **GPT-6.1 Terra目录**：官方`model/list`实测`model=gpt-6.1-terra`、显示`GPT-6.1 Terra`、默认强度`low`且非隐藏。human正常API登记`choice_id=rmc_54101bd4da53`，复用`builtin/openai/native-codex-chatgpt-login`，原Sol保留。
- **349/350 Terra首片**：349首次不通过的延迟启动状态门已由350修复；ready只恢复pending，`not_eligible/failed/enqueued/None`不再复活。共集成28个实现/测试/页面文件，SHA与fix1 candidate一致。集成后111项Node及原失败反例、正常pending和重复回调测试通过；Windows `ADMINI~1`短路径差异为baseline同现的环境限制，不冒充产品通过。
- **发布**：本地集成`8fa0f6e`，公开`4c5cb33`，PR #7仅含本切片34个代码/文档文件，不带其他内部提交，尚未合并。发布工作区`.tmp/terra-role-publication-20261028`保留。发布记录`7c129ca`，交付格式规范`e095f81`。
- **AGENTS公开PR #6**为早期版本，尚未合并或更新；当前分支后续规则以本地文件为准。
- 详[350复验与集成](spec/TERRA_ROLE_REVIEW_350_20261028.md)、[349首次复核](spec/TERRA_ROLE_REVIEW_349_20261028.md)。

## 当前运行现场

- **2026-11-01 内存泄漏 P0 已修复、上线并验收通过**：00:56 正常停启（提交 `27985e9`），基线 329 MB。6 小时 72 次采样（00:56–06:52，进程未重启）：runtime 61.2 → 66.9 MB（**0.016 MB/分钟**，修复前 8.9）、7 宿主合计 158.2 → 175.2（0.048）、API 109.9 → 117.9（0.023）、合计 329.3 → 360.0（**0.086 MB/分钟**）；分段斜率 0.150 → 0.068 → 0.039 逐步下降，符合预热后趋平。夜间 0 条 ERROR、0 次 `MemoryError`/`can't start new thread`，空闲物理 646 → 965 MB。修复前同样 355 分钟预计增长约 11 GB，实测 +30.7 MB。独立复核：**369（K2.8p）已 approved 并收取**——独立复跑 verify_bench 全 `+0.000 KB/call`、346 项 250.219s OK、自采 30.08 分钟 34 点 9 进程斜率全部 <0.2 MB/分钟（runtime 0.00028），证据在 `.tmp/p0-memfix-review-kimi-20261101/`；其交付正文是「说明文字 + 围栏 JSON」，被系统判为自由文本（invalid），结论由我按证据核过。**370（agent:codex）因沙箱拒绝只读命令报 blocked**，19:28 按用户要求收取并置为 completed（保留 blocked 事实，不代表复核通过；真正的独立复核实为 371+377）；环境修复后 18:09 重派 **371**，结论 `changes_requested`：5 个审查点均落到行号，346 项 254.885s OK（2 个符号链接跳过），基准 +0.132/0/0 KB，唯一阻断 **R1**——`_SecurityAttributes` 构造与所有权交接在异常清理区外，注入 MemoryError 时 3 个 SID 不释放。**R1 已返修（提交 `12c992f`）**：try 延伸到交接之后、`handed_off` 标志避免双重释放，新增 `tests/test_role_provision_p0_leak.py` 覆盖两个注入反例、成功路径与 close 幂等；350 项回归中仅既有 flaky `test_slow_real_worker_does_not_block_control_loop_stop` 失败（基线同样 2/3 失败）。**定向复验 377 通过（技术）**：两反例 3/3/0、新增 4 项 + 346 项（275.005s，2 个符号链接跳过）、G4、close 幂等、6 类旧异常与 4 类发布错误码对照、真实 ACL 原子发布全部通过；377 自报 `blocked` 仅因交付枚举冲突（schema 只收 `complete/partial/blocked`，派发时误写 `approved`），已按已处理收取 371/377。诊断、A/B 与「为什么定时清缓存无效」见 [MEMORY_LEAK_DIAGNOSIS_20261031](spec/MEMORY_LEAK_DIAGNOSIS_20261031.md)。
- **2026-11-01 Codex 复核执行能力已补正**：小G 任务模式改为 cwd=项目根 + `workspace-write` + `windows.sandbox="elevated"` + 仓库外 TEMP（`--add-dir`），可写整仓；实测 346 项 296.940s OK、33 项 12.861s OK、仓库根写文件成功。常驻 worktree 方案已放弃；旧 `.codex/config.toml` 已改名 `.codex/config.toml.stale-20261027`。`agent:codex` 宿主已于 19:48 按 drain 标记正常重启为 17568（旧 11172 已退出），服务 generation 51/`ins_49e91fecc579` ready；原生配置校验已改为结构化字段，允许 Codex 写回的项目信任。正式 `codex_role_host.py` 的 tools 分支已于 2026-11-02 补上 `windows.sandbox`/`--add-dir` 并默认 tools（见顶部）；本次 11-01 记录只修正启动校验，当时的完整开发权限未验收。Terra 宿主已于 22:08 正常重启为 18292（服务 generation 16/`ins_71c494b3c6c4` ready）；正式宿主与桥接命令已改用 `developer_instructions`，任务 388 与普通消息均通过。API 已于 22:27 重载为 18248。
- 2026-10-31 15:25实测：`/healthz` 200（db/storage ok），runtime `3928`、API `15212`，startup complete、worker无错、七宿主serving。
- 大K已完成冷恢复并启动至generation 9/`ins_770346c0363b`，running/ready/idle，同实例心跳持续推进；旧实例已离线，不再处于`recovery_required`。
- G-terra已实际启动到ready并正常关闭，最终恢复原关闭状态。任务366暴露的 `base_instructions` 兼容缺陷已在本日参数修复片处理（见顶部）；386/387 复现后已修正，388 与普通消息验收通过。
- 旧`GPT agent:prj-e8fe7066bbec.gpt-79445c1f`仍offline、无实例、无`role_native_setups`准备记录；不要连续点击启动或擅自删除。
- 当前API用系统Python+`PYTHONPATH=D:/claude-test/TALK;D:/claude-test/TALK/.venv/Lib/site-packages`，避免venv exe低完整性。生产配置、原生HOME、Key和既有角色未擅自修改。

## 旧任务与未解决项

- **347/2993**整体仍未完成；**348/2994**两个DSH凭据拒绝边界仍缺修复/复验证据。之前Codex仅补CLI运行配置，本轮仅修Codex启动前缀，均不是348安全修复。原创建者agent:codex，尚未收取；正常收取与业务验收通过须区分。
- **旧角色兼容恢复（B1-a/b/c/d 已完成并实机闭环，2026-10-29 晚）**：小G`agent:codex`、小D`agent:deepseek`、小K`agent:kimi`为`origin=imported`、无创建操作。B1-a 以已提交`role_legacy_attach_operations`为锚点，`choice_snapshot`现读合成；B1-b 补 rotate-key legacy 分支；B1-c 放行 preflight 的补录来源；B1-d 让作业侧预期绑定指纹回落请求快照。20:30/20:44/20:45 三次恢复全部`provisioned`，作业推进为`succeeded`，`credential_version`保持 2，用户确认小K 启停正常。
- **351思考强度（已完成并加载，351-G 已补逐任务修复）**：A–F 覆盖用户覆盖值、官方能力清单与四种运行器落点；351-G 修复 Codex 真实接单路径（cli_bridge 钩子 + 模板化重写），小G 与 Terra 不重启即可逐任务生效。五个运行器的最小实测均已通过（DSH patch、Kimi config.toml、WorkBuddy --effort、Codex rollout/命令行）。用户确认 Codex 复核已完成；任务 351 待按原权限收取，未推送。
- **角色页面余项**：3d 删除清理闭环已完成（`da001a8`）并实机验收；外观模式（白天/夜间）已完成并推送（`bc3bba7`）。
- 旧记录250/2767 failed未收取、286 paused、344/2990 failed未收取，保持不操作。历史主控/页面开发要求可能仍是旧值，不冒称已同步。

## 明日开工（2026-10-30，用户关机前留）

启动命令（正常 PowerShell，`PYTHONPATH` 那行必须带）：

```powershell
cd D:\claude-test\TALK
$env:PYTHONPATH = "D:/claude-test/TALK;D:/claude-test/TALK/.venv/Lib/site-packages"
python -B -X utf8 -m scripts.talk_runtime serve --config "D:/claude-test/TALK-private/talk-runtime.json" --apply --detach
```

状态检查：`python -B -X utf8 -m scripts.talk_runtime status --config "D:/claude-test/TALK-private/talk-runtime.json"`；页面 `http://127.0.0.1:8000`。

已知残留风险：若关机时宿主未正常退出，明天可能出现某宿主 `drain_marker_present`（小D 的
`~/.talk/role-service-host/deepseek-next/prj_e8fe7066bbec/agent_deepseek/drain.request`），
删掉该标记即可；若 `serve` 提示 `*_requires_review`，先确认没有旧 runtime 进程再清
`runtime\*.request`。`reload-api` 的兜底修复已在 `3fc5320`，但要下次整套重启才生效。

明日建议顺序：先 347/348 收尾（只读复核缺口再动手，涉及 DSH 凭据拒绝边界），再做运行器新版本提示（需先定"已适配版本"来源）。

## 下一步恢复顺序

0. **P0 内存泄漏修复：已验收通过（2026-11-01）**。`27985e9` 修复 + `229a735` 观察：6 小时逐进程 <0.2 MB/分钟、合计 0.086 且分段递减；独立复核 369（kimi）approved，370（小G）环境修复后重派为 371，发现 R1 已由 `12c992f` 返修、377 定向复验通过（两反例 3/3/0、346 项、G4、ACL 语义与 close 幂等）；369/370/371/377 均已收取（370 置 completed 但保留 blocked 事实）。剩余：推送与部署均已完成（远端 HEAD 8650aa0；`12c992f` 随 11-02 19:09 runtime 重启加载）。P1 轮询降频、P2 内存观测、P3 并发/内存规格另开切片。
1. **347/2993 与 348/2994 的历史收尾**：整体仍未完成；348 两个 DSH 凭据拒绝边界仍缺修复/复验证据。原创建者为 `agent:codex`，收取需按其身份与权限执行；用户可决定是否重新派发。
2. **推送与收取**：推送已完成（远端 `8650aa0`，2026-11-02）；351 任务已 `completed/collected`（结果 blocked，第一轮，见顶部更正）。新增 Codex tools 修复的 4 个文件尚未提交/推送。
3. **缓存清理**：用户已明确优先级不高，暂缓；盘点结论见下（可安全清理约 40MB，大头是各 CLI 状态目录，不能按缓存删）。
4. 路线图其余条目（定时任务项目化、工作区登记、跨项目/工作区隔离等）见[路线图](spec/DEVELOPMENT_ROADMAP.md)，不自动开工。会话窗口换新 90% 已完成（`8992e7f`）；“任务列表按真实对话窗口展示”和“主被动跟进完整接入与验证”已分别于 2026-11-04 由用户取消（任务窗口保持按任务维度，等待交付统一走程序轮询）；“任务窗口展示交办内容并去掉输入框”已完成并验收（`29842ea`）；“运行器新版本提示”已完成（`17701d5`）；**WorkBuddy 内置模型接入已完成开发与独立复核（432/433，K2.8 PASS，集成提交 `1564191`），待用户验收；验收通过后再推送。**
5. **正式 Codex 宿主 tools 分支：已完成（2026-11-02）**：`scripts/codex_role_host.py` 默认 tools，任务命令带 `windows.sandbox="elevated"` + `--add-dir`；`bridges/codex_execution_native.py` 的 `-c` 白名单已补；Terra 394/395 实测通过。首次 tools 任务的 Windows 沙箱初始化可能超过模型 90s 工具等待，重试通过，预热优化另开。

重开窗口后恢复指令：`继续项目`。历史细节见[PROGRESS_HISTORY](PROGRESS_HISTORY.md)。
