/* R1 回归：开发要求编辑区可见性统一由 renderTaskDetailsPanel 同步。
   用 vm 加载真实 web/workspace.js 全文 + 从 web/app.js 按标记抽取的真实导航/详情渲染函数
   （renderWorkspaceMode → renderBlackboard/renderRoomStrip + renderGroupMembersPanel
     → renderTaskDetailsPanel → renderWorkspaceRoleDetails/renderRequirementsPanel），
   通过真实事件处理器（角色/群聊按钮 click、selectWorkspaceTask、setActiveGroup）驱动导航，
   不直接调用 renderRequirementsPanel 下断言。renderRoomStrip 不触碰 requirements-panel
   （见 .tmp/req-2/review-notes.md §3.3），这里以空实现桩替代，聚焦详情栏同步点。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const workspaceSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');

function sliceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `切片标记缺失: ${startMarker} .. ${endMarker}`);
  return source.slice(start, end);
}

// 真实函数切片（修改 app.js 调用链时这些切片会跟随真实代码，不是手写镜像）。
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
].join('\n');

const STUBS = `
function renderRoomStrip() {} // 不触碰 requirements-panel；本测试聚焦详情栏同步点
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
    title: '', type: '', open: false, dataset: {}, children: [],
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

function harness({ projectId = 'A', memberId = 'human:qa', withTask = false } = {}) {
  const elements = new Map();
  const el = id => {
    if (!elements.has(id)) {
      const initial = ['requirements-panel', 'role-details-panel', 'group-members-panel', 'task-details-panel'].includes(id) ? ['hidden'] : [];
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
  // 具名元素全局（app.js/workspace.js 顶层引用的 DOM 单例）与 getElementById 同源，避免双份对象。
  const named = {
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
  };
  const context = vm.createContext({
    myId: memberId,
    activeProjectId: projectId,
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
    projectTasks: withTask ? [{
      id: 7, title: '演示任务', content: '任务内容', workflow_status: 'in_progress', status: 'running',
      created_by: 'human:qa', target_member_id: 'agent:kimi', hall_group_id: 'group:task-hall',
      updated_at: '2026-09-18T10:00:00Z', claimed_at: null, finished_at: null,
    }] : [],
    groups: [
      { id: 'group:chat1', type: 'group', project_id: 'A', name: '普通房间', members: [{ member_id: 'human:qa', role: 'owner' }] },
      { id: 'group:task-hall', type: 'task', project_id: 'A', name: '任务 Hall', members: [{ member_id: 'human:qa', role: 'member' }] },
    ],
    projects: [{ project_id: 'A', development_requirements: null }],
    apiFetch: url => {
      requests.push(url);
      const match = /\/api\/projects\/([^/?]+)$/.exec(url);
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ project_id: decodeURIComponent(match[1]), development_requirements: null }) });
    },
    readErrorDetail: async (res, fallback) => fallback,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { matchMedia: () => ({ matches: false }), confirm: () => true },
    document: documentStub,
    ...Object.fromEntries(Object.entries(named).map(([name, id]) => [name, el(id)])),
  });
  vm.runInContext(workspaceSource, context);
  vm.runInContext(STUBS + APP_PIECES, context);
  // const 声明不挂到 context 对象，显式暴露引用便于断言与驱动真实入口。
  vm.runInContext('this.__ui = { workspaceUI, selectWorkspaceTask, setActiveGroup, renderWorkspaceMode, renderGroupMembersPanel };', context);
  const ui = context.__ui;
  const tick = async () => { await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0)); };
  const hidden = id => el(id).classList.contains('hidden');
  return { context, ui, el, requests, tick, hidden };
}

const enterRoles = h => { h.el('workspace-roles-btn').fire('click'); return h.tick(); };
const enterChats = h => { h.el('workspace-chats-btn').fire('click'); return h.tick(); };

test('R1 角色页显示编辑区与角色详情（真实按钮 → renderWorkspaceMode 全链路）', async () => {
  const h = harness();
  await enterRoles(h);
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(h.hidden('role-details-panel'), false);
  assert.ok(h.requests.some(url => /\/api\/projects\/A$/.test(url)));
});

test('R1 角色 → 群聊 → 普通房间：编辑区与角色详情都隐藏（原缺陷路径）', async () => {
  const h = harness();
  await enterRoles(h);
  assert.equal(h.hidden('requirements-panel'), false);
  // 真实链路：群聊按钮 → openWorkspaceChats → setActiveGroup → renderWorkspaceMode
  // → renderRoomStrip + renderGroupMembersPanel → renderTaskDetailsPanel → renderRequirementsPanel
  await enterChats(h);
  assert.equal(h.ui.workspaceUI.mode, 'chats');
  assert.equal(h.context.activeGroupId, 'group:chat1');
  assert.equal(h.context.blackboardOpen, false);
  assert.equal(h.hidden('requirements-panel'), true);
  assert.equal(h.hidden('role-details-panel'), true);
  // 群聊成员面板正常显示（没有把整个详情栏误隐藏）
  assert.equal(h.hidden('group-members-panel'), false);
  // 停留期间再次刷新详情（模拟 5 秒轮询之外的重绘入口）也不会复活
  h.ui.renderGroupMembersPanel();
  assert.equal(h.hidden('requirements-panel'), true);
});

test('R1 群聊返回角色页：编辑区恢复显示且同项目草稿保留', async () => {
  const h = harness();
  await enterRoles(h);
  const before = h.requests.length;
  h.el('requirements-input').value = '草稿：R1 往返保留';
  h.el('requirements-input').fire('input');
  await enterChats(h);
  assert.equal(h.hidden('requirements-panel'), true);
  await enterRoles(h);
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(h.el('requirements-input').value, '草稿：R1 往返保留');
  assert.equal(h.requests.length, before); // 同项目同账号不重新读取
  assert.match(h.el('requirements-status').textContent, /未保存/);
});

test('R1 角色 → 任务详情：编辑区隐藏，任务详情显示', async () => {
  const h = harness({ withTask: true });
  await enterRoles(h);
  assert.equal(h.hidden('requirements-panel'), false);
  const task = h.context.projectTasks[0];
  h.ui.selectWorkspaceTask(task);
  await h.tick();
  assert.equal(h.ui.workspaceUI.mode, 'tasks');
  assert.equal(h.hidden('requirements-panel'), true);
  assert.equal(h.hidden('task-details-panel'), false);
});

test('R1 任务完整对话（任务 Hall）与返回：编辑区不残留', async () => {
  const h = harness({ withTask: true });
  await enterRoles(h);
  h.ui.setActiveGroup('group:task-hall'); // 真实入口：进入任务完整对话
  await h.tick();
  assert.equal(h.ui.workspaceUI.mode, 'tasks');
  assert.equal(h.context.blackboardOpen, false);
  assert.equal(h.hidden('requirements-panel'), true);
  assert.equal(h.hidden('role-details-panel'), true);
  // 返回任务页（setBlackboardOpen 路径等价于点“任务”）
  h.ui.workspaceUI.mode = 'tasks'; h.context.blackboardOpen = true;
  h.ui.renderWorkspaceMode();
  await h.tick();
  assert.equal(h.hidden('requirements-panel'), true);
  await enterRoles(h);
  assert.equal(h.hidden('requirements-panel'), false);
});

test('R1 无项目与未登录：编辑区隐藏且不发起读取', async () => {
  const h = harness({ projectId: null });
  await enterRoles(h); // 角色按钮：blackboardOpen = Boolean(null) = false
  assert.equal(h.context.blackboardOpen, false);
  assert.equal(h.hidden('requirements-panel'), true);
  assert.equal(h.requests.length, 0);
  // 账号切换（未登录态）
  const h2 = harness();
  h2.context.myId = null;
  await enterRoles(h2);
  assert.equal(h2.hidden('requirements-panel'), true);
  assert.equal(h2.requests.length, 0);
});
