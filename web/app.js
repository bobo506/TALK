// TALK — Minimal Web UI
"use strict";

const API = "";
const mentionPattern = /@([^\s]+)/g;
const ALL_MENTION_ID = "所有人";
const HISTORY_RENDER_CHUNK = 80;
const HISTORY_PAGE_SIZE = 100;
const markdownRenderer = configureMarkdownRenderer();
const NOTIFICATION_SOUND_COOLDOWN_MS = 1200;
const DEFAULT_REVOKE_WINDOW_SEC = 120;
const DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const JUMP_HIGHLIGHT_MS = 1000;
const SETUP_KEY_BYTES = 32;

let appConfig = {
  revoke_window_sec: DEFAULT_REVOKE_WINDOW_SEC,
  max_upload_bytes: DEFAULT_MAX_UPLOAD_BYTES,
  ws_ping_interval: 20,
  ws_ping_timeout: 45,
  file_retention_days: 30,
};

let apiKey = "";
let myId = "";
let members = [];
let lastId = 0;
let ws = null;
let eventSource = null;
let pollTimer = null;
let taskPollTimer = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let pendingFile = null;
let dragDepth = 0;
let sending = false;
let historyLoading = false;
let statusTimer = null;
let loggingOut = false;
let renderedMessageIds = new Set();
let messageRecords = new Map();
let revokeButtonTimers = new Map();
let activeReplyTo = null;
let jumpHighlightTimer = null;
let onlineMemberIds = new Set();
let hasPresenceSnapshot = false;
let notificationAudioContext = null;
let lastNotificationAt = 0;
let oldestLoadedId = null;
let hasMoreHistory = false;
let appliedHistoryQuery = "";
let setupKeyVisible = false;
let setupKeyCopyTimer = null;
let groups = [];
let activeGroupId = null;
let groupCreateOpen = false;
let groupCreateSaving = false;
let groupMembersOpen = false;
let groupMemberSaving = false;
let groupMetaSaving = false;
let selectedMemberKindFilters = new Set();
let groupMetaEditing = false;
let agentProfileEditing = null;
let agentProfileSaving = false;
let projects = [];
let activeProjectId = null;
let projectAgents = [];
let projectTasks = [];
let blackboardOpen = false;
let selectedTaskId = null;
let selectedTaskTree = null;
let taskCreateOpen = false;
let taskCreateSaving = false;
let taskActionSaving = false;
let taskCreateParentRoot = null;

// ── DOM refs ─────────────────────────────────────────────────────────
const loginOverlay = document.getElementById("login-overlay");
const authLoading = document.getElementById("auth-loading");
const loginPanel = document.getElementById("login-panel");
const loginKey = document.getElementById("login-key");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");
const setupPanel = document.getElementById("setup-panel");
const setupId = document.getElementById("setup-id");
const setupName = document.getElementById("setup-name");
const setupKey = document.getElementById("setup-key");
const setupKeyGenerateBtn = document.getElementById("setup-key-generate-btn");
const setupKeyToggleBtn = document.getElementById("setup-key-toggle-btn");
const setupKeyToggleLabel = document.getElementById("setup-key-toggle-label");
const setupKeyCopyBtn = document.getElementById("setup-key-copy-btn");
const setupKeyEyeOpen = document.getElementById("setup-key-eye-open");
const setupKeyEyeClosed = document.getElementById("setup-key-eye-closed");
const setupBtn = document.getElementById("setup-btn");
const setupError = document.getElementById("setup-error");
const connectionStatus = document.getElementById("connection-status");
const userBadge = document.getElementById("user-badge");
const logoutBtn = document.getElementById("logout-btn");
const roomStrip = document.getElementById("room-strip");
const projectStrip = document.getElementById("project-strip");
const projectSelect = document.getElementById("project-select");
const refreshProjectBtn = document.getElementById("refresh-project-btn");
const projectBlackboardBtn = document.getElementById("project-blackboard-btn");
const projectTaskCount = document.getElementById("project-task-count");
const delegateTaskBtn = document.getElementById("delegate-task-btn");
const projectEmptyNote = document.getElementById("project-empty-note");
const blackboardView = document.getElementById("blackboard-view");
const blackboardTitle = document.getElementById("blackboard-title");
const blackboardDescription = document.getElementById("blackboard-description");
const blackboardRefreshBtn = document.getElementById("blackboard-refresh-btn");
const blackboardDelegateBtn = document.getElementById("blackboard-delegate-btn");
const blackboardSummary = document.getElementById("blackboard-summary");
const blackboardColumns = document.getElementById("blackboard-columns");
const blackboardEmpty = document.getElementById("blackboard-empty");
const hallHeader = document.getElementById("hall-header");
const roomTitle = document.getElementById("room-title");
const roomDescription = document.getElementById("room-description");
const globalRoomBtn = document.getElementById("global-room-btn");
const groupRoomList = document.getElementById("group-room-list");
const hallFilterInput = document.getElementById("hall-filter-input");
const refreshGroupsBtn = document.getElementById("refresh-groups-btn");
const toggleGroupCreateBtn = document.getElementById("toggle-group-create-btn");
const toggleGroupMembersBtn = document.getElementById("toggle-group-members-btn");
const groupCreateOverlay = document.getElementById("group-create-overlay");
const groupCreatePanel = document.getElementById("group-create-panel");
const closeGroupCreateBtn = document.getElementById("close-group-create-btn");
const groupCreateName = document.getElementById("group-create-name");
const groupCreateId = document.getElementById("group-create-id");
const groupCreateDescription = document.getElementById("group-create-description");
const groupCreateMemberSelect = document.getElementById("group-create-member-select");
const groupCreateMemberChips = document.getElementById("group-create-member-chips");
let selectedCreateMemberIds = new Set();
const groupCreateError = document.getElementById("group-create-error");
const cancelGroupCreateBtn = document.getElementById("cancel-group-create-btn");
const submitGroupCreateBtn = document.getElementById("submit-group-create-btn");
const groupMembersPanel = document.getElementById("group-members-panel");
const groupMembersSubtitle = document.getElementById("group-members-subtitle");
const closeGroupMembersBtn = document.getElementById("close-group-members-btn");
const groupMetaForm = document.getElementById("group-meta-form");
const groupMetaName = document.getElementById("group-meta-name");
const groupMetaDescription = document.getElementById("group-meta-description");
const groupMetaSaveBtn = document.getElementById("group-meta-save-btn");
const groupMembersList = document.getElementById("group-members-list");
const groupMemberAddForm = document.getElementById("group-member-add-form");
const groupMemberAddSelect = document.getElementById("group-member-add-select");
const groupMemberAddRole = document.getElementById("group-member-add-role");
const groupMemberAddBtn = document.getElementById("group-member-add-btn");
const groupMembersError = document.getElementById("group-members-error");
const deleteGroupBtn = document.getElementById("delete-group-btn");
const allMembersList = document.getElementById("all-members-list");
const agentProfileOverlay = document.getElementById("agent-profile-overlay");
const agentProfilePanel = document.getElementById("agent-profile-panel");
const closeAgentProfileBtn = document.getElementById("close-agent-profile-btn");
const cancelAgentProfileBtn = document.getElementById("cancel-agent-profile-btn");
const saveAgentProfileBtn = document.getElementById("save-agent-profile-btn");
const agentProfileTitle = document.getElementById("agent-profile-title");
const agentProfileMember = document.getElementById("agent-profile-member");
const agentProfileBusinessRole = document.getElementById("agent-profile-business-role");
const agentProfileIdentity = document.getElementById("agent-profile-identity");
const agentProfileSoul = document.getElementById("agent-profile-soul");
const agentProfileUser = document.getElementById("agent-profile-user");
const agentProfileError = document.getElementById("agent-profile-error");
const presenceStrip = document.getElementById("presence-strip");
const presenceSummary = document.getElementById("presence-summary");
const presenceMembers = document.getElementById("presence-members");
const historyToolbar = document.getElementById("history-toolbar");
const historySearchInput = document.getElementById("history-search-input");
const historySearchBtn = document.getElementById("history-search-btn");
const historyClearBtn = document.getElementById("history-clear-btn");
const loadOlderBtn = document.getElementById("load-older-btn");
const historyStatus = document.getElementById("history-status");
const messagesEl = document.getElementById("messages");
const composerFooter = document.getElementById("composer-footer");
const composer = document.getElementById("composer");
const dropHint = document.getElementById("drop-hint");
const pendingFileEl = document.getElementById("pending-file");
const pendingFileName = document.getElementById("pending-file-name");
const pendingFileMeta = document.getElementById("pending-file-meta");
const replyBar = document.getElementById("reply-bar");
const replyAuthor = document.getElementById("reply-author");
const replyPreview = document.getElementById("reply-preview");
const clearReplyBtn = document.getElementById("clear-reply-btn");
const composerStatus = document.getElementById("composer-status");
const clearFileBtn = document.getElementById("clear-file-btn");
const fileInput = document.getElementById("file-input");
const attachBtn = document.getElementById("attach-btn");
const msgInput = document.getElementById("msg-input");
const sendBtn = document.getElementById("send-btn");
const mentionDropdown = document.getElementById("mention-dropdown");
const taskDetailsPanel = document.getElementById("task-details-panel");
const taskDetailsTitle = document.getElementById("task-details-title");
const taskDetailsStatus = document.getElementById("task-details-status");
const taskDetailsMeta = document.getElementById("task-details-meta");
const taskDetailsContent = document.getElementById("task-details-content");
const taskDetailsError = document.getElementById("task-details-error");
const taskDetailsActions = document.getElementById("task-details-actions");
const taskDetailsRefreshBtn = document.getElementById("task-details-refresh-btn");
const taskCreateOverlay = document.getElementById("task-create-overlay");
const taskCreatePanel = document.getElementById("task-create-panel");
const taskCreateProject = document.getElementById("task-create-project");
const taskCreateAgent = document.getElementById("task-create-agent");
const taskCreateTitle = document.getElementById("task-create-title");
const taskCreateContent = document.getElementById("task-create-content");
const taskCreateGovernance = document.getElementById("task-create-governance");
const taskCreateDelegation = document.getElementById("task-create-delegation");
const taskCreateSliceBudget = document.getElementById("task-create-slice-budget");
const taskCreateMilestone = document.getElementById("task-create-milestone");
const taskCreateQuality = document.getElementById("task-create-quality");
const taskCreateKind = document.getElementById("task-create-kind");
const taskCreateReviewPolicyField = document.getElementById("task-create-review-policy-field");
const taskCreateReviewPolicy = document.getElementById("task-create-review-policy");
const taskCreateRelatedField = document.getElementById("task-create-related-field");
const taskCreateRelated = document.getElementById("task-create-related");
const taskCreateTriggerField = document.getElementById("task-create-trigger-field");
const taskCreateTrigger = document.getElementById("task-create-trigger");
const taskCreateError = document.getElementById("task-create-error");
const closeTaskCreateBtn = document.getElementById("close-task-create-btn");
const cancelTaskCreateBtn = document.getElementById("cancel-task-create-btn");
const submitTaskCreateBtn = document.getElementById("submit-task-create-btn");
const LOCAL_API_KEY_STORAGE = "talk_api_key";
const SESSION_API_KEY_STORAGE = "talk_session_api_key";
const ACTIVE_GROUP_STORAGE = "talk_active_group_id";
const ACTIVE_PROJECT_STORAGE = "talk_active_project_id";

const connectionStates = {
  connecting: {
    label: "连接中",
    classes: "border-yellow-500/40 bg-yellow-500/10 text-yellow-200",
  },
  connected: {
    label: "实时已连接",
    classes: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  },
  sse: {
    label: "SSE 已连接",
    classes: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  },
  sseFallback: {
    label: "SSE 兜底中",
    classes: "border-blue-500/40 bg-blue-500/10 text-blue-100",
  },
  sseReconnecting: {
    label: "SSE 重连中 · 轮询兜底",
    classes: "border-yellow-500/40 bg-yellow-500/10 text-yellow-200",
  },
  reconnecting: {
    label: "重连中 · 轮询兜底",
    classes: "border-yellow-500/40 bg-yellow-500/10 text-yellow-200",
  },
  polling: {
    label: "仅轮询中",
    classes: "border-gray-500/40 bg-gray-700 text-gray-200",
  },
};

const composerStatusClasses = {
  info: "border-blue-500/40 bg-blue-500/10 text-blue-100",
  error: "border-red-500/40 bg-red-500/10 text-red-100",
};

const defaultComposerPlaceholder = "输入消息… 开头用 @ 指定接收者，不写则广播";
const fileComposerPlaceholder = "输入文件附言… 开头用 @ 指定接收者，不写则广播";
const emptyTimelineText = "这里是消息时间线。暂无消息，发送第一条消息开始对话。";
const emptySearchText = "没有找到匹配的消息。换个关键词再试试。";

// ── Login ────────────────────────────────────────────────────────────
loginBtn.addEventListener("click", () => doLoginV2());
loginKey.addEventListener("keydown", (e) => {
  if (e.key === "Enter") doLoginV2();
});
setupBtn.addEventListener("click", createInitialAdmin);
setupKeyGenerateBtn.addEventListener("click", generateSetupKey);
setupKeyToggleBtn.addEventListener("click", toggleSetupKeyVisibility);
setupKeyCopyBtn.addEventListener("click", copySetupKeyToClipboard);
setupId.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createInitialAdmin();
});
setupName.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createInitialAdmin();
});
setupKey.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createInitialAdmin();
});
setupKey.addEventListener("input", updateSetupKeyControls);

function clearLoginError() {
  loginError.textContent = "";
  loginError.classList.add("hidden");
}

function showSetupError(msg) {
  setupError.textContent = msg;
  setupError.classList.toggle("hidden", !msg);
}

function setSetupKeyVisibility(visible) {
  setupKeyVisible = visible && Boolean(setupKey.value.trim());
  setupKey.type = setupKeyVisible ? "text" : "password";
  setupKeyToggleLabel.textContent = setupKeyVisible ? "隐藏" : "显示";
  setupKeyEyeOpen.classList.toggle("hidden", !setupKeyVisible);
  setupKeyEyeClosed.classList.toggle("hidden", setupKeyVisible);
}

function updateSetupKeyControls() {
  const hasKey = Boolean(setupKey.value.trim());
  setupKeyToggleBtn.disabled = !hasKey;
  setupKeyCopyBtn.disabled = !hasKey;
  setupKeyToggleBtn.classList.toggle("opacity-50", !hasKey);
  setupKeyToggleBtn.classList.toggle("cursor-not-allowed", !hasKey);
  setupKeyCopyBtn.classList.toggle("opacity-50", !hasKey);
  setupKeyCopyBtn.classList.toggle("cursor-not-allowed", !hasKey);

  if (!hasKey) {
    clearSetupKeyCopyFeedback();
  }
  setSetupKeyVisibility(setupKeyVisible && hasKey);
}

function clearSetupKeyCopyFeedback() {
  if (setupKeyCopyTimer) {
    clearTimeout(setupKeyCopyTimer);
    setupKeyCopyTimer = null;
  }
  setupKeyCopyBtn.textContent = "复制";
}

