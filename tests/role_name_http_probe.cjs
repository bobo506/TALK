'use strict';
// Actual saveRoleName → apiFetch → fetch → isolated HTTP API contract.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {documentFixture}=require('./role_creation_dom.cjs');
const [baseUrl,memberId]=process.argv.slice(2);
const workspace=fs.readFileSync(require.resolve('../web/workspace.js'),'utf8');
const app=fs.readFileSync(require.resolve('../web/app.js'),'utf8');
const h=documentFixture();
for(const id of ['role-name-modal','role-name-input','role-name-status','role-name-save','role-name-cancel','role-name-edit']) {
  const n=h.document.createElement('div');n.id=id;h.elements.set(id,n);
}
const context=vm.createContext({document:h.document,console,API:baseUrl,apiKey:'bobo-key',fetch,
  activeProjectId:'prj_alpha',myId:'human:bobo',blackboardOpen:true,workspaceUI:{mode:'roles'},
  projectAgents:[{member_id:memberId,role_name:'WorkBuddy-k3'}],members:[],
  currentMemberIsHuman:()=>true,renderWorkspaceList:()=>{},renderTaskDetailsPanel:()=>{},
});
vm.runInContext(app.slice(app.indexOf('function apiFetch(')),context);
vm.runInContext(workspace.slice(workspace.indexOf('function chatMemberName('),workspace.indexOf('function workspaceChatCandidates(')),context);
(async()=>{
  context.openRoleNameEditor(context.projectAgents[0]);
  h.el('role-name-input').value='真实链路改名';
  await context.saveRoleName({preventDefault(){}});
  assert.equal(h.el('role-name-modal').classList.contains('hidden'),true,h.el('role-name-status').textContent);
  assert.equal(context.projectAgents[0].role_name,'真实链路改名');
  const response=await fetch(baseUrl+'/api/projects/prj_alpha/agents',{headers:{'X-API-Key':'bobo-key'}});
  assert.equal(response.status,200);
  const row=(await response.json()).find(r=>r.member_id===memberId);
  assert.equal(row.role_name,'真实链路改名');assert.equal(row.display_name,'WorkBuddy-k3');
  console.log(JSON.stringify({actual_ui_api_fetch_http:true,saved:true,project_only:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
