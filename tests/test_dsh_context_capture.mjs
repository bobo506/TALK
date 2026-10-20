import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const {
  CaptureError,
  EXPECTED_STATE_VERSION,
  MAX_SAFE_INTEGER,
  PROJECTION_KEY,
  SNAPSHOT_SCHEMA,
  SNAPSHOT_SCHEMA_VERSION,
  createContextCapture,
  mountContextCapture,
} = await import(
  pathToFileURL(
    path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../bridges/dsh_context_capture.mjs",
    ),
  ).href
);

const T0 = Date.parse("2026-10-20T15:00:00.000Z");
const T1 = T0 + 1000;
const T2 = T0 + 2000;
const T3 = T0 + 3000;
const T4 = T0 + 4000;
const T5 = T0 + 5000;
const NOW = T4 + 1000;

function iso(ms) {
  return new Date(ms).toISOString();
}

function makeRequest(overrides = {}) {
  return {
    nativeSessionId: "session-test",
    sessionGeneration: 3,
    projectId: "prj_e8fe7066bbec",
    targetMemberId: "agent:deepseek",
    requesterId: "agent:codex",
    continuityKey: "line:test",
    workspaceIdentity: "workspace:talk",
    workspacePath: "D:/claude-test/TALK",
    nativeHomeNamespace: "native-home:test",
    runnerId: "runner:test",
    serviceLaunchId: "launch:test",
    providerId: "deepseek-official",
    modelId: "deepseek-flash",
    modelBindingFingerprint: "a".repeat(64),
    configPermissionFingerprint: "b".repeat(64),
    hostAttestation: { verified: true, source: "test-host" },
    ...overrides,
  };
}

function createWorld({
  id = "session-test",
  cwd = "D:/claude-test/TALK",
  config = { provider: "deepseek-official", model: "deepseek-flash" },
  initialView,
  request = {},
} = {}) {
  const sessionListeners = new Set();
  const disposedListeners = new Set();
  const session = {
    id,
    header: { cwd },
    seq: 0,
    firstLiveSeq: 0,
    events: [],
    context: config === null ? undefined : { ...config },
    eventAt(seq) {
      return this.events[seq];
    },
    requestContext() {
      return this.context;
    },
    append(type, data, time) {
      const event = { type, seq: this.seq, time, data };
      this.seq += 1;
      this.events[event.seq] = event;
      for (const listener of [...sessionListeners]) listener(this, event);
      return event;
    },
  };
  const sessionMap = new Map([[id, session]]);
  const sessions = {
    get(sessionId) {
      return sessionMap.get(sessionId);
    },
    set(sessionId, value) {
      sessionMap.set(sessionId, value);
    },
    delete(sessionId) {
      sessionMap.delete(sessionId);
    },
  };
  const projection = {
    views: new Map(),
    snapshotCalls: 0,
    cachedCalls: 0,
    onChangedCalls: 0,
    failSnapshot: false,
    onChangedListeners: new Set(),
    setView(target, view) {
      this.views.set(target, view);
    },
    getView(target) {
      return this.views.get(target);
    },
    snapshot(target) {
      this.snapshotCalls += 1;
      if (this.failSnapshot) throw new Error("PROMPT_SECRET");
      const view = this.views.get(target);
      const values = {};
      if (view !== undefined) values[PROJECTION_KEY] = view;
      return { asOfSeq: target.seq - 1, values };
    },
    cachedSnapshot() {
      this.cachedCalls += 1;
      return {
        asOfSeq: 9999,
        values: {
          [PROJECTION_KEY]: {
            projectedTokens: 9999,
            pressureTokens: 9999,
            contextWindow: 100000,
          },
        },
      };
    },
    onChanged(callback) {
      this.onChangedCalls += 1;
      this.onChangedListeners.add(callback);
      return () => {
        this.onChangedListeners.delete(callback);
      };
    },
    emit(target, value, seq) {
      for (const callback of [...this.onChangedListeners]) {
        callback(target, PROJECTION_KEY, value, seq);
      }
    },
  };
  const capture = createContextCapture({
    sessions,
    sessionProjections: projection,
    subscribeSessionEvent: (listener) => {
      sessionListeners.add(listener);
      return () => sessionListeners.delete(listener);
    },
    subscribeSessionDisposed: (listener) => {
      disposedListeners.add(listener);
      return () => disposedListeners.delete(listener);
    },
    clock: () => NOW,
  });
  const resolvedRequest = { nativeSessionId: id, ...request };
  if (initialView !== undefined) projection.setView(session, initialView);
  const handle = capture.track(makeRequest(resolvedRequest));
  return {
    id,
    session,
    sessions,
    projection,
    capture,
    handle,
    sessionListeners,
    disposedListeners,
    request: makeRequest(resolvedRequest),
    read(now = NOW, extra = {}) {
      return capture.read(handle, { now, ...extra });
    },
    emitConfig(provider, model, time = T1) {
      session.context = { provider, model };
      return session.append("request/context", { provider, model }, time);
    },
    emitView(view, time, type = "assistant/message") {
      const event = session.append(type, {}, time);
      projection.setView(session, view);
      projection.emit(session, view, event.seq);
      return event;
    },
    disposeSession() {
      for (const listener of [...disposedListeners]) listener(session);
    },
  };
}

