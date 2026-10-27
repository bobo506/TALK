'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createRoleRequestUI}=require('../web/role-creation.js');
const {documentFixture}=require('./role_creation_dom.cjs');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function limitedHistory(call,backend) {
  if(call.method!=='GET')return undefined;
  if(call.path.includes('/role-requests?')) {
    const status=new URL(call.path,'http://fixture').searchParams.get('status');
    return response(backend.rows.filter(r=>!status||r.status===status).sort((a,b)=>String(a.created_at).localeCompare(String(b.created_at))).slice(0,200));
  }
  if(call.path.includes('/role-requests/'))return response(backend.rows.find(r=>call.path.endsWith('/'+r.request_key))||{},backend.rows.some(r=>call.path.endsWith('/'+r.request_key))?200:404);
}
const oldHistory=()=>Array.from({length:205},(_,i)=>({request_key:`role-old-history-${String(i).padStart(8,'0')}`,status:'provisioned',revision:3,member_id:`old:${i}`,created_at:'2025-01-01T00:00:00Z'}));
function harness({storage=new Map(),human=true,handler}={}) {
  const dom=documentFixture(),ctx={projectId:'p',accountId:'human:a',active:true,settings:true,human};
  const requests=[],timers=new Map();let count=0,confirms=0;
  const backend={host:{enabled:true,host_label:'local',config_version:0},rows:[],roles:[]};
  const deps={document:dom.document,context:()=>ctx,storage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    setTimeout:fn=>{const id=++count;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
    newKey:()=>`role-000000000000000000000000000${++count}`,confirm:()=>{confirms++;return true;},
    refreshRoster:async()=>{},renderDetails:()=>{},selectRole:id=>{ctx.selected=id;},
    api:async(path,options)=>{
      const call={path,method:options.method||'GET',body:options.body?JSON.parse(options.body):null};requests.push(call);
      const value=await handler?.(call,backend);if(value!==undefined)return value;
      if(path.endsWith('/role-provision-host'))return response(backend.host);
      if(path.includes('/role-requests?'))return response(backend.rows);
      if(path.endsWith('/roles'))return response(backend.roles);
      if(path.endsWith('/agents'))return response([]);
      if(path==='/api/runners')return response([{runner_id:'r',display_name:'DSH',adapter_status:'adapted',control_kind:'managed_cli'}]);
      if(path.endsWith('/model-choices'))return response([{runner_id:'r',choice_id:'c',model_display_name:'Flash'}]);
      if(call.method==='POST'&&path.endsWith('/role-requests')) {const row={...call.body,status:'requested',revision:1};backend.rows.unshift(row);return response({...row,api_key:'SECRET',lease_token:'TOKEN'});}
      throw Error('unexpected '+path);
    }};
  const ui=createRoleRequestUI(deps);
  async function ready() {ui.sync();await tick();}
  async function fill(name='审查助手') {await ui.open();dom.el('role-create-runner').value='r';await ui.chooseRunner();dom.el('role-create-model').value='c';dom.el('role-create-name').value=name;dom.el('role-create-description').value='负责审查';}
  return {...dom,ui,ctx,requests,timers,backend,storage,deps,ready,fill,confirms:()=>confirms};
}
test('选择真实目录并提交单一人类意图，未知凭据字段不进入状态或存储',async()=>{
  const h=harness();await h.ready();await h.fill();await h.ui.submit();
  const posts=h.requests.filter(r=>r.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].path,'/api/projects/p/role-requests');
  assert.deepEqual(Object.keys(posts[0].body).sort(),['auto_start','choice_id','confirm','kind','request_key','role_description','role_name','runner_id'].sort());
  assert.equal(posts[0].body.role_name,'审查助手');assert.equal(posts[0].body.choice_id,'c');
  assert.equal(h.el('role-create-submit').disabled,true);
  assert.doesNotMatch(JSON.stringify(h.ui.state),/SECRET|TOKEN/);assert.doesNotMatch([...h.storage.values()].join(''),/SECRET|TOKEN/);
});

