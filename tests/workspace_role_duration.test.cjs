// ROLE-1：角色展示映射统一 + 参与任务表“执行耗时”列的定向测试。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function functionSource(source, name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  assert.ok(start >= 0 && end >= 0, `未找到函数 ${name}`);
  return rest.slice(0, end + 1);
}

// ── 最小 DOM 桩：只实现 workspace.js 实际用到的节点能力 ─────────────────
function fakeElement(tag) {
  const el = {
    tagName: tag, className: '', textContent: '', value: '', scope: '', type: '', disabled: false,
    dataset: {}, attrs: {}, children: [],
    appendChild(c) { el.children.push(c); return c; },
    append(...cs) { el.children.push(...cs); },
    replaceChildren() { el.children = []; },
    insertBefore(node, ref) {
      const i = el.children.indexOf(ref);
      el.children.splice(i < 0 ? el.children.length : i, 0, node);
      return node;
    },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    addEventListener() {},
    classList: {
      _s: new Set(),
      add(...cs) { cs.forEach(c => this._s.add(c)); },
      remove(...cs) { cs.forEach(c => this._s.delete(c)); },
      toggle(c, force) {
        const on = force === undefined ? !this._s.has(c) : !!force;
        if (on) this._s.add(c); else this._s.delete(c);
        return on;
      },
      contains(c) { return this._s.has(c); },
    },
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

// 在 vm 中运行整份 workspace.js（剥掉顶层 workspaceUI 常量，改用可控实例），
// 使 renderWorkspaceRoleDetails 以其真实依赖做真实渲染。
function workspaceContext({ roles, membersList, tasks, selectedRole, roleFilter }) {
  const panel = fakeElement('div');
  const elements = { 'role-details-panel': panel };
  const documentStub = {
    createElement: tag => fakeElement(tag),
    getElementById: id => elements[id] || (elements[id] = fakeElement('div')),
  };
  const context = vm.createContext({
    document: documentStub,
    blackboardOpen: true,
    activeProjectId: 'p1',
    myId: 'human:qa',
    members: membersList,
    projectAgents: roles,
    projectTasks: tasks,
    workspaceUI: { mode: 'roles', selectedRole, roleFilter, result: null, resultRequest: 0, renderedTask: null },
    eligibleProjectAgents: () => [],
    setTaskCreateOpen: () => {},
    taskCreateAgent: { value: '' },
    window: { matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(wsSource.replace(/const workspaceUI = \{[^}]*\};/, ''), context);
  vm.runInContext(functionSource(appSource, 'taskStatusMeta'), context);
  return { context, panel };
}

const EXEC_LABEL = '执行工作';
const EXEC_DESC = '负责执行分配的工作、提交完成结果，并交叉验证其他角色的成果。';

test('角色展示映射：lead 保持统筹，dev/developer/reviewer 统一执行工作，其他类别不变', () => {
  assert.equal(helpers.workspaceRoleLabel('lead'), '统筹任务');
  assert.equal(helpers.workspaceRoleLabel('dev'), EXEC_LABEL);
  assert.equal(helpers.workspaceRoleLabel('developer'), EXEC_LABEL);
  assert.equal(helpers.workspaceRoleLabel('reviewer'), EXEC_LABEL);
  assert.equal(helpers.workspaceRoleLabel('tester'), '测试验证');
  assert.equal(helpers.workspaceRoleLabel('ui'), '界面设计');
  assert.equal(helpers.workspaceRoleLabel('custom-role'), 'custom-role');
  assert.equal(helpers.workspaceRoleLabel(''), '项目助手');
  assert.equal(helpers.workspaceRoleDescription('lead'), '负责分配工作、跟进进度，并汇总最终成果。');
  assert.equal(helpers.workspaceRoleDescription('dev'), EXEC_DESC);
  assert.equal(helpers.workspaceRoleDescription('developer'), EXEC_DESC);
  assert.equal(helpers.workspaceRoleDescription('reviewer'), EXEC_DESC);
  assert.equal(helpers.workspaceRoleDescription('tester'), '负责验证成果是否符合要求，并提交测试结论。');
  assert.equal(helpers.workspaceRoleDescription('ui'), undefined);
  assert.equal(helpers.workspaceRoleDescription('custom-role'), undefined);
});

test('耗时单元：执行中挂统一计时器标识，终态冻结，缺/负时间显示 —，超 24 小时不回卷', () => {
  global.document = { createElement: tag => fakeElement(tag) };
  try {
    const running = helpers.workspaceTaskDurationEl({ id: 7, workflow_status: 'in_progress', claimed_at: '2020-01-01T00:00:00', finished_at: null });
    assert.equal(running.className, 'task-card-duration');
    assert.equal(running.dataset.taskId, '7');
    assert.equal(running.dataset.running, '1');
    assert.match(running.textContent, /^\d{2,}:\d{2}:\d{2}$/);
    const finished = helpers.workspaceTaskDurationEl({ id: 8, workflow_status: 'completed', claimed_at: '2026-09-18T09:00:00', finished_at: '2026-09-18T09:05:24' });
    assert.equal(finished.textContent, '00:05:24');
    assert.equal(finished.dataset.running, undefined);
    const missing = helpers.workspaceTaskDurationEl({ id: 9, workflow_status: 'canceled', claimed_at: null, finished_at: '2026-09-18T10:00:00' });
    assert.equal(missing.textContent, '—');
    assert.equal(missing.dataset.running, undefined);
    const negative = helpers.workspaceTaskDurationEl({ id: 11, workflow_status: 'failed', claimed_at: '2026-09-18T10:00:00', finished_at: '2026-09-18T09:00:00' });
    assert.equal(negative.textContent, '—');
    const long = helpers.workspaceTaskDurationEl({ id: 10, workflow_status: 'completed', claimed_at: '2026-09-17T08:00:00', finished_at: '2026-09-18T10:30:00' });
    assert.equal(long.textContent, '26:30:00');
    // in_progress 但 finished_at 已存在：按结束冻结，不再挂 running 标识
    const frozen = helpers.workspaceTaskDurationEl({ id: 12, workflow_status: 'in_progress', claimed_at: '2026-09-18T09:00:00', finished_at: '2026-09-18T09:02:00' });
    assert.equal(frozen.textContent, '00:02:00');
    assert.equal(frozen.dataset.running, undefined);
  } finally {
    delete global.document;
  }
});

function roleFixture() {
  const membersList = [
    { id: 'human:qa', kind: 'human', display_name: 'bobo' },
    { id: 'agent:codex', kind: 'agent', display_name: 'codex CLI Bridge (agent:codex)' },
    { id: 'agent:kimi', kind: 'agent', display_name: 'kimi CLI Bridge (agent:kimi)' },
    { id: 'agent:deepseek', kind: 'agent', display_name: 'dsh CLI Bridge (agent:deepseek)' },
    { id: 'agent:altdev', kind: 'agent', display_name: 'AltDev' },
  ];
  const roles = [
    { member_id: 'agent:codex', business_role: 'lead' },
    { member_id: 'agent:kimi', business_role: 'reviewer' },
    { member_id: 'agent:deepseek', business_role: 'dev' },
    { member_id: 'agent:altdev', business_role: 'developer' },
  ];
  const tasks = [
    { id: 1, root_task_id: 1, title: '执行任务A', target_member_id: 'agent:kimi', created_by: 'human:qa', workflow_status: 'in_progress', claimed_at: '2026-09-18T09:00:00', finished_at: null },
    { id: 2, root_task_id: 2, title: '历史任务B', target_member_id: 'agent:kimi', created_by: 'human:qa', workflow_status: 'completed', claimed_at: '2026-09-18T09:01:45', finished_at: '2026-09-18T09:05:24' },
    { id: 3, root_task_id: 3, title: '委派任务C', target_member_id: 'agent:deepseek', created_by: 'agent:kimi', workflow_status: 'in_progress', claimed_at: '2026-09-18T08:00:00', finished_at: null },
  ];
  return { membersList, roles, tasks };
}

test('角色详情真实渲染：表头为 任务/执行耗时/任务状态/操作，不再展示承担工作', () => {
  const { membersList, roles, tasks } = roleFixture();
  const { context, panel } = workspaceContext({ roles, membersList, tasks, selectedRole: 'agent:kimi', roleFilter: 'running' });
  context.renderWorkspaceRoleDetails();
  assert.deepEqual(findAll(panel, n => n.tagName === 'th').map(n => n.textContent), ['任务', '执行耗时', '任务状态', '操作']);
  const texts = allTexts(panel);
  for (const gone of ['承担工作', '统筹与汇总', '委派与跟进', '检查工作']) {
    assert.ok(!texts.some(t => t.includes(gone)), `不应再出现：${gone}`);
  }
  // reviewer/Kimi 显示执行工作标签与统一说明；原始 business_role 不被改写
  assert.ok(texts.includes(EXEC_LABEL));
  assert.ok(texts.includes(EXEC_DESC));
  assert.equal(roles.find(r => r.member_id === 'agent:kimi').business_role, 'reviewer');
  // 进行中筛选：执行中任务挂 running 标识，状态与操作列保留
  const durations = findAll(panel, n => n.className === 'task-card-duration');
  assert.deepEqual(durations.map(n => n.dataset.taskId).sort(), ['1', '3']);
  for (const d of durations) assert.equal(d.dataset.running, '1');
  assert.ok(texts.includes('执行中'));
  assert.deepEqual(findAll(panel, n => n.tagName === 'button' && n.textContent === '查看任务').length, 2);
  // 已结束筛选：终态耗时冻结，无 running 标识
  context.workspaceUI.roleFilter = 'finished';
  context.renderWorkspaceRoleDetails();
  const done = findAll(panel, n => n.className === 'task-card-duration');
  assert.equal(done.length, 1);
  assert.equal(done[0].textContent, '00:03:39');
  assert.equal(done[0].dataset.running, undefined);
});

test('真实角色渲染：lead 保持统筹原文，dev/developer 与 reviewer 说明一致', () => {
  const { membersList, roles, tasks } = roleFixture();
  const { context, panel } = workspaceContext({ roles, membersList, tasks, selectedRole: 'agent:codex', roleFilter: 'running' });
  context.renderWorkspaceRoleDetails();
  let texts = allTexts(panel);
  assert.ok(texts.includes('统筹任务'));
  assert.ok(texts.includes('负责分配工作、跟进进度，并汇总最终成果。'));
  assert.ok(!texts.includes(EXEC_DESC));
  // developer 与 dev 同义：altdev(developer) 显示与执行角色相同的标签和说明
  context.workspaceUI.selectedRole = 'agent:altdev';
  context.renderWorkspaceRoleDetails();
  texts = allTexts(panel);
  assert.ok(texts.includes(EXEC_LABEL));
  assert.ok(texts.includes(EXEC_DESC));
  // 无参与任务的角色保持空状态
  context.renderWorkspaceRoleDetails();
  assert.ok(allTexts(panel).includes('当前没有这类任务。'));
});

test('同一任务在任务列表与角色表并存时，单计时器同时刷新两处耗时', () => {
  const task = { id: 1, workflow_status: 'in_progress', claimed_at: '2026-09-18T09:00:00', finished_at: null };
  const listEl = { className: 'task-card-duration', dataset: { taskId: '1', running: '1' }, textContent: '' };
  const roleEl = { className: 'task-card-duration', dataset: { taskId: '1', running: '1' }, textContent: '' };
  const context = vm.createContext({
    ...helpers,
    projectTasks: [task],
    document: { querySelectorAll: () => [listEl, roleEl] },
  });
  vm.runInContext(functionSource(appSource, 'tickTaskDurations'), context);
  context.tickTaskDurations(Date.UTC(2026, 8, 18, 9, 0, 30));
  assert.equal(listEl.textContent, '00:00:30');
  assert.equal(roleEl.textContent, '00:00:30');
  // 第二次 tick 按真实时间重算，两处同步更新
  context.tickTaskDurations(Date.UTC(2026, 8, 18, 9, 1, 5));
  assert.equal(listEl.textContent, '00:01:05');
  assert.equal(roleEl.textContent, '00:01:05');
});

test('源码契约：参与集合逻辑不变，taskKindLabel 保留给其他页面，全仓库仍只有一个耗时计时器', () => {
  const roleFn = functionSource(wsSource, 'renderWorkspaceRoleDetails');
  assert.match(roleFn, /\["任务", "执行耗时", "任务状态", "操作"\]/);
  assert.ok(!roleFn.includes('"承担工作"'));
  assert.ok(!roleFn.includes('统筹与汇总'));
  assert.ok(!roleFn.includes('委派与跟进'));
  assert.ok(!roleFn.includes('taskKindLabel'));
  assert.match(roleFn, /workspaceTaskDurationEl\(task\)/);
  assert.match(roleFn, /workspaceRoleDescription\(role\.business_role\)/);
  // 参与任务集合与委派关系筛选逻辑保持不变
  assert.match(wsSource, /task\.target_member_id === id \|\| \(task\.created_by === id/);
  // taskKindLabel 能力保留（任务流转等其它页面继续使用）
  assert.match(appSource, /function taskKindLabel\(kind\)/);
  assert.match(wsSource, /taskKindLabel\(child\.task_kind\)/);
  // workspace.js 不新增任何计时器；app.js 仍只有一处 tickTaskDurations setInterval
  assert.ok(!wsSource.includes('setInterval'));
  assert.equal((appSource.match(/setInterval\(tickTaskDurations/g) || []).length, 1);
  // 计时器选择器兼容角色表单元：按 class + data-running 标识全局匹配
  assert.match(appSource, /querySelectorAll\("\.task-card-duration\[data-running='1'\]"\)/);
});
