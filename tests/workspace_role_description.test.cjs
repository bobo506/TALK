// ROLE-DESC-F1：角色说明前端编辑（静态 DOM 方案 A）的交互测试。
// 在 vm 中加载整份真实 web/workspace.js（含真实 renderWorkspaceList/renderWorkspaceRoleDetails/
// renderRoleDescriptionPanel 与顶部事件绑定），renderTaskDetailsPanel 桩按 app.js 真实顺序调用
// 四个真实面板函数。断言直接读 textarea.value 与节点对象身份（fake DOM focus 是空实现，
// 真实焦点/光标行为留用户页面验收，见 design §3.9 测试盲区）。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');
const helpers = require('../web/workspace.js');

function fakeEl(tag) {
  const classes = new Set();
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '', disabled: false, readOnly: false,
    dataset: {}, attrs: {}, children: [], listeners: {},
    classList: {
      add(...cs) { cs.forEach(c => classes.add(c)); },
      remove(...cs) { cs.forEach(c => classes.delete(c)); },
      toggle(c, force) { const on = force === undefined ? !classes.has(c) : !!force; on ? classes.add(c) : classes.delete(c); return on; },
      contains(c) { return classes.has(c); },
    },
    appendChild(c) { el.children.push(c); return c; },
    append(...cs) { el.children.push(...cs); },
    replaceChildren() { el.children.length = 0; },
    insertBefore(node) { el.children.push(node); return node; },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    addEventListener(type, fn) { (el.listeners[type] ||= []).push(fn); },
    fire(type, event = {}) { for (const fn of el.listeners[type] || []) fn(event); },
    focus() {},
    scrollIntoView() {},
    querySelectorAll: () => [],
  };
  Object.defineProperty(el, 'lastChild', { get: () => el.children[el.children.length - 1] || null });
  Object.defineProperty(el, 'childElementCount', { get: () => el.children.length });
  return el;
}
function allTexts(node, out = []) {
  if (node.textContent) out.push(node.textContent);
  for (const c of node.children) allTexts(c, out);
  return out;
}
function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  for (const c of node.children) findAll(c, pred, out);
  return out;
}

const EXEC_LABEL = '执行工作';
const EXEC_DESC = '负责执行分配的工作、提交完成结果，并交叉验证其他角色的成果。';
const KIMI_DEFAULT = `执行工作\n${EXEC_DESC}`; // reviewer 默认
const MEMBERS = [
  { id: 'human:qa', kind: 'human', display_name: 'bobo' },
  { id: 'agent:kimi', kind: 'agent', display_name: 'Kimi' },
  { id: 'agent:deepseek', kind: 'agent', display_name: 'DeepSeek' },
  { id: 'agent:ui', kind: 'agent', display_name: 'UI' },
];
// deepseek 自带自定义说明，用于区分上下文切换与迟到响应；ui 无解释映射（默认只留标签行）。
const ROSTER = [
  { member_id: 'agent:kimi', business_role: 'reviewer', role_description: null },
  { member_id: 'agent:deepseek', business_role: 'dev', role_description: '深度自定义说明\n第二行保留' },
  { member_id: 'agent:ui', business_role: 'ui', role_description: null },
];

