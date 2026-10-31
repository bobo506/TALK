# 351-A 角色思考强度设置与展示（候选设计与验收记录）

日期：2026-10-31（Asia/Shanghai）。来源任务：TALK #351「角色详情页思考强度设置与Codex实际执行贯通」。
本文件只记录 **351-A（设置与展示）** 这一片；#351 的执行贯通部分（Codex 宿主/执行侧真正吃该值、
会话轮换、旧小G与 G-terra 入口）列为 **351-B**，本片未实现、未验证。

生产状态：**未加载**。本片全部改动只在隔离候选 `.tmp/role-effort-detail-20261031/task-351A/candidate/`，
生产源码、生产库、运行中服务均未被修改。

## 1. 目的与范围

用户需要像选择模型一样，在**角色详情页**随时明确指定思考强度，而不是只能在创建角色时确定，
也不需要为了改强度重建角色。原 #351 由 w-d 执行时因会话工具权限被拒而 blocked，零产出；
本片按用户最新直接指令改由 DeepSeek 实现，拆成 A/B 两片串行推进。

本片（A）做：

- 角色详情页大号角色名称右侧的紧凑「思考强度」控件（带清晰标签）；
- 保存为**角色独立设置**，刷新/重开页面后保留；
- 只有真人有权限修改，后端同时校验权限、能力与非法值；
- 明确区分**用户覆盖值**、**模型默认值**与“下一次执行将采用”的生效值；
- 可选项只来自官方模型目录或运行器适配事实，能力未知时如实禁用并解释。

本片（A）不做（留给 351-B）：

- 把强度真正传进 Codex 宿主/执行参数（`model_reasoning_effort`）与原生会话；
- 旧小G入口、G-terra 动态角色的执行侧接入；
- 强度变更时的原生会话轮换；
- 真实模型调用与生产加载。

## 2. 数据模型（只增列）

`project_role_bindings` 新增两列，均不参与六维内容指纹与绑定有效性判定：

| 列 | 含义 | NULL 语义 |
|---|---|---|
| `effort_override` | 真人经角色详情页显式覆盖的思考强度 | 跟随模型默认 |
| `supported_efforts` | 可校验的支持清单（JSON 数组文本，canonical 顺序） | 能力未知 |

已存在的 `default_effort` 保持原语义：由准备流程从官方模型目录写回，宿主启动时回填，
**不会**覆盖 `effort_override`（本片有回归用例固定该行为）。

绑定被重写（换运行器/模型）时，`default_effort`、`effort_override`、`supported_efforts`
一起清空：把旧模型的清单或旧覆盖值沿用到新模型，等于用旧事实冒充新模型的可用性。

## 3. 读取与派生

绑定事实 SQL（单语句、30 列）新增两列后，sha256 由
`2008b7326af9eafb763cffd05dc75e8cff75c9ec833a8b46f1b946d8fd18c294` 变为
`36c5c552e8b521cf1b74daad17d3d609079a5cf2124bcfdd3b27417ff9b9cf0d`
（SQL 正文 2598 字符）。派生规则集中在 `server/models.py::resolve_role_effort`，
读取接口、角色列表与写入响应共用同一份口径，前端不重复实现能力规则：

- `effort_override`：只接受已知强度字面量，否则按 NULL（未设置）处理；
- `effective_effort`：`override ?? default`，只表达“下一次执行将采用的选择”，**不是执行证据**；
- `effort_options` / `effort_source`：
  - 有 `supported_efforts` → `catalog`（官方模型目录）；
  - 否则该 runtime 有适配事实 → `adapter`（运行器实际接受并会传给 CLI 的集合）；
  - 都没有 → 空列表 + `None`（能力未知，不用通用枚举凑数）。

当前适配事实表只有 `codex → {minimal, low, medium, high, xhigh}`，与
`bridges/codex_execution_native.py` 的校验集合一致；351-B 让执行侧成为唯一来源后，该表退化为兜底。

## 4. 写入接口

`PUT /api/projects/{project_id}/roles/{member_id}/binding/effort`

请求体 `{"effort": "high" | null}`（`effort` 为必填键、可为 null；未知字段 422）。

| 情况 | 结果 |
|---|---|
| 非 human 调用 | 403 `only human members can manage projects` |
| 项目不存在 | 404 |
| 绑定不存在 | 404 `role_binding_not_found` |
| `null` / 空串 | 200，清除覆盖、恢复跟随模型默认（不要求能力清单） |
| 非法字面量 | 422 `effort_value_invalid` |
| 能力未知 | 409 `effort_capability_unknown` |
| 不在可选项内 | 422 `effort_not_supported` |
| 合法值 | 200，返回完整绑定响应（含派生事实） |

