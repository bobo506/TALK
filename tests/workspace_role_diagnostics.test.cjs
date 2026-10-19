// 运行诊断候选：真实 role-diagnostics.js + 冻结 workspace.js 最小钩子的纯 DOM/VM 交互测试。
// 全部 API 均为手动 resolved fake；不启动 HTTP/浏览器/CLI，不读真实日志、DB 或凭据。
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const diagnosticsSource = fs.readFileSync(require.resolve('../web/role-diagnostics.js'), 'utf8');
const indexSource = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
const cssSource = fs.readFileSync(require.resolve('../web/role-diagnostics.css'), 'utf8');
const fixtures = JSON.parse(fs.readFileSync(require.resolve('../docs/spec/ROLE_RUNTIME_LOG_VIEW_EXAMPLES.json'), 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));
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
function runningService(overrides = {}) {
  return serviceRow({
    observed: 'running', last_action: 'start', last_result: 'success', readiness_service: 'ready',
    can_start: false, can_stop: true, ownership_held: true,
    observed_instance_id: 'ins_fake_current92',
    current_launch: {
      launch_id: 'launch-fake-a91c', action: 'start', state: 'reported', expected_instance_id: 'ins_fake_current92',
      launch_expires_at: '2026-10-19T00:00:00Z', claimed_at: '2026-10-18T19:00:00Z', reported_at: '2026-10-18T19:01:00Z', outcome: 'ready', error_code: null,
    },
    ...overrides,
  });
}

const activeHarnesses = [];
afterEach(() => {
  for (const h of activeHarnesses.splice(0)) {
    h.context.stopRoleServicePolling();
    h.context.roleDiagnostics.closeDetail({ restoreFocus: false });
  }
});