test('新建Kimi角色先等待独立登录，不自动启动未配置的运行器',async()=>{
  const h=harness({handler:c=>{
    if(c.path==='/api/runners')return response([{runner_id:'r',runtime:'kimi-code',display_name:'Kimi',adapter_status:'adapted',control_kind:'managed_cli'}]);
    if(c.path.endsWith('/model-choices'))return response([{runner_id:'r',choice_id:'c',model_display_name:'K3.1'}]);
  }});
  await h.ready();await h.fill();await h.ui.submit();
  assert.equal(h.requests.find(r=>r.method==='POST').body.auto_start,false);
  assert.match(h.el('role-create-notice').textContent,/手动启动/);
});

test('已创建Kimi角色展示受限本机登录指引，禁止拼接不安全标识',async()=>{
  const h=harness();
  h.backend.roles=[{member_id:'agent:new',role_name:'K',runner:{runtime:'kimi-code'},service:{observed:'stopped'}}];
  h.backend.rows=[{request_key:'role-0000000000000000000000000001',kind:'create',status:'provisioned',revision:3,credential_version:1,member_id:'agent:new'}];
  await h.ready();
  let panel=h.ui.rolePanel({member_id:'agent:new'});
  assert.match(h.texts(panel),/python -m scripts\.kimi_role_setup --project p --member agent:new/);
  h.ctx.projectId='p;danger';
  panel=h.ui.rolePanel({member_id:'agent:new'});
  assert.doesNotMatch(h.texts(panel),/python -m/);
  assert.match(h.texts(panel),/无法安全生成/);
});

test('已归档Kimi角色不展示登录配置命令',async()=>{
  const h=harness();
  h.backend.roles=[{member_id:'agent:new',role_name:'K',archived:true,runner:{runtime:'kimi-code'},service:{observed:'stopped'}}];
  h.backend.rows=[{request_key:'role-0000000000000000000000000001',kind:'create',status:'provisioned',revision:3,credential_version:1,member_id:'agent:new'}];
  await h.ready();
  const panel=h.ui.rolePanel({member_id:'agent:new'});
  assert.doesNotMatch(h.texts(panel),/kimi_role_setup/);
});
test('保存处理中重复点击不会创建第二个请求',async()=>{
  const d=deferred();const h=harness({handler:c=>c.method==='POST'?d.promise:undefined});await h.ready();await h.fill();
  const pending=h.ui.submit();await h.ui.submit();assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
  d.resolve(response({request_key:h.ui.state.attempt.key,status:'requested',revision:1}));await pending;
});
test('丢响应后字段修改不改变原键和载荷，重建页面也能重试',async()=>{
  const storage=new Map();const h=harness({storage,handler:c=>{if(c.method==='POST')throw Error('lost');}});await h.ready();await h.fill();await h.ui.submit();
  const original=h.requests.find(r=>r.method==='POST').body;h.el('role-create-name').value='不能改';await h.ui.submit();
  assert.deepEqual(h.requests.filter(r=>r.method==='POST').map(r=>r.body),[original,original]);
  const reopened=harness({storage});await reopened.ready();await reopened.ui.open();await reopened.ui.submit();
  assert.deepEqual(reopened.requests.find(r=>r.method==='POST').body,original);
  assert.match(reopened.texts(reopened.el('role-create-runner')),/DSH/);assert.match(reopened.texts(reopened.el('role-create-model')),/Flash/);
});

