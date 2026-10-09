// ROLE-BINDING-B4：角色页“运行器与模型绑定”只读展示的前端聚焦测试。
// 在 vm 中加载整份真实 web/workspace.js，走真实 renderWorkspaceList / renderWorkspaceRoleDetails /
// workspaceRoleBindingPanel 渲染路径（不是源码字符串匹配，也不是手写 DOM 镜像），断言真实生成的
// 文本节点、class、属性与请求记录；绑定数据只来自 projectAgents（同一次 GET agents 载荷）。
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const wsSource = fs.readFileSync(require.resolve('../web/workspace.js'), 'utf8');

function fakeEl(tag) {
  const classes = new Set();
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '', disabled: false, readOnly: false,
    dataset: {}, attrs: {}, children: [], listeners: {}, replaceCount: 0,
    classList: {
      add(...cs) { cs.forEach(c => classes.add(c)); },
      remove(...cs) { cs.forEach(c => classes.delete(c)); },
      toggle(c, force) { const on = force === undefined ? !classes.has(c) : !!force; on ? classes.add(c) : classes.delete(c); return on; },
      contains(c) { return classes.has(c); },
    },
    appendChild(c) { el.children.push(c); return c; },
    append(...cs) { el.children.push(...cs); },
    replaceChildren() { el.replaceCount += 1; el.children.length = 0; },
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

const MEMBERS = [
  { id: 'human:qa', kind: 'human', display_name: 'bobo' },
  { id: 'agent:kimi', kind: 'agent', display_name: 'Kimi' },
  { id: 'agent:deepseek', kind: 'agent', display_name: 'DeepSeek' },
];
// 隔离 fixture：全部字段齐全的有效绑定（不写任何生产绑定，只作为渲染输入）。
function boundRow(overrides = {}) {
  return {
    runner_id: 'kimi-code', runtime: 'kimi-code', runner_display_name: 'Kimi Code', runner_status: 'idle',
    model_source: 'custom_api', provider_id: 'managed:kimi-code', connection_ref: 'native-kimi-code-managed-login',
    model_id: 'kimi-for-coding', model_alias: 'kimi-code/kimi-for-coding', model_display_name: 'K2.8 Preview',
    binding_state: 'bound', binding_fingerprint: 'f'.repeat(4), updated_by: 'human:bobo', updated_at: '2026-10-09T00:00:00Z',
    ...overrides,
  };
}
const DEFAULT_ROSTER = [
  { member_id: 'agent:kimi', business_role: 'reviewer', role_description: null, binding: boundRow(), binding_state: 'bound' },
  { member_id: 'agent:deepseek', business_role: 'dev', role_description: null, binding: null, binding_state: 'unconfigured' },
];

function harness({ human = true, roster = DEFAULT_ROSTER } = {}) {
  const pending = [];
  const requests = [];
  const created = [];
  const elements = new Map();
  const getEl = id => {
    if (!elements.has(id)) { const node = fakeEl('div'); node.id = id; elements.set(id, node); }
    return elements.get(id);
  };
  const workbench = fakeEl('div');
  const documentStub = {
    getElementById: getEl,
    createElement: tag => { created.push(tag); return fakeEl(tag); },
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
    apiFetch: (url, opts) => {
      requests.push({ url, opts });
      return new Promise((resolve, reject) => pending.push({ url, opts, resolve, reject }));
    },
    readErrorDetail: async (res, fallback) => {
      try { const body = await res.json(); if (typeof body?.detail === 'string' && body.detail) return body.detail; } catch (_) {}
      return fallback;
    },
    taskStatusMeta: () => ({ label: '执行中', className: 'running' }),
    formatTaskTime: () => '10-09 10:00',
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
  // 按 app.js 真实顺序调用四个面板同步函数（本片只对绑定区负责，其它面板保持真实调用以验证互不干扰）。
  context.renderTaskDetailsPanel = () => {
    context.renderWorkspaceRoleDetails();
    context.renderRequirementsPanel();
    context.renderControllerModePanel();
    context.renderRoleDescriptionPanel();
  };
  vm.runInContext(wsSource, context);
  vm.runInContext('this.__wsui = workspaceUI;', context);

  const flush = async () => { for (let i = 0; i < 3; i++) await new Promise(r => setTimeout(r, 0)); };
  const rows = () => getEl('blackboard-columns').children;
  const roleRows = () => rows().filter(row => String(row.className).includes('role-row') && !String(row.className).includes('role-settings-row'));
  const settingsRow = () => rows().find(row => String(row.className).includes('role-settings-row'));
  const roleRow = memberId => roleRows().find(row => allTexts(row).some(t => t.includes(memberId)));
  const bindingSummary = memberId => roleRow(memberId).children.find(c => String(c.className).includes('role-binding-summary'));
  const bindingSection = () => getEl('role-details-name-panel').children.find(c => String(c.className).includes('role-binding-section'));
  const bindingTexts = () => allTexts(bindingSection());
  const bindingPairs = () => {
    const pairs = [];
    for (const dl of findAll(bindingSection(), n => n.tagName === 'dl')) {
      for (let i = 0; i + 1 < dl.children.length; i += 2) pairs.push([dl.children[i].textContent, dl.children[i + 1].textContent]);
    }
    return pairs;
  };
  const stateBadge = () => findAll(bindingSection(), n => String(n.className).includes('role-binding-state'))[0];
  const enterRoles = async () => {
    getEl('workspace-roles-btn').fire('click');
    context.renderWorkspaceList();
    context.renderWorkspaceRoleDetails();
    context.renderTaskDetailsPanel();
    await flush();
  };
  const selectRole = async memberId => { roleRow(memberId).fire('click'); await flush(); };
  return {
    context, ui: context.__wsui, requests, created, pending, flush, el: getEl,
    rows, roleRows, settingsRow, roleRow, bindingSummary, bindingSection, bindingTexts, bindingPairs, stateBadge,
    enterRoles, selectRole,
  };
}

test('有效绑定：列表紧凑中文摘要 + 详情只读字段全部走真实渲染路径', async () => {
  const h = harness();
  await h.enterRoles();
  const summary = h.bindingSummary('agent:kimi');
  assert.ok(summary, '角色行出现绑定摘要');
  assert.equal(summary.textContent, '绑定：已绑定 · Kimi Code（kimi-code） · K2.8 Preview');
  // 原有列表语义保持：名称、说明摘要、参与任务仍在各自位置，绑定摘要不顶替身份。
  const row = h.roleRow('agent:kimi');
  assert.equal(row.children[0].textContent, 'Kimi');
  assert.equal(row.children[1].textContent, '执行工作');
  assert.match(row.children[2].textContent, /正在参与|当前没有进行中的任务/);
  assert.equal(row.children[3], summary);

  await h.selectRole('agent:kimi');
  assert.equal(h.stateBadge().textContent, '已绑定');
  assert.ok(String(h.stateBadge().className).includes('ok'));
  const pairs = h.bindingPairs();
  assert.deepEqual(pairs, [
    ['运行器', 'Kimi Code'],
    ['运行器类型', 'kimi-code'],
    ['模型来源', '自定义 API（custom_api）'],
    ['提供方标识', 'managed:kimi-code'],
    ['连接标识', 'native-kimi-code-managed-login'],
    ['模型 ID', 'kimi-for-coding'],
    ['模型别名', 'kimi-code/kimi-for-coding'],
    ['模型展示名', 'K2.8 Preview'],
    ['绑定状态', '已绑定'],
  ]);
  // 不展示指纹/更新人/更新等非白名单字段，也不出现任何“匹配”结论。
  const texts = h.bindingTexts().join('\n');
  assert.ok(!texts.includes('ffff'), 'binding_fingerprint 不进入 UI');
  assert.ok(!texts.includes('human:bobo') && !texts.includes('2026-10-09T00:00:00Z'), 'updated_* 不进入 UI');
  assert.ok(!texts.includes('匹配') && !texts.includes('binding_match'), '不输出匹配结论');
  // 角色说明编辑区仍是独立静态节点，未被动态绑定区替换。
  assert.ok(!h.el('role-details-name-panel').children.includes(h.el('role-description-input')));
});

test('unconfigured 明确“未配置”，不写成接入失败，也不伪造模型', async () => {
  const h = harness();
  await h.enterRoles();
  assert.equal(h.bindingSummary('agent:deepseek').textContent, '绑定：未配置');
  await h.selectRole('agent:deepseek');
  assert.equal(h.stateBadge().textContent, '未配置');
  assert.deepEqual(h.bindingPairs(), [['绑定状态', '未配置']]);
  const note = h.bindingTexts().find(t => t.includes('还没有保存'));
  assert.ok(note && note.includes('并不表示接入有问题'), '未配置按“缺少配置”解释');
  assert.ok(!h.bindingTexts().join(' ').includes('接入失败'));
  assert.ok(!h.bindingTexts().some(t => t.includes('kimi-code')), '未配置不猜测运行器/型号');
});

test('not_in_roster 显示“已离册（保留配置）”并保留既有字段；不与其他失效状态混淆', async () => {
  const h = harness({
    roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow(), binding_state: 'not_in_roster' }],
  });
  await h.enterRoles();
  assert.equal(h.bindingSummary('agent:kimi').textContent, '绑定：已离册（保留配置） · Kimi Code（kimi-code） · K2.8 Preview');
  await h.selectRole('agent:kimi');
  assert.equal(h.stateBadge().textContent, '已离册（保留配置）');
  const pairs = h.bindingPairs();
  assert.ok(pairs.some(([k, v]) => k === '模型 ID' && v === 'kimi-for-coding'), '保留已存配置字段');
  assert.equal(pairs.find(([k]) => k === '绑定状态')[1], '已离册（保留配置）');
  assert.ok(!h.bindingTexts().includes('已绑定'), '离册不得显示为已绑定');
});

