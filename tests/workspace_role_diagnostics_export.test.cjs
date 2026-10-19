// 诊断日志导出候选：真实 role-diagnostics.js + 冻结基线最小改的 workspace.js 的纯 DOM/VM 交互测试。
// 全部 API 均为手动 resolved fake；Blob/URL 为内存假实现；不启动 HTTP/浏览器/CLI，不读真实日志、DB 或凭据。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const diagnosticsSource = fs.readFileSync(require.resolve('../web/role-diagnostics.js'), 'utf8');
const indexSource = fs.readFileSync(require.resolve('../web/index.html'), 'utf8');
const cssSource = fs.readFileSync(require.resolve('../web/role-diagnostics.css'), 'utf8');
const workspaceCssSource = fs.readFileSync(require.resolve('../web/workspace.css'), 'utf8');
const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
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
class FakeBlob {
  constructor(parts, options) {
    this.parts = parts;
    this.options = options;
    this.text = parts.map(part => typeof part === 'string' ? part : new TextDecoder().decode(part)).join('');
    this.size = this.text.length;
  }
}

function harness({ human = true, service = serviceRow(), roster = null } = {}) {
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
  for (const [id, value] of Object.entries({ 'workspace-search': '', 'role-description-input': '', 'requirements-input': '' })) {
    if (elements.has(id)) elements.get(id).value = value;
  }
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
  const urlStub = {
    created: [], revoked: [],
    createObjectURL(blob) { const url = `blob:fake-${this.created.length}`; this.created.push({ url, blob }); return url; },
    revokeObjectURL(url) { this.revoked.push(url); },
  };
  const windowStub = {
    matchMedia: () => ({ matches: false }),
    AbortController,
    TextEncoder,
    TextDecoder,
    Blob: FakeBlob,
    URL: urlStub,
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
  const exportRequests = () => requests.filter(request => request.url.includes('/runtime-logs/export'));
  const lastRequest = () => exportRequests()[exportRequests().length - 1];
  const respondExport = (request, bodyText, { status = 200, contentType = 'application/x-ndjson; charset=utf-8', disposition = 'attachment; filename="talk-diagnostics_20261018T040000Z_20261019T040000Z.jsonl"' } = {}) => {
    request.resolve({
      ok: status >= 200 && status < 300,
      status,
      headers: {
        get: name => {
          const key = String(name).toLowerCase();
          if (key === 'content-type') return contentType;
          if (key === 'content-disposition') return disposition;
          return null;
        },
      },
      body: { getReader() {
        const bytes = new TextEncoder().encode(bodyText);
        let offset = 0;
        return { async read() {
          if (offset >= bytes.length) return { done: true };
          const value = bytes.slice(offset, offset + 65536); offset += value.length;
          return { done: false, value };
        }, async cancel() { offset = bytes.length; }, releaseLock() {} };
      } },
      text: async () => { throw new Error('必须有界读取，不能消费整份 text'); },
      json: async () => JSON.parse(bodyText),
    });
  };
  return {
    context, account, roles, el, pending, requests, exportRequests, lastRequest, respondExport, flush, render, selectRole,
    ui: context.__workspaceUI, diag: context.roleDiagnostics, urlStub, windowListeners,
    statusText: () => el('role-export-status').textContent,
    resultBox: () => el('role-export-result'),
    download: () => el('role-export-download'),
    generate: () => click(el('role-export-generate-btn')),
  };
}

function metaFor(request, overrides = {}, eventCount = 0) {
  const url = new URL(request.url, 'http://fixture.invalid');
  const match = url.pathname.match(/^\/api\/projects\/([^/]+)\/roles\/([^/]+)\/runtime-logs\/export$/);
  return {
    kind: 'meta', schema: 'talk-diagnostics-export-1',
    scope: { project_id: decodeURIComponent(match[1]), member_id: decodeURIComponent(match[2]) },
    query: { since: url.searchParams.get('since'), until: url.searchParams.get('until') },
    generated_at: '2026-10-19T12:00:00Z',
    record_count: eventCount, complete: true, truncated: false, reasons: [],
    scan: { complete: true, truncated: false, scanned_files: 3, scanned_bytes: 128, malformed_lines: 0, unavailable_sources: 0 },
    ...overrides,
  };
}
function exportBody(meta, events = []) {
  return [JSON.stringify(meta), ...events.map(event => JSON.stringify(event))].join('\n') + '\n';
}
function eventRecord(overrides = {}) {
  return {
    kind: 'event', log_id: 'rtd-fake-00001', project_id: 'prj_fake_a', member_id: 'agent:fake-a',
    recorded_at: '2026-10-19T01:00:00Z', severity: 'error', event: 'task_claim_failed', stage: 'task_claim',
    instance_id: 'ins_fake_old17', launch_id: 'launch-fake-old17', task_id: 273,
    exception: { type: 'TaskClaimError', message: '领取失败', message_preview: '领取失败', frames: [{ file_name: 'cli_bridge.py', line: 3214, function: 'handle_queued_task' }] },
    phase: 'task_preflight', transition: { operation_id: 'op-fake1', status: 'failed', from_state: null, to_state: 'task_preflight', started_at: '2026-10-19T00:59:00Z', finished_at: '2026-10-19T01:00:00Z', duration_ms: 60000, attempt: 1 },
    ...overrides,
  };
}
function setRange(h, sinceLocal, untilLocal) {
  h.el('role-export-since').value = sinceLocal;
  h.el('role-export-until').value = untilLocal;
}
function utcOf(localValue) { return new Date(localValue).toISOString(); }

test('复核：相互矛盾的完整性标记拒绝保存，不能显示为完整', async () => {
  for (const overrides of [{ complete: true, reasons: ['scan_incomplete'] }, { complete: true, truncated: true }, { scan: { complete: false, truncated: false, scanned_files: 0, scanned_bytes: 0, malformed_lines: 0, unavailable_sources: 0 } }, { scan: null }]) {
    const h = harness(); h.generate();
    const request = h.lastRequest();
    h.respondExport(request, exportBody(metaFor(request, overrides)));
    await h.flush();
    assert.equal(h.urlStub.created.length, 0);
    assert.equal(h.el('role-export-status').className, 'role-export-status error');
  }
});

test('复核：编辑时间后旧文件立即失效，非法新范围也不能保留旧下载', async () => {
  const h = harness(); h.generate();
  const request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request))); await h.flush();
  h.el('role-export-since').value = '';
  h.el('role-export-since').fire('input');
  assert.equal(h.resultBox().classList.contains('hidden'), true);
  assert.deepEqual(h.urlStub.revoked, ['blob:fake-0']);
  h.generate();
  assert.equal(h.download().getAttribute('href'), '#');
});

