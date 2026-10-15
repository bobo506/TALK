// 2026-10-15截图纠正：列表保留绑定状态、运行器短名和一次模型名，去冗余后缀；ID/空闲提示留详情。
// 加载真实workspace.js，验证实际角色行/详情、选择/搜索与只读行为；
// 原属性表/C4指引专属断言随已撤销的界面要求退役，保留列表状态/安全/草稿等有效覆盖。
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
  const rows = () => getEl('blackboard-columns').children.flatMap(node => String(node.className).includes('role-entry') ? node.children : [node]);
  const roleRows = () => rows().filter(row => String(row.className).includes('role-row') && !String(row.className).includes('role-settings-row'));
  const settingsRow = () => rows().find(row => String(row.className).includes('role-settings-row'));
  const roleRow = memberId => roleRows().find(row => row.dataset.memberId === memberId);
  const bindingSummary = memberId => roleRow(memberId).children.find(c => String(c.className).includes('role-binding-summary')).textContent;
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
    rows, roleRows, settingsRow, roleRow, bindingSummary,
    enterRoles, selectRole,
  };
}


test('截图实际登记名只显示运行器短名和一次模型，列表空闲隐藏但详情与进行中数量保持',async()=>{
  const h=harness({roster:[{...DEFAULT_ROSTER[0],binding:boundRow({runner_display_name:'Kimi Code · K2.8 Preview 执行'})},DEFAULT_ROSTER[1]]});await h.enterRoles();
  const row=h.roleRow('agent:kimi');assert.ok(row);assert.equal(row.dataset.memberId,'agent:kimi');
  const list=allTexts(row).join('\n');assert.match(list,/Kimi Code/);assert.doesNotMatch(list,/（kimi-code）|agent:kimi|当前没有进行中的任务/);
  assert.equal(h.bindingSummary('agent:kimi'),'绑定：已绑定 · Kimi Code · K2.8 Preview');
  assert.equal(findAll(row,n=>String(n.className).includes('role-binding-summary')).length,1);
  await h.selectRole('agent:kimi');const panel=h.el('role-details-name-panel');const detail=allTexts(panel).join('\n');
  assert.match(detail,/成员 ID：agent:kimi/);assert.doesNotMatch(detail,/Kimi Code|K2.8 Preview|运行器与模型绑定|提供方标识|连接标识|模型来源|模型 ID|收尾指引|配置进度/);
  assert.equal(findAll(panel,n=>String(n.className).includes('role-binding-section')).length,0);
  assert.match(detail,/当前没有进行中的任务/);
  h.context.projectTasks=[{id:1,target_member_id:'agent:kimi',workflow_status:'assigned'}];
  h.context.renderWorkspaceList();h.context.renderWorkspaceRoleDetails();
  assert.match(allTexts(h.roleRow('agent:kimi')).join('\n'),/正在参与 1 项任务/);
  assert.match(allTexts(panel).join('\n'),/正在参与 1 项任务/);
  h.context.projectTasks[0].workflow_status='completed';h.context.renderWorkspaceList();h.context.renderWorkspaceRoleDetails();
  assert.doesNotMatch(allTexts(h.roleRow('agent:kimi')).join('\n'),/正在参与|当前没有进行中的任务/);
  assert.match(allTexts(panel).join('\n'),/当前没有进行中的任务/);
});

test('实际列表短摘要仍区分真实绑定状态，详情不恢复已移除的属性块',async()=>{
  const cases=[
    [{binding:null,binding_state:'unconfigured'},/未配置/],
    [{binding:boundRow(),binding_state:'partial'},/不完整/],
    [{binding:boundRow(),binding_state:'not_in_roster'},/已离册/],
    [{binding:boundRow(),binding_state:'runner_retired'},/运行器.*退役|运行器.*下架/],
    [{binding:boundRow(),binding_state:'constructor'},/未知绑定状态/],
    [{binding:boundRow(),binding_state:'__proto__'},/未知绑定状态/],
  ];
  for(const [fields,expected] of cases) {
    const h=harness({roster:[{member_id:'agent:kimi',business_role:'dev',...fields}]});await h.enterRoles();
    const text=h.bindingSummary('agent:kimi');assert.match(text,expected);assert.doesNotMatch(text,/已绑定/);
    assert.equal(findAll(h.roleRow('agent:kimi'),n=>String(n.className).includes('role-binding-summary')).length,1);
    await h.selectRole('agent:kimi');assert.doesNotMatch(allTexts(h.el('role-details-name-panel')).join('\n'),/运行器与模型绑定|收尾指引/);
  }
  const legacy=harness({roster:[{member_id:'agent:kimi',business_role:'dev'}]});await legacy.enterRoles();assert.match(legacy.bindingSummary('agent:kimi'),/当前服务未提供绑定信息/);
});