function generateRandomSetupKey() {
  if (!window.crypto || typeof window.crypto.getRandomValues !== "function") {
    throw new Error("当前浏览器不支持安全随机数，请手动填写登录密钥。");
  }

  const bytes = new Uint8Array(SETUP_KEY_BYTES);
  window.crypto.getRandomValues(bytes);

  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function generateSetupKey() {
  try {
    setupKey.value = generateRandomSetupKey();
    showSetupError("");
    setSetupKeyVisibility(false);
    updateSetupKeyControls();
  } catch (err) {
    showSetupError(err.message);
  }
}

function toggleSetupKeyVisibility() {
  if (!setupKey.value.trim()) return;
  setSetupKeyVisibility(!setupKeyVisible);
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (_err) {
      // Some embedded browsers expose Clipboard API but deny write permission.
      // Fall through to the legacy selection-based copy path below.
    }
  }

  const temp = document.createElement("textarea");
  temp.value = text;
  temp.setAttribute("readonly", "readonly");
  temp.style.position = "fixed";
  temp.style.opacity = "0";
  document.body.appendChild(temp);
  temp.select();

  const copied = document.execCommand("copy");
  document.body.removeChild(temp);

  if (!copied) {
    throw new Error("复制失败，请手动复制登录密钥。");
  }
}

async function copySetupKeyToClipboard() {
  const key = setupKey.value.trim();
  if (!key) return;

  try {
    await copyTextToClipboard(key);
    clearSetupKeyCopyFeedback();
    setupKeyCopyBtn.textContent = "已复制";
    setupKeyCopyTimer = setTimeout(() => {
      setupKeyCopyTimer = null;
      setupKeyCopyBtn.textContent = "复制";
    }, 1600);
  } catch (err) {
    setupKey.focus();
    setupKey.select();
    showSetupError("浏览器拒绝了自动复制。登录密钥已帮你选中，请按 Ctrl+C 手动复制。");
  }
}

function setAuthMode(mode) {
  authLoading.classList.toggle("hidden", mode !== "loading");
  loginPanel.classList.toggle("hidden", mode !== "login");
  setupPanel.classList.toggle("hidden", mode !== "setup");
  if (mode !== "setup") {
    clearSetupKeyCopyFeedback();
  }
}

function getStoredApiKey() {
  return sessionStorage.getItem(SESSION_API_KEY_STORAGE) || localStorage.getItem(LOCAL_API_KEY_STORAGE) || "";
}

function clearStoredApiKeys() {
  localStorage.removeItem(LOCAL_API_KEY_STORAGE);
  sessionStorage.removeItem(SESSION_API_KEY_STORAGE);
}

function persistApiKey(key, { persistent = true } = {}) {
  if (persistent) {
    localStorage.setItem(LOCAL_API_KEY_STORAGE, key);
    sessionStorage.removeItem(SESSION_API_KEY_STORAGE);
    return;
  }

  sessionStorage.setItem(SESSION_API_KEY_STORAGE, key);
  localStorage.removeItem(LOCAL_API_KEY_STORAGE);
}

async function doLoginV2(providedKey = null, { persistent = true } = {}) {
  clearLoginError();
  const nextKey = (providedKey ?? loginKey.value).trim();
  if (!nextKey) return false;
  apiKey = nextKey;

  try {
    const meRes = await apiFetch("/api/members/me");
    if (!meRes.ok) {
      apiKey = "";
      clearStoredApiKeys();
      showLoginError("登录密钥无效或认证失败。");
      return false;
    }
    const me = await meRes.json();
    myId = me.id;

    const membersRes = await apiFetch("/api/members");
    if (!membersRes.ok) {
      apiKey = "";
      showLoginError("成员列表加载失败。");
      return false;
    }
    members = await membersRes.json();
    await loadRuntimeConfig();
    await loadProjects();
    await loadGroups();

    loginOverlay.classList.add("hidden");
    userBadge.textContent = myId;
    persistApiKey(apiKey, { persistent });
    hasPresenceSnapshot = false;
    onlineMemberIds = new Set();
    renderPresenceStrip();
    startChat();
    return true;
  } catch (err) {
    apiKey = "";
    showLoginError("连接失败：" + err.message);
    return false;
  }
}

async function createInitialAdmin() {
  showSetupError("");
  const payload = {
    id: setupId.value.trim(),
    display_name: setupName.value.trim(),
    api_key: setupKey.value.trim(),
  };
  if (!payload.id || !payload.display_name || !payload.api_key) {
    showSetupError("请填写管理员 ID、昵称和登录密钥。");
    return;
  }
  if (!payload.id.startsWith("human:")) {
    showSetupError("管理员 ID 必须以 human: 开头，例如 human:home。");
    return;
  }

  setupBtn.disabled = true;
  try {
    const res = await fetch(API + "/api/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `创建管理员失败：${res.status}`));
    }

    loginKey.value = payload.api_key;
    const loggedIn = await doLoginV2(payload.api_key, { persistent: false });
    if (!loggedIn) {
      showSetupError("管理员已创建，但自动登录失败。");
    }
  } catch (err) {
    showSetupError(err.message);
  } finally {
    setupBtn.disabled = false;
  }
}

async function bootstrapAuthFlow() {
  setAuthMode("loading");
  try {
    const res = await fetch(API + "/api/setup/status");
    if (!res.ok) {
      throw new Error(`setup status ${res.status}`);
    }

    const payload = await res.json();
    if (payload.needs_setup) {
      clearStoredApiKeys();
      setAuthMode("setup");
      return;
    }

    setAuthMode("login");
    const saved = getStoredApiKey();
    if (!saved) return;

    loginKey.value = saved;
    await doLoginV2(saved, {
      persistent: localStorage.getItem(LOCAL_API_KEY_STORAGE) === saved,
    });
  } catch (err) {
    setAuthMode("login");
    showLoginError("初始化状态加载失败：" + err.message);
  }
}

async function doLogin() {
  loginError.textContent = "";
  loginError.classList.add("hidden");
  apiKey = loginKey.value.trim();
  if (!apiKey) return;

  try {
    const meRes = await apiFetch("/api/members/me");
    if (!meRes.ok) {
      showLoginError("API Key 无效或认证失败");
      return;
    }
    const me = await meRes.json();
    myId = me.id;

    const membersRes = await apiFetch("/api/members");
    if (!membersRes.ok) {
      showLoginError("成员列表加载失败");
      return;
    }
    members = await membersRes.json();
    await loadRuntimeConfig();
    await loadProjects();
    await loadGroups();

    loginOverlay.classList.add("hidden");
    userBadge.textContent = myId;
    localStorage.setItem("talk_api_key", apiKey);
    hasPresenceSnapshot = false;
    onlineMemberIds = new Set();
    renderPresenceStrip();
    startChat();
  } catch (err) {
    showLoginError("连接失败：" + err.message);
  }
}

(function autoLogin() {
  return;
})();

updateComposerPlaceholder();
resizeComposerInput();
updateSetupKeyControls();
bootstrapAuthFlow();

function showLoginError(msg) {
  loginError.textContent = msg;
  loginError.classList.remove("hidden");
}

logoutBtn.addEventListener("click", () => {
  loggingOut = true;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (taskPollTimer) {
    clearInterval(taskPollTimer);
    taskPollTimer = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
  closeEventStream();
  clearStoredApiKeys();
  location.reload();
});

loadOlderBtn.addEventListener("click", loadOlderMessages);
historySearchBtn.addEventListener("click", applyHistorySearch);
historyClearBtn.addEventListener("click", clearHistorySearch);
globalRoomBtn.addEventListener("click", () => setActiveGroup(null));
projectSelect.addEventListener("change", () => setActiveProject(projectSelect.value));
projectBlackboardBtn.addEventListener("click", () => setBlackboardOpen(true));
refreshProjectBtn.addEventListener("click", refreshProjectWorkspace);
blackboardRefreshBtn.addEventListener("click", refreshProjectWorkspace);
delegateTaskBtn.addEventListener("click", () => setTaskCreateOpen(true));
blackboardDelegateBtn.addEventListener("click", () => setTaskCreateOpen(true));
taskDetailsRefreshBtn.addEventListener("click", () => loadProjectTasks());
closeTaskCreateBtn.addEventListener("click", () => setTaskCreateOpen(false));
cancelTaskCreateBtn.addEventListener("click", () => setTaskCreateOpen(false));
taskCreatePanel.addEventListener("submit", createTaskFromPanel);
taskCreateKind.addEventListener("change", renderTaskCreateMode);
taskCreateDelegation.addEventListener("change", renderTaskCreateMode);
taskCreateMilestone.addEventListener("change", () => {
  if (taskCreateMilestone.checked) taskCreateDelegation.checked = true;
  renderTaskCreateMode();
});
taskCreateOverlay.addEventListener("mousedown", (event) => {
  if (event.target === taskCreateOverlay && !taskCreateSaving) setTaskCreateOpen(false);
});
refreshGroupsBtn.addEventListener("click", refreshGroups);
toggleGroupCreateBtn.addEventListener("click", () => setGroupCreateOpen(!groupCreateOpen));
toggleGroupMembersBtn.addEventListener("click", () => {
  setGroupMembersOpen(true);
  if (groupMemberAddSelect && !groupMemberAddSelect.disabled) {
    groupMemberAddSelect.focus();
  }
});
cancelGroupCreateBtn.addEventListener("click", () => setGroupCreateOpen(false));
closeGroupCreateBtn.addEventListener("click", () => setGroupCreateOpen(false));
groupCreateOverlay.addEventListener("mousedown", (event) => {
  if (event.target === groupCreateOverlay) setGroupCreateOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && groupCreateOpen) setGroupCreateOpen(false);
  if (event.key === "Escape" && agentProfileEditing) closeAgentProfileEditor();
  if (event.key === "Escape" && taskCreateOpen && !taskCreateSaving) setTaskCreateOpen(false);
});
groupCreateMemberSelect.addEventListener("change", () => {
  const memberId = groupCreateMemberSelect.value;
  if (!memberId) return;
  selectedCreateMemberIds.add(memberId);
  renderGroupCreateMembers();
});
groupCreatePanel.addEventListener("submit", createGroupFromPanel);
agentProfilePanel.addEventListener("submit", saveAgentProfileEditor);
closeAgentProfileBtn.addEventListener("click", closeAgentProfileEditor);
cancelAgentProfileBtn.addEventListener("click", closeAgentProfileEditor);
agentProfileOverlay.addEventListener("mousedown", (event) => {
  if (event.target === agentProfileOverlay && !agentProfileSaving) closeAgentProfileEditor();
});
closeGroupMembersBtn.addEventListener("click", () => setGroupMembersOpen(true));
groupMetaForm.addEventListener("submit", updateGroupMetadataFromPanel);
groupMemberAddForm.addEventListener("submit", addGroupMemberFromPanel);
deleteGroupBtn.addEventListener("click", deleteActiveGroup);
hallFilterInput.addEventListener("input", renderRoomStrip);
roomTitle.addEventListener("click", () => {
  if (!activeGroupId || !canManageGroups()) return;
  groupMetaEditing = true;
  setGroupMembersOpen(true);
  renderGroupMembersPanel();
  groupMetaName.focus();
  groupMetaName.select();
});
historySearchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    applyHistorySearch();
  }
});

// ── Project Blackboard / Task Hall ─────────────────────────────────
function activeProjectStorageKey() {
  return myId ? `${ACTIVE_PROJECT_STORAGE}:${myId}` : ACTIVE_PROJECT_STORAGE;
}

function getActiveProject() {
  return projects.find((project) => project.project_id === activeProjectId) || null;
}

async function loadProjects() {
  try {
    const res = await apiFetch("/api/projects");
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `项目列表加载失败: ${res.status}`));
    }
    projects = await res.json();
    const stored = localStorage.getItem(activeProjectStorageKey());
    activeProjectId = projects.some((project) => project.project_id === stored)
      ? stored
      : projects[0]?.project_id || null;
    if (activeProjectId) {
      localStorage.setItem(activeProjectStorageKey(), activeProjectId);
      blackboardOpen = true;
      await loadProjectAgents();
      await loadProjectTasks({ silent: true });
    } else {
      projectAgents = [];
      projectTasks = [];
      selectedTaskId = null;
      selectedTaskTree = null;
      blackboardOpen = false;
    }
    renderProjectStrip();
    renderWorkspaceMode();
  } catch (err) {
    projects = [];
    activeProjectId = null;
    projectAgents = [];
    projectTasks = [];
    selectedTaskTree = null;
    blackboardOpen = false;
    console.error(err);
  }
}

async function loadProjectAgents() {
  if (!activeProjectId) {
    projectAgents = [];
    return;
  }
  const res = await apiFetch(`/api/projects/${encodeURIComponent(activeProjectId)}/agents`);
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `项目 Agent 加载失败: ${res.status}`));
  }
  projectAgents = await res.json();
}

async function loadProjectTasks({ silent = false } = {}) {
  if (!activeProjectId) {
    projectTasks = [];
    selectedTaskId = null;
    selectedTaskTree = null;
    renderProjectStrip();
    renderBlackboard();
    renderGroupMembersPanel();
    return;
  }
  try {
    const params = new URLSearchParams({ project_id: activeProjectId });
    const res = await apiFetch(`/api/tasks?${params.toString()}`);
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `项目任务加载失败: ${res.status}`));
    }
    projectTasks = await res.json();
    projectTasks.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
    if (!projectTasks.some((task) => Number(task.id) === Number(selectedTaskId))) {
      selectedTaskId = projectTasks[0]?.id ?? null;
      selectedTaskTree = null;
    }
    const hasUnknownHall = projectTasks.some(
      (task) => task.hall_group_id && !groups.some((group) => group.id === task.hall_group_id)
    );
    if (hasUnknownHall) {
      await loadGroups();
    }
    await loadSelectedTaskTree({ silent: true });
    renderProjectStrip();
    renderRoomStrip();
    renderBlackboard();
    renderGroupMembersPanel();
  } catch (err) {
    if (!silent) {
      showComposerStatus(err.message, "error", { source: "tasks", timeoutMs: 3500 });
    }
    console.error(err);
  }
}

