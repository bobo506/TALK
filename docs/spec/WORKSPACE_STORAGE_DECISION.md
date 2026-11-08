# 工作区存储与分发方向（2026-11-06 确定）

本文件记录用户与协调者确定的工作区数据布局、便携分发方向和 W3 边界；实现以任务包为准，本文不单独构成开工授权。

## 决策

1. **中央库**：`TALK/talk.db` 继续保存项目、成员、任务、群、消息、角色元数据，按 `project_id` 区分；**现在不拆每工作区 DB**。
2. **每工作区目录**：`TALK/workspaces/<project_id>/` 保存该工作区的 TALK 数据——角色运行时、任务附件/日志/导出、runtime 状态等；**不保存真实项目源码**。
3. **真实项目目录在 TALK 外**：例如 `D:\test` 仍是项目源码目录，TALK 只在其中放 `.talk/project.yaml` 指针。
4. **角色 ID 带项目前缀**：延续现有 `agent:<project_id>.<role>.<hash>` 形式；同名角色在不同工作区生成不同 ID/Key/运行时目录。
5. **分发目标：文件夹绿色版**：整个 TALK 目录压缩拷贝到新设备，提供启动文件即可；不做安装器，不做可配置 `data_root`，不写 AppData/注册表。
6. **角色运行时按 project+role 隔离**：路径包含 `project_id` 与 `member_id`；服务状态、HOME、cwd、Key、会话均按此命名空间隔离。
7. **角色 Key 安全（2026-11-06 追加细化）**：按**部署形态自动判定**——数据根在 git 工作区内时，Key 一律不落 TALK 目录（沿用仓库外私有 Key 根，如 `~/.talk/keys`，现有"拒绝仓库内 Key"守卫保留）；数据根不是 git 工作区（绿色版解压后的正式使用）时，角色 Key 落 `TALK/keys/<project_id>/`，作为角色要素随目录管理。`.gitignore` 追加 `/keys/` 兜底，防止开发期误推；打包 zip 会包含明文秘密，需提示，不做加密。
8. **运行器目录（2026-11-06 确定）**：`TALK/runners/<runtime>/` 单独存放终端运行器（codex / kimi-code / dsh / workbuddy）的**适配数据与元数据**——模型清单与别名、思考强度选项、版本适配基线、探测缓存等。**不放**凭据/登录态（仍在角色 native HOME），**不托管** CLI 安装本体；数据可由代码默认值生成、可覆盖、可重建。

## 目录布局

```
TALK/
  start.bat / TALK.exe          # 启动器（后续打包切片）
  server/ web/ scripts/ bridges/
  config.toml
  talk.db                       # 中央元数据，按 project_id 区分
  workspaces/
    <project_id>/
      workspace.json            # 显示名、真实根路径、创建时间
      roles/
        <member_id>/            # 角色运行时配置/HOME/会话
      tasks/                    # 任务附件、日志、导出
      runtime/                  # 服务状态、进程日志
  runners/
    <runtime>/                  # 适配数据/元数据：模型清单、强度选项、版本基线、探测缓存
  keys/
    <project_id>/               # 角色 Key（敏感）；仅正式部署写入，开发期不写此目录
  uploads/                      # 文件上传（可按 project_id 分目录）
```

真实项目：
```
D:\test\
  .talk\project.yaml            # 仅注册指针
  ...项目源码...
```

## 非目标

- 不把实际项目源码放进 TALK。
- 不把角色 Key/原生 HOME 放进项目源码目录。
- 开发期（数据根在 git 工作区）不往 TALK 目录写 Key；只有正式部署（数据根不是 git 工作区）才写 `keys/`。
- `runners/` 不放凭据/登录态，不托管运行器 CLI 安装本体。
- 现在不拆每工作区 DB；所有表已有 `project_id`，保留未来按项目迁移/导出路径。
- 现在不做安装器、服务注册、AppData 数据目录选择。
- 不改现有 TALK 角色 ID 或迁移历史数据；新角色按新规则。

## 未来拆库触发条件（仅记录，不实现）

- `talk.db` 达到数 GB、备份/恢复明显变慢；
- 多 Agent 并发写频繁出现 `database is locked`；
- 需要单独搬走/备份/删除一个工作区；
- 合规或隔离要求必须物理分库。

到时可按项目把行导出到 `workspaces/<project_id>/workspace.db`，API 增加路由层；当前不提前复杂化。

## W3 建议切片

- **W3a 身份与创建**：每工作区新建角色，ID 带项目前缀；同名跨工作区不同 ID/Key；现有角色不变。
- **W3b 运行时隔离**：HOME/cwd/Key/服务状态/启动停止按 project+role 隔离；A 工作区 stop 不影响 B。
- **W3c 双工作区验收**：两个工作区各建角色，分别跑任务、切换、停止，互不影响。
- **运行器适配目录（独立后续切片，不在 W3a–W3c）**：`TALK/runners/<runtime>/` 落地决策 8，需先确定哪些适配数据从代码默认值迁到数据文件，避免两处真相。

注意：`identity_exclusive_reference_refused` 表示**不要复用**另一个工作区已有的角色身份；W3 是在目标工作区**新建**自己的角色，不是放开跨项目复用。W3a 设计必须按决策 7/8：Key 落点按部署形态自动判定（git 工作区→仓库外；非 git 工作区→`TALK/keys/<project_id>/`），`runners/` 只存适配数据/元数据。

## 分发版只保留新布局（2026-11-08 用户确定）

- **当前开发实例（TALK 项目，`prj_e8fe7066bbec`）继续兼容存量 legacy 角色**：不迁移、不重建，启停与路径行为保持。
- **后续完成的正式安装包只带新布局**：不再包含 legacy 路径与兼容入口；新装实例的所有新角色统一 `workspace-v1`（`workspaces/<project>/roles/<member>/…`）。
- 不提供“按项目选择 legacy”的开关；legacy 仅作为当前实例的存量兼容。
- **触发条件**：W3c 验收与开闸稳定后，另起切片清理 legacy（只读盘点 → 回归 → 移除兼容代码/迁移入口/相关文档）；现有实例不受影响。
