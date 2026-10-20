/**
 * talk-dsh-context-capture
 *
 * Read-only, mountable capture of DSH's native `contextPressure` session
 * projection for the TALK execution-session kernel.
 *
 * This module is intentionally dependency-free (no filesystem, network,
 * process, timer, model or persistence side effects). It consumes only the
 * already-verified native Cordis services:
 *
 *   - `sessions.get(nativeSessionId)` — selected live session (never guessed
 *     from files, mtime, titles or "latest" lists);
 *   - `session.id`, `session.header.cwd`, `session.seq`, `session.eventAt(seq)`
 *     — identity/lifecycle/cut and the exact committed event timestamp;
 *   - `session.requestContext()` — latest native provider/model route record;
 *   - `sessionProjections.snapshot(session, ["contextPressure"])` — the exact
 *     current registry cut and selected view;
 *   - `sessionProjections.onChanged(...)` — optional native change feed used to
 *     associate each projected/pressure/capacity value with the exact event
 *     seq/time that changed it. No historical replay or file scan.
 *
 * Verified against the frozen installed sources `@deepseek-ai/dsh*@0.1.5-rc.2`:
 * token-meter `contextPressure` stateVersion=4, projection `snapshot` cut is
 * `session.seq - 1`, and `onChanged` receives `(session, key, value, seq)`.
 *
 * Deliberate limitations:
 *   - Source times are only known for changes observed after `track()`.
 *     Values already present at mount are reported as `unverified`, never
 *     backdated to the read time, a file mtime or callers' current clock.
 *   - `snapshot()` internally materializes every registered projection unit
 *     (not only `contextPressure`). That synchronous in-memory folding is
 *     native behavior; this module never checkpoints, exports or writes it.
 *   - Native numerator and capacity are independent last-wins slots. Their
 *     source times are tracked independently; this module does not claim one
 *     atomic request sample.
 *   - `cachedSnapshot()`, persisted checkpoints and cached projection rows are
 *     never used as current values.
 *   - Native home / launch / runner / project / model-binding identity cannot
 *     be proven from a Session object. They are recorded as caller-attested and
 *     must be attested by a trusted host caller; cross-process authentication is
 *     not implemented here.
 */

const SNAPSHOT_SCHEMA = "talk-dsh-context-snapshot-1";
const SNAPSHOT_SCHEMA_VERSION = 1;
const PRODUCER_MODULE = "dsh_context_capture";
const PRODUCER_VERSION = "1.0.0";
const PROJECTION_KEY = "contextPressure";
const EXPECTED_STATE_VERSION = 4;
const NATIVE_PACKAGE = "@deepseek-ai/dsh";
const NATIVE_FROZEN_VERSION = "0.1.5-rc.2";
const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;

const METRIC_FIELDS = Object.freeze([
  "projectedTokens",
  "pressureTokens",
  "contextWindow",
]);
const METRIC_FIELD_SET = new Set(METRIC_FIELDS);
const IDENTIFIER_CONTROL_RE = /[\x00-\x1f\x7f]/;

const STATIC_LIMITATIONS = Object.freeze([
  "source_times_tracked_only_after_mount",
  "snapshot_materializes_all_registered_projection_units",
  "usage_and_capacity_sources_update_independently",
  "captured_at_observation_is_not_source_time",
  "no_cross_process_authentication",
]);

class CaptureError extends Error {
  constructor(code, field) {
    super(`${field}: ${code}`);
    this.name = "CaptureError";
    this.code = code;
    this.field = field;
  }
}

function fail(code, field) {
  throw new CaptureError(code, field);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (Object.getPrototypeOf(value) === Object.prototype ||
      Object.getPrototypeOf(value) === null)
  );
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isSafeInteger(value, minimum = 0) {
  return (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= minimum &&
    value <= MAX_SAFE_INTEGER
  );
}

function isIdentifier(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 512 &&
    value === value.trim() &&
    !IDENTIFIER_CONTROL_RE.test(value) &&
    !/[\uD800-\uDFFF]/u.test(value)
  );
}

function isClockMs(value) {
  return isSafeInteger(value) && value >= 0 && value <= 8640000000000000;
}

function isoFromMs(ms) {
  if (!isClockMs(ms)) return null;
  try {
    return new Date(ms).toISOString();
  } catch {
    return null;
  }
}

function nowMsFromInput(value, clock) {
  if (value === undefined) {
    const fromClock = typeof clock === "function" ? clock() : Date.now();
    if (!isClockMs(fromClock)) fail("clock_invalid", "clock");
    return fromClock;
  }
  if (typeof value === "number" && isClockMs(value)) return value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed) && isClockMs(parsed)) return parsed;
  }
  fail("observed_at_invalid", "now");
}

function sourceTimeMs(session, seq) {
  if (!isSafeInteger(seq)) return null;
  try {
    if (typeof session.eventAt !== "function") return null;
    const event = session.eventAt(seq);
    if (!isPlainObject(event) || event.seq !== seq) return null;
    if (!isClockMs(event.time)) return null;
    return event.time;
  } catch {
    return null;
  }
}

