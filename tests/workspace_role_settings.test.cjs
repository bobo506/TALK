// ROLE-SETTINGS-1：角色页“项目设置”独立首项 + 主控管理集中 + 移除角色交办入口。
// 在 vm 中加载整份真实 web/workspace.js（含真实 renderWorkspaceList/renderWorkspaceRoleDetails/
// renderRequirementsPanel/renderControllerPanel 与顶部事件绑定），renderTaskDetailsPanel 桩
// 按 app.js 的真实顺序调用三个真实面板函数；setActiveProject 从 app.js 按函数边界真实抽取。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');

function functionSource(source, name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  assert.ok(start >= 0 && end >= 0, `未找到函数 ${name}`);
  return rest.slice(0, end + 1);
}

function fakeEl(tag) {
  const classes = new Set();
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '', disabled: false, readOnly: false,
    dataset: {}, attrs: {}, children: [], listeners: {},
    classList: {
      add(...cs) { cs.forEach(c => classes.add(c)); },
      remove(...cs) { cs.forEach(c => classes.delete(c)); },
      toggle(c, force) { const on = force === undefined ? !classes.has(c) : !!force; on ? classes.add(c) : classes.delete(c); return on; },
      contains(c) { return classes.has(c); },
    },
    appendChild(c) { el.children.push(c); return c; },
    append(...cs) { el.children.push(...cs); },
    replaceChildren() { el.children.length = 0; },
    insertBefore(node) { el.children.push(node); return node; },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    addEventListener(type, fn) { (el.listeners[type] ||= []).push(fn); },
    fire(type, event = {}) { for (const fn of el.listeners[type] || []) fn(event); },
    focus() {},
    scrollIntoView() {},
    querySelectorAll: () => [],
  };
  Object.defineProperty(el, 'lastChild', { get: () => el.children[el.children.length - 1] || null });
  Object.defineProperty(el, 'childElementCount', { get: () => el.children.length });
  return el;
}
function allTexts(node, out = []) {
  if (node.textContent) out.push(node.textContent);
  for (const c of node.children) allTexts(c, out);
  return out;
}
function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  for (const c of node.children) findAll(c, pred, out);
  return out;
}

const MEMBERS = [
  { id: 'human:qa', kind: 'human', display_name: 'bobo' },
  { id: 'agent:kimi', kind: 'agent', display_name: 'Kimi' },
  { id: 'agent:kimi2', kind: 'agent', display_name: 'Kimi' }, // 同名角色，靠 member_id 消歧
  { id: 'agent:deepseek', kind: 'agent', display_name: 'DeepSeek' },
  { id: 'agent:banned', kind: 'agent', display_name: 'Banned', disabled_at: '2026-09-20T00:00:00' },
];
const ROSTER = [
  { member_id: 'agent:kimi', business_role: 'reviewer' },
  { member_id: 'agent:kimi2', business_role: 'reviewer' },
  { member_id: 'agent:deepseek', business_role: 'dev' },
];

