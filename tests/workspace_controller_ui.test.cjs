// C1b-S2/ROLE-SETTINGS-1 角色页项目主控：状态/DOM 异步测试。
// 通过 vm 抽取 workspace.js 中 C1b-S2 代码块，用 DOM 存根验证 human/agent、同名角色、
// 空/有指定、候选选择器、先解除理由、解除再指定、失效成员仍可解除、旧后端/无项目/错误、
// double submit、409/400 重读不自动写、切项目/账号迟到响应、版本安全边界与 REQ-2 草稿隔离。
// ROLE-SETTINGS-1 起主控管理集中在“项目设置”页：指定走面板候选选择器 + 设为按钮，
// 角色详情不再提供管理入口；焦点去向相应落在面板控件上。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');

const workspaceSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const blockStart = workspaceSource.indexOf('// ── C1b-S2 项目主控指定');
const blockEnd = workspaceSource.indexOf('function workspaceTaskNotice(');
assert.ok(blockStart > 0 && blockEnd > blockStart, 'C1b-S2 代码块边界');
const controllerBlock = workspaceSource.slice(blockStart, blockEnd);

function fakeEl(id, onFocus) {
  const classes = new Set(id === 'controller-panel' ? [] : []);
  const el = {
    id, value: '', textContent: '', className: '', disabled: false, title: '',
    dataset: {}, children: [], focusCalls: 0,
    classList: {
      add: c => classes.add(c),
      remove: c => classes.delete(c),
      toggle: (c, force) => { const on = force === undefined ? !classes.has(c) : force; on ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    addEventListener() {},
    appendChild(child) { el.children.push(child); return child; },
    replaceChildren() { el.children.length = 0; },
    // 浏览器行为近似：hidden/disabled 元素不可聚焦。
    focus() { if (classes.has('hidden') || el.disabled) return; el.focusCalls++; if (onFocus) onFocus(el); },
  };
  return el;
}

const MEMBERS = [
  { id: 'human:qa', kind: 'human', display_name: 'bobo' },
  { id: 'agent:kimi', kind: 'agent', display_name: '助手' },
  { id: 'agent:kimi2', kind: 'agent', display_name: '助手' }, // 同名角色，用 member_id 消歧
  { id: 'agent:deepseek', kind: 'agent', display_name: 'DeepSeek' },
  { id: 'agent:offsite', kind: 'agent', display_name: 'Outsider' }, // 不在名册
  { id: 'agent:banned', kind: 'agent', display_name: 'Banned', disabled_at: '2026-09-19T00:00:00' },
];
const ROSTER = [
  { member_id: 'agent:kimi', business_role: 'reviewer' },
  { member_id: 'agent:kimi2', business_role: 'reviewer' },
  { member_id: 'agent:deepseek', business_role: 'dev' },
  { member_id: 'agent:banned', business_role: 'dev' },
];

function harness({ human = true, projectId = 'A' } = {}) {
  const pending = [];
  const elements = new Map();
  // ROLE-SETTINGS-1：主控控件固定在“项目设置”页（controller-assign-btn/controller-clear-btn）。
  // actionButtons 仅用于个别用例模拟“同动作节点被置灰/隐藏”的覆盖层；默认 querySelector
  // 命中真实面板元素，焦点断言直接落在面板控件上，不再需要模拟角色详情按钮的增删。
  const actionButtons = [];
  let settingsSelected = true; // 本项目设置页为选中状态；用例可切换为具体角色选择
  const document = {
    getElementById: id => {
      if (!elements.has(id)) {
        const node = fakeEl(id, el => { document.activeElement = el; });
        if (id === 'controller-assign-btn') node.dataset.controllerAction = 'assign';
        if (id === 'controller-clear-btn') node.dataset.controllerAction = 'clear';
        elements.set(id, node);
      }
      return elements.get(id);
    },
    createElement: tag => fakeEl(tag),
    activeElement: null,
    body: fakeEl('body'),
    querySelector: sel => {
      const m = /^\[data-controller-action="(.+)"\]$/.exec(sel);
      if (!m) return null;
      const override = actionButtons.find(n => !n._removed && n.dataset.controllerAction === m[1]);
      if (override) return override;
      const id = m[1] === 'assign' ? 'controller-assign-btn' : m[1] === 'clear' ? 'controller-clear-btn' : null;
      return id ? document.getElementById(id) : null;
    },
  };
  const addActionButton = (action, { disabled = false, hidden = false } = {}) => {
    const btn = fakeEl(`action-${action}-${actionButtons.length}`, el => { document.activeElement = el; });
    btn.dataset.controllerAction = action;
    btn.disabled = disabled;
    if (hidden) btn.classList.add('hidden');
    actionButtons.push(btn);
    return btn;
  };
  const calls = { list: 0, details: 0 };
  const context = vm.createContext({
    workspaceUI: { mode: 'roles' }, blackboardOpen: true,
    activeProjectId: projectId, myId: human ? 'human:qa' : 'agent:kimi',
    members: MEMBERS, projectAgents: ROSTER,
    projects: [
      { project_id: 'A', development_requirements: 'REQ2草稿', controller_member_id: null },
      { project_id: 'B', development_requirements: 'B要求', controller_member_id: null },
    ],
    currentMemberIsHuman: () => human,
    // ROLE-SETTINGS-1：面板只在“项目设置”选中时可见；本 harness 用闭包开关模拟选中具体角色。
    workspaceSettingsSelected: () => settingsSelected,
    apiFetch: (url, opts) => new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject })),
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    workspaceEl: (tag, className, text) => ({ tag, className: className || '', textContent: text ?? '', dataset: {} }),
    workspaceButton: (text, handler, className) => ({ textContent: text, className, dataset: {}, disabled: false, title: '', setAttribute() {} }),
    workspaceMemberName: id => (MEMBERS.find(m => m.id === id) || {}).display_name || String(id).replace(/^(agent|human):/, ''),
    workspaceRoles: () => ROSTER.filter(a => !MEMBERS.find(m => m.id === a.member_id)?.disabled_at),
    renderWorkspaceList: () => { calls.list++; },
    renderWorkspaceRoleDetails: () => { calls.details++; },
    document,
  });
  vm.runInContext(controllerBlock, context);
  // const 声明不挂到 context 对象，显式暴露引用便于断言。
  vm.runInContext('this.__ui = controllerUI;', context);
  const ui = context.__ui;
  const el = id => document.getElementById(id);
  const reply = (index, data, { ok = true, status = 200 } = {}) =>
    pending[index].resolve({ ok, status, json: async () => data });
  const fail = (index, err) => pending[index].reject(err);
  // 进入角色页项目设置（首次触发上下文加载）；project 响应带主控三字段。
  async function enter(project = projectId, read = {}) {
    context.activeProjectId = project;
    const request = context.renderControllerPanel();
    const index = pending.length - 1;
    reply(index, {
      project_id: project,
      controller_member_id: null,
      controller_assignment_version: 0,
      controller_assignment_status: 'unassigned',
      ...read,
    });
    await request;
  }
  const setSettingsSelected = value => { settingsSelected = value; };
  return { context, pending, reply, fail, el, ui, calls, enter, document, actionButtons, addActionButton, setSettingsSelected };
}