function sourceObject(seq, timeMs) {
  if (!isSafeInteger(seq)) {
    return { kind: "native_projection_change", seq: null, time: null };
  }
  return {
    kind: "native_projection_change",
    seq,
    time: isoFromMs(timeMs),
  };
}

function sessionFacts(session) {
  return {
    id: session.id,
    cwd: session.header?.cwd,
    seq: session.seq,
    firstLiveSeq: session.firstLiveSeq,
  };
}

function projectionFacts(snapshot) {
  if (!isPlainObject(snapshot)) return null;
  return { asOfSeq: snapshot.asOfSeq, values: snapshot.values };
}

function describeInvalidNumber(value) {
  if (typeof value === "bigint") {
    const text = value.toString();
    return {
      raw_type: "bigint",
      raw_repr: text.length > 64 ? `${text.slice(0, 64)}...` : text,
    };
  }
  if (typeof value === "number") {
    let kind = "number";
    if (!Number.isFinite(value)) kind = "non_finite_number";
    else if (!Number.isInteger(value)) kind = "non_integer_number";
    return { raw_type: kind, raw_repr: String(value) };
  }
  if (typeof value === "boolean") {
    return { raw_type: "boolean", raw_repr: String(value) };
  }
  if (typeof value === "string") {
    return { raw_type: "string", raw_length: value.length };
  }
  return { raw_type: Array.isArray(value) ? "array" : typeof value, raw_repr: null };
}

function classifyInvalidField(value, kind) {
  if (typeof value === "boolean") return "value_boolean";
  if (typeof value === "bigint") return "value_bigint";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "value_non_finite";
    if (!Number.isInteger(value)) return "value_non_integer";
    if (value < 0) return "value_negative";
    if (value > MAX_SAFE_INTEGER) return "value_too_large";
    if (kind === "capacity" && value === 0) return "value_not_positive";
    return "value_invalid";
  }
  if (typeof value === "string") return "value_string";
  return "value_wrong_type";
}

function validFieldValue(value, kind) {
  if (!isSafeInteger(value)) return false;
  if (kind === "capacity") return value > 0;
  return true;
}

function readField(view, field, kind) {
  if (!hasOwn(view, field)) {
    return {
      present: false,
      valid: false,
      value: null,
      reason_code: "field_missing",
      raw: null,
    };
  }
  const raw = view[field];
  if (!validFieldValue(raw, kind)) {
    const reason = classifyInvalidField(raw, kind);
    return {
      present: true,
      valid: false,
      value: null,
      reason_code: reason,
      raw: describeInvalidNumber(raw),
    };
  }
  return {
    present: true,
    valid: true,
    value: raw,
    reason_code: "ok",
    raw: null,
  };
}

function newSourceSlot() {
  return { present: false, valid: false, value: null, seq: null, time: null, known: false };
}

function fieldSourcesFromView(view) {
  const sources = {};
  for (const field of METRIC_FIELDS) {
    const parsed = readField(view, field, field === "contextWindow" ? "capacity" : "tokens");
    sources[field] = {
      ...newSourceSlot(),
      present: parsed.present,
      valid: parsed.valid,
      value: parsed.valid ? parsed.value : null,
    };
  }
  return sources;
}

function configSnapshot(provider, model, seq, timeMs) {
  return {
    provider,
    model,
    seq: isSafeInteger(seq) ? seq : null,
    time: isClockMs(timeMs) ? timeMs : null,
    known:
      isIdentifier(provider) &&
      isIdentifier(model) &&
      isSafeInteger(seq) &&
      isClockMs(timeMs),
  };
}

function configFromRequestContext(session) {
  try {
    if (typeof session.requestContext !== "function") return null;
    const value = session.requestContext();
    if (!isPlainObject(value)) return null;
    return configSnapshot(value.provider, value.model, null, null);
  } catch {
    return null;
  }
}

function deepFreeze(value) {
  if (value === null || typeof value !== "object") return value;
  for (const key of Object.keys(value)) deepFreeze(value[key]);
  return Object.freeze(value);
}

function copyView(view) {
  if (!isPlainObject(view)) return null;
  const copy = {};
  for (const field of METRIC_FIELDS) {
    if (hasOwn(view, field)) copy[field] = view[field];
  }
  return copy;
}

function unknownMetric(reasonCode = "not_read") {
  return {
    state: "unknown",
    value: null,
    reason_code: reasonCode,
    source: null,
  };
}

function unknownConfig(reasonCode = "not_read") {
  return {
    state: "unknown",
    value: null,
    reason_code: reasonCode,
    source: null,
  };
}

function emptyMetrics(reasonCode = "not_read") {
  return {
    projected_tokens: unknownMetric(reasonCode),
    pressure_tokens: unknownMetric(reasonCode),
    context_window: unknownMetric(reasonCode),
  };
}