test('介绍按后端空白集合归空，非空白换行和FEFF保留原文',async()=>{
  for(const [input,expected] of [['\u0085'.repeat(2001),null],['\uFEFF','\uFEFF'],['  介绍\n第二行  ','  介绍\n第二行  ']]) {
    const h=harness();await h.ready();await h.fill();h.el('role-create-description').value=input;await h.ui.submit();
    assert.equal(h.requests.find(r=>r.method==='POST').body.role_description,expected);
  }
});
test('名称冲突是确定性拒绝，用户可以修改后重新保存',async()=>{
  const h=harness({handler:c=>c.method==='POST'?response({detail:'role_request_role_conflict'},409):undefined});await h.ready();await h.fill();await h.ui.submit();
  assert.equal(h.ui.state.attempt,null);assert.equal(h.el('role-create-name').disabled,false);
  assert.match(h.el('role-create-notice').textContent,/已有待处理/);
});
test('agent只有只读进度，所有写入口均不发POST',async()=>{
  const h=harness({human:false});await h.ready();assert.equal(h.ui.newButton(),null);
  await h.ui.submit();await h.ui.setHost(true);await h.ui.mutate({request_key:'x',revision:1},'resume');await h.ui.recover({member_id:'a',credential_version:1});
  assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
});

test('打开人类表单后账号变为agent，提交监听仍拒绝POST',async()=>{
  const h=harness();await h.ready();await h.fill();h.ctx.human=false;h.ctx.accountId='agent:readonly';
  await h.el('role-create-form').fire('submit',{preventDefault(){}});
  assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
});

test('宿主代际无法安全表示时操作按钮禁用且不发送POST',async()=>{
  const h=harness();h.backend.host.config_version=Number.MAX_SAFE_INTEGER+1;await h.ready();
  h.el('role-request-host-name').value='another-host';await h.el('role-request-host-name').fire('input');
  assert.equal(h.el('role-request-host-enable').disabled,true);assert.equal(h.el('role-request-host-disable').disabled,true);
  await h.ui.setHost(true);assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
});

test('超过200条历史完成请求不会挤掉新待创建进度',async()=>{
  const h=harness({handler:limitedHistory});h.backend.rows=[...oldHistory(),{request_key:'role-current-00000000',status:'requested',revision:1,role_name:'新的角色',created_at:'2026-10-13T00:00:00Z'}];
  await h.ready();assert.match(h.texts(h.el('role-request-list')),/新的角色/);assert.equal(h.timers.size,1);
  assert.match(h.texts(h.el('role-request-list')),/部分记录未显示/);
});

test('本页保存后跨入已满终态列表，刷新和重建页面仍跟踪原请求',async()=>{
  const storage=new Map();const h=harness({storage,handler:limitedHistory});h.backend.rows=oldHistory();await h.ready();await h.fill();await h.ui.submit();
  const saved=h.backend.rows[0];Object.assign(saved,{status:'provisioned',member_id:'new:member',created_at:'2026-10-13T00:00:00Z',credential_version:1});
  await h.ui.refresh();assert.match(h.texts(h.ui.rolePanel({member_id:'new:member'})),/绑定重置/);assert.equal(h.timers.size,0);
  assert.ok(h.requests.some(r=>r.method==='GET'&&r.path.endsWith('/role-requests/'+saved.request_key)));
  const reopened=harness({storage,handler:limitedHistory});reopened.backend.rows=h.backend.rows;await reopened.ready();
  assert.match(reopened.texts(reopened.ui.rolePanel({member_id:'new:member'})),/绑定重置/);assert.equal(reopened.requests.filter(r=>r.method==='POST').length,0);
  reopened.ctx.accountId='human:b';reopened.ui.sync();await tick();
  assert.equal(reopened.ui.state.recentKeys.length,0);
  reopened.ctx.projectId='other';reopened.ctx.accountId='human:a';reopened.ui.sync();await tick();
  assert.equal(reopened.ui.state.recentKeys.length,0);
});

test('同一角色以最新配置请求展示，历史失败不盖住新恢复结果',async()=>{
  const h=harness({handler:limitedHistory});h.backend.rows=[
    {request_key:'role-earlier-00000000',member_id:'m',status:'failed',revision:2,created_at:'2026-10-12T00:00:00Z'},
    {request_key:'role-recover-00000000',member_id:'m',status:'provisioned',revision:3,credential_version:2,created_at:'2026-10-13T00:00:00Z'}];
  await h.ready();const text=h.texts(h.ui.rolePanel({member_id:'m'}));assert.match(text,/绑定重置/);assert.doesNotMatch(text,/配置未完成/);
});

