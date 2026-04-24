# MODULE: 文件上传下载

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M2 已实现，已补上传链路与 sha256 秒传自动化测试

## 目标

实现文件包（zip、tar.gz、单文件等）的上传和下载功能，支持 Agent 之间交换代码包。上传后返回 `file_id`，通过消息模块发送 `type=file` 的消息引用该 `file_id`，接收方按 `file_id` 下载。

## 负责范围

- 文件：`server/routes/files.py`
- 端点：
  - `POST /api/files` — 上传文件（multipart/form-data）
  - `GET /api/files/{file_id}` — 下载文件（二进制流）
- 存储目录：`storage/files/`

## 接口契约

### 对外提供

- **`POST /api/files`**：接收 multipart 上传，先落临时文件并计算 sha256；命中已存在实体时按 A 方案新建一条 `files` 记录并复用既有 `path`，未命中时写入新实体；返回 `{file_id, filename, size_bytes}`
- **`GET /api/files/{file_id}`**：返回文件二进制流（StreamingResponse），附 `Content-Disposition` header

### 依赖外部

- `server/auth.py` — `get_current_member` 鉴权
- `server/models.py` — `File` ORM 模型（已定义，含 `id, filename, mime, size_bytes, sha256, uploader_id, path, created_at`）
- `server/db.py` — `get_session`, `STORAGE_DIR`, `UPLOAD_MAX_MB`, `FILE_RETENTION_DAYS`
- `aiofiles` — 异步文件写入（已在 requirements.txt）

## 关键约束

- 单文件大小上限：`config.toml` 的 `upload_max_mb`（默认 100 MB）
- 文件实体存储路径：`storage/files/<file_id>`（不保留原始文件名，避免路径注入）
- 必须计算并存储 `sha256`，接收方可校验完整性
- 两个端点都需要鉴权
- **秒传方案**：采用 A 方案，允许多条 `files` 记录共享同一实体路径；因此过期清理必须以“该路径是否仍有未过期引用”为准，而不是按单条记录直接删盘
- **文件消息约定**：调用方上传文件后，发 `type=file` 消息时至少提供 `file_id`；消息模块会从 files 表冻结 `filename / size_bytes / mime` 到消息快照（详见 MODULE_messages）
- **保留策略**：消息快照永久保留；文件实体按 `config.toml` 中的 `file_retention_days` 过期清理，`0` 表示永久保留

## 当前实现现状

- `POST /api/files` 已实现：multipart 接收 → 临时文件落盘 → sha256 计算 → 按 sha256 查重
- 秒传命中时采用 A 方案：删除临时文件，创建新的 `files` 记录并复用既有 `path`；每次上传仍会生成新的 `file_id`，保留当前上传者的 `uploader_id / filename / mime`
- 秒传未命中时沿用原路径策略：把临时文件移动到 `storage/files/<file_id>`，并写入新的 `files` 记录
- 文件表中的 `sha256` 已建立索引，便于秒传查重
- `GET /api/files/{file_id}` 已实现：查表 → 文件存在性校验 → StreamingResponse 下载；若文件记录已因保留期清理删除，但历史消息仍引用该 `file_id`，返回 `404 file expired`
- 上传响应返回 `file_id / filename / size_bytes`
- 文件消息的元信息快照由消息模块在发送时从 `files` 表提取，不需要前端再额外请求文件详情接口
- 旧历史文件消息在服务启动时会尝试根据 `file_id` 从 `files` 表回填快照字段
- 服务启动时会按 `file_retention_days` 清理过期文件：先删除过期 `files` 记录，再仅在该 `path` 不再被任何未过期记录引用时删除磁盘实体；历史消息快照不受影响
- 已补自动化测试：`tests/test_files.py` 覆盖过期文件清理、`GET /api/files/{file_id}` 对 `file expired / file not found` 的区分，以及上传成功落盘/元数据落库、上传鉴权拒绝、超限文件拒绝、上传后文件消息快照冻结、首传 dedup miss、二次同内容 dedup hit、共享路径场景下的清理保护

## 待改进点

- 文件卡片当前展示使用的是消息快照中的 `size_bytes / mime`，如后续需要更丰富信息（哈希、上传者、上传时间），再决定是否新增独立文件详情接口
- MIME 类型当前使用 `UploadFile.content_type` 或 `mimetypes` 推断，精度有限
- 当前只在服务启动时执行过期清理，不做后台定时任务
- 若后续需要更细粒度策略，再评估是否引入“实体表 + 引用表”的正式建模，避免共享路径语义长期堆叠在 `files` 单表上

## 验收标准

- [x] `POST /api/files` 上传 zip 文件成功，返回 `{file_id, filename, size_bytes}`
- [x] 上传的文件存储在 `storage/files/<file_id>`
- [x] 数据库 `files` 表记录了 filename, mime, size_bytes, sha256, uploader_id
- [x] `GET /api/files/{file_id}` 返回原始文件二进制流，sha256 与上传时一致
- [x] 超过 `upload_max_mb` 的文件被拒绝（413 或 400）
- [x] 非法 `file_id` 返回 404
- [x] 与消息模块联动：发送 `type=file` 消息时提供 `file_id` 后，消息返回中携带冻结后的 `filename / size_bytes / mime`
- [x] `file_retention_days > 0` 时，服务启动会清理过期文件实体与 `files` 记录，但保留历史消息快照
- [x] 过期文件被历史消息引用时，下载返回 `404` 且 `detail=file expired`
- [x] 同一内容文件重复上传时，磁盘上只保留一份实体
- [x] 秒传命中时有明确日志标记（`talk.files` dedup hit/miss）
- [x] 秒传场景下，若仍有未过期引用，清理逻辑不会误删共享实体