function installKnownWorld({
  projected = 59900,
  capacity = 100000,
  pressure = projected,
  includeProjected = true,
  includePressure = true,
  provider = "deepseek-official",
  model = "deepseek-flash",
  configTime = T1,
} = {}) {
  const world = createWorld({ config: null });
  world.emitConfig(provider, model, configTime);
  const capacityView = { contextWindow: capacity };
  world.emitView(capacityView, T2);
  let view = capacityView;
  if (includePressure) {
    view = { ...view, pressureTokens: pressure };
    world.emitView(view, T3);
  }
  if (includeProjected) {
    view = { ...view, projectedTokens: projected };
    world.emitView(view, T4);
  }
  return world;
}

test("schema, cut and exact native snapshot; cachedSnapshot is never used", () => {
  const world = installKnownWorld();
  const snapshot = world.read();
  assert.equal(snapshot.schema, SNAPSHOT_SCHEMA);
  assert.equal(snapshot.schema_version, SNAPSHOT_SCHEMA_VERSION);
  assert.equal(snapshot.producer.native_contract.expected_state_version, EXPECTED_STATE_VERSION);
  assert.equal(snapshot.producer.native_contract.projection_key, "contextPressure");
  assert.equal(snapshot.session.projection.authority, "registry_snapshot");
  assert.equal(snapshot.session.projection.cached_snapshot_used, false);
  assert.equal(snapshot.session.projection.checkpoint_used, false);
  assert.equal(snapshot.session.projection.materializes_all_registered_units, true);
  assert.equal(snapshot.session.projection.cut, world.session.seq - 1);
  assert.equal(snapshot.session.revision, world.session.seq - 1);
  assert.equal(world.projection.cachedCalls, 0);
  assert.equal(world.projection.snapshotCalls, 2); // track baseline + read
});

test("native Session class instances are accepted, not only plain objects", () => {
  class NativeSession {
    constructor() {
      this.id = "session-test";
      this.header = { cwd: "D:/claude-test/TALK" };
      this.seq = 0;
      this.firstLiveSeq = 0;
      this.events = [];
      this.context = { provider: "deepseek-official", model: "deepseek-flash" };
    }
    eventAt(seq) {
      return this.events[seq];
    }
    requestContext() {
      return this.context;
    }
  }
  const session = new NativeSession();
  const projection = {
    calls: 0,
    snapshot() {
      this.calls += 1;
      return { asOfSeq: -1, values: {} };
    },
    onChanged() {
      return () => {};
    },
  };
  const capture = createContextCapture({
    sessions: { get: () => session },
    sessionProjections: projection,
  });
  const handle = capture.track(makeRequest());
  assert.equal(handle.bound, true);
  const snapshot = capture.read(handle, { now: NOW });
  assert.equal(snapshot.capture.reason_code, "projection_empty");
  capture.dispose();
});

test("known zero, 59.9 percent and 60 percent values are preserved as exact integers", () => {
  for (const [projected, capacity] of [
    [0, 100],
    [59900, 100000],
    [60000, 100000],
    [MAX_SAFE_INTEGER, MAX_SAFE_INTEGER],
  ]) {
    const world = installKnownWorld({ projected, capacity, pressure: projected });
    const snapshot = world.read();
    assert.equal(snapshot.metrics.projected_tokens.state, "known");
    assert.equal(snapshot.metrics.projected_tokens.value, projected);
    assert.equal(snapshot.metrics.context_window.state, "known");
    assert.equal(snapshot.metrics.context_window.value, capacity);
    assert.equal(snapshot.capture.status, "available");
    assert.equal(JSON.parse(JSON.stringify(snapshot)).metrics.projected_tokens.value, projected);
  }
});

