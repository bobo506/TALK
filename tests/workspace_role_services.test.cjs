// R1-3：项目角色页“受管 CLI 服务”单独启动/关闭 + 项目级“全部启动”的真实接线聚焦测试。
// 与 workspace_role_binding.test.cjs 同一做法：vm 加载整份真实 web/workspace.js + 假 DOM +
// 记录 apiFetch 调用；断言真实渲染出的状态文本、按钮 disabled、真实请求 URL/method/headers/body
// 与真实 2 秒轮询生命周期，不是源码字符串匹配，也不手写渲染镜像。
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function fakeEl(tag) {
  const classes = new Set();
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '', disabled: false, readOnly: false,
    dataset: {}, attrs: {}, children: [], listeners: {}, replaceCount: 0,
    classList: {
      add(...cs) { cs.forEach(c => classes.add(c)); },
      remove(...cs) { cs.forEach(c => classes.delete(c)); },
      toggle(c, force) { const on = force === undefined ? !classes.has(c) : !!force; on ? classes.add(c) : classes.delete(c); return on; },
      contains(c) { return classes.has(c); },
    },
    appendChild(c) {
      if (c.parentElement) c.parentElement.children.splice(c.parentElement.children.indexOf(c), 1);
      c.parentElement = el; el.children.push(c); return c;
    },
    append(...cs) { cs.forEach(c => el.appendChild(c)); },
    replaceChildren(...cs) {
      el.replaceCount += 1;
      el.children.forEach(c => { c.parentElement = null; });
      el.children.length = 0; el.append(...cs);
    },
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
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 冻结契约里的 service 投影（隔离 fixture，只作为渲染输入，不写任何生产数据）。
function serviceRow(overrides = {}) {
  return {
    desired: 'stopped', observed: 'not_started', last_action: null, last_result: null,
    error_code: null, error_message: null, control_kind: 'managed_cli', manager_kind: 'cli_process',
    generation: 0, current_launch: null, observed_instance_id: null,
    native_login: 'unverified', model_alias: 'resolved', readiness_service: 'pending',
    can_start: true, can_stop: false, ownership_held: false, started_at: null, stopped_at: null, updated_at: '2026-10-11T00:00:00Z',
    ...overrides,
  };
}

const activeHarnesses = [];
afterEach(() => { for (const h of activeHarnesses.splice(0)) h.context.stopRoleServicePolling(); });

test('全部启动被人工关闭取代后结束该批次轮询', () => {
  const h = harness({ roster: [{ member_id: 'agent:a', service: serviceRow() }] });
  h.roleServiceUI.batch = {
    busy: false, results: [{ member_id: 'agent:a', status: 'requested' }], requestFailures: [],
    launches: { 'agent:a': { launch_id: 'start-a', generation: 1 } },
    settled: { 'agent:a': 'pending' }, counts: { requested: 1, pending: 1, started: 0, skipped: 0, failed: 0 },
  };
  h.context.roleServiceBatchConverge([{ member_id: 'agent:a', ...serviceRow({
    generation: 2, desired: 'stopped', observed: 'stopped', last_action: 'stop', last_result: 'stopped',
  }) }]);
  assert.notEqual(h.roleServiceUI.batch.settled['agent:a'], 'pending');
  assert.equal(h.roleServiceUI.batch.counts.pending, 0);
  assert.equal(h.roleServiceUI.batch.counts.started, 0);
  assert.equal(h.roleServiceUI.batch.counts.skipped, 1);
});

test('失败服务关闭并释放归属后可进入批量失败重试', () => {
  const h = harness({ roster: [{ member_id: 'agent:a', service: serviceRow() }] });
  h.roleServiceUI.batch = {
    busy: false, results: [{ member_id: 'agent:a', status: 'requested' }], requestFailures: [],
    launches: { 'agent:a': { launch_id: 'start-a', generation: 1 } },
    settled: { 'agent:a': 'failed_owned' }, counts: { requested: 1, pending: 0, started: 0, skipped: 0, failed: 1 },
  };
  h.context.roleServiceBatchConverge([{ member_id: 'agent:a', ...serviceRow({
    generation: 2, desired: 'stopped', observed: 'stopped', ownership_held: false, can_start: true,
  }) }]);
  assert.equal(h.roleServiceUI.batch.settled['agent:a'], 'failed');
  assert.equal(h.context.roleServiceBatchFailedMembers(h.roleServiceUI.batch).join(','), 'agent:a');
});

test('批量跳过归属未释放的角色仍跟踪后续关闭', () => {
  const h = harness({ roster: [{ member_id: 'agent:a', service: serviceRow({
    generation: 1, observed: 'failed', ownership_held: true, can_start: false, can_stop: true,
  }) }] });
  const result = { member_id: 'agent:a', status: 'skipped_ownership_held', generation: 1 };
  const batch = { busy: false, results: [result], requestFailures: [], launches: {}, settled: {}, counts: {} };
  h.roleServiceUI.batch = batch;
  h.context.roleServiceApplyStartAll([result], batch);
  assert.equal(batch.launches['agent:a'].generation, 1);
  h.context.roleServiceBatchConverge([{ member_id: 'agent:a', ...serviceRow({
    generation: 2, desired: 'stopped', observed: 'stopped', ownership_held: false, can_start: true,
  }) }]);
  assert.equal(h.context.roleServiceBatchFailedMembers(batch).join(','), 'agent:a');
  assert.equal(batch.counts.failed, 1);
  assert.equal(batch.counts.skipped, 0, '同一角色不同时计为跳过与失败');
});

function harness({ human = true, roster = [] } = {}) {
  const pending = [];
  const requests = [];
  const elements = new Map();
  const getEl = id => {
    if (!elements.has(id)) { const node = fakeEl('div'); node.id = id; elements.set(id, node); }
    return elements.get(id);
  };
  // 与实际 HTML 一致的搜索/操作树；getElementById 不返回已被移除的搜索框。
  const board = getEl('blackboard-view');
  const toolbar = getEl('blackboard-toolbar');
  toolbar.append(getEl('workspace-search'), getEl('role-service-batch-actions'));
  board.append(getEl('blackboard-header'), toolbar, getEl('role-service-batch-feedback'),
    getEl('blackboard-summary'), getEl('blackboard-columns'));
  const workbench = fakeEl('div');
  const documentStub = {
    getElementById: id => id === 'workspace-search'
      ? findAll(board, node => node.id === id)[0] || null : getEl(id),
    createElement: tag => fakeEl(tag),
    createTextNode: text => ({ textContent: text }),
    querySelector: sel => (sel === '.workbench' ? workbench : null),
    activeElement: null,
    body: fakeEl('body'),
  };
  const members = [
    { id: 'human:qa', kind: 'human', display_name: 'bobo' },
    ...roster.map(item => ({ id: item.member_id, kind: 'agent', display_name: String(item.member_id).replace(/^agent:/, '') })),
  ];
  const context = vm.createContext({
    document: documentStub,
    // vm 的新 context 默认没有宿主计时器；注入 Node 的 setTimeout/clearTimeout，
    // 让真实 workspace.js 的轮询生命周期（不是测试内镜像）被实际驱动。
    setTimeout,
    clearTimeout,
    blackboardOpen: true,
    activeProjectId: 'A',
    activeGroupId: null,
    myId: human ? 'human:qa' : 'agent:managed',
    members,
    projectAgents: roster.map(item => ({ ...item })),
    projectTasks: [],
    groups: [],
    projects: [{ project_id: 'A' }],
    currentMemberIsHuman: () => human,
    apiFetch: (url, opts) => {
      requests.push({ url, opts });
      return new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject }));
    },
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    taskStatusMeta: () => ({ label: '执行中', className: 'running' }),
    formatTaskTime: () => '10-11 10:00',
    selectWorkspaceTask: () => {},
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
    setBlackboardOpen: () => {},
    renderWorkspaceMode: () => {},
    selectedTaskTree: null,
    taskTreeRequest: 0,
    activeProjectStorageKey: () => 'active-project:test',
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { matchMedia: () => ({ matches: false }) },
    blackboardTitle: getEl('blackboard-title'),
    blackboardDescription: getEl('blackboard-description'),
    blackboardColumns: getEl('blackboard-columns'),
    blackboardSummary: getEl('blackboard-summary'),
    blackboardEmpty: getEl('blackboard-empty'),
    userBadge: getEl('user-badge'),
  });
  context.renderTaskDetailsPanel = () => { context.renderWorkspaceRoleDetails(); };
  vm.runInContext(wsSource, context);
  vm.runInContext('this.__roleServiceUI = roleServiceUI; this.__workspaceUI = workspaceUI;', context);
  const roleServiceUI = context.__roleServiceUI;

  const flush = async () => { for (let i = 0; i < 4; i++) await sleep(0); };
  const waitFor = async (pred, timeoutMs = 1000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) { if (pred()) return true; await sleep(5); }
    return pred();
  };
  const rows = () => findAll(getEl('blackboard-columns'), () => true).slice(1);
  const controlsFor = memberId => rows().find(node =>
    String(node.className).includes('role-service-controls') && node.dataset.memberId === memberId);
  const buttonIn = (node, text) => (node ? findAll(node, n => n.tagName === 'button' && n.textContent === text)[0] : undefined);
  const stateOf = box => { const n = box && findAll(box, x => String(x.className).includes('role-service-state'))[0]; return n ? n.textContent : ''; };
  const hintOf = box => { const n = box && findAll(box, x => String(x.className).includes('role-service-hint'))[0]; return n ? n.textContent : ''; };
  const batchBox = () => findAll(getEl('role-service-batch-actions'), n => String(n.className) === 'role-service-batch')[0];
  const batchFeedbackBox = () => getEl('role-service-batch-feedback');
  const roleRow = memberId => rows().find(row => String(row.className).includes('role-row')
    && !String(row.className).includes('role-settings-row') && allTexts(row).some(t => t.includes(memberId)));
  // 沿真实角色选择入口打开详情，逐角色操作只从详情获取。
  const actionsFor = memberId => {
    if (context.__workspaceUI.selectedRole !== memberId || context.__workspaceUI.roleSelection !== 'role') {
      roleRow(memberId)?.fire('click');
    }
    return findAll(getEl('role-details-name-panel'), node =>
      String(node.className).includes('role-service-detail-controls') && node.dataset.memberId === memberId)[0];
  };

  const api = {
    context,
    roleServiceUI,
    requests,
    pending,
    el: getEl,
    rows,
    controlsFor,
    state: memberId => stateOf(controlsFor(memberId)),
    hint: memberId => hintOf(controlsFor(memberId)),
    startBtn: memberId => buttonIn(actionsFor(memberId), '启动'),
    stopBtn: memberId => buttonIn(actionsFor(memberId), '关闭'),
    batchBox,
    batchFeedbackBox,
    startAllBtn: () => buttonIn(batchBox(), '全部启动'),
    retryBtn: () => buttonIn(batchFeedbackBox(), '重试失败项'),
    startRequests: () => requests.filter(r => /\/service\/start$/.test(r.url)),
    stopRequests: () => requests.filter(r => /\/service\/stop$/.test(r.url)),
    servicePolls: () => requests.filter(r => /\/role-services$/.test(r.url)),
    setPollDelay: ms => { roleServiceUI.pollDelayMs = ms; },
    reply: (index, data, { ok = true, status = 200 } = {}) => pending[index].resolve({ ok, status, json: async () => data }),
    flush,
    waitFor,
    enterRoles: async () => {
      getEl('workspace-roles-btn').fire('click');
      context.renderWorkspaceList();
      context.renderTaskDetailsPanel();
      await flush();
    },
    selectRole: async memberId => { roleRow(memberId).fire('click'); await flush(); },
  };
  activeHarnesses.push(api);
  return api;
}