async function loadSelectedTaskTree({ silent = false } = {}) {
  const task = projectTasks.find((item) => Number(item.id) === Number(selectedTaskId));
  if (!task) {
    selectedTaskTree = null;
    return;
  }
  try {
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/tree`);
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `任务树加载失败: ${res.status}`));
    }
    selectedTaskTree = await res.json();
  } catch (err) {
    selectedTaskTree = null;
    if (!silent) showTaskDetailsError(err.message);
    console.error(err);
  }
}

async function setActiveProject(projectId) {
  if (!projectId || projectId === activeProjectId) {
    if (projectId) setBlackboardOpen(true);
    return;
  }
  activeProjectId = projectId;
  localStorage.setItem(activeProjectStorageKey(), activeProjectId);
  selectedTaskId = null;
  selectedTaskTree = null;
  blackboardOpen = true;
  try {
    await Promise.all([loadProjectAgents(), loadProjectTasks({ silent: true })]);
  } catch (err) {
    showComposerStatus(err.message, "error", { source: "tasks", timeoutMs: 3500 });
  }
  renderProjectStrip();
  renderRoomStrip();
  renderWorkspaceMode();
}

async function refreshProjectWorkspace() {
  if (!activeProjectId) return;
  refreshProjectBtn.disabled = true;
  blackboardRefreshBtn.disabled = true;
  taskDetailsRefreshBtn.disabled = true;
  try {
    await loadProjectAgents();
    await loadProjectTasks();
    await loadGroups();
    renderRoomStrip();
  } finally {
    refreshProjectBtn.disabled = false;
    blackboardRefreshBtn.disabled = false;
    taskDetailsRefreshBtn.disabled = false;
  }
}

function renderProjectStrip() {
  if (!myId) return;
  projectStrip.classList.remove("hidden");
  projectSelect.innerHTML = "";
  if (!projects.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无项目";
    projectSelect.appendChild(option);
  } else {
    for (const project of projects) {
      const option = document.createElement("option");
      option.value = project.project_id;
      option.textContent = project.display_name;
      option.selected = project.project_id === activeProjectId;
      projectSelect.appendChild(option);
    }
  }
  projectSelect.disabled = projects.length === 0;
  projectBlackboardBtn.disabled = !activeProjectId;
  projectBlackboardBtn.classList.toggle("active", blackboardOpen && Boolean(activeProjectId));
  projectTaskCount.textContent = String(projectTasks.length);
  const canDelegate = Boolean(activeProjectId && eligibleProjectAgents().length);
  delegateTaskBtn.disabled = !canDelegate;
  blackboardDelegateBtn.disabled = !canDelegate;
  projectEmptyNote.classList.toggle("hidden", projects.length > 0);
}

function eligibleProjectAgents() {
  const indexedIds = new Set(projectAgents.map((agent) => agent.member_id));
  const hasIndex = indexedIds.size > 0;
  return members
    .filter((member) => member.kind === "agent")
    .filter((member) => !member.disabled_at && member.id !== myId)
    .filter((member) => !hasIndex || indexedIds.has(member.id))
    .sort((a, b) => a.id.localeCompare(b.id, "zh-CN"));
}

function setBlackboardOpen(open) {
  blackboardOpen = Boolean(open && activeProjectId);
  setGroupCreateOpen(false);
  renderProjectStrip();
  renderRoomStrip();
  renderWorkspaceMode();
  if (blackboardOpen) {
    loadProjectTasks({ silent: true });
  } else if (activeGroupId) {
    loadHistory();
  }
}

function renderWorkspaceMode() {
  blackboardView.classList.toggle("hidden", !blackboardOpen);
  hallHeader.classList.toggle("hidden", blackboardOpen);
  messagesEl.classList.toggle("hidden", blackboardOpen);
  composerFooter.classList.toggle("hidden", blackboardOpen);
  if (blackboardOpen) renderBlackboard();
  renderGroupMembersPanel();
}

function taskStatusMeta(task) {
  const workflow = task?.workflow_status || "assigned";
  const mapping = {
    assigned: ["待执行者确认", "attention"],
    clarification_requested: ["待请求者澄清", "attention"],
    clarification_answered: ["澄清已提交 · 待确认", "attention"],
    needs_decision: ["需要人工决策", "danger"],
    accepted: ["已接受 · 待领取", ""],
    in_progress: ["执行中", "running"],
    submitted: ["结果待收取", "attention"],
    completed: ["已完成", "success"],
    failed: ["失败", "danger"],
    canceled: ["已取消", "danger"],
  };
  const [label, className] = mapping[workflow] || [workflow, ""];
  return { label, className };
}

function taskBoardColumn(task) {
  if (["assigned", "clarification_requested", "clarification_answered", "needs_decision", "accepted"].includes(task.workflow_status)) return "attention";
  if (task.workflow_status === "in_progress") return "running";
  if (task.workflow_status === "submitted") return "submitted";
  return "finished";
}

function formatTaskTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function renderBlackboard() {
  const project = getActiveProject();
  blackboardTitle.textContent = project ? `${project.display_name} · 任务黑板` : "任务黑板";
  blackboardDescription.textContent = project?.description || "按协作状态查看项目任务，点击卡片可查看 Task Hall 与可执行动作。";
  blackboardSummary.innerHTML = "";
  blackboardColumns.innerHTML = "";

  const columns = [
    { key: "attention", label: "待响应" },
    { key: "running", label: "执行中" },
    { key: "submitted", label: "结果待收取" },
    { key: "finished", label: "已结束" },
  ];
  for (const column of columns) {
    const count = projectTasks.filter((task) => taskBoardColumn(task) === column.key).length;
    const chip = document.createElement("span");
    chip.className = "blackboard-summary-chip";
    const label = document.createElement("span");
    label.textContent = column.label;
    const number = document.createElement("strong");
    number.textContent = String(count);
    chip.appendChild(label);
    chip.appendChild(number);
    blackboardSummary.appendChild(chip);
  }

  blackboardEmpty.classList.toggle("hidden", projectTasks.length > 0);
  blackboardColumns.classList.toggle("hidden", projectTasks.length === 0);
  for (const column of columns) {
    const tasks = projectTasks.filter((task) => taskBoardColumn(task) === column.key);
    const columnEl = document.createElement("section");
    columnEl.className = "blackboard-column";
    const header = document.createElement("div");
    header.className = "blackboard-column-header";
    const title = document.createElement("span");
    title.textContent = column.label;
    const count = document.createElement("span");
    count.className = "blackboard-column-count";
    count.textContent = String(tasks.length);
    header.appendChild(title);
    header.appendChild(count);
    const list = document.createElement("div");
    list.className = "blackboard-card-list";
    if (!tasks.length) {
      const empty = document.createElement("div");
      empty.className = "blackboard-column-empty";
      empty.textContent = "暂无任务";
      list.appendChild(empty);
    }
    for (const task of tasks) {
      list.appendChild(renderTaskCard(task));
    }
    columnEl.appendChild(header);
    columnEl.appendChild(list);
    blackboardColumns.appendChild(columnEl);
  }
}

function renderTaskCard(task) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = `task-card ${Number(task.id) === Number(selectedTaskId) ? "selected" : ""}`;
  const title = document.createElement("div");
  title.className = "task-card-title";
  title.textContent = task.title || task.content || `任务 #${task.id}`;
  const status = document.createElement("span");
  const meta = taskStatusMeta(task);
  status.className = `task-status-badge ${meta.className}`;
  status.textContent = meta.label;
  const people = document.createElement("div");
  people.className = "task-card-meta";
  people.textContent = `${shortName(task.created_by)} → ${shortName(task.target_member_id)}`;
  const footer = document.createElement("div");
  footer.className = "task-card-footer";
  const attempt = document.createElement("span");
  attempt.textContent = `#${task.id} · attempt ${task.attempt || 0}`;
  const updated = document.createElement("span");
  updated.textContent = formatTaskTime(task.updated_at);
  footer.appendChild(attempt);
  footer.appendChild(updated);
  card.appendChild(title);
  card.appendChild(status);
  card.appendChild(people);
  card.appendChild(footer);
  card.addEventListener("click", async () => {
    selectedTaskId = task.id;
    selectedTaskTree = null;
    renderBlackboard();
    renderTaskDetailsPanel();
    await loadSelectedTaskTree();
    renderTaskDetailsPanel();
  });
  card.addEventListener("dblclick", () => openTaskHall(task));
  return card;
}

function getContextTask() {
  if (!blackboardOpen && activeGroupId) {
    return projectTasks.find((task) => task.hall_group_id === activeGroupId) || null;
  }
  return projectTasks.find((task) => Number(task.id) === Number(selectedTaskId)) || null;
}

function showTaskDetailsError(message) {
  taskDetailsError.textContent = message || "";
  taskDetailsError.classList.toggle("hidden", !message);
}

function taskActionButton(label, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.disabled = taskActionSaving;
  button.addEventListener("click", handler);
  return button;
}

function currentMemberIsHuman() {
  return members.find((member) => member.id === myId)?.kind === "human";
}

function taskKindLabel(kind) {
  return {
    general: "普通任务",
    development: "开发切片",
    review: "Review",
    test: "Test",
    rework: "返工",
  }[kind] || kind || "普通任务";
}

function checkpointReasonLabel(reason) {
  return {
    batch_limit: "本批额度已安全收尾",
    risk_boundary: "风险边界",
    milestone: "里程碑待人工验收",
    time_limit: "授权时间到期",
    usage_limit: "用量门禁",
    review_exhausted: "返工轮次耗尽",
    needs_decision: "澄清需要人工决策",
    manual_pause: "人工暂停",
  }[reason] || reason || "无";
}

function appendTaskGovernanceCard(tree) {
  if (!tree?.root) return;
  const card = document.createElement("div");
  card.className = "task-governance-card";
  const title = document.createElement("strong");
  title.textContent = "任务树控制与质量门禁";
  card.appendChild(title);
  const control = document.createElement("div");
  control.textContent = `控制：${tree.root.control_status || "—"} · 检查点：${checkpointReasonLabel(tree.root.checkpoint_reason)}`;
  card.appendChild(control);
  const budget = document.createElement("div");
  budget.textContent = `授权 epoch ${tree.root.authorization_epoch || 0} · 剩余切片 ${tree.remaining_slice_budget} · 非终态后代 ${tree.nonterminal_descendants}`;
  card.appendChild(budget);

  const reviewList = document.createElement("div");
  reviewList.className = "task-gate-list";
  for (const gate of tree.review_gates || []) {
    const row = document.createElement("div");
    const verdict = gate.current_verdict?.verdict || "pending";
    row.textContent = `Review · 开发 #${gate.development_task_id} → 当前 #${gate.current_subject_task_id}：${verdict}`;
    reviewList.appendChild(row);
  }
  const testGate = tree.test_gate;
  if (testGate?.required) {
    const row = document.createElement("div");
    row.textContent = `里程碑 Test · 冻结版本 ${testGate.frozen_task_ids.map((id) => `#${id}`).join("、") || "尚未形成"}：${testGate.current_verdict?.verdict || "pending"}`;
    reviewList.appendChild(row);
  }
  if (!reviewList.childElementCount) {
    const row = document.createElement("div");
    row.textContent = "当前任务树没有强制质量门禁。";
    reviewList.appendChild(row);
  }
  card.appendChild(reviewList);
  taskDetailsContent.insertAdjacentElement("afterend", card);
}

function renderTaskDetailsPanel() {
  const task = getContextTask();
  taskDetailsPanel.classList.toggle("hidden", !task);
  groupMembersPanel.classList.toggle("hidden", Boolean(task));
  if (!task) return;

  taskDetailsTitle.textContent = task.title || `任务 #${task.id}`;
  taskDetailsStatus.innerHTML = "";
  const meta = taskStatusMeta(task);
  const badge = document.createElement("span");
  badge.className = `task-status-badge ${meta.className}`;
  badge.textContent = meta.label;
  taskDetailsStatus.appendChild(badge);
  taskDetailsMeta.innerHTML = "";
  const rows = [
    `任务 ID：${task.id}`,
    `类型：${taskKindLabel(task.task_kind)}`,
    `请求者：${task.created_by}`,
    `执行者：${task.target_member_id}`,
    `执行状态：${task.status}`,
    `attempt：${task.attempt || 0}`,
    task.lease_expires_at ? `租约截止：${formatTaskTime(task.lease_expires_at)}` : "当前无活动租约",
  ];
  for (const value of rows) {
    const row = document.createElement("div");
    row.textContent = value;
    taskDetailsMeta.appendChild(row);
  }
  taskDetailsContent.textContent = task.content || "";
  taskDetailsPanel.querySelectorAll(".task-governance-card").forEach((node) => node.remove());
  appendTaskGovernanceCard(selectedTaskTree);
  showTaskDetailsError("");
  taskDetailsActions.innerHTML = "";

  if (task.hall_group_id) {
    taskDetailsActions.appendChild(
      taskActionButton("进入 Task Hall", "task-action-primary", () => openTaskHall(task))
    );
  }
  if (task.target_member_id === myId && ["assigned", "clarification_answered"].includes(task.workflow_status)) {
    taskDetailsActions.appendChild(
      taskActionButton("标记为待澄清", "task-action-secondary", () => runTaskAction(task, "request-clarification"))
    );
  }
  if (task.target_member_id === myId && ["assigned", "clarification_answered"].includes(task.workflow_status)) {
    taskDetailsActions.appendChild(
      taskActionButton("接受任务", "task-action-secondary", () => runTaskAction(task, "accept"))
    );
  }
  if (task.created_by === myId && task.workflow_status === "submitted") {
    taskDetailsActions.appendChild(
      taskActionButton("收取并完成", "task-action-primary", () => runTaskAction(task, "collect-result"))
    );
  }
  if (task.created_by === myId && task.workflow_status === "clarification_requested") {
    taskDetailsActions.appendChild(
      taskActionButton("提交 Hall 中最新澄清答复", "task-action-primary", () => submitLatestClarificationAnswer(task))
    );
  }
  if (currentMemberIsHuman() && task.workflow_status === "needs_decision") {
    taskDetailsActions.appendChild(
      taskActionButton("释放人工决策", "task-action-secondary", () => resolveTaskDecision(task))
    );
  }
  if (task.created_by === myId && task.status === "queued") {
    taskDetailsActions.appendChild(
      taskActionButton("取消未领取任务", "task-action-danger", () => runTaskAction(task, "cancel", { confirmCancel: true }))
    );
  }

  const tree = selectedTaskTree;
  const root = tree?.root;
  if (currentMemberIsHuman() && root) {
    if (root.status === "running" && root.control_status === "active" && root.may_delegate) {
      taskDetailsActions.appendChild(
        taskActionButton("创建开发 / Review / Test 子任务", "task-action-primary", () => setTaskCreateOpen(true, { parentRoot: root }))
      );
    }
    if (root.control_status === "active") {
      taskDetailsActions.appendChild(
        taskActionButton("暂停整棵任务树", "task-action-secondary", () => runTaskTreeAction(root, "pause-tree"))
      );
      taskDetailsActions.appendChild(
        taskActionButton("在风险边界暂停", "task-action-secondary", () => runTaskTreeAction(root, "checkpoint", { reason: "risk_boundary" }))
      );
    }
    if (["paused", "awaiting_human"].includes(root.control_status) && root.checkpoint_reason !== "milestone") {
      taskDetailsActions.appendChild(
        taskActionButton("授权继续一批", "task-action-primary", () => resumeTaskTreeFromBlackboard(root))
      );
    }
    if (root.control_status === "awaiting_human" && root.checkpoint_reason === "milestone" && tree.test_gate?.satisfied) {
      taskDetailsActions.appendChild(
        taskActionButton("人工验收通过", "task-action-primary", () => runTaskTreeAction(root, "accept-milestone"))
      );
    }
    if (root.control_status !== "canceled") {
      taskDetailsActions.appendChild(
        taskActionButton("终止整棵任务树", "task-action-danger", () => runTaskTreeAction(root, "cancel-tree", null, { confirmCancel: true }))
      );
    }
  }
}

async function openTaskHall(task) {
  if (!task?.hall_group_id) return;
  if (!groups.some((group) => group.id === task.hall_group_id)) {
    await loadGroups();
  }
  selectedTaskId = task.id;
  setActiveGroup(task.hall_group_id);
}

async function runTaskAction(task, action, { confirmCancel = false } = {}) {
  if (taskActionSaving) return;
  if (confirmCancel && !window.confirm("取消后该任务不能重新领取。确定取消吗？")) return;
  taskActionSaving = true;
  showTaskDetailsError("");
  renderTaskDetailsPanel();
  try {
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/${action}`, { method: "POST" });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `任务操作失败: ${res.status}`));
    }
    const updated = await res.json();
    projectTasks = projectTasks.map((item) => Number(item.id) === Number(updated.id) ? updated : item);
    selectedTaskId = updated.id;
    await loadSelectedTaskTree({ silent: true });
    renderProjectStrip();
    renderBlackboard();
  } catch (err) {
    showTaskDetailsError(err.message);
  } finally {
    taskActionSaving = false;
    renderTaskDetailsPanel();
  }
}

async function runTaskTreeAction(root, action, body = null, { confirmCancel = false } = {}) {
  if (taskActionSaving) return;
  if (confirmCancel && !window.confirm("这会终止整棵任务树，未完成任务不能恢复。确定继续吗？")) return;
  taskActionSaving = true;
  showTaskDetailsError("");
  renderTaskDetailsPanel();
  try {
    const options = { method: "POST" };
    if (body !== null) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(root.id)}/${action}`, options);
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `任务树操作失败: ${res.status}`));
    }
    selectedTaskTree = await res.json();
    await loadProjectTasks({ silent: true });
  } catch (err) {
    showTaskDetailsError(err.message);
  } finally {
    taskActionSaving = false;
    renderTaskDetailsPanel();
  }
}