test("missing services, session, projection key and projection view are unknown", () => {
  const noServices = createContextCapture({});
  const noServicesHandle = noServices.track(makeRequest());
  const noServicesSnapshot = noServices.read(noServicesHandle, { now: NOW });
  assert.equal(noServicesSnapshot.capture.status, "unknown");
  assert.equal(noServicesSnapshot.capture.reason_code, "sessions_service_missing");

  const noProjection = createWorld();
  noProjection.capture.dispose();
  const noProjectionCapture = createContextCapture({
    sessions: noProjection.sessions,
    subscribeSessionEvent: (listener) => {
      noProjection.sessionListeners.add(listener);
      return () => noProjection.sessionListeners.delete(listener);
    },
  });
  const noProjectionHandle = noProjectionCapture.track(makeRequest());
  const noProjectionSnapshot = noProjectionCapture.read(noProjectionHandle, { now: NOW });
  assert.equal(noProjectionSnapshot.capture.reason_code, "projection_service_missing");

  const missingSession = createWorld();
  missingSession.sessions.delete("session-test");
  const missingSessionSnapshot = missingSession.read();
  assert.equal(missingSessionSnapshot.capture.reason_code, "session_not_live");

  const missingView = createWorld();
  missingView.session.append("turn/start", {}, T1);
  const missingViewModel = missingView.read();
  assert.equal(missingViewModel.capture.reason_code, "projection_missing");

  const failing = createWorld();
  failing.projection.failSnapshot = true;
  const failedSnapshot = failing.read();
  assert.equal(failedSnapshot.capture.reason_code, "projection_snapshot_failed");
  const serialized = JSON.stringify(failedSnapshot);
  assert.equal(serialized.includes("PROMPT_SECRET"), false);
});

test("host attestation and workspace must be explicit", () => {
  const noAttestation = createWorld({
    request: { hostAttestation: null },
  });
  const snapshot = noAttestation.read();
  assert.equal(snapshot.capture.status, "unknown");
  assert.equal(snapshot.capture.reason_code, "host_not_verified");

  const badWorkspace = createWorld({
    request: { workspacePath: "D:/other/workspace" },
  });
  const badWorkspaceSnapshot = badWorkspace.read();
  assert.equal(badWorkspaceSnapshot.capture.reason_code, "workspace_mismatch");
  assert.equal(badWorkspaceSnapshot.host.workspace_verified, false);
});

test("invalid projected values stay invalid and never become missing or low pressure", () => {
  const cases = [
    [-1, "value_negative"],
    [1.5, "value_non_integer"],
    [Number.NaN, "value_non_finite"],
    [Number.POSITIVE_INFINITY, "value_non_finite"],
    [true, "value_boolean"],
    [MAX_SAFE_INTEGER + 1, "value_too_large"],
    [9007199254740993n, "value_bigint"],
    ["59900", "value_string"],
  ];
  for (const [value, reason] of cases) {
    const world = installKnownWorld();
    world.emitView(
      { contextWindow: 100000, pressureTokens: 59900, projectedTokens: value },
      T5,
    );
    const snapshot = world.read();
    assert.equal(snapshot.metrics.projected_tokens.state, "invalid", String(value));
    assert.equal(snapshot.metrics.projected_tokens.reason_code, reason, String(value));
    assert.equal(snapshot.metrics.projected_tokens.value, null);
    assert.equal(snapshot.metrics.pressure_tokens.state, "known");
    assert.equal(snapshot.metrics.pressure_tokens.value, 59900);
    assert.equal(snapshot.capture.status, "partial");
    const serialized = JSON.stringify(snapshot);
    assert.doesNotThrow(() => JSON.parse(serialized));
    assert.equal(serialized.includes("PROMPT_SECRET"), false);
  }
});

test("invalid capacity and invalid pressure are explicit", () => {
  const zeroCapacity = installKnownWorld({ capacity: 0 });
  const zeroSnapshot = zeroCapacity.read();
  assert.equal(zeroSnapshot.metrics.context_window.state, "invalid");
  assert.equal(zeroSnapshot.metrics.context_window.reason_code, "value_not_positive");

  const badPressure = installKnownWorld({ includeProjected: false });
  badPressure.emitView({ contextWindow: 100000, pressureTokens: -5 }, T5);
  const badPressureSnapshot = badPressure.read();
  assert.equal(badPressureSnapshot.metrics.pressure_tokens.state, "invalid");
  assert.equal(badPressureSnapshot.metrics.pressure_tokens.reason_code, "value_negative");
  assert.equal(badPressureSnapshot.metrics.projected_tokens.state, "missing");
});