function hostBase(request) {
  if (!isPlainObject(request)) return null;
  return {
    project_id: request.projectId,
    target_member_id: request.targetMemberId,
    requester_id: request.requesterId,
    continuity_key: request.continuityKey,
    workspace_identity: request.workspaceIdentity,
    workspace_verified: false,
    native_home_namespace: request.nativeHomeNamespace,
    runner_id: request.runnerId,
    service_launch_id: request.serviceLaunchId,
    provider_id: request.providerId,
    model_id: request.modelId,
    model_binding_fingerprint: request.modelBindingFingerprint,
    config_permission_fingerprint: request.configPermissionFingerprint,
    attestation: {
      verified: false,
      source: null,
    },
    verification: {
      workspace: "unverified",
      native_home: "caller_attested",
      service_launch: "caller_attested",
      runner: "caller_attested",
      project_scope: "caller_attested",
      model_binding: "caller_attested",
    },
  };
}

function baseSnapshot(request, observedAt, reasonCode) {
  return {
    schema: SNAPSHOT_SCHEMA,
    schema_version: SNAPSHOT_SCHEMA_VERSION,
    producer: {
      module: PRODUCER_MODULE,
      version: PRODUCER_VERSION,
      native_contract: {
        package: NATIVE_PACKAGE,
        frozen_version: NATIVE_FROZEN_VERSION,
        projection_key: PROJECTION_KEY,
        expected_state_version: EXPECTED_STATE_VERSION,
        session_read_api: "sessions.get",
        projection_read_api: "sessionProjections.snapshot",
        change_feed_api: "sessionProjections.onChanged",
      },
    },
    observed_at: observedAt,
    host: hostBase(request),
    session: {
      native_session_id: request?.nativeSessionId ?? null,
      generation: request?.sessionGeneration ?? null,
      generation_source: null,
      lifecycle: { state: "unknown", source: null },
      session_seq: null,
      first_live_seq: null,
      revision: null,
      revision_source: "projection_cut",
      projection: {
        key: PROJECTION_KEY,
        authority: "registry_snapshot",
        expected_state_version: EXPECTED_STATE_VERSION,
        cut: null,
        session_seq: null,
        source: "sessionProjections.snapshot",
        cached_snapshot_used: false,
        checkpoint_used: false,
        materializes_all_registered_units: true,
      },
    },
    config: {
      provider_id: unknownConfig(),
      model_id: unknownConfig(),
      model_binding_fingerprint: {
        state: "caller_attested",
        value: request?.modelBindingFingerprint ?? null,
        reason_code: "caller_attested",
        source: null,
      },
      config_permission_fingerprint: {
        state: "caller_attested",
        value: request?.configPermissionFingerprint ?? null,
        reason_code: "caller_attested",
        source: null,
      },
    },
    metrics: emptyMetrics(),
    capture: {
      status: "unknown",
      reason_code: reasonCode,
      blocking_issues: [reasonCode],
      listeners: {
        projection_change: false,
        session_event: false,
        session_disposed: false,
      },
      limitations: [...STATIC_LIMITATIONS],
    },
  };
}

function normalizeTrackRequest(raw) {
  if (!isPlainObject(raw)) fail("request_invalid", "request");
  const stringFields = [
    "nativeSessionId",
    "projectId",
    "targetMemberId",
    "requesterId",
    "continuityKey",
    "workspaceIdentity",
    "workspacePath",
    "nativeHomeNamespace",
    "runnerId",
    "serviceLaunchId",
    "providerId",
    "modelId",
    "modelBindingFingerprint",
    "configPermissionFingerprint",
  ];
  const normalized = {};
  for (const field of stringFields) {
    const value = raw[field];
    if (!isIdentifier(value)) fail("identifier_invalid", field);
    normalized[field] = value;
  }
  if (!isSafeInteger(raw.sessionGeneration, 1)) {
    fail("generation_invalid", "sessionGeneration");
  }
  normalized.sessionGeneration = raw.sessionGeneration;
  const attestation = raw.hostAttestation;
  if (!isPlainObject(attestation) || attestation.verified !== true) {
    normalized.hostAttestation = null;
  } else if (!isIdentifier(attestation.source)) {
    normalized.hostAttestation = null;
  } else {
    normalized.hostAttestation = {
      verified: true,
      source: attestation.source,
    };
  }
  return normalized;
}

class ContextCapture {
  constructor(dependencies = {}) {
    this.sessions = dependencies.sessions;
    this.sessionProjections = dependencies.sessionProjections;
    this.subscribeSessionEvent =
      typeof dependencies.subscribeSessionEvent === "function"
        ? dependencies.subscribeSessionEvent
        : null;
    this.subscribeSessionDisposed =
      typeof dependencies.subscribeSessionDisposed === "function"
        ? dependencies.subscribeSessionDisposed
        : null;
    this.clock = typeof dependencies.clock === "function" ? dependencies.clock : Date.now;
    this.tracked = new Map();
    this.trackedById = new Map();
    this.disposers = [];
    this.listenersReady = false;
    this.listenerIssues = [];
    this.disposed = false;
  }

