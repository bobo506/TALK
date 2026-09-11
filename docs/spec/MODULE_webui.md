# MODULE: Web UI

> 所属项目：TALK
> 负责人/Agent：待分配
> 状态：M2 已实现，持续细化中

## 目标

提供浏览器端的单页聊天界面，让人类用户能够登录、查看消息流、发送消息（支持 `@` 定向）、实时接收新消息。

## 负责范围

- 文件：`web/index.html`, `web/app.js`, `web/style.css`, `web/workspace.js`, `web/workspace.css`
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
- 当前主界面与登录页使用浅色 Windows 风格；历史暗色工作台样式仅作为旧实现记录保留
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

## 2026-06-10 WEB-WINDOWS-LIGHT-REDESIGN-1 Addendum

- Web UI 按已确认的 `.plans/talk-webui-redesign-preview.html` 预览稿落地为浅色 Windows 风格：桌面为左侧 Hall 列表、中间消息时间线、右侧成员详情三栏。
- 登录页 / 首次管理员页同步切换到同一套浅色面板、控件、字体层级和按钮样式，避免登录前后视觉断裂。
- 左侧 Hall 列表显示成员数量 `(x)`，并支持按 Hall 名称、ID、成员 ID、昵称或 kind 做本地过滤。
- 右侧成员区改为常驻：上方展示当前 Hall 成员与移除按钮，下方展示所有成员；点击下方成员的 `human / agent` 角色标签可多选筛选上方当前 Hall 成员，未选择时默认显示全部。
- Hall 标题可点击并聚焦右侧重命名表单；当前 Hall 的在线统计保留在标题区，不再重复展示成员列表。
- 当前 Hall 消息搜索保留原 `q` 后端过滤能力，并在正文命中处追加前端 `mark` 高亮。
- Composer 保留“文件 / 发送”主操作；上传文件后继续在输入框上方显示待发送文件名和体积。
- 本轮不改后端 API、不引入前端构建链，继续复用现有 Vanilla JS DOM id 与 Group 成员管理接口。
- 静态资源 cache-busting 版本已更新到 `20260610-windows-redesign`。


## 2026-09-07 UI-WORKSPACE-1：任务 / 角色双栏

- 项目默认进入任务总览。左侧“任务 / 角色”同级切换，右侧随选择变化；旧对话入口收在“对话与房间”。继续使用现有项目/任务/成员/消息 API。
- `workspace.js` 负责列表、角色详情、任务流转与成果读取，`workspace.css` 负责双栏与响应式覆盖；`app.js` 保留鉴权、数据加载、创建、聊天和任务动作。资源版本为 `20260907-density-1`。
- 总览只列根任务，子任务从“分工与流转”进入。完成、失败、取消属于“已结束”，已提交但未收取仍是进行中的工作；“待我处理”也考虑根任务下的子项。
- “任务要求”原样展示创建时的正文，默认折叠。任务详情不再展示内部 ID、attempt、lease、epoch、授权剩余等字段；保留真实检查/测试结论与必要操作。
- 角色来自项目 Agent 索引，职责来自 business_role；工作状态来自实际任务，不推测服务在线。角色详情可看当前/历史参与任务、进入具体任务、预选角色打开原有交办弹窗；不增加角色配置或服务启动接口。
- 任务树加载捕获项目/账号/任务上下文并递增请求序号，响应必须同时匹配根和选中任务；切换后立即清除旧树。树动作验证当前归属，异步动作完成不改变新的用户选择。
- 成果通过既有消息查询读取指定 result_message_id，纯文本呈现并识别撤回；文件成果从完整对话下载。没有 Hall 访问权限时给出可见提示，不绕过原权限。
- 未变化的静默轮询不重建列表/详情，保留焦点、展开内容和提示；任务创建弹窗关闭后恢复入口焦点。完成态隐藏树控制。
- 验证命令：`node --test tests/workspace_ui.test.cjs` 与 `.venv\Scripts\python.exe -m unittest tests.test_task_web_ui -q`。真实页面与响应式验证记录见根目录 `design-qa.md`。

- 验收尺寸调整：宽度至少 701px 时通过根元素 `zoom:0.8` 统一缩小字体、控件与间距，并以相同系数补偿 `vh` 高度；更窄窗口维持原尺寸。浏览器保持 100% 即为新的默认显示密度。


## 2026-09-08 群聊标签导航

- 标签顺序为任务 / 群聊 / 角色，移除 `room-disclosure` 和全局消息流按钮。`room-strip` 改为群聊模式专属面板，只显示 `type != task` 的当前项目或无项目房间。
- `workspaceUI.mode` 区分三种模式；任务完整对话仍属于任务模式，左侧保留主任务列表。普通群聊选中最近或首个有权限的房间；无房间显示空状态，不退回全局收发。
- 新建群聊沿用 `/api/groups`，增加现有字段 `project_id`，创建后通过统一房间导航进入。权限、成员、聊天 API 不变；不删除历史数据或后端全局接口。
- `timelineRevision` 与房间/账号身份保护历史、轮询和分页响应；旧响应不能向当前时间线追加内容。创建弹窗关闭恢复焦点。
- 静态资源版本 `20260908-chats-1`；桌面 80% 默认密度继续有效，手机布局沿用原尺寸。验证记录见 `design-qa.md` 与项目进度。


## 2026-09-08 群聊成员验收修复

- 邀请和添加成员取当前项目 Agent profile 索引与其他真人账号，排除自己和禁用成员；无项目时沿用全局候选。项目未配置的历史 Agent 不再进入邀请候选，历史成员关系不变。
- 自动 bridge 名称缩为 Codex / DeepSeek / Kimi 等，保留人工昵称；候选同名时附加 ID 消歧。@ 只列当前房间可用成员并排除自己，写入实际成员 ID，不引入别名路由协议。
- 右侧只保留“群聊成员”：人数、简短名称、中文职责/在线状态。添加按钮展开原添加表单，管理按钮展开角色设置、移除和删除群聊；服务端权限约束不变。
- 资源版本 `20260908-members-2`，保留桌面 80% 和窄屏原尺寸。详见 design-qa.md。


## 2026-09-10 成果展开与收起

- 任务成果按钮在“查看成果 / 收起成果”之间切换，通过 `aria-controls=task-result-body` 和 `aria-expanded` 标明状态；加载中也允许收起，收起立即隐藏并清空正文。
- 成果状态绑定项目、账号、任务；关闭与上下文变化递增请求序号，迟到的成功/错误响应不得回填。切到无任务项目再返回原任务也保持收起；同一上下文的详情刷新保持用户展开或收起状态。
- 文件、撤回、错误及无权限提示沿用原逻辑。本切片不改完整对话的右侧栏，第二项反馈留待单独验收。
- JS 缓存版本为 `20260910-result-toggle`，CSS 仍为 `20260908-members-2`。32 项 Node 与 2 项 Python 页面契约通过；真实页面记录见 `design-qa.md`。


## 2026-09-11 任务完整对话布局

- 任务完整对话隐藏重复任务详情侧栏，聊天区占用腾出的空间；点击左侧任务返回详情。任务页成果/分工操作、普通群聊成员栏保留。
- Kimi #23开发，DeepSeek #25独立审查PASS：39项Node、2项Python通过；无真实浏览器验证，页面效果待用户验收。