test("fields are sourced independently and unchanged values keep their old source time", () => {
  const world = createWorld();
  world.emitConfig("deepseek-official", "deepseek-flash", T1);
  world.emitView({ contextWindow: 100000 }, T2);
  world.emitView({ contextWindow: 100000, pressureTokens: 59900 }, T3);
  const before = world.read(T4);
  assert.equal(before.metrics.context_window.source.time, iso(T2));
  assert.equal(before.metrics.pressure_tokens.source.time, iso(T3));
  assert.equal(before.metrics.projected_tokens.state, "missing");

  world.emitView({ contextWindow: 200000, pressureTokens: 59900 }, T4);
  const after = world.read(T5);
  assert.equal(after.metrics.context_window.source.time, iso(T4));
  assert.equal(after.metrics.pressure_tokens.source.time, iso(T3));
  assert.equal(after.metrics.pressure_tokens.state, "known");

  world.emitView(
    { contextWindow: 200000, pressureTokens: 60000, projectedTokens: 60000 },
    T5,
  );
  const final = world.read(T5 + 1000);
  assert.equal(final.metrics.context_window.source.time, iso(T4));
  assert.equal(final.metrics.pressure_tokens.source.time, iso(T5));
  assert.equal(final.metrics.projected_tokens.source.time, iso(T5));
});

test("values present before mount have unknown source time and are not backdated", () => {
  const world = createWorld({ initialView: { contextWindow: 100000, pressureTokens: 0, projectedTokens: 0 } });
  world.session.append("turn/start", {}, T1);
  const before = world.read(T4);
  assert.equal(before.metrics.projected_tokens.state, "unverified");
  assert.equal(before.metrics.projected_tokens.reason_code, "source_time_unknown");
  assert.equal(before.metrics.pressure_tokens.detail, undefined);
  assert.equal(before.capture.status, "partial");

  world.emitView({ contextWindow: 100000, pressureTokens: 0, projectedTokens: 0 }, T5);
  const after = world.read(T5 + 1000);
  // The value did not change, so the native change feed did not fire; the
  // mount-time value remains unverified rather than being relabeled as fresh.
  assert.equal(after.metrics.projected_tokens.state, "unverified");
  assert.equal(after.metrics.projected_tokens.source.seq, null);
  assert.equal(after.metrics.projected_tokens.source.time, null);
});

test("source time is the committed event time, never the read clock", () => {
  const world = installKnownWorld();
  const snapshot = world.read(NOW + 60000);
  assert.equal(snapshot.metrics.projected_tokens.source.time, iso(T4));
  assert.equal(snapshot.metrics.context_window.source.time, iso(T2));
  assert.equal(snapshot.observed_at, iso(NOW + 60000));
});

test("generation, session replacement, disposal and previous cut are protected", () => {
  const world = installKnownWorld();
  const generation = world.capture.read(world.handle, {
    now: NOW,
    sessionGeneration: 99,
  });
  assert.equal(generation.capture.reason_code, "generation_mismatch");

  const previous = world.read(NOW, { previousCut: 999 });
  assert.equal(previous.capture.reason_code, "revision_regressed");

  world.disposeSession();
  const disposed = world.read();
  assert.equal(disposed.capture.reason_code, "session_disposed");

  const replacement = createWorld();
  replacement.sessions.set("session-test", {
    ...replacement.session,
    id: "session-test",
    header: { cwd: "D:/claude-test/TALK" },
  });
  const replaced = replacement.read();
  assert.equal(replaced.capture.reason_code, "session_replaced");
});

test("out-of-order and duplicate-conflict revisions become unknown; compaction remains exact", () => {
  const world = installKnownWorld();
  const seq = world.session.seq;
  world.session.append("assistant/message", {}, T5);
  world.projection.setView(world.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 59900,
  });
  world.projection.emit(world.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 59900,
  }, seq - 2);
  const outOfOrder = world.read();
  assert.equal(outOfOrder.capture.reason_code, "revision_anomaly");

  const duplicateWorld = installKnownWorld();
  const duplicateSeq = duplicateWorld.session.seq - 1;
  duplicateWorld.projection.emit(duplicateWorld.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 60000,
  }, duplicateSeq);
  const duplicate = duplicateWorld.read();
  assert.equal(duplicate.capture.reason_code, "revision_anomaly");

  const compacted = installKnownWorld();
  const compactEvent = compacted.session.append("system/message", {}, T5);
  compacted.projection.setView(compacted.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 12000,
  });
  compacted.projection.emit(compacted.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 12000,
  }, compactEvent.seq);
  const compactedSnapshot = compacted.read();
  assert.equal(compactedSnapshot.metrics.projected_tokens.state, "known");
  assert.equal(compactedSnapshot.metrics.projected_tokens.value, 12000);
  assert.equal(compactedSnapshot.metrics.projected_tokens.source.time, iso(T5));
});