test('其余失效/身份状态按合同原文展示，无效配置不显示为已绑定', async () => {
  const cases = [
    ['member_missing', '成员不存在（保留配置）', 'invalid'],
    ['member_disabled', '成员已禁用（保留配置）', 'invalid'],
    ['not_agent', '非 Agent 成员（保留配置）', 'invalid'],
    ['partial', '配置不完整（无效）', 'invalid'],
    ['runner_missing', '运行器未登记（无效）', 'invalid'],
    ['runner_retired', '运行器已退役（无效）', 'invalid'],
    ['no_project', '无项目上下文', 'unknown'],
  ];
  for (const [state, label, kind] of cases) {
    const row = state === 'runner_missing'
      ? boundRow({ runtime: null, runner_display_name: null, runner_status: null })
      : boundRow();
    const h = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: row, binding_state: state }] });
    await h.enterRoles();
    assert.equal(h.bindingSummary('agent:kimi').textContent.startsWith(`绑定：${label}`), true, `${state} 列表摘要`);
    await h.selectRole('agent:kimi');
    assert.equal(h.stateBadge().textContent, label, `${state} 详情状态`);
    assert.ok(String(h.stateBadge().className).includes(kind), `${state} 状态样式分类`);
    assert.ok(!h.bindingTexts().includes('已绑定'), `${state} 不得显示已绑定`);
    if (state === 'runner_missing') {
      assert.equal(h.bindingPairs().find(([k]) => k === '运行器')[1], '运行器未上报');
    }
  }
});