只改这一列，不创建/解除绑定、不改六维与指纹、不改 `default_effort`。并发语义与既有
`default-effort` 一致：单列最后写入生效，`updated_by` / `updated_at` 如实记录，不新增 CAS。

## 5. 页面行为

- 控件位置：角色详情大号角色名称右侧、名称编辑按钮之前；窄屏允许换行，不压缩标题、不横向溢出。
- 选项：`跟随模型默认（X）` + `effort_options`；`X` 未记录时如实写“未记录”。
- 覆盖值不在当前清单内（准备后目录变动）时仍作为当前项显示，并标注“支持清单未包含”，
  避免下拉悄悄漂移成另一个值。
- 三行提示分别给出：`用户设置：X` / `跟随模型默认`、`模型默认：Y` / `未记录`、可选项来源；
  能力未知时改为“未提供可校验的支持清单，暂不能修改”，控件禁用。
- Agent 会话、归档角色、绑定无效（非 `bound`）时控件禁用；没有绑定行时不渲染控件。
- 保存失败按 401/403/404/409/422 给出中文提示，不显示 HTTP 正文，不回填伪成功值。
- 列表绑定摘要的强度改为**生效值**（覆盖优先），用户覆盖时显示为 `high（用户设置）`，
  未覆盖时保持旧格式，因此列表与详情不会互相矛盾。

## 6. 验收证据（本片实测）

命令与原始输出见 `evidence/`；候选文件清单见 `delivery/manifest.json`。

- `python -B -X utf8 -m unittest tests.test_project_role_bindings tests.test_role_creation_web_ui tests.test_talk_runtime -q` → **Ran 71 tests, OK**
- `python -B -X utf8 -m unittest tests.test_task_binding_snapshot -q` → **Ran 27 tests, OK**
- `python -B -X utf8 -m unittest tests.test_task_binding_snapshot tests.test_project_role_startup tests.test_project_startup_runtime tests.test_role_services -q` → **Ran 148 tests, OK**
- Node 全量（26 个 `tests/*.test.cjs`）：
  - 基线（HEAD 干净副本）：`tests 383 / pass 367 / fail 16`
  - 候选：`tests 390 / pass 374 / fail 16`
  - 失败集合逐项比对**完全一致**，均为既有失败；新增 7 个用例全部通过。
- `tests/workspace_role_binding.test.cjs` 单文件：**22/22 通过**（15 既有 + 7 新增）。

未运行/未验证（如实记录）：

- 未做真实浏览器截图：本片在隔离候选内运行，未启动页面服务，属 not_run；
- 未加载生产、未改生产库、未启停服务；
- 未验证真实执行参数（属 351-B），不能把“配置已保存”当成“已实际执行”。

## 7. 351-B 待办（本片未实现）

1. Codex 宿主/执行侧读取 `effort_override` 并传入 `-c model_reasoning_effort=...`；
   运行器拒绝/不支持时必须明确反馈，不静默降级。
2. 强度变更后的原生活跃会话处理：按既有受管机制轮换，不清理旧会话/锁/归属。
3. 旧小G入口（`.tmp/legacy-role-page-control/codex-next/`）与 G-terra 动态角色入口的执行侧接入。
4. 准备流程写入 `supported_efforts`（Codex 官方 `model/list` 的 `supportedReasoningEfforts`，
   Kimi `models.json` 的 `support_efforts`），让 catalog 来源在真实数据上可用；本片先用
   adapter 事实覆盖 codex，未改准备/写回链路。
5. 生产加载方案与回退步骤，需单独授权后执行。

## 8. 回退

本片只增列、只增接口与控件；回退为恢复 6 个产品文件（`server/models.py`、`server/db.py`、
`server/routes/projects.py`、`web/workspace.js`、`web/workspace.css`、`web/index.html`）与
对应测试/文档到基线版本即可。新增两列为空列，不参与任何既有判定，保留列不影响旧代码读取。

## 9. 生产加载（需单独授权，本片未执行）

按项目既有节奏，加载应走“冻结 → 独立复核 → 明确授权 → 正常停机 → 替换 → 重启”的顺序，
不能在服务运行中热替换：

1. 替换前逐文件核对候选 `post_sha256` 与生产当前文件 hash，确认无第三方漂移；
2. 备份生产 6 个文件（保留原不存在记录），记录备份路径与 hash；
3. 按既有受管方式正常停止承载页面的服务，确认旧进程退出；
4. 复制 6 个产品文件，核验 hash 与候选一致；
5. 正常启动同一服务，最小检查：`GET /api/projects/{id}/agents` 返回新增字段、
   `PUT .../binding/effort` 按上表校验、页面按 Ctrl+F5 后控件出现；
6. 数据库迁移由 `init_db()` 只增列完成，不重建表、不回填数据；
7. 失败回退：停机 → 恢复备份 6 文件 → 重启；新增空列可不回滚，不影响旧代码。
