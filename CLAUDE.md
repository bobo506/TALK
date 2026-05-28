# TALK — Claude Code 入口

本文件由 Claude Code 自动加载。Claude 在本项目中作为一个普通 agent，遵循全 agent 通用的协作约定，不享受特殊待遇。

## 必读清单

1. `AGENTS.md` —— 抽象角色字典（决策 / 执行 Agent）、协作节奏、切片收尾约定、编码与文档语言约定、项目结构注意事项、技术栈速查、启动方式
2. `docs/PROJECT_BRIEF.md` —— 项目定位、系统架构、数据模型、运维基线、模块索引；模块索引指向各 `MODULE_xxx.md`，按任务只读对应那一份
3. `docs/PROGRESS.md` —— 当前进度快照、当前角色分配、卡点与下一步计划

## Claude 在本项目的身份

- **决策分级**（决策 Agent / 执行 Agent）与**业务角色**（lead / dev / ui / tester 等）的来源：
  - **目标态**：bridge 在 prompt 中按 bridge 配置 + `groups.metadata.roles` 注入。该"角色注入框架"尚未落地，对应 `docs/PROGRESS.md` Next Plan 修复项 5.3。
  - **过渡态**：5.3 落地之前，Claude 的角色由 `docs/PROGRESS.md` 第 1 节 "Current Agent Role" 显式声明；未声明则按 `AGENTS.md` 默认规则处理（即**执行 Agent**）。

## 部署 / 运维入口

详见 `docs/DEPLOY.md`、`docs/QUICKSTART_USER.md`，及 `docs/PROJECT_BRIEF.md` "运维基线"段。
