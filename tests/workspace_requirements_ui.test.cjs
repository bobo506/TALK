// REQ-2 角色页项目级“开发要求”编辑区：状态/DOM 异步测试。
// 通过 vm 抽取 workspace.js 中 REQ-2 代码块，用 DOM 存根验证 项目/账号/请求序号 绑定、
// 迟到响应丢弃、保存中继续编辑、清空、旧后端兼容、emoji 长度与错误分支。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');

const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const workspaceSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const blockStart = workspaceSource.indexOf('const REQUIREMENTS_MAX_CHARS');
const blockEnd = workspaceSource.indexOf('function renderWorkspaceList()');
assert.ok(blockStart > 0 && blockEnd > blockStart, 'REQ-2 代码块边界');
const requirementsBlock = workspaceSource.slice(blockStart, blockEnd);

function fakeEl(id) {
  const classes = new Set(id === 'requirements-panel' ? [] : []);
  return {
    id, value: '', textContent: '', className: '', disabled: false, readOnly: false,
    classList: {
      add: c => classes.add(c),
      remove: c => classes.delete(c),
      toggle: (c, force) => { const on = force === undefined ? !classes.has(c) : force; on ? classes.add(c) : classes.delete(c); },
      contains: c => classes.has(c),
    },
    addEventListener() {},
  };
}

function harness({ human = true } = {}) {
  const pending = [];
  const elements = new Map();
  const document = { getElementById: id => { if (!elements.has(id)) elements.set(id, fakeEl(id)); return elements.get(id); } };
  const context = vm.createContext({
    workspaceUI: { mode: 'roles' }, blackboardOpen: true,
    activeProjectId: 'A', myId: 'human:qa',
    // ROLE-SETTINGS-1：REQ-2 代码块只在“项目设置”选中时可见；本 harness 默认停留在项目设置页。
    workspaceSettingsSelected: () => true,
    projects: [{ project_id: 'A', development_requirements: null }, { project_id: 'B', development_requirements: null }],
    currentMemberIsHuman: () => human,
    apiFetch: (url, opts) => new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject })),
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    document,
  });
  vm.runInContext(requirementsBlock, context);
  // const 声明不挂到 context 对象，显式暴露引用便于断言。
  vm.runInContext('this.__ui = requirementsUI; this.__drafts = requirementsDrafts;', context);
  const ui = context.__ui, drafts = context.__drafts;
  const el = id => document.getElementById(id);
  const reply = (index, data, { ok = true, status = 200 } = {}) =>
    pending[index].resolve({ ok, status, json: async () => data });
  const fail = (index, err) => pending[index].reject(err);
  async function load(project = 'A', value = null) {
    context.activeProjectId = project;
    const request = context.renderRequirementsPanel();
    const index = pending.length - 1;
    reply(index, { project_id: project, development_requirements: value });
    await request;
  }
  return { context, pending, reply, fail, el, ui, drafts, load };
}

test('字符数按 Unicode 码点计数，与后端 Python len 对齐（含 emoji/中文/换行）', () => {
  assert.equal(helpers.workspaceRequirementsLength('a😀b'), 3);
  assert.equal(helpers.workspaceRequirementsLength('中文\n换行'), 5);
  assert.equal(helpers.workspaceRequirementsLength('😀'.repeat(20000)), 20000);
  assert.equal(helpers.workspaceRequirementsLength('😀'.repeat(20001)), 20001);
  assert.equal(helpers.normalizeRequirementsValue(null), null);
  assert.equal(helpers.normalizeRequirementsValue('   \n\t '), null);
  assert.equal(helpers.normalizeRequirementsValue(' x '), ' x ');
  assert.equal(helpers.normalizeRequirementsValue('中文\n要求'), '中文\n要求');
});

