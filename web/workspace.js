/* 面向日常使用者的任务 / 角色工作台；复用现有 API 和权限。 */
const workspaceUI = { mode: "tasks", filter: "all", query: "", selectedRole: null, roleFilter: "finished", result: null, resultRequest: 0, renderedTask: null };
function workspaceRootId(task) { return task?.root_task_id || task?.id; }
function workspaceFinished(task) { return ["completed", "failed", "canceled"].includes(task?.workflow_status); }
function workspaceTreeMatches(task, tree) {
  return Boolean(task && tree?.root && Number(workspaceRootId(task)) === Number(tree.root.id)
    && tree.tasks?.some(item => Number(item.id) === Number(task.id)));
}
function workspaceNeedsMe(task, memberId, human) {
  if (workspaceFinished(task)) return false;
  if (human && (task.workflow_status === "needs_decision" || ["paused", "awaiting_human"].includes(task.control_status))) return true;
  return (task.created_by === memberId && ["submitted", "clarification_requested"].includes(task.workflow_status))
    || (task.target_member_id === memberId && ["assigned", "clarification_answered"].includes(task.workflow_status));
}
// 普通群聊沿用项目与历史无项目房间的范围，任务房间只从任务详情进入。
function workspaceChatRooms(items, projectId) {
  return items.filter(group => group.type !== "task" && (!projectId || !group.project_id || group.project_id === projectId));
}
function workspaceHasConversation() {
  return ["tasks", "chats"].includes(workspaceUI.mode) && !blackboardOpen && Boolean(getActiveGroup()) && canEnterGroup(activeGroupId)
    && (workspaceUI.mode !== "chats" || workspaceChatRooms([getActiveGroup()], activeProjectId).length > 0);
}
function openWorkspaceChats() {
  const rooms = workspaceChatRooms(groups, activeProjectId);
  const next = rooms.find(group => group.id === workspaceUI.lastChatId && canEnterGroup(group.id))
    || rooms.find(group => group.id === activeGroupId && canEnterGroup(group.id))
    || rooms.find(group => canEnterGroup(group.id));
  workspaceUI.mode = "chats";
  hallFilterInput.value = "";
  // 空群聊不回落到旧全局消息流；由页面显示空状态。
  setActiveGroup(next?.id || null);
  renderWorkspaceMode();
}
function workspaceEl(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function workspaceButton(text, handler, className = "workspace-text-button") {
  const button = workspaceEl("button", className, text);
  button.type = "button"; button.addEventListener("click", handler); return button;
}
function chatMemberName(member) {
  const id = String(member?.id || "未指定");
  const short = id.replace(/^(agent|human):/, "");
  const name = member?.display_name;
  return name && !/CLI Bridge|agent:/i.test(name) ? name : ({codex:"Codex",deepseek:"DeepSeek",kimi:"Kimi"}[short] || short);
}
function workspaceMemberName(id) { return chatMemberName(members.find(item => item.id === id) || {id}); }
function workspaceChatCandidates(items, roles, projectId, selfId) {
  const roleIds = new Set(roles.map(role => role.member_id));
  return items.filter(member => member.id !== selfId && !member.disabled_at
    && (member.kind !== "agent" || !projectId || roleIds.has(member.id)));
}
function workspaceMentionCandidates(items, selfId) { return items.filter(member => member.id !== selfId && !member.disabled_at); }
function workspaceRoleLabel(role) {
  return ({ lead: "统筹任务", dev: "执行工作", developer: "执行工作", reviewer: "检查工作", tester: "测试验证", ui: "界面设计" })[role] || role || "项目助手";
}
function workspaceRoles() { return projectAgents.filter(agent => !members.find(member => member.id === agent.member_id)?.disabled_at); }
function workspaceRoleTasks(id) {
  return projectTasks.filter(task => task.target_member_id === id || (task.created_by === id
    && !projectTasks.some(root => root.id === workspaceRootId(task) && root.id !== task.id && root.target_member_id === id)));
}
function workspaceWorkSummary(id) {
  const count = workspaceRoleTasks(id).filter(task => !workspaceFinished(task)).length;
  return count ? `正在参与 ${count} 项任务` : "当前没有进行中的任务";
}
function workspaceTitle(task) { return task.title || task.content?.split("\n")[0] || "未命名任务"; }
function syncWorkspaceLayout() {
  document.querySelector(".workbench").classList.toggle("project-mode", blackboardOpen);
  document.querySelector(".workbench").classList.toggle("empty-chat-mode", workspaceUI.mode === "chats" && !workspaceHasConversation());
  document.getElementById("project-blackboard-btn").setAttribute("aria-pressed", String(workspaceUI.mode === "tasks"));
  document.getElementById("workspace-chats-btn").setAttribute("aria-pressed", String(workspaceUI.mode === "chats"));
  document.getElementById("workspace-roles-btn").setAttribute("aria-pressed", String(blackboardOpen && workspaceUI.mode === "roles"));
  if (myId) userBadge.textContent = workspaceMemberName(myId);
}
function selectWorkspaceTask(task) {
  workspaceUI.query = ""; document.getElementById("workspace-search").value = "";
  workspaceUI.mode = "tasks";
  blackboardOpen = true;
  selectedTaskId = task.id;
  selectedTaskTree = null;
  taskTreeError = "";
  renderWorkspaceMode();
  loadSelectedTaskTree().then(() => renderTaskDetailsPanel());
  if (window.matchMedia("(max-width: 700px)").matches) taskDetailsPanel.scrollIntoView({ block: "start" });
}
function workspaceTaskRow(task) {
  const button = workspaceButton("", () => selectWorkspaceTask(task), "task-card");
  const selected = Number(workspaceRootId(getContextTask())) === Number(task.id);
  button.classList.toggle("selected", selected);
  button.setAttribute("aria-pressed", String(selected));
  button.appendChild(workspaceEl("div", "task-card-title", workspaceTitle(task)));
  const status = taskStatusMeta(task);
  button.appendChild(workspaceEl("span", `task-status-badge ${status.className}`, status.label));
  button.appendChild(workspaceEl("div", "task-card-meta", `负责人 ${workspaceMemberName(task.target_member_id)} · ${formatTaskTime(task.updated_at)}`));
  return button;
}
function renderWorkspaceList() {
  const rolesMode = workspaceUI.mode === "roles";
  syncWorkspaceLayout();
  blackboardTitle.textContent = rolesMode ? "角色" : "任务";
  blackboardDescription.textContent = rolesMode ? "参与协作的助手" : "按你委派的工作整理";
  const search = document.getElementById("workspace-search");
  search.placeholder = rolesMode ? "搜索角色" : "搜索任务";
  search.setAttribute("aria-label", search.placeholder);
  blackboardColumns.replaceChildren(); blackboardSummary.replaceChildren();
  blackboardEmpty.classList.add("hidden"); blackboardColumns.classList.remove("hidden");
  const query = workspaceUI.query.trim().toLocaleLowerCase();
  if (rolesMode) {
    const roles = workspaceRoles();
    if (!roles.some(role => role.member_id === workspaceUI.selectedRole)) workspaceUI.selectedRole = roles[0]?.member_id || null;
    for (const role of roles.filter(item => `${workspaceMemberName(item.member_id)} ${workspaceRoleLabel(item.business_role)}`.toLocaleLowerCase().includes(query))) {
      const row = workspaceButton("", () => { workspaceUI.selectedRole = role.member_id; renderWorkspaceList(); renderTaskDetailsPanel(); }, "role-row");
      row.classList.toggle("selected", role.member_id === workspaceUI.selectedRole);
      row.setAttribute("aria-pressed", String(role.member_id === workspaceUI.selectedRole));
      row.append(workspaceEl("strong", "", workspaceMemberName(role.member_id)), workspaceEl("span", "", workspaceRoleLabel(role.business_role)), workspaceEl("small", "", workspaceWorkSummary(role.member_id)));
      blackboardColumns.appendChild(row);
    }
  } else {
    for (const [value, label] of [["all", "全部"], ["running", "进行中"], ["mine", "待我处理"], ["finished", "已结束"]]) {
      const button = workspaceButton(label, () => { workspaceUI.filter = value; renderWorkspaceList(); });
      button.setAttribute("aria-pressed", String(workspaceUI.filter === value));
      blackboardSummary.appendChild(button);
    }
    const tasks = projectTasks.filter(task => !task.parent_task_id).filter(task => {
      const family = projectTasks.filter(item => Number(workspaceRootId(item)) === Number(task.id));
      if (workspaceUI.filter === "finished" && !workspaceFinished(task)) return false;
      if (workspaceUI.filter === "running" && workspaceFinished(task)) return false;
      if (workspaceUI.filter === "mine" && !family.some(item => workspaceNeedsMe(item, myId, currentMemberIsHuman()))) return false;
      return `${workspaceTitle(task)} ${workspaceMemberName(task.target_member_id)}`.toLocaleLowerCase().includes(query);
    });
    for (const task of tasks) blackboardColumns.appendChild(workspaceTaskRow(task));
  }
  if (!blackboardColumns.childElementCount) blackboardColumns.appendChild(workspaceEl("p", "workspace-empty", query ? "没有匹配的结果" : rolesMode ? "这个项目还没有配置角色。" : "当前筛选下没有任务。"));
}
function renderWorkspaceRoleDetails() {
  const panel = document.getElementById("role-details-panel");
  const visible = blackboardOpen && workspaceUI.mode === "roles";
  panel.classList.toggle("hidden", !visible);
  if (!visible) return;
  panel.replaceChildren();
  const role = workspaceRoles().find(item => item.member_id === workspaceUI.selectedRole);
  if (!role) { panel.appendChild(workspaceEl("p", "workspace-empty", "选择一个角色，查看他的工作。")); return; }
  panel.append(workspaceEl("p", "workspace-breadcrumb", `角色 / ${workspaceMemberName(role.member_id)}`), workspaceEl("h2", "", workspaceMemberName(role.member_id)), workspaceEl("p", "role-description", workspaceRoleLabel(role.business_role)), workspaceEl("p", "role-current", workspaceWorkSummary(role.member_id)));
  const description = ({ lead: "负责分配工作、跟进进度，并汇总最终成果。", dev: "负责执行分配的工作，并提交完成结果。", reviewer: "负责检查工作成果，指出问题并给出检查结论。", tester: "负责验证成果是否符合要求，并提交测试结论。" })[role.business_role];
  if (description) panel.insertBefore(workspaceEl("p", "role-explanation", description), panel.lastChild);
  const assign = workspaceButton("交办任务", () => { setTaskCreateOpen(true); taskCreateAgent.value = role.member_id; }, "task-action-primary");
  assign.disabled = !eligibleProjectAgents().some(member => member.id === role.member_id);
  panel.appendChild(assign);
  const section = workspaceEl("section", "role-task-section");
  section.appendChild(workspaceEl("h3", "", "参与的任务"));
  const filters = workspaceEl("div", "role-task-filters");
  for (const [value, label] of [["running", "进行中"], ["finished", "已结束"]]) {
    const button = workspaceButton(label, () => { workspaceUI.roleFilter = value; renderWorkspaceRoleDetails(); });
    button.setAttribute("aria-pressed", String(workspaceUI.roleFilter === value)); filters.appendChild(button);
  }
  section.appendChild(filters);
  const table = workspaceEl("table", "role-task-table");
  const head = workspaceEl("thead"); const tr = workspaceEl("tr");
  for (const title of ["任务", "承担工作", "任务状态", "操作"]) { const th = workspaceEl("th", "", title); th.scope = "col"; tr.appendChild(th); }
  head.appendChild(tr); table.appendChild(head);
  const body = workspaceEl("tbody");
  const tasks = workspaceRoleTasks(role.member_id).filter(task => workspaceFinished(task) === (workspaceUI.roleFilter === "finished"));
  for (const task of tasks) {
    const row = workspaceEl("tr");
    const name = workspaceEl("td"); name.appendChild(workspaceEl("span", "role-task-name", workspaceTitle(task)));
    const work = task.target_member_id === role.member_id ? (task.may_delegate ? "统筹与汇总" : taskKindLabel(task.task_kind)) : "委派与跟进";
    const state = taskStatusMeta(task); const status = workspaceEl("td"); status.appendChild(workspaceEl("span", `task-status-badge ${state.className}`, state.label));
    const action = workspaceEl("td"); const button = workspaceButton("查看任务", () => selectWorkspaceTask(task)); button.setAttribute("aria-label", `查看任务：${workspaceTitle(task)}`); action.appendChild(button);
    row.append(name, workspaceEl("td", "", work), status, action); body.appendChild(row);
  }
  table.appendChild(body); section.appendChild(table);
  if (!tasks.length) section.appendChild(workspaceEl("p", "workspace-empty", "当前没有这类任务。"));
  panel.appendChild(section);
}
function workspaceTaskNotice(task, tree) {
  if (task.workflow_status === "completed") return "成果已收取，本任务已完成。无需继续操作。";
  if (task.workflow_status === "failed") return "任务执行失败，请查看已有结果和失败原因。";
  if (task.workflow_status === "canceled") return "任务已取消，不会继续执行。";
  if (tree?.root.control_status === "awaiting_human" && tree.root.checkpoint_reason === "milestone") return "检查已完成，等待项目负责人进行人工验收。";
  if (["paused", "awaiting_human"].includes(tree?.root.control_status)) return `任务已暂停：${checkpointReasonLabel(tree.root.checkpoint_reason)}。`;
  if (task.workflow_status === "submitted") return task.created_by === myId ? "成果已提交，等待你查看并收取。" : "成果已提交，等待请求者收取。";
  if (task.workflow_status === "clarification_requested") return task.created_by === myId ? "需要你补充任务要求，请在完整对话中答复。" : "等待请求者补充任务要求。";
  if (task.workflow_status === "needs_decision") return "需要项目负责人作出决定，任务尚未继续。";
  return task.workflow_status === "in_progress" ? "负责人正在推进任务，下面可查看分工进展。" : "任务已交办，等待负责人接手。";
}
function renderWorkspaceTaskStory(task) {
  const tree = workspaceTreeMatches(task, selectedTaskTree) ? selectedTaskTree : null;
  const notice = document.getElementById("task-notice"); notice.textContent = workspaceTaskNotice(task, tree);
  notice.className = `task-notice ${taskStatusMeta(task).className}`;
  document.getElementById("task-outcome-summary").textContent = task.last_error || (task.result_message_id ? "负责人已提交成果，可查看具体内容或完整对话。" : "尚未提交最终成果。任务要求与分工记录保留在下方。");
  if (workspaceUI.renderedTask !== task.id) {
    document.getElementById("task-requirements").open = false;
    resetWorkspaceResult(); workspaceUI.renderedTask = task.id;
  }
  const result = document.getElementById("task-result-body");
  if (!workspaceResultOpen(task)) { result.classList.add("hidden"); result.textContent = ""; }
  const flow = document.getElementById("task-flow-list"); flow.replaceChildren();
  const list = workspaceEl("ol", "handoff-list");
  const assigned = workspaceEl("li"); assigned.append(workspaceEl("strong", "", "交办任务"), workspaceEl("p", "", `${workspaceMemberName(task.created_by)} → ${workspaceMemberName(task.target_member_id)}`)); list.appendChild(assigned);
  if (!tree) list.appendChild(workspaceEl("li", "workspace-empty", taskTreeError || "正在加载分工进度…"));
  else {
    const children = tree.tasks.filter(item => item.parent_task_id && (Number(item.parent_task_id) === Number(task.id) || Number(task.id) === Number(tree.root.id))).sort((a,b) => a.id-b.id);
    for (const child of children) {
      const item = workspaceEl("li"); item.append(workspaceButton(`${taskKindLabel(child.task_kind)} · ${workspaceTitle(child)}`, () => selectWorkspaceTask(child)), workspaceEl("p", "", `${workspaceMemberName(child.created_by)} → ${workspaceMemberName(child.target_member_id)} · ${taskStatusMeta(child).label}`)); list.appendChild(item);
    }
    if (!children.length) list.appendChild(workspaceEl("li", "", `负责人 ${workspaceMemberName(task.target_member_id)} · ${taskStatusMeta(task).label}`));
    // 只有根任务展示当前质量结论；不把兄弟任务门禁混入子任务。
    if (Number(task.id) === Number(tree.root.id)) {
      for (const gate of tree.review_gates || []) {
        const subject = tree.tasks.find(item => Number(item.id) === Number(gate.current_subject_task_id));
        const verdict = ({ approved: "检查通过", changes_requested: "检查要求修改" })[gate.current_verdict?.verdict] || "等待检查结论";
        list.appendChild(workspaceEl("li", "", `${subject ? workspaceTitle(subject) : "执行成果"} · ${verdict}`));
      }
      if (tree.test_gate?.required) list.appendChild(workspaceEl("li", "", tree.test_gate.satisfied ? "当前成果测试通过" : "当前成果尚未通过测试"));
    }
  }
  if (task.workflow_status === "completed") list.appendChild(workspaceEl("li", "", "负责人已提交成果，请求者已收取，任务完成。"));
  flow.appendChild(list);
  if (task.parent_task_id && tree) flow.appendChild(workspaceButton("返回主任务", () => selectWorkspaceTask(tree.root)));
}
// 成果展开状态以 workspaceUI.result 为准，并绑定 项目/账号/任务 完整上下文；切换时由详情重绘与请求序号共同作废旧状态。
function workspaceResultOpen(task) {
  const result = workspaceUI.result;
  return Boolean(task && result && Number(result.taskId) === Number(task.id)
    && result.memberId === myId && result.projectId === activeProjectId);
}
// 上下文切换（含切到无任务项目、task=null 的空详情）时统一清空成果状态并作废旧请求。
function resetWorkspaceResult() {
  workspaceUI.result = null; ++workspaceUI.resultRequest;
}
function syncWorkspaceResultButton() {
  const button = document.querySelector('[aria-controls="task-result-body"]');
  if (!button) return;
  const open = workspaceResultOpen(getContextTask());
  button.textContent = open ? "收起成果" : "查看成果";
  button.setAttribute("aria-expanded", String(open));
}
async function showWorkspaceResult(task) {
  const panel = document.getElementById("task-result-body");
  // 已展开（含加载中）时再次点击：立即收起、清空内容并作废未完成的请求。
  if (workspaceResultOpen(task)) {
    resetWorkspaceResult();
    panel.classList.add("hidden"); panel.textContent = "";
    syncWorkspaceResultButton();
    return;
  }
  const request = ++workspaceUI.resultRequest;
  const memberId = myId;
  const projectId = activeProjectId;
  if (!canEnterGroup(task.hall_group_id)) { showTaskDetailsError("当前账号尚未加入这个任务对话，无法查看成果。请联系任务负责人确认访问权限。"); return; }
  panel.classList.remove("hidden"); panel.textContent = "正在加载成果…";
  const current = () => request === workspaceUI.resultRequest && memberId === myId
    && projectId === activeProjectId && getContextTask()?.id === task.id;
  workspaceUI.result = { taskId: task.id, memberId, projectId };
  syncWorkspaceResultButton();
  try {
    const params = new URLSearchParams({group_id: task.hall_group_id, before: String(task.result_message_id + 1), limit: "1"});
    const res = await apiFetch(`/api/messages?${params}`);
    if (!res.ok) throw new Error(await readErrorDetail(res, "成果加载失败，请重试。"));
    const messages = await res.json(); if (!current()) return;
    const message = messages.find(item => Number(item.id) === Number(task.result_message_id));
    if (!message) throw new Error("没有找到指定成果，请查看完整对话。");
    panel.textContent = message.revoked_at ? "这条成果消息已撤回。" : message.type === "file" ? `文件成果：${message.filename || "文件"}\n${message.caption || ""}\n请在完整对话中下载文件。` : message.content || "成果消息没有正文。";
  } catch (err) { if (current()) panel.textContent = err.message; }
}
if (typeof document !== "undefined") {
  document.getElementById("workspace-chats-btn").addEventListener("click", openWorkspaceChats);
  document.getElementById("workspace-roles-btn").addEventListener("click", () => {
    workspaceUI.mode = "roles"; blackboardOpen = Boolean(activeProjectId); selectedTaskTree = null; ++taskTreeRequest;
    workspaceUI.query = ""; document.getElementById("workspace-search").value = "";
    renderWorkspaceMode();
  });
  document.getElementById("workspace-search").addEventListener("input", event => { workspaceUI.query = event.target.value; renderWorkspaceList(); });
}
if (typeof module !== "undefined") module.exports = {workspaceRootId, workspaceFinished, workspaceTreeMatches, workspaceNeedsMe, workspaceChatRooms, chatMemberName, workspaceChatCandidates, workspaceMentionCandidates, workspaceResultOpen, resetWorkspaceResult, syncWorkspaceResultButton, showWorkspaceResult};
