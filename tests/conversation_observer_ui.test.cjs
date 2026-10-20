/* 285 管理账号只读旁观的前端接线测试：vm 加载真实 web/workspace.js + web/app.js，
   通过可编程 fetch 桩驱动真实 doLoginV2 / loadMyPermissions / canEnterGroup /
   setActiveGroup / openTaskHall / showWorkspaceResult / sendMessage 等函数。
   不把 canEnterGroup mock 成永远 true；权限只来自 /api/members/me/permissions 的已认证响应。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const webDir = path.join(__dirname, '..', 'web');
const workspaceSource = fs.readFileSync(path.join(webDir, 'workspace.js'), 'utf8');
const appSource = fs.readFileSync(path.join(webDir, 'app.js'), 'utf8');

const MEMBERS = [
  { id: 'human:bobo', kind: 'human', display_name: 'bobo' },
  { id: 'human:carol', kind: 'human', display_name: 'carol' },
  { id: 'agent:AI1', kind: 'agent', display_name: 'AI1' },
];
const PROJECTS = [{ project_id: 'p1', display_name: '项目一' }];
// bobo/carol 都不是 group:lab / group:task-1 的成员；group:mine 包含 carol。
const LAB = { id: 'group:lab', name: 'Lab', description: '', type: 'free', project_id: 'p1', members: [{ member_id: 'agent:AI1', role: 'owner' }] };
const TASK_HALL = { id: 'group:task-1', name: 'Task Hall', description: '', type: 'task', project_id: 'p1', members: [{ member_id: 'agent:AI1', role: 'owner' }] };
const MINE = { id: 'group:mine', name: 'Mine', description: '', type: 'free', project_id: 'p1', members: [{ member_id: 'agent:AI1', role: 'owner' }, { member_id: 'human:carol', role: 'member' }] };
const GROUPS = [LAB, TASK_HALL, MINE];

function fakeEl(tag = 'div') {
  const classes = new Set();
  return {
    tagName: tag.toUpperCase(),
    children: [],
    dataset: {},
    style: {},
    attrs: {},
    handlers: {},
    value: '',
    textContent: '',
    innerHTML: '',
    className: '',
    placeholder: '',
    disabled: false,
    checked: false,
    type: '',
    title: '',
    scrollTop: 0,
    scrollHeight: 0,
    selectionStart: 0,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : Boolean(force);
        if (on) classes.add(name); else classes.delete(name);
        return on;
      },
      contains: (name) => classes.has(name),
    },
    addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); },
    removeEventListener() {},
    appendChild(child) { this.children.push(child); return child; },
    append(...items) { this.children.push(...items); },
    prepend(...items) { this.children.unshift(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    insertBefore(child) { this.children.unshift(child); return child; },
    remove() {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return this.attrs[name]; },
    removeAttribute(name) { delete this.attrs[name]; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest() { return null; },
    contains() { return false; },
    focus() {}, select() {}, click() {}, scrollIntoView() {}, setSelectionRange() {}, reset() {},
  };
}

function makeDocument() {
  const byId = new Map();
  const bySelector = new Map();
  const created = [];
  return {
    created,
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, fakeEl());
      return byId.get(id);
    },
    createElement(tag) {
      const el = fakeEl(tag);
      created.push(el);
      return el;
    },
    createTextNode(text) { return { nodeType: 3, textContent: String(text) }; },
    createDocumentFragment() { return fakeEl('fragment'); },
    addEventListener() {},
    querySelector(selector) {
      if (!bySelector.has(selector)) bySelector.set(selector, fakeEl());
      return bySelector.get(selector);
    },
    querySelectorAll() { return [] },
    body: fakeEl('body'),
  };
}

function memoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
    _map: map,
  };
}

// routes: [prefix, responder]；responder 可以是 {status, data}、函数 (url, opts) => {status, data}，或 'pend'。
function makeFetch(routes) {
  const calls = [];
  const pendings = [];
  const fetchFn = (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase();
    calls.push({ method, url, opts });
    const entry = routes.find(([prefix]) => url.startsWith(prefix));
    const responder = entry && entry[1];
    if (responder === 'pend') {
      return new Promise((resolve) => pendings.push({ url, method, resolve }));
    }
    const result = typeof responder === 'function' ? responder(url, opts) : responder;
    if (!result) {
      return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: 'not found' }), headers: { get: () => null } });
    }
    const status = result.status === undefined ? 200 : result.status;
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: async () => result.data,
      headers: { get: () => null },
    });
  };
  return { fetchFn, calls, pendings };
}

function baseRoutes(permissions) {
  return [
    ['/api/setup/status', { data: { needs_setup: false } }],
    ['/api/members/me/permissions', permissions],
    ['/api/members/me', (url, opts) => {
      const key = opts.headers && opts.headers['X-API-Key'];
      return { data: key === 'carol-key' ? MEMBERS[1] : MEMBERS[0] };
    }],
    ['/api/members', { data: MEMBERS }],
    ['/api/config', { data: {} }],
    ['/api/projects', (url) => (url.includes('/agents') ? { data: [] } : { data: PROJECTS })],
    ['/api/tasks', { data: [] }],
    ['/api/groups', { data: GROUPS }],
    ['/api/messages', (url, opts) => (opts.method === 'POST'
      ? { status: 201, data: { id: 900, type: 'text', content: 'ok' } }
      : { data: [] })],
  ];
}

function harness(routes) {
  const document = makeDocument();
  const localStorage = memoryStorage();
  const sessionStorage = memoryStorage();
  const fetchStub = makeFetch(routes);
  const context = vm.createContext({
    console,
    document,
    localStorage,
    sessionStorage,
    location: { protocol: 'http:', host: 'sandbox.local', reload() {} },
    fetch: fetchStub.fetchFn,
    window: { addEventListener() {} },
    navigator: {},
    URLSearchParams,
    setInterval: () => 1,
    clearInterval() {},
    setTimeout: () => 0,
    clearTimeout() {},
    requestAnimationFrame: () => {},
  });
  vm.runInContext(workspaceSource, context, { filename: 'workspace.js' });
  vm.runInContext(appSource, context, { filename: 'app.js' });
  return { context, document, fetchStub, localStorage };
}

const run = (context, code) => vm.runInContext(code, context);
const observerPermissions = { data: { member_id: 'human:bobo', can_view_all_conversations: true } };
const plainPermissions = { data: { member_id: 'human:carol', can_view_all_conversations: false } };

function loginAs(context, key) {
  return run(context, `doLoginV2(${JSON.stringify(key)})`);
}

function roomButtons(document) {
  return document.created.filter((el) => String(el.className).includes('group-chat-row'));
}

test('观察者登录后可进入未加入的群聊，列表按钮不再禁用且标注只读', async () => {
  const { context, document } = harness(baseRoutes(observerPermissions));
  await loginAs(context, 'bobo-key');
  assert.equal(run(context, 'canViewAllConversations'), true);
  assert.equal(run(context, 'canEnterGroup("group:lab")'), true);
  assert.equal(run(context, 'canEnterGroup("group:task-1")'), true);

  document.created.length = 0;
  run(context, 'workspaceUI.mode = "chats"; renderRoomStrip()');
  const lab = roomButtons(document).find((el) => el.children[0] && el.children[0].textContent === 'Lab');
  assert.ok(lab, '群列表应渲染 Lab 房间');
  assert.equal(lab.disabled, false);
  assert.match(lab.children[1].textContent, /未加入（只读）/);
  assert.match(lab.title, /可只读查看/);
});

test('普通成员无权限时群列表仍禁用并提示尚未加入', async () => {
  const { context, document } = harness(baseRoutes(plainPermissions));
  await loginAs(context, 'carol-key');
  assert.equal(run(context, 'canViewAllConversations'), false);
  assert.equal(run(context, 'canEnterGroup("group:lab")'), false);
  assert.equal(run(context, 'canEnterGroup("group:mine")'), true);

  document.created.length = 0;
  run(context, 'workspaceUI.mode = "chats"; renderRoomStrip()');
  const lab = roomButtons(document).find((el) => el.children[0] && el.children[0].textContent === 'Lab');
  assert.ok(lab);
  assert.equal(lab.disabled, true);
  assert.match(lab.children[1].textContent, /尚未加入/);
});

test('旧服务 404 / 缺字段 / 成员不匹配都不授予旁观权限', async () => {
  for (const permissions of [
    undefined, // 路由不存在 → 404
    { status: 404, data: { detail: 'not found' } },
    { data: {} },
    { data: { member_id: 'human:bobo' } },
    { data: { member_id: 'human:carol', can_view_all_conversations: true } },
    { data: { member_id: 'human:bobo', can_view_all_conversations: 'yes' } },
  ]) {
    const routes = baseRoutes(permissions).filter(([prefix]) => permissions !== undefined || prefix !== '/api/members/me/permissions');
    const { context } = harness(routes);
    await loginAs(context, 'bobo-key');
    assert.equal(run(context, 'canViewAllConversations'), false, JSON.stringify(permissions));
    assert.equal(run(context, 'canEnterGroup("group:lab")'), false, JSON.stringify(permissions));
  }
});

test('只读旁观下输入/发送/附件/回复入口全部关闭且函数调用被守卫', async () => {
  const { context, document, fetchStub } = harness(baseRoutes(observerPermissions));
  await loginAs(context, 'bobo-key');
  run(context, 'setActiveGroup("group:lab")');

  const msgInput = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const attachBtn = document.getElementById('attach-btn');
  assert.equal(msgInput.disabled, true);
  assert.equal(sendBtn.disabled, true);
  assert.equal(attachBtn.disabled, true);
  assert.match(msgInput.placeholder, /只读查看/);
  assert.match(document.getElementById('composer-status').textContent, /只读查看/);

  msgInput.value = '不应发出';
  await run(context, 'sendMessage()');
  run(context, 'pendingFile = { name: "a.txt", size: 10 }');
  await run(context, 'sendFileMessage()');
  const posts = fetchStub.calls.filter((call) => call.method === 'POST' && call.url.startsWith('/api/messages'));
  assert.equal(posts.length, 0, '只读旁观不应产生任何发送请求');

  run(context, 'pendingFile = null');
  run(context, 'setPendingFile({ name: "b.txt", size: 10 })');
  assert.equal(run(context, 'pendingFile'), null, '只读旁观不能添加附件');

  run(context, "activateReplyTarget({ id: 5, from: 'agent:AI1', type: 'text', content: 'x' })");
  assert.equal(run(context, 'activeReplyTo'), null, '只读旁观不能发起回复');
});

test('已有成员的发言路径不受只读逻辑影响', async () => {
  const { context, document, fetchStub } = harness(baseRoutes(plainPermissions));
  await loginAs(context, 'carol-key');
  run(context, 'setActiveGroup("group:mine")');

  const msgInput = document.getElementById('msg-input');
  assert.equal(msgInput.disabled, false);
  assert.equal(document.getElementById('send-btn').disabled, false);
  assert.equal(run(context, 'activeGroupReadOnly()'), false);

  msgInput.value = '成员正常发言';
  await run(context, 'sendMessage()');
  const posts = fetchStub.calls.filter((call) => call.method === 'POST' && call.url.startsWith('/api/messages'));
  assert.equal(posts.length, 1);
  assert.match(posts[0].opts.body, /group:mine/);
});

test('观察者可从未加入的 Task Hall 查看完整对话与成果', async () => {
  const task7 = { id: 7, hall_group_id: 'group:task-1', result_message_id: 42, title: '任务7', content: '内容', workflow_status: 'submitted', status: 'succeeded', created_by: 'human:alice', target_member_id: 'agent:AI1', updated_at: '2026-10-20T00:00:00Z' };
  const routes = baseRoutes(observerPermissions).map(([prefix, responder]) => {
    if (prefix === '/api/messages') {
      return [prefix, () => ({ data: [{ id: 42, type: 'text', content: '成果正文', from_id: 'agent:AI1', created_at: '2026-10-20T00:00:00Z' }] })];
    }
    if (prefix === '/api/tasks') {
      return [prefix, (url) => (url.includes('/tree') ? { data: [] } : { data: [task7] })];
    }
    return [prefix, responder];
  });
  const { context, document } = harness(routes);
  await loginAs(context, 'bobo-key');

  await run(context, 'openTaskHall({ id: 7, hall_group_id: "group:task-1" })');
  assert.equal(run(context, 'activeGroupId'), 'group:task-1');
  assert.equal(run(context, 'workspaceUI.mode'), 'tasks');
  // 等待 setActiveGroup 内部的任务树加载/详情重绘落定，避免其异步清理覆盖成果面板。
  for (let i = 0; i < 10; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setImmediate(resolve));
  }

  context.resultTask = { id: 7, hall_group_id: 'group:task-1', result_message_id: 42 };
  await run(context, 'showWorkspaceResult(resultTask)');
  assert.equal(document.getElementById('task-result-body').textContent, '成果正文');
});

test('非观察者查看完整对话与成果仍被成员规则阻挡', async () => {
  const { context, document } = harness(baseRoutes(plainPermissions));
  await loginAs(context, 'carol-key');

  await run(context, 'openTaskHall({ id: 7, hall_group_id: "group:task-1" })');
  assert.equal(run(context, 'activeGroupId'), null);
  assert.match(document.getElementById('task-details-error').textContent, /尚未加入/);

  context.resultTask = { id: 7, hall_group_id: 'group:task-1', result_message_id: 42 };
  await run(context, 'showWorkspaceResult(resultTask)');
  assert.match(document.getElementById('task-details-error').textContent, /尚未加入/);
});

test('换账号后旁观能力清零并重新加载，不继承旧响应', async () => {
  const routes = baseRoutes(observerPermissions);
  const { context, fetchStub } = harness(routes);
  await loginAs(context, 'bobo-key');
  assert.equal(run(context, 'canViewAllConversations'), true);

  // 换成 carol：/me 返回 carol，权限接口 404。
  routes.length = 0;
  routes.push(...baseRoutes({ status: 404, data: { detail: 'not found' } })
    .map(([prefix, responder]) => (prefix === '/api/members/me'
      ? [prefix, { data: MEMBERS[1] }]
      : [prefix, responder])));
  await loginAs(context, 'carol-key');
  assert.equal(run(context, 'myId'), 'human:carol');
  assert.equal(run(context, 'canViewAllConversations'), false);
  assert.equal(run(context, 'canEnterGroup("group:lab")'), false);
  assert.ok(fetchStub.calls.some((call) => call.url.startsWith('/api/members/me/permissions')));
});

test('在途权限请求的迟到回包在当前账号已变化时不生效', async () => {
  const routes = baseRoutes(observerPermissions);
  const { context, fetchStub } = harness(routes);
  await loginAs(context, 'bobo-key');
  assert.equal(run(context, 'canViewAllConversations'), true);

  // 换成挂起的权限响应，模拟请求在途时账号已切换。
  routes.splice(0, routes.length, ...baseRoutes('pend'));
  run(context, 'canViewAllConversations = false');
  const pendingPromise = run(context, 'loadMyPermissions()');
  run(context, "myId = 'human:carol'");
  assert.equal(fetchStub.pendings.length, 1);
  fetchStub.pendings[0].resolve({
    ok: true,
    status: 200,
    json: async () => ({ member_id: 'human:bobo', can_view_all_conversations: true }),
    headers: { get: () => null },
  });
  await pendingPromise;
  // 账号已切走，迟到的成功响应不得授权。
  assert.equal(run(context, 'canViewAllConversations'), false);
});

test('登录恢复：观察者按存储恢复未加入的房间，普通成员不恢复', async () => {
  const first = harness(baseRoutes(observerPermissions));
  first.localStorage.setItem('talk_active_group_id:human:bobo', 'group:lab');
  await loginAs(first.context, 'bobo-key');
  assert.equal(run(first.context, 'activeGroupId'), 'group:lab');

  const second = harness(baseRoutes(plainPermissions));
  second.localStorage.setItem('talk_active_group_id:human:carol', 'group:lab');
  await loginAs(second.context, 'carol-key');
  assert.equal(run(second.context, 'activeGroupId'), null);
});


const response = (allowed) => ({ok:true,status:200,json:async()=>({member_id:'human:bobo',can_view_all_conversations:allowed})});

test('logout clears observer capability synchronously even if navigation is delayed', async () => {
  const {context,document}=harness(baseRoutes(observerPermissions));
  await loginAs(context,'bobo-key');
  document.getElementById('logout-btn').handlers.click[0]();
  assert.equal(run(context,'canViewAllConversations'),false);
  assert.equal(run(context,'canEnterGroup("group:lab")'),false);
});

test('permissions response after logout cannot restore observer capability',async()=>{
  const {context,document}=harness(baseRoutes(observerPermissions));
  await loginAs(context,'bobo-key');
  let resolve;
  context.fetch=()=>new Promise(r=>{resolve=r;});
  const pending=run(context,'loadMyPermissions()');
  document.getElementById('logout-btn').handlers.click[0]();
  resolve(response(true)); await pending;
  assert.equal(run(context,'canViewAllConversations'),false);
});

test('newer permission response wins for the same key and member',async()=>{
  const {context}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  const resolvers=[]; context.fetch=()=>new Promise(r=>resolvers.push(r));
  const first=run(context,'loadMyPermissions()'); const second=run(context,'loadMyPermissions()');
  resolvers[1](response(false)); await second;
  resolvers[0](response(true)); await first;
  assert.equal(run(context,'canViewAllConversations'),false);
});

test('old failed request cannot clear a newer permission result',async()=>{
  const {context}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  let reject; context.fetch=()=>new Promise((r,j)=>{reject=j;});
  const old=run(context,'loadMyPermissions()');
  context.fetch=()=>Promise.resolve(response(true)); await run(context,'loadMyPermissions()');
  reject(new Error('synthetic old request failure')); await old;
  assert.equal(run(context,'canViewAllConversations'),true);
});

test('login failing after permission fetch does not retain observer capability',async()=>{
  const routes=baseRoutes(observerPermissions).map(([prefix,responder])=>prefix==='/api/members'?[prefix,{status:500,data:{}}]:[prefix,responder]);
  const {context}=harness(routes); assert.equal(await loginAs(context,'bobo-key'),false);
  assert.equal(run(context,'canViewAllConversations'),false);
});

test('read-only timeline does not expose a usable Reply action',async()=>{
  const {context}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  run(context,'setActiveGroup("group:lab")');
  const actions=run(context,'renderMessageActions({id:11,from:"agent:AI1",group_id:"group:lab",type:"text",content:"x",created_at:"2026-10-20T00:00:00Z"})');
  const replies=actions?actions.children.filter(el=>el.textContent==='回复'):[];
  assert.ok(replies.every(el=>el.disabled===true),'Reply must be absent or disabled while observing');
});

test('completion of an earlier send cannot re-enable a read-only room composer',async()=>{
  const {context,document}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  run(context,'groups.find(g=>g.id==="group:mine").members.push({member_id:"human:bobo",role:"member"});setActiveGroup("group:mine")');
  document.getElementById('msg-input').value='member send';
  const original=context.fetch; let resolve;
  context.fetch=(url,opts={})=>(url==='/api/messages'&&opts.method==='POST')?new Promise(r=>{resolve=r;}):original(url,opts);
  const sending=run(context,'sendMessage()');
  run(context,'setActiveGroup("group:lab")');
  assert.equal(document.getElementById('send-btn').disabled,true);
  resolve({ok:true,status:201}); await sending;
  assert.equal(document.getElementById('send-btn').disabled,true);
});

test('read-only observer cannot revoke its own earlier message through the UI',async()=>{
  const {context,fetchStub}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  run(context,'setActiveGroup("group:lab")');
  context.ownMessage={id:13,from:'human:bobo',type:'text',content:'old member message',group_id:'group:lab',created_at:new Date().toISOString()};
  const actions=run(context,'renderMessageActions(ownMessage)');
  assert.ok(!actions || actions.children.every(el=>el.disabled));
  await run(context,'revokeMessage(13)');
  assert.equal(fetchStub.calls.filter(c=>c.method==='POST'&&c.url.includes('/revoke')).length,0);
});

test('an attachment upload finishing after room switch is discarded without an error or message POST',async()=>{
  const {context,fetchStub}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  run(context,'groups.find(g=>g.id==="group:mine").members.push({member_id:"human:bobo",role:"member"});setActiveGroup("group:mine"); pendingFile={name:"old.txt",size:1}');
  context.FormData=class { append(){} };
  const errors=[]; context.console={...console,error:e=>errors.push(e)};
  const original=context.fetch; let resolve;
  context.fetch=(url,opts={})=>url==='/api/files'?new Promise(r=>{resolve=r;}):original(url,opts);
  const sending=run(context,'sendFileMessage()');
  run(context,'setActiveGroup("group:lab")');
  resolve({ok:true,json:async()=>({file_id:'uploaded-old'})}); await sending;
  assert.deepEqual(errors,[]);
  assert.equal(fetchStub.calls.filter(c=>c.method==='POST'&&c.url==='/api/messages').length,0);
});

test('a stale login identity response cannot replace the current account',async()=>{
  const {context}=harness(baseRoutes(observerPermissions));
  const original=context.fetch; let resolve;
  context.fetch=(url,opts={})=>url==='/api/members/me'&&opts.headers['X-API-Key']==='bobo-key'?new Promise(r=>{resolve=r;}):original(url,opts);
  const old=loginAs(context,'bobo-key');
  await loginAs(context,'carol-key');
  resolve({ok:true,json:async()=>({id:'human:bobo',kind:'human'})}); await old;
  assert.equal(run(context,'myId'),'human:carol');
  assert.equal(run(context,'apiKey'),'carol-key');
  assert.equal(run(context,'canViewAllConversations'),false);
});

function controlTask(overrides={}){
  return {id:285,root_task_id:285,project_id:'p1',hall_group_id:'group:task-1',created_by:'agent:AI1',target_member_id:'agent:AI1',status:'running',workflow_status:'in_progress',control_status:'active',may_delegate:false,title:'Task',content:'Work',...overrides};
}
function showControls(context,document,root,{task=root,testGate=false}={}){
  context.fixtureTask=task; context.fixtureRoot=root; context.fixtureGate=testGate;
  document.getElementById('task-details-actions').children=[];
  run(context,'workspaceUI.mode="tasks"; activeProjectId="p1"; blackboardOpen=true; selectedTaskId=fixtureTask.id; projectTasks=[fixtureTask]; selectedTaskTree={root:fixtureRoot,tasks:[fixtureRoot,fixtureTask],relations:[],test_gate:{satisfied:fixtureGate}};renderTaskDetailsPanel()');
  return document.getElementById('task-details-actions').children;
}

test('one stop control sends pause-tree for the root and preserves child scope',async()=>{
  const routes=baseRoutes(observerPermissions).map(([prefix,responder])=>prefix==='/api/tasks'?[prefix,(url,opts)=>opts.method==='POST'?{data:{root:controlTask({control_status:'paused'}),tasks:[],relations:[]}}:{data:[]}]:[prefix,responder]);
  const {context,document,fetchStub}=harness(routes); await loginAs(context,'bobo-key');
  const actions=showControls(context,document,controlTask(),{task:controlTask({id:286,parent_task_id:285})});
  const stop=actions.find(el=>el.textContent==='中止任务'); assert.ok(stop);
  assert.match(stop.title,/子任务/);
  assert.ok(actions.every(el=>!['暂停整棵任务树','授权继续一批','在风险边界暂停','终止整棵任务树'].includes(el.textContent)));
  await stop.handlers.click[0]();
  const posts=fetchStub.calls.filter(c=>c.method==='POST');
  assert.equal(posts.length,1); assert.equal(posts[0].url,'/api/tasks/285/pause-tree');
});

test('stopped and awaiting-human tasks expose no resume or extra termination action',async()=>{
  const {context,document,fetchStub}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  for(const control_status of ['paused','awaiting_human']){
    const root=controlTask({control_status,checkpoint_reason:'manual_pause'});
    const actions=showControls(context,document,root);
    assert.ok(actions.every(el=>!['中止任务','授权继续一批','在风险边界暂停','终止整棵任务树'].includes(el.textContent)));
    context.noticeTask=root; context.noticeTree={root};
    assert.match(run(context,'workspaceTaskNotice(noticeTask,noticeTree)'),control_status==='paused'?/已中止/:/等待人工/);
  }
  assert.equal(fetchStub.calls.filter(c=>c.method==='POST').length,0);
});

test('milestone acceptance remains human-only and requires a satisfied test gate',async()=>{
  const {context,document}=harness(baseRoutes(observerPermissions)); await loginAs(context,'bobo-key');
  const root=controlTask({control_status:'awaiting_human',checkpoint_reason:'milestone'});
  assert.ok(!showControls(context,document,root).some(el=>el.textContent==='人工验收通过'));
  assert.ok(showControls(context,document,root,{testGate:true}).some(el=>el.textContent==='人工验收通过'));
  run(context,'myId="agent:AI1"');
  assert.ok(!showControls(context,document,root,{testGate:true}).some(el=>el.textContent==='人工验收通过'));
});