function resumeTaskTreeFromBlackboard(root) {
  const raw = window.prompt("下一批允许启动多少个开发切片？请输入 1–3。", "1");
  if (raw === null) return;
  const sliceBudget = Number(raw);
  if (!Number.isInteger(sliceBudget) || sliceBudget < 1 || sliceBudget > 3) {
    showTaskDetailsError("切片额度必须是 1–3 的整数。");
    return;
  }
  runTaskTreeAction(root, "resume-tree", {
    slice_budget: sliceBudget,
    authorization_ttl_seconds: 5400,
  });
}

async function submitLatestClarificationAnswer(task) {
  if (!task.hall_group_id || taskActionSaving) return;
  taskActionSaving = true;
  showTaskDetailsError("");
  renderTaskDetailsPanel();
  try {
    const params = new URLSearchParams({ group_id: task.hall_group_id, limit: "100" });
    const history = await apiFetch(`/api/messages?${params.toString()}`);
    if (!history.ok) {
      throw new Error(await readErrorDetail(history, `Hall 消息读取失败: ${history.status}`));
    }
    const latest = (await history.json())
      .filter((message) => message.from_id === myId && !message.revoked_at)
      .sort((a, b) => Number(b.id) - Number(a.id))[0];
    if (!latest) {
      throw new Error("请先进入 Task Hall 发送完整澄清答复，再提交边界。");
    }
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/submit-clarification-answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_message_id: latest.id }),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `澄清答复提交失败: ${res.status}`));
    }
    await loadProjectTasks({ silent: true });
  } catch (err) {
    showTaskDetailsError(err.message);
  } finally {
    taskActionSaving = false;
    renderTaskDetailsPanel();
  }
}

async function resolveTaskDecision(task) {
  const allowAdditionalRound = window.confirm("是否额外开放一轮澄清？选择“取消”会仅按当前补充继续。 ");
  if (taskActionSaving) return;
  taskActionSaving = true;
  showTaskDetailsError("");
  renderTaskDetailsPanel();
  try {
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/resolve-clarification`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ allow_additional_round: allowAdditionalRound }),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `人工决策释放失败: ${res.status}`));
    }
    await loadProjectTasks({ silent: true });
  } catch (err) {
    showTaskDetailsError(err.message);
  } finally {
    taskActionSaving = false;
    renderTaskDetailsPanel();
  }
}

function showTaskCreateError(message) {
  taskCreateError.textContent = message || "";
  taskCreateError.classList.toggle("hidden", !message);
}

function renderTaskCreateAgentOptions() {
  taskCreateAgent.innerHTML = "";
  const agents = eligibleProjectAgents();
  if (!agents.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "项目中没有可委派 Agent";
    taskCreateAgent.appendChild(option);
  } else {
    for (const member of agents) {
      const option = document.createElement("option");
      option.value = member.id;
      option.textContent = `${member.display_name || shortName(member.id)} · ${member.id}`;
      taskCreateAgent.appendChild(option);
    }
  }
  taskCreateAgent.disabled = taskCreateSaving || !agents.length;
  submitTaskCreateBtn.disabled = taskCreateSaving || !agents.length;
}

function taskOptionLabel(task) {
  return `#${task.id} · ${taskKindLabel(task.task_kind)} · ${task.title || task.content || "未命名"}`;
}

function renderTaskCreateMode() {
  const childMode = Boolean(taskCreateParentRoot);
  taskCreateGovernance.classList.toggle("hidden", childMode);
  taskCreateQuality.classList.toggle("hidden", !childMode);
  taskCreateSliceBudget.disabled = !taskCreateDelegation.checked;
  taskCreateMilestone.disabled = !taskCreateDelegation.checked;
  if (!childMode) return;

  const kind = taskCreateKind.value;
  taskCreateReviewPolicyField.classList.toggle("hidden", kind !== "development");
  taskCreateRelatedField.classList.toggle("hidden", !["review", "test", "rework"].includes(kind));
  taskCreateTriggerField.classList.toggle("hidden", kind !== "rework");
  taskCreateRelated.innerHTML = "";
  taskCreateTrigger.innerHTML = "";

  const tasks = selectedTaskTree?.tasks || [];
  let related = [];
  if (["review", "test"].includes(kind)) {
    const frozenIds = new Set(selectedTaskTree?.test_gate?.frozen_task_ids || []);
    related = tasks.filter((task) => frozenIds.has(Number(task.id)));
  } else if (kind === "rework") {
    related = tasks.filter((task) => task.task_kind === "development");
  }
  for (const task of related) {
    const option = document.createElement("option");
    option.value = String(task.id);
    option.textContent = taskOptionLabel(task);
    option.selected = kind === "test" || (kind === "rework" && related.length === 1);
    taskCreateRelated.appendChild(option);
  }

  if (kind === "rework") {
    const triggers = tasks.filter((task) => {
      const verdict = task.gate_verdict?.verdict;
      return (task.task_kind === "review" && verdict === "changes_requested")
        || (task.task_kind === "test" && verdict === "failed");
    });
    for (const task of triggers) {
      const option = document.createElement("option");
      option.value = String(task.id);
      option.textContent = `${taskOptionLabel(task)} · ${task.gate_verdict.verdict}`;
      taskCreateTrigger.appendChild(option);
    }
  }
}

function setTaskCreateOpen(open, { parentRoot = null } = {}) {
  taskCreateOpen = Boolean(open && activeProjectId);
  showTaskCreateError("");
  taskCreateOverlay.classList.toggle("hidden", !taskCreateOpen);
  if (!taskCreateOpen) {
    taskCreatePanel.reset();
    taskCreateParentRoot = null;
    return;
  }
  taskCreateParentRoot = parentRoot;
  const project = getActiveProject();
  taskCreateProject.textContent = project
    ? `${project.display_name} · ${project.project_id}${parentRoot ? ` · 根任务 #${parentRoot.id}` : ""}`
    : "";
  taskCreateDelegation.checked = false;
  taskCreateMilestone.checked = false;
  taskCreateSliceBudget.value = "1";
  taskCreateKind.value = "development";
  taskCreateReviewPolicy.value = "required";
  renderTaskCreateAgentOptions();
  renderTaskCreateMode();
  taskCreateTitle.focus();
}

async function createTaskFromPanel(event) {
  event.preventDefault();
  if (taskCreateSaving || !activeProjectId) return;
  const payload = {
    project_id: activeProjectId,
    target_member_id: taskCreateAgent.value,
    title: taskCreateTitle.value.trim() || null,
    content: taskCreateContent.value.trim(),
  };
  if (taskCreateParentRoot) {
    payload.parent_task_id = taskCreateParentRoot.id;
    payload.authorization_epoch = taskCreateParentRoot.authorization_epoch;
    payload.task_kind = taskCreateKind.value;
    if (payload.task_kind === "development") {
      payload.review_policy = taskCreateReviewPolicy.value;
    }
    if (["review", "test", "rework"].includes(payload.task_kind)) {
      payload.related_task_ids = Array.from(taskCreateRelated.selectedOptions, (option) => Number(option.value));
    }
    if (payload.task_kind === "rework") {
      payload.trigger_task_id = Number(taskCreateTrigger.value) || null;
    }
  } else {
    payload.may_delegate = taskCreateDelegation.checked;
    payload.milestone_test_required = taskCreateMilestone.checked;
    if (payload.may_delegate) {
      payload.slice_budget = Number(taskCreateSliceBudget.value);
    }
  }
  if (!payload.target_member_id || !payload.content) {
    showTaskCreateError("请选择执行 Agent，并填写任务正文。");
    return;
  }
  if (taskCreateParentRoot && ["review", "test", "rework"].includes(payload.task_kind) && !payload.related_task_ids.length) {
    showTaskCreateError("请选择质量任务要覆盖的最新冻结任务。");
    return;
  }
  if (payload.task_kind === "rework" && !payload.trigger_task_id) {
    showTaskCreateError("请选择触发返工的 Review 或 Test。");
    return;
  }
  taskCreateSaving = true;
  submitTaskCreateBtn.disabled = true;
  showTaskCreateError("");
  try {
    const res = await apiFetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `任务创建失败: ${res.status}`));
    }
    const created = await res.json();
    selectedTaskId = created.id;
    setTaskCreateOpen(false);
    blackboardOpen = true;
    await Promise.all([loadGroups(), loadProjectTasks()]);
    renderWorkspaceMode();
  } catch (err) {
    showTaskCreateError(err.message);
  } finally {
    taskCreateSaving = false;
    renderTaskCreateAgentOptions();
  }
}

// ── Group / Hall room navigation ────────────────────────────────────
function activeGroupStorageKey() {
  return myId ? `${ACTIVE_GROUP_STORAGE}:${myId}` : ACTIVE_GROUP_STORAGE;
}

async function loadGroups() {
  try {
    const res = await apiFetch("/api/groups");
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `Group 列表加载失败: ${res.status}`));
    }
    groups = await res.json();
    restoreActiveGroup();
  } catch (err) {
    groups = [];
    activeGroupId = null;
    console.error(err);
    showComposerStatus(err.message, "error", { source: "load", timeoutMs: 0 });
  }
}

async function refreshGroups() {
  refreshGroupsBtn.disabled = true;
  try {
    const previousGroupId = activeGroupId;
    await loadGroups();
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
    if (previousGroupId !== activeGroupId) {
      resetTimelineState();
      await loadHistory();
    } else {
      clearComposerStatus("load");
    }
  } finally {
    refreshGroupsBtn.disabled = false;
  }
}

function restoreActiveGroup() {
  const storedGroupId = localStorage.getItem(activeGroupStorageKey()) || "";
  if (storedGroupId && canEnterGroup(storedGroupId)) {
    activeGroupId = storedGroupId;
  } else {
    activeGroupId = null;
    localStorage.removeItem(activeGroupStorageKey());
  }
}

function getActiveGroup() {
  if (!activeGroupId) return null;
  return groups.find((group) => group.id === activeGroupId) || null;
}

function canManageGroups() {
  return myId.startsWith("human:");
}

function findMember(memberId) {
  return members.find((member) => member.id === memberId) || null;
}

function replaceGroup(updatedGroup) {
  groups = groups.some((group) => group.id === updatedGroup.id)
    ? groups.map((group) => group.id === updatedGroup.id ? updatedGroup : group)
    : [updatedGroup, ...groups];
}

function getGroupMemberIds(group) {
  return new Set((group?.members || []).map((member) => member.member_id));
}

function canEnterGroup(groupId) {
  const group = groups.find((item) => item.id === groupId);
  return Boolean(group && getGroupMemberIds(group).has(myId));
}

function setActiveGroup(groupId) {
  const nextGroupId = groupId || null;
  if (nextGroupId && !canEnterGroup(nextGroupId)) {
    showComposerStatus("你还不是这个 Group 的成员，无法进入它的 Hall。", "error", {
      source: "room",
      timeoutMs: 3500,
    });
    return;
  }
  if (activeGroupId === nextGroupId && !blackboardOpen) return;

  blackboardOpen = false;
  activeGroupId = nextGroupId;
  if (activeGroupId) {
    localStorage.setItem(activeGroupStorageKey(), activeGroupId);
  } else {
    localStorage.removeItem(activeGroupStorageKey());
    groupMembersOpen = false;
  }

  setGroupCreateOpen(false);
  resetTimelineState();
  renderRoomStrip();
  renderPresenceStrip();
  renderMentionDropdownIfOpen();
  updateComposerPlaceholder();
  renderProjectStrip();
  renderWorkspaceMode();
  loadHistory();
  msgInput.focus();
}

function renderRoomStrip() {
  if (!myId) return;

  roomStrip.classList.remove("hidden");
  const activeGroup = getActiveGroup();
  groupMembersOpen = Boolean(activeGroup);
  globalRoomBtn.classList.toggle("active", !blackboardOpen && !activeGroupId);
  groupRoomList.innerHTML = "";

  roomTitle.textContent = activeGroup ? `${activeGroup.name} Hall` : "全局消息流";
  roomTitle.classList.toggle("editable", Boolean(activeGroup));
  roomDescription.textContent = activeGroup
    ? `${activeGroup.id} · Hall 在线同步中 · @ 开头提醒成员，同组可见${activeGroup.description ? ` · ${activeGroup.description}` : ""}`
    : "旧全局聊天与私聊时间线";
  const hallGroupId = document.getElementById("hall-group-id");
  if (hallGroupId) {
    hallGroupId.textContent = activeGroup ? activeGroup.id : "";
    hallGroupId.classList.toggle("hidden", !activeGroup);
  }

  const hallQuery = hallFilterInput.value.trim().toLowerCase();
  const projectGroups = activeProjectId
    ? groups.filter((group) => group.project_id === activeProjectId || !group.project_id)
    : groups;
  const visibleGroups = hallQuery
    ? projectGroups.filter((group) => groupMatchesHallQuery(group, hallQuery))
    : projectGroups;

  if (projectGroups.length === 0) {
    const empty = document.createElement("span");
    empty.className = "group-room-empty";
    empty.textContent = activeProjectId ? "当前项目暂无 Hall" : "暂无 Group";
    groupRoomList.appendChild(empty);
  } else if (visibleGroups.length === 0) {
    const empty = document.createElement("span");
    empty.className = "group-room-empty";
    empty.textContent = "没有匹配的 Hall";
    groupRoomList.appendChild(empty);
  } else {
    for (const group of visibleGroups) {
      const button = document.createElement("button");
      const isActive = !blackboardOpen && group.id === activeGroupId;
      const canEnter = getGroupMemberIds(group).has(myId);
      button.type = "button";
      button.className = `room-chip ${isActive ? "active" : ""}`;
      const typeLabel = group.type === "task" ? "任务" : group.type === "discussion" ? "讨论" : "Hall";
      button.textContent = `${typeLabel} · ${group.name}`;
      button.title = canEnter
        ? `${group.name} (${group.id})`
        : `${group.name} (${group.id}) · 你还不是成员`;
      button.disabled = !canEnter;
      button.addEventListener("click", () => setActiveGroup(group.id));
      groupRoomList.appendChild(button);
    }
  }

  toggleGroupCreateBtn.textContent = groupCreateOpen ? "×" : "＋";
  toggleGroupMembersBtn.classList.toggle(
    "hidden",
    !activeGroup || blackboardOpen || activeGroup.type === "task" || Boolean(getContextTask())
  );
  toggleGroupMembersBtn.classList.toggle("active", groupMembersOpen && Boolean(activeGroup));
  toggleGroupMembersBtn.textContent = "＋";
  groupCreateOverlay.classList.toggle("hidden", !groupCreateOpen);
  renderGroupCreateMembers();
  renderGroupMembersPanel();
}

function groupMatchesHallQuery(group, query) {
  const haystack = [
    group.id,
    group.name,
    group.description,
    ...(group.members || []).flatMap((membership) => {
      const member = findMember(membership.member_id);
      return [membership.member_id, membership.role, member?.display_name, member?.kind];
    }),
  ];
  return haystack
    .filter((value) => typeof value === "string" && value)
    .some((value) => value.toLowerCase().includes(query));
}

function setGroupCreateOpen(open) {
  groupCreateOpen = open;
  showGroupCreateError("");
  if (open) {
    groupMembersOpen = false;
  }
  if (open) {
    selectedCreateMemberIds = new Set();
    renderGroupCreateMembers();
    groupCreateName.focus();
  } else {
    groupCreatePanel.reset();
  }
  renderRoomStrip();
}