function harness({ human = true, roster = ROSTER } = {}) {
  const pending = [];
  const elements = new Map();
  const getEl = id => {
    if (!elements.has(id)) { const node = fakeEl('div'); node.id = id; elements.set(id, node); }
    return elements.get(id);
  };
  const workbench = fakeEl('div');
  const documentStub = {
    getElementById: getEl,
    createElement: tag => fakeEl(tag),
    createTextNode: text => ({ textContent: text }),
    querySelector: sel => (sel === '.workbench' ? workbench : null),
    activeElement: null,
    body: fakeEl('body'),
  };
  const context = vm.createContext({
    document: documentStub,
    blackboardOpen: true,
    activeProjectId: 'A',
    activeGroupId: null,
    myId: human ? 'human:qa' : 'agent:kimi',
    members: MEMBERS,
    projectAgents: roster.map(item => ({ ...item })),
    projectTasks: [],
    groups: [],
    projects: [{ project_id: 'A' }],
    currentMemberIsHuman: () => human,
    apiFetch: (url, opts) => new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject })),
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    // app.js 侧函数：本切片不涉及的用桩，面板同步按真实顺序调用真实函数。
    taskStatusMeta: () => ({ label: '执行中', className: 'running' }),
    formatTaskTime: () => '10-05 10:00',
    selectWorkspaceTask: () => {},
    getActiveGroup: () => null,
    canEnterGroup: () => false,
    setActiveGroup: () => {},
    renderRoomStrip: () => {},
    renderProjectStrip: () => {},
    renderGroupMembersPanel: () => {},
    setGroupCreateOpen: () => {},
    showComposerStatus: () => {},
    loadHistory: () => {},
    loadSelectedTaskTree: async () => {},
    setBlackboardOpen: () => {},
    renderWorkspaceMode: () => {},
    selectedTaskTree: null,
    taskTreeRequest: 0,
    activeProjectStorageKey: () => 'active-project:test',
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: { matchMedia: () => ({ matches: false }) },
    blackboardTitle: getEl('blackboard-title'),
    blackboardDescription: getEl('blackboard-description'),
    blackboardColumns: getEl('blackboard-columns'),
    blackboardSummary: getEl('blackboard-summary'),
    blackboardEmpty: getEl('blackboard-empty'),
    userBadge: getEl('user-badge'),
  });
  // renderTaskDetailsPanel 桩按 app.js 真实顺序调用四个真实面板同步函数。
  context.renderTaskDetailsPanel = () => {
    context.renderWorkspaceRoleDetails();
    context.renderRequirementsPanel();
    context.renderControllerModePanel();
    context.renderRoleDescriptionPanel();
  };
  vm.runInContext(wsSource, context);
  vm.runInContext('this.__wsui = workspaceUI; this.__rdui = roleDescriptionUI; this.__drafts = roleDescriptionDrafts;', context);
  const el = getEl;
  const reply = (index, data, { ok = true, status = 200 } = {}) =>
    pending[index].resolve({ ok, status, json: async () => data });
  const flush = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setTimeout(r, 0)); };
  const hidden = id => el(id).classList.contains('hidden');
  const enterRoles = async () => {
    el('workspace-roles-btn').fire('click');
    context.renderWorkspaceList();
    context.renderTaskDetailsPanel();
    await flush();
  };
  const rows = () => el('blackboard-columns').children;
  const roleRow = memberId => rows().find(row => !row.className.includes('role-settings-row') && allTexts(row).includes(memberId));
  const selectRole = async memberId => { roleRow(memberId).fire('click'); await flush(); };
  const puts = () => pending.map((p, i) => ({ ...p, index: i })).filter(p => p.opts?.method === 'PUT');
  const input = () => el('role-description-input');
  const status = () => el('role-description-status').textContent;
  return { context, ui: context.__wsui, rdui: context.__rdui, drafts: context.__drafts, pending, reply, flush, hidden, el, enterRoles, rows, roleRow, selectRole, puts, input, status };
}

test('默认文案生成器与有效说明/摘要/归一化纯函数', () => {
  assert.equal(helpers.workspaceRoleDefaultDescription('lead'), '统筹任务\n负责分配工作、跟进进度，并汇总最终成果。');
  assert.equal(helpers.workspaceRoleDefaultDescription('ui'), '界面设计'); // 无解释映射只留标签行
  assert.equal(helpers.workspaceRoleDefaultDescription('custom-role'), 'custom-role');
  // 无自定义 → 默认；有自定义（含空行开头）→ 自定义，不回退硬编码
  assert.equal(helpers.workspaceRoleDescriptionText({ business_role: 'lead' }), '统筹任务\n负责分配工作、跟进进度，并汇总最终成果。');
  assert.equal(helpers.workspaceRoleDescriptionText({ business_role: 'lead', role_description: '\n\n自定义\n尾部' }), '\n\n自定义\n尾部');
  assert.equal(helpers.workspaceRoleSummary({ business_role: 'lead' }), '统筹任务');
  assert.equal(helpers.workspaceRoleSummary({ business_role: 'lead', role_description: '\n\n自定义\n尾部' }), '自定义');
  // 归一化复用 Python str.isspace 空白集合：U+001C–1F/U+0085/U+3000 全空白归 null
  assert.equal(helpers.normalizeRoleDescriptionValue('     '), null);
  assert.equal(helpers.normalizeRoleDescriptionValue(' \u001c\u001f\u0085\u3000 '), null);
  assert.equal(helpers.normalizeRoleDescriptionValue(''), null);
  assert.equal(helpers.normalizeRoleDescriptionValue(null), null);
  // U+FEFF 不在 Python 空白集合内：单独存在时是非空白原文，不得被当空白归 null（JS trim 会误判）
  assert.equal(helpers.normalizeRoleDescriptionValue('\ufeff'), '\ufeff');
  assert.equal(helpers.normalizeRoleDescriptionValue(' 正文 \n'), ' 正文 \n');
  // 摘要同样不得把 U+FEFF 自定义值误回退硬编码
  assert.equal(helpers.workspaceRoleSummary({ business_role: 'lead', role_description: '\ufeff' }), '\ufeff');
  assert.equal(helpers.ROLE_DESCRIPTION_MAX_CHARS, 2000);
});

