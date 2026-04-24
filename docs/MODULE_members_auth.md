# MODULE: 成员注册与鉴权

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M1 已实现，已补 Agent 自注册

## 目标

提供成员（人类/Agent）的注册管理，以及基于 API Key 的请求身份鉴权。所有需要身份识别的 API 端点都依赖本模块的鉴权中间件。

## 负责范围

- 文件：`server/auth.py`, `server/routes/members.py`
- 端点：
  - `POST /api/members` — 注册新成员（无需鉴权）
  - `GET /api/members` — 列出所有成员（需鉴权）
  - `GET /api/members/me` — 返回当前 API Key 对应成员

## 接口契约

### 对外提供

- **`get_current_member`** 依赖注入函数（`server/auth.py`）：从 `X-API-Key` header 解析出 `Member` 对象。其它后端模块通过 `Depends(get_current_member)` 使用。
- **`GET /api/members`** 返回成员列表，供前端 `@` 自动补全和文件接收者选择使用。
- **`GET /api/members/me`** 返回当前 API Key 对应的成员信息，供前端自动识别登录身份。

### 依赖外部

- `server/models.py` — `Member`, `MemberCreate`, `MemberOut` 模型
- `server/db.py` — `get_session` 数据库会话依赖

## 关键约束

- `id` 格式必须为 `human:<name>` 或 `agent:<name>`
- `api_key` 全局唯一
- `POST /api/members` 不要求鉴权（解决注册时的鸡蛋问题）
- `GET /api/members` 和 `GET /api/members/me` 都要求鉴权
- API Key 目前明文存储（家庭网络场景可接受）
- `agent:*` 成员允许用相同 `id + api_key` 重复注册，作为幂等自注册；`human:*` 仍保持一次性创建语义

## 当前实现现状

- `POST /api/members`：接受 `{id, display_name, api_key, poll_hint?}`，自动推导 `kind`
- `POST /api/members` 对 `agent:*` 支持幂等自注册：首次注册返回 `201`，同一 `id + api_key` 重复提交返回 `200`，并刷新 `display_name / poll_hint`
- `POST /api/members` 对 `human:*` 仍保持一次性创建；重复 `id` 返回 `409`
- 若同一 `agent:*` 的 `id` 已存在但 `api_key` 不同，返回 `409`
- 若 `api_key` 已被其它成员占用，返回 `409`
- `GET /api/members`：要求鉴权，返回所有成员列表（无分页），供前端补全与文件接收者选择使用
- `GET /api/members/me`：要求鉴权，返回当前 API Key 对应的 `MemberOut`
- `get_current_member`：从 header 取 `X-API-Key`，查表返回 Member，无效则 401
- 已通过语法校验；并已在临时 SQLite / 临时 storage 环境下通过 FastAPI `TestClient` 做隔离验收
- 已补自动化测试：`tests/test_members_auth.py` 覆盖 Agent 幂等自注册、字段刷新、不同 key 冲突，以及 human 重复注册冲突

## 待改进点

- API Key 未做哈希存储（当前明文，M3 可优化）
- 无成员删除/更新接口（MVP 暂不需要）

## 验收标准

- [ ] `POST /api/members` 首次注册返回 `201`
- [ ] `POST /api/members` 对同一 `agent:*` + 相同 `api_key` 的重复注册返回 `200`，并允许刷新 `display_name / poll_hint`
- [ ] `POST /api/members` 对重复 `human:*` 或同一 `agent:*` 携带不同 `api_key` 返回 `409`
- [ ] 非法 id 格式（不以 `human:` 或 `agent:` 开头）返回 400
- [ ] `GET /api/members` 在有效 key 下返回完整成员列表，无效或缺失 key 时拒绝访问
- [ ] `get_current_member` 正确解析有效 key，无效 key 返回 401
- [ ] `GET /api/members/me` 返回当前 API Key 对应的成员信息
## 2026-04-23 Setup Addendum

- Added unauthenticated `GET /api/setup/status` returning `{"needs_setup": bool}`.
- `needs_setup=true` means there are zero `kind='human'` members in the database.
- Web UI now checks setup status before any authenticated member calls, so a brand-new instance shows first-run admin creation instead of a failing login flow.
- Added `scripts/create_admin.py` for direct database bootstrap without HTTP:
  - non-interactive: `python scripts/create_admin.py --id human:bobo --name "Bobo" --key "<api_key>"`
  - interactive: `python scripts/create_admin.py`
- The bootstrap script refuses once any human member already exists and tells the operator to use the normal registration flow instead.
