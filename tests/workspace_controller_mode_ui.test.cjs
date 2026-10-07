// C2-B 项目设置页“调度模式”面板：状态/DOM 异步测试。
// 通过 vm 抽取 workspace.js 中 C2-B 代码块（标记 // ── C2-B 项目调度模式 到
// renderWorkspaceTaskStory 之间），用 DOM 存根验证：加载/human/agent、成功核实、
// I-2 起保存“主动”为固定意向提示（不再查询/依赖任何指定状态）、缺字段/404 不支持、
// 409 只 GET 刷新不自动重写
// （含 GET 失败恢复：409 后需重读状态下重试入口可见、保存暂禁、重试只 GET 不 PATCH、
// 读取成功清新版本后由用户明确保存、需重读不串上下文）、400/422/普通错误保留选择且不进入
// 需重读、非法版本禁写、未知模式如实降级、
// 跨项目/账号迟到成功与失败不回填、保存中续选保护、saveToken 所有权不锁死、
// 面板可见性互斥与同上下文不重读；
// C2-B-UX 离页复位：切任务/群聊/具体角色放弃未保存选择且全程无 PATCH、返回显示已保存
// 模式（含已保存主动返主动）、失败未保存离开返回原已保存、同页重绘/轮询不吞选择、
// 保存在途离开/保存中续选后离开的迟到成功展示真实保存结果、离开期间迟到失败如实显示；
// 已保存状态行只显示模式名、不含（版本 N），expected_version/CAS 仍原样工作。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const workspaceSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const blockStart = workspaceSource.indexOf('// ── C2-B 项目调度模式');
const blockEnd = workspaceSource.indexOf('function renderWorkspaceTaskStory(');
assert.ok(blockStart > 0 && blockEnd > blockStart, 'C2-B 代码块边界');
const modeBlock = workspaceSource.slice(blockStart, blockEnd);

function fakeEl(id, onFocus) {
  const classes = new Set();
  const el = {
    id, value: '', textContent: '', className: '', disabled: false, checked: false, title: '',
    dataset: {}, children: [], focusCalls: 0,
    classList: {
      add: c => classes.add(c),
      remove: c => classes.delete(c),
      toggle: (c, force) => { const on = force === undefined ? !classes.has(c) : force; on ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    addEventListener() {},
    appendChild(child) { el.children.push(child); return child; },
    replaceChildren() { el.children.length = 0; },
    focus() { if (classes.has('hidden') || el.disabled) return; el.focusCalls++; if (onFocus) onFocus(el); },
  };
  return el;
}

const MEMBERS = [
  { id: 'human:qa', kind: 'human', display_name: 'bobo' },
  { id: 'agent:kimi', kind: 'agent', display_name: 'Kimi' },
];

// enter() 的 read 合并进默认项目响应。服务端 ProjectOut 仍携带已弃用的指定字段
//（兼容输出），保留在默认响应里可顺带验证模式面板完全忽略它们。
function harness({ human = true, projectId = 'A' } = {}) {
  const pending = [];
  const elements = new Map();
  let settingsSelected = true;
  const document = {
    getElementById: id => {
      if (!elements.has(id)) elements.set(id, fakeEl(id, el => { document.activeElement = el; }));
      return elements.get(id);
    },
    createElement: tag => fakeEl(tag),
    activeElement: null,
    body: fakeEl('body'),
  };
  const context = vm.createContext({
    workspaceUI: { mode: 'roles' }, blackboardOpen: true,
    activeProjectId: projectId, myId: human ? 'human:qa' : 'agent:kimi',
    members: MEMBERS,
    projects: [
      { project_id: 'A', controller_member_id: null, controller_assignment_status: 'unassigned' },
      { project_id: 'B', controller_member_id: null, controller_assignment_status: 'unassigned' },
    ],
    currentMemberIsHuman: () => human,
    workspaceSettingsSelected: () => settingsSelected,
    apiFetch: (url, opts) => new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject })),
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    document,
  });
  vm.runInContext(modeBlock, context);
  vm.runInContext('this.__ui = controllerModeUI;', context);
  const ui = context.__ui;
  const el = id => document.getElementById(id);
  const reply = (index, data, { ok = true, status = 200 } = {}) =>
    pending[index].resolve({ ok, status, json: async () => data });
  const fail = (index, err) => pending[index].reject(err);
  async function enter(project = projectId, read = {}) {
    context.activeProjectId = project;
    const merged = {
      project_id: project,
      controller_mode: 'passive',
      controller_mode_version: 0,
      controller_member_id: null,
      controller_assignment_status: 'unassigned',
      ...read,
    };
    const request = context.renderControllerModePanel();
    reply(pending.length - 1, merged);
    await request;
  }
  const setSettingsSelected = value => { settingsSelected = value; };
  return { context, pending, reply, fail, el, ui, enter, document, setSettingsSelected };
}

