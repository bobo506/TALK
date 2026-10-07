/* I-2 固定主控入口退役：真实接线验证。
   静态部分断言 index.html 不再含主控面板 DOM、四处静态资源版本一致、web 源码无退役符号；
   运行时部分用 vm 加载整份真实 web/workspace.js（含顶部真实事件绑定）与从 web/app.js
   按函数边界真实抽取的 renderWorkspaceMode/renderGroupMembersPanel/renderTaskDetailsPanel/
   refreshProjectWorkspace 等，经真实“角色”按钮 click、真实 radio change 与“保存” click 驱动：
   - 全链路不抛 ReferenceError（任何对已删函数的残留调用都会在驱动时立即暴露）；
   - 任何导航/刷新/保存路径都不发起 /controller-assignment 请求；
   - 保留的调度模式读取/渲染、固定“主动”意向提示与 #164/#165 离页丢弃行为照常。
   DOM 为存根：验证跨函数接线与请求面，不代表真实浏览器点击/视觉。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const workspaceSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const indexHtml = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');

const STATIC_VERSION = '20261007-initiator-mode-ui';
const RETIRED_SYMBOLS = [
  'controllerUI', 'controllerStatusMeta', 'reloadControllerAssignment', 'renderControllerPanel',
  'workspaceControllerBadge', 'workspaceControllerSummary', 'controllerCandidate',
  'controllerAssignedLabel', 'saveControllerAssignment', 'loadControllerAssignment',
  'controllerEl', 'CONTROLLER_STATUSES',
];
const RETIRED_DOM_IDS = [
  'controller-panel', 'controller-current', 'controller-detail', 'controller-assign-row',
  'controller-candidate-select', 'controller-assign-btn', 'controller-clear-btn',
  'controller-retry-btn', 'controller-status',
];

function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `切片标记缺失: ${startMarker} .. ${endMarker}`);
  return source.slice(start, end);
}

// 真实函数切片（随 app.js 真实代码走，不是手写镜像）。
const APP_PIECES = [
  sliceBetween(appSource, 'function taskStatusMeta(', 'function taskBoardColumn('),
  sliceBetween(appSource, 'function formatTaskTime(', '// 统一轻量计时器'),
  sliceBetween(appSource, 'function renderWorkspaceMode()', 'function taskStatusMeta('),
  sliceBetween(appSource, 'function renderBlackboard()', 'function renderTaskCard('),
  sliceBetween(appSource, 'function getContextTask()', 'function taskKindLabel('),
  sliceBetween(appSource, 'function taskKindLabel(', 'function checkpointReasonLabel('),
  sliceBetween(appSource, 'function renderTaskDetailsPanel()', 'async function openTaskHall('),
  sliceBetween(appSource, 'function sortedGroupMembers(', 'function showGroupMembersError('),
  sliceBetween(appSource, 'function renderGroupMembersPanel()', 'function memberKindFromId('),
  sliceBetween(appSource, 'function memberKindFromId(', 'function toggleMemberKindFilter('),
  sliceBetween(appSource, 'function getActiveGroup()', 'function canManageGroups('),
  sliceBetween(appSource, 'function getGroupMemberIds(', 'function setActiveGroup('),
  sliceBetween(appSource, 'function setActiveGroup(', 'function renderRoomStrip()'),
  // I-2：刷新路径真实抽取——必须证明 reloadControllerAssignment 删除后刷新链路不抛错、只重读模式。
  sliceBetween(appSource, 'async function refreshProjectWorkspace()', 'function renderProjectStrip()'),
].join('\n');

const STUBS = `
function renderRoomStrip() {}
function renderProjectStrip() {}
function renderPresenceStrip() {}
function renderMentionDropdownIfOpen() {}
function updateComposerPlaceholder() {}
function showComposerStatus() {}
function setGroupCreateOpen() {}
function resetTimelineState() {}
function setTaskCreateOpen() {}
function loadHistory() {}
function loadSelectedTaskTree() { return Promise.resolve(); }
function loadProjectAgents() { return Promise.resolve(); }
function loadProjectTasks() { return Promise.resolve(); }
function loadGroups() { return Promise.resolve(); }
function eligibleProjectAgents() { return [{ id: 'agent:kimi' }]; }
function canManageGroups() { return false; }
function findMember(id) { return members.find(m => m.id === id) || null; }
function activeGroupStorageKey() { return 'active-group'; }
function openAgentProfileEditor() {}
function removeGroupMemberFromPanel() {}
function appendChatMemberOptions() {}
`;

function fakeEl(id, initialClasses = []) {
  const classes = new Set(initialClasses);
  const el = {
    id, value: '', textContent: '', className: '', disabled: false, readOnly: false,
    title: '', type: '', open: false, checked: false, dataset: {}, children: [],
    listeners: {},
    classList: {
      add: c => classes.add(c),
      remove: c => classes.delete(c),
      toggle: (c, force) => { const on = force === undefined ? !classes.has(c) : force; on ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    addEventListener(type, fn) { (el.listeners[type] ||= []).push(fn); },
    appendChild(child) { el.children.push(child); return child; },
    append(...items) { el.children.push(...items); },
    insertBefore(node) { el.children.push(node); return node; },
    replaceChildren() { el.children.length = 0; },
    setAttribute() {},
    remove() {},
    focus() {},
    scrollIntoView() {},
    querySelectorAll: () => [],
    fire(type, event = {}) { for (const fn of el.listeners[type] || []) fn(event); },
  };
  Object.defineProperty(el, 'childElementCount', { get: () => el.children.length });
  Object.defineProperty(el, 'lastChild', { get: () => el.children[el.children.length - 1] || null });
  return el;
}

// 项目读取响应携带已弃用的指定字段（真实 ProjectOut 兼容输出）：顺带验证前端完全忽略它们。
function projectBody(projectId, mode = 'passive', version = 0) {
  return {
    project_id: projectId,
    development_requirements: null,
    controller_mode: mode,
    controller_mode_version: version,
    controller_member_id: null,
    controller_assignment_version: 0,
    controller_assignment_status: 'unassigned',
  };
}

function harness() {
  const elements = new Map();
  const el = id => {
    if (!elements.has(id)) {
      const initial = ['requirements-panel', 'role-details-name-panel', 'role-details-tasks-panel', 'group-members-panel', 'task-details-panel'].includes(id) ? ['hidden'] : [];
      elements.set(id, fakeEl(id, initial));
    }
    return elements.get(id);
  };
  const workbench = fakeEl('workbench');
  const documentStub = {
    getElementById: el,
    createElement: tag => fakeEl(tag),
    createTextNode: text => ({ text }),
    querySelector: selector => (selector === '.workbench' ? workbench : null),
  };
  const requests = [];
  let modeVersion = 0;
  let savedMode = 'passive';
  const apiFetch = (url, opts) => {
    requests.push({ url, opts });
    const projectMatch = /\/api\/projects\/([^/?]+)$/.exec(url);
    if (opts?.method === 'PATCH' && /\/controller-mode$/.test(url)) {
      const body = JSON.parse(opts.body);
      assert.equal(body.expected_version, modeVersion, 'CAS：expected_version 原样回传');
      savedMode = body.mode;
      modeVersion += 1;
      return Promise.resolve({ ok: true, status: 200, json: async () => projectBody('A', savedMode, modeVersion) });
    }
    if (projectMatch) {
      return Promise.resolve({ ok: true, status: 200, json: async () => projectBody(decodeURIComponent(projectMatch[1]), savedMode, modeVersion) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => [] });
  };
  const context = vm.createContext({
    myId: 'human:qa',
    activeProjectId: 'A',
    activeGroupId: null,
    blackboardOpen: false,
    selectedTaskId: null,
    selectedTaskTree: null,
    taskTreeError: '',
    taskTreeRequest: 0,
    groupMembersOpen: false,
    taskActionSaving: false,
    groupMemberSaving: false,
    agentProfileSaving: false,
    onlineMemberIds: new Set(),
    selectedMemberKindFilters: new Set(),
    members: [
      { id: 'human:qa', kind: 'human', display_name: 'QA' },
      { id: 'agent:kimi', kind: 'agent', display_name: 'Kimi' },
    ],
    projectAgents: [{ member_id: 'agent:kimi', business_role: 'dev' }],
    projectTasks: [],
    groups: [],
    projects: [{ project_id: 'A', development_requirements: null }],
    apiFetch,
    readErrorDetail: async (res, fallback) => fallback,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { matchMedia: () => ({ matches: false }), confirm: () => true },
    document: documentStub,
    ...Object.fromEntries(Object.entries({
      blackboardView: 'blackboard-view',
      roomStrip: 'room-strip',
      hallHeader: 'hall-header',
      messagesEl: 'messages',
      composerFooter: 'composer-footer',
      taskDetailsPanel: 'task-details-panel',
      groupMembersPanel: 'group-members-panel',
      blackboardColumns: 'blackboard-columns',
      blackboardSummary: 'blackboard-summary',
      blackboardEmpty: 'blackboard-empty',
      blackboardTitle: 'blackboard-title',
      blackboardDescription: 'blackboard-description',
      taskDetailsError: 'task-details-error',
      taskDetailsTitle: 'task-details-title',
      taskDetailsStatus: 'task-details-status',
      taskDetailsMeta: 'task-details-meta',
      taskDetailsContent: 'task-details-content',
      taskDetailsActions: 'task-details-actions',
      groupMembersSubtitle: 'group-members-subtitle',
      groupMetaForm: 'group-meta-form',
      groupMembersList: 'group-members-list',
      groupMemberAddForm: 'group-member-add-form',
      groupMemberAddBtn: 'group-member-add-btn',
      groupMemberAddSelect: 'group-member-add-select',
      groupMemberAddRole: 'group-member-add-role',
      deleteGroupBtn: 'delete-group-btn',
      hallFilterInput: 'hall-filter-input',
      msgInput: 'msg-input',
      userBadge: 'user-badge',
      taskCreateAgent: 'task-create-agent',
      refreshProjectBtn: 'refresh-project-btn',
      taskDetailsRefreshBtn: 'task-details-refresh-btn',
    }).map(([name, id]) => [name, el(id)])),
  });
  vm.runInContext(workspaceSource, context);
  vm.runInContext(STUBS + APP_PIECES, context);
  vm.runInContext('this.__ui = { workspaceUI, selectWorkspaceTask, setActiveGroup, renderWorkspaceMode, renderGroupMembersPanel, refreshProjectWorkspace, selectControllerMode, saveControllerMode, renderControllerModePanel };', context);
  const ui = context.__ui;
  vm.runInContext('this.__modeui = controllerModeUI;', context);
  const tick = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setTimeout(r, 0)); };
  const hidden = id => el(id).classList.contains('hidden');
  const assignmentCalls = () => requests.filter(r => r.url.includes('controller-assignment'));
  return { context, ui, modeui: context.__modeui, el, requests, tick, hidden, assignmentCalls };
}

test('静态退役：index.html 无主控面板 DOM、四处版本一致；web 源码无退役符号', () => {
  for (const id of RETIRED_DOM_IDS) {
    assert.ok(!indexHtml.includes(`id="${id}"`), `index.html 不得残留 #${id}`);
    assert.ok(!workspaceSource.includes(id), `workspace.js 不得引用 #${id}`);
    assert.ok(!appSource.includes(id), `app.js 不得引用 #${id}`);
  }
  for (const symbol of RETIRED_SYMBOLS) {
    assert.ok(!workspaceSource.includes(symbol), `workspace.js 不得残留 ${symbol}`);
    assert.ok(!appSource.includes(symbol), `app.js 不得残留 ${symbol}`);
  }
  assert.ok(!workspaceSource.includes('/controller-assignment'), 'workspace.js 不再读写指定端点');
  assert.ok(!appSource.includes('/controller-assignment'), 'app.js 不再读写指定端点');
  assert.equal(indexHtml.split(STATIC_VERSION).length - 1, 4, '四处静态资源版本一致');
  assert.ok(!indexHtml.includes('20261006-controller-mode'), '旧版本串不残留');
});

test('真实“角色”按钮进入项目设置：模式面板读取/渲染保留，绝无 assignment 请求', async () => {
  const h = harness();
  // 真实事件绑定：workspace.js 顶部“角色”按钮 click → renderWorkspaceMode 全链路
  h.el('workspace-roles-btn').fire('click');
  await h.tick();
  assert.equal(h.ui.workspaceUI.mode, 'roles');
  assert.equal(h.hidden('controller-mode-panel'), false, '模式面板在项目设置可见');
  assert.equal(h.hidden('requirements-panel'), false, '开发要求面板保留');
  assert.equal(h.el('controller-mode-saved').textContent, '已保存设置：被动');
  assert.equal(h.el('controller-mode-effective').textContent, '实际执行：尚无生效的主动调度（本版本不支持自动生效）');
  assert.ok(h.requests.some(r => /\/api\/projects\/A$/.test(r.url)), '模式/开发要求项目读取存在');
  assert.equal(h.assignmentCalls().length, 0, '全链路不得请求 /controller-assignment');
  // 已删函数在真实运行上下文中不存在；保留的模式函数可用
  for (const fn of ['renderControllerPanel', 'reloadControllerAssignment', 'saveControllerAssignment', 'loadControllerAssignment', 'syncControllerPanel']) {
    assert.equal(typeof h.context[fn], 'undefined', `${fn} 已删除`);
  }
  assert.equal(typeof h.context.renderControllerModePanel, 'function');
  assert.equal(typeof h.context.reloadControllerMode, 'function');
});

test('真实 refreshProjectWorkspace：刷新只重读模式，无 assignment、无 ReferenceError', async () => {
  const h = harness();
  h.el('workspace-roles-btn').fire('click');
  await h.tick();
  const before = h.requests.length;
  await h.ui.refreshProjectWorkspace();
  await h.tick();
  const added = h.requests.slice(before);
  assert.equal(h.assignmentCalls().length, 0, '刷新不得请求 /controller-assignment');
  assert.equal(added.length, 1, '角色页刷新只追加一次模式项目重读');
  assert.ok(/\/api\/projects\/A$/.test(added[0].url));
  assert.equal(added[0].opts?.method, undefined, '模式重读为 GET');
  assert.equal(h.el('controller-mode-saved').textContent, '已保存设置：被动');
});

test('#164/#165 离页语义经真实导航保留：离开项目设置丢弃未保存选择，全程无 PATCH', async () => {
  const h = harness();
  h.el('workspace-roles-btn').fire('click');
  await h.tick();
  // 真实 radio change 绑定：选择“主动”只更新未保存选择
  const activeRadio = h.el('controller-mode-active');
  activeRadio.value = 'active'; // 对应 index.html 中 value="active"（DOM 存根不带 HTML 属性）
  activeRadio.checked = true;
  activeRadio.fire('change', { target: activeRadio });
  assert.equal(h.modeui.selection, 'active');
  assert.equal(h.el('controller-mode-save-btn').disabled, false);
  // 真实导航离开：切任务页（renderWorkspaceMode → renderGroupMembersPanel → renderTaskDetailsPanel）
  h.ui.workspaceUI.mode = 'tasks';
  h.ui.renderWorkspaceMode();
  await h.tick();
  assert.equal(h.modeui.selection, null, '离页丢弃未保存选择');
  assert.equal(h.hidden('controller-mode-panel'), true);
  // 返回项目设置：radio 按已保存被动显示
  h.ui.workspaceUI.mode = 'roles';
  h.ui.renderWorkspaceMode();
  await h.tick();
  assert.equal(h.hidden('controller-mode-panel'), false);
  assert.equal(h.el('controller-mode-passive').checked, true);
  assert.equal(h.el('controller-mode-active').checked, false);
  assert.equal(h.requests.filter(r => r.opts?.method === 'PATCH').length, 0, '离页不发 PATCH');
  assert.equal(h.assignmentCalls().length, 0);
});

test('保存“主动”走真实绑定：PATCH controller-mode 成功核实后显示固定意向提示', async () => {
  const h = harness();
  h.el('workspace-roles-btn').fire('click');
  await h.tick();
  const activeRadio = h.el('controller-mode-active');
  activeRadio.value = 'active'; // 对应 index.html 中 value="active"（DOM 存根不带 HTML 属性）
  activeRadio.checked = true;
  activeRadio.fire('change', { target: activeRadio });
  h.el('controller-mode-save-btn').fire('click');
  await h.tick();
  const patch = h.requests.find(r => r.opts?.method === 'PATCH');
  assert.ok(patch, '真实保存按钮触发 PATCH');
  assert.ok(/\/api\/projects\/A\/controller-mode$/.test(patch.url));
  assert.equal(JSON.parse(patch.opts.body).mode, 'active');
  assert.equal(h.modeui.saved, 'active');
  assert.equal(h.el('controller-mode-saved').textContent, '已保存设置：主动');
  // I-2：固定意向提示，无任何指定前置
  assert.equal(h.modeui.notice, '已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。');
  assert.equal(h.el('controller-mode-effective').textContent, '实际执行：尚无生效的主动调度（本版本不支持自动生效）');
  assert.equal(h.assignmentCalls().length, 0, '保存模式不触碰 /controller-assignment');
});
