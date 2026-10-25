'use strict';
// Input is a real isolated GET /agents response, not a hand-built UI role.
const fs=require('node:fs'),vm=require('node:vm');
const {documentFixture}=require('./role_creation_dom.cjs');
const input=JSON.parse(fs.readFileSync(0,'utf8')),h=documentFixture(),requests=[];
const app=fs.readFileSync(require.resolve('../web/app.js'),'utf8');
const workspace=fs.readFileSync(require.resolve('../web/workspace.js'),'utf8');
const ctx=vm.createContext({document:h.document,projectAgentRequest:0,activeProjectId:input.project,
  myId:'human:bobo',projectAgents:[],currentMemberIsHuman:()=>true,
  roleServiceView:r=>({service:r.service}),renderWorkspaceRoleDetails:()=>{},
  workspaceEl:(tag,css='',text='')=>{const e=h.document.createElement(tag);e.className=css;e.textContent=text;return e;},
  apiFetch:async(path,options={})=>{
    if(options.method&&options.method!=='GET')throw Error('render must be read-only');
    requests.push(path);return {ok:true,json:async()=>input.agents};
  }});
vm.runInContext(app.slice(app.indexOf('async function loadProjectAgents()'),app.indexOf('async function loadProjectTasks(')),ctx);
vm.runInContext(workspace.slice(workspace.indexOf('const roleStartupUI ='),workspace.indexOf('function renderWorkspaceRoleDetails()')),ctx);
(async()=>{
  await ctx.loadProjectAgents();
  const role=ctx.projectAgents.find(r=>r.member_id===input.member);
  const panel=ctx.workspaceRoleStartupPanel(role);
  console.log(JSON.stringify({visible:!!panel,checked:panel?panel.children[0].children[0].checked:null,
    text:panel?h.texts(panel):'',requests}));
})().catch(error=>{console.error(error);process.exitCode=1;});