const EFFECTIVE_LINE = '实际执行：尚无生效的主动调度（本版本不支持自动生效）';

test('无项目或未登录时面板隐藏且不发起请求', () => {
  const { context, pending, el } = harness();
  context.activeProjectId = null;
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  context.activeProjectId = 'A'; context.myId = null;
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  assert.equal(pending.length, 0);
});

test('human 加载被动默认：状态两行如实显示，保存需显式选择且版本原样回传', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), false);
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：被动');
  assert.ok(!/（版本/.test(el('controller-mode-saved').textContent), '已保存状态行不显示版本号');
  assert.equal(el('controller-mode-effective').textContent, EFFECTIVE_LINE);
  assert.ok(!/已启用/.test(el('controller-mode-effective').textContent));
  assert.equal(el('controller-mode-passive').checked, true);
  assert.equal(el('controller-mode-active').checked, false);
  assert.equal(el('controller-mode-save-btn').disabled, true, '无修改时保存不可用');
  assert.equal(el('controller-mode-passive').disabled, false);
  // 选择“主动”只是未保存选择，不发请求
  context.selectControllerMode('active');
  assert.equal(pending.length, 1, '切换选项不自动提交');
  assert.equal(el('controller-mode-save-btn').disabled, false);
  assert.match(el('controller-mode-status').textContent, /尚未保存/);
  const save = context.saveControllerMode();
  assert.equal(ui.saving, true);
  const patch = pending[pending.length - 1];
  assert.match(patch.url, /\/api\/projects\/A\/controller-mode$/);
  assert.equal(patch.opts.method, 'PATCH');
  assert.deepEqual(JSON.parse(patch.opts.body), { mode: 'active', expected_version: 0 });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saving, false);
  assert.equal(ui.saved, 'active');
  assert.equal(ui.version, 1);
  assert.equal(ui.selection, null, '成功后清空未保存选择');
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：主动');
  assert.equal(el('controller-mode-active').checked, true);
  // I-2：保存主动为固定意向提示，不再查询任何指定状态
  assert.equal(ui.notice, '已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。');
  assert.match(el('controller-mode-effective').textContent, /尚无生效的主动调度/, '保存主动不伪装成已生效');
});

test('保存主动/被动提示固定：不查询、不依赖任何指定状态（响应携带已弃用字段也无关）', async () => {
  // 指定为有效 assigned：提示同样是固定意向文案
  const { context, pending, reply, ui, enter } = harness();
  await enter('A', { controller_member_id: 'agent:kimi', controller_assignment_status: 'assigned' });
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: 'agent:kimi', controller_assignment_status: 'assigned',
  });
  await save;
  assert.equal(ui.notice, '已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。');
  assert.ok(!/已生效|已启用/.test(ui.notice));
  // 指定失效（成员被禁用）：提示逐字节相同——模式保存不再有指定前置
  const h2 = harness();
  await h2.enter('A', { controller_member_id: 'agent:kimi', controller_assignment_status: 'member_disabled' });
  h2.context.selectControllerMode('active');
  const save2 = h2.context.saveControllerMode();
  h2.reply(h2.pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: 'agent:kimi', controller_assignment_status: 'member_disabled',
  });
  await save2;
  assert.equal(h2.ui.notice, '已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。');
});

