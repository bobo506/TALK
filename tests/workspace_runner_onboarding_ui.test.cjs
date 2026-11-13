const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../web/workspace.js"), "utf8");
const part = source.slice(source.indexOf("const runnerOnboardingUI"), source.indexOf("const ROLE_TASKS_PAGE_SIZE"));
const codex = { runtime: "codex", display_name: "Codex CLI", detected_version: "1", status: "match" };
const kimi = { runtime: "kimi-code", display_name: "Kimi Code", detected_version: "1", status: "match" };
const workbuddy = { runtime: "workbuddy", display_name: "WorkBuddy", detected_version: "1", status: "match" };
const missingRunners = [codex, kimi, { runtime: "dsh", display_name: "DeepSeek Harness" }]
  .map(item => ({ ...item, detected_version: null, status: "unknown", probe_status: "missing" }));

function harness(items = [codex], roles = []) {
  const nodes = {}, storage = new Map(), calls = { render: 0, open: 0, sync: 0, scroll: 0, warnings: [] };
  let otherModal = false;
  const document = { activeElement: null, getElementById: id => nodes[id] || null,
    querySelector: () => otherModal || !nodes["runner-onboarding-overlay"].classList.contains("hidden") ? {} : null };
  function node(id) {
    const listeners = {}, classes = new Set();
    const n = { textContent: "", isConnected: true, classList: { add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x) },
      addEventListener(type, fn) { listeners[type] = fn; }, fire(type, event = {}) { listeners[type]?.(event); },
      focus() { document.activeElement = n; }, scrollIntoView() { calls.scroll++; } };
    nodes[id] = n; return n;
  }
  for (const id of ["runner-onboarding-overlay", "runner-onboarding-title", "runner-onboarding-message", "runner-onboarding-close", "runner-onboarding-dismiss", "runner-onboarding-action", "runner-versions-panel"]) node(id);
  nodes["runner-onboarding-overlay"].classList.add("hidden");
  const before = node("before"); before.focus();
  const env = { document, sessionStorage: { getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v) },
    console: { warn: (...args) => calls.warnings.push(args) }, myId: "human:a", activeProjectId: "p1", projectAgents: roles,
    currentMemberIsHuman: () => true, workspaceUI: { mode: "tasks", roleSelection: "role" }, blackboardOpen: false,
    apiFetch: async () => ({ok: true, json: async () => items}), renderWorkspaceMode: () => calls.render++,
    syncRunnerVersions: () => calls.sync++, roleRequestApp: { open: () => calls.open++ } };
  vm.createContext(env); vm.runInContext(part, env);
  return { env, nodes, calls, storage, before, node, setItems: value => { items = value; }, setOtherModal: value => { otherModal = value; },
    hidden: () => nodes["runner-onboarding-overlay"].classList.contains("hidden"), click: id => nodes[id].fire("click") };
}

