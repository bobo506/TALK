const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
function slice(a,b) { const i=source.indexOf(a), j=source.indexOf(b,i); assert.ok(i>=0 && j>i); return source.slice(i,j); }
const functions = [
  slice('function activeProjectStorageKey()', 'async function loadProjectAgents()'),
  slice('async function setActiveProject(', 'async function refreshProjectWorkspace()'),
  slice('function activeGroupStorageKey()', 'async function refreshGroups()'),
  slice('function restoreActiveGroup()', 'function getActiveGroup()'),
].join('\n');
function setup() {
  const c = { URLSearchParams, console, calls: [], store: {}, results: {},
    myId:'agent:a', ACTIVE_PROJECT_STORAGE:'talk_active_project_id', ACTIVE_GROUP_STORAGE:'talk_active_group_id',
    activeProjectId:null, activeGroupId:null, groupRequest:0, groups:[], projects:[], projectAgents:[], projectTasks:[],
    selectedTaskId:null, selectedTaskTree:null, taskTreeError:'', blackboardOpen:false, groupMembersOpen:false,
    workspaceUI:{}, document:{getElementById:()=>({value:''})},
    localStorage:{getItem(k){return c.store[k] || null},setItem(k,v){c.store[k]=v},removeItem(k){delete c.store[k]}},
    apiFetch:async url => { c.calls.push(url); return {ok:true,json:async()=>c.results[url] || []} },
    canEnterGroup:id=>c.groups.some(g=>g.id===id),
    loadProjectAgents:async()=>{c.calls.push('agents:'+c.activeProjectId)},
    loadProjectTasks:async()=>{c.calls.push('tasks:'+c.activeProjectId)},
    resetWorkspaceResult(){}, resetTimelineState(){c.calls.push('timeline-reset')},
    renderProjectStrip(){}, renderWorkspaceMode(){}, renderRoomStrip(){}, renderPresenceStrip(){c.calls.push('presence')},
    showComposerStatus(){}, setBlackboardOpen(){},
  };
  vm.createContext(c); vm.runInContext(functions,c); return c;
}
test('加载群按当前工作区过滤，无项目时不请求；旧请求不能覆盖新项目', async()=>{
 const c=setup(); await c.loadGroups(); assert.equal(c.calls.length,0);
 c.activeProjectId='A'; c.results['/api/groups?project_id=A']=[{id:'group:a'}];
 c.store['talk_active_group_id:agent:a']='group:a'; await c.loadGroups();
 assert.deepEqual(c.calls,['/api/groups?project_id=A']); assert.equal(c.activeGroupId,'group:a');
 let finish; c.apiFetch = url => url.endsWith('A') ? new Promise(resolve=>{finish=resolve}) : Promise.resolve({ok:true,json:async()=>[{id:'group:b'}]});
 const old=c.loadGroups(); c.activeProjectId='B'; await c.loadGroups(); finish({ok:true,json:async()=>[{id:'group:a'}]}); await old;
 assert.equal(c.groups[0].id,'group:b');
});
test('切换清理旧会话、重置时间线并加载新项目，不调用服务或任务停止接口', async()=>{
 const c=setup(); c.projects=[{project_id:'A'},{project_id:'B'}]; c.activeProjectId='A'; c.activeGroupId='group:a';
 c.groups=[{id:'group:a'}]; c.store['talk_active_group_id:agent:a']='group:a';
 c.results['/api/groups?project_id=B']=[{id:'group:b'}]; await c.setActiveProject('B');
 assert.equal(c.activeGroupId,null); assert.equal(c.store['talk_active_group_id:agent:a'],undefined);
 assert.equal(c.store['talk_active_project_id:agent:a'],'B');
 for (const call of ['timeline-reset','agents:B','/api/groups?project_id=B','tasks:B','presence']) assert.ok(c.calls.includes(call),call);
 assert.ok(c.calls.every(call=>!/(stop|start|cancel)/i.test(call)));
});
test('按成员恢复 A 或 B，不可用回退首项，无项目删除缓存', async()=>{
 for (const stored of ['A','B','missing',null]) {
  const c=setup(); c.store['talk_active_project_id:agent:a']=stored;
  c.results['/api/projects']=[{project_id:'A'},{project_id:'B'}]; await c.loadProjects();
  assert.equal(c.activeProjectId,stored==='B'?'B':'A');
  assert.ok(c.calls.includes('tasks:'+c.activeProjectId)); assert.ok(c.calls.includes('agents:'+c.activeProjectId));
 }
 const c=setup(); c.store['talk_active_project_id:agent:a']='missing'; await c.loadProjects();
 assert.equal(c.activeProjectId,null); assert.equal(c.store['talk_active_project_id:agent:a'],undefined);
});
test('创建与上传使用当前工作区并提供缺失提示',()=>{
 const task=slice('async function createTaskFromPanel(', '// ── Group / Hall');
 const group=slice('async function createGroupFromPanel(', '\nfunction ');
 const upload=slice('async function uploadPendingFile()', '\nasync function ');
 for (const piece of [task,group,upload]) { assert.match(piece,/请先选择工作区/); assert.match(piece,/project_id[^\n]*activeProjectId/); }
});