function harness({ human = true, service = serviceRow(), roster = null, clipboard = null } = {}) {
  const pending = [];
  const requests = [];
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
  // 静态表单的实际默认值；其余页面元素仅作 workspace.js 的 DOM 桩。
  const defaults = {
    'role-log-time': '24h', 'role-log-instance': '', 'role-log-since': '', 'role-log-until': '',
    'role-log-launch': '', 'role-log-task': '', 'role-log-event': '', 'role-log-stage': '', 'role-log-ref': '',
    'workspace-search': '', 'role-description-input': '', 'requirements-input': '',
  };
  for (const [id, value] of Object.entries(defaults)) if (elements.has(id)) elements.get(id).value = value;
  elements.get('role-log-severity-error').checked = true;
  elements.get('role-log-severity-warning').checked = true;
  const account = { human };
  const roles = roster || [
    { member_id: 'agent:fake-a', business_role: 'dev', role_description: null, service },
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
    navigator: { clipboard: clipboard || { writeText: async () => {} } },
    AbortController,
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
    projectTasks: [{ id: 901, target_member_id: 'agent:fake-a', created_by: 'human:qa', title: '既有任务', workflow_status: 'in_progress', content: '保留任务区' }],
    groups: [], projects: [{ project_id: 'prj_fake_a' }, { project_id: 'prj_fake_b' }],
    currentMemberIsHuman: () => account.human,
    apiFetch: (url, opts) => {
      const request = { url, opts: opts || {}, index: requests.length };
      requests.push(request);
      const promise = new Promise((resolve, reject) => { request.resolve = resolve; request.reject = reject; });
      pending.push(request);
      return promise;
    },
    readErrorDetail: async (res, fallback) => { try { const body = await res.json(); return body && body.detail || fallback; } catch (_) { return fallback; } },
    taskStatusMeta: () => ({ label: '执行中', className: 'running' }),
    formatTaskTime: () => '10-18 20:00',
    selectWorkspaceTask: () => {},
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
  vm.runInContext('this.__workspaceUI = workspaceUI;', context);
  const el = id => elements.get(id);
  const flush = async () => { for (let i = 0; i < 6; i++) await sleep(0); };
  const render = () => { context.renderWorkspaceList(); context.renderTaskDetailsPanel(); };
  const selectRole = memberId => {
    context.__workspaceUI.mode = 'roles';
    context.__workspaceUI.roleSelection = 'role';
    context.__workspaceUI.selectedRole = memberId;
    render();
  };
  selectRole('agent:fake-a');
  const respond = (request, body, status = 200) => {
    request.resolve({ ok: status >= 200 && status < 300, status, json: async () => clone(body) });
  };
  const logRequests = () => requests.filter(request => request.url.includes('/runtime-logs'));
  const lastRequest = () => logRequests()[logRequests().length - 1];
  const recordsText = () => allTexts(el('role-log-records')).join('\n');
  const h = {
    context, account, roles, el, pending, requests, logRequests, lastRequest, respond, flush, render, selectRole,
    ui: context.__workspaceUI, diag: context.roleDiagnostics, recordsText, windowListeners,
    startDefault: () => click(el('role-log-view-btn')),
    query: () => el('role-log-query-btn').disabled ? [] : el('role-log-filter-form').fire('submit'),
    detailButtons: () => findAll(el('role-log-records'), n => n.tagName === 'button' && n.textContent === '查看详情'),
    copyButtons: () => findAll(el('role-log-records'), n => n.tagName === 'button' && n.textContent === '复制引用'),
  };
  activeHarnesses.push(h);
  return h;
}

function pageFixture(overrides = {}) {
  const page = clone(fixtures.list_complete);
  Object.assign(page, overrides);
  return page;
}
function detailFixture(overrides = {}) {
  const detail = clone(fixtures.detail);
  if (overrides.record) Object.assign(detail.record, overrides.record);
  const rest = { ...overrides }; delete rest.record;
  Object.assign(detail, rest);
  return detail;
}
function assertWhitelistedListUrl(url) {
  const parsed = new URL(url, 'http://fixture.invalid');
  const allowed = new Set(['ref', 'since', 'until', 'instance_id', 'launch_id', 'task_id', 'event', 'stage', 'severity', 'limit', 'cursor']);
  for (const key of parsed.searchParams.keys()) assert.ok(allowed.has(key), `unexpected query key ${key}`);
  for (const forbidden of ['root', 'path', 'file', 'host', 'follow_symlinks', 'sql', 'where', 'glob', 'detail']) assert.ok(!parsed.searchParams.has(forbidden));
}

test('静态入口位于说明与任务区之间，资源版本统一且日志代码不解析 innerHTML', () => {
  const description = indexSource.indexOf('id="role-description-panel"');
  const diagnostics = indexSource.indexOf('id="role-diagnostics-panel"');
  const tasks = indexSource.indexOf('id="role-details-tasks-panel"');
  assert.ok(description >= 0 && description < diagnostics && diagnostics < tasks);
  assert.ok(indexSource.indexOf('/role-diagnostics.js') < indexSource.indexOf('/workspace.js'));
  const versions = [...indexSource.matchAll(/(?:href|src)="\/[^"?]+\?v=([^"]+)"/g)].map(match => match[1]);
  assert.ok(versions.length >= 7 && versions.every(version => version === '20261019-runtime-log-view-v1'));
  assert.ok(!diagnosticsSource.includes('innerHTML'));
  assert.match(cssSource, /overflow-wrap:\s*anywhere/);
});

test('human 选角色不自动查日志，静态筛选/说明/任务/开关钩子在重绘后保持', async () => {
  const h = harness();
  assert.equal(h.logRequests().length, 0);
  assert.equal(h.el('role-log-status').textContent.includes('尚未查询'), true);
  assert.equal(h.el('role-evidence-queue').textContent, '当前接单循环：未知');
  assert.match(h.el('role-evidence-preflight').textContent, /未知/);
  const filter = h.el('role-log-launch');
  const description = h.el('role-description-input');
  filter.value = 'draft-not-sent';
  description.value = '未保存说明';
  description.fire('input', { target: description });
  for (let i = 0; i < 3; i++) h.render();
  assert.equal(h.el('role-log-launch'), filter);
  assert.equal(filter.value, 'draft-not-sent');
  assert.equal(h.el('role-description-input'), description);
  assert.equal(description.value, '未保存说明');
  assert.match(allTexts(h.el('role-details-name-panel')).join(' '), /角色开关/);
  h.ui.roleFilter = 'running'; h.render();
  assert.match(allTexts(h.el('role-details-tasks-panel')).join(' '), /既有任务/);
  assert.equal(h.logRequests().length, 0);
  await h.flush();
});

test('默认点击查看才查询：24h 由服务端默认、error+warning、20 条，防重复提交并渲染摘要', async () => {
  const h = harness({ service: runningService() });
  h.startDefault();
  h.startDefault();
  assert.equal(h.logRequests().length, 1);
  const request = h.lastRequest();
  assertWhitelistedListUrl(request.url);
  const params = new URL(request.url, 'http://fixture.invalid').searchParams;
  assert.equal(params.has('since'), false);
  assert.equal(params.has('until'), false);
  assert.equal(params.get('severity'), 'error,warning');
  assert.equal(params.get('limit'), '20');
  assert.equal(request.opts.method, 'GET');
  h.respond(request, fixtures.list_complete);
  await h.flush();
  const text = h.recordsText();
  assert.match(text, /2026/);
  assert.match(text, /错误/);
  assert.match(text, /task_claim_failed/);
  assert.match(text, /task_claim/);
  assert.match(text, /TaskClaimError/);
  assert.match(text, /当前实例 ins_fake_current92/);
  assert.match(text, /历史实例 ins_fake_old17/);
  assert.match(text, /launch-fake-a91c/);
  assert.match(text, /#273/);
  assert.match(text, /rtd-031f55a209-000001/);
  assert.match(text, /写入完整/);
  assert.ok(!text.includes('handle_queued_task'), '列表不预埋详情帧');
  assert.equal(h.detailButtons().length, 2);
  assert.equal(h.logRequests().length, 1, '渲染不自动读取详情');
});

test('Agent 只看既有服务证据，日志控件禁用且任何入口都不发请求', async () => {
  const h = harness({ human: false, service: runningService() });
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), false);
  assert.equal(h.el('role-log-view-btn').disabled, true);
  assert.match(h.el('role-log-permission').textContent, /没有运行日志查看权限/);
  assert.match(h.el('role-evidence-owner').textContent, /归属未释放/);
  h.startDefault(); h.query(); h.diag.startRefQuery(); h.diag.openDetail('rtd-031f55a209-000001');
  await h.flush();
  assert.equal(h.logRequests().length, 0);
  assert.equal(h.recordsText(), '');
  assert.doesNotMatch(h.el('role-log-status').textContent, /没有可查日志|未发现异常/);
});

test('异常/全部事件与合同内组合筛选精确发送；当前实例同时限定 launch', async () => {
  const h = harness({ service: runningService() });
  click(h.el('role-log-mode-all'));
  h.el('role-log-time').value = '1h'; h.el('role-log-time').fire('change');
  h.el('role-log-instance').value = '__current__'; h.el('role-log-instance').fire('change');
  h.el('role-log-task').value = '273'; h.el('role-log-task').fire('input');
  h.el('role-log-event').value = 'queue_started'; h.el('role-log-event').fire('input');
  h.el('role-log-stage').value = 'queue'; h.el('role-log-stage').fire('input');
  h.query();
  assert.equal(h.logRequests().length, 1);
  const params = new URL(h.lastRequest().url, 'http://fixture.invalid').searchParams;
  assert.equal(params.get('severity'), 'error,warning,info');
  assert.equal(params.get('instance_id'), 'ins_fake_current92');
  assert.equal(params.get('launch_id'), 'launch-fake-a91c');
  assert.equal(params.get('task_id'), '273');
  assert.equal(params.get('event'), 'queue_started');
  assert.equal(params.get('stage'), 'queue');
  assert.ok(Number.isFinite(Date.parse(params.get('since'))));
  assert.ok(Number.isFinite(Date.parse(params.get('until'))));
  assert.equal(params.get('limit'), '20');
  assertWhitelistedListUrl(h.lastRequest().url);
  h.respond(h.lastRequest(), fixtures.list_complete);
  await h.flush();
});

test('本地参数校验拒绝无TimeZone/超31天/坏ref/不支持形态，不发请求', async () => {
  const h = harness();
  h.el('role-log-time').value = 'custom'; h.el('role-log-time').fire('change');
  h.el('role-log-since').value = '2026-10-01T00:00:00'; h.el('role-log-since').fire('input');
  h.el('role-log-until').value = '2026-10-02T00:00:00Z'; h.el('role-log-until').fire('input');
  h.query();
  assert.match(h.el('role-log-status').textContent, /带时区/);
  h.el('role-log-since').value = '2026-09-01T00:00:00Z'; h.el('role-log-since').fire('input');
  h.el('role-log-until').value = '2026-10-18T00:00:00Z'; h.el('role-log-until').fire('input');
  h.query();
  assert.match(h.el('role-log-status').textContent, /31 天/);
  h.el('role-log-ref').value = '../../etc/passwd';
  h.diag.startRefQuery();
  assert.match(h.el('role-log-status').textContent, /不是路径/);
  h.el('role-log-time').value = '24h'; h.el('role-log-time').fire('change');
  h.el('role-log-event').value = 'task*'; h.el('role-log-event').fire('input');
  h.query();
  assert.match(h.el('role-log-status').textContent, /事件只能使用/);
  await h.flush();
  assert.equal(h.logRequests().length, 0);
});

test('独立 ref 不带默认时间/异常级别；info null exception 的列表与详情诚实显示', async () => {
  const h = harness();
  const ref = 'rtd-info-old01';
  const info = clone(fixtures.list_complete.records[0]);
  Object.assign(info, { log_id: ref, event: 'queue_started', severity: 'info', exception: null, recorded_at: '2026-09-01T00:00:00Z' });
  h.el('role-log-ref').value = ref;
  h.diag.startRefQuery();
  const request = h.lastRequest();
  const params = new URL(request.url, 'http://fixture.invalid').searchParams;
  assert.equal(params.get('ref'), ref);
  assert.equal([...params.keys()].join(','), 'ref');
  const page = pageFixture({ records: [info] });
  page.query.ref = ref; page.query.since = null; page.query.until = null; page.query.severity = null;
  h.respond(request, page); await h.flush();
  assert.match(h.recordsText(), /该事件没有异常摘要/);
  click(h.detailButtons()[0]);
  const detailRequest = h.lastRequest();
  assert.ok(detailRequest.url.endsWith(`/runtime-logs/${ref}/detail`));
  assert.ok(!detailRequest.url.includes('?'));
  const detail = detailFixture({ record: info });
  h.respond(detailRequest, detail); await h.flush();
  assert.match(allTexts(h.el('role-log-detail-content')).join(' '), /该事件没有异常堆栈/);
  assert.doesNotMatch(allTexts(h.el('role-log-detail-content')).join(' '), /TaskClaimError/);
});

test('详情仅显式读取，展示全部已记录帧/因果链/省略与完整性，关闭清空并恢复焦点', async () => {
  const h = harness({ service: runningService() });
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  const trigger = h.detailButtons()[0];
  click(trigger);
  assert.equal(h.logRequests().length, 2);
  assert.equal(h.el('role-log-detail-dialog').open, true);
  h.respond(h.lastRequest(), fixtures.detail); await h.flush();
  const text = allTexts(h.el('role-log-detail-content')).join('\n');
  assert.match(text, /cli_bridge.py:3214 · handle_queued_task/);
  assert.match(text, /talk_client.py:88 · claim_task/);
  assert.match(text, /explicit_cause|显式原因/);
  assert.match(text, /fake_transport.py:12 · request/);
  assert.match(text, /链深度：1/);
  assert.match(text, /脱敏类型：known_value、secret_field/);
  assert.ok(!text.includes('source_file'));
  click(h.el('role-log-detail-close'));
  assert.equal(h.el('role-log-detail-dialog').open, false);
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  assert.ok(trigger.focusCount > 0, '关闭后返回详情触发按钮');
});

test('详情关闭/切角色后的迟到成功与失败均不回填；离页立即清空', async () => {
  const h = harness();
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  click(h.detailButtons()[0]);
  const late = h.lastRequest();
  click(h.el('role-log-detail-close'));
  h.respond(late, fixtures.detail); await h.flush();
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  click(h.detailButtons()[0]);
  const switched = h.lastRequest();
  h.selectRole('agent:fake-b');
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  h.respond(switched, { detail: 'diagnostics_unavailable' }, 503); await h.flush();
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  assert.equal(h.el('role-log-status').textContent.includes('尚未查询'), true);
  h.startDefault();
  const leaving = h.lastRequest();
  h.ui.mode = 'tasks'; h.render();
  h.respond(leaving, fixtures.list_complete); await h.flush();
  assert.equal(h.recordsText(), '');
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), true);
});