test('human 选中角色：静态面板显示、默认文案预填 textarea.value，详情面板不再渲染硬编码行', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  assert.equal(h.hidden('role-description-panel'), false);
  assert.equal(h.input().value, KIMI_DEFAULT);
  assert.equal(h.input().readOnly, false);
  assert.equal(h.el('role-description-count').textContent, `${[...KIMI_DEFAULT].length} / 2000 字符`);
  assert.equal(h.el('role-description-save').disabled, true, '未修改时不可保存');
  assert.match(h.status(), /默认说明/);
  // 动态角色详情面板（名称区 + 参与任务区）不再出现硬编码标签/解释（移到静态编辑区）
  const texts = [...allTexts(h.el('role-details-name-panel')), ...allTexts(h.el('role-details-tasks-panel'))];
  assert.ok(!texts.includes(EXEC_LABEL));
  assert.ok(!texts.includes(EXEC_DESC));
  // 已自定义角色预填自定义原文（含换行），不渲染默认
  await h.selectRole('agent:deepseek');
  assert.equal(h.input().value, '深度自定义说明\n第二行保留');
});

test('编辑期间任务变化/轮询重绘：textarea 节点身份与内容保持，列表行不被说明区牵连', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  const before = h.input();
  before.value = '未保存草稿 v1';
  before.fire('input');
  const panelNode = h.el('role-description-panel');
  // 模拟 5 秒轮询/任务数据变化触发的多轮重绘（真实 renderTaskDetailsPanel 调用链）
  for (let i = 0; i < 5; i++) {
    h.context.renderWorkspaceList();
    h.context.renderTaskDetailsPanel();
    await h.flush();
  }
  assert.equal(h.input(), before, 'textarea 仍是同一节点，未被销毁重建');
  assert.equal(h.el('role-description-panel'), panelNode, '静态面板节点身份保持');
  assert.equal(h.input().value, '未保存草稿 v1', '草稿内容不被轮询覆盖');
  assert.match(h.status(), /未保存/);
  // 动态名称区/任务区照常重建（子节点被 replaceChildren 刷新），说明区不受影响
  assert.ok(h.el('role-details-tasks-panel').children.length > 0, '参与任务区仍正常渲染');
  assert.ok(h.el('role-details-name-panel').children.length > 0, '名称区仍正常渲染');
  assert.ok(h.el('role-details-tasks-panel').children.every(c => c !== before), '编辑区不在动态任务区内');
  assert.ok(h.el('role-details-name-panel').children.every(c => c !== before), '编辑区不在动态名称区内');
});

test('草稿按 账号/项目/成员 隔离：同项目切角色不覆盖，往返恢复', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = 'kimi 未保存草稿';
  h.input().fire('input');
  // 切到 deepseek：显示其自定义说明，不被 kimi 草稿污染
  await h.selectRole('agent:deepseek');
  assert.equal(h.input().value, '深度自定义说明\n第二行保留');
  // 再切 ui：无解释映射角色默认只留标签行
  await h.selectRole('agent:ui');
  assert.equal(h.input().value, '界面设计');
  // 切回 kimi：草稿恢复并提示
  await h.selectRole('agent:kimi');
  assert.equal(h.input().value, 'kimi 未保存草稿');
  assert.match(h.status(), /已恢复上次未保存的草稿/);
  assert.ok(h.drafts.has('human:qa/A/agent:kimi'), '草稿 key 按 账号/项目/成员 隔离');
  assert.ok(!h.drafts.has('human:qa/A/agent:deepseek'));
});