test('已保存主动无任何指定可用性提示；指定字段变化不影响模式状态与面板', async () => {
  const { context, el, ui, enter } = harness();
  await enter('A', {
    controller_mode: 'active', controller_mode_version: 3,
    controller_member_id: 'agent:kimi', controller_assignment_status: 'assigned',
  });
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：主动');
  assert.equal(el('controller-mode-status').textContent, '', '无错误/未保存差异时状态行留白，无指定提示');
  // 项目缓存中的指定字段变化（已弃用字段仍由服务端返回）不再被本面板读取
  context.projects[0].controller_assignment_status = 'not_in_roster';
  context.syncControllerModePanel();
  assert.ok(!/主控|指定/.test(el('controller-mode-status').textContent), '不出现任何指定可用性提示');
  assert.equal(ui.saved, 'active');
  assert.equal(ui.version, 3);
  assert.equal(el('controller-mode-effective').textContent, EFFECTIVE_LINE);
});

test('agent 账号只读：radio 禁用、保存隐藏、提示由项目负责人管理，但仍能看到已保存状态', async () => {
  const { el, enter } = harness({ human: false });
  await enter('A', { controller_mode: 'active', controller_mode_version: 2 });
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：主动');
  assert.equal(el('controller-mode-effective').textContent, EFFECTIVE_LINE);
  assert.equal(el('controller-mode-passive').disabled, true);
  assert.equal(el('controller-mode-active').disabled, true);
  assert.equal(el('controller-mode-save-btn').classList.contains('hidden'), true);
  assert.match(el('controller-mode-status').textContent, /由项目负责人管理/);
});

test('加载中禁用并提示读取中；读取失败显示错误与重试入口，不伪装已保存被动', async () => {
  const { context, pending, reply, el } = harness();
  context.activeProjectId = 'A';
  context.renderControllerModePanel();
  assert.match(el('controller-mode-saved').textContent, /读取中/);
  assert.match(el('controller-mode-effective').textContent, /无法确认/);
  assert.equal(el('controller-mode-passive').disabled, true);
  assert.equal(el('controller-mode-active').disabled, true);
  assert.equal(el('controller-mode-save-btn').disabled, true);
  reply(pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await new Promise(r => setTimeout(r, 0));
  assert.match(el('controller-mode-saved').textContent, /读取失败/);
  assert.ok(!/已保存设置：被动/.test(el('controller-mode-saved').textContent));
  assert.equal(el('controller-mode-retry-btn').classList.contains('hidden'), false);
  assert.equal(el('controller-mode-save-btn').disabled, true);
});

test('旧服务 GET 缺模式字段：明确不支持并禁用保存，不把缺失当成被动', async () => {
  const { context, pending, reply, el, ui } = harness();
  context.activeProjectId = 'A';
  const request = context.renderControllerModePanel();
  reply(pending.length - 1, { project_id: 'A', display_name: '旧服务' });
  await request;
  assert.equal(ui.supported, false);
  assert.match(el('controller-mode-saved').textContent, /当前服务不支持调度模式设置/);
  assert.ok(!/已保存设置：被动/.test(el('controller-mode-saved').textContent), '缺失不得伪装成被动');
  assert.match(el('controller-mode-effective').textContent, /无法确认/);
  assert.equal(el('controller-mode-save-btn').disabled, true);
  const before = pending.length;
  await context.saveControllerMode();
  assert.equal(pending.length, before, '不支持时不发出任何写请求');
});

test('PATCH 404：明确不支持并禁用保存，不假报成功、保留当前选择', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'Not Found' }, { ok: false, status: 404 });
  await save;
  assert.equal(ui.supported, false);
  assert.match(ui.error, /尚未支持调度模式设置/);
  assert.match(ui.error, /本次未保存/);
  assert.equal(ui.saved, 'passive', '不得把提交值当成已保存');
  assert.equal(ui.selection, 'active', '选择保留，可查明后再操作');
  assert.equal(el('controller-mode-save-btn').disabled, true, '不支持后保存禁用');
});