test('状态映射：六种已知状态如实呈现，未知状态降级为无法识别', () => {
  assert.equal(helpers.controllerStatusMeta('unassigned').label, '未指定');
  assert.equal(helpers.controllerStatusMeta('assigned').label, '已指定');
  assert.ok(!helpers.controllerStatusMeta('assigned').reason);
  for (const status of ['not_in_roster', 'member_disabled', 'member_missing', 'not_agent']) {
    assert.equal(helpers.controllerStatusMeta(status).label, '已指定 · 当前不可用');
    assert.ok(helpers.controllerStatusMeta(status).reason, status);
  }
  const unknown = helpers.controllerStatusMeta('lease_active');
  assert.equal(unknown.label, '指定状态无法识别');
  assert.match(unknown.reason, /lease_active/);
});

test('无项目或未登录时面板隐藏且不发起请求', () => {
  const { context, pending, el } = harness();
  context.activeProjectId = null;
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  context.activeProjectId = 'A'; context.myId = null;
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  assert.equal(pending.length, 0);
});

test('human 未指定：显示未指定，候选选择器列出名册内角色，写请求用 member_id 与读取版本', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  assert.equal(el('controller-panel').classList.contains('hidden'), false);
  assert.equal(el('controller-current').textContent, '项目主控：未指定');
  assert.match(el('controller-detail').textContent, /长期保存/);
  // 候选选择器：名册内已注册未禁用的 agent（kimi/kimi2/deepseek），禁用成员不出现，带 member_id 消歧
  assert.equal(el('controller-assign-row').classList.contains('hidden'), false);
  const select = el('controller-candidate-select');
  assert.deepEqual(select.children.map(o => o.value), ['agent:kimi', 'agent:kimi2', 'agent:deepseek']);
  assert.match(select.children[0].textContent, /助手（agent:kimi）/);
  assert.equal(select.disabled, false);
  assert.equal(el('controller-assign-btn').disabled, false);
  // 同值 no-op 不发请求；版本 0 正常可用
  const before = context.__ui.request;
  await context.saveControllerAssignment(null);
  assert.equal(context.__ui.request, before);
  select.value = 'agent:kimi';
  const save = context.saveControllerAssignment(select.value);
  assert.equal(ui.saving, true);
  assert.match(pending[pending.length - 1].url, /\/api\/projects\/A\/controller-assignment$/);
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { member_id: 'agent:kimi', expected_version: 0 });
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(ui.saving, false);
  assert.match(el('controller-current').textContent, /助手（agent:kimi）/);
  // 已有指定后候选行可见但置灰，不能再直接指定他人
  assert.equal(el('controller-assign-row').classList.contains('hidden'), false);
  assert.equal(el('controller-candidate-select').disabled, true);
  assert.equal(el('controller-assign-btn').disabled, true);
});

test('agent 账号只读：无写入入口并给出说明，但仍能看到指定状态', async () => {
  const { context, el, enter } = harness({ human: false });
  await enter('A', { controller_member_id: 'agent:deepseek', controller_assignment_version: 3, controller_assignment_status: 'assigned' });
  assert.match(el('controller-current').textContent, /DeepSeek（agent:deepseek）/);
  assert.equal(el('controller-clear-btn').classList.contains('hidden'), true);
  assert.equal(el('controller-assign-row').classList.contains('hidden'), true);
  assert.match(el('controller-status').textContent, /Agent，只能查看/);
  // 指定角色的徽标对 agent 同样可见
  assert.equal(context.workspaceControllerBadge('agent:deepseek'), true);
  assert.equal(context.workspaceControllerBadge('agent:kimi'), false);
});

