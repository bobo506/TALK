const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function harness(human = true) {
  let active = null;
  function el(tag) {
    const classes = new Set();
    const node = { tagName: tag, set className(value) { classes.clear(); value.split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); }, children: [], listeners: {}, attrs: {}, textContent: '', value: '', disabled: false,
      classList: { toggle(c, b) { b ? classes.add(c) : classes.delete(c); }, add(c) { classes.add(c); }, remove(c) { classes.delete(c); }, contains(c) { return classes.has(c); } },
      appendChild(c) { node.children.push(c); c.parent = node; return c; }, append(...cs) { cs.forEach(c => node.appendChild(c)); },
      replaceChildren(...cs) { node.children = []; node.append(...cs); }, setAttribute(k, v) { node.attrs[k] = v; },
      addEventListener(k, fn) { (node.listeners[k] ||= []).push(fn); },
      fire(k, e = {}) { for (const fn of node.listeners[k] || []) fn(e); },
      focus() { active = node; }, remove() { if (node.parent) node.parent.children = node.parent.children.filter(c => c !== node); },
    }; return node;
  }
  const nodes = new Map(), body = el('body'), events = {};
  const document = { body, createElement: el, get activeElement() { return active; },
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, el('div')); return nodes.get(id); },
    addEventListener(k, fn) { (events[k] ||= []).push(fn); }, removeEventListener(k, fn) { events[k] = (events[k] || []).filter(f => f !== fn); },
  };
  const requests = [];
  const ctx = vm.createContext({ document, blackboardOpen: true, activeProjectId: 'p', myId: 'h', projectAgents: [],
    currentMemberIsHuman: () => human, crypto: { randomUUID: () => 'op-123' },
    apiFetch: (url, opts) => new Promise(resolve => requests.push({ url, opts, resolve })) });
  vm.runInContext(source, ctx);
  vm.runInContext('workspaceUI.mode = "roles"; workspaceUI.roleSelection = "settings";', ctx);
  const panel = document.getElementById('workspace-diagnostics-panel');
  panel.tagName = 'SECTION';
  const reply = (i, data, status = 200) => requests[i].resolve({ ok: status === 200, status, json: async () => data });
  const flush = async () => { await new Promise(resolve => setImmediate(resolve)); };
  const find = (node, text) => node.textContent === text ? node : node.children.map(c => find(c, text)).find(Boolean);
  const text = node => [node.textContent, ...node.children.map(text)].join(' ');
  const open = () => { find(panel, '重新选择该项目的目录').fire('click'); return body.children[0].children[0]; };
  return { ctx, document, panel, requests, reply, flush, find, text, open, events };
}
async function ready(h) {
  h.ctx.renderWorkspaceDiagnosticsPanel();
  h.reply(0, { root_status: 'missing', issues: [{ code: 'workspace_root_missing' }], duplicate_projects: ['q'] });
  await h.flush();
}
function parts(h) {
  const modal = h.open();
  return { modal, selected: modal.children[2].children[1], error: modal.children[3], browse: modal.children[4].children[0], confirm: modal.children[4].children[1], cancel: modal.children[4].children[2] };
}
async function choose(h, d, path = 'C:\\picked') {
  d.browse.fire('click'); const i = h.requests.length - 1; h.reply(i, { path }); await h.flush();
}
const success = { candidate_root: 'C:\\normalized', preview_token: 'tok', expected_revision: 3, blocked_reasons: [] };
test('真人面板样式与入口；Agent 不显示', async () => {
  const h = harness(); await ready(h); assert.ok(h.find(h.panel, '重新选择该项目的目录'));
  const heading = h.panel.children[0].children[0];
  assert.equal(heading.children[0].tagName, 'p'); assert.ok(heading.children[0].classList.contains('sidebar-kicker')); assert.equal(heading.children[0].textContent, '项目级 · 本机目录');
  assert.equal(heading.children[1].tagName, 'h3'); assert.equal(heading.children[1].textContent, '工作区');
  const group = h.panel.children[1]; assert.ok(group.classList.contains('workspace-diagnostics-group'));
  assert.equal(group.children[0].textContent, '目录状态：不存在'); assert.ok(group.children[0].classList.contains('workspace-diagnostics-status'));
  assert.ok(group.children.at(-1).classList.contains('requirements-toolbar')); assert.ok(h.find(group, '重新选择该项目的目录').classList.contains('room-secondary-btn'));
  const a = harness(false); a.ctx.renderWorkspaceDiagnosticsPanel(); assert.equal(a.requests.length, 0); assert.ok(a.panel.classList.contains('hidden'));
});
test('对话框只有说明、已选、错误和三个按钮，焦点循环及恢复', async () => {
  const h = harness(); await ready(h); const opener = h.find(h.panel, '重新选择该项目的目录'); opener.focus();
  const d = parts(h); assert.ok(h.document.body.children[0].classList.contains('modal-overlay')); assert.ok(d.modal.classList.contains('modal-card')); assert.ok(d.modal.classList.contains('workspace-relink-card'));
  assert.deepEqual(d.modal.children.map(n => n.tagName), ['div', 'p', 'div', 'p', 'div']);
  assert.ok(d.modal.children[0].classList.contains('modal-header')); assert.equal(d.modal.children[0].children[0].tagName, 'h3'); assert.equal(d.modal.children[0].children[0].textContent, '重新选择该项目的目录');
  assert.equal(d.modal.children[1].textContent, '选择该项目被移动或改名后的目录；不会移动文件、不会合并历史。');
  assert.ok(d.modal.children[2].classList.contains('workspace-relink-field')); assert.equal(d.modal.children[2].children[0].textContent, '已选目录');
  assert.ok(d.modal.children[4].classList.contains('group-create-footer')); assert.deepEqual(d.modal.children[4].children.map(n => n.textContent), ['浏览', '确认', '取消']);
  assert.ok(d.browse.classList.contains('room-secondary-btn')); assert.ok(d.confirm.classList.contains('room-primary-btn')); assert.ok(d.cancel.classList.contains('room-secondary-btn'));
  assert.equal(d.selected.textContent, '尚未选择'); assert.ok(d.error.classList.contains('workspace-relink-error')); assert.equal(d.error.attrs.role, 'alert'); assert.ok(d.error.classList.contains('hidden')); assert.equal(d.confirm.disabled, true);
  const descendants = node => [node, ...node.children.flatMap(descendants)];
  assert.equal(descendants(d.modal).filter(n => n.tagName === 'button').length, 3); assert.ok(!descendants(d.modal).some(n => ['input', 'textarea'].includes(n.tagName)));
  assert.doesNotMatch(h.text(d.modal), /检查目录|预览/); assert.equal(h.document.activeElement, d.browse);
  let prevented = false; h.events.keydown[0]({ key: 'Tab', shiftKey: true, preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(h.document.activeElement, d.cancel);
  d.cancel.fire('click'); assert.equal(h.document.activeElement, opener); assert.equal(h.requests.length, 1);
});
test('浏览成功回填、取消不改且传上次选择，picker 错误只显示中文', async () => {
  const h = harness(); await ready(h); const d = parts(h); await choose(h, d);
  assert.equal(d.selected.textContent, 'C:\\picked'); assert.equal(d.selected.attrs.title, 'C:\\picked'); assert.equal(d.confirm.disabled, false);
  d.browse.fire('click'); assert.deepEqual(JSON.parse(h.requests[2].opts.body), { initial_dir: 'C:\\picked' }); h.reply(2, { path: null }); await h.flush(); assert.equal(d.selected.textContent, 'C:\\picked');
  d.browse.fire('click'); h.reply(3, { detail: 'workspace_picker_busy', secret: 'SECRET' }, 409); await h.flush();
  assert.match(d.error.textContent, /窗口打开/); assert.ok(!d.error.classList.contains('hidden')); assert.doesNotMatch(h.text(d.modal), /SECRET/);
});
test('确认先 preview 后 relink，使用服务端返回值并防重复，成功关闭刷新', async () => {
  const h = harness(); await ready(h); const d = parts(h); await choose(h, d);
  d.confirm.fire('click'); assert.equal(d.browse.disabled, true); assert.equal(d.confirm.disabled, true); assert.equal(d.cancel.disabled, true); d.confirm.fire('click'); assert.equal(h.requests.length, 3); assert.match(h.requests[2].url, /workspace-relink-preview$/);
  assert.deepEqual(JSON.parse(h.requests[2].opts.body), { candidate_root: 'C:\\picked' });
  h.reply(2, { ...success, private: 'SECRET' }); await h.flush(); assert.match(h.requests[3].url, /workspace-relink$/);
  assert.deepEqual(JSON.parse(h.requests[3].opts.body), { candidate_root: 'C:\\normalized', preview_token: 'tok', expected_revision: 3, operation_id: 'op-123', confirm: true });
  assert.doesNotMatch(h.text(d.modal), /SECRET|tok|normalized/); d.confirm.fire('click'); assert.equal(h.requests.length, 4);
  h.reply(3, { stage: 'completed' }); await h.flush(); assert.equal(h.document.body.children.length, 0); assert.match(h.requests[4].url, /workspace-diagnostics$/);
});
test('阻断和确认失败显示错误且保持窗口', async () => {
  const h = harness(); await ready(h); const d = parts(h); await choose(h, d);
  d.confirm.fire('click'); h.reply(2, { blocked_reasons: [{ code: 'workspace_duplicate' }] }); await h.flush(); assert.match(d.error.textContent, /重复/); assert.equal(h.requests.length, 3);
  d.confirm.fire('click'); h.reply(3, success); await h.flush(); h.reply(4, { detail: 'workspace_preview_stale', private: 'SECRET' }, 409); await h.flush();
  assert.match(d.error.textContent, /过期/); assert.equal(h.document.body.children.length, 1); assert.doesNotMatch(h.text(d.modal), /SECRET/);
});
test('取消、Esc、遮罩关闭不提交', async () => {
  const h = harness(); await ready(h); let d = parts(h); await choose(h, d); d.cancel.fire('click');
  d = parts(h); h.events.keydown[0]({ key: 'Escape', preventDefault() {} }); assert.equal(h.document.body.children.length, 0);
  d = parts(h); const overlay = h.document.body.children[0]; overlay.fire('click', { target: overlay }); assert.equal(h.document.body.children.length, 0); assert.equal(h.requests.length, 2);
});
test('picker 各稳定错误码和预览失败均显示一行中文', async () => {
  const h = harness(); await ready(h); const d = parts(h);
  for (const [code, message] of [['workspace_picker_timeout', '超时'], ['workspace_picker_unavailable', '不可用'], ['workspace_picker_failed', '失败'], ['workspace_picker_input_invalid', '参数无效']]) {
    d.browse.fire('click'); h.reply(h.requests.length - 1, { detail: code, private: 'SECRET' }, 503); await h.flush();
    assert.ok(d.error.textContent.includes(message)); assert.doesNotMatch(h.text(d.modal), /SECRET/);
  }
  await choose(h, d); d.confirm.fire('click'); h.reply(h.requests.length - 1, { detail: 'workspace_busy' }, 409); await h.flush();
  assert.match(d.error.textContent, /正在进行/); assert.doesNotMatch(h.requests.at(-1).url, /workspace-relink$/);
});