test('复核：不完整的零条文件不能宣称范围内没有记录', async () => {
  const h = harness(); h.generate(); const request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { complete: false, reasons: ['projection_failed'] })));
  await h.flush();
  assert.match(h.statusText(), /导出不完整/);
  assert.doesNotMatch(h.statusText(), /范围内没有诊断记录/);
});

test('复核：请求入口不可用也解除生成状态', async () => {
  const h = harness(); h.context.apiFetch = null; h.generate(); await h.flush();
  assert.equal(h.el('role-export-generate-btn').disabled, false);
  assert.equal(h.diag._state.generating, false);
});

test('复核：流式体积超过16MiB即取消读取，不消费剩余响应；meta只解析首行', async () => {
  const h = harness(); h.generate(); const request = h.lastRequest();
  let reads = 0, canceled = false, released = false;
  const first = new TextEncoder().encode(exportBody(metaFor(request, { record_count: 1 })));
  request.resolve({ ok: true, headers: { get: name => name === 'content-type' ? 'application/x-ndjson' : null },
    body: { getReader() { return {
      async read() { reads += 1; return { done: false, value: reads === 1 ? first : new Uint8Array(1024*1024).fill(120) }; },
      async cancel() { canceled = true; }, releaseLock() { released = true; },
    }; } }, text: async () => { throw new Error('不能读取整份文本'); },
  });
  await h.flush();
  assert.match(h.statusText(), /超出有界大小上限/);
  assert.equal(reads, 17);
  assert.equal(canceled, true);
  assert.equal(released, true);
  assert.equal(h.urlStub.created.length, 0);
});

