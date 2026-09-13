const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');
const { workspaceParseTime, workspaceFormatDuration, workspaceTaskDuration } = helpers;
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
function appFunction(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  assert.ok(start >= 0 && end >= 0);
  return rest.slice(0, end + 1);
}

test('耗时格式 HH:MM:SS，小时超过 24 不回卷', () => {
  assert.equal(workspaceFormatDuration(0), '00:00:00');
  assert.equal(workspaceFormatDuration(999), '00:00:00');
  assert.equal(workspaceFormatDuration(3661 * 1000), '01:01:01');
  assert.equal(workspaceFormatDuration(25 * 3600 * 1000), '25:00:00');
  assert.equal(workspaceFormatDuration(100 * 3600 * 1000), '100:00:00');
  assert.equal(workspaceFormatDuration(-1), '—');
  assert.equal(workspaceFormatDuration(NaN), '—');
});

test('UTC 无时区字符串按 UTC 解析，明确偏移按原值解析', () => {
  const naive = workspaceParseTime('2026-09-13T09:18:20.702888');
  assert.equal(naive, Date.UTC(2026, 8, 13, 9, 18, 20, 702));
  // SQLite 原样空格分隔形态也能解析为 UTC
  assert.equal(workspaceParseTime('2026-09-13 09:18:20'), Date.UTC(2026, 8, 13, 9, 18, 20));
  const offset = workspaceParseTime('2026-09-13T17:18:20+08:00');
  assert.equal(offset, Date.UTC(2026, 8, 13, 9, 18, 20));
  assert.equal(workspaceParseTime('2026-09-13T09:18:20Z'), Date.UTC(2026, 8, 13, 9, 18, 20));
  assert.equal(workspaceParseTime('not-a-time'), null);
  assert.equal(workspaceParseTime(''), null);
  assert.equal(workspaceParseTime(null), null);
});

test('缺少或无效起止时间显示 —，不产生 NaN 或负数', () => {
  const now = Date.UTC(2026, 8, 13, 12, 0, 0);
  // 从未领取（排队/取消未执行）
  assert.equal(workspaceTaskDuration({ workflow_status: 'canceled', claimed_at: null, finished_at: '2026-09-13T10:00:00' }, now), '—');
  assert.equal(workspaceTaskDuration({ workflow_status: 'assigned', claimed_at: null, finished_at: null }, now), '—');
  // 无效时间
  assert.equal(workspaceTaskDuration({ workflow_status: 'in_progress', claimed_at: '???', finished_at: null }, now), '—');
  // 结束早于开始
  assert.equal(workspaceTaskDuration({ workflow_status: 'failed', claimed_at: '2026-09-13T11:00:00', finished_at: '2026-09-13T10:00:00' }, now), '—');
  // 非终态也未执行中（如租约过期退回队列）：不冻结也不计时
  assert.equal(workspaceTaskDuration({ workflow_status: 'assigned', claimed_at: '2026-09-13T09:00:00', finished_at: null }, now), '—');
});

test('终态按 claimed_at→finished_at 冻结，与当前时间无关', () => {
  const task = { workflow_status: 'completed', claimed_at: '2026-09-13T09:01:45.452521', finished_at: '2026-09-13T09:05:24.568057' };
  const expected = workspaceFormatDuration(Date.UTC(2026, 8, 13, 9, 5, 24, 568) - Date.UTC(2026, 8, 13, 9, 1, 45, 452));
  assert.equal(expected, '00:03:39');
  assert.equal(workspaceTaskDuration(task, Date.UTC(2030, 0, 1)), '00:03:39');
  assert.equal(workspaceTaskDuration(task, Date.UTC(2020, 0, 1)), '00:03:39');
  // 失败 / 取消同样冻结
  assert.equal(workspaceTaskDuration({ ...task, workflow_status: 'failed' }, Date.UTC(2030, 0, 1)), '00:03:39');
  assert.equal(workspaceTaskDuration({ ...task, workflow_status: 'canceled' }, Date.UTC(2030, 0, 1)), '00:03:39');
});

test('执行中按当前时间实时计算，不含排队与待收取时间', () => {
  // claimed 之前排了 10 分钟队：从 claimed_at 起算
  const task = { workflow_status: 'in_progress', created_at: '2026-09-13T08:50:00', claimed_at: '2026-09-13T09:00:00', finished_at: null };
  assert.equal(workspaceTaskDuration(task, Date.UTC(2026, 8, 13, 9, 0, 5)), '00:00:05');
  assert.equal(workspaceTaskDuration(task, Date.UTC(2026, 8, 13, 10, 0, 0)), '01:00:00');
  // submitted（待收取）也已有 finished_at，按执行结束冻结
  assert.equal(workspaceTaskDuration({ workflow_status: 'submitted', claimed_at: '2026-09-13T09:00:00', finished_at: '2026-09-13T09:05:00' }, Date.UTC(2026, 8, 13, 9, 30, 0)), '00:05:00');
});

function tickHarness(tasks, elements) {
  const context = vm.createContext({
    ...helpers,
    projectTasks: tasks,
    document: { querySelectorAll: () => elements.filter(el => el.dataset.running === '1' && el.className === 'task-card-duration') },
  });
  vm.runInContext(appFunction('tickTaskDurations'), context);
  return context.tickTaskDurations;
}

test('统一计时器只刷新执行中条目，不重建列表、不触碰终态', () => {
  const running = { className: 'task-card-duration', dataset: { taskId: '1', running: '1' }, textContent: '00:00:01' };
  const finished = { className: 'task-card-duration', dataset: { taskId: '2' }, textContent: '00:03:39' };
  const tasks = [
    { id: 1, workflow_status: 'in_progress', claimed_at: '2026-09-13T09:00:00', finished_at: null },
    { id: 2, workflow_status: 'completed', claimed_at: '2026-09-13T09:01:45', finished_at: '2026-09-13T09:05:24' },
  ];
  const tick = tickHarness(tasks, [running, finished]);
  tick(Date.UTC(2026, 8, 13, 9, 0, 42));
  assert.equal(running.textContent, '00:00:42');
  assert.equal(finished.textContent, '00:03:39');
  // 再次 tick 按真实时间戳重算，不累加误差
  tick(Date.UTC(2026, 8, 13, 9, 1, 5));
  assert.equal(running.textContent, '00:01:05');
  // 任务从列表中消失时不写回
  const gone = { className: 'task-card-duration', dataset: { taskId: '99', running: '1' }, textContent: 'x' };
  tickHarness(tasks, [gone])(Date.UTC(2026, 8, 13, 9, 2, 0));
  assert.equal(gone.textContent, 'x');
});

test('startChat 与登出各只挂/清一个耗时计时器', () => {
  const startChat = appFunction('startChat');
  assert.match(startChat, /taskDurationTimer = setInterval\(tickTaskDurations, 1000\)/);
  assert.match(startChat, /if \(taskDurationTimer\) clearInterval\(taskDurationTimer\)/);
  const logoutBlock = source.slice(source.indexOf('logoutBtn.addEventListener'), source.indexOf('loadOlderBtn.addEventListener'));
  assert.match(logoutBlock, /clearInterval\(taskDurationTimer\)/);
  // 全文件只有一处耗时计时器 setInterval，避免多 timer 叠加
  assert.equal((source.match(/setInterval\(tickTaskDurations/g) || []).length, 1);
});