test("unknown projection fields are rejected instead of guessed", () => {
  const baseline = createWorld({
    initialView: {
      contextWindow: 100000,
      pressureTokens: 59900,
      projectedTokens: 59900,
      futureField: 1,
    },
  });
  baseline.session.append("turn/start", {}, T1);
  assert.equal(baseline.read().capture.reason_code, "projection_unknown_fields");

  const world = installKnownWorld();
  world.emitView(
    {
      contextWindow: 100000,
      pressureTokens: 59900,
      projectedTokens: 59900,
      futureField: 1,
    },
    T5,
  );
  const snapshot = world.read();
  assert.equal(snapshot.capture.reason_code, "projection_unknown_fields");
});

test("native provider/model are read from requestContext and binding stays caller-attested", () => {
  const world = installKnownWorld({ provider: "provider-a", model: "model-a" });
  const snapshot = world.read();
  assert.equal(snapshot.config.provider_id.state, "known");
  assert.equal(snapshot.config.provider_id.value, "provider-a");
  assert.equal(snapshot.config.model_id.value, "model-a");
  assert.equal(snapshot.config.provider_id.source.kind, "request/context");
  assert.equal(snapshot.config.provider_id.source.time, iso(T1));
  assert.equal(snapshot.config.model_binding_fingerprint.state, "caller_attested");
  assert.equal(snapshot.config.config_permission_fingerprint.state, "caller_attested");
  assert.equal(snapshot.host.verification.native_home, "caller_attested");
  assert.equal(snapshot.host.verification.service_launch, "caller_attested");
  assert.equal(snapshot.host.verification.workspace, "native_header_cwd_exact_match");
});

test("request/context for unrelated capacity/system changes does not refresh config source time", () => {
  const world = installKnownWorld();
  world.session.append(
    "request/context",
    { provider: "deepseek-official", model: "deepseek-flash" },
    T5,
  );
  const snapshot = world.read(T5 + 1000);
  assert.equal(snapshot.config.provider_id.state, "known");
  assert.equal(snapshot.config.provider_id.source.time, iso(T1));
  assert.equal(snapshot.config.model_id.source.time, iso(T1));
});

test("config without an observed request/context source is unverified, not fresh", () => {
  const world = createWorld();
  world.emitView({ contextWindow: 100000 }, T1);
  world.emitView({ contextWindow: 100000, pressureTokens: 59900 }, T2);
  const snapshot = world.read(T3);
  assert.equal(snapshot.config.provider_id.state, "unverified");
  assert.equal(snapshot.config.provider_id.reason_code, "source_time_unknown");
  assert.equal(snapshot.capture.status, "partial");
});

test("pre-mount config repeated after mount stays unverified, not backdated", () => {
  const world = createWorld(); // default context already exists at mount
  world.emitConfig("deepseek-official", "deepseek-flash", T1); // same-value repeat
  world.emitView({ contextWindow: 100000, pressureTokens: 59900 }, T2);
  const snapshot = world.read(T3);
  assert.equal(snapshot.config.provider_id.state, "unverified");
  assert.equal(snapshot.config.provider_id.reason_code, "source_time_unknown");
  assert.equal(snapshot.config.provider_id.source, null);
});

test("request/context source time and ordering are exposed, not synthesized", () => {
  const world = createWorld({ config: null });
  world.emitView({ contextWindow: 100000 }, T1);
  world.emitView({ contextWindow: 100000, pressureTokens: 59900 }, T2);
  world.emitConfig("deepseek-official", "deepseek-flash", T3);
  const snapshot = world.read(T4);
  assert.equal(snapshot.config.provider_id.state, "known");
  assert.equal(snapshot.config.provider_id.source.time, iso(T3));
  assert.equal(snapshot.metrics.pressure_tokens.source.time, iso(T2));
  // T3 config is newer than the T2 pressure sample; the adapter must reject
  // this ordering even though the capture can report both source times.
  assert.ok(Date.parse(snapshot.config.provider_id.source.time) > Date.parse(snapshot.metrics.pressure_tokens.source.time));
});

