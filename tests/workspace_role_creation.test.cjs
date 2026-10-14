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
  return {...dom,ui,ctx,requests,timers,backend,storage,ready,fill,confirms:()=>confirms};
}
test('选择真实目录并提交单一人类意图，未知凭据字段不进入状态或存储',async()=>{
  const h=harness();await h.ready();await h.fill();await h.ui.submit();
  const posts=h.requests.filter(r=>r.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].path,'/api/projects/p/role-requests');
  assert.deepEqual(Object.keys(posts[0].body).sort(),['choice_id','confirm','kind','request_key','role_description','role_name','runner_id'].sort());
  assert.equal(posts[0].body.role_name,'审查助手');assert.equal(posts[0].body.choice_id,'c');
  assert.equal(h.el('role-create-submit').disabled,true);
  assert.doesNotMatch(JSON.stringify(h.ui.state),/SECRET|TOKEN/);assert.doesNotMatch([...h.storage.values()].join(''),/SECRET|TOKEN/);
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
  await h.ui.refresh();assert.match(h.texts(h.ui.rolePanel({member_id:'new:member'})),/配置已完成/);assert.equal(h.timers.size,0);
  assert.ok(h.requests.some(r=>r.method==='GET'&&r.path.endsWith('/role-requests/'+saved.request_key)));
  const reopened=harness({storage,handler:limitedHistory});reopened.backend.rows=h.backend.rows;await reopened.ready();
  assert.match(reopened.texts(reopened.ui.rolePanel({member_id:'new:member'})),/配置已完成/);assert.equal(reopened.requests.filter(r=>r.method==='POST').length,0);
  reopened.ctx.accountId='human:b';reopened.ui.sync();await tick();
  assert.equal(reopened.ui.state.recentKeys.length,0);
  reopened.ctx.projectId='other';reopened.ctx.accountId='human:a';reopened.ui.sync();await tick();
  assert.equal(reopened.ui.state.recentKeys.length,0);
});

test('同一角色以最新配置请求展示，历史失败不盖住新恢复结果',async()=>{
  const h=harness({handler:limitedHistory});h.backend.rows=[
    {request_key:'role-earlier-00000000',member_id:'m',status:'failed',revision:2,created_at:'2026-10-12T00:00:00Z'},
    {request_key:'role-recover-00000000',member_id:'m',status:'provisioned',revision:3,created_at:'2026-10-13T00:00:00Z'}];
  await h.ready();const text=h.texts(h.ui.rolePanel({member_id:'m'}));assert.match(text,/配置已完成/);assert.doesNotMatch(text,/配置未完成/);
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
  const text=h.texts(h.ui.rolePanel({member_id:'a'}));assert.match(text,/配置状态未知/);assert.match(text,/<img src=x/);assert.doesNotMatch(text,/\[object Object\]/);
});
test('目录切换时晚到模型结果不覆盖当前选择，已下架模型不可选择',async()=>{
  const d=deferred();const h=harness({handler:c=>c.path.includes('/r/model-choices')?d.promise:undefined});await h.ready();await h.ui.open();
  h.el('role-create-runner').value='r';const old=h.ui.chooseRunner();h.el('role-create-runner').value='new';await h.ui.chooseRunner();
  d.resolve(response([{runner_id:'r',choice_id:'late'}]));await old;assert.equal(h.ui.state.choices.length,0);
});
test('完成配置只展示配置步骤，不产生服务启动POST或列表三状态',async()=>{
  const h=harness();h.backend.rows=[{request_key:'x',member_id:'a',role_name:'助手',status:'provisioned',revision:8,provision_job:{steps:{profile:{state:'succeeded'},key_file:{state:'skipped'},preflight:{state:'succeeded'}}}}];await h.ready();
  const text=h.texts(h.ui.rolePanel({member_id:'a'}));assert.match(text,/配置已完成/);assert.match(text,/身份档案 · 完成/);assert.doesNotMatch(text,/未启动|启动成功|关闭中/);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,0);assert.equal(h.timers.size,0);
});
