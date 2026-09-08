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

test('群聊只列本项目和历史无项目房间，排除任务专属房间',()=>{
  const items=[{id:'task',type:'task',project_id:'p1'},{id:'chat',type:'group',project_id:'p1'},
    {id:'legacy',project_id:null},{id:'other',type:'discussion',project_id:'p2'}];
  assert.deepEqual(helpers.workspaceChatRooms(items,'p1').map(g=>g.id),['chat','legacy']);
});
test('群聊页不会沿用之前选中的任务详情',()=>{
  const {context:c}=harness('getContextTask');
  c.workspaceUI.mode='chats'; c.blackboardOpen=false; c.activeGroupId='chat';
  assert.equal(c.getContextTask(),null);
});
for(const name of ['loadHistory','pollMessages']) test(`${name} 的旧房间响应不进入新房间`,async()=>{
  const {context:c,reply}=harness('captureTimelineContext',name);
  Object.assign(c,{timelineRevision:1,activeGroupId:'old',workspaceHasConversation:()=>true,
    renderHistoryToolbar(){},buildHistoryRequestPath:()=>'/messages',buildPollRequestPath:()=>'/messages',
    clearComposerStatus(){},showComposerStatus(){throw Error('不应显示旧房间提示');},
    renderMessagesInChunks(){throw Error('不应渲染旧消息');},appendMessages(){throw Error('不应追加旧消息');},
    historyLoading:false});
  const request=c[name](); c.activeGroupId='new'; ++c.timelineRevision;
  reply(0,[{id:1,group_id:'old'}]); await request;
});
test('没有选中群聊时不会请求全局消息',async()=>{
  const {context:c,pending}=harness('loadHistory','pollMessages');
  c.workspaceHasConversation=()=>false;
  await c.loadHistory(); await c.pollMessages(); assert.equal(pending.length,0);
});

test('创建群聊携带当前项目并进入新房间',async()=>{
  const {context:c}=harness('createGroupFromPanel'); let submitted;
  Object.assign(c,{groupCreateSaving:false,groupCreateName:{value:'协作群'},groupCreateId:{value:''},
    groupCreateDescription:{value:''},selectedCreateMemberIds:new Set(['human:alice']),
    submitGroupCreateBtn:{},cancelGroupCreateBtn:{},groups:[],
    clearComposerStatus(){},showGroupCreateError(message){throw Error(message);},
    setGroupCreateOpen(open){c.modalOpen=open;},setActiveGroup(id){c.entered=id;},
    apiFetch:async(url,options)=>{submitted={url,body:JSON.parse(options.body)};return {ok:true,json:async()=>({id:'new-room',project_id:'p1'})};}});
  await c.createGroupFromPanel({preventDefault(){}});
  assert.equal(submitted.url,'/api/groups'); assert.equal(submitted.body.project_id,'p1');
  assert.deepEqual(submitted.body.member_ids,['human:alice']);
  assert.equal(c.entered,'new-room'); assert.equal(c.modalOpen,false);
});


test('群聊邀请按项目角色筛选，排除自己和禁用成员，保留其他真人账号',()=>{
  const members=[{id:'human:qa',kind:'human'}, {id:'human:bobo',kind:'human'},
    {id:'agent:codex',kind:'agent'},{id:'agent:pi',kind:'agent'},
    {id:'agent:off',kind:'agent',disabled_at:'2026-09-08'}];
  const roles=[{member_id:'agent:codex'},{member_id:'agent:off'}];
  assert.deepEqual(helpers.workspaceChatCandidates(members,roles,'p1','human:qa').map(m=>m.id),['human:bobo','agent:codex']);
  assert.deepEqual(helpers.workspaceChatCandidates(members,[], 'p2','human:bobo').map(m=>m.id),['human:qa']);
  assert.deepEqual(helpers.workspaceChatCandidates(members,[],null,'human:qa').map(m=>m.id),['human:bobo','agent:codex','agent:pi']);
});
test('@ 候选排除自己与禁用成员，不改变房间成员关系',()=>{
  const members=[{id:'human:qa'},{id:'agent:codex'},{id:'agent:disabled',disabled_at:'yes'}];
  assert.deepEqual(helpers.workspaceMentionCandidates(members,'human:qa').map(m=>m.id),['agent:codex']);
  assert.equal(members.length,3);
});
test('自动 bridge 昵称显示简短名称，人工昵称保留',()=>{
  assert.equal(helpers.chatMemberName({id:'agent:codex',display_name:'codex CLI Bridge (agent:codex)'}),'Codex');
  assert.equal(helpers.chatMemberName({id:'agent:deepseek',display_name:'dsh CLI Bridge (agent:deepseek)'}),'DeepSeek');
  assert.equal(helpers.chatMemberName({id:'agent:kimi',display_name:'审查助手'}),'审查助手');
  assert.equal(helpers.chatMemberName({id:'human:bobo',display_name:'bobo'}),'bobo');
});