test('角色页展示当前服务端值并同步项目缓存；无内容时为空', async () => {
  const { el, ui, context, load } = harness();
  await load('A', 'Kimi 负责前端\nDeepSeek 负责后端');
  assert.equal(el('requirements-panel').classList.contains('hidden'), false);
  assert.equal(el('requirements-input').value, 'Kimi 负责前端\nDeepSeek 负责后端');
  assert.equal(ui.saved, 'Kimi 负责前端\nDeepSeek 负责后端');
  assert.equal(context.projects[0].development_requirements, 'Kimi 负责前端\nDeepSeek 负责后端');
  assert.match(el('requirements-status').textContent, /与服务端一致/);
});

test('无项目或未登录时面板隐藏且不发起请求', () => {
  const { context, pending, el } = harness();
  context.activeProjectId = null;
  context.renderRequirementsPanel();
  assert.equal(el('requirements-panel').classList.contains('hidden'), true);
  assert.equal(pending.length, 0);
});

test('同项目重复重绘（轮询/切换角色）不重发请求、不覆盖未保存文本', async () => {
  const { context, pending, el, load } = harness();
  await load('A', '旧要求');
  el('requirements-input').value = '未保存草稿';
  context.recordRequirementsDraft();
  const before = pending.length;
  context.renderRequirementsPanel();
  context.renderRequirementsPanel();
  assert.equal(pending.length, before);
  assert.equal(el('requirements-input').value, '未保存草稿');
});