function setGroupMembersOpen(open) {
  const activeGroup = getActiveGroup();
  groupMembersOpen = Boolean(open && activeGroup);
  if (groupMembersOpen) {
    groupCreateOpen = false;
  }
  showGroupMembersError("");
  renderRoomStrip();
}

function renderGroupCreateMembers() {
  // Dropdown lists members not yet added (self is always the owner, excluded).
  groupCreateMemberSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = members.length ? "添加成员…" : "成员列表尚未加载";
  groupCreateMemberSelect.appendChild(placeholder);
  for (const member of members) {
    if (member.id === myId || selectedCreateMemberIds.has(member.id)) continue;
    const option = document.createElement("option");
    option.value = member.id;
    option.textContent = `${shortName(member.id)} · ${member.display_name}`;
    groupCreateMemberSelect.appendChild(option);
  }
  groupCreateMemberSelect.disabled = !members.length;

  // Chips show the selected members, each removable.
  groupCreateMemberChips.innerHTML = "";
  for (const memberId of selectedCreateMemberIds) {
    const chip = document.createElement("span");
    chip.className = "group-create-chip";

    const text = document.createElement("span");
    text.textContent = shortName(memberId);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "group-create-chip-remove";
    remove.setAttribute("aria-label", `移除 ${memberId}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      selectedCreateMemberIds.delete(memberId);
      renderGroupCreateMembers();
    });

    chip.appendChild(text);
    chip.appendChild(remove);
    groupCreateMemberChips.appendChild(chip);
  }
}

function showGroupCreateError(message) {
  groupCreateError.textContent = message;
  groupCreateError.classList.toggle("hidden", !message);
}

async function createGroupFromPanel(event) {
  event.preventDefault();
  if (groupCreateSaving) return;

  const name = groupCreateName.value.trim();
  if (!name) {
    showGroupCreateError("请填写 Group 名称。");
    groupCreateName.focus();
    return;
  }

  const selectedMemberIds = Array.from(selectedCreateMemberIds)
    .filter((memberId) => memberId && memberId !== myId);

  const body = {
    name,
    member_ids: selectedMemberIds,
  };
  const id = groupCreateId.value.trim();
  const description = groupCreateDescription.value.trim();
  if (id) body.id = id;
  if (description) body.description = description;

  groupCreateSaving = true;
  submitGroupCreateBtn.disabled = true;
  cancelGroupCreateBtn.disabled = true;
  try {
    const res = await apiFetch("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `Group 创建失败: ${res.status}`));
    }

    const group = await res.json();
    groups = [group, ...groups.filter((item) => item.id !== group.id)];
    activeGroupId = group.id;
    localStorage.setItem(activeGroupStorageKey(), activeGroupId);
    groupCreateOpen = false;
    groupCreatePanel.reset();
    clearComposerStatus("room");
    resetTimelineState();
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
    updateComposerPlaceholder();
    await loadHistory();
  } catch (err) {
    console.error(err);
    showGroupCreateError(err.message);
  } finally {
    groupCreateSaving = false;
    submitGroupCreateBtn.disabled = false;
    cancelGroupCreateBtn.disabled = false;
  }
}

function sortedGroupMembers(group) {
  const roleRank = { owner: 0, moderator: 1, member: 2 };
  return [...(group?.members || [])].sort((a, b) => {
    const rankDiff = (roleRank[a.role] ?? 9) - (roleRank[b.role] ?? 9);
    if (rankDiff !== 0) return rankDiff;
    return a.member_id.localeCompare(b.member_id, "zh-CN");
  });
}

function showGroupMembersError(message) {
  groupMembersError.textContent = message;
  groupMembersError.classList.toggle("hidden", !message);
}

function renderGroupMembersPanel() {
  const activeGroup = getActiveGroup();
  const contextTask = getContextTask();
  renderTaskDetailsPanel();
  const isOpen = Boolean(activeGroup && activeGroup.type !== "task" && !blackboardOpen && !contextTask);
  groupMembersPanel.classList.toggle("hidden", !isOpen);
  if (!isOpen || !activeGroup) return;

  const canManage = canManageGroups();
  const memberIds = getGroupMemberIds(activeGroup);
  groupMembersSubtitle.textContent = "";
  groupMetaForm.classList.toggle("hidden", !canManage || !groupMetaEditing);
  if (canManage && groupMetaEditing) {
    groupMetaName.value = activeGroup.name || "";
    groupMetaDescription.value = activeGroup.description || "";
    groupMetaName.disabled = groupMetaSaving;
    groupMetaDescription.disabled = groupMetaSaving;
    groupMetaSaveBtn.disabled = groupMetaSaving;
  }
  groupMembersList.innerHTML = "";

  const memberships = sortedGroupMembers(activeGroup).filter((membership) => {
    if (!selectedMemberKindFilters.size) return true;
    const member = findMember(membership.member_id);
    return selectedMemberKindFilters.has(member?.kind || memberKindFromId(membership.member_id));
  });

  for (const membership of memberships) {
    const member = findMember(membership.member_id);
    const row = document.createElement("div");
    row.className = "group-member-row";

    const identity = document.createElement("div");
    identity.className = "group-member-identity";

    const name = document.createElement("div");
    name.className = "group-member-name";
    name.textContent = membership.member_id === myId
      ? `${shortName(membership.member_id)} (我)`
      : shortName(membership.member_id);

    const meta = document.createElement("div");
    meta.className = "group-member-meta";
    const onlineText = onlineMemberIds.has(membership.member_id) ? "在线" : "离线";
    const metaParts = [membership.role];
    if (membership.business_role) metaParts.push(membership.business_role);
    metaParts.push(onlineText);
    meta.textContent = metaParts.join(" · ");

    const dot = document.createElement("span");
    dot.className = `member-status-dot ${onlineMemberIds.has(membership.member_id) ? "online" : "offline"}`;

    identity.appendChild(dot);
    identity.appendChild(name);
    identity.appendChild(meta);

    const controls = document.createElement("div");
    controls.className = "group-member-controls";

    if (member?.kind === "agent" && canManage && activeGroup.project_id) {
      const editProfileButton = document.createElement("button");
      editProfileButton.type = "button";
      editProfileButton.className = "group-member-remove-btn";
      editProfileButton.textContent = "编辑人设";
      editProfileButton.disabled = groupMemberSaving || agentProfileSaving;
      editProfileButton.title = "编辑该 agent 的 IDENTITY / SOUL / USER 与业务角色";
      editProfileButton.addEventListener("click", () => openAgentProfileEditor(membership));
      controls.appendChild(editProfileButton);
    }

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "group-member-remove-btn";
    removeButton.textContent = "移除";
    removeButton.disabled = !canManage || groupMemberSaving || membership.member_id === myId;
    removeButton.title = membership.member_id === myId ? "不能在当前界面移除自己" : "移出 Group";
    removeButton.addEventListener("click", () => removeGroupMemberFromPanel(membership.member_id));

    controls.appendChild(removeButton);
    row.appendChild(identity);
    row.appendChild(controls);
    groupMembersList.appendChild(row);
  }

  if (memberships.length === 0) {
    const empty = document.createElement("div");
    empty.className = "member-empty-state";
    empty.textContent = "没有符合当前角色筛选的 Hall 成员";
    groupMembersList.appendChild(empty);
  }

  groupMemberAddForm.classList.add("hidden");
  groupMemberAddBtn.disabled = groupMemberSaving;
  groupMemberAddSelect.innerHTML = "";
  if (canManage) {
    const availableMembers = members
      .filter((member) => !memberIds.has(member.id))
      .sort((a, b) => a.id.localeCompare(b.id, "zh-CN"));

    if (availableMembers.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "没有可添加的成员";
      groupMemberAddSelect.appendChild(option);
      groupMemberAddSelect.disabled = true;
      groupMemberAddBtn.disabled = true;
    } else {
      groupMemberAddSelect.disabled = groupMemberSaving;
      for (const member of availableMembers) {
        const option = document.createElement("option");
        option.value = member.id;
        option.textContent = `${member.id} · ${member.display_name}`;
        groupMemberAddSelect.appendChild(option);
      }
    }
    groupMemberAddRole.disabled = groupMemberSaving;
  }
  if (deleteGroupBtn) {
    deleteGroupBtn.classList.toggle("hidden", !canManage);
    deleteGroupBtn.disabled = groupMemberSaving;
  }

  renderAllMembersPanel(activeGroup, canManage);
}

function memberKindFromId(memberId) {
  return String(memberId || "").startsWith("agent:") ? "agent" : "human";
}

function toggleMemberKindFilter(kind) {
  if (!kind) return;
  selectedMemberKindFilters = new Set(selectedMemberKindFilters);
  if (selectedMemberKindFilters.has(kind)) {
    selectedMemberKindFilters.delete(kind);
  } else {
    selectedMemberKindFilters.add(kind);
  }
  renderGroupMembersPanel();
}

function renderAllMembersPanel(activeGroup, canManage) {
  if (!allMembersList) return;
  allMembersList.innerHTML = "";
  if (!activeGroup) return;

  const memberIds = getGroupMemberIds(activeGroup);
  // 只列 agent —— human 不在此列表展示（UI #3）。
  const agents = [...members].filter((member) => member.kind === "agent").sort((a, b) => {
    if (memberIds.has(a.id) !== memberIds.has(b.id)) {
      return memberIds.has(a.id) ? -1 : 1;
    }
    return a.id.localeCompare(b.id, "zh-CN");
  });

  for (const member of agents) {
    const isDisabled = Boolean(member.disabled_at);
    const row = document.createElement("div");
    row.className = `all-member-row${isDisabled ? " disabled" : ""}`;

    const body = document.createElement("div");
    body.className = "all-member-body";

    const name = document.createElement("div");
    name.className = "all-member-name";
    name.textContent = member.id === myId ? `${shortName(member.id)} (我)` : shortName(member.id);

    body.appendChild(name);
    if (isDisabled) {
      const badge = document.createElement("span");
      badge.className = "member-disabled-badge";
      badge.textContent = "已禁用";
      body.appendChild(badge);
    }

    const action = document.createElement("button");
    action.type = "button";
    action.className = memberIds.has(member.id) ? "member-added-pill" : "member-add-btn";
    action.textContent = memberIds.has(member.id) ? "已在 Hall" : "加入";
    // 已禁用的 agent 不能加入群
    action.disabled = memberIds.has(member.id) || !canManage || groupMemberSaving || isDisabled;
    action.addEventListener("click", () => saveGroupMember(member.id, "member"));

    row.appendChild(body);
    if (canManage) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = `member-toggle-btn ${isDisabled ? "enable" : "disable"}`;
      toggle.textContent = isDisabled ? "启用" : "禁用";
      toggle.disabled = groupMemberSaving;
      toggle.title = isDisabled ? "重新启用此 agent" : "全局禁用此 agent（拒绝其登录/收发，保留历史与群关系）";
      toggle.addEventListener("click", () => toggleMemberDisabled(member));
      row.appendChild(toggle);
    }
    row.appendChild(action);
    allMembersList.appendChild(row);
  }

  if (!agents.length) {
    const empty = document.createElement("div");
    empty.className = "member-empty-state";
    empty.textContent = "暂无 agent";
    allMembersList.appendChild(empty);
  }
}

async function toggleMemberDisabled(member) {
  if (!member || !canManageGroups() || groupMemberSaving) return;
  const disabling = !member.disabled_at;
  groupMemberSaving = true;
  renderGroupMembersPanel();
  try {
    const res = await apiFetch(`/api/members/${encodeURIComponent(member.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled: disabling }),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `${disabling ? "禁用" : "启用"}失败: ${res.status}`));
    }
    const updated = await res.json();
    const idx = members.findIndex((m) => m.id === updated.id);
    if (idx >= 0) members[idx] = updated;
    showGroupMembersError("");
  } catch (err) {
    console.error(err);
    showGroupMembersError(err.message);
  } finally {
    groupMemberSaving = false;
    renderGroupMembersPanel();
  }
}

function showAgentProfileError(message) {
  agentProfileError.textContent = message;
  agentProfileError.classList.toggle("hidden", !message);
}

function setAgentProfileSaving(isSaving) {
  agentProfileSaving = isSaving;
  agentProfileBusinessRole.disabled = isSaving;
  agentProfileIdentity.disabled = isSaving;
  agentProfileSoul.disabled = isSaving;
  agentProfileUser.disabled = isSaving;
  saveAgentProfileBtn.disabled = isSaving;
  cancelAgentProfileBtn.disabled = isSaving;
  closeAgentProfileBtn.disabled = isSaving;
  saveAgentProfileBtn.textContent = isSaving ? "保存中..." : "保存";
}

function closeAgentProfileEditor() {
  if (agentProfileSaving) return;
  agentProfileEditing = null;
  agentProfileOverlay.classList.add("hidden");
  showAgentProfileError("");
}

async function openAgentProfileEditor(membership) {
  const activeGroup = getActiveGroup();
  if (!membership || !activeGroup?.project_id || !canManageGroups()) return;

  agentProfileEditing = {
    groupId: activeGroup.id,
    projectId: activeGroup.project_id,
    memberId: membership.member_id,
    role: membership.role,
    businessRole: membership.business_role || "",
    decisionTier: membership.decision_tier || null,
  };
  agentProfileTitle.textContent = "编辑人设";
  agentProfileMember.textContent = `${membership.member_id} · ${activeGroup.name}`;
  agentProfileBusinessRole.value = membership.business_role || "";
  agentProfileIdentity.value = "";
  agentProfileSoul.value = "";
  agentProfileUser.value = "";
  showAgentProfileError("");
  agentProfileOverlay.classList.remove("hidden");
  setAgentProfileSaving(true);

  try {
    const res = await apiFetch(
      `/api/projects/${encodeURIComponent(activeGroup.project_id)}/agents/${encodeURIComponent(membership.member_id)}/profile`
    );
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `人设加载失败: ${res.status}`));
    }
    const profile = await res.json();
    agentProfileIdentity.value = profile.identity || "";
    agentProfileSoul.value = profile.soul || "";
    agentProfileUser.value = profile.user || "";
    showAgentProfileError("");
  } catch (err) {
    console.error(err);
    showAgentProfileError(err.message);
  } finally {
    setAgentProfileSaving(false);
    agentProfileBusinessRole.focus();
  }
}