test('409 只 GET 刷新最新模式/版本、不自动重写；选择保留，可按新版本手动再保存', async () => {
  const { context, pending, reply, ui, el, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'controller mode version conflict: expected_version=0, current_version=1' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  // 409 后自动发起一次 GET 重读，且没有第二个 PATCH
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 1);
  const reread = pending[pending.length - 1];
  assert.match(reread.url, /\/api\/projects\/A$/);
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saved, 'active');
  assert.equal(ui.version, 1);
  assert.match(ui.error, /已被他人修改/);
  assert.match(ui.error, /已刷新到最新状态，请确认后再保存/);
  // 用户选择“主动”恰好与刷新后的已保存值一致：无未保存差异
  assert.equal(el('controller-mode-save-btn').disabled, true);
  // 再改回被动：携带刷新后的版本 1 手动重试成功
  context.selectControllerMode('passive');
  const retry = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'passive', expected_version: 1 });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'passive', controller_mode_version: 2,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await retry;
  assert.equal(ui.saved, 'passive');
  assert.match(ui.notice, /已保存“被动”/);
});

test('409 后 GET 刷新失败：如实提示刷新失败，不谎报已刷新', async () => {
  const { context, pending, reply, ui, el, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'version conflict' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  reply(pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await save;
  assert.equal(ui.saving, false);
  assert.match(ui.error, /已被他人修改/);
  assert.match(ui.error, /自动刷新最新状态失败/);
  assert.ok(!/已刷新到最新状态/.test(ui.error));
  assert.equal(ui.saved, 'passive', '未刷到新状态不得改写已保存值');
  // F-1 恢复入口：该状态“重试”可见可操作、保存暂禁（避免旧版本无效 CAS），文案与控件一致
  assert.equal(ui.reloadNeeded, true, '409 后重读失败须标记需重读');
  assert.match(ui.error, /点“重试”/);
  assert.equal(el('controller-mode-retry-btn').classList.contains('hidden'), false, '文案指向的重试入口必须可见');
  assert.equal(el('controller-mode-save-btn').disabled, true, '需重读期间保存暂禁，不用旧版本再写');
});

test('409 重读失败后恢复：重试只 GET 不 PATCH，成功更新版本后由用户明确保存', async () => {
  const { context, pending, reply, ui, el, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'version conflict' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  reply(pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await save;
  assert.equal(ui.reloadNeeded, true);
  const patchCount = () => pending.filter(p => p.opts?.method === 'PATCH').length;
  assert.equal(patchCount(), 1);
  // 点“重试”（与按钮绑定同一入口 loadControllerMode）：只发 GET，不发 PATCH
  const reread = context.loadControllerMode();
  const getRequest = pending[pending.length - 1];
  assert.match(getRequest.url, /\/api\/projects\/A$/);
  assert.equal(getRequest.opts?.method, undefined, '重试必须是 GET 读取');
  assert.equal(patchCount(), 1, '重试不得自动重写');
  assert.equal(ui.reloadNeeded, true, '读取在途期间保持需重读');
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'passive', controller_mode_version: 5,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await reread;
  assert.equal(ui.reloadNeeded, false, '读取成功解除需重读');
  assert.equal(ui.saved, 'passive');
  assert.equal(ui.version, 5);
  assert.equal(ui.selection, 'active', '用户未保存选择保留');
  assert.equal(el('controller-mode-retry-btn').classList.contains('hidden'), true, '恢复后重试入口收起');
  assert.equal(el('controller-mode-save-btn').disabled, false, '有新版本与未保存选择时保存恢复可用');
  // 由用户明确保存：携带读取到的新版本
  const resave = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'active', expected_version: 5 });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 6,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await resave;
  assert.equal(ui.saved, 'active');
  assert.equal(ui.version, 6);
  assert.match(ui.notice, /已保存“主动”/);
});

test('需重读状态不串上下文：切项目清除并正常保存；重读成功的 409 不留需重读', async () => {
  const { context, pending, reply, ui, el, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'conflict' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  reply(pending.length - 1, { detail: 'boom' }, { ok: false, status: 500 });
  await save;
  assert.equal(ui.reloadNeeded, true);
  // 切到 B：上下文重置必须清除需重读，B 的保存不受影响
  await enter('B', { controller_mode: 'passive', controller_mode_version: 2 });
  assert.equal(ui.projectId, 'B');
  assert.equal(ui.reloadNeeded, false, '需重读不得串到新项目');
  assert.equal(el('controller-mode-retry-btn').classList.contains('hidden'), true);
  context.selectControllerMode('active');
  assert.equal(el('controller-mode-save-btn').disabled, false, '新项目保存不被旧需重读锁死');
  const saveB = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'active', expected_version: 2 });
  reply(pending.length - 1, {
    project_id: 'B', controller_mode: 'active', controller_mode_version: 3,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await saveB;
  assert.equal(ui.saved, 'active');
  // 409 但自动重读成功：状态已刷新，不留需重读，保存按新版本可用
  const h2 = harness();
  await h2.enter('A');
  h2.context.selectControllerMode('active');
  const save2 = h2.context.saveControllerMode();
  h2.reply(h2.pending.length - 1, { detail: 'conflict' }, { ok: false, status: 409 });
  await new Promise(r => setTimeout(r, 0));
  h2.reply(h2.pending.length - 1, {
    project_id: 'A', controller_mode: 'passive', controller_mode_version: 7,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save2;
  assert.equal(h2.ui.reloadNeeded, false, '重读成功即解除需重读');
  assert.equal(h2.ui.version, 7);
  assert.equal(h2.el('controller-mode-retry-btn').classList.contains('hidden'), true);
  assert.equal(h2.el('controller-mode-save-btn').disabled, false, '选择保留且与新版本不同，可手动再保存');
});

test('400/422 普通保存失败不进入需重读：重试入口不显示、保存保持可用', async () => {
  const { context, pending, reply, ui, el, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const bad = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'mode must be one of [passive, active]' }, { ok: false, status: 422 });
  await bad;
  assert.match(ui.error, /mode must be one of/);
  assert.equal(ui.reloadNeeded, false, '普通保存失败不得标记需重读');
  assert.equal(el('controller-mode-retry-btn').classList.contains('hidden'), true, 'loaded 状态的普通失败不显示重试');
  assert.equal(el('controller-mode-save-btn').disabled, false, '普通失败保留选择可直接改后重试保存');
});

test('400/422/500 失败：展示服务端 detail，保留当前选择可重试成功', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const bad = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'mode must be one of [passive, active]' }, { ok: false, status: 422 });
  await bad;
  assert.match(ui.error, /mode must be one of/);
  assert.equal(ui.selection, 'active', '失败保留当前选择');
  assert.equal(ui.saved, 'passive');
  // 普通 500
  const fail2 = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'internal error' }, { ok: false, status: 500 });
  await fail2;
  assert.match(ui.error, /internal error/);
  assert.equal(ui.selection, 'active');
  // 重试成功
  const retry = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'active', expected_version: 0 });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await retry;
  assert.equal(ui.saved, 'active');
  assert.equal(ui.selection, null);
});

