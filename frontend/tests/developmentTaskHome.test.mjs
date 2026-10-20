import assert from "node:assert/strict";
import { build } from "esbuild";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
async function bundle(name) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(`../src/create/${name}.tsx`, import.meta.url))],
    bundle: true, platform: "node", format: "cjs", write: false, external: ["react"], loader: { ".css": "empty" },
    plugins: [{ name: "boundaries", setup(b) {
      b.onResolve({ filter: /^react-i18next$/ }, () => ({ path: "translation", namespace: "mock" }));
      b.onResolve({ filter: /^@openai\/apps-sdk-ui\/components\/Tooltip$/ }, () => ({ path: "tooltip", namespace: "mock" }));
      b.onLoad({ filter: /.*/, namespace: "mock" }, args => ({ contents: args.path === "translation"
        ? 'export const useTranslation=()=>({t:k=>k,i18n:{language:"en-US"}});'
        : 'export const Tooltip=({children})=>children;', loader: "js" }));
      b.onLoad({ filter: /adk\/developmentRuns\.ts$/ }, () => ({ contents: 'export const {developmentRuns,runEnded,DevelopmentRequestError}=globalThis.homeTaskApi;', loader: "js" }));
      b.onLoad({ filter: /primitives\/Toast\/index\.ts$/ }, () => ({ contents: 'export const ToastProvider=({children})=>children; export const useToast=()=>globalThis.homeTaskToast;', loader: "js" }));
    } }],
  });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  return module.exports;
}
function environment() {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const React = require("react");
  return { dom, React, act: React.act, root: require("react-dom/client").createRoot(document.getElementById("root")) };
}

test("home and notifications share discovery, preserve errors and fence owner changes", async () => {
  const { dom, React, act, root } = environment();
  const requests = [], updates = [], toasts = [];
  class RequestError extends Error { constructor(message, status) { super(message); this.status = status; } }
  globalThis.homeTaskApi = { DevelopmentRequestError: RequestError, runEnded: r => r.state === "succeeded", developmentRuns: {
    active: signal => { const item = deferred(); requests.push({ ...item, signal }); return item.promise; },
    get: async () => { throw new Error("Unexpected detail request"); },
  } };
  globalThis.homeTaskToast = { add: value => toasts.push(value), dismiss() {} };
  const { DevelopmentTaskNotice } = await bundle("DevelopmentTaskNotice");
  const render = (ownerId, refreshKey = 0, hideNotices = true) => act(async () => root.render(React.createElement(DevelopmentTaskNotice, {
    ownerId, refreshKey, hideNotices, sessionId: "", onUpdate: value => updates.push(value), async onOpen() {},
  })));
  const alice = { runId: "a", sessionId: "session-a", message: "Alice private", state: "running" };
  try {
    await render("alice");
    assert.equal(updates.at(-1).loading, true);
    await act(async () => requests[0].resolve([alice]));
    assert.deepEqual(updates.at(-1).runs, [alice]);
    assert.equal(toasts.length, 0, "Home does not show duplicate background popups");
    await render("alice", 1);
    await render("alice", 2);
    assert.equal(requests.length, 2, "Refresh cannot overlap discovery");
    await act(async () => requests[1].reject(new Error("Offline")));
    assert.equal(updates.at(-1).error, "Offline");
    assert.deepEqual(updates.at(-1).runs, [alice], "Transient failure keeps the last list");
    await render("alice", 3, false);
    await act(async () => requests[2].resolve([alice]));
    assert.equal(updates.at(-1).error, "");
    assert.equal(toasts.at(-1).id, "a", "Background notification remains available elsewhere");
    await render("alice", 4);
    const stale = requests.at(-1);
    await render("bob", 4);
    assert.equal(stale.signal.aborted, true);
    assert.equal(updates.at(-1).ownerId, "bob");
    assert.deepEqual(updates.at(-1).runs, []);
    await act(async () => stale.resolve([alice]));
    assert.equal(updates.at(-1).ownerId, "bob");
    await act(async () => requests.at(-1).resolve([{ ...alice, runId: "b", message: "Bob private" }]));
    await render("bob", 5);
    await act(async () => requests.at(-1).reject(new RequestError("Login required", 401)));
    assert.deepEqual(updates.at(-1).runs, [], "Authorization loss clears sensitive data");
    assert.equal(updates.at(-1).error, "Login required");
  } finally {
    await act(async () => root.unmount());
    assert.equal(requests.at(-1).signal.aborted, true);
    dom.window.close();
  }
});

test("home entries reject foreign snapshots and cancel late opens on navigation", async () => {
  const { dom, React, act, root } = environment();
  const { DevelopmentTaskList } = await bundle("DevelopmentTaskList");
  const opens = [];
  let fail = true;
  const pending = deferred();
  const alice = { ownerId: "alice", loading: false, error: "", runs: [{
    runId: "a", sessionId: "old-session", message: "Alice private goal", state: "running", createdAt: 1700000000,
  }] };
  const render = (ownerId, disabled = false) => act(async () => root.render(React.createElement(DevelopmentTaskList, {
    ownerId, disabled, snapshot: alice, onRefresh() {},
    onOpen: async (session, signal) => { opens.push({ session, signal }); if (fail) throw new Error("Connection failed"); await pending.promise; },
  })));
  try {
    await render("bob");
    assert.doesNotMatch(document.body.textContent, /Alice private/);
    await render("alice");
    await act(async () => document.querySelector(".ic-task").click());
    assert.match(document.querySelector('[role="alert"]').textContent, /Connection failed/);
    assert.match(document.body.textContent, /Alice private goal/);
    fail = false;
    await act(async () => document.querySelector(".ic-task").click());
    assert.equal(document.querySelector(".ic-task").disabled, true);
    await act(async () => document.querySelector(".ic-task").click());
    assert.equal(opens.length, 2, "Duplicate open is disabled");
    assert.equal(opens.at(-1).session, "old-session", "Open targets the existing environment");
    await render("alice", true);
    assert.equal(opens.at(-1).signal.aborted, true, "Starting a new build cancels the old navigation");
    await act(async () => pending.resolve());
  } finally { await act(async () => root.unmount()); dom.window.close(); }
});