async function saveAgentProfileEditor(event) {
  event.preventDefault();
  if (!agentProfileEditing || agentProfileSaving) return;

  const editing = agentProfileEditing;
  const nextBusinessRole = agentProfileBusinessRole.value.trim();
  setAgentProfileSaving(true);
  showAgentProfileError("");

  try {
    const profileRes = await apiFetch(
      `/api/projects/${encodeURIComponent(editing.projectId)}/agents/${encodeURIComponent(editing.memberId)}/profile`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          identity: agentProfileIdentity.value,
          soul: agentProfileSoul.value,
          user: agentProfileUser.value,
        }),
      }
    );
    if (!profileRes.ok) {
      throw new Error(await readErrorDetail(profileRes, `人设保存失败: ${profileRes.status}`));
    }

    if (nextBusinessRole !== editing.businessRole) {
      const roleRes = await apiFetch(
        `/api/groups/${encodeURIComponent(editing.groupId)}/members/${encodeURIComponent(editing.memberId)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role: editing.role,
            business_role: nextBusinessRole,
            decision_tier: editing.decisionTier,
          }),
        }
      );
      if (!roleRes.ok) {
        throw new Error(await readErrorDetail(roleRes, `业务角色保存失败: ${roleRes.status}`));
      }
      const group = await roleRes.json();
      replaceGroup(group);
    }

    agentProfileEditing = null;
    agentProfileOverlay.classList.add("hidden");
    showAgentProfileError("");
    showGroupMembersError("");
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
    setAgentProfileSaving(false);
    renderGroupMembersPanel();
  } catch (err) {
    console.error(err);
    showAgentProfileError(err.message);
  } finally {
    setAgentProfileSaving(false);
  }
}

async function updateGroupMetadataFromPanel(event) {
  event.preventDefault();
  const activeGroup = getActiveGroup();
  if (!activeGroup || groupMetaSaving) return;

  const name = groupMetaName.value.trim();
  const description = groupMetaDescription.value.trim();
  if (!name) {
    showGroupMembersError("请填写 Group 名称。");
    groupMetaName.focus();
    return;
  }

  groupMetaSaving = true;
  renderGroupMembersPanel();
  try {
    const res = await apiFetch(`/api/groups/${encodeURIComponent(activeGroup.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `Group 更新失败: ${res.status}`));
    }

    const group = await res.json();
    replaceGroup(group);
    groupMetaEditing = false;
    clearComposerStatus("room");
    showGroupMembersError("");
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
    updateMessagesEmptyState();
  } catch (err) {
    console.error(err);
    showGroupMembersError(err.message);
    renderGroupMembersPanel();
  } finally {
    groupMetaSaving = false;
    renderGroupMembersPanel();
  }
}

async function addGroupMemberFromPanel(event) {
  event.preventDefault();
  const memberId = groupMemberAddSelect.value;
  if (!memberId || groupMemberSaving || !activeGroupId) return;
  await saveGroupMember(memberId, groupMemberAddRole.value);
}

async function saveGroupMember(memberId, role) {
  groupMemberSaving = true;
  renderGroupMembersPanel();
  try {
    const res = await apiFetch(`/api/groups/${encodeURIComponent(activeGroupId)}/members/${encodeURIComponent(memberId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `成员更新失败: ${res.status}`));
    }

    const group = await res.json();
    replaceGroup(group);
    clearComposerStatus("room");
    showGroupMembersError("");
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
  } catch (err) {
    console.error(err);
    showGroupMembersError(err.message);
    renderGroupMembersPanel();
  } finally {
    groupMemberSaving = false;
    renderGroupMembersPanel();
  }
}

async function removeGroupMemberFromPanel(memberId) {
  if (!memberId || memberId === myId || groupMemberSaving || !activeGroupId) return;
  groupMemberSaving = true;
  renderGroupMembersPanel();
  try {
    const res = await apiFetch(`/api/groups/${encodeURIComponent(activeGroupId)}/members/${encodeURIComponent(memberId)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `成员移除失败: ${res.status}`));
    }

    const group = await res.json();
    replaceGroup(group);
    clearComposerStatus("room");
    showGroupMembersError("");
    renderRoomStrip();
    renderPresenceStrip();
    renderMentionDropdownIfOpen();
  } catch (err) {
    console.error(err);
    showGroupMembersError(err.message);
    renderGroupMembersPanel();
  } finally {
    groupMemberSaving = false;
    renderGroupMembersPanel();
  }
}

async function deleteActiveGroup() {
  const group = getActiveGroup();
  if (!group || !canManageGroups() || groupMemberSaving) return;
  const confirmed = window.confirm(
    `确定删除 Hall「${group.name}」(${group.id}) 吗？\n` +
    "将永久删除该 Hall 及其全部消息记录，不可恢复。"
  );
  if (!confirmed) return;

  groupMemberSaving = true;
  renderGroupMembersPanel();
  try {
    const res = await apiFetch(`/api/groups/${encodeURIComponent(group.id)}`, { method: "DELETE" });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `删除 Hall 失败: ${res.status}`));
    }
    groups = groups.filter((item) => item.id !== group.id);
    groupMembersOpen = false;
    showGroupMembersError("");
    if (activeGroupId === group.id) {
      setActiveGroup(null); // 重置时间线 / 本地存储 / 各处渲染
    } else {
      renderRoomStrip();
      renderPresenceStrip();
      renderMentionDropdownIfOpen();
    }
  } catch (err) {
    console.error(err);
    showGroupMembersError(err.message);
    renderGroupMembersPanel();
  } finally {
    groupMemberSaving = false;
    renderGroupMembersPanel();
  }
}

function getScopedMembers() {
  const activeGroup = getActiveGroup();
  if (!activeGroup) return members;

  const memberIds = getGroupMemberIds(activeGroup);
  return members.filter((member) => memberIds.has(member.id));
}

function messageBelongsToActiveRoom(message) {
  return activeGroupId
    ? message.group_id === activeGroupId
    : !message.group_id;
}

function addActiveGroupToParams(params) {
  if (activeGroupId) {
    params.set("group_id", activeGroupId);
  }
}

function applyActiveGroupToPayload(body) {
  if (activeGroupId) {
    body.group_id = activeGroupId;
  }
  return body;
}

function resetTimelineState({ clearSearch = true } = {}) {
  lastId = 0;
  oldestLoadedId = null;
  hasMoreHistory = false;
  historyLoading = false;
  if (clearSearch) {
    appliedHistoryQuery = "";
    historySearchInput.value = "";
  }
  renderedMessageIds = new Set();
  messageRecords = new Map();
  clearAllRevokeButtonTimers();
  clearReplyTarget();
  messagesEl.innerHTML = "";
  updateMessagesEmptyState();
  updateComposerPlaceholder();
  renderHistoryToolbar();
}

// ── Chat lifecycle ───────────────────────────────────────────────────
function startChat() {
  loggingOut = false;
  resetTimelineState();
  renderProjectStrip();
  renderRoomStrip();
  renderWorkspaceMode();
  renderPresenceStrip();
  if (pollTimer) clearInterval(pollTimer);
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  closeEventStream();
  if (blackboardOpen) {
    loadProjectTasks({ silent: true });
  } else {
    loadHistory();
  }
  connectWS();
  pollTimer = setInterval(pollMessages, 3000);
  if (taskPollTimer) clearInterval(taskPollTimer);
  taskPollTimer = setInterval(() => loadProjectTasks({ silent: true }), 5000);
}

async function loadHistory() {
  try {
    historyLoading = true;
    renderHistoryToolbar();
    const res = await apiFetch(buildHistoryRequestPath());
    if (!res.ok) {
      showComposerStatus("历史消息加载失败，请稍后重试。", "error", { source: "load", timeoutMs: 0 });
      return;
    }
    clearComposerStatus("load");
    const msgs = await res.json();
    if (msgs.length > 0) {
      await renderMessagesInChunks(msgs, HISTORY_RENDER_CHUNK);
      oldestLoadedId = msgs[0].id;
      lastId = Math.max(lastId, msgs[msgs.length - 1].id);
      hasMoreHistory = msgs.length === HISTORY_PAGE_SIZE;
      renderHistoryToolbar();
      scrollBottom();
    } else {
      oldestLoadedId = null;
      hasMoreHistory = false;
      updateMessagesEmptyState();
      renderHistoryToolbar();
    }
  } catch (err) {
    showComposerStatus(`历史消息加载失败: ${err.message}`, "error", { source: "load", timeoutMs: 0 });
  } finally {
    historyLoading = false;
    renderHistoryToolbar();
  }
}

async function pollMessages() {
  try {
    const res = await apiFetch(buildPollRequestPath());
    if (!res.ok) {
      showComposerStatus("消息同步失败，正在继续轮询。", "error", { source: "load", timeoutMs: 0 });
      return;
    }
    clearComposerStatus("load");
    const msgs = await res.json();
    if (msgs.length > 0) {
      const freshMessages = msgs.filter((message) => !renderedMessageIds.has(message.id));
      const visibleMessages = freshMessages.filter(matchesActiveHistoryQuery);
      const appendedCount = appendMessages(visibleMessages);
      lastId = Math.max(lastId, msgs[msgs.length - 1].id);
      if (appendedCount > 0) {
        maybePlayNotification(visibleMessages);
        scrollBottom();
      }
    }
  } catch (err) {
    showComposerStatus(`消息同步失败: ${err.message}`, "error", { source: "load", timeoutMs: 0 });
  }
}

function connectWS() {
  if (!apiKey) return;
  if (!("WebSocket" in window)) {
    connectEventStream({ fallback: false });
    return;
  }
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  setConnectionStatus(reconnectAttempts > 0 ? "reconnecting" : "connecting");
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws?token=${encodeURIComponent(apiKey)}`);

  ws.onopen = () => {
    const recovered = reconnectAttempts > 0;
    reconnectAttempts = 0;
    closeEventStream();
    setConnectionStatus("connected");
    if (recovered) {
      showComposerStatus("实时连接已恢复。", "info", { source: "ws", timeoutMs: 2500 });
    } else {
      clearComposerStatus("ws");
    }
  };

  ws.onmessage = (event) => {
    let data = null;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      console.warn("Ignoring invalid WS event", err);
      return;
    }
    if (data.type === "ping") {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "pong" }));
      }
      return;
    }
    handleRealtimeEvent(data);
  };

  ws.onclose = () => {
    ws = null;
    if (loggingOut) return;
    connectEventStream({ fallback: true });
    scheduleReconnect();
  };

  ws.onerror = () => {
    setConnectionStatus("polling");
    connectEventStream({ fallback: true });
  };
}

function scheduleReconnect() {
  if (reconnectTimer || loggingOut) return;
  reconnectAttempts += 1;
  const delay = Math.min(1000 * (2 ** (reconnectAttempts - 1)), 10000);
  setConnectionStatus("reconnecting");
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWS();
  }, delay);
}

function connectEventStream({ fallback = true } = {}) {
  if (!apiKey || loggingOut) return;
  if (!("EventSource" in window)) {
    setConnectionStatus("polling");
    return;
  }
  if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
    return;
  }

  const source = new EventSource(`${API}/api/events?token=${encodeURIComponent(apiKey)}`);
  eventSource = source;

  source.onopen = () => {
    if (source !== eventSource) return;
    setConnectionStatus(fallback ? "sseFallback" : "sse");
    if (fallback) {
      clearComposerStatus("ws");
    }
  };

  source.onerror = () => {
    if (source !== eventSource || loggingOut) return;
    setConnectionStatus("sseReconnecting");
  };

  for (const eventType of ["message", "revoke", "presence", "ping"]) {
    source.addEventListener(eventType, (event) => {
      if (source !== eventSource) return;
      handleServerSentEvent(eventType, event);
    });
  }
}

function closeEventStream() {
  if (!eventSource) return;
  eventSource.close();
  eventSource = null;
}

function handleServerSentEvent(type, event) {
  if (type === "ping") return;

  let payload = {};
  try {
    payload = event.data ? JSON.parse(event.data) : {};
  } catch (err) {
    console.warn("Ignoring invalid SSE event", err);
    return;
  }

  handleRealtimeEvent({ type, payload });
}

function handleRealtimeEvent(data) {
  if (data.type === "message") {
    const message = data.payload;
    if (messageBelongsToActiveRoom(message) && message.id > lastId) {
      lastId = message.id;
      const appendedCount = upsertMessages(matchesActiveHistoryQuery(message) ? [message] : [], "append");
      if (appendedCount > 0) {
        maybePlayNotification([message]);
        scrollBottom();
      }
    }
  } else if (data.type === "revoke") {
    applyRevokeEvent(data.payload);
  } else if (data.type === "presence") {
    hasPresenceSnapshot = true;
    onlineMemberIds = new Set(data.payload?.online_ids || []);
    renderPresenceStrip();
  }
}

// ── Send message / file ──────────────────────────────────────────────
sendBtn.addEventListener("click", sendMessage);
msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    if (!mentionDropdown.classList.contains("hidden")) {
      return;
    }
    e.preventDefault();
    sendMessage();
  }
});

async function sendMessage() {
  if (sending) return;

  const rawText = msgInput.value.trim();
  if (!rawText && !pendingFile) return;

  if (pendingFile) {
    await sendFileMessage(rawText || null);
    return;
  }

  const body = {
    type: "text",
    content: rawText,
  };
  applyActiveGroupToPayload(body);
  if (activeReplyTo) {
    body.reply_to = activeReplyTo.id;
  }

  sending = true;
  sendBtn.disabled = true;
  try {
    const res = await apiFetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `发送失败: ${res.status}`));
    }
    clearReplyTarget();
    resetComposerInput();
    clearComposerStatus("send");
  } catch (err) {
    console.error(err);
    showComposerStatus(err.message, "error", { source: "send", timeoutMs: 0 });
  } finally {
    sending = false;
    sendBtn.disabled = false;
  }
}

async function sendFileMessage(caption = null) {
  if (!pendingFile) return;

  sending = true;
  sendBtn.disabled = true;
  attachBtn.disabled = true;
  try {
    const uploaded = await uploadPendingFile();
    const res = await apiFetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(applyActiveGroupToPayload({
        type: "file",
        content: pendingFile.name,
        file_id: uploaded.file_id,
        caption,
        reply_to: activeReplyTo ? activeReplyTo.id : null,
      })),
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `文件消息发送失败: ${res.status}`));
    }
    clearPendingFile();
    clearReplyTarget();
    resetComposerInput();
    clearComposerStatus("send");
  } catch (err) {
    console.error(err);
    showComposerStatus(err.message, "error", { source: "send", timeoutMs: 0 });
  } finally {
    sending = false;
    sendBtn.disabled = false;
    attachBtn.disabled = false;
  }
}

async function uploadPendingFile() {
  const form = new FormData();
  form.append("file", pendingFile);

  const res = await apiFetch("/api/files", {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = `上传失败: ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) {
      // Ignore non-JSON error bodies.
    }
    throw new Error(detail);
  }
  return res.json();
}

