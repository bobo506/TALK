// 主任务列表分页候选：真实 workspace.js（冻结基线 + renderWorkspaceList 20 条/页）+ 真实 index.html 的纯 DOM/VM 测试。
// 目标是左侧“任务”页 renderWorkspaceList 的根任务卡片列表（非参与任务表、非子任务树）。
// 不启动 HTTP/浏览器/CLI，不读真实 DB 或凭据；任务数据全部为内存假记录。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const diagnosticsSource = fs.readFileSync(require.resolve('../web/role-diagnostics.js'), 'utf8');
const indexSource = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const workspaceCssSource = fs.readFileSync(require.resolve('../web/workspace.css'), 'utf8');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function fakeEl(tag, documentRef) {
  const classes = new Set();
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '', checked: false,
    disabled: false, readOnly: false, dataset: {}, attrs: {}, children: [], listeners: {},
    parentElement: null, isConnected: true, focusCount: 0, open: false,
    classList: {
      add(...cs) { cs.forEach(c => classes.add(c)); },
      remove(...cs) { cs.forEach(c => classes.delete(c)); },
      toggle(c, force) { const on = force === undefined ? !classes.has(c) : !!force; on ? classes.add(c) : classes.delete(c); return on; },
      contains(c) { return classes.has(c); },
    },
    appendChild(c) {
      if (c.parentElement) c.parentElement.children.splice(c.parentElement.children.indexOf(c), 1);
      c.parentElement = el; c.isConnected = el.isConnected; el.children.push(c); return c;
    },
    append(...cs) { cs.forEach(c => el.appendChild(c)); },
    replaceChildren(...cs) {
      for (const c of el.children) { c.parentElement = null; c.isConnected = false; }
      el.children.length = 0; el.append(...cs);
    },
    insertBefore(node, before) {
      const index = before ? el.children.indexOf(before) : -1;
      if (index < 0) return el.appendChild(node);
      node.parentElement = el; node.isConnected = el.isConnected; el.children.splice(index, 0, node); return node;
    },
    remove() {
      if (el.parentElement) {
        const index = el.parentElement.children.indexOf(el);
        if (index >= 0) el.parentElement.children.splice(index, 1);
      }
      el.parentElement = null; el.isConnected = false;
    },
    setAttribute(k, v) { el.attrs[k] = String(v); if (k === 'open') el.open = true; },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k) ? el.attrs[k] : null; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k); },
    removeAttribute(k) { delete el.attrs[k]; if (k === 'open') el.open = false; },
    addEventListener(type, fn) { (el.listeners[type] ||= []).push(fn); },
    fire(type, event = {}) {
      event.target ||= el; event.currentTarget = el; event.preventDefault ||= () => { event.defaultPrevented = true; };
      return (el.listeners[type] || []).map(fn => fn(event));
    },
    focus() { el.focusCount += 1; if (documentRef) documentRef.activeElement = el; },
    scrollIntoView() {},
    showModal() { el.setAttribute('open', ''); },
    close() { const wasOpen = el.open || el.hasAttribute('open'); el.removeAttribute('open'); if (wasOpen) el.fire('close'); },
    querySelectorAll: () => [],
  };
  Object.defineProperty(el, 'lastChild', { get: () => el.children[el.children.length - 1] || null });
  Object.defineProperty(el, 'firstChild', { get: () => el.children[0] || null });
  Object.defineProperty(el, 'childElementCount', { get: () => el.children.length });
  return el;
}
function allTexts(node, out = []) {
  if (node.textContent) out.push(String(node.textContent));
  for (const c of node.children || []) allTexts(c, out);
  return out;
}
function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  for (const c of node.children || []) findAll(c, pred, out);
  return out;
}
function click(node) { if (!node || node.disabled) return []; return node.fire('click'); }
function hasClass(node, name) { return String(node.className || '').split(/\s+/).includes(name) || node.classList.contains(name); }
function makeTask(id, overrides = {}) {
  return {
    id, parent_task_id: null, root_task_id: id,
    target_member_id: 'agent:fake-a', created_by: 'human:qa',
    title: `任务${id}`, content: `内容${id}`, workflow_status: 'completed',
    hall_group_id: null,
    claimed_at: '2026-10-18T10:00:00Z', finished_at: '2026-10-18T11:00:00Z',
    updated_at: '2026-10-18T11:00:00Z',
    ...overrides,
  };
}