test('版本安全边界：非安全整数或负版本禁止发送失真 expected_version', async () => {
  for (const version of [9223372036854775807, Number.MAX_SAFE_INTEGER + 1, 1.5, -1, '3', null]) {
    const { context, pending, el, ui, enter } = harness();
    await enter('A', { controller_mode_version: version });
    assert.match(el('controller-mode-status').textContent, /安全表示/, String(version));
    assert.equal(el('controller-mode-save-btn').disabled, true);
    context.selectControllerMode('active');
    const before = pending.length;
    await context.saveControllerMode();
    assert.equal(pending.length, before, '不得发出失真版本');
    assert.match(ui.error, /无法安全表示/);
  }
  // MAX_SAFE_INTEGER 边界值照常可用
  const { context, pending, reply, ui, enter } = harness();
  await enter('A', { controller_mode_version: Number.MAX_SAFE_INTEGER });
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'active', expected_version: Number.MAX_SAFE_INTEGER });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: Number.MAX_SAFE_INTEGER,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saved, 'active');
});

test('未知模式如实降级：显示无法识别、不预选任何项，选择合法模式可修复保存', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A', { controller_mode: 'turbo', controller_mode_version: 7 });
  assert.match(el('controller-mode-saved').textContent, /无法识别的模式（服务返回：turbo）/);
  assert.ok(!/已保存设置：被动/.test(el('controller-mode-saved').textContent), '未知模式不得伪装成被动');
  assert.equal(el('controller-mode-passive').checked, false);
  assert.equal(el('controller-mode-active').checked, false);
  context.selectControllerMode('passive');
  const save = context.saveControllerMode();
  assert.deepEqual(JSON.parse(pending[pending.length - 1].opts.body), { mode: 'passive', expected_version: 7 });
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'passive', controller_mode_version: 8,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saved, 'passive');
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：被动');
});