test('旧服务缺字段、未记录、未知状态、未配置四类严格区分', async () => {
  // 旧服务：整个 binding / binding_state 字段都没有。
  const legacy = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer' }] });
  await legacy.enterRoles();
  assert.equal(legacy.bindingSummary('agent:kimi').textContent, '绑定：当前服务未提供绑定信息');
  await legacy.selectRole('agent:kimi');
  assert.deepEqual(legacy.bindingPairs(), [['绑定状态', '当前服务未提供绑定状态']]);
  assert.ok(legacy.bindingTexts().some(t => t.includes('不等于“未配置”')), '旧服务缺失必须与未配置区分');

  // 字段在但空值：记“未记录”，不等于未配置。
  const empty = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: null, binding_state: null }] });
  await empty.enterRoles();
  assert.equal(empty.bindingSummary('agent:kimi').textContent, '绑定：绑定状态未记录');
  await empty.selectRole('agent:kimi');
  assert.equal(empty.stateBadge().textContent, '绑定状态未记录');

  // 未知枚举值：如实显示原值，不伪装成未配置，也不当接入失败。
  const unknown = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow({ binding_state: 'future_state' }), binding_state: 'future_state' }] });
  await unknown.enterRoles();
  assert.equal(unknown.bindingSummary('agent:kimi').textContent, '绑定：未知绑定状态 · Kimi Code（kimi-code） · K2.8 Preview');
  await unknown.selectRole('agent:kimi');
  assert.equal(unknown.stateBadge().textContent, '未知绑定状态');
  assert.ok(unknown.bindingPairs().some(([k, v]) => k === '绑定状态' && v === '未知绑定状态（future_state）'));
  assert.ok(!unknown.bindingTexts().includes('未配置'), '未知状态不得渲染成未配置');
});

