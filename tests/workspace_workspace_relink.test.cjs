const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function harness(human = true) {
  let active = null;
  function el(tag) {
    const classes = new Set();
    const node = { tagName: tag, children: [], listeners: {}, attrs: {}, textContent: '', value: '', disabled: false,
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
  const open = () => { find(panel, '重新关联已有目录').fire('click'); return body.children[0].children[0]; };
  return { ctx, document, panel, requests, reply, flush, find, text, open, events };
}
async function ready(h) {
  h.ctx.renderWorkspaceDiagnosticsPanel();
  h.reply(0, { root_status: 'missing', issues: [{ code: 'workspace_root_missing' }], duplicate_projects: ['q'], binding: 'not_checked' });
  await h.flush();
}
function dialogParts(h) {
  const modal = h.open();
  return { modal, input: modal.children[2].children[0], status: modal.children[3], check: modal.children[4], confirm: modal.children[5], cancel: modal.children[6] };
}
const success = { candidate_root: 'C:\\normalized', preview_token: 'tok', expected_revision: 3, candidate_status: 'ok', code: 'workspace_identity_unverified', blocked_reasons: [] };
test('真人诊断与重复警告；Agent 不可见且不请求', async () => {
  const h = harness(); await ready(h); assert.match(h.text(h.panel), /目录状态：不存在/); assert.match(h.text(h.panel), /警告/); assert.doesNotMatch(h.text(h.panel), /not_checked|错误/);
  const a = harness(false); a.ctx.renderWorkspaceDiagnosticsPanel(); assert.equal(a.requests.length, 0); assert.ok(a.panel.classList.contains('hidden'));
});
test('无效路径不请求；盘符和 UNC 路径通过校验', async () => {
  const h = harness(); await ready(h); const d = dialogParts(h);
  for (const path of ['relative', 'C:relative', 'C:\\bad\0x', 'C:\\' + 'a'.repeat(32768), '\\\\server']) { d.input.value = path; d.check.fire('click'); assert.match(d.status.textContent, /绝对目录路径/); }
  assert.equal(h.requests.length, 1); assert.equal(h.ctx.workspaceRelinkPathValid('C:\\valid'), true); assert.equal(h.ctx.workspaceRelinkPathValid('\\\\server\\share'), true);
});
test('预览展示服务端根并按其提交；提交防重复并刷新诊断', async () => {
  const h = harness(); await ready(h); const d = dialogParts(h); d.input.value = 'C:\\input'; d.check.fire('click'); h.reply(1, success); await h.flush();
  assert.match(d.status.textContent, /C:\\normalized/); assert.equal(d.confirm.disabled, false);
  d.confirm.fire('click'); d.confirm.fire('click'); assert.equal(h.requests.length, 3);
  assert.deepEqual(JSON.parse(h.requests[2].opts.body), { candidate_root: 'C:\\normalized', preview_token: 'tok', expected_revision: 3, operation_id: 'op-123', confirm: true });
  h.reply(2, { stage: 'completed' }); await h.flush(); assert.match(d.status.textContent, /成功/); assert.match(h.requests[3].url, /workspace-diagnostics$/);
});
test('预览及提交 409 禁用确认并显示中文，重检后方可继续', async () => {
  const h = harness(); await ready(h); const d = dialogParts(h); d.input.value = 'C:\\input'; d.check.fire('click');
  h.reply(1, { blocked_reasons: [{ code: 'workspace_duplicate' }] }, 409); await h.flush(); assert.equal(d.confirm.disabled, true); assert.match(d.status.textContent, /重复/);
  d.check.fire('click'); h.reply(2, success); await h.flush(); d.confirm.fire('click'); h.reply(3, { detail: 'workspace_preview_stale' }, 409); await h.flush(); assert.equal(d.confirm.disabled, true); assert.match(d.status.textContent, /重新检查/);
});
test('取消、Esc 和遮罩关闭均不提交；无私密字段回显', async () => {
  const h = harness(); await ready(h); let d = dialogParts(h); d.input.value = 'C:\\input'; d.check.fire('click');
  h.reply(1, { ...success, private: 'SECRET', config_file: 'C:\\private' }); await h.flush(); assert.doesNotMatch(h.text(d.modal), /SECRET|private|tok/); d.cancel.fire('click'); assert.equal(h.requests.length, 2);
  d = dialogParts(h); h.events.keydown[0]({ key: 'Escape', preventDefault() {} }); assert.equal(h.document.body.children.length, 0);
  d = dialogParts(h); const overlay = h.document.body.children[0]; overlay.fire('click', { target: overlay }); assert.equal(h.document.body.children.length, 0); assert.equal(h.requests.length, 2);
});
test('诊断失败不阻塞入口，切换项目使旧请求失效', async () => {
  const h = harness(); h.ctx.renderWorkspaceDiagnosticsPanel(); h.reply(0, {}, 500); await h.flush(); assert.match(h.text(h.panel), /读取失败/); assert.ok(h.find(h.panel, '重新关联已有目录'));
  h.ctx.activeProjectId = 'q'; h.ctx.renderWorkspaceDiagnosticsPanel(); h.reply(1, { root_status: 'ok' }); await h.flush(); assert.match(h.text(h.panel), /正常/);
});
test('焦点循环与恢复，编辑路径后旧预览失效', async () => {
  const h = harness(); await ready(h); const opener = h.find(h.panel, '重新关联已有目录'); opener.focus();
  const d = dialogParts(h); assert.equal(h.document.activeElement, d.input);
  const close = d.modal.children[0].children[1]; close.focus(); let prevented = false;
  h.events.keydown[0]({ key: 'Tab', shiftKey: true, preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(h.document.activeElement, d.cancel);
  d.input.value = 'C:\\input'; d.check.fire('click'); h.reply(1, success); await h.flush(); assert.equal(d.confirm.disabled, false);
  d.input.value = 'C:\\other'; d.input.fire('input'); assert.equal(d.confirm.disabled, true); d.confirm.fire('click'); assert.equal(h.requests.length, 2);
  d.cancel.fire('click'); assert.equal(h.document.activeElement, opener);
});
