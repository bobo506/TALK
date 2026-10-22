'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {documentFixture}=require('./role_creation_dom.cjs');
const source=fs.readFileSync(require.resolve('../web/workspace.js'),'utf8');
const functions=source.slice(source.indexOf('function chatMemberName('),source.indexOf('function workspaceChatCandidates('));
function harness(){
  const h=documentFixture();
  for(const id of ['role-name-modal','role-name-input','role-name-status','role-name-save','role-name-cancel','role-name-edit']) {
    const n=h.document.createElement('div');n.id=id;h.elements.set(id,n);
  }
  const requests=[];let respond=async()=>({ok:true,json:async()=>({member_id:'agent:new',role_name:'新名称'})});
  const ctx=vm.createContext({document:h.document,console,activeProjectId:'p',myId:'human:a',blackboardOpen:true,
    workspaceUI:{mode:'roles'},projectAgents:[{member_id:'agent:new',role_name:'WorkBuddy-k3'},{member_id:'agent:old',role_name:'WorkBuddy接入验证'}],
    members:[{id:'agent:new',display_name:'被运行器覆盖的名称'}],currentMemberIsHuman:()=>true,
    roleRequestApp:{roleName:()=> '旧缓存名',setRoleName:()=>{}},
    apiFetch:async(path,options)=>{requests.push({path,...options});return respond();},
    renderWorkspaceList:()=>{},renderTaskDetailsPanel:()=>{},
  });
  vm.runInContext(functions,ctx);
  return {ctx,h,requests,respond:fn=>respond=fn,open:()=>ctx.openRoleNameEditor(ctx.projectAgents[0]),
    submit:()=>ctx.saveRoleName({preventDefault(){}})};
}
test('项目创建名称优先于运行器全局名/旧缓存；两个同模型身份各显示自己的名称',()=>{
  const {ctx}=harness();assert.equal(ctx.workspaceMemberName('agent:new'),'WorkBuddy-k3');
  assert.equal(ctx.workspaceMemberName('agent:old'),'WorkBuddy接入验证');
});
test('改名使用精确项目/成员PATCH，成功只更新项目角色，保留全局名',async()=>{
  const x=harness();x.open();assert.equal(x.h.el('role-name-input').value,'WorkBuddy-k3');
  x.h.el('role-name-input').value='  新名称  ';await x.submit();
  assert.equal(x.requests.length,1);assert.equal(x.requests[0].path,'/api/projects/p/roles/agent%3Anew');
  assert.equal(x.requests[0].method,'PATCH');assert.deepEqual(JSON.parse(x.requests[0].body),{role_name:'新名称'});
  assert.equal(x.ctx.projectAgents[0].role_name,'新名称');assert.equal(x.ctx.projectAgents[1].role_name,'WorkBuddy接入验证');
  assert.equal(x.ctx.members[0].display_name,'被运行器覆盖的名称');
  assert.equal(x.h.el('role-name-modal').classList.contains('hidden'),true);
});
test('冲突保留草稿并允许重试，不把失败的名称写入列表',async()=>{
  const x=harness();x.respond(async()=>({ok:false,json:async()=>({detail:'role_name_conflict'})}));
  x.open();x.h.el('role-name-input').value='重复名';await x.submit();
  assert.match(x.h.el('role-name-status').textContent,/已被使用/);assert.equal(x.h.el('role-name-input').value,'重复名');
  assert.equal(x.h.el('role-name-save').disabled,false);assert.equal(x.ctx.projectAgents[0].role_name,'WorkBuddy-k3');
});
test('空白和65个Unicode字符都在发送前阻止',async()=>{
  const x=harness();x.open();for(const value of ['   ','😀'.repeat(65)]){x.h.el('role-name-input').value=value;await x.submit();}
  assert.equal(x.requests.length,0);
});
test('取消不写数据并恢复编辑按钮焦点',()=>{
  const x=harness();x.open();x.ctx.closeRoleNameEditor();assert.equal(x.requests.length,0);
  assert.equal(x.h.document.activeElement,x.h.el('role-name-edit'));
});
test('保存期间切账号/项目，迟到回执不覆盖新上下文',async()=>{
  const x=harness();let done;x.respond(()=>new Promise(resolve=>done=resolve));
  x.open();x.h.el('role-name-input').value='新名称';const pending=x.submit();
  x.ctx.activeProjectId='other';x.ctx.myId='human:b';x.ctx.syncRoleNameEditor();
  done({ok:true,json:async()=>({member_id:'agent:new',role_name:'新名称'})});await pending;
  assert.equal(x.ctx.projectAgents[0].role_name,'WorkBuddy-k3');assert.equal(x.h.el('role-name-modal').classList.contains('hidden'),true);
});
test('agent只读及归档角色不可打开编辑器',()=>{
  const x=harness();x.ctx.currentMemberIsHuman=()=>false;x.open();assert.equal(vm.runInContext('roleNameUI.context',x.ctx),null);
  x.ctx.currentMemberIsHuman=()=>true;x.ctx.openRoleNameEditor({...x.ctx.projectAgents[0],archived:true});assert.equal(vm.runInContext('roleNameUI.context',x.ctx),null);
});
test('真实页面有可访问名称、静态铅笔图标和同风格对话框',()=>{
  const html=fs.readFileSync(require.resolve('../web/index.html'),'utf8');
  assert.match(html,/aria-labelledby="role-name-title"/);assert.match(html,/id="role-name-input"/);
  assert.match(source,/修改角色名称/);assert.match(source,/stroke="currentColor"/);assert.match(source,/icon-action subtle role-name-edit/);
});