// ── 门控：只有 managed_cli 才可能启用启动 ───────────────────────────────────
test('门控：managed_cli + can_start 可启动；unknown/external_session/service=null 禁用并有如实提示', async () => {
  const h = harness({
    roster: [
      { member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ can_start: true }) },
      { member_id: 'agent:external', business_role: 'dev', service: serviceRow({ control_kind: 'external_session', can_start: false }) },
      { member_id: 'agent:unknown', business_role: 'dev', service: serviceRow({ control_kind: 'unknown', can_start: false }) },
      { member_id: 'agent:none', business_role: 'dev', service: null },
      { member_id: 'agent:legacy', business_role: 'dev' },
    ],
  });
  await h.enterRoles();
  assert.equal(h.startBtn('agent:managed').disabled, false, 'managed_cli + can_start 可启动');
  assert.equal(h.stopBtn('agent:managed').disabled, true, 'can_stop=false 时关闭不可用');
  assert.equal(h.startBtn('agent:external').disabled, true);
  assert.ok(h.state('agent:external') !== '启动成功', 'external_session 不得显示启动成功');
  assert.ok(h.hint('agent:external').includes('需人工在原生客户端打开/登录'), 'external_session 如实提示');
  assert.equal(h.startBtn('agent:unknown').disabled, true);
  assert.ok(h.hint('agent:unknown').includes('未声明受管控制能力'), 'unknown 如实提示未声明控制能力');
  assert.equal(h.startBtn('agent:none').disabled, true);
  assert.ok(h.hint('agent:none').includes('未登记受管服务'), 'service=null 如实说未登记');
  assert.equal(h.controlsFor('agent:legacy'), undefined, '旧服务没有 service 字段时不渲染控制块（≠ service:null）');
});