test('截断外按原键读取的迟到结果不能污染新项目',async()=>{
  const d=deferred();const key='role-tracked-00000000',storage=new Map([['talk-role-intent:["p","human:a"]:saved',JSON.stringify([key])]]);
  const h=harness({storage,handler:(c,b)=>c.path.endsWith('/role-requests/'+key)?d.promise:limitedHistory(c,b)});h.backend.rows=oldHistory();h.ui.sync();await tick();
  h.ctx.projectId='other';h.ui.sync();await tick();d.resolve(response({request_key:key,status:'provisioned',member_id:'from-old-project'}));await tick();
  assert.equal(h.ui.state.rows.some(r=>r.member_id==='from-old-project'),false);
});

test('存储禁用时丢响应保留内存同键并明确提示刷新限制',async()=>{
  const storage={get(){throw Error('denied');},set(){throw Error('denied');},delete(){throw Error('denied');}};
  const h=harness({storage,handler:c=>{if(c.method==='POST')throw Error('lost');}});await h.ready();await h.fill();await h.ui.submit();
  assert.match(h.el('role-create-notice').textContent,/无法保留待确认请求/);const key=h.requests.find(r=>r.method==='POST').body.request_key;
  await h.ui.submit();assert.ok(h.requests.filter(r=>r.method==='POST').every(r=>r.body.request_key===key));
});
test('离开角色页立即清计时器，迟到回调也不读取',async()=>{
  const h=harness();h.backend.rows=[{request_key:'x',status:'requested',revision:1}];await h.ready();assert.equal(h.timers.size,1);
  const callback=[...h.timers.values()][0];h.ctx.active=false;h.ui.sync();const count=h.requests.length;callback();await tick();
  assert.equal(h.requests.length,count);assert.equal(h.timers.size,0);
});
test('A→B→A旧结果被世代挡住，不污染新上下文',async()=>{
  const d=deferred();let first=true;
  const h=harness({handler:c=>{if(c.path.includes('/role-requests?')&&first){first=false;return d.promise;}}});h.ui.sync();
  h.ctx.projectId='b';h.ui.sync();await tick();h.ctx.projectId='p';h.ui.sync();await tick();
  d.resolve(response([{request_key:'old',status:'failed',role_name:'旧项目结果'}]));await tick();
  assert.equal(h.ui.state.rows.length,0);assert.doesNotMatch(h.texts(h.el('role-request-list')),/旧项目/);
});
test('切换账号后迟到保存不会清新账号状态',async()=>{
  const d=deferred();const h=harness({handler:c=>c.method==='POST'?d.promise:undefined});await h.ready();await h.fill();const pending=h.ui.submit();
  h.ctx.accountId='human:b';h.ui.sync();await tick();d.resolve(response({request_key:'old',status:'requested'}));await pending;
  assert.equal(h.ui.state.attempt,null);assert.equal(h.ui.state.modalRow,null);assert.equal(h.ui.state.busy,false);
});
test('取消与继续带当前revision，409刷新后仍保留错误提示',async()=>{
  const h=harness({handler:c=>c.method==='POST'?response({detail:'role_request_revision_conflict'},409):undefined});await h.ready();
  await h.ui.mutate({request_key:'safe/x',revision:4},'resume');
  const post=h.requests.find(r=>r.method==='POST');assert.match(post.path,/safe%2Fx\/resume$/);assert.deepEqual(post.body,{expected_revision:4,confirm:true});
  assert.match(h.ui.state.error,/进度已变化/);
});
test('人工恢复丢响应后保持同一键和固定凭据版本，不自动另建恢复',async()=>{
  const h=harness({handler:c=>{if(c.method==='POST')throw Error('lost');}});await h.ready();
  await h.ui.recover({member_id:'a',credential_version:1});await h.ui.refresh();await h.ui.recover({member_id:'a',credential_version:2});
  const posts=h.requests.filter(r=>r.method==='POST');assert.deepEqual(posts[0].body,posts[1].body);assert.equal(posts[1].body.expected_credential_version,1);assert.equal(h.confirms(),1);
  assert.ok(posts.every(p=>!p.path.includes('rotate-key')));
});
test('宿主设置用服务端版本CAS，超安全整数拒绝写入',async()=>{
  const h=harness({handler:(c,b)=>{if(c.method==='POST'){b.host={enabled:true,config_version:1,host_label:c.body.host_label};return response(b.host);}}});await h.ready();h.el('role-request-host-name').value='local-2';await h.ui.setHost(true);
  assert.deepEqual(h.requests.find(r=>r.method==='POST').body,{expected_version:0,host_label:'local-2'});
  h.ui.state.host.config_version=Number.MAX_SAFE_INTEGER+1;const before=h.requests.length;await h.ui.setHost(false);assert.equal(h.requests.length,before);
});
test('旧服务不支持时禁止保存，不回退到返回Key的创建接口',async()=>{
  const h=harness({handler:c=>c.path.endsWith('/role-provision-host')?response({detail:'notfound'},404):undefined});await h.ready();await h.fill();await h.ui.submit();
  assert.equal(h.ui.state.supported,false);assert.equal(h.requests.filter(r=>r.method==='POST').length,0);assert.equal(h.ui.newButton().disabled,true);
});
test('陌生状态与恶意文本按纯文本展示，无继承键假状态',async()=>{
  const h=harness();h.backend.rows=[{request_key:'x',status:'__proto__',member_id:'a',role_name:'<img src=x onerror=alert(1)>'}];await h.ready();
  const text=h.texts(h.ui.rolePanel({member_id:'a'}));assert.match(text,/配置状态未知/);assert.doesNotMatch(text,/<img src=x/);assert.doesNotMatch(text,/\[object Object\]/);
});
test('目录切换时晚到模型结果不覆盖当前选择，已下架模型不可选择',async()=>{
  const d=deferred();const h=harness({handler:c=>c.path.includes('/r/model-choices')?d.promise:undefined});await h.ready();await h.ui.open();
  h.el('role-create-runner').value='r';const old=h.ui.chooseRunner();h.el('role-create-runner').value='new';await h.ui.chooseRunner();
  d.resolve(response([{runner_id:'r',choice_id:'late'}]));await old;assert.equal(h.ui.state.choices.length,0);
});