test('human 保存自定义说明：PUT 合同、缓存更新、列表摘要显式重绘、草稿清除', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = '前端与复核\n负责交互实现';
  h.input().fire('input');
  assert.equal(h.el('role-description-save').disabled, false);
  h.el('role-description-save').fire('click');
  const [put] = h.puts();
  assert.ok(put, '发起 PUT 请求');
  assert.equal(put.url, '/api/projects/A/agents/agent%3Akimi/description');
  assert.deepEqual(JSON.parse(put.opts.body), { description: '前端与复核\n负责交互实现' });
  await h.flush();
  assert.match(h.status(), /正在保存/);
  h.reply(put.index, {
    project_id: 'A', member_id: 'agent:kimi',
    description: '前端与复核\n负责交互实现', updated_at: '2026-10-05T01:00:00', updated_by: 'human:qa',
  });
  await h.flush();
  assert.match(h.status(), /已保存/);
  assert.equal(h.input().value, '前端与复核\n负责交互实现');
  // D2：projectAgents 缓存核实后立即更新，列表摘要显式重绘为首个非空行
  assert.equal(h.context.projectAgents.find(a => a.member_id === 'agent:kimi').role_description, '前端与复核\n负责交互实现');
  assert.equal(h.roleRow('agent:kimi').children[1].textContent, '前端与复核');
  assert.ok(!h.drafts.has('human:qa/A/agent:kimi'), '保存成功后草稿清除');
  assert.equal(h.el('role-description-save').disabled, true, '内容与服务端一致后不可重复保存');
});

test('保存中继续输入：迟到成功响应只认提交时文本，新草稿保留且不误标已保存', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = '提交版本 v1';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  const [put] = h.puts();
  // 保存进行中继续输入
  h.input().value = '提交后又改了 v2';
  h.input().fire('input');
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: '提交版本 v1', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  assert.equal(h.rdui.saved, '提交版本 v1');
  assert.equal(h.context.projectAgents.find(a => a.member_id === 'agent:kimi').role_description, '提交版本 v1');
  assert.equal(h.input().value, '提交后又改了 v2', '新草稿不被响应覆盖');
  assert.equal(h.drafts.get('human:qa/A/agent:kimi'), '提交后又改了 v2');
  assert.match(h.status(), /先前内容已保存；当前仍有未保存的修改/);
  assert.equal(h.el('role-description-save').disabled, false, '新草稿仍可保存');
});

test('迟到响应：保存中切换角色后旧响应不回填、不写缓存、不报错', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = 'kimi 新说明';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  const [put] = h.puts();
  // 响应未回就切到 deepseek：上下文切换递增请求序号，作废旧保存
  await h.selectRole('agent:deepseek');
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: 'kimi 新说明', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  assert.equal(h.context.projectAgents.find(a => a.member_id === 'agent:kimi').role_description, null, '迟到响应不写名册缓存');
  assert.equal(h.input().value, '深度自定义说明\n第二行保留', '迟到响应不回填新上下文');
  assert.equal(h.rdui.saved, '深度自定义说明\n第二行保留');
  assert.ok(!/未确认|失败/.test(h.status()), '迟到响应静默丢弃，不误报错误');
});

test('全空白（Python isspace 集合）与等于默认提交 null 恢复默认；U+FEFF 按非空白原文保存', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  // U+001C/U+001F/U+0085/U+3000 全空白 → null
  h.input().value = ' \u001c\u001f\u0085\u3000 ';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  let [put] = h.puts();
  assert.deepEqual(JSON.parse(put.opts.body), { description: null });
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: null, updated_at: null, updated_by: null });
  await h.flush();
  assert.equal(h.rdui.saved, null);
  assert.equal(h.input().value, KIMI_DEFAULT, '空白恢复默认后编辑区同步回默认文案');
  assert.match(h.status(), /已恢复默认说明/);
  // 等于默认文案逐字相等 → 不脏，不可保存
  assert.equal(h.el('role-description-save').disabled, true);
  // 已有自定义时填回默认 → 提交 null（不落库默认副本）
  h.input().value = '先有自定义';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: '先有自定义', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  h.input().value = KIMI_DEFAULT;
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  assert.deepEqual(JSON.parse(put.opts.body), { description: null }, '等于默认文案时提交 null');
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: null, updated_at: null, updated_by: null });
  await h.flush();
  // U+FEFF 单独存在：非空白，按原文保存（前后端同一空白集合，不分叉）
  h.input().value = '\ufeff';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  assert.deepEqual(JSON.parse(put.opts.body), { description: '\ufeff' });
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: '\ufeff', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  assert.equal(h.roleRow('agent:kimi').children[1].textContent, '\ufeff', '合法自定义值不误回退硬编码');
});