test('半缺字段：已有值照存、缺值写“未上报”，不补默认模型', async () => {
  const h = harness({
    roster: [{
      member_id: 'agent:kimi', business_role: 'reviewer', binding_state: 'partial',
      binding: boundRow({ model_source: null, provider_id: null, connection_ref: null, model_alias: null, model_display_name: null, runtime: null, runner_display_name: null }),
    }],
  });
  await h.enterRoles();
  assert.equal(h.bindingSummary('agent:kimi').textContent, '绑定：配置不完整（无效） · 运行器未上报 · kimi-for-coding');
  await h.selectRole('agent:kimi');
  assert.deepEqual(h.bindingPairs(), [
    ['运行器', '运行器未上报'],
    ['运行器类型', '运行器类型未上报'],
    ['模型来源', '来源未上报'],
    ['提供方标识', '提供方未上报'],
    ['连接标识', '连接标识未上报'],
    ['模型 ID', 'kimi-for-coding'],
    ['模型别名', '模型别名未上报'],
    ['模型展示名', '模型展示名未上报'],
    ['绑定状态', '配置不完整（无效）'],
  ]);
});

test('内置来源按 builtin 展示；未知来源值如实标为未识别', async () => {
  const builtin = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow({ model_source: 'builtin', provider_id: 'builtin:codex', connection_ref: 'native-codex-login', model_id: 'gpt-5-codex', model_alias: null, model_display_name: null }), binding_state: 'bound' }] });
  await builtin.enterRoles();
  await builtin.selectRole('agent:kimi');
  assert.equal(builtin.bindingPairs().find(([k]) => k === '模型来源')[1], '运行器内置（builtin）');
  assert.equal(builtin.bindingSummary('agent:kimi').textContent, '绑定：已绑定 · Kimi Code（kimi-code） · gpt-5-codex');

  const strange = harness({ roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow({ model_source: 'hybrid_x' }), binding_state: 'bound' }] });
  await strange.enterRoles();
  await strange.selectRole('agent:kimi');
  assert.equal(strange.bindingPairs().find(([k]) => k === '模型来源')[1], '未识别的来源值（hybrid_x）');
});