test('XSS 与长文只进 textContent/pre；复制失败有反馈，恢复后可复制', async () => {
  const h = harness({ clipboard: { writeText: async () => { throw new Error('denied'); } } });
  const payload = '<img src=x onerror=alert(1)>' + '长文'.repeat(400);
  const page = pageFixture();
  page.records[0].exception.message_preview = payload;
  h.startDefault(); h.respond(h.lastRequest(), page); await h.flush();
  assert.ok(h.recordsText().includes(payload));
  assert.equal(findAll(h.el('role-log-records'), n => ['img', 'script'].includes(n.tagName)).length, 0);
  click(h.copyButtons()[0]); await h.flush();
  assert.match(h.el('role-log-status').textContent, /复制失败.*手动选择/);
  h.context.window.navigator.clipboard = { writeText: async () => {} };
  click(h.copyButtons()[0]); await h.flush();
  assert.match(h.el('role-log-status').textContent, /已复制/);
  click(h.detailButtons()[0]);
  const detail = detailFixture();
  detail.record.exception.message = '<script>globalThis.compromised=true</script>';
  h.respond(h.lastRequest(), detail); await h.flush();
  assert.ok(allTexts(h.el('role-log-detail-content')).join(' ').includes('<script>globalThis.compromised=true</script>'));
  assert.equal(findAll(h.el('role-log-detail-content'), n => n.tagName === 'script').length, 0);
  assert.equal(h.context.globalThis ? h.context.globalThis.compromised : undefined, undefined);
});

