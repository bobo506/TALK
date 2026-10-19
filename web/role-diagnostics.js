/* 角色运行诊断：只在人类显式点击后读取日志；所有响应文本均按纯文本渲染。 */
var roleDiagnostics = (function roleDiagnosticsModule(global) {
  "use strict";

  const LOG_REF_RE = /^rtd-[A-Za-z0-9.-]{4,160}$/;
  const SAFE_FILTER_RE = /^[A-Za-z0-9_.:-]+$/;
  const SEVERITIES = ["error", "warning", "info"];
  const FILTER_KEYS = ["since", "until", "instance_id", "launch_id", "task_id", "event", "stage", "severity", "ref"];
  const state = {
    epoch: 0,
    contextKey: null,
    visible: false,
    human: false,
    projectId: null,
    accountId: null,
    role: null,
    serviceView: null,
    serviceStatus: null,
    queried: false,
    records: [],
    evidenceRecords: new Map(),
    loading: false,
    loadingMore: false,
    listSeq: 0,
    queryGeneration: 0,
    activeFilterKey: null,
    canonicalFilterKey: null,
    canonicalQuery: null,
    limit: 20,
    hasMore: false,
    nextCursor: null,
    refMode: false,
    scan: null,
    status: "",
    statusKind: "",
    scanNote: "",
    listController: null,
    detailSeq: 0,
    detailController: null,
    detail: { open: false, ref: null, returnFocus: null },
    copySeq: 0,
  };

  function byId(id) {
    return typeof document === "undefined" ? null : document.getElementById(id);
  }
  function makeEl(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function makeButton(text, handler, className = "workspace-text-button") {
    const node = makeEl("button", className, text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }
  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = value === null || value === undefined ? "" : String(value);
  }
  function setHidden(id, hidden) {
    const node = byId(id);
    if (node) node.classList.toggle("hidden", Boolean(hidden));
  }
  function showValue(value, missing = "未记录") {
    return value === null || value === undefined || value === "" ? missing : String(value);
  }
  function boolValue(value) {
    return value === true ? "是" : value === false ? "否" : "未记录";
  }
  function currentService() {
    return state.serviceView && state.serviceView.service ? state.serviceView.service : null;
  }
  function currentIdentity() {
    const service = currentService();
    const launch = service && service.current_launch;
    const instanceId = service && typeof service.observed_instance_id === "string" ? service.observed_instance_id : "";
    const launchId = launch && typeof launch.launch_id === "string" ? launch.launch_id : "";
    const expected = launch && typeof launch.expected_instance_id === "string" ? launch.expected_instance_id : "";
    return {
      launchId,
      instanceId,
      valid: Boolean(launchId && instanceId && expected && expected === instanceId),
    };
  }
  function contextIdentity(ctx) {
    const service = ctx && ctx.serviceView && ctx.serviceView.service;
    const launch = service && service.current_launch;
    return [
      service && service.observed_instance_id ? service.observed_instance_id : "",
      launch && launch.launch_id ? launch.launch_id : "",
      launch && launch.expected_instance_id ? launch.expected_instance_id : "",
    ];
  }
  function contextKeyFor(ctx) {
    if (!ctx || !ctx.visible || !ctx.role || !ctx.role.member_id || !ctx.projectId || !ctx.accountId) return null;
    return JSON.stringify([
      ctx.projectId, ctx.accountId, ctx.role.member_id, Boolean(ctx.human), ...contextIdentity(ctx),
    ]);
  }
  function canReadLogs() {
    return Boolean(state.visible && state.human && state.contextKey && state.projectId && state.accountId && state.role);
  }
  function apiFetcher() {
    if (typeof apiFetch === "function") return apiFetch;
    if (global && typeof global.apiFetch === "function") return global.apiFetch;
    return null;
  }
  function newAbortController() {
    const Controller = global && global.AbortController;
    return typeof Controller === "function" ? new Controller() : null;
  }
  function abortController(key) {
    const controller = state[key];
    if (controller && typeof controller.abort === "function") {
      try { controller.abort(); } catch (_) { /* 已关闭的控制器无需重复处理 */ }
    }
    state[key] = null;
  }
  function localError(message) {
    const error = new Error(message);
    error.localValidation = true;
    return error;
  }
  function responseError(message) {
    const error = new Error(message);
    error.responseContract = true;
    return error;
  }

  function clearDetailContent() {
    const content = byId("role-log-detail-content");
    if (content) content.replaceChildren();
    setText("role-log-detail-status", "");
    setText("role-log-detail-ref", "");
    setText("role-log-detail-title", "日志详情");
  }
  function dialogIsOpen(dialog) {
    return Boolean(dialog && (dialog.open || (typeof dialog.hasAttribute === "function" && dialog.hasAttribute("open"))));
  }
  function closeDetail({ restoreFocus = true, alreadyClosed = false } = {}) {
    const returnFocus = state.detail.returnFocus;
    state.detailSeq += 1;
    abortController("detailController");
    state.detail = { open: false, ref: null, returnFocus: null };
    clearDetailContent();
    const dialog = byId("role-log-detail-dialog");
    if (!alreadyClosed && dialogIsOpen(dialog)) {
      if (typeof dialog.close === "function") {
        try { dialog.close(); } catch (_) { dialog.removeAttribute("open"); }
      } else {
        dialog.removeAttribute("open");
      }
    }
    if (restoreFocus && returnFocus && returnFocus.isConnected !== false && typeof returnFocus.focus === "function") {
      returnFocus.focus();
    }
  }
  function openDetailDialog() {
    const dialog = byId("role-log-detail-dialog");
    if (!dialog) return;
    if (!dialogIsOpen(dialog)) {
      if (typeof dialog.showModal === "function") {
        try { dialog.showModal(); } catch (_) { dialog.setAttribute("open", ""); }
      } else {
        dialog.setAttribute("open", "");
      }
    }
    const close = byId("role-log-detail-close");
    if (close && typeof close.focus === "function") close.focus();
  }

  function selectedSeverities() {
    return SEVERITIES.filter(level => {
      const input = byId(`role-log-severity-${level}`);
      return input && input.checked;
    });
  }
  function setSeverity(levels) {
    for (const level of SEVERITIES) {
      const input = byId(`role-log-severity-${level}`);
      if (input) input.checked = levels.includes(level);
    }
  }
  function syncTimeFields() {
    const custom = byId("role-log-time") && byId("role-log-time").value === "custom";
    setHidden("role-log-since-field", !custom);
    setHidden("role-log-until-field", !custom);
  }
  function resetInstanceOptions() {
    const select = byId("role-log-instance");
    if (!select) return;
    for (const child of Array.from(select.children || [])) {
      if (child.dataset && child.dataset.dynamic === "1" && typeof child.remove === "function") child.remove();
    }
    select.value = "";
  }
  function resetFilterDom() {
    const values = {
      "role-log-time": "24h",
      "role-log-since": "",
      "role-log-until": "",
      "role-log-launch": "",
      "role-log-task": "",
      "role-log-event": "",
      "role-log-stage": "",
      "role-log-ref": "",
    };
    for (const [id, value] of Object.entries(values)) {
      const input = byId(id);
      if (input) input.value = value;
    }
    resetInstanceOptions();
    setSeverity(["error", "warning"]);
    syncTimeFields();
  }
  function clearQueryResults({ preserveEvidence = true } = {}) {
    state.records = [];
    if (!preserveEvidence) state.evidenceRecords = new Map();
    state.canonicalQuery = null;
    state.canonicalFilterKey = null;
    state.activeFilterKey = null;
    state.hasMore = false;
    state.nextCursor = null;
    state.refMode = false;
    state.scan = null;
    state.scanNote = "";
    const records = byId("role-log-records");
    if (records) records.replaceChildren();
  }
  function invalidateList() {
    state.listSeq += 1;
    state.queryGeneration += 1;
    abortController("listController");
    state.loading = false;
    state.loadingMore = false;
  }
  function filtersChanged() {
    if (!state.visible || state.loading) return;
    closeDetail({ restoreFocus: false });
    invalidateList();
    clearQueryResults();
    state.queried = false;
    state.status = "筛选已修改；点击“查询”后才会按新条件读取。";
    state.statusKind = "";
    syncTimeFields();
    renderControls();
    renderStatus();
  }
  function resetToDefault() {
    closeDetail({ restoreFocus: false });
    invalidateList();
    clearQueryResults();
    state.queried = false;
    state.status = "";
    state.statusKind = "";
    resetFilterDom();
    renderControls();
    renderStatus();
  }

  function validateSafeFilter(value, label, max) {
    if (!value) return null;
    const text = String(value).trim();
    if (!text) return null;
    if (text.length > max || !SAFE_FILTER_RE.test(text)) {
      throw localError(`${label}只能使用字母、数字、下划线、点、冒号或连字符，且不超过 ${max} 字符。`);
    }
    return text;
  }
  function explicitTimezone(value, label) {
    const text = String(value || "").trim();
    if (!text || !/(?:z|[+-]\d{2}:?\d{2})$/i.test(text) || !Number.isFinite(Date.parse(text))) {
      throw localError(`${label}必须是带时区的有效 ISO 8601 时间。`);
    }
    return new Date(text).toISOString();
  }
  function buildFilterQuery() {
    const time = byId("role-log-time") ? byId("role-log-time").value : "24h";
    const query = {
      since: null, until: null, instance_id: null, launch_id: null,
      task_id: null, event: null, stage: null, severity: selectedSeverities(), ref: null,
    };
    if (!query.severity.length) throw localError("请至少选择一个日志级别。");
    const now = Date.now();
    if (time === "1h" || time === "7d") {
      const duration = time === "1h" ? 3600000 : 7 * 86400000;
      query.until = new Date(now).toISOString();
      query.since = new Date(now - duration).toISOString();
    } else if (time === "custom") {
      query.since = explicitTimezone(byId("role-log-since") && byId("role-log-since").value, "开始时间");
      query.until = explicitTimezone(byId("role-log-until") && byId("role-log-until").value, "结束时间");
      const sinceMs = Date.parse(query.since);
      const untilMs = Date.parse(query.until);
      if (sinceMs >= untilMs) throw localError("开始时间必须早于结束时间。");
      if (untilMs - sinceMs > 31 * 86400000) throw localError("自定义时间跨度不能超过 31 天。");
    } else if (time !== "24h") {
      throw localError("无法识别的时间范围。");
    }
    query.instance_id = validateSafeFilter(byId("role-log-instance") && byId("role-log-instance").value === "__current__" ? "" : (byId("role-log-instance") && byId("role-log-instance").value), "实例", 128);
    query.launch_id = validateSafeFilter(byId("role-log-launch") && byId("role-log-launch").value, "启动动作", 128);
    query.event = validateSafeFilter(byId("role-log-event") && byId("role-log-event").value, "事件", 64);
    query.stage = validateSafeFilter(byId("role-log-stage") && byId("role-log-stage").value, "阶段", 64);
    const taskText = byId("role-log-task") ? byId("role-log-task").value.trim() : "";
    if (taskText) {
      if (!/^[1-9]\d*$/.test(taskText) || !Number.isSafeInteger(Number(taskText))) {
        throw localError("任务编号必须是页面可安全表示的正整数。");
      }
      query.task_id = String(Number(taskText));
    }
    if (byId("role-log-instance") && byId("role-log-instance").value === "__current__") {
      const identity = currentIdentity();
      if (!identity.valid) throw localError("当前 launch 与实例身份未完整匹配，不能按“当前实例”筛选。");
      if (query.launch_id && query.launch_id !== identity.launchId) {
        throw localError("当前实例筛选不能与另一个 launch_id 混用。");
      }
      query.instance_id = identity.instanceId;
      query.launch_id = identity.launchId;
    }
    return query;
  }
  function filterKey(query, limit = 20, cursor = null) {
    return JSON.stringify({
      since: query.since ?? null, until: query.until ?? null,
      instance_id: query.instance_id ?? null, launch_id: query.launch_id ?? null,
      task_id: query.task_id === null || query.task_id === undefined ? null : String(query.task_id),
      event: query.event ?? null, stage: query.stage ?? null,
      severity: Array.isArray(query.severity) ? [...query.severity] : null,
      ref: query.ref ?? null, limit, cursor,
    });
  }
  function canonicalQuery(query, limit) {
    const canonical = { limit };
    for (const key of FILTER_KEYS) {
      if (key === "severity") canonical.severity = Array.isArray(query.severity) ? [...query.severity] : null;
      else if (key === "task_id") canonical.task_id = query.task_id === null || query.task_id === undefined ? null : String(query.task_id);
      else canonical[key] = query[key] ?? null;
    }
    return canonical;
  }
  function paramsFor(query, { cursor = null, refOnly = false, refMode = false } = {}) {
    const params = new URLSearchParams();
    if (refOnly || refMode) {
      params.set("ref", query.ref);
      return params;
    }
    for (const key of ["since", "until", "instance_id", "launch_id", "task_id", "event", "stage"]) {
      if (query[key] !== null && query[key] !== undefined && query[key] !== "") params.set(key, String(query[key]));
    }
    if (Array.isArray(query.severity)) params.set("severity", query.severity.join(","));
    params.set("limit", String(query.limit || 20));
    if (cursor) params.set("cursor", cursor);
    return params;
  }
  function listPath(query, options) {
    const base = `/api/projects/${encodeURIComponent(state.projectId)}/roles/${encodeURIComponent(state.role.member_id)}/runtime-logs`;
    return `${base}?${paramsFor(query, options).toString()}`;
  }
  function isListCurrent(request) {
    return state.epoch === request.epoch
      && state.contextKey === request.contextKey
      && state.queryGeneration === request.generation
      && state.listSeq === request.id
      && state.activeFilterKey === request.key
      && canReadLogs();
  }
  function validateScope(data, schema) {
    if (!data || data.schema !== schema || !data.scope
        || data.scope.project_id !== state.projectId || data.scope.member_id !== state.role.member_id) {
      throw responseError("服务响应的项目、角色或 schema 与当前上下文不一致。");
    }
  }
  function validateRecordScope(record) {
    if (!record || record.project_id !== state.projectId || record.member_id !== state.role.member_id) {
      throw responseError("服务响应含当前项目与角色之外的记录，已拒绝展示。");
    }
  }
  function validatePage(data, request) {
    validateScope(data, "talk-runtime-log-page-1");
    if (!Array.isArray(data.records) || !data.query || !data.page || !data.scan
        || typeof data.scan.complete !== "boolean" || !Number.isInteger(data.page.limit)
        || data.page.limit < 1 || data.page.limit > 50) {
      throw responseError("日志列表响应缺少合同要求的 query、page 或 scan 字段。");
    }
    for (const record of data.records) validateRecordScope(record);
    if (request.refMode) {
      if (data.query.ref !== request.query.ref) throw responseError("精确引用响应与请求不一致。");
    } else if (typeof data.query.since !== "string" || typeof data.query.until !== "string"
        || !Number.isFinite(Date.parse(data.query.since)) || !Number.isFinite(Date.parse(data.query.until))) {
      throw responseError("首页未返回可用于稳定分页的绝对规范化时间。");
    }
    if (request.kind === "more") {
      const returnedKey = filterKey(canonicalQuery(data.query, data.page.limit), data.page.limit);
      if (data.page.limit !== request.query.limit || returnedKey !== request.key) {
        throw responseError("分页响应的规范化 query 与首页不一致，已拒绝拼接。");
      }
    }
  }
  function exceptionOnly(query) {
    const levels = Array.isArray(query.severity) ? [...query.severity].sort() : [];
    return levels.join(",") === "error,warning" && !query.event && !query.ref;
  }
  function scanMessage(scan, warnings) {
    const notes = [];
    if (scan && scan.complete === false) {
      if (scan.truncated) {
        notes.push("已显示本次扫描命中的记录；扫描达到上限，结果可能不完整。请缩小时间范围，或按实例、启动动作、日志引用查询。");
      } else {
        notes.push("本次扫描未完成，结果可能不完整；未将缺失记录当作无异常。");
      }
    }
    if (scan && ((Number(scan.malformed_lines) || 0) > 0 || (Number(scan.unavailable_sources) || 0) > 0)) {
      notes.push("部分日志记录无法读取或解析，结果可能不完整；未将缺失记录当作无异常。");
    }
    if (Array.isArray(warnings) && warnings.length) {
      notes.push(`服务端警告码：${warnings.map(item => String(item)).join("、")}`);
    }
    return notes.join(" ");
  }
  function addEvidenceRecords(records) {
    for (const record of records) {
      if (record && typeof record.log_id === "string" && record.log_id) state.evidenceRecords.set(record.log_id, record);
    }
  }
  function handlePage(data, request) {
    validatePage(data, request);
    const incoming = data.records;
    if (request.kind === "more") {
      const existing = new Set(state.records.map(record => record && record.log_id));
      if (incoming.some(record => existing.has(record && record.log_id))) {
        throw responseError("分页返回了重复日志引用，已拒绝拼接。");
      }
      state.records = state.records.concat(incoming);
    } else {
      state.records = incoming.slice();
    }
    addEvidenceRecords(incoming);
    state.queried = true;
    state.limit = data.page.limit;
    state.canonicalQuery = canonicalQuery(data.query, data.page.limit);
    state.canonicalFilterKey = filterKey(state.canonicalQuery, data.page.limit);
    state.scan = data.scan;
    state.scanNote = scanMessage(data.scan, data.warnings);
    state.hasMore = Boolean(!request.refMode && data.scan.complete && data.page.has_more
      && typeof data.page.next_cursor === "string" && data.page.next_cursor);
    state.nextCursor = state.hasMore ? data.page.next_cursor : null;
    if (!state.records.length) {
      if (!data.scan.complete) {
        state.status = "本次扫描未完成，不能据此确认没有日志。";
        state.statusKind = "warning";
      } else if (exceptionOnly(data.query)) {
        state.status = "当前范围内未发现异常日志。";
        state.statusKind = "";
      } else {
        state.status = "当前范围内没有可查日志。";
        state.statusKind = "";
      }
    } else {
      state.status = `已显示 ${state.records.length} 条日志摘要。`;
      state.statusKind = data.scan.complete ? "" : "warning";
    }
    addInstanceOptions(incoming);
    renderEvidence();
    renderRecords();
  }
  function apiErrorMessage(status, detail, request) {
    const code = typeof detail === "string" ? detail : "";
    if (status === 401) return "登录已失效，请重新登录；本次日志未读取。";
    if (status === 403) return "当前 Agent 账号没有运行日志查看权限。";
    if (status === 404 && code === "log_not_found") {
      return "未找到该日志引用；它可能已超出保留期、从未写入成功，或不属于当前项目与角色。";
    }
    if (status === 404) return "项目或角色不存在，或该历史角色对不在可查范围。";
    if (status === 409 && code === "stale_cursor") {
      return "日志分页依据已变化，请从第一页重新查询；旧页已清空，未拼接新旧数据。";
    }
    if (status === 409 && code === "log_ref_conflict") {
      return "同一日志引用命中多条不一致记录，无法安全确定结果。";
    }
    if (status === 410 && code === "log_retention_expired") {
      return "该日志已过保留期，详细内容不可再读取；保留期处置记录仍在。";
    }
    if (status === 422) {
      const labels = {
        invalid_log_ref: "日志引用格式无效。",
        invalid_filter: "查询参数不符合合同，请检查时间、筛选与条数。",
        invalid_cursor: "分页游标无效或与当前筛选不一致，请从第一页重查。",
        conflicting_filters: "精确引用不能与时间、级别、其它筛选或分页混用。",
      };
      return labels[code] || "查询参数不符合合同，请检查后重试。";
    }
    if (status === 503 && code === "diagnostics_unavailable") {
      return "暂时无法读取该角色的日志来源；这不表示角色已停止或没有异常。首版仅支持同机已配置来源。";
    }
    if (status === 503 && code === "diagnostics_scan_incomplete") {
      return "日志扫描未完成，无法确认该引用或详情；请缩小范围后重查，不能据此判定不存在。";
    }
    if (status === 503 && code === "diagnostics_projection_failed") {
      return "日志内容无法安全投影，未展示原始记录或内部路径。";
    }
    if (status === 503) return "日志来源暂时不可用；这不表示角色已停止或没有异常。";
    return `日志读取失败（HTTP ${status || "网络错误"}），请稍后重试；既有服务状态与启停操作不受影响。`;
  }
  function applyListError(request, status, detail) {
    if (status === 409 && detail === "stale_cursor") {
      state.records = [];
      state.canonicalQuery = null;
      state.canonicalFilterKey = null;
      state.hasMore = false;
      state.nextCursor = null;
      state.scan = null;
      state.scanNote = "";
      renderRecords();
    }
    state.status = apiErrorMessage(status, detail, request);
    state.statusKind = "error";
  }
  async function performList(request) {
    const fetcher = apiFetcher();
    if (!fetcher) {
      if (isListCurrent(request)) {
        applyListError(request, 0, "network_error");
        state.loading = false;
        state.loadingMore = false;
        renderControls();
        renderStatus();
      }
      return;
    }
    const controller = newAbortController();
    state.listController = controller;
    try {
      const options = { method: "GET" };
      if (controller) options.signal = controller.signal;
      const response = await fetcher(listPath(request.query, request), options);
      if (!isListCurrent(request)) return;
      const body = await response.json().catch(() => null);
      if (!isListCurrent(request)) return;
      if (!response.ok) {
        applyListError(request, response.status, body && body.detail);
        return;
      }
      handlePage(body, request);
    } catch (error) {
      if (!isListCurrent(request)) return;
      if (error && error.name === "AbortError") return;
      applyListError(request, 0, error && error.responseContract ? "invalid_response" : "network_error");
      if (error && error.responseContract) state.status = error.message;
    } finally {
      if (isListCurrent(request)) {
        state.loading = false;
        state.loadingMore = false;
        state.listController = null;
        renderControls();
        renderStatus();
        renderEvidence();
      }
    }
  }
  function beginList(query, { kind = "first", key, refMode = false, cursor = null } = {}) {
    if (!canReadLogs() || state.loading) return false;
    closeDetail({ restoreFocus: false });
    invalidateList();
    const id = state.listSeq;
    const generation = state.queryGeneration;
    state.loading = true;
    state.loadingMore = kind === "more";
    state.refMode = refMode;
    state.status = "正在读取日志…";
    state.statusKind = "";
    state.scanNote = "";
    state.activeFilterKey = key;
    if (kind === "first") {
      state.records = [];
      state.canonicalQuery = null;
      state.canonicalFilterKey = null;
      state.hasMore = false;
      state.nextCursor = null;
      state.scan = null;
      renderRecords();
    }
    renderControls();
    renderStatus();
    const request = {
      id, generation, key, kind, refMode, cursor, query,
      epoch: state.epoch, contextKey: state.contextKey,
    };
    performList(request);
    return true;
  }
  function startDefaultQuery() {
    if (!canReadLogs() || state.loading) return;
    resetToDefault();
    startFirstPage();
  }
  function startFirstPage() {
    if (!canReadLogs() || state.loading) return;
    try {
      const query = buildFilterQuery();
      query.limit = 20;
      beginList(query, { kind: "first", key: filterKey(query, 20), refMode: false });
    } catch (error) {
      state.status = error && error.localValidation ? `参数错误：${error.message}` : "无法构造日志查询。";
      state.statusKind = "error";
      renderStatus();
      renderControls();
    }
  }
  function startRefQuery() {
    if (!canReadLogs() || state.loading) return;
    const ref = byId("role-log-ref") ? byId("role-log-ref").value.trim() : "";
    if (!LOG_REF_RE.test(ref)) {
      state.status = "参数错误：日志引用格式无效，应为一整串 rtd- 引用，不是路径。";
      state.statusKind = "error";
      renderStatus();
      return;
    }
    const query = { ref };
    beginList(query, { kind: "first", key: filterKey({ ...query, severity: null }, 20), refMode: true });
  }
  function loadMore() {
    if (!canReadLogs() || state.loading || !state.hasMore || !state.nextCursor
        || !state.canonicalQuery || state.refMode) return;
    const query = { ...state.canonicalQuery, limit: state.limit };
    const key = state.canonicalFilterKey;
    beginList(query, { kind: "more", key, refMode: false, cursor: state.nextCursor });
  }

  function recordInstanceRelation(record) {
    const identity = currentIdentity();
    const current = Boolean(identity.valid && record && record.instance_id
      && record.instance_id === identity.instanceId && record.launch_id === identity.launchId);
    if (!record || !record.instance_id) return { current: false, text: "实例未记录" };
    return {
      current,
      text: `${current ? "当前实例" : "历史实例"} ${record.instance_id}`,
    };
  }
  function formatTime(value) {
    if (!value) return "时间未记录";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { hour12: false });
  }
  function severityText(value) {
    return ({ error: "错误", warning: "警告", info: "信息" })[value] || showValue(value, "级别未记录");
  }
  function integrityText(integrity, detail = false) {
    const row = integrity || {};
    const parts = [
      row.redacted === true ? "已执行脱敏（非绝对保证）" : row.redacted === false ? "未标记脱敏" : "脱敏标志未记录",
      row.truncated === true ? "原始记录有截断" : row.truncated === false ? "原始记录未标记截断" : "截断标志未记录",
      row.write_complete === true ? "写入完整" : row.write_complete === false ? "写入不完整" : "写入完整性未记录",
    ];
    if (detail) {
      parts.push(`容量软上限：${boolValue(row.capacity_soft_exceeded)}`, `事件大小软上限：${boolValue(row.event_size_soft_exceeded)}`);
      if (Array.isArray(row.redaction_kinds)) parts.push(`脱敏类型：${row.redaction_kinds.join("、") || "无"}`);
      if (Array.isArray(row.truncated_fields)) parts.push(`截断字段：${row.truncated_fields.join("、") || "无"}`);
    }
    return parts.join("；");
  }
  function addInstanceOptions(records) {
    const select = byId("role-log-instance");
    if (!select) return;
    const selected = select.value;
    const existing = new Set(Array.from(select.children || []).map(option => option.value));
    for (const record of records) {
      const value = record && record.instance_id;
      if (!value || existing.has(value) || !SAFE_FILTER_RE.test(value) || value.length > 128) continue;
      const option = makeEl("option", "", `${recordInstanceRelation(record).current ? "当前" : "历史"}实例 ${value}`);
      option.value = value;
      option.dataset.dynamic = "1";
      select.appendChild(option);
      existing.add(value);
    }
    select.value = selected;
  }
  function renderRecords() {
    const container = byId("role-log-records");
    if (!container) return;
    container.replaceChildren();
    for (const record of state.records) {
      const card = makeEl("article", "role-log-record");
      const relation = recordInstanceRelation(record);
      const head = makeEl("div", "role-log-record-head");
      head.append(
        makeEl("time", "role-log-time-text", formatTime(record.recorded_at)),
        makeEl("span", `role-log-severity-badge ${showValue(record.severity, "unknown")}`, severityText(record.severity)),
        makeEl("strong", "role-log-event-name", showValue(record.event, "事件未记录")),
        makeEl("span", "role-log-stage", `阶段：${showValue(record.stage)}`),
      );
      card.appendChild(head);
      const exception = record.exception;
      const preview = exception
        ? [exception.type, exception.message_preview].filter(value => value !== null && value !== undefined && value !== "").join("：") || "已记录异常，但无简短摘要"
        : "该事件没有异常摘要。";
      card.appendChild(makeEl("p", "role-log-preview", preview));
      const meta = makeEl("div", "role-log-record-meta");
      meta.append(
        makeEl("span", relation.current ? "role-log-instance current" : "role-log-instance historical", relation.text),
        makeEl("span", "", `启动：${showValue(record.launch_id)}`),
        makeEl("span", "", `任务：${record.task_id === null || record.task_id === undefined ? "未记录" : `#${record.task_id}`}`),
      );
      card.appendChild(meta);
      card.appendChild(makeEl("p", "role-log-integrity", integrityText(record.integrity)));
      const refRow = makeEl("div", "role-log-ref-row-display");
      const validRef = typeof record.log_id === "string" && LOG_REF_RE.test(record.log_id);
      const code = makeEl("code", "role-log-ref-text", validRef ? record.log_id : "没有可信日志引用");
      code.tabIndex = 0;
      refRow.appendChild(code);
      if (validRef) {
        refRow.append(
          makeButton("复制引用", event => copyReference(record.log_id, event && event.currentTarget), "room-secondary-btn"),
          makeButton("查看详情", event => openDetail(record.log_id, event && event.currentTarget), "room-primary-btn"),
        );
      } else {
        refRow.appendChild(makeEl("span", "role-log-missing-ref", "详细日志可能未写入；不能据此推断没有异常。"));
      }
      card.appendChild(refRow);
      container.appendChild(card);
    }
  }

  async function copyReference(ref, trigger) {
    if (!canReadLogs() || !LOG_REF_RE.test(ref)) return;
    const seq = ++state.copySeq;
    const contextKey = state.contextKey;
    try {
      const clipboard = global && global.navigator && global.navigator.clipboard;
      if (!clipboard || typeof clipboard.writeText !== "function") throw new Error("clipboard unavailable");
      await clipboard.writeText(ref);
      if (seq !== state.copySeq || contextKey !== state.contextKey) return;
      state.status = "日志引用已复制。";
      state.statusKind = "success";
    } catch (_) {
      if (seq !== state.copySeq || contextKey !== state.contextKey) return;
      state.status = "复制失败，请手动选择并复制日志引用。";
      state.statusKind = "error";
      if (trigger && typeof trigger.focus === "function") trigger.focus();
    }
    renderStatus();
  }

  function latestEvidence(events) {
    const wanted = new Set(events);
    return Array.from(state.evidenceRecords.values())
      .filter(record => record && wanted.has(record.event))
      .sort((a, b) => String(b.recorded_at || "").localeCompare(String(a.recorded_at || ""))
        || String(b.log_id || "").localeCompare(String(a.log_id || "")))[0] || null;
  }
  function evidenceLine(prefix, record) {
    if (!record) return prefix;
    const relation = recordInstanceRelation(record);
    return `${prefix}${record.event} · ${formatTime(record.recorded_at)} · ${relation.current ? "当前实例" : "历史实例"}`;
  }
  function renderEvidence() {
    const service = currentService();
    const identity = currentIdentity();
    if (!state.visible) return;
    let owner = "归属证据未知；宿主当前状态未知";
    let ownerDetail = "没有宿主独立心跳，不能显示“宿主正常”";
    if (state.serviceView && state.serviceView.provided && service) {
      owner = service.ownership_held === true
        ? "归属未释放；宿主当前状态未知"
        : service.ownership_held === false ? "当前未持有原进程归属；宿主当前状态未知" : "归属证据未知；宿主当前状态未知";
      const receipt = service.last_action || service.last_result;
      ownerDetail = `${receipt ? `最近服务回执：${receipt}（历史事实）` : "最近服务回执未记录"}；证据时间：${showValue(service.updated_at)}；无宿主独立心跳`;
    }
    setText("role-evidence-owner", owner);
    setText("role-evidence-owner-detail", ownerDetail);

    let heartbeat = "实例心跳：未知";
    let heartbeatDetail = "没有可精确匹配当前项目、launch 与实例的公开心跳证据";
    const statusText = state.serviceStatus && state.serviceStatus.text;
    if (service && identity.valid) {
      heartbeatDetail = `当前 launch ${identity.launchId} · 实例 ${identity.instanceId}；服务投影时间 ${showValue(service.updated_at)}`;
      if (typeof statusText === "string" && statusText.startsWith("启动成功")) heartbeat = "近期有实例心跳（按现有服务投影）";
      else if (statusText === "运行状态待核实") heartbeat = "运行状态待核实；超时不证明实例已死亡";
      else if (service.observed === "stopped" || service.observed === "not_started") heartbeat = `当前无运行中实例心跳；服务投影：${statusText || service.observed}`;
      else if (service.observed === "starting" || service.observed === "stopping") heartbeat = `实例心跳待确认；服务投影：${statusText || service.observed}`;
      else heartbeat = `实例心跳证据不足；服务投影：${statusText || showValue(service.observed, "未知")}`;
    } else if (service && statusText) {
      heartbeat = `实例心跳身份未完整匹配；服务投影：${statusText}`;
    }
    setText("role-evidence-heartbeat", heartbeat);
    setText("role-evidence-heartbeat-detail", heartbeatDetail);

    const queue = latestEvidence(["queue_started", "queue_stopped", "queue_worker_exception"]);
    const queueEvidence = queue ? evidenceLine("最近一次已读接单循环事件：", queue) : "本次已查日志未出现接单循环事件";
    setText("role-evidence-queue", "当前接单循环：未知");
    setText("role-evidence-queue-detail", state.queried || state.evidenceRecords.size
      ? `${queueEvidence}；无周期 queue heartbeat，不能推断当前健康或死亡`
      : "历史接单循环事件：尚未查询；无周期 queue heartbeat");

    const claim = latestEvidence(["task_claimed"]);
    setText("role-evidence-claim", claim
      ? `最近已读领取记录：${claim.task_id === null || claim.task_id === undefined ? "任务编号未记录" : `#${claim.task_id}`}；当前能力未验证`
      : state.queried || state.evidenceRecords.size ? "本次已查范围无领取记录；当前能力未验证" : "最近领取记录：尚未查询；当前能力未验证");
    setText("role-evidence-claim-detail", claim
      ? `${evidenceLine("历史证据：", claim)}；历史领取不代表当前可接单，idle 也不等于接单正常`
      : "无领取记录不等于不能接单；不进行主动 canary、模型调用或新任务");
    setText("role-evidence-preflight", "领取前预检：未知");
    setText("role-evidence-preflight-detail", "缺少实际关联的预检起止记录；创建到领取的总时间不等于模型预检耗时");
  }

  function renderStatus() {
    const status = byId("role-log-status");
    if (status) {
      status.textContent = state.status || (state.human ? "尚未查询运行日志；不会自动扫描。" : "当前 Agent 账号没有运行日志查看权限。");
      status.className = `role-log-status${state.statusKind ? ` ${state.statusKind}` : ""}`;
    }
    const scan = byId("role-log-scan");
    if (scan) scan.textContent = state.scanNote || "";
  }
  function renderControls() {
    setHidden("role-diagnostics-panel", !state.visible);
    const disabled = !canReadLogs() || state.loading;
    const ids = [
      "role-log-view-btn", "role-log-mode-errors", "role-log-mode-all", "role-log-time",
      "role-log-since", "role-log-until", "role-log-instance", "role-log-launch", "role-log-task",
      "role-log-event", "role-log-stage", "role-log-severity-error", "role-log-severity-warning",
      "role-log-severity-info", "role-log-ref", "role-log-ref-btn", "role-log-query-btn", "role-log-reset-btn",
    ];
    for (const id of ids) {
      const control = byId(id);
      if (control) control.disabled = disabled;
    }
    const more = byId("role-log-more-btn");
    if (more) {
      more.disabled = disabled;
      more.classList.toggle("hidden", !(canReadLogs() && state.hasMore && state.nextCursor && !state.refMode));
      more.textContent = state.loadingMore ? "正在读取日志…" : "加载更早";
    }
    const levels = selectedSeverities();
    const errors = byId("role-log-mode-errors");
    const all = byId("role-log-mode-all");
    if (errors) errors.setAttribute("aria-pressed", String(levels.join(",") === "error,warning"));
    if (all) all.setAttribute("aria-pressed", String(levels.join(",") === "error,warning,info"));
    setText("role-log-permission", !state.human
      ? "当前 Agent 账号没有运行日志查看权限"
      : state.loading ? "正在读取日志…" : "只读查询，不会启停服务、恢复、创建任务或调用模型");
    syncTimeFields();
  }
  function renderAll() {
    renderControls();
    renderEvidence();
    renderStatus();
  }

  function sync(ctx) {
    const panel = byId("role-diagnostics-panel");
    if (!panel) return;
    const key = contextKeyFor(ctx);
    if (key !== state.contextKey) {
      state.epoch += 1;
      closeDetail({ restoreFocus: false });
      invalidateList();
      state.copySeq += 1;
      state.contextKey = key;
      state.visible = Boolean(key);
      state.human = Boolean(key && ctx.human);
      state.projectId = key ? ctx.projectId : null;
      state.accountId = key ? ctx.accountId : null;
      state.role = key ? ctx.role : null;
      state.serviceView = key ? ctx.serviceView : null;
      state.serviceStatus = key ? ctx.serviceStatus : null;
      state.queried = false;
      state.evidenceRecords = new Map();
      clearQueryResults();
      state.status = "";
      state.statusKind = "";
      resetFilterDom();
      renderRecords();
    } else if (key) {
      state.visible = true;
      state.human = Boolean(ctx.human);
      state.role = ctx.role;
      state.serviceView = ctx.serviceView;
      state.serviceStatus = ctx.serviceStatus;
    } else {
      state.visible = false;
    }
    renderAll();
  }

  function detailCurrent(request) {
    return state.epoch === request.epoch && state.contextKey === request.contextKey
      && state.queryGeneration === request.generation && state.detailSeq === request.id
      && state.detail.open && state.detail.ref === request.ref
      && state.activeFilterKey === request.filterKey && canReadLogs();
  }
  function detailPath(ref) {
    return `/api/projects/${encodeURIComponent(state.projectId)}/roles/${encodeURIComponent(state.role.member_id)}/runtime-logs/${encodeURIComponent(ref)}/detail`;
  }
  function validateDetail(data, ref) {
    validateScope(data, "talk-runtime-log-detail-1");
    if (!data.record || data.record.log_id !== ref || !data.scan || data.scan.complete !== true) {
      throw responseError("日志详情未完成唯一、完整扫描，或引用与请求不一致。");
    }
    validateRecordScope(data.record);
    return data.record;
  }
  function appendFrameList(container, frames, omitted) {
    const list = makeEl("ol", "role-log-frames");
    for (const frame of Array.isArray(frames) ? frames : []) {
      const item = makeEl("li");
      const pre = makeEl("pre", "role-log-frame", `${showValue(frame && frame.file_name, "文件名未记录")}:${showValue(frame && frame.line, "行号未记录")} · ${showValue(frame && frame.function, "函数未记录")}`);
      item.appendChild(pre);
      list.appendChild(item);
    }
    if (!list.children.length) list.appendChild(makeEl("li", "role-log-empty-frame", "未记录堆栈帧。"));
    container.appendChild(list);
    if (Number(omitted) > 0) container.appendChild(makeEl("p", "role-log-omitted", `另有 ${Number(omitted)} 帧已省略或未记录；此处不补造。`));
  }
  function renderDetailRecord(record) {
    const content = byId("role-log-detail-content");
    if (!content) return;
    content.replaceChildren();
    setText("role-log-detail-title", `${formatTime(record.recorded_at)} · ${showValue(record.event)}`);
    setText("role-log-detail-ref", record.log_id);
    const summary = makeEl("section", "role-log-detail-section");
    summary.appendChild(makeEl("h4", "", "记录摘要"));
    summary.appendChild(makeEl("p", "", `级别：${severityText(record.severity)}；阶段：${showValue(record.stage)}`));
    summary.appendChild(makeEl("p", "", `${recordInstanceRelation(record).text}；启动：${showValue(record.launch_id)}；任务：${record.task_id === null || record.task_id === undefined ? "未记录" : `#${record.task_id}`}`));
    summary.appendChild(makeEl("p", "", integrityText(record.integrity, true)));
    summary.appendChild(makeEl("p", "", `返回码：${showValue(record.returncode)}；超时：${boolValue(record.timeout)}；取消类别：${showValue(record.cancel_category)}`));
    if (typeof record.related_log_id === "string" && LOG_REF_RE.test(record.related_log_id)) {
      const related = makeEl("p", "", `关联日志：${record.related_log_id} `);
      related.appendChild(makeButton("查询关联日志", () => {
        if (!canReadLogs()) return;
        const input = byId("role-log-ref");
        if (input) input.value = record.related_log_id;
        startRefQuery();
      }));
      summary.appendChild(related);
    }
    content.appendChild(summary);
    const budgets = makeEl("section", "role-log-detail-section");
    budgets.appendChild(makeEl("h4", "", "本次记录的实际预算（秒）"));
    const budgetLabels = {
      cli_timeout_seconds: "模型 CLI 超时", http_timeout_seconds: "HTTP 超时",
      task_lease_seconds: "任务租约", task_heartbeat_interval_seconds: "任务心跳间隔",
      managed_heartbeat_interval_seconds: "受管实例心跳间隔", task_poll_interval_seconds: "接单轮询间隔",
      mcp_wait_seconds: "MCP 单次等待",
    };
    for (const [key, label] of Object.entries(budgetLabels)) {
      budgets.appendChild(makeEl("p", "", `${label}：${showValue(record.budgets && record.budgets[key])}`));
    }
    content.appendChild(budgets);
    const exceptionSection = makeEl("section", "role-log-detail-section");
    exceptionSection.appendChild(makeEl("h4", "", "异常与因果链"));
    const exception = record.exception;
    if (exception === null || exception === undefined) {
      exceptionSection.appendChild(makeEl("p", "role-log-no-exception", "该事件没有异常堆栈。"));
    } else {
      exceptionSection.appendChild(makeEl("p", "role-log-exception-type", showValue(exception.type, "异常类型未记录")));
      const message = makeEl("pre", "role-log-detail-message", showValue(exception.message, "异常消息未记录"));
      exceptionSection.appendChild(message);
      exceptionSection.appendChild(makeEl("p", "", `空字符串：${boolValue(exception.str_empty)}；消息读取异常：${boolValue(exception.message_error)}；帧总数：${showValue(exception.frames_total, "0")}`));
      appendFrameList(exceptionSection, exception.frames, exception.frames_omitted);
      const chain = Array.isArray(exception.cause_chain) ? exception.cause_chain : [];
      if (!chain.length) exceptionSection.appendChild(makeEl("p", "", "未记录因果链。"));
      chain.forEach((cause, index) => {
        const box = makeEl("section", "role-log-cause");
        const relation = ({ explicit_cause: "显式原因", implicit_context: "隐式上下文" })[cause && cause.relation] || showValue(cause && cause.relation, "关系未记录");
        box.appendChild(makeEl("h5", "", `因果 ${index + 1} · ${relation}`));
        box.appendChild(makeEl("p", "", showValue(cause && cause.type, "异常类型未记录")));
        box.appendChild(makeEl("pre", "role-log-detail-message", showValue(cause && cause.message, "异常消息未记录")));
        box.appendChild(makeEl("p", "", `帧总数：${showValue(cause && cause.frames_total, "0")}；省略：${showValue(cause && cause.frames_omitted, "0")}`));
        appendFrameList(box, cause && cause.frames, 0);
        exceptionSection.appendChild(box);
      });
      exceptionSection.appendChild(makeEl("p", "", `链深度：${showValue(exception.chain_depth, "0")}；链截断：${boolValue(exception.chain_truncated)}；链循环：${boolValue(exception.chain_cycle)}`));
      exceptionSection.appendChild(makeEl("p", "", `显式原因：${boolValue(exception.has_explicit_cause)}；上下文存在：${boolValue(exception.context_present)}；上下文 suppressed：${boolValue(exception.context_suppressed)}`));
    }
    content.appendChild(exceptionSection);
    setText("role-log-detail-status", "仅显示已记录并执行脱敏的详情；不包含源码行或完整文件路径。");
  }
  async function performDetail(request) {
    const fetcher = apiFetcher();
    if (!fetcher) {
      if (detailCurrent(request)) setText("role-log-detail-status", apiErrorMessage(0, "network_error", request));
      return;
    }
    const controller = newAbortController();
    state.detailController = controller;
    try {
      const options = { method: "GET" };
      if (controller) options.signal = controller.signal;
      const response = await fetcher(detailPath(request.ref), options);
      if (!detailCurrent(request)) return;
      const body = await response.json().catch(() => null);
      if (!detailCurrent(request)) return;
      if (!response.ok) {
        setText("role-log-detail-status", apiErrorMessage(response.status, body && body.detail, request));
        return;
      }
      const record = validateDetail(body, request.ref);
      state.queried = true;
      addEvidenceRecords([record]);
      renderDetailRecord(record);
      renderEvidence();
    } catch (error) {
      if (!detailCurrent(request) || (error && error.name === "AbortError")) return;
      setText("role-log-detail-status", error && error.responseContract ? error.message : apiErrorMessage(0, "network_error", request));
    } finally {
      if (detailCurrent(request)) state.detailController = null;
    }
  }
  function openDetail(ref, trigger) {
    if (!canReadLogs() || !LOG_REF_RE.test(ref)) return;
    closeDetail({ restoreFocus: false });
    state.detail = { open: true, ref, returnFocus: trigger || (typeof document !== "undefined" ? document.activeElement : null) };
    const id = state.detailSeq;
    clearDetailContent();
    setText("role-log-detail-ref", ref);
    setText("role-log-detail-title", "正在读取日志详情");
    setText("role-log-detail-status", "正在读取详情…");
    openDetailDialog();
    const request = {
      id, ref, epoch: state.epoch, contextKey: state.contextKey,
      generation: state.queryGeneration, filterKey: state.activeFilterKey,
    };
    performDetail(request);
  }

  function bind(id, type, handler) {
    const node = byId(id);
    if (node) node.addEventListener(type, handler);
  }
  function bindEvents() {
    if (typeof document === "undefined") return;
    bind("role-log-view-btn", "click", startDefaultQuery);
    bind("role-log-filter-form", "submit", event => { if (event && event.preventDefault) event.preventDefault(); startFirstPage(); });
    bind("role-log-reset-btn", "click", resetToDefault);
    bind("role-log-ref-btn", "click", startRefQuery);
    bind("role-log-more-btn", "click", loadMore);
    bind("role-log-mode-errors", "click", () => { setSeverity(["error", "warning"]); filtersChanged(); });
    bind("role-log-mode-all", "click", () => { setSeverity(SEVERITIES); filtersChanged(); });
    const filterIds = [
      "role-log-time", "role-log-since", "role-log-until", "role-log-instance", "role-log-launch",
      "role-log-task", "role-log-event", "role-log-stage", "role-log-severity-error",
      "role-log-severity-warning", "role-log-severity-info",
    ];
    for (const id of filterIds) {
      bind(id, id === "role-log-time" || id === "role-log-instance" || id.includes("severity") ? "change" : "input", filtersChanged);
    }
    bind("role-log-detail-close", "click", () => closeDetail());
    bind("role-log-detail-dialog", "cancel", event => { if (event && event.preventDefault) event.preventDefault(); closeDetail(); });
    bind("role-log-detail-dialog", "close", () => { if (state.detail.open) closeDetail({ alreadyClosed: true }); });
    if (global && typeof global.addEventListener === "function") {
      global.addEventListener("pagehide", () => {
        sync({ visible: false });
      });
    }
  }
  bindEvents();

  const api = {
    sync,
    startDefaultQuery,
    startFirstPage,
    startRefQuery,
    loadMore,
    openDetail,
    closeDetail,
    resetToDefault,
    copyReference,
    recordInstanceRelation,
    apiErrorMessage,
    _state: state,
  };
  return api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));

if (typeof module !== "undefined" && module.exports) module.exports = roleDiagnostics;
