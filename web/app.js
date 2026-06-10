// TALK — Minimal Web UI
"use strict";

const API = "";
const mentionPattern = /@([^\s]+)/g;
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
const roomTitle = document.getElementById("room-title");
const roomDescription = document.getElementById("room-description");
const globalRoomBtn = document.getElementById("global-room-btn");
const groupRoomList = document.getElementById("group-room-list");
const hallFilterInput = document.getElementById("hall-filter-input");
const refreshGroupsBtn = document.getElementById("refresh-groups-btn");
const toggleGroupCreateBtn = document.getElementById("toggle-group-create-btn");
const toggleGroupMembersBtn = document.getElementById("toggle-group-members-btn");
const groupCreatePanel = document.getElementById("group-create-panel");
const groupCreateName = document.getElementById("group-create-name");
const groupCreateId = document.getElementById("group-create-id");
const groupCreateDescription = document.getElementById("group-create-description");
const groupCreateMembers = document.getElementById("group-create-members");
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
const allMembersList = document.getElementById("all-members-list");
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
const LOCAL_API_KEY_STORAGE = "talk_api_key";
const SESSION_API_KEY_STORAGE = "talk_session_api_key";
const ACTIVE_GROUP_STORAGE = "talk_active_group_id";

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
refreshGroupsBtn.addEventListener("click", refreshGroups);
toggleGroupCreateBtn.addEventListener("click", () => setGroupCreateOpen(!groupCreateOpen));
toggleGroupMembersBtn.addEventListener("click", () => {
  setGroupMembersOpen(true);
  if (groupMemberAddSelect && !groupMemberAddSelect.disabled) {
    groupMemberAddSelect.focus();
  }
});
cancelGroupCreateBtn.addEventListener("click", () => setGroupCreateOpen(false));
groupCreatePanel.addEventListener("submit", createGroupFromPanel);
closeGroupMembersBtn.addEventListener("click", () => setGroupMembersOpen(true));
groupMetaForm.addEventListener("submit", updateGroupMetadataFromPanel);
groupMemberAddForm.addEventListener("submit", addGroupMemberFromPanel);
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
  if (activeGroupId === nextGroupId) return;

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
  loadHistory();
  msgInput.focus();
}

