/**
 * TALK execution-session runner for the installed DeepSeek Harness.
 *
 * It is mounted by a per-spawn overlay that disables the stock headless
 * startup/runner and inserts this plugin. The bridge writes a private request
 * JSON (query or deliver) and reads one atomic result JSON after this process
 * exits. All identities come from the bridge request; this plugin only checks
 * them against the live native session and the native model selection.
 *
 * Query mode never calls the model. Deliver mode creates or resumes the exact
 * managed session, tracks the existing context collector, appends the
 * directive as one native user message, waits for the turn, flushes, and
 * confirms delivery from the durable `user/message` event before writing the
 * result.
 */
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

import { HOST_VERSION, assistantTextFrom, findCommittedDirective, mountCapture, readSnapshot, runtimeConfigFingerprint, safeTurnError, sha256Text, trackSession } from "./dsh_context_host.mjs";

export const name = "talk-execution-runner";
export const inject = ["agents", "sessions", "agentDefaultModel", "sessionProjections"];

const REQUEST_SCHEMA = "talk-dsh-execution-request-1";
const RESULT_SCHEMA = "talk-dsh-execution-result-1";
const REQUEST_VERSION = 1;
const RESULT_VERSION = 1;
const PLUGIN_VERSION = "1.0.0";
const MAX_REQUEST_BYTES = 4 * 1024 * 1024;
const MAX_RESULT_BYTES = 8 * 1024 * 1024;
const NATIVE_SESSION_RE = /^session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CONTROL_RE = /[\x00-\x1f\x7f]/;
const TEXT_CONTROL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/;

class ProtocolError extends Error {
  constructor(code, field) {
    super(field ? `${code}:${field}` : code);
    this.code = code;
    this.field = field ?? null;
  }
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isSafeInteger(value, minimum = 0) {
  return Number.isSafeInteger(value) && value >= minimum;
}

function requireString(value, field, { max = 4096, allowEmpty = false, multiline = false } = {}) {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    throw new ProtocolError("field_invalid", field);
  }
  if (value.length > max) throw new ProtocolError("field_too_large", field);
  if ((multiline ? TEXT_CONTROL_RE : CONTROL_RE).test(value)) {
    throw new ProtocolError("field_control", field);
  }
  return value;
}

function canonicalJson(value) {
  if (Array.isArray(value)) return value.map(canonicalJson);
  if (isPlainObject(value)) {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalJson(value[key]);
    return out;
  }
  return value;
}

function jsonSha256(value) {
  return sha256Text(JSON.stringify(canonicalJson(value)));
}