test('保存响应核实：项目不符、模式不一致或版本不可用都不算保存成功', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const wrongProject = context.saveControllerMode();
  reply(pending.length - 1, { project_id: 'B', controller_mode: 'active', controller_mode_version: 1 });
  await wrongProject;
  assert.match(ui.error, /未确认本次保存/);
  assert.equal(ui.saved, 'passive');
  const wrongMode = context.saveControllerMode();
  reply(pending.length - 1, { project_id: 'A', controller_mode: 'passive', controller_mode_version: 1 });
  await wrongMode;
  assert.match(ui.error, /未确认本次保存/);
  const badVersion = context.saveControllerMode();
  reply(pending.length - 1, { project_id: 'A', controller_mode: 'active', controller_mode_version: 9.223372036854776e18 });
  await badVersion;
  assert.match(ui.error, /未确认本次保存/, '失真版本（超出安全整数）不算成功');
  assert.equal(ui.saved, 'passive');
});

test('跨项目/账号迟到响应不回填新上下文；切回后正常保存', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  const saveIndex = pending.length - 1;
  await enter('B', { controller_mode: 'active', controller_mode_version: 5 });
  assert.equal(ui.projectId, 'B');
  assert.equal(ui.version, 5);
  // 项目 A 的迟到保存成功响应被丢弃
  reply(saveIndex, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.projectId, 'B');
  assert.equal(ui.version, 5);
  // 切账号后旧账号的迟到读取同样丢弃
  const h2 = harness();
  h2.context.activeProjectId = 'A';
  const load = h2.context.renderControllerModePanel();
  const loadIndex = h2.pending.length - 1;
  h2.context.myId = 'human:other';
  const load2 = h2.context.renderControllerModePanel();
  h2.reply(h2.pending.length - 1, {
    project_id: 'A', controller_mode: 'passive', controller_mode_version: 0,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await load2;
  h2.reply(loadIndex, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 9,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await load;
  assert.equal(h2.ui.memberId, 'human:other');
  assert.equal(h2.ui.saved, 'passive');
  assert.equal(h2.ui.version, 0);
});

test('保存中续选保护：保存响应不吞掉保存期间的新选择', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  assert.equal(ui.saving, true);
  // 保存期间用户改回“被动”：选择受保护，radio 可继续操作
  context.selectControllerMode('passive');
  assert.equal(el('controller-mode-passive').disabled, false, '保存中仍允许修改选择');
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saved, 'active');
  assert.equal(ui.selection, 'passive', '新选择不被响应吞掉');
  assert.match(ui.notice, /先前选择已保存；当前选择尚未保存/);
  assert.equal(el('controller-mode-passive').checked, true);
  assert.equal(el('controller-mode-save-btn').disabled, false, '新选择仍可继续保存');
});

test('A→B→A 往返后旧 PATCH 迟到：不清理新保存 saving、不写状态、不发第三次 PATCH', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const first = context.saveControllerMode(); // P1 在途
  const p1 = pending.length - 1;
  assert.equal(ui.saving, true);
  await enter('B');
  await enter('A');
  context.selectControllerMode('active');
  const second = context.saveControllerMode(); // P2 在途
  const p2 = pending.length - 1;
  assert.equal(ui.saving, true);
  // 旧 P1 迟到：上下文重新“活着”，但 P1 不拥有当前保存状态
  reply(p1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await first;
  assert.equal(ui.saving, true, '旧请求的 finally 不得提前清掉新请求的 saving');
  assert.equal(ui.saved, 'passive', '旧请求成败不得写入新上下文状态');
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 2, '旧请求到达不得触发第三次 PATCH');
  reply(p2, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await second;
  assert.equal(ui.saving, false);
  assert.equal(ui.saved, 'active', '最终状态由最新一次保存决定');
});