test('静态合同：导出面板新 DOM、旧日志查看 DOM 全部移除，资源版本统一且代码不解析 innerHTML', () => {
  for (const id of ['role-diagnostics-panel', 'role-export-since', 'role-export-until', 'role-export-generate-btn', 'role-export-permission', 'role-export-status', 'role-export-result', 'role-export-summary', 'role-export-download']) {
    assert.ok(indexSource.includes(`id="${id}"`), `missing ${id}`);
  }
  for (const removed of ['role-log-filter-form', 'role-log-records', 'role-log-detail-dialog', 'role-log-ref', 'role-log-view-btn', 'role-log-query-btn', 'role-log-more-btn', 'role-log-severity-error', 'role-evidence-owner', 'role-evidence-heartbeat', 'role-evidence-queue', 'role-evidence-claim', 'role-evidence-preflight', 'role-log-instance', 'role-log-time']) {
    assert.ok(!indexSource.includes(`id="${removed}"`), `旧元素应移除：${removed}`);
  }
  const description = indexSource.indexOf('id="role-description-panel"');
  const diagnostics = indexSource.indexOf('id="role-diagnostics-panel"');
  const tasks = indexSource.indexOf('id="role-details-tasks-panel"');
  assert.ok(description >= 0 && description < diagnostics && diagnostics < tasks);
  assert.ok(indexSource.indexOf('/role-diagnostics.js') < indexSource.indexOf('/workspace.js'));
  const versions = [...indexSource.matchAll(/(?:href|src)="\/[^"?]+\?v=([^"]+)"/g)].map(match => match[1]);
  assert.ok(versions.length >= 7 && versions.every(version => version === '20261019-diagnostics-export-v1'));
  assert.ok(!diagnosticsSource.includes('innerHTML'));
  assert.match(cssSource, /overflow-wrap:\s*anywhere/);
  assert.match(cssSource, /\.role-export-range/);
  assert.match(workspaceCssSource, /\.role-task-pagination/);
  assert.match(indexSource, /诊断日志导出/);
  assert.ok(!indexSource.includes('查看运行日志'));
});

test('human 选角色不自动发请求；默认最近 24 小时预填且可编辑', async () => {
  const h = harness();
  assert.equal(h.exportRequests().length, 0);
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), false);
  const since = Date.parse(h.el('role-export-since').value);
  const until = Date.parse(h.el('role-export-until').value);
  assert.ok(Number.isFinite(since) && Number.isFinite(until));
  assert.equal(until - since, 86400000);
  assert.match(h.statusText(), /尚未生成诊断日志；选择角色不会自动扫描/);
  setRange(h, '2026-10-18T04:00', '2026-10-19T04:00');
  h.render(); h.render();
  assert.equal(h.el('role-export-since').value, '2026-10-18T04:00', '重绘不覆盖已编辑输入');
  assert.equal(h.exportRequests().length, 0);
  await h.flush();
});

test('显式点击才发单次 GET export：仅 since/until、本地输入转 UTC；在途防并发', async () => {
  const h = harness();
  setRange(h, '2026-10-18T04:00', '2026-10-19T04:30');
  h.generate();
  h.generate();
  assert.equal(h.exportRequests().length, 1);
  const request = h.lastRequest();
  assert.equal(request.opts.method, 'GET');
  const url = new URL(request.url, 'http://fixture.invalid');
  assert.equal(url.pathname, '/api/projects/prj_fake_a/roles/agent%3Afake-a/runtime-logs/export');
  assert.equal([...url.searchParams.keys()].sort().join(','), 'since,until');
  assert.equal(url.searchParams.get('since'), utcOf('2026-10-18T04:00'));
  assert.equal(url.searchParams.get('until'), utcOf('2026-10-19T04:30'));
  assert.ok(url.searchParams.get('since').endsWith('Z'));
  assert.equal(h.el('role-export-generate-btn').disabled, true, '在途禁用生成按钮');
  assert.equal(h.el('role-export-since').disabled, true, '在途禁用时间输入');
  assert.match(h.statusText(), /正在生成诊断文件/);
  h.respondExport(request, exportBody(metaFor(request)));
  await h.flush();
  assert.equal(h.el('role-export-generate-btn').disabled, false);
});