test('门控：不因 binding_state=bound 或实例自报 idle 放开启动', async () => {
  const h = harness({
    roster: [{
      member_id: 'agent:x', business_role: 'dev', binding_state: 'bound',
      instances: [{ id: 'i1', runtime: 'codex', status: 'idle' }],
      service: serviceRow({ control_kind: 'unknown', can_start: false }),
    }],
  });
  await h.enterRoles();
  assert.equal(h.startBtn('agent:x').disabled, true, '未知控制能力不得因已绑定/空闲放开');
  assert.ok(h.hint('agent:x').includes('未声明受管控制能力'));
  assert.ok(!allTexts(h.controlsFor('agent:x')).join(' ').includes('启动成功'));
});

// ── 状态文案映射（设计 §11.2） ─────────────────────────────────────────────
test('状态文案：not_started/stopped 不算失败；running 未就绪不出成功；未知不伪装', async () => {
  const h = harness({
    roster: [
      { member_id: 'agent:a', business_role: 'dev', service: serviceRow({ observed: 'not_started' }) },
      { member_id: 'agent:b', business_role: 'dev', service: serviceRow({ observed: 'stopped', last_result: 'stopped' }) },
      { member_id: 'agent:c', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'pending' }) },
      { member_id: 'agent:d', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', native_login: 'unverified' }) },
      { member_id: 'agent:e', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', native_login: 'verified' }) },
      { member_id: 'agent:f', business_role: 'dev', service: serviceRow({ observed: 'unknown' }) },
      { member_id: 'agent:g', business_role: 'dev', service: serviceRow({ observed: 'failed', last_result: 'failed', error_code: 'readiness_timeout' }) },
      { member_id: 'agent:h', business_role: 'dev', service: serviceRow({ observed: 'failed', last_result: 'failed', error_code: 'start_timeout', error_message: '进程启动超时' }) },
    ],
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  assert.equal(h.state('agent:a'), '未启动');
  assert.equal(h.state('agent:b'), '未启动（已关闭）');
  assert.ok(!h.state('agent:b').includes('失败'), 'stopped 不得显示失败');
  assert.equal(h.state('agent:c'), '启动中…');
  assert.ok(!h.state('agent:c').includes('成功'), 'running 但未就绪不得显示成功');
  assert.equal(h.state('agent:d'), '启动成功（原生登录未核验）');
  assert.equal(h.state('agent:e'), '启动成功');
  assert.equal(h.state('agent:f'), '未知');
  assert.equal(h.state('agent:g'), '启动失败（未就绪）');
  assert.ok(h.state('agent:h').includes('启动失败') && h.state('agent:h').includes('start_timeout'));
});

test('状态文案：starting/stopping 加载态禁用按钮', async () => {
  const h = harness({
    roster: [
      { member_id: 'agent:start', business_role: 'dev', service: serviceRow({ observed: 'starting', desired: 'running', can_start: true }) },
      { member_id: 'agent:stop', business_role: 'dev', service: serviceRow({ observed: 'stopping', desired: 'stopped', can_start: false, can_stop: true }) },
    ],
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  assert.equal(h.state('agent:start'), '启动中…');
  assert.equal(h.startBtn('agent:start').disabled, true, 'starting 时启动按钮禁用');
  assert.equal(h.state('agent:stop'), '关闭中…');
  assert.equal(h.stopBtn('agent:stop').disabled, true, 'stopping 时关闭按钮禁用');
});

// ── 真实请求接线 ────────────────────────────────────────────────────────────
test('点击启动：真实 POST /roles/{member_id}/service/start，响应后进入启动中', async () => {
  const h = harness({ roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ can_start: true }) }] });
  h.setPollDelay(60000);
  await h.enterRoles();
  h.startBtn('agent:managed').fire('click');
  await h.flush();
  assert.equal(h.requests.length, 1);
  const request = h.requests[0];
  assert.equal(request.url, '/api/projects/A/roles/agent%3Amanaged/service/start');
  assert.equal(request.opts.method, 'POST');
  assert.equal(request.opts.headers['Content-Type'], 'application/json');
  assert.equal(request.opts.body, undefined, '单独启动不需要请求体');
  assert.equal(h.startBtn('agent:managed').disabled, true, '在途时按钮禁用');
  h.reply(0, {
    member_id: 'agent:managed', role_name: 'Managed', launch_id: 'l1', generation: 1, action: 'start',
    expected_instance_id: 'ins_1', launch_expires_at: '2026-10-11T00:01:00Z', desired: 'running', observed: 'starting',
  });
  await h.flush();
  assert.equal(h.startBtn('agent:managed').disabled, true);
  assert.equal(h.state('agent:managed'), '启动中…');
  assert.equal(h.roleServiceUI.busy.size, 0, '应答后在途标记清除');
});