test('配置变化后重绘即更新显示，不改名册空值语义', async () => {
  const h = harness();
  await h.enterRoles();
  assert.equal(h.bindingSummary('agent:deepseek').textContent, '绑定：未配置');
  await h.selectRole('agent:deepseek');
  assert.deepEqual(h.bindingPairs(), [['绑定状态', '未配置']]);
  // 同一份 projectAgents 载荷被刷新（refreshProjectWorkspace/切项目重读）后，值随之更新。
  h.context.projectAgents[1].binding = boundRow({ runner_display_name: 'DeepSeek Harness', runtime: 'dsh', model_source: 'custom_api', provider_id: 'managed:deepseek', connection_ref: 'native-dsh-login', model_id: 'deepseek-chat', model_alias: null, model_display_name: null });
  h.context.projectAgents[1].binding_state = 'bound';
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  await h.flush();
  assert.equal(h.bindingSummary('agent:deepseek').textContent, '绑定：已绑定 · DeepSeek Harness（dsh） · deepseek-chat');
  assert.equal(h.bindingPairs().find(([k]) => k === '模型 ID')[1], 'deepseek-chat');
  // 状态回退也如实反映
  h.context.projectAgents[1].binding_state = 'runner_retired';
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  assert.equal(h.stateBadge().textContent, '运行器已退役（无效）');
});

test('绑定只读区不产生任何按角色请求或写请求，也不读实例字段回填', async () => {
  const h = harness({
    roster: [{
      member_id: 'agent:kimi', business_role: 'reviewer', binding: null, binding_state: 'unconfigured',
      // 与实例/运行中模型无关的额外字段：不得被当成绑定内容。
      runtime: 'codex', model_id: 'gpt-5-codex', runner_display_name: 'Codex CLI', runner_status: 'online',
      instances: [{ id: 'i1', runtime: 'codex', status: 'online' }],
    }],
  });
  h.requests.length = 0;
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  await h.flush();
  for (const request of h.requests) {
    assert.ok(!/\/binding(\?|$)/.test(request.url), `不得请求绑定端点：${request.url}`);
    assert.ok(!/\/agents\/agent:/.test(request.url), `不得按角色新增请求：${request.url}`);
    assert.ok(!request.opts || !request.opts.method || request.opts.method === 'GET', '不得发写请求');
  }
  assert.equal(h.bindingSummary('agent:kimi').textContent, '绑定：未配置');
  await h.selectRole('agent:kimi');
  const texts = h.bindingTexts().join('\n');
  for (const leak of ['codex', 'gpt-5-codex', 'Codex CLI', 'online']) {
    assert.ok(!texts.includes(leak), `实例/运行中字段不得回填绑定：${leak}`);
  }
});

test('恶意 runner/model/alias/connection 值只作纯文本，不产生链接或事件', async () => {
  const evil = '<img src=x onerror="alert(1)">';
  const evilConnection = 'javascript:alert(2)" onclick="window.x=1';
  const evilAlias = '</dd><script>alert(3)</script>';
  const evilUnion = 'native-kimi"><svg/onload=alert(4)>';
  const h = harness({
    roster: [{
      member_id: 'agent:kimi', business_role: 'reviewer', binding_state: 'bound',
      binding: boundRow({
        runner_id: evil, runtime: evil, runner_display_name: evil, runner_status: evil,
        model_source: 'custom_api', provider_id: evil, connection_ref: evilConnection,
        model_id: evil, model_alias: evilAlias, model_display_name: evilUnion,
      }),
    }],
  });
  await h.enterRoles();
  h.created.length = 0;
  await h.selectRole('agent:kimi');
  const section = h.bindingSection();
  const nodes = [section, ...findAll(section, () => true)];
  for (const node of nodes) {
    assert.ok(['a', 'img', 'script', 'iframe', 'link', 'svg'].includes(node.tagName) === false, `不得生成可执行/可导航元素：${node.tagName}`);
    for (const key of Object.keys(node.attrs)) {
      assert.ok(!/^on/i.test(key), `不得写事件属性：${key}`);
      assert.ok(!['href', 'src', 'action', 'srcdoc'].includes(key), `不得写可导航属性：${key}`);
    }
    assert.equal(Object.keys(node.listeners).length, 0, '绑定区不得注册事件监听');
  }
  for (const tag of h.created) {
    assert.ok(!['a', 'img', 'script', 'iframe', 'link', 'svg'].includes(tag), `渲染期不得创建 ${tag}`);
  }
  const pairs = h.bindingPairs();
  assert.equal(pairs.find(([k]) => k === '运行器')[1], evil, '恶意值原样作为文本显示');
  assert.equal(pairs.find(([k]) => k === '运行器类型')[1], evil);
  assert.equal(pairs.find(([k]) => k === '连接标识')[1], evilConnection);
  assert.equal(pairs.find(([k]) => k === '模型别名')[1], evilAlias);
  assert.equal(pairs.find(([k]) => k === '模型展示名')[1], evilUnion);
  assert.ok(h.bindingSummary('agent:kimi').textContent.includes(evil));
});