test('完整响应：首行 meta 合同校验通过，展示范围/数量/完整与下载链接；生成不自动下载', async () => {
  const h = harness();
  setRange(h, '2026-10-18T04:00', '2026-10-19T04:30');
  h.generate();
  const request = h.lastRequest();
  const events = [eventRecord(), eventRecord({ log_id: 'rtd-fake-00002', severity: 'info', exception: null, task_id: null })];
  h.respondExport(request, exportBody(metaFor(request, {}, events.length), events));
  await h.flush();
  assert.match(h.statusText(), /已生成诊断文件/);
  assert.match(h.statusText(), /共 2 条记录，扫描与导出完整/);
  assert.match(h.statusText(), new RegExp(metaFor(request).query.since.replace(/[.+]/g, m => `\\${m}`)));
  assert.equal(h.el('role-export-status').className, 'role-export-status success');
  assert.equal(h.resultBox().classList.contains('hidden'), false);
  assert.match(h.el('role-export-summary').textContent, /共 2 条记录 · 扫描与导出完整/);
  assert.equal(h.urlStub.created.length, 1);
  assert.equal(h.download().getAttribute('href'), 'blob:fake-0');
  assert.equal(h.download().getAttribute('download'), 'talk-diagnostics_20261018T040000Z_20261019T040000Z.jsonl');
  const event = {};
  h.download().fire('click', event);
  assert.equal(event.defaultPrevented, undefined, '有文件时点击下载不被阻止');
  assert.equal(h.urlStub.revoked.length, 0, '下载不回收 Blob，允许重复下载');
});

test('空结果与不完整导出均诚实呈现；不完整给出原因码且仍可下载', async () => {
  const h = harness();
  h.generate();
  let request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request)));
  await h.flush();
  assert.match(h.statusText(), /共 0 条记录，所选范围内没有诊断记录/);
  assert.equal(h.el('role-export-status').className, 'role-export-status success');
  assert.equal(h.resultBox().classList.contains('hidden'), false, '空结果也提供含 meta 的文件');
  h.generate();
  request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { complete: false, truncated: true, reasons: ['record_limit', 'byte_limit'] }, 1), [eventRecord()]));
  await h.flush();
  assert.match(h.statusText(), /共 1 条记录；导出不完整（record_limit、byte_limit），未将缺失记录当作无异常/);
  assert.equal(h.el('role-export-status').className, 'role-export-status warning');
  assert.match(h.el('role-export-summary').textContent, /导出不完整（record_limit、byte_limit）/);
  assert.equal(h.resultBox().classList.contains('hidden'), false);
});

test('本地校验：空值/坏格式/开始不早于结束/超 31 天均拒绝且不发请求', async () => {
  const h = harness();
  setRange(h, '', '2026-10-19T04:00');
  h.generate();
  assert.match(h.statusText(), /参数错误：开始时间必须是有效的本地日期时间/);
  setRange(h, '不是时间', '2026-10-19T04:00');
  h.generate();
  assert.match(h.statusText(), /参数错误：开始时间必须是有效的本地日期时间/);
  setRange(h, '2026-10-19T04:00', '2026-10-19T04:00');
  h.generate();
  assert.match(h.statusText(), /开始时间必须早于结束时间/);
  setRange(h, '2026-10-19T05:00', '2026-10-19T04:00');
  h.generate();
  assert.match(h.statusText(), /开始时间必须早于结束时间/);
  setRange(h, '2026-09-01T00:00', '2026-10-19T00:00');
  h.generate();
  assert.match(h.statusText(), /导出时间跨度不能超过 31 天/);
  setRange(h, '2026-09-18T00:00', '2026-10-19T00:00');
  h.generate();
  assert.equal(h.exportRequests().length, 1, '恰好 31 天允许');
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest())));
  await h.flush();
});

test('401/403/404/422/503 错误只映射文案：不生成文件、不把错误 JSON 当下载', async () => {
  const h = harness();
  const cases = [
    [401, 'unauthorized', /登录已失效，请重新登录/],
    [403, 'log_read_forbidden', /没有诊断日志导出权限/],
    [404, 'project_not_found', /项目或角色不存在/],
    [422, 'invalid_filter', /导出参数不符合合同：开始\/结束时间必须带时区/],
    [422, 'other_code', /导出参数不符合合同，请检查后重试/],
    [503, 'diagnostics_unavailable', /暂时无法读取该角色的日志来源；这不表示角色已停止或没有异常/],
    [503, 'diagnostics_projection_failed', /无法安全投影，未生成文件/],
    [503, 'other_outage', /日志来源暂时不可用；这不表示角色已停止或没有异常/],
    [500, 'boom', /诊断日志导出失败（HTTP 500）/],
  ];
  for (const [status, detail, expected] of cases) {
    h.generate();
    assert.equal(h.el('role-export-generate-btn').disabled, true);
    h.respondExport(h.lastRequest(), JSON.stringify({ detail }), { status, contentType: 'application/json' });
    await h.flush();
    assert.match(h.statusText(), expected, `status=${status} detail=${detail}`);
    assert.equal(h.el('role-export-status').className, 'role-export-status error');
    assert.equal(h.resultBox().classList.contains('hidden'), true);
  }
  assert.equal(h.urlStub.created.length, 0, '任何错误都不创建 Blob');
  assert.equal(h.exportRequests().length, cases.length);
});