  _ensureListeners() {
    if (this.listenersReady || this.disposed) return;
    this.listenersReady = true;
    if (
      this.sessionProjections &&
      typeof this.sessionProjections.onChanged === "function"
    ) {
      try {
        const dispose = this.sessionProjections.onChanged((session, key, value, seq) => {
          this._onProjectionChanged(session, key, value, seq);
        });
        if (typeof dispose === "function") this.disposers.push(dispose);
        else this.listenerIssues.push("projection_change_disposer_missing");
      } catch {
        this.listenerIssues.push("projection_change_listener_unavailable");
      }
    } else {
      this.listenerIssues.push("projection_change_listener_unavailable");
    }
    if (this.subscribeSessionEvent) {
      try {
        const dispose = this.subscribeSessionEvent((session, event) => {
          this._onSessionEvent(session, event);
        });
        if (typeof dispose === "function") this.disposers.push(dispose);
        else this.listenerIssues.push("session_event_disposer_missing");
      } catch {
        this.listenerIssues.push("session_event_listener_unavailable");
      }
    } else {
      this.listenerIssues.push("session_event_listener_unavailable");
    }
    if (this.subscribeSessionDisposed) {
      try {
        const dispose = this.subscribeSessionDisposed((session) => {
          this._onSessionDisposed(session);
        });
        if (typeof dispose === "function") this.disposers.push(dispose);
        else this.listenerIssues.push("session_disposed_disposer_missing");
      } catch {
        this.listenerIssues.push("session_disposed_listener_unavailable");
      }
    }
  }

  _stopListeners() {
    for (const dispose of this.disposers) {
      try {
        dispose();
      } catch {
        // Dispose failures are contained; no raw error is exposed or stored.
      }
    }
    this.disposers = [];
    this.listenersReady = false;
    this.listenerIssues = [];
  }

  track(request) {
    if (this.disposed) fail("capture_disposed", "capture");
    const normalized = normalizeTrackRequest(request);
    const observedAt = isoFromMs(nowMsFromInput(undefined, this.clock));
    if (normalized.hostAttestation === null) {
      return this._unbound(normalized, "host_not_verified", observedAt);
    }
    if (!this.sessions || typeof this.sessions.get !== "function") {
      return this._unbound(normalized, "sessions_service_missing", observedAt);
    }
    if (
      !this.sessionProjections ||
      typeof this.sessionProjections.snapshot !== "function"
    ) {
      return this._unbound(normalized, "projection_service_missing", observedAt);
    }

    let session;
    try {
      session = this.sessions.get(normalized.nativeSessionId);
    } catch {
      return this._unbound(normalized, "session_lookup_failed", observedAt);
    }
    if (session === undefined || session === null) {
      return this._unbound(normalized, "session_not_live", observedAt);
    }
    let facts;
    try {
      facts = sessionFacts(session);
    } catch {
      return this._unbound(normalized, "session_unreadable", observedAt);
    }
    if (typeof session !== "object" || facts.id !== normalized.nativeSessionId) {
      return this._unbound(normalized, "session_id_mismatch", observedAt);
    }
    const cwd = facts.cwd;
    if (typeof cwd !== "string" || cwd !== normalized.workspacePath) {
      return this._unbound(normalized, "workspace_mismatch", observedAt);
    }
    if (!isSafeInteger(facts.seq)) {
      return this._unbound(normalized, "session_seq_invalid", observedAt);
    }
    if (this.trackedById.has(normalized.nativeSessionId)) {
      fail("session_already_tracked", "nativeSessionId");
    }

    let projectionSnapshot;
    try {
      projectionSnapshot = projectionFacts(this.sessionProjections.snapshot(session, [PROJECTION_KEY]));
    } catch {
      return this._unbound(normalized, "projection_snapshot_failed", observedAt);
    }
    if (
      !isPlainObject(projectionSnapshot) ||
      !isSafeInteger(projectionSnapshot.asOfSeq, -1) ||
      projectionSnapshot.asOfSeq < -1 ||
      !isPlainObject(projectionSnapshot.values)
    ) {
      return this._unbound(normalized, "projection_snapshot_invalid", observedAt);
    }

    let view;
    let baselineView;
    const baselineAnomalies = new Set();
    try {
      view = hasOwn(projectionSnapshot.values, PROJECTION_KEY)
        ? projectionSnapshot.values[PROJECTION_KEY]
        : null;
      baselineView = copyView(view);
      if (view !== null) {
        if (!isPlainObject(view)) baselineAnomalies.add("projection_view_invalid");
        else if (Object.keys(view).some((field) => !METRIC_FIELD_SET.has(field))) {
          baselineAnomalies.add("projection_unknown_fields");
        }
      }
    } catch {
      return this._unbound(normalized, "projection_view_unreadable", observedAt);
    }
    const handle = {
      kind: "talk-dsh-context-capture-handle-1",
      bound: true,
      reason_code: null,
      native_session_id: normalized.nativeSessionId,
      session_generation: normalized.sessionGeneration,
      session,
      request: normalized,
      lastView: baselineView,
      fieldSources: baselineView === null
        ? {
            projectedTokens: newSourceSlot(),
            pressureTokens: newSourceSlot(),
            contextWindow: newSourceSlot(),
          }
        : fieldSourcesFromView(baselineView),
      configSource: configFromRequestContext(session),
      lastProjectionSeq: null,
      lastSessionEventSeq: projectionSnapshot.asOfSeq,
      boundCut: projectionSnapshot.asOfSeq,
      highestCut: projectionSnapshot.asOfSeq,
      anomalies: baselineAnomalies,
      disposed: false,
      detached: false,
      bound_at: observedAt,
      dispose: () => this.untrack(handle),
    };
    this.tracked.set(session, handle);
    this.trackedById.set(normalized.nativeSessionId, handle);
    this._ensureListeners();
    return handle;
  }