test('恢复默认按钮：填回默认文案并提交 null', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:deepseek'); // 已有自定义说明
  assert.equal(h.input().value, '深度自定义说明\n第二行保留');
  assert.equal(h.el('role-description-reset').disabled, false);
  h.el('role-description-reset').fire('click');
  const put = h.puts().at(-1);
  assert.deepEqual(JSON.parse(put.opts.body), { description: null });
  h.reply(put.index, { project_id: 'A', member_id: 'agent:deepseek', description: null, updated_at: null, updated_by: null });
  await h.flush();
  assert.equal(h.input().value, `执行工作\n${EXEC_DESC}`, '恢复默认后显示 dev 默认文案');
  assert.equal(h.context.projectAgents.find(a => a.member_id === 'agent:deepseek').role_description, null);
  assert.equal(h.roleRow('agent:deepseek').children[1].textContent, EXEC_LABEL, '列表摘要回到默认短标签');
});

test('2000 码点上限：超限禁保存且不发起请求；emoji 按码点计数', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = '要'.repeat(2001);
  h.input().fire('input');
  assert.equal(h.el('role-description-save').disabled, true);
  assert.match(h.status(), /已超出 2000 字符上限/);
  assert.equal(h.el('role-description-count').textContent, '2001 / 2000 字符');
  const before = h.pending.length;
  h.el('role-description-save').fire('click');
  await h.flush();
  assert.equal(h.pending.length, before, '超限不发起请求');
  // 恰好 2000 码点（含 emoji 代理对按 1 码点计）可以保存
  h.input().value = '要'.repeat(1999) + '🙂';
  h.input().fire('input');
  assert.equal(h.el('role-description-count').textContent, '2000 / 2000 字符');
  assert.equal(h.el('role-description-save').disabled, false);
});

test('响应核实失败与请求失败：草稿保留、缓存不变、状态报错', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  // 响应描述与提交不一致 → 不认成功
  h.input().value = '核实失败草稿';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  let put = h.puts().at(-1);
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: '被篡改的值', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  assert.match(h.status(), /服务未确认本次保存/);
  assert.equal(h.context.projectAgents.find(a => a.member_id === 'agent:kimi').role_description, null, '核实失败不写缓存');
  assert.equal(h.input().value, '核实失败草稿', '草稿保留');
  assert.equal(h.drafts.get('human:qa/A/agent:kimi'), '核实失败草稿');
  // 500 失败 → 草稿保留、报错
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  h.reply(put.index, { detail: '数据库繁忙' }, { ok: false, status: 500 });
  await h.flush();
  assert.match(h.status(), /数据库繁忙/);
  assert.equal(h.input().value, '核实失败草稿');
  assert.equal(h.rdui.saving, false, '失败后保存状态解除，可重试');
});

test('agent 账号只读：textarea readOnly、编辑控件隐藏、状态明示', async () => {
  const h = harness({ human: false });
  await h.enterRoles();
  await h.selectRole('agent:deepseek');
  assert.equal(h.hidden('role-description-panel'), false);
  assert.equal(h.input().readOnly, true);
  assert.equal(h.input().disabled, false, 'N4：agent 只读态只 readOnly 不 disabled，文本可选中复制');
  assert.equal(h.input().value, '深度自定义说明\n第二行保留', 'agent 可读有效说明');
  for (const id of ['role-description-save', 'role-description-discard', 'role-description-reset']) {
    assert.equal(h.el(id).classList.contains('hidden'), true, `${id} 对 agent 隐藏`);
  }
  assert.match(h.status(), /只能查看/);
  // 即使触发保存处理器也不发请求
  h.input().value = 'agent 试图修改';
  const before = h.pending.length;
  h.el('role-description-save').fire('click');
  await h.flush();
  assert.equal(h.pending.length, before);
});

test('旧服务缺 role_description 字段：降级只读并提示，禁用保存（N4：只 readOnly 不 disabled，可复制）', async () => {
  const legacy = [
    { member_id: 'agent:kimi', business_role: 'reviewer' },
    { member_id: 'agent:deepseek', business_role: 'dev' },
  ];
  const h = harness({ roster: legacy });
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  assert.equal(h.hidden('role-description-panel'), false);
  assert.equal(h.input().value, KIMI_DEFAULT, '降级展示默认文案');
  // N4 修正：只读态用 readOnly 而非 disabled，文本可选中复制；保存按钮禁用（不可操作）
  assert.equal(h.input().readOnly, true);
  assert.equal(h.input().disabled, false);
  assert.equal(h.el('role-description-save').disabled, true);
  assert.equal(h.el('role-description-discard').disabled, true);
  assert.match(h.status(), /当前服务尚未支持保存角色说明/);
  const before = h.pending.length;
  h.el('role-description-save').fire('click');
  await h.flush();
  assert.equal(h.pending.length, before, '不支持时不发起 PUT');
});

