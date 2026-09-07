const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../web/workspace.js');
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
function appFunction(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  const rest = source.slice(start);
  const end = rest.slice(1).search(/\n(?:async )?function /);
  assert.ok(start >= 0 && end >= 0);
  return rest.slice(0, end + 1);
}
const root = id => ({id, root_task_id:id, status:'running', workflow_status:'in_progress'});
const tree = id => ({root:root(id), tasks:[root(id)]});
function harness(...names) {
  const pending = [];
  const context = vm.createContext({
    ...helpers, activeProjectId:'p1', myId:'human:qa', taskTreeRequest:0,
    selectedTaskTree:null, taskTreeError:'', currentTask:root(15),
    getContextTask(){return context.currentTask;},
    apiFetch: url => new Promise((resolve,reject) => pending.push({url,resolve,reject})),
    readErrorDetail: async () => '加载失败', showTaskDetailsError: message => {context.error=message;},
    taskActionSaving:false, workspaceUI:{}, projectTasks:[root(15),root(9)], selectedTaskId:15,
    renderTaskDetailsPanel(){}, renderBlackboard(){}, renderProjectStrip(){},
    window:{confirm:()=>true}, loadProjectTasks:async()=>{},
  });
  for(const name of ['taskContextKey', ...names]) vm.runInContext(appFunction(name),context);
  const reply = (index, data) => pending[index].resolve({ok:true,json:async()=>data});
  return {context,pending,reply};
}
test('任务树必须同时匹配根任务和选中任务，不能复用其他 Hall 的门禁', () => {
  assert.equal(helpers.workspaceTreeMatches(root(9),tree(15)),false);
  assert.equal(helpers.workspaceTreeMatches({id:16,root_task_id:15},tree(15)),false);
  assert.equal(helpers.workspaceTreeMatches({id:16,root_task_id:15},{root:root(15),tasks:[root(15),{id:16}]}),true);
});
test('已提交成果仍待收取；已完成任务不再进入待我处理',()=>{
  const task={workflow_status:'submitted',created_by:'human:qa'};
  assert.equal(helpers.workspaceFinished(task),false);
  assert.equal(helpers.workspaceNeedsMe(task,'human:qa',true),true);
  assert.equal(helpers.workspaceNeedsMe(task,'human:other',true),false);
  assert.equal(helpers.workspaceNeedsMe({...task,workflow_status:'completed',control_status:'paused'},'human:qa',true),false);
});
test('先请求 #15 后切换 #9，迟到的 #15 响应不能覆盖 #9',async()=>{
  const {context:c,reply}=harness('loadSelectedTaskTree');
  const first=c.loadSelectedTaskTree(); c.currentTask=root(9);
  const second=c.loadSelectedTaskTree(); reply(1,tree(9)); await second;
  reply(0,tree(15)); await first; assert.equal(c.selectedTaskTree.root.id,9);
});
test('旧请求失败不能清除新任务的进度',async()=>{
  const {context:c,reply,pending}=harness('loadSelectedTaskTree');
  const first=c.loadSelectedTaskTree(); c.currentTask=root(9);
  const second=c.loadSelectedTaskTree(); reply(1,tree(9)); await second;
  pending[0].reject(new Error('旧网络错误')); await first;
  assert.equal(c.selectedTaskTree.root.id,9); assert.equal(c.taskTreeError,'');
});
for(const field of ['activeProjectId','myId']) test(`切换 ${field} 后丢弃旧任务树响应`,async()=>{
  const {context:c,reply}=harness('loadSelectedTaskTree');
  const request=c.loadSelectedTaskTree(); c[field]='changed'; reply(0,tree(15)); await request;
  assert.equal(c.selectedTaskTree,null);
});
test('当前任务加载错误清空过期门禁并提供错误反馈',async()=>{
  const {context:c,reply}=harness('loadSelectedTaskTree');
  c.selectedTaskTree=tree(15); const request=c.loadSelectedTaskTree(); reply(0,tree(9)); await request;
  assert.equal(c.selectedTaskTree,null); assert.match(c.taskTreeError,/不一致/);
});
test('旧树操作按钮不匹配当前任务时不发出请求',async()=>{
  const {context:c,pending}=harness('runTaskTreeAction');
  c.currentTask=root(9); c.selectedTaskTree=tree(15);
  await c.runTaskTreeAction(root(15),'pause-tree');
  assert.equal(pending.length,0); assert.match(c.error,/任务已切换/);
});
test('操作返回期间切换任务，保持新选择且不注入旧树',async()=>{
  const {context:c,reply}=harness('runTaskTreeAction');
  c.selectedTaskTree=tree(15); const request=c.runTaskTreeAction(root(15),'pause-tree');
  c.currentTask=root(9); c.selectedTaskTree=tree(9); reply(0,tree(15)); await request;
  assert.equal(c.selectedTaskTree.root.id,9); assert.equal(c.taskActionSaving,false);
});
test('单任务操作完成不抢回用户刚刚切换的选择',async()=>{
  const {context:c,reply}=harness('runTaskAction');
  c.loadSelectedTaskTree=async()=>{};
  const request=c.runTaskAction(root(15),'accept');
  c.currentTask=root(9); c.selectedTaskId=9; reply(0,{...root(15),workflow_status:'accepted'}); await request;
  assert.equal(c.selectedTaskId,9); assert.equal(c.projectTasks[0].workflow_status,'accepted');
});
test('角色索引响应不能写入另一个项目',async()=>{
  const {context:c,reply}=harness('loadProjectAgents');
  c.projectAgents=[]; const request=c.loadProjectAgents(); c.activeProjectId='p2';
  reply(0,[{member_id:'agent:old'}]); await request; assert.equal(c.projectAgents.length,0);
});
