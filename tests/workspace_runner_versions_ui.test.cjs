const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../web/workspace.js"), "utf8");
const start = source.indexOf("function runnerVersionText(");
const end = source.indexOf("function syncRunnerVersions(", start);
const ctx = {}; vm.createContext(ctx); vm.runInContext(source.slice(start, end), ctx);
const item = { runtime: "codex", display_name: "Codex CLI", detected_version: "0.164.0", adapted_version: "0.164.0" };
test("一致时简短显示适配版本", () => {
  const text = ctx.runnerVersionText({...item, status: "match"});
  assert.match(text, /已适配 0\.164\.0/); assert.doesNotMatch(text, /仅提示|自动更新/);
});
test("不一致时显示提示", () => {
  const text = ctx.runnerVersionText({...item, detected_version: "0.170.0", status: "newer"});
  assert.match(text, /有新版本/); assert.match(text, /0\.170\.0/); assert.match(text, /仅提示，不会自动更新/);
  assert.match(ctx.runnerVersionText({...item, status: "older"}), /旧于适配/);
});
test("未知占位与原因，不显示升级警告", () => {
  const text = ctx.runnerVersionText({...item, status: "unknown", detected_version: null, detail: "未找到命令"});
  assert.match(text, /未知/); assert.match(text, /未找到命令/); assert.doesNotMatch(text, /有新版本|仅提示/);
});
test("项目设置渲染四个运行器并复用结果，离开后隐藏", async () => {
  const make = () => ({children: [], style: {}, textContent: "", appendChild(n) { this.children.push(n); },
    replaceChildren() { this.children = []; }, classList: { classes: new Set(), add(k) { this.classes.add(k); }, toggle(k, value) { this.hidden = value; } }});
  const panel = make(); panel.isConnected = true; panel.parentElement = {};
  const box = make();
  const messages = [{id: 1, text: "保持不变"}];
  let calls = 0;
  const env = { document: {getElementById: id => id === "runner-versions-panel" ? panel : id === "runner-versions-content" ? box : null, createElement: make},
    blackboardOpen: true, workspaceUI: {mode: "roles", roleSelection: "settings"}, myId: "agent:test", activeProjectId: "p1", messages,
    workspaceSettingsSelected() { return env.workspaceUI.roleSelection === "settings"; },
    apiFetch: async () => { calls++; return {ok: true, json: async () => [
      {...item, display_name: "<img>", status: "newer"},
      {...item, runtime: "kimi", display_name: "Kimi", status: "match"},
      {...item, runtime: "claude", display_name: "Claude", status: "older"},
      {...item, runtime: "deepseek", display_name: "DeepSeek", status: "unknown", detected_version: null}
    ]}; } };
  vm.createContext(env);
  vm.runInContext(source.slice(source.indexOf("const runnerVersionsUI"), source.indexOf("// 参与任务分页")), env);
  env.syncRunnerVersions();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1); assert.equal(panel.classList.hidden, false);
  assert.equal(box.children.length, 4);
  assert.match(box.children[0].textContent, /<img>.*有新版本/);
  assert.match(box.children[1].textContent, /Kimi.*已适配/);
  assert.match(box.children[2].textContent, /Claude.*旧于适配/);
  assert.match(box.children[3].textContent, /DeepSeek.*未知/);
  assert.ok(box.children[0].classList.classes.has("runner-version-mismatch"));
  assert.ok(box.children[2].classList.classes.has("runner-version-mismatch"));
  assert.deepEqual(box.children[0].style, {});
  assert.deepEqual(messages, [{id: 1, text: "保持不变"}]);
  env.syncRunnerVersions(); assert.equal(calls, 1);
  env.workspaceUI.roleSelection = "role"; env.syncRunnerVersions(); assert.equal(panel.classList.hidden, true);
  for (const mode of ["tasks", "chats"]) {
    env.workspaceUI.mode = mode; env.syncRunnerVersions(); assert.equal(panel.classList.hidden, true);
  }
});
test("项目设置中面板顺序及同步入口", () => {
  const html = fs.readFileSync(require.resolve("../web/index.html"), "utf8");
  const controller = html.indexOf('id="controller-mode-panel"');
  const versions = html.indexOf('id="runner-versions-panel"');
  const host = html.indexOf('id="role-request-host-panel"');
  assert.ok(controller >= 0 && controller < versions && versions < host);
  assert.doesNotMatch(html, /id="runner-versions"/);
  const layout = source.slice(source.indexOf("function syncWorkspaceLayout()"), source.indexOf("function workspaceTaskRow("));
  assert.doesNotMatch(layout, /syncRunnerVersions/);
  const controllerRender = source.slice(source.indexOf("function renderControllerModePanel()"), source.indexOf("function renderControllerModePanel()") + 180);
  assert.match(controllerRender, /syncRunnerVersions/);
});
test("加载失败显示未知", async () => {
  const make = () => ({children: [], appendChild(n) { this.children.push(n); }, replaceChildren() { this.children = []; }, classList: {toggle() {}, add() {}}});
  const panel = make(); panel.isConnected = true; panel.parentElement = {};
  const box = make();
  const env = {document: {getElementById: id => id === "runner-versions-panel" ? panel : box, createElement: make},
    blackboardOpen: true, workspaceUI: {mode: "roles"}, myId: "a", activeProjectId: "p",
    workspaceSettingsSelected: () => true, apiFetch: async () => { throw new Error("offline"); }};
  vm.createContext(env);
  vm.runInContext(source.slice(source.indexOf("const runnerVersionsUI"), source.indexOf("// 参与任务分页")), env);
  env.syncRunnerVersions();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(box.children[0].textContent, "未知");
});

test("角色导航立即同步版本面板并复用缓存", async () => {
  // 复用已有 DOM 环境及 app.js 真实渲染链，执行 workspace.js 的真实点击绑定。
  const harnessSource = fs.readFileSync(require.resolve("./workspace_initiator_mode_ui.test.cjs"), "utf8");
  const setup = harnessSource.slice(0, harnessSource.indexOf("test('静态"));
  assert.ok(setup.includes("function harness()"));
  const makeHarness = new Function("require", setup + "\nreturn harness;")(require);
  const h = makeHarness();
  const panel = h.el("runner-versions-panel");
  panel.isConnected = true; panel.parentElement = {}; panel.classList.add("hidden");
  const calls = () => h.requests.filter(r => r.url === "/api/runners/versions").length;
  for (const mode of ["tasks", "chats"]) {
    h.ui.workspaceUI.mode = mode;
    h.context.blackboardOpen = false;
    h.ui.renderWorkspaceMode();
    assert.equal(h.hidden("runner-versions-panel"), true);
    h.el("workspace-roles-btn").fire("click");
    assert.equal(h.hidden("runner-versions-panel"), false, `${mode} 进入角色页立即可见`);
    await h.tick();
    assert.equal(calls(), 1);
    h.ui.renderWorkspaceMode();
    assert.equal(h.hidden("runner-versions-panel"), false);
    await h.tick();
    assert.equal(calls(), 1);
  }
  const roleEntry = h.el("blackboard-columns").children.find(entry => entry.children.some(child => child.dataset?.memberId === "agent:kimi"));
  assert.ok(roleEntry);
  roleEntry.children.find(child => child.dataset?.memberId === "agent:kimi").fire("click");
  assert.equal(h.hidden("runner-versions-panel"), true);
  h.ui.workspaceUI.mode = "tasks";
  h.ui.renderWorkspaceMode();
  assert.equal(h.hidden("runner-versions-panel"), true);
  await h.tick();
  assert.equal(calls(), 1);
});