test('点击关闭：真实 POST /roles/{member_id}/service/stop', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', can_start: false, can_stop: true }) }],
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  assert.equal(h.stopBtn('agent:managed').disabled, false);
  h.stopBtn('agent:managed').fire('click');
  await h.flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, '/api/projects/A/roles/agent%3Amanaged/service/stop');
  assert.equal(h.requests[0].opts.method, 'POST');
  h.reply(0, {
    member_id: 'agent:managed', role_name: 'Managed', launch_id: 'l2', generation: 2, action: 'stop',
    expected_instance_id: 'ins_1', launch_expires_at: '2026-10-11T00:01:00Z', desired: 'stopped', observed: 'stopping',
    idempotent_stopped: false,
  });
  await h.flush();
  assert.equal(h.state('agent:managed'), '关闭中…');
});

test('重复点击：请求在途时不产生第二个 start 请求', async () => {
  const h = harness({ roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ can_start: true }) }] });
  h.setPollDelay(60000);
  await h.enterRoles();
  const button = h.startBtn('agent:managed');
  button.fire('click');
  await h.flush();
  button.fire('click');
  await h.flush();
  const fresh = h.startBtn('agent:managed');
  if (fresh) { fresh.fire('click'); await h.flush(); }
  assert.equal(h.startRequests().length, 1, '并发重复提交被拦截');
  assert.equal(h.roleServiceUI.busy.has('agent:managed'), true);
});