function harness({ human = true, tasks = [] } = {}) {
  const requests = [];
  const selectedTasks = [];
  const elements = new Map();
  const documentStub = {
    activeElement: null,
    getElementById: id => elements.get(id) || null,
    createElement: tag => fakeEl(tag, documentStub),
    createTextNode: text => { const node = fakeEl('#text', documentStub); node.textContent = text; return node; },
    querySelector: selector => selector === '.workbench' ? workbench : null,
    querySelectorAll: () => [],
  };
  const workbench = fakeEl('div', documentStub);
  for (const match of indexSource.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const node = fakeEl(match[1], documentStub);
    node.id = match[2];
    const tag = match[0];
    if (/class="[^"]*\bhidden\b/.test(tag)) node.classList.add('hidden');
    elements.set(node.id, node);
  }
  for (const [id, value] of Object.entries({ 'workspace-search': '', 'role-description-input': '', 'requirements-input': '' })) {
    if (elements.has(id)) elements.get(id).value = value;
  }
  const account = { human };
  const roles = [
    { member_id: 'agent:fake-a', business_role: 'dev', role_description: null },
    { member_id: 'agent:fake-b', business_role: 'reviewer', role_description: '另一角色' },
  ];
  const members = [
    { id: 'human:qa', kind: 'human', display_name: 'QA' },
    { id: 'human:other', kind: 'human', display_name: 'Other' },
    { id: 'agent:viewer', kind: 'agent', display_name: 'Viewer' },
    ...roles.map(role => ({ id: role.member_id, kind: 'agent', display_name: role.member_id.replace(/^agent:/, '') })),
  ];
  const windowListeners = {};
  const windowStub = {
    matchMedia: () => ({ matches: false }),
    AbortController,
    TextEncoder,
    addEventListener(type, fn) { (windowListeners[type] ||= []).push(fn); },
  };
  const context = vm.createContext({
    document: documentStub,
    window: windowStub,
    URLSearchParams,
    encodeURIComponent,
    Date,
    JSON,
    Map,
    Set,
    Array,
    Object,
    String,
    Number,
    Boolean,
    RegExp,
    Promise,
    Error,
    console,
    blackboardOpen: true,
    activeProjectId: 'prj_fake_a',
    activeGroupId: null,
    myId: human ? 'human:qa' : 'agent:viewer',
    members,
    projectAgents: roles.map(role => ({ ...role })),
    projectTasks: tasks,
    groups: [], projects: [{ project_id: 'prj_fake_a' }, { project_id: 'prj_fake_b' }],
    currentMemberIsHuman: () => account.human,
    apiFetch: (url, opts) => {
      const request = { url, opts: opts || {}, index: requests.length };
      requests.push(request);
      return new Promise((resolve, reject) => { request.resolve = resolve; request.reject = reject; });
    },
    readErrorDetail: async (res, fallback) => fallback,
    taskStatusMeta: task => task.workflow_status === 'completed' ? { label: '已完成', className: 'success' } : { label: '执行中', className: 'running' },
    formatTaskTime: () => '10-18 20:00',
    selectWorkspaceTask: task => { selectedTasks.push(task); },
    getContextTask: () => null,
    selectedTaskId: null,
    getActiveGroup: () => null,
    canEnterGroup: () => false,
    setActiveGroup: () => {},
    renderRoomStrip: () => {}, renderProjectStrip: () => {}, renderGroupMembersPanel: () => {},
    setGroupCreateOpen: () => {}, showComposerStatus: () => {}, loadHistory: () => {},
    loadSelectedTaskTree: async () => {}, setBlackboardOpen: () => {}, renderWorkspaceMode: () => {},
    selectedTaskTree: null, taskTreeRequest: 0,
    activeProjectStorageKey: () => 'active-project:test',
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    setTimeout: () => 1,
    clearTimeout: () => {},
    blackboardTitle: elements.get('blackboard-title'), blackboardDescription: elements.get('blackboard-description'),
    blackboardColumns: elements.get('blackboard-columns'), blackboardSummary: elements.get('blackboard-summary'),
    blackboardEmpty: elements.get('blackboard-empty'), userBadge: elements.get('user-badge'),
  });
  context.renderTaskDetailsPanel = () => {
    context.renderWorkspaceRoleDetails();
    context.renderRequirementsPanel();
    context.renderControllerModePanel();
    context.renderRoleDescriptionPanel();
  };
  vm.runInContext(diagnosticsSource, context, { filename: 'role-diagnostics.js' });
  vm.runInContext(wsSource, context, { filename: 'workspace.js' });
  vm.runInContext('this.__workspaceUI = workspaceUI; this.__taskListPageUI = taskListPageUI; this.__roleTasksPageUI = roleTasksPageUI;', context);
  const el = id => elements.get(id);
  const flush = async () => { for (let i = 0; i < 6; i++) await sleep(0); };
  const render = () => { context.renderWorkspaceList(); context.renderTaskDetailsPanel(); };
  // 任务页渲染入口：workspace.js 顶部真实事件绑定之外的直接渲染调用。
  const showTasks = () => { context.__workspaceUI.mode = 'tasks'; context.blackboardOpen = true; render(); };
  const cards = () => findAll(el('blackboard-columns'), n => hasClass(n, 'task-card'));
  const cardTitles = () => cards().map(card => {
    const title = findAll(card, n => hasClass(n, 'task-card-title'))[0];
    return title ? title.textContent : '';
  });
  const pager = () => findAll(el('blackboard-columns'), n => hasClass(n, 'task-list-pagination'))[0] || null;
  const pagerInfo = () => {
    const node = pager();
    if (!node) return null;
    const info = node.children.find(c => hasClass(c, 'task-list-page-info'));
    return info ? info.textContent : null;
  };
  const prevBtn = () => pager() && pager().children.find(c => hasClass(c, 'task-list-page-prev'));
  const nextBtn = () => pager() && pager().children.find(c => hasClass(c, 'task-list-page-next'));
  const filterBtn = label => findAll(el('blackboard-summary'), n => n.tagName === 'button' && n.textContent === label)[0];
  // 真实搜索接线：workspace.js 顶部 input 监听 → workspaceUI.query → renderWorkspaceList。
  const typeSearch = value => {
    const input = el('workspace-search');
    input.value = value;
    input.fire('input', { target: input });
  };
  showTasks();
  return {
    context, account, el, requests, selectedTasks, flush, render, showTasks, typeSearch,
    ui: context.__workspaceUI, pageUI: context.__taskListPageUI, rolePageUI: context.__roleTasksPageUI,
    cards, cardTitles, pager, pagerInfo, prevBtn, nextBtn, filterBtn,
  };
}

