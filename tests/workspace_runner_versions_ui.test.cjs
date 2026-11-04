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
test("角色页渲染安全文本并复用结果，离开后隐藏", async () => {
  const make = () => ({children: [], style: {}, textContent: "", appendChild(n) { this.children.push(n); },
    replaceChildren() { this.children = []; }, classList: { toggle(k, value) { this.hidden = value; } }});
  const box = make(); box.isConnected = true; box.parentElement = {};
  let calls = 0;
  const env = { document: {getElementById: () => box, createElement: make},
    blackboardOpen: true, workspaceUI: {mode: "roles"}, myId: "agent:test",
    apiFetch: async () => { calls++; return {ok: true, json: async () => [{...item, display_name: "<img>", status: "newer"}]}; } };
  vm.createContext(env);
  vm.runInContext(source.slice(source.indexOf("const runnerVersionsUI"), source.indexOf("// 参与任务分页")), env);
  env.syncRunnerVersions();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1); assert.equal(box.children[1].textContent.includes("<img>"), true);
  assert.match(box.children[1].textContent, /有新版本/);
  env.syncRunnerVersions(); assert.equal(calls, 1);
  env.workspaceUI.mode = "tasks"; env.syncRunnerVersions(); assert.equal(box.classList.hidden, true);
});