test('响应合同防线：错类型/错 schema/错 scope/错区间/缺生成时间/数量不符/未知原因码分别拒绝', async () => {
  const h = harness();
  const attempts = [];
  const reject = async (body, options, expected) => {
    h.generate();
    const request = h.lastRequest();
    h.respondExport(request, body, options);
    await h.flush();
    assert.match(h.statusText(), expected);
    assert.equal(h.resultBox().classList.contains('hidden'), true);
    attempts.push(request);
  };
  let request;
  h.generate(); request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request)), { contentType: 'application/json' });
  await h.flush();
  assert.match(h.statusText(), /类型不是 application\/x-ndjson/);
  h.generate(); request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { schema: 'talk-other-9' })));
  await h.flush();
  assert.match(h.statusText(), /首行不是合同要求的 meta 记录/);
  h.generate(); request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { scope: { project_id: 'prj_fake_a', member_id: 'agent:fake-b' } })));
  await h.flush();
  assert.match(h.statusText(), /项目、角色与当前上下文不一致/);
  h.generate(); request = h.lastRequest();
  const wrongRange = metaFor(request);
  wrongRange.query = { since: '2020-01-01T00:00:00Z', until: '2020-01-02T00:00:00Z' };
  h.respondExport(request, exportBody(wrongRange));
  await h.flush();
  assert.match(h.statusText(), /查询区间与本次请求不一致/);
  h.generate(); request = h.lastRequest();
  const noTime = metaFor(request); delete noTime.generated_at;
  h.respondExport(request, exportBody(noTime));
  await h.flush();
  assert.match(h.statusText(), /缺少有效的生成时间/);
  h.generate(); request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { record_count: 2 }), [eventRecord()]));
  await h.flush();
  assert.match(h.statusText(), /实际事件行数与 meta 记录数不一致/);
  h.generate(); request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request, { complete: false, reasons: ['<img src=x onerror=alert(1)>'] })));
  await h.flush();
  assert.match(h.statusText(), /无法识别的不完整原因/);
  h.generate(); request = h.lastRequest();
  h.respondExport(request, 'not-json-at-all\n');
  await h.flush();
  assert.match(h.statusText(), /首行不是可解析的 meta JSON/);
  assert.equal(h.urlStub.created.length, 0, '九类坏响应都不创建 Blob');
});

test('有界防线：首行 meta 超 64KiB 或总长超限都拒绝保存', async () => {
  const h = harness();
  h.generate();
  let request = h.lastRequest();
  const fatMeta = metaFor(request, { record_count: 0 });
  fatMeta.scan.padding = 'x'.repeat(70 * 1024);
  h.respondExport(request, exportBody(fatMeta));
  await h.flush();
  assert.match(h.statusText(), /首行 meta 超过有界上限/);
  h.generate();
  request = h.lastRequest();
  const huge = `${JSON.stringify(metaFor(request, { record_count: 0 }))}\n${'y'.repeat(16 * 1024 * 1024 + 70 * 1024)}`;
  h.respondExport(request, huge);
  await h.flush();
  assert.match(h.statusText(), /超出有界大小上限/);
  assert.equal(h.urlStub.created.length, 0);
});

