const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
function slice(a, b) {
  const start = source.indexOf(a), end = source.indexOf(b, start);
  assert.ok(start >= 0 && end > start);
  return source.slice(start, end);
}
function harness() {
  const elements = new Map();
  function element(tag) {
    const classes = new Set();
    const node = { tag, children: [], style: {}, dataset: {}, disabled: false, setAttribute(name, value) { this[name] = value; }, querySelectorAll: () => [],
      classList: { add: x => classes.add(x), remove: x => classes.delete(x), toggle: (x, on) => on ? classes.add(x) : classes.delete(x), contains: x => classes.has(x) },
      append(...items) { for (const item of items) this.appendChild(item); },
      appendChild(item) { if (item.fragment) { for (const child of [...item.children]) this.appendChild(child); return item; } item.parent = this; this.children.push(item); return item; },
      prepend(item) { if (item.fragment) { for (const child of [...item.children].reverse()) this.prepend(child); return; } item.parent = this; this.children.unshift(item); },
      after(item) { const parent = this.parent; let i = parent.children.indexOf(this) + 1; for (const child of item.fragment ? item.children : [item]) { child.parent = parent; parent.children.splice(i++, 0, child); } },
      remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; },
      replaceWith(item) { const p = this.parent; p.children.splice(p.children.indexOf(this), 1, item); item.parent = p; },
    };
    Object.defineProperty(node, 'innerHTML', { set() { this.children = []; } });
    return node;
  }
  const el = id => { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
  const document = { createElement: element, createDocumentFragment: () => ({ ...element('fragment'), fragment: true }),
    getElementById(id) { const find = n => n.id === id ? n : n.children.map(find).find(Boolean); return [...elements.values()].map(find).find(Boolean) || null; } };
  const ctx = vm.createContext({ document, messagesEl: el('messages'), msgInput: el('input'), attachBtn: el('attach'), sendBtn: el('send'), mentionDropdown: el('mentions'),
    workspaceUI: { mode: 'tasks' }, blackboardOpen: false, activeGroupId: 't', selectedTaskId: null,
    groups: [{ id: 't', type: 'task', members: [{member_id:'人'}, {member_id:'执行者'}] }, { id: 'g', type: 'group' }], projectTasks: [{ id: 1, hall_group_id: 't', title: '<标题>', content: '第一行\n第二行', workflow_status: 'submitted', created_by: '人', target_member_id: '执行者', created_at: '2026-11-04' }],
    sending: false, pendingFile: null, activeReplyTo: null, renderedMessageIds: new Set(), messageRecords: new Map(), appliedHistoryQuery: '', emptySearchText: '', emptyTimelineText: '',
    getActiveGroup() { return ctx.groups.find(g => g.id === ctx.activeGroupId); }, workspaceHasConversation: () => true, activeGroupReadOnly: () => ctx.observer || false,
    workspaceMemberName: id => id || '—', formatTaskTime: x => x, showComposerStatus() {}, clearComposerStatus() {}, updateComposerPlaceholder() {}, clearPendingFile() {}, clearReplyTarget() {},
    createMessageElement: message => { const n = element('message'); n.id = 'msg-' + message.id; return n; },
  });
  vm.runInContext([
    slice('function taskHallComposerReadOnly()', 'function syncComposerReadOnly()'),
    slice('function syncComposerReadOnly()', 'function taskBoardColumn('),
    slice('function getContextTask()', 'function taskContextKey()'),
    slice('function upsertMessages(', 'async function renderMessagesInChunks('),
    slice('function updateMessagesEmptyState()', 'function renderFileCard('),
  ].join('\n'), ctx);
  return { ctx, el };
}
test('任务交办内容置顶、保留原文且不计入消息；历史向前加载仍置顶', () => {
  const { ctx, el } = harness();
  ctx.renderTaskHallBrief();
  let brief = el('messages').children[0];
  assert.equal(brief.id, 'task-hall-brief');
  assert.doesNotMatch(brief.style.cssText, /position\s*:\s*(sticky|fixed|absolute)/i);
  const header = brief.children[0], details = brief.children[1], toggle = header.children[3];
  assert.equal(header.children[0].textContent, '任务交办内容');
  assert.equal(header.children[1].textContent, '<标题>');
  assert.equal(toggle.textContent, '展开');
  assert.equal(details.hidden, true);
  toggle.onclick();
  assert.equal(details.hidden, false);
  assert.equal(toggle.textContent, '收起');
  assert.match(details.textContent, /第一行\n第二行/);
  assert.match(details.textContent, /发起者：人\n执行者：执行者\n创建时间：2026-11-04/);
  assert.equal(details.children[0].textContent, '参与者：人、执行者');
  assert.equal(details.children[0].children.length, 0, '参与者只读展示');
  assert.match(details.style.cssText, /max-height\s*:\s*60vh/i);
  assert.match(details.style.cssText, /overflow\s*:\s*auto/i);
  assert.doesNotMatch(details.style.cssText, /position\s*:\s*(sticky|fixed|absolute)/i);
  ctx.renderTaskHallBrief();
  brief = el('messages').children[0];
  assert.equal(brief.children[1].hidden, false);
  assert.equal(brief.children[0].children[3].textContent, '收起');
  brief.children[0].children[3].onclick();
  assert.equal(brief.children[1].hidden, true);
  assert.equal(ctx.messageRecords.size, 0);
  ctx.appendMessages([{ id: 2 }]); ctx.prependMessages([{ id: 1 }]);
  assert.deepEqual(el('messages').children.map(n => n.id), ['task-hall-brief', 'msg-1', 'msg-2']);
  assert.equal(ctx.messageRecords.size, 2); assert.equal(ctx.renderedMessageIds.size, 2);
  ctx.renderTaskHallBrief(); assert.equal(el('messages').children[0].id, 'task-hall-brief'); assert.equal(ctx.messageRecords.size, 2);
});
test('任务状态与旁观权限共同控制输入；普通群聊保持可用', () => {
  const { ctx, el } = harness();
  ctx.syncComposerReadOnly(); assert.equal(el('input').disabled, true); assert.equal(el('send').disabled, true); assert.equal(el('attach').disabled, true);
  for (const state of ['clarification_requested', 'needs_decision']) { ctx.projectTasks[0].workflow_status = state; ctx.syncComposerReadOnly(); assert.equal(el('input').disabled, false); assert.equal(el('send').disabled, false); }
  ctx.observer = true; ctx.syncComposerReadOnly(); assert.equal(el('input').disabled, true); ctx.observer = false;
  ctx.projectTasks[0].workflow_status = 'submitted'; ctx.syncComposerReadOnly(); assert.equal(el('send').disabled, true);
  ctx.renderTaskHallBrief(); ctx.activeGroupId = 'g'; ctx.workspaceUI.mode = 'chats'; ctx.renderTaskHallBrief(); ctx.syncComposerReadOnly();
  assert.equal(el('input').disabled, false); assert.equal(el('send').disabled, false); assert.equal(el('messages').children.length, 0);
});

test('reset on leaving or switching task', () => {
  const { ctx, el } = harness();
  ctx.renderTaskHallBrief();
  el('messages').children[0].children[0].children[3].onclick();
  ctx.activeGroupId = 'g'; ctx.renderTaskHallBrief();
  ctx.activeGroupId = 't'; ctx.renderTaskHallBrief();
  assert.equal(el('messages').children[0].children[1].hidden, true);
  el('messages').children[0].children[0].children[3].onclick();
  ctx.projectTasks[0].id = 2; ctx.renderTaskHallBrief();
  assert.equal(el('messages').children[0].children[1].hidden, true);
});