function withinRoot(root, target) {
  const rel = relative(root, target);
  return rel === "" || (rel !== ".." && !rel.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`) && !isAbsolute(rel));
}

function validatePaths(config, request) {
  const requestPath = requireString(config.requestPath, "requestPath", { max: 32768 });
  const outputPath = requireString(config.outputPath, "outputPath", { max: 32768 });
  if (!isAbsolute(requestPath) || !isAbsolute(outputPath)) {
    throw new ProtocolError("path_not_absolute", "paths");
  }
  if (!isPlainObject(request.paths)) throw new ProtocolError("field_invalid", "paths");
  const allowedRoot = requireString(request.paths.allowedRoot, "paths.allowedRoot", { max: 32768 });
  if (!isAbsolute(allowedRoot)) throw new ProtocolError("path_not_absolute", "paths.allowedRoot");
  if (request.paths.request !== requestPath || request.paths.output !== outputPath) {
    throw new ProtocolError("path_mismatch", "paths");
  }
  let rootReal;
  let requestReal;
  let outputReal;
  try {
    rootReal = realpathSync.native(resolve(allowedRoot));
    requestReal = realpathSync.native(resolve(requestPath));
    const outputParentReal = realpathSync.native(dirname(resolve(outputPath)));
    outputReal = join(outputParentReal, basename(resolve(outputPath)));
  } catch {
    throw new ProtocolError("path_unverifiable", "paths");
  }
  if (!statSync(rootReal).isDirectory() || !withinRoot(rootReal, requestReal) || !withinRoot(rootReal, outputReal)) {
    throw new ProtocolError("path_outside_root", "paths");
  }
  if (requestReal === outputReal) throw new ProtocolError("path_conflict", "paths");
  return { requestPath: requestReal, outputPath: outputReal, allowedRoot: rootReal };
}

function readRequest(requestPath) {
  let size;
  try {
    size = statSync(requestPath).size;
  } catch {
    throw new ProtocolError("request_unreadable", "request");
  }
  if (size <= 0 || size > MAX_REQUEST_BYTES) {
    throw new ProtocolError("request_size_invalid", "request");
  }
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(requestPath, "utf8"));
  } catch {
    throw new ProtocolError("request_json_invalid", "request");
  }
  if (!isPlainObject(parsed)) throw new ProtocolError("request_invalid", "request");
  return parsed;
}

function validateRequest(request, config, mode) {
  if (request.schema !== REQUEST_SCHEMA) throw new ProtocolError("schema_unsupported", "schema");
  if (request.version !== REQUEST_VERSION) throw new ProtocolError("version_unsupported", "version");
  if (request.mode !== mode) throw new ProtocolError("mode_mismatch", "mode");
  if (typeof request.requestDigest !== "string" || !/^[0-9a-f]{64}$/.test(request.requestDigest)) {
    throw new ProtocolError("digest_invalid", "requestDigest");
  }
  const body = { ...request };
  delete body.requestDigest;
  if (jsonSha256(body) !== request.requestDigest) {
    throw new ProtocolError("digest_mismatch", "requestDigest");
  }
  if (!isPlainObject(request.native)) throw new ProtocolError("field_invalid", "native");
  const action = request.native.action;
  if (action !== "create" && action !== "resume") {
    throw new ProtocolError("action_invalid", "native.action");
  }
  const sessionId = requireString(request.native.sessionId, "native.sessionId", { max: 128 });
  if (!NATIVE_SESSION_RE.test(sessionId)) throw new ProtocolError("session_id_invalid", "native.sessionId");
  if (!isSafeInteger(request.native.sessionGeneration, 1) || request.native.sessionGeneration > Number.MAX_SAFE_INTEGER) {
    throw new ProtocolError("generation_invalid", "native.sessionGeneration");
  }
  if (request.native.previousCut !== undefined && request.native.previousCut !== null) {
    if (!isSafeInteger(request.native.previousCut, -1) || request.native.previousCut < -1) {
      throw new ProtocolError("cut_invalid", "native.previousCut");
    }
  }
  if (request.native.expectedRevision !== undefined && request.native.expectedRevision !== null) {
    if (!isSafeInteger(request.native.expectedRevision, 0)) {
      throw new ProtocolError("revision_invalid", "native.expectedRevision");
    }
  }
  const workspacePath = requireString(request.workspacePath, "workspacePath", { max: 32768 });
  if (!isAbsolute(workspacePath)) throw new ProtocolError("path_not_absolute", "workspacePath");
  const identity = request.identity;
  if (!isPlainObject(identity)) throw new ProtocolError("field_invalid", "identity");
  for (const field of [
    "projectId",
    "targetMemberId",
    "requesterId",
    "continuityKey",
    "workspaceIdentity",
    "nativeHomeNamespace",
    "runnerId",
    "serviceLaunchId",
    "providerId",
    "modelId",
    "modelBindingFingerprint",
    "configPermissionFingerprint",
  ]) {
    requireString(identity[field], `identity.${field}`, { max: 512 });
  }
  const nativePackageRoot = requireString(request.nativePackageRoot, "nativePackageRoot", { max: 32768 });
  if (!isAbsolute(nativePackageRoot)) throw new ProtocolError("path_not_absolute", "nativePackageRoot");
  const turnTimeoutMs = request.turnTimeoutMs;
  if (!isSafeInteger(turnTimeoutMs, 1000) || turnTimeoutMs > 86_400_000) {
    throw new ProtocolError("timeout_invalid", "turnTimeoutMs");
  }
  if (mode === "deliver") {
    const directive = request.directive;
    if (!isPlainObject(directive)) throw new ProtocolError("field_invalid", "directive");
    requireString(directive.text, "directive.text", {
      max: 2 * 1024 * 1024,
      multiline: true,
    });
    if (sha256Text(directive.text) !== directive.sha256) {
      throw new ProtocolError("directive_sha_mismatch", "directive.sha256");
    }
    requireString(directive.deliveryId, "directive.deliveryId", { max: 160 });
    requireString(directive.taskId, "directive.taskId", { max: 64 });
    if (!isSafeInteger(directive.attempt)) throw new ProtocolError("field_invalid", "directive.attempt");
    requireString(directive.executionId, "directive.executionId", { max: 160 });
    if (typeof directive.firstTurn !== "boolean") throw new ProtocolError("field_invalid", "directive.firstTurn");
  }
  return {
    sessionId,
    sessionGeneration: request.native.sessionGeneration,
    action,
    workspacePath,
    nativePackageRoot,
    turnTimeoutMs,
  };
}

function writeResult(outputPath, payload) {
  const encoded = Buffer.from(JSON.stringify(payload), "utf8");
  if (encoded.length > MAX_RESULT_BYTES) throw new ProtocolError("result_too_large", "result");
  mkdirSync(dirname(outputPath), { recursive: true });
  const temp = join(dirname(outputPath), `.${process.pid}-${randomUUID()}.tmp`);
  writeFileSync(temp, encoded, { encoding: "utf8", mode: 0o600 });
  if (existsSync(outputPath)) {
    rmSync(temp, { force: true });
    throw new ProtocolError("output_exists", "output");
  }
  renameSync(temp, outputPath);
}

async function loadNative(nativePackageRoot) {
  const manifestPath = join(nativePackageRoot, "package.json");
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch {
    throw new ProtocolError("native_package_unreadable", "nativePackageRoot");
  }
  if (manifest?.name !== "@deepseek-ai/dsh") {
    throw new ProtocolError("native_package_identity", "nativePackageRoot");
  }
  if (manifest.version !== '0.1.5-rc.2') throw new ProtocolError('native_package_version_unsupported');
  const require = createRequire(pathToFileURL(manifestPath));
  const agentPath = require.resolve("@deepseek-ai/dsh-agent");
  const llmPath = require.resolve("@deepseek-ai/dsh-llm");
  const agent = await import(pathToFileURL(agentPath).href);
  const llm = await import(pathToFileURL(llmPath).href);
  if (typeof agent.installModelSelection !== "function" || typeof llm.createUserMessage !== "function") {
    throw new ProtocolError("native_api_missing", "nativePackageRoot");
  }
  return { installModelSelection: agent.installModelSelection, createUserMessage: llm.createUserMessage };
}

function modelOf(selection) {
  if (!isPlainObject(selection)) return null;
  if (typeof selection.provider !== "string" || typeof selection.model !== "string") return null;
  return { provider: selection.provider, model: selection.model };
}

async function queryOrDeliver(ctx, config) {
  const mode = config.mode;
  if (mode !== "query" && mode !== "deliver") throw new ProtocolError("mode_invalid", "mode");
  if (config.pluginVersion !== PLUGIN_VERSION) {
    throw new ProtocolError("plugin_version_mismatch", "pluginVersion");
  }
  const request = readRequest(resolve(config.requestPath));
  const paths = validatePaths(config, request);
  const validated = validateRequest(request, config, mode);
  const native = await loadNative(validated.nativePackageRoot);

  await ctx.get("loader")?.await();
  const agents = ctx.get("agents");
  const sessions = ctx.get("sessions");
  const defaultModel = ctx.get("agentDefaultModel");
  if (agents === undefined || sessions === undefined || defaultModel === undefined) {
    throw new ProtocolError("native_service_missing", "services");
  }
  const selection = defaultModel.currentSelection();
  const currentModel = modelOf(selection);
  if (currentModel === null || currentModel.provider !== request.identity.providerId || currentModel.model !== request.identity.modelId) {
    return {
      schema: RESULT_SCHEMA,
      version: RESULT_VERSION,
      status: "unavailable",
      mode,
      reason_code: "model_mismatch",
      request_digest: request.requestDigest,
      host_version: HOST_VERSION,
      query: null,
      delivery: null,
    };
  }

  let agent;
  let createdOrResumed = false;
  try {
    const setup = (agentCtx) => {
      native.installModelSelection(agentCtx, { current: selection, assembled: void 0 });
    };
    if (validated.action === "create") {
      ({ agent } = await agents.create({
        sessionId: validated.sessionId,
        meta: { cwd: validated.workspacePath },
        agentOptions: { provider: selection.provider, model: selection.model },
        setup,
      }));
    } else {
      ({ agent } = await agents.resume({
        resumeSessionId: validated.sessionId,
        agentOptions: { provider: selection.provider, model: selection.model },
        setup,
      }));
    }
    createdOrResumed = true;
  } catch {
    return {
      schema: RESULT_SCHEMA,
      version: RESULT_VERSION,
      status: "unavailable",
      mode,
      reason_code: "session_unavailable",
      request_digest: request.requestDigest,
      host_version: HOST_VERSION,
      query: null,
      delivery: null,
    };
  }

  // Verify the exact live identity before any model call.
  const liveSession = agent.session;
  const liveId = liveSession?.id;
  const liveCwd = liveSession?.header?.cwd;
  if (liveId !== validated.sessionId || liveCwd !== validated.workspacePath) {
    return {
      schema: RESULT_SCHEMA,
      version: RESULT_VERSION,
      status: "unavailable",
      mode,
      reason_code: "session_identity_mismatch",
      request_digest: request.requestDigest,
      host_version: HOST_VERSION,
      query: null,
      delivery: null,
    };
  }
  const inventoryHash = runtimeConfigFingerprint(agent.ctx, liveSession, selection);
  if (request.native.expectedInventoryHash !== undefined && request.native.expectedInventoryHash !== null &&
      inventoryHash !== request.native.expectedInventoryHash) {
    throw new ProtocolError('runtime_config_changed', 'native.expectedInventoryHash');
  }
  await agent.whenIdle();
  const firstSeq = liveSession.seq;
  if (
    validated.action === "resume" &&
    isSafeInteger(request.native.expectedRevision, 0)
  ) {
    const expected = request.native.expectedRevision;
    const liveCut = liveSession.seq - 1;
    let benignClose = false;
    if (liveCut === expected + 1) {
      const last = liveSession.eventAt(liveCut);
      benignClose = last !== undefined && last.type === "session/end-seed";
    }
    if (liveCut !== expected && !benignClose) {
      return {
        schema: RESULT_SCHEMA,
        version: RESULT_VERSION,
        status: "unavailable",
        mode,
        reason_code: "session_changed_since_query",
        request_digest: request.requestDigest,
        host_version: HOST_VERSION,
        inventory_hash: inventoryHash,
        query: null,
        delivery: null,
      };
    }
  }

  const capture = mountCapture(ctx);
  const handle = trackSession(capture, request);
  if (!handle || handle.bound !== true) throw new ProtocolError('capture_unbound');
  if (mode === "query") {
    let revision = liveSession.seq - 1;
    let metrics = null;
    try {
      const projections = ctx.get("sessionProjections");
      const snap = projections?.snapshot?.(liveSession, ["contextPressure"]);
      if (isPlainObject(snap) && isSafeInteger(snap.asOfSeq, -1) && isPlainObject(snap.values)) {
        revision = snap.asOfSeq;
        const view = snap.values.contextPressure;
        if (isPlainObject(view)) metrics = view;
      }
    } catch {
      metrics = null;
    }
    const appended = [];
    if (isSafeInteger(request.native.previousCut, -1) && request.native.previousCut >= -1) {
      const from = Math.max(0, request.native.previousCut + 1);
      for (let seq = from; seq <= revision && appended.length < 64; seq++) {
        const event = liveSession.eventAt(seq);
        if (event !== undefined) appended.push(String(event.type ?? "unknown"));
      }
    }
    const snapshot = readSnapshot(capture, handle, {
      now: Date.now(), sessionGeneration: validated.sessionGeneration,
      previousCut: request.native.previousCut,
    });
    capture.untrack(handle);
    await sessions.flush(liveSession);
    return {
      schema: RESULT_SCHEMA,
      version: RESULT_VERSION,
      status: "ok",
      mode,
      request_digest: request.requestDigest,
      host_version: HOST_VERSION,
      inventory_hash: inventoryHash,
      snapshot,
      query: {
        native_session_id: liveSession.id,
        session_generation: validated.sessionGeneration,
        session_revision: revision,
        session_seq: liveSession.seq,
        appended_event_types: appended,
        cwd: liveCwd,
        provider_id: currentModel.provider,
        model_id: currentModel.model,
        lifecycle: "live",
        metrics_status: "unverified_query",
        metrics: isPlainObject(metrics) ? metrics : null,
      },
      delivery: null,
    };
  }

  // Deliver: track before the new native events, then append one user message.
  if (!handle || handle.bound !== true) {
    return {
      schema: RESULT_SCHEMA,
      version: RESULT_VERSION,
      status: "unavailable",
      mode,
      reason_code: "capture_unbound",
      request_digest: request.requestDigest,
      host_version: HOST_VERSION,
      inventory_hash: inventoryHash,
      query: null,
      delivery: null,
    };
  }

  let timedOut = false;
  let canceled = false;
  let durable = false;
  let assistant = { text: "", turnReason: null, turnEndSeq: null };
  const startedAt = new Date().toISOString();
  try {
    agent.followup(
      native.createUserMessage({
        content: [{ type: "text", text: request.directive.text }],
        source: { kind: "user" },
      })
    );
    const idle = agent.whenIdle().then(() => "idle");
    let timeoutHandle = null;
    const timeout = new Promise((resolve) => {
      timeoutHandle = setTimeout(() => resolve("timeout"), validated.turnTimeoutMs);
      // Do not keep the process alive after a fast turn; the race clears it.
      timeoutHandle.unref?.();
    });
    const winner = await Promise.race([idle, timeout]);
    if (timeoutHandle !== null) clearTimeout(timeoutHandle);
    if (winner === "timeout") {
      timedOut = true;
      try {
        agent.cancel(new Error("talk execution delivery timeout"), { keepInbox: true });
      } catch {
        canceled = true;
      }
      await Promise.race([agent.whenIdle(), sleep(5000)]);
    }
  } catch {
    // The turn may have failed after the user message was already committed;
    // inspect the durable log below instead of assuming non-delivery.
  } finally {
    try {
      await sessions.flush(liveSession);
      durable = true;
    } catch {
      // Result still records whether the durable user/message was observed.
    }
    assistant = assistantTextFrom(liveSession, firstSeq);
  }

  let snapshot = null;
  try {
    if (handle.bound === true) {
      snapshot = readSnapshot(capture, handle, {
        now: Date.now(),
        sessionGeneration: validated.sessionGeneration,
        previousCut: request.native.previousCut,
      });
    }
  } catch {
    snapshot = null;
  }
  try {
    capture.untrack(handle);
  } catch {
    // ignore disposal failure; no raw error crosses the protocol
  }

  const committed = durable ? findCommittedDirective(liveSession, firstSeq, request.directive.text) : null;
  const revision =
    isPlainObject(snapshot) && isSafeInteger(snapshot.session?.revision, 0)
      ? snapshot.session.revision
      : Math.max(0, liveSession.seq - 1);
  const reasonKind = assistant.turnReason?.kind ?? null;
  let outcome;
  if (committed === null) {
    outcome = timedOut ? "timed_out_before_delivery" : "failed_before_delivery";
  } else if (timedOut) {
    outcome = "timed_out_after_delivery";
  } else if (reasonKind === "canceled" || canceled) {
    outcome = "canceled_after_delivery";
  } else {
    outcome = "delivered";
  }
  const turnOutcome = timedOut
    ? "timeout"
    : reasonKind === "completed"
      ? "completed"
      : reasonKind === "error"
        ? "error"
        : reasonKind === "canceled"
          ? "canceled"
          : "unknown";

  return {
    schema: RESULT_SCHEMA,
    version: RESULT_VERSION,
    status: "ok",
    mode,
    request_digest: request.requestDigest,
    host_version: HOST_VERSION,
    inventory_hash: inventoryHash,
    query: null,
    snapshot,
    delivery: {
      delivery_id: request.directive.deliveryId,
      task_id: request.directive.taskId,
      attempt: request.directive.attempt,
      execution_id: request.directive.executionId,
      body_sha256: request.directive.sha256,
      native_session_id: liveSession.id,
      session_generation: validated.sessionGeneration,
      session_revision: revision,
      first_turn: request.directive.firstTurn,
      outcome,
      turn_outcome: turnOutcome,
      turn_error: safeTurnError(assistant.turnReason),
      directive_committed: committed !== null,
      directive_seq: committed?.seq ?? null,
      assistant_text: assistant.text,
      started_at: startedAt,
      completed_at: new Date().toISOString(),
    },
  };
}

async function run(ctx, config) {
  let outputPath = null;
  try {
    if (!isPlainObject(config)) throw new ProtocolError("config_invalid", "config");
    const requestPath = requireString(config.requestPath, "requestPath", { max: 32768 });
    requireString(config.outputPath, "outputPath", { max: 32768 });
    const request = readRequest(requestPath);
    outputPath = validatePaths(config, request).outputPath;
    const payload = await queryOrDeliver(ctx, config);
    payload.plugin_version = PLUGIN_VERSION;
    writeResult(outputPath, payload);
    return 0;
  } catch (error) {
    if (outputPath !== null) {
      try {
        writeResult(outputPath, {
          schema: RESULT_SCHEMA,
          version: RESULT_VERSION,
          status: "error",
          mode: typeof config?.mode === "string" ? config.mode : "unknown",
          reason_code: error instanceof ProtocolError ? error.code : "runner_failed",
          field: error instanceof ProtocolError ? error.field : null,
          request_digest: null,
          host_version: HOST_VERSION,
          query: null,
          delivery: null,
        });
      } catch {
        // No output path can be trusted; the bridge will taint the attempt.
      }
    }
    try {
      process.stderr.write(
        `talk-execution-runner: ${error instanceof ProtocolError ? error.code : "runner_failed"}\n`
      );
    } catch {
      // ignore
    }
    return 1;
  }
}

export function apply(ctx, config) {
  const exit = ctx.get("appExit");
  if (exit === undefined) {
    throw new Error("talk-execution-runner: the launcher must provide ctx.appExit");
  }
  run(ctx, config)
    .then((code) => exit(code))
    .catch(() => exit(1));
}

// Test-only exports: request/path/result helpers are pure and do not mount the
// plugin. Keeping them named with an underscore avoids presenting them as the
// native runner contract.
export {
  run as _run,
  validatePaths as _validatePaths,
  validateRequest as _validateRequest,
  writeResult as _writeResult,
  jsonSha256 as _jsonSha256,
  PLUGIN_VERSION as _PLUGIN_VERSION,
};