test("零角色且 Codex 可用时显示创建引导并还原焦点", async () => {
  const h = harness(); await h.env.maybeShowRunnerOnboarding();
  assert.equal(h.hidden(), false); assert.match(h.nodes["runner-onboarding-title"].textContent, /Codex CLI/);
  assert.equal(h.nodes["runner-onboarding-action"].textContent, "创建角色");
  assert.equal(h.env.document.activeElement, h.nodes["runner-onboarding-action"]);
  h.click("runner-onboarding-close"); assert.equal(h.hidden(), true); assert.equal(h.env.document.activeElement, h.before);
});
test("多个可用运行器包含版本关系提示", async () => {
  const h = harness([{...codex, status: "newer"}, kimi]); await h.env.maybeShowRunnerOnboarding();
  assert.match(h.nodes["runner-onboarding-message"].textContent, /Codex CLI、Kimi Code/);
  assert.match(h.nodes["runner-onboarding-message"].textContent, /部分运行器版本关系待确认，创建前请核对/);
});
test("有角色且可用时不提示；有角色但确定无可用时仍提示", async () => {
  const ready = harness([codex], [{}]); await ready.env.maybeShowRunnerOnboarding(); assert.equal(ready.hidden(), true);
  const missing = harness(missingRunners, [{}]); await missing.env.maybeShowRunnerOnboarding(); assert.equal(missing.hidden(), false);
  assert.match(missing.nodes["runner-onboarding-message"].textContent, /Codex CLI、Kimi Code、DeepSeek Harness/);
  assert.equal(missing.nodes["runner-onboarding-action"].textContent, "查看运行器状态");
  missing.click("runner-onboarding-dismiss"); await missing.env.maybeShowRunnerOnboarding(); assert.equal(missing.hidden(), true);
});
test("WorkBuddy 不计入；受支持运行器 unknown 无版本时不误报", async () => {
  const h = harness([{ ...workbuddy, probe_status: "missing" }, missingRunners[0]]); await h.env.maybeShowRunnerOnboarding();
  assert.equal(h.hidden(), false); assert.doesNotMatch(h.nodes["runner-onboarding-message"].textContent, /WorkBuddy/);
  const unknown = harness([workbuddy, { ...codex, status: "unknown", detected_version: null }]); await unknown.env.maybeShowRunnerOnboarding();
  assert.equal(unknown.hidden(), true);
});
test("无角色且全部缺失时列出缺失名称，混合错误时标注未知", async () => {
  const all = harness(missingRunners); await all.env.maybeShowRunnerOnboarding();
  assert.equal(all.hidden(), false);
  assert.match(all.nodes["runner-onboarding-message"].textContent, /缺少 Codex CLI、Kimi Code、DeepSeek Harness 运行器/);
  assert.doesNotMatch(all.nodes["runner-onboarding-message"].textContent, /其余运行器状态未知/);
  const mixed = harness([missingRunners[0], {...missingRunners[1], probe_status: "error"}, workbuddy]);
  await mixed.env.maybeShowRunnerOnboarding();
  assert.equal(mixed.hidden(), false);
  assert.match(mixed.nodes["runner-onboarding-message"].textContent, /缺少 Codex CLI 运行器.*其余运行器状态未知/);
  assert.doesNotMatch(mixed.nodes["runner-onboarding-message"].textContent, /Kimi Code|WorkBuddy/);
  const legacy = harness([missingRunners[0], {...kimi, detected_version: null, status: "unknown"}]);
  await legacy.env.maybeShowRunnerOnboarding();
  assert.match(legacy.nodes["runner-onboarding-message"].textContent, /其余运行器状态未知/);
});
test("仅错误、旧响应、WorkBuddy 或空数组时不弹窗", async () => {
  for (const items of [[], [workbuddy], [{...missingRunners[0], probe_status: "error"}],
    [{...codex, detected_version: null, status: "unknown"}], [workbuddy, {...missingRunners[0], probe_status: "error"}]]) {
    const h = harness(items); await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), true);
  }
});
test("请求失败、非数组不误报", async () => {
  for (const api of [async () => { throw Error("offline"); }, async () => ({ok:false}), async () => ({ok:true, json: async () => ({})})]) {
    const h = harness(); h.env.apiFetch = api; await h.env.maybeShowRunnerOnboarding();
    assert.equal(h.hidden(), true); assert.equal(h.calls.warnings.length, 1);
  }
});
test("session 去重，项目或成员变化可再次判定，Esc 关闭", async () => {
  const h = harness(); await h.env.maybeShowRunnerOnboarding(); h.click("runner-onboarding-dismiss");
  await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), true);
  h.env.activeProjectId = "p2"; await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), false);
  let prevented = false, stopped = false;
  h.nodes["runner-onboarding-overlay"].fire("keydown", {key:"Escape", preventDefault() { prevented = true; }, stopPropagation() { stopped = true; }});
  assert.ok(prevented && stopped && h.hidden()); await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), true);
  h.env.myId = "human:b"; await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), false);
});
test("按钮仅导航和打开表单或滚动状态面板", async () => {
  const ready = harness(); await ready.env.maybeShowRunnerOnboarding(); ready.click("runner-onboarding-action");
  assert.equal(ready.hidden(), true); assert.equal(ready.env.workspaceUI.mode, "roles"); assert.equal(ready.env.workspaceUI.roleSelection, "settings");
  assert.equal(ready.env.blackboardOpen, true); assert.equal(ready.calls.render, 1); assert.equal(ready.calls.open, 1);
  const missing = harness(missingRunners); await missing.env.maybeShowRunnerOnboarding(); missing.click("runner-onboarding-action");
  assert.equal(missing.env.workspaceUI.mode, "roles"); assert.equal(missing.env.workspaceUI.roleSelection, "settings"); assert.equal(missing.env.blackboardOpen, true);
  assert.equal(missing.calls.sync, 1); assert.equal(missing.calls.scroll, 1); assert.equal(missing.calls.open, 0);
});
test("其他弹窗打开时不抢占；异步项目切换不显示过期提示", async () => {
  const h = harness(); h.setOtherModal(true); await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), true);
  h.setOtherModal(false); let finish; h.env.apiFetch = () => new Promise(resolve => { finish = resolve; });
  const pending = h.env.maybeShowRunnerOnboarding(); h.env.activeProjectId = "p2";
  finish({ ok: true, json: async () => [codex] }); await pending; assert.equal(h.hidden(), true);
});
test("登录遮罩消失后再显示，非真人不请求", async () => {
  const h = harness(); const login = h.node("login-overlay"); let callback;
  h.env.MutationObserver = class { constructor(fn) { callback = fn; } observe() {} disconnect() {} };
  await h.env.maybeShowRunnerOnboarding(); assert.equal(h.hidden(), true);
  login.classList.add("hidden"); callback(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.hidden(), false);
  const agent = harness(); agent.env.currentMemberIsHuman = () => false;
  agent.env.apiFetch = () => { throw Error("must not fetch"); };
  await agent.env.maybeShowRunnerOnboarding(); assert.equal(agent.hidden(), true); assert.equal(agent.calls.warnings.length, 0);
});
test("静态弹窗语义及项目角色加载入口", () => {
  const html = fs.readFileSync(require.resolve("../web/index.html"), "utf8");
  assert.match(html, /id="runner-onboarding-overlay"/); assert.match(html, /role="dialog" aria-modal="true" aria-labelledby="runner-onboarding-title" aria-describedby="runner-onboarding-message"/);
  const app = fs.readFileSync(require.resolve("../web/app.js"), "utf8");
  assert.match(app.slice(app.indexOf("async function loadProjectAgents()"), app.indexOf("async function loadProjectTasks(")), /projectAgents = loaded;[\s\S]*maybeShowRunnerOnboarding\(\)/);
});