test('角色切换使在途旧响应作废；新角色先到后旧角色再到也不污染', async () => {
  const h = harness();
  h.startDefault();
  const oldA = h.lastRequest();
  h.selectRole('agent:fake-b');
  h.startDefault();
  const newB = h.lastRequest();
  const pageB = pageFixture();
  pageB.scope.member_id = 'agent:fake-b';
  pageB.records = pageB.records.slice(0, 1).map(record => ({ ...record, member_id: 'agent:fake-b', log_id: 'rtd-role-b0001' }));
  h.respond(newB, pageB); await h.flush();
  assert.match(h.recordsText(), /rtd-role-b0001/);
  h.respond(oldA, fixtures.list_complete); await h.flush();
  assert.match(h.recordsText(), /rtd-role-b0001/);
  assert.doesNotMatch(h.recordsText(), /rtd-031f55a209-000001/);
  assert.equal(h.diag._state.role.member_id, 'agent:fake-b');
});

test('在途切项目、切账号均清空上下文并拒绝旧响应', async () => {
  const h = harness();
  h.startDefault();
  const oldProject = h.lastRequest();
  h.context.activeProjectId = 'prj_fake_b';
  h.render();
  assert.equal(h.recordsText(), '');
  h.startDefault();
  const newProject = h.lastRequest();
  const projectPage = pageFixture();
  projectPage.scope.project_id = 'prj_fake_b';
  projectPage.records = projectPage.records.map(record => ({ ...record, project_id: 'prj_fake_b' }));
  h.respond(oldProject, fixtures.list_complete);
  h.respond(newProject, projectPage); await h.flush();
  assert.match(h.recordsText(), /rtd-031f55a209-000001/);
  h.startDefault();
  const oldAccount = h.lastRequest();
  h.context.myId = 'human:other';
  h.render();
  assert.equal(h.recordsText(), '');
  h.startDefault();
  const newAccount = h.lastRequest();
  h.respond(oldAccount, projectPage);
  h.respond(newAccount, projectPage); await h.flush();
  assert.match(h.recordsText(), /rtd-031f55a209-000001/);
  assert.equal(h.diag._state.accountId, 'human:other');
});

