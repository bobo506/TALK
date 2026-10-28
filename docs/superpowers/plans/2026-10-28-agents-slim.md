# AGENTS.md 结构化精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将自动加载的 `AGENTS.md` 精简为当前授权与长期规则入口，同时保留348交接事实和全部现行协作约束。

**Architecture:** 规则与进度分离：`AGENTS.md` 保留稳定规则和链接，任务状态继续由进度、交接、路线图、用户手册及验收文档承载。完整替换规则文件后，通过关键规则清单、相对链接和Git差异验证，避免精简为简单删历史而引入规则冲突。

**Tech Stack:** Markdown、Python标准库、Git。

**Spec:** `docs/superpowers/specs/2026-10-28-agents-slim-design.md`

## Global Constraints

- 只修改 `AGENTS.md` 以及本设计/计划文档，不改产品、测试、任务状态或生产配置。
- 目标为6,000–16,000个Unicode字符；不得为达字数删除现行约束，也不为达到预估下限保留重复说明。
- 当前348验收不通过、2994仅原创建者可收取、返修未自动授权等事实必须准确保留。
- 中文描述，UTF-8；不自动推送。

## Review Focus

- 旧分工与新分工冲突：以用户最新明确授权和具体任务包为准，测试当前角色节不含已失效的固定Codex分工。
- 历史事实丢失：348两项失败、未集成、未收取及原身份收尾限制继续可发现，测试相应事实和文档链接存在。
- 规则重复导致再次膨胀：每项长期规则只在一个主章节表达，测试无带日期的任务流水账。
- 链接迁移失效：所有相对Markdown链接都解析到仓库内现有文件。
- 误改其它现场：最终Git差异仅限设计和计划文档及 `AGENTS.md`，348材料和任务状态不变。

---

### Task 1: 重写规则入口

**Files:**
- Modify: `AGENTS.md`
- Reference: `docs/PROGRESS.md`
- Reference: `docs/HANDOFF_20261028.md`
- Reference: `docs/spec/DEVELOPMENT_ROADMAP.md`
- Reference: `docs/guides/USER_MANUAL.md`

**Interfaces:**
- Consumes: 已确认的设计和现有正式文档中的当前事实。
- Produces: 仅含当前授权、长期规则、文档索引和开发约定的 `AGENTS.md`。

- [ ] **Step 1: 核对重写前基线**

Run: `python -c "from pathlib import Path; p=Path('AGENTS.md'); s=p.read_text(encoding='utf-8'); print(len(s.splitlines()), len(s), p.stat().st_size)"`
Expected: 当前基线约498行、67,729字符、137,844字节；若不同，先审阅外部新增变更再重写。

- [ ] **Step 2: 完整替换 `AGENTS.md`**

按设计五部分写入：开发者指引与文档入口；当前身份与348交接；分工、切片、隔离、复核；交付、进度、Git、人验；终端、编码和启动约定。删除带日期的任务流水账和已被替代的固定分工，不复制路线图或用户手册正文。

- [ ] **Step 3: 检查篇幅和关键规则**

Run: `python -c "from pathlib import Path; s=Path('AGENTS.md').read_text(encoding='utf-8'); required=['每个新切片','独立复核','集中返修','默认被动','人工验收','docs/spec/DEVELOPMENT_ROADMAP.md','docs/guides/USER_MANUAL.md','2994','TALK_API_KEY','argv']; missing=[x for x in required if x not in s]; print({'chars':len(s),'lines':len(s.splitlines()),'missing':missing}); assert 6000 <= len(s) <= 16000 and not missing"`
Expected: 字符在目标区间，`missing=[]`。

### Task 2: 验证与本地收尾

**Files:**
- Verify: `AGENTS.md`
- Verify: `docs/superpowers/specs/2026-10-28-agents-slim-design.md`
- Verify: `docs/superpowers/plans/2026-10-28-agents-slim.md`

**Interfaces:**
- Consumes: Task 1的规则文件。
- Produces: 可审阅、可回溯的纯文档变更。

- [ ] **Step 1: 验证相对链接和Markdown基本完整性**

Run: `python -c "from pathlib import Path; import re; p=Path('AGENTS.md'); links=[x for x in re.findall(r'\[[^]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')) if '://' not in x and not x.startswith('#')]; missing=[x for x in links if not (p.parent/x.split('#')[0]).exists()]; print({'links':len(links),'missing':missing}); assert not missing"`
Expected: 所有本地链接目标存在，`missing=[]`。

- [ ] **Step 2: 审阅最终差异和空白错误**

Run: `git diff --check && git diff --stat && git status --short`
Expected: 无空白错误；产品源码、测试、348材料和任务文档无未授权改动，仅有本设计、计划和 `AGENTS.md`。

- [ ] **Step 3: 本地提交**

Run: `git add AGENTS.md docs/superpowers/specs/2026-10-28-agents-slim-design.md docs/superpowers/plans/2026-10-28-agents-slim.md && git commit -m "文档：结构化精简 AGENTS 规则入口"`
Expected: 仅上述文档进入一次本地提交，不推送。