test('列表摘要与搜索：首个非空行、说明全文与成员名/business_role 均可命中', async () => {
  const roster = [
    { member_id: 'agent:kimi', business_role: 'reviewer', role_description: '\n\n独立复核接口\n其余说明内容' },
    { member_id: 'agent:deepseek', business_role: 'dev', role_description: null },
    { member_id: 'agent:ui', business_role: 'ui', role_description: null },
  ];
  const h = harness({ roster });
  await h.enterRoles();
  // D1：以空行开头的自定义说明，摘要显示首个非空行而非空白格
  assert.equal(h.roleRow('agent:kimi').children[1].textContent, '独立复核接口');
  assert.equal(h.roleRow('agent:deepseek').children[1].textContent, EXEC_LABEL, '未自定义角色摘要无视觉回归');
  assert.equal(h.roleRow('agent:ui').children[1].textContent, '界面设计');
  const search = h.el('workspace-search');
  const visibleIds = () => h.rows().filter(r => r.className.includes('role-row') && !r.className.includes('role-settings-row')).map(r => r.children[0].textContent);
  search.value = '其余说明内容'; // 有效说明全文命中（非首行也能搜到）
  search.fire('input', { target: search });
  assert.deepEqual(visibleIds(), ['Kimi']);
  search.value = 'reviewer'; // 原始 business_role 命中
  search.fire('input', { target: search });
  assert.deepEqual(visibleIds(), ['Kimi']);
  search.value = 'deepseek'; // 成员名命中
  search.fire('input', { target: search });
  assert.deepEqual(visibleIds(), ['DeepSeek']);
  search.value = '统筹任务'; // 硬编码标签对 dev/ui 角色不再命中
  search.fire('input', { target: search });
  assert.deepEqual(visibleIds(), []);
});

test('放弃修改：回到已保存内容并清草稿', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:deepseek');
  h.input().value = '不想要的修改';
  h.input().fire('input');
  h.el('role-description-discard').fire('click');
  assert.equal(h.input().value, '深度自定义说明\n第二行保留');
  assert.ok(!h.drafts.has('human:qa/A/agent:deepseek'));
  assert.match(h.status(), /已恢复为已保存的内容/);
});

test('源码契约：说明区不经过 innerHTML，归一化复用空白集合，保存后显式重绘列表', () => {
  // 本切片涉及的安全/结构纪律在源码层兜底（HTML 同级结构由 Python 页面契约断言）
  const block = wsSource.slice(wsSource.indexOf('const ROLE_DESCRIPTION_MAX_CHARS'), wsSource.indexOf('function renderWorkspaceList()'));
  assert.ok(!block.includes('innerHTML'), 'ROLE-DESC-F1 区块无 innerHTML');
  assert.ok(block.includes('REQUIREMENTS_BLANK.test(text)'), '空白判定复用 Python isspace 集合');
  assert.ok(!/\.trim\(\)\s*===?\s*""/.test(block), '不以 JS trim 判空');
  assert.match(block, /method: "PUT"/);
  assert.match(block, /JSON\.stringify\(\{ description: normalized \}\)/);
  assert.match(block, /renderWorkspaceList\(\)/, '保存成功后显式重绘列表摘要');
  // N1：超限判定先归一化空白再查非空长度
  assert.ok(block.includes('normalizeRoleDescriptionValue(input.value) !== null && length > ROLE_DESCRIPTION_MAX_CHARS'), 'N1：超限先归一化空白');
  // N3：PUT 404 分支不再武断翻转 supported
  assert.ok(block.includes('/project not found/.test(detail)'), 'N3：project not found 独立分支');
  assert.ok(!/res\.status === 404[\s\S]*?supported = false/.test(block.slice(block.indexOf('res.status === 404'), block.indexOf('if (!res.ok)'))), 'N3：404 分支不翻转 supported');
  // N4：只读态只 readOnly 不 disabled
  assert.ok(block.includes('input.readOnly = !human || !ready;'), 'N4：agent/旧服务只 readOnly');
  assert.ok(!block.includes('input.disabled'), 'N4：说明编辑区不再使用 disabled');
  const appSource = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
  const detailsFn = appSource.slice(appSource.indexOf('function renderTaskDetailsPanel()'));
  assert.ok(detailsFn.indexOf('renderRoleDescriptionPanel()') > detailsFn.indexOf('renderControllerModePanel()'), 'app.js 同步点新增说明面板调用');
  // N5：测试桩 renderTaskDetailsPanel 的面板调用顺序与真实 app.js 一致
  // （I-2：固定主控面板已退役，同步点为调度模式面板）。
  const realCalls = [...detailsFn.slice(0, detailsFn.indexOf('getContextTask()')).matchAll(/\b(renderWorkspaceRoleDetails|renderRequirementsPanel|renderControllerModePanel|renderRoleDescriptionPanel)\(\);/g)].map(m => m[1]);
  assert.deepEqual(realCalls, ['renderWorkspaceRoleDetails', 'renderRequirementsPanel', 'renderControllerModePanel', 'renderRoleDescriptionPanel'], '真实 app.js 面板调用顺序');
  const stubSource = fs.readFileSync(__filename, 'utf8');
  const stubFn = stubSource.slice(stubSource.indexOf('context.renderTaskDetailsPanel = () => {'));
  const stubCalls = [...stubFn.slice(0, stubFn.indexOf('};')).matchAll(/\b(renderWorkspaceRoleDetails|renderRequirementsPanel|renderControllerModePanel|renderRoleDescriptionPanel)\(\);/g)].map(m => m[1]);
  assert.deepEqual(stubCalls, realCalls, '测试桩与真实 app.js 调用一致');
  assert.ok(!wsSource.includes('setInterval'), '不新增计时器/轮询');
});

