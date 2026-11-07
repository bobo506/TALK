# W3a 验收说明（2026-11-07）

本文件是 W3a（每工作区独立角色身份与创建流程）的人工验收说明。开发、自测与独立复核已完成；**尚未部署、尚未做真实浏览器验收**。

## 一、交付范围与提交

| 子切片 | 内容 | 提交 |
|---|---|---|
| W3a-1 | `storage_layout` 字段（`project_roles` / `role_provision_requests`）、`server/workspace_paths.py` 路径 resolver、Key 形态守卫、profile 兼容、`.gitignore` | `22446d5` |
| W3a-2a | 新角色/请求行写 `workspace-v1`、请求投影带布局、路径登记接受 workspace-v1、provision 真实写入（Key+三档案）、worker 顺序（目录/`workspace.json` 排他发布/Key/ACK） | `2f4809a` |
| W3a-2b-1 | 后端全部启动入口拒绝 workspace-v1（`workspace_runtime_not_ready`），legacy 不变 | `340e52b` |
| W3a-2b-2 | 前端创建角色固定 `auto_start:false`、新布局角色提示"角色已准备，运行时隔离待启用 / 自动启动已关闭" | `68d6522` |

独立复核：489（W3a-1）、500+502（W3a-2a）、504（W3a-2b-1）、506（W3a-2b-2），均 approved。

## 二、部署前须知（**重要**）

- **W3a 新布局角色不可运行**：这是设计约定（运行时隔离属 W3b），新建角色只会"已准备、不可启动"。因此建议 **W3a 与 W3b 同一窗口部署**；如先单独部署 W3a，需接受"新角色暂不可用"。
- 部署会触发 `server/db.py` 的幂等迁移（两张表加 `storage_layout`，旧行默认 `legacy`）。**部署前备份 `talk.db`**，部署后核对列存在与旧数据不变。
- 澄清额度改动（默认 3/上限 5）已开发并复核，无 schema 变更，可在 W3a 验收后单独 reload 生效。
- 部署方式沿用现有 runtime 受控 reload（不重启角色宿主）；生产启停需项目管理者授权。

## 三、人工验收步骤（真实浏览器，隔离或备份后进行）

1. 打开页面 → 进入角色页（项目设置内）。
2. 新建一个角色：提交前确认"自动启动"控件为禁用状态；创建成功后，卡片应显示"角色已准备，运行时隔离待启用"与"自动启动已关闭"。
3. 打开浏览器开发者工具，确认创建请求体中 `auto_start === false`；重复提交同一 `operation_key`（缓存重放），请求体应保持原键原载荷。
4. 已有 legacy 角色卡片：**不应**出现上述新布局提示，原自动启动/配置反馈保持。
5. 对新布局角色点"启动"：应收到稳定错误 `workspace_runtime_not_ready`，页面显示中文提示，不产生进程、不写启动记录。
6. 对 legacy 角色启动/停止一次：行为与改动前一致。
7. 落点检查（隔离环境）：`workspaces/<编码 project_id>/workspace.json` 存在且内容无 Key；`roles/<编码 member_id>/profiles/` 有三份档案；Key 位于 resolver 计算位置（git 形态在仓库外，非 git 形态在 `keys/<编码 project_id>/`）。

## 四、已知限制与未验证项

- 真实浏览器未验证（开发/复核均仅自动化测试）；页面提示为纯文本、复用现有样式类。
- 新布局角色不可运行（等 W3b）；`talk_runtime`/`role_service_host` 仅实现启动拒绝，未实现 HOME/session/state 隔离。
- 服务端 start 意图 API 在未传 guard 时仍会受理 workspace-v1 意图（真正拒绝在 host 执行层），直连会产生"反复拒绝但不 claim"的 pending launch；计划 W3b 收紧。
- Windows junction/reparse 防护只有模拟用例，未做真实 junction 验收。
- git 形态新 Key 命名（`m-<base32>.key`）与 legacy 旧命名（`<member_dir_name>.key`）并存，统一留 W3b。
- `tests/test_talk_task_tools` 中两个 `list_agents` 用例在本机默认临时目录下会假失败（基线同样），需显式设置可写 `TEMP`/`TMP`/`SQLITE_TMPDIR`。

## 五、回退

- 代码回退：`git revert` 对应提交或回到 `9c73c39`（W3a-2b-1 前）。
- 数据回退：使用部署前备份的 `talk.db`；`storage_layout` 列可保留（旧行 `legacy` 不影响旧行为）。