test('已有指定：候选选择器可见但置灰并显示先解除理由；同名角色按 member_id 消歧', async () => {
  const { context, el, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi2', controller_assignment_version: 5, controller_assignment_status: 'assigned' });
  assert.match(el('controller-current').textContent, /助手（agent:kimi2）/);
  assert.match(el('controller-detail').textContent, /不代表在线、已确认或会话已生效/);
  // 先解除理由明确，指定入口保留但不可用
  assert.match(el('controller-detail').textContent, /请先解除当前指定，再另选/);
  assert.equal(el('controller-assign-row').classList.contains('hidden'), false);
  assert.equal(el('controller-candidate-select').disabled, true);
  assert.equal(el('controller-assign-btn').disabled, true);
  // 同名角色 kimi 与 kimi2：徽标只落在被指定的 member_id 上
  assert.equal(context.workspaceControllerBadge('agent:kimi2'), true);
  assert.equal(context.workspaceControllerBadge('agent:kimi'), false);
  // 面板解除入口对 human 可用
  assert.equal(el('controller-clear-btn').classList.contains('hidden'), false);
  assert.equal(el('controller-clear-btn').disabled, false);
});

test('解除再指定：两次写各自携带最新读取版本；项目缓存只回写主控字段', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  // 解除：显式 null + expected_version=1
  const clear = context.saveControllerAssignment(null);
  const clearReq = pending[pending.length - 1];
  assert.match(clearReq.url, /\/api\/projects\/A\/controller-assignment$/);
  assert.equal(clearReq.opts.method, 'PATCH');
  assert.deepEqual(JSON.parse(clearReq.opts.body), { member_id: null, expected_version: 1 });
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await clear;
  assert.equal(ui.assignedId, null);
  assert.equal(ui.version, 2);
  assert.match(ui.notice, /已解除/);
  // 再指定另一名角色：携带解除后的版本 2
  const assign = context.saveControllerAssignment('agent:deepseek');
  const assignReq = pending[pending.length - 1];
  assert.deepEqual(JSON.parse(assignReq.opts.body), { member_id: 'agent:deepseek', expected_version: 2 });
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:deepseek', controller_assignment_version: 3, controller_assignment_status: 'assigned' });
  await assign;
  assert.equal(ui.assignedId, 'agent:deepseek');
  assert.match(ui.notice, /已保存。已指定仅表示职责配置有效，不代表在线或已确认/);
  // 项目缓存只回写主控三字段，开发要求原样保留
  const project = context.projects[0];
  assert.equal(project.controller_member_id, 'agent:deepseek');
  assert.equal(project.controller_assignment_version, 3);
  assert.equal(project.development_requirements, 'REQ2草稿');
});

test('失效成员（禁用/移出名册/不存在）仍显示名称或 ID、无效原因，human 可解除', async () => {
  for (const [status, reason] of [
    ['member_disabled', /已被禁用/],
    ['not_in_roster', /不在项目名册中/],
    ['member_missing', /已不存在/],
    ['not_agent', /不是 Agent/],
  ]) {
    const { context, pending, reply, el, ui, enter } = harness();
    await enter('A', { controller_member_id: 'agent:ghost', controller_assignment_version: 7, controller_assignment_status: status });
    assert.match(el('controller-current').textContent, /ghost（agent:ghost）/);
    assert.match(el('controller-detail').textContent, reason);
    assert.match(el('controller-detail').textContent, /仍长期保存/);
    // 失效指定仍占用唯一主控位，候选指定入口保持可见但禁用
    assert.equal(el('controller-assign-row').classList.contains('hidden'), false);
    assert.equal(el('controller-candidate-select').disabled, true);
    assert.equal(el('controller-assign-btn').disabled, true);
    // human 解除入口可用
    assert.equal(el('controller-clear-btn').classList.contains('hidden'), false);
    const clear = context.saveControllerAssignment(null);
    reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 8, controller_assignment_status: 'unassigned' });
    await clear;
    assert.equal(ui.assignedId, null);
    assert.match(ui.notice, /已解除/);
  }
});

test('S1 竞态如实呈现：PATCH 200 但状态 not_in_roster 时提示“已保存但当前不可用”', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  const save = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'not_in_roster' });
  await save;
  assert.match(ui.notice, /已保存，但当前不可用：该成员当前不在项目名册中/);
  assert.match(ui.notice, /可解除后另选/);
  assert.ok(!/已就绪|已生效|在线/.test(ui.notice));
});

test('double submit 防护：保存中第二次写入直接返回，只有一个 PATCH', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  const first = context.saveControllerAssignment('agent:kimi');
  assert.equal(ui.saving, true);
  await context.saveControllerAssignment('agent:deepseek'); // 应被 saving 拦截
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 1);
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await first;
  assert.equal(ui.assignedId, 'agent:kimi');
});

test('409 冲突：重新读取最新状态但不自动重试写；400 候选变化给出明确提示', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  const save = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'controller assignment version conflict: expected_version=0, current_version=1' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  // 409 后自动发起一次 GET 重读，且没有第二个 PATCH
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 1);
  const reread = pending[pending.length - 1];
  assert.match(reread.url, /\/api\/projects\/A$/);
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:deepseek', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(ui.assignedId, 'agent:deepseek');
  assert.equal(ui.version, 1);
  assert.match(ui.error, /version conflict/);
  assert.match(ui.error, /已为你刷新到最新状态/);
  // 用户确认后可按最新状态手动重试（先解除）
  const retry = context.saveControllerAssignment(null);
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { member_id: null, expected_version: 1 });
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await retry;
  // 400 候选变化：明确提示，不假报保存
  const bad = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'controller candidate is disabled: agent:kimi' }, { ok: false, status: 400 });
  await new Promise(r => setTimeout(r, 0));
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await bad;
  assert.match(ui.error, /candidate is disabled/);
  assert.match(ui.error, /请刷新角色列表后重试/);
  assert.equal(ui.assignedId, null);
});

