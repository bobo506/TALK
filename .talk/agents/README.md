# Agent Profiles（TALK dogfood）

每个接入本项目的 Agent 在此目录下拥有一个子目录，存放其身份层四件套
（PROJECT_INTEGRATION §5.3）：IDENTITY / SOUL / USER / MEMORY。

## 目录命名约定（Windows 安全）

`member_id` 含 `:`（如 `agent:codex`），而 Windows 文件系统禁止目录名含 `:`。
因此目录名按 **`:` → `_`** 净化：

| member_id | 目录名 |
|-----------|--------|
| `agent:codex` | `agent_codex/` |
| `agent:pi` | `agent_pi/` |
| `agent:pi-kimi` | `agent_pi-kimi/` |

> bridge 按 member_id 查 profile 时需做同样的净化映射（Phase 2 落地）。
> server 端 `project_agents` 表存的是显式相对路径，不依赖目录名等于 member_id。

## 四件套

```
agent_<id>/
├── IDENTITY.md   # 必需 — 我是谁、Agent 类型、擅长领域
├── SOUL.md       # 必需 — 语气、决策风格、不可逾越的边界
├── USER.md       # 可选 — 这个项目里的搭档信息
└── MEMORY.md     # 可选 — 长期记忆（或指向外部存储的指针）
```

`MEMORY.md` 的运行期数据建议放 `.talk/memory/`（已 .gitignore）。
