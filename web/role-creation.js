/* R1-4：页面只提交人类意图，凭据与文件由宿主处理。 */
function createRoleRequestUI(deps) {
  const state = { epoch: 0, key: "", active: false, loading: false, seq: 0, timer: null,
    host: null, rows: [], roles: [], supported: null, error: "", busy: false,
    modal: false, runners: [], choices: [], catalogSeq: 0, attempt: null, notice: "",
    recentKeys: [], limited: false, storageUnavailable: false, modelSeeds: [] };
  const el = id => deps.document.getElementById(id);
  const context = () => deps.context();
  const human = () => context().human === true;
  const current = epoch => state.active && epoch === state.epoch && context().active
    && state.key === JSON.stringify([context().projectId, context().accountId]);
  const base = () => `/api/projects/${encodeURIComponent(context().projectId)}`;
  const storageKey = () => `talk-role-intent:${state.key}`;
  const codes = {
    role_name_conflict: "这个角色名称已被使用，请换一个名称。",
    role_request_role_conflict: "这个角色已有待处理的配置请求。",
    role_name_invalid: "角色名称须为 1–64 个字符。",
    choice_retired: "这个模型选项已下架，请重新选择。",
    runner_retired: "这个运行器已下架，请重新选择。",
    role_provision_choice_changed: "模型配置已变化，请重新选择。",
    role_request_config_conflict: "宿主设置已被更新，请刷新后再操作。",
    role_request_revision_conflict: "配置进度已变化，请刷新后再操作。",
    role_request_member_created: "角色已创建，请从角色详情继续配置。",
    role_request_status_conflict: "当前进度不允许此操作，请刷新后查看。",
    role_request_role_in_use: "角色仍在使用中，请先关闭服务并处理在途任务。",
    manual_recovery_required: "本机接入凭据缺失，需要人工确认恢复。",
    role_key_foreign_refused: "本机存在来源不明的凭据文件，宿主已停止覆盖。",
    key_provenance_write_failed: "接入凭据已保存，来源记录未完成，可继续原配置。",
    worker_io_budget_exceeded: "本轮配置超时，可在租约结束后继续。",
    preflight_failed: "配置检查未通过，请核对宿主环境后继续。",
  };
  const safeInt = n => Number.isSafeInteger(n) && n >= 0;
  const lookup = (map, key, fallback) => Object.hasOwn(map, key) ? map[key] : fallback;
  const node = (tag, cls, text) => {
    const n = deps.document.createElement(tag); if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text; return n;
  };
  const button = (text, fn, cls = "role-service-button") => {
    const n = node("button", cls, text); n.type = "button";
    n.addEventListener("click", fn); return n;
  };
  function keepAttempt() {
    try {
      if (!deps.storage) { state.storageUnavailable = true; return; }
      if (state.attempt) deps.storage?.setItem(storageKey(), JSON.stringify(state.attempt));
      else deps.storage?.removeItem(storageKey());
    } catch (_) { state.storageUnavailable = true; /* 存储不可用时保留内存中的同一请求键。 */ }
  }
  const validRequestKey = key => typeof key === "string" && /^role-[a-zA-Z0-9_-]{8,120}$/.test(key);
  function restoreRecentKeys() {
    try {
      if (!deps.storage) { state.storageUnavailable = true; return; }
      const keys = JSON.parse(deps.storage.getItem(`${storageKey()}:saved`) || "[]");
      state.recentKeys = Array.isArray(keys) ? [...new Set(keys.filter(validRequestKey))].slice(0, 32) : [];
    } catch (_) { state.storageUnavailable = true; }
  }
  function remember(key) {
    if (!validRequestKey(key)) return;
    state.recentKeys = [key, ...state.recentKeys.filter(k => k !== key)].slice(0, 32);
    try { if (deps.storage) deps.storage.setItem(`${storageKey()}:saved`, JSON.stringify(state.recentKeys));
      else state.storageUnavailable = true;
    } catch (_) { state.storageUnavailable = true; }
  }
  function restoreAttempt() {
    try {
      const saved = JSON.parse(deps.storage?.getItem(storageKey()) || "null");
      if (saved && /^role-[a-zA-Z0-9_-]{8,120}$/.test(saved.key) && saved.payload?.kind === "create") {
        const p = saved.payload;
        if (Object.hasOwn(p, "auto_start") && ![true, false, null].includes(p.auto_start)) return;
        state.attempt = { key: saved.key, labels: { runner: String(saved.labels?.runner || "上次选择的运行器"),
          model: String(saved.labels?.model || "上次选择的模型") }, payload: { request_key: saved.key, kind: "create", confirm: true,
          role_name: String(p.role_name || ""), role_description: p.role_description == null ? null : String(p.role_description),
          runner_id: String(p.runner_id || ""), choice_id: String(p.choice_id || ""),
          // 原键重试必须保持旧载荷；不替旧请求补上自动启动意图。
          ...(Object.hasOwn(p, "auto_start") ? { auto_start: p.auto_start } : {}) } };
      }
    } catch (_) { state.attempt = null; }
  }
  async function api(path, body) {
    const response = await deps.api(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!response.ok) {
      let code = ""; try { const data = await response.json(); if (typeof data.detail === "string") code = data.detail; } catch (_) {}
      const error = new Error((Object.hasOwn(codes, code) ? codes[code] : null) || (response.status === 403 ? "只有真人账号可以修改角色配置。"
        : response.status === 404 ? "当前服务尚未提供此功能，请加载新版服务。" : `操作未完成（${response.status}），请刷新后重试。`));
      error.status = response.status; error.code = Object.hasOwn(codes, code) ? code : ""; throw error;
    }
    return response.json();
  }
  // 只保留公开事实；未知附加字段（包括任何凭据）不进入状态、DOM或存储。
  function publicRow(row) {
    const out = {};
    for (const key of ["request_key", "kind", "status", "effective_status", "revision", "role_name", "member_id",
      "credential_version", "lease_held", "retry_exhausted", "last_error_code", "created_at", "updated_at"]) out[key] = row[key];
    out.auto_start = row.auto_start === true;
    for (const key of ["auto_start_status", "auto_start_launch_id", "auto_start_error_code"]) {
      out[key] = typeof row[key] === "string" ? row[key] : null;
    }
    const job = row.provision_job;
    if (job && typeof job === "object") {
      out.provision_job = { status: job.status, steps: {} };
      for (const step of ["profile", "key_file", "preflight"]) {
        out.provision_job.steps[step] = { state: job.steps?.[step]?.state };
      }
    }
    return out;
  }
  function upsert(row) {
    if (!row || typeof row.request_key !== "string") return;
    const clean = publicRow(row);
    remember(clean.request_key);
    state.rows = [clean, ...state.rows.filter(r => r.request_key !== clean.request_key)];
  }
  function label(row) {
    if (row.retry_exhausted === true && row.lease_held !== true) return "等待人工继续";
    if (["requested", "leased", "created"].includes(row.status) && state.host?.enabled === false) return "等待开启宿主配置";
    if (row.status === "leased" && row.lease_held !== true && row.effective_status === "requested") return "等待宿主重新领取";
    return lookup({ requested: state.host?.enabled === false ? "等待开启宿主配置" : "等待宿主", leased: "宿主已领取",
      created: row.lease_held ? "正在配置" : "等待宿主继续配置", provisioned: "配置已完成", failed: "配置未完成", canceled: "已取消" }, row.status, "配置状态未知");
  }
  function autoStartFeedback(row) {
    // pending意图不能把配置失败/取消伪装成启动中；旧请求和恢复保持原反馈。
    if (row.kind !== "create" || row.auto_start !== true || row.status !== "provisioned") return null;
    if (row.auto_start_status === "enqueued") return {
      text: "自动启动请求已提交，实际运行状态请查看角色开关。", attention: false,
    };
    const reasons = {
      auto_start_control_kind_not_managed: "本次未执行自动启动：运行器的受管启动能力尚未确认。",
      auto_start_config_disabled: "本次未执行自动启动：宿主配置已关闭。",
      auto_start_manual_intent_present: "已保留手动启停操作，本次不再自动启动。",
      auto_start_enqueue_failed: "本次自动启动请求提交失败，请在角色开关核对后手动启动。",
    };
    const fallback = lookup({
      not_eligible: "本次未执行自动启动：启动条件未满足。当前状态请查看角色开关。",
      failed: "本次自动启动未完成，请在角色开关核对当前状态。",
    }, row.auto_start_status, "自动启动结果尚未确认，请刷新核对。" );
    return { text: lookup(reasons, row.auto_start_error_code, fallback), attention: true };
  }
  function canRecover(row) {
    return human() && safeInt(row.revision) && Boolean(row.member_id)
      && (row.status === "provisioned" || (row.status === "failed" && row.last_error_code === "manual_recovery_required"))
      && safeInt(row.credential_version) && row.credential_version > 0;
  }
  function resetControl(row) {
    const box = node("div", "role-reset-control");
    box.append(button("绑定重置", () => recover(row)),
      node("p", "role-reset-hint", "接入异常时修复本机配置，必要时更新接入凭据。"));
    box.children[0].disabled = state.busy;
    return box;
  }
  function progress(row, { showRoleLink = true } = {}) {
    const box = node("section", "role-request-card");
    box.append(node("strong", "", row.role_name || "角色配置"), node("p", "role-request-status", label(row)));
    const autoStart = autoStartFeedback(row);
    if (autoStart) box.append(node("p", "role-request-status", autoStart.text));
    if (row.provision_job) {
      const steps = node("ul", "role-request-steps");
      for (const [step, title] of [["profile", "身份档案"], ["key_file", "本机接入配置"], ["preflight", "配置检查"]]) {
        const status = lookup({ succeeded: "完成", skipped: "已核验", pending: "待处理", failed: "未完成" }, row.provision_job.steps?.[step]?.state, "未知");
        steps.append(node("li", "", `${title} · ${status}`));
      }
      box.append(steps);
    }
    if (row.status === "failed") box.append(node("p", "role-request-error", lookup(codes, row.last_error_code, "宿主未完成配置，请检查环境后继续。")));
    const actions = node("div", "role-request-actions");
    if (human() && safeInt(row.revision)) {
      if (!row.member_id && ["requested", "leased", "failed"].includes(row.status)) actions.append(button("取消创建", () => mutate(row, "cancel")));
      if ((row.status === "failed" && row.last_error_code !== "manual_recovery_required") || (row.retry_exhausted === true && row.lease_held !== true)) {
        actions.append(button("继续配置", () => mutate(row, "resume")));
      }
      if (canRecover(row)) actions.append(resetControl(row));
    }
    if (row.member_id && showRoleLink) actions.append(button("查看角色", () => { close(false); deps.selectRole(row.member_id); }));
    for (const child of actions.children) child.disabled = state.busy;
    box.append(actions); return box;
  }
  function render() {
    const list = el("role-request-list");
    if (list) {
      list.replaceChildren(); list.classList.toggle("hidden", !state.active);
      const waiting = state.rows.filter(r => !r.member_id && ["requested", "leased", "failed"].includes(r.status));
      if (state.error) list.append(node("p", "role-request-error", state.error));
      if (state.limited) list.append(node("p", "role-request-status", "配置记录较多，部分记录未显示；本页保存的请求会继续跟踪。"));
      for (const row of waiting) list.append(progress(row));
    }
    renderHost();
    renderModelSetup();
    const form = el("role-create-form"); if (!form) return;
    const pinned = Boolean(state.attempt);
    for (const id of ["role-create-runner", "role-create-model", "role-create-name", "role-create-description"]) {
      el(id).disabled = state.busy || pinned || Boolean(state.modalRow) || !human() || (id === "role-create-model" && !state.choices.length);
    }
    el("role-create-submit").disabled = state.busy || Boolean(state.modalRow) || !human() || state.supported !== true
      || (!pinned && (!el("role-create-runner").value || !el("role-create-model").value || !el("role-create-name").value.trim()));
    el("role-create-submit").textContent = state.busy ? "保存中…" : pinned ? "核对并重试保存" : "保存并配置";
    el("role-create-notice").textContent = state.notice + (state.attempt && state.storageUnavailable
      ? " 此浏览器无法保留待确认请求，请在关闭或刷新页面前核对保存结果。" : "");
    const result = el("role-create-result"); result.replaceChildren();
    if (state.modalRow) result.append(progress(state.modalRow));
  }
  function modelSeeds(agents, runner) {
    if (!Array.isArray(agents) || runner?.runtime !== "kimi-code") return [];
    const seeds = new Map();
    for (const agent of agents) {
      const b = agent.binding;
      if (agent.binding_state !== "bound" || !b || b.runner_id !== runner.runner_id || b.runtime !== runner.runtime) continue;
      if (!["model_id", "model_source", "provider_id", "connection_ref"].every(key => typeof b[key] === "string" && b[key].trim())) continue;
      if (!["builtin", "external"].includes(b.model_source)) continue;
      const payload = {};
      for (const key of ["model_id", "model_source", "provider_id", "connection_ref"]) payload[key] = b[key];
      payload.model_alias = typeof b.model_alias === "string" ? b.model_alias : "";
      payload.model_display_name = typeof b.model_display_name === "string" ? b.model_display_name : null;
      const fingerprint = JSON.stringify([payload.model_source, payload.provider_id, payload.connection_ref, payload.model_id, payload.model_alias]);
      if (!seeds.has(fingerprint)) seeds.set(fingerprint, { fingerprint, payload });
    }
    return [...seeds.values()];
  }
  function renderModelSetup() {
    const panel = el("role-create-model-setup"); if (!panel) return;
    panel.replaceChildren();
    const visible = state.modal && !state.choices.length && state.modelSeeds.length > 0 && !state.attempt && !state.modalRow;
    panel.classList.toggle("hidden", !visible); if (!visible) return;
    panel.append(node("p", "role-request-hint", "这个运行器尚无可选模型，可以登记本项目已保存的模型配置。登记不代表原生登录或服务启动已经通过。"));
    for (const seed of state.modelSeeds) {
      const name = seed.payload.model_display_name || seed.payload.model_alias || seed.payload.model_id;
      const action = button(`登记项目已有模型：${name}`, () => registerModel(seed), "role-service-button");
      action.disabled = state.busy || !human() || state.supported !== true; panel.append(action);
    }
  }
  function renderHost() {
    const panel = el("role-request-host-panel"); if (!panel) return;
    panel.classList.toggle("hidden", !state.active || !context().settings);
    el("role-request-host-status").textContent = state.error || (state.loading && !state.host ? "读取中…"
      : state.host ? state.host.enabled ? `配置已开启 · ${state.host.host_label || "宿主名称未提供"}` : "配置已暂停，创建请求会等待宿主。" : "宿主配置尚未读取。");
    const input = el("role-request-host-name");
    if (state.host && deps.document.activeElement !== input && !state.hostDirty) input.value = state.host.host_label || "";
    input.disabled = !human() || state.busy || !state.host || state.supported !== true;
    el("role-request-host-enable").textContent = state.host?.enabled ? "更新宿主" : "开启配置";
    el("role-request-host-enable").disabled = input.disabled || !input.value.trim() || !safeInt(state.host?.config_version)
      || (state.host?.enabled === true && input.value.trim() === state.host.host_label);
    el("role-request-host-disable").disabled = !human() || state.busy || state.host?.enabled !== true || !safeInt(state.host?.config_version);
  }
  function schedule() {
    if (state.timer !== null) deps.clearTimeout(state.timer);
    state.timer = null;
    if (state.active && state.supported && state.rows.some(r => ["requested", "leased", "created"].includes(r.status))) {
      state.timer = deps.setTimeout(() => { state.timer = null; refresh(); }, 3000);
    }
  }
  async function readRows(prefix, epoch, seq) {
    // 接口逐状态升序限量；分状态读取避免历史终态挤掉新在途请求。
    const groups = await Promise.all(["requested", "leased", "created", "failed", "provisioned", "canceled"]
      .map(status => api(`${prefix}/role-requests?limit=200&status=${status}`)));
    if (!current(epoch) || seq !== state.seq) return null;
    if (groups.some(rows => !Array.isArray(rows))) throw new Error("请求列表格式不完整。");
    const rows = new Map(groups.flat().map(row => [row.request_key, publicRow(row)]));
    // 本页已保存请求和上一轮在途请求按原键读取，跨终态/截断仍收敛到真实结果。
    const tracked = [...new Set([...state.recentKeys,
      ...state.rows.filter(row => ["requested", "leased", "created"].includes(row.status)).map(row => row.request_key)])];
    const missing = tracked.filter(key => !rows.has(key));
    const results = await Promise.all(missing.map(async key => {
      try {
        const row = await api(`${prefix}/role-requests/${encodeURIComponent(key)}`);
        if (row.request_key !== key) throw new Error("请求结果不匹配。");
        return publicRow(row);
      } catch (err) { if (err.status === 404) return null; throw err; }
    }));
    if (!current(epoch) || seq !== state.seq) return null;
    for (const row of results) if (row) rows.set(row.request_key, row);
    const priority = row => { const index = state.recentKeys.indexOf(row.request_key); return index < 0 ? state.recentKeys.length : index; };
    const ordered = [...rows.values()].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))
      || priority(a) - priority(b));
    return { rows: ordered, limited: groups.some(rows => rows.length >= 200) };
  }
  async function refresh() {
    if (!state.active) return;
    const epoch = state.epoch, seq = ++state.seq, prefix = base(); state.loading = true;
    try {
      const [host, requests, roles] = await Promise.all([api(`${prefix}/role-provision-host`), readRows(prefix, epoch, seq), api(`${prefix}/roles`)]);
      if (!current(epoch) || seq !== state.seq) return;
      if (!host || typeof host.enabled !== "boolean" || !requests || !Array.isArray(roles)) throw new Error("服务返回的配置事实不完整，请刷新后重试。");
      state.host = { enabled: host.enabled, host_label: host.host_label, config_version: host.config_version };
      state.rows = requests.rows; state.limited = requests.limited;
      state.roles = roles.map(r => ({ member_id: r.member_id, role_name: r.role_name, archived: r.archived }));
      state.supported = true; state.error = "";
      if (state.modalRow) state.modalRow = state.rows.find(r => r.request_key === state.modalRow.request_key) || state.modalRow;
      // 新成员由宿主创建后，重读既有名册；不制造临时member或伪造角色行。
      await deps.refreshRoster(); if (!current(epoch) || seq !== state.seq) return;
    } catch (err) {
      if (!current(epoch) || seq !== state.seq) return;
      state.error = err.status ? err.message : "配置进度暂时无法读取，请刷新重试。";
      if (err.status === 404) state.supported = false;
    } finally {
      if (current(epoch) && seq === state.seq) { state.loading = false; render(); deps.renderDetails(); schedule(); }
    }
  }
  function sync() {
    const c = context(), key = JSON.stringify([c.projectId, c.accountId]);
    if (state.active === Boolean(c.active) && state.key === key) { renderHost(); return; }
    if (state.timer !== null) deps.clearTimeout(state.timer);
    state.timer = null; ++state.epoch; ++state.seq; state.active = Boolean(c.active); state.key = key;
    Object.assign(state, { host: null, rows: [], roles: [], supported: null, error: "", busy: false, loading: false,
      attempt: null, modalRow: null, hostDirty: false, notice: "", runners: [], choices: [], recoveryAttempts: new Map(),
      recentKeys: [], limited: false, storageUnavailable: false, modelSeeds: [] });
    close(false); render();
    if (state.active) { restoreAttempt(); restoreRecentKeys(); refresh(); }
  }
  function fillSelect(id, values, title, key) {
    const select = el(id); select.replaceChildren();
    const empty = node("option", "", title); empty.value = ""; select.append(empty);
    for (const row of values) {
      const option = node("option", "", row.display_name || row.model_display_name || row.model_alias || row.model_id || row[key]);
      option.value = row[key]; select.append(option);
    }
    select.value = "";
  }
  async function open() {
    if (!state.active || !human()) return;
    state.modal = true; state.notice = ""; state.modalRow = null;
    state.modelSeeds = [];
    el("role-create-modal").classList.remove("hidden"); el("role-create-close").focus();
    const epoch = state.epoch, seq = ++state.catalogSeq;
    if (state.attempt) {
      el("role-create-name").value = state.attempt.payload.role_name;
      el("role-create-description").value = state.attempt.payload.role_description || "";
      fillSelect("role-create-runner", [{ runner_id: state.attempt.payload.runner_id, display_name: state.attempt.labels?.runner || "上次选择的运行器" }], "选择运行器", "runner_id");
      fillSelect("role-create-model", [{ choice_id: state.attempt.payload.choice_id, display_name: state.attempt.labels?.model || "上次选择的模型" }], "选择模型", "choice_id");
      el("role-create-runner").value = state.attempt.payload.runner_id;
      el("role-create-model").value = state.attempt.payload.choice_id;
      state.notice = "上次保存尚未确认，将用同一请求核对和重试。"; render(); return;
    }
    el("role-create-name").value = ""; el("role-create-description").value = "";
    state.choices = []; fillSelect("role-create-runner", [], "读取运行器…", "runner_id");
    fillSelect("role-create-model", [], "先选择运行器", "choice_id"); render();
    try {
      const rows = await api("/api/runners");
      if (!current(epoch) || !state.modal || seq !== state.catalogSeq) return;
      state.runners = Array.isArray(rows) ? rows.filter(r => ["adapted", "discoverable", "unverified"].includes(r.adapter_status))
        .map(r => ({ runner_id: r.runner_id, display_name: r.display_name, runtime: r.runtime, adapter_status: r.adapter_status, control_kind: r.control_kind })) : [];
      fillSelect("role-create-runner", state.runners, state.runners.length ? "选择运行器" : "暂无已登记的运行器", "runner_id");
    } catch (err) { if (current(epoch) && state.modal && seq === state.catalogSeq) state.notice = err.status ? err.message : "运行器目录读取失败，请关闭后重试。"; }
    if (current(epoch) && state.modal && seq === state.catalogSeq) render();
  }
  async function chooseRunner() {
    if (!human() || state.busy || state.attempt) return;
    const runner = el("role-create-runner").value, epoch = state.epoch, seq = ++state.catalogSeq;
    state.notice = ""; state.choices = []; state.modelSeeds = []; fillSelect("role-create-model", [], runner ? "读取模型…" : "先选择运行器", "choice_id"); render();
    if (!runner) return;
    try {
      const choices = await api(`/api/runners/${encodeURIComponent(runner)}/model-choices`);
      if (!current(epoch) || !state.modal || seq !== state.catalogSeq || el("role-create-runner").value !== runner) return;
      state.choices = Array.isArray(choices) ? choices.filter(c => c.runner_id === runner && !c.retired_at)
        .map(c => ({ choice_id: c.choice_id, runner_id: c.runner_id, model_display_name: c.model_display_name, model_alias: c.model_alias, model_id: c.model_id })) : [];
      fillSelect("role-create-model", state.choices, state.choices.length ? "选择模型" : "暂无可选模型", "choice_id");
      const fact = state.runners.find(r => r.runner_id === runner);
      if (fact && (fact.adapter_status !== "adapted" || fact.control_kind !== "managed_cli")) state.notice = "运行器接入或启停能力尚未确认；配置可以继续，自动启动须通过实际能力检查。";
      if (!state.choices.length) {
        if (fact?.runtime === "kimi-code") {
          const agents = await api(`${base()}/agents`);
          if (!current(epoch) || !state.modal || seq !== state.catalogSeq || el("role-create-runner").value !== runner) return;
          state.modelSeeds = modelSeeds(agents, fact);
        }
        if (!state.modelSeeds.length) state.notice = "这个运行器尚未登记可选模型，请管理员先准备模型目录。";
      }
    } catch (err) { if (current(epoch) && seq === state.catalogSeq) state.notice = err.status ? err.message : "模型目录读取失败，请重新选择运行器。"; }
    if (current(epoch) && seq === state.catalogSeq) render();
  }
  async function registerModel(seed) {
    if (!state.active || !state.modal || !human() || state.busy || state.attempt || state.modalRow || state.supported !== true || !state.modelSeeds.includes(seed)) return;
    const runnerId = el("role-create-runner").value, fact = state.runners.find(r => r.runner_id === runnerId);
    if (!fact || fact.runtime !== "kimi-code") return;
    const epoch = state.epoch, seq = state.catalogSeq, prefix = base(); state.busy = true; state.notice = "正在登记项目已有模型…"; render();
    const valid = () => current(epoch) && state.modal && seq === state.catalogSeq && el("role-create-runner").value === runnerId;
    try {
      const [agents, choices] = await Promise.all([api(`${prefix}/agents`), api(`/api/runners/${encodeURIComponent(runnerId)}/model-choices?include_retired=true`)]);
      if (!valid()) return;
      if (!modelSeeds(agents, fact).some(item => item.fingerprint === seed.fingerprint)) throw new Error("项目中的模型配置已变化，请重新选择运行器。");
      if (!Array.isArray(choices)) throw new Error("模型目录返回不完整，请重试。");
      const matching = choices.find(c => c.runner_id === runnerId && JSON.stringify([c.model_source, c.provider_id, c.connection_ref, c.model_id, c.model_alias || ""]) === seed.fingerprint);
      if (matching?.retired_at) throw new Error("此模型选项已下架，请联系管理员处理。");
      const result = matching || await api(`/api/runners/${encodeURIComponent(runnerId)}/model-choices`, seed.payload);
      if (!valid()) return;
      if (result.runner_id !== runnerId || !result.choice_id || result.retired_at
        || JSON.stringify([result.model_source, result.provider_id, result.connection_ref, result.model_id, result.model_alias || ""]) !== seed.fingerprint) throw new Error("登记结果尚未确认，请重新选择运行器核对模型目录。");
      state.choices = [{ choice_id: result.choice_id, runner_id: runnerId, model_display_name: result.model_display_name, model_alias: result.model_alias, model_id: result.model_id }];
      state.modelSeeds = []; fillSelect("role-create-model", state.choices, "选择模型", "choice_id");
      el("role-create-model").value = result.choice_id; state.notice = "模型目录已准备，可以填写角色名称并保存配置。登记不代表服务已启动。";
    } catch (err) { if (valid()) {
      const messages = ["项目中的模型配置已变化，请重新选择运行器。", "此模型选项已下架，请联系管理员处理。", "登记结果尚未确认，请重新选择运行器核对模型目录。"];
      state.notice = err.status ? err.message : messages.includes(err.message) ? err.message : "登记结果尚未确认，请重试；会先核对已有目录。";
    }
    } finally { if (current(epoch)) { state.busy = false; render(); } }
  }
  function close(focus = true) {
    state.modal = false; ++state.catalogSeq; el("role-create-modal")?.classList.add("hidden");
    if (focus && state.active) el("role-create-open")?.focus();
  }
  async function submit(event) {
    event?.preventDefault(); if (!state.active || !state.modal || !human() || state.busy || state.supported !== true) return;
    const epoch = state.epoch, prefix = base();
    if (!state.attempt) {
      const name = el("role-create-name").value.trim();
      // 与后端一致：空白先归null，非空白介绍保留原文及换行。
      const rawDescription = el("role-create-description").value;
      const description = /^[\u0009-\u000d\u001c-\u001f\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(rawDescription) ? null : rawDescription;
      const runner = el("role-create-runner").value, choice = el("role-create-model").value;
      if (!name || [...name].length > 64 || (description !== null && [...description].length > 2000) || !state.runners.some(r => r.runner_id === runner)
        || !state.choices.some(c => c.choice_id === choice && c.runner_id === runner)) { state.notice = "请选择运行器和模型，并填写 1–64 字的名称、最多 2000 字的介绍。"; render(); return; }
      let key; try { key = deps.newKey(); } catch (_) { state.notice = "无法生成请求标识，请重新加载页面后再试。"; render(); return; }
      const selectedModel = state.choices.find(c => c.choice_id === choice);
      state.attempt = { key, labels: { runner: state.runners.find(r => r.runner_id === runner)?.display_name || "已选运行器",
        model: selectedModel.model_display_name || selectedModel.model_alias || selectedModel.model_id || "已选模型" },
        payload: { request_key: key, kind: "create", confirm: true, auto_start: true,
        role_name: name, role_description: description, runner_id: runner, choice_id: choice } }; keepAttempt();
    }
    const attempt = state.attempt; state.busy = true; state.notice = ""; render();
    try {
      const row = await api(`${prefix}/role-requests`, attempt.payload);
      if (!current(epoch)) return;
      if (row.request_key !== attempt.key) throw new Error("保存结果尚未确认。");
      upsert(row); state.modalRow = publicRow(row); state.attempt = null; keepAttempt();
      state.notice = row.auto_start === true ? "请求已保存，配置完成后将尝试自动启动服务。"
        : attempt.payload.auto_start === true ? "请求已保存，当前服务未确认自动启动意图；配置完成后请核对角色开关。"
        : "原请求已保存，宿主会继续配置；本次未请求自动启动。";
      await refresh();
    } catch (err) {
      if (!current(epoch)) return;
      // 确定性4xx拒绝可修改表单；网络/5xx或响应异常必须保留原键和原载荷。
      const rejected = ["role_name_conflict", "role_name_invalid", "role_request_role_conflict", "choice_retired", "runner_retired", "role_provision_choice_changed"].includes(err.code);
      if (rejected || (err.status >= 400 && err.status < 500 && ![408, 409, 429].includes(err.status))) { state.attempt = null; keepAttempt(); }
      state.notice = err.status ? err.message : "保存结果尚未确认，请核对并重试；不会创建第二个请求。";
    } finally { if (current(epoch)) { state.busy = false; render(); schedule(); } }
  }
  async function mutate(row, action) {
    if (!state.active || !human() || state.busy || !safeInt(row.revision)) return;
    const epoch = state.epoch, prefix = base(); state.busy = true; render();
    try {
      const result = await api(`${prefix}/role-requests/${encodeURIComponent(row.request_key)}/${action}`,
        { expected_revision: row.revision, ...(action === "resume" ? { confirm: true } : {}) });
      if (!current(epoch)) return; upsert(result); await refresh();
    } catch (err) { if (current(epoch)) {
      const message = err.status ? err.message : "操作结果尚未确认，请刷新核对后重试。";
      await refresh(); if (current(epoch)) state.error = message;
    } }
    finally { if (current(epoch)) { state.busy = false; render(); deps.renderDetails(); } }
  }
  async function recover(row) {
    if (!state.active || !human() || state.busy || !safeInt(row.credential_version) || row.credential_version < 1) return;
    const savedKey = `talk-role-recover:${state.key}:${row.member_id}`;
    let intent;
    try { const saved = JSON.parse(deps.storage?.getItem(savedKey) || "null");
      if (saved && /^role-[a-zA-Z0-9_-]{8,120}$/.test(saved.key) && safeInt(saved.version) && saved.version > 0) intent = saved;
    } catch (_) {}
    intent ||= state.recoveryAttempts?.get(row.member_id);
    if (!intent && !deps.confirm("绑定重置将修复本机接入，必要时更新 TALK 凭据并使旧凭据失效，不更换运行器或模型。确认重置？")) return;
    intent ||= { key: deps.newKey(), version: row.credential_version };
    state.recoveryAttempts ||= new Map(); state.recoveryAttempts.set(row.member_id, intent);
    try { deps.storage?.setItem(savedKey, JSON.stringify({ key: intent.key, version: intent.version })); } catch (_) {}
    const epoch = state.epoch, prefix = base(); state.busy = true; render();
    // 恢复仅提交意图，不调用一次性Key接口；丢响应通过同一键读回，不自动另建恢复。
    try {
      const result = await api(`${prefix}/role-requests`, { request_key: intent.key, kind: "recover", confirm: true,
        member_id: row.member_id, expected_credential_version: intent.version });
      if (!current(epoch)) return;
      if (result.request_key !== intent.key) throw new Error("恢复结果未确认。");
      state.recoveryAttempts.delete(row.member_id);
      try { deps.storage?.removeItem(savedKey); } catch (_) {}
      upsert(result); await refresh();
    } catch (err) { if (current(epoch)) state.error = err.status ? err.message : "恢复结果尚未确认，请刷新后核对。"; }
    finally { if (current(epoch)) { state.busy = false; render(); deps.renderDetails(); schedule(); } }
  }
  async function setHost(enabled) {
    if (!state.active || !human() || state.busy || !safeInt(state.host?.config_version)) return;
    const label = el("role-request-host-name").value.trim(); if (enabled && (!label || [...label].length > 64)) return;
    const epoch = state.epoch, prefix = base(); state.busy = true; render();
    try {
      await api(`${prefix}/role-provision-host/${enabled ? "enable" : "disable"}`, {
        expected_version: state.host.config_version, ...(enabled ? { host_label: label } : {}),
      });
      if (!current(epoch)) return; state.hostDirty = false; await refresh();
    } catch (err) { if (current(epoch)) { state.error = err.status ? err.message : "设置结果尚未确认，请刷新核对。"; } }
    finally { if (current(epoch)) { state.busy = false; render(); } }
  }
  function rolePanel(role) {
    if (!state.active) return null;
    const row = state.rows.find(r => r.member_id === role.member_id);
    if (!row) return null;
    const panel = node("section", "role-maintenance");
    if (row.status !== "provisioned") {
      panel.append(node("p", row.status === "failed" ? "role-request-error" : "role-request-status", label(row)));
      if (row.status === "failed") panel.append(node("p", "role-request-error", lookup(codes, row.last_error_code, "本机配置未完成，请检查环境后继续。")));
      if (human() && safeInt(row.revision) && ((row.status === "failed" && row.last_error_code !== "manual_recovery_required") || (row.retry_exhausted === true && row.lease_held !== true))) {
        const resume = button("继续配置", () => mutate(row, "resume")); resume.disabled = state.busy; panel.append(resume);
      }
    }
    const autoStart = autoStartFeedback(row);
    if (autoStart?.attention) panel.append(node("p", "role-request-status", autoStart.text));
    if (canRecover(row)) panel.append(resetControl(row));
    return panel.children.length ? panel : null;
  }
  function attach() {
    el("role-create-form")?.addEventListener("submit", submit);
    el("role-create-runner")?.addEventListener("change", chooseRunner);
    for (const id of ["role-create-model", "role-create-name", "role-create-description"]) el(id)?.addEventListener("input", render);
    el("role-create-close")?.addEventListener("click", () => close());
    el("role-request-host-name")?.addEventListener("input", () => { state.hostDirty = true; renderHost(); });
    el("role-request-host-enable")?.addEventListener("click", () => setHost(true));
    el("role-request-host-disable")?.addEventListener("click", () => setHost(false));
    el("role-create-modal")?.addEventListener("keydown", event => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab") {
        const nodes = [...el("role-create-modal").querySelectorAll("button,input,select,textarea")].filter(n => !n.disabled);
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && deps.document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && deps.document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
  }
  function newButton() {
    if (!human()) return null;
    const n = button("创建角色", open, "role-service-button role-create-primary"); n.id = "role-create-open";
    n.disabled = state.supported === false; return n;
  }
  attach();
  return { state, sync, refresh, open, close, chooseRunner, registerModel, submit, mutate, recover, setHost, rolePanel, newButton,
    setRoleName: (id, name) => { const role = state.roles.find(r => r.member_id === id); if (role) role.role_name = name; },
    roleName: id => state.roles.find(r => r.member_id === id)?.role_name || "" };
}

const roleRequestApp = typeof document === "undefined" ? null : createRoleRequestUI({
  document, api: (path, options) => apiFetch(path, options),
  context: () => ({ projectId: activeProjectId, accountId: myId, human: currentMemberIsHuman(),
    active: Boolean(activeProjectId && myId && blackboardOpen && workspaceUI.mode === "roles"), settings: workspaceSettingsSelected() }),
  get storage() { try { return sessionStorage; } catch (_) { return null; } },
  newKey: () => { const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    return `role-${Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("")}`; },
  confirm: text => window.confirm(text), setTimeout, clearTimeout,
  refreshRoster: async () => { await loadProjectAgents(); },
  renderDetails: () => { renderWorkspaceList(); renderTaskDetailsPanel(); },
  selectRole: id => { workspaceUI.roleSelection = "role"; workspaceUI.selectedRole = id; renderWorkspaceList(); renderTaskDetailsPanel(); },
});
if (typeof module !== "undefined") module.exports = { createRoleRequestUI };
