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
  assert.equal(workbench.has('project-mode'), false);
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

test('群聊空状态沿用 empty-chat-mode，不混入 task-chat-mode', () => {
  const { context: c, workbench } = harness();
  c.blackboardOpen = false;
  c.activeGroupId = null;
  vm.runInContext('workspaceUI.mode = "chats"', c);
  c.syncWorkspaceLayout();
  assert.equal(workbench.has('task-chat-mode'), false);
  assert.equal(workbench.has('empty-chat-mode'), true);
});

test('workspaceTaskChatActive 只读布局条件，不触碰详情 DOM', () => {
  assert.equal(typeof helpers.workspaceTaskChatActive, 'function');
  const sourceText = source;
  // 本切片只切换 workbench class；不删除、不重建详情 DOM。
  assert.match(sourceText, /classList\.toggle\("task-chat-mode", workspaceTaskChatActive\(\)\)/);
  assert.equal(sourceText.includes('taskDetailsPanel.remove'), false);
  assert.equal(sourceText.includes('details-panel").remove'), false);
});
