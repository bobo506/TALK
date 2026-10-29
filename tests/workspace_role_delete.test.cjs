'use strict';
const {test}=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {documentFixture}=require('./role_creation_dom.cjs');
const source=fs.readFileSync(require.resolve('../web/workspace.js'),'utf8');
const deletion=source.slice(source.indexOf('const roleDeleteUI ='),source.indexOf('function workspaceRoleServicePanel('));
function harness(){
  const dom=documentFixture(),calls=[],timers=new Map();let confirmed=true,reply,seq=0;
  const element=(tag,cls,text)=>{const n=dom.document.createElement(tag);n.className=cls||'';if(text)n.textContent=text;
    Object.defineProperty(n,'childElementCount',{get:()=>n.children.length});return n;};
  const ctx=vm.createContext({document:dom.document,myId:'human:qa',activeProjectId:'prj_a',projectAgentRequest:0,
    projectAgents:[{member_id:'agent:a',role_name:'角色 A',deletion:null,service:{observed:'stopped',ownership_held:false}},{member_id:'agent:b'}],
    projectTasks:[{id:286,status:'queued',control_status:'paused'}],members:[],currentMemberIsHuman:()=>true,
    workspaceMemberName:()=> '角色 A',roleServiceView:role=>({service:role.service,provided:Boolean(role.service)}),
    workspaceEl:element,workspaceButton:(text,fn,cls)=>{const n=element('button',cls,text);n.addEventListener('click',fn);return n;},
    renderWorkspaceList(){},renderTaskDetailsPanel(){},renderWorkspaceRoleDetails(){},
    window:{confirm:()=>confirmed},setTimeout:fn=>{timers.set(++seq,fn);return seq;},clearTimeout:id=>timers.delete(id),
    apiFetch:async(url,opts)=>{calls.push({url,opts});return reply ? reply() : {ok:true,json:async()=>({member_id:'agent:a',status:'pending',revision:1})};},
  });
  vm.runInContext(deletion,ctx);
  vm.runInContext(source.match(/function workspaceRoles\(\) \{[\s\S]*?\n\}/)[0],ctx);
  return {ctx,calls,timers,dom,cancel(){confirmed=false;},respond(fn){reply=fn;},button(){return ctx.roleDeleteButton(ctx.projectAgents[0]);},
    role(){return ctx.projectAgents[0];},state(){return vm.runInContext('roleDeleteUI',ctx);}};
}
test('真实删除按钮确认后发 JSON，显示待清理并保留任务',async()=>{
  const x=harness();await x.button().fire('click');
  assert.equal(x.calls[0].opts.method,'POST');assert.equal(x.calls[0].opts.headers['Content-Type'],'application/json');
  assert.deepEqual(JSON.parse(x.calls[0].opts.body),{confirm_member_id:'agent:a'});
  assert.equal(x.role().archived,true);assert.equal(x.role().deletion.status,'pending');
  assert.equal(x.ctx.projectTasks[0].id,286);assert.equal(x.ctx.projectTasks[0].control_status,'paused');
  assert.equal(x.button().disabled,true);
});
test('取消、Agent只读和运行状态禁止删除入口',async()=>{
  const x=harness();x.cancel();await x.button().fire('click');assert.equal(x.calls.length,0);
  x.ctx.currentMemberIsHuman=()=>false;assert.equal(x.button(),null);
  x.ctx.currentMemberIsHuman=()=>true;x.role().service.ownership_held=true;assert.equal(x.button().disabled,true);
});
test('未闭环任务的拒绝说明可读，不改变原角色',async()=>{
  const x=harness();x.respond(()=>({ok:false,json:async()=>({detail:'role_has_active_tasks'})}));
  await x.button().fire('click');assert.equal(x.role().archived,undefined);
  assert.match(x.dom.texts(x.ctx.workspaceRoleDeletePanel(x.role())),/未闭环任务/);
});
test('清理失败给出原因，再点删除不要求重新确认',async()=>{
  const x=harness();x.role().archived=true;x.role().deletion={status:'failed',error_code:'cleanup_busy',steps:{credentials:'failed',startup_config:'pending'}};
  assert.match(x.dom.texts(x.ctx.workspaceRoleDeletePanel(x.role())),/资源清理未完成/);
  assert.match(x.dom.texts(x.ctx.workspaceRoleDeletePanel(x.role())),/资源正被占用/);
  x.cancel();await x.button().fire('click');assert.equal(x.calls.length,1);assert.equal(x.role().deletion.status,'pending');
});
test('迟到的项目或账号回执不能移除新上下文的角色',async()=>{
  const x=harness();let finish;x.respond(()=>new Promise(resolve=>finish=resolve));
  const pending=x.ctx.deleteWorkspaceRole('agent:a');await Promise.resolve();
  x.ctx.activeProjectId='prj_b';x.ctx.myId='human:other';
  finish({ok:true,json:async()=>({member_id:'agent:a',status:'complete'})});await pending;
  assert.equal(x.ctx.projectAgents.length,2);assert.equal(x.role().archived,undefined);
});
test('同一角色在途重复点击只发一次',async()=>{
  const x=harness();let finish;x.respond(()=>new Promise(resolve=>finish=resolve));
  const pending=x.ctx.deleteWorkspaceRole('agent:a');await Promise.resolve();await x.ctx.deleteWorkspaceRole('agent:a');
  assert.equal(x.calls.length,1);finish({ok:true,json:async()=>({member_id:'agent:a',status:'pending'})});await pending;
});
test('轮询完成后清除本地清理记录，历史不变，离页停止轮询',async()=>{
  const x=harness();x.role().deletion={status:'cleaning'};x.ctx.roleDeleteSync(x.role());
  assert.equal(x.timers.size,1);const tick=[...x.timers.values()][0];x.timers.clear();
  x.respond(()=>({ok:true,json:async()=>({member_id:'agent:a',status:'complete'})}));await tick();
  assert.equal(x.ctx.projectAgents.length,1);assert.equal(x.ctx.projectAgents[0].member_id,'agent:b');assert.equal(x.ctx.projectTasks[0].id,286);
  x.ctx.roleDeleteSync(null);assert.equal(x.timers.size,0);
});
test('详情删除按钮接在启动关闭控件旁，失败原因显示在按钮下方',()=>{
  assert.match(source,/controls\?\.children\[0\] \|\| section/);
  assert.match(source,/const deletePanel = workspaceRoleDeletePanel\(role\)/);
  const x=harness();x.role().archived=true;x.role().deletion={status:'failed',error_code:'cleanup_busy'};
  const panel=x.ctx.workspaceRoleDeletePanel(x.role());
  const nodes=Array.from(panel.children);
  const index=nodes.findIndex(node=>node.className==='role-service-button role-delete-button');
  const reason=index>=0?nodes.slice(index+1).find(node=>node.className==='role-delete-reason'):null;
  assert.ok(index>=0,'删除按钮仍在');
  assert.ok(reason,'原因说明在按钮之后');
  assert.match(reason.textContent,/资源清理未完成/);
});
test('删除被接受立即从正常角色集合消失，不再有独立清理面板',async()=>{
  const x=harness();await x.button().fire('click');
  assert.deepEqual(Array.from(x.ctx.workspaceRoles(),r=>r.member_id),['agent:b']);
  assert.equal(x.ctx.projectAgents.length,2);
  assert.equal(x.ctx.workspaceRoleCleanupPanel,undefined);
  assert.equal(x.ctx.projectTasks[0].control_status,'paused');
});