test('double submit 防护：保存中第二次写入直接返回，只有一个 PATCH', async () => {
  const { context, pending, reply, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const first = context.saveControllerMode();
  assert.equal(ui.saving, true);
  await context.saveControllerMode(); // 应被 saving 拦截
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 1);
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await first;
  assert.equal(ui.saved, 'active');
});

test('C2-B-UX 离页复位：切任务/群聊/具体角色放弃未保存选择，返回显示已保存被动，全程无 PATCH', async () => {
  const { context, pending, el, ui, enter, setSettingsSelected } = harness();
  await enter('A'); // 已保存被动 v0
  context.selectControllerMode('active');
  assert.equal(el('controller-mode-active').checked, true);
  assert.match(el('controller-mode-status').textContent, /尚未保存/);
  const before = pending.length;
  // 切任务页：放弃未保存选择
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null, '切任务页放弃未保存选择');
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  // 切群聊页：同样保持放弃
  context.workspaceUI.mode = 'chats';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null);
  // 返回项目设置：radio 匹配已保存被动，状态行只显示模式名
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), false);
  assert.equal(el('controller-mode-passive').checked, true, '返回显示已保存被动');
  assert.equal(el('controller-mode-active').checked, false);
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：被动');
  assert.equal(el('controller-mode-save-btn').disabled, true, '无未保存差异，保存不可用');
  // 再选一次，然后选具体角色（仍在角色标签但离开项目设置）：同样放弃
  context.selectControllerMode('active');
  setSettingsSelected(false);
  context.renderControllerModePanel();
  assert.equal(ui.selection, null, '选具体角色同样放弃未保存选择');
  setSettingsSelected(true);
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-passive').checked, true);
  assert.equal(el('controller-mode-save-btn').disabled, true);
  assert.equal(pending.filter(p => p.opts?.method === 'PATCH').length, 0, '离页不发 PATCH、不自动保存');
  assert.equal(pending.length, before, '同上下文往返不触发额外读取');
});

test('C2-B-UX 离页复位：已保存主动时未保存改选被动，离开返回显示主动', async () => {
  const { context, el, ui, enter } = harness();
  await enter('A', { controller_mode: 'active', controller_mode_version: 2 });
  assert.equal(el('controller-mode-active').checked, true);
  context.selectControllerMode('passive');
  assert.equal(el('controller-mode-passive').checked, true);
  assert.equal(el('controller-mode-save-btn').disabled, false);
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null);
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-active').checked, true, '返回显示已保存主动');
  assert.equal(el('controller-mode-passive').checked, false);
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：主动');
  assert.equal(el('controller-mode-save-btn').disabled, true, '未保存选择已放弃，不靠修改真实项目模式回到原值');
});

test('C2-B-UX 同页重绘/轮询同步不吞未保存选择', async () => {
  const { context, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  // 面板仍可见的重绘/同步（任务轮询重绘、提示刷新等同一路径）不得当成离开
  context.renderControllerModePanel();
  context.syncControllerModePanel();
  context.renderControllerModePanel();
  context.syncControllerModePanel();
  assert.equal(ui.selection, 'active', '同页重绘保留未保存选择');
  assert.equal(el('controller-mode-active').checked, true);
  assert.match(el('controller-mode-status').textContent, /尚未保存/);
  assert.equal(el('controller-mode-save-btn').disabled, false, '显式保存入口保持可用');
});

test('C2-B-UX 保存在途离开再进入：离开放弃选择但不取消在途保存，迟到成功展示真实保存结果', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  assert.equal(ui.saving, true);
  // 保存请求在途即离开：选择被放弃，在途保存不取消、request/saveToken 不动
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null);
  assert.equal(ui.saving, true, '离开不取消在途保存');
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saving, false, 'saveToken 不锁死，在途保存正常收尾');
  assert.equal(ui.saved, 'active');
  assert.equal(ui.version, 1);
  // 返回：展示真实已确认保存结果，radio 为已保存主动
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-active').checked, true);
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：主动');
  assert.match(el('controller-mode-status').textContent, /已保存“主动”/);
});