test('HTTP 非 2xx：读取 detail 错误码展示，不显示假成功，且可重试', async () => {
  const h = harness({ roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ can_start: true }) }] });
  h.setPollDelay(60000);
  await h.enterRoles();
  h.startBtn('agent:managed').fire('click');
  await h.flush();
  h.reply(0, { detail: 'control_kind_not_managed' }, { ok: false, status: 409 });
  await h.flush();
  assert.ok(h.hint('agent:managed').includes('control_kind_not_managed'), '稳定错误码如实展示');
  assert.equal(h.state('agent:managed'), '未启动');
  assert.ok(!allTexts(h.controlsFor('agent:managed')).join(' ').includes('启动成功'));
  assert.equal(h.startBtn('agent:managed').disabled, false, '失败后可重试');
});

// ── 轮询生命周期 ────────────────────────────────────────────────────────────
test('starting 触发 role-services 轮询，收敛 running+ready 后停止轮询', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'starting', desired: 'running', can_start: false }) }],
  });
  h.setPollDelay(5);
  await h.enterRoles();
  assert.ok(await h.waitFor(() => h.servicePolls().length >= 1), 'starting 时发起 role-services 轮询');
  assert.equal(h.requests[0].url, '/api/projects/A/role-services');
  assert.equal(h.requests[0].opts, undefined, '轮询为 GET');
  h.reply(0, [{
    member_id: 'agent:managed', role_name: 'Managed', archived: false,
    desired: 'running', observed: 'running', readiness_service: 'ready', native_login: 'verified',
    control_kind: 'managed_cli', can_start: false, can_stop: true, generation: 1,
  }]);
  assert.ok(await h.waitFor(() => h.state('agent:managed') === '启动成功'), '收敛态按轮询结果重绘');
  const settled = h.servicePolls().length;
  await sleep(40);
  assert.equal(h.servicePolls().length, settled, '全部收敛为稳定态后停止轮询');
  assert.equal(h.roleServiceUI.pollTimer, null);
});

test('离页/切项目/切账号停止轮询，不泄漏计时器', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'starting', desired: 'running', can_start: false }) }],
  });
  h.setPollDelay(5);
  await h.enterRoles();
  assert.ok(await h.waitFor(() => h.servicePolls().length >= 1));
  // 真实 app.js 导航：renderWorkspaceMode → syncWorkspaceLayout。
  h.context.__workspaceUI.mode = 'tasks';
  h.context.syncWorkspaceLayout();
  assert.equal(h.roleServiceUI.pollTimer, null, '离页立即清表');
  const left = h.servicePolls().length;
  await sleep(40);
  assert.equal(h.servicePolls().length, left, '离页后不再轮询');
  // 回到角色页后切账号：上下文变化同样停表并清空覆盖层。
  h.context.__workspaceUI.mode = 'roles';
  h.context.myId = 'human:other';
  h.context.syncWorkspaceLayout();
  assert.equal(h.roleServiceUI.pollTimer, null);
  assert.equal(h.roleServiceUI.memberId, 'human:other');
});

test('轮询进行中切项目：迟到 role-services 响应不回写新上下文', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'starting', desired: 'running', can_start: false }) }],
  });
  h.setPollDelay(5);
  await h.enterRoles();
  assert.ok(await h.waitFor(() => h.servicePolls().length >= 1));
  const stale = h.pending.find(p => /\/role-services$/.test(p.url));
  h.context.activeProjectId = 'B';
  h.context.syncWorkspaceLayout();
  stale.resolve({ ok: true, status: 200, json: async () => [{ member_id: 'agent:managed', observed: 'running', readiness_service: 'ready', native_login: 'verified' }] });
  await h.flush();
  assert.equal(h.roleServiceUI.projectId, 'B');
  assert.equal(h.roleServiceUI.overlay.size, 0, '迟到响应不得写入新项目上下文');
});