test('完成配置的详情不再重复成功状态或三步，仅保留有资格的绑定重置',async()=>{
  const h=harness();h.backend.rows=[{request_key:'x',member_id:'a',role_name:'助手',status:'provisioned',revision:8,credential_version:1,provision_job:{steps:{profile:{state:'succeeded'},key_file:{state:'skipped'},preflight:{state:'succeeded'}}}}];await h.ready();
  const text=h.texts(h.ui.rolePanel({member_id:'a'}));assert.match(text,/绑定重置/);assert.match(text,/必要时更新接入凭据/);assert.doesNotMatch(text,/配置已完成|配置进度|身份档案|配置检查|未启动|启动成功|关闭中/);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,0);assert.equal(h.timers.size,0);
});

test('角色详情没有返回自身入口，agent和无代际旧记录没有可用重置操作',async()=>{
  for(const human of [true,false]) {
    const h=harness({human});h.backend.rows=[{request_key:'role-completed-00000000',member_id:'agent:ready',role_name:'Kimi k2.8',status:'provisioned',revision:4,credential_version:1}];
    await h.ready();const panel=h.ui.rolePanel({member_id:'agent:ready'});
    if(!human){assert.equal(panel,null);continue;}
    const actions=panel.querySelectorAll().filter(n=>n.tagName==='BUTTON').map(n=>n.textContent);
    assert.deepEqual(actions,['绑定重置']);assert.equal(h.requests.some(r=>r.method==='POST'),false);
  }
});

