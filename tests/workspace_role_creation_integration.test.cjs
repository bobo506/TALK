'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {documentFixture}=require('./role_creation_dom.cjs');
test('真实页面模块启动顺序、toolbar、名册刷新、角色详情与离页同步连通',async()=>{
  const h=documentFixture(),doc=h.document;
  const lookup=doc.getElementById;
  doc.getElementById=id=>{let n=lookup(id);if(!n){n=doc.createElement('div');n.id=id;h.elements.set(id,n);}return n;};
  doc.querySelector=selector=>doc.getElementById(selector);
  doc.addEventListener=()=>{};
  const requests=[],storage=new Map();let rows=[];
  const ctx=vm.createContext({document:doc,console,crypto:webcrypto,Uint8Array,Map,Set,URLSearchParams,
    window:{confirm:()=>true,matchMedia:()=>({matches:false})},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    setTimeout:()=>1,clearTimeout:()=>{},activeProjectId:'p',myId:'human:a',blackboardOpen:true,
    members:[{id:'human:a',kind:'human'}],projectAgents:[],projectTasks:[],groups:[],userBadge:doc.getElementById('badge'),
    currentMemberIsHuman:()=>true,getActiveGroup:()=>null,canEnterGroup:()=>false,
    blackboardTitle:doc.getElementById('title'),blackboardDescription:doc.getElementById('description'),
    blackboardColumns:doc.getElementById('columns'),blackboardSummary:doc.getElementById('summary'),blackboardEmpty:doc.getElementById('empty'),
    loadProjectAgents:async()=>{ctx.projectAgents=rows.some(r=>r.member_id)?[{member_id:'agent:new',role_description:'负责检查',binding:null,binding_state:'unconfigured',service:null}]:[];},
    renderTaskDetailsPanel:()=>ctx.renderWorkspaceRoleDetails(),
    apiFetch:async(path,options={})=>{requests.push({path,method:options.method||'GET'});let data;
      if(path.endsWith('/role-provision-host'))data={enabled:true,host_label:'local',config_version:0};
      else if(path.includes('/role-requests?'))data=rows;
      else if(path.endsWith('/roles'))data=rows.some(r=>r.member_id)?[{member_id:'agent:new',role_name:'新助手'}]:[];
      else if(path==='/api/runners')data=[{runner_id:'r',display_name:'DSH',adapter_status:'adapted',control_kind:'managed_cli'}];
      else if(path.endsWith('/model-choices'))data=[{runner_id:'r',choice_id:'c',model_alias:'flash'}];
      else if(path.endsWith('/role-requests')){const p=JSON.parse(options.body);rows=[{...p,member_id:'agent:new',status:'created',revision:2,credential_version:1,lease_held:true}];data=rows[0];}
      else throw Error('unexpected path '+path);
      return {ok:true,status:200,json:async()=>data};
    }});
  vm.runInContext(fs.readFileSync('web/role-creation.js','utf8'),ctx);
  vm.runInContext(fs.readFileSync('web/workspace.js','utf8'),ctx);
  vm.runInContext('workspaceUI.mode="roles"; renderWorkspaceList();',ctx);
  await new Promise(resolve=>setImmediate(resolve));
  const controller=vm.runInContext('roleRequestApp',ctx);
  const toolbar=doc.getElementById('role-service-batch-actions');assert.match(h.texts(toolbar),/创建角色/);
  await controller.open();h.el('role-create-runner').value='r';await controller.chooseRunner();h.el('role-create-model').value='c';h.el('role-create-name').value='新助手';await controller.submit();
  assert.equal(ctx.projectAgents[0].member_id,'agent:new');assert.match(h.texts(ctx.blackboardColumns),/新助手/);
  const viewRole=h.el('role-create-result').querySelectorAll().find(n=>n.tagName==='BUTTON'&&n.textContent==='查看角色');
  assert.ok(viewRole,'创建结果应提供查看角色入口');await viewRole.fire('click');
  assert.equal(controller.state.modal,false);assert.ok(h.el('role-create-modal').classList.contains('hidden'));
  assert.equal(vm.runInContext('workspaceUI.selectedRole',ctx),'agent:new');
  assert.equal(vm.runInContext('workspaceUI.roleSelection',ctx),'role');
  assert.equal(doc.getElementById('role-details-name-panel').classList.contains('hidden'),false);
  assert.match(h.texts(doc.getElementById('role-details-name-panel')),/配置进度/);
  assert.doesNotMatch(h.texts(doc.getElementById('role-details-name-panel')),/查看角色/);
  Object.assign(rows[0],{status:'provisioned',revision:4,lease_held:false});await controller.refresh();
  assert.match(h.texts(doc.getElementById('role-details-name-panel')),/配置已完成/);
  assert.match(h.texts(doc.getElementById('role-details-name-panel')),/恢复本机接入/);
  assert.doesNotMatch(h.texts(doc.getElementById('role-details-name-panel')),/查看角色/);
  assert.equal(requests.filter(r=>r.method==='POST').length,1);
  vm.runInContext('workspaceUI.mode="tasks";syncWorkspaceLayout();',ctx);
  assert.equal(controller.state.active,false);assert.ok(doc.getElementById('role-create-modal').classList.contains('hidden'));
});
