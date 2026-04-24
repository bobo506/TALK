# MODULE: Web UI

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M2 已实现，持续细化中

## 目标

提供浏览器端的单页聊天界面，让人类用户能够登录、查看消息流、发送消息（支持 `@` 定向）、实时接收新消息。

## 负责范围

- 文件：`web/index.html`, `web/app.js`, `web/style.css`
- 由 FastAPI StaticFiles 托管在 `/` 路径下

## 接口契约

### 对外提供

- 浏览器端用户界面（无其它模块依赖本模块）

### 依赖外部

- `GET /api/members/me` — 用 API Key 获取当前登录身份
- `GET /api/members` — 获取成员列表用于 `@` 自动补全与接收者校验
- `POST /api/messages` — 发送消息
- `GET /api/messages` — 拉取历史/轮询新消息
- `WS /ws?token=` — 实时接收推送
- Tailwind CSS CDN（`https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css`）

## 关键约束

- 纯 Vanilla JS，不使用任何前端框架或构建工具
- 暗色主题（bg-gray-900）
- 消息中的 `@member_id` 需高亮显示
- 被 `@` 的消息整条高亮（左侧蓝色边框）
- 中文界面

## 当前实现现状

- **登录**：输入 API Key → 调 `GET /api/members/me` 自动识别当前成员 → 再调 `GET /api/members` 加载成员列表；localStorage 保存 API Key 并自动登录
- **消息流**：首次历史加载改为获取最新一页消息；页面顶部提供“搜索 / 清除 / 加载更早消息”工具条，通过 `q + before` 组合浏览历史结果；实时/轮询消息继续使用批量 append，减少大批量 DOM 压力
- **实时接收**：WS 连接 + HTTP 轮询 3s 双通道降级；WS 断开后会指数退避自动重连，期间由轮询兜底；WS 额外接收 `presence` 事件维护在线成员状态
- **撤回态**：自己发送的消息会在撤回窗口内显示“撤回”按钮；收到历史撤回态或 WS `revoke` 事件后，消息卡片整体替换为灰色占位“XX 撤回了一条消息”
- **在线状态**：头部保留连接状态徽标；消息区上方新增在线成员条，显示 `在线 x/y` 与成员在线/离线状态
- **提示音**：收到新的非本人消息时播放轻量提示音；历史加载和本人消息不会触发
- **发送**：前端不再决定真实接收者；文本消息与文件附言的开头 mention 由服务端统一解析，前端保留 `@` 自动补全与基础输入提示
- **@ 补全**：输入框在开头 mention 区块中输入 `@` 时弹出下拉框，支持键盘上下选择 + Tab/Enter 补全
- **文件消息**：支持文件选择/拖拽上传、文件气泡、下载按钮、文件附言（`caption`）渲染；若下载返回 `file expired`，文件卡片会标记“已过期”并禁用下载按钮
- **文件卡片元信息**：优先读取消息里的 `filename / size_bytes / mime` 快照，显示友好的文件名和体积/MIME，而不是直接暴露 `file_id`
- **输入/错误反馈**：发送失败时优先回显服务端 `detail`；输入区显示加载失败、发送失败、重连恢复等页内状态提示

## 待改进点

- 未做真正的消息虚拟滚动；当前已支持基于 `before` 的历史分页，但仍是按钮触发式加载更多
- 搜索结果目前只做简单关键词过滤，未做命中高亮
- Tailwind CDN 版本较旧（2.2.19），可升级
- 过期文件状态目前在下载失败后才显式标记，未做预探测
- 提示音目前使用浏览器 Web Audio API 合成短音，未提供单独的静音开关
- 撤回按钮的窗口时长当前由静态页面读取默认值 120 秒；若后续改配置，前端展示逻辑需同步

## 验收标准

- [ ] 输入有效 API Key 后成功登录并显示消息流
- [ ] 发送纯文本消息后，消息实时出现在消息流中
- [ ] `@` 输入后弹出成员补全下拉框，选择后正确填入
- [ ] 被 `@` 的消息左侧显示蓝色高亮边框
- [ ] 刷新页面后历史消息仍然可见
- [ ] 输入关键词后能筛选正文 / 附言 / 文件名命中的消息
- [ ] 点击“加载更早消息”后能在不打断当前位置的前提下向前翻页
- [ ] 搜索模式下仍可继续向前翻页，并可通过“清除”恢复普通历史视图
- [ ] WS 断开后自动重连，重连期间仍可通过轮询继续接收新消息
- [ ] 自己发送的消息在 120 秒窗口内显示“撤回”按钮，超窗后自动消失
- [ ] 收到撤回事件或加载到撤回历史后，消息卡片会切换为灰色占位文案
- [ ] 文本正文与文件附言都只以开头连续 mention 块决定接收者，中途 `@` 不参与路由
- [ ] 文件过期后历史消息卡片仍可显示，但下载按钮会在失败后切换为“已过期”
- [ ] 在线成员条能随 WS presence 事件更新成员在线/离线状态
- [ ] 收到新的非本人消息时会触发一次提示音
## MSG-4 Addendum

- Composer now supports reply mode. Clicking the message action enters a reply state above the input box with sender and preview, plus a cancel button.
- Sending text or file messages includes `reply_to` when reply mode is active.
- Message cards render a compact reply strip when `message.reply_to` is present.
- Clicking a rendered reply strip scrolls to the referenced message if it is currently loaded, then highlights it briefly.
- If the referenced message is revoked, the reply strip changes to `[原消息已撤回]`.
- Frontend runtime constants are now loaded from unauthenticated `GET /api/config` and cached client-side.
- Revoke button visibility uses `revoke_window_sec` from `/api/config`.
- Pending file selection now pre-checks `max_upload_bytes` from `/api/config` before upload.