  _unbound(request, reasonCode, observedAt) {
    const handle = {
      kind: "talk-dsh-context-capture-handle-1",
      bound: false,
      reason_code: reasonCode,
      native_session_id: request.nativeSessionId,
      session_generation: request.sessionGeneration,
      session: null,
      request,
      dispose: () => {},
    };
    return handle;
  }

  _onProjectionChanged(session, key, value, seq) {
    try {
      if (key !== PROJECTION_KEY) return;
      const handle = this.tracked.get(session);
      if (handle === undefined || handle.disposed) return;
      if (!isSafeInteger(seq)) {
        handle.anomalies.add("projection_event_seq_invalid");
        return;
      }
      if (seq <= handle.boundCut || seq >= session.seq) {
        handle.anomalies.add("projection_event_out_of_order");
        return;
      }
      if (
        handle.lastProjectionSeq !== null &&
        seq < handle.lastProjectionSeq
      ) {
        handle.anomalies.add("projection_event_out_of_order");
        return;
      }
      if (
        handle.lastProjectionSeq !== null &&
        seq === handle.lastProjectionSeq
      ) {
        const same = this._viewsEqual(handle.lastView, value);
        if (!same) handle.anomalies.add("projection_event_duplicate_conflict");
        return;
      }
      if (!isPlainObject(value)) {
        handle.anomalies.add("projection_view_invalid");
        return;
      }
      const extra = Object.keys(value).filter((field) => !METRIC_FIELD_SET.has(field));
      if (extra.length > 0) handle.anomalies.add("projection_unknown_fields");
      const time = sourceTimeMs(session, seq);
      for (const field of METRIC_FIELDS) {
        const kind = field === "contextWindow" ? "capacity" : "tokens";
        const next = readField(value, field, kind);
        const previous = handle.lastView === null
          ? null
          : readField(handle.lastView, field, kind);
        const changed =
          next.present !== (previous !== null && previous.present) ||
          !Object.is(
            next.valid ? next.value : null,
            previous !== null && previous.valid ? previous.value : null,
          );
        if (!changed) continue;
        handle.fieldSources[field] = {
          present: next.present,
          valid: next.valid,
          value: next.valid ? next.value : null,
          seq,
          time,
          known: next.valid && next.present && time !== null,
        };
      }
      handle.lastView = copyView(value);
      handle.lastProjectionSeq = seq;
      if (seq > handle.highestCut) handle.highestCut = seq;
    } catch {
      const handle = this.tracked.get(session);
      if (handle !== undefined) handle.anomalies.add("projection_listener_error");
    }
  }

  _onSessionEvent(session, event) {
    try {
      const handle = this.tracked.get(session);
      if (handle === undefined || handle.disposed) return;
      if (!isPlainObject(event) || !isSafeInteger(event.seq)) {
        handle.anomalies.add("session_event_invalid");
        return;
      }
      if (
        typeof session.eventAt !== "function" ||
        session.eventAt(event.seq) !== event ||
        event.seq <= handle.boundCut || event.seq >= session.seq
      ) {
        handle.anomalies.add("session_event_invalid");
        return;
      }
      if (event.seq === handle.lastSessionEventSeq) return;
      if (event.seq !== handle.lastSessionEventSeq + 1) {
        handle.anomalies.add("session_event_out_of_order");
        return;
      }
      if (
        handle.lastSessionEventSeq !== null &&
        event.seq < handle.lastSessionEventSeq
      ) {
        handle.anomalies.add("session_event_out_of_order");
        return;
      }
      handle.lastSessionEventSeq = event.seq;
      if (event.type !== "request/context") return;
      const data = isPlainObject(event.data) ? event.data : null;
      const time = isClockMs(event.time) ? event.time : null;
      const nextConfig = data === null
        ? { provider: null, model: null, seq: event.seq, time, known: false }
        : configSnapshot(data.provider, data.model, event.seq, time);
      const previous = handle.configSource;
      if (previous === null) {
        // No provider/model was present at mount: this is the first observed
        // config record, so its event time is a valid source.
        handle.configSource = nextConfig;
      } else if (previous.known === true) {
        // Keep the original source time on unrelated request/context events;
        // only an actual provider/model change gets a new source.
        if (
          previous.provider !== nextConfig.provider ||
          previous.model !== nextConfig.model
        ) {
          handle.configSource = nextConfig;
        }
      } else if (
        previous.provider !== nextConfig.provider ||
        previous.model !== nextConfig.model
      ) {
        // A config existed before mount but its source time is unverifiable.
        // A later same-value repeat must NOT backdate it into a known source;
        // only an observed provider/model change gives a new known source.
        handle.configSource = nextConfig;
      }
      // A request/context event can also be appended for a capacity or
      // system-prompt change while provider/model stay the same. In that case
      // its timestamp is NOT a new provider/model source time; keep the older
      // known source (or the unknown baseline) instead of refreshing it.
      if (nextConfig.known !== true) {
        handle.anomalies.add("request_context_invalid");
      }
    } catch {
      const handle = this.tracked.get(session);
      if (handle !== undefined) handle.anomalies.add("session_listener_error");
    }
  }