// ── Render messages ──────────────────────────────────────────────────
function createMessageElement(m) {
  const isMine = m.from === myId;
  const isMentioned = m.to && m.to.includes(myId);

  const div = document.createElement("div");
  div.id = "msg-" + m.id;
  div.className = `msg-bubble rounded-lg px-3 py-2 ${isMine ? "mine" : "others"} ${isMentioned ? "msg-mentioned" : ""}`;
  div.dataset.messageId = String(m.id);
  div.dataset.from = m.from;
  div.dataset.createdAt = m.created_at;
  div.dataset.revoked = m.revoked ? "true" : "false";

  const header = document.createElement("div");
  header.className = "text-xs mb-1 " + (isMine ? "text-blue-300" : "text-gray-400");
  const time = new Date(m.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  header.textContent = `${shortName(m.from)}  ${time}`;

  div.appendChild(header);
  const replyRef = renderReplyReference(m.reply_to, m);
  if (replyRef) {
    div.appendChild(replyRef);
  }

  if (m.revoked) {
    div.classList.remove("mine", "others", "msg-mentioned");
    div.classList.add("bg-gray-700", "text-gray-300", "border", "border-gray-600");
    const placeholder = document.createElement("div");
    placeholder.className = "text-sm";
    placeholder.textContent = `${shortName(m.revoked_by || m.from)} 撤回了一条消息`;
    div.appendChild(placeholder);
  } else if (m.type === "file" && m.file_id) {
    div.appendChild(renderFileCard(m));
  } else {
    const content = document.createElement("div");
    content.className = "rich-text text-sm";
    renderRichText(content, m.content || "");
    div.appendChild(content);
  }

  const actions = renderMessageActions(m);
  if (actions) {
    div.appendChild(actions);
  }

  return div;
}

function renderMessageActions(message) {
  const canReply = !message.revoked;
  const canRevoke = canRevokeMessage(message);
  if (!canReply && !canRevoke) {
    clearRevokeButtonTimer(message.id);
    return null;
  }

  const actions = document.createElement("div");
  actions.className = "message-actions";

  if (canReply) {
    const replyBtn = document.createElement("button");
    replyBtn.className = "message-action-btn";
    replyBtn.type = "button";
    replyBtn.textContent = "回复";
    replyBtn.addEventListener("click", () => activateReplyTarget(message));
    actions.appendChild(replyBtn);
  }

  if (!canRevoke) {
    clearRevokeButtonTimer(message.id);
    return actions;
  }

  const revokeBtn = document.createElement("button");
  revokeBtn.className = "message-action-btn";
  revokeBtn.type = "button";
  revokeBtn.textContent = "撤回";
  revokeBtn.addEventListener("click", () => revokeMessage(message.id, revokeBtn));
  actions.appendChild(revokeBtn);

  scheduleRevokeButtonRefresh(message);
  return actions;
}

function renderReplyReference(replyTo, message = null) {
  if (!replyTo || !replyTo.id) return null;

  const reply = document.createElement("div");
  reply.className = "message-reply";
  const compact = shouldUseCompactReplyReference(replyTo, message);
  if (compact) {
    reply.classList.add("compact");
  }
  const targetLoaded = Boolean(document.getElementById("msg-" + replyTo.id));
  if (targetLoaded) {
    reply.classList.add("clickable");
    reply.title = "点击跳转到原消息";
    reply.addEventListener("click", () => jumpToMessage(replyTo.id));
  }

  if (compact) {
    const summary = document.createElement("div");
    summary.className = "message-reply-summary";
    summary.textContent = `${shortName(message.from || "unknown")} 回复 ${shortName(replyTo.from_id || "unknown")}`;
    reply.appendChild(summary);
    return reply;
  }

  const label = document.createElement("div");
  label.className = "message-reply-label";
  label.textContent = shortName(replyTo.from_id || "unknown");
  const preview = document.createElement("div");
  preview.className = "message-reply-preview";
  preview.textContent = replyPreviewText(replyTo);

  reply.appendChild(label);
  reply.appendChild(preview);
  return reply;
}

function shouldUseCompactReplyReference(replyTo, message) {
  if (!replyTo || !message || !message.from || !replyTo.from_id) return false;
  if (message.from === replyTo.from_id) return false;

  const recipients = Array.isArray(message.to) ? message.to : null;
  if (!recipients || recipients.length === 0) {
    return true;
  }
  return recipients.includes(replyTo.from_id);
}

function replyPreviewText(replyTo) {
  if (!replyTo) return "";
  if (replyTo.revoked) {
    return "[原消息已撤回]";
  }
  if (replyTo.preview) {
    return replyTo.preview;
  }
  if (replyTo.type === "file") {
    return "[文件]";
  }
  return "[消息]";
}

function upsertMessages(messages, position = "append") {
  const fragment = document.createDocumentFragment();
  let insertedCount = 0;

  for (const message of messages) {
    const existing = document.getElementById("msg-" + message.id);
    messageRecords.set(message.id, message);
    if (existing) {
      existing.replaceWith(createMessageElement(message));
      continue;
    }

    fragment.appendChild(createMessageElement(message));
    renderedMessageIds.add(message.id);
    insertedCount += 1;
  }

  if (insertedCount > 0) {
    if (position === "prepend") {
      messagesEl.prepend(fragment);
    } else {
      messagesEl.appendChild(fragment);
    }
  }

  updateMessagesEmptyState();
  return insertedCount;
}

function appendMessages(messages) {
  return upsertMessages(messages, "append");
}

function prependMessages(messages) {
  return upsertMessages(messages, "prepend");
}

async function renderMessagesInChunks(messages, chunkSize = HISTORY_RENDER_CHUNK) {
  for (let index = 0; index < messages.length; index += chunkSize) {
    appendMessages(messages.slice(index, index + chunkSize));
    if (index + chunkSize < messages.length) {
      await nextFrame();
    }
  }
}

function nextFrame() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

function buildHistoryRequestPath(before = null) {
  const params = new URLSearchParams();
  params.set("limit", String(HISTORY_PAGE_SIZE));
  addActiveGroupToParams(params);
  if (before !== null) {
    params.set("before", String(before));
  }
  if (appliedHistoryQuery) {
    params.set("q", appliedHistoryQuery);
  }
  return `/api/messages?${params.toString()}`;
}

function buildPollRequestPath() {
  const params = new URLSearchParams();
  params.set("since", String(lastId));
  params.set("limit", "100");
  addActiveGroupToParams(params);
  return `/api/messages?${params.toString()}`;
}

async function loadOlderMessages() {
  if (historyLoading || !hasMoreHistory || oldestLoadedId === null) return;

  historyLoading = true;
  renderHistoryToolbar();
  const previousScrollHeight = messagesEl.scrollHeight;
  const previousScrollTop = messagesEl.scrollTop;

  try {
    const res = await apiFetch(buildHistoryRequestPath(oldestLoadedId));
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `历史分页加载失败: ${res.status}`));
    }

    const msgs = await res.json();
    if (msgs.length === 0) {
      hasMoreHistory = false;
      renderHistoryToolbar();
      return;
    }

    const prependedCount = prependMessages(msgs);
    oldestLoadedId = msgs[0].id;
    hasMoreHistory = msgs.length === HISTORY_PAGE_SIZE;
    renderHistoryToolbar();

    if (prependedCount > 0) {
      requestAnimationFrame(() => {
        const heightDelta = messagesEl.scrollHeight - previousScrollHeight;
        messagesEl.scrollTop = previousScrollTop + heightDelta;
      });
    }
  } catch (err) {
    showComposerStatus(err.message, "error", { source: "load", timeoutMs: 0 });
  } finally {
    historyLoading = false;
    renderHistoryToolbar();
  }
}

async function applyHistorySearch() {
  const nextQuery = historySearchInput.value.trim();
  if (nextQuery === appliedHistoryQuery) return;
  appliedHistoryQuery = nextQuery;
  await reloadHistoryView();
}

async function clearHistorySearch() {
  if (!appliedHistoryQuery && !historySearchInput.value.trim()) return;
  historySearchInput.value = "";
  appliedHistoryQuery = "";
  await reloadHistoryView();
}

async function reloadHistoryView() {
  oldestLoadedId = null;
  hasMoreHistory = false;
  renderedMessageIds = new Set();
  messageRecords = new Map();
  clearAllRevokeButtonTimers();
  messagesEl.innerHTML = "";
  updateMessagesEmptyState();
  renderHistoryToolbar();
  await loadHistory();
}

function updateMessagesEmptyState() {
  const hasMessages = renderedMessageIds.size > 0;
  const activeGroup = getActiveGroup();
  messagesEl.classList.toggle("is-empty", !hasMessages);
  messagesEl.dataset.emptyText = appliedHistoryQuery
    ? emptySearchText
    : activeGroup
      ? `${activeGroup.name} Hall 暂无消息，发送第一条消息开始同步。`
      : emptyTimelineText;
}

function renderFileCard(message) {
  const card = document.createElement("div");
  card.className = "file-card";

  const meta = document.createElement("div");
  meta.className = "file-card-meta";

  const name = document.createElement("div");
  name.className = "file-card-name";
  name.textContent = message.filename || message.content || `文件 ${message.file_id}`;

  const caption = document.createElement("div");
  caption.className = "file-card-caption rich-text";
  if (message.caption) {
    renderRichText(caption, message.caption);
  } else {
    caption.classList.add("hidden");
  }

  const size = document.createElement("div");
  size.className = "file-card-size";
  size.textContent = formatFileMeta(message);

  const status = document.createElement("div");
  status.className = "file-card-status hidden";

  const downloadBtn = document.createElement("button");
  downloadBtn.className = "file-download-btn";
  downloadBtn.textContent = "下载";
  downloadBtn.addEventListener("click", async () => {
    downloadBtn.disabled = true;
    const originalText = downloadBtn.textContent;
    downloadBtn.textContent = "下载中...";
    try {
      await downloadFile(message.file_id, message.filename || message.content || "download");
      downloadBtn.textContent = "已下载";
      clearFileCardStatus(card, status);
      clearComposerStatus("send");
    } catch (err) {
      console.error(err);
      if (isExpiredFileError(err)) {
        markFileCardExpired(card, status, downloadBtn);
        showComposerStatus("文件已过期，无法下载。", "error", { source: "send", timeoutMs: 0 });
        return;
      }

      showComposerStatus(err.message, "error", { source: "send", timeoutMs: 0 });
      downloadBtn.textContent = originalText;
    } finally {
      if (downloadBtn.dataset.expired === "true") {
        return;
      }
      setTimeout(() => {
        downloadBtn.disabled = false;
        downloadBtn.textContent = "下载";
      }, 800);
    }
  });

  meta.appendChild(name);
  meta.appendChild(caption);
  meta.appendChild(size);
  meta.appendChild(status);
  card.appendChild(meta);
  card.appendChild(downloadBtn);
  return card;
}

async function downloadFile(fileId, fallbackName) {
  const res = await apiFetch(`/api/files/${encodeURIComponent(fileId)}`);
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `下载失败: ${res.status}`));
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = parseDownloadName(res.headers.get("Content-Disposition")) || fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function parseDownloadName(contentDisposition) {
  if (!contentDisposition) return "";

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1]);

  const asciiMatch = contentDisposition.match(/filename="([^"]+)"/i);
  return asciiMatch ? asciiMatch[1] : "";
}

function shortName(id) {
  return id.includes(":") ? id.split(":")[1] : id;
}

function canRevokeMessage(message) {
  if (!message || message.revoked || message.from !== myId) return false;
  const createdAtMs = Date.parse(message.created_at);
  if (Number.isNaN(createdAtMs)) return false;
  return Date.now() < createdAtMs + getRevokeWindowSec() * 1000;
}

function scheduleRevokeButtonRefresh(message) {
  clearRevokeButtonTimer(message.id);
  const createdAtMs = Date.parse(message.created_at);
  if (Number.isNaN(createdAtMs)) return;

  const delay = createdAtMs + getRevokeWindowSec() * 1000 - Date.now();
  if (delay <= 0) return;

  const timer = setTimeout(() => {
    revokeButtonTimers.delete(message.id);
    const current = messageRecords.get(message.id);
    if (current) {
      upsertMessages([current], "append");
    }
  }, delay + 50);
  revokeButtonTimers.set(message.id, timer);
}

function clearRevokeButtonTimer(messageId) {
  const timer = revokeButtonTimers.get(messageId);
  if (timer) {
    clearTimeout(timer);
    revokeButtonTimers.delete(messageId);
  }
}

function clearAllRevokeButtonTimers() {
  for (const timer of revokeButtonTimers.values()) {
    clearTimeout(timer);
  }
  revokeButtonTimers.clear();
}

async function revokeMessage(messageId, buttonEl) {
  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "撤回中...";
  }

  try {
    const res = await apiFetch(`/api/messages/${messageId}/revoke`, {
      method: "POST",
    });
    if (!res.ok) {
      throw new Error(await readErrorDetail(res, `撤回失败: ${res.status}`));
    }

    const payload = await res.json();
    applyRevokeEvent(payload);
    clearComposerStatus("send");
  } catch (err) {
    console.error(err);
    showComposerStatus(err.message, "error", { source: "send", timeoutMs: 0 });
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.textContent = "撤回";
    }
  }
}

function applyRevokeEvent(payload) {
  const messageId = Number(payload?.id);
  if (!Number.isInteger(messageId)) return;

  const current = messageRecords.get(messageId);
  if (current) {
    const updated = {
      ...current,
      revoked: true,
      revoked_at: payload.revoked_at || current.revoked_at || new Date().toISOString(),
      revoked_by: payload.revoked_by || current.revoked_by || current.from,
      content: null,
      caption: null,
      filename: null,
      size_bytes: null,
      mime: null,
    };
    messageRecords.set(messageId, updated);
    clearRevokeButtonTimer(messageId);
    upsertMessages([updated], "append");
  }

  updateReplyReferencesForRevokedMessage(messageId);
  if (activeReplyTo && activeReplyTo.id === messageId) {
    activeReplyTo = {
      ...activeReplyTo,
      preview: null,
      revoked: true,
    };
    renderReplyBar();
  }
}

function renderHistoryToolbar() {
  historyToolbar.classList.remove("hidden");
  historySearchBtn.disabled = historyLoading;
  historyClearBtn.disabled = historyLoading || (!appliedHistoryQuery && !historySearchInput.value.trim());
  loadOlderBtn.disabled = historyLoading || !hasMoreHistory || oldestLoadedId === null;

  if (historyLoading) {
    loadOlderBtn.textContent = "加载中…";
    historyStatus.textContent = appliedHistoryQuery ? `正在搜索“${appliedHistoryQuery}”` : "正在拉取更早消息";
    return;
  }

  loadOlderBtn.textContent = "加载更早消息";
  if (oldestLoadedId === null) {
    historyStatus.textContent = appliedHistoryQuery ? `未找到“${appliedHistoryQuery}”相关消息` : "暂无历史消息";
    return;
  }

  if (appliedHistoryQuery) {
    historyStatus.textContent = hasMoreHistory
      ? `搜索“${appliedHistoryQuery}”中，当前已加载到消息 #${oldestLoadedId}`
      : `“${appliedHistoryQuery}”的结果已全部加载`;
    return;
  }

  historyStatus.textContent = hasMoreHistory
    ? `当前已加载到消息 #${oldestLoadedId}`
    : "已到最早消息";
}

function renderPresenceStrip() {
  if (!members.length || !myId) return;

  presenceStrip.classList.remove("hidden");
  presenceMembers.innerHTML = "";
  const scopedMembers = getScopedMembers();
  const scopedMemberIds = new Set(scopedMembers.map((member) => member.id));
  const onlineScopedCount = Array.from(onlineMemberIds).filter((memberId) => scopedMemberIds.has(memberId)).length;

  if (!hasPresenceSnapshot) {
    presenceSummary.textContent = "在线成员同步中…";
  } else {
    presenceSummary.textContent = activeGroupId
      ? `Hall 在线 ${onlineScopedCount}/${scopedMembers.length}`
      : `在线 ${onlineScopedCount}/${scopedMembers.length}`;
  }
  if (activeGroupId && roomDescription) {
    const activeGroup = getActiveGroup();
    roomDescription.textContent = activeGroup
      ? `${activeGroup.id} · Hall 在线 ${onlineScopedCount}/${scopedMembers.length} · @ 开头提醒成员，同组可见${activeGroup.description ? ` · ${activeGroup.description}` : ""}`
      : roomDescription.textContent;
  }

  const sortedMembers = [...scopedMembers].sort((a, b) => {
    if (a.id === myId) return -1;
    if (b.id === myId) return 1;
    return a.id.localeCompare(b.id, "zh-CN");
  });

  for (const member of sortedMembers) {
    const chip = document.createElement("div");
    const isOnline = onlineMemberIds.has(member.id);
    chip.className = `presence-chip ${isOnline ? "online" : "offline"} ${member.id === myId ? "self" : ""}`;
    chip.title = `${member.display_name} (${member.id})`;

    const dot = document.createElement("span");
    dot.className = "presence-dot";

    const label = document.createElement("span");
    label.className = "presence-label";
    label.textContent = member.id === myId ? `${shortName(member.id)} (我)` : shortName(member.id);

    chip.appendChild(dot);
    chip.appendChild(label);
    presenceMembers.appendChild(chip);
  }
  renderGroupMembersPanel();
}

function maybePlayNotification(messages) {
  if (!messages.some(shouldNotifyForMessage)) return;

  const now = Date.now();
  if (now - lastNotificationAt < NOTIFICATION_SOUND_COOLDOWN_MS) return;
  lastNotificationAt = now;
  playNotificationSound();
}