test('文件名只接受安全服务端名；路径穿越/伪装名回退为本地固定日期名', async () => {
  const h = harness();
  setRange(h, '2026-10-18T04:00', '2026-10-19T04:30');
  h.generate();
  let request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request)), { disposition: 'attachment; filename="../../etc/passwd"' });
  await h.flush();
  const compact = value => {
    const date = new Date(value);
    const pad = n => String(n).padStart(2, '0');
    return `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`;
  };
  const meta = metaFor(request);
  const expected = `talk-diagnostics_${compact(meta.query.since)}_${compact(meta.query.until)}.jsonl`;
  assert.equal(h.download().getAttribute('download'), expected);
  h.generate();
  request = h.lastRequest();
  h.respondExport(request, exportBody(metaFor(request)), { disposition: null });
  await h.flush();
  assert.equal(h.download().getAttribute('download'), expected);
});

test('重新生成清旧 Blob 并 revoke；两次生成各自独立可下载', async () => {
  const h = harness();
  h.generate();
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.download().getAttribute('href'), 'blob:fake-0');
  h.generate();
  assert.deepEqual(h.urlStub.revoked, ['blob:fake-0'], '重生成先回收旧文件');
  assert.equal(h.resultBox().classList.contains('hidden'), true, '在途期间结果区隐藏');
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, 2), [eventRecord(), eventRecord({ log_id: 'rtd-fake-00002' })]));
  await h.flush();
  assert.equal(h.download().getAttribute('href'), 'blob:fake-1');
  assert.match(h.statusText(), /共 2 条记录/);
  assert.equal(h.urlStub.created.length, 2);
  assert.equal(h.urlStub.revoked.length, 1);
});

