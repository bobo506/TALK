/* R1-4：页面只提交人类意图，凭据与文件由宿主处理。 */
function createRoleRequestUI(deps) {
  const state = { epoch: 0, key: "", active: false, loading: false, seq: 0, timer: null,
    host: null, rows: [], roles: [], supported: null, error: "", busy: false,
    modal: false, runners: [], choices: [], catalogSeq: 0, attempt: null, notice: "",
    recentKeys: [], limited: false, storageUnavailable: false, modelSeeds: [],
    failureAlerts: new Set(),
    nativeSetups: new Map(), nativeBusy: new Set(), nativeErrors: new Map(), nativeReadSeq: new Map() };
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
    const service = state.roles.find(role => role.member_id === row.member_id)?.service;
    if (service?.observed === "running" && service.readiness_service === "ready") return {
      text: "角色配置已完成，服务已启动。", attention: false,
    };
    if (service?.observed === "failed") return {
      text: "角色配置已完成，但服务启动未完成。请查看角色，在角色详情中重试启动。", attention: true,
    };
    if (row.auto_start_status === "pending") {
      const setup = state.nativeSetups.get(row.member_id);
      if (setup?.status === "failed") return {
        text: `官方授权或模型准备未完成，自动启动未执行。${nativeErrorsText[setup.error_code] || "请在角色详情重试准备。"}`,
        attention: true,
      };
      if (setup?.status === "ready") return {
        text: "后台准备已完成，正在等待启动入队；也可在角色详情手动启动并核对真实状态。",
        attention: true,
      };
      return {
        text: row.auto_start_error_code === "native_authorization_required"
          ? "等待完成运行器官方授权与模型准备后自动启动。"
          : "等待后台准备完成后自动启动。", attention: false,
      };
    }
    if (row.auto_start_status === "enqueued") return {
      text: "自动启动请求已提交，实际运行状态请查看角色开关。", attention: false,
    };
    const reasons = {
      auto_start_control_kind_not_managed: "本次未执行自动启动：运行器的受管启动能力尚未确认。",
      auto_start_config_disabled: "本次未执行自动启动：宿主配置已关闭。",
      auto_start_manual_intent_present: "已保留手动启停操作，本次不再自动启动。",
      auto_start_enqueue_failed: "本次自动启动请求提交失败，请在角色开关核对后手动启动。",
      native_authorization_required: "请先完成运行器官方授权与所选模型准备，再手动启动角色。",
    };
    const fallback = lookup({
      not_eligible: "本次未执行自动启动：启动条件未满足。当前状态请查看角色开关。",
      failed: "本次自动启动未完成，请在角色开关核对当前状态。",
    }, row.auto_start_status, "自动启动结果尚未确认，请刷新核对。" );
    return { text: lookup(reasons, row.auto_start_error_code, fallback), attention: true };
  }
  const nativeErrorsText = {
    native_previous_process_unverified: "无法确认上次授权进程，尚未启动新授权，请检查原授权是否已结束。",
    native_previous_process_identity_changed: "上次授权进程的身份已变化，未停止其他进程，也未启动新授权。",
    native_previous_process_stop_unconfirmed: "尚未确认上次授权进程已退出，本次不会启动新授权，请稍后重试。",
    native_process_identity_unverified: "未能记录本次授权进程的身份，授权未继续，请重试。",
    native_process_scope_unavailable: "本次授权进程无法隔离管理，准备未继续，请检查运行环境后重试。",
    native_cli_missing: "运行 TALK 的电脑未找到已配置的运行器 CLI，请核对本机安装与运行器配置后重试。",
    native_role_busy: "角色仍在运行或配置被占用，请先正常关闭后重试。",
    native_model_configuration_required: "官方授权已返回，但所选模型尚未准备完成；请核对模型后重试。",
    native_model_selection_changed: "所选模型已变化，请重新完成官方授权与模型准备。",
    native_authorization_failed: "官方授权未完成，请重试；TALK 不会把进程退出当作授权成功。",
    native_authorization_canceled: "已取消本次官方授权，角色未启动。",
    native_setup_interrupted: "授权会话已中断，请重试；不会沿用未确认的授权结果。",
    native_cli_version_unsupported: "当前 Codex CLI 版本未适配，请核对本机运行器配置。",
    native_model_catalog_unavailable: "无法确认官方模型目录，请稍后重试。",
    native_selected_model_unavailable: "当前账号的官方模型目录未找到所选模型，请核对账号和模型选择。",
    native_setup_failed: "本机授权或模型准备失败，请检查环境后重试。",
  };
  function notifyFailure(key, roleName, detail) {
    if (!key || state.failureAlerts.has(key)) return;
    state.failureAlerts.add(key);
    const text = `角色「${roleName || "新角色"}」未完成：${detail}`;
    try { deps.alert?.(text); } catch (_) { /* 弹窗被浏览器拦截时保留列表内状态。 */ }
  }
  function nativePublic(row) {
    if (!row || typeof row !== "object") return null;
    return { member_id: row.member_id, choice_id: row.choice_id, status: row.status,
      revision: row.revision, authorization_code: typeof row.authorization_code === "string" ? row.authorization_code : null, authorization_url: typeof row.authorization_url === "string" ? row.authorization_url : null,
      error_code: typeof row.error_code === "string" ? row.error_code : null,
      requires_user_action: row.requires_user_action === true, can_start: row.can_start === true,
      can_cancel: row.can_cancel === true, updated_at: row.updated_at, completed_at: row.completed_at || null };
  }
  async function loadNativeSetup(role, epoch = state.epoch, paint = true) {
    const member = role?.member_id;
    if (!member || !human() || state.nativeBusy.has(member)) return;
    const seq = (state.nativeReadSeq.get(member) || 0) + 1;
    state.nativeReadSeq.set(member, seq);
    const fresh = () => current(epoch) && state.nativeReadSeq.get(member) === seq;
    try {
      const row = await api(`${base()}/roles/${encodeURIComponent(member)}/native-setup`);
      if (!fresh() || row.member_id !== member) return;
      const before = state.nativeSetups.get(member);
      const clean = nativePublic(row);
      if (clean) {
        state.nativeSetups.set(member, clean);
        const recent = state.rows.some(item => item.member_id === member && state.recentKeys.includes(item.request_key));
        if (clean.status === "failed" && (!before || before.status !== "failed") && (before || recent)) {
          const detail = nativeErrorsText[clean.error_code] || "官方授权或模型准备未完成，请查看角色详情后重试。";
          notifyFailure(`native:${member}:${clean.revision}`, role?.role_name, detail);
        }
      }
      state.nativeErrors.delete(member);
    } catch (err) {
      if (fresh()) state.nativeErrors.set(member, err.status ? err.message : "授权状态暂时无法读取，请稍后刷新。");
    } finally {
      if (paint && fresh()) { render(); deps.renderDetails(); schedule(); }
    }
  }
  async function mutateNativeSetup(role, action) {
    const member = role?.member_id, row = state.nativeSetups.get(member);
    if (!member || !row || state.nativeBusy.has(member) || !human()) return;
    state.nativeReadSeq.set(member, (state.nativeReadSeq.get(member) || 0) + 1);
    const epoch = state.epoch; state.nativeBusy.add(member); state.nativeErrors.delete(member); render();
    try {
      const result = await api(`${base()}/roles/${encodeURIComponent(member)}/native-setup/${action}`,
        { confirm: true, expected_revision: row.revision });
      if (!current(epoch) || result.member_id !== member) return;
      const clean = nativePublic(result); if (!clean) throw new Error("授权状态不完整。");
      state.nativeSetups.set(member, clean);
      await refresh();
    } catch (err) {
      if (current(epoch)) state.nativeErrors.set(member, err.status ? err.message : "授权结果尚未确认，请刷新后重试。");
    } finally {
      if (current(epoch)) { state.nativeBusy.delete(member); render(); schedule(); }
    }
  }
  function nativeSetup(role) {
    if (!human() || role?.archived || !["kimi-code", "codex"].includes(role?.runner?.runtime)) return null;
    const runnerName = role.runner.runtime === "codex" ? "Codex" : "Kimi Code";
    const member = role.member_id, setup = state.nativeSetups.get(member);
    if (setup?.status === "not_required") return null;
    const box = node("div", "role-reset-control role-native-setup");
    box.append(node("strong", "", `${runnerName} 官方授权与模型准备`));
    const labels = { required: "需官方授权", starting: "正在启动官方授权…",
      awaiting_authorization: "等待你在官方页面完成授权", finalizing: "正在角色独立环境准备所选模型…",
      ready: "官方授权与所选模型配置已完成", failed: "官方授权或模型准备未完成" };
    box.append(node("p", "role-request-status", labels[setup?.status] || "正在读取授权状态…"));
    const model = (runnerName === "Codex" ? role.model?.model_id : null)
      || role.model?.model_display_name || role.model?.model_alias || role.model?.model_id;
    if (model) box.append(node("p", "role-reset-hint", `所选模型：${model}`));
    if (runnerName === "Codex") box.append(node("p", "role-reset-hint", "思考强度使用准备时官方模型目录返回的默认值。"));
    if (setup?.authorization_url && setup.status === "awaiting_authorization") {
      const link = node("a", "role-service-button", `打开 ${runnerName} 官方授权页面`);
      link.href = setup.authorization_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      box.append(link);
      if (setup.authorization_code) box.append(node("p", "role-device-code", `在官方页面输入一次性验证码：${setup.authorization_code}`));
    }
    if (state.nativeErrors.has(member)) box.append(node("p", "role-request-error", state.nativeErrors.get(member)));
    if (setup?.error_code) box.append(node("p", "role-request-error", nativeErrorsText[setup.error_code] || "准备未完成，请刷新后重试。"));
    const actions = node("div", "role-request-actions");
    if (setup?.can_start) actions.append(button(setup.status === "failed" ? "重试官方授权" : "开始官方授权", () => mutateNativeSetup(role, "start")));
    if (setup?.can_cancel) actions.append(button("取消本次授权", () => mutateNativeSetup(role, "cancel")));
    actions.append(button("刷新授权状态", () => loadNativeSetup(role)));
    for (const child of actions.children) child.disabled = state.nativeBusy.has(member);
    box.append(actions);
    box.append(node("p", "role-reset-hint", `通过 ${runnerName} 官方流程授权。角色使用独立目录；保存后会在后台自动开始准备，完成后可在角色详情启动或关闭。${runnerName === "Codex" ? "设备码登录需先在 ChatGPT 安全设置或工作区权限中启用。" : ""}`));
    return box;
  }
  function canRecover(row) {
    return human() && safeInt(row.revision) && Boolean(row.member_id)
      && (row.status === "provisioned" || (row.status === "failed" && row.last_error_code === "manual_recovery_required"))
      && safeInt(row.credential_version) && row.credential_version > 0;
  }
  function resetButton(row) {
    const btn = button("绑定重置", () => recover(row));
    btn.disabled = state.busy;
    return btn;
  }
  function resetControl(row) {
    const box = node("div", "role-reset-control");
    box.append(resetButton(row),
      node("p", "role-reset-hint", "接入异常时修复本机配置，必要时更新接入凭据。"));
    return box;
  }
  // 2026-10-28：按用户要求把“绑定重置”移到角色详情服务行的第 4 个按钮位（删除角色之后），
  // 详情里不再重复渲染维护面板中的旧位置；仅保留按钮本身，不再带说明段落。
  // 2026-10-29 B1-a：旧角色（imported + 已提交补录记录）没有创建请求行，用角色自身的
  // recoverable / credential_version 生成同样的恢复请求；服务端按补录锚点校验。
  function resetButtonFor(memberId, role) {
    if (!state.active || !human()) return null;
    const row = state.rows.find(r => r.member_id === memberId);
    if (row && canRecover(row)) return resetButton(row);
    if (role && role.recoverable === true && Number.isInteger(role.credential_version)
        && role.credential_version > 0) {
      return resetButton({ member_id: memberId, credential_version: role.credential_version });
    }
    return null;
  }
  function progress(row, { showRoleLink = true } = {}) {
    const box = node("section", "role-request-card");
    box.append(node("strong", "", row.role_name || "角色配置"), node("p", "role-request-status", label(row)));
    const autoStart = autoStartFeedback(row);
    if (autoStart) box.append(node("p", "role-request-status", autoStart.text));
    const setup = nativeSetup(state.roles.find(role => role.member_id === row.member_id));
    if (setup && row.status === "provisioned") box.append(setup);
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
    if (["requested", "leased", "created"].includes(row.status)) {
      box.append(node("p", "role-request-status", state.host?.enabled === false
        ? "请求已保存，请先开启宿主配置后继续处理。可以关闭此窗口；请勿重复创建。"
        : "请求已保存，宿主会自动处理。可以关闭此窗口，稍后查看配置进度；请勿重复创建。"));
      actions.append(button("刷新进度", () => refresh()));
    }
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
    const selectedRunner = state.runners.find(r => r.runner_id === el("role-create-runner").value);
    const auto = el("role-create-auto-start");
    if (auto) { auto.disabled = state.busy || pinned || Boolean(state.modalRow) || !human() || selectedRunner?.runtime === "kimi-code";
      if (selectedRunner?.runtime === "kimi-code") auto.checked = false; }
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
    const runner = state.runners.find(row => row.runner_id === el("role-create-runner").value);
    // 2026-10-28：按用户要求移除 Codex 的默认强度说明行；本面板仍保持“对 Codex 不出模型种子列表”。
    if (state.modal && !state.attempt && !state.modalRow && runner?.runtime === "codex") {
      panel.classList.add("hidden");
      return;
    }
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
    if (state.active && state.supported && (state.rows.some(r => {
      if (["requested", "leased", "created"].includes(r.status)) return true;
      if (r.status !== "provisioned" || r.auto_start !== true) return false;
      if (r.auto_start_status === "pending") return true;
      if (r.auto_start_status !== "enqueued") return false;
      // 已投递后持续跟踪到真实 running/失败，用户无需手动刷新。
      const service = state.roles.find(role => role.member_id === r.member_id)?.service;
      return service?.observed !== "running" && service?.observed !== "failed";
    })
      || [...state.nativeSetups.entries()].some(([member, row]) => {
        if (!["required", "starting", "awaiting_authorization", "finalizing"].includes(row.status)) return false;
        if (state.roles.find(role => role.member_id === member)?.runner.runtime !== "codex") return false;
        return state.rows.some(item => item.member_id === member
          && (state.recentKeys.includes(item.request_key) || ["requested", "leased", "created"].includes(item.status)));
      }))) {
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
    const previousRows = new Map(state.rows.map(row => [row.request_key, row]));
    try {
      const [host, requests, roles] = await Promise.all([api(`${prefix}/role-provision-host`), readRows(prefix, epoch, seq), api(`${prefix}/roles`)]);
      if (!current(epoch) || seq !== state.seq) return;
      if (!host || typeof host.enabled !== "boolean" || !requests || !Array.isArray(roles)) throw new Error("服务返回的配置事实不完整，请刷新后重试。");
      state.host = { enabled: host.enabled, host_label: host.host_label, config_version: host.config_version };
      state.rows = requests.rows; state.limited = requests.limited;
      // 2026-10-29：同一成员已有更晚的成功请求时，更早的失败请求视为已被取代——既不弹
      // “未完成”，也从本页已保存请求里移除，避免刷新后反复提示旧失败。
      const provisionedAt = new Map();
      for (const row of requests.rows) {
        if (row.status !== "provisioned" || !row.member_id) continue;
        const at = String(row.created_at || "");
        if (!provisionedAt.has(row.member_id) || at > provisionedAt.get(row.member_id)) provisionedAt.set(row.member_id, at);
      }
      const superseded = new Set(requests.rows
        .filter(row => row.status === "failed" && provisionedAt.has(row.member_id)
          && String(row.created_at || "") < provisionedAt.get(row.member_id))
        .map(row => row.request_key));
      if (superseded.size && state.recentKeys.some(key => superseded.has(key))) {
        state.recentKeys = state.recentKeys.filter(key => !superseded.has(key));
        try { if (deps.storage) deps.storage.setItem(`${storageKey()}:saved`, JSON.stringify(state.recentKeys)); } catch (_) { /* 存储禁用时只影响下次刷新。 */ }
      }
      state.roles = roles.map(r => ({ member_id: r.member_id, role_name: r.role_name, archived: r.archived,
        runner: { runtime: r.runner?.runtime },
        model: r.model && typeof r.model === "object" ? {
          model_display_name: r.model.model_display_name, model_alias: r.model.model_alias, model_id: r.model.model_id,
        } : null,
        service: r.service && typeof r.service === "object" ? {
          observed: r.service.observed, readiness_service: r.service.readiness_service,
        } : null }));
      for (const row of state.rows) {
        const before = previousRows.get(row.request_key);
        const recent = state.recentKeys.includes(row.request_key);
        if (row.status === "failed" && !superseded.has(row.request_key) && (!before || before.status !== "failed") && (before || recent)) {
          notifyFailure(`request:${row.request_key}:${row.revision}`, row.role_name,
            lookup(codes, row.last_error_code, "后台配置未完成，请检查环境后继续。"));
        }
        if (row.status === "provisioned" && row.auto_start === true && row.auto_start_status === "failed"
            && (!before || before.auto_start_status !== "failed")) {
          notifyFailure(`auto:${row.request_key}:${row.revision}`, row.role_name,
            "角色已配置，但自动启动未完成；请在角色详情核对后重试启动。");
        }
      }
      state.supported = true; state.error = "";
      if (state.modalRow) state.modalRow = state.rows.find(r => r.request_key === state.modalRow.request_key) || state.modalRow;
      // 新成员由宿主创建后，重读既有名册；不制造临时member或伪造角色行。
      await deps.refreshRoster(); if (!current(epoch) || seq !== state.seq) return;
      await Promise.all(state.roles.filter(role => ["kimi-code", "codex"].includes(role.runner.runtime)).map(role => loadNativeSetup(role, epoch, false)));
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
      recentKeys: [], limited: false, storageUnavailable: false, modelSeeds: [], failureAlerts: new Set(),
      nativeSetups: new Map(), nativeBusy: new Set(), nativeErrors: new Map(), nativeReadSeq: new Map() });
    close(false); render();
    if (state.active) { restoreAttempt(); restoreRecentKeys(); refresh(); }
  }
  // 2026-10-28：Kimi Code 的历史登记名带模型与“执行”后缀（如“Kimi Code · K2.8 Preview 执行”）。
  // 角色列表已有同一套规范化（workspace.js 的 ROLE_BINDING_KIMI_CODE_LEGACY_NAMES），创建弹窗此前
  // 直接显示原始登记名；这里补齐为“Kimi Code”。只影响展示，不改登记数据或绑定。
  const KIMI_CODE_LEGACY_RUNNER_NAMES = new Set(["Kimi Code · K2.8 Preview 执行", "Kimi Code · K2.8 Preview"]);
  // 与 workspace.js 的 runnerNameWithoutCli 保持同一口径：运行器展示名去掉“CLI”字样。
  function stripRunnerCli(name) {
    const text = String(name || "").trim();
    if (!text) return text;
    return text.replace(/\s*内置\s*CLI\b/gi, " ").replace(/\bCLI\b/gi, " ").replace(/\s{2,}/g, " ").trim();
  }
  function runnerLabel(row) {
    const name = String(row?.display_name || "").trim();
    if (name && row?.runtime === "kimi-code" && KIMI_CODE_LEGACY_RUNNER_NAMES.has(name)) return "Kimi Code";
    return stripRunnerCli(name);
  }
  // 2026-10-28：创建角色时模型下拉只显示模型名；“· xhigh”这类强度后缀只用于列表展示，
  // 不在选择阶段出现（强度来源改为准备阶段落库的官方值）。
  const MODEL_STRENGTH_LITERALS = new Set(["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]);
  function modelLabel(row) {
    const display = String(row?.model_display_name || "").trim();
    if (display) {
      const cut = display.lastIndexOf("·");
      const head = cut >= 0 ? display.slice(0, cut).trim() : "";
      const tail = cut >= 0 ? display.slice(cut + 1).trim() : "";
      if (head && tail && MODEL_STRENGTH_LITERALS.has(tail.toLowerCase())) return head;
      return display;
    }
    return String(row?.model_alias || row?.model_id || row?.choice_id || "");
  }
  function fillSelect(id, values, title, key) {
    const select = el(id); select.replaceChildren();
    const empty = node("option", "", title); empty.value = ""; select.append(empty);
    for (const row of values) {
      const option = node("option", "", row.display_name ? runnerLabel(row) : modelLabel(row));
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
      if (el("role-create-auto-start")) el("role-create-auto-start").checked = state.attempt.payload.auto_start === true;
      fillSelect("role-create-runner", [{ runner_id: state.attempt.payload.runner_id, display_name: state.attempt.labels?.runner || "上次选择的运行器" }], "选择运行器", "runner_id");
      fillSelect("role-create-model", [{ choice_id: state.attempt.payload.choice_id, display_name: state.attempt.labels?.model || "上次选择的模型" }], "选择模型", "choice_id");
      el("role-create-runner").value = state.attempt.payload.runner_id;
      el("role-create-model").value = state.attempt.payload.choice_id;
      state.notice = "上次保存尚未确认，将用同一请求核对和重试。"; render(); return;
    }
    el("role-create-name").value = ""; el("role-create-description").value = "";
    if (el("role-create-auto-start")) el("role-create-auto-start").checked = false;
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
      // 2026-10-28：按用户要求移除未核验运行器的“接入或启停能力尚未确认”提示；
      // 能力事实仍由运行器/服务状态区展示，这里不再追加说明。
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
      // Kimi 仍须先完成页面内官方授权；Codex 允许保存自动启动意图，服务端会等
      // 后台设备授权/模型准备 ready 后再投递首次启动。
      const needsManualPreparation = state.runners.find(r => r.runner_id === runner)?.runtime === "kimi-code";
      state.attempt = { key, labels: { runner: runnerLabel(state.runners.find(r => r.runner_id === runner)) || "已选运行器",
        model: modelLabel(selectedModel) || "已选模型" },
        payload: { request_key: key, kind: "create", confirm: true,
        auto_start: !needsManualPreparation && el("role-create-auto-start")?.checked === true,
        role_name: name, role_description: description, runner_id: runner, choice_id: choice } }; keepAttempt();
    }
    const attempt = state.attempt; state.busy = true; state.notice = ""; render();
    try {
      const row = await api(`${prefix}/role-requests`, attempt.payload);
      if (!current(epoch)) return;
      if (row.request_key !== attempt.key) throw new Error("保存结果尚未确认。");
      upsert(row); state.modalRow = null; state.attempt = null; keepAttempt();
      // 保存受理即关闭创建页并回到真实角色列表；后台进度在列表/详情持续刷新。
      close(false);
      state.notice = row.auto_start === true ? "请求已保存，后台会自动完成添加、官方授权准备和反馈；准备完成后将按你的选择尝试自动启动。"
        : attempt.payload.auto_start === true ? "请求已保存，当前服务未确认自动启动意图；配置完成后请核对角色开关。"
        : "请求已保存，后台会自动完成添加与准备；保存不会自动启动角色。";
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
    const setup = nativeSetup(state.roles.find(item => item.member_id === role.member_id));
    if (setup && row.status === "provisioned") panel.append(setup);
    if (row.status !== "provisioned") {
      panel.append(node("p", row.status === "failed" ? "role-request-error" : "role-request-status", label(row)));
      if (row.status === "failed") panel.append(node("p", "role-request-error", lookup(codes, row.last_error_code, "本机配置未完成，请检查环境后继续。")));
      if (human() && safeInt(row.revision) && ((row.status === "failed" && row.last_error_code !== "manual_recovery_required") || (row.retry_exhausted === true && row.lease_held !== true))) {
        const resume = button("继续配置", () => mutate(row, "resume")); resume.disabled = state.busy; panel.append(resume);
      }
    }
    const autoStart = autoStartFeedback(row);
    if (autoStart) panel.append(node("p", "role-request-status", autoStart.text));
    // 2026-10-28：“绑定重置”已移到角色详情服务行，这里不再渲染；面板即使为空也返回，
    // 由 CSS `.role-maintenance:empty` 隐藏，避免调用方拿到 null 后改变既有渲染语义。
    return panel;
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
    resetButton: resetButtonFor,
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
  confirm: text => window.confirm(text), alert: text => window.alert(text),
  // 浏览器定时器要求 Window 接收者；不能经 deps.setTimeout 改成普通对象调用。
  setTimeout: (callback, delay) => window.setTimeout(callback, delay),
  clearTimeout: timer => window.clearTimeout(timer),
  refreshRoster: async () => { await loadProjectAgents(); },
  renderDetails: () => { renderWorkspaceList(); renderTaskDetailsPanel(); },
  selectRole: id => { workspaceUI.roleSelection = "role"; workspaceUI.selectedRole = id; renderWorkspaceList(); renderTaskDetailsPanel(); },
});
if (typeof module !== "undefined") module.exports = { createRoleRequestUI };