test('列表模型字段降级和运行器缺展示名保持，不猜型号',async()=>{
  for(const [fields,expected] of [
    [{model_display_name:'',model_alias:'known-alias'},/known-alias/],
    [{model_display_name:null,model_alias:'',model_id:'known-model'},/known-model/],
    [{model_display_name:'',model_alias:'',model_id:''},/模型未上报/],
    [{runner_display_name:null,runtime:'kimi-code'},/kimi-code/],
    [{runner_display_name:'',runtime:''},/运行器未上报/],
    [{runner_display_name:'Custom Runner · East'},/Custom Runner · East/],
    [{runner_display_name:'Kimi Code · K2.8 Preview'},/绑定：已绑定 · Kimi Code · K2.8 Preview$/],
  ]) {
    const h=harness({roster:[{member_id:'agent:kimi',binding:boundRow(fields),binding_state:'bound'}]});await h.enterRoles();assert.match(h.bindingSummary('agent:kimi'),expected);
  }
});

test('列表和详情使用公开文本，未知附加字段和属性元数据不展示',async()=>{
  const malicious='<img src=x onerror=alert(1)>';
  const h=harness({roster:[{member_id:'agent:kimi',binding:boundRow({runner_display_name:malicious,model_display_name:'<script>bad()</script>',connection_ref:'private-ref-sentinel',provider_id:'provider-sentinel',api_key:'SECRET'}),binding_state:'bound'}]});
  await h.enterRoles();assert.match(h.bindingSummary('agent:kimi'),/onerror=alert/);assert.match(h.bindingSummary('agent:kimi'),/bad\(\)/);
  assert.equal(h.created.includes('img'),false);assert.equal(h.created.includes('script'),false);assert.equal(h.created.includes('a'),false);
  await h.selectRole('agent:kimi');const all=[...allTexts(h.el('blackboard-columns')),...allTexts(h.el('role-details-name-panel'))].join('\n');
  assert.doesNotMatch(all,/private-ref-sentinel|provider-sentinel|SECRET/);
});

test('移除列表ID不影响真实角色选择、项目设置首项和角色计数',async()=>{
  const h=harness();await h.enterRoles();assert.match(allTexts(h.settingsRow()).join(' '),/项目设置/);assert.equal(h.roleRows().length,2);
  await h.selectRole('agent:deepseek');assert.equal(h.ui.selectedRole,'agent:deepseek');assert.equal(h.ui.roleSelection,'role');
  assert.match(allTexts(h.el('role-details-name-panel')).join('\n'),/成员 ID：agent:deepseek/);
  h.settingsRow().fire('click');assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
});

test('搜索仍按名称和说明，不把模型、运行器或ID当成新搜索范围',async()=>{
  const h=harness();await h.enterRoles();
  for(const query of ['K2.8 Preview','agent:kimi','native-kimi-code-managed-login']) {h.ui.query=query;h.context.renderWorkspaceList();assert.equal(h.roleRows().length,0);}
  h.ui.query='Kimi';h.context.renderWorkspaceList();assert.equal(h.roleRows().length,1);
});

test('短摘要随真实模型声明重绘，不额外读取绑定或发出写请求',async()=>{
  const h=harness();await h.enterRoles();await h.selectRole('agent:kimi');
  h.context.projectAgents[0].binding=boundRow({model_display_name:'新模型声明'});h.context.renderWorkspaceList();h.context.renderWorkspaceRoleDetails();
  assert.equal(h.bindingSummary('agent:kimi'),'绑定：已绑定 · Kimi Code · 新模型声明');
  assert.equal(h.requests.some(r=>['POST','PUT','PATCH','DELETE'].includes(r.opts?.method)),false);
  assert.equal(h.requests.some(r=>/\/binding|model-choices/.test(r.url)),false);
});

test('重绘角色信息保持说明编辑器节点、焦点和草稿',async()=>{
  const h=harness();await h.enterRoles();await h.selectRole('agent:kimi');
  const input=h.el('role-description-input');input.value='尚未保存的说明';h.context.document.activeElement=input;
  h.context.renderWorkspaceList();h.context.renderWorkspaceRoleDetails();
  assert.equal(h.el('role-description-input'),input);assert.equal(input.value,'尚未保存的说明');assert.equal(h.context.document.activeElement,input);
});

test('角色开关使用易懂标题，项目设置或任务页仍隐藏具体角色详情',async()=>{
  const h=harness({roster:[{...DEFAULT_ROSTER[0],service:null}]});await h.enterRoles();await h.selectRole('agent:kimi');
  const detail=allTexts(h.el('role-details-name-panel')).join('\n');assert.match(detail,/角色开关/);assert.doesNotMatch(detail,/受管 CLI 服务/);
  h.settingsRow().fire('click');assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
  h.ui.mode='tasks';h.context.renderWorkspaceRoleDetails();assert.ok(h.el('role-details-name-panel').classList.contains('hidden'));
});

test('agent只读角色摘要，历史分级或实例信息不改变展示和权限',async()=>{
  const h=harness({human:false,roster:[{...DEFAULT_ROSTER[0],decision_tier:'decision',instances:[{model:'not-a-binding-model'}]}]});await h.enterRoles();await h.selectRole('agent:kimi');
  const text=[...allTexts(h.el('blackboard-columns')),...allTexts(h.el('role-details-name-panel'))].join('\n');assert.doesNotMatch(text,/not-a-binding-model|决策 Agent|decision_tier/);
  assert.match(h.bindingSummary('agent:kimi'),/K2.8 Preview/);assert.equal(h.requests.some(r=>r.opts?.method&&r.opts.method!=='GET'),false);
});