test("unreadable projection view is contained without leaking error text", () => {
  const world = installKnownWorld();
  const evil = {};
  Object.defineProperty(evil, "projectedTokens", {
    enumerable: true,
    get() {
      throw new Error("PROMPT_SECRET_SHOULD_NOT_LEAK");
    },
  });
  world.projection.setView(world.session, evil);
  const event = world.session.append("assistant/message", {}, T5);
  world.projection.emit(world.session, evil, event.seq);
  const snapshot = world.read();
  assert.equal(snapshot.capture.status, "unknown");
  assert.ok(
    ["projection_listener_error", "projection_view_unreadable"].includes(
      snapshot.capture.reason_code,
    ),
  );
  assert.equal(JSON.stringify(snapshot).includes("PROMPT_SECRET_SHOULD_NOT_LEAK"), false);
});

test("listener exceptions are contained and never leak raw error text", () => {
  const world = installKnownWorld();
  const evil = {};
  Object.defineProperty(evil, "projectedTokens", {
    enumerable: true,
    get() {
      throw new Error("PROMPT_SECRET_SHOULD_NOT_LEAK");
    },
  });
  const event = world.session.append("assistant/message", {}, T5);
  world.projection.emit(world.session, evil, event.seq);
  world.projection.setView(world.session, {
    contextWindow: 100000,
    pressureTokens: 59900,
    projectedTokens: 59900,
  });
  const snapshot = world.read();
  assert.equal(snapshot.capture.reason_code, "projection_listener_error");
  const serialized = JSON.stringify(snapshot);
  assert.equal(serialized.includes("PROMPT_SECRET_SHOULD_NOT_LEAK"), false);
});

test("duplicate tracking is rejected until the old handle is detached", () => {
  const world = installKnownWorld();
  assert.throws(
    () => world.capture.track(makeRequest()),
    (error) => error instanceof CaptureError && error.code === "session_already_tracked",
  );
  world.handle.dispose();
  const rebound = world.capture.track(makeRequest());
  assert.equal(rebound.bound, true);
  rebound.dispose();
  world.capture.dispose();
});

test("snapshots are deeply immutable and request input is not mutated", () => {
  const world = installKnownWorld();
  const request = world.request;
  const before = JSON.stringify(request);
  const snapshot = world.read();
  assert.equal(Object.isFrozen(snapshot), true);
  assert.equal(Object.isFrozen(snapshot.metrics), true);
  assert.equal(Object.isFrozen(snapshot.metrics.projected_tokens), true);
  assert.equal(Object.isFrozen(snapshot.host), true);
  assert.throws(() => {
    snapshot.metrics.projected_tokens.value = 1;
  }, TypeError);
  assert.equal(JSON.stringify(request), before);
  assert.equal(JSON.stringify(world.projection.getView(world.session)).includes("59900"), true);
});

test("dispose and untrack are idempotent and remove native listeners", () => {
  const world = installKnownWorld();
  assert.equal(world.projection.onChangedListeners.size, 1);
  assert.equal(world.sessionListeners.size, 1);
  world.handle.dispose();
  assert.equal(world.projection.onChangedListeners.size, 0);
  assert.equal(world.sessionListeners.size, 0);
  const detached = world.read();
  assert.equal(detached.capture.reason_code, "handle_detached");
  world.handle.dispose();
  assert.equal(world.projection.onChangedListeners.size, 0);

  const second = installKnownWorld();
  second.capture.dispose();
  second.capture.dispose();
  assert.equal(second.projection.onChangedListeners.size, 0);
  assert.equal(second.sessionListeners.size, 0);
  const disposed = second.read();
  assert.equal(disposed.capture.reason_code, "capture_disposed");
});

