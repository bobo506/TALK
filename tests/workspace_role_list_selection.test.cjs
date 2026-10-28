/* 角色列表文字可框选复制（2026-10-28）：选区判定、重绘延后与拖选守卫的定向测试。
   选区判定直接 vm 运行真实 web/workspace.js 的实现；样式断言读取真实样式表。 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const helperStart = source.indexOf('function workspaceRoleListSelection()');
const helperEnd = source.indexOf('function renderWorkspaceList()');
const helper = helperStart >= 0 && helperEnd > helperStart ? source.slice(helperStart, helperEnd) : '';

// 只跑选区判定这一段，不加载整份 workspace.js（它依赖 app.js 注入的全局）。
function run(getSelection) {
  const context = vm.createContext({ window: typeof getSelection === 'undefined' ? {} : { getSelection } });
  vm.runInContext(helper, context);
  return context;
}
const entryEl = { nodeType: 1, closest: selector => (selector === '.role-entry' ? { className: 'role-entry' } : null) };
const outsideEl = { nodeType: 1, closest: () => null };

test('选区判定取自真实源码而不是测试自带桩', () => {
  assert.ok(helper.includes('function workspaceRoleListSelection()'));
  assert.ok(helper.length > 120);
});

test('角色条目内未折叠的选区返回 selection', () => {
  const selection = { isCollapsed: false, anchorNode: entryEl };
  assert.equal(run(() => selection).workspaceRoleListSelection(), selection);
});

test('折叠选区、列表外选区、无锚点、无 selection 均安全返回 null', () => {
  assert.equal(run(() => ({ isCollapsed: true, anchorNode: entryEl })).workspaceRoleListSelection(), null);
  assert.equal(run(() => ({ isCollapsed: false, anchorNode: outsideEl })).workspaceRoleListSelection(), null);
  assert.equal(run(() => ({ isCollapsed: false, anchorNode: null })).workspaceRoleListSelection(), null);
  assert.equal(run(() => null).workspaceRoleListSelection(), null);
  assert.equal(run(undefined).workspaceRoleListSelection(), null);
});

test('文本节点锚点沿 parentElement 判定', () => {
  const selection = { isCollapsed: false, anchorNode: { nodeType: 3, parentElement: entryEl } };
  assert.equal(run(() => selection).workspaceRoleListSelection(), selection);
});

test('角色行样式声明 user-select:text，按钮行文字才能被框选', () => {
  const css = fs.readFileSync(require.resolve('../web/workspace.css'), 'utf8');
  assert.match(css, /\.role-row \{[^}]*user-select:text/);
  assert.match(css, /\.role-row \{[^}]*-webkit-user-select:text/);
});

test('有选区时延后重绘，选区结束后补绘，角色行与项目设置行拖选都不导航', () => {
  assert.match(source, /if \(workspaceRoleListSelection\(\)\) \{ workspaceUI\.listRenderDeferred = true; return; \}/);
  assert.match(source, /if \(!workspaceUI\.listRenderDeferred \|\| workspaceRoleListSelection\(\)\) return;/);
  assert.match(source, /document\.addEventListener\?\.\("selectionchange", \(\) => \{/);
  const guards = source.match(/if \(workspaceRoleListSelection\(\)\) return;/g) || [];
  assert.ok(guards.length >= 2, `角色行与项目设置行的点击守卫都应存在，实际 ${guards.length} 处`);
});