test('N1：2001+ 个 U+3000 全空白不判超限——保存按钮可用，提交 null 恢复默认', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = '　'.repeat(2001); // 2001 个 U+3000
  h.input().fire('input');
  // 计数仍显示原始长度，但不报超限、不禁用保存（先归一化空白再判长度）
  assert.equal(h.el('role-description-count').textContent, '2001 / 2000 字符');
  assert.equal(h.el('role-description-count').classList.contains('over'), false, '全空白不标超限');
  assert.ok(!/已超出/.test(h.status()), '全空白不报超限提示');
  // 必须断言真实可用按钮（非绕开 disabled 直接调 handler）
  assert.equal(h.el('role-description-save').disabled, false, '全空白超长时保存按钮可用');
  h.el('role-description-save').fire('click');
  const put = h.puts().at(-1);
  assert.ok(put, '点击可用按钮后真实发起 PUT');
  assert.deepEqual(JSON.parse(put.opts.body), { description: null }, '全空白归一为 null');
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: null, updated_at: null, updated_by: null });
  await h.flush();
  assert.match(h.status(), /已恢复默认说明/);
  assert.equal(h.input().value, KIMI_DEFAULT);
  // 对照：非空白 2001 码点仍判超限禁保存
  h.input().value = '要'.repeat(2001);
  h.input().fire('input');
  assert.equal(h.el('role-description-save').disabled, true, '非空白超限仍禁保存');
  assert.match(h.status(), /已超出 2000 字符上限/);
});

test('N3：PUT 404 三分支——名册/项目不存在/普通 404 都不武断降级不支持，错误准确可重试', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  // ① 非名册 404：报错但编辑区仍可用，supported 不变
  h.input().value = '名册分支草稿';
  h.input().fire('input');
  h.el('role-description-save').fire('click');
  let put = h.puts().at(-1);
  h.reply(put.index, { detail: 'member agent:kimi is not in the project roster of project A' }, { ok: false, status: 404 });
  await h.flush();
  assert.match(h.status(), /不在项目名册中/);
  assert.equal(h.rdui.supported, true, '名册 404 不降级不支持');
  assert.equal(h.input().readOnly, false, '编辑区仍可用');
  assert.equal(h.input().value, '名册分支草稿', '草稿保留');
  // ② project not found 404：准确报错，不翻转 supported
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  assert.ok(put, '失败后可重试发出新 PUT');
  h.reply(put.index, { detail: 'project not found' }, { ok: false, status: 404 });
  await h.flush();
  assert.match(h.status(), /项目不存在或已被删除/);
  assert.equal(h.rdui.supported, true, 'project not found 不降级不支持');
  assert.equal(h.input().readOnly, false, '编辑区仍可用');
  // ③ 普通 404（网关/反代兜底）：不当作旧服务不支持，可重试
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  h.reply(put.index, { detail: 'Not Found' }, { ok: false, status: 404 });
  await h.flush();
  assert.match(h.status(), /接口返回 404/);
  assert.ok(!/尚未支持保存角色说明/.test(h.status()), '普通 404 不误报为旧服务不支持');
  assert.equal(h.rdui.supported, true, '普通 404 不翻转 supported');
  assert.equal(h.el('role-description-save').disabled, false, '失败后可再次重试');
  h.el('role-description-save').fire('click');
  put = h.puts().at(-1);
  h.reply(put.index, { project_id: 'A', member_id: 'agent:kimi', description: '名册分支草稿', updated_at: 't', updated_by: 'human:qa' });
  await h.flush();
  assert.match(h.status(), /已保存/);
});

