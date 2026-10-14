'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createRoleRequestUI}=require('../web/role-creation.js');
const {documentFixture}=require('./role_creation_dom.cjs');
const tick=()=>new Promise(r=>setImmediate(r));
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const binding=()=>({runner_id:'kimi',runtime:'kimi-code',model_source:'builtin',provider_id:'managed:kimi-code',connection_ref:'native-kimi-code-managed-login',model_id:'kimi-for-coding',model_alias:'kimi-code/kimi-for-coding',model_display_name:'K2.8 Preview'});
function harness(handler) {
  const dom=documentFixture(),ctx={active:true,projectId:'p',accountId:'human:a',human:true,settings:false},calls=[];
  const data={runners:[{runner_id:'kimi',runtime:'kimi-code',display_name:'Kimi Code',adapter_status:'unverified',control_kind:'unknown'}],choices:[],agents:[{binding_state:'bound',binding:binding()}]};
  const ui=createRoleRequestUI({document:dom.document,context:()=>ctx,storage:null,setTimeout:()=>1,clearTimeout:()=>{},newKey:()=>`role-${'a'.repeat(32)}`,confirm:()=>true,refreshRoster:async()=>{},renderDetails:()=>{},selectRole:()=>{},
    api:async(path,options={})=>{
      const c={path,method:options.method||'GET',body:options.body?JSON.parse(options.body):null};calls.push(c);
      const handled=await handler?.(c,data);if(handled!==undefined)return handled;
      if(path.endsWith('/role-provision-host'))return response({enabled:false,config_version:0});
      if(path.includes('/role-requests?')||path.endsWith('/roles'))return response([]);
      if(path.endsWith('/agents'))return response(data.agents);
      if(path==='/api/runners')return response(data.runners);
      if(path.includes('/model-choices')&&c.method==='GET')return response(path.includes('include_retired')?data.choices:data.choices.filter(r=>!r.retired_at));
      if(path.endsWith('/model-choices')&&c.method==='POST'){const choice={...c.body,runner_id:'kimi',choice_id:'c',source_kind:'declared',retired_at:null,api_key:'SECRET',lease_token:'TOKEN'};data.choices.push(choice);return response(choice,201);}
      if(path.endsWith('/role-requests')&&c.method==='POST')return response({...c.body,status:'requested',revision:1});
      throw Error('unexpected '+path);
    }});
  async function ready(){ui.sync();await tick();await ui.open();dom.el('role-create-runner').value='kimi';await ui.chooseRunner();}
  return {...dom,ui,ctx,data,calls,ready,posts:()=>calls.filter(c=>c.method==='POST')};
}
test('创建目录接受已登记未核验/可发现/外部运行器，排除下架与未知状态',async()=>{
  const h=harness();h.data.runners.push({runner_id:'visible',adapter_status:'discoverable',control_kind:'external_session'},{runner_id:'retired',adapter_status:'retired',control_kind:'managed_cli'},{runner_id:'bad',adapter_status:'__proto__'});await h.ready();
  assert.deepEqual(h.ui.state.runners.map(r=>r.runner_id),['kimi','visible']);assert.equal(h.posts().length,0);assert.match(h.el('role-create-notice').textContent,/尚未确认/);
});
test('空模型目录以真实项目绑定提供登记入口，不自动写入或伪造模型',async()=>{
  const h=harness();await h.ready();assert.match(h.texts(h.el('role-create-model-setup')),/K2.8 Preview/);assert.equal(h.ui.state.choices.length,0);assert.equal(h.posts().length,0);
});
test('真人点击登记只写公开模型维度，取得实际choice后才可保存意图',async()=>{
  const h=harness();await h.ready();const action=h.el('role-create-model-setup').children.find(n=>n.tagName==='BUTTON');await action.fire('click');
  assert.deepEqual(h.posts()[0].body,{model_id:'kimi-for-coding',model_source:'builtin',provider_id:'managed:kimi-code',connection_ref:'native-kimi-code-managed-login',model_alias:'kimi-code/kimi-for-coding',model_display_name:'K2.8 Preview'});
  assert.equal(h.el('role-create-model').value,'c');assert.doesNotMatch(JSON.stringify(h.ui.state),/SECRET|TOKEN/);
  h.el('role-create-name').value='新助手';await h.ui.submit();assert.equal(h.posts()[1].body.choice_id,'c');assert.equal(h.posts()[1].path,'/api/projects/p/role-requests');
  assert.equal(h.ui.state.runners[0].adapter_status,'unverified');assert.equal(h.ui.state.runners[0].control_kind,'unknown');
});
test('已有活动模型目录优先，无额外读取项目绑定或登记入口',async()=>{
  const h=harness();h.data.choices=[{...binding(),choice_id:'existing',retired_at:null}];await h.ready();assert.equal(h.ui.state.choices[0].choice_id,'existing');assert.equal(h.ui.state.modelSeeds.length,0);assert.equal(h.calls.some(c=>c.path.endsWith('/agents')),false);
});
test('登记处理中重复点击只发一次模型POST',async()=>{
  const d=deferred();const h=harness(c=>c.method==='POST'?d.promise:undefined);await h.ready();const seed=h.ui.state.modelSeeds[0];const first=h.ui.registerModel(seed);await tick();await h.ui.registerModel(seed);assert.equal(h.posts().length,1);d.resolve(response({...seed.payload,runner_id:'kimi',choice_id:'c'}));await first;
});
test('登记响应丢失后重试先读取已存在的模型，不再次写目录',async()=>{
  const h=harness((c,b)=>{if(c.method==='POST'){b.choices.push({...c.body,runner_id:'kimi',choice_id:'created',source_kind:'verified',model_display_name:'保留已有名称'});throw Error('lost SECRET');}});await h.ready();const seed=h.ui.state.modelSeeds[0];await h.ui.registerModel(seed);assert.doesNotMatch(h.el('role-create-notice').textContent,/SECRET/);await h.ui.registerModel(seed);assert.equal(h.posts().length,1);assert.equal(h.el('role-create-model').value,'created');assert.equal(h.ui.state.choices[0].model_display_name,'保留已有名称');
});
test('项目模型绑定变化时拒绝旧卡片登记',async()=>{
  const h=harness();await h.ready();const seed=h.ui.state.modelSeeds[0];h.data.agents[0].binding.model_id='changed';await h.ui.registerModel(seed);assert.equal(h.posts().length,0);assert.match(h.el('role-create-notice').textContent,/配置已变化/);
});
test('已下架的同维度模型不复活、不覆盖',async()=>{
  const h=harness();h.data.choices=[{...binding(),choice_id:'retired',retired_at:'2026-10-14'}];await h.ready();await h.ui.registerModel(h.ui.state.modelSeeds[0]);assert.equal(h.posts().length,0);assert.match(h.el('role-create-notice').textContent,/已下架/);assert.equal(h.ui.state.choices.length,0);
});
test('缺少完整绑定事实或不属于该运行器时没有登记入口',async()=>{
  for(const change of [b=>{delete b.provider_id;},b=>{b.runner_id='other';},b=>{b.runtime='dsh';}]) {const h=harness();change(h.data.agents[0].binding);await h.ready();assert.equal(h.ui.state.modelSeeds.length,0);assert.equal(h.posts().length,0);assert.match(h.el('role-create-notice').textContent,/管理员先准备/);}
});
test('切换为Agent账号后直调登记也不写入',async()=>{
  const h=harness();await h.ready();const seed=h.ui.state.modelSeeds[0];h.ctx.human=false;await h.ui.registerModel(seed);assert.equal(h.posts().length,0);
});
test('目录核对期间关闭弹窗或切项目，不发送后续POST',async()=>{
  for(const change of [h=>h.ui.close(),h=>{h.ctx.projectId='other';h.ui.sync();}]) {const d=deferred();let hold=false;const h=harness(c=>hold&&c.path.endsWith('/agents')?d.promise:undefined);await h.ready();const seed=h.ui.state.modelSeeds[0];hold=true;const work=h.ui.registerModel(seed);await tick();change(h);d.resolve(response(h.data.agents));await work;assert.equal(h.posts().length,0);}
});
test('登记POST迟到响应不能覆盖新账号状态',async()=>{
  const d=deferred();const h=harness(c=>c.method==='POST'?d.promise:undefined);await h.ready();const seed=h.ui.state.modelSeeds[0];const work=h.ui.registerModel(seed);await tick();h.ctx.accountId='human:b';h.ui.sync();d.resolve(response({...seed.payload,runner_id:'kimi',choice_id:'late'}));await work;assert.equal(h.ui.state.choices.length,0);assert.equal(h.ui.state.busy,false);
});
test('同一模型的重复项目绑定只生成一份登记载荷',async()=>{
  const h=harness();h.data.agents.push({binding_state:'bound',binding:{...binding(),model_display_name:'另一名称'}});await h.ready();assert.equal(h.ui.state.modelSeeds.length,1);
});
test('登记结果维度或运行器不匹配时不选入表单',async()=>{
  const h=harness(c=>c.method==='POST'?response({...c.body,runner_id:'other',choice_id:'bad'}):undefined);await h.ready();await h.ui.registerModel(h.ui.state.modelSeeds[0]);assert.equal(h.ui.state.choices.length,0);assert.match(h.el('role-create-notice').textContent,/结果尚未确认/);
});