test('403/网络错误/旧接口 404：如实报错，不假报保存；错误可恢复重试', async () => {
  const { context, pending, reply, fail, ui, enter } = harness();
  await enter('A');
  // 403 无权限
  const forbidden = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'only human members can manage projects' }, { ok: false, status: 403 });
  await forbidden;
  assert.match(ui.error, /only human/);
  assert.equal(ui.assignedId, null);
  assert.equal(ui.saving, false);
  // 网络错误
  const offline = context.saveControllerAssignment('agent:kimi');
  fail(pending.length - 1, new Error('fetch failed'));
  await offline;
  assert.match(ui.error, /fetch failed/);
  assert.equal(ui.assignedId, null);
  // 旧接口 404：明确不支持，不假报保存
  const legacy = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'Not Found' }, { ok: false, status: 404 });
  await legacy;
  assert.match(ui.error, /尚未支持项目主控指定/);
  assert.match(ui.error, /本次未保存/);
  assert.equal(ui.supported, false);
  assert.equal(ui.assignedId, null);
});

test('旧后端读取缺字段：明确不支持并禁用写入，不误当未指定', async () => {
  const h2 = harness();
  h2.context.activeProjectId = 'A';
  const request = h2.context.renderControllerPanel();
  h2.reply(h2.pending.length - 1, { project_id: 'A', display_name: '旧服务' });
  await request;
  assert.equal(h2.ui.supported, false);
  assert.match(h2.el('controller-current').textContent, /当前服务不支持/);
  assert.match(h2.el('controller-status').textContent, /尚未支持/);
  assert.equal(h2.el('controller-assign-row').classList.contains('hidden'), true); // 不支持时不出现指定入口
  const before = h2.pending.length;
  await h2.context.saveControllerAssignment('agent:kimi');
  assert.equal(h2.pending.length, before); // 不发出任何写请求
});

test('读取失败：显示错误与重试入口，不启用写入', async () => {
  const { context, pending, reply, el, ui } = harness();
  context.activeProjectId = 'A';
  const request = context.renderControllerPanel();
  reply(pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await request;
  assert.equal(ui.loaded, false);
  assert.match(el('controller-current').textContent, /读取失败/);
  assert.equal(el('controller-retry-btn').classList.contains('hidden'), false);
  assert.equal(el('controller-assign-row').classList.contains('hidden'), true);
  // 加载中也一样：无写入口可用
  const h2 = harness();
  h2.context.activeProjectId = 'A';
  h2.context.renderControllerPanel();
  assert.match(h2.el('controller-current').textContent, /读取中/);
  assert.equal(h2.el('controller-assign-row').classList.contains('hidden'), true);
});

test('切项目/账号后迟到响应不能污染新上下文', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  // 发起保存后立刻切到项目 B（触发新上下文读取）
  const save = context.saveControllerAssignment('agent:kimi');
  const saveIndex = pending.length - 1;
  await enter('B', { controller_member_id: 'agent:deepseek', controller_assignment_version: 9, controller_assignment_status: 'assigned' });
  assert.equal(ui.projectId, 'B');
  assert.equal(ui.assignedId, 'agent:deepseek');
  // 项目 A 的迟到保存响应被丢弃
  reply(saveIndex, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(ui.projectId, 'B');
  assert.equal(ui.assignedId, 'agent:deepseek');
  assert.equal(ui.version, 9);
  // 切账号：旧账号读取响应同样被丢弃
  const h2 = harness();
  h2.context.activeProjectId = 'A';
  const load = h2.context.renderControllerPanel();
  const loadIndex = h2.pending.length - 1;
  h2.context.myId = 'human:other';
  h2.context.renderControllerPanel(); // 账号变化触发新读取
  h2.reply(h2.pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 0, controller_assignment_status: 'unassigned' });
  h2.reply(loadIndex, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 4, controller_assignment_status: 'assigned' });
  await load;
  assert.equal(h2.ui.memberId, 'human:other');
  assert.equal(h2.ui.assignedId, null);
});

test('版本安全边界：无法安全表示的版本禁止发送失真 expected_version', async () => {
  // 2**63-1 经 JSON 解析已失真为 9223372036854775808（> MAX_SAFE_INTEGER）
  for (const version of [9223372036854775807, Number.MAX_SAFE_INTEGER + 1, 1.5, '3', null]) {
    const { context, pending, el, ui, enter } = harness();
    await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: version, controller_assignment_status: 'assigned' });
    assert.match(el('controller-detail').textContent, /安全表示/, String(version));
    assert.match(el('controller-status').textContent, /无法安全表示/);
    assert.equal(el('controller-clear-btn').disabled, true);
    const before = pending.length;
    await context.saveControllerAssignment(null);
    assert.equal(pending.length, before); // 未发出失真版本
    assert.match(ui.error, /无法安全表示/);
  }
  // 未指定但版本不可安全表示：候选选择器出现但写入控件禁用
  const unsafe = harness();
  await unsafe.enter('A', { controller_member_id: null, controller_assignment_version: Number.MAX_SAFE_INTEGER + 1, controller_assignment_status: 'unassigned' });
  assert.equal(unsafe.el('controller-assign-row').classList.contains('hidden'), false);
  assert.equal(unsafe.el('controller-assign-btn').disabled, true);
  assert.equal(unsafe.el('controller-candidate-select').disabled, true);
  // 安全整数边界（MAX_SAFE_INTEGER）照常可用
  const { context, pending, reply, ui, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: Number.MAX_SAFE_INTEGER, controller_assignment_status: 'assigned' });
  const clear = context.saveControllerAssignment(null);
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { member_id: null, expected_version: Number.MAX_SAFE_INTEGER });
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 0, controller_assignment_status: 'unassigned' });
  await clear;
  assert.equal(ui.assignedId, null);
});

