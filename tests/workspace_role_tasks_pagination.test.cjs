// 参与任务分页候选：真实 workspace.js（冻结基线 + 20 条/页最小改）+ 真实 role-diagnostics.js 的纯 DOM/VM 测试。
// 不启动 HTTP/浏览器/CLI，不读真实 DB 或凭据；任务数据全部为内存假记录。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const diagnosticsSource = fs.readFileSync(require.resolve('../web/role-diagnostics.js'), 'utf8');
const indexSource = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
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
function serviceRow(overrides = {}) {
  return {
    desired: 'running', observed: 'stopped', last_action: 'stop', last_result: 'stopped',
    error_code: null, error_message: null, control_kind: 'managed_cli', manager_kind: 'cli_process',
    generation: 2, current_launch: null, observed_instance_id: null,
    native_login: 'verified', model_alias: 'resolved', readiness_service: 'pending',
    can_start: true, can_stop: false, ownership_held: false,
    started_at: '2026-10-18T19:00:00Z', stopped_at: '2026-10-18T20:00:00Z', updated_at: '2026-10-18T20:00:00Z',
    ...overrides,
  };
}
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

function harness({ human = true, tasks = [], roster = null } = {}) {
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
  const roles = roster || [
    { member_id: 'agent:fake-a', business_role: 'dev', role_description: null, service: serviceRow() },
    { member_id: 'agent:fake-b', business_role: 'reviewer', role_description: '另一角色', service: serviceRow() },
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
  vm.runInContext('this.__workspaceUI = workspaceUI; this.__roleTasksPageUI = roleTasksPageUI;', context);
  const el = id => elements.get(id);
  const flush = async () => { for (let i = 0; i < 6; i++) await sleep(0); };
  const render = () => { context.renderWorkspaceList(); context.renderTaskDetailsPanel(); };
  const selectRole = memberId => {
    context.__workspaceUI.mode = 'roles';
    context.__workspaceUI.roleSelection = 'role';
    context.__workspaceUI.selectedRole = memberId;
    render();
  };
  const taskRows = () => findAll(el('role-details-tasks-panel'), n => n.tagName === 'tr' && n.children.some(c => c.tagName === 'td'));
  const rowTitles = () => taskRows().map(row => {
    const name = row.children[0];
    return name && name.children[0] ? name.children[0].textContent : '';
  });
  const pager = () => findAll(el('role-details-tasks-panel'), n => hasClass(n, 'role-task-pagination'))[0] || null;
  const pagerInfo = () => {
    const node = pager();
    if (!node) return null;
    const info = node.children.find(c => hasClass(c, 'role-task-page-info'));
    return info ? info.textContent : null;
  };
  const prevBtn = () => pager() && pager().children.find(c => hasClass(c, 'role-task-page-prev'));
  const nextBtn = () => pager() && pager().children.find(c => hasClass(c, 'role-task-page-next'));
  const filterBtn = label => findAll(el('role-details-tasks-panel'), n => n.tagName === 'button' && n.textContent === label && hasClass(n, 'workspace-text-button') && !hasClass(n, 'role-task-page-prev') && !hasClass(n, 'role-task-page-next'))[0];
  const viewButtons = () => findAll(el('role-details-tasks-panel'), n => n.tagName === 'button' && n.textContent === '查看任务');
  return {
    context, account, roles, el, requests, selectedTasks, flush, render, selectRole,
    ui: context.__workspaceUI, pageUI: context.__roleTasksPageUI,
    taskRows, rowTitles, pager, pagerInfo, prevBtn, nextBtn, filterBtn, viewButtons,
  };
}

test('静态合同：每页 20 条常量、分页条样式、筛选与表头保持', () => {
  assert.match(wsSource, /ROLE_TASKS_PAGE_SIZE = 20/);
  assert.match(wsSource, /roleTasksPageUI/);
  assert.match(workspaceCssSource, /\.role-task-pagination/);
  assert.match(wsSource, /"参与的任务"/);
  for (const title of ['"任务", "执行耗时", "任务状态", "操作"']) {
    assert.ok(wsSource.includes(title));
  }
});

test('0 条：空态文案、无分页条', async () => {
  const h = harness({ tasks: [] });
  h.selectRole('agent:fake-a');
  assert.equal(h.taskRows().length, 0);
  assert.match(allTexts(h.el('role-details-tasks-panel')).join(' '), /当前没有这类任务/);
  assert.equal(h.pager(), null);
  await h.flush();
});

test('1 条与 20 条：单页、首尾禁用、范围准确', async () => {
  const one = harness({ tasks: [makeTask(1)] });
  one.selectRole('agent:fake-a');
  assert.equal(one.taskRows().length, 1);
  assert.equal(one.pagerInfo(), '第 1 / 1 页 · 共 1 条 · 本页 1–1 条');
  assert.equal(one.prevBtn().disabled, true);
  assert.equal(one.nextBtn().disabled, true);
  const twenty = harness({ tasks: Array.from({ length: 20 }, (_, i) => makeTask(i + 1)) });
  twenty.selectRole('agent:fake-a');
  assert.equal(twenty.taskRows().length, 20);
  assert.equal(twenty.pagerInfo(), '第 1 / 1 页 · 共 20 条 · 本页 1–20 条');
  assert.equal(twenty.nextBtn().disabled, true);
});

test('21 条：第二页 1 条，翻页往返正确', async () => {
  const h = harness({ tasks: Array.from({ length: 21 }, (_, i) => makeTask(i + 1)) });
  h.selectRole('agent:fake-a');
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 条 · 本页 1–20 条');
  assert.equal(h.prevBtn().disabled, true);
  assert.equal(h.nextBtn().disabled, false);
  assert.equal(h.rowTitles()[0], '任务1');
  assert.equal(h.rowTitles()[19], '任务20');
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 2 页 · 共 21 条 · 本页 21–21 条');
  assert.deepEqual(h.rowTitles(), ['任务21']);
  assert.equal(h.prevBtn().disabled, false);
  assert.equal(h.nextBtn().disabled, true);
  click(h.prevBtn());
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 条 · 本页 1–20 条');
  assert.equal(h.rowTitles().length, 20);
  await h.flush();
});

test('40 条整两页与 41 条三页：边界页码/范围无遗漏', async () => {
  const forty = harness({ tasks: Array.from({ length: 40 }, (_, i) => makeTask(i + 1)) });
  forty.selectRole('agent:fake-a');
  click(forty.nextBtn());
  assert.equal(forty.pagerInfo(), '第 2 / 2 页 · 共 40 条 · 本页 21–40 条');
  assert.equal(forty.nextBtn().disabled, true);
  const big = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  big.selectRole('agent:fake-a');
  click(big.nextBtn());
  click(big.nextBtn());
  assert.equal(big.pagerInfo(), '第 3 / 3 页 · 共 41 条 · 本页 41–41 条');
  assert.equal(big.nextBtn().disabled, true);
  assert.equal(big.prevBtn().disabled, false);
});

test('翻页不发任何网络请求；每行保留查看任务/执行耗时/状态', async () => {
  const h = harness({ tasks: Array.from({ length: 25 }, (_, i) => makeTask(i + 1)) });
  h.selectRole('agent:fake-a');
  click(h.nextBtn());
  await h.flush();
  assert.equal(h.requests.length, 0, '分页不请求任务接口');
  const row = h.taskRows()[0];
  const duration = findAll(row, n => hasClass(n, 'task-card-duration'))[0];
  assert.equal(duration.textContent, '01:00:00', '执行耗时沿用 claimed→finished');
  assert.match(allTexts(row).join(' '), /已完成/);
  click(h.viewButtons()[0]);
  assert.equal(h.context.selectedTaskId, 21, '查看任务导航到本页实际任务');
});

test('筛选切换重置第一页；进行中/已结束各自分页', async () => {
  const running = Array.from({ length: 25 }, (_, i) => makeTask(100 + i, { workflow_status: 'in_progress', finished_at: null }));
  const finished = Array.from({ length: 21 }, (_, i) => makeTask(i + 1));
  const h = harness({ tasks: [...finished, ...running] });
  h.selectRole('agent:fake-a');
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 条 · 本页 1–20 条');
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 2 页 · 共 21 条 · 本页 21–21 条');
  click(h.filterBtn('进行中'));
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 25 条 · 本页 1–20 条', '切筛选回第一页');
  assert.equal(h.rowTitles()[0], '任务100');
  click(h.filterBtn('已结束'));
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 21 条 · 本页 1–20 条');
  await h.flush();
});

test('切角色/切项目/切账号/离开详情都重置第一页；普通轮询保页码；记录减少夹回合法页', async () => {
  const h = harness({ tasks: Array.from({ length: 41 }, (_, i) => makeTask(i + 1)) });
  h.selectRole('agent:fake-a');
  click(h.nextBtn());
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 3 / 3 页 · 共 41 条 · 本页 41–41 条');
  h.render();
  h.render();
  assert.equal(h.pagerInfo(), '第 3 / 3 页 · 共 41 条 · 本页 41–41 条', '同上下文轮询重绘保持页码');
  h.context.projectTasks = Array.from({ length: 20 }, (_, i) => makeTask(i + 1));
  h.render();
  assert.equal(h.pagerInfo(), '第 1 / 1 页 · 共 20 条 · 本页 1–20 条', '记录减少夹回合法页');
  h.context.projectTasks = Array.from({ length: 41 }, (_, i) => makeTask(i + 1));
  h.render();
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 条 · 本页 21–40 条');
  h.selectRole('agent:fake-b');
  assert.equal(h.pageUI.page, 1, '切角色重置');
  h.selectRole('agent:fake-a');
  click(h.nextBtn());
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
  assert.equal(h.pagerInfo(), '第 2 / 3 页 · 共 41 条 · 本页 21–40 条');
  h.ui.mode = 'tasks';
  h.render();
  assert.equal(h.el('role-details-tasks-panel').classList.contains('hidden'), true);
  assert.equal(h.pageUI.page, 1, '离开角色详情重置');
  h.ui.mode = 'roles';
  h.render();
  assert.equal(h.pagerInfo(), '第 1 / 3 页 · 共 41 条 · 本页 1–20 条', '返回后从第一页开始');
  await h.flush();
});

test('切到项目设置重置页码；未保存角色说明草稿在翻页/重绘后保持', async () => {
  const h = harness({ tasks: Array.from({ length: 30 }, (_, i) => makeTask(i + 1)) });
  h.selectRole('agent:fake-a');
  const description = h.el('role-description-input');
  description.value = '未保存说明草稿';
  description.fire('input', { target: description });
  click(h.nextBtn());
  assert.equal(h.pagerInfo(), '第 2 / 2 页 · 共 30 条 · 本页 21–30 条');
  assert.equal(h.el('role-description-input'), description, '静态说明区不被重绘销毁');
  assert.equal(description.value, '未保存说明草稿');
  h.render();
  assert.equal(description.value, '未保存说明草稿', '轮询重绘不覆盖草稿');
  h.context.__workspaceUI.roleSelection = 'settings';
  h.render();
  assert.equal(h.pageUI.page, 1, '离开具体角色到项目设置即重置');
  h.selectRole('agent:fake-a');
  assert.equal(h.pagerInfo(), '第 1 / 2 页 · 共 30 条 · 本页 1–20 条');
  assert.equal(description.value, '未保存说明草稿', '同账号+项目+角色的草稿往返保持');
  await h.flush();
});

test('服务区/说明区/任务详情导航回归：角色开关与名称区保持，导出不自动发请求', async () => {
  const h = harness({ tasks: Array.from({ length: 21 }, (_, i) => makeTask(i + 1)) });
  h.selectRole('agent:fake-a');
  assert.match(allTexts(h.el('role-details-name-panel')).join(' '), /角色开关/);
  assert.match(allTexts(h.el('role-details-name-panel')).join(' '), /成员 ID：agent:fake-a/);
  assert.equal(h.requests.filter(r => r.url.includes('/runtime-logs')).length, 0, '选中角色不自动扫描日志');
  click(h.nextBtn());
  assert.match(allTexts(h.el('role-details-name-panel')).join(' '), /角色开关/, '翻页不影响服务区');
  await h.flush();
});
