/* 诊断日志导出：只在人类显式点击后生成一份 JSONL 文件；所有响应文本均按纯文本渲染。
   页面不展示日志/异常原文；导出按项目+角色跨实例，不按当前 launch 限制旧实例。
   状态文案精简：正常 idle/完整成功不堆说明，仅保留简短的生成中/错误/不完整反馈。 */
var roleDiagnostics = (function roleDiagnosticsModule(global) {
  "use strict";

  const EXPORT_SCHEMA = "talk-diagnostics-export-1";
  const EXPORT_CONTENT_TYPE = "application/x-ndjson";
  const MAX_META_LINE_BYTES = 64 * 1024;
  const MAX_EXPORT_BYTES = 16 * 1024 * 1024; // 包含 meta 的总长度
  const MAX_SPAN_MS = 31 * 86400000;
  const KNOWN_REASONS = new Set([
    "scan_incomplete", "source_changed", "malformed_records", "unavailable_records",
    "projection_failed", "record_limit", "byte_limit", "time_limit", "duplicate_log_id",
    "backend_coverage_unverified", "backend_missing_components", "backend_unavailable",
  ]);
  const SAFE_FILENAME_RE = /^talk-diagnostics_\d{8}T\d{6}Z_\d{8}T\d{6}Z\.jsonl$/;
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
    generating: false,
    requestSeq: 0,
    controller: null,
    blobUrl: null,
    fileName: null,
    meta: null,
    status: "",
    statusKind: "",
  };

  function byId(id) {
    return typeof document === "undefined" ? null : document.getElementById(id);
  }
  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = value === null || value === undefined ? "" : String(value);
  }
  function setHidden(id, hidden) {
    const node = byId(id);
    if (node) node.classList.toggle("hidden", Boolean(hidden));
  }
  // 导出按项目+角色跨实例聚合：上下文键不含当前 launch/实例身份，
  // 服务投影变化（含当前实例变化）不使已生成文件失效，也不触发重新生成。
  function contextKeyFor(ctx) {
    if (!ctx || !ctx.visible || !ctx.role || !ctx.role.member_id || !ctx.projectId || !ctx.accountId) return null;
    return JSON.stringify([ctx.projectId, ctx.accountId, ctx.role.member_id, Boolean(ctx.human)]);
  }
  function canExport() {
    return Boolean(state.visible && state.human && state.contextKey && state.projectId && state.role);
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
  function utf8Length(text) {
    const Encoder = global && global.TextEncoder;
    if (typeof Encoder === "function") return new Encoder().encode(text).length;
    return unescape(encodeURIComponent(text)).length;
  }

  function pad2(value) { return String(value).padStart(2, "0"); }
  function formatLocalInput(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }
  function resetRangeInputs() {
    const sinceInput = byId("role-export-since");
    const untilInput = byId("role-export-until");
    if (!sinceInput || !untilInput) return;
    const until = new Date();
    const since = new Date(until.getTime() - 86400000);
    sinceInput.value = formatLocalInput(since);
    untilInput.value = formatLocalInput(until);
  }
  // datetime-local 输入是操作人本地时间；提交时统一转成带时区的 UTC ISO。
  function parseLocalInput(value, label) {
    const text = String(value || "").trim();
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$/.test(text)) {
      throw localError(`${label}必须是有效的本地日期时间。`);
    }
    const ms = Date.parse(text); // 无时区的 date-time 按本地时间解析（ECMAScript 合同）
    if (!Number.isFinite(ms)) throw localError(`${label}必须是有效的本地日期时间。`);
    return new Date(ms).toISOString();
  }
  function validateRange() {
    const since = parseLocalInput(byId("role-export-since") && byId("role-export-since").value, "开始时间");
    const until = parseLocalInput(byId("role-export-until") && byId("role-export-until").value, "结束时间");
    const sinceMs = Date.parse(since);
    const untilMs = Date.parse(until);
    if (sinceMs >= untilMs) throw localError("开始时间必须早于结束时间。");
    if (untilMs - sinceMs > MAX_SPAN_MS) throw localError("导出时间跨度不能超过 31 天。");
    return { since, until };
  }
  function exportPath(since, until) {
    const params = new URLSearchParams({ since, until });
    return `/api/projects/${encodeURIComponent(state.projectId)}/roles/${encodeURIComponent(state.role.member_id)}/runtime-logs/export?${params.toString()}`;
  }

  function revokeBlob() {
    if (state.blobUrl) {
      const urlApi = global && global.URL;
      if (urlApi && typeof urlApi.revokeObjectURL === "function") {
        try { urlApi.revokeObjectURL(state.blobUrl); } catch (_) { /* 回收失败不影响状态清理 */ }
      }
    }
    state.blobUrl = null;
    state.fileName = null;
    state.meta = null;
  }
  function clearResult() {
    revokeBlob();
    renderResult();
  }

  function exportErrorMessage(status, detail) {
    const code = typeof detail === "string" ? detail : "";
    if (status === 401) return "登录已失效，请重新登录；本次未生成诊断文件。";
    if (status === 403) return "当前 Agent 账号没有诊断日志导出权限。";
    if (status === 404) return "项目或角色不存在，或该历史角色对不在可查范围。";
    if (status === 422) {
      return code === "invalid_filter"
        ? "导出参数不符合合同：开始/结束时间必须带时区、开始早于结束且跨度不超过 31 天。"
        : "导出参数不符合合同，请检查后重试。";
    }
    if (status === 503 && code === "diagnostics_unavailable") {
      return "暂时无法读取该角色的日志来源；这不表示角色已停止或没有异常。";
    }
    if (status === 503 && code === "diagnostics_projection_failed") {
      return "日志内容无法安全投影，未生成文件，也不展示原始记录或内部路径。";
    }
    if (status === 503) return "日志来源暂时不可用；这不表示角色已停止或没有异常。";
    return `诊断日志导出失败（HTTP ${status || "网络错误"}），请稍后重试；既有服务状态与启停操作不受影响。`;
  }

  function absoluteTime(value) {
    return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
      && Number.isFinite(Date.parse(value));
  }
  function validateExportMeta(meta, request) {
    if (!meta || typeof meta !== "object" || meta.kind !== "meta" || meta.schema !== EXPORT_SCHEMA) {
      throw responseError("导出响应首行不是合同要求的 meta 记录，已拒绝保存。");
    }
    if (!meta.scope || meta.scope.project_id !== state.projectId || meta.scope.member_id !== state.role.member_id) {
      throw responseError("导出文件的项目、角色与当前上下文不一致，已拒绝保存。");
    }
    const query = meta.query;
    if (!query || typeof query.since !== "string" || typeof query.until !== "string"
        || !absoluteTime(query.since) || !absoluteTime(query.until)) {
      throw responseError("导出文件缺少带时区的绝对查询时间，已拒绝保存。");
    }
    // query 时间允许 +00:00 与 Z 两种写法，按真实时间戳比较语义是否一致。
    if (Date.parse(query.since) !== Date.parse(request.since) || Date.parse(query.until) !== Date.parse(request.until)) {
      throw responseError("导出文件的查询区间与本次请求不一致，已拒绝保存。");
    }
    if (!absoluteTime(meta.generated_at)) {
      throw responseError("导出文件缺少有效的生成时间，已拒绝保存。");
    }
    if (!Number.isSafeInteger(meta.record_count) || meta.record_count < 0 || meta.record_count > 10000) {
      throw responseError("导出文件的记录数量无效，已拒绝保存。");
    }
    if (typeof meta.complete !== "boolean"
        || typeof meta.truncated !== "boolean") {
      throw responseError("导出文件缺少完整性标记，已拒绝保存。");
    }
    if (!Array.isArray(meta.reasons)
        || meta.reasons.some(reason => typeof reason !== "string" || !KNOWN_REASONS.has(reason))) {
      throw responseError("导出文件包含无法识别的不完整原因，已拒绝保存。");
    }
    const scan = meta.scan;
    const counters = ["scanned_files", "scanned_bytes", "malformed_lines", "unavailable_sources"];
    if (!scan || typeof scan.complete !== "boolean" || typeof scan.truncated !== "boolean"
        || counters.some(key => !Number.isSafeInteger(scan[key]) || scan[key] < 0)
        || (meta.complete && (meta.truncated || meta.reasons.length || !scan.complete || scan.truncated
          || scan.malformed_lines || scan.unavailable_sources))
        || (!meta.complete && !meta.reasons.length)) {
      throw responseError("导出文件的完整性标记缺失或相互矛盾，已拒绝保存。");
    }
    return meta;
  }
  // 文件名只接受已验证的安全服务端名；否则回退到本地按查询区间生成的固定日期名。
  function safeFileName(response, meta) {
    const header = response && response.headers && typeof response.headers.get === "function"
      ? response.headers.get("content-disposition")
      : null;
    const match = typeof header === "string" ? header.match(/filename="([^"]+)"/) : null;
    if (match && SAFE_FILENAME_RE.test(match[1])) return match[1];
    const compact = value => {
      const date = new Date(value);
      return `${date.getUTCFullYear()}${pad2(date.getUTCMonth() + 1)}${pad2(date.getUTCDate())}`
        + `T${pad2(date.getUTCHours())}${pad2(date.getUTCMinutes())}${pad2(date.getUTCSeconds())}Z`;
    };
    return `talk-diagnostics_${compact(meta.query.since)}_${compact(meta.query.until)}.jsonl`;
  }
  // 成功文案精简：完整（含完整零条）不堆范围/计数/扫描长句，下载入口可用即可；
  // 不完整必须保留简短提示，绝不静默显示为完整。
  function applySuccess(meta) {
    if (meta.complete) {
      state.status = "";
      state.statusKind = "";
    } else {
      state.status = "日志文件不完整。";
      state.statusKind = "warning";
    }
  }
  function applyError(status, detail) {
    state.status = exportErrorMessage(status, detail);
    state.statusKind = "error";
  }

  function isExportCurrent(request) {
    return state.epoch === request.epoch
      && state.contextKey === request.contextKey
      && state.requestSeq === request.seq
      && canExport();
  }
  // Read with an enforced byte cap. Only the bounded first line is decoded
  // and parsed; event bytes are copied verbatim into the downloadable Blob.
  async function readExportBody(response, request) {
    if (!response.body || typeof response.body.getReader !== "function") {
      throw responseError("当前环境不支持有界读取下载文件。");
    }
    const reader = response.body.getReader();
    const parts = [];
    const metaBytes = [];
    let block = new Uint8Array(65536), used = 0, total = 0;
    let firstLine = true, lineHasContent = false, eventCount = 0, meta = null;
    const parseMeta = () => {
      try {
        meta = JSON.parse(new global.TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(metaBytes)));
      } catch (_) {
        throw responseError("导出响应首行不是可解析的 meta JSON，已拒绝保存。");
      }
      validateExportMeta(meta, request);
    };
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (!isExportCurrent(request)) throw new Error("stale export");
        if (done) break;
        const chunk = new Uint8Array(value);
        total += chunk.byteLength;
        if (total > MAX_EXPORT_BYTES) throw responseError("导出文件超出有界大小上限，已拒绝保存。");
        for (const byte of chunk) {
          if (firstLine) {
            if (byte === 10) { parseMeta(); firstLine = false; }
            else {
              metaBytes.push(byte);
              if (metaBytes.length > MAX_META_LINE_BYTES) throw responseError("导出文件首行 meta 超过有界上限，已拒绝保存。");
            }
          } else if (byte === 10) {
            if (lineHasContent) eventCount += 1;
            lineHasContent = false;
          } else if (byte !== 13 && byte !== 9 && byte !== 32) lineHasContent = true;
          if (eventCount > 10000) throw responseError("导出文件的记录数量超出上限，已拒绝保存。");
        }
        let offset = 0;
        while (offset < chunk.length) {
          const count = Math.min(block.length - used, chunk.length - offset);
          block.set(chunk.subarray(offset, offset + count), used);
          used += count; offset += count;
          if (used === block.length) { parts.push(block); block = new Uint8Array(65536); used = 0; }
        }
      }
      if (firstLine) parseMeta();
      else if (lineHasContent) eventCount += 1;
      if (eventCount !== meta.record_count) throw responseError("导出文件的实际事件行数与 meta 记录数不一致，已拒绝保存。");
      if (used) parts.push(block.slice(0, used));
      return { parts, meta };
    } catch (error) {
      try { await reader.cancel(); } catch (_) { /* 保留原错误 */ }
      throw error;
    } finally {
      reader.releaseLock();
    }
  }
  async function performExport(request) {
    const fetcher = apiFetcher();
    const controller = newAbortController();
    state.controller = controller;
    try {
      if (!fetcher) throw new Error("request unavailable");
      const options = { method: "GET" };
      if (controller) options.signal = controller.signal;
      const response = await fetcher(exportPath(request.since, request.until), options);
      if (!isExportCurrent(request)) return;
      if (!response.ok) {
        // 错误体只取 detail 码做映射，绝不把错误 JSON 当文件保存。
        const body = await response.json().catch(() => null);
        if (!isExportCurrent(request)) return;
        applyError(response.status, body && body.detail);
        return;
      }
      const contentType = response.headers && typeof response.headers.get === "function"
        ? String(response.headers.get("content-type") || "")
        : "";
      if (contentType.split(";")[0].trim().toLowerCase() !== EXPORT_CONTENT_TYPE) {
        throw responseError("导出响应类型不是 application/x-ndjson，已拒绝保存。");
      }
      const file = await readExportBody(response, request);
      if (!isExportCurrent(request)) return;
      const meta = file.meta;
      const BlobCtor = global && global.Blob;
      const urlApi = global && global.URL;
      if (typeof BlobCtor !== "function" || !urlApi || typeof urlApi.createObjectURL !== "function") {
        throw responseError("当前环境不支持生成下载文件。");
      }
      state.fileName = safeFileName(response, meta);
      state.blobUrl = urlApi.createObjectURL(new BlobCtor(file.parts, { type: EXPORT_CONTENT_TYPE }));
      state.meta = meta;
      applySuccess(meta);
    } catch (error) {
      if (!isExportCurrent(request)) return;
      if (error && error.name === "AbortError") return;
      revokeBlob();
      if (error && error.responseContract) {
        state.status = error.message;
        state.statusKind = "error";
      } else {
        applyError(0, "network_error");
      }
    } finally {
      if (isExportCurrent(request)) {
        state.generating = false;
        state.controller = null;
        renderControls();
        renderStatus();
        renderResult();
      }
    }
  }
  function startExport() {
    if (!canExport() || state.generating) return false;
    clearResult();
    let range;
    try {
      range = validateRange();
    } catch (error) {
      state.status = error && error.localValidation ? `参数错误：${error.message}` : "无法构造导出请求。";
      state.statusKind = "error";
      renderControls();
      renderStatus();
      return false;
    }
    // 重新生成前清理旧文件并 revoke；防并发由 generating 与按钮禁用共同保证。
    clearResult();
    state.requestSeq += 1;
    state.generating = true;
    state.status = "正在生成诊断文件…";
    state.statusKind = "";
    renderControls();
    renderStatus();
    const request = {
      epoch: state.epoch,
      contextKey: state.contextKey,
      seq: state.requestSeq,
      since: range.since,
      until: range.until,
    };
    performExport(request);
    return true;
  }

  function renderControls() {
    setHidden("role-diagnostics-panel", !state.visible);
    const disabled = !canExport() || state.generating;
    for (const id of ["role-export-since", "role-export-until", "role-export-generate-btn"]) {
      const control = byId(id);
      if (control) control.disabled = disabled;
    }
    // 常态不放操作解释；仅在实际无权限（Agent 账号）时保留简短提示。
    setText("role-export-permission", state.human ? "" : "无导出权限");
  }
  function renderStatus() {
    const status = byId("role-export-status");
    if (status) {
      // 正常 idle/success 不堆状态说明：只有生成中/错误/不完整等必要反馈占用状态行。
      status.textContent = state.status;
      status.className = `role-export-status${state.statusKind ? ` ${state.statusKind}` : ""}`;
    }
  }
  // 下载入口在同一工具栏：生成前隐藏，生成成功才出现；无独立结果卡片。
  function renderResult() {
    const link = byId("role-export-download");
    const ready = Boolean(state.visible && state.blobUrl && state.meta);
    if (link) {
      link.classList.toggle("hidden", !ready);
      if (ready) {
        link.setAttribute("href", state.blobUrl);
        link.setAttribute("download", state.fileName);
      } else {
        link.setAttribute("href", "#");
        link.removeAttribute("download");
      }
    }
  }
  function renderAll() {
    renderControls();
    renderStatus();
    renderResult();
  }

  function sync(ctx) {
    const panel = byId("role-diagnostics-panel");
    if (!panel) return;
    const key = contextKeyFor(ctx);
    if (key !== state.contextKey) {
      // 上下文切换（角色/账号/项目/离页/退出）：作废在途请求、清旧文件并 revoke。
      state.epoch += 1;
      state.requestSeq += 1;
      abortController("controller");
      state.generating = false;
      state.contextKey = key;
      state.visible = Boolean(key);
      state.human = Boolean(key && ctx.human);
      state.projectId = key ? ctx.projectId : null;
      state.accountId = key ? ctx.accountId : null;
      state.role = key ? ctx.role : null;
      state.serviceView = key ? ctx.serviceView || null : null;
      state.serviceStatus = key ? ctx.serviceStatus || null : null;
      clearResult();
      state.status = "";
      state.statusKind = "";
      if (key) resetRangeInputs();
    } else if (key) {
      // 同角色服务轮询只更新投影：已生成文件保留，不重新生成、不自动再查。
      state.visible = true;
      state.human = Boolean(ctx.human);
      state.role = ctx.role;
      state.serviceView = ctx.serviceView || null;
      state.serviceStatus = ctx.serviceStatus || null;
    } else {
      state.visible = false;
    }
    renderAll();
  }

  function bind(id, type, handler) {
    const node = byId(id);
    if (node) node.addEventListener(type, handler);
  }
  function bindEvents() {
    if (typeof document === "undefined") return;
    bind("role-export-generate-btn", "click", startExport);
    for (const id of ["role-export-since", "role-export-until"]) {
      bind(id, "input", () => {
        if (state.generating) return;
        clearResult();
        state.status = "";
        state.statusKind = "";
        renderStatus();
      });
    }
    // 下载只由用户显式点击；无有效文件时阻止空跳转。
    bind("role-export-download", "click", event => {
      if (!state.blobUrl && event && event.preventDefault) event.preventDefault();
    });
    if (global && typeof global.addEventListener === "function") {
      global.addEventListener("pagehide", () => {
        sync({ visible: false });
      });
    }
  }
  bindEvents();

  const api = {
    sync,
    startExport,
    exportErrorMessage,
    _state: state,
  };
  return api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));

if (typeof module !== "undefined" && module.exports) module.exports = roleDiagnostics;