test('保存响应校验：项目不符或 member 不一致都不算保存成功', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  const wrong = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { project_id: 'B', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await wrong;
  assert.match(ui.error, /未确认本次保存/);
  assert.equal(ui.assignedId, null);
  const mismatch = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:deepseek', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await mismatch;
  assert.match(ui.error, /未确认本次保存/);
  assert.equal(ui.assignedId, null);
});

test('候选校验：禁用/非名册成员不能指定；已有指定时不能绕过解除直接覆盖', async () => {
  const { context, pending, ui, enter } = harness();
  await enter('A');
  await context.saveControllerAssignment('agent:banned'); // 已禁用
  assert.match(ui.error, /不在可指定范围/);
  await context.saveControllerAssignment('agent:offsite'); // 不在名册
  assert.match(ui.error, /不在可指定范围/);
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 0);
  // 已有指定时直接指定他人：界面置灰之外，保存路径也拒绝覆盖
  const h2 = harness();
  await h2.enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await h2.context.saveControllerAssignment('agent:deepseek');
  assert.equal(h2.pending.filter(p => p.opts?.method === 'PATCH').length, 0);
});

test('同项目重复重绘不重发请求；读取完成触发列表与详情同步刷新', async () => {
  const { context, pending, calls, enter } = harness();
  await enter('A');
  assert.ok(calls.list > 0 && calls.details > 0); // 加载完成后同步徽标与按钮
  const before = pending.length;
  context.renderControllerPanel(); // 轮询/重绘路径：同上下文只同步 DOM，不重读
  context.renderControllerPanel();
  assert.equal(pending.length, before);
});

test('任务/群聊导航不残留管理区：离开角色页即隐藏，返回不重复读取', async () => {
  const { context, pending, el, enter, setSettingsSelected } = harness();
  await enter('A');
  assert.equal(el('controller-panel').classList.contains('hidden'), false);
  context.workspaceUI.mode = 'chats';
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  context.workspaceUI.mode = 'tasks';
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  // 返回角色页：同上下文不重新读取，面板恢复
  const before = pending.length;
  context.workspaceUI.mode = 'roles';
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), false);
  assert.equal(pending.length, before);
  // 选中具体角色时项目设置页互斥：主控面板隐藏；回到项目设置恢复且不重新读取
  setSettingsSelected(false);
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  setSettingsSelected(true);
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), false);
  assert.equal(pending.length, before);
});

test('REQ-2 隔离：主控代码块不触碰开发要求字段、localStorage 与 innerHTML', () => {
  assert.ok(!controllerBlock.includes('development_requirements'), '不应读写开发要求字段');
  assert.ok(!controllerBlock.includes('localStorage.'), '草稿/状态只存内存');
  assert.ok(!controllerBlock.includes('innerHTML'), '文案只走 textContent');
  // 项目缓存回写只限主控三字段
  assert.ok(controllerBlock.includes('project.controller_member_id ='));
  assert.ok(!/project\.(display_name|description|controller_mode|project_root_path)\s*=/.test(controllerBlock));
});

// ── #114 定向修正回归（R1 焦点去向 / R2 迟到响应不重绘新页面） ─────────────
// 以下用例驱动真实代码块中的 syncControllerViews/controllerFocusTarget。
// ROLE-SETTINGS-1 起主控控件固定在“项目设置”面板（不再随角色详情重建），
// 因此焦点断言直接落在真实面板元素上：指定成功→解除主控，解除成功→候选选择器，
// 失败→回原按钮；hidden/disabled 不作为目标，用户移焦/切视图后不抢焦。

test('R1 指定成功后焦点落到同一上下文的“解除主控”控件，不落 body', async () => {
  const { context, pending, reply, document, el, enter } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  const clearBtn = el('controller-clear-btn');
  assignBtn.focus();
  assert.equal(document.activeElement, assignBtn);
  const save = context.saveControllerAssignment('agent:kimi');
  // 保存中间态：同动作按钮被置灰但仍在，焦点不动（无额外 focus 调用）
  assert.equal(assignBtn.disabled, true);
  assert.equal(assignBtn.focusCalls, 1, '保存中间态不重复聚焦同动作按钮');
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(assignBtn.classList.contains('hidden'), false, '指定成功后“设为项目主控”保持可见');
  assert.equal(assignBtn.disabled, true, '指定成功后按钮置灰');
  assert.ok(clearBtn.focusCalls >= 1, '成功后应显式聚焦“解除主控”');
  assert.equal(document.activeElement, clearBtn, '焦点应落到同一上下文下一步可操作的“解除主控”');
  assert.notEqual(document.activeElement, document.body, '焦点不应落回 body');
});