// ── 全部启动 + 部分失败定向重试 ─────────────────────────────────────────────
test('全部启动部分失败：写入意图只算“启动请求”，重试 member_ids 只含失败项', async () => {
  const h = harness({
    roster: ['agent:a', 'agent:b', 'agent:c'].map(member_id => ({ member_id, business_role: 'dev', service: serviceRow({ can_start: true }) })),
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  h.startAllBtn().fire('click');
  await h.flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, '/api/projects/A/role-services/start-all');
  assert.equal(h.requests[0].opts.method, 'POST');
  assert.equal(h.requests[0].opts.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(h.requests[0].opts.body), {}, '全部启动省略 member_ids');
  h.reply(0, {
    project_id: 'A',
    requested: ['agent:a', 'agent:b', 'agent:c'],
    results: [
      { member_id: 'agent:a', role_name: 'A', status: 'requested', launch_id: 'l1', generation: 1, expected_instance_id: 'ins_1', error_code: null },
      { member_id: 'agent:b', role_name: 'B', status: 'skipped_running', launch_id: null, generation: null, expected_instance_id: null, error_code: null },
      { member_id: 'agent:c', role_name: 'C', status: 'failed', launch_id: null, generation: null, expected_instance_id: null, error_code: 'control_kind_not_managed' },
    ],
    counts: { started: 0, requested: 1, skipped: 1, failed: 1 },
  });
  await h.flush();
  assert.ok(h.retryBtn(), '部分失败时出现“重试失败项”入口');
  const texts = allTexts(h.batchFeedbackBox()).join('\n');
  // F6 口径：写入意图是“启动请求”，绝不显示成“已启动”。
  assert.ok(texts.includes('启动请求 1'), texts);
  assert.ok(texts.includes('已启动 0'), texts);
  assert.ok(texts.includes('跳过 1') && texts.includes('失败 1'), texts);
  assert.ok(texts.includes('control_kind_not_managed'), '失败清单带稳定错误码');
  // 请求成功的角色在页面进入“启动中…”，不是成功。
  assert.equal(h.state('agent:a'), '启动中…');
  h.retryBtn().fire('click');
  await h.flush();
  assert.equal(h.requests.length, 2);
  assert.equal(h.requests[1].url, '/api/projects/A/role-services/start-all');
  assert.deepEqual(JSON.parse(h.requests[1].opts.body), { member_ids: ['agent:c'] }, '只重试失败项，不重复成功/跳过项');
});

test('全部启动：轮询把后到 ready 计成功、后到 failed 归入失败，仍受管的失败只提示先关闭', async () => {
  const h = harness({
    roster: ['agent:a', 'agent:b', 'agent:c'].map(member_id => ({ member_id, business_role: 'dev', service: serviceRow({ can_start: true }) })),
  });
  h.setPollDelay(10);
  await h.enterRoles();
  h.startAllBtn().fire('click');
  await h.flush();
  h.reply(0, {
    project_id: 'A',
    requested: ['agent:a', 'agent:b', 'agent:c'],
    results: [
      { member_id: 'agent:a', role_name: 'A', status: 'requested', launch_id: 'l1', generation: 1, expected_instance_id: 'ins_1', error_code: null },
      { member_id: 'agent:b', role_name: 'B', status: 'requested', launch_id: 'l2', generation: 1, expected_instance_id: 'ins_2', error_code: null },
      { member_id: 'agent:c', role_name: 'C', status: 'requested', launch_id: 'l3', generation: 1, expected_instance_id: 'ins_3', error_code: null },
    ],
    counts: { started: 0, requested: 3, skipped: 0, failed: 0 },
  });
  await h.flush();
  // 等待真实计时器驱动的轮询请求，然后回一份收敛后的服务投影。
  const poll = await h.waitFor(() => h.servicePolls()[0]);
  assert.ok(poll, '批量存在 pending 时继续轮询');
  const index = h.pending.findIndex(p => /\/role-services$/.test(p.url));
  h.reply(index, [
    { member_id: 'agent:a', control_kind: 'managed_cli', observed: 'running', readiness_service: 'ready', generation: 1, ownership_held: false, can_start: false, can_stop: true },
    { member_id: 'agent:b', control_kind: 'managed_cli', observed: 'failed', readiness_service: 'failed', generation: 1, ownership_held: false, can_start: true, can_stop: false, error_code: 'readiness_timeout' },
    { member_id: 'agent:c', control_kind: 'managed_cli', observed: 'failed', readiness_service: 'failed', generation: 1, ownership_held: true, can_start: false, can_stop: true, error_code: 'readiness_timeout' },
  ]);
  await h.flush();
  await h.waitFor(() => allTexts(h.batchFeedbackBox()).join(' ').includes('已启动 1'));
  const texts = allTexts(h.batchFeedbackBox()).join('\n');
  assert.ok(texts.includes('已启动 1'), texts);
  assert.ok(texts.includes('失败 2'), texts);
  assert.ok(texts.includes('需先关闭（原进程归属未释放）'), texts);
  // B 未受管 → 可重试；C 仍受管 → 不能重复启动，必须先关闭。
  assert.equal(h.startBtn('agent:c').disabled, true, '仍持有进程的角色不允许重复启动');
  assert.equal(h.stopBtn('agent:c').disabled, false, '仍持有进程的角色必须先关闭');
  assert.ok(String(h.hint('agent:c')).includes('原进程归属未释放'), h.hint('agent:c'));
  assert.equal(h.state('agent:c'), '启动失败（进程仍受管，请先关闭）');
});

test('全部启动整体失败：展示服务端 detail，不显示假成功', async () => {
  const h = harness({ roster: [{ member_id: 'agent:a', business_role: 'dev', service: serviceRow({ can_start: true }) }] });
  h.setPollDelay(60000);
  await h.enterRoles();
  h.startAllBtn().fire('click');
  await h.flush();
  h.reply(0, { detail: 'role_not_found' }, { ok: false, status: 404 });
  await h.flush();
  assert.ok(allTexts(h.batchFeedbackBox()).join(' ').includes('role_not_found'));
  assert.ok(!h.retryBtn(), '整体失败不出现失败项重试入口');
});

// ── R1-3 页面验收反馈布局：单状态标签、条目化、详情去重、批量入口与反馈分离 ──
test('搜索框在角色重绘与任务切换后保持连接及原输入监听', async () => {
  const html = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
  assert.match(html, /id="blackboard-toolbar"[\s\S]*?id="workspace-search"[\s\S]*?id="role-service-batch-actions"/);
  const h = harness({ roster: [{ member_id: 'agent:search', business_role: 'dev', service: serviceRow() }] });
  const input = h.context.document.getElementById('workspace-search');
  const originalListener = input.listeners.input[0];
  await h.enterRoles();
  for (const mode of ['roles', 'tasks', 'roles']) {
    h.context.__workspaceUI.mode = mode;
    h.context.renderWorkspaceList();
    assert.equal(h.context.document.getElementById('workspace-search'), input);
    assert.equal(input.parentElement, h.el('blackboard-toolbar'));
    assert.equal(h.el('blackboard-toolbar').classList.contains('hidden'), false);
    assert.equal(input.listeners.input[0], originalListener);
    input.value = mode === 'roles' ? '不存在的角色' : '不存在的任务';
    input.fire('input', { target: input });
    assert.equal(h.context.__workspaceUI.query, input.value);
    assert.ok(allTexts(h.el('blackboard-columns')).some(text => text.includes(mode === 'roles' ? '没有匹配的角色' : '没有匹配的结果')));
  }
});

test('列表条目：只显示当前状态，不出现启动/关闭两个按钮', async () => {
  const h = harness({
    roster: [
      { member_id: 'agent:a', business_role: 'dev', service: serviceRow({ can_start: true }) },
      { member_id: 'agent:b', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', native_login: 'verified', can_stop: true }) },
    ],
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  for (const memberId of ['agent:a', 'agent:b']) {
    const box = h.controlsFor(memberId);
    assert.ok(box, `${memberId} 渲染服务控制块`);
    const states = findAll(box, n => String(n.className).includes('role-service-state'));
    assert.equal(states.length, 1, `${memberId} 只展示一个当前状态标签`);
    // 用户所指“未启动、启动、关闭”只保留当前状态，操作仅在详情。
    const buttons = findAll(box, n => n.tagName === 'button').map(n => n.textContent);
    assert.deepEqual(buttons, [], `${memberId} 的列表状态旁不再有启动/关闭`);
    // 条目化：角色行与服务控制同属一个 .role-entry，状态标签不出现在角色行按钮内部。
    const entry = h.rows().find(node => String(node.className).includes('role-entry')
      && findAll(node, n => String(n.className).includes('role-service-controls')).length === 1
      && findAll(node, n => n.dataset && n.dataset.memberId === memberId).length > 0);
    assert.ok(entry, `${memberId} 的角色行与服务控制同属一个条目`);
    const roleRowButton = entry.children.find(n => String(n.className).includes('role-row'));
    assert.ok(roleRowButton && String(roleRowButton.tagName).toLowerCase() === 'button', '角色行仍是按钮');
    assert.equal(findAll(roleRowButton, n => String(n.className).includes('role-service-state')).length, 0,
      '状态标签不在角色行按钮内部（避免嵌套按钮与压线）');
  }
  assert.ok(h.state('agent:a') !== h.state('agent:b'), '两个角色的当前状态各自独立展示');
});

test('批量入口与反馈分离：按钮在顶栏操作区，进度/重试在独立反馈区', async () => {
  const h = harness({
    roster: ['agent:a', 'agent:b'].map(member_id => ({ member_id, business_role: 'dev', service: serviceRow({ can_start: true }) })),
  });
  h.setPollDelay(60000);
  await h.enterRoles();
  assert.ok(h.startAllBtn(), '“全部启动”在顶栏操作区');
  assert.equal(h.batchFeedbackBox().children.length, 0, '无反馈时反馈区为空');
  assert.equal(findAll(h.el('blackboard-summary'), n => n.tagName === 'button').length, 0, '角色页不把批量入口混进任务筛选标签行');
  h.startAllBtn().fire('click');
  await h.flush();
  h.reply(0, {
    project_id: 'A',
    requested: ['agent:a', 'agent:b'],
    results: [
      { member_id: 'agent:a', role_name: 'A', status: 'requested', launch_id: 'l1', generation: 1, expected_instance_id: 'ins_1', error_code: null },
      { member_id: 'agent:b', role_name: 'B', status: 'failed', launch_id: null, generation: null, expected_instance_id: null, error_code: 'control_kind_not_managed' },
    ],
    counts: { started: 0, requested: 1, skipped: 0, failed: 1 },
  });
  await h.flush();
  const feedback = allTexts(h.batchFeedbackBox()).join('\n');
  assert.ok(feedback.includes('启动请求 1') && feedback.includes('失败 1'), feedback);
  assert.ok(h.retryBtn(), '失败重试入口在反馈区');
  // 顶栏操作区只保留全部启动，重试与进度留在反馈区。
  const toolbarButtons = findAll(h.batchBox(), n => n.tagName === 'button').map(n => n.textContent);
  assert.deepEqual(toolbarButtons, ['全部启动']);
  assert.ok(!allTexts(h.batchBox()).join(' ').includes('启动请求'), '顶栏操作区不承载进度文本');
});

// ── 角色详情 + 只读账号 ─────────────────────────────────────────────────────
test('角色详情不重复服务状态标签：保留启动/关闭与必要提示', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', native_login: 'verified', can_start: false, can_stop: true }) }],
  });
  await h.enterRoles();
  await h.selectRole('agent:managed');
  const section = findAll(h.el('role-details-name-panel'), n => String(n.className).includes('role-service-section'))[0];
  assert.ok(section, '角色详情渲染服务控制区');
  assert.equal(findAll(section, n => String(n.className).includes('role-service-state')).length, 0,
    '详情区（标题旁与 controls 内）不再展示服务状态标签');
  assert.ok(!allTexts(section).join(' ').includes('启动成功'), '详情不重复状态文案');
  const startButton = findAll(section, n => n.tagName === 'button' && n.textContent === '启动')[0];
  const stopButton = findAll(section, n => n.tagName === 'button' && n.textContent === '关闭')[0];
  assert.equal(startButton.disabled, true);
  assert.equal(stopButton.disabled, false);
  // 列表仍是当前状态的入口：状态标签只在列表条目里出现。
  assert.equal(h.state('agent:managed'), '启动成功', '当前状态入口保留在角色列表');
  assert.equal(h.controlsFor('agent:managed') === undefined, false);
});

test('agent 账号只读：启动/关闭/全部启动禁用，不发写请求', async () => {
  const h = harness({
    human: false,
    roster: [{ member_id: 'agent:managed', business_role: 'dev', service: serviceRow({ observed: 'running', readiness_service: 'ready', can_start: false, can_stop: true }) }],
  });
  await h.enterRoles();
  assert.equal(h.startBtn('agent:managed').disabled, true);
  assert.equal(h.stopBtn('agent:managed').disabled, true);
  assert.equal(h.startAllBtn().disabled, true);
  h.startBtn('agent:managed').fire('click');
  h.stopBtn('agent:managed').fire('click');
  h.startAllBtn().fire('click');
  await h.flush();
  assert.equal(h.requests.filter(r => r.opts && r.opts.method === 'POST').length, 0, 'agent 不发任何写请求');
});

test('未归档才有控制；归档角色不渲染服务控制', async () => {
  const h = harness({
    roster: [
      { member_id: 'agent:live', business_role: 'dev', service: serviceRow({ can_start: true }) },
      { member_id: 'agent:archived', business_role: 'dev', archived: true, service: serviceRow({ can_start: true }) },
    ],
  });
  await h.enterRoles();
  assert.ok(h.controlsFor('agent:live'));
  assert.equal(h.controlsFor('agent:archived'), undefined, '归档角色不显示服务控制');
});
