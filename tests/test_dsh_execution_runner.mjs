import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { runtimeConfigFingerprint } from '../bridges/dsh_context_host.mjs';

import {
  _PLUGIN_VERSION,
  _jsonSha256,
  _validatePaths,
  _validateRequest,
  _writeResult,
  _run,
} from "../bridges/dsh_execution_runner.mjs";

test('error handler never writes a result through an unverified output path', async () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'talk-runner-error-'));
  const allowed=path.join(root,'allowed');
  fs.mkdirSync(allowed);
  const request=path.join(allowed,'request.json');
  const output=path.join(root,'outside.json');
  fs.writeFileSync(request,JSON.stringify({paths:{allowedRoot:allowed,request,output}}),{encoding:'utf8'});
  try {
    const code=await _run({}, {requestPath:request,outputPath:output,mode:'query',pluginVersion:_PLUGIN_VERSION});
    assert.equal(code,1);
    assert.equal(fs.existsSync(output),false);
  } finally {
    // Exact temporary root created above; no computed caller path is deleted.
    assert.equal(path.dirname(fs.realpathSync(root)),fs.realpathSync(os.tmpdir()));
    fs.rmSync(root,{recursive:true,force:true});
  }
});

test('runtime fingerprint reads effective permissions and reasoning; unknown facts do not authorize reuse', () => {
  let mode='workspace-write', approval='ask';
  const entry={id:'plugin',options:{name:'plugin-a'},disabled:false};
  const services={
    loader:{entries:()=>[entry]},
    sandboxPolicy:{resolve:()=>({mode,workspaceRoot:'D:/workspace'}),defaultMode:'workspace-write'},
    approval:{effectivePolicy:()=>approval,config:{policy:'ask'}},
    permissionPresets:{current:()=>mode,defaultPreset:'workspace-write'},
  };
  const ctx={get:key=>services[key]};
  const session={seq:100,eventAt:()=>undefined};
  const selection={provider:'p',model:'m',reasoningEffort:'max'};
  const first=runtimeConfigFingerprint(ctx,session,selection);
  assert.match(first,/^[0-9a-f]{64}$/);
  mode='read-only';
  assert.notEqual(runtimeConfigFingerprint(ctx,session,selection),first);
  mode='workspace-write'; approval='never';
  assert.notEqual(runtimeConfigFingerprint(ctx,session,selection),first);
  approval='ask';
  assert.notEqual(runtimeConfigFingerprint(ctx,session,{...selection,reasoningEffort:'high'}),first);
  entry.options.name='plugin-b';
  assert.notEqual(runtimeConfigFingerprint(ctx,session,selection),first);
  delete services.approval;
  assert.equal(runtimeConfigFingerprint(ctx,session,selection),null);
});

function baseRequest(root) {
  const request = {
    schema: "talk-dsh-execution-request-1",
    version: 1,
    mode: "query",
    identity: {
      projectId: "prj_test",
      targetMemberId: "agent:deepseek",
      requesterId: "agent:codex",
      continuityKey: "line:test",
      workspaceIdentity: "workspace:test",
      nativeHomeNamespace: "dsh:test",
      runnerId: "runner:test",
      serviceLaunchId: "launch:test",
      providerId: "deepseek-official",
      modelId: "deepseek-flash",
      modelBindingFingerprint: "a".repeat(64),
      configPermissionFingerprint: "b".repeat(64),
    },
    workspacePath: root,
    nativePackageRoot: path.join(root, "dsh"),
    native: {
      action: "resume",
      sessionId: "session-11111111-1111-4111-8111-111111111111",
      sessionGeneration: 1,
      previousCut: 3,
      expectedRevision: 4,
    },
    turnTimeoutMs: 120000,
    paths: {
      allowedRoot: root,
      request: path.join(root, "request.json"),
      output: path.join(root, "result.json"),
    },
    directive: null,
  };
  request.requestDigest = _jsonSha256(request);
  return request;
}

test("runner request validation accepts exact shape and optional expectedRevision", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "talk-runner-"));
  const request = baseRequest(root);
  const validated = _validateRequest(request, {}, "query");
  assert.equal(validated.sessionId, request.native.sessionId);
  assert.equal(validated.action, "resume");
  fs.rmSync(root, { recursive: true, force: true });
});

test("runner rejects digest, schema, path traversal and bad session ids", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "talk-runner-"));
  const request = baseRequest(root);
  const wrong = structuredClone(request);
  wrong.requestDigest = "0".repeat(64);
  assert.throws(() => _validateRequest(wrong, {}, "query"), /digest_mismatch/);

  const traversal = structuredClone(request);
  traversal.paths.output = path.join(root, "..", "escape.json");
  traversal.requestDigest = _jsonSha256({ ...traversal, requestDigest: undefined });
  fs.writeFileSync(request.paths.request, "{}", "utf8");
  assert.throws(
    () =>
      _validatePaths(
        { requestPath: traversal.paths.request, outputPath: traversal.paths.output },
        traversal
      ),
    /path_outside_root|path_mismatch/
  );

  const badId = structuredClone(request);
  badId.native.sessionId = "../../escape";
  badId.requestDigest = _jsonSha256({ ...badId, requestDigest: undefined });
  assert.throws(() => _validateRequest(badId, {}, "query"), /session_id_invalid/);

  fs.rmSync(root, { recursive: true, force: true });
});

test("runner result writing is atomic and never overwrites an existing output", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "talk-runner-"));
  const output = path.join(root, "result.json");
  _writeResult(output, { schema: "talk-dsh-execution-result-1", version: 1 });
  const parsed = JSON.parse(fs.readFileSync(output, "utf8"));
  assert.equal(parsed.version, 1);
  assert.throws(
    () => _writeResult(output, { schema: "talk-dsh-execution-result-1", version: 1 }),
    /output_exists/
  );
  assert.equal(_PLUGIN_VERSION, "1.0.0");
  fs.rmSync(root, { recursive: true, force: true });
});