test('R1 解除成功后解除入口隐藏，焦点落到可见的候选选择器（下一步是另选）', async () => {
  const { context, pending, reply, document, el, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  const clearBtn = el('controller-clear-btn');
  clearBtn.focus();
  assert.equal(document.activeElement, clearBtn);
  const save = context.saveControllerAssignment(null);
  assert.equal(clearBtn.disabled, true, '保存中间态解除按钮置灰');
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await save;
  assert.equal(clearBtn.classList.contains('hidden'), true, '解除成功后解除入口隐藏');
  assert.equal(clearBtn.focusCalls, 1, '不能把焦点放回已隐藏的解除按钮');
  const select = el('controller-candidate-select');
  assert.equal(select.classList.contains('hidden'), false);
  assert.ok(select.focusCalls >= 1, '应聚焦候选选择器，便于立即另选');
  assert.equal(document.activeElement, select);
  assert.notEqual(document.activeElement, document.body);
});

test('R1 失败路径保留原按钮并回焦；disabled/hidden 节点不作为焦点目标', async () => {
  const { context, pending, reply, document, el, enter } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  assignBtn.focus();
  const save = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'permission denied' }, { ok: false, status: 403 });
  await save;
  assert.ok(assignBtn.focusCalls >= 2, '失败后焦点回到保留的“设为项目主控”');
  assert.equal(document.activeElement, assignBtn);
  // 同动作节点存在但 disabled/hidden 时，不把它当焦点目标
  const h2 = harness();
  await h2.enter('A');
  const disabledBtn = h2.addActionButton('assign', { disabled: true });
  const hiddenBtn = h2.addActionButton('assign', { hidden: true });
  h2.document.activeElement = hiddenBtn;
  const failing = h2.context.saveControllerAssignment('agent:kimi');
  h2.reply(h2.pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await failing;
  assert.equal(disabledBtn.focusCalls, 0, '不把焦点放到 disabled 节点');
  assert.equal(hiddenBtn.focusCalls, 0, '不把焦点放到 hidden 节点');
});

test('R1 用户在保存期间主动移焦到其它控件时不抢焦', async () => {
  const { context, pending, reply, document, el, addActionButton, enter } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  assignBtn.focus();
  const save = context.saveControllerAssignment('agent:kimi');
  // 用户在响应返回前主动把焦点移到搜索框（非主控控件）
  const search = addActionButton('none');
  delete search.dataset.controllerAction;
  search.focus();
  assert.equal(document.activeElement, search);
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(document.activeElement, search, '用户已主动移焦，不抢回焦点');
  assert.equal(assignBtn.focusCalls, 1);
  assert.equal(el('controller-clear-btn').focusCalls, 0);
});

test('R1 离开角色页后迟到响应不执行回焦（不抢新页面焦点）', async () => {
  const { context, pending, reply, document, el, enter } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  assignBtn.focus();
  const save = context.saveControllerAssignment('agent:kimi');
  // 响应返回前切到任务页：真实导航会重建工作台，面板隐藏
  context.workspaceUI.mode = 'tasks';
  context.renderControllerPanel();
  document.activeElement = document.body;
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(el('controller-clear-btn').focusCalls, 0, '离开角色页后不抢焦');
  assert.equal(document.activeElement, document.body);
});