test('切角色使在途旧响应作废；乱序到达不回填旧角色文件', async () => {
  const h = harness();
  h.generate();
  const oldA = h.lastRequest();
  h.selectRole('agent:fake-b');
  assert.equal(h.resultBox().classList.contains('hidden'), true);
  assert.match(h.statusText(), /尚未生成诊断日志/);
  h.generate();
  const newB = h.lastRequest();
  assert.ok(newB.url.includes('agent%3Afake-b'));
  const metaB = metaFor(newB, { scope: { project_id: 'prj_fake_a', member_id: 'agent:fake-b' } }, 1);
  h.respondExport(newB, exportBody(metaB, [eventRecord({ member_id: 'agent:fake-b' })]));
  await h.flush();
  assert.equal(h.download().getAttribute('href'), 'blob:fake-0');
  h.respondExport(oldA, exportBody(metaFor(oldA, {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.urlStub.created.length, 1, '旧角色迟到响应不再生成文件');
  assert.equal(h.diag._state.role.member_id, 'agent:fake-b');
});

test('切项目/切账号清空结果并拒绝旧响应；时间输入恢复默认 24 小时', async () => {
  const h = harness();
  h.generate();
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.resultBox().classList.contains('hidden'), false);
  h.generate();
  const oldProject = h.lastRequest();
  h.context.activeProjectId = 'prj_fake_b';
  h.render();
  assert.deepEqual(h.urlStub.revoked, ['blob:fake-0']);
  assert.equal(h.resultBox().classList.contains('hidden'), true);
  const since = Date.parse(h.el('role-export-since').value);
  assert.equal(Date.parse(h.el('role-export-until').value) - since, 86400000, '切项目恢复默认最近 24 小时');
  h.respondExport(oldProject, exportBody(metaFor(oldProject, {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.urlStub.created.length, 1);
  h.generate();
  const newProject = h.lastRequest();
  assert.ok(newProject.url.includes('/api/projects/prj_fake_b/'));
  h.respondExport(newProject, exportBody(metaFor(newProject, {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.resultBox().classList.contains('hidden'), false);
  h.context.myId = 'human:other';
  h.render();
  assert.ok(h.urlStub.revoked.includes('blob:fake-1'), '切账号回收文件');
  assert.equal(h.resultBox().classList.contains('hidden'), true);
  assert.equal(h.diag._state.accountId, 'human:other');
});

test('离开角色页与 pagehide 都清空结果、回收 Blob 并作废在途；返回后重新生成', async () => {
  const h = harness();
  h.generate();
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, 1), [eventRecord()]));
  await h.flush();
  h.generate();
  const inFlight = h.lastRequest();
  h.ui.mode = 'tasks';
  h.render();
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), true);
  assert.ok(h.urlStub.revoked.includes('blob:fake-0'));
  h.respondExport(inFlight, exportBody(metaFor(inFlight, {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.urlStub.created.length, 1, '离页后迟到响应不回填');
  h.ui.mode = 'roles';
  h.render();
  assert.equal(h.resultBox().classList.contains('hidden'), true);
  for (const fn of h.windowListeners.pagehide || []) fn();
  assert.equal(h.diag._state.visible, false);
  h.ui.mode = 'tasks';
  h.render();
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), true);
});

test('退出登录在导航前回收 Blob 并拒绝在途旧响应（复用 app.js 实际退出回调）', async () => {
  const h = harness();
  h.generate();
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, 1), [eventRecord()]));
  await h.flush();
  h.generate();
  const late = h.lastRequest();
  const match = appSource.match(/logoutBtn.addEventListener\("click", \(\) => \{([\s\S]*?)\n\}\);/);
  assert.ok(match, '使用实际退出回调');
  let reloaded = false;
  Object.assign(h.context, {
    pollTimer: null, taskPollTimer: null, taskDurationTimer: null, reconnectTimer: null, ws: null,
    closeEventStream() {}, clearStoredApiKeys() {},
    location: { reload() {
      reloaded = true;
      assert.ok(h.urlStub.revoked.includes('blob:fake-0'), 'reload 调用前必须回收 Blob');
      assert.equal(h.diag._state.visible, false);
    } },
  });
  vm.runInContext(match[1], h.context);
  assert.equal(reloaded, true);
  h.respondExport(late, exportBody(metaFor(late, {}, 1), [eventRecord()]));
  await h.flush();
  assert.equal(h.urlStub.created.length, 1, '退出后迟到响应不生成新文件');
});

test('当前实例/launch 变化不清已生成文件、不触发新生成；下载内容含事件原文但不进 DOM', async () => {
  const h = harness({ service: runningService() });
  h.generate();
  const xss = '<img src=x onerror=alert(1)>' + '长文'.repeat(200);
  const events = [eventRecord({ exception: { type: 'TaskClaimError', message: xss, message_preview: xss, frames: [] } })];
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest(), {}, events.length), events));
  await h.flush();
  assert.equal(h.urlStub.created[0].blob.text.includes(xss), true, '事件原文只进入下载文件');
  assert.equal(findAll(h.el('role-diagnostics-panel'), n => ['img', 'script'].includes(n.tagName)).length, 0);
  assert.doesNotMatch(allTexts(h.el('role-diagnostics-panel')).join(' '), /onerror/, '页面不展示日志/异常原文');
  const before = h.exportRequests().length;
  h.context.projectAgents = [
    { member_id: 'agent:fake-a', business_role: 'dev', role_description: null, service: runningService({ observed_instance_id: 'ins_fake_new01', current_launch: { launch_id: 'launch-fake-new01', action: 'start', state: 'reported', expected_instance_id: 'ins_fake_new01' } }) },
    { member_id: 'agent:fake-b', business_role: 'reviewer', role_description: '另一角色', service: serviceRow() },
  ];
  h.render();
  h.render();
  assert.equal(h.exportRequests().length, before, '实例变化不自动重新生成');
  assert.equal(h.resultBox().classList.contains('hidden'), false, '跨实例导出结果保留');
  assert.equal(h.download().getAttribute('href'), 'blob:fake-0');
  assert.equal(h.urlStub.revoked.length, 0);
});

test('Agent 账号：控件禁用、任何入口都不发导出请求', async () => {
  const h = harness({ human: false, service: runningService() });
  assert.equal(h.el('role-diagnostics-panel').classList.contains('hidden'), false);
  assert.equal(h.el('role-export-generate-btn').disabled, true);
  assert.equal(h.el('role-export-since').disabled, true);
  assert.match(h.el('role-export-permission').textContent, /没有诊断日志导出权限/);
  assert.match(h.statusText(), /没有诊断日志导出权限/);
  h.generate();
  assert.equal(h.diag.startExport(), false);
  await h.flush();
  assert.equal(h.exportRequests().length, 0);
  assert.equal(h.urlStub.created.length, 0);
});

test('无 Blob/URL 环境的旧浏览器如实降级，不假装已生成', async () => {
  const h = harness();
  h.context.window.Blob = undefined;
  h.context.window.URL = undefined;
  h.generate();
  h.respondExport(h.lastRequest(), exportBody(metaFor(h.lastRequest())));
  await h.flush();
  assert.match(h.statusText(), /当前环境不支持生成下载文件/);
  assert.equal(h.resultBox().classList.contains('hidden'), true);
});