test('分页重放首页绝对规范化 query；加载中禁筛选/防重复，stale_cursor 清空旧页不拼接', async () => {
  const h = harness();
  const first = pageFixture();
  first.records = first.records.slice(0, 1);
  first.page.has_more = true; first.page.next_cursor = 'cursor.one';
  h.startDefault(); h.respond(h.lastRequest(), first); await h.flush();
  const canonical = clone(first.query);
  click(h.el('role-log-more-btn'));
  click(h.el('role-log-more-btn'));
  assert.equal(h.logRequests().length, 2);
  assert.equal(h.el('role-log-time').disabled, true);
  const secondRequest = h.lastRequest();
  const secondParams = new URL(secondRequest.url, 'http://fixture.invalid').searchParams;
  assert.equal(secondParams.get('since'), canonical.since);
  assert.equal(secondParams.get('until'), canonical.until);
  assert.equal(secondParams.get('severity'), 'error,warning');
  assert.equal(secondParams.get('cursor'), 'cursor.one');
  assert.equal(secondParams.get('limit'), '20');
  const second = pageFixture();
  second.records = second.records.slice(1);
  second.page.has_more = true; second.page.next_cursor = 'cursor.two';
  h.respond(secondRequest, second); await h.flush();
  assert.match(h.recordsText(), /rtd-031f55a209-000001/);
  assert.match(h.recordsText(), /rtd-91aa55bb09-000007/);
  click(h.el('role-log-more-btn'));
  assert.equal(new URL(h.lastRequest().url, 'http://fixture.invalid').searchParams.get('cursor'), 'cursor.two');
  h.respond(h.lastRequest(), { detail: 'stale_cursor' }, 409); await h.flush();
  assert.equal(h.recordsText(), '');
  assert.match(h.el('role-log-status').textContent, /分页依据已变化.*旧页已清空/);
  assert.equal(h.el('role-log-more-btn').classList.contains('hidden'), true);
});

