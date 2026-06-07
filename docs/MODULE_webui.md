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
- `GET /api/events?token=` — SSE 实时事件流兜底
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
- **实时接收**：优先使用 WS 连接；WS 不可用或断开时会接入 `GET /api/events?token=...` SSE 作为实时兜底，并继续保留 HTTP 轮询 3s 做补漏；WS 恢复后会关闭 SSE；实时通道接收 `message / revoke / presence` 事件维护消息、撤回和在线成员状态
- **撤回态**：自己发送的消息会在撤回窗口内显示“撤回”按钮；收到历史撤回态或实时 `revoke` 事件后，消息卡片整体替换为灰色占位“XX 撤回了一条消息”
- **在线状态**：头部保留连接状态徽标；消息区上方新增在线成员条，显示 `在线 x/y` 与成员在线/离线状态
- **Group / Hall**：顶部工作区新增全局消息流 / Group Hall 切换条；可从 Web UI 创建 Group 并选择初始成员；进入 Hall 后历史、轮询、发送、在线成员条和 `@` 补全都会按当前 Group 作用域运行；human 成员可在 Hall 内展开成员面板，添加成员、调整角色或移除其他成员
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
- [ ] WS 不可用或断开时可切换到 SSE 实时兜底，WS 恢复后回到 WS 通道
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

## 2026-04-24 DOC-1 / SETUP-1 UX Addendum

- 首次管理员引导页已切换为中文提示文案，明确区分 `管理员 ID`、`昵称` 与 `登录密钥`，并提示管理员 ID 必须使用 `human:*` 格式
- `登录密钥` 输入框默认隐藏内容（`password`），避免新手误以为需要自己设计一串复杂字符串
- 表单新增浏览器端 `自动生成` 按钮，使用 `crypto.getRandomValues()` 生成 32 字节 base64url 登录密钥
- 表单新增显隐切换与一键复制按钮；若内嵌浏览器拒绝剪贴板写入，会退回到选中密钥并提示用户按 `Ctrl+C` 手动复制
- 快速启动文档已拆分为家庭用户视角与 Agent 开发者视角两个独立入口，避免把 Docker 新手和 SDK 开发者混在一份说明里

## 2026-05-14 Chat UI Review Addendum

- 聊天主界面残留英文文案已改为中文，包括搜索工具条、退出按钮、文件按钮、发送按钮、拖拽文件提示、移除文件与取消回复。
- 搜索工具条视觉层级已收敛：搜索按钮使用主色，清除与加载更早消息使用次级深色按钮。
- 底部输入区已改为明确的 composer 容器，文件按钮、输入框、发送按钮通过背景色、边框和主色按钮区分。
- 空消息区新增中文空状态，说明该区域是消息时间线，避免空白区域看起来像未知框。

## 2026-05-14 Visual Polish Addendum

- 登录页与首次管理员页已统一为深色工作台风格，加入品牌标识、中文加载/登录文案、边框卡片、明确的主/次按钮和聚焦态。
- 聊天主界面头部、在线成员条、搜索工具条、消息时间线与底部 composer 已统一边界、背景、按钮层级和消息气泡样式。
- 桌面宽度下搜索输入与操作按钮保持同一工具条层级；窄屏下工具条和 composer 会换行/收缩，避免长文本和输入区横向溢出。
- 当前视觉验证使用本机 Chrome headless 截图完成：真实登录页桌面/窄屏可渲染，聊天主界面用同一份 CSS 的临时预览 HTML 验证桌面和 500px 窄屏布局。

## 2026-05-14 WEB-VISUAL-2 Addendum

- 按 `image_gen` 视觉稿方向继续收敛真实页面布局，但未新增左侧会话/频道栏，避免在 Group/Hall 数据模型落地前制造假功能入口。
- 聊天页结构改为 `header + workspace-tools + messages + composer`：在线成员与历史搜索统一进入顶部工作台工具区，消息时间线和输入区作为同一聊天工作区的上下两端。
- `workspace-tools` 现在承载在线成员、搜索、清除、加载更早消息与历史状态，视觉上形成一个整体控制面板，而不是两条割裂横条。
- 静态资源 cache-busting 版本已更新到 `20260514-visual-2`，便于浏览器刷新到本轮布局。