test('复核导航：经真实群聊按钮离页再返回任务，页码必须重置', async () => {
  const h = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  Object.assign(h.context, {
    hallFilterInput: h.el('hall-filter-input'),
    blackboardView: h.el('blackboard-view'), roomStrip: h.el('room-strip'),
    hallHeader: h.el('hall-header'), messagesEl: h.el('messages'),
    composerFooter: h.el('composer-footer'), renderBlackboard: () => h.context.renderWorkspaceList(),
    msgInput: h.el('msg-input'), sendBtn: h.el('send-btn'), attachBtn: h.el('attach-btn'),
    mentionDropdown: h.el('mention-dropdown'), sending: false,
    clearComposerStatus: () => {}, updateComposerPlaceholder: () => {},
  });
  const start = appSource.indexOf('function renderWorkspaceMode()');
  const end = appSource.indexOf('function taskStatusMeta(', start);
  assert.ok(start >= 0 && end > start);
  vm.runInContext(appSource.slice(start, end), h.context);
  click(h.nextBtn());
  assert.equal(h.pageUI.page, 2);
  // 真正导航到群聊的分支不调用 renderWorkspaceList。
  click(h.el('workspace-chats-btn'));
  assert.equal(h.ui.mode, 'chats');
  assert.equal(h.pageUI.page, 1, '进入群聊时立即重置，不依赖任务列表重绘');
  h.ui.mode = 'tasks';
  h.context.renderWorkspaceMode();
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 41 项');
  await h.flush();
});

test('静态合同：主列表每页 20 条常量、分页条样式、参与任务分页保持', () => {
  assert.match(wsSource, /TASK_LIST_PAGE_SIZE = 20/);
  assert.match(wsSource, /taskListPageUI/);
  assert.match(wsSource, /workspaceTaskListPagination/);
  assert.match(workspaceCssSource, /\.task-list-pagination/);
  assert.match(workspaceCssSource, /\.task-list-page-info/);
  assert.match(workspaceCssSource, /@media\(max-width:700px\)\{[^}]*\.task-list-pagination/);
  // 既有参与任务 20 条分页不改
  assert.match(wsSource, /ROLE_TASKS_PAGE_SIZE = 20/);
  assert.match(workspaceCssSource, /\.role-task-pagination/);
});