test('A→B→A 往返后早期响应被丢弃，只应用最新一次读取', async () => {
  const { context, pending, reply, ui, el } = harness();
  context.renderRequirementsPanel();          // A 第一次读取
  context.activeProjectId = 'B';
  context.renderRequirementsPanel();          // B 读取
  context.activeProjectId = 'A';
  const last = context.renderRequirementsPanel(); // A 第二次读取
  assert.equal(pending.length, 3);
  reply(2, { project_id: 'A', development_requirements: 'A 最新' });
  await last;
  reply(0, { project_id: 'A', development_requirements: 'A 旧迟到' });
  reply(1, { project_id: 'B', development_requirements: 'B 迟到' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(ui.saved, 'A 最新');
  assert.equal(el('requirements-input').value, 'A 最新');
});

test('读取 URL 绑定发起时项目，切换账号后旧响应失效', async () => {
  const { context, pending, reply, ui } = harness();
  context.renderRequirementsPanel();
  assert.match(pending[0].url, /\/api\/projects\/A$/);
  context.myId = 'human:other';
  context.renderRequirementsPanel();
  assert.match(pending[1].url, /\/api\/projects\/A$/);
  reply(0, { project_id: 'A', development_requirements: '旧账号响应' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(ui.saved, null);
  assert.equal(ui.memberId, 'human:other');
});

test('旧后端响应缺少字段：提示不支持并禁用保存，不发送 PATCH', async () => {
  const { context, pending, reply, el, ui } = harness();
  const request = context.renderRequirementsPanel();
  reply(0, { project_id: 'A' }); // 旧后端没有 development_requirements
  await request;
  assert.equal(ui.supported, false);
  assert.match(el('requirements-status').textContent, /尚未支持/);
  assert.equal(el('requirements-input').disabled, true);
  assert.equal(el('requirements-save-btn').disabled, true);
  el('requirements-input').value = '尝试保存';
  await context.saveProjectRequirements();
  assert.equal(pending.length, 1); // 没有发出 PATCH
});

test('保存成功：核实同项目+字段+值一致，清空草稿并同步缓存', async () => {
  const { context, pending, reply, el, ui, drafts, load } = harness();
  await load('A', '旧要求');
  el('requirements-input').value = '新要求';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  assert.equal(pending.at(-1).opts.method, 'PATCH');
  assert.match(pending.at(-1).url, /\/api\/projects\/A$/);
  assert.deepEqual(JSON.parse(pending.at(-1).opts.body), { development_requirements: '新要求' });
  assert.match(el('requirements-status').textContent, /正在保存/);
  reply(pending.length - 1, { project_id: 'A', development_requirements: '新要求' });
  await saving;
  assert.equal(ui.saved, '新要求');
  assert.equal(ui.saving, false);
  assert.equal(drafts.has('human:qa/A'), false);
  assert.equal(context.projects[0].development_requirements, '新要求');
  assert.match(el('requirements-status').textContent, /已保存/);
});

test('保存期间继续编辑：迟到响应不覆盖新草稿、不误标已保存', async () => {
  const { context, pending, reply, el, ui, drafts, load } = harness();
  await load('A', '旧要求');
  el('requirements-input').value = '第二版';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  el('requirements-input').value = '第三版（保存中继续编辑）';
  context.recordRequirementsDraft();
  reply(pending.length - 1, { project_id: 'A', development_requirements: '第二版' });
  await saving;
  assert.equal(ui.saved, '第二版');
  assert.equal(el('requirements-input').value, '第三版（保存中继续编辑）');
  assert.equal(drafts.get('human:qa/A'), '第三版（保存中继续编辑）');
  assert.match(el('requirements-status').textContent, /仍有未保存的修改/);
  assert.equal(el('requirements-save-btn').disabled, false); // 新草稿可再次保存
});

test('保存响应缺字段或值不一致：不报成功，保留草稿', async () => {
  for (const body of [{ project_id: 'A' }, { project_id: 'A', development_requirements: '被改写' }, { project_id: 'B', development_requirements: '新要求' }]) {
    const { context, pending, reply, el, ui, drafts, load } = harness();
    await load('A', null);
    el('requirements-input').value = '新要求';
    context.recordRequirementsDraft();
    const saving = context.saveProjectRequirements();
    reply(pending.length - 1, body);
    await saving;
    assert.equal(ui.saved, null);
    assert.equal(drafts.get('human:qa/A'), '新要求');
    assert.equal(el('requirements-input').value, '新要求');
    assert.match(el('requirements-status').textContent, /未确认本次保存/);
  }
});

test('清空内容后显式保存：提交原文，服务端归一为 null 视为成功', async () => {
  const { context, pending, reply, el, ui, load } = harness();
  await load('A', '有内容');
  el('requirements-input').value = '   ';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  assert.deepEqual(JSON.parse(pending.at(-1).opts.body), { development_requirements: '   ' });
  reply(pending.length - 1, { project_id: 'A', development_requirements: null });
  await saving;
  assert.equal(ui.saved, null);
  assert.equal(el('requirements-input').value, ''); // 全空白提交归一为空文本
  assert.match(el('requirements-status').textContent, /已保存/);
});

test('401/403/404/422/网络失败：保留草稿、可重试、不假成功', async () => {
  for (const [status, detail] of [[401, 'invalid api key'], [403, 'only human members can manage projects'], [404, 'project not found'], [422, 'development_requirements must be at most 20000 characters']]) {
    const { context, pending, reply, el, ui, drafts, load } = harness();
    await load('A', '旧要求');
    el('requirements-input').value = '草稿';
    context.recordRequirementsDraft();
    const saving = context.saveProjectRequirements();
    reply(pending.length - 1, { detail }, { ok: false, status });
    await saving;
    assert.equal(ui.saved, '旧要求');
    assert.equal(ui.saving, false);
    assert.equal(drafts.get('human:qa/A'), '草稿');
    assert.equal(el('requirements-input').value, '草稿');
    assert.equal(el('requirements-status').textContent, detail);
    assert.equal(el('requirements-save-btn').disabled, false); // 允许重试
  }
  const { context, pending, fail, el, ui, drafts, load } = harness();
  await load('A', '旧要求');
  el('requirements-input').value = '草稿';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  fail(pending.length - 1, new Error('network down'));
  await saving;
  assert.equal(ui.saved, '旧要求');
  assert.equal(drafts.get('human:qa/A'), '草稿');
  assert.match(el('requirements-status').textContent, /network down/);
});

test('读取失败显示错误与重试按钮，重试成功后恢复可编辑', async () => {
  const { context, pending, reply, el, ui } = harness();
  const request = context.renderRequirementsPanel();
  reply(0, { detail: 'project not found' }, { ok: false, status: 404 });
  await request;
  assert.match(el('requirements-status').textContent, /project not found/);
  assert.equal(el('requirements-retry-btn').classList.contains('hidden'), false);
  assert.equal(el('requirements-input').disabled, true);
  const retry = context.loadProjectRequirements();
  reply(1, { project_id: 'A', development_requirements: '恢复内容' });
  await retry;
  assert.equal(ui.saved, '恢复内容');
  assert.equal(el('requirements-input').value, '恢复内容');
  assert.equal(el('requirements-input').disabled, false);
  assert.equal(el('requirements-retry-btn').classList.contains('hidden'), true);
});

test('超过 20000 字符前端阻止保存（不误拒恰好 20000）', async () => {
  const { context, pending, el, load } = harness();
  await load('A', null);
  el('requirements-input').value = '好'.repeat(20000) + '😀';
  context.recordRequirementsDraft();
  await context.saveProjectRequirements();
  assert.equal(pending.length, 1); // 只有读取请求，没有 PATCH
  assert.equal(el('requirements-save-btn').disabled, true);
  assert.match(el('requirements-status').textContent, /超出 20000 字符上限/);
  assert.match(el('requirements-count').textContent, /20001 \/ 20000/);
  el('requirements-input').value = '好'.repeat(20000);
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  assert.equal(pending.length, 2);
  assert.equal(el('requirements-save-btn').disabled, true); // 保存中防重复提交
  assert.equal(pending.at(-1).opts.method, 'PATCH');
});

test('放弃修改恢复已保存内容并清除草稿', async () => {
  const { context, el, ui, drafts, load } = harness();
  await load('A', '服务端内容');
  el('requirements-input').value = '不要的草稿';
  context.recordRequirementsDraft();
  assert.equal(drafts.has('human:qa/A'), true);
  context.discardProjectRequirements();
  assert.equal(el('requirements-input').value, '服务端内容');
  assert.equal(drafts.has('human:qa/A'), false);
  assert.match(el('requirements-status').textContent, /已恢复为已保存的内容/);
});

test('切换项目再返回：内存草稿按账号+项目恢复，不污染其它项目', async () => {
  const { context, pending, reply, el, load } = harness();
  await load('A', 'A 已保存');
  el('requirements-input').value = 'A 的草稿';
  context.recordRequirementsDraft();
  await load('B', 'B 已保存');
  assert.equal(el('requirements-input').value, 'B 已保存');
  // 返回 A：先立即展示草稿，读取完成后草稿与服务端值不同则保留。
  context.activeProjectId = 'A';
  const back = context.renderRequirementsPanel();
  assert.equal(el('requirements-input').value, 'A 的草稿');
  reply(pending.length - 1, { project_id: 'A', development_requirements: 'A 已保存' });
  await back;
  assert.equal(el('requirements-input').value, 'A 的草稿');
  assert.match(el('requirements-status').textContent, /未保存/);
  // 另一账号登录同项目不看到这份草稿。
  context.myId = 'human:other';
  context.renderRequirementsPanel();
  assert.equal(el('requirements-input').value, '');
});

test('Agent 账号只读：文本框只读、保存按钮禁用', async () => {
  const { context, pending, el, load } = harness({ human: false });
  context.myId = 'agent:kimi';
  await load('A', '项目要求');
  assert.equal(el('requirements-input').readOnly, true);
  assert.equal(el('requirements-save-btn').disabled, true);
  assert.match(el('requirements-status').textContent, /只能查看/);
  el('requirements-input').value = '试图修改';
  context.recordRequirementsDraft();
  await context.saveProjectRequirements();
  assert.equal(pending.length, 1); // 未发出 PATCH
});

test('重复提交防护：保存中再次触发保存不发出第二个请求', async () => {
  const { context, pending, reply, el, ui, load } = harness();
  await load('A', null);
  el('requirements-input').value = '内容';
  context.recordRequirementsDraft();
  const first = context.saveProjectRequirements();
  const second = context.saveProjectRequirements();
  assert.equal(pending.length, 2); // 读取 + 一次 PATCH
  reply(pending.length - 1, { project_id: 'A', development_requirements: '内容' });
  await first; await second;
  assert.equal(ui.saved, '内容');
});

// ── R2 返工：空白判空按 Python str.isspace 合同（与真实后端 .tmp/req-2/probe_boundary.py 对齐） ──
test('R2 判空集合按 Python str.isspace：U+001C/U+0085 归 null，U+FEFF/U+200B 不算空白', () => {
  const n = helpers.normalizeRequirementsValue;
  // Python 视为空白、JS trim 漏算的：归一为 null
  assert.equal(n('\u001c'), null);
  assert.equal(n('\u001c\u001d\u001e\u001f'), null);
  assert.equal(n('\u0085'), null);
  assert.equal(n('\u0085\u001c'), null);
  // 双方都视为空白的集合不回归
  assert.equal(n('\t\n\r\v\f '), null);
  assert.equal(n('\u00a0\u1680\u2000\u200a\u2028\u2029\u202f\u205f\u3000'), null);
  // JS trim 多算、Python 不算的：保留原文
  assert.equal(n('\ufeff'), '\ufeff');
  // 双方都不算空白：保留原文
  assert.equal(n('\u200b'), '\u200b');
  // 含非空白字符：整体原文保留，不 trim
  assert.equal(n('a\u001cb'), 'a\u001cb');
  assert.equal(n('  保留首尾空格  '), '  保留首尾空格  ');
});

test('R2 保存判定：U+001C 全空白提交，服务端归 null 视为成功（不再误报失败）', async () => {
  const { context, pending, reply, el, ui, load } = harness();
  await load('A', '旧内容');
  el('requirements-input').value = '\u001c';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  // 提交原文（不 trim），由服务端归一
  assert.deepEqual(JSON.parse(pending.at(-1).opts.body), { development_requirements: '\u001c' });
  reply(pending.length - 1, { project_id: 'A', development_requirements: null });
  await saving;
  assert.equal(ui.saved, null);
  assert.equal(ui.error, '');
  assert.equal(el('requirements-input').value, ''); // 归一后同步为空文本
  assert.match(el('requirements-status').textContent, /已保存/);
});

test('R2 保存判定：U+FEFF 服务端原文保留，前端核实一致认成功', async () => {
  const { context, pending, reply, el, ui, load } = harness();
  await load('A', null);
  el('requirements-input').value = '\ufeff';
  context.recordRequirementsDraft();
  const saving = context.saveProjectRequirements();
  reply(pending.length - 1, { project_id: 'A', development_requirements: '\ufeff' });
  await saving;
  assert.equal(ui.saved, '\ufeff');
  assert.equal(ui.error, '');
  assert.equal(el('requirements-input').value, '\ufeff');
  assert.match(el('requirements-status').textContent, /已保存/);
  // 已对齐服务端值，不再误标脏状态
  assert.equal(el('requirements-save-btn').disabled, true);
});

test('R2 清空/放弃/脏状态边界：Python 空白输入可保存可放弃，FEFF 保留脏判定', async () => {
  const { context, el, drafts, load } = harness();
  await load('A', null);
  // saved=null：U+001C 输入与空文本不同 → 脏，允许显式保存交由后端归一
  el('requirements-input').value = '\u001c';
  context.recordRequirementsDraft();
  assert.equal(el('requirements-save-btn').disabled, false);
  assert.match(el('requirements-status').textContent, /未保存/);
  // 放弃修改：恢复已保存值（空文本）并清草稿
  context.discardProjectRequirements();
  assert.equal(el('requirements-input').value, '');
  assert.equal(drafts.has('human:qa/A'), false);
  assert.match(el('requirements-status').textContent, /已恢复为已保存的内容/);
  assert.equal(el('requirements-save-btn').disabled, true); // 不脏不可保存
  // U+FEFF 归一后非 null，与服务端 null 不同 → 脏且可保存
  el('requirements-input').value = '\ufeff';
  context.recordRequirementsDraft();
  assert.equal(el('requirements-save-btn').disabled, false);
  assert.equal(drafts.get('human:qa/A'), '\ufeff');
});
