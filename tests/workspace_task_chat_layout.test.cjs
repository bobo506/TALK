/* 任务完整对话布局的行为测试：vm 运行真实 web/workspace.js，驱动 syncWorkspaceLayout 验证
   task-chat-mode 只在“任务模式 + 任务 Hall 对话打开”时出现，切换任务/群聊/项目后不残留。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');
const source = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

const taskHall = { id: 'group:task-hall', type: 'task', project_id: 'p1', members: [] };
const chatRoom = { id: 'group:chat', type: 'group', project_id: 'p1', members: [] };

function harness() {
  const classes = new Set();
  const workbench = {
    classList: {
      toggle: (name, on) => { if (on) classes.add(name); else classes.delete(name); },
    },
    has: name => classes.has(name),
  };
  const buttons = {};
  const context = vm.createContext({
    blackboardOpen: false,
    activeGroupId: null,
    activeProjectId: 'p1',
    myId: 'human:qa',
    members: [],
    projectAgents: [],
    groups: [taskHall, chatRoom],
    userBadge: { textContent: '' },
    getActiveGroup() { return context.groups.find(g => g.id === context.activeGroupId) || null; },
    canEnterGroup: id => context.groups.some(g => g.id === id),
    document: {
      querySelector: selector => (selector === '.workbench' ? workbench : null),
      getElementById: id => buttons[id] || (buttons[id] = { setAttribute() {}, value: '', addEventListener() {} }),
    },
  });
  vm.runInContext(source, context);
  return { context, workbench };
}

test('任务页（任务列表 + 详情）不启用 task-chat-mode，详情栏保持原有布局', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = true;
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), false);
  assert.equal(workbench.has('project-mode'), true);
});

test('任务页查看完整对话：启用 task-chat-mode 隐藏重复详情栏', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = false;
  c.activeGroupId = taskHall.id;
  vm.runInContext('workspaceUI.mode = "tasks"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), true);
  assert.equal(workbench.has('project-mode'), true);
  assert.equal(c.workspaceTaskChatActive(), true);
});

test('完整对话返回任务页后 task-chat-mode 立即移除，不残留布局状态', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = false;
  c.activeGroupId = taskHall.id;
  vm.runInContext('workspaceUI.mode = "tasks"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), true);
  // 返回任务：点击左侧任务列表 → blackboardOpen = true（selectWorkspaceTask / setBlackboardOpen 路径）。
  c.blackboardOpen = true;
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), false);
  assert.equal(c.workspaceTaskChatActive(), false);
});

test('切到普通群聊后 task-chat-mode 不残留，群聊成员栏布局不受影响', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = false;
  c.activeGroupId = taskHall.id;
  vm.runInContext('workspaceUI.mode = "tasks"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), true);
  // 切到普通群聊：setActiveGroup 将 mode 改为 chats。
  c.activeGroupId = chatRoom.id;
  vm.runInContext('workspaceUI.mode = "chats"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), false);
  assert.equal(c.workspaceTaskChatActive(), false);
});

test('任务模式下没有可用对话（空项目/无权限）不启用 task-chat-mode', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = false;
  c.activeGroupId = null;
  vm.runInContext('workspaceUI.mode = "tasks"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), false);
});

test('页面移除群聊入口、创建入口、房间列表及空态', () => {
  const html = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
  for (const id of ['workspace-chats-btn', 'group-create-overlay', 'group-room-list', 'workspace-chat-empty', 'hall-filter-input', 'delete-group-btn']) {
    assert.ok(!html.includes(`id="${id}"`), id);
  }
});

test('workspaceTaskChatActive 只读布局条件，不触碰详情 DOM', () => {
  assert.equal(typeof helpers.workspaceTaskChatActive, 'function');
  const sourceText = source;
  // 本切片只切换 workbench class；不删除、不重建详情 DOM。
  assert.match(sourceText, /classList\.toggle\("task-chat-mode", workspaceTaskChatActive\(\)\)/);
  assert.equal(sourceText.includes('taskDetailsPanel.remove'), false);
  assert.equal(sourceText.includes('details-panel").remove'), false);
});

test('Hall 打开、切换任务和返回导航保留左侧列表、选中态、页码及滚动', async () => {
  const { context: c, workbench } = harness();
  const app = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
  const slice = (start, end) => app.slice(app.indexOf(start), app.indexOf(end, app.indexOf(start)));
  function node() {
    const classes = new Set();
    return { children: [], attributes: {}, scrollTop: 0, value: '',
      classList: { toggle: (n, on) => on ? classes.add(n) : classes.delete(n), contains: n => classes.has(n) },
      setAttribute(n, v) { this.attributes[n] = v; },
      appendChild(n) { this.children.push(n); }, addEventListener(n, fn) { this[n] = fn; }, focus() {} };
  }
  const elements = Object.fromEntries(['workspace-tools', 'workspace-search', 'blackboard-view', 'hall-header', 'messages', 'composer-footer'].map(id => [id, node()]));
  elements['workspace-tools'].scrollTop = 137;
  c.document.getElementById = id => elements[id] || (elements[id] = node());
  c.document.createElement = node;
  c.document.createTextNode = text => ({ textContent: text });
  c.window = { matchMedia: () => ({ matches: false }) };
  Object.assign(c, {
    blackboardOpen: true, selectedTaskId: 1, selectedTaskTree: null, taskTreeError: '', taskTreeRequest: 0,
    projectTasks: [{id: 1, hall_group_id: taskHall.id}, {id: 2, hall_group_id: 'group:task-2'}],
    groups: [taskHall, {id: 'group:task-2', type: 'task', members: []}],
    blackboardView: elements['blackboard-view'], hallHeader: elements['hall-header'], messagesEl: elements.messages,
    composerFooter: elements['composer-footer'], msgInput: node(),
    localStorage: { setItem() {}, removeItem() {} }, activeGroupStorageKey: () => 'group',
    renderRoomStrip() {}, renderPresenceStrip() {}, renderMentionDropdownIfOpen() {}, updateComposerPlaceholder() {},
    renderProjectStrip() {}, resetTimelineState() {}, loadSelectedTaskTree: async () => {}, loadHistory() {},
    renderTaskDetailsPanel() {}, renderGroupMembersPanel() {}, renderTaskHallBrief() {}, syncComposerReadOnly() {},
    loadProjectTasks() {}, showTaskDetailsError() {}, showComposerStatus() {},
    workspaceTitle: task => `任务 ${task.id}`, taskStatusMeta: () => ({className: '', label: ''}),
    formatTaskTime: () => '', currentMemberIsHuman: () => true,
  });
  vm.runInContext([
    slice('function setBlackboardOpen(', 'function taskHallComposerReadOnly()'),
    slice('function getContextTask()', 'function taskContextKey()'),
    slice('async function openTaskHall(', 'async function runTaskAction('),
    slice('function setActiveGroup(', 'function renderRoomStrip()'),
    'workspaceTaskDurationEl = () => document.createElement("span");',
    'renderBlackboard = () => { rows = projectTasks.map(workspaceTaskRow); document.getElementById("workspace-tools").scrollTop = 0; };',
    'workspaceUI.query = "保留搜索"; taskListPageUI.page = 2;',
  ].join('\n'), c);
  // 首次同步建立分页上下文，再模拟当前页和搜索。
  c.syncWorkspaceLayout();
  vm.runInContext('taskListPageUI.page = 2', c);
  await c.openTaskHall(c.projectTasks[0]);
  assert.equal(workbench.has('project-mode'), true);
  assert.equal(workbench.has('task-chat-mode'), true);
  assert.equal(elements['blackboard-view'].classList.contains('hidden'), false);
  for (const id of ['hall-header', 'messages', 'composer-footer']) assert.equal(elements[id].classList.contains('hidden'), false, id);
  assert.equal(c.rows[0].classList.contains('selected'), true);
  assert.equal(c.rows[0].attributes['aria-pressed'], 'true');
  assert.equal(elements['workspace-tools'].scrollTop, 137);
  assert.equal(vm.runInContext('taskListPageUI.page', c), 2);
  c.selectWorkspaceTask(c.projectTasks[1]);
  assert.equal(c.activeGroupId, 'group:task-2');
  assert.equal(c.rows[1].classList.contains('selected'), true);
  assert.equal(c.rows[0].classList.contains('selected'), false);
  assert.equal(elements['workspace-tools'].scrollTop, 137);
  assert.equal(vm.runInContext('workspaceUI.query', c), '保留搜索');
  c.setBlackboardOpen(true);
  assert.equal(workbench.has('task-chat-mode'), false);
  assert.equal(workbench.has('project-mode'), true);
  assert.equal(elements['blackboard-view'].classList.contains('hidden'), false);
  for (const id of ['hall-header', 'messages', 'composer-footer']) assert.equal(elements[id].classList.contains('hidden'), true, id);
  assert.equal(c.rows[1].classList.contains('selected'), true);
  assert.equal(elements['workspace-tools'].scrollTop, 137);
});

test('项目与 Hall 桌面列宽一致，Hall 显示对话并隐藏详情，小屏上下排列', () => {
  const css = fs.readFileSync(require.resolve('../web/style.css'), 'utf8');
  const workspaceCss = fs.readFileSync(require.resolve('../web/workspace.css'), 'utf8');
  assert.match(workspaceCss, /\.workbench\.project-mode\s*\{grid-template-columns:minmax\(270px,32%\) minmax\(0,1fr\)/);
  assert.match(css, /\.workbench\.project-mode\.task-chat-mode\s*\{\s*grid-template-columns:\s*minmax\(270px, 32%\) minmax\(0, 1fr\)/);
  assert.match(css, /\.workbench\.project-mode\.task-chat-mode \.timeline-workspace\s*\{\s*display:\s*flex/);
  assert.match(css, /\.workbench\.project-mode\.task-chat-mode \.details-panel\s*\{\s*display:\s*none/);
  assert.match(css, /@media \(max-width: 1000px\)[\s\S]*?grid-template-columns: 280px minmax\(0, 1fr\)/);
  assert.match(workspaceCss, /@media\(max-width:700px\)[\s\S]*?\.workbench\.project-mode\s*\{display:flex; flex-direction:column/);
  assert.match(css, /@media \(max-width: 700px\)[\s\S]*?\.workbench\.project-mode\.task-chat-mode \.timeline-workspace/);
});
