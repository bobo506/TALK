/* “查看成果 / 收起成果” 切换的行为测试：通过 vm 运行真实 web/workspace.js，验证异步竞态与无障碍状态。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function fakePanel() {
  const classes = new Set(['hidden']);
  return {
    textContent: '',
    classList: { add: name => classes.add(name), remove: name => classes.delete(name) },
    isHidden: () => classes.has('hidden'),
  };
}
function fakeButton() {
  return { textContent: '', attrs: {}, setAttribute(name, value) { this.attrs[name] = String(value); } };
}
// renderWorkspaceTaskStory 需要的通用元素桩：记录子节点与属性，不实现真实布局。
function fakeEl() {
  return {
    children: [],
    attrs: {},
    textContent: '',
    className: '',
    open: false,
    type: '',
    classList: { add() {}, remove() {}, toggle() {} },
    appendChild(child) { this.children.push(child); },
    append(...items) { this.children.push(...items); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener() {},
  };
}
function harness(options = {}) {
  const panel = fakePanel();
  const button = fakeButton();
  const pending = [];
  const elements = {};
  const context = vm.createContext({
    myId: 'human:qa',
    activeProjectId: 'p1',
    members: [],
    selectedTaskTree: null,
    taskTreeError: '',
    URLSearchParams,
    getContextTask() { return context.currentTask; },
    canEnterGroup: () => options.canEnter !== false,
    showTaskDetailsError(message) { context.error = message; },
    apiFetch: url => new Promise((resolve, reject) => pending.push({ url, resolve, reject })),
    readErrorDetail: async () => '成果加载失败，请重试。',
    formatTaskTime: () => '',
    taskStatusMeta: () => ({ label: '', className: '' }),
    taskKindLabel: kind => kind || '',
    document: {
      getElementById: id => {
        if (id === 'task-result-body') return panel;
        if (['task-notice', 'task-outcome-summary', 'task-requirements', 'task-flow-list'].includes(id)) {
          return elements[id] || (elements[id] = fakeEl());
        }
        return { addEventListener() {}, value: '' };
      },
      querySelector: selector => (selector === '[aria-controls="task-result-body"]' ? button : null),
      createElement: () => fakeEl(),
    },
  });
  vm.runInContext(source, context);
  context.currentTask = options.task || { id: 19, hall_group_id: 'g1', result_message_id: 101 };
  const ui = vm.runInContext('workspaceUI', context);
  const reply = (index, data) => pending[index].resolve({ ok: true, json: async () => data });
  return { context, ui, panel, button, pending, reply };
}
const message = data => [{ id: 101, type: 'text', ...data }];

test('首次点击展开成果，按钮变为“收起成果”并标记 aria-expanded', async () => {
  const { context, panel, button, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  assert.equal(panel.textContent, '正在加载成果…');
  assert.equal(panel.isHidden(), false);
  assert.equal(button.textContent, '收起成果');
  assert.equal(button.attrs['aria-expanded'], 'true');
  reply(0, message({ content: '验收通过的成果' }));
  await request;
  assert.equal(panel.textContent, '验收通过的成果');
  assert.equal(panel.isHidden(), false);
  assert.equal(button.textContent, '收起成果');
});

test('再次点击立即收起并清除展示内容，按钮恢复“查看成果”', async () => {
  const { context, panel, button, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask); // 展开，请求挂起
  await context.showWorkspaceResult(context.currentTask); // 收起
  assert.equal(panel.isHidden(), true);
  assert.equal(panel.textContent, '');
  assert.equal(button.textContent, '查看成果');
  assert.equal(button.attrs['aria-expanded'], 'false');
  assert.equal(context.workspaceResultOpen(context.currentTask), false);
  reply(0, message({ content: '迟到的成果' }));
  await request;
  assert.equal(panel.isHidden(), true);
  assert.equal(panel.textContent, '');
});

test('加载中可收起，旧请求失败也不得重新显示内容', async () => {
  const { context, panel, pending } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  await context.showWorkspaceResult(context.currentTask); // 加载中收起
  pending[0].reject(new Error('网络错误'));
  await request;
  assert.equal(panel.isHidden(), true);
  assert.equal(panel.textContent, '');
});

test('展开→收起→再展开时，旧响应不得覆盖新响应', async () => {
  const { context, panel, reply } = harness();
  const first = context.showWorkspaceResult(context.currentTask);
  await context.showWorkspaceResult(context.currentTask); // 收起
  const second = context.showWorkspaceResult(context.currentTask); // 再展开
  reply(0, message({ content: '旧响应' }));
  await first;
  assert.equal(panel.textContent, '正在加载成果…');
  reply(1, message({ content: '新响应' }));
  await second;
  assert.equal(panel.textContent, '新响应');
  assert.equal(panel.isHidden(), false);
});

test('切换任务后旧成果响应不能污染当前页面', async () => {
  const { context, panel, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  context.currentTask = { id: 20, hall_group_id: 'g2', result_message_id: 202 };
  reply(0, message({ content: '任务19的成果' }));
  await request;
  assert.equal(panel.textContent, '正在加载成果…');
});

test('切换账号后旧成果响应不能写入页面', async () => {
  const { context, panel, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  context.myId = 'human:other';
  reply(0, message({ content: '旧账号的成果' }));
  await request;
  assert.equal(panel.textContent, '正在加载成果…');
});

test('无权限时保留可见提示，不发出请求也不展开面板', async () => {
  const { context, panel, pending } = harness({ canEnter: false });
  await context.showWorkspaceResult(context.currentTask);
  assert.match(context.error, /无法查看成果/);
  assert.equal(pending.length, 0);
  assert.equal(panel.isHidden(), true);
  assert.equal(context.workspaceResultOpen(context.currentTask), false);
});

test('加载失败保留错误内容呈现，面板保持可收起状态', async () => {
  const { context, panel, button, pending } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  pending[0].resolve({ ok: false });
  await request;
  assert.equal(panel.textContent, '成果加载失败，请重试。');
  assert.equal(panel.isHidden(), false);
  assert.equal(button.textContent, '收起成果');
});

test('成果不存在、已撤回与文件成果的呈现保持不变', async () => {
  const missing = harness();
  const request = missing.context.showWorkspaceResult(missing.context.currentTask);
  missing.reply(0, []);
  await request;
  assert.equal(missing.panel.textContent, '没有找到指定成果，请查看完整对话。');

  const revoked = harness();
  const revokedRequest = revoked.context.showWorkspaceResult(revoked.context.currentTask);
  revoked.reply(0, message({ content: '已删除', revoked_at: '2026-09-08' }));
  await revokedRequest;
  assert.equal(revoked.panel.textContent, '这条成果消息已撤回。');

  const file = harness();
  const fileRequest = file.context.showWorkspaceResult(file.context.currentTask);
  file.reply(0, [{ id: 101, type: 'file', filename: 'report.zip', caption: '测试报告' }]);
  await fileRequest;
  assert.match(file.panel.textContent, /文件成果：report\.zip/);
  assert.match(file.panel.textContent, /请在完整对话中下载文件。/);
});

test('收起后实际调用生产 renderWorkspaceTaskStory 重绘，成果仍保持收起', async () => {
  const { context, ui, panel, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  reply(0, message({ content: '成果' }));
  await request;
  const before = ui.resultRequest;
  await context.showWorkspaceResult(context.currentTask); // 收起
  assert.equal(ui.result, null);
  assert.ok(ui.resultRequest > before);
  // 真实调用生产 renderWorkspaceTaskStory 重绘详情：收起后状态为空，重绘必须保持隐藏并清空内容。
  context.renderWorkspaceTaskStory(context.currentTask);
  assert.equal(context.workspaceResultOpen(context.currentTask), false);
  assert.equal(panel.isHidden(), true);
  assert.equal(panel.textContent, '');
});

test('项目切换后旧成果响应不能写入页面', async () => {
  const { context, panel, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask);
  context.activeProjectId = 'p2'; // current() 捕获的 projectId 不再匹配
  reply(0, message({ content: '旧项目的成果' }));
  await request;
  assert.equal(panel.textContent, '正在加载成果…');
});

test('切到无任务项目再返回旧任务，旧展开状态不能复活', async () => {
  const { context, ui, panel, reply } = harness();
  const request = context.showWorkspaceResult(context.currentTask); // p1 任务19 展开
  // 切换项目：setActiveProject 改 activeProjectId 并调用 resetWorkspaceResult 作废旧请求。
  context.activeProjectId = 'p2';
  context.resetWorkspaceResult();
  assert.equal(ui.result, null);
  reply(0, message({ content: '项目p1的成果' }));
  await request; // 旧响应被丢弃
  assert.equal(panel.textContent, '正在加载成果…');
  // 返回旧项目旧任务：成果状态已清空，重绘后仍保持收起。
  context.activeProjectId = 'p1';
  assert.equal(context.workspaceResultOpen(context.currentTask), false);
  context.renderWorkspaceTaskStory(context.currentTask);
  assert.equal(panel.isHidden(), true);
  assert.equal(panel.textContent, '');
});