test('清理失败角色回到正常列表，原因只在详情删除按钮下方',()=>{
  const x=harness();x.role().archived=true;x.role().deletion={status:'failed',steps:{private_state:'failed'},error_code:'cleanup_busy'};
  assert.deepEqual(Array.from(x.ctx.workspaceRoles(),r=>r.member_id),['agent:a','agent:b']);
  assert.match(x.dom.texts(x.ctx.workspaceRoleDeletePanel(x.role())),/资源清理未完成/);
  assert.match(x.dom.texts(x.ctx.workspaceRoleDeletePanel(x.role())),/资源正被占用/);
  x.ctx.currentMemberIsHuman=()=>false;assert.equal(x.ctx.workspaceRoleDeletePanel(x.role()),null);
});

test('没有选中角色时仍在角色页跟进清理，离页停止跟进',()=>{
  assert.match(source,/roleDeleteSync\(blackboardOpen && workspaceUI.mode === "roles" && currentMemberIsHuman\(\)/);
  assert.match(source,/projectAgents.find\(item => \["pending", "cleaning"\].includes\(item.deletion\?\.status\)\)/);
  assert.doesNotMatch(source,/workspaceRoleCleanupPanel/);
});

test('旧状态不能覆盖较新的重试，旧服务不显示删除按钮',()=>{
  const x=harness();x.role().deletion={status:'pending',revision:3};
  x.ctx.roleDeleteApply({account:'human:qa',project:'prj_a',member:'agent:a'},{member_id:'agent:a',status:'failed',revision:2});
  assert.equal(x.role().deletion.revision,3);assert.equal(x.role().deletion.status,'pending');
  delete x.role().deletion;assert.equal(x.button(),null);
});