test('列表与选择语义保持：项目设置首项、角色数量、搜索范围不含绑定值', async () => {
  const h = harness();
  await h.enterRoles();
  assert.equal(h.rows()[0], h.settingsRow());
  assert.equal(h.settingsRow().children[0].textContent, '项目设置');
  assert.equal(h.roleRows().length, 2, '角色数量不计项目设置');
  // 搜索仍只按成员名 + 说明 + business_role：绑定里的模型名不参与匹配。
  h.ui.query = 'K2.8';
  h.context.renderWorkspaceList();
  assert.equal(h.roleRows().length, 0, '绑定值不进入搜索匹配范围');
  assert.ok(allTexts(h.el('blackboard-columns')).some(t => t === '没有匹配的角色'));
  h.ui.query = '';
  h.context.renderWorkspaceList();
  assert.equal(h.roleRows().length, 2);
  // 选中失效角色仍回退项目设置，绑定展示不改变选择语义。
  h.ui.roleSelection = 'role';
  h.ui.selectedRole = 'agent:ghost';
  h.context.renderWorkspaceList();
  h.context.renderTaskDetailsPanel();
  assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
  assert.ok(!h.bindingSection(), '项目设置下不残留绑定面板');
});

test('未变化重绘不销毁角色说明编辑器、焦点与草稿', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  const inputNode = h.el('role-description-input');
  inputNode.value = '未保存草稿 v1';
  inputNode.fire('input');
  inputNode.focus();
  for (let i = 0; i < 5; i++) {
    h.context.renderWorkspaceList();
    h.context.renderTaskDetailsPanel();
    await h.flush();
  }
  assert.equal(h.el('role-description-input'), inputNode, 'textarea 节点身份保持');
  assert.equal(inputNode.value, '未保存草稿 v1', '草稿不被绑定重绘覆盖');
  assert.equal(inputNode.replaceCount, 0, '说明编辑器未被 replaceChildren 触碰');
  assert.ok(h.bindingSection(), '绑定区照常刷新');
  assert.ok(!h.el('role-details-name-panel').children.includes(inputNode));
});

test('绑定面板可见性与角色详情一致：项目设置/非角色页不显示', async () => {
  const h = harness();
  await h.enterRoles();
  await h.selectRole('agent:kimi');
  assert.ok(h.bindingSection());
  h.ui.roleSelection = 'settings';
  h.context.renderTaskDetailsPanel();
  assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
  h.ui.mode = 'tasks';
  h.context.renderTaskDetailsPanel();
  assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
  h.ui.mode = 'roles';
  h.ui.roleSelection = 'role';
  h.context.renderTaskDetailsPanel();
  assert.ok(h.bindingSection(), '回到角色详情时绑定区恢复');
});