test('0 项：原空态文案、无空翻页栏', async () => {
  const h = harness({ tasks: [] });
  assert.equal(h.cards().length, 0);
  assert.match(allTexts(h.el('blackboard-columns')).join(' '), /当前筛选下没有任务/);
  assert.equal(h.pager(), null);
  await h.flush();
});

test('1 项与 20 项：单页、首尾禁用、页码总数准确', async () => {
  const one = harness({ tasks: [makeTask(1)] });
  assert.equal(one.cards().length, 1);
  assert.equal(one.pagerInfo(), '第 1 / 1 页 · 共 1 项');
  assert.equal(one.prevBtn().disabled, true);
  assert.equal(one.nextBtn().disabled, true);
  const twenty = harness({ tasks: Array.from({ length: 20 }, (_, i) => makeTask(i + 1)) });
  assert.equal(twenty.cards().length, 20);
  assert.equal(twenty.pagerInfo(), '第 1 / 1 页 · 共 20 项');
  assert.equal(twenty.nextBtn().disabled, true);
  await one.flush(); await twenty.flush();
});

test('21 项：第二页 1 项，翻页往返正确、不请求接口、不改选中任务', async () => {
  const h = harness({ tasks: Array.from({ length: 21 }, (_, i) => makeTask(i + 1)) });
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 项');
  assert.equal(h.prevBtn().disabled, true);
  assert.equal(h.nextBtn().disabled, false);
  assert.equal(h.cardTitles()[0], '任务1');
  assert.equal(h.cardTitles()[19], '任务20');
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 2 页 · 共 21 项');
  assert.deepEqual(h.cardTitles(), ['任务21']);
  assert.equal(h.prevBtn().disabled, false);
  assert.equal(h.nextBtn().disabled, true);
  click(h.prevBtn());
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 项');
  assert.equal(h.cardTitles().length, 20);
  assert.equal(h.requests.length, 0, '分页不请求任务接口');
  assert.equal(h.selectedTasks.length, 0, '翻页不自动选中别的任务');
  assert.equal(h.context.selectedTaskId, null, '翻页不改已选任务');
  await h.flush();
});

test('40 项整两页与 41 项三页：边界页码无遗漏', async () => {
  const forty = harness({ tasks: Array.from({ length: 40 }, (_, i) => makeTask(i + 1)) });
  click(forty.nextBtn());
  assert.equal(forty.pagerInfo(), '第 2 / 2 页 · 共 40 项');
  assert.equal(forty.nextBtn().disabled, true);
  assert.equal(forty.cards().length, 20);
  const big = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  click(big.nextBtn());
  click(big.nextBtn());
  assert.equal(big.pagerInfo(), '第 3 / 3 页 · 共 41 项');
  assert.deepEqual(big.cardTitles(), ['任务41']);
  assert.equal(big.nextBtn().disabled, true);
  assert.equal(big.prevBtn().disabled, false);
  await forty.flush(); await big.flush();
});

test('根/子任务 family：子任务卡片不计入总数也不占页位', async () => {
  const roots = Array.from({ length: 21 }, (_, i) => makeTask(i + 1));
  const children = [makeTask(101, { parent_task_id: 1, root_task_id: 1, title: '子任务A' }), makeTask(102, { parent_task_id: 2, root_task_id: 2, title: '子任务B' })];
  const h = harness({ tasks: [...roots, ...children] });
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 项', '总数只算根任务');
  assert.equal(h.cardTitles().includes('子任务A'), false, '子任务不作为独立卡片');
  assert.equal(h.cards().length, 20);
  await h.flush();
});

test('四筛选各自分页；切筛选回第一页', async () => {
  const running = Array.from({ length: 25 }, (_, i) => makeTask(100 + i, { workflow_status: 'in_progress', finished_at: null }));
  const finished = Array.from({ length: 21 }, (_, i) => makeTask(i + 1));
  const h = harness({ tasks: [...finished, ...running] });
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 46 项');
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 46 项');
  click(h.filterBtn('已结束'));
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 项', '切筛选回第一页');
  click(h.filterBtn('进行中'));
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 25 项');
  assert.equal(h.cardTitles()[0], '任务100');
  click(h.filterBtn('待我处理'));
  assert.match(allTexts(h.el('blackboard-columns')).join(' '), /当前筛选下没有任务/);
  assert.equal(h.pager(), null, '筛选为空不显示空翻页栏');
  click(h.filterBtn('全部'));
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 46 项');
  await h.flush();
});