test("sessions are isolated; changes in one tracked session do not source another", () => {
  const first = createWorld({ id: "session-a" });
  const secondSession = {
    id: "session-b",
    header: { cwd: "D:/claude-test/TALK" },
    seq: 0,
    firstLiveSeq: 0,
    events: [],
    context: { provider: "deepseek-official", model: "deepseek-flash" },
    eventAt(seq) {
      return this.events[seq];
    },
    requestContext() {
      return this.context;
    },
    append(type, data, time) {
      const event = { type, seq: this.seq, time, data };
      this.seq += 1;
      this.events[event.seq] = event;
      for (const listener of [...first.sessionListeners]) listener(this, event);
      return event;
    },
  };
  first.sessions.set("session-b", secondSession);
  first.projection.setView(secondSession, { contextWindow: 100000 });
  const secondHandle = first.capture.track(
    makeRequest({ nativeSessionId: "session-b", sessionGeneration: 4 }),
  );
  secondSession.append("turn/start", {}, T0);

  // The session event subscription is shared by both tracked sessions, but
  // only the projection registry knows about secondSession. Emit a source
  // change for session-a and confirm session-b's snapshot has no source time.
  first.emitView({ contextWindow: 100000, pressureTokens: 1 }, T1);
  const a = first.read();
  const b = first.capture.read(secondHandle, { now: NOW });
  assert.equal(a.metrics.pressure_tokens.state, "known");
  assert.equal(b.metrics.context_window.state, "unverified");
  assert.equal(b.metrics.context_window.source.time, null);
  assert.notEqual(a.session.native_session_id, b.session.native_session_id);
});

test("product capture module has no filesystem, network or process side effects", () => {
  const modulePath = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../bridges/dsh_context_capture.mjs",
  );
  const source = fs.readFileSync(modulePath, "utf8");
  for (const token of [
    "node:fs",
    "node:net",
    "node:http",
    "node:child_process",
    "writeFile",
    "spawn(",
    "exec(",
    "fetch(",
  ]) {
    assert.equal(source.includes(token), false, token);
  }
});

test("error messages contain only fields/codes, not input or prompt values", () => {
  const capture = createContextCapture({});
  assert.throws(
    () => capture.track(makeRequest({ nativeSessionId: "" })),
    (error) => error instanceof CaptureError && error.message === "nativeSessionId: identifier_invalid",
  );
  assert.throws(
    () => capture.track(makeRequest({ sessionGeneration: 0 })),
    (error) => error instanceof CaptureError && error.message === "sessionGeneration: generation_invalid",
  );
});

function crossLanguageCases() {
  const cases = [];
  const reuse = installKnownWorld({ projected: 59900, pressure: 59900 });
  cases.push({
    name: "reuse_59_9",
    snapshot: reuse.read(NOW),
    now: iso(NOW + 1000),
    expected: { action: "reuse_session", used: 59900, capacity: 100000 },
  });
  const exact = installKnownWorld({ projected: 60000, pressure: 60000 });
  cases.push({
    name: "new_60",
    snapshot: exact.read(NOW),
    now: iso(NOW + 1000),
    expected: { action: "new_session", used: 60000, capacity: 100000 },
  });
  const zero = installKnownWorld({ projected: 0, pressure: 0, capacity: 1000 });
  cases.push({
    name: "zero",
    snapshot: zero.read(NOW),
    now: iso(NOW + 1000),
    expected: { action: "reuse_session", used: 0, capacity: 1000 },
  });
  const fallback = installKnownWorld({
    includeProjected: false,
    pressure: 59900,
  });
  cases.push({
    name: "pressure_fallback",
    snapshot: fallback.read(NOW),
    now: iso(NOW + 1000),
    expected: { action: "reuse_session", used: 59900, capacity: 100000 },
  });
  const invalid = installKnownWorld();
  invalid.emitView(
    { contextWindow: 100000, pressureTokens: 59900, projectedTokens: -1 },
    T5,
  );
  cases.push({
    name: "invalid_projected",
    snapshot: invalid.read(NOW),
    now: iso(NOW + 1000),
    expected: { action: "new_session", used: null, capacity: 100000 },
  });
  const expired = installKnownWorld();
  cases.push({
    name: "expired",
    snapshot: expired.read(T4 + 3600 * 1000),
    now: iso(T4 + 3600 * 1000 + 1000),
    expected: { action: "new_session", used: 59900, capacity: 100000 },
  });
  return {
    schema: "talk-dsh-cross-language-cases-1",
    generated_by: "candidate/tests/test_dsh_context_capture.mjs",
    generated_at_utc: iso(NOW),
    now: iso(NOW + 1000),
    cases,
  };
}

if (process.argv[2] === "--emit-cross-language") {
  const out = process.argv[3];
  if (!out) {
    process.stderr.write("missing output path\n");
    process.exit(2);
  }
  fs.writeFileSync(out, `${JSON.stringify(crossLanguageCases(), null, 2)}\n`, "utf8");
  process.exit(0);
}

