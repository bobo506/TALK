/* 面向日常使用者的任务 / 角色工作台；复用现有 API 和权限。 */
const workspaceUI = { mode: "tasks", filter: "all", query: "", selectedRole: null, roleSelection: "settings", roleFilter: "finished", result: null, resultRequest: 0, renderedTask: null };
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
function workspaceMemberName(id) { return chatMemberName(members.find(item => item.id === id) || {id}); }
function workspaceChatCandidates(items, roles, projectId, selfId) {
  const roleIds = new Set(roles.map(role => role.member_id));
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
function workspaceRoles() { return projectAgents.filter(agent => !members.find(member => member.id === agent.member_id)?.disabled_at); }
// ROLE-SETTINGS-1：角色列表固定首项“项目设置”是独立导航项，不是伪造 Agent——
// 不计入角色数量、不进入名册/主控候选，其选中状态也不会作为 member_id 传给任何任务或 API。
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
function workspaceWorkSummary(id) {
  const count = workspaceRoleTasks(id).filter(task => !workspaceFinished(task)).length;
  return count ? `正在参与 ${count} 项任务` : "当前没有进行中的任务";
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
function syncWorkspaceLayout() {
  document.querySelector(".workbench").classList.toggle("project-mode", blackboardOpen);
  document.querySelector(".workbench").classList.toggle("task-chat-mode", workspaceTaskChatActive());
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
// 说明是纯展示文本：不改变主控指定、business_role / decision_tier 或任务权限。
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
// 同项目轮询/导航不覆盖，切项目往返可按 key 恢复。不复制主控 CAS/saveToken。
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
    && Boolean(activeProjectId) && Boolean(myId);
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
    ? `参与协作的助手 · ${activeProjectId ? workspaceControllerSummary() : "项目主控：无项目"}`
    : "按你委派的工作整理";
  const search = document.getElementById("workspace-search");
  search.placeholder = rolesMode ? "搜索角色" : "搜索任务";
  search.setAttribute("aria-label", search.placeholder);
  blackboardColumns.replaceChildren(); blackboardSummary.replaceChildren();
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
    settingsRow.append(workspaceEl("strong", "", "项目设置"), workspaceEl("span", "", "开发要求 · 主控 · 调度模式"), workspaceEl("small", "", "项目级 · 不属于任何角色"));
    blackboardColumns.appendChild(settingsRow);
    // ROLE-DESC-F1：搜索范围 = 成员名 + 有效说明全文（自定义 ?? 默认）+ 原始 business_role。
    const matchedRoles = roles.filter(item => `${workspaceMemberName(item.member_id)} ${workspaceRoleDescriptionText(item)} ${item.business_role || ""}`.toLocaleLowerCase().includes(query));
    for (const role of matchedRoles) {
      const row = workspaceButton("", () => { workspaceUI.roleSelection = "role"; workspaceUI.selectedRole = role.member_id; renderWorkspaceList(); renderTaskDetailsPanel(); }, "role-row");
      row.classList.toggle("selected", !workspaceSettingsSelected() && role.member_id === workspaceUI.selectedRole);
      row.setAttribute("aria-pressed", String(!workspaceSettingsSelected() && role.member_id === workspaceUI.selectedRole));
      // 摘要列取有效说明的首个非空行：自定义后不再显示过时的硬编码短标签。
      row.append(workspaceEl("strong", "", workspaceMemberName(role.member_id)), workspaceEl("span", "", workspaceRoleSummary(role)), workspaceEl("small", "", workspaceWorkSummary(role.member_id)));
      // 被指定角色带“项目主控”标记；同名角色用 member_id 消歧（写请求始终使用 ID）。
      if (workspaceControllerBadge(role.member_id)) row.appendChild(workspaceEl("span", "role-controller-badge", "项目主控"));
      row.appendChild(workspaceEl("small", "role-row-id", role.member_id));
      blackboardColumns.appendChild(row);
    }
    // “项目设置”不计入角色数量：空名册/无匹配的提示只针对真实角色行。
    if (!matchedRoles.length) blackboardColumns.appendChild(workspaceEl("p", "workspace-empty", roles.length ? "没有匹配的角色" : "这个项目还没有配置角色。"));
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
  // ROLE-DESC-F1 修正（#137/N4）：角色详情拆为名称区与参与任务区两个动态容器，
  // 静态说明编辑区（index.html 居中独立）位于两者之间；replaceChildren 只触碰这两个容器，
  // 绝不经过说明区——编辑区节点、内容与焦点在轮询重绘时天然保持。
  const namePanel = document.getElementById("role-details-name-panel");
  const tasksPanel = document.getElementById("role-details-tasks-panel");
  // ROLE-SETTINGS-1：项目设置与具体角色互斥——选中“项目设置”时角色详情整体隐藏，不残留空白面板。
  const visible = blackboardOpen && workspaceUI.mode === "roles" && !workspaceSettingsSelected();
  namePanel.classList.toggle("hidden", !visible);
  tasksPanel.classList.toggle("hidden", !visible);
  if (!visible) return;
  namePanel.replaceChildren();
  tasksPanel.replaceChildren();
  const role = workspaceRoles().find(item => item.member_id === workspaceUI.selectedRole);
  if (!role) { namePanel.classList.add("hidden"); tasksPanel.classList.add("hidden"); return; } // 防御：失效选择由 workspaceSettingsSelected 回退到项目设置
  namePanel.append(workspaceEl("p", "workspace-breadcrumb", `角色 / ${workspaceMemberName(role.member_id)}`), workspaceEl("h2", "", workspaceMemberName(role.member_id)), workspaceEl("p", "role-current", workspaceWorkSummary(role.member_id)));
  // ROLE-DESC-F1：原硬编码的短标签行（role-description）与解释行（role-explanation）从动态面板移除；
  // 说明统一由居中静态编辑区 #role-description-panel 呈现（自定义 ?? 默认），映射仅作默认值生成器。
  // ROLE-SETTINGS-1：移除角色详情的“交办任务”快捷入口；ROLE-DESC-F2 已移除顶部“新建任务”入口，
  // 任务创建只保留任务详情子任务入口与主控派发（公共 POST /api/tasks / MCP / SDK）。
  // 主控管理集中在“项目设置”页；角色详情只保留当前指定标记，同名角色仍按 member_id 消歧。
  namePanel.appendChild(workspaceEl("p", "role-member-id", `成员 ID：${role.member_id}`));
  if (workspaceControllerBadge(role.member_id)) namePanel.appendChild(workspaceEl("p", "role-controller-badge", "项目主控（当前指定）"));
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
  for (const task of tasks) {
    const row = workspaceEl("tr");
    const name = workspaceEl("td"); name.appendChild(workspaceEl("span", "role-task-name", workspaceTitle(task)));
    const duration = workspaceEl("td"); duration.appendChild(workspaceTaskDurationEl(task));
    const state = taskStatusMeta(task); const status = workspaceEl("td"); status.appendChild(workspaceEl("span", `task-status-badge ${state.className}`, state.label));
    const action = workspaceEl("td"); const button = workspaceButton("查看任务", () => selectWorkspaceTask(task)); button.setAttribute("aria-label", `查看任务：${workspaceTitle(task)}`); action.appendChild(button);
    row.append(name, duration, status, action); body.appendChild(row);
  }
  table.appendChild(body); section.appendChild(table);
  if (!tasks.length) section.appendChild(workspaceEl("p", "workspace-empty", "当前没有这类任务。"));
  tasksPanel.appendChild(section);
}
// ── C1b-S2 项目主控指定（角色页，唯一长期指定） ─────────────────────────
// 数据源是服务端返回的 controller_member_id / controller_assignment_version /
// controller_assignment_status：不自动指定 lead/Codex，不从业务角色标签推导；
// assigned 只表示职责配置有效，不代表在线、已确认（ACK）或会话已生效。
// 指定长期保存，无期限/续租，离线不自动解除；失效成员（移出名册/禁用/不存在）仍在
// 项目级面板保留名称或 ID、无效原因与 human 解除入口。写操作只走专用
// PATCH /api/projects/{id}/controller-assignment，携带上次读取的版本，不用普通项目 PATCH。
const CONTROLLER_STATUSES = {
  unassigned: { label: "未指定" },
  assigned: { label: "已指定" },
  not_in_roster: { label: "已指定 · 当前不可用", reason: "该成员当前不在项目名册中" },
  member_disabled: { label: "已指定 · 当前不可用", reason: "该成员已被禁用" },
  member_missing: { label: "已指定 · 当前不可用", reason: "该成员已不存在" },
  not_agent: { label: "已指定 · 当前不可用", reason: "该成员不是 Agent" },
};
// 未知/缺失状态明确降级为“无法识别”，不假定有效，也不虚构成功。
function controllerStatusMeta(status) {
  return CONTROLLER_STATUSES[status] || { label: "指定状态无法识别", reason: `服务返回了无法识别的状态：${String(status)}` };
}
// 状态绑定 项目/账号/请求序号；只存内存，不写 localStorage，不新增轮询或独立 timer。
// saving 的清理权按请求所有权（saveToken）判定：只有发起当前这次保存的请求可以清理
// saving、回焦或同步相关视图；A→B→A 往返或切账号期间迟到的旧请求即使上下文重新“活着”，
// 也不拥有新请求的保存状态，不得提前清零。token 独立于请求序号 —— 409/400 的内部重读会
// 递增序号，若用序号当所有权，当前请求在重读后反而永远无法清理自己的保存状态。
const controllerUI = { projectId: null, memberId: null, supported: false, loaded: false, saving: false, saveToken: null, request: 0, assignedId: null, version: null, status: null, error: "", notice: "" };
function controllerEl(id) { return typeof document === "undefined" ? null : document.getElementById(id); }
function controllerContextValid() {
  return controllerUI.projectId !== null && controllerUI.projectId === activeProjectId && controllerUI.memberId === myId;
}
// 指定展示始终带 member_id 消歧（同项目可有多个同名 Kimi/DeepSeek 角色）。
function controllerAssignedLabel(memberId) { return `${workspaceMemberName(memberId)}（${memberId}）`; }
// 版本要作为 expected_version 原样回传；JS number 无法安全表示时禁止发送失真的版本号。
function controllerVersionSafe() { return Number.isSafeInteger(controllerUI.version) && controllerUI.version >= 0; }
function workspaceControllerBadge(memberId) {
  return controllerContextValid() && controllerUI.loaded && controllerUI.supported && controllerUI.assignedId === memberId;
}
function workspaceControllerSummary() {
  if (!controllerContextValid()) return "项目主控：读取中…";
  if (!controllerUI.loaded) return controllerUI.error ? "项目主控：读取失败" : "项目主控：读取中…";
  if (!controllerUI.supported) return "项目主控：当前服务不支持";
  return controllerUI.assignedId ? `项目主控：${controllerAssignedLabel(controllerUI.assignedId)}` : "项目主控：未指定";
}
// 候选只取项目名册内、已注册、未禁用的 agent（不要求在线）；前端过滤只影响体验，服务端仍独立校验。
function controllerCandidate(memberId) {
  if (!workspaceRoles().some(role => role.member_id === memberId)) return false;
  const member = members.find(item => item.id === memberId);
  return Boolean(member) && member.kind === "agent" && !member.disabled_at;
}
// ROLE-SETTINGS-1：主控管理集中在“项目设置”页（候选选择器 + 设为/解除）；
// 角色详情只保留 workspaceControllerBadge 标记，不再提供逐角色管理入口。
// 项目级面板可见性统一由 renderTaskDetailsPanel() 同步（app.js），与开发要求编辑区同一同步点；
// 任务/群聊导航都会经过该同步点，不会残留管理区。
function renderControllerPanel() {
  const panel = controllerEl("controller-panel");
  if (!panel) return;
  const visible = blackboardOpen && workspaceUI.mode === "roles" && workspaceSettingsSelected() && Boolean(activeProjectId) && Boolean(myId);
  panel.classList.toggle("hidden", !visible);
  if (!visible) { controllerFocusMemory = null; return; }
  if (controllerUI.projectId !== activeProjectId || controllerUI.memberId !== myId) {
    // 上下文切换（含往返）：递增请求序号作废旧读写，新上下文重新读取。
    ++controllerUI.request;
    controllerFocusMemory = null;
    Object.assign(controllerUI, { projectId: activeProjectId, memberId: myId, supported: false, loaded: false, saving: false, saveToken: null, assignedId: null, version: null, status: null, error: "", notice: "" });
    return loadControllerAssignment();
  }
  syncControllerPanel();
}
// 候选选择器：候选集合不变时不重建 option，避免保存中/轮询同步打断用户正在进行的下拉选择与焦点。
function syncControllerCandidates(select, candidates) {
  const signature = candidates.join("\n");
  if (select.dataset.signature === signature) return;
  const previous = select.value;
  select.dataset.signature = signature;
  select.replaceChildren();
  if (!candidates.length) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "暂无可指定的名册内 Agent";
    select.appendChild(empty);
    return;
  }
  for (const id of candidates) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = controllerAssignedLabel(id); // 同名候选用 member_id 消歧
    select.appendChild(option);
  }
  // 保留用户已选候选（仍在名册内时）；否则显式落到第一个候选，与浏览器默认选中行为一致。
  select.value = previous && candidates.includes(previous) ? previous : candidates[0];
}
function syncControllerPanel() {
  const panel = controllerEl("controller-panel");
  if (!panel || panel.classList.contains("hidden")) return;
  const current = controllerEl("controller-current");
  const detail = controllerEl("controller-detail");
  const clearBtn = controllerEl("controller-clear-btn");
  const retryBtn = controllerEl("controller-retry-btn");
  const status = controllerEl("controller-status");
  const assignRow = controllerEl("controller-assign-row");
  const candidateSelect = controllerEl("controller-candidate-select");
  const assignBtn = controllerEl("controller-assign-btn");
  const human = currentMemberIsHuman();
  current.textContent = workspaceControllerSummary();
  let detailText = "";
  if (controllerUI.loaded && controllerUI.supported) {
    if (!controllerVersionSafe()) detailText = "服务返回的主控版本超出页面可安全表示的范围；为避免写错版本，已暂停指定与解除操作，请刷新或联系管理员。";
    else if (controllerUI.assignedId) {
      const meta = controllerStatusMeta(controllerUI.status);
      detailText = meta.reason
        ? `${meta.reason}；指定仍长期保存，不会自动解除或转移，可解除后另选。`
        : "已指定仅表示职责配置有效，不代表在线、已确认或会话已生效；指定长期保存，直到人工解除。";
      // 已有非 null 指定时不能再直接指定他人：先解除理由在此明确，候选选择器保持可见但禁用。
      if (human) detailText += " 如需更换主控，请先解除当前指定，再另选。";
    } else {
      detailText = "还没有指定主控；可在下方选择一名名册内的 Agent 设为项目主控。指定长期保存，直到人工解除。";
    }
  }
  detail.textContent = detailText;
  const showClear = human && controllerUI.loaded && controllerUI.supported && Boolean(controllerUI.assignedId);
  clearBtn.classList.toggle("hidden", !showClear);
  clearBtn.disabled = controllerUI.saving || (showClear && !controllerVersionSafe());
  // human 加载完成后保留指定入口；已有指定时置灰，agent 只读 / 未加载完成时整行隐藏。
  // 行内控件同步 hidden：焦点解算按节点自身判定可聚焦性，不依赖祖先状态。
  const showAssign = human && controllerUI.loaded && controllerUI.supported;
  assignRow.classList.toggle("hidden", !showAssign);
  candidateSelect.classList.toggle("hidden", !showAssign);
  assignBtn.classList.toggle("hidden", !showAssign);
  if (showAssign) {
    const candidates = workspaceRoles().map(role => role.member_id).filter(controllerCandidate);
    syncControllerCandidates(candidateSelect, candidates);
    candidateSelect.disabled = Boolean(controllerUI.assignedId) || controllerUI.saving || !controllerVersionSafe() || !candidates.length;
    assignBtn.disabled = candidateSelect.disabled || !candidateSelect.value;
  }
  retryBtn.classList.toggle("hidden", !(!controllerUI.loaded && controllerUI.error && !controllerUI.saving));
  let message = "", kind = "";
  if (!controllerUI.loaded && controllerUI.error) { message = controllerUI.error; kind = "error"; }
  else if (controllerUI.saving) message = "正在保存…";
  else if (controllerUI.error) { message = controllerUI.error; kind = "error"; }
  else if (controllerUI.notice) { message = controllerUI.notice; kind = "success"; }
  else if (!controllerUI.loaded) message = "正在读取项目主控指定…";
  else if (controllerUI.supported && !controllerVersionSafe()) { message = "主控版本无法安全表示，写入已暂停。"; kind = "error"; }
  else if (controllerUI.supported && !human) message = "当前账号是 Agent，只能查看；主控指定由项目负责人管理。";
  status.textContent = message;
  status.className = `controller-status${kind ? ` ${kind}` : ""}`;
}
async function loadControllerAssignment() {
  const request = ++controllerUI.request;
  const projectId = controllerUI.projectId, memberId = controllerUI.memberId;
  controllerUI.error = "";
  syncControllerPanel();
  const current = () => request === controllerUI.request
    && projectId === activeProjectId && projectId === controllerUI.projectId
    && memberId === myId && memberId === controllerUI.memberId;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) throw new Error(await readErrorDetail(res, `项目主控读取失败（${res.status}），请稍后重试。`));
    const data = await res.json();
    if (!current()) return;
    if (!data || data.project_id !== projectId || !("controller_member_id" in data)
        || !("controller_assignment_version" in data) || !("controller_assignment_status" in data)) {
      // 旧后端没有主控字段：明确提示不支持并禁用写入，不把缺失当成“未指定”。
      controllerUI.loaded = true;
      controllerUI.supported = false;
      controllerUI.assignedId = null; controllerUI.version = null; controllerUI.status = null;
      controllerUI.error = "当前服务尚未支持项目主控指定，暂时只能查看角色。";
    } else {
      applyControllerRead(projectId, data);
    }
  } catch (err) {
    if (!current()) return;
    controllerUI.loaded = false;
    controllerUI.error = err.message || "项目主控读取失败，请重试。";
  }
  if (current()) syncControllerViews();
}
function applyControllerRead(projectId, data) {
  controllerUI.supported = true;
  controllerUI.loaded = true;
  controllerUI.assignedId = typeof data.controller_member_id === "string" && data.controller_member_id ? data.controller_member_id : null;
  controllerUI.version = data.controller_assignment_version;
  controllerUI.status = typeof data.controller_assignment_status === "string" ? data.controller_assignment_status : "";
  // 只回写主控三个字段到项目缓存；其它项目字段一律不碰，避免影响开发要求草稿等状态。
  const project = projects.find(item => item.project_id === projectId);
  if (project) {
    project.controller_member_id = controllerUI.assignedId;
    project.controller_assignment_version = data.controller_assignment_version;
    project.controller_assignment_status = data.controller_assignment_status;
  }
}
// 焦点去向按动作语义推导：失败时原按钮仍在则回焦原按钮；指定成功后“设为项目主控”置灰，
// 落到同一上下文对应的“解除主控”（下一步可操作元素）；解除成功后解除入口隐藏，
// 落到可见的候选选择器（下一步是另选），不可聚焦时落到稳定可聚焦的面板状态行
// （tabindex=-1，仅程序化聚焦，不进 Tab 序）。
// 保存中间态（同动作按钮被置灰但未消失）不动焦点，靠焦点动作记忆在完成时恢复；
// 用户已主动移焦到其它可见控件、或切到具体角色/其它项目/账号/导航后不抢焦；
// 永不聚焦 hidden/disabled 节点。
let controllerFocusMemory = null;
function controllerFocusable(node) {
  return Boolean(node && typeof node.focus === "function" && !node.disabled
    && !(node.classList && node.classList.contains("hidden")));
}
function controllerFocusTarget(action) {
  const same = document.querySelector(`[data-controller-action="${action}"]`);
  if (controllerFocusable(same)) return same;
  // 同动作按钮仍在但只是被置灰（保存中间态）：不动焦点，等完成后的最终状态再恢复。
  if (controllerUI.saving && same && !(same.classList && same.classList.contains("hidden"))) return null;
  // 保存结束后同动作节点已禁用或隐藏（动作已变）：指定成功的下一步是解除主控；解除成功的下一步是另选候选。
  if (action === "assign") {
    const clear = document.querySelector('[data-controller-action="clear"]');
    if (controllerFocusable(clear)) return clear;
  }
  if (action === "clear") {
    const select = controllerEl("controller-candidate-select");
    if (controllerFocusable(select)) return select;
  }
  const status = controllerEl("controller-current");
  return controllerFocusable(status) ? status : null;
}
// 读取/保存完成后刷新列表徽标与角色详情；尽量恢复原焦点，避免键盘操作被重绘打断。
function syncControllerViews() {
  const active = typeof document === "undefined" ? null : document.activeElement;
  const action = active && active.dataset ? active.dataset.controllerAction || null : null;
  if (action) {
    // 记录焦点动作意图：真实浏览器中控件隐藏/重绘会把焦点带回 body，靠记忆在完成时恢复。
    // 记忆绑定保存发起时的项目设置上下文：保存期间用户切到具体角色或其它视图属于新的
    // 交互意图，完成后取消回焦，不把焦点拉回项目设置的主控区。
    controllerFocusMemory = { action, projectId: activeProjectId, memberId: myId };
  } else if (active && active !== document.body) {
    controllerFocusMemory = null; // 焦点在其它可见控件上：用户已主动移焦，不再为主控回焦
  }
  syncControllerPanel();
  // C2-B：主控指定变化后只刷新调度模式面板的主控可用性提示（读项目缓存事实），不写模式。
  // typeof 防御：C1b-S2 定向测试单独抽取本代码块运行时，调度模式函数不在上下文中。
  if (typeof syncControllerModePanel === "function") syncControllerModePanel();
  // 只在角色页（黑板打开的管理上下文仍在）重绘列表与角色详情；离开角色页或黑板关闭后，
  // 迟到的读取/保存响应只维护 controllerUI 与项目缓存状态，由返回角色页时的正常导航渲染
  // 呈现服务器最终状态，避免主控请求重绘任务/群聊页面造成焦点与滚动位置丢失。
  const inRoles = blackboardOpen && workspaceUI.mode === "roles";
  if (inRoles) {
    renderWorkspaceList();
    renderWorkspaceRoleDetails();
  }
  // 主控控件只存在于“项目设置”页；用户已切到具体角色时不回焦主控区。
  const inSettings = inRoles && workspaceSettingsSelected();
  if (inSettings && typeof document !== "undefined") {
    const memory = controllerFocusMemory;
    const plan = action || (memory && memory.projectId === activeProjectId && memory.memberId === myId
      ? memory.action : null);
    if (plan) {
      const next = controllerFocusTarget(plan);
      if (next) { next.focus(); controllerFocusMemory = null; }
    }
  }
}
// 角色页“刷新”复用既有刷新生命周期：只重读当前上下文的主控状态，不新增高频轮询。
function reloadControllerAssignment() {
  if (!(blackboardOpen && workspaceUI.mode === "roles" && activeProjectId && myId)) return;
  if (!controllerContextValid() || controllerUI.saving) return;
  loadControllerAssignment();
}
async function saveControllerAssignment(targetId) {
  const projectId = activeProjectId, memberId = myId;
  if (!projectId || controllerUI.saving || !controllerUI.loaded || !controllerUI.supported) return;
  if (controllerUI.projectId !== projectId || controllerUI.memberId !== memberId) return;
  if (!currentMemberIsHuman()) return;
  if (targetId !== null && typeof targetId !== "string") return;
  // 只能从空指定新角色；已有指定时须先解除再另选，不直接覆盖（服务端对覆盖返回 409）。
  if (targetId !== null && controllerUI.assignedId && controllerUI.assignedId !== targetId) return;
  if (targetId === controllerUI.assignedId) return;
  if (!controllerVersionSafe()) {
    controllerUI.error = "主控版本无法安全表示，已取消本次写入，请刷新后重试。";
    syncControllerViews();
    return;
  }
  if (targetId !== null && !controllerCandidate(targetId)) {
    controllerUI.error = "该角色当前不在可指定范围内（须为项目名册内已注册、未禁用的 Agent）。";
    syncControllerViews();
    return;
  }
  const expected = controllerUI.version;
  const saveToken = {};
  controllerUI.saving = true;
  controllerUI.saveToken = saveToken;
  controllerUI.error = ""; controllerUI.notice = "";
  const request = ++controllerUI.request;
  syncControllerViews();
  const contextAlive = () => projectId === activeProjectId && projectId === controllerUI.projectId
    && memberId === myId && memberId === controllerUI.memberId;
  const current = () => request === controllerUI.request && contextAlive();
  // 只有仍拥有当前保存状态的请求可在 finally 清理 saving 并同步视图；
  // 不用请求序号判断所有权（内部重读会递增序号，见 controllerUI 声明处注释）。
  const ownsSave = () => controllerUI.saveToken === saveToken;
  try {
    // 写请求始终使用 member_id（解除为显式 null）；expected_version 原样回传上次读取的版本，不自己 +1。
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}/controller-assignment`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ member_id: targetId, expected_version: expected }),
    });
    if (!current()) return;
    if (res.status === 409 || res.status === 400) {
      const detail = await readErrorDetail(res, res.status === 409 ? "主控指定状态已变化。" : "候选角色已变化。");
      if (!current()) return;
      // 冲突/候选变化：只重新读取最新状态，不自动替用户重试写。
      await rereadControllerState(projectId, memberId);
      if (!contextAlive()) return;
      controllerUI.error = res.status === 409
        ? `${detail} 已为你刷新到最新状态，请确认后再操作。`
        : `${detail} 请刷新角色列表后重试。`;
    } else if (res.status === 404) {
      // 旧服务没有该接口：明确不支持，不假报保存。
      controllerUI.loaded = true;
      controllerUI.supported = false;
      controllerUI.error = "当前服务尚未支持项目主控指定（接口返回 404），本次未保存。";
    } else if (!res.ok) {
      controllerUI.error = await readErrorDetail(res, `保存失败（${res.status}），请重试。`);
    } else {
      const data = await res.json().catch(() => null);
      if (!current()) return;
      // 必须核实同项目响应带回三个字段且 member 与本次请求一致，才算保存成功。
      if (!data || data.project_id !== projectId || !("controller_member_id" in data)
          || !("controller_assignment_version" in data) || !("controller_assignment_status" in data)
          || data.controller_member_id !== targetId) {
        controllerUI.error = "服务未确认本次保存（响应未带回一致的主控指定），请刷新后重试。";
      } else {
        applyControllerRead(projectId, data);
        if (targetId === null) {
          controllerUI.notice = "已解除主控指定。";
        } else if (controllerUI.status === "assigned") {
          controllerUI.notice = "已保存。已指定仅表示职责配置有效，不代表在线或已确认。";
        } else {
          // S1 已披露竞态：提交期间候选被禁用/移出名册时可能 200 但配置无效，如实提示真实状态。
          const meta = controllerStatusMeta(controllerUI.status);
          controllerUI.notice = `已保存，但当前不可用：${meta.reason || meta.label}。指定仍长期保存，可解除后另选。`;
        }
      }
    }
  } catch (err) {
    if (!current()) return;
    controllerUI.error = err.message || "保存失败，请检查网络后重试。";
  } finally {
    // 上下文活着但所有权已易手（A→B→A / 切账号往返期间有新保存接管）时：
    // 旧请求到达只结束自己，不清新请求的 saving、不回焦、不同步视图、不再发写请求。
    if (contextAlive() && ownsSave()) {
      controllerUI.saveToken = null;
      controllerUI.saving = false;
      syncControllerViews();
    }
  }
}
// 409/400 后只重读最新主控状态（自带请求序号），不自动重试写。
async function rereadControllerState(projectId, memberId) {
  const request = ++controllerUI.request;
  try {
    const res = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!res.ok) return;
    const data = await res.json().catch(() => null);
    if (request !== controllerUI.request || projectId !== activeProjectId || projectId !== controllerUI.projectId
        || memberId !== myId || memberId !== controllerUI.memberId) return;
    if (data && data.project_id === projectId && "controller_member_id" in data
        && "controller_assignment_version" in data && "controller_assignment_status" in data) {
      applyControllerRead(projectId, data);
    }
  } catch (_) { /* 重读失败保持原状态，错误文案已提示 */ }
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
// ── C2-B 项目调度模式（角色页“项目设置”，仅保存设置意向） ─────────────────
// 读取 GET /api/projects/{id} 的 controller_mode / controller_mode_version；加载中禁用控件
// 并提示读取中。写入只走专用 PATCH /api/projects/{id}/controller-mode，expected_version
// 原样回传上次读取的版本（不自己 +1、不走普通项目 PATCH）。保存的永远只是“意向”：
// 本版本没有任何主动调度生效入口（effective 恒为 null），界面把“已保存设置”与
// “实际执行”分两行如实显示，绝不把 null 伪装成启用状态。无主控或主控失效/未知仍可
// 保存意向，保存“主动”时如实显示原因且不会因此产生任何主动调度。
// 与主控指定面板相互独立：各自 CAS 字段，保存模式不写指定；主控变更经项目缓存只刷新
// 本面板提示，不写模式。状态绑定 项目/账号/请求序号，保存收尾用独立 saveToken 所有权
// （同 C1b-S2 纪律，409 内部重读递增序号不会夺走当前保存的清理权）；迟到成功/错误不
// 回填其它上下文；用户未保存的选择存于 selection，重绘不得吞掉。不新增后台轮询。
// 409 后标记“需重读”（reloadNeeded）：重读成功前暂禁保存以避免旧版本无效 CAS，“重试”
// 只做 GET 重读、不自动 PATCH，任一次读取成功即解除并按原权限/版本/dirty 恢复保存。
// C2-B-UX（2026-10-06 用户验收反馈）：离开“项目设置”（切任务/群聊、选具体角色、切项目/
// 账号等使面板隐藏）即放弃未保存选择，返回时 radio 与状态行按已确认 saved 显示；离页不发
// PATCH、不自动保存、不弹确认、不留持久化草稿。已保存状态行只显示模式名，不再显示版本号；
// controller_mode_version / expected_version / CAS / 响应核实全部保留，仅删展示。
const CONTROLLER_MODE_LABELS = { passive: "被动", active: "主动" };
const controllerModeUI = { projectId: null, memberId: null, supported: false, loaded: false, saving: false, saveToken: null, request: 0, saved: null, version: null, controllerId: undefined, controllerStatus: undefined, selection: null, error: "", notice: "", reloadNeeded: false };
function controllerModeEl(id) { return typeof document === "undefined" ? null : document.getElementById(id); }
function controllerModeContextValid() {
  return controllerModeUI.projectId !== null && controllerModeUI.projectId === activeProjectId && controllerModeUI.memberId === myId;
}
// 版本要作为 expected_version 原样回传；JS number 无法安全表示时禁止发送失真的版本号。
function controllerModeVersionSafe() { return Number.isSafeInteger(controllerModeUI.version) && controllerModeUI.version >= 0; }
function controllerModeKnown(mode) { return Object.prototype.hasOwnProperty.call(CONTROLLER_MODE_LABELS, mode); }
// 主控可用性只读事实来源：项目缓存（主控面板保存后已回写最新值）优先，
// 其次本面板自己的项目读取快照；只用于提示，绝不写模式字段。
function controllerModeControllerState() {
  const project = projects.find(item => item.project_id === controllerModeUI.projectId);
  const id = project && "controller_member_id" in project ? project.controller_member_id : controllerModeUI.controllerId;
  const status = project && "controller_assignment_status" in project ? project.controller_assignment_status : controllerModeUI.controllerStatus;
  return { id: id || null, status: typeof status === "string" ? status : "" };
}
// 无主控 / 主控失效 / 状态未知时的原因短句；assigned 返回空串。
function controllerModeUnavailableReason() {
  const { id, status } = controllerModeControllerState();
  if (status === "assigned") return "";
  if (!id || status === "unassigned") return "尚未指定项目主控";
  const meta = controllerStatusMeta(status);
  return meta.reason || meta.label;
}
// 仅当已保存意向为“主动”且主控不可用时常驻提示；被动或无问题不额外打扰。
function controllerModeAvailabilityNote() {
  if (controllerModeUI.saved !== "active") return "";
  const reason = controllerModeUnavailableReason();
  return reason ? `当前主控指定不可用：${reason}；保存的“主动”意向不会因此产生任何主动调度。` : "";
}
// 项目级面板可见性统一由 renderTaskDetailsPanel() 同步（app.js），与开发要求/主控面板同一同步点。
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
    Object.assign(controllerModeUI, { projectId: activeProjectId, memberId: myId, supported: false, loaded: false, saving: false, saveToken: null, saved: null, version: null, controllerId: undefined, controllerStatus: undefined, selection: null, error: "", notice: "", reloadNeeded: false });
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
  else if (controllerModeAvailabilityNote()) { message = controllerModeAvailabilityNote(); kind = "attention"; }
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
      controllerModeUI.controllerId = undefined; controllerModeUI.controllerStatus = undefined;
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
  controllerModeUI.controllerId = "controller_member_id" in data ? (data.controller_member_id || null) : undefined;
  controllerModeUI.controllerStatus = "controller_assignment_status" in data ? data.controller_assignment_status : undefined;
  // 只回写模式两字段到项目缓存；主控字段由主控面板维护，其它项目字段一律不碰。
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
            const reason = controllerModeUnavailableReason();
            controllerModeUI.notice = reason
              ? `已保存“主动”，但当前主控指定不可用：${reason}，不会因此产生任何主动调度。`
              : "已保存“主动”。这只是设置意向：不会唤醒会话或自动运行，已结束的桌面对话仍需人工唤回。";
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
  const controllerClearBtn = document.getElementById("controller-clear-btn");
  if (controllerClearBtn) {
    controllerClearBtn.addEventListener("click", () => saveControllerAssignment(null));
    document.getElementById("controller-retry-btn").addEventListener("click", () => { if (controllerContextValid()) loadControllerAssignment(); });
  }
  const controllerAssignBtn = document.getElementById("controller-assign-btn");
  if (controllerAssignBtn) {
    // 指定写请求始终使用候选选择器的 member_id；“项目设置”导航项本身不是成员，永不出现在候选中。
    controllerAssignBtn.addEventListener("click", () => {
      const select = document.getElementById("controller-candidate-select");
      if (select && select.value) saveControllerAssignment(select.value);
    });
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
  if (roleDescriptionInput) {
    roleDescriptionInput.addEventListener("input", recordRoleDescriptionDraft);
    document.getElementById("role-description-save").addEventListener("click", saveRoleDescription);
    document.getElementById("role-description-discard").addEventListener("click", discardRoleDescription);
    document.getElementById("role-description-reset").addEventListener("click", resetRoleDescription);
  }
}
if (typeof module !== "undefined") module.exports = {workspaceRootId, workspaceFinished, workspaceTreeMatches, workspaceNeedsMe, workspaceChatRooms, chatMemberName, workspaceChatCandidates, workspaceMentionCandidates, workspaceResultOpen, resetWorkspaceResult, syncWorkspaceResultButton, showWorkspaceResult, workspaceTaskChatActive, workspaceParseTime, workspaceFormatDuration, workspaceTaskDuration, workspaceTaskDurationEl, workspaceRoleKey, workspaceRoleLabel, workspaceRoleDescription, workspaceRoleDefaultDescription, workspaceRoleDescriptionText, workspaceRoleSummary, normalizeRoleDescriptionValue, ROLE_DESCRIPTION_MAX_CHARS, workspaceRequirementsLength, normalizeRequirementsValue, REQUIREMENTS_MAX_CHARS, controllerStatusMeta, workspaceSettingsSelected};