test('只读：绑定区不产生可编辑控件，不给 agent 账号额外入口', async () => {
  const h = harness({ human: false, roster: [{ member_id: 'agent:deepseek', business_role: 'dev', binding: boundRow(), binding_state: 'bound' }] });
  await h.enterRoles();
  await h.selectRole('agent:deepseek');
  const controls = findAll(h.bindingSection(), n => ['button', 'input', 'textarea', 'select', 'a'].includes(n.tagName));
  assert.deepEqual(controls, [], '绑定区不得出现任何可编辑/可提交控件');
  assert.ok(h.bindingTexts().includes('已绑定'));
});

// ── #202 F1 定向修正回归：枚举映射只认自有白名单键 ────────────────────────────
// 反例来自复核探针 prototype_boundary_probe.cjs 复现的 7 项：5 个 binding_state 继承键
// + 2 个 model_source 继承键。断言全部走真实 renderWorkspaceList / renderWorkspaceRoleDetails
// 渲染出的列表摘要、详情字段与状态徽标，不是源码字符串匹配，也不手写映射镜像。
const INHERITED_KEY_STATES = ['constructor', '__proto__', 'toString', 'valueOf', 'hasOwnProperty'];
const INHERITED_KEY_SOURCES = ['constructor', '__proto__', 'Constructor', '__PROTO__'];

test('F1：binding_state 继承键不被误认为已知枚举，列表/详情一致降级为未知原值', async () => {
  for (const value of INHERITED_KEY_STATES) {
    const h = harness({
      roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow({ binding_state: value }), binding_state: value }],
    });
    await h.enterRoles();
    assert.equal(h.bindingSummary('agent:kimi').textContent, '绑定：未知绑定状态 · Kimi Code（kimi-code） · K2.8 Preview', `${value} 列表摘要`);
    await h.selectRole('agent:kimi');
    assert.equal(h.stateBadge().textContent, '未知绑定状态', `${value} 徽标文字`);
    const badgeClass = String(h.stateBadge().className);
    assert.ok(badgeClass.includes('unknown'), `${value} kind 必须为 unknown`);
    assert.ok(!badgeClass.includes('undefined'), `${value} 不得渲染 undefined 分类`);
    assert.equal(h.bindingPairs().find(([k]) => k === '绑定状态')[1], `未知绑定状态（${value}）`, `${value} 详情保留未知原值`);
    assert.ok(h.bindingTexts().some(t => t.includes('还不认识的绑定状态')), `${value} known=false 走未知说明`);
    assert.ok(!h.bindingTexts().includes('未配置'), `${value} 不得降级成未配置`);
    assert.ok(!h.bindingTexts().join('\n').includes('undefined'), `${value} 不得出现 undefined 文本`);
  }
});

test('F1：model_source 继承键返回纯文本“未识别的来源值（原值）”，不显示原型函数/对象', async () => {
  for (const value of INHERITED_KEY_SOURCES) {
    const h = harness({
      roster: [{ member_id: 'agent:kimi', business_role: 'reviewer', binding: boundRow({ model_source: value }), binding_state: 'bound' }],
    });
    await h.enterRoles();
    await h.selectRole('agent:kimi');
    const sourceText = h.bindingPairs().find(([k]) => k === '模型来源')[1];
    assert.equal(typeof sourceText, 'string', `${value} 必须是纯文本字符串`);
    assert.equal(sourceText, `未识别的来源值（${value}）`, `${value} 原值如实标注`);
    const joined = h.bindingTexts().join('\n');
    for (const leak of ['native code', 'Object.prototype', '[object', '=>']) {
      assert.ok(!String(sourceText).includes(leak), `${value} 来源值不得含原型文本：${leak}`);
      assert.ok(!joined.includes(leak), `${value} 面板不得出现原型文本：${leak}`);
    }
    // 合法枚举不受影响，且继承键没有被当成“未上报”。
    assert.ok(!joined.includes('来源未上报'), `${value} 与“来源未上报”区分`);
    assert.equal(h.stateBadge().textContent, '已绑定', `${value} 状态仍为已绑定`);
  }
});