function harness({ human = true, projectId = 'A', roster = ROSTER } = {}) {
  const pending = [];
  const elements = new Map();
  const getEl = id => {
    if (!elements.has(id)) { const node = fakeEl('div'); node.id = id; elements.set(id, node); }
    return elements.get(id);
  };
  const workbench = fakeEl('div');
  const documentStub = {
    getElementById: getEl,
    createElement: tag => fakeEl(tag),
    createTextNode: text => ({ textContent: text }),
    querySelector: sel => (sel === '.workbench' ? workbench : null),
    activeElement: null,
    body: fakeEl('body'),
  };
  const calls = { selectTask: [] };
  const context = vm.createContext({
    document: documentStub,
    blackboardOpen: true,
    activeProjectId: projectId,
    activeGroupId: null,
    myId: human ? 'human:qa' : 'agent:kimi',
    members: MEMBERS,
    projectAgents: roster,
    projectTasks: [],
    groups: [],
    projects: [
      { project_id: 'A', development_requirements: 'A 已保存要求' },
      { project_id: 'B', development_requirements: 'B 要求' },
    ],
    currentMemberIsHuman: () => human,
    apiFetch: (url, opts) => new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject })),
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    // app.js 侧函数：本切片不涉及的用桩，面板同步按真实顺序调用真实函数。
    taskStatusMeta: () => ({ label: '执行中', className: 'running' }),
    formatTaskTime: () => '09-20 10:00',
    selectWorkspaceTask: task => { calls.selectTask.push(task.id); },
    getActiveGroup: () => null,
    canEnterGroup: () => false,
    setActiveGroup: () => {},
    renderRoomStrip: () => {},
    renderProjectStrip: () => {},
    renderGroupMembersPanel: () => {},
    setGroupCreateOpen: () => {},
    showComposerStatus: () => {},
    loadHistory: () => {},
    loadSelectedTaskTree: async () => {},
    loadProjectAgents: async () => {},
    loadProjectTasks: async () => {},
    setBlackboardOpen: () => {},
    renderWorkspaceMode: () => {},
    selectedTaskTree: null,
    taskTreeRequest: 0,
    activeProjectStorageKey: () => 'active-project:test',
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { matchMedia: () => ({ matches: false }), confirm: () => true },
    // app.js 里的具名 DOM 单例
    blackboardTitle: getEl('blackboard-title'),
    blackboardDescription: getEl('blackboard-description'),
    blackboardColumns: getEl('blackboard-columns'),
    blackboardSummary: getEl('blackboard-summary'),
    blackboardEmpty: getEl('blackboard-empty'),
    userBadge: getEl('user-badge'),
  });
  // renderTaskDetailsPanel 桩按 app.js 真实顺序调用三个真实面板同步函数。
  context.renderTaskDetailsPanel = () => {
    context.renderWorkspaceRoleDetails();
    context.renderRequirementsPanel();
    context.renderControllerPanel();
  };
  vm.runInContext(wsSource, context);
  // const 声明不挂到 context 对象，显式暴露引用便于断言与驱动选择状态。
  vm.runInContext('this.__wsui = workspaceUI;', context);
  const ui = context.__wsui;
  // setActiveProject 真实抽取：验证切项目不串选。
  vm.runInContext(functionSource(appSource, 'setActiveProject'), context);
  const el = getEl;
  const reply = (index, data, { ok = true, status = 200 } = {}) =>
    pending[index].resolve({ ok, status, json: async () => data });
  const flush = async () => { await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0)); };
  const hidden = id => el(id).classList.contains('hidden');
  // 真实导航入口：角色标签按钮（顶部事件绑定来自真实 workspace.js）+ 真实列表渲染与面板同步
  const enterRoles = async () => {
    el('workspace-roles-btn').fire('click');
    context.renderWorkspaceList();
    context.renderTaskDetailsPanel();
    await flush();
  };
  // 项目设置页会并行发起开发要求与主控两次项目读取：统一应答所有在途项目 GET。
  const replyProjectReads = body => {
    pending.forEach((p, i) => {
      if (p._done || !/\/api\/projects\/[^/]+$/.test(p.url)) return;
      p._done = true;
      reply(i, body);
    });
  };
  const rows = () => el('blackboard-columns').children;
  const settingsRow = () => rows()[0];
  const roleRow = memberId => rows().find(row => !row.className.includes('role-settings-row') && allTexts(row).includes(memberId));
  return { context, ui, pending, reply, replyProjectReads, flush, hidden, el, enterRoles, rows, settingsRow, roleRow, calls };
}

const CONTROLLER_READ = {
  controller_member_id: null, controller_assignment_version: 0, controller_assignment_status: 'unassigned',
};

test('固定首项：首次进入角色页默认“项目设置”，不计入角色、不是 Agent、不发起角色相关请求', async () => {
  const h = harness();
  await h.enterRoles();
  const settings = h.settingsRow();
  assert.ok(settings, '列表首项存在');
  assert.ok(settings.className.includes('role-settings-row'));
  assert.equal(settings.children[0].textContent, '项目设置');
  assert.equal(settings.attrs['aria-pressed'], 'true');
  // 角色行仍是真实名册成员（3 个），“项目设置”不占用角色位
  const roleRows = h.rows().filter(row => !row.className.includes('role-settings-row'));
  assert.deepEqual(roleRows.map(row => row.children[0].textContent), ['Kimi', 'Kimi', 'DeepSeek']);
  // 选中项目设置时不产生 member_id 语义：selectedRole 保持 null，请求只有项目读取
  assert.equal(h.ui.selectedRole, null);
  assert.equal(h.context.workspaceSettingsSelected(), true);
  assert.ok(h.pending.every(p => /\/api\/projects\/A$/.test(p.url)), '只发起项目读取，没有把首项当成员请求');
  // 右侧互斥：项目级面板显示，角色详情隐藏
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(h.hidden('controller-panel'), false);
  assert.equal(h.hidden('role-details-panel'), true);
});