function shouldNotifyForMessage(message) {
  return message.from !== myId;
}

function matchesActiveHistoryQuery(message) {
  if (!appliedHistoryQuery) return true;
  if (message.revoked) return false;

  const query = appliedHistoryQuery.toLowerCase();
  return [message.content, message.caption, message.filename, message.reply_to?.preview]
    .filter((value) => typeof value === "string" && value)
    .some((value) => value.toLowerCase().includes(query));
}

function playNotificationSound() {
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return;

  if (!notificationAudioContext) {
    notificationAudioContext = new AudioContextCtor();
  }

  if (notificationAudioContext.state === "suspended") {
    notificationAudioContext.resume()
      .then(() => triggerNotificationTone(notificationAudioContext))
      .catch(() => {});
    return;
  }

  triggerNotificationTone(notificationAudioContext);
}

function triggerNotificationTone(audioContext) {
  try {
    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, now);
    oscillator.frequency.exponentialRampToValueAtTime(660, now + 0.18);

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.035, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);

    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.2);
  } catch (_) {
    // Ignore audio API failures; sound is best-effort only.
  }
}

function configureMarkdownRenderer() {
  if (!window.marked) {
    return null;
  }

  window.marked.setOptions({
    gfm: true,
    breaks: true,
  });

  return window.marked;
}

function renderRichText(container, text) {
  container.innerHTML = renderMarkdown(text);
  highlightCodeBlocks(container);
  decorateMentions(container);
  decorateSearchHits(container);
}

function renderMarkdown(text) {
  if (!text) return "";

  if (!markdownRenderer) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  if (!window.DOMPurify) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  return window.DOMPurify.sanitize(markdownRenderer.parse(text), {
    USE_PROFILES: { html: true },
  });
}

function highlightCodeBlocks(container) {
  if (!window.hljs) return;

  for (const block of container.querySelectorAll("pre code")) {
    window.hljs.highlightElement(block);
  }
}

function decorateMentions(container) {
  const memberIds = new Set(members.map((member) => member.id));
  const textNodes = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent) continue;
    if (parent.closest("code, pre, .mention")) continue;
    textNodes.push(node);
  }

  for (const node of textNodes) {
    const fragment = buildMentionFragment(node.textContent || "", memberIds);
    if (fragment) {
      node.parentNode.replaceChild(fragment, node);
    }
  }
}

function decorateSearchHits(container) {
  const query = appliedHistoryQuery.trim();
  if (!query) return;

  const textNodes = [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent) continue;
    if (parent.closest("code, pre, mark, .mention")) continue;
    textNodes.push(node);
  }

  for (const node of textNodes) {
    const fragment = buildSearchHitFragment(node.textContent || "", query);
    if (fragment) {
      node.parentNode.replaceChild(fragment, node);
    }
  }
}

function buildSearchHitFragment(text, query) {
  const needle = query.toLowerCase();
  const source = text.toLowerCase();
  if (!needle || !source.includes(needle)) return null;

  const fragment = document.createDocumentFragment();
  let cursor = 0;
  let index = source.indexOf(needle, cursor);
  while (index !== -1) {
    if (index > cursor) {
      fragment.appendChild(document.createTextNode(text.slice(cursor, index)));
    }
    const mark = document.createElement("mark");
    mark.textContent = text.slice(index, index + query.length);
    fragment.appendChild(mark);
    cursor = index + query.length;
    index = source.indexOf(needle, cursor);
  }
  if (cursor < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(cursor)));
  }
  return fragment;
}

function buildMentionFragment(text, memberIds) {
  mentionPattern.lastIndex = 0;
  let lastIndex = 0;
  let match = null;
  let hasMention = false;
  const fragment = document.createDocumentFragment();

  while ((match = mentionPattern.exec(text)) !== null) {
    const [full, memberId] = match;
    if (!memberIds.has(memberId) && !isAllMentionToken(memberId)) {
      continue;
    }

    hasMention = true;
    if (match.index > lastIndex) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }

    const span = document.createElement("span");
    span.className = "mention";
    span.textContent = full;
    fragment.appendChild(span);
    lastIndex = match.index + full.length;
  }

  if (!hasMention) {
    return null;
  }

  if (lastIndex < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
  }

  return fragment;
}

function isAllMentionToken(token) {
  return token === ALL_MENTION_ID || token.toLowerCase() === "all";
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── File picker / drag and drop ─────────────────────────────────────
attachBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files[0]) {
    setPendingFile(fileInput.files[0]);
  }
});
clearFileBtn.addEventListener("click", clearPendingFile);
clearReplyBtn.addEventListener("click", clearReplyTarget);

composer.addEventListener("dragenter", (e) => {
  e.preventDefault();
  e.stopPropagation();
  dragDepth += 1;
  dropHint.classList.remove("hidden");
});

composer.addEventListener("dragover", (e) => {
  e.preventDefault();
  e.stopPropagation();
  dropHint.classList.remove("hidden");
});

["dragleave", "dragend"].forEach((eventName) => {
  composer.addEventListener(eventName, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      dropHint.classList.add("hidden");
    }
  });
});

composer.addEventListener("drop", (e) => {
  e.preventDefault();
  e.stopPropagation();
  dragDepth = 0;
  dropHint.classList.add("hidden");
  const files = e.dataTransfer && e.dataTransfer.files;
  if (files && files[0]) {
    setPendingFile(files[0]);
  }
});

window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

function setPendingFile(file) {
  if (appConfig.max_upload_bytes && file.size > appConfig.max_upload_bytes) {
    showComposerStatus(
      `文件过大：${formatBytes(file.size)}，当前上限 ${formatBytes(appConfig.max_upload_bytes)}`,
      "error",
      { source: "send", timeoutMs: 0 },
    );
    return;
  }
  pendingFile = file;
  pendingFileName.textContent = file.name;
  pendingFileMeta.textContent = formatBytes(file.size);
  pendingFileEl.classList.remove("hidden");
  clearComposerStatus("send");
  updateComposerPlaceholder();
}

function clearPendingFile() {
  pendingFile = null;
  fileInput.value = "";
  pendingFileEl.classList.add("hidden");
  pendingFileName.textContent = "";
  pendingFileMeta.textContent = "";
  updateComposerPlaceholder();
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatFileMeta(message) {
  const parts = [];
  if (typeof message.size_bytes === "number") {
    parts.push(formatBytes(message.size_bytes));
  }
  if (message.mime) {
    parts.push(message.mime);
  }
  return parts.join(" · ") || "文件";
}

function updateComposerPlaceholder() {
  if (activeGroupId) {
    msgInput.placeholder = pendingFile
      ? "输入文件附言… Hall 内 @ 只用于提醒成员"
      : "输入 Hall 消息… @ 成员会提醒他，同组成员都可见";
    return;
  }
  msgInput.placeholder = pendingFile ? fileComposerPlaceholder : defaultComposerPlaceholder;
}

function activateReplyTarget(message) {
  activeReplyTo = {
    id: message.id,
    from_id: message.from,
    preview: message.revoked ? null : buildReplyPreviewFromMessage(message),
    type: message.type,
    revoked: Boolean(message.revoked),
  };
  renderReplyBar();
  msgInput.focus();
}

function clearReplyTarget() {
  activeReplyTo = null;
  renderReplyBar();
}

function renderReplyBar() {
  if (!activeReplyTo) {
    replyBar.classList.add("hidden");
    replyAuthor.textContent = "";
    replyPreview.textContent = "";
    return;
  }

  replyAuthor.textContent = `回复 ${shortName(activeReplyTo.from_id || "unknown")}`;
  replyPreview.textContent = replyPreviewText(activeReplyTo);
  replyBar.classList.remove("hidden");
}

function buildReplyPreviewFromMessage(message) {
  if (!message) return "";
  const raw = message.type === "file"
    ? (message.filename || message.content || "[文件]")
    : (message.content || "");
  return raw.replace(/\s+/g, " ").trim().slice(0, 80) || (message.type === "file" ? "[文件]" : "[消息]");
}

function updateReplyReferencesForRevokedMessage(messageId) {
  const impacted = [];
  for (const [id, message] of messageRecords.entries()) {
    if (message.reply_to && Number(message.reply_to.id) === messageId) {
      const updated = {
        ...message,
        reply_to: {
          ...message.reply_to,
          preview: null,
          revoked: true,
        },
      };
      messageRecords.set(id, updated);
      impacted.push(updated);
    }
  }

  if (impacted.length > 0) {
    upsertMessages(impacted, "append");
  }
}

function jumpToMessage(messageId) {
  const target = document.getElementById("msg-" + messageId);
  if (!target) return;

  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("jump-highlight");
  if (jumpHighlightTimer) {
    clearTimeout(jumpHighlightTimer);
  }
  jumpHighlightTimer = setTimeout(() => {
    target.classList.remove("jump-highlight");
    jumpHighlightTimer = null;
  }, JUMP_HIGHLIGHT_MS);
}

function getRevokeWindowSec() {
  return Number(appConfig.revoke_window_sec || DEFAULT_REVOKE_WINDOW_SEC);
}

async function loadRuntimeConfig() {
  try {
    const res = await fetch(API + "/api/config");
    if (!res.ok) {
      throw new Error(`config ${res.status}`);
    }
    const config = await res.json();
    appConfig = {
      ...appConfig,
      ...config,
    };
  } catch (err) {
    console.warn("Failed to load runtime config", err);
  }
}

function resetComposerInput() {
  msgInput.value = "";
  mentionDropdown.classList.add("hidden");
  resizeComposerInput();
}

function resizeComposerInput() {
  msgInput.style.height = "auto";
  const maxHeight = 240;
  msgInput.style.height = `${Math.min(msgInput.scrollHeight, maxHeight)}px`;
  msgInput.style.overflowY = msgInput.scrollHeight > maxHeight ? "auto" : "hidden";
}

function setConnectionStatus(state) {
  const config = connectionStates[state] || connectionStates.polling;
  connectionStatus.textContent = config.label;
  connectionStatus.className = `text-xs px-2 py-1 rounded-full border ${config.classes}`;
  connectionStatus.classList.remove("hidden");
}

function showComposerStatus(message, kind = "info", { source = "general", timeoutMs = 4000 } = {}) {
  clearTimeout(statusTimer);
  statusTimer = null;
  composerStatus.dataset.source = source;
  composerStatus.textContent = message;
  composerStatus.className = `mb-3 px-3 py-2 rounded-lg text-sm border ${composerStatusClasses[kind] || composerStatusClasses.info}`;
  composerStatus.classList.remove("hidden");
  if (timeoutMs > 0) {
    statusTimer = setTimeout(() => clearComposerStatus(source), timeoutMs);
  }
}

function clearComposerStatus(source = null) {
  if (source && composerStatus.dataset.source !== source) return;
  clearTimeout(statusTimer);
  statusTimer = null;
  composerStatus.textContent = "";
  composerStatus.dataset.source = "";
  composerStatus.classList.add("hidden");
}

function setInputErrorState(hasError) {
  msgInput.classList.toggle("border-red-500", hasError);
  msgInput.classList.toggle("focus:border-red-500", hasError);
  msgInput.classList.toggle("border-gray-600", !hasError);
  msgInput.classList.toggle("focus:border-blue-500", !hasError);
}

function isExpiredFileError(err) {
  return err && err.message === "file expired";
}

function markFileCardExpired(card, statusEl, buttonEl) {
  card.classList.add("file-card-expired");
  statusEl.textContent = "文件已过期，无法下载";
  statusEl.classList.remove("hidden");
  buttonEl.disabled = true;
  buttonEl.dataset.expired = "true";
  buttonEl.textContent = "已过期";
}

function clearFileCardStatus(card, statusEl) {
  card.classList.remove("file-card-expired");
  statusEl.textContent = "";
  statusEl.classList.add("hidden");
}

async function readErrorDetail(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string" && body.detail) {
      return body.detail;
    }
    if (Array.isArray(body?.detail) && body.detail.length > 0) {
      return body.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    }
  } catch (_) {
    // Ignore non-JSON error bodies.
  }
  return fallback;
}

// ── @ Autocomplete ───────────────────────────────────────────────────
let mentionStart = -1;

msgInput.addEventListener("input", () => {
  setInputErrorState(false);
  resizeComposerInput();
  const val = msgInput.value;
  const cursor = msgInput.selectionStart;
  const before = val.substring(0, cursor);
  const mentionContext = before.match(/^\s*(?:@[^\s]+\s+)*@([^\s]*)$/);

  if (mentionContext) {
    const query = mentionContext[1].toLowerCase();
    mentionStart = before.lastIndexOf("@");
    const activeGroup = getActiveGroup();

    const filtered = getScopedMembers().filter(
      (m) => m.id.toLowerCase().includes(query) || m.display_name.toLowerCase().includes(query)
    );
    const canMentionAll = Boolean(activeGroup) && (query === "" || ALL_MENTION_ID.includes(query) || "all".includes(query));

    if (canMentionAll || filtered.length > 0) {
      mentionDropdown.innerHTML = "";
      if (canMentionAll) {
        const li = document.createElement("li");
        li.textContent = "所有人（全体成员）";
        li.dataset.id = ALL_MENTION_ID;
        li.addEventListener("mousedown", (event) => event.preventDefault());
        li.addEventListener("click", () => completeMention(ALL_MENTION_ID));
        mentionDropdown.appendChild(li);
      }
      for (const m of filtered) {
        const li = document.createElement("li");
        li.textContent = `${m.id} (${m.display_name})`;
        li.dataset.id = m.id;
        li.addEventListener("mousedown", (event) => event.preventDefault());
        li.addEventListener("click", () => completeMention(m.id));
        mentionDropdown.appendChild(li);
      }
      mentionDropdown.classList.remove("hidden");
      return;
    }
  }

  mentionDropdown.classList.add("hidden");
});

function renderMentionDropdownIfOpen() {
  if (mentionDropdown.classList.contains("hidden")) return;
  mentionDropdown.classList.add("hidden");
}

msgInput.addEventListener("keydown", (e) => {
  if (mentionDropdown.classList.contains("hidden")) return;

  const items = mentionDropdown.querySelectorAll("li");
  const active = mentionDropdown.querySelector("li.active");
  let idx = Array.from(items).indexOf(active);

  if (e.key === "ArrowDown") {
    e.preventDefault();
    if (active) active.classList.remove("active");
    idx = (idx + 1) % items.length;
    items[idx].classList.add("active");
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (active) active.classList.remove("active");
    idx = idx <= 0 ? items.length - 1 : idx - 1;
    items[idx].classList.add("active");
  } else if (e.key === "Tab" || e.key === "Enter") {
    e.preventDefault();
    const sel = active || items[0];
    if (sel) completeMention(sel.dataset.id);
  } else if (e.key === "Escape") {
    mentionDropdown.classList.add("hidden");
  }
});

function completeMention(memberId) {
  const val = msgInput.value;
  const after = val.substring(msgInput.selectionStart);
  const nextValue = val.substring(0, mentionStart) + "@" + memberId + " " + after;
  const nextCursor = mentionStart + memberId.length + 2;
  msgInput.value = nextValue;
  mentionDropdown.classList.add("hidden");
  resizeComposerInput();
  msgInput.focus();
  msgInput.setSelectionRange(nextCursor, nextCursor);
}

// ── API helper ───────────────────────────────────────────────────────
function apiFetch(path, opts = {}) {
  opts.headers = opts.headers || {};
  opts.headers["X-API-Key"] = apiKey;
  return fetch(API + path, opts);
}