test('待我处理筛选按 family 判定：子任务待我处理时根任务可见并分页', async () => {
  const roots = Array.from({ length: 21 }, (_, i) => makeTask(i + 1, { workflow_status: 'in_progress', finished_at: null }));
  // 只有最后一个根任务的子任务待我处理（我创建、待收取的子任务）
  const child = makeTask(201, { parent_task_id: 21, root_task_id: 21, title: '子任务待收', workflow_status: 'submitted', created_by: 'agent:fake-a', target_member_id: 'agent:fake-b' });
  child.created_by = 'human:qa';
  const h = harness({ tasks: [...roots, child] });
  click(h.filterBtn('待我处理'));
  assert.equal(h.pagerInfo(), '第 1 / 1 页 · 共 1 项');
  assert.deepEqual(h.cardTitles(), ['任务21']);
  await h.flush();
});

test('搜索经真实 input 监听：缩小范围并重置第一页；清空恢复', async () => {
  const h = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 项');
  h.typeSearch('任务4');
  assert.equal(h.pagerInfo(), '第 1 / 1 页 · 共 3 项', '搜索回第一页；匹配 任务4/任务40/任务41 共 3 项');
  assert.deepEqual(h.cardTitles(), ['任务4', '任务40', '任务41']);
  h.typeSearch('任务4');
  assert.equal(h.pageUI.page, 1, '重复输入保持第一页');
  h.typeSearch('');
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 41 项', '清空搜索回第一页完整集合');
  await h.flush();
});

test('轮询/手动刷新保页码；集合缩小夹回最后有效页', async () => {
  const h = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  click(h.nextBtn());
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 3 / 3 页 · 共 41 项');
  h.render();
  h.render();
  assert.equal(h.pagerInfo(), '第 3 / 3 页 · 共 41 项', '同上下文轮询重绘保持页码');
  h.context.projectTasks = Array.from({ length: 20 }, (_, i) => makeTask(i + 1));
  h.render();
  assert.equal(h.pagerInfo(), '第 1 / 1 页 · 共 20 项', '记录减少夹回合法页');
  h.context.projectTasks = Array.from({ length: 41 }, (_, i) => makeTask(i + 1));
  h.render();
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 41 项');
  await h.flush();
});

test('切账号/切项目/切模式/离页（进入任务对话）都重置第一页；翻页不动角色分页', async () => {
  const h = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 项');
  h.context.activeProjectId = 'prj_fake_b';
  h.render();
  assert.equal(h.pageUI.page, 1, '切项目重置');
  h.context.activeProjectId = 'prj_fake_a';
  h.render();
  click(h.nextBtn());
  h.context.myId = 'human:other';
  h.render();
  assert.equal(h.pageUI.page, 1, '切账号重置');
  h.context.myId = 'human:qa';
  h.render();
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 项');
  h.ui.mode = 'roles';
  h.render();
  assert.equal(h.pageUI.page, 1, '切模式重置');
  h.ui.mode = 'tasks';
  h.render();
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 项');
  // 离页：进入任务对话（blackboardOpen=false）即离开任务列表
  h.context.blackboardOpen = false;
  h.render();
  assert.equal(h.pageUI.page, 1, '离开任务列表重置');
  h.context.blackboardOpen = true;
  h.render();
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 41 项', '返回后从第一页开始');
  assert.equal(h.rolePageUI.page, 1, '角色参与任务分页状态不受影响');
  await h.flush();
});

test('翻页后选中/查看任务导航仍用本页实际任务；卡片既有结构保持', async () => {
  const h = harness({ tasks: Array.from({ length: 25 }, (_, i) => makeTask(i + 1)) });
  click(h.nextBtn());
  const first = h.cards()[0];
  // 点击卡片走 workspace.js 真实 selectWorkspaceTask：选中本页实际任务，不改页码。
  click(first);
  assert.equal(h.context.selectedTaskId, 21, '第二页首张卡片选中任务21');
  assert.equal(h.pageUI.page, 2, '选中任务不改变当前页');
  // 卡片保留既有结构：标题/状态/负责人/耗时
  assert.match(allTexts(first).join(' '), /任务21/);
  assert.match(allTexts(first).join(' '), /已完成/);
  assert.equal(findAll(first, n => hasClass(n, 'task-card-duration'))[0].textContent, '01:00:00');
  await h.flush();
});