test('搜索过滤角色行时“项目设置”保持可达，且不受过滤影响', async () => {
  const h = harness();
  await h.enterRoles();
  const search = h.el('workspace-search');
  search.value = '不存在的角色xyz';
  search.fire('input', { target: search });
  const rows = h.rows();
  assert.equal(rows[0].children[0].textContent, '项目设置', '固定首项不随搜索隐藏');
  assert.equal(rows[0].attrs['aria-pressed'], 'true');
  assert.ok(allTexts(h.el('blackboard-columns')).some(t => t.includes('没有匹配的角色')));
  // 搜索中点击首项仍然可达项目设置页
  rows[0].fire('click');
  await h.flush();
  assert.equal(h.context.workspaceSettingsSelected(), true);
  assert.equal(h.hidden('requirements-panel'), false);
  // 搜索词命中角色名时角色行正常出现
  search.value = 'deepseek';
  search.fire('input', { target: search });
  assert.equal(h.rows().length, 2); // 项目设置 + DeepSeek
  assert.equal(h.rows()[1].children[0].textContent, 'DeepSeek');
});

test('名册为空但项目存在：仍可进入项目设置配置开发要求、看到主控状态', async () => {
  const h = harness({ roster: [] });
  await h.enterRoles();
  assert.equal(h.settingsRow().children[0].textContent, '项目设置');
  assert.ok(allTexts(h.el('blackboard-columns')).some(t => t.includes('这个项目还没有配置角色')));
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(h.hidden('controller-panel'), false);
  // 开发要求读取与编辑照常（项目存在即可，不依赖名册）
  h.replyProjectReads({ project_id: 'A', development_requirements: '已有要求', ...CONTROLLER_READ });
  await h.flush();
  const input = h.el('requirements-input');
  assert.equal(input.value, '已有要求');
  assert.equal(input.disabled, false);
  // 主控读取完成：未指定且无可选名册成员时，候选选择器给出空候选提示且不可提交
  const assignRow = h.el('controller-assign-row');
  assert.equal(assignRow.classList.contains('hidden'), false);
  const select = h.el('controller-candidate-select');
  assert.deepEqual(select.children.map(o => o.textContent), ['暂无可指定的名册内 Agent']);
  assert.equal(h.el('controller-assign-btn').disabled, true);
});

test('互斥切换：点角色只显示角色详情，点项目设置只显示项目级面板，不残留空白面板', async () => {
  const h = harness();
  await h.enterRoles();
  h.replyProjectReads({ project_id: 'A', development_requirements: null, ...CONTROLLER_READ });
  await h.flush();
  // 点具体角色
  h.roleRow('agent:deepseek').fire('click');
  await h.flush();
  assert.equal(h.ui.roleSelection, 'role');
  assert.equal(h.ui.selectedRole, 'agent:deepseek');
  assert.equal(h.hidden('role-details-panel'), false);
  assert.equal(h.hidden('requirements-panel'), true);
  assert.equal(h.hidden('controller-panel'), true);
  // 角色详情确实渲染了内容（不是残留空白面板）
  const details = h.el('role-details-panel');
  assert.ok(allTexts(details).some(t => t.includes('DeepSeek')));
  assert.ok(allTexts(details).some(t => t.includes('参与的任务')));
  // 回到项目设置：角色详情整体隐藏
  h.settingsRow().fire('click');
  await h.flush();
  assert.equal(h.hidden('role-details-panel'), true);
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(h.hidden('controller-panel'), false);
  assert.equal(h.ui.selectedRole, 'agent:deepseek', '角色选择保留，仅切换查看对象');
});

