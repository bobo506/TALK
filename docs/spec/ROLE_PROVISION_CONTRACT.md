# 角色宿主配置合同（R1-2）

> 2026-10-11：经 #218–#221 补正、Codex 定向修复及 #222 独立复核后发布；原草稿与失败记录保留。
> 上层依据：[生命周期设计](ROLE_LIFECYCLE_DESIGN.md) §7.4–7.8；使用见 [验收指南](../guides/ROLE_PROVISION_ACCEPTANCE.md)。

## 0. 范围与权限

作业承接 R1-1 已创建角色的身份档、仓库外 TALK Key 文件、启动前检查。显式目标为 `project_id/member_id/operation_key`；不重建身份、不重发 Key、不批量同步名册。

四个配置入口均要求 `kind=human`，使用 `X-API-Key`；agent 调用 403。没有对应 `role_creation_operations` 的历史导入身份拒绝配置，不伪造创建操作。原生运行器账号与 TALK 角色凭据分别管理。

本片提供 API/宿主脚本并去除页面固定分级；页面一键配置按钮、受管服务启停、删除及退出清理继续 R1-3/R1-4。

## 1. 作业记录

`role_provision_jobs` 以原创建操作的 `operation_key` 为主键，保存 `project_id/member_id/status/steps/resume_of/revision/credential_version`、创建者及时间。写入口在检查角色事实前取得 SQLite 写锁并刷新 ORM 事实。

步骤固定 `profile/key_file/preflight`，每步只含 `state/attempts/error_code/updated_at`。步骤状态 `pending/succeeded/failed/skipped`；作业状态不代表任务执行或服务已启动。

### 1.1 状态与版本

- 有失败：全失败为 `failed`，其余为 `partial`。无失败：全部待跑为 `pending`，部分待跑为 `running`，全部成功/跳过为 `succeeded`。
- 初建三步 `pending`、`attempts=1`，作业 `revision=1`。
- `credential_version` 是创建/续跑时角色凭据版本快照。轮换不追改历史成功作业；消费时必须比较当前版本。
- `revision`、单步 `attempt` 与凭据版本共同防止旧回报覆盖新尝试。

## 2. API

前缀 `/api/projects/{project_id}/roles/{member_id}`。请求禁止额外字段。每个入口核验项目/角色/成员/名册：归档、禁用、离册、身份缺失或操作不匹配稳定拒绝，恢复不绕过检查。

### 2.1 `POST /provision`

```json
{"operation_key":"<原创建操作键>","resume":false,"steps":null}
```

首次创建 201；已有且 `resume=false` 返回 200 原样读回。`resume=true` 默认重开失败/待跑步骤，也可用非空 `steps` 子集定向续跑；重开步骤 `attempts+1`，作业 `revision+1`，记录 `resume_of`。

凭据版本相同且已成功返回 `409 provision_job_terminal`。版本变化后允许显式续跑，即使历史成功，也强制重开 `key_file/preflight` 并更新快照；旧成功不能证明新 Key 有效。版本相同时保留已成功/跳过步骤；版本变化时显式选中的步骤依服务端规则重开。

### 2.2 `GET /provision?operation_key=...`

只读作业；无作业 `404 provision_job_not_found`，非法参数 422。仍检查当前角色资格。

### 2.3 `POST /provision/ack`

```json
{"operation_key":"<原创建操作键>","step":"profile","attempt":1,
 "revision":1,"credential_version":1,"state":"succeeded","error_code":null}
```

`state` 只能 `succeeded/failed/skipped`；只有 `failed` 可带安全错误码（最多 64 字符）。检查当前角色后，依次检查 revision、步骤待跑状态、attempt、凭据版本，冲突为 `provision_revision_conflict/provision_step_not_pending/provision_stale_attempt/provision_credential_stale`（409）。

ACK 版本必须同时等于作业快照与角色当前值。成功更新单步、聚合状态和 `revision+1`。宿主在本地步骤前捕获代际，不能重新读新版本为旧证明补造回报。

### 2.4 公开响应

白名单：

```text
operation_key, project_id, member_id, status, revision,
credential_version, role_credential_version, expected_binding_fingerprint,
resume_of, steps, created_by, created_at, updated_at
```

`role_credential_version` 是读取时角色当前版本；`expected_binding_fingerprint` 来自原创建 choice，采用既有六维指纹算法。单步只含 §1 的四字段。不含 Key、凭据路径、绝对路径、argv 或异常正文。

### 2.5 `POST /provision/roster-paths`

请求 `operation_key/identity_path/soul_path/user_path`，只登记本人三份相对路径。固定根 `.talk/agents/<该成员目录>/`、文件 `IDENTITY.md/SOUL.md/USER.md`；拒绝绝对路径、越界、跨角色或混合目录。响应只有 `member_id` 与三相对路径，不做全量 sync。

## 3. 宿主脚本

### 3.1 参数与凭据