test('N5：跨项目往返草稿隔离——A→B→A 恢复 A 草稿，B 草稿并存', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = 'A 项目草稿';
  h.input().fire('input');
  // 切到项目 B（名册重新加载后的缓存），同角色显示服务端值，不串 A 草稿
  h.context.activeProjectId = 'B';
  h.context.projectAgents = ROSTER.map(item => ({ ...item }));
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  await h.flush();
  assert.equal(h.input().value, KIMI_DEFAULT, 'B 项目显示服务端值');
  h.input().value = 'B 项目草稿';
  h.input().fire('input');
  assert.ok(h.drafts.has('human:qa/B/agent:kimi'), 'B 草稿按项目隔离');
  assert.ok(h.drafts.has('human:qa/A/agent:kimi'), 'A 草稿并存不被覆盖');
  // 往返回 A：恢复 A 草稿并提示
  h.context.activeProjectId = 'A';
  h.context.projectAgents = ROSTER.map(item => ({ ...item }));
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  await h.flush();
  assert.equal(h.input().value, 'A 项目草稿', '往返恢复 A 草稿');
  assert.match(h.status(), /已恢复上次未保存的草稿/);
});

test('N5：切账号隔离——另一账号看到服务端值，切回后草稿恢复', async () => {
  const h = harness();
  h.context.members.push({ id: 'human:bob', kind: 'human', display_name: 'Bob' });
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.input().value = 'qa 的未保存草稿';
  h.input().fire('input');
  // 切到另一账号：按 账号/项目/成员 key 隔离，显示服务端值
  h.context.myId = 'human:bob';
  h.context.renderTaskDetailsPanel();
  await h.flush();
  assert.equal(h.input().value, KIMI_DEFAULT, 'bob 看到服务端值，不串 qa 草稿');
  assert.ok(h.drafts.has('human:qa/A/agent:kimi'), 'qa 草稿保留');
  h.input().value = 'bob 的草稿';
  h.input().fire('input');
  assert.ok(h.drafts.has('human:bob/A/agent:kimi'), 'bob 草稿独立 key');
  // 切回 qa：草稿恢复
  h.context.myId = 'human:qa';
  h.context.renderTaskDetailsPanel();
  await h.flush();
  assert.equal(h.input().value, 'qa 的未保存草稿', '切回后恢复 qa 草稿');
  assert.match(h.status(), /已恢复上次未保存的草稿/);
});

test('N5/N4：布局 名称区→说明区→参与任务区；重绘后说明区仍同一节点', async () => {
  const h = harness();
  h.context.projectTasks = [
    { id: 7, root_task_id: 7, title: '布局核对任务', target_member_id: 'agent:kimi', created_by: 'human:qa', workflow_status: 'completed', claimed_at: '2026-10-01T09:00:00', finished_at: '2026-10-01T10:00:00' },
  ];
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  // 名称区渲染角色名，任务区渲染参与任务（说明区是两者之间的静态容器，见 Python 页面契约断言同级顺序）
  const nameTexts = allTexts(h.el('role-details-name-panel'));
  assert.ok(nameTexts.some(t => t.includes('Kimi')), '名称区显示角色名');
  assert.ok(allTexts(h.el('role-details-tasks-panel')).some(t => t.includes('参与的任务')), '任务区显示参与任务');
  assert.ok(allTexts(h.el('role-details-tasks-panel')).some(t => t.includes('布局核对任务')), '参与任务交互保留');
  // 三个面板是独立节点：说明区不在任一动态度量内，重绘不销毁
  const descPanel = h.el('role-description-panel');
  const inputNode = h.input();
  assert.notEqual(descPanel, h.el('role-details-name-panel'));
  assert.notEqual(descPanel, h.el('role-details-tasks-panel'));
  for (let i = 0; i < 3; i++) {
    h.context.renderWorkspaceRoleDetails();
    h.context.renderTaskDetailsPanel();
    await h.flush();
  }
  assert.equal(h.el('role-description-panel'), descPanel, '重绘后说明区仍同一节点');
  assert.equal(h.input(), inputNode, '重绘后 textarea 仍同一节点');
  // 动态两容器已被 replaceChildren 刷新（内容重建），说明区节点身份不受影响
  assert.ok(h.el('role-details-name-panel').children.length > 0);
  assert.ok(h.el('role-details-tasks-panel').children.length > 0);
});