test('R2 PATCH 成功/失败晚于角色→任务/群聊切换：列表与角色详情不被额外重建，状态仍维护、不卡 saving', async () => {
  // PATCH 成功迟到
  const { context, pending, reply, calls, ui, el, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  const save = context.saveControllerAssignment(null);
  const patchIndex = pending.length - 1;
  context.workspaceUI.mode = 'tasks'; // 切到任务页
  context.renderControllerPanel();    // 真实导航同步点：面板隐藏
  const listCalls = calls.list, detailCalls = calls.details;
  reply(patchIndex, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await save;
  assert.equal(calls.list, listCalls, '离开角色页后迟到 PATCH 成功不得重绘列表');
  assert.equal(calls.details, detailCalls, '离开角色页后不得重绘角色详情');
  assert.equal(ui.saving, false, 'saving 不卡死');
  assert.equal(ui.assignedId, null, '状态仍维护到服务器最终值');
  assert.equal(ui.version, 2);
  assert.equal(el('controller-panel').classList.contains('hidden'), true, '管理面板不残留');
  // 返回角色页：同上下文不重读，面板呈现最新（解除后）状态而非陈旧指定
  context.workspaceUI.mode = 'roles';
  const before = pending.length;
  context.renderControllerPanel();
  assert.equal(pending.length, before, '同上下文返回不重复读取');
  assert.match(el('controller-current').textContent, /未指定/);

  // PATCH 失败迟到（403）
  const h2 = harness();
  await h2.enter('A');
  const save2 = h2.context.saveControllerAssignment('agent:kimi');
  const patch2 = h2.pending.length - 1;
  h2.context.workspaceUI.mode = 'chats'; // 切到群聊页
  h2.context.renderControllerPanel();
  const list2 = h2.calls.list, detail2 = h2.calls.details;
  h2.reply(patch2, { detail: 'permission denied' }, { ok: false, status: 403 });
  await save2;
  assert.equal(h2.calls.list, list2, '迟到 PATCH 失败不得重绘列表');
  assert.equal(h2.calls.details, detail2);
  assert.equal(h2.ui.saving, false);
  assert.match(h2.ui.error, /permission denied/, '错误状态仍记录');
  assert.equal(h2.ui.assignedId, null, '失败不假报已指定');
});

test('R2 GET 成功/失败晚于角色→任务/群聊切换：列表不额外重建，返回角色页可见服务器最终状态', async () => {
  // GET 成功迟到：进入角色页触发读取，响应返回前切到任务页
  const { context, pending, reply, calls, ui, el } = harness();
  context.activeProjectId = 'A';
  const load = context.renderControllerPanel();
  const loadIndex = pending.length - 1;
  context.workspaceUI.mode = 'tasks';
  context.renderControllerPanel();
  const listCalls = calls.list, detailCalls = calls.details;
  reply(loadIndex, { project_id: 'A', controller_member_id: 'agent:deepseek', controller_assignment_version: 5, controller_assignment_status: 'assigned' });
  await load;
  assert.equal(calls.list, listCalls, '迟到 GET 成功不得重绘任务页列表');
  assert.equal(calls.details, detailCalls);
  assert.equal(ui.assignedId, 'agent:deepseek', '状态仍更新为服务器最终值');
  assert.equal(ui.version, 5);
  // 返回角色页：显示刚读到的最终状态，不显示陈旧“未指定”
  context.workspaceUI.mode = 'roles';
  context.renderControllerPanel();
  assert.match(el('controller-current').textContent, /DeepSeek（agent:deepseek）/);

  // GET 失败迟到：返回角色页显示读取失败与重试入口，不显示“未指定”
  const h2 = harness();
  h2.context.activeProjectId = 'A';
  const load2 = h2.context.renderControllerPanel();
  const load2Index = h2.pending.length - 1;
  h2.context.workspaceUI.mode = 'chats';
  h2.context.renderControllerPanel();
  const list2 = h2.calls.list, detail2 = h2.calls.details;
  h2.reply(load2Index, { detail: 'boom' }, { ok: false, status: 500 });
  await load2;
  assert.equal(h2.calls.list, list2, '迟到 GET 失败不得重绘群聊页列表');
  assert.equal(h2.calls.details, detail2);
  h2.context.workspaceUI.mode = 'roles';
  h2.context.renderControllerPanel();
  assert.match(h2.el('controller-current').textContent, /读取失败/);
  assert.equal(h2.el('controller-retry-btn').classList.contains('hidden'), false);
});

test('R2 黑板关闭后迟到响应不重绘；仍在角色页时读取完成照常重绘列表与详情', async () => {
  const { context, pending, reply, calls, ui, el, enter } = harness();
  await enter('A');
  context.reloadControllerAssignment();
  const refreshIndex = pending.length - 1;
  context.blackboardOpen = false; // 黑板关闭
  context.renderControllerPanel();
  const listCalls = calls.list, detailCalls = calls.details;
  reply(refreshIndex, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await new Promise(r => setTimeout(r, 0));
  assert.equal(calls.list, listCalls, '黑板关闭后迟到响应不得重绘列表');
  assert.equal(calls.details, detailCalls);
  assert.equal(ui.assignedId, 'agent:kimi', '状态仍维护');
  // 恢复角色页后正常重绘路径不受影响
  context.blackboardOpen = true;
  context.renderControllerPanel();
  context.reloadControllerAssignment();
  const refresh2 = pending.length - 1;
  reply(refresh2, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 2, controller_assignment_status: 'assigned' });
  await new Promise(r => setTimeout(r, 0));
  assert.ok(calls.list > listCalls && calls.details > detailCalls, '在角色页时读取完成仍照常重绘列表与详情');
  assert.match(el('controller-current').textContent, /agent:kimi/);
});

// ── #116 定向修正回归（F1 保存请求所有权 / F2 切角色取消焦点恢复意图） ─────────────
// 以下用例以可控延迟（pending 队列手动应答）驱动真实 saveControllerAssignment/
// renderControllerPanel 调用路径，不是只测新 token 的自设函数。修改前的实现中：
// F1 旧请求 finally 只按 contextAlive() 判断会提前清掉新保存的 saving；
// F2 焦点记忆不绑定选中角色，切角色后迟到成功仍回焦主控区 —— 这两组用例在修改前会失败。

test('F1 A→B→A 往返后旧 PATCH 迟到：不清理新保存 saving、不写状态、不发第三次 PATCH、不回焦', async () => {
  const { context, pending, reply, ui, document, addActionButton, enter } = harness();
  await enter('A');
  const first = context.saveControllerAssignment('agent:kimi'); // P1 在途
  const p1 = pending.length - 1;
  assert.equal(ui.saving, true);
  // A→B→A：每次上下文切换都重置状态并重新读取（真实 renderControllerPanel 路径）
  await enter('B');
  await enter('A');
  const secondBtn = addActionButton('assign');
  document.activeElement = secondBtn;
  const second = context.saveControllerAssignment('agent:kimi'); // P2 在途
  const p2 = pending.length - 1;
  assert.equal(ui.saving, true);
  assert.equal(secondBtn.focusCalls, 1, 'P2 保存开始回焦同动作按钮（既有行为）');
  // 旧 P1 迟到：上下文重新“活着”，但 P1 不拥有当前保存状态
  reply(p1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await first;
  assert.equal(ui.saving, true, '旧请求的 finally 不得提前清掉新请求的 saving');
  assert.equal(ui.assignedId, null, '旧请求成败不得写入新上下文状态');
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 2, '旧请求到达不得触发第三次 PATCH');
  assert.equal(secondBtn.focusCalls, 1, '旧请求到达不得回焦或同步视图');
  // P2 正常完成：当前请求仍拥有保存状态，可正常结束
  reply(p2, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await second;
  assert.equal(ui.saving, false, '当前请求正常路径可结束');
  assert.equal(ui.assignedId, 'agent:kimi', '最终状态由最新一次保存决定');
});

test('F1 切账号往返后旧 PATCH 迟到：同样不清理新保存状态、不污染新请求', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  const first = context.saveControllerAssignment('agent:kimi'); // P1（human:qa）在途
  const p1 = pending.length - 1;
  // 切到另一 human 账号再切回：账号变化分支重置状态并重新读取
  context.myId = 'human:other';
  const loadOther = context.renderControllerPanel();
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 0, controller_assignment_status: 'unassigned' });
  await loadOther;
  assert.equal(ui.memberId, 'human:other');
  context.myId = 'human:qa';
  const loadBack = context.renderControllerPanel();
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 0, controller_assignment_status: 'unassigned' });
  await loadBack;
  const second = context.saveControllerAssignment('agent:kimi'); // P2 在途
  const p2 = pending.length - 1;
  assert.equal(ui.saving, true);
  // 旧 P1 迟到：项目与账号都重新匹配（上下文“活着”），但所有权属于 P2
  reply(p1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await first;
  assert.equal(ui.saving, true, '切账号往返后旧请求仍不得清理新请求的 saving');
  assert.equal(ui.assignedId, null);
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 2);
  reply(p2, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await second;
  assert.equal(ui.saving, false);
  assert.equal(ui.assignedId, 'agent:kimi');
});