test('绑定重置实际点击保留人工确认和recover载荷，不重选模型或直接轮换Key',async()=>{
  const h=harness();h.backend.rows=[{request_key:'role-ready-00000000',member_id:'agent:ready',status:'provisioned',revision:4,credential_version:2}];await h.ready();
  let confirmation='';h.deps.confirm=text=>{confirmation=text;return true;};
  const panel=h.ui.rolePanel({member_id:'agent:ready'});const button=panel.querySelectorAll().find(n=>n.tagName==='BUTTON'&&n.textContent==='绑定重置');
  await button.fire('click');const posts=h.requests.filter(r=>r.method==='POST');assert.equal(posts.length,1);
  assert.match(confirmation,/必要时更新 TALK 凭据并使旧凭据失效/);assert.match(confirmation,/不更换运行器或模型/);
  assert.equal(posts[0].body.kind,'recover');assert.equal(posts[0].body.member_id,'agent:ready');assert.equal(posts[0].body.expected_credential_version,2);
  assert.deepEqual(Object.keys(posts[0].body).sort(),['confirm','expected_credential_version','kind','member_id','request_key']);
  assert.equal(posts[0].path.endsWith('/role-requests'),true);assert.doesNotMatch(posts[0].path,/binding|rotate-key|service/);
});

test('绑定重置取消确认不发写请求，缺代际的已完成记录不提供操作',async()=>{
  const h=harness();h.backend.rows=[{request_key:'role-ready-00000000',member_id:'a',status:'provisioned',revision:4,credential_version:1}];await h.ready();
  h.deps.confirm=()=>false;const panel=h.ui.rolePanel({member_id:'a'});await panel.querySelectorAll().find(n=>n.tagName==='BUTTON').fire('click');
  assert.equal(h.requests.some(r=>r.method==='POST'),false);
  delete h.backend.rows[0].credential_version;await h.ui.refresh();assert.equal(h.ui.rolePanel({member_id:'a'}),null);
});

test('请求处理中详情和创建结果的绑定重置按钮均禁用，不产生重复恢复',async()=>{
  const d=deferred();const h=harness({handler:c=>c.method==='POST'?d.promise:undefined});
  const row={request_key:'role-ready-00000000',member_id:'a',status:'provisioned',revision:4,credential_version:1};
  h.backend.rows=[row];await h.ready();h.ui.state.modalRow={...row};
  const pending=h.ui.recover(row);
  const detail=h.ui.rolePanel({member_id:'a'});const result=h.el('role-create-result');
  for(const container of [detail,result]) {
    const reset=container.querySelectorAll().find(n=>n.tagName==='BUTTON'&&n.textContent==='绑定重置');
    assert.ok(reset);assert.equal(reset.disabled,true);
  }
  await h.ui.recover(row);assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
  d.resolve(response({...row,status:'requested'}));await pending;
});

test('详情移除进度大块后，处理中与失败仍有简短反馈及原继续或重置资格',async()=>{
  for(const human of [true,false])for(const kind of ['created','failed','manual']) {
    const h=harness({human});h.backend.rows=[{request_key:'role-state-00000000',member_id:'a',status:kind==='created'?'created':'failed',revision:4,credential_version:1,last_error_code:kind==='manual'?'manual_recovery_required':'preflight_failed'}];await h.ready();
    const panel=h.ui.rolePanel({member_id:'a'});const text=h.texts(panel);assert.doesNotMatch(text,/配置进度|身份档案|本机接入配置 ·|配置检查 ·/);
    const labels=panel.querySelectorAll().filter(n=>n.tagName==='BUTTON').map(n=>n.textContent);
    if(kind==='created'){assert.match(text,/等待宿主|正在配置/);assert.deepEqual(labels,[]);}
    else {assert.match(text,/配置未完成/);assert.equal(labels.includes(kind==='manual'?'绑定重置':'继续配置'),human);}
  }
});