test("cross-language emitter still produces the expected schema and cases", () => {
  const payload = crossLanguageCases();
  assert.equal(payload.schema, "talk-dsh-cross-language-cases-1");
  assert.equal(payload.cases.length, 6);
  for (const item of payload.cases) {
    assert.equal(item.snapshot.schema, SNAPSHOT_SCHEMA);
    assert.equal(JSON.parse(JSON.stringify(item.snapshot)).schema, SNAPSHOT_SCHEMA);
  }
});

test("native identity getters fail as unknown without exposing exception text", () => {
  const world = installKnownWorld();
  Object.defineProperty(world.session, "header", {
    get() { throw new Error("PRIVATE_NATIVE_SENTINEL"); },
  });
  const snapshot = world.read();
  assert.equal(snapshot.capture.status, "unknown");
  assert.ok(!JSON.stringify(snapshot).includes("PRIVATE_NATIVE_SENTINEL"));
  assert.doesNotThrow(() => world.capture.track(world.request));
});

test("projection callbacks from before the bound cut cannot source new values", () => {
  const world = createWorld({ config: null });
  world.emitConfig("deepseek-official", "deepseek-flash", T1);
  for (let index = 0; index < 4; index += 1) {
    world.emitView({ contextWindow: 100000, pressureTokens: index + 1, projectedTokens: index + 1 }, T2 + index);
  }
  world.capture.untrack(world.handle);
  world.handle = world.capture.track(world.request);
  const value = { contextWindow: 100000, pressureTokens: 5, projectedTokens: 5 };
  world.projection.setView(world.session, value);
  world.projection.emit(world.session, value, 1);
  const snapshot = world.capture.read(world.handle, { now: NOW });
  assert.equal(snapshot.capture.status, "unknown");
});

test("native projection changes cannot be attributed to future uncommitted events", () => {
  const world = installKnownWorld();
  world.projection.emit(world.session, { contextWindow: 100000, pressureTokens: 2, projectedTokens: 2 }, world.session.seq);
  assert.equal(world.read().capture.status, "unknown");
});

test("session event gaps and conflicting duplicates block capture", () => {
  for (const duplicate of [false, true]) {
    const world = installKnownWorld();
    const event = world.session.events.at(-1);
    const invalid = duplicate
      ? { ...event, type: "request/context", data: { provider: "other", model: "other" } }
      : { ...event, seq: event.seq + 2 };
    for (const callback of world.sessionListeners) callback(world.session, invalid);
    assert.equal(world.read().capture.status, "unknown");
  }
});

test("mount adapter registers exact native event signatures and releases them", () => {
  const world = createWorld({ config: null });
  world.capture.dispose();
  const ctx = {
    get(name) {
      return { sessions: world.sessions, sessionProjections: world.projection }[name];
    },
    on(name, callback) {
      const listeners = {
        "session/event": world.sessionListeners,
        "session/disposed": world.disposedListeners,
      }[name];
      assert.ok(listeners);
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
  };
  const capture = mountContextCapture(ctx, { clock: () => NOW });
  const handle = capture.track(world.request);
  world.emitConfig("deepseek-official", "deepseek-flash", T1);
  world.emitView({ contextWindow: 100000 }, T2);
  world.emitView({ contextWindow: 100000, pressureTokens: 59900, projectedTokens: 59900 }, T3);
  assert.equal(capture.read(handle).capture.status, "available");
  world.disposeSession();
  assert.equal(capture.read(handle).capture.reason_code, "session_disposed");
  capture.dispose();
  assert.equal(world.sessionListeners.size, 0);
  assert.equal(world.disposedListeners.size, 0);
  assert.equal(world.projection.onChangedListeners.size, 0);
});

test("projection envelope getters are contained in both read and track", () => {
  const world = installKnownWorld();
  world.projection.snapshot = () => ({
    asOfSeq: world.session.seq - 1,
    get values() { throw new Error("PRIVATE_PROJECTION_SENTINEL"); },
  });
  const snapshot = world.read();
  assert.equal(snapshot.capture.status, "unknown");
  assert.ok(!JSON.stringify(snapshot).includes("PRIVATE_PROJECTION_SENTINEL"));
  world.capture.untrack(world.handle);
  assert.doesNotThrow(() => world.capture.track(world.request));
});

test("identifiers reject unpaired surrogates before transport", () => {
  const world = createWorld();
  assert.throws(() => world.capture.track(makeRequest({ nativeSessionId: "\ud800" })), CaptureError);
});
