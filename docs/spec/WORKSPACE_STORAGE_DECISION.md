# 工作区存储与分发方向（2026-11-06 确定）

本文件记录用户与协调者确定的工作区数据布局、便携分发方向和 W3 边界；实现以任务包为准，本文不单独构成开工授权。

## 决策

1. **中央库**：`TALK/talk.db` 继续保存项目、成员、任务、群、消息、角色元数据，按 `project_id` 区分；**现在不拆每工作区 DB**。
2. **每工作区目录**：`TALK/workspaces/<project_id>/` 保存该工作区的 TALK 数据——角色运行时、任务附件/日志/导出、runtime 状态等；**不保存真实项目源码**。
3. **真实项目目录在 TALK 外**：例如 `D:\test` 仍是项目源码目录，TALK 只在其中放 `.talk/project.yaml` 指针。
4. **角色 ID 带项目前缀**：延续现有 `agent:<project_id>.<role>.<hash>` 形式；同名角色在不同工作区生成不同 ID/Key/运行时目录。
5. **分发目标：文件夹绿色版**：整个 TALK 目录压缩拷贝到新设备，提供启动文件即可；不做安装器，不做可配置 `data_root`，不写 AppData/注册表。
6. **角色运行时按 project+role 隔离**：路径包含 `project_id` 与 `member_id`；服务状态、HOME、cwd、Key、会话均按此命名空间隔离。
7. **角色 Key 安全**：Key 可随 TALK 目录携带，但 zip 会包含秘密；实现时放 `TALK/keys/<project_id>/` 并明确提示，后续可评估加密或外部 Key 模式。

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
  keys/
    <project_id>/               # 角色 Key（敏感）
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

注意：`identity_exclusive_reference_refused` 表示**不要复用**另一个工作区已有的角色身份；W3 是在目标工作区**新建**自己的角色，不是放开跨项目复用。