test('新建请求固定自动首次启动，配置尚未完成时不显示已启动或发启动POST',async()=>{
  const h=harness();await h.ready();await h.fill();await h.ui.submit();
  const post=h.requests.find(r=>r.method==='POST');assert.equal(post.body.auto_start,true);
  assert.match(h.el('role-create-notice').textContent,/配置完成后将尝试自动启动/);
  assert.doesNotMatch(h.texts(h.el('role-create-result')),/启动成功|请求已提交|启动中/);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
  assert.equal(h.requests.some(r=>r.path.includes('/service/')),false);
});

test('旧缓存缺省、false、null和新true均沿原键原载荷重试，不追补意图',async()=>{
  for(const extra of [{},{auto_start:false},{auto_start:null},{auto_start:true}]) {
    const key='role-pinned-00000000';
    const payload={request_key:key,kind:'create',confirm:true,role_name:'原请求',role_description:null,runner_id:'r',choice_id:'c',...extra};
    const storage=new Map([['talk-role-intent:["p","human:a"]',JSON.stringify({key,payload})]]);
    const h=harness({storage});await h.ready();await h.ui.open();await h.ui.submit();
    assert.deepEqual(h.requests.find(r=>r.method==='POST').body,payload);
  }
});

test('自动启动新请求丢响应重建页面后仍保留true及同一请求',async()=>{
  const storage=new Map();const h=harness({storage,handler:c=>{if(c.method==='POST')throw Error('lost');}});
  await h.ready();await h.fill();await h.ui.submit();
  const payload=h.requests.find(r=>r.method==='POST').body;assert.equal(payload.auto_start,true);
  const reopened=harness({storage});await reopened.ready();await reopened.ui.open();await reopened.ui.submit();
  assert.deepEqual(reopened.requests.find(r=>r.method==='POST').body,payload);
});

async function completedAuto(h,extra={}) {
  await h.ready();await h.fill();await h.ui.submit();
  Object.assign(h.backend.rows[0],{status:'provisioned',member_id:'agent:auto',revision:4,credential_version:1,
    auto_start_status:'enqueued',auto_start_launch_id:'launch-public',auto_start_error_code:null,...extra});
  await h.ui.refresh();
}

test('入队只显示已提交，详情沿角色开关展示实际状态且无重复配置卡',async()=>{
  const h=harness();await completedAuto(h);
  assert.match(h.texts(h.el('role-create-result')),/配置已完成/);
  assert.match(h.texts(h.el('role-create-result')),/自动启动请求已提交/);
  assert.doesNotMatch(h.texts(h.el('role-create-result')),/启动成功|已就绪|启动中/);
  const detail=h.texts(h.ui.rolePanel({member_id:'agent:auto'}));
  assert.match(detail,/绑定重置/);assert.doesNotMatch(detail,/配置已完成|请求已提交|身份档案|启动成功/);
  assert.equal(h.ui.state.rows[0].auto_start_launch_id,'launch-public');
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});

test('人工意图、未受管和入队失败分别有简短反馈，刷新只读不重试启动',async()=>{
  for(const [status,code,message] of [
    ['not_eligible','auto_start_manual_intent_present',/已保留手动启停/],
    ['not_eligible','auto_start_control_kind_not_managed',/受管启动能力尚未确认/],
    ['not_eligible','auto_start_config_disabled',/宿主配置已关闭/],
    ['failed','auto_start_enqueue_failed',/自动启动请求提交失败/],
  ]) {
    const h=harness();await completedAuto(h,{auto_start_status:status,auto_start_error_code:code,auto_start_launch_id:null});
    assert.match(h.texts(h.el('role-create-result')),/配置已完成/);
    assert.match(h.texts(h.ui.rolePanel({member_id:'agent:auto'})),message);
    assert.doesNotMatch(h.texts(h.ui.rolePanel({member_id:'agent:auto'})),/配置已完成|身份档案|查看角色|启动成功/);
    await h.ui.refresh();assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
  }
});

