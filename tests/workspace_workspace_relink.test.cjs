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
  return { modal, selected: modal.children[1], error: modal.children[2], browse: modal.children[3].children[0], confirm: modal.children[3].children[1], cancel: modal.children[3].children[2] };
}
async function choose(h, d, path = 'C:\\picked') {
  d.browse.fire('click'); const i = h.requests.length - 1; h.reply(i, { path }); await h.flush();
}
const success = { candidate_root: 'C:\\normalized', preview_token: 'tok', expected_revision: 3, blocked_reasons: [] };
test('真人面板样式与入口；Agent 不显示', async () => {
  const h = harness(); await ready(h); assert.ok(h.find(h.panel, '重新选择该项目的目录'));
  assert.equal(h.panel.children[0].tagName, 'div'); assert.match(h.panel.attrs.style, /border-bottom/);
  assert.ok(h.panel.children.at(-1).classList.contains('requirements-toolbar'));
  const a = harness(false); a.ctx.renderWorkspaceDiagnosticsPanel(); assert.equal(a.requests.length, 0); assert.ok(a.panel.classList.contains('hidden'));
});
test('对话框只有说明、已选、错误和三个按钮，焦点循环及恢复', async () => {
  const h = harness(); await ready(h); const opener = h.find(h.panel, '重新选择该项目的目录'); opener.focus();
  const d = parts(h); assert.deepEqual(d.modal.children.map(n => n.tagName), ['h3', 'p', 'p', 'div']);
  assert.deepEqual(d.modal.children[3].children.map(n => n.textContent), ['浏览', '确认', '取消']);
  assert.equal(d.selected.textContent, '尚未选择'); assert.ok(d.error.classList.contains('hidden')); assert.equal(d.confirm.disabled, true);
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
  d.confirm.fire('click'); d.confirm.fire('click'); assert.equal(h.requests.length, 3); assert.match(h.requests[2].url, /workspace-relink-preview$/);
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