test('完整无异常/无事件、不完整扫描、坏行与不可读来源计数分别诚实呈现', async () => {
  const h = harness();
  const empty = pageFixture({ records: [] });
  h.startDefault(); h.respond(h.lastRequest(), empty); await h.flush();
  assert.match(h.el('role-log-status').textContent, /未发现异常日志/);
  click(h.el('role-log-mode-all')); h.query();
  const emptyAll = pageFixture({ records: [] });
  emptyAll.query.severity = ['error', 'warning', 'info'];
  h.respond(h.lastRequest(), emptyAll); await h.flush();
  assert.match(h.el('role-log-status').textContent, /没有可查日志/);
  h.el('role-log-time').value = '1h'; h.el('role-log-time').fire('change'); h.query();
  h.respond(h.lastRequest(), fixtures.list_limited); await h.flush();
  assert.match(h.el('role-log-status').textContent, /不能据此确认没有日志/);
  assert.match(h.el('role-log-scan').textContent, /扫描达到上限.*可能不完整/);
  assert.equal(h.el('role-log-more-btn').classList.contains('hidden'), true);
  h.el('role-log-time').value = '24h'; h.el('role-log-time').fire('change'); h.query();
  const bad = pageFixture({ records: [] });
  bad.scan.complete = false; bad.scan.truncated = false; bad.scan.malformed_lines = 2; bad.scan.unavailable_sources = 1;
  h.respond(h.lastRequest(), bad); await h.flush();
  assert.match(h.el('role-log-scan').textContent, /无法读取或解析.*未将缺失记录当作无异常/);
  assert.doesNotMatch(h.el('role-log-status').textContent, /当前范围内没有可查日志|未发现异常日志/);
});

test('403/404ref/422/503 与详情扫描失败均使用合同语义，不伪造空态', async () => {
  const h = harness();
  const cases = [
    [403, 'log_read_forbidden', /没有运行日志查看权限/],
    [422, 'invalid_filter', /查询参数不符合合同/],
    [503, 'diagnostics_unavailable', /无法读取该角色的日志来源.*不表示角色已停止或没有异常/],
  ];
  for (const [status, detail, expected] of cases) {
    h.diag.resetToDefault(); h.startDefault();
    h.respond(h.lastRequest(), { detail }, status); await h.flush();
    assert.match(h.el('role-log-status').textContent, expected);
    assert.doesNotMatch(h.el('role-log-status').textContent, /当前范围内没有可查日志/);
    assert.match(h.el('role-evidence-claim').textContent, /尚未查询/);
    assert.match(h.el('role-evidence-queue-detail').textContent, /尚未查询/);
  }
  h.el('role-log-ref').value = 'rtd-unknown01';
  h.diag.startRefQuery(); h.respond(h.lastRequest(), { detail: 'log_not_found' }, 404); await h.flush();
  assert.match(h.el('role-log-status').textContent, /可能已超出保留期.*从未写入成功.*不属于当前项目与角色/);
  h.diag.resetToDefault(); h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  click(h.detailButtons()[0]);
  h.respond(h.lastRequest(), { detail: 'diagnostics_scan_incomplete' }, 503); await h.flush();
  assert.match(h.el('role-log-detail-status').textContent, /扫描未完成.*不能据此判定不存在/);
});

