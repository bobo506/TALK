const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
function appFunction(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  assert.ok(start >= 0 && end >= 0);
  return rest.slice(0, end + 1);
}
const context = vm.createContext({});
for (const name of ['taskKindLabel', 'taskOptionLabel']) vm.runInContext(appFunction(name), context);

test('已归一化标题直接复用，不重复拼编号', () => {
  const label = context.taskOptionLabel({id: 61, task_kind: 'development', title: '61-统一任务标题', content: '正文'});
  assert.equal(label, '61-统一任务标题 · 执行工作');
});

test('旧任务无编号前缀时保持 #编号 兼容展示', () => {
  const label = context.taskOptionLabel({id: 54, task_kind: 'general', title: '前端：任务列表显示执行耗时', content: '正文'});
  assert.equal(label, '#54 · 前端：任务列表显示执行耗时 · 普通任务');
});

test('无标题旧任务回退到正文首行且不出现 undefined', () => {
  const label = context.taskOptionLabel({id: 9, task_kind: 'review', title: null, content: '第一行\n第二行'});
  assert.equal(label, '#9 · 第一行 · 检查');
  assert.ok(!label.includes('undefined') && !label.includes('null'));
});

test('名称中的数字与连字符原样保留', () => {
  const label = context.taskOptionLabel({id: 62, task_kind: 'general', title: '62-v2-修复3-5天耗时', content: '正文'});
  assert.equal(label, '62-v2-修复3-5天耗时 · 普通任务');
});
