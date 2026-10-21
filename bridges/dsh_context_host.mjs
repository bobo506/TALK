/**
 * TALK execution-session host helpers for the native DSH runner.
 *
 * This module is loaded inside the isolated TALK runner plugin. It wraps the
 * existing `dsh_context_capture.mjs` collector (no second rule set) and only
 * adapts native services/events to its documented camelCase request shape.
 * It performs no file, network, process or model call by itself.
 */
import { createHash } from "node:crypto";

import { mountContextCapture } from "./dsh_context_capture.mjs";

export const HOST_VERSION = "dsh_context_host/1.0.0";
export const HOST_ATTESTATION_SOURCE = "talk-execution-runner/1.0.0";

export function sha256Text(text) {
  return createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
    return out;
  }
  return value;
}

export function buildTrackRequest(request) {
  const identity = request.identity;
  return {
    nativeSessionId: request.native.sessionId,
    projectId: identity.projectId,
    targetMemberId: identity.targetMemberId,
    requesterId: identity.requesterId,
    continuityKey: identity.continuityKey,
    workspaceIdentity: identity.workspaceIdentity,
    workspacePath: request.workspacePath,
    nativeHomeNamespace: identity.nativeHomeNamespace,
    runnerId: identity.runnerId,
    serviceLaunchId: identity.serviceLaunchId,
    providerId: identity.providerId,
    modelId: identity.modelId,
    modelBindingFingerprint: identity.modelBindingFingerprint,
    configPermissionFingerprint: identity.configPermissionFingerprint,
    sessionGeneration: request.native.sessionGeneration,
    hostAttestation: {
      verified: true,
      source: HOST_ATTESTATION_SOURCE,
    },
    resumeRestore: request.native.action === "resume",
  };
}

export function mountCapture(ctx) {
  return mountContextCapture(ctx, {});
}

export function trackSession(capture, request) {
  const handle = capture.track(buildTrackRequest(request));
  return handle;
}

export function readSnapshot(
  capture,
  handle,
  { now, sessionGeneration, previousCut }
) {
  const options = { now, sessionGeneration };
  if (previousCut !== undefined && previousCut !== null) {
    options.previousCut = previousCut;
  }
  return capture.read(handle, options);
}

export function loaderInventory(ctx) {
  const loader = ctx.get?.("loader");
  if (loader === undefined || typeof loader.entries !== "function") {
    return null;
  }
  const rows = [];
  try {
    for (const entry of Array.from(loader.entries())) {
      if (entry === null || typeof entry !== "object") continue;
      rows.push({
        id: typeof entry.id === "string" ? entry.id : null,
        name: typeof entry.options?.name === "string" ? entry.options.name : null,
        disabled: entry.disabled === true,
      });
    }
  } catch {
    return null;
  }
  rows.sort((left, right) =>
    `${left.id ?? ""}\0${left.name ?? ""}`.localeCompare(
      `${right.id ?? ""}\0${right.name ?? ""}`
    )
  );
  return sha256Text(canonicalJson({ schema: "talk-dsh-entry-inventory-1", version: 1, entries: rows }));
}

const RUNTIME_CONFIG_EVENT_TYPES = new Set([
  "permission/preset",
  "sandbox/mode",
  "approval/policy",
]);

/**
 * Runtime config/permission fingerprint bound to the exact live session.
 *
 * Includes the loaded plugin inventory (ids/names/disabled), the verified model
 * selection, and the session's own permission/sandbox/approval facts. It never
 * reads user settings files, credentials, or secret values. This is used as an
 * additional same-window guard: a changed permission/sandbox/plugin tree makes
 * the next query's fingerprint differ and forces a new full window.
 */
export function runtimeConfigFingerprint(ctx, session, selection) {
  const inventory = loaderInventory(ctx);
  if (inventory === null) return null;
  let permissions;
  try {
    const sandbox = ctx.get('sandboxPolicy');
    const approval = ctx.get('approval');
    const presets = ctx.get('permissionPresets');
    const resolved = sandbox?.resolve({session});
    const policy = approval?.effectivePolicy(session);
    if (!['read-only','workspace-write','danger-full-access'].includes(resolved?.mode) ||
        !['ask','never'].includes(policy) || typeof resolved?.workspaceRoot !== 'string' ||
        typeof presets?.current !== 'function') return null;
    permissions = {
      mode: resolved.mode, workspaceRoot: resolved.workspaceRoot, approval: policy,
      preset: presets.current(session),
      deploymentMode: sandbox.defaultMode,
      deploymentApproval: approval.config.policy ?? 'ask',
      deploymentPreset: presets.defaultPreset,
    };
    if (Object.values(permissions).some(value => typeof value !== 'string')) return null;
  } catch {
    return null;
  }
  return sha256Text(
    canonicalJson({
      schema: "talk-dsh-runtime-config-1",
      version: 1,
      inventory_sha256: inventory,
      model: {
        provider: selection?.provider ?? null,
        model: selection?.model ?? null,
        reasoningEffort: selection?.reasoningEffort ?? null,
      },
      permissions,
    })
  );
}

export function assistantTextFrom(session, firstSeq) {
  let started = false;
  let text = "";
  let turnReason = null;
  let turnEndSeq = null;
  let userCommitted = false;
  for (let seq = firstSeq; seq < session.seq; seq++) {
    const event = session.eventAt(seq);
    if (event === undefined) continue;
    if (event.type === "turn/start") {
      started = true;
      continue;
    }
    if (!started) continue;
    if (event.type === "assistant/message") {
      const blocks = event.data?.message?.content;
      if (Array.isArray(blocks)) {
        const joined = blocks
          .filter((block) => block?.type === "text")
          .map((block) => block.text)
          .join("");
        if (joined !== "") text = joined;
      }
    }
    if (event.type === "turn/end") {
      turnReason = event.data?.reason ?? null;
      turnEndSeq = seq;
    }
  }
  return { text, turnReason, turnEndSeq, userCommitted };
}

export function findCommittedDirective(session, firstSeq, directiveText) {
  for (let seq = firstSeq; seq < session.seq; seq++) {
    const event = session.eventAt(seq);
    if (event === undefined || event.type !== "user/message") continue;
    const content = event.data?.content;
    if (!Array.isArray(content)) continue;
    const text = content
      .filter((block) => block?.type === "text")
      .map((block) => block.text)
      .join("");
    if (text === directiveText) {
      return { seq, event };
    }
  }
  return null;
}

export function turnOutcomeOf(reason, { timedOut = false, canceled = false } = {}) {
  if (timedOut) return "timed_out_after_delivery";
  if (canceled) return "canceled_after_delivery";
  if (reason !== null && typeof reason === "object" && reason.kind === "error") {
    return "delivered";
  }
  if (reason !== null && typeof reason === "object" && reason.kind === "canceled") {
    return "canceled_after_delivery";
  }
  return "delivered";
}

export function safeTurnError(reason) {
  if (reason === null || typeof reason !== "object") return null;
  if (reason.kind !== "error") return null;
  const code =
    reason.error !== null && typeof reason.error === "object"
      ? String(reason.error.code ?? "turn_error").slice(0, 80)
      : "turn_error";
  return { code };
}