test('五类证据分离：无宿主/queue/preflight 心跳均未知，历史领取与当前/旧实例不推健康', async () => {
  const h = harness({ service: runningService() });
  assert.match(h.el('role-evidence-owner').textContent, /归属未释放.*宿主当前状态未知/);
  assert.doesNotMatch(h.el('role-evidence-owner').textContent, /宿主正常/);
  assert.match(h.el('role-evidence-heartbeat').textContent, /近期有实例心跳/);
  const wrongLaunch = h.diag.recordInstanceRelation({ instance_id: 'ins_fake_current92', launch_id: 'launch-fake-old17' });
  assert.equal(wrongLaunch.current, false, '同实例但旧 launch 仍必须标历史');
  assert.match(wrongLaunch.text, /历史实例/);
  assert.equal(h.el('role-evidence-queue').textContent, '当前接单循环：未知');
  assert.match(h.el('role-evidence-preflight').textContent, /未知/);
  const queue = clone(fixtures.list_complete.records[0]);
  Object.assign(queue, { log_id: 'rtd-queue-current1', event: 'queue_started', severity: 'info', exception: null, task_id: null });
  const claim = clone(fixtures.list_complete.records[0]);
  Object.assign(claim, { log_id: 'rtd-claim-current1', event: 'task_claimed', severity: 'info', exception: null, task_id: 273 });
  click(h.el('role-log-mode-all')); h.query();
  const page = pageFixture({ records: [queue, claim] });
  page.query.severity = ['error', 'warning', 'info'];
  h.respond(h.lastRequest(), page); await h.flush();
  assert.equal(h.el('role-evidence-queue').textContent, '当前接单循环：未知');
  assert.match(h.el('role-evidence-queue-detail').textContent, /queue_started.*当前实例/);
  assert.match(h.el('role-evidence-claim').textContent, /#273.*当前能力未验证/);
  assert.match(h.el('role-evidence-claim-detail').textContent, /历史领取不代表当前可接单.*idle 也不等于接单正常/);
  assert.match(h.el('role-evidence-preflight').textContent, /未知/);
  const stale = harness({ service: runningService({ observed: 'unknown', readiness_service: 'unknown', error_code: 'instance_heartbeat_expired' }) });
  assert.match(stale.el('role-evidence-heartbeat').textContent, /待核实.*不证明实例已死亡/);
  assert.doesNotMatch(stale.el('role-evidence-owner').textContent, /宿主正常/);
});

test('当前实例筛选在 launch/实例证据缺失时本地拒绝，不把旧实例算当前', async () => {
  const h = harness();
  h.el('role-log-instance').value = '__current__'; h.el('role-log-instance').fire('change');
  h.query();
  assert.match(h.el('role-log-status').textContent, /当前 launch 与实例身份未完整匹配/);
  assert.equal(h.logRequests().length, 0);
  const current = h.diag.recordInstanceRelation({ instance_id: 'ins_fake_current92', launch_id: 'launch-fake-a91c' });
  assert.equal(current.current, false);
  assert.match(current.text, /历史实例/);
});

test('分页响应规范化 query 或记录 scope 变化时拒绝拼接/展示', async () => {
  const h = harness();
  const first = pageFixture();
  first.records = first.records.slice(0, 1); first.page.has_more = true; first.page.next_cursor = 'cursor.one';
  h.startDefault(); h.respond(h.lastRequest(), first); await h.flush();
  click(h.el('role-log-more-btn'));
  const mismatched = pageFixture();
  mismatched.records = mismatched.records.slice(1); mismatched.query.until = '2020-01-01T00:00:00Z';
  h.respond(h.lastRequest(), mismatched); await h.flush();
  assert.match(h.el('role-log-status').textContent, /规范化 query 与首页不一致/);
  assert.doesNotMatch(h.recordsText(), /rtd-91aa55bb09-000007/);
  h.diag.resetToDefault(); h.startDefault();
  const wrongScope = pageFixture(); wrongScope.records[0].project_id = 'prj_other';
  h.respond(h.lastRequest(), wrongScope); await h.flush();
  assert.match(h.el('role-log-status').textContent, /当前项目与角色之外/);
  assert.equal(h.recordsText(), '');
});

test('pagehide 作废列表与详情请求并清空详情，迟到响应不复活', async () => {
  const h = harness();
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  click(h.detailButtons()[0]);
  const detailRequest = h.lastRequest();
  for (const fn of h.windowListeners.pagehide || []) fn();
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  assert.equal(h.diag._state.visible, false);
  h.respond(detailRequest, fixtures.detail); await h.flush();
  assert.equal(h.el('role-log-detail-content').children.length, 0);
  assert.equal(h.diag._state.records.length, 0);
});

const reviewAppSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');

test('复核：pagehide 清除已渲染日志、筛选和分页，避免页面缓存恢复旧内容', async () => {
  const h = harness();
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  assert.notEqual(h.recordsText(), '');
  h.el('role-log-ref').value = 'rtd-private-draft';
  for (const fn of h.windowListeners.pagehide || []) fn();
  assert.equal(h.recordsText(), '');
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), true);
  assert.equal(h.el('role-log-ref').value, '');
  assert.equal(h.diag._state.canonicalQuery, null);
  assert.equal(h.diag._state.accountId, null);
});

