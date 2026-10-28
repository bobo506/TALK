'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {documentFixture}=require('./role_creation_dom.cjs');
const source=fs.readFileSync(require.resolve('../web/workspace.js'),'utf8');
const part=source.slice(source.indexOf('const roleStartupUI ='),source.indexOf('function renderWorkspaceRoleDetails()'));
function fixture(){
  const h=documentFixture(),requests=[];
  let respond=async()=>({ok:true,json:async()=>({enabled:true,revision:1,updated_at:'fixture'})});
  const role={member_id:'agent:one',binding_state:'bound',service:{control_kind:'managed_cli'},startup:{enabled:false,revision:0,last_activation:null}};
  const ctx=vm.createContext({document:h.document,activeProjectId:'p',myId:'human:a',projectAgents:[role],
    currentMemberIsHuman:()=>true,roleServiceView:r=>({service:r.service}),renderWorkspaceRoleDetails:()=>{},
    workspaceEl:(tag,css='',text='')=>{const e=h.document.createElement(tag);e.className=css;e.textContent=text;return e;},
    apiFetch:async(path,options)=>{requests.push({path,...options});return respond();}});
  vm.runInContext(part,ctx);
  return {h,ctx,role,requests,respond:fn=>respond=fn,panel:()=>ctx.workspaceRoleStartupPanel(role),save:v=>ctx.saveRoleStartup(role.member_id,v)};
}
function checkbox(panel){return panel.children[0].children[0];}
test('默认不勾选，标签可访问、下次加载才生效，单纯渲染没有写请求',()=>{
  const x=fixture(),panel=x.panel();assert.equal(checkbox(panel).checked,false);
  assert.match(x.h.texts(panel),/随项目自动启动/);assert.match(x.h.texts(panel),/本次手动关闭后不会再次拉起/);
  assert.equal(x.requests.length,0);
});
test('保存只PUT精确项目/成员选择，JSON头正确，不触发启停',async()=>{
  const x=fixture();await x.save(true);assert.equal(x.requests.length,1);
  assert.equal(x.requests[0].path,'/api/projects/p/roles/agent%3Aone/startup');
  assert.equal(x.requests[0].method,'PUT');assert.deepEqual(JSON.parse(x.requests[0].body),{enabled:true});
  assert.equal(x.requests[0].headers['Content-Type'],'application/json');assert.equal(checkbox(x.panel()).checked,true);
});
test('请求失败恢复原值并可重试，不显示HTTP正文',async()=>{
  const x=fixture();x.respond(async()=>({ok:false,json:async()=>({detail:'fixture-secret'})}));
  await x.save(true);const p=x.panel();assert.equal(checkbox(p).checked,false);assert.equal(checkbox(p).disabled,false);
  assert.match(x.h.texts(p),/保存失败/);assert.doesNotMatch(x.h.texts(p),/fixture-secret/);
});
test('保存期间只一份请求；旧列表响应不覆盖已保存的新版本',async()=>{
  const x=fixture();let done;x.respond(()=>new Promise(resolve=>done=resolve));
  const request=x.save(true);assert.equal(checkbox(x.panel()).disabled,true);await x.save(false);assert.equal(x.requests.length,1);
  done({ok:true,json:async()=>({enabled:true,revision:2})});await request;
  x.role.startup={enabled:false,revision:0};assert.equal(checkbox(x.panel()).checked,true);
  x.role.startup={enabled:false,revision:3};assert.equal(checkbox(x.panel()).checked,false);
});
test('切账号/项目后旧回执不能回填或释放新请求的busy',async()=>{
  const x=fixture();let first,second;x.respond(()=>new Promise(resolve=>first=resolve));
  const old=x.save(true);x.ctx.activeProjectId='other';x.ctx.myId='human:b';x.panel();
  x.respond(()=>new Promise(resolve=>second=resolve));const next=x.save(false);
  first({ok:true,json:async()=>({enabled:true,revision:1})});await old;
  assert.equal(checkbox(x.panel()).disabled,true);assert.equal(x.role.startup.enabled,false);
  second({ok:true,json:async()=>({enabled:false,revision:2})});await next;
  assert.equal(checkbox(x.panel()).disabled,false);assert.equal(x.role.startup.enabled,false);
});
test('角色已删除时迟到成功不恢复角色或设置',async()=>{
  const x=fixture();let done;x.respond(()=>new Promise(resolve=>done=resolve));const request=x.save(true);
  x.role.deletion={status:'pending'};done({ok:true,json:async()=>({enabled:true,revision:1})});await request;
  assert.equal(x.role.startup.enabled,false);assert.equal(x.panel(),null);
});
test('agent/归档/缺绑定/不受管/旧后端均隐藏且不能发送',async()=>{
  for(const kind of ['agent','archived','binding','unmanaged','legacy']){
    const x=fixture();if(kind==='agent')x.ctx.currentMemberIsHuman=()=>false;
    if(kind==='archived')x.role.archived=true;if(kind==='binding')x.role.binding_state='missing';
    if(kind==='unmanaged')x.role.service.control_kind='external_session';if(kind==='legacy')delete x.role.startup;
    assert.equal(x.panel(),null);await x.save(true);assert.equal(x.requests.length,0);
  }
});
test('失败执行不再显示自动启动提示，保存不把入队说成已就绪',()=>{
  const x=fixture();x.role.startup.last_activation={status:'failed',error_code:'private-path'};
  const text=x.h.texts(x.panel());
  // 2026-10-28：按用户要求移除“上次自动启动未完成，请查看服务状态后手动启动。”，不再展示该行。
  assert.doesNotMatch(text,/查看服务状态后手动启动/);
  assert.doesNotMatch(text,/private-path|启动成功/);
  assert.match(text,/随项目自动启动/);
});
test('页面详情接入控件，资源版本更新，UI没有启动执行API调用',()=>{
  assert.match(source,/const startupPanel = workspaceRoleStartupPanel\(role\)/);
  assert.match(fs.readFileSync(require.resolve('../web/index.html'),'utf8'),/20261028-role-list-select-v1/);
  assert.doesNotMatch(part,/role-services\/startup|\/service\/start|\/service\/stop/);
});