test('配置失败取消不把pending意图当启动中，旧请求及恢复不显示自动启动反馈',async()=>{
  for(const extra of [
    {status:'failed',auto_start_status:'pending'},
    {status:'canceled',auto_start_status:'pending'},
    {auto_start:false},
    {kind:'recover'},
  ]) {
    const h=harness();await completedAuto(h,extra);
    assert.doesNotMatch(h.texts(h.el('role-create-result')),/自动启动请求已提交|启动成功|启动中/);
    assert.doesNotMatch(h.texts(h.ui.rolePanel({member_id:'agent:auto'})),/自动启动/);
  }
});

test('未知自动启动状态或错误码不冒充就绪、不展示后端任意错误正文',async()=>{
  for(const status of ['pending','__proto__',null]) {
    const h=harness();await completedAuto(h,{auto_start_status:status,auto_start_error_code:'<img src=x onerror=alert(1)>'});
    const text=h.texts(h.el('role-create-result'));
    assert.match(text,/结果尚未确认/);assert.doesNotMatch(text,/启动成功|已就绪|<img|alert\(1\)/);
  }
});

test('旧服务未确认auto意图时诚实提示，不仅凭提交载荷承诺自动启动',async()=>{
  const h=harness({handler:(c,b)=>{
    if(c.method==='POST') {const row={...c.body,status:'requested',revision:1};delete row.auto_start;b.rows=[row];return response(row);}
  }});
  await h.ready();await h.fill();await h.ui.submit();
  assert.match(h.el('role-create-notice').textContent,/未确认自动启动意图/);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});


test('新建等待时可刷新进度，并提示可关闭且不要重复创建',async()=>{
  const h=harness();await h.ready();await h.fill();await h.ui.submit();
  const text=h.texts(h.el('role-create-result'));
  assert.match(text,/请求已保存.*可以关闭.*请勿重复创建/);
  const refresh=h.el('role-create-result').querySelectorAll().find(n=>n.tagName==='BUTTON'&&n.textContent==='刷新进度');
  assert.ok(refresh);const before=h.requests.length;await refresh.fire('click');
  assert.ok(h.requests.length>before);assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});

test('配置完成后继续跟进实际启动，失败展示查看角色并停止轮询',async()=>{
  const h=harness();await completedAuto(h);
  h.backend.roles=[{member_id:'agent:auto',service:{observed:'starting',readiness_service:'pending'}}];
  await h.ui.refresh();assert.equal(h.timers.size,1);
  h.backend.roles[0].service={observed:'failed',readiness_service:'failed'};
  await h.ui.refresh();assert.equal(h.timers.size,0);
  assert.match(h.texts(h.el('role-create-result')),/角色配置已完成，但服务启动未完成/);
  const view=h.el('role-create-result').querySelectorAll().find(n=>n.tagName==='BUTTON'&&n.textContent==='查看角色');
  assert.ok(view);await view.fire('click');assert.equal(h.ctx.selected,'agent:auto');
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});

test('配置完成后只依据真实ready服务显示已启动',async()=>{
  const h=harness();await completedAuto(h);
  h.backend.roles=[{member_id:'agent:auto',service:{observed:'running',readiness_service:'ready'}}];
  await h.ui.refresh();assert.match(h.texts(h.el('role-create-result')),/角色配置已完成，服务已启动/);
  assert.equal(h.timers.size,0);
});


test('宿主关闭时提示先开启配置，不承诺自动处理且刷新不重发请求',async()=>{
  const h=harness();await h.ready();h.backend.host.enabled=false;
  await h.fill();await h.ui.submit();await h.ui.refresh();
  const text=h.texts(h.el('role-create-result'));
  assert.match(text,/请先开启宿主配置/);assert.doesNotMatch(text,/宿主会自动处理/);
  assert.match(text,/可以关闭.*请勿重复创建/);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);
});
