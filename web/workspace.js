/* 面向日常使用者的任务 / 角色工作台；复用现有 API 和权限。 */
const workspaceUI = { mode: "tasks", filter: "all", query: "", selectedRole: null, roleSelection: "settings", roleFilter: "finished", result: null, resultRequest: 0, renderedTask: null };
// 参与任务分页：每页固定 20 条；页码绑定 账号/项目/角色/筛选 上下文，任何变化（含离开角色详情）都重置第一页。
const ROLE_TASKS_PAGE_SIZE = 20;
const roleTasksPageUI = { key: null, page: 1 };
// 主任务列表分页：每页固定 20 条；页码绑定 账号/项目/模式/离页/搜索/筛选 上下文，
// 任何变化都重置第一页；同上下文的普通轮询/手动刷新保页码，集合缩小时夹回最后有效页。
const TASK_LIST_PAGE_SIZE = 20;
const taskListPageUI = { key: null, page: 1 };
// R1-3：搜索框保持静态节点；角色页批量操作与结果分别重绘，避免移除搜索及其输入监听。
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
// 任务完整对话：任务模式下进入任务 Hall 对话时，右侧不再重复任务详情栏，聊天占用腾出的空间。
function workspaceTaskChatActive() {
  return workspaceUI.mode === "tasks" && !blackboardOpen && workspaceHasConversation();
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
function workspaceMemberName(id) {
  const projectName = projectAgents.find(role => role.member_id === id)?.role_name;
  if (typeof projectName === "string" && projectName.trim()) return projectName;
  const roleName = typeof roleRequestApp !== "undefined" && roleRequestApp?.roleName(id);
  return roleName || chatMemberName(members.find(item => item.id === id) || {id});
}

const roleNameUI = { context: null, seq: 0, saving: false };
function roleNameContextCurrent(context) {
  return context && context.projectId === activeProjectId && context.accountId === myId
    && currentMemberIsHuman() && workspaceUI.mode === "roles" && blackboardOpen;
}
function closeRoleNameEditor(restoreFocus = true) {
  const context = roleNameUI.context;
  roleNameUI.context = null; roleNameUI.seq++; roleNameUI.saving = false;
  document.getElementById("role-name-modal")?.classList.add("hidden");
  if (restoreFocus && roleNameContextCurrent(context)) document.getElementById("role-name-edit")?.focus();
}
function syncRoleNameEditor() {
  if (roleNameUI.context && !roleNameContextCurrent(roleNameUI.context)) closeRoleNameEditor(false);
}
function openRoleNameEditor(role) {
  if (!currentMemberIsHuman() || role.archived === true) return;
  const input = document.getElementById("role-name-input");
  if (!input) return;
  roleNameUI.context = {projectId: activeProjectId, accountId: myId, memberId: role.member_id};
  roleNameUI.seq++; roleNameUI.saving = false;
  input.value = workspaceMemberName(role.member_id); input.disabled = false;
  document.getElementById("role-name-status").textContent = "";
  document.getElementById("role-name-save").disabled = false;
  document.getElementById("role-name-cancel").disabled = false;
  document.getElementById("role-name-modal").classList.remove("hidden");
  input.focus(); input.select?.();
}
async function saveRoleName(event) {
  event?.preventDefault();
  const context = roleNameUI.context;
  if (!roleNameContextCurrent(context) || roleNameUI.saving) return;
  const input = document.getElementById("role-name-input");
  const name = input.value.trim();
  const status = document.getElementById("role-name-status");
  if (!name || Array.from(name).length > 64) { status.textContent = "角色名称须为1–64个字符。"; input.focus(); return; }
  const seq = ++roleNameUI.seq; roleNameUI.saving = true;
  for (const id of ["role-name-input", "role-name-save", "role-name-cancel"]) document.getElementById(id).disabled = true;
  status.textContent = "正在保存…";
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(context.projectId)}/roles/${encodeURIComponent(context.memberId)}`, {
      method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({role_name: name}),
    });
    const body = await res.json().catch(() => ({}));
    if (!roleNameContextCurrent(context) || roleNameUI.seq !== seq) return;
    if (!res.ok) {
      const code = typeof body.detail === "string" ? body.detail : "";
      const message = ({role_name_conflict: "这个角色名称已被使用，请换一个名称。", role_name_invalid: "角色名称须为1–64个字符。", role_archived: "该角色已归档，请刷新角色列表。"})[code];
      const statusMessage = ({401: "登录已失效，请重新登录后重试。", 403: "当前账号没有修改角色名称的权限。", 404: "角色不存在或已移除，请刷新角色列表。", 422: "名称提交格式不正确，请刷新页面后重试。"})[res.status];
      throw new Error(message || statusMessage || `名称保存失败（HTTP ${res.status}），请稍后重试。`);
    }
    if (body.member_id !== context.memberId || typeof body.role_name !== "string") throw new Error("名称回执不完整，请刷新核对。");
    // Ignore roster reads issued before this confirmed rename.
    if (typeof projectAgentRequest !== "undefined") projectAgentRequest++;
    const role = projectAgents.find(row => row.member_id === context.memberId);
    if (role) role.role_name = body.role_name;
    if (typeof roleRequestApp !== "undefined") roleRequestApp?.setRoleName?.(context.memberId, body.role_name);
    closeRoleNameEditor(false);
    renderWorkspaceList(); renderTaskDetailsPanel();
    document.getElementById("role-name-edit")?.focus();
  } catch (err) {
    if (roleNameContextCurrent(context) && roleNameUI.seq === seq) status.textContent = err.message || "名称保存失败，请重试。";
  } finally {
    if (roleNameContextCurrent(context) && roleNameUI.seq === seq) {
      roleNameUI.saving = false;
      for (const id of ["role-name-input", "role-name-save", "role-name-cancel"]) document.getElementById(id).disabled = false;
    }
  }
}
function workspaceChatCandidates(items, roles, projectId, selfId) {
  const roleIds = new Set(roles.filter(role => !role.archived).map(role => role.member_id));
  return items.filter(member => member.id !== selfId && !member.disabled_at
    && (member.kind !== "agent" || !projectId || roleIds.has(member.id)));
}
function workspaceMentionCandidates(items, selfId) { return items.filter(member => member.id !== selfId && !member.disabled_at); }
// 角色展示映射仅决定界面文案，不授予任何权限；真实职责以项目开发要求和具体任务包为准。
// developer 与 dev 同义归一，标签与说明共用同一映射，不散落硬编码。
function workspaceRoleKey(role) { return role === "developer" ? "dev" : role; }
function workspaceRoleLabel(role) {
  return ({ lead: "统筹任务", dev: "执行工作", reviewer: "执行工作", tester: "测试验证", ui: "界面设计" })[workspaceRoleKey(role)] || role || "项目助手";
}
function workspaceRoleDescription(role) {
  return ({
    lead: "负责分配工作、跟进进度，并汇总最终成果。",
    dev: "负责执行分配的工作、提交完成结果，并交叉验证其他角色的成果。",
    reviewer: "负责执行分配的工作、提交完成结果，并交叉验证其他角色的成果。",
    tester: "负责验证成果是否符合要求，并提交测试结论。",
  })[workspaceRoleKey(role)];
}
function workspaceRoles() { return projectAgents.filter(agent => agent.deletion?.status !== "complete" && (agent.deletion || !members.find(member => member.id === agent.member_id)?.disabled_at)); }
// ROLE-SETTINGS-1：角色列表固定首项“项目设置”是独立导航项，不是伪造 Agent——
// 不计入角色数量、不进入名册成员候选，其选中状态也不会作为 member_id 传给任何任务或 API。
// 选择状态：roleSelection === "role" 且 selectedRole 命中当前名册时查看具体角色；
// 其余一律回落到“项目设置”（首次进入、选择失效、切项目后均是如此）。
function workspaceSettingsSelected() {
  return workspaceUI.roleSelection !== "role"
    || !workspaceRoles().some(role => role.member_id === workspaceUI.selectedRole);
}
function workspaceRoleTasks(id) {
  return projectTasks.filter(task => task.target_member_id === id || (task.created_by === id
    && !projectTasks.some(root => root.id === workspaceRootId(task) && root.id !== task.id && root.target_member_id === id)));
}
function workspaceWorkSummary(id, { hideEmpty = false } = {}) {
  const count = workspaceRoleTasks(id).filter(task => !workspaceFinished(task)).length;
  return count ? `正在参与 ${count} 项任务` : hideEmpty ? "" : "当前没有进行中的任务";
}
function workspaceTitle(task) { return task.title || task.content?.split("\n")[0] || "未命名任务"; }
// 执行耗时起止：claimed_at 是角色实际领取（重试会刷新为最新一次领取），finished_at 是执行结束（成功提交/失败/取消），均不含排队与待收取时间。
// 后端时间可能是 UTC 无时区字符串（如 2026-09-13T09:18:20.702888）或带明确偏移，统一按真实时间戳解析，无效返回 null。
function workspaceParseTime(value) {
  if (value === null || value === undefined) return null;
  let text = String(value).trim();
  if (!text) return null;
  if (!/(?:z|[+-]\d{2}:?\d{2})$/i.test(text)) text += "Z";
  const ms = Date.parse(text.includes("T") ? text : text.replace(" ", "T"));
  return Number.isNaN(ms) ? null : ms;
}
// HH:MM:SS；小时超过 24 不回卷，超过 99 自然扩展位数。
function workspaceFormatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const total = Math.floor(ms / 1000);
  const pad = n => String(n).padStart(2, "0");
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor(total / 60) % 60)}:${pad(total % 60)}`;
}
// 终态用 finished_at 冻结；执行中按传入的当前时间实时计算；缺少/无效起止或负值显示 —。
function workspaceTaskDuration(task, nowMs = Date.now()) {
  const start = workspaceParseTime(task?.claimed_at);
  if (start === null) return "—";
  const finished = workspaceParseTime(task?.finished_at);
  const end = finished !== null ? finished : (task?.workflow_status === "in_progress" ? nowMs : null);
  if (end === null || end < start) return "—";
  return workspaceFormatDuration(end - start);
}
// 统一耗时单元：终态渲染时冻结；执行中挂上既有单计时器识别的 data-running 标识，
// 由 tickTaskDurations 逐秒只刷新 textContent，不为每行新增 timer。
function workspaceTaskDurationEl(task) {
  const el = workspaceEl("span", "task-card-duration", workspaceTaskDuration(task));
  el.dataset.taskId = String(task.id);
  if (task?.workflow_status === "in_progress" && workspaceParseTime(task.claimed_at) !== null && workspaceParseTime(task.finished_at) === null) {
    el.dataset.running = "1";
  }
  return el;
}
function syncTaskListPaginationContext() {
  const key = myId && activeProjectId && workspaceUI.mode === "tasks" && blackboardOpen
    ? JSON.stringify([myId, activeProjectId, workspaceUI.filter, workspaceUI.query]) : null;
  if (key !== taskListPageUI.key) {
    taskListPageUI.key = key;
    taskListPageUI.page = 1;
  }
}
function syncWorkspaceLayout() {
  // 群聊导航不渲染任务列表；在公共导航入口同步，离页也能立即作废旧页码。
  syncTaskListPaginationContext();
  document.querySelector(".workbench").classList.toggle("project-mode", blackboardOpen);
  document.querySelector(".workbench").classList.toggle("task-chat-mode", workspaceTaskChatActive());
  document.querySelector(".workbench").classList.toggle("empty-chat-mode", workspaceUI.mode === "chats" && !workspaceHasConversation());
  document.getElementById("project-blackboard-btn").setAttribute("aria-pressed", String(workspaceUI.mode === "tasks"));
  document.getElementById("workspace-chats-btn").setAttribute("aria-pressed", String(workspaceUI.mode === "chats"));
  document.getElementById("workspace-roles-btn").setAttribute("aria-pressed", String(blackboardOpen && workspaceUI.mode === "roles"));
  if (myId) userBadge.textContent = workspaceMemberName(myId);
  // R1-3：每次导航/刷新都同步服务轮询上下文——离开角色页、切项目或切账号立即停表。
  syncRoleServicePollingContext();
  if (typeof roleRequestApp !== "undefined") roleRequestApp?.sync();
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
  const meta = workspaceEl("div", "task-card-meta");
  meta.appendChild(document.createTextNode(`负责人 ${workspaceMemberName(task.target_member_id)} · ${formatTaskTime(task.updated_at)} · 耗时 `));
  // 只有执行中的条目由统一计时器逐秒刷新；终态在渲染时冻结，列表轮询不重绘时也不变。
  meta.appendChild(workspaceTaskDurationEl(task));
  button.appendChild(meta);
  return button;
}
// ── REQ-2 项目级“开发要求”编辑区（角色页，不绑定单个角色） ─────────────
// 上限与后端 PROJECT_DEVELOPMENT_REQUIREMENTS_MAX_CHARS 一致；字符数按 Unicode
// 码点计数（JS 展开迭代与 Python len 对成形文本一致），不用 maxlength 误拒 emoji。
const REQUIREMENTS_MAX_CHARS = 20000;
function workspaceRequirementsLength(text) { return [...String(text ?? "")].length; }
// 与后端 normalize_development_requirements 对齐：null/全空白（含空串）归一为 null，其它原文保留。
// 空白集合按 Python str.isspace() 合同（server/models.py 用 value.strip() 判空）：
// U+0009–U+000D、U+001C–U+001F、U+0020、U+0085、U+00A0、U+1680、U+2000–U+200A、U+2028/U+2029、
// U+202F、U+205F、U+3000。不用 JS trim()：它会多算 U+FEFF、漏算 U+001C–U+001F/U+0085，与后端分叉。
const REQUIREMENTS_BLANK = /^[\u0009-\u000d\u001c-\u001f\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u;
function normalizeRequirementsValue(value) {
  if (value === null || value === undefined) return null;
  const text = String(value);
  return REQUIREMENTS_BLANK.test(text) ? null : text;
}
// 读写状态绑定 项目/账号/请求序号；草稿只存内存（按 账号+项目 隔离），不写 localStorage，不跨账号共享。
const requirementsUI = { projectId: null, memberId: null, supported: false, loaded: false, saving: false, request: 0, saved: null, error: "", notice: "" };
const requirementsDrafts = new Map();
function requirementsEl(id) { return typeof document === "undefined" ? null : document.getElementById(id); }
function requirementsDraftKey(projectId, memberId) { return `${memberId}/${projectId}`; }
function renderRequirementsPanel() {
  const panel = requirementsEl("requirements-panel");
  if (!panel) return;
  // ROLE-SETTINGS-1：开发要求只属于“项目设置”页；选中具体角色或离开角色页时隐藏，草稿状态不受影响。
  const visible = blackboardOpen && workspaceUI.mode === "roles" && workspaceSettingsSelected() && Boolean(activeProjectId) && Boolean(myId);
  panel.classList.toggle("hidden", !visible);
  if (!visible) return;
  const projectId = activeProjectId, memberId = myId;
  if (requirementsUI.projectId !== projectId || requirementsUI.memberId !== memberId) {
    // 上下文切换（含往返 A→B→A）：递增请求序号使旧读写作废，新上下文重新读取。
    ++requirementsUI.request;
    Object.assign(requirementsUI, { projectId, memberId, supported: false, loaded: false, saving: false, saved: null, error: "", notice: "" });
    const draft = requirementsDrafts.get(requirementsDraftKey(projectId, memberId));
    const input = requirementsEl("requirements-input");
    if (input) input.value = draft ?? "";
    if (draft !== undefined) requirementsUI.notice = "已恢复上次未保存的草稿。";
    return loadProjectRequirements();
  }
  syncRequirementsEditor();
}
function syncRequirementsEditor() {
  const panel = requirementsEl("requirements-panel");
  const input = requirementsEl("requirements-input");
  if (!panel || !input || panel.classList.contains("hidden")) return;
  const status = requirementsEl("requirements-status");
  const count = requirementsEl("requirements-count");
  const saveBtn = requirementsEl("requirements-save-btn");
  const discardBtn = requirementsEl("requirements-discard-btn");
  const retryBtn = requirementsEl("requirements-retry-btn");
  const human = currentMemberIsHuman();
  const ready = requirementsUI.loaded && requirementsUI.supported;
  // 保存期间允许继续编辑；迟到的保存响应只按提交时文本对齐，不覆盖新草稿。
  input.readOnly = !human;
  input.disabled = !human || !ready;
  const dirty = ready && input.value !== (requirementsUI.saved ?? "");
  const length = workspaceRequirementsLength(input.value);
  const overLimit = length > REQUIREMENTS_MAX_CHARS;
  count.textContent = `${length} / ${REQUIREMENTS_MAX_CHARS} 字符`;
  count.classList.toggle("over", overLimit);
  saveBtn.disabled = requirementsUI.saving || !ready || !dirty || overLimit;
  discardBtn.disabled = requirementsUI.saving || !ready || !dirty;
  retryBtn.classList.toggle("hidden", !(!requirementsUI.loaded && requirementsUI.error && !requirementsUI.saving));
  let message = "", kind = "";
  if (!requirementsUI.loaded && requirementsUI.error) { message = requirementsUI.error; kind = "error"; }
  else if (requirementsUI.saving) message = "正在保存…";
  else if (requirementsUI.error) { message = requirementsUI.error; kind = "error"; }
  else if (!requirementsUI.loaded) message = "正在读取项目开发要求…";
  else if (overLimit) { message = `已超出 ${REQUIREMENTS_MAX_CHARS} 字符上限，请精简后再保存。`; kind = "error"; }
  else if (requirementsUI.notice) { message = requirementsUI.notice; kind = "success"; }
  else if (!human) message = "当前账号是 Agent，只能查看，不能修改。";
  else if (dirty) message = "有未保存的修改，尚未保存。";
  else message = requirementsUI.saved === null ? "当前还没有内容；保存后仅保留最新一份。" : "当前内容与服务端一致。";
  status.textContent = message;
  status.className = `requirements-status${kind ? ` ${kind}` : ""}`;
}
function recordRequirementsDraft() {
  const input = requirementsEl("requirements-input");
  if (!input) return;
  requirementsUI.notice = "";
  if (requirementsUI.projectId && requirementsUI.memberId) {
    const key = requirementsDraftKey(requirementsUI.projectId, requirementsUI.memberId);
    if (requirementsUI.loaded && input.value === (requirementsUI.saved ?? "")) requirementsDrafts.delete(key);
    else requirementsDrafts.set(key, input.value);
  }
  syncRequirementsEditor();
}
async function loadProjectRequirements() {
  const request = ++requirementsUI.request;
  const projectId = requirementsUI.projectId, memberId = requirementsUI.memberId;
  requirementsUI.error = "";
  syncRequirementsEditor();
  const current = () => request === requirementsUI.request
    && projectId === activeProjectId && projectId === requirementsUI.projectId
    && memberId === myId && memberId === requirementsUI.memberId;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) throw new Error(await readErrorDetail(res, `项目开发要求读取失败（${res.status}），请稍后重试。`));
    const data = await res.json();
    if (!current()) return;
    if (!data || !("development_requirements" in data)) {
      // 旧后端没有该字段：明确提示不支持并禁用保存，不把缺失当成 null 后再 PATCH。
      requirementsUI.supported = false;
      requirementsUI.loaded = false;
      requirementsUI.error = "当前服务尚未支持项目开发要求，暂时只能查看角色，不能编辑保存。";
    } else {
      requirementsUI.supported = true;
      requirementsUI.loaded = true;
      requirementsUI.saved = typeof data.development_requirements === "string" ? data.development_requirements : null;
      const key = requirementsDraftKey(projectId, memberId);
      const draft = requirementsDrafts.get(key);
      const input = requirementsEl("requirements-input");
      if (draft === undefined || draft === (requirementsUI.saved ?? "")) {
        requirementsDrafts.delete(key);
        if (input) input.value = requirementsUI.saved ?? "";
      }
      // 同步当前项目缓存，保持刷新前其它读取也是最新值。
      const project = projects.find(item => item.project_id === projectId);
      if (project) project.development_requirements = requirementsUI.saved;
    }
  } catch (err) {
    if (!current()) return;
    requirementsUI.loaded = false;
    requirementsUI.error = err.message || "项目开发要求读取失败，请重试。";
  }
  if (current()) syncRequirementsEditor();
}
async function saveProjectRequirements() {
  const input = requirementsEl("requirements-input");
  if (!input) return;
  const projectId = activeProjectId, memberId = myId;
  if (!projectId || requirementsUI.saving || !requirementsUI.loaded || !requirementsUI.supported) return;
  if (requirementsUI.projectId !== projectId || requirementsUI.memberId !== memberId) return;
  if (!currentMemberIsHuman()) return;
  const submitted = input.value;
  if (submitted === (requirementsUI.saved ?? "")) return;
  if (workspaceRequirementsLength(submitted) > REQUIREMENTS_MAX_CHARS) { syncRequirementsEditor(); return; }
  requirementsUI.saving = true;
  requirementsUI.error = ""; requirementsUI.notice = "";
  const request = ++requirementsUI.request;
  const normalized = normalizeRequirementsValue(submitted);
  syncRequirementsEditor();
  const current = () => request === requirementsUI.request
    && projectId === activeProjectId && projectId === requirementsUI.projectId
    && memberId === myId && memberId === requirementsUI.memberId;
  try {
    // 只显式提交这一个字段，不携带名称/路径等其它项目元数据；URL 绑定发起时项目。
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ development_requirements: submitted }),
    });
    if (!res.ok) throw new Error(await readErrorDetail(res, `保存失败（${res.status}），草稿已保留，请重试。`));
    const data = await res.json().catch(() => null);
    if (!current()) return;
    // 必须核实同项目响应确实带回字段且值与规范化提交一致，才算保存成功（防旧后端静默忽略字段）。
    if (!data || data.project_id !== projectId || !("development_requirements" in data)
        || data.development_requirements !== normalized) {
      throw new Error("服务未确认本次保存（响应未带回一致的 development_requirements），草稿已保留，请重试。");
    }
    requirementsUI.saved = data.development_requirements;
    const project = projects.find(item => item.project_id === projectId);
    if (project) project.development_requirements = requirementsUI.saved;
    const key = requirementsDraftKey(projectId, memberId);
    if (input.value === submitted) {
      requirementsDrafts.delete(key);
      // 全空白提交已被服务端归一为 null，编辑区同步成空文本，避免残留的空白被误当未保存修改。
      input.value = requirementsUI.saved ?? "";
      requirementsUI.notice = "已保存。";
    } else {
      // 保存期间继续编辑：保留新草稿，不把新草稿误标为已保存。
      requirementsDrafts.set(key, input.value);
      requirementsUI.notice = "先前内容已保存；当前仍有未保存的修改。";
    }
  } catch (err) {
    if (!current()) return;
    requirementsUI.error = err.message || "保存失败，草稿已保留，请重试。";
  } finally {
    if (current()) { requirementsUI.saving = false; syncRequirementsEditor(); }
  }
}
function discardProjectRequirements() {
  const input = requirementsEl("requirements-input");
  if (!input || requirementsUI.saving || !requirementsUI.loaded) return;
  requirementsDrafts.delete(requirementsDraftKey(requirementsUI.projectId, requirementsUI.memberId));
  input.value = requirementsUI.saved ?? "";
  requirementsUI.error = "";
  requirementsUI.notice = "已恢复为已保存的内容。";
  syncRequirementsEditor();
}
// ── ROLE-DESC-F1 角色说明编辑区（角色页，绑定具体在册角色） ─────────────
// 静态 DOM 区块（index.html 中位于名称区 #role-details-name-panel 与参与任务区
// #role-details-tasks-panel 之间，三者同级），动态 replaceChildren 不触碰它：
// 5 秒轮询/任务变化触发的重绘不会销毁 textarea，内容/焦点/光标天然保持。
// 可见性统一由 renderTaskDetailsPanel（app.js）同步。
// 数据来自既有 GET /api/projects/{id}/agents 响应的 role_description 字段（B1）：
// null = 无自定义、使用默认文案；写走专用 PUT /agents/{member_id}/description（仅 human）。
// 说明是纯展示文本：不改变任务发起者归属、business_role 或任务权限。
const ROLE_DESCRIPTION_MAX_CHARS = 2000;
// 默认文案 = 短标签 + 换行 + 解释（无解释时只留标签行）；硬编码映射仅作为默认值生成器保留，
// 一旦存在自定义说明，展示端不再渲染映射内容。
function workspaceRoleDefaultDescription(businessRole) {
  const label = workspaceRoleLabel(businessRole);
  const explanation = workspaceRoleDescription(businessRole);
  return explanation ? `${label}\n${explanation}` : label;
}
// 有效说明 = 自定义 ?? 默认。后端归一化拒绝全空白，任何非 null 自定义都含非空白行，
// 不得把合法自定义值误回退到硬编码默认。
function workspaceRoleDescriptionText(agent) {
  const custom = agent?.role_description;
  return typeof custom === "string" ? custom : workspaceRoleDefaultDescription(agent?.business_role);
}
// D1：列表摘要取有效说明的首个非空行。判空用与后端一致的 Python str.isspace 空白集合
// （不得以 JS trim 判空：U+FEFF 虽非 Python 空白、可被保存为合法值，trim 会误判为空行
// 把合法自定义摘要误回退到硬编码标签）；展示内容按同一空白集合去两端。
const ROLE_DESCRIPTION_BLANK_EDGE = /^[\u0009-\u000d\u001c-\u001f\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u001f\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu;
function workspaceRoleSummary(agent) {
  for (const line of workspaceRoleDescriptionText(agent).split("\n")) {
    if (REQUIREMENTS_BLANK.test(line)) continue; // 空行开头不显示空白格
    const shown = line.replace(ROLE_DESCRIPTION_BLANK_EDGE, "");
    if (shown) return shown;
  }
  return workspaceRoleLabel(agent?.business_role);
}
// 归一化与后端 normalize_role_description 同序同集合（设计 §3.2-D8 唯一事实）：
// 先按 Python str.isspace() 空白集合判空白归 null（复用 REQ2 REQUIREMENTS_BLANK，
// 不得以 JS trim() 代替——它会多算 U+FEFF、漏算 U+001C–U+001F/U+0085），非空白原文保留，
// 2000 码点上限只在非空白提交时检查。
function normalizeRoleDescriptionValue(value) {
  if (value === null || value === undefined) return null;
  const text = String(value);
  return REQUIREMENTS_BLANK.test(text) ? null : text;
}
// 读写状态绑定 账号/项目/角色member_id + 请求序号；草稿只存内存 Map
// （key = 账号/项目/成员），不写 localStorage：刷新或登出（页面重载）即清空，
// 同项目轮询/导航不覆盖，切项目往返可按 key 恢复。不复制已随 I-2 退役的主控指定面板 CAS/saveToken。
const roleDescriptionUI = { projectId: null, memberId: null, accountId: null, supported: false, loaded: false, saving: false, request: 0, saved: null, error: "", notice: "" };
const roleDescriptionDrafts = new Map();
function roleDescriptionEl(id) { return typeof document === "undefined" ? null : document.getElementById(id); }
function roleDescriptionDraftKey(projectId, accountId, memberId) { return `${accountId}/${projectId}/${memberId}`; }
function roleDescriptionCurrentRole() {
  return roleDescriptionUI.memberId
    ? workspaceRoles().find(item => item.member_id === roleDescriptionUI.memberId) || null
    : null;
}
function roleDescriptionBaseline() {
  // 有效已保存值：自定义 ?? 默认文案；dirty 判定以此为基准。
  return roleDescriptionUI.saved ?? workspaceRoleDefaultDescription(roleDescriptionCurrentRole()?.business_role);
}
// 从名册缓存采用服务端值（名册由 loadProjectAgents 统一加载/刷新，本面板不另发读请求）。
// 有草稿或保存中不得用服务端值覆盖输入框；无草稿时跟进最新 saved，赋值前判等避免光标跳动。
function adoptRoleDescriptionServerValue() {
  const entry = roleDescriptionUI.projectId === activeProjectId && roleDescriptionUI.accountId === myId
    ? projectAgents.find(item => item.member_id === roleDescriptionUI.memberId)
    : undefined;
  if (!entry) { roleDescriptionUI.loaded = false; roleDescriptionUI.supported = false; return; }
  // 旧服务缺 role_description 字段：降级只读并提示，不把缺失当成 null 后再 PUT。
  const supported = "role_description" in entry;
  roleDescriptionUI.supported = supported;
  roleDescriptionUI.loaded = true;
  roleDescriptionUI.saved = supported && typeof entry.role_description === "string" ? entry.role_description : null;
  const key = roleDescriptionDraftKey(roleDescriptionUI.projectId, roleDescriptionUI.accountId, roleDescriptionUI.memberId);
  const draft = roleDescriptionDrafts.get(key);
  const baseline = roleDescriptionBaseline();
  const input = roleDescriptionEl("role-description-input");
  if (draft !== undefined && draft !== baseline) return; // 草稿优先，输入框保持用户内容
  roleDescriptionDrafts.delete(key);
  if (input && !roleDescriptionUI.saving && input.value !== baseline) input.value = baseline;
}
function renderRoleDescriptionPanel() {
  const panel = roleDescriptionEl("role-description-panel");
  if (!panel) return;
  // 与角色详情同一可见条件：角色模式 + 选中具体在册角色（非项目设置）；其余导航一律隐藏。
  const visible = blackboardOpen && workspaceUI.mode === "roles" && !workspaceSettingsSelected()
    && Boolean(activeProjectId) && Boolean(myId)
    && !projectAgents.find(role => role.member_id === workspaceUI.selectedRole)?.archived;
  panel.classList.toggle("hidden", !visible);
  if (!visible) return;
  const projectId = activeProjectId, accountId = myId, memberId = workspaceUI.selectedRole;
  if (roleDescriptionUI.projectId !== projectId || roleDescriptionUI.memberId !== memberId
      || roleDescriptionUI.accountId !== accountId) {
    // 上下文切换（含 A→B→A 往返）：递增请求序号作废旧读写，按新上下文重建状态。
    ++roleDescriptionUI.request;
    Object.assign(roleDescriptionUI, { projectId, memberId, accountId, supported: false, loaded: false, saving: false, saved: null, error: "", notice: "" });
    adoptRoleDescriptionServerValue();
    const draft = roleDescriptionDrafts.get(roleDescriptionDraftKey(projectId, accountId, memberId));
    const input = roleDescriptionEl("role-description-input");
    if (input && draft !== undefined && input.value !== draft) {
      input.value = draft;
      roleDescriptionUI.notice = "已恢复上次未保存的草稿。";
    }
  } else {
    // 同上下文的名册刷新（轮询/手动刷新/sync）可能带回新服务端值：按草稿纪律跟进。
    adoptRoleDescriptionServerValue();
  }
  syncRoleDescriptionEditor();
}
function syncRoleDescriptionEditor() {
  const panel = roleDescriptionEl("role-description-panel");
  const input = roleDescriptionEl("role-description-input");
  if (!panel || !input || panel.classList.contains("hidden")) return;
  const status = roleDescriptionEl("role-description-status");
  const count = roleDescriptionEl("role-description-count");
  const saveBtn = roleDescriptionEl("role-description-save");
  const discardBtn = roleDescriptionEl("role-description-discard");
  const resetBtn = roleDescriptionEl("role-description-reset");
  const human = currentMemberIsHuman();
  const ready = roleDescriptionUI.loaded && roleDescriptionUI.supported;
  // 值来源优先级 = 草稿 ?? 已保存 ?? 默认；无草稿时判等赋值，避免无意义 value 写入导致光标跳动。
  const key = roleDescriptionUI.projectId
    ? roleDescriptionDraftKey(roleDescriptionUI.projectId, roleDescriptionUI.accountId, roleDescriptionUI.memberId)
    : null;
  const draft = key ? roleDescriptionDrafts.get(key) : undefined;
  if (draft === undefined && !roleDescriptionUI.saving) {
    const target = roleDescriptionUI.loaded ? roleDescriptionBaseline() : "";
    if (input.value !== target) input.value = target;
  }
  const baseline = roleDescriptionBaseline();
  const dirty = ready && input.value !== baseline;
  const length = workspaceRequirementsLength(input.value);
  // N1 修正：先归一化空白再判超限——全空白提交归 null（恢复默认）不受长度约束，
  // 仅非空白值适用 2000 码点上限；计数展示仍用原始长度。
  const overLimit = normalizeRoleDescriptionValue(input.value) !== null && length > ROLE_DESCRIPTION_MAX_CHARS;
  count.textContent = `${length} / ${ROLE_DESCRIPTION_MAX_CHARS} 字符`;
  count.classList.toggle("over", overLimit);
  // agent 账号整组编辑控件隐藏、只读展示；human 在旧服务/未加载完成时禁用保存。
  for (const btn of [saveBtn, discardBtn, resetBtn]) btn.classList.toggle("hidden", !human);
  saveBtn.disabled = roleDescriptionUI.saving || !ready || !dirty || overLimit;
  discardBtn.disabled = roleDescriptionUI.saving || !ready || !dirty;
  // 恢复默认 = 填回默认文案并提交（发送 null）；已是默认且无修改时无可恢复。
  resetBtn.disabled = roleDescriptionUI.saving || !ready || (!dirty && roleDescriptionUI.saved === null);
  // N4 修正：agent 与旧服务只读态只用 readOnly（文本可选中复制），不再 disabled；
  // 两种只读态都没有可操作的保存按钮（agent 隐藏、旧服务禁用）。
  input.readOnly = !human || !ready;
  let message = "", kind = "";
  if (roleDescriptionUI.error) { message = roleDescriptionUI.error; kind = "error"; }
  else if (roleDescriptionUI.saving) message = "正在保存…";
  else if (!roleDescriptionUI.loaded) message = "正在读取角色说明…";
  else if (!roleDescriptionUI.supported) { message = "当前服务尚未支持保存角色说明，暂时只能查看。"; kind = "error"; }
  else if (overLimit) { message = `已超出 ${ROLE_DESCRIPTION_MAX_CHARS} 字符上限，请精简后再保存。`; kind = "error"; }
  else if (roleDescriptionUI.notice) { message = roleDescriptionUI.notice; kind = "success"; }
  else if (!human) message = "当前账号是 Agent，只能查看，不能修改。";
  else if (dirty) message = "有未保存的修改，尚未保存。";
  else message = roleDescriptionUI.saved === null ? "当前使用默认说明；保存空白内容或恢复默认都会回到默认文案。" : "当前内容与服务端一致。";
  status.textContent = message;
  status.className = `role-description-status${kind ? ` ${kind}` : ""}`;
}
function recordRoleDescriptionDraft() {
  const input = roleDescriptionEl("role-description-input");
  if (!input) return;
  roleDescriptionUI.notice = "";
  if (roleDescriptionUI.projectId && roleDescriptionUI.memberId && roleDescriptionUI.accountId) {
    const key = roleDescriptionDraftKey(roleDescriptionUI.projectId, roleDescriptionUI.accountId, roleDescriptionUI.memberId);
    if (roleDescriptionUI.loaded && input.value === roleDescriptionBaseline()) roleDescriptionDrafts.delete(key);
    else roleDescriptionDrafts.set(key, input.value);
  }
  syncRoleDescriptionEditor();
}
async function saveRoleDescription() {
  const input = roleDescriptionEl("role-description-input");
  if (!input) return;
  const { projectId, accountId, memberId } = roleDescriptionUI;
  if (!projectId || !memberId || roleDescriptionUI.saving || !roleDescriptionUI.loaded || !roleDescriptionUI.supported) return;
  if (projectId !== activeProjectId || accountId !== myId) return;
  if (!currentMemberIsHuman()) return;
  const defaultText = workspaceRoleDefaultDescription(roleDescriptionCurrentRole()?.business_role);
  const submitted = input.value;
  if (submitted === (roleDescriptionUI.saved ?? defaultText)) return;
  // 归一化与后端同序：全空白（含 ""）或与默认文案逐字相等都发送 null（恢复默认、不落库）；
  // 只有非空白提交才查 2000 码点上限。
  const normalized = submitted === defaultText ? null : normalizeRoleDescriptionValue(submitted);
  if (normalized !== null && workspaceRequirementsLength(normalized) > ROLE_DESCRIPTION_MAX_CHARS) { syncRoleDescriptionEditor(); return; }
  roleDescriptionUI.saving = true;
  roleDescriptionUI.error = ""; roleDescriptionUI.notice = "";
  const request = ++roleDescriptionUI.request;
  syncRoleDescriptionEditor();
  const current = () => request === roleDescriptionUI.request
    && projectId === activeProjectId && projectId === roleDescriptionUI.projectId
    && accountId === myId && accountId === roleDescriptionUI.accountId
    && memberId === roleDescriptionUI.memberId && memberId === workspaceUI.selectedRole;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(memberId)}/description`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: normalized }),
    });
    if (!current()) return;
    if (res.status === 404) {
      const detail = await readErrorDetail(res, "");
      if (!current()) return;
      if (/not in the project roster/.test(detail)) {
        roleDescriptionUI.error = "该角色当前不在项目名册中，说明未保存。请刷新角色列表后重试。";
      } else if (/project not found/.test(detail)) {
        // N3 修正：项目被并发删除只报错、保留草稿可重试，不武断判定为旧服务不支持。
        roleDescriptionUI.error = "项目不存在或已被删除，说明未保存。草稿已保留，请确认项目后重试。";
      } else {
        // N3 修正：其它 404（网关/反代兜底、路由缺失等）同样不翻转 supported——旧服务缺
        // role_description 字段的降级只读已由名册字段判定；此处只准确报错、保留草稿、可重试。
        roleDescriptionUI.error = `保存失败（接口返回 404${detail ? `：${detail}` : ""}），本次未保存。草稿已保留，请刷新后重试。`;
      }
      return;
    }
    if (!res.ok) throw new Error(await readErrorDetail(res, `保存失败（${res.status}），草稿已保留，请重试。`));
    const data = await res.json().catch(() => null);
    if (!current()) return;
    // 必须核实同项目/同成员响应带回与归一化提交一致的 description，才算保存成功（防旧服务静默忽略）。
    if (!data || data.project_id !== projectId || data.member_id !== memberId
        || !("description" in data) || data.description !== normalized) {
      throw new Error("服务未确认本次保存（响应未带回一致的 description），草稿已保留，请重试。");
    }
    roleDescriptionUI.saved = data.description;
    // D2：核实通过后立即更新名册缓存并显式重绘列表摘要，无需刷新页面。
    const agent = projectAgents.find(item => item.member_id === memberId);
    if (agent) agent.role_description = data.description;
    const key = roleDescriptionDraftKey(projectId, accountId, memberId);
    if (input.value === submitted) {
      roleDescriptionDrafts.delete(key);
      // 空白提交已被归一为 null：编辑区同步回默认文案，残留空白不被误当未保存修改。
      const target = roleDescriptionUI.saved ?? defaultText;
      if (input.value !== target) input.value = target;
      roleDescriptionUI.notice = normalized === null ? "已恢复默认说明。" : "已保存。";
    } else {
      // 保存期间继续编辑：保留新草稿，不把新草稿误标为已保存。
      roleDescriptionDrafts.set(key, input.value);
      roleDescriptionUI.notice = "先前内容已保存；当前仍有未保存的修改。";
    }
    renderWorkspaceList();
  } catch (err) {
    if (!current()) return;
    roleDescriptionUI.error = err.message || "保存失败，草稿已保留，请重试。";
  } finally {
    if (current()) { roleDescriptionUI.saving = false; syncRoleDescriptionEditor(); }
  }
}
function discardRoleDescription() {
  const input = roleDescriptionEl("role-description-input");
  if (!input || roleDescriptionUI.saving || !roleDescriptionUI.loaded) return;
  roleDescriptionDrafts.delete(roleDescriptionDraftKey(roleDescriptionUI.projectId, roleDescriptionUI.accountId, roleDescriptionUI.memberId));
  const target = roleDescriptionBaseline();
  if (input.value !== target) input.value = target;
  roleDescriptionUI.error = "";
  roleDescriptionUI.notice = "已恢复为已保存的内容。";
  syncRoleDescriptionEditor();
}
// 恢复默认 = 把编辑区填回默认文案并提交（判等后发送 null），与保存空白同效。
function resetRoleDescription() {
  const input = roleDescriptionEl("role-description-input");
  if (!input || roleDescriptionUI.saving || !roleDescriptionUI.loaded || !roleDescriptionUI.supported) return;
  if (!currentMemberIsHuman()) return;
  const defaultText = workspaceRoleDefaultDescription(roleDescriptionCurrentRole()?.business_role);
  if (input.value !== defaultText) {
    input.value = defaultText;
    recordRoleDescriptionDraft();
  }
  saveRoleDescription();
}
function renderWorkspaceList() {
  const rolesMode = workspaceUI.mode === "roles";
  // 开发要求编辑区的可见性统一由 renderTaskDetailsPanel() 同步（app.js），覆盖群聊等不经本函数的导航路径。
  syncWorkspaceLayout();
  blackboardTitle.textContent = rolesMode ? "角色" : "任务";
  blackboardDescription.textContent = rolesMode
    ? "参与协作的助手"
    : "按你委派的工作整理";
  const search = document.getElementById("workspace-search");
  search.placeholder = rolesMode ? "搜索角色" : "搜索任务";
  search.setAttribute("aria-label", search.placeholder);
  blackboardColumns.replaceChildren(); blackboardSummary.replaceChildren();
  const batchActions = document.getElementById("role-service-batch-actions");
  const batchFeedbackContainer = document.getElementById("role-service-batch-feedback");
  batchActions.replaceChildren(); batchFeedbackContainer.replaceChildren();
  batchActions.classList.toggle("hidden", !rolesMode);
  batchFeedbackContainer.classList.toggle("hidden", !rolesMode);
  blackboardSummary.classList.toggle("hidden", rolesMode);
  blackboardEmpty.classList.add("hidden"); blackboardColumns.classList.remove("hidden");
  const query = workspaceUI.query.trim().toLocaleLowerCase();
  if (rolesMode) {
    const roles = workspaceRoles();
    // 选中角色失效（移出名册/禁用/切项目）时回退到“项目设置”，不保留无效选择、不自动改选其它角色。
    if (!roles.some(role => role.member_id === workspaceUI.selectedRole)) {
      workspaceUI.selectedRole = null;
      if (workspaceUI.roleSelection === "role") workspaceUI.roleSelection = "settings";
    }
    // 固定首项“项目设置”：独立导航项，不参与角色搜索过滤，名册为空时也可达。
    const settingsRow = workspaceButton("", () => { workspaceUI.roleSelection = "settings"; renderWorkspaceList(); renderTaskDetailsPanel(); }, "role-row role-settings-row");
    settingsRow.classList.toggle("selected", workspaceSettingsSelected());
    settingsRow.setAttribute("aria-pressed", String(workspaceSettingsSelected()));
    settingsRow.append(workspaceEl("strong", "", "项目设置"), workspaceEl("span", "", "开发要求 · 调度模式 · 宿主配置"), workspaceEl("small", "", "项目级 · 不属于任何角色"));
    const settingsEntry = workspaceEl("div", "role-entry role-settings-entry");
    settingsEntry.classList.toggle("selected", workspaceSettingsSelected());
    settingsEntry.appendChild(settingsRow);
    blackboardColumns.appendChild(settingsEntry);
    // ROLE-DESC-F1：搜索范围 = 成员名 + 有效说明全文（自定义 ?? 默认）+ 原始 business_role。
    const matchedRoles = roles.filter(item => `${workspaceMemberName(item.member_id)} ${workspaceRoleDescriptionText(item)} ${item.business_role || ""}`.toLocaleLowerCase().includes(query));
    for (const role of matchedRoles) {
      // R1-3 布局修正：角色行与其服务控制包进同一个 .role-entry，条目自己只有一条底边线，
      // 状态标签留在行内正常流中，不再用负外边距压到行边框上；两个子块各自负责左右留白。
      const entry = workspaceEl("div", "role-entry");
      const row = workspaceButton("", () => { workspaceUI.roleSelection = "role"; workspaceUI.selectedRole = role.member_id; renderWorkspaceList(); renderTaskDetailsPanel(); }, "role-row");
      row.dataset.memberId = role.member_id;
      row.classList.toggle("selected", !workspaceSettingsSelected() && role.member_id === workspaceUI.selectedRole);
      row.setAttribute("aria-pressed", String(!workspaceSettingsSelected() && role.member_id === workspaceUI.selectedRole));
      entry.classList.toggle("selected", !workspaceSettingsSelected() && role.member_id === workspaceUI.selectedRole);
      // 摘要列取有效说明的首个非空行：自定义后不再显示过时的硬编码短标签。
      row.append(workspaceEl("strong", "", workspaceMemberName(role.member_id)), workspaceEl("span", "", workspaceRoleSummary(role)));
      // 列表省去空闲提示，绑定摘要只保留短名；有进行中任务时仍显示数量，详情保留完整工作提示。
      const workSummary = workspaceWorkSummary(role.member_id, { hideEmpty: true });
      if (workSummary) row.appendChild(workspaceEl("small", "", workSummary));
      row.appendChild(workspaceEl("small", "role-binding-summary", workspaceRoleBindingSummary(role)));
      entry.appendChild(row);
      if (role.deletion) row.appendChild(workspaceEl("small", "role-delete-summary", role.deletion.status === "failed" ? "删除未完成" : "正在删除…"));
      // R1-3：受管服务控制作为角色行的同级块（行本身是 <button>，不能再嵌套按钮）；未归档才显示。
      if (role.archived !== true) {
        const serviceControls = workspaceRoleServiceControls(role);
        if (serviceControls) entry.appendChild(serviceControls);
      }
      blackboardColumns.appendChild(entry);
    }
    // “项目设置”不计入角色数量：空名册/无匹配的提示只针对真实角色行。
    if (!matchedRoles.length) blackboardColumns.appendChild(workspaceEl("p", "workspace-empty", roles.length ? "没有匹配的角色" : "这个项目还没有配置角色。"));
    // R1-3：项目级“全部启动”进顶栏操作区，批量进度/失败/重试进独立反馈区；任务页筛选入口不受影响。
    batchActions.appendChild(workspaceRoleServiceStartAllButton());
    if (typeof roleRequestApp !== "undefined") {
      const create = roleRequestApp?.newButton(); if (create) batchActions.insertBefore(create, batchActions.firstChild);
    }
    const batchFeedback = workspaceRoleServiceBatchFeedback();
    if (batchFeedback) batchFeedbackContainer.appendChild(batchFeedback);
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
    // 主任务列表固定 20 条/页：在原完整可见集合的根任务/family/四筛选/搜索与原顺序之后再切片，
    // 总数按筛选后的根任务计（子任务卡片不计入），不改任务接口或加载范围。
    const totalPages = Math.max(1, Math.ceil(tasks.length / TASK_LIST_PAGE_SIZE));
    if (taskListPageUI.page > totalPages) taskListPageUI.page = totalPages;
    if (taskListPageUI.page < 1) taskListPageUI.page = 1;
    const pageStart = (taskListPageUI.page - 1) * TASK_LIST_PAGE_SIZE;
    for (const task of tasks.slice(pageStart, pageStart + TASK_LIST_PAGE_SIZE)) blackboardColumns.appendChild(workspaceTaskRow(task));
    // 0 项保原空态、不显示空翻页栏；有结果时底部一行简洁翻页。
    if (tasks.length) blackboardColumns.appendChild(workspaceTaskListPagination(tasks.length, totalPages));
  }
  if (!blackboardColumns.childElementCount) blackboardColumns.appendChild(workspaceEl("p", "workspace-empty", query ? "没有匹配的结果" : rolesMode ? "这个项目还没有配置角色。" : "当前筛选下没有任务。"));
  // R1-3：重绘后按最新投影决定是否（继续）轮询受管服务状态；无 starting/stopping 时不建立计时器。
  maybeStartRoleServicePolling();
}
// ── ROLE-BINDING-B4 角色运行器/模型绑定（角色页只读展示，合同 §4.3–4.4） ─────
// 数据来源：同一次 GET /api/projects/{id}/agents 响应里已有的 binding / binding_state
// （B1a 后端、B3 工具只读消费）。本片不新增任何每角色 GET/PUT，也不从 instances.runtime、
// 运行中的模型或成员展示名回填绑定——绑定只认这两个字段。
// 只消费公开白名单字段：runtime / runner_display_name / model_source / provider_id /
// connection_ref / model_id / model_alias / model_display_name + binding_state；
// 未知字段一律不读不显示，凭据与日志不进入 UI。全部值走 textContent（workspaceEl）渲染，
// connection_ref / provider_id 只作普通文本，不解析、不跳转、不探测、不拼命令。
// 合同 §4.4 阶梯：unconfigured（"未配置"）、not_in_roster（"已离册（保留配置）"）、行内缺值
// （"模型未上报"）与旧服务未提供字段（未知）四类严格区分；未知不伪装成未配置，未配置不当接入失败。
// 产品展示名规则（D-5）未决：只展示 API 已有值，不制定命名规则、不批量改名；B2 证据片未落地，
// 本片不输出 binding_match*、不写任何一致性结论、不推断型号。
// 列表只展示绑定状态、运行器短名和一次模型名；详情属性区已退役。
const ROLE_BINDING_STATES = {
  no_project: ["无项目上下文", "unknown"],
  member_missing: ["成员不存在（保留配置）", "invalid"],
  member_disabled: ["成员已禁用（保留配置）", "invalid"],
  not_in_roster: ["已离册（保留配置）", "invalid"],
  not_agent: ["非 Agent 成员（保留配置）", "invalid"],
  unconfigured: ["未配置", "neutral"],
  partial: ["配置不完整（无效）", "invalid"],
  runner_missing: ["运行器未登记（无效）", "invalid"],
  runner_retired: ["运行器已退役（无效）", "invalid"],
  bound: ["已绑定", "ok"],
};
function roleBindingSource(agent) { return agent && typeof agent === "object" && !Array.isArray(agent) ? agent : null; }
// 「没有 binding 字段」（旧服务）与「binding 为 null」（没有存储行）是两件事，必须分开判断。
function roleBindingRow(agent) {
  const source = roleBindingSource(agent);
  if (!source || !Object.prototype.hasOwnProperty.call(source, "binding")) return { supported: false, present: false, row: null };
  const row = source.binding;
  if (row && typeof row === "object" && !Array.isArray(row)) return { supported: true, present: true, row };
  return { supported: true, present: false, row: null };
}
function roleBindingText(value) { return typeof value === "string" && value.trim() ? value : null; }
// binding_state 优先取顶层字段（合同 §4.3 始终存在）；顶层缺失且行内自带非空状态时复用同一事实，
// 两者都没有才算“当前服务未提供”；空值记“未记录”；服务返回的枚举不在白名单时如实标为未知原值。
function roleBindingStateInfo(agent, row) {
  const source = roleBindingSource(agent);
  let provided = false;
  let raw;
  if (source && Object.prototype.hasOwnProperty.call(source, "binding_state")) { provided = true; raw = source.binding_state; }
  else if (row && typeof row.binding_state === "string" && row.binding_state.trim()) { provided = true; raw = row.binding_state; }
  const value = typeof raw === "string" ? raw.trim() : "";
  if (!provided) return { provided: false, known: false, key: null, label: "当前服务未提供绑定状态", text: "当前服务未提供绑定状态", kind: "unknown" };
  if (!value) return { provided: true, known: false, key: null, label: "绑定状态未记录", text: "绑定状态未记录", kind: "unknown" };
  // F1 修正：两张枚举映射都是普通对象，直接下标会把 constructor/__proto__/toString 等继承键
  // 当成已知枚举（label/kind 变 undefined）。这里只接受自有白名单键，继承键与任意未知值一律按
  // “未知绑定状态（原值）”降级；不引入新的安全框架，也不改合法枚举与未提供/未记录的既有分支。
  if (!Object.prototype.hasOwnProperty.call(ROLE_BINDING_STATES, value)) return { provided: true, known: false, key: value, label: "未知绑定状态", text: `未知绑定状态（${value}）`, kind: "unknown" };
  const known = ROLE_BINDING_STATES[value];
  return { provided: true, known: true, key: value, label: known[0], text: known[0], kind: known[1] };
}
// 运行器登记名可能附有“· 当前模型 执行”，只去掉与真实模型字段相同的尾段，保留其它自定义名称。
// 有展示名时不再拼接 runtime；缺展示名仍按已上报 runtime 如实降级。
// 280：三个 Kimi 角色共用旧登记名“Kimi Code · K2.8 Preview 执行”（及不带“执行”的版本），
// 该名称是历史系统名、不含当前模型事实。仅对 runtime=kimi-code 且登记名精确匹配这一已知旧系统名时，
// 列表运行器短名统一为 Kimi Code，模型段仍用当前 binding 模型（K3 保持 K3）；
// 不泛化截断自定义名称，不改运行器/角色永久名称或绑定数据。
const ROLE_BINDING_KIMI_CODE_LEGACY_NAMES = new Set(["Kimi Code · K2.8 Preview 执行", "Kimi Code · K2.8 Preview"]);
function roleBindingRunnerText(row, missing) {
  const name = roleBindingText(row.runner_display_name);
  const runtime = roleBindingText(row.runtime);
  if (name && runtime === "kimi-code" && ROLE_BINDING_KIMI_CODE_LEGACY_NAMES.has(name.trim())) return "Kimi Code";
  const model = roleBindingModelText(row, null);
  const withoutRole = name?.replace(/\s+执行$/, "");
  const suffix = model && ` · ${model}`;
  const shortName = suffix && withoutRole?.endsWith(suffix) ? withoutRole.slice(0, -suffix.length).trim() : name;
  return shortName || name || runtime || missing;
}
// 紧凑摘要的取值优先级仅为压缩显示，不改写字段含义：模型展示名 → 模型别名 → 模型 ID。
function roleBindingModelText(row, missing) {
  return roleBindingText(row.model_display_name) || roleBindingText(row.model_alias) || roleBindingText(row.model_id) || missing;
}
// 280：公开 binding 没有独立的思考强度字段，只从明确的 model_display_name 最后一个中点段拆
// 已知强度字面量（匹配忽略大小写，显示保留原值），前段（模型名）须非空；未知后缀原样保留为模型名，
// 不据别名/成员名/运行实例或 native 配置猜值，alias/id 降级值不做强度拆分。
// 拆不出强度时返回 null：摘要省略该项与对应分隔符，不显示“未提供/未知/默认”等占位。
const ROLE_BINDING_THINKING_STRENGTHS = new Set(["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]);
function roleBindingModelAndStrength(row) {
  const display = roleBindingText(row.model_display_name);
  const model = roleBindingModelText(row, null);
  let strength = null;
  let modelName = model;
  if (display) {
    const cut = display.lastIndexOf("·");
    const head = cut >= 0 ? display.slice(0, cut).trim() : "";
    const tail = cut >= 0 ? display.slice(cut + 1).trim() : "";
    if (head && tail && ROLE_BINDING_THINKING_STRENGTHS.has(tail.toLowerCase())) {
      modelName = head;
      strength = tail;
    }
  }
  return { modelName, strength };
}
function workspaceRoleBindingSummary(agent) {
  const row = roleBindingRow(agent);
  const state = roleBindingStateInfo(agent, row.row);
  if (!row.supported) return "绑定：当前服务未提供绑定信息";
  const parts = [state.label];
  if (row.present) {
    parts.push(roleBindingRunnerText(row.row, "运行器未上报"));
    const { modelName, strength } = roleBindingModelAndStrength(row.row);
    parts.push(modelName || "模型未上报");
    if (strength) parts.push(strength);
  }
  return `绑定：${parts.join(" · ")}`;
}
// ── R1-3 受管 CLI 服务：逐角色启动/关闭 与 项目级“全部启动” ─────────────────
// 数据来源（不新增每角色读请求）：角色行自带的 service 投影叠加最近一次动作响应/轮询结果。
// own property 判定沿用绑定区纪律：没有 `service` 字段（旧服务未上报）≠ `service: null`（未登记），
// 后者仍如实渲染禁用控件，不伪装成启动失败。
// 启停中、运行中及运行心跳失联的角色持续读取 GET /api/projects/{id}/role-services；
// 全部未启动/已关闭后不再续期；离开角色页/切项目/切账号
// 由 syncWorkspaceLayout（app.js 每次导航都会调用）停止定时器，在途响应按 token 丢弃，不泄漏计时器。
// 状态文案严格按设计 §11.2 映射；不因 binding_state / 实例自报 idle / can_start 之外的推断放开启动，
// 只有 control_kind === "managed_cli" 且 can_start 为真时才可能启用启动按钮。
const ROLE_SERVICE_STATUS_HINTS = {
  external_session: "需人工在原生客户端打开/登录；页面不提供受管启动。",
  missing: "未声明受管控制能力；页面不提供启动。",
  unregistered: "未登记受管服务，未声明受管控制能力；页面不提供启动。",
  unsupported: "该角色未上报受管服务信息，页面不提供启动；这不等于启动失败。",
};
const roleServiceUI = {
  projectId: null,
  memberId: null,
  overlay: new Map(),
  busy: new Set(),
  errors: new Map(),
  batch: null,
  pollTimer: null,
  pollBusy: false,
  pollToken: 0,
  actionRefresh: 0,
  pollError: "",
  pollDelayMs: 2000,
};
function roleServiceObject(value) { return value && typeof value === "object" && !Array.isArray(value) ? value : null; }
function roleServiceHuman() { return typeof currentMemberIsHuman === "function" ? Boolean(currentMemberIsHuman()) : true; }
function roleServicePageActive() {
  return typeof document !== "undefined" && blackboardOpen === true && workspaceUI.mode === "roles"
    && Boolean(activeProjectId) && Boolean(myId);
}
function roleServiceDeclared(role) {
  return Boolean(role) && typeof role === "object" && Object.prototype.hasOwnProperty.call(role, "service");
}
// 停止轮询并作废在途响应：递增 token 让迟到的 role-services 结果不再回写、不再续期。
function stopRoleServicePolling() {
  if (roleServiceUI.pollTimer !== null) {
    if (typeof clearTimeout === "function") clearTimeout(roleServiceUI.pollTimer);
    roleServiceUI.pollTimer = null;
  }
  roleServiceUI.pollBusy = false;
  ++roleServiceUI.pollToken;
}
// 项目/账号切换时清空覆盖层、在途标记与批量结果；同上下文重绘不清，避免轮询结果被吞。
function ensureRoleServiceContext() {
  if (roleServiceUI.projectId === activeProjectId && roleServiceUI.memberId === myId) return;
  stopRoleServicePolling();
  roleServiceUI.projectId = activeProjectId;
  roleServiceUI.memberId = myId;
  roleServiceUI.overlay = new Map();
  roleServiceUI.busy = new Set();
  roleServiceUI.errors = new Map();
  roleServiceUI.batch = null;
  roleServiceUI.actionRefresh = 0;
  roleServiceUI.pollError = "";
}
// app.js 每次导航/刷新都会经 renderWorkspaceMode → syncWorkspaceLayout；离页即停表。
function syncRoleServicePollingContext() {
  syncRoleNameEditor();
  if (!roleServicePageActive()) { stopRoleServicePolling(); return; }
  ensureRoleServiceContext();
}
function roleServiceView(role) {
  const memberId = role && typeof role.member_id === "string" ? role.member_id : "";
  const declared = roleServiceDeclared(role);
  const overlay = memberId ? roleServiceUI.overlay.get(memberId) : undefined;
  const raw = declared ? roleServiceObject(role.service) : null;
  return {
    memberId,
    declared,
    provided: declared || Boolean(overlay),
    service: overlay || raw,
    error: memberId ? (roleServiceUI.errors.get(memberId) || "") : "",
  };
}
function roleServiceShorten(text, max = 60) {
  const value = String(text).replace(/\s+/g, " ").trim();
  return value.length > max ? `${value.slice(0, max)}…` : value;
}
function roleServiceFailureReason(service) {
  const code = typeof service.error_code === "string" && service.error_code.trim() ? service.error_code.trim() : null;
  const message = typeof service.error_message === "string" && service.error_message.trim() ? service.error_message.trim() : null;
  if (code && message) return `${code}：${roleServiceShorten(message)}`;
  return code || (message ? roleServiceShorten(message) : null);
}
function roleServiceLivenessUnknown(service) {
  return service?.observed === "unknown" && [
    "instance_heartbeat_expired", "instance_unavailable", "instance_identity_mismatch",
  ].includes(service.error_code);
}
function roleServiceStopTimeout(service) {
  return service?.observed === "unknown" && service.error_code === "stop_timeout";
}
// 严格映射（设计 §11.2）：stopped = 人工关闭，不得显示失败；running 只有 readiness_service === "ready"
// 才是“启动成功”，否则是“启动中…”；未知枚举如实标未知，不伪装。
function roleServiceStatus(service) {
  if (!service) return { text: "未登记受管服务", kind: "unknown" };
  const observed = typeof service.observed === "string" ? service.observed : "";
  const readiness = typeof service.readiness_service === "string" ? service.readiness_service : "";
  const nativeLogin = typeof service.native_login === "string" ? service.native_login : "";
  if (observed === "stopped") return { text: "未启动（已关闭）", kind: "neutral" };
  if (observed === "not_started") return { text: "未启动", kind: "neutral" };
  if (observed === "starting") return { text: "启动中…", kind: "running" };
  if (observed === "stopping") return { text: "关闭中…", kind: "running" };
  if (roleServiceStopTimeout(service)) return { text: "关闭超时（状态待核实）", kind: "unknown" };
  if (roleServiceLivenessUnknown(service)) return { text: "运行状态待核实", kind: "unknown" };
  if (observed === "running") {
    if (readiness !== "ready") return { text: "启动中…", kind: "running" };
    return { text: nativeLogin === "unverified" ? "启动成功（原生登录未核验）" : "启动成功", kind: "success" };
  }
  if (service.ownership_held === true && observed !== "running" && observed !== "starting") {
    return { text: "启动失败（进程仍受管，请先关闭）", kind: "danger" };
  }
  if (service.last_result === "failed" && service.error_code === "readiness_timeout") {
    return { text: "启动失败（未就绪）", kind: "danger" };
  }
  if (observed === "failed") {
    const reason = roleServiceFailureReason(service);
    return { text: reason ? `启动失败（${reason}）` : "启动失败", kind: "danger" };
  }
  if (observed === "unknown" || !observed) return { text: "未知", kind: "unknown" };
  return { text: `未知（${observed}）`, kind: "unknown" };
}
function roleServiceControl(role) {
  const view = roleServiceView(role);
  const status = roleServiceStatus(view.service);
  const service = view.service;
  const busy = Boolean(view.memberId && roleServiceUI.busy.has(view.memberId));
  const batchBusy = Boolean(roleServiceUI.batch && roleServiceUI.batch.busy);
  const human = roleServiceHuman();
  const kind = service && typeof service.control_kind === "string" ? service.control_kind : "";
  const observed = service && typeof service.observed === "string" ? service.observed : "";
  const ownershipHeld = Boolean(service && service.ownership_held === true);
  let hint = "";
  if (!view.provided) hint = ROLE_SERVICE_STATUS_HINTS.unsupported;
  else if (!service) hint = ROLE_SERVICE_STATUS_HINTS.unregistered;
  else if (kind === "external_session") hint = ROLE_SERVICE_STATUS_HINTS.external_session;
  else if (kind !== "managed_cli") hint = ROLE_SERVICE_STATUS_HINTS.missing;
  const managed = kind === "managed_cli";
  // 启动只对受管 CLI 且服务自述可启动时开放；加载态（starting/stopping）与在途请求都禁用。
  // 原进程归属未释放（失败/过期/unknown 但仍有活进程）时**禁止**重复启动，必须先关闭。
  const canStart = managed && service.can_start === true && !ownershipHeld && !busy && !batchBusy && human
    && observed !== "starting" && observed !== "stopping";
  const canStop = Boolean(service) && service.can_stop === true && !busy && !batchBusy && human
    && observed !== "stopping";
  if (managed && !human) hint = "当前账号是 Agent，只能查看服务状态。";
  else if (managed && roleServiceStopTimeout(service) && !hint) hint = "关闭请求已超时，请检查原宿主及进程；确认已停止后进行人工恢复，不能重复启动。";
  else if (managed && roleServiceLivenessUnknown(service) && !hint) hint = "无法确认执行端仍在运行，请先检查服务宿主；确认停止前不能重复启动。";
  else if (managed && ownershipHeld && !hint) hint = "请先「关闭」并确认已停止，再重新启动。";
  else if (managed && service && service.can_start !== true && service.can_stop !== true && !hint) hint = "当前不可启动。";
  if (view.error) hint = view.error;
  return { view, status, busy, batchBusy, human, kind, observed, managed, ownershipHeld, canStart, canStop, hint };
}
// 角色列表只显示当前服务状态；启动/关闭操作仅放在角色详情。
function workspaceRoleServiceStateLabel(status) {
  return workspaceEl("span", `role-service-state ${status.kind}`, status.text);
}
function workspaceRoleServiceActions(role, className) {
  const control = roleServiceControl(role);
  if (!control.view.provided) return null;
  const box = workspaceEl("div", className);
  if (control.view.memberId) box.dataset.memberId = control.view.memberId;
  const row = workspaceEl("div", "role-service-row");
  const start = workspaceButton("启动", event => { event?.stopPropagation?.(); startRoleService(control.view.memberId); }, "role-service-button role-service-start");
  start.disabled = !control.canStart;
  start.setAttribute("aria-label", `启动 ${workspaceMemberName(control.view.memberId)} 的服务`);
  if (control.hint) start.title = control.hint;
  const stop = workspaceButton("关闭", event => { event?.stopPropagation?.(); stopRoleService(control.view.memberId); }, "role-service-button role-service-stop");
  stop.disabled = !control.canStop;
  stop.setAttribute("aria-label", `关闭 ${workspaceMemberName(control.view.memberId)} 的服务`);
  if (control.hint) stop.title = control.hint;
  row.append(start, stop);
  box.appendChild(row);
  if (control.hint) box.appendChild(workspaceEl("p", "role-service-hint", control.hint));
  return box;
}
function workspaceRoleServiceControls(role, className = "role-service-controls") {
  const control = roleServiceControl(role);
  if (!control.view.provided) return null;
  const box = workspaceEl("div", className);
  if (control.view.memberId) box.dataset.memberId = control.view.memberId;
  const listStatus = control.status.kind === "success" ? { ...control.status, text: "启动成功" } : control.status;
  box.appendChild(workspaceRoleServiceStateLabel(listStatus));
  const listHint = control.hint === "请先「关闭」并确认已停止，再重新启动。" ? "" : control.hint;
  if (listHint) box.appendChild(workspaceEl("p", "role-service-hint", listHint));
  return box;
}
const roleDeleteUI = {busy: new Set(), errors: new Map(), timer: null, context: null, generation: 0};
function roleDeleteKey(memberId) { return JSON.stringify([myId, activeProjectId, memberId]); }
function roleDeleteCurrent(context) {
  return context && context.account === myId && context.project === activeProjectId;
}
function roleDeleteMessage(code) {
  return ({role_service_running: "请先关闭角色，确认已停止后再删除。",
    role_instance_active: "仍有在线或状态未确认的角色实例，请先关闭。",
    role_has_active_tasks: "该角色还有未闭环任务，请先处理并收取结果。",
    role_has_active_schedules: "该角色还有定时任务，请先结束相关定时任务。",
    role_provision_active: "角色正在配置，请等配置结束后再删除。",
    role_delete_identity_proof_required: "独占身份归属未确认，请先核对角色名册及共享引用后再删除。",
    manager_not_stopped: "本机宿主尚未退出，请确认后台正常运行后重试。",
    local_runtime_required: "请先正常重载 TALK 后台，再重试清理。",
    runtime_config_changed: "本机配置已变化，请正常重载 TALK 后台后重试。",
    credential_mismatch: "专属凭据归属核验未通过，请核对后重试。",
    unsafe_resource: "资源归属或路径无法确认，请核对后重试。",
    cleanup_busy: "资源正被占用，请稍后重试。",
    cleanup_budget: "本轮清理尚未完成，请重试继续清理。"})[code] || "删除尚未完成，请稍后重试。";
}
function roleDeleteApply(context, value) {
  if (!roleDeleteCurrent(context) || value?.member_id !== context.member) return;
  if (typeof projectAgentRequest !== "undefined") projectAgentRequest++;
  const role = projectAgents.find(row => row.member_id === context.member);
  if (role?.deletion && Number.isInteger(role.deletion.revision) && Number.isInteger(value.revision)
      && value.revision < role.deletion.revision) return;
  if (value.status === "complete") {
    projectAgents = projectAgents.filter(row => row.member_id !== context.member);
  } else if (role) {
    role.archived = true; role.deletion = value;
    role.binding = null; role.role_description = null;
  }
  renderWorkspaceList(); renderTaskDetailsPanel();
}
async function deleteWorkspaceRole(memberId) {
  if (!currentMemberIsHuman() || !activeProjectId) return;
  const role = projectAgents.find(row => row.member_id === memberId);
  const key = roleDeleteKey(memberId);
  if (!role || roleDeleteUI.busy.has(key)) return;
  if (!role.deletion && !window.confirm(`删除角色「${workspaceMemberName(memberId)}」？\n将清除本项目角色配置和专属接入资源，保留历史任务、结果与消息。重新添加会创建新身份。`)) return;
  const context = {account:myId, project:activeProjectId, member:memberId};
  roleDeleteUI.busy.add(key); roleDeleteUI.errors.delete(key);
  renderWorkspaceRoleDetails();
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(context.project)}/roles/${encodeURIComponent(memberId)}/delete`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({confirm_member_id:memberId}),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(roleDeleteMessage(body.detail));
    if (body.member_id !== memberId || !["pending","cleaning","failed","complete"].includes(body.status)) throw new Error("删除回执不完整，请刷新核对。");
    roleDeleteApply(context, body);
  } catch (err) {
    if (roleDeleteCurrent(context)) roleDeleteUI.errors.set(key, err.message || "删除失败，请重试。");
  } finally {
    roleDeleteUI.busy.delete(key);
    if (roleDeleteCurrent(context)) renderWorkspaceRoleDetails();
  }
}
function roleDeleteButton(role) {
  if (!currentMemberIsHuman() || !("deletion" in role)) return null;
  const key = roleDeleteKey(role.member_id), service = roleServiceView(role).service;
  const pending = ["pending","cleaning"].includes(role.deletion?.status);
  const button = workspaceButton(role.deletion ? "重试清理" : "删除角色", () => deleteWorkspaceRole(role.member_id), "role-service-button role-delete-button");
  button.disabled = pending || roleDeleteUI.busy.has(key) || (!role.deletion && Boolean(service && (
    service.ownership_held || ["running","starting","stopping","unknown"].includes(service.observed))));
  if (button.disabled && !pending) button.title = "请先关闭角色并确认已停止。";
  return button;
}
function roleDeleteSync(role) {
  const context = role ? {account:myId, project:activeProjectId, member:role.member_id} : null;
  const key = context ? JSON.stringify(context) : null;
  if (roleDeleteUI.context !== key) {
    if (roleDeleteUI.timer) clearTimeout(roleDeleteUI.timer);
    roleDeleteUI.timer = null; roleDeleteUI.context = key;
    roleDeleteUI.generation++;
  }
  if (!role?.deletion || !["pending","cleaning"].includes(role.deletion.status) || roleDeleteUI.timer) return;
  const generation = roleDeleteUI.generation;
  roleDeleteUI.timer = setTimeout(async () => {
    try {
      const res = await apiFetch(`/api/projects/${encodeURIComponent(context.project)}/roles/${encodeURIComponent(context.member)}/deletion`);
      if (!res.ok) throw new Error("清理状态暂时无法读取，正在重试…");
      const body = await res.json();
      if (roleDeleteCurrent(context) && roleDeleteUI.context === key && roleDeleteUI.generation === generation) {
        roleDeleteUI.errors.delete(roleDeleteKey(context.member));
        roleDeleteApply(context, body);
      }
    } catch (err) {
      if (roleDeleteCurrent(context) && roleDeleteUI.context === key && roleDeleteUI.generation === generation) roleDeleteUI.errors.set(roleDeleteKey(context.member), err.message);
    } finally {
      if (roleDeleteUI.context === key && roleDeleteUI.generation === generation) {
        roleDeleteUI.timer = null;
        if (roleDeleteCurrent(context)) renderWorkspaceRoleDetails();
      }
    }
  }, 2000);
}
function workspaceRoleDeletePanel(role) {
  const section = workspaceEl("section", "role-delete-section");
  section.setAttribute("aria-live", "polite");
  if (!role.deletion && (role.archived || !roleServiceView(role).provided)) {
    const button = roleDeleteButton(role); if (button) section.appendChild(button);
  }
  if (role.deletion) {
    const failed = role.deletion.status === "failed";
    section.appendChild(workspaceEl("p", "", failed ? "删除未完成" : "正在清理角色专属资源…"));
    if (failed) section.appendChild(workspaceEl("p", "", roleDeleteMessage(role.deletion.error_code)));
    const labels = {manager:"本机宿主",profiles:"身份档",credentials:"专属凭据",private_state:"专属状态",startup_config:"启动配置"};
    for (const [step, state] of Object.entries(role.deletion.steps || {})) {
      if (state === "failed" || state === "pending") section.appendChild(workspaceEl("p", "", `${labels[step] || "资源"}：${state === "failed" ? "清理失败" : "待清理"}`));
    }
    if (failed) { const button = roleDeleteButton(role); if (button) section.appendChild(button); }
  }
  const error = roleDeleteUI.errors.get(roleDeleteKey(role.member_id));
  if (error) section.appendChild(workspaceEl("p", "role-delete-error", error));
  return section.childElementCount ? section : null;
}
function workspaceRoleServicePanel(role) {
  const control = roleServiceControl(role);
  if (!control.view.provided) return null;
  const section = workspaceEl("section", "role-service-section");
  section.setAttribute("aria-label", "角色开关");
  const head = workspaceEl("div", "role-service-head");
  head.appendChild(workspaceEl("h3", "", "角色开关"));
  section.appendChild(head);
  const controls = workspaceRoleServiceActions(role, "role-service-controls role-service-detail-controls");
  if (controls) section.appendChild(controls);
  const deleteButton = roleDeleteButton(role);
  if (deleteButton) (controls?.children[0] || section).appendChild(deleteButton);
  return section;
}
function roleServiceRoleName(memberId) {
  return workspaceRoles().some(item => item.member_id === memberId) ? workspaceMemberName(memberId) : memberId;
}
// 批量计数口径（返修 F6）：写入意图只算「启动请求」，**只有**本次动作真实收敛为
// running + readiness_service=ready 才算「已启动」；failed/unknown 一律进失败集合。
function roleServiceCountResults(results) {
  const counts = { requested: 0, started: 0, pending: 0, skipped: 0, failed: 0 };
  for (const item of Array.isArray(results) ? results : []) {
    if (item?.status === "ready") counts.started += 1;
    else if (item?.status === "requested") { counts.requested += 1; counts.pending += 1; }
    else if (item?.status === "skipped_running" || item?.status === "skipped_ownership_held") counts.skipped += 1;
    else if (item?.status === "failed") counts.failed += 1;
  }
  return counts;
}
// 轮询收敛：把「后到的 failed/unknown」归入本批次失败，把「真实 ready」计入已启动；
// 仍拥有进程的失败角色只提示先关闭，不进入失败重试集合（避免重复启动）。
function roleServiceBatchConverge(rows) {
  const batch = roleServiceUI.batch;
  if (!batch || batch.busy) return;
  const byMember = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const memberId = row && typeof row.member_id === "string" ? row.member_id : "";
    if (memberId) byMember.set(memberId, row);
  }
  let changed = false;
  for (const memberId of Object.keys(batch.launches || {})) {
    const track = batch.launches[memberId];
    const row = byMember.get(memberId);
    if (!row) continue;
    const settled = batch.settled[memberId] || "pending";
    const generation = row.generation;
    const sameAction = track && Number.isInteger(track.generation) && generation === track.generation;
    const observed = typeof row.observed === "string" ? row.observed : "";
    if (sameAction && roleServiceLivenessUnknown(row)
      && (settled === "pending" || settled === "liveness_unknown")) {
      if (settled !== "liveness_unknown") {
        batch.settled[memberId] = "liveness_unknown";
        changed = true;
      }
      continue;
    }
    if (settled === "failed_owned") {
      if (row.ownership_held === false && observed === "stopped" && row.can_start === true) {
        batch.settled[memberId] = "failed";
        changed = true;
      } else if (track && Number.isInteger(generation) && generation > track.generation
        && row.ownership_held === false && observed !== "stopping") {
        batch.settled[memberId] = "superseded";
        changed = true;
      }
      continue;
    }
    if (settled !== "pending" && settled !== "liveness_unknown") continue;
    // 人工关闭或新的动作取代本批次时，不把旧启动一直计为 pending，
    // 也不把后一个世代的成功误计成本批次成功。
    if (track && Number.isInteger(generation) && generation > track.generation) {
      batch.settled[memberId] = "superseded";
      changed = true;
      continue;
    }
    if (observed === "running" && row.readiness_service === "ready" && sameAction) {
      batch.settled[memberId] = "ready";
      changed = true;
    } else if ((observed === "failed" || observed === "unknown") && sameAction) {
      batch.settled[memberId] = row.ownership_held === true ? "failed_owned" : "failed";
      changed = true;
    }
  }
  if (changed) {
    const settled = Object.values(batch.settled || {});
    const originalSkipped = (Array.isArray(batch.results) ? batch.results : []).filter(item =>
      item?.status === "skipped_running" || (item?.status === "skipped_ownership_held"
        && !Object.prototype.hasOwnProperty.call(batch.settled, item.member_id))).length;
    batch.counts = Object.assign({}, batch.counts, {
      started: settled.filter(v => v === "ready").length,
      failed: (batch.requestFailures || []).length + settled.filter(v => v === "failed" || v === "failed_owned").length,
      pending: settled.filter(v => v === "pending").length,
      unknown: settled.filter(v => v === "liveness_unknown").length,
      skipped: originalSkipped + settled.filter(v => v === "superseded").length,
    });
  }
}
function roleServiceBatchFailedMembers(batch) {
  const failed = new Set(Array.isArray(batch?.requestFailures) ? batch.requestFailures : []);
  for (const [memberId, value] of Object.entries(batch?.settled || {})) {
    if (value === "failed") failed.add(memberId);
  }
  return [...failed];
}
function roleServiceBatchOwnedMembers(batch) {
  return Object.entries(batch?.settled || {})
    .filter(([, value]) => value === "failed_owned")
    .map(([memberId]) => memberId);
}
function roleServiceBatchRequestFailures(results) {
  return (Array.isArray(results) ? results : [])
    .filter(item => item && item.status === "failed" && typeof item.member_id === "string")
    .map(item => item.member_id);
}
// R1-3 布局修正：批量入口只渲染按钮（进顶栏操作区）；进度/失败/重试渲染在独立反馈区。
function workspaceRoleServiceStartAllButton() {
  const box = workspaceEl("div", "role-service-batch");
  const human = roleServiceHuman();
  const batch = roleServiceUI.batch;
  const startAll = workspaceButton("全部启动", () => startAllRoleServices(), "role-service-button role-service-start-all");
  startAll.disabled = Boolean(batch && batch.busy) || !human || !workspaceRoles().length;
  if (!human) startAll.title = "当前账号是 Agent，只能查看服务状态。";
  box.appendChild(startAll);
  return box;
}
// 反馈区：可换行、不挤占按钮位置。无任何反馈时返回 null，容器靠 CSS :empty 收起，不留空白条。
function workspaceRoleServiceBatchFeedback() {
  const box = workspaceEl("div", "role-service-batch-feedback-content");
  const batch = roleServiceUI.batch;
  if (batch && batch.busy) box.appendChild(workspaceEl("span", "role-service-batch-status", "正在全部启动…"));
  else if (batch && batch.error) box.appendChild(workspaceEl("span", "role-service-batch-status error", batch.error));
  else if (batch) {
    const counts = Object.assign(
      { requested: 0, started: 0, pending: 0, skipped: 0, failed: 0 },
      roleServiceCountResults(batch.results),
      batch.counts || {},
    );
    // 口径：写入的是「启动请求」；「已启动」只在真实 ready 后出现。
    box.appendChild(workspaceEl("span", "role-service-batch-status",
      `启动请求 ${counts.requested ?? 0} · 已启动 ${counts.started ?? 0} · 启动中 ${counts.pending ?? 0} · 跳过 ${counts.skipped ?? 0} · 失败 ${counts.failed ?? 0}`
      + (counts.unknown ? ` · 待核实 ${counts.unknown}` : "")));
    const failed = roleServiceBatchFailedMembers(batch);
    if (failed.length) {
      const names = failed.map(memberId => {
        const item = (Array.isArray(batch.results) ? batch.results : []).find(row => row && row.member_id === memberId);
        return `${roleServiceRoleName(memberId)}${item && item.error_code ? `（${item.error_code}）` : ""}`;
      }).join("、");
      box.appendChild(workspaceEl("span", "role-service-batch-failed", `失败：${names}`));
      const retry = workspaceButton("重试失败项", () => startAllRoleServices(failed), "role-service-button role-service-retry-failed");
      retry.disabled = Boolean(batch.busy);
      box.appendChild(retry);
    }
    const owned = roleServiceBatchOwnedMembers(batch);
    if (owned.length) {
      // 原进程归属未释放的角色不能重复启动：必须先在角色行上「关闭」。
      const names = owned.map(memberId => roleServiceRoleName(memberId)).join("、");
      box.appendChild(workspaceEl("span", "role-service-batch-owned", `需先关闭并确认已停止：${names}`));
    }
  }
  if (roleServiceUI.pollError) box.appendChild(workspaceEl("span", "role-service-batch-status error", roleServiceUI.pollError));
  return box.childElementCount ? box : null;
}
async function roleServiceErrorDetail(res, fallback) {
  const messages = {
    local_runtime_unavailable: "本机角色服务暂不可用，请检查启动终端后重试。",
    recovery_process_not_absent: "尚未确认原执行端已停止，请检查本机服务后重试关闭。",
    recovery_process_inventory_unknown: "暂时无法核实本机进程，请检查权限后重试关闭。",
    recovery_tasks_active: "该角色仍有未结束的任务，请先处理任务再关闭。",
    local_recovery_unverified: "暂时无法核实原执行端，请检查本机服务后重试关闭。",
  };
  try {
    if (typeof readErrorDetail === "function") {
      const detail = await readErrorDetail(res, fallback);
      return messages[detail] || detail;
    }
    const body = await res.json();
    if (body && typeof body.detail === "string" && body.detail) return messages[body.detail] || body.detail;
  } catch (_) { /* 响应体不可读时退回兜底文案 */ }
  return fallback;
}
// 动作响应只带回 desired/observed/generation/launch 等有限字段；合并到已有投影，不臆造其它事实。
function roleServiceMergeAction(base, data) {
  const merged = Object.assign({}, roleServiceObject(base) || {});
  if (!data || typeof data !== "object") return merged;
  if (typeof data.desired === "string") merged.desired = data.desired;
  if (typeof data.observed === "string") merged.observed = data.observed;
  if (Number.isInteger(data.generation)) merged.generation = data.generation;
  if (data.idempotent_stopped === true) {
    // 兼容旧服务响应中默认的observed=stopping；已确认停止的回执优先。
    Object.assign(merged, { observed: "stopped", ownership_held: false, can_stop: false,
      last_result: "stopped", error_code: null, error_message: null, current_launch: null });
  }
  if ((data.action === "start" || data.action === "stop") && data.idempotent_stopped !== true) {
    merged.current_launch = {
      launch_id: data.launch_id ?? null,
      action: data.action,
      state: "pending",
      expected_instance_id: data.expected_instance_id ?? null,
      launch_expires_at: data.launch_expires_at ?? null,
      claimed_at: null,
      reported_at: null,
      outcome: null,
      error_code: null,
    };
  }
  return merged;
}
function roleServiceBaseFor(memberId) {
  if (roleServiceUI.overlay.has(memberId)) return roleServiceUI.overlay.get(memberId);
  const role = workspaceRoles().find(item => item.member_id === memberId);
  return role && roleServiceDeclared(role) ? roleServiceObject(role.service) : null;
}
async function startRoleService(memberId) {
  const role = workspaceRoles().find(item => item.member_id === memberId);
  if (!role || role.archived === true || roleServiceUI.busy.has(memberId)) return;
  if (!roleServiceControl(role).canStart) return;
  if (!roleServicePageActive() || typeof apiFetch !== "function") return;
  const projectId = activeProjectId, accountId = myId;
  roleServiceUI.busy.add(memberId);
  roleServiceUI.errors.delete(memberId);
  renderWorkspaceList(); renderTaskDetailsPanel();
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/roles/${encodeURIComponent(memberId)}/service/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (projectId !== activeProjectId || accountId !== myId) return;
    if (!res.ok) {
      roleServiceUI.errors.set(memberId, await roleServiceErrorDetail(res, `启动失败（${res.status}），请稍后重试。`));
    } else {
      const data = await res.json().catch(() => null);
      roleServiceUI.overlay.set(memberId, roleServiceMergeAction(roleServiceBaseFor(memberId), data));
    }
  } catch (err) {
    if (projectId === activeProjectId && accountId === myId) roleServiceUI.errors.set(memberId, (err && err.message) || "启动请求失败，请重试。");
  } finally {
    roleServiceUI.busy.delete(memberId);
    if (projectId === activeProjectId && accountId === myId) { renderWorkspaceList(); renderTaskDetailsPanel(); }
  }
}
async function stopRoleService(memberId) {
  const role = workspaceRoles().find(item => item.member_id === memberId);
  if (!role || role.archived === true || roleServiceUI.busy.has(memberId)) return;
  if (!roleServiceControl(role).canStop) return;
  if (!roleServicePageActive() || typeof apiFetch !== "function") return;
  const projectId = activeProjectId, accountId = myId;
  roleServiceUI.busy.add(memberId);
  roleServiceUI.errors.delete(memberId);
  renderWorkspaceList(); renderTaskDetailsPanel();
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/roles/${encodeURIComponent(memberId)}/service/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (projectId !== activeProjectId || accountId !== myId) return;
    if (!res.ok) {
      roleServiceUI.errors.set(memberId, await roleServiceErrorDetail(res, `关闭失败（${res.status}），请稍后重试。`));
    } else {
      const data = await res.json().catch(() => null);
      roleServiceUI.overlay.set(memberId, roleServiceMergeAction(roleServiceBaseFor(memberId), data));
      if (data?.idempotent_stopped === true) roleServiceUI.actionRefresh = (roleServiceUI.actionRefresh || 0) + 1;
    }
  } catch (err) {
    if (projectId === activeProjectId && accountId === myId) roleServiceUI.errors.set(memberId, (err && err.message) || "关闭请求失败，请重试。");
  } finally {
    roleServiceUI.busy.delete(memberId);
    if (projectId === activeProjectId && accountId === myId) { renderWorkspaceList(); renderTaskDetailsPanel(); }
  }
}
// 批量结果逐角色合并（返修 F6）：写入意图只显示「启动中…」（进入轮询），
// 真实 ready 由轮询收敛后计成功；failed 记稳定错误码；skipped 不伪造成功。
function roleServiceApplyStartAll(results, batch) {
  for (const item of Array.isArray(results) ? results : []) {
    const memberId = item && typeof item.member_id === "string" ? item.member_id : "";
    if (!memberId) continue;
    const base = roleServiceBaseFor(memberId);
    if (item.status === "failed") {
      roleServiceUI.errors.set(memberId, item.error_code || "启动失败");
      roleServiceUI.overlay.set(memberId, Object.assign({}, base || {}, {
        desired: "stopped", observed: "failed", last_action: "start", last_result: "failed", error_code: item.error_code ?? null,
      }));
    } else if (item.status === "requested" || item.status === "ready") {
      roleServiceUI.errors.delete(memberId);
      roleServiceUI.overlay.set(memberId, roleServiceMergeAction(base, {
        desired: "running", observed: "starting", generation: item.generation, action: "start",
        launch_id: item.launch_id, expected_instance_id: item.expected_instance_id,
      }));
      if (batch && item.status === "requested") {
        batch.launches[memberId] = { launch_id: item.launch_id ?? null, generation: item.generation ?? null };
        batch.settled[memberId] = "pending";
      }
    } else if (item.status === "skipped_running") {
      roleServiceUI.errors.delete(memberId);
      const observed = base && typeof base.observed === "string" ? base.observed : "starting";
      roleServiceUI.overlay.set(memberId, Object.assign({}, base || {}, { desired: "running", observed }));
    } else if (item.status === "skipped_ownership_held") {
      roleServiceUI.errors.delete(memberId);
      const observed = base && typeof base.observed === "string" ? base.observed : "unknown";
      roleServiceUI.overlay.set(memberId, Object.assign({}, base || {}, {
        desired: "running", observed, ownership_held: true, can_start: false, can_stop: true,
      }));
      if (batch) {
        batch.launches[memberId] = {
          launch_id: base?.current_launch?.launch_id ?? null,
          generation: item.generation ?? base?.generation ?? null,
        };
        batch.settled[memberId] = "failed_owned";
      }
    }
  }
}
async function startAllRoleServices(memberIds) {
  if (roleServiceUI.batch && roleServiceUI.batch.busy) return;
  if (!roleServiceHuman() || !roleServicePageActive() || typeof apiFetch !== "function") return;
  const projectId = activeProjectId, accountId = myId;
  if (!projectId || !accountId) return;
  // 省略/空 member_ids = 全部角色；给定子集只用于“重试失败项”，成功/跳过项不重复提交。
  const subset = Array.isArray(memberIds) ? memberIds.filter(id => typeof id === "string" && id) : [];
  roleServiceUI.batch = Object.assign({}, roleServiceUI.batch || {}, { busy: true, error: "" });
  renderWorkspaceList(); renderTaskDetailsPanel();
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/role-services/start-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subset.length ? { member_ids: subset } : {}),
    });
    if (projectId !== activeProjectId || accountId !== myId) return;
    if (!res.ok) {
      roleServiceUI.batch = Object.assign({}, roleServiceUI.batch || {}, {
        busy: false,
        error: await roleServiceErrorDetail(res, `全部启动失败（${res.status}），请稍后重试。`),
      });
    } else {
      const data = await res.json().catch(() => null);
      const results = Array.isArray(data?.results) ? data.results : [];
      const batch = {
        requested: Array.isArray(data?.requested) ? data.requested : subset,
        results,
        counts: roleServiceCountResults(results),
        requestFailures: roleServiceBatchRequestFailures(results),
        launches: {},
        settled: {},
        busy: false,
        error: "",
      };
      roleServiceUI.batch = batch;
      roleServiceApplyStartAll(results, batch);
    }
  } catch (err) {
    if (projectId === activeProjectId && accountId === myId) {
      roleServiceUI.batch = Object.assign({}, roleServiceUI.batch || {}, { busy: false, error: (err && err.message) || "全部启动请求失败，请重试。" });
    }
  } finally {
    if (projectId === activeProjectId && accountId === myId) { renderWorkspaceList(); renderTaskDetailsPanel(); }
  }
}
function roleServiceNeedsPolling() {
  if (!roleServicePageActive()) return false;
  if (roleServiceUI.actionRefresh) return true;
  const batch = roleServiceUI.batch;
  if (batch && Object.values(batch.settled || {}).some(value => value === "pending")) return true;
  for (const role of workspaceRoles()) {
    const view = roleServiceView(role);
    if (!view.provided || !view.service) continue;
    const observed = typeof view.service.observed === "string" ? view.service.observed : "";
    if (observed === "starting" || observed === "stopping" || observed === "running"
      || roleServiceLivenessUnknown(view.service) || roleServiceStopTimeout(view.service)) return true;
  }
  return false;
}
function maybeStartRoleServicePolling() {
  if (roleServiceUI.pollTimer !== null || roleServiceUI.pollBusy) return;
  if (typeof setTimeout !== "function") return;
  if (!roleServiceNeedsPolling()) return;
  const projectId = activeProjectId, accountId = myId;
  roleServiceUI.pollTimer = setTimeout(() => {
    roleServiceUI.pollTimer = null;
    pollRoleServices(projectId, accountId);
  }, roleServiceUI.pollDelayMs);
}
async function pollRoleServices(projectId, accountId) {
  if (!roleServicePageActive() || projectId !== activeProjectId || accountId !== myId) return;
  if (roleServiceUI.pollBusy || typeof apiFetch !== "function") return;
  const token = ++roleServiceUI.pollToken;
  const actionRefresh = roleServiceUI.actionRefresh || 0;
  roleServiceUI.pollBusy = true;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/role-services`);
    if (token !== roleServiceUI.pollToken || projectId !== activeProjectId || accountId !== myId) return;
    if (!res.ok) {
      roleServiceUI.pollError = await roleServiceErrorDetail(res, `服务状态刷新失败（${res.status}），将继续重试。`);
    } else {
      const list = await res.json().catch(() => null);
      if (token !== roleServiceUI.pollToken || projectId !== activeProjectId || accountId !== myId) return;
      roleServiceUI.pollError = "";
      if (actionRefresh === roleServiceUI.actionRefresh) roleServiceUI.actionRefresh = 0;
      const rows = Array.isArray(list) ? list : [];
      for (const item of rows) {
        const memberId = item && typeof item.member_id === "string" ? item.member_id : "";
        if (memberId) roleServiceUI.overlay.set(memberId, item);
      }
      // 批量收敛：后到的 failed/unknown 归入本批次失败，真实 ready 才计成功。
      roleServiceBatchConverge(rows);
    }
  } catch (err) {
    if (token === roleServiceUI.pollToken && projectId === activeProjectId && accountId === myId) {
      roleServiceUI.pollError = (err && err.message) || "服务状态刷新失败，将继续重试。";
    }
  } finally {
    if (token === roleServiceUI.pollToken) {
      roleServiceUI.pollBusy = false;
      // 重绘重新评估续期：运行中/失联继续检查，全部关闭或离页才停表。
      if (roleServicePageActive() && projectId === activeProjectId && accountId === myId) {
        renderWorkspaceList();
        renderTaskDetailsPanel();
      }
    }
  }
}
function renderWorkspaceRoleDetails() {
  // ROLE-DESC-F1 修正（#137/N4）：角色详情拆为名称区与参与任务区两个动态容器，
  // 静态说明编辑区（index.html 居中独立）位于两者之间；replaceChildren 只触碰这两个容器，
  // 绝不经过说明区——编辑区节点、内容与焦点在轮询重绘时天然保持。
  const namePanel = document.getElementById("role-details-name-panel");
  const tasksPanel = document.getElementById("role-details-tasks-panel");
  // ROLE-SETTINGS-1：项目设置与具体角色互斥——选中“项目设置”时角色详情整体隐藏，不残留空白面板。
  const visible = blackboardOpen && workspaceUI.mode === "roles" && !workspaceSettingsSelected();
  const role = workspaceRoles().find(item => item.member_id === workspaceUI.selectedRole) || null;
  // 分页上下文必须在任何提前 return 前同步：切账号/项目/角色/筛选或离开角色详情（不可见/选择失效）
  // 一律重置第一页；同上下文的普通轮询保持页码。不凭旧 selectedRole 残留串页。
  const roleTasksPageKey = visible && role
    ? JSON.stringify([myId, activeProjectId, role.member_id, workspaceUI.roleFilter])
    : null;
  if (roleTasksPageKey !== roleTasksPageUI.key) {
    roleTasksPageUI.key = roleTasksPageKey;
    roleTasksPageUI.page = 1;
  }
  // 运行诊断是独立静态面板：每次导航都同步完整上下文，离页也在 return 前清理；
  // 同角色服务轮询只更新证据，不重建筛选、日志或详情节点。
  if (typeof roleDiagnostics !== "undefined") {
    const serviceView = visible && role ? roleServiceView(role) : null;
    roleDiagnostics.sync({
      visible: Boolean(visible && role), role, serviceView,
      serviceStatus: serviceView ? roleServiceStatus(serviceView.service) : null,
      projectId: activeProjectId, accountId: myId, human: currentMemberIsHuman(),
    });
  }
  namePanel.classList.toggle("hidden", !visible);
  tasksPanel.classList.toggle("hidden", !visible);
  roleDeleteSync(visible ? role : null);
  if (!visible) return;
  namePanel.replaceChildren();
  tasksPanel.replaceChildren();
  if (!role) { namePanel.classList.add("hidden"); tasksPanel.classList.add("hidden"); return; } // 防御：失效选择由 workspaceSettingsSelected 回退到项目设置
  const nameHeading = workspaceEl("div", "role-name-heading");
  nameHeading.appendChild(workspaceEl("h2", "", workspaceMemberName(role.member_id)));
  if (currentMemberIsHuman() && role.archived !== true) {
    const edit = workspaceButton("", () => openRoleNameEditor(role), "icon-action subtle role-name-edit");
    edit.id = "role-name-edit"; edit.title = "修改角色名称"; edit.setAttribute("aria-label", "修改角色名称");
    edit.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-7"/><path d="m16 3 5 5M10 14l-1 4 4-1 9-9a2.1 2.1 0 0 0-5-5z"/></svg>';
    nameHeading.appendChild(edit);
  }
  namePanel.append(workspaceEl("p", "workspace-breadcrumb", `角色 / ${workspaceMemberName(role.member_id)}`), nameHeading, workspaceEl("p", "role-current", workspaceWorkSummary(role.member_id)));
  // ROLE-DESC-F1：原硬编码的短标签行（role-description）与解释行（role-explanation）从动态面板移除；
  // 说明统一由居中静态编辑区 #role-description-panel 呈现（自定义 ?? 默认），映射仅作默认值生成器。
  // ROLE-SETTINGS-1：移除角色详情的“交办任务”快捷入口；ROLE-DESC-F2 已移除顶部“新建任务”入口，
  // 任务创建只保留任务详情子任务入口与任务发起者派发（公共 POST /api/tasks / MCP / SDK）。
  // 固定主控标记已随 I-2 退役：角色详情不再显示“项目主控”徽标。
  namePanel.appendChild(workspaceEl("p", "role-member-id", `成员 ID：${role.member_id}`));
  // R1-3：受管 CLI 服务操作区（未归档且名册带 service 字段时显示）；由 workspaceRoleServicePanel
  // 只渲染启动/关闭与必要提示 —— 详情不再重复服务状态标签（状态入口在左侧角色列表）。
  if (role.archived !== true) {
    const servicePanel = workspaceRoleServicePanel(role);
    if (servicePanel) namePanel.appendChild(servicePanel);
  }
  const deletePanel = workspaceRoleDeletePanel(role);
  if (deletePanel) namePanel.appendChild(deletePanel);
  if (typeof roleRequestApp !== "undefined" && !role.deletion) {
    const actions = roleRequestApp?.rolePanel(role); if (actions) namePanel.appendChild(actions);
  }
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
  // 参与任务表：耗时替代原“承担工作”列；任务关系与筛选不变。
  for (const title of ["任务", "执行耗时", "任务状态", "操作"]) { const th = workspaceEl("th", "", title); th.scope = "col"; tr.appendChild(th); }
  head.appendChild(tr); table.appendChild(head);
  const body = workspaceEl("tbody");
  const tasks = workspaceRoleTasks(role.member_id).filter(task => workspaceFinished(task) === (workspaceUI.roleFilter === "finished"));
  // 固定 20 条/页：在现有完整可见集合与进行中/已结束筛选后的顺序上分页，不改任务接口。
  // 普通轮询保持页码；记录减少时夹回合法页。
  const totalPages = Math.max(1, Math.ceil(tasks.length / ROLE_TASKS_PAGE_SIZE));
  if (roleTasksPageUI.page > totalPages) roleTasksPageUI.page = totalPages;
  if (roleTasksPageUI.page < 1) roleTasksPageUI.page = 1;
  const pageStart = (roleTasksPageUI.page - 1) * ROLE_TASKS_PAGE_SIZE;
  const pageTasks = tasks.slice(pageStart, pageStart + ROLE_TASKS_PAGE_SIZE);
  for (const task of pageTasks) {
    const row = workspaceEl("tr");
    const name = workspaceEl("td"); name.appendChild(workspaceEl("span", "role-task-name", workspaceTitle(task)));
    const duration = workspaceEl("td"); duration.appendChild(workspaceTaskDurationEl(task));
    const state = taskStatusMeta(task); const status = workspaceEl("td"); status.appendChild(workspaceEl("span", `task-status-badge ${state.className}`, state.label));
    const action = workspaceEl("td"); const button = workspaceButton("查看任务", () => selectWorkspaceTask(task)); button.setAttribute("aria-label", `查看任务：${workspaceTitle(task)}`); action.appendChild(button);
    row.append(name, duration, status, action); body.appendChild(row);
  }
  table.appendChild(body); section.appendChild(table);
  if (!tasks.length) {
    section.appendChild(workspaceEl("p", "workspace-empty", "当前没有这类任务。"));
  } else {
    section.appendChild(workspaceRoleTasksPagination(tasks.length, pageStart, pageTasks.length, totalPages));
  }
  tasksPanel.appendChild(section);
}
// 参与任务分页条：上一页/下一页、页数/总数/本页范围；首尾禁用。翻页只重绘详情，不重新请求任务接口。
function workspaceRoleTasksPagination(total, pageStart, pageCount, totalPages) {
  const pager = workspaceEl("div", "role-task-pagination");
  const prev = workspaceButton("上一页", () => {
    if (roleTasksPageUI.page > 1) { roleTasksPageUI.page -= 1; renderWorkspaceRoleDetails(); }
  }, "workspace-text-button role-task-page-prev");
  prev.disabled = roleTasksPageUI.page <= 1;
  const info = workspaceEl("span", "role-task-page-info", `第 ${roleTasksPageUI.page} / ${totalPages} 页 · 共 ${total} 条 · 本页 ${pageStart + 1}–${pageStart + pageCount} 条`);
  const next = workspaceButton("下一页", () => {
    if (roleTasksPageUI.page < totalPages) { roleTasksPageUI.page += 1; renderWorkspaceRoleDetails(); }
  }, "workspace-text-button role-task-page-next");
  next.disabled = roleTasksPageUI.page >= totalPages;
  pager.append(prev, info, next);
  return pager;
}
// 主任务列表分页条：上一页/第x/y页（共n项）/下一页，沿用文字按钮与灰色信息样式，首尾禁用。
// 翻页只重绘左侧列表：不请求任务接口、不改已选任务、不动右侧对话与角色分页状态。
function workspaceTaskListPagination(total, totalPages) {
  const pager = workspaceEl("div", "task-list-pagination");
  const prev = workspaceButton("上一页", () => {
    if (taskListPageUI.page > 1) { taskListPageUI.page -= 1; renderWorkspaceList(); }
  }, "workspace-text-button task-list-page-prev");
  prev.disabled = taskListPageUI.page <= 1;
  const info = workspaceEl("span", "task-list-page-info", `第 ${taskListPageUI.page} / ${totalPages} 页 · 共 ${total} 项`);
  const next = workspaceButton("下一页", () => {
    if (taskListPageUI.page < totalPages) { taskListPageUI.page += 1; renderWorkspaceList(); }
  }, "workspace-text-button task-list-page-next");
  next.disabled = taskListPageUI.page >= totalPages;
  pager.append(prev, info, next);
  return pager;
}
function workspaceTaskNotice(task, tree) {
  if (task.workflow_status === "completed") return "成果已收取，本任务已完成。无需继续操作。";
  if (task.workflow_status === "failed") return "任务执行失败，请查看已有结果和失败原因。";
  if (task.workflow_status === "canceled") return "任务已取消，不会继续执行。";
  if (tree?.root.control_status === "awaiting_human" && tree.root.checkpoint_reason === "milestone") return "检查已完成，等待项目负责人进行人工验收。";
  if (tree?.root.control_status === "paused") return `任务已中止：${checkpointReasonLabel(tree.root.checkpoint_reason)}。`;
  if (tree?.root.control_status === "awaiting_human") return `任务等待人工处理：${checkpointReasonLabel(tree.root.checkpoint_reason)}。`;
  if (task.workflow_status === "submitted") return task.created_by === myId ? "成果已提交，等待你查看并收取。" : "成果已提交，等待请求者收取。";
  if (task.workflow_status === "clarification_requested") return task.created_by === myId ? "需要你补充任务要求，请在完整对话中答复。" : "等待请求者补充任务要求。";
  if (task.workflow_status === "needs_decision") return "需要项目负责人作出决定，任务尚未继续。";
  return task.workflow_status === "in_progress" ? "负责人正在推进任务，下面可查看分工进展。" : "任务已交办，等待负责人接手。";
}
// ── C2-B 项目调度模式（角色页“项目设置”，仅保存设置意向） ─────────────────
// 读取 GET /api/projects/{id} 的 controller_mode / controller_mode_version；加载中禁用控件
// 并提示读取中。写入只走专用 PATCH /api/projects/{id}/controller-mode，expected_version
// 原样回传上次读取的版本（不自己 +1、不走普通项目 PATCH）。保存的永远只是“意向”：
// 本版本没有任何主动调度生效入口（effective 恒为 null），界面把“已保存设置”与
// “实际执行”分两行如实显示，绝不把 null 伪装成启用状态。
// I-2（发起者模式）：模式只约束任务发起侧，与任何指定/成员状态无关——面板不再读取、
// 不依赖任何指定字段，保存“主动”统一显示固定意向提示，无任何指定前置要求。
// 状态绑定 项目/账号/请求序号，保存收尾用独立 saveToken 所有权（内部 409 重读会递增
// 请求序号，不用序号当所有权）；迟到成功/错误不回填其它上下文；用户未保存的选择存于
// selection，重绘不得吞掉。不新增后台轮询。
// 409 后标记“需重读”（reloadNeeded）：重读成功前暂禁保存以避免旧版本无效 CAS，“重试”
// 只做 GET 重读、不自动 PATCH，任一次读取成功即解除并按原权限/版本/dirty 恢复保存。
// C2-B-UX（2026-10-06 用户验收反馈）：离开“项目设置”（切任务/群聊、选具体角色、切项目/
// 账号等使面板隐藏）即放弃未保存选择，返回时 radio 与状态行按已确认 saved 显示；离页不发
// PATCH、不自动保存、不弹确认、不留持久化草稿。已保存状态行只显示模式名，不再显示版本号；
// controller_mode_version / expected_version / CAS / 响应核实全部保留，仅删展示。
const CONTROLLER_MODE_LABELS = { passive: "被动", active: "主动" };
const controllerModeUI = { projectId: null, memberId: null, supported: false, loaded: false, saving: false, saveToken: null, request: 0, saved: null, version: null, selection: null, error: "", notice: "", reloadNeeded: false };
function controllerModeEl(id) { return typeof document === "undefined" ? null : document.getElementById(id); }
function controllerModeContextValid() {
  return controllerModeUI.projectId !== null && controllerModeUI.projectId === activeProjectId && controllerModeUI.memberId === myId;
}
// 版本要作为 expected_version 原样回传；JS number 无法安全表示时禁止发送失真的版本号。
function controllerModeVersionSafe() { return Number.isSafeInteger(controllerModeUI.version) && controllerModeUI.version >= 0; }
function controllerModeKnown(mode) { return Object.prototype.hasOwnProperty.call(CONTROLLER_MODE_LABELS, mode); }
// 项目级面板可见性统一由 renderTaskDetailsPanel() 同步（app.js），与开发要求编辑区同一同步点。
function renderControllerModePanel() {
  const panel = controllerModeEl("controller-mode-panel");
  if (!panel) return;
  const visible = blackboardOpen && workspaceUI.mode === "roles" && workspaceSettingsSelected() && Boolean(activeProjectId) && Boolean(myId);
  panel.classList.toggle("hidden", !visible);
  if (!visible) {
    // C2-B-UX：离开“项目设置”（切任务/群聊、选具体角色、切项目/账号、关黑板等）即放弃
    // 未保存选择：不发 PATCH、不自动保存、不弹确认、不留持久化草稿；返回时 radio 与状态行
    // 按已确认 saved 显示。在途保存、request 序号与 saveToken 所有权不受此处影响，迟到成功/
    // 失败仍按原上下文校验如实入账；同页重绘/轮询（面板仍可见）不进入此分支，不吞用户选择。
    controllerModeUI.selection = null;
    return;
  }
  if (controllerModeUI.projectId !== activeProjectId || controllerModeUI.memberId !== myId) {
    // 上下文切换（含 A→B→A 往返与切账号）：递增请求序号作废旧读写，
    // 重置保存所有权（旧请求迟到不得清理新上下文的保存状态），新上下文重新读取。
    ++controllerModeUI.request;
    Object.assign(controllerModeUI, { projectId: activeProjectId, memberId: myId, supported: false, loaded: false, saving: false, saveToken: null, saved: null, version: null, selection: null, error: "", notice: "", reloadNeeded: false });
    return loadControllerMode();
  }
  syncControllerModePanel();
}
function syncControllerModePanel() {
  const panel = controllerModeEl("controller-mode-panel");
  if (!panel || panel.classList.contains("hidden")) return;
  const savedLine = controllerModeEl("controller-mode-saved");
  const effectiveLine = controllerModeEl("controller-mode-effective");
  const passiveRadio = controllerModeEl("controller-mode-passive");
  const activeRadio = controllerModeEl("controller-mode-active");
  const saveBtn = controllerModeEl("controller-mode-save-btn");
  const retryBtn = controllerModeEl("controller-mode-retry-btn");
  const status = controllerModeEl("controller-mode-status");
  const human = currentMemberIsHuman();
  const ready = controllerModeUI.loaded && controllerModeUI.supported;
  // 状态行一：已保存设置（仅模式名；版本号仍参与 expected_version/CAS 但不展示）。
  // 加载中/读取失败/旧服务/未知模式如实降级，不把缺失或异常值伪装成已保存被动。
  if (!controllerModeUI.loaded) {
    savedLine.textContent = controllerModeUI.error ? "已保存设置：读取失败" : "已保存设置：读取中…";
  } else if (!controllerModeUI.supported) {
    savedLine.textContent = "已保存设置：当前服务不支持调度模式设置";
  } else if (controllerModeKnown(controllerModeUI.saved)) {
    savedLine.textContent = `已保存设置：${CONTROLLER_MODE_LABELS[controllerModeUI.saved]}`;
  } else {
    savedLine.textContent = `已保存设置：无法识别的模式（服务返回：${String(controllerModeUI.saved)}），可选择下方模式重新保存`;
  }
  // 状态行二：实际执行。本版本没有主动调度的生效入口，支持读取时恒为这句话；
  // 不支持或读取失败时如实标注无法确认，绝不写成启用状态。
  effectiveLine.textContent = ready
    ? "实际执行：尚无生效的主动调度（本版本不支持自动生效）"
    : `实际执行：${controllerModeUI.loaded ? "当前服务不支持调度模式读取，无法确认" : "读取失败，无法确认"}`;
  // 显示选择 = 用户未保存选择 ?? 已保存值（未知模式不预选任何项）。重绘只按状态回写
  // checked，用户选择存放在 selection 中，轮询/重绘不会吞掉未保存选择。
  const shown = controllerModeUI.selection ?? (controllerModeKnown(controllerModeUI.saved) ? controllerModeUI.saved : null);
  const editable = human && ready;
  passiveRadio.disabled = !editable;
  activeRadio.disabled = !editable;
  passiveRadio.checked = shown === "passive";
  activeRadio.checked = shown === "active";
  const dirty = ready && shown !== null && shown !== controllerModeUI.saved;
  // 409 后需重读（reloadNeeded）期间暂禁保存：旧 expected_version 已被拒绝，再点保存只会重复 409；
  // 重读成功（applyControllerModeRead）后按原权限/版本/dirty 条件恢复。
  saveBtn.disabled = controllerModeUI.saving || controllerModeUI.reloadNeeded || !ready || !dirty || !controllerModeVersionSafe();
  saveBtn.classList.toggle("hidden", !human);
  // 重试入口：初读失败（!loaded）或 409 后需重读（reloadNeeded）两种错误状态可见；
  // 点击只做 GET 重读，不发 PATCH。400/422 等普通保存失败、版本不安全、agent 只读不进入此状态。
  retryBtn.classList.toggle("hidden", !(!controllerModeUI.saving && Boolean(controllerModeUI.error) && (!controllerModeUI.loaded || controllerModeUI.reloadNeeded)));
  let message = "", kind = "";
  if (!controllerModeUI.loaded && controllerModeUI.error) { message = controllerModeUI.error; kind = "error"; }
  else if (controllerModeUI.saving) message = "正在保存…";
  else if (controllerModeUI.error) { message = controllerModeUI.error; kind = "error"; }
  else if (controllerModeUI.notice) { message = controllerModeUI.notice; kind = "success"; }
  else if (!controllerModeUI.loaded) message = "正在读取调度模式…";
  else if (!controllerModeUI.supported) { message = "当前服务尚未支持调度模式设置，暂时只能查看。"; kind = "error"; }
  else if (!controllerModeVersionSafe()) { message = "调度模式版本超出页面可安全表示的范围；为避免写错版本，已暂停保存，请刷新或联系管理员。"; kind = "error"; }
  else if (!human) message = "当前账号是 Agent，只能查看；调度模式由项目负责人管理。";
  else if (dirty) message = "有未保存的选择，尚未保存。";
  status.textContent = message;
  status.className = `controller-mode-status${kind ? ` ${kind}` : ""}`;
}
// 用户切换选项只更新未保存选择，不自动提交；显式“保存”才发起写入。
function selectControllerMode(mode) {
  if (!controllerModeKnown(mode)) return;
  if (controllerModeUI.selection === mode) return;
  controllerModeUI.selection = mode;
  controllerModeUI.notice = "";
  syncControllerModePanel();
}
async function loadControllerMode() {
  const request = ++controllerModeUI.request;
  const projectId = controllerModeUI.projectId, memberId = controllerModeUI.memberId;
  controllerModeUI.error = "";
  syncControllerModePanel();
  const current = () => request === controllerModeUI.request
    && projectId === activeProjectId && projectId === controllerModeUI.projectId
    && memberId === myId && memberId === controllerModeUI.memberId;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) throw new Error(await readErrorDetail(res, `调度模式读取失败（${res.status}），请稍后重试。`));
    const data = await res.json();
    if (!current()) return;
    if (!data || data.project_id !== projectId || !("controller_mode" in data) || !("controller_mode_version" in data)) {
      // 旧服务缺模式字段：明确不支持并禁用保存，不把缺失当成被动。
      controllerModeUI.loaded = true;
      controllerModeUI.supported = false;
      controllerModeUI.saved = null; controllerModeUI.version = null;
      controllerModeUI.reloadNeeded = false;
      controllerModeUI.error = "当前服务尚未支持调度模式设置，暂时只能查看角色。";
    } else {
      applyControllerModeRead(projectId, data);
    }
  } catch (err) {
    if (!current()) return;
    controllerModeUI.loaded = false;
    controllerModeUI.error = err.message || "调度模式读取失败，请重试。";
  }
  if (current()) syncControllerModePanel();
}
function applyControllerModeRead(projectId, data) {
  controllerModeUI.supported = true;
  controllerModeUI.loaded = true;
  controllerModeUI.reloadNeeded = false; // 任何一次成功读取都拿到最新状态，解除“409 后需重读”
  controllerModeUI.saved = typeof data.controller_mode === "string" ? data.controller_mode : null;
  controllerModeUI.version = data.controller_mode_version;
  // 只回写模式两字段到项目缓存；其它项目字段一律不碰（已弃用的指定字段同样不读取、不回写）。
  const project = projects.find(item => item.project_id === projectId);
  if (project) {
    project.controller_mode = controllerModeUI.saved;
    project.controller_mode_version = data.controller_mode_version;
  }
}
// 409 后只重读最新模式/版本（自带请求序号），不自动替用户重写；返回是否确实刷新成功。
async function rereadControllerModeState(projectId, memberId) {
  const request = ++controllerModeUI.request;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) return false;
    const data = await res.json().catch(() => null);
    if (request !== controllerModeUI.request || projectId !== activeProjectId || projectId !== controllerModeUI.projectId
        || memberId !== myId || memberId !== controllerModeUI.memberId) return false;
    if (data && data.project_id === projectId && "controller_mode" in data && "controller_mode_version" in data) {
      applyControllerModeRead(projectId, data);
      return true;
    }
  } catch (_) { /* 重读失败保持原状态，错误文案如实提示刷新失败 */ }
  return false;
}
async function saveControllerMode() {
  const projectId = activeProjectId, memberId = myId;
  if (!projectId || controllerModeUI.saving || !controllerModeUI.loaded || !controllerModeUI.supported) return;
  // 409 后尚未重读成功前禁止再用旧版本写入（界面同时禁用保存按钮，这里兜底）。
  if (controllerModeUI.reloadNeeded) return;
  if (controllerModeUI.projectId !== projectId || controllerModeUI.memberId !== memberId) return;
  if (!currentMemberIsHuman()) return;
  const submitted = controllerModeUI.selection ?? (controllerModeKnown(controllerModeUI.saved) ? controllerModeUI.saved : null);
  if (!controllerModeKnown(submitted) || submitted === controllerModeUI.saved) return;
  if (!controllerModeVersionSafe()) {
    controllerModeUI.error = "调度模式版本无法安全表示，已取消本次写入，请刷新后重试。";
    syncControllerModePanel();
    return;
  }
  const expected = controllerModeUI.version;
  const saveToken = {};
  controllerModeUI.saving = true;
  controllerModeUI.saveToken = saveToken;
  controllerModeUI.error = ""; controllerModeUI.notice = "";
  const request = ++controllerModeUI.request;
  syncControllerModePanel();
  const contextAlive = () => projectId === activeProjectId && projectId === controllerModeUI.projectId
    && memberId === myId && memberId === controllerModeUI.memberId;
  const current = () => request === controllerModeUI.request && contextAlive();
  // 只有仍拥有当前保存状态的请求可在 finally 清理 saving 并同步视图；内部 409 重读会
  // 递增请求序号，故所有权用独立 token 判定，不用请求序号（同 C1b-S2 的 saveToken 纪律）。
  const ownsSave = () => controllerModeUI.saveToken === saveToken;
  try {
    // 写请求只走专用 controller-mode 入口；expected_version 原样回传上次读取的版本，不自己 +1。
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/controller-mode`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: submitted, expected_version: expected }),
    });
    if (!current()) return;
    if (res.status === 409) {
      const detail = await readErrorDetail(res, "调度模式设置已被他人修改。");
      if (!current()) return;
      // 409 只重新 GET 取最新模式/版本，不自动替用户重写；用户当前选择保留，便于确认后再保存。
      // 先置“需重读”：重读成功会被 applyControllerModeRead 清除；重读失败则保持该状态，
      // 保存暂禁（避免旧版本无效 CAS）、“重试”入口可见且只发 GET，直到某次读取成功解除。
      controllerModeUI.reloadNeeded = true;
      const refreshed = await rereadControllerModeState(projectId, memberId);
      if (!contextAlive()) return;
      controllerModeUI.error = refreshed
        ? `${detail} 设置已被他人修改，已刷新到最新状态，请确认后再保存。`
        : `${detail} 设置已被他人修改；自动刷新最新状态失败，已暂停保存；请点“重试”重新读取最新状态，确认后再保存。`;
    } else if (res.status === 404) {
      // 模式接口不存在（旧服务）：明确不支持并禁用保存，不假报成功。
      controllerModeUI.loaded = true;
      controllerModeUI.supported = false;
      controllerModeUI.error = "当前服务尚未支持调度模式设置（接口返回 404），本次未保存。";
    } else if (!res.ok) {
      // 400/422/其它失败：展示服务端 detail，保留用户当前选择便于重试。
      controllerModeUI.error = await readErrorDetail(res, `保存失败（${res.status}），请重试。`);
    } else {
      const data = await res.json().catch(() => null);
      if (!current()) return;
      // 必须核实同项目响应、必要字段存在、返回模式与提交值一致且版本可安全表示，才算保存成功。
      const versionOk = Boolean(data) && Number.isSafeInteger(data.controller_mode_version) && data.controller_mode_version >= 0;
      if (!data || data.project_id !== projectId || !("controller_mode" in data)
          || data.controller_mode !== submitted || !versionOk) {
        controllerModeUI.error = "服务未确认本次保存（响应未带回一致的调度模式），请刷新后重试。";
      } else {
        applyControllerModeRead(projectId, data);
        if (controllerModeUI.selection !== null && controllerModeUI.selection !== submitted) {
          // 保存期间用户又改了选择：保留新选择，不把它误标为已保存。
          controllerModeUI.notice = "先前选择已保存；当前选择尚未保存。";
        } else {
          controllerModeUI.selection = null;
          if (submitted === "active") {
            // I-2：保存“主动”只记录项目意向，无任何指定前置；固定提示，不查询任何指定状态。
            controllerModeUI.notice = "已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。";
          } else {
            controllerModeUI.notice = "已保存“被动”。派发任务后本轮结束，由你通知完成后再读取与收取。";
          }
        }
      }
    }
  } catch (err) {
    if (!current()) return;
    controllerModeUI.error = err.message || "保存失败，请检查网络后重试。";
  } finally {
    // 上下文活着但所有权已易手（A→B→A / 切账号往返期间有新保存接管）时：
    // 旧请求到达只结束自己，不清新请求的 saving、不同步视图、不再发写请求。
    if (contextAlive() && ownsSave()) {
      controllerModeUI.saveToken = null;
      controllerModeUI.saving = false;
      syncControllerModePanel();
    }
  }
}
// 角色页“刷新”复用既有刷新生命周期：只重读当前上下文的调度模式，不新增高频轮询。
function reloadControllerMode() {
  if (!(blackboardOpen && workspaceUI.mode === "roles" && activeProjectId && myId)) return;
  if (!controllerModeContextValid() || controllerModeUI.saving) return;
  loadControllerMode();
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
  const requirementsInput = document.getElementById("requirements-input");
  if (requirementsInput) {
    requirementsInput.addEventListener("input", recordRequirementsDraft);
    document.getElementById("requirements-save-btn").addEventListener("click", saveProjectRequirements);
    document.getElementById("requirements-discard-btn").addEventListener("click", discardProjectRequirements);
    document.getElementById("requirements-retry-btn").addEventListener("click", () => loadProjectRequirements());
  }
  const controllerModeSaveBtn = document.getElementById("controller-mode-save-btn");
  if (controllerModeSaveBtn) {
    // C2-B 调度模式：radio 只更新未保存选择，显式“保存”才提交；重试重读当前上下文。
    controllerModeSaveBtn.addEventListener("click", saveControllerMode);
    document.getElementById("controller-mode-retry-btn").addEventListener("click", () => { if (controllerModeContextValid()) loadControllerMode(); });
    for (const id of ["controller-mode-passive", "controller-mode-active"]) {
      document.getElementById(id).addEventListener("change", event => {
        if (event.target.checked) selectControllerMode(event.target.value);
      });
    }
  }
  const roleDescriptionInput = document.getElementById("role-description-input");
  const roleNameForm = document.getElementById("role-name-form");
  if (roleNameForm) {
    roleNameForm.addEventListener("submit", saveRoleName);
    document.getElementById("role-name-cancel").addEventListener("click", () => closeRoleNameEditor());
    document.getElementById("role-name-modal").addEventListener("keydown", event => {
      if (event.key === "Escape" && !roleNameUI.saving) { event.preventDefault(); closeRoleNameEditor(); }
      if (event.key === "Tab") {
        const nodes = ["role-name-input", "role-name-cancel", "role-name-save"].map(id => document.getElementById(id)).filter(node => !node.disabled);
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
  }
  if (roleDescriptionInput) {
    roleDescriptionInput.addEventListener("input", recordRoleDescriptionDraft);
    document.getElementById("role-description-save").addEventListener("click", saveRoleDescription);
    document.getElementById("role-description-discard").addEventListener("click", discardRoleDescription);
    document.getElementById("role-description-reset").addEventListener("click", resetRoleDescription);
  }
}
if (typeof module !== "undefined") module.exports = {workspaceRootId, workspaceFinished, workspaceTreeMatches, workspaceNeedsMe, workspaceChatRooms, chatMemberName, workspaceChatCandidates, workspaceMentionCandidates, workspaceResultOpen, resetWorkspaceResult, syncWorkspaceResultButton, showWorkspaceResult, workspaceTaskChatActive, workspaceParseTime, workspaceFormatDuration, workspaceTaskDuration, workspaceTaskDurationEl, workspaceRoleKey, workspaceRoleLabel, workspaceRoleDescription, workspaceRoleDefaultDescription, workspaceRoleDescriptionText, workspaceRoleSummary, normalizeRoleDescriptionValue, ROLE_DESCRIPTION_MAX_CHARS, workspaceRequirementsLength, normalizeRequirementsValue, REQUIREMENTS_MAX_CHARS, workspaceSettingsSelected, ROLE_BINDING_STATES, workspaceRoleBindingSummary};