function renderRoomStrip() {
  if (!myId) return;

  roomStrip.classList.remove("hidden");
  const activeGroup = getActiveGroup();
  groupMembersOpen = Boolean(activeGroup);
  globalRoomBtn.classList.toggle("active", !activeGroupId);
  groupRoomList.innerHTML = "";

  roomTitle.textContent = activeGroup ? `${activeGroup.name} Hall` : "全局消息流";
  roomTitle.classList.toggle("editable", Boolean(activeGroup));
  roomDescription.textContent = activeGroup
    ? `${activeGroup.id} · Hall 在线同步中 · @ 开头提醒成员，同组可见${activeGroup.description ? ` · ${activeGroup.description}` : ""}`
    : "旧全局聊天与私聊时间线";
  const titleEditHint = document.getElementById("hall-title-edit-hint");
  if (titleEditHint) {
    titleEditHint.classList.toggle("hidden", !activeGroup);
  }

  const hallQuery = hallFilterInput.value.trim().toLowerCase();
  const visibleGroups = hallQuery
    ? groups.filter((group) => groupMatchesHallQuery(group, hallQuery))
    : groups;

  if (groups.length === 0) {
    const empty = document.createElement("span");
    empty.className = "group-room-empty";
    empty.textContent = "暂无 Group";
    groupRoomList.appendChild(empty);
  } else if (visibleGroups.length === 0) {
    const empty = document.createElement("span");
    empty.className = "group-room-empty";
    empty.textContent = "没有匹配的 Hall";
    groupRoomList.appendChild(empty);
  } else {
    for (const group of visibleGroups) {
      const button = document.createElement("button");
      const isActive = group.id === activeGroupId;
      const canEnter = getGroupMemberIds(group).has(myId);
      button.type = "button";
      button.className = `room-chip ${isActive ? "active" : ""}`;
      button.textContent = `${group.name} (${getGroupMemberIds(group).size})`;
      button.title = canEnter
        ? `${group.name} (${group.id})`
        : `${group.name} (${group.id}) · 你还不是成员`;
      button.disabled = !canEnter;
      button.addEventListener("click", () => setActiveGroup(group.id));
      groupRoomList.appendChild(button);
    }
  }

  toggleGroupCreateBtn.textContent = groupCreateOpen ? "×" : "＋";
  toggleGroupMembersBtn.classList.toggle("hidden", !activeGroup);
  toggleGroupMembersBtn.classList.toggle("active", groupMembersOpen && Boolean(activeGroup));
  toggleGroupMembersBtn.textContent = "＋";
  groupCreatePanel.classList.toggle("hidden", !groupCreateOpen);
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
  groupCreateMembers.innerHTML = "";
  if (!members.length) {
    const empty = document.createElement("div");
    empty.className = "group-create-member-empty";
    empty.textContent = "成员列表尚未加载";
    groupCreateMembers.appendChild(empty);
    return;
  }

  for (const member of members) {
    const label = document.createElement("label");
    label.className = "group-create-member";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = member.id;
    checkbox.checked = member.id === myId;
    checkbox.disabled = member.id === myId;

    const text = document.createElement("span");
    text.textContent = member.id === myId
      ? `${shortName(member.id)} (我)`
      : `${shortName(member.id)} · ${member.display_name}`;

    label.appendChild(checkbox);
    label.appendChild(text);
    groupCreateMembers.appendChild(label);
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

  const selectedMemberIds = Array.from(groupCreateMembers.querySelectorAll("input[type='checkbox']:checked"))
    .map((input) => input.value)
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
  const isOpen = Boolean(activeGroup);
  groupMembersPanel.classList.toggle("hidden", !isOpen);
  if (!isOpen || !activeGroup) return;

  const canManage = canManageGroups();
  const memberIds = getGroupMemberIds(activeGroup);
  const selectedKinds = selectedMemberKindFilters.size
    ? Array.from(selectedMemberKindFilters).join(" / ")
    : "全部";
  groupMembersSubtitle.textContent = `${activeGroup.id} · ${activeGroup.members.length} 位成员 · ${selectedKinds}`;
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
    const kind = member?.kind || memberKindFromId(membership.member_id);
    const onlineText = onlineMemberIds.has(membership.member_id) ? "在线" : "离线";
    meta.textContent = `${membership.role} · ${onlineText}${member ? ` · ${member.display_name}` : ""}`;

    const dot = document.createElement("span");
    dot.className = `member-status-dot ${onlineMemberIds.has(membership.member_id) ? "online" : "offline"}`;

    identity.appendChild(dot);
    identity.appendChild(name);
    identity.appendChild(meta);

    const controls = document.createElement("div");
    controls.className = "group-member-controls";

    const roleSelect = document.createElement("select");
    roleSelect.className = "group-member-role-select";
    roleSelect.disabled = !canManage || groupMemberSaving;
    for (const role of ["member", "moderator", "owner"]) {
      const option = document.createElement("option");
      option.value = role;
      option.textContent = role;
      option.selected = membership.role === role;
      roleSelect.appendChild(option);
    }
    roleSelect.addEventListener("change", () => updateGroupMemberRole(membership.member_id, roleSelect.value));

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "group-member-remove-btn";
    removeButton.textContent = "移除";
    removeButton.disabled = !canManage || groupMemberSaving || membership.member_id === myId;
    removeButton.title = membership.member_id === myId ? "不能在当前界面移除自己" : "移出 Group";
    removeButton.addEventListener("click", () => removeGroupMemberFromPanel(membership.member_id));

    controls.appendChild(roleSelect);
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
  const sortedMembers = [...members].sort((a, b) => {
    if (memberIds.has(a.id) !== memberIds.has(b.id)) {
      return memberIds.has(a.id) ? -1 : 1;
    }
    return a.id.localeCompare(b.id, "zh-CN");
  });

  for (const member of sortedMembers) {
    const row = document.createElement("div");
    row.className = "all-member-row";

    const body = document.createElement("div");
    body.className = "all-member-body";

    const name = document.createElement("div");
    name.className = "all-member-name";
    name.textContent = member.id === myId ? `${shortName(member.id)} (我)` : shortName(member.id);

    const meta = document.createElement("div");
    meta.className = "all-member-meta";
    meta.textContent = member.display_name || member.id;

    const roleButton = document.createElement("button");
    roleButton.type = "button";
    roleButton.className = `member-kind-pill ${selectedMemberKindFilters.has(member.kind) ? "active" : ""}`;
    roleButton.textContent = member.kind || memberKindFromId(member.id);
    roleButton.addEventListener("click", () => toggleMemberKindFilter(member.kind || memberKindFromId(member.id)));

    body.appendChild(name);
    body.appendChild(meta);
    body.appendChild(roleButton);

    const action = document.createElement("button");
    action.type = "button";
    action.className = memberIds.has(member.id) ? "member-added-pill" : "member-add-btn";
    action.textContent = memberIds.has(member.id) ? "已在 Hall" : "加入";
    action.disabled = memberIds.has(member.id) || !canManage || groupMemberSaving;
    action.addEventListener("click", () => saveGroupMember(member.id, "member"));

    row.appendChild(body);
    row.appendChild(action);
    allMembersList.appendChild(row);
  }

  if (!sortedMembers.length) {
    const empty = document.createElement("div");
    empty.className = "member-empty-state";
    empty.textContent = "暂无可显示成员";
    allMembersList.appendChild(empty);
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

async function updateGroupMemberRole(memberId, role) {
  if (!memberId || !role || groupMemberSaving || !activeGroupId) return;
  await saveGroupMember(memberId, role);
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
  renderRoomStrip();
  renderPresenceStrip();
  if (pollTimer) clearInterval(pollTimer);
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  closeEventStream();
  loadHistory();
  connectWS();
  pollTimer = setInterval(pollMessages, 3000);
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
    if (!memberIds.has(memberId)) {
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

    const filtered = getScopedMembers().filter(
      (m) => m.id.toLowerCase().includes(query) || m.display_name.toLowerCase().includes(query)
    );

    if (filtered.length > 0) {
      mentionDropdown.innerHTML = "";
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