test('F1 当前请求各路径均可结束：409 内部重读递增序号后仍拥有保存状态；失败/旧请求后新保存不受阻', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  // 409：内部重读会递增请求序号，但当前请求凭所有权 token 仍可清理 saving
  const conflict = context.saveControllerAssignment('agent:kimi');
  reply(pending.length - 1, { detail: 'version conflict' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  assert.match(pending[pending.length - 1].url, /\/api\/projects\/A$/, '409 后自动重读最新状态');
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:deepseek', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await conflict;
  assert.equal(ui.saving, false, '409 重读后当前请求仍可结束（所有权不被内部重读夺走）');
  assert.match(ui.error, /version conflict/);
  assert.equal(ui.assignedId, 'agent:deepseek');
  // 失败路径：网络错误后 saving 正常清理，可再次发起保存
  const offline = context.saveControllerAssignment(null);
  pending[pending.length - 1].reject(new Error('fetch failed'));
  await offline;
  assert.equal(ui.saving, false);
  assert.match(ui.error, /fetch failed/);
  const retry = context.saveControllerAssignment(null);
  reply(pending.length - 1, { project_id: 'A', controller_member_id: null, controller_assignment_version: 2, controller_assignment_status: 'unassigned' });
  await retry;
  assert.equal(ui.saving, false);
  assert.equal(ui.assignedId, null);
});

// ── #116 定向修正回归（F2 焦点恢复意图绑定当前视图） ─────────────
// ROLE-SETTINGS-1 起主控控件固定在“项目设置”面板：保存期间用户切到具体角色（或离开
// 项目设置页）属于新的交互意图，完成后不回焦主控区；仍在项目设置页时按记忆恢复。

test('F2 保存中切到具体角色：完成后取消回焦不抢焦，保存清理与服务器结果更新不受影响', async () => {
  const { context, pending, reply, ui, document, el, enter, setSettingsSelected } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  assignBtn.focus();
  assert.equal(document.activeElement, assignBtn);
  const save = context.saveControllerAssignment('agent:kimi');
  // 保存中间态：同动作按钮置灰但未消失，不动焦点
  assert.equal(assignBtn.disabled, true);
  assert.equal(assignBtn.focusCalls, 1);
  // 用户点击具体角色行：真实导航经过 renderTaskDetailsPanel → renderControllerPanel，面板隐藏
  setSettingsSelected(false);
  context.renderControllerPanel();
  assert.equal(el('controller-panel').classList.contains('hidden'), true);
  document.activeElement = document.body; // 行重绘把焦点打回 body
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  assert.equal(el('controller-clear-btn').focusCalls, 0, '切到具体角色后不把焦点拉回主控区控件');
  assert.equal(document.activeElement, document.body, '不跨视图抢焦');
  assert.equal(ui.saving, false, '保存状态照常清理');
  assert.equal(ui.assignedId, 'agent:kimi', '服务器结果照常更新');
  assert.equal(ui.version, 1);
  // 回到项目设置页：呈现服务器最终状态（已指定 + 解除入口），不重复读取
  const before = pending.length;
  setSettingsSelected(true);
  context.renderControllerPanel();
  assert.equal(pending.length, before);
  assert.match(el('controller-current').textContent, /agent:kimi/);
  assert.equal(el('controller-clear-btn').classList.contains('hidden'), false);
});

test('F2 保存期间未离开项目设置：焦点记忆恢复到下一步可见控件', async () => {
  const { context, pending, reply, ui, document, el, enter } = harness();
  await enter('A');
  const assignBtn = el('controller-assign-btn');
  assignBtn.focus();
  const save = context.saveControllerAssignment('agent:kimi');
  // 模拟真实浏览器把控件置灰/隐藏时焦点回落 body 的空窗
  document.activeElement = document.body;
  reply(pending.length - 1, { project_id: 'A', controller_member_id: 'agent:kimi', controller_assignment_version: 1, controller_assignment_status: 'assigned' });
  await save;
  const clearBtn = el('controller-clear-btn');
  assert.ok(clearBtn.focusCalls >= 1, '未离开项目设置时仍按记忆恢复到可见“解除主控”');
  assert.equal(document.activeElement, clearBtn);
  assert.equal(ui.saving, false);
});