  _onSessionDisposed(session) {
    const handle = this.tracked.get(session);
    if (handle !== undefined) handle.disposed = true;
  }

  _viewsEqual(left, right) {
    if (!isPlainObject(left) || !isPlainObject(right)) {
      return left === right;
    }
    for (const field of METRIC_FIELDS) {
      const leftHas = hasOwn(left, field);
      const rightHas = hasOwn(right, field);
      if (leftHas !== rightHas) return false;
      if (leftHas && !Object.is(left[field], right[field])) return false;
    }
    return true;
  }

  read(handle, options = {}) {
    const nowMs = nowMsFromInput(options.now, this.clock);
    const observedAt = isoFromMs(nowMs);
    let previousCut = null;
    if (options.previousCut !== undefined) {
      if (!isSafeInteger(options.previousCut, -1) || options.previousCut < -1) {
        fail("previous_cut_invalid", "previousCut");
      }
      previousCut = options.previousCut;
    }
    if (options.sessionGeneration !== undefined) {
      if (!isSafeInteger(options.sessionGeneration, 1)) {
        fail("generation_invalid", "sessionGeneration");
      }
    }

    if (this.disposed) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "capture_disposed");
    }
    if (!isPlainObject(handle) || handle.kind !== "talk-dsh-context-capture-handle-1") {
      fail("handle_invalid", "handle");
    }
    if (handle.bound !== true) {
      return this._unknownSnapshotFromHandle(handle, observedAt, handle.reason_code);
    }
    if (handle.detached) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "handle_detached");
    }
    if (handle.disposed) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_disposed");
    }
    if (this.tracked.get(handle.session) !== handle) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "handle_not_owned");
    }
    if (
      options.sessionGeneration !== undefined &&
      options.sessionGeneration !== handle.session_generation
    ) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "generation_mismatch");
    }

    let live;
    try {
      live = this.sessions && typeof this.sessions.get === "function"
        ? this.sessions.get(handle.native_session_id)
        : undefined;
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_lookup_failed");
    }
    if (live === undefined || live === null) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_not_live");
    }
    if (live !== handle.session) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_replaced");
    }
    let facts;
    try {
      facts = sessionFacts(live);
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_unreadable");
    }
    if (facts.id !== handle.native_session_id) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_id_mismatch");
    }
    const cwd = facts.cwd;
    if (typeof cwd !== "string" || cwd !== handle.request.workspacePath) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "workspace_mismatch");
    }
    if (!isSafeInteger(facts.seq)) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_seq_invalid");
    }
    if (
      handle.lastSessionEventSeq !== null &&
      facts.seq - 1 < handle.lastSessionEventSeq
    ) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "revision_regressed");
    }
    if (
      handle.anomalies.has("projection_event_out_of_order") ||
      handle.anomalies.has("projection_event_duplicate_conflict") ||
      handle.anomalies.has("session_event_out_of_order")
    ) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "revision_anomaly");
    }
    if (handle.anomalies.has("projection_unknown_fields")) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_unknown_fields");
    }
    if (handle.anomalies.has("projection_view_invalid")) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_view_invalid");
    }

    let projectionSnapshot;
    const seqBefore = facts.seq;
    try {
      projectionSnapshot = projectionFacts(this.sessionProjections.snapshot(live, [PROJECTION_KEY]));
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_snapshot_failed");
    }
    if (
      !isPlainObject(projectionSnapshot) ||
      !isSafeInteger(projectionSnapshot.asOfSeq, -1) ||
      projectionSnapshot.asOfSeq < -1 ||
      !isPlainObject(projectionSnapshot.values)
    ) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_snapshot_invalid");
    }
    let seqAfter;
    try {
      seqAfter = live.seq;
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_lookup_failed");
    }
    if (!isSafeInteger(seqAfter) || seqAfter !== seqBefore) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "session_changed_during_read");
    }

    const cut = projectionSnapshot.asOfSeq;
    if (cut < 0) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_empty");
    }
    if (cut + 1 !== seqAfter) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_cut_inconsistent");
    }
    if (previousCut !== null && cut < previousCut) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "revision_regressed");
    }
    if (cut < handle.highestCut) {
      return this._unknownSnapshotFromHandle(handle, observedAt, "revision_regressed");
    }
    handle.highestCut = cut;

    let view;
    try {
      view = hasOwn(projectionSnapshot.values, PROJECTION_KEY)
        ? projectionSnapshot.values[PROJECTION_KEY]
        : null;
      if (!isPlainObject(view)) {
        return this._unknownSnapshotFromHandle(handle, observedAt, "projection_missing");
      }
      const extra = Object.keys(view).filter((field) => !METRIC_FIELD_SET.has(field));
      if (extra.length > 0) {
        return this._unknownSnapshotFromHandle(handle, observedAt, "projection_unknown_fields");
      }
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_view_unreadable");
    }

    // Resolve each field against the source slot of THIS handle. The helper
    // below receives the handle explicitly to avoid cross-session mixing.
    let projected;
    let pressure;
    let capacity;
    try {
      const resolveFor = (field) => this._resolveMetricForHandle(handle, field, view, nowMs);
      projected = resolveFor("projectedTokens");
      pressure = resolveFor("pressureTokens");
      capacity = resolveFor("contextWindow");
    } catch {
      return this._unknownSnapshotFromHandle(handle, observedAt, "projection_view_unreadable");
    }
    const config = this._resolveConfigForHandle(handle, live, nowMs);

    const blocking = [];
    if (handle.anomalies.has("request_context_invalid")) {
      blocking.push("request_context_invalid");
    }
    if (handle.anomalies.has("session_event_invalid")) {
      blocking.push("session_event_invalid");
    }
    if (handle.anomalies.has("session_listener_error")) {
      blocking.push("session_listener_error");
    }
    if (handle.anomalies.has("projection_listener_error")) {
      blocking.push("projection_listener_error");
    }
    if (handle.anomalies.has("projection_event_seq_invalid")) {
      blocking.push("projection_event_seq_invalid");
    }

    const host = hostBase(handle.request);
    host.workspace_verified = true;
    host.attestation = {
      verified: true,
      source: handle.request.hostAttestation.source,
    };
    host.verification = {
      workspace: "native_header_cwd_exact_match",
      native_home: "caller_attested",
      service_launch: "caller_attested",
      runner: "caller_attested",
      project_scope: "caller_attested",
      model_binding: "caller_attested",
    };

    const configState = {
      provider_id: config.provider_id,
      model_id: config.model_id,
      model_binding_fingerprint: {
        state: "caller_attested",
        value: handle.request.modelBindingFingerprint,
        reason_code: "caller_attested",
        source: null,
      },
      config_permission_fingerprint: {
        state: "caller_attested",
        value: handle.request.configPermissionFingerprint,
        reason_code: "caller_attested",
        source: null,
      },
    };

    const metrics = {
      projected_tokens: projected,
      pressure_tokens: pressure,
      context_window: capacity,
    };
    const metricReady =
      pressure.state === "known" &&
      (projected.state === "known" || projected.state === "missing") &&
      capacity.state === "known" &&
      config.provider_id.state === "known" &&
      config.model_id.state === "known";
    let status = "partial";
    let reasonCode = "source_time_unknown";
    if (blocking.length > 0) {
      status = "unknown";
      reasonCode = blocking[0];
    } else if (metricReady) {
      status = "available";
      reasonCode = null;
    }

    const snapshot = {
      schema: SNAPSHOT_SCHEMA,
      schema_version: SNAPSHOT_SCHEMA_VERSION,
      producer: {
        module: PRODUCER_MODULE,
        version: PRODUCER_VERSION,
        native_contract: {
          package: NATIVE_PACKAGE,
          frozen_version: NATIVE_FROZEN_VERSION,
          projection_key: PROJECTION_KEY,
          expected_state_version: EXPECTED_STATE_VERSION,
          session_read_api: "sessions.get",
          projection_read_api: "sessionProjections.snapshot",
          change_feed_api: "sessionProjections.onChanged",
        },
      },
      observed_at: observedAt,
      host,
      session: {
        native_session_id: handle.native_session_id,
        generation: handle.session_generation,
        generation_source: "caller_bound_live_session",
        lifecycle: { state: "live", source: "sessions.get" },
        session_seq: seqAfter,
        first_live_seq: isSafeInteger(facts.firstLiveSeq) ? facts.firstLiveSeq : null,
        revision: cut,
        revision_source: "projection_cut",
        projection: {
          key: PROJECTION_KEY,
          authority: "registry_snapshot",
          expected_state_version: EXPECTED_STATE_VERSION,
          cut,
          session_seq: seqAfter,
          source: "sessionProjections.snapshot",
          cached_snapshot_used: false,
          checkpoint_used: false,
          materializes_all_registered_units: true,
        },
      },
      config: configState,
      metrics,
      capture: {
        status,
        reason_code: reasonCode,
        blocking_issues: blocking,
        listeners: {
          projection_change:
            this.listenersReady &&
            !this.listenerIssues.some((issue) => issue.startsWith("projection_change")),
          session_event:
            this.listenersReady &&
            !this.listenerIssues.some((issue) => issue.startsWith("session_event")),
          session_disposed:
            this.subscribeSessionDisposed !== null &&
            this.listenersReady &&
            !this.listenerIssues.some((issue) => issue.startsWith("session_disposed")),
        },
        limitations: [...STATIC_LIMITATIONS],
      },
    };
    return deepFreeze(snapshot);
  }

  _resolveMetricForHandle(handle, field, view, observedAtMs) {
    const kind = field === "contextWindow" ? "capacity" : "tokens";
    const parsed = readField(view, field, kind);
    if (!parsed.present) {
      return {
        state: "missing",
        value: null,
        reason_code: "field_missing",
        source: null,
      };
    }
    if (!parsed.valid) {
      return {
        state: "invalid",
        value: null,
        reason_code: parsed.reason_code,
        detail: parsed.raw,
        source: null,
      };
    }
    const tracked = handle.fieldSources[field];
    if (
      tracked !== undefined &&
      tracked.present &&
      tracked.value === parsed.value &&
      tracked.known
    ) {
      if (tracked.time === null || tracked.time > observedAtMs) {
        return {
          state: "unverified",
          value: parsed.value,
          reason_code: tracked.time === null ? "source_time_unknown" : "source_after_observation",
          source: sourceObject(tracked.seq, tracked.time),
        };
      }
      return {
        state: "known",
        value: parsed.value,
        reason_code: "ok",
        source: sourceObject(tracked.seq, tracked.time),
      };
    }
    let reason = "source_time_unknown";
    if (
      tracked !== undefined &&
      tracked.present &&
      tracked.value !== parsed.value
    ) {
      reason = "value_changed_without_source";
    }
    return {
      state: "unverified",
      value: parsed.value,
      reason_code: reason,
      source:
        tracked === undefined
          ? null
          : sourceObject(tracked.seq, tracked.time),
    };
  }

  _resolveConfigForHandle(handle, session, observedAtMs) {
    let current = null;
    try {
      if (typeof session.requestContext === "function") {
        const value = session.requestContext();
        if (isPlainObject(value)) {
          current = { provider: value.provider, model: value.model };
        }
      }
    } catch {
      current = null;
    }
    if (
      current === null ||
      !isIdentifier(current.provider) ||
      !isIdentifier(current.model)
    ) {
      return {
        provider_id: {
          state: "missing",
          value: null,
          reason_code: "request_context_missing",
          source: null,
        },
        model_id: {
          state: "missing",
          value: null,
          reason_code: "request_context_missing",
          source: null,
        },
      };
    }
    const tracked = handle.configSource;
    let state = "unverified";
    let reason = "source_time_unknown";
    let source = null;
    if (
      tracked !== null &&
      tracked.provider === current.provider &&
      tracked.model === current.model &&
      tracked.known
    ) {
      if (tracked.time === null || tracked.time > observedAtMs) {
        reason = tracked.time === null ? "source_time_unknown" : "source_after_observation";
      } else {
        state = "known";
        reason = "ok";
      }
      source = {
        kind: "request/context",
        seq: tracked.seq,
        time: isoFromMs(tracked.time),
      };
    } else if (
      tracked !== null &&
      (tracked.provider !== current.provider || tracked.model !== current.model)
    ) {
      reason = "value_changed_without_source";
    }
    return {
      provider_id: {
        state,
        value: current.provider,
        reason_code: reason,
        source,
      },
      model_id: {
        state,
        value: current.model,
        reason_code: reason,
        source,
      },
    };
  }

  _unknownSnapshotFromHandle(handle, observedAt, reasonCode) {
    const request = handle && isPlainObject(handle.request) ? handle.request : null;
    const snapshot = baseSnapshot(request, observedAt, reasonCode);
    if (request !== null) {
      snapshot.session.native_session_id = request.nativeSessionId;
      snapshot.session.generation = request.sessionGeneration;
    }
    return deepFreeze(snapshot);
  }

  untrack(handle) {
    if (!isPlainObject(handle)) return;
    const tracked = handle.session === undefined ? null : this.tracked.get(handle.session);
    if (tracked !== handle) return;
    this.tracked.delete(handle.session);
    this.trackedById.delete(handle.native_session_id);
    handle.disposed = true;
    handle.detached = true;
    if (this.tracked.size === 0) this._stopListeners();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    for (const handle of this.tracked.values()) {
      handle.disposed = true;
    }
    this.tracked.clear();
    this.trackedById.clear();
    this._stopListeners();
  }
}