test('C2-B-UX 保存中续选后离开：续选被放弃，迟到成功只展示真实保存值', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  context.selectControllerMode('passive'); // 保存期间续选
  assert.equal(ui.selection, 'passive');
  context.workspaceUI.mode = 'chats';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null, '离页放弃保存期间的续选');
  reply(pending.length - 1, {
    project_id: 'A', controller_mode: 'active', controller_mode_version: 1,
    controller_member_id: null, controller_assignment_status: 'unassigned',
  });
  await save;
  assert.equal(ui.saved, 'active');
  assert.equal(ui.selection, null, '迟到成功不得复活离页前的续选');
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-active').checked, true);
  assert.match(el('controller-mode-status').textContent, /已保存“主动”/);
});

test('C2-B-UX 保存失败未保存即离开：返回显示原已保存模式，失败信息如实保留', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  reply(pending.length - 1, { detail: 'mode must be one of [passive, active]' }, { ok: false, status: 422 });
  await save;
  assert.equal(ui.selection, 'active', '面板会话内失败保留选择可重试');
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null, '离页放弃失败后的未保存选择');
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-passive').checked, true, '失败未保存返回仍原已保存被动');
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：被动');
  assert.match(el('controller-mode-status').textContent, /mode must be one of/, '失败信息如实保留');
});

test('C2-B-UX 离开期间迟到保存失败：返回如实显示错误与原已保存模式，不回填未保存选择', async () => {
  const { context, pending, reply, el, ui, enter } = harness();
  await enter('A');
  context.selectControllerMode('active');
  const save = context.saveControllerMode();
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(ui.selection, null);
  reply(pending.length - 1, { detail: 'internal error' }, { ok: false, status: 500 });
  await save;
  assert.equal(ui.saved, 'passive', '迟到失败不改写已保存值');
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-passive').checked, true);
  assert.equal(el('controller-mode-saved').textContent, '已保存设置：被动');
  assert.match(el('controller-mode-status').textContent, /internal error/, '迟到错误如实显示');
});

test('面板可见性：任务/群聊页与具体角色互斥隐藏，返回项目设置不重复读取', async () => {
  const { context, pending, el, enter, setSettingsSelected } = harness();
  await enter('A');
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), false);
  context.workspaceUI.mode = 'chats';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  context.workspaceUI.mode = 'tasks';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  const before = pending.length;
  context.workspaceUI.mode = 'roles';
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), false);
  assert.equal(pending.length, before, '同上下文返回不重复读取');
  // 选中具体角色：与项目设置互斥
  setSettingsSelected(false);
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), true);
  setSettingsSelected(true);
  context.renderControllerModePanel();
  assert.equal(el('controller-mode-panel').classList.contains('hidden'), false);
  assert.equal(pending.length, before);
  // 同项目重复重绘不重发请求
  context.renderControllerModePanel();
  context.renderControllerModePanel();
  assert.equal(pending.length, before);
});

test('隔离纪律：模式代码块不触碰指定字段、REQ-2 草稿、localStorage 与 innerHTML，无轮询、无已退役依赖', () => {
  assert.ok(!modeBlock.includes('localStorage.'), '状态只存内存');
  assert.ok(!modeBlock.includes('innerHTML'), '文案只走 textContent');
  assert.ok(!modeBlock.includes('setInterval'), '不新增后台轮询');
  assert.ok(!/project\.(display_name|description|development_requirements|controller_member_id|controller_assignment_version|controller_assignment_status)\s*=/.test(modeBlock), '项目缓存只回写模式两字段');
  assert.ok(modeBlock.includes('project.controller_mode ='), '模式字段回写存在');
  assert.ok(!modeBlock.includes('/controller-assignment'), '不读写指定');
  assert.ok(!modeBlock.includes('已启用'), '绝不把 effective=null 写成已启用');
  // I-2：模式面板对固定主控的全部依赖已解除——以下符号在代码块中不得存在
  for (const gone of ['controllerModeControllerState', 'controllerModeUnavailableReason', 'controllerModeAvailabilityNote', 'controllerStatusMeta', 'controllerId', 'controllerStatus']) {
    assert.ok(!modeBlock.includes(gone), `已退役依赖不得残留: ${gone}`);
  }
});