test('角色详情不再提供“交办任务”入口；参与任务“查看任务”等原功能保留', async () => {
  const h = harness();
  h.context.projectTasks = [
    { id: 5, root_task_id: 5, title: '样例任务', target_member_id: 'agent:deepseek', created_by: 'human:qa', workflow_status: 'in_progress', claimed_at: '2026-09-20T09:00:00', finished_at: null },
  ];
  h.ui.roleFilter = 'running'; // 参与任务表默认“已结束”筛选，切到进行中
  await h.enterRoles();
  h.roleRow('agent:deepseek').fire('click');
  await h.flush();
  const details = h.el('role-details-panel');
  const texts = allTexts(details);
  assert.ok(!texts.some(t => t.includes('交办任务')), '角色详情不再有“交办任务”快捷入口');
  assert.ok(!findAll(details, n => n.tagName === 'button').some(b => (b.textContent || '').includes('交办')));
  const viewButtons = findAll(details, n => n.tagName === 'button' && n.textContent === '查看任务');
  assert.equal(viewButtons.length, 1, '参与任务“查看任务”保留');
  viewButtons[0].fire('click');
  // 查看任务仍走真实 selectWorkspaceTask 导航：切到任务模式并选中该任务
  assert.equal(h.ui.mode, 'tasks');
  assert.equal(h.context.selectedTaskId, 5);
  // 全局任务创建入口不动：shared 创建弹窗与函数仍在源码中
  assert.match(appSource, /function setTaskCreateOpen\(/);
  assert.match(appSource, /function renderTaskCreateAgentOptions\(/);
});

test('主控集中在项目设置页：候选选择器指定、列表徽标与角色详情标记保留、详情无管理面板', async () => {
  const h = harness();
  await h.enterRoles();
  h.replyProjectReads({ project_id: 'A', development_requirements: null, ...CONTROLLER_READ });
  await h.flush();
  // 候选选择器列出名册内未禁用 agent，禁用成员不出现，同名角色带 member_id 消歧
  const select = h.el('controller-candidate-select');
  assert.deepEqual(select.children.map(o => o.value), ['agent:kimi', 'agent:kimi2', 'agent:deepseek']);
  assert.ok(select.children.every(o => /（agent:/.test(o.textContent)));
  // 通过真实“设为项目主控”按钮发起指定（顶部事件绑定来自真实 workspace.js）
  select.value = 'agent:kimi2';
  h.el('controller-assign-btn').fire('click');
  const patch = h.pending.find(p => p.opts?.method === 'PATCH');
  assert.match(patch.url, /\/api\/projects\/A\/controller-assignment$/);
  assert.deepEqual(JSON.parse(patch.opts.body), { member_id: 'agent:kimi2', expected_version: 0 });
  h.reply(h.pending.indexOf(patch), { project_id: 'A', controller_member_id: 'agent:kimi2', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await h.flush();
  // 指定后：候选行可见但置灰、显示先解除理由，解除入口可用
  assert.equal(h.el('controller-assign-row').classList.contains('hidden'), false);
  assert.equal(select.disabled, true);
  assert.equal(h.el('controller-assign-btn').disabled, true);
  const writesBefore = h.pending.length;
  select.value = 'agent:kimi';
  h.el('controller-assign-btn').fire('click');
  await h.flush();
  assert.equal(h.pending.length, writesBefore, '即使触发禁用按钮处理器也不能覆盖已有主控');
  assert.match(h.el('controller-detail').textContent, /请先解除当前指定，再另选/);
  assert.equal(h.hidden('controller-clear-btn'), false);
  // 列表徽标按 member_id 消歧落在 kimi2 行，首项“项目设置”不带徽标
  assert.ok(allTexts(h.roleRow('agent:kimi2')).some(t => t.includes('项目主控')), '列表保留主控标记');
  assert.ok(!allTexts(h.settingsRow()).some(t => t.includes('项目主控（')));
  // 角色详情只保留标记，没有指定/解除管理控件
  h.roleRow('agent:kimi2').fire('click');
  await h.flush();
  const details = h.el('role-details-panel');
  assert.ok(allTexts(details).some(t => t.includes('项目主控（当前指定）')));
  const buttons = findAll(details, n => n.tagName === 'button').map(b => b.textContent || '');
  assert.ok(!buttons.some(t => /设为项目主控|解除主控/.test(t)), '角色详情不再重复主控管理面板');
  // 解除走设置页真实按钮
  h.settingsRow().fire('click');
  await h.flush();
  h.el('controller-clear-btn').fire('click');
  const clear = h.pending.filter(p => p.opts?.method === 'PATCH').at(-1);
  assert.deepEqual(JSON.parse(clear.opts.body), { member_id: null, expected_version: 1 });
  h.reply(h.pending.indexOf(clear), { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await h.flush();
  assert.equal(h.el('controller-assign-row').classList.contains('hidden'), false, '解除后候选选择器保持可见');
  assert.equal(select.disabled, false);
  assert.equal(h.el('controller-assign-btn').disabled, false);
});

test('agent 账号在项目设置页只读：无指定/解除入口，但能看到当前指定状态', async () => {
  const h = harness({ human: false });
  await h.enterRoles();
  h.replyProjectReads({
    project_id: 'A', development_requirements: '只读要求',
    controller_member_id: 'agent:deepseek', controller_assignment_version: 4, controller_assignment_status: 'assigned',
  });
  await h.flush();
  assert.equal(h.el('controller-assign-row').classList.contains('hidden'), true);
  assert.equal(h.hidden('controller-clear-btn'), true);
  assert.match(h.el('controller-current').textContent, /DeepSeek（agent:deepseek）/);
  assert.match(h.el('controller-status').textContent, /只能查看/);
  assert.equal(h.el('requirements-input').readOnly, true);
  assert.equal(h.el('requirements-save-btn').disabled, true);
});

test('REQ-2 草稿：项目设置 ↔ 具体角色切换不丢未保存草稿，同项目不重读', async () => {
  const h = harness();
  await h.enterRoles();
  h.replyProjectReads({ project_id: 'A', development_requirements: '已保存内容', ...CONTROLLER_READ });
  await h.flush();
  const input = h.el('requirements-input');
  input.value = '未保存草稿 v1';
  input.fire('input');
  const readsBefore = h.pending.length;
  // 切到具体角色再切回：草稿保留，不重新读取，不误标已保存
  h.roleRow('agent:kimi').fire('click');
  await h.flush();
  assert.equal(h.hidden('requirements-panel'), true);
  h.settingsRow().fire('click');
  await h.flush();
  assert.equal(h.hidden('requirements-panel'), false);
  assert.equal(input.value, '未保存草稿 v1');
  assert.equal(h.pending.length, readsBefore);
  assert.match(h.el('requirements-status').textContent, /未保存/);
});

test('切项目不串选：setActiveProject 重置为“项目设置”，返回角色页不把旧项目选择带过来', async () => {
  const h = harness();
  await h.enterRoles();
  h.roleRow('agent:kimi').fire('click');
  await h.flush();
  assert.equal(h.ui.roleSelection, 'role');
  assert.equal(h.ui.selectedRole, 'agent:kimi');
  // 真实 setActiveProject 路径切到项目 B
  const switching = h.context.setActiveProject('B');
  assert.equal(h.ui.roleSelection, 'settings');
  assert.equal(h.ui.selectedRole, null);
  await switching;
  // 返回项目 A 也不复活旧选择（状态已在切换时重置）
  const back = h.context.setActiveProject('A');
  assert.equal(h.context.workspaceSettingsSelected(), true);
  await back;
});

test('页面结构断言：设置首项导航独立于名册，源码中角色详情无交办/主控管理入口', () => {
  // 实际调用路径之上再做结构兜底：角色详情函数不再出现交办入口与主控管理渲染
  const roleFn = functionSource(wsSource, 'renderWorkspaceRoleDetails');
  assert.ok(!/workspaceButton\([^)]*交办/.test(roleFn), '角色详情移除交办任务按钮');
  assert.ok(!roleFn.includes('setTaskCreateOpen'), '角色详情不再绑定共享创建弹窗预选');
  assert.ok(!roleFn.includes('saveControllerAssignment'), '角色详情不再发起主控写操作');
  assert.ok(roleFn.includes('workspaceControllerBadge(role.member_id)'), '角色详情保留主控标记');
  assert.ok(roleFn.includes('查看任务'), '参与任务查看入口保留');
  // 共享任务创建系统保留（其它页面入口不动）
  assert.match(wsSource, /function syncControllerCandidates\(/);
  assert.match(appSource, /taskCreateAgent\.value/);
  // 不新增高频轮询/计时器
  assert.ok(!wsSource.includes('setInterval'));
});