/**
 * Create a capture controller. `sessions` and `sessionProjections` are the
 * native Cordis services. The optional subscribe functions receive a listener
 * and must return the exact disposer (for a future plugin mount:
 * `(listener) => ctx.on("session/event", listener)`).
 */
export function createContextCapture(dependencies) {
  return new ContextCapture(dependencies);
}

/**
 * Future-mount convenience. Must be called inside a Cordis plugin `apply`
 * (or another context where `sessionProjections.onChanged` can register its
 * effect). This slice does not load it in any running profile.
 */
export function mountContextCapture(ctx, options = {}) {
  if (ctx === null || typeof ctx !== "object") fail("ctx_invalid", "ctx");
  const sessions = typeof ctx.get === "function" ? ctx.get("sessions") : ctx.sessions;
  const sessionProjections =
    typeof ctx.get === "function" ? ctx.get("sessionProjections") : ctx.sessionProjections;
  return createContextCapture({
    sessions,
    sessionProjections,
    subscribeSessionEvent:
      typeof ctx.on === "function" ? (listener) => ctx.on("session/event", listener) : null,
    subscribeSessionDisposed:
      typeof ctx.on === "function" ? (listener) => ctx.on("session/disposed", listener) : null,
    clock: options.clock,
  });
}

export {
  CaptureError,
  EXPECTED_STATE_VERSION,
  MAX_SAFE_INTEGER,
  METRIC_FIELDS,
  NATIVE_FROZEN_VERSION,
  NATIVE_PACKAGE,
  PRODUCER_MODULE,
  PRODUCER_VERSION,
  PROJECTION_KEY,
  SNAPSHOT_SCHEMA,
  SNAPSHOT_SCHEMA_VERSION,
};