`python scripts/role_provision.py` 必填 `--project/--member/--operation-key`。默认 dry-run，零 HTTP/文件写入；没有单独 `--dry-run` 参数，`--apply` 才执行配置。

可选 `--project-root/--key-root/--base-url/--steps/--resume/--overwrite-profile/--key-input-file/--cli-executable/--lock-stale-seconds/--timeout-seconds/--json`。默认仓库根、用户 `.talk/keys`、HTTP 15 秒、陈旧锁阈值 900 秒。

角色 Key 来自已存目标文件、`--key-input-file` 或 `TALK_ROLE_API_KEY`；human 操作者来自 `TALK_OPERATOR_API_KEY` 或 `TALK_OPERATOR_KEY_FILE`。不在 argv 传 Key。脚本不代调轮换，不从作业重新获取 Key。

缺 operator 时可能只有部分本地步骤，返回 `operator_key_missing/partial`，不伪报 ACK。具备 operator 时先确认作业/代际，再写身份档/Key；失效代际必须显式 `--resume`。

### 3.2 三步与重复执行

- `profile`：三份本人档案；保留人工内容、补缺失文件，只有显式 `--overwrite-profile` 才覆盖。
- `key_file`：已有文件读回并通过 `/api/members/me`；未知/旧 Key 拒绝覆盖。新 Key 同目录临时写、flush、验证、原子替换。Windows 在临时文件创建时设置私有 DACL（当前用户/SYSTEM/Administrators），再核验；失败不退回直接写最终文件。POSIX 使用 0600。
- `preflight`：三档实际可读、本人身份匹配、本人名册路径、角色存在、绑定 `bound`，运行器/模型/alias 与选择一致；原 choice 指纹与当前绑定指纹精确比较，防止连接来源漂移。`--cli-executable` 只检查文件存在，不执行。

重复配置仍核当前资格/版本/精确绑定。只有精确 `provision_job_terminal` 409 与新鲜同 revision/凭据版本读回，才能按已完成处理；泛化409/未知/禁用/离册/归档拒绝不能被随后恢复读回升级为成功。

### 3.3 路径、锁与中断

Key 根必须仓库外。对声明路径及祖先检查现有 symlink/junction/reparse，再解析边界；锁/guard 检查在 mkdir 前执行，取得 guard 时复查。验证覆盖静态链接，不承诺防御检查/创建之间恶意并发路径替换。

身份档与 Key 各自加锁，身份档锁不依赖 Key 根。永久 `<lock>.guard` 使用 OS 互斥（Windows 字节锁/POSIX flock），不能删除锁住的 inode。完整 owner 记录先临时写/flush/fsync，再原子排他发布；替代发布同样受 guard 保护。

持有 OS guard、owner 确认已死且过期才回收。未知/不可解析旧锁 fail closed，不只凭时间删除。只释放本人令牌；活 owner 的临时文件保持，死 owner 可识别临时文件可清理。结束保留永久 guard，移除本人可见锁记录。

### 3.4 输出与退出

`--json` 单一 `talk-role-provision-1` 对象，含三步/ACK/作业/稳定错误码。本地输出可含操作者显式选择的路径，不打印 Key/异常正文；公开 API 遵守 §2.4。

退出 0：计划完整或配置 `applied`；1：`partial/failed`；2：参数错误。`applied` 是所选配置步骤成功；若只选子集须另外核完整三步，不代表原生登录/服务就绪。

### 3.5 恢复

| 情况 | 处理 |
| --- | --- |
| `resume_required` | 原三元组显式 `--resume`；轮换会重开凭据相关步骤。 |
| `role_key_unknown/role_key_stale/identity_mismatch` | 核原一次性创建/轮换的本人 Key；旧文件人工确认，脚本不覆盖/轮换。 |
| `provision_lock_busy` | 活进程保持，死且过期才自动回收。 |
| 不可解析旧锁 | 人工核进程/目标，不能盲删永久 guard。 |
| preflight 或绑定失败 | 对照原 choice、当前绑定及本人档案路径。 |
| `cli_executable_missing` | 核显式文件路径；检查不启动 CLI。 |

## 4. 迁移与证据边界

旧 `decision_tier` 列/接口、`--decision-tier` 兼容弃用；bridge、身份生成/扫描、K28、adapter closeout、Hall 与角色主显示不再赋予决策/执行身份或据此分派。原任务/快照及人工本机档案不追改。`review_exempt`、`created_by` 发起者主动/被动、target 领取/完成与13键快照保持。

Codex最终684项Python证据集合通过（204切片＋未改376相关＋104投影）；#222另独立重点143项通过、零失败/错误/跳过，不叠加为827；原Node59项未变沿用。junction新回归原221预期失败、修后外部零副作用，真实进程中断/PID/guard恢复通过。

文件symlink因WinError1314未运行；真实junction与形状定序分别验证。无生产配置/数据库重载、真实Key/登录/模型、受管服务、宿主等待或浏览器验证，完整UI及运行器能力继续R1-3/R1-4。