test('复核：退出登录在导航前清除敏感内容并拒绝在途旧响应', async () => {
  const h = harness();
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  click(h.detailButtons()[0]); const late = h.lastRequest();
  const match = reviewAppSource.match(/logoutBtn.addEventListener\("click", \(\) => \{([\s\S]*?)\n\}\);/);
  assert.ok(match, '使用实际退出回调');
  Object.assign(h.context, {
    pollTimer: null, taskPollTimer: null, taskDurationTimer: null, reconnectTimer: null, ws: null,
    closeEventStream() {}, clearStoredApiKeys() {},
    location: { reload() {
      assert.equal(h.recordsText(), '', 'reload 调用前必须清空');
      assert.equal(h.diag._state.visible, false);
    } },
  });
  vm.runInContext(match[1], h.context);
  h.respond(late, fixtures.detail); await h.flush();
  assert.equal(h.el('role-log-detail-content').children.length, 0);
});

test('复核：详情呈现实际返回码、超时/取消、预算和关联引用，0/false 不冒充缺失', async () => {
  const h = harness();
  h.startDefault(); h.respond(h.lastRequest(), fixtures.list_complete); await h.flush();
  click(h.detailButtons()[0]);
  const d = detailFixture();
  Object.assign(d.record, {returncode: 0, timeout: false, cancel_category: 'task_cancelled', related_log_id: 'rtd-related-0001'});
  d.record.budgets = {cli_timeout_seconds: 21600, http_timeout_seconds: 10, task_lease_seconds: 120,
    task_heartbeat_interval_seconds: 30, managed_heartbeat_interval_seconds: 30, task_poll_interval_seconds: 2, mcp_wait_seconds: null};
  h.respond(h.lastRequest(), d); await h.flush();
  const text = allTexts(h.el('role-log-detail-content')).join('\n');
  assert.match(text, /返回码：0/); assert.match(text, /超时：否/);
  assert.match(text, /task_cancelled/); assert.match(text, /21600/); assert.match(text, /120/);
  assert.match(text, /MCP.*未记录/);
  assert.match(text, /rtd-related-0001/);
  const related = findAll(h.el('role-log-detail-content'), n => n.tagName === 'button' && n.textContent === '查询关联日志')[0];
  assert.ok(related); click(related);
  const url = new URL(h.lastRequest().url, 'http://fixture.invalid');
  assert.equal(url.pathname, '/api/projects/prj_fake_a/roles/agent%3Afake-a/runtime-logs');
  assert.equal(url.searchParams.get('ref'), 'rtd-related-0001');
  assert.equal([...url.searchParams.keys()].join(','), 'ref');
});