## 2026-05-14 WEB-GROUP-1 Addendum

- 顶部 `workspace-tools` 新增 `room-strip`：提供“全局”入口、可进入的 Group Hall 列表、刷新按钮和“新建 Group”面板。
- 登录后 Web UI 会调用 `GET /api/groups`，恢复当前用户上次进入的 Group；如果该用户已不在 Group 内，则回退到全局消息流。
- 切换到 Group Hall 后，历史加载和轮询都会携带 `group_id`；WebSocket 实时消息也只追加当前 active room 的消息，避免其它 Group 或全局消息污染当前时间线。
- 文本和文件发送会自动带上当前 `group_id`；切换 room 会清空当前回复目标，避免跨 Group 回复。
- Group Hall 内 `@` 补全和在线成员条只展示当前 Group 成员；placeholder 明确提示 Hall 内 `@` 是提醒，不限制可见性。
- 新建 Group 面板支持名称、可选 ID、可选描述和初始成员选择；创建成功后自动进入新 Hall。
- 静态资源 cache-busting 版本已更新到 `20260514-groups-ui`。

## 2026-05-15 WEB-GROUP-MEMBERS-1 Addendum

- Group Hall 内新增“成员”面板；进入某个 Hall 后可展开查看当前 Group 成员及角色。
- human 成员可通过 Web UI 添加未入组成员、调整 `owner / moderator / member` 角色，并移除其他成员。
- Agent 成员保留只读成员列表；成员管理仍由服务端权限控制，前端只做可用性收敛。
- 成员变更成功后，房间描述、在线成员条、`@` 补全和成员面板会立即使用服务端返回的新 Group 快照刷新。
- 静态资源 cache-busting 版本已更新到 `20260515-group-members`。

## 2026-05-16 WEB-SSE-UI-1 Addendum

- Web UI 已接入 `GET /api/events?token=...` SSE 事件流作为实时兜底。
- 浏览器优先使用 WebSocket；如果当前浏览器不支持 WebSocket，或 WebSocket 断开/报错，会打开 SSE 并显示 `SSE 已连接 / SSE 兜底中 / SSE 重连中 · 轮询兜底` 状态。
- WebSocket 恢复后会主动关闭 SSE，避免同一浏览器同时占用两条实时通道。
- SSE 与 WS 共用前端实时事件处理逻辑，统一处理 `message / revoke / presence`，`ping` 事件只用于保持连接。
- HTTP 轮询仍保留为断线与事件缺口补漏通道，不承担在线成员状态。
- 静态资源 cache-busting 版本已更新到 `20260516-sse-ui`。

## 2026-05-25 WEB-REPLY-COMPACT-1 Addendum

- 当两个角色互相回复时，消息卡片里的引用条改为紧凑文本：`A 回复 B`，不再展开对方完整预览，减少多 Agent 讨论时的纵向占用。
- 若当前消息是发给 B、但引用的是第三方 C 的内容，前端仍保留原来的引用框与预览，避免丢失第三方上下文。
- 紧凑引用仍保留点击跳转能力；当被引用消息已加载时，点击 `A 回复 B` 会滚动并高亮原消息。
- 静态资源 cache-busting 版本已更新到 `20260525-reply-compact`。

## 2026-06-07 WEB-WORKBENCH-REDESIGN-1 Addendum

- Web UI 第一版 Product Design 重设计已落地：页面从“顶部工具条 + 聊天流”改为“左侧 Hall 控制台 + 右侧消息时间线”的工作台结构。
- 左侧 `Hall 控制台` 聚合全局 / Group Hall 切换、新建 Group、成员面板和在线成员状态；右侧保留历史搜索、消息流和底部 composer。
- 本轮只调整信息架构与视觉层级，不改变现有 API、DOM id 行为契约或 Vanilla JS 技术约束。
- 视觉系统改为中性暗色工作台，辅以 teal / indigo / amber 状态色；桌面为双栏，窄屏自动切为单列并避免横向溢出。
- highlight.js 浏览器脚本路径改用 `highlightjs/cdn-release@11.11.1/build/highlight.min.js`，避免旧 `lib/common.min.js` 在浏览器中触发 `require is not defined`。
- 静态资源 cache-busting 版本已更新到 `20260607-workbench-redesign`。
